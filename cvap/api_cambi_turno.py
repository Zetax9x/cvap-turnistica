"""API della pagina dipendenti e registro riservato del gestionale."""
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import db, cambi_turno, db_cambi_turno as registro, email_cambi_turno
from .api_comune import Id, IdPath, DataValida


class CambioIn(BaseModel):
    tipo: Literal['cessione', 'scambio']
    persona_id: Id
    collega_id: Id
    turno_id: Id
    turno_ricevuto_id: Id | None = None


class ConfermaIn(CambioIn):
    versione: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    chiave: UUID


class AnnullaIn(BaseModel):
    versione: Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
    chiave: UUID


def crea_router(connessione, scrittura, dati_settimana, payload_settimana, postino, notifica=None):
    router = APIRouter()
    Conn = Annotated[sqlite3.Connection, Depends(connessione)]
    pubblico = '/api/cambi-turno'
    gestione = '/api/gestione-cambi-turno'

    @router.get(pubblico + '/dipendenti')
    def dipendenti(conn: Conn):
        return [{'id': p['id'], 'nome': p['nome']} for p in db.lista_persone(conn) if p['tipo'] == 'dipendente']

    @router.get(pubblico + '/turni')
    def turni(conn: Conn, persona_id: Id, settimana: DataValida | None = None):
        return cambi_turno.turni_futuri(conn, persona_id, settimana)

    @router.post(pubblico + '/anteprima')
    def anteprima(body: CambioIn, conn: Conn):
        return cambi_turno.anteprima(conn, body.model_dump(), dati_settimana)

    @router.post(pubblico + '/conferme')
    def conferma(body: ConfermaIn, conn: Conn):
        with scrittura():
            nuova = conn.execute('SELECT 1 FROM variazioni_turno WHERE chiave = ?', (str(body.chiave),)).fetchone() is None
            v = cambi_turno.conferma(conn, body.model_dump(mode='json'), dati_settimana, payload_settimana)
            email_cambi_turno.invia_pendenti(conn, v['id'], postino)
            risposta = registro.esito(conn, registro.variazione(conn, v['id']))
        if nuova and notifica:  # solo alla prima registrazione: una ripetizione con la stessa chiave non riavvisa
            notifica('Cambio turno registrato', (risposta['riepilogo'] or [''])[0], '/app/#/altro/cambi')
        return risposta

    @router.get(pubblico + '/conferme/{riferimento}')
    def esito(riferimento: UUID, conn: Conn):
        return registro.esito(conn, registro.variazione(conn, chiave=str(riferimento)))

    @router.get(gestione)
    def elenco(conn: Conn, settimana: DataValida | None = None,
               stato_email: Literal['inviata', 'da_reinviare'] | None = None):
        rows = conn.execute('SELECT id FROM variazioni_turno ORDER BY id DESC').fetchall()
        lista = [registro.esito(conn, registro.variazione(conn, r['id']), True) for r in rows]
        if settimana:
            from .calendario import lunedi
            lista = [v for v in lista if lunedi(settimana).isoformat() in v['dati']['settimane']]
        return [v for v in lista if not stato_email or v['notifica'] == stato_email]

    @router.post(gestione + '/{vid}/reinvia')
    def reinvia(vid: IdPath, conn: Conn):
        with scrittura():
            email_cambi_turno.invia_pendenti(conn, vid, postino)
            return registro.esito(conn, registro.variazione(conn, vid), True)

    @router.post(gestione + '/{vid}/anteprima-annullamento')
    def anteprima_annullamento(vid: IdPath, conn: Conn):
        return cambi_turno.anteprima_annullamento(conn, vid, dati_settimana)

    @router.post(gestione + '/{vid}/annulla')
    def annulla(vid: IdPath, body: AnnullaIn, conn: Conn):
        with scrittura():
            v = cambi_turno.annulla(conn, vid, body.model_dump(mode='json'), dati_settimana, payload_settimana)
            email_cambi_turno.invia_pendenti(conn, v['id'], postino)
            return registro.esito(conn, registro.variazione(conn, v['id']), True)

    return router
