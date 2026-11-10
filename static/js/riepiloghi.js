// Impostazioni → "Riepiloghi via email": indirizzi in più (responsabili, segreteria…) e cosa ricevono.

import { api } from "./api.js";
import { el, clear, toast, toastErrore, chiediConferma, mondayOf, todayISO, dataLunga, ddmm, addDays } from "./util.js";

export const CONTENUTI = [
  ["turni", "Turni della settimana", "Turni"],
  ["liberi", "Liberi", "Liberi"],
  ["indisponibilita", "Indisponibilità della settimana", "Indisp."],
  ["statistiche", "Statistiche dei turni", "Statistiche"],
  ["statistiche_indisponibilita", "Statistiche delle indisponibilità", "Stat. indisp."],
];
const DESCR_RESPONSABILE = "Riceve turni e liberi anche quando premi “Invia i turni via email” nella settimana";

let sezione = null;
let elenco = [];
let settimana = mondayOf(todayISO());

/** Carica e disegna la sezione dentro `contenitore` (una <section> della pagina Impostazioni). */
export async function mostraRiepiloghi(contenitore) {
  sezione = contenitore;
  try {
    elenco = await api.destinatari();
  } catch (err) {
    clear(sezione).append(el("p", { class: "banner banner-errore" }, `Indirizzi non caricati: ${err.message}`));
    return;
  }
  render();
}

async function ricarica() {
  elenco = await api.destinatari();
  render();
}

function spunte(prefisso, scelti, onchange) {
  return CONTENUTI.map(([valore, etichetta]) => el("input", {
    type: "checkbox", id: `${prefisso}-${valore}`, value: valore, checked: scelti.includes(valore),
    "aria-label": etichetta, onchange,
  }));
}

function render() {
  const s = clear(sezione);
  s.append(
    el("h2", { id: "titolo-riepiloghi", class: "card-title" }, "Riepiloghi via email"),
    el("p", { class: "muted" },
      "Indirizzi in più (responsabili, segreteria…) e per ognuno cosa ricevere. Con “Invia i riepiloghi” ognuno riceve ",
      "un'email con le parti spuntate. Chi ha “Responsabile” riceve anche turni e liberi ogni volta che invii i turni ",
      "della settimana al personale."),
  );
  if (elenco.length) s.append(renderTabella());
  else s.append(el("p", { class: "muted" }, "Nessun indirizzo: aggiungi il primo qui sotto."));
  s.append(renderAggiungi(), renderInvio());
}

function renderTabella() {
  return el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-riepiloghi" },
    el("caption", { class: "sr-only" }, "Indirizzi dei riepiloghi e contenuti scelti"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Email"),
      el("th", { scope: "col" }, "Nome"),
      CONTENUTI.map(([, etichetta, breve]) => el("th", { scope: "col", class: "col-spunta", title: etichetta }, breve)),
      el("th", { scope: "col", class: "col-spunta", title: DESCR_RESPONSABILE }, "Responsabile"),
      el("th", { scope: "col", class: "azioni" }, ""))),
    el("tbody", {}, elenco.map(rigaDestinatario))));
}

function rigaDestinatario(d) {
  const pre = `dest-${d.id}`;
  const email = el("input", { type: "email", id: `${pre}-email`, value: d.email, maxlength: "254", "aria-label": "Email" });
  const nome = el("input", { type: "text", id: `${pre}-nome`, value: d.nome || "", maxlength: "100", "aria-label": "Nome",
    placeholder: "facoltativo" });
  const caselle = spunte(pre, d.contenuti, () => salva());
  const resp = el("input", { type: "checkbox", id: `${pre}-resp`, checked: d.responsabile,
    "aria-label": "Responsabile", title: DESCR_RESPONSABILE, onchange: () => salva() });

  async function salva() {
    const contenuti = caselle.filter((c) => c.checked).map((c) => c.value);
    if (!contenuti.length) {
      toast("Lascia almeno un contenuto spuntato (o elimina l'indirizzo).", "avviso");
      await ricarica();
      return;
    }
    try {
      // salvato: si aggiorna solo il dato in memoria, senza ridisegnare (il cursore resta dov'è)
      const nuovo = await api.aggiornaDestinatario(d.id, { email: email.value.trim(), nome: nome.value.trim() || null,
        contenuti, responsabile: resp.checked });
      elenco = elenco.map((x) => (x.id === d.id ? nuovo : x));
      Object.assign(d, nuovo);
      toast("Salvato.", "ok", 2500);
    } catch (err) {
      toastErrore(err);
      await ricarica();
    }
  }
  email.addEventListener("change", salva);
  nome.addEventListener("change", salva);

  return el("tr", {},
    el("td", {}, email),
    el("td", {}, nome),
    caselle.map((c) => el("td", { class: "col-spunta" }, c)),
    el("td", { class: "col-spunta" }, resp),
    el("td", { class: "azioni" }, el("button", {
      type: "button", class: "btn btn-small btn-danger", "aria-label": `Elimina ${d.email}`,
      onclick: async () => {
        const ok = await chiediConferma(`Togliere ${d.email} dai riepiloghi?`, { titolo: "Eliminare l'indirizzo?", ok: "Elimina", pericolo: true });
        if (!ok) return;
        try { await api.eliminaDestinatario(d.id); toast("Indirizzo eliminato.", "ok"); await ricarica(); } catch (err) { toastErrore(err); }
      },
    }, "Elimina")));
}

function renderAggiungi() {
  const email = el("input", { type: "email", id: "nuovo-dest-email", required: true, maxlength: "254", autocomplete: "off" });
  const nome = el("input", { type: "text", id: "nuovo-dest-nome", maxlength: "100", placeholder: "facoltativo" });
  const caselle = spunte("nuovo-dest", ["turni", "liberi"]);
  const resp = el("input", { type: "checkbox", id: "nuovo-dest-resp" });
  const bottone = el("button", { type: "submit", class: "btn btn-primary" }, "Aggiungi indirizzo");
  return el("form", {
    class: "riepiloghi-nuovo",
    onsubmit: async (e) => {
      e.preventDefault();
      const contenuti = caselle.filter((c) => c.checked).map((c) => c.value);
      if (!email.value.trim()) { email.focus(); return; }
      if (!contenuti.length) { toast("Scegli almeno un contenuto.", "avviso"); return; }
      bottone.disabled = true;
      try {
        await api.creaDestinatario({ email: email.value.trim(), nome: nome.value.trim() || null, contenuti,
          responsabile: resp.checked });
        toast("Indirizzo aggiunto.", "ok");
        await ricarica();
      } catch (err) {
        toastErrore(err);
        bottone.disabled = false;
      }
    },
  },
  el("h3", {}, "Nuovo indirizzo"),
  el("div", { class: "campi" },
    el("div", { class: "campo campo-largo" }, el("label", { for: "nuovo-dest-email" }, "Email"), email),
    el("div", { class: "campo" }, el("label", { for: "nuovo-dest-nome" }, "Nome"), nome)),
  el("fieldset", { class: "riepiloghi-spunte" },
    el("legend", {}, "Cosa ricevere"),
    CONTENUTI.map(([valore, etichetta], i) => el("label", { class: "check", for: caselle[i].id }, caselle[i], ` ${etichetta}`)),
    el("label", { class: "check", for: "nuovo-dest-resp", title: DESCR_RESPONSABILE }, resp,
      " Responsabile (riceve turni e liberi con l'invio della settimana)")),
  el("div", { class: "form-actions" }, bottone));
}

function renderInvio() {
  const data = el("input", { type: "date", id: "riepiloghi-settimana", value: settimana,
    onchange: (e) => { if (e.target.value) { settimana = mondayOf(e.target.value); descr.textContent = periodo(); } } });
  const periodo = () => `dal ${ddmm(settimana)} al ${dataLunga(addDays(settimana, 6))}`;
  const descr = el("span", { class: "muted" }, periodo());
  const bottone = el("button", {
    type: "button", class: "btn btn-primary btn-grande", disabled: !elenco.length,
    onclick: async () => {
      const ok = await chiediConferma(`Inviare i riepiloghi della settimana ${periodo()} a ${elenco.length} `
        + `${elenco.length === 1 ? "indirizzo" : "indirizzi"}?`, { titolo: "Inviare i riepiloghi?", ok: "Invia" });
      if (!ok) return;
      bottone.disabled = true;
      try {
        const r = await api.inviaRiepiloghi(settimana);
        if (r.errori.length) {
          toast(`Inviati ${r.inviate.length}; non inviati: ${r.errori.map((x) => `${x.email} (${x.errore})`).join(", ")}.`, "avviso", 12000);
        } else {
          toast(`Riepiloghi inviati a ${r.inviate.length} ${r.inviate.length === 1 ? "indirizzo" : "indirizzi"}.`, "ok");
        }
      } catch (err) {
        toastErrore(err);
      } finally {
        bottone.disabled = false;
      }
    },
  }, "Invia i riepiloghi");
  return el("div", { class: "riepiloghi-invio" },
    el("h3", {}, "Invia"),
    el("div", { class: "campi" },
      el("div", { class: "campo" }, el("label", { for: "riepiloghi-settimana" }, "Settimana"), data),
      el("div", { class: "campo" }, descr),
      el("div", { class: "campo campo-azione" }, bottone)));
}
