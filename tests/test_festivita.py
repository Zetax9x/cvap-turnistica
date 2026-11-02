"""Fase 4 del piano rotazioni: calendario delle festività (modulo puro, database, API, payload settimana).

Ancora senza effetto sul generatore (docs/PIANO-rotazioni.md, sezione 3.1).
"""
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import db  # noqa: E402
from cvap.app import create_app  # noqa: E402
from cvap.festivita import (FESTIVITA_PREDEFINITE, date_festive, festivi_periodo, pasqua,  # noqa: E402
                            turni_festivi)

NOMI_PREDEFINITE = [
    "Capodanno", "Epifania", "Pasqua", "Lunedì dell'Angelo", "Liberazione", "Festa del lavoro",
    "Festa della Repubblica", "Sant'Emidio", "Ferragosto", "Ognissanti", "Immacolata",
    "Vigilia di Natale", "Natale", "Santo Stefano", "San Silvestro",
]


def fest(id, nome, regola="fissa", giorno=None, mese=None, offset_pasqua=None, data=None,
         conta_giorno=True, conta_notte=True, conta_notte_prima=False, peso=1):
    return {"id": id, "nome": nome, "regola": regola, "giorno": giorno, "mese": mese,
            "offset_pasqua": offset_pasqua, "data": data, "conta_giorno": conta_giorno,
            "conta_notte": conta_notte, "conta_notte_prima": conta_notte_prima, "peso": peso}


def predefinite():
    return [fest(i, nome, regola, giorno, mese, offset)
            for i, (_, nome, regola, giorno, mese, offset) in enumerate(FESTIVITA_PREDEFINITE, start=1)]


NATALE = fest(13, "Natale", giorno=25, mese=12)


# --- modulo puro: Pasqua ---------------------------------------------------------------------------

@pytest.mark.parametrize("anno, attesa", [
    (2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)),
    (2000, date(2000, 4, 23)), (2011, date(2011, 4, 24)), (2038, date(2038, 4, 25)), (2285, date(2285, 3, 22)),
])
def test_pasqua_anni_noti(anno, attesa):
    assert pasqua(anno) == attesa


def test_pasqua_e_sempre_domenica_tra_22_marzo_e_25_aprile():
    for anno in range(1900, 2101):
        p = pasqua(anno)
        assert p.weekday() == 6 and date(anno, 3, 22) <= p <= date(anno, 4, 25), anno


@pytest.mark.parametrize("anno", [1582, 4100])
def test_pasqua_fuori_calendario_gregoriano(anno):
    with pytest.raises(ValueError):
        pasqua(anno)


# --- modulo puro: date delle festività -------------------------------------------------------------

def test_predefinite_nell_ordine_del_piano():
    assert [nome for _, nome, *_ in FESTIVITA_PREDEFINITE] == NOMI_PREDEFINITE
    chiavi = [chiave for chiave, *_ in FESTIVITA_PREDEFINITE]
    assert len(set(chiavi)) == len(chiavi) and all(chiavi)


def test_date_festive_predefinite_2026():
    d = date_festive(predefinite(), 2026)
    assert len(d) == 15
    assert d[date(2026, 4, 5)] == "Pasqua"
    assert d[date(2026, 4, 6)] == "Lunedì dell'Angelo"
    assert d[date(2026, 8, 5)] == "Sant'Emidio"
    assert d[date(2026, 12, 25)] == "Natale"


def test_lunedi_dell_angelo_e_il_giorno_dopo_pasqua():
    assert date(2027, 3, 29) in date_festive([fest(4, "Lunedì dell'Angelo", "pasqua", offset_pasqua=1)], 2027)


def test_fissa_29_febbraio_solo_negli_anni_bisestili():
    f = [fest(1, "Bisestile", giorno=29, mese=2)]
    assert date_festive(f, 2025) == {}
    assert date_festive(f, 2028) == {date(2028, 2, 29): "Bisestile"}


def test_data_singola_solo_nel_suo_anno():
    f = [fest(1, "Visita", "data", data="2026-06-10")]
    assert date_festive(f, 2026) == {date(2026, 6, 10): "Visita"}
    assert date_festive(f, 2027) == {}


def test_due_festivita_nello_stesso_giorno_uniscono_i_nomi():
    f = [fest(3, "Pasqua", "pasqua", offset_pasqua=0), fest(5, "Liberazione", giorno=25, mese=4)]
    assert date_festive(f, 2038) == {date(2038, 4, 25): "Pasqua / Liberazione"}


# --- modulo puro: turni che contano ----------------------------------------------------------------

def test_turni_festivi_giorno_e_notte_del_giorno_stesso():
    assert turni_festivi([NATALE], date(2026, 12, 21), date(2026, 12, 27)) == {
        (date(2026, 12, 25), "giorno"): 13, (date(2026, 12, 25), "notte"): 13}


def test_turni_festivi_solo_i_turni_spuntati():
    dal, al = date(2026, 12, 21), date(2026, 12, 27)
    solo_notte = turni_festivi([{**NATALE, "conta_giorno": False}], dal, al)
    solo_giorno = turni_festivi([{**NATALE, "conta_notte": False}], dal, al)
    assert solo_notte == {(date(2026, 12, 25), "notte"): 13}
    assert solo_giorno == {(date(2026, 12, 25), "giorno"): 13}


def test_notte_della_sera_prima_e_un_turno_del_giorno_precedente():
    t = turni_festivi([{**NATALE, "conta_notte_prima": True}], date(2026, 12, 21), date(2026, 12, 27))
    assert t[(date(2026, 12, 24), "notte")] == 13
    assert (date(2026, 12, 24), "giorno") not in t


def test_turni_festivi_limitati_al_periodo():
    natale = {**NATALE, "conta_notte_prima": True}
    assert (date(2026, 12, 24), "notte") not in turni_festivi([natale], date(2026, 12, 25), date(2026, 12, 31))
    assert turni_festivi([natale], date(2026, 12, 18), date(2026, 12, 24)) == {(date(2026, 12, 24), "notte"): 13}


def test_notte_prima_di_capodanno_a_cavallo_d_anno():
    capodanno = fest(1, "Capodanno", giorno=1, mese=1, conta_notte_prima=True)
    assert turni_festivi([capodanno], date(2026, 12, 28), date(2026, 12, 31)) == {(date(2026, 12, 31), "notte"): 1}
    t = turni_festivi([capodanno], date(2026, 12, 28), date(2027, 1, 3))
    assert set(t) == {(date(2026, 12, 31), "notte"), (date(2027, 1, 1), "giorno"), (date(2027, 1, 1), "notte")}


def test_stesso_turno_in_due_festivita_vince_il_peso_poi_l_id():
    vigilia = fest(12, "Vigilia di Natale", giorno=24, mese=12, conta_giorno=False)
    natale = {**NATALE, "conta_notte_prima": True, "peso": 3}
    dal, al = date(2026, 12, 21), date(2026, 12, 27)
    assert turni_festivi([vigilia, natale], dal, al)[(date(2026, 12, 24), "notte")] == 13
    assert turni_festivi([vigilia, {**natale, "peso": 1}], dal, al)[(date(2026, 12, 24), "notte")] == 12


def test_festivi_periodo_per_il_payload():
    f = [fest(1, "Capodanno", giorno=1, mese=1), fest(15, "San Silvestro", giorno=31, mese=12, peso=2)]
    assert festivi_periodo(f, date(2026, 12, 28), date(2027, 1, 3)) == [
        {"data": "2026-12-31", "nome": "San Silvestro", "peso": 2},
        {"data": "2027-01-01", "nome": "Capodanno", "peso": 1},
    ]


# --- database --------------------------------------------------------------------------------------

def test_predefinite_inserite_una_volta_e_non_attive(tmp_path):
    path = str(tmp_path / "t.db")
    db.connetti(path).close()
    conn = db.connetti(path)
    try:
        righe = conn.execute("SELECT nome, attiva, peso FROM festivita WHERE chiave IS NOT NULL ORDER BY id").fetchall()
    finally:
        conn.close()
    assert [r[0] for r in righe] == NOMI_PREDEFINITE
    assert all(r[1] == 0 and r[2] == 1 for r in righe)


# --- API -------------------------------------------------------------------------------------------

@pytest.fixture(params=["sqlite", "libsql"])
def client(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    return TestClient(create_app(str(tmp_path / "t.db")))


def lista(client, **params):
    r = client.get("/api/festivita", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def per_nome(client, nome):
    return next(f for f in lista(client) if f["nome"] == nome)


def corpo(f, **modifiche):
    campi = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte",
             "conta_notte_prima", "peso", "attiva")
    return {**{k: f[k] for k in campi}, **modifiche}


def attiva(client, nome, **modifiche):
    f = per_nome(client, nome)
    r = client.put(f"/api/festivita/{f['id']}", json=corpo(f, attiva=True, **modifiche))
    assert r.status_code == 200, r.text
    return r.json()


def test_get_festivita_predefinite(client):
    fs = lista(client, anno=2026)
    assert [f["nome"] for f in fs] == NOMI_PREDEFINITE
    assert all(f["predefinita"] is True and f["attiva"] is False and f["peso"] == 1 for f in fs)
    assert all(f["conta_giorno"] is True and f["conta_notte"] is True and f["conta_notte_prima"] is False
               for f in fs)
    pasqua_ = next(f for f in fs if f["nome"] == "Pasqua")
    assert pasqua_["regola"] == "pasqua" and pasqua_["offset_pasqua"] == 0
    assert pasqua_["anteprima"] == {"2026": "2026-04-05", "2027": "2027-03-28"}
    assert next(f for f in fs if f["nome"] == "Natale")["anteprima"] == {"2026": "2026-12-25", "2027": "2027-12-25"}


def test_anteprima_predefinita_anno_di_oggi_e_limiti(client):
    oggi = date.today().year
    assert set(per_nome(client, "Natale")["anteprima"]) == {str(oggi), str(oggi + 1)}
    assert client.get("/api/festivita", params={"anno": 1999}).status_code == 422
    assert client.get("/api/festivita", params={"anno": 2100}).status_code == 422


def test_attiva_predefinita_con_peso_e_turni(client):
    f = attiva(client, "Natale", peso=3, conta_notte_prima=True)
    assert f["attiva"] is True and f["peso"] == 3 and f["conta_notte_prima"] is True
    g = per_nome(client, "Natale")
    assert g["attiva"] is True and g["peso"] == 3 and g["conta_notte_prima"] is True


@pytest.mark.parametrize("modifica", [{"nome": "Natale bis"}, {"mese": 11}, {"giorno": 24},
                                      {"regola": "data", "data": "2026-12-25"}])
def test_predefinita_non_si_rinomina_ne_si_sposta(client, modifica):
    f = per_nome(client, "Natale")
    r = client.put(f"/api/festivita/{f['id']}", json=corpo(f, **modifica))
    assert r.status_code == 400, r.text
    assert per_nome(client, "Natale")["mese"] == 12


def test_predefinita_non_si_cancella(client):
    f = per_nome(client, "Natale")
    assert client.delete(f"/api/festivita/{f['id']}").status_code == 400
    assert per_nome(client, "Natale")


@pytest.mark.parametrize("dati, attesi", [
    ({"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6},
     {"giorno": 13, "mese": 6, "offset_pasqua": None, "data": None}),
    ({"nome": "Corpus Domini", "regola": "pasqua", "offset_pasqua": 60, "giorno": 3},
     {"offset_pasqua": 60, "giorno": None, "mese": None, "data": None}),
    ({"nome": "Visita", "regola": "data", "data": "2026-06-10", "mese": 6},
     {"data": "2026-06-10", "giorno": None, "mese": None, "offset_pasqua": None}),
    ({"nome": "Bisestile", "regola": "fissa", "giorno": 29, "mese": 2}, {"giorno": 29, "mese": 2}),
])
def test_crea_festivita_aggiunta_a_mano(client, dati, attesi):
    r = client.post("/api/festivita", json=dati)
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["predefinita"] is False and f["attiva"] is True and f["peso"] == 1
    assert {k: f[k] for k in attesi} == attesi
    assert lista(client)[-1]["id"] == f["id"]


def test_modifica_e_cancella_festivita_aggiunta(client):
    f = client.post("/api/festivita", json={"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6}).json()
    r = client.put(f"/api/festivita/{f['id']}", json=corpo(f, nome="Sant'Antonio", giorno=14, peso=2))
    assert r.status_code == 200, r.text
    assert r.json()["nome"] == "Sant'Antonio" and r.json()["giorno"] == 14 and r.json()["peso"] == 2
    assert client.delete(f"/api/festivita/{f['id']}").status_code == 204
    assert client.delete(f"/api/festivita/{f['id']}").status_code == 404


def test_put_e_delete_di_festivita_inesistente(client):
    f = per_nome(client, "Natale")
    assert client.put("/api/festivita/999", json=corpo(f)).status_code == 404
    assert client.delete("/api/festivita/999").status_code == 404


@pytest.mark.parametrize("dati", [
    {"nome": ""}, {"nome": "   "}, {"nome": "x" * 101}, {"regola": "boh"},
    {"mese": None}, {"giorno": None}, {"giorno": 31, "mese": 4}, {"giorno": 30, "mese": 2},
    {"giorno": 0}, {"mese": 13},
    {"regola": "pasqua", "offset_pasqua": None}, {"regola": "pasqua", "offset_pasqua": 100},
    {"regola": "data", "data": None}, {"regola": "data", "data": "2026-13-45"},
    {"regola": "data", "data": "1999-12-31"},
    {"peso": 0}, {"peso": 4}, {"peso": "x"},
    {"conta_giorno": False, "conta_notte": False, "conta_notte_prima": False},
])
def test_validazione(client, dati):
    base = {"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6}
    assert client.post("/api/festivita", json={**base, **dati}).status_code == 422


@pytest.mark.parametrize("dati", [
    {"nome": "natale ", "regola": "fissa", "giorno": 1, "mese": 3},
    {"nome": "NATALE", "regola": "fissa", "giorno": 1, "mese": 3},
    {"nome": "Natale bis", "regola": "fissa", "giorno": 25, "mese": 12},
    {"nome": "Pasquetta", "regola": "pasqua", "offset_pasqua": 1},
])
def test_doppioni_rifiutati(client, dati):
    r = client.post("/api/festivita", json=dati)
    assert r.status_code == 400, r.text


def test_doppione_data_singola_e_in_modifica(client):
    visita = {"nome": "Visita", "regola": "data", "data": "2026-06-10"}
    assert client.post("/api/festivita", json=visita).status_code == 201
    assert client.post("/api/festivita", json={**visita, "nome": "Altra"}).status_code == 400
    f = client.post("/api/festivita", json={"nome": "Patrono", "regola": "fissa", "giorno": 13, "mese": 6}).json()
    assert client.put(f"/api/festivita/{f['id']}", json=corpo(f, nome="Visita")).status_code == 400
    assert client.put(f"/api/festivita/{f['id']}", json=corpo(f, peso=2)).status_code == 200  # sé stessa non conta


def test_payload_settimana_solo_festivita_attive(client):
    assert client.get("/api/settimane/2026-12-21").json()["festivi"] == []
    attiva(client, "Natale")
    festivi = client.get("/api/settimane/2026-12-21").json()["festivi"]
    assert festivi == [{"data": "2026-12-25", "nome": "Natale", "peso": 1}]  # Santo Stefano non è attivo


def test_payload_pasqua_e_pasquetta_in_settimane_diverse(client):
    attiva(client, "Pasqua")
    attiva(client, "Lunedì dell'Angelo", peso=2)
    assert client.get("/api/settimane/2027-03-22").json()["festivi"] == [
        {"data": "2027-03-28", "nome": "Pasqua", "peso": 1}]
    assert client.get("/api/settimane/2027-03-29").json()["festivi"] == [
        {"data": "2027-03-29", "nome": "Lunedì dell'Angelo", "peso": 2}]


def test_payload_festivi_a_cavallo_d_anno(client):
    attiva(client, "San Silvestro")
    attiva(client, "Capodanno")
    festivi = client.get("/api/settimane/2026-12-28").json()["festivi"]
    assert [f["data"] for f in festivi] == ["2026-12-31", "2027-01-01"]


def test_campi_che_la_regola_non_usa_non_danno_errore(client):
    r = client.post("/api/festivita", json={"nome": "Ceneri", "regola": "pasqua", "offset_pasqua": -46,
                                            "giorno": 0, "mese": 13, "data": "1900-01-01"})
    assert r.status_code == 201, r.text
    assert r.json()["giorno"] is None and r.json()["mese"] is None and r.json()["data"] is None


def test_regole_diverse_nello_stesso_giorno_sono_ammesse(client):
    r = client.post("/api/festivita", json={"nome": "Natale 2026 speciale", "regola": "data", "data": "2026-12-25"})
    assert r.status_code == 201, r.text


def test_tetto_alle_festivita_aggiunte_a_mano(client, monkeypatch):
    from cvap import api_festivita
    monkeypatch.setattr(api_festivita, "FESTIVITA_AGGIUNTE_MAX", 2)
    for giorno in (1, 2):
        assert client.post("/api/festivita", json={"nome": f"F{giorno}", "regola": "fissa", "giorno": giorno,
                                                   "mese": 3}).status_code == 201
    r = client.post("/api/festivita", json={"nome": "F3", "regola": "fissa", "giorno": 3, "mese": 3})
    assert r.status_code == 400 and "100" not in r.text
