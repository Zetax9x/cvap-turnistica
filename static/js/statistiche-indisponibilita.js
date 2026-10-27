// Scheda "Indisponibilità" delle Statistiche: per ogni dipendente, quante volte ha chiesto di essere
// indisponibile in ciascun giorno della settimana (lunedì..domenica), per vedere le richieste ricorrenti.

import { api } from "./api.js";
import { el, clear, dataLunga, GIORNI_BREVI } from "./util.js";
import { bottoneStampa, focusTitolo, nuovoCaricamento, renderSchede, superato } from "./statistiche.js";

const GIORNI_LUNGHI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"];
const PARTI = [["mattina", "M"], ["pomeriggio", "P"], ["notte", "N"]];

const stato = { root: null, righe: [], dal: "", al: "" };

export async function mostra(root) {
  stato.root = root;
  clear(root).append(renderSchede("indisponibilita"),
    el("p", { class: "muted loading" }, "Caricamento delle indisponibilità…"));
  await carica();
}

async function carica() {
  const numero = nuovoCaricamento();
  try {
    const righe = await api.statisticheIndisponibilita(stato.dal, stato.al);
    if (superato(numero)) return;
    stato.righe = righe;
    render();
    focusTitolo(stato.root);
  } catch (err) {
    if (superato(numero)) return;
    clear(stato.root).append(renderSchede("indisponibilita"), el("div", { class: "banner banner-errore", role: "alert" },
      el("strong", {}, "Impossibile caricare le indisponibilità. "), err.message));
  }
}

function render() {
  const root = clear(stato.root);
  root.append(renderSchede("indisponibilita"), el("header", { class: "view-header" },
    el("div", { class: "view-header-riga" }, el("h1", {}, "Indisponibilità per giorno"), bottoneStampa()),
    el("p", { class: "muted" },
      "Quante volte ogni dipendente ha chiesto di essere indisponibile in ciascun giorno della settimana. "
      + "Il numero conta i giorni (anche se indisponibile solo in una parte); sotto, il dettaglio per mattina (M), "
      + "pomeriggio (P) e notte (N). Più la cella è scura, più il giorno ricorre per quel dipendente. Le ferie non sono comprese.")));
  root.append(renderPeriodo(), el("p", { class: "solo-stampa" }, `Periodo: ${descriviPeriodo()}`));

  if (!stato.righe.length) {
    root.append(el("p", { class: "muted" }, "Nessun dipendente registrato."));
    return;
  }
  // l'intensità del colore è relativa alla riga: conta lo schema di ciascuno, non chi ne chiede di più
  const tbody = el("tbody", {}, stato.righe.map((r) => {
    const massimo = Math.max(0, ...r.giorni.map((g) => g.totale));
    return el("tr", {},
      el("th", { scope: "row" }, r.nome, r.attivo ? null : el("span", { class: "muted" }, " (non attivo)")),
      r.giorni.map((g, i) => renderCella(g, i, massimo)),
      el("td", { class: "num indisp-totale" }, String(r.totale)),
      el("td", {}, piuRichiesto(r)));
  }));

  root.append(el("div", { class: "table-scroll" }, el("table", { class: "tabella tabella-indisp-stat" },
    el("caption", { class: "sr-only" }, "Indisponibilità richieste per dipendente e giorno della settimana"),
    el("thead", {}, el("tr", {},
      el("th", { scope: "col" }, "Dipendente"),
      GIORNI_BREVI.map((g, i) => el("th", { scope: "col", class: `num${i >= 5 ? " weekend" : ""}` }, g)),
      el("th", { scope: "col", class: "num" }, "Totale"),
      el("th", { scope: "col" }, "Più richiesto"))),
    tbody)));
}

function renderCella(g, i, massimo) {
  const dettaglio = PARTI.filter(([parte]) => g[parte]).map(([parte, sigla]) => `${sigla}${g[parte]}`).join(" ");
  const livello = g.totale && massimo ? Math.ceil((g.totale / massimo) * 4) : 0;  // 0..4
  return el("td", {
    class: `num indisp-cella indisp-liv-${livello}${i >= 5 ? " weekend" : ""}`,
    title: g.totale
      ? `${GIORNI_LUNGHI[i]}: ${g.totale} ${g.totale === 1 ? "volta" : "volte"} (mattina ${g.mattina}, pomeriggio ${g.pomeriggio}, notte ${g.notte})`
      : null,
  }, g.totale ? [el("span", { class: "indisp-num" }, String(g.totale)), el("span", { class: "indisp-parti" }, dettaglio)] : "·");
}

/** Il giorno (o i giorni a pari merito) con più richieste, con la quota sul totale. */
function piuRichiesto(r) {
  if (!r.totale) return el("span", { class: "muted" }, "—");
  const massimo = Math.max(...r.giorni.map((g) => g.totale));
  const giorni = r.giorni.map((g, i) => (g.totale === massimo ? GIORNI_LUNGHI[i] : null)).filter(Boolean);
  return `${giorni.join(", ")} (${massimo} su ${r.totale})`;
}

function descriviPeriodo() {
  if (!stato.dal && !stato.al) return "tutte le indisponibilità registrate";
  return [stato.dal ? `dal ${dataLunga(stato.dal)}` : null, stato.al ? `al ${dataLunga(stato.al)}` : null]
    .filter(Boolean).join(" ");
}

function renderPeriodo() {
  const dal = el("input", { type: "date", id: "indisp-dal", value: stato.dal });
  const al = el("input", { type: "date", id: "indisp-al", value: stato.al });
  const applica = (e) => {
    e.preventDefault();
    if (dal.value && al.value && dal.value > al.value) {
      al.setCustomValidity("La data di fine deve essere dopo quella di inizio");
      al.reportValidity();
      return;
    }
    al.setCustomValidity("");
    stato.dal = dal.value;
    stato.al = al.value;
    carica();
  };
  return el("form", { class: "filtri periodo-indisp", "aria-label": "Periodo", onsubmit: applica },
    el("label", { for: "indisp-dal" }, "Dal"), dal,
    el("label", { for: "indisp-al" }, "al"), al,
    el("button", { type: "submit", class: "btn" }, "Applica"),
    stato.dal || stato.al
      ? el("button", {
        type: "button", class: "btn btn-ghost",
        onclick: () => { stato.dal = ""; stato.al = ""; carica(); },
      }, "Tutto il periodo")
      : el("span", { class: "muted" }, "Senza date: tutte le indisponibilità registrate."));
}
