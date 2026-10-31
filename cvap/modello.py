"""Entità di dominio della turnistica.

Gli orari sono espressi in ore assolute (giorno ordinale * 24 + ora), così il
calcolo del riposo tra turni funziona anche a cavallo di giorni e settimane.
"""
from dataclasses import dataclass
from datetime import date

TIPI = ("dipendente", "volontario")
QUALIFICHE = ("autista", "soccorritore")
FASCE = ("giorno", "notte")
SEGMENTI = ("intero", "mattina", "pomeriggio", "standby", "standby_mattina", "standby_pomeriggio",
            "prog_mattina", "prog_pomeriggio")
RUOLI = ("autista", "soccorritore")
ORIGINI = ("volontario", "generato", "manuale")
PARTI_TURNO = ("mattina", "pomeriggio", "notte")  # le parti della giornata in cui un dipendente può essere indisponibile

ORE_RIPOSO_MIN = 11
TURNI_VIETABILI = ("mattina", "pomeriggio", "giorno", "notte")  # tipi di turno per i divieti

# Postazioni "a richiesta": i posti esistono solo dove l'utente indica il fabbisogno (solo settimane A).
STANDBY = "Standby"
PROGRAMMATI = "Programmati"
POSTAZIONI_A_RICHIESTA = (STANDBY, PROGRAMMATI)

# Assistenze ed Extra (tutte le settimane): richieste con nome e orario libero a ore intere, con N autisti e
# M soccorritori. Ogni richiesta ha il suo segmento "extra_<id>_<inizio>_<fine>" (ore dall'inizio del
# giorno; la fine può superare 24 se passa la mezzanotte), così orario e ore si ricavano dal segmento.
EXTRA = "Assistenze ed Extra"
DURATA_EXTRA_MAX = 24


def segmento_extra(richiesta_id: int, inizio: int, fine: int) -> str:
    return f"extra_{richiesta_id}_{inizio}_{fine}"


def leggi_extra(segmento: str) -> tuple[int, int, int] | None:
    """(id, inizio, fine) di un segmento di Assistenze ed Extra valido, altrimenti None."""
    parti = segmento.split("_")
    if len(parti) != 4 or parti[0] != "extra" or not all(x.isdigit() for x in parti[1:]):
        return None
    rid, inizio, fine = (int(x) for x in parti[1:])
    if not (0 <= inizio <= 23 and inizio < fine <= inizio + DURATA_EXTRA_MAX):
        return None
    return rid, inizio, fine


def is_extra(segmento: str) -> bool:
    return segmento.startswith("extra_")


def per_segmento(segmento: str) -> bool:
    """True se nel turno ci sono più posti uguali, contati per segmento (Programmati, Assistenze ed Extra)."""
    return segmento.startswith("prog_") or is_extra(segmento)


def fascia_extra(inizio: int) -> str:
    """Una richiesta è "di giorno" se inizia tra le 7 e le 19, altrimenti "di notte"."""
    return "giorno" if 7 <= inizio < 19 else "notte"


def _parti_extra(inizio: int, fine: int) -> frozenset[str]:
    def parte(h):
        h %= 24
        return "mattina" if 7 <= h < 14 else "pomeriggio" if 14 <= h < 20 else "notte"
    return frozenset(parte(h) for h in range(inizio, fine))

_ORARI = {
    ("giorno", "intero"): (8, 20),
    ("giorno", "mattina"): (8, 14),
    ("giorno", "pomeriggio"): (14, 20),
    ("notte", "intero"): (20, 32),  # 20:00 -> 08:00 del giorno dopo
    ("giorno", "standby"): (7, 19),
    ("giorno", "standby_mattina"): (7, 14),
    ("giorno", "standby_pomeriggio"): (14, 19),
    ("notte", "standby"): (19, 31),  # 19:00 -> 07:00
    ("giorno", "prog_mattina"): (7, 14),
    ("giorno", "prog_pomeriggio"): (14, 20),
}

# Turno intero di giorno -> le due metà in cui un volontario può spezzarlo (la notte non si spezza)
META = {
    "intero": ("mattina", "pomeriggio"),
    "standby": ("standby_mattina", "standby_pomeriggio"),
}
INTERO_DI = {meta: intero for intero, coppia in META.items() for meta in coppia}

_TURNI_AMMESSI = {
    STANDBY: {("giorno", "standby"), ("giorno", "standby_mattina"), ("giorno", "standby_pomeriggio"),
              ("notte", "standby")},
    PROGRAMMATI: {("giorno", "prog_mattina"), ("giorno", "prog_pomeriggio")},
}
_TURNI_NORMALI = {("giorno", "intero"), ("giorno", "mattina"), ("giorno", "pomeriggio"), ("notte", "intero")}


def parti_turno(fascia: str, segmento: str) -> frozenset[str]:
    """Parti della giornata (PARTI_TURNO) coperte da un turno."""
    if is_extra(segmento):
        _, inizio, fine = _dati_extra(fascia, segmento)
        return _parti_extra(inizio, fine)
    if fascia == "notte":
        return frozenset({"notte"})
    if segmento in ("mattina", "standby_mattina", "prog_mattina"):
        return frozenset({"mattina"})
    if segmento in ("pomeriggio", "standby_pomeriggio", "prog_pomeriggio"):
        return frozenset({"pomeriggio"})
    return frozenset({"mattina", "pomeriggio"})


def turni_ammessi(postazione: str) -> set[tuple[str, str]]:
    """Coppie (fascia, segmento) valide per la postazione."""
    return _TURNI_AMMESSI.get(postazione, _TURNI_NORMALI)


def turno_ammesso(postazione: str, fascia: str, segmento: str) -> bool:
    """True se (fascia, segmento) è un turno valido della postazione."""
    if postazione == EXTRA:
        dati = leggi_extra(segmento)
        return dati is not None and fascia == fascia_extra(dati[1])
    return (fascia, segmento) in turni_ammessi(postazione)


def segmento_intero(postazione: str, fascia: str) -> str:
    """Segmento del turno intero di una fascia (per i Programmati non esiste: ogni metà è a sé)."""
    return "standby" if postazione == STANDBY else "intero"


def si_sovrappongono(seg_a: str, seg_b: str) -> bool:
    """True se due segmenti dello stesso posto coprono in parte le stesse ore."""
    return seg_a == seg_b or INTERO_DI.get(seg_a) == seg_b or INTERO_DI.get(seg_b) == seg_a


def _dati_extra(fascia: str, segmento: str) -> tuple[int, int, int]:
    dati = leggi_extra(segmento)
    if dati is None or fascia != fascia_extra(dati[1]):
        raise ValueError(f"combinazione fascia/segmento non valida: {fascia}/{segmento}")
    return dati


def orario(d: date, fascia: str, segmento: str) -> tuple[int, int]:
    if is_extra(segmento):
        _, inizio, fine = _dati_extra(fascia, segmento)
    else:
        try:
            inizio, fine = _ORARI[(fascia, segmento)]
        except KeyError:
            raise ValueError(f"combinazione fascia/segmento non valida: {fascia}/{segmento}") from None
    base = d.toordinal() * 24
    return base + inizio, base + fine


def tipi_turno(fascia: str, segmento: str) -> frozenset[str]:
    """Tipi di turno (TURNI_VIETABILI) toccati da un turno: le sue parti, più "giorno" se è di giorno."""
    parti = parti_turno(fascia, segmento)
    return parti | {"giorno"} if fascia == "giorno" else parti


@dataclass(frozen=True)
class Divieto:
    """Turni che un dipendente non può fare: in una postazione e/o di un tipo (None = qualsiasi)."""
    postazione: str | None = None
    turno: str | None = None


@dataclass(frozen=True)
class Persona:
    id: int
    nome: str
    tipo: str
    qualifica: str
    autista_programmati: bool = False  # può guidare nei Programmati anche se soccorritore
    max_ore_settimana: int | None = None  # tetto alle ore lavorate (le ferie non contano); None = nessuno
    divieti: tuple[Divieto, ...] = ()

    def vieta(self, postazione: str, fascia: str, segmento: str) -> bool:
        """True se un divieto della persona copre quel turno."""
        tipi = tipi_turno(fascia, segmento)
        return any((d.postazione is None or d.postazione == postazione) and (d.turno is None or d.turno in tipi)
                   for d in self.divieti)

    @property
    def dipendente(self) -> bool:
        return self.tipo == "dipendente"

    def puo_ricoprire(self, ruolo: str, postazione: str | None = None) -> bool:
        # l'autista può fare anche il soccorritore, non viceversa
        if ruolo == "soccorritore" or self.qualifica == "autista":
            return True
        return postazione == PROGRAMMATI and self.autista_programmati


@dataclass(frozen=True)
class Postazione:
    nome: str
    solo_settimane_b: bool = False


@dataclass(frozen=True)
class Fabbisogno:
    """Quante persone servono in un turno di una postazione a richiesta."""
    data: date
    postazione: str
    fascia: str
    segmento: str
    ruolo: str
    quantita: int


@dataclass(frozen=True)
class Unita:
    """Un posto da coprire: un ruolo su una postazione in una fascia (o mezza fascia)."""
    data: date
    postazione: str
    fascia: str
    segmento: str
    ruolo: str

    def __post_init__(self):
        if self.ruolo not in RUOLI:
            raise ValueError(f"ruolo non valido: {self.ruolo}")
        # valida fascia/segmento e memorizza l'orario (usato moltissimo dal generatore)
        inizio, fine = orario(self.data, self.fascia, self.segmento)
        object.__setattr__(self, "_inizio", inizio)
        object.__setattr__(self, "_fine", fine)

    @property
    def inizio(self) -> int:
        return self._inizio

    @property
    def fine(self) -> int:
        return self._fine

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
