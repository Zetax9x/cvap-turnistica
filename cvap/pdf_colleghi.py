"""PDF «Con chi si lavora» (A4 orizzontale), dalla pagina Statistiche → Equità.

Prima una tabella incrociata dipendente × dipendente con i turni fatti insieme (gli zeri, «mai insieme», in rosso),
poi per ogni dipendente il dettaglio: con chi ha lavorato (dipendenti e volontari), quante volte di giorno e di
notte, l'ultima volta insieme e con quali colleghi non ha mai lavorato. Dati da `confronti.con_chi`.
"""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import email_turni as et
from .pdf_equita import _CELLA, _GRIGLIA, _H2, _H3, _NOTA, _TESTA, _TESTO, _TITOLO, LARGHEZZA, Markup, _p, _tabella

_MAI_BG = colors.HexColor("#fde2e1")  # caselle «mai insieme» (testo #9f1d1d)
_DIAGONALE = colors.HexColor("#e5e9ee")
_CENTRO = _CELLA.clone("centro", alignment=1)
_TESTA_CENTRO = _TESTA.clone("testa_centro", alignment=1)


def _data(iso: str) -> str:
    return et._dmy(iso)


def _matrice(dati: dict) -> list:
    dip = dati["dipendenti"]
    n = len(dip)
    if n < 2:
        return [_p("Servono almeno due dipendenti con turni nel periodo.", _TESTO)]
    numero = {d["persona_id"]: i + 1 for i, d in enumerate(dip)}
    testa = [_p("Dipendente", _TESTA)] + [_p(str(numero[d["persona_id"]]), _TESTA_CENTRO) for d in dip] + [
        _p("Mai insieme", _TESTA_CENTRO)]
    righe = [testa]
    stile = [("GRID", (0, 0), (-1, -1), 0.4, _GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(et.TESTA_BG)),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for r, a in enumerate(dip, start=1):
        riga = [_p(f"<b>{numero[a['persona_id']]}.</b> {escape(a['nome'])}"
                   + ("" if a["attivo"] else " <i>(non attivo)</i>"), _CELLA)]
        for c, b in enumerate(dip, start=1):
            if a["persona_id"] == b["persona_id"]:
                riga.append(_p("", _CENTRO))
                stile.append(("BACKGROUND", (c, r), (c, r), _DIAGONALE))
                continue
            v = dati["matrice"][str(a["persona_id"])][str(b["persona_id"])]
            if v:
                riga.append(_p(str(v), _CENTRO))
            else:  # mai insieme: in rosso
                riga.append(_p('<font color="#9f1d1d"><b>0</b></font>', _CENTRO))
                stile.append(("BACKGROUND", (c, r), (c, r), _MAI_BG))
        riga.append(_p(str(len(a["mai"])), _CENTRO))
        righe.append(riga)
    nome, mai = 130, 50
    cella = (LARGHEZZA - nome - mai) / n
    t = Table(righe, colWidths=[nome] + [cella] * n + [mai], repeatRows=1)
    t.setStyle(TableStyle(stile))
    return [t, Spacer(1, 4),
            _p("Ogni casella: turni fatti insieme (stesso giorno, stessa postazione, stessa fascia). Le colonne hanno "
               "gli stessi numeri delle righe. In rosso le coppie che non hanno mai lavorato insieme nel periodo.", _NOTA)]


def _scheda(d: dict) -> list:
    titolo = escape(d["nome"]) + ("" if d["attivo"] else " <i>(non attivo)</i>")
    dip = [c for c in d["colleghi"] if not c["volontario"]]
    vol = [c for c in d["colleghi"] if c["volontario"]]
    riassunto = (f"Turni nel periodo: <b>{d['turni']}</b> · in compagnia: <b>{d['in_compagnia']}</b> · "
                 f"colleghi dipendenti: <b>{len(dip)}</b> · volontari: <b>{len(vol)}</b>")
    out = [Paragraph(titolo, _H3), _p(riassunto, _TESTO), Spacer(1, 3)]

    def righe(lista):
        return [[Markup(f"<b>{escape(c['nome'])}</b>"), c["turni"], c["giorno"], c["notte"], f"{c['percentuale']}%",
                 _data(c["ultima"])] for c in lista]
    intestazioni = ["Turni insieme", "Di giorno", "Di notte", "% dei suoi turni", "Ultima volta insieme"]
    larghezze = [30, 12, 10, 10, 13, 16]
    if dip:
        out.append(_tabella(["Con i dipendenti", *intestazioni], righe(dip), larghezze, {1, 2, 3, 4}))
    if vol:
        out += [Spacer(1, 3), _tabella(["Con i volontari", *intestazioni], righe(vol), larghezze, {1, 2, 3, 4})]
    if not d["colleghi"]:
        out.append(_p("Nel periodo non ha mai lavorato con nessuno.", _TESTO))
    out.append(Spacer(1, 3))
    if d["mai"]:
        nomi = ", ".join(escape(m["nome"]) + ("" if m["attivo"] else " (non attivo)") for m in d["mai"])
        out.append(_p(f'<font color="#9f1d1d"><b>Mai insieme a ({len(d["mai"])}):</b></font> {nomi}.', _TESTO))
    else:
        out.append(_p("Ha lavorato almeno una volta con tutti i colleghi dipendenti.", _TESTO))
    return [KeepTogether(out), Spacer(1, 8)]


def genera_colleghi(dati: dict, periodo: str) -> bytes:
    """`dati`: `confronti.con_chi`; `periodo`: es. "dal 19/10/2026 al 15/11/2026"."""
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=20, bottomMargin=20,
                            title="Con chi si lavora", author="Croce Verde Ascoli Piceno")
    settimane = dati.get("settimane", [])
    intro = (f"{len(settimane)} {'settimana confermata' if len(settimane) == 1 else 'settimane confermate'} con turni "
             f"generati, {escape(periodo)}. Due persone «lavorano insieme» quando hanno un turno nello stesso giorno, "
             "nella stessa postazione e nella stessa fascia (giorno o notte), anche se uno dei due fa mezzo turno.")
    contenuto = [Paragraph("Con chi si lavora", _TITOLO), _p(intro, _TESTO), Spacer(1, 6)]
    if not dati.get("dipendenti"):
        contenuto.append(_p("Nessuna settimana confermata con turni generati nel periodo.", _TESTO))
    else:
        contenuto += [Paragraph("Tabella incrociata dei dipendenti", _H2), *_matrice(dati), PageBreak(),
                      Paragraph("Dettaglio per dipendente", _H2)]
        for d in dati["dipendenti"]:
            contenuto += _scheda(d)
    doc.build(contenuto, onFirstPage=_pie, onLaterPages=_pie)
    return out.getvalue()


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#4d5868"))
    canvas.drawCentredString(landscape(A4)[0] / 2, 10,
                             f"Croce Verde Ascoli Piceno · Con chi si lavora · pagina {doc.page}")
    canvas.restoreState()
