// Scheda «Statistiche»: ore, notti e weekend per persona; equità; festività.
import { api } from "/static/js/api.js";
import { el, clear, formatOre, formatSaldo, etichetta } from "/static/js/util.js";
import { testata, riempi, gruppo, riga, avatar, foglio, avviso, pill, monta } from "./ui.js";

export default async function statistiche(root) {
  const corpo = el("div", { class: "contenuto" });
  let tipo = "dipendente";
  let dati = [];
  const segm = el("div", { class: "segmenti", role: "group", "aria-label": "Tipo" });
  const lista = el("div");
  const disegna = () => {
    const sel = dati.filter((d) => d.tipo === tipo);
    const maxOre = Math.max(1, ...sel.map((d) => d.ore_lavorate));
    monta(segm, ...[["dipendente", "Dipendenti"], ["volontario", "Volontari"]].map(([v, t]) =>
      el("button", { type: "button", "aria-pressed": String(tipo === v), onClick: () => { tipo = v; disegna(); } }, t)));
    monta(lista, sel.length ? gruppo(...sel.map((d) => riga({
      titolo: d.nome, avatar: avatar(d.nome, d.tipo), onClick: () => dettaglio(d), freccia: true,
      sotto: el("div", {}, `${formatOre(d.ore_lavorate)} h · ${d.settimane} sett.`,
        el("div", { class: "barra", style: "margin-top:6px" }, el("i", { style: `width:${(d.ore_lavorate / maxOre) * 100}%` }))),
      fine: d.tipo === "dipendente" ? el("span", { class: `riga-fine num` }, formatSaldo(d.saldo_ore)) : null,
    }))) : el("div", { class: "vuoto" }, "Ancora nessuna settimana confermata."));
  };
  root.append(testata("Statistiche", { sotto: "Solo settimane confermate" }),
    el("div", { class: "contenuto", style: "padding-bottom:0" }, segm), corpo);
  corpo.append(lista);
  await riempi(lista, async () => { dati = await api.statistiche(); return []; });
  disegna();
}

function dettaglio(d) {
  const festivi = d.festivi ? d.festivi.turni : 0;
  const voce = (t, v) => el("div", { class: "numero" }, el("b", { class: "num" }, String(v)), el("span", {}, t));
  foglio(d.nome, () => [
    el("div", { class: "griglia2" },
      voce("settimane", d.settimane), voce("ore lavorate", formatOre(d.ore_lavorate)),
      voce("ore di giorno", formatOre(d.ore_giorno)), voce("ore di notte", formatOre(d.ore_notte)),
      voce("ore di ferie", formatOre(d.ore_ferie)), voce("ore di malattia", formatOre(d.ore_malattia)),
      voce("turni festivi", festivi), voce("turni a Ascoli", d.ascoli ? d.ascoli.turni : 0)),
    d.tipo === "dipendente" ? el("p", { class: "muto" }, `Saldo ore rispetto alla media: ${formatSaldo(d.saldo_ore)} h`) : null,
    d.ore_sostituzioni ? el("p", { class: "muto" }, `Sostituzioni (ore extra, non contate sopra): ${formatOre(d.ore_sostituzioni)} h`) : null,
    el("div", { class: "card-titolo" }, "Weekend e sedi"),
    gruppo(...Object.entries(d.weekend || {}).map(([k, v]) => riga({ titolo: k.replace(/_/g, " "), fine: String(v), freccia: false })),
      ...Object.entries(d.sedi || {}).map(([k, v]) => riga({ titolo: k, fine: String(v), freccia: false }))),
  ]);
}
