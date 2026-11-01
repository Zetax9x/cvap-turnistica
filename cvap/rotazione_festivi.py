"""Rotazione delle festività: conteggio per festività e dipendente (docs/PIANO-rotazioni.md, 3.3 e 3.5).

Modulo puro, riusato dal generatore, dalle statistiche e (in seguito) dall'ordine di rotazione in anticipo e dal
quadro dell'equità. Per ogni festività attiva e ogni dipendente, negli ultimi `ANNI_FESTIVI` anni:

- **turni**: turni fatti in quella festività (anni importati + settimane del programma; solo dipendenti);
- **esposizione**: volte in cui la festività è caduta mentre era in servizio. Anni importati: se era nell'elenco
  "in servizio" salvato, altrimenti nella proposta (dipendenti attivi + chi compare nei dati di quell'anno); conta solo
  se la festività è nei dati di quell'anno. Programma: se era tra i dipendenti della settimana, anche in ferie o
  indisponibile (riposo goduto); in malattia in un giorno dei turni che contano, senza averne lavorato uno, no;
- **ultimo_anno**: anno della festività più recente in cui l'ha fatta;
- **debito**: turni − tasso × esposizione, col tasso calcolato tra un gruppo di dipendenti (`debiti`).

Le festività sono dict come in cvap/festivita.py; dello storico importato contano solo le date prima di `limite`
(lunedì della prima settimana generata): dopo, le conta il programma.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta

from .festivita import turni_di, data_nell_anno, occorrenze, turni_festivi
from .modello import Assegnazione

ANNI_FESTIVI = 5
# pesi del generatore (cvap/solver.py), qui perché li usa anche l'ordine di rotazione in anticipo
P_FESTIVITA = 60             # x peso della festività, sul debito della festività
P_STESSA_FESTIVITA = 500     # x peso: l'ha fatta l'anno prima (metà se due anni prima)
FASCE_DISPONIBILE = ("giorno", "notte", "entrambi")  # chi vuole lavorare una festività (3.6)


@dataclass(frozen=True)
class SettimanaProgramma:
    """Una settimana salvata nel programma: lunedì, dipendenti della settimana e turni."""
    inizio: date
    dipendenti: frozenset[int]
    assegnazioni: tuple[Assegnazione, ...]


@dataclass
class ContoFestivita:
    turni: int = 0
    esposizione: int = 0
    ultimo_anno: int | None = None
    debito: float = 0.0

    def lavorata(self, anno: int) -> None:
        self.turni += 1
        self.ultimo_anno = anno if self.ultimo_anno is None else max(self.ultimo_anno, anno)


@dataclass(frozen=True)
class FestiviSettimana:
    """Le festività di una settimana da generare, per il generatore."""
    turni: dict[tuple[date, str], int] = field(default_factory=dict)  # (giorno, fascia) -> id festività
    peso: dict[int, int] = field(default_factory=dict)                # id -> peso (1-3)
    anno: dict[int, int] = field(default_factory=dict)                # id -> anno della festività nella settimana
    conti: dict[int, dict[int, ContoFestivita]] = field(default_factory=dict)  # id -> persona -> conto
    # turni delle festività della settimana fatti prima del lunedì (la notte della sera prima di un lunedì
    # festivo è nella settimana precedente): id -> persona -> turni; contano come già fissati
    fuori_settimana: dict[int, dict[int, int]] = field(default_factory=dict)
    # chi vuole lavorare ogni turno festivo: (giorno, fascia) -> dipendenti; sconto nel generatore (3.6)
    disponibili: dict[tuple[date, str], frozenset[int]] = field(default_factory=dict)


Conti = dict[int, dict[int, ContoFestivita]]


def inizio_periodo(riferimento: date) -> date:
    """Primo giorno del periodo considerato: `ANNI_FESTIVI` anni prima (il 29/2 diventa 28/2)."""
    anno = riferimento.year - ANNI_FESTIVI
    try:
        return riferimento.replace(year=anno)
    except ValueError:
        return date(anno, 2, 28)


def _occorrenza(f: Mapping, giorno_turno: date, fascia: str) -> date:
    """Il giorno della festività a cui appartiene un suo turno (la notte della sera prima è del giorno dopo)."""
    if (giorno_turno, fascia) in turni_di(f, giorno_turno) and data_nell_anno(f, giorno_turno.year) == giorno_turno:
        return giorno_turno
    return giorno_turno + timedelta(days=1)


def _conto(conti: dict, festivita_id: int, persona_id: int) -> ContoFestivita:
    return conti.setdefault(festivita_id, {}).setdefault(persona_id, ContoFestivita())


def _conta_importati(conti: Conti, festivita: list[Mapping], dal: date, al: date, importati: Iterable[Mapping],
                     servizio: Mapping[int, set[int]], dipendenti_attivi: set[int]) -> None:
    per_anno: dict[int, list[Mapping]] = {}
    for r in importati:
        per_anno.setdefault(r["anno"], []).append(r)
    for anno, righe in per_anno.items():
        in_servizio = servizio.get(anno) or set(dipendenti_attivi) | {r["persona_id"] for r in righe}
        for f in festivita:
            d = data_nell_anno(f, anno)
            righe_festivita = [r for r in righe if r["festivita_id"] == f["id"]]
            if d is None or not dal <= d < al or not righe_festivita:
                continue
            for pid in in_servizio:
                _conto(conti, f["id"], pid).esposizione += 1
            for r in righe_festivita:
                _conto(conti, f["id"], r["persona_id"]).lavorata(anno)


def _conta_programma(conti: Conti, festivita: list[Mapping], dal: date, al: date,
                     settimane: Iterable[SettimanaProgramma], malattia: set[tuple[int, date]] | frozenset,
                     dipendenti_attivi: set[int]) -> None:
    per_id = {f["id"]: f for f in festivita}
    mappa = turni_festivi(festivita, dal - timedelta(days=1), al)
    settimane = list(settimane)
    # turni dei dipendenti nei turni che contano, per (festività, giorno della festività): la notte della sera
    # prima può essere nella settimana precedente
    lavorati: dict[tuple[int, date], set[int]] = {}
    for s in settimane:
        for a in s.assegnazioni:
            fid = mappa.get((a.data, a.fascia))
            if fid is None or (a.persona_id not in s.dipendenti and a.persona_id not in dipendenti_attivi):
                continue
            d = _occorrenza(per_id[fid], a.data, a.fascia)
            if dal <= d < al:
                lavorati.setdefault((fid, d), set()).add(a.persona_id)
                _conto(conti, fid, a.persona_id).lavorata(d.year)
    for s in settimane:
        if not s.assegnazioni:
            continue  # settimana vuota o non ancora fatta: nessuna esposizione
        fine = s.inizio + timedelta(days=6)
        for d, f in occorrenze(festivita, max(dal, s.inizio), min(al - timedelta(days=1), fine)):
            giorni_turni = {g for g, _ in turni_di(f, d)}
            chi_ha_lavorato = lavorati.get((f["id"], d), set())
            for pid in s.dipendenti | chi_ha_lavorato:
                malato = any((pid, g) in malattia for g in giorni_turni)
                if pid in chi_ha_lavorato or not malato:
                    _conto(conti, f["id"], pid).esposizione += 1


def debiti(conti: Mapping[int, ContoFestivita], gruppo: Iterable[int],
           fissati: Mapping[int, int] | None = None) -> dict[int, float]:
    """Debito di ogni persona del gruppo: turni (+ già fissati) − tasso × esposizione.

    Il tasso (turni ÷ esposizione) si calcola sul solo gruppo, come per le altre rotazioni del generatore."""
    gruppo = list(gruppo)
    fissati = fissati or {}
    vuoto = ContoFestivita()
    esposizione = sum(conti.get(p, vuoto).esposizione for p in gruppo)
    tasso = sum(conti.get(p, vuoto).turni for p in gruppo) / esposizione if esposizione else 0.0
    return {p: conti.get(p, vuoto).turni + fissati.get(p, 0) - tasso * conti.get(p, vuoto).esposizione
            for p in gruppo}


def conta_festivita(festivita: Iterable[Mapping], riferimento: date, *, limite: date | None,
                    importati: Iterable[Mapping] = (), servizio: Mapping[int, set[int]] | None = None,
                    dipendenti_attivi: Iterable[int] = (), settimane: Iterable[SettimanaProgramma] = (),
                    malattia: set[tuple[int, date]] | frozenset = frozenset()) -> dict[int, dict[int, ContoFestivita]]:
    """Festività -> dipendente -> conto, per le festività cadute in [riferimento − ANNI_FESTIVI anni, riferimento).

    `festivita`: quelle attive. `importati`: righe {anno, festivita_id, persona_id, fascia} dello storico; `servizio`:
    anno -> dipendenti in servizio salvati; `settimane`: le settimane del programma (dalla prima generata in poi);
    `malattia`: coppie (persona, giorno). Ogni dipendente attivo ha un conto per ogni festività; il debito è
    calcolato tra i dipendenti attivi.
    """
    festivita = list(festivita)
    attivi = set(dipendenti_attivi)
    dal = inizio_periodo(riferimento)
    fine_importati = min(riferimento, limite) if limite else riferimento
    conti: dict[int, dict[int, ContoFestivita]] = {f["id"]: {} for f in festivita}
    _conta_importati(conti, festivita, dal, fine_importati, importati, servizio or {}, attivi)
    _conta_programma(conti, festivita, dal, riferimento, settimane, malattia, attivi)
    for fid, per_persona in conti.items():
        for pid in attivi:
            per_persona.setdefault(pid, ContoFestivita())
        for pid, d in debiti(per_persona, attivi).items():
            per_persona[pid].debito = d
    return conti


def costo_festivita(debito: float, peso: int, anno: int, ultimo_anno: int | None) -> float:
    """Costo di rotazione di un turno della festività per una persona, come nel generatore: costo marginale del
    debito, più un supplemento se l'ha fatta l'anno prima (metà se due anni prima)."""
    costo = P_FESTIVITA * peso * (2 * debito + 1)
    if ultimo_anno is not None:
        costo += P_STESSA_FESTIVITA * peso * {1: 1, 2: 0.5}.get(anno - ultimo_anno, 0)
    return costo


def ordine_rotazione(conti: Mapping[int, ContoFestivita], gruppo: Iterable[int], peso: int, anno: int,
                     nomi: Mapping[int, str]) -> list[tuple[int, float]]:
    """(persona, debito) in ordine di precedenza a lavorare la festività: prima il costo più basso nel generatore
    (debito tra il gruppo e chi l'ha fatta di recente), a parità chi non la fa da più tempo, poi il nome."""
    vuoto = ContoFestivita()
    debito = debiti(conti, gruppo)

    def chiave(pid):
        ultimo = conti.get(pid, vuoto).ultimo_anno
        return (costo_festivita(debito[pid], peso, anno, ultimo), -1 if ultimo is None else ultimo,
                nomi.get(pid, "").casefold(), pid)
    return [(pid, debito[pid]) for pid in sorted(debito, key=chiave)]


def turni_disponibili(festivita: Iterable[Mapping], dal: date, al: date,
                      disponibili: Mapping[date, Mapping[int, str]]) -> dict[tuple[date, str], frozenset[int]]:
    """(giorno, fascia) -> chi vuole lavorare quel turno festivo, per i turni in [dal, al].

    `disponibili`: giorno della festività -> persona -> 'giorno' | 'notte' | 'entrambi'. La notte della sera prima è
    una notte della festività; contano solo i turni spuntati per la festività."""
    festivita = list(festivita)
    per_id = {f["id"]: f for f in festivita}
    out: dict[tuple[date, str], frozenset[int]] = {}
    for (g, fascia), fid in turni_festivi(festivita, dal, al).items():
        chi = disponibili.get(_occorrenza(per_id[fid], g, fascia), {})
        persone = frozenset(pid for pid, f in chi.items() if f in (fascia, "entrambi"))
        if persone:
            out[(g, fascia)] = persone
    return out


def festivi_settimana(festivita: Iterable[Mapping], giorni: list[date], conti: Mapping[int, dict[int, ContoFestivita]],
                      contesto: Iterable[Assegnazione] = (), dipendenti: Iterable[int] = (),
                      disponibili: Mapping[date, Mapping[int, str]] | None = None) -> FestiviSettimana:
    """I turni festivi della settimana (festività attive), con peso, anno e conti di ogni festività.

    `contesto`: turni dei giorni prima della settimana; di questi, quelli dei `dipendenti` nella notte della sera
    prima di una festività della settimana (lunedì festivo) vanno in `fuori_settimana`. `disponibili`: chi vuole
    lavorare, per giorno della festività (vedi `turni_disponibili`)."""
    festivita = list(festivita)
    per_id = {f["id"]: f for f in festivita}
    vigilia = giorni[0] - timedelta(days=1)
    tutti = turni_festivi(festivita, vigilia, giorni[-1])
    turni = {t: fid for t, fid in tutti.items() if t[0] >= giorni[0]}
    prima = {t: fid for t, fid in tutti.items() if t[0] == vigilia and _occorrenza(per_id[fid], *t) >= giorni[0]}
    ids = set(turni.values()) | set(prima.values())
    anno: dict[int, int] = {}
    for (g, fascia), fid in sorted(prima.items()) + sorted(turni.items()):
        anno.setdefault(fid, _occorrenza(per_id[fid], g, fascia).year)
    dip = set(dipendenti)
    fuori: dict[int, dict[int, int]] = {}
    for a in contesto:
        fid = prima.get((a.data, a.fascia))
        if fid is not None and a.persona_id in dip:
            chi = fuori.setdefault(fid, {})
            chi[a.persona_id] = chi.get(a.persona_id, 0) + 1
    voglia = turni_disponibili(festivita, giorni[0], giorni[-1], disponibili) if disponibili else {}
    return FestiviSettimana(turni=turni, peso={fid: per_id[fid]["peso"] for fid in ids}, anno=anno,
                            conti={fid: dict(conti.get(fid, {})) for fid in ids}, fuori_settimana=fuori,
                            disponibili=voglia)


def riepilogo_generazione(fs: FestiviSettimana, assegnazioni: Iterable[Assegnazione], dipendenti: Iterable[int],
                          nomi: Mapping[int, str]) -> dict | None:
    """Per il report della generazione, in parole semplici: turni festivi dei dipendenti nella settimana per
    festività, quanti a chi l'aveva lavorata l'anno prima e quante persone hanno più di un turno festivo.
    None se la settimana non ha turni festivi. `nomi`: id festività -> nome."""
    if not fs.turni:
        return None
    dip = set(dipendenti)
    per_festivita: dict[int, int] = {}
    per_persona: dict[int, int] = {}
    anno_prima = 0
    for a in assegnazioni:
        fid = fs.turni.get((a.data, a.fascia))
        if fid is None or a.persona_id not in dip:
            continue
        per_festivita[fid] = per_festivita.get(fid, 0) + 1
        per_persona[a.persona_id] = per_persona.get(a.persona_id, 0) + 1
        conto = fs.conti[fid].get(a.persona_id)
        if conto is not None and conto.ultimo_anno is not None and fs.anno[fid] - conto.ultimo_anno == 1:
            anno_prima += 1
    for chi in fs.fuori_settimana.values():
        for pid, n in chi.items():
            per_persona[pid] = per_persona.get(pid, 0) + n
    primo_turno = {}
    for t, fid in sorted(fs.turni.items()):
        primo_turno.setdefault(fid, t)
    ordine = sorted(primo_turno, key=primo_turno.get)
    return {"per_festivita": [{"festivita": nomi[fid], "turni": per_festivita.get(fid, 0)} for fid in ordine],
            "turni": sum(per_festivita.values()), "anno_prima": anno_prima,
            "persone_con_piu_festivi": sum(1 for n in per_persona.values() if n > 1)}
