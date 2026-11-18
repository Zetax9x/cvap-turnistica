"""La scheda ore che il dipendente vede: turni effettivi del mese più le sue correzioni, oppure la scheda congelata.

Compone i dati di `db`, `db_schede_ore` e il calcolo puro di `scheda_ore`; non conosce l'API né i cookie.
"""
import sqlite3
from datetime import date

from . import db, db_schede_ore, scheda_ore


def _periodo(mese: str) -> tuple[date, date]:
    anno, numero = (int(x) for x in mese.split("-"))
    return date(anno, numero, 1), date(anno, numero, scheda_ore.giorni_del_mese(mese))


def _calcolate(conn: sqlite3.Connection, persona_id: int, mese: str) -> dict[int, dict]:
    """I giorni del mese ricavati dai turni effettivi della persona, con ferie, malattie e nomi delle richieste Extra."""
    dal, al = _periodo(mese)
    turni = [a for _, a in db.assegnazioni_periodo(conn, dal, al, "effettivi") if a.persona_id == persona_id]
    malattia = db.giorni_malattia(conn, dal, al)
    assenze = {d: "malattia" if (persona_id, d) in malattia else "ferie"
               for d in db.ferie_periodo(conn, dal, al).get(persona_id, set())}
    nomi_extra = {e["segmento"]: e["nome"] for e in db.extra_periodo(conn, dal, al)}
    return scheda_ore.turni_in_righe(mese, turni, assenze, nomi_extra)


def scheda_del_mese(conn: sqlite3.Connection, persona_id: int, mese: str) -> dict:
    """La scheda mostrata: se è confermata quella congelata, altrimenti turni effettivi + correzioni."""
    persona = db.get_persona(conn, persona_id)
    salvata = db_schede_ore.get_scheda(conn, persona_id, mese)
    if salvata and salvata["stato"] == "confermata" and salvata["congelata"]:
        giorni, totali = salvata["congelata"]["giorni"], salvata["congelata"]["totali"]
    else:
        giorni = scheda_ore.applica_correzioni(_calcolate(conn, persona_id, mese),
                                               db_schede_ore.get_correzioni(conn, persona_id, mese))
        totali = scheda_ore.totali(giorni)
    return {"persona": {"id": persona_id, "nome": persona["nome"]}, "mese": mese,
            "stato": salvata["stato"] if salvata else "bozza", "note": salvata["note"] if salvata else "",
            "giorni": giorni, "totali": totali, "confermata_il": salvata["confermata_il"] if salvata else None,
            "aggiornata_il": salvata["aggiornata_il"] if salvata else None}


def congela(conn: sqlite3.Connection, persona_id: int, mese: str) -> dict:
    """La scheda mostrata ora (righe e totali), da salvare con `db_schede_ore.conferma`."""
    scheda = scheda_del_mese(conn, persona_id, mese)
    return {"giorni": scheda["giorni"], "totali": scheda["totali"]}


def salva_correzione(conn: sqlite3.Connection, persona_id: int, mese: str, giorno: int, dati: dict) -> None:
    """Salva le correzioni di un giorno; ValueError (messaggio in italiano) se non sono valide."""
    valida = scheda_ore.valida_correzione(dati, mese, giorno)
    base = _calcolate(conn, persona_id, mese)[giorno]            # il giorno com'è calcolato adesso
    db_schede_ore.salva_giorno(conn, persona_id, mese, giorno, {**valida, "_base": base})
