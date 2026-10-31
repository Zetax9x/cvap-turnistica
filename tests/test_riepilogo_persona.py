"""Statistiche → Riepilogo per dipendente: i turni svolti in un periodo, giorno per giorno, e i totali."""
import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

LUNEDI = "2026-10-26"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(c, nome, tipo="dipendente", qualifica="autista"):
    r = c.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def turno(c, pid, data, postazione="Acquasanta", fascia="giorno", segmento="intero", ruolo="autista"):
    r = c.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={
        "data": data, "postazione": postazione, "fascia": fascia, "segmento": segmento, "ruolo": ruolo,
        "persona_id": pid})
    assert r.status_code == 201, r.text


def riepilogo(c, pid, dal="2026-10-26", al="2026-11-01"):
    return c.get(f"/api/statistiche/persona/{pid}", params={"dal": dal, "al": al})


def test_turni_giorno_per_giorno_e_totali(client):
    pid = crea(client, "Rino")
    turno(client, pid, "2026-10-26")                                   # lun giorno 12 h Acquasanta
    turno(client, pid, "2026-10-28", "Venarotta", "notte")             # mer notte 12 h
    turno(client, pid, "2026-10-31", "Venarotta", segmento="mattina")  # sab mattina 6 h
    client.post("/api/ferie", json={"persona_id": pid, "dal": "2026-10-29", "al": "2026-10-29", "motivo": "malattia"})
    client.put(f"/api/settimane/{LUNEDI}/indisponibilita",
               json={"persona_id": pid, "turni": [{"data": "2026-11-01", "parte": "notte"}]})
    r = riepilogo(client, pid)
    assert r.status_code == 200, r.text
    x = r.json()
    assert (x["nome"], x["dal"], x["al"]) == ("Rino", "2026-10-26", "2026-11-01")
    giorni = {g["data"]: g for g in x["giorni"]}
    assert len(x["giorni"]) == 7  # tutti i giorni del periodo, dall'alto in basso
    [t] = giorni["2026-10-26"]["turni"]
    assert (t["postazione"], t["orario"], t["ruolo"], t["ore"], t["fascia"]) == \
        ("Acquasanta", "Giorno 8–20", "Autista", 12, "giorno")
    assert giorni["2026-10-28"]["turni"][0]["orario"] == "Notte 20–8"
    assert giorni["2026-10-31"]["turni"][0]["orario"] == "Mattina 8–14"
    assert giorni["2026-10-29"]["assenza"] == "malattia"
    assert giorni["2026-11-01"]["indisponibile"] == ["notte"]
    assert giorni["2026-10-27"] == {"data": "2026-10-27", "turni": [], "assenza": None, "indisponibile": []}

    s = x["riepilogo"]
    assert s["turni"] == 3 and s["ore_lavorate"] == 30
    assert (s["ore_giorno"], s["ore_notte"]) == (18, 12)
    assert (s["turni_giorno"], s["turni_notte"]) == (2, 1)
    assert (s["giorni_ferie"], s["giorni_malattia"]) == (0, 1)
    assert s["ore_ferie_malattia"] == 6 and s["ore_totali"] == 36
    assert s["weekend"] == {"sab_giorno": 1, "sab_notte": 0, "dom_giorno": 0, "dom_notte": 0}
    assert s["postazioni"] == [{"postazione": "Acquasanta", "turni": 1, "ore": 12},
                               {"postazione": "Venarotta", "turni": 2, "ore": 18}]
    assert s["giorni_indisponibili"] == 1


def test_fuori_periodo_non_conta(client):
    pid = crea(client, "Rino")
    turno(client, pid, "2026-10-26")
    turno(client, pid, "2026-10-30")
    x = riepilogo(client, pid, dal="2026-10-27", al="2026-10-31").json()
    assert x["riepilogo"]["turni"] == 1 and len(x["giorni"]) == 5


def test_assistenze_con_il_nome_della_richiesta(client):
    pid = crea(client, "Rino")
    s = client.post(f"/api/settimane/{LUNEDI}/extra", json={
        "data": "2026-10-27", "nome": "Partita", "inizio": 15, "fine": 19, "autisti": 1, "soccorritori": 0}).json()
    turno(client, pid, "2026-10-27", "Assistenze ed Extra", segmento=s["extra"][0]["segmento"])
    x = riepilogo(client, pid).json()
    [t] = next(g for g in x["giorni"] if g["data"] == "2026-10-27")["turni"]
    assert t["postazione"] == "Partita (Assistenze ed Extra)" and t["orario"] == "Pomeriggio 15–19" and t["ore"] == 4
    assert x["riepilogo"]["postazioni"] == [{"postazione": "Assistenze ed Extra", "turni": 1, "ore": 4}]


@pytest.mark.parametrize("params", [
    {"dal": "2026-11-02", "al": "2026-11-01"},  # al prima di dal
    {"dal": "2025-01-01", "al": "2026-11-01"},  # più di un anno
    {"dal": "2026-10-26"},                      # manca al
])
def test_periodo_non_valido(client, params):
    pid = crea(client, "Rino")
    assert client.get(f"/api/statistiche/persona/{pid}", params=params).status_code in (400, 422)


def test_persona_inesistente(client):
    assert riepilogo(client, 999).status_code == 404
