"""Statistiche delle indisponibilità: quante volte ogni dipendente le chiede per giorno della settimana."""
from datetime import timedelta

from fastapi.testclient import TestClient

from cvap.app import create_app
from cvap.storico import indisponibilita_per_giorno

from .conftest import LUNEDI_A


def giorno(i):
    return LUNEDI_A + timedelta(days=i)


VUOTO = {"totale": 0, "mattina": 0, "pomeriggio": 0, "notte": 0}


# --- funzione pura -------------------------------------------------------------------

def test_sette_colonne_dal_lunedi_alla_domenica_anche_senza_richieste():
    assert indisponibilita_per_giorno(set()) == [VUOTO] * 7


def test_conta_i_giorni_e_le_parti_per_giorno_della_settimana():
    richieste = {
        (giorno(0), "mattina"), (giorno(0), "notte"),   # lunedì: un giorno, due parti
        (giorno(7), "mattina"),                          # lunedì della settimana dopo
        (giorno(4), "pomeriggio"),                       # venerdì
    }
    r = indisponibilita_per_giorno(richieste)
    assert r[0] == {"totale": 2, "mattina": 2, "pomeriggio": 0, "notte": 1}
    assert r[4] == {"totale": 1, "mattina": 0, "pomeriggio": 1, "notte": 0}
    assert r[6] == VUOTO


# --- API -------------------------------------------------------------------------------

def _client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def _crea(client, nome, tipo="dipendente"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": "autista"})
    assert r.status_code == 201, r.text
    return r.json()


def _indisponibile(client, persona_id, turni):
    lunedi = turni[0][0] - timedelta(days=turni[0][0].weekday())
    r = client.put(f"/api/settimane/{lunedi.isoformat()}/indisponibilita", json={
        "persona_id": persona_id, "turni": [{"data": d.isoformat(), "parte": p} for d, p in turni]})
    assert r.status_code == 200, r.text


def test_statistiche_indisponibilita_per_dipendente(tmp_path):
    client = _client(tmp_path)
    mario, anna = _crea(client, "Mario"), _crea(client, "Anna")
    _crea(client, "Vito", "volontario")
    _indisponibile(client, mario["id"], [(giorno(2), "mattina"), (giorno(2), "pomeriggio")])
    _indisponibile(client, mario["id"], [(giorno(9), "notte")])  # mercoledì della settimana dopo
    r = client.get("/api/statistiche/indisponibilita")
    assert r.status_code == 200, r.text
    righe = r.json()
    # solo dipendenti, in ordine di nome; anche chi non ne ha chiesta nessuna
    assert [x["nome"] for x in righe] == ["Anna", "Mario"]
    m = righe[1]
    assert m["persona_id"] == mario["id"] and m["totale"] == 2
    assert m["giorni"][2] == {"totale": 2, "mattina": 1, "pomeriggio": 1, "notte": 1}
    assert righe[0]["persona_id"] == anna["id"]
    assert righe[0]["totale"] == 0 and righe[0]["giorni"] == [VUOTO] * 7


def test_statistiche_indisponibilita_in_un_periodo(tmp_path):
    client = _client(tmp_path)
    mario = _crea(client, "Mario")
    _indisponibile(client, mario["id"], [(giorno(1), "notte")])
    _indisponibile(client, mario["id"], [(giorno(8), "notte")])
    r = client.get("/api/statistiche/indisponibilita",
                   params={"dal": giorno(7).isoformat(), "al": giorno(13).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()[0]["totale"] == 1


def test_statistiche_indisponibilita_periodo_non_valido(tmp_path):
    client = _client(tmp_path)
    r = client.get("/api/statistiche/indisponibilita", params={"dal": "2026-11-10", "al": "2026-11-01"})
    assert r.status_code == 400
    assert client.get("/api/statistiche/indisponibilita", params={"dal": "ieri"}).status_code == 422


def test_dipendente_disattivato_compare_solo_se_ha_indisponibilita(tmp_path):
    client = _client(tmp_path)
    mario, luca = _crea(client, "Mario"), _crea(client, "Luca")
    _indisponibile(client, mario["id"], [(giorno(5), "mattina")])
    for p in (mario, luca):
        client.put(f"/api/persone/{p['id']}", json={**p, "attivo": False})
    assert [x["nome"] for x in client.get("/api/statistiche/indisponibilita").json()] == ["Mario"]
