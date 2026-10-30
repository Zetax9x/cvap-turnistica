"""Invio delle email via SMTP (Gmail, Brevo o altro servizio), configurato con variabili d'ambiente:

    SMTP_HOST, SMTP_PORT (587 = STARTTLS, 465 = SSL), SMTP_USER, SMTP_PASSWORD,
    EMAIL_MITTENTE (predefinito SMTP_USER), EMAIL_NOME_MITTENTE

Senza SMTP_HOST l'invio non è configurato e l'interfaccia lo spiega.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

NOME_MITTENTE = "Croce Verde Ascoli Piceno - Turni"
log = logging.getLogger("cvap.posta")


class PostinoBloccato:
    """Invio disattivato di proposito (es. sito pubblico senza password): `motivo` lo spiega."""

    configurato = False

    def __init__(self, motivo: str):
        self.motivo = motivo

    def invia(self, messaggi):
        return {m["To"]: self.motivo for m in messaggi}


class PostinoSmtp:
    def __init__(self, host: str | None, porta: int = 587, utente: str = "", password: str = "",
                 mittente: str = "", nome_mittente: str = NOME_MITTENTE, timeout: float = 20.0):
        self.host, self.porta, self.utente, self.password = host, porta, utente, password
        self.mittente = mittente or utente
        self.nome_mittente = nome_mittente
        self.timeout = timeout

    @classmethod
    def da_ambiente(cls) -> "PostinoSmtp":
        env = os.environ
        porta = env.get("SMTP_PORT", "").strip()
        return cls(env.get("SMTP_HOST") or None, int(porta) if porta.isdigit() else 587, env.get("SMTP_USER", ""),
                   env.get("SMTP_PASSWORD", ""), env.get("EMAIL_MITTENTE", ""),
                   env.get("EMAIL_NOME_MITTENTE") or NOME_MITTENTE)

    @property
    def configurato(self) -> bool:
        return bool(self.host and self.mittente)

    @property
    def da(self) -> str:
        return formataddr((self.nome_mittente, self.mittente))

    def invia(self, messaggi: list[EmailMessage]) -> dict[str, str | None]:
        """Invia con una sola connessione. Esito per destinatario: None se partito, altrimenti l'errore."""
        esito: dict[str, str | None] = {}
        if not messaggi:
            return esito
        contesto = ssl.create_default_context()
        try:
            if self.porta == 465:
                server = smtplib.SMTP_SSL(self.host, self.porta, timeout=self.timeout, context=contesto)
            else:
                server = smtplib.SMTP(self.host, self.porta, timeout=self.timeout)
                server.starttls(context=contesto)
            with server:
                if self.utente:
                    server.login(self.utente, self.password)
                for m in messaggi:
                    if "From" not in m:
                        m["From"] = self.da
                    try:
                        server.send_message(m)
                        esito[m["To"]] = None
                    except smtplib.SMTPException as e:
                        log.warning("invio non riuscito: %s", e)
                        esito[m["To"]] = _breve(e)
        except (OSError, smtplib.SMTPException) as e:
            log.warning("server di posta: %s", e)  # il dettaglio resta nei log, non va al browser
            errore = "Server di posta non raggiungibile o accesso rifiutato (controlla le impostazioni SMTP)"
            for m in messaggi:
                esito.setdefault(m["To"], errore)
        return esito


def _breve(e: Exception) -> str:
    """Messaggio per l'interfaccia: il codice SMTP, senza dettagli del server."""
    codice = getattr(e, "smtp_code", None)
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "Indirizzo rifiutato dal server di posta"
    return f"Invio rifiutato dal server di posta (codice {codice})" if codice else "Invio non riuscito"
