"""Chi può coprire un turno già assegnato, ad esempio di un dipendente che va in malattia.

Ogni candidato si prova davvero: si toglie il turno a chi lo aveva, lo si dà al candidato come sostituzione e si
confronta il controllo della settimana (`valida_settimana`) prima e dopo. Le ore di una sostituzione sono extra
(non contano nei limiti di ore). Scelta dell'utente:
- esclusi: chi non può fare quel turno (qualifica, divieto, assente, indisponibile, già in servizio a quell'ora)
  e chi lavorerebbe più di LAVORO_DI_FILA_MAX ore senza staccare;
- proposti ma in fondo, con le regole che non rispetterebbe (`regole`): riposo di 11 h, giorni di fila, Ascoli;
- semplici note (`avvisi`): le eccezioni ammesse, come 3 giorni di fila.

Se nessuno può coprirlo rispettando tutte le regole, si cercano catene di un solo passaggio (`catene_sostituzione`):
B prende il turno (ore normali: scambia un suo turno) e cede un suo turno vicino a C (ore extra).
"""
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta

from .modello import SOSTITUZIONE, Assegnazione, Fabbisogno, Persona, ore_extra
from .vincoli import SCARTO_ORE_MAX, Violazione, minimo_ore, ore_ferie, valida_settimana

# errori che rendono impossibile la sostituzione (gli altri nuovi problemi del candidato sono avvisi)
ERRORI_BLOCCANTI = frozenset({"persona", "qualifica", "segmento", "divieto", "ferie", "indisponibile",
                              "sovrapposizione"})
LAVORO_DI_FILA_MAX = 12  # ore di lavoro senza staccare: oltre, mai
PAUSA_STACCO = 2         # una pausa più corta (es. Standby fino alle 19 e notte dalle 20) non interrompe il lavoro
GIORNI_TURNO_CEDUTO = 3  # catene: B cede solo un turno entro 3 giorni (oltre non può essere quello che lo blocca)
CATENE_MAX = 5  # scambi proposti per turno, i migliori prima (l'interfaccia ne mostra 3, gli altri su richiesta)
# un turno in più avvicina sempre al minimo di ore: il messaggio cambia ma non è un problema nuovo
ERRORI_IGNORATI = frozenset({"ore_min"})


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
    origine: str = SOSTITUZIONE,
) -> list[Candidato]:
    """Dipendenti tra `candidabili` che possono prendere `turno` al posto di chi lo ha, i migliori prima:
    prima chi rispetta tutte le regole (poi chi ne viola meno), poi chi ha meno note, poi chi ha lavorato meno ore
    (extra e ferie comprese), poi il nome.

    `assegnazioni`: i turni della settimana, `turno` compreso (ValueError se manca).
    `origine`: come lo prenderebbe il candidato (predefinito: sostituzione, ore extra).
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
        nuovo = replace(turno, persona_id=pid, origine=origine)
        suoi = [a for a in [*senza, *contesto] if a.persona_id == pid]
        if ore_di_fila(suoi, nuovo) > LAVORO_DI_FILA_MAX:
            continue
        nuove = [v for v in controlla([*senza, nuovo]) - prima
                 if v.persona_id == pid and v.codice not in ERRORI_IGNORATI]
        if any(v.livello == "errore" and v.codice in ERRORI_BLOCCANTI for v in nuove):
            continue
        contate = ore[pid] + ore_ferie(giorni, ferie.get(pid, set()))
        regole = tuple(sorted(v.messaggio for v in nuove if v.livello == "errore"))
        avvisi = tuple(sorted(v.messaggio for v in nuove if v.livello != "errore"))
        out.append(Candidato(pid, p.nome, p.qualifica, ore[pid], extra[pid], contate,
                             ore[pid] + extra[pid] + turno.ore, regole, avvisi))
    return sorted(out, key=lambda c: (len(c.regole), len(c.avvisi), c.ore_contate + c.ore_sostituzioni,
                                      c.nome.lower(), c.persona_id))


@dataclass(frozen=True)
class Catena:
    prende: Candidato       # B: prende il turno da coprire e cede `ceduto` (ore normali)
    ceduto: Assegnazione    # il turno di B che passa a C
    copre: Candidato        # C: prende `ceduto` come sostituzione (ore extra)


def prova_catena(turno: Assegnazione, prende: int, ceduto: Assegnazione, copre: int, *,
                 assegnazioni: Sequence[Assegnazione], **regole) -> Catena | None:
    """La catena se B (`prende`) e C (`copre`) rispettano entrambi tutte le regole, altrimenti None."""
    if ceduto not in assegnazioni or ceduto.persona_id != prende or copre in (prende, turno.persona_id):
        return None
    b = _prova_b(turno, ceduto, assegnazioni, regole)
    if b is None:
        return None
    c = candidati_sostituzione(ceduto, [copre], assegnazioni=_dopo_b(turno, ceduto, assegnazioni), **regole)
    if not c or c[0].regole:
        return None
    return Catena(b, ceduto, c[0])


def _prova_b(turno, ceduto, assegnazioni, regole) -> Candidato | None:
    """B se, cedendo `ceduto`, prende `turno` rispettando tutte le regole e senza scendere sotto il minimo di ore."""
    pid = ceduto.persona_id
    prova = candidati_sostituzione(turno, [pid], assegnazioni=_senza(assegnazioni, ceduto), origine="manuale",
                                   **regole)
    if not prova or prova[0].regole:
        return None
    b = prova[0]
    ceduto_conta = 0 if ore_extra(ceduto) else ceduto.ore
    ferie = b.ore_contate - b.ore
    prima, dopo = b.ore + ceduto_conta, b.ore + turno.ore  # ore che contano, prima e dopo lo scambio
    if dopo < prima and dopo + ferie < minimo_ore(regole["persone"][pid]):
        return None  # con lo scambio scenderebbe sotto il minimo di ore
    # le ore mostrate sono quelle di B prima dello scambio (col turno che cede)
    return replace(b, ore=prima, ore_contate=prima + ferie)


def _dopo_b(turno, ceduto, assegnazioni) -> list[Assegnazione]:
    """La settimana dopo che B ha preso `turno`, con `ceduto` ancora suo (da passare a C)."""
    senza = _senza(_senza(assegnazioni, ceduto), turno)
    return [*senza, replace(turno, persona_id=ceduto.persona_id, origine="manuale"), ceduto]


def catene_sostituzione(turno: Assegnazione, candidabili: Iterable[int], *, assegnazioni: Sequence[Assegnazione],
                        massimo: int = CATENE_MAX, **regole) -> list[Catena]:
    """Catene di un passaggio, solo se nessuno può coprire `turno` direttamente rispettando tutte le regole.

    Per ogni B si prova a cedere ognuno dei suoi turni vicini al miglior C. Le migliori prima: meno note, poi meno
    ore di C (che lavora in più), poi di B."""
    candidabili = list(dict.fromkeys(candidabili))
    diretti = candidati_sostituzione(turno, candidabili, assegnazioni=assegnazioni, **regole)
    if any(not c.regole for c in diretti):
        return []
    vicino = timedelta(days=GIORNI_TURNO_CEDUTO)
    catene = []
    for b in candidabili:
        for ceduto in assegnazioni:
            if ceduto == turno or ceduto.persona_id != b or abs(ceduto.data - turno.data) > vicino:
                continue
            prova_b = _prova_b(turno, ceduto, assegnazioni, regole)
            if prova_b is None:
                continue
            altri = [c for c in candidabili if c not in (b, turno.persona_id)]
            buoni = [c for c in candidati_sostituzione(ceduto, altri, assegnazioni=_dopo_b(turno, ceduto, assegnazioni),
                                                       **regole) if not c.regole]
            if buoni:
                catene.append(Catena(prova_b, ceduto, buoni[0]))
    catene.sort(key=lambda k: (len(k.prende.avvisi) + len(k.copre.avvisi),
                               k.copre.ore_contate + k.copre.ore_sostituzioni, k.prende.ore_contate,
                               k.prende.nome.lower(), k.copre.nome.lower()))
    return catene[:massimo]
