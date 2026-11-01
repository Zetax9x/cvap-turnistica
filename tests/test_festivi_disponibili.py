"""Fase 7 del piano rotazioni: chi vuole lavorare una festività (docs/PIANO-rotazioni.md, 3.6).

Modulo puro (turni di chi è disponibile), generatore con modelli piccoli che il solver chiude all'ottimo (ogni scenario
è verificato anche senza lo sconto, per essere sicuri che la scelta dipenda da lui), API e payload della settimana.
"""
import os
from datetime import date, timedelta

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import solver  # noqa: E402
from cvap.rotazione_festivi import ContoFestivita, festivi_settimana, turni_disponibili  # noqa: E402
from cvap.solver import genera  # noqa: E402

from . import test_api_festivi, test_api_storico_festivi  # noqa: E402
from .test_api_storico_festivi import attiva, crea  # noqa: E402
from .test_festivita import fest  # noqa: E402
from .test_solver_festivi import DA_MARTEDI, PERSONE, SEDE, chi_lavora, conti, per_gruppo  # noqa: E402

client = test_api_storico_festivi.client    # fixture (sqlite e libsql)
cattura = test_api_festivi.cattura          # fixture: argomenti passati al generatore
NATALE = fest(13, "Natale", giorno=25, mese=12)
D_NATALE = date(2026, 12, 25)
GIORNO_NATALE = {(D_NATALE, "giorno")}
NOTTE_NATALE = {(D_NATALE, "notte")}


# --- modulo puro --------------------------------------------------------------------------------------

def test_turni_disponibili_per_fascia():
    disp = {D_NATALE: {1: "giorno", 2: "notte", 3: "entrambi"}}
    t = turni_disponibili([NATALE], D_NATALE - timedelta(days=3), D_NATALE + timedelta(days=1), disp)
    assert t == {(D_NATALE, "giorno"): frozenset({1, 3}), (D_NATALE, "notte"): frozenset({2, 3})}


def test_turni_disponibili_notte_della_sera_prima_e_turni_che_non_contano():
    f = {**NATALE, "conta_giorno": False, "conta_notte_prima": True}
    vigilia = D_NATALE - timedelta(days=1)
    t = turni_disponibili([f], vigilia, D_NATALE, {D_NATALE: {1: "notte", 2: "giorno"}})
    # la notte della sera prima è una notte di Natale; il giorno non conta: chi vuole il giorno non ha turni
    assert t == {(vigilia, "notte"): frozenset({1}), (D_NATALE, "notte"): frozenset({1})}


def test_festivi_settimana_con_i_disponibili():
    fs = festivi_settimana([NATALE], DA_MARTEDI, {}, disponibili={D_NATALE: {7: "giorno"}})
    assert fs.disponibili == {(D_NATALE, "giorno"): frozenset({7})}
    assert festivi_settimana([NATALE], DA_MARTEDI, {}).disponibili == {}


# --- generatore ------------------------------------------------------------------------------------------

# l'autista 1 ha fatto Natale molte volte e l'anno scorso: per la rotazione non tocca a lui
MOLTE = ContoFestivita(turni=4, esposizione=5, ultimo_anno=2025)
POCHE = ContoFestivita(turni=1, esposizione=5, ultimo_anno=2022)


def genera_con(disponibili, conti_natale, monkeypatch=None, senza_sconto=False):
    if senza_sconto:
        monkeypatch.setattr(solver, "P_DISPONIBILE_FESTIVO", 0)
    fs = festivi_settimana([NATALE], DA_MARTEDI, {13: conti_natale}, disponibili={D_NATALE: disponibili})
    r = genera(DA_MARTEDI, SEDE, PERSONE, festivi=fs, tempo_max=10)
    assert r.scoperti == []
    return r


def test_chi_vuole_lavorare_riceve_prima_quel_turno(monkeypatch):
    c = conti(POCHE, p1=MOLTE)
    assert 1 in chi_lavora(genera_con({1: "giorno"}, c), GIORNO_NATALE)
    # controllo: senza lo sconto la rotazione lo terrebbe a casa
    assert 1 not in chi_lavora(genera_con({1: "giorno"}, c, monkeypatch, senza_sconto=True), GIORNO_NATALE)


def test_lo_sconto_vale_solo_per_la_fascia_scelta():
    c = conti(POCHE, p1=MOLTE)
    r = genera_con({1: "notte"}, c)
    assert 1 in chi_lavora(r, NOTTE_NATALE)
    assert 1 not in chi_lavora(r, GIORNO_NATALE)


def test_le_regole_restano_valide_un_solo_turno_tra_giorno_e_notte():
    # vuole entrambi, ma giorno e notte di fila non si possono fare: ne fa uno solo
    c = conti(POCHE, p1=MOLTE)
    r = genera_con({1: "entrambi"}, c)
    assert 1 in chi_lavora(r, GIORNO_NATALE | NOTTE_NATALE)
    assert sum(1 for a in r.assegnazioni if a.persona_id == 1 and a.data == D_NATALE) == 1


def test_le_regole_restano_valide_ferie():
    fs = festivi_settimana([NATALE], DA_MARTEDI, {13: conti(POCHE)}, disponibili={D_NATALE: {1: "entrambi"}})
    r = genera(DA_MARTEDI, SEDE, PERSONE, festivi=fs, ferie={1: {D_NATALE}}, tempo_max=10)
    assert 1 not in chi_lavora(r, GIORNO_NATALE | NOTTE_NATALE)


def test_tra_piu_disponibili_decide_la_rotazione():
    # gli autisti 1 e 2 vogliono il giorno di Natale; 1 l'ha fatto molte volte e l'anno scorso: tocca a 2
    c = conti(POCHE, p1=MOLTE)
    r = genera_con({1: "giorno", 2: "giorno"}, c)
    autisti_giorno = {a.persona_id for a in r.assegnazioni if (a.data, a.fascia) in GIORNO_NATALE
                      and a.ruolo == "autista"}
    assert autisti_giorno == {2}


def test_tra_piu_disponibili_decide_la_rotazione_anche_al_contrario():
    c = conti(POCHE, p2=MOLTE)
    r = genera_con({1: "giorno", 2: "giorno"}, c)
    autisti_giorno = {a.persona_id for a in r.assegnazioni if (a.data, a.fascia) in GIORNO_NATALE
                      and a.ruolo == "autista"}
    assert autisti_giorno == {1}


def test_i_disponibili_sono_preferiti_a_chi_tocca_per_rotazione(monkeypatch):
    # i primi (1, 2, 5, 6) sono indietro con Natale; i soccorritori 7 e 8, avanti, vogliono la notte
    c = per_gruppo({1, 2, 5, 6}, ContoFestivita(turni=0, esposizione=5), MOLTE)
    r = genera_con({7: "notte", 8: "notte"}, c)
    soccorritori_notte = {a.persona_id for a in r.assegnazioni if (a.data, a.fascia) in NOTTE_NATALE
                          and a.ruolo == "soccorritore"}
    assert soccorritori_notte & {7, 8}
    r = genera_con({7: "notte", 8: "notte"}, c, monkeypatch, senza_sconto=True)
    soccorritori_notte = {a.persona_id for a in r.assegnazioni if (a.data, a.fascia) in NOTTE_NATALE
                          and a.ruolo == "soccorritore"}
    assert not soccorritori_notte & {7, 8}


# --- API ------------------------------------------------------------------------------------------------

def metti(client, data, persona_id, fascia):
    return client.put("/api/festivita/disponibili", json={"data": data, "persona_id": persona_id, "fascia": fascia})


def elenco(client, dal="2026-01-01", al="2027-12-31"):
    r = client.get("/api/festivita/disponibili", params={"dal": dal, "al": al})
    assert r.status_code == 200, r.text
    return r.json()


def test_segna_cambia_e_toglie_la_disponibilita(client):
    mario = crea(client, "Mario Rossi")["id"]
    attiva(client, "Natale")
    r = metti(client, "2026-12-25", mario, "giorno")
    assert r.status_code == 200, r.text
    assert r.json() == {"data": "2026-12-25", "persona_id": mario, "fascia": "giorno"}
    assert elenco(client) == [{"data": "2026-12-25", "persona_id": mario, "nome": "Mario Rossi", "fascia": "giorno"}]
    assert metti(client, "2026-12-25", mario, "entrambi").status_code == 200
    assert [x["fascia"] for x in elenco(client)] == ["entrambi"]
    r = metti(client, "2026-12-25", mario, None)
    assert r.status_code == 200 and r.json()["fascia"] is None
    assert elenco(client) == []
    assert metti(client, "2026-12-25", mario, None).status_code == 200  # togliere due volte non è un errore


def test_elenco_nel_periodo_in_ordine(client):
    mario, anna = crea(client, "Mario Rossi")["id"], crea(client, "Anna Verdi")["id"]
    attiva(client, "Natale")
    attiva(client, "Santo Stefano")
    metti(client, "2026-12-26", mario, "notte")
    metti(client, "2026-12-25", mario, "giorno")
    metti(client, "2026-12-25", anna, "notte")
    assert [(x["data"], x["nome"]) for x in elenco(client)] == [
        ("2026-12-25", "Anna Verdi"), ("2026-12-25", "Mario Rossi"), ("2026-12-26", "Mario Rossi")]
    assert [x["data"] for x in elenco(client, "2026-12-26", "2026-12-31")] == ["2026-12-26"]


def test_validazioni(client):
    mario = crea(client, "Mario Rossi")["id"]
    vol = crea(client, "Vol", tipo="volontario")["id"]
    assert metti(client, "2026-12-25", mario, "giorno").status_code == 400   # Natale non attivo
    attiva(client, "Natale")
    assert metti(client, "2026-12-23", mario, "giorno").status_code == 400   # non è una festività
    assert metti(client, "2026-12-25", vol, "giorno").status_code == 400     # volontario
    assert metti(client, "2026-12-25", 9999, "giorno").status_code == 404
    assert metti(client, "2026-12-25", mario, "mattina").status_code == 422
    assert metti(client, "non-una-data", mario, "giorno").status_code == 422
    r = client.get("/api/festivita/disponibili", params={"dal": "2026-12-31", "al": "2026-01-01"})
    assert r.status_code == 400
    assert client.get("/api/festivita/disponibili").status_code == 422


def test_cancellare_una_persona_toglie_le_sue_disponibilita(client):
    mario, luigi = crea(client, "Mario Rossi")["id"], crea(client, "Luigi Bianchi")["id"]
    attiva(client, "Natale")
    metti(client, "2026-12-25", mario, "giorno")
    metti(client, "2026-12-25", luigi, "notte")
    # Luigi ha un turno: viene solo disattivato, ma la disponibilità si toglie comunque
    assert client.post("/api/settimane/2026-12-21/assegnazioni", json={
        "data": "2026-12-22", "postazione": "Acquasanta", "fascia": "giorno", "segmento": "intero",
        "ruolo": "autista", "persona_id": luigi}).status_code == 201
    assert client.delete(f"/api/persone/{mario}").status_code == 204
    assert client.delete(f"/api/persone/{luigi}").status_code == 204
    assert elenco(client) == []


def test_la_settimana_mostra_chi_vuole_lavorare(client):
    mario, anna = crea(client, "Mario Rossi")["id"], crea(client, "Anna Verdi")["id"]
    attiva(client, "Natale")
    metti(client, "2026-12-25", mario, "entrambi")
    metti(client, "2026-12-25", anna, "notte")
    s = client.get("/api/settimane/2026-12-21").json()
    assert sorted(s["festivi_disponibili"], key=lambda x: (x["fascia"], x["persona_id"])) == sorted([
        {"data": "2026-12-25", "fascia": "giorno", "persona_id": mario},
        {"data": "2026-12-25", "fascia": "notte", "persona_id": mario},
        {"data": "2026-12-25", "fascia": "notte", "persona_id": anna},
    ], key=lambda x: (x["fascia"], x["persona_id"]))
    assert client.get("/api/settimane/2026-11-02").json()["festivi_disponibili"] == []


def test_la_generazione_passa_i_disponibili(client, cattura):
    mario = crea(client, "Mario Rossi")["id"]
    attiva(client, "Natale")
    metti(client, "2027-12-25", mario, "giorno")
    assert client.post("/api/settimane/2027-12-20/genera", json={}).status_code == 200
    assert cattura[-1]["festivi"].disponibili == {(date(2027, 12, 25), "giorno"): frozenset({mario})}
