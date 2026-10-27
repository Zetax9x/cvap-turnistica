"""Massimo di 72 ore lavorate a settimana per ogni dipendente: nessuno può superarlo."""
from datetime import timedelta

from fastapi.testclient import TestClient

from cvap.app import create_app
from cvap.calendario import giorni_settimana
from cvap.modello import Persona
from cvap.solver import genera
from cvap.vincoli import ORE_MAX_SETTIMANA, massimo_ore, valida_settimana

from .conftest import LUNEDI_A, LUNEDI_B, ass, staff

STAZIONI = ["Acquasanta", "Venarotta"]
GIORNI = giorni_settimana(LUNEDI_A)


def giorno(i):
    return LUNEDI_A + timedelta(days=i)


def oltre_massimo(persone, assegnazioni, **kw):
    v = valida_settimana(GIORNI, STAZIONI, assegnazioni, {p.id: p for p in persone}, **kw)
    return [x for x in v if x.codice == "ore_max"]


def sette_giorni(pid):
    """Un turno di giorno intero (12h) ogni giorno: 84h."""
    return [ass(giorno(i), "Acquasanta", "giorno", "autista", pid) for i in range(7)]


MARIO = Persona(1, "Mario", "dipendente", "autista")


def test_il_massimo_e_72_ore():
    assert ORE_MAX_SETTIMANA == 72


def test_massimo_ore_della_persona():
    assert massimo_ore(MARIO) == 72
    assert massimo_ore(Persona(2, "Luca", "dipendente", "autista", max_ore_settimana=30)) == 30
    assert massimo_ore(Persona(3, "Sara", "dipendente", "autista", max_ore_settimana=80)) == 72


# --- validatore ------------------------------------------------------------------

def test_oltre_72_ore_e_errore_anche_senza_massimo_personale():
    v = oltre_massimo([MARIO], sette_giorni(1))
    assert len(v) == 1
    assert v[0].livello == "errore" and v[0].persona_id == 1
    assert v[0].messaggio == "Mario: 84h, oltre il massimo di 72h a settimana"


def test_esattamente_72_ore_va_bene():
    assert oltre_massimo([MARIO], sette_giorni(1)[:6]) == []


def test_le_ferie_non_contano_nel_massimo():
    assert oltre_massimo([MARIO], sette_giorni(1)[:6], ferie={1: {giorno(6)}}) == []


def test_un_massimo_personale_sopra_72_non_alza_il_tetto():
    sara = Persona(1, "Sara", "dipendente", "autista", max_ore_settimana=80)
    assert [x.messaggio for x in oltre_massimo([sara], sette_giorni(1))] == [
        "Sara: 84h, oltre il massimo di 72h a settimana"]


def test_i_volontari_non_hanno_massimo():
    vito = Persona(1, "Vito", "volontario", "autista")
    assert oltre_massimo([vito], sette_giorni(1)) == []


# --- generatore --------------------------------------------------------------------

def test_il_generatore_non_supera_mai_72_ore_e_segnala_gli_scoperti():
    giorni = giorni_settimana(LUNEDI_B)
    ris = genera(giorni, ["Acquasanta"], staff(2, 2), tempo_max=10)
    assert max(ris.ore.values()) <= ORE_MAX_SETTIMANA
    assert ris.scoperti
    assert "posti non coperti" in ris.messaggio


def test_il_generatore_non_aggiunge_turni_a_chi_ha_gia_72_ore_fissate():
    persone = staff(8, 6)
    fissi = [ass(giorno(i), "Acquasanta", "giorno", "autista", 1, origine="manuale") for i in (0, 1, 3, 4)]
    fissi += [ass(giorno(5), "Venarotta", "notte", "autista", 1, origine="manuale"),
              ass(giorno(6), "Venarotta", "notte", "autista", 1, origine="manuale")]
    ris = genera(GIORNI, STAZIONI, persone, fissi=fissi, tempo_max=10)
    assert not [a for a in ris.assegnazioni if a.persona_id == 1]
    assert ris.ore[1] == 72


# --- API -------------------------------------------------------------------------------

def test_il_massimo_personale_non_puo_superare_72(tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db")))
    p = client.post("/api/persone", json={"nome": "Mario", "tipo": "dipendente", "qualifica": "autista"}).json()
    url = f"/api/persone/{p['id']}/parametri"
    assert client.put(url, json={"max_ore_settimana": 73}).status_code == 422
    assert client.put(url, json={"max_ore_settimana": 72}).status_code == 200
