// Turni di un dipendente nella settimana: colleghi, totali, PDF e calendario .ics sul telefono.
import { api } from "/static/js/api.js";
import { el, todayISO, mondayOf, addDays, ddmm, parseISO, GIORNI_BREVI, indiceGiorno, etichetta, orarioTurno, oraInizio, formatOre, etichettaParti } from "/static/js/util.js";
import { testata, icona, pill, avviso, foglio, gruppo, riga, conferma, mostra, mostraErrore, monta, caricamento } from "./ui.js";

/** Colleghi che condividono (anche solo in parte) il turno nella stessa postazione. */
function colleghi(s, t) {
  const dal = oraInizio(t.fascia, t.segmento), al = dal + t.ore;
  const nomi = new Map();
  for (const a of s.assegnazioni) {
    if (a.persona_id === t.persona_id || a.data !== t.data || a.postazione !== t.postazione
      || (a.postazione === "Assistenze ed Extra" && a.segmento !== t.segmento)) continue;
    const inizio = oraInizio(a.fascia, a.segmento);
    const da = Math.max(dal, inizio), fino = Math.min(al, inizio + a.ore);
    if (da < fino) nomi.set(a.persona_nome + (da === dal && fino === al ? "" : ` (${da % 24}–${fino % 24})`), { da, fino });
  }
  return [...nomi].sort((x, y) => x[1].da - y[1].da || x[0].localeCompare(y[0], "it")).map((x) => x[0]).join(", ");
}

export default async function dipendente(root, { parametri }) {
  const id = Number(parametri[0]);
  const lun = mondayOf(parametri[1] || todayISO());
  const corpo = el("div", { class: "contenuto" }, caricamento());
  const testa = el("div", { style: "display:contents" });
  root.append(testa, corpo);
  const vai = (n) => { location.hash = `#/dipendente/${id}/${addDays(lun, 7 * n)}`; };
  try {
    const [persone, s] = await Promise.all([api.persone(), api.settimana(lun)]);
    const p = persone.find((x) => x.id === id);
    if (!p) throw new Error("Persona non trovata");
    monta(testa, testata(p.nome, {
      indietro: () => { location.hash = `#/persona/${id}`; },
      sotto: `${ddmm(lun)} – ${ddmm(addDays(lun, 6))} · ${s.stato === "confermata" ? "confermata" : s.stato === "bozza" ? "bozza" : "da preparare"}`,
      azioni: [
        el("button", { class: "btn btn-icona", "aria-label": "Settimana precedente", onClick: () => vai(-1) }, icona("indietro")),
        el("button", { class: "btn btn-icona", "aria-label": "Settimana successiva", onClick: () => vai(1) }, icona("avanti")),
      ] }));
    const ferie = new Map(s.ferie.filter((x) => x.persona_id === id).map((x) => [x.data, x.motivo]));
    const indisp = new Map();
    for (const x of s.indisponibilita.filter((x) => x.persona_id === id)) {
      if (!indisp.has(x.data)) indisp.set(x.data, new Set());
      indisp.get(x.data).add(x.parte);
    }
    const errori = new Set(s.violazioni.filter((v) => v.persona_id === id && v.livello === "errore" && v.data).map((v) => v.data));
    const r = s.riepilogo.find((x) => x.persona_id === id);
    monta(corpo,
      ...s.giorni.map((g) => {
        const turni = s.assegnazioni.filter((a) => a.persona_id === id && a.data === g)
          .sort((a, b) => oraInizio(a.fascia, a.segmento) - oraInizio(b.fascia, b.segmento));
        const festivo = s.festivi.find((f) => f.data === g);
        return el("section", { class: "card", style: g === todayISO() ? "outline:2px solid var(--verde)" : null },
          el("div", { style: "display:flex;align-items:center;gap:8px;margin-bottom:6px" },
            el("strong", { style: "flex:1" }, `${GIORNI_BREVI[indiceGiorno(g)]} ${parseISO(g).getDate()}/${parseISO(g).getMonth() + 1}`),
            festivo ? pill(festivo.nome, "rosso") : null,
            errori.has(g) ? pill("da controllare", "ambra") : null),
          turni.length ? turni.map((a) => el("div", { class: `posto ${a.origine === "volontario" ? "vol" : a.origine === "manuale" ? "man" : ""}`, style: "flex-wrap:wrap" },
            icona(a.fascia === "notte" ? "luna" : "sole", a.fascia === "notte" ? "notte-i" : "giorno-i"),
            el("span", { class: "nome", style: "white-space:normal" }, `${orarioTurno(a.fascia, a.segmento)} · ${a.postazione} · ${etichetta("ruolo", a.ruolo)}`),
            a.origine === "sostituzione" ? pill("extra", "ambra") : null,
            colleghi(s, a) ? el("span", { class: "muto piccolo", style: "flex-basis:100%;padding-left:28px" }, `Con ${colleghi(s, a)}`) : null))
            : ferie.has(g) ? pill(etichetta("motivo", ferie.get(g)), ferie.get(g) === "malattia" ? "rosso" : "blu")
              : el("span", { class: "muto" }, indisp.has(g) ? `Indisponibile: ${etichettaParti(indisp.get(g)).toLowerCase()}` : "Riposo"));
      }),
      el("section", { class: "card" }, el("div", { class: "card-titolo" }, "Totali della settimana"),
        el("div", { class: "griglia2" },
          num(`${formatOre(r ? r.ore : 0)} h`, "ore totali"), num(r ? `${formatOre(r.ore_giorno)} / ${formatOre(r.ore_notte)}` : "—", "giorno / notte"),
          num(r ? r.turni_weekend : 0, "turni nel weekend"), num(s.media_ore ? `${formatOre(Math.round(s.media_ore * 10) / 10)} h` : "—", "media dipendenti")),
        r && r.ore_sostituzioni ? el("p", { class: "muto piccolo", style: "margin-top:10px" }, `Più ${formatOre(r.ore_sostituzioni)} ore di sostituzioni.`) : null),
      el("a", { class: "btn btn-blocco", href: `/api/settimane/${lun}/pdf/${id}`, target: "_blank", rel: "noopener" }, icona("pdf"), "PDF dei turni"),
      el("button", { class: "btn btn-blocco", onClick: () => calendario(p) }, icona("settimana"), "Calendario sul telefono"));
  } catch (e) {
    if (e && e.status === 401) return;
    monta(corpo, avviso(e.message || "Errore", "errore"));
  }
}

const num = (n, testo) => el("div", { class: "numero" }, el("b", { class: "num" }, String(n)), el("span", {}, testo));

/** Link .ics della persona: copia, aggiungi al calendario (webcal) o creane uno nuovo. */
function calendario(p) {
  foglio("Calendario sul telefono", (chiudi) => {
    const box = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
    const mostraLink = (percorso) => {
      const url = `${location.origin}${percorso}`;
      monta(box,
        el("p", { class: "muto" }, `I turni confermati di ${p.nome} compaiono nel calendario e si aggiornano da soli, cambi turno compresi. Il link è personale: daglielo solo a lui o a lei.`),
        el("input", { class: "input", readOnly: true, value: url, "aria-label": "Link del calendario", onFocus: (e) => e.target.select() }),
        el("div", { class: "azioni" },
          el("button", { class: "btn", onClick: async () => {
            try { await navigator.clipboard.writeText(url); mostra("Link copiato"); } catch { mostra("Copia non riuscita: tieni premuto sul link per copiarlo", "errore"); }
          } }, "Copia link"),
          el("a", { class: "btn btn-primario", href: `webcal://${location.host}${percorso}` }, "Aggiungi al calendario")),
        el("button", { class: "btn btn-pericolo btn-blocco", onClick: async () => {
          if (!(await conferma(`Il link attuale smetterà subito di funzionare: ${p.nome} dovrà aggiungere quello nuovo. Serve se il link è finito a chi non deve vederlo.`, { titolo: "Creare un nuovo link?", ok: "Nuovo link", pericolo: true }))) return;
          try { mostraLink((await api.nuovoCalendario(p.id)).percorso); mostra("Nuovo link creato"); } catch (e) { mostraErrore(e); }
        } }, "Crea un nuovo link"));
    };
    api.calendario(p.id).then((r) => mostraLink(r.percorso)).catch((e) => monta(box, avviso(e.message, "errore")));
    return box;
  });
}
