// Scheda «Oggi»: i turni di oggi e di domani, chi è libero, avvisi della settimana.
import { api } from "/static/js/api.js";
import { el, todayISO, addDays, mondayOf, dataLunga, GIORNI_BREVI, indiceGiorno } from "/static/js/util.js";
import { testata, riempi, pill } from "./ui.js";
import { turniDelGiorno, disegnaGiorno, scoperti } from "./turni.js";

export default async function oggi(root) {
  const contenitore = el("div", { class: "contenuto" });
  root.append(testata("Oggi", { sotto: dataLunga(todayISO()) }), contenitore);
  await riempi(contenitore, async () => {
    const oggiIso = todayISO();
    const lun = mondayOf(oggiIso);
    const sett = await api.settimana(lun);
    const gruppi = turniDelGiorno(sett, oggiIso);
    const nScoperti = scoperti(gruppi);
    const domaniIso = addDays(oggiIso, 1);
    // domani può cadere nella settimana dopo
    const settDomani = mondayOf(domaniIso) === lun ? sett : await api.settimana(mondayOf(domaniIso));
    const gDomani = turniDelGiorno(settDomani, domaniIso);
    const festivo = (sett.festivi || []).find((f) => f.data === oggiIso);
    const liberiOggi = (sett.liberi || []).find((g) => g.data === oggiIso);
    return [
      el("div", {}, pill(sett.stato === "confermata" ? "Settimana confermata" : sett.stato === "bozza" ? "Settimana in bozza" : "Settimana da preparare",
        sett.stato === "confermata" ? "verde" : sett.stato === "bozza" ? "ambra" : ""),
      nScoperti ? [" ", pill(`${nScoperti} scoperti`, "rosso")] : null,
      festivo ? [" ", pill(festivo.nome || "Festivo", "rosso")] : null),
      disegnaGiorno(gruppi),
      liberiOggi && liberiOggi.liberi.length ? el("section", { class: "card" },
        el("div", { class: "card-titolo" }, `Dipendenti liberi oggi (${liberiOggi.liberi.length})`),
        el("div", {}, liberiOggi.liberi.map((p) => el("span", { style: "display:inline-block;margin:0 6px 6px 0" }, pill(p.nome))))) : null,
      el("div", { class: "card-titolo", style: "margin:6px 4px 0" }, `Domani · ${GIORNI_BREVI[indiceGiorno(domaniIso)]}`),
      disegnaGiorno(gDomani),
    ];
  });
}
