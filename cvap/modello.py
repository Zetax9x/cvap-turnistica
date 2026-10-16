"""Entità di dominio della turnistica.

Gli orari sono espressi in ore assolute (giorno ordinale * 24 + ora), così il
calcolo del riposo tra turni funziona anche a cavallo di giorni e settimane.
"""
from dataclasses import dataclass
from datetime import date

TIPI = ("dipendente", "volontario")
QUALIFICHE = ("autista", "soccorritore")
FASCE = ("giorno", "notte")
SEGMENTI = ("intero", "mattina", "pomeriggio")
RUOLI = ("autista", "soccorritore")
ORIGINI = ("volontario", "generato", "manuale")

ORE_RIPOSO_MIN = 11

_ORARI = {
    ("giorno", "intero"): (8, 20),
    ("giorno", "mattina"): (8, 14),
    ("giorno", "pomeriggio"): (14, 20),
    ("notte", "intero"): (20, 32),  # 20:00 -> 08:00 del giorno dopo
}


def orario(d: date, fascia: str, segmento: str) -> tuple[int, int]:
    try:
        inizio, fine = _ORARI[(fascia, segmento)]
    except KeyError:
        raise ValueError(f"combinazione fascia/segmento non valida: {fascia}/{segmento}") from None
    base = d.toordinal() * 24
    return base + inizio, base + fine


@dataclass(frozen=True)
class Persona:
    id: int
    nome: str
    tipo: str
    qualifica: str

    @property
    def dipendente(self) -> bool:
        return self.tipo == "dipendente"

    def puo_ricoprire(self, ruolo: str) -> bool:
        # l'autista può fare anche il soccorritore, non viceversa
        return ruolo == "soccorritore" or self.qualifica == "autista"


@dataclass(frozen=True)
class Postazione:
    nome: str
    solo_settimane_b: bool = False


@dataclass(frozen=True)
class Unita:
    """Un posto da coprire: un ruolo su una postazione in una fascia (o mezza fascia)."""
    data: date
    postazione: str
    fascia: str
    segmento: str
    ruolo: str

    @property
    def inizio(self) -> int:
        return orario(self.data, self.fascia, self.segmento)[0]

    @property
    def fine(self) -> int:
        return orario(self.data, self.fascia, self.segmento)[1]

    @property
    def ore(self) -> int:
        return self.fine - self.inizio

    @property
    def chiave(self) -> tuple:
        """Identifica il posto (postazione/fascia/ruolo) indipendentemente dal segmento."""
        return (self.data, self.postazione, self.fascia, self.ruolo)


@dataclass(frozen=True)
class Assegnazione(Unita):
    persona_id: int
    origine: str = "generato"

    @property
    def unita(self) -> Unita:
        return Unita(self.data, self.postazione, self.fascia, self.segmento, self.ruolo)


def in_conflitto(a: Unita, b: Unita) -> bool:
    """True se la stessa persona non può fare entrambi i turni (sovrapposti o con meno di 11h di riposo)."""
    if a.inizio <= b.inizio:
        pausa = b.inizio - a.fine
    else:
        pausa = a.inizio - b.fine
    return pausa < ORE_RIPOSO_MIN
