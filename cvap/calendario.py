"""Calendario settimanale: le settimane partono sempre di lunedì e si alternano A/B.

Settimana A: solo postazioni fisse. Settimana B: anche quelle `solo_settimane_b` (Ascoli).
"""
from datetime import date, timedelta

from .modello import Postazione


def lunedi(d: date) -> date:
    return d - timedelta(days=d.weekday())


def tipo_settimana(inizio: date, riferimento_a: date) -> str:
    settimane = (lunedi(inizio) - lunedi(riferimento_a)).days // 7
    return "A" if settimane % 2 == 0 else "B"


def giorni_settimana(d: date) -> list[date]:
    inizio = lunedi(d)
    return [inizio + timedelta(days=i) for i in range(7)]


def postazioni_attive(tipo: str, postazioni: list[Postazione]) -> list[str]:
    return [p.nome for p in postazioni if tipo == "B" or not p.solo_settimane_b]
