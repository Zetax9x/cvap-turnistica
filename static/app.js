// CVAP Turnistica — ingresso del frontend: routing a hash e montaggio delle viste.

import * as settimana from "./js/settimana.js";
import * as personale from "./js/personale.js";
import * as statistiche from "./js/statistiche.js";
import * as impostazioni from "./js/impostazioni.js";

const VISTE = {
  settimana: { modulo: settimana, titolo: "Settimana" },
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

window.addEventListener("hashchange", instrada);
instrada();
