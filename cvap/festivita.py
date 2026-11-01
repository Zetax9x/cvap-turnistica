"""Calendario delle festività a rotazione (docs/PIANO-rotazioni.md, sezione 3.1).

Modulo puro: le festività sono dict con le colonne della tabella `festivita` (`id`, `nome`, `regola`,
`giorno`, `mese`, `offset_pasqua`, `data`, `conta_giorno`, `conta_notte`, `conta_notte_prima`, `peso`).
Le funzioni non filtrano `attiva`: lo fa chi le chiama.
"""
from collections.abc import Iterable, Mapping
from datetime import date, timedelta

from .modello import FASCE

GIORNO, NOTTE = FASCE
REGOLE = ("fissa", "pasqua", "data")
PESO_MIN, PESO_MAX = 1, 3  # 1 normale, 2 importante, 3 molto importante
OFFSET_PASQUA_MAX = 70  # copre Carnevale (-47) e Corpus Domini (+60)
ANNO_MIN_GREGORIANO, ANNO_MAX_PASQUA = 1583, 4099

# (chiave, nome, regola, giorno, mese, offset_pasqua): inserite all'avvio, non attive; l'ordine dà gli id
FESTIVITA_PREDEFINITE = (
    ("capodanno", "Capodanno", "fissa", 1, 1, None),
    ("epifania", "Epifania", "fissa", 6, 1, None),
    ("pasqua", "Pasqua", "pasqua", None, None, 0),
    ("pasquetta", "Lunedì dell'Angelo", "pasqua", None, None, 1),
    ("liberazione", "Liberazione", "fissa", 25, 4, None),
    ("lavoro", "Festa del lavoro", "fissa", 1, 5, None),
    ("repubblica", "Festa della Repubblica", "fissa", 2, 6, None),
    ("sant_emidio", "Sant'Emidio", "fissa", 5, 8, None),
    ("ferragosto", "Ferragosto", "fissa", 15, 8, None),
    ("ognissanti", "Ognissanti", "fissa", 1, 11, None),
    ("immacolata", "Immacolata", "fissa", 8, 12, None),
    ("vigilia_natale", "Vigilia di Natale", "fissa", 24, 12, None),
    ("natale", "Natale", "fissa", 25, 12, None),
    ("santo_stefano", "Santo Stefano", "fissa", 26, 12, None),
    ("san_silvestro", "San Silvestro", "fissa", 31, 12, None),
)


def pasqua(anno: int) -> date:
    """Domenica di Pasqua nel calendario gregoriano (algoritmo di Meeus/Jones/Butcher)."""
    if not ANNO_MIN_GREGORIANO <= anno <= ANNO_MAX_PASQUA:
        raise ValueError(f"Anno fuori dal calendario gregoriano supportato: {anno}")
    a, b, c = anno % 19, anno // 100, anno % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 (nome dell'algoritmo)
    m = (a + 11 * h + 19 * l) // 433
    mese = (h + l - 7 * m + 90) // 25
    giorno = (h + l - 7 * m + 33 * mese + 19) % 32
    return date(anno, mese, giorno)


def _data(valore) -> date | None:
    if valore is None or isinstance(valore, date):
        return valore
    return date.fromisoformat(valore)


def data_nell_anno(f: Mapping, anno: int) -> date | None:
    """Il giorno della festività `f` nell'anno, o None (29/2 negli anni non bisestili, data di un altro anno)."""
    if f["regola"] == "fissa":
        try:
            return date(anno, f["mese"], f["giorno"])
        except ValueError:
            return None
    if f["regola"] == "pasqua":
        return pasqua(anno) + timedelta(days=f["offset_pasqua"])
    d = _data(f["data"])
    return d if d is not None and d.year == anno else None


def occorrenze(festivita: Iterable[Mapping], dal: date, al: date) -> list[tuple[date, Mapping]]:
    """Le festività che cadono in [dal, al], ordinate per (data, id).

    Ogni festività cade al più una volta l'anno: con offset entro ±70 giorni la Pasqua non cambia anno.
    """
    elenco = list(festivita)
    trovate = [(d, f) for f in elenco for anno in range(dal.year, al.year + 1)
               if (d := data_nell_anno(f, anno)) is not None and dal <= d <= al]
    return sorted(trovate, key=lambda x: (x[0], x[1]["id"]))


def date_festive(festivita: Iterable[Mapping], anno: int) -> dict[date, str]:
    """Giorno -> nome della festività dell'anno; due festività nello stesso giorno: "Pasqua / Liberazione"."""
    nomi: dict[date, list[str]] = {}
    for d, f in occorrenze(festivita, date(anno, 1, 1), date(anno, 12, 31)):
        nomi.setdefault(d, []).append(f["nome"])
    return {d: " / ".join(n) for d, n in nomi.items()}


def _turni_di(f: Mapping, d: date) -> list[tuple[date, str]]:
    """I turni che contano per la festività del giorno `d` (la notte appartiene al giorno in cui inizia)."""
    turni = []
    if f["conta_notte_prima"]:
        turni.append((d - timedelta(days=1), NOTTE))
    if f["conta_giorno"]:
        turni.append((d, GIORNO))
    if f["conta_notte"]:
        turni.append((d, NOTTE))
    return turni


def turni_festivi(festivita: Iterable[Mapping], dal: date, al: date) -> dict[tuple[date, str], int]:
    """(data di inizio del turno, fascia) -> id della festività, per i turni in [dal, al].

    Se un turno conta per due festività vince quella di peso più alto, a parità quella con id più basso.
    """
    scelta: dict[tuple[date, str], Mapping] = {}
    for d, f in occorrenze(festivita, dal, al + timedelta(days=1)):  # +1: la notte prima della festività
        for turno in _turni_di(f, d):
            if not dal <= turno[0] <= al:
                continue
            attuale = scelta.get(turno)
            if attuale is None or (f["peso"], -f["id"]) > (attuale["peso"], -attuale["id"]):
                scelta[turno] = f
    return {turno: f["id"] for turno, f in sorted(scelta.items())}


def festivi_periodo(festivita: Iterable[Mapping], dal: date, al: date) -> list[dict]:
    """Le festività che cadono in [dal, al], per il payload della settimana."""
    return [{"data": d.isoformat(), "nome": f["nome"], "peso": f["peso"]} for d, f in occorrenze(festivita, dal, al)]


def anteprima(f: Mapping, anno: int) -> dict[str, str | None]:
    """Le date della festività nell'anno indicato e nel successivo (None se quell'anno non cade)."""
    return {str(a): (d.isoformat() if (d := data_nell_anno(f, a)) else None) for a in (anno, anno + 1)}


def errore_regola(regola: str, giorno: int | None, mese: int | None, offset_pasqua: int | None,
                  data: date | None) -> str | None:
    """Messaggio d'errore se i campi non bastano per la regola, altrimenti None."""
    if regola == "fissa":
        if giorno is None or mese is None:
            return "Per una festività fissa servono giorno e mese"
        try:
            date(2000, mese, giorno)  # anno bisestile: il 29/2 è ammesso
        except ValueError:
            return f"Giorno non valido: {giorno}/{mese}"
        return None
    if regola == "pasqua":
        return None if offset_pasqua is not None else "Per una festività legata alla Pasqua servono i giorni dalla Pasqua"
    return None if data is not None else "Per una festività in un solo giorno serve la data"
