"""PDF settimanale generato sul server dagli stessi dati del tabellone email."""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

from . import email_turni as tabellone
from .modello import EXTRA


def genera(settimane, rettifica=False, *, prova=False):
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), rightMargin=22, leftMargin=22,
                            topMargin=22, bottomMargin=24,
                            title='TEST - Simulazione turni' if prova else 'Tabellone turni aggiornato')
    stile = getSampleStyleSheet()
    cella = ParagraphStyle('cella', fontName='Helvetica', fontSize=8, leading=11)
    def testo(s):
        return Paragraph(escape(str(s)).replace('\n', '<br/>'), cella)
    elementi = []
    for n, s in enumerate(settimane):
        if n:
            elementi.append(PageBreak())
        titolo = ('Rettifica - ' if rettifica else '') + f"Tabellone {s['inizio']} / {s['fine']}"
        if prova:
            titolo = 'TEST - Simulazione - ' + titolo
        elementi.extend([Paragraph(titolo, stile['Heading1']),
                          Paragraph(f"Settimana {s['tipo']} - {escape(s['stato'])}", stile['Normal']), Spacer(1, 10)])
        for posto in tabellone._postazioni(s):
            elementi.append(Paragraph(escape(posto), stile['Heading2']))
            righe = [(f, seg, ruolo, etichetta) for f, seg, ruolo, etichetta in tabellone._righe(posto)]
            dati = [[testo('Turno / ruolo')] + [testo(tabellone._dmy(g)) for g in s['giorni']]]
            for fascia, segmento, ruolo, etichetta in righe:
                celle = [testo(f'{etichetta}\n{ruolo}')]
                for g in s['giorni']:
                    persone, avvisi = tabellone._cella(s, posto, g, fascia, segmento, ruolo)
                    voci = [p['nome'] + (f" ({p['orario']})" if p['orario'] else '') for p in persone]
                    celle.append(testo('\n'.join(voci + avvisi) or '-'))
                dati.append(celle)
            elementi.extend([_tabella(dati), Spacer(1, 8)])
        for extra in s.get('extra', []):
            elementi.append(Paragraph(escape(f"{extra['data']} - {extra['nome']}"), stile['Heading2']))
            dati = [[testo('Turno / ruolo'), testo('Dipendenti e volontari')]]
            for ruolo in ('autista', 'soccorritore'):
                persone, avvisi = tabellone._cella(s, EXTRA, extra['data'], extra['fascia'], extra['segmento'], ruolo)
                ora = tabellone.orario_turno(extra['fascia'], extra['segmento'])
                dati.append([testo(f'{ora}\n{ruolo}'), testo('\n'.join([p['nome'] for p in persone] + avvisi) or '-')])
            elementi.extend([_tabella(dati), Spacer(1, 8)])
    def pagina(canvas, documento):
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(819, 12, f'CVAP - pagina {documento.page}')
    doc.build(elementi, onFirstPage=pagina, onLaterPages=pagina)
    return out.getvalue()


def _tabella(dati):
    larghezze = [110] + [(797 - 110) / (len(dati[0]) - 1)] * (len(dati[0]) - 1)
    tab = Table(dati, colWidths=larghezze, repeatRows=1, hAlign='LEFT')
    tab.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#b7c7c9')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e1efea')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f4f7f6')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return tab
