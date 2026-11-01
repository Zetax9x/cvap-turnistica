---
name: test-suite-solo-al-merge
description: Durante il lavoro a step lanciare solo i test pertinenti; la suite completa solo prima del merge del branch
metadata:
  node_type: memory
  type: feedback
  originSessionId: 19ba6292-869c-4748-9328-add6409c325e
  modified: 2026-11-01T16:06:59.425Z
---

Lavorando a un piano a più fasi: un commit per ogni step, lanciando solo i file di test pertinenti (es. test_solver, test_speciali, test_storico, test_extra, test_simulazione per il generatore). La suite completa (500+ test) si lancia una volta sola, a piano finito, prima del merge del branch.

**Why:** l'utente (2026-11-01) non vuole aspettare tutta la suite a ogni passo; la macchina ha 2 CPU e i test CP-SAT sono lenti.

**How to apply:** non lanciare `pytest` senza argomenti durante gli step; farlo solo prima del merge. Vedi [[cvap-turnistica-progetto]].
