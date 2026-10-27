// Client REST per il backend CVAP (vedi docs/API.md).

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function dettaglio(body, status) {
  if (body && body.detail !== undefined) {
    const d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
      // Errori di validazione FastAPI (422)
      return d.map((e) => {
        const campo = Array.isArray(e.loc) ? e.loc.filter((x) => x !== "body").join(".") : "";
        return campo ? `${campo}: ${e.msg}` : e.msg;
      }).join("; ");
    }
    return JSON.stringify(d);
  }
  return `Errore del server (HTTP ${status})`;
}

async function richiesta(metodo, percorso, corpo) {
  const opzioni = { method: metodo, headers: { Accept: "application/json" } };
  if (corpo !== undefined) {
    opzioni.headers["Content-Type"] = "application/json";
    opzioni.body = JSON.stringify(corpo);
  }
  let risposta;
  try {
    risposta = await fetch(`/api${percorso}`, opzioni);
  } catch {
    throw new ApiError("Impossibile contattare il server. Verifica che l'applicazione sia avviata.", 0);
  }
  if (risposta.status === 204) return null;
  let body = null;
  const testo = await risposta.text();
  if (testo) {
    try { body = JSON.parse(testo); } catch { body = null; }
  }
  if (!risposta.ok) throw new ApiError(dettaglio(body, risposta.status), risposta.status);
  return body;
}

const enc = encodeURIComponent;

export const api = {
  persone: () => richiesta("GET", "/persone"),
  creaPersona: (dati) => richiesta("POST", "/persone", dati),
  aggiornaPersona: (id, dati) => richiesta("PUT", `/persone/${enc(id)}`, dati),
  eliminaPersona: (id) => richiesta("DELETE", `/persone/${enc(id)}`),
  impostaParametri: (id, maxOre) =>
    richiesta("PUT", `/persone/${enc(id)}/parametri`, { max_ore_settimana: maxOre }),

  divieti: () => richiesta("GET", "/divieti"),
  creaDivieto: (dati) => richiesta("POST", "/divieti", dati),
  eliminaDivieto: (id) => richiesta("DELETE", `/divieti/${enc(id)}`),

  postazioni: () => richiesta("GET", "/postazioni"),

  impostazioni: () => richiesta("GET", "/impostazioni"),
  salvaImpostazioni: (dati) => richiesta("PUT", "/impostazioni", dati),

  settimana: (data) => richiesta("GET", `/settimane/${enc(data)}`),
  aggiungiAssegnazione: (data, dati) => richiesta("POST", `/settimane/${enc(data)}/assegnazioni`, dati),
  eliminaAssegnazione: (id) => richiesta("DELETE", `/assegnazioni/${enc(id)}`),
  genera: (data, tempoMax) =>
    richiesta("POST", `/settimane/${enc(data)}/genera`, tempoMax ? { tempo_max: tempoMax } : {}),
  conferma: (data) => richiesta("POST", `/settimane/${enc(data)}/conferma`),
  riapri: (data) => richiesta("POST", `/settimane/${enc(data)}/riapri`),
  rimuoviGenerati: (data) => richiesta("DELETE", `/settimane/${enc(data)}/generati`),

  // turni: [{data, parte}] con parte "mattina" | "pomeriggio" | "notte"
  impostaIndisponibilita: (data, personaId, turni) =>
    richiesta("PUT", `/settimane/${enc(data)}/indisponibilita`, { persona_id: personaId, turni }),

  impostaFabbisogno: (data, voci) => richiesta("PUT", `/settimane/${enc(data)}/fabbisogno`, { voci }),

  ferie: () => richiesta("GET", "/ferie"),
  creaFerie: (dati) => richiesta("POST", "/ferie", dati),
  eliminaFerie: (id) => richiesta("DELETE", `/ferie/${enc(id)}`),

  statistiche: () => richiesta("GET", "/statistiche"),
  statisticheIndisponibilita: (dal, al) => {
    const q = new URLSearchParams();
    if (dal) q.set("dal", dal);
    if (al) q.set("al", al);
    return richiesta("GET", `/statistiche/indisponibilita${q.size ? `?${q}` : ""}`);
  },
};
