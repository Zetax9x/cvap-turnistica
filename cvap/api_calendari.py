"""Calendari .ics dei dipendenti (cvap/calendario_ics.py).

- `GET /turni/<nome>-<codice>.ics`: il calendario, senza password (i programmi di calendario non la possono
  inserire): lo protegge il codice segreto. Conta solo il codice, il nome serve a riconoscere il link.
- `GET /api/calendari/{id}` e `POST /api/calendari/{id}/rigenera`: il link della persona, o uno nuovo che
  sostituisce il vecchio; dietro la password del sito come le altre API.
"""
import re
import sqlite3
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from . import calendario_ics, db, db_calendari
from .api_comune import IdPath, errore

_FILE = re.compile(r"^(?:[a-z0-9-]*-)?([0-9a-f]{20})\.ics$")


def crea_router(connessione: Callable) -> APIRouter:
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    def dipendente(conn, persona_id: int) -> dict:
        p = db.get_persona(conn, persona_id)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        if p["tipo"] != "dipendente":
            raise errore("Il calendario dei turni è solo per i dipendenti")
        return p

    def voce(p: dict, codice: str) -> dict:
        return {"persona_id": p["id"], "nome": p["nome"],
                "percorso": f"/turni/{calendario_ics.slug(p['nome'])}-{codice}.ics"}

    @router.get("/api/calendari/{persona_id}")
    def link(persona_id: IdPath, conn: Conn):
        p = dipendente(conn, persona_id)
        return voce(p, db_calendari.codice(conn, p["id"]))

    @router.post("/api/calendari/{persona_id}/rigenera")
    def rigenera(persona_id: IdPath, conn: Conn):
        p = dipendente(conn, persona_id)
        return voce(p, db_calendari.rigenera(conn, p["id"]))

    @router.api_route("/turni/{file}", methods=["GET", "HEAD"], include_in_schema=False)
    def calendario(file: str, conn: Conn):
        trovato = _FILE.match(file)
        pid = db_calendari.persona_del_codice(conn, trovato.group(1)) if trovato else None
        p = db.get_persona(conn, pid) if pid else None
        if p is None or p["tipo"] != "dipendente" or not p["attivo"]:
            raise HTTPException(404, "Calendario non trovato")
        eventi = calendario_ics.eventi_persona(conn, p["id"], date.today())
        testo = calendario_ics.componi(p["nome"], eventi, datetime.now(timezone.utc))
        return Response(testo, media_type="text/calendar; charset=utf-8", headers={
            "Content-Disposition": f'inline; filename="turni-{calendario_ics.slug(p["nome"])}.ics"',
            "Cache-Control": "private, max-age=300",
            "X-Robots-Tag": "noindex",
        })

    return router
