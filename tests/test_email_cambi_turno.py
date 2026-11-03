"""Notifiche persistenti, esiti parziali e recupero senza doppi cambi."""
import json
from datetime import date
from email import message_from_string, policy
from io import BytesIO

from pypdf import PdfReader

from cvap import db
from .test_api_cambi_turno import scenario, conferma


def test_email_contiene_prima_dopo_avvisi_e_due_tabelloni(scenario):
    c, conn, postino, corpo, _ = scenario
    assert conferma(c, corpo).status_code == 200
    m = postino.messaggi[0]
    testo = m.get_body(preferencelist=('html',)).get_content()
    assert 'Anna' in testo and 'Bruno' in testo
    assert 'Segnalazioni' in testo and '2090-01-02' in testo and '2090-01-16' in testo
    pdf = PdfReader(BytesIO(list(m.iter_attachments())[0].get_payload(decode=True)))
    assert len(pdf.pages) >= 2
    assert any('2090-01-02' in p.extract_text() for p in pdf.pages)
    assert any('2090-01-16' in p.extract_text() for p in pdf.pages)


def test_reinvio_solo_destinatario_fallito_con_fotografia_originaria(scenario):
    c, conn, postino, corpo, _ = scenario
    db.crea_destinatario(conn, 'seconda@example.org', 'Seconda', ['turni'], True)
    postino.falliscono.add('seconda@example.org')
    vid = conferma(c, corpo).json()['id']
    originale = postino.messaggi[-1].as_string()
    with conn:
        conn.execute('UPDATE persone SET nome = ? WHERE id = ?', ('Nuovo nome', corpo['collega_id']))
    c.post('/api/accesso', json={'password': 'gestione'})
    postino.falliscono.clear()
    esito = c.post(f'/api/gestione-cambi-turno/{vid}/reinvia')
    assert esito.json()['notifica'] == 'inviata'
    assert [m['To'] for m in postino.messaggi] == ['capo@example.org', 'seconda@example.org', 'seconda@example.org']
    assert postino.messaggi[-1].as_string() == originale


def test_senza_smtp_o_destinatari_cambio_salvato_e_notifica_recuperabile(scenario):
    c, conn, postino, corpo, _ = scenario
    with conn:
        conn.execute('DELETE FROM destinatari_email')
    postino.configurato = False
    r = conferma(c, corpo)
    assert r.status_code == 200 and r.json()['notifica'] == 'da_reinviare'
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    db.crea_destinatario(conn, 'nuovacapo@example.org', 'Capo', ['turni'], True)
    postino.configurato = True
    c.post('/api/accesso', json={'password': 'gestione'})
    assert c.post(f"/api/gestione-cambi-turno/{r.json()['id']}/reinvia").json()['notifica'] == 'inviata'
    assert postino.messaggi[-1]['To'] == 'nuovacapo@example.org'


def test_errore_pdf_non_invia_messaggio_incompleto(scenario, monkeypatch):
    from cvap import pdf_cambi_turno
    c, conn, postino, corpo, _ = scenario
    def fallisce(*args):
        raise RuntimeError('PDF simulato')
    monkeypatch.setattr(pdf_cambi_turno, 'genera', fallisce)
    r = conferma(c, corpo)
    assert r.status_code == 200
    assert r.json()['notifica'] == 'da_reinviare'
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    assert not postino.messaggi


def test_rettifica_fallita_reinvio_e_vecchia_notifica_superata(scenario):
    from uuid import uuid4
    c, conn, postino, corpo, _ = scenario
    postino.falliscono.add('capo@example.org')
    vid = conferma(c, corpo).json()['id']
    c.post('/api/accesso', json={'password': 'gestione'})
    vista = c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento').json()
    r = c.post(f'/api/gestione-cambi-turno/{vid}/annulla', json={'versione': vista['versione'], 'chiave': str(uuid4())})
    assert r.json()['notifica'] == 'da_reinviare'
    assert r.json()['notifiche'][0]['stato'] == 'superata'
    postino.falliscono.clear()
    assert c.post(f'/api/gestione-cambi-turno/{vid}/reinvia').json()['notifica'] == 'inviata'
    assert 'Rettifica' in postino.messaggi[-1]['Subject']
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']


def test_pendente_sopravvive_riavvio_e_tentativo_interrotto(scenario):
    from fastapi.testclient import TestClient
    from cvap.app import create_app
    c, conn, postino, corpo, _ = scenario
    postino.configurato = False
    vid = conferma(c, corpo).json()['id']
    with conn:
        conn.execute("UPDATE notifiche_variazioni SET stato = 'in_invio', aggiornata_il = '2020-01-01T00:00:00+00:00'")
    path = conn.execute('PRAGMA database_list').fetchone()['file']
    nuovo = TestClient(create_app(path, password='gestione', postino=postino))
    nuovo.post('/api/accesso', json={'password': 'gestione'})
    postino.configurato = True
    assert nuovo.post(f'/api/gestione-cambi-turno/{vid}/reinvia').json()['notifica'] == 'inviata'
    assert len(postino.messaggi) == 1
