"""Minimo di 36 ore a settimana per ogni dipendente (ferie comprese, 6h al giorno)."""
from datetime import timedelta

from cvap.calendario import giorni_settimana
from cvap.modello import Persona
from cvap.solver import StoricoPersona, genera
from cvap.vincoli import ORE_MIN_SETTIMANA, valida_settimana

from .conftest import LUNEDI_A, ass, staff

STAZIONI = ["Acquasanta", "Venarotta"]
GIORNI = giorni_settimana(LUNEDI_A)


def giorno(i):
    return LUNEDI_A + timedelta(days=i)


def turni(pid, n, postazione="Acquasanta"):
    """n turni di giorno interi (12h l'uno) a giorni alterni."""
    return [ass(giorno(2 * i), postazione, "giorno", "autista", pid) for i in range(n)]


def sotto_minimo(persone, assegnazioni, **kw):
    v = valida_settimana(GIORNI, STAZIONI, assegnazioni, {p.id: p for p in persone}, **kw)
    return [x for x in v if x.codice == "ore_min"]


MARIO = Persona(1, "Mario", "dipendente", "autista")
LUCA = Persona(2, "Luca", "dipendente", "autista")


# --- validatore ------------------------------------------------------------------

def test_il_minimo_e_36_ore():
    assert ORE_MIN_SETTIMANA == 36


def test_sotto_le_36_ore_e_errore():
    v = sotto_minimo([MARIO, LUCA], turni(1, 2) + turni(2, 3, "Venarotta"))
    assert len(v) == 1
    assert v[0].livello == "errore" and v[0].persona_id == 1
    assert v[0].messaggio == "Mario: 24h, meno del minimo di 36h a settimana"


def test_esattamente_36_ore_va_bene():
    assert sotto_minimo([MARIO], turni(1, 3)) == []


def test_le_ferie_contano_6_ore_al_giorno_nel_minimo():
    ferie = {1: {giorno(5), giorno(6)}}  # 12h di ferie + 24h lavorate = 36
    assert sotto_minimo([MARIO], turni(1, 2), ferie=ferie) == []


def test_ferie_comprese_ma_ancora_sotto_il_minimo():
    ferie = {1: {giorno(6)}}  # 6h di ferie + 24h lavorate = 30
    v = sotto_minimo([MARIO], turni(1, 2), ferie=ferie)
    assert [x.messaggio for x in v] == ["Mario: 24h + 6h ferie, meno del minimo di 36h a settimana"]


def test_chi_e_in_ferie_tutta_la_settimana_non_ha_minimo():
    assert sotto_minimo([MARIO], [], ferie={1: set(GIORNI)}) == []


def test_i_volontari_non_hanno_minimo():
    vol = Persona(50, "Volontaria", "volontario", "soccorritore")
    a = [ass(giorno(0), "Acquasanta", "giorno", "soccorritore", 50, origine="volontario")]
    assert sotto_minimo([vol], a) == []


def test_con_un_massimo_sotto_36_vale_il_massimo():
    # non dovrebbe capitare, ma le due regole non devono mai contraddirsi
    mario = Persona(1, "Mario", "dipendente", "autista", max_ore_settimana=24)
    assert sotto_minimo([mario], turni(1, 2)) == []


# --- generatore ------------------------------------------------------------------

def test_il_generatore_non_scende_sotto_36_ore_neanche_per_recuperare():
    # Autista 1 ha lavorato molto in passato: il recupero lo spingerebbe sotto le 36 ore
    persone = staff(4, 4)
    storico = {p.id: StoricoPersona(settimane=4) for p in persone}
    storico[1] = StoricoPersona(settimane=4, saldo_ore=96)
    r = genera(GIORNI, ["Acquasanta"], persone, storico=storico, tempo_max=10, scarto_ore_max=48)
    assert r.scoperti == []
    assert min(r.ore.values()) >= 36
    assert "minimo" not in r.messaggio


def test_il_generatore_segnala_chi_resta_sotto_il_minimo():
    # 14 turni da soccorritore per 6 soccorritori: almeno uno non arriva a 3 turni (36h)
    persone = staff(4, 6)
    r = genera(GIORNI, ["Acquasanta"], persone, tempo_max=10)
    assert r.scoperti == []
    sotto = [p for p in persone if r.ore[p.id] < 36]
    assert sotto
    assert "Sotto il minimo di 36h: " in r.messaggio
    assert all(p.nome in r.messaggio for p in sotto)
    v = valida_settimana(GIORNI, ["Acquasanta"], r.assegnazioni, {p.id: p for p in persone})
    assert {x.persona_id for x in v if x.codice == "ore_min"} == {p.id for p in sotto}


def test_il_generatore_conta_le_ferie_nel_minimo():
    persone = staff(4, 4)
    ferie = {1: {GIORNI[4], GIORNI[5], GIORNI[6]}}  # 18h di ferie: bastano 2 turni
    r = genera(GIORNI, ["Acquasanta"], persone, ferie=ferie, tempo_max=10)
    assert r.ore[1] + 18 >= 36
    assert "minimo" not in r.messaggio
