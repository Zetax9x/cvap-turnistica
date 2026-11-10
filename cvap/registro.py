"""Registro delle azioni: ogni modifica fatta dal sito, con quale accesso (normale, master...) e l'esito.

Lo scrive il middleware in app.py per ogni richiesta alle API che non sia una lettura; gli accessi li
scrive l'endpoint di login (riuscito o no). Lo vede solo chi è entrato con la password master.
"""
import json
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
    descrizione TEXT NOT NULL,
    dettagli TEXT NOT NULL DEFAULT '[]'  -- JSON: [[etichetta, valore], ...]
);
CREATE INDEX IF NOT EXISTS registro_azioni_accesso ON registro_azioni(accesso, id);
"""

# anteprime: POST che non modificano nulla
_SOLO_LETTURA = re.compile(r"/anteprima(-annullamento)?$")

_D = r"(?P<data>\d{4}-\d{2}-\d{2})"
_ID = r"(?P<id>[^/]+)"
# (metodo, percorso, cosa indica {id}, descrizione). Nella descrizione {data} è la data in italiano, {og}
# l'oggetto indicato da {id} letto dal database prima dell'azione (persona, turno...), {nome} il nome inviato.
_AZIONI = [
    ("POST", rf"/api/settimane/{_D}/genera", None, "Generazione dei turni della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/conferma", None, "Conferma della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/riapri", None, "Riapertura della settimana del {data}"),
    ("DELETE", rf"/api/settimane/{_D}/generati", None, "Rimozione dei turni generati della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/assegnazioni", None, "Turno aggiunto a mano nella settimana del {data}"),
    ("PUT", rf"/api/settimane/{_D}/indisponibilita", None, "Indisponibilità modificate nella settimana del {data}"),
    ("PUT", rf"/api/settimane/{_D}/fabbisogno", None, "Standby e Programmati modificati nella settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/extra", None, "Assistenza o Extra «{nome}» aggiunta nella settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/email/prova", None, "Email di prova della settimana del {data}"),
    ("POST", rf"/api/settimane/{_D}/email", None, "Invio delle email dei turni della settimana del {data}"),
    ("DELETE", rf"/api/assegnazioni/{_ID}", "turno", "Tolto il turno di {og}"),
    ("POST", rf"/api/assegnazioni/{_ID}/sostituisci", "turno", "Sostituzione nel turno di {og}"),
    ("POST", rf"/api/assegnazioni/{_ID}/catena", "turno", "Scambio a catena dal turno di {og}"),
    ("POST", r"/api/persone", None, "Persona aggiunta: {nome}"),
    ("PUT", rf"/api/persone/{_ID}/parametri", "persona", "Parametri di {og} modificati"),
    ("PUT", rf"/api/persone/{_ID}", "persona", "Scheda di {og} modificata"),
    ("DELETE", rf"/api/persone/{_ID}", "persona", "Persona eliminata: {og}"),
    ("POST", r"/api/ferie", None, "Ferie aggiunte"),
    ("DELETE", rf"/api/ferie/{_ID}", "ferie", "Ferie tolte a {og}"),
    ("POST", r"/api/calendario-copertura/ferie", None, "Ferie aggiunte dal calendario"),
    ("POST", r"/api/divieti", None, "Divieto aggiunto"),
    ("DELETE", rf"/api/divieti/{_ID}", "divieto", "Divieto tolto a {og}"),
    ("PUT", rf"/api/extra/{_ID}", "extra", "Assistenza o Extra «{og}» modificata"),
    ("DELETE", rf"/api/extra/{_ID}", "extra", "Assistenza o Extra «{og}» tolta"),
    ("PUT", r"/api/impostazioni", None, "Impostazioni modificate"),
    ("PUT", r"/api/email-equita", None, "Indirizzo dell'email dell'equità modificato"),
    ("POST", r"/api/email-equita/prova", None, "Email dell'equità inviata a mano"),
    ("POST", r"/api/destinatari/invia", None, "Invio dei riepiloghi ai destinatari"),
    ("POST", r"/api/destinatari", None, "Destinatario email aggiunto"),
    ("PUT", rf"/api/destinatari/{_ID}", "destinatario", "Destinatario email {og} modificato"),
    ("DELETE", rf"/api/destinatari/{_ID}", "destinatario", "Destinatario email {og} tolto"),
    ("PUT", r"/api/festivita/disponibili", None, "Disponibilità per le festività modificate"),
    ("POST", r"/api/festivita", None, "Festività aggiunta: {nome}"),
    ("PUT", rf"/api/festivita/{_ID}", "festivita", "Festività «{og}» modificata"),
    ("DELETE", rf"/api/festivita/{_ID}", "festivita", "Festività «{og}» tolta"),
    ("POST", r"/api/storico-festivi/importa", None, "Storico delle festività importato"),
    ("PUT", rf"/api/storico-festivi/{_ID}", None, "Storico delle festività del {id} modificato"),
    ("POST", rf"/api/calendari/{_ID}/rigenera", "persona", "Link del calendario di {og} rigenerato"),
    ("POST", r"/api/cambi-turno/conferme", None, "Cambio turno chiesto da un dipendente"),
    ("POST", rf"/api/gestione-cambi-turno/{_ID}/annulla", None, "Cambio turno {id} annullato"),
    ("POST", rf"/api/gestione-cambi-turno/{_ID}/reinvia", None, "Notifiche del cambio turno {id} inviate di nuovo"),
    ("PUT", r"/api/push/iscrizione", None, "Notifiche attivate su un dispositivo"),
    ("DELETE", r"/api/push/iscrizione", None, "Notifiche disattivate su un dispositivo"),
    ("POST", r"/api/push/prova", None, "Notifica di prova"),
    ("POST", r"/api/uscita", None, "Uscita"),
]
_AZIONI_RE = [(m, re.compile(p + "$"), og, d) for m, p, og, d in _AZIONI]

# --- dettagli -----------------------------------------------------------------------------------
MAX_ELENCO = 12   # voci mostrate di un elenco (indisponibilità, fabbisogno...)
MAX_TESTO = 300
# campi da non salvare mai: segreti e dati tecnici dei dispositivi
_NASCOSTI = {"password", "chiave", "chiave_annullamento", "versione", "endpoint", "keys", "auth", "p256dh",
             "expirationTime"}
_ETICHETTE = {
    "persona_id": "Persona", "sostituto_id": "Sostituto", "ceduto_id": "Turno ceduto", "nome": "Nome",
    "nome_volontario": "Volontario", "tipo": "Tipo", "qualifica": "Qualifica", "email": "Email",
    "autista_programmati": "Autista nei Programmati", "attivo": "Attivo", "max_ore_settimana": "Massimo ore a settimana",
    "dal": "Dal", "al": "Al", "motivo": "Motivo", "data": "Giorno", "postazione": "Postazione", "fascia": "Fascia",
    "segmento": "Parte del turno", "ruolo": "Ruolo", "turno": "Turno", "quantita": "Quanti", "inizio": "Dalle ore",
    "fine": "Alle ore", "autisti": "Autisti", "soccorritori": "Soccorritori", "tempo_max": "Tempo massimo (secondi)",
    "data_riferimento_a": "Data di riferimento settimana A", "scarto_ore_max": "Differenza massima di ore",
    "contenuti": "Riepiloghi", "responsabile": "Riceve i turni", "turni": "Turni", "voci": "Posti richiesti",
    "anno": "Anno", "regola": "Regola", "giorno": "Giorno", "mese": "Mese", "conta_giorno": "Conta il giorno",
    "conta_notte": "Conta la notte",
}
_ORARI = {("giorno", "intero"): "8–20", ("giorno", "mattina"): "8–14", ("giorno", "pomeriggio"): "14–20",
          ("notte", "intero"): "20–8", ("giorno", "standby"): "7–19", ("giorno", "standby_mattina"): "7–14",
          ("giorno", "standby_pomeriggio"): "14–19", ("notte", "standby"): "19–7",
          ("giorno", "prog_mattina"): "7–14", ("giorno", "prog_pomeriggio"): "14–20"}
_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _data_it(valore: str) -> str:
    return date.fromisoformat(valore).strftime("%d/%m/%Y")


def _nome_persona(conn, pid) -> str:
    try:
        r = conn.execute("SELECT nome FROM persone WHERE id = ?", (int(pid),)).fetchone()
    except (TypeError, ValueError):
        return str(pid)
    return r["nome"] if r else f"n. {pid}"


def descrivi_turno(conn, aid) -> str | None:
    """«Marco Bianchi, 18/11/2026, Acquasanta, giorno 8–20, autista» (None se il turno non c'è)."""
    try:
        r = conn.execute("SELECT a.data, a.postazione, a.fascia, a.segmento, a.ruolo, p.nome FROM assegnazioni a "
                         "LEFT JOIN persone p ON p.id = a.persona_id WHERE a.id = ?", (int(aid),)).fetchone()
    except (TypeError, ValueError):
        return None
    if not r:
        return None
    orario = _ORARI.get((r["fascia"], r["segmento"]), r["segmento"])
    return f"{r['nome'] or '?'}, {_data_it(r['data'])}, {r['postazione']}, {r['fascia']} {orario}, {r['ruolo']}"


def _oggetto(conn, tipo: str, oid: str) -> tuple[str, list[tuple[str, str]]]:
    """Etichetta breve e dettagli dell'oggetto indicato nel percorso, letti prima dell'azione."""
    def riga(sql):
        try:
            return conn.execute(sql, (int(oid),)).fetchone()
        except (TypeError, ValueError):
            return None
    if tipo == "persona":
        nome = _nome_persona(conn, oid)
        return nome, [("Persona", nome)]
    if tipo == "turno":
        turno = descrivi_turno(conn, oid)
        if not turno:
            return f"n. {oid}", []
        chi, quando = turno.split(", ", 2)[:2]
        return f"{chi} del {quando[:5]}", [("Turno", turno)]
    if tipo == "ferie":
        r = riga("SELECT persona_id, dal, al, motivo FROM ferie WHERE id = ?")
        if not r:
            return f"n. {oid}", []
        nome = _nome_persona(conn, r["persona_id"])
        return nome, [("Persona", nome), ("Dal", _data_it(r["dal"])), ("Al", _data_it(r["al"])), ("Motivo", r["motivo"])]
    if tipo == "divieto":
        r = riga("SELECT persona_id, postazione, turno FROM divieti WHERE id = ?")
        if not r:
            return f"n. {oid}", []
        nome = _nome_persona(conn, r["persona_id"])
        return nome, [("Persona", nome), ("Postazione", r["postazione"] or "qualsiasi"), ("Turno", r["turno"] or "qualsiasi")]
    if tipo == "extra":
        r = riga("SELECT data, nome FROM richieste_extra WHERE id = ?")
        return (r["nome"], [("Giorno", _data_it(r["data"]))]) if r else (f"n. {oid}", [])
    if tipo == "festivita":
        r = riga("SELECT nome FROM festivita WHERE id = ?")
        return (r["nome"], []) if r else (f"n. {oid}", [])
    if tipo == "destinatario":
        r = riga("SELECT email FROM destinatari_email WHERE id = ?")
        return (r["email"], []) if r else (f"n. {oid}", [])
    return oid, []


# nei divieti e simili un campo vuoto vuol dire "tutti"
_VUOTO_QUALSIASI = {"postazione", "turno", "fascia", "segmento", "ruolo"}
# messaggi di validazione più frequenti (FastAPI li dà in inglese)
_MESSAGGI = {"Field required": "manca un dato obbligatorio", "Input should be a valid date": "data non valida",
             "Input should be a valid integer": "numero non valido", "Extra inputs are not permitted": "dato non previsto"}


def _valore(conn, chiave: str, valore) -> str:
    if valore is None:
        return "qualsiasi" if chiave in _VUOTO_QUALSIASI else "nessuno"
    if isinstance(valore, bool):
        return "sì" if valore else "no"
    if chiave in ("persona_id", "sostituto_id"):
        return _nome_persona(conn, valore)
    if chiave == "ceduto_id":
        return descrivi_turno(conn, valore) or f"n. {valore}"
    if isinstance(valore, str) and _DATA_ISO.match(valore):
        return _data_it(valore)
    if isinstance(valore, dict):
        parti = [_valore(conn, k, v) for k, v in valore.items() if k not in _NASCOSTI]
        return " ".join(p for p in parti if p)
    if isinstance(valore, list):
        voci = [_valore(conn, chiave, v) for v in valore[:MAX_ELENCO]]
        altre = len(valore) - MAX_ELENCO
        testo = "; ".join(voci) if voci else "nessuno"
        return testo + (f"; e altri {altre}" if altre > 0 else "")
    return str(valore)[:MAX_TESTO]


def dettagli_corpo(conn, corpo) -> list[tuple[str, str]]:
    """I dati inviati con l'azione, in italiano, con i nomi al posto dei numeri; mai password e chiavi."""
    if not isinstance(corpo, dict):
        return []
    return [(_ETICHETTE.get(k, k), _valore(conn, k, v)) for k, v in corpo.items() if k not in _NASCOSTI]


def _errore_validazione(e) -> str:
    if not isinstance(e, dict):
        return str(e)
    msg = str(e.get("msg", ""))
    msg = next((it for en, it in _MESSAGGI.items() if msg.startswith(en)), msg)
    campo = [str(x) for x in e.get("loc", []) if x != "body"]
    return f"{_ETICHETTE.get(campo[-1], campo[-1])}: {msg}" if campo else msg


def dettagli_esito(metodo: str, percorso: str, codice: int, risposta) -> list[tuple[str, str]]:
    """Cosa è successo: il motivo se non è riuscita; per la generazione, posti scoperti e qualità."""
    if codice >= 400:
        dettaglio = risposta.get("detail") if isinstance(risposta, dict) else None
        if isinstance(dettaglio, list):  # errori di validazione
            dettaglio = "; ".join(_errore_validazione(e) for e in dettaglio)
        return [("Motivo", str(dettaglio)[:MAX_TESTO])] if dettaglio else [("Motivo", f"errore {codice}")]
    if metodo == "POST" and percorso.endswith("/genera") and isinstance(risposta, dict):
        report = risposta.get("report") or {}
        scoperti = len(report.get("scoperti") or [])
        generati = sum(1 for a in risposta.get("assegnazioni") or [] if a.get("origine") == "generato")
        esito = [("Turni generati", str(generati)),
                 ("Posti scoperti", str(scoperti) if scoperti else "nessuno")]
        if report.get("stato"):
            esito.append(("Soluzione", "ottima" if report["stato"] == "ottimo" else "buona, non dimostrata ottima"))
        return esito
    return []


def da_registrare(metodo: str, percorso: str) -> bool:
    """Le modifiche alle API; non le letture, le anteprime e l'accesso (lo registra l'endpoint)."""
    return (metodo in ("POST", "PUT", "PATCH", "DELETE") and percorso.startswith("/api/")
            and percorso != "/api/accesso" and not _SOLO_LETTURA.search(percorso))


def prepara(conn, metodo: str, percorso: str, corpo=None) -> tuple[str, list[tuple[str, str]]]:
    """Descrizione e dettagli di un'azione, da chiamare PRIMA di eseguirla (dopo, un turno tolto non c'è più)."""
    for m, regola, tipo, testo in _AZIONI_RE:
        trovato = regola.match(percorso) if m == metodo else None
        if not trovato:
            continue
        valori = {"nome": "", "og": "", **trovato.groupdict()}
        dettagli = []
        if "data" in trovato.groupdict():
            valori["data"] = _data_it(valori["data"])
        if tipo and "id" in valori:
            valori["og"], dettagli = _oggetto(conn, tipo, valori["id"])
        if isinstance(corpo, dict) and isinstance(corpo.get("nome"), str):
            valori["nome"] = corpo["nome"]
        descrizione = testo.format(**valori).removesuffix(": ")
        # i dati inviati che non ripetono quelli dell'oggetto
        gia = {e for e, _ in dettagli}
        if valori["nome"] and "{nome}" in testo:
            gia.add("Nome")  # è già nella descrizione
        return descrizione, dettagli + [(e, v) for e, v in dettagli_corpo(conn, corpo) if e not in gia]
    return f"{metodo} {percorso}", dettagli_corpo(conn, corpo)


def descrivi(metodo: str, percorso: str, conn=None) -> str:
    if conn is None:
        conn = _SENZA_DB
    return prepara(conn, metodo, percorso)[0]


class _SenzaDb:
    """Per descrivere un'azione senza database: gli oggetti restano indicati dal numero."""
    def execute(self, *_):
        return self

    def fetchone(self):
        return None


_SENZA_DB = _SenzaDb()


def crea_tabella(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    colonne = {r["name"] for r in conn.execute("PRAGMA table_info(registro_azioni)").fetchall()}
    if "dettagli" not in colonne:  # registro creato da una versione precedente
        try:
            with conn:
                conn.execute("ALTER TABLE registro_azioni ADD COLUMN dettagli TEXT NOT NULL DEFAULT '[]'")
        except Exception:  # due avvii insieme: l'altro l'ha già aggiunta
            pass


def registra(conn: sqlite3.Connection, accesso: str, metodo: str, percorso: str, esito: int,
             descrizione: str | None = None, quando: datetime | None = None,
             dettagli: list[tuple[str, str]] = ()) -> None:
    quando = (quando or datetime.now()).isoformat(timespec="seconds")
    with conn:
        cur = conn.execute(
            "INSERT INTO registro_azioni(quando, accesso, metodo, percorso, esito, descrizione, dettagli) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (quando, accesso, metodo, percorso, esito, descrizione or descrivi(metodo, percorso, conn),
             json.dumps([list(d) for d in dettagli], ensure_ascii=False)))
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
        f"SELECT id, quando, accesso, metodo, percorso, esito, descrizione, dettagli FROM registro_azioni {dove} "
        "ORDER BY id DESC LIMIT ?", (*parametri, limite)).fetchall()
    return [{**dict(r), "dettagli": json.loads(r["dettagli"] or "[]")} for r in righe]
