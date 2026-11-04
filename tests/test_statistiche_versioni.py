"""La sorgente scelta segue lo stesso turno in tutte le statistiche."""
from datetime import date

from cvap import db, dati_festivi, prossime_festivita

from .test_api_festivi import client, settimana_generata, SETT_NATALE, NATALE
from .test_api_storico_festivi import attiva, crea, salva, turno


def prepara(client):
    anna, bruno = [crea(client, nome)["id"] for nome in ("Anna", "Bruno")]
    natale = attiva(client, "Natale")
    assert salva(client, 2025, [turno(natale, anna)], [anna, bruno]).status_code == 200
    settimana_generata(client, SETT_NATALE, [anna, bruno], [(NATALE, "giorno", anna)])
    conn = db.apri(client.percorso_db)
    with conn:
        aid, _ = db.assegnazioni_periodo(conn, NATALE, NATALE)[0]
        db.imposta_titolare_effettivo(conn, aid, bruno)
    conn.close()
    return anna, bruno, natale


def test_turni_riepilogo_ed_equita_usano_la_versione(client):
    anna, bruno, _ = prepara(client)
    for versione, titolare, altro in (("generati", anna, bruno), ("effettivi", bruno, anna)):
        r = client.get("/api/statistiche", params={"versione": versione})
        assert r.status_code == 200, r.text
        righe = {r["persona_id"]: r for r in r.json()}
        assert righe[titolare]["ore_lavorate"] == 12
        assert righe[altro]["ore_lavorate"] == 0
        r = client.get(f"/api/statistiche/persona/{titolare}", params={
            "dal": NATALE.isoformat(), "al": NATALE.isoformat(), "versione": versione})
        assert r.status_code == 200, r.text
        assert r.json()["riepilogo"]["ore_lavorate"] == 12
        r = client.get("/api/statistiche/equita", params={"versione": versione})
        assert r.status_code == 200, r.text
        ore = next(rot for rot in r.json()["rotazioni"] if rot["chiave"] == "ore")
        assert ore["piu_avanti"]["persona_id"] == titolare
    assert client.get("/api/statistiche").json() == client.get(
        "/api/statistiche", params={"versione": "effettivi"}).json()


def test_festivita_importate_comuni_e_programma_separato(client):
    anna, bruno, natale = prepara(client)
    conn = db.apri(client.percorso_db)
    try:
        for versione, a_attesi, b_attesi in (("generati", 2, 0), ("effettivi", 1, 1)):
            conti = dati_festivi.conti_festivita(conn, date(2027, 1, 1), versione=versione)[natale]
            assert conti[anna].turni == a_attesi
            assert conti[bruno].turni == b_attesi
            prossimo = next(f for f in prossime_festivita.prossime(
                conn, date(2027, 11, 1), 2, versione=versione) if f["festivita_id"] == natale)
            persone = {p["persona_id"]: p for p in prossimo["ordine"]}
            assert persone[anna]["volte_5_anni"] == a_attesi
            assert persone[bruno]["volte_5_anni"] == b_attesi
            r = client.get("/api/festivita/lavorate", params={"anno": 2026, "versione": versione})
            assert r.status_code == 200, r.text
            voce = next(f for f in r.json()["festivita"] if f["festivita_id"] == natale)
            assert [p["persona_id"] for p in voce["giorno"]] == [anna if versione == "generati" else bruno]
    finally:
        conn.close()


def test_versione_sconosciuta_rifiutata(client):
    for percorso, params in (("/api/statistiche/equita", {}),
                             ("/api/festivita/prossime", {}),
                             ("/api/festivita/lavorate", {"anno": 2026})):
        assert client.get(percorso, params={**params, "versione": "altra"}).status_code == 422
