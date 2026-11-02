"""Repository della tabella `festivi_disponibili` (schema in db.py): chi vuole lavorare una festività
(docs/PIANO-rotazioni.md, 3.6). Una riga per giorno della festività e dipendente; fascia giorno, notte o entrambi.

Le letture restituiscono solo righe valide oggi: giorno che è una festività attiva, fascia che quella festività
conta (`rotazione_festivi.fasce_valide`) e dipendente attivo. Le righe che non valgono più si cancellano quando
cambia o si cancella una festività (`pulisci`, nella stessa transazione) e quando una persona smette di essere un
dipendente attivo (db.aggiorna_persona, db.elimina_persona).
"""
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import date

from .rotazione_festivi import fasce_valide

_RIGHE_VALIDE = (
    "SELECT d.data, d.persona_id, p.nome, d.fascia FROM festivi_disponibili d JOIN persone p ON p.id = d.persona_id "
    "WHERE d.data >= ? AND d.data <= ? AND p.attivo = 1 AND p.tipo = 'dipendente' "
    "ORDER BY d.data, p.nome COLLATE NOCASE, d.persona_id")


def _valide(conn, festivita: Iterable[Mapping], dal: date, al: date) -> list:
    festivita = list(festivita)
    rows = conn.execute(_RIGHE_VALIDE, (dal.isoformat(), al.isoformat())).fetchall()
    return [r for r in rows if r["fascia"] in fasce_valide(festivita, date.fromisoformat(r["data"]))]


def elenco(conn: sqlite3.Connection, festivita: Iterable[Mapping], dal: date, al: date) -> list[dict]:
    """[{data, persona_id, nome, fascia}] con data in [dal, al], in ordine di data e nome. `festivita`: le attive."""
    return [{"data": r["data"], "persona_id": r["persona_id"], "nome": r["nome"], "fascia": r["fascia"]}
            for r in _valide(conn, festivita, dal, al)]


def per_giorno(conn: sqlite3.Connection, festivita: Iterable[Mapping], dal: date, al: date) -> dict[date, dict[int, str]]:
    """Giorno della festività -> persona -> fascia, con data in [dal, al] (per generatore e ordine di rotazione)."""
    out: dict[date, dict[int, str]] = {}
    for r in _valide(conn, festivita, dal, al):
        out.setdefault(date.fromisoformat(r["data"]), {})[r["persona_id"]] = r["fascia"]
    return out


def imposta(conn: sqlite3.Connection, data: date, persona_id: int, fascia: str | None) -> None:
    """Segna (o cambia) la fascia che la persona vuole lavorare quel giorno; None la toglie."""
    with conn:
        if fascia is None:
            conn.execute("DELETE FROM festivi_disponibili WHERE data = ? AND persona_id = ?",
                         (data.isoformat(), persona_id))
        else:
            conn.execute("INSERT INTO festivi_disponibili(data, persona_id, fascia) VALUES (?, ?, ?) "
                         "ON CONFLICT(data, persona_id) DO UPDATE SET fascia = excluded.fascia",
                         (data.isoformat(), persona_id, fascia))


def pulisci(conn: sqlite3.Connection, festivita: Iterable[Mapping]) -> None:
    """Cancella le righe di giorni che non sono più festività attive o con una fascia che non conta più.

    Da chiamare DENTRO la transazione che cambia il calendario (non apre un proprio `with conn`)."""
    festivita = list(festivita)
    rows = conn.execute("SELECT DISTINCT data, fascia FROM festivi_disponibili").fetchall()
    for r in rows:
        if r["fascia"] not in fasce_valide(festivita, date.fromisoformat(r["data"])):
            conn.execute("DELETE FROM festivi_disponibili WHERE data = ? AND fascia = ?", (r["data"], r["fascia"]))


def togli_persona(conn: sqlite3.Connection, persona_id: int) -> None:
    """Da chiamare dentro una transazione: la persona non entra più nella rotazione."""
    conn.execute("DELETE FROM festivi_disponibili WHERE persona_id = ?", (persona_id,))
