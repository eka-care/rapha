#!/bin/sh
# Everything that can be checked without a running CARE. Run before committing.
set -e
cd "$(dirname "$0")/.."
python3 -m catalogue.build
python3 -m catalogue.tests.test_guard
python3 -m catalogue.tests.test_validate
python3 -m care_phc.tests.test_thread
git diff --exit-code catalogue/catalogue.json >/dev/null 2>&1 || {
  echo "FAIL catalogue.json is not the compiled form of the atoms; commit it"; exit 1; }
echo "\nall checks passed"
