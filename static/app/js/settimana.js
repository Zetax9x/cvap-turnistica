// Scheda «Settimana»: giorno per giorno, correzioni a mano, genera, conferma, invio email.
import { api } from "/static/js/api.js";
import { el, clear, todayISO, addDays, mondayOf, ddmm, GIORNI_BREVI, parseISO, formatOre, etichetta } from "/static/js/util.js";
import { testata, icona, riempi, pill, avviso, foglio, gruppo, riga, conferma, scegli, conAttesa, mostra, mostraErrore, caricamento, monta } from "./ui.js";
import { turniDelGiorno, disegnaGiorno, scoperti } from "./turni.js";
import { apriPosto } from "./modifica.js";
import { disegnaPrepara } from "./prepara.js";

const STATO = { nuova: ["Da preparare", ""], bozza: ["Bozza", "ambra"], confermata: ["Confermata", "verde"] };

export default async function settimana(root, { parametri }) {
  const lun = mondayOf(parametri[0] || todayISO());
  const oggi = todayISO();
  let giorno = (parametri[1] && parametri[1] !== "prepara" ? parametri[1] : null) || (mondayOf(oggi) === lun ? oggi : lun);
  let sett = null;
  let generati = null;  // payload della versione «Generati», se la si sta guardando
  let vista = parametri[1] === "prepara" ? "prepara" : "turni";

  const barra = el("div", { class: "giorni" });
  const corpo = el("div", { class: "contenuto" });
  const titolo = el("div", { style: "display:contents" });
  const selettore = el("div", { class: "contenuto", style: "padding-bottom:8px" });
  root.append(titolo, selettore, barra, corpo);

  function disegnaSelettore() {
    monta(selettore, el("div", { class: "segmenti", role: "group", "aria-label": "Vista" },
      [["turni", "Turni"], ["prepara", "Prepara"]].map(([v, t]) => el("button", { type: "button", "aria-pressed": String(vista === v),
        onClick: () => { vista = v; history.replaceState(null, "", `#/settimana/${lun}/${v === "prepara" ? "prepara" : giorno}`); disegnaSelettore(); disegnaBarra(); disegnaCorpo(); } }, t))));
  }

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
    barra.hidden = vista === "prepara";
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
    if (vista === "prepara") { monta(corpo, disegnaPrepara(sett, ricarica)); return; }
    const gruppi = turniDelGiorno(generati || sett, giorno);
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
      generati ? el("div", { class: "avviso" }, "Stai guardando i turni Generati: sola lettura, come li ha prodotti il programma. ",
        el("button", { class: "btn", style: "min-height:36px;margin-top:8px", onClick: () => { generati = null; disegnaBarra(); disegnaCorpo(); } }, "Torna agli Effettivi")) : null,
      disegnaGiorno(gruppi, generati ? null : (info) => apriPosto(info, sett, giorno, ricarica)),
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
          el("span", {}, r.nome), el("span", { class: "num muto" }, `${formatOre(r.ore)} h${r.ore_ferie ? ` + ${formatOre(r.ore_ferie)} ferie/malattia` : ""}${r.ore_sostituzioni ? ` + ${formatOre(r.ore_sostituzioni)} extra` : ""}`)),
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
      { valore: "generati", titolo: "Vedi i turni Generati", sotto: "Confronto con quanto prodotto dal programma" },
      sett.report ? { valore: "report", titolo: "Report della generazione", sotto: "Qualità, scoperti, festività" } : null,
      { valore: "oggi", titolo: "Vai a questa settimana" },
    ].filter(Boolean));
    try {
      if (voce === "genera") await genera();
      else if (voce === "conferma") {
        if (sett.violazioni.some((v) => v.livello === "errore") && !(await conferma("Ci sono errori nei controlli. Confermare lo stesso?", { ok: "Conferma" }))) return;
        ricarica(await api.conferma(lun)); mostra("Settimana confermata");
      } else if (voce === "riapri") { ricarica(await api.riapri(lun)); mostra("Settimana riaperta"); }
      else if (voce === "email") apriEmail();
      else if (voce === "generati") {
        generati = await conAttesa("Carico i turni generati…", "", () => api.tabelloneGenerato(lun));
        if (vista !== "turni") { vista = "turni"; disegnaSelettore(); }
        disegnaBarra(); disegnaCorpo();
      } else if (voce === "report") apriReport();
      else if (voce === "rimuovi") {
        if (await conferma("Togliere tutti i turni generati di questa settimana?", { ok: "Togli", pericolo: true })) { ricarica(await api.rimuoviGenerati(lun)); mostra("Turni generati tolti"); }
      } else if (voce === "oggi") location.hash = `#/settimana/${mondayOf(oggi)}/${oggi}`;
    } catch (e) { mostraErrore(e); }
  }

  function apriReport() {
    const r = sett.report;
    const q = r.qualita;
    foglio("Report della generazione", () => [
      el("div", {}, pill(etichetta("statoReport", r.stato) || r.stato, r.stato === "ottimo" ? "verde" : r.stato === "ammissibile" ? "ambra" : "rosso")),
      r.messaggio ? el("p", {}, r.messaggio) : null,
      el("div", { class: "griglia2" },
        r.durata_s !== undefined ? el("div", { class: "numero" }, el("b", { class: "num" }, `${formatOre(Math.round(r.durata_s * 10) / 10)} s`), el("span", {}, "durata")) : null,
        r.media_ore ? el("div", { class: "numero" }, el("b", { class: "num" }, `${formatOre(Math.round(r.media_ore * 10) / 10)} h`), el("span", {}, "media ore")) : null,
        q ? el("div", { class: "numero" }, el("b", { class: "num" }, `${formatOre(q.gap_pct)}%`), el("span", {}, "distanza dall'ottimo")) : null,
        q ? el("div", { class: "numero" }, el("b", { class: "num" }, String(Math.round(q.punteggio))), el("span", {}, "penalità (meno è meglio)")) : null),
      r.qualita_precedente ? el("p", { class: "muto piccolo" }, `Generazione precedente: penalità ${Math.round(r.qualita_precedente.punteggio)}.`) : null,
      (r.scoperti || []).length ? [el("div", { class: "card-titolo" }, `Posti scoperti (${r.scoperti.length})`),
        gruppo(...r.scoperti.map((t) => riga({ titolo: `${ddmm(t.data)} · ${t.postazione}`, sotto: `${etichetta("fasciaBreve", t.fascia)} · ${etichetta("ruolo", t.ruolo)}`, freccia: false })))] : avviso("Nessun posto scoperto.", "ok"),
    ]);
  }

  function apriEmail() {
    foglio("Invio email", (chiudi) => {
      const box = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
      api.statoEmail(lun).then((s) => {
        const STATO_EMAIL = { da_inviare: ["da inviare", "ambra"], inviata: ["inviata", "verde"], cambiata: ["cambiata", "rosso"] };
        const scelti = new Set(s.destinatari.filter((d) => d.stato !== "inviata").map((d) => d.persona_id));
        const pronto = s.configurato && sett.stato === "confermata";
        const responsabili = el("input", { type: "checkbox", checked: true });
        const conta = el("span", { class: "muto piccolo" });
        const bottone = el("button", { class: "btn btn-primario btn-blocco", disabled: !pronto }, "Invia");
        const aggiorna = () => {
          conta.textContent = `${scelti.size} di ${s.destinatari.length} selezionati`;
          bottone.textContent = `Invia a ${scelti.size}${responsabili.checked ? " e ai responsabili" : ""}`;
          bottone.disabled = !pronto || (!scelti.size && !responsabili.checked);
        };
        const righe = s.destinatari.map((d) => {
          const cb = el("input", { type: "checkbox", checked: scelti.has(d.persona_id), "aria-label": d.nome, onChange: () => {
            if (cb.checked) scelti.add(d.persona_id); else scelti.delete(d.persona_id);
            aggiorna();
          } });
          const [t, tipo] = STATO_EMAIL[d.stato] || [d.stato, ""];
          return el("label", { class: "riga", style: "cursor:pointer" }, cb,
            el("div", { class: "riga-corpo" }, el("div", { class: "riga-titolo" }, d.nome), el("div", { class: "riga-sotto" }, d.email)), pill(t, tipo));
        });
        const imposta = (tutti) => {
          scelti.clear();
          if (tutti) s.destinatari.forEach((d) => scelti.add(d.persona_id));
          righe.forEach((r, i) => { r.querySelector("input").checked = tutti; });
          aggiorna();
        };
        bottone.addEventListener("click", async () => {
          const ids = [...scelti];
          if (!(await conferma(`Inviare l'email a ${ids.length} person${ids.length === 1 ? "a" : "e"}${responsabili.checked ? " e ai responsabili" : ""}?`, { ok: "Invia" }))) return;
          try {
            const r = await conAttesa("Invio in corso…", "", () => api.inviaEmail(lun, ids, responsabili.checked));
            mostra(`${r.inviate.length} inviate${r.errori.length ? `, ${r.errori.length} con errore: ${r.errori[0].errore}` : ""}`, r.errori.length ? "errore" : "");
            chiudi();
          } catch (e) { mostraErrore(e); }
        });
        const prova = el("input", { class: "input", type: "email", inputMode: "email", autocapitalize: "off", placeholder: "Tuo indirizzo per un'email di prova" });
        const provaBtn = el("button", { class: "btn", onClick: async () => {
          if (!prova.value.trim()) return mostra("Scrivi un indirizzo", "errore");
          provaBtn.disabled = true;
          try { const r = await api.provaEmail(lun, prova.value.trim()); mostra(`Email di prova inviata a ${r.inviata_a}`); } catch (e) { mostraErrore(e); }
          provaBtn.disabled = false;
        } }, "Invia prova");
        monta(box,
          !s.configurato ? avviso("L'invio email non è configurato sul server.", "errore") : null,
          sett.stato !== "confermata" ? avviso("Conferma la settimana prima di inviare.") : null,
          s.senza_email.length ? avviso(`Senza email: ${s.senza_email.join(", ")}`) : null,
          el("div", { class: "azioni" },
            el("button", { class: "btn", onClick: () => imposta(true) }, "Tutti"),
            el("button", { class: "btn", onClick: () => imposta(false) }, "Nessuno")),
          conta,
          s.destinatari.length ? gruppo(...righe) : el("div", { class: "vuoto" }, "Nessun destinatario con turni."),
          el("label", { class: "interruttore", style: "background:var(--card);border-radius:14px;padding:0 14px" }, el("span", {}, "Includi i responsabili"), responsabili),
          bottone,
          el("div", { class: "card-titolo", style: "margin:6px 0 0" }, "Email di prova"),
          el("div", { class: "azioni" }, prova, provaBtn));
        responsabili.addEventListener("change", aggiorna);
        aggiorna();
      }).catch((e) => monta(box, avviso(e.message, "errore")));
      return box;
    });
  }

  await riempi(corpo, async () => { sett = await api.settimana(lun); return []; });
  if (!sett) return;
  if (!sett.giorni.includes(giorno)) giorno = lun;
  intestazione(); disegnaSelettore(); disegnaBarra(); disegnaCorpo();
}
