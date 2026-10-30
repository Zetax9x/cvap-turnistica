// Vista "Personale": elenco, aggiunta, modifica in linea, disattivazione/eliminazione, ferie.

import { api } from "./api.js";
import { el, clear, toast, toastErrore, chiediConferma, etichetta, dataEstesa, todayISO, badgeAssenza } from "./util.js";

const stato = {
  root: null,
  persone: [],
  ferie: [],
  filtroTipo: "tutti",
  mostraInattivi: true,
  inModifica: null, // id persona in modifica
};

export async function mostra(root) {
  stato.root = root;
  if (!stato.persone.length) clear(root).append(el("p", { class: "muted loading" }, "Caricamento del personale…"));
  try {
    [stato.persone, stato.ferie] = await Promise.all([api.persone(), api.ferie()]);
    render();
  } catch (err) {
    clear(root).append(el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare il personale. "), err.message));
  }
}

async function ricarica() {
  [stato.persone, stato.ferie] = await Promise.all([api.persone(), api.ferie()]);
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

const DESCR_AUTISTA_PROG = "Può fare l’autista nei Programmati anche se è soccorritore";

function checkAutistaProg(id, valore) {
  return el("input", { id, type: "checkbox", name: "autista_programmati", checked: !!valore });
}

function render() {
  const root = clear(stato.root);
  root.append(el("header", { class: "view-header" },
    el("h1", {}, "Personale"),
    el("p", { class: "muted" }, "Gli autisti possono coprire sia il ruolo di autista sia quello di soccorritore. ",
      "Con “Autista programmati” un soccorritore può fare l’autista anche nei Programmati.")));

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
  } else {
    root.append(renderTabella(elenco));
  }
  root.append(renderFerie());
}

function renderTabella(elenco) {
  const tbody = el("tbody", {}, elenco.map((p) => (stato.inModifica === p.id ? rigaModifica(p) : rigaLettura(p))));
  const tabella = el("table", { class: "tabella tabella-persone" },
    el("caption", { class: "sr-only" }, "Elenco del personale"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Nome"),
      el("th", { scope: "col" }, "Tipo"),
      el("th", { scope: "col" }, "Qualifica"),
      el("th", { scope: "col", title: DESCR_AUTISTA_PROG }, "Autista programmati"),
      el("th", { scope: "col" }, "Email"),
      el("th", { scope: "col" }, "Stato"),
      el("th", { scope: "col", class: "azioni" }, "Azioni"))),
    tbody);
  ruoliTabella(tabella);
  return el("div", { class: "table-scroll" }, tabella);
}

/** Ruoli espliciti: sul telefono la tabella diventa un elenco di schede (display flex) e alcuni
 *  browser (Safari) altrimenti perdono la struttura di tabella per i lettori di schermo. */
function ruoliTabella(tabella) {
  tabella.setAttribute("role", "table");
  for (const gruppo of tabella.querySelectorAll("thead, tbody")) gruppo.setAttribute("role", "rowgroup");
  for (const riga of tabella.querySelectorAll("tr")) riga.setAttribute("role", "row");
  for (const th of tabella.querySelectorAll("thead th")) th.setAttribute("role", "columnheader");
  for (const th of tabella.querySelectorAll("tbody th")) th.setAttribute("role", "rowheader");
  for (const td of tabella.querySelectorAll("td")) td.setAttribute("role", "cell");
}

function renderFormNuova() {
  const nome = el("input", { id: "nuova-nome", name: "nome", type: "text", required: true, autocomplete: "off", maxlength: "100" });
  const tipo = selectTipo("nuova-tipo", "dipendente");
  const qual = selectQualifica("nuova-qualifica", "soccorritore");
  const autProg = checkAutistaProg("nuova-autista-prog", false);
  const email = el("input", { id: "nuova-email", name: "email", type: "email", autocomplete: "off", maxlength: "254",
    placeholder: "facoltativa" });
  const invia = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi persona");
  return el("form", {
    class: "card form-inline", "aria-labelledby": "titolo-nuova",
    onsubmit: async (e) => {
      e.preventDefault();
      const valore = nome.value.trim();
      if (!valore) { nome.focus(); toast("Inserisci il nome.", "avviso"); return; }
      invia.disabled = true;
      try {
        const p = await api.creaPersona({
          nome: valore, tipo: tipo.value, qualifica: qual.value, autista_programmati: autProg.checked,
          email: email.value.trim(),
        });
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
    el("div", { class: "campo campo-largo" }, el("label", { for: "nuova-email" }, "Email (per ricevere i turni)"), email),
    el("div", { class: "campo campo-check" },
      el("label", { class: "check", for: "nuova-autista-prog", title: DESCR_AUTISTA_PROG }, autProg, " Autista programmati")),
    el("div", { class: "campo campo-azione" }, invia)));
}

function rigaLettura(p) {
  return el("tr", { class: p.attivo ? null : "inattivo" },
    el("th", { scope: "row" }, p.nome),
    el("td", {}, el("span", { class: `badge badge-${p.tipo}` }, etichetta("tipo", p.tipo))),
    el("td", {}, etichetta("qualifica", p.qualifica)),
    el("td", {}, p.autista_programmati
      ? el("span", { class: "badge badge-programmati", title: DESCR_AUTISTA_PROG }, "Sì")
      : el("span", { class: "muted" }, "No")),
    el("td", { class: "cella-email" }, p.email || el("span", { class: "muted" }, "—")),
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
  const autProg = checkAutistaProg(`${pre}-autista-prog`, p.autista_programmati);
  const email = el("input", { id: `${pre}-email`, type: "email", value: p.email || "", maxlength: "254",
    "aria-label": "Email", placeholder: "email" });

  const salva = async () => {
    const valore = nome.value.trim();
    if (!valore) { nome.focus(); toast("Il nome non può essere vuoto.", "avviso"); return; }
    try {
      await api.aggiornaPersona(p.id, {
        nome: valore, tipo: tipo.value, qualifica: qual.value, attivo: attivo.checked,
        autista_programmati: autProg.checked, email: email.value.trim(),
      });
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
    el("td", {}, el("label", { class: "check", for: `${pre}-autista-prog`, title: DESCR_AUTISTA_PROG }, autProg, " Autista programmati")),
    el("td", {}, email),
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
    await api.aggiornaPersona(p.id, {
      nome: p.nome, tipo: p.tipo, qualifica: p.qualifica, attivo,
      autista_programmati: !!p.autista_programmati,
    });
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

// ---------------------------------------------------------------- ferie

function giorniTra(dal, al) {
  return Math.round((Date.parse(al) - Date.parse(dal)) / 86400000) + 1;
}

function renderFerie() {
  const dipendenti = stato.persone.filter((p) => p.tipo === "dipendente" && p.attivo)
    .sort((a, b) => a.nome.localeCompare(b.nome, "it"));
  const nomi = new Map(stato.persone.map((p) => [p.id, p.nome]));
  const oggi = todayISO();

  const persona = el("select", { id: "ferie-persona", required: true },
    el("option", { value: "" }, "— Seleziona —"),
    dipendenti.map((p) => el("option", { value: String(p.id) }, p.nome)));
  const dal = el("input", { id: "ferie-dal", type: "date", required: true });
  const al = el("input", { id: "ferie-al", type: "date", required: true });
  const motivo = el("select", { id: "ferie-motivo" },
    el("option", { value: "ferie" }, "Ferie"),
    el("option", { value: "malattia" }, "Malattia o infortunio"));
  dal.addEventListener("change", () => { if (dal.value && (!al.value || al.value < dal.value)) al.value = dal.value; });
  const invia = el("button", { type: "submit", class: "btn btn-primary", disabled: !dipendenti.length }, "Aggiungi");

  const form = el("form", {
    class: "campi",
    onsubmit: async (e) => {
      e.preventDefault();
      if (!persona.value || !dal.value || !al.value) { toast("Indica dipendente, dal e al.", "avviso"); return; }
      invia.disabled = true;
      try {
        await api.creaFerie({ persona_id: Number(persona.value), dal: dal.value, al: al.value, motivo: motivo.value });
        toast(motivo.value === "malattia" ? "Malattia aggiunta." : "Ferie aggiunte.", "ok");
        await ricarica();
      } catch (err) {
        toastErrore(err);
        invia.disabled = false;
      }
    },
  },
  el("div", { class: "campo campo-largo" }, el("label", { for: "ferie-persona" }, "Dipendente"), persona),
  el("div", { class: "campo" }, el("label", { for: "ferie-motivo" }, "Motivo"), motivo),
  el("div", { class: "campo" }, el("label", { for: "ferie-dal" }, "Dal"), dal),
  el("div", { class: "campo" }, el("label", { for: "ferie-al" }, "Al (incluso)"), al),
  el("div", { class: "campo campo-azione" }, invia));

  const tabella = (lista) => el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Dipendente"),
      el("th", { scope: "col" }, "Motivo"),
      el("th", { scope: "col" }, "Dal"),
      el("th", { scope: "col" }, "Al"),
      el("th", { scope: "col", class: "num" }, "Giorni"),
      el("th", { scope: "col", class: "azioni" }, "Azioni"))),
    el("tbody", {}, lista.map((f) => {
      const nome = nomi.get(f.persona_id) || `#${f.persona_id}`;
      return el("tr", {},
        el("th", { scope: "row" }, nome),
        el("td", {}, badgeAssenza(f.motivo)),
        el("td", {}, dataEstesa(f.dal)),
        el("td", {}, dataEstesa(f.al)),
        el("td", { class: "num" }, String(giorniTra(f.dal, f.al))),
        el("td", { class: "azioni" }, el("button", {
          type: "button", class: "btn btn-small btn-danger", "aria-label": `Elimina ${f.motivo === "malattia" ? "malattia" : "ferie"} di ${nome} dal ${f.dal}`,
          onclick: () => eliminaFerie(f, nome),
        }, "Elimina")));
    }))));

  const correnti = stato.ferie.filter((f) => f.al >= oggi);
  const passate = stato.ferie.filter((f) => f.al < oggi).reverse();
  return el("section", { class: "card", "aria-labelledby": "titolo-ferie" },
    el("h2", { id: "titolo-ferie", class: "card-title" }, "Ferie e malattia"),
    el("p", { class: "muted" },
      "Nei giorni di ferie o di malattia/infortunio il dipendente non riceve turni e ogni giorno conta 6 ore nel confronto tra le ore dei dipendenti. ",
      "Le ore che mancano non vanno recuperate nelle settimane successive. Il motivo serve solo a distinguerle."),
    form,
    correnti.length ? tabella(correnti) : el("p", { class: "muted" }, "Nessuna ferie o malattia in corso o in programma."),
    passate.length ? el("details", { class: "ferie-passate" },
      el("summary", {}, `Passate (${passate.length})`), tabella(passate)) : null);
}

async function eliminaFerie(f, nome) {
  const cosa = f.motivo === "malattia" ? "la malattia" : "le ferie";
  const ok = await chiediConferma(`Eliminare ${cosa} di ${nome} dal ${dataEstesa(f.dal)} al ${dataEstesa(f.al)}?`,
    { titolo: `Eliminare ${cosa}?`, ok: "Elimina", pericolo: true });
  if (!ok) return;
  try {
    await api.eliminaFerie(f.id);
    toast(f.motivo === "malattia" ? "Malattia eliminata." : "Ferie eliminate.", "ok");
    await ricarica();
  } catch (err) {
    toastErrore(err);
  }
}
