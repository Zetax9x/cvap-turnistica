import { toast, toastErrore } from "./util.js";

const URL_GENERATORE = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
let caricamentoGeneratore = null;

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
export async function scaricaPdf(sorgenti, titolo, { orientamento = "portrait" } = {}) {
  const area = document.createElement("article");
  area.className = `pdf-esportazione pdf-esportazione-${orientamento}`;
  for (const sorgente of (Array.isArray(sorgenti) ? sorgenti : [sorgenti])) {
    if (!sorgente?.isConnected) continue;
    area.append(sorgente.cloneNode(true));
  }
  area.querySelectorAll(".no-print, button, input, select, textarea").forEach((nodo) => nodo.remove());
  if (!area.childElementCount) throw new Error("Non ci sono dati da esportare in PDF.");

  const contenitore = document.createElement("div");
  contenitore.style.cssText = "position:fixed;left:-100000px;top:0";
  area.style.position = "relative";
  area.style.zIndex = "auto";
  contenitore.append(area);
  document.body.append(contenitore);
  try {
    const html2pdf = await generatorePdf();
    await document.fonts?.ready;
    await html2pdf().set({
      margin: 7,
      filename: nomeFile(titolo),
      image: { type: "jpeg", quality: 0.96 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff", onclone: normalizzaColori },
      jsPDF: { unit: "mm", format: "a4", orientation: orientamento },
      pagebreak: { mode: ["css", "legacy"] },
    }).from(area).save();
    toast("PDF scaricato.", "ok");
  } catch (err) {
    toastErrore(err);
  } finally {
    contenitore.remove();
  }
}
