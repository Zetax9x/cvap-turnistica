// Azioni su un posto del turno: assegnare, sostituire, togliere.
import { api } from "/static/js/api.js";
import { el, clear, etichetta, orarioTurno, dataLunga } from "/static/js/util.js";
import { foglio, gruppo, riga, avviso, avatar, pill, conferma, mostra, mostraErrore, icona, caricamento, monta } from "./ui.js";

const titoloPosto = (i, data) => `${i.postazione} · ${orarioTurno(i.fascia, i.segmento)} · ${etichetta("ruolo", i.ruolo)} · ${dataLunga(data)}`;

/** `ricarica(settimanaAggiornata)` viene chiamata dopo ogni modifica riuscita. */
export function apriPosto(info, sett, data, ricarica) {
  const a = info.assegnazione;
  const bloccata = sett.stato === "confermata";
  if (!a) return apriAssegna(info, sett, data, ricarica, bloccata);
  foglio(a.persona_nome, (chiudi) => [
    el("p", { class: "muto" }, titoloPosto(info, data)),
    el("div", {}, pill(etichetta("origine", a.origine), a.origine === "volontario" ? "verde" : a.origine === "manuale" ? "blu" : ""),
      " ", el("span", { class: "muto piccolo num" }, `${a.ore} ore`)),
    bloccata ? avviso("La settimana è confermata: riaprila per modificare i turni.") : null,
    el("div", { class: "azioni" },
      el("button", { class: "btn", disabled: bloccata, onClick: () => { chiudi(); apriSostituti(a, sett, data, ricarica); } }, icona("cambio"), "Sostituisci"),
      el("button", { class: "btn btn-pericolo", disabled: bloccata, onClick: async () => {
        if (!(await conferma(`Togliere ${a.persona_nome} da questo turno?`, { ok: "Togli", pericolo: true }))) return;
        try {
          ricarica(await (async () => { await api.eliminaAssegnazione(a.id); return api.settimana(sett.inizio); })());
          chiudi(); mostra("Turno tolto");
        } catch (e) { mostraErrore(e); }
      } }, icona("cestino"), "Togli")),
  ]);
}

/**
 * Cerca tra le persone attive adatte al ruolo; se il nome non esiste propone di crearlo come volontario.
 * `suScelta({persona_id} | {nome_volontario}, nome)` viene chiamata alla scelta. Restituisce i nodi da mettere nel foglio.
 */
export function sceltaPersona(ruolo, suScelta) {
  const elenco = el("div");
  const cerca = el("input", { class: "input", type: "search", placeholder: "Cerca o scrivi un nome nuovo", "aria-label": "Cerca persona",
    autocapitalize: "words", autocomplete: "off" });
  let persone = [];
  const disegna = () => {
    const q = cerca.value.trim();
    const adatte = persone.filter((p) => p.attivo && (ruolo === "soccorritore" || p.qualifica === "autista")
      && p.nome.toLowerCase().includes(q.toLowerCase()));
    const esatto = persone.some((p) => p.nome.toLowerCase() === q.toLowerCase());
    monta(elenco,
      adatte.length ? gruppo(...adatte.map((p) => riga({
        titolo: p.nome, sotto: `${etichetta("tipo", p.tipo)} · ${etichetta("qualifica", p.qualifica)}`, avatar: avatar(p.nome, p.tipo), freccia: false,
        onClick: () => suScelta({ persona_id: p.id }, p.nome),
      }))) : el("div", { class: "vuoto" }, q ? "Nessuna persona con questo nome." : "Nessuna persona trovata."),
      q && !esatto ? el("button", { class: "btn btn-blocco", style: "margin-top:10px", onClick: () => suScelta({ nome_volontario: q }, q) },
        icona("piu"), `Nuovo volontario «${q}»`) : null);
  };
  cerca.addEventListener("input", disegna);
  monta(elenco, caricamento());
  api.persone().then((l) => { persone = l; disegna(); }).catch((e) => monta(elenco, avviso(e.message, "errore")));
  return [cerca, elenco];
}

function apriAssegna(info, sett, data, ricarica, bloccata) {
  foglio("Assegna un posto", (chiudi) => [
    el("p", { class: "muto" }, titoloPosto(info, data)),
    bloccata ? avviso("La settimana è confermata: riaprila per modificare i turni.") : null,
    bloccata ? null : sceltaPersona(info.ruolo, async (chi, nome) => {
      try {
        ricarica(await api.aggiungiAssegnazione(sett.inizio, {
          data, postazione: info.postazione, fascia: info.fascia, segmento: info.segmento, ruolo: info.ruolo, ...chi,
        }));
        chiudi(); mostra(`${nome} assegnato`);
      } catch (e) { mostraErrore(e); }
    })]);
}

function apriSostituti(a, sett, data, ricarica) {
  foglio(`Sostituisci ${a.persona_nome}`, (chiudi) => {
    const corpo = el("div", { style: "display:flex;flex-direction:column;gap:12px" }, caricamento());
    api.sostituti(a.id).then((r) => {
      const scegli = async (persona, nota) => {
        if (nota && !(await conferma(`${persona.nome}: ${nota}. Procedo comunque?`, { ok: "Procedi" }))) return;
        try {
          ricarica(await api.sostituisci(a.id, persona.persona_id));
          chiudi(); mostra(`${persona.nome} al posto di ${a.persona_nome}`);
        } catch (e) { mostraErrore(e); }
      };
      monta(corpo, 
        r.assenza ? avviso(`${a.persona_nome} è in ${r.assenza}.`) : null,
        r.candidati.length ? gruppo(...r.candidati.map((c) => riga({
          titolo: c.nome,
          sotto: [`${c.ore_dopo} h dopo`, ...c.regole, ...c.avvisi].join(" · "),
          fine: c.regole.length ? pill("regole", "rosso") : c.avvisi.length ? pill("avviso", "ambra") : pill("ok", "verde"),
          freccia: false,
          onClick: () => scegli(c, c.regole.length ? c.regole.join("; ") : ""),
        }))) : el("div", { class: "vuoto" }, "Nessun sostituto disponibile."),
        r.catene && r.catene.length ? el("div", { class: "card-titolo" }, "Scambio a catena") : null,
        ...(r.catene || []).map((c) => riga({
          titolo: `${c.prende.nome} prende il turno`, sotto: `e cede un suo turno a ${c.copre.nome}`, freccia: false,
          onClick: async () => {
            try {
              ricarica(await api.catena(a.id, { persona_id: c.prende.persona_id, ceduto_id: c.ceduto.id, sostituto_id: c.copre.persona_id }));
              chiudi(); mostra("Scambio a catena fatto");
            } catch (e) { mostraErrore(e); }
          },
        })));
    }).catch((e) => monta(corpo, avviso(e.message, "errore")));
    return corpo;
  });
}
