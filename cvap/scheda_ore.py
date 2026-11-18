"""Scheda ore mensile del dipendente: calcolo puro (nessun database, nessuna API).

Dai turni effettivi di una persona in un mese si ottiene una riga per giorno nelle colonne del modello
`docs/TABELLA_RIEPILOGO_ORE (1).xlsx`; le correzioni del dipendente sostituiscono i singoli giorni e i totali
seguono le formule del modello.
"""
import calendar
import math
import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from .modello import EXTRA, PROGRAMMATI, STANDBY, Assegnazione

COLONNE = ("ascoli", "acquasanta", "venarotta", "programmati", "assistenze", "viaggi_ast", "viaggi")
ETICHETTE = {"ascoli": "Ascoli", "acquasanta": "Acquasanta", "venarotta": "Venarotta", "programmati": "Programmati",
             "assistenze": "Assistenze", "viaggi_ast": "Viaggi Ast", "viaggi": "Viaggi"}
# le colonne del modello: Ascoli, Acquasanta e Venarotta sono le postazioni; le altre sono i secondari
COLONNE_POSTAZIONI = ("ascoli", "acquasanta", "venarotta")
COLONNE_SECONDARI = ("programmati", "assistenze", "viaggi_ast", "viaggi")
_POSTAZIONE_COLONNA = {"Ascoli": "ascoli", "Acquasanta": "acquasanta", "Venarotta": "venarotta",
                       PROGRAMMATI: "programmati", STANDBY: "programmati", EXTRA: "assistenze"}

MAX_NOTE_GIORNO = 200
MAX_NOTE_FINALI = 1000
MAX_CAUSALE = 100
MESI_INDIETRO = 12

_ORARIO = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")
_ERRORE_ORARIO = "Orario non valido: scrivi ad esempio 8 oppure 8:30 (da 0 a 24)"


# --- orari ---------------------------------------------------------------------------------

def parse_orario(testo) -> float:
    """Ore decimali (0–24) da `8`, `8:30`, `20` o da un numero; ValueError se non valido."""
    if isinstance(testo, bool) or testo is None:
        raise ValueError(_ERRORE_ORARIO)
    if isinstance(testo, (int, float)):
        if not 0 <= testo <= 24:
            raise ValueError(_ERRORE_ORARIO)
        return float(testo)
    trovato = _ORARIO.match(str(testo).strip())
    if not trovato:
        raise ValueError(_ERRORE_ORARIO)
    ore, minuti = int(trovato.group(1)), int(trovato.group(2) or 0)
    if ore > 24 or minuti > 59 or (ore == 24 and minuti):
        raise ValueError(_ERRORE_ORARIO)
    return ore + minuti / 60


def formatta_orario(ore: float) -> str:
    """`8.5` → `"8:30"`, `20.0` → `"20"`."""
    intere, minuti = int(ore), round((ore - int(ore)) * 60)
    if minuti == 60:
        intere, minuti = intere + 1, 0
    return f"{intere}" if not minuti else f"{intere}:{minuti:02d}"


def ore_intervallo(inizio: float, fine: float) -> float:
    """Ore tra due orari, anche a cavallo della mezzanotte; inizio uguale a fine = 24 ore (come il modello)."""
    inizio, fine = inizio % 24, fine % 24
    return 24.0 if inizio == fine else (fine - inizio) % 24


def _arrotonda_ora(ore: float) -> int:
    """Come il modello (`-INT(0.5-ROUND(x,4))`): all'ora intera, la mezz'ora esatta scende."""
    return math.ceil(round(ore, 4) - 0.5)


# --- mesi ----------------------------------------------------------------------------------

def _anno_mese(mese: str) -> tuple[int, int]:
    anno, numero = mese.split("-")
    return int(anno), int(numero)


def giorni_del_mese(mese: str) -> int:
    anno, numero = _anno_mese(mese)
    return calendar.monthrange(anno, numero)[1]


def mesi_apribili(oggi: date) -> list[str]:
    """Il mese in corso e i 12 precedenti, dal più recente."""
    mesi = []
    for indietro in range(MESI_INDIETRO + 1):
        indice = oggi.year * 12 + oggi.month - 1 - indietro
        mesi.append(f"{indice // 12:04d}-{indice % 12 + 1:02d}")
    return mesi


# --- dai turni alle righe -----------------------------------------------------------------

def _giorno_vuoto(giorno: int) -> dict:
    return {"giorno": giorno, "ferie": 0, "colonne": {c: None for c in COLONNE}, "note": "",
            "disponibilita": None, "da_rivedere": False, "corretto": False, "turni_cambiati": False}


def _nota_turno(a: Assegnazione, nomi_extra: dict[str, str]) -> str:
    if a.postazione == STANDBY:
        return "Standby"
    if a.postazione == EXTRA:
        return nomi_extra.get(a.segmento) or EXTRA
    return ""


def _unisci_contigui(intervalli: list[tuple[float, float]]) -> list[list[float]]:
    """Intervalli (inizio, fine) ordinati: quelli che si toccano (fine = inizio del successivo) diventano uno."""
    uniti: list[list[float]] = []
    for inizio, fine in sorted(intervalli):
        if uniti and uniti[-1][1] == inizio:
            uniti[-1][1] = fine
        else:
            uniti.append([inizio, fine])
    return uniti


def turni_in_righe(mese: str, turni: Iterable[Assegnazione], assenze: dict[date, str],
                   nomi_extra: dict[str, str]) -> dict[int, dict]:
    """Una riga per ogni giorno del mese. Ogni turno va nel giorno in cui inizia."""
    anno, numero = _anno_mese(mese)
    righe = {g: _giorno_vuoto(g) for g in range(1, giorni_del_mese(mese) + 1)}
    note: dict[int, list[str]] = defaultdict(list)
    gruppi: dict[tuple[int, str], list[tuple[float, float]]] = defaultdict(list)
    for a in turni:
        colonna = _POSTAZIONE_COLONNA.get(a.postazione)
        if colonna is None or (a.data.year, a.data.month) != (anno, numero):
            continue
        gruppi[a.data.day, colonna].append((float(a.inizio), float(a.fine)))
        if nota := _nota_turno(a, nomi_extra):
            note[a.data.day].append(nota)
    for (giorno, colonna), intervalli in gruppi.items():
        primo, *altri = _unisci_contigui(intervalli)
        righe[giorno]["colonne"][colonna] = [primo[0] % 24, primo[1] % 24]
        for inizio, fine in altri:
            righe[giorno]["da_rivedere"] = True
            note[giorno].append(f"{ETICHETTE[colonna]} {formatta_orario(inizio % 24)}–{formatta_orario(fine % 24)}"
                                " da inserire a mano")
    for giorno_assenza, motivo in assenze.items():
        if (giorno_assenza.year, giorno_assenza.month) != (anno, numero):
            continue
        if motivo == "malattia":
            note[giorno_assenza.day].insert(0, "Malattia")
        else:
            righe[giorno_assenza.day]["ferie"] = 1
    for giorno, voci in note.items():
        righe[giorno]["note"] = "; ".join(dict.fromkeys(voci))
    return righe


# --- correzioni ---------------------------------------------------------------------------

def _intervallo(valore, colonna: str) -> list[float] | None:
    if valore is None:
        return None
    if not isinstance(valore, (list, tuple)) or len(valore) != 2:
        raise ValueError(f"{ETICHETTE.get(colonna, colonna)}: servono l'orario di inizio e quello di fine")
    vuoti = [v is None or str(v).strip() == "" for v in valore]
    if all(vuoti):
        return None
    if any(vuoti):
        raise ValueError(f"{ETICHETTE.get(colonna, colonna)}: manca l'orario di inizio o quello di fine")
    return [parse_orario(valore[0]), parse_orario(valore[1])]


def _disponibilita(valore) -> dict | None:
    if not valore:
        return None
    if not isinstance(valore, dict):
        raise ValueError("Disponibilità aggiuntive non valide")
    causale = str(valore.get("causale") or "").strip()
    if len(causale) > MAX_CAUSALE:
        raise ValueError(f"La causale può avere al massimo {MAX_CAUSALE} caratteri")
    orari = _intervallo([valore.get("inizio"), valore.get("fine")], "disponibilità aggiuntive")
    if orari is None:
        return None
    return {"inizio": orari[0], "fine": orari[1], "causale": causale}


def valida_correzione(dati: dict, mese: str, giorno: int) -> dict:
    """Correzione di un giorno, normalizzata (orari in ore decimali, tutte le colonne presenti)."""
    if not 1 <= giorno <= giorni_del_mese(mese):
        raise ValueError("Questo giorno non esiste nel mese")
    ferie = dati.get("ferie", 0)
    if ferie not in (0, 1) or isinstance(ferie, str):
        raise ValueError("Ferie può essere solo 0 o 1")
    note = dati.get("note") or ""
    if not isinstance(note, str) or len(note.strip()) > MAX_NOTE_GIORNO:
        raise ValueError(f"Le note del giorno possono avere al massimo {MAX_NOTE_GIORNO} caratteri")
    colonne = dati.get("colonne") or {}
    sconosciute = set(colonne) - set(COLONNE)
    if sconosciute:
        raise ValueError(f"Colonna sconosciuta: {', '.join(sorted(sconosciute))}")
    return {"ferie": int(ferie), "colonne": {c: _intervallo(colonne.get(c), c) for c in COLONNE},
            "note": note.strip(), "disponibilita": _disponibilita(dati.get("disponibilita"))}


def applica_correzioni(calcolate: dict[int, dict], correzioni: dict[int, dict]) -> list[dict]:
    """I giorni del mese, quelli corretti dal dipendente al posto di quelli calcolati.

    `correzioni[g]["_base"]` è il giorno calcolato quando la correzione è stata salvata: se oggi il calcolato è
    diverso (cambio turno, malattia…) il giorno è segnato `turni_cambiati`.
    """
    righe = []
    for giorno in sorted(calcolate):
        calcolato, corretto = calcolate[giorno], correzioni.get(giorno)
        if corretto is None:
            righe.append({**calcolato, "colonne": dict(calcolato["colonne"])})
            continue
        base = corretto.get("_base")
        righe.append({"giorno": giorno, "ferie": corretto["ferie"],
                      "colonne": {c: corretto["colonne"].get(c) for c in COLONNE}, "note": corretto["note"],
                      "disponibilita": corretto["disponibilita"], "da_rivedere": False, "corretto": True,
                      "turni_cambiati": base is not None and base != calcolato})
    return righe


# --- totali -------------------------------------------------------------------------------

def _ore_coppie(coppie: Iterable[list[float] | None]) -> float:
    """Ore di una colonna: somma degli intervalli completi, arrotondata a 2 decimali (come il modello)."""
    return round(sum(ore_intervallo(c[0], c[1]) for c in coppie if c and None not in c), 2)


def ore_colonna(giorni: list[dict], colonna: str) -> float:
    """Ore di una colonna nel mese (come la riga 46 del modello: 2 decimali, prima dell'arrotondamento all'ora)."""
    return _ore_coppie(g["colonne"][colonna] for g in giorni)


def ore_disponibilita_grezze(giorni: list[dict]) -> float:
    """Ore delle disponibilità aggiuntive nel mese, 2 decimali (cella S46 del modello)."""
    return _ore_coppie([g["disponibilita"]["inizio"], g["disponibilita"]["fine"]] for g in giorni if g["disponibilita"])


def totali(giorni: list[dict]) -> dict:
    """Totali come le formule del modello: postazioni, secondari, totale del mese, disponibilità e giorni di ferie."""
    def ore(colonne):
        return round(sum(ore_colonna(giorni, c) for c in colonne), 4)

    postazioni, secondari = _arrotonda_ora(ore(COLONNE_POSTAZIONI)), _arrotonda_ora(ore(COLONNE_SECONDARI))
    return {"giorni_ferie": sum(g["ferie"] for g in giorni), "ore_postazioni": postazioni,
            "ore_secondari": secondari, "totale_mese": postazioni + secondari,
            "ore_disponibilita": _arrotonda_ora(ore_disponibilita_grezze(giorni))}
