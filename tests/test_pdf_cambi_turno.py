"""Contenuto reale degli allegati PDF, inclusi servizi extra e rettifiche."""
from datetime import date
from io import BytesIO

from pypdf import PdfReader

from cvap import db, pdf_cambi_turno
from cvap.app import payload_settimana
from cvap.modello import Assegnazione
from .test_api_cambi_turno import scenario


def test_pdf_servizi_ordinari_extra_e_rettifica(scenario):
    _, conn, _, corpo, _ = scenario
    db.crea_extra(conn, date(2090, 1, 2), 'Assistenza partita', 16, 20, 1, 0)
    extra = db.extra_periodo(conn, date(2090, 1, 2), date(2090, 1, 2))[0]
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), 'Assistenze ed Extra', extra['fascia'],
                                         extra['segmento'], 'autista', corpo['persona_id']))
    s = payload_settimana(conn, date(2090, 1, 2))
    pdf = pdf_cambi_turno.genera([s], rettifica=True)
    assert pdf.startswith(b'%PDF-')
    testo = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
    assert all(x in testo for x in ['Rettifica', 'Anna', 'Acquasanta', 'Venarotta', 'Assistenza partita', '16', '20'])
