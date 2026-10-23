"""Test dell'API REST (FastAPI + SQLite) secondo docs/API.md."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap import db  # noqa: E402
from cvap.app import create_app  # noqa: E402

LUNEDI_A = "2026-10-19"
LUNEDI_B = "2026-10-26"


@pytest.fixture(params=["sqlite", "libsql"])
def client(request, tmp_path, monkeypatch):
    if request.param == "libsql":
        # stesso codice usato con Turso, ma su un file locale tramite libsql
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(client, nome, tipo="dipendente", qualifica="autista"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()


def prenota(client, settimana, persona_id, data=None, postazione="Acquasanta", fascia="giorno",
            segmento="intero", ruolo="soccorritore"):
    return client.post(f"/api/settimane/{settimana}/assegnazioni", json={
        "data": data or settimana, "postazione": postazione, "fascia": fascia,
        "segmento": segmento, "ruolo": ruolo, "persona_id": persona_id,
    })


def staff_14(client):
    ids = [crea(client, f"Autista {i}", "dipendente", "autista")["id"] for i in range(8)]
    ids += [crea(client, f"Soccorritore {i}", "dipendente", "soccorritore")["id"] for i in range(6)]
    return ids


# --- persone ---------------------------------------------------------------

def test_crud_persone(client):
    assert client.get("/api/persone").json() == []
    p = crea(client, "  Mario Rossi  ")
    assert p["nome"] == "Mario Rossi" and p["attivo"] is True and p["tipo"] == "dipendente"
    assert p["autista_programmati"] is False
    r = client.put(f"/api/persone/{p['id']}", json={
        "nome": "Mario", "tipo": "volontario", "qualifica": "soccorritore", "attivo": False})
    assert r.status_code == 200
    assert r.json() == {"id": p["id"], "nome": "Mario", "tipo": "volontario",
                        "qualifica": "soccorritore", "autista_programmati": False, "attivo": False,
                        "max_ore_settimana": None}
    assert len(client.get("/api/persone").json()) == 1
    assert client.delete(f"/api/persone/{p['id']}").status_code == 204
    assert client.get("/api/persone").json() == []


def test_persone_404(client):
    assert client.put("/api/persone/999", json={
        "nome": "X", "tipo": "dipendente", "qualifica": "autista", "attivo": True}).status_code == 404
    assert client.delete("/api/persone/999").status_code == 404


@pytest.mark.parametrize("body", [
    {"nome": "", "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "   ", "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "x" * 101, "tipo": "dipendente", "qualifica": "autista"},
    {"nome": "Mario", "tipo": "capo", "qualifica": "autista"},
    {"nome": "Mario", "tipo": "dipendente", "qualifica": "medico"},
    {"tipo": "dipendente", "qualifica": "autista"},
])
def test_persone_validazione_422(client, body):
    assert client.post("/api/persone", json=body).status_code == 422


def test_delete_persona_con_assegnazioni_la_disattiva(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, p["id"]).status_code == 201
    assert client.delete(f"/api/persone/{p['id']}").status_code == 204
    persone = client.get("/api/persone").json()
    assert persone == [{**p, "attivo": False}]


# --- postazioni / impostazioni -------------------------------------------------

def test_postazioni_seed(client):
    post = client.get("/api/postazioni").json()
    assert [(p["nome"], p["solo_settimane_b"]) for p in post] == [
        ("Acquasanta", False), ("Venarotta", False), ("Ascoli", True)]


def test_impostazioni_normalizzate_al_lunedi(client):
    assert client.get("/api/impostazioni").json() == {"data_riferimento_a": LUNEDI_A, "scarto_ore_max": 12}
    r = client.put("/api/impostazioni", json={"data_riferimento_a": "2026-10-29"})  # giovedì
    assert r.status_code == 200
    assert r.json() == {"data_riferimento_a": LUNEDI_B, "scarto_ore_max": 12}
    assert client.get("/api/impostazioni").json() == {"data_riferimento_a": LUNEDI_B, "scarto_ore_max": 12}
    assert client.put("/api/impostazioni", json={"data_riferimento_a": "boh"}).status_code == 422


# --- settimane ---------------------------------------------------------------

def test_settimana_a(client):
    s = client.get("/api/settimane/2026-10-21").json()
    assert s["inizio"] == LUNEDI_A and s["fine"] == "2026-10-25"
    assert s["tipo"] == "A" and s["stato"] == "nuova"
    assert s["postazioni"] == ["Acquasanta", "Venarotta"]
    assert len(s["giorni"]) == 7 and s["giorni"][0] == LUNEDI_A
    assert s["assegnazioni"] == [] and s["report"] is None and s["media_ore"] == 0
    assert any(v["codice"] == "scoperto" for v in s["violazioni"])


def test_settimana_b(client):
    s = client.get(f"/api/settimane/{LUNEDI_B}").json()
    assert s["tipo"] == "B"
    assert s["postazioni"] == ["Acquasanta", "Venarotta", "Ascoli"]


def test_data_non_valida_400(client):
    assert client.get("/api/settimane/2026-13-45").status_code == 400


def test_prenotazione_volontario(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    r = prenota(client, LUNEDI_A, p["id"], data="2026-10-24", segmento="mattina")
    assert r.status_code == 201, r.text
    s = r.json()
    [a] = s["assegnazioni"]
    assert a["origine"] == "volontario" and a["persona_nome"] == "Anna" and a["ore"] == 6
    [riga] = s["riepilogo"]
    assert riga["persona_id"] == p["id"] and riga["ore"] == 6 and riga["ore_giorno"] == 6
    assert riga["turni_weekend"] == 1
    assert s["stato"] == "nuova"


def test_prenotazione_dipendente_manuale(client):
    p = crea(client, "Mario", "dipendente", "autista")
    s = prenota(client, LUNEDI_A, p["id"], ruolo="autista").json()
    assert s["assegnazioni"][0]["origine"] == "manuale"
    assert s["media_ore"] == 12


@pytest.mark.parametrize("override", [
    {"data": "2026-10-26"},                         # fuori settimana
    {"postazione": "Ascoli"},                       # non attiva in settimana A
    {"postazione": "Inesistente"},
    {"fascia": "notte", "segmento": "mattina"},     # segmento non valido di notte
    {"ruolo": "autista"},                           # soccorritore non abilitato
])
def test_prenotazioni_rifiutate_400(client, override):
    p = crea(client, "Anna", "volontario", "soccorritore")
    r = prenota(client, LUNEDI_A, p["id"], **override)
    assert r.status_code == 400
    assert isinstance(r.json()["detail"], str)


def test_prenotazione_persona_inesistente(client):
    assert prenota(client, LUNEDI_A, 999).status_code in (400, 404)


def test_posto_gia_occupato_400(client):
    a = crea(client, "Anna", "volontario", "soccorritore")
    b = crea(client, "Bea", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, a["id"], segmento="intero").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], segmento="pomeriggio").status_code == 400
    # segmenti complementari invece vanno bene
    assert prenota(client, LUNEDI_A, a["id"], data="2026-10-20", segmento="mattina").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], data="2026-10-20", segmento="pomeriggio").status_code == 201


def test_validazione_body_assegnazione_422(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, p["id"], ruolo="medico").status_code == 422
    assert prenota(client, LUNEDI_A, p["id"], fascia="sera").status_code == 422


def test_delete_assegnazione(client):
    p = crea(client, "Anna", "volontario", "soccorritore")
    a = prenota(client, LUNEDI_A, p["id"]).json()["assegnazioni"][0]
    assert client.delete(f"/api/assegnazioni/{a['id']}").status_code == 204
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["assegnazioni"] == []
    assert client.delete(f"/api/assegnazioni/{a['id']}").status_code == 404


# --- generazione ---------------------------------------------------------------

@pytest.fixture
def generata(client):
    staff_14(client)
    vol = crea(client, "Volontaria", "volontario", "soccorritore")
    assert prenota(client, LUNEDI_A, vol["id"], data="2026-10-21", postazione="Venarotta").status_code == 201
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5})
    assert r.status_code == 200, r.text
    return client, r.json(), vol


def test_genera_copre_tutto(generata):
    _, s, vol = generata
    assert s["stato"] == "bozza"
    rep = s["report"]
    assert rep["scoperti"] == [] and rep["stato"] in ("ottimo", "ammissibile")
    assert rep["media_ore"] > 0 and rep["durata_s"] >= 0
    assert not [v for v in s["violazioni"] if v["livello"] == "errore"]
    vols = [a for a in s["assegnazioni"] if a["origine"] == "volontario"]
    assert len(vols) == 1 and vols[0]["persona_id"] == vol["id"]
    assert len(s["assegnazioni"]) == 7 * 2 * 2 * 2
    assert s["media_ore"] > 0
    assert len(s["riepilogo"]) == 15


def test_rigenera_mantiene_fissi_e_sostituisce_generati(generata):
    client, s, vol = generata
    generati = [a for a in s["assegnazioni"] if a["origine"] == "generato"]
    # un turno generato cancellato e sostituito da un manuale
    g = generati[0]
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 204
    r = prenota(client, LUNEDI_A, g["persona_id"], data=g["data"], postazione=g["postazione"],
                fascia=g["fascia"], segmento=g["segmento"], ruolo=g["ruolo"])
    assert r.status_code == 201, r.text
    s2 = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5}).json()
    origini = [a["origine"] for a in s2["assegnazioni"]]
    assert origini.count("volontario") == 1 and origini.count("manuale") == 1
    assert len(s2["assegnazioni"]) == 56
    vecchi_ids = {a["id"] for a in generati}
    assert not vecchi_ids & {a["id"] for a in s2["assegnazioni"] if a["origine"] == "generato"}

    s3 = client.delete(f"/api/settimane/{LUNEDI_A}/generati").json()
    assert sorted(a["origine"] for a in s3["assegnazioni"]) == ["manuale", "volontario"]


def test_conferma_blocca_e_riapri_sblocca(generata):
    client, s, vol = generata
    g = next(a for a in s["assegnazioni"] if a["origine"] == "generato" and a["ruolo"] == "soccorritore")
    posto = {k: g[k] for k in ("data", "postazione", "fascia", "segmento", "ruolo")}
    c = client.post(f"/api/settimane/{LUNEDI_A}/conferma")
    assert c.status_code == 200 and c.json()["stato"] == "confermata"
    assert client.post(f"/api/settimane/{LUNEDI_A}/genera", json={}).status_code == 400
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 400
    assert client.delete(f"/api/settimane/{LUNEDI_A}/generati").status_code == 400
    assert prenota(client, LUNEDI_A, vol["id"], **posto).status_code == 400
    r = client.post(f"/api/settimane/{LUNEDI_A}/riapri")
    assert r.status_code == 200 and r.json()["stato"] == "bozza"
    assert client.delete(f"/api/assegnazioni/{g['id']}").status_code == 204
    assert prenota(client, LUNEDI_A, vol["id"], **posto).status_code == 201


def test_statistiche(generata):
    client, s, vol = generata
    stats = client.get("/api/statistiche").json()
    per_id = {x["persona_id"]: x for x in stats}
    assert per_id[vol["id"]]["tipo"] == "volontario"
    assert per_id[vol["id"]]["ore_totali"] == 12 and per_id[vol["id"]]["saldo_ore"] == 0
    assert per_id[vol["id"]]["settimane"] == 1
    dip = [x for x in stats if x["tipo"] == "dipendente"]
    assert len(dip) == 14
    assert sum(x["ore_totali"] for x in dip) == 672 - 12
    assert all(x["settimane"] == 1 for x in dip)
    assert abs(sum(x["saldo_ore"] for x in dip)) < 1e-6
    assert set(dip[0]["weekend"]) == {"sab_giorno", "sab_notte", "dom_giorno", "dom_notte"}
    assert all(x["standby"] == 0 and x["programmati"] == 0 for x in stats)


def test_genera_settimana_successiva_usa_storico(generata):
    client, _, _ = generata
    r = client.post(f"/api/settimane/{LUNEDI_B}/genera", json={"tempo_max": 5})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["tipo"] == "B" and s["stato"] == "bozza"


# --- statici -----------------------------------------------------------------

def test_index_non_crasha(client):
    r = client.get("/")
    assert r.status_code in (200, 404)


# --- correzioni dalla security review ------------------------------------------

def test_persona_non_attiva_non_si_puo_assegnare(client):
    p = crea(client, "Ex", "dipendente", "autista")
    client.put(f"/api/persone/{p['id']}", json={"nome": "Ex", "tipo": "dipendente",
                                                 "qualifica": "autista", "attivo": False})
    r = prenota(client, LUNEDI_A, p["id"])
    assert r.status_code == 400


@pytest.mark.parametrize("data", ["0001-01-01", "9999-12-31"])
def test_date_estreme_rifiutate_senza_500(client, data):
    assert client.get(f"/api/settimane/{data}").status_code == 400


def test_generazione_concorrente_restituisce_409(client):
    staff_14(client)
    client.app.state.blocco_scrittura.acquire()
    try:
        r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5})
        assert r.status_code == 409
    finally:
        client.app.state.blocco_scrittura.release()


def test_generazione_fallita_non_cancella_i_turni_precedenti(generata):
    client, _, _ = generata
    prima = [a for a in client.get(f"/api/settimane/{LUNEDI_A}").json()["assegnazioni"] if a["origine"] == "generato"]
    assert prima
    for p in client.get("/api/persone").json():
        if p["tipo"] == "dipendente":
            client.put(f"/api/persone/{p['id']}", json={**{k: p[k] for k in ("nome", "tipo", "qualifica")},
                                                         "attivo": False})
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5})
    assert r.status_code == 409
    dopo = [a for a in client.get(f"/api/settimane/{LUNEDI_A}").json()["assegnazioni"] if a["origine"] == "generato"]
    assert len(dopo) == len(prima)


def test_id_persona_non_riutilizzato(client):
    a = crea(client, "A")
    b = crea(client, "B")
    client.delete(f"/api/persone/{b['id']}")
    c = crea(client, "C")
    assert c["id"] > b["id"] > a["id"]


# --- ferie ------------------------------------------------------------------------

def test_crud_ferie(client):
    p = crea(client, "Mario")
    r = client.post("/api/ferie", json={"persona_id": p["id"], "dal": "2026-10-20", "al": "2026-10-22"})
    assert r.status_code == 201, r.text
    f = r.json()
    assert f == {"id": f["id"], "persona_id": p["id"], "dal": "2026-10-20", "al": "2026-10-22"}
    assert client.get("/api/ferie").json() == [f]
    assert client.delete(f"/api/ferie/{f['id']}").status_code == 204
    assert client.get("/api/ferie").json() == []
    assert client.delete(f"/api/ferie/{f['id']}").status_code == 404


def test_ferie_non_valide(client):
    p = crea(client, "Mario")
    v = crea(client, "Anna", "volontario", "soccorritore")
    ok = {"persona_id": p["id"], "dal": "2026-10-20", "al": "2026-10-25"}
    assert client.post("/api/ferie", json=ok).status_code == 201
    casi = [
        {**ok, "dal": "2026-10-23", "al": "2026-10-28"},             # si sovrappone
        {**ok, "dal": "2026-11-05", "al": "2026-11-01"},             # dal dopo al
        {**ok, "persona_id": v["id"], "dal": "2026-11-01", "al": "2026-11-02"},  # volontario
    ]
    for body in casi:
        assert client.post("/api/ferie", json=body).status_code == 400, body
    assert client.post("/api/ferie", json={**ok, "persona_id": 9999}).status_code == 404


def test_settimana_mostra_ferie_e_quota(client):
    p = crea(client, "Mario")
    crea(client, "Luca")
    client.post("/api/ferie", json={"persona_id": p["id"], "dal": "2026-10-14", "al": "2026-10-21"})
    s = client.get(f"/api/settimane/{LUNEDI_A}").json()
    assert sorted(x["data"] for x in s["ferie"] if x["persona_id"] == p["id"]) == \
        ["2026-10-19", "2026-10-20", "2026-10-21"]
    r = next(x for x in s["riepilogo"] if x["persona_id"] == p["id"])
    assert r["giorni_ferie"] == 3
    # 3 giorni di ferie = 18h che contano nella media: (18 + 0) / 2
    assert r["ore_ferie"] == 18 and r["ore"] == 0
    assert s["media_ore"] == 9


# --- indisponibilità -----------------------------------------------------------------

def test_indisponibilita_settimanale(client):
    p = crea(client, "Mario")
    url = f"/api/settimane/{LUNEDI_A}/indisponibilita"
    r = client.put(url, json={"persona_id": p["id"], "turni": [
        {"data": "2026-10-20", "parte": "mattina"}, {"data": "2026-10-20", "parte": "notte"},
        {"data": "2026-10-24", "parte": "pomeriggio"}]})
    assert r.status_code == 200, r.text
    s = r.json()
    assert sorted((x["data"], x["parte"]) for x in s["indisponibilita"]) == [
        ("2026-10-20", "mattina"), ("2026-10-20", "notte"), ("2026-10-24", "pomeriggio")]
    assert all(x["persona_id"] == p["id"] for x in s["indisponibilita"])
    # il riepilogo conta i giorni con almeno una parte indisponibile
    assert [x["giorni_indisponibili"] for x in s["riepilogo"] if x["persona_id"] == p["id"]] == [2]
    # sostituisce quelle della persona in quella settimana
    r = client.put(url, json={"persona_id": p["id"], "turni": [{"data": "2026-10-21", "parte": "notte"}]})
    assert [(x["data"], x["parte"]) for x in r.json()["indisponibilita"]] == [("2026-10-21", "notte")]
    assert client.put(url, json={"persona_id": p["id"], "turni": []}).json()["indisponibilita"] == []
    assert client.put(url, json={"persona_id": 9999, "turni": []}).status_code == 404


def test_indisponibilita_validazione(client):
    p = crea(client, "Mario")
    v = crea(client, "Anna", "volontario", "soccorritore")
    url = f"/api/settimane/{LUNEDI_A}/indisponibilita"
    voce = {"data": "2026-10-20", "parte": "mattina"}
    assert client.put(url, json={"persona_id": p["id"], "turni": [{"data": "2026-10-27", "parte": "notte"}]}
                      ).status_code == 400  # fuori settimana
    assert client.put(url, json={"persona_id": p["id"], "turni": [{"data": "2026-10-20", "parte": "sera"}]}
                      ).status_code == 422
    assert client.put(url, json={"persona_id": p["id"], "date": ["2026-10-20"]}).status_code == 422
    assert client.put(url, json={"persona_id": p["id"], "turni": [voce] * 22}).status_code == 422
    assert client.put(url, json={"persona_id": v["id"], "turni": [voce]}).status_code == 400  # volontario


def test_indisponibilita_di_una_parte_non_blocca_le_altre(client):
    p = crea(client, "Mario")
    assert prenota(client, LUNEDI_A, p["id"], data="2026-10-20", segmento="mattina").status_code in (200, 201)
    url = f"/api/settimane/{LUNEDI_A}/indisponibilita"

    def errori():
        s = client.get(f"/api/settimane/{LUNEDI_A}").json()
        return [v for v in s["violazioni"] if v["codice"] == "indisponibile"]

    client.put(url, json={"persona_id": p["id"], "turni": [{"data": "2026-10-20", "parte": "pomeriggio"}]})
    assert not errori()
    client.put(url, json={"persona_id": p["id"], "turni": [{"data": "2026-10-20", "parte": "mattina"}]})
    assert errori()


def test_migrazione_della_vecchia_indisponibilita_a_giorno_intero(tmp_path):
    from datetime import date

    percorso = str(tmp_path / "vecchio.db")
    conn = db.connetti(percorso)
    pid = db.crea_persona(conn, "Mario", "dipendente", "autista")["id"]
    with conn:  # db "vecchio": una riga nella tabella a giorno intero
        conn.execute("INSERT INTO indisponibilita(persona_id, data) VALUES (?, ?)", (pid, "2026-10-21"))
    conn.close()
    for _ in range(2):  # la seconda apertura (o un avvio concorrente) non duplica né fallisce
        conn = db.connetti(percorso)
        assert db.indisponibili_periodo(conn, date(2026, 10, 19), date(2026, 10, 25)) == {
            pid: {(date(2026, 10, 21), parte) for parte in ("mattina", "pomeriggio", "notte")}}
        assert conn.execute("SELECT COUNT(*) FROM indisponibilita").fetchone()[0] == 0
        conn.close()


def test_indisponibilita_bloccata_se_settimana_confermata(client):
    p = crea(client, "Mario")
    client.post(f"/api/settimane/{LUNEDI_A}/conferma")
    r = client.put(f"/api/settimane/{LUNEDI_A}/indisponibilita", json={"persona_id": p["id"], "turni": []})
    assert r.status_code == 400


def test_genera_rispetta_ferie_e_indisponibilita(client):
    ids = staff_14(client)
    client.post("/api/ferie", json={"persona_id": ids[0], "dal": "2026-10-19", "al": "2026-10-21"})
    client.put(f"/api/settimane/{LUNEDI_A}/indisponibilita", json={
        "persona_id": ids[1], "turni": [{"data": "2026-10-24", "parte": x} for x in ("mattina", "pomeriggio", "notte")]})
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["report"]["scoperti"] == []
    assert not [a for a in s["assegnazioni"]
                if (a["persona_id"] == ids[0] and a["data"] <= "2026-10-21")
                or (a["persona_id"] == ids[1] and a["data"] == "2026-10-24")]
    assert not [v for v in s["violazioni"] if v["livello"] == "errore"]


def test_ferie_non_fanno_recuperare_ore_la_settimana_dopo(client):
    ids = staff_14(client)
    client.post("/api/ferie", json={"persona_id": ids[0], "dal": "2026-10-19", "al": "2026-10-23"})
    assert client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5}).status_code == 200
    stats = {x["persona_id"]: x for x in client.get("/api/statistiche").json()}
    assert stats[ids[0]]["saldo_ore"] == 0


def test_statistiche_partono_dalla_prima_settimana_generata(client):
    # avvio del sistema: la domenica della settimana prima è inserita a mano, solo come contesto
    ids = staff_14(client)
    vol = crea(client, "Volontario", "volontario", "soccorritore")
    prima = "2026-10-12"
    assert prenota(client, prima, ids[0], data="2026-10-18", ruolo="autista").status_code == 201
    assert prenota(client, prima, ids[8], data="2026-10-18", fascia="notte").status_code == 201
    assert prenota(client, prima, vol["id"], data="2026-10-18", postazione="Venarotta").status_code == 201
    assert client.post(f"/api/settimane/{prima}/conferma").status_code == 200
    stats = client.get("/api/statistiche").json()
    assert stats == []
    assert client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 5}).status_code == 200
    stats = {x["persona_id"]: x for x in client.get("/api/statistiche").json()}
    assert all(x["settimane"] == 1 for x in stats.values())
    assert sum(x["ore_totali"] for x in stats.values()) == 672
    assert vol["id"] not in stats
    assert stats[ids[0]]["weekend"]["dom_giorno"] + stats[ids[8]]["weekend"]["dom_notte"] <= 2


# --- volontari scritti per nome ------------------------------------------------------

def prenota_nome(client, nome, data=LUNEDI_A, postazione="Acquasanta", fascia="giorno",
                 segmento="intero", ruolo="soccorritore"):
    return client.post(f"/api/settimane/{LUNEDI_A}/assegnazioni", json={
        "data": data, "postazione": postazione, "fascia": fascia,
        "segmento": segmento, "ruolo": ruolo, "nome_volontario": nome,
    })


def test_volontario_si_prenota_scrivendo_solo_il_nome(client):
    r = prenota_nome(client, "  Anna Verdi ")
    assert r.status_code == 201, r.text
    a = r.json()["assegnazioni"][0]
    assert a["persona_nome"] == "Anna Verdi" and a["origine"] == "volontario"
    vol = [p for p in client.get("/api/persone").json() if p["tipo"] == "volontario"]
    assert [p["nome"] for p in vol] == ["Anna Verdi"]
    # lo stesso nome (maiuscole/spazi diversi) riusa la stessa persona: lo storico resta unito
    r = prenota_nome(client, "anna  verdi", data="2026-10-21")
    assert r.status_code == 201, r.text
    ids = {a["persona_id"] for a in r.json()["assegnazioni"]}
    assert ids == {vol[0]["id"]}
    assert len([p for p in client.get("/api/persone").json() if p["tipo"] == "volontario"]) == 1


def test_volontario_per_nome_nel_posto_da_autista(client):
    r = prenota_nome(client, "Paolo", ruolo="autista")
    assert r.status_code == 201, r.text
    p = next(p for p in client.get("/api/persone").json() if p["nome"] == "Paolo")
    assert p["qualifica"] == "autista"
    # un volontario già noto come soccorritore che fa l'autista diventa autista
    assert prenota_nome(client, "Gino").status_code == 201
    assert prenota_nome(client, "Gino", data="2026-10-22", ruolo="autista").status_code == 201
    gino = next(p for p in client.get("/api/persone").json() if p["nome"] == "Gino")
    assert gino["qualifica"] == "autista"


def test_volontario_disattivato_viene_riattivato(client):
    v = crea(client, "Lucia", "volontario", "soccorritore")
    client.put(f"/api/persone/{v['id']}", json={**{k: v[k] for k in ("nome", "tipo", "qualifica")}, "attivo": False})
    r = prenota_nome(client, "lucia")
    assert r.status_code == 201, r.text
    assert r.json()["assegnazioni"][0]["persona_id"] == v["id"]
    assert next(p for p in client.get("/api/persone").json() if p["id"] == v["id"])["attivo"] is True


def test_nome_volontario_non_valido(client):
    crea(client, "Mario Rossi")  # dipendente
    assert prenota_nome(client, "mario rossi").status_code == 400
    assert prenota_nome(client, "   ").status_code in (400, 422)
    body = {"data": LUNEDI_A, "postazione": "Acquasanta", "fascia": "giorno", "segmento": "intero",
            "ruolo": "soccorritore"}
    url = f"/api/settimane/{LUNEDI_A}/assegnazioni"
    assert client.post(url, json=body).status_code in (400, 422)                       # nessuno dei due
    assert client.post(url, json={**body, "persona_id": 1, "nome_volontario": "X"}).status_code in (400, 422)


# --- postazioni a richiesta: Standby e Programmati ---------------------------------------

def voce(data=LUNEDI_A, postazione="Programmati", fascia="giorno", segmento="prog_mattina",
         ruolo="autista", quantita=1):
    return {"data": data, "postazione": postazione, "fascia": fascia, "segmento": segmento,
            "ruolo": ruolo, "quantita": quantita}


def imposta_fabbisogno(client, voci, settimana=LUNEDI_A):
    return client.put(f"/api/settimane/{settimana}/fabbisogno", json={"voci": voci})


def test_persona_autista_programmati(client):
    r = client.post("/api/persone", json={"nome": "Sara", "tipo": "dipendente", "qualifica": "soccorritore",
                                          "autista_programmati": True})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["autista_programmati"] is True
    assert client.get("/api/persone").json()[0]["autista_programmati"] is True
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Sara", "tipo": "dipendente",
                                                    "qualifica": "soccorritore", "attivo": True})
    assert r.status_code == 200 and r.json()["autista_programmati"] is True  # campo assente: invariato
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Sara", "tipo": "dipendente", "qualifica": "soccorritore",
                                                    "attivo": True, "autista_programmati": False})
    assert r.json()["autista_programmati"] is False
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Sara", "tipo": "dipendente", "qualifica": "soccorritore",
                                                    "attivo": True, "autista_programmati": True})
    assert r.json()["autista_programmati"] is True
    assert client.get("/api/persone").json()[0]["autista_programmati"] is True


def test_payload_postazioni_a_richiesta(client):
    a = client.get(f"/api/settimane/{LUNEDI_A}").json()
    assert a["postazioni_a_richiesta"] == ["Standby", "Programmati"] and a["fabbisogno"] == []
    b = client.get(f"/api/settimane/{LUNEDI_B}").json()
    assert b["postazioni_a_richiesta"] == [] and b["fabbisogno"] == []


def test_imposta_fabbisogno_e_rimozione(client):
    voci = [voce(quantita=3),
            voce(data="2026-10-20", postazione="Standby", fascia="notte", segmento="standby", ruolo="autista"),
            voce(data="2026-10-20", postazione="Standby", fascia="notte", segmento="standby", ruolo="soccorritore")]
    r = imposta_fabbisogno(client, voci)
    assert r.status_code == 200, r.text
    s = r.json()
    assert sorted(s["fabbisogno"], key=lambda f: (f["data"], f["postazione"], f["ruolo"])) == sorted(
        voci, key=lambda f: (f["data"], f["postazione"], f["ruolo"]))
    # i posti richiesti e non coperti sono scoperti
    assert sum(1 for v in s["violazioni"] if v["codice"] == "scoperto" and v["data"] == LUNEDI_A) >= 1
    # aggiornamento della quantità e rimozione con 0
    s = imposta_fabbisogno(client, [voce(quantita=2), voci[1] | {"quantita": 0}]).json()
    assert len(s["fabbisogno"]) == 2
    assert voce(quantita=2) in s["fabbisogno"]
    assert all(f["ruolo"] == "soccorritore" for f in s["fabbisogno"] if f["postazione"] == "Standby")
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["fabbisogno"] == s["fabbisogno"]


@pytest.mark.parametrize("v", [
    voce(data="2026-10-26"),                                        # data fuori settimana
    voce(postazione="Acquasanta", segmento="intero"),               # postazione normale
    voce(postazione="Inesistente"),
    voce(segmento="standby"),                                       # segmento non dei Programmati
    voce(fascia="notte"),                                           # Programmati solo di giorno
    voce(postazione="Standby", segmento="standby_mattina"),         # Standby solo "standby"
    voce(postazione="Standby", segmento="standby", quantita=2),     # Standby 0-1
])
def test_fabbisogno_non_valido_400(client, v):
    r = imposta_fabbisogno(client, [v])
    assert r.status_code == 400, r.text
    assert isinstance(r.json()["detail"], str)
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["fabbisogno"] == []


def test_fabbisogno_tutto_o_niente(client):
    r = imposta_fabbisogno(client, [voce(), voce(data="2026-10-26")])
    assert r.status_code == 400
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["fabbisogno"] == []


def test_fabbisogno_quantita_fuori_limiti_422(client):
    assert imposta_fabbisogno(client, [voce(quantita=21)]).status_code in (400, 422)
    assert imposta_fabbisogno(client, [voce(quantita=-1)]).status_code in (400, 422)
    assert imposta_fabbisogno(client, [voce()] * 201).status_code in (400, 422)


def test_fabbisogno_settimana_b_o_confermata_400(client):
    assert imposta_fabbisogno(client, [voce(data=LUNEDI_B)], settimana=LUNEDI_B).status_code == 400
    assert client.post(f"/api/settimane/{LUNEDI_A}/conferma").status_code == 200
    assert imposta_fabbisogno(client, [voce()]).status_code == 400


def test_programmati_volontari_fino_alla_quantita(client):
    assert imposta_fabbisogno(client, [voce(quantita=2)]).status_code == 200
    kw = {"postazione": "Programmati", "segmento": "prog_mattina", "ruolo": "autista"}
    assert prenota_nome(client, "Uno", **kw).status_code == 201
    assert prenota_nome(client, "Due", **kw).status_code == 201
    r = prenota_nome(client, "Tre", **kw)
    assert r.status_code == 400
    # nessun volontario creato se la prenotazione fallisce
    assert "Tre" not in [p["nome"] for p in client.get("/api/persone").json()]
    # il pomeriggio è un turno a sé, non richiesto
    r = prenota_nome(client, "Uno", **{**kw, "segmento": "prog_pomeriggio"})
    assert r.status_code == 400 and "non richiesto" in r.json()["detail"]
    s = client.get(f"/api/settimane/{LUNEDI_A}").json()
    assert len([a for a in s["assegnazioni"] if a["postazione"] == "Programmati"]) == 2


def test_soccorritore_autista_programmati(client):
    sara = client.post("/api/persone", json={"nome": "Sara", "tipo": "dipendente", "qualifica": "soccorritore",
                                             "autista_programmati": True}).json()
    assert imposta_fabbisogno(client, [voce()]).status_code == 200
    r = prenota(client, LUNEDI_A, sara["id"], postazione="Programmati", segmento="prog_mattina", ruolo="autista")
    assert r.status_code == 201, r.text
    r = prenota(client, LUNEDI_A, sara["id"], data="2026-10-21", ruolo="autista")  # Acquasanta
    assert r.status_code == 400


def test_standby_spezzato_volontario_e_dipendente(client):
    voci = [voce(postazione="Standby", segmento="standby", ruolo=r) for r in ("autista", "soccorritore")]
    assert imposta_fabbisogno(client, voci).status_code == 200
    dip = crea(client, "Mario", "dipendente", "soccorritore")
    r = prenota_nome(client, "Anna", postazione="Standby", segmento="standby_mattina")
    assert r.status_code == 201, r.text
    r = prenota(client, LUNEDI_A, dip["id"], postazione="Standby", segmento="standby_pomeriggio")
    assert r.status_code == 201, r.text
    # il posto intero ora è occupato
    altro = crea(client, "Luca", "dipendente", "soccorritore")
    assert prenota(client, LUNEDI_A, altro["id"], postazione="Standby", segmento="standby").status_code == 400
    # segmento non ammesso per lo Standby
    assert prenota(client, LUNEDI_A, altro["id"], postazione="Standby", segmento="mattina").status_code == 400


def test_turno_a_richiesta_non_richiesto_400(client):
    p = crea(client, "Mario", "dipendente", "soccorritore")
    r = prenota(client, LUNEDI_A, p["id"], postazione="Standby", segmento="standby")
    assert r.status_code == 400 and "non richiesto" in r.json()["detail"]
    r = prenota_nome(client, "Nuovo", postazione="Programmati", segmento="prog_mattina")
    assert r.status_code == 400
    assert "Nuovo" not in [p["nome"] for p in client.get("/api/persone").json()]


def test_postazioni_a_richiesta_non_in_settimana_b(client):
    p = crea(client, "Mario", "dipendente", "soccorritore")
    r = prenota(client, LUNEDI_B, p["id"], postazione="Standby", segmento="standby")
    assert r.status_code == 400


def test_genera_con_fabbisogno(client):
    staff_14(client)
    crea(client, "Autista extra", "dipendente", "autista")
    crea(client, "Soccorritore extra", "dipendente", "soccorritore")
    voci = [voce(data="2026-10-20", postazione="Standby", fascia="notte", segmento="standby", ruolo=r)
            for r in ("autista", "soccorritore")]
    voci.append(voce(quantita=2))
    assert imposta_fabbisogno(client, voci).status_code == 200
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 10})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["report"]["scoperti"] == []
    assert not [v for v in s["violazioni"] if v["livello"] == "errore"]
    speciali = [a for a in s["assegnazioni"] if a["postazione"] in ("Standby", "Programmati")]
    assert len(speciali) == 4
    assert len([a for a in speciali if a["postazione"] == "Programmati" and a["ruolo"] == "autista"]) == 2


@pytest.mark.parametrize("backend", ["sqlite", "libsql"])
def test_migrazione_colonna_autista_programmati(tmp_path, monkeypatch, backend):
    import sqlite3

    percorso = tmp_path / "vecchio.db"
    vecchio = sqlite3.connect(percorso)
    vecchio.executescript("""
        CREATE TABLE persone (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, tipo TEXT NOT NULL,
            qualifica TEXT NOT NULL, attivo INTEGER NOT NULL DEFAULT 1);
        INSERT INTO persone(nome, tipo, qualifica) VALUES ('Vecchio', 'dipendente', 'autista');
    """)
    vecchio.commit()
    vecchio.close()
    if backend == "libsql":
        pytest.importorskip("libsql")
        monkeypatch.setattr(db, "remoto", lambda path: True)
    c = TestClient(create_app(str(percorso)))
    [p] = c.get("/api/persone").json()
    assert p["nome"] == "Vecchio" and p["autista_programmati"] is False
    colonne = [r[1] for r in sqlite3.connect(percorso).execute("PRAGMA table_info(persone)")]
    assert "autista_programmati" in colonne
    create_app(str(percorso))  # riaprire un DB già migrato non fallisce


# --- correzioni dalla review --------------------------------------------------------------

def test_put_persona_senza_flag_lo_mantiene(client):
    p = client.post("/api/persone", json={"nome": "Sara", "tipo": "dipendente", "qualifica": "soccorritore",
                                          "autista_programmati": True}).json()
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Sara B", "tipo": "dipendente",
                                                    "qualifica": "soccorritore", "attivo": True})
    assert r.status_code == 200 and r.json()["autista_programmati"] is True


def test_id_enormi_non_causano_errori_del_server(client):
    enorme = 2 ** 70
    corpo = {"nome": "X", "tipo": "dipendente", "qualifica": "autista", "attivo": True}
    assert client.put(f"/api/persone/{enorme}", json=corpo).status_code in (404, 422)
    assert client.delete(f"/api/assegnazioni/{enorme}").status_code in (404, 422)
    assert client.delete(f"/api/ferie/{enorme}").status_code in (404, 422)
    imposta_fabbisogno(client, [voce(quantita=2)])
    r = client.post(f"/api/settimane/{LUNEDI_A}/assegnazioni", json={
        "data": LUNEDI_A, "postazione": "Programmati", "fascia": "giorno", "segmento": "prog_mattina",
        "ruolo": "autista", "persona_id": enorme})
    assert r.status_code in (404, 422)


def test_stessa_persona_due_volte_nello_stesso_turno_programmati(client):
    p = crea(client, "Rino", "dipendente", "autista")
    imposta_fabbisogno(client, [voce(quantita=3)])
    corpo = {"data": LUNEDI_A, "postazione": "Programmati", "fascia": "giorno", "segmento": "prog_mattina",
             "ruolo": "autista"}
    url = f"/api/settimane/{LUNEDI_A}/assegnazioni"
    assert client.post(url, json={**corpo, "persona_id": p["id"]}).status_code == 201
    assert client.post(url, json={**corpo, "persona_id": p["id"]}).status_code == 400
    assert client.post(url, json={**corpo, "nome_volontario": "Gina"}).status_code == 201
    assert client.post(url, json={**corpo, "nome_volontario": "gina"}).status_code == 400


def test_nome_con_caratteri_di_controllo_rifiutato(client):
    r = client.post("/api/persone", json={"nome": "a\u0000b", "tipo": "volontario", "qualifica": "autista"})
    assert r.status_code == 422


# --- parametri dei dipendenti ------------------------------------------------------------

def test_scarto_ore_max_impostabile_e_nel_payload_della_settimana(client):
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["scarto_ore_max"] == 12
    r = client.put("/api/impostazioni", json={"scarto_ore_max": 6})
    assert r.status_code == 200
    assert r.json() == {"data_riferimento_a": LUNEDI_A, "scarto_ore_max": 6}  # la data resta com'è
    assert client.get("/api/impostazioni").json()["scarto_ore_max"] == 6
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["scarto_ore_max"] == 6


@pytest.mark.parametrize("valore", [0, -1, 25, 6.5, "dodici", None])
def test_scarto_ore_max_fuori_intervallo_422(client, valore):
    assert client.put("/api/impostazioni", json={"scarto_ore_max": valore}).status_code == 422


def test_impostazioni_vuote_422(client):
    assert client.put("/api/impostazioni", json={}).status_code == 422


def test_scarto_ore_max_usato_dal_validatore(client):
    a, b = crea(client, "Anna"), crea(client, "Bea")
    for giorno in ("2026-10-19", "2026-10-21"):
        assert prenota(client, LUNEDI_A, a["id"], data=giorno, ruolo="autista").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], data="2026-10-20", postazione="Venarotta",
                   ruolo="autista").status_code == 201

    def codici():
        return {v["codice"] for v in client.get(f"/api/settimane/{LUNEDI_A}").json()["violazioni"]}

    assert "ore" not in codici()  # 24h e 12h: differenza 12 su limite 12
    client.put("/api/impostazioni", json={"scarto_ore_max": 5})
    assert "ore" in codici()


def test_differenza_ore_nel_payload(client):
    a, b = crea(client, "Anna"), crea(client, "Bea")
    for giorno in ("2026-10-19", "2026-10-21"):
        assert prenota(client, LUNEDI_A, a["id"], data=giorno, ruolo="autista").status_code == 201
    assert prenota(client, LUNEDI_A, b["id"], data="2026-10-20", postazione="Venarotta",
                   ruolo="autista").status_code == 201
    s = client.get(f"/api/settimane/{LUNEDI_A}").json()
    assert s["scarto_ore_max"] == 12
    assert s["differenza_ore"] == {
        "differenza": 12, "limite": 12,
        "massimo": {"persona_id": a["id"], "nome": "Anna", "ore": 24},
        "minimo": {"persona_id": b["id"], "nome": "Bea", "ore": 12}}
    client.put("/api/impostazioni", json={"scarto_ore_max": 5})
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["differenza_ore"]["limite"] == 5


def test_differenza_ore_conta_le_ferie(client):
    a, b = crea(client, "Anna"), crea(client, "Bea")
    assert prenota(client, LUNEDI_A, a["id"], data="2026-10-19", ruolo="autista").status_code == 201
    assert client.post("/api/ferie", json={"persona_id": b["id"], "dal": "2026-10-20",
                                           "al": "2026-10-21"}).status_code == 201
    d = client.get(f"/api/settimane/{LUNEDI_A}").json()["differenza_ore"]
    assert d["massimo"]["ore"] == 12 and d["minimo"]["ore"] == 12 and d["differenza"] == 0


def test_differenza_ore_null_con_un_solo_dipendente(client):
    crea(client, "Anna")
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["differenza_ore"] is None


def test_differenza_ore_null_se_l_altro_ha_un_massimo(client):
    crea(client, "Anna")
    b = crea(client, "Bea")
    client.put(f"/api/persone/{b['id']}/parametri", json={"max_ore_settimana": 24})
    assert client.get(f"/api/settimane/{LUNEDI_A}").json()["differenza_ore"] is None


def test_massimo_ore_della_persona(client):
    p = crea(client, "Mario")
    assert client.get("/api/persone").json()[0]["max_ore_settimana"] is None
    r = client.put(f"/api/persone/{p['id']}/parametri", json={"max_ore_settimana": 24})
    assert r.status_code == 200 and r.json()["max_ore_settimana"] == 24 and r.json()["nome"] == "Mario"
    assert client.get("/api/persone").json()[0]["max_ore_settimana"] == 24
    r = client.put(f"/api/persone/{p['id']}/parametri", json={"max_ore_settimana": None})
    assert r.status_code == 200 and r.json()["max_ore_settimana"] is None
    assert client.get("/api/persone").json()[0]["max_ore_settimana"] is None


def test_modifica_persona_non_cancella_il_massimo_ore(client):
    p = crea(client, "Mario")
    client.put(f"/api/persone/{p['id']}/parametri", json={"max_ore_settimana": 30})
    r = client.put(f"/api/persone/{p['id']}", json={"nome": "Mario R", "tipo": "dipendente",
                                                    "qualifica": "autista", "attivo": True})
    assert r.json()["max_ore_settimana"] == 30


@pytest.mark.parametrize("corpo", [{"max_ore_settimana": 0}, {"max_ore_settimana": -5},
                                   {"max_ore_settimana": 169}, {"max_ore_settimana": 2.5},
                                   {"max_ore_settimana": "tanto"}, {}])
def test_massimo_ore_non_valido_422(client, corpo):
    p = crea(client, "Mario")
    assert client.put(f"/api/persone/{p['id']}/parametri", json=corpo).status_code == 422


def test_massimo_ore_persona_inesistente_404(client):
    assert client.put("/api/persone/999/parametri", json={"max_ore_settimana": 10}).status_code == 404


def test_massimo_ore_segnalato_dal_validatore_e_nel_riepilogo(client):
    a, b = crea(client, "Anna"), crea(client, "Bea")
    client.put(f"/api/persone/{a['id']}/parametri", json={"max_ore_settimana": 12})
    for giorno in ("2026-10-19", "2026-10-21"):
        assert prenota(client, LUNEDI_A, a["id"], data=giorno, ruolo="autista").status_code == 201
    s = client.get(f"/api/settimane/{LUNEDI_A}").json()
    assert any(v["codice"] == "ore_max" and v["persona_id"] == a["id"] for v in s["violazioni"])
    riga = next(r for r in s["riepilogo"] if r["persona_id"] == a["id"])
    assert riga["max_ore_settimana"] == 12
    assert next(r for r in s["riepilogo"] if r["persona_id"] == b["id"])["max_ore_settimana"] is None


def test_crud_divieti(client):
    p = crea(client, "Mario")
    assert client.get("/api/divieti").json() == []
    r = client.post("/api/divieti", json={"persona_id": p["id"], "postazione": "Venarotta", "turno": "notte"})
    assert r.status_code == 201
    d = r.json()
    assert d["persona_id"] == p["id"] and d["postazione"] == "Venarotta" and d["turno"] == "notte"
    solo_turno = client.post("/api/divieti", json={"persona_id": p["id"], "turno": "mattina"}).json()
    assert solo_turno["postazione"] is None and solo_turno["turno"] == "mattina"
    solo_postazione = client.post("/api/divieti", json={"persona_id": p["id"], "postazione": "Ascoli"}).json()
    assert solo_postazione["turno"] is None
    assert [x["id"] for x in client.get("/api/divieti").json()] == [d["id"], solo_turno["id"], solo_postazione["id"]]
    assert client.delete(f"/api/divieti/{d['id']}").status_code == 204
    assert [x["id"] for x in client.get("/api/divieti").json()] == [solo_turno["id"], solo_postazione["id"]]
    assert client.delete(f"/api/divieti/{d['id']}").status_code == 404


def test_divieti_validazione(client):
    p = crea(client, "Mario")
    v = crea(client, "Anna", "volontario", "soccorritore")
    ok = {"persona_id": p["id"], "postazione": "Venarotta", "turno": "notte"}
    assert client.post("/api/divieti", json={"persona_id": p["id"]}).status_code == 400  # né postazione né turno
    assert client.post("/api/divieti", json={"persona_id": p["id"], "postazione": None,
                                             "turno": None}).status_code == 400
    assert client.post("/api/divieti", json={**ok, "persona_id": 999}).status_code == 404
    assert client.post("/api/divieti", json={**ok, "persona_id": v["id"]}).status_code == 400  # volontario
    assert client.post("/api/divieti", json={**ok, "postazione": "Atlantide"}).status_code == 400
    assert client.post("/api/divieti", json={**ok, "turno": "sera"}).status_code == 422
    assert client.post("/api/divieti", json={**ok, "postazione": ""}).status_code == 422
    assert client.post("/api/divieti", json=ok).status_code == 201
    assert client.post("/api/divieti", json=ok).status_code == 400  # duplicato
    assert client.post("/api/divieti", json={"persona_id": p["id"], "turno": "notte"}).status_code == 201
    assert client.post("/api/divieti", json={"persona_id": p["id"], "turno": "notte"}).status_code == 400
    assert client.post("/api/divieti", json={**ok, "postazione": "Standby"}).status_code == 201  # a richiesta
    assert client.delete("/api/divieti/999").status_code == 404


def test_eliminando_la_persona_si_eliminano_i_divieti(client):
    p = crea(client, "Mario")
    altro = crea(client, "Luca")
    client.post("/api/divieti", json={"persona_id": p["id"], "turno": "notte"})
    client.post("/api/divieti", json={"persona_id": altro["id"], "turno": "notte"})
    assert client.delete(f"/api/persone/{p['id']}").status_code == 204
    assert [d["persona_id"] for d in client.get("/api/divieti").json()] == [altro["id"]]


def test_turno_manuale_vietato_segnalato(client):
    p = crea(client, "Mario")
    client.post("/api/divieti", json={"persona_id": p["id"], "postazione": "Venarotta", "turno": "notte"})
    r = prenota(client, LUNEDI_A, p["id"], postazione="Venarotta", fascia="notte", ruolo="autista")
    assert r.status_code == 201  # il turno manuale si può fare: è il validatore a segnalarlo
    assert any(v["codice"] == "divieto" and v["persona_id"] == p["id"] for v in r.json()["violazioni"])


def test_la_generazione_rispetta_massimo_ore_divieti_e_banda(client):
    ids = staff_14(client)
    client.put("/api/impostazioni", json={"scarto_ore_max": 14})
    client.put(f"/api/persone/{ids[0]}/parametri", json={"max_ore_settimana": 24})
    client.post("/api/divieti", json={"persona_id": ids[1], "turno": "notte"})
    r = client.post(f"/api/settimane/{LUNEDI_A}/genera", json={"tempo_max": 10})
    assert r.status_code == 200, r.text
    s = r.json()
    righe = {x["persona_id"]: x for x in s["riepilogo"]}
    assert righe[ids[0]]["ore"] <= 24
    assert not [a for a in s["assegnazioni"] if a["persona_id"] == ids[1] and a["fascia"] == "notte"]
    assert not [v for v in s["violazioni"] if v["livello"] == "errore"]
