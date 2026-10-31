"""Assistenze ed Extra: richieste con nome, orario libero (ore intere) e posti per autisti e soccorritori,
in tutte le settimane (A e B). Il generatore le riempie con i dipendenti, ma le copre per ultime."""
import pytest
from fastapi.testclient import TestClient

from cvap.calendario import giorni_settimana
from cvap.modello import EXTRA, Fabbisogno, Persona, Unita, orario, parti_turno, segmento_extra
from cvap.solver import genera
from cvap.vincoli import valida_settimana

from .conftest import LUNEDI_A, LUNEDI_B, ass, staff

GIORNI = giorni_settimana(LUNEDI_A)
MARTEDI = GIORNI[1]


# --- modello -------------------------------------------------------------------------

def test_orario_di_una_richiesta():
    base = MARTEDI.toordinal() * 24
    seg = segmento_extra(7, 9, 13)
    assert orario(MARTEDI, "giorno", seg) == (base + 9, base + 13)
    u = Unita(MARTEDI, EXTRA, "giorno", seg, "autista")
    assert u.ore == 4


def test_una_richiesta_puo_passare_la_mezzanotte():
    base = MARTEDI.toordinal() * 24
    seg = segmento_extra(3, 22, 26)
    assert orario(MARTEDI, "notte", seg) == (base + 22, base + 26)
    assert parti_turno("notte", seg) == {"notte"}


def test_parti_della_giornata_di_una_richiesta():
    assert parti_turno("giorno", segmento_extra(1, 9, 13)) == {"mattina"}
    assert parti_turno("giorno", segmento_extra(1, 15, 18)) == {"pomeriggio"}
    assert parti_turno("giorno", segmento_extra(1, 10, 22)) == {"mattina", "pomeriggio", "notte"}


def test_orario_non_valido():
    with pytest.raises(ValueError):
        orario(MARTEDI, "giorno", "extra_1_13_9")  # finisce prima di iniziare
    with pytest.raises(ValueError):
        orario(MARTEDI, "giorno", "extra_1_9_40")  # più di 24 ore


# --- generatore e regole ---------------------------------------------------------------

def richiesta(d, rid, inizio, fine, autisti=0, soccorritori=0):
    seg = segmento_extra(rid, inizio, fine)
    fascia = "giorno" if 7 <= inizio < 19 else "notte"
    out = []
    if autisti:
        out.append(Fabbisogno(d, EXTRA, fascia, seg, "autista", autisti))
    if soccorritori:
        out.append(Fabbisogno(d, EXTRA, fascia, seg, "soccorritore", soccorritori))
    return out


def test_il_generatore_riempie_le_richieste_e_le_ore_contano():
    persone = staff(12, 12)
    richieste = richiesta(MARTEDI, 1, 9, 13, autisti=2, soccorritori=2)
    r = genera(GIORNI, ["Acquasanta", "Venarotta"], persone, fabbisogno=richieste, tempo_max=20)
    extra = [a for a in r.assegnazioni if a.postazione == EXTRA]
    assert len(extra) == 4 and not [u for u in r.scoperti if u.postazione == EXTRA]
    assert sorted(a.ruolo for a in extra) == ["autista", "autista", "soccorritore", "soccorritore"]
    assert all(a.ore == 4 for a in extra)
    mappa = {p.id: p for p in persone}
    v = valida_settimana(GIORNI, ["Acquasanta", "Venarotta"], r.assegnazioni, mappa, fabbisogno=richieste)
    assert not [x for x in v if x.livello == "errore"], v


def test_se_il_personale_non_basta_resta_scoperta_prima_la_richiesta():
    # un solo autista per due posti alla stessa ora (la notte della sede e la richiesta)
    persone = [Persona(1, "Rino", "dipendente", "autista")]
    richieste = richiesta(MARTEDI, 1, 20, 23, autisti=1)
    r = genera([MARTEDI], [], persone, fabbisogno=richieste, tempo_max=5)
    assert [a.postazione for a in r.assegnazioni] == [EXTRA]  # da sola viene coperta
    r = genera([MARTEDI], ["Acquasanta"], persone, fabbisogno=richieste, tempo_max=5)
    assert EXTRA not in {a.postazione for a in r.assegnazioni}
    assert any(u.postazione == EXTRA for u in r.scoperti)


def test_la_richiesta_scoperta_e_un_errore_e_quella_in_piu_un_eccesso():
    richieste = richiesta(MARTEDI, 1, 9, 13, autisti=1)
    v = valida_settimana(GIORNI, [], [], {}, fabbisogno=richieste)
    assert [x.codice for x in v] == ["scoperto"]
    seg = segmento_extra(1, 9, 13)
    a = [ass(MARTEDI, EXTRA, "giorno", "autista", 1, seg), ass(MARTEDI, EXTRA, "giorno", "autista", 2, seg)]
    v = valida_settimana(GIORNI, [], a, {p.id: p for p in staff(2, 0)}, fabbisogno=richieste)
    assert "eccesso" in {x.codice for x in v} and "segmento" not in {x.codice for x in v}


# --- API -----------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    from cvap.app import create_app
    return TestClient(create_app(str(tmp_path / "t.db")))


def crea_persona(c, nome, tipo="dipendente", qualifica="autista"):
    r = c.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": qualifica})
    assert r.status_code == 201, r.text
    return r.json()


def nuova(c, settimana, **campi):
    corpo = {"data": str(settimana), "nome": "Partita stadio", "inizio": 15, "fine": 19,
             "autisti": 1, "soccorritori": 1, **campi}
    return c.post(f"/api/settimane/{settimana}/extra", json=corpo)


@pytest.mark.parametrize("settimana", [LUNEDI_A, LUNEDI_B])
def test_si_aggiunge_una_richiesta_in_ogni_settimana(client, settimana):
    r = nuova(client, settimana, autisti=2, soccorritori=2)
    assert r.status_code == 201, r.text
    s = r.json()
    [e] = s["extra"]
    assert (e["nome"], e["data"], e["inizio"], e["fine"], e["autisti"], e["soccorritori"]) == \
        ("Partita stadio", str(settimana), 15, 19, 2, 2)
    assert e["fascia"] == "giorno" and e["segmento"] == segmento_extra(e["id"], 15, 19)
    posti = {(f["ruolo"], f["quantita"]) for f in s["fabbisogno"] if f["postazione"] == EXTRA}
    assert posti == {("autista", 2), ("soccorritore", 2)}
    assert sum(1 for v in s["violazioni"] if v["codice"] == "scoperto") >= 2


def test_richiesta_di_notte_oltre_la_mezzanotte(client):
    s = nuova(client, LUNEDI_B, inizio=22, fine=2, nome="Concerto").json()
    [e] = s["extra"]
    assert (e["inizio"], e["fine"], e["fascia"]) == (22, 2, "notte")
    assert e["segmento"] == segmento_extra(e["id"], 22, 26)


@pytest.mark.parametrize("campi", [
    {"autisti": 0, "soccorritori": 0},  # nessun posto
    {"inizio": 9, "fine": 9},           # nessuna durata
    {"inizio": 24},
    {"fine": -1},
    {"nome": ""},
    {"data": "2026-11-30"},             # fuori dalla settimana
    {"autisti": 21},
])
def test_richieste_non_valide(client, campi):
    assert nuova(client, LUNEDI_A, **campi).status_code in (400, 422)


def test_volontario_nella_richiesta_e_posti_esauriti(client):
    e = nuova(client, LUNEDI_B, autisti=1, soccorritori=0).json()["extra"][0]
    corpo = {"data": LUNEDI_B.isoformat(), "postazione": EXTRA, "fascia": "giorno", "segmento": e["segmento"],
             "ruolo": "autista"}
    r = client.post(f"/api/settimane/{LUNEDI_B}/assegnazioni", json={**corpo, "nome_volontario": "Vol. Ugo"})
    assert r.status_code == 201, r.text
    [a] = [a for a in r.json()["assegnazioni"] if a["postazione"] == EXTRA]
    assert a["persona_nome"] == "Vol. Ugo" and a["ore"] == 4
    r = client.post(f"/api/settimane/{LUNEDI_B}/assegnazioni", json={**corpo, "nome_volontario": "Vol. Ada"})
    assert r.status_code == 400
    # segmento di una richiesta che non c'è
    r = client.post(f"/api/settimane/{LUNEDI_B}/assegnazioni",
                    json={**corpo, "segmento": segmento_extra(999, 15, 19), "nome_volontario": "Vol. Ada"})
    assert r.status_code == 400


def test_modifica_e_eliminazione_portano_con_se_le_persone(client):
    e = nuova(client, LUNEDI_B, autisti=1, soccorritori=0).json()["extra"][0]
    client.post(f"/api/settimane/{LUNEDI_B}/assegnazioni", json={
        "data": LUNEDI_B.isoformat(), "postazione": EXTRA, "fascia": "giorno", "segmento": e["segmento"],
        "ruolo": "autista", "nome_volontario": "Vol. Ugo"})
    r = client.put(f"/api/extra/{e['id']}", json={
        "data": LUNEDI_B.isoformat(), "nome": "Fiera", "inizio": 20, "fine": 1, "autisti": 2, "soccorritori": 1})
    assert r.status_code == 200, r.text
    s = r.json()
    [e2] = s["extra"]
    assert (e2["nome"], e2["fascia"], e2["segmento"]) == ("Fiera", "notte", segmento_extra(e["id"], 20, 25))
    [a] = [a for a in s["assegnazioni"] if a["postazione"] == EXTRA]
    assert (a["segmento"], a["fascia"], a["ore"]) == (e2["segmento"], "notte", 5)
    assert client.delete(f"/api/extra/{e['id']}").status_code == 204
    s = client.get(f"/api/settimane/{LUNEDI_B}").json()
    assert s["extra"] == [] and not [a for a in s["assegnazioni"] if a["postazione"] == EXTRA]
    assert client.delete(f"/api/extra/{e['id']}").status_code == 404


def test_settimana_confermata_non_si_tocca(client):
    e = nuova(client, LUNEDI_B).json()["extra"][0]
    assert client.post(f"/api/settimane/{LUNEDI_B}/conferma").status_code == 200
    assert nuova(client, LUNEDI_B).status_code == 400
    assert client.delete(f"/api/extra/{e['id']}").status_code == 400


def test_generazione_con_richiesta_e_ore_nel_riepilogo(client):
    for i in range(10):
        crea_persona(client, f"Autista {i}", qualifica="autista")
        crea_persona(client, f"Socc {i}", qualifica="soccorritore")
    nuova(client, LUNEDI_B, data=str(MARTEDI + (LUNEDI_B - LUNEDI_A)), inizio=9, fine=13,
          autisti=1, soccorritori=1)
    r = client.post(f"/api/settimane/{LUNEDI_B}/genera", json={"tempo_max": 10})
    assert r.status_code == 200, r.text
    s = r.json()
    extra = [a for a in s["assegnazioni"] if a["postazione"] == EXTRA]
    assert len(extra) == 2
    ore = {x["persona_id"]: x["ore"] for x in s["riepilogo"]}
    for a in extra:
        turni = [b for b in s["assegnazioni"] if b["persona_id"] == a["persona_id"]]
        assert ore[a["persona_id"]] == sum(b["ore"] for b in turni)
