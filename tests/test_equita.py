"""Quadro dell'equità (Statistiche → Equità): modulo puro cvap/equita.py e API /api/statistiche/equita."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from cvap import db
from cvap.app import create_app
from cvap.equita import ANDAMENTO_PUNTI_MAX, ROTAZIONI, equita, rotazione_festivita
from cvap.modello import STANDBY, Assegnazione
from cvap.rotazione_festivi import ContoFestivita, debiti
from cvap.storico import SettimanaPassata
from cvap.vincoli import ASCOLI

W1 = date(2026, 10, 19)  # lunedì
W2 = date(2026, 10, 26)
W3 = date(2026, 11, 2)


def ass(d, postazione, fascia, persona_id, ruolo="soccorritore", origine="generato"):
    return Assegnazione(d, postazione, fascia, "intero", ruolo, persona_id, origine)


def giorno(lunedi, i):
    return lunedi + timedelta(days=i)


def persona(pid, nome, tipo="dipendente", attivo=True, qualifica="autista"):
    return {"id": pid, "nome": nome, "tipo": tipo, "qualifica": qualifica, "autista_programmati": False,
            "attivo": attivo}


PERSONE = [
    persona(1, "Anna"), persona(2, "Bruno"), persona(3, "Carla"),
    persona(4, "Dario", attivo=False),   # disattivato, con turni
    persona(5, "Elena", attivo=False),   # disattivato, senza turni
    persona(9, "Vito", "volontario"),
]


def settimane_note():
    """Due settimane generate. Standby: Anna 2 + 1, Bruno 1. Ascoli (solo la seconda): Carla 1."""
    s1 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3, 4, 5], assegnazioni=[
        ass(giorno(W1, 0), STANDBY, "giorno", 1), ass(giorno(W1, 2), STANDBY, "giorno", 1),
        ass(giorno(W1, 1), STANDBY, "giorno", 2), ass(giorno(W1, 3), "Acquasanta", "notte", 4),
        ass(giorno(W1, 4), "Acquasanta", "giorno", 9),
    ])
    s2 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3, 4], assegnazioni=[
        ass(giorno(W2, 0), STANDBY, "giorno", 1), ass(giorno(W2, 1), ASCOLI, "notte", 3),
    ])
    return [(W1, s1), (W2, s2)]


def per_id(rotazione):
    return {d["persona_id"]: d for d in rotazione["dipendenti"]}


# --- modulo puro -----------------------------------------------------------------------------------

def test_registro_comprende_le_rotazioni_esistenti():
    chiavi = [r.chiave for r in ROTAZIONI]
    assert chiavi == ["ore", "giorno_notte", "sab_giorno", "sab_notte", "dom_giorno", "dom_notte",
                      "standby", "programmati", "assistenze", "ascoli", "ascoli_giorno_notte", "sedi"]
    out = equita(settimane_note(), PERSONE)
    assert list(out) == chiavi


def test_rotazione_con_storico_noto_piu_avanti_piu_indietro_e_differenza():
    standby = equita(settimane_note(), PERSONE)["standby"]
    # 4 turni su 8 settimane lavorate (4 dipendenti x 2): quota attesa 1 a testa
    d = per_id(standby)
    assert (d[1]["fatti"], d[1]["quota"], d[1]["scarto"]) == (3, 1, 2)
    assert (d[2]["fatti"], d[2]["quota"], d[2]["scarto"]) == (1, 1, 0)
    assert d[3]["scarto"] == -1 and d[4]["scarto"] == -1
    assert standby["piu_avanti"]["persona_id"] == 1 and standby["piu_avanti"]["scarto"] == 2
    # a pari merito il primo in ordine di nome
    assert standby["piu_indietro"]["persona_id"] == 3 and standby["piu_indietro"]["nome"] == "Carla"
    assert standby["differenza"] == 3


def test_dettaglio_ordinato_da_chi_ha_fatto_di_piu():
    standby = equita(settimane_note(), PERSONE)["standby"]
    assert [d["persona_id"] for d in standby["dipendenti"]] == [1, 2, 3, 4]


def test_andamento_un_valore_per_settimana_generata_e_tendenza():
    standby = equita(settimane_note(), PERSONE)["standby"]
    # dopo la prima settimana: 3 turni su 4 settimane, quota 0,75: Anna +1,25, Carla -0,75
    assert standby["andamento"] == [{"settimana": "2026-10-19", "differenza": 2.0},
                                    {"settimana": "2026-10-26", "differenza": 3.0}]
    assert standby["tendenza"] == "aumenta"


def test_andamento_segue_solo_le_settimane_generate():
    manuale = SettimanaPassata(media_ore=0, dipendenti=[1, 2, 3, 4], assegnazioni=[
        ass(giorno(W3, 0), STANDBY, "giorno", 2, origine="manuale")])
    out = equita(settimane_note() + [(W3, manuale)], PERSONE)
    assert [p["settimana"] for p in out["standby"]["andamento"]] == ["2026-10-19", "2026-10-26"]
    assert per_id(out["standby"])[2]["fatti"] == 1


def test_tendenza_si_riduce_e_stabile():
    s3 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3, 4], assegnazioni=[
        ass(giorno(W3, 0), STANDBY, "giorno", 3), ass(giorno(W3, 1), STANDBY, "giorno", 4),
        ass(giorno(W3, 2), STANDBY, "notte", 3), ass(giorno(W3, 3), STANDBY, "notte", 4)])
    out = equita(settimane_note() + [(W3, s3)], PERSONE)
    assert out["standby"]["tendenza"] == "si_riduce"
    # una sola settimana: niente tendenza
    assert equita(settimane_note()[:1], PERSONE)["standby"]["tendenza"] is None
    # Programmati mai fatti: differenza sempre 0
    assert out["programmati"]["tendenza"] == "stabile"


def test_esposizione_di_ascoli_sono_le_settimane_con_ascoli():
    ascoli = equita(settimane_note(), PERSONE)["ascoli"]
    d = per_id(ascoli)
    # una settimana con Ascoli per 4 dipendenti, 1 turno: quota 0,25
    assert d[3]["fatti"] == 1 and d[3]["quota"] == 0.25 and d[3]["scarto"] == 0.75
    assert d[1]["scarto"] == -0.25
    assert ascoli["andamento"][0]["differenza"] == 0  # la prima settimana non aveva Ascoli


def test_chi_ha_il_divieto_non_entra_nella_rotazione():
    out = equita(settimane_note(), PERSONE, vietate={2: {ASCOLI}})
    d = per_id(out["ascoli"])
    assert d[2]["partecipa"] is False and d[2]["scarto"] is None
    assert d[3]["quota"] == pytest.approx(1 / 3, abs=0.01)
    assert per_id(out["ascoli_giorno_notte"])[2]["partecipa"] is False
    assert per_id(out["standby"])[2]["partecipa"] is True


def test_rotazioni_a_meta_giorni_e_notti_ad_ascoli():
    gn = equita(settimane_note(), PERSONE)["ascoli_giorno_notte"]
    d = per_id(gn)
    # Carla 0 giorni e 1 notte: metà dei turni = 0,5, ha fatto più notti
    assert (d[3]["fatti"], d[3]["quota"], d[3]["scarto"]) == (0, 0.5, -0.5)
    # chi non è mai stato ad Ascoli non partecipa
    assert d[1]["partecipa"] is False
    assert gn["piu_avanti"]["persona_id"] == 3 and gn["piu_indietro"]["persona_id"] == 3
    assert gn["differenza"] == 0


def test_ore_rispetto_alla_media():
    ore = equita(settimane_note(), PERSONE)["ore"]
    d = per_id(ore)
    assert sum(x["scarto"] for x in d.values()) == pytest.approx(0, abs=0.05)
    assert ore["piu_avanti"]["persona_id"] == 1  # 36 ore, il più alto


def test_volontari_esclusi_e_disattivati_solo_con_turni():
    out = equita(settimane_note(), PERSONE)
    for rot in out.values():
        ids = {d["persona_id"] for d in rot["dipendenti"]}
        assert 9 not in ids and 5 not in ids and 4 in ids
    assert per_id(out["standby"])[4]["attivo"] is False


def test_dipendente_attivo_senza_settimane_compare_ma_non_partecipa():
    persone = PERSONE + [persona(6, "Franco")]
    d = per_id(equita(settimane_note(), persone)["standby"])
    assert d[6]["partecipa"] is False and d[6]["fatti"] is None


def test_settimana_solo_a_mano_in_mezzo_conta_come_per_il_generatore():
    manuale = SettimanaPassata(media_ore=0, dipendenti=[1, 2, 3, 4], assegnazioni=[
        ass(giorno(W2, 0), STANDBY, "giorno", 2, origine="manuale")])
    s3 = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3, 4], assegnazioni=[
        ass(giorno(W3, 0), STANDBY, "giorno", 3)])
    w1 = settimane_note()[0]
    out = equita([w1, (W2, manuale), (W3, s3)], PERSONE)
    # calcola_storico conta anche la settimana a mano in mezzo; l'andamento segue solo le generate
    assert per_id(out["standby"])[2]["fatti"] == 2
    assert [p["settimana"] for p in out["standby"]["andamento"]] == ["2026-10-19", "2026-11-02"]


def test_con_dal_a_meta_il_conteggio_riparte_dalla_prima_settimana_del_periodo():
    out = equita(settimane_note()[1:], PERSONE)
    d = per_id(out["standby"])
    assert d[1]["fatti"] == 1 and d[2]["fatti"] == 0
    assert [p["settimana"] for p in out["standby"]["andamento"]] == ["2026-10-26"]


def test_rotazione_a_richiesta_solo_per_chi_puo_ricoprire_i_ruoli_usati():
    # Standby fatto solo da autisti: la soccorritrice Carla non potrebbe mai farlo
    autisti = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3], assegnazioni=[
        ass(giorno(W1, 0), STANDBY, "giorno", 1, ruolo="autista"),
        ass(giorno(W1, 1), STANDBY, "giorno", 1, ruolo="autista")])
    persone = [persona(1, "Anna"), persona(2, "Bruno"), persona(3, "Carla", qualifica="soccorritore")]
    standby = equita([(W1, autisti)], persone)["standby"]
    d = per_id(standby)
    assert d[3]["partecipa"] is False
    assert d[2]["quota"] == 1 and standby["piu_indietro"]["persona_id"] == 2
    # un ruolo da soccorritore nella postazione la fa rientrare
    misto = SettimanaPassata(media_ore=12, dipendenti=[1, 2, 3], assegnazioni=[
        *autisti.assegnazioni, ass(giorno(W1, 2), STANDBY, "giorno", 2)])
    assert per_id(equita([(W1, misto)], persone)["standby"])[3]["partecipa"] is True


def test_andamento_al_massimo_ventisei_punti_con_l_ultima_settimana():
    settimane = [(W1 + timedelta(weeks=i), SettimanaPassata(media_ore=12, dipendenti=[1, 2], assegnazioni=[
        ass(W1 + timedelta(weeks=i), STANDBY, "giorno", 1 + i % 2)])) for i in range(30)]
    andamento = equita(settimane, PERSONE)["standby"]["andamento"]
    assert len(andamento) == ANDAMENTO_PUNTI_MAX == 26
    assert andamento[0]["settimana"] == W1.isoformat()
    assert andamento[-1]["settimana"] == (W1 + timedelta(weeks=29)).isoformat()


def test_senza_settimane_nessun_dato():
    out = equita([], PERSONE)
    assert out["standby"]["andamento"] == [] and out["standby"]["piu_avanti"] is None
    assert out["standby"]["differenza"] == 0


# --- API -------------------------------------------------------------------------------------------

@pytest.fixture(params=["sqlite", "libsql"])
def ambiente(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    percorso = str(tmp_path / "t.db")
    return TestClient(create_app(percorso)), percorso


def crea(client, nome, tipo="dipendente"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": "soccorritore"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def prepara(ambiente):
    client, percorso = ambiente
    a, b, c = crea(client, "Anna"), crea(client, "Bruno"), crea(client, "Carla")
    vol = crea(client, "Vito", "volontario")
    ex, ex_senza = crea(client, "Dario"), crea(client, "Elena")
    conn = db.apri(percorso)
    try:
        db.salva_generazione(conn, W1, giorno(W1, 6), [
            ass(giorno(W1, 0), STANDBY, "giorno", a), ass(giorno(W1, 2), STANDBY, "giorno", a),
            ass(giorno(W1, 1), STANDBY, "giorno", b), ass(giorno(W1, 3), "Acquasanta", "notte", ex)],
            [a, b, c, ex, ex_senza], "2026-10-18T10:00:00", {})
        db.crea_assegnazione(conn, ass(giorno(W1, 4), "Acquasanta", "giorno", vol, origine="volontario"))
        db.salva_generazione(conn, W2, giorno(W2, 6), [ass(giorno(W2, 0), STANDBY, "giorno", a)],
                             [a, b, c, ex], "2026-10-25T10:00:00", {})
        # terza settimana compilata solo a mano: non conta
        db.crea_assegnazione(conn, ass(giorno(W3, 0), STANDBY, "giorno", b, origine="manuale"))
        db.imposta_stato(conn, W3, "confermata")
        for pid, nome in ((ex, "Dario"), (ex_senza, "Elena")):
            db.aggiorna_persona(conn, pid, nome, "dipendente", "soccorritore", False)
    finally:
        conn.close()
    return client, {"a": a, "b": b, "c": c, "vol": vol, "ex": ex, "ex_senza": ex_senza}


def rotazione(risposta, chiave):
    return next(r for r in risposta["rotazioni"] if r["chiave"] == chiave)


def test_api_equita(ambiente):
    client, ids = prepara(ambiente)
    r = client.get("/api/statistiche/equita")
    assert r.status_code == 200, r.text
    dati = r.json()
    assert dati["settimane"] == ["2026-10-19", "2026-10-26"]
    assert [x["chiave"] for x in dati["rotazioni"]] == [rot.chiave for rot in ROTAZIONI]
    standby = rotazione(dati, "standby")
    assert standby["nome"] == "Standby" and standby["unita"] == "turni"
    assert standby["piu_avanti"]["persona_id"] == ids["a"] and standby["differenza"] == 3
    assert [p["differenza"] for p in standby["andamento"]] == [2.0, 3.0]
    presenti = {d["persona_id"] for d in standby["dipendenti"]}
    assert presenti == {ids["a"], ids["b"], ids["c"], ids["ex"]}


def test_api_equita_nel_periodo(ambiente):
    client, ids = prepara(ambiente)
    dati = client.get("/api/statistiche/equita", params={"dal": "2026-10-27", "al": "2026-11-30"}).json()
    # la settimana del 26 ottobre si sovrappone al periodo: conta da sola
    assert dati["settimane"] == ["2026-10-26"]
    standby = rotazione(dati, "standby")
    assert len(standby["andamento"]) == 1
    assert {d["persona_id"]: d["fatti"] for d in standby["dipendenti"]}[ids["a"]] == 1
    # nel periodo il disattivato non ha turni: non compare
    assert ids["ex"] not in {d["persona_id"] for d in standby["dipendenti"]}


def test_api_equita_esclude_chi_ha_il_divieto(ambiente):
    client, ids = prepara(ambiente)
    r = client.post("/api/divieti", json={"persona_id": ids["b"], "postazione": STANDBY})
    assert r.status_code == 201, r.text
    standby = rotazione(client.get("/api/statistiche/equita").json(), "standby")
    assert {d["persona_id"]: d["partecipa"] for d in standby["dipendenti"]}[ids["b"]] is False


def test_api_equita_periodo_non_valido(ambiente):
    client, _ = ambiente
    r = client.get("/api/statistiche/equita", params={"dal": "2026-11-02", "al": "2026-10-01"})
    assert r.status_code == 400
    assert client.get("/api/statistiche/equita", params={"dal": "non-data"}).status_code == 422


# --- festività (fase 9): una rotazione per ogni festività attiva -------------------------------------

NATALE = {"id": 7, "nome": "Natale"}


def conti_natale():
    """Ultimi 5 anni: Anna 2 turni su 2 volte in servizio, Bruno 1 su 2, Carla 0 su 1, Dario mai in servizio;
    Zeno (ex dipendente, non tra le persone mostrate) 3 su 3: non entra nel tasso."""
    return {1: ContoFestivita(turni=2, esposizione=2), 2: ContoFestivita(turni=1, esposizione=2),
            3: ContoFestivita(turni=0, esposizione=1), 99: ContoFestivita(turni=3, esposizione=3)}


def test_festivita_stesso_debito_del_generatore():
    out = equita(settimane_note(), PERSONE, extra=[rotazione_festivita(NATALE, conti_natale())])
    assert list(out)[-1] == "festivita_7"
    natale = out["festivita_7"]
    assert (natale["nome"], natale["unita"], natale["festivita"]) == ("Natale", "turni", True)
    d = per_id(natale)
    # stesso calcolo di rotazione_festivi.debiti tra chi è mostrato e ha esposizione: tasso 3/5
    attesi = debiti(conti_natale(), [1, 2, 3])
    for pid in (1, 2, 3):
        assert d[pid]["partecipa"] is True
        assert d[pid]["scarto"] == pytest.approx(attesi[pid], abs=0.01)
    assert (d[1]["fatti"], d[1]["quota"], d[1]["scarto"]) == (2, 1.2, 0.8)
    assert d[3]["quota"] == 0.6
    # mai in servizio in quella festività: non partecipa
    assert d[4]["partecipa"] is False and d[4]["fatti"] is None
    assert natale["piu_avanti"]["persona_id"] == 1 and natale["piu_indietro"]["persona_id"] == 3
    assert natale["differenza"] == 1.4


def test_festivita_senza_andamento_settimanale():
    out = equita(settimane_note(), PERSONE, extra=[rotazione_festivita(NATALE, conti_natale())])
    assert out["festivita_7"]["andamento"] == [] and out["festivita_7"]["tendenza"] is None
    # le altre rotazioni non sono festività e hanno l'andamento
    assert out["standby"]["festivita"] is False and len(out["standby"]["andamento"]) == 2


def test_festivita_conta_anche_chi_non_ha_settimane_nel_periodo():
    # Franco, attivo, ha fatto Natale negli anni importati ma non ha settimane nel periodo
    persone = PERSONE + [persona(6, "Franco")]
    conti = {**conti_natale(), 6: ContoFestivita(turni=1, esposizione=1)}
    d = per_id(equita(settimane_note(), persone, extra=[rotazione_festivita(NATALE, conti)])["festivita_7"])
    assert d[6]["partecipa"] is True and d[6]["fatti"] == 1


def test_festivita_anche_senza_settimane_generate():
    natale = equita([], PERSONE, extra=[rotazione_festivita(NATALE, conti_natale())])["festivita_7"]
    # senza settimane: i dipendenti attivi, con lo storico importato
    assert per_id(natale)[1]["scarto"] == 0.8 and natale["andamento"] == []


# --- API: festività -----------------------------------------------------------------------------------

SETT_NATALE = date(2026, 12, 21)  # Natale 2026 è venerdì 25
NATALE_2026 = date(2026, 12, 25)


def prepara_festivita(ambiente):
    """Natale attivo, Ferragosto attivato e poi disattivato. Natale 2025 (importato): Mario. Natale 2026 (programma):
    Luigi di giorno e Mario di notte, Anna in ferie (conta come in servizio), Bruno in malattia (non conta)."""
    from .test_api_storico_festivi import attiva, festivita, salva, turno
    client, percorso = ambiente
    mario, luigi, anna, bruno = (crea(client, n) for n in ("Mario", "Luigi", "Anna", "Bruno"))
    tutti = [mario, luigi, anna, bruno]
    natale = attiva(client, "Natale")
    ferragosto = attiva(client, "Ferragosto")
    f = festivita(client, "Ferragosto")
    campi = ("nome", "regola", "giorno", "mese", "offset_pasqua", "data", "conta_giorno", "conta_notte",
             "conta_notte_prima", "peso")
    r = client.put(f"/api/festivita/{ferragosto}", json={**{k: f[k] for k in campi}, "attiva": False})
    assert r.status_code == 200, r.text
    assert salva(client, 2025, [turno(natale, mario), turno(ferragosto, luigi)], tutti).status_code == 200
    conn = db.apri(percorso)
    try:
        db.salva_generazione(conn, W1, giorno(W1, 6), [ass(giorno(W1, 0), "Acquasanta", "giorno", mario)],
                             tutti, "2026-10-18T10:00:00", {})
        db.salva_generazione(conn, SETT_NATALE, giorno(SETT_NATALE, 6), [
            ass(NATALE_2026, "Acquasanta", "giorno", luigi), ass(NATALE_2026, "Acquasanta", "notte", mario)],
            tutti, "2026-12-20T10:00:00", {})
    finally:
        conn.close()
    assert client.post("/api/ferie", json={"persona_id": anna, "dal": "2026-12-24", "al": "2026-12-26"}).status_code == 201
    assert client.post("/api/ferie", json={"persona_id": bruno, "dal": "2026-12-25", "al": "2026-12-25",
                                           "motivo": "malattia"}).status_code == 201
    return client, {"mario": mario, "luigi": luigi, "anna": anna, "bruno": bruno, "natale": natale,
                    "ferragosto": ferragosto}


def test_api_equita_festivita_attive_con_storico_importato_e_programma(ambiente):
    client, ids = prepara_festivita(ambiente)
    dati = client.get("/api/statistiche/equita").json()
    chiavi = [r["chiave"] for r in dati["rotazioni"]]
    # dopo le rotazioni del registro, solo le festività attive
    assert chiavi == [rot.chiave for rot in ROTAZIONI] + [f"festivita_{ids['natale']}"]
    natale = rotazione(dati, f"festivita_{ids['natale']}")
    assert (natale["nome"], natale["unita"], natale["festivita"]) == ("Natale", "turni", True)
    assert natale["andamento"] == [] and natale["tendenza"] is None
    d = {x["persona_id"]: x for x in natale["dipendenti"]}
    # turni: Mario 2, Luigi 1; esposizione: Mario, Luigi, Anna 2, Bruno 1 (malattia a Natale 2026): tasso 3/7
    assert (d[ids["mario"]]["fatti"], d[ids["mario"]]["quota"]) == (2, 0.86)
    assert d[ids["anna"]]["quota"] == 0.86 and d[ids["anna"]]["scarto"] == -0.86
    assert d[ids["bruno"]]["quota"] == 0.43
    assert natale["piu_avanti"]["persona_id"] == ids["mario"]
    assert natale["piu_indietro"]["persona_id"] == ids["anna"]
    assert natale["differenza"] == 2


def test_api_equita_festivita_ultimi_anni_fino_alla_fine_del_periodo(ambiente):
    client, ids = prepara_festivita(ambiente)
    # periodo che finisce prima di Natale 2026: conta solo Natale 2025 (importato)
    dati = client.get("/api/statistiche/equita", params={"al": "2026-12-01"}).json()
    d = {x["persona_id"]: x for x in rotazione(dati, f"festivita_{ids['natale']}")["dipendenti"]}
    assert d[ids["mario"]]["fatti"] == 1 and d[ids["mario"]]["quota"] == 0.25
    assert d[ids["luigi"]]["fatti"] == 0
    # una fine lontana nel futuro non sposta la finestra oltre i dati: Natale 2025 e 2026 contano ancora
    dati = client.get("/api/statistiche/equita", params={"al": "2100-01-01"}).json()
    d = {x["persona_id"]: x for x in rotazione(dati, f"festivita_{ids['natale']}")["dipendenti"]}
    assert d[ids["mario"]]["fatti"] == 2


def test_api_equita_senza_festivita_attive(ambiente):
    client, _ = prepara(ambiente)
    dati = client.get("/api/statistiche/equita").json()
    assert not [r for r in dati["rotazioni"] if r["chiave"].startswith("festivita_")]
    assert all(r["festivita"] is False for r in dati["rotazioni"])
