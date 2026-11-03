import { el } from "./util.js";

export async function richiesta(percorso, corpo) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90000);
  try {
    const r = await fetch(`/api/${percorso}`, {
      method: corpo === undefined ? "GET" : "POST", signal: controller.signal,
      headers: { Accept: "application/json", ...(corpo === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(corpo === undefined ? {} : { body: JSON.stringify(corpo) }),
    });
    const dati = await r.json();
    if (!r.ok) {
      const detail = dati.detail;
      const messaggio = Array.isArray(detail) ? "Controlla i dati inseriti e riprova." : detail;
      const err = new Error(messaggio || "Operazione non riuscita.");
      err.status = r.status;
      if (r.status === 401) window.dispatchEvent(new CustomEvent("cvap:accesso-richiesto"));
      throw err;
    }
    return dati;
  } catch (err) {
    if (err.status) throw err;
    throw new Error("Non riusciamo a contattare il sito. Controlla la connessione e riprova. Se stavi confermando un cambio, controlla prima se è stato salvato.");
  } finally { clearTimeout(timer); }
}

export function turnoScheda(t) {
  const data = new Date(`${t.data}T12:00:00`).toLocaleDateString("it-IT", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });
  const fine = t.fine?.slice(0, 10) !== t.data ? " · termina il giorno seguente" : "";
  return el("div", { class: "cambio-turno-dettaglio" },
    el("strong", {}, data), el("span", {}, `${t.orario}${fine}`),
    el("span", {}, `${t.postazione} · ${t.ruolo}`));
}

export function riepilogo(vista) {
  return el("div", { class: "cambio-riepilogo" },
    ...vista.prima.map((prima, i) => el("article", { class: "cambio-card" },
      el("p", {}, el("strong", {}, prima.persona_nome), " lascia questo turno a ", el("strong", {}, vista.dopo[i].persona_nome)),
      turnoScheda(prima))),
    vista.avvisi.length ? el("aside", { class: "cambio-avviso" },
      el("h3", {}, "Da sapere prima di confermare"), el("p", {}, "Puoi confermare anche con questi avvisi. Saranno inclusi nell’email ai responsabili."),
      el("ul", {}, ...vista.avvisi.map(v => el("li", {}, v.messaggio)))) : null,
    vista.errori.length ? el("div", { class: "cambio-errore", role: "alert" },
      el("h3", {}, "Non puoi confermare questo cambio"),
      el("p", {}, "Leggi il motivo qui sotto. Torna indietro e scegli un altro collega o un altro turno."),
      el("ul", {}, ...vista.errori.map(v => el("li", {}, v.messaggio)))) : null);
}

export function nuovaChiave() {
  // randomUUID richiede un contesto sicuro; il fallback funziona anche in LAN via HTTP.
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
  const h = [...b].map(x => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}
