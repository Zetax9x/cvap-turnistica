"""Compilazione del modello Excel della scheda ore (cvap/xlsx_scheda.py)."""
import io
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

import pytest

from cvap.modello import EXTRA, segmento_extra
from cvap.scheda_ore import applica_correzioni, totali, turni_in_righe, valida_correzione
from cvap.xlsx_scheda import compila_scheda, nome_file

from .conftest import ass

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
MODELLO = "cvap/modelli/scheda-ore.xlsx"


def scheda(mese="2026-11", turni=(), assenze=None, correzioni=None, note="", nome="Mario Rossi", nomi_extra=None):
    calcolate = turni_in_righe(mese, list(turni), assenze or {}, nomi_extra or {})
    giorni = applica_correzioni(calcolate, correzioni or {})
    return {"persona": {"nome": nome}, "mese": mese, "note": note, "giorni": giorni, "totali": totali(giorni)}


def leggi(contenuto: bytes):
    """(celle, unioni, testo del workbook): celle = riferimento -> numero, testo o None se vuota."""
    z = zipfile.ZipFile(io.BytesIO(contenuto))
    foglio = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    condivise = [("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
                 for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)]
    celle = {}
    for c in foglio.iter("{%s}c" % NS["m"]):
        tipo, v = c.get("t"), c.find("m:v", NS)
        if tipo == "inlineStr":
            celle[c.get("r")] = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
        elif tipo == "s" and v is not None:
            celle[c.get("r")] = condivise[int(v.text)]
        elif tipo == "str":
            celle[c.get("r")] = (v.text or "") if v is not None else ""
        elif v is not None and v.text not in (None, ""):
            celle[c.get("r")] = float(v.text)
        else:
            celle[c.get("r")] = None
    unioni = foglio.find("m:mergeCells", NS)
    return celle, unioni, z.read("xl/workbook.xml").decode("utf-8")


def test_lo_zip_conserva_tutti_i_file_del_modello_e_ogni_xml_si_rilegge():
    uscita = zipfile.ZipFile(io.BytesIO(compila_scheda(scheda())))
    modello = zipfile.ZipFile(MODELLO)
    assert set(uscita.namelist()) == set(modello.namelist())
    for nome in uscita.namelist():
        if nome.endswith((".xml", ".rels")):
            ET.fromstring(uscita.read(nome))


def test_ore_intere_come_interi_e_mezze_ore_come_frazione_del_giorno():
    turni = [ass(date(2026, 11, 18), "Acquasanta", "giorno", "autista", 1)]
    celle, _, _ = leggi(compila_scheda(scheda(turni=turni)))
    assert celle["F32"] == 8 and celle["G32"] == 20          # giorno 18 → riga 14 + 18
    corr = {18: valida_correzione({"colonne": {"ascoli": ["8:30", "20"]}}, "2026-11", 18)}
    celle, _, _ = leggi(compila_scheda(scheda(turni=turni, correzioni=corr)))
    assert celle["D32"] == pytest.approx(8.5 / 24, abs=1e-9) and celle["E32"] == 20
    assert celle["F32"] is None                               # la correzione ha sostituito il giorno


def test_mezzanotte_e_ventiquattro_ore():
    corr = {5: valida_correzione({"colonne": {"ascoli": ["8", "8"], "venarotta": ["14", "0"]}}, "2026-11", 5)}
    celle, _, _ = leggi(compila_scheda(scheda(correzioni=corr)))
    assert celle["D19"] == 8 and celle["E19"] == 8            # uguali: 24 ore, le conta la formula del modello
    assert celle["H19"] == 14 and celle["I19"] == 0           # fine a mezzanotte


def test_ventiquattro_si_scrive_zero_cosi_il_modello_conta_come_la_pagina():
    # nel modello 24 diventa 24*(1-23/24) in virgola mobile: scritto come 0 il confronto tra inizio e fine è esatto
    corr = {6: valida_correzione({"colonne": {"ascoli": ["0", "24"], "venarotta": ["24", "0"], "acquasanta": ["8", "24"]}},
                                 "2026-11", 6)}
    sc = scheda(correzioni=corr)
    celle, _, _ = leggi(compila_scheda(sc))
    assert celle["D20"] == 0 and celle["E20"] == 0               # 0–24: 24 ore
    assert celle["H20"] == 0 and celle["I20"] == 0               # 24–0: 24 ore
    assert celle["F20"] == 8 and celle["G20"] == 0               # 8–24: 16 ore
    assert sc["totali"]["ore_postazioni"] == 24 + 24 + 16


def test_intestazione_anno_nome_mese():
    celle, _, _ = leggi(compila_scheda(scheda()))
    assert celle["B2"] == 2026 and celle["G3"] == "Mario Rossi" and celle["O3"] == "NOVEMBRE"
    assert celle["W2"] == 11
    celle, _, _ = leggi(compila_scheda(scheda(mese="2027-03")))
    assert celle["B2"] == 2027 and celle["O3"] == "MARZO" and celle["W2"] == 3


def test_ferie_note_e_disponibilita():
    corr = {7: valida_correzione({"ferie": 1, "note": "Visita medica",
                                  "disponibilita": {"inizio": "9", "fine": "13", "causale": "Evento"}}, "2026-11", 7)}
    celle, _, _ = leggi(compila_scheda(scheda(correzioni=corr)))
    assert celle["C21"] == 1 and celle["R21"] == "Visita medica"
    assert celle["S21"] == 9 and celle["T21"] == 13 and celle["U21"] == "Evento"


def test_note_e_standby_dai_turni():
    seg = segmento_extra(5, 9, 13)
    turni = [ass(date(2026, 11, 14), EXTRA, "giorno", "autista", 1, segmento=seg),
             ass(date(2026, 11, 12), "Standby", "giorno", "autista", 1, segmento="standby")]
    celle, _, _ = leggi(compila_scheda(scheda(turni=turni, nomi_extra={seg: "Assistenza partita"})))
    assert celle["R28"] == "Assistenza partita" and celle["L28"] == 9 and celle["M28"] == 13
    assert celle["R26"] == "Standby" and celle["J26"] == 7 and celle["K26"] == 19


def test_totali_scritti_nelle_celle_con_formula():
    turni = [ass(date(2026, 11, 18), "Acquasanta", "giorno", "autista", 1),
             ass(date(2026, 11, 20), "Ascoli", "notte", "autista", 1)]
    sc = scheda(turni=turni, assenze={date(2026, 11, 2): "ferie"})
    celle, _, _ = leggi(compila_scheda(sc))
    assert celle["F46"] == 12 and celle["D46"] == 12 and celle["H46"] == 0
    assert celle["D48"] == sc["totali"]["ore_postazioni"] == 24
    assert celle["J48"] == sc["totali"]["ore_secondari"] and celle["R48"] == sc["totali"]["totale_mese"]
    assert celle["C48"] == sc["totali"]["giorni_ferie"] == 1
    assert celle["S48"] == sc["totali"]["ore_disponibilita"]


def test_ricalcolo_all_apertura_e_area_di_stampa_con_le_note_finali():
    _, _, workbook = leggi(compila_scheda(scheda()))
    assert 'fullCalcOnLoad="1"' in workbook
    assert "$A$1:$U$53" in workbook


@pytest.mark.parametrize("testo", ["O'Neil & <Figli> \"Rossi\"", "Perché è così: à è ì ò ù — ok"])
def test_caratteri_speciali_in_nome_e_note(testo):
    corr = {3: valida_correzione({"note": testo[:100]}, "2026-11", 3)}
    celle, _, _ = leggi(compila_scheda(scheda(nome=testo, note=testo, correzioni=corr)))
    assert celle["G3"] == testo and celle["R17"] == testo[:100] and celle["B53"] == testo


def test_note_finali_con_etichetta_e_cella_unita():
    celle, unioni, _ = leggi(compila_scheda(scheda(note="Riga uno\nRiga due")))
    assert celle["B52"] == "Note finali:" and celle["B53"] == "Riga uno\nRiga due"
    riferimenti = [m.get("ref") for m in unioni.findall("m:mergeCell", NS)]
    assert "B53:U53" in riferimenti and int(unioni.get("count")) == len(riferimenti)


def test_senza_note_finali_non_si_scrive_il_riquadro():
    celle, unioni, _ = leggi(compila_scheda(scheda(note="")))
    assert celle.get("B52") in (None, "") and celle.get("B53") in (None, "")
    assert "B53:U53" not in [m.get("ref") for m in unioni.findall("m:mergeCell", NS)]


@pytest.mark.parametrize("mese, ultimo", [("2026-02", 28), ("2028-02", 29), ("2026-11", 30), ("2026-12", 31)])
def test_righe_dopo_l_ultimo_giorno_restano_vuote(mese, ultimo):
    corr = {ultimo: valida_correzione({"colonne": {"ascoli": ["8", "20"]}}, mese, ultimo)}
    celle, _, _ = leggi(compila_scheda(scheda(mese=mese, correzioni=corr)))
    assert celle[f"D{14 + ultimo}"] == 8
    for giorno in range(ultimo + 1, 32):
        riga = 14 + giorno
        assert all(celle.get(f"{col}{riga}") in (None, "") for col in "CDEFGHIJKLMNOPQRSTU")
        assert celle.get(f"W{riga}") in (None, "")                 # la data di servizio non esiste


def test_data_di_servizio_per_i_giorni_del_mese():
    celle, _, _ = leggi(compila_scheda(scheda(mese="2026-11")))
    assert celle["W15"] == 46327 and celle["W44"] == 46356          # 1 e 30 novembre 2026 (seriali di Excel)


def test_nome_file():
    assert nome_file(scheda()) == "scheda-ore-mario-rossi-2026-11.xlsx"
    assert nome_file(scheda(nome="Dell'Orto Giovanni", mese="2027-01")) == "scheda-ore-dell-orto-giovanni-2027-01.xlsx"
