"""Chi può coprire un turno già assegnato, ad esempio di un dipendente che va in malattia.

Ogni candidato si prova davvero: si toglie il turno a chi lo aveva, lo si dà al candidato come sostituzione e si
confronta il controllo della settimana (`valida_settimana`) prima e dopo. Le ore di una sostituzione sono extra
(non contano nei limiti di ore). Scelta dell'utente:
- esclusi: chi non può fare quel turno (qualifica, divieto, assente, indisponibile, già in servizio a quell'ora)
  e chi lavorerebbe più di LAVORO_DI_FILA_MAX ore senza staccare;
- proposti ma in fondo, con le regole che non rispetterebbe (`regole`): riposo di 11 h, giorni di fila, Ascoli;
- semplici note (`avvisi`): le eccezioni ammesse, come 3 giorni di fila.
"""
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date

from .modello import SOSTITUZIONE, Assegnazione, Fabbisogno, Persona, ore_extra
from .vincoli import SCARTO_ORE_MAX, Violazione, ore_ferie, valida_settimana

# errori che rendono impossibile la sostituzione (gli altri nuovi problemi del candidato sono avvisi)
ERRORI_BLOCCANTI = frozenset({"persona", "qualifica", "segmento", "divieto", "ferie", "indisponibile",
                              "sovrapposizione"})
LAVORO_DI_FILA_MAX = 12  # ore di lavoro senza staccare: oltre, mai
PAUSA_STACCO = 2         # una pausa più corta (es. Standby fino alle 19 e notte dalle 20) non interrompe il lavoro


@dataclass(frozen=True)
class Candidato:
    persona_id: int
    nome: str
    qualifica: str
    ore: int               # ore di turno della settimana che contano (senza le sostituzioni)
    ore_sostituzioni: int  # ore extra di sostituzioni già fatte nella settimana
    ore_contate: int       # ore + 6 h per giorno di ferie o malattia (come nel confronto tra dipendenti)
    ore_dopo: int          # ore lavorate davvero dopo aver preso il turno, extra comprese
    regole: tuple[str, ...] = ()  # regole che non rispetterebbe (errori del validatore)
    avvisi: tuple[str, ...] = ()  # eccezioni ammesse (avvisi del validatore)


def ore_di_fila(turni: Iterable[Assegnazione], turno: Assegnazione) -> int:
    """Ore di lavoro senza staccare (pause sotto PAUSA_STACCO) del blocco che contiene `turno`."""
    inizio, fine = turno.inizio, turno.fine
    altri = sorted(turni, key=lambda a: a.inizio)
    cambiato = True
    while cambiato:  # allarga il blocco finché un turno lo tocca da una parte o dall'altra
        cambiato = False
        for a in altri:
            if a.inizio < fine + PAUSA_STACCO and a.fine > inizio - PAUSA_STACCO \
                    and (a.inizio < inizio or a.fine > fine):
                inizio, fine, cambiato = min(inizio, a.inizio), max(fine, a.fine), True
    return fine - inizio


def _senza(assegnazioni: Sequence[Assegnazione], turno: Assegnazione) -> list[Assegnazione]:
    """Le assegnazioni senza `turno` (solo una volta, anche se per errore ce ne fossero due uguali)."""
    turni = list(assegnazioni)
    turni.remove(turno)
    return turni


def candidati_sostituzione(
    turno: Assegnazione,
    candidabili: Iterable[int],
    *,
    giorni: list[date],
    postazioni: list[str],
    assegnazioni: Sequence[Assegnazione],
    persone: dict[int, Persona],
    contesto: Sequence[Assegnazione] = (),
    ferie: dict[int, set[date]] | None = None,
    indisponibili: dict[int, set[tuple[date, str]]] | None = None,
    fabbisogno: Sequence[Fabbisogno] = (),
    scarto_ore_max: int = SCARTO_ORE_MAX,
) -> list[Candidato]:
    """Dipendenti tra `candidabili` che possono prendere `turno` al posto di chi lo ha, i migliori prima:
    prima chi rispetta tutte le regole (poi chi ne viola meno), poi chi ha meno note, poi chi ha lavorato meno ore
    (extra e ferie comprese), poi il nome.

    `assegnazioni`: i turni della settimana, `turno` compreso (ValueError se manca).
    """
    if turno not in assegnazioni:
        raise ValueError("il turno da coprire non è tra le assegnazioni della settimana")
    ferie = ferie or {}
    senza = _senza(assegnazioni, turno)

    def controlla(turni: list[Assegnazione]) -> set[Violazione]:
        return set(valida_settimana(giorni, postazioni, turni, persone, contesto=contesto, ferie=ferie,
                                    indisponibili=indisponibili, fabbisogno=fabbisogno,
                                    scarto_ore_max=scarto_ore_max))

    prima = controlla(senza)
    ore, extra = Counter(), Counter()
    for a in senza:
        (extra if ore_extra(a) else ore)[a.persona_id] += a.ore

    out = []
    for pid in dict.fromkeys(candidabili):
        p = persone.get(pid)
        if (p is None or not p.dipendente or pid == turno.persona_id
                or not p.puo_ricoprire(turno.ruolo, turno.postazione)):
            continue
        nuovo = replace(turno, persona_id=pid, origine=SOSTITUZIONE)
        suoi = [a for a in [*senza, *contesto] if a.persona_id == pid]
        if ore_di_fila(suoi, nuovo) > LAVORO_DI_FILA_MAX:
            continue
        nuove = [v for v in controlla([*senza, nuovo]) - prima if v.persona_id == pid]
        if any(v.livello == "errore" and v.codice in ERRORI_BLOCCANTI for v in nuove):
            continue
        contate = ore[pid] + ore_ferie(giorni, ferie.get(pid, set()))
        regole = tuple(sorted(v.messaggio for v in nuove if v.livello == "errore"))
        avvisi = tuple(sorted(v.messaggio for v in nuove if v.livello != "errore"))
        out.append(Candidato(pid, p.nome, p.qualifica, ore[pid], extra[pid], contate,
                             ore[pid] + extra[pid] + turno.ore, regole, avvisi))
    return sorted(out, key=lambda c: (len(c.regole), len(c.avvisi), c.ore_contate + c.ore_sostituzioni,
                                      c.nome.lower(), c.persona_id))
