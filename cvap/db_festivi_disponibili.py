"""Repository della tabella `festivi_disponibili` (schema in db.py): chi vuole lavorare una festività
(docs/PIANO-rotazioni.md, 3.6). Una riga per giorno della festività e dipendente; fascia giorno, notte o entrambi."""
import sqlite3
from datetime import date


def elenco(conn: sqlite3.Connection, dal: date, al: date) -> list[dict]:
    """[{data, persona_id, nome, fascia}] con data in [dal, al], in ordine di data e nome."""
    rows = conn.execute(
        "SELECT d.data, d.persona_id, p.nome, d.fascia FROM festivi_disponibili d JOIN persone p ON p.id = d.persona_id "
        "WHERE d.data >= ? AND d.data <= ? ORDER BY d.data, p.nome COLLATE NOCASE, d.persona_id",
        (dal.isoformat(), al.isoformat())).fetchall()
    return [{"data": r["data"], "persona_id": r["persona_id"], "nome": r["nome"], "fascia": r["fascia"]} for r in rows]


def per_giorno(conn: sqlite3.Connection, dal: date, al: date) -> dict[date, dict[int, str]]:
    """Giorno della festività -> persona -> fascia, con data in [dal, al] (per generatore e ordine di rotazione)."""
    out: dict[date, dict[int, str]] = {}
    rows = conn.execute("SELECT data, persona_id, fascia FROM festivi_disponibili WHERE data >= ? AND data <= ?",
                        (dal.isoformat(), al.isoformat())).fetchall()
    for r in rows:
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
