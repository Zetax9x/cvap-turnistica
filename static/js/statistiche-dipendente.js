// Scheda "Riepilogo per dipendente" delle Statistiche: scelto un dipendente e un periodo, i suoi turni
// giorno per giorno (dall'alto in basso) e, sotto, i totali. Si può stampare.

import { api } from "./api.js";
import { el, clear, dataLunga, ddmm, indiceGiorno, GIORNI_BREVI, formatOre, badgeAssenza, todayISO } from "./util.js";
import { bottoneStampa, focusTitolo, nuovoCaricamento, renderSchede, superato } from "./statistiche.js";

const GIORNI_MAX = 366;
const PARTI = { mattina: "mattina", pomeriggio: "pomeriggio", notte: "notte" };

// la scelta resta finché non si ricarica la pagina
const stato = { root: null, persone: [], personaId: "", dal: "", al: "", dati: null };

/** Primo e ultimo giorno del mese corrente. */
function meseCorrente() {
  const [a, m] = todayISO().split("-").map(Number);
  const ultimo = new Date(a, m, 0).getDate();
  const mm = String(m).padStart(2, "0");
  return [`${a}-${mm}-01`, `${a}-${mm}-${String(ultimo).padStart(2, "0")}`];
}

export async function mostra(root) {
  stato.root = root;
  if (!stato.dal || !stato.al) [stato.dal, stato.al] = meseCorrente();
  const numero = nuovoCaricamento();
  clear(root).append(renderSchede("dipendente"), el("p", { class: "muted loading" }, "Caricamento…"));
  try {
    const persone = await api.persone();
    if (superato(numero)) return;
    stato.persone = persone.filter((p) => p.tipo === "dipendente")
      .sort((a, b) => (b.attivo - a.attivo) || a.nome.localeCompare(b.nome, "it"));
    if (stato.personaId && !stato.persone.some((p) => String(p.id) === stato.personaId)) stato.personaId = "";
    if (stato.personaId) await carica(numero);
    else render();
    focusTitolo(root);
  } catch (err) {
    if (superato(numero)) return;
    errore(err);
  }
}

async function carica(numero = nuovoCaricamento()) {
  try {
    const dati = await api.riepilogoPersona(stato.personaId, stato.dal, stato.al);
    if (superato(numero)) return;
    stato.dati = dati;
    render();
  } catch (err) {
    if (superato(numero)) return;
    errore(err);
  }
}

function errore(err) {
  clear(stato.root).append(renderSchede("dipendente"), renderFiltri(),
    el("div", { class: "banner banner-errore", role: "alert" }, el("strong", {}, "Impossibile caricare il riepilogo. "), err.message));
}

function render() {
  const root = clear(stato.root);
  const d = stato.dati && String(stato.dati.persona_id) === stato.personaId ? stato.dati : null;
  root.append(renderSchede("dipendente"), el("header", { class: "view-header" },
    el("div", { class: "view-header-riga" }, el("h1", {}, "Riepilogo per dipendente"), d ? bottoneStampa() : null),
    el("p", { class: "muted no-print" }, "Scegli un dipendente e il periodo: vedi i turni svolti giorno per giorno e, in fondo, i totali.")));
  root.append(renderFiltri());
  if (!stato.persone.length) {
    root.append(el("p", { class: "muted" }, "Nessun dipendente registrato."));
    return;
  }
  if (!d) {
    root.append(el("p", { class: "muted" }, "Scegli un dipendente e premi “Mostra”."));
    return;
  }
  root.append(
    el("div", { class: "riepilogo-testa" },
      el("h2", {}, d.nome),
      el("p", {}, `Dal ${dataLunga(d.dal)} al ${dataLunga(d.al)}`)),
    renderGiorni(d), renderTotali(d.riepilogo));
}

function renderFiltri() {
  const persona = el("select", { id: "riep-persona", required: true },
    el("option", { value: "" }, "— Scegli —"),
    stato.persone.map((p) => el("option", { value: String(p.id), selected: String(p.id) === stato.personaId },
      p.attivo ? p.nome : `${p.nome} (non attivo)`)));
  const dal = el("input", { type: "date", id: "riep-dal", value: stato.dal, required: true });
  const al = el("input", { type: "date", id: "riep-al", value: stato.al, required: true });
  const applica = (e) => {
    e.preventDefault();
    al.setCustomValidity("");
    if (dal.value > al.value) al.setCustomValidity("La data di fine deve essere dopo quella di inizio");
    else if ((Date.parse(al.value) - Date.parse(dal.value)) / 86400000 >= GIORNI_MAX) {
      al.setCustomValidity(`Il periodo può essere al massimo di ${GIORNI_MAX} giorni`);
    }
    if (!e.target.reportValidity()) return;
    stato.personaId = persona.value;
    stato.dal = dal.value;
    stato.al = al.value;
    carica();
  };
  const mese = () => {
    [dal.value, al.value] = meseCorrente();
  };
  return el("form", { class: "filtri filtri-riepilogo", "aria-label": "Dipendente e periodo", onsubmit: applica },
    el("label", { for: "riep-persona" }, "Dipendente"), persona,
    el("label", { for: "riep-dal" }, "Dal"), dal,
    el("label", { for: "riep-al" }, "al"), al,
    el("button", { type: "button", class: "btn btn-ghost", onclick: mese }, "Questo mese"),
    el("button", { type: "submit", class: "btn btn-primary" }, "Mostra"));
}

/** Un giorno per riga, dall'alto in basso. */
function renderGiorni(d) {
  const righe = d.giorni.map((g) => {
    const i = indiceGiorno(g.data);
    const contenuto = [];
    for (const t of g.turni) {
      contenuto.push(el("div", { class: `riep-turno turno-${t.fascia}` },
        el("span", { class: "riep-orario" }, el("span", { "aria-hidden": "true" }, t.fascia === "notte" ? "☾ " : "☀ "), t.orario),
        el("span", { class: "riep-postazione" }, t.postazione),
        el("span", { class: "riep-ruolo" }, t.ruolo),
        t.festivita ? el("span", { class: "riep-festivo" }, `Festivo: ${t.festivita}`) : null));
    }
    if (g.assenza) contenuto.push(badgeAssenza(g.assenza));
    if (g.indisponibile.length) {
      contenuto.push(el("span", { class: "riep-indisp" },
        `Indisponibile: ${g.indisponibile.map((p) => PARTI[p] || p).join(", ")}`));
    }
    if (!contenuto.length) contenuto.push(el("span", { class: "muted riep-riposo" }, "Riposo"));
    const ore = g.turni.reduce((s, t) => s + t.ore, 0);
    return el("tr", { class: i >= 5 ? "weekend" : null },
      el("th", { scope: "row", class: "riep-data" }, el("b", {}, GIORNI_BREVI[i]), ` ${ddmm(g.data)}/${g.data.slice(0, 4)}`),
      el("td", {}, contenuto),
      el("td", { class: "num" }, ore ? `${formatOre(ore)} h` : ""));
  });
  return el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-riepilogo" },
    el("caption", { class: "sr-only" }, `Turni di ${d.nome} giorno per giorno`),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Giorno"), el("th", { scope: "col" }, "Turni"), el("th", { scope: "col", class: "num" }, "Ore"))),
    el("tbody", {}, righe)));
}

function renderTotali(r) {
  const voce = (titolo, valore, nota = null) => el("div", { class: "riep-voce" },
    el("dt", {}, titolo), el("dd", {}, valore, nota ? el("span", { class: "riep-nota" }, nota) : null));
  const assenze = [r.giorni_ferie ? `${r.giorni_ferie} g ferie` : null, r.giorni_malattia ? `${r.giorni_malattia} g malattia` : null]
    .filter(Boolean).join(" + ");
  const w = r.weekend;
  return el("section", { class: "riep-totali", "aria-labelledby": "riep-totali-titolo" },
    el("h2", { id: "riep-totali-titolo" }, "Riepilogo del periodo"),
    el("dl", { class: "riep-griglia" },
      voce("Turni svolti", String(r.turni), `${r.turni_giorno} di giorno · ${r.turni_notte} di notte`),
      voce("Ore lavorate", `${formatOre(r.ore_lavorate)} h`, `${formatOre(r.ore_giorno)} h giorno · ${formatOre(r.ore_notte)} h notte`),
      voce("Ferie e malattia", assenze || "nessuna", r.ore_ferie_malattia ? `${formatOre(r.ore_ferie_malattia)} h accreditate` : null),
      voce("Ore totali", `${formatOre(r.ore_totali)} h`, "lavorate + 6 h per giorno di ferie o malattia"),
      voce("Turni nel weekend", String(w.sab_giorno + w.sab_notte + w.dom_giorno + w.dom_notte),
        `sab ${w.sab_giorno} G / ${w.sab_notte} N · dom ${w.dom_giorno} G / ${w.dom_notte} N`),
      voce("Turni festivi", String(r.turni_festivi || 0),
        (r.festivi || []).map((f) => `${f.festivita} ${f.turni}`).join(" · ") || null),
      voce("Giorni con indisponibilità", String(r.giorni_indisponibili))),
    r.postazioni.length ? el("table", { class: "tabella tabella-riep-postazioni" },
      el("caption", {}, "Turni per postazione"),
      el("thead", {}, el("tr", {},
        el("th", { scope: "col" }, "Postazione"), el("th", { scope: "col", class: "num" }, "Turni"),
        el("th", { scope: "col", class: "num" }, "Ore"))),
      el("tbody", {}, r.postazioni.map((p) => el("tr", {},
        el("th", { scope: "row" }, p.postazione), el("td", { class: "num" }, String(p.turni)),
        el("td", { class: "num" }, `${formatOre(p.ore)} h`))))) : null);
}
