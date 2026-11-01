"""API del calendario delle festività a rotazione: GET/POST/PUT/DELETE /api/festivita (docs/API.md)."""
import sqlite3
from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator

from . import db, db_festivi_disponibili, db_festivita, db_storico_festivi, prossime_festivita
from .api_comune import DataValida, Id, IdPath, Nome, errore
from .festivita import OFFSET_PASQUA_MAX, PESO_MAX, PESO_MIN, anteprima, date_festive, errore_regola
from .prossime_festivita import MESI_MAX, MESI_MIN

ANNO_MIN, ANNO_MAX = 2000, 2099
FESTIVITA_AGGIUNTE_MAX = 100  # aggiunte a mano: bastano e avanzano, e il calendario resta leggibile
PERIODO_DISPONIBILI_MAX = 3 * 366  # giorni


class DisponibileIn(BaseModel):
    """Chi vuole lavorare una festività: fascia None toglie l'indicazione."""
    data: DataValida
    persona_id: Id
    fascia: Literal["giorno", "notte", "entrambi"] | None
# campi che non servono alla regola: azzerati, così l'interfaccia può mandare il modulo intero
_NON_PERTINENTI = {"fissa": ("offset_pasqua", "data"), "pasqua": ("giorno", "mese", "data"),
                   "data": ("giorno", "mese", "offset_pasqua")}


class FestivitaIn(BaseModel):
    nome: Nome
    regola: Literal["fissa", "pasqua", "data"]
    giorno: int | None = Field(default=None, ge=1, le=31)
    mese: int | None = Field(default=None, ge=1, le=12)
    offset_pasqua: int | None = Field(default=None, ge=-OFFSET_PASQUA_MAX, le=OFFSET_PASQUA_MAX)
    data: DataValida | None = None
    conta_giorno: bool = True
    conta_notte: bool = True
    conta_notte_prima: bool = False
    peso: int = Field(default=PESO_MIN, ge=PESO_MIN, le=PESO_MAX)
    attiva: bool = True

    @model_validator(mode="before")
    @classmethod
    def _azzera_non_pertinenti(cls, valori):
        """Prima dei controlli: un campo che la regola non usa (es. il giorno per Pasqua) non deve dare errore."""
        if isinstance(valori, dict) and valori.get("regola") in _NON_PERTINENTI:
            return {**valori, **{k: None for k in _NON_PERTINENTI[valori["regola"]]}}
        return valori

    @model_validator(mode="after")
    def _coerente(self):
        messaggio = errore_regola(self.regola, self.giorno, self.mese, self.offset_pasqua, self.data)
        if messaggio:
            raise ValueError(messaggio)
        if not (self.conta_giorno or self.conta_notte or self.conta_notte_prima):
            raise ValueError("Scegli almeno un turno che conta: giorno, notte o notte della sera prima")
        return self

    def dati(self) -> dict:
        return self.model_dump()


def _con_anteprima(f: dict, anno: int) -> dict:
    return {**f, "anteprima": anteprima(f, anno)}


def crea_router(connessione: Callable) -> APIRouter:
    """Router delle festività; `connessione` è la dipendenza che apre il database (vedi app.py)."""
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    # i percorsi fissi (/api/festivita/disponibili, /prossime, /lavorate) vanno dichiarati PRIMA di quelli con {id}

    @router.get("/api/festivita/disponibili")
    def disponibili(conn: Conn, dal: DataValida, al: DataValida):
        if al < dal:
            raise errore("La data di fine è prima di quella di inizio")
        if (al - dal).days > PERIODO_DISPONIBILI_MAX:
            raise errore(f"Il periodo può essere al massimo di {PERIODO_DISPONIBILI_MAX} giorni")
        return db_festivi_disponibili.elenco(conn, dal, al)

    @router.put("/api/festivita/disponibili")
    def imposta_disponibile(body: DisponibileIn, conn: Conn):
        p = db.get_persona(conn, body.persona_id)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        if p["tipo"] != "dipendente":
            raise errore("Solo i dipendenti entrano nella rotazione delle festività")
        if body.data not in date_festive(db_festivita.festivita_attive(conn), body.data.year):
            raise errore("Quel giorno non è una festività a rotazione: attivala prima in Impostazioni")
        db_festivi_disponibili.imposta(conn, body.data, body.persona_id, body.fascia)
        return {"data": body.data.isoformat(), "persona_id": body.persona_id, "fascia": body.fascia}

    @router.get("/api/festivita/prossime")
    def prossime(conn: Conn, mesi: Annotated[int, Query(ge=MESI_MIN, le=MESI_MAX)] = 12):
        return prossime_festivita.prossime(conn, date.today(), mesi)

    @router.get("/api/festivita/lavorate")
    def lavorate(conn: Conn, anno: Annotated[int, Query(ge=ANNO_MIN, le=ANNO_MAX)]):
        return prossime_festivita.lavorate_anno(conn, anno, date.today())

    @router.get("/api/festivita")
    def lista(conn: Conn, anno: Annotated[int | None, Query(ge=ANNO_MIN, le=ANNO_MAX)] = None):
        anno = anno if anno is not None else date.today().year
        return [_con_anteprima(f, anno) for f in db_festivita.lista_festivita(conn)]

    @router.post("/api/festivita", status_code=201)
    def crea(body: FestivitaIn, conn: Conn):
        dati = body.dati()
        if db_festivita.numero_aggiunte(conn) >= FESTIVITA_AGGIUNTE_MAX:
            raise errore(f"Si possono aggiungere al massimo {FESTIVITA_AGGIUNTE_MAX} festività")
        if messaggio := db_festivita.festivita_doppione(conn, dati):
            raise errore(messaggio)
        return _con_anteprima(db_festivita.crea_festivita(conn, dati), date.today().year)

    @router.put("/api/festivita/{festivita_id}")
    def aggiorna(festivita_id: IdPath, body: FestivitaIn, conn: Conn):
        attuale = db_festivita.get_festivita(conn, festivita_id)
        if attuale is None:
            raise HTTPException(404, "Festività non trovata")
        dati = body.dati()
        if attuale["predefinita"]:
            nuovi = {**dati, "data": dati["data"].isoformat() if dati["data"] else None}
            if any(nuovi[k] != attuale[k] for k in db_festivita.IDENTITA):
                raise errore("Le festività predefinite non si possono rinominare né spostare")
        if messaggio := db_festivita.festivita_doppione(conn, dati, escluso=festivita_id):
            raise errore(messaggio)
        f = db_festivita.aggiorna_festivita(conn, festivita_id, dati)
        if f is None:
            raise HTTPException(404, "Festività non trovata")
        return _con_anteprima(f, date.today().year)

    @router.delete("/api/festivita/{festivita_id}", status_code=204)
    def elimina(festivita_id: IdPath, conn: Conn):
        attuale = db_festivita.get_festivita(conn, festivita_id)
        if attuale is None:
            raise HTTPException(404, "Festività non trovata")
        if attuale["predefinita"]:
            raise errore("Le festività predefinite non si cancellano: si possono solo disattivare")
        if anni := db_storico_festivi.anni_con_festivita(conn, festivita_id):
            elenco = ", ".join(str(a) for a in anni)
            raise errore(f"{attuale['nome']} è nello storico ({elenco}): disattivala oppure togli prima quei dati")
        db_festivita.elimina_festivita(conn, festivita_id)
        return Response(status_code=204)

    return router
