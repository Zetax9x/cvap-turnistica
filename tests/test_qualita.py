"""Indicatori di qualità della generazione (punteggio, distanza dall'ottimo, soluzioni trovate...)."""
from cvap.calendario import giorni_settimana
from cvap.solver import genera

from .conftest import LUNEDI_A, staff

GIORNI = giorni_settimana(LUNEDI_A)
CHIAVI = {"punteggio", "limite_inferiore", "gap_pct", "soluzioni", "tempo_migliore_s", "durata_s",
          "tempo_max", "workers"}


def test_qualita_presente_con_valori_coerenti():
    ris = genera(GIORNI, ["Acquasanta"], staff(4, 4), tempo_max=5)
    q = ris.qualita
    assert q is not None and CHIAVI <= set(q)
    assert q["soluzioni"] >= 1
    assert 0 <= q["tempo_migliore_s"] <= q["durata_s"]
    assert q["gap_pct"] >= 0
    assert q["limite_inferiore"] <= q["punteggio"]
    assert q["tempo_max"] == 5
    assert q["workers"] >= 1
    if ris.stato == "ottimo":
        assert q["gap_pct"] == 0


def test_qualita_assente_se_tutto_gia_coperto():
    ris = genera(GIORNI, [], staff(4, 4), tempo_max=5)
    assert ris.qualita is None


def test_qualita_assente_senza_dipendenti():
    ris = genera(GIORNI, ["Acquasanta"], [], tempo_max=5)
    assert ris.stato == "impossibile" and ris.qualita is None
