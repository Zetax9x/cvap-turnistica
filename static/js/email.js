// Invio dei turni via email: finestra con i destinatari, invio a tutti o solo le modifiche, email di prova.

import { api } from "./api.js";
import { el, clear, toast, toastErrore } from "./util.js";

const CHIAVE_PROVA = "cvap.emailProva";
const STATI = {
  da_inviare: { testo: "da inviare", classe: "badge-avviso" },
  inviata: { testo: "già inviata", classe: "badge-confermata" },
  cambiata: { testo: "turni cambiati", classe: "badge-bozza" },
};

let dialog = null;

function finestra() {
  if (!dialog) {
    dialog = el("dialog", { class: "dialog dialog-email", "aria-labelledby": "email-titolo" });
    document.body.appendChild(dialog);
  }
  return clear(dialog);
}

function testa(d, titolo, sotto) {
  d.append(el("div", { class: "dialog-head" },
    el("h2", { id: "email-titolo", class: "dialog-title" }, titolo),
    sotto ? el("p", { class: "muted" }, sotto) : null,
    el("button", { type: "button", class: "dialog-x", "aria-label": "Chiudi", onclick: () => d.close() }, "×")));
}

const NON_CONFIGURATO = "L'invio non è ancora configurato: servono i dati del servizio di posta "
  + "(SMTP_HOST, SMTP_USER, SMTP_PASSWORD…) nelle impostazioni del server.";

/** Finestra "Invia i turni via email" per la settimana che inizia `data`. */
export async function apriInvio(data) {
  let info;
  try {
    info = await api.statoEmail(data);
  } catch (err) {
    toastErrore(err);
    return;
  }
  const d = finestra();
  testa(d, "Invia i turni via email",
    "Ognuno riceve i propri turni e il tabellone completo della settimana.");

  if (!info.configurato) {
    d.append(el("div", { class: "banner banner-info" }, info.motivo || NON_CONFIGURATO));
  }
  const lista = info.destinatari;
  const daMandare = lista.filter((x) => x.stato !== "inviata");
  if (lista.length) {
    d.append(el("section", { class: "dialog-section" },
      el("h3", {}, `Destinatari (${lista.length})`),
      el("ul", { class: "lista-email" }, lista.map((x) => el("li", {},
        el("span", { class: "libero-nome" }, x.nome),
        el("span", { class: "muted email-indirizzo" }, x.email),
        el("span", { class: `badge ${STATI[x.stato].classe}` }, STATI[x.stato].testo))))));
  } else {
    d.append(el("p", { class: "dialog-text" }, "Nessuno ha ancora un indirizzo email: aggiungilo in Personale."));
  }
  if (info.senza_email.length) {
    d.append(el("section", { class: "dialog-section" },
      el("h3", {}, `Senza email (${info.senza_email.length})`),
      el("p", { class: "muted" }, `${info.senza_email.join(", ")}. Non riceveranno nulla: aggiungi l'email in Personale.`)));
  }

  const azioni = el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Annulla"));
  const puoInviare = info.configurato && info.stato_settimana === "confermata";
  const parziale = daMandare.length && daMandare.length < lista.length;
  if (parziale) {
    azioni.append(el("button", {
      type: "button", class: "btn btn-primary", disabled: !puoInviare,
      onclick: () => invia(d, data, true),
    }, `Invia solo modifiche e mancanti (${daMandare.length})`));
  }
  azioni.append(el("button", {
    type: "button", class: parziale ? "btn" : "btn btn-primary", disabled: !puoInviare || !lista.length,
    onclick: () => invia(d, data, false),
  }, `Invia a tutti (${lista.length})`));
  d.append(azioni);
  d.showModal();
}

async function invia(d, data, soloModifiche) {
  for (const b of d.querySelectorAll("button")) b.disabled = true;
  const stato = el("p", { class: "dialog-text", role: "status" }, "Invio in corso…");
  d.append(stato);
  let esito;
  try {
    esito = await api.inviaEmail(data, soloModifiche);
  } catch (err) {
    d.close();
    toastErrore(err);
    return;
  }
  clear(d);
  testa(d, esito.errori.length ? "Invio completato con errori" : "Email inviate");
  d.append(el("p", { class: "dialog-text" },
    esito.inviate.length ? `Inviate a ${esito.inviate.length}: ${esito.inviate.map((x) => x.nome).join(", ")}.`
      : "Nessuna email da inviare."));
  if (esito.errori.length) {
    d.append(el("section", { class: "dialog-section" },
      el("h3", {}, `Non inviate (${esito.errori.length})`),
      el("ul", { class: "lista-email" }, esito.errori.map((x) => el("li", {},
        el("span", { class: "libero-nome" }, x.nome), el("span", { class: "muted email-indirizzo" }, x.email),
        el("span", { class: "email-errore" }, x.errore))))));
  }
  d.append(el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn btn-primary", onclick: () => d.close() }, "Chiudi")));
  toast(esito.errori.length ? `${esito.errori.length} email non inviate.` : "Email inviate.",
    esito.errori.length ? "avviso" : "ok");
}

/** Finestra "Invia una prova a me": l'email com'è, mandata a un indirizzo scelto. */
export function apriProva(data) {
  const d = finestra();
  testa(d, "Invia una prova", "Ricevi l'email esattamente come la riceverà il personale, prima di mandarla a tutti.");
  let salvato = "";
  try { salvato = localStorage.getItem(CHIAVE_PROVA) || ""; } catch { /* ignora */ }
  const input = el("input", { id: "email-prova", type: "email", required: true, value: salvato, autocomplete: "email" });
  const bottone = el("button", { type: "submit", class: "btn btn-primary" }, "Invia la prova");
  const form = el("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      const indirizzo = input.value.trim();
      if (!indirizzo) { input.focus(); return; }
      bottone.disabled = true;
      try {
        const r = await api.provaEmail(data, indirizzo);
        try { localStorage.setItem(CHIAVE_PROVA, indirizzo); } catch { /* ignora */ }
        d.close();
        toast(`Prova inviata a ${r.inviata_a} (come la riceverà ${r.esempio}).`, "ok");
      } catch (err) {
        toastErrore(err);
        bottone.disabled = false;
      }
    },
  },
  el("div", { class: "campo campo-largo" }, el("label", { for: "email-prova" }, "Il tuo indirizzo email"), input),
  el("div", { class: "dialog-actions" },
    el("button", { type: "button", class: "btn", onclick: () => d.close() }, "Annulla"), bottone));
  d.append(form);
  d.showModal();
  input.focus();
}
