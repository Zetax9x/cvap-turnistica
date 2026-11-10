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
    assert master.post("/api/persone", json={"nome": "Mario", "tipo": "dipendente",
                                             "qualifica": "autista"}).status_code == 201
    normale.post("/api/settimane/2026-10-19/conferma")
    normale.get("/api/persone")  # le letture non si registrano
    TestClient(app).post("/api/accesso", json={"password": "sbagliata"})
    righe = master.get("/api/registro").json()
    azioni = [(r["accesso"], r["descrizione"], r["esito"]) for r in righe]
    assert azioni == [
        ("anonimo", "Tentativo di accesso con password sbagliata", 401),
        ("normale", "Conferma della settimana del 19/10/2026", 200),
        ("master", "Persona aggiunta: Mario", 201),
        ("master", "Accesso", 200),
        ("normale", "Accesso", 200),
    ]
    solo_normale = master.get("/api/registro", params={"accesso": "master"}).json()
    assert {r["accesso"] for r in solo_normale} == {"master"}
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
    assert [(r["accesso"], r["descrizione"]) for r in registro.lista(conn)] == [("aperto", "Persona aggiunta: Mario")]
    conn.close()


def test_descrizioni():
    assert registro.descrivi("POST", "/api/settimane/2026-10-19/genera") == \
        "Generazione dei turni della settimana del 19/10/2026"
    assert registro.descrivi("DELETE", "/api/assegnazioni/42") == "Tolto il turno di n. 42"
    assert registro.descrivi("POST", "/api/qualcosa") == "POST /api/qualcosa"
    assert not registro.da_registrare("POST", "/api/calendario-copertura/ferie/anteprima")
    assert not registro.da_registrare("GET", "/api/persone")
    assert registro.da_registrare("POST", "/api/ferie")


def _dettagli(riga):
    return {e: v for e, v in riga["dettagli"]}


def test_i_dettagli_hanno_i_nomi_le_date_e_mai_le_password(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    pid = master.post("/api/persone", json={"nome": "Marco Bianchi", "tipo": "dipendente",
                                            "qualifica": "autista"}).json()["id"]
    normale.post("/api/ferie", json={"persona_id": pid, "dal": "2026-11-18", "al": "2026-11-20"})
    righe = master.get("/api/registro").json()
    ferie = _dettagli(righe[0])
    assert righe[0]["descrizione"] == "Ferie aggiunte"
    assert ferie == {"Persona": "Marco Bianchi", "Dal": "18/11/2026", "Al": "20/11/2026"}
    assert righe[1]["descrizione"] == "Persona aggiunta: Marco Bianchi"
    assert _dettagli(righe[1]) == {"Tipo": "dipendente", "Qualifica": "autista"}
    accesso_ = next(r for r in righe if r["descrizione"] == "Accesso")
    assert all("password" not in e.lower() and NORMALE not in v and MASTER not in v
               for e, v in accesso_["dettagli"])


def test_turno_tolto_descritto_con_chi_quando_e_dove(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    pid = master.post("/api/persone", json={"nome": "Marco Bianchi", "tipo": "dipendente",
                                            "qualifica": "autista"}).json()["id"]
    s = master.post("/api/settimane/2026-10-19/assegnazioni", json={
        "data": "2026-10-21", "postazione": "Acquasanta", "fascia": "giorno", "segmento": "intero",
        "ruolo": "autista", "persona_id": pid}).json()
    aid = s["assegnazioni"][0]["id"]
    assert master.delete(f"/api/assegnazioni/{aid}").status_code == 204
    riga = master.get("/api/registro").json()[0]
    assert riga["descrizione"] == "Tolto il turno di Marco Bianchi del 21/10"
    assert _dettagli(riga) == {"Turno": "Marco Bianchi, 21/10/2026, Acquasanta, giorno 8–20, autista"}


def test_azione_non_riuscita_salva_il_motivo(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    r = normale.delete("/api/ferie/999")
    assert r.status_code >= 400
    riga = master.get("/api/registro").json()[0]
    assert riga["esito"] == r.status_code and _dettagli(riga)["Motivo"]


def test_generazione_salva_turni_generati_e_posti_scoperti(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    master.post("/api/persone", json={"nome": "Solo", "tipo": "dipendente", "qualifica": "autista"})
    assert normale.post("/api/settimane/2026-10-19/genera", json={"tempo_max": 2}).status_code == 200
    d = _dettagli(master.get("/api/registro").json()[0])
    assert d["Tempo massimo (secondi)"] == "2" and int(d["Turni generati"]) > 0 and d["Posti scoperti"] != "nessuno"


def test_registro_vecchio_senza_colonna_dettagli(tmp_path):
    from cvap import db
    percorso = str(tmp_path / "t.db")
    conn = db.connetti(percorso)
    conn.executescript("""CREATE TABLE registro_azioni (id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT NOT NULL,
        accesso TEXT NOT NULL, metodo TEXT NOT NULL, percorso TEXT NOT NULL, esito INTEGER NOT NULL,
        descrizione TEXT NOT NULL);
        INSERT INTO registro_azioni(quando, accesso, metodo, percorso, esito, descrizione)
        VALUES ('2026-11-10T10:00:00', 'normale', 'POST', '/api/ferie', 201, 'Ferie aggiunte');""")
    conn.close()
    master, _ = _entra(create_app(percorso, password=NORMALE, password_master=MASTER), MASTER)
    righe = master.get("/api/registro").json()
    assert righe[-1]["descrizione"] == "Ferie aggiunte" and righe[-1]["dettagli"] == []


def test_divieto_vuoto_vuol_dire_qualsiasi_e_motivi_in_italiano(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    pid = master.post("/api/persone", json={"nome": "Anna", "tipo": "dipendente",
                                            "qualifica": "autista"}).json()["id"]
    master.post("/api/divieti", json={"persona_id": pid, "postazione": None, "turno": "notte"})
    normale.post("/api/ferie", json={"persona_id": pid})
    ferie, divieto = master.get("/api/registro").json()[:2]
    assert _dettagli(divieto)["Postazione"] == "qualsiasi"
    assert _dettagli(ferie)["Motivo"] == "Dal: manca un dato obbligatorio; Al: manca un dato obbligatorio"


# --- modalità semplice: la password normale usa solo la procedura guidata ------------------------

def test_con_la_master_la_normale_e_in_modalita_semplice(app, tmp_path):
    normale, r = _entra(app, NORMALE)
    assert r["semplice"] is True and normale.get("/api/sessione").json()["semplice"] is True
    master, r = _entra(app, MASTER)
    assert r["semplice"] is False
    # senza master la normale fa tutto, come prima
    solo_normale, r = _entra(create_app(str(tmp_path / "x.db"), password=NORMALE), NORMALE)
    assert r["semplice"] is False
    assert solo_normale.post("/api/persone", json={"nome": "A", "tipo": "dipendente",
                                                   "qualifica": "autista"}).status_code == 201


def test_modalita_semplice_solo_le_api_della_procedura(app):
    normale, _ = _entra(app, NORMALE)
    master, _ = _entra(app, MASTER)
    pid = master.post("/api/persone", json={"nome": "Marco", "tipo": "dipendente",
                                            "qualifica": "autista"}).json()["id"]
    settimana = "2026-10-19"
    assert normale.get(f"/api/settimane/{settimana}").status_code == 200
    assert normale.get("/api/persone").status_code == 200
    assert normale.post("/api/ferie", json={"persona_id": pid, "dal": "2026-10-20", "al": "2026-10-21"}).status_code == 201
    assert normale.put(f"/api/settimane/{settimana}/indisponibilita",
                       json={"persona_id": pid, "turni": [{"data": "2026-10-22", "parte": "notte"}]}).status_code == 200
    s = normale.post(f"/api/settimane/{settimana}/assegnazioni", json={
        "data": "2026-10-23", "postazione": "Acquasanta", "fascia": "giorno", "segmento": "intero",
        "ruolo": "soccorritore", "nome_volontario": "Vol. Anna"})
    assert s.status_code == 201, s.text
    volontario = next(a for a in s.json()["assegnazioni"] if a["persona_nome"] == "Vol. Anna")
    # il resto del programma no
    for metodo, percorso in (("POST", "/api/persone"), ("GET", "/api/statistiche"), ("PUT", "/api/impostazioni"),
                             ("DELETE", f"/api/settimane/{settimana}/generati"), ("GET", "/api/registro")):
        assert normale.request(metodo, percorso, json={}).status_code == 403, percorso
    # turni: si tolgono quelli dei volontari, non quelli dei dipendenti
    dip = master.post(f"/api/settimane/{settimana}/assegnazioni", json={
        "data": "2026-10-24", "postazione": "Acquasanta", "fascia": "giorno", "segmento": "intero",
        "ruolo": "autista", "persona_id": pid}).json()
    turno_dip = next(a for a in dip["assegnazioni"] if a["persona_id"] == pid)
    assert normale.delete(f"/api/assegnazioni/{turno_dip['id']}").status_code == 403
    assert normale.delete(f"/api/assegnazioni/{volontario['id']}").status_code == 204
    # Standby e Assistenze ed Extra
    voci = [{"data": "2026-10-21", "postazione": "Standby", "fascia": "giorno", "segmento": "standby", "ruolo": r,
             "quantita": 1} for r in ("autista", "soccorritore")]
    assert normale.put(f"/api/settimane/{settimana}/fabbisogno", json={"voci": voci}).status_code == 200
    extra = normale.post(f"/api/settimane/{settimana}/extra", json={"data": "2026-10-22", "nome": "Partita", "inizio": 15,
                                                                     "fine": 18, "autisti": 1, "soccorritori": 1})
    assert extra.status_code == 201
    assert normale.delete(f"/api/extra/{extra.json()['extra'][0]['id']}").status_code == 204
    assert normale.get(f"/api/settimane/{settimana}/pdf-tabellone").headers["content-type"] == "application/pdf"
    assert normale.get(f"/api/settimane/{settimana}/pdf-liberi").status_code == 200
    # «Ho fatto un errore, rigenera»: si riapre la settimana confermata
    assert normale.post(f"/api/settimane/{settimana}/conferma").status_code == 200
    assert normale.post(f"/api/settimane/{settimana}/riapri").json()["stato"] == "bozza"
