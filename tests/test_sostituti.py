"""Sostituti: chi può coprire un turno già assegnato (ad es. di chi va in malattia)."""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap.app import create_app  # noqa: E402
from cvap.modello import Assegnazione, Divieto, Persona  # noqa: E402
from cvap.sostituti import candidati_sostituzione  # noqa: E402

LUN = date(2026, 10, 19)  # settimana A
GIORNI = [LUN + timedelta(days=i) for i in range(7)]
SEDE = "Acquasanta"
ALTRA = "Venarotta"


def persona(pid, nome, qualifica="autista", tipo="dipendente", **kw):
    return Persona(pid, nome, tipo, qualifica, **kw)


def turno(pid, giorno=0, fascia="giorno", ruolo="soccorritore", postazione=SEDE, segmento="intero"):
    return Assegnazione(LUN + timedelta(days=giorno), postazione, fascia, segmento, ruolo, pid)


def calcola(da_coprire, assegnazioni, persone, **kw):
    return candidati_sostituzione(da_coprire, [p.id for p in persone.values() if p.dipendente],
                                  giorni=GIORNI, postazioni=[SEDE, ALTRA], assegnazioni=assegnazioni,
                                  persone=persone, **kw)


def ids(candidati):
    return [c.persona_id for c in candidati]


# --- funzione pura ------------------------------------------------------------------

def test_propone_chi_e_libero_e_non_chi_e_assente():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Libero"), 3: persona(3, "In ferie")}
    t = turno(1)
    out = calcola(t, [t], persone, ferie={1: {LUN}, 3: {LUN}})
    assert ids(out) == [2]


def test_esclude_chi_non_rispetta_riposo_o_si_sovrappone():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Notte prima"), 3: persona(3, "Stesso turno"),
               4: persona(4, "Libero")}
    t = turno(1, giorno=1)
    notte_prima = turno(2, giorno=0, fascia="notte")           # finisce alle 8 del giorno del turno
    stesso = turno(3, giorno=1, ruolo="autista")               # già in servizio nelle stesse ore
    out = calcola(t, [t, notte_prima, stesso], persone)
    assert ids(out) == [4]


def test_esclude_divieti_qualifica_e_indisponibili():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Divieto", divieti=(Divieto(SEDE, "giorno"),)),
               3: persona(3, "Soccorritore", qualifica="soccorritore"), 4: persona(4, "Indisponibile"),
               5: persona(5, "Volontario", tipo="volontario"), 6: persona(6, "Buono")}
    t = turno(1, ruolo="autista")
    out = candidati_sostituzione(t, [1, 2, 3, 4, 5, 6], giorni=GIORNI, postazioni=[SEDE], assegnazioni=[t],
                                 persone=persone, indisponibili={4: {(LUN, "mattina")}})
    assert ids(out) == [6]


def test_esclude_chi_supererebbe_tre_di_fila_o_il_massimo_ore():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Tre giorni"), 3: persona(3, "Tetto", max_ore_settimana=12),
               4: persona(4, "Libero")}
    t = turno(1, giorno=3)
    gia = [turno(2, giorno=g, postazione=ALTRA) for g in (0, 1, 2)] + [turno(3, giorno=5)]
    out = calcola(t, [t, *gia], persone)
    assert ids(out) == [4]


def test_ordina_per_ore_e_mette_in_fondo_chi_ha_avvisi():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Tante ore"), 3: persona(3, "Poche ore"),
               4: persona(4, "Due di fila")}
    t = turno(1, giorno=3)
    gia = [turno(2, giorno=g, postazione=ALTRA) for g in (5, 6)]
    gia += [turno(4, giorno=1, postazione=ALTRA), turno(4, giorno=2, postazione=ALTRA)]  # con il 3: tre di fila
    out = calcola(t, [t, *gia], persone)
    assert ids(out) == [3, 2, 4]
    poche = out[0]
    assert (poche.nome, poche.ore, poche.ore_dopo, poche.avvisi) == ("Poche ore", 0, 12, ())
    assert any("di fila" in a for a in out[2].avvisi)


def test_le_ferie_contano_nelle_ore_per_l_ordine():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Ferie due giorni"), 3: persona(3, "Un turno")}
    t = turno(1, giorno=0)
    out = calcola(t, [t, turno(3, giorno=4)], persone, ferie={1: {LUN}, 2: {GIORNI[5], GIORNI[6]}})
    # 12 h contate per entrambi: a pari ore conta il nome
    assert ids(out) == [2, 3]
    assert (out[0].ore, out[0].ore_contate) == (0, 12)


def test_superare_la_differenza_ore_e_un_avviso_non_un_esclusione():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Pieno"), 3: persona(3, "Vuoto")}
    t = turno(1, giorno=6)
    gia = [turno(2, giorno=g) for g in (0, 2, 4)]   # 36 h; con il turno 48 h, Vuoto resta a 0
    out = calcola(t, [t, *gia], persone, ferie={1: {GIORNI[6]}})
    pieno = next(c for c in out if c.persona_id == 2)
    assert any("Differenza" in a for a in pieno.avvisi)


def test_turno_che_non_e_nella_settimana_da_errore():
    with pytest.raises(ValueError):
        calcola(turno(1), [], {1: persona(1, "X")})


# --- API ----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(client, nome, qualifica="autista", tipo="dipendente"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def prenota(client, persona_id, data="2026-10-20", fascia="giorno", ruolo="soccorritore"):
    r = client.post("/api/settimane/2026-10-19/assegnazioni", json={
        "data": data, "postazione": SEDE, "fascia": fascia, "segmento": "intero", "ruolo": ruolo,
        "persona_id": persona_id})
    assert r.status_code == 201, r.text
    return next(a["id"] for a in r.json()["assegnazioni"]
                if a["persona_id"] == persona_id and a["data"] == data and a["fascia"] == fascia)


def test_api_sostituti_di_chi_va_in_malattia(client):
    malato, libero, notte = crea(client, "Malato"), crea(client, "Libero"), crea(client, "Notte")
    aid = prenota(client, malato)
    prenota(client, notte, data="2026-10-19", fascia="notte")
    client.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-21",
                                    "motivo": "malattia"})
    r = client.get(f"/api/assegnazioni/{aid}/sostituti")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assenza"] == "malattia"
    assert body["turno"]["id"] == aid and body["turno"]["persona_nome"] == "Malato"
    assert [c["persona_id"] for c in body["candidati"]] == [libero]
    assert body["candidati"][0] == {"persona_id": libero, "nome": "Libero", "qualifica": "autista", "ore": 0,
                                    "ore_contate": 0, "ore_dopo": 12, "avvisi": []}


def test_api_sostituisci_scambia_la_persona(client):
    malato, libero = crea(client, "Malato"), crea(client, "Libero")
    aid = prenota(client, malato)
    r = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": libero})
    assert r.status_code == 200, r.text
    turni = [(a["persona_id"], a["data"], a["origine"]) for a in r.json()["assegnazioni"]]
    assert turni == [(libero, "2026-10-20", "manuale")]


def test_api_sostituisci_rifiuta_casi_non_validi(client):
    malato, socc = crea(client, "Malato"), crea(client, "Socc", qualifica="soccorritore")
    spento = crea(client, "Spento")
    client.put(f"/api/persone/{spento}", json={"nome": "Spento", "tipo": "dipendente", "qualifica": "autista",
                                                "attivo": False})
    aid = prenota(client, malato, ruolo="autista")
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": socc}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": spento}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": malato}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": 9999}).status_code == 404
    assert client.post("/api/assegnazioni/9999/sostituisci", json={"persona_id": socc}).status_code == 404
    assert client.get("/api/assegnazioni/9999/sostituti").status_code == 404
    # la sostituzione fallita non tocca il turno
    s = client.get("/api/settimane/2026-10-19").json()
    assert [a["persona_id"] for a in s["assegnazioni"]] == [malato]


def test_api_sostituisci_in_settimana_confermata(client):
    malato, libero = crea(client, "Malato"), crea(client, "Libero")
    aid = prenota(client, malato)
    client.post("/api/settimane/2026-10-19/conferma")
    assert client.get(f"/api/assegnazioni/{aid}/sostituti").status_code == 200   # i suggerimenti si vedono
    r = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": libero})
    assert r.status_code == 400 and "riaprila" in r.json()["detail"]


def test_api_turni_coinvolti_da_un_assenza(client):
    malato, altro = crea(client, "Malato"), crea(client, "Altro")
    prenota(client, malato, data="2026-10-20")
    prenota(client, malato, data="2026-10-23")
    prenota(client, altro, data="2026-10-21")
    f = client.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-21",
                                        "motivo": "malattia"}).json()
    r = client.get(f"/api/ferie/{f['id']}/turni")
    assert r.status_code == 200, r.text
    assert [(t["data"], t["settimana"], t["postazione"]) for t in r.json()] == [("2026-10-20", "2026-10-19", SEDE)]
    assert client.get("/api/ferie/9999/turni").status_code == 404
