"""Password del sito: con APP_PASSWORD le API chiedono l'accesso; senza, il sito resta aperto."""
import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

PASSWORD = "croce-verde-2026"


@pytest.fixture
def protetto(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db"), password=PASSWORD))


def test_senza_password_il_sito_resta_aperto(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db")))
    assert c.get("/api/persone").status_code == 200
    assert c.get("/api/sessione").json() == {"protetto": False, "autenticato": True}


def test_con_password_le_api_chiedono_l_accesso(protetto):
    r = protetto.get("/api/persone")
    assert r.status_code == 401
    assert protetto.post("/api/persone", json={"nome": "X", "tipo": "dipendente", "qualifica": "autista"}).status_code == 401
    assert protetto.get("/api/sessione").json() == {"protetto": True, "autenticato": False}


def test_la_pagina_e_i_file_statici_restano_raggiungibili(protetto):
    # la schermata di accesso deve potersi caricare
    assert protetto.get("/static/style.css").status_code == 200
    assert protetto.get("/").status_code == 200


def test_password_sbagliata(protetto):
    r = protetto.post("/api/accesso", json={"password": "sbagliata"})
    assert r.status_code == 401
    assert protetto.get("/api/persone").status_code == 401


def test_accesso_e_uscita(protetto):
    r = protetto.post("/api/accesso", json={"password": PASSWORD})
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert protetto.get("/api/persone").status_code == 200
    assert protetto.get("/api/sessione").json() == {"protetto": True, "autenticato": True}
    assert protetto.post("/api/uscita").status_code == 204
    assert protetto.get("/api/persone").status_code == 401


def test_cookie_falsificato_non_vale(protetto):
    protetto.cookies.set("cvap_sessione", "9999999999.abcdef")
    assert protetto.get("/api/persone").status_code == 401


def test_cambiare_password_invalida_le_sessioni(tmp_path):
    percorso = str(tmp_path / "t.db")
    vecchio = TestClient(create_app(percorso, password="vecchia-password"))
    vecchio.post("/api/accesso", json={"password": "vecchia-password"})
    nuovo = TestClient(create_app(percorso, password="nuova-password"))
    nuovo.cookies = vecchio.cookies
    assert nuovo.get("/api/persone").status_code == 401


def test_la_documentazione_dell_api_e_nascosta_con_la_password(protetto):
    assert protetto.get("/docs").status_code == 404
    assert protetto.get("/openapi.json").status_code == 404


def test_il_cookie_non_dipende_solo_dalla_password(tmp_path):
    # stessa password, database diverso: il segreto casuale salvato nel database cambia la firma
    a = TestClient(create_app(str(tmp_path / "a.db"), password=PASSWORD))
    b = TestClient(create_app(str(tmp_path / "b.db"), password=PASSWORD))
    a.post("/api/accesso", json={"password": PASSWORD})
    b.cookies = a.cookies
    assert b.get("/api/persone").status_code == 401
