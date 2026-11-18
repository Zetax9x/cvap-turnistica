"""Compilazione del modello Excel della scheda ore (`cvap/modelli/scheda-ore.xlsx`).

Il modello è il foglio `Scheda riepilogo Rev.3_MR_2024` (una riga per giorno, righe 15–45). Non si usa nessuna
libreria Excel: si modifica direttamente l'XML del foglio con la libreria standard, così formule, stili e
convalide restano quelli del modello. Gli orari seguono la sua convenzione (formato `[<1]h:mm;[>=1]0":00"`): ore
intere come numeri interi (8 → "8:00", anche 24), le altre come frazione del giorno (8:30 → 8,5/24).
"""
import io
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from .calendario_ics import slug
from .scheda_ore import COLONNE, giorni_del_mese, ore_colonna, ore_disponibilita_grezze

MODELLO = Path(__file__).parent / "modelli" / "scheda-ore.xlsx"
FOGLIO = "xl/worksheets/sheet1.xml"
MESI = ("GENNAIO", "FEBBRAIO", "MARZO", "APRILE", "MAGGIO", "GIUGNO", "LUGLIO", "AGOSTO", "SETTEMBRE", "OTTOBRE",
        "NOVEMBRE", "DICEMBRE")
CELLE_COLONNE = {"ascoli": ("D", "E"), "acquasanta": ("F", "G"), "venarotta": ("H", "I"), "programmati": ("J", "K"),
                 "assistenze": ("L", "M"), "viaggi_ast": ("N", "O"), "viaggi": ("P", "Q")}
TOTALE_COLONNA = {"ascoli": "D46", "acquasanta": "F46", "venarotta": "H46", "programmati": "J46",
                  "assistenze": "L46", "viaggi_ast": "N46", "viaggi": "P46"}
PRIMA_RIGA_GIORNI = 15      # il giorno g sta alla riga 14 + g
GIORNI_MAX = 31
RIGA_ETICHETTA_NOTE, RIGA_NOTE = 52, 53
ULTIMA_COLONNA_NOTE = "U"
CARATTERI_PER_RIGA_NOTE = 120
ALTEZZA_RIGA_NOTE = 15
_EPOCA_EXCEL = date(1899, 12, 30)
_CELLA = re.compile(r'<c r="([A-Z]+\d+)"([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_FORMULA = re.compile(r"<f(?:\s[^>]*)?>.*?</f>|<f(?:\s[^>]*)?/>", re.S)
_CONTROLLO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def nome_file(scheda: dict) -> str:
    return f"scheda-ore-{slug(scheda['persona']['nome'])}-{scheda['mese']}.xlsx"


# --- celle ---------------------------------------------------------------------------------

def _num(valore: float) -> str:
    return str(int(valore)) if float(valore).is_integer() else repr(float(valore))


def _orario(ore: float) -> str:
    return _num(ore) if float(ore).is_integer() else repr(round(ore / 24, 12))


def _testo(testo: str) -> str:
    return escape(_CONTROLLO.sub("", testo))


def _riscrivi(ref: str, attributi: str, interno: str | None, modifica: tuple[str, str]) -> str:
    """La cella `ref` con il nuovo valore. `modifica` = (tipo, valore): `n` numero, `s` testo, `fn` e `fs` numero o
    testo calcolato da una formula (la formula resta, cambia solo il valore memorizzato)."""
    tipo, valore = modifica
    attributi = re.sub(r'\s+t="[^"]*"', "", attributi)
    if tipo == "n":
        return f'<c r="{ref}"{attributi}><v>{valore}</v></c>'
    if tipo == "s":
        return f'<c r="{ref}"{attributi} t="inlineStr"><is><t xml:space="preserve">{_testo(valore)}</t></is></c>'
    formula = _FORMULA.search(interno or "")
    formula = formula.group(0) if formula else ""
    segno = ' t="str"' if tipo == "fs" else ""
    return f'<c r="{ref}"{attributi}{segno}>{formula}<v>{_testo(valore) if tipo == "fs" else valore}</v></c>'


def _modifiche(scheda: dict) -> dict[str, tuple[str, str]]:
    anno, numero = (int(x) for x in scheda["mese"].split("-"))
    ultimo, giorni = giorni_del_mese(scheda["mese"]), scheda["giorni"]
    celle = {"B2": ("n", str(anno)), "G3": ("s", scheda["persona"]["nome"]), "O3": ("s", MESI[numero - 1]),
             "W2": ("fn", str(numero))}
    for giorno in range(1, GIORNI_MAX + 1):
        riga = 14 + giorno
        if giorno > ultimo:
            celle[f"W{riga}"] = ("fs", "")
            continue
        celle[f"W{riga}"] = ("fn", str((date(anno, numero, giorno) - _EPOCA_EXCEL).days))
    for g in giorni:
        riga = 14 + g["giorno"]
        if g["ferie"]:
            celle[f"C{riga}"] = ("n", "1")
        for colonna, (inizio, fine) in CELLE_COLONNE.items():
            if g["colonne"][colonna]:
                celle[f"{inizio}{riga}"] = ("n", _orario(g["colonne"][colonna][0]))
                celle[f"{fine}{riga}"] = ("n", _orario(g["colonne"][colonna][1]))
        if g["note"]:
            celle[f"R{riga}"] = ("s", g["note"])
        if d := g["disponibilita"]:
            celle[f"S{riga}"], celle[f"T{riga}"] = ("n", _orario(d["inizio"])), ("n", _orario(d["fine"]))
            if d["causale"]:
                celle[f"U{riga}"] = ("s", d["causale"])
    t = scheda["totali"]
    for colonna, ref in TOTALE_COLONNA.items():
        celle[ref] = ("fn", _num(ore_colonna(giorni, colonna)))
    celle.update({"S46": ("fn", _num(ore_disponibilita_grezze(giorni))), "C48": ("fn", str(t["giorni_ferie"])),
                  "D48": ("fn", str(t["ore_postazioni"])), "J48": ("fn", str(t["ore_secondari"])),
                  "R48": ("fn", str(t["totale_mese"])), "S48": ("fn", str(t["ore_disponibilita"]))})
    return celle


# --- foglio e cartella di lavoro ----------------------------------------------------------

def _righe_note_finali(note: str) -> str:
    righe = sum(max(1, -(-len(r) // CARATTERI_PER_RIGA_NOTE)) for r in note.split("\n"))
    vuote = "".join(f'<c r="{c}{RIGA_NOTE}" s="71"/>' for c in "CDEFGHIJKLMNOPQRSTU")
    return (f'<row r="{RIGA_ETICHETTA_NOTE}" spans="2:21"><c r="B{RIGA_ETICHETTA_NOTE}" s="36" t="inlineStr">'
            '<is><t xml:space="preserve">Note finali:</t></is></c></row>'
            f'<row r="{RIGA_NOTE}" spans="2:21" ht="{ALTEZZA_RIGA_NOTE * righe}" customHeight="1">'
            f'<c r="B{RIGA_NOTE}" s="36" t="inlineStr"><is><t xml:space="preserve">{_testo(note)}</t></is></c>'
            f"{vuote}</row>")


def _foglio(xml: str, scheda: dict) -> str:
    modifiche = _modifiche(scheda)
    xml = _CELLA.sub(lambda m: _riscrivi(m.group(1), m.group(2), m.group(3), modifiche[m.group(1)])
                     if m.group(1) in modifiche else m.group(0), xml)
    if not scheda["note"].strip():
        return xml
    xml = xml.replace("</sheetData>", _righe_note_finali(scheda["note"].strip()) + "</sheetData>", 1)
    unione = f"B{RIGA_NOTE}:{ULTIMA_COLONNA_NOTE}{RIGA_NOTE}"
    conta = re.search(r'<mergeCells count="(\d+)"', xml)
    xml = xml.replace(conta.group(0), f'<mergeCells count="{int(conta.group(1)) + 1}"', 1)
    xml = xml.replace("</mergeCells>", f'<mergeCell ref="{unione}"/></mergeCells>', 1)
    return re.sub(r'<dimension ref="([A-Z]+\d+):([A-Z]+)\d+"/>', rf'<dimension ref="\1:\2{RIGA_NOTE}"/>', xml, count=1)


def _cartella(xml: str) -> str:
    """Ricalcolo all'apertura e area di stampa fino alle note finali."""
    xml = re.sub(r"<calcPr([^>]*?)/>", lambda m: m.group(0) if "fullCalcOnLoad" in m.group(1)
                 else f'<calcPr{m.group(1)} fullCalcOnLoad="1"/>', xml, count=1)
    return xml.replace("$U$50", f"$U${RIGA_NOTE}")


def compila_scheda(scheda: dict) -> bytes:
    """Il contenuto dello `.xlsx`: il modello compilato con la scheda (vedi `servizio_schede_ore.scheda_del_mese`)."""
    uscita = io.BytesIO()
    with zipfile.ZipFile(MODELLO) as modello, zipfile.ZipFile(uscita, "w", zipfile.ZIP_DEFLATED) as nuovo:
        for voce in modello.infolist():
            dati = modello.read(voce.filename)
            if voce.filename == FOGLIO:
                dati = _foglio(dati.decode("utf-8"), scheda).encode("utf-8")
            elif voce.filename == "xl/workbook.xml":
                dati = _cartella(dati.decode("utf-8")).encode("utf-8")
            nuovo.writestr(voce.filename, dati)
    return uscita.getvalue()
