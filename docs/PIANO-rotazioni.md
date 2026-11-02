# Piano: rotazione nel tempo di Ascoli, Assistenze ed Extra e festività

Obiettivo: oltre alle ore, ai weekend, a Standby/Programmati e alle due sedi, il generatore distribuisce
**a rotazione nel tempo** anche:

1. i turni ad **Ascoli**;
2. i turni di **Assistenze ed Extra**;
3. i turni nelle **festività** scelte in Impostazioni, tenendo conto anche di **chi le ha lavorate negli anni passati**.

Inoltre:

- una festività passata a casa per **ferie o indisponibilità** conta come riposo goduto (punto 3.5);
- si può segnare **chi vuole lavorare** una festività (punto 3.6);
- l'**ordine di rotazione** delle prossime festività è visibile in anticipo (punto 3.7);
- un **quadro dell'equità** nelle Statistiche mostra se le rotazioni funzionano (capitolo 4).

Il piano parte dal codice di `main` al commit `5c4a7e1`.

**Stato (2 novembre 2026): tutte le fasi del capitolo 5 sono fatte** (1–10, sul branch
`piano/rotazioni-ascoli-extra-festivita`). I pesi delle festività restano quelli di partenza: la simulazione non ha
mostrato un miglioramento chiaro (numeri al punto 3.3).

---

## 0. Situazione attuale

| Cosa | Oggi | File |
|---|---|---|
| Weekend | Equi nel tempo con il meccanismo del "debito" (sotto); al massimo uno a settimana | `solver._weekend`, `storico.StoricoPersona.weekend` |
| Standby e Programmati | Stesso meccanismo, solo tra chi quella settimana li può fare; penalità per il secondo turno nella settimana | `solver._richieste`, `StoricoPersona.richieste`, `CATEGORIE_RICHIESTA` |
| Acquasanta / Venarotta | Scambi a fine generazione verso tanti turni nell'una quanti nell'altra | `solver.riequilibra_sedi`, `StoricoPersona.sedi` |
| **Ascoli** | Solo regole **settimanali**: max 2 (3 in extremis), mai due giorni/notti di fila, giorno e notte alternati. **Nessun conteggio nel tempo** | `solver._ascoli`, `vincoli._ascoli*` |
| **Assistenze ed Extra** | Coperte per ultime; contano solo nelle ore. **Nessuna rotazione** | `solver._priorita`, `modello.EXTRA` |
| **Festività** | **Non esistono**: sono speciali solo sabato e domenica (`categoria_weekend`) | — |
| Storico | Ricalcolato ogni volta dalle settimane salvate, a partire dalla prima con turni generati (ottobre 2026). **Niente anni passati** | `storico.calcola_storico`, `app._settimana_passata` |

### Il meccanismo del "debito" (già usato per weekend e Standby/Programmati)

Per ogni categoria (es. "sabato notte") e ogni dipendente:

- **quota attesa** = tasso medio × esposizione (es. turni di sabato notte per settimana lavorata × settimane lavorate);
- **debito** = turni fatti nello storico + turni già fissati questa settimana − quota attesa
  (positivo = ne ha fatti più del dovuto);
- ogni turno di quella categoria assegnato alla persona costa `P × (2 × debito + 1)`: è il costo marginale di
  `(debito + c)²`, quindi riceve per primo chi è più "in credito".

Le tre nuove rotazioni usano lo stesso meccanismo, cambiando solo **cosa si conta** e **l'esposizione**.

---

## 1. Ascoli a rotazione

**Comportamento atteso:** nel tempo ogni dipendente fa una quota simile di turni ad Ascoli, rispetto alle settimane B
in cui era in servizio, e ad Ascoli fa **tanti giorni quante notti**. Chi finora ne ha fatti di più ne riceve meno,
e viceversa; chi ad Ascoli ha fatto più giorni riceve più notti, e viceversa. Le regole settimanali restano come sono
e hanno la precedenza.

### Dati

- `StoricoPersona.ascoli: int`: turni ad Ascoli (anche mezzo turno conta 1, come nella regola settimanale).
- `StoricoPersona.settimane_ascoli: int`: settimane in cui Ascoli era attiva e la persona era presente
  (non in ferie tutta la settimana). Una settimana conta se contiene almeno un turno ad Ascoli: così non dipende
  dalla data di riferimento A/B, che può cambiare.
- `StoricoPersona.ascoli_giorno: int` e `StoricoPersona.ascoli_notte: int`: gli stessi turni divisi per fascia
  (`ascoli = ascoli_giorno + ascoli_notte`).
- `calcola_storico` aggiorna i contatori, nelle stesse settimane che contano già per gli altri.
- **Decisione:** lo storico di Ascoli parte dalla **prima settimana generata**; nessuna importazione di dati passati.

### Generatore

- Si generalizza `_richieste` in `_rotazioni`, guidato da una tabella di categorie:

  | Categoria | Turni che contano | Contatore | Esposizione | Penalità per il 2° turno nella settimana |
  |---|---|---|---|---|
  | Standby | postazione Standby | `richieste["Standby"]` | `settimane` | sì (`P_DOPPIA_RICHIESTA`) |
  | Programmati | postazione Programmati | `richieste["Programmati"]` | `settimane` | sì |
  | **Ascoli** | postazione Ascoli | `ascoli` | `settimane_ascoli` | **no** (già regolato dal max 2 settimanale) |
  | **Assistenze ed Extra** | postazione Assistenze ed Extra | `richieste["Assistenze ed Extra"]` | `settimane` | sì |

  Il primo passo è un refactor senza cambiamenti di comportamento (gli stessi test di oggi devono passare).
- Come oggi, entrano nel calcolo solo gli **idonei** della settimana, cioè chi ha almeno un turno possibile in
  quella categoria: chi ha il divieto per Ascoli, è in ferie, ecc. non paga e non sposta il tasso.
- Peso: `P_ASCOLI_STORICO = 30` (come weekend e Standby). Resta molto sotto le regole settimanali di Ascoli
  (`P_ASCOLI_GIORNO_NOTTE = 2000`, `P_TERZO_ASCOLI = 1.000.000`), che quindi continuano a prevalere.
- **Decisione: equilibrare anche giorni e notti ad Ascoli nel tempo**, oltre all'alternanza nella settimana.
  Per ogni dipendente si minimizza `|(ascoli_giorno − ascoli_notte) dello storico + (giorni − notti) ad Ascoli della
  settimana|`, con peso `P_ASCOLI_GN_STORICO = 100` per ogni turno di differenza. Anche mezzo turno conta 1.
  Resta sotto l'alternanza settimanale (`P_ASCOLI_GIORNO_NOTTE = 2000`): prima si alterna nella settimana, poi si
  recupera lo squilibrio accumulato.

### Dove si vede

- Statistiche: colonna **Ascoli** con turni totali e giorni / notti (pagina, stampa, riepilogo via email).
  Il riepilogo per dipendente mostra già i turni per postazione.
- `GET /api/statistiche`: campo `ascoli: {turni, giorno, notte}`.

### Test (prima rossi, poi verdi, come negli altri commit)

- `calcola_storico` conta i turni ad Ascoli (anche mezzi) e le settimane con Ascoli dei soli presenti.
- A parità di tutto, chi ha più turni ad Ascoli nello storico ne riceve meno.
- Chi ha il divieto per Ascoli non entra nel tasso.
- A parità di tutto, chi ad Ascoli ha fatto più giorni che notti nello storico riceve una notte, e viceversa.
- Le regole settimanali (max 2, mai di fila, alternanza) restano rispettate anche con uno storico molto sbilanciato.
- Statistiche: campo `ascoli` (turni, giorno, notte) per i dipendenti; per i volontari solo i totali.

---

## 2. Assistenze ed Extra a rotazione

**Comportamento atteso:** i turni di Assistenze ed Extra sono distribuiti a rotazione tra chi li può fare, come
Standby e Programmati. Restano gli ultimi a essere coperti se manca personale: la rotazione sceglie *chi* li fa,
non *se* si coprono.

### Dati e generatore

- `CATEGORIE_RICHIESTA` comprende anche `EXTRA` (`StoricoPersona.richieste["Assistenze ed Extra"]`).
- Esposizione: tutte le settimane lavorate (le Assistenze esistono sia nelle settimane A sia nelle B).
- **Decisione:** si contano i **turni**, come per Standby e Programmati: ogni turno di Assistenze vale 1, qualunque
  sia la durata (da 1 a 24 ore). L'equilibrio delle ore c'è già.
- **Decisione:** lo storico parte dalla **prima settimana generata**; nessuna importazione di dati passati.
- **Decisione:** si evita di dare **due Assistenze alla stessa persona nella stessa settimana**: penalità
  `P_DOPPIA_RICHIESTA` per ogni turno di Assistenze oltre il primo, come per Standby e Programmati.

### Dove si vede

- Statistiche: colonna **Assistenze** (pagina, stampa, riepilogo via email); `GET /api/statistiche`: campo `assistenze`.

### Test

- Lo storico conta i turni di Assistenze ed Extra.
- Chi ne ha fatti di più nello storico ne riceve meno; chi non può farli (ruolo, divieto, ferie) non entra nel tasso.
- Quando possibile, nessuno riceve due turni di Assistenze nella stessa settimana.
- La priorità di copertura non cambia: se manca personale restano scoperte per prime le Assistenze.

---

## 3. Festività a rotazione

**Comportamento atteso:** il responsabile sceglie in Impostazioni le festività che contano. I turni in quelle
festività vengono distribuiti a rotazione **festività per festività** (decisione): per ogni festività, chi
l'ha lavorata più volte negli ultimi 5 anni, o l'ha lavorata l'anno scorso, ha la precedenza per restare a casa.
Esempio: chi ha fatto Natale l'anno scorso quest'anno a Natale lascia il posto a chi non lo fa da più tempo.
Non si fa un conteggio unico di tutte le festività: aver lavorato a Ferragosto non dispensa da Natale.

Lo storico comprende anche gli anni passati, inseriti a mano o importati da un file.

### 3.1 Calendario delle festività (Impostazioni)

Nuova scheda **"Festività a rotazione"** nelle Impostazioni:

- **Elenco predefinito** da spuntare (all'inizio nessuna spuntata):
  Capodanno (1/1), Epifania (6/1), Pasqua, Lunedì dell'Angelo, Liberazione (25/4), Festa del lavoro (1/5),
  Festa della Repubblica (2/6), Sant'Emidio, patrono di Ascoli Piceno (5/8), Ferragosto (15/8), Ognissanti (1/11),
  Immacolata (8/12), Vigilia di Natale (24/12), Natale (25/12), Santo Stefano (26/12), San Silvestro (31/12).
- **Festività aggiunte a mano:** nome + giorno e mese (ogni anno) oppure una data singola.
- **Quali turni contano** (decisione: si scelgono dal calendario, festività per festività), con tre caselle:
  - il giorno (8–20);
  - la notte che inizia quel giorno (20–8);
  - la notte della sera prima. Esempio: la "notte di Natale" 24→25 nel programma è un turno del 24, perché la notte
    appartiene al giorno in cui inizia.

  Predefinito: giorno e notte del giorno stesso. Volendo, la Vigilia si spunta come festività a sé.
- **Peso** (decisione: si sceglie dal calendario, festività per festività): **1 = normale**, **2 = importante**,
  **3 = molto importante**; predefinito 1. Il peso dice quanto conta rispettare la rotazione di quella festività
  rispetto alle altre preferenze: con peso 3 il programma evita molto di più di far rifare la festività a chi l'ha
  già fatta (punto 3.3).
- **Anteprima** delle date dell'anno in corso e del prossimo, con Pasqua e Pasquetta calcolate.
- Nella **griglia della settimana** e nella **stampa** i giorni festivi sono evidenziati con il nome della festività.

Dati e API:

```
festivita(id INTEGER PK AUTOINCREMENT, nome TEXT NOT NULL,
          regola TEXT NOT NULL,          -- 'fissa' (giorno/mese ogni anno) | 'pasqua' (offset da Pasqua) | 'data' (una sola volta)
          giorno INTEGER, mese INTEGER, offset_pasqua INTEGER, data TEXT,
          conta_giorno INTEGER NOT NULL DEFAULT 1, conta_notte INTEGER NOT NULL DEFAULT 1,
          conta_notte_prima INTEGER NOT NULL DEFAULT 0,
          peso INTEGER NOT NULL DEFAULT 1,  -- 1 normale, 2 importante, 3 molto importante
          attiva INTEGER NOT NULL DEFAULT 0)
```

- Predefinite inserite all'avvio (non attive), come oggi le postazioni.
- `cvap/festivita.py` (nuovo): `pasqua(anno)` (algoritmo di Gauss/Meeus, senza dipendenze esterne),
  `date_festive(festivita, anno) -> dict[date, nome]`,
  `turni_festivi(festivita, dal, al) -> dict[(data_inizio_turno, fascia), id_festività]`.
- API: `GET /api/festivita`, `POST /api/festivita`, `PUT /api/festivita/{id}`, `DELETE /api/festivita/{id}`
  (le predefinite si attivano o disattivano, non si cancellano; `peso` intero da 1 a 3, almeno un turno che conta);
  `GET /api/settimane/{data}` aggiunge `festivi: [{data, nome, peso}]`.

### 3.2 Storico degli anni passati

Lo storico del programma parte da ottobre 2026, quindi per le festività servono i dati degli anni precedenti.
Vanno in tabelle **separate** dalle assegnazioni, così non toccano ore, settimane e statistiche delle settimane:

```
storico_festivi(id INTEGER PK AUTOINCREMENT, anno INTEGER NOT NULL, festivita_id INTEGER NOT NULL REFERENCES festivita(id),
                persona_id INTEGER NOT NULL REFERENCES persone(id), fascia TEXT NOT NULL)   -- 'giorno' | 'notte'
storico_festivi_servizio(anno INTEGER NOT NULL, persona_id INTEGER NOT NULL REFERENCES persone(id),
                         PRIMARY KEY (anno, persona_id))   -- chi era in servizio quell'anno (serve per la quota attesa)
```

Due modi per inserirli, nella nuova pagina **Impostazioni → Storico festività**:

1. **A mano:** per ogni anno, una tabella festività × (giorno, notte) in cui si scelgono i nomi, più l'elenco di
   chi era in servizio quell'anno (predefinito: i dipendenti attuali più chi compare nei dati di quell'anno).
2. **Da file** Excel o CSV, con un'anteprima prima di salvare:

   | Anno | Festività | Turno | Nome |
   |---|---|---|---|
   | 2025 | Natale | giorno | Mario Rossi |
   | 2025 | Natale | notte | Luca Bianchi |
   | 2025 | Ferragosto | giorno | Anna Verdi |

   - Al posto di Anno e Festività si può dare la **data** (es. 25/12/2025): la festività si ricava dal calendario.
   - I nomi si confrontano con il Personale ignorando maiuscole e spazi (come per i volontari). I nomi non trovati
     sono elencati nell'anteprima: si possono abbinare a una persona esistente, registrare come ex dipendenti
     (persona non attiva) oppure scartare.
   - Le righe con date dalla prima settimana generata in poi vengono ignorate: quei turni il programma li conta
     già dalle assegnazioni, quindi niente doppioni.
   - Servono i dati degli **ultimi 5 anni** (punto 3.3): quelli più vecchi si possono inserire, ma non contano.

### 3.3 Regole nel generatore

Note dalla fase 5 (storico fatto il 2026-11-01): leggendo lo storico importato contare solo le festività con data
prima della prima settimana generata (il limite si sposta se si cancellano i turni generati); dove l'elenco "in
servizio" di un anno non è salvato usare la stessa proposta della pagina (dipendenti attivi + chi compare nei dati).

- **Periodo considerato** (decisione): le festività degli **ultimi 5 anni** prima della settimana da generare
  (costante `ANNI_FESTIVI = 5`, facile da cambiare).
- **Rotazione festività per festività** (decisione): ogni festività è una categoria a sé, con il meccanismo del debito.
  Non c'è un conteggio unico di tutte le festività. Per la festività `f`, di peso `w`, e il dipendente `p`:
  - **esposizione** = quante volte, nel periodo considerato, la festività `f` è caduta mentre `p` era in servizio:
    negli anni importati se era nell'elenco di chi era in servizio, nelle settimane del programma se era tra i
    dipendenti della settimana, **anche se era in ferie o indisponibile** (punto 3.5); è esclusa solo la malattia;
  - **tasso** = turni fatti in `f` da tutti ÷ esposizione di tutti, tra i dipendenti idonei quella settimana;
  - **debito** = turni fatti in `f` (anni importati + programma) + turni già fissati in `f` − tasso × esposizione;
  - ogni turno in `f` costa `P_FESTIVITA × w × (2 × debito + 1)`: chi ha fatto quella festività più del dovuto
    paga di più, e il peso rende la rotazione più forte.
- **Chi l'ha fatta di recente:** chi ha lavorato **la stessa festività l'anno prima** paga in più
  `P_STESSA_FESTIVITA × w` per rifarla (metà se l'ha fatta due anni prima). Così la rotazione guarda sia a quante
  volte l'ha fatta in 5 anni sia a quando.
- **Non più di un turno festivo a testa nella stessa settimana** (es. Natale + Santo Stefano):
  penalità `P_DOPPIO_FESTIVO`, come per i weekend. È una regola a parte: distribuisce i festivi vicini tra persone
  diverse, senza fare un conteggio totale nel tempo.
- **Festivo di domenica** (decisione): conta **sia come weekend sia come festivo**. Il turno entra nella rotazione
  dei weekend (domenica giorno o domenica notte) e in quella della festività.
- **Volontari:** i turni festivi coperti dai volontari non entrano nella rotazione (contano solo i turni dei dipendenti).
- Pesi di partenza, da tarare con la simulazione:

  | Penalità | Proposta | Confronto con quelle esistenti |
  |---|---|---|
  | `P_FESTIVITA` | 60 × peso, sul debito della festività | da 60 a 180: oltre il doppio dei weekend (30) |
  | `P_STESSA_FESTIVITA` | 500 × peso | da 500 a 1.500: sopra il doppio weekend (300), sotto i tre di fila (5.000) |
  | `P_DOPPIO_FESTIVO` | 300 | come il doppio weekend |
  | `P_DISPONIBILE_FESTIVO` | −3.000 (sconto) | supera le penalità di rotazione, resta sotto i tre di fila (5.000) |

  **Taratura con la simulazione (fase 10, fatta il 2 novembre 2026): i pesi restano questi.**
  `python -m cvap.simulazione --festivita --anni 3 --tempo 20 --worker 2 --pesi ...`: 17 dipendenti, settimane dal
  24/12 al 1/1 per 3 anni (7 settimane), Natale peso 3 con la notte della Vigilia, Santo Stefano peso 1, Capodanno
  peso 2 con la notte di San Silvestro, storico inventato dei 5 anni prima (4 persone di giorno e 4 di notte per
  festività, due sempre a Natale), uno che vuole lavorare il giorno di Natale, uno in ferie a Natale il primo anno.
  Una configurazione per riga, cambiando un peso alla volta:

  | Pesi | Scoperti | Diff. ore peggiore | Divario saldi ore | Turni festivi | Ripetute dall'anno prima | Doppi festivi | Più − meno in 5 anni (Natale, S. Stefano, Capodanno) | Vuole lavorare |
  |---|---|---|---|---|---|---|---|---|
  | partenza (60 / 500 / 300 / −3.000) | 2 | 24 h | 37 h | 117 | 44 | 36 | 3, 2, 2 | 1/3 |
  | partenza, ripetuta | 1 | 12 h | 13 h | 117 | 41 | 33 | 3, 3, 2 | 2/3 |
  | `P_FESTIVITA` 30 | 1 | 24 h | 49 h | 118 | 56 | 32 | 3, 3, 2 | 1/3 |
  | `P_FESTIVITA` 120 | 0 | 36 h | 21 h | 118 | 61 | 26 | 3, 4, 2 | 2/3 |
  | `P_STESSA_FESTIVITA` 250 | 0 | 24 h | 24 h | 118 | 58 | 32 | 3, 3, 2 | 2/3 |
  | `P_STESSA_FESTIVITA` 1.000 | 2 | 12 h | 25 h | 116 | 38 | 28 | 3, 2, 2 | 2/3 |
  | `P_DOPPIO_FESTIVO` 150 | 0 | 24 h | 8 h | 118 | 40 | 32 | 3, 2, 2 | 3/3 |
  | `P_DOPPIO_FESTIVO` 600 | 0 | 12 h | 18 h | 118 | 52 | 29 | 3, 2, 2 | 2/3 |
  | `P_DISPONIBILE_FESTIVO` −1.500 | 0 | 12 h | 19 h | 118 | 44 | 27 | 3, 3, 2 | 2/3 |

  Letture: il rumore è grande (la stessa configurazione ripetuta cambia di 3 ripetute, 3 doppi, 1 scoperto, 12 h di
  differenza): nessuna settimana arriva all'ottimo dimostrato in 20 s. Abbassare `P_STESSA_FESTIVITA` o cambiare
  `P_FESTIVITA` in su o in giù aumenta chiaramente le ripetute (56–61 contro 41–44); alzare `P_STESSA_FESTIVITA` a
  1.000 le riduce poco (38) ma con 2 posti scoperti, quindi non è un miglioramento chiaro. I doppi festivi sono quasi
  tutti inevitabili: nella settimana di Natale e Santo Stefano ci sono circa 24–30 turni festivi per 16–17 persone.
  Il divario negli ultimi 5 anni (3, 2–3, 2) e nessuno senza la festività non cambiano con i pesi. I posti scoperti (0–2
  su 7 settimane) e la differenza di ore oltre 12 compaiono anche con i pesi di partenza: dipendono dal tempo di
  ricerca con 17 dipendenti nelle settimane B, non dai pesi delle festività.
  Pesi finali: `P_FESTIVITA = 60`, `P_STESSA_FESTIVITA = 500`, `P_DOPPIO_FESTIVO = 300`,
  `P_DISPONIBILE_FESTIVO = −3.000`.

  Nessuna di queste supera i vincoli più importanti (copertura, ore minime, differenza massima, regole di Ascoli):
  la rotazione dei festivi sceglie *tra* le soluzioni che rispettano le regole.
- Lo storico dei festivi si ricalcola ogni volta, come quello attuale: se si aggiunge una festività al calendario,
  conta subito anche per le settimane già fatte nel programma; per gli anni importati conta solo se è nei dati.

### 3.4 Dove si vede

- Statistiche: colonna **Festivi** con i turni degli ultimi 5 anni per ogni festività (e l'ultimo anno in cui
  l'ha fatta), anche nel riepilogo via email; `GET /api/statistiche`: campo
  `festivi: {per_festivita: [{festivita, turni, ultimo_anno}]}`.
- Riepilogo per dipendente: turni festivi del periodo.
- Pagina **Storico festività**: per ogni anno chi ha lavorato ogni festività, importato o dal programma.

### 3.5 Ferie e indisponibilità nelle festività

**Decisione:** una festività passata a casa per **ferie** o per **indisponibilità** conta come **riposo goduto**.

- Quella festività entra nell'esposizione della persona (punto 3.3): la sua quota attesa cresce, il debito scende e
  la volta dopo ha la precedenza a lavorarla. Così chi prende sempre ferie a Natale non salta la rotazione.
- La **malattia o infortunio** invece non conta: quella festività non vale né come lavorata né come riposo.
- Indisponibilità: conta se riguarda almeno uno dei turni che contano per quella festività (es. la notte di Natale).
- Negli anni importati non si distingue: chi era in servizio e non ha lavorato quella festività conta come a casa.
- Esempio: Anna è in ferie a Natale 2026, Luca lavora. A Natale 2027, a parità di tutto, tocca prima ad Anna.

### 3.6 Chi vuole lavorare una festività

**Decisione:** si può segnare che un dipendente **vuole lavorare** una festività.

- Si segna nella pagina delle prossime festività (punto 3.7), per persona e festività: giorno, notte o entrambi.
- Dati:

  ```
  festivi_disponibili(data TEXT NOT NULL, persona_id INTEGER NOT NULL REFERENCES persone(id),
                      fascia TEXT NOT NULL,     -- 'giorno' | 'notte' | 'entrambi'
                      PRIMARY KEY (data, persona_id))
  ```

- Generatore: i turni di quella festività assegnati a chi è disponibile ricevono uno sconto
  `P_DISPONIBILE_FESTIVO` (−3.000), più forte delle penalità di rotazione: quei turni vanno prima a loro.
  Tutte le regole restano valide (riposi, ore, qualifica, Ascoli…).
- Se i disponibili sono più dei posti, tra loro decide la rotazione.
- I turni lavorati volentieri **contano comunque nella rotazione** di chi li fa: se un anno non è più disponibile,
  la rotazione terrà conto di quante volte l'ha già fatta.
- Nell'elenco dei dipendenti della cella della griglia compare l'indicazione "vuole lavorare".
- API: `GET /api/festivita/disponibili?dal&al`, `PUT /api/festivita/disponibili` `{data, persona_id, fascia | null}`
  (`null` = toglie).

### 3.7 Ordine di rotazione visibile in anticipo

**Decisione:** nuova scheda **Statistiche → Festività** con le prossime festività e l'ordine di rotazione.

- Per ogni festività attiva dei prossimi 12 mesi: data, peso e l'elenco dei dipendenti attivi **in ordine di
  precedenza a lavorarla** (prima chi ha il debito più basso, a parità chi non la fa da più tempo).
- Per ogni persona: qualifica, volte negli ultimi 5 anni, ultimo anno in cui l'ha fatta, "vuole lavorarla"
  (modificabile qui, punto 3.6), ferie o indisponibilità già registrate per quel giorno.
- È un'indicazione: l'assegnazione vera dipende anche dalle regole (riposi, ore, Ascoli…) e dai posti da autista e
  da soccorritore. Per questo l'elenco mostra la qualifica.
- Usa la stessa funzione di calcolo del generatore, così ordine e assegnazione non possono divergere.
- Stampabile, per comunicarlo al personale con anticipo (es. Natale già in autunno).
- La stessa scheda mostra anche lo storico per anno (chi ha lavorato ogni festività), importato o dal programma.
- API: `GET /api/festivita/prossime?mesi=12` →
  `[{data, festivita_id, nome, peso, ordine: [{persona_id, nome, qualifica, volte_5_anni, ultimo_anno, debito,
  disponibile, assente}]}]`.

### Test

- `pasqua(anno)` per alcuni anni noti (es. 2025 → 20/4, 2026 → 5/4, 2027 → 28/3).
- `date_festive` e `turni_festivi`: contano solo i turni spuntati per ogni festività, compresa la "notte della sera prima".
- API del calendario: attivazione, festività aggiunte, peso da 1 a 3, almeno un turno che conta, validazioni
  (data non valida, nome vuoto, doppioni).
- Importazione: abbinamento dei nomi, righe non abbinate, righe dopo la prima settimana generata ignorate,
  nessun effetto su ore e statistiche delle settimane.
- Storico: contano solo le festività degli ultimi 5 anni.
- Generatore: a parità di tutto, chi ha fatto Natale l'anno scorso non lo rifà; per ogni festività chi l'ha fatta
  più volte negli ultimi 5 anni ne riceve meno; aver fatto un'altra festività non cambia la rotazione di Natale;
  con peso più alto la rotazione prevale su preferenze che a peso 1 la batterebbero; al massimo un festivo a testa
  nella settimana quando possibile.
- Festivo di domenica: il turno conta sia nei weekend sia nella festività.
- Ferie e indisponibilità in una festività entrano nell'esposizione (la volta dopo ha la precedenza); la malattia no.
- Chi vuole lavorare una festività riceve prima quei turni, nel rispetto delle regole; tra più disponibili decide la
  rotazione; i turni lavorati volentieri contano nella rotazione.
- L'ordine delle prossime festività coincide con quello usato dal generatore a parità di regole e posti.

---

## 4. Quadro dell'equità

**Decisione:** nuova scheda **Statistiche → Equità** per verificare che le rotazioni funzionino e rispondere a
chi chiede "perché sempre io?".

- Una riga per ogni rotazione: ore (saldo), giorni/notti, weekend (sabato e domenica, giorno e notte), Standby,
  Programmati, Assistenze ed Extra, Ascoli (turni e giorni/notti), Acquasanta/Venarotta e ogni festività attiva.
- Per ogni rotazione: chi è più avanti e chi più indietro rispetto alla propria quota attesa (lo stesso "debito"
  usato dal generatore), la differenza tra i due e se si sta riducendo.
- **Andamento nel tempo:** la differenza settimana per settimana, in un piccolo grafico SVG fatto a mano (nessuna
  libreria in più), calcolando lo storico alla fine di ogni settimana.
- Cliccando una rotazione: il dettaglio per dipendente (fatti, quota attesa, scarto), ordinato.
- Periodo filtrabile; stampabile.
- Dati: `cvap/equita.py` (nuovo), `equita(settimane) -> {rotazione: {andamento, dipendenti}}`, riusando
  `calcola_storico` sulle settimane fino a ognuna; API `GET /api/statistiche/equita?dal&al`.
- Si può fare subito dopo le fasi di Ascoli e Assistenze, per le rotazioni già esistenti, e completare con le
  festività quando arrivano.

### Test

- Per una rotazione con storico noto: chi è più avanti, chi più indietro, differenza e dettaglio per dipendente.
- L'andamento ha un valore per settimana e segue le settimane generate.
- I volontari non compaiono; i dipendenti disattivati solo se hanno turni nel periodo.

---

## 5. Ordine di lavoro

Ogni fase è un commit di test (rossi) seguito da un commit di implementazione (verdi), come nella storia del progetto.

**Fatte tutte (1–10).** Fase 10: `python -m cvap.simulazione --festivita`, taratura al punto 3.3 (pesi invariati),
`docs/API.md` (indice dei moduli e sezione Simulazione), README e guida per i dipendenti `docs/GUIDA-dipendenti.md`.

1. **Refactor** di `_richieste` in `_rotazioni` con la tabella delle categorie, senza cambiare il comportamento.
2. **Ascoli a rotazione**, numero di turni e giorni/notti, + colonna nelle statistiche.
3. **Assistenze ed Extra a rotazione**, senza doppioni nella settimana, + colonna nelle statistiche.
4. **Calendario delle festività**: database, API, scheda Impostazioni con turni che contano e peso, giorni
   evidenziati in griglia e stampa (ancora senza effetto sul generatore).
5. **Storico festività**: tabelle, pagina di inserimento a mano, importazione da file.
6. **Festività nel generatore**, con ferie e indisponibilità come riposo goduto, + statistiche e riepiloghi.
7. **Chi vuole lavorare una festività**: dati, API, sconto nel generatore.
8. **Ordine di rotazione in anticipo**: scheda Statistiche → Festività, con stampa.
9. **Quadro dell'equità**: scheda Statistiche → Equità (si può anticipare dopo la fase 3 per le rotazioni già
   esistenti, e completare con le festività).
10. **Simulazione** (`cvap/simulazione.py`): più settimane con festività e storico importato, per tarare i pesi;
    aggiornamento di `docs/API.md`, README e guida per i dipendenti.

Le fasi 1–3 sono piccole e indipendenti dalle festività: si possono rilasciare subito.

---

## 6. Decisioni prese

| Domanda | Decisione |
|---|---|
| Assistenze ed Extra: turni o ore? | **Turni** (ognuno vale 1, qualunque sia la durata) |
| Festività: quali turni contano? | **Si scelgono dal calendario**, per ogni festività: giorno, notte, notte della sera prima |
| Quanti anni considerare per le festività? | **5 anni** |
| Festività più importanti? | **Peso scelto dal calendario**, per ogni festività: 1 normale, 2 importante, 3 molto importante |
| Storico di Ascoli e Assistenze | **Si parte dalla prima settimana generata**, senza dati passati |
| Ascoli: anche giorni e notti nel tempo? | **Sì, si equilibra tutto**: numero di turni e giorni/notti ad Ascoli |
| Assistenze: due nella stessa settimana alla stessa persona? | **Si evitano** |
| Rotazione delle festività | **Festività per festività**: niente conteggio unico di tutte le festività |
| Festivo di domenica | **Conta sia come weekend sia come festivo** |
| Ferie o indisponibilità in una festività | **Contano come riposo goduto**: la volta dopo ha la precedenza a lavorarla (malattia esclusa) |
| Chi vuole lavorare una festività | **Si può segnare**: riceve prima quei turni, che contano nella sua rotazione |
| Ordine di rotazione in anticipo | **Sì**: scheda Statistiche → Festività, stampabile |
| Quadro dell'equità | **Sì**: scheda Statistiche → Equità |
| Quota proporzionale alle ore per chi ha un massimo più basso | **No** |
| Limite di tempo per le altre rotazioni (weekend, Standby, Programmati, Ascoli, sedi) | **No**: guardano a tutto lo storico |

Non restano domande aperte.

## 7. Cosa mi serve per lo storico delle festività

- Per gli **ultimi 5 anni** (dalla fine del 2021 alla prima settimana generata, ottobre 2026): **chi ha lavorato
  ogni festività, di giorno e di notte**, nel formato della tabella del punto 3.2 (Excel, CSV o anche un elenco
  scritto, che converto io). Bastano le festività che si spunteranno nel calendario.
- Per ogni anno: **chi era in servizio** (basta segnalare chi non c'era ancora o non c'era più, rispetto al personale di oggi).
- I nomi scritti come in **Personale**, o l'elenco delle corrispondenze se sono scritti in altro modo.
