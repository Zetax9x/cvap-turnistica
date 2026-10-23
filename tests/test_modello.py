import pytest

from cvap.modello import PARTI_TURNO, parti_turno


def test_parti_turno():
    assert PARTI_TURNO == ("mattina", "pomeriggio", "notte")


@pytest.mark.parametrize("fascia, segmento, attese", [
    ("notte", "intero", {"notte"}),
    ("notte", "standby", {"notte"}),
    ("giorno", "mattina", {"mattina"}),
    ("giorno", "standby_mattina", {"mattina"}),
    ("giorno", "prog_mattina", {"mattina"}),
    ("giorno", "pomeriggio", {"pomeriggio"}),
    ("giorno", "standby_pomeriggio", {"pomeriggio"}),
    ("giorno", "prog_pomeriggio", {"pomeriggio"}),
    ("giorno", "intero", {"mattina", "pomeriggio"}),
    ("giorno", "standby", {"mattina", "pomeriggio"}),
])
def test_parti_turno_per_fascia_e_segmento(fascia, segmento, attese):
    assert parti_turno(fascia, segmento) == frozenset(attese)
