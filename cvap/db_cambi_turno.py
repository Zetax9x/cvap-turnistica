"""Registro dei cambi e coda persistente. Le scritture partecipano alla transazione del chiamante."""
import json
from contextlib import contextmanager

from fastapi import HTTPException


def codifica(dati):
    return json.dumps(dati, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@contextmanager
def transazione(conn):
    # BEGIN IMMEDIATE serializza anche istanze diverse del server SQLite/libSQL.
    with conn:
        conn.execute('BEGIN IMMEDIATE')
        yield


def revisione(conn, aid):
    r = conn.execute('SELECT MAX(id) AS n FROM revisioni_cambi_turno WHERE assegnazione_id = ?', (aid,)).fetchone()
    return r['n'] or 0


def variazione(conn, vid=None, chiave=None):
    if chiave is not None:
        r = conn.execute('SELECT * FROM variazioni_turno WHERE chiave = ?', (chiave,)).fetchone()
    else:
        r = conn.execute('SELECT * FROM variazioni_turno WHERE id = ?', (vid,)).fetchone()
    if not r:
        raise HTTPException(404, 'Cambio non trovato')
    return {**dict(r), 'dati': json.loads(r['dati']), 'rettifica': json.loads(r['rettifica']) if r['rettifica'] else None}


def notifiche(conn, vid):
    return [dict(r) for r in conn.execute(
        'SELECT id, tipo, destinatario, stato, tentativi, errore FROM notifiche_variazioni '
        'WHERE variazione_id = ? ORDER BY id', (vid,)).fetchall()]


def esito(conn, v, riservato=False):
    ns = notifiche(conn, v['id'])
    tipo = 'rettifica' if v['annullata_il'] else 'variazione'
    attuali = [n for n in ns if n['tipo'] == tipo]
    stato = 'inviata' if attuali and all(n['stato'] == 'inviata' for n in attuali) else 'da_reinviare'
    base = {'id': v['id'], 'creata_il': v['creata_il'], 'annullata_il': v['annullata_il'],
            'notifica': stato, 'riepilogo': v['dati']['riepilogo']}
    if riservato:
        base.update(dati=v['dati'], notifiche=ns, rettifica=v['rettifica'])
    return base


def prepara_notifiche(conn, vid, tipo, fotografia):
    responsabili = conn.execute('SELECT email FROM destinatari_email WHERE responsabile = 1 ORDER BY id').fetchall()
    # Anche senza destinatari la comunicazione resta persistente e visibile al gestionale.
    for email in sorted({r['email'].lower() for r in responsabili}) or ['']:
        conn.execute('INSERT INTO notifiche_variazioni(variazione_id, tipo, destinatario, fotografia) '
                     'VALUES (?, ?, ?, ?)', (vid, tipo, email, codifica(fotografia)))
