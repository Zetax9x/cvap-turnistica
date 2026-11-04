"""Generati per la distribuzione; impegni effettivi per i vincoli."""
from datetime import timedelta

import pytest

from cvap.calendario import giorni_settimana
from cvap.modello import Fabbisogno, PROGRAMMATI
from cvap.solver import genera

from .conftest import LUNEDI_A, ass, staff


GIORNI = giorni_settimana(LUNEDI_A)
RICHIESTA = Fabbisogno(LUNEDI_A, PROGRAMMATI, "giorno", "prog_mattina", "autista", 1)


def _genera(persone, effettivi, generati):
    return genera(GIORNI, [], persone, contesto=effettivi, contesto_generati=generati,
                  fabbisogno=[RICHIESTA], workers=1, tempo_max=2)


@pytest.mark.parametrize("ricevuto", [False, True])
def test_riposo_dopo_turno_ricevuto_o_cancellato(ricevuto):
    notte = ass(LUNEDI_A - timedelta(days=1), "Acquasanta", "notte", "autista", 1)
    r = _genera(staff(1, 0), [notte] if ricevuto else [], [] if ricevuto else [notte])
    assert len(r.assegnazioni) == (0 if ricevuto else 1)
    assert len(r.scoperti) == (1 if ricevuto else 0)


@pytest.mark.parametrize("ricevuti", [False, True])
def test_limite_consecutivi_conta_i_turni_effettivi(ricevuti):
    precedenti = [ass(LUNEDI_A - timedelta(days=i), "Acquasanta", "giorno", "autista", 1)
                  for i in (1, 2, 3)]
    r = _genera(staff(1, 0), precedenti if ricevuti else [], [] if ricevuti else precedenti)
    assert len(r.assegnazioni) == (0 if ricevuti else 1)


def test_penalita_tre_turni_di_fila_segue_il_programma_generato():
    generati = [ass(LUNEDI_A - timedelta(days=i), "Acquasanta", "giorno", "autista", 1)
                for i in (1, 2)]
    effettivi = [ass(a.data, a.postazione, a.fascia, a.ruolo, 2) for a in generati]
    r = _genera(staff(2, 0), effettivi, generati)
    assert not r.scoperti
    assert [a.persona_id for a in r.assegnazioni] == [2]
