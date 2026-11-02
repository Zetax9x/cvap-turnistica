"""Storico delle festività degli anni passati: lettura del file CSV e anteprima (docs/PIANO-rotazioni.md, sez. 3.2).

Modulo puro, senza database. Le festività e le persone arrivano come dict (come da GET /api/festivita e
GET /api/persone). Lo storico serve alla rotazione delle festività (fase 6): non tocca ore, settimane e statistiche.
"""
import csv
import io
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta

from .db import _chiave_nome
from .festivita import ANNO_MAX_PASQUA, data_nell_anno, occorrenze
from .modello import FASCE

ANNO_MIN = 2000
RIGHE_MAX = 5000
TESTO_MAX = 1_000_000
PERSONE_PER_CELLA_MAX = 20
NOME_MAX = 100

_FASCE = {"giorno": FASCE[0], "g": FASCE[0], "diurno": FASCE[0], "notte": FASCE[1], "n": FASCE[1],
          "notturno": FASCE[1]}
_INTESTAZIONI = {"anno": "anno", "festivita": "festivita", "turno": "turno", "fascia": "turno", "nome": "nome",
                 "data": "data"}
_ALIAS_FESTIVITA = {"pasquetta": "lunedi dell'angelo"}
_CONTROLLO = re.compile(r"[\x00-\x1f\x7f]")  # come il tipo Nome delle API
_FORMATI_DATA = ("%d/%m/%Y", "%Y-%m-%d")


def _semplice(testo: str) -> str:
    """Minuscolo, senza accenti e senza spazi doppi: per confrontare intestazioni e nomi di festività."""
    senza_accenti = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return " ".join(senza_accenti.split()).casefold()


def parse_data(s: str) -> date | None:
    s = (s or "").strip()
    for formato in _FORMATI_DATA:
        try:
            return datetime.strptime(s, formato).date()
        except ValueError:
            continue
    return None


def parse_fascia(s: str) -> str | None:
    return _FASCE.get(_semplice(s or ""))


def limite_storico(prima_generata: date | None, oggi: date) -> date:
    """Dal limite in poi le festività le conta già il programma (lunedì della prima settimana generata)."""
    if prima_generata is not None:
        return prima_generata - timedelta(days=prima_generata.weekday())
    return oggi + timedelta(days=1)


def celle_troppo_piene(turni: list[tuple]) -> list[tuple[int, str]]:
    """(festivita_id, fascia) con più di PERSONE_PER_CELLA_MAX persone; turni: (festivita_id, fascia, persona)."""
    conteggio = Counter((f, fascia) for f, fascia, _ in turni)
    return [cella for cella, n in conteggio.items() if n > PERSONE_PER_CELLA_MAX]


def anno_max(limite: date) -> int:
    return (limite - timedelta(days=1)).year


def _righe_numerate(testo: str) -> list[tuple[int, list[str]]]:
    """(numero di riga nel file, celle) delle righe non vuote; separatore ";" (Excel italiano) o ","."""
    if len(testo) > TESTO_MAX:
        raise ValueError(f"File troppo grande: al massimo {TESTO_MAX // 1000} kB")
    testo = testo.lstrip("﻿")
    prima = next((r for r in testo.splitlines() if r.strip()), "")
    separatore = ";" if prima.count(";") >= prima.count(",") else ","
    lettore = csv.reader(io.StringIO(testo), delimiter=separatore)
    righe, inizio = [], 1
    try:
        for r in lettore:  # numero della riga in cui inizia il record (le celle tra virgolette possono andare a capo)
            if any(celle := [c.strip() for c in r]):
                righe.append((inizio, celle))
            inizio = lettore.line_num + 1
    except csv.Error as e:  # es. una cella oltre il limite del modulo csv
        raise ValueError(f"File CSV non valido alla riga {inizio}") from e
    if len(righe) > RIGHE_MAX + 1:
        raise ValueError(f"Troppe righe: al massimo {RIGHE_MAX}")
    return righe


def leggi_csv(testo: str) -> list[list[str]]:
    """Righe non vuote del CSV, con le celle ripulite dagli spazi."""
    return [celle for _, celle in _righe_numerate(testo)]


def _colonne(intestazione: list[str]) -> dict[str, int]:
    colonne = {}
    for i, titolo in enumerate(intestazione):
        chiave = _INTESTAZIONI.get(_semplice(titolo))
        if chiave and chiave not in colonne:
            colonne[chiave] = i
    if "nome" not in colonne or "turno" not in colonne or not (
            "data" in colonne or ("anno" in colonne and "festivita" in colonne)):
        raise ValueError("Intestazione non valida: servono le colonne Nome, Turno e Data (oppure Anno e Festività)")
    return colonne


def _festivita_per_nome(festivita: list[dict], testo: str) -> dict | None:
    cercato = _semplice(testo)
    cercato = _ALIAS_FESTIVITA.get(cercato, cercato)
    return next((f for f in festivita if _semplice(f["nome"]) == cercato), None)


def _festivita_del_giorno(festivita: list[dict], d: date) -> tuple[dict | None, str | None]:
    """La festività che cade il giorno `d` (anche non attiva); con più festività si preferisce l'unica attiva."""
    trovate = [f for _, f in occorrenze(festivita, d, d)]
    if len(trovate) > 1:
        attive = [f for f in trovate if f.get("attiva")]
        if len(attive) != 1:
            nomi = ", ".join(f["nome"] for f in trovate)
            return None, f"più festività il {d:%d/%m/%Y} ({nomi}): usa le colonne Anno e Festività"
        trovate = attive
    return (trovate[0] if trovate else None), None


def _cella(riga: list[str], colonne: dict[str, int], chiave: str) -> str:
    i = colonne.get(chiave)
    return riga[i].strip() if i is not None and i < len(riga) else ""


def _da_data(testo: str, festivita: list[dict]) -> tuple[dict | None, date | None, dict | None]:
    d = parse_data(testo)
    if d is None:
        return None, None, {"errore": f"data non valida: {testo!r} (usa gg/mm/aaaa)"}
    if not ANNO_MIN <= d.year <= ANNO_MAX_PASQUA:
        return None, None, {"errore": f"anno non valido: {d.year} (dal {ANNO_MIN})"}
    f, errore = _festivita_del_giorno(festivita, d)
    if errore:
        return None, None, {"errore": errore}
    if f is None:
        return None, None, {"motivo": "data_non_festiva", "dettaglio": f"{d:%d/%m/%Y}"}
    return f, d, None


def _da_anno_e_nome(testo_anno: str, testo_fest: str, festivita: list[dict]):
    if not testo_anno.isdigit():
        return None, None, {"errore": f"anno non valido: {testo_anno!r}"}
    anno = int(testo_anno)
    if not ANNO_MIN <= anno <= ANNO_MAX_PASQUA:
        return None, None, {"errore": f"anno non valido: {anno} (dal {ANNO_MIN})"}
    f = _festivita_per_nome(festivita, testo_fest)
    if f is None:
        return None, None, {"motivo": "festivita_non_nel_calendario", "dettaglio": testo_fest}
    d = data_nell_anno(f, anno)
    if d is None:
        return None, None, {"motivo": "non_cade_nell_anno", "dettaglio": f"{f['nome']} {anno}"}
    return f, d, None


def _festivita_e_data(riga, colonne, festivita) -> tuple[dict | None, date | None, dict | None]:
    """(festività, data in cui cade, problema) dove problema è {"errore": msg} oppure {"motivo", "dettaglio"}."""
    if "data" in colonne and _cella(riga, colonne, "data"):
        return _da_data(_cella(riga, colonne, "data"), festivita)
    return _da_anno_e_nome(_cella(riga, colonne, "anno"), _cella(riga, colonne, "festivita"), festivita)


def persone_per_chiave(persone: list[dict]) -> dict[str, list[dict]]:
    """Solo i dipendenti (attivi o no): lo storico serve alla rotazione dei dipendenti."""
    indice: dict[str, list[dict]] = {}
    for p in persone:
        if p["tipo"] == "dipendente":
            indice.setdefault(_chiave_nome(p["nome"]), []).append(p)
    return indice


def _riga(numero, riga, colonne, festivita, limite) -> dict:
    """Una riga del file: {"riconosciuta": {...}} oppure {"errore": msg} oppure {"motivo", "dettaglio"}."""
    nome = " ".join(_cella(riga, colonne, "nome").split())
    if not nome or len(nome) > NOME_MAX:
        return {"errore": "nome mancante" if not nome else f"nome troppo lungo (al massimo {NOME_MAX} caratteri)"}
    if _CONTROLLO.search(nome):
        return {"errore": "nome con caratteri non validi"}
    fascia = parse_fascia(_cella(riga, colonne, "turno"))
    if fascia is None:
        return {"errore": f"turno non valido: {_cella(riga, colonne, 'turno')!r} (usa giorno o notte)"}
    f, d, problema = _festivita_e_data(riga, colonne, festivita)
    if problema:
        return problema
    if d >= limite:
        return {"motivo": "oltre_prima_generata", "dettaglio": f"{f['nome']} {d:%d/%m/%Y}"}
    return {"riconosciuta": {"riga": numero, "anno": d.year, "festivita_id": f["id"], "festivita": f["nome"],
                             "data": d.isoformat(), "fascia": fascia, "nome": nome}}


def _abbina(ric: dict, indice: dict, non_trovati: dict, numero: int) -> None:
    trovate = indice.get(_chiave_nome(ric["nome"]), [])
    ric["persona_id"] = trovate[0]["id"] if len(trovate) == 1 else None
    if ric["persona_id"] is None:
        voce = non_trovati.setdefault(_chiave_nome(ric["nome"]), {"nome": ric["nome"], "righe": [], "candidati": [
            {"id": p["id"], "nome": p["nome"], "attivo": p["attivo"]} for p in trovate]})
        voce["righe"].append(numero)


def analizza(testo: str, festivita: list[dict], persone: list[dict], limite: date) -> dict:
    """Anteprima dell'importazione: non salva nulla. ValueError se il file non si può leggere."""
    righe = _righe_numerate(testo)
    if not righe:
        raise ValueError("Il file è vuoto")
    colonne = _colonne(righe[0][1])
    indice = persone_per_chiave(persone)
    esito = {"riconosciute": [], "errori": [], "ignorate": [], "non_trovati": [], "doppioni": 0}
    visti, non_trovati = set(), {}
    for numero, riga in righe[1:]:
        r = _riga(numero, riga, colonne, festivita, limite)
        if "errore" in r:
            esito["errori"].append({"riga": numero, "messaggio": r["errore"]})
        elif "motivo" in r:
            esito["ignorate"].append({"riga": numero, **r})
        else:
            ric = r["riconosciuta"]
            chiave = (ric["anno"], ric["festivita_id"], ric["fascia"], _chiave_nome(ric["nome"]))
            if chiave in visti:
                esito["doppioni"] += 1
                continue
            visti.add(chiave)
            _abbina(ric, indice, non_trovati, numero)
            esito["riconosciute"].append(ric)
    esito["non_trovati"] = list(non_trovati.values())
    return esito
