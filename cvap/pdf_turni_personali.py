"""PDF personale (allegato alle email dei turni e scaricabile da «Turni dipendente»): sette giorni in colonna,
con lo stile comune dei PDF (`pdf_stile`) e gli stessi colori del tabellone (giorno, notte, weekend, festività)."""
from datetime import date
from html import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, Table

from . import email_turni
from . import pdf_stile as st

_TURNO = ParagraphStyle("turno", parent=st.CELLA, fontSize=11.5, leading=15, alignment=1, spaceAfter=7)
_GIORNO = ParagraphStyle("giorno", parent=_TURNO, fontName="Helvetica-Bold", spaceAfter=0)
_RIPOSO = ParagraphStyle("riposo", parent=_TURNO, textColor=colors.HexColor(st.MUTO))


def genera(settimana: dict, persona: dict) -> bytes:
    giorni = email_turni.turni_personali(settimana, persona['id'], con_colleghi=True)
    titoli, celle = [], []
    regole = []
    for i, g in enumerate(giorni):
        d = date.fromisoformat(g['data'])
        feste = email_turni._nomi_feste(settimana, g['data'])
        testa = f"{email_turni.GIORNI[d.weekday()]}<br/>{email_turni._dm(g['data'])}"
        if feste:
            testa += f'<br/><font size="9" color="{email_turni.FESTIVO_TESTO}">{escape(feste)}</font>'
            regole.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(email_turni.FESTIVO_BG)))
        elif d.weekday() >= 5:
            regole.append(('BACKGROUND', (i, 0), (i, 0), colors.HexColor(email_turni.WEEKEND_BG)))
        titoli.append(Paragraph(testa, _GIORNO))
        contenuto = []
        for t in g['turni']:
            contenuto.append(Paragraph(
                f"<b>{escape(t['orario'])}</b><br/>{escape(t['postazione'])}<br/>"
                f"<font color=\"{st.MUTO}\">{escape(t['ruolo'])}</font>"
                + (f"<br/><font size=\"10\">Con {escape(t['colleghi'])}</font>" if t['colleghi'] else ''), _TURNO))
        if not contenuto:
            contenuto.append(Paragraph(escape(email_turni.stato_giorno(settimana, persona['id'], g)), _RIPOSO))
        celle.append(contenuto)
        if g['turni'] and all(t['fascia'] == 'notte' for t in g['turni']):
            regole.append(('BACKGROUND', (i, 1), (i, 1), colors.HexColor(email_turni.NOTTE_BG)))
        elif g['turni']:
            regole.append(('BACKGROUND', (i, 1), (i, 1), colors.HexColor(email_turni.GIORNO_BG)))
    larghezza = st.larghezza()
    tabella = Table([titoli, celle], colWidths=[larghezza / len(giorni)] * len(giorni), repeatRows=1)
    tabella.setStyle(st.stile_griglia([('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                                       *regole]))
    periodo = f"Settimana dal {email_turni._dmy(settimana['inizio'])} al {email_turni._dmy(settimana['fine'])}"
    legenda = Paragraph(f'<font backColor="{email_turni.GIORNO_BG}">&nbsp;Turno di giorno&nbsp;</font> &nbsp; '
                        f'<font backColor="{email_turni.NOTTE_BG}">&nbsp;Turno di notte&nbsp;</font> &nbsp; '
                        "«Con»: i colleghi dello stesso turno.", st.NOTA)
    return st.documento(f"Turni di {persona['nome']}", periodo, [tabella, Spacer(1, 6), legenda])
