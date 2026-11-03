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
    pagina(2, "Quale turno vuoi cambiare?", el("p", {}, `Hai scelto il nome: ${persona.nome}.`),
      el("p", { class: "cambio-muted" }, "Scegli il turno che vuoi dare a un collega. Vedi solo i turni che devono ancora iniziare."),
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
    bottone("Do il mio turno a un collega", () => { tipo = "cessione"; ricevuto = null; scegliCollega(); }),
    bottone("Scambio il mio turno con un collega", () => { tipo = "scambio"; scegliCollega(); }));
  pagina(3, "Cosa vuoi fare?", turnoScheda(turno),
    el("p", {}, "Prima di proseguire, accordati con il collega. Puoi dargli il tuo turno oppure fare uno scambio: lui farà il tuo turno e tu farai il suo."), sceltaTipo,
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
      pagina(3, `Quale turno di ${collega.nome} farai tu?`,
        elencoTurni(turni, null, t => { ricevuto = t; esegui(mostraAnteprima); }),
        bottone("Cambia collega", scegliCollega, true));
    }
  }));
  avanti.disabled = !selettore.value;
  selettore.addEventListener("change", () => { avanti.disabled = !selettore.value; });
  pagina(3, tipo === "cessione" ? "Chi farà il tuo turno?" : "Con chi scambi il turno?",
    turnoScheda(turno), el("label", { for: "collega" }, "Dipendente"), selettore, avanti,
    bottone("Indietro", scegliOperazione, true));
}

async function mostraAnteprima() {
  corpo = { tipo, persona_id: persona.id, collega_id: collega.id, turno_id: turno.id, turno_ricevuto_id: ricevuto?.id ?? null };
  vista = await richiesta("cambi-turno/anteprima", corpo);
  const conferma = bottone("Conferma il cambio e invia l’email", () => esegui(async () => {
    const invio = { ...corpo, versione: vista.versione, chiave: nuovaChiave() };
    memorizza(invio);
    await inviaConferma(invio);
  }));
  conferma.disabled = vista.errori.length > 0;
  pagina(4, "Controlla e conferma", riepilogo(vista),
    el("p", {}, "Controlla nomi, date e orari. Conferma solo se avete già concordato il cambio: il tabellone verrà aggiornato e i responsabili riceveranno un’email con il riepilogo e il PDF dei turni."),
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
    el("p", {}, esito.notifica === "inviata" ? "Il tabellone è aggiornato. L’email con il riepilogo e il PDF è stata inviata ai responsabili."
      : "Il cambio è salvato e il tabellone è aggiornato. L’email non è stata inviata a tutti i responsabili. Avvisa la responsabile: potrà reinviarla dal gestionale. Non registrare di nuovo lo stesso cambio.")),
    bottone("Registra un altro cambio", scegliPersona));
  root.focus();
}

function recupero(invio) {
  pagina(4, "Controlla se il cambio è stato salvato", el("p", {}, "La connessione si è interrotta e non sappiamo se il cambio è stato salvato. Premi Controlla il salvataggio. Se non risulta salvato, premi Riprova a salvare questo cambio."),
    bottone("Controlla il salvataggio", () => esegui(async () => {
      try { mostraEsito(await richiesta(`cambi-turno/conferme/${invio.chiave}`)); }
      catch (err) {
        if (err.status === 404) throw new Error("Il cambio non risulta ancora salvato. Premi Riprova a salvare questo cambio.");
        throw err;
      }
    })),
    bottone("Riprova a salvare questo cambio", () => esegui(async () => {
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
