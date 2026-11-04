"""Tabellone Generati consultabile e statistiche su settimane generate e confermate."""
from datetime import date, timedelta

import pytest

from cvap import db
from cvap.modello import Assegnazione

from .test_api_festivi import client, settimana_generata
from .test_api_storico_festivi import crea


@pytest.mark.parametrize("versione", ["generati", "effettivi"])
def test_saldo_e_settimane_escludono_bozze_e_settimane_manuali(client, versione):
    anna, bruno = [crea(client, nome)["id"] for nome in ("Anna", "Bruno")]
    w1, manuale, w2, bozza = [date(2026, 10, 19) + timedelta(weeks=i) for i in range(4)]
    # Prima settimana: Anna 12, Bruno 0, media 6 -> saldo +6 / -6.
    settimana_generata(client, w1, [anna, bruno], [(w1, "giorno", anna)])
    conn = db.apri(client.percorso_db)
    try:
        db.crea_assegnazione(conn, Assegnazione(manuale, "Acquasanta", "giorno", "intero", "autista", anna, "manuale"))
        db.imposta_stato(conn, manuale, "confermata")
    finally:
        conn.close()
    # Seconda generata: Bruno 12 -> i saldi cumulati tornano a zero.
    settimana_generata(client, w2, [anna, bruno], [(w2, "giorno", bruno)])
    settimana_generata(client, bozza, [anna, bruno], [(bozza, "giorno", anna)], confermata=False)
    righe = {r["persona_id"]: r for r in client.get("/api/statistiche", params={"versione": versione}).json()}
    for pid in (anna, bruno):
        assert righe[pid]["settimane"] == 2
        assert righe[pid]["ore_lavorate"] == 12
        assert righe[pid]["saldo_ore"] == 0
    equita = client.get("/api/statistiche/equita", params={"versione": versione}).json()
    assert equita["settimane"] == [w1.isoformat(), w2.isoformat()]
    ore = next(r for r in equita["rotazioni"] if r["chiave"] == "ore")
    assert ore["differenza"] == 0
    # Riaprendo una settimana, anche ore e saldo escono subito dalle statistiche.
    assert client.post(f"/api/settimane/{w2}/riapri").status_code == 200
    righe = {r["persona_id"]: r for r in client.get("/api/statistiche", params={"versione": versione}).json()}
    assert righe[anna]["settimane"] == righe[bruno]["settimane"] == 1
    assert righe[anna]["saldo_ore"] == 6
    assert righe[bruno]["saldo_ore"] == -6
    assert client.post(f"/api/settimane/{w2}/conferma").status_code == 200
    assert all(r["saldo_ore"] == 0 for r in client.get("/api/statistiche", params={"versione": versione}).json())


def test_tabellone_generato_separato_senza_scritture(client):
    anna, bruno = [crea(client, nome)["id"] for nome in ("Anna", "Bruno")]
    w = date(2026, 10, 19)
    settimana_generata(client, w, [anna, bruno], [(w, "giorno", anna)])
    conn = db.apri(client.percorso_db)
    try:
        aid, _ = db.assegnazioni_periodo(conn, w, w)[0]
        with conn:
            db.imposta_titolare_effettivo(conn, aid, bruno)
    finally:
        conn.close()
    prima = client.get(f"/api/settimane/{w}").json()
    r = client.get(f"/api/settimane/{w}/generati")
    assert r.status_code == 200, r.text
    generati = r.json()
    assert generati["versione"] == "generati"
    assert generati["sola_lettura"] is True
    assert [(a["id"], a["persona_id"]) for a in generati["assegnazioni"]] == [(aid, anna)]
    assert [(a["id"], a["persona_id"]) for a in prima["assegnazioni"]] == [(aid, bruno)]
    assert client.get(f"/api/settimane/{w}").json() == prima
    assert client.get(f"/api/settimane/{w + timedelta(days=2)}/generati").json() == generati


def test_bozza_non_conta_anche_se_ha_turni_generati(client):
    anna = crea(client, "Anna")["id"]
    w = date(2026, 10, 19)
    settimana_generata(client, w, [anna], [(w, "giorno", anna)], confermata=False)
    assert client.get("/api/statistiche").json() == []
    assert client.get("/api/statistiche/equita").json()["settimane"] == []
    # Consultazione disponibile anche prima della conferma.
    r = client.get(f"/api/settimane/{w}/generati")
    assert r.status_code == 200
    assert r.json()["stato"] == "bozza"
    assert r.json()["sola_lettura"] is True
