"""Email dell'equità: contenuto «equita» nei riepiloghi e invio automatico a ogni settimana generata confermata."""
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


def destinatario(c, email, contenuti):
    r = c.post("/api/destinatari", json={"email": email, "contenuti": contenuti})
    assert r.status_code == 201, r.text


def aspetta(postino, n, secondi=10):
    fine = time.monotonic() + secondi
    while len(postino.inviati) < n and time.monotonic() < fine:
        time.sleep(0.05)
    return postino.inviati


def genera_e_conferma(c, settimana=LUNEDI):
    assert c.post(f"/api/settimane/{settimana}/genera", json={"tempo_max": 3}).status_code == 200
    assert c.post(f"/api/settimane/{settimana}/conferma").status_code == 200


def test_alla_conferma_di_una_settimana_generata_arriva_l_email_dell_equita(client, postino):
    destinatario(client, "io@example.org", ["equita"])
    destinatario(client, "segreteria@example.org", ["turni"])  # non l'ha scelta: niente
    genera_e_conferma(client)
    inviati = aspetta(postino, 1)
    assert [m["To"] for m in inviati] == ["io@example.org"]
    testo = contenuto(inviati[0])
    assert inviati[0]["Subject"].startswith("Equità dei turni dopo la settimana dal 19/10")
    for sezione in ("Generazione della settimana", "Equità dei turni", "Statistiche dei turni",
                    "Statistiche delle indisponibilità", "Giorni e notti", "Sabato giorno", "Acquasanta e Venarotta",
                    "Autista 1", "Scarto"):
        assert sezione in testo, sezione


def test_niente_email_senza_turni_generati_o_senza_destinatari(client, postino):
    assert client.post(f"/api/settimane/{LUNEDI}/conferma").status_code == 200  # settimana senza turni generati
    destinatario(client, "io@example.org", ["turni"])
    genera_e_conferma(client, "2026-10-26")
    time.sleep(0.5)
    assert postino.inviati == []


def test_equita_tra_i_contenuti_dei_riepiloghi(client, postino):
    genera_e_conferma(client)
    destinatario(client, "io@example.org", ["statistiche", "equita"])
    postino.inviati.clear()
    r = client.post("/api/destinatari/invia", json={"data": LUNEDI})
    assert r.status_code == 200, r.text
    testo = contenuto(postino.inviati[0])
    assert "Equità dei turni" in testo and "Differenza tra chi è più avanti" in testo
