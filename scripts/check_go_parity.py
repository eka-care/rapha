"""Run: python3 scripts/check_go_parity.py

The Go backend's answers against the Python's, field for field, over two real
sockets at once.

Why this is a differential check and not a Go test
--------------------------------------------------
The port's rule is that the Python is right and the Go is wrong where they
disagree (docs/superpowers/plans/2026-10-31-go-backend-port.md). A Go test
asserting a literal shape would be a THIRD opinion: it would pass while both
engines drifted from each other, because the literal would have been copied
from whichever one was read last. So nothing here is written down. Both
kernels are started on the same declarations with the same environment, asked
the same question, and the two answers are compared.

What this does NOT do
---------------------
Replace the socket level checks. scripts/e2e.py and scripts/check_live.py are
the acceptance test and they run against either backend through
PHC_BACKEND; this is the narrower thing they cannot be, which is a
side-by-side diff. A route Go does not serve yet is named here, not skipped in
silence, so the list of what is still owed is in the output of a check rather
than in a commit message.

Also NOT done here: a shape with no PHC_FACILITY at all. bundles/phc declares
`facility: all-plugins`, so the default IS a shape and the empty case is
bundles/lab's, which the Go backend cannot serve yet at all (one bundle; see
cmd/api/main.go).
"""
from __future__ import annotations

import functools
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backend                                                       # noqa: E402

PREFIX = "/api/v1/phc"
QUESTIONNAIRES = ROOT / "questionnaires"
# The shapes bundles/phc declares. Every one of them, rather than a chosen
# two: a shape is one declared line and the whole point is that nothing else
# differs, so there is no reason to leave one out.
SHAPES = ("all-plugins", "no-laboratory", "consulting-room-only")
# The read routes both engines serve today whose whole answer can be asked
# for with a bare GET and no state. Each is asked under both prefixes, because
# /api and /api/v1/phc are one router in the Python and two mounts in the Go,
# and that is exactly the kind of difference a diff should catch.
SERVED = ("/whoami", "/facility")
# The write path, which cannot be compared that way: every one of these needs
# a thread, most need a payload, and three of them need a proposal that a
# previous call issued. They are compared by walk() below, which runs the same
# scenario against both engines and diffs what each one answered at every
# step. Listed here so the "what Go does not serve yet" loop does not expect
# a 501 from a route that is now served.
WRITE_PATH = ("/threads", "/operations", "/proposals")

checks = 0


def ok(what):
    global checks
    checks += 1
    print("ok   %s" % what)


def call(base, path, *, method="GET", headers=None, body=None):
    """(status, parsed body). Nothing is expected here: what each engine
    answered is the thing being compared, so a 4xx is data and not a failure.
    """
    sent = dict(headers or {})
    raw_body = None
    if body is not None:
        raw_body = json.dumps(body).encode()
        sent["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, method=method, headers=sent,
                                 data=raw_body)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    return status, (json.loads(raw) if raw else {})


def get(base, path, headers=None, expect=200):
    status, body = call(base, path, headers=headers)
    assert status == expect, "GET %s: expected %s, got %s %s" % (
        path, expect, status, str(body)[:400])
    return body


# --------------------------------------------------------------------------
# payloads, built from the declarations rather than typed here
# --------------------------------------------------------------------------
#
# A payload is an INPUT and a status or a sentence is an EXPECTATION, and this
# file may hold the first and may not hold the second. So the payloads are
# generated from the questionnaires on disk: every required question answered
# with a value its own declaration says is legal, which means a form that
# grows a required question grows these payloads too instead of silently
# starting to be refused.
#
# The one place a literal would be a bug and is avoided twice over: scenario()
# below asserts the Python ACCEPTED every payload it meant to be accepted, so
# a filler that produced nonsense fails this check loudly instead of comparing
# two engines agreeing about a refusal nobody intended.

@functools.lru_cache(maxsize=None)
def schema(slug):
    return json.loads((QUESTIONNAIRES / ("%s.json" % slug)).read_text())


def _phc(question):
    return (question.get("styling_metadata") or {}).get("phc") or {}


def _middle(question):
    """A number inside every band this question declares.

    The CRITICAL band when there is one, so an ordinary reading does not raise
    a flag; the physiological range otherwise. Both ends are the
    declaration's, so a range that moves moves this.
    """
    band = _phc(question).get("critical") or _phc(question).get("range")
    if not band:
        return 1
    middle = (band["low"] + band["high"]) / 2
    return int(middle) if question["type"] == "integer" else round(middle, 1)


def _answer(question, codes):
    """One legal answer to one question, from the question's own declaration.

    `codes` resolves a value set slug to a code it holds, so a question whose
    ANSWER carries the concept is answered with a concept rather than a word.
    """
    kind = question["type"]
    if kind in ("integer", "decimal", "quantity"):
        return _middle(question)
    if kind == "boolean":
        return True
    if kind == "choice":
        options = [o["value"] for o in question.get("answer_option") or []]
        if options:
            return options[0]
        slug = question.get("answer_value_set")
        if slug:
            return codes(slug, question)
        return "unknown"
    if kind == "date":
        return "2026-01-01"
    if kind == "dateTime":
        return "2026-01-01T00:00:00Z"
    if kind == "time":
        return "09:00"
    if kind == "url":
        return "https://example.invalid/x"
    return "parity"


def filled(slug, codes, *, every=False):
    """A payload for this questionnaire: every required question answered.

    `every=True` answers the optional ones too, which is what exercises the
    mapping's fan-out (six vitals rather than three) and the terminology's
    unit rule.
    """
    def rows(questions):
        out = {}
        for question in questions:
            wanted = question.get("required") or every
            if question.get("type") == "group" and question.get("repeats"):
                if wanted:
                    out[question["link_id"]] = [rows(question["questions"] or [])]
                continue
            if question.get("type") == "group":
                out.update(rows(question.get("questions") or []))
                continue
            if question.get("type") == "display" or not wanted:
                continue
            out[question["link_id"]] = _answer(question, codes)
        return out
    return rows(schema(slug)["questions"])


def coder():
    """A code from a cached value set, honouring `unit_of`.

    The unit question is the awkward one: its answer has to be the unit the
    OTHER answer's concept is reported in, which is the kernel's second
    terminology rule. So the picker remembers which analyte it picked and
    answers the unit question with that concept's own unit.
    """
    chosen = {}

    def pick(slug, question):
        blob = json.loads((ROOT / "terminology" / ("%s.json" % slug)).read_text())
        of = _phc(question).get("unit_of")
        if of and of in chosen:
            unit = chosen[of].get("unit")
            if unit:
                return unit
        code = sorted(blob["concepts"])[0]
        chosen[question["link_id"]] = dict(blob["concepts"][code])
        return code
    return pick


def both(shape, db_dir):
    """One kernel of each language on the same declarations and the same shape.

    PHC_BACKEND is set per launch rather than for the process, because this is
    the one check that wants both at once and scripts/backend.py reads the
    environment when it is asked.
    """
    started = {}
    for name in (backend.PYTHON, backend.GO):
        os.environ[backend.ENV] = name
        started[name] = backend.launch(
            os.path.join(db_dir, "%s-%s.sqlite3" % (name, shape)),
            bundle="phc", facility=shape)
    os.environ.pop(backend.ENV, None)
    return started


# --------------------------------------------------------------------------
# the write path: one scenario, both engines, diffed step by step
# --------------------------------------------------------------------------
#
# WHY A WALK AND NOT A SET OF ASSERTIONS
# --------------------------------------
# Every guard property is about a SEQUENCE: a proposal is judged again at
# confirm, a confirmed proposal cannot be confirmed twice, a denial is on the
# trail before the write. None of those is a fact about one response. So a
# scenario is a recorded walk — a label, a status and a body per step — run
# against each engine on its own database, and the two recordings are diffed.
# Nothing about either shape is written here, which is the rule this file was
# built on: a literal would pass while both engines drifted from each other.
#
# WHAT IS NORMALISED, AND WHY THAT IS NOT A LITERAL
# -------------------------------------------------
# Two kernels on two databases mint their own ids and stamp their own clocks,
# so `enc-6f2a...` and `2026-10-31T17:04:11Z` cannot be equal and must not be
# compared. They are replaced by a marker that says WHICH volatile thing was
# there, so a missing id and a present one still differ. Nothing else is
# touched: a denial sentence, an outcome, a flag, a station, a status code and
# every clinical value are compared as they arrived.

VOLATILE_KEYS = ("id", "thread", "encounter", "token", "proposal",
                 "proposal_id", "at", "created_at", "created_date",
                 "decided_at", "opened_at", "directory_synced")
# An id this store mints: a short prefix, a hyphen and twelve hex characters.
ID_SHAPE = re.compile(r"\b[a-z_]{3,6}-[0-9a-f]{12}\b")
# And the seed's own, which is a serial rather than random.
SEED_SHAPE = re.compile(r"\bseed-[0-9]{4}\b")
STAMP_SHAPE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b")


def normalise(value):
    if isinstance(value, dict):
        out = {}
        for key, inner in value.items():
            if key in VOLATILE_KEYS:
                out[key] = "<%s>" % key if inner is not None else None
            else:
                out[key] = normalise(inner)
        return out
    if isinstance(value, list):
        return [normalise(item) for item in value]
    if isinstance(value, str):
        value = ID_SHAPE.sub("<id>", value)
        value = SEED_SHAPE.sub("<id>", value)
        return STAMP_SHAPE.sub("<at>", value)
    return value


class Walk:
    """One engine, one thread, and a recording of everything it answered."""

    def __init__(self, base):
        self.base = base
        self.steps = []
        self.thread = None
        self.proposal = None

    def _record(self, label, status, body):
        self.steps.append((label, status, normalise(body)))
        return status, body

    def headers(self, role, actor=None):
        sent = {"X-PHC-Role": role}
        # A fixed actor per role rather than the kernel's own default, which
        # is "user:<role>" and identical in both engines anyway. Fixed so the
        # separation-of-duties predicate has a stable person to be about.
        sent["X-PHC-Actor"] = actor or ("user:%s" % role)
        return sent

    def open(self, label="open a thread", role="frontdesk"):
        status, body = call(self.base, PREFIX + "/threads", method="POST",
                            headers=self.headers(role), body={})
        if status == 200:
            self.thread = body["id"]
        return self._record(label, status, body)

    def panel(self, label, role="demo"):
        status, body = call(self.base, PREFIX + "/threads/" + self.thread,
                            headers=self.headers(role))
        return self._record(label, status, body)

    def commit(self, label, op, payload, role, *, confirmed=False, extra=None):
        body = dict(extra or {}, thread=self.thread, payload=payload)
        if confirmed:
            body["confirmed"] = True
        status, answer = call(
            self.base, PREFIX + "/operations/%s/commit" % op, method="POST",
            headers=self.headers(role), body=body)
        return self._record(label, status, answer)

    def propose(self, label, op, payload, role):
        status, answer = call(
            self.base, PREFIX + "/operations/%s/propose" % op, method="POST",
            headers=self.headers(role), body={"thread": self.thread,
                                              "payload": payload})
        if status == 200:
            self.proposal = answer["proposal_id"]
        return self._record(label, status, answer)

    def read_proposal(self, label):
        status, answer = call(self.base, PREFIX + "/proposals/" + self.proposal)
        return self._record(label, status, answer)

    def confirm(self, label, role, payload=None):
        body = {}
        if payload is not None:
            body["payload"] = payload
        status, answer = call(
            self.base, PREFIX + "/proposals/%s/confirm" % self.proposal,
            method="POST", headers=self.headers(role), body=body)
        return self._record(label, status, answer)

    def reject(self, label, role, reason=""):
        status, answer = call(
            self.base, PREFIX + "/proposals/%s/reject" % self.proposal,
            method="POST", headers=self.headers(role),
            body={"reason": reason})
        return self._record(label, status, answer)


def registered(walk, codes):
    """A thread with a patient on it, which is what every other property
    needs: almost every operation's first precondition is `registered`."""
    walk.open()
    walk.commit("register a patient", "phc.op.patient-register",
                filled("phc.schema.register-v1", codes), "frontdesk")


# Each scenario is a function of (walk, codes). It makes calls; the walk
# records them; compare() diffs the two recordings. A scenario returns the
# property it is about, as a sentence, for the output.

def s_seven_steps(walk, codes):
    """A whole write, and what it moved: the flags, the station and the line."""
    registered(walk, codes)
    walk.panel("the panel after registration")
    walk.commit("record vitals", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes, every=True), "nurse")
    walk.panel("the panel after vitals")
    walk.commit("record vitals again", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes), "nurse")
    walk.panel("the panel after the refused repeat")
    return ("a write moves the line, and the same write twice is refused the "
            "second time")


def s_denials_are_audited(walk, codes):
    """Every decision is audited, denials included. An audit line that only
    appears when a write succeeded is a log of what worked."""
    walk.open()
    walk.commit("commit with no capability", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes), "frontdesk")
    walk.propose("propose before the precondition holds", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    walk.commit("commit an invalid payload", "phc.op.patient-register",
                {"name": "only a name"}, "frontdesk")
    walk.commit("commit an operation this workflow never draws",
                "phc.op.household-visit",
                filled("phc.schema.household-visit-v1", codes), "demo")
    walk.panel("the trail after four refusals")
    return "a refusal is audited on both surfaces, and writes nothing"


# The one scenario that is ALL refusals on purpose, so the "this proves
# something" property below is inverted for it: every call must have been
# refused and the trail must carry every refusal.
s_denials_are_audited.refusals_only = True


def s_machine_writes_are_proposals(walk, codes):
    """A machine surface gets propose_* only: there is no tool that commits."""
    registered(walk, codes)
    walk.propose("propose vitals from the machine surface", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    walk.read_proposal("read the proposal back")
    walk.panel("the panel while the proposal is pending")
    return "a write from the machine surface is a proposal and no row"


def s_judged_again_at_confirm(walk, codes):
    """The property a queue or a delay would otherwise break."""
    registered(walk, codes)
    walk.propose("propose vitals", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    walk.commit("somebody else records the vitals first", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes), "nurse")
    walk.confirm("confirm the proposal now the precondition has gone", "nurse")
    walk.read_proposal("the proposal after the refused confirm")
    walk.panel("the panel after the refused confirm")
    return "a proposal is judged again at confirm, not when it was made"


def s_confirmed_once(walk, codes):
    registered(walk, codes)
    walk.propose("propose vitals", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    walk.confirm("confirm it", "nurse")
    walk.confirm("confirm it again", "nurse")
    walk.panel("the panel after one confirm and one replay")
    return "one proposal writes one row, and a replay writes none"


def s_edited_at_confirm(walk, codes):
    """The payload as the person edited it, re-validated."""
    registered(walk, codes)
    walk.propose("propose vitals", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    edited = dict(filled("phc.schema.vitals-v1", codes), systolic=400)
    walk.confirm("confirm with an edit that is out of range", "nurse", edited)
    walk.confirm("confirm with an edit that is in range", "nurse",
                 dict(filled("phc.schema.vitals-v1", codes), systolic=118))
    walk.panel("the panel after the edited confirm")
    return "a confirm validates the payload as the person edited it"


def s_capability_is_enforced_not_hidden(walk, codes):
    """A screen not offering something is not a refusal."""
    registered(walk, codes)
    walk.panel("what a clerk is offered", "frontdesk")
    walk.panel("what a nurse is offered", "nurse")
    walk.commit("the clerk taps the nurse's action anyway", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes), "frontdesk")
    walk.panel("the panel after the refused tap")
    return "a capability is enforced, not hidden"


def s_irreversible(walk, codes):
    """An irreversible operation needs an explicit confirm from a person, and
    a machine caller asserting confirmation gets nowhere."""
    registered(walk, codes)
    # every=True so the number is actually answered: without it the link
    # writes no abha_number, `abha.linked` stays false and the scenario proves
    # the refusals without proving the write.
    payload = filled("phc.schema.abha-link-v1", codes, every=True)
    walk.propose("an agent proposes an irreversible write", "phc.op.abha-link",
                 payload, "frontdesk")
    walk.commit("a person commits it with no confirm", "phc.op.abha-link",
                payload, "frontdesk")
    walk.commit("a person commits it with the confirm", "phc.op.abha-link",
                payload, "frontdesk", confirmed=True)
    walk.panel("the panel after the irreversible write")
    return ("an irreversible write needs a person and an explicit confirm, "
            "and cannot be proposed at all")


def s_the_kernel_names_the_surface(walk, codes):
    """A body claiming `surface: voice` is recorded as rendered."""
    registered(walk, codes)
    walk.commit("commit claiming a surface in the body", "phc.op.vitals-record",
                filled("phc.schema.vitals-v1", codes), "nurse",
                extra={"surface": "voice", "actor": "somebody else"})
    walk.panel("the trail after a body that claimed a surface")
    return "the kernel names the surface, never the caller"


def s_reject(walk, codes):
    registered(walk, codes)
    walk.propose("propose vitals", "phc.op.vitals-record",
                 filled("phc.schema.vitals-v1", codes), "nurse")
    walk.reject("reject it", "nurse", reason="not this patient")
    walk.confirm("confirm the rejected proposal", "nurse")
    walk.panel("the panel after a rejection")
    return "a refusal stays on the record and cannot be confirmed afterwards"


def s_a_plugin_that_is_off(walk, codes):
    """A plugin that is off is a capability the caller does not hold, and the
    denial names both. The shape is the only thing that differs between these
    three runs, so this is also the proof that the shape reached the guard."""
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    walk.commit("order a laboratory test", "phc.op.lab-order",
                filled("phc.schema.lab-order-v1", codes), "demo")
    walk.panel("the panel after the consultation")
    return "a plugin this centre does not run is a capability nobody holds"


def s_repeating_groups_fan_out(walk, codes):
    """One payload, several rows, and the row number in every refusal."""
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    good = filled("phc.schema.rx-v1", codes)
    two = {"medications": [dict(good["medications"][0]),
                           dict(good["medications"][0], dose=2)]}
    walk.commit("prescribe two medicines", "phc.op.rx-prescribe", two, "demo")
    walk.panel("the panel after a prescription of two")
    broken = {"medications": [dict(good["medications"][0]),
                              {"dose": 1, "nonsense": "x"}]}
    walk.commit("prescribe with the second row broken", "phc.op.rx-prescribe",
                broken, "demo")
    walk.panel("the panel after a broken second row")
    return "a repeating group is validated per row and writes one row per row"


def s_a_code_outside_its_value_set(walk, codes):
    """A coding that cannot be constructed unvalidated: the terminology half
    of guard step 1."""
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    good = filled("phc.schema.rx-v1", codes)
    bad = {"medications": [dict(good["medications"][0], drug="999999999")]}
    walk.commit("prescribe a drug code no value set holds", "phc.op.rx-prescribe",
                bad, "demo")
    walk.panel("the panel after an unbound code")
    return "an answer outside its value set is refused before anything is written"


SCENARIOS = (
    s_seven_steps,
    s_denials_are_audited,
    s_machine_writes_are_proposals,
    s_judged_again_at_confirm,
    s_confirmed_once,
    s_edited_at_confirm,
    s_capability_is_enforced_not_hidden,
    s_irreversible,
    s_the_kernel_names_the_surface,
    s_reject,
    s_a_plugin_that_is_off,
    s_repeating_groups_fan_out,
    s_a_code_outside_its_value_set,
)


def write_path(shape, python, go):
    """Every scenario against both engines, diffed step by step."""
    for scenario in SCENARIOS:
        walks = {}
        for name, base in (("python", python), ("go", go)):
            walk = Walk(base)
            about = scenario(walk, coder())
            walks[name] = walk
        py, gone = walks["python"], walks["go"]
        assert len(py.steps) == len(gone.steps), (
            "%s: %s recorded %d steps and %s recorded %d"
            % (shape, "python", len(py.steps), "go", len(gone.steps)))
        for (label, status, body), (_, go_status, go_body) in zip(py.steps, gone.steps):
            assert status == go_status, (
                "%s / %s / %s: python answered %s and go answered %s\n"
                "python: %s\ngo:     %s"
                % (shape, scenario.__name__, label, status, go_status,
                   json.dumps(body, sort_keys=True)[:600],
                   json.dumps(go_body, sort_keys=True)[:600]))
            assert body == go_body, (
                "%s / %s / %s: the two engines disagree\npython: %s\ngo:     %s"
                % (shape, scenario.__name__, label,
                   json.dumps(body, sort_keys=True),
                   json.dumps(go_body, sort_keys=True)))
        ok("%s: %s, over %d steps, identically in both engines"
           % (shape, about, len(py.steps)))
        properties(shape, scenario, py)


def properties(shape, scenario, walk):
    """The handful of facts that are properties rather than comparisons.

    These are here because two engines can agree and still both be wrong:
    comparing a denial sentence proves they match, not that it is a denial, or
    that it kept the raw precondition out of a clerk's way. Each one below is
    a property of the recording rather than a literal taken off either engine.
    """
    bodies = [body for _, _, body in walk.steps]
    statuses = [status for _, status, _ in walk.steps]

    # A denial message never echoes the raw precondition. The literals come
    # from the compiled catalogue, so this grows when a bundle does.
    #
    # Only the literals that CARRY something the sentence must drop: the "not
    # " and "actor of " prefixes and the dotted flag spelling. A precondition
    # that is one bare word ("registered") is not distinguishable from the
    # word a correct sentence uses ("Requires registered."), which is also why
    # catalogue/tests/test_guard.py's own case list is made of the punctuated
    # ones. Checking the bare words too would fail on the correct answer.
    raw = set()
    for op in json.loads((ROOT / "catalogue" / "catalogue.json").read_text())["operations"].values():
        for pre in op.get("preconditions") or []:
            if pre.startswith("not ") or "actor of " in pre or "." in pre:
                raw.add(pre)
    assert raw, "no punctuated precondition in the catalogue: this proves nothing"
    sentences = [body["detail"] for status, body in zip(statuses, bodies)
                 if status == 422 and "detail" in body]
    for sentence in sentences:
        for pre in raw:
            assert pre not in sentence, (
                "%s / %s: a denial echoed the raw precondition %r: %r"
                % (shape, scenario.__name__, pre, sentence))

    # Every audit row names a surface the kernel knows, whatever a body
    # claimed. There is no third surface and a caller cannot add one.
    panels = [body for body in bodies if isinstance(body, dict) and "audit" in body]
    for panel in panels:
        for row in panel["audit"]:
            assert row["surface"] in ("rendered", "mcp"), row

    # A pending proposal has written nothing: its operation's own emitted
    # flags are absent while it waits. Read off the catalogue rather than
    # named here.
    atoms = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())["operations"]
    for panel in panels:
        # Only when nothing ELSE performed that operation on this thread. One
        # scenario proposes a write and then has somebody record the same
        # thing directly, which is the whole point of it: the flag is then
        # raised by the commit and the proposal is still pending and still has
        # written nothing. kernel/state.PERFORMED is the two outcomes that
        # mean the work was done, read off the trail rather than named here.
        done = {row["operation"] for row in panel["audit"]
                if row["outcome"] in ("allowed", "confirmed")}
        for proposal in panel["proposals"]:
            if proposal["status"] != "pending" or proposal["operation"] in done:
                continue
            for flag in atoms[proposal["operation"]].get("emits") or []:
                assert flag not in panel["flags"], (
                    "%s: %s is pending, nothing performed it, and %s is "
                    "already raised" % (shape, proposal["operation"], flag))

    # One proposal, one confirmation. A replayed confirm must not put a second
    # "confirmed" line on the trail, because a second line would mean a second
    # write. Counted per proposal id rather than asserted as a number.
    for panel in panels:
        confirmed = {}
        for row in panel["audit"]:
            if row["outcome"] == "confirmed" and row["proposal"]:
                confirmed[row["proposal"]] = confirmed.get(row["proposal"], 0) + 1
        for which, times in confirmed.items():
            assert times == 1, (
                "%s / %s: a proposal was confirmed %d times"
                % (shape, scenario.__name__, times))

    # The scenario reached a real write. Two engines agreeing that everything
    # was refused is two engines agreeing about nothing, and the brief this
    # was grown under says so. So every scenario must contain at least one
    # allowed decision AND the recording must show something moved — except
    # the one whose subject IS the refusals, where the property is the
    # opposite and is checked as such.
    allowed = [body for status, body in zip(statuses, bodies)
               if status == 200 and isinstance(body, dict)
               and ("committed" in body or "proposal" in body)]
    if getattr(scenario, "refusals_only", False):
        assert not allowed, ("%s / %s: a call this scenario means to be "
                             "refused was allowed" % (shape, scenario.__name__))
        assert panels and panels[-1]["audit"], (
            "%s / %s: refusals were not audited" % (shape, scenario.__name__))
        for row in panels[-1]["audit"]:
            assert row["outcome"].startswith("denied: "), row
        assert not panels[-1]["flags"] and not panels[-1]["proposals"], (
            "%s / %s: a refused call left something behind: %s"
            % (shape, scenario.__name__, panels[-1]["flags"]))
    else:
        assert allowed, ("%s / %s: no call was allowed, so the comparison "
                         "compared two refusals" % (shape, scenario.__name__))
        assert any(panel["flags"] for panel in panels), (
            "%s / %s: no flag was ever raised, so nothing was written"
            % (shape, scenario.__name__))

    # Nothing is decided without a line on the trail. Once any decision has
    # been taken on this thread, allowed or refused, the audit carries it.
    decisions = sum(1 for status, body in zip(statuses, bodies)
                    if status in (200, 422) and isinstance(body, dict)
                    and ("committed" in body or "proposal" in body
                         or "detail" in body))
    if decisions and panels:
        assert panels[-1]["audit"], (
            "%s / %s: %d decisions were taken and the trail is empty"
            % (shape, scenario.__name__, decisions))


def main():
    # The Go binary is built once, loudly, before anything is compared: a
    # build failure here must not read as a route mismatch.
    binary = backend.build_go()
    ok("the Go backend builds: %s" % binary.relative_to(ROOT))

    with tempfile.TemporaryDirectory() as tmp:
        for shape in SHAPES:
            started = both(shape, tmp)
            try:
                compare(shape, started[backend.PYTHON].base,
                        started[backend.GO].base)
            finally:
                for server in started.values():
                    server.close()

    print("\nok   go parity: %d checks, two engines on one set of declarations"
          % checks)
    return 0


def compare(shape, python, go):
    # --- the root. The service name and the bundle are the same fact in both;
    # `routes` is NOT, and saying so is the point of comparing it separately.
    py_root = get(python, "/")
    go_root = get(go, "/")
    assert py_root["service"] == go_root["service"], (py_root, go_root)
    assert py_root["bundle"] == go_root["bundle"], (py_root, go_root)
    assert sorted(py_root) == sorted(go_root), (sorted(py_root), sorted(go_root))
    # The Python's list is FastAPI's own route table, so it also carries
    # /docs, /redoc and /openapi.json, which are FastAPI's and not the
    # kernel's. Every kernel route is held both ways: the Go names no route
    # the Python does not serve, AND the Go names every route the Python
    # serves. The second direction is the one that matters, because a route
    # added to api/main.py and not to the Go's table would otherwise be
    # invisible until somebody noticed it missing.
    kernel_routes = {r for r in go_root["routes"] if r != "/"}
    served_routes = {r for r in py_root["routes"]
                     if r.startswith("/api") and r != "/"}
    assert kernel_routes == served_routes, \
        "only on the Go: %s\nonly on the Python: %s" % (
            sorted(kernel_routes - served_routes),
            sorted(served_routes - kernel_routes))
    ok("%s: the root answers the same service and the same bundle, and the "
       "two engines name the same %d routes" % (shape, len(kernel_routes)))

    # --- the two served routes, under both prefixes, byte for byte.
    for route in SERVED:
        for prefix in ("/api", PREFIX):
            for spelling in (prefix + route, prefix + route + "/"):
                py = get(python, spelling)
                gone = get(go, spelling)
                assert py == gone, "%s\npython: %s\ngo:     %s" % (
                    spelling, json.dumps(py, sort_keys=True),
                    json.dumps(gone, sort_keys=True))
    ok("%s: /whoami and /facility are identical under both prefixes and both "
       "spellings of the trailing slash" % shape)

    # --- and the shape is really doing something, so the line above is not
    # two engines agreeing about nothing.
    facility = get(go, PREFIX + "/facility")
    assert facility["facility"] == shape, facility["facility"]
    withheld = sorted(facility["withheld"])
    if shape == "all-plugins":
        assert withheld == [], withheld
    else:
        assert withheld, "%s withholds nothing, so this shape proves nothing" % shape
        # The declared list stays whole. A facility declines a capability; it
        # does not delete one from the bundle.
        for cap in withheld:
            assert cap in facility["capabilities"], (cap, facility["capabilities"])
        assert set(withheld).isdisjoint(facility["user"]["capabilities"]), facility
    ok("%s: the Go kernel withholds %d capabilities it still declares, and the "
       "caller holds none of them" % (shape, len(withheld)))

    # --- the role header. There is no authentication in either engine and
    # this is what that means: a header picks who you are. Compared rather
    # than asserted, so neither engine can be the one that invented a model.
    for role in ("nurse", "mo", "frontdesk", "demo"):
        header = {"X-PHC-Role": role, "X-PHC-Actor": "user:someone"}
        py = get(python, PREFIX + "/whoami", header)
        gone = get(go, PREFIX + "/whoami", header)
        assert py == gone, (role, py, gone)
    unknown = {"X-PHC-Role": "surgeon"}
    get(python, PREFIX + "/whoami", unknown, expect=400)
    get(go, PREFIX + "/whoami", unknown, expect=400)
    ok("%s: X-PHC-Role narrows both engines identically for 4 roles, and both "
       "refuse a role the bundle does not declare with a 400" % shape)

    # --- the write path. The guard, over two real sockets, as a sequence
    # rather than as a set of shapes. See write_path.
    write_path(shape, python, go)

    # --- what Go does not serve yet, said out loud. 501 and not 404, so the
    # difference between "not ported" and "no such route" is on the wire.
    owed = []
    for route in sorted({r for r in get(python, "/")["routes"]
                         if r.startswith(PREFIX)}):
        # The templated ones cannot be asked without an id; the prefix is
        # enough, because the Go mounts a subtree.
        path = route.split("{")[0].rstrip("/")
        if path.endswith(tuple(SERVED)):
            continue
        if path[len(PREFIX):].startswith(WRITE_PATH):
            continue
        body = get(go, path, expect=501)
        assert "does not serve" in body["detail"], body
        owed.append(path[len(PREFIX):] or "/")
    ok("%s: %d routes the Python serves answer 501 on the Go with the slice "
       "that will bring them, rather than 404" % (shape, len(owed)))


if __name__ == "__main__":
    sys.exit(main())
