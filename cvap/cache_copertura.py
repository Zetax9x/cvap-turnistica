"""Cache in memoria dei controlli di copertura preventiva (il Calendario ne lancia 12 per ogni mese, ~5 secondi).

Un risultato vale finché nessuna richiesta modifica i dati (`invalida`) e per al più `scadenza_s` secondi: la scadenza
copre le modifiche fatte fuori dal server (altri processi sullo stesso database)."""

import threading
import time
from collections.abc import Callable, Hashable
from typing import Any

SCADENZA_S = 600


class CacheCopertura:
    def __init__(self, scadenza_s: float = SCADENZA_S, orologio: Callable[[], float] = time.monotonic):
        self._scadenza_s = scadenza_s
        self._orologio = orologio
        self._lock = threading.Lock()
        self._versione = 0
        self._voci: dict[Hashable, tuple[float, Any]] = {}

    def invalida(self) -> None:
        """Da chiamare quando i dati cambiano: i risultati in corso di calcolo non verranno più salvati."""
        with self._lock:
            self._versione += 1
            self._voci.clear()

    def prendi(self, chiave: Hashable, calcola: Callable[[], Any]) -> Any:
        """Il risultato salvato per `chiave`, o `calcola()` (fuori dal lock: è lento) se manca o è scaduto."""
        with self._lock:
            versione = self._versione
            voce = self._voci.get(chiave)
            if voce is not None and self._orologio() - voce[0] < self._scadenza_s:
                return voce[1]
        valore = calcola()
        with self._lock:
            if self._versione == versione:  # nel frattempo non è cambiato nulla
                self._voci[chiave] = (self._orologio(), valore)
        return valore
