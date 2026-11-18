// Impostazioni → "Codici scheda ore": il codice personale con cui ogni dipendente apre la sua scheda ore
// (pagina /scheda-ore). Il codice non si rilegge mai: si imposta, si genera (mostrato una sola volta) o si azzera.

import { api } from "./api.js";
import { el, toast, toastErrore, chiediConferma } from "./util.js";

const LUNGHEZZA_PIN = 6;  // come LUNGHEZZA_PIN in cvap/db_schede_ore.py: il PIN è fatto di esattamente 6 cifre
const FORMATO_PIN = new RegExp(`^[0-9]{${LUNGHEZZA_PIN}}$`);

function meseCorrente() {
  const oggi = new Date();
  return `${oggi.getFullYear()}-${String(oggi.getMonth() + 1).padStart(2, "0")}`;
}

/** Il codice generato in un popup: si vede una volta sola, finché si chiude. */
function mostraCodiceGenerato(nome, codice) {
  return new Promise((risolvi) => {
    const d = el("dialog", { class: "dialog dialog-conferma", "aria-labelledby": "codice-generato-titolo" });
    const chiudi = el("button", { type: "button", class: "btn btn-primary", onclick: () => d.close() }, "Chiudi");
    const copia = el("button", { type: "button", class: "btn btn-secondary", onclick: async () => {
      try { await navigator.clipboard.writeText(codice); copia.textContent = "Copiato"; } catch { copia.textContent = "Copia non riuscita: selezionalo a mano"; }
    } }, "Copia");
    d.append(el("h2", { id: "codice-generato-titolo", class: "dialog-title" }, `PIN di ${nome}`),
      el("p", { class: "dialog-text" }, "Comunicalo al dipendente: questo è l'unico momento in cui si vede."),
      el("p", { class: "dialog-text" }, el("strong", { style: "font-size:1.6rem;letter-spacing:.15em;user-select:all" }, codice)),
      el("div", { class: "dialog-actions" }, copia, chiudi));
    d.addEventListener("close", () => { d.remove(); risolvi(); }, { once: true });
    document.body.append(d);
    d.showModal();
    chiudi.focus();
  });
}

function rigaDipendente(p, aggiorna) {
  const campo = el("input", { type: "text", inputmode: "numeric", pattern: "[0-9]*", id: `codice-${p.persona_id}`, autocomplete: "off",
    maxLength: LUNGHEZZA_PIN, placeholder: `${LUNGHEZZA_PIN} cifre`, "aria-label": `Nuovo PIN per ${p.nome}` });
  const esegui = async (azione, messaggio) => {
    try { await azione(); if (messaggio) toast(messaggio, "ok"); await aggiorna(); } catch (err) { toastErrore(err); }
  };
  const imposta = () => {
    if (!FORMATO_PIN.test(campo.value)) { toast(`Il PIN deve essere di ${LUNGHEZZA_PIN} cifre, solo numeri.`, "avviso"); campo.focus(); return; }
    const codice = campo.value;
    campo.value = "";
    return esegui(() => api.impostaCodiceScheda(p.persona_id, codice), `PIN di ${p.nome} impostato.`);
  };
  const genera = async () => {
    if (p.ha_codice && !await chiediConferma(`${p.nome} ha già un PIN: quello vecchio smetterà di funzionare.`,
      { titolo: "Generare un nuovo PIN?", ok: "Genera" })) return;
    try {
      const { codice } = await api.generaCodiceScheda(p.persona_id);
      await aggiorna();
      await mostraCodiceGenerato(p.nome, codice);
    } catch (err) { toastErrore(err); }
  };
  const azzera = async () => {
    if (!await chiediConferma(`${p.nome} non potrà più aprire la scheda ore finché non gli dai un nuovo PIN.`,
      { titolo: "Azzerare il PIN?", ok: "Azzera", pericolo: true })) return;
    await esegui(() => api.azzeraCodiceScheda(p.persona_id), `PIN di ${p.nome} azzerato.`);
  };
  return el("tr", {},
    el("th", { scope: "row" }, el("label", { for: campo.id }, p.nome)),
    el("td", {}, el("span", { class: `badge ${p.ha_codice ? "badge-confermata" : "badge-nuova"}` }, p.ha_codice ? "Impostato" : "Non impostato")),
    el("td", {}, campo, el("button", { type: "button", class: "btn btn-small", onclick: imposta }, "Imposta")),
    el("td", {}, el("button", { type: "button", class: "btn btn-small", onclick: genera }, "Genera PIN"),
      p.ha_codice ? el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: azzera }, "Azzera") : null));
}

/**
 * La sezione ripiegabile con l'elenco dei dipendenti e dei loro codici. `creaSezione` è `sezioneRipiegabile` di
 * impostazioni.js (così la sezione resta aperta o chiusa come l'ha lasciata l'utente dopo ogni ridisegno).
 */
export function renderCodiciScheda(creaSezione) {
  const corpo = el("div", {}, el("p", { class: "muted" }, "Caricamento…"));
  const sezione = creaSezione("imp-codici-scheda", "titolo-codici-scheda", "PIN scheda ore", "accesso dei dipendenti", corpo);
  const aggiorna = async () => {
    try {
      const elenco = await api.elencoSchedeOre(meseCorrente());
      const senza = elenco.filter((p) => !p.ha_codice).length;
      sezione.querySelector(".sezione-riassunto").textContent = senza ? `${senza} senza PIN` : "tutti con il PIN";
      corpo.replaceChildren(
        el("p", { class: "hint" }, "Ogni dipendente apre la sua scheda ore mensile da ", el("code", {}, `${location.origin}/scheda-ore`),
          " scegliendo il suo nome e scrivendo il suo PIN personale. Imposta un PIN di 6 cifre oppure generane uno: "
          + "dopo il salvataggio non si può più rileggere."),
        elenco.length ? el("div", { class: "table-scroll" }, el("table", { class: "tabella" },
          el("caption", { class: "sr-only" }, "PIN per la scheda ore dei dipendenti"),
          el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Dipendente"), el("th", { scope: "col" }, "PIN"),
            el("th", { scope: "col" }, "Nuovo PIN"), el("th", { scope: "col" }, "Azioni"))),
          el("tbody", {}, elenco.map((p) => rigaDipendente(p, aggiorna)))))
          : el("p", { class: "muted" }, "Nessun dipendente attivo."));
    } catch (err) { corpo.replaceChildren(el("p", { class: "muted", role: "alert" }, err.message)); }
  };
  aggiorna();
  return sezione;
}
