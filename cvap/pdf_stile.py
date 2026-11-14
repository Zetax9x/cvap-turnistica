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
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor(VERDE),
                    spaceBefore=8, spaceAfter=5)
H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=15, leading=18, textColor=colors.HexColor(TESTO_COLORE),
                    spaceBefore=2, spaceAfter=3)
TESTO = ParagraphStyle("testo", fontName="Helvetica", fontSize=11, leading=15, textColor=colors.HexColor(TESTO_COLORE))
CELLA = ParagraphStyle("cella", fontName="Helvetica", fontSize=10.5, leading=13.5, textColor=colors.HexColor(TESTO_COLORE))
CELLA_DESTRA = ParagraphStyle("cella_destra", parent=CELLA, alignment=2)
CELLA_CENTRO = ParagraphStyle("cella_centro", parent=CELLA, alignment=1)
TESTA = ParagraphStyle("testa", parent=CELLA, fontName="Helvetica-Bold")
TESTA_DESTRA = ParagraphStyle("testa_destra", parent=TESTA, alignment=2)
TESTA_CENTRO = ParagraphStyle("testa_centro", parent=TESTA, alignment=1)
NOTA = ParagraphStyle("nota", parent=CELLA, fontSize=9, leading=11.5, textColor=colors.HexColor(MUTO))
# griglie per giorno (tabellone, turni personali, liberi): testo grande e centrato, come la proposta A
CELLA_GRANDE = ParagraphStyle("cella_grande", parent=CELLA, fontSize=12, leading=15, alignment=1)
TESTA_GRANDE = ParagraphStyle("testa_grande", parent=CELLA_GRANDE, fontName="Helvetica-Bold")
NOTA_GRANDE = ParagraphStyle("nota_grande", parent=CELLA_GRANDE, fontSize=10, leading=12.5,
                             textColor=colors.HexColor(MUTO))
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
            centro=frozenset(), totale: float | None = None, alternata: bool = True, regole=()) -> Table:
    """Tabella standard: intestazione in verde chiaro ripetuta a ogni pagina, righe alternate, griglia leggera.
    `larghezze` sono proporzioni, scalate su `totale` (di norma la larghezza utile della pagina orizzontale);
    `destra` e `centro`: indici delle colonne allineate a destra o al centro (intestazione compresa)."""
    totale = totale or larghezza()

    def stile(i: int, testa: bool) -> ParagraphStyle:
        if i in centro:
            return TESTA_CENTRO if testa else CELLA_CENTRO
        if i in destra:
            return TESTA_DESTRA if testa else CELLA_DESTRA
        return TESTA if testa else CELLA
    dati = [[p(t, stile(i, True)) for i, t in enumerate(intestazioni)]]
    for riga in righe:
        dati.append([c if isinstance(c, (Paragraph, list)) else p(c, stile(i, False)) for i, c in enumerate(riga)])
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


def stile_griglia(regole=(), *, centrata: bool = False) -> TableStyle:
    """Lo stile di base delle tabelle, per le griglie costruite a mano (tabellone, turni personali). `centrata`:
    testo in mezzo anche in verticale e celle più alte (griglie per giorno)."""
    margine = 6 if centrata else 4
    return TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GRIGLIA),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE" if centrata else "TOP"),
                       ("BACKGROUND", (0, 0), (-1, 0), TESTA_BG),
                       ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                       ("TOPPADDING", (0, 1), (-1, -1), margine), ("BOTTOMPADDING", (0, 1), (-1, -1), margine),
                       ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), *regole])


def documento(titolo: str, sottotitolo: str, blocchi: list, *, verticale: bool = False,
              avviso: str | None = None, legenda: str | None = None, adesso: datetime | None = None) -> bytes:
    """Il PDF finito: testata e piè di pagina comuni su ogni pagina. `avviso`: riquadro giallo nella testata, a
    destra del titolo, su ogni pagina (es. "Aggiornato con i cambi turno"): non sposta il contenuto, così lo
    stesso foglio con e senza avviso ha le stesse pagine. `legenda`: riga (in formato reportlab) in fondo a ogni
    pagina, sopra il piè di pagina (es. i colori del tabellone)."""
    pagina = A4 if verticale else landscape(A4)
    creato = (adesso or datetime.now(ZoneInfo("Europe/Rome"))).strftime("%d/%m/%Y alle %H:%M")
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=pagina, leftMargin=MARGINE, rightMargin=MARGINE,
                            topMargin=MARGINE + TESTATA, bottomMargin=MARGINE + (22 if legenda else 6),
                            title=titolo, author=ENTE)

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
        if avviso:
            stile = ParagraphStyle("avviso_testata", parent=TESTO, fontName="Helvetica-Bold", fontSize=10.5,
                                   leading=13, textColor=colors.HexColor(TESTO_COLORE))
            riquadro = Paragraph(escape(avviso), stile)
            largo = 300
            _, alto_testo = riquadro.wrap(largo - 16, 40)
            alto_box = alto_testo + 10
            x_box = w - MARGINE - largo
            canvas.setFillColor(AVVISO_BG)
            canvas.setStrokeColor(AVVISO_BORDO)
            canvas.setLineWidth(0.8)
            canvas.roundRect(x_box, alto - 4 - alto_box, largo, alto_box, 3, stroke=1, fill=1)
            riquadro.drawOn(canvas, x_box + 8, alto - 4 - alto_box + 5)
        canvas.setStrokeColor(colors.HexColor(VERDE))
        canvas.setLineWidth(1.2)
        canvas.line(MARGINE, alto - 47, w - MARGINE, alto - 47)
        canvas.setStrokeColor(GRIGLIA)
        canvas.setLineWidth(0.5)
        canvas.line(MARGINE, MARGINE + 2, w - MARGINE, MARGINE + 2)
        if legenda:
            riga = Paragraph(legenda, NOTA)
            riga.wrap(w - 2 * MARGINE, 20)
            riga.drawOn(canvas, MARGINE, MARGINE + 7)
        canvas.setFillColor(colors.HexColor(MUTO))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(MARGINE, MARGINE - 8, f"{ENTE} · {titolo} · creato il {creato}")
        canvas.drawRightString(w - MARGINE, MARGINE - 8, f"Pagina {_doc.page}")
        canvas.restoreState()

    contenuto = list(blocchi)
    doc.build(contenuto, onFirstPage=testata_e_pie, onLaterPages=testata_e_pie)
    return out.getvalue()
