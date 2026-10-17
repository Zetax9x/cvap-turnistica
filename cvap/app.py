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

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StringConstraints

from . import db
from .calendario import giorni_settimana, lunedi, postazioni_attive, tipo_settimana
from .modello import Assegnazione, Persona
from .storico import CATEGORIE_WEEKEND, SettimanaPassata, calcola_storico, categoria_weekend
from .vincoli import valida_settimana

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
GIORNI_CONTESTO = 3
DATA_MIN, DATA_MAX = date(2000, 1, 1), date(2100, 12, 31)
DataValida = Annotated[date, Field(ge=DATA_MIN, le=DATA_MAX)]

_SOVRAPPOSTI = {
    "intero": {"intero", "mattina", "pomeriggio"},
    "mattina": {"intero", "mattina"},
    "pomeriggio": {"intero", "pomeriggio"},
}

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Tipo = Literal["dipendente", "volontario"]
Qualifica = Literal["autista", "soccorritore"]


class PersonaIn(BaseModel):
    nome: Nome
    tipo: Tipo
    qualifica: Qualifica


class PersonaUpdate(PersonaIn):
    attivo: bool = True


class ImpostazioniIn(BaseModel):
    data_riferimento_a: DataValida


class AssegnazioneIn(BaseModel):
    data: DataValida
    postazione: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    fascia: Literal["giorno", "notte"]
    segmento: Literal["intero", "mattina", "pomeriggio"]
    ruolo: Literal["autista", "soccorritore"]
    persona_id: int


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


def payload_settimana(conn: sqlite3.Connection, inizio: date) -> dict:
    giorni, tipo, attive = _info_settimana(conn, inizio)
    righe = db.assegnazioni_periodo(conn, giorni[0], giorni[-1])
    assegnazioni = [a for _, a in righe]
    persone = {p["id"]: p for p in db.lista_persone(conn)}
    presenti = {a.persona_id for a in assegnazioni}

    # volontari + dipendenti attivi + chiunque (anche disattivato) abbia turni questa settimana
    rilevanti = {pid: db.a_persona(p) for pid, p in persone.items()
                 if p["tipo"] == "volontario" or p["attivo"] or pid in presenti}
    violazioni = valida_settimana(giorni, attive, assegnazioni, rilevanti, contesto=_contesto(conn, giorni))

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
        })
    riepilogo.sort(key=lambda r: (r["tipo"] != "dipendente", r["nome"].lower(), r["persona_id"]))

    ids_attivi = {p["id"] for p in dipendenti_attivi}
    ore_dip = sum(a.ore for a in assegnazioni if a.persona_id in ids_attivi)
    media = ore_dip / len(ids_attivi) if ids_attivi else 0

    riga = db.get_settimana(conn, giorni[0])
    return {
        "inizio": giorni[0].isoformat(),
        "fine": giorni[-1].isoformat(),
        "tipo": tipo,
        "stato": riga["stato"] if riga else "nuova",
        "giorni": [g.isoformat() for g in giorni],
        "postazioni": attive,
        "assegnazioni": [{
            "id": aid, "data": a.data.isoformat(), "postazione": a.postazione, "fascia": a.fascia,
            "segmento": a.segmento, "ruolo": a.ruolo, "persona_id": a.persona_id,
            "persona_nome": persone[a.persona_id]["nome"] if a.persona_id in persone else f"#{a.persona_id}",
            "origine": a.origine, "ore": a.ore,
        } for aid, a in righe],
        "violazioni": [{"livello": v.livello, "codice": v.codice, "messaggio": v.messaggio,
                        "persona_id": v.persona_id, "data": _iso(v.data)} for v in violazioni],
        "riepilogo": riepilogo,
        "media_ore": media,
        "report": riga["report"] if riga else None,
    }


def _settimana_passata(conn, riga: dict) -> SettimanaPassata:
    inizio = date.fromisoformat(riga["inizio"])
    assegnazioni = [a for _, a in db.assegnazioni_periodo(conn, inizio, inizio + timedelta(days=6))]
    dipendenti = list(riga["dipendenti"])
    presenti = set(dipendenti)
    ore = sum(a.ore for a in assegnazioni if a.persona_id in presenti)
    media = ore / len(dipendenti) if dipendenti else 0.0
    return SettimanaPassata(media_ore=media, dipendenti=dipendenti, assegnazioni=assegnazioni)


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
        return db.crea_persona(conn, body.nome, body.tipo, body.qualifica)

    @app.put("/api/persone/{persona_id}")
    def aggiorna_persona(persona_id: int, body: PersonaUpdate, conn: Conn):
        p = db.aggiorna_persona(conn, persona_id, body.nome, body.tipo, body.qualifica, body.attivo)
        if p is None:
            raise HTTPException(404, "Persona non trovata")
        return p

    @app.delete("/api/persone/{persona_id}", status_code=204)
    def elimina_persona(persona_id: int, conn: Conn):
        if not db.elimina_persona(conn, persona_id):
            raise HTTPException(404, "Persona non trovata")
        return Response(status_code=204)

    # --- postazioni / impostazioni ---
    @app.get("/api/postazioni")
    def lista_postazioni(conn: Conn):
        return db.lista_postazioni(conn)

    @app.get("/api/impostazioni")
    def get_impostazioni(conn: Conn):
        return {"data_riferimento_a": db.get_riferimento_a(conn).isoformat()}

    @app.put("/api/impostazioni")
    def put_impostazioni(body: ImpostazioniIn, conn: Conn):
        return {"data_riferimento_a": db.set_riferimento_a(conn, body.data_riferimento_a).isoformat()}

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
            if body.postazione not in attive:
                raise _errore(f"La postazione {body.postazione} non è attiva nella settimana {tipo}")
            if body.fascia == "notte" and body.segmento != "intero":
                raise _errore("Il turno di notte non si può spezzare in mattina/pomeriggio")
            p = db.get_persona(conn, body.persona_id)
            if p is None:
                raise HTTPException(404, "Persona non trovata")
            if not p["attivo"]:
                raise _errore(f"{p['nome']} non è attivo: riattivalo in Personale per assegnarlo")
            if not db.a_persona(p).puo_ricoprire(body.ruolo):
                raise _errore(f"{p['nome']} non è abilitato al ruolo di autista")
            nuova = Assegnazione(body.data, body.postazione, body.fascia, body.segmento, body.ruolo,
                                 body.persona_id, "volontario" if p["tipo"] == "volontario" else "manuale")
            for _, a in db.assegnazioni_periodo(conn, body.data, body.data):
                if a.chiave == nuova.chiave and a.segmento in _SOVRAPPOSTI[nuova.segmento]:
                    raise _errore("Il posto è già occupato in quella fascia")
            db.crea_assegnazione(conn, nuova)
            return payload_settimana(conn, inizio)

    @app.delete("/api/assegnazioni/{assegnazione_id}", status_code=204)
    def elimina_assegnazione(assegnazione_id: int, conn: Conn):
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
            giorni, _, attive = _info_settimana(conn, inizio)
            dipendenti = db.dipendenti_attivi(conn)
            fissi = [a for _, a in db.assegnazioni_periodo(conn, giorni[0], giorni[-1]) if a.origine != "generato"]
            storico = calcola_storico([_settimana_passata(conn, r) for r in db.lista_settimane(conn, prima_di=inizio)])
            kwargs = {"tempo_max": body.tempo_max} if body and body.tempo_max else {}

            t0 = time.monotonic()
            ris = solver.genera(giorni, attive, dipendenti, fissi=fissi, contesto=_contesto(conn, giorni),
                                storico=storico, **kwargs)
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
                    "weekend": {k: 0 for k in CATEGORIE_WEEKEND},
                })
                if a.persona_id not in visti:
                    visti.add(a.persona_id)
                    v["settimane"] += 1
                v["ore_totali"] += a.ore
                v["ore_giorno" if a.fascia == "giorno" else "ore_notte"] += a.ore
                cat = categoria_weekend(a)
                if cat:
                    v["weekend"][cat] += 1
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
    percorso = Path(os.environ.get("CVAP_DB", "data/turni.db"))
    percorso.parent.mkdir(parents=True, exist_ok=True)
    return create_app(str(percorso))


app = _app_predefinita()
