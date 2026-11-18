"""API della scheda ore mensile.

- `/api/schede-ore/…`: per il dipendente, senza la password del sito. Si entra con nome e codice personale
  (`POST /accesso`) e il server dà un cookie firmato `cvap_scheda` che contiene la persona: ogni altra chiamata
  usa solo quella persona, quindi nessuno può leggere o modificare la scheda di un altro.
- `/api/schede-ore-gestione/…`: per la master (codici personali, elenco delle schede, riapertura).
"""
import hashlib
import hmac
import math
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi import Path as PathParam
from pydantic import BaseModel, Field

from . import db, db_schede_ore, registro, servizio_schede_ore
from .api_comune import Id, IdPath
from .scheda_ore import MAX_NOTE_FINALI, mesi_apribili
from .xlsx_scheda import compila_scheda, nome_file

COOKIE = "cvap_scheda"
PERCORSO_COOKIE = "/api/schede-ore"
DURATA_COOKIE_S = 2 * 60 * 60
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NON_VALIDO = "Nome o codice non corretti"
ACCESSO_RICHIESTO = "Accesso richiesto: apri la tua scheda con nome e codice"
MESE_VALIDO = r"^\d{4}-(0[1-9]|1[0-2])$"

Mese = Annotated[str, PathParam(pattern=MESE_VALIDO)]
Giorno = Annotated[int, PathParam(ge=1, le=31)]


# --- cookie di sessione -------------------------------------------------------------------

def chiave_scheda(segreto: str) -> bytes:
    """La chiave che firma i cookie della scheda ore, derivata dal segreto di sessione del programma."""
    return hmac.new(segreto.encode(), b"scheda-ore", hashlib.sha256).digest()


def chiave_persona(chiave: bytes, impronta: str) -> bytes:
    """La chiave dei cookie di una persona: dipende dal suo codice attuale (`db_schede_ore.impronta_codice`), quindi
    azzerare o cambiare il codice chiude subito le sessioni aperte."""
    return hmac.new(chiave, impronta.encode(), hashlib.sha256).digest()


def _firma(chiave: bytes, corpo: str) -> str:
    return hmac.new(chiave, corpo.encode(), hashlib.sha256).hexdigest()


def crea_cookie(chiave: bytes, persona_id: int, adesso: float) -> str:
    corpo = f"{persona_id}.{int(adesso) + DURATA_COOKIE_S}"
    return f"{corpo}.{_firma(chiave, corpo)}"


def persona_dal_cookie(chiave: bytes, valore: str | None, adesso: float) -> int | None:
    """La persona del cookie, o None se è assente, manomesso o scaduto."""
    parti = (valore or "").split(".")
    if len(parti) != 3 or not (parti[0].isdigit() and parti[1].isdigit()) or not parti[2].isascii():
        return None
    if not hmac.compare_digest(parti[2], _firma(chiave, f"{parti[0]}.{parti[1]}")):
        return None
    return int(parti[0]) if adesso <= int(parti[1]) else None


# --- corpi delle richieste ----------------------------------------------------------------

class AccessoIn(BaseModel):
    persona_id: Id
    codice: Annotated[str, Field(max_length=100)]


class GiornoIn(BaseModel):
    ferie: int = 0
    colonne: dict[str, list | None] = {}
    note: str = ""
    disponibilita: dict | None = None


class NoteIn(BaseModel):
    note: Annotated[str, Field(max_length=MAX_NOTE_FINALI)]


class CodiceIn(BaseModel):
    codice: Annotated[str, Field(min_length=db_schede_ore.CODICE_MIN, max_length=100)]


def _dipendente_attivo(conn: sqlite3.Connection, persona_id: int | None) -> dict | None:
    p = db.get_persona(conn, persona_id) if persona_id else None
    return p if p and p["tipo"] == "dipendente" and p["attivo"] else None


# --- router del dipendente ----------------------------------------------------------------

def crea_router(connessione: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/schede-ore")
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]
    chiavi: dict[str, bytes] = {}

    def chiave_di(conn: sqlite3.Connection) -> bytes:
        """La chiave dei cookie: dal segreto di sessione del database, letto al primo uso."""
        if "scheda" not in chiavi:
            chiavi["scheda"] = chiave_scheda(db.segreto_sessione(conn))
        return chiavi["scheda"]

    def persona_dal_cookie_attuale(conn: sqlite3.Connection, valore: str | None) -> int | None:
        """La persona del cookie, solo se il suo codice è ancora quello con cui è entrata."""
        grezzo = (valore or "").split(".")[0]
        impronta = db_schede_ore.impronta_codice(conn, int(grezzo)) if grezzo.isdigit() and len(grezzo) <= 12 else None
        if impronta is None:
            return None
        return persona_dal_cookie(chiave_persona(chiave_di(conn), impronta), valore, time.time())

    def persona_corrente(request: Request, conn: Conn) -> dict:
        pid = persona_dal_cookie_attuale(conn, request.cookies.get(COOKIE))
        p = _dipendente_attivo(conn, pid)
        if p is None:
            raise HTTPException(401, ACCESSO_RICHIESTO)
        return p

    Persona = Annotated[dict, Depends(persona_corrente)]

    def mese_apribile(mese: str) -> str:
        if mese not in mesi_apribili(date.today()):
            raise HTTPException(404, "Questo mese non è disponibile")
        return mese

    def modificabile(conn: sqlite3.Connection, persona_id: int, mese: str) -> None:
        salvata = db_schede_ore.get_scheda(conn, persona_id, mese)
        if salvata and salvata["stato"] == "confermata":
            raise HTTPException(409, "La scheda è confermata e non si può più modificare")

    @router.get("/dipendenti")
    def elenco_dipendenti(conn: Conn):
        return [{"id": p["id"], "nome": p["nome"]} for p in db.lista_persone(conn)
                if p["tipo"] == "dipendente" and p["attivo"]]

    @router.post("/accesso")
    def accesso(body: AccessoIn, request: Request, response: Response, conn: Conn):
        p = _dipendente_attivo(conn, body.persona_id)
        if p is None:
            raise HTTPException(401, NON_VALIDO)
        stato, fino = db_schede_ore.verifica_codice(conn, p["id"], body.codice)
        if stato == "senza_codice":
            raise HTTPException(403, "Il codice personale non è ancora impostato: chiedilo ai responsabili")
        if stato == "bloccato":
            minuti = max(1, math.ceil((fino - datetime.now()).total_seconds() / 60))
            raise HTTPException(429, f"Troppi tentativi: riprova tra {minuti} minuti")
        if stato != "ok":
            raise HTTPException(401, NON_VALIDO)
        https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
        cookie = crea_cookie(chiave_persona(chiave_di(conn), db_schede_ore.impronta_codice(conn, p["id"]) or ""),
                             p["id"], time.time())
        response.set_cookie(COOKIE, cookie, max_age=DURATA_COOKIE_S, path=PERCORSO_COOKIE, httponly=True,
                            samesite="strict", secure=https)
        return {"persona_id": p["id"], "nome": p["nome"]}

    @router.post("/uscita")
    def uscita(response: Response):
        response.delete_cookie(COOKIE, path=PERCORSO_COOKIE)
        return {"ok": True}

    @router.get("/mesi")
    def mesi(p: Persona, conn: Conn):
        out = []
        for mese in mesi_apribili(date.today()):
            salvata = db_schede_ore.get_scheda(conn, p["id"], mese)
            out.append({"mese": mese, "stato": salvata["stato"] if salvata else "non_aperta"})
        return out

    @router.get("/{mese}.xlsx")
    def scarica(mese: Mese, p: Persona, conn: Conn):
        mese_apribile(mese)
        scheda = servizio_schede_ore.scheda_del_mese(conn, p["id"], mese)
        if scheda["stato"] != "confermata":
            raise HTTPException(409, "La scheda si scarica dopo la conferma")
        return Response(compila_scheda(scheda), media_type=XLSX, headers={
            "Content-Disposition": f'attachment; filename="{nome_file(scheda)}"', "Cache-Control": "no-store"})

    @router.get("/{mese}")
    def scheda(mese: Mese, p: Persona, conn: Conn):
        return servizio_schede_ore.scheda_del_mese(conn, p["id"], mese_apribile(mese))

    @router.put("/{mese}/giorni/{giorno}")
    def salva_giorno(mese: Mese, giorno: Giorno, body: GiornoIn, p: Persona, conn: Conn):
        modificabile(conn, p["id"], mese_apribile(mese))
        try:
            servizio_schede_ore.salva_correzione(conn, p["id"], mese, giorno, body.model_dump())
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return servizio_schede_ore.scheda_del_mese(conn, p["id"], mese)

    @router.delete("/{mese}/giorni/{giorno}")
    def ripristina_giorno(mese: Mese, giorno: Giorno, p: Persona, conn: Conn):
        modificabile(conn, p["id"], mese_apribile(mese))
        db_schede_ore.ripristina_giorno(conn, p["id"], mese, giorno)
        return servizio_schede_ore.scheda_del_mese(conn, p["id"], mese)

    @router.put("/{mese}/note")
    def salva_note(mese: Mese, body: NoteIn, p: Persona, conn: Conn):
        modificabile(conn, p["id"], mese_apribile(mese))
        db_schede_ore.salva_note(conn, p["id"], mese, body.note.strip())
        return servizio_schede_ore.scheda_del_mese(conn, p["id"], mese)

    @router.post("/{mese}/conferma")
    def conferma(mese: Mese, p: Persona, conn: Conn):
        modificabile(conn, p["id"], mese_apribile(mese))
        congelata = servizio_schede_ore.congela(conn, p["id"], mese)
        if not db_schede_ore.conferma(conn, p["id"], mese, congelata):
            raise HTTPException(409, "La scheda è confermata e non si può più modificare")
        registro.registra(conn, registro.PUBBLICO, "POST", f"{PERCORSO_COOKIE}/{mese}/conferma", 200,
                          f"{p['nome']} ha confermato la scheda ore di {mese}")
        return servizio_schede_ore.scheda_del_mese(conn, p["id"], mese)

    return router


# --- router di gestione (master) ----------------------------------------------------------

def crea_router_gestione(connessione: Callable) -> APIRouter:
    """Codici personali, elenco delle schede di un mese, download e riapertura. Dietro la password del sito:
    chi entra con la password normale quando esiste la master non lo raggiunge (modalità semplice)."""
    router = APIRouter(prefix="/api/schede-ore-gestione")
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    def dipendente(conn: sqlite3.Connection, persona_id: int) -> dict:
        p = db.get_persona(conn, persona_id)
        if p is None or p["tipo"] != "dipendente":
            raise HTTPException(404, "Dipendente non trovato")
        return p

    @router.put("/codici/{persona_id}", status_code=204)
    def imposta_codice(persona_id: IdPath, body: CodiceIn, conn: Conn):
        db_schede_ore.imposta_codice(conn, dipendente(conn, persona_id)["id"], body.codice)
        return Response(status_code=204)

    @router.delete("/codici/{persona_id}", status_code=204)
    def azzera_codice(persona_id: IdPath, conn: Conn):
        db_schede_ore.azzera_codice(conn, dipendente(conn, persona_id)["id"])
        return Response(status_code=204)

    @router.post("/codici/{persona_id}/genera")
    def genera_codice(persona_id: IdPath, conn: Conn):
        """Il codice nuovo, che questa risposta mostra una sola volta."""
        codice = db_schede_ore.genera_codice()
        db_schede_ore.imposta_codice(conn, dipendente(conn, persona_id)["id"], codice)
        return {"codice": codice}

    @router.get("/{mese}/{persona_id}.xlsx")
    def scarica(mese: Mese, persona_id: IdPath, conn: Conn):
        dipendente(conn, persona_id)
        scheda = servizio_schede_ore.scheda_del_mese(conn, persona_id, mese)
        if scheda["stato"] != "confermata":
            raise HTTPException(409, "La scheda non è ancora confermata")
        return Response(compila_scheda(scheda), media_type=XLSX, headers={
            "Content-Disposition": f'attachment; filename="{nome_file(scheda)}"', "Cache-Control": "no-store"})

    @router.post("/{mese}/{persona_id}/riapri", status_code=204)
    def riapri(mese: Mese, persona_id: IdPath, conn: Conn):
        dipendente(conn, persona_id)
        if not db_schede_ore.riapri(conn, persona_id, mese):
            raise HTTPException(409, "La scheda non è confermata")
        return Response(status_code=204)

    @router.get("/{mese}")
    def elenco(mese: Mese, conn: Conn):
        return db_schede_ore.elenco_mese(conn, mese)

    return router
