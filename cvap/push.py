"""Notifiche push per il telefono (PWA su iPhone da iOS 16.4, anche Android e computer).

Un solo dispositivo iscritto: una nuova iscrizione sostituisce la precedente. Tutto sta nella tabella
`impostazioni` (nessuna tabella nuova): la chiave privata VAPID, creata al primo uso, e l'iscrizione.
Le notifiche non fanno mai fallire l'operazione che le provoca: l'invio parte in un thread e gli errori
finiscono nel log.
"""
import base64
import json
import logging
import os
import threading

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid

_log = logging.getLogger(__name__)
CH_PRIVATA = "push_vapid_privata"
CH_ISCRIZIONE = "push_iscrizione"
TIMEOUT_S = 10


class IscrizioneScaduta(Exception):
    """Il servizio push dice che l'iscrizione non esiste più (telefono cambiato, app disinstallata)."""


def _leggi(conn, chiave: str) -> str | None:
    r = conn.execute("SELECT valore FROM impostazioni WHERE chiave = ?", (chiave,)).fetchone()
    return r["valore"] if r else None


def _chiave_privata(conn) -> str:
    """Chiave VAPID in formato PEM: generata una volta sola e conservata (cambiarla invaliderebbe l'iscrizione)."""
    if _leggi(conn, CH_PRIVATA) is None:
        v = Vapid()
        v.generate_keys()
        with conn:
            conn.execute("INSERT OR IGNORE INTO impostazioni(chiave, valore) VALUES (?, ?)",
                         (CH_PRIVATA, v.private_pem().decode()))
    return _leggi(conn, CH_PRIVATA)


def chiave_pubblica(conn) -> str:
    """Chiave pubblica del server nel formato che il browser vuole (punto non compresso, base64 url)."""
    v = Vapid.from_pem(_chiave_privata(conn).encode())
    raw = v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def iscrizione(conn) -> dict | None:
    valore = _leggi(conn, CH_ISCRIZIONE)
    return json.loads(valore) if valore else None


def salva_iscrizione(conn, endpoint: str, p256dh: str, auth: str) -> None:
    dati = {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}
    with conn:
        conn.execute("INSERT INTO impostazioni(chiave, valore) VALUES (?, ?) "
                     "ON CONFLICT(chiave) DO UPDATE SET valore = excluded.valore", (CH_ISCRIZIONE, json.dumps(dati)))


def togli_iscrizione(conn) -> None:
    with conn:
        conn.execute("DELETE FROM impostazioni WHERE chiave = ?", (CH_ISCRIZIONE,))


def _contatto() -> str:
    """Il servizio push vuole un contatto dell'invio (mailto: o https:)."""
    esplicito = os.environ.get("PUSH_CONTATTO", "").strip()
    if esplicito:
        return esplicito
    mittente = os.environ.get("EMAIL_MITTENTE", "").strip()
    return f"mailto:{mittente}" if mittente else "mailto:turni@example.com"


def _spedisci(sottoscrizione: dict, payload: str, pem: str) -> None:
    """Invio vero al servizio push. Separata per poterla sostituire nei test."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info=sottoscrizione, data=payload, vapid_private_key=Vapid.from_pem(pem.encode()),
                vapid_claims={"sub": _contatto()}, ttl=3600, timeout=TIMEOUT_S)
    except WebPushException as e:
        stato = getattr(getattr(e, "response", None), "status_code", None)
        if stato in (404, 410):
            raise IscrizioneScaduta() from e
        raise


def prepara(conn, titolo: str, testo: str, url: str) -> tuple[dict, str, str] | None:
    """Tutto ciò che serve per spedire (letto mentre la connessione c'è), o None se nessuno è iscritto."""
    sott = iscrizione(conn)
    if sott is None:
        return None
    return sott, json.dumps({"titolo": titolo, "testo": testo, "url": url}), _chiave_privata(conn)


def spedisci_in_background(sottoscrizione: dict, payload: str, pem: str) -> None:
    def lavoro():
        try:
            _spedisci(sottoscrizione, payload, pem)
        except IscrizioneScaduta:
            _log.warning("Notifica push non consegnata: iscrizione scaduta, va riattivata dall'app")
        except Exception:  # noqa: BLE001 - una notifica persa non deve mai disturbare altro
            _log.exception("Notifica push non inviata")
    threading.Thread(target=lavoro, daemon=True, name="push").start()
