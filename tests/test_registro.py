"""Password master e registro delle azioni (cvap/registro.py)."""
import pytest
from fastapi.testclient import TestClient

from cvap import accesso, registro
from cvap.app import create_app

NORMALE, MASTER = "password-normale", "password-master"


@pytest.fixture
def app(tmp_path):
    return create_app(str(tmp_path / "t.db"), password=NORMALE, password_master=MASTER)


def _entra(app, password):
    c = TestClient(app)
    r = c.post("/api/accesso", json={"password": password})
    assert r.status_code == 200, r.text
    return c, r.json()


def test_le_due_password_aprono_il_sito_e_solo_la_master_e_master(app):
    normale, r = _entra(app, NORMALE)
    assert r["master"] is False and normale.get("/api/sessione").json()["master"] is False
    master, r = _entra(app, MASTER)
    assert r["master"] is True and master.get("/api/sessione").json()["master"] is True
    assert normale.get("/api/persone").status_code == 200
    assert master.get("/api/persone").status_code == 200


def test_il_registro_si_vede_solo_con_la_master(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    assert normale.get("/api/registro").status_code == 403
    assert TestClient(app).get("/api/registro").status_code == 401
    assert master.get("/api/registro").status_code == 200


def test_il_registro_contiene_le_azioni_di_entrambe_le_password(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    assert normale.post("/api/persone", json={"nome": "Mario", "tipo": "dipendente",
                                              "qualifica": "autista"}).status_code == 201
    master.post("/api/settimane/2026-10-19/conferma")
    normale.get("/api/persone")  # le letture non si registrano
    TestClient(app).post("/api/accesso", json={"password": "sbagliata"})
    righe = master.get("/api/registro").json()
    azioni = [(r["accesso"], r["descrizione"], r["esito"]) for r in righe]
    assert azioni == [
        ("anonimo", "Tentativo di accesso con password sbagliata", 401),
        ("master", "Conferma della settimana del 19/10/2026", 200),
        ("normale", "Persona aggiunta", 201),
        ("master", "Accesso", 200),
        ("normale", "Accesso", 200),
    ]
    solo_normale = master.get("/api/registro", params={"accesso": "normale"}).json()
    assert {r["accesso"] for r in solo_normale} == {"normale"}
    piu_vecchie = master.get("/api/registro", params={"prima_di": righe[1]["id"], "limite": 1}).json()
    assert [r["id"] for r in piu_vecchie] == [righe[2]["id"]]


def test_senza_accesso_non_si_registra_niente(app):
    assert TestClient(app).post("/api/persone", json={"nome": "X", "tipo": "dipendente",
                                                      "qualifica": "autista"}).status_code == 401
    master, _ = _entra(app, MASTER)
    assert [r["descrizione"] for r in master.get("/api/registro").json()] == ["Accesso"]


def test_il_ruolo_master_non_si_falsifica(app):
    normale, _ = _entra(app, NORMALE)
    scadenza, firma = normale.cookies.get(accesso.COOKIE).split(".")
    normale.cookies.set(accesso.COOKIE, f"{scadenza}.master.{firma}")
    assert normale.get("/api/persone").status_code == 401


def test_master_ignorata_senza_password_normale_o_se_uguale(tmp_path):
    aperto = TestClient(create_app(str(tmp_path / "a.db"), password_master=MASTER))
    assert aperto.get("/api/sessione").json()["master"] is False
    assert aperto.get("/api/registro").status_code == 403
    uguale = create_app(str(tmp_path / "b.db"), password=NORMALE, password_master=NORMALE)
    _, r = _entra(uguale, NORMALE)
    assert r["master"] is False


def test_sito_aperto_registra_le_azioni_come_aperto(tmp_path):
    from cvap import db
    percorso = str(tmp_path / "t.db")
    c = TestClient(create_app(percorso))
    c.post("/api/persone", json={"nome": "Mario", "tipo": "dipendente", "qualifica": "autista"})
    conn = db.apri(percorso)
    assert [(r["accesso"], r["descrizione"]) for r in registro.lista(conn)] == [("aperto", "Persona aggiunta")]
    conn.close()


def test_descrizioni():
    assert registro.descrivi("POST", "/api/settimane/2026-10-19/genera") == \
        "Generazione dei turni della settimana del 19/10/2026"
    assert registro.descrivi("DELETE", "/api/assegnazioni/42") == "Turno 42 tolto"
    assert registro.descrivi("POST", "/api/qualcosa") == "POST /api/qualcosa"
    assert not registro.da_registrare("POST", "/api/calendario-copertura/ferie/anteprima")
    assert not registro.da_registrare("GET", "/api/persone")
    assert registro.da_registrare("POST", "/api/ferie")
