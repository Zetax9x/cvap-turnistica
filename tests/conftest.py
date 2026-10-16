from datetime import date

import pytest

from cvap.modello import Assegnazione, Persona

LUNEDI_A = date(2026, 10, 19)  # settimana di riferimento A
LUNEDI_B = date(2026, 10, 26)


def staff(n_autisti: int, n_soccorritori: int, tipo: str = "dipendente", start_id: int = 1) -> list[Persona]:
    persone = []
    pid = start_id
    for _ in range(n_autisti):
        persone.append(Persona(pid, f"Autista {pid}", tipo, "autista"))
        pid += 1
    for _ in range(n_soccorritori):
        persone.append(Persona(pid, f"Soccorritore {pid}", tipo, "soccorritore"))
        pid += 1
    return persone


def ass(d: date, postazione: str, fascia: str, ruolo: str, persona_id: int,
        segmento: str = "intero", origine: str = "generato") -> Assegnazione:
    return Assegnazione(d, postazione, fascia, segmento, ruolo, persona_id, origine)


@pytest.fixture
def lunedi_a() -> date:
    return LUNEDI_A
