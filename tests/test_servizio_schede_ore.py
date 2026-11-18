"""Servizio della scheda ore: turni effettivi, correzioni, conferma (cvap/servizio_schede_ore.py)."""
from datetime import date, datetime

import pytest

from cvap import db, db_schede_ore, servizio_schede_ore as servizio
from cvap.modello import Assegnazione

MESE = "2026-11"
ADESSO = datetime(2026, 11, 18, 10, 0, 0)


@pytest.fixture
def conn(tmp_path):
    c = db.connetti(str(tmp_path / "t.db"))
    yield c
    c.close()


@pytest.fixture
def mario(conn):
    return db.crea_persona(conn, "Mario Rossi", "dipendente", "autista")["id"]


@pytest.fixture
def anna(conn):
    return db.crea_persona(conn, "Anna Neri", "dipendente", "soccorritore")["id"]


def turno(conn, persona_id, giorno, postazione="Acquasanta", fascia="giorno", segmento="intero", ruolo="autista"):
    return db.crea_assegnazione(conn, Assegnazione(giorno, postazione, fascia, segmento, ruolo, persona_id, "generato"))


def giorno(scheda, n):
    return scheda["giorni"][n - 1]


def test_la_scheda_ha_persona_mese_stato_e_tutti_i_giorni(conn, mario):
    s = servizio.scheda_del_mese(conn, mario, MESE)
    assert s["persona"] == {"id": mario, "nome": "Mario Rossi"} and s["mese"] == MESE
    assert s["stato"] == "bozza" and s["note"] == "" and s["confermata_il"] is None
    assert [g["giorno"] for g in s["giorni"]] == list(range(1, 31))
    assert s["totali"]["totale_mese"] == 0


def test_la_scheda_segue_i_turni_effettivi_dopo_un_cambio(conn, mario, anna):
    aid = turno(conn, mario, date(2026, 11, 18))
    assert giorno(servizio.scheda_del_mese(conn, mario, MESE), 18)["colonne"]["acquasanta"] == [8.0, 20.0]
    with conn:
        db.imposta_titolare_effettivo(conn, aid, anna)                    # cessione a Anna
    assert giorno(servizio.scheda_del_mese(conn, mario, MESE), 18)["colonne"]["acquasanta"] is None
    s_anna = servizio.scheda_del_mese(conn, anna, MESE)
    assert giorno(s_anna, 18)["colonne"]["acquasanta"] == [8.0, 20.0] and s_anna["totali"]["ore_postazioni"] == 12


def test_la_notte_del_30_compare_il_30_e_quella_del_primo_del_mese_dopo_no(conn, mario):
    turno(conn, mario, date(2026, 11, 30), fascia="notte")
    turno(conn, mario, date(2026, 12, 1), fascia="notte")
    s = servizio.scheda_del_mese(conn, mario, MESE)
    assert giorno(s, 30)["colonne"]["acquasanta"] == [20.0, 8.0]
    assert sum(1 for g in s["giorni"] if g["colonne"]["acquasanta"]) == 1


def test_ferie_e_malattia(conn, mario):
    db.crea_ferie(conn, mario, date(2026, 11, 2), date(2026, 11, 3), "ferie")
    db.crea_ferie(conn, mario, date(2026, 11, 10), date(2026, 11, 10), "malattia")
    s = servizio.scheda_del_mese(conn, mario, MESE)
    assert giorno(s, 2)["ferie"] == 1 and giorno(s, 3)["ferie"] == 1 and s["totali"]["giorni_ferie"] == 2
    assert giorno(s, 10)["ferie"] == 0 and giorno(s, 10)["note"] == "Malattia"


def test_una_correzione_sostituisce_il_giorno_calcolato(conn, mario):
    turno(conn, mario, date(2026, 11, 18))
    servizio.salva_correzione(conn, mario, MESE, 18, {"colonne": {"acquasanta": ["9", "17"]}})
    g = giorno(servizio.scheda_del_mese(conn, mario, MESE), 18)
    assert g["colonne"]["acquasanta"] == [9.0, 17.0] and g["corretto"] is True and g["turni_cambiati"] is False


def test_correzione_non_valida_solleva_value_error(conn, mario):
    with pytest.raises(ValueError):
        servizio.salva_correzione(conn, mario, MESE, 31, {})
    assert db_schede_ore.get_correzioni(conn, mario, MESE) == {}


def test_turni_cambiati_dopo_la_correzione(conn, mario):
    aid = turno(conn, mario, date(2026, 11, 18))
    servizio.salva_correzione(conn, mario, MESE, 18, {"note": "ok"})
    db.elimina_assegnazione(conn, aid)                                    # il turno viene tolto
    g = giorno(servizio.scheda_del_mese(conn, mario, MESE), 18)
    assert g["corretto"] is True and g["turni_cambiati"] is True


def test_la_scheda_confermata_non_cambia_se_i_turni_cambiano(conn, mario):
    aid = turno(conn, mario, date(2026, 11, 18))
    db_schede_ore.conferma(conn, mario, MESE, servizio.congela(conn, mario, MESE), ADESSO)
    prima = servizio.scheda_del_mese(conn, mario, MESE)
    db.elimina_assegnazione(conn, aid)
    dopo = servizio.scheda_del_mese(conn, mario, MESE)
    assert prima["stato"] == dopo["stato"] == "confermata"
    assert prima["giorni"] == dopo["giorni"] and prima["totali"] == dopo["totali"]
    assert giorno(dopo, 18)["colonne"]["acquasanta"] == [8.0, 20.0] and dopo["totali"]["ore_postazioni"] == 12
    assert dopo["confermata_il"] == ADESSO.isoformat(timespec="seconds")


def test_dopo_la_riapertura_i_giorni_non_corretti_seguono_di_nuovo_i_turni(conn, mario):
    aid = turno(conn, mario, date(2026, 11, 18))
    turno(conn, mario, date(2026, 11, 19))
    servizio.salva_correzione(conn, mario, MESE, 19, {"note": "mia"})
    db_schede_ore.conferma(conn, mario, MESE, servizio.congela(conn, mario, MESE), ADESSO)
    db.elimina_assegnazione(conn, aid)
    db_schede_ore.riapri(conn, mario, MESE)
    s = servizio.scheda_del_mese(conn, mario, MESE)
    assert s["stato"] == "bozza"
    assert giorno(s, 18)["colonne"]["acquasanta"] is None                 # segue i turni: il turno non c'è più
    assert giorno(s, 19)["note"] == "mia" and giorno(s, 19)["corretto"] is True


def test_le_note_finali_arrivano_dalla_scheda_salvata(conn, mario):
    db_schede_ore.salva_note(conn, mario, MESE, "Tutto ok", ADESSO)
    assert servizio.scheda_del_mese(conn, mario, MESE)["note"] == "Tutto ok"


def test_i_turni_degli_altri_non_compaiono(conn, mario, anna):
    turno(conn, anna, date(2026, 11, 18), ruolo="soccorritore")
    assert sum(1 for g in servizio.scheda_del_mese(conn, mario, MESE)["giorni"] if g["colonne"]["acquasanta"]) == 0
