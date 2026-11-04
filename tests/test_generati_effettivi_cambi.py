"""I cambi operativi non riscrivono il programma usato dal generatore."""
from datetime import date
from uuid import uuid4

import pytest

from cvap import db
from .test_api_cambi_turno import scenario, conferma


def cessione(corpo):
    return {**corpo, 'tipo': 'cessione', 'turno_ricevuto_id': None}


def accesso(client):
    assert client.post('/api/accesso', json={'password': 'gestione'}).status_code == 200


def annulla(client, vid):
    vista = client.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento')
    assert vista.status_code == 200, vista.text
    return client.post(f'/api/gestione-cambi-turno/{vid}/annulla',
                       json={'versione': vista.json()['versione'], 'chiave': str(uuid4())})


@pytest.mark.parametrize('tipo', ['cessione', 'scambio'])
def test_base_invariata_dopo_cambio_e_annullamento(scenario, tipo):
    client, conn, _, corpo, _ = scenario
    ids = [corpo['turno_id'], corpo['turno_ricevuto_id']]
    prima = [db.get_assegnazione(conn, aid, versione='generati') for aid in ids]
    richiesta = cessione(corpo) if tipo == 'cessione' else corpo
    risposta = conferma(client, richiesta)
    assert risposta.status_code == 200, risposta.text
    assert [db.get_assegnazione(conn, aid, versione='generati') for aid in ids] == prima
    assert db.get_assegnazione(conn, ids[0]).persona_id == corpo['collega_id']
    accesso(client)
    assert annulla(client, risposta.json()['id']).status_code == 200
    assert [db.get_assegnazione(conn, aid, versione='generati') for aid in ids] == prima
    assert [db.get_assegnazione(conn, aid) for aid in ids] == prima


def test_elenco_pubblico_segue_solo_titolari_effettivi(scenario):
    client, _, _, corpo, _ = scenario
    assert conferma(client, cessione(corpo)).status_code == 200
    propri = client.get('/api/cambi-turno/turni', params={'persona_id': corpo['persona_id']}).json()
    collega = client.get('/api/cambi-turno/turni', params={'persona_id': corpo['collega_id']}).json()
    assert propri == []
    assert {t['id'] for t in collega} == {corpo['turno_id'], corpo['turno_ricevuto_id']}
    filtrati = client.get('/api/cambi-turno/turni', params={
        'persona_id': corpo['collega_id'], 'settimana': '2090-01-02'}).json()
    assert [t['id'] for t in filtrati] == [corpo['turno_id']]


def test_cancellazione_effettiva_blocca_vecchio_annullamento(scenario):
    client, conn, _, corpo, _ = scenario
    risposta = conferma(client, cessione(corpo))
    assert risposta.status_code == 200
    db.elimina_assegnazione(conn, corpo['turno_id'])
    assert db.get_assegnazione(conn, corpo['turno_id']) is None
    assert db.get_assegnazione(conn, corpo['turno_id'], versione='generati').persona_id == corpo['persona_id']
    accesso(client)
    assert client.post(f"/api/gestione-cambi-turno/{risposta.json()['id']}/anteprima-annullamento").status_code == 409


@pytest.mark.parametrize('titolare', ['originale', 'effettivo'])
def test_malattia_distingue_titolare_originale_da_effettivo(scenario, titolare):
    client, conn, _, corpo, _ = scenario
    risposta = conferma(client, cessione(corpo))
    assert risposta.status_code == 200
    pid = corpo['persona_id'] if titolare == 'originale' else corpo['collega_id']
    accesso(client)
    assenza = client.post('/api/ferie', json={
        'persona_id': pid, 'dal': '2090-01-02', 'al': '2090-01-02', 'motivo': 'malattia'})
    assert assenza.status_code == 201, assenza.text
    originale = db.get_assegnazione(conn, corpo['turno_id'], versione='generati')
    effettivo = db.get_assegnazione(conn, corpo['turno_id'])
    if titolare == 'originale':
        assert originale is None
        assert effettivo.persona_id == corpo['collega_id']
    else:
        assert originale.persona_id == corpo['persona_id']
        assert effettivo is None
    assert client.post(f"/api/gestione-cambi-turno/{risposta.json()['id']}/anteprima-annullamento").status_code == 409
    assert client.delete(f"/api/ferie/{assenza.json()['id']}").status_code == 204
    assert db.get_assegnazione(conn, corpo['turno_id'], versione='generati') == originale
    assert db.get_assegnazione(conn, corpo['turno_id']) == effettivo


def test_seconda_cessione_non_riscrive_base_e_invalida_undo_precedente(scenario):
    client, conn, _, corpo, _ = scenario
    primo = conferma(client, cessione(corpo))
    assert primo.status_code == 200
    ritorno = {**cessione(corpo), 'persona_id': corpo['collega_id'], 'collega_id': corpo['persona_id']}
    secondo = conferma(client, ritorno)
    assert secondo.status_code == 200, secondo.text
    assert db.get_assegnazione(conn, corpo['turno_id'], versione='generati').persona_id == corpo['persona_id']
    accesso(client)
    assert client.post(f"/api/gestione-cambi-turno/{primo.json()['id']}/anteprima-annullamento").status_code == 409
    assert annulla(client, secondo.json()['id']).status_code == 200
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    assert db.get_assegnazione(conn, corpo['turno_id'], versione='generati').persona_id == corpo['persona_id']


def test_errore_sul_secondo_trasferimento_annulla_primo_e_revisioni(scenario, monkeypatch):
    client, conn, postino, corpo, _ = scenario
    dal, al = date(2090, 1, 1), date(2090, 1, 31)
    prima = db.assegnazioni_periodo(conn, dal, al)
    revisione = conn.execute('SELECT MAX(id) AS n FROM revisioni_cambi_turno').fetchone()['n']
    originale = db.imposta_titolare_effettivo
    chiamate = []

    def fallisce_al_secondo(connessione, aid, pid):
        chiamate.append(aid)
        if len(chiamate) == 2:
            raise RuntimeError('Secondo trasferimento fallito')
        originale(connessione, aid, pid)

    monkeypatch.setattr(db, 'imposta_titolare_effettivo', fallisce_al_secondo)
    with pytest.raises(RuntimeError, match='Secondo trasferimento fallito'):
        conferma(client, corpo)
    assert db.assegnazioni_periodo(conn, dal, al) == prima
    assert db.assegnazioni_periodo(conn, dal, al, versione='generati') == prima
    assert conn.execute('SELECT MAX(id) AS n FROM revisioni_cambi_turno').fetchone()['n'] == revisione
    assert conn.execute('SELECT COUNT(*) AS n FROM variazioni_turno').fetchone()['n'] == 0
    assert not postino.messaggi


@pytest.mark.parametrize('cancellato', [False, True])
def test_rigenerazione_bloccata_con_cambio_attivo_anche_se_cancellato(scenario, monkeypatch, cancellato):
    from cvap import solver

    client, conn, _, corpo, _ = scenario
    assert conferma(client, cessione(corpo)).status_code == 200
    accesso(client)
    assert client.post('/api/settimane/2090-01-02/riapri').status_code == 200
    if cancellato:
        assert client.delete(f"/api/assegnazioni/{corpo['turno_id']}").status_code == 204

    def non_deve_generare(*args, **kwargs):
        raise AssertionError('La settimana con cambio attivo non deve raggiungere il solver')

    monkeypatch.setattr(solver, 'genera', non_deve_generare)
    risposta = client.post('/api/settimane/2090-01-02/genera', json={})
    assert risposta.status_code == 409, risposta.text
    assert 'cambi turno' in risposta.json()['detail']
    assert db.get_assegnazione(conn, corpo['turno_id'], versione='generati').persona_id == corpo['persona_id']


def test_rigenerazione_consentita_dopo_annullamento_cambio(scenario, monkeypatch):
    from cvap import solver

    client, _, _, corpo, _ = scenario
    cambio = conferma(client, cessione(corpo))
    assert cambio.status_code == 200
    accesso(client)
    assert annulla(client, cambio.json()['id']).status_code == 200
    assert client.post('/api/settimane/2090-01-02/riapri').status_code == 200
    chiamate = []

    def genera_simulato(*args, **kwargs):
        chiamate.append(args[0])
        return solver.Risultato(stato='ottimo')

    monkeypatch.setattr(solver, 'genera', genera_simulato)
    risposta = client.post('/api/settimane/2090-01-02/genera', json={})
    assert risposta.status_code == 200, risposta.text
    assert len(chiamate) == 1


def test_sostituzione_responsabile_dopo_cessione_modifica_entrambe(scenario):
    client, conn, _, corpo, _ = scenario
    cambio = conferma(client, cessione(corpo))
    assert cambio.status_code == 200
    accesso(client)
    assert client.post('/api/settimane/2090-01-02/riapri').status_code == 200
    risposta = client.post(f"/api/assegnazioni/{corpo['turno_id']}/sostituisci",
                           json={'persona_id': corpo['persona_id']})
    assert risposta.status_code == 200, risposta.text
    giorno = date(2090, 1, 2)
    generati = db.assegnazioni_periodo(conn, giorno, giorno, versione='generati')
    assert len(generati) == 1
    assert generati == db.assegnazioni_periodo(conn, giorno, giorno)
    assert generati[0][1].persona_id == corpo['persona_id']
    assert client.post(f"/api/gestione-cambi-turno/{cambio.json()['id']}/anteprima-annullamento").status_code == 409
