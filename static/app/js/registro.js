// Registro delle azioni (solo con la password master): tutte le modifiche fatte, con la password usata e il dettaglio.
import { api } from "/static/js/api.js";
import { el } from "/static/js/util.js";
import { testata, gruppo, pill, avviso, caricamento, monta, mostraErrore } from "./ui.js";

const PAGINA = 100;
const ACCESSI = {
  normale: ["Normale", ""], master: ["Master", "blu"], pubblico: ["Dipendente", ""],
  aperto: ["Senza password", ""], anonimo: ["Sconosciuto", "rosso"],
};

function quando(iso) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" })} `
    + d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function esito(codice) {
  if (codice < 300) return pill("Fatto", "verde");
  if (codice === 401) return pill("Rifiutato", "rosso");
  return pill("Non riuscito", "ambra");
}

function voce(r) {
  const [testo, tipo] = ACCESSI[r.accesso] || [r.accesso, ""];
  return el("div", { class: "riga registro-voce" },
    el("div", { class: "riga-corpo" },
      el("div", { class: "registro-testa" }, el("span", { class: "muto piccolo" }, quando(r.quando)), pill(testo, tipo), esito(r.esito)),
      el("div", { class: "riga-titolo" }, r.descrizione),
      (r.dettagli || []).length ? el("dl", { class: "registro-dettagli" }, r.dettagli.map(([etichetta, valore]) =>
        el("div", { class: etichetta === "Motivo" ? "registro-motivo" : null }, el("dt", {}, etichetta), el("dd", {}, valore)))) : null));
}

export default async function registro(root) {
  const filtro = el("select", { class: "input", "aria-label": "Accesso" },
    el("option", { value: "" }, "Tutti gli accessi"),
    ...Object.entries(ACCESSI).map(([v, [t]]) => el("option", { value: v }, t)));
  const lista = gruppo();
  const altre = el("button", { class: "btn btn-blocco", type: "button", hidden: true }, "Carica le precedenti");
  const box = el("div", {}, caricamento());
  let ultimo = null;
  const carica = async (dacapo) => {
    altre.disabled = true;
    try {
      if (dacapo) { ultimo = null; monta(lista); }
      const righe = await api.registro({ accesso: filtro.value, prima_di: ultimo, limite: PAGINA });
      lista.append(...righe.map(voce));
      if (righe.length) ultimo = righe[righe.length - 1].id;
      altre.hidden = righe.length < PAGINA;
      monta(box, lista.children.length ? lista : avviso("Nessuna azione registrata."));
    } catch (e) {
      monta(box, avviso(e.message, "errore"));
    } finally {
      altre.disabled = false;
    }
  };
  filtro.addEventListener("change", () => carica(true).catch(mostraErrore));
  altre.addEventListener("click", () => carica(false).catch(mostraErrore));
  root.append(testata("Registro", { sotto: "Le modifiche fatte, con la password usata", indietro: () => { location.hash = "#/altro"; } }),
    el("div", { class: "contenuto" }, filtro, box, altre));
  await carica(true);
}
