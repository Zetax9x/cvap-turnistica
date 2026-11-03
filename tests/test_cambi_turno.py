"""Regole concordate, atomicità e modifiche concorrenti sui cambi turno."""
from datetime import date, datetime
from uuid import uuid4

import pytest

from cvap import db, cambi_turno
from cvap.modello import Assegnazione, segmento_extra
from .test_api_cambi_turno import scenario, anteprima, conferma


@pytest.mark.parametrize('fine,ammesso', [(21, True), (22, False)])
def test_soglia_11_ore_anche_settimana_precedente(scenario, fine, ammesso):
    c, conn, postino, corpo, _ = scenario
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 1), 'Assistenze ed Extra', 'giorno',
                                         segmento_extra(99, 12, fine), 'soccorritore', corpo['collega_id']))
    corpo = {**corpo, 'tipo': 'cessione', 'turno_ricevuto_id': None}
    vista = anteprima(c, corpo)
    assert bool(vista['errori']) is not ammesso
    r = conferma(c, corpo, vista)
    assert r.status_code == (200 if ammesso else 400), r.text
    if not ammesso:
        assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']
        assert not postino.messaggi


def test_blocca_riposo_dopo_turno_ricevuto_per_dichiarante(scenario):
    c, conn, _, corpo, _ = scenario
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 16), 'Acquasanta', 'notte', 'intero',
                                         'autista', corpo['persona_id']))
    vista = anteprima(c, corpo)
    assert any(v['persona_id'] == corpo['persona_id'] for v in vista['errori'])
    assert conferma(c, corpo, vista).status_code == 400


def test_sovrapposizione_assenza_ore_qualifica_sono_solo_avvisi(scenario):
    c, conn, _, corpo, _ = scenario
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), 'Venarotta', 'giorno', 'intero',
                                         'soccorritore', corpo['collega_id']))
    db.crea_ferie(conn, corpo['collega_id'], date(2090, 1, 2), date(2090, 1, 2))
    db.imposta_max_ore(conn, corpo['collega_id'], 1)
    vista = anteprima(c, corpo)
    codici = {v['codice'] for v in vista['avvisi']}
    assert {'sovrapposizione', 'ferie', 'qualifica', 'ore_max'} <= codici
    assert not vista['errori']
    assert conferma(c, corpo, vista).status_code == 200


def test_riposo_pregresso_non_coinvolto_non_blocca(scenario):
    c, conn, _, corpo, _ = scenario
    for fascia in ('giorno', 'notte'):
        db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 5), 'Venarotta', fascia, 'intero',
                                             'soccorritore', corpo['collega_id']))
    assert not anteprima(c, corpo)['errori']
    assert conferma(c, corpo).status_code == 200


def test_cambio_di_turni_non_ancora_iniziati_oggi(scenario, monkeypatch):
    c, conn, _, corpo, _ = scenario
    monkeypatch.setattr(cambi_turno, 'adesso', lambda: datetime(2090, 1, 2, 7, 59, tzinfo=cambi_turno.FUSO))
    turni = c.get('/api/cambi-turno/turni', params={'persona_id': corpo['persona_id']}).json()
    assert [t['id'] for t in turni] == [corpo['turno_id']]
    vista = anteprima(c, corpo)
    monkeypatch.setattr(cambi_turno, 'adesso', lambda: datetime(2090, 1, 2, 8, 0, tzinfo=cambi_turno.FUSO))
    assert c.get('/api/cambi-turno/turni', params={'persona_id': corpo['persona_id']}).json() == []
    assert conferma(c, corpo, vista).status_code == 400


def test_errore_durante_salvataggio_notifica_fa_rollback_di_entrambi(scenario, monkeypatch):
    from cvap import db_cambi_turno
    c, conn, postino, corpo, _ = scenario
    vista = anteprima(c, corpo)
    def fallisce(*args):
        raise RuntimeError('Errore database simulato')
    monkeypatch.setattr(db_cambi_turno, 'prepara_notifiche', fallisce)
    with pytest.raises(RuntimeError, match='Errore database simulato'):
        conferma(c, corpo, vista)
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']
    assert db.get_assegnazione(conn, corpo['turno_ricevuto_id']).persona_id == corpo['collega_id']
    assert conn.execute('SELECT COUNT(*) AS n FROM variazioni_turno').fetchone()['n'] == 0
    assert not postino.messaggi


def test_due_richieste_contemporanee_sullo_stesso_turno(scenario):
    from concurrent.futures import ThreadPoolExecutor
    c, conn, _, corpo, _ = scenario
    vista = anteprima(c, corpo)
    with ThreadPoolExecutor(max_workers=2) as executor:
        rs = list(executor.map(lambda _: conferma(c, corpo, vista), range(2)))
    assert sorted(r.status_code for r in rs) == [200, 409]
    assert conn.execute('SELECT COUNT(*) AS n FROM variazioni_turno').fetchone()['n'] == 1


def test_annullamento_scambio_ripristina_entrambi_e_blocco(scenario):
    c, conn, _, corpo, _ = scenario
    r = conferma(c, corpo)
    vid = r.json()['id']
    c.post('/api/accesso', json={'password': 'gestione'})
    vista = c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento').json()
    r = c.post(f'/api/gestione-cambi-turno/{vid}/annulla', json={'versione': vista['versione'], 'chiave': str(uuid4())})
    assert r.status_code == 200, r.text
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']
    assert db.get_assegnazione(conn, corpo['turno_ricevuto_id']).persona_id == corpo['collega_id']
    assert db.get_settimana(conn, date(2090, 1, 2))['stato'] == 'confermata'


def test_annullamento_rileva_modifica_poi_ripristino_e_id_riusato(scenario):
    c, conn, _, corpo, _ = scenario
    vid = conferma(c, corpo).json()['id']
    with conn:
        conn.execute('UPDATE assegnazioni SET persona_id = ? WHERE id = ?', (corpo['persona_id'], corpo['turno_id']))
        conn.execute('UPDATE assegnazioni SET persona_id = ? WHERE id = ?', (corpo['collega_id'], corpo['turno_id']))
    c.post('/api/accesso', json={'password': 'gestione'})
    assert c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento').status_code == 409


def test_variazione_ricalcola_ore_senza_creare_straordinario(scenario):
    c, _, _, corpo, _ = scenario
    corpo = {**corpo, 'tipo': 'cessione', 'turno_ricevuto_id': None}
    assert conferma(c, corpo).status_code == 200
    c.post('/api/accesso', json={'password': 'gestione'})
    tabellone = c.get('/api/settimane/2090-01-02').json()
    persone = {p['persona_id']: p for p in tabellone['riepilogo']}
    assert persone[corpo['persona_id']]['ore'] == 0
    assert persone[corpo['collega_id']]['ore'] == 12
    assert persone[corpo['collega_id']]['ore_sostituzioni'] == 0


def test_non_dipendenti_e_stessa_persona_rifiutati(scenario):
    c, conn, _, corpo, _ = scenario
    volontario = next(p['id'] for p in db.lista_persone(conn) if p['tipo'] == 'volontario')
    assert c.post('/api/cambi-turno/anteprima', json={**corpo, 'collega_id': volontario}).status_code == 400
    assert c.post('/api/cambi-turno/anteprima', json={**corpo, 'collega_id': corpo['persona_id']}).status_code == 400


def test_errore_11_ore_introdotto_dopo_anteprima_impedisce_conferma(scenario):
    c, conn, _, corpo, _ = scenario
    vista = anteprima(c, corpo)
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 1), 'Acquasanta', 'notte', 'intero', 'soccorritore', corpo['collega_id']))
    assert conferma(c, corpo, vista).status_code == 409
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['persona_id']


def test_dipendente_disattivato_non_filtrato_e_qualifica_segnalata(scenario):
    c, conn, _, corpo, _ = scenario
    with conn:
        conn.execute('UPDATE persone SET attivo = 0 WHERE id = ?', (corpo['collega_id'],))
    assert any(p['id'] == corpo['collega_id'] for p in c.get('/api/cambi-turno/dipendenti').json())
    vista = anteprima(c, corpo)
    assert any(a['codice'] == 'qualifica' for a in vista['avvisi'])


def test_annullamento_non_bloccato_da_semplice_correzione_del_nome(scenario):
    c, conn, _, corpo, _ = scenario
    vid = conferma(c, corpo).json()['id']
    with conn:
        conn.execute('UPDATE persone SET nome = ? WHERE id = ?', ('Bruno corretto', corpo['collega_id']))
    c.post('/api/accesso', json={'password': 'gestione'})
    r = c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento')
    assert r.status_code == 200, r.text


def test_annullamento_blocca_riposo_insufficiente_nel_ripristino(scenario):
    c, conn, postino, corpo, _ = scenario
    vid = conferma(c, corpo).json()['id']
    db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 1), 'Acquasanta', 'notte',
                                         'intero', 'autista', corpo['persona_id']))
    c.post('/api/accesso', json={'password': 'gestione'})
    vista = c.post(f'/api/gestione-cambi-turno/{vid}/anteprima-annullamento').json()
    assert any(e['codice'] == 'riposo' for e in vista['errori'])
    r = c.post(f'/api/gestione-cambi-turno/{vid}/annulla',
               json={'versione': vista['versione'], 'chiave': str(uuid4())})
    assert r.status_code == 400, r.text
    assert db.get_assegnazione(conn, corpo['turno_id']).persona_id == corpo['collega_id']
    assert len(postino.messaggi) == 1


def test_turni_in_bozza_visibili_e_modificabili(scenario):
    c, conn, _, corpo, _ = scenario
    db.imposta_stato(conn, date(2090, 1, 2), 'bozza')
    turni = c.get('/api/cambi-turno/turni', params={'persona_id': corpo['persona_id']}).json()
    assert [t['id'] for t in turni] == [corpo['turno_id']]
    assert conferma(c, corpo).status_code == 200
    assert db.get_settimana(conn, date(2090, 1, 2))['stato'] == 'bozza'


def test_transazione_e_registro_con_adattatore_libsql_locale(tmp_path, monkeypatch):
    libsql = pytest.importorskip('libsql')
    from cvap.app import _dati_settimana, payload_settimana
    monkeypatch.setattr(db, 'apri', lambda path: db._ConnessioneLibsql(libsql.connect(path)))
    conn = db.connetti(str(tmp_path / 'libsql.db'))
    try:
        a = db.crea_persona(conn, 'Anna', 'dipendente', 'autista')['id']
        b = db.crea_persona(conn, 'Bruno', 'dipendente', 'autista')['id']
        aid = db.crea_assegnazione(conn, Assegnazione(date(2090, 1, 2), 'Acquasanta',
                                                     'giorno', 'intero', 'autista', a))
        corpo = {'tipo': 'cessione', 'persona_id': a, 'collega_id': b, 'turno_id': aid,
                 'turno_ricevuto_id': None}
        vista = cambi_turno.anteprima(conn, corpo, _dati_settimana)
        richiesta = {**corpo, 'versione': vista['versione'], 'chiave': str(uuid4())}
        v = cambi_turno.conferma(conn, richiesta, _dati_settimana, payload_settimana)
        assert db.get_assegnazione(conn, aid).persona_id == b
        assert cambi_turno.conferma(conn, richiesta, _dati_settimana, payload_settimana)['id'] == v['id']
        vista = cambi_turno.anteprima_annullamento(conn, v['id'], _dati_settimana)
        cambi_turno.annulla(conn, v['id'], {'versione': vista['versione'], 'chiave': str(uuid4())},
                            _dati_settimana, payload_settimana)
        assert db.get_assegnazione(conn, aid).persona_id == a
    finally:
        conn.close()
