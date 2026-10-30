// CVAP Turnistica — ingresso del frontend: routing a hash e montaggio delle viste.

import * as settimana from "./js/settimana.js";
import * as personale from "./js/personale.js";
import * as dipendente from "./js/dipendente.js";
import * as statistiche from "./js/statistiche.js";
import * as impostazioni from "./js/impostazioni.js";
import { api } from "./js/api.js";
import { el } from "./js/util.js";

const VISTE = {
  settimana: { modulo: settimana, titolo: "Settimana" },
  dipendente: { modulo: dipendente, titolo: "Turni dipendente" },
  personale: { modulo: personale, titolo: "Personale" },
  statistiche: { modulo: statistiche, titolo: "Statistiche" },
  impostazioni: { modulo: impostazioni, titolo: "Impostazioni" },
};
const PREDEFINITA = "settimana";

function leggiHash() {
  const [nome, ...resto] = location.hash.replace(/^#\/?/, "").split("/");
  return { nome: VISTE[nome] ? nome : PREDEFINITA, parametro: resto.join("/") || null, valido: !!VISTE[nome] };
}

let vistaCorrente = null;

function instrada() {
  const { nome, parametro, valido } = leggiHash();
  if (!valido && location.hash && location.hash !== "#") {
    history.replaceState(null, "", `#${PREDEFINITA}`);
  }
  for (const [chiave] of Object.entries(VISTE)) {
    const sezione = document.getElementById(`view-${chiave}`);
    if (sezione) sezione.hidden = chiave !== nome;
    const link = document.querySelector(`.nav a[data-view="${chiave}"]`);
    if (link) {
      if (chiave === nome) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  }
  document.title = `${VISTE[nome].titolo} · CVAP Turnistica`;
  const contenitore = document.getElementById(`view-${nome}`);
  const cambioVista = vistaCorrente !== nome;
  vistaCorrente = nome;
  VISTE[nome].modulo.mostra(contenitore, parametro);
  if (cambioVista) {
    const main = document.getElementById("main");
    if (main) main.focus({ preventScroll: true });
  }
}

// ---------------------------------------------------------------- accesso con password

let protetto = false;

function mostraAccesso() {
  document.body.classList.add("senza-accesso");
  const main = document.getElementById("main");
  for (const sezione of main.querySelectorAll(".view")) sezione.hidden = true;
  let box = document.getElementById("accesso");
  if (box) { box.querySelector("input").focus(); return; }
  const input = el("input", { id: "accesso-password", type: "password", required: true, autocomplete: "current-password" });
  const errore = el("p", { class: "accesso-errore", role: "alert" });
  const bottone = el("button", { type: "submit", class: "btn btn-primary btn-grande" }, "Entra");
  box = el("form", {
    id: "accesso", class: "accesso card", "aria-labelledby": "accesso-titolo",
    onsubmit: async (e) => {
      e.preventDefault();
      bottone.disabled = true;
      errore.textContent = "";
      try {
        await api.accedi(input.value);
        box.remove();
        document.body.classList.remove("senza-accesso");
        aggiornaEsci();
        vistaCorrente = null;
        instrada();
      } catch (err) {
        errore.textContent = err.status === 401 ? "Password errata." : err.message;
        input.select();
      } finally {
        bottone.disabled = false;
      }
    },
  },
  el("img", { src: "/static/img/logo-croce-verde.png", alt: "Croce Verde Ascoli Piceno", class: "accesso-logo" }),
  el("h1", { id: "accesso-titolo" }, "Turnistica"),
  el("p", { class: "muted" }, "Inserisci la password dell'associazione."),
  el("label", { for: "accesso-password" }, "Password"), input, errore, bottone);
  main.append(box);
  input.focus();
}

function aggiornaEsci() {
  const nav = document.querySelector(".nav");
  let esci = document.getElementById("esci");
  if (!protetto) { if (esci) esci.remove(); return; }
  if (esci) return;
  esci = el("button", {
    id: "esci", type: "button", class: "btn btn-ghost btn-small esci",
    onclick: async () => {
      try { await api.esci(); } catch { /* comunque si torna alla password */ }
      mostraAccesso();
    },
  }, "Esci");
  nav.after(esci);
}

window.addEventListener("cvap:accesso-richiesto", mostraAccesso);
window.addEventListener("hashchange", () => { if (!document.getElementById("accesso")) instrada(); });

(async () => {
  try {
    const s = await api.sessione();
    protetto = s.protetto;
    if (s.protetto && !s.autenticato) { mostraAccesso(); return; }
  } catch { /* se il controllo fallisce si prova comunque: le API diranno se serve la password */ }
  aggiornaEsci();
  instrada();
})();
