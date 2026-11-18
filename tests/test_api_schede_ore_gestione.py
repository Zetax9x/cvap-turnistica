"""API di gestione delle schede ore per la master: codici, elenco del mese, riapertura, download."""
import io
import os
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import db, db_schede_ore  # noqa: E402
from cvap.app import create_app  # noqa: E402

MESE = date.today().strftime("%Y-%m")
PUBBLICA = "/api/schede-ore"
GESTIONE = "/api/schede-ore-gestione"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
GIORNO_OK = {"ferie": 0, "colonne": {"ascoli": ["8", "20"]}, "note": "", "disponibilita": None}


@pytest.fixture(params=["sqlite", "libsql"])
def ambiente(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    percorso = str(tmp_path / "t.db")
    return TestClient(create_app(percorso)), percorso


@pytest.fixture
def client(ambiente):
    return ambiente[0]


@pytest.fixture
def conn(ambiente):
    c = db.apri(ambiente[1])
    yield c
    c.close()


@pytest.fixture
def mario(conn):
    return db.crea_persona(conn, "Mario Rossi", "dipendente", "autista")["id"]


def entra(client, pid, codice):
    return client.post(f"{PUBBLICA}/accesso", json={"persona_id": pid, "codice": codice})


# --- codici ------------------------------------------------------------------------------

def test_imposta_codice_e_il_dipendente_entra(client, mario):
    assert client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "codice1"}).status_code == 204
    assert entra(client, mario, "codice1").status_code == 200
    assert entra(client, mario, "altro").status_code == 401


@pytest.mark.parametrize("codice", ["abc", "12345", ""])
def test_codice_troppo_corto_422(client, mario, codice):
    assert client.put(f"{GESTIONE}/codici/{mario}", json={"codice": codice}).status_code == 422


def test_persone_non_valide_404(client, conn):
    volontario = db.crea_persona(conn, "Vol Carla", "volontario", "soccorritore")["id"]
    for pid in (9999, volontario):
        assert client.put(f"{GESTIONE}/codici/{pid}", json={"codice": "codice1"}).status_code == 404
        assert client.delete(f"{GESTIONE}/codici/{pid}").status_code == 404
        assert client.post(f"{GESTIONE}/codici/{pid}/genera").status_code == 404
        assert client.post(f"{GESTIONE}/{MESE}/{pid}/riapri").status_code == 404
        assert client.get(f"{GESTIONE}/{MESE}/{pid}.xlsx").status_code == 404


def test_genera_codice_casuale_e_vale_subito(client, mario):
    r = client.post(f"{GESTIONE}/codici/{mario}/genera")
    assert r.status_code == 200
    codice = r.json()["codice"]
    assert len(codice) == 8 and codice.isalnum() and codice == codice.upper()
    assert entra(client, mario, codice).status_code == 200
    assert client.post(f"{GESTIONE}/codici/{mario}/genera").json()["codice"] != codice


def test_azzera_codice(client, mario):
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "codice1"})
    assert client.delete(f"{GESTIONE}/codici/{mario}").status_code == 204
    assert entra(client, mario, "codice1").status_code == 403


def test_nuovo_codice_sostituisce_il_vecchio_e_sblocca(client, mario):
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "vecchio1"})
    for _ in range(5):
        entra(client, mario, "no")
    assert entra(client, mario, "vecchio1").status_code == 429
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "nuovo22"})
    assert entra(client, mario, "vecchio1").status_code == 401
    assert entra(client, mario, "nuovo22").status_code == 200


# --- elenco, download, riapertura --------------------------------------------------------

def test_elenco_del_mese_con_gli_stati(client, conn, mario):
    anna = db.crea_persona(conn, "Anna Neri", "dipendente", "soccorritore")["id"]
    db.crea_persona(conn, "Vol Carla", "volontario", "soccorritore")
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "codice1"})
    elenco = {r["nome"]: r for r in client.get(f"{GESTIONE}/{MESE}").json()}
    assert set(elenco) == {"Mario Rossi", "Anna Neri"}
    assert elenco["Mario Rossi"]["stato"] == "non_aperta" and elenco["Mario Rossi"]["ha_codice"] is True
    assert elenco["Anna Neri"]["ha_codice"] is False
    entra(client, mario, "codice1")
    client.put(f"{PUBBLICA}/{MESE}/note", json={"note": "x"})
    assert {r["nome"]: r["stato"] for r in client.get(f"{GESTIONE}/{MESE}").json()}["Mario Rossi"] == "bozza"
    client.post(f"{PUBBLICA}/{MESE}/conferma")
    voce = {r["nome"]: r for r in client.get(f"{GESTIONE}/{MESE}").json()}["Mario Rossi"]
    assert voce["stato"] == "confermata" and voce["confermata_il"] and voce["persona_id"] == mario
    assert anna  # presente e non aperta


def test_mese_non_valido_422(client):
    assert client.get(f"{GESTIONE}/2026-13").status_code == 422
    assert client.get(f"{GESTIONE}/boh").status_code == 422


def test_download_solo_se_confermata(client, mario):
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "codice1"})
    entra(client, mario, "codice1")
    client.put(f"{PUBBLICA}/{MESE}/giorni/3", json=GIORNO_OK)
    assert client.get(f"{GESTIONE}/{MESE}/{mario}.xlsx").status_code == 409
    client.post(f"{PUBBLICA}/{MESE}/conferma")
    r = client.get(f"{GESTIONE}/{MESE}/{mario}.xlsx")
    assert r.status_code == 200 and r.headers["content-type"] == XLSX
    assert f'filename="scheda-ore-mario-rossi-{MESE}.xlsx"' in r.headers["content-disposition"]
    assert "xl/worksheets/sheet1.xml" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()


def test_riapri_rimette_in_bozza_e_il_dipendente_puo_modificare(client, mario):
    client.put(f"{GESTIONE}/codici/{mario}", json={"codice": "codice1"})
    entra(client, mario, "codice1")
    client.put(f"{PUBBLICA}/{MESE}/giorni/3", json=GIORNO_OK)
    assert client.post(f"{GESTIONE}/{MESE}/{mario}/riapri").status_code == 409       # non è confermata
    client.post(f"{PUBBLICA}/{MESE}/conferma")
    assert client.put(f"{PUBBLICA}/{MESE}/note", json={"note": "no"}).status_code == 409
    assert client.post(f"{GESTIONE}/{MESE}/{mario}/riapri").status_code == 204
    assert client.put(f"{PUBBLICA}/{MESE}/note", json={"note": "dopo"}).status_code == 200
    s = client.get(f"{PUBBLICA}/{MESE}").json()
    assert s["stato"] == "bozza" and s["giorni"][2]["corretto"] is True               # le correzioni restano


def test_nessuna_cache(client, mario):
    assert "no-store" in client.get(f"{GESTIONE}/{MESE}").headers["cache-control"]
    assert "no-store" in client.post(f"{GESTIONE}/codici/{mario}/genera").headers["cache-control"]


# --- master e password normale -----------------------------------------------------------

@pytest.fixture
def siti(tmp_path):
    percorso = str(tmp_path / "t.db")
    app = create_app(percorso, password="normale1", password_master="master1")
    master, normale = TestClient(app), TestClient(app)
    assert master.post("/api/accesso", json={"password": "master1"}).status_code == 200
    assert normale.post("/api/accesso", json={"password": "normale1"}).status_code == 200
    c = db.apri(percorso)
    pid = db.crea_persona(c, "Mario Rossi", "dipendente", "autista")["id"]
    c.close()
    return master, normale, pid


def chiamate(pid):
    return [("PUT", f"{GESTIONE}/codici/{pid}", {"codice": "codice1"}), ("DELETE", f"{GESTIONE}/codici/{pid}", None),
            ("POST", f"{GESTIONE}/codici/{pid}/genera", None), ("GET", f"{GESTIONE}/{MESE}", None),
            ("GET", f"{GESTIONE}/{MESE}/{pid}.xlsx", None), ("POST", f"{GESTIONE}/{MESE}/{pid}/riapri", None)]


def test_la_password_normale_non_arriva_alla_gestione_se_esiste_la_master(siti):
    master, normale, pid = siti
    for metodo, url, corpo in chiamate(pid):
        r = normale.request(metodo, url, json=corpo)
        assert r.status_code == 403, (metodo, url, r.status_code)
    assert master.put(f"{GESTIONE}/codici/{pid}", json={"codice": "codice1"}).status_code == 204
    assert master.get(f"{GESTIONE}/{MESE}").status_code == 200
    assert master.post(f"{GESTIONE}/codici/{pid}/genera").status_code == 200


def test_senza_login_la_gestione_e_chiusa(siti, tmp_path):
    _, _, pid = siti
    anonimo = TestClient(create_app(str(tmp_path / "t.db"), password="normale1", password_master="master1"))
    for metodo, url, corpo in chiamate(pid):
        assert anonimo.request(metodo, url, json=corpo).status_code == 401, url


def test_il_registro_descrive_le_azioni_e_non_contiene_mai_il_codice(siti, tmp_path):
    master, _, pid = siti
    master.put(f"{GESTIONE}/codici/{pid}", json={"codice": "segretissimo9"})
    generato = master.post(f"{GESTIONE}/codici/{pid}/genera").json()["codice"]
    master.delete(f"{GESTIONE}/codici/{pid}")
    assert master.put(f"{GESTIONE}/codici/{pid}", json={"codice": "q7z"}).status_code == 422   # troppo corto
    master.post(f"{PUBBLICA}/accesso", json={"persona_id": pid, "codice": generato})  # accesso pubblico, non in registro
    righe = master.get("/api/registro").json()
    testo = str(righe)
    assert "segretissimo9" not in testo and generato not in testo and "q7z" not in testo
    descrizioni = [r["descrizione"] for r in righe]
    assert any("Codice scheda ore di Mario Rossi impostato" in d for d in descrizioni)
    assert any("Codice scheda ore di Mario Rossi generato" in d for d in descrizioni)
    assert any("Codice scheda ore di Mario Rossi azzerato" in d for d in descrizioni)


def test_la_riapertura_e_nel_registro(siti):
    master, _, pid = siti
    master.put(f"{GESTIONE}/codici/{pid}", json={"codice": "codice1"})
    assert master.post(f"{PUBBLICA}/accesso", json={"persona_id": pid, "codice": "codice1"}).status_code == 200
    master.post(f"{PUBBLICA}/{MESE}/conferma")
    assert master.post(f"{GESTIONE}/{MESE}/{pid}/riapri").status_code == 204
    descrizioni = [r["descrizione"] for r in master.get("/api/registro").json()]
    assert any("Scheda ore di Mario Rossi riaperta" in d and MESE in d for d in descrizioni)


def test_senza_la_master_la_password_normale_ha_accesso_completo(tmp_path):
    percorso = str(tmp_path / "t.db")
    client = TestClient(create_app(percorso, password="normale1"))
    assert client.post("/api/accesso", json={"password": "normale1"}).status_code == 200
    c = db.apri(percorso)
    pid = db.crea_persona(c, "Mario Rossi", "dipendente", "autista")["id"]
    c.close()
    assert client.put(f"{GESTIONE}/codici/{pid}", json={"codice": "codice1"}).status_code == 204
    assert client.get(f"{GESTIONE}/{MESE}").status_code == 200
