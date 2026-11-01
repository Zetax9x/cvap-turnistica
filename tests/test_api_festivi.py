"""Fase 6 del piano rotazioni: festività nel generatore (dati passati al solver), statistiche, riepilogo per
dipendente ed email (docs/PIANO-rotazioni.md, 3.3-3.5)."""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import db, solver  # noqa: E402
from cvap.app import create_app  # noqa: E402
from cvap.modello import Assegnazione  # noqa: E402

from .test_api_storico_festivi import attiva, crea, salva, turno  # noqa: E402

PRIMA = date(2026, 10, 19)        # prima settimana generata
SETT_NATALE = date(2026, 12, 21)  # Natale 2026 è venerdì 25
NATALE = date(2026, 12, 25)


@pytest.fixture(params=["sqlite", "libsql"])
def client(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    percorso = str(tmp_path / "t.db")
    c = TestClient(create_app(percorso))
    c.percorso_db = percorso
    return c


def settimana_generata(client, inizio, dipendenti, turni):
    """Salva una settimana 'generata' con i turni dati: (giorno, fascia, persona_id[, origine])."""
    conn = db.apri(client.percorso_db)
    try:
        nuove = [Assegnazione(d, "Acquasanta", fascia, "intero", "autista", pid, "generato")
                 for d, fascia, pid in turni]
        db.salva_generazione(conn, inizio, inizio + timedelta(days=6), nuove, list(dipendenti), "2026-10-01", {})
    finally:
        conn.close()


def per_nome(stat, persona_id):
    riga = next(r for r in stat if r["persona_id"] == persona_id)
    return {f["festivita"]: f for f in riga["festivi"]["per_festivita"]}


# --- statistiche --------------------------------------------------------------------------------------

def test_statistiche_festivi_per_festivita_importati_e_programma(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale, ferragosto = attiva(client, "Natale"), attiva(client, "Ferragosto")
    settimana_generata(client, PRIMA, [mario, luigi], [(PRIMA, "giorno", mario), (PRIMA, "notte", luigi)])
    assert salva(client, 2025, [turno(natale, mario), turno(ferragosto, mario, "notte")],
                 [mario, luigi]).status_code == 200
    assert salva(client, 2021, [turno(natale, luigi)], [mario, luigi]).status_code == 200   # oltre i 5 anni
    assert salva(client, 2022, [turno(natale, luigi)], [mario, luigi]).status_code == 200
    settimana_generata(client, SETT_NATALE, [mario, luigi], [(NATALE, "giorno", luigi), (NATALE, "notte", mario)])

    stat = client.get("/api/statistiche").json()
    m, lu = per_nome(stat, mario), per_nome(stat, luigi)
    assert m["Natale"] == {"festivita": "Natale", "turni": 2, "ultimo_anno": 2026}
    assert m["Ferragosto"] == {"festivita": "Ferragosto", "turni": 1, "ultimo_anno": 2025}
    # Natale 2021 è fuori dagli ultimi 5 anni (ultima settimana del programma: fine 2026)
    assert lu["Natale"] == {"festivita": "Natale", "turni": 2, "ultimo_anno": 2026}
    assert lu["Ferragosto"] == {"festivita": "Ferragosto", "turni": 0, "ultimo_anno": None}
    riga_mario = next(r for r in stat if r["persona_id"] == mario)
    assert riga_mario["festivi"]["turni"] == 3


def test_statistiche_festivi_volontari_vuoti_e_turni_dei_volontari_esclusi(client):
    mario = crea(client, "Mario Rossi")["id"]
    vol = crea(client, "Vol", tipo="volontario")["id"]
    attiva(client, "Natale")
    settimana_generata(client, SETT_NATALE, [mario], [(NATALE, "giorno", mario), (NATALE, "notte", vol)])
    stat = client.get("/api/statistiche").json()
    riga_vol = next(r for r in stat if r["persona_id"] == vol)
    assert riga_vol["festivi"] == {"turni": 0, "per_festivita": []}
    assert per_nome(stat, mario)["Natale"]["turni"] == 1


def test_statistiche_festivi_solo_festivita_attive(client):
    mario = crea(client, "Mario Rossi")["id"]
    settimana_generata(client, SETT_NATALE, [mario], [(NATALE, "giorno", mario)])
    stat = client.get("/api/statistiche").json()
    assert next(r for r in stat if r["persona_id"] == mario)["festivi"] == {"turni": 0, "per_festivita": []}


# --- generatore: dati passati al solver --------------------------------------------------------------

@pytest.fixture
def cattura(monkeypatch):
    chiamate = []

    def finto(giorni, postazioni, persone, **kw):
        chiamate.append(kw)
        return solver.Risultato("ottimo", media_ore=0.0)

    monkeypatch.setattr(solver, "genera", finto)
    return chiamate


def test_la_generazione_passa_le_festivita_con_storico_importato_e_programma(client, cattura):
    mario, luigi, anna = (crea(client, n)["id"] for n in ("Mario Rossi", "Luigi Bianchi", "Anna Verdi"))
    natale = attiva(client, "Natale")
    settimana_generata(client, PRIMA, [mario, luigi, anna], [(PRIMA, "giorno", mario)])
    assert salva(client, 2025, [turno(natale, mario)], [mario, luigi, anna]).status_code == 200
    # Natale 2026 nel programma: Luigi lavora, Anna in ferie (riposo goduto), Mario in malattia (non conta)
    assert client.post("/api/ferie", json={"persona_id": anna, "dal": "2026-12-24", "al": "2026-12-26"}).status_code == 201
    assert client.post("/api/ferie", json={"persona_id": mario, "dal": "2026-12-25", "al": "2026-12-25",
                                           "motivo": "malattia"}).status_code == 201
    settimana_generata(client, SETT_NATALE, [mario, luigi, anna], [(NATALE, "giorno", luigi)])

    r = client.post("/api/settimane/2027-12-20/genera", json={})
    assert r.status_code == 200, r.text
    fs = cattura[-1]["festivi"]
    assert fs.turni[(date(2027, 12, 25), "giorno")] == natale and fs.turni[(date(2027, 12, 25), "notte")] == natale
    assert fs.anno[natale] == 2027 and fs.peso[natale] == 1
    c = fs.conti[natale]
    assert (c[mario].turni, c[mario].esposizione, c[mario].ultimo_anno) == (1, 1, 2025)
    assert (c[luigi].turni, c[luigi].esposizione, c[luigi].ultimo_anno) == (1, 2, 2026)
    assert (c[anna].turni, c[anna].esposizione) == (0, 2)


def test_la_generazione_senza_festivita_attive(client, cattura):
    crea(client, "Mario Rossi")
    assert client.post("/api/settimane/2026-12-21/genera", json={}).status_code == 200
    fs = cattura[-1]["festivi"]
    assert fs.turni == {}


# --- riepilogo per dipendente --------------------------------------------------------------------------

def test_riepilogo_per_dipendente_turni_festivi_del_periodo(client):
    pid = crea(client, "Rino")["id"]
    attiva(client, "Ognissanti")  # domenica 1/11/2026
    for d, fascia in (("2026-10-31", "giorno"), ("2026-11-01", "notte")):
        r = client.post("/api/settimane/2026-10-26/assegnazioni", json={
            "data": d, "postazione": "Acquasanta", "fascia": fascia, "segmento": "intero", "ruolo": "autista",
            "persona_id": pid})
        assert r.status_code == 201, r.text
    x = client.get(f"/api/statistiche/persona/{pid}", params={"dal": "2026-10-26", "al": "2026-11-01"}).json()
    assert x["riepilogo"]["turni_festivi"] == 1
    assert x["riepilogo"]["festivi"] == [{"festivita": "Ognissanti", "turni": 1}]
    giorni = {g["data"]: g for g in x["giorni"]}
    assert giorni["2026-11-01"]["turni"][0]["festivita"] == "Ognissanti"
    assert giorni["2026-10-31"]["turni"][0]["festivita"] is None


# --- email -------------------------------------------------------------------------------------------

def test_le_statistiche_via_email_hanno_i_festivi():
    from cvap.email_turni import _sezione_statistiche
    riga = {"nome": "Mario", "tipo": "dipendente", "settimane": 2, "ore_totali": 96, "saldo_ore": 0,
            "ore_giorno": 48, "ore_notte": 48, "weekend": {}, "standby": 0, "programmati": 0, "sedi": {},
            "ascoli": {"turni": 0, "giorno": 0, "notte": 0}, "assistenze": 0,
            "festivi": {"turni": 3, "per_festivita": [
                {"festivita": "Natale", "turni": 2, "ultimo_anno": 2025},
                {"festivita": "Ferragosto", "turni": 0, "ultimo_anno": None},
                {"festivita": "Pasqua", "turni": 1, "ultimo_anno": 2023}]}}
    html_, testo = _sezione_statistiche([riga])
    assert "Festivi" in html_
    assert "Natale 2 (2025), Pasqua 1 (2023)" in html_ and "Natale 2 (2025), Pasqua 1 (2023)" in testo
    assert "Ferragosto" not in testo
