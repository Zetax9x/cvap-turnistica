"""PDF del tabellone e dei dipendenti liberi di una settimana (A4 orizzontale), per l'app e per la stampa.

Lavora sul payload della settimana come le email: riusa da `email_turni` le righe, le celle e i testi,
così il foglio coincide con quello che si vede nella pagina.
"""
from datetime import date
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import email_turni as et
from .modello import EXTRA

_PICCOLO = ParagraphStyle("cella", fontName="Helvetica", fontSize=8, leading=10)
_CENTRO = ParagraphStyle("testa", parent=_PICCOLO, alignment=1, fontName="Helvetica-Bold")
_NOTA = ParagraphStyle("nota", parent=_PICCOLO, textColor=colors.HexColor("#4d5868"))
_GRIGLIA = colors.HexColor("#8a94a3")


def _c(hex_: str):
    return colors.HexColor(hex_)


def _documento(titolo: str, sottotitolo: str, blocchi: list) -> bytes:
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=20,
                            bottomMargin=20, title=titolo)
    stili = getSampleStyleSheet()
    doc.build([Paragraph(escape(titolo), stili["Title"]), Paragraph(escape(sottotitolo), stili["Heading3"]),
               Spacer(1, 6), *blocchi])
    return out.getvalue()


def _periodo(s: dict) -> str:
    return f"Settimana dal {et._dmy(s['inizio'])} al {et._dmy(s['fine'])}"


def _testa_giorni(s: dict) -> tuple[list, list]:
    """Intestazioni dei sette giorni e regole di sfondo (weekend e festività)."""
    celle, regole = [], []
    for i, g in enumerate(s["giorni"], start=1):
        feste = et._nomi_feste(s, g)
        testo = f"{et.GIORNI_BREVI[date.fromisoformat(g).weekday()]} {et._dm(g)}"
        if feste:
            testo += f'<br/><font size="7" color="{et.FESTIVO_TESTO}">{escape(feste)}</font>'
            regole.append(("BACKGROUND", (i, 0), (i, 0), _c(et.FESTIVO_BG)))
        elif date.fromisoformat(g).weekday() >= 5:
            regole.append(("BACKGROUND", (i, 0), (i, 0), _c(et.WEEKEND_BG)))
        celle.append(Paragraph(testo, _CENTRO))
    return celle, regole


def _voci(persone: list[dict], scoperte: list[str]) -> list[Paragraph]:
    out = []
    for p in persone:
        nome = f"<b>{escape(p['nome'])}</b>" + (f" {escape(p['orario'])}" if p["orario"] else "")
        if p["volontario"]:
            nome = f'<font backColor="{et.VOL_BG}" color="{et.VOL_TESTO}">{nome}</font>'
        out.append(Paragraph(nome, _PICCOLO))
    out += [Paragraph(f'<font color="{et.ROSSO}"><b>{escape(x)}</b></font>', _PICCOLO) for x in scoperte]
    return out or [Paragraph("—", _PICCOLO)]


def _tabella(righe: list[list], regole: list, larghezza: float) -> Table:
    colonne = [70] + [(larghezza - 70) / 7] * 7
    t = Table(righe, colWidths=colonne, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, _GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), _c(et.TESTA_BG)),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), *regole]))
    return t


def genera_tabellone(s: dict) -> bytes:
    larghezza = landscape(A4)[0] - 36
    testa, regole_testa = _testa_giorni(s)
    blocchi = []
    for postazione in et._postazioni(s):
        righe = [[Paragraph("Turno", _CENTRO), *testa]]
        regole = list(regole_testa)
        for i, (fascia, segmento, ruolo, turno) in enumerate(et._righe(postazione), start=1):
            sfondo = _c(et.GIORNO_BG if fascia == "giorno" else et.NOTTE_BG)
            etichetta = Paragraph(f"{escape(turno)}<br/><b>{et.RUOLI[ruolo]}</b>", _PICCOLO)
            righe.append([etichetta] + [_voci(*et._cella(s, postazione, g, fascia, segmento, ruolo)) for g in s["giorni"]])
            regole.append(("BACKGROUND", (0, i), (-1, i), sfondo))
            if i > 1 and ruolo == "autista":
                regole.append(("LINEABOVE", (0, i), (-1, i), 1.5, colors.black))
        blocchi.append(KeepTogether([Paragraph(f"<b>{escape(postazione)}</b>", getSampleStyleSheet()["Heading4"]),
                                     _tabella(righe, regole, larghezza), Spacer(1, 8)]))
    if s.get("extra"):
        celle = []
        for g in s["giorni"]:
            schede = []
            for e in et._richieste_extra(s, g):
                schede.append(Paragraph(f"<b>{escape(e['nome'])}</b> {escape(et._ore(e['fascia'], e['segmento']))}", _PICCOLO))
                for ruolo in et._ruoli_extra(e):
                    persone, scoperte = et._cella(s, EXTRA, g, e["fascia"], e["segmento"], ruolo)
                    schede.append(Paragraph(f"<i>{et.RUOLI[ruolo]}</i>", _NOTA))
                    schede += _voci(persone, scoperte)
            celle.append(schede or [Paragraph("—", _PICCOLO)])
        blocchi.append(KeepTogether([Paragraph(f"<b>{EXTRA}</b>", getSampleStyleSheet()["Heading4"]),
                                     _tabella([[Paragraph("Richieste", _CENTRO), *testa], [Paragraph("Assistenze<br/>ed Extra", _PICCOLO), *celle]],
                                              regole_testa, larghezza)]))
    return _documento("Tabellone dei turni", _periodo(s), blocchi)


def genera_liberi(s: dict) -> bytes:
    larghezza = landscape(A4)[0] - 36
    testa, regole = _testa_giorni(s)
    righe = [[Paragraph("", _CENTRO), *testa]]
    for chiave, titolo, bg in (("liberi", "Liberi", "#e3f2e6"), ("indisponibili", "Indisponibili", "#fdf0d5"),
                               ("ferie", "Ferie / malattia", "#e3eafa")):
        celle = []
        for g in s.get("liberi", []):
            voci = []
            for x in g[chiave]:
                note = [", ".join(et.PARTI[p] for p in x.get("parti", []))] if x.get("parti") else []
                note += [et.AVVISI.get(a, a) for a in x.get("avvisi", [])]
                if x.get("motivo"):
                    note.append("malattia" if x["motivo"] == "malattia" else "ferie")
                nota = ", ".join(n for n in note if n)
                voci.append(Paragraph(f"<b>{escape(x['nome'])}</b>" + (f" <i>({escape(nota)})</i>" if nota else ""), _PICCOLO))
            celle.append(voci or [Paragraph("—", _PICCOLO)])
        righe.append([Paragraph(f"<b>{titolo}</b>", _PICCOLO), *celle])
        regole.append(("BACKGROUND", (0, len(righe) - 1), (0, len(righe) - 1), _c(bg)))
    nota = Paragraph("Smonto notte = ha fatto la notte il giorno prima (finisce alle 8) · notte = fa la notte quella sera.", _NOTA)
    return _documento("Dipendenti liberi", _periodo(s), [_tabella(righe, regole, larghezza), Spacer(1, 6), nota])
