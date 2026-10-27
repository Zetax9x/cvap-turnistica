"""Dipendenti liberi giorno per giorno: chi non ha turni di giorno, con avvisi per le notti.

Chi è in ferie o indisponibile non è tra i liberi ma in elenchi a parte, così si vede che non è chiamabile.
"""
from collections.abc import Iterable
from datetime import date, timedelta

from .modello import PARTI_TURNO, Assegnazione


def liberi_settimana(giorni: list[date], dipendenti: dict[int, str], assegnazioni: Iterable[Assegnazione],
                     ferie: dict[int, set[date]], indisponibili: dict[int, set[tuple[date, str]]]) -> list[dict]:
    """Per ogni giorno: `liberi` e `indisponibili` (con `avvisi` "smonto_notte" / "notte") e `ferie`.

    `assegnazioni` deve comprendere le notti del giorno prima del primo giorno (per lo smonto del lunedì).
    """
    di_giorno: set[tuple[int, date]] = set()
    notti: set[tuple[int, date]] = set()
    for a in assegnazioni:
        (notti if a.fascia == "notte" else di_giorno).add((a.persona_id, a.data))

    ordinati = sorted(dipendenti.items(), key=lambda kv: (kv[1].lower(), kv[0]))
    out = []
    for g in giorni:
        liberi, in_ferie, indisp = [], [], []
        for pid, nome in ordinati:
            if g in ferie.get(pid, ()):
                in_ferie.append({"persona_id": pid, "nome": nome})
                continue
            if (pid, g) in di_giorno:
                continue
            avvisi = [codice for codice, giorno in (("smonto_notte", g - timedelta(days=1)), ("notte", g))
                      if (pid, giorno) in notti]
            parti = {parte for d, parte in indisponibili.get(pid, ()) if d == g}
            if parti:
                indisp.append({"persona_id": pid, "nome": nome,
                               "parti": [p for p in PARTI_TURNO if p in parti], "avvisi": avvisi})
            else:
                liberi.append({"persona_id": pid, "nome": nome, "avvisi": avvisi})
        out.append({"data": g.isoformat(), "liberi": liberi, "ferie": in_ferie, "indisponibili": indisp})
    return out
