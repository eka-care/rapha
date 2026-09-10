"""Run every check: python3 -m catalogue.tests"""
import runpy
import sys

for mod in ("catalogue.tests.test_guard", "catalogue.tests.test_validate"):
    print(f"--- {mod}")
    runpy.run_module(mod, run_name="__main__")
print("all checks passed", file=sys.stderr)
