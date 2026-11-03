# Design audit: CVAP Turnistica

Report unico che unisce la critique di design e l'audit tecnico dell'interfaccia in `static/`. È il secondo giro, fatto il 3 novembre 2026 dopo le correzioni del primo.

## In breve

- **Nessun problema critico.** Il primo giro ne aveva 3 (griglia della Settimana su telefono, tabelle tagliate, contrasto del pulsante "Assegna"): sono risolti.
- Restano **4 problemi importanti** e **7 minori**. Il più visibile è l'inizio della Settimana su telefono: il tabellone parte a 876 px, sotto il primo schermo.
- Il lavoro precedente ha fatto salire entrambi i punteggi.

| Valutazione | Primo giro | Secondo giro | Fascia |
|---|---|---|---|
| Critique (design) | 28/40 | **31/40** | Good |
| Audit (tecnico) | 14/20 | **16/20** | Good |

| Area dell'audit | Primo giro | Secondo giro |
|---|---|---|
| Accessibilità | 3/4 | 4/4 |
| Prestazioni | 3/4 | 3/4 |
| Temi e colori | 3/4 | 3/4 |
| Adattamento ai telefoni | 2/4 | 3/4 |
| Coerenza dell'implementazione | 3/4 | 3/4 |

Problemi: da **16** (3 critici, 8 importanti, 5 minori) a **11** (0 critici, 4 importanti, 7 minori). Due dei minori vengono dal primo giro e sono ancora da decidere (titolo dentro `<summary>`, M3, e email in Personale, M4); gli altri 9 sono nuovi di questo giro.

## Come sono stati fatti i controlli

- **Critique:** valutazione in un unico contesto (nessun sotto-agente), con rilevatore automatico. Screenshot nuovi della Settimana a 1440 px (pagina intera) e a 390 px (primo schermo); le altre viste valutate dalle misure fatte nei passaggi precedenti. L'evidenziazione nel browser non è stata fatta.
- **Audit:** controllo del codice, contrasti calcolati sui colori nuovi, misure nel browser su tutte e sei le viste a 1440 e 390 px (id doppi, controlli senza nome, campi senza etichetta, titoli, aria, scorrimento orizzontale, altezza dei controlli, tempo di ridisegno) e rilevatore su `static/index.html`, `static/js` e `static/style.css`.
- **Non provato:** un telefono vero, l'orientamento orizzontale, un lettore di schermo vero, la stampa dopo le ultime modifiche.
- **Eccezioni registrate nel rilevatore:** i bordi laterali colorati (`side-tab`) sono esclusi solo in `static/style.css`, con motivo scritto in `.impeccable/config.json`: codificano lo stato con colori coerenti in tutta l'app. Il tratteggio di "turno non richiesto" è un falso positivo: serve in bianco e nero.

## Problemi critici

Nessuno.

---

## Problemi importanti

### I1. Settimana su telefono: il tabellone parte sotto il primo schermo
- **Pagina:** Settimana (telefono, 390 px).
- **Cosa non va:** la griglia comincia a 876 px dall'alto. Prima ci sono testata, banner, toolbar, due pannelli ("Disponibilità dipendenti" e "Richieste Standby e Programmati", con un "Apri" che ripete la freccia) e una legenda dei colori su 4 righe. Chi apre l'app da telefono non vede nessun turno senza scorrere.
- **Cosa proponiamo:** legenda in una riga richiudibile ("Legenda"), pannelli ridotti a una riga con freccia e conteggio, testo del banner più corto. Obiettivo: i turni entrano nel primo schermo.
- **Comando consigliato:** `/impeccable distill`

### I2. Settimana su PC: una colonna vuota accanto al Riepilogo ore
- **Pagina:** Settimana (PC, 1440 px).
- **Cosa non va:** il pannello "Controlli" ("Nessuna violazione rilevata") occupa una colonna stretta e sotto resta uno spazio vuoto di circa 600 px, mentre il Riepilogo ore scorre per tutta la pagina.
- **Cosa proponiamo:** "Controlli" come striscia di stato a tutta larghezza sopra il riepilogo, che prende tutto lo spazio.
- **Comando consigliato:** `/impeccable layout`

### I3. Campi, selettori e pulsanti a 40 px con puntatore tattile
- **Pagine:** soprattutto Settimana (selettori e campi quantità nelle sezioni "Disponibilità dipendenti" e "Richieste", pulsanti della toolbar), poi Personale e Impostazioni.
- **Cosa non va:** il valore di base di `.btn`, `input` e `select` è 40 px (`static/style.css`), 4 px sotto la soglia di 44 che il progetto si è dato (`--tap`). I comandi più recenti (`.btn-small`, barra dei giorni, barra dell'azione) seguono già 44 px. Passa il minimo WCAG (24 px).
- **Cosa proponiamo:** `@media (pointer: coarse)` con `min-height: var(--tap)` su campi, selettori e `.btn`, come già fatto per `.btn-small`.
- **Comando consigliato:** `/impeccable adapt`

### I4. Righe di apertura di 23 px
- **Pagine:** Personale ("Aggiungi una persona") e Impostazioni ("Come funziona").
- **Cosa non va:** l'area da toccare è alta quanto il testo, molto meno del resto della scheda. Le sezioni richiudibili aggiunte di recente sono già a 44 px.
- **Cosa proponiamo:** `min-height: var(--tap)` e allineamento al centro sulle `summary` rimaste (`.nuova-persona > summary`, `.info-ripiegabile summary`).
- **Comando consigliato:** `/impeccable adapt`

---

## Problemi minori

### M1. Altezze incoerenti nella toolbar su telefono, e testo a 15 px
- **Pagina:** Settimana (telefono).
- **Cosa non va:** "Altre opzioni" è più bassa di "Invia i turni via email" (40 contro 44 px). Il corpo del testo su telefono resta a 15 px, sotto la regola ordinaria di 16.
- **Cosa proponiamo:** stessa altezza (`--tap`) per i due pulsanti; valutare 16 px per il corpo su telefono.
- **Comando consigliato:** `/impeccable polish`

### M2. Codice morto del vecchio suggerimento di scorrimento
- **Pagina:** Settimana.
- **Cosa non va:** da quando la barra dei giorni mostra un giorno solo, il paragrafo "Scorri orizzontalmente per vedere tutti i giorni" non si vede mai. Resta in `static/js/settimana.js` (riga 625) e in tre regole di `static/style.css` (`.griglia-scorri`).
- **Cosa proponiamo:** togliere l'elemento e le regole.
- **Comando consigliato:** `/impeccable distill`

### M3. Titolo dentro la riga cliccabile
- **Pagine:** Settimana (pannello "Turni da coprire") e Impostazioni (sezioni richiudibili).
- **Cosa non va:** il titolo (`h2`) sta dentro `<summary>`: alcuni lettori di schermo perdono il livello del titolo. Non l'ho provato con un lettore vero.
- **Cosa proponiamo:** provare con un lettore di schermo prima di cambiare; una correzione semplice non c'è senza duplicare il titolo.
- **Comando consigliato:** `/impeccable polish`

### M4. Indirizzi email reali visibili
- **Pagina:** Personale.
- **Cosa non va:** la tabella mostra gli indirizzi email. In una stampa o in uno screenshot condiviso diventano dati personali visibili.
- **Cosa proponiamo:** nasconderli nelle stampe, o mostrarli solo nella finestra "Modifica". È una scelta sulla privacy, tua.
- **Comando consigliato:** `/impeccable polish`

### M5. Colori scritti a mano nelle regole di stampa
- **Pagine:** tutte (stampa e stati). Codice: `static/style.css`.
- **Cosa non va:** circa 204 valori esadecimali fuori da `:root`, in gran parte nelle regole di stampa. Nessun difetto visibile; cambiare i colori richiede di toccare molti punti.
- **Cosa proponiamo:** token solo per i pochi colori di stato che ricorrono; quelli specifici della stampa restano.
- **Comando consigliato:** `/impeccable colorize`

### M6. Due frecce diverse per le sezioni richiudibili
- **Pagine:** Settimana ("Turni da coprire") e Impostazioni.
- **Cosa non va:** le sezioni di Impostazioni hanno una freccia disegnata (un triangolo che ruota), il pannello "Turni da coprire" ha quella standard del browser. Non ho potuto vederlo: questa settimana non ci sono turni da coprire.
- **Cosa proponiamo:** una sola freccia per tutte le sezioni richiudibili.
- **Comando consigliato:** `/impeccable polish`

### M7. Calendario su telefono: 42 righe
- **Pagina:** Calendario (telefono).
- **Cosa non va:** l'elenco dei giorni è lungo (2104 px). I giorni coperti occupano 44 px ognuno.
- **Cosa proponiamo:** una riga per settimana, che si apre sui giorni solo se c'è un'eccezione. È un cambio di struttura: da decidere.
- **Comando consigliato:** `/impeccable shape`

---

## Risolti dal primo giro

| Voce | Cosa è stato fatto |
|---|---|
| Settimana su telefono: due giorni su sette | Barra dei giorni con i posti scoperti, un giorno alla volta |
| Tabelle larghe tagliate | Sfumatura sul bordo destro, barra di scorrimento visibile, nome e pulsanti fissi, Riepilogo ore più largo |
| Contrasto di "Assegna" | Verde `#007a36`, 5,47:1 |
| Calendario che ripete le etichette | Solo eccezioni; "Settimana A/B" una volta per riga |
| Calendario su telefono a 7 colonne | Elenco di giorni con il nome accanto alla data |
| Menu in basso troncato | "Dipend." e "Impost." con nome completo nell'`aria-label`, testo da 12 px |
| Impostazioni troppo lunga | Sezioni richiudibili con freccia, campi della giusta larghezza, riquadri uguali |
| Colori arancioni | Sei token `--eccezione-*` |
| Scorciatoie e azione principale | ← e → per cambiare settimana, barra fissa su telefono |
| Prima apertura del Calendario | Cache lato server e spinner |
| "Autista programmati" su telefono | Badge con il nome intero, solo per chi lo è |
| Navigazione di Turni dipendente | Selettore su una riga |
| Celle fuori mese | Solo grigio, senza tratteggio |

## Da non cambiare

- **Settimana su PC:** legenda dei colori, weekend evidenziato, icone sole e luna, posti scoperti in rosso, banner di stato, blocco della settimana confermata.
- **Tratteggio "turno non richiesto":** funziona anche in bianco e nero.
- **Bordi laterali colorati:** codificano lo stato; eccezione registrata nel rilevatore.
- **Basi di accessibilità:** link "Vai al contenuto", ring del focus a 3 px, una `h1` per vista, nessun id doppio, tutti i controlli con nome, nessun errore in console, `prefers-reduced-motion` rispettato, nessuna vista scorre in orizzontale a 390 px.

## Ordine di lavoro consigliato

1. `/impeccable distill`: inizio della Settimana su telefono (I1) e codice morto (M2).
2. `/impeccable layout`: striscia "Controlli" a tutta larghezza (I2).
3. `/impeccable adapt`: controlli e righe `summary` a 44 px con il tocco (I3, I4).
4. `/impeccable polish`: toolbar, freccia unica, email e titolo dentro `<summary>` (M1, M3, M4, M6), poi verifica finale a 1440 e 390 px.
5. Facoltativi: `/impeccable colorize` (M5) e `/impeccable shape` per il Calendario a settimane (M7).

Dopo le modifiche, rilanciare `/impeccable critique` e `/impeccable audit` per confrontare i punteggi con quelli di questo giro (31/40 e 16/20).
