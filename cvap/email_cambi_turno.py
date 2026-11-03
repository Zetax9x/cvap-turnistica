"""Composizione e invio recuperabile delle notifiche, dopo il salvataggio dei turni."""
import json
import logging
from datetime import datetime, timedelta, timezone
from email import message_from_string, policy
from email.message import EmailMessage
from html import escape

from . import db_cambi_turno as registro, email_turni, pdf_cambi_turno

log = logging.getLogger('cvap.cambi_turno')


def componi(foto, indirizzo, tipo):
    v = foto['variazione']
    rettifica = tipo == 'rettifica'
    titolo = 'Cambio turno annullato' if rettifica else 'Variazione turni: ' + v['dichiarante']
    quando = datetime.fromisoformat(foto['quando']).strftime('%d/%m/%Y alle %H:%M')
    righe = [titolo, f"Cambio registrato da: {v['dichiarante']}", f"Data: {quando}",
             ('Il cambio è stato annullato e i turni sono tornati alle persone indicate qui sotto.' if rettifica
              else 'Il tabellone è stato aggiornato. Qui sotto trovi chi farà ciascun turno.'), *v['riepilogo']]
    avvisi = [a['messaggio'] for a in v['avvisi']]
    if avvisi:
        righe += ['Segnalazioni: il cambio è stato salvato anche in presenza di questi avvisi.', *avvisi]
    html = '<h1>' + escape(titolo) + '</h1>' + ''.join(f'<p>{escape(r)}</p>' for r in righe[1:])
    for s in foto['settimane']:
        html += f"<h2>Settimana {s['inizio']} / {s['fine']}</h2>" + email_turni._html_tabellone(s, None)
        righe.append(f"Tabellone {s['inizio']} / {s['fine']}: trovi tutti i turni nel PDF allegato e nel corpo dell’email.")
    m = EmailMessage()
    m['To'], m['Subject'] = indirizzo, titolo
    m.set_content('\n\n'.join(righe))
    m.add_alternative('<!doctype html><html lang="it"><body>' + html + '</body></html>', subtype='html')
    pdf = pdf_cambi_turno.genera(foto['settimane'], rettifica)
    m.add_attachment(pdf, maintype='application', subtype='pdf', filename='tabellone-aggiornato.pdf')
    return m


def invia_pendenti(conn, vid, postino):
    """Claim persistente prima di SMTP. I tentativi interrotti tornano disponibili dopo 5 minuti."""
    ora = datetime.now(timezone.utc)
    quando = ora.isoformat()
    scaduta = (ora - timedelta(minutes=5)).isoformat()
    with registro.transazione(conn):
        v = registro.variazione(conn, vid)
        tipo = 'rettifica' if v['annullata_il'] else 'variazione'
        vuote = conn.execute("SELECT * FROM notifiche_variazioni WHERE variazione_id = ? AND tipo = ? "
                              "AND destinatario = ''", (vid, tipo)).fetchall()
        for vuota in vuote:
            responsabili = conn.execute('SELECT email FROM destinatari_email WHERE responsabile = 1').fetchall()
            if responsabili:
                for email in sorted({r['email'].lower() for r in responsabili}):
                    conn.execute('INSERT OR IGNORE INTO notifiche_variazioni(variazione_id, tipo, destinatario, fotografia) '
                                 'VALUES (?, ?, ?, ?)', (vid, tipo, email, vuota['fotografia']))
                conn.execute('DELETE FROM notifiche_variazioni WHERE id = ?', (vuota['id'],))
            else:
                conn.execute("UPDATE notifiche_variazioni SET errore = 'Nessun responsabile configurato', stato = 'errore' "
                             'WHERE id = ?', (vuota['id'],))
        righe = [dict(r) for r in conn.execute("SELECT * FROM notifiche_variazioni WHERE variazione_id = ? AND tipo = ? "
                 "AND destinatario != '' AND (stato IN ('da_inviare', 'errore') "
                 "OR (stato = 'in_invio' AND aggiornata_il < ?)) ORDER BY id", (vid, tipo, scaduta)).fetchall()]
        for r in righe:
            conn.execute("UPDATE notifiche_variazioni SET stato = 'in_invio', tentativi = tentativi + 1, aggiornata_il = ? "
                         'WHERE id = ?', (quando, r['id']))
    for r in righe:
        messaggio, errore = None, None
        try:
            if not postino.configurato:
                errore = getattr(postino, 'motivo', None) or 'Invio SMTP non configurato'
            else:
                messaggio = message_from_string(r['messaggio'], policy=policy.default) if r['messaggio'] else componi(
                    json.loads(r['fotografia']), r['destinatario'], r['tipo'])
                # Congela anche l'allegato MIME, prima di tentare la spedizione.
                with registro.transazione(conn):
                    conn.execute('UPDATE notifiche_variazioni SET messaggio = ? WHERE id = ?',
                                 (messaggio.as_string(), r['id']))
                errore = postino.invia([messaggio]).get(r['destinatario'], 'Invio non confermato')
        except Exception:
            log.exception('Notifica cambio turno %s non completata', r['id'])
            errore = 'Preparazione PDF o invio email non riusciti: riprova dal gestionale'
        with registro.transazione(conn):
            conn.execute('UPDATE notifiche_variazioni SET stato = ?, errore = ?, aggiornata_il = ? WHERE id = ?',
                         ('errore' if errore else 'inviata', errore, datetime.now(timezone.utc).isoformat(), r['id']))
