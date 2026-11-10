// Vista "Registro" (solo accesso master): tutte le modifiche fatte dal sito, con quale password e l'esito.

import { api } from "./api.js";
import { el } from "./util.js";

const PAGINA = 200;
const ACCESSI = {
  normale: { testo: "Normale", classe: "badge-nuova" },
  master: { testo: "Master", classe: "badge-dipendente" },
  pubblico: { testo: "Dipendente", classe: "badge-nuova" },
  aperto: { testo: "Senza password", classe: "badge-nuova" },
  anonimo: { testo: "Sconosciuto", classe: "badge-errore" },
};

function quando(iso) {
  const d = new Date(iso);
  return `${d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" })} `
    + d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function esito(codice) {
  if (codice < 300) return el("span", { class: "badge badge-confermata" }, "Fatto");
  if (codice === 401) return el("span", { class: "badge badge-errore" }, "Rifiutato");
  return el("span", { class: "badge badge-avviso", title: `Codice ${codice}` }, "Non riuscito");
}

function riga(r) {
  const a = ACCESSI[r.accesso] || { testo: r.accesso, classe: "badge-nuova" };
  return el("tr", {},
    el("td", { class: "registro-quando" }, quando(r.quando)),
    el("td", {}, el("span", { class: `badge ${a.classe}` }, a.testo)),
    el("td", {}, r.descrizione, el("div", { class: "registro-percorso muted" }, `${r.metodo} ${r.percorso}`)),
    el("td", {}, esito(r.esito)));
}

export async function mostra(root) {
  const filtro = el("select", { id: "registro-accesso" },
    el("option", { value: "" }, "Tutti gli accessi"),
    ...Object.entries(ACCESSI).map(([valore, a]) => el("option", { value: valore }, a.testo)));
  const corpo = el("tbody");
  const messaggio = el("p", { class: "muted", role: "status" });
  const altre = el("button", { type: "button", class: "btn btn-secondary", hidden: true }, "Carica le precedenti");
  let ultimo = null;

  const carica = async (dacapo) => {
    altre.disabled = true;
    try {
      if (dacapo) { ultimo = null; corpo.replaceChildren(); }
      const righe = await api.registro({ accesso: filtro.value, prima_di: ultimo, limite: PAGINA });
      corpo.append(...righe.map(riga));
      if (righe.length) ultimo = righe[righe.length - 1].id;
      altre.hidden = righe.length < PAGINA;
      messaggio.textContent = corpo.children.length ? "" : "Nessuna azione registrata.";
    } catch (err) {
      messaggio.textContent = err.message;
    } finally {
      altre.disabled = false;
    }
  };
  filtro.addEventListener("change", () => carica(true));
  altre.addEventListener("click", () => carica(false));

  root.replaceChildren(
    el("header", { class: "view-header" },
      el("h1", {}, "Registro delle azioni"),
      el("p", {}, "Tutte le modifiche fatte dal sito, dalla più recente, con la password usata: "
        + "normale, master, o i dipendenti dalla pagina dei cambi turno. Le sole consultazioni non compaiono.")),
    el("div", { class: "registro-filtri" }, el("label", { for: "registro-accesso" }, "Accesso"), filtro),
    el("div", { class: "registro-tabella" },
      el("table", { class: "tabella" },
        el("thead", {}, el("tr", {}, el("th", {}, "Quando"), el("th", {}, "Accesso"), el("th", {}, "Azione"),
          el("th", {}, "Esito"))),
        corpo)),
    messaggio, altre);
  await carica(true);
}
