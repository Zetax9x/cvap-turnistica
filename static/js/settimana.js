// Vista "Settimana": disponibilità, griglia turni, generazione, conferma, violazioni, riepilogo.

import { api } from "./api.js";
import { apriInvio, apriProva } from "./email.js";
import {
  el, clear, toast, toastErrore, chiediConferma, addDays, mondayOf, todayISO, ddmm, dataLunga,
  dataEstesa, indiceGiorno, GIORNI_BREVI, etichetta, formatOre, formatSaldo, orarioTurno,
  PARTI_TURNO, SCELTE_INDISPONIBILITA, partiTurno, valoreParti, etichettaParti, badgeAssenza,
  EXTRA, leggiExtra,
} from "./util.js";

const FASCE = ["giorno", "notte"];
const RUOLI = ["autista", "soccorritore"];
// Postazioni a richiesta (solo settimane A): esistono solo dove l'utente indica il fabbisogno.
const STANDBY = "Standby";
const PROGRAMMATI = "Programmati";
const POSTAZIONI_A_RICHIESTA = [STANDBY, PROGRAMMATI];
const SEGMENTI_PROG = ["prog_mattina", "prog_pomeriggio"];
const MAX_PROGRAMMATI = 20;
const MAX_EXTRA = 20;  // persone per ruolo in una richiesta di Assistenze ed Extra
const SCARTO_PREDEFINITO = 12;  // se il server non indica `scarto_ore_max`
const CHIAVE_SETTIMANA = "cvap.settimana";
const CHIAVE_TEMPO = "cvap.tempoGenerazione";
// Su Vercel la funzione si ferma a 300 s: si lascia margine per leggere e salvare i dati
const TEMPO_PREDEFINITO = 120;
const TEMPO_MIN = 10;
const TEMPO_MAX = 280;

const stato = {
  root: null,
  data: null,          // lunedì ISO della settimana visualizzata
  settimana: null,     // payload GET /settimane/{data}
  persone: [],
  divieti: [],         // [{id, persona_id, postazione, turno}]
  occupato: false,
  cellaAperta: null,   // {data, postazione, fascia, ruolo, segmento?} (segmento solo per i Programmati)
  dispAperta: {},      // lunedì ISO -> pannello disponibilità aperto/chiuso dall'utente
  richAperta: {},      // lunedì ISO -> pannello richieste Standby/Programmati aperto/chiuso
};

let dialogCella = null;
let dialogLiberi = null;
let dialogExtra = null;

// Avvisi sui dipendenti liberi (campo `liberi` del payload)
const AVVISI_LIBERI = {
  smonto_notte: { breve: "smonto notte", lungo: "Smonta dalla notte (finisce alle 8)" },
  notte: { breve: "notte", lungo: "Fa la notte questa sera" },
};

// ---------------------------------------------------------------- ingresso

// Il menu "Altre opzioni" si chiude cliccando fuori o con Esc, come un normale menu a tendina.
document.addEventListener("click", (e) => {
  for (const menu of document.querySelectorAll(".altre-opzioni[open]")) {
    if (!menu.contains(e.target)) menu.open = false;
  }
});
document.addEventListener("keydown", (e) => {
  // con una finestra aperta Esc chiude solo la finestra (che poi ridà il focus al suo pulsante)
  if (e.key !== "Escape" || e.defaultPrevented || document.querySelector("dialog[open]")) return;
  for (const menu of document.querySelectorAll(".altre-opzioni[open]")) {
    menu.open = false;
    menu.querySelector("summary").focus();
  }
});
// ...e quando con Tab si esce dal menu
document.addEventListener("focusout", (e) => {
  const menu = e.target.closest && e.target.closest(".altre-opzioni[open]");
  if (menu && e.relatedTarget && !menu.contains(e.relatedTarget) && !document.querySelector("dialog[open]")) {
    menu.open = false;
  }
});

export async function mostra(root, parametro) {
  stato.root = root;
  let data = parametro && /^\d{4}-\d{2}-\d{2}$/.test(parametro) ? parametro : null;
  if (!data) {
    try { data = sessionStorage.getItem(CHIAVE_SETTIMANA); } catch { data = null; }
  }
  stato.data = mondayOf(data || todayISO());
  try { sessionStorage.setItem(CHIAVE_SETTIMANA, stato.data); } catch { /* ignora */ }

  if (!stato.settimana || stato.settimana.inizio !== stato.data) {
    renderCaricamento();
  }
  try {
    const [settimana, persone, divieti] = await Promise.all([api.settimana(stato.data), api.persone(), api.divieti().catch(() => [])]);  // i divieti servono solo per l'etichetta "NON PUÒ"
    // ignora risposte arrivate dopo un cambio di settimana
    if (mondayOf(settimana.inizio) !== stato.data) return;
    stato.settimana = settimana;
    stato.persone = persone;
    stato.divieti = divieti;
    render();
  } catch (err) {
    renderErrore(err);
  }
}

function vaiA(data) {
  location.hash = `#settimana/${mondayOf(data)}`;
}

function aggiorna(settimana) {
  // risposta arrivata dopo un cambio di settimana: non va mostrata
  if (!settimana || mondayOf(settimana.inizio) !== stato.data) return;
  stato.settimana = settimana;
  render();
  if (dialogCella && dialogCella.open && stato.cellaAperta) renderDialog();
}

async function ricarica() {
  aggiorna(await api.settimana(stato.data));
}

// ---------------------------------------------------------------- render

function renderCaricamento() {
  clear(stato.root).append(
    renderTestata(null),
    el("p", { class: "muted loading" }, "Caricamento della settimana…"),
  );
}

function renderErrore(err) {
  clear(stato.root).append(
    renderTestata(null),
    el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare la settimana. "), err.message,
      " ", el("button", { type: "button", class: "btn btn-small", onclick: () => mostra(stato.root, stato.data) }, "Riprova")),
  );
}

function render() {
  const s = stato.settimana;
  const confermata = s.stato === "confermata";
  const frammento = document.createDocumentFragment();
  frammento.append(renderTestata(s), renderPassi(s), renderToolbar(s));
  if (confermata) {
    frammento.append(el("div", { class: "banner banner-info" },
      "Settimana confermata: le modifiche sono bloccate. Usa “Riapri” per modificarla."));
  }
  if (s.report) frammento.append(renderReport(s.report));
  frammento.append(renderDisponibilita(s));
  if ((s.postazioni_a_richiesta || []).length) frammento.append(renderRichieste(s));
  const speciali = postazioniSpecialiVisibili(s);
  frammento.append(renderLegenda(speciali.length > 0));

  const griglie = el("div", { class: "griglie" });
  for (const postazione of s.postazioni) griglie.append(renderGriglia(s, postazione));
  if (!s.postazioni.length) griglie.append(el("p", { class: "muted" }, "Nessuna postazione attiva in questa settimana."));
  for (const postazione of speciali) griglie.append(renderGriglia(s, postazione));
  griglie.append(renderGrigliaExtra(s));
  frammento.append(griglie);

  frammento.append(el("div", { class: "pannelli" }, renderViolazioni(s), renderRiepilogo(s)));
  if (haTurni(s)) frammento.append(renderStampaLiberi(s));
  clear(stato.root).append(frammento);
  if (dialogLiberi && dialogLiberi.open) {
    if (haTurni(s) && s.giorni.includes(dialogLiberi.dataset.data)) renderDialogLiberi(); else dialogLiberi.close();
  }
}

function renderTestata(s) {
  const inputData = el("input", {
    type: "date", id: "settimana-data", value: stato.data || "",
    onchange: (e) => { if (e.target.value) vaiA(e.target.value); },
  });
  const nav = el("div", { class: "week-nav", role: "group", "aria-label": "Navigazione settimane" },
    el("button", { type: "button", class: "btn btn-freccia", onclick: () => vaiA(addDays(stato.data, -7)), "aria-label": "Settimana precedente", title: "Settimana precedente" }, "‹"),
    el("button", { type: "button", class: "btn", onclick: () => vaiA(todayISO()) }, "Oggi"),
    el("button", { type: "button", class: "btn btn-freccia", onclick: () => vaiA(addDays(stato.data, 7)), "aria-label": "Settimana successiva", title: "Settimana successiva" }, "›"),
    el("label", { class: "sr-only", for: "settimana-data" }, "Vai alla settimana del giorno"),
    inputData,
  );

  const titolo = el("div", { class: "week-title" });
  if (s) {
    titolo.append(
      el("h1", {}, el("span", { class: "sr-only week-tipo" }, `Settimana ${s.tipo}, `),
        el("span", { class: "week-range" }, `${ddmm(s.inizio)} – ${dataLunga(s.fine || addDays(s.inizio, 6))}`)),
      el("div", { class: "week-meta" },
        el("span", { class: "badge badge-tipo week-tipo", "aria-hidden": "true" }, `Settimana ${s.tipo}`),
        el("span", { class: `badge badge-stato badge-${s.stato}` }, etichetta("stato", s.stato)),
        el("span", { class: "muted week-postazioni" }, s.postazioni.join(" · "))),
    );
  } else {
    titolo.append(el("h1", {}, "Settimana"));
  }
  return el("header", { class: "week-header" }, titolo, nav);
}

/** I quattro passi di ogni settimana, con quello a cui si è arrivati evidenziato. */
function renderPassi(s) {
  const passi = [
    ["Disponibilità", "Segna indisponibili e richieste"],
    ["Genera", "Crea i turni in automatico"],
    ["Controlla", "Correggi le celle se serve"],
    ["Conferma", "Blocca la settimana"],
  ];
  const generati = s.assegnazioni.some((a) => a.origine === "generato");
  const attuale = s.stato === "confermata" ? 4 : generati ? 2 : s.assegnazioni.length ? 1 : 0;
  return el("ol", { class: "passi", role: "list", "aria-label": "Passi della settimana" },
    passi.map(([titolo, sotto], i) => {
      const fatto = i < attuale;
      const classe = fatto ? "passo passo-fatto" : i === attuale ? "passo passo-attuale" : "passo";
      return el("li", { class: classe, "aria-current": i === attuale ? "step" : null },
        el("span", { class: "passo-num", "aria-hidden": "true" }, fatto ? "✓" : String(i + 1)),
        el("span", { class: "passo-testo" },
          el("span", { class: "passo-titolo" }, titolo, fatto ? el("span", { class: "sr-only" }, " (fatto)") : null),
          el("span", { class: "passo-sotto" }, sotto)));
    }));
}

function renderToolbar(s) {
  const confermata = s.stato === "confermata";
  const haGenerati = s.assegnazioni.some((a) => a.origine === "generato");
  const dis = stato.occupato;
  const altre = el("details", { class: "altre-opzioni" },
    el("summary", {}, "Altre opzioni"),
    el("div", { class: "altre-opzioni-menu" },
      el("label", { class: "tempo-generazione", title: "Più tempo = soluzioni migliori quando ci sono molti posti" },
        "Tempo massimo di generazione ",
        el("input", {
          type: "number", id: "tempo-generazione", min: String(TEMPO_MIN), max: String(TEMPO_MAX), step: "10",
          value: String(tempoGenerazione()), disabled: confermata || dis, inputmode: "numeric",
          onchange: (e) => salvaTempo(e.target),
        }),
        " s"),
      el("button", {
        type: "button", class: "btn", disabled: dis || !haTurni(s), onclick: () => apriProva(stato.data),
        title: "Ricevi l'email dei turni come la riceverà il personale",
      }, "Invia una prova a me"),
      el("button", {
        type: "button", class: "btn btn-danger", disabled: confermata || dis || !haGenerati, onclick: onRimuoviGenerati,
      }, "Rimuovi i turni generati")));
  return el("div", { class: "toolbar", role: "group", "aria-label": "Azioni settimana" },
    el("button", {
      type: "button", class: "btn btn-primary btn-grande", disabled: confermata || dis, onclick: onGenera,
    }, haGenerati ? "Rigenera turni" : "Genera turni"),
    confermata
      ? [el("button", {
          type: "button", class: "btn btn-primary btn-grande", disabled: dis, onclick: () => apriInvio(stato.data),
        }, "Invia i turni via email"),
        el("button", { type: "button", class: "btn btn-grande", disabled: dis, onclick: onRiapri }, "Riapri")]
      : el("button", { type: "button", class: "btn btn-success btn-grande", disabled: dis || s.stato === "nuova" && !s.assegnazioni.length, onclick: onConferma }, "Conferma settimana"),
    altre,
    el("span", { class: "toolbar-spacer" }),
    el("button", {
      type: "button", class: "btn btn-ghost", disabled: !haTurni(s), onclick: stampaLiberi,
      title: "Stampa per ogni giorno della settimana chi è libero",
    }, "Stampa liberi"),
    el("button", { type: "button", class: "btn btn-ghost", onclick: stampaGriglia }, "Stampa"),
  );
}

function renderLegenda(conSpeciali) {
  return el("ul", { class: "legenda", "aria-label": "Legenda" },
    el("li", {}, el("span", { class: "chip chip-volontario" }, "Nome"), " volontario"),
    el("li", {}, el("span", { class: "chip chip-manuale" }, "Nome"), " fissato manualmente"),
    el("li", {}, el("span", { class: "chip chip-generato" }, "Nome"), " generato"),
    el("li", {}, el("span", { class: "scoperto" }, "scoperto"), " posto da coprire"),
    conSpeciali ? el("li", {}, el("span", { class: "non-richiesto", "aria-hidden": "true" }, "—"), " turno non richiesto") : null,
  );
}

// Frasi tecniche del generatore che a chi fa i turni non servono (lo stato si vede già dal titolo).
// Devono restare uguali ai testi di cvap/solver.py `genera()`.
const FRASI_TECNICHE = [
  /Soluzione buona ma non dimostrata ottima nel tempo disponibile\.\s*/,
  /Tutti i posti coperti nel rispetto delle regole\.\s*/,
  /Tutti i posti sono già coperti\.\s*/,
  /\d+ posti non coperti: servono altri dipendenti o volontari\.\s*/,
];

/** Esito della generazione in parole semplici: posti scoperti e problemi da sistemare, niente dati tecnici. */
function renderReport(r) {
  const riuscita = ["ottimo", "ammissibile"].includes(r.stato);
  const scoperti = r.scoperti || [];
  const note = riuscita
    ? FRASI_TECNICHE.reduce((testo, frase) => testo.replace(frase, ""), r.messaggio || "").trim()
    : r.messaggio || "";
  const classe = !riuscita ? "errore" : scoperti.length || note ? "avviso" : "ok";
  const titolo = !riuscita ? "Turni non generati"
    : scoperti.length ? `Turni generati: ${scoperti.length === 1 ? "1 posto scoperto" : `${scoperti.length} posti scoperti`}`
    : note ? "Turni generati: da controllare" : "Turni generati: tutti i posti coperti";
  const icona = { ok: "✓", avviso: "!", errore: "×" }[classe];
  const riquadro = el("div", { class: `report report-${classe}`, role: "region", "aria-label": "Esito della generazione" },
    el("span", { class: "report-icona", "aria-hidden": "true" }, icona),
    el("div", { class: "report-head" }, el("strong", {}, titolo)),
    note ? el("p", { class: "report-msg" }, note) : null,
  );
  if (scoperti.length) {
    riquadro.append(
      el("p", { class: "report-scoperti-titolo" }, "Servono altri dipendenti o volontari per:"),
      el("ul", { class: "report-scoperti" }, scoperti.map((u) => el("li", {},
        `${dataEstesa(u.data)} · ${u.postazione} · ${orarioTurno(u.fascia, u.segmento)} · ${etichetta("ruolo", u.ruolo)}`))),
    );
  }
  return riquadro;
}

// ---------------------------------------------------------------- griglia

/*
 * Una "cella" è un posto della griglia: {data, postazione, fascia, ruolo} e, solo per i Programmati,
 * anche `segmento` (prog_mattina / prog_pomeriggio sono turni distinti, con più persone ciascuno).
 * Postazioni normali e Standby: un posto per ruolo, il turno di giorno è spezzabile in due metà.
 */

function aRichiesta(postazione) {
  return POSTAZIONI_A_RICHIESTA.includes(postazione) || postazione === EXTRA;
}

/** Segmento del turno intero della postazione (i Programmati non ne hanno: ogni metà è a sé). */
function segmentoIntero(postazione) {
  return postazione === STANDBY ? "standby" : "intero";
}

/** Le due metà in cui si spezza il turno di giorno. */
function metaGiorno(postazione) {
  return postazione === STANDBY ? ["standby_mattina", "standby_pomeriggio"] : ["mattina", "pomeriggio"];
}

/** Segmento con cui la cella è identificata (il suo turno intero, o la metà per i Programmati). */
function segmentoCella(c) {
  return c.segmento || segmentoIntero(c.postazione);
}

/** Postazioni con più posti uguali nello stesso turno, contati per segmento. */
function perSegmento(postazione) {
  return postazione === PROGRAMMATI || postazione === EXTRA;
}

function chiaveCella(c) {
  const base = `${c.data}|${c.postazione}|${c.fascia}|${c.ruolo}`;
  return perSegmento(c.postazione) ? `${base}|${c.segmento}` : base;
}

function assegnazioniCella(s, c) {
  return s.assegnazioni.filter((a) =>
    a.data === c.data && a.postazione === c.postazione && a.fascia === c.fascia && a.ruolo === c.ruolo
    && (!c.segmento || a.segmento === c.segmento));
}

/** Quantità richiesta nel fabbisogno per un turno di una postazione a richiesta (0 se assente). */
function quantitaFabbisogno(s, data, postazione, fascia, segmento, ruolo) {
  const f = (s.fabbisogno || []).find((x) => x.data === data && x.postazione === postazione
    && x.fascia === fascia && x.segmento === segmento && x.ruolo === ruolo);
  return f ? Number(f.quantita) || 0 : 0;
}

/** Posti richiesti nella cella: 1 per le postazioni normali, dal fabbisogno per quelle a richiesta. */
function richiestiCella(s, c) {
  if (!aRichiesta(c.postazione)) return 1;
  return quantitaFabbisogno(s, c.data, c.postazione, c.fascia, segmentoCella(c), c.ruolo);
}

/**
 * Segmenti mancanti di un posto singolo (postazioni normali e Standby):
 * [] se coperto, [turno intero] se vuoto, altrimenti la metà mancante.
 */
function segmentiMancanti(c, lista) {
  if (!lista.length) return [segmentoIntero(c.postazione)];
  if (c.fascia !== "giorno") return [];
  const intero = segmentoIntero(c.postazione);
  const meta = metaGiorno(c.postazione);
  const coperti = new Set();
  for (const a of lista) {
    if (a.segmento === intero) meta.forEach((m) => coperti.add(m));
    else coperti.add(a.segmento);
  }
  return meta.filter((x) => !coperti.has(x));
}

/**
 * Stato di copertura di una cella:
 * {richiesti, mancanti: segmenti mancanti (posto singolo), nMancanti: posti scoperti, eccesso: persone in più}.
 * Le celle non richieste (postazioni a richiesta senza fabbisogno) hanno richiesti = 0 e nulla di mancante.
 */
function coperturaCella(s, c, lista) {
  const richiesti = richiestiCella(s, c);
  if (perSegmento(c.postazione)) {
    return {
      richiesti, mancanti: [],
      nMancanti: Math.max(0, richiesti - lista.length),
      eccesso: Math.max(0, lista.length - richiesti),
    };
  }
  if (!richiesti) return { richiesti, mancanti: [], nMancanti: 0, eccesso: lista.length ? 1 : 0 };
  const mancanti = segmentiMancanti(c, lista);
  return { richiesti, mancanti, nMancanti: mancanti.length ? 1 : 0, eccesso: 0 };
}

/** Testi "scoperto" da mostrare nella cella. */
function testiScoperti(c, cop) {
  if (perSegmento(c.postazione)) {
    if (!cop.nMancanti) return [];
    if (cop.richiesti === 1) return ["scoperto"];
    return [`${cop.nMancanti} di ${cop.richiesti} ${cop.nMancanti === 1 ? "scoperto" : "scoperti"}`];
  }
  return cop.mancanti.map((m) => (m === segmentoIntero(c.postazione) ? "scoperto" : `${etichetta("segmento", m)} scoperto`));
}

/** Postazioni a richiesta da mostrare in griglia: con fabbisogno o con assegnazioni. */
function postazioniSpecialiVisibili(s) {
  const attive = s.postazioni_a_richiesta || [];
  return POSTAZIONI_A_RICHIESTA.filter((p) =>
    (attive.includes(p) && (s.fabbisogno || []).some((f) => f.postazione === p && f.quantita > 0))
    || s.assegnazioni.some((a) => a.postazione === p));
}

/** Righe della griglia di una postazione: [{fascia, segmento?, ruolo, etichettaTurno, inizio}]. */
function righeGriglia(postazione) {
  const righe = [];
  if (postazione === PROGRAMMATI) {
    for (const segmento of SEGMENTI_PROG) {
      RUOLI.forEach((ruolo, idx) => righe.push({
        fascia: "giorno", segmento, ruolo, etichettaTurno: orarioTurno("giorno", segmento), inizio: idx === 0,
      }));
    }
    return righe;
  }
  for (const fascia of FASCE) {
    RUOLI.forEach((ruolo, idx) => righe.push({
      fascia, ruolo, etichettaTurno: orarioTurno(fascia, segmentoIntero(postazione)), inizio: idx === 0,
    }));
  }
  return righe;
}

function indiceViolazioni(s) {
  const mappa = new Map();
  for (const v of s.violazioni || []) {
    if (v.persona_id === null || v.persona_id === undefined || !v.data) continue;
    const k = `${v.persona_id}|${v.data}`;
    if (mappa.get(k) !== "errore") mappa.set(k, v.livello);
  }
  return mappa;
}

/** Nomi delle festività di un giorno, uniti da " / " ("" se non è festivo). */
function nomiFeste(s, data) {
  return (s.festivi || []).filter((f) => f.data === data).map((f) => f.nome).join(" / ");
}

/**
 * Intestazione di colonna di un giorno (griglie e stampa dei liberi): nome e data, weekend e festività
 * evidenziati, con il nome della festività sotto. Con `conLiberi` il giorno apre "chi è libero".
 */
function thGiorno(s, data, conLiberi = false) {
  const i = indiceGiorno(data);
  const feste = nomiFeste(s, data);
  const classi = [i >= 5 ? "weekend" : null, feste ? "festivo" : null].filter(Boolean).join(" ") || null;
  const contenuto = [
    el("span", { class: "giorno-nome" }, GIORNI_BREVI[i]), " ", el("span", { class: "giorno-data" }, ddmm(data)),
    feste ? el("span", { class: "giorno-festa" }, feste) : null,
  ];
  return el("th", { scope: "col", class: classi },
    conLiberi
      ? el("button", {
        type: "button", class: "giorno-btn", title: "Chi è libero questo giorno",
        "aria-label": `${GIORNI_BREVI[i]} ${ddmm(data)}${feste ? `, ${feste}` : ""}: chi è libero`,
        onclick: () => apriLiberi(data),
      }, contenuto)
      : contenuto);
}

function renderGriglia(s, postazione) {
  const scopertiReport = new Set(((s.report && s.report.scoperti) || []).map((u) => chiaveCella(u)));
  const violazioni = indiceViolazioni(s);
  const confermata = s.stato === "confermata";
  const speciale = aRichiesta(postazione);

  const thead = el("thead", {}, el("tr", {},
    el("th", { scope: "col", class: "col-turno" }, "Turno"),
    s.giorni.map((g) => thGiorno(s, g, haTurni(s))),
  ));

  const tbody = el("tbody");
  for (const riga of righeGriglia(postazione)) {
    const classeRiga = riga.segmento ? `riga-${riga.segmento}` : `riga-${riga.fascia}`;
    const tr = el("tr", { class: `${classeRiga} fascia-${riga.fascia}${riga.inizio ? " inizio-fascia" : ""}` },
      el("th", { scope: "row", class: "col-turno" },
        el("span", { class: "fascia-label" },
          el("span", { class: "fascia-icona", "aria-hidden": "true" }, riga.fascia === "notte" ? "☾" : "☀"),
          riga.etichettaTurno),
        el("span", { class: "ruolo-label" }, etichetta("ruolo", riga.ruolo))));
    for (const g of s.giorni) {
      const cella = { data: g, postazione, fascia: riga.fascia, ruolo: riga.ruolo };
      if (riga.segmento) cella.segmento = riga.segmento;
      tr.append(renderCella(s, cella, scopertiReport, violazioni, confermata));
    }
    tbody.append(tr);
  }

  const idTitolo = `griglia-${postazione.replace(/[^\w-]/g, "_")}`;
  return el("section", { class: `griglia-blocco${speciale ? " griglia-speciale" : ""}`, "aria-labelledby": idTitolo },
    el("h2", { id: idTitolo, class: "griglia-titolo" }, postazione,
      speciale ? el("span", { class: "griglia-sottotitolo muted" }, " · solo i turni richiesti") : null),
    el("div", { class: "griglia-scroll" },
      el("table", { class: "griglia" }, thead, tbody)));
}

/** Il segmento va indicato sul chip solo se diverso dal turno della riga. */
function mostraSegmento(a) {
  return !perSegmento(a.postazione) && a.segmento !== segmentoIntero(a.postazione);
}

/** Cella di un posto; `tag` "div" per usarla fuori da una tabella (Assistenze ed Extra). */
function renderCella(s, cella, scopertiReport, violazioni, confermata, tag = "td") {
  const { data, postazione } = cella;
  const lista = assegnazioniCella(s, cella)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const cop = coperturaCella(s, cella, lista);
  const scoperti = testiScoperti(cella, cop);
  const evidenzia = scoperti.length && scopertiReport.has(chiaveCella(cella));
  const i = indiceGiorno(data);
  const turno = `${orarioTurno(cella.fascia, segmentoCella(cella))}, ${etichetta("ruolo", cella.ruolo)}`;
  const classi = ["cella"];
  if (i >= 5) classi.push("weekend");

  // Postazione a richiesta, turno non richiesto e vuoto: niente da fare qui.
  if (!cop.richiesti && !lista.length) {
    classi.push("cella-non-richiesta");
    return el(tag, { class: classi.join(" ") },
      el("span", { class: "non-richiesto", "aria-hidden": "true" }, "—"),
      el("span", { class: "sr-only" }, `${postazione}, ${GIORNI_BREVI[i]} ${ddmm(data)}, ${turno}: non richiesto`));
  }

  const contenuto = [];
  const descr = [];
  for (const a of lista) {
    const viol = violazioni.get(`${a.persona_id}|${a.data}`);
    const seg = mostraSegmento(a);
    contenuto.push(el("span", {
      class: `chip chip-${a.origine}${viol ? ` chip-viol-${viol}` : ""}`,
      title: `${etichetta("origine", a.origine)}${viol ? (viol === "errore" ? " · violazione" : " · avviso") : ""}`,
    },
      el("span", { class: "chip-nome" }, a.persona_nome),
      seg ? el("span", { class: "chip-seg" }, etichetta("segmento", a.segmento)) : null,
      a.origine === "manuale" ? el("span", { class: "chip-tag" }, "fissato") : null,
      viol ? el("span", { class: "chip-alert", "aria-hidden": "true" }, "!") : null,
    ));
    descr.push(`${a.persona_nome}${seg ? ` ${etichetta("segmento", a.segmento)}` : ""} (${etichetta("origine", a.origine)})`);
  }
  for (const testo of scoperti) {
    contenuto.push(el("span", { class: "scoperto" }, testo));
    descr.push(testo);
  }
  if (cop.eccesso) {
    const testo = cop.richiesti ? `${cop.eccesso} oltre il richiesto` : "non richiesto";
    contenuto.push(el("span", { class: "eccesso" }, testo));
    descr.push(testo);
  }
  if (postazione === PROGRAMMATI && cop.richiesti > 1 && !cop.nMancanti && !cop.eccesso) {
    descr.push(`${cop.richiesti} su ${cop.richiesti}`);
  }

  const etichettaCella = `${postazione}, ${GIORNI_BREVI[i]} ${ddmm(data)}, ${turno}: ${descr.join(", ")}`;
  if (scoperti.length) classi.push("cella-scoperta");
  if (evidenzia) classi.push("cella-evidenziata");

  return el(tag, { class: classi.join(" ") },
    el("button", {
      type: "button", class: "cella-btn", "aria-label": etichettaCella,
      title: confermata ? "Settimana confermata (sola lettura)" : "Modifica assegnazioni",
      onclick: () => apriDialog(cella),
    }, contenuto));
}

function ordineSegmento(seg) {
  return {
    intero: 0, mattina: 1, pomeriggio: 2,
    standby: 0, standby_mattina: 1, standby_pomeriggio: 2,
    prog_mattina: 1, prog_pomeriggio: 2,
  }[seg] ?? 3;
}

// ---------------------------------------------------------------- pannelli

function nomePersona(s, id) {
  const r = (s.riepilogo || []).find((x) => x.persona_id === id);
  if (r) return r.nome;
  const p = stato.persone.find((x) => x.id === id);
  return p ? p.nome : `#${id}`;
}

function renderViolazioni(s) {
  const lista = (s.violazioni || []).slice().sort((a, b) =>
    (a.livello === b.livello ? 0 : a.livello === "errore" ? -1 : 1) || String(a.data || "").localeCompare(String(b.data || "")));
  const errori = lista.filter((v) => v.livello === "errore").length;
  const avvisi = lista.length - errori;
  const sezione = el("section", { class: "pannello", "aria-labelledby": "titolo-violazioni" },
    el("h2", { id: "titolo-violazioni" }, "Controlli",
      el("span", { class: "conteggi" },
        el("span", { class: "badge badge-errore" }, `${errori} errori`),
        el("span", { class: "badge badge-avviso" }, `${avvisi} avvisi`))));
  if (!lista.length) {
    sezione.append(el("p", { class: "ok-text" }, "Nessuna violazione rilevata."));
    return sezione;
  }
  // I "posti scoperti" sono già visibili in griglia: raggruppati in un unico elemento espandibile.
  const scoperti = lista.filter((v) => v.codice === "scoperto");
  const altre = lista.filter((v) => v.codice !== "scoperto");
  if (scoperti.length) {
    sezione.append(el("details", { class: `viol viol-${scoperti[0].livello} viol-gruppo` },
      el("summary", {},
        el("span", { class: "viol-livello" }, scoperti[0].livello === "errore" ? "Errore" : "Avviso"),
        el("span", { class: "viol-testo" }, `${scoperti.length} posti scoperti (evidenziati in rosso nella griglia)`)),
      el("ul", { class: "viol-sotto" }, scoperti.map((v) => el("li", {}, v.messaggio)))));
  }
  if (!altre.length) return sezione;
  sezione.append(el("ul", { class: "violazioni" }, altre.map((v) => el("li", { class: `viol viol-${v.livello}` },
    el("span", { class: "viol-livello" }, v.livello === "errore" ? "Errore" : "Avviso"),
    el("span", { class: "viol-testo" },
      v.messaggio,
      v.persona_id !== null && v.persona_id !== undefined || v.data
        ? el("span", { class: "viol-meta" },
          [v.persona_id !== null && v.persona_id !== undefined ? nomePersona(s, v.persona_id) : null, v.data ? dataEstesa(v.data) : null]
            .filter(Boolean).join(" · "))
        : null)))));
  return sezione;
}

/** Tipi di turno toccati da un turno (come `tipi_turno` del server). */
function tipiTurno(fascia, segmento) {
  if (leggiExtra(segmento)) return [...(fascia === "giorno" ? ["giorno"] : []), ...partiTurno(fascia, segmento)];
  if (fascia === "notte") return ["notte"];
  if (segmento === "intero" || segmento === "standby") return ["giorno", "mattina", "pomeriggio"];
  if (segmento.endsWith("mattina")) return ["giorno", "mattina"];
  if (segmento.endsWith("pomeriggio")) return ["giorno", "pomeriggio"];
  return ["giorno"];
}

/** True se un divieto della persona copre il turno. */
function vietato(personaId, postazione, fascia, segmento) {
  const tipi = tipiTurno(fascia, segmento);
  return stato.divieti.some((d) => d.persona_id === personaId
    && (!d.postazione || d.postazione === postazione) && (!d.turno || tipi.includes(d.turno)));
}

function renderRiepilogo(s) {
  const media = s.media_ore;
  const diff = s.differenza_ore || null;
  const limite = diff ? diff.limite : (s.scarto_ore_max ?? SCARTO_PREDEFINITO);
  const oltre = !!diff && diff.differenza > limite;
  // chi è il massimo o il minimo conta solo quando la differenza supera il limite (anche a pari merito)
  const confrontabile = (r) => r.tipo === "dipendente" && r.giorni_ferie < 7 && !r.max_ore_settimana;
  const contateDi = (r) => r.ore + (r.ore_ferie || 0);
  const estremi = new Map();
  if (oltre && diff.massimo && diff.minimo) {
    for (const r of (s.riepilogo || []).filter(confrontabile)) {
      if (contateDi(r) === diff.massimo.ore) estremi.set(r.persona_id, "ha più ore");
      else if (contateDi(r) === diff.minimo.ore) estremi.set(r.persona_id, "ha meno ore");
    }
  }
  const righe = (s.riepilogo || []).slice().sort((a, b) =>
    (a.tipo === b.tipo ? 0 : a.tipo === "dipendente" ? -1 : 1) || b.ore - a.ore || a.nome.localeCompare(b.nome, "it"));
  const sezione = el("section", { class: "pannello", "aria-labelledby": "titolo-riepilogo" },
    el("h2", { id: "titolo-riepilogo" }, "Riepilogo ore",
      media !== null && media !== undefined ? el("span", { class: "conteggi muted" }, `Media dipendenti: ${formatOre(media)} h`) : null,
      diff ? el("span", { class: `conteggi ${oltre ? "scarto-alto" : "muted"}`,
        title: "Tra chi fa più ore e chi ne fa meno; ferie 6 h al giorno; chi ha un massimo di ore non è confrontato" },
      `Differenza max−min: ${formatOre(diff.differenza)} h (limite ${formatOre(limite)} h)`,
      oltre ? el("span", { class: "sr-only" }, " oltre il limite") : null) : null));
  if (!righe.length) {
    sezione.append(el("p", { class: "muted" }, "Nessuna assegnazione in questa settimana."));
    return sezione;
  }
  const tbody = el("tbody", {}, righe.map((r) => {
    const dip = r.tipo === "dipendente";
    // ore contate = ore lavorate + ferie (6 h al giorno): sono quelle confrontate tra i dipendenti
    const contate = dip && r.giorni_ferie < 7 ? contateDi(r) : null;
    const estremo = dip ? estremi.get(r.persona_id) : null;
    const assenze = [r.giorni_ferie ? `${descriviAssenze(r)} = ${formatOre(r.ore_ferie || 0)}h` : null,
      r.giorni_indisponibili ? `indisp. ${r.giorni_indisponibili}g` : null].filter(Boolean).join(", ");
    return el("tr", { class: estremo ? "fuori-media" : null },
      el("th", { scope: "row" },
        dip ? el("a", { href: `#dipendente/${r.persona_id}/${s.inizio}`, title: "Vedi solo i suoi turni" }, r.nome) : r.nome,
        assenze ? el("span", { class: "muted riepilogo-assenze" }, ` (${assenze})`) : null),
      el("td", {}, etichetta("tipo", r.tipo)),
      el("td", { class: "num" }, formatOre(r.ore)),
      el("td", { class: "num" }, formatOre(r.ore_giorno)),
      el("td", { class: "num" }, formatOre(r.ore_notte)),
      el("td", { class: "num" }, formatOre(r.turni_weekend)),
      el("td", { class: `num${estremo ? " scarto-alto" : ""}` },
      contate === null ? "—" : formatOre(contate),
      dip && r.max_ore_settimana && contate !== null
        ? el("span", { class: "muted" }, ` (max ${formatOre(r.max_ore_settimana)} h, fuori confronto)`) : null,
      estremo ? el("span", { class: "sr-only" }, ` (${estremo}: differenza oltre ${formatOre(limite)} ore)`) : null),
    );
  }));
  sezione.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Persona"),
      el("th", { scope: "col" }, "Tipo"),
      el("th", { scope: "col", class: "num" }, "Ore"),
      el("th", { scope: "col", class: "num" }, "Giorno"),
      el("th", { scope: "col", class: "num" }, "Notte"),
      el("th", { scope: "col", class: "num" }, "Turni weekend"),
      el("th", { scope: "col", class: "num", title: "Ore lavorate più 6 ore per ogni giorno di ferie: sono le ore confrontate tra i dipendenti" }, "Ore contate"))),
    tbody)));
  return sezione;
}

// ---------------------------------------------------------------- disponibilità

/** Id delle persone che hanno `data` nella lista [{persona_id, data}], e (se `parti`) una di quelle parti. */
function giorniPersona(lista, data, parti = null) {
  return new Set((lista || []).filter((x) => x.data === data && (!parti || parti.includes(x.parte)))
    .map((x) => x.persona_id));
}

/** Parti indisponibili per persona e data: Map "persona|data" -> Set di parti. */
function partiIndisponibili(lista) {
  const out = new Map();
  for (const x of lista || []) {
    const chiave = `${x.persona_id}|${x.data}`;
    if (!out.has(chiave)) out.set(chiave, new Set());
    out.get(chiave).add(x.parte);
  }
  return out;
}

/** Il menu di un giorno: le scelte standard, più la combinazione salvata se non è tra queste. */
function menuIndisponibilita(parti) {
  const valore = valoreParti(parti);
  const scelte = SCELTE_INDISPONIBILITA.some(([v]) => v === valore)
    ? SCELTE_INDISPONIBILITA : [...SCELTE_INDISPONIBILITA, [valore, etichettaParti(parti)]];
  return { valore, opzioni: scelte.map(([v, testo]) => el("option", { value: v, selected: v === valore }, testo)) };
}

function renderDisponibilita(s) {
  const confermata = s.stato === "confermata";
  const dipendenti = stato.persone
    .filter((p) => p.tipo === "dipendente" && p.attivo)
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const ferie = new Map((s.ferie || []).map((x) => [`${x.persona_id}|${x.data}`, x.motivo]));
  const indisp = partiIndisponibili(s.indisponibilita);
  const n = indisp.size;  // giorni con almeno una parte indisponibile
  const nFerie = new Set((s.ferie || []).filter((x) => x.motivo !== "malattia").map((x) => x.persona_id)).size;
  const nMalattia = new Set((s.ferie || []).filter((x) => x.motivo === "malattia").map((x) => x.persona_id)).size;

  const riepilogo = [n ? `${n} giorni indisponibili` : "nessuna indisponibilità",
    nFerie ? `${nFerie} in ferie` : null, nMalattia ? `${nMalattia} in malattia` : null].filter(Boolean).join(" · ");
  const aperto = stato.dispAperta[s.inizio] ?? s.stato === "nuova";
  const blocco = el("details", {
    class: "pannello disponibilita", open: aperto,
    ontoggle: (e) => { stato.dispAperta[s.inizio] = e.currentTarget.open; },
  },
    el("summary", {}, el("h2", { class: "disponibilita-titolo" }, "Disponibilità dipendenti"),
      el("span", { class: "muted" }, ` ${riepilogo}`)),
    el("p", { class: "muted" },
      "Per ogni giorno scegli quando un dipendente non può lavorare (mattina, pomeriggio, notte): non riceverà ",
      "turni che coprono quella parte. La notte è quella che inizia la sera del giorno scelto. ",
      "Ferie e malattia si inseriscono in Personale: ogni giorno conta 6 ore."));
  if (!dipendenti.length) {
    blocco.append(el("p", { class: "muted" }, "Nessun dipendente attivo."));
    return blocco;
  }

  const tbody = el("tbody", {}, dipendenti.map((p) => el("tr", {},
    el("th", { scope: "row" }, p.nome),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      const classe = `disp-cella${i >= 5 ? " weekend" : ""}`;
      if (ferie.has(`${p.id}|${g}`)) {
        return el("td", { class: classe }, badgeAssenza(ferie.get(`${p.id}|${g}`)));
      }
      const menu = menuIndisponibilita(indisp.get(`${p.id}|${g}`) || new Set());
      return el("td", { class: `${classe}${menu.valore ? " disp-indisponibile" : ""}` }, el("select", {
        id: `disp-${p.id}-${g}`,  // per ridare il focus dopo il salvataggio (il pannello si ricostruisce)
        disabled: confermata || stato.occupato,
        "aria-label": `${p.nome} indisponibile ${GIORNI_BREVI[i]} ${ddmm(g)}`,
        "data-precedente": menu.valore,
        onchange: (e) => onCambiaIndisponibilita(p, g, e.target),
      }, menu.opzioni));
    }))));

  blocco.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-disponibilita" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Dipendente"),
      s.giorni.map((g) => {
        const i = indiceGiorno(g);
        return el("th", { scope: "col", class: `disp-cella${i >= 5 ? " weekend" : ""}` }, `${GIORNI_BREVI[i]} ${ddmm(g)}`);
      }))),
    tbody)));
  return blocco;
}

// I salvataggi dei pannelli (disponibilità, richieste) vanno al server uno alla volta, nell'ordine in cui
// l'utente li fa: così l'ultima risposta è sempre la più recente, e Genera/Conferma li aspettano.
let coda = Promise.resolve();

function inCoda(fn) {
  const risultato = coda.then(fn);
  coda = risultato.catch(() => {});
  return risultato;
}

async function onCambiaIndisponibilita(p, data, menu) {
  const idFocus = menu.id;
  const precedente = menu.dataset.precedente;
  const scelte = menu.value ? menu.value.split("+") : [];
  const cella = menu.closest("td");
  cella.classList.toggle("disp-indisponibile", Boolean(menu.value));  // subito, senza aspettare il server
  menu.disabled = true;
  try {
    // le altre indisponibilità si leggono al momento dell'invio, dopo i salvataggi precedenti in coda
    await inCoda(async () => {
      const turni = (stato.settimana.indisponibilita || [])
        .filter((x) => x.persona_id === p.id && x.data !== data)
        .map((x) => ({ data: x.data, parte: x.parte }));
      for (const parte of PARTI_TURNO.filter((x) => scelte.includes(x))) turni.push({ data, parte });
      aggiorna(await api.impostaIndisponibilita(stato.data, p.id, turni));
    });
    rifocalizza(idFocus);
  } catch (err) {
    toastErrore(err);
    menu.value = precedente;
    cella.classList.toggle("disp-indisponibile", Boolean(precedente));
    menu.disabled = false;
  }
}

// ---------------------------------------------------------------- richieste Standby / Programmati

/** Ripristina il focus sull'elemento con lo stesso id dopo un nuovo render (il pannello viene ricostruito). */
function rifocalizza(id) {
  if (!id) return;
  const nodo = document.getElementById(id);
  if (nodo && !nodo.disabled) nodo.focus();
}

async function salvaFabbisogno(voci, idFocus) {
  const data = stato.data;
  await inCoda(async () => aggiorna(await api.impostaFabbisogno(data, voci)));
  rifocalizza(idFocus);
}

function intestazioneGiorni(s, primaColonna) {
  return el("thead", {}, el("tr", {},
    el("th", { scope: "col" }, primaColonna),
    s.giorni.map((g) => {
      const i = indiceGiorno(g);
      return el("th", { scope: "col", class: `disp-cella${i >= 5 ? " weekend" : ""}` }, `${GIORNI_BREVI[i]} ${ddmm(g)}`);
    })));
}

function renderRichieste(s) {
  const attive = s.postazioni_a_richiesta || [];
  const bloccato = s.stato === "confermata" || stato.occupato;
  const fabb = s.fabbisogno || [];
  const nStandby = new Set(fabb.filter((f) => f.postazione === STANDBY && f.quantita > 0)
    .map((f) => `${f.data}|${f.fascia}`)).size;
  const nProg = fabb.filter((f) => f.postazione === PROGRAMMATI)
    .reduce((t, f) => t + (Number(f.quantita) || 0), 0);
  const riepilogo = [
    attive.includes(STANDBY) ? (nStandby ? `${nStandby} ${nStandby === 1 ? "turno" : "turni"} Standby` : "nessuno Standby") : null,
    attive.includes(PROGRAMMATI) ? (nProg ? `${nProg} ${nProg === 1 ? "posto" : "posti"} nei Programmati` : "nessun Programmato") : null,
  ].filter(Boolean).join(" · ");

  const aperto = stato.richAperta[s.inizio] ?? s.stato === "nuova";
  const blocco = el("details", {
    class: "pannello richieste", open: aperto,
    ontoggle: (e) => { stato.richAperta[s.inizio] = e.currentTarget.open; },
  },
    el("summary", {}, el("h2", { class: "richieste-titolo" }, "Richieste Standby e Programmati"),
      el("span", { class: "muted" }, ` ${riepilogo}`)),
    el("p", { class: "muted" },
      "Indica prima di generare quando servono. Ogni Standby richiede un autista e un soccorritore; ",
      "nei Programmati indica quante persone servono per ruolo. I turni non richiesti non vengono assegnati."));

  if (attive.includes(STANDBY)) blocco.append(renderRichiesteStandby(s, bloccato));
  if (attive.includes(PROGRAMMATI)) blocco.append(renderRichiesteProgrammati(s, bloccato));
  return blocco;
}

function renderRichiesteStandby(s, bloccato) {
  const tbody = el("tbody", {}, FASCE.map((fascia) => {
    const turno = orarioTurno(fascia, "standby");
    return el("tr", {},
      el("th", { scope: "row" }, turno),
      s.giorni.map((g) => {
        const i = indiceGiorno(g);
        const richiesto = RUOLI.some((r) => quantitaFabbisogno(s, g, STANDBY, fascia, "standby", r) > 0);
        return el("td", { class: `disp-cella${i >= 5 ? " weekend" : ""}` }, el("input", {
          type: "checkbox", id: `rich-standby-${g}-${fascia}`, checked: richiesto, disabled: bloccato,
          "aria-label": `Standby ${turno} ${GIORNI_BREVI[i]} ${ddmm(g)}: richiesto autista e soccorritore`,
          onchange: (e) => onCambiaStandby(g, fascia, e.target),
        }));
      }));
  }));
  return el("section", { class: "richieste-blocco", "aria-labelledby": "titolo-rich-standby" },
    el("h3", { id: "titolo-rich-standby" }, "Standby", el("span", { class: "muted" }, " · autista + soccorritore")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" },
      intestazioneGiorni(s, "Turno"), tbody)));
}

async function onCambiaStandby(data, fascia, checkbox) {
  const quantita = checkbox.checked ? 1 : 0;
  const voci = RUOLI.map((ruolo) => ({ data, postazione: STANDBY, fascia, segmento: "standby", ruolo, quantita }));
  const idFocus = checkbox.id;  // letto prima di disabilitare: un controllo disabilitato perde il focus
  checkbox.disabled = true;
  try {
    await salvaFabbisogno(voci, idFocus);
  } catch (err) {
    toastErrore(err);
    checkbox.checked = !checkbox.checked;
    checkbox.disabled = false;
  }
}

function renderRichiesteProgrammati(s, bloccato) {
  const righe = [];
  for (const segmento of SEGMENTI_PROG) {
    RUOLI.forEach((ruolo, idx) => {
      const turno = orarioTurno("giorno", segmento);
      const ruoloPlurale = ruolo === "autista" ? "Autisti" : "Soccorritori";
      righe.push(el("tr", { class: idx === 0 ? "inizio-fascia" : null },
        el("th", { scope: "row" },
          el("span", { class: "fascia-label" }, turno), " ", el("span", { class: "ruolo-label" }, ruoloPlurale)),
        s.giorni.map((g) => {
          const i = indiceGiorno(g);
          const valore = quantitaFabbisogno(s, g, PROGRAMMATI, "giorno", segmento, ruolo);
          return el("td", { class: `disp-cella${i >= 5 ? " weekend" : ""}` }, el("input", {
            type: "number", class: "input-quantita", id: `rich-prog-${g}-${segmento}-${ruolo}`,
            min: "0", max: String(MAX_PROGRAMMATI), step: "1", inputmode: "numeric",
            value: String(valore), disabled: bloccato, dataset: { valore: String(valore) },
            "aria-label": `Programmati ${turno} ${GIORNI_BREVI[i]} ${ddmm(g)}: numero di ${ruoloPlurale.toLowerCase()}`,
            onchange: (e) => onCambiaProgrammati(g, segmento, ruolo, e.target),
          }));
        })));
    });
  }
  return el("section", { class: "richieste-blocco", "aria-labelledby": "titolo-rich-prog" },
    el("h3", { id: "titolo-rich-prog" }, "Programmati", el("span", { class: "muted" }, " · persone per turno")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" },
      intestazioneGiorni(s, "Turno"), el("tbody", {}, righe))));
}

async function onCambiaProgrammati(data, segmento, ruolo, input) {
  const precedente = input.dataset.valore || "0";
  const testo = input.value.trim();
  // con testo non numerico (es. "e") il campo number vale "": non va scambiato per uno svuotamento
  const quantita = input.validity && input.validity.badInput ? NaN : testo === "" ? 0 : Number(testo);
  if (!Number.isInteger(quantita) || quantita < 0 || quantita > MAX_PROGRAMMATI) {
    toast(`Indica un numero intero da 0 a ${MAX_PROGRAMMATI}.`, "avviso");
    input.value = precedente;
    return;
  }
  if (String(quantita) === precedente) { input.value = precedente; return; }
  const idFocus = input.id;
  input.disabled = true;
  try {
    await salvaFabbisogno([{ data, postazione: PROGRAMMATI, fascia: "giorno", segmento, ruolo, quantita }], idFocus);
  } catch (err) {
    toastErrore(err);
    input.value = precedente;
    input.disabled = false;
  }
}

// ---------------------------------------------------------------- dipendenti liberi

/** I liberi hanno senso solo quando la settimana ha dei turni. */
function haTurni(s) {
  return s.assegnazioni.length > 0 && Array.isArray(s.liberi);
}

function liberiDel(s, data) {
  return (s.liberi || []).find((x) => x.data === data) || { data, liberi: [], indisponibili: [], ferie: [] };
}

function badgeAvvisi(avvisi, formato) {
  return (avvisi || []).map((a) => el("span", {
    class: `badge badge-avviso avviso-${a}`, title: AVVISI_LIBERI[a] ? AVVISI_LIBERI[a].lungo : a,
  }, AVVISI_LIBERI[a] ? AVVISI_LIBERI[a][formato] : a));
}

/** "ferie 3g", "malattia 2g" o "ferie 1g + malattia 2g" (contano allo stesso modo: 6 h al giorno). */
function descriviAssenze(r) {
  const malattia = r.giorni_malattia || 0;
  const ferie = r.giorni_ferie - malattia;
  return [ferie ? `ferie ${ferie}g` : null, malattia ? `malattia ${malattia}g` : null].filter(Boolean).join(" + ");
}

/** `senza`: avviso da non ripetere (è già il titolo della riga in cui compare la persona). */
function voceLibero(v, formato, senza = null) {
  return el("li", {}, el("span", { class: "libero-nome" }, v.nome),
    v.parti ? el("span", { class: "muted" }, ` (${etichettaParti(new Set(v.parti)).toLowerCase()})`) : null,
    v.motivo ? [" ", badgeAssenza(v.motivo)] : null,
    badgeAvvisi((v.avvisi || []).filter((a) => a !== senza), formato));
}

function apriLiberi(data) {
  if (!dialogLiberi) {
    dialogLiberi = el("dialog", { class: "dialog dialog-liberi", "aria-labelledby": "liberi-titolo" });
    document.body.appendChild(dialogLiberi);
  }
  dialogLiberi.dataset.data = data;
  renderDialogLiberi();
  if (!dialogLiberi.open) dialogLiberi.showModal();
  const chiudi = dialogLiberi.querySelector(".dialog-actions .btn");
  if (chiudi) chiudi.focus();
}

function renderDialogLiberi() {
  const s = stato.settimana;
  const g = liberiDel(s, dialogLiberi.dataset.data);
  const d = clear(dialogLiberi);
  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "liberi-titolo", class: "dialog-title" }, `Liberi · ${dataEstesa(g.data)}`),
    el("p", { class: "muted" }, "Dipendenti senza turni di giorno."),
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));
  d.append(el("section", { class: "dialog-section", "aria-label": "Liberi" },
    el("h3", {}, `Liberi (${g.liberi.length})`),
    g.liberi.length
      ? el("ul", { class: "lista-liberi" }, g.liberi.map((v) => voceLibero(v, "lungo")))
      : el("p", { class: "muted" }, "Nessun dipendente libero.")));
  if (g.indisponibili.length) {
    d.append(el("section", { class: "dialog-section", "aria-label": "Indisponibili" },
      el("h3", {}, `Indisponibili (${g.indisponibili.length})`),
      el("ul", { class: "lista-liberi" }, g.indisponibili.map((v) => voceLibero(v, "lungo")))));
  }
  if (g.ferie.length) {
    d.append(el("section", { class: "dialog-section", "aria-label": "In ferie o malattia" },
      el("h3", {}, `In ferie o malattia (${g.ferie.length})`),
      el("ul", { class: "lista-liberi" }, g.ferie.map((v) => voceLibero(v, "lungo")))));
  }
  d.append(el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Chiudi")));
}

/** Riepilogo dei liberi di tutta la settimana: visibile solo nella stampa "Stampa liberi". */
function renderStampaLiberi(s) {
  const giorni = s.giorni.map((g) => liberiDel(s, g));
  // chi smonta dalla notte e la rifà la sera compare in entrambe le righe
  const conAvviso = (avviso) => (g) => g.liberi.filter((v) => (v.avvisi || []).includes(avviso));
  const riga = (titolo, classe, persone, senza = null) => el("tr", { class: `riga-${classe}` },
    el("th", { scope: "row" }, titolo),
    giorni.map((g, i) => {
      const elenco = persone(g);
      return el("td", { class: i >= 5 ? "weekend" : null },
        elenco.length ? el("ul", { class: "lista-liberi" }, elenco.map((v) => voceLibero(v, "breve", senza))) : "—");
    }));
  return el("section", { class: "stampa-liberi" },
    el("h2", {}, "Dipendenti liberi"),
    el("table", { class: "tabella tabella-liberi" },
      el("thead", {}, el("tr", {},
        el("th", { scope: "col" }, ""),
        s.giorni.map((g) => thGiorno(s, g)))),
      el("tbody", {},
        riga("Liberi tutto il giorno", "liberi", (g) => g.liberi.filter((v) => !(v.avvisi || []).length)),
        riga("Smontano dalla notte", "smonto", conAvviso("smonto_notte"), "smonto_notte"),
        riga("Fanno la notte", "notte", conAvviso("notte"), "notte"),
        riga("Indisponibili", "indisponibili", (g) => g.indisponibili),
        riga("Ferie / malattia", "ferie", (g) => g.ferie))),
    el("p", { class: "nota-stampa" },
      "Smontano dalla notte = hanno fatto la notte il giorno prima (finiscono alle 8) · "
      + "Fanno la notte = sono liberi di giorno e fanno la notte quella sera."));
}

// Se "afterprint" non arriva (alcuni browser) la classe resta: la stampa normale la toglie comunque.
function stampaGriglia() {
  document.body.classList.remove("stampa-liberi-attiva");
  window.print();
}

function stampaLiberi() {
  document.body.classList.add("stampa-liberi-attiva");
  window.addEventListener("afterprint", () => document.body.classList.remove("stampa-liberi-attiva"), { once: true });
  window.print();
}

// ---------------------------------------------------------------- Assistenze ed Extra

function richiestaExtra(s, segmento) {
  return (s.extra || []).find((e) => e.segmento === segmento) || null;
}

function ruoliExtra(e) {
  return RUOLI.filter((r) => (r === "autista" ? e.autisti : e.soccorritori) > 0);
}

function cellaExtra(e, ruolo) {
  return { data: e.data, postazione: EXTRA, fascia: e.fascia, ruolo, segmento: e.segmento };
}

/** Tabellone delle Assistenze ed Extra (tutte le settimane): in ogni giorno le richieste, con i loro posti. */
function renderGrigliaExtra(s) {
  const confermata = s.stato === "confermata";
  const scopertiReport = new Set(((s.report && s.report.scoperti) || []).map((u) => chiaveCella(u)));
  const violazioni = indiceViolazioni(s);
  const richieste = s.extra || [];
  const thead = el("thead", {}, el("tr", {},
    el("th", { scope: "col", class: "col-turno" }, "Richieste"),
    s.giorni.map((g) => thGiorno(s, g))));
  const celle = s.giorni.map((g, i) => {
    const delGiorno = richieste.filter((e) => e.data === g)
      .sort((a, b) => a.inizio - b.inizio || a.id - b.id);
    const schede = delGiorno.map((e) => el("div", { class: `extra-scheda fascia-${e.fascia}` },
      el("div", { class: "extra-testa" },
        el("span", { class: "extra-nome" }, e.nome),
        el("span", { class: "extra-orario" },
          el("span", { "aria-hidden": "true" }, e.fascia === "notte" ? "☾ " : "☀ "), `${e.inizio}–${e.fine}`),
        confermata ? null : el("button", {
          type: "button", class: "btn btn-small extra-modifica no-print",
          "aria-label": `Modifica la richiesta ${e.nome}`, title: "Modifica o elimina la richiesta",
          onclick: () => apriExtra({ richiesta: e }),
        }, "Modifica")),
      ruoliExtra(e).map((ruolo) => el("div", { class: "extra-posto" },
        el("span", { class: "ruolo-label" }, etichetta("ruolo", ruolo)),
        renderCella(s, cellaExtra(e, ruolo), scopertiReport, violazioni, confermata, "div")))));
    const aggiungi = confermata ? null : el("button", {
      type: "button", class: "btn btn-small extra-aggiungi no-print",
      "aria-label": `Aggiungi una richiesta ${GIORNI_BREVI[i]} ${ddmm(g)}`,
      onclick: () => apriExtra({ data: g }),
    }, "+ Richiesta");
    return el("td", { class: `cella-extra${i >= 5 ? " weekend" : ""}` },
      schede, aggiungi, !schede.length && confermata ? el("span", { class: "non-richiesto" }, "—") : null);
  });
  const tbody = el("tbody", {}, el("tr", {},
    el("th", { scope: "row", class: "col-turno" }, el("span", { class: "ruolo-label" }, "Assistenze ed Extra")),
    celle));
  return el("section", {
    class: `griglia-blocco griglia-speciale griglia-extra${richieste.length ? "" : " griglia-vuota"}`,
    "aria-labelledby": "griglia-extra",
  },
  el("h2", { id: "griglia-extra", class: "griglia-titolo" }, EXTRA,
    el("span", { class: "griglia-sottotitolo muted no-print" },
      confermata ? "" : " · premi “+ Richiesta” nel giorno per aggiungerne una")),
  el("div", { class: "griglia-scroll" }, el("table", { class: "griglia" }, thead, tbody)));
}

/** Pannello di una richiesta: nuova (`data`) o da modificare (`richiesta`). */
function apriExtra({ data = null, richiesta = null }) {
  if (!dialogExtra) {
    dialogExtra = el("dialog", { class: "dialog dialog-extra", "aria-labelledby": "extra-titolo" });
    document.body.appendChild(dialogExtra);
  }
  const s = stato.settimana;
  const e = richiesta || { data, nome: "", inizio: 8, fine: 12, autisti: 1, soccorritori: 1 };
  const d = clear(dialogExtra);
  const ore = (id, valore) => el("select", { id, required: true },
    Array.from({ length: 24 }, (_, h) => el("option", { value: String(h), selected: h === valore }, `${h}:00`)));
  const numero = (id, valore) => el("input", {
    id, type: "number", min: "0", max: String(MAX_EXTRA), step: "1", inputmode: "numeric", value: String(valore),
  });
  const nome = el("input", { id: "extra-nome", type: "text", maxlength: "100", required: true, value: e.nome,
    autocomplete: "off", placeholder: "es. Partita allo stadio" });
  const giorno = el("select", { id: "extra-data" },
    s.giorni.map((g, i) => el("option", { value: g, selected: g === e.data }, `${GIORNI_BREVI[i]} ${ddmm(g)}`)));
  const dalle = ore("extra-inizio", e.inizio);
  const alle = ore("extra-fine", e.fine);
  const autisti = numero("extra-autisti", e.autisti);
  const soccorritori = numero("extra-soccorritori", e.soccorritori);
  const campo = (id, testo, input, cls = "campo") => el("div", { class: cls }, el("label", { for: id }, testo), input);
  const salva = el("button", { type: "submit", class: "btn btn-primary" }, richiesta ? "Salva" : "Aggiungi");

  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "extra-titolo", class: "dialog-title" },
      richiesta ? `Modifica richiesta · ${EXTRA}` : `Nuova richiesta · ${EXTRA}`),
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));
  d.append(el("form", {
    class: "dialog-section",
    onsubmit: async (ev) => {
      ev.preventDefault();
      const corpo = {
        data: giorno.value, nome: nome.value.trim(), inizio: Number(dalle.value), fine: Number(alle.value),
        autisti: Number(autisti.value) || 0, soccorritori: Number(soccorritori.value) || 0,
      };
      if (!corpo.nome) { nome.focus(); toast("Scrivi il nome della richiesta.", "avviso"); return; }
      if (corpo.inizio === corpo.fine) { alle.focus(); toast("L’ora di fine dev’essere diversa da quella di inizio.", "avviso"); return; }
      const fuori = [corpo.autisti, corpo.soccorritori].some((n) => !Number.isInteger(n) || n < 0 || n > MAX_EXTRA);
      if (fuori) { autisti.focus(); toast(`Il numero di persone va da 0 a ${MAX_EXTRA}.`, "avviso"); return; }
      if (corpo.autisti + corpo.soccorritori < 1) { autisti.focus(); toast("Serve almeno una persona.", "avviso"); return; }
      salva.disabled = true;
      try {
        const nuova = richiesta ? await api.modificaExtra(richiesta.id, corpo) : await api.creaExtra(stato.data, corpo);
        d.close();
        aggiorna(nuova);
        toast(richiesta ? "Richiesta modificata." : "Richiesta aggiunta.", "ok");
      } catch (err) {
        toastErrore(err);
        salva.disabled = false;
      }
    },
  },
  el("div", { class: "campi" },
    campo("extra-nome", "Nome della richiesta", nome, "campo campo-largo"),
    campo("extra-data", "Giorno", giorno),
    campo("extra-inizio", "Dalle", dalle),
    campo("extra-fine", "Alle", alle),
    campo("extra-autisti", "Autisti", autisti),
    campo("extra-soccorritori", "Soccorritori", soccorritori)),
  el("p", { class: "hint" }, "Se l’ora di fine è prima di quella di inizio, la richiesta finisce il giorno dopo (es. 22:00–2:00)."),
  el("div", { class: "form-actions" },
    salva,
    richiesta ? el("button", {
      type: "button", class: "btn btn-danger",
      onclick: async (ev) => {
        const btn = ev.currentTarget;  // dopo l'await currentTarget non c'è più
        const occupati = s.assegnazioni.filter((a) => a.segmento === richiesta.segmento).length;
        const testo = occupati === 1 ? "Verrà tolta anche la persona assegnata."
          : occupati ? `Verranno tolte anche le ${occupati} persone assegnate.` : "La richiesta verrà eliminata.";
        const ok = await chiediConferma(testo, { titolo: `Eliminare “${richiesta.nome}”?`, ok: "Elimina", pericolo: true });
        if (!ok) return;
        btn.disabled = true;
        try {
          await api.eliminaExtra(richiesta.id);
          d.close();
          await ricarica();
          toast("Richiesta eliminata.", "ok");
        } catch (err) {
          toastErrore(err);
          btn.disabled = false;
        }
      },
    }, "Elimina") : null,
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Annulla"))));
  if (!d.open) d.showModal();
  nome.focus();
}

// ---------------------------------------------------------------- dialog cella

function apriDialog(cella) {
  if (!dialogCella) {
    dialogCella = el("dialog", { class: "dialog dialog-cella", "aria-labelledby": "cella-titolo" });
    dialogCella.addEventListener("close", () => { stato.cellaAperta = null; });
    document.body.appendChild(dialogCella);
  }
  stato.cellaAperta = cella;
  renderDialog();
  if (!dialogCella.open) dialogCella.showModal();
  const primo = dialogCella.querySelector("#cella-volontario, .btn-danger, .btn");
  if (primo) primo.focus();
}

function renderDialog() {
  const s = stato.settimana;
  const c = stato.cellaAperta;
  const confermata = s.stato === "confermata";
  const lista = assegnazioniCella(s, c)
    .sort((a, b) => ordineSegmento(a.segmento) - ordineSegmento(b.segmento));
  const cop = coperturaCella(s, c, lista);
  const prog = perSegmento(c.postazione);  // più posti nello stesso turno
  const richiesta = c.postazione === EXTRA ? richiestaExtra(s, c.segmento) : null;
  const d = clear(dialogCella);

  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "cella-titolo", class: "dialog-title" },
      `${richiesta ? `${richiesta.nome} (${EXTRA})` : c.postazione} · ${dataEstesa(c.data)}`),
    el("p", { class: "muted" }, `${orarioTurno(c.fascia, segmentoCella(c))} · ${etichetta("ruolo", c.ruolo)}`,
      prog ? ` · ${cop.richiesti} ${cop.richiesti === 1 ? "richiesto" : "richiesti"}` : ""),
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));

  // Assegnazioni esistenti
  const esistenti = el("section", { class: "dialog-section", "aria-label": "Assegnazioni presenti" },
    el("h3", {}, "Assegnati"));
  if (!lista.length) {
    esistenti.append(cop.richiesti
      ? el("p", { class: "scoperto-text" }, prog && cop.richiesti > 1 ? "Nessuno: posti scoperti." : "Nessuno: posto scoperto.")
      : el("p", { class: "muted" }, "Nessuno."));
  } else {
    esistenti.append(el("ul", { class: "lista-assegnati" }, lista.map((a) => el("li", {},
      el("span", { class: `chip chip-${a.origine}` }, el("span", { class: "chip-nome" }, a.persona_nome)),
      el("span", { class: "muted" }, `${etichetta("segmentoLungo", a.segmento)} · ${etichetta("origine", a.origine)}${a.ore ? ` · ${formatOre(a.ore)} h` : ""}`),
      el("button", {
        type: "button", class: "btn btn-small btn-danger", disabled: confermata,
        "aria-label": `Rimuovi ${a.persona_nome}`,
        onclick: (e) => onEliminaAssegnazione(a, e.currentTarget),
      }, "Rimuovi")))));
  }
  const mancanti = cop.mancanti;
  if (lista.length && mancanti.length) {
    esistenti.append(el("p", { class: "scoperto-text" },
      `Manca: ${mancanti.map((m) => etichetta("segmentoLungo", m)).join(", ")}`));
  }
  if (prog && lista.length && cop.nMancanti) {
    esistenti.append(el("p", { class: "scoperto-text" },
      cop.nMancanti === 1 ? "Manca ancora 1 persona." : `Mancano ancora ${cop.nMancanti} persone.`));
  }
  if (cop.eccesso) {
    esistenti.append(el("p", { class: "eccesso-text" }, cop.richiesti
      ? `Assegnate ${cop.eccesso} persone in più del richiesto.`
      : "Turno non richiesto: rimuovi le assegnazioni o indica il fabbisogno nelle richieste."));
  }
  d.append(esistenti);

  // Form aggiunta
  if (confermata) {
    d.append(el("p", { class: "banner banner-info" }, "Settimana confermata: riaprila per modificare."));
  } else if (!cop.richiesti) {
    d.append(el("p", { class: "banner banner-info" },
      "Turno non richiesto: per assegnarlo indicalo prima nel pannello “Richieste Standby e Programmati”."));
  } else if (prog && !cop.nMancanti) {
    d.append(el("p", { class: "banner banner-info" },
      "Tutti i posti richiesti sono occupati: aumenta il numero nelle richieste per aggiungere altre persone."));
  } else {
    d.append(renderFormAggiunta(c, mancanti));
  }
  d.append(el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Chiudi")));
}

function renderFormAggiunta(c, mancanti) {
  const s = stato.settimana;
  const oreSettimana = new Map((s.riepilogo || []).map((r) => [r.persona_id, r.ore]));
  const giaInCella = new Set(assegnazioniCella(s, c).map((a) => a.persona_id));
  const inFerie = new Map((s.ferie || []).filter((x) => x.data === c.data).map((x) => [x.persona_id, x.motivo]));
  // indisponibile solo se la sua indisponibilità tocca le ore di questo turno
  const indisponibili = giorniPersona(s.indisponibilita, c.data, partiTurno(c.fascia, segmentoCella(c)));
  const prog = c.postazione === PROGRAMMATI;  // "autista programmati" vale solo qui
  // l'autista può fare anche il soccorritore; nei Programmati guida anche chi ha "autista programmati"
  const puoRicoprire = (p) => c.ruolo === "soccorritore" || p.qualifica === "autista"
    || (prog && !!p.autista_programmati);
  const dipendenti = stato.persone
    .filter((p) => p.tipo === "dipendente" && p.attivo && puoRicoprire(p))
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const volontariNoti = stato.persone.filter((p) => p.tipo === "volontario")
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));

  // Volontario: basta scrivere il nome (se è nuovo viene registrato in automatico)
  const nomeVol = el("input", {
    id: "cella-volontario", type: "text", maxlength: "100", autocomplete: "off", list: "cella-volontari-noti",
  });
  const suggerimenti = el("datalist", { id: "cella-volontari-noti" },
    volontariNoti.map((p) => el("option", { value: p.nome })));
  const campoVol = el("div", { class: "campo campo-largo" },
    el("label", { for: "cella-volontario" }, "Nome del volontario"), nomeVol, suggerimenti,
    el("p", { class: "hint" }, "Se è la prima volta che fa un turno viene registrato in automatico."));

  // Dipendente: elenco
  const select = el("select", { id: "cella-persona", name: "persona_id" },
    el("option", { value: "" }, "— Seleziona —"),
    dipendenti.map((p) => {
      const ore = oreSettimana.get(p.id);
      const extra = [inFerie.has(p.id) ? (inFerie.get(p.id) === "malattia" ? "IN MALATTIA" : "IN FERIE") : null, indisponibili.has(p.id) ? "INDISPONIBILE" : null,
        vietato(p.id, c.postazione, c.fascia, segmentoCella(c)) ? "NON PUÒ" : null,
        p.qualifica === "autista" ? "autista" : (prog && p.autista_programmati ? "autista programmati" : null), ore ? `${formatOre(ore)} h` : null, giaInCella.has(p.id) ? "già qui" : null]
        .filter(Boolean).join(", ");
      return el("option", { value: String(p.id) }, extra ? `${p.nome} (${extra})` : p.nome);
    }));
  const campoDip = el("div", { class: "campo campo-largo", hidden: true },
    el("label", { for: "cella-persona" }, "Dipendente"), select,
    !dipendenti.length ? el("p", { class: "hint" }, c.ruolo === "autista"
      ? "Nessun dipendente attivo con qualifica autista."
      : "Nessun dipendente attivo. Aggiungilo nella sezione Personale.") : null,
    c.ruolo === "autista" && dipendenti.length ? el("p", { class: "hint" }, prog
      ? "Sono elencati i dipendenti autisti e i soccorritori abilitati come autisti programmati."
      : "Sono elencati solo i dipendenti autisti.") : null);

  let chi = "volontario";
  const scegli = (valore) => {
    chi = valore;
    campoVol.hidden = valore !== "volontario";
    campoDip.hidden = valore !== "dipendente";
    (valore === "volontario" ? nomeVol : select).focus();
  };
  const interruttore = el("div", { class: "campo", role: "radiogroup", "aria-label": "Chi fa il turno" },
    ["volontario", "dipendente"].map((v) => el("label", { class: "check" },
      el("input", { type: "radio", name: "cella-chi", value: v, checked: v === chi, onchange: () => scegli(v) }),
      ` ${etichetta("tipo", v)}`)));

  const campi = [interruttore, campoVol, campoDip];
  // Segmento: il turno di giorno (normali e Standby) si può spezzare; notte e Programmati no.
  let segSelect = null;
  if (c.fascia === "giorno" && !perSegmento(c.postazione)) {
    const intero = segmentoIntero(c.postazione);
    const predefinito = mancanti.length === 1 ? mancanti[0] : intero;
    segSelect = el("select", { id: "cella-segmento", name: "segmento" },
      [intero, ...metaGiorno(c.postazione)].map((seg) => el("option", { value: seg, selected: seg === predefinito },
        seg === intero ? `Intero ${orarioTurno("giorno", seg).replace(/^\S+ /, "")}` : orarioTurno("giorno", seg))));
    campi.push(el("div", { class: "campo" }, el("label", { for: "cella-segmento" }, "Segmento"), segSelect));
  }

  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi");
  const form = el("form", {
    class: "dialog-section form-aggiunta",
    onsubmit: async (e) => {
      e.preventDefault();
      const turno = {
        data: c.data, postazione: c.postazione, fascia: c.fascia,
        segmento: segSelect ? segSelect.value : segmentoCella(c), ruolo: c.ruolo,
      };
      if (chi === "volontario") {
        const nome = nomeVol.value.trim();
        if (!nome) { nomeVol.focus(); toast("Scrivi il nome del volontario.", "avviso"); return; }
        turno.nome_volontario = nome;
      } else {
        if (!select.value) { select.focus(); toast("Seleziona un dipendente.", "avviso"); return; }
        turno.persona_id = Number(select.value);
      }
      invia.disabled = true;
      try {
        const nuova = await api.aggiungiAssegnazione(stato.data, turno);
        dialogCella.close();
        aggiorna(nuova);
        toast("Assegnazione aggiunta.", "ok");
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
        return;
      }
      if (turno.nome_volontario) {
        // può essere un volontario nuovo: serve per i suggerimenti; se fallisce il turno è comunque salvato
        try { stato.persone = await api.persone(); } catch { /* si aggiorna al prossimo caricamento */ }
      }
    },
  }, el("h3", {}, "Aggiungi"), el("div", { class: "campi" }, campi), el("div", { class: "form-actions" }, invia));
  return form;
}

async function onEliminaAssegnazione(a, btn) {
  btn.disabled = true;
  try {
    await api.eliminaAssegnazione(a.id);
    await ricarica();
    toast(`${a.persona_nome} rimosso dal turno.`, "ok");
    const focus = dialogCella && dialogCella.open && dialogCella.querySelector("select, .btn");
    if (focus) focus.focus();
  } catch (err) {
    toastErrore(err);
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- azioni toolbar

async function eseguiAzione(fn, { overlay = null } = {}) {
  if (stato.occupato) return;
  stato.occupato = true;
  render();
  const ov = document.getElementById("overlay");
  if (overlay && ov) {
    ov.querySelector(".overlay-msg").textContent = overlay;
    ov.hidden = false;
  }
  try {
    const risultato = await inCoda(fn);  // dopo eventuali salvataggi dei pannelli ancora in corso
    stato.occupato = false;
    if (risultato) aggiorna(risultato); else render();
    return risultato;
  } catch (err) {
    stato.occupato = false;
    render();
    toastErrore(err);
    return null;
  } finally {
    if (ov) ov.hidden = true;
  }
}

function tempoGenerazione() {
  let valore = null;
  try { valore = Number(localStorage.getItem(CHIAVE_TEMPO)); } catch { /* ignora */ }
  return Number.isInteger(valore) && valore >= TEMPO_MIN && valore <= TEMPO_MAX ? valore : TEMPO_PREDEFINITO;
}

function salvaTempo(input) {
  const valore = Number(input.value);
  if (!Number.isInteger(valore) || valore < TEMPO_MIN || valore > TEMPO_MAX) {
    toast(`Il tempo massimo va da ${TEMPO_MIN} a ${TEMPO_MAX} secondi.`, "avviso");
    input.value = String(tempoGenerazione());
    return;
  }
  try { localStorage.setItem(CHIAVE_TEMPO, String(valore)); } catch { /* ignora */ }
}

async function onGenera() {
  const s = stato.settimana;
  if (s.assegnazioni.some((a) => a.origine === "generato")) {
    const ok = await chiediConferma(
      "Le assegnazioni generate in precedenza verranno sostituite. Quelle dei volontari e quelle fissate manualmente restano invariate.",
      { titolo: "Rigenerare i turni?", ok: "Rigenera" });
    if (!ok) return;
  }
  const tempo = tempoGenerazione();
  const sotto = document.querySelector("#overlay .overlay-sub");
  if (sotto) sotto.textContent = `Può richiedere fino a ${tempo < 90 ? `${tempo} secondi` : `${Math.ceil(tempo / 60)} minuti`}.`;
  const r = await eseguiAzione(() => api.genera(stato.data, tempo), { overlay: "Generazione in corso…" });
  if (r && r.report) {
    const rep = r.report;
    const n = (rep.scoperti || []).length;
    const okStato = ["ottimo", "ammissibile"].includes(rep.stato);
    const testo = !okStato ? "Turni non generati: vedi il messaggio sopra la griglia."
      : n ? `Turni generati: ${n === 1 ? "1 posto scoperto" : `${n} posti scoperti`}.` : "Turni generati.";
    toast(testo, okStato ? (n ? "avviso" : "ok") : "errore");
  }
}

async function onRimuoviGenerati() {
  const ok = await chiediConferma("Verranno rimosse tutte le assegnazioni generate automaticamente in questa settimana.",
    { titolo: "Rimuovere i turni generati?", ok: "Rimuovi", pericolo: true });
  if (!ok) return;
  if (await eseguiAzione(() => api.rimuoviGenerati(stato.data))) toast("Assegnazioni generate rimosse.", "ok");
}

async function onConferma() {
  const s = stato.settimana;
  const errori = (s.violazioni || []).filter((v) => v.livello === "errore").length;
  const scoperti = contaScoperti(s);
  const note = [];
  if (errori) note.push(`${errori} errori nei controlli`);
  if (scoperti) note.push(`${scoperti} posti scoperti`);
  const ok = await chiediConferma(
    note.length
      ? `Attenzione: ${note.join(" e ")}. Confermando, la settimana non sarà più modificabile finché non verrà riaperta.`
      : "Confermando, la settimana non sarà più modificabile finché non verrà riaperta.",
    { titolo: "Confermare la settimana?", ok: "Conferma" });
  if (!ok) return;
  if (await eseguiAzione(() => api.conferma(stato.data))) toast("Settimana confermata.", "ok");
}

async function onRiapri() {
  if (await eseguiAzione(() => api.riapri(stato.data))) toast("Settimana riaperta.", "ok");
}

/** Posti scoperti della settimana, comprese le postazioni a richiesta (solo i turni richiesti). */
function contaScoperti(s) {
  let n = 0;
  const postazioni = [...s.postazioni, ...(s.postazioni_a_richiesta || [])];
  for (const postazione of postazioni) for (const riga of righeGriglia(postazione)) for (const g of s.giorni) {
    const c = { data: g, postazione, fascia: riga.fascia, ruolo: riga.ruolo };
    if (riga.segmento) c.segmento = riga.segmento;
    n += coperturaCella(s, c, assegnazioniCella(s, c)).nMancanti;
  }
  for (const e of s.extra || []) for (const ruolo of ruoliExtra(e)) {
    const c = cellaExtra(e, ruolo);
    n += coperturaCella(s, c, assegnazioniCella(s, c)).nMancanti;
  }
  return n;
}
