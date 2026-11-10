// Vista "Turni della settimana": procedura guidata per chi non usa il programma completo.
// Mostra la settimana; se non è ancora generata guida passo passo: volontari, ferie e malattie, indisponibilità,
// riepilogo, generazione (con conferma automatica). Poi i turni si vedono e si scaricano in PDF.

import { api } from "./api.js";
import {
  el, toast, toastErrore, chiediConferma, addDays, mondayOf, todayISO, ddmm, parseISO, GIORNI_BREVI, indiceGiorno,
  etichetta, orarioTurno, PARTI_TURNO, SCELTE_INDISPONIBILITA, etichettaParti, badgeAssenza,
} from "./util.js";

const TEMPO_GENERAZIONE = 180;  // secondi
const PASSI = ["Servizi", "Volontari", "Ferie e malattie", "Indisponibilità", "Riepilogo", "Generazione"];
const P = { servizi: 0, volontari: 1, ferie: 2, indisponibilita: 3, riepilogo: 4, generazione: 5 };
const STANDBY = "Standby";
const PROGRAMMATI = "Programmati";
// turni richiedibili (come TURNI_RICHIEDIBILI in app.py): [postazione, fascia, segmento, etichetta]
const TURNI_RICHIESTA = [
  [STANDBY, "giorno", "standby", "Standby giorno 7–19"], [STANDBY, "notte", "standby", "Standby notte 19–7"],
  [PROGRAMMATI, "giorno", "prog_mattina", "Programmati mattina 7–14"],
  [PROGRAMMATI, "giorno", "prog_pomeriggio", "Programmati pomeriggio 14–20"],
];
const RUOLI = ["autista", "soccorritore"];
// turni che un volontario può coprire: [fascia, segmento, etichetta]
const TURNI_VOLONTARI = [
  ["giorno", "intero", "Giorno 8–20"], ["giorno", "mattina", "Mattina 8–14"],
  ["giorno", "pomeriggio", "Pomeriggio 14–20"], ["notte", "intero", "Notte 20–8"],
];

// servizi: null = non ancora chiesto se servono Standby, Programmati o Assistenze; true/false = risposta
const stato = { root: null, data: null, settimana: null, persone: [], ferie: [], passo: null, generando: false, servizi: null };

const giorno = (iso) => `${GIORNI_BREVI[indiceGiorno(iso)]} ${ddmm(iso)}`;
const annoBreve = (iso) => `${ddmm(iso)}/${parseISO(iso).getFullYear()}`;
const nome = (id) => (stato.persone.find((p) => p.id === id) || {}).nome || `n. ${id}`;
const dipendenti = () => stato.persone.filter((p) => p.tipo === "dipendente" && p.attivo);
const volontari = () => stato.persone.filter((p) => p.tipo === "volontario");
const opzione = (valore, testo, scelto) => el("option", { value: valore, selected: valore === scelto }, testo);
const generata = (s) => s.stato === "confermata" || s.assegnazioni.some((a) => a.origine === "generato");

function turniVolontari() {
  const ids = new Set(volontari().map((p) => p.id));
  return stato.settimana.assegnazioni.filter((a) => ids.has(a.persona_id))
    .sort((a, b) => a.data.localeCompare(b.data) || a.fascia.localeCompare(b.fascia));
}

function ferieSettimana() {
  const { inizio, fine } = stato.settimana;
  return stato.ferie.filter((f) => f.dal <= fine && f.al >= inizio)
    .sort((a, b) => a.dal.localeCompare(b.dal) || nome(a.persona_id).localeCompare(nome(b.persona_id)));
}

/** Indisponibilità della settimana per persona e giorno: [{persona_id, data, parti: Set}] */
function indisponibilita() {
  const mappa = new Map();
  for (const i of stato.settimana.indisponibilita || []) {
    const chiave = `${i.persona_id}|${i.data}`;
    if (!mappa.has(chiave)) mappa.set(chiave, { persona_id: i.persona_id, data: i.data, parti: new Set() });
    mappa.get(chiave).parti.add(i.parte);
  }
  return [...mappa.values()].sort((a, b) => a.data.localeCompare(b.data) || nome(a.persona_id).localeCompare(nome(b.persona_id)));
}

async function carica() {
  const [settimana, persone, ferie] = await Promise.all([api.settimana(stato.data), api.persone(), api.ferie()]);
  Object.assign(stato, { settimana, persone, ferie });
}

/** Esegue un'azione, ricarica i dati e ridisegna; gli errori diventano un avviso. */
async function esegui(azione, messaggio) {
  try {
    await azione();
    await carica();
    if (messaggio) toast(messaggio, "ok");
  } catch (err) {
    toastErrore(err);
  }
  disegna();
}

// ---------------------------------------------------------------- pagina della settimana

function intestazione() {
  const s = stato.settimana;
  const vai = (data) => { location.hash = `#genera/${mondayOf(data)}`; };
  const scelta = el("input", { type: "date", value: s.inizio, "aria-label": "Vai alla settimana del giorno",
    onchange: (e) => e.target.value && vai(e.target.value) });
  return el("header", { class: "view-header guida-testa" },
    el("h1", {}, "Turni della settimana"),
    el("p", { class: "guida-periodo" }, `Dal ${giorno(s.inizio)} al ${giorno(s.fine)}/${parseISO(s.fine).getFullYear()}`),
    el("div", { class: "guida-settimane" },
      el("button", { type: "button", class: "btn btn-secondary", onclick: () => vai(addDays(s.inizio, -7)) }, "‹ Precedente"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => vai(todayISO()) }, "Questa settimana"),
      el("button", { type: "button", class: "btn btn-secondary", onclick: () => vai(addDays(s.inizio, 7)) }, "Successiva ›"),
      el("label", { class: "guida-vai" }, "Vai a ", scelta)));
}

async function scaricaPdf(tipo) {
  const percorso = `/api/settimane/${stato.settimana.inizio}/pdf-${tipo}`;
  try {
    const r = await fetch(percorso, { credentials: "same-origin" });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Errore ${r.status}`);
    const url = URL.createObjectURL(await r.blob());
    const a = el("a", { href: url, download: `${tipo === "liberi" ? "liberi" : "turni"}-${stato.settimana.inizio}.pdf` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  } catch (err) {
    toastErrore(err);
  }
}

/** Tabella dei turni in sola lettura: una riga per postazione, fascia e ruolo; una colonna per giorno. */
function tabellaTurni(s) {
  const postazioni = [...s.postazioni, ...new Set(s.assegnazioni.map((a) => a.postazione).filter((p) => !s.postazioni.includes(p)))];
  const righe = [];
  for (const postazione of postazioni) {
    for (const fascia of ["giorno", "notte"]) {
      for (const ruolo of RUOLI) {
        const turni = s.assegnazioni.filter((a) => a.postazione === postazione && a.fascia === fascia && a.ruolo === ruolo);
        if (!turni.length && !s.postazioni.includes(postazione)) continue;
        righe.push(el("tr", {},
          el("th", { scope: "row" }, el("strong", {}, postazione),
            el("div", { class: "muted" }, `${etichetta("fasciaBreve", fascia)} · ${etichetta("ruolo", ruolo)}`)),
          s.giorni.map((g) => {
            const chi = turni.filter((a) => a.data === g);
            return el("td", { class: chi.length ? null : "guida-vuoto" }, chi.length
              ? chi.map((a) => el("div", {}, a.persona_nome,
                a.segmento === "intero" ? null : el("span", { class: "muted" }, ` ${orarioTurno(a.fascia, a.segmento)}`)))
              : "—");
          })));
      }
    }
  }
  return el("div", { class: "guida-tabella" }, el("table", { class: "tabella" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), s.giorni.map((g) => el("th", {}, giorno(g))))),
    el("tbody", {}, righe)));
}

function paginaSettimana() {
  const s = stato.settimana;
  if (!generata(s)) {
    return el("section", { class: "card guida-vuota" },
      el("h2", {}, "Questa settimana non è ancora stata generata"),
      el("p", {}, "Premi il pulsante: il programma ti guida passo passo. Inserisci i turni dei volontari, "
        + "le ferie e malattie e le indisponibilità, poi controlli il riepilogo e generi i turni."),
      el("button", { type: "button", class: "btn btn-primary btn-grande", onclick: () => { stato.passo = 0; disegna(); } },
        "Genera settimana"));
  }
  const confermata = s.stato === "confermata";
  return el("section", {},
    el("div", { class: "guida-stato" },
      el("span", { class: `badge ${confermata ? "badge-confermata" : "badge-bozza"}` }, confermata ? "Confermata" : "Non ancora confermata"),
      confermata ? el("span", { class: "muted" }, "I turni sono definitivi.")
        : el("span", { class: "muted" }, "I turni sono stati preparati ma non ancora confermati.")),
    el("div", { class: "guida-pdf" },
      el("button", { type: "button", class: "btn btn-primary", onclick: () => scaricaPdf("tabellone") }, "Scarica PDF turni"),
      el("button", { type: "button", class: "btn btn-secondary", onclick: () => scaricaPdf("liberi") }, "Scarica PDF liberi")),
    tabellaTurni(s),
    correzione(s));
}

/** Sotto i turni: rifare la settimana dal primo passo, tenendo tutto quello che è già stato inserito. */
function correzione(s) {
  if (s.cambi_attivi) {
    return el("p", { class: "muted guida-correzione" }, "In questa settimana ci sono cambi turno già registrati: "
      + "non si può più rigenerare. Per correggere qualcosa chiedi a chi gestisce il programma.");
  }
  const riprendi = () => { stato.passo = P.servizi; disegna(); };
  if (s.stato !== "confermata") {
    return el("div", { class: "guida-correzione" },
      el("button", { type: "button", class: "btn btn-secondary", onclick: riprendi }, "Riprendi la modifica e rigenera"),
      el("button", { type: "button", class: "btn btn-ghost", onclick: () => esegui(() => api.conferma(s.inizio), "Settimana confermata.") },
        "Conferma i turni così come sono"));
  }
  const rigenera = async () => {
    const ok = await chiediConferma("Torni al primo passo con tutto quello che hai già inserito (servizi, volontari, ferie, "
      + "indisponibilità) e puoi correggere quello che serve. Alla fine la settimana viene generata di nuovo da capo "
      + "e i turni attuali vengono sostituiti.", { titolo: "Rigenerare la settimana?", ok: "Sì, correggi e rigenera" });
    if (!ok) return;
    try {
      stato.settimana = await api.riapri(s.inizio);
      riprendi();
    } catch (err) {
      toastErrore(err);
    }
  };
  return el("div", { class: "guida-correzione" },
    el("button", { type: "button", class: "btn btn-secondary", onclick: rigenera }, "Ho fatto un errore, rigenera la settimana"));
}

// ---------------------------------------------------------------- procedura guidata

function indicatorePassi() {
  return el("ol", { class: "guida-passi", "aria-label": "Passi" }, PASSI.map((p, i) =>
    el("li", { class: i === stato.passo ? "attivo" : i < stato.passo ? "fatto" : null, "aria-current": i === stato.passo ? "step" : null },
      el("span", { class: "guida-numero" }, String(i + 1)), el("span", { class: "guida-nome" }, p))));
}

function pulsantiPasso({ avanti = "Avanti", suAvanti } = {}) {
  return el("div", { class: "guida-azioni" },
    el("button", { type: "button", class: "btn btn-ghost", onclick: () => { stato.passo = stato.passo ? stato.passo - 1 : null; disegna(); } },
      stato.passo ? "‹ Indietro" : "Annulla"),
    el("button", { type: "button", class: "btn btn-primary", onclick: suAvanti || (() => { stato.passo += 1; disegna(); }) }, avanti));
}

function tabella(intestazioni, righe, vuoto) {
  if (!righe.length) return el("p", { class: "muted guida-nessuno" }, vuoto);
  return el("div", { class: "guida-tabella" }, el("table", { class: "tabella" },
    el("thead", {}, el("tr", {}, intestazioni.map((t) => el("th", {}, t)))), el("tbody", {}, righe)));
}

const rimuovi = (testo, azione) => el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: azione }, testo);

function campo(etichettaTesto, controllo) {
  return el("label", { class: "guida-campo" }, el("span", {}, etichettaTesto), controllo);
}

const plurale = (n, uno, tanti) => `${n} ${n === 1 ? uno : tanti}`;
const quantita = (data, postazione, fascia, segmento, ruolo) => {
  const f = (stato.settimana.fabbisogno || []).find((x) => x.data === data && x.postazione === postazione
    && x.fascia === fascia && x.segmento === segmento && x.ruolo === ruolo);
  return f ? Number(f.quantita) || 0 : 0;
};

/** Standby e Programmati richiesti (dal fabbisogno) e Assistenze ed Extra, per il riepilogo. */
function serviziSettimana() {
  const s = stato.settimana;
  const righe = [];
  for (const [postazione, fascia, segmento, testo] of TURNI_RICHIESTA) {
    for (const g of s.giorni) {
      const [a, so] = RUOLI.map((r) => quantita(g, postazione, fascia, segmento, r));
      if (!a && !so) continue;
      const quanti = [a && plurale(a, "autista", "autisti"), so && plurale(so, "soccorritore", "soccorritori")].filter(Boolean).join(" e ");
      righe.push({ tipo: "fabbisogno", data: g, testo, quanti });
    }
  }
  for (const e of s.extra || []) {
    const quanti = [e.autisti && plurale(e.autisti, "autista", "autisti"),
      e.soccorritori && plurale(e.soccorritori, "soccorritore", "soccorritori")].filter(Boolean).join(" e ");
    righe.push({ tipo: "extra", id: e.id, data: e.data, testo: `${e.nome} ${e.inizio}–${e.fine}`, quanti });
  }
  return righe.sort((a, b) => a.data.localeCompare(b.data));
}

function tabellaServizi(righe, conTogli) {
  return tabella(["Giorno", "Servizio", "Personale", ...(conTogli ? [""] : [])], righe.map((r) => el("tr", {},
    el("td", {}, giorno(r.data)), el("td", {}, r.testo), el("td", {}, r.quanti),
    conTogli ? el("td", {}, rimuovi("Togli", () => esegui(() => api.eliminaExtra(r.id), "Tolta."))) : null)),
  conTogli ? "Nessuna assistenza o extra inserita." : "Nessuno.");
}

/** Salva voci del fabbisogno e ridisegna rimettendo il cursore sul controllo appena cambiato. */
async function salvaFabbisogno(voci, idFocus) {
  try {
    stato.settimana = await api.impostaFabbisogno(stato.settimana.inizio, voci);
  } catch (err) {
    toastErrore(err);
  }
  disegna();
  const nodo = idFocus && document.getElementById(idFocus);
  if (nodo) nodo.focus();
}

function intestazioneGiorni(s, primaColonna) {
  return el("thead", {}, el("tr", {}, el("th", { scope: "col" }, primaColonna),
    s.giorni.map((g) => el("th", { scope: "col", class: `disp-cella${indiceGiorno(g) >= 5 ? " weekend" : ""}` }, giorno(g)))));
}

/** Come nel programma completo: una casella per giorno e turno; ogni Standby è un autista e un soccorritore. */
function grigliaStandby(s) {
  const tbody = el("tbody", {}, ["giorno", "notte"].map((fascia) => {
    const turno = orarioTurno(fascia, "standby");
    return el("tr", {}, el("th", { scope: "row" }, turno), s.giorni.map((g) => {
      const richiesto = RUOLI.some((r) => quantita(g, STANDBY, fascia, "standby", r) > 0);
      const id = `guida-standby-${g}-${fascia}`;
      return el("td", { class: `disp-cella${indiceGiorno(g) >= 5 ? " weekend" : ""}` }, el("input", {
        type: "checkbox", id, checked: richiesto, "aria-label": `Standby ${turno} ${giorno(g)}`,
        onchange: (e) => salvaFabbisogno(RUOLI.map((ruolo) => ({ data: g, postazione: STANDBY, fascia, segmento: "standby",
          ruolo, quantita: e.target.checked ? 1 : 0 })), id),
      }));
    }));
  }));
  return el("section", { class: "richieste-blocco" },
    el("h3", {}, "Standby", el("span", { class: "muted" }, " · spunta i turni: ognuno è un autista e un soccorritore")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" }, intestazioneGiorni(s, "Turno"), tbody)));
}

/** Come nel programma completo: per ogni giorno della settimana quanti autisti e soccorritori servono. */
function grigliaProgrammati(s) {
  const righe = [];
  for (const segmento of ["prog_mattina", "prog_pomeriggio"]) {
    RUOLI.forEach((ruolo, idx) => {
      const turno = orarioTurno("giorno", segmento);
      const ruoli = ruolo === "autista" ? "Autisti" : "Soccorritori";
      righe.push(el("tr", { class: idx === 0 ? "inizio-fascia" : null },
        el("th", { scope: "row" }, el("span", { class: "fascia-label" }, turno), " ", el("span", { class: "ruolo-label" }, ruoli)),
        s.giorni.map((g) => {
          const valore = quantita(g, PROGRAMMATI, "giorno", segmento, ruolo);
          const id = `guida-prog-${g}-${segmento}-${ruolo}`;
          return el("td", { class: `disp-cella${indiceGiorno(g) >= 5 ? " weekend" : ""}` }, el("input", {
            type: "number", class: "input-quantita", id, min: "0", max: "20", step: "1", inputmode: "numeric",
            value: String(valore), "aria-label": `Programmati ${turno} ${giorno(g)}: numero di ${ruoli.toLowerCase()}`,
            onchange: (e) => {
              const n = e.target.value.trim() === "" ? 0 : Number(e.target.value);
              if (!Number.isInteger(n) || n < 0 || n > 20) {
                toast("Indica un numero intero da 0 a 20.", "avviso");
                e.target.value = String(valore);
                return;
              }
              salvaFabbisogno([{ data: g, postazione: PROGRAMMATI, fascia: "giorno", segmento, ruolo, quantita: n }], id);
            },
          }));
        })));
    });
  }
  return el("section", { class: "richieste-blocco" },
    el("h3", {}, "Programmati", el("span", { class: "muted" }, " · quante persone servono per turno, giorno per giorno")),
    el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-richieste" }, intestazioneGiorni(s, "Turno"), el("tbody", {}, righe))));
}

function passoServizi() {
  const s = stato.settimana;
  const righe = serviziSettimana();
  const attive = s.postazioni_a_richiesta || [];
  const conStandby = attive.length > 0;
  const titolo = el("h2", {}, "1. Standby, Programmati e Assistenze");
  if (stato.servizi === null && !righe.length) {
    return [titolo,
      el("p", {}, conStandby
        ? "Questa settimana servono Standby, Programmati o Assistenze ed Extra?"
        : "Questa settimana servono Assistenze ed Extra? (Standby e Programmati ci sono solo nelle settimane senza Ascoli.)"),
      el("div", { class: "guida-scelta" },
        el("button", { type: "button", class: "btn btn-secondary btn-grande", onclick: () => { stato.servizi = false; stato.passo = P.volontari; disegna(); } }, "No, nessuno"),
        el("button", { type: "button", class: "btn btn-primary btn-grande", onclick: () => { stato.servizi = true; disegna(); } }, "Sì")),
      el("div", { class: "guida-azioni" },
        el("button", { type: "button", class: "btn btn-ghost", onclick: () => { stato.passo = null; disegna(); } }, "Annulla"))];
  }
  const moduli = [];
  if (attive.includes(STANDBY)) moduli.push(grigliaStandby(s));
  if (attive.includes(PROGRAMMATI)) moduli.push(grigliaProgrammati(s));
  if (!conStandby) moduli.push(el("p", { class: "muted" }, "In questa settimana (con Ascoli) Standby e Programmati non ci sono."));
  const nomeExtra = el("input", { required: true, maxlength: 100, placeholder: "Es. Assistenza partita" });
  const quandoExtra = el("select", {}, s.giorni.map((g) => opzione(g, giorno(g))));
  const ore = (valore) => el("select", {}, Array.from({ length: 24 }, (_, h) => opzione(String(h), `${h}:00`, String(valore))));
  const dalle = ore(9);
  const alle = ore(13);
  const autisti = el("input", { type: "number", min: 0, max: 20, value: 1 });
  const soccorritori = el("input", { type: "number", min: 0, max: 20, value: 1 });
  const aggiungiExtra = (e) => {
    e.preventDefault();
    esegui(() => api.creaExtra(s.inizio, { data: quandoExtra.value, nome: nomeExtra.value.trim(), inizio: Number(dalle.value),
      fine: Number(alle.value), autisti: Number(autisti.value) || 0, soccorritori: Number(soccorritori.value) || 0 }),
    `${nomeExtra.value.trim()} aggiunta.`);
  };
  moduli.push(el("h3", {}, "Assistenze ed Extra"),
    el("form", { class: "card guida-form", onsubmit: aggiungiExtra },
      campo("Nome", nomeExtra), campo("Giorno", quandoExtra), campo("Dalle", dalle), campo("Alle", alle),
      campo("Autisti", autisti), campo("Soccorritori", soccorritori),
      el("button", { type: "submit", class: "btn btn-secondary" }, "Aggiungi")));
  return [titolo,
    el("p", {}, "Indica i servizi richiesti questa settimana: le modifiche si salvano subito. Quando hai finito premi Avanti."),
    ...moduli,
    tabellaServizi(righe.filter((r) => r.tipo === "extra"), true),
    pulsantiPasso()];
}

function passoVolontari() {
  const s = stato.settimana;
  const lista = el("datalist", { id: "guida-volontari" }, volontari().map((p) => el("option", { value: p.nome })));
  const chi = el("input", { list: "guida-volontari", required: true, autocomplete: "off", placeholder: "Nome e cognome" });
  const ruolo = el("select", {}, RUOLI.map((r) => opzione(r, etichetta("ruolo", r))));
  const quando = el("select", {}, s.giorni.map((g) => opzione(g, giorno(g))));
  const dove = el("select", {}, s.postazioni.map((p) => opzione(p, p)));
  const turno = el("select", {}, TURNI_VOLONTARI.map(([f, seg, t]) => opzione(`${f}|${seg}`, t)));
  const aggiungi = (e) => {
    e.preventDefault();
    const testo = chi.value.trim();
    if (!testo) return;
    const esistente = volontari().find((p) => p.nome.toLowerCase() === testo.toLowerCase());
    const [fascia, segmento] = turno.value.split("|");
    esegui(() => api.aggiungiAssegnazione(s.inizio, {
      data: quando.value, postazione: dove.value, fascia, segmento, ruolo: ruolo.value,
      ...(esistente ? { persona_id: esistente.id } : { nome_volontario: testo }),
    }), `Turno di ${testo} aggiunto.`);
  };
  return [
    el("h2", {}, "2. Turni dei volontari"),
    el("p", {}, "Inserisci i turni che coprono i volontari questa settimana. Se non ce ne sono, premi Avanti."),
    el("form", { class: "card guida-form", onsubmit: aggiungi }, lista,
      campo("Volontario", chi), campo("Ruolo", ruolo), campo("Giorno", quando), campo("Postazione", dove), campo("Turno", turno),
      el("button", { type: "submit", class: "btn btn-secondary" }, "Aggiungi")),
    tabella(["Volontario", "Ruolo", "Giorno", "Postazione", "Turno", ""], turniVolontari().map((a) => el("tr", {},
      el("td", {}, a.persona_nome), el("td", {}, etichetta("ruolo", a.ruolo)), el("td", {}, giorno(a.data)),
      el("td", {}, a.postazione), el("td", {}, orarioTurno(a.fascia, a.segmento)),
      el("td", {}, rimuovi("Togli", () => esegui(() => api.eliminaAssegnazione(a.id), "Turno tolto."))))),
    "Nessun turno di volontari inserito."),
    pulsantiPasso(),
  ];
}

function passoFerie() {
  const s = stato.settimana;
  const chi = el("select", { required: true }, opzione("", "Scegli il dipendente"),
    dipendenti().map((p) => opzione(String(p.id), p.nome)));
  const dal = el("input", { type: "date", value: s.inizio, required: true });
  const al = el("input", { type: "date", value: s.fine, required: true });
  const motivo = el("select", {}, opzione("ferie", "Ferie"), opzione("malattia", "Malattia o infortunio"));
  const aggiungi = (e) => {
    e.preventDefault();
    if (!chi.value) return;
    esegui(() => api.creaFerie({ persona_id: Number(chi.value), dal: dal.value, al: al.value, motivo: motivo.value }),
      `${motivo.value === "ferie" ? "Ferie aggiunte" : "Malattia aggiunta"} per ${nome(Number(chi.value))}.`);
  };
  return [
    el("h2", {}, "3. Ferie e malattie"),
    el("p", {}, "Inserisci chi è in ferie o in malattia questa settimana. Se nessuno, premi Avanti."),
    el("form", { class: "card guida-form", onsubmit: aggiungi },
      campo("Dipendente", chi), campo("Dal", dal), campo("Al", al), campo("Motivo", motivo),
      el("button", { type: "submit", class: "btn btn-secondary" }, "Aggiungi")),
    tabella(["Dipendente", "Motivo", "Dal", "Al", ""], ferieSettimana().map((f) => el("tr", {},
      el("td", {}, nome(f.persona_id)), el("td", {}, etichetta("motivoLungo", f.motivo)),
      el("td", {}, annoBreve(f.dal)), el("td", {}, annoBreve(f.al)),
      el("td", {}, rimuovi("Togli", async () => {
        if (await chiediConferma(`Togliere ${f.motivo === "ferie" ? "le ferie" : "la malattia"} di ${nome(f.persona_id)}?`,
          { titolo: "Togliere?", ok: "Togli" })) esegui(() => api.eliminaFerie(f.id), "Tolte.");
      })))),
    "Nessuna ferie o malattia in questa settimana."),
    pulsantiPasso(),
  ];
}

/** Salva le indisponibilità di una persona in un giorno (parti vuote = disponibile), tenendo gli altri giorni. */
function impostaGiorno(personaId, data, parti) {
  const altri = (stato.settimana.indisponibilita || []).filter((i) => i.persona_id === personaId && i.data !== data)
    .map((i) => ({ data: i.data, parte: i.parte }));
  const turni = [...altri, ...PARTI_TURNO.filter((p) => parti.has(p)).map((parte) => ({ data, parte }))];
  return api.impostaIndisponibilita(stato.settimana.inizio, personaId, turni);
}

// i salvataggi delle indisponibilità vanno al server uno alla volta, nell'ordine in cui si fanno
let coda = Promise.resolve();

/** Come nel programma completo: un menu per dipendente e giorno; chi è in ferie o malattia ha il badge. */
function passoIndisponibilita() {
  const s = stato.settimana;
  const persone = dipendenti().slice().sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const assenze = new Map((s.ferie || []).map((x) => [`${x.persona_id}|${x.data}`, x.motivo]));
  const parti = new Map(indisponibilita().map((i) => [`${i.persona_id}|${i.data}`, i.parti]));
  const cambia = (p, g, menu) => {
    const id = menu.id;
    const precedente = menu.dataset.precedente;
    menu.closest("td").classList.toggle("disp-indisponibile", Boolean(menu.value));
    menu.disabled = true;
    const scelte = new Set(menu.value ? menu.value.split("+") : []);
    const salva = coda.then(async () => {
      stato.settimana = await impostaGiorno(p.id, g, scelte);
    });
    coda = salva.catch(() => {});
    salva.then(() => {
      disegna();
      document.getElementById(id)?.focus();
    }, (err) => {
      toastErrore(err);
      menu.value = precedente;
      menu.closest("td").classList.toggle("disp-indisponibile", Boolean(precedente));
      menu.disabled = false;
    });
  };
  const corpo = el("tbody", {}, persone.map((p) => el("tr", {},
    el("th", { scope: "row" }, p.nome),
    s.giorni.map((g) => {
      const classe = `disp-cella${indiceGiorno(g) >= 5 ? " weekend" : ""}`;
      if (assenze.has(`${p.id}|${g}`)) return el("td", { class: classe }, badgeAssenza(assenze.get(`${p.id}|${g}`)));
      const insieme = parti.get(`${p.id}|${g}`) || new Set();
      const valore = PARTI_TURNO.filter((x) => insieme.has(x)).join("+");
      const scelte = SCELTE_INDISPONIBILITA.some(([v]) => v === valore)
        ? SCELTE_INDISPONIBILITA : [...SCELTE_INDISPONIBILITA, [valore, etichettaParti(insieme)]];
      return el("td", { class: `${classe}${valore ? " disp-indisponibile" : ""}` }, el("select", {
        id: `guida-disp-${p.id}-${g}`, "aria-label": `${p.nome} indisponibile ${giorno(g)}`, "data-precedente": valore,
        onchange: (e) => cambia(p, g, e.target),
      }, scelte.map(([v, t]) => opzione(v, t, valore))));
    }))));
  return [
    el("h2", {}, "4. Indisponibilità"),
    el("p", {}, "Per ogni giorno scegli quando un dipendente non può lavorare. Le modifiche si salvano subito. "
      + "La notte è quella che inizia la sera del giorno scelto. Se nessuno ha indisponibilità, premi Avanti."),
    persone.length
      ? el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-disponibilita" },
        intestazioneGiorni(s, "Dipendente"), corpo))
      : el("p", { class: "muted" }, "Nessun dipendente attivo."),
    pulsantiPasso(),
  ];
}

function passoRiepilogo() {
  const vol = turniVolontari();
  const servizi = serviziSettimana();
  const ferie = ferieSettimana();
  const indisp = indisponibilita();
  const sezione = (titolo, n, contenuto, passo) => el("section", { class: "guida-riepilogo" },
    el("div", { class: "guida-riepilogo-testa" }, el("h3", {}, `${titolo} (${n})`),
      el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: () => { stato.passo = passo; disegna(); } }, "Modifica")),
    contenuto);
  const avvia = async () => {
    const ok = await chiediConferma(
      `La generazione dura circa ${Math.round(TEMPO_GENERAZIONE / 60)} minuti. `
      + (generata(stato.settimana) ? "I turni attuali vengono sostituiti da quelli nuovi. " : "")
      + "Al termine la settimana viene confermata. Procedere?", { titolo: "Generare la settimana?", ok: "Genera" });
    if (ok) genera();
  };
  return [
    el("h2", {}, "5. Riepilogo"),
    el("p", {}, "Controlla che sia tutto corretto. Se manca qualcosa premi Modifica nella sezione giusta."),
    sezione("Standby, Programmati e Assistenze", servizi.length, tabellaServizi(servizi, false), P.servizi),
    sezione("Turni dei volontari", vol.length, tabella(["Volontario", "Ruolo", "Giorno", "Postazione", "Turno"], vol.map((a) =>
      el("tr", {}, el("td", {}, a.persona_nome), el("td", {}, etichetta("ruolo", a.ruolo)), el("td", {}, giorno(a.data)),
        el("td", {}, a.postazione), el("td", {}, orarioTurno(a.fascia, a.segmento)))), "Nessuno."), P.volontari),
    sezione("Ferie e malattie", ferie.length, tabella(["Dipendente", "Motivo", "Dal", "Al"], ferie.map((f) =>
      el("tr", {}, el("td", {}, nome(f.persona_id)), el("td", {}, etichetta("motivoLungo", f.motivo)),
        el("td", {}, annoBreve(f.dal)), el("td", {}, annoBreve(f.al)))), "Nessuna."), P.ferie),
    sezione("Indisponibilità", indisp.length, tabella(["Dipendente", "Giorno", "Non disponibile"], indisp.map((i) =>
      el("tr", {}, el("td", {}, nome(i.persona_id)), el("td", {}, giorno(i.data)), el("td", {}, etichettaParti(i.parti)))), "Nessuna."), P.indisponibilita),
    pulsantiPasso({ avanti: "Conferma e genera", suAvanti: avvia }),
  ];
}

function passoGenerazione() {
  const barra = el("progress", { max: TEMPO_GENERAZIONE, value: 0, class: "guida-barra" });
  const resto = el("p", { class: "guida-resto", "aria-live": "polite" }, "");
  const inizio = Date.now();
  const aggiorna = () => {
    if (!barra.isConnected) return;
    const passati = Math.min(TEMPO_GENERAZIONE, (Date.now() - inizio) / 1000);
    barra.value = passati;
    const mancano = Math.max(0, Math.ceil(TEMPO_GENERAZIONE - passati));
    resto.textContent = mancano ? `Ancora circa ${Math.floor(mancano / 60)}:${String(mancano % 60).padStart(2, "0")} minuti.`
      : "Quasi finito…";
    setTimeout(aggiorna, 1000);
  };
  setTimeout(aggiorna, 0);
  return [
    el("h2", {}, "6. Generazione in corso"),
    el("p", {}, "Il programma sta preparando i turni rispettando riposi, ore ed equità. Non chiudere questa pagina."),
    barra, resto,
  ];
}

async function genera() {
  stato.passo = P.generazione;
  stato.generando = true;
  disegna();
  const inizio = stato.settimana.inizio;
  try {
    await api.genera(inizio, TEMPO_GENERAZIONE);
    await api.conferma(inizio);
    stato.passo = null;
    toast("Turni generati e confermati.", "ok");
  } catch (err) {
    stato.passo = P.riepilogo;
    toastErrore(err);
  } finally {
    stato.generando = false;
  }
  try { await carica(); } catch (err) { toastErrore(err); }
  disegna();
}

// ---------------------------------------------------------------- montaggio

function disegna() {
  const r = stato.root;
  if (!r || !stato.settimana) return;
  const contenuto = stato.passo === null ? [paginaSettimana()]
    : [indicatorePassi(), ...[passoServizi, passoVolontari, passoFerie, passoIndisponibilita, passoRiepilogo,
      passoGenerazione][stato.passo]()];
  r.replaceChildren(intestazione(), ...contenuto);
}

export async function mostra(root, parametro) {
  const data = mondayOf(/^\d{4}-\d{2}-\d{2}$/.test(parametro || "") ? parametro : todayISO());
  if (stato.generando) { stato.root = root; disegna(); return; }  // non si cambia settimana durante la generazione
  if (data !== stato.data) Object.assign(stato, { passo: null, servizi: null });
  Object.assign(stato, { root, data });
  root.replaceChildren(el("p", { class: "muted" }, "Caricamento…"));
  try {
    await carica();
  } catch (err) {
    root.replaceChildren(el("p", { role: "alert" }, err.message));
    return;
  }
  disegna();
}
