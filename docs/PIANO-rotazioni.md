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
- `calcola_storico` aggiorna i due contatori, nelle stesse settimane che contano già per gli altri (dalla prima generata).

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
- Da decidere (domanda 2): anche **giorno/notte ad Ascoli nel tempo** (contatori `ascoli_giorno` e `ascoli_notte`),
  oltre all'alternanza nella settimana.

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
- Penalità per il secondo turno di Assistenze nella stessa settimana: sì, per allargare la rotazione (domanda 1b).
- Da decidere (domanda 1): contare **turni** (come Standby) o **ore**? Le Assistenze durano da 1 a 24 ore: contando
  i turni, chi fa un'assistenza di 2 ore vale come chi ne fa una di 12. Proposta: contare i turni (più semplice e
  coerente con Standby e Programmati), visto che l'equilibrio delle ore c'è già.

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

- nel **totale**: nel tempo ognuno fa una quota simile di turni festivi;
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
- **Quali turni contano**, per ogni festività: il giorno (8–20), la notte che inizia quel giorno (20–8) e, se si
  vuole, la notte della sera prima. Esempio: la "notte di Natale" 24→25 nel programma è un turno del 24, perché la
  notte appartiene al giorno in cui inizia. Predefinito: giorno e notte del giorno stesso (domanda 3).
- **Anteprima** delle date dell'anno in corso e del prossimo, con Pasqua e Pasquetta calcolate.
- Nella **griglia della settimana** e nella **stampa** i giorni festivi sono evidenziati con il nome della festività.

Dati e API:

```
festivita(id INTEGER PK AUTOINCREMENT, nome TEXT NOT NULL,
          regola TEXT NOT NULL,          -- 'fissa' (giorno/mese ogni anno) | 'pasqua' (offset da Pasqua) | 'data' (una sola volta)
          giorno INTEGER, mese INTEGER, offset_pasqua INTEGER, data TEXT,
          conta_giorno INTEGER NOT NULL DEFAULT 1, conta_notte INTEGER NOT NULL DEFAULT 1,
          conta_notte_prima INTEGER NOT NULL DEFAULT 0,
          attiva INTEGER NOT NULL DEFAULT 0)
```

- Predefinite inserite all'avvio (non attive), come oggi le postazioni.
- `cvap/festivita.py` (nuovo): `pasqua(anno)` (algoritmo di Gauss/Meeus, senza dipendenze esterne),
  `date_festive(festivita, anno) -> dict[date, nome]`,
  `turni_festivi(festivita, dal, al) -> dict[(data_inizio_turno, fascia), id_festività]`.
- API: `GET /api/festivita`, `POST /api/festivita`, `PUT /api/festivita/{id}`, `DELETE /api/festivita/{id}`
  (le predefinite si attivano o disattivano, non si cancellano); `GET /api/settimane/{data}` aggiunge
  `festivi: [{data, nome}]`.

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

### 3.3 Regole nel generatore

- **Esposizione** di un dipendente = turni festivi "possibili" nel periodo considerato in cui era in servizio:
  - anni importati: le festività di quell'anno, se era nell'elenco di chi era in servizio;
  - settimane del programma: le festività in cui era tra i dipendenti della settimana e non in ferie.
- **Totale equo:** debito = turni festivi fatti (anni importati + programma) + già fissati − tasso × esposizione.
  Ogni turno festivo costa `P_FESTIVI × (2 × debito + 1)`.
- **Rotazione della singola festività:** chi ha lavorato **la stessa festività l'anno prima** paga
  `P_STESSA_FESTIVITA` per rifarla (eventualmente metà peso se l'ha fatta due anni prima).
- **Non più di un turno festivo a testa nella stessa settimana** (es. Natale + Santo Stefano):
  penalità `P_DOPPIO_FESTIVO`, come per i weekend.
- **Periodo considerato:** ultimi N anni (nuova impostazione, proposta 3; domanda 5).
- **Festivo di domenica:** conta sia come weekend sia come festivo (domanda 6).
- **Volontari:** i turni festivi coperti dai volontari non entrano nella rotazione (contano solo i turni dei dipendenti).
- Pesi di partenza, da tarare con la simulazione:

  | Penalità | Proposta | Confronto con quelle esistenti |
  |---|---|---|
  | `P_FESTIVI` | 60 per turno, sul debito | il doppio dei weekend (30): i festivi pesano di più |
  | `P_STESSA_FESTIVITA` | 500 | sopra il doppio weekend (300), sotto i tre di fila (5.000) |
  | `P_DOPPIO_FESTIVO` | 300 | come il doppio weekend |

  Nessuna di queste supera i vincoli più importanti (copertura, ore minime, differenza massima, regole di Ascoli):
  la rotazione dei festivi sceglie *tra* le soluzioni che rispettano le regole.
- Lo storico dei festivi si ricalcola ogni volta, come quello attuale: se si aggiunge una festività al calendario,
  conta subito anche per le settimane già fatte nel programma; per gli anni importati conta solo se è nei dati.

### 3.4 Dove si vede

- Statistiche: colonna **Festivi** (totale nel periodo considerato, con il dettaglio per festività), anche nel
  riepilogo via email; `GET /api/statistiche`: campo `festivi: {totale, per_festivita}`.
- Riepilogo per dipendente: turni festivi del periodo.
- Pagina **Storico festività**: per ogni anno chi ha lavorato ogni festività, importato o dal programma.

### Test

- `pasqua(anno)` per alcuni anni noti (es. 2025 → 20/4, 2026 → 5/4, 2027 → 28/3).
- `date_festive` e `turni_festivi`, compresa l'opzione "notte della sera prima".
- API del calendario: attivazione, festività aggiunte, validazioni (data non valida, nome vuoto, doppioni).
- Importazione: abbinamento dei nomi, righe non abbinate, righe dopo la prima settimana generata ignorate,
  nessun effetto su ore e statistiche delle settimane.
- Generatore: a parità di tutto, chi ha fatto Natale l'anno scorso non lo rifà; chi ha più festivi ne riceve meno;
  al massimo un festivo a testa nella settimana quando possibile.

---

## 4. Ordine di lavoro

Ogni fase è un commit di test (rossi) seguito da un commit di implementazione (verdi), come nella storia del progetto.

1. **Refactor** di `_richieste` in `_rotazioni` con la tabella delle categorie, senza cambiare il comportamento.
2. **Ascoli a rotazione** + colonna nelle statistiche.
3. **Assistenze ed Extra a rotazione** + colonna nelle statistiche.
4. **Calendario delle festività**: database, API, scheda Impostazioni, giorni evidenziati in griglia e stampa
   (ancora senza effetto sul generatore).
5. **Storico festività**: tabelle, pagina di inserimento a mano, importazione da file.
6. **Festività nel generatore** + statistiche e riepiloghi.
7. **Simulazione** (`cvap/simulazione.py`): più settimane con festività e storico importato, per tarare i pesi;
   aggiornamento di `docs/API.md`, README e guida per i dipendenti.

Le fasi 1–3 sono piccole e indipendenti dalle festività: si possono rilasciare subito.

---

## 5. Domande aperte

1. **Assistenze ed Extra:** contare i turni o le ore? (proposta: turni)
   1b. Evitare due Assistenze alla stessa persona nella stessa settimana? (proposta: sì)
2. **Ascoli:** oltre al numero di turni, equilibrare nel tempo anche giorni e notti ad Ascoli?
3. **Festività, turni che contano:** giorno e notte del giorno stesso? Anche la notte della sera prima
   (es. 24→25 per Natale)? Oppure si aggiunge la Vigilia come festività a sé?
4. **Rotazione:** sia sul totale sia sulla singola festività (proposta), o solo una delle due?
5. **Quanti anni** considerare? (proposta: 3)
6. **Festivo di domenica:** conta sia come weekend sia come festivo? (proposta: sì)
7. **Festività più importanti:** Natale, Capodanno, Ferragosto devono pesare più delle altre?
8. **Storico di Ascoli e Assistenze:** si parte da zero dalla prima settimana generata, o ci sono dati passati?

## 6. Cosa mi serve per lo storico delle festività

- Per ogni anno passato da considerare: **chi ha lavorato ogni festività, di giorno e di notte**, nel formato della
  tabella del punto 3.2 (Excel, CSV o anche un elenco scritto, che converto io).
- Per ogni anno: **chi era in servizio** (basta segnalare chi non c'era ancora o non c'era più, rispetto al personale di oggi).
- I nomi scritti come in **Personale**, o l'elenco delle corrispondenze se sono scritti in altro modo.
