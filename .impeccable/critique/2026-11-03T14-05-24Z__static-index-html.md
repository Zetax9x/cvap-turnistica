---
target: tutta l app (static/)
total_score: 28
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:C:\\Users\\yuris\\Documents\\GitHub\\cvap-turnistica\\static\\index.html"
target_fingerprint: "sha256:de02bfd5f9d3d253eefa6644b80c374c36a2118b4d670a4abb3fefe97ed2ea1e"
target_path: "C:\\Users\\yuris\\Documents\\GitHub\\cvap-turnistica\\static\\index.html"
timestamp: 2026-11-03T14-05-24Z
slug: static-index-html
closed: true
---
Method: DEGRADED single-context (sotto-agenti non usati: richiesta esplicita assente, risparmio token del progetto)

# Critique: tutta l'app (static/)

Punteggio 28/40 (Good, 70%). Heuristics: 1=3, 2=3, 3=3, 4=3, 5=3, 6=3, 7=2, 8=2, 9=3, 10=3.

## Design Specificity Verdict
- Settimana: su misura (legenda volontario / fissato a mano / generato / extra / scoperto, weekend evidenziato, sole e luna, tratteggio "turno non richiesto").
- Personale, Impostazioni, Calendario: pannelli amministrativi generici.
- Detector: 7 segnalazioni. 6 x undersized-ui-text (menu a 10,56 px, static/index.html), 1 x repeating-stripes-gradient (falso positivo: tratteggio funzionale anche in bianco e nero).

## Priority Issues
1. [P1] Griglia Settimana su telefono: 2 giorni su 7 visibili, riepilogo ore con solo Persona e Tipo. Fix: un giorno alla volta con selettore fisso. Comando: adapt.
2. [P1] Tabelle larghe tagliate senza avviso (Riepilogo ore, Statistiche, Ferie e malattia, Divieti con "Elimina" fuori vista su mobile). Fix: scorrimento visibile, prima colonna e azioni fisse. Comando: layout.
3. [P2] Calendario ripete "Settimana A/B" e "Coperta dai dipendenti" in ogni cella; su 390 px il testo va a capo per sillabe. Fix: mostrare solo le eccezioni. Comando: distill.
4. [P2] Menu mobile a 10,56 px con etichette troncate ("Dipende...", "Impostaz..."). Fix: etichette brevi, 12 px o piu. Comando: typeset.
5. [P2] Impostazioni: pagina unica da oltre 2000 px, campi "Max ore/settimana" troppo stretti, riquadro email piu stretto degli altri. Fix: sezioni richiudibili, campi della larghezza giusta. Comando: layout.

## Persona Red Flags
- Alex (chi prepara i turni ogni settimana): nessuna scorciatoia per cambiare settimana, generare, confermare.
- Casey (telefono): azioni importanti in alto, fuori dalla portata del pollice; Elimina vicino a Modifica e Disattiva.
- Sam (tastiera / schermo piccolo): menu a 10,56 px, colonne fuori vista senza indicazione. Contrasto del testo secondario sufficiente.

## Minor
- Email reali visibili nella tabella Personale.
- Controlli di navigazione settimana su tre righe a 390 px.
- Tratteggio "turno non richiesto" da conservare.
- Celle fuori mese del Calendario: tratteggio e grigio sommati.
