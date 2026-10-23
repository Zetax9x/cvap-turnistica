"""API REST della turnistica (FastAPI). Contratto in docs/API.md."""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints, model_validator

from . import db
from .calendario import giorni_settimana, lunedi, postazioni_attive, tipo_settimana
from .modello import (INTERO_DI, PARTI_TURNO, POSTAZIONI_A_RICHIESTA, PROGRAMMATI, SEGMENTI, STANDBY,
                      TURNI_VIETABILI, Assegnazione, Fabbisogno, Persona, si_sovrappongono, turni_ammessi)
from .storico import CATEGORIE_WEEKEND, SettimanaPassata, calcola_storico, categoria_weekend
from .vincoli import giorni_disponibili, media_ore, ore_ferie, valida_settimana

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
GIORNI_CONTESTO = 3
DATA_MIN, DATA_MAX = date(2000, 1, 1), date(2100, 12, 31)
DataValida = Annotated[date, Field(ge=DATA_MIN, le=DATA_MAX)]
FERIE_GIORNI_MAX = 366
FABBISOGNO_VOCI_MAX = 200
QUANTITA_MAX = {STANDBY: 1, PROGRAMMATI: 20}
# turni che si possono richiedere (le metà dello Standby sono solo per i volontari che lo spezzano)
TURNI_RICHIEDIBILI = {
    STANDBY: {("giorno", "standby"), ("notte", "standby")},
    PROGRAMMATI: {("giorno", "prog_mattina"), ("giorno", "prog_pomeriggio")},
}

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100,
                                        pattern=r"^[^\x00-\x1f\x7f]+$")]  # niente caratteri di controllo
ID_MAX = 2 ** 63 - 1  # oltre, SQLite non accetta l'intero (OverflowError -> 500)
Id = Annotated[int, Field(ge=1, le=ID_MAX)]
IdPath = Annotated[int, PathParam(ge=1, le=ID_MAX)]
Tipo = Literal["dipendente", "volontario"]
Qualifica = Literal["autista", "soccorritore"]


class PersonaIn(BaseModel):
    nome: Nome
    tipo: Tipo
    qualifica: Qualifica
    autista_programmati: bool = False


class PersonaUpdate(PersonaIn):
    attivo: bool = True
    autista_programmati: bool | None = None  # assente = resta com'è


class ParametriIn(BaseModel):
    max_ore_settimana: int | None = Field(ge=1, le=24 * 7)  # obbligatorio; null = nessun limite


class DivietoIn(BaseModel):
    persona_id: Id
    postazione: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    turno: Literal[TURNI_VIETABILI] | None = None


class ImpostazioniIn(BaseModel):
    data_riferimento_a: DataValida | None = None
    scarto_ore_max: int | None = Field(default=None, ge=db.SCARTO_ORE_MAX_RANGE[0], le=db.SCARTO_ORE_MAX_RANGE[1])

    @model_validator(mode="after")
    def _almeno_una(self):
        if not self.model_fields_set & {"data_riferimento_a", "scarto_ore_max"}:
            raise ValueError("indicare data_riferimento_a e/o scarto_ore_max")
        if self.data_riferimento_a is None and self.scarto_ore_max is None:
            raise ValueError("i valori indicati non possono essere null")
        return self


class AssegnazioneIn(BaseModel):
    data: DataValida
    postazione: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    fascia: Literal["giorno", "notte"]
    segmento: Literal[SEGMENTI]
    ruolo: Literal["autista", "soccorritore"]
    persona_id: Id | None = None
    nome_volontario: Nome | None = None  # volontario non registrato: si cerca per nome o si crea

    @model_validator(mode="after")
    def _una_persona(self):
        if (self.persona_id is None) == (self.nome_volontario is None):
            raise ValueError("indicare persona_id oppure nome_volontario (uno solo)")
        return self


class FerieIn(BaseModel):
    persona_id: Id
    dal: DataValida
    al: DataValida


class TurnoIndisponibileIn(BaseModel):
    data: DataValida
    parte: Literal[PARTI_TURNO]


class IndisponibilitaIn(BaseModel):
    persona_id: Id
    turni: Annotated[list[TurnoIndisponibileIn], Field(max_length=21)]  # 7 giorni x 3 parti


class VoceFabbisognoIn(BaseModel):
    data: DataValida
    postazione: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    fascia: Literal["giorno", "notte"]
    segmento: Literal[SEGMENTI]
    ruolo: Literal["autista", "soccorritore"]
    quantita: int = Field(ge=0, le=20)


class FabbisognoIn(BaseModel):
    voci: Annotated[list[VoceFabbisognoIn], Field(max_length=FABBISOGNO_VOCI_MAX)]


class GeneraIn(BaseModel):
    tempo_max: float | None = Field(default=None, gt=0, le=600)


def _errore(messaggio: str) -> HTTPException:
    return HTTPException(status_code=400, detail=messaggio)


def _data(valore: str) -> date:
    try:
        d = date.fromisoformat(valore)
    except ValueError:
        raise _errore(f"Data non valida: {valore!r} (formato atteso AAAA-MM-GG)") from None
    if not DATA_MIN <= d <= DATA_MAX:
        raise _errore(f"Data fuori intervallo ({DATA_MIN.year}-{DATA_MAX.year})")
    return d


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _unita_json(u) -> dict:
    return {"data": u.data.isoformat(), "postazione": u.postazione, "fascia": u.fascia,
            "segmento": u.segmento, "ruolo": u.ruolo}


# --- costruzione del payload settimana -------------------------------------------

def _contesto(conn, giorni: list[date]) -> list[Assegnazione]:
    prima = db.assegnazioni_periodo(conn, giorni[0] - timedelta(days=GIORNI_CONTESTO), giorni[0] - timedelta(days=1))
    dopo = db.assegnazioni_periodo(conn, giorni[-1] + timedelta(days=1), giorni[-1] + timedelta(days=GIORNI_CONTESTO))
    return [a for _, a in prima + dopo]


def _info_settimana(conn, inizio: date) -> tuple[list[date], str, list[str]]:
    giorni = giorni_settimana(inizio)
    tipo = tipo_settimana(inizio, db.get_riferimento_a(conn))
    return giorni, tipo, postazioni_attive(tipo, db.postazioni(conn))


def _giorni_json(per_persona: dict[int, set[date]]) -> list[dict]:
    return [{"persona_id": pid, "data": d.isoformat()}
            for pid, giorni in sorted(per_persona.items()) for d in sorted(giorni)]


def _a_richiesta(tipo: str) -> list[str]:
    """Postazioni a richiesta disponibili nella settimana (solo le settimane A)."""
    return list(POSTAZIONI_A_RICHIESTA) if tipo == "A" else []


def _fabbisogno_attivo(conn, giorni: list[date], tipo: str):
    """Fabbisogno della settimana; nelle settimane B è vuoto anche se nel DB ne restano righe
    (ad es. dopo un cambio della data di riferimento A)."""
    if not _a_richiesta(tipo):
        return []
    return db.fabbisogno_periodo(conn, giorni[0], giorni[-1])


def payload_settimana(conn: sqlite3.Connection, inizio: date) -> dict:
    giorni, tipo, attive = _info_settimana(conn, inizio)
    fabbisogno = _fabbisogno_attivo(conn, giorni, tipo)
    righe = db.assegnazioni_periodo(conn, giorni[0], giorni[-1])
    assegnazioni = [a for _, a in righe]
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    presenti = {a.persona_id for a in assegnazioni}
    ferie = db.ferie_periodo(conn, giorni[0], giorni[-1])
    indisponibili = db.indisponibili_periodo(conn, giorni[0], giorni[-1])

    # volontari + dipendenti attivi + chiunque (anche disattivato) abbia turni questa settimana
    divieti = db.divieti_per_persona(conn)
    scarto_ore_max = db.get_scarto_ore_max(conn)
    rilevanti = {pid: db.a_persona(p, divieti.get(pid, ())) for pid, p in persone.items()
                 if p["tipo"] == "volontario" or p["attivo"] or pid in presenti}
    violazioni = valida_settimana(giorni, attive, assegnazioni, rilevanti, contesto=_contesto(conn, giorni),
                                  ferie=ferie, indisponibili=indisponibili, fabbisogno=fabbisogno,
                                  scarto_ore_max=scarto_ore_max)

    dipendenti_attivi = [p for p in persone.values() if p["tipo"] == "dipendente" and p["attivo"]]
    ids_riepilogo = presenti | {p["id"] for p in dipendenti_attivi}
    riepilogo = []
    for pid in ids_riepilogo:
        p = persone.get(pid)
        if p is None:
            continue
        turni = [a for a in assegnazioni if a.persona_id == pid]
        riepilogo.append({
            "persona_id": pid, "nome": p["nome"], "tipo": p["tipo"], "qualifica": p["qualifica"],
            "ore": sum(a.ore for a in turni),
            "ore_giorno": sum(a.ore for a in turni if a.fascia == "giorno"),
            "ore_notte": sum(a.ore for a in turni if a.fascia == "notte"),
            "turni_weekend": sum(1 for a in turni if a.data.weekday() >= 5),
            "giorni_ferie": len(ferie.get(pid, ())),
            "ore_ferie": ore_ferie(giorni, ferie.get(pid, set())) if p["tipo"] == "dipendente" else 0,
            "giorni_indisponibili": len({d for d, _ in indisponibili.get(pid, ())}),
            "max_ore_settimana": p["max_ore_settimana"] if p["tipo"] == "dipendente" else None,
        })
    riepilogo.sort(key=lambda r: (r["tipo"] != "dipendente", r["nome"].lower(), r["persona_id"]))

    ore_dip = {p["id"]: 0 for p in dipendenti_attivi if giorni_disponibili(giorni, ferie.get(p["id"], set()))}
    for a in assegnazioni:
        if a.persona_id in ore_dip:
            ore_dip[a.persona_id] += a.ore
    media = media_ore(ore_dip, {pid: ore_ferie(giorni, ferie.get(pid, set())) for pid in ore_dip})

    riga = db.get_settimana(conn, giorni[0])
    return {
        "inizio": giorni[0].isoformat(),
        "fine": giorni[-1].isoformat(),
        "tipo": tipo,
        "stato": riga["stato"] if riga else "nuova",
        "giorni": [g.isoformat() for g in giorni],
        "postazioni": attive,
        "postazioni_a_richiesta": _a_richiesta(tipo),
        "fabbisogno": [{"data": f.data.isoformat(), "postazione": f.postazione, "fascia": f.fascia,
                        "segmento": f.segmento, "ruolo": f.ruolo, "quantita": f.quantita} for f in fabbisogno],
        "assegnazioni": [{
            "id": aid, "data": a.data.isoformat(), "postazione": a.postazione, "fascia": a.fascia,
            "segmento": a.segmento, "ruolo": a.ruolo, "persona_id": a.persona_id,
            "persona_nome": persone[a.persona_id]["nome"] if a.persona_id in persone else f"#{a.persona_id}",
            "origine": a.origine, "ore": a.ore,
        } for aid, a in righe],
        "ferie": _giorni_json(ferie),
        "indisponibilita": [{"persona_id": pid, "data": d.isoformat(), "parte": parte}
                            for pid, turni in sorted(indisponibili.items())
                            for d, parte in sorted(turni, key=lambda t: (t[0], PARTI_TURNO.index(t[1])))],
        "violazioni": [{"livello": v.livello, "codice": v.codice, "messaggio": v.messaggio,
                        "persona_id": v.persona_id, "data": _iso(v.data)} for v in violazioni],
        "riepilogo": riepilogo,
        "media_ore": media,
        "scarto_ore_max": scarto_ore_max,
        "report": riga["report"] if riga else None,
    }


def _settimana_passata(conn, riga: dict) -> SettimanaPassata:
    inizio = date.fromisoformat(riga["inizio"])
    assegnazioni = [a for _, a in db.assegnazioni_periodo(conn, inizio, inizio + timedelta(days=6))]
    giorni = giorni_settimana(inizio)
    dipendenti = list(riga["dipendenti"])
    ferie = db.ferie_periodo(conn, giorni[0], giorni[-1])
    disponibili = {pid: giorni_disponibili(giorni, ferie.get(pid, set())) for pid in dipendenti}
    ore = {pid: 0 for pid, g in disponibili.items() if g}
    for a in assegnazioni:
        if a.persona_id in ore:
            ore[a.persona_id] += a.ore
    crediti = {pid: ore_ferie(giorni, ferie.get(pid, set())) for pid in ore}
    return SettimanaPassata(media_ore=media_ore(ore, crediti), dipendenti=dipendenti,
                            assegnazioni=assegnazioni,
                            giorni_ferie={pid: 7 - g for pid, g in disponibili.items() if g < 7},
                            max_ore={p["id"]: p["max_ore_settimana"] for p in db.lista_persone(conn)
                                     if p["id"] in ore and p["max_ore_settimana"]})


def _volontario_per_nome(conn, nome: str, ruolo: str) -> int:
    """Id del volontario con quel nome (maiuscole e spazi non contano), creandolo se non esiste.

    Chi fa l'autista diventa autista; un volontario disattivato viene riattivato.
    """
    nome = " ".join(nome.split())
    omonimi = db.persone_per_nome(conn, nome)
    if any(p["tipo"] == "dipendente" for p in omonimi):
        raise _errore(f"{nome} è un dipendente: sceglilo dall'elenco dei dipendenti")
    if not omonimi:
        return db.crea_persona(conn, nome, "volontario", ruolo)["id"]
    p = max(omonimi, key=lambda x: (x["attivo"], -x["id"]))  # preferisci l'attivo, poi il più vecchio
    qualifica = "autista" if ruolo == "autista" else p["qualifica"]
    if not p["attivo"] or qualifica != p["qualifica"]:
        db.aggiorna_persona(conn, p["id"], p["nome"], p["tipo"], qualifica, True)
    return p["id"]


def _verifica_posto_richiesto(conn, body: "AssegnazioneIn", stesso_posto: list[Assegnazione]) -> None:
    """Postazioni a richiesta: il turno dev'essere richiesto e avere ancora posti liberi."""
    if body.postazione == PROGRAMMATI:
        segmento_richiesto = body.segmento
    else:  # Standby: le metà occupano il posto del turno intero
        segmento_richiesto = INTERO_DI.get(body.segmento, body.segmento)
    quantita = sum(f.quantita for f in db.fabbisogno_periodo(conn, body.data, body.data)
                   if (f.postazione, f.fascia, f.segmento, f.ruolo)
                   == (body.postazione, body.fascia, segmento_richiesto, body.ruolo))
    if quantita <= 0:
        raise _errore(f"Turno non richiesto: indica prima il fabbisogno di {body.postazione} per quel turno")
    if body.postazione == PROGRAMMATI:
        if sum(1 for a in stesso_posto if a.segmento == body.segmento) >= quantita:
            raise _errore(f"I posti richiesti per quel turno di {body.postazione} sono già tutti occupati")
    elif any(si_sovrappongono(a.segmento, body.segmento) for a in stesso_posto):
        raise _errore("Il posto è già occupato in quella fascia")


def _verifica_modificabile(conn, inizio: date) -> None:
    riga = db.get_settimana(conn, inizio)
    if riga and riga["stato"] == "confermata":
        raise _errore("La settimana è confermata: riaprila per modificarla")


# --- app ---------------------------------------------------------------------

def create_app(db_path: str) -> FastAPI:
    db_path = str(db_path)
    db.connetti(db_path).close()  # crea schema e seed

    app = FastAPI(title="CVAP Turnistica")
    blocco = threading.Lock()
    app.state.blocco_scrittura = blocco

    @contextmanager
    def scrittura(attendi: bool = True):
        """Serializza le modifiche alle settimane: nulla cambia (né si conferma) durante una generazione."""
        preso = blocco.acquire(timeout=5) if attendi else blocco.acquire(blocking=False)
        if not preso:
            raise HTTPException(409, "Generazione dei turni in corso: riprova tra qualche istante")
        try:
            yield
        finally:
            blocco.release()

    def connessione() -> Iterator[sqlite3.Connection]:
        conn = db.apri(db_path)
        try:
            yield conn
        finally:
            conn.close()

    Conn = Annotated[sqlite3.Connection, Depends(connessione)]

    # --- persone ---
    @app.get("/api/persone")
    def lista_persone(conn: Conn):
        return db.lista_persone(conn)

    @app.post("/api/persone", status_code=201)
    def crea_persona(body: PersonaIn, conn: Conn):
        return db.crea_persona(conn, body.nome, body.tipo, body.qualifica, body.autista_programmati)

    @app.put("/api/persone/{persona_id}")
    def aggiorna_persona(persona_id: IdPath, body: PersonaUpdate, conn: Conn):
        p = db.aggiorna_persona(conn, persona_id, body.nome, body.tipo, body.qualifica, body.attivo,
                                body.autista_programmati)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        return p

    @app.put("/api/persone/{persona_id}/parametri")
    def imposta_parametri(persona_id: IdPath, body: ParametriIn, conn: Conn):
        p = db.imposta_max_ore(conn, persona_id, body.max_ore_settimana)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        return p

    @app.delete("/api/persone/{persona_id}", status_code=204)
    def elimina_persona(persona_id: IdPath, conn: Conn):
        if not db.elimina_persona(conn, persona_id):
            raise HTTPException(404, "Persona non trovata")
        return Response(status_code=204)

    # --- postazioni / impostazioni ---
    @app.get("/api/postazioni")
    def lista_postazioni(conn: Conn):
        return db.lista_postazioni(conn)

    def impostazioni(conn) -> dict:
        return {"data_riferimento_a": db.get_riferimento_a(conn).isoformat(),
                "scarto_ore_max": db.get_scarto_ore_max(conn)}

    @app.get("/api/impostazioni")
    def get_impostazioni(conn: Conn):
        return impostazioni(conn)

    @app.put("/api/impostazioni")
    def put_impostazioni(body: ImpostazioniIn, conn: Conn):
        if body.data_riferimento_a is not None:
            db.set_riferimento_a(conn, body.data_riferimento_a)
        if body.scarto_ore_max is not None:
            db.set_scarto_ore_max(conn, body.scarto_ore_max)
        return impostazioni(conn)

    # --- divieti ---
    @app.get("/api/divieti")
    def lista_divieti(conn: Conn):
        return db.lista_divieti(conn)

    @app.post("/api/divieti", status_code=201)
    def crea_divieto(body: DivietoIn, conn: Conn):
        if body.postazione is None and body.turno is None:
            raise _errore("Indica almeno la postazione o il tipo di turno")
        p = db.get_persona(conn, body.persona_id)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        if p["tipo"] != "dipendente":
            raise _errore("I divieti si inseriscono solo per i dipendenti")
        if body.postazione is not None and body.postazione not in (
                [x["nome"] for x in db.lista_postazioni(conn)] + list(POSTAZIONI_A_RICHIESTA)):
            raise _errore(f"Postazione sconosciuta: {body.postazione}")
        divieto = db.crea_divieto(conn, body.persona_id, body.postazione, body.turno)
        if divieto is None:
            raise _errore("Questo divieto esiste già")
        return divieto

    @app.delete("/api/divieti/{divieto_id}", status_code=204)
    def elimina_divieto(divieto_id: IdPath, conn: Conn):
        if not db.elimina_divieto(conn, divieto_id):
            raise HTTPException(404, "Divieto non trovato")
        return Response(status_code=204)

    # --- settimane ---
    @app.get("/api/settimane/{data}")
    def get_settimana(data: str, conn: Conn):
        return payload_settimana(conn, lunedi(_data(data)))

    @app.post("/api/settimane/{data}/assegnazioni", status_code=201)
    def aggiungi_assegnazione(data: str, body: AssegnazioneIn, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            _verifica_modificabile(conn, inizio)
            giorni, tipo, attive = _info_settimana(conn, inizio)
            if body.data not in giorni:
                raise _errore("La data del turno non appartiene a questa settimana")
            if body.postazione not in attive + _a_richiesta(tipo):
                raise _errore(f"La postazione {body.postazione} non è attiva nella settimana {tipo}")
            if (body.fascia, body.segmento) not in turni_ammessi(body.postazione):
                raise _errore(f"Turno {body.fascia}/{body.segmento} non valido per {body.postazione}")
            stesso_posto = [a for _, a in db.assegnazioni_periodo(conn, body.data, body.data)
                            if (a.postazione, a.fascia, a.ruolo) == (body.postazione, body.fascia, body.ruolo)]
            if body.postazione in POSTAZIONI_A_RICHIESTA:
                _verifica_posto_richiesto(conn, body, stesso_posto)
            elif any(si_sovrappongono(a.segmento, body.segmento) for a in stesso_posto):
                raise _errore("Il posto è già occupato in quella fascia")
            # stessa persona due volte nello stesso turno (Programmati: più posti uguali)
            if body.nome_volontario is not None:
                gia = {p["id"] for p in db.persone_per_nome(conn, body.nome_volontario)}
            else:
                gia = {body.persona_id}
            if any(a.persona_id in gia and si_sovrappongono(a.segmento, body.segmento) for a in stesso_posto):
                raise _errore("Questa persona è già assegnata a quel turno")
            if body.nome_volontario is not None:
                persona_id = _volontario_per_nome(conn, body.nome_volontario, body.ruolo)
                origine = "volontario"
            else:
                p = db.get_persona(conn, body.persona_id)
                if p is None:
                    raise HTTPException(404, "Persona non trovata")
                if not p["attivo"]:
                    raise _errore(f"{p['nome']} non è attivo: riattivalo in Personale per assegnarlo")
                if not db.a_persona(p).puo_ricoprire(body.ruolo, body.postazione):
                    raise _errore(f"{p['nome']} non è abilitato al ruolo di autista in {body.postazione}")
                persona_id = p["id"]
                origine = "volontario" if p["tipo"] == "volontario" else "manuale"
            db.crea_assegnazione(conn, Assegnazione(body.data, body.postazione, body.fascia, body.segmento,
                                                    body.ruolo, persona_id, origine))
            return payload_settimana(conn, inizio)

    @app.delete("/api/assegnazioni/{assegnazione_id}", status_code=204)
    def elimina_assegnazione(assegnazione_id: IdPath, conn: Conn):
        with scrittura():
            a = db.get_assegnazione(conn, assegnazione_id)
            if a is None:
                raise HTTPException(404, "Assegnazione non trovata")
            _verifica_modificabile(conn, lunedi(a.data))
            db.elimina_assegnazione(conn, assegnazione_id)
            return Response(status_code=204)

    @app.post("/api/settimane/{data}/genera")
    def genera_settimana(data: str, conn: Conn, body: GeneraIn | None = None):
        from . import solver  # import tardivo: OR-Tools è pesante

        with scrittura(attendi=False):
            inizio = lunedi(_data(data))
            _verifica_modificabile(conn, inizio)
            giorni, tipo, attive = _info_settimana(conn, inizio)
            fabbisogno = _fabbisogno_attivo(conn, giorni, tipo)
            dipendenti = db.dipendenti_attivi(conn)
            fissi = [a for _, a in db.assegnazioni_periodo(conn, giorni[0], giorni[-1]) if a.origine != "generato"]
            storico = calcola_storico([_settimana_passata(conn, r) for r in db.lista_settimane(conn, prima_di=inizio)])
            kwargs = {"tempo_max": body.tempo_max} if body and body.tempo_max else {}

            t0 = time.monotonic()
            ris = solver.genera(giorni, attive, dipendenti, fissi=fissi, contesto=_contesto(conn, giorni),
                                storico=storico, ferie=db.ferie_periodo(conn, giorni[0], giorni[-1]),
                                indisponibili=db.indisponibili_periodo(conn, giorni[0], giorni[-1]),
                                fabbisogno=fabbisogno, scarto_ore_max=db.get_scarto_ore_max(conn), **kwargs)
            durata = round(time.monotonic() - t0, 2)
            if ris.stato in ("impossibile", "nessuna_soluzione"):
                # niente da salvare: si tengono i turni generati in precedenza
                raise HTTPException(409, ris.messaggio)

            report = {
                "stato": ris.stato,
                "messaggio": ris.messaggio,
                "scoperti": [_unita_json(u) for u in ris.scoperti],
                "media_ore": ris.media_ore,
                "durata_s": durata,
            }
            nuove = [Assegnazione(a.data, a.postazione, a.fascia, a.segmento, a.ruolo, a.persona_id, "generato")
                     for a in ris.assegnazioni]
            db.salva_generazione(conn, giorni[0], giorni[-1], nuove, [p.id for p in dipendenti],
                                 datetime.now().isoformat(timespec="seconds"), report)
            return payload_settimana(conn, inizio)

    @app.post("/api/settimane/{data}/conferma")
    def conferma(data: str, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            db.imposta_stato(conn, inizio, "confermata")
            return payload_settimana(conn, inizio)

    @app.post("/api/settimane/{data}/riapri")
    def riapri(data: str, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            db.imposta_stato(conn, inizio, "bozza")
            return payload_settimana(conn, inizio)

    @app.delete("/api/settimane/{data}/generati")
    def elimina_generati(data: str, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            _verifica_modificabile(conn, inizio)
            db.elimina_generati(conn, inizio, inizio + timedelta(days=6))
            return payload_settimana(conn, inizio)

    # --- ferie ---
    @app.get("/api/ferie")
    def lista_ferie(conn: Conn):
        return db.lista_ferie(conn)

    @app.post("/api/ferie", status_code=201)
    def crea_ferie(body: FerieIn, conn: Conn):
        p = db.get_persona(conn, body.persona_id)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        if p["tipo"] != "dipendente":
            raise _errore("Le ferie si inseriscono solo per i dipendenti")
        if body.dal > body.al:
            raise _errore("La data di inizio delle ferie è dopo quella di fine")
        if (body.al - body.dal).days >= FERIE_GIORNI_MAX:
            raise _errore(f"Periodo di ferie troppo lungo (massimo {FERIE_GIORNI_MAX} giorni)")
        with scrittura():
            if db.ferie_sovrapposte(conn, body.persona_id, body.dal, body.al):
                raise _errore(f"{p['nome']} ha già ferie in quel periodo")
            return db.crea_ferie(conn, body.persona_id, body.dal, body.al)

    @app.delete("/api/ferie/{ferie_id}", status_code=204)
    def elimina_ferie(ferie_id: IdPath, conn: Conn):
        with scrittura():
            if not db.elimina_ferie(conn, ferie_id):
                raise HTTPException(404, "Ferie non trovate")
        return Response(status_code=204)

    # --- fabbisogno delle postazioni a richiesta ---
    @app.put("/api/settimane/{data}/fabbisogno")
    def imposta_fabbisogno(data: str, body: FabbisognoIn, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            _verifica_modificabile(conn, inizio)
            giorni, tipo, _ = _info_settimana(conn, inizio)
            if tipo != "A":
                raise _errore("Standby e Programmati esistono solo nelle settimane A")
            voci = []
            for v in body.voci:
                if v.data not in giorni:
                    raise _errore("La data del fabbisogno non appartiene a questa settimana")
                if v.postazione not in POSTAZIONI_A_RICHIESTA:
                    raise _errore(f"{v.postazione} non è una postazione a richiesta")
                if (v.fascia, v.segmento) not in TURNI_RICHIEDIBILI[v.postazione]:
                    raise _errore(f"Turno {v.fascia}/{v.segmento} non valido per {v.postazione}")
                if v.quantita > QUANTITA_MAX[v.postazione]:
                    raise _errore(f"Quantità non valida per {v.postazione} (massimo {QUANTITA_MAX[v.postazione]})")
                voci.append(Fabbisogno(v.data, v.postazione, v.fascia, v.segmento, v.ruolo, v.quantita))
            db.imposta_fabbisogno(conn, voci)
            return payload_settimana(conn, inizio)

    # --- indisponibilità ---
    @app.put("/api/settimane/{data}/indisponibilita")
    def imposta_indisponibilita(data: str, body: IndisponibilitaIn, conn: Conn):
        with scrittura():
            inizio = lunedi(_data(data))
            _verifica_modificabile(conn, inizio)
            giorni = giorni_settimana(inizio)
            p = db.get_persona(conn, body.persona_id)
            if p is None:
                raise HTTPException(404, "Persona non trovata")
            if p["tipo"] != "dipendente":
                raise _errore("Le indisponibilità si inseriscono solo per i dipendenti")
            if any(t.data not in giorni for t in body.turni):
                raise _errore("Le date di indisponibilità devono essere in questa settimana")
            db.imposta_indisponibilita(conn, body.persona_id, giorni[0], giorni[-1],
                                    [(t.data, t.parte) for t in body.turni])
            return payload_settimana(conn, inizio)

    # --- statistiche ---
    @app.get("/api/statistiche")
    def statistiche(conn: Conn):
        righe = db.lista_settimane(conn)
        passate = [_settimana_passata(conn, r) for r in righe]
        storico = calcola_storico(passate)
        persone = {p["id"]: p for p in db.lista_persone(conn)}

        out = []
        for pid, st in storico.items():
            p = persone.get(pid)
            if p is None:
                continue
            out.append({
                "persona_id": pid, "nome": p["nome"], "tipo": p["tipo"], "qualifica": p["qualifica"],
                "settimane": st.settimane, "ore_totali": st.ore_giorno + st.ore_notte,
                "saldo_ore": st.saldo_ore, "ore_giorno": st.ore_giorno, "ore_notte": st.ore_notte,
                "weekend": dict(st.weekend),
                "standby": st.richieste[STANDBY], "programmati": st.richieste[PROGRAMMATI],
            })

        volontari: dict[int, dict] = {}
        for s in passate:
            visti = set()
            for a in s.assegnazioni:
                p = persone.get(a.persona_id)
                if p is None or p["tipo"] != "volontario":
                    continue
                v = volontari.setdefault(a.persona_id, {
                    "persona_id": p["id"], "nome": p["nome"], "tipo": p["tipo"], "qualifica": p["qualifica"],
                    "settimane": 0, "ore_totali": 0, "saldo_ore": 0, "ore_giorno": 0, "ore_notte": 0,
                    "weekend": {k: 0 for k in CATEGORIE_WEEKEND}, "standby": 0, "programmati": 0,
                })
                if a.persona_id not in visti:
                    visti.add(a.persona_id)
                    v["settimane"] += 1
                v["ore_totali"] += a.ore
                v["ore_giorno" if a.fascia == "giorno" else "ore_notte"] += a.ore
                cat = categoria_weekend(a)
                if cat:
                    v["weekend"][cat] += 1
                chiave = {STANDBY: "standby", PROGRAMMATI: "programmati"}.get(a.postazione)
                if chiave:
                    v[chiave] += 1
        out += volontari.values()
        out.sort(key=lambda r: (r["tipo"] != "dipendente", r["nome"].lower(), r["persona_id"]))
        return out

    # --- statici ---
    app.mount("/static", StaticFiles(directory=STATIC_DIR, check_dir=False), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        indice = STATIC_DIR / "index.html"
        if not indice.is_file():
            raise HTTPException(404, "Frontend non disponibile")
        return FileResponse(indice)

    return app


def _app_predefinita() -> FastAPI:
    turso = os.environ.get("TURSO_DATABASE_URL")
    if turso:  # su Vercel il filesystem è in sola lettura: si usa Turso
        return create_app(turso)
    percorso = Path(os.environ.get("CVAP_DB", "data/turni.db"))
    percorso.parent.mkdir(parents=True, exist_ok=True)
    return create_app(str(percorso))


app = _app_predefinita()
