"""PDF «Con chi si lavora» (A4 orizzontale), dalla pagina Statistiche → Equità.

Solo le coppie autista + soccorritore, per qualifica: due autisti nello stesso turno non contano. Prima una tabella
incrociata autisti × soccorritori con i turni fatti insieme (gli zeri, «mai insieme», in rosso), poi per ogni autista
e ogni soccorritore il dettaglio: con chi ha lavorato (dipendenti e volontari dell'altra qualifica), quante volte di
giorno e di notte, l'ultima volta insieme e con chi non ha mai lavorato. Dati da `confronti.con_chi`.
"""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import email_turni as et
from .pdf_equita import _CELLA, _GRIGLIA, _H2, _H3, _NOTA, _TESTA, _TESTO, _TITOLO, LARGHEZZA, Markup, _p, _tabella

_MAI_BG = colors.HexColor("#fde2e1")  # caselle «mai insieme» (testo #9f1d1d)
_CENTRO = _CELLA.clone("centro", alignment=1)
_TESTA_CENTRO = _TESTA.clone("testa_centro", alignment=1)


def _data(iso: str) -> str:
    return et._dmy(iso)


def _nome(d: dict) -> str:
    return escape(d["nome"]) + ("" if d["attivo"] else " <i>(non attivo)</i>")


def _matrice(dati: dict) -> list:
    autisti, soccorritori = dati["autisti"], dati["soccorritori"]
    if not autisti or not soccorritori:
        return [_p("Servono autisti e soccorritori con turni nel periodo.", _TESTO)]
    testa = [_p("Autista (riga) / soccorritore (colonna)", _TESTA)] + [_p(_nome(b), _TESTA_CENTRO) for b in soccorritori] + [
        _p("Soccorritori mai incontrati", _TESTA_CENTRO)]
    righe = [testa]
    stile = [("GRID", (0, 0), (-1, -1), 0.4, _GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(et.TESTA_BG)),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    for r, a in enumerate(autisti, start=1):
        riga = [_p(f"<b>{_nome(a)}</b>", _CELLA)]
        for c, b in enumerate(soccorritori, start=1):
            v = dati["matrice"][str(a["persona_id"])][str(b["persona_id"])]
            if v:
                riga.append(_p(str(v), _CENTRO))
            else:  # mai insieme: in rosso
                riga.append(_p('<font color="#9f1d1d"><b>0</b></font>', _CENTRO))
                stile.append(("BACKGROUND", (c, r), (c, r), _MAI_BG))
        riga.append(_p(str(len(a["mai"])), _CENTRO))
        righe.append(riga)
    # in fondo, per ogni soccorritore, quanti autisti non ha mai incontrato
    righe.append([_p("<b>Autisti mai incontrati</b>", _CELLA)] + [_p(str(len(b["mai"])), _CENTRO) for b in soccorritori]
                 + [_p("", _CENTRO)])
    stile.append(("BACKGROUND", (0, len(righe) - 1), (-1, len(righe) - 1), colors.HexColor(et.TESTA_BG)))
    nome, mai = 120, 70
    cella = (LARGHEZZA - nome - mai) / len(soccorritori)
    t = Table(righe, colWidths=[nome] + [cella] * len(soccorritori) + [mai], repeatRows=1)
    t.setStyle(TableStyle(stile))
    return [t, Spacer(1, 4),
            _p("Ogni casella: turni che l'autista della riga e il soccorritore della colonna hanno fatto insieme (stesso "
               "giorno, stessa postazione, stessa fascia). Conta la qualifica: due autisti nello stesso turno non "
               "contano, anche se uno dei due fa il soccorritore. In rosso le coppie che non hanno mai lavorato insieme.",
               _NOTA)]


def _scheda(d: dict, altri: str) -> list:
    """`altri`: "soccorritori" per un autista, "autisti" per un soccorritore."""
    titolo = _nome(d)
    dip = [c for c in d["colleghi"] if not c["volontario"]]
    vol = [c for c in d["colleghi"] if c["volontario"]]
    riassunto = (f"Turni nel periodo: <b>{d['turni']}</b> · con {altri}: <b>{d['in_compagnia']}</b> · "
                 f"{altri} dipendenti diversi: <b>{len(dip)}</b> · volontari: <b>{len(vol)}</b>")
    out = [Paragraph(titolo, _H3), _p(riassunto, _TESTO), Spacer(1, 3)]

    def righe(lista):
        return [[Markup(f"<b>{escape(c['nome'])}</b>"), c["turni"], c["giorno"], c["notte"], f"{c['percentuale']}%",
                 _data(c["ultima"])] for c in lista]
    intestazioni = ["Turni insieme", "Di giorno", "Di notte", "% dei suoi turni", "Ultima volta insieme"]
    larghezze = [30, 12, 10, 10, 13, 16]
    if dip:
        out.append(_tabella([f"Con i {altri} dipendenti", *intestazioni], righe(dip), larghezze, {1, 2, 3, 4}))
    if vol:
        out += [Spacer(1, 3), _tabella([f"Con i {altri} volontari", *intestazioni], righe(vol), larghezze, {1, 2, 3, 4})]
    if not d["colleghi"]:
        out.append(_p(f"Nel periodo non ha mai lavorato con {altri}.", _TESTO))
    out.append(Spacer(1, 3))
    if d["mai"]:
        nomi = ", ".join(escape(m["nome"]) + ("" if m["attivo"] else " (non attivo)") for m in d["mai"])
        out.append(_p(f'<font color="#9f1d1d"><b>Mai insieme a ({len(d["mai"])}):</b></font> {nomi}.', _TESTO))
    else:
        out.append(_p(f"Ha lavorato almeno una volta con tutti i {altri} dipendenti.", _TESTO))
    return [KeepTogether(out), Spacer(1, 8)]


def genera_colleghi(dati: dict, periodo: str) -> bytes:
    """`dati`: `confronti.con_chi`; `periodo`: es. "dal 19/10/2026 al 15/11/2026"."""
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=20, bottomMargin=20,
                            title="Con chi si lavora", author="Croce Verde Ascoli Piceno")
    settimane = dati.get("settimane", [])
    intro = (f"{len(settimane)} {'settimana confermata' if len(settimane) == 1 else 'settimane confermate'} con turni "
             f"generati, {escape(periodo)}. Si contano solo le coppie autista + soccorritore (per qualifica): lavorano "
             "insieme quando hanno un turno nello stesso giorno, nella stessa postazione e nella stessa fascia (giorno o "
             "notte), anche se uno dei due fa mezzo turno.")
    contenuto = [Paragraph("Con chi si lavora", _TITOLO), _p(intro, _TESTO), Spacer(1, 6)]
    if not dati.get("autisti") and not dati.get("soccorritori"):
        contenuto.append(_p("Nessuna settimana confermata con turni generati nel periodo.", _TESTO))
    else:
        contenuto += [Paragraph("Autisti e soccorritori: turni insieme", _H2), *_matrice(dati), PageBreak(),
                      Paragraph("Autisti: con quali soccorritori", _H2)]
        for d in dati["autisti"]:
            contenuto += _scheda(d, "soccorritori")
        contenuto += [PageBreak(), Paragraph("Soccorritori: con quali autisti", _H2)]
        for d in dati["soccorritori"]:
            contenuto += _scheda(d, "autisti")
    doc.build(contenuto, onFirstPage=_pie, onLaterPages=_pie)
    return out.getvalue()


def _pie(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#4d5868"))
    canvas.drawCentredString(landscape(A4)[0] / 2, 10,
                             f"Croce Verde Ascoli Piceno · Con chi si lavora · pagina {doc.page}")
    canvas.restoreState()
