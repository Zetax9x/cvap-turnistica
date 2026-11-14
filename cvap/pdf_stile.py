"""Stile comune di tutti i PDF (tabellone, liberi, turni personali, cambi turno, equità, con chi si lavora).

Ogni pagina ha la stessa testata (logo, titolo, sottotitolo e una riga verde) e lo stesso piè di pagina (ente,
titolo, data di creazione e numero di pagina). Testi, tabelle e colori vengono da qui, così tutti i fogli si
somigliano e si leggono allo stesso modo.
"""
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

LOGO = Path(__file__).resolve().parent.parent / "static" / "img" / "logo-croce-verde.png"
ENTE = "Croce Verde Ascoli Piceno"

VERDE = "#009541"
VERDE_SCURO = "#00672d"
TESTO_COLORE = "#1b2330"
MUTO = "#5b6570"
GRIGLIA = colors.HexColor("#c3cbd6")
TESTA_BG = colors.HexColor("#e6f4ea")      # intestazione delle tabelle: verde chiarissimo
RIGA_ALTERNATA = colors.HexColor("#f6f8fa")
AVVISO_BG, AVVISO_BORDO = colors.HexColor("#fff4cc"), colors.HexColor("#d99000")

MARGINE = 24
TESTATA = 54  # spazio riservato in alto per logo e titolo

TITOLO = ParagraphStyle("titolo", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=colors.HexColor(VERDE))
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=colors.HexColor(VERDE),
                    spaceBefore=8, spaceAfter=5)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor(TESTO_COLORE),
                    spaceBefore=7, spaceAfter=3)
TESTO = ParagraphStyle("testo", fontName="Helvetica", fontSize=10.5, leading=14.5, textColor=colors.HexColor(TESTO_COLORE))
CELLA = ParagraphStyle("cella", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=colors.HexColor(TESTO_COLORE))
CELLA_DESTRA = ParagraphStyle("cella_destra", parent=CELLA, alignment=2)
CELLA_CENTRO = ParagraphStyle("cella_centro", parent=CELLA, alignment=1)
TESTA = ParagraphStyle("testa", parent=CELLA, fontName="Helvetica-Bold")
TESTA_DESTRA = ParagraphStyle("testa_destra", parent=TESTA, alignment=2)
TESTA_CENTRO = ParagraphStyle("testa_centro", parent=TESTA, alignment=1)
NOTA = ParagraphStyle("nota", parent=CELLA, fontSize=8.5, leading=11, textColor=colors.HexColor(MUTO))
AVVISO = ParagraphStyle("avviso", parent=TESTO, fontName="Helvetica-Bold", backColor=AVVISO_BG,
                        borderColor=AVVISO_BORDO, borderWidth=0.8, borderPadding=6, spaceBefore=4, spaceAfter=10)


class Markup(str):
    """Testo di una cella già in formato reportlab (grassetto, colori): non va escapato."""


def p(testo, stile=CELLA) -> Paragraph:
    """Paragrafo da testo semplice (escapato) o da `Markup`."""
    return Paragraph(testo if isinstance(testo, Markup) else escape(str(testo)), stile)


def larghezza(verticale: bool = False) -> float:
    pagina = A4 if verticale else landscape(A4)
    return pagina[0] - 2 * MARGINE


def tabella(intestazioni: list[str], righe: list[list], larghezze: list[float], destra=frozenset(), *,
            totale: float | None = None, alternata: bool = True, regole=()) -> Table:
    """Tabella standard: intestazione in verde chiaro ripetuta a ogni pagina, righe alternate, griglia leggera.
    `larghezze` sono proporzioni, scalate su `totale` (di norma la larghezza utile della pagina orizzontale)."""
    totale = totale or larghezza()
    dati = [[p(t, TESTA_DESTRA if i in destra else TESTA) for i, t in enumerate(intestazioni)]]
    for riga in righe:
        dati.append([c if isinstance(c, (Paragraph, list)) else p(c, CELLA_DESTRA if i in destra else CELLA)
                     for i, c in enumerate(riga)])
    somma = sum(larghezze)
    t = Table(dati, colWidths=[w * totale / somma for w in larghezze], repeatRows=1)
    stile = [("GRID", (0, 0), (-1, -1), 0.4, GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("BACKGROUND", (0, 0), (-1, 0), TESTA_BG),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if alternata and len(dati) > 2:
        stile.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, RIGA_ALTERNATA]))
    t.setStyle(TableStyle([*stile, *regole]))
    return t


def stile_griglia(regole=()) -> TableStyle:
    """Lo stile di base delle tabelle, per le griglie costruite a mano (tabellone, turni personali)."""
    return TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("BACKGROUND", (0, 0), (-1, 0), TESTA_BG),
                       ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                       ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), *regole])


def documento(titolo: str, sottotitolo: str, blocchi: list, *, verticale: bool = False,
              avviso: str | None = None, adesso: datetime | None = None) -> bytes:
    """Il PDF finito: testata e piè di pagina comuni su ogni pagina. `avviso`: riquadro giallo sotto la testata
    della prima pagina (es. "Aggiornato con i cambi turno")."""
    pagina = A4 if verticale else landscape(A4)
    creato = (adesso or datetime.now(ZoneInfo("Europe/Rome"))).strftime("%d/%m/%Y alle %H:%M")
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=pagina, leftMargin=MARGINE, rightMargin=MARGINE,
                            topMargin=MARGINE + TESTATA, bottomMargin=MARGINE + 6, title=titolo, author=ENTE)

    def testata_e_pie(canvas, _doc):
        w, h = pagina
        canvas.saveState()
        alto = h - MARGINE
        x = MARGINE
        if LOGO.exists():
            canvas.drawImage(str(LOGO), x, alto - 40, width=91, height=40, mask="auto")
            x += 104
        canvas.setFillColor(colors.HexColor(VERDE))
        canvas.setFont("Helvetica-Bold", 18)
        canvas.drawString(x, alto - 18, titolo)
        canvas.setFillColor(colors.HexColor(MUTO))
        canvas.setFont("Helvetica", 11)
        canvas.drawString(x, alto - 34, sottotitolo)
        canvas.setStrokeColor(colors.HexColor(VERDE))
        canvas.setLineWidth(1.2)
        canvas.line(MARGINE, alto - 47, w - MARGINE, alto - 47)
        canvas.setStrokeColor(GRIGLIA)
        canvas.setLineWidth(0.5)
        canvas.line(MARGINE, MARGINE + 2, w - MARGINE, MARGINE + 2)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGINE, MARGINE - 8, f"{ENTE} · {titolo} · creato il {creato}")
        canvas.drawRightString(w - MARGINE, MARGINE - 8, f"Pagina {_doc.page}")
        canvas.restoreState()

    contenuto = ([Paragraph(escape(avviso), AVVISO)] if avviso else []) + list(blocchi)
    doc.build(contenuto, onFirstPage=testata_e_pie, onLaterPages=testata_e_pie)
    return out.getvalue()
