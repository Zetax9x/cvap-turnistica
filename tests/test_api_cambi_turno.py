"""Percorso reale dei cambi, con database temporaneo e postino simulato."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from cvap import db
from cvap.app import create_app
from cvap.modello import Assegnazione


class Postino:
    configurato = True

    def __init__(self):
        self.messaggi = []
        self.falliscono = set()

    def invia(self, messaggi):
        self.messaggi.extend(messaggi)
        return {m['To']: 'Errore simulato' if m['To'] in self.falliscono else None for m in messaggi}


@pytest.fixture
def scenario(tmp_path):
    path = str(tmp_path / 'cambi.db')
    postino = Postino()
    client = TestClient(create_app(path, password='gestione', postino=postino))
    conn = db.apri(path)
    a = db.crea_persona(conn, 'Anna', 'dipendente', 'autista', email='anna@example.org')['id']
    b = db.crea_persona(conn, 'Bruno', 'dipendente', 'autista', email='bruno@example.org')['id']
    db.crea_persona(conn, 'Volontario', 'volontario', 'autista')
    db.crea_destinatario(conn, 'capo@example.org', 'Responsabile', ['turni'], True)
    primo = db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), 'Acquasanta', 'giorno', 'intero', 'autista', a))
    secondo = db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 16), 'Venarotta', 'giorno', 'intero', 'soccorritore', b))
    db.imposta_stato(conn, date(2090, 1, 2), 'confermata')
    passato = db.crea_assegnazione(conn, Assegnazione(date(2020, 1, 2), 'Acquasanta', 'giorno', 'intero', 'autista', a))
    yield client, conn, postino, {'tipo': 'scambio', 'persona_id': a, 'collega_id': b,
                                 'turno_id': primo, 'turno_ricevuto_id': secondo}, passato
    conn.close()


def anteprima(client, corpo):
    r = client.post('/api/cambi-turno/anteprima', json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def conferma(client, corpo, vista=None, chiave=None):
    vista = vista or anteprima(client, corpo)
    return client.post('/api/cambi-turno/conferme', json={**corpo, 'versione': vista['versione'],
                                                        'chiave': chiave or str(uuid4())})


def test_accesso_pubblico_limitato_e_turni_futuri(scenario):
    c, conn, _, corpo, passato = scenario
    r = c.get('/api/cambi-turno/dipendenti')
    assert r.status_code == 200
    assert [x['nome'] for x in r.json()] == ['Anna', 'Bruno']
    assert all(set(x) == {'id', 'nome'} for x in r.json())
    turni = c.get('/api/cambi-turno/turni', params={'persona_id': corpo['persona_id']}).json()
    assert [x['id'] for x in turni] == [corpo['turno_id']]
    assert passato not in [x['id'] for x in turni]
    assert c.get('/api/persone').status_code == 401
    assert c.get('/api/gestione-cambi-turno').status_code == 401
    assert c.get('/cambio-turno').status_code == 200


def test_scambio_settimane_bloccate_email_e_idempotenza(scenario):
    c, conn, postino, corpo, _ = scenario
    vista = anteprima(c, corpo)
    assert not vista['errori']
    assert not any(v['codice'] == 'qualifica' for v in vista['avvisi'])
    chiave = str(uuid4())
    r = conferma(c, corpo, vista, chiave)
    assert r.status_code == 200, r.text
    esito = r.json()
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    assert db.get_assegnazione(conn, corpo['turno_ricevuto_id']).persona_id == corpo['persona_id']
    assert db.get_assegnazione(conn, corpo['turno_id']).origine == 'generato'
    assert db.get_settimana(conn, date(2090, 1, 2))['stato'] == 'confermata'
    assert conferma(c, corpo, vista, chiave).json()['id'] == esito['id']
    assert len(postino.messaggi) == 1
    assert postino.messaggi[0]['To'] == 'capo@example.org'
    assert list(postino.messaggi[0].iter_attachments())[0].get_content_type() == 'application/pdf'
    assert c.get('/api/cambi-turno/conferme/' + chiave).json()['id'] == esito['id']


def test_conflitto_non_sovrascrive_e_niente_email(scenario):
    c, conn, postino, corpo, _ = scenario
    vista = anteprima(c, corpo)
    with conn:
        conn.execute('UPDATE assegnazioni SET origine = ? WHERE id = ?', ('manuale', corpo['turno_id']))
    r = conferma(c, corpo, vista)
    assert r.status_code == 409
    assert db.get_assegnazione(conn, corpo['turno_ricevuto_id']).persona_id == corpo['collega_id']
    assert not postino.messaggi


def test_cessione_errore_email_reinvio_e_annullamento(scenario):
    c, conn, postino, corpo, _ = scenario
    corpo = {**corpo, 'tipo': 'cessione', 'turno_ricevuto_id': None}
    postino.falliscono.add('capo@example.org')
    r = conferma(c, corpo)
    assert r.status_code == 200, r.text
    variazione = r.json()
    assert variazione['notifica'] == 'da_reinviare'
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    c.post('/api/accesso', json={'password': 'gestione'})
    registro = c.get('/api/gestione-cambi-turno').json()
    assert registro[0]['id'] == variazione['id']
    postino.falliscono.clear()
    assert c.post(f"/api/gestione-cambi-turno/{variazione['id']}/reinvia").json()['notifica'] == 'inviata'
    vista = c.post(f"/api/gestione-cambi-turno/{variazione['id']}/anteprima-annullamento").json()
    dati = {'versione': vista['versione'], 'chiave': str(uuid4())}
    r = c.post(f"/api/gestione-cambi-turno/{variazione['id']}/annulla", json=dati)
    assert r.status_code == 200, r.text
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']
    assert 'Cambio turno annullato' in postino.messaggi[-1]['Subject']
    n = len(postino.messaggi)
    assert c.post(f"/api/gestione-cambi-turno/{variazione['id']}/annulla", json=dati).status_code == 200
    assert len(postino.messaggi) == n


def test_annullamento_bloccato_se_turno_modificato(scenario):
    c, conn, _, corpo, _ = scenario
    r = conferma(c, corpo)
    assert r.status_code == 200, r.text
    vid = r.json()['id']
    with conn:
        conn.execute('UPDATE assegnazioni SET origine = ? WHERE id = ?', ('manuale', corpo['turno_id']))
    c.post('/api/accesso', json={'password': 'gestione'})
    assert c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento').status_code == 409
