"""Altri confronti di equità, oltre alle rotazioni di equita.py: weekend interi liberi, sequenze pesanti, con chi si lavora.

Si calcolano sulle stesse settimane del quadro dell'equità (confermate, dalla prima all'ultima con turni generati) e
per gli stessi dipendenti (gli attivi e i disattivati con turni nel periodo). Nessuno di questi conti entra nel
generatore: servono solo a vedere come sono andate le cose.
"""
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import date, timedelta

from .equita import _differenza, _r, _scelti
from .storico import SettimanaPassata, solo_generate

FREQUENTI = 3  # colleghi più frequenti mostrati per persona


def _contate(settimane: Sequence[tuple[date, SettimanaPassata]]) -> list[tuple[date, SettimanaPassata]]:
    """Come equita(): dalla prima all'ultima settimana generata, comprese quelle fatte a mano in mezzo."""
    ordinate = sorted(settimane, key=lambda x: x[0])
    generate = [i for i, (_, s) in enumerate(ordinate) if solo_generate([s])]
    return ordinate[generate[0]:generate[-1] + 1] if generate else []


def weekend_liberi(contate: list[tuple[date, SettimanaPassata]], scelti: list[dict]) -> dict:
    """Weekend senza nessun turno il sabato e la domenica. Contano le settimane in cui il dipendente c'era e non era
    in ferie o malattia tutta la settimana; la sua parte è la media del gruppo per le sue settimane."""
    ids = {p["id"] for p in scelti}
    settimane, liberi = Counter(), Counter()
    for _, s in contate:
        lavora_nel_weekend = {a.persona_id for a in s.assegnazioni if a.data.weekday() >= 5}
        for pid in s.dipendenti:
            if pid not in ids or s.giorni_ferie.get(pid, 0) >= 7:
                continue
            settimane[pid] += 1
            if pid not in lavora_nel_weekend:
                liberi[pid] += 1
    tasso = sum(liberi.values()) / sum(settimane.values()) if settimane else 0.0
    valori = {pid: (liberi[pid], tasso * settimane[pid]) for pid in settimane}
    dipendenti = [{"persona_id": p["id"], "nome": p["nome"], "attivo": bool(p["attivo"]),
                   "settimane": settimane[p["id"]], "liberi": liberi[p["id"]], "quota": _r(valori[p["id"]][1]),
                   "scarto": _r(valori[p["id"]][0] - valori[p["id"]][1])}
                  for p in scelti if p["id"] in valori]
    dipendenti.sort(key=lambda d: (-d["scarto"], d["nome"].lower()))
    return {"differenza": _differenza(valori), "media": _r(tasso * 100), "dipendenti": dipendenti}


def sequenze(contate: list[tuple[date, SettimanaPassata]], scelti: list[dict]) -> list[dict]:
    """Per dipendente: notti di fila (coppie di notti in giorni consecutivi), tre turni di fila nella stessa fascia
    (le terne di giorni consecutivi, come la penalità del generatore) e il massimo di giorni di fila con un turno."""
    giorni = defaultdict(lambda: defaultdict(set))  # pid -> fascia -> date
    lavorati = defaultdict(set)                      # pid -> date con almeno un turno
    ids = {p["id"] for p in scelti}
    for _, s in contate:
        for a in s.assegnazioni:
            if a.persona_id in ids:
                giorni[a.persona_id][a.fascia].add(a.data)
                lavorati[a.persona_id].add(a.data)
    uno = timedelta(days=1)
    out = []
    for p in scelti:
        pid = p["id"]
        notti = giorni[pid]["notte"]
        notti_di_fila = sum(1 for d in notti if d + uno in notti)
        tre_di_fila = sum(1 for fascia in ("giorno", "notte") for d in giorni[pid][fascia]
                          if d + uno in giorni[pid][fascia] and d + 2 * uno in giorni[pid][fascia])
        massimo, corrente, precedente = 0, 0, None
        for d in sorted(lavorati[pid]):
            corrente = corrente + 1 if precedente is not None and d - precedente == uno else 1
            massimo, precedente = max(massimo, corrente), d
        out.append({"persona_id": pid, "nome": p["nome"], "attivo": bool(p["attivo"]), "notti_di_fila": notti_di_fila,
                    "tre_di_fila": tre_di_fila, "giorni_di_fila_max": massimo})
    out.sort(key=lambda d: (-(d["notti_di_fila"] + d["tre_di_fila"]), -d["giorni_di_fila_max"], d["nome"].lower()))
    return out


def colleghi(contate: list[tuple[date, SettimanaPassata]], scelti: list[dict], persone: Sequence[dict]) -> list[dict]:
    """Con chi lavora ognuno: stesso giorno, postazione e fascia (dipendenti e volontari). Per dipendente quanti turni
    in compagnia, quanti colleghi diversi e i più frequenti."""
    nomi = {p["id"]: p["nome"] for p in persone}
    insieme = defaultdict(Counter)  # pid -> collega -> turni insieme
    turni = Counter()
    ids = {p["id"] for p in scelti}
    for _, s in contate:
        gruppi = defaultdict(set)
        for a in s.assegnazioni:
            gruppi[(a.data, a.postazione, a.fascia)].add(a.persona_id)
        for chi in gruppi.values():
            for pid in chi & ids:
                altri = chi - {pid}
                if altri:
                    turni[pid] += 1
                    insieme[pid].update(altri)
    out = []
    for p in scelti:
        conta = insieme[p["id"]]
        frequenti = sorted(conta.items(), key=lambda x: (-x[1], nomi.get(x[0], "").lower()))[:FREQUENTI]
        out.append({"persona_id": p["id"], "nome": p["nome"], "attivo": bool(p["attivo"]), "turni": turni[p["id"]],
                    "colleghi_diversi": len(conta),
                    "frequenti": [{"persona_id": c, "nome": nomi.get(c, f"n. {c}"), "turni": n,
                                   "percentuale": round(n / turni[p["id"]] * 100) if turni[p["id"]] else 0}
                                  for c, n in frequenti]})
    out.sort(key=lambda d: d["nome"].lower())
    return out


def confronti(settimane: Sequence[tuple[date, SettimanaPassata]], persone: Sequence[dict]) -> dict:
    """{settimane, weekend_liberi, sequenze, colleghi} sulle settimane del quadro dell'equità."""
    contate = _contate(settimane)
    scelti = _scelti(persone, [s for _, s in contate])
    return {
        "settimane": [inizio.isoformat() for inizio, s in contate if solo_generate([s])],
        "weekend_liberi": weekend_liberi(contate, scelti),
        "sequenze": sequenze(contate, scelti),
        "colleghi": colleghi(contate, scelti, persone),
    }
