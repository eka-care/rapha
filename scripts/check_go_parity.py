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

import datetime
import functools
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
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
SERVED = ("/whoami", "/facility", "/catalogue", "/operations",
          "/questionnaires")
# The served read routes whose answer carries THIS STORE'S OWN TIMESTAMPS, so
# they cannot be compared byte for byte: two engines seed their own file a
# fraction of a second apart, and a queue row's opened_at is that fraction.
# Compared by stamped() below, through the same normalise() the write path's
# walk uses, which replaces a volatile value with a marker that says WHICH
# volatile thing was there rather than dropping it.
#
# /patients/search and /patients/pending are the LOCAL half of
# kernel/directory.py. There is no vendor behind that seam in Go and no
# credential is read, so the two engines are compared with
# PHC_DIRECTORY=absent (see both() below), which makes the Python take the
# same degraded path by the ordinary route. A facility WITH a credential
# configured would get suggestions from the Python and none from the Go: that
# gap is real, it is named here, and it is not closed by pretending this
# comparison covers it.
SERVED_STAMPED = ("/queue", "/patients/search", "/patients/pending")
# And the served read routes that need a path parameter, so they cannot join
# the loop above. /valuesets is compared by valuesets() below, over every slug
# a question in this bundle actually binds its answer to; /views and /subjects
# by the write path's own walk, which is the only place a thread and a subject
# exist to ask about.
SERVED_TEMPLATED = ("/valuesets", "/views", "/subjects")
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


def _outside_the_critical_band(question):
    """A number inside the physiological range and outside the critical one.

    Both bands are the question's own, so this moves when a declaration does,
    and the point of it is guard step 7: a critical but IN RANGE value commits
    and raises a stored flag. An out of range value never gets that far, the
    validator blocks it.
    """
    band, outer = _phc(question).get("critical"), _phc(question).get("range")
    if not band or not outer:
        return None
    middle = (band["high"] + outer["high"]) / 2
    if not (outer["low"] <= middle <= outer["high"]) or band["low"] <= middle <= band["high"]:
        return None
    return int(middle) if question["type"] == "integer" else round(middle, 1)


def critical(slug, codes):
    """A payload for this form with one answer critical and in range.

    Returns (payload, the flag that answer declares) or (None, None) for a
    form that declares no critical band at all, so a bundle without one skips
    the scenario rather than asserting against nothing.
    """
    payload = filled(slug, codes)
    for question in validate_walk(schema(slug)["questions"]):
        value = _outside_the_critical_band(question)
        flag = _phc(question).get("flags")
        if value is None or not flag or question["link_id"] not in payload:
            continue
        return dict(payload, **{question["link_id"]: value}), flag
    return None, None


def validate_walk(questions):
    for question in questions:
        yield question
        for inner in validate_walk(question.get("questions") or []):
            yield inner


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


def bound_slugs():
    """Every value set a question in this bundle binds its ANSWER to.

    Walked rather than listed, because a bound sub question of a repeating
    group is where the empty dropdown was, and because a value set added to a
    form has to arrive here without anybody editing this file.
    """
    found = set()
    cat = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
    for op_id in cat["manifest"]["operations"]:
        slug = cat["operations"][op_id].get("input")
        if not slug:
            continue
        for question in validate_walk(schema(slug)["questions"]):
            if question.get("answer_value_set"):
                found.add(question["answer_value_set"])
    assert found, "no question binds an answer, so this proves nothing"
    return sorted(found)


def _as_list(value):
    """kernel/views._as_list: a declaration may write one flag or a list of
    them and both mean the same thing."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


@functools.lru_cache(maxsize=None)
def declared():
    """The loaded bundle's own declarations, off the compiled artifact.

    catalogue.json's `views`, `metrics` and `workflows` are the LOADED
    bundle's (kernel/contracts.BUNDLE_KEYS); its top level `capabilities`,
    `bundles`, `states` and `operations` are the union over every bundle. Only
    the first three are read here, and nothing read here is an expectation:
    these are the declarations the two engines are both evaluating, used to
    decide what to ASK.
    """
    return json.loads((ROOT / "catalogue" / "catalogue.json").read_text())


def valuesets(shape, python, go):
    """GET /valuesets/{slug}, every bound slug, and what the parameters do.

    Nothing about any expansion is written here. The slugs come off the forms,
    and the queries come off whatever the first expansion answered, so a value
    set that is renamed or re-coded moves this check with it.
    """
    asked = 0
    for slug in bound_slugs():
        for spelling in ("", "/"):
            for tail in ("", "?limit=200", "?limit=1", "?limit=0",
                         "?limit=100000"):
                at = "%s/valuesets/%s%s%s" % (PREFIX, slug, spelling, tail)
                py = get(python, at)
                gone = get(go, at)
                assert py == gone, "%s\npython: %s\ngo:     %s" % (
                    at, json.dumps(py, sort_keys=True),
                    json.dumps(gone, sort_keys=True))
                asked += 1
        # The `q` parameter, which api/main.py says exists and nothing calls.
        # Asked with a word taken from this value set's own first display and
        # with one taken from its code, so the filter is exercised on both
        # halves of the Python's test rather than on a word typed here.
        body = get(python, "%s/valuesets/%s" % (PREFIX, slug))
        words = [body["concepts"][0]["display"].split()[0],
                 body["concepts"][0]["value"][:3], "nothing anybody declared"]
        for word in words:
            at = "%s/valuesets/%s?q=%s" % (PREFIX, slug,
                                           urllib.parse.quote(word))
            py = get(python, at)
            gone = get(go, at)
            assert py == gone, "%s\npython: %s\ngo:     %s" % (
                at, json.dumps(py, sort_keys=True),
                json.dumps(gone, sort_keys=True))
            asked += 1
    # A value set nothing caches. The Python raises UnboundCoding and answers
    # 404 with its own sentence, which interpolates the cache DIRECTORY, so
    # this also holds the two engines to the same path on the wire.
    missing = "%s/valuesets/%s" % (PREFIX, "-".join(sorted(bound_slugs()))[:60])
    py = call(python, missing)
    gone = call(go, missing)
    assert py == gone, "%s\npython: %s\ngo:     %s" % (missing, py, gone)
    assert py[0] == 404 and "is cached in" in py[1]["detail"], py
    # WHAT THE CEILING IS NOT PROVED BY THIS, SAID RATHER THAN IMPLIED.
    # api/main.py clamps the count at 200 and the renderer asks for 200.
    # Changing the Go's ceiling from 200 to 20 was applied as a mutation and
    # PASSED THE WHOLE GATE, because the largest value set in this tree holds
    # nine concepts, so 20 and 200 and 100000 are the same answer. It cannot
    # be made to fail without adding concepts to a value set, and nothing here
    # may do that: terminology/condition-code.json says "NOT A PRIMARY HEALTH
    # CENTRE DIAGNOSIS LIST" and awaits a named clinician. So the claim below
    # is the narrow one: an explicit limit is honoured, and a limit below one
    # is clamped up. The 200 ceiling is unobservable against these
    # declarations and is the thing that goes silently short the day a real
    # NRCeS release sits behind the same seam.
    biggest = max(len(get(python, "%s/valuesets/%s" % (PREFIX, slug))["concepts"])
                  for slug in bound_slugs())
    assert biggest < 200, biggest
    ok("%s: %d expansions of %d bound value sets are identical, an explicit "
       "limit and the unused q parameter included, and an uncached slug "
       "refuses the same way in both. The 200 ceiling is NOT proved: the "
       "largest value set here holds %d concepts"
       % (shape, asked + 1, len(bound_slugs()), biggest))


def forms(shape, python, go):
    """The forms, and the one property of that list that is not a comparison.

    GET /questionnaires/ is deliberately NOT narrowed by the caller's
    capabilities: a form is a bundle's declaration, and the renderer labels an
    OLD audit row with the questionnaire of whatever operation wrote it, so a
    narrowed list would strip the label off a card a colleague left behind.
    Held here by asking as a role that holds almost nothing and diffing that
    against the demo account's answer, in both engines.
    """
    served = {}
    for role in ("frontdesk", "demo"):
        header = {"X-PHC-Role": role}
        py = get(python, PREFIX + "/questionnaires", header)
        gone = get(go, PREFIX + "/questionnaires", header)
        assert py == gone, "%s\npython: %s\ngo:     %s" % (
            role, json.dumps(py, sort_keys=True),
            json.dumps(gone, sort_keys=True))
        served[role] = sorted(py["questionnaires"])
    assert served["frontdesk"] == served["demo"], served
    # And the caller really is narrower, so the line above is not two
    # identical callers agreeing.
    narrow = get(go, PREFIX + "/whoami", {"X-PHC-Role": "frontdesk"})
    whole = get(go, PREFIX + "/whoami", {"X-PHC-Role": "demo"})
    assert len(narrow["capabilities"]) < len(whole["capabilities"]), (narrow, whole)
    ok("%s: both engines serve the same %d forms to a clerk holding %d "
       "capabilities and to the demo account holding %d, because a form is a "
       "declaration and not a facility's choice"
       % (shape, len(served["demo"]), len(narrow["capabilities"]),
          len(whole["capabilities"])))


def stamped(shape, python, go):
    """The served reads whose answers carry this store's own timestamps.

    Compared through normalise(), which is the same treatment the write path's
    walk gives every recording: an id this store minted and a stamp this
    store's clock wrote are replaced by a marker naming which volatile thing
    was there, so a missing value and a present one still differ. Nothing else
    is touched — a name, a flag, a station, a badge, a count and a status code
    are compared as they arrived.
    """
    asked = 0
    for route in SERVED_STAMPED:
        for prefix in ("/api", PREFIX):
            for spelling in (prefix + route, prefix + route + "/"):
                py_status, py = call(python, spelling)
                go_status, gone = call(go, spelling)
                assert py_status == go_status, (spelling, py_status, go_status)
                assert normalise(py) == normalise(gone), "%s\npython: %s\ngo:     %s" % (
                    spelling, json.dumps(normalise(py), sort_keys=True),
                    json.dumps(normalise(gone), sort_keys=True))
                asked += 1
    # And the answers are not two empty screens agreeing. The seeded demo day
    # is the only reason either engine has a row here at all, so this is also
    # what fails if a store stops seeding.
    queue = get(python, PREFIX + "/queue")
    assert queue["rows"], "%s: the queue is empty, so this compared nothing" % shape
    assert any(row["station"] for row in queue["rows"]), queue["rows"]
    assert any(row["station"] is None for row in queue["rows"]), (
        "%s: no seeded thread has finished the line, so the trailing group "
        "proves nothing" % shape)
    register = get(python, PREFIX + "/patients/pending")
    assert register["count"], (
        "%s: no registered patient is unpublished, so the pending list "
        "compared nothing" % shape)
    ok("%s: %d stamped reads are identical once this store's own ids and "
       "clocks are marked: a queue of %d seeded threads and a register of %d "
       "patients no directory has seen" % (shape, asked, len(queue["rows"]),
                                           register["count"]))


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
            bundle="phc", facility=shape,
            # The kernel's own answer to having no vendor behind the patient
            # directory seam, asked for by name rather than relied on. The
            # Python reaches it anyway whenever EKA_ACCESS_TOKEN and
            # EKA_CLIENT_ID are unset, which is how every check in this
            # repository runs, and the Go has no connector at all. Saying it
            # here means the two engines are compared where they can honestly
            # be compared instead of agreeing by accident on a machine with no
            # credential and disagreeing on one that has.
            env={"PHC_DIRECTORY": "absent"})
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
# An id either engine mints: a short prefix, a hyphen, and EIGHT OR TWELVE
# hex characters.
#
# There are two shapes and this used to carry only one. A proposal id is
# `prop-` and twelve hex (kernel/proposals._id, uuid4().hex[:12]); every ROW
# id is the resource's first four letters and EIGHT (adapters/local/store.new_id,
# uuid4().hex[:8]). Only the twelve was written here, so a row id appearing as
# a list VALUE rather than under one of the volatile keys above was compared
# literally. Nothing reached it until a tasklist put a list of thread ids on
# the wire, and two stores mint their own, so the first check to get there
# failed for a reason that was not a difference in behaviour.
#
# The seed's own `enc-001` is deliberately NOT matched and stays compared as
# itself, because the seed DECLARES it and both engines must answer it;
# SEED_SHAPE below covers the serial row ids the seed mints.
ID_SHAPE = re.compile(r"\b[a-z_]{3,6}-(?:[0-9a-f]{12}|[0-9a-f]{8})\b")
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


def _sorted(value):
    """Every list in this value, sorted by what it holds. For a comparison
    that is about a SET of rows and not about their order; see Walk.read."""
    if isinstance(value, dict):
        return {k: _sorted(v) for k, v in value.items()}
    if isinstance(value, list):
        return sorted((_sorted(item) for item in value),
                      key=lambda item: json.dumps(item, sort_keys=True))
    return value


class Walk:
    """One engine, one thread, and a recording of everything it answered."""

    def __init__(self, base):
        self.base = base
        self.steps = []
        # The same recording with nothing normalised, for the properties()
        # pass. A property about a tasklist has to know WHICH thread was
        # listed, and `thread` is a volatile key: every id in `steps` is
        # already replaced by a marker, which is right for the diff and
        # useless for recomputing a predicate.
        self.raw = []
        # {view id: the status it answered}, filled by the views scenario, so
        # the properties pass can say no declared view was skipped without
        # parsing a step label.
        self.asked = {}
        self.thread = None
        self.proposal = None

    def _record(self, label, status, body):
        self.steps.append((label, status, normalise(body)))
        self.raw.append((label, status, body))
        return status, body

    def read(self, label, path, *, ordered=True):
        """One GET, recorded. For the read routes that need a thread or a
        subject to exist, which is why they cannot be asked in compare()'s
        stateless loop.

        WHAT `ordered=False` GIVES UP, AND WHY IT HAS TO
        ------------------------------------------------
        A queue is ordered `created_date DESC, id` and a tasklist's threads
        are sorted by id. By the time this scenario runs, every earlier
        scenario on this shape has left a thread on the same database, and all
        of them were opened inside the same second, so the tiebreak is the id
        — which each store MINTED FOR ITSELF. Two engines on two files
        therefore order the same rows differently for a reason that is not a
        difference in behaviour, and normalise() has already replaced those
        ids with a marker, so no amount of care in the diff can line them up.
        So the two recordings are compared as multisets at this one step, and
        what is given up is said rather than hidden: the ROW ORDER of a queue
        is not compared here. It IS compared, exactly, in stamped() — on a
        freshly seeded store, where every id is the seed's own declared one
        and the order is deterministic in both engines.
        """
        status, body = call(self.base, PREFIX + path, headers=self.headers("demo"))
        if ordered:
            return self._record(label, status, body)
        self.steps.append((label, status, _sorted(normalise(body))))
        self.raw.append((label, status, body))
        return status, body

    def peek(self, label, path):
        """One GET, kept for the properties pass and NOT compared.

        For a read whose very SUBJECT is an id this store minted: the panel
        behind each row of a queue. The two engines show the same rows in a
        different order, because the order is decided by ids they each minted
        for themselves, so "the third row's panel" is a different thread in
        each engine and comparing the two is comparing two different visits.
        The panels are still read, because the tasklist property below
        recomputes each declared predicate from the flags the kernel itself
        derived for EVERY thread, and that needs all of them. What is given up
        is said: these particular panels are not diffed. Every panel whose
        thread this walk opened itself IS diffed, by panel() above, and
        GET /threads/{id} is diffed on the seeded threads by every other
        scenario in this file.
        """
        status, body = call(self.base, PREFIX + path, headers=self.headers("demo"))
        self.raw.append((label, status, body))
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


def s_the_state_emit(walk, codes):
    """Guard step 7, which is the one step no other scenario reaches: a flag
    the store holds because no resource can answer it.

    Two kinds, both from the declarations. A critical but IN RANGE reading
    raises its question's own flag; an out of range one never gets here
    because the validator blocks it. And a consent is three stored flags the
    workflow composes a fourth from, which is what a consent has to be: the
    store can raise a flag and cannot lower one, and a consent that cannot be
    withdrawn is not a consent.
    """
    walk.open()
    consented = dict(filled("phc.schema.register-v1", codes),
                     capture_consent=True)
    walk.commit("register with the consent read out at the desk",
                "phc.op.patient-register", consented, "frontdesk")
    walk.panel("the panel once the patient has consented")
    payload, flag = critical("phc.schema.vitals-v1", codes)
    assert payload and flag, ("no question in this bundle declares a critical "
                              "band with a flag, so this scenario proves nothing")
    walk.commit("record a critical but in-range reading", "phc.op.vitals-record",
                payload, "nurse")
    walk.panel("the panel after a critical reading")
    walk.commit("the doctor stops the recording", "phc.op.capture-withdraw",
                filled("phc.schema.capture-withdraw-v1", codes), "demo")
    walk.panel("the panel after the consent was withdrawn")
    return ("a stored flag is raised by the answer that declares it, and a "
            "withdrawn consent lowers a flag the store cannot lower")


def a_row_group(slug):
    """(the group's link_id, its sub questions) for the first repeating group
    this form declares, or (None, None).

    Derived, so the scenarios below name no field: a form that renames its
    group or reorders its questions moves them with it.
    """
    for question in validate_walk(schema(slug)["questions"]):
        if question.get("type") == "group" and question.get("repeats"):
            return question["link_id"], list(validate_walk(question["questions"]))
    return None, None


def q_of(subs, slug):
    """The sub question that binds `slug`, which coder() needs so that a unit
    answer can follow the analyte it is the unit of."""
    return next(q for q in subs if q.get("answer_value_set") == slug)


def s_a_row_is_addressed_by_number(walk, codes):
    """Row addressing, and the four shapes it refuses.

    The row number has to be in every sentence, because "medications is
    invalid" does not tell a prescriber which line to fix. And a sub
    question's link_id arriving at the TOP level is an unknown key rather
    than an answer for row zero: a renderer that sent it has lost the row it
    belonged to, and folding it in would put a dose on the wrong medicine.
    """
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    slug, op = "phc.schema.rx-v1", "phc.op.rx-prescribe"
    group, subs = a_row_group(slug)
    assert group and subs, "%s declares no repeating group" % slug
    good = filled(slug, codes)
    row = dict(good[group][0])
    first = subs[0]["link_id"]

    walk.commit("a row field sent at the top level instead of in its row", op,
                dict(good, **{first: row[first]}), "demo")
    walk.commit("the group answered with one row rather than a list of rows",
                op, {group: row}, "demo")
    walk.commit("a row that is a single value and not a set of answers", op,
                {group: [row, row[first]]}, "demo")
    walk.commit("three rows, the second missing a required answer and the "
                "third carrying one the form never asked", op,
                {group: [row,
                         {k: v for k, v in row.items() if k != first},
                         dict(row, **{"%s_nobody_declared" % group: "x"})]},
                "demo")
    walk.panel("the panel after four refusals addressed by row")
    walk.commit("two rows, both whole", op, {group: [row, dict(row)]}, "demo")
    walk.panel("the panel after a prescription of two")
    return ("a row is addressed by number, a row field with no row is refused "
            "rather than folded into the first row, and every sentence says "
            "which row")


def s_a_bound_choice_is_constrained_per_row(walk, codes):
    """The third binding form, in the SECOND row.

    s_a_code_outside_its_value_set already breaks row zero. This breaks a
    later row, which is the case a per-question check would pass: the first
    row is legal and the refusal has to name the second.
    """
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    slug, op = "phc.schema.rx-v1", "phc.op.rx-prescribe"
    group, subs = a_row_group(slug)
    bound = next(q for q in subs if q.get("answer_value_set"))
    # A code from ANOTHER value set this form binds, so it is a real code and
    # the only thing wrong with it is which list it is on. Never a literal.
    elsewhere = next(q["answer_value_set"] for q in subs
                     if q.get("answer_value_set")
                     and q["answer_value_set"] != bound["answer_value_set"])
    good = filled(slug, codes)
    row = dict(good[group][0])
    wrong = dict(row, **{bound["link_id"]: codes(elsewhere, q_of(subs, elsewhere))})
    walk.commit("two rows, the second naming a code from the wrong value set",
                op, {group: [row, wrong]}, "demo")
    walk.panel("the panel after a code from the wrong list")
    walk.commit("two rows, both coded from the lists they bind", op,
                {group: [row, dict(row)]}, "demo")
    walk.panel("the panel after two coded rows")
    return "a bound choice is constrained in every row, not only the first"


# --------------------------------------------------------------------------
# the declared views, the queue, the metrics, the spine
# --------------------------------------------------------------------------
#
# These are reads, so they could in principle have joined compare()'s
# stateless loop. They are a walk instead because the interesting answers are
# the ones that CHANGE: a queue is what the writes above it put there, a
# tasklist's predicate is about threads a write created, a dashboard counts
# them, and a summary and a spine need a thread and a subject that exist. A
# stateless pair of reads against two freshly seeded files would compare two
# demo days and nothing either engine did.

def s_the_views_see_what_the_write_did(walk, codes):
    """Every declared view, before and after a write, and the spine behind it.

    Which views are asked comes off the compiled catalogue, so a view a bundle
    adds is asked here without anybody editing this file, and a view whose
    capability this shape withholds is asked too: the 403 is an answer and is
    compared like any other.
    """
    walk.read("the queue, on the seeded demo day", "/queue", ordered=False)
    registered(walk, codes)
    # Named explicitly as well as by default, because api/main.py picks the
    # first queue view by sorting the ids and that choice is a behaviour.
    for vid, decl in sorted(declared()["views"].items()):
        if decl["kind"] == "queue":
            walk.read("the queue named outright: %s" % vid, "/queue?view=" + vid,
                      ordered=False)
    walk.read("the queue, with the thread this walk opened on it", "/queue",
              ordered=False)

    for vid, decl in sorted(declared()["views"].items()):
        path = "/views/%s" % vid
        if decl["kind"] == "summary":
            # A summary is a view OF a thread, so it needs one, and says so
            # rather than drawing an empty page.
            walk.read("%s with no thread named" % vid, path)
            path += "?thread=" + walk.thread
        # A queue and a tasklist both carry ids this store minted in a list
        # whose order those ids decide; see Walk.read.
        in_order = decl["kind"] not in ("queue", "tasklist")
        for spelling in (path, path.replace("?", "/?") if "?" in path else path + "/"):
            status, _ = walk.read("%s at %s" % (vid, spelling), spelling,
                                  ordered=in_order)
            walk.asked[vid] = status
    walk.read("a view no bundle declares", "/views/" + "-".join(sorted(declared()["views"]))[:60])

    # Every thread the queue shows, so the properties pass can recompute each
    # tasklist predicate from the flags the panels carry rather than from a
    # case named here.
    _, queue = walk.read("the queue once more, to walk its rows", "/queue",
                         ordered=False)
    for row in queue.get("rows") or []:
        walk.peek("the panel behind queue row %s" % row["thread"],
                  "/threads/" + row["thread"])

    # The spine: one subject, every visit. The subject id is the patient row
    # this walk's own registration created, which the panel carries under the
    # spine field's own resource. A bundle declaring no spine answers 404 and
    # that is compared too.
    _, panel = walk.read("the panel of the thread this walk registered",
                         "/threads/" + walk.thread)
    subject = (panel.get("subject") or {}).get("id")
    if subject:
        walk.read("the spine of the subject this walk registered", "/subjects/" + subject)
    walk.read("a subject nobody registered", "/subjects/nobody-of-that-name")
    return ("the declared views, the queue named and defaulted, the summary "
            "before and after a thread, the dashboard, the tasklist and the spine")


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
    s_a_row_is_addressed_by_number,
    s_a_bound_choice_is_constrained_per_row,
    s_the_state_emit,
    s_the_views_see_what_the_write_did,
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

    # ------------------------------------------------------------------
    # the declared views, when this walk read any
    # ------------------------------------------------------------------
    #
    # Comparisons prove the two engines answer the same thing. These prove the
    # thing they both answered is the thing the declaration asked for, which
    # is the half a diff cannot reach: two resolvers that both ignored a
    # view's window, or both let a declined visit onto "consent never asked",
    # would agree perfectly.
    seen = [(label, body) for label, status, body in walk.raw
            if status == 200 and isinstance(body, dict)
            and "view" in body and "generated_at" in body]
    if seen:
        decls, metrics = declared()["views"], declared()["metrics"]
        # Every thread panel this walk read, so a tasklist's predicate can be
        # recomputed from the flags the kernel itself derived.
        known = {body["id"]: set(body["flags"])
                 for _, status, body in walk.raw
                 if status == 200 and isinstance(body, dict)
                 and "line" in body and "flags" in body and "id" in body}
        trails = {body["id"]: body["audit"]
                  for _, status, body in walk.raw
                  if status == 200 and isinstance(body, dict)
                  and "line" in body and "audit" in body}
        queue_scopes = {d["scope"] for d in decls.values() if d["kind"] == "queue"}
        kinds = set()
        for label, body in seen:
            decl = decls[body["view"]]
            kinds.add(decl["kind"])

            if decl["kind"] == "dashboard":
                assert body["rows"], (
                    "%s / %s: a dashboard answered no metric at all" % (shape, label))
                for m in body["rows"]:
                    # THE VIEW'S WINDOW WINS over each metric's own. Without
                    # this a resolver reading each metric's declared window
                    # would put a week and a day side by side on one screen.
                    assert m["window"] == decl["window"], (
                        "%s / %s: %s answered window %r and the view declares %r"
                        % (shape, label, m["metric"], m["window"], decl["window"]))
                    if m["unit"] == "count":
                        assert m["value"] == float(m["numerator"]), m
                    elif not m["denominator"]:
                        # An empty denominator is zero and not an error: an
                        # empty week is a normal week at a health centre.
                        assert m["value"] == 0, m
                    elif m["unit"] == "percent":
                        assert m["value"] == round(
                            m["numerator"] / m["denominator"] * 100, 2), m
                # And the override is really exercised, so the line above is
                # not satisfied by a dashboard whose metrics all happen to
                # declare the view's own window.
                assert any(metrics[mid]["window"] != decl["window"]
                           for mid in decl["metrics"]), (
                    "%s: every metric on %s declares the view's own window, "
                    "so nothing is overridden" % (shape, body["view"]))

            elif decl["kind"] == "queue":
                for row in body["rows"]:
                    assert sorted(row["subject"]) == sorted(decl["columns"]), (
                        "%s / %s: a queue row carries %s and the view declares %s"
                        % (shape, label, sorted(row["subject"]), sorted(decl["columns"])))
                    for flag, style in row["badges"].items():
                        assert flag in row["flags"], (
                            "%s / %s: badge %r on a row that does not hold it"
                            % (shape, label, flag))
                        assert decl["badges"].get(flag) == style, (
                            "%s / %s: badge %r is %r and the view declares %r"
                            % (shape, label, flag, style, decl["badges"].get(flag)))
                keys = [str(g["key"]) for g in body["groups"]]
                if len(set(keys)) == len(keys):
                    # Every thread in exactly one group. Guarded, because a
                    # bundle naming one station at two steps gets two groups
                    # with the same key and the Python counts it twice.
                    assert sum(g["count"] for g in body["groups"]) == len(body["rows"]), (
                        "%s / %s: %d rows across groups totalling %d"
                        % (shape, label, len(body["rows"]),
                           sum(g["count"] for g in body["groups"])))

            elif decl["kind"] == "tasklist":
                assert len(body["rows"]) == len(decl["tasks"]), (shape, label)
                for row, task in zip(body["rows"], decl["tasks"]):
                    assert row["title"] == task["title"], (row, task)
                    # A real count, not a number beside an empty list.
                    assert row["count"] == len(row["threads"]), row
                    assert row["operation"] == task.get("operation"), (row, task)
                    want = _as_list(task["where"].get("flag"))
                    avoid = _as_list(task["where"].get("not"))
                    if decl["scope"] in queue_scopes:
                        assert set(row["threads"]) <= set(known), (
                            "%s / %s: %r lists a thread no queue showed"
                            % (shape, label, row["title"]))
                    # Recomputed from the flags the kernel derived, over every
                    # thread rather than over a case named here: that is what
                    # catches a `not` clause that only tests its first member.
                    expect = sorted(tid for tid, flags in known.items()
                                    if all(f in flags for f in want)
                                    and not any(f in flags for f in avoid))
                    assert sorted(t for t in row["threads"] if t in known) == expect, (
                        "%s / %s: %r listed %s and the flags say %s"
                        % (shape, label, row["title"],
                           sorted(t for t in row["threads"] if t in known), expect))

            elif decl["kind"] == "summary":
                for block in body["rows"]:
                    assert block["fields"] == (
                        decls[body["view"]]["sections"][body["rows"].index(block)]["fields"]), block
        # No declared view was skipped, and the only reason one is not read is
        # that this facility withholds the capability that opens it. A view
        # gated by a plugin this centre does not run answers 403 by design
        # (scripts/check_plugins.py owns that assertion), which is why the
        # dashboard is absent from `kinds` at consulting-room-only and present
        # at the other two shapes.
        for vid, status in walk.asked.items():
            assert status in (200, 403), (shape, vid, status)
            if status == 200:
                assert decls[vid]["kind"] in kinds, (shape, vid)
        assert set(walk.asked) == set(decls), (
            "%s: this walk asked for %s and the bundle declares %s"
            % (shape, sorted(walk.asked), sorted(decls)))
        openable = {d["kind"] for vid, d in decls.items() if walk.asked[vid] != 403}
        assert kinds == openable, (
            "%s: this walk read %s and this caller may open %s"
            % (shape, sorted(kinds), sorted(openable)))

        # ---- the spine, when this walk read one
        for _, status, body in walk.raw:
            if status != 200 or not isinstance(body, dict) or "encounters" not in body:
                continue
            assert body["encounters"], "%s: a subject with no visits at all" % shape
            opened = [v["opened_at"] for v in body["encounters"]]
            assert opened == sorted(opened, reverse=True), (
                "%s: a timeline is not newest first: %s" % (shape, opened))
            threads = [v["thread"] for v in body["encounters"]]
            assert len(threads) == len(set(threads)), threads
            for visit in body["encounters"]:
                if visit["thread"] not in known:
                    continue
                # One subject, every visit, and each visit is the same visit
                # the thread panel draws: the spine derives its flags and its
                # station the same way or it is a second opinion about the
                # same encounter.
                assert set(visit["flags"]) == known[visit["thread"]], visit
                did = [d["operation"] for d in visit["did"]]
                assert len(did) == len(set(did)), ("an operation twice", did)
                performed = {row["operation"] for row in trails[visit["thread"]]
                             if row["outcome"].startswith(
                                 ("committed", "confirmed", "allowed"))}
                assert set(did) == performed, (
                    "%s: a visit says it did %s and the trail says %s"
                    % (shape, sorted(did), sorted(performed)))

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


# --------------------------------------------------------------------------
# fill: the one half of this slice that is on no route
# --------------------------------------------------------------------------
#
# api/fill.py is reached through the scribe, and the scribe is G8, so the two
# engines' fill cannot be diffed over a socket the way everything else here is.
# It is diffed as a PAIR OF PROGRAMS instead: this file writes a file of
# inputs, each engine answers it, and the two answers are compared. Nothing
# about either answer is written down, which is the same rule the rest of this
# check is built on.
#
# The Go side is care_phc_mcp/fill/parity_test.go, a test that asserts nothing
# and exists only as the transport. Why a test and not a third command or a new
# route is in that file's own comment.
#
# RUN ONCE AND NOT PER SHAPE, SAID OUT LOUD
# -----------------------------------------
# fill takes no facility input. It reads the questionnaire an operation names
# and the offline terminology cache, and a facility's shape reaches neither, so
# three runs would be one run counted three times. The shape dependent half of
# this slice IS compared per shape: it is the validator, and it reaches the
# socket through the write path above.
#
# A HEARD VALUE IS AN INPUT AND AN INPUT MAY BE WRITTEN HERE
# ----------------------------------------------------------
# What a recogniser heard is not a declaration, so the phrases below are typed:
# "one forty", "haan", "15 December", "31 February". They are what somebody
# says, and no file in this repository declares them. What is NOT typed is any
# answer: which of them coerce accepts, what it becomes, and which ids owe a
# tick all come off the two engines. The legal values and the options a phrase
# is matched against are read off the forms and the value sets.

TODAY = "2026-09-16"


def heard(field):
    """Phrases to try against one field. Derived where a declaration has one
    (its own options, its own displays) and spoken where it does not."""
    tries = ["", "   ", "nothing anybody declared"]
    options = field.get("options") or []
    labels = field.get("labels") or {}
    if options:
        tries += [options[0], " %s " % options[-1]]
    for code in sorted(labels):
        if labels[code]:
            tries += [labels[code], "  %s  " % labels[code].upper()]
            break
    kind = field["type"]
    tries += {
        "integer": ["140", "140.5", 140, 140.0, "one forty"],
        "decimal": ["12.5", 12.5, "12", "twelve"],
        "quantity": ["12.5", 12.5, "12", "twelve"],
        "boolean": ["yes", "no", "haan", "nahi", "1", "0", "maybe", True, False],
        "date": ["today", "yesterday", "2026-08-01", "15 August", "August 15",
                 "15 December", "31 February", "32 August", "15 Smarch"],
        "dateTime": ["today", "2026-08-01", "15 August", "31 February"],
        "time": ["  09:00  ", 12],
        "string": ["  a phrase  ", 12],
        "text": ["  a phrase  ", 12],
        "url": ["  https://example.invalid/x  ", 12],
        "structured": [[{"a": 1}], [1], []],
    }.get(kind, ["  a phrase  "])
    return tries


def legal(field):
    """One phrase this field can hold, from its own declaration where it has
    one. Used to answer every question of a form at once."""
    options = field.get("options") or []
    if options:
        return options[0]
    return {"integer": "1", "decimal": "1.5", "quantity": "1.5",
            "boolean": "yes", "date": "today", "dateTime": "today",
            "time": "09:00", "structured": [{"a": 1}]}.get(
                field["type"], "a phrase")


def fill_cases():
    """The inputs both engines are asked, built from the forms on disk."""
    from api import fill as filler
    cat = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
    slugs = []
    for op_id in sorted(cat["manifest"]["operations"]):
        slug = cat["operations"][op_id].get("input")
        if slug and slug not in slugs:
            slugs.append(slug)
    cases = {"questionnaires": str(QUESTIONNAIRES),
             "terminology": str(ROOT / "terminology"),
             "today": TODAY, "flatten": slugs, "coerce": [], "drafts": []}
    for slug in slugs:
        fields = filler.flatten(schema(slug))
        for field in fields:
            for value in heard(field):
                cases["coerce"].append({"slug": slug,
                                        "link_id": field["link_id"],
                                        "value": value})
        # One draft per form: every answerable question answered, the row ones
        # addressed to row zero, a SECOND row numbered 7 by the extractor so
        # the renumbering has something to do, and the two shapes that must be
        # dropped rather than guessed at.
        answers, n = [], 0
        for field in fields:
            n += 1
            ident = field["link_id"]
            if field["row_of"]:
                ident = filler.row_id(field["row_of"], 0, field["link_id"])
            answers.append({"id": ident, "value": legal(field),
                            # Spread either side of api/fill.CAP, so the cap
                            # is exercised without this file naming it.
                            "confidence": round(0.5 + 0.05 * (n % 11), 2),
                            "evidence": "said %s" % field["link_id"]})
        for field in fields:
            if field["row_of"]:
                answers.append({"id": filler.row_id(field["row_of"], 7,
                                                    field["link_id"]),
                                "value": legal(field), "confidence": 0.61,
                                "evidence": "second %s" % field["link_id"]})
                # The row field with NO row number. Dropped, never folded into
                # row zero, which is the rule this whole slice turns on.
                answers.append({"id": field["link_id"], "value": legal(field),
                                "confidence": 0.95, "evidence": "rowless"})
            else:
                # And a top level field addressed into a group it is not in.
                answers.append({"id": filler.row_id("nobody_declared_this", 0,
                                                    field["link_id"]),
                                "value": legal(field), "confidence": 0.95,
                                "evidence": "wrong group"})
        cases["drafts"].append({"slug": slug, "operation": "x.op",
                                "kind": "whole", "instrument": "i",
                                "transcript": "a transcript",
                                "answers": answers})

        # And a second draft for a form with an enable_when, answering ONLY
        # the gated questions and not the ones they are gated on, so the rule
        # actually refuses something.
        #
        # This exists because of a mutation that did not fail. Breaking
        # fill.Enabled so a disabled answer is kept passed the whole gate on
        # its first pass: every draft above answers every question, so every
        # rule held and the deletion never ran. The declaration this now
        # reaches is phc.schema.lab-result-v1's `override_reason`, gated on
        # `value` existing, and it is found by walking rather than named here.
        gated = [f for f in fields if f["enable_when"]]
        gates = {r["question"] for f in gated for r in f["enable_when"]}
        if gated:
            cases["drafts"].append({
                "slug": slug, "operation": "x.op", "kind": "gated",
                "instrument": "i",
                "transcript": "a transcript",
                "answers": [{"id": f["link_id"], "value": legal(f),
                             "confidence": 0.7,
                             "evidence": "said %s" % f["link_id"]}
                            for f in fields
                            if f["link_id"] not in gates and not f["row_of"]]})
    assert cases["coerce"] and cases["drafts"], cases["flatten"]
    # The gate above really was reached, or the line it exists for proves
    # nothing: at least one form in this bundle declares an enable_when.
    assert any(one.get("kind") == "gated" for one in cases["drafts"]), \
        ("no question in this bundle declares enable_when, so fill's gate is "
         "unexercised and the mutation that found that hole would pass again")
    return cases


def python_fill(cases):
    from api import fill as filler
    today = datetime.date.fromisoformat(cases["today"])
    out = {"flatten": {}, "coerce": [], "drafts": []}
    for slug in cases["flatten"]:
        out["flatten"][slug] = filler.flatten(schema(slug))
    for one in cases["coerce"]:
        by = {f["link_id"]: f for f in filler.flatten(schema(one["slug"]))}
        held, value = filler.coerce(by[one["link_id"]], one["value"], today)
        out["coerce"].append({"ok": held, "value": value})
    for one in cases["drafts"]:
        answers = {a["id"]: {"value": a["value"],
                             "confidence": a["confidence"],
                             "evidence": a["evidence"]}
                   for a in one["answers"]}
        out["drafts"].append(filler.build_draft(
            one["operation"], schema(one["slug"]), answers, one["transcript"],
            instrument=one["instrument"], today=today))
    # Round tripped through JSON, because that is what the Go answer arrives
    # as and a tuple or a date would compare unequal for the wrong reason.
    return json.loads(json.dumps(out))


def go_fill(cases, tmp):
    cases_at = os.path.join(tmp, "fill-cases.json")
    answers_at = os.path.join(tmp, "fill-answers.json")
    with open(cases_at, "w") as f:
        json.dump(cases, f)
    done = subprocess.run(
        ["go", "test", "./fill/", "-run", "TestFillAnswersForTheParityCheck",
         "-count=1"],
        cwd=str(backend.GO_MODULE), capture_output=True, text=True,
        env=dict(os.environ, PHC_FILL_CASES=cases_at,
                 PHC_FILL_ANSWERS=answers_at))
    if done.returncode != 0 or not os.path.exists(answers_at):
        raise SystemExit("\nthe Go engine could not answer the fill cases:\n\n%s%s\n"
                         % (done.stdout[-4000:], done.stderr[-2000:]))
    with open(answers_at) as f:
        return json.load(f)


def fill_parity(tmp):
    # api/fill.TICK_TYPES, read rather than retyped: which answer types are
    # read back and ticked is the Python's declaration, and the Go is held to
    # it by the comparison below rather than by a list in this file.
    from api.fill import TICK_TYPES
    cases = fill_cases()
    py = python_fill(cases)
    gone = go_fill(cases, tmp)

    for slug in cases["flatten"]:
        assert py["flatten"][slug] == gone["flatten"][slug], (
            "%s: the two engines flatten it differently\npython: %s\ngo:     %s"
            % (slug, json.dumps(py["flatten"][slug], sort_keys=True),
               json.dumps(gone["flatten"][slug], sort_keys=True)))
    ok("fill: %d forms flatten identically, every bound choice carrying the "
       "codes and the displays its value set holds"
       % len(cases["flatten"]))

    for one, a, b in zip(cases["coerce"], py["coerce"], gone["coerce"]):
        assert a == b, ("coerce %s.%s of %r: python %s, go %s"
                        % (one["slug"], one["link_id"], one["value"], a, b))
    # And the phrases really did both things, so the line above is not two
    # engines agreeing that everything was refused.
    held = [a for a in py["coerce"] if a["ok"]]
    assert held and len(held) < len(py["coerce"]), len(held)
    ok("fill: %d heard phrases coerce identically in both engines, %d of them "
       "accepted and %d refused" % (len(py["coerce"]), len(held),
                                    len(py["coerce"]) - len(held)))

    for one, a, b in zip(cases["drafts"], py["drafts"], gone["drafts"]):
        assert a == b, ("the draft for %s differs\npython: %s\ngo:     %s"
                        % (one["slug"], json.dumps(a, sort_keys=True),
                           json.dumps(b, sort_keys=True)))

    # The two properties of a draft that are properties and not comparisons.
    # Two engines can agree and still both be wrong: comparing a `tick` list
    # proves they match, not that it holds a tick per row addressed id.
    ticked = rowed = 0
    for one, draft in zip(cases["drafts"], py["drafts"]):
        if not draft:
            continue
        owed = set(draft["tick"])
        # Which keys hold ROWS, read off the flattened form: a key is a
        # repeating group when some question says it is inside it. Not "every
        # value that is a list", which also catches a `structured` answer and
        # was the first spelling of this loop.
        groups = {f["row_of"] for f in py["flatten"][one["slug"]] if f["row_of"]}
        for ident, value in draft["values"].items():
            if ident not in groups or not isinstance(value, list):
                continue
            for index, row in enumerate(value):
                rowed += 1
                for link_id in row:
                    at = "%s[%d].%s" % (ident, index, link_id)
                    field = next(f for f in py["flatten"][one["slug"]]
                                 if f["link_id"] == link_id)
                    if field["type"] in TICK_TYPES:
                        assert at in owed, (
                            "%s: %s filled a %s and is owed no tick"
                            % (one["slug"], at, field["type"]))
                        ticked += 1
        # A row field answered with NO row number was dropped, and the drop is
        # visible: it is in `unfilled` and its value is in no row. Only for the
        # draft that answered everything; the gated one answers no row field at
        # all, so there is nothing for it to have dropped.
        if one["kind"] != "whole":
            continue
        for field in py["flatten"][one["slug"]]:
            if not field["row_of"]:
                continue
            assert field["link_id"] in draft["unfilled"], (
                "%s: %s was answered with no row and was not dropped"
                % (one["slug"], field["link_id"]))
            assert field["link_id"] not in draft["values"], draft["values"]
    assert ticked and rowed, (ticked, rowed)
    ok("fill: %d drafts are identical in both engines, and %d non text values "
       "across %d rows each come back owing a tick under their own row "
       "addressed id" % (len(cases["drafts"]), ticked, rowed))


def main():
    # The Go binary is built once, loudly, before anything is compared: a
    # build failure here must not read as a route mismatch.
    binary = backend.build_go()
    ok("the Go backend builds: %s" % binary.relative_to(ROOT))

    with tempfile.TemporaryDirectory() as tmp:
        # fill first, because it needs no server and a difference there is
        # cheaper to read than one found after three pairs of kernels have
        # been started.
        fill_parity(tmp)
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

    # --- the forms and the value sets behind their bound choices, which are
    # the rest of what a screen asks a clinician. See forms() and valuesets().
    forms(shape, python, go)
    valuesets(shape, python, go)
    stamped(shape, python, go)

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
        if path.endswith(tuple(SERVED) + SERVED_STAMPED + SERVED_TEMPLATED):
            continue
        if path[len(PREFIX):].startswith(WRITE_PATH):
            continue
        body = get(go, path, expect=501)
        assert "does not serve" in body["detail"], body
        owed.append(path[len(PREFIX):] or "/")
    ok("%s: %d routes the Python serves answer 501 on the Go with the slice "
       "that will bring them, rather than 404" % (shape, len(owed)))


# ---------------------------------------------------------------------------
# The mutation ledger for what G3 added: 15 applied, 14 caught
# ---------------------------------------------------------------------------
#
# Each one was applied to the GO side, proved applied (the file changed AND
# the replaced text was gone AND git agreed), run through the whole of
# scripts/check.sh, reverted, and the revert proved clean against git. The
# gate stops at the first failure, so "first" is the gate's own order. Every
# one that failed failed here, in "== the Go backend, beside the Python ==".
#
#  1. CompiledJSON serves catalogue.json's top level capabilities, bundles and
#     states -- the union over every bundle -- instead of the loaded bundle's
#     own.  -> GET /api/catalogue differs.
#  2. CompiledJSON serves every bundle's operations instead of the manifest's.
#     -> GET /api/catalogue differs.
#  3. /questionnaires narrowed by the caller's capabilities.
#     -> forms(), asking as `frontdesk`.
#  4. /questionnaires serves the parsed questions instead of the whole file.
#     -> GET /api/questionnaires differs.
#  5. The expansion's ceiling is 20 and not 200.  -> NOT CAUGHT, and it cannot
#     be: the largest value set in this tree holds nine concepts, so every
#     ceiling above nine is the same answer, and nothing here may add a
#     concept to a value set. Recorded in valuesets() rather than claimed.
#  6. The expansion ignores `q`.  -> valuesets(), the q taken off a display.
#  7. The expansion drops the `unit` a coded answer needs beside the code.
#     -> valuesets(), on lab-analyte.
#  8. The expansion's `q` filters the display only, never the code.
#     -> valuesets(), the q taken off a code.
#  9. The validator accepts a repeating group's sub question answered at the
#     TOP level, which is a renderer that lost the row it belonged to.
#     -> the write path, s_a_plugin_that_is_off's consultation: 200 and 422.
# 10. Every row refusal says row zero.
#     -> the write path, s_repeating_groups_fan_out's broken second row.
# 11. fill folds a row field with no row number into row zero.
#     -> fill_parity, the draft for phc.schema.abha-link-v1.
# 12. fill owes one tick per question rather than one per row addressed id.
#     -> fill_parity, the draft for phc.schema.consult-v1.
# 13. fill flattens the repeating group itself as an answerable field.
#     -> fill_parity, the flattening of phc.schema.consult-v1.
# 14. fill keeps an answer whose enable_when does not hold.
# 15. fill's enable_when refuses nothing at all.
#     -> both fill_parity, the draft for phc.schema.lab-result-v1 -- but only
#        after the check grew the case that reaches them. See below.
#
# THE HOLE THE MUTATIONS FOUND IN THIS CHECK
# ------------------------------------------
# 14 was applied first against the fill cases as they were originally built,
# and PASSED THE WHOLE GATE. Every draft answered every question of its form,
# so every enable_when rule held and the deletion never ran: the one branch of
# api/fill.enabled that does anything was unreachable. The fix is the second
# draft per form in fill_cases(), which answers only the GATED questions and
# not the ones they are gated on. 15 was then added as the broader form of the
# same mutation and both fail.
#
# One assertion was NARROWED rather than kept. valuesets() used to say the cap
# was included in what it compared. It is not and cannot be; the line now says
# which value set is the largest and that the ceiling is unproved.

if __name__ == "__main__":
    sys.exit(main())
