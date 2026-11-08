"""Notifiche push: chiave del server, iscrizione di un dispositivo, prova e avviso dei cambi turno."""
import json
import threading
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cvap import db, push
from cvap.app import create_app
from cvap.modello import Assegnazione

ISCRIZIONE = {"endpoint": "https://web.push.apple.com/abc123", "keys": {"p256dh": "BNc" + "x" * 80, "auth": "authsegreto"}}


@pytest.fixture
def inviate(monkeypatch):
    """Sostituisce l'invio vero: registra (iscrizione, contenuto) invece di contattare il servizio push."""
    lista = []
    monkeypatch.setattr(push, "_spedisci", lambda sott, payload, pem: lista.append((sott, json.loads(payload))))
    return lista


def attendi_invii():
    for t in [t for t in threading.enumerate() if t.name == "push"]:
        t.join(timeout=5)


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def test_chiave_pubblica_valida_e_stabile(client):
    a = client.get("/api/push").json()
    assert a["iscritto"] is False
    assert len(a["chiave"]) == 87  # 65 byte (punto non compresso) in base64 url senza riempimento
    assert client.get("/api/push").json()["chiave"] == a["chiave"]  # la stessa a ogni richiesta: cambiarla rompe l'iscrizione


def test_iscrizione_sostituzione_e_rimozione(client, inviate):
    assert client.put("/api/push/iscrizione", json=ISCRIZIONE).json() == {"iscritto": True}
    assert client.get("/api/push").json()["iscritto"] is True
    # un solo dispositivo: la nuova iscrizione prende il posto della vecchia
    nuova = {**ISCRIZIONE, "endpoint": "https://web.push.apple.com/nuovo"}
    client.put("/api/push/iscrizione", json=nuova)
    client.post("/api/push/prova")
    assert [s["endpoint"] for s, _ in inviate] == [nuova["endpoint"]]
    assert client.delete("/api/push/iscrizione").status_code == 204
    assert client.get("/api/push").json()["iscritto"] is False


def test_iscrizione_non_valida_respinta(client):
    assert client.put("/api/push/iscrizione", json={**ISCRIZIONE, "endpoint": "http://non-sicuro.example"}).status_code == 422
    assert client.put("/api/push/iscrizione", json={"endpoint": ISCRIZIONE["endpoint"]}).status_code == 422


def test_prova_senza_iscrizione_e_con_iscrizione(client, inviate):
    r = client.post("/api/push/prova")
    assert r.status_code == 400 and "iscritto" in r.json()["detail"] and not inviate
    client.put("/api/push/iscrizione", json=ISCRIZIONE)
    assert client.post("/api/push/prova").json() == {"inviata": True}
    sott, contenuto = inviate[0]
    assert sott["endpoint"] == ISCRIZIONE["endpoint"] and sott["keys"]["auth"] == "authsegreto"
    assert contenuto["url"].startswith("/app/")


def test_iscrizione_scaduta_viene_tolta(client, monkeypatch):
    def scaduta(*_):
        raise push.IscrizioneScaduta()
    monkeypatch.setattr(push, "_spedisci", scaduta)
    client.put("/api/push/iscrizione", json=ISCRIZIONE)
    r = client.post("/api/push/prova")
    assert r.status_code == 400 and "riattiva" in r.json()["detail"]
    assert client.get("/api/push").json()["iscritto"] is False


def test_le_api_push_chiedono_la_password(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db"), password="segreta"))
    assert c.get("/api/push").status_code == 401
    assert c.post("/api/push/prova").status_code == 401


# ---------------------------------------------------------------- cambio turno

@pytest.fixture
def scenario(tmp_path):
    path = str(tmp_path / "cambi.db")
    c = TestClient(create_app(path))
    conn = db.apri(path)
    a = db.crea_persona(conn, "Anna", "dipendente", "autista")["id"]
    b = db.crea_persona(conn, "Bruno", "dipendente", "autista")["id"]
    primo = db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), "Acquasanta", "giorno", "intero", "autista", a))
    secondo = db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 16), "Venarotta", "giorno", "intero", "soccorritore", b))
    db.imposta_stato(conn, date(2090, 1, 2), "confermata")
    yield c, {"tipo": "scambio", "persona_id": a, "collega_id": b, "turno_id": primo, "turno_ricevuto_id": secondo}
    conn.close()


def registra(c, corpo, chiave, versione=None):
    versione = versione or c.post("/api/cambi-turno/anteprima", json=corpo).json()["versione"]
    return c.post("/api/cambi-turno/conferme", json={**corpo, "versione": versione, "chiave": chiave})


def test_il_cambio_turno_avvisa_una_sola_volta(scenario, inviate):
    c, corpo = scenario
    c.put("/api/push/iscrizione", json=ISCRIZIONE)
    chiave = str(uuid4())
    versione = c.post("/api/cambi-turno/anteprima", json=corpo).json()["versione"]
    assert registra(c, corpo, chiave, versione).status_code == 200
    attendi_invii()
    assert len(inviate) == 1
    assert inviate[0][1]["titolo"] == "Cambio turno registrato"
    assert inviate[0][1]["url"] == "/app/#/altro/cambi"
    # stessa chiave: è lo stesso cambio (risposta persa e rinviata), non si riavvisa
    ripetizione = registra(c, corpo, chiave, versione)
    assert ripetizione.status_code == 200  # stessa richiesta: restituisce quanto già registrato
    attendi_invii()
    assert len(inviate) == 1


def test_senza_dispositivo_il_cambio_turno_funziona_lo_stesso(scenario, inviate):
    c, corpo = scenario
    assert registra(c, corpo, str(uuid4())).status_code == 200
    attendi_invii()
    assert inviate == []


def test_un_errore_di_invio_non_rompe_il_cambio_turno(scenario, monkeypatch):
    def rotta(*_):
        raise RuntimeError("servizio push non raggiungibile")
    monkeypatch.setattr(push, "_spedisci", rotta)
    c, corpo = scenario
    c.put("/api/push/iscrizione", json=ISCRIZIONE)
    assert registra(c, corpo, str(uuid4())).status_code == 200
    attendi_invii()
