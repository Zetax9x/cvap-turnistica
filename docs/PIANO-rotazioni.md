# Piano: rotazione nel tempo di Ascoli, Assistenze ed Extra e festività

Obiettivo: oltre alle ore, ai weekend, a Standby/Programmati e alle due sedi, il generatore distribuisce
**a rotazione nel tempo** anche:

1. i turni ad **Ascoli**;
2. i turni di **Assistenze ed Extra**;
3. i turni nelle **festività** scelte in Impostazioni, tenendo conto anche di **chi le ha lavorate negli anni passati**.

Il piano parte dal codice di `main` al commit `5c4a7e1`.

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
in cui era in servizio. Chi finora ne ha fatti di più ne riceve meno, e viceversa. Le regole settimanali restano
come sono e hanno la precedenza.

### Dati

- `StoricoPersona.ascoli: int`: turni ad Ascoli (anche mezzo turno conta 1, come nella regola settimanale).
- `StoricoPersona.settimane_ascoli: int`: settimane in cui Ascoli era attiva e la persona era presente
  (non in ferie tutta la settimana). Una settimana conta se contiene almeno un turno ad Ascoli: così non dipende
  dalla data di riferimento A/B, che può cambiare.
- `calcola_storico` aggiorna i due contatori, nelle stesse settimane che contano già per gli altri.
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
- Ancora da decidere (domanda aperta A): anche **giorno/notte ad Ascoli nel tempo** (contatori `ascoli_giorno` e
  `ascoli_notte`), oltre all'alternanza nella settimana.

### Dove si vede

- Statistiche: colonna **Ascoli** (pagina, stampa, riepilogo via email). Il riepilogo per dipendente mostra già i turni per postazione.
- `GET /api/statistiche`: campo `ascoli`.

### Test (prima rossi, poi verdi, come negli altri commit)

- `calcola_storico` conta i turni ad Ascoli (anche mezzi) e le settimane con Ascoli dei soli presenti.
- A parità di tutto, chi ha più turni ad Ascoli nello storico ne riceve meno.
- Chi ha il divieto per Ascoli non entra nel tasso.
- Le regole settimanali (max 2, mai di fila, alternanza) restano rispettate anche con uno storico molto sbilanciato.
- Statistiche: campo `ascoli` per i dipendenti; per i volontari solo il totale.

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
- Penalità per il secondo turno di Assistenze nella stessa settimana: proposta sì, per allargare la rotazione
  (domanda aperta B).

### Dove si vede

- Statistiche: colonna **Assistenze** (pagina, stampa, riepilogo via email); `GET /api/statistiche`: campo `assistenze`.

### Test

- Lo storico conta i turni di Assistenze ed Extra.
- Chi ne ha fatti di più nello storico ne riceve meno; chi non può farli (ruolo, divieto, ferie) non entra nel tasso.
- La priorità di copertura non cambia: se manca personale restano scoperte per prime le Assistenze.

---

## 3. Festività a rotazione

**Comportamento atteso:** il responsabile sceglie in Impostazioni le festività che contano. I turni in quelle
festività vengono distribuiti a rotazione:

- nel **totale**: negli ultimi 5 anni ognuno fa una quota simile di turni festivi, pesati secondo l'importanza
  della festività scelta nel calendario;
- nella **singola festività**: chi ha lavorato a Natale l'anno scorso, quest'anno a Natale ha la precedenza per
  restare a casa.

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
  **3 = molto importante**; predefinito 1. Un turno in una festività di peso 3 conta come tre turni festivi
  normali, sia nel totale sia nella rotazione della singola festività (punto 3.3).
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

- **Periodo considerato** (decisione): le festività degli **ultimi 5 anni** prima della settimana da generare
  (costante `ANNI_FESTIVI = 5`, facile da cambiare).
- **Punti festivi:** ogni turno festivo vale quanto il **peso** della sua festività (1, 2 o 3). Si contano i punti,
  non i turni, così le festività importanti pesano di più nella rotazione.
- **Esposizione** di un dipendente = punti festivi "possibili" nel periodo considerato in cui era in servizio
  (somma dei pesi delle festività):
  - anni importati: le festività di quell'anno, se era nell'elenco di chi era in servizio;
  - settimane del programma: le festività in cui era tra i dipendenti della settimana e non in ferie.
- **Totale equo:** debito = punti festivi fatti (anni importati + programma) + punti già fissati − tasso × esposizione.
  Un turno in una festività di peso `w` costa `P_FESTIVI × (2 × w × debito + w²)`: è il costo marginale di
  `(debito + w × c)²`, quindi più la festività pesa, più conta chi l'ha già fatta.
- **Rotazione della singola festività:** chi ha lavorato **la stessa festività l'anno prima** paga
  `P_STESSA_FESTIVITA × w` per rifarla (metà se l'ha fatta due anni prima).
- **Non più di un turno festivo a testa nella stessa settimana** (es. Natale + Santo Stefano):
  penalità `P_DOPPIO_FESTIVO`, come per i weekend.
- **Festivo di domenica:** proposta: conta sia come weekend sia come festivo (domanda aperta D).
- **Volontari:** i turni festivi coperti dai volontari non entrano nella rotazione (contano solo i turni dei dipendenti).
- Pesi di partenza, da tarare con la simulazione:

  | Penalità | Proposta | Confronto con quelle esistenti |
  |---|---|---|
  | `P_FESTIVI` | 60 per punto, sul debito | il doppio dei weekend (30): i festivi pesano di più |
  | `P_STESSA_FESTIVITA` | 500 × peso | da 500 a 1.500: sopra il doppio weekend (300), sotto i tre di fila (5.000) |
  | `P_DOPPIO_FESTIVO` | 300 | come il doppio weekend |

  Nessuna di queste supera i vincoli più importanti (copertura, ore minime, differenza massima, regole di Ascoli):
  la rotazione dei festivi sceglie *tra* le soluzioni che rispettano le regole.
- Lo storico dei festivi si ricalcola ogni volta, come quello attuale: se si aggiunge una festività al calendario,
  conta subito anche per le settimane già fatte nel programma; per gli anni importati conta solo se è nei dati.

### 3.4 Dove si vede

- Statistiche: colonna **Festivi** con turni e punti negli ultimi 5 anni e il dettaglio per festività, anche nel
  riepilogo via email; `GET /api/statistiche`: campo `festivi: {turni, punti, per_festivita}`.
- Riepilogo per dipendente: turni festivi del periodo.
- Pagina **Storico festività**: per ogni anno chi ha lavorato ogni festività, importato o dal programma.

### Test

- `pasqua(anno)` per alcuni anni noti (es. 2025 → 20/4, 2026 → 5/4, 2027 → 28/3).
- `date_festive` e `turni_festivi`: contano solo i turni spuntati per ogni festività, compresa la "notte della sera prima".
- API del calendario: attivazione, festività aggiunte, peso da 1 a 3, almeno un turno che conta, validazioni
  (data non valida, nome vuoto, doppioni).
- Importazione: abbinamento dei nomi, righe non abbinate, righe dopo la prima settimana generata ignorate,
  nessun effetto su ore e statistiche delle settimane.
- Storico: contano solo le festività degli ultimi 5 anni.
- Generatore: a parità di tutto, chi ha fatto Natale l'anno scorso non lo rifà; chi ha più punti festivi ne riceve
  meno; una festività di peso 3 conta come tre di peso 1; al massimo un festivo a testa nella settimana quando possibile.

---

## 4. Ordine di lavoro

Ogni fase è un commit di test (rossi) seguito da un commit di implementazione (verdi), come nella storia del progetto.

1. **Refactor** di `_richieste` in `_rotazioni` con la tabella delle categorie, senza cambiare il comportamento.
2. **Ascoli a rotazione** + colonna nelle statistiche.
3. **Assistenze ed Extra a rotazione** + colonna nelle statistiche.
4. **Calendario delle festività**: database, API, scheda Impostazioni con turni che contano e peso, giorni
   evidenziati in griglia e stampa (ancora senza effetto sul generatore).
5. **Storico festività**: tabelle, pagina di inserimento a mano, importazione da file.
6. **Festività nel generatore** + statistiche e riepiloghi.
7. **Simulazione** (`cvap/simulazione.py`): più settimane con festività e storico importato, per tarare i pesi;
   aggiornamento di `docs/API.md`, README e guida per i dipendenti.

Le fasi 1–3 sono piccole e indipendenti dalle festività: si possono rilasciare subito.

---

## 5. Decisioni e domande aperte

### Decisioni prese

| Domanda | Decisione |
|---|---|
| Assistenze ed Extra: turni o ore? | **Turni** (ognuno vale 1, qualunque sia la durata) |
| Festività: quali turni contano? | **Si scelgono dal calendario**, per ogni festività: giorno, notte, notte della sera prima |
| Quanti anni considerare per le festività? | **5 anni** |
| Festività più importanti? | **Peso scelto dal calendario**, per ogni festività: 1 normale, 2 importante, 3 molto importante |
| Storico di Ascoli e Assistenze | **Si parte dalla prima settimana generata**, senza dati passati |

### Ancora aperte (se non indicato diversamente, si applica la proposta)

- **A. Ascoli:** oltre al numero di turni, equilibrare nel tempo anche giorni e notti ad Ascoli? (proposta: no, per ora basta l'alternanza nella settimana)
- **B. Assistenze:** evitare due Assistenze alla stessa persona nella stessa settimana? (proposta: sì)
- **C. Rotazione delle festività:** sia sul totale sia sulla singola festività? (proposta: sì, entrambe)
- **D. Festivo di domenica:** conta sia come weekend sia come festivo? (proposta: sì)

## 6. Cosa mi serve per lo storico delle festività

- Per gli **ultimi 5 anni** (dalla fine del 2021 alla prima settimana generata, ottobre 2026): **chi ha lavorato
  ogni festività, di giorno e di notte**, nel formato della tabella del punto 3.2 (Excel, CSV o anche un elenco
  scritto, che converto io). Bastano le festività che si spunteranno nel calendario.
- Per ogni anno: **chi era in servizio** (basta segnalare chi non c'era ancora o non c'era più, rispetto al personale di oggi).
- I nomi scritti come in **Personale**, o l'elenco delle corrispondenze se sono scritti in altro modo.
