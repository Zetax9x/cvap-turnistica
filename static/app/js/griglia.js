// Vista a griglia dell'intera settimana: righe = turni, colonne = giorni. Legenda e filtri.
import { el, GIORNI_BREVI, indiceGiorno, parseISO, ddmm, orarioTurno, oraInizio } from "/static/js/util.js";
import { turniDelGiorno } from "./turni.js";
import { monta } from "./ui.js";

const SIGLA = { autista: "A", soccorritore: "S" };

/** Righe della griglia: per postazione, i turni (fascia + segmento) presenti in almeno un giorno. */
function righeGriglia(sett) {
  const per = new Map();
  for (const g of sett.giorni) {
    for (const p of turniDelGiorno(sett, g)) {
      if (!per.has(p.postazione)) per.set(p.postazione, new Map());
      for (const t of p.turni) per.get(p.postazione).set(`${t.fascia}|${t.segmento}`, { fascia: t.fascia, segmento: t.segmento });
    }
  }
  return [...per].map(([postazione, m]) => ({
    postazione, turni: [...m.values()].sort((a, b) => oraInizio(a.fascia, a.segmento) - oraInizio(b.fascia, b.segmento)),
  }));
}

function cella(sett, postazione, t, g) {
  const p = turniDelGiorno(sett, g).find((x) => x.postazione === postazione);
  const turno = p && p.turni.find((x) => x.fascia === t.fascia && x.segmento === t.segmento);
  const td = el("td", { class: `gr-cella gr-f-${t.fascia}` });
  if (!turno) { td.append(el("span", { class: "muto" }, "·")); return { td, scoperti: 0 }; }
  let scoperti = 0;
  for (const posto of turno.posti) {
    const a = posto.assegnazione;
    if (!a) scoperti++;
    td.append(el("div", { class: `gr-posto ${!a ? "gr-vuoto" : a.origine === "volontario" ? "gr-vol" : a.origine === "manuale" ? "gr-man" : ""}` },
      el("b", {}, SIGLA[posto.ruolo]), " ", a ? a.persona_nome : "scoperto"));
  }
  return { td, scoperti };
}

/** `stato` = {postazione: string|null, soloScoperti: bool}; `ridisegna()` rifà la vista dopo un filtro. */
export function disegnaGriglia(sett, stato, { suGiorno, ridisegna }) {
  const righe = righeGriglia(sett);
  const filtri = el("div", { style: "display:flex;gap:8px;overflow-x:auto;padding-bottom:2px" },
    [[null, "Tutte"], ...righe.map((r) => [r.postazione, r.postazione])].map(([v, t]) =>
      el("button", { class: "btn", style: "min-height:36px;flex:none", "aria-pressed": String(stato.postazione === v), type: "button",
        onClick: () => { stato.postazione = v; ridisegna(); } }, t)),
    el("button", { class: "btn", style: "min-height:36px;flex:none", "aria-pressed": String(stato.soloScoperti), type: "button",
      onClick: () => { stato.soloScoperti = !stato.soloScoperti; ridisegna(); } }, "Solo scoperti"));
  const legenda = el("div", { class: "gr-legenda piccolo muto" },
    el("span", { class: "gr-vol gr-chip" }, "Volontario"), el("span", { class: "gr-man gr-chip" }, "Fissato"),
    el("span", { class: "gr-chip" }, "Generato"), el("span", { class: "gr-vuoto gr-chip" }, "Scoperto"));

  const testa = el("tr", {}, el("th", { class: "gr-prima" }, "Turno"), sett.giorni.map((g) => {
    const festivo = (sett.festivi || []).find((f) => f.data === g);
    const we = indiceGiorno(g) >= 5;
    return el("th", { class: `${festivo ? "gr-festivo" : we ? "gr-we" : ""}` },
      el("button", { class: "gr-giorno", type: "button", onClick: () => suGiorno(g), "aria-label": `Apri ${GIORNI_BREVI[indiceGiorno(g)]} ${ddmm(g)}` },
        GIORNI_BREVI[indiceGiorno(g)], el("br"), el("b", { class: "num" }, String(parseISO(g).getDate())),
        festivo ? el("div", { class: "gr-nomefesta" }, festivo.nome) : null));
  }));

  const blocchi = [];
  for (const r of righe) {
    if (stato.postazione && stato.postazione !== r.postazione) continue;
    const corpo = [];
    for (const t of r.turni) {
      const celle = sett.giorni.map((g) => cella(sett, r.postazione, t, g));
      if (stato.soloScoperti && !celle.some((c) => c.scoperti)) continue;
      corpo.push(el("tr", {}, el("th", { class: `gr-prima gr-f-${t.fascia}` }, orarioTurno(t.fascia, t.segmento)), celle.map((c) => c.td)));
    }
    if (!corpo.length) continue;
    blocchi.push(el("section", { class: "card", style: "padding:10px 0 4px" },
      el("div", { style: "font-weight:800;padding:0 14px 6px" }, r.postazione),
      el("div", { class: "gr-scroll" }, el("table", { class: "gr-tabella" }, el("thead", {}, testa.cloneNode(true)), el("tbody", {}, corpo)))));
  }
  // cloneNode non porta i listener: li ricollego sui pulsanti dei giorni
  for (const b of blocchi) b.querySelectorAll(".gr-giorno").forEach((btn, i) => btn.addEventListener("click", () => suGiorno(sett.giorni[i % 7])));
  return [filtri, legenda, blocchi.length ? blocchi : el("div", { class: "vuoto" }, stato.soloScoperti ? "Nessun posto scoperto." : "Nessun turno in questa settimana.")];
}
