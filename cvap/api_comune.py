"""Tipi e helper condivisi dalle route dell'API (app.py e i router dei singoli argomenti)."""
from datetime import date
from typing import Annotated

from fastapi import HTTPException, Path as PathParam, Response
from pydantic import Field, StringConstraints

DATA_MIN, DATA_MAX = date(2000, 1, 1), date(2100, 12, 31)
DataValida = Annotated[date, Field(ge=DATA_MIN, le=DATA_MAX)]

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100,
                                        pattern=r"^[^\x00-\x1f\x7f]+$")]  # niente caratteri di controllo
ID_MAX = 2 ** 63 - 1  # oltre, SQLite non accetta l'intero (OverflowError -> 500)
Id = Annotated[int, Field(ge=1, le=ID_MAX)]
IdPath = Annotated[int, PathParam(ge=1, le=ID_MAX)]


def risposta_pdf(contenuto: bytes, nome: str) -> Response:
    """Un PDF fatto dal server, da scaricare (nome del file in `nome`), mai dalla cache."""
    return Response(contenuto, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})


def descrivi_periodo(dal: date | None, al: date | None, vuoto: str = "Tutto lo storico") -> str:
    """Il periodo scelto a parole, per il sottotitolo dei PDF: «Dal 01/10/2026 al 31/10/2026»."""
    if dal and al:
        return f"Dal {dal:%d/%m/%Y} al {al:%d/%m/%Y}"
    if dal:
        return f"Dal {dal:%d/%m/%Y}"
    if al:
        return f"Fino al {al:%d/%m/%Y}"
    return vuoto


def errore(messaggio: str) -> HTTPException:
    """Errore di dominio (400) con messaggio per l'utente."""
    return HTTPException(status_code=400, detail=messaggio)
