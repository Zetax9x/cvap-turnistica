"""Calendario dei turni per il telefono: un file .ics (RFC 5545) per dipendente.

Contiene i turni effettivi (cambi turno compresi) delle sole settimane confermate, da due mesi fa a un anno
avanti. Gli orari sono in UTC, calcolati dall'ora di Roma, così ogni calendario mostra l'inizio giusto anche
a cavallo del cambio dell'ora.

Gli eventi hanno solo l'orario di inizio (DTSTART, senza DTEND: durata zero secondo RFC 5545, 3.6.1): una notte
20–8 non occupa così due giorni del calendario. L'orario completo del turno ("Notte 20–8") resta nella
descrizione. Il file si raggiunge con un link segreto (`db_calendari`),
perché i programmi di calendario non possono inserire la password del sito.
"""
import hashlib
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db
from .email_turni import RUOLI, orario_turno
from .modello import EXTRA, leggi_extra, orario

ZONA = ZoneInfo("Europe/Rome")
GIORNI_PRIMA = 62    # turni passati che restano nel calendario
GIORNI_DOPO = 400    # turni futuri (di fatto: tutte le settimane già confermate)
LUNGHEZZA_RIGA = 75  # ottetti per riga, oltre si ripiega (RFC 5545, 3.1)
PRODID = "-//Croce Verde Ascoli Piceno//CVAP Turnistica//IT"


@dataclass(frozen=True)
class Evento:
    uid: str
    inizio: datetime  # con fuso orario
    fine: datetime  # non va nel file (solo l'inizio), ma resta per chi usa gli eventi
    titolo: str
    luogo: str
    descrizione: str


def slug(nome: str) -> str:
    """Il nome per il link: minuscolo, senza accenti, parole separate da trattini."""
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "dipendente"


def orari_utc(d: date, fascia: str, segmento: str) -> tuple[datetime, datetime]:
    """Inizio e fine di un turno in UTC, partendo dall'ora di Roma del giorno in cui inizia."""
    inizio, fine = orario(d, fascia, segmento)
    mezzanotte = datetime(d.year, d.month, d.day)
    base = d.toordinal() * 24

    def utc(ore: int) -> datetime:
        return (mezzanotte + timedelta(hours=ore - base)).replace(tzinfo=ZONA).astimezone(timezone.utc)

    return utc(inizio), utc(fine)


def testo_ics(testo: str) -> str:
    """Testo di una proprietà con i caratteri speciali protetti (RFC 5545, 3.3.11)."""
    return (testo.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _piega(riga: str) -> list[str]:
    """Una riga logica in righe di al massimo 75 ottetti, senza spezzare i caratteri UTF-8."""
    out, attuale, ottetti = [], "", 0
    for c in riga:
        n = len(c.encode())
        if ottetti + n > LUNGHEZZA_RIGA:
            out.append(attuale)
            attuale, ottetti = " ", 1  # le righe successive iniziano con uno spazio
        attuale += c
        ottetti += n
    out.append(attuale)
    return out


def _quando(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def componi(nome: str, eventi: list[Evento], adesso: datetime) -> str:
    righe = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{testo_ics(f'Turni - {nome}')}", "X-WR-TIMEZONE:Europe/Rome",
             "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    for e in sorted(eventi, key=lambda e: (e.inizio, e.uid)):
        righe += ["BEGIN:VEVENT", f"UID:{e.uid}", f"DTSTAMP:{_quando(adesso)}", f"DTSTART:{_quando(e.inizio)}",
                  f"SUMMARY:{testo_ics(e.titolo)}", f"LOCATION:{testo_ics(e.luogo)}",
                  f"DESCRIPTION:{testo_ics(e.descrizione)}", "TRANSP:OPAQUE", "END:VEVENT"]
    righe.append("END:VCALENDAR")
    return "".join(r + "\r\n" for riga in righe for r in _piega(riga))


def _uid(a) -> str:
    """Uguale finché il turno resta lo stesso, anche se la settimana viene rigenerata o riaperta."""
    chiave = f"{a.data.isoformat()}|{a.postazione}|{a.fascia}|{a.segmento}|{a.ruolo}|{a.persona_id}"
    return hashlib.sha256(chiave.encode()).hexdigest()[:32] + "@cvap-turnistica"


def eventi_persona(conn: sqlite3.Connection, persona_id: int, oggi: date) -> list[Evento]:
    """I turni effettivi della persona nelle settimane confermate, con i colleghi dello stesso turno."""
    dal, al = oggi - timedelta(days=GIORNI_PRIMA), oggi + timedelta(days=GIORNI_DOPO)
    confermate = {s["inizio"] for s in db.lista_settimane(conn) if s["stato"] == "confermata"}
    tutte = [a for _, a in db.assegnazioni_periodo(conn, dal, al)
             if (a.data - timedelta(days=a.data.weekday())).isoformat() in confermate]
    nomi = {p["id"]: p["nome"] for p in db.lista_persone(conn)}
    extra = {e["id"]: e["nome"] for e in db.extra_periodo(conn, dal, al)}

    def postazione(a) -> str:
        if a.postazione != EXTRA:
            return a.postazione
        dati = leggi_extra(a.segmento)
        nome = extra.get(dati[0]) if dati else None
        return f"{nome} ({EXTRA})" if nome else EXTRA

    out = []
    for a in tutte:
        if a.persona_id != persona_id:
            continue
        colleghi = sorted(f"{nomi.get(b.persona_id, '?')} ({b.ruolo})" for b in tutte
                          if b.persona_id != persona_id and b.data == a.data and b.postazione == a.postazione
                          and b.inizio < a.fine and a.inizio < b.fine)
        ruolo = RUOLI.get(a.ruolo, a.ruolo)
        righe = [orario_turno(a.fascia, a.segmento), f"Ruolo: {ruolo}"]
        if colleghi:
            righe.append("Con: " + ", ".join(colleghi))
        righe.append("Turni confermati - Croce Verde Ascoli Piceno")
        inizio, fine = orari_utc(a.data, a.fascia, a.segmento)
        luogo = postazione(a)
        out.append(Evento(_uid(a), inizio, fine, f"{luogo} · {ruolo}", luogo, "\n".join(righe)))
    return out
