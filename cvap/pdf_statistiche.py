"""PDF di Statistiche (Turni, Indisponibilità, Riepilogo per dipendente, Equità), Festività «a chi tocca» e Sostituti.

Fatti dal server con lo stile comune (`pdf_stile`), come il tabellone e i turni personali: stessa testata, stesso
piè di pagina, stesse tabelle. Prima erano la «fotografia» della pagina fatta dal browser. I dati sono quelli delle
stesse API della pagina; i testi delle pagine sono ripresi qui, così il foglio dice quello che si vede a schermo.
"""
import re
from datetime import date, datetime
from html import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

from . import email_turni as et
from . import pdf_equita as eq
from . import pdf_stile as st
from .pdf_stile import Markup, p

MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
VERSIONI = {"effettivi": "Turni effettivi (con i cambi turno)", "generati": "Turni generati (senza i cambi turno)"}
RIQUADRO_BG = colors.HexColor("#e8f5ec")
FERIE_BG = colors.HexColor("#e3eafa")


def versione_testo(versione: str) -> str:
    return VERSIONI.get(versione, VERSIONI["effettivi"])


def _giorno_lungo(iso: str, anno: bool = False) -> str:
    """«Lunedì 23 ottobre» (con `anno`: «Lunedì 23 ottobre 2026»)."""
    d = date.fromisoformat(iso)
    return f"{et.GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}" + (f" {d.year}" if anno else "")


def _grassetto(testo) -> Markup:
    return Markup(f"<b>{escape(str(testo))}</b>")


def _vuoto(testo: str) -> list:
    return [p(testo, st.TESTO)]


# --- Statistiche → Turni -----------------------------------------------------------------------------------

def genera_statistiche(righe: list[dict], versione: str = "effettivi") -> bytes:
    """Come la tabella della pagina (dipendenti e volontari), in due tabelle per non rimpicciolire il testo."""
    if not righe:
        blocchi = _vuoto("Nessuna settimana confermata con turni generati.")
        return st.documento("Statistiche dei turni", versione_testo(versione), blocchi)

    def saldo(r):
        return f"{r.get('saldo_ore', 0):+.1f}".replace(".", ",") if r["tipo"] == "dipendente" else "—"

    def extra(r):
        return f"{et._num(r['ore_sostituzioni'])} h" if r.get("ore_sostituzioni") else "0"

    def tipo(r):
        return "Dipendente" if r["tipo"] == "dipendente" else "Volontario"

    ore = [[_grassetto(r["nome"]), tipo(r), r["settimane"], et._ore_totali(r), saldo(r), extra(r),
            f"{r['ore_giorno']} / {r['ore_notte']}",
            f"{r.get('sedi', {}).get('Acquasanta', 0)} / {r.get('sedi', {}).get('Venarotta', 0)}"] for r in righe]
    speciali = []
    for r in righe:
        w = r["weekend"]
        speciali.append([_grassetto(r["nome"]), w["sab_giorno"], w["sab_notte"], w["dom_giorno"], w["dom_notte"],
                         sum(w.values()), et._standby(r), r["programmati"], et._ascoli(r), r.get("assistenze", 0)])
    blocchi = [
        Paragraph("Ore e sedi", st.H2),
        st.tabella(["Persona", "Tipo", "Settimane", "Ore totali", "Saldo ore", "Sostituzioni (extra)",
                    "Ore giorno / notte", "Acquasanta / Venarotta"], ore, [19, 10, 8, 20, 8, 11, 12, 13],
                   destra={2, 3, 4, 5, 6, 7}),
        Spacer(1, 4),
        p("Contano solo le settimane generate e confermate: le bozze e le settimane compilate solo a mano sono "
          "escluse. Ore totali: ore lavorate più 6 h per ogni giorno di ferie o malattia (chi è assente tutta la "
          "settimana è escluso dal conteggio). Saldo ore: differenza rispetto alla media dei dipendenti, settimana per "
          "settimana, come fa il generatore: le settimane con ferie o malattia non lo cambiano; + ore in più, − ore in "
          "meno; per i volontari non c'è. Sostituzioni: ore extra, fuori da tutte le altre colonne.", st.NOTA),
        PageBreak(),
        Paragraph("Weekend e turni speciali", st.H2),
        st.tabella(["Persona", "Sabato giorno", "Sabato notte", "Domenica giorno", "Domenica notte", "Weekend totale",
                    "Standby (G / N)", "Programmati", "Ascoli (G / N)", "Assistenze"], speciali,
                   [19, 8, 8, 9, 9, 9, 11, 10, 11, 9], destra=set(range(1, 10))),
        Spacer(1, 4),
        p("Weekend: turni di sabato e domenica, di giorno (G) e di notte (N). Standby e Ascoli: turni totali e, tra "
          "parentesi, quanti di giorno (G) e di notte (N). Programmati e Assistenze: turni svolti (ogni Assistenza "
          "conta 1, qualunque sia la durata).", st.NOTA)]
    return st.documento("Statistiche dei turni", versione_testo(versione), blocchi)


# --- Statistiche → Indisponibilità --------------------------------------------------------------------------

LIVELLI = [None, "#e8f5ec", "#cdeadb", "#a8dbc0", "#7ccaa3"]  # più scuro = il giorno ricorre di più


def genera_indisponibilita(righe: list[dict], periodo: str) -> bytes:
    """`periodo`: es. «Dal 01/10/2026 al 31/10/2026» o «Tutte le indisponibilità registrate»."""
    if not righe:
        return st.documento("Indisponibilità per giorno", periodo, _vuoto("Nessun dipendente registrato."))
    regole, dati = [], []
    for r, riga in enumerate(righe, start=1):
        massimo = max([0, *(g["totale"] for g in riga["giorni"])])
        celle = [Markup(f"<b>{escape(riga['nome'])}</b>" + ("" if riga["attivo"] else " <i>(non attivo)</i>"))]
        for i, g in enumerate(riga["giorni"], start=1):
            if not g["totale"]:
                celle.append(p("·", st.CELLA_CENTRO))
                continue
            livello = -(-g["totale"] * 4 // massimo)  # soffitto, come nella pagina: 1..4
            dettaglio = " ".join(f"{sigla}{g[parte]}" for parte, sigla in (("mattina", "M"), ("pomeriggio", "P"),
                                                                           ("notte", "N")) if g[parte])
            celle.append(Paragraph(f"<b>{g['totale']}</b><br/><font size=\"9\" color=\"{st.MUTO}\">{dettaglio}</font>",
                                   st.CELLA_CENTRO))
            regole.append(("BACKGROUND", (i, r), (i, r), colors.HexColor(LIVELLI[livello])))
        celle += [str(riga["totale"]), _piu_richiesto(riga)]
        dati.append(celle)
    tabella = st.tabella(["Dipendente", *et.GIORNI_BREVI, "Totale", "Più richiesto"], dati,
                         [19] + [8] * 7 + [8, 17], centro=set(range(1, 9)), alternata=False, regole=regole)
    nota = p("Quante volte ogni dipendente ha chiesto di essere indisponibile in ciascun giorno della settimana. Il "
             "numero conta i giorni (anche se indisponibile solo in una parte); sotto, il dettaglio per mattina (M), "
             "pomeriggio (P) e notte (N). Più la cella è scura, più il giorno ricorre per quel dipendente. Ferie e "
             "malattia non sono comprese.", st.NOTA)
    return st.documento("Indisponibilità per giorno", periodo, [tabella, Spacer(1, 4), nota])


def _piu_richiesto(r: dict) -> str:
    if not r["totale"]:
        return "—"
    massimo = max(g["totale"] for g in r["giorni"])
    giorni = [et.GIORNI[i] for i, g in enumerate(r["giorni"]) if g["totale"] == massimo]
    return f"{', '.join(giorni)} ({massimo} su {r['totale']})"


# --- Statistiche → Riepilogo per dipendente ------------------------------------------------------------------

def genera_riepilogo(d: dict, versione: str = "effettivi") -> bytes:
    """`d`: la risposta di `riepilogo.riepilogo_persona`."""
    periodo = f"dal {et._dmy(d['dal'])} al {et._dmy(d['al'])}"
    sottotitolo = f"{d['nome']} · {periodo} · {versione_testo(versione)}"
    blocchi = [Paragraph("Turni giorno per giorno", st.H2), _giorni(d), Spacer(1, 6),
               KeepTogether([Paragraph("Riepilogo del periodo", st.H2), *_totali(d["riepilogo"])])]
    return st.documento("Riepilogo per dipendente", sottotitolo, blocchi)


def _giorni(d: dict) -> Table:
    righe, regole = [], []
    for i, g in enumerate(d["giorni"], start=1):
        giorno = date.fromisoformat(g["data"])
        contenuto = []
        for t in g["turni"]:
            riga = f"<b>{escape(t['orario'])}</b> · {escape(t['postazione'])} · {escape(t['ruolo'])}"
            if t["origine"] == "sostituzione":
                riga += f' · <font color="{et.FESTIVO_TESTO}">Sostituzione (extra)</font>'
            if t.get("festivita"):
                riga += f' · <font color="{et.FESTIVO_TESTO}">Festivo: {escape(t["festivita"])}</font>'
            contenuto.append(Paragraph(riga, st.CELLA))
        if g["assenza"]:
            contenuto.append(Paragraph(f"<b>{'Malattia' if g['assenza'] == 'malattia' else 'Ferie'}</b>", st.CELLA))
        if g["indisponibile"]:
            parti = ", ".join(et.PARTI.get(x, x) for x in g["indisponibile"])
            contenuto.append(Paragraph(f"Indisponibile: {parti}", st.CELLA))
        if not contenuto:
            contenuto.append(Paragraph(f'<font color="{st.MUTO}">Riposo</font>', st.CELLA))
        ore = sum(t["ore"] for t in g["turni"] if t["origine"] != "sostituzione")
        extra = sum(t["ore"] for t in g["turni"] if t["origine"] == "sostituzione")
        testo_ore = (f"{et._num(ore)} h" if ore else "") + (f"<br/>+{et._num(extra)} h extra" if extra else "")
        righe.append([Paragraph(f"<b>{et.GIORNI_BREVI[giorno.weekday()]}</b> {et._dmy(g['data'])}", st.CELLA),
                      contenuto, Paragraph(testo_ore, st.CELLA_DESTRA)])
        if g["assenza"]:
            regole.append(("BACKGROUND", (0, i), (-1, i), FERIE_BG))
        elif g["turni"]:
            tutti_notte = all(t["fascia"] == "notte" for t in g["turni"])
            regole.append(("BACKGROUND", (0, i), (-1, i),
                           colors.HexColor(et.NOTTE_BG if tutti_notte else et.GIORNO_BG)))
        elif giorno.weekday() >= 5:
            regole.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(et.WEEKEND_BG)))
    return st.tabella(["Giorno", "Turni", "Ore"], righe, [16, 74, 10], destra={2}, alternata=False, regole=regole)


def _totali(r: dict) -> list:
    w = r["weekend"]
    assenze = " + ".join(x for x in (f"{r['giorni_ferie']} g ferie" if r["giorni_ferie"] else "",
                                     f"{r['giorni_malattia']} g malattia" if r["giorni_malattia"] else "") if x)
    sostituzioni = r.get("turni_sostituzioni", 0)
    voci = [
        ("Turni svolti", str(r["turni"]), f"{r['turni_giorno']} di giorno · {r['turni_notte']} di notte"),
        ("Ore lavorate", f"{et._num(r['ore_lavorate'])} h",
         f"{et._num(r['ore_giorno'])} h giorno · {et._num(r['ore_notte'])} h notte"),
        ("Ferie e malattia", assenze or "nessuna",
         f"{et._num(r['ore_ferie_malattia'])} h accreditate" if r["ore_ferie_malattia"] else ""),
        ("Ore totali", f"{et._num(r['ore_totali'])} h", "lavorate + 6 h per giorno di ferie o malattia"),
        ("Sostituzioni (extra)", f"{et._num(r.get('ore_sostituzioni', 0))} h" if sostituzioni else "nessuna",
         (f"{sostituzioni} {'turno' if sostituzioni == 1 else 'turni'} al posto di un collega assente: non contano "
          "negli altri totali") if sostituzioni else ""),
        ("Turni nel weekend", str(sum(w.values())),
         f"sab {w['sab_giorno']} G / {w['sab_notte']} N · dom {w['dom_giorno']} G / {w['dom_notte']} N"),
        ("Turni festivi", str(r.get("turni_festivi", 0)),
         " · ".join(f"{f['festivita']} {f['turni']}" for f in r.get("festivi", []))),
        ("Giorni con indisponibilità", str(r["giorni_indisponibili"]), ""),
    ]
    out = [st.tabella(["Voce", "Valore", "Dettaglio"], [[_grassetto(t), v, nota] for t, v, nota in voci], [24, 18, 58])]
    if r["postazioni"]:
        out += [Spacer(1, 8), Paragraph("Turni per postazione", st.H3),
                st.tabella(["Postazione", "Turni", "Ore"],
                           [[_grassetto(x["postazione"]), x["turni"], f"{et._num(x['ore'])} h"] for x in r["postazioni"]],
                           [50, 20, 30], destra={1, 2}, totale=st.larghezza() * 0.6)]
    return out


# --- Statistiche → Equità --------------------------------------------------------------------------------------

def genera_equita_pagina(quadro: dict, confronti: dict, periodo: str, versione: str = "effettivi",
                         assenze: dict[int, str] | None = None) -> bytes:
    """Le rotazioni dell'equità e gli altri confronti, come la pagina e come l'allegato dell'email."""
    blocchi = [*eq._equita(quadro, assenze or {}, intestazione=False), PageBreak(), *eq._confronti(confronti or {})]
    return st.documento("Equità dei turni", f"{periodo} · {versione_testo(versione)}", blocchi)


# --- Festività: a chi tocca ----------------------------------------------------------------------------------------

IMPORTANZA = {1: "normale", 2: "importante", 3: "molto importante"}
VOGLIA = {None: "No", "": "No", "giorno": "Giorno", "notte": "Notte", "entrambi": "Giorno e notte"}
ASSENZA = {"ferie": "Ferie", "malattia": "Malattia", "indisponibile": "Indisponibile"}
FASCE = {"giorno": "Giorno", "notte": "Notte"}


def genera_festivita(voci: list[dict], mesi: int, versione: str = "effettivi") -> bytes:
    sottotitolo = f"Prossimi {mesi} {'mese' if mesi == 1 else 'mesi'} · {versione_testo(versione)}"
    if not voci:
        return st.documento("Festività: a chi tocca", sottotitolo, _vuoto(
            f"Nessuna festività a rotazione nei prossimi {mesi} {'mese' if mesi == 1 else 'mesi'}. "
            "Le festività che contano si scelgono in Impostazioni."))
    blocchi = [p("Per ogni festività, l'ordine in cui toccherebbe lavorarla: in alto chi ha la precedenza, cioè chi "
                 "l'ha lavorata meno volte negli ultimi 5 anni o non la lavora da più tempo. Chi l'ha lavorata l'anno "
                 "scorso scende verso il fondo. Chi vuole lavorarla riceve prima quei turni.", st.TESTO),
               Spacer(1, 3),
               p("È un'indicazione: chi lavora davvero dipende anche dai riposi, dalle ore della settimana, dalle ferie e "
                 "dai posti da autista e da soccorritore (per questo c'è la qualifica). Il generatore usa sempre i turni "
                 "generati.", st.NOTA)]
    for n, f in enumerate(voci):
        blocchi.append(PageBreak() if n else Spacer(1, 4))
        blocchi += _festivita(f)
    return st.documento("Festività: a chi tocca", sottotitolo, blocchi)


def _festivita(f: dict) -> list:
    d = date.fromisoformat(f["data"])
    turni = ", ".join(x for x in ("notte della sera prima" if f.get("conta_notte_prima") else "",
                                  "giorno" if f.get("conta_giorno") else "",
                                  "notte" if f.get("conta_notte") else "") if x)
    out = [Paragraph(f"{escape(f['nome'])} · {_giorno_lungo(f['data'], anno=True)}", st.H2),
           p(f"Importanza: {IMPORTANZA.get(f['peso'], f['peso'])} · Turni che contano: {turni or '—'}", st.TESTO)]
    fasce = [x for x in ("giorno" if f.get("conta_giorno") else None,
                         "notte" if f.get("conta_notte") or f.get("conta_notte_prima") else None) if x]
    if not fasce:
        return out + _vuoto("Nessuna fascia selezionata per questa festività.")
    for fascia in fasce:
        ordine = (f.get("ordini_per_fascia") or {}).get(fascia)
        titolo = Paragraph(FASCE[fascia], st.H3)
        if not isinstance(ordine, list):
            out += [titolo, p(f"Le statistiche di {FASCE[fascia].lower()} non sono disponibili.", st.TESTO)]
        elif not ordine:
            out += [titolo, p("Nessun dipendente attivo.", st.TESTO)]
        else:
            righe = [[i + 1, _grassetto(x["nome"]), et.RUOLI.get(x["qualifica"], x["qualifica"]), x["volte_5_anni"],
                      str(x["ultimo_anno"]) if x["ultimo_anno"] else "mai", VOGLIA.get(x.get("disponibile"), "No"),
                      ASSENZA.get(x.get("assente"), "–")] for i, x in enumerate(ordine)]
            out.append(KeepTogether([titolo, st.tabella(
                ["N.", "Dipendente", "Qualifica", "Volte negli ultimi 5 anni", "Ultima volta", "Vuole lavorarla",
                 "Assenze registrate"], righe, [5, 27, 15, 15, 11, 14, 13], destra={0, 3, 4})]))
    return out


# --- Sostituti ---------------------------------------------------------------------------------------------------

NOTA_EXTRA = "Le ore di una sostituzione sono extra: non contano nelle ore della settimana né nelle statistiche."
REGOLE = ("Regole controllate: almeno 11 ore di riposo tra due turni, al massimo 3 giorni o 3 notti di fila, mai più di "
          "12 ore di lavoro di fila, nessun turno a chi è in ferie, in malattia o indisponibile.")
_ETICHETTA = ParagraphStyle("etichetta", parent=st.CELLA, fontName="Helvetica-Bold", fontSize=9.5,
                            textColor=colors.HexColor(st.VERDE_SCURO))
_SCELTA = ParagraphStyle("scelta", parent=st.TESTO, fontSize=13, leading=17)


def genera_sostituti(settimana: dict, esiti: list[dict], adesso: datetime | None = None) -> bytes:
    """`esiti`: per ogni turno da coprire, la risposta di `GET /api/assegnazioni/{id}/sostituti`."""
    periodo = f"Settimana dal {et._dmy(settimana['inizio'])} al {et._dmy(settimana['fine'])}"
    quanti = "C'è 1 turno da coprire" if len(esiti) == 1 else f"Ci sono {len(esiti)} turni da coprire"
    blocchi = [p(f"{quanti}. Per ogni turno c'è una proposta consigliata e, sotto, le alternative in ordine di "
                 "preferenza.", st.TESTO), Spacer(1, 6)]
    for n, e in enumerate(esiti, start=1):
        blocchi += _turno_da_coprire(settimana, e, n, len(esiti))
    blocchi += [Spacer(1, 4), p(NOTA_EXTRA, st.NOTA), p(REGOLE, st.NOTA)]
    return st.documento("Sostituzioni da organizzare", periodo, blocchi, adesso=adesso)


def _nome_postazione(settimana: dict, a: dict) -> str:
    if a["postazione"] != et.EXTRA:
        return a["postazione"]
    richiesta = next((x for x in settimana.get("extra", []) if x["segmento"] == a["segmento"]), None)
    return f"{richiesta['nome']} ({et.EXTRA})" if richiesta else et.EXTRA


def _turno_da_coprire(settimana: dict, e: dict, n: int, totale: int) -> list:
    a = e["turno"]
    motivo = {"malattia": "in malattia", "ferie": "in ferie"}.get(e.get("assenza"))
    chi = (f"Lo aveva <b>{escape(a['persona_nome'])}</b>, che è {motivo}." if motivo
           else f"Ora è assegnato a <b>{escape(a['persona_nome'])}</b>.")
    testata = [p(f"Turno {n} di {totale}" if totale > 1 else "Turno da coprire", st.NOTA),
               Paragraph(f"{_giorno_lungo(a['data'])} · {escape(et.orario_turno(a['fascia'], a['segmento']))}", st.H2),
               p(f"{_nome_postazione(settimana, a)} · {et.RUOLI.get(a['ruolo'], a['ruolo'])}", st.TESTO),
               Paragraph(chi, st.TESTO), Spacer(1, 4)]
    return [KeepTogether([*testata, *_proposte(e)]), Spacer(1, 12)]


def _riquadro(contenuto: list, sfondo=RIQUADRO_BG, bordo=st.VERDE) -> Table:
    t = Table([[contenuto]], colWidths=[st.larghezza()])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), sfondo), ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor(bordo)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def _ore_totali(c: dict) -> int:
    return (c.get("ore") or 0) + (c.get("ore_sostituzioni") or 0)


def _proposte(e: dict) -> list:
    candidati, catene = e.get("candidati", []), e.get("catene", [])
    in_regola = [c for c in candidati if not c.get("regole")]
    fuori = [c for c in candidati if c.get("regole")]
    out = []
    if in_regola:
        out.append(_proposta_diretta(in_regola[0]))
        if len(in_regola) > 1:
            out += [Spacer(1, 6), _alternative("Se non è disponibile, in alternativa (in ordine):", in_regola[1:], False)]
    elif catene:
        out.append(_proposta_scambio(catene[0]))
    else:
        out.append(_riquadro([Paragraph("Nessun dipendente disponibile", _ETICHETTA),
                              Paragraph("Nessun dipendente può farlo rispettando le regole: serve un volontario.",
                                        _SCELTA)], st.AVVISO_BG, "#d99000"))
    if fuori:
        out += [Spacer(1, 6), _alternative("Solo se non c'è altra soluzione (non rispettano le regole):", fuori, True)]
    return out


def _semplifica(messaggio: str, nome: str | None = None) -> str:
    """Messaggi del controllo in parole semplici: senza il nome davanti, «eccezione» = consentito."""
    t = str(messaggio)
    if nome and t.startswith(f"{nome}: "):
        t = t[len(nome) + 2:]
    t = re.sub(r"solo (\d+)h di riposo tra (.+) e (.+)$", r"solo \1 ore di riposo tra due turni (\2 e \3)", t)
    t = t.replace("(eccezione)", "(consentito)")
    t = re.sub(r"\(massimo (\d+)\)", r"(il massimo è \1)", t)
    return t[:1].upper() + t[1:]


def _proposta_diretta(c: dict) -> Table:
    note = [_semplifica(v, c["nome"]) for v in c.get("avvisi", [])]
    righe = [Paragraph("Proposta consigliata", _ETICHETTA),
             Paragraph(f"Chiamare <b>{escape(c['nome'])}</b>.", _SCELTA),
             p(f"Rispetta tutte le regole. Questa settimana lavora {et._num(_ore_totali(c))} h; con questo turno "
               f"{et._num(c['ore_dopo'])} h.", st.TESTO)]
    if note:
        righe.append(p(f"Da sapere: {'; '.join(note)}.", st.TESTO))
    return _riquadro(righe)


def _proposta_scambio(k: dict) -> Table:
    b, c, t = k["prende"], k["copre"], k["ceduto"]
    note = [f"{b['nome']}: {_semplifica(v, b['nome']).lower()}" for v in b.get("avvisi", [])]
    note += [f"{c['nome']}: {_semplifica(v, c['nome']).lower()}" for v in c.get("avvisi", [])]
    ore_b = ("(lascia un suo turno: le sue ore non cambiano)" if b["ore_dopo"] == b["ore"]
             else f"(lascia un suo turno: le sue ore passano da {et._num(b['ore'])} a {et._num(b['ore_dopo'])} h)")
    ceduto = f"{_giorno_lungo(t['data'])} · {et.orario_turno(t['fascia'], t['segmento'])} · {t['postazione']}"
    righe = [Paragraph("Proposta consigliata: uno scambio", _ETICHETTA),
             p("Nessuno può fare questo turno direttamente rispettando le regole, ma con uno scambio tra due persone "
               "si copre tutto:", st.TESTO),
             Paragraph(f"1. <b>{escape(b['nome'])}</b> fa questo turno <font color=\"{st.MUTO}\">{escape(ore_b)}</font>.",
                       st.TESTO),
             Paragraph(f"2. <b>{escape(c['nome'])}</b> fa al posto di {escape(b['nome'])} il turno di "
                       f"<b>{escape(ceduto)}</b> <font color=\"{st.MUTO}\">(ore extra; con questo turno lavora "
                       f"{et._num(c['ore_dopo'])} h)</font>.", st.TESTO)]
    if note:
        righe.append(p(f"Da sapere: {'; '.join(note)}.", st.TESTO))
    return _riquadro(righe)


def _alternative(titolo: str, lista: list[dict], fuori_regola: bool) -> KeepTogether:
    righe = []
    for i, c in enumerate(lista, start=1):
        testi = [_semplifica(v, c["nome"]) for v in [*(c.get("regole", []) if fuori_regola else []), *c.get("avvisi", [])]]
        righe.append([i, _grassetto(c["nome"]), f"{et._num(_ore_totali(c))} h (con il turno: {et._num(c['ore_dopo'])} h)",
                      "; ".join(testi) or "—"])
    return KeepTogether([Paragraph(f"<b>{escape(titolo)}</b>", st.TESTO), Spacer(1, 3),
                         st.tabella(["#", "Nome", "Ore nella settimana", "Cosa non rispetta" if fuori_regola else "Note"],
                                    righe, [4, 26, 28, 42], destra={0})])
