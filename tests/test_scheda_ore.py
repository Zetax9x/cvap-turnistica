"""Calcolo puro della scheda ore mensile (cvap/scheda_ore.py)."""
from datetime import date

import pytest

from cvap.modello import EXTRA, segmento_extra
from cvap.scheda_ore import (COLONNE, applica_correzioni, formatta_orario, giorni_del_mese, mesi_apribili,
                             ore_intervallo, parse_orario, totali, turni_in_righe, valida_correzione)

from .conftest import ass

MESE = "2026-11"


# --- orari -------------------------------------------------------------------------------

@pytest.mark.parametrize("testo, atteso", [("8", 8.0), ("8:30", 8.5), ("20", 20.0), ("24", 24.0), ("0", 0.0),
                                           (" 7:15 ", 7.25), (9, 9.0), (8.5, 8.5)])
def test_parse_orario_valido(testo, atteso):
    assert parse_orario(testo) == atteso


@pytest.mark.parametrize("testo", ["25", "8:60", "abc", "", "-1", "24:30", "8:5:3", None])
def test_parse_orario_non_valido(testo):
    with pytest.raises(ValueError):
        parse_orario(testo)


def test_formatta_orario():
    assert formatta_orario(8.5) == "8:30"
    assert formatta_orario(20.0) == "20"
    assert formatta_orario(7.25) == "7:15"


@pytest.mark.parametrize("inizio, fine, atteso", [(8, 20, 12), (20, 8, 12), (8, 8, 24), (20, 0, 4), (8, 8.5, 0.5),
                                                   (0, 24, 24), (23, 1, 2)])
def test_ore_intervallo(inizio, fine, atteso):
    assert ore_intervallo(inizio, fine) == atteso


# --- mesi --------------------------------------------------------------------------------

def test_giorni_del_mese():
    assert giorni_del_mese("2026-02") == 28
    assert giorni_del_mese("2028-02") == 29
    assert giorni_del_mese("2026-11") == 30
    assert giorni_del_mese("2026-12") == 31


def test_mesi_apribili_dal_corrente_ai_dodici_precedenti():
    mesi = mesi_apribili(date(2026, 11, 18))
    assert len(mesi) == 13 and mesi[0] == "2026-11" and mesi[-1] == "2025-11"
    assert mesi_apribili(date(2026, 1, 5))[1] == "2025-12"


# --- dai turni alle righe ----------------------------------------------------------------

def test_ogni_giorno_del_mese_e_presente_anche_senza_turni():
    righe = turni_in_righe(MESE, [], {}, {})
    assert sorted(righe) == list(range(1, 31))
    g = righe[5]
    assert g["ferie"] == 0 and g["note"] == "" and g["disponibilita"] is None
    assert g["colonne"] == {c: None for c in COLONNE}
    assert g["da_rivedere"] is False and g["corretto"] is False and g["turni_cambiati"] is False


def test_acquasanta_giorno_va_nella_sua_colonna():
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 18), "Acquasanta", "giorno", "autista", 1)], {}, {})
    assert righe[18]["colonne"]["acquasanta"] == [8.0, 20.0]
    assert all(v is None for c, v in righe[18]["colonne"].items() if c != "acquasanta")


@pytest.mark.parametrize("postazione, colonna", [("Ascoli", "ascoli"), ("Acquasanta", "acquasanta"),
                                                  ("Venarotta", "venarotta")])
def test_postazioni_nelle_rispettive_colonne(postazione, colonna):
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 3), postazione, "giorno", "autista", 1)], {}, {})
    assert righe[3]["colonne"][colonna] == [8.0, 20.0]


def test_la_notte_a_cavallo_del_mese_resta_nel_giorno_di_inizio():
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 30), "Acquasanta", "notte", "autista", 1)], {}, {})
    assert righe[30]["colonne"]["acquasanta"] == [20.0, 8.0]


def test_i_turni_di_un_altro_mese_sono_ignorati():
    turni = [ass(date(2026, 12, 1), "Acquasanta", "giorno", "autista", 1),
             ass(date(2026, 10, 31), "Acquasanta", "notte", "autista", 1)]
    righe = turni_in_righe(MESE, turni, {}, {})
    assert all(g["colonne"]["acquasanta"] is None for g in righe.values())


def test_mezzi_turni_programmati_contigui_diventano_un_intervallo():
    turni = [ass(date(2026, 11, 10), "Programmati", "giorno", "autista", 1, segmento="prog_mattina"),
             ass(date(2026, 11, 10), "Programmati", "giorno", "autista", 1, segmento="prog_pomeriggio")]
    righe = turni_in_righe(MESE, turni, {}, {})
    assert righe[10]["colonne"]["programmati"] == [7.0, 20.0]
    assert righe[10]["da_rivedere"] is False


def test_standby_va_in_programmati_con_nota_standby():
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 12), "Standby", "giorno", "autista", 1, segmento="standby")], {}, {})
    assert righe[12]["colonne"]["programmati"] == [7.0, 19.0]
    assert righe[12]["note"] == "Standby"


def test_standby_di_notte_a_cavallo_della_mezzanotte():
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 12), "Standby", "notte", "autista", 1, segmento="standby")], {}, {})
    assert righe[12]["colonne"]["programmati"] == [19.0, 7.0]


def test_extra_va_in_assistenze_con_il_nome_della_richiesta():
    seg = segmento_extra(5, 9, 13)
    turno = ass(date(2026, 11, 14), EXTRA, "giorno", "autista", 1, segmento=seg)
    righe = turni_in_righe(MESE, [turno], {}, {seg: "Assistenza partita"})
    assert righe[14]["colonne"]["assistenze"] == [9.0, 13.0]
    assert righe[14]["note"] == "Assistenza partita"


def test_extra_senza_nome_usa_il_nome_generico():
    seg = segmento_extra(5, 9, 13)
    righe = turni_in_righe(MESE, [ass(date(2026, 11, 14), EXTRA, "giorno", "autista", 1, segmento=seg)], {}, {})
    assert righe[14]["note"] == EXTRA


def test_ferie_e_malattia():
    assenze = {date(2026, 11, 2): "ferie", date(2026, 11, 3): "malattia"}
    righe = turni_in_righe(MESE, [], assenze, {})
    assert righe[2]["ferie"] == 1 and righe[2]["note"] == ""
    assert righe[3]["ferie"] == 0 and righe[3]["note"] == "Malattia"


def test_due_intervalli_non_contigui_nella_stessa_colonna_vanno_rivisti():
    turni = [ass(date(2026, 11, 20), "Programmati", "giorno", "autista", 1, segmento="prog_mattina"),
             ass(date(2026, 11, 20), "Standby", "notte", "autista", 1, segmento="standby")]
    g = turni_in_righe(MESE, turni, {}, {})[20]
    assert g["colonne"]["programmati"] == [7.0, 14.0]
    assert g["da_rivedere"] is True
    assert "19" in g["note"] and "7" in g["note"]


# --- correzioni --------------------------------------------------------------------------

def correzione(**cambi):
    dati = {"ferie": 0, "colonne": {"acquasanta": ["8:30", "20"]}, "note": "", "disponibilita": None}
    dati.update(cambi)
    return dati


def test_valida_correzione_normalizza_gli_orari():
    v = valida_correzione(correzione(), MESE, 18)
    assert v["colonne"]["acquasanta"] == [8.5, 20.0]
    assert v["colonne"]["ascoli"] is None
    assert set(v["colonne"]) == set(COLONNE)
    assert v["ferie"] == 0 and v["note"] == "" and v["disponibilita"] is None
    assert "_base" not in v


def test_valida_correzione_disponibilita():
    v = valida_correzione(correzione(disponibilita={"inizio": "9", "fine": "13:30", "causale": "Evento"}), MESE, 18)
    assert v["disponibilita"] == {"inizio": 9.0, "fine": 13.5, "causale": "Evento"}


@pytest.mark.parametrize("giorno, dati", [
    (31, correzione()),                                               # novembre ha 30 giorni
    (0, correzione()),
    (5, correzione(note="x" * 201)),
    (5, correzione(colonne={"sconosciuta": ["8", "9"]})),
    (5, correzione(colonne={"ascoli": ["8", ""]})),                   # un solo estremo
    (5, correzione(colonne={"ascoli": ["8"]})),
    (5, correzione(colonne={"ascoli": ["25", "9"]})),
    (5, correzione(ferie=2)),
    (5, correzione(disponibilita={"inizio": "9", "fine": "", "causale": ""})),
    (5, correzione(disponibilita={"inizio": "9", "fine": "10", "causale": "x" * 101})),
])
def test_valida_correzione_rifiuta(giorno, dati):
    with pytest.raises(ValueError):
        valida_correzione(dati, MESE, giorno)


def test_il_giorno_corretto_sostituisce_quello_calcolato():
    calcolate = turni_in_righe(MESE, [ass(date(2026, 11, 18), "Acquasanta", "giorno", "autista", 1)], {}, {})
    corr = valida_correzione(correzione(colonne={"acquasanta": ["9", "17"]}), MESE, 18)
    righe = applica_correzioni(calcolate, {18: corr})
    assert [r["giorno"] for r in righe] == list(range(1, 31))
    g = righe[17]
    assert g["colonne"]["acquasanta"] == [9.0, 17.0] and g["corretto"] is True
    assert righe[0]["corretto"] is False and righe[18]["corretto"] is False


def test_turni_cambiati_solo_se_il_calcolato_di_oggi_differisce_dalla_base():
    prima = turni_in_righe(MESE, [ass(date(2026, 11, 18), "Acquasanta", "giorno", "autista", 1)], {}, {})
    corr = valida_correzione(correzione(note="ok"), MESE, 18)
    assert applica_correzioni(prima, {18: corr})[17]["turni_cambiati"] is False        # senza _base
    corr_con_base = {**corr, "_base": prima[18]}
    assert applica_correzioni(prima, {18: corr_con_base})[17]["turni_cambiati"] is False
    dopo = turni_in_righe(MESE, [], {}, {})                                              # il turno è stato tolto
    assert applica_correzioni(dopo, {18: corr_con_base})[17]["turni_cambiati"] is True
    assert "_base" not in applica_correzioni(dopo, {18: corr_con_base})[17]


# --- totali ------------------------------------------------------------------------------

def righe_con(colonne=None, ferie=0, disp=None, n=1):
    g = turni_in_righe(MESE, [], {}, {})[n]
    return {**g, "colonne": {**g["colonne"], **(colonne or {})}, "ferie": ferie, "disponibilita": disp}


def test_totali_ore_postazioni_e_ferie():
    giorni = [righe_con({"ascoli": [8.0, 20.0]}, n=1), righe_con({"acquasanta": [20.0, 8.0]}, n=2),
              righe_con(ferie=1, n=3), righe_con(ferie=1, n=4)]
    t = totali(giorni)
    assert t["giorni_ferie"] == 2
    assert t["ore_postazioni"] == 24 and t["ore_secondari"] == 0 and t["totale_mese"] == 24


def test_totali_secondari_e_totale_mese():
    giorni = [righe_con({"programmati": [7.0, 19.0], "assistenze": [9.0, 13.0]}, n=1),
              righe_con({"viaggi": [8.0, 9.0]}, n=2), righe_con({"acquasanta": [8.0, 20.0]}, n=3)]
    t = totali(giorni)
    assert t["ore_postazioni"] == 12 and t["ore_secondari"] == 17
    assert t["totale_mese"] == 29


@pytest.mark.parametrize("fine, atteso", [(8.4, 0), (8.5, 0), (8.6, 1), (9.5, 1), (9.6, 2)])
def test_i_secondari_si_arrotondano_all_ora_come_nel_modello(fine, atteso):
    # formula del modello: -INT(0.5 - ROUND(x, 4)): la mezz'ora esatta scende
    t = totali([righe_con({"viaggi_ast": [8.0, fine]})])
    assert t["ore_secondari"] == atteso


def test_totali_disponibilita_aggiuntive():
    giorni = [righe_con(disp={"inizio": 9.0, "fine": 13.0, "causale": "x"}, n=1),
              righe_con(disp={"inizio": 20.0, "fine": 2.5, "causale": "y"}, n=2)]
    assert totali(giorni)["ore_disponibilita"] == 10     # 4 + 6,5 = 10,5 → 10 (la mezz'ora scende)


def test_intervalli_uguali_valgono_24_ore():
    assert totali([righe_con({"ascoli": [8.0, 8.0]})])["ore_postazioni"] == 24


def test_celle_incomplete_non_contano():
    assert totali([righe_con({"ascoli": [8.0, None]})])["ore_postazioni"] == 0
