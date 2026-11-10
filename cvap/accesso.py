"""Password del sito: un cookie firmato con HMAC dice che chi naviga l'ha inserita, e quale.

Le password sono due: quella normale (APP_PASSWORD) e, facoltativa, quella master (APP_PASSWORD_MASTER),
che in più vede il registro delle azioni. Il cookie porta il ruolo ("normale" o "master") dentro la firma,
quindi non si può cambiare a mano.

La chiave di firma deriva dalla password e da un segreto casuale (SESSIONE_SEGRETO, o generato e
salvato nel database): cambiare la password, o il segreto, invalida tutte le sessioni aperte.
Le sessioni non sono salvate sul server, quindi funziona anche su Vercel.
"""
import hashlib
import hmac
import re
import time

COOKIE = "cvap_sessione"
DURATA_S = 14 * 24 * 3600  # 14 giorni


def chiave(password: str, segreto: str = "") -> bytes:
    return hashlib.sha256(f"cvap-sessione\0{segreto}\0{password}".encode()).digest()


def _firma(k: bytes, dati) -> str:
    return hmac.new(k, str(dati).encode(), hashlib.sha256).hexdigest()


NORMALE, MASTER = "normale", "master"
RUOLI = (NORMALE, MASTER)


def crea_token(k: bytes, adesso: float | None = None, ruolo: str = NORMALE) -> str:
    if ruolo not in RUOLI:
        raise ValueError(f"ruolo sconosciuto: {ruolo}")
    scadenza = int(adesso if adesso is not None else time.time()) + DURATA_S
    if ruolo == NORMALE:  # stesso formato di prima: le sessioni già aperte restano valide
        return f"{scadenza}.{_firma(k, scadenza)}"
    return f"{scadenza}.{ruolo}.{_firma(k, f'{scadenza}.{ruolo}')}"


def ruolo_token(k: bytes, token: str | None, adesso: float | None = None) -> str | None:
    """Il ruolo del cookie ("normale" o "master"), o None se il cookie non è valido o è scaduto."""
    if not token or "." not in token:
        return None
    parti = token.split(".")
    if len(parti) == 2:
        (scadenza_s, firma), ruolo, firmato = parti, NORMALE, parti[0]
    elif len(parti) == 3 and parti[1] == MASTER:
        scadenza_s, ruolo, firma = parti
        firmato = f"{scadenza_s}.{ruolo}"
    else:
        return None
    if not scadenza_s.isdigit() or int(scadenza_s) < (adesso if adesso is not None else time.time()):
        return None
    return ruolo if hmac.compare_digest(firma, _firma(k, firmato)) else None


def token_valido(k: bytes, token: str | None, adesso: float | None = None) -> bool:
    return ruolo_token(k, token, adesso) is not None


def password_giusta(inserita: str, password: str) -> bool:
    return hmac.compare_digest(inserita.encode(), password.encode())


# --- modalità semplice ------------------------------------------------------------------------
# Con la password master configurata, chi entra con quella normale usa solo la procedura guidata
# (pagina "Turni della settimana"): queste sono le sole API che le servono.
_D = r"\d{4}-\d{2}-\d{2}"
API_SEMPLICE = [(metodo, re.compile(percorso + "$")) for metodo, percorso in (
    ("GET", r"/api/(sessione|persone|ferie)"),
    ("GET", rf"/api/settimane/{_D}"),
    ("GET", rf"/api/settimane/{_D}/pdf-(tabellone|liberi)"),
    ("POST", r"/api/(accesso|uscita|ferie)"),
    ("POST", rf"/api/settimane/{_D}/(assegnazioni|genera|conferma|riapri)"),
    ("POST", rf"/api/settimane/{_D}/extra"),
    ("PUT", rf"/api/settimane/{_D}/(indisponibilita|fabbisogno)"),
    ("DELETE", r"/api/(assegnazioni|ferie|extra)/\d+"),
)]


def consentita_in_semplice(metodo: str, percorso: str) -> bool:
    return any(m == metodo and r.match(percorso) for m, r in API_SEMPLICE)
