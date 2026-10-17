#!/usr/bin/env bash
# Avvia CVAP Turnistica su http://localhost:8000 (database in data/turni.db, o $CVAP_DB).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
# HOST=0.0.0.0 per renderlo raggiungibile da altri dispositivi della rete (nessun login!)
exec "$PY" -m uvicorn cvap.app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" "$@"
