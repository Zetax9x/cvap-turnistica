"""Processi paralleli del generatore: tanti quanti i core della macchina (massimo 8), oppure scelti con CVAP_WORKER."""
import pytest
from fastapi.testclient import TestClient

from cvap import app as modulo_app
from cvap import solver
from cvap.app import create_app, worker_generatore


@pytest.fixture
def sei_core(monkeypatch):
    monkeypatch.delenv("CVAP_WORKER", raising=False)
    monkeypatch.setattr(modulo_app.os, "sched_getaffinity", lambda pid: set(range(6)), raising=False)


def test_senza_impostazione_usa_i_core_della_macchina(sei_core):
    assert worker_generatore() == 6


def test_senza_impostazione_non_supera_8(monkeypatch):
    monkeypatch.delenv("CVAP_WORKER", raising=False)
    monkeypatch.setattr(modulo_app.os, "sched_getaffinity", lambda pid: set(range(32)), raising=False)
    assert worker_generatore() == 8


def test_senza_sched_getaffinity_usa_cpu_count(monkeypatch):
    monkeypatch.delenv("CVAP_WORKER", raising=False)
    monkeypatch.delattr(modulo_app.os, "sched_getaffinity", raising=False)
    monkeypatch.setattr(modulo_app.os, "cpu_count", lambda: 2)
    assert worker_generatore() == 2


def test_cvap_worker_sceglie_il_numero(sei_core, monkeypatch):
    monkeypatch.setenv("CVAP_WORKER", " 4 ")
    assert worker_generatore() == 4


@pytest.mark.parametrize("valore", ["", "0", "-2", "tanti", "65", "3.5"])
def test_cvap_worker_non_valido_usa_i_core(sei_core, monkeypatch, valore):
    monkeypatch.setenv("CVAP_WORKER", valore)
    assert worker_generatore() == 6


def test_la_generazione_usa_quei_worker(sei_core, monkeypatch, tmp_path):
    monkeypatch.setenv("CVAP_WORKER", "3")
    chiamate = []

    def finto_genera(*args, **kwargs):
        chiamate.append(kwargs.get("workers"))
        return solver.Risultato("ottimo", messaggio="Tutti i posti sono già coperti.")

    monkeypatch.setattr(solver, "genera", finto_genera)
    client = TestClient(create_app(str(tmp_path / "t.db")))
    r = client.post("/api/settimane/2026-10-19/genera", json={})
    assert r.status_code == 200, r.text
    assert chiamate == [3]
