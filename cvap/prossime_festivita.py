"""Ordine di rotazione delle prossime festività e storico per anno (docs/PIANO-rotazioni.md, 3.7).

L'ordine usa lo stesso calcolo del generatore (`dati_festivi.dati_conti` + `rotazione_festivi.conta_festivita`,
debito e `costo_festivita` in `ordine_rotazione`), con il periodo che finisce al lunedì della settimana della
festività come quando la si genera: ordine e assegnazione non possono divergere. Differenze possibili, perché è
un'indicazione: il generatore calcola il tasso tra chi quella settimana può fare i turni (ferie, qualifica…) e tiene
conto dei turni già fissati, oltre alle regole (riposi, ore, Ascoli) e ai posti da autista e da soccorritore.
"""
import calendar
import sqlite3
from dataclasses import replace
from datetime import date, timedelta

from . import dati_festivi, db, db_festivi_disponibili, db_festivita, db_storico_festivi
from .calendario import lunedi
from .festivita import data_nell_anno, occorrenze, turni_di, turni_festivi
from .modello import parti_turno
from .rotazione_festivi import ContoFestivita, conta_festivita, inizio_periodo, occorrenza, ordine_rotazione
from .storico_festivi import limite_storico

MESI_MIN, MESI_MAX = 1, 24


def aggiungi_mesi(d: date, mesi: int) -> date:
    """Lo stesso giorno `mesi` mesi dopo (o l'ultimo del mese, se quel giorno non c'è)."""
    m = d.month - 1 + mesi
    anno, mese = d.year + m // 12, m % 12 + 1
    return date(anno, mese, min(d.day, calendar.monthrange(anno, mese)[1]))


def _assenze(conn, dal: date, al: date):
    """Funzione (persona, festività, giorno) -> 'malattia' | 'ferie' | 'indisponibile' | None per i turni che
    contano (la notte della sera prima è del giorno prima)."""
    ferie = db.ferie_periodo(conn, dal, al)
    malattia = db.giorni_malattia(conn, dal, al)
    indisponibili = db.indisponibili_periodo(conn, dal, al)

    def assente(pid: int, f: dict, d: date) -> str | None:
        turni = turni_di(f, d)
        if any((pid, g) in malattia for g, _ in turni):
            return "malattia"
        if any(g in ferie.get(pid, ()) for g, _ in turni):
            return "ferie"
        indisp = indisponibili.get(pid, set())
        if any((g, parte) in indisp for g, fascia in turni for parte in parti_turno(fascia, "intero")):
            return "indisponibile"
        return None
    return assente


def _solo_turni_festivi(festivita: list[dict], dati: dict) -> dict:
    """Le settimane con i soli turni festivi (gli altri `conta_festivita` li scarta comunque), una volta sola invece
    che a ogni riferimento. Una settimana senza turni festivi tiene un turno qualsiasi: resta "con turni" e quindi
    continua a dare esposizione, come nel calcolo completo."""
    settimane = dati["settimane"]
    if not settimane:
        return dati
    mappa = turni_festivi(festivita, settimane[0].inizio - timedelta(days=1), settimane[-1].inizio + timedelta(days=6))
    ridotte = []
    for s in settimane:
        festive = tuple(a for a in s.assegnazioni if (a.data, a.fascia) in mappa)
        ridotte.append(replace(s, assegnazioni=festive or s.assegnazioni[:1]))
    return {**dati, "settimane": ridotte}


def _nel_periodo(dati: dict, riferimento: date) -> dict:
    """I dati di `dati_conti` ristretti a quelli che possono contare per `riferimento` (stesso risultato di
    `conta_festivita`, che filtra da sé, ma senza scorrere ogni volta tutto lo storico): settimane dal giorno prima
    dell'inizio del periodo (la notte della sera prima) a `riferimento`, righe importate degli anni del periodo."""
    dal = inizio_periodo(riferimento)
    return {**dati,
            "settimane": [s for s in dati["settimane"] if dal - timedelta(days=7) <= s.inizio < riferimento],
            "importati": [r for r in dati["importati"] if dal.year <= r["anno"] <= riferimento.year]}


def prossime(conn: sqlite3.Connection, oggi: date, mesi: int) -> list[dict]:
    """Le festività attive in [oggi, oggi + mesi), con i dipendenti attivi in ordine di precedenza a lavorarle."""
    festivita = db_festivita.festivita_attive(conn)
    fine = aggiungi_mesi(oggi, mesi) - timedelta(days=1)
    voci = occorrenze(festivita, oggi, fine)
    if not voci:
        return []
    persone = {p["id"]: p for p in db.lista_persone(conn) if p["tipo"] == "dipendente" and p["attivo"]}
    nomi = {pid: p["nome"] for pid, p in persone.items()}
    riferimenti = sorted({lunedi(d) for d, _ in voci})
    dati = _solo_turni_festivi(festivita, dati_festivi.dati_conti(conn, inizio_periodo(riferimenti[0]),
                                                                  riferimenti[-1]))
    dati_per_riferimento = {r: _nel_periodo(dati, r) for r in riferimenti}
    conti = {r: conta_festivita(festivita, r, **dati_per_riferimento[r]) for r in riferimenti}
    festivita_per_fascia = {
        "giorno": {f["id"]: {**f, "conta_notte": False, "conta_notte_prima": False}
                   for f in festivita if f["conta_giorno"]},
        "notte": {f["id"]: {**f, "conta_giorno": False}
                  for f in festivita if f["conta_notte"] or f["conta_notte_prima"]},
    }
    # Stessi dati e stessa esposizione dell'aggregato; solo le fasce del conto
    # cambiano. Anche una settimana senza turni della singola fascia resta nei dati.
    conti_per_fascia = {
        fascia: {r: conta_festivita(gruppo.values(), r, **dati_per_riferimento[r]) for r in riferimenti}
        for fascia, gruppo in festivita_per_fascia.items() if gruppo
    }
    disponibili = db_festivi_disponibili.per_giorno(conn, festivita, oggi, fine)
    assente = _assenze(conn, oggi - timedelta(days=1), fine)

    def elenco_ordine(f: dict, d: date, conto: dict) -> list[dict]:
        ordine = []
        for pid, debito in ordine_rotazione(conto, persone, f["peso"], d.year, nomi):
            c = conto.get(pid, ContoFestivita())
            ordine.append({"persona_id": pid, "nome": nomi[pid], "qualifica": persone[pid]["qualifica"],
                           "volte_5_anni": c.turni, "ultimo_anno": c.ultimo_anno, "debito": round(debito, 2),
                           "disponibile": disponibili.get(d, {}).get(pid), "assente": assente(pid, f, d)})
        return ordine

    out = []
    for d, f in voci:
        riferimento = lunedi(d)
        ordine = elenco_ordine(f, d, conti[riferimento].get(f["id"], {}))
        ordini_per_fascia = {
            fascia: elenco_ordine(gruppo[f["id"]], d, conti_per_fascia[fascia][riferimento].get(f["id"], {}))
            for fascia, gruppo in festivita_per_fascia.items() if f["id"] in gruppo
        }
        out.append({"data": d.isoformat(), "festivita_id": f["id"], "nome": f["nome"], "peso": f["peso"],
                    "conta_giorno": f["conta_giorno"], "conta_notte": f["conta_notte"],
                    "conta_notte_prima": f["conta_notte_prima"], "ordine": ordine,
                    "ordini_per_fascia": ordini_per_fascia})
    return out


def _anni(conn, prima: date | None, oggi: date) -> list[int]:
    """Anni con dati: quelli importati e quelli del programma (dalla prima settimana generata a oggi)."""
    anni = {r["anno"] for r in db_storico_festivi.riepilogo_anni(conn) if r["turni"]}
    if prima is not None:
        anni |= set(range(prima.year, max(prima.year, oggi.year) + 1))
    return sorted(anni, reverse=True)


def lavorate_anno(conn: sqlite3.Connection, anno: int, oggi: date) -> dict:
    """Chi ha lavorato ogni festività dell'anno: dallo storico importato prima della prima settimana generata, dal
    programma dopo (solo dipendenti, come nella rotazione). Festività: le attive che cadono nell'anno più quelle con
    dati."""
    prima = db_storico_festivi.prima_generata(conn)
    limite = limite_storico(prima, oggi)
    tutte = db_festivita.lista_festivita(conn)
    per_id = {f["id"]: f for f in tutte}
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    lavorate: dict[tuple[int, date], dict[str, set[int]]] = {}

    def segna(fid: int, d: date, fascia: str, pid: int) -> None:
        lavorate.setdefault((fid, d), {"giorno": set(), "notte": set()})[fascia].add(pid)

    for r in db_storico_festivi.turni_anno(conn, anno):
        d = data_nell_anno(per_id[r["festivita_id"]], anno)
        p = persone.get(r["persona_id"])
        if d is not None and d < limite and p is not None and p["tipo"] == "dipendente":
            segna(r["festivita_id"], d, r["fascia"], r["persona_id"])
    if prima is not None:
        gruppo = [f for f in tutte if f["attiva"] or f["stata_attiva"]]
        dal, al = date(anno, 1, 1) - timedelta(days=1), date(anno, 12, 31)
        mappa = turni_festivi(gruppo, dal, al)
        for _, a in db.assegnazioni_periodo(conn, max(dal, prima - timedelta(days=1)), al):
            fid = mappa.get((a.data, a.fascia))
            p = persone.get(a.persona_id)
            if fid is None or p is None or p["tipo"] != "dipendente":
                continue
            d = occorrenza(per_id[fid], a.data, a.fascia)
            if d.year == anno and d >= limite:
                segna(fid, d, a.fascia, a.persona_id)
    for d, f in occorrenze([f for f in tutte if f["attiva"]], date(anno, 1, 1), date(anno, 12, 31)):
        lavorate.setdefault((f["id"], d), {"giorno": set(), "notte": set()})

    def elenco(ids):
        return sorted(({"persona_id": pid, "nome": persone[pid]["nome"] if pid in persone else f"#{pid}"}
                       for pid in ids), key=lambda x: (x["nome"].casefold(), x["persona_id"]))
    voci = [{"festivita_id": fid, "nome": per_id[fid]["nome"], "data": d.isoformat(), "attiva": per_id[fid]["attiva"],
             "peso": per_id[fid]["peso"], "fonte": "importato" if d < limite else "programma",
             "giorno": elenco(chi["giorno"]), "notte": elenco(chi["notte"])}
            for (fid, d), chi in sorted(lavorate.items(), key=lambda x: (x[0][1], x[0][0]))]
    return {"anno": anno, "limite": limite.isoformat(), "anni": _anni(conn, prima, oggi), "festivita": voci}
