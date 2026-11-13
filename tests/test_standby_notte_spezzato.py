"""Standby di notte spezzabile dai volontari: 19-23 (`standby_sera`) e 23-7 (`standby_notte`), come il giorno
(7-14 / 14-19). Il fabbisogno resta il turno intero; i dipendenti fanno il turno intero, o la metà che nessun
volontario copre."""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("CVAP_DB", ":memory:")

from cvap.app import create_app  # noqa: E402
from cvap.calendario import giorni_settimana  # noqa: E402
from cvap.email_turni import orario_turno  # noqa: E402
from cvap.modello import STANDBY, Fabbisogno, orario, parti_turno, si_sovrappongono, turno_ammesso  # noqa: E402
from cvap.slot import unita_da_coprire  # noqa: E402
from cvap.solver import genera  # noqa: E402
from cvap.vincoli import valida_settimana  # noqa: E402

from .conftest import LUNEDI_A, ass, staff  # noqa: E402

GIORNI = giorni_settimana(LUNEDI_A)
LUNEDI = LUNEDI_A.isoformat()


def standby_notte():
    return [Fabbisogno(LUNEDI_A, STANDBY, "notte", "standby", r, 1) for r in ("autista", "soccorritore")]


# --- modello ---------------------------------------------------------------------------------

def test_orari_e_turni_ammessi():
    base = LUNEDI_A.toordinal() * 24
    assert orario(LUNEDI_A, "notte", "standby_sera") == (base + 19, base + 23)
    assert orario(LUNEDI_A, "notte", "standby_notte") == (base + 23, base + 31)
    assert turno_ammesso(STANDBY, "notte", "standby_sera") and turno_ammesso(STANDBY, "notte", "standby_notte")
    assert not turno_ammesso(STANDBY, "giorno", "standby_sera")
    assert not turno_ammesso("Acquasanta", "notte", "standby_sera")
    assert parti_turno("notte", "standby_sera") == {"notte"}
    assert si_sovrappongono("standby_sera", "standby") and not si_sovrappongono("standby_sera", "standby_notte")
    assert orario_turno("notte", "standby_sera") == "Sera 19–23"
    assert orario_turno("notte", "standby_notte") == "Notte 23–7"


# --- posti da coprire e controlli --------------------------------------------------------------

def test_volontario_su_mezza_notte_di_standby_lascia_l_altra_meta():
    occupate = [ass(LUNEDI_A, STANDBY, "notte", "soccorritore", 99, segmento="standby_sera", origine="volontario")]
    unita = unita_da_coprire(GIORNI, [], occupate, standby_notte())
    assert sorted((u.ruolo, u.segmento, u.ore) for u in unita) == [
        ("autista", "standby", 12), ("soccorritore", "standby_notte", 8)]


def test_notte_di_standby_spezzata_e_coperta_non_e_scoperta_ne_doppione():
    p = {x.id: x for x in staff(1, 2)}
    a = [ass(LUNEDI_A, STANDBY, "notte", "autista", 1, segmento="standby"),
         ass(LUNEDI_A, STANDBY, "notte", "soccorritore", 2, segmento="standby_sera"),
         ass(LUNEDI_A, STANDBY, "notte", "soccorritore", 3, segmento="standby_notte")]
    codici = {x.codice for x in valida_settimana(GIORNI, [], a, p, fabbisogno=standby_notte()) if x.livello == "errore"}
    assert not codici & {"scoperto", "doppione", "eccesso", "segmento"}
    a.append(ass(LUNEDI_A, STANDBY, "notte", "soccorritore", 3, segmento="standby"))
    codici = {x.codice for x in valida_settimana(GIORNI, [], a, p, fabbisogno=standby_notte()) if x.livello == "errore"}
    assert {"doppione", "eccesso"} & codici


def test_il_generatore_da_al_dipendente_solo_la_meta_scoperta():
    fissi = [ass(LUNEDI_A, STANDBY, "notte", "soccorritore", 99, segmento="standby_sera", origine="volontario")]
    persone = staff(2, 2)
    r = genera(GIORNI, [], persone, fissi=fissi, fabbisogno=standby_notte(), tempo_max=5)
    assert r.scoperti == []
    socc = [a for a in r.assegnazioni if a.ruolo == "soccorritore" and a.persona_id != 99]
    assert [a.segmento for a in socc] == ["standby_notte"]
    assert [a.segmento for a in r.assegnazioni if a.ruolo == "autista"] == ["standby"]


# --- API ----------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def test_api_notte_di_standby_spezzata_tra_volontario_e_dipendente(client):
    voci = [{"data": LUNEDI, "postazione": STANDBY, "fascia": "notte", "segmento": "standby", "ruolo": r,
             "quantita": 1} for r in ("autista", "soccorritore")]
    assert client.put(f"/api/settimane/{LUNEDI}/fabbisogno", json={"voci": voci}).status_code == 200
    mario = client.post("/api/persone", json={"nome": "Mario", "tipo": "dipendente", "qualifica": "soccorritore"}).json()
    turno = {"data": LUNEDI, "postazione": STANDBY, "fascia": "notte", "ruolo": "soccorritore"}
    r = client.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={**turno, "segmento": "standby_sera",
                                                                   "nome_volontario": "Anna"})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={**turno, "segmento": "standby_notte",
                                                                   "persona_id": mario["id"]})
    assert r.status_code == 201, r.text
    luca = client.post("/api/persone", json={"nome": "Luca", "tipo": "dipendente", "qualifica": "soccorritore"}).json()
    r = client.post(f"/api/settimane/{LUNEDI}/assegnazioni", json={**turno, "segmento": "standby",
                                                                   "persona_id": luca["id"]})
    assert r.status_code == 400  # il posto è già tutto coperto
    # il fabbisogno resta solo il turno intero
    voci[0]["segmento"] = "standby_sera"
    assert client.put(f"/api/settimane/{LUNEDI}/fabbisogno", json={"voci": voci}).status_code == 400

