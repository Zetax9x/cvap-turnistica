"""Cessioni e scambi: qualifica, riposo e sovrapposizioni bloccano l'operazione."""
import hashlib
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from . import db, db_cambi_turno as registro
from .calendario import lunedi
from .email_turni import orario_turno
from .modello import Assegnazione, ORE_RIPOSO_MIN
from .vincoli import valida_settimana

FUSO = ZoneInfo('Europe/Rome')


def adesso():
    return datetime.now(FUSO)


def istante(a, fine=False):
    ore = a.fine if fine else a.inizio
    return datetime.combine(date.fromordinal(ore // 24), time(ore % 24), FUSO)


def dipendente(conn, pid):
    p = db.get_persona(conn, pid)
    if not p or p['tipo'] != 'dipendente':
        raise HTTPException(400, 'Scegli un dipendente presente nel personale')
    return p


def fotografia(conn, aid, a=None):
    a = a or db.get_assegnazione(conn, aid)
    if not a:
        raise HTTPException(409, 'Un turno non esiste più: ricarica i turni')
    p = db.get_persona(conn, a.persona_id)
    return {**asdict(a), 'id': aid, 'data': a.data.isoformat(),
            'persona_nome': p['nome'] if p else f'#{a.persona_id}',
            'orario': orario_turno(a.fascia, a.segmento), 'inizio': istante(a).isoformat(),
            'fine': istante(a, True).isoformat(), 'revisione': registro.revisione(conn, aid)}


def assegnazione(f):
    return Assegnazione(date.fromisoformat(f['data']), f['postazione'], f['fascia'], f['segmento'],
                        f['ruolo'], f['persona_id'], f['origine'])


def turni_futuri(conn, pid, settimana=None):
    dipendente(conn, pid)
    ora = adesso()
    dal, al = ora.date(), date.max
    if settimana:
        primo = lunedi(settimana)
        dal, al = max(dal, primo), primo + timedelta(days=6)
    righe = db.assegnazioni_persona(conn, pid, dal, al)
    return sorted([f for aid, a in righe if (f := fotografia(conn, aid, a))['inizio'] > ora.isoformat()],
                  key=lambda f: (f['inizio'], f['postazione'], f['ruolo'], f['id']))


def descrivi(f):
    d = date.fromisoformat(f['data']).strftime('%d/%m/%Y')
    return f"{d}, {f['orario']}, {f['postazione']}, {f['ruolo']}"


def _valuta(conn, prima, dopo, dati_settimana):
    """Valida il risultato senza scriverlo. I dati gestionali restano sul server."""
    sostituzioni = {f['id']: assegnazione(f) for f in dopo}
    coinvolti = {f['persona_id'] for f in prima + dopo}
    settimane = sorted({lunedi(date.fromisoformat(f['data'])) for f in prima})
    avvisi, errori = [], []
    for f in dopo:
        p = db.a_persona(dipendente(conn, f['persona_id']))
        if not p.puo_ricoprire(f['ruolo'], f['postazione']):
            errori.append({'codice': 'qualifica', 'persona_id': p.id,
                           'messaggio': f"{p.nome} non ha la qualifica richiesta per svolgere questo turno come {f['ruolo']}: "
                                        f"{descrivi(f)}. Scegli un collega o un turno compatibile con la qualifica."})
    # Riposo e sovrapposizioni si controllano nei dintorni di ogni turno.
    dintorni = {}
    for f in dopo:
        d = date.fromisoformat(f['data'])
        for aid, a in db.assegnazioni_periodo(conn, d - timedelta(days=2), d + timedelta(days=2)):
            if a.persona_id in coinvolti or aid in sostituzioni:
                dintorni[aid] = a
    prima_map = dict(dintorni)
    dintorni.update(sostituzioni)

    def conflitti(righe):
        out = {}
        for (ia, a), (ib, b) in combinations(sorted(righe.items(), key=lambda x: (x[1].inizio, x[0])), 2):
            if a.persona_id != b.persona_id or not ({ia, ib} & sostituzioni.keys()):
                continue
            pausa = b.inizio - a.fine
            if pausa < ORE_RIPOSO_MIN:
                out[(a.persona_id, ia, ib)] = pausa
        return out

    precedenti = conflitti(prima_map)
    for chiave, pausa in conflitti(dintorni).items():
        if chiave in precedenti and pausa >= precedenti[chiave]:
            continue
        pid, ia, ib = chiave
        nome = dipendente(conn, pid)['nome']
        fa, fb = fotografia(conn, ia, dintorni[ia]), fotografia(conn, ib, dintorni[ib])
        if pausa < 0:
            codice = 'sovrapposizione'
            messaggio = f"{nome} è già impegnato in un altro turno nello stesso orario: {descrivi(fa)} e {descrivi(fb)}."
        else:
            codice = 'riposo'
            messaggio = f"{nome}: {pausa} ore di riposo tra {descrivi(fa)} e {descrivi(fb)}. Servono almeno 11 ore."
        errori.append({'codice': codice, 'persona_id': pid, 'messaggio': messaggio})

    for settimana in settimane:
        d = dati_settimana(conn, settimana)
        regole = d.regole()
        regole['persone'] = dict(regole['persone'])
        divieti = db.divieti_per_persona(conn)
        for pid in coinvolti:
            if pid not in regole['persone']:
                regole['persone'][pid] = db.a_persona(d.persone[pid], divieti.get(pid, ()))
        regole['assegnazioni'] = [sostituzioni.get(aid, a) for aid, a in d.righe]
        # Lo scambio può modificare anche il contesto dell'altra settimana.
        regole['contesto'] = [a for a in d.contesto if a not in [assegnazione(f) for f in prima]]
        regole['contesto'] += [a for a in sostituzioni.values()
                              if a.data not in set(d.giorni) and min(abs((a.data - g).days) for g in d.giorni) <= 3]
        for v in valida_settimana(**regole):
            if v.persona_id not in coinvolti or v.codice in {'riposo', 'sovrapposizione', 'qualifica'}:
                continue
            messaggio = v.messaggio
            if v.codice == 'ferie' and (v.persona_id, v.data) in d.malattia:
                messaggio = messaggio.replace('in ferie', 'in malattia')
            item = {'codice': v.codice, 'persona_id': v.persona_id, 'messaggio': messaggio}
            if item not in avvisi:
                avvisi.append(item)
    revisione = conn.execute('SELECT MAX(id) AS n FROM revisioni_cambi_turno').fetchone()['n'] or 0
    versione = hashlib.sha256(registro.codifica([prima, dopo, avvisi, errori, revisione]).encode()).hexdigest()
    return {'prima': prima, 'dopo': dopo, 'avvisi': avvisi, 'errori': errori, 'versione': versione,
            'settimane': [d.isoformat() for d in settimane]}


def anteprima(conn, corpo, dati_settimana):
    pid, collega = corpo['persona_id'], corpo['collega_id']
    dipendente(conn, pid)
    dipendente(conn, collega)
    if pid == collega:
        raise HTTPException(400, 'Scegli un altro dipendente')
    ids = [corpo['turno_id']]
    if corpo['tipo'] == 'scambio':
        if not corpo.get('turno_ricevuto_id'):
            raise HTTPException(400, 'Scegli il turno che ricevi')
        ids.append(corpo['turno_ricevuto_id'])
    elif corpo.get('turno_ricevuto_id') is not None:
        raise HTTPException(400, 'Una cessione non prevede un turno ricevuto')
    prima = [fotografia(conn, aid) for aid in ids]
    if prima[0]['persona_id'] != pid or (len(prima) == 2 and prima[1]['persona_id'] != collega):
        raise HTTPException(409, 'Il titolare di un turno è cambiato: ricarica i turni')
    if any(istante(assegnazione(f)) <= adesso() for f in prima):
        raise HTTPException(400, 'Puoi selezionare soltanto turni non ancora iniziati')
    dopo = [fotografia(conn, ids[0], replace(assegnazione(prima[0]), persona_id=collega))]
    if len(prima) == 2:
        dopo.append(fotografia(conn, ids[1], replace(assegnazione(prima[1]), persona_id=pid)))
    vista = _valuta(conn, prima, dopo, dati_settimana)
    riepilogo = [f"{n['persona_nome']} farà il turno di {f['persona_nome']}: {descrivi(f)}" for f, n in zip(prima, dopo)]
    return {**vista, 'tipo': corpo['tipo'], 'dichiarante': prima[0]['persona_nome'], 'riepilogo': riepilogo,
            'richiesta': {k: corpo.get(k) for k in ('tipo', 'persona_id', 'collega_id', 'turno_id', 'turno_ricevuto_id')}}


def _controlla(vista, versione):
    if versione != vista['versione']:
        raise HTTPException(409, 'I turni o i dati del personale sono cambiati. Aggiorna l’elenco dei turni e controlla di nuovo il riepilogo prima di confermare.')
    if vista['errori']:
        raise HTTPException(400, '; '.join(e['messaggio'] for e in vista['errori']))


def _trasferisci(conn, foto):
    for f in foto:
        # La base generata resta invariata; audit e titolare effettivo sono atomici.
        db.imposta_titolare_effettivo(conn, f['id'], f['persona_id'])


def conferma(conn, corpo, dati_settimana, payload_settimana):
    with registro.transazione(conn):
        esistente = conn.execute('SELECT id FROM variazioni_turno WHERE chiave = ?', (corpo['chiave'],)).fetchone()
        if esistente:
            v = registro.variazione(conn, esistente['id'])
            richiesta = {k: corpo.get(k) for k in v['dati']['richiesta']}
            if richiesta != v['dati']['richiesta']:
                raise HTTPException(409, 'Questa richiesta è già stata usata per un altro cambio')
            return v
        vista = anteprima(conn, corpo, dati_settimana)
        _controlla(vista, corpo['versione'])
        _trasferisci(conn, vista['dopo'])
        vista['dopo'] = [fotografia(conn, f['id']) for f in vista['dopo']]
        quando = adesso().isoformat(timespec='seconds')
        cur = conn.execute('INSERT INTO variazioni_turno(chiave, creata_il, dati) VALUES (?, ?, ?)',
                           (corpo['chiave'], quando, registro.codifica(vista)))
        vid = cur.lastrowid
        foto = {'variazione': vista, 'quando': quando,
                'settimane': [payload_settimana(conn, date.fromisoformat(d)) for d in vista['settimane']]}
        registro.prepara_notifiche(conn, vid, 'variazione', foto)
        return registro.variazione(conn, vid)


def anteprima_annullamento(conn, vid, dati_settimana):
    v = registro.variazione(conn, vid)
    if v['annullata_il']:
        raise HTTPException(409, 'Questo cambio è già stato annullato')
    salvati = v['dati']['dopo']
    attuali = [fotografia(conn, f['id']) for f in salvati]
    # La revisione individua anche un turno cambiato e poi rimesso com'era (o un id riutilizzato).
    if any(assegnazione(a) != assegnazione(s) or a['revisione'] != s['revisione']
           for a, s in zip(attuali, salvati)):
        raise HTTPException(409, 'I turni sono stati ulteriormente modificati: serve un intervento manuale')
    ritorno = [fotografia(conn, f['id'], assegnazione(f)) for f in v['dati']['prima']]
    vista = _valuta(conn, attuali, ritorno, dati_settimana)
    vista['riepilogo'] = [f"Ripristino a {f['persona_nome']}: {descrivi(f)}" for f in ritorno]
    return vista


def annulla(conn, vid, corpo, dati_settimana, payload_settimana):
    with registro.transazione(conn):
        v = registro.variazione(conn, vid)
        if v['annullata_il']:
            if v['chiave_annullamento'] == corpo['chiave']:
                return v
            raise HTTPException(409, 'Questo cambio è già stato annullato')
        vista = anteprima_annullamento(conn, vid, dati_settimana)
        _controlla(vista, corpo['versione'])
        _trasferisci(conn, vista['dopo'])
        quando = adesso().isoformat(timespec='seconds')
        vista.update(dichiarante='Responsabile (accesso gestionale)', tipo='rettifica')
        conn.execute('UPDATE variazioni_turno SET annullata_il = ?, chiave_annullamento = ?, rettifica = ? WHERE id = ?',
                     (quando, corpo['chiave'], registro.codifica(vista), vid))
        foto = {'variazione': vista, 'quando': quando,
                'settimane': [payload_settimana(conn, date.fromisoformat(d)) for d in vista['settimane']]}
        registro.prepara_notifiche(conn, vid, 'rettifica', foto)
        # Non spedire una vecchia variazione pendente dopo la sua rettifica.
        conn.execute("UPDATE notifiche_variazioni SET stato = 'superata' WHERE variazione_id = ? "
                     "AND tipo = 'variazione' AND stato != 'inviata'", (vid,))
        return registro.variazione(conn, vid)
