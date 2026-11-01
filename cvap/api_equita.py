"""API del quadro dell'equità: GET /api/statistiche/equita?dal&al (docs/API.md)."""
import sqlite3
from collections.abc import Callable
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends

from . import db, db_festivita
from .api_comune import DATA_MAX, DATA_MIN, DataValida, errore
from .calendario import lunedi
from .dati_festivi import _riferimento_statistiche, conti_festivita
from .equita import Rotazione, equita, rotazione_festivita
from .storico import SettimanaPassata, solo_generate


def postazioni_vietate(conn) -> dict[int, set[str]]:
    """Per dipendente, le postazioni vietate per intero (divieto senza tipo di turno)."""
    out: dict[int, set[str]] = {}
    for d in db.lista_divieti(conn):
        if d["postazione"] is not None and d["turno"] is None:
            out.setdefault(d["persona_id"], set()).add(d["postazione"])
    return out


def rotazioni_festivita(conn, al: date | None) -> list[Rotazione]:
    """Una rotazione per ogni festività attiva, con lo storico degli ultimi 5 anni fino alla fine del periodo.

    Fine del periodo: il giorno dopo `al`, ma non oltre quella delle statistiche (dopo l'ultima settimana salvata o
    l'ultimo turno, almeno domani), così una data lontana non sposta la finestra oltre i dati; senza `al`, quella
    delle statistiche. `dal` non si applica: una festività cade una volta l'anno."""
    festivita = db_festivita.festivita_attive(conn)
    if not festivita:
        return []
    riferimento = _riferimento_statistiche(conn)
    if al is not None:
        riferimento = min(riferimento, al + timedelta(days=1))
    conti = conti_festivita(conn, riferimento, festivita)
    return [rotazione_festivita(f, conti.get(f["id"], {})) for f in festivita]


def crea_router(connessione: Callable, settimana_passata: Callable[..., SettimanaPassata]) -> APIRouter:
    """`connessione`: la dipendenza che apre il database; `settimana_passata(conn, riga)`: la settimana come la
    vedono storico e statistiche (app._settimana_passata, passata da app.py per evitare un import circolare)."""
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    @router.get("/api/statistiche/equita")
    def quadro_equita(conn: Conn, dal: DataValida | None = None, al: DataValida | None = None):
        al_richiesto = al  # None senza data: la fine dei festivi è quella delle statistiche
        dal, al = dal or DATA_MIN, al or DATA_MAX
        if dal > al:
            raise errore("La data di inizio è dopo quella di fine")
        # le settimane che si sovrappongono al periodo; contano solo quelle con turni generati (come le statistiche)
        righe = [r for r in db.lista_settimane(conn) if lunedi(dal) <= date.fromisoformat(r["inizio"]) <= al]
        settimane = [(date.fromisoformat(r["inizio"]), settimana_passata(conn, r)) for r in righe]
        quadro = equita(settimane, db.lista_persone(conn), postazioni_vietate(conn),
                        extra=rotazioni_festivita(conn, al_richiesto))
        contate = [inizio.isoformat() for inizio, s in settimane if solo_generate([s])]
        return {"settimane": contate, "rotazioni": [{"chiave": k, **v} for k, v in quadro.items()]}

    return router
