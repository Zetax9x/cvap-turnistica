"""Statistiche cumulative dei turni passati, usate dal generatore per l'equità nel tempo."""
from dataclasses import dataclass, field

from datetime import date

from .modello import EXTRA, PARTI_TURNO, POSTAZIONI_A_RICHIESTA, Assegnazione
from .vincoli import ASCOLI, ORE_FERIE_GIORNO

CATEGORIE_WEEKEND = ("sab_giorno", "sab_notte", "dom_giorno", "dom_notte")
# Standby, Programmati e Assistenze ed Extra: turni distribuiti a rotazione come i weekend
CATEGORIE_RICHIESTA = (*POSTAZIONI_A_RICHIESTA, EXTRA)
SEDI_ALTERNATE = ("Acquasanta", "Venarotta")  # ognuno, nel tempo, tanti turni nell'una quanti nell'altra


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
    richieste: dict[str, int] = field(default_factory=dict)  # turni Standby, Programmati, Assistenze ed Extra
    sedi: dict[str, int] = field(default_factory=dict)  # turni ad Acquasanta e a Venarotta (anche mezzi)
    ore_ferie: int = 0     # ORE_FERIE_GIORNO per giorno di ferie (nelle settimane che contano)
    ore_malattia: int = 0  # idem per malattia o infortunio
    ascoli: int = 0            # turni ad Ascoli (anche mezzo turno conta 1)
    ascoli_giorno: int = 0     # di cui di giorno
    ascoli_notte: int = 0      # di cui di notte
    settimane_ascoli: int = 0  # settimane con Ascoli in cui era presente: la base della quota attesa

    @property
    def ore_lavorate(self) -> int:
        return self.ore_giorno + self.ore_notte

    @property
    def ore_contate(self) -> int:
        """Ore lavorate più quelle accreditate per ferie e malattia, come nel confronto tra dipendenti."""
        return self.ore_lavorate + self.ore_ferie + self.ore_malattia

    def __post_init__(self):
        self.weekend = {k: self.weekend.get(k, 0) for k in CATEGORIE_WEEKEND}
        self.richieste = {k: self.richieste.get(k, 0) for k in CATEGORIE_RICHIESTA}
        self.sedi = {k: self.sedi.get(k, 0) for k in SEDI_ALTERNATE}


@dataclass
class SettimanaPassata:
    media_ore: float  # media ore dei dipendenti, ferie comprese
    dipendenti: list[int]
    assegnazioni: list[Assegnazione]
    giorni_ferie: dict[int, int] = field(default_factory=dict)  # id -> giorni di assenza (ferie o malattia)
    giorni_malattia: dict[int, int] = field(default_factory=dict)  # id -> quanti di quei giorni per malattia
    max_ore: dict[int, int] = field(default_factory=dict)  # id -> massimo ore a settimana


def dalla_prima_generata(settimane: list[SettimanaPassata]) -> list[SettimanaPassata]:
    """Le settimane dalla prima con turni generati in poi (in ordine di data).

    Quelle prima, inserite solo a mano per avviare il sistema, fanno da contesto ma non entrano nei conteggi."""
    for i, s in enumerate(settimane):
        if any(a.origine == "generato" for a in s.assegnazioni):
            return settimane[i:]
    return []


def indisponibilita_per_giorno(richieste: set[tuple[date, str]]) -> list[dict]:
    """Indisponibilità di un dipendente per giorno della settimana (0 = lunedì): `totale` = giorni con almeno
    una parte indisponibile, poi quante volte ogni parte (mattina, pomeriggio, notte)."""
    out = [{"totale": 0, **{parte: 0 for parte in PARTI_TURNO}} for _ in range(7)]
    for d in {d for d, _ in richieste}:
        out[d.weekday()]["totale"] += 1
    for d, parte in richieste:
        out[d.weekday()][parte] += 1
    return out


def solo_generate(settimane: list[SettimanaPassata]) -> list[SettimanaPassata]:
    """Le settimane con turni generati: le sole che contano nelle statistiche."""
    return [s for s in settimane if any(a.origine == "generato" for a in s.assegnazioni)]


def calcola_storico(settimane: list[SettimanaPassata]) -> dict[int, StoricoPersona]:
    storico: dict[int, StoricoPersona] = {}
    for s in dalla_prima_generata(settimane):
        # in ferie tutta la settimana: la settimana non conta per lui
        presenti = {pid for pid in s.dipendenti if s.giorni_ferie.get(pid, 0) < 7}
        ore = {pid: 0 for pid in presenti}
        # una settimana "con Ascoli" ha almeno un turno ad Ascoli: non dipende dalla data di riferimento A/B
        con_ascoli = any(a.postazione == ASCOLI for a in s.assegnazioni)
        for pid in presenti:
            st = storico.setdefault(pid, StoricoPersona())
            st.settimane += 1
            if con_ascoli:
                st.settimane_ascoli += 1
            malattia = s.giorni_malattia.get(pid, 0)
            st.ore_malattia += ORE_FERIE_GIORNO * malattia
            st.ore_ferie += ORE_FERIE_GIORNO * (s.giorni_ferie.get(pid, 0) - malattia)
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
            if a.postazione in st.sedi:
                st.sedi[a.postazione] += 1
            if a.postazione == ASCOLI:
                st.ascoli += 1
                if a.fascia == "giorno":
                    st.ascoli_giorno += 1
                else:
                    st.ascoli_notte += 1
        for pid, h in ore.items():
            # con ferie nella settimana le ore mancanti non si recuperano dopo
            if not s.giorni_ferie.get(pid):
                # chi ha un massimo sotto la media si misura dal massimo: non va "recuperato"
                rif = min(s.media_ore, s.max_ore[pid]) if pid in s.max_ore else s.media_ore
                storico[pid].saldo_ore += h - rif
    return storico
