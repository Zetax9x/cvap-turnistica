---
name: usa-agenti-ecc
description: "Regola fissa: usare SEMPRE tutte le skill e gli agenti ecc pertinenti, a ogni fase del lavoro (piano, TDD, sviluppo in parallelo, revisioni, prova dal vivo, commit)"
metadata:
  node_type: memory
  type: feedback
  originSessionId: d6202b15-3d98-484f-8f4a-e580dcbfa253
  modified: 2026-11-01T18:15:09.593Z
---

L'utente l'ha chiesto più volte: il 2026-10-19 ("Utilizza sempre tutti gli agenti e gli strumenti di ecc"), il 2026-11-01 ("usa multi agenti ed tutte le skill e agenti ecc") e di nuovo il 2026-11-01, chiedendo che diventi una regola fissa prima della fase 5.

**Why:** vuole che ogni modifica passi dai flussi specializzati e dalle revisioni del plugin ecc, non solo da modifiche fatte a mano; è la sua istruzione predefinita, da applicare senza che la ripeta.

**How to apply:** su ogni fase o funzionalità di [[cvap-turnistica-progetto]], senza aspettare che lo chieda:
- Piano: ecc:planner (backend) ed ecc:code-explorer (frontend) in parallelo; skill ecc:plan / ecc:tdd-workflow.
- TDD: commit dei test rossi, poi dell'implementazione (stile del progetto), come in ecc:tdd-guide.
- Sviluppo: agenti in parallelo su file diversi (es. general-purpose per static/ mentre si scrive il backend), senza commit da parte loro.
- Revisioni in parallelo dopo il codice: ecc:python-reviewer (o fastapi-reviewer), ecc:security-reviewer per input/API, ecc:typescript-reviewer per static/js, ecc:code-reviewer, ecc:silent-failure-hunter; ecc:commit-reviewer prima dei commit.
- Prova dal vivo nel browser (chrome-devtools, skill run): il 2026-11-01 ha trovato un bug che il revisore non aveva visto.
- Saltare solo skill/agenti di altri linguaggi o domini (Go, Rust, Bengali, healthcare…).
- Test in parallelo con `pytest -n 4` (vedi [[test-suite-solo-al-merge]]).
