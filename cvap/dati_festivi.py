"""Dati della rotazione delle festività letti dal database (calcolo in cvap/rotazione_festivi.py).

Usati dalla generazione (POST /api/settimane/{data}/genera), dalle statistiche e dal riepilogo per dipendente.
"""
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from . import db, db_festivita, db_storico_festivi
from .calendario import lunedi
from .festivita import turni_festivi
from .rotazione_festivi import (ContoFestivita, FestiviSettimana, SettimanaProgramma, conta_festivita,
                                festivi_settimana, inizio_periodo)
from .storico_festivi import limite_storico


def _settimane_programma(conn, prima: date | None, dal: date, al: date) -> list[SettimanaProgramma]:
    """Le settimane salvate dalla prima generata in poi che toccano [dal, al)."""
    if prima is None:
        return []
    inizio = max(prima, lunedi(dal))
    righe = [r for r in db.lista_settimane(conn, prima_di=al) if date.fromisoformat(r["inizio"]) >= inizio]
    if not righe:
        return []
    turni = defaultdict(list)
    for _, a in db.assegnazioni_periodo(conn, inizio, al - timedelta(days=1)):
        turni[lunedi(a.data)].append(a)
    return [SettimanaProgramma(date.fromisoformat(r["inizio"]), frozenset(r["dipendenti"]),
                               tuple(turni.get(date.fromisoformat(r["inizio"]), ()))) for r in righe]


def conti_festivita(conn: sqlite3.Connection, riferimento: date,
                    festivita: list[dict] | None = None) -> dict[int, dict[int, ContoFestivita]]:
    """Conti delle festività attive negli ultimi anni prima di `riferimento` (storico importato + programma)."""
    festivita = db_festivita.festivita_attive(conn) if festivita is None else festivita
    if not festivita:
        return {}
    attivi = {p["id"] for p in db.lista_persone(conn) if p["tipo"] == "dipendente" and p["attivo"]}
    prima = db_storico_festivi.prima_generata(conn)
    dal = inizio_periodo(riferimento)
    settimane = _settimane_programma(conn, prima, dal, riferimento)
    malattia = db.giorni_malattia(conn, dal - timedelta(days=1), riferimento) if settimane else set()
    return conta_festivita(festivita, riferimento, limite=limite_storico(prima, date.today()),
                           importati=db_storico_festivi.tutti_i_turni(conn),
                           servizio=db_storico_festivi.servizio_per_anno(conn), dipendenti_attivi=attivi,
                           settimane=settimane, malattia=malattia)


def festivi_per_generazione(conn: sqlite3.Connection, giorni: list[date]) -> FestiviSettimana:
    """Le festività della settimana da generare, con lo storico di ognuna fino al lunedì della settimana."""
    festivita = db_festivita.festivita_attive(conn)
    if not turni_festivi(festivita, giorni[0], giorni[-1]):
        return FestiviSettimana()
    return festivi_settimana(festivita, giorni, conti_festivita(conn, giorni[0], festivita))


def festivi_statistiche(conn: sqlite3.Connection, dipendenti: Iterable[int]) -> dict[int, dict]:
    """Dipendente -> {turni, per_festivita: [{festivita, turni, ultimo_anno}]} negli ultimi anni, fino alla fine
    dell'ultima settimana salvata (o a oggi), per ogni festività attiva."""
    festivita = db_festivita.festivita_attive(conn)
    settimane = db.lista_settimane(conn)
    riferimento = date.today() + timedelta(days=1)
    if settimane:
        riferimento = max(riferimento, date.fromisoformat(settimane[-1]["inizio"]) + timedelta(days=7))
    conti = conti_festivita(conn, riferimento, festivita)
    out = {}
    for pid in dipendenti:
        voci = [{"festivita": f["nome"], "turni": c.turni, "ultimo_anno": c.ultimo_anno}
                for f in festivita for c in [conti[f["id"]].get(pid, ContoFestivita())]]
        out[pid] = {"turni": sum(v["turni"] for v in voci), "per_festivita": voci}
    return out


def nomi_turni_festivi(conn: sqlite3.Connection, dal: date, al: date) -> dict[tuple[date, str], str]:
    """(giorno, fascia) -> nome della festività attiva, per i turni festivi in [dal, al]."""
    festivita = db_festivita.festivita_attive(conn)
    nomi = {f["id"]: f["nome"] for f in festivita}
    return {turno: nomi[fid] for turno, fid in turni_festivi(festivita, dal, al).items()}
