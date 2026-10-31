"""Run: python3 scripts/check_plugins.py

A health centre's copy is a choice, not a fork.

Two primary health centres run this file's one bundle, one catalogue and one
renderer, and differ by one declared list. What is asserted here is not that a
button is missing, which proves nothing: it is that a plugin a facility does
not run is a capability nobody holds, so the operation is absent from the
rendered surface AND from the machine surface AND refused by the guard with an
audit row, the step it closed is skipped rather than pending, and the view
whose capability it was answers 403.

The in process service below is deliberately the SMALLEST facility this bundle
ships, `consulting-room-only`, because every "off" assertion needs a kernel
that really has those plugins off. The comparisons against a centre that runs
everything load the kernel directly, which needs no socket and no second
process.

Mutations this is built to fail under are listed at the bottom of the file.
"""
from __future__ import annotations

import copy
import os
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# Before api.main is imported: it resolves its bundle and its facility at
# import time, exactly as a deployed kernel does, so the facility cannot be
# switched inside a running process and this check must not pretend it can.
os.environ["PHC_DB"] = ":memory:"
os.environ.setdefault("PHC_FACILITY", "consulting-room-only")
SHAPE = os.environ["PHC_FACILITY"]

from fastapi.testclient import TestClient                      # noqa: E402

from adapters.local.store import SqliteStore, seed             # noqa: E402
from catalogue import guard, vocab                             # noqa: E402
from kernel import declarations, plugins, state, views          # noqa: E402

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


MANIFEST = yaml.safe_load((ROOT / "bundles" / "phc" / "bundle.yaml").read_text())
# The two shapes held against each other throughout: a centre that runs every
# plugin, and one with no laboratory. Loaded through declarations.load() the
# way check.sh does, so what is compared is what a kernel would really run.
WHOLE = declarations.load("phc", facility="all-plugins")
NO_LAB = declarations.load("phc", facility="no-laboratory")
LEAST = declarations.load("phc", facility=SHAPE)
DECLS = {}
for path in sorted((ROOT / "bundles" / "phc").glob("*.md")):
    from catalogue.build import parse
    fm, body = parse(path)
    DECLS[fm["id"]] = (fm, body)


# ---------------------------------------------------------------------------
# 1. A facility's shape is one declaration, and it can hold nothing clinical.
# ---------------------------------------------------------------------------

# Two keys on a facility, three on a plugin, and every value is a list of ids
# this build already validates. There is nowhere in either to put a code, a
# value set, a unit, a range, a threshold, an interval, a question or a
# section heading, which is what keeps a facility's shape a composition
# decision rather than a clinical one made by whoever installed the software.
assert set(plugins.FACILITY_KEYS) == {"title", "without"}, plugins.FACILITY_KEYS
assert set(plugins.PLUGIN_KEYS) == {"title", "capabilities", "always"}, plugins.PLUGIN_KEYS
CLINICAL = ("code", "system", "display", "value", "unit", "range", "threshold",
            "interval", "binding", "valueset", "value_set", "question",
            "asks", "section", "profile", "mapping", "writes", "emits",
            "preconditions", "station", "states", "operations", "instrument")
for key in plugins.FACILITY_KEYS + plugins.PLUGIN_KEYS:
    for word in CLINICAL:
        assert word not in key, (key, word)
ok("a facility declaration holds %d keys and a plugin %d, and not one of them "
   "can carry a code, a value set, a threshold, an interval, a question or a "
   "section heading" % (len(plugins.FACILITY_KEYS), len(plugins.PLUGIN_KEYS)))

# Every word a plugin names is one this bundle already declares, each claimed
# once, and a capability no plugin claims is always on. The last is the default
# on rule and it is checked as a fact rather than assumed: a capability that
# fell out of every plugin would be an ability no facility could ever switch
# off, which is fine, and one claimed twice would be two switches neither of
# which works.
DECLARED_CAPS = set(MANIFEST["capabilities"])
CLAIMED = {}
for pid, decl in MANIFEST["plugins"].items():
    for cap in decl["capabilities"]:
        assert cap in DECLARED_CAPS, (pid, cap)
        assert cap not in CLAIMED, (cap, pid, CLAIMED.get(cap))
        CLAIMED[cap] = pid
assert not plugins.lint(MANIFEST, WHOLE.operations, DECLS), \
    plugins.lint(MANIFEST, WHOLE.operations, DECLS)
ok("every one of the %d capabilities the %d plugins name is declared by this "
   "bundle and claimed by exactly one of them" % (len(CLAIMED), len(MANIFEST["plugins"])))

# And every facility names only plugins that exist, never one that is always
# on, and the build's own default is one of them.
for fid, decl in MANIFEST["facilities"].items():
    for pid in decl["without"]:
        assert pid in MANIFEST["plugins"], (fid, pid)
        assert not MANIFEST["plugins"][pid].get("always"), (fid, pid)
assert MANIFEST["facility"] in MANIFEST["facilities"], MANIFEST["facility"]
ok("each of the %d facilities names only plugins this bundle declares, none of "
   "them one declared always on, and the default shape is one of the %d"
   % (len(MANIFEST["facilities"]), len(MANIFEST["facilities"])))


# ---------------------------------------------------------------------------
# 2. Two shapes, one codebase. Nothing is copied and nothing is removed.
# ---------------------------------------------------------------------------

# The compiled artifact every surface reads is byte identical between a centre
# with a laboratory and one without. That is the whole claim of the module: a
# different facility is not a different build, so a change made once is made
# for both. If this ever differs, somebody has started forking the catalogue.
import json  # noqa: E402

assert json.dumps(declarations.compile_json(WHOLE), sort_keys=True) == \
       json.dumps(declarations.compile_json(NO_LAB), sort_keys=True)
assert set(WHOLE.operations) == set(NO_LAB.operations) == set(LEAST.operations)
assert set(WHOLE.views) == set(NO_LAB.views) and set(WHOLE.metrics) == set(NO_LAB.metrics)
ok("the compiled catalogue is identical for all three shapes: %d operations, "
   "%d views and %d metrics, one copy, no fork"
   % (len(WHOLE.operations), len(WHOLE.views), len(WHOLE.metrics)))

# What differs is one dict, and it is derived from the declaration rather than
# written anywhere.
assert WHOLE.withheld == {}, WHOLE.withheld
assert NO_LAB.withheld == {"lab.order": "orders", "lab.result.enter": "orders",
                           "lab.result.validate": "orders"}, NO_LAB.withheld
assert LEAST.withheld == dict(NO_LAB.withheld,
                              **{"visit.household": "outreach",
                                 "reporting.view": "reporting"}), LEAST.withheld
assert (WHOLE.facility, NO_LAB.facility) == ("all-plugins", "no-laboratory")
ok("and what differs is one derived dict: %d capabilities withheld at a centre "
   "with no laboratory, %d at a consulting room"
   % (len(NO_LAB.withheld), len(LEAST.withheld)))

# A role keeps exactly what the facility still runs. Subtraction, not a second
# role table: bundle.yaml's presets are untouched and a facility's deviation is
# never a rewritten preset.
ROLES = vocab.for_bundle("phc").roles
for role, caps in sorted(ROLES.items()):
    assert plugins.effective(caps, WHOLE.withheld) == list(caps), role
    narrowed = plugins.effective(caps, NO_LAB.withheld)
    assert narrowed == [c for c in caps if c not in NO_LAB.withheld], role
LAB_ROLES = [r for r, caps in ROLES.items() if set(caps) & set(NO_LAB.withheld)]
assert sorted(LAB_ROLES) == ["cho", "lab", "lab_incharge", "mo"], LAB_ROLES
assert plugins.effective(ROLES["lab"], NO_LAB.withheld) == ["patient.find", "handover"]
ok("with every plugin on, no role loses a capability; with the laboratory off, "
   "%d of the %d presets do, and the presets themselves are unedited"
   % (len(LAB_ROLES), len(ROLES)))

# The facility's demo day is its own, because a seeded thread whose history
# names an operation nobody here may perform is a lie about what happened here
# and draws a card no person can confirm.
assert len(WHOLE.seed) == 7 and len(NO_LAB.seed) == 6, (len(WHOLE.seed), len(NO_LAB.seed))
for bundle in (NO_LAB, LEAST):
    for thread in bundle.seed:
        for entry in (thread.get("proposals") or []) + (thread.get("audit") or []):
            op = bundle.operations[entry["operation"]]
            assert op["capability"] not in bundle.withheld, (thread["id"], entry)
ok("and the seeded demo day shortens with the facility: %d threads become %d, "
   "and not one surviving thread's history names an operation this centre may "
   "not perform" % (len(WHOLE.seed), len(NO_LAB.seed)))


# ---------------------------------------------------------------------------
# 3. Off on the rendered surface: absent, not greyed out.
# ---------------------------------------------------------------------------

def a_store(bundle):
    store = SqliteStore(":memory:")
    seed(store, bundle.seed)
    return store


# The demo account, which is every capability this bundle declares. It is the
# strongest case: if the action is gone for the account that holds everything,
# it is gone for everybody. It is also the only account the browser can be,
# which is why this is asserted here and not with a screenshot.
def held(bundle):
    return set(plugins.effective(sorted(DECLARED_CAPS), bundle.withheld))


WITHHELD_OPS = sorted(oid for oid, op in WHOLE.operations.items()
                      if op["capability"] in LEAST.withheld)
assert WITHHELD_OPS == ["phc.op.household-visit", "phc.op.lab-order",
                        "phc.op.lab-result-enter"], WITHHELD_OPS

for bundle, expect in ((WHOLE, True), (LEAST, False)):
    # `expect` says whether this centre runs them. The positive direction is
    # the ANY_DRAWN pass below rather than a per thread assertion, because an
    # operation whose precondition is unmet is legitimately absent on some
    # threads and asserting otherwise would be asserting the wrong thing.
    store = a_store(bundle)
    wf = bundle.workflow()
    for thread in bundle.seed:
        known = state.flags(store, thread["id"], wf)
        drawn = {op["id"] for op in state.actions(wf, bundle.operations, known,
                                                  held(bundle))}
        if expect:
            continue
        for oid in WITHHELD_OPS:
            assert oid not in drawn, (bundle.facility, thread["id"], oid)
            # And the same predicate the guard enforces, asked directly, so a
            # quick action row that happened to be capped cannot pass for an
            # absence.
            assert guard.visible(bundle.operations[oid], held(bundle),
                                 known) is False, (bundle.facility, oid)
ANY_DRAWN = False
store = a_store(WHOLE)
for thread in WHOLE.seed:
    known = state.flags(store, thread["id"], WHOLE.workflow())
    if {op["id"] for op in state.actions(WHOLE.workflow(), WHOLE.operations, known,
                                         held(WHOLE))} & set(WITHHELD_OPS):
        ANY_DRAWN = True
assert ANY_DRAWN, "the three operations are drawn somewhere at a centre that " \
                  "runs every plugin, or this check proves nothing"
ok("the %d operations a consulting room may not perform are absent from the "
   "quick action row of every seeded thread, for the account that holds every "
   "capability, and drawn at a centre that runs them" % len(WITHHELD_OPS))

# The line itself is shorter: the laboratory step is skipped rather than
# pending, because nothing can raise the flag that makes it apply. Nobody
# waits at a station this centre does not have.
LAB_STEP = [s for s in LEAST.workflow().steps if s.station == "lab"]
assert len(LAB_STEP) == 1 and LAB_STEP[0].applies_when == "lab.ordered"
store = a_store(LEAST)
for thread in LEAST.seed:
    known = state.flags(store, thread["id"], LEAST.workflow())
    drawn = state.line(LEAST.workflow(), known)
    at_lab = [s for s in drawn if s.station == "lab"]
    assert [s.status for s in at_lab] == ["skipped"], (thread["id"], at_lab)
    assert state.station(LEAST.workflow(), known) != "lab", thread["id"]
ok("and the laboratory step of the line is skipped rather than pending on "
   "every one of the %d threads, so no patient stands at a station this "
   "centre does not have" % len(LEAST.seed))

# The view whose own capability a facility withholds is unreachable, and the
# metrics it names with it. A dashboard is the only way a metric is read.
DASHBOARD = WHOLE.views["phc.view.facility-dashboard"]
assert DASHBOARD.capability == "reporting.view"
assert DASHBOARD.capability in LEAST.withheld
assert DASHBOARD.capability not in held(LEAST)
UNREACHABLE = {m for v in LEAST.views.values() if v.capability in LEAST.withheld
               for m in (v.metrics or [])}
assert UNREACHABLE == set(LEAST.manifest.metrics), sorted(UNREACHABLE)
ok("a view whose capability this facility withholds is unreachable, and so are "
   "all %d metrics, because a dashboard is the only declaration that reads one"
   % len(UNREACHABLE))

# A view that is still reachable still resolves. Switching a plugin off must
# not break the screens that remain, which is the failure mode a facility
# switch has.
store = a_store(LEAST)
for vid, view in sorted(LEAST.views.items()):
    if view.capability in LEAST.withheld:
        continue
    thread = LEAST.seed[0]["id"] if view.kind == "summary" else None
    result = views.resolve(LEAST, vid, store, thread=thread, caps=held(LEAST))
    assert result.kind == view.kind, vid
ok("and every view this centre can still open resolves against its own rows: "
   "%d of %d" % (len(LEAST.views) - 1, len(LEAST.views)))


# ---------------------------------------------------------------------------
# 4. The guard refuses it, which is the part that matters.
# ---------------------------------------------------------------------------

store = a_store(LEAST)
THREAD = "enc-003"
PAYLOAD = {"investigations": ["CBC"]}
for surface in (guard.RENDERED, guard.MCP):
    decision = guard.evaluate(
        LEAST.operations["phc.op.lab-order"], caps=held(LEAST),
        state=state.flags(store, THREAD, LEAST.workflow()), payload=PAYLOAD,
        surface=surface, validate=lambda op, payload: [], performers={},
        withheld=LEAST.withheld)
    assert not decision, decision
    assert "lab.order" in decision.reason and "orders" in decision.reason, decision.reason
    assert decision.audit["outcome"].startswith("denied: capability lab.order "
                                                "withheld by plugin"), decision.audit
ok("the guard refuses it on both surfaces and the audit row names the "
   "capability AND the plugin, so an admin can reconstruct the decision "
   "against a bundle.yaml that has since been edited")

# The denial is step 2 of the same seven and nothing moved: the capability
# check runs after the payload check and before the preconditions, so a
# malformed payload sent to a plugin this centre does not run still reports
# the payload problem first. That was already true of a plain missing
# capability and is not a regression.
bad_payload = guard.evaluate(
    LEAST.operations["phc.op.lab-order"], caps=held(LEAST),
    state=frozenset(), payload={}, surface=guard.RENDERED,
    validate=lambda op, payload: ["'tests' is required"], performers={},
    withheld=LEAST.withheld)
assert "payload invalid" in bad_payload.reason, bad_payload.reason
ok("and it is the same step 2 it always was: a malformed payload is still "
   "reported before the withheld capability, as it is for any other denial")

# With no withheld map the sentence is exactly what it was. Every existing
# call site passes none, so this is what keeps the other denial strings, and
# the checks that read them, untouched.
plain = guard.evaluate(
    LEAST.operations["phc.op.lab-order"], caps=set(), state=frozenset(),
    payload=PAYLOAD, surface=guard.RENDERED, validate=lambda op, payload: [],
    performers={})
assert plain.reason == "missing capability lab.order", plain.reason
ok("and a caller that simply lacks the capability still reads 'missing "
   "capability lab.order', unchanged, because the plugin sentence is reached "
   "only through the facility's own map")


# ---------------------------------------------------------------------------
# 5. Off on the machine surface, through the service the agent really calls.
# ---------------------------------------------------------------------------

from api import main                                           # noqa: E402

client = TestClient(main.app)
main.store = main.make_store()
assert main.BUNDLE.facility == SHAPE, main.BUNDLE.facility

# GET /whoami is what care_phc_mcp builds its tool list from (its own
# `capabilities()` reads exactly this route), so a capability absent here is a
# tool absent there. The socket half of this, driving the real Go binary
# against a real kernel, is in scripts/e2e.py; this is the half that needs no
# port.
mine = set(client.get("/api/whoami").json()["capabilities"])
for cap in LEAST.withheld:
    assert cap not in mine, cap
assert "encounter.document" in mine, "the consultation is untouched"
ok("GET /whoami, which is where the MCP server reads its tool list from, omits "
   "all %d withheld capabilities for the account that holds everything else"
   % len(LEAST.withheld))

# And the route says which shape is running and what it withholds, so the
# difference between two centres is readable rather than inferred.
facility = client.get("/api/facility").json()
assert facility["facility"] == SHAPE, facility["facility"]
assert facility["withheld"] == dict(sorted(LEAST.withheld.items()))
assert sorted(facility["capabilities"]) == sorted(DECLARED_CAPS), \
    "the declared list stays whole; only the caller's is narrowed"
ok("and GET /facility names the shape and what it withholds, while the "
   "declared capability list stays the whole %d" % len(DECLARED_CAPS))

# Called anyway, over the service, it is refused and writes nothing.
before = len(client.get("/api/threads/%s" % THREAD).json()["audit"])
for route in ("propose", "commit"):
    reply = client.post("/api/operations/phc.op.lab-order/%s" % route,
                        json={"thread": THREAD, "payload": PAYLOAD})
    assert reply.status_code == 422, (route, reply.status_code, reply.text)
    assert "lab.order" in reply.text and "orders" in reply.text, reply.text
after = client.get("/api/threads/%s" % THREAD).json()
assert len(after["audit"]) == before + 2, (before, len(after["audit"]))
assert all(r["outcome"].startswith("denied: capability lab.order withheld by plugin")
           for r in after["audit"][-2:]), after["audit"][-2:]
assert not after["proposals"], after["proposals"]
rows = main.store.count("service_request", thread=THREAD, where={})
assert rows == 0, rows
ok("called anyway over the service it is refused on both routes, two audit "
   "rows are written naming the plugin, no proposal is queued and no row lands")

# The dashboard this centre does not run answers 403 with the capability named,
# and the ones it does run still open.
assert client.get("/api/views/phc.view.facility-dashboard").status_code == 403
assert "reporting.view" in client.get("/api/views/phc.view.facility-dashboard").text
assert client.get("/api/views/phc.view.station-queue").status_code == 200
assert client.get("/api/queue").status_code == 200
ok("the dashboard this centre does not run answers 403 naming the capability, "
   "and the queue it does run still opens")


# ---------------------------------------------------------------------------
# 6. The lint that keeps it honest.
# ---------------------------------------------------------------------------

def bend(**changes):
    """A copy of the real manifest with one thing wrong."""
    out = copy.deepcopy(MANIFEST)
    for key, value in changes.items():
        out[key] = value
    return out


def refused(manifest, fragment):
    bad = plugins.lint(manifest, WHOLE.operations, DECLS)
    assert any(fragment in line for line in bad), (fragment, bad)


# A facility naming a plugin that does not exist is a switch wired to nothing.
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"]["without"] = ["ordrs"]
refused(bend(facilities=shapes), "switches off 'ordrs', which is not a plugin")

# A facility switching off the floor.
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"]["without"] = ["baseline"]
refused(bend(facilities=shapes), "'baseline', which is declared always on")

# A plugin naming a capability this bundle does not declare.
pls = copy.deepcopy(MANIFEST["plugins"])
pls["orders"]["capabilities"] = ["lab.ordr"]
refused(bend(plugins=pls), "names 'lab.ordr', which this bundle does not declare")

# Two plugins claiming one capability: two switches, neither of which works.
pls = copy.deepcopy(MANIFEST["plugins"])
pls["outreach"]["capabilities"] = ["visit.household", "lab.order"]
refused(bend(plugins=pls), "claims 'lab.order', which plugin 'orders' already claims")

# The spelling YAML eats. `off: [orders]` parses as a key named False and the
# facility withholds nothing, which is the failure this module was written
# with before the message existed.
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"] = {"title": "A centre with no laboratory", False: ["orders"]}
refused(bend(facilities=shapes), "the key is `without`. YAML reads a bare on or off")

# A declared facility with no default, and a default that is not one of them.
refused({k: v for k, v in MANIFEST.items() if k != "facility"},
        "declares facilities and no `facility:`")
refused(bend(facility="no-such-centre"), "is not one of the declared facilities")

# Unknown keys on either declaration, and a plugin missing its words.
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"]["threshold"] = 7
refused(bend(facilities=shapes), "unknown key 'threshold'")
pls = copy.deepcopy(MANIFEST["plugins"])
pls["orders"].pop("capabilities")
refused(bend(plugins=pls), "missing capabilities")
ok("the lint refuses the eight ways a facility declaration looks configured "
   "and is not: an unknown plugin, the floor switched off, an undeclared "
   "capability, one claimed twice, the spelling YAML reads as a boolean, a "
   "missing default, an unknown default and an unknown key")

# And the one that matters most: a choice that stops the line. A step nothing
# left can close and nothing can skip means every patient waits at that
# station forever, which is a silently broken centre rather than a smaller one.
pls = copy.deepcopy(MANIFEST["plugins"])
pls["baseline"]["capabilities"] = [c for c in pls["baseline"]["capabilities"]
                                   if c != "vitals.record"]
pls["vitals"] = {"title": "Vital signs", "capabilities": ["vitals.record"]}
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"]["without"] = ["vitals"]
refused(bend(plugins=pls, facilities=shapes),
        "nothing this centre may do raises 'vitals.recorded'")
# Whereas the laboratory step, which declares an applies_when, is allowed to
# become unreachable: that IS the mechanism. A centre with no laboratory has
# no laboratory queue, and this is the line that says the two cases are told
# apart rather than both refused or both allowed.
assert not plugins.lint(MANIFEST, WHOLE.operations, DECLS)
assert any(s.station == "lab" and s.applies_when for s in WHOLE.workflow().steps)
ok("and it refuses a facility whose choice stops the line, while allowing one "
   "whose choice only skips a step the workflow already declared skippable: "
   "the difference is the step's own applies_when, and both cases are proved")

# A facility may not reach anything clinical, because there is nothing clinical
# in reach. Proved by handing the resolver a facility that tries: the keys are
# refused rather than ignored, so a threshold typed here fails the build
# instead of being silently dropped.
shapes = copy.deepcopy(MANIFEST["facilities"])
shapes["no-laboratory"].update({"asks": ["history"], "profile": "OPConsultRecord",
                                "sections": {"ChiefComplaints": []}})
bad = plugins.lint(bend(facilities=shapes), WHOLE.operations, DECLS)
for key in ("asks", "profile", "sections"):
    assert any("unknown key '%s'" % key in line for line in bad), (key, bad)
ok("a facility that tries to declare a form, a profile or a section heading is "
   "refused key by key rather than having them quietly ignored")


# ---------------------------------------------------------------------------
# 7. The gate runs the lint, rather than only owning it.
# ---------------------------------------------------------------------------
#
# Everything in section 6 asks plugins.lint() directly, which proves the rule
# and not the wiring: deleting the one call in kernel/declarations.py leaves
# every assertion above passing. So this loads a bent bundle through
# declarations.load(), the way check.sh does, and asserts the bundle refuses to
# load at all. Module 14 found this hole the same way.
import tempfile                                                # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    home = pathlib.Path(tmp) / "bundles"
    (home / "phc").mkdir(parents=True)
    for src in (ROOT / "bundles" / "phc").iterdir():
        if src.is_file():
            (home / "phc" / src.name).write_text(src.read_text())
    bent = copy.deepcopy(MANIFEST)
    bent["facilities"]["no-laboratory"]["without"] = ["baseline"]
    (home / "phc" / "bundle.yaml").write_text(yaml.safe_dump(bent, sort_keys=False))
    was = declarations.BUNDLES
    try:
        declarations.BUNDLES = home
        try:
            declarations.load("phc")
            raise AssertionError("a facility switching off the floor loaded")
        except declarations.DeclarationError as exc:
            assert "declared always on" in str(exc), str(exc)
    finally:
        declarations.BUNDLES = was
assert declarations.load("phc").manifest.id == "phc", "the real bundle still loads"
ok("the gate runs the plugin lint rather than only owning it: a facility "
   "switching off the floor makes kernel/declarations.py refuse the bundle")

# And the subtraction is wired too. Deleting it from api/main.py caller() left
# every kernel level assertion above passing, because they compute the narrowed
# set themselves. This asks the service what the caller holds, for each
# declared role, and holds it against what the resolver says it should be.
for role in sorted(vocab.for_bundle("phc").roles):
    served = client.get("/api/whoami?role=%s" % role).json()["capabilities"]
    assert served == plugins.effective(ROLES[role], LEAST.withheld), role
ok("and the subtraction is wired into the service: what /whoami serves each of "
   "the %d presets is what the resolver says, not what bundle.yaml says"
   % len(ROLES))


# ---------------------------------------------------------------------------
# 8. The resolver names no facility's words.
# ---------------------------------------------------------------------------
#
# The same rule every engine module is held to, for the same reason: a module
# that types a capability, a station, a flag, a plugin id or a facility id has
# opinions about one facility and is not the thing that makes two of them
# possible. Read off the compiled catalogue and the manifest, so it grows when
# a bundle does.
from engine_code import engine_code                            # noqa: E402

WORDS = sorted(
    set(DECLARED_CAPS) | set(MANIFEST["states"]) | set(MANIFEST["stations"])
    | set(MANIFEST["roles"]) | set(MANIFEST["plugins"]) | set(MANIFEST["facilities"])
    | set(MANIFEST["operations"]) | {MANIFEST["id"], MANIFEST["facility"]})
assert len(WORDS) >= 60, len(WORDS)
live = engine_code(ROOT / "kernel" / "plugins.py")
assert live.strip() and "\ndef\n" in live, "the stripper found no code"
assert '"""' not in live, "a docstring survived the strip"
typed = [w for w in WORDS if '"%s"' % w in live or "'%s'" % w in live]
assert not typed, "kernel/plugins.py types this facility's word(s) %r" % typed
ok("the resolver types none of this facility's %d declared words: not a "
   "capability, a station, a flag, a role, a plugin id, a facility id or an "
   "operation" % len(WORDS))


print("ok   a facility's shape: %d checks passed" % checks)

# ---------------------------------------------------------------------------
# What this fails under. Each was run, and the check that failed first is
# named, because a mutation that breaks parsing fails everything for the wrong
# reason.
# ---------------------------------------------------------------------------
#
# - have `effective()` return `caps` unchanged: section 2's role subtraction
#   fails first, on the laboratory preset.
# - have `withheld()` ignore the facility and return {}: section 2's "what
#   differs is one derived dict" fails first.
# - have `off()` read the plugin list of every facility rather than the chosen
#   one: section 2's withheld dicts fail, because the consulting room's three
#   plugins come back for every shape.
# - delete the subtraction from api/main.py caller(): section 5's /whoami
#   check fails, and section 7's per preset check fails too, which is the
#   point of having both.
# - delete `plugins.lint` from kernel/declarations.load(): section 7's wiring
#   check fails and nothing in section 6 notices.
# - drop the plugin name from the guard's withheld denial: section 4's first
#   check fails on the audit outcome.
# - have the guard reach the withheld sentence without a withheld map:
#   section 4's last check fails, because an ordinary missing capability stops
#   reading "missing capability lab.order".
# - exempt a step with an applies_when from the stop the line rule by
#   exempting every step: section 6's last lint check fails, because a
#   facility that switches off vital signs loads.
# - apply the stop the line rule to every step including the skippable ones:
#   the real bundle stops loading, and section 1's "the real manifest lints
#   clean" fails first.
# - have `seeded()` keep every thread: section 2's seed check fails on the
#   count, and the per thread check fails on the laboratory proposal.
