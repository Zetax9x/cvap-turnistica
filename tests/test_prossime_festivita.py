"""Fase 8 del piano rotazioni: ordine di rotazione delle prossime festività e storico per anno
(docs/PIANO-rotazioni.md, 3.7).

L'ordine usa lo stesso calcolo del generatore: con un solo posto libero, chi è primo nell'ordine riceve il turno.
"""
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import dati_festivi, db, prossime_festivita, solver  # noqa: E402
from cvap.modello import Assegnazione  # noqa: E402
from cvap.rotazione_festivi import ContoFestivita, ordine_rotazione  # noqa: E402

from .test_api_festivi import settimana_generata  # noqa: E402
from . import test_api_storico_festivi  # noqa: E402
from .test_api_storico_festivi import attiva, crea, salva, turno  # noqa: E402

client = test_api_storico_festivi.client  # fixture (sqlite e libsql)


def prossimo_natale() -> date:
    oggi = date.today()
    d = date(oggi.year, 12, 25)
    return d if d >= oggi else date(oggi.year + 1, 12, 25)


def prossime(client, **params):
    r = client.get("/api/festivita/prossime", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def storico_natale(client, natale, servizio, chi):
    """Anni importati: chi[anno] ha lavorato Natale di giorno; in servizio i dipendenti di `servizio`."""
    for anno, persone in chi.items():
        assert salva(client, anno, [turno(natale, p) for p in persone], servizio).status_code == 200


# --- modulo puro ------------------------------------------------------------------------------------------

def test_ordine_rotazione_come_il_generatore():
    # A l'ha fatta l'anno scorso, B due volte tempo fa, C due anni fa: per il solo debito A e C sarebbero pari e
    # primi, ma il generatore fa pagare di più chi l'ha fatta l'anno prima (e metà due anni prima)
    conti = {1: ContoFestivita(turni=1, esposizione=4, ultimo_anno=2025),
             2: ContoFestivita(turni=2, esposizione=4, ultimo_anno=2023),
             3: ContoFestivita(turni=1, esposizione=4, ultimo_anno=2024)}
    ordine = ordine_rotazione(conti, [1, 2, 3], peso=1, anno=2026, nomi={1: "A", 2: "B", 3: "C"})
    assert [pid for pid, _ in ordine] == [2, 3, 1]
    assert dict(ordine)[1] == pytest.approx(-1 / 3)


def test_ordine_rotazione_a_parita_chi_non_la_fa_da_piu_tempo_poi_nome():
    conti = {1: ContoFestivita(turni=1, esposizione=5, ultimo_anno=2021),
             2: ContoFestivita(turni=1, esposizione=5, ultimo_anno=2020),
             3: ContoFestivita(turni=0, esposizione=0),
             4: ContoFestivita(turni=0, esposizione=0)}
    # 3 e 4 hanno debito 0 come 1 e 2 (mai in servizio): prima chi non l'ha mai fatta, poi per nome
    ordine = ordine_rotazione(conti, [1, 2, 3, 4], peso=1, anno=2026, nomi={1: "A", 2: "B", 3: "Zeno", 4: "Ada"})
    assert [pid for pid, _ in ordine] == [4, 3, 2, 1]


# --- API ------------------------------------------------------------------------------------------------

def test_prossime_festivita_ordine_e_dettagli(client):
    d = prossimo_natale()
    y = d.year
    a, b, c = (crea(client, n)["id"] for n in ("Anna", "Bruno", "Carlo"))
    dd = crea(client, "Dario", qualifica="soccorritore")["id"]
    natale = attiva(client, "Natale")
    tutti = [a, b, c, dd]
    storico_natale(client, natale, tutti, {y - 4: [b], y - 3: [b], y - 2: [c], y - 1: [a]})

    voci = prossime(client)
    assert [v["nome"] for v in voci] == ["Natale"]
    v = voci[0]
    assert (v["data"], v["festivita_id"], v["peso"]) == (d.isoformat(), natale, 1)
    ordine = v["ordine"]
    # Dario mai; Bruno due volte ma non di recente; Carlo due anni fa; Anna l'anno scorso
    assert [x["nome"] for x in ordine] == ["Dario", "Bruno", "Carlo", "Anna"]
    per_nome = {x["nome"]: x for x in ordine}
    assert per_nome["Bruno"] == {"persona_id": b, "nome": "Bruno", "qualifica": "autista", "volte_5_anni": 2,
                                 "ultimo_anno": y - 3, "debito": 1.0, "disponibile": None, "assente": None}
    assert per_nome["Dario"]["qualifica"] == "soccorritore" and per_nome["Dario"]["ultimo_anno"] is None
    assert per_nome["Anna"]["debito"] == 0.0 and per_nome["Anna"]["volte_5_anni"] == 1


def test_prossime_festivita_disponibili_e_assenze(client):
    d = prossimo_natale()
    a, b, c, dd = (crea(client, n)["id"] for n in ("Anna", "Bruno", "Carlo", "Dario"))
    attiva(client, "Natale")
    assert client.put("/api/festivita/disponibili", json={"data": d.isoformat(), "persona_id": c,
                                                          "fascia": "notte"}).status_code == 200
    assert client.post("/api/ferie", json={"persona_id": a, "dal": (d - timedelta(days=2)).isoformat(),
                                           "al": d.isoformat()}).status_code == 201
    assert client.post("/api/ferie", json={"persona_id": b, "dal": d.isoformat(), "al": d.isoformat(),
                                           "motivo": "malattia"}).status_code == 201
    r = client.put(f"/api/settimane/{d.isoformat()}/indisponibilita",
                   json={"persona_id": dd, "turni": [{"data": d.isoformat(), "parte": "notte"}]})
    assert r.status_code == 200, r.text
    per_nome = {x["nome"]: x for x in prossime(client)[0]["ordine"]}
    assert per_nome["Carlo"]["disponibile"] == "notte" and per_nome["Carlo"]["assente"] is None
    assert per_nome["Anna"]["assente"] == "ferie"
    assert per_nome["Bruno"]["assente"] == "malattia"
    assert per_nome["Dario"]["assente"] == "indisponibile"


def test_prossime_festivita_solo_attive_dipendenti_attivi_e_mesi(client):
    a = crea(client, "Anna")["id"]
    crea(client, "Vol", tipo="volontario")
    ex = crea(client, "Ex")["id"]
    assert client.put(f"/api/persone/{ex}", json={"nome": "Ex", "tipo": "dipendente", "qualifica": "autista",
                                                  "attivo": False}).status_code == 200
    assert prossime(client) == []
    attiva(client, "Natale")
    attiva(client, "Ferragosto")
    voci = prossime(client, mesi=24)
    assert sorted(v["nome"] for v in voci) == ["Ferragosto", "Ferragosto", "Natale", "Natale"]
    assert [v["data"] for v in voci] == sorted(v["data"] for v in voci)
    assert all([x["persona_id"] for x in v["ordine"]] == [a] for v in voci)
    assert len(prossime(client)) == 2
    for mesi in (0, 25, "x"):
        assert client.get("/api/festivita/prossime", params={"mesi": mesi}).status_code == 422


def test_l_ordine_coincide_con_l_assegnazione_del_generatore(client):
    """Natale 2026 con un solo posto libero (il giorno da autista): lo riceve chi è primo nell'ordine."""
    a, b, c = (crea(client, n)["id"] for n in ("Anna", "Bruno", "Carlo"))
    natale = attiva(client, "Natale")
    storico_natale(client, natale, [a, b, c], {2022: [b], 2023: [b], 2024: [c], 2025: [a]})
    conn = db.apri(client.percorso_db)
    try:
        voce = next(v for v in prossime_festivita.prossime(conn, date(2026, 11, 1), 2) if v["nome"] == "Natale")
        assert voce["data"] == "2026-12-25"
        primo = voce["ordine"][0]["persona_id"]
        assert primo == b  # per il solo debito sarebbero primi Anna e Carlo

        giorni = [date(2026, 12, 25)]
        volontario = 9999  # gli altri posti sono già coperti da volontari
        fissi = [Assegnazione(giorni[0], "Acquasanta", f, "intero", r, volontario, "volontario")
                 for f, r in (("giorno", "soccorritore"), ("notte", "autista"), ("notte", "soccorritore"))]
        fs = dati_festivi.festivi_per_generazione(conn, giorni)
        ris = solver.genera(giorni, ["Acquasanta"], db.dipendenti_attivi(conn), fissi=fissi, festivi=fs,
                            tempo_max=10)
    finally:
        conn.close()
    assert ris.scoperti == []
    assert [x.persona_id for x in ris.assegnazioni] == [primo]


def test_storico_per_anno_importato_e_dal_programma(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    vol = crea(client, "Vol", tipo="volontario")["id"]
    natale = attiva(client, "Natale")
    prima = date(2026, 10, 19)
    settimana_generata(client, prima, [mario, luigi], [(prima, "giorno", mario)])
    assert salva(client, 2025, [turno(natale, mario), turno(natale, luigi, "notte")], [mario, luigi]).status_code == 200
    settimana_generata(client, date(2026, 12, 21), [mario, luigi],
                       [(date(2026, 12, 25), "giorno", luigi), (date(2026, 12, 25), "notte", vol)])

    r = client.get("/api/festivita/lavorate", params={"anno": 2025})
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["anno"] == 2025 and 2025 in x["anni"] and 2026 in x["anni"]
    voce = next(f for f in x["festivita"] if f["nome"] == "Natale")
    assert voce["fonte"] == "importato" and voce["data"] == "2025-12-25"
    assert voce["giorno"] == [{"persona_id": mario, "nome": "Mario Rossi"}]
    assert voce["notte"] == [{"persona_id": luigi, "nome": "Luigi Bianchi"}]

    voce = next(f for f in client.get("/api/festivita/lavorate", params={"anno": 2026}).json()["festivita"]
                if f["nome"] == "Natale")
    assert voce["fonte"] == "programma"
    assert voce["giorno"] == [{"persona_id": luigi, "nome": "Luigi Bianchi"}]
    assert voce["notte"] == []  # i volontari non entrano nella rotazione
    assert client.get("/api/festivita/lavorate", params={"anno": 1999}).status_code == 422


def test_storico_per_anno_importato_solo_dipendenti(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    natale = attiva(client, "Natale")
    assert salva(client, 2024, [turno(natale, mario), turno(natale, luigi)], [mario, luigi]).status_code == 200
    # Luigi ora è un volontario: non entra nella rotazione e non compare
    assert client.put(f"/api/persone/{luigi}", json={"nome": "Luigi Bianchi", "tipo": "volontario",
                                                     "qualifica": "autista", "attivo": True}).status_code == 200
    voce = next(f for f in client.get("/api/festivita/lavorate", params={"anno": 2024}).json()["festivita"]
                if f["nome"] == "Natale")
    assert voce["giorno"] == [{"persona_id": mario, "nome": "Mario Rossi"}]
