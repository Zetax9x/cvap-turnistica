// Disegna i turni di una giornata (postazioni → turni → posti) a partire dal payload di /api/settimane/{data}.
import { el, etichetta, orarioTurno, oraInizio, EXTRA } from "/static/js/util.js";
import { icona } from "./ui.js";

const RUOLI = ["autista", "soccorritore"];
const SIGLA = { autista: "A", soccorritore: "S" };

/** Posti della giornata raggruppati: [{postazione, turni: [{fascia, segmento, posti: [{ruolo, assegnazione|null}]}]}] */
export function turniDelGiorno(sett, data) {
  const per = new Map(); // postazione → Map(chiave turno → {fascia, segmento, ruoli:{ruolo:{ass:[], quantita}}})
  const turno = (p, fascia, segmento) => {
    if (!per.has(p)) per.set(p, new Map());
    const m = per.get(p);
    const k = `${fascia}|${segmento}`;
    if (!m.has(k)) m.set(k, { fascia, segmento, ruoli: { autista: { ass: [], quantita: 0 }, soccorritore: { ass: [], quantita: 0 } } });
    return m.get(k);
  };
  for (const f of sett.fabbisogno || []) if (f.data === data) turno(f.postazione, f.fascia, f.segmento).ruoli[f.ruolo].quantita += f.quantita;
  for (const a of sett.assegnazioni) if (a.data === data) turno(a.postazione, a.fascia, a.segmento).ruoli[a.ruolo].ass.push(a);
  // postazioni normali: servono sempre un autista e un soccorritore per turno (giorno 8–20 e notte 20–8), anche mezzi turni
  // dei volontari; se manca una metà del giorno è quella a risultare scoperta. Prima della generazione non si segna nulla.
  if (sett.stato !== "nuova" || sett.assegnazioni.length) {
    for (const p of sett.postazioni || []) {
      for (const fascia of ["giorno", "notte"]) {
        for (const ruolo of RUOLI) {
          const segs = new Set(sett.assegnazioni.filter((a) => a.data === data && a.postazione === p && a.fascia === fascia && a.ruolo === ruolo).map((a) => a.segmento));
          if (!segs.size) turno(p, fascia, "intero").ruoli[ruolo].quantita = Math.max(1, turno(p, fascia, "intero").ruoli[ruolo].quantita);
          else if (fascia === "giorno" && !segs.has("intero")) {
            for (const meta of ["mattina", "pomeriggio"]) if (!segs.has(meta)) turno(p, "giorno", meta).ruoli[ruolo].quantita = 1;
          }
        }
      }
    }
  }
  const ordine = [...(sett.postazioni || []), ...(sett.postazioni_a_richiesta || []), EXTRA];
  const nomi = [...per.keys()].sort((x, y) => {
    const ix = ordine.indexOf(x), iy = ordine.indexOf(y);
    return (ix < 0 ? 99 : ix) - (iy < 0 ? 99 : iy);
  });
  return nomi.map((postazione) => ({
    postazione,
    turni: [...per.get(postazione).values()]
      .sort((a, b) => oraInizio(a.fascia, a.segmento) - oraInizio(b.fascia, b.segmento))
      .map((t) => ({
        fascia: t.fascia, segmento: t.segmento,
        posti: RUOLI.flatMap((ruolo) => {
          const r = t.ruoli[ruolo];
          const vuoti = Math.max(0, r.quantita - r.ass.length);
          return [...r.ass.map((assegnazione) => ({ ruolo, assegnazione })),
            ...Array.from({ length: vuoti }, () => ({ ruolo, assegnazione: null }))];
        }),
      })),
  }));
}

/** Contatore dei posti scoperti in un elenco di postazioni. */
export const scoperti = (gruppi) => gruppi.reduce((n, g) => n + g.turni.reduce((m, t) => m + t.posti.filter((p) => !p.assegnazione).length, 0), 0);

function posto(p, { postazione, fascia, segmento }, suTocco) {
  const a = p.assegnazione;
  const classe = !a ? "vuoto-posto" : a.origine === "volontario" ? "vol" : a.origine === "manuale" ? "man" : "";
  const contenuto = [
    el("span", { class: "ruolo", title: etichetta("ruolo", p.ruolo) }, SIGLA[p.ruolo]),
    el("span", { class: "nome" }, a ? a.persona_nome : "Scoperto"),
    a && a.origine === "sostituzione" ? el("span", { class: "pill pill-ambra" }, "extra") : null,
    a ? el("span", { class: "meta num" }, `${a.ore} h`) : null,
  ];
  const info = { postazione, fascia, segmento, ruolo: p.ruolo, assegnazione: a };
  return suTocco
    ? el("button", { class: `posto ${classe}`, type: "button", onClick: () => suTocco(info) }, contenuto)
    : el("div", { class: `posto ${classe}` }, contenuto);
}

export function disegnaGiorno(gruppi, suTocco) {
  if (!gruppi.length) return el("div", { class: "vuoto" }, "Nessun turno previsto per questo giorno.");
  return gruppi.map((g) => el("section", { class: "postazione" },
    el("div", { class: "postazione-testa" }, g.postazione),
    g.turni.map((t) => el("div", { class: "turno" },
      el("div", { class: "turno-testa" },
        icona(t.fascia === "notte" ? "luna" : "sole", t.fascia === "notte" ? "notte-i" : "giorno-i"),
        orarioTurno(t.fascia, t.segmento)),
      t.posti.map((p) => posto(p, { postazione: g.postazione, fascia: t.fascia, segmento: t.segmento }, suTocco))))));
}
