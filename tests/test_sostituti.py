"""Sostituti: chi può coprire un turno già assegnato (ad es. di chi va in ferie)."""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")  # l'app di modulo non deve creare data/turni.db

from cvap.app import create_app  # noqa: E402
from cvap.modello import Assegnazione, Divieto, Persona  # noqa: E402
from cvap.sostituti import candidati_sostituzione  # noqa: E402

LUN = date(2026, 10, 19)  # settimana A
GIORNI = [LUN + timedelta(days=i) for i in range(7)]
SEDE = "Acquasanta"
ALTRA = "Venarotta"


def persona(pid, nome, qualifica="autista", tipo="dipendente", **kw):
    return Persona(pid, nome, tipo, qualifica, **kw)


def turno(pid, giorno=0, fascia="giorno", ruolo="soccorritore", postazione=SEDE, segmento="intero"):
    return Assegnazione(LUN + timedelta(days=giorno), postazione, fascia, segmento, ruolo, pid)


def calcola(da_coprire, assegnazioni, persone, **kw):
    return candidati_sostituzione(da_coprire, [p.id for p in persone.values() if p.dipendente],
                                  giorni=GIORNI, postazioni=[SEDE, ALTRA], assegnazioni=assegnazioni,
                                  persone=persone, **kw)


def ids(candidati):
    return [c.persona_id for c in candidati]


# --- funzione pura ------------------------------------------------------------------

def test_propone_chi_e_libero_e_non_chi_e_assente():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Libero"), 3: persona(3, "In ferie")}
    t = turno(1)
    out = calcola(t, [t], persone, ferie={1: {LUN}, 3: {LUN}})
    assert ids(out) == [2]


def test_esclude_chi_non_rispetta_riposo_o_si_sovrappone():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Notte prima"), 3: persona(3, "Stesso turno"),
               4: persona(4, "Libero")}
    t = turno(1, giorno=1)
    notte_prima = turno(2, giorno=0, fascia="notte")           # finisce alle 8 del giorno del turno
    stesso = turno(3, giorno=1, ruolo="autista")               # già in servizio nelle stesse ore
    out = calcola(t, [t, notte_prima, stesso], persone)
    assert ids(out) == [4]


def test_esclude_divieti_qualifica_e_indisponibili():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Divieto", divieti=(Divieto(SEDE, "giorno"),)),
               3: persona(3, "Soccorritore", qualifica="soccorritore"), 4: persona(4, "Indisponibile"),
               5: persona(5, "Volontario", tipo="volontario"), 6: persona(6, "Buono")}
    t = turno(1, ruolo="autista")
    out = candidati_sostituzione(t, [1, 2, 3, 4, 5, 6], giorni=GIORNI, postazioni=[SEDE], assegnazioni=[t],
                                 persone=persone, indisponibili={4: {(LUN, "mattina")}})
    assert ids(out) == [6]


def test_chi_violerebbe_riposo_o_giorni_di_fila_e_proposto_con_avviso():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Tre giorni"), 3: persona(3, "Poco riposo"),
               4: persona(4, "Libero")}
    t = turno(1, giorno=3, fascia="notte")                                    # 20-8
    gia = [turno(2, giorno=g, fascia="notte", postazione=ALTRA) for g in (0, 1, 2)]  # con questa: 4 notti di fila
    gia.append(turno(3, giorno=3, segmento="mattina", postazione=ALTRA))      # 8-14: solo 6 h di riposo
    out = calcola(t, [t, *gia], persone)
    assert ids(out) == [4, 2, 3] or ids(out) == [4, 3, 2]
    regole = {c.persona_id: " ".join(c.regole) for c in out}
    assert regole[4] == ""
    assert "di fila" in regole[2]
    assert "riposo" in regole[3]


def test_mai_chi_lavorerebbe_piu_di_12_ore_di_fila():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Notte prima"), 3: persona(3, "Standby prima"),
               4: persona(4, "Libero")}
    t = turno(1, giorno=1)                                                    # 8-20
    notte = turno(2, giorno=0, fascia="notte")                                # 20-8: 24 h senza staccare
    standby = Assegnazione(GIORNI[1], "Standby", "giorno", "standby_mattina", "soccorritore", 3)  # 7-14: si sovrappone
    out = calcola(t, [t, notte, standby], persone)
    assert ids(out) == [4]


def test_le_ore_delle_sostituzioni_non_contano_nei_limiti_di_ore():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Tetto", max_ore_settimana=12), 3: persona(3, "Vuoto")}
    t = turno(1, giorno=6)
    gia = [turno(2, giorno=0)]                       # già al suo massimo di 12 h
    out = calcola(t, [t, *gia], persone, ferie={1: {GIORNI[6]}})
    tetto = next(c for c in out if c.persona_id == 2)
    assert tetto.regole == tetto.avvisi == ()        # niente "oltre il massimo", niente differenza ore
    assert (tetto.ore, tetto.ore_sostituzioni, tetto.ore_dopo) == (12, 0, 24)


def test_le_sostituzioni_gia_fatte_sono_extra():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Ha sostituito")}
    t = turno(1, giorno=3)
    extra = Assegnazione(GIORNI[0], SEDE, "giorno", "intero", "soccorritore", 2, "sostituzione")
    out = calcola(t, [t, extra], persone)
    assert (out[0].ore, out[0].ore_sostituzioni, out[0].ore_contate, out[0].ore_dopo) == (0, 12, 0, 24)


def test_ordina_per_ore_e_mette_in_fondo_chi_ha_avvisi():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Tante ore"), 3: persona(3, "Poche ore"),
               4: persona(4, "Due di fila")}
    t = turno(1, giorno=3)
    gia = [turno(2, giorno=g, postazione=ALTRA) for g in (5, 6)]
    gia += [turno(4, giorno=1, postazione=ALTRA), turno(4, giorno=2, postazione=ALTRA)]  # con il 3: tre di fila
    out = calcola(t, [t, *gia], persone, scarto_ore_max=72)  # qui non conta la differenza ore
    assert ids(out) == [3, 2, 4]
    poche = out[0]
    assert (poche.nome, poche.ore, poche.ore_dopo, poche.avvisi) == ("Poche ore", 0, 12, ())
    assert out[1].avvisi == () and out[2].regole == ()   # 3 di fila è un'eccezione ammessa: solo una nota
    assert any("di fila" in a for a in out[2].avvisi)


def test_le_ferie_contano_nelle_ore_per_l_ordine():
    persone = {1: persona(1, "Malato"), 2: persona(2, "Ferie due giorni"), 3: persona(3, "Un turno")}
    t = turno(1, giorno=0)
    out = calcola(t, [t, turno(3, giorno=4)], persone, ferie={1: {LUN}, 2: {GIORNI[5], GIORNI[6]}})
    # 12 h contate per entrambi: a pari ore conta il nome
    assert ids(out) == [2, 3]
    assert (out[0].ore, out[0].ore_contate) == (0, 12)


def test_turno_che_non_e_nella_settimana_da_errore():
    with pytest.raises(ValueError):
        calcola(turno(1), [], {1: persona(1, "X")})


# --- API ----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea(client, nome, qualifica="autista", tipo="dipendente"):
    r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def prenota(client, persona_id, data="2026-10-20", fascia="giorno", ruolo="soccorritore"):
    r = client.post("/api/settimane/2026-10-19/assegnazioni", json={
        "data": data, "postazione": SEDE, "fascia": fascia, "segmento": "intero", "ruolo": ruolo,
        "persona_id": persona_id})
    assert r.status_code == 201, r.text
    return next(a["id"] for a in r.json()["assegnazioni"]
                if a["persona_id"] == persona_id and a["data"] == data and a["fascia"] == fascia)


def test_api_sostituti_di_chi_va_in_ferie(client):
    malato, libero, notte = crea(client, "Malato"), crea(client, "Libero"), crea(client, "Notte")
    aid = prenota(client, malato)
    prenota(client, notte, data="2026-10-19", fascia="notte")
    client.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-21",
                                    "motivo": "ferie"})
    r = client.get(f"/api/assegnazioni/{aid}/sostituti")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assenza"] == "ferie"
    assert body["turno"]["id"] == aid and body["turno"]["persona_nome"] == "Malato"
    assert [c["persona_id"] for c in body["candidati"]] == [libero]
    assert body["candidati"][0] == {"persona_id": libero, "nome": "Libero", "qualifica": "autista", "ore": 0,
                                    "ore_sostituzioni": 0, "ore_contate": 0, "ore_dopo": 12, "regole": [], "avvisi": []}


def test_api_sostituisci_scambia_la_persona(client):
    malato, libero = crea(client, "Malato"), crea(client, "Libero")
    aid = prenota(client, malato)
    r = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": libero})
    assert r.status_code == 200, r.text
    turni = [(a["persona_id"], a["data"], a["origine"]) for a in r.json()["assegnazioni"]]
    assert turni == [(libero, "2026-10-20", "sostituzione")]


def test_api_sostituisci_rifiuta_casi_non_validi(client):
    malato, socc = crea(client, "Malato"), crea(client, "Socc", qualifica="soccorritore")
    spento = crea(client, "Spento")
    client.put(f"/api/persone/{spento}", json={"nome": "Spento", "tipo": "dipendente", "qualifica": "autista",
                                                "attivo": False})
    aid = prenota(client, malato, ruolo="autista")
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": socc}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": spento}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": malato}).status_code == 400
    assert client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": 9999}).status_code == 404
    assert client.post("/api/assegnazioni/9999/sostituisci", json={"persona_id": socc}).status_code == 404
    assert client.get("/api/assegnazioni/9999/sostituti").status_code == 404
    # la sostituzione fallita non tocca il turno
    s = client.get("/api/settimane/2026-10-19").json()
    assert [a["persona_id"] for a in s["assegnazioni"]] == [malato]


def test_api_sostituisci_in_settimana_confermata(client):
    malato, libero = crea(client, "Malato"), crea(client, "Libero")
    aid = prenota(client, malato)
    client.post("/api/settimane/2026-10-19/conferma")
    assert client.get(f"/api/assegnazioni/{aid}/sostituti").status_code == 200   # i suggerimenti si vedono
    r = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": libero})
    assert r.status_code == 400 and "riaprila" in r.json()["detail"]


@pytest.mark.parametrize("motivo", ["ferie", "malattia"])
def test_api_turni_coinvolti_da_un_assenza(client, motivo):
    malato, altro = crea(client, "Malato"), crea(client, "Altro")
    prenota(client, malato, data="2026-10-20")
    prenota(client, malato, data="2026-10-23")
    prenota(client, altro, data="2026-10-21")
    assenza = client.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-21",
                                             "motivo": motivo})
    assert assenza.status_code == 201, assenza.text
    f = assenza.json()
    r = client.get(f"/api/ferie/{f['id']}/turni")
    assert r.status_code == 200, r.text
    attesi = [("2026-10-20", "2026-10-19", SEDE)] if motivo == "ferie" else []
    assert [(t["data"], t["settimana"], t["postazione"]) for t in r.json()] == attesi
    tabellone = client.get("/api/settimane/2026-10-19").json()
    turni_attesi = [(malato, "2026-10-23"), (altro, "2026-10-21")]
    if motivo == "ferie":
        turni_attesi.append((malato, "2026-10-20"))
    assert sorted((a["persona_id"], a["data"]) for a in tabellone["assegnazioni"]) == sorted(turni_attesi)
    assert client.get("/api/ferie/9999/turni").status_code == 404


# --- le ore delle sostituzioni sono extra: fuori da limiti, storico e statistiche -------------------

def test_validatore_non_conta_le_sostituzioni_nelle_ore():
    from cvap.vincoli import valida_settimana
    persone = {1: persona(1, "A", max_ore_settimana=12), 2: persona(2, "B")}
    turni = [turno(1, giorno=0), turno(2, giorno=0, ruolo="autista"),
             Assegnazione(GIORNI[2], SEDE, "giorno", "intero", "soccorritore", 1, "sostituzione"),
             Assegnazione(GIORNI[4], SEDE, "giorno", "intero", "soccorritore", 1, "sostituzione")]
    codici = {v.codice for v in valida_settimana(GIORNI, [], turni, persone)}
    assert not codici & {"ore_max", "ore"}           # 36 h lavorate da A, ma 24 sono extra


def test_storico_non_conta_le_sostituzioni():
    from cvap.storico import SettimanaPassata, calcola_storico
    turni = [turno(1, giorno=0), Assegnazione(GIORNI[5], SEDE, "giorno", "intero", "soccorritore", 1, "sostituzione")]
    s = SettimanaPassata(media_ore=12, dipendenti=[1], assegnazioni=turni)
    st = calcola_storico([s])[1]
    assert (st.ore_lavorate, st.saldo_ore, st.weekend["sab_giorno"], st.ore_sostituzioni) == (12, 0, 0, 12)


def test_api_ore_extra_in_settimana_statistiche_e_riepilogo(client, tmp_path):
    malato, libero = crea(client, "Malato"), crea(client, "Libero")
    aid = prenota(client, malato, data="2026-10-24")      # sabato
    prenota(client, libero, data="2026-10-19")
    s = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": libero}).json()
    r = next(x for x in s["riepilogo"] if x["persona_id"] == libero)
    assert (r["ore"], r["ore_sostituzioni"], r["turni_weekend"]) == (12, 12, 0)
    # statistiche: la settimana conta se ha turni generati; qui la si segna come generata a mano
    from cvap import db
    conn = db.connetti(str(tmp_path / "t.db"))
    with conn:
        conn.execute("UPDATE assegnazioni SET origine = 'generato' WHERE origine = 'manuale'")
        conn.execute("INSERT OR REPLACE INTO settimane(inizio, stato, dipendenti) VALUES (?, 'bozza', ?)",
                     ("2026-10-19", f"[{malato}, {libero}]"))
    conn.close()
    st = next(x for x in client.get("/api/statistiche").json() if x["persona_id"] == libero)
    assert (st["ore_lavorate"], st["ore_sostituzioni"], st["weekend"]["sab_giorno"]) == (12, 12, 0)
    rp = client.get(f"/api/statistiche/persona/{libero}?dal=2026-10-19&al=2026-10-25").json()["riepilogo"]
    assert (rp["ore_lavorate"], rp["turni"], rp["ore_sostituzioni"], rp["turni_sostituzioni"]) == (12, 1, 12, 1)
    assert rp["weekend"]["sab_giorno"] == 0


def test_mai_chi_staccherebbe_solo_un_ora():
    # Standby 7-19 e poi la notte 20-8: un'ora di pausa non interrompe il lavoro (25 h di fila)
    persone = {1: persona(1, "Malato"), 2: persona(2, "Standby"), 3: persona(3, "Libero")}
    t = turno(1, giorno=2, fascia="notte")
    standby = Assegnazione(GIORNI[2], "Standby", "giorno", "standby", "soccorritore", 2)
    assert ids(calcola(t, [t, standby], persone)) == [3]


def test_ore_di_fila():
    from cvap.sostituti import ore_di_fila
    giorno, notte = turno(1, giorno=0), turno(1, giorno=0, fascia="notte")
    assert ore_di_fila([], giorno) == 12
    assert ore_di_fila([giorno], notte) == 24
    assert ore_di_fila([turno(1, giorno=1)], notte) == 24          # notte 20-8 e giorno dopo 8-20
    assert ore_di_fila([turno(1, giorno=2)], notte) == 12


def test_il_generatore_non_conta_le_ore_delle_sostituzioni():
    from cvap.solver import _ore_fisse
    extra = Assegnazione(LUN, SEDE, "giorno", "intero", "soccorritore", 1, "sostituzione")
    assert _ore_fisse([persona(1, "A")], [extra, turno(1, giorno=2)]) == {1: 12}


def test_sostituzione_su_turno_sparito_non_crea_doppioni(tmp_path):
    from cvap import db
    conn = db.connetti(str(tmp_path / "x.db"))
    pid = db.crea_persona(conn, "A", "dipendente", "autista")["id"]
    aid = db.crea_assegnazione(conn, turno(pid))
    db.elimina_assegnazione(conn, aid)
    assert db.sostituisci_assegnazione(conn, aid, turno(pid, giorno=1)) is None
    assert db.assegnazioni_periodo(conn, LUN, GIORNI[-1]) == []
    conn.close()


def test_api_sostituisci_rifiuta_chi_non_puo_prendere_il_turno(client):
    malato, assente, occupato = crea(client, "Malato"), crea(client, "Assente"), crea(client, "Occupato")
    aid = prenota(client, malato)
    r = client.post("/api/settimane/2026-10-19/assegnazioni", json={
        "data": "2026-10-20", "postazione": ALTRA, "fascia": "giorno", "segmento": "intero", "ruolo": "autista",
        "persona_id": occupato})
    assert r.status_code == 201, r.text
    client.post("/api/ferie", json={"persona_id": assente, "dal": "2026-10-20", "al": "2026-10-20"})
    for pid in (assente, occupato):
        r = client.post(f"/api/assegnazioni/{aid}/sostituisci", json={"persona_id": pid})
        assert r.status_code == 400 and "non può prendere" in r.json()["detail"]


# --- catena: B prende il turno del malato e cede un suo turno a C (un solo passaggio) ------------------

def scenario_catena():
    """Nessuno copre direttamente il giorno 8-20 di martedì: B ha la notte prima (24 h di fila), C ha un divieto.
    Ma B può prenderlo cedendo la sua notte a C."""
    persone = {1: persona(1, "Malato"), 2: persona(2, "B"),
               3: persona(3, "C", divieti=(Divieto(SEDE, "giorno"),)), 4: persona(4, "Assente")}
    t = turno(1, giorno=1)
    notte_b = turno(2, giorno=0, fascia="notte", postazione=ALTRA)
    return persone, t, notte_b


def test_catena_quando_nessuno_copre_direttamente():
    from cvap.sostituti import catene_sostituzione
    persone, t, notte_b = scenario_catena()
    ferie = {1: {GIORNI[1]}, 4: {GIORNI[0], GIORNI[1]}}
    assert calcola(t, [t, notte_b], persone, ferie=ferie) == [] or all(
        c.regole for c in calcola(t, [t, notte_b], persone, ferie=ferie))
    catene = catene_sostituzione(t, [1, 2, 3, 4], giorni=GIORNI, postazioni=[SEDE, ALTRA],
                                 assegnazioni=[t, notte_b], persone=persone, ferie=ferie)
    assert [(k.prende.persona_id, k.ceduto, k.copre.persona_id) for k in catene] == [(2, notte_b, 3)]
    k = catene[0]
    assert (k.prende.ore, k.prende.ore_dopo) == (12, 12)           # B: scambia un turno, ore normali
    assert (k.copre.ore_sostituzioni, k.copre.ore_dopo) == (0, 12)  # C: lavora in più, ore extra
    assert k.prende.regole == k.copre.regole == ()


def test_niente_catene_se_c_e_un_sostituto_diretto():
    from cvap.sostituti import catene_sostituzione
    persone, t, notte_b = scenario_catena()
    persone[5] = persona(5, "Libero")
    catene = catene_sostituzione(t, [2, 3, 5], giorni=GIORNI, postazioni=[SEDE, ALTRA],
                                 assegnazioni=[t, notte_b], persone=persone, ferie={1: {GIORNI[1]}})
    assert catene == []


def test_api_catena(client):
    malato, b, c = crea(client, "Malato"), crea(client, "B"), crea(client, "C")
    client.post("/api/divieti", json={"persona_id": c, "postazione": SEDE, "turno": "giorno"})
    aid = prenota(client, malato)                                                   # mar 20/10 8-20
    r = client.post("/api/settimane/2026-10-19/assegnazioni", json={
        "data": "2026-10-19", "postazione": ALTRA, "fascia": "notte", "segmento": "intero", "ruolo": "autista",
        "persona_id": b})
    notte = next(a["id"] for a in r.json()["assegnazioni"] if a["persona_id"] == b)
    client.post("/api/ferie", json={"persona_id": malato, "dal": "2026-10-20", "al": "2026-10-20",
                                    "motivo": "ferie"})
    body = client.get(f"/api/assegnazioni/{aid}/sostituti").json()
    assert all(x["regole"] for x in body["candidati"])
    catena = body["catene"][0]
    assert (catena["prende"]["persona_id"], catena["ceduto"]["id"], catena["copre"]["persona_id"]) == (b, notte, c)
    # una catena non valida è rifiutata e non tocca nulla
    sbagliata = client.post(f"/api/assegnazioni/{aid}/catena",
                            json={"persona_id": c, "ceduto_id": notte, "sostituto_id": b})
    assert sbagliata.status_code == 400
    r = client.post(f"/api/assegnazioni/{aid}/catena", json={"persona_id": b, "ceduto_id": notte, "sostituto_id": c})
    assert r.status_code == 200, r.text
    turni = sorted((a["persona_id"], a["data"], a["fascia"], a["origine"]) for a in r.json()["assegnazioni"])
    assert turni == sorted([(b, "2026-10-20", "giorno", "manuale"), (c, "2026-10-19", "notte", "sostituzione")])
    assert client.post(f"/api/assegnazioni/{aid}/catena",
                       json={"persona_id": b, "ceduto_id": notte, "sostituto_id": c}).status_code == 404


def test_si_propongono_piu_catene_e_il_massimo_le_limita():
    from cvap.sostituti import catene_sostituzione
    persone, t, notte_b = scenario_catena()
    persone[5] = persona(5, "B due")
    notte_b2 = turno(5, giorno=0, fascia="notte", postazione=ALTRA, ruolo="autista")
    tutti = dict(giorni=GIORNI, postazioni=[SEDE, ALTRA], assegnazioni=[t, notte_b, notte_b2], persone=persone,
                 ferie={1: {GIORNI[1]}, 4: {GIORNI[0], GIORNI[1]}})
    assert len(catene_sostituzione(t, [2, 3, 4, 5], **tutti)) == 2               # due scambi possibili: li propone
    assert len(catene_sostituzione(t, [2, 3, 4, 5], massimo=1, **tutti)) == 1    # il massimo li limita
