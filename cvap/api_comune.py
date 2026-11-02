"""Tipi e helper condivisi dalle route dell'API (app.py e i router dei singoli argomenti)."""
from datetime import date
from typing import Annotated

from fastapi import HTTPException, Path as PathParam
from pydantic import Field, StringConstraints

DATA_MIN, DATA_MAX = date(2000, 1, 1), date(2100, 12, 31)
DataValida = Annotated[date, Field(ge=DATA_MIN, le=DATA_MAX)]

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100,
                                        pattern=r"^[^\x00-\x1f\x7f]+$")]  # niente caratteri di controllo
ID_MAX = 2 ** 63 - 1  # oltre, SQLite non accetta l'intero (OverflowError -> 500)
Id = Annotated[int, Field(ge=1, le=ID_MAX)]
IdPath = Annotated[int, PathParam(ge=1, le=ID_MAX)]


def errore(messaggio: str) -> HTTPException:
    """Errore di dominio (400) con messaggio per l'utente."""
    return HTTPException(status_code=400, detail=messaggio)
