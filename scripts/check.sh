#!/bin/sh
# Everything that can be checked without a running CARE. Run before committing.
set -e
cd "$(dirname "$0")/.."
python3 -m catalogue.build
python3 -m catalogue.tests.test_guard
python3 -m catalogue.tests.test_validate
python3 -m care_phc.tests.test_thread
python3 -m care_phc.tests.test_token
(cd care_phc_mcp && go vet ./... && go test ./...)
python3 scripts/gen-fixtures.py
if [ -d care_phc_fe/node_modules ]; then
  (cd care_phc_fe && npx tsc -b && npm run build >/dev/null)
  echo "ok   care_phc_fe typechecks and builds"
else
  echo "warn care_phc_fe: run npm install to check the frontend"
fi
printf '\nall checks passed\n'
