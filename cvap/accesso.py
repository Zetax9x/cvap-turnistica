"""Password unica del sito: un cookie firmato con HMAC dice che chi naviga l'ha inserita.

La chiave di firma deriva dalla password e da un segreto casuale (SESSIONE_SEGRETO, o generato e
salvato nel database): cambiare la password, o il segreto, invalida tutte le sessioni aperte.
Le sessioni non sono salvate sul server, quindi funziona anche su Vercel.
"""
import hashlib
import hmac
import time

COOKIE = "cvap_sessione"
DURATA_S = 14 * 24 * 3600  # 14 giorni


def chiave(password: str, segreto: str = "") -> bytes:
    return hashlib.sha256(f"cvap-sessione\0{segreto}\0{password}".encode()).digest()


def _firma(k: bytes, scadenza: int) -> str:
    return hmac.new(k, str(scadenza).encode(), hashlib.sha256).hexdigest()


def crea_token(k: bytes, adesso: float | None = None) -> str:
    scadenza = int(adesso if adesso is not None else time.time()) + DURATA_S
    return f"{scadenza}.{_firma(k, scadenza)}"


def token_valido(k: bytes, token: str | None, adesso: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    scadenza_s, firma = token.split(".", 1)
    if not scadenza_s.isdigit():
        return False
    scadenza = int(scadenza_s)
    if scadenza < (adesso if adesso is not None else time.time()):
        return False
    return hmac.compare_digest(firma, _firma(k, scadenza))


def password_giusta(inserita: str, password: str) -> bool:
    return hmac.compare_digest(inserita.encode(), password.encode())
