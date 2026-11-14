// Guida per i dipendenti in Word, dal testo di docs/GUIDA-dipendenti.md (Markdown semplice: titoli, paragrafi,
// elenchi, tabelle, citazioni, grassetto, codice). Dopo ogni modifica alla guida, dalla cartella del progetto:
//   node docs/crea-guida-docx.js
// Serve il pacchetto npm "docx" (npm install -g docx). La data in copertina è quella della riga «aggiornata al …».
// PDF: soffice --headless --convert-to pdf --outdir docs docs/CVAP-Turnistica-Guida-per-i-dipendenti.docx
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun, Footer, AlignmentType, PageNumber,
  WidthType, ShadingType, BorderStyle, LevelFormat, PageBreak, HeadingLevel, LineRuleType,
} = require("docx");

const path = require("path");
const RADICE = path.join(__dirname, "..");
const [, , mdPath = path.join(RADICE, "docs/GUIDA-dipendenti.md"),
  logoPath = path.join(RADICE, "static/img/logo-croce-verde.png"),
  outPath = path.join(RADICE, "docs/CVAP-Turnistica-Guida-per-i-dipendenti.docx")] = process.argv;
const VERDE = "009541", VERDE_SCURO = "00672D", TESTO = "1B2330", MUTO = "5B6570";
const RIGA_ALT = "F3F6F8", RIQUADRO = "E8F5EC", FONT = "Calibri";
const MARGINE = 1247; // 2,2 cm
const LARGHEZZA = 11906 - 2 * MARGINE; // A4 meno i margini laterali

/** Testo con **grassetto** e `codice` in TextRun. */
function runs(testo, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let ultimo = 0, m;
  while ((m = re.exec(testo))) {
    if (m.index > ultimo) out.push(new TextRun({ text: testo.slice(ultimo, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: "Consolas", ...base }));
    ultimo = m.index + t.length;
  }
  if (ultimo < testo.length) out.push(new TextRun({ text: testo.slice(ultimo), ...base }));
  return out;
}

const pulisci = (t) => t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"); // link: solo il testo

function tabella(righe) {
  const celle = righe.map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => pulisci(c.trim())));
  const [testa, , ...corpo] = celle;
  const n = testa.length;
  // colonne: la prima più stretta se il testo è corto, l'ultima prende il resto
  const lunghezze = testa.map((_, i) => Math.max(...celle.filter((_, j) => j !== 1).map((r) => (r[i] || "").length)));
  const tot = lunghezze.reduce((a, b) => a + Math.min(b, 60) + 8, 0);
  let larghezze = lunghezze.map((l) => Math.round(((Math.min(l, 60) + 8) / tot) * LARGHEZZA));
  larghezze[n - 1] = LARGHEZZA - larghezze.slice(0, n - 1).reduce((a, b) => a + b, 0);
  const bordo = { style: BorderStyle.SINGLE, size: 4, color: "D5DCE3" };
  const bordi = { top: bordo, bottom: bordo, left: bordo, right: bordo };
  const cella = (testo, i, intestazione, alterna) => new TableCell({
    width: { size: larghezze[i], type: WidthType.DXA }, borders: bordi,
    margins: { top: 90, bottom: 90, left: 130, right: 130 },
    shading: intestazione ? { fill: VERDE, type: ShadingType.CLEAR, color: "auto" }
      : alterna ? { fill: RIGA_ALT, type: ShadingType.CLEAR, color: "auto" } : undefined,
    children: [new Paragraph({ spacing: { before: 0, after: 0, line: 264, lineRule: LineRuleType.AUTO },
      children: runs(testo, intestazione ? { bold: true, color: "FFFFFF", size: 20 } : { size: 20 }) })],
  });
  return new Table({
    width: { size: LARGHEZZA, type: WidthType.DXA }, columnWidths: larghezze,
    rows: [
      new TableRow({ tableHeader: true, children: testa.map((t, i) => cella(t, i, true)) }),
      ...corpo.map((r, k) => new TableRow({ cantSplit: true, children: testa.map((_, i) => cella(r[i] || "", i, false, k % 2 === 1)) })),
    ],
  });
}

function corpoDocumento(md) {
  const righe = md.split("\n");
  const out = [];
  let i = 0, numeroLista = 0;
  // il titolo, la riga "aggiornata al" e l'introduzione vanno in copertina
  while (i < righe.length && !righe[i].startsWith("# Parte 1")) i++;
  while (i < righe.length) {
    let r = righe[i];
    if (!r.trim()) { i++; continue; }
    if (r.includes('break-before: page')) { i++; continue; }  // la pagina nuova la decide il generatore
    if (r.trim() === "---") { i++; continue; }
    if (r.startsWith("|")) {
      const blocco = [];
      while (i < righe.length && righe[i].startsWith("|")) blocco.push(righe[i++]);
      out.push(tabella(blocco), new Paragraph({ spacing: { before: 0, after: 80, line: 200, lineRule: LineRuleType.AUTO }, children: [] }));
      continue;
    }
    if (r.startsWith("# ")) {
      // "Parte 1 · Regolamento": nuova pagina con titolo grande
      if (out.length) out.push(new Paragraph({ children: [new PageBreak()] }));  // la Parte 1 segue la copertina
      out.push(new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(r.slice(2))] }));
      i++; continue;
    }
    if (r.startsWith("## ")) {
      out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: /regole in una pagina/i.test(r),
        children: runs(r.slice(3)) }));
      i++; continue;
    }
    if (r.startsWith("### ")) { out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: runs(r.slice(4)) })); i++; continue; }
    if (r.startsWith("> ")) {
      out.push(new Paragraph({
        shading: { fill: RIQUADRO, type: ShadingType.CLEAR, color: "auto" }, indent: { left: 200, right: 200 },
        border: { left: { style: BorderStyle.SINGLE, size: 18, color: VERDE, space: 8 } },
        spacing: { before: 120, after: 200 }, children: runs(pulisci(r.slice(2))),
      }));
      i++; continue;
    }
    const elenco = r.match(/^- (.*)$/), numerato = r.match(/^(\d+)\. (.*)$/);
    if (elenco || numerato) {
      let testo = (elenco ? elenco[1] : numerato[2]);
      i++;
      while (i < righe.length && /^ {2,}\S/.test(righe[i])) testo += " " + righe[i++].trim();
      if (numerato && numerato[1] === "1") numeroLista++;
      out.push(new Paragraph({  // ogni voce resta intera (keepLines); l'elenco può continuare nella pagina dopo
        numbering: elenco ? { reference: "punti", level: 0 } : { reference: `numeri-${numeroLista}`, level: 0 },
        keepLines: true, spacing: { after: 100 }, children: runs(pulisci(testo)),
      }));
      continue;
    }
    // paragrafo: righe consecutive fino a una vuota o a un altro blocco
    let testo = r.trim();
    i++;
    while (i < righe.length && righe[i].trim() && !/^(#|\||- |\d+\. |> |<div)/.test(righe[i])) testo += " " + righe[i++].trim();
    const domanda = testo.match(/^\*\*([^*]+\?)\*\*$/);
    if (domanda) {
      out.push(new Paragraph({ keepNext: true, keepLines: true, spacing: { before: 170, after: 40 },
        children: [new TextRun({ text: domanda[1], bold: true, color: VERDE_SCURO })] }));
    } else {
      // un paragrafo che introduce un elenco o una tabella (finisce con ":") resta con ciò che segue
      out.push(new Paragraph({ keepNext: testo.endsWith(":"), spacing: { after: 140 }, children: runs(pulisci(testo)) }));
    }
  }
  return out;
}

const md = fs.readFileSync(mdPath, "utf8");
const data = (md.match(/aggiornata al ([^\n]+)/) || [, ""])[1].trim();
/** Il paragrafo introduttivo ("Nella Parte 1 ..."), per la copertina. */
function introduzione(testo) {
  const righe = testo.split("\n");
  const i = righe.findIndex((r) => r.startsWith("Nella **Parte 1**"));
  const out = [];
  for (let k = i; k < righe.length && righe[k].trim(); k++) out.push(righe[k].trim());
  return out.join(" ");
}
const logo = fs.readFileSync(logoPath);
const copertina = [
  new Paragraph({ spacing: { before: 1700, after: 600, line: 240, lineRule: LineRuleType.AUTO },
    children: [new ImageRun({ type: "png", data: logo, transformation: { width: 295, height: 130 } })] }),
  new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: "Come funzionano i turni", bold: true, size: 68, color: VERDE, font: FONT })] }),
  new Paragraph({ spacing: { after: 360 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: VERDE, space: 12 } },
    children: [new TextRun({ text: "Regolamento e guida per i dipendenti", size: 36, color: TESTO, font: FONT })] }),
  new Paragraph({ spacing: { before: 360, after: 100 }, children: [new TextRun({ text: "Croce Verde Ascoli Piceno", bold: true, size: 26 })] }),
  new Paragraph({ spacing: { after: 100 }, children: [new TextRun({ text: "Regole e funzionamento del programma dei turni", size: 22, color: MUTO })] }),
  new Paragraph({ spacing: { after: 100 }, children: [new TextRun({ text: `Aggiornata al ${data}`, size: 22, color: MUTO })] }),
  new Paragraph({ spacing: { before: 1400, after: 120, line: 300, lineRule: LineRuleType.AUTO },
    shading: { fill: RIQUADRO, type: ShadingType.CLEAR, color: "auto" }, indent: { left: 120, right: 120 },
    border: { left: { style: BorderStyle.SINGLE, size: 24, color: VERDE, space: 10 } },
    children: runs(introduzione(md), { size: 23 }) }),
  new Paragraph({ children: [new PageBreak()] }),
];

const liste = [{ reference: "punti", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 560, hanging: 300 } } } }] }];
for (let k = 1; k <= 20; k++) {
  liste.push({ reference: `numeri-${k}`, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 560, hanging: 340 } } } }] });
}

const doc = new Document({
  creator: "Croce Verde Ascoli Piceno", title: "Come funzionano i turni: regolamento e guida per i dipendenti",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: TESTO }, paragraph: { spacing: { line: 288, lineRule: LineRuleType.AUTO } } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", next: "Normal", run: { font: FONT, size: 48, bold: true, color: VERDE },
        paragraph: { spacing: { before: 0, after: 240 }, keepNext: true,
          border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: VERDE, space: 6 } } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: VERDE },
        paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, keepLines: true, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "CFE8D8", space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 25, bold: true, color: VERDE_SCURO },
        paragraph: { spacing: { before: 320, after: 120 }, keepNext: true, keepLines: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: liste },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: MARGINE, bottom: 1134, left: MARGINE, right: MARGINE } },
      titlePage: true },
    footers: {
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        border: { top: { style: BorderStyle.SINGLE, size: 4, color: "D5DCE3", space: 6 } }, children: [
        new TextRun({ text: "Croce Verde Ascoli Piceno · Come funzionano i turni · pagina ", size: 18, color: MUTO }),
        new TextRun({ children: [PageNumber.CURRENT], size: 18, color: MUTO })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
    },
    children: [...copertina, ...corpoDocumento(md)],
  }],
});

Packer.toBuffer(doc).then((b) => fs.writeFileSync(outPath, b));
