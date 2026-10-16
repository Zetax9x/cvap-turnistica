// Vista "Personale": elenco, aggiunta, modifica in linea, disattivazione/eliminazione.

import { api } from "./api.js";
import { el, clear, toast, toastErrore, chiediConferma, etichetta } from "./util.js";

const stato = {
  root: null,
  persone: [],
  filtroTipo: "tutti",
  mostraInattivi: true,
  inModifica: null, // id persona in modifica
};

export async function mostra(root) {
  stato.root = root;
  if (!stato.persone.length) clear(root).append(el("p", { class: "muted loading" }, "Caricamento del personale…"));
  try {
    stato.persone = await api.persone();
    render();
  } catch (err) {
    clear(root).append(el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare il personale. "), err.message));
  }
}

async function ricarica() {
  stato.persone = await api.persone();
  render();
}

function selectTipo(id, valore) {
  return el("select", { id, name: "tipo", required: true },
    ["dipendente", "volontario"].map((t) => el("option", { value: t, selected: t === valore }, etichetta("tipo", t))));
}

function selectQualifica(id, valore) {
  return el("select", { id, name: "qualifica", required: true },
    ["autista", "soccorritore"].map((q) => el("option", { value: q, selected: q === valore }, etichetta("qualifica", q))));
}

function render() {
  const root = clear(stato.root);
  root.append(el("header", { class: "view-header" },
    el("h1", {}, "Personale"),
    el("p", { class: "muted" }, "Gli autisti possono coprire sia il ruolo di autista sia quello di soccorritore.")));

  root.append(renderFormNuova());

  // Filtri
  const conteggi = { tutti: 0, dipendente: 0, volontario: 0 };
  for (const p of stato.persone) {
    if (!stato.mostraInattivi && !p.attivo) continue;
    conteggi.tutti++; conteggi[p.tipo] = (conteggi[p.tipo] || 0) + 1;
  }
  const filtri = el("div", { class: "filtri", role: "group", "aria-label": "Filtra per tipo" },
    [["tutti", "Tutti"], ["dipendente", "Dipendenti"], ["volontario", "Volontari"]].map(([v, t]) =>
      el("button", {
        type: "button", class: `btn btn-filter${stato.filtroTipo === v ? " attivo" : ""}`,
        "aria-pressed": stato.filtroTipo === v ? "true" : "false",
        onclick: () => { stato.filtroTipo = v; render(); },
      }, `${t} (${conteggi[v] || 0})`)),
    el("label", { class: "check" },
      el("input", { type: "checkbox", checked: stato.mostraInattivi, onchange: (e) => { stato.mostraInattivi = e.target.checked; render(); } }),
      " Mostra non attivi"));
  root.append(filtri);

  const elenco = stato.persone
    .filter((p) => stato.filtroTipo === "tutti" || p.tipo === stato.filtroTipo)
    .filter((p) => stato.mostraInattivi || p.attivo)
    .sort((a, b) => (b.attivo - a.attivo) || a.nome.localeCompare(b.nome, "it"));

  if (!elenco.length) {
    root.append(el("p", { class: "muted" }, stato.persone.length ? "Nessuna persona corrisponde al filtro." : "Nessuna persona registrata. Aggiungi la prima con il modulo qui sopra."));
    return;
  }

  const tbody = el("tbody", {}, elenco.map((p) => (stato.inModifica === p.id ? rigaModifica(p) : rigaLettura(p))));
  root.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-persone" },
    el("caption", { class: "sr-only" }, "Elenco del personale"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Nome"),
      el("th", { scope: "col" }, "Tipo"),
      el("th", { scope: "col" }, "Qualifica"),
      el("th", { scope: "col" }, "Stato"),
      el("th", { scope: "col", class: "azioni" }, "Azioni"))),
    tbody)));
}

function renderFormNuova() {
  const nome = el("input", { id: "nuova-nome", name: "nome", type: "text", required: true, autocomplete: "off", maxlength: "100" });
  const tipo = selectTipo("nuova-tipo", "dipendente");
  const qual = selectQualifica("nuova-qualifica", "soccorritore");
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi persona");
  return el("form", {
    class: "card form-inline", "aria-labelledby": "titolo-nuova",
    onsubmit: async (e) => {
      e.preventDefault();
      const valore = nome.value.trim();
      if (!valore) { nome.focus(); toast("Inserisci il nome.", "avviso"); return; }
      invia.disabled = true;
      try {
        const p = await api.creaPersona({ nome: valore, tipo: tipo.value, qualifica: qual.value });
        toast(`${p && p.nome ? p.nome : valore} aggiunto.`, "ok");
        await ricarica();
        const n = document.getElementById("nuova-nome");
        if (n) n.focus();
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
      }
    },
  },
  el("h2", { id: "titolo-nuova", class: "card-title" }, "Nuova persona"),
  el("div", { class: "campi" },
    el("div", { class: "campo campo-largo" }, el("label", { for: "nuova-nome" }, "Nome e cognome"), nome),
    el("div", { class: "campo" }, el("label", { for: "nuova-tipo" }, "Tipo"), tipo),
    el("div", { class: "campo" }, el("label", { for: "nuova-qualifica" }, "Qualifica"), qual),
    el("div", { class: "campo campo-azione" }, invia)));
}

function rigaLettura(p) {
  return el("tr", { class: p.attivo ? null : "inattivo" },
    el("th", { scope: "row" }, p.nome),
    el("td", {}, el("span", { class: `badge badge-${p.tipo}` }, etichetta("tipo", p.tipo))),
    el("td", {}, etichetta("qualifica", p.qualifica)),
    el("td", {}, p.attivo ? el("span", { class: "badge badge-attivo" }, "Attivo") : el("span", { class: "badge badge-inattivo" }, "Non attivo")),
    el("td", { class: "azioni" },
      el("button", {
        type: "button", class: "btn btn-small", "aria-label": `Modifica ${p.nome}`,
        onclick: () => { stato.inModifica = p.id; render(); focusRiga(p.id); },
      }, "Modifica"),
      p.attivo
        ? el("button", { type: "button", class: "btn btn-small", "aria-label": `Disattiva ${p.nome}`, onclick: () => cambiaAttivo(p, false) }, "Disattiva")
        : el("button", { type: "button", class: "btn btn-small", "aria-label": `Riattiva ${p.nome}`, onclick: () => cambiaAttivo(p, true) }, "Riattiva"),
      el("button", { type: "button", class: "btn btn-small btn-danger", "aria-label": `Elimina ${p.nome}`, onclick: () => elimina(p) }, "Elimina")));
}

function rigaModifica(p) {
  const pre = `mod-${p.id}`;
  const nome = el("input", { id: `${pre}-nome`, type: "text", value: p.nome, required: true, maxlength: "100", "aria-label": "Nome" });
  const tipo = selectTipo(`${pre}-tipo`, p.tipo);
  tipo.setAttribute("aria-label", "Tipo");
  const qual = selectQualifica(`${pre}-qualifica`, p.qualifica);
  qual.setAttribute("aria-label", "Qualifica");
  const attivo = el("input", { id: `${pre}-attivo`, type: "checkbox", checked: !!p.attivo });

  const salva = async () => {
    const valore = nome.value.trim();
    if (!valore) { nome.focus(); toast("Il nome non può essere vuoto.", "avviso"); return; }
    try {
      await api.aggiornaPersona(p.id, { nome: valore, tipo: tipo.value, qualifica: qual.value, attivo: attivo.checked });
      stato.inModifica = null;
      toast("Modifiche salvate.", "ok");
      await ricarica();
    } catch (err) {
      toastErrore(err);
    }
  };
  const annulla = () => { stato.inModifica = null; render(); };
  const tasti = (e) => {
    if (e.key === "Enter" && e.target.tagName !== "BUTTON") { e.preventDefault(); salva(); }
    if (e.key === "Escape") { e.preventDefault(); annulla(); }
  };

  return el("tr", { class: "in-modifica", dataset: { id: String(p.id) }, onkeydown: tasti },
    el("td", {}, nome),
    el("td", {}, tipo),
    el("td", {}, qual),
    el("td", {}, el("label", { class: "check", for: `${pre}-attivo` }, attivo, " Attivo")),
    el("td", { class: "azioni" },
      el("button", { type: "button", class: "btn btn-small btn-primary", onclick: salva }, "Salva"),
      el("button", { type: "button", class: "btn btn-small", onclick: annulla }, "Annulla")));
}

function focusRiga(id) {
  const input = document.getElementById(`mod-${id}-nome`);
  if (input) { input.focus(); input.select(); }
}

async function cambiaAttivo(p, attivo) {
  try {
    await api.aggiornaPersona(p.id, { nome: p.nome, tipo: p.tipo, qualifica: p.qualifica, attivo });
    toast(attivo ? `${p.nome} riattivato.` : `${p.nome} disattivato.`, "ok");
    await ricarica();
  } catch (err) {
    toastErrore(err);
  }
}

async function elimina(p) {
  const ok = await chiediConferma(
    `Eliminare ${p.nome}? Se la persona ha già turni assegnati non verrà cancellata ma soltanto disattivata, per preservare lo storico.`,
    { titolo: "Eliminare la persona?", ok: "Elimina", pericolo: true });
  if (!ok) return;
  try {
    await api.eliminaPersona(p.id);
    await ricarica();
    const ancora = stato.persone.find((x) => x.id === p.id);
    toast(ancora ? `${p.nome} ha turni registrati: è stato disattivato.` : `${p.nome} eliminato.`, "ok");
  } catch (err) {
    toastErrore(err);
  }
}
