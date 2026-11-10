// Vista "Turni della settimana": procedura guidata per chi non usa il programma completo.
// Mostra la settimana; se non è ancora generata guida passo passo: volontari, ferie e malattie, indisponibilità,
// riepilogo, generazione (con conferma automatica). Poi i turni si vedono e si scaricano in PDF.

import { api } from "./api.js";
import {
  el, toast, toastErrore, chiediConferma, addDays, mondayOf, todayISO, ddmm, parseISO, GIORNI_BREVI, indiceGiorno,
  etichetta, orarioTurno, PARTI_TURNO, SCELTE_INDISPONIBILITA, etichettaParti,
} from "./util.js";

const TEMPO_GENERAZIONE = 180;  // secondi
const PASSI = ["Volontari", "Ferie e malattie", "Indisponibilità", "Riepilogo", "Generazione"];
const RUOLI = ["autista", "soccorritore"];
// turni che un volontario può coprire: [fascia, segmento, etichetta]
const TURNI_VOLONTARI = [
  ["giorno", "intero", "Giorno 8–20"], ["giorno", "mattina", "Mattina 8–14"],
  ["giorno", "pomeriggio", "Pomeriggio 14–20"], ["notte", "intero", "Notte 20–8"],
];

const stato = { root: null, data: null, settimana: null, persone: [], ferie: [], passo: null, generando: false };

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
      confermata ? el("span", { class: "muted" }, "I turni sono definitivi e non si possono modificare da qui.")
        : el("span", { class: "muted" }, "I turni sono stati preparati ma non ancora confermati.")),
    el("div", { class: "guida-pdf" },
      el("button", { type: "button", class: "btn btn-primary", onclick: () => scaricaPdf("tabellone") }, "Scarica PDF turni"),
      el("button", { type: "button", class: "btn btn-secondary", onclick: () => scaricaPdf("liberi") }, "Scarica PDF liberi")),
    tabellaTurni(s));
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
    el("h2", {}, "1. Turni dei volontari"),
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
    el("h2", {}, "2. Ferie e malattie"),
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

function passoIndisponibilita() {
  const s = stato.settimana;
  const chi = el("select", { required: true }, opzione("", "Scegli il dipendente"),
    dipendenti().map((p) => opzione(String(p.id), p.nome)));
  const quando = el("select", {}, s.giorni.map((g) => opzione(g, giorno(g))));
  const parti = el("select", {}, SCELTE_INDISPONIBILITA.filter(([v]) => v).map(([v, t]) => opzione(v, t)));
  const aggiungi = (e) => {
    e.preventDefault();
    if (!chi.value) return;
    const id = Number(chi.value);
    esegui(() => impostaGiorno(id, quando.value, new Set(parti.value.split("+"))), `Indisponibilità di ${nome(id)} salvata.`);
  };
  return [
    el("h2", {}, "3. Indisponibilità"),
    el("p", {}, "Inserisci chi non può lavorare in un giorno o in una parte del giorno. Se nessuno, premi Avanti."),
    el("form", { class: "card guida-form", onsubmit: aggiungi },
      campo("Dipendente", chi), campo("Giorno", quando), campo("Non disponibile", parti),
      el("button", { type: "submit", class: "btn btn-secondary" }, "Aggiungi")),
    tabella(["Dipendente", "Giorno", "Non disponibile", ""], indisponibilita().map((i) => el("tr", {},
      el("td", {}, nome(i.persona_id)), el("td", {}, giorno(i.data)), el("td", {}, etichettaParti(i.parti)),
      el("td", {}, rimuovi("Togli", () => esegui(() => impostaGiorno(i.persona_id, i.data, new Set()), "Indisponibilità tolta."))))),
    "Nessuna indisponibilità inserita."),
    pulsantiPasso(),
  ];
}

function passoRiepilogo() {
  const vol = turniVolontari();
  const ferie = ferieSettimana();
  const indisp = indisponibilita();
  const sezione = (titolo, n, contenuto, passo) => el("section", { class: "guida-riepilogo" },
    el("div", { class: "guida-riepilogo-testa" }, el("h3", {}, `${titolo} (${n})`),
      el("button", { type: "button", class: "btn btn-ghost btn-small", onclick: () => { stato.passo = passo; disegna(); } }, "Modifica")),
    contenuto);
  const avvia = async () => {
    const ok = await chiediConferma(
      `La generazione dura circa ${Math.round(TEMPO_GENERAZIONE / 60)} minuti. Al termine la settimana viene confermata `
      + "e i turni non si potranno più modificare da qui. Procedere?", { titolo: "Generare la settimana?", ok: "Genera" });
    if (ok) genera();
  };
  return [
    el("h2", {}, "4. Riepilogo"),
    el("p", {}, "Controlla che sia tutto corretto. Se manca qualcosa premi Modifica nella sezione giusta."),
    sezione("Turni dei volontari", vol.length, tabella(["Volontario", "Ruolo", "Giorno", "Postazione", "Turno"], vol.map((a) =>
      el("tr", {}, el("td", {}, a.persona_nome), el("td", {}, etichetta("ruolo", a.ruolo)), el("td", {}, giorno(a.data)),
        el("td", {}, a.postazione), el("td", {}, orarioTurno(a.fascia, a.segmento)))), "Nessuno."), 0),
    sezione("Ferie e malattie", ferie.length, tabella(["Dipendente", "Motivo", "Dal", "Al"], ferie.map((f) =>
      el("tr", {}, el("td", {}, nome(f.persona_id)), el("td", {}, etichetta("motivoLungo", f.motivo)),
        el("td", {}, annoBreve(f.dal)), el("td", {}, annoBreve(f.al)))), "Nessuna."), 1),
    sezione("Indisponibilità", indisp.length, tabella(["Dipendente", "Giorno", "Non disponibile"], indisp.map((i) =>
      el("tr", {}, el("td", {}, nome(i.persona_id)), el("td", {}, giorno(i.data)), el("td", {}, etichettaParti(i.parti)))), "Nessuna."), 2),
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
    el("h2", {}, "5. Generazione in corso"),
    el("p", {}, "Il programma sta preparando i turni rispettando riposi, ore ed equità. Non chiudere questa pagina."),
    barra, resto,
  ];
}

async function genera() {
  stato.passo = 4;
  stato.generando = true;
  disegna();
  const inizio = stato.settimana.inizio;
  try {
    await api.genera(inizio, TEMPO_GENERAZIONE);
    await api.conferma(inizio);
    stato.passo = null;
    toast("Turni generati e confermati.", "ok");
  } catch (err) {
    stato.passo = 3;
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
    : [indicatorePassi(), ...[passoVolontari, passoFerie, passoIndisponibilita, passoRiepilogo, passoGenerazione][stato.passo]()];
  r.replaceChildren(intestazione(), ...contenuto);
}

export async function mostra(root, parametro) {
  const data = mondayOf(/^\d{4}-\d{2}-\d{2}$/.test(parametro || "") ? parametro : todayISO());
  if (stato.generando) { stato.root = root; disegna(); return; }  // non si cambia settimana durante la generazione
  if (data !== stato.data) stato.passo = null;
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
