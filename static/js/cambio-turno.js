import { el } from "./util.js";
import { richiesta, turnoScheda, riepilogo, nuovaChiave } from "./cambi-turno-comune.js";

const root = document.getElementById("cambio-app");
const PENDENTE = "cvap-cambio-pendente";
let persone = [], persona = null, turno = null, tipo = null, collega = null, ricevuto = null;
let vista = null, corpo = null, occupato = false;

function memorizza(valore) {
  try { valore ? sessionStorage.setItem(PENDENTE, JSON.stringify(valore)) : sessionStorage.removeItem(PENDENTE); } catch { /* navigazione privata */ }
}
function leggiPendente() {
  try { return JSON.parse(sessionStorage.getItem(PENDENTE)); } catch { return null; }
}
function bottone(testo, azione, secondario = false) {
  return el("button", { type: "button", class: secondario ? "cambio-secondario" : "", onclick: azione }, testo);
}
function pagina(passo, titolo, ...figli) {
  root.replaceChildren(el("p", { class: "cambio-passo" }, `Passo ${passo} di 4`),
    el("h2", {}, titolo), ...figli, el("p", { id: "cambio-errore", class: "cambio-errore", role: "alert", tabindex: -1, hidden: true }));
  root.focus();
}
function errore(err) {
  const p = document.getElementById("cambio-errore");
  if (p) { p.hidden = false; p.textContent = err.message; p.focus(); }
}
async function esegui(azione) {
  if (occupato) return;
  occupato = true;
  root.setAttribute("aria-busy", "true");
  const controlli = [...root.querySelectorAll("button, input, select")];
  const stati = controlli.map(c => c.disabled);
  controlli.forEach(c => c.disabled = true);
  try { await azione(); } catch (err) { errore(err); }
  finally {
    occupato = false; root.removeAttribute("aria-busy");
    controlli.forEach((c, i) => { if (c.isConnected) c.disabled = stati[i]; });
  }
}

function scegliPersona() {
  const cerca = el("input", { id: "cerca-persona", type: "search", placeholder: "Cerca il tuo nome", autocomplete: "off" });
  const lista = el("div", { class: "cambio-scelte" });
  const disegna = () => {
    const visibili = persone.filter(p => p.nome.toLocaleLowerCase("it").includes(cerca.value.toLocaleLowerCase("it")));
    lista.replaceChildren(...visibili.map(p => bottone(p.nome, () => {
      persona = p; turno = null; scegliTurno();
    }, true)));
    if (!visibili.length) lista.append(el("p", { role: "status" }, "Nessun dipendente trovato."));
  };
  cerca.addEventListener("input", disegna);
  pagina(1, "Chi sei?", el("p", {}, "Scegli il tuo nome per vedere i turni ancora da svolgere."),
    el("label", { for: "cerca-persona" }, "Il tuo nome"), cerca, lista);
  disegna();
}

async function scegliTurno() {
  await esegui(async () => {
    const turni = await richiesta(`cambi-turno/turni?persona_id=${persona.id}`);
    pagina(2, "Quale turno vuoi cambiare?", el("p", {}, `Stai registrando come ${persona.nome}.`),
      el("p", { class: "cambio-muted" }, "Sono visibili solo i turni futuri."),
      elencoTurni(turni, turno?.id, t => { turno = t; tipo = null; collega = null; ricevuto = null; scegliOperazione(); }),
      bottone("Cambia nome", scegliPersona, true));
  });
}

function elencoTurni(turni, selezionato, seleziona) {
  if (!turni.length) return el("p", { role: "status" }, "Non ci sono turni ancora da svolgere.");
  const contenitore = el("div", { class: "cambio-scelte" });
  let settimana = "";
  for (const t of turni) {
    const d = new Date(`${t.data}T12:00:00`);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const gruppo = d.toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
    if (gruppo !== settimana) { contenitore.append(el("h3", {}, `Settimana del ${gruppo}`)); settimana = gruppo; }
    contenitore.append(el("button", { type: "button", class: "cambio-secondario cambio-turno-scelta",
      "aria-pressed": t.id === selezionato ? "true" : "false", onclick: () => seleziona(t) }, turnoScheda(t)));
  }
  return contenitore;
}

function scegliOperazione() {
  const sceltaTipo = el("div", { class: "cambio-scelte" },
    bottone("Ho ceduto il turno", () => { tipo = "cessione"; ricevuto = null; scegliCollega(); }),
    bottone("Ho scambiato il turno", () => { tipo = "scambio"; scegliCollega(); }));
  pagina(3, "Che variazione hai concordato?", turnoScheda(turno), sceltaTipo,
    bottone("Indietro ai miei turni", scegliTurno, true));
}

function scegliCollega() {
  const selettore = el("select", { id: "collega", required: true }, el("option", { value: "" }, "Scegli un dipendente"),
    ...persone.filter(p => p.id !== persona.id).map(p => el("option", { value: p.id }, p.nome)));
  if (collega) selettore.value = String(collega.id);
  const avanti = bottone("Continua", () => esegui(async () => {
    collega = persone.find(p => p.id === Number(selettore.value));
    ricevuto = null;
    if (tipo === "cessione") await mostraAnteprima();
    else {
      const turni = await richiesta(`cambi-turno/turni?persona_id=${collega.id}`);
      pagina(3, `Quale turno di ${collega.nome} ricevi?`,
        elencoTurni(turni, null, t => { ricevuto = t; esegui(mostraAnteprima); }),
        bottone("Cambia collega", scegliCollega, true));
    }
  }));
  avanti.disabled = !selettore.value;
  selettore.addEventListener("change", () => { avanti.disabled = !selettore.value; });
  pagina(3, tipo === "cessione" ? "A chi cedi il turno?" : "Con chi hai scambiato?",
    turnoScheda(turno), el("label", { for: "collega" }, "Dipendente"), selettore, avanti,
    bottone("Indietro", scegliOperazione, true));
}

async function mostraAnteprima() {
  corpo = { tipo, persona_id: persona.id, collega_id: collega.id, turno_id: turno.id, turno_ricevuto_id: ricevuto?.id ?? null };
  vista = await richiesta("cambi-turno/anteprima", corpo);
  const conferma = bottone("Conferma e comunica alla responsabile", () => esegui(async () => {
    const invio = { ...corpo, versione: vista.versione, chiave: nuovaChiave() };
    memorizza(invio);
    await inviaConferma(invio);
  }));
  conferma.disabled = vista.errori.length > 0;
  pagina(4, "Controlla e conferma", riepilogo(vista),
    el("p", {}, "Confermando aggiorni il tabellone e comunichi la variazione ai responsabili, con il PDF dei turni aggiornati."),
    conferma, bottone("Indietro", scegliCollega, true),
    bottone("Ricarica i miei turni", scegliTurno, true));
}

async function inviaConferma(invio) {
  try {
    const esito = await richiesta("cambi-turno/conferme", invio);
    mostraEsito(esito);
  } catch (err) {
    if (err.status) { memorizza(null); throw err; }
    recupero(invio);
  }
}

function mostraEsito(esito) {
  memorizza(null);
  root.replaceChildren(el("div", { class: "cambio-successo", role: "status" },
    el("h2", {}, esito.annullata_il ? "Cambio annullato dalla responsabile" : "Cambio registrato"),
    el("p", {}, `Registrazione n. ${esito.id}`),
    el("ul", {}, ...esito.riepilogo.map(r => el("li", {}, r))),
    el("p", {}, esito.notifica === "inviata" ? "Comunicazione inviata ai responsabili con il tabellone aggiornato e il PDF."
      : "Il cambio è salvato. La comunicazione ai responsabili è da reinviare dal gestionale. Non registrare di nuovo il cambio.")),
    bottone("Registra un’altra variazione", scegliPersona));
  root.focus();
}

function recupero(invio) {
  pagina(4, "Verifica la registrazione", el("p", {}, "La connessione si è interrotta. Verifica l’esito oppure riprendi lo stesso invio: il cambio verrà registrato una volta sola."),
    bottone("Verifica esito", () => esegui(async () => {
      try { mostraEsito(await richiesta(`cambi-turno/conferme/${invio.chiave}`)); }
      catch (err) {
        if (err.status === 404) throw new Error("La registrazione non risulta ancora completata. Riprendi lo stesso invio.");
        throw err;
      }
    })),
    bottone("Riprendi lo stesso invio", () => esegui(async () => {
      try { await inviaConferma(invio); }
      catch (err) {
        // Un errore certo dal server permette di ricominciare con dati aggiornati.
        if (err.status) {
          pagina(4, "Rivedi il cambio", el("p", {}, err.message), bottone("Ricarica i turni", scegliPersona));
        } else throw err;
      }
    }), true));
}

(async () => {
  try {
    persone = await richiesta("cambi-turno/dipendenti");
    const invio = leggiPendente();
    if (invio) recupero(invio); else scegliPersona();
  } catch (err) {
    pagina(1, "Impossibile caricare i dipendenti", bottone("Riprova", () => location.reload()));
    errore(err);
  }
})();
