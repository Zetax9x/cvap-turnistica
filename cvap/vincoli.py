"""Validazione di una settimana di turni: copertura, qualifiche, riposo, turni consecutivi, ore, assenze.

Usato per controllare sia l'output del generatore sia le modifiche manuali.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

from .modello import ORE_RIPOSO_MIN, Assegnazione, Persona
from .slot import unita_da_coprire

MAX_CONSECUTIVI = 3       # oltre è vietato
SOGLIA_CONSECUTIVI = 3    # da qui in su si segnala come eccezione
SCARTO_ORE_MAX = 12

_SOVRAPPOSTI = {
    "intero": {"intero", "mattina", "pomeriggio"},
    "mattina": {"intero", "mattina"},
    "pomeriggio": {"intero", "pomeriggio"},
}


@dataclass(frozen=True)
class Violazione:
    livello: str          # "errore" | "avviso"
    codice: str
    messaggio: str
    persona_id: int | None = None
    data: date | None = None


def _fmt(d: date) -> str:
    return d.strftime("%d/%m")


def _descrivi(a: Assegnazione) -> str:
    seg = "" if a.segmento == "intero" else f" ({a.segmento})"
    return f"{a.postazione} {a.fascia}{seg} {_fmt(a.data)}"


def valida_settimana(
    giorni: list[date],
    postazioni: list[str],
    assegnazioni: list[Assegnazione],
    persone: dict[int, Persona],
    contesto: list[Assegnazione] = (),
    ferie: dict[int, set[date]] | None = None,
    indisponibili: dict[int, set[date]] | None = None,
) -> list[Violazione]:
    """`ferie` e `indisponibili`: giorni (per id persona) in cui non può iniziare alcun turno.

    Le ferie riducono anche la quota di ore della settimana, in proporzione ai giorni.
    """
    ferie, indisponibili = ferie or {}, indisponibili or {}
    violazioni: list[Violazione] = []
    violazioni += _copertura(giorni, postazioni, assegnazioni)
    violazioni += _doppioni(assegnazioni)
    violazioni += _qualifiche(assegnazioni, persone)
    violazioni += _assenze(assegnazioni, persone, ferie, "ferie", "è in ferie")
    violazioni += _assenze(assegnazioni, persone, indisponibili, "indisponibile", "è indisponibile")

    settimana = set(giorni)
    per_persona: dict[int, list[Assegnazione]] = defaultdict(list)
    for a in list(assegnazioni) + list(contesto):
        per_persona[a.persona_id].append(a)
    for pid, turni in per_persona.items():
        persona = persone.get(pid)
        nome = persona.nome if persona else f"#{pid}"
        # le regole di riposo valgono per i dipendenti; per i volontari sono solo avvisi
        livello = "errore" if persona and persona.dipendente else "avviso"
        violazioni += _riposo(pid, nome, turni, settimana, livello)
        violazioni += _consecutivi(pid, nome, turni, settimana, livello)

    violazioni += _ore(giorni, assegnazioni, persone, ferie)
    return violazioni


def _copertura(giorni, postazioni, assegnazioni):
    return [
        Violazione("errore", "scoperto", f"Posto scoperto: {u.ruolo} {_descrivi(u)}", data=u.data)
        for u in unita_da_coprire(giorni, postazioni, assegnazioni)
    ]


def _doppioni(assegnazioni):
    per_posto: dict[tuple, list[Assegnazione]] = defaultdict(list)
    for a in assegnazioni:
        per_posto[a.chiave].append(a)
    out = []
    for gruppo in per_posto.values():
        for a, b in combinations(gruppo, 2):
            if b.segmento in _SOVRAPPOSTI[a.segmento]:
                out.append(Violazione("errore", "doppione",
                                      f"Posto {a.ruolo} {_descrivi(a)} assegnato due volte", data=a.data))
    return out


def _qualifiche(assegnazioni, persone):
    out = []
    for a in assegnazioni:
        p = persone.get(a.persona_id)
        if p is None:
            out.append(Violazione("errore", "persona", f"Persona sconosciuta in {_descrivi(a)}", a.persona_id, a.data))
        elif not p.puo_ricoprire(a.ruolo):
            out.append(Violazione("errore", "qualifica",
                                  f"{p.nome} non è autista ({_descrivi(a)})", p.id, a.data))
        if a.fascia == "notte" and a.segmento != "intero":
            out.append(Violazione("errore", "segmento", f"La notte non si può spezzare ({_descrivi(a)})",
                                  a.persona_id, a.data))
    return out


def _assenze(assegnazioni, persone, giorni_assenza, codice, testo):
    out = []
    for a in assegnazioni:
        if a.data in giorni_assenza.get(a.persona_id, ()):
            p = persone.get(a.persona_id)
            nome = p.nome if p else f"#{a.persona_id}"
            out.append(Violazione("errore", codice, f"{nome} {testo} il {_fmt(a.data)} ({_descrivi(a)})",
                                  a.persona_id, a.data))
    return out


def giorni_disponibili(giorni: list[date], ferie: set[date]) -> int:
    """Giorni della settimana non in ferie: la quota di ore è media * giorni / 7."""
    return sum(1 for d in giorni if d not in ferie)


def _riposo(pid, nome, turni, settimana, livello):
    out = []
    for a, b in combinations(sorted(turni, key=lambda t: t.inizio), 2):
        if a.data not in settimana and b.data not in settimana:
            continue
        pausa = b.inizio - a.fine
        if pausa < 0:
            out.append(Violazione("errore", "sovrapposizione",
                                  f"{nome} è in due turni contemporaneamente: {_descrivi(a)} e {_descrivi(b)}",
                                  pid, b.data))
        elif pausa < ORE_RIPOSO_MIN:
            out.append(Violazione(livello, "riposo",
                                  f"{nome}: solo {pausa}h di riposo tra {_descrivi(a)} e {_descrivi(b)}",
                                  pid, b.data))
    return out


def _consecutivi(pid, nome, turni, settimana, livello):
    out = []
    for fascia in ("giorno", "notte"):
        date_lavorate = sorted({t.data for t in turni if t.fascia == fascia})
        for inizio, lunghezza in _sequenze(date_lavorate):
            serie = {inizio + timedelta(days=i) for i in range(lunghezza)}
            if lunghezza < SOGLIA_CONSECUTIVI or not serie & settimana:
                continue
            etichetta = "giorni" if fascia == "giorno" else "notti"
            if lunghezza > MAX_CONSECUTIVI:
                out.append(Violazione(livello, "consecutivi",
                                      f"{nome}: {lunghezza} {etichetta} di fila dal {_fmt(inizio)} (massimo {MAX_CONSECUTIVI})",
                                      pid, inizio))
            else:
                out.append(Violazione("avviso", "consecutivi",
                                      f"{nome}: {lunghezza} {etichetta} di fila dal {_fmt(inizio)} (eccezione)",
                                      pid, inizio))
    return out


def _sequenze(date_ordinate: list[date]):
    """Restituisce (inizio, lunghezza) di ogni serie di date consecutive."""
    serie = []
    for d in date_ordinate:
        if serie and d - serie[-1][0] == timedelta(days=serie[-1][1]):
            serie[-1] = (serie[-1][0], serie[-1][1] + 1)
        else:
            serie.append((d, 1))
    return serie


def _ore(giorni, assegnazioni, persone, ferie):
    # chi è in ferie tutta la settimana non conta; gli altri hanno una quota proporzionale ai giorni
    disponibili = {p.id: giorni_disponibili(giorni, ferie.get(p.id, set()))
                   for p in persone.values() if p.dipendente}
    dipendenti = [p for p in persone.values() if disponibili.get(p.id)]
    if not dipendenti:
        return []
    ore = {p.id: 0 for p in dipendenti}
    for a in assegnazioni:
        if a.persona_id in ore:
            ore[a.persona_id] += a.ore
    # media di un dipendente a tempo pieno (7 giorni disponibili)
    media = sum(ore.values()) / (sum(disponibili[p.id] for p in dipendenti) / 7)
    out = []
    for p in dipendenti:
        quota = media * disponibili[p.id] / 7
        scarto = ore[p.id] - quota
        if abs(scarto) > SCARTO_ORE_MAX:
            rif = f"dalla media ({media:.1f}h)" if disponibili[p.id] == 7 else f"dalla quota ({quota:.1f}h, ferie)"
            out.append(Violazione("errore", "ore", f"{p.nome}: {ore[p.id]}h, scarto {scarto:+.1f}h {rif}", p.id))
    return out
