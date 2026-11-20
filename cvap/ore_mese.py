"""Differenza massima di ore nel mese, con limite progressivo.

Oltre al limite della settimana (`scarto_ore_max`), tra chi ha più ore contate e chi ne ha meno nel mese di
calendario, dal giorno 1 fino all'ultimo giorno generato, non devono esserci più di `scarto_ore_mese` ore.
Il limite è progressivo: si controlla a ogni settimana generata sul periodo dal 1° del mese fin lì, così a fine
mese vale per tutto il mese.

- Ore contate come nella settimana: ore lavorate (senza le sostituzioni, che sono extra) più 6 ore per ogni giorno
  di ferie o malattia. Un turno conta nel mese in cui comincia (la notte del 31 conta nel mese che finisce).
- Si controlla solo quando dal 1° del mese sono passati almeno `GIORNI_MINIMI` giorni: nei primi giorni di un mese
  che comincia a fine settimana (sabato e domenica) qualcuno deve per forza fare due turni e qualcun altro nessuno.
- Nel confronto entrano i dipendenti senza un massimo di ore personale, in servizio in tutte le settimane del
  periodo e mai in ferie o malattia per una settimana intera (come nel confronto della settimana, chi è assente
  tutta la settimana è fuori dal calcolo).
- Le ore delle settimane passate sono quelle dei turni generati, come per lo storico e l'equità: i cambi turno
  fatti dopo la conferma non contano.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from .modello import Assegnazione, Persona, ore_extra
from .vincoli import ORE_FERIE_GIORNO

GIORNI_MINIMI = 7
SCARTO_ORE_MESE = 12

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre")


@dataclass(frozen=True)
class ConfrontoMese:
    """Il confronto di un mese per la settimana da generare.

    `giorni`: i giorni della settimana che cadono nel mese; `precedenti`: ore contate di ogni partecipante dal 1°
    del mese al giorno prima della settimana; `crediti`: ore di ferie o malattia dei partecipanti nei `giorni`.
    Partecipano solo gli id in `precedenti`."""
    anno: int
    mese: int
    giorni: frozenset[date]
    precedenti: dict[int, int] = field(default_factory=dict)
    crediti: dict[int, int] = field(default_factory=dict)
    fino_al: date | None = None

    @property
    def nome(self) -> str:
        return f"{MESI[self.mese - 1]} {self.anno}"


def _settimana_assente(giorni: Iterable[date], ferie: set[date]) -> bool:
    giorni = list(giorni)
    return bool(giorni) and all(d in ferie for d in giorni)


def prepara(giorni: Sequence[date], passato: Iterable[Assegnazione], ferie: dict[int, set[date]],
            settimane_passate: Sequence[tuple[Sequence[date], Iterable[int]]],
            persone: Iterable[Persona]) -> list[ConfrontoMese]:
    """I confronti mensili per la settimana `giorni` (uno per mese toccato, se da controllare).

    `passato`: turni generati dal 1° del mese (o dei mesi) fino al giorno prima della settimana; `ferie`: giorni di
    ferie o malattia per id, almeno dal 1° del mese alla fine della settimana; `settimane_passate`: per ogni
    settimana precedente (giorni, id dei dipendenti in servizio); `persone`: i dipendenti attivi di questa settimana.
    """
    giorni = sorted(giorni)
    passato = [a for a in passato if not ore_extra(a)]
    persone = [p for p in persone if p.dipendente and p.max_ore_settimana is None]
    out = []
    for anno, mese in sorted({(d.year, d.month) for d in giorni}):
        nel_mese = [d for d in giorni if (d.year, d.month) == (anno, mese)]
        primo, ultimo = date(anno, mese, 1), nel_mese[-1]
        if (ultimo - primo).days + 1 < GIORNI_MINIMI:
            continue
        prima = giorni[0] - timedelta(days=1)  # i giorni del mese prima della settimana: [primo, prima]
        # le settimane senza elenco dei dipendenti (mai generate) non dicono chi era in servizio
        passate = [(list(g), set(ids)) for g, ids in settimane_passate
                   if g and ids and min(g) <= prima and max(g) >= primo]
        partecipanti = []
        for p in persone:
            assenze = ferie.get(p.id, set())
            if any(p.id not in ids for _, ids in passate):
                continue  # non era in servizio in una settimana del periodo
            if any(_settimana_assente(g, assenze) for g, _ in passate) or _settimana_assente(giorni, assenze):
                continue  # assente per una settimana intera: fuori dal calcolo, come nella settimana
            partecipanti.append(p.id)
        if len(partecipanti) < 2:
            continue
        precedenti = {}
        for pid in partecipanti:
            lavorate = sum(a.ore for a in passato if a.persona_id == pid and primo <= a.data <= prima)
            assenti = sum(1 for d in ferie.get(pid, ()) if primo <= d <= prima)
            precedenti[pid] = lavorate + ORE_FERIE_GIORNO * assenti
        crediti = {pid: ORE_FERIE_GIORNO * sum(1 for d in nel_mese if d in ferie.get(pid, ())) for pid in partecipanti}
        out.append(ConfrontoMese(anno, mese, frozenset(nel_mese), precedenti, crediti, ultimo))
    return out


def differenza(confronto: ConfrontoMese, assegnazioni: Iterable[Assegnazione],
               persone: dict[int, Persona] | None = None) -> dict | None:
    """Differenza tra chi ha più ore contate nel mese e chi ne ha meno, dopo i turni `assegnazioni` della settimana
    (fissati compresi). Come `vincoli.differenza_ore`, con il mese e i nomi se ci sono le `persone`."""
    ore = {pid: confronto.precedenti[pid] + confronto.crediti.get(pid, 0) for pid in confronto.precedenti}
    for a in assegnazioni:
        if a.persona_id in ore and a.data in confronto.giorni and not ore_extra(a):
            ore[a.persona_id] += a.ore
    if len(ore) < 2:
        return None
    pid_max = min(ore, key=lambda pid: (-ore[pid], pid))
    pid_min = min(ore, key=lambda pid: (ore[pid], pid))

    def voce(pid):
        return {"persona_id": pid, "nome": persone[pid].nome if persone and pid in persone else str(pid),
                "ore": ore[pid]}

    return {"mese": confronto.nome, "fino_al": confronto.fino_al.isoformat() if confronto.fino_al else None,
            "differenza": ore[pid_max] - ore[pid_min], "massimo": voce(pid_max), "minimo": voce(pid_min)}
