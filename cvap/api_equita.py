"""API del quadro dell'equità: GET /api/statistiche/equita?dal&al (docs/API.md)."""
import sqlite3
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends

from . import db
from .api_comune import DATA_MAX, DATA_MIN, DataValida, errore
from .calendario import lunedi
from .equita import equita
from .storico import SettimanaPassata, solo_generate


def postazioni_vietate(conn) -> dict[int, set[str]]:
    """Per dipendente, le postazioni vietate per intero (divieto senza tipo di turno)."""
    out: dict[int, set[str]] = {}
    for d in db.lista_divieti(conn):
        if d["postazione"] is not None and d["turno"] is None:
            out.setdefault(d["persona_id"], set()).add(d["postazione"])
    return out


def crea_router(connessione: Callable, settimana_passata: Callable[..., SettimanaPassata]) -> APIRouter:
    """`connessione`: la dipendenza che apre il database; `settimana_passata(conn, riga)`: la settimana come la
    vedono storico e statistiche (app._settimana_passata, passata da app.py per evitare un import circolare)."""
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    @router.get("/api/statistiche/equita")
    def quadro_equita(conn: Conn, dal: DataValida | None = None, al: DataValida | None = None):
        dal, al = dal or DATA_MIN, al or DATA_MAX
        if dal > al:
            raise errore("La data di inizio è dopo quella di fine")
        # le settimane che si sovrappongono al periodo; contano solo quelle con turni generati (come le statistiche)
        righe = [r for r in db.lista_settimane(conn) if lunedi(dal) <= date.fromisoformat(r["inizio"]) <= al]
        settimane = [(date.fromisoformat(r["inizio"]), settimana_passata(conn, r)) for r in righe]
        quadro = equita(settimane, db.lista_persone(conn), postazioni_vietate(conn))
        contate = [inizio.isoformat() for inizio, s in settimane if solo_generate([s])]
        return {"settimane": contate, "rotazioni": [{"chiave": k, **v} for k, v in quadro.items()]}

    return router
