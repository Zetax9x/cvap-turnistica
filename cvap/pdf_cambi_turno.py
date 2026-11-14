"""PDF allegato all'email dei cambi turno: lo stesso tabellone che si scarica dal sito e dall'app
(`pdf_tabellone`), con un riquadro che dice che è aggiornato con i cambi turno (o che è una rettifica)."""
from .pdf_tabellone import genera_tabelloni

AGGIORNATO = "Tabellone aggiornato con i cambi turno: fa fede questo foglio."
RETTIFICA = "Rettifica: un cambio turno è stato annullato e i turni sono tornati come prima. Fa fede questo foglio."


def genera(settimane, rettifica=False) -> bytes:
    return genera_tabelloni(list(settimane), avviso=RETTIFICA if rettifica else AGGIORNATO)
