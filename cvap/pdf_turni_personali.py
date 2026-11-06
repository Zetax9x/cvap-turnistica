"""PDF personale: sette giorni in colonna, come la stampa della pagina Dipendenti."""
from datetime import date
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer

from . import email_turni


def genera(settimana: dict, persona: dict) -> bytes:
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=20, rightMargin=20,
                            topMargin=24, bottomMargin=24, title=f"Turni di {persona['nome']}")
    stili = getSampleStyleSheet()
    normale = ParagraphStyle('turno', fontName='Helvetica', fontSize=11, leading=15,
                             alignment=1, spaceAfter=5)
    intestazione = ParagraphStyle('giorno', parent=normale, fontName='Helvetica-Bold')
    giorni = email_turni.turni_personali(settimana, persona['id'], con_colleghi=True)
    titoli, celle = [], []
    for g in giorni:
        indice = date.fromisoformat(g['data']).weekday()
        titoli.append(Paragraph(f"{email_turni.GIORNI[indice]}<br/>{email_turni._dm(g['data'])}", intestazione))
        contenuto = []
        for t in g['turni']:
            contenuto.append(Paragraph(
                f"<b>{escape(t['orario'])}</b><br/><b>{escape(t['postazione'])}</b><br/>"
                f"{escape(t['ruolo'])}"
                + (f"<br/>Con {escape(t['colleghi'])}" if t['colleghi'] else ''), normale))
        if not contenuto:
            etichetta = email_turni.stato_giorno(settimana, persona['id'], g)
            contenuto.append(Paragraph(etichetta, normale))
        celle.append(contenuto)
    tabella = Table([titoli, celle], colWidths=[doc.width / len(giorni)] * len(giorni), repeatRows=1)
    regole = [('GRID', (0, 0), (-1, -1), .7, colors.HexColor('#555555')),
              ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#aac6f2')),
              ('VALIGN', (0, 0), (-1, -1), 'TOP'),
              ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]
    for i, g in enumerate(giorni):
        if date.fromisoformat(g['data']).weekday() >= 5:
            regole.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor('#c79cc2')))
        if g['turni'] and all(t['fascia'] == 'notte' for t in g['turni']):
            regole.append(('BACKGROUND', (i, 1), (i, 1), colors.HexColor('#eef1fc')))
        elif g['turni']:
            regole.append(('BACKGROUND', (i, 1), (i, 1), colors.HexColor('#fff8de')))
    tabella.setStyle(TableStyle(regole))
    doc.build([Paragraph(escape(persona['nome']), stili['Title']),
               Paragraph(f"Turni dal {email_turni._dmy(settimana['inizio'])} "
                         f"al {email_turni._dmy(settimana['fine'])}", stili['Heading2']),
               Spacer(1, 12), tabella])
    return out.getvalue()
