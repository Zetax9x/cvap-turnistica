"""Calcolo dei posti ancora da coprire, dati i posti già occupati (volontari o fissati a mano)."""
from datetime import date

from .modello import FASCE, RUOLI, Assegnazione, Unita


def unita_da_coprire(giorni: list[date], postazioni: list[str], occupate: list[Assegnazione]) -> list[Unita]:
    segmenti_occupati: dict[tuple, set[str]] = {}
    for a in occupate:
        segmenti_occupati.setdefault(a.chiave, set()).add(a.segmento)

    unita = []
    for d in giorni:
        for postazione in postazioni:
            for fascia in FASCE:
                for ruolo in RUOLI:
                    occupati = segmenti_occupati.get((d, postazione, fascia, ruolo), set())
                    if "intero" in occupati:
                        continue
                    if fascia == "notte" or not occupati:
                        unita.append(Unita(d, postazione, fascia, "intero", ruolo))
                        continue
                    # turno di giorno spezzato da un volontario: resta la metà libera
                    for segmento in ("mattina", "pomeriggio"):
                        if segmento not in occupati:
                            unita.append(Unita(d, postazione, fascia, segmento, ruolo))
    return unita
