// Cambi turno registrati dai dipendenti (gestione).
import { el, clear } from "/static/js/util.js";
import { testata, gruppo, riga, avviso, caricamento, pill, foglio, conferma, mostra, mostraErrore, monta } from "./ui.js";

async function chiama(percorso, corpo) {
  const r = await fetch(`/api/${percorso}`, corpo === undefined ? { headers: { Accept: "application/json" } }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
  if (r.status === 401) window.dispatchEvent(new CustomEvent("cvap:accesso-richiesto"));
  const t = await r.text(); let b = null; try { b = t ? JSON.parse(t) : null; } catch { /* niente */ }
  if (!r.ok) throw new Error(typeof (b && b.detail) === "string" ? b.detail : `Errore ${r.status}`);
  return b;
}

export default async function cambi(root) {
  const corpo = el("div", { class: "contenuto" }, caricamento());
  root.append(testata("Cambi turno", { indietro: () => { location.hash = "#/altro"; }, sotto: "Cessioni e scambi dei dipendenti" }), corpo);
  async function carica() {
    try {
      const dati = await chiama("gestione-cambi-turno");
      monta(corpo, 
        el("div", { class: "card" }, el("div", { class: "card-titolo" }, "Link per i dipendenti"),
          el("input", { class: "input", readOnly: true, value: `${location.origin}/cambio-turno`, "aria-label": "Link", onFocus: (e) => e.target.select() })),
        dati.length ? gruppo(...dati.map((v) => riga({
          titolo: `#${v.id} · ${v.dati.tipo === "scambio" ? "Scambio" : "Cessione"}`,
          sotto: `${v.dati.dichiarante} · ${new Date(v.creata_il).toLocaleDateString("it-IT")}`,
          fine: v.annullata_il ? pill("annullato", "rosso") : v.notifica === "inviata" ? pill("email ok", "verde") : pill("da reinviare", "ambra"),
          onClick: () => dettaglio(v) }))) : el("div", { class: "vuoto" }, "Nessun cambio registrato."));
    } catch (e) { monta(corpo, avviso(e.message, "errore")); }
  }
  function dettaglio(v) {
    foglio(`Cambio #${v.id}`, (chiudi) => [
      el("ul", { style: "margin:0;padding-left:18px" }, v.riepilogo.map((r) => el("li", {}, r))),
      v.notifica !== "inviata" ? el("button", { class: "btn btn-blocco", onClick: async () => {
        try { await chiama(`gestione-cambi-turno/${v.id}/reinvia`, {}); chiudi(); mostra("Comunicazione reinviata"); await carica(); } catch (e) { mostraErrore(e); }
      } }, "Reinvia la comunicazione") : null,
      !v.annullata_il ? el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
        try {
          const a = await chiama(`gestione-cambi-turno/${v.id}/anteprima-annullamento`, {});
          if (a.errori && a.errori.length) return mostra(a.errori[0], "errore");
          if (!(await conferma("I turni tornano a chi li aveva prima e i responsabili ricevono l'email di annullamento.", { titolo: "Annullare il cambio?", ok: "Annulla il cambio", pericolo: true }))) return;
          await chiama(`gestione-cambi-turno/${v.id}/annulla`, { versione: a.versione, chiave: crypto.randomUUID() });
          chiudi(); mostra("Cambio annullato"); await carica();
        } catch (e) { mostraErrore(e); }
      } }, "Annulla il cambio") : null]);
  }
  await carica();
}
