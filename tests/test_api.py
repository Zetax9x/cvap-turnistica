"""Test dell'API REST (FastAPI + SQLite) secondo docs/API.md."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap.app import create_app  # noqa: E402

LUNEDI_A = "2026-10-19"
LUNEDI_B = "2026-10-26"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(client, nome, tipo="dipendente", qualifica="autista"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()


def prenota(client, settimana, persona_id, data=None, postazione="Acquasanta", fascia="giorno",
            segmento="intero", ruolo="soccorritore"):
    return client.post(f"/api/settimane/{settimana}/assegnazioni", json={
        "data": data or settimana, "postazione": postazione, "fascia": fascia,
        "segmento": segmento, "ruolo": ruolo, "persona_id": persona_id,
    })


def staff_14(client):
    ids = [crea(client, f"Autista {i}", "dipendente", "autista")["id"] for i in range(8)]
    ids += [crea(client, f"Soccorritore {i}", "dipendente", "soccorritore")["id"] for i in range(6)]
    return ids


# --- persone ---------------------------------------------------------------

def test_crud_persone(client):
    assert client.get("/api/persone").json() == []
    p = crea(client, "  Mario Rossi  ")
    assert p["nome"] == "Mario Rossi" and p["attivo"] is True and p["tipo"] == "dipendente"
    r = client.put(f"/api/persone/{p['id']}", json={
        "nome": "Mario", "tipo": "volontario", "qualifica": "soccorritore", "attivo": False})
    assert r.status_code == 200
    assert r.json() == {"id": p["id"], "nome": "Mario", "tipo": "volontario",
                        "qualifica": "soccorritore", "attivo": False}
    assert len(client.get("/api/persone").json()) == 1
    assert client.delete(f"/api/persone/{p['id']}").status_code == 204
    assert client.get("/api/persone").json() == []


def test_persone_404(client):
    assert client.put("/api/persone/999", json={
        "nome": "X", "tipo": "dipendente", "qualifica": "autista", "attivo": True}).status_code == 404
    assert client.delete("/api/persone/999").status_code == 404


@pytest.mark.parametrize("body", [
    {"nome": "", "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "   ", "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "x" * 101, "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "Mario", "tipo": "capo", "qualifica": "autista"},
    {"nome": "Mario", "tipo": "dipendente", "qualifica": "medico"},
    {"tipo": "dipendente", "qualifica": "autista"},
])
def test_persone_validazione_422(client, body):
    assert client.post("/api/persone", json=body).status_code == 422


def test_delete_persona_con_assegnazioni_la_disattiva(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, p["id"]).status_code == 201
    assert client.delete(f"/api/persone/{p['id']}").status_code == 204
    persone = client.get("/api/persone").json()
    assert persone == [{**p, "attivo": False}]


# --- postazioni / impostazioni -------------------------------------------------

def test_postazioni_seed(client):
    post = client.get("/api/postazioni").json()
    assert [(p["nome"], p["solo_settimane_b"]) for p in post] == [
        ("Acquasanta", False), ("Venarotta", False), ("Ascoli", True)]


def test_impostazioni_normalizzate_al_lunedi(client):
    assert client.get("/api/impostazioni").json() == {"data_riferimento_a": LUNEDI_A}
    r = client.put("/api/impostazioni", json={"data_riferimento_a": "2026-10-29"})  # giovedì
    assert r.status_code == 200
    assert r.json() == {"data_riferimento_a": LUNEDI_B}
    assert client.get("/api/impostazioni").json() == {"data_riferimento_a": LUNEDI_B}
    assert client.put("/api/impostazioni", json={"data_riferimento_a": "boh"}).status_code == 422


# --- settimane ---------------------------------------------------------------

def test_settimana_a(client):
    s = client.get("/api/settimane/2026-10-21").json()
    assert s["inizio"] == LUNEDI_A and s["fine"] == "2026-10-25"
    assert s["tipo"] == "A" and s["stato"] == "nuova"
    assert s["postazioni"] == ["Acquasanta", "Venarotta"]
    assert len(s["giorni"]) == 7 and s["giorni"][0] == LUNEDI_A
    assert s["assegnazioni"] == [] and s["report"] is None and s["media_ore"] == 0
    assert any(v["codice"] == "scoperto" for v in s["violazioni"])


def test_settimana_b(client):
    s = client.get(f"/api/settimane/{LUNEDI_B}").json()
    assert s["tipo"] == "B"
    assert s["postazioni"] == ["Acquasanta", "Venarotta", "Ascoli"]


def test_data_non_valida_400(client):
    assert client.get("/api/settimane/2026-13-45").status_code == 400


def test_prenotazione_volontario(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    r = prenota(client, LUNEDI_A, p["id"], data="2026-10-24", segmento="mattina")
    assert r.status_code == 201, r.text
    s = r.json()
    [a] = s["assegnazioni"]
    assert a["origine"] == "volontario" and a["persona_nome"] == "Anna" and a["ore"] == 6
    [riga] = s["riepilogo"]
    assert riga["persona_id"] == p["id"] and riga["ore"] == 6 and riga["ore_giorno"] == 6
    assert riga["turni_weekend"] == 1
    assert s["stato"] == "nuova"


def test_prenotazione_dipendente_manuale(client):
    p = crea(client, "Mario", "dipendente", "autista")
    s = prenota(client, LUNEDI_A, p["id"], ruolo="autista").json()
    assert s["assegnazioni"][0]["origine"] == "manuale"
    assert s["media_ore"] == 12


@pytest.mark.parametrize("override", [
    {"data": "2026-10-26"},                         # fuori settimana
    {"postazione": "Ascoli"},                       # non attiva in settimana A
    {"postazione": "Inesistente"},
    {"fascia": "notte", "segmento": "mattina"},     # segmento non valido di notte
    {"ruolo": "autista"},                           # soccorritore non abilitato
])
def test_prenotazioni_rifiutate_400(client, override):
    p = crea(client, "Anna", "volontario", "soccorritore")
    r = prenota(client, LUNEDI_A, p["id"], **override)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_prenotazione_persona_inesistente(client):
    assert prenota(client, LUNEDI_A, 999).status_code in (400, 404)


def test_posto_gia_occupato_400(client):
    a = crea(client, "Anna", "volontario", "soccorritore")
    b = crea(client, "Bea", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, a["id"], segmento="intero").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], segmento="pomeriggio").status_code == 400
    # segmenti complementari invece vanno bene
    assert prenota(client, LUNEDI_A, a["id"], data="2026-10-20", segmento="mattina").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], data="2026-10-20", segmento="pomeriggio").status_code == 201


def test_validazione_body_assegnazione_422(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, p["id"], ruolo="medico").status_code == 422
    assert prenota(client, LUNEDI_A, p["id"], fascia="sera").status_code == 422


def test_delete_assegnazione(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    a = prenota(client, LUNEDI_A, p["id"]).json()["assegnazioni"][0]
    assert client.delete(f"/api/assegnazioni/{a['id']}").status_code == 204
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["assegnazioni"] == []
    assert client.delete(f"/api/assegnazioni/{a['id']}").status_code == 404


# --- generazione ---------------------------------------------------------------

@pytest.fixture
def generata(client):
    staff_14(client)
    vol = crea(client, "Volontaria", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, vol["id"], data="2026-10-21", postazione="Venarotta").status_code == 201
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5})
    assert r.status_code == 200, r.text
    return client, r.json(), vol


def test_genera_copre_tutto(generata):
    _, s, vol = generata
    assert s["stato"] == "bozza"
    rep = s["report"]
    assert rep["scoperti"] == [] and rep["stato"] in ("ottimo", "ammissibile")
    assert rep["media_ore"] > 0 and rep["durata_s"] >= 0
    assert not [v for v in s["violazioni"] if v["livello"] == "errore"]
    vols = [a for a in s["assegnazioni"] if a["origine"] == "volontario"]
    assert len(vols) == 1 and vols[0]["persona_id"] == vol["id"]
    assert len(s["assegnazioni"]) == 7 * 2 * 2 * 2
    assert s["media_ore"] > 0
    assert len(s["riepilogo"]) == 15


def test_rigenera_mantiene_fissi_e_sostituisce_generati(generata):
    client, s, vol = generata
    generati = [a for a in s["assegnazioni"] if a["origine"] == "generato"]
    # un turno generato cancellato e sostituito da un manuale
    g = generati[0]
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 204
    r = prenota(client, LUNEDI_A, g["persona_id"], data=g["data"], postazione=g["postazione"],
                fascia=g["fascia"], segmento=g["segmento"], ruolo=g["ruolo"])
    assert r.status_code == 201, r.text
    s2 = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5}).json()
    origini = [a["origine"] for a in s2["assegnazioni"]]
    assert origini.count("volontario") == 1 and origini.count("manuale") == 1
    assert len(s2["assegnazioni"]) == 56
    vecchi_ids = {a["id"] for a in generati}
    assert not vecchi_ids & {a["id"] for a in s2["assegnazioni"] if a["origine"] == "generato"}

    s3 = client.delete(f"/api/settimane/{LUNEDI_A}/generati").json()
    assert sorted(a["origine"] for a in s3["assegnazioni"]) == ["manuale", "volontario"]


def test_conferma_blocca_e_riapri_sblocca(generata):
    client, s, vol = generata
    g = next(a for a in s["assegnazioni"] if a["origine"] == "generato" and a["ruolo"] == "soccorritore")
    posto = {k: g[k] for k in ("data", "postazione", "fascia", "segmento", "ruolo")}
    c = client.post(f"/api/settimane/{LUNEDI_A}/conferma")
    assert c.status_code == 200 and c.json()["stato"] == "confermata"
    assert client.post(f"/api/settimane/{LUNEDI_A}/genera", json={}).status_code == 400
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 400
    assert client.delete(f"/api/settimane/{LUNEDI_A}/generati").status_code == 400
    assert prenota(client, LUNEDI_A, vol["id"], **posto).status_code == 400
    r = client.post(f"/api/settimane/{LUNEDI_A}/riapri")
    assert r.status_code == 200 and r.json()["stato"] == "bozza"
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 204
    assert prenota(client, LUNEDI_A, vol["id"], **posto).status_code == 201


def test_statistiche(generata):
    client, s, vol = generata
    stats = client.get("/api/statistiche").json()
    per_id = {x["persona_id"]: x for x in stats}
    assert per_id[vol["id"]]["tipo"] == "volontario"
    assert per_id[vol["id"]]["ore_totali"] == 12 and per_id[vol["id"]]["saldo_ore"] == 0
    assert per_id[vol["id"]]["settimane"] == 1
    dip = [x for x in stats if x["tipo"] == "dipendente"]
    assert len(dip) == 14
    assert sum(x["ore_totali"] for x in dip) == 672 - 12
    assert all(x["settimane"] == 1 for x in dip)
    assert abs(sum(x["saldo_ore"] for x in dip)) < 1e-6
    assert set(dip[0]["weekend"]) == {"sab_giorno", "sab_notte", "dom_giorno", "dom_notte"}


def test_genera_settimana_successiva_usa_storico(generata):
    client, _, _ = generata
    r = client.post(f"/api/settimane/{LUNEDI_B}/genera", json={"tempo_max": 5})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["tipo"] == "B" and s["stato"] == "bozza"


# --- statici -----------------------------------------------------------------

def test_index_non_crasha(client):
    r = client.get("/")
    assert r.status_code in (200, 404)
