"""Run: python3 -m adapters.care.tests.test_live

The only check in this repo that talks to a real CARE. It is READ ONLY and it
must stay that way: the instance it reads is OHC's shared public deployment,
and writing test patients into somebody else's environment is not acceptable.
Every request here is a GET, there is no token, and the assertion below that
nothing but GET was issued is what keeps it that way.

What it proves
--------------
The five fields marked LIVE in adapters/care/map.py, and the pagination
envelope this adapter pages with. /api/v1/govt/organization/ is the one
endpoint on the public instance that answers without credentials, so it is the
whole of what can be verified against a real response body from here. Everything
else in map.py is marked SCHEMA, from the OpenAPI document the same running
instance publishes, or INFERRED.

Skipped without complaint when there is no network, and by SKIP_E2E=1, exactly
as scripts/e2e.py's socket half is.
"""
import os
import sys
import urllib.error

from adapters.care import map as care_map
from adapters.care.store import http_transport

BASE = os.environ.get("CARE_LIVE_BASE", "https://careapi.ohc.network")
PUBLIC = "/api/v1/govt/organization/"


def demo():
    if os.environ.get("SKIP_E2E"):
        print("warn care live check skipped: SKIP_E2E is set")
        return
    issued = []
    transport = http_transport(BASE, token=None)

    def read_only(method, path, params=None, body=None):
        assert method == "GET" and body is None, \
            "this check is read only against somebody else's instance"
        issued.append((method, path))
        return transport(method, path, params, None)

    try:
        status, page = read_only("GET", PUBLIC, {"limit": 2}, None)
    except (urllib.error.URLError, OSError) as exc:
        print("warn care live check skipped: %s is unreachable (%s)" % (BASE, exc))
        return
    if status != 200:
        print("warn care live check skipped: %s answered %s" % (BASE, status))
        return

    # The envelope adapters/care/store.py pages with. The schema declares next
    # and previous on this very endpoint; the real response carries neither,
    # which is why the adapter never follows them.
    assert set(page) == {"count", "results"}, sorted(page)
    assert isinstance(page["count"], int) and page["count"] > 0
    rows = page["results"]
    assert len(rows) == 2, "limit is honoured"

    # The five LIVE marks in map.py, read off the row rather than trusted.
    spec = care_map.RESOURCES["organization"]
    row = rows[0]
    for name, field in spec.fields.items():
        assert field.verified == care_map.LIVE, name
        if name == "parent":
            continue            # a top level organization has an empty parent
        assert field.read(row) is not None, \
            "map.py claims organization.%s is live and it is not on the wire" % name
    assert spec.fields["name"].read(row) == row["name"]
    assert spec.fields["code"].read(row) == row["org_type"]

    # offset, which is how the adapter pages.
    _, second = read_only("GET", PUBLIC, {"limit": 2, "offset": 2}, None)
    assert [r["id"] for r in second["results"]] != [r["id"] for r in rows]

    # And the error shape a missing token produces, which CareError carries.
    status, body = read_only("GET", "/api/v1/patient/", {"limit": 1}, None)
    assert status in (401, 403), status
    assert "detail" in body, body

    assert {m for m, _ in issued} == {"GET"}, issued
    print("ok   %d live reads against %s, envelope and five field names "
          "confirmed" % (len(issued), BASE))


if __name__ == "__main__":
    demo()
    sys.exit(0)
