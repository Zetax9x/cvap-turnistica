// Scheda ore mensile del dipendente: accesso con nome e codice, revisione dei giorni, note finali, conferma e
// download. Le API sono sotto /api/schede-ore (cvap/api_schede_ore.py): la persona è quella del cookie di sessione.
import { el } from "./util.js";

const root = document.getElementById("so-app");
const messaggioStato = document.getElementById("so-stato");
const MESI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre",
  "Novembre", "Dicembre"];
const COLONNE = [["ascoli", "Ascoli"], ["acquasanta", "Acquasanta"], ["venarotta", "Venarotta"],
  ["programmati", "Programmati"], ["assistenze", "Assistenze"], ["viaggi_ast", "Viaggi Ast"], ["viaggi", "Viaggi"]];
const STATI_MESE = { non_aperta: "Non ancora aperta", bozza: "In revisione", confermata: "Confermata" };
const MAX_NOTE_GIORNO = 200, MAX_NOTE_FINALI = 1000, MAX_CAUSALE = 100;

const sessione = { mese: null, scheda: null, vista: null, giorno: null, visto: 1 };  // giorno: numero o "riepilogo"
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
const NOMI_GIORNO = ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"];
const LETTERE = ["D", "L", "M", "M", "G", "V", "S"];
const titoloGiorno = (g) => `${NOMI_GIORNO[giornoSettimana(g)]} ${g} ${MESI[Number(sessione.mese.slice(5)) - 1].toLowerCase()}`;

// ---------------------------------------------------------------- giorni controllati (solo in questo browser)

let controllati = new Set();
const chiaveControlli = () => `cvap-scheda-${sessione.scheda.persona.id ?? sessione.scheda.persona.nome}-${sessione.mese}`;

function leggiControllati() {
  try { return new Set(JSON.parse(localStorage.getItem(chiaveControlli()) || "[]")); } catch { return new Set(); }
}
function salvaControllati() {
  try { localStorage.setItem(chiaveControlli(), JSON.stringify([...controllati])); } catch { /* memoria del browser non disponibile */ }
}
const eControllato = (g) => controllati.has(g.giorno) || Boolean(g.corretto);
const daRivedere = (g) => Boolean(g.da_rivedere || g.turni_cambiati);

// ---------------------------------------------------------------- note dei turni
// Il programma salva una sola nota per giorno: le note dei turni ci stanno dentro come «Ascoli: testo», separate da «; ».
// Le altre voci (Malattia, Standby, nomi delle assistenze...) le scrive il programma e restano com'sono.

const SEPARATORE_NOTE = "; ";
const prefissoNota = (nome) => `${nome}: `;

function leggiNote(note) {
  const turni = {}, altre = [];
  for (const parte of note.split(SEPARATORE_NOTE).map((p) => p.trim()).filter(Boolean)) {
    const colonna = COLONNE.find(([, nome]) => parte.startsWith(prefissoNota(nome)));
    if (colonna) turni[colonna[0]] = parte.slice(prefissoNota(colonna[1]).length); else altre.push(parte);
  }
  return { turni, altre };
}

// Un turno extra (oltre a quelli che escono il venerdì) si segna con la parola «Extra» all'inizio della nota del turno.
const MARCA_EXTRA = "Extra";
function separaExtra(nota) {
  if (nota === MARCA_EXTRA) return { extra: true, testo: "" };
  if (nota.startsWith(`${MARCA_EXTRA} - `)) return { extra: true, testo: nota.slice(MARCA_EXTRA.length + 3) };
  return { extra: false, testo: nota };
}
function uniscExtra(extra, testo) {
  const pulito = testo.trim();
  return extra ? (pulito ? `${MARCA_EXTRA} - ${pulito}` : MARCA_EXTRA) : pulito;
}

/** La nota del giorno riscritta con la nota di un solo turno cambiata (testo vuoto = nota tolta). */
function componiNote(note, colonna, testo) {
  const { turni, altre } = leggiNote(note);
  const pulito = (testo || "").replace(/;/g, ",").trim();
  if (pulito) turni[colonna] = pulito; else delete turni[colonna];
  return [...altre, ...COLONNE.filter(([c]) => turni[c]).map(([c, nome]) => prefissoNota(nome) + turni[c])].join(SEPARATORE_NOTE);
}

/** L'ultimo giorno da controllare: oggi nel mese in corso, altrimenti tutto il mese. */
function ultimoDaControllare() {
  const oggi = new Date(), [anno, mese] = sessione.mese.split("-").map(Number);
  return oggi.getFullYear() === anno && oggi.getMonth() + 1 === mese ? oggi.getDate() : sessione.scheda.giorni.length;
}
const nonControllati = () => sessione.scheda.giorni.filter((g) => g.giorno <= ultimoDaControllare() && !eControllato(g));

// ---------------------------------------------------------------- salvataggi

let erroreCorrente = null;   // la casella d'errore della schermata aperta
let modo = null;             // null | "correggi" | "aggiungi": cosa sta facendo il dipendente nel giorno aperto
const contenitori = {};

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

async function dopoErrore(err) {
  if (err.status === 401) return sessioneScaduta();
  if (err.status === 409) { await vistaScheda(sessione.mese); return segnala("La scheda è confermata"); }
  scrivi(erroreCorrente, err.message);
}

/** Salva un giorno (i salvataggi vanno uno alla volta). Dà true se è andato a buon fine. */
function invia(giorno, modifiche) {
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("PUT", `/${sessione.mese}/giorni/${giorno}`, corpoDa(datiGiorno(giorno), modifiche));
      controllati.add(giorno);
      salvaControllati();
      modo = null;
      aggiorna();
      segnala("Salvato");
      return true;
    } catch (err) { await dopoErrore(err); return false; }
  });
  return coda;
}

function ripristina(giorno) {
  coda = coda.then(async () => {
    try {
      sessione.scheda = await chiama("DELETE", `/${sessione.mese}/giorni/${giorno}`);
      modo = null;
      aggiorna();
      segnala("Giorno ripristinato dai turni");
    } catch (err) { await dopoErrore(err); }
  });
}

function aggiornaTotali() {
  const t = sessione.scheda.totali;
  contenitori.totali.replaceChildren(el("span", { class: "so-totali-titolo" }, "Le tue ore del mese:"), ...[["Giorni di ferie", t.giorni_ferie], ["Ore postazioni", t.ore_postazioni],
    ["Ore secondari", t.ore_secondari], ["Totale mese", t.totale_mese], ["Ore disponibilità aggiuntive", t.ore_disponibilita]]
    .map(([nome, valore]) => el("span", {}, `${nome}: `, el("strong", {}, String(valore)))));
}

// ---------------------------------------------------------------- moduli del giorno

const campoOra = (etichetta, valore) => {
  const input = el("input", { type: "text", inputmode: "numeric", autocomplete: "off", maxlength: 5, placeholder: "8:00", value: valore });
  return { input, campo: el("label", { class: "so-ora" }, etichetta, input) };
};

/** Il modulo per scrivere un turno: nuovo (colonna assente, si sceglie il tipo) o da modificare. */
function formTurno(giorno, colonna, chiudi) {
  const g = datiGiorno(giorno);
  const attuale = colonna ? orePair(g.colonne[colonna]) : null;
  const scelta = colonna ? null : el("select", { "aria-label": "Tipo di turno" },
    COLONNE.filter(([c]) => !g.colonne[c]).map(([c, nome]) => el("option", { value: c }, nome)));
  const inizio = campoOra("Ora di inizio", attuale ? attuale[0] : ""), fine = campoOra("Ora di fine", attuale ? attuale[1] : "");
  const prima = separaExtra(colonna ? (leggiNote(g.note).turni[colonna] || "") : "");
  const nota = el("input", { type: "text", autocomplete: "off", maxlength: MAX_NOTE_GIORNO, placeholder: "per esempio: Ass. Fiera", value: prima.testo });
  const extra = el("input", { type: "checkbox", checked: prima.extra });
  const salva = el("button", { type: "submit", class: "so-piccolo" }, "Salva");
  return el("form", { class: "so-turno-form", onsubmit: async (e) => {
    e.preventDefault();
    if (!inizio.input.value.trim() || !fine.input.value.trim()) { scrivi(erroreCorrente, "Scrivi l'ora di inizio e di fine, per esempio 8 oppure 8:30."); return; }
    salva.disabled = true;
    const tipo = colonna || scelta.value, corrente = datiGiorno(giorno);
    const colonne = { ...corpoDa(corrente).colonne, [tipo]: [inizio.input.value.trim(), fine.input.value.trim()] };
    if (!await invia(giorno, { colonne, note: componiNote(corrente.note, tipo, uniscExtra(extra.checked, nota.value)) })) salva.disabled = false;
  } }, ...(scelta ? [scelta] : []), inizio.campo, fine.campo,
  el("label", { class: "so-extra-turno" }, extra, " Si tratta di un extra? (Oltre i turni che escono il venerdì)"),
  el("label", { class: "so-nota-turno" }, "Nota del turno (se serve)", nota), salva,
  el("button", { type: "button", class: "so-secondario so-piccolo", onclick: chiudi }, "Annulla"));
}

/** Un turno con Modifica ed Elimina (si vede dopo «Correggi gli orari»). */
function voceTurno(giorno, colonna, nome, coppia) {
  const li = el("li", { class: "so-turno" });
  const vista = () => li.replaceChildren(
    el("span", { class: `so-chip so-${colonna}` }, nome), el("span", { class: "so-turno-ore" }, `${formatta(coppia[0])} – ${formatta(coppia[1])}`),
    el("button", { type: "button", class: "so-secondario so-piccolo", "aria-label": `Modifica ${nome}`,
      onclick: () => li.replaceChildren(formTurno(giorno, colonna, vista)) }, "Modifica"),
    el("button", { type: "button", class: "so-secondario so-piccolo", "aria-label": `Elimina ${nome}`,
      onclick: () => { const corrente = datiGiorno(giorno);
        invia(giorno, { colonne: { ...corpoDa(corrente).colonne, [colonna]: null }, note: componiNote(corrente.note, colonna, "") }); } }, "Elimina"),
    ...(leggiNote(datiGiorno(giorno).note).turni[colonna] ? [el("span", { class: "so-nota-testo" }, leggiNote(datiGiorno(giorno).note).turni[colonna])] : []));
  vista();
  return li;
}

/** Disponibilità aggiuntiva del giorno (sempre visibile): un solo modulo con un solo pulsante. */
function formExtra(giorno, bloccata) {
  const g = datiGiorno(giorno), d = g.disponibilita;
  const dal = campoOra("Dalle", d ? formatta(d.inizio) : ""), al = campoOra("Alle", d ? formatta(d.fine) : "");
  const motivo = el("input", { type: "text", autocomplete: "off", maxlength: MAX_CAUSALE, value: d ? d.causale : "", disabled: bloccata });
  for (const c of [dal.input, al.input]) c.disabled = bloccata;
  const salva = el("button", { type: "submit", class: "so-secondario so-piccolo" }, "Salva disponibilità");
  return el("form", { class: "so-extra", onsubmit: async (e) => {
    e.preventDefault();
    const disp = [dal.input.value.trim(), al.input.value.trim(), motivo.value.trim()];
    if (disp.some(Boolean) && (!disp[0] || !disp[1])) { scrivi(erroreCorrente, "Per la disponibilità aggiuntiva scrivi sia da che ora a che ora."); return; }
    salva.disabled = true;
    const ok = await invia(giorno, { disponibilita: disp.some(Boolean) ? { inizio: disp[0], fine: disp[1], causale: disp[2] } : null });
    if (!ok) salva.disabled = false;
  } },
  el("fieldset", { class: "so-disp" }, el("legend", {}, "Disponibilità aggiuntiva (Volontariato)"),
    el("p", { class: "so-tenue so-aiuto" }, "Compila solo se quel giorno hai dato una disponibilità in più. Altrimenti lascia vuoto."), dal.campo, al.campo,
    el("label", { class: "so-motivo" }, "Motivo", motivo)),
  ...(bloccata ? [] : [salva]));
}

// ---------------------------------------------------------------- schermata del giorno

const segnaliGiorno = (g, bloccata) => [
  ...(g.corretto ? [el("p", { class: "so-etichetta so-bozza" }, "Corretto da te"),
    ...(bloccata ? [] : [el("button", { type: "button", class: "so-secondario so-piccolo", onclick: () => ripristina(g.giorno) }, "Ripristina dai turni")])] : []),
  ...(g.da_rivedere ? [el("p", { class: "so-avviso" }, "Due turni nella stessa colonna: controlla gli orari e le note.")] : []),
  ...(g.turni_cambiati ? [el("p", { class: "so-avviso" }, "I turni sono cambiati dopo la tua correzione: controlla.")] : []),
  ...(g.giorno > ultimoDaControllare() ? [el("p", { class: "so-tenue" }, "Questo giorno non è ancora passato: non serve controllarlo adesso.")] : []),
];

function elencoTurni(g) {
  const turni = COLONNE.filter(([c]) => g.colonne[c]);
  if (modo === "correggi") return el("div", {}, el("p", { class: "so-tenue" }, "Premi «Modifica» sul turno da cambiare, oppure «Elimina» se non l'hai fatto."),
    el("ul", { class: "so-turni" }, turni.map(([c, nome]) => voceTurno(g.giorno, c, nome, g.colonne[c]))));
  if (!turni.length) return el("p", { class: "so-tenue" }, g.ferie ? "Hai segnato questo giorno come ferie." : "Il programma non ha trovato turni per questo giorno.");
  const note = leggiNote(g.note).turni;
  return el("div", { class: "so-grandi" }, turni.map(([c, nome]) => el("div", {},
    el("span", { class: `so-chip so-${c}` }, nome), ` ${formatta(g.colonne[c][0])} – ${formatta(g.colonne[c][1])}`,
    ...(note[c] ? [el("small", { class: "so-nota-testo" }, note[c])] : []))));
}

function azioniGiorno(g) {
  const giorno = g.giorno, ha = COLONNE.some(([c]) => g.colonne[c]), piene = COLONNE.every(([c]) => g.colonne[c]);
  const cambia = (valore) => { modo = modo === valore ? null : valore; aggiorna(); };
  const grande = (titolo, spiegazione, opzioni) => el("button", { type: "button", ...opzioni },
    el("strong", {}, titolo), el("small", {}, spiegazione));
  return el("div", { class: "so-azioni-giorno" },
    el("p", { class: "so-domanda-testo" }, "Cosa vuoi fare per questo giorno?"),
    grande(ha || g.ferie ? "✓ Sì, è tutto giusto" : "✓ Sì, quel giorno non ho fatto turni",
      ha ? "Ho fatto proprio questi turni, con questi orari. Passa al giorno dopo." : "Passa al giorno dopo.", { class: "so-grande", onclick: () => {
        controllati.add(giorno); salvaControllati(); vaiA(giorno < sessione.scheda.giorni.length ? giorno + 1 : "riepilogo");
      } }),
    ...(ha ? [grande("Cambia un orario", "Ho iniziato o finito a un'ora diversa.",
      { class: "so-secondario so-grande", "aria-pressed": String(modo === "correggi"), onclick: () => cambia("correggi") })] : []),
    ...(piene ? [] : [grande("+ Aggiungi un turno", "Ho fatto un turno che qui non c'è.",
      { class: "so-secondario so-grande", "aria-pressed": String(modo === "aggiungi"), onclick: () => cambia("aggiungi") })]),
    grande(g.ferie ? "Ferie segnate ✓" : "Ero in ferie", g.ferie ? "Tocca per togliere le ferie." : "Segna questo giorno come ferie.",
      { class: "so-secondario so-grande", "aria-pressed": g.ferie ? "true" : "false", onclick: () => invia(giorno, { ferie: g.ferie ? 0 : 1 }) }));
}

function schermataGiorno() {
  const giorno = sessione.giorno, g = datiGiorno(giorno), bloccata = confermata();
  erroreCorrente = boxErrore();
  return [el("section", { class: `so-domanda${eWeekend(giorno) ? " so-weekend" : ""}`, "aria-label": titoloGiorno(giorno) },
    el("h2", { tabindex: -1 }, titoloGiorno(giorno)),
    ...(bloccata ? [] : [el("p", { class: "so-tenue" }, "Il programma ha segnato questi turni per te:")]),
    elencoTurni(g),
    ...(leggiNote(g.note).altre.length ? [el("p", { class: "so-tenue so-nota-programma" }, `Note del programma: ${leggiNote(g.note).altre.join("; ")}`)] : []),
    ...segnaliGiorno(g, bloccata),
    ...(modo === "aggiungi" && !bloccata ? [formTurno(giorno, null, () => { modo = null; aggiorna(); })] : []),
    ...(bloccata ? [] : [azioniGiorno(g)]), erroreCorrente),
  el("section", { class: "so-extra-box" }, formExtra(giorno, bloccata)),
  el("div", { class: "so-azioni so-passi" },
    el("button", { type: "button", class: "so-secondario", disabled: giorno <= 1, onclick: () => vaiA(giorno - 1) }, "‹ Giorno prima"),
    el("button", { type: "button", class: "so-secondario", onclick: () => vaiA(giorno < sessione.scheda.giorni.length ? giorno + 1 : "riepilogo") },
      giorno < sessione.scheda.giorni.length ? "Vai al giorno dopo ›" : "Vai al riepilogo ›"))];
}

// ---------------------------------------------------------------- striscia della settimana e avanzamento

function disegnaStriscia() {
  const n = sessione.scheda.giorni.length, scost = (giornoSettimana(1) + 6) % 7;   // lunedì = 0
  const idx = Math.floor((sessione.visto - 1 + scost) / 7), primo = idx * 7 - scost + 1;
  const celle = Array.from({ length: 7 }, (_, k) => {
    const giorno = primo + k;
    if (giorno < 1 || giorno > n) return el("span", { class: "so-cella so-vuota", "aria-hidden": "true" });
    const g = datiGiorno(giorno), fatto = !confermata() && eControllato(g);
    return el("button", { type: "button", class: `so-cella${giorno === sessione.giorno ? " so-attiva" : ""}${giorno > ultimoDaControllare() ? " so-futuro" : ""}`,
      "aria-label": `${titoloGiorno(giorno)}${fatto ? ", controllato" : ""}`, "aria-current": giorno === sessione.giorno ? "true" : "false",
      onclick: () => vaiA(giorno) }, el("small", {}, LETTERE[giornoSettimana(giorno)]), el("strong", {}, String(giorno)), el("i", { class: fatto ? "so-pallino" : "" }));
  });
  const primoValido = Math.max(1, primo), ultimoValido = Math.min(n, primo + 6);
  return [el("div", { class: "so-settimana-nav" },
    el("button", { type: "button", class: "so-secondario so-piccolo", disabled: primo <= 1, onclick: () => vaiA(Math.max(1, primo - 7)) }, "‹ Prima"),
    el("strong", {}, `Dal ${primoValido} al ${ultimoValido}`),
    el("button", { type: "button", class: "so-secondario so-piccolo", disabled: primo + 7 > n, onclick: () => vaiA(primo + 7) }, "Dopo ›")),
  el("div", { class: "so-striscia" }, celle),
  ...(confermata() ? [] : [el("p", { class: "so-tenue so-didascalia" }, "Tocca un giorno per aprirlo. Il pallino verde vuol dire che l'hai già controllato.")])];
}

function disegnaAvanzamento() {
  if (confermata()) return [];
  const fine = ultimoDaControllare(), fatti = sessione.scheda.giorni.filter((g) => g.giorno <= fine && eControllato(g)).length;
  return [el("div", { class: "so-avanza" },
    el("span", {}, `Hai controllato ${fatti} ${fatti === 1 ? "giorno" : "giorni"} su ${fine}`),
    el("button", { type: "button", class: "so-secondario so-piccolo", onclick: () => vaiA("riepilogo") }, "Vai al riepilogo")),
  el("progress", { value: fatti, max: fine, "aria-label": "Giorni controllati" })];
}

// ---------------------------------------------------------------- riepilogo, conferma, note finali

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

function campoNoteFinali(bloccata) {
  const errore = boxErrore();
  const note = el("textarea", { id: "so-note", rows: 4, maxlength: MAX_NOTE_FINALI, disabled: bloccata, value: sessione.scheda.note,
    onchange: () => {
      coda = coda.then(async () => {
        try { sessione.scheda = await chiama("PUT", `/${sessione.mese}/note`, { note: note.value }); scrivi(errore, ""); segnala("Salvato"); }
        catch (err) { if (err.status === 401) return sessioneScaduta(); scrivi(errore, err.message); }
      });
    } });
  return [el("h3", {}, el("label", { for: "so-note" }, "Note finali")), note, errore];
}

function elencoDaVedere(giorni, testo) {
  return giorni.length ? el("ul", { class: "so-da-vedere" }, giorni.map((g) => el("li", {},
    el("button", { type: "button", class: "so-secondario", onclick: () => vaiA(g.giorno) }, titoloGiorno(g.giorno), el("span", { class: "so-etichetta so-bozza" }, testo(g)))))) : null;
}

function schermataRiepilogo() {
  const bloccata = confermata(), mancano = nonControllati(), dubbi = sessione.scheda.giorni.filter((g) => daRivedere(g) && !mancano.includes(g));
  erroreCorrente = boxErrore();
  return [el("section", { class: "so-domanda" }, el("h2", { tabindex: -1 }, "Riepilogo del mese"),
    ...(bloccata ? [el("p", { class: "so-ok" }, `Scheda confermata il ${new Date(sessione.scheda.confermata_il).toLocaleString("it-IT")}. Puoi scaricarla in Excel.`)]
      : [mancano.length || dubbi.length
        ? el("p", {}, "Prima di finire guarda questi giorni:") : el("p", { class: "so-ok" }, "Hai controllato tutti i giorni.")]),
    ...(bloccata ? [] : [elencoDaVedere(mancano, () => "Da controllare"), elencoDaVedere(dubbi, (g) => (g.turni_cambiati ? "Turni cambiati" : "Da rivedere"))].filter(Boolean)),
    ...campoNoteFinali(bloccata),
    el("div", { class: "so-azioni" }, bloccata
      ? el("a", { class: "so-pulsante", href: `/api/schede-ore/${sessione.mese}.xlsx`, download: "" }, "Scarica Excel")
      : el("button", { type: "button", class: "so-grande", onclick: conferma }, "Ho finito la revisione")),
    ...(bloccata ? [] : [el("p", { class: "so-tenue" }, "Dopo la conferma la scheda non si può più modificare.")]))];
}

// ---------------------------------------------------------------- pagina

function aggiorna(portaFocus = false) {
  if (typeof sessione.giorno === "number") sessione.visto = sessione.giorno;
  contenitori.avanzamento.replaceChildren(...disegnaAvanzamento());
  contenitori.striscia.replaceChildren(...disegnaStriscia());
  contenitori.schermata.replaceChildren(...(sessione.giorno === "riepilogo" ? schermataRiepilogo() : schermataGiorno()));
  aggiornaTotali();
  if (portaFocus) contenitori.schermata.querySelector("h2").focus();
}

function vaiA(giorno) {
  sessione.giorno = giorno;
  modo = null;
  aggiorna(true);
}

function disegnaScheda() {
  const s = sessione.scheda, bloccata = confermata();
  controllati = leggiControllati();
  modo = null;
  const primo = nonControllati()[0];
  sessione.giorno = bloccata || !primo ? "riepilogo" : primo.giorno;
  sessione.visto = typeof sessione.giorno === "number" ? sessione.giorno : 1;
  for (const nome of ["avanzamento", "striscia", "schermata"]) contenitori[nome] = el("div", { class: `so-${nome}-box` });
  contenitori.totali = el("div", { class: "so-totali", role: "group", "aria-label": "Totali del mese" });
  mostra("scheda",
    el("div", { class: "so-testa-scheda" },
      el("h2", {}, `${nomeMese(sessione.mese)} · ${s.persona.nome} `, el("span", { class: `so-etichetta so-${s.stato}` }, bloccata ? "Confermata" : "In revisione")),
      el("div", { class: "so-azioni" },
        el("button", { type: "button", class: "so-secondario", onclick: () => vistaMesi() }, "‹ Mesi"),
        el("button", { type: "button", class: "so-secondario", onclick: esci }, "Esci"))),
    ...(bloccata ? [] : [el("div", { class: "so-guida" }, el("strong", {}, "Come si fa"),
      el("ol", {}, el("li", {}, "Qui sotto vedi un giorno alla volta, con i turni che il programma ha segnato per te."),
        el("li", {}, "Se è tutto giusto, premi «Sì, è tutto giusto». Se no, cambia l'orario o aggiungi il turno che manca."),
        el("li", {}, "Quando hai controllato tutti i giorni, premi «Vai al riepilogo» e poi «Ho finito la revisione»."),
        el("li", {}, "Gli orari si scrivono così: 8 oppure 8:30.")))]),
    contenitori.avanzamento, contenitori.striscia, contenitori.schermata, contenitori.totali);
  aggiorna();
}

vistaMesi().catch((err) => { root.replaceChildren(el("p", { class: "so-errore", role: "alert" }, err.message)); });
