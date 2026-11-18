"""API della scheda ore del dipendente: accesso con nome e codice, correzioni, conferma, download."""
import io
import os
import time
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import api_schede_ore, db, db_schede_ore  # noqa: E402
from cvap.app import create_app  # noqa: E402
from cvap.modello import Assegnazione  # noqa: E402
from cvap.scheda_ore import giorni_del_mese, mesi_apribili  # noqa: E402

OGGI = date.today()
MESE = OGGI.strftime("%Y-%m")
URL = "/api/schede-ore"
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


def dipendente(conn, nome, codice="codice1", tipo="dipendente"):
    pid = db.crea_persona(conn, nome, tipo, "autista")["id"]
    if codice:
        db_schede_ore.imposta_codice(conn, pid, codice)
    return pid


@pytest.fixture
def mario(conn):
    return dipendente(conn, "Mario Rossi")


def entra(client, pid, codice="codice1"):
    return client.post(f"{URL}/accesso", json={"persona_id": pid, "codice": codice})


def mese_con_giorni(n):
    return next(m for m in mesi_apribili(OGGI) if giorni_del_mese(m) == n)


# --- accesso -----------------------------------------------------------------------------

def test_elenco_dipendenti_senza_accesso(client, conn, mario):
    dipendente(conn, "Anna Neri")
    dipendente(conn, "Vol Carla", tipo="volontario")
    inattivo = dipendente(conn, "Ex Dino")
    db.aggiorna_persona(conn, inattivo, "Ex Dino", "dipendente", "autista", False, None, db.INVARIATA)
    r = client.get(f"{URL}/dipendenti")
    assert r.status_code == 200
    assert r.json() == [{"id": db.lista_persone(conn)[0]["id"], "nome": "Anna Neri"}, {"id": mario, "nome": "Mario Rossi"}]


def test_accesso_corretto_imposta_il_cookie_sicuro(client, mario):
    r = entra(client, mario)
    assert r.status_code == 200 and r.json() == {"persona_id": mario, "nome": "Mario Rossi"}
    cookie = r.headers["set-cookie"].lower()
    assert "cvap_scheda=" in cookie and "httponly" in cookie and "samesite=strict" in cookie
    assert "path=/api/schede-ore" in cookie and "max-age=7200" in cookie


def test_nome_o_codice_errati_hanno_la_stessa_risposta(client, conn, mario):
    volontario = dipendente(conn, "Vol Carla", tipo="volontario")
    inattivo = dipendente(conn, "Ex Dino")
    db.aggiorna_persona(conn, inattivo, "Ex Dino", "dipendente", "autista", False, None, db.INVARIATA)
    risposte = [entra(client, mario, "sbagliato"), entra(client, 9999), entra(client, volontario),
                entra(client, inattivo)]
    assert [r.status_code for r in risposte] == [401] * 4
    assert all(r.json() == {"detail": "Nome o codice non corretti"} for r in risposte)
    assert "set-cookie" not in risposte[0].headers


def test_dopo_cinque_errori_anche_il_codice_giusto_e_bloccato(client, mario):
    for _ in range(5):
        assert entra(client, mario, "no").status_code == 401
    r = entra(client, mario)
    assert r.status_code == 429 and "riprova tra" in r.json()["detail"]


def test_senza_codice_impostato(client, conn):
    pid = dipendente(conn, "Bruno Verdi", codice=None)
    r = entra(client, pid)
    assert r.status_code == 403 and "chiedilo ai responsabili" in r.json()["detail"]


def test_senza_cookie_tutto_e_negato_tranne_elenco_accesso_e_uscita(client, mario):
    assert client.get(f"{URL}/dipendenti").status_code == 200
    assert client.post(f"{URL}/uscita").status_code in (200, 204)
    assert client.get(f"{URL}/mesi").status_code == 401
    assert client.get(f"{URL}/{MESE}").status_code == 401
    assert client.get(f"{URL}/{MESE}.xlsx").status_code == 401
    assert client.put(f"{URL}/{MESE}/giorni/3", json=GIORNO_OK).status_code == 401
    assert client.delete(f"{URL}/{MESE}/giorni/3").status_code == 401
    assert client.put(f"{URL}/{MESE}/note", json={"note": "x"}).status_code == 401
    assert client.post(f"{URL}/{MESE}/conferma").status_code == 401


def test_cookie_scaduto_manomesso_o_falsificato(ambiente, conn, mario):
    client, _ = ambiente
    anna = dipendente(conn, "Anna Neri", "codice2")
    chiave = api_schede_ore.chiave_scheda(db.segreto_sessione(conn))
    adesso = time.time()
    valido = api_schede_ore.crea_cookie(chiave, mario, adesso)
    scaduto = api_schede_ore.crea_cookie(chiave, mario, adesso - 7201)
    manomesso = valido[:-1] + ("0" if valido[-1] != "0" else "1")
    # il cookie di Anna con l'id di Mario al posto del suo: la firma non torna
    falsificato = api_schede_ore.crea_cookie(chiave, anna, adesso).replace(f"{anna}.", f"{mario}.", 1)
    for cookie, atteso in ((valido, 200), (scaduto, 401), (manomesso, 401), (falsificato, 401), ("", 401), ("a.b.c", 401)):
        r = client.get(f"{URL}/mesi", headers={"Cookie": f"cvap_scheda={cookie}"})
        assert r.status_code == atteso, cookie
    assert api_schede_ore.persona_dal_cookie(chiave, valido, adesso) == mario
    assert api_schede_ore.persona_dal_cookie(chiave, scaduto, adesso) is None


def test_ognuno_vede_solo_la_propria_scheda(client, conn, mario):
    anna = dipendente(conn, "Anna Neri", "codice2")
    db.crea_assegnazione(conn, Assegnazione(date(OGGI.year, OGGI.month, 10), "Acquasanta", "giorno", "intero",
                                            "autista", mario, "generato"))
    entra(client, anna, "codice2")
    s = client.get(f"{URL}/{MESE}").json()
    assert s["persona"]["nome"] == "Anna Neri" and s["totali"]["totale_mese"] == 0
    client.cookies.clear()
    entra(client, mario)
    assert client.get(f"{URL}/{MESE}").json()["totali"]["ore_postazioni"] == 12


def test_un_dipendente_disattivato_dopo_l_accesso_perde_l_accesso(client, conn, mario):
    entra(client, mario)
    assert client.get(f"{URL}/mesi").status_code == 200
    db.aggiorna_persona(conn, mario, "Mario Rossi", "dipendente", "autista", False, None, db.INVARIATA)
    assert client.get(f"{URL}/mesi").status_code == 401


def test_uscita_toglie_il_cookie(client, mario):
    entra(client, mario)
    assert client.get(f"{URL}/mesi").status_code == 200
    assert client.post(f"{URL}/uscita").status_code in (200, 204)
    assert client.get(f"{URL}/mesi").status_code == 401


# --- mesi --------------------------------------------------------------------------------

def test_i_mesi_apribili_sono_13_con_lo_stato(client, mario):
    entra(client, mario)
    client.put(f"{URL}/{MESE}/note", json={"note": "x"})
    mesi = client.get(f"{URL}/mesi").json()
    assert [m["mese"] for m in mesi] == mesi_apribili(OGGI)
    assert mesi[0]["stato"] == "bozza" and mesi[1]["stato"] == "non_aperta"


def test_mesi_non_apribili_o_non_validi(client, mario):
    entra(client, mario)
    prossimo = f"{OGGI.year + (OGGI.month == 12)}-{OGGI.month % 12 + 1:02d}"
    quattordici_fa = f"{OGGI.year - 1 - (OGGI.month == 1)}-{(OGGI.month - 2) % 12 + 1:02d}"
    assert client.get(f"{URL}/{prossimo}").status_code == 404
    assert client.get(f"{URL}/{quattordici_fa}").status_code == 404
    assert client.get(f"{URL}/{mesi_apribili(OGGI)[-1]}").status_code == 200
    for sbagliato in ("2026-13", "2026-00", "abcdefg", "2026-1", "26-11"):
        assert client.get(f"{URL}/{sbagliato}").status_code == 422, sbagliato


# --- correzioni --------------------------------------------------------------------------

def test_correzione_di_un_giorno_e_ripristino(client, mario):
    entra(client, mario)
    r = client.put(f"{URL}/{MESE}/giorni/3", json=GIORNO_OK)
    assert r.status_code == 200
    g = r.json()["giorni"][2]
    assert g["colonne"]["ascoli"] == [8.0, 20.0] and g["corretto"] is True
    assert r.json()["totali"]["ore_postazioni"] == 12
    assert client.get(f"{URL}/{MESE}").json()["giorni"][2]["corretto"] is True
    r = client.delete(f"{URL}/{MESE}/giorni/3")
    assert r.status_code == 200 and r.json()["giorni"][2]["corretto"] is False and r.json()["totali"]["ore_postazioni"] == 0


def test_correzioni_non_valide(client, mario):
    entra(client, mario)
    mese30 = mese_con_giorni(30)
    assert client.put(f"{URL}/{mese30}/giorni/31", json=GIORNO_OK).status_code == 422
    assert client.put(f"{URL}/{MESE}/giorni/0", json=GIORNO_OK).status_code == 422
    assert client.put(f"{URL}/{MESE}/giorni/32", json=GIORNO_OK).status_code == 422
    brutto = {**GIORNO_OK, "colonne": {"ascoli": ["25", "9"]}}
    r = client.put(f"{URL}/{MESE}/giorni/3", json=brutto)
    assert r.status_code == 422 and "Orario non valido" in str(r.json()["detail"])
    assert client.put(f"{URL}/{MESE}/giorni/3", json={**GIORNO_OK, "note": "x" * 201}).status_code == 422
    assert client.put(f"{URL}/{MESE}/giorni/3", json={**GIORNO_OK, "colonne": {"boh": ["8", "9"]}}).status_code == 422
    assert client.put(f"{URL}/{MESE}/giorni/3", json="non un oggetto").status_code == 422
    assert client.get(f"{URL}/{MESE}").json()["giorni"][2]["corretto"] is False


def test_note_finali(client, mario):
    entra(client, mario)
    r = client.put(f"{URL}/{MESE}/note", json={"note": "Tutto a posto"})
    assert r.status_code == 200 and r.json()["note"] == "Tutto a posto"
    assert client.get(f"{URL}/{MESE}").json()["note"] == "Tutto a posto"
    assert client.put(f"{URL}/{MESE}/note", json={"note": "x" * 1001}).status_code == 422
    assert client.put(f"{URL}/{MESE}/note", json={"note": "x" * 1000}).status_code == 200


# --- conferma e download -----------------------------------------------------------------

def test_conferma_blocca_ogni_modifica(client, mario):
    entra(client, mario)
    client.put(f"{URL}/{MESE}/giorni/3", json=GIORNO_OK)
    r = client.post(f"{URL}/{MESE}/conferma")
    assert r.status_code == 200 and r.json()["stato"] == "confermata" and r.json()["confermata_il"]
    assert client.post(f"{URL}/{MESE}/conferma").status_code == 409
    assert client.put(f"{URL}/{MESE}/giorni/4", json=GIORNO_OK).status_code == 409
    assert client.delete(f"{URL}/{MESE}/giorni/3").status_code == 409
    assert client.put(f"{URL}/{MESE}/note", json={"note": "dopo"}).status_code == 409
    assert client.get(f"{URL}/{MESE}").json()["giorni"][2]["corretto"] is True


def test_download_solo_dopo_la_conferma(client, mario):
    entra(client, mario)
    assert client.get(f"{URL}/{MESE}.xlsx").status_code == 409
    client.put(f"{URL}/{MESE}/giorni/3", json=GIORNO_OK)
    client.post(f"{URL}/{MESE}/conferma")
    r = client.get(f"{URL}/{MESE}.xlsx")
    assert r.status_code == 200 and r.headers["content-type"] == XLSX
    assert f'filename="scheda-ore-mario-rossi-{MESE}.xlsx"' in r.headers["content-disposition"]
    assert "no-store" in r.headers["cache-control"]
    assert "xl/worksheets/sheet1.xml" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()


def test_tutte_le_risposte_non_si_mettono_in_cache(client, mario):
    assert "no-store" in client.get(f"{URL}/dipendenti").headers["cache-control"]
    assert "no-store" in entra(client, mario, "no").headers["cache-control"]
    entra(client, mario)
    assert "no-store" in client.get(f"{URL}/{MESE}").headers["cache-control"]
    assert "no-store" in client.get(f"{URL}/2026-13").headers["cache-control"]


# --- registro e password del sito --------------------------------------------------------

def test_le_modifiche_non_sono_nel_registro_ma_la_conferma_si(client, conn, mario):
    entra(client, mario)
    client.put(f"{URL}/{MESE}/giorni/3", json=GIORNO_OK)
    client.put(f"{URL}/{MESE}/note", json={"note": "x"})
    client.post(f"{URL}/{MESE}/conferma")
    righe = [dict(r) for r in conn.execute("SELECT accesso, percorso, descrizione FROM registro_azioni").fetchall()]
    schede = [r for r in righe if "/schede-ore/" in r["percorso"]]
    assert len(schede) == 1 and schede[0]["accesso"] == "pubblico"        # come la pagina dei cambi turno
    assert "Mario Rossi" in schede[0]["descrizione"] and MESE in schede[0]["descrizione"]
    assert "codice1" not in str(righe)


def test_con_la_password_del_sito_le_api_restano_raggiungibili(tmp_path):
    percorso = str(tmp_path / "t.db")
    client = TestClient(create_app(percorso, password="normale1", password_master="master1"))
    assert client.get("/api/persone").status_code == 401                  # il sito è chiuso
    assert client.get(f"{URL}/dipendenti").status_code == 200             # la scheda ore no
    c = db.apri(percorso)
    mario = dipendente(c, "Mario Rossi")
    c.close()
    assert entra(client, mario).status_code == 200
    # anche con il cookie della password normale (modalità semplice) la scheda ore funziona
    assert client.post("/api/accesso", json={"password": "normale1"}).status_code == 200
    assert client.get(f"{URL}/mesi").status_code == 200


# --- pagina ------------------------------------------------------------------------------

def test_la_pagina_e_i_suoi_file_sono_serviti_senza_accesso(client):
    pagina = client.get("/scheda-ore")
    assert pagina.status_code == 200 and "text/html" in pagina.headers["content-type"]
    assert "Scheda ore" in pagina.text and "/static/js/scheda-ore.js" in pagina.text
    assert 'name="robots" content="noindex,nofollow"' in pagina.text
    assert client.get("/static/js/scheda-ore.js").status_code == 200
    assert client.get("/static/scheda-ore.css").status_code == 200


def test_la_pagina_non_e_dietro_la_password_del_sito(tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db"), password="normale1"))
    assert client.get("/scheda-ore").status_code == 200
