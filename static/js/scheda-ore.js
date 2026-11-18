// Scheda ore mensile del dipendente: accesso con nome e codice, revisione dei giorni, note finali, conferma e
// download. Le API sono sotto /api/schede-ore (cvap/api_schede_ore.py): la persona è quella del cookie di sessione.
import { el } from "./util.js";

const root = document.getElementById("so-app");
const messaggioStato = document.getElementById("so-stato");
const MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre",
  "Novembre", "Dicembre"];
const GIORNI = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
const COLONNE = [["ascoli", "Ascoli"], ["acquasanta", "Acquasanta"], ["venarotta", "Venarotta"],
  ["programmati", "Programmati"], ["assistenze", "Assistenze"], ["viaggi_ast", "Viaggi Ast"], ["viaggi", "Viaggi"]];
const STATI_MESE = { non_aperta: "Non ancora aperta", bozza: "In revisione", confermata: "Confermata" };
const STRETTO = window.matchMedia("(max-width: 760px)");
const MAX_NOTE_GIORNO = 200, MAX_NOTE_FINALI = 1000, MAX_CAUSALE = 100;

const sessione = { mese: null, scheda: null, vista: null };
const righe = new Map();       // giorno -> { campi, segnali, errore, riassunto }
let totali = null;
let coda = Promise.resolve();  // i salvataggi vanno al server uno alla volta, nell'ordine in cui si fanno
let timerStato = 0;

// ---------------------------------------------------------------- utilità

const nomeMese = (mese) => `${MESI[Number(mese.slice(5)) - 1]} ${mese.slice(0, 4)}`;

function formatta(ore) {
  let intere = Math.floor(ore), minuti = Math.round((ore - intere) * 60);
  if (minuti === 60) { intere += 1; minuti = 0; }
  return minuti ? `${intere}:${String(minuti).padStart(2, "0")}` : String(intere);
}

function giornoSettimana(giorno) {
  const [anno, mese] = sessione.mese.split("-").map(Number);
  return new Date(Date.UTC(anno, mese - 1, giorno)).getUTCDay();
}
const eWeekend = (giorno) => [0, 6].includes(giornoSettimana(giorno));
const etichettaGiorno = (giorno) => `${GIORNI[giornoSettimana(giorno)]} ${giorno}`;

function testoErrore(dati, codice) {
  const dettaglio = dati && dati.detail;
  if (Array.isArray(dettaglio)) return dettaglio.map((d) => d.msg || String(d)).join("; ");
  return typeof dettaglio === "string" ? dettaglio : `Errore del programma (${codice}). Riprova.`;
}

async function chiama(metodo, percorso, corpo) {
  let risposta;
  try {
    risposta = await fetch(`/api/schede-ore${percorso}`, {
      method: metodo, credentials: "same-origin", cache: "no-store",
      headers: corpo === undefined ? {} : { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    throw Object.assign(new Error("Non riesco a raggiungere il programma: controlla la connessione e riprova."), { status: 0 });
  }
  if (risposta.status === 204) return null;
  let dati = null;
  try { dati = await risposta.json(); } catch { /* risposta senza corpo */ }
  if (!risposta.ok) throw Object.assign(new Error(testoErrore(dati, risposta.status)), { status: risposta.status });
  return dati;
}

function segnala(testo) {
  messaggioStato.textContent = testo;
  clearTimeout(timerStato);
  timerStato = setTimeout(() => { messaggioStato.textContent = ""; }, 2000);
}

function mostra(vista, ...figli) {
  sessione.vista = vista;
  root.replaceChildren(...figli);
  root.focus();
}

const boxErrore = () => el("p", { class: "so-errore", role: "alert", tabindex: -1, hidden: true });
function scrivi(box, testo) { box.hidden = !testo; box.textContent = testo || ""; if (testo) box.focus(); }

// ---------------------------------------------------------------- accesso

async function vistaAccesso(messaggio = "") {
  righe.clear();
  const errore = boxErrore();
  const nome = el("select", { id: "so-nome", required: true });
  const codice = el("input", { id: "so-codice", type: "password", autocomplete: "off", required: true, maxlength: 100 });
  const entra = el("button", { type: "submit" }, "Entra");
  const form = el("form", { class: "so-stretto", onsubmit: async (e) => {
    e.preventDefault();
    if (!nome.value) { scrivi(errore, "Scegli il tuo nome."); return; }
    entra.disabled = true;
    try {
      await chiama("POST", "/accesso", { persona_id: Number(nome.value), codice: codice.value });
      await vistaMesi();
    } catch (err) {
      codice.value = "";
      scrivi(errore, err.message);
      entra.disabled = false;
    }
  } },
  el("label", { class: "so-campo", for: "so-nome" }, el("span", {}, "Il tuo nome"), nome),
  el("label", { class: "so-campo", for: "so-codice" }, el("span", {}, "Il tuo codice personale"), codice),
  el("div", { class: "so-azioni" }, entra), errore);
  mostra("accesso", el("h2", {}, "Apri la tua scheda"),
    el("p", { class: "so-tenue so-stretto" }, "Scegli il tuo nome e scrivi il codice che ti hanno dato i responsabili."), form);
  try {
    const dipendenti = await chiama("GET", "/dipendenti");
    nome.append(el("option", { value: "" }, "Scegli il tuo nome"), ...dipendenti.map((d) => el("option", { value: d.id }, d.nome)));
    if (!dipendenti.length) scrivi(errore, "Non ci sono dipendenti attivi.");
  } catch (err) { scrivi(errore, err.message); }
  if (messaggio) scrivi(errore, messaggio);
}

async function esci() {
  try { await chiama("POST", "/uscita"); } catch { /* il cookie scade da solo */ }
  await vistaAccesso();
}

function sessioneScaduta() { return vistaAccesso("La sessione è scaduta: rientra con il tuo codice."); }

// ---------------------------------------------------------------- mesi

async function vistaMesi(messaggio = "") {
  let mesi;
  try { mesi = await chiama("GET", "/mesi"); } catch (err) {
    if (err.status === 401) return vistaAccesso();
    throw err;
  }
  const errore = boxErrore();
  mostra("mesi",
    el("div", { class: "so-testa-scheda" }, el("h2", {}, "Scegli il mese"),
      el("button", { type: "button", class: "so-secondario", onclick: esci }, "Esci")),
    el("p", { class: "so-tenue" }, "Il mese in corso e i dodici precedenti. Le schede si compilano dai tuoi turni: tu controlli e correggi."),
    el("ul", { class: "so-mesi" }, mesi.map((m) => el("li", {}, el("button", { type: "button", onclick: () => vistaScheda(m.mese) },
      el("span", {}, nomeMese(m.mese)),
      el("span", { class: `so-etichetta so-${m.stato}` }, STATI_MESE[m.stato] || m.stato))))),
    errore);
  scrivi(errore, messaggio);
}

// ---------------------------------------------------------------- scheda

async function vistaScheda(mese) {
  try { sessione.scheda = await chiama("GET", `/${mese}`); sessione.mese = mese; } catch (err) {
    if (err.status === 401) return sessioneScaduta();
    return vistaMesi(err.message);
  }
  disegnaScheda();
}

const confermata = () => sessione.scheda.stato === "confermata";

function riassunto(g) {
  const parti = COLONNE.filter(([c]) => g.colonne[c]).map(([c, nome]) => `${nome} ${formatta(g.colonne[c][0])}–${formatta(g.colonne[c][1])}`);
  if (g.ferie) parti.unshift("Ferie");
  return parti.length ? parti.join(" · ") : "—";
}

function creaCampi(g, bloccata) {
  const base = { type: "text", autocomplete: "off", disabled: bloccata };
  const orario = (valore, aria) => el("input", { ...base, class: "so-orario", maxlength: 5,
    value: valore == null ? "" : formatta(valore), "aria-label": `${aria}, ${etichettaGiorno(g.giorno)}`, onchange: () => salva(g.giorno) });
  const campi = {
    ferie: el("input", { type: "checkbox", checked: Boolean(g.ferie), disabled: bloccata,
      "aria-label": `Ferie, ${etichettaGiorno(g.giorno)}`, onchange: () => salva(g.giorno) }),
    colonne: {},
    note: el("input", { ...base, class: "so-nota", maxlength: MAX_NOTE_GIORNO, value: g.note,
      "aria-label": `Note, ${etichettaGiorno(g.giorno)}`, onchange: () => salva(g.giorno) }),
    dispInizio: orario(g.disponibilita && g.disponibilita.inizio, "Disponibilità aggiuntive, inizio"),
    dispFine: orario(g.disponibilita && g.disponibilita.fine, "Disponibilità aggiuntive, fine"),
    causale: el("input", { ...base, class: "so-causale", maxlength: MAX_CAUSALE, value: g.disponibilita ? g.disponibilita.causale : "",
      "aria-label": `Causale, ${etichettaGiorno(g.giorno)}`, onchange: () => salva(g.giorno) }),
  };
  for (const [colonna, nome] of COLONNE) {
    const coppia = g.colonne[colonna];
    campi.colonne[colonna] = [orario(coppia && coppia[0], `${nome}, inizio`), orario(coppia && coppia[1], `${nome}, fine`)];
  }
  return campi;
}

function tuttiICampi(campi) {
  return [campi.ferie, ...Object.values(campi.colonne).flat(), campi.note, campi.dispInizio, campi.dispFine, campi.causale];
}

function riempi(campi, g) {
  const imposta = (campo, valore) => { if (campo !== document.activeElement) campo.value = valore; };
  campi.ferie.checked = Boolean(g.ferie);
  for (const [colonna] of COLONNE) {
    const coppia = g.colonne[colonna];
    imposta(campi.colonne[colonna][0], coppia ? formatta(coppia[0]) : "");
    imposta(campi.colonne[colonna][1], coppia ? formatta(coppia[1]) : "");
  }
  imposta(campi.note, g.note);
  imposta(campi.dispInizio, g.disponibilita ? formatta(g.disponibilita.inizio) : "");
  imposta(campi.dispFine, g.disponibilita ? formatta(g.disponibilita.fine) : "");
  imposta(campi.causale, g.disponibilita ? g.disponibilita.causale : "");
}

function raccogli(campi) {
  const coppia = ([a, b]) => (a.value.trim() || b.value.trim() ? [a.value.trim(), b.value.trim()] : null);
  const colonne = Object.fromEntries(COLONNE.map(([c]) => [c, coppia(campi.colonne[c])]));
  const disp = [campi.dispInizio.value.trim(), campi.dispFine.value.trim(), campi.causale.value.trim()];
  return { ferie: campi.ferie.checked ? 1 : 0, colonne, note: campi.note.value.trim(),
    disponibilita: disp.some(Boolean) ? { inizio: disp[0], fine: disp[1], causale: disp[2] } : null };
}

function disegnaSegnali(r, g) {
  const figli = [];
  if (g.corretto) {
    figli.push(el("span", { class: "so-etichetta so-bozza" }, "Corretto"));
    if (!confermata()) figli.push(el("button", { type: "button", class: "so-secondario so-piccolo", onclick: () => ripristina(g.giorno) }, "Ripristina dai turni"));
  }
  if (g.da_rivedere) figli.push(el("span", { class: "so-etichetta so-bozza", title: "Due turni nella stessa colonna: controlla gli orari e le note" }, "Da rivedere"));
  if (g.turni_cambiati) figli.push(el("span", { class: "so-avviso" }, "I turni sono cambiati dopo la tua correzione"));
  r.segnali.replaceChildren(...figli);
  if (r.riassunto) r.riassunto.textContent = riassunto(g);
}

function aggiornaGiorno(giorno) {
  const r = righe.get(giorno), g = sessione.scheda.giorni[giorno - 1];
  riempi(r.campi, g);
  disegnaSegnali(r, g);
  tuttiICampi(r.campi).forEach((c) => c.removeAttribute("aria-invalid"));
  scrivi(r.errore, "");
}

function aggiornaTotali() {
  const t = sessione.scheda.totali;
  totali.replaceChildren(...[["Giorni di ferie", t.giorni_ferie], ["Ore postazioni", t.ore_postazioni],
    ["Ore secondari", t.ore_secondari], ["Totale mese", t.totale_mese], ["Ore disponibilità aggiuntive", t.ore_disponibilita]]
    .map(([nome, valore]) => el("span", {}, `${nome}: `, el("strong", {}, String(valore)))));
}

async function dopoErrore(err, r) {
  if (err.status === 401) return sessioneScaduta();
  if (err.status === 409) { await vistaScheda(sessione.mese); return segnala("La scheda è confermata"); }
  scrivi(r.errore, err.message);
  tuttiICampi(r.campi).forEach((c) => c.setAttribute("aria-invalid", "true"));
}

function salva(giorno) {
  const r = righe.get(giorno), corpo = raccogli(r.campi);
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("PUT", `/${sessione.mese}/giorni/${giorno}`, corpo);
      aggiornaGiorno(giorno);
      aggiornaTotali();
      segnala("Salvato");
    } catch (err) { await dopoErrore(err, r); }
  });
}

function ripristina(giorno) {
  const r = righe.get(giorno);
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("DELETE", `/${sessione.mese}/giorni/${giorno}`);
      for (const g of sessione.scheda.giorni) if (righe.has(g.giorno)) aggiornaGiorno(g.giorno);
      aggiornaTotali();
      segnala("Giorno ripristinato dai turni");
    } catch (err) { await dopoErrore(err, r); }
  });
}

function rigaTabella(g, bloccata) {
  const campi = creaCampi(g, bloccata), segnali = el("div", { class: "so-segnali" }), errore = el("p", { class: "so-riga-errore", role: "alert", hidden: true });
  righe.set(g.giorno, { campi, segnali, errore });
  const celle = COLONNE.flatMap(([c]) => campi.colonne[c].map((i) => el("td", {}, i)));
  const tr = el("tr", { class: eWeekend(g.giorno) ? "so-weekend" : "" },
    el("th", { scope: "row" }, etichettaGiorno(g.giorno), segnali, errore), el("td", {}, campi.ferie), ...celle,
    el("td", {}, campi.note), el("td", {}, campi.dispInizio), el("td", {}, campi.dispFine), el("td", {}, campi.causale));
  disegnaSegnali(righe.get(g.giorno), g);
  return tr;
}

function cartaGiorno(g, bloccata) {
  const campi = creaCampi(g, bloccata), segnali = el("div", { class: "so-segnali" }), errore = el("p", { class: "so-riga-errore", role: "alert", hidden: true });
  const sintesi = el("span", { class: "so-tenue" });
  righe.set(g.giorno, { campi, segnali, errore, riassunto: sintesi });
  const coppia = (nome, [a, b]) => el("div", { class: "so-intero so-coppia" }, el("strong", {}, nome),
    el("label", {}, "Inizio", a), el("label", {}, "Fine", b));
  const carta = el("details", { class: `so-giorno${eWeekend(g.giorno) ? " so-weekend" : ""}` },
    el("summary", {}, el("strong", {}, etichettaGiorno(g.giorno)), sintesi),
    el("div", { class: "so-giorno-campi" },
      el("label", { class: "so-intero" }, campi.ferie, " Ferie"),
      ...COLONNE.map(([c, nome]) => coppia(nome, campi.colonne[c])),
      el("label", { class: "so-intero" }, "Note", campi.note),
      coppia("Disponibilità aggiuntive", [campi.dispInizio, campi.dispFine]),
      el("label", { class: "so-intero" }, "Causale", campi.causale), segnali, errore));
  disegnaSegnali(righe.get(g.giorno), g);
  return carta;
}

function intestazione() {
  const gruppi = COLONNE.map(([, nome]) => el("th", { scope: "colgroup", colspan: 2 }, nome));
  const inizioFine = COLONNE.flatMap(() => [el("th", { scope: "col" }, "Inizio"), el("th", { scope: "col" }, "Fine")]);
  return el("thead", {},
    el("tr", {}, el("th", { rowspan: 2, scope: "col" }, "Giorno"), el("th", { rowspan: 2, scope: "col" }, "Ferie"), ...gruppi,
      el("th", { rowspan: 2, scope: "col" }, "Note"), el("th", { colspan: 3, scope: "colgroup" }, "Disponibilità aggiuntive")),
    el("tr", {}, ...inizioFine, el("th", { scope: "col" }, "Inizio"), el("th", { scope: "col" }, "Fine"), el("th", { scope: "col" }, "Causale")));
}

function chiediConferma() {
  return new Promise((risolvi) => {
    let esito = false;
    const d = el("dialog", { class: "so-dialogo", "aria-labelledby": "so-conferma-titolo" });
    const annulla = el("button", { type: "button", class: "so-secondario", onclick: () => d.close() }, "Annulla");
    d.append(el("h2", { id: "so-conferma-titolo" }, "Confermi la scheda?"),
      el("p", {}, "Dopo la conferma non potrai più modificarla. Per riaprirla dovrai chiedere ai responsabili."),
      el("div", { class: "so-azioni" }, annulla, el("button", { type: "button", onclick: () => { esito = true; d.close(); } }, "Conferma la scheda")));
    d.addEventListener("close", () => { d.remove(); risolvi(esito); }, { once: true });
    document.body.append(d);
    d.showModal();
    annulla.focus();
  });
}

async function conferma() {
  if (!await chiediConferma()) return;
  await coda;  // i salvataggi in corso finiscono prima di congelare la scheda
  try {
    sessione.scheda = await chiama("POST", `/${sessione.mese}/conferma`);
    disegnaScheda();
    segnala("Scheda confermata");
  } catch (err) {
    if (err.status === 401) return sessioneScaduta();
    segnala(err.message);
  }
}

function disegnaScheda() {
  righe.clear();
  const s = sessione.scheda, bloccata = confermata();
  const erroreNote = boxErrore();
  const note = el("textarea", { id: "so-note", rows: 4, maxlength: MAX_NOTE_FINALI, disabled: bloccata, value: s.note,
    onchange: () => {
      coda = coda.then(async () => {
        try { sessione.scheda = await chiama("PUT", `/${sessione.mese}/note`, { note: note.value }); scrivi(erroreNote, ""); segnala("Salvato"); }
        catch (err) { if (err.status === 401) return sessioneScaduta(); scrivi(erroreNote, err.message); }
      });
    } });
  const giorni = s.giorni;
  const corpo = STRETTO.matches
    ? el("div", { class: "so-giorni" }, giorni.map((g) => cartaGiorno(g, bloccata)))
    : el("div", { class: "so-scorri" }, el("table", { class: "so-tabella" },
      el("caption", { class: "sr-only" }, `Scheda ore di ${nomeMese(sessione.mese)}`), intestazione(),
      el("tbody", {}, giorni.map((g) => rigaTabella(g, bloccata)))));
  totali = el("div", { class: "so-totali", role: "group", "aria-label": "Totali del mese" });
  mostra("scheda",
    el("div", { class: "so-testa-scheda" },
      el("h2", {}, `${nomeMese(sessione.mese)} · ${s.persona.nome} `, el("span", { class: `so-etichetta so-${s.stato}` }, bloccata ? "Confermata" : "In revisione")),
      el("div", { class: "so-azioni" },
        el("button", { type: "button", class: "so-secondario", onclick: () => vistaMesi() }, "‹ Mesi"),
        el("button", { type: "button", class: "so-secondario", onclick: esci }, "Esci"))),
    bloccata
      ? el("p", { class: "so-ok" }, `Scheda confermata il ${new Date(s.confermata_il).toLocaleString("it-IT")}. Puoi scaricarla in Excel.`)
      : el("p", { class: "so-tenue" }, "I turni sono compilati dal programma. Correggi dove serve (le modifiche si salvano da sole) e, quando hai finito, premi «Ho finito la revisione». Scrivi gli orari come 8 oppure 8:30."),
    corpo,
    el("h3", {}, el("label", { for: "so-note" }, "Note finali")), note, erroreNote,
    el("div", { class: "so-azioni" }, bloccata
      ? el("a", { class: "so-pulsante", href: `/api/schede-ore/${sessione.mese}.xlsx`, download: "" }, "Scarica Excel")
      : el("button", { type: "button", onclick: conferma }, "Ho finito la revisione")),
    totali);
  aggiornaTotali();
}

STRETTO.addEventListener("change", () => { if (sessione.vista === "scheda") disegnaScheda(); });

vistaMesi().catch((err) => { root.replaceChildren(el("p", { class: "so-errore", role: "alert" }, err.message)); });
