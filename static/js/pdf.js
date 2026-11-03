import { toast, toastErrore } from "./util.js";

const URL_GENERATORE = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
let caricamentoGeneratore = null;
const LARGHEZZA_FINESTRA_PDF = 1280;  // oltre i 640 px delle regole per il telefono, abbastanza per una pagina A4 orizzontale

function generatorePdf() {
  if (typeof window.html2pdf === "function") return Promise.resolve(window.html2pdf);
  if (caricamentoGeneratore) return caricamentoGeneratore;

  caricamentoGeneratore = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = URL_GENERATORE;
    script.async = true;
    script.onload = () => typeof window.html2pdf === "function"
      ? resolve(window.html2pdf)
      : reject(new Error("Il generatore PDF non è stato caricato correttamente."));
    script.onerror = () => reject(new Error("Impossibile caricare il generatore PDF. Controlla la connessione e riprova."));
    document.head.append(script);
  }).catch((err) => {
    caricamentoGeneratore = null;
    throw err;
  });
  return caricamentoGeneratore;
}

function nomeFile(titolo) {
  const base = String(titolo || "turnistica")
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `${base || "turnistica"}.pdf`;
}

/** Riusa gli stili cartacei, limitandoli alla copia esportata. */
function stiliEsportazione() {
  const regole = [];
  const visita = (elenco, stampa = false) => {
    for (const regola of elenco) {
      if (regola.type === CSSRule.MEDIA_RULE) {
        if (regola.conditionText === "print") visita(regola.cssRules, true);
      } else if (stampa && regola.type === CSSRule.STYLE_RULE) {
        const selettori = regola.selectorText.split(",").map((selettore) => {
          const s = selettore.trim();
          return /^(?:body|:root)(?=[\s.#:[>]|$)/.test(s)
            ? s.replace(/^(?:body|:root)/, ".pdf-esportazione")
            : `.pdf-esportazione ${s}`;
        });
        regole.push(`${selettori.join(",")} { ${regola.style.cssText} }`);
      }
    }
  };
  for (const foglio of document.styleSheets) {
    // I fogli esterni non accessibili non contengono gli stili dell'applicazione.
    try { visita(foglio.cssRules); } catch (err) {
      if (err.name !== "SecurityError") throw err;
    }
  }
  const stile = document.createElement("style");
  stile.textContent = regole.join("\n") + `
    .pdf-esportazione { position: relative; z-index: auto; padding: 0; margin: 0;
      box-sizing: border-box; font-size: 10pt; background: #fff; color: #000; }
    .pdf-esportazione .griglia, .pdf-esportazione .tabella-liberi { width: 100%; min-width: 0; }
    .pdf-esportazione .griglie { display: block; }
    .pdf-esportazione .eq-freccia { display: none; }
    /* la tabella delle statistiche ha 14 colonne: nel PDF testo e spaziature più stretti, così entra nella pagina */
    .pdf-esportazione .tabella-stat { font-size: 7pt; }
    .pdf-esportazione .tabella-stat th, .pdf-esportazione .tabella-stat td { padding: .3rem .35rem; }
    .pdf-esportazione .tabella-stat thead th, .pdf-esportazione .tabella-stat td, .pdf-esportazione .tabella-stat .sort-btn { white-space: normal; }
    .pdf-esportazione .tabella-stat .cella-rapporto { min-width: 0; }
    .pdf-esportazione .table-scroll, .pdf-esportazione .griglia-scroll { overflow: visible; -webkit-mask-image: none; mask-image: none; }
    .pdf-esportazione.pdf-esportazione-tabellone .stampa-liberi { display: none !important; }
    .pdf-esportazione.pdf-esportazione-liberi .stampa-liberi { display: block !important; }
    .pdf-esportazione-liberi .week-tipo, .pdf-esportazione-liberi .badge-stato { display: none; }
    .pdf-esportazione .griglia-blocco[hidden] { display: block; }
  `;
  return stile;
}

// Il paginatore può aggiungere spazio fino al bordo del foglio: non esportare
// una pagina finale bianca dovuta agli arrotondamenti fra pixel e millimetri.
function ritagliaFondoBianco(canvas) {
  const contesto = canvas.getContext("2d");
  for (let fondo = canvas.height; fondo > 0; fondo -= 128) {
    const cima = Math.max(0, fondo - 128);
    const { data } = contesto.getImageData(0, cima, canvas.width, fondo - cima);
    for (let i = data.length - 4; i >= 0; i -= 4) {
      if (data[i + 3] && (data[i] < 250 || data[i + 1] < 250 || data[i + 2] < 250)) {
        const altezza = Math.min(canvas.height, cima + Math.floor(i / 4 / canvas.width) + 3);
        if (altezza === canvas.height) return canvas;
        const ritaglio = document.createElement("canvas");
        ritaglio.width = canvas.width;
        ritaglio.height = altezza;
        ritaglio.getContext("2d").drawImage(canvas, 0, 0);
        return ritaglio;
      }
    }
  }
  return canvas;
}

// html2canvas non interpreta i colori CSS moderni: li risolviamo con il browser
// nella sola copia destinata al PDF, inclusi gradienti e ombre.
function normalizzaColori(documento) {
  const canvas = documento.createElement("canvas");
  canvas.width = canvas.height = 1;
  const contesto = canvas.getContext("2d", { willReadFrequently: true });
  const cache = new Map();
  const proprieta = ["color", "background-color", "border-top-color", "border-right-color",
    "border-bottom-color", "border-left-color", "outline-color", "text-decoration-color",
    "column-rule-color", "fill", "stroke", "background-image", "box-shadow", "text-shadow"];
  const converti = (colore) => {
    if (!cache.has(colore)) {
      contesto.clearRect(0, 0, 1, 1);
      contesto.fillStyle = colore;
      contesto.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = contesto.getImageData(0, 0, 1, 1).data;
      cache.set(colore, `rgba(${r}, ${g}, ${b}, ${a / 255})`);
    }
    return cache.get(colore);
  };
  for (const nodo of documento.querySelectorAll("*")) {
    const stile = documento.defaultView.getComputedStyle(nodo);
    for (const nome of proprieta) {
      const valore = stile.getPropertyValue(nome);
      const normalizzato = valore.replace(/\b(?:color|oklch|oklab|lch|lab)\([^)]*\)/g, converti);
      if (normalizzato !== valore) nodo.style.setProperty(nome, normalizzato, "important");
    }
  }
}

/** Scarica un PDF del contenuto già visibile, senza aprire il dialogo di stampa del browser. */
export async function scaricaPdf(sorgenti, titolo, { orientamento = "portrait", modalita = "" } = {}) {
  const area = document.createElement("article");
  area.className = `pdf-esportazione pdf-esportazione-${orientamento} pdf-esportazione-${modalita}`;
  if (modalita === "liberi") area.classList.add("stampa-liberi-attiva");
  area.style.width = `${(orientamento === "landscape" ? 297 : 210) - 14}mm`;
  for (const sorgente of (Array.isArray(sorgenti) ? sorgenti : [sorgenti])) {
    if (!sorgente?.isConnected) continue;
    area.append(sorgente.cloneNode(true));
  }
  // Questi pulsanti contengono dati, non comandi (celle, giorni, ordinamenti, righe dell'equità): conserviamo nomi e date.
  // I comandi veri hanno sempre la classe .btn e vengono tolti qui sotto.
  for (const pulsante of area.querySelectorAll("button:not(.btn)")) {
    const testo = document.createElement("span");
    testo.className = pulsante.className;
    testo.append(...pulsante.childNodes);
    pulsante.replaceWith(testo);
  }
  area.querySelectorAll(".no-print, button, input, select, textarea").forEach((nodo) => nodo.remove());
  if (!area.childElementCount) throw new Error("Non ci sono dati da esportare in PDF.");

  const contenitore = document.createElement("div");
  contenitore.style.cssText = "position:fixed;left:-100000px;top:0";
  area.style.position = "relative";
  area.style.zIndex = "auto";
  contenitore.append(area);
  document.body.append(contenitore);
  const stile = stiliEsportazione();
  document.head.append(stile);
  try {
    const html2pdf = await generatorePdf();
    await document.fonts?.ready;
    // Una tabella più larga del foglio non va tagliata: si allarga l'area e il generatore rimpicciolisce tutto alla
    // larghezza della pagina (proporzioni e salti pagina restano coerenti).
    const larghezza = Math.ceil(area.scrollWidth);
    const troppoLarga = larghezza > area.clientWidth + 1;
    if (troppoLarga) area.style.width = `${larghezza}px`;
    const esportazione = html2pdf().set({
      margin: 7,
      filename: nomeFile(titolo),
      image: { type: "jpeg", quality: 0.96 },
      html2canvas: {
        scale: 2, useCORS: true, backgroundColor: "#ffffff", onclone: normalizzaColori,
        // il PDF si disegna sempre con il layout da PC, anche se lo scarichi dal telefono: le regole per lo schermo
        // piccolo (un giorno alla volta, celle strette) non devono finire sul foglio
        windowWidth: Math.max(larghezza, LARGHEZZA_FINESTRA_PDF),
        // il generatore cattura di norma la sola larghezza della pagina: con una tabella più larga va detto
        ...(troppoLarga ? { width: larghezza } : {}),
      },
      jsPDF: { unit: "mm", format: "a4", orientation: orientamento },
      // le righe delle tabelle e le intestazioni non si spezzano tra due pagine
      pagebreak: { mode: ["css", "legacy"], avoid: ["tr", "h2", "h3"] },
    }).from(area);
    const canvas = await esportazione.toCanvas().get("canvas");
    await esportazione.set({ canvas: ritagliaFondoBianco(canvas) }).save();
    toast("PDF scaricato.", "ok");
  } catch (err) {
    toastErrore(err);
  } finally {
    contenitore.remove();
    stile.remove();
  }
}
