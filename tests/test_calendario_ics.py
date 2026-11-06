"""Calendario dei turni per il telefono: un file .ics per dipendente, raggiungibile con un link segreto."""
import os
import re
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import calendario_ics  # noqa: E402
from cvap.app import create_app  # noqa: E402

LUNEDI = "2026-10-19"
LUNEDI_DOPO = "2026-10-26"
UTC = timezone.utc


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(client, nome, tipo="dipendente", qualifica="autista"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def turno(client, persona_id, data=LUNEDI, postazione="Acquasanta", fascia="giorno", segmento="intero",
          ruolo="autista"):
    r = client.post(f"/api/settimane/{data}/assegnazioni", json={
        "data": data, "postazione": postazione, "fascia": fascia, "segmento": segmento, "ruolo": ruolo,
        "persona_id": persona_id})
    assert r.status_code == 201, r.text


def conferma(client, settimana=LUNEDI):
    assert client.post(f"/api/settimane/{settimana}/conferma").status_code == 200


def percorso(client, persona_id):
    r = client.get(f"/api/calendari/{persona_id}")
    assert r.status_code == 200, r.text
    return r.json()["percorso"]


def eventi(testo: str) -> list[dict]:
    """Gli eventi del file, con le righe ripiegate riunite."""
    righe = testo.replace("\r\n ", "").split("\r\n")
    out, attuale = [], None
    for riga in righe:
        if riga == "BEGIN:VEVENT":
            attuale = {}
        elif riga == "END:VEVENT":
            out.append(attuale)
            attuale = None
        elif attuale is not None and ":" in riga:
            chiave, valore = riga.split(":", 1)
            attuale[chiave.split(";")[0]] = valore
    return out


# --- formato --------------------------------------------------------------------------------

def test_orari_in_utc_anche_al_cambio_dell_ora():
    # la notte del 24/10/2026 attraversa il ritorno all'ora solare: 20:00 CEST -> 08:00 CET
    assert calendario_ics.orari_utc(date(2026, 10, 24), "notte", "intero") == (
        datetime(2026, 10, 24, 18, tzinfo=UTC), datetime(2026, 10, 25, 7, tzinfo=UTC))
    assert calendario_ics.orari_utc(date(2026, 7, 1), "giorno", "intero") == (
        datetime(2026, 7, 1, 6, tzinfo=UTC), datetime(2026, 7, 1, 18, tzinfo=UTC))
    assert calendario_ics.orari_utc(date(2026, 1, 15), "giorno", "mattina") == (
        datetime(2026, 1, 15, 7, tzinfo=UTC), datetime(2026, 1, 15, 13, tzinfo=UTC))


def test_testo_speciale_e_righe_lunghe_secondo_lo_standard():
    lungo = "Con: " + ", ".join(f"Niccolò Collega {i} (soccorritore)" for i in range(8))
    evento = calendario_ics.Evento(uid="x@cvap", inizio=datetime(2026, 10, 19, 6, tzinfo=UTC),
                                   fine=datetime(2026, 10, 19, 18, tzinfo=UTC),
                                   titolo="Acquasanta; prova, uno", luogo="Acquasanta", descrizione=lungo + "\nRiga 2")
    testo = calendario_ics.componi("Mario Rossi", [evento], adesso=datetime(2026, 10, 1, tzinfo=UTC))
    assert testo.startswith("BEGIN:VCALENDAR\r\n") and testo.endswith("END:VCALENDAR\r\n")
    assert all(len(r.encode()) <= 75 for r in testo.split("\r\n"))
    [e] = eventi(testo)
    assert e["SUMMARY"] == r"Acquasanta\; prova\, uno"
    assert e["DESCRIPTION"] == calendario_ics.testo_ics(lungo) + r"\nRiga 2"
    assert e["DTSTART"] == "20261019T060000Z" and e["DTEND"] == "20261019T180000Z"


def test_nome_nel_link_senza_accenti_e_spazi():
    assert calendario_ics.slug("Niccolò D'Angelo") == "niccolo-d-angelo"
    assert calendario_ics.slug("  ÀÉ  ") == "ae"
    assert calendario_ics.slug("***") == "dipendente"


# --- API ------------------------------------------------------------------------------------

def test_link_con_nome_e_codice_segreto(client):
    pid = crea(client, "Mario Rossi")
    p = percorso(client, pid)
    assert re.fullmatch(r"/turni/mario-rossi-[0-9a-f]{20}\.ics", p)
    assert percorso(client, pid) == p  # resta lo stesso


def test_il_calendario_contiene_i_turni_delle_settimane_confermate(client):
    mario = crea(client, "Mario Rossi", qualifica="autista")
    luca = crea(client, "Luca Bianchi", qualifica="soccorritore")
    turno(client, mario)
    turno(client, luca, ruolo="soccorritore")
    turno(client, mario, data="2026-10-22", postazione="Venarotta", fascia="notte")
    conferma(client)
    r = client.get(percorso(client, mario))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "X-WR-CALNAME:Turni - Mario Rossi" in r.text
    giorno, notte = sorted(eventi(r.text), key=lambda e: e["DTSTART"])
    assert giorno["SUMMARY"] == "Acquasanta · Autista"
    assert (giorno["DTSTART"], giorno["DTEND"]) == ("20261019T060000Z", "20261019T180000Z")
    assert "Giorno 8–20" in giorno["DESCRIPTION"] and "Luca Bianchi (soccorritore)" in giorno["DESCRIPTION"]
    assert giorno["LOCATION"] == "Acquasanta"
    assert notte["SUMMARY"] == "Venarotta · Autista"
    assert (notte["DTSTART"], notte["DTEND"]) == ("20261022T180000Z", "20261023T060000Z")
    assert giorno["UID"] != notte["UID"]


def test_le_settimane_in_bozza_non_compaiono(client):
    mario = crea(client, "Mario Rossi")
    turno(client, mario)
    turno(client, mario, data=LUNEDI_DOPO)
    conferma(client)  # solo la prima settimana
    assert [e["DTSTART"][:8] for e in eventi(client.get(percorso(client, mario)).text)] == ["20261019"]


def test_l_identificativo_del_turno_resta_uguale(client):
    mario = crea(client, "Mario Rossi")
    turno(client, mario)
    conferma(client)
    p = percorso(client, mario)
    assert eventi(client.get(p).text)[0]["UID"] == eventi(client.get(p).text)[0]["UID"]


def test_il_link_funziona_senza_password_le_api_no(tmp_path):
    app = create_app(str(tmp_path / "t.db"), password="segreta")
    gestione = TestClient(app)
    assert gestione.post("/api/accesso", json={"password": "segreta"}).status_code == 200
    mario = crea(gestione, "Mario Rossi")
    p = percorso(gestione, mario)
    telefono = TestClient(app)  # senza il cookie dell'accesso
    assert telefono.get(p).status_code == 200
    assert telefono.get(f"/api/calendari/{mario}").status_code == 401


@pytest.mark.parametrize("finto", ["/turni/mario-rossi-0123456789abcdef0123.ics", "/turni/mario-rossi.ics",
                                   "/turni/mario-rossi-0123.ics", "/turni/qualcosa.txt"])
def test_link_sbagliato_404(client, finto):
    crea(client, "Mario Rossi")
    assert client.get(finto).status_code == 404


def test_il_nome_nel_link_non_conta_solo_il_codice(client):
    mario = crea(client, "Mario Rossi")
    codice = percorso(client, mario).rsplit("-", 1)[1]
    assert client.get(f"/turni/altro-nome-{codice}").status_code == 200
    assert client.get(f"/turni/{codice}").status_code == 200


def test_un_nuovo_link_disattiva_il_vecchio(client):
    mario = crea(client, "Mario Rossi")
    vecchio = percorso(client, mario)
    r = client.post(f"/api/calendari/{mario}/rigenera")
    assert r.status_code == 200
    nuovo = r.json()["percorso"]
    assert nuovo != vecchio
    assert client.get(vecchio).status_code == 404
    assert client.get(nuovo).status_code == 200


def test_dipendente_disattivato_non_ha_calendario(client):
    mario = crea(client, "Mario Rossi")
    p = percorso(client, mario)
    r = client.put(f"/api/persone/{mario}", json={"nome": "Mario Rossi", "tipo": "dipendente",
                                                  "qualifica": "autista", "attivo": False})
    assert r.status_code == 200, r.text
    assert client.get(p).status_code == 404


def test_solo_per_i_dipendenti(client):
    vol = crea(client, "Anna Verdi", tipo="volontario", qualifica="soccorritore")
    assert client.get(f"/api/calendari/{vol}").status_code == 400
    assert client.post(f"/api/calendari/{vol}/rigenera").status_code == 400
    assert client.get("/api/calendari/999").status_code == 404


def test_cancellare_la_persona_toglie_il_link(client):
    mario = crea(client, "Mario Rossi")
    p = percorso(client, mario)
    assert client.delete(f"/api/persone/{mario}").status_code == 204
    assert client.get(p).status_code == 404
