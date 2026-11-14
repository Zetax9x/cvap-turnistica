"""PDF del tabellone e dei dipendenti liberi di una settimana (A4 orizzontale), per l'app e per la stampa.

Lavora sul payload della settimana come le email: riusa da `email_turni` le righe, le celle e i testi,
così il foglio coincide con quello che si vede nella pagina.
"""
from datetime import date
from html import escape

from reportlab.lib import colors
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table

from . import email_turni as et
from . import pdf_stile as st
from .modello import EXTRA

_PICCOLO = st.CELLA
_CENTRO = st.TESTA_CENTRO
_NOTA = st.NOTA


def _c(hex_: str):
    return colors.HexColor(hex_)


def _periodo(s: dict) -> str:
    return f"Settimana dal {et._dmy(s['inizio'])} al {et._dmy(s['fine'])}"


def _testa_giorni(s: dict) -> tuple[list, list]:
    """Intestazioni dei sette giorni e regole di sfondo (weekend e festività)."""
    celle, regole = [], []
    for i, g in enumerate(s["giorni"], start=1):
        feste = et._nomi_feste(s, g)
        testo = f"{et.GIORNI_BREVI[date.fromisoformat(g).weekday()]} {et._dm(g)}"
        if feste:
            testo += f'<br/><font size="7" color="{et.FESTIVO_TESTO}">{escape(feste)}</font>'
            regole.append(("BACKGROUND", (i, 0), (i, 0), _c(et.FESTIVO_BG)))
        elif date.fromisoformat(g).weekday() >= 5:
            regole.append(("BACKGROUND", (i, 0), (i, 0), _c(et.WEEKEND_BG)))
        celle.append(Paragraph(testo, _CENTRO))
    return celle, regole


def _voci(persone: list[dict], scoperte: list[str]) -> list[Paragraph]:
    out = []
    for p in persone:
        nome = f"<b>{escape(p['nome'])}</b>" + (f" {escape(p['orario'])}" if p["orario"] else "")
        if p["volontario"]:
            nome = f'<font backColor="{et.VOL_BG}" color="{et.VOL_TESTO}">{nome}</font>'
        out.append(Paragraph(nome, _PICCOLO))
    out += [Paragraph(f'<font color="{et.ROSSO}"><b>{escape(x)}</b></font>', _PICCOLO) for x in scoperte]
    return out or [Paragraph("—", _PICCOLO)]


def _tabella(righe: list[list], regole: list, larghezza: float) -> Table:
    colonne = [72] + [(larghezza - 72) / 7] * 7
    t = Table(righe, colWidths=colonne, repeatRows=1)
    t.setStyle(st.stile_griglia(regole))
    return t


def blocchi_tabellone(s: dict) -> list:
    """Le griglie del tabellone di una settimana (una per postazione, più Assistenze ed Extra): le stesse per il
    download e per l'email dei cambi turno."""
    larghezza = st.larghezza()
    testa, regole_testa = _testa_giorni(s)
    blocchi = []
    for postazione in et._postazioni(s):
        righe = [[Paragraph("Turno", _CENTRO), *testa]]
        regole = list(regole_testa)
        for i, (fascia, segmento, ruolo, turno) in enumerate(et._righe(postazione), start=1):
            sfondo = _c(et.GIORNO_BG if fascia == "giorno" else et.NOTTE_BG)
            etichetta = Paragraph(f"{escape(turno)}<br/><b>{et.RUOLI[ruolo]}</b>", _PICCOLO)
            righe.append([etichetta] + [_voci(*et._cella(s, postazione, g, fascia, segmento, ruolo)) for g in s["giorni"]])
            regole.append(("BACKGROUND", (0, i), (-1, i), sfondo))
            if i > 1 and ruolo == "autista":
                regole.append(("LINEABOVE", (0, i), (-1, i), 1.5, colors.black))
        blocchi.append(KeepTogether([Paragraph(escape(postazione), st.H3), _tabella(righe, regole, larghezza),
                                     Spacer(1, 6)]))
    if s.get("extra"):
        celle = []
        for g in s["giorni"]:
            schede = []
            for e in et._richieste_extra(s, g):
                schede.append(Paragraph(f"<b>{escape(e['nome'])}</b> {escape(et._ore(e['fascia'], e['segmento']))}", _PICCOLO))
                for ruolo in et._ruoli_extra(e):
                    persone, scoperte = et._cella(s, EXTRA, g, e["fascia"], e["segmento"], ruolo)
                    schede.append(Paragraph(f"<i>{et.RUOLI[ruolo]}</i>", _NOTA))
                    schede += _voci(persone, scoperte)
            celle.append(schede or [Paragraph("—", _PICCOLO)])
        blocchi.append(KeepTogether([Paragraph(EXTRA, st.H3),
                                     _tabella([[Paragraph("Richieste", _CENTRO), *testa], [Paragraph("Assistenze<br/>ed Extra", _PICCOLO), *celle]],
                                              regole_testa, larghezza)]))
    blocchi.append(_legenda())
    return blocchi


def _legenda() -> Paragraph:
    return Paragraph(
        f'<font backColor="{et.GIORNO_BG}">&nbsp;Giorno&nbsp;</font> &nbsp; '
        f'<font backColor="{et.NOTTE_BG}">&nbsp;Notte&nbsp;</font> &nbsp; '
        f'<font backColor="{et.VOL_BG}" color="{et.VOL_TESTO}">&nbsp;<b>Volontario</b>&nbsp;</font> &nbsp; '
        f'<font color="{et.ROSSO}"><b>scoperto</b></font> = posto senza nessuno · '
        "accanto al nome l'orario, se fa solo una parte del turno.", st.NOTA)


def genera_tabellone(s: dict, avviso: str | None = None) -> bytes:
    """Il tabellone di una settimana. `avviso`: es. "Aggiornato con i cambi turno" (email dei cambi turno)."""
    return st.documento("Tabellone dei turni", _periodo(s) + _versione(s), blocchi_tabellone(s), avviso=avviso)


def genera_tabelloni(settimane: list[dict], avviso: str | None = None) -> bytes:
    """Più settimane nello stesso PDF (email dei cambi turno), una per pagina, con lo stesso disegno."""
    blocchi = []
    for n, s in enumerate(settimane):
        if n:
            blocchi.append(PageBreak())
        if len(settimane) > 1:
            blocchi.append(Paragraph(escape(_periodo(s) + _versione(s)), st.H2))
        blocchi += blocchi_tabellone(s)
    sottotitolo = _periodo(settimane[0]) if len(settimane) == 1 else (
        f"Dal {et._dmy(settimane[0]['inizio'])} al {et._dmy(settimane[-1]['fine'])}")
    return st.documento("Tabellone dei turni", sottotitolo, blocchi, avviso=avviso)


def _versione(s: dict) -> str:
    return " · turni generati (senza i cambi turno)" if s.get("versione") == "generati" else ""


def genera_liberi(s: dict) -> bytes:
    larghezza = st.larghezza()
    testa, regole = _testa_giorni(s)
    righe = [[Paragraph("", _CENTRO), *testa]]
    for chiave, titolo, bg in (("liberi", "Liberi", "#e3f2e6"), ("indisponibili", "Indisponibili", "#fdf0d5"),
                               ("ferie", "Ferie / malattia", "#e3eafa")):
        celle = []
        for g in s.get("liberi", []):
            voci = []
            for x in g[chiave]:
                note = [", ".join(et.PARTI[p] for p in x.get("parti", []))] if x.get("parti") else []
                note += [et.AVVISI.get(a, a) for a in x.get("avvisi", [])]
                if x.get("motivo"):
                    note.append("malattia" if x["motivo"] == "malattia" else "ferie")
                nota = ", ".join(n for n in note if n)
                voci.append(Paragraph(f"<b>{escape(x['nome'])}</b>" + (f" <i>({escape(nota)})</i>" if nota else ""), _PICCOLO))
            celle.append(voci or [Paragraph("—", _PICCOLO)])
        righe.append([Paragraph(f"<b>{titolo}</b>", _PICCOLO), *celle])
        regole.append(("BACKGROUND", (0, len(righe) - 1), (0, len(righe) - 1), _c(bg)))
    nota = Paragraph("Smonto notte = ha fatto la notte il giorno prima (finisce alle 8) · notte = fa la notte quella sera.", _NOTA)
    return st.documento("Dipendenti liberi", _periodo(s), [_tabella(righe, regole, larghezza), Spacer(1, 6), nota])
