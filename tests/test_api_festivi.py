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
    assert m["Natale"] == {"festivita": "Natale", "attiva": True, "turni": 2, "ultimo_anno": 2026}
    assert m["Ferragosto"] == {"festivita": "Ferragosto", "attiva": True, "turni": 1, "ultimo_anno": 2025}
    # Natale 2021 è fuori dagli ultimi 5 anni (ultima settimana del programma: fine 2026)
    assert lu["Natale"] == {"festivita": "Natale", "attiva": True, "turni": 2, "ultimo_anno": 2026}
    assert lu["Ferragosto"] == {"festivita": "Ferragosto", "attiva": True, "turni": 0, "ultimo_anno": None}
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


# --- correzioni dopo la revisione -------------------------------------------------------------------

def assegna(client, d, fascia, pid, origine="manuale", postazione="Acquasanta"):
    """Un turno salvato direttamente, senza toccare la tabella delle settimane."""
    conn = db.apri(client.percorso_db)
    try:
        db.crea_assegnazione(conn, Assegnazione(d, postazione, fascia, "intero", "autista", pid, origine))
    finally:
        conn.close()


def disattiva(client, nome):
    f = next(f for f in client.get("/api/festivita").json() if f["nome"] == nome)
    campi = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte",
             "conta_notte_prima", "peso")
    r = client.put(f"/api/festivita/{f['id']}", json={**{k: f[k] for k in campi}, "attiva": False})
    assert r.status_code == 200, r.text


def test_settimana_con_turni_ma_senza_riga_conta(client, cattura):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    settimana_generata(client, PRIMA, [mario, luigi], [(PRIMA, "giorno", mario), (PRIMA, "notte", luigi)])
    assegna(client, NATALE, "giorno", mario)  # settimana di Natale compilata a mano, senza riga in `settimane`
    assert per_nome(client.get("/api/statistiche").json(), mario)["Natale"]["turni"] == 1
    assert client.post("/api/settimane/2027-12-20/genera", json={}).status_code == 200
    c = cattura[-1]["festivi"].conti[natale]
    # dipendenti di quella settimana: chi vi ha turni
    assert (c[mario].turni, c[mario].esposizione) == (1, 1)
    assert c[luigi].esposizione == 0


def test_settimana_salvata_ma_vuota_non_espone(client, cattura):
    mario = crea(client, "Mario Rossi")["id"]
    natale = attiva(client, "Natale")
    settimana_generata(client, PRIMA, [mario], [(PRIMA, "giorno", mario)])
    settimana_generata(client, SETT_NATALE, [mario], [])
    assert client.post("/api/settimane/2027-12-20/genera", json={}).status_code == 200
    assert cattura[-1]["festivi"].conti[natale][mario].esposizione == 0


def test_festivita_disattivata_resta_in_statistiche_e_riepilogo(client):
    mario = crea(client, "Mario Rossi")["id"]
    attiva(client, "Natale")
    attiva(client, "Ferragosto")
    settimana_generata(client, PRIMA, [mario], [(PRIMA, "giorno", mario)])
    settimana_generata(client, SETT_NATALE, [mario], [(NATALE, "giorno", mario)])
    disattiva(client, "Natale")
    stat = client.get("/api/statistiche").json()
    riga = next(r for r in stat if r["persona_id"] == mario)
    assert riga["festivi"]["turni"] == 1
    voci = {f["festivita"]: f for f in riga["festivi"]["per_festivita"]}
    assert voci["Natale"] == {"festivita": "Natale", "attiva": False, "turni": 1, "ultimo_anno": 2026}
    assert voci["Ferragosto"]["attiva"] is True and voci["Ferragosto"]["turni"] == 0
    assert "Capodanno" not in voci  # non attiva e mai lavorata
    x = client.get(f"/api/statistiche/persona/{mario}", params={"dal": "2026-12-21", "al": "2026-12-27"}).json()
    assert x["riepilogo"]["festivi"] == [{"festivita": "Natale (non più nel calendario)", "turni": 1}]


def test_lunedi_festivo_la_notte_prima_della_settimana_precedente_e_gia_fissata(client, cattura):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    f = next(f for f in client.get("/api/festivita").json() if f["nome"] == "Capodanno")
    campi = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte", "peso")
    assert client.put(f"/api/festivita/{f['id']}", json={**{k: f[k] for k in campi}, "conta_notte_prima": True,
                                                          "attiva": True}).status_code == 200
    settimana_generata(client, PRIMA, [mario, luigi], [(PRIMA, "giorno", mario)])
    # 1/1/2029 è lunedì: la notte del 31/12/2028 è nella settimana precedente, già salvata
    settimana_generata(client, date(2028, 12, 25), [mario, luigi], [(date(2028, 12, 31), "notte", mario)])
    assert client.post("/api/settimane/2029-01-01/genera", json={}).status_code == 200
    fs = cattura[-1]["festivi"]
    assert fs.fuori_settimana == {f["id"]: {mario: 1}}
    assert fs.turni[(date(2029, 1, 1), "giorno")] == f["id"]
    # nelle statistiche quella notte conta come lavorata per Capodanno 2029
    assert per_nome(client.get("/api/statistiche").json(), mario)["Capodanno"] == {
        "festivita": "Capodanno", "attiva": True, "turni": 1, "ultimo_anno": 2029}


def test_turni_festivi_di_chi_non_e_in_tabella(client):
    mario = crea(client, "Mario Rossi")["id"]
    ex = crea(client, "Ex Dipendente")["id"]
    natale = attiva(client, "Natale")
    settimana_generata(client, PRIMA, [mario], [(PRIMA, "giorno", mario)])
    assert salva(client, 2025, [turno(natale, ex), turno(natale, ex, "notte"), turno(natale, mario)],
                 [mario, ex]).status_code == 200
    r = client.get("/api/statistiche/festivi")
    assert r.status_code == 200, r.text
    assert r.json() == {"fuori_tabella": [{"festivita": "Natale", "attiva": True, "turni": 2}]}
    assert ex not in {x["persona_id"] for x in client.get("/api/statistiche").json()}


def test_report_della_generazione_con_le_festivita(client, cattura):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    attiva(client, "Natale")
    settimana_generata(client, PRIMA, [mario, luigi], [(PRIMA, "giorno", mario)])
    assegna(client, NATALE, "giorno", mario)  # fissato a mano nella settimana da generare
    r = client.post("/api/settimane/2026-12-21/genera", json={})
    assert r.status_code == 200, r.text
    assert r.json()["report"]["festivi"] == {"per_festivita": [{"festivita": "Natale", "turni": 1}], "turni": 1,
                                             "anno_prima": 0, "persone_con_piu_festivi": 0}
    r = client.post("/api/settimane/2026-11-02/genera", json={})
    assert r.json()["report"]["festivi"] is None


def test_le_statistiche_via_email_segnano_le_festivita_non_piu_nel_calendario():
    from cvap.email_turni import festivi_testo
    riga = {"festivi": {"turni": 1, "per_festivita": [
        {"festivita": "Natale", "attiva": False, "turni": 1, "ultimo_anno": 2025}]}}
    assert festivi_testo(riga) == "Natale (non più nel calendario) 1 (2025)"
