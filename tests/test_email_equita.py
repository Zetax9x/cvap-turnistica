"""Email dell'equità: un indirizzo a parte, invio automatico a ogni settimana generata confermata e invio a mano."""
import time

import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

from .test_email import LUNEDI, PostinoFinto, contenuto, crea


@pytest.fixture
def postino():
    return PostinoFinto()


@pytest.fixture
def client(tmp_path, postino):
    c = TestClient(create_app(str(tmp_path / "t.db"), postino=postino))
    for i in range(4):
        crea(c, f"Autista {i + 1}")
        crea(c, f"Soccorritore {i + 1}", qualifica="soccorritore")
    return c


def aspetta(postino, n, secondi=10):
    fine = time.monotonic() + secondi
    while len(postino.inviati) < n and time.monotonic() < fine:
        time.sleep(0.05)
    return postino.inviati


def genera_e_conferma(c, settimana=LUNEDI):
    assert c.post(f"/api/settimane/{settimana}/genera", json={"tempo_max": 3}).status_code == 200
    assert c.post(f"/api/settimane/{settimana}/conferma").status_code == 200


def test_indirizzo_si_imposta_e_si_toglie(client):
    assert client.get("/api/email-equita").json()["email"] is None
    assert client.put("/api/email-equita", json={"email": "io@example.org"}).json()["email"] == "io@example.org"
    assert client.put("/api/email-equita", json={"email": "non-valida"}).status_code == 422
    assert client.put("/api/email-equita", json={"email": None}).json()["email"] is None


def test_arriva_solo_all_indirizzo_impostato_e_non_ai_riepiloghi(client, postino):
    client.put("/api/email-equita", json={"email": "io@example.org"})
    client.post("/api/destinatari", json={"email": "segreteria@example.org", "contenuti": ["statistiche"]})
    genera_e_conferma(client)
    inviati = aspetta(postino, 1)
    time.sleep(0.3)
    assert [m["To"] for m in inviati] == ["io@example.org"]
    testo = contenuto(inviati[0])
    assert inviati[0]["Subject"].startswith("Equità dei turni dopo la settimana dal 19/10")
    for sezione in ("Generazione della settimana", "Equità dei turni", "Statistiche dei turni",
                    "Statistiche delle indisponibilità", "Giorni e notti", "Sabato giorno", "Acquasanta e Venarotta",
                    "Autista 1", "Scarto"):
        assert sezione in testo, sezione


def test_niente_email_senza_indirizzo_o_senza_turni_generati(client, postino):
    genera_e_conferma(client)  # nessun indirizzo impostato
    client.put("/api/email-equita", json={"email": "io@example.org"})
    assert client.post("/api/settimane/2026-10-26/conferma").status_code == 200  # senza turni generati
    time.sleep(0.5)
    assert postino.inviati == []


def test_l_equita_non_e_piu_tra_i_contenuti_dei_riepiloghi(client):
    r = client.post("/api/destinatari", json={"email": "a@example.org", "contenuti": ["equita"]})
    assert r.status_code == 422


def test_invio_a_mano(client, postino):
    assert client.post("/api/email-equita/prova").status_code == 400  # senza indirizzo
    client.put("/api/email-equita", json={"email": "io@example.org"})
    assert client.post("/api/email-equita/prova").status_code == 400  # nessuna settimana generata
    genera_e_conferma(client)
    aspetta(postino, 1)
    postino.inviati.clear()
    r = client.post("/api/email-equita/prova")
    assert r.status_code == 200, r.text
    assert r.json() == {"inviata": "io@example.org", "settimana": LUNEDI}
    assert [m["To"] for m in postino.inviati] == ["io@example.org"]
