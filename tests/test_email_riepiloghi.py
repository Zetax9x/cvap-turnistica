"""Riepiloghi via email per indirizzi definiti in Impostazioni: ognuno sceglie cosa ricevere."""
import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

from .test_email import LUNEDI, PostinoFinto, contenuto, crea, turno

TUTTI = ["turni", "liberi", "indisponibilita", "statistiche", "statistiche_indisponibilita"]


@pytest.fixture
def postino():
    return PostinoFinto()


@pytest.fixture
def client(tmp_path, postino):
    return TestClient(create_app(str(tmp_path / "t.db"), postino=postino))


def aggiungi(c, email, contenuti, nome=None, responsabile=False):
    r = c.post("/api/destinatari", json={"email": email, "nome": nome, "contenuti": contenuti,
                                         "responsabile": responsabile})
    assert r.status_code == 201, r.text
    return r.json()


def test_destinatari_si_aggiungono_modificano_ed_eliminano(client):
    d = aggiungi(client, "capo@example.org", ["turni", "liberi"], "Responsabile")
    assert d == {"id": d["id"], "email": "capo@example.org", "nome": "Responsabile", "contenuti": ["turni", "liberi"],
                 "responsabile": False}
    r = client.put(f"/api/destinatari/{d['id']}", json={"email": "capo@example.org", "nome": "Capo",
                                                         "contenuti": ["statistiche"]})
    assert r.status_code == 200 and r.json()["contenuti"] == ["statistiche"] and r.json()["nome"] == "Capo"
    assert [x["email"] for x in client.get("/api/destinatari").json()] == ["capo@example.org"]
    assert client.delete(f"/api/destinatari/{d['id']}").status_code == 204
    assert client.get("/api/destinatari").json() == []
    assert client.delete(f"/api/destinatari/{d['id']}").status_code == 404


def test_destinatari_non_validi(client):
    aggiungi(client, "capo@example.org", ["turni"])
    assert client.post("/api/destinatari", json={"email": "capo@example.org", "contenuti": ["liberi"]}).status_code == 400
    assert client.post("/api/destinatari", json={"email": "altro@example.org", "contenuti": []}).status_code == 422
    assert client.post("/api/destinatari", json={"email": "altro@example.org", "contenuti": ["boh"]}).status_code == 422
    assert client.post("/api/destinatari", json={"email": "a@x.org,b@y.org", "contenuti": ["turni"]}).status_code == 422


def test_ognuno_riceve_solo_quello_che_ha_scelto(client, postino):
    mario = crea(client, "Mario")
    luca = crea(client, "Luca")
    turno(client, mario["id"], "2026-10-20", "Venarotta", "notte")
    client.put(f"/api/settimane/{LUNEDI}/indisponibilita",
               json={"persona_id": luca["id"], "turni": [{"data": "2026-10-22", "parte": "mattina"}]})
    client.post("/api/ferie", json={"persona_id": luca["id"], "dal": "2026-10-24", "al": "2026-10-24", "motivo": "malattia"})
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    aggiungi(client, "capo@example.org", ["turni", "liberi"])
    aggiungi(client, "segreteria@example.org", ["indisponibilita", "statistiche", "statistiche_indisponibilita"])

    r = client.post("/api/destinatari/invia", json={"data": LUNEDI})
    assert r.status_code == 200, r.text
    assert sorted(x["email"] for x in r.json()["inviate"]) == ["capo@example.org", "segreteria@example.org"]
    per = {m["To"]: m for m in postino.inviati}

    capo = contenuto(per["capo@example.org"])
    assert "Turni della settimana" in capo and "Venarotta" in capo and "Mario" in capo
    assert "Dipendenti liberi" in capo
    assert "Statistiche" not in capo and "Indisponibilità della settimana" not in capo
    assert "19/10" in per["capo@example.org"]["Subject"]

    seg = contenuto(per["segreteria@example.org"])
    assert "Indisponibilità della settimana" in seg and "Luca" in seg and "mattina" in seg.lower()
    assert "Malattia" in seg
    assert "Statistiche dei turni" in seg and "Statistiche delle indisponibilità" in seg
    assert "Acquasanta / Venarotta" in seg
    assert "Turni della settimana" not in seg and "Dipendenti liberi" not in seg


def test_settimana_in_bozza_e_segnalata(client, postino):
    mario = crea(client, "Mario")
    turno(client, mario["id"], "2026-10-20")
    aggiungi(client, "capo@example.org", ["turni"])
    client.post("/api/destinatari/invia", json={"data": LUNEDI})
    [m] = postino.inviati
    assert "bozza" in m["Subject"].lower()


def test_invio_senza_destinatari_o_senza_configurazione(client, tmp_path):
    assert client.post("/api/destinatari/invia", json={"data": LUNEDI}).status_code == 400

    class NonConfigurato:
        configurato = False
    c = TestClient(create_app(str(tmp_path / "n.db"), postino=NonConfigurato()))
    aggiungi(c, "capo@example.org", ["turni"])
    r = c.post("/api/destinatari/invia", json={"data": LUNEDI})
    assert r.status_code == 400 and "configurat" in r.json()["detail"]


def test_tutti_i_contenuti_insieme(client, postino):
    crea(client, "Mario")
    aggiungi(client, "tutto@example.org", TUTTI)
    client.post("/api/destinatari/invia", json={"data": LUNEDI})
    t = contenuto(postino.inviati[0])
    for titolo in ("Turni della settimana", "Dipendenti liberi", "Indisponibilità della settimana",
                   "Statistiche dei turni", "Statistiche delle indisponibilità"):
        assert titolo in t, titolo


# --- responsabili: ricevono turni e liberi con "Invia i turni via email" della settimana ---------

def test_il_responsabile_riceve_turni_e_liberi_con_l_invio_della_settimana(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    turno(client, mario["id"], "2026-10-20")
    aggiungi(client, "capo@example.org", ["statistiche"], "Capo", responsabile=True)
    aggiungi(client, "altro@example.org", ["turni"])  # non responsabile: con l'invio della settimana non riceve
    client.post(f"/api/settimane/{LUNEDI}/conferma")

    stato = client.get(f"/api/settimane/{LUNEDI}/email").json()
    assert [r["email"] for r in stato["responsabili"]] == ["capo@example.org"]

    r = client.post(f"/api/settimane/{LUNEDI}/email", json={}).json()
    assert sorted(x["email"] for x in r["inviate"]) == ["capo@example.org", "mario@example.org"]
    per = {m["To"]: m for m in postino.inviati}
    assert "altro@example.org" not in per
    capo = contenuto(per["capo@example.org"])
    assert "Turni della settimana" in capo and "Dipendenti liberi" in capo
    assert "Statistiche" not in capo  # con l'invio della settimana: solo turni e liberi


def test_il_responsabile_riceve_l_aggiornamento_solo_se_qualcosa_cambia(client, postino):
    mario = crea(client, "Mario", "mario@example.org")
    turno(client, mario["id"], "2026-10-20")
    aggiungi(client, "capo@example.org", ["turni"], responsabile=True)
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    client.post(f"/api/settimane/{LUNEDI}/email", json={})
    postino.inviati.clear()

    client.post(f"/api/settimane/{LUNEDI}/email", json={"solo_modifiche": True})
    assert postino.inviati == []

    client.post(f"/api/settimane/{LUNEDI}/riapri")
    turno(client, mario["id"], "2026-10-23", "Venarotta")
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    client.post(f"/api/settimane/{LUNEDI}/email", json={"solo_modifiche": True})
    per = {m["To"]: m for m in postino.inviati}
    assert set(per) == {"mario@example.org", "capo@example.org"}
    assert "aggiornamento" in per["capo@example.org"]["Subject"].lower()


def test_il_responsabile_riceve_anche_se_nessuno_del_personale_ha_l_email(client, postino):
    mario = crea(client, "Mario")
    turno(client, mario["id"], "2026-10-20")
    aggiungi(client, "capo@example.org", ["turni"], responsabile=True)
    client.post(f"/api/settimane/{LUNEDI}/conferma")
    r = client.post(f"/api/settimane/{LUNEDI}/email", json={}).json()
    assert [x["email"] for x in r["inviate"]] == ["capo@example.org"]
