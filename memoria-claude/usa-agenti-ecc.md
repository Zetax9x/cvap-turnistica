---
name: usa-agenti-ecc
description: "L'utente vuole che si usino sempre gli agenti e le skill ecc (plugin ecc) nel lavoro sul progetto"
metadata:
  node_type: memory
  type: feedback
  originSessionId: ad542813-0c9c-4c0e-aed5-9a01f23fd4bb
  modified: 2026-10-19T18:44:42.204Z
---

L'utente ha chiesto (2026-10-19): "Utilizza sempre tutti gli agenti e gli strumenti di ecc."

**Why:** vuole che il lavoro passi dalle revisioni e dai flussi specializzati del plugin ecc, non solo dalle modifiche fatte a mano.

**How to apply:** per ogni modifica al codice di [[cvap-turnistica-progetto]] usare gli agenti ecc pertinenti allo stack (Python/FastAPI/CP-SAT, JS vanilla): ecc:tdd-workflow per le nuove regole, poi ecc:python-reviewer, ecc:fastapi-reviewer, ecc:code-reviewer, ecc:silent-failure-hunter, ecc:security-reviewer quando si toccano input/API, ecc:typescript-reviewer per i file in static/js, ecc:commit-reviewer prima del commit. Saltare quelli di altri linguaggi o domini (Go, Rust, Bengali, healthcare…), che non c'entrano.
