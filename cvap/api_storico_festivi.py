"""API dello storico festività degli anni passati: /api/storico-festivi (docs/API.md, docs/PIANO-rotazioni.md 3.2)."""
import sqlite3
from collections.abc import Callable
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path as PathParam
from pydantic import BaseModel, Field, StringConstraints

from . import db, db_festivita, db_storico_festivi
from .api_comune import Id, Nome, errore
from .db import _chiave_nome
from .festivita import data_nell_anno
from .storico_festivi import (ANNO_MIN, PERSONE_PER_CELLA_MAX, RIGHE_MAX, TESTO_MAX, analizza, anno_max,
                              celle_troppo_piene, limite_storico, persone_per_chiave)

ANNO_PATH_MAX = 2099
TURNI_ANNO_MAX = 2000
SERVIZIO_MAX = 500
Fascia = Literal["giorno", "notte"]
AnnoPath = Annotated[int, PathParam(ge=ANNO_MIN, le=ANNO_PATH_MAX)]


class TurnoIn(BaseModel):
    festivita_id: Id
    fascia: Fascia
    persona_id: Id


class StoricoAnnoIn(BaseModel):
    turni: list[TurnoIn] = Field(default_factory=list, max_length=TURNI_ANNO_MAX)
    servizio: list[Id] = Field(default_factory=list, max_length=SERVIZIO_MAX)


class AnteprimaIn(BaseModel):
    testo: Annotated[str, StringConstraints(max_length=TESTO_MAX)]


class RigaImportIn(BaseModel):
    anno: int = Field(ge=ANNO_MIN, le=ANNO_PATH_MAX)
    festivita_id: Id
    fascia: Fascia
    nome: Nome


class AbbinamentoIn(BaseModel):
    nome: Nome
    azione: Literal["persona", "nuovo", "scarta"]
    persona_id: Id | None = None
    qualifica: Literal["autista", "soccorritore"] = "soccorritore"


class ImportaIn(BaseModel):
    righe: list[RigaImportIn] = Field(max_length=RIGHE_MAX)
    abbinamenti: list[AbbinamentoIn] = Field(default_factory=list, max_length=RIGHE_MAX)
    sostituisci: bool = False


def _nome_pulito(nome: str) -> str:
    return " ".join(nome.split())


def _limite(conn) -> date:
    return limite_storico(db_storico_festivi.prima_generata(conn), date.today())


def _controlla_anno(anno: int, limite: date) -> None:
    if anno > anno_max(limite):
        raise errore(f"Dal {limite:%d/%m/%Y} in poi le festività le conta già il programma: "
                     f"lo storico arriva al {anno_max(limite)}")


def _data_valida(f: dict | None, anno: int, limite: date) -> date | None:
    """Il giorno della festività nell'anno, se cade prima del limite; altrimenti None."""
    d = data_nell_anno(f, anno) if f else None
    return d if d is not None and d < limite else None


def _payload_anno(conn, anno: int, limite: date) -> dict:
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    festivita = {f["id"]: f for f in db_festivita.lista_festivita(conn)}
    turni = db_storico_festivi.turni_anno(conn, anno)
    usate = {t["festivita_id"] for t in turni}
    voci = []
    for f in festivita.values():
        d = _data_valida(f, anno, limite)
        if d is not None and (f["id"] in usate or f["attiva"]):
            celle = {fascia: [{"persona_id": t["persona_id"], "nome": persone[t["persona_id"]]["nome"]}
                              for t in turni if t["festivita_id"] == f["id"] and t["fascia"] == fascia]
                     for fascia in ("giorno", "notte")}
            voci.append({"festivita_id": f["id"], "nome": f["nome"], "data": d.isoformat(), "attiva": f["attiva"],
                         "peso": f["peso"], **celle})
    salvato = db_storico_festivi.servizio_anno(conn, anno)
    ids = salvato or sorted({p["id"] for p in persone.values() if p["tipo"] == "dipendente" and p["attivo"]}
                            | {t["persona_id"] for t in turni})
    servizio = sorted(({"persona_id": i, "nome": persone[i]["nome"], "attivo": persone[i]["attivo"]} for i in ids),
                      key=lambda x: x["nome"].casefold())
    return {"anno": anno, "limite": limite.isoformat(), "festivita": sorted(voci, key=lambda v: (v["data"], v["nome"])),
            "servizio": servizio, "servizio_salvato": bool(salvato)}


def _dipendente(persone: dict, persona_id: int) -> None:
    p = persone.get(persona_id)
    if p is None:
        raise errore(f"Persona non trovata: {persona_id}")
    if p["tipo"] != "dipendente":
        raise errore(f"{p['nome']} è un volontario: lo storico delle festività riguarda i dipendenti")


def _turni_validi(conn, anno: int, body: StoricoAnnoIn, limite: date) -> list[tuple[int, str, int]]:
    festivita = {f["id"]: f for f in db_festivita.lista_festivita(conn)}
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    turni = list(dict.fromkeys((t.festivita_id, t.fascia, t.persona_id) for t in body.turni))
    for f_id, fascia, p_id in turni:
        if f_id not in festivita:
            raise errore(f"Festività non trovata: {f_id}")
        if _data_valida(festivita[f_id], anno, limite) is None:
            raise errore(f"{festivita[f_id]['nome']} {anno}: non cade quell'anno o la conta già il programma")
        _dipendente(persone, p_id)
    _controlla_celle(turni, festivita, anno)
    for p_id in body.servizio:
        _dipendente(persone, p_id)
    return turni


def _controlla_celle(turni: list[tuple], festivita: dict, anno: int) -> None:
    for f_id, fascia in celle_troppo_piene(turni):
        raise errore(f"{festivita[f_id]['nome']} {anno}, {fascia}: al massimo {PERSONE_PER_CELLA_MAX} persone")


def _risolvi_nome(nome: str, abbinamenti: dict, dipendenti: dict, persone: dict) -> str | None:
    """Chiave della persona per l'importazione ("id:<n>" o "nuovo:<nome>"), None se scartata; 400 se non risolto."""
    chiave = _chiave_nome(nome)
    a = abbinamenti.get(chiave)
    if a is not None:
        if a.azione == "scarta":
            return None
        if a.azione == "nuovo":
            if dipendenti.get(_chiave_nome(a.nome)):
                raise errore(f"{a.nome} è già nel Personale: scegli la persona invece di registrarla di nuovo")
            return f"nuovo:{_nome_pulito(a.nome)}"
        if a.persona_id is None:
            raise errore(f"{nome}: scegli la persona")
        _dipendente(persone, a.persona_id)
        return f"id:{a.persona_id}"
    trovate = dipendenti.get(chiave, [])
    if len(trovate) != 1:
        raise errore(f"{nome}: persona non trovata o con omonimi, scegli a chi corrisponde")
    return f"id:{trovate[0]['id']}"


def _prepara_importazione(conn, body: ImportaIn, limite: date):
    festivita = {f["id"]: f for f in db_festivita.lista_festivita(conn)}
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    dipendenti = persone_per_chiave(list(persone.values()))
    abbinamenti = {_chiave_nome(a.nome): a for a in body.abbinamenti}  # a parità di nome vale l'ultimo
    turni: dict[int, list[tuple[int, str, str]]] = {}
    conti = {"ignorate": 0, "scartate": 0}
    anni_validi: set[int] = set()  # anni con almeno una riga valida (anche se scartata): "sostituisci" vale per loro
    for r in body.righe:
        if _data_valida(festivita.get(r.festivita_id), r.anno, limite) is None:
            conti["ignorate"] += 1
            continue
        anni_validi.add(r.anno)
        chiave = _risolvi_nome(r.nome, abbinamenti, dipendenti, persone)
        if chiave is None:
            conti["scartate"] += 1
        else:
            turni.setdefault(r.anno, []).append((r.festivita_id, r.fascia, chiave))
    turni = {anno: list(dict.fromkeys(t)) for anno, t in turni.items()}
    for anno, t in turni.items():
        if len(t) > TURNI_ANNO_MAX:
            raise errore(f"{anno}: al massimo {TURNI_ANNO_MAX} turni in un anno")
        _controlla_celle(t, festivita, anno)
    usate = {k for t in turni.values() for *_, k in t}
    nuove = {_chiave_nome(a.nome): (_nome_pulito(a.nome), a.qualifica) for a in body.abbinamenti
             if a.azione == "nuovo" and f"nuovo:{_nome_pulito(a.nome)}" in usate}  # un nome, una persona
    return turni, list(nuove.values()), conti, anni_validi


def crea_router(connessione: Callable) -> APIRouter:
    """Router dello storico festività; `connessione` è la dipendenza che apre il database (vedi app.py)."""
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    # percorsi fissi prima di quelli con {anno}

    @router.get("/api/storico-festivi")
    def riepilogo(conn: Conn):
        limite = _limite(conn)
        return {"anno_min": ANNO_MIN, "anno_max": anno_max(limite), "limite": limite.isoformat(),
                "anni": db_storico_festivi.riepilogo_anni(conn)}

    @router.post("/api/storico-festivi/anteprima")
    def anteprima(body: AnteprimaIn, conn: Conn):
        try:
            esito = analizza(body.testo, db_festivita.lista_festivita(conn), db.lista_persone(conn), _limite(conn))
        except ValueError as e:
            raise errore(str(e)) from None
        esistenti = db_storico_festivi.righe_per_anno(conn)  # anni già inseriti e anni del file
        anni = set(esistenti) | {r["anno"] for r in esito["riconosciute"]}
        return {**esito, "righe_esistenti_per_anno": {str(a): esistenti.get(a, 0) for a in sorted(anni)}}

    @router.post("/api/storico-festivi/importa")
    def importa(body: ImportaIn, conn: Conn):
        limite = _limite(conn)
        turni, nuove, conti, anni_validi = _prepara_importazione(conn, body, limite)
        sostituiti = anni_validi if body.sostituisci else set()
        create, inseriti = db_storico_festivi.importa(conn, turni, nuove, sostituiti)
        return {"importati": inseriti, "gia_presenti": sum(len(t) for t in turni.values()) - inseriti, **conti,
                "anni": sorted(set(turni) | sostituiti), "persone_create": create}

    @router.get("/api/storico-festivi/{anno}")
    def leggi_anno(anno: AnnoPath, conn: Conn):
        limite = _limite(conn)
        _controlla_anno(anno, limite)
        return _payload_anno(conn, anno, limite)

    @router.put("/api/storico-festivi/{anno}")
    def salva_anno(anno: AnnoPath, body: StoricoAnnoIn, conn: Conn):
        limite = _limite(conn)
        _controlla_anno(anno, limite)
        turni = _turni_validi(conn, anno, body, limite)
        servizio = sorted(set(body.servizio) | {p for *_, p in turni})
        modificabili = {f["id"] for f in db_festivita.lista_festivita(conn) if _data_valida(f, anno, limite)}
        db_storico_festivi.sostituisci_anno(conn, anno, turni, servizio, modificabili)
        return _payload_anno(conn, anno, limite)

    return router
