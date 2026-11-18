// Vista "Schede ore" (solo accesso master): lo stato della scheda ore mensile di ogni dipendente, il download
// delle schede confermate e la riapertura (il dipendente potrà di nuovo correggerla e confermarla).

import { api } from "./api.js";
import { el, toast, toastErrore, chiediConferma } from "./util.js";

const STATI = { non_aperta: ["Non aperta", "badge-nuova"], bozza: ["In revisione", "badge-avviso"], confermata: ["Confermata", "badge-confermata"] };
const FORMATO_MESE = /^\d{4}-(0[1-9]|1[0-2])$/;

function meseCorrente() {
  const oggi = new Date();
  return `${oggi.getFullYear()}-${String(oggi.getMonth() + 1).padStart(2, "0")}`;
}

function quando(iso) {
  return iso ? new Date(iso).toLocaleString("it-IT", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
}

export async function mostra(root) {
  const mese = el("input", { type: "month", id: "schede-mese", value: meseCorrente(), pattern: "\\d{4}-\\d{2}", placeholder: "AAAA-MM" });
  const corpo = el("tbody");
  const messaggio = el("p", { class: "muted", role: "status" });

  const carica = async () => {
    if (!FORMATO_MESE.test(mese.value)) { messaggio.textContent = "Scegli un mese (AAAA-MM)."; corpo.replaceChildren(); return; }
    try {
      const elenco = await api.elencoSchedeOre(mese.value);
      corpo.replaceChildren(...elenco.map(riga));
      messaggio.textContent = elenco.length ? "" : "Nessun dipendente attivo.";
    } catch (err) { messaggio.textContent = err.message; }
  };

  const riapri = async (p) => {
    if (!await chiediConferma(`${p.nome} potrà di nuovo correggere la scheda di ${mese.value} e poi confermarla ancora. Le sue correzioni restano.`,
      { titolo: "Riaprire la scheda?", ok: "Riapri", pericolo: true })) return;
    try { await api.riapriSchedaOre(mese.value, p.persona_id); toast(`Scheda di ${p.nome} riaperta.`, "ok"); await carica(); } catch (err) { toastErrore(err); }
  };

  const riga = (p) => {
    const [testo, classe] = STATI[p.stato] || [p.stato, "badge-nuova"];
    const confermata = p.stato === "confermata";
    return el("tr", {},
      el("th", { scope: "row" }, p.nome),
      el("td", {}, el("span", { class: `badge ${classe}` }, testo)),
      el("td", {}, quando(p.aggiornata_il)),
      el("td", {}, quando(p.confermata_il)),
      el("td", {}, confermata ? [
        el("a", { class: "btn btn-small btn-secondary", href: `/api/schede-ore-gestione/${mese.value}/${p.persona_id}.xlsx`, download: "" }, "Scarica Excel"),
        el("button", { type: "button", class: "btn btn-small btn-ghost", onclick: () => riapri(p) }, "Riapri")] : null));
  };

  mese.addEventListener("change", carica);
  root.replaceChildren(
    el("header", { class: "view-header" },
      el("h1", {}, "Schede ore"),
      el("p", {}, "Le schede ore mensili dei dipendenti: ognuno le controlla e le corregge dalla sua pagina, poi le conferma. "
        + "Qui scarichi quelle confermate e, se serve, le riapri.")),
    el("div", { class: "registro-filtri" }, el("label", { for: "schede-mese" }, "Mese"), mese),
    el("div", { class: "registro-tabella" },
      el("table", { class: "tabella" },
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Dipendente"), el("th", { scope: "col" }, "Stato"),
          el("th", { scope: "col" }, "Ultima modifica"), el("th", { scope: "col" }, "Confermata il"), el("th", { scope: "col" }, "Azioni"))),
        corpo)),
    messaggio);
  await carica();
}
