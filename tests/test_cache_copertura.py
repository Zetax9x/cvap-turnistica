"""Cache dei controlli di copertura: riuso tra una richiesta e l'altra, invalidata da ogni scrittura."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import app as api  # noqa: E402
from cvap.cache_copertura import CacheCopertura  # noqa: E402


class Orologio:
    def __init__(self):
        self.ora = 0.0

    def __call__(self) -> float:
        return self.ora


def test_il_risultato_si_calcola_una_volta_sola():
    cache, chiamate = CacheCopertura(), []

    def calcola():
        chiamate.append(1)
        return {"stato": "copribile"}

    assert cache.prendi("a", calcola) == cache.prendi("a", calcola) == {"stato": "copribile"}
    assert len(chiamate) == 1


def test_chiavi_diverse_si_calcolano_separate():
    cache = CacheCopertura()
    assert cache.prendi(("a", False), lambda: 1) == 1
    assert cache.prendi(("a", True), lambda: 2) == 2


def test_invalida_forza_il_ricalcolo():
    cache = CacheCopertura()
    cache.prendi("a", lambda: 1)
    cache.invalida()
    assert cache.prendi("a", lambda: 2) == 2


def test_il_risultato_scade():
    orologio = Orologio()
    cache = CacheCopertura(scadenza_s=60, orologio=orologio)
    cache.prendi("a", lambda: 1)
    orologio.ora = 59
    assert cache.prendi("a", lambda: 2) == 1
    orologio.ora = 61
    assert cache.prendi("a", lambda: 3) == 3


def test_un_calcolo_interrotto_da_una_modifica_non_resta_in_cache():
    cache = CacheCopertura()

    def calcola_mentre_i_dati_cambiano():
        cache.invalida()  # un'altra richiesta scrive mentre il solver lavora
        return "vecchio"

    assert cache.prendi("a", calcola_mentre_i_dati_cambiano) == "vecchio"
    assert cache.prendi("a", lambda: "nuovo") == "nuovo"


@pytest.fixture
def client(tmp_path):
    return TestClient(api.create_app(str(tmp_path / "t.db")))


def conta_controlli(monkeypatch):
    chiamate = []

    def controllo(conn, inizio, con_volontari):
        chiamate.append((inizio, con_volontari))
        return {"stato": "copribile", "scoperti": []}

    monkeypatch.setattr(api, "_copertura_preventiva", controllo)
    return chiamate


def test_il_calendario_riusa_i_controlli_finche_i_dati_non_cambiano(client, monkeypatch):
    chiamate = conta_controlli(monkeypatch)
    prima = client.get("/api/calendario-copertura?mese=2026-10")
    assert prima.status_code == 200, prima.text
    controlli = 2 * len(prima.json()["settimane"])  # due scenari per settimana
    assert len(chiamate) == controlli

    seconda = client.get("/api/calendario-copertura?mese=2026-10")
    assert seconda.json() == prima.json()
    assert len(chiamate) == controlli  # tutto dalla cache


def test_il_mese_vicino_riusa_le_settimane_in_comune(client, monkeypatch):
    chiamate = conta_controlli(monkeypatch)
    client.get("/api/calendario-copertura?mese=2026-10")
    prima = len(chiamate)
    novembre = client.get("/api/calendario-copertura?mese=2026-11").json()
    nuove = len(chiamate) - prima
    assert nuove == 2 * len(novembre["settimane"]) - 2  # la settimana a cavallo dei due mesi (2 scenari) c'è già


def test_una_scrittura_svuota_la_cache(client, monkeypatch):
    chiamate = conta_controlli(monkeypatch)
    controlli = 2 * len(client.get("/api/calendario-copertura?mese=2026-10").json()["settimane"])
    r = client.post("/api/persone", json={"nome": "Nuovo", "tipo": "dipendente", "qualifica": "autista"})
    assert r.status_code == 201, r.text
    client.get("/api/calendario-copertura?mese=2026-10")
    assert len(chiamate) == 2 * controlli  # ricalcolato dopo la modifica


def test_una_scrittura_rifiutata_svuota_comunque_la_cache(client, monkeypatch):
    chiamate = conta_controlli(monkeypatch)
    controlli = 2 * len(client.get("/api/calendario-copertura?mese=2026-10").json()["settimane"])
    assert client.post("/api/persone", json={}).status_code == 422
    client.get("/api/calendario-copertura?mese=2026-10")
    assert len(chiamate) == 2 * controlli  # meglio ricalcolare che rischiare dati vecchi
