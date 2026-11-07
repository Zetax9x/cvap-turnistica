// Turni CVAP (app per telefono): avvio, accesso, navigazione a schede.
import { api } from "/static/js/api.js";
import { el, clear } from "/static/js/util.js";
import { icona, avviso, monta } from "./ui.js";

const SCHEDE = [
  { id: "oggi", testo: "Oggi", icona: "oggi" },
  { id: "settimana", testo: "Settimana", icona: "settimana" },
  { id: "persone", testo: "Persone", icona: "persone" },
  { id: "statistiche", testo: "Statistiche", icona: "stat" },
  { id: "altro", testo: "Altro", icona: "altro" },
];
const VISTE = {
  oggi: () => import("./oggi.js"),
  settimana: () => import("./settimana.js"),
  persone: () => import("./persone.js"),
  statistiche: () => import("./statistiche.js"),
  altro: () => import("./altro.js"),
};
// sezioni che appartengono a una scheda ma hanno un nome proprio nell'indirizzo
const DI_SCHEDA = { persona: "persone", dipendente: "persone" };

const schermata = document.getElementById("schermata");
const tab = document.getElementById("tab");
let pulizia = null;
let seq = 0;

export function vai(percorso) { location.hash = `#/${percorso}`; }

function leggiIndirizzo() {
  const parti = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  return { sezione: parti[0] || "oggi", parametri: parti.slice(1) };
}

function disegnaSchede(attiva) {
  monta(tab, ...SCHEDE.map((s) => el("a", {
    href: `#/${s.id}`, "aria-current": s.id === attiva ? "page" : null,
  }, icona(s.icona), el("span", {}, s.testo))));
}

async function mostraVista() {
  const mio = ++seq;
  const { sezione, parametri } = leggiIndirizzo();
  const nome = VISTE[sezione] ? sezione : (VISTE[DI_SCHEDA[sezione]] ? DI_SCHEDA[sezione] : "oggi");
  disegnaSchede(DI_SCHEDA[sezione] || nome);
  if (pulizia) { try { pulizia(); } catch { /* niente */ } pulizia = null; }
  clear(schermata);
  try {
    const modulo = await VISTE[nome]();
    if (mio !== seq) return;
    pulizia = (await modulo.default(schermata, { sezione, parametri })) || null;
  } catch (e) {
    if (mio !== seq || (e && e.status === 401)) return;
    monta(schermata, el("div", { class: "contenuto", style: "padding-top:24px" },
      avviso(e && e.message ? e.message : "Errore imprevisto", "errore")));
  }
}

// ---------- accesso ----------
const boxAccesso = document.getElementById("accesso");

function mostraAccesso() {
  if (!boxAccesso.hidden) return;
  const campo = el("input", { class: "input", type: "password", autocomplete: "current-password",
    placeholder: "Password dell'associazione", "aria-label": "Password" });
  const errore = el("div");
  const bottone = el("button", { class: "btn btn-primario btn-blocco", type: "submit" }, "Entra");
  const modulo = el("form", { class: "contenuto", onSubmit: async (ev) => {
    ev.preventDefault();
    bottone.disabled = true;
    clear(errore);
    try {
      await api.accedi(campo.value);
      boxAccesso.hidden = true;
      clear(boxAccesso);
      avvia();
    } catch (e) {
      errore.append(avviso(e.message, "errore"));
      bottone.disabled = false;
    }
  } }, campo, errore, bottone);
  monta(boxAccesso, 
    el("img", { src: "/static/img/logo-croce-verde.png", alt: "Croce Verde Ascoli Piceno" }),
    el("h1", { class: "titolo-s" }, "Turni CVAP"),
    modulo);
  boxAccesso.hidden = false;
  document.getElementById("app").hidden = true;
  document.getElementById("avvio").hidden = true;
}

window.addEventListener("cvap:accesso-richiesto", mostraAccesso);

export async function esci() {
  await api.esci();
  location.hash = "#/oggi";
  location.reload();
}

async function avvia() {
  try {
    const s = await api.sessione();
    if (s.protetto && !s.autenticato) { mostraAccesso(); return; }
  } catch (e) {
    document.getElementById("avvio").hidden = true;
    document.body.append(el("div", { class: "contenuto", style: "padding:24px" }, avviso(e.message, "errore")));
    return;
  }
  document.getElementById("app").hidden = false;
  document.getElementById("avvio").hidden = true;
  if (!location.hash) history.replaceState(null, "", "#/oggi");
  mostraVista();
}

window.addEventListener("hashchange", mostraVista);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/app/sw.js", { scope: "/app/" }).catch(() => { /* senza SW l'app funziona lo stesso */ });
}
avvia();
