"""Dipendenti liberi giorno per giorno (nessun turno di giorno), con avvisi per le notti."""
from datetime import timedelta

from fastapi.testclient import TestClient

from cvap.app import create_app
from cvap.calendario import giorni_settimana
from cvap.liberi import liberi_settimana

from .conftest import LUNEDI_A, ass

GIORNI = giorni_settimana(LUNEDI_A)
DIPENDENTI = {1: "Mario", 2: "Anna", 3: "Luca"}


def giorno(i):
    return LUNEDI_A + timedelta(days=i)


def del_giorno(risultato, i):
    return next(x for x in risultato if x["data"] == giorno(i).isoformat())


def nomi(voci):
    return [v["nome"] for v in voci]


def mario(risultato, i):
    return next(v for v in del_giorno(risultato, i)["liberi"] if v["persona_id"] == 1)


# --- funzione pura -------------------------------------------------------------------

def test_un_elemento_per_giorno_della_settimana():
    r = liberi_settimana(GIORNI, DIPENDENTI, [], {}, {})
    assert [x["data"] for x in r] == [g.isoformat() for g in GIORNI]


def test_senza_turni_tutti_liberi_in_ordine_alfabetico():
    r = del_giorno(liberi_settimana(GIORNI, DIPENDENTI, [], {}, {}), 0)
    assert nomi(r["liberi"]) == ["Anna", "Luca", "Mario"]
    assert all(v["avvisi"] == [] for v in r["liberi"])
    assert r["ferie"] == [] and r["indisponibili"] == []


def test_chi_lavora_di_giorno_non_e_libero():
    turni = [ass(giorno(0), "Acquasanta", "giorno", "autista", 1),
             ass(giorno(0), "Venarotta", "giorno", "autista", 2, segmento="mattina")]
    r = liberi_settimana(GIORNI, DIPENDENTI, turni, {}, {})
    assert nomi(del_giorno(r, 0)["liberi"]) == ["Luca"]
    assert nomi(del_giorno(r, 1)["liberi"]) == ["Anna", "Luca", "Mario"]


def test_chi_fa_la_notte_quel_giorno_e_libero_con_avviso():
    r = liberi_settimana(GIORNI, DIPENDENTI, [ass(giorno(2), "Acquasanta", "notte", "autista", 1)], {}, {})
    assert mario(r, 2)["avvisi"] == ["notte"]


def test_chi_smonta_dalla_notte_e_libero_con_avviso():
    r = liberi_settimana(GIORNI, DIPENDENTI, [ass(giorno(2), "Acquasanta", "notte", "autista", 1)], {}, {})
    assert mario(r, 3)["avvisi"] == ["smonto_notte"]


def test_smonto_e_notte_di_fila_hanno_entrambi_gli_avvisi():
    notti = [ass(giorno(2), "Acquasanta", "notte", "autista", 1), ass(giorno(3), "Acquasanta", "notte", "autista", 1)]
    assert mario(liberi_settimana(GIORNI, DIPENDENTI, notti, {}, {}), 3)["avvisi"] == ["smonto_notte", "notte"]


def test_la_notte_della_domenica_prima_vale_per_il_lunedi():
    domenica_prima = LUNEDI_A - timedelta(days=1)
    r = liberi_settimana(GIORNI, DIPENDENTI, [ass(domenica_prima, "Acquasanta", "notte", "autista", 1)], {}, {})
    assert r[0]["data"] == LUNEDI_A.isoformat()
    assert mario(r, 0)["avvisi"] == ["smonto_notte"]


def test_la_notte_dello_standby_conta_come_notte():
    r = liberi_settimana(GIORNI, DIPENDENTI, [ass(giorno(1), "Standby", "notte", "autista", 1, segmento="standby")],
                         {}, {})
    assert mario(r, 1)["avvisi"] == ["notte"]


def test_chi_e_in_ferie_va_nell_elenco_a_parte():
    r = del_giorno(liberi_settimana(GIORNI, DIPENDENTI, [], {2: {giorno(4)}}, {}), 4)
    assert nomi(r["liberi"]) == ["Luca", "Mario"]
    assert r["ferie"] == [{"persona_id": 2, "nome": "Anna"}]


def test_chi_e_indisponibile_va_nell_elenco_a_parte_con_le_parti():
    indisp = {3: {(giorno(1), "notte"), (giorno(1), "mattina")}}
    r = del_giorno(liberi_settimana(GIORNI, DIPENDENTI, [], {}, indisp), 1)
    assert nomi(r["liberi"]) == ["Anna", "Mario"]
    assert r["indisponibili"] == [{"persona_id": 3, "nome": "Luca", "parti": ["mattina", "notte"], "avvisi": []}]


def test_indisponibile_ma_di_turno_di_giorno_non_compare():
    turni = [ass(giorno(1), "Acquasanta", "giorno", "autista", 3)]
    r = del_giorno(liberi_settimana(GIORNI, DIPENDENTI, turni, {}, {3: {(giorno(1), "notte")}}), 1)
    assert 3 not in [v["persona_id"] for v in r["liberi"] + r["indisponibili"]]


def test_le_assegnazioni_di_chi_non_e_tra_i_dipendenti_sono_ignorate():
    r = liberi_settimana(GIORNI, DIPENDENTI, [ass(giorno(0), "Acquasanta", "giorno", "autista", 99)], {}, {})
    assert nomi(del_giorno(r, 0)["liberi"]) == ["Anna", "Luca", "Mario"]


# --- API -------------------------------------------------------------------------------

def test_payload_settimana_contiene_i_liberi(tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db")))

    def crea(nome, tipo="dipendente"):
        r = client.post("/api/persone", json={"nome": nome, "tipo": tipo, "qualifica": "autista"})
        assert r.status_code == 201, r.text
        return r.json()

    mario_id, anna_id = crea("Mario")["id"], crea("Anna")["id"]
    crea("Vito", "volontario")
    spento = crea("Spento")
    client.put(f"/api/persone/{spento['id']}", json={**spento, "attivo": False})
    domenica_prima = (LUNEDI_A - timedelta(days=1)).isoformat()
    r = client.post(f"/api/settimane/{domenica_prima}/assegnazioni", json={
        "data": domenica_prima, "postazione": "Acquasanta", "fascia": "notte", "segmento": "intero",
        "ruolo": "autista", "persona_id": mario_id})
    assert r.status_code == 201, r.text
    r = client.post("/api/ferie", json={"persona_id": anna_id, "dal": LUNEDI_A.isoformat(), "al": LUNEDI_A.isoformat()})
    assert r.status_code == 201, r.text

    s = client.get(f"/api/settimane/{LUNEDI_A.isoformat()}").json()
    assert [x["data"] for x in s["liberi"]] == s["giorni"]
    lunedi = s["liberi"][0]
    # solo dipendenti attivi: niente volontari né disattivati
    assert lunedi["liberi"] == [{"persona_id": mario_id, "nome": "Mario", "avvisi": ["smonto_notte"]}]
    assert lunedi["ferie"] == [{"persona_id": anna_id, "nome": "Anna", "motivo": "ferie"}]
