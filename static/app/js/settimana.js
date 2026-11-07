// Scheda «Settimana»: giorno per giorno, correzioni a mano, genera, conferma, invio email.
import { api } from "/static/js/api.js";
import { el, clear, todayISO, addDays, mondayOf, ddmm, GIORNI_BREVI, parseISO, formatOre, etichetta } from "/static/js/util.js";
import { testata, icona, riempi, pill, avviso, foglio, gruppo, riga, conferma, scegli, conAttesa, mostra, mostraErrore, caricamento, monta } from "./ui.js";
import { turniDelGiorno, disegnaGiorno, scoperti } from "./turni.js";
import { apriPosto } from "./modifica.js";

const STATO = { nuova: ["Da preparare", ""], bozza: ["Bozza", "ambra"], confermata: ["Confermata", "verde"] };

export default async function settimana(root, { parametri }) {
  const lun = mondayOf(parametri[0] || todayISO());
  const oggi = todayISO();
  let giorno = parametri[1] || (mondayOf(oggi) === lun ? oggi : lun);
  let sett = null;

  const barra = el("div", { class: "giorni" });
  const corpo = el("div", { class: "contenuto" });
  const titolo = el("div", { style: "display:contents" });
  root.append(titolo, barra, corpo);

  const vaiSett = (n) => { location.hash = `#/settimana/${addDays(lun, 7 * n)}`; };

  function intestazione() {
    const fine = addDays(lun, 6);
    const [testoStato, tipoStato] = STATO[sett.stato] || STATO.nuova;
    monta(titolo, testata(`${ddmm(lun)} – ${ddmm(fine)}`, {
      sotto: el("span", {}, `Settimana ${sett.tipo} `, pill(testoStato, tipoStato)),
      azioni: [
        el("button", { class: "btn btn-icona", "aria-label": "Settimana precedente", onClick: () => vaiSett(-1) }, icona("indietro")),
        el("button", { class: "btn btn-icona", "aria-label": "Settimana successiva", onClick: () => vaiSett(1) }, icona("avanti")),
        el("button", { class: "btn btn-icona", "aria-label": "Azioni della settimana", onClick: menu }, icona("altro")),
      ],
    }));
  }

  function disegnaBarra() {
    monta(barra, ...sett.giorni.map((g, i) => {
      const festivo = (sett.festivi || []).some((f) => f.data === g);
      const nScop = scoperti(turniDelGiorno(sett, g));
      return el("button", { class: `giorno ${festivo ? "festivo" : ""} ${g === oggi ? "oggi" : ""}`, type: "button",
        "aria-pressed": String(g === giorno), "aria-label": `${GIORNI_BREVI[i]} ${ddmm(g)}`,
        onClick: () => { giorno = g; history.replaceState(null, "", `#/settimana/${lun}/${g}`); disegnaBarra(); disegnaCorpo(); } },
      el("small", {}, GIORNI_BREVI[i]), el("b", { class: "num" }, String(parseISO(g).getDate())),
      nScop && sett.stato !== "nuova" ? el("span", { class: "punto", title: `${nScop} scoperti` }) : null);
    }));
    const attivo = barra.querySelector('[aria-pressed="true"]');
    if (attivo) attivo.scrollIntoView({ inline: "center", block: "nearest" });
  }

  function disegnaCorpo() {
    const gruppi = turniDelGiorno(sett, giorno);
    const festivo = (sett.festivi || []).find((f) => f.data === giorno);
    const err = sett.violazioni.filter((v) => v.livello === "errore").length;
    const avv = sett.violazioni.length - err;
    const liberi = (sett.liberi || []).find((g) => g.data === giorno);
    const assenti = (sett.ferie || []).filter((f) => f.data === giorno);
    monta(corpo, 
      festivo ? avviso(`Festivo: ${festivo.nome}`, "errore") : null,
      sett.violazioni.length ? el("button", { class: `avviso ${err ? "avviso-errore" : ""}`, style: "border:0;text-align:left;width:100%", onClick: apriControlli },
        `${err ? `${err} error${err === 1 ? "e" : "i"}` : ""}${err && avv ? " e " : ""}${avv ? `${avv} avvis${avv === 1 ? "o" : "i"}` : ""} nei controlli · tocca per vedere`) : null,
      sett.report && sett.report.scoperti && sett.report.scoperti.length ? avviso(`La generazione ha lasciato ${sett.report.scoperti.length} posti scoperti.`) : null,
      sett.stato === "nuova" && !sett.assegnazioni.length ? el("div", { class: "card" },
        el("p", {}, "Settimana ancora da preparare."),
        el("button", { class: "btn btn-primario btn-blocco", style: "margin-top:10px", onClick: genera }, "Genera i turni")) : null,
      disegnaGiorno(gruppi, (info) => apriPosto(info, sett, giorno, ricarica)),
      liberi && (liberi.liberi.length || liberi.ferie.length || liberi.indisponibili.length) ? el("section", { class: "card" },
        el("div", { class: "card-titolo" }, "Dipendenti liberi"),
        el("div", {}, liberi.liberi.map((p) => el("span", { style: "display:inline-block;margin:0 6px 6px 0" },
          pill(p.nome + (p.avvisi.includes("smonto_notte") ? " · smonta" : ""))))),
        liberi.ferie.length ? el("p", { class: "muto piccolo" }, "Assenti: ", liberi.ferie.map((x) => `${x.nome} (${etichetta("motivo", x.motivo).toLowerCase()})`).join(", ")) : null,
        liberi.indisponibili.length ? el("p", { class: "muto piccolo" }, "Indisponibili: ", liberi.indisponibili.map((x) => x.nome).join(", ")) : null) : null,
      assenti.length && !(liberi && liberi.ferie.length) ? avviso(`In ferie o malattia: ${assenti.length}`) : null,
      riepilogoOre());
  }

  function riepilogoOre() {
    const righe = sett.riepilogo.filter((r) => r.ore || r.ore_sostituzioni);
    if (!righe.length) return null;
    return el("section", { class: "card" },
      el("div", { class: "card-titolo" }, `Ore della settimana · media ${formatOre(sett.media_ore)} h`),
      righe.map((r) => el("div", { style: "margin-bottom:10px" },
        el("div", { style: "display:flex;justify-content:space-between;font-size:14px" },
          el("span", {}, r.nome), el("span", { class: "num muto" }, `${formatOre(r.ore)} h${r.ore_sostituzioni ? ` + ${formatOre(r.ore_sostituzioni)} extra` : ""}`)),
        el("div", { class: "barra" }, el("i", { class: r.max_ore_settimana && r.ore > r.max_ore_settimana ? "sopra" : "",
          style: `width:${Math.min(100, (r.ore / Math.max(1, (sett.media_ore || 36) * 1.4)) * 100)}%` })))));
  }

  function apriControlli() {
    foglio("Controlli della settimana", () => gruppo(...sett.violazioni.map((v) => riga({
      titolo: v.messaggio, sotto: v.data ? ddmm(v.data) : "", freccia: false,
      fine: pill(v.livello === "errore" ? "errore" : "avviso", v.livello === "errore" ? "rosso" : "ambra"),
    }))));
  }

  function ricarica(nuova) { sett = nuova; intestazione(); disegnaBarra(); disegnaCorpo(); }

  async function genera() {
    if (sett.stato === "confermata") return mostra("Riapri la settimana per rigenerarla");
    if (sett.assegnazioni.some((a) => a.origine === "generato") &&
      !(await conferma("I turni generati verranno rifatti. Quelli dei volontari e quelli fissati a mano restano.", { titolo: "Rigenerare?", ok: "Rigenera" }))) return;
    try {
      const r = await conAttesa("Generazione in corso…", "Può richiedere fino a un minuto.", () => api.genera(lun));
      ricarica(r);
      const rep = r.report;
      mostra(rep ? `${etichetta("statoReport", rep.stato)}${rep.scoperti && rep.scoperti.length ? ` · ${rep.scoperti.length} scoperti` : ""}` : "Turni generati");
    } catch (e) { mostraErrore(e); }
  }

  async function menu() {
    const conf = sett.stato === "confermata";
    const voce = await scegli("Azioni", [
      { valore: "genera", titolo: "Genera i turni", sotto: conf ? "Prima riapri la settimana" : "Rifà i posti non fissati" },
      conf ? { valore: "riapri", titolo: "Riapri la settimana", sotto: "Per modificare i turni" }
        : { valore: "conferma", titolo: "Conferma la settimana", sotto: "Rende definitivi i turni" },
      { valore: "email", titolo: "Invia i turni per email", sotto: conf ? "Ai dipendenti e ai volontari" : "Disponibile a settimana confermata" },
      { valore: "rimuovi", titolo: "Togli i turni generati", sotto: "Restano volontari e turni fissati" },
      { valore: "oggi", titolo: "Vai a questa settimana" },
    ]);
    try {
      if (voce === "genera") await genera();
      else if (voce === "conferma") {
        if (sett.violazioni.some((v) => v.livello === "errore") && !(await conferma("Ci sono errori nei controlli. Confermare lo stesso?", { ok: "Conferma" }))) return;
        ricarica(await api.conferma(lun)); mostra("Settimana confermata");
      } else if (voce === "riapri") { ricarica(await api.riapri(lun)); mostra("Settimana riaperta"); }
      else if (voce === "email") apriEmail();
      else if (voce === "rimuovi") {
        if (await conferma("Togliere tutti i turni generati di questa settimana?", { ok: "Togli", pericolo: true })) { ricarica(await api.rimuoviGenerati(lun)); mostra("Turni generati tolti"); }
      } else if (voce === "oggi") location.hash = `#/settimana/${mondayOf(oggi)}/${oggi}`;
    } catch (e) { mostraErrore(e); }
  }

  function apriEmail() {
    foglio("Invio email", (chiudi) => {
      const box = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
      api.statoEmail(lun).then((s) => {
        const da = s.destinatari.filter((d) => d.stato !== "inviata");
        const invia = async (lista, etichettaOk) => {
          if (!(await conferma(`Inviare l'email a ${lista.length} person${lista.length === 1 ? "a" : "e"}?`, { ok: etichettaOk }))) return;
          try {
            const r = await conAttesa("Invio in corso…", "", () => api.inviaEmail(lun, lista.map((d) => d.persona_id), true));
            mostra(`${r.inviate.length} inviate${r.errori.length ? `, ${r.errori.length} con errore` : ""}`, r.errori.length ? "errore" : "");
            chiudi();
          } catch (e) { mostraErrore(e); }
        };
        monta(box, 
          !s.configurato ? avviso("L'invio email non è configurato sul server.", "errore") : null,
          sett.stato !== "confermata" ? avviso("Conferma la settimana prima di inviare.") : null,
          el("div", { class: "griglia2" },
            el("div", { class: "numero" }, el("b", { class: "num" }, String(s.destinatari.filter((d) => d.stato === "inviata").length)), el("span", {}, "già inviate")),
            el("div", { class: "numero" }, el("b", { class: "num" }, String(da.length)), el("span", {}, "da inviare o cambiate"))),
          s.senza_email.length ? avviso(`Senza email: ${s.senza_email.join(", ")}`) : null,
          el("div", { class: "azioni" },
            el("button", { class: "btn btn-primario", disabled: !s.configurato || sett.stato !== "confermata" || !da.length, onClick: () => invia(da, "Invia") }, `Invia a ${da.length}`),
            el("button", { class: "btn", disabled: !s.configurato || sett.stato !== "confermata" || !s.destinatari.length, onClick: () => invia(s.destinatari, "Invia a tutti") }, "A tutti")));
      }).catch((e) => monta(box, avviso(e.message, "errore")));
      return box;
    });
  }

  await riempi(corpo, async () => { sett = await api.settimana(lun); return []; });
  if (!sett) return;
  if (!sett.giorni.includes(giorno)) giorno = lun;
  intestazione(); disegnaBarra(); disegnaCorpo();
}
