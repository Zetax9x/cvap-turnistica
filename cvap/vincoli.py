"""Validazione di una settimana di turni: copertura, qualifiche, riposo, turni consecutivi, ore, assenze.

Usato per controllare sia l'output del generatore sia le modifiche manuali.
"""
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import combinations

from .modello import (ORE_RIPOSO_MIN, PARTI_TURNO, Assegnazione, Fabbisogno, Persona, orario, parti_turno,
                      si_sovrappongono, turni_ammessi)
from .slot import unita_da_coprire

MAX_CONSECUTIVI = 3       # oltre è vietato
SOGLIA_CONSECUTIVI = 3    # da qui in su si segnala come eccezione
SCARTO_ORE_MAX = 12
ORE_FERIE_GIORNO = 6      # ore che conta ogni giorno di ferie nel confronto con la media
ORE_MIN_SETTIMANA = 36    # ore minime di ogni dipendente, ferie comprese
ORE_MAX_SETTIMANA = 72    # ore lavorate massime di ogni dipendente (le ferie non contano): nessuno le supera
ASCOLI = "Ascoli"
MAX_TURNI_ASCOLI = 2      # turni a settimana per dipendente ad Ascoli
MAX_TURNI_ASCOLI_EXTREMIS = 3  # solo se non c'è altra soluzione (avviso); oltre è vietato

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
    if a.segmento == "intero":
        seg = ""
    else:
        try:
            inizio, fine = orario(a.data, a.fascia, a.segmento)
            seg = f" {inizio % 24}-{fine % 24}"
        except ValueError:
            seg = f" ({a.segmento})"
    return f"{a.postazione} {a.fascia}{seg} {_fmt(a.data)}"


def valida_settimana(
    giorni: list[date],
    postazioni: list[str],
    assegnazioni: list[Assegnazione],
    persone: dict[int, Persona],
    contesto: list[Assegnazione] = (),
    ferie: dict[int, set[date]] | None = None,
    indisponibili: dict[int, set[tuple[date, str]]] | None = None,
    fabbisogno: Sequence[Fabbisogno] = (),
    scarto_ore_max: int = SCARTO_ORE_MAX,
) -> list[Violazione]:
    """`ferie`: giorni (per id persona) in cui non può iniziare alcun turno.
    `indisponibili`: coppie (giorno, parte) per id persona; un turno è vietato se una delle sue parti
    (`parti_turno`) è indisponibile nel giorno in cui inizia.

    Ogni giorno di ferie conta ORE_FERIE_GIORNO ore nel confronto delle ore.
    `fabbisogno`: posti richiesti nelle postazioni a richiesta (Standby, Programmati).
    `scarto_ore_max`: differenza massima ammessa tra chi fa più ore e chi ne fa meno (ferie comprese),
    tra i dipendenti senza massimo ore.
    """
    ferie, indisponibili = ferie or {}, indisponibili or {}
    violazioni: list[Violazione] = []
    violazioni += _copertura(giorni, postazioni, assegnazioni, fabbisogno)
    violazioni += _doppioni(assegnazioni, postazioni)
    violazioni += _eccessi(giorni, assegnazioni, postazioni, fabbisogno)
    violazioni += _qualifiche(assegnazioni, persone)
    violazioni += _divieti(assegnazioni, persone)
    violazioni += _assenze(assegnazioni, persone, ferie, "ferie", "è in ferie")
    violazioni += _indisponibilita(assegnazioni, persone, indisponibili)

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
        if persona and persona.dipendente:
            violazioni += _ascoli_di_fila(pid, nome, turni, settimana)

    violazioni += _ore(giorni, assegnazioni, persone, ferie, scarto_ore_max)
    violazioni += _ascoli(assegnazioni, persone)
    return violazioni


def _copertura(giorni, postazioni, assegnazioni, fabbisogno):
    return [
        Violazione("errore", "scoperto", f"Posto scoperto: {u.ruolo} {_descrivi(u)}", data=u.data)
        for u in unita_da_coprire(giorni, postazioni, assegnazioni, fabbisogno)
    ]


def _doppioni(assegnazioni, postazioni):
    """Posti delle postazioni normali coperti due volte nelle stesse ore (per Standby e Programmati: `_eccessi`)."""
    per_posto: dict[tuple, list[Assegnazione]] = defaultdict(list)
    for a in assegnazioni:
        if a.postazione in postazioni:
            per_posto[a.chiave].append(a)
    out = []
    for gruppo in per_posto.values():
        for a, b in combinations(gruppo, 2):
            if si_sovrappongono(a.segmento, b.segmento):
                out.append(Violazione("errore", "doppione",
                                      f"Posto {a.ruolo} {_descrivi(a)} assegnato due volte", data=a.data))
    return out


def _eccessi(giorni, assegnazioni, postazioni, fabbisogno):
    """Nelle postazioni a richiesta: persone in turni non richiesti o più di quante richieste."""
    settimana = set(giorni)
    richiesti = Counter()
    for f in fabbisogno:
        richiesti[(f.data, f.postazione, f.fascia, f.ruolo)] += f.quantita
        if f.segmento.startswith("prog_"):
            richiesti[(f.data, f.postazione, f.fascia, f.segmento, f.ruolo)] += f.quantita
    presenti: dict[tuple, list[Assegnazione]] = defaultdict(list)
    for a in assegnazioni:
        if a.postazione in postazioni or a.data not in settimana:
            continue
        # Programmati: si conta per segmento; Standby: per posto (le due metà sono lo stesso posto)
        chiave = ((a.data, a.postazione, a.fascia, a.segmento, a.ruolo) if a.segmento.startswith("prog_")
                  else a.chiave)
        presenti[chiave].append(a)
    out = []
    for chiave, gruppo in presenti.items():
        a = gruppo[0]
        # metà di Standby coperte da persone diverse contano come un solo posto
        n = len(gruppo) if a.segmento.startswith("prog_") else _posti_occupati(gruppo)
        if n > richiesti[chiave]:
            out.append(Violazione("errore", "eccesso",
                                  f"{a.ruolo} {_descrivi(a)}: {n} assegnati, richiesti {richiesti[chiave]}",
                                  data=a.data))
    return out


def _posti_occupati(gruppo: list[Assegnazione]) -> int:
    """Quanti posti singoli servono per ospitare i turni (le due metà di un turno ne occupano uno)."""
    interi = sum(1 for a in gruppo if a.segmento in ("intero", "standby"))
    mattine = sum(1 for a in gruppo if a.segmento.endswith("mattina"))
    pomeriggi = sum(1 for a in gruppo if a.segmento.endswith("pomeriggio"))
    return interi + max(mattine, pomeriggi)


def _qualifiche(assegnazioni, persone):
    out = []
    for a in assegnazioni:
        p = persone.get(a.persona_id)
        if p is None:
            out.append(Violazione("errore", "persona", f"Persona sconosciuta in {_descrivi(a)}", a.persona_id, a.data))
        elif not p.puo_ricoprire(a.ruolo, a.postazione):
            out.append(Violazione("errore", "qualifica",
                                  f"{p.nome} non è autista ({_descrivi(a)})", p.id, a.data))
        if (a.fascia, a.segmento) not in turni_ammessi(a.postazione):
            out.append(Violazione("errore", "segmento", f"Orario non valido per {a.postazione} ({_descrivi(a)})",
                                  a.persona_id, a.data))
    return out


def _divieti(assegnazioni, persone):
    out = []
    for a in assegnazioni:
        p = persone.get(a.persona_id)
        if p and p.dipendente and p.vieta(a.postazione, a.fascia, a.segmento):
            out.append(Violazione("errore", "divieto",
                                  f"{p.nome} non può fare questo turno ({_descrivi(a)})", p.id, a.data))
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


def _indisponibilita(assegnazioni, persone, indisponibili):
    out = []
    for a in assegnazioni:
        indisp = indisponibili.get(a.persona_id, ())
        bloccate = [parte for parte in PARTI_TURNO
                    if parte in parti_turno(a.fascia, a.segmento) and (a.data, parte) in indisp]
        if bloccate:
            p = persone.get(a.persona_id)
            nome = p.nome if p else f"#{a.persona_id}"
            quando = " e ".join(f"di {parte}" if parte == "notte" else f"la {parte}" for parte in bloccate)
            out.append(Violazione("errore", "indisponibile",
                                  f"{nome} è indisponibile {quando} il {_fmt(a.data)} ({_descrivi(a)})",
                                  a.persona_id, a.data))
    return out


def giorni_disponibili(giorni: list[date], ferie: set[date]) -> int:
    """Giorni della settimana non in ferie (0 = in ferie tutta la settimana)."""
    return sum(1 for d in giorni if d not in ferie)


def ore_ferie(giorni: list[date], ferie: set[date]) -> int:
    """Ore accreditate per le ferie nella settimana: ORE_FERIE_GIORNO per giorno."""
    return ORE_FERIE_GIORNO * (len(giorni) - giorni_disponibili(giorni, ferie))


def media_ore(ore: dict[int, int], crediti: dict[int, int]) -> float:
    """Media ore dei dipendenti, contando le ore di ferie (`crediti`) come lavorate."""
    return sum(ore[pid] + crediti.get(pid, 0) for pid in ore) / len(ore) if ore else 0.0


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


def _ascoli_di_fila(pid, nome, turni, settimana):
    """Ad Ascoli mai due turni della stessa fascia in giorni consecutivi (anche mezzo turno)."""
    out = []
    for fascia in ("giorno", "notte"):
        date_ascoli = {t.data for t in turni if t.postazione == ASCOLI and t.fascia == fascia}
        for d in sorted(date_ascoli):
            dopo = d + timedelta(days=1)
            if dopo in date_ascoli and {d, dopo} & settimana:
                etichetta = "giorni" if fascia == "giorno" else "notti"
                out.append(Violazione("errore", "ascoli_di_fila",
                                      f"{nome}: due {etichetta} di fila ad Ascoli ({_fmt(d)} e {_fmt(dopo)})",
                                      pid, dopo))
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


def _ascoli(assegnazioni, persone):
    # ogni posto conta come un turno, anche mezzo turno; vale solo per i dipendenti
    conta = Counter(a.persona_id for a in assegnazioni if a.postazione == ASCOLI)
    out = []
    for pid, n in conta.items():
        p = persone.get(pid)
        if not p or not p.dipendente or n <= MAX_TURNI_ASCOLI:
            continue
        livello = "errore" if n > MAX_TURNI_ASCOLI_EXTREMIS else "avviso"
        out.append(Violazione(livello, "ascoli",
                              f"{p.nome}: {n} turni ad Ascoli (massimo {MAX_TURNI_ASCOLI}, "
                              f"{MAX_TURNI_ASCOLI_EXTREMIS} solo in extremis)", pid))
    return out


def differenza_ore(giorni, assegnazioni, persone, ferie) -> dict | None:
    """Differenza tra chi fa più ore e chi ne fa meno, sulle ore contate (lavorate + ferie).

    Partecipano i dipendenti presenti (non in ferie tutta la settimana) senza massimo ore.
    Con meno di 2 partecipanti restituisce None."""
    ore = {p.id: ore_ferie(giorni, ferie.get(p.id, set())) for p in persone.values()
           if p.dipendente and p.max_ore_settimana is None
           and giorni_disponibili(giorni, ferie.get(p.id, set()))}
    for a in assegnazioni:
        if a.persona_id in ore:
            ore[a.persona_id] += a.ore
    if len(ore) < 2:
        return None
    # a pari ore sceglie l'id più basso, per un risultato stabile
    pid_max = min(ore, key=lambda pid: (-ore[pid], pid))
    pid_min = min(ore, key=lambda pid: (ore[pid], pid))

    def voce(pid):
        return {"persona_id": pid, "nome": persone[pid].nome, "ore": ore[pid]}

    return {"differenza": ore[pid_max] - ore[pid_min], "massimo": voce(pid_max), "minimo": voce(pid_min)}


def minimo_ore(p: Persona) -> int:
    """Ore minime della settimana: ORE_MIN_SETTIMANA, o il massimo ore della persona se più basso."""
    return ORE_MIN_SETTIMANA if p.max_ore_settimana is None else min(ORE_MIN_SETTIMANA, p.max_ore_settimana)


def massimo_ore(p: Persona) -> int:
    """Ore lavorate massime della settimana: ORE_MAX_SETTIMANA, o il massimo ore della persona se più basso."""
    return ORE_MAX_SETTIMANA if p.max_ore_settimana is None else min(ORE_MAX_SETTIMANA, p.max_ore_settimana)


def sotto_minimo(giorni, assegnazioni, persone, ferie) -> list[dict]:
    """Dipendenti presenti (non in ferie tutta la settimana) con ore lavorate + ferie sotto il minimo."""
    lavorate = Counter()
    for a in assegnazioni:
        lavorate[a.persona_id] += a.ore
    out = []
    for p in persone.values():
        giorni_ferie = ferie.get(p.id, set())
        if not (p.dipendente and giorni_disponibili(giorni, giorni_ferie)):
            continue
        h_ferie = ore_ferie(giorni, giorni_ferie)
        if lavorate[p.id] + h_ferie < minimo_ore(p):
            out.append({"persona_id": p.id, "nome": p.nome, "ore": lavorate[p.id], "ferie": h_ferie,
                        "minimo": minimo_ore(p)})
    return out


def _ore(giorni, assegnazioni, persone, ferie, scarto_ore_max=SCARTO_ORE_MAX):
    lavorate = Counter()
    for a in assegnazioni:
        lavorate[a.persona_id] += a.ore
    out = []
    for p in persone.values():
        if not (p.dipendente and giorni_disponibili(giorni, ferie.get(p.id, set()))):
            continue  # come nel generatore: chi è in ferie tutta la settimana non conta
        tetto = massimo_ore(p)
        if lavorate[p.id] > tetto:  # le ferie non contano nel tetto
            out.append(Violazione("errore", "ore_max",
                                  f"{p.nome}: {lavorate[p.id]}h, oltre il massimo di {tetto}h a settimana", p.id))
    for x in sotto_minimo(giorni, assegnazioni, persone, ferie):
        extra = f" + {x['ferie']}h ferie" if x["ferie"] else ""
        out.append(Violazione("errore", "ore_min",
                              f"{x['nome']}: {x['ore']}h{extra}, meno del minimo di {x['minimo']}h a settimana",
                              x["persona_id"]))
    d = differenza_ore(giorni, assegnazioni, persone, ferie)
    if d and d["differenza"] > scarto_ore_max:
        alto, basso = d["massimo"], d["minimo"]
        out.append(Violazione("errore", "ore",
                              f"Differenza di {d['differenza']}h tra {alto['nome']} ({alto['ore']}h) e "
                              f"{basso['nome']} ({basso['ore']}h): massimo {scarto_ore_max}h",
                              alto["persona_id"]))
    return out
