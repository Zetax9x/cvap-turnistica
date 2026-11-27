"""Equità nel mese, con limite progressivo: ore, notti e weekend.

Oltre ai limiti della settimana e al pareggio nel tempo, nel mese di calendario, dal giorno 1 fino all'ultimo giorno
generato, tra chi è più avanti e chi è più indietro non ci devono essere più di:
- `ore`: 12 ore (impostazione «scarto_ore_mese»);
- `notti`: 2 notti, cioè 24 ore di notte (impostazione «scarto_notti_mese», in notti);
- `weekend`: 2 turni di weekend, sabato o domenica, giorno o notte (impostazione «scarto_weekend_mese»).
Il limite è progressivo: si controlla a ogni settimana generata sul periodo dal 1° del mese fin lì, così a fine
mese vale per tutto il mese. Si comincia quando dal 1° sono passati almeno `GIORNI_MINIMI` giorni.

Come si misura: giorno per giorno ognuno ha uno scarto dalla media dei colleghi presenti quel giorno; lo scarto del
mese è la somma degli scarti dei giorni. Il giorno di ferie o malattia, per chi è assente, è neutro: non crea né
debiti né crediti (il resto della settimana conta). Lo stesso le settimane in cui non era in servizio e i giorni
delle settimane non confermate (per tutti). Senza assenze è lo stesso che confrontare i totali del mese.

- Un turno conta nel mese in cui comincia (la notte del 31 conta nel mese che finisce); le sostituzioni (extra) non
  contano; le notti si misurano in ore (un mezzo turno di notte vale 6 ore), i weekend in turni.
- Nel confronto entrano i dipendenti senza un massimo di ore personale.
- Le settimane passate si leggono dai turni generati, come per lo storico e l'equità: i cambi turno fatti dopo la
  conferma non contano.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from .calendario import lunedi
from .modello import Assegnazione, Persona, ore_extra
from .storico import categoria_weekend

GIORNI_MINIMI = 7
MISURE = ("ore", "notti", "weekend")
LIMITI_PREDEFINITI = {"ore": 12, "notti": 24, "weekend": 2}  # notti in ore (2 notti)
NOMI_MISURE = {"ore": "ore", "notti": "ore di notte", "weekend": "turni di weekend"}

MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre")


def valore(misura: str, turno) -> int:
    """Quanto conta un turno (assegnazione o posto da coprire) per la misura."""
    if misura == "ore":
        return turno.ore
    if misura == "notti":
        return turno.ore if turno.fascia == "notte" else 0
    return 1 if categoria_weekend(turno) else 0


@dataclass(frozen=True)
class ConfrontoMese:
    """Il confronto di un mese per la settimana da generare.

    `giorni`: i giorni della settimana che cadono nel mese; `partecipanti`: chi entra nel confronto; `presenti[giorno]`:
    chi conta quel giorno (non è in ferie o malattia); `precedenti[misura][id]`: scarto accumulato dal 1° del mese al
    giorno prima della settimana."""
    anno: int
    mese: int
    giorni: frozenset[date]
    partecipanti: tuple[int, ...] = ()
    presenti: dict[date, frozenset[int]] = field(default_factory=dict)
    precedenti: dict[str, dict[int, float]] = field(default_factory=dict)
    fino_al: date | None = None

    @property
    def nome(self) -> str:
        return f"{MESI[self.mese - 1]} {self.anno}"


def prepara(giorni: Sequence[date], passato: Iterable[Assegnazione], ferie: dict[int, set[date]],
            settimane_passate: Sequence[tuple[Sequence[date], Iterable[int]]],
            persone: Iterable[Persona]) -> list[ConfrontoMese]:
    """I confronti mensili per la settimana `giorni` (uno per mese toccato, se da controllare).

    `passato`: turni generati dal 1° del mese (o dei mesi) fino al giorno prima della settimana; `ferie`: giorni di
    ferie o malattia per id, almeno dal 1° del mese alla fine della settimana; `settimane_passate`: per le settimane
    precedenti (giorni, id dei dipendenti in servizio: un elenco vuoto vuol dire «non noto», tutti in servizio);
    `persone`: i dipendenti attivi di questa settimana.
    """
    giorni = sorted(giorni)
    passato = [a for a in passato if not ore_extra(a)]
    partecipanti = tuple(p.id for p in persone if p.dipendente and p.max_ore_settimana is None)
    in_servizio = {lunedi(min(g)): set(ids) for g, ids in settimane_passate if g and ids}
    out = []
    for anno, mese in sorted({(d.year, d.month) for d in giorni}):
        nel_mese = [d for d in giorni if (d.year, d.month) == (anno, mese)]
        primo, ultimo = date(anno, mese, 1), nel_mese[-1]
        if (ultimo - primo).days + 1 < GIORNI_MINIMI or len(partecipanti) < 2:
            continue
        prima = giorni[0] - timedelta(days=1)
        precedenti = {m: {pid: 0.0 for pid in partecipanti} for m in MISURE}
        per_giorno = defaultdict(list)
        for a in passato:
            if primo <= a.data <= prima:
                per_giorno[a.data].append(a)
        d = primo
        while d <= prima:
            ids = in_servizio.get(lunedi(d))
            presenti = [pid for pid in partecipanti if (ids is None or pid in ids) and d not in ferie.get(pid, ())]
            if presenti:
                for m in MISURE:
                    x = {pid: 0 for pid in presenti}
                    for a in per_giorno.get(d, ()):
                        if a.persona_id in x:
                            x[a.persona_id] += valore(m, a)
                    media = sum(x.values()) / len(x)
                    for pid in presenti:
                        precedenti[m][pid] += x[pid] - media
            d += timedelta(days=1)
        presenti = {g: frozenset(pid for pid in partecipanti if g not in ferie.get(pid, ())) for g in nel_mese}
        out.append(ConfrontoMese(anno, mese, frozenset(nel_mese), partecipanti, presenti, precedenti, ultimo))
    return out


def scarti(confronto: ConfrontoMese, assegnazioni: Iterable[Assegnazione], misura: str) -> dict[int, float]:
    """Lo scarto del mese di ogni partecipante dopo i turni `assegnazioni` della settimana (fissati compresi)."""
    s = {pid: confronto.precedenti.get(misura, {}).get(pid, 0.0) for pid in confronto.partecipanti}
    assegnazioni = [a for a in assegnazioni if not ore_extra(a)]
    for g in confronto.giorni:
        presenti = confronto.presenti.get(g, frozenset())
        if not presenti:
            continue
        x = {pid: 0 for pid in presenti}
        for a in assegnazioni:
            if a.persona_id in x and a.data == g:
                x[a.persona_id] += valore(misura, a)
        media = sum(x.values()) / len(x)
        for pid in presenti:
            s[pid] += x[pid] - media
    return s


def differenza(confronto: ConfrontoMese, assegnazioni: Iterable[Assegnazione], misura: str = "ore",
               persone: dict[int, Persona] | None = None) -> dict | None:
    """Distanza tra chi è più avanti e chi è più indietro nel mese, per la misura, dopo i turni della settimana."""
    s = scarti(confronto, assegnazioni, misura)
    if len(s) < 2:
        return None
    pid_max = min(s, key=lambda pid: (-s[pid], pid))
    pid_min = min(s, key=lambda pid: (s[pid], pid))

    def voce(pid):
        return {"persona_id": pid, "nome": persone[pid].nome if persone and pid in persone else str(pid),
                "scarto": round(s[pid], 1)}

    return {"mese": confronto.nome, "fino_al": confronto.fino_al.isoformat() if confronto.fino_al else None,
            "misura": misura, "unita": NOMI_MISURE[misura], "differenza": round(s[pid_max] - s[pid_min], 1),
            "massimo": voce(pid_max), "minimo": voce(pid_min)}
