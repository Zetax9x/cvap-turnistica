"""Statistiche cumulative dei turni passati, usate dal generatore per l'equità nel tempo."""
from dataclasses import dataclass, field

from .modello import POSTAZIONI_A_RICHIESTA, Assegnazione

CATEGORIE_WEEKEND = ("sab_giorno", "sab_notte", "dom_giorno", "dom_notte")
CATEGORIE_RICHIESTA = POSTAZIONI_A_RICHIESTA  # Standby e Programmati, distribuiti come i weekend


def categoria_weekend(a: Assegnazione) -> str | None:
    giorno = {5: "sab", 6: "dom"}.get(a.data.weekday())
    return f"{giorno}_{a.fascia}" if giorno else None


@dataclass
class StoricoPersona:
    settimane: int = 0
    saldo_ore: float = 0.0  # ore lavorate in più (+) o in meno (-) rispetto alle medie settimanali
    weekend: dict[str, int] = field(default_factory=dict)
    ore_giorno: int = 0
    ore_notte: int = 0
    richieste: dict[str, int] = field(default_factory=dict)  # turni Standby e Programmati

    def __post_init__(self):
        self.weekend = {k: self.weekend.get(k, 0) for k in CATEGORIE_WEEKEND}
        self.richieste = {k: self.richieste.get(k, 0) for k in CATEGORIE_RICHIESTA}


@dataclass
class SettimanaPassata:
    media_ore: float  # media ore dei dipendenti, ferie comprese
    dipendenti: list[int]
    assegnazioni: list[Assegnazione]
    giorni_ferie: dict[int, int] = field(default_factory=dict)  # id -> giorni di ferie nella settimana


def calcola_storico(settimane: list[SettimanaPassata]) -> dict[int, StoricoPersona]:
    storico: dict[int, StoricoPersona] = {}
    for s in settimane:
        # in ferie tutta la settimana: la settimana non conta per lui
        presenti = {pid for pid in s.dipendenti if s.giorni_ferie.get(pid, 0) < 7}
        ore = {pid: 0 for pid in presenti}
        for pid in presenti:
            storico.setdefault(pid, StoricoPersona()).settimane += 1
        for a in s.assegnazioni:
            if a.persona_id not in presenti:
                continue
            st = storico[a.persona_id]
            ore[a.persona_id] += a.ore
            if a.fascia == "giorno":
                st.ore_giorno += a.ore
            else:
                st.ore_notte += a.ore
            cat = categoria_weekend(a)
            if cat:
                st.weekend[cat] += 1
            if a.postazione in st.richieste:
                st.richieste[a.postazione] += 1
        for pid, h in ore.items():
            # con ferie nella settimana le ore mancanti non si recuperano dopo
            if not s.giorni_ferie.get(pid):
                storico[pid].saldo_ore += h - s.media_ore
    return storico
