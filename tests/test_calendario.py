from datetime import date, timedelta

from cvap.calendario import giorni_settimana, lunedi, postazioni_attive, tipo_settimana
from cvap.modello import Postazione

from .conftest import LUNEDI_A

POSTAZIONI = [
    Postazione("Acquasanta", solo_settimane_b=False),
    Postazione("Venarotta", solo_settimane_b=False),
    Postazione("Ascoli", solo_settimane_b=True),
]


def test_lunedi_riporta_qualsiasi_giorno_al_lunedi_della_settimana():
    assert lunedi(date(2026, 10, 25)) == LUNEDI_A  # domenica
    assert lunedi(date(2026, 10, 21)) == LUNEDI_A  # mercoledi
    assert lunedi(LUNEDI_A) == LUNEDI_A


def test_settimana_di_riferimento_e_tipo_a_e_si_alterna():
    assert tipo_settimana(LUNEDI_A, LUNEDI_A) == "A"
    assert tipo_settimana(LUNEDI_A + timedelta(weeks=1), LUNEDI_A) == "B"
    assert tipo_settimana(LUNEDI_A + timedelta(weeks=2), LUNEDI_A) == "A"
    assert tipo_settimana(LUNEDI_A - timedelta(weeks=1), LUNEDI_A) == "B"
    assert tipo_settimana(LUNEDI_A + timedelta(weeks=51), LUNEDI_A) == "B"


def test_riferimento_non_lunedi_viene_normalizzato():
    assert tipo_settimana(LUNEDI_A, LUNEDI_A + timedelta(days=3)) == "A"


def test_giorni_settimana_da_lunedi_a_domenica():
    giorni = giorni_settimana(date(2026, 10, 22))
    assert giorni[0] == LUNEDI_A
    assert len(giorni) == 7
    assert giorni[-1].weekday() == 6


def test_ascoli_attiva_solo_nelle_settimane_b():
    assert postazioni_attive("A", POSTAZIONI) == ["Acquasanta", "Venarotta"]
    assert postazioni_attive("B", POSTAZIONI) == ["Acquasanta", "Venarotta", "Ascoli"]
