# CVAP turnistica: istruzioni per Claude

Rispondi in italiano. Stato del lavoro e cose aperte: `data/NOTE.md` (leggilo a inizio sessione se serve continuità).

## Risparmio di token
- Cerca con Grep/Glob prima di leggere; leggi solo le righe che servono (offset/limit); non rileggere file già letti.
- Browser: per controllare il funzionamento usa `take_snapshot`, la console o `evaluate_script`; `take_screenshot`
  solo per verifiche dell'aspetto grafico, e il meno possibile.
- Agenti: compiti piccoli (testi, documenti, ritocchi) senza agenti; funzionalità vere con una sola revisione
  finale (`ecc:code-reviewer`), non più revisori in parallelo.
- Output dei comandi: usa `tail`/`grep` per mostrare solo le righe utili (es. esito dei test).

## Progetto
- Python FastAPI + SQLite/Turso + OR-Tools CP-SAT; frontend JavaScript semplice in `static/`.
- Test: `.venv/Scripts/python.exe -m pytest -n 4`; durante il lavoro solo i test pertinenti, suite completa prima del merge.
- `data/` contiene dati veri ed è fuori da git: non committarlo mai.
- Script e test devono impostare `CVAP_DB` prima di importare `cvap.app` (altrimenti tocca `data/turni.db`).
- Push e PR solo se l'utente lo chiede; l'utente apre le PR da sé.
