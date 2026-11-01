"""Dati della rotazione delle festività letti dal database (calcolo in cvap/rotazione_festivi.py).

Usati dalla generazione (POST /api/settimane/{data}/genera), dalle statistiche e dal riepilogo per dipendente.
"""
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from . import db, db_festivi_disponibili, db_festivita, db_storico_festivi
from .calendario import lunedi
from .festivita import turni_festivi
from .modello import Assegnazione
from .rotazione_festivi import (ContoFestivita, FestiviSettimana, SettimanaProgramma, conta_festivita,
                                festivi_settimana, inizio_periodo, turni_disponibili)
from .storico_festivi import limite_storico


NON_PIU_NEL_CALENDARIO = "non più nel calendario"


def _settimane_programma(conn, prima: date | None, dal: date, al: date) -> list[SettimanaProgramma]:
    """Le settimane dalla prima generata in poi che toccano [dal, al) e hanno almeno un turno.

    Dipendenti della settimana: quelli salvati nella riga di `settimane`; per le settimane compilate a mano senza
    riga, i dipendenti che hanno turni quella settimana. Le settimane senza turni non danno esposizione."""
    if prima is None:
        return []
    inizio = max(prima, lunedi(dal))
    turni = defaultdict(list)
    for _, a in db.assegnazioni_periodo(conn, inizio, al - timedelta(days=1)):
        turni[lunedi(a.data)].append(a)
    if not turni:
        return []
    righe = {date.fromisoformat(r["inizio"]): r for r in db.lista_settimane(conn, prima_di=al)}
    dipendenti = {p["id"] for p in db.lista_persone(conn) if p["tipo"] == "dipendente"}
    out = []
    for lun in sorted(turni):
        riga = righe.get(lun)
        chi = set(riga["dipendenti"]) if riga else {a.persona_id for a in turni[lun] if a.persona_id in dipendenti}
        out.append(SettimanaProgramma(lun, frozenset(chi), tuple(turni[lun])))
    return out


def conti_festivita(conn: sqlite3.Connection, riferimento: date,
                    festivita: list[dict] | None = None) -> dict[int, dict[int, ContoFestivita]]:
    """Conti delle festività (predefinito: le attive) negli ultimi anni prima di `riferimento` (storico
    importato + programma)."""
    festivita = db_festivita.festivita_attive(conn) if festivita is None else festivita
    if not festivita:
        return {}
    return conta_festivita(festivita, riferimento, **dati_conti(conn, inizio_periodo(riferimento), riferimento))


def dati_conti(conn: sqlite3.Connection, dal: date, al: date) -> dict:
    """Gli argomenti di `conta_festivita` letti dal database, validi per ogni riferimento con periodo dentro
    [dal, al): `conta_festivita` considera da sé solo le festività del suo periodo. Così l'ordine delle prossime
    festività legge il database una volta sola e fa lo stesso calcolo del generatore."""
    attivi = {p["id"] for p in db.lista_persone(conn) if p["tipo"] == "dipendente" and p["attivo"]}
    prima = db_storico_festivi.prima_generata(conn)
    settimane = _settimane_programma(conn, prima, dal, al)
    malattia = db.giorni_malattia(conn, dal - timedelta(days=1), al) if settimane else set()
    return {"limite": limite_storico(prima, date.today()), "importati": db_storico_festivi.tutti_i_turni(conn),
            "servizio": db_storico_festivi.servizio_per_anno(conn), "dipendenti_attivi": attivi,
            "settimane": settimane, "malattia": malattia}


def festivi_per_generazione(conn: sqlite3.Connection, giorni: list[date],
                            contesto: Iterable[Assegnazione] = ()) -> FestiviSettimana:
    """Le festività della settimana da generare, con lo storico di ognuna fino al lunedì della settimana.

    `contesto`: turni dei giorni prima (la notte della sera prima di un lunedì festivo conta come già fissata)."""
    festivita = db_festivita.festivita_attive(conn)
    if not turni_festivi(festivita, giorni[0], giorni[-1]):
        return FestiviSettimana()
    dipendenti = {p["id"] for p in db.lista_persone(conn) if p["tipo"] == "dipendente"}
    # la notte della domenica può essere la notte della sera prima di un lunedì festivo: un giorno in più
    disponibili = db_festivi_disponibili.per_giorno(conn, festivita, giorni[0], giorni[-1] + timedelta(days=1))
    return festivi_settimana(festivita, giorni, conti_festivita(conn, giorni[0], festivita), contesto, dipendenti,
                             disponibili)


def disponibili_settimana(conn: sqlite3.Connection, giorni: list[date]) -> list[dict]:
    """Per la griglia della settimana: [{data, fascia, persona_id}] dei turni festivi che qualcuno vuole lavorare."""
    festivita = db_festivita.festivita_attive(conn)
    disponibili = db_festivi_disponibili.per_giorno(conn, festivita, giorni[0], giorni[-1] + timedelta(days=1))
    if not festivita or not disponibili:
        return []
    return [{"data": g.isoformat(), "fascia": fascia, "persona_id": pid}
            for (g, fascia), chi in turni_disponibili(festivita, giorni[0], giorni[-1], disponibili).items()
            for pid in sorted(chi)]


def riferimento_statistiche(conn) -> date:
    """Fine del periodo delle statistiche: dopo l'ultima settimana salvata o l'ultimo turno, almeno domani."""
    riferimento = date.today() + timedelta(days=1)
    settimane = db.lista_settimane(conn)
    if settimane:
        riferimento = max(riferimento, date.fromisoformat(settimane[-1]["inizio"]) + timedelta(days=7))
    r = conn.execute("SELECT MAX(data) AS ultima FROM assegnazioni").fetchone()
    if r and r["ultima"]:
        riferimento = max(riferimento, date.fromisoformat(r["ultima"]) + timedelta(days=1))
    return riferimento


def _conti_statistiche(conn) -> list[tuple[dict, dict[int, ContoFestivita]]]:
    """(festività, conti per persona) per le attive e per le non più attive, ognuna calcolata a parte."""
    tutte = db_festivita.lista_festivita(conn)
    riferimento = riferimento_statistiche(conn)
    nello_storico = {r["festivita_id"] for r in db_storico_festivi.tutti_i_turni(conn)}
    # non attive: solo quelle che lo sono state o che sono nello storico importato (non le predefinite mai usate)
    non_piu = [f for f in tutte if not f["attiva"] and (f["stata_attiva"] or f["id"] in nello_storico)]
    out = []
    for gruppo in ([f for f in tutte if f["attiva"]], non_piu):
        conti = conti_festivita(conn, riferimento, gruppo)
        out += [(f, conti.get(f["id"], {})) for f in sorted(gruppo, key=lambda f: f["id"])]
    return out


def festivi_statistiche(conn: sqlite3.Connection, dipendenti: Iterable[int]) -> tuple[dict[int, dict], list[dict]]:
    """Negli ultimi anni, fino alla fine dell'ultima settimana salvata (o a domani):

    - dipendente -> {turni, per_festivita: [{festivita, attiva, turni, ultimo_anno}]}: tutte le festività attive,
      più quelle non più nel calendario in cui ha lavorato (non contano più per il generatore, ma restano nel totale);
    - turni festivi di chi non è tra `dipendenti` (es. ex dipendenti presenti solo nello storico importato):
      [{festivita, attiva, turni}]."""
    dipendenti = list(dipendenti)
    in_tabella = set(dipendenti)
    conti = _conti_statistiche(conn)
    out = {}
    for pid in dipendenti:
        voci = [{"festivita": f["nome"], "attiva": f["attiva"], "turni": c.turni, "ultimo_anno": c.ultimo_anno}
                for f, per_persona in conti for c in [per_persona.get(pid, ContoFestivita())]
                if f["attiva"] or c.turni]
        out[pid] = {"turni": sum(v["turni"] for v in voci), "per_festivita": voci}
    fuori = [{"festivita": f["nome"], "attiva": f["attiva"],
              "turni": sum(c.turni for pid, c in per_persona.items() if pid not in in_tabella)}
             for f, per_persona in conti]
    return out, [v for v in fuori if v["turni"]]


def nomi_turni_festivi(conn: sqlite3.Connection, dal: date, al: date) -> dict[tuple[date, str], str]:
    """(giorno, fascia) -> nome della festività per i turni festivi in [dal, al]: prima le attive, poi le non più
    nel calendario (con l'etichetta)."""
    tutte = db_festivita.lista_festivita(conn)
    out: dict[tuple[date, str], str] = {}
    for attiva in (True, False):
        gruppo = [f for f in tutte if f["attiva"] == attiva and (attiva or f["stata_attiva"])]
        nomi = {f["id"]: f["nome"] if attiva else f"{f['nome']} ({NON_PIU_NEL_CALENDARIO})" for f in gruppo}
        for turno, fid in turni_festivi(gruppo, dal, al).items():
            out.setdefault(turno, nomi[fid])
    return out
