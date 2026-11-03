"""La prova invia solo a Yuri e non registra né applica il cambio simulato."""
from datetime import date
from io import BytesIO
import time

import pytest
from pypdf import PdfReader

from cvap import db, email_cambi_turno, pdf_cambi_turno
from cvap.modello import Assegnazione
from .test_api_cambi_turno import scenario, anteprima, conferma


DESTINATARIO = 'squarciayuri@gmail.com'


def fotografia_db(conn):
    return {tabella: [dict(r) for r in conn.execute(f'SELECT * FROM {tabella} ORDER BY rowid').fetchall()]
            for tabella in ('assegnazioni', 'settimane', 'variazioni_turno',
                            'notifiche_variazioni', 'revisioni_cambi_turno')}


def prova(c, corpo, vista=None):
    vista = vista or anteprima(c, corpo)
    return c.post('/api/cambi-turno/email/prova',
                  json={**corpo, 'versione': vista['versione'], 'indirizzo': 'altro@example.org'})


@pytest.mark.parametrize('tipo', ['scambio', 'cessione'])
@pytest.mark.parametrize('attivi', [True, False])
def test_prova_simula_tabellone_pdf_senza_modificare_dati(scenario, monkeypatch, tipo, attivi):
    c, conn, postino, corpo, _ = scenario
    if not attivi:
        with conn:
            conn.execute('UPDATE persone SET attivo = 0')
    if tipo == 'cessione':
        corpo = {**corpo, 'tipo': tipo, 'turno_ricevuto_id': None}
    prima = fotografia_db(conn)
    foto = []
    componi = email_cambi_turno.componi
    def cattura(f, *args, **kwargs):
        foto.append(f)
        return componi(f, *args, **kwargs)
    monkeypatch.setattr(email_cambi_turno, 'componi', cattura)
    r = prova(c, corpo)
    assert r.status_code == 200, r.text
    assert r.json()['inviata_a'] == DESTINATARIO
    assert fotografia_db(conn) == prima
    assert len(postino.messaggi) == 1
    m = postino.messaggi[0]
    assert m['To'] == DESTINATARIO and m['Cc'] is None and m['Bcc'] is None
    assert m['Subject'].startswith('TEST')
    assert 'non è stato registrato' in m.get_body(preferencelist=('plain',)).get_content()
    assert 'simulazione' in m.get_body(preferencelist=('html',)).get_content().lower()
    turni = {a['id']: a for s in foto[0]['settimane'] for a in s['assegnazioni']}
    assert turni[corpo['turno_id']]['persona_id'] == corpo['collega_id']
    if tipo == 'scambio':
        assert turni[corpo['turno_ricevuto_id']]['persona_id'] == corpo['persona_id']
    allegato = list(m.iter_attachments())[0]
    assert allegato.get_content_type() == 'application/pdf'
    pdf = PdfReader(BytesIO(allegato.get_payload(decode=True)))
    testo = '\n'.join(p.extract_text() for p in pdf.pages)
    assert 'TEST' in testo and 'Bruno' in pdf.pages[0].extract_text()
    assert 'Anna' not in pdf.pages[0].extract_text()
    if tipo == 'scambio':
        assert len(pdf.pages) >= 2 and '2090-01-16' in testo
    # La prova non consuma la conferma: il normale invio continua ai responsabili.
    assert conferma(c, corpo).status_code == 200
    assert postino.messaggi[-1]['To'] == 'capo@example.org'
    assert not postino.messaggi[-1]['Subject'].startswith('TEST')
    assert foto[0]['settimane'] == foto[1]['settimane']


@pytest.mark.parametrize('guasto', ['configurazione', 'smtp', 'pdf'])
def test_errore_prova_non_modifica_tabellone_o_registro(scenario, monkeypatch, guasto):
    c, conn, postino, corpo, _ = scenario
    prima = fotografia_db(conn)
    if guasto == 'configurazione':
        postino.configurato = False
    elif guasto == 'smtp':
        postino.falliscono.add(DESTINATARIO)
    else:
        def fallisce(*args, **kwargs):
            raise RuntimeError('Errore PDF simulato')
        monkeypatch.setattr(pdf_cambi_turno, 'genera', fallisce)
    r = prova(c, corpo)
    assert r.status_code == (400 if guasto == 'configurazione' else 502), r.text
    assert fotografia_db(conn) == prima
    if guasto != 'smtp':
        assert not postino.messaggi


def test_prova_ricontrolla_versione_e_sovrapposizioni(scenario):
    c, conn, postino, corpo, _ = scenario
    vista = anteprima(c, corpo)
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), 'Venarotta', 'giorno', 'intero',
                                         'soccorritore', corpo['collega_id']))
    prima = fotografia_db(conn)
    assert prova(c, corpo, vista).status_code == 409
    assert prova(c, corpo).status_code == 400
    assert fotografia_db(conn) == prima
    assert not postino.messaggi


def test_prova_rispetta_limite_email_esistente(scenario):
    c, conn, postino, corpo, _ = scenario
    for _ in range(10):
        assert db.registra_prova_email(conn, time.time(), 10, 3600)
    prima = fotografia_db(conn)
    assert prova(c, corpo).status_code == 429
    assert fotografia_db(conn) == prima
    assert not postino.messaggi
