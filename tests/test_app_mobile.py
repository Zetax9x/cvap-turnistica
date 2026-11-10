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


def test_pdf_dei_turni_di_un_dipendente(client):
    p = client.post("/api/persone", json={"nome": "Rossi Marco", "tipo": "dipendente", "qualifica": "autista"}).json()
    r = client.get(f"/api/settimane/2026-11-02/pdf/{p['id']}")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert client.get("/api/settimane/2026-11-02/pdf/9999").status_code == 404


def _esportati(testo: str) -> set[str]:
    nomi = set(re.findall(r"export\s+(?:async\s+)?(?:function|class|const|let)\s+(\w+)", testo))
    for blocco in re.findall(r"export\s*\{([^}]*)\}", testo):
        nomi |= {n.split(" as ")[-1].strip() for n in blocco.split(",") if n.strip()}
    if re.search(r"export\s+default", testo):
        nomi.add("default")
    return nomi


def test_ogni_nome_importato_e_esportato_dal_modulo(client):
    """Un nome importato che il modulo non esporta fa fallire l'app solo quando la schermata si apre."""
    statici = RADICE.parent
    for js in (RADICE / "js").glob("*.js"):
        for nomi, origine in re.findall(r'import\s*\{([^}]*)\}\s*from\s*"([^"]+)"', js.read_text(encoding="utf-8")):
            if origine.startswith("./"):
                file = RADICE / "js" / origine[2:]
            elif origine.startswith("/static/"):
                file = statici / origine[len("/static/"):]
            else:
                continue
            esportati = _esportati(file.read_text(encoding="utf-8"))
            for n in (x.split(" as ")[0].strip() for x in nomi.split(",") if x.strip()):
                assert n in esportati, f"{js.name} importa «{n}» da {origine}, che non lo esporta"


def test_pdf_di_tabellone_e_liberi(client):
    """Anche con turni, volontari, Extra e festività il PDF si costruisce."""
    for i in range(4):
        client.post("/api/persone", json={"nome": f"Dip {i}", "tipo": "dipendente", "qualifica": "autista" if i % 2 == 0 else "soccorritore"})
    post = client.get("/api/postazioni").json()[0]["nome"]
    client.post("/api/settimane/2026-11-02/assegnazioni", json={
        "data": "2026-11-03", "postazione": post, "fascia": "giorno", "segmento": "intero", "ruolo": "autista", "persona_id": 1})
    client.post("/api/settimane/2026-11-02/assegnazioni", json={
        "data": "2026-11-03", "postazione": post, "fascia": "giorno", "segmento": "intero", "ruolo": "soccorritore",
        "nome_volontario": "Volo Test"})
    client.post("/api/settimane/2026-11-02/extra", json={
        "data": "2026-11-04", "nome": "Gara", "inizio": 8, "fine": 14, "autisti": 1, "soccorritori": 1})
    for percorso in ("pdf-tabellone", "pdf-tabellone?versione=generati", "pdf-liberi"):
        r = client.get(f"/api/settimane/2026-11-02/{percorso}")
        assert r.status_code == 200, percorso
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF") and len(r.content) > 1500


def test_i_fogli_con_liste_lunghe_scorrono_e_non_trascinano_lo_sfondo():
    """Senza queste regole una lista lunga viene compressa e tagliata, e il dito scorre la pagina sotto."""
    css = (RADICE / "app.css").read_text(encoding="utf-8")
    corpo = re.search(r"\.foglio-corpo\s*\{([^}]*)\}", css).group(1)
    assert "overflow-y: auto" in corpo and "min-height: 0" in corpo and "overscroll-behavior: contain" in corpo
    assert re.search(r"\.foglio-corpo\s*>\s*\*\s*\{[^}]*flex-shrink:\s*0", css)
    assert re.search(r"body\.foglio-aperto\s+\.schermata\s*\{[^}]*overflow:\s*hidden", css)
    assert "foglio-aperto" in (RADICE / "js" / "ui.js").read_text(encoding="utf-8")
