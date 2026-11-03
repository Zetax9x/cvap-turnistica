# Design audit: CVAP Turnistica

Report unico che unisce la critique di design e l'audit tecnico dell'interfaccia in `static/`. È il terzo giro, fatto il 3 novembre 2026 dopo la correzione dei problemi importanti del secondo.

## In breve

- **Nessun problema critico e nessun problema importante aperto.** Restano 4 problemi minori, tutti da decidere o da provare con strumenti che qui non ho.
- I punteggi sono saliti a ogni giro. L'audit tecnico è ora **Excellent**.
- Durante il giro ho trovato e corretto due difetti che avevo introdotto io con i comandi da 44 px (vedi "Corretti durante il giro").

| Valutazione | Primo giro | Secondo giro | Terzo giro | Fascia |
|---|---|---|---|---|
| Critique (design) | 28/40 | 31/40 | **32/40** | Good |
| Audit (tecnico) | 14/20 | 16/20 | **18/20** | Excellent |

| Area dell'audit | 1° giro | 2° giro | 3° giro |
|---|---|---|---|
| Accessibilità | 3/4 | 4/4 | 4/4 |
| Prestazioni | 3/4 | 3/4 | 3/4 |
| Temi e colori | 3/4 | 3/4 | 3/4 |
| Adattamento ai telefoni | 2/4 | 3/4 | 4/4 |
| Coerenza dell'implementazione | 3/4 | 3/4 | 4/4 |

Problemi aperti: da **16** (3 critici, 8 importanti, 5 minori) a **11** (0, 4, 7) a **4** (0, 0, 4).

## Come sono stati fatti i controlli

- **Critique:** valutazione in un unico contesto (nessun sotto-agente), con rilevatore automatico. Screenshot della Settimana a 390 px (primo schermo) e misure su tutte e sei le viste. L'evidenziazione nel browser non è stata fatta.
- **Audit:** misure nel browser su tutte e sei le viste a 1440 e 390 px: id doppi, controlli senza nome, campi senza etichetta, una `h1` per vista, scorrimento orizzontale della pagina, controlli sotto i 44 px con il tocco, testo sotto gli 11,5 px, tempo di ridisegno della Settimana. Rilevatore su `static/index.html`, `static/js` e `static/style.css`.
- **Risultati delle misure:** nessun id doppio, nessun controllo o campo senza nome, una `h1` per vista, nessuno scorrimento orizzontale a 390 px, nessun controllo sotto i 44 px con il tocco in nessuna vista, nessun testo sotto gli 11,5 px, ridisegno della Settimana in 15–21 ms, nessun errore in console.
- **Non provato:** un telefono vero, l'orientamento orizzontale, un lettore di schermo vero, la stampa dopo le ultime modifiche.
- **Eccezioni registrate nel rilevatore:** i bordi laterali colorati (`side-tab`) sono esclusi solo in `static/style.css`, con motivo scritto in `.impeccable/config.json`. Il tratteggio di "turno non richiesto" è un falso positivo: serve in bianco e nero.

## Problemi critici

Nessuno.

## Problemi importanti

Nessuno.

---

## Problemi minori

### M1. Calendario su telefono: 42 righe
- **Pagina:** Calendario (telefono).
- **Cosa non va:** l'elenco dei giorni è lungo (circa 2100 px) e i giorni coperti occupano 44 px ognuno.
- **Cosa proponiamo:** una riga per settimana, che si apre sui giorni solo se c'è un'eccezione. È un cambio di struttura: da decidere.
- **Comando consigliato:** `/impeccable shape`

### M2. Titolo dentro la riga cliccabile
- **Pagine:** Settimana (pannello "Turni da coprire") e Impostazioni (sezioni richiudibili).
- **Cosa non va:** il titolo (`h2`) sta dentro `<summary>`: alcuni lettori di schermo perdono il livello del titolo. Non l'ho provato con un lettore vero.
- **Cosa proponiamo:** provarlo con un lettore di schermo prima di cambiare; una correzione semplice non c'è senza duplicare il titolo.
- **Comando consigliato:** `/impeccable polish`

### M3. Indirizzi email reali visibili
- **Pagina:** Personale.
- **Cosa non va:** la tabella mostra gli indirizzi email. In una stampa o in uno screenshot condiviso diventano dati personali visibili.
- **Cosa proponiamo:** nasconderli nelle stampe, o mostrarli solo nella finestra "Modifica". È una scelta sulla privacy, tua.
- **Comando consigliato:** `/impeccable polish`

### M4. Colori scritti a mano nelle regole di stampa
- **Pagine:** tutte (stampa e stati). Codice: `static/style.css`.
- **Cosa non va:** circa 204 valori esadecimali fuori da `:root`, in gran parte nelle regole di stampa. Nessun difetto visibile; cambiare i colori richiede di toccare molti punti.
- **Cosa proponiamo:** token solo per i pochi colori di stato che ricorrono; quelli specifici della stampa restano.
- **Comando consigliato:** `/impeccable colorize`

---

## Corretti durante il giro

| Difetto | Dove nasceva | Correzione |
|---|---|---|
| Intestazione del giorno senza spazio tra nome e data ("Mar03/11"), cella più alta | Comandi da 44 px: `.giorno-btn` era diventato `inline-flex` | Spazio tra nome e data (`gap`), intestazione allineata al centro |
| Freccia dei pannelli "Disponibilità" e "Richieste" più bassa del titolo | `align-items: center` aggiunto per l'altezza minima | `align-content: center`, freccia alla stessa altezza del titolo |

## Risolti dal primo e dal secondo giro

| Voce | Cosa è stato fatto |
|---|---|
| Settimana su telefono: due giorni su sette | Barra dei giorni con i posti scoperti, un giorno alla volta |
| Settimana su telefono: tabellone sotto il primo schermo | Legenda e filtri dietro un pulsante, pannelli da una riga, banner più corto: il selettore dei giorni passa da 876 a circa 610 px |
| Settimana su PC: colonna vuota | "Controlli" a tutta larghezza sopra il Riepilogo ore |
| Tabelle larghe tagliate | Sfumatura sul bordo destro, barra di scorrimento visibile, nome e pulsanti fissi |
| Contrasto di "Assegna" | Verde `#007a36`, 5,47:1 |
| Calendario che ripete le etichette e a 7 colonne su telefono | Solo eccezioni; elenco di giorni su telefono |
| Menu in basso troncato | "Dipend." e "Impost." con nome completo nell'`aria-label`, testo da 12 px |
| Impostazioni troppo lunga | Sezioni richiudibili con freccia, campi della giusta larghezza |
| Colori arancioni | Sei token `--eccezione-*` |
| Scorciatoie e azione principale | ← e → per cambiare settimana, barra fissa sul telefono |
| Prima apertura del Calendario | Cache lato server e spinner |
| Controlli a 40 px e righe di apertura da 23 px con il tocco | Tutti a 44 px con puntatore tattile; su PC restano a 40 px |
| Altezze incoerenti nella toolbar | Pulsanti e "Altre opzioni" a 44 px; corpo del testo da 16 px su telefono |
| Codice morto del vecchio suggerimento di scorrimento | Rimosso |
| Frecce diverse nelle sezioni richiudibili | Stesso triangolo in "Turni da coprire" e nelle sezioni di Impostazioni |
| "Autista programmati" su telefono, navigazione di Turni dipendente, celle fuori mese | Badge con il nome intero; selettore su una riga; solo grigio |

## Da non cambiare

- **Settimana su PC:** legenda dei colori, weekend evidenziato, icone sole e luna, posti scoperti in rosso, banner di stato, blocco della settimana confermata.
- **Riepilogo ore su PC:** larghezza massima di 1100 px; il vuoto a destra è voluto, per non allungare le righe.
- **Tratteggio "turno non richiesto" e bordi laterali colorati:** eccezioni documentate nel rilevatore.
- **Basi di accessibilità:** link "Vai al contenuto", ring del focus a 3 px, contrasti tra 5,5 e 16:1, `prefers-reduced-motion` rispettato.

## Ordine di lavoro consigliato

1. Provare con un lettore di schermo il titolo dentro `<summary>` (M2) prima di cambiare qualcosa.
2. Decidere sulle email in Personale (M3).
3. Facoltativi: `/impeccable shape` per il Calendario a settimane (M1) e `/impeccable colorize` per i colori di stampa (M4).

Dopo le modifiche, rilanciare `/impeccable critique` e `/impeccable audit` per confrontare i punteggi con quelli di questo giro (32/40 e 18/20).
