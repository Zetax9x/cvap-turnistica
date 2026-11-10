"""Registro delle azioni: ogni modifica fatta dal sito, con quale accesso (normale, master...) e l'esito.

Lo scrive il middleware in app.py per ogni richiesta alle API che non sia una lettura; gli accessi li
scrive l'endpoint di login (riuscito o no). Lo vede solo chi è entrato con la password master.
"""
import re
import sqlite3
from datetime import date, datetime

MAX_RIGHE = 20_000  # oltre, si cancellano le più vecchie
PULIZIA_OGNI = 500

# accesso: chi ha fatto l'azione
APERTO = "aperto"        # sito senza password (uso locale)
PUBBLICO = "pubblico"    # pagina dei cambi turno dei dipendenti, senza password
ANONIMO = "anonimo"      # tentativo di accesso con password sbagliata

SCHEMA = """
CREATE TABLE IF NOT EXISTS registro_azioni (  -- cvap/registro.py
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quando TEXT NOT NULL,
    accesso TEXT NOT NULL,
    metodo TEXT NOT NULL,
    percorso TEXT NOT NULL,
    esito INTEGER NOT NULL,
    descrizione TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS registro_azioni_accesso ON registro_azioni(accesso, id);
"""

# anteprime: POST che non modificano nulla
_SOLO_LETTURA = re.compile(r"/anteprima(-annullamento)?$")

_D = r"(?P<data>\d{4}-\d{2}-\d{2})"
_ID = r"(?P<id>[^/]+)"
# (metodo, percorso, descrizione): {data} diventa la data in italiano, {id} il numero nel percorso
_AZIONI = [
    ("POST", rf"/api/settimane/{_D}/genera", "Generazione dei turni della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/conferma", "Conferma della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/riapri", "Riapertura della settimana del {data}"),
    ("DELETE", rf"/api/settimane/{_D}/generati", "Rimozione dei turni generati della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/assegnazioni", "Turno aggiunto a mano nella settimana del {data}"),
    ("PUT", rf"/api/settimane/{_D}/indisponibilita", "Indisponibilità modificate nella settimana del {data}"),
    ("PUT", rf"/api/settimane/{_D}/fabbisogno", "Standby e Programmati modificati nella settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/extra", "Assistenza o Extra aggiunta nella settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/email/prova", "Email di prova della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/email", "Invio delle email dei turni della settimana del {data}"),
    ("DELETE", rf"/api/assegnazioni/{_ID}", "Turno {id} tolto"),
    ("POST", rf"/api/assegnazioni/{_ID}/sostituisci", "Sostituzione nel turno {id}"),
    ("POST", rf"/api/assegnazioni/{_ID}/catena", "Scambio a catena dal turno {id}"),
    ("POST", r"/api/persone", "Persona aggiunta"),
    ("PUT", rf"/api/persone/{_ID}/parametri", "Parametri della persona {id} modificati"),
    ("PUT", rf"/api/persone/{_ID}", "Persona {id} modificata"),
    ("DELETE", rf"/api/persone/{_ID}", "Persona {id} eliminata"),
    ("POST", r"/api/ferie", "Ferie aggiunte"),
    ("DELETE", rf"/api/ferie/{_ID}", "Ferie {id} tolte"),
    ("POST", r"/api/calendario-copertura/ferie", "Ferie aggiunte dal calendario"),
    ("POST", r"/api/divieti", "Divieto aggiunto"),
    ("DELETE", rf"/api/divieti/{_ID}", "Divieto {id} tolto"),
    ("PUT", rf"/api/extra/{_ID}", "Assistenza o Extra {id} modificata"),
    ("DELETE", rf"/api/extra/{_ID}", "Assistenza o Extra {id} tolta"),
    ("PUT", r"/api/impostazioni", "Impostazioni modificate"),
    ("POST", r"/api/destinatari/invia", "Invio dei riepiloghi ai destinatari"),
    ("POST", r"/api/destinatari", "Destinatario email aggiunto"),
    ("PUT", rf"/api/destinatari/{_ID}", "Destinatario email {id} modificato"),
    ("DELETE", rf"/api/destinatari/{_ID}", "Destinatario email {id} tolto"),
    ("PUT", r"/api/festivita/disponibili", "Disponibilità per le festività modificate"),
    ("POST", r"/api/festivita", "Festività aggiunta"),
    ("PUT", rf"/api/festivita/{_ID}", "Festività {id} modificata"),
    ("DELETE", rf"/api/festivita/{_ID}", "Festività {id} tolta"),
    ("POST", r"/api/storico-festivi/importa", "Storico delle festività importato"),
    ("PUT", rf"/api/storico-festivi/{_ID}", "Storico delle festività del {id} modificato"),
    ("POST", rf"/api/calendari/{_ID}/rigenera", "Link del calendario della persona {id} rigenerato"),
    ("POST", r"/api/cambi-turno/conferme", "Cambio turno chiesto da un dipendente"),
    ("POST", rf"/api/gestione-cambi-turno/{_ID}/annulla", "Cambio turno {id} annullato"),
    ("POST", rf"/api/gestione-cambi-turno/{_ID}/reinvia", "Notifiche del cambio turno {id} inviate di nuovo"),
    ("PUT", r"/api/push/iscrizione", "Notifiche attivate su un dispositivo"),
    ("DELETE", r"/api/push/iscrizione", "Notifiche disattivate su un dispositivo"),
    ("POST", r"/api/push/prova", "Notifica di prova"),
    ("POST", r"/api/uscita", "Uscita"),
]
_AZIONI_RE = [(m, re.compile(p + "$"), d) for m, p, d in _AZIONI]


def da_registrare(metodo: str, percorso: str) -> bool:
    """Le modifiche alle API; non le letture, le anteprime e l'accesso (lo registra l'endpoint)."""
    return (metodo in ("POST", "PUT", "PATCH", "DELETE") and percorso.startswith("/api/")
            and percorso != "/api/accesso" and not _SOLO_LETTURA.search(percorso))


def descrivi(metodo: str, percorso: str) -> str:
    for m, regola, testo in _AZIONI_RE:
        trovato = regola.match(percorso) if m == metodo else None
        if trovato:
            valori = trovato.groupdict()
            if "data" in valori:
                valori["data"] = date.fromisoformat(valori["data"]).strftime("%d/%m/%Y")
            return testo.format(**valori)
    return f"{metodo} {percorso}"


def crea_tabella(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def registra(conn: sqlite3.Connection, accesso: str, metodo: str, percorso: str, esito: int,
             descrizione: str | None = None, quando: datetime | None = None) -> None:
    quando = (quando or datetime.now()).isoformat(timespec="seconds")
    with conn:
        cur = conn.execute(
            "INSERT INTO registro_azioni(quando, accesso, metodo, percorso, esito, descrizione) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (quando, accesso, metodo, percorso, esito, descrizione or descrivi(metodo, percorso)))
        nuovo = cur.lastrowid
        if nuovo and nuovo % PULIZIA_OGNI == 0:
            conn.execute("DELETE FROM registro_azioni WHERE id <= ?", (nuovo - MAX_RIGHE,))


def lista(conn: sqlite3.Connection, limite: int = 200, prima_di: int | None = None,
          accesso: str | None = None) -> list[dict]:
    """Le azioni dalla più recente; `prima_di` (un id) per caricare le successive."""
    condizioni, parametri = [], []
    if prima_di is not None:
        condizioni.append("id < ?")
        parametri.append(prima_di)
    if accesso:
        condizioni.append("accesso = ?")
        parametri.append(accesso)
    dove = f"WHERE {' AND '.join(condizioni)}" if condizioni else ""
    righe = conn.execute(
        f"SELECT id, quando, accesso, metodo, percorso, esito, descrizione FROM registro_azioni {dove} "
        "ORDER BY id DESC LIMIT ?", (*parametri, limite)).fetchall()
    return [dict(r) for r in righe]
