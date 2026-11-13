"""PDF dell'equità dei turni (A4 orizzontale), allegato all'email dell'equità a ogni settimana confermata.

Stessi contenuti che prima erano nel corpo dell'email: esito della generazione, ogni criterio dell'equità
(festività escluse) con il dettaglio per dipendente, gli altri confronti, le statistiche dei turni e delle
indisponibilità. I testi e i formati dei numeri vengono da `email_turni`, così PDF ed email dicono lo stesso.
"""
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import email_turni as et

_STILI = getSampleStyleSheet()
_TITOLO = _STILI["Title"]
_H2 = ParagraphStyle("h2", parent=_STILI["Heading2"], textColor=colors.HexColor(et.VERDE), spaceBefore=4, spaceAfter=4)
_H3 = ParagraphStyle("h3", parent=_STILI["Heading3"], fontSize=11, spaceBefore=8, spaceAfter=2)
_TESTO = ParagraphStyle("testo", fontName="Helvetica", fontSize=9, leading=12)
_CELLA = ParagraphStyle("cella", fontName="Helvetica", fontSize=8, leading=10)
_NOTA = ParagraphStyle("nota", parent=_CELLA, fontSize=7.5, textColor=colors.HexColor("#4d5868"))
_TESTA = ParagraphStyle("testa", parent=_CELLA, fontName="Helvetica-Bold")
_DESTRA = ParagraphStyle("destra", parent=_CELLA, alignment=2)
_TESTA_DESTRA = ParagraphStyle("testa_destra", parent=_TESTA, alignment=2)


class Markup(str):
    """Testo di una cella già in formato reportlab (grassetto, colori): non va escapato."""
_GRIGLIA = colors.HexColor("#c3cbd6")
_SOPRA, _SOTTO = "#c2410c", "#1d4ed8"  # come nella pagina Equità: arancio più della sua parte, blu meno
LARGHEZZA = landscape(A4)[0] - 36
# senza frecce: i caratteri standard dei PDF non le hanno
_ANDAMENTO = {"si_avvicina": "si avvicina alla sua parte", "si_allontana": "si allontana dalla sua parte", "stabile": "stabile"}


def _p(testo, stile=_CELLA) -> Paragraph:
    return Paragraph(testo if isinstance(testo, str) else escape(str(testo)), stile)


def _tabella(intestazioni: list[str], righe: list[list], larghezze: list[float], destra: set[int] = frozenset()) -> Table:
    dati = [[_p(escape(t), _TESTA_DESTRA if i in destra else _TESTA) for i, t in enumerate(intestazioni)]]
    for riga in righe:
        dati.append([Paragraph(c if isinstance(c, Markup) else escape(str(c)), _DESTRA if i in destra else _CELLA)
                     for i, c in enumerate(riga)])
    totale = sum(larghezze)
    t = Table(dati, colWidths=[w * LARGHEZZA / totale for w in larghezze], repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, _GRIGLIA), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(et.TESTA_BG)),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
    return t


def _scarto(x) -> str:
    if x is None:
        return "—"
    colore = _SOPRA if x > 0 else _SOTTO if x < 0 else "#1b2330"
    return Markup(f'<font color="{colore}"><b>{escape(et._scarto(x))}</b></font>')


def _generazione(s: dict) -> list:
    report = s.get("report") or {}
    q = report.get("qualita") or {}
    scoperti = report.get("scoperti") or []
    voci = (report.get("diagnostica") or {}).get("voci") or []
    righe = [f"Soluzione: <b>{'ottima' if report.get('stato') == 'ottimo' else 'buona, non dimostrata ottima'}</b>"]
    if q:
        righe.append(f"distanza dall'ottimo {et._num(q.get('gap_pct'))}%, durata {et._num(q.get('durata_s'))} s")
    righe.append(f"posti scoperti: <b>{len(scoperti) or 'nessuno'}</b>")
    out = [Paragraph("Generazione della settimana", _H2), _p(" · ".join(righe), _TESTO)]
    if scoperti:
        out.append(_p("<br/>".join(escape(f"{et._dm(u['data'])} · {u['postazione']} · {u['fascia']} · {u['ruolo']}")
                                   for u in scoperti), _TESTO))
    if voci:
        regole = [v for v in voci if v["tipo"] == "regola" and v.get("quante")]
        out.append(_p("<b>Regole allentate:</b> " + (escape("; ".join(f"{v['etichetta']} ({v['quante']})" for v in regole))
                                                    if regole else "nessuna"), _TESTO))
        equita = [v for v in voci if v["tipo"] == "equita" and v["voce"] != "festivita"]
        totale = sum(abs(v["punti"]) for v in equita) or 1
        out.append(_p("<b>Peso dei criteri di equità in questa settimana:</b> " + escape("; ".join(
            f"{v['etichetta']} {round(abs(v['punti']) / totale * 100)}%" for v in equita)), _TESTO))
    return out


def _equita(quadro: dict, assenze: dict[int, str]) -> list:
    rotazioni = [r for r in quadro.get("rotazioni", []) if r.get("con_dati", True) and not r.get("festivita")]
    settimane = quadro.get("settimane", [])
    out = [Paragraph("Equità dei turni", _H2)]
    if not rotazioni:
        return out + [_p("Nessuna settimana confermata con turni generati.", _TESTO)]
    out.append(_p(
        f"Calcolata su {len(settimane)} {'settimana' if len(settimane) == 1 else 'settimane'} confermate con turni generati"
        + (f", dal {et._dmy(settimane[0])}" if settimane else "") + ". Scarto positivo: ha fatto più della sua parte; "
        "negativo: meno. È lo stesso calcolo che usa il generatore. Nelle note i giorni di ferie e di malattia inseriti nel "
        "periodo. Ore lavorate: come nel generatore, le settimane con ferie o malattia (anche di un solo giorno) non "
        "cambiano lo scarto, così chi è stato assente non risulta indietro; nelle ore fatte ogni giorno di assenza conta "
        "6 ore e le settimane di assenza intera non ci sono. Andamento: lo scarto di oggi rispetto a 4 settimane generate fa.",
        _NOTA))
    for rot in rotazioni:
        unita = "turno" if rot.get("differenza") == 1 and rot.get("unita") == "turni" else rot.get("unita", "turni")
        riassunto = [f"Differenza tra chi è più avanti e chi è più indietro: <b>{et._num(rot.get('differenza'))} {unita}</b>"]
        if rot.get("tendenza"):
            riassunto.append(et._TENDENZA.get(rot["tendenza"], rot["tendenza"]))
        estremi = [f"{nome} {escape(x['nome'])} ({et._scarto(x['scarto'])})"
                   for nome, x in (("più avanti", rot.get("piu_avanti")), ("più indietro", rot.get("piu_indietro"))) if x]
        righe = []
        for d in rot.get("dipendenti", []):
            nota = "; ".join(x for x in ("" if d["partecipa"] else (d.get("motivo") or "non partecipa"),
                                         assenze.get(d["persona_id"], "")) if x)
            righe.append([Markup(f"<b>{escape(d['nome'])}</b>" + ("" if d.get("attivo", True) else " <i>(non attivo)</i>")),
                          et._num(d["fatti"]), et._num(d["quota"]), _scarto(d["scarto"]),
                          et._scarto(d.get("scarto_prima")), _ANDAMENTO.get(d.get("andamento"), "—"), nota])
        out.append(KeepTogether([
            Paragraph(escape(rot["nome"]), _H3),
            _p(" · ".join(riassunto) + (f"<br/>{'; '.join(estremi)}" if estremi else ""), _TESTO), Spacer(1, 3),
            _tabella(["Dipendente", rot.get("fatti", "Fatti"), rot.get("quota", "La sua parte"), "Scarto", "4 settimane fa",
                      "Andamento", "Note"], righe, [18, 10, 10, 8, 9, 17, 28], {1, 2, 3, 4}),
            _p(f"Scarto positivo: {escape(rot.get('sopra', ''))}; negativo: {escape(rot.get('sotto', ''))}.", _NOTA)]))
    return out


def _confronti(c: dict) -> list:
    out = [Paragraph("Altri confronti", _H2)]
    if not c or not c.get("settimane"):
        return out + [_p("Nessuna settimana confermata con turni generati.", _TESTO)]
    w = c["weekend_liberi"]
    out += [KeepTogether([
        Paragraph("Weekend interi liberi", _H3),
        _p(f"Differenza tra chi ne ha avuti di più e chi di meno: <b>{et._num(w['differenza'])}</b> · media del gruppo "
           f"{et._num(w['media'])}% dei weekend. Nessun turno né sabato né domenica; le settimane tutte in ferie o malattia "
           "non contano.", _TESTO), Spacer(1, 3),
        _tabella(["Dipendente", "Weekend liberi", "Settimane", "La sua parte", "Scarto"],
                 [[d["nome"], d["liberi"], d["settimane"], et._num(d["quota"]), _scarto(d["scarto"])] for d in w["dipendenti"]],
                 [30, 15, 15, 15, 15], {1, 2, 3, 4})])]
    out += [KeepTogether([
        Paragraph("Sequenze pesanti", _H3),
        _p("Notti di fila: due notti in giorni consecutivi. Tre di fila: tre giorni consecutivi nella stessa fascia. "
           "Giorni di fila: il massimo di giorni consecutivi con almeno un turno.", _TESTO), Spacer(1, 3),
        _tabella(["Dipendente", "Notti di fila", "Tre di fila", "Massimo giorni di fila"],
                 [[d["nome"], d["notti_di_fila"], d["tre_di_fila"], d["giorni_di_fila_max"]] for d in c["sequenze"]],
                 [30, 20, 20, 20], {1, 2, 3})])]
    out += [Paragraph("Con chi si lavora", _H3),
            _p("Stesso giorno, postazione e fascia, volontari compresi.", _TESTO), Spacer(1, 3),
            _tabella(["Dipendente", "Turni in compagnia", "Colleghi diversi", "Più spesso con"],
                     [[d["nome"], d["turni"], d["colleghi_diversi"],
                       " · ".join(f"{f['nome']} ({f['turni']}, {f['percentuale']}%)" for f in d["frequenti"]) or "—"]
                      for d in c["colleghi"]], [20, 12, 12, 56], {1, 2})]
    return out


def _statistiche(righe: list[dict]) -> list:
    """Solo i dipendenti: i volontari non compaiono."""
    righe = [r for r in righe if r["tipo"] == "dipendente"]
    out = [Paragraph("Statistiche dei turni", _H2)]
    if not righe:
        return out + [_p("Nessuna settimana con turni generati.", _TESTO)]
    dati = []
    for r in righe:
        saldo = r.get("saldo_ore", 0)
        sedi = r.get("sedi", {})
        dati.append([Markup(f"<b>{escape(r['nome'])}</b>"), r["settimane"], et._ore_totali(r),
                     f"{saldo:+.1f}".replace(".", ","),
                     f"{r['ore_giorno']} / {r['ore_notte']}", f"{sedi.get('Acquasanta', 0)} / {sedi.get('Venarotta', 0)}",
                     sum(r["weekend"].values()), et._standby(r), r["programmati"], et._ascoli(r), r.get("assistenze", 0)])
    return out + [_tabella(["Dipendente", "Settimane", "Ore totali", "Saldo ore", "Ore giorno / notte",
                            "Acquasanta / Venarotta", "Weekend", "Standby (g / n)", "Programmati", "Ascoli (g / n)", "Assistenze"],
                           dati, [14, 7, 13, 7, 9, 9, 6, 6, 7, 8, 7], set(range(1, 11))),
                  _p("Solo i dipendenti e le settimane con turni generati. Ore totali: ore lavorate più 6 h per ogni giorno di ferie o "
                     "malattia. Saldo ore: differenza rispetto alla media dei dipendenti; le settimane con ferie o malattia "
                     "non lo cambiano, come nel generatore.", _NOTA)]


def _indisponibilita(righe: list[dict]) -> list:
    out = [Paragraph("Statistiche delle indisponibilità", _H2)]
    if not righe:
        return out + [_p("Nessuna indisponibilità.", _TESTO)]
    dati = [[Markup(f"<b>{escape(r['nome'])}</b>")] + [g["totale"] or "·" for g in r["giorni"]] + [r["totale"]] for r in righe]
    return out + [_tabella(["Dipendente", *et.GIORNI_BREVI, "Totale"], dati, [30] + [9] * 8, set(range(1, 9))),
                  _p("Quante volte ognuno è stato indisponibile in ciascun giorno della settimana, su tutto lo storico.", _NOTA)]


def genera_equita(s: dict, *, equita: dict, statistiche: list[dict], statistiche_indisp: list[dict],
                  confronti: dict | None = None, assenze: dict[int, str] | None = None) -> bytes:
    out = BytesIO()
    titolo = f"Equità dei turni dopo la settimana dal {et._dm(s['inizio'])} al {et._dmy(s['fine'])}"
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=18, rightMargin=18, topMargin=20, bottomMargin=20,
                            title=titolo, author="Croce Verde Ascoli Piceno · Turnistica")
    doc.build([Paragraph(escape(titolo), _TITOLO), *_generazione(s), *_equita(equita, assenze or {}), PageBreak(),
               *_confronti(confronti or {}), PageBreak(), *_statistiche(statistiche), Spacer(1, 8),
               *_indisponibilita(statistiche_indisp)])
    return out.getvalue()
