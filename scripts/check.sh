#!/bin/sh
# Everything that can be checked without a running CARE. Run before committing.
set -e
cd "$(dirname "$0")/.."
python3 -m catalogue.build
python3 -m catalogue.tests.test_guard
python3 -m catalogue.tests.test_validate
python3 -m care_phc.tests.test_thread
(cd care_phc_mcp && go vet ./... && go test ./...)
printf '\nall checks passed\n'
