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
const MAX_NOTE_GIORNO = 200, MAX_NOTE_FINALI = 1000, MAX_CAUSALE = 100;

const sessione = { mese: null, scheda: null, vista: null };
const carte = new Map();       // giorno -> { radice, corpo, errore }
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
  carte.clear();
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
const datiGiorno = (giorno) => sessione.scheda.giorni[giorno - 1];
const orePair = (coppia) => (coppia ? [formatta(coppia[0]), formatta(coppia[1])] : null);

/** Il corpo della richiesta di salvataggio: il giorno com'è adesso, con le sole modifiche indicate. */
function corpoDa(g, modifiche = {}) {
  const d = g.disponibilita;
  return {
    ferie: g.ferie ? 1 : 0,
    colonne: Object.fromEntries(COLONNE.map(([c]) => [c, orePair(g.colonne[c])])),
    note: g.note,
    disponibilita: d ? { inizio: formatta(d.inizio), fine: formatta(d.fine), causale: d.causale } : null,
    ...modifiche,
  };
}

async function dopoErrore(err, carta) {
  if (err.status === 401) return sessioneScaduta();
  if (err.status === 409) { await vistaScheda(sessione.mese); return segnala("La scheda è confermata"); }
  scrivi(carta.errore, err.message);
}

/** Salva un giorno (i salvataggi vanno uno alla volta) e lo ridisegna. Dà true se è andato a buon fine. */
function invia(giorno, modifiche) {
  const carta = carte.get(giorno);
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("PUT", `/${sessione.mese}/giorni/${giorno}`, corpoDa(datiGiorno(giorno), modifiche));
      disegnaGiorno(giorno);
      aggiornaTotali();
      segnala("Salvato");
      return true;
    } catch (err) { await dopoErrore(err, carta); return false; }
  });
  return coda;
}

function ripristina(giorno) {
  const carta = carte.get(giorno);
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("DELETE", `/${sessione.mese}/giorni/${giorno}`);
      for (const g of sessione.scheda.giorni) if (carte.has(g.giorno)) disegnaGiorno(g.giorno);
      aggiornaTotali();
      segnala("Giorno ripristinato dai turni");
    } catch (err) { await dopoErrore(err, carta); }
  });
}

function aggiornaTotali() {
  const t = sessione.scheda.totali;
  totali.replaceChildren(...[["Giorni di ferie", t.giorni_ferie], ["Ore postazioni", t.ore_postazioni],
    ["Ore secondari", t.ore_secondari], ["Totale mese", t.totale_mese], ["Ore disponibilità aggiuntive", t.ore_disponibilita]]
    .map(([nome, valore]) => el("span", {}, `${nome}: `, el("strong", {}, String(valore)))));
}

// ---------------------------------------------------------------- un giorno

const campoOra = (etichetta, valore) => {
  const input = el("input", { type: "text", inputmode: "numeric", autocomplete: "off", maxlength: 5, placeholder: "8:30", value: valore });
  return { input, campo: el("label", { class: "so-ora" }, etichetta, input) };
};

/** Il modulo per scrivere un turno: nuovo (colonna assente, si sceglie il tipo) o da modificare. */
function formTurno(giorno, colonna, chiudi) {
  const g = datiGiorno(giorno), carta = carte.get(giorno);
  const attuale = colonna ? orePair(g.colonne[colonna]) : null;
  const scelta = colonna ? null : el("select", { "aria-label": "Tipo di turno" },
    COLONNE.filter(([c]) => !g.colonne[c]).map(([c, nome]) => el("option", { value: c }, nome)));
  const inizio = campoOra("Inizio", attuale ? attuale[0] : ""), fine = campoOra("Fine", attuale ? attuale[1] : "");
  const salva = el("button", { type: "submit", class: "so-piccolo" }, "Salva");
  return el("form", { class: "so-turno-form", onsubmit: async (e) => {
    e.preventDefault();
    if (!inizio.input.value.trim() || !fine.input.value.trim()) { scrivi(carta.errore, "Scrivi l'ora di inizio e di fine, per esempio 8 oppure 8:30."); return; }
    salva.disabled = true;
    const tipo = colonna || scelta.value;
    const colonne = { ...corpoDa(datiGiorno(giorno)).colonne, [tipo]: [inizio.input.value.trim(), fine.input.value.trim()] };
    if (!await invia(giorno, { colonne })) salva.disabled = false;
  } }, ...(scelta ? [scelta] : []), inizio.campo, fine.campo, salva,
  el("button", { type: "button", class: "so-secondario so-piccolo", onclick: chiudi }, "Annulla"));
}

function voceTurno(giorno, colonna, nome, coppia, bloccata) {
  const li = el("li", { class: "so-turno" });
  const vista = () => li.replaceChildren(
    el("span", { class: "so-turno-nome" }, nome), el("span", { class: "so-turno-ore" }, `${formatta(coppia[0])}–${formatta(coppia[1])}`),
    ...(bloccata ? [] : [
      el("button", { type: "button", class: "so-secondario so-piccolo", "aria-label": `Modifica ${nome}`,
        onclick: () => li.replaceChildren(formTurno(giorno, colonna, vista)) }, "Modifica"),
      el("button", { type: "button", class: "so-secondario so-piccolo", "aria-label": `Elimina ${nome}`,
        onclick: () => invia(giorno, { colonne: { ...corpoDa(datiGiorno(giorno)).colonne, [colonna]: null } }) }, "Elimina")]));
  vista();
  return li;
}

function bloccoAggiungi(giorno) {
  const riquadro = el("div", { class: "so-aggiungi" });
  const bottone = () => riquadro.replaceChildren(el("button", { type: "button", class: "so-secondario so-piccolo",
    onclick: () => riquadro.replaceChildren(formTurno(giorno, null, bottone)) }, "+ Aggiungi turno"));
  bottone();
  return riquadro;
}

/** Nota del giorno e disponibilità aggiuntiva: un solo modulo con un solo pulsante. */
function formExtra(giorno, bloccata) {
  const g = datiGiorno(giorno), d = g.disponibilita, carta = carte.get(giorno);
  const nota = el("input", { type: "text", autocomplete: "off", maxlength: MAX_NOTE_GIORNO, value: g.note, disabled: bloccata });
  const dal = campoOra("Dalle", d ? formatta(d.inizio) : ""), al = campoOra("Alle", d ? formatta(d.fine) : "");
  const motivo = el("input", { type: "text", autocomplete: "off", maxlength: MAX_CAUSALE, value: d ? d.causale : "", disabled: bloccata });
  for (const c of [dal.input, al.input]) c.disabled = bloccata;
  const salva = el("button", { type: "submit", class: "so-secondario so-piccolo" }, "Salva nota e disponibilità");
  return el("form", { class: "so-extra", onsubmit: async (e) => {
    e.preventDefault();
    const disp = [dal.input.value.trim(), al.input.value.trim(), motivo.value.trim()];
    if (disp.some(Boolean) && (!disp[0] || !disp[1])) { scrivi(carta.errore, "Per la disponibilità aggiuntiva scrivi sia da che ora a che ora."); return; }
    salva.disabled = true;
    const ok = await invia(giorno, { note: nota.value.trim(), disponibilita: disp.some(Boolean) ? { inizio: disp[0], fine: disp[1], causale: disp[2] } : null });
    if (!ok) salva.disabled = false;
  } },
  el("label", { class: "so-nota" }, "Nota del giorno", nota),
  el("fieldset", { class: "so-disp" }, el("legend", {}, "Disponibilità aggiuntiva (oltre al turno)"), dal.campo, al.campo,
    el("label", { class: "so-motivo" }, "Motivo", motivo)),
  ...(bloccata ? [] : [salva]));
}

function intestazioneGiorno(g, bloccata) {
  const segni = [];
  if (g.corretto) {
    segni.push(el("span", { class: "so-etichetta so-bozza" }, "Corretto"));
    if (!bloccata) segni.push(el("button", { type: "button", class: "so-secondario so-piccolo", onclick: () => ripristina(g.giorno) }, "Ripristina dai turni"));
  }
  if (g.da_rivedere) segni.push(el("span", { class: "so-etichetta so-bozza", title: "Due turni nella stessa colonna: controlla gli orari e le note" }, "Da rivedere"));
  const ferie = bloccata
    ? (g.ferie ? [el("span", { class: "so-etichetta" }, "Ferie")] : [])
    : [el("button", { type: "button", class: "so-ferie-bottone so-secondario so-piccolo", "aria-pressed": g.ferie ? "true" : "false",
      onclick: () => invia(g.giorno, { ferie: g.ferie ? 0 : 1 }) }, g.ferie ? "Ferie ✓" : "Ferie")];
  return el("div", { class: "so-giorno-testa" }, el("h3", {}, etichettaGiorno(g.giorno)), el("div", { class: "so-segnali" }, ...segni, ...ferie));
}

function disegnaGiorno(giorno) {
  const carta = carte.get(giorno), g = datiGiorno(giorno), bloccata = confermata();
  const turni = COLONNE.filter(([c]) => g.colonne[c]).map(([c, nome]) => voceTurno(giorno, c, nome, g.colonne[c], bloccata));
  const piene = COLONNE.every(([c]) => g.colonne[c]);
  carta.radice.classList.toggle("so-con-ferie", Boolean(g.ferie));
  carta.corpo.replaceChildren(intestazioneGiorno(g, bloccata),
    ...(g.turni_cambiati ? [el("p", { class: "so-avviso" }, "I turni sono cambiati dopo la tua correzione.")] : []),
    turni.length ? el("ul", { class: "so-turni" }, turni) : el("p", { class: "so-tenue so-vuoto" }, g.ferie ? "Giorno di ferie." : "Nessun turno."),
    ...(bloccata || piene ? [] : [bloccoAggiungi(giorno)]), formExtra(giorno, bloccata));
  scrivi(carta.errore, "");
}

function cartaGiorno(giorno) {
  const corpo = el("div"), errore = boxErrore();
  const radice = el("article", { class: `so-giorno${eWeekend(giorno) ? " so-weekend" : ""}` }, corpo, errore);
  carte.set(giorno, { radice, corpo, errore });
  disegnaGiorno(giorno);
  return radice;
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
  carte.clear();
  const s = sessione.scheda, bloccata = confermata();
  const erroreNote = boxErrore();
  const note = el("textarea", { id: "so-note", rows: 4, maxlength: MAX_NOTE_FINALI, disabled: bloccata, value: s.note,
    onchange: () => {
      coda = coda.then(async () => {
        try { sessione.scheda = await chiama("PUT", `/${sessione.mese}/note`, { note: note.value }); scrivi(erroreNote, ""); segnala("Salvato"); }
        catch (err) { if (err.status === 401) return sessioneScaduta(); scrivi(erroreNote, err.message); }
      });
    } });
  totali = el("div", { class: "so-totali", role: "group", "aria-label": "Totali del mese" });
  mostra("scheda",
    el("div", { class: "so-testa-scheda" },
      el("h2", {}, `${nomeMese(sessione.mese)} · ${s.persona.nome} `, el("span", { class: `so-etichetta so-${s.stato}` }, bloccata ? "Confermata" : "In revisione")),
      el("div", { class: "so-azioni" },
        el("button", { type: "button", class: "so-secondario", onclick: () => vistaMesi() }, "‹ Mesi"),
        el("button", { type: "button", class: "so-secondario", onclick: esci }, "Esci"))),
    bloccata
      ? el("p", { class: "so-ok" }, `Scheda confermata il ${new Date(s.confermata_il).toLocaleString("it-IT")}. Puoi scaricarla in Excel.`)
      : el("p", { class: "so-tenue" }, "I turni sono già compilati dal programma. Controlla ogni giorno: se un orario non è giusto premi Modifica, se manca un turno premi «+ Aggiungi turno», se eri in ferie premi Ferie. Gli orari si scrivono come 8 oppure 8:30. Quando hai finito premi «Ho finito la revisione» in fondo."),
    el("div", { class: "so-giorni" }, s.giorni.map((g) => cartaGiorno(g.giorno))),
    el("h3", {}, el("label", { for: "so-note" }, "Note finali")), note, erroreNote,
    el("div", { class: "so-azioni" }, bloccata
      ? el("a", { class: "so-pulsante", href: `/api/schede-ore/${sessione.mese}.xlsx`, download: "" }, "Scarica Excel")
      : el("button", { type: "button", onclick: conferma }, "Ho finito la revisione")),
    totali);
  aggiornaTotali();
}

vistaMesi().catch((err) => { root.replaceChildren(el("p", { class: "so-errore", role: "alert" }, err.message)); });
