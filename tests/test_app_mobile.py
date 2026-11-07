"""App per telefono (PWA in static/app): file serviti, manifest e service worker coerenti, accesso con password."""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cvap.app import create_app

RADICE = Path(__file__).resolve().parent.parent / "static" / "app"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def test_la_pagina_dell_app_si_apre(client):
    r = client.get("/app/")
    assert r.status_code == 200
    assert 'rel="manifest"' in r.text and "apple-mobile-web-app-capable" in r.text


def test_manifest_valido_e_icone_raggiungibili(client):
    r = client.get("/app/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["display"] == "standalone" and m["scope"] == "/app/" and m["start_url"].startswith(m["scope"])
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    for i in m["icons"]:
        assert client.get(i["src"]).status_code == 200


def test_icona_per_iphone_presente(client):
    assert client.get("/app/img/apple-touch-icon.png").status_code == 200


def test_service_worker_non_mette_in_cache_le_api(client):
    r = client.get("/app/sw.js")
    assert r.status_code == 200
    assert '"/api/"' in r.text  # le chiamate API vanno sempre in rete


def test_ogni_modulo_importato_esiste(client):
    """Una vista dichiarata in main.js o un modulo importato che manca romperebbe l'app solo a runtime."""
    for js in (RADICE / "js").glob("*.js"):
        for rel in re.findall(r'(?:from|import\()\s*"(\./[^"]+)"', js.read_text(encoding="utf-8")):
            assert (RADICE / "js" / rel).is_file(), f"{js.name} importa {rel}, che non esiste"
    assert client.get("/app/js/main.js").status_code == 200


def test_con_password_la_pagina_e_pubblica_ma_le_api_no(tmp_path):
    c = TestClient(create_app(str(tmp_path / "t.db"), password="segreta"))
    assert c.get("/app/").status_code == 200  # serve per mostrare la schermata della password
    assert c.get("/api/settimane/2026-11-02").status_code == 401
