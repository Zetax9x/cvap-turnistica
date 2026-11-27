"""Regola leggera «non sempre lo stesso collega».

Un autista e un soccorritore lavorano insieme quando sono nello stesso equipaggio: stesso giorno, stessa postazione
con equipaggio (Acquasanta, Venarotta, Ascoli, Standby: non i Programmati), stessa fascia, uno come autista e
l'altro come soccorritore, con orari che si sovrappongono (un mezzo turno conta). Valgono anche i volontari.

Il generatore evita che la stessa coppia lavori insieme più di `MAX_STESSA_COPPIA` volte nelle ultime
`GIORNI_FINESTRA` giorni (le 3 settimane prima più quella da generare), quando ci sono alternative: è una
penalità leggera, sotto le regole su ore, notti e weekend. Le settimane passate si leggono dai turni effettivi
(cambi turno compresi): conta con chi si è lavorato davvero.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .modello import POSTAZIONI_EQUIPAGGIO, Assegnazione, ore_extra

MAX_STESSA_COPPIA = 2
GIORNI_FINESTRA = 28  # la settimana da generare più le 3 precedenti


def chiave(t) -> tuple | None:
    """Equipaggio di un turno (assegnazione o posto da coprire): None se non è un turno con equipaggio."""
    if t.postazione not in POSTAZIONI_EQUIPAGGIO:
        return None
    return (t.data, t.postazione, t.fascia)


def sovrapposti(a, b) -> bool:
    return a.inizio < b.fine and b.inizio < a.fine


def coppia(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def conta(assegnazioni: Iterable[Assegnazione]) -> Counter:
    """Quante volte ogni coppia (id più basso, id più alto) ha lavorato insieme."""
    per_equipaggio = defaultdict(list)
    for a in assegnazioni:
        if not ore_extra(a) and (k := chiave(a)):
            per_equipaggio[k].append(a)
    out = Counter()
    for turni in per_equipaggio.values():
        autisti = [a for a in turni if a.ruolo == "autista"]
        soccorritori = [a for a in turni if a.ruolo == "soccorritore"]
        viste = set()
        for a in autisti:
            for s in soccorritori:
                if a.persona_id != s.persona_id and sovrapposti(a, s):
                    viste.add(coppia(a.persona_id, s.persona_id))
        out.update(viste)  # nello stesso equipaggio la coppia conta una volta, anche con due mezzi turni
    return out
