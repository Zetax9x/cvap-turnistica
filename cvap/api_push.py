"""API delle notifiche push: stato, iscrizione del dispositivo, notifica di prova (dietro la password del sito)."""
import logging
from typing import Annotated

from fastapi import APIRouter, Response
from pydantic import BaseModel, StringConstraints

from . import db, push
from .api_comune import errore

Testo = Annotated[str, StringConstraints(min_length=1, max_length=600)]


class ChiaviIn(BaseModel):
    p256dh: Testo
    auth: Testo


class IscrizioneIn(BaseModel):
    endpoint: Annotated[str, StringConstraints(min_length=10, max_length=1000, pattern=r"^https://")]
    keys: ChiaviIn


def crea_router(db_path: str) -> APIRouter:
    router = APIRouter()

    def con_db(funzione):
        conn = db.connetti(db_path)
        try:
            return funzione(conn)
        finally:
            conn.close()

    @router.get("/api/push")
    def stato():
        return con_db(lambda c: {"chiave": push.chiave_pubblica(c), "iscritto": push.iscrizione(c) is not None})

    @router.put("/api/push/iscrizione")
    def iscrivi(corpo: IscrizioneIn):
        con_db(lambda c: push.salva_iscrizione(c, corpo.endpoint, corpo.keys.p256dh, corpo.keys.auth))
        return {"iscritto": True}

    @router.delete("/api/push/iscrizione", status_code=204)
    def togli():
        con_db(push.togli_iscrizione)
        return Response(status_code=204)

    @router.post("/api/push/prova")
    def prova():
        dati = con_db(lambda c: push.prepara(c, "Turni CVAP", "Le notifiche funzionano.", "/app/#/altro"))
        if dati is None:
            raise errore("Nessun dispositivo iscritto: attiva prima le notifiche")
        try:
            push._spedisci(*dati)
        except push.IscrizioneScaduta:
            con_db(push.togli_iscrizione)
            raise errore("L'iscrizione è scaduta: riattiva le notifiche da questo telefono")
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("Notifica di prova non inviata")
            raise errore("Invio non riuscito: il servizio delle notifiche non risponde o ha rifiutato l'invio")
        return {"inviata": True}

    return router
