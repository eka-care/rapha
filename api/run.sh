#!/bin/sh
# Run the kernel API on :8000. PHC_DB names the SQLite file; delete it to
# reseed. PHC_BUNDLE picks the declaration bundle.
set -e
cd "$(dirname "$0")/.."
export PHC_DB="${PHC_DB:-phc.sqlite3}"
export PHC_BUNDLE="${PHC_BUNDLE:-phc}"
echo "kernel API on http://127.0.0.1:${PORT:-8000}  bundle=$PHC_BUNDLE  db=$PHC_DB"
exec python3 -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT:-8000}" "$@"
