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

import base64
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
          "/questionnaires", "/roles")
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


@functools.lru_cache(maxsize=None)
def vocab(slug):
    """One cached value set, as it is written on disk.

    Read rather than asked of either engine, for the same reason the payloads
    are generated: a value set is a DECLARATION, and a check that learned an
    analyte's reported unit from one of the two engines would be comparing an
    engine against itself.
    """
    return json.loads((ROOT / "terminology" / ("%s.json" % slug)).read_text())


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
    # A whole number written as a float is NOT the same answer as the same
    # number written as an integer, and Python's own == says it is: 37 == 37.0
    # is True, and so is {"temperature": 37} == {"temperature": 37.0}. So two
    # engines putting `37` and `37.0` on the wire compared EQUAL here, and a
    # decimal answer is exactly where that happens -- Python keeps a float and
    # json.dumps writes "37.0", while Go's encoding/json writes float64(37) as
    # "37". That reaches the store as the text of a clinical value.
    #
    # Found by mutation: breaking the Go's decimal formatting survived the
    # whole gate. A float is therefore marked as one, so the two spellings are
    # two different recordings. A bool is checked first, because in Python it
    # is an int.
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return "<float %r>" % value
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

    def khoj(self, label, utterance, role, *, confidence=None, extra=None):
        """One sentence at the composer's endpoint, recorded.

        `backend` is pinned to the router on purpose and not left to the
        environment. agent/planner.py takes the llm branch the moment
        ANTHROPIC_API_KEY is set, and this check must compare two planners
        rather than one planner and one network call. The Go has no llm
        backend at all and says so; that gap is named in the port plan and is
        NOT closed by pretending this comparison covers it.

        The route's deprecated alias is NOT driven from here, and that is a
        constraint rather than a choice: scripts/check_khoj.py forbids any
        tracked source file outside the alias itself from naming that path in
        code, and this file is not on its list. What holds the alias is the
        route-table comparison above, which proves both engines name it, plus
        the fact that each engine serves it with the same handler as this
        route and so has no logic of its own on it. A live cross-engine
        comparison of that spelling would need that check's allowlist widened.
        """
        body = dict(extra or {}, thread=self.thread, utterance=utterance,
                    backend="router")
        if confidence is not None:
            body["confidence"] = confidence
        status, answer = call(self.base, PREFIX + "/khoj", method="POST",
                              headers=self.headers(role), body=body)
        if status == 200:
            allowed = [c["proposal_id"] for c in answer.get("proposals") or []
                       if c.get("proposal_id")]
            if allowed:
                self.proposal = allowed[0]
        # The answer carries the thread AS IT STANDS AFTER THE TURN, under the
        # key `thread`. Everywhere else in this file that key holds an id, so
        # it is in VOLATILE_KEYS and normalise() replaces whatever is under it
        # with a marker -- which here would throw away the entire panel and
        # compare nothing of it. A found-by-mutation hole: the Go answering
        # the panel from BEFORE the turn, so the new pending card was missing
        # from it, passed the whole gate.
        #
        # So the panel is recorded under a key the volatile list does not
        # swallow, and `raw` keeps the answer exactly as the engine wrote it,
        # because the properties pass below reads the real key.
        recorded = dict(answer)
        if isinstance(recorded.get("thread"), dict):
            recorded["thread_after_the_turn"] = recorded.pop("thread")
        self.steps.append((label, status, normalise(recorded)))
        self.raw.append((label, status, answer))
        return status, answer


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


def a_unit_rule():
    """(operation, form, the unit question, the question it is the unit of)
    for the first form in this bundle that declares `unit_of`, or four Nones.

    Derived, so nothing below names a form, a field, an analyte or a unit. The
    rule is "an answer declared `unit_of` another is the unit that other
    answer's concept is reported in", and the only honest place to prove it is
    on whichever question actually declares it.
    """
    cat = declared()
    for op_id in cat["manifest"]["operations"]:
        slug = cat["operations"][op_id].get("input")
        if not slug:
            continue
        questions = list(validate_walk(schema(slug)["questions"]))
        for question in questions:
            other = _phc(question).get("unit_of")
            if not other:
                continue
            peer = next((q for q in questions if q["link_id"] == other), None)
            if peer is not None and peer.get("answer_value_set"):
                return op_id, slug, question, peer
    return None, None, None, None


def s_a_unit_must_be_the_analytes_own(walk, codes):
    """The SECOND terminology rule, which the other scenarios never reach.

    s_a_code_outside_its_value_set breaks the first rule: a code no value set
    holds. This breaks the second with a code that IS in its value set and is
    simply not this analyte's unit, which is the case a per-answer check
    passes: both answers are legal on their own and the pair is nonsense. A
    haemoglobin of 12 is a normal haemoglobin in g/dL and a nonsense one in
    mg/dL, and nothing in a payload said which until this rule.
    """
    op, slug, unit_q, peer_q = a_unit_rule()
    assert op, ("no question in this bundle declares %s, so this scenario "
                "proves nothing" % "unit_of")
    registered(walk, codes)
    walk.commit("document a consultation", "phc.op.consult-document",
                filled("phc.schema.consult-v1", codes, every=True), "demo")
    walk.commit("order a laboratory test", "phc.op.lab-order",
                filled("phc.schema.lab-order-v1", codes), "demo")

    right = filled(slug, codes)
    picked = right[peer_q["link_id"]]
    reported = (vocab(peer_q["answer_value_set"])["concepts"]
                .get(str(picked), {}).get("unit"))
    assert reported, ("%s is cached with no unit, so the rule cannot be "
                      "broken deliberately" % picked)
    assert right[unit_q["link_id"]] == reported, (
        "the filler did not answer %s with the unit %s is reported in"
        % (unit_q["link_id"], picked))
    # A REAL unit, out of the same value set the unit question binds, whose
    # only fault is that it is not the one this analyte is reported in. Never
    # a literal, and never a code from somewhere else: that would fail the
    # FIRST rule and prove nothing new.
    elsewhere = [code for code in sorted(vocab(unit_q["answer_value_set"])["concepts"])
                 if code != reported]
    assert elsewhere, ("%s holds one unit, so a wrong one cannot be picked"
                       % unit_q["answer_value_set"])
    wrong = dict(right, **{unit_q["link_id"]: elsewhere[0]})

    # Whether this SHAPE runs the laboratory at all. Two of the three
    # withhold it, and there the two engines are compared refusing for a
    # capability rather than for a unit, which is a real comparison and is
    # NOT the unit rule. So the claim below says which of the two ran rather
    # than letting one stand in for the other.
    capability = declared()["operations"][op].get("capability")
    mine = get(walk.base, PREFIX + "/whoami",
               walk.headers("demo"))["capabilities"]
    held = capability in mine

    # The wrong one first: the operation declares `not lab.resulted`, so a
    # result that landed would close the door on the second attempt.
    _, refused = walk.commit(
        "enter the result in a real unit that is not that analyte's",
        op, wrong, "demo")
    walk.panel("the panel after a value and a unit that disagree")
    if held:
        # The refusal has to be ABOUT the pair, and every word checked for
        # here was derived above: the unit that was sent, the analyte that was
        # picked, and the unit that analyte is reported in. A refusal that
        # merely said "invalid" would pass a diff and tell a technician
        # nothing.
        said = json.dumps(refused)
        for word in (str(wrong[unit_q["link_id"]]), str(picked), str(reported)):
            assert word in said, (
                "the refusal does not name %r, so it does not say which of "
                "the two answers to correct: %s" % (word, said))
    walk.commit("enter the same result in the unit the analyte is reported in",
                op, right, "demo")
    walk.panel("the panel after a value and its own unit")
    if not held:
        return ("this shape runs no laboratory, so the unit rule is reached "
                "by neither engine and both refuse for the capability "
                "instead")
    return ("a value and its unit are one checked thing: a unit that is not "
            "the analyte's own is refused even though it is a real unit, and "
            "the refusal names both answers")


def s_the_state_emit(walk, codes):
    """Guard step 7, which is the one step no other scenario reaches: a flag
    the store holds because no resource can answer it.

    A critical but IN RANGE reading raises its question's own flag; an out of
    range one never gets here because the validator blocks it.

    There used to be a second kind in this scenario: a capture consent, which
    was three stored flags the workflow composed a fourth from. The owner
    removed consent in full on 4 November 2026 and this bundle now declares
    exactly one way to reach guard step 7, so that is what the walk does.
    """
    walk.open()
    walk.commit("register the patient", "phc.op.patient-register",
                filled("phc.schema.register-v1", codes), "frontdesk")
    walk.panel("the panel once the patient is registered")
    payload, flag = critical("phc.schema.vitals-v1", codes)
    assert payload and flag, ("no question in this bundle declares a critical "
                              "band with a flag, so this scenario proves nothing")
    walk.commit("record a critical but in-range reading", "phc.op.vitals-record",
                payload, "nurse")
    walk.panel("the panel after a critical reading")
    return "a stored flag is raised by the answer that declares it"


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
    subjects = []
    for row in queue.get("rows") or []:
        _, panel = walk.peek("the panel behind queue row %s" % row["thread"],
                             "/threads/" + row["thread"])
        # The spine field's own resource is the subject, and the panel merges
        # that row in, so its `id` is the continuing subject's. Collected from
        # the SEEDED threads as well as this walk's own, because a subject
        # with one visit proves nothing about a timeline: bundles/phc/seed.yaml
        # says so in its own words at the thread that declares
        # `same_patient_as`, and without that thread a join that had stopped
        # joining would look exactly the same.
        found = (panel.get("subject") or {}).get("id")
        if found and found not in subjects:
            subjects.append(found)
    for found in sorted(subjects):
        # The seed mints its row ids as serials in declaration order, so this
        # path is the same path in both engines and the two answers are
        # comparable. A subject this walk registered has a minted id instead,
        # which each engine chose for itself; that one is read for the
        # properties pass and not diffed, the way the panels above are.
        if SEED_SHAPE.fullmatch(found):
            walk.read("the spine of seeded subject %s" % found, "/subjects/" + found)
        else:
            walk.peek("the spine of subject %s" % found, "/subjects/" + found)

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


def s_the_calendar_with_women_in_it(walk, codes):
    """The facility calendar over a centre that has episodes, which the seeded
    day has none of.

    Without this the calendar was compared over an empty centre: every month
    the same nothing, so two engines that disagreed about every date rule would
    have agreed. Here are an open pregnancy, one whose first contact nobody
    made, a delivery (which ends the pregnancy and opens postnatal care in ONE
    commit, so an opening and an ending share an instant), and a miscarriage
    (which must leave no row at all). Then `?on=` is walked over the dates
    where the two engines' calendars are most likely to differ.
    """
    today = datetime.date.today()
    day = lambda n: (today - datetime.timedelta(days=n)).isoformat()

    def woman(label, lmp_days_ago):
        registered(walk, codes)
        walk.commit("%s: open a pregnancy" % label, "phc.op.pregnancy-open",
                    {"dating_basis": "last_menstrual_period",
                     "dating_date": day(lmp_days_ago)}, "anm")

    woman("an open pregnancy", 100)
    woman("a pregnancy nobody has seen for months", 190)
    woman("a delivery", 270)
    walk.commit("the delivery is recorded", "phc.op.delivery-record",
                {"delivery_date": day(3), "outcome": "live_birth"}, "anm")
    woman("a miscarriage", 100)
    walk.commit("the miscarriage is recorded", "phc.op.pregnancy-close",
                {"outcome": "miscarriage"}, "anm")
    walk.panel("the panel once the miscarriage is recorded")
    # An agreement between two refusals would prove nothing, so every write
    # above must have landed.
    writes = [status for label, status, _ in walk.raw if "pregnancy" in label
              or "recorded" in label]
    assert writes and all(status == 200 for status in writes), writes

    answers = {}
    first = today.replace(day=1)
    last = (first.replace(day=28) + datetime.timedelta(days=4))
    last = last - datetime.timedelta(days=last.day)
    for label, on in (("today, by saying nothing", None),
                      ("the first of this month", first.isoformat()),
                      ("the last of this month", last.isoformat()),
                      ("31 December", "2026-12-31"),
                      ("29 February in a leap year", "2028-02-29"),
                      ("29 February in a year that has none", "2027-02-29"),
                      ("a day that does not exist", "2026-02-30"),
                      ("a month that does not exist", "2026-13-01"),
                      ("an empty value", ""),
                      ("a timestamp", "2026-11-04T10:00:00Z"),
                      ("a compact date", "20261104")):
        path = "/views/phc.view.calendar"
        if on is not None:
            path += "?on=" + urllib.parse.quote(on)
        # Unordered, for the reason Walk.read gives: two contacts due on one
        # day come out in the order of ids each engine minted for itself.
        status, body = walk.read("the calendar on %s" % label, path, ordered=False)
        answers[label] = (status, body)
    # And the answers are the ones worth agreeing on: women are owed, nothing
    # is owed to the miscarriage, and a date that is not one is refused.
    status, body = answers["today, by saying nothing"]
    assert status == 200 and body["rows"], (status, body)
    assert {r["state"] for r in body["rows"]} >= {"missed"}, body["rows"]
    # The seeded day has a pregnant woman of its own; the women this walk
    # registered are the ones it named "parity".
    ours = {r["subject"] for r in body["rows"]
            if r["subject_row"].get("name") == "parity"}
    assert len(ours) == 3, \
        "three of this walk's women are owed and the fourth miscarried: %d" % len(ours)
    for label in ("a day that does not exist", "an empty value", "a timestamp"):
        assert answers[label][0] == 400, (label, answers[label])
    return ("the calendar over open, unseen, delivered and miscarried women, "
            "on month ends, leap days and impossible dates")


def s_the_planner_hears_and_proposes(walk, codes):
    """The ask-and-search turn: a sentence in, cards out, and no clinical row.

    Four shapes of utterance, because the router reads four and a comparison
    that only sent one would agree about a quarter of it: the blood pressure
    pair and a number beside a field name, a choice the words do not settle,
    a sentence that names no operation at all, and an empty one.

    What is compared is every card the turn built -- the payload it filled,
    the guard's verdict, the question it asked instead of guessing, the
    kernel's own ordering sentence and the reply composed from all of it. The
    cards are compared as the engines wrote them, so the ordering is part of
    the diff rather than something this file re-sorts away.
    """
    walk.open()
    # BEFORE the patient is registered, which is the only way an utterance
    # reaches the guard's PRECONDITION step at all. Payload validity is
    # checked before preconditions and the router fills thin payloads, so
    # every thin utterance is refused for the payload and never gets there. A
    # complete one on a thread nobody has registered yet is refused for the
    # precondition instead, which is what puts the precondition advice on a
    # card -- and that advice is keyed on the guard's machine-stable kind
    # rather than on its sentence, so nothing else in this file exercises it.
    walk.khoj("a complete sentence before the patient is registered",
              "bp 134 over 86, pulse 78, temp 37, sats 96, weight 61", "nurse")
    walk.commit("register a patient", "phc.op.patient-register",
                filled("phc.schema.register-v1", codes), "frontdesk")
    # The pair and a number beside a field name, which is the utterance the
    # composer's own check sends.
    walk.khoj("a sentence that fills a form", "bp 134 over 86, pulse 78, temp 37, sats 96, weight 61", "nurse")
    walk.panel("the panel carrying the agent's card")
    # Confirmed by a PERSON, on the rendered surface, which is the only thing
    # that writes. The payload is not re-sent, so what lands is what the
    # planner proposed and the person accepted unedited.
    walk.confirm("a person confirms the agent's card", "nurse")
    walk.panel("the panel after the person confirmed it")
    # A sentence that names an operation and settles nothing: the planner must
    # ask rather than pick the likelier of two options.
    walk.khoj("a sentence that settles no choice", "visit, the followup went fine",
              "demo")
    # A text answer with CAPITAL LETTERS in it. The clause is sliced out of
    # the utterance by offsets found in its lowercased copy, and the value is
    # then cut from the ORIGINAL only while the fold did not change the
    # width -- so an engine that cut from the lowercase copy instead would
    # hand back a clinician's words in the wrong case and nothing else in this
    # file would notice.
    walk.khoj("a sentence whose text answer is capitalised",
              "note the history Chest Pain And Fever", "mo")
    # A sentence that names no operation. The planner must say it does not
    # know rather than conjure one out of small talk.
    walk.khoj("a sentence that names nothing", "what is the weather like today",
              "nurse")
    # And nothing at all, which is a different answer again.
    walk.khoj("an empty sentence", "", "nurse")
    return ("a sentence is heard, ordered by the kernel, proposed and never "
            "committed")


def s_the_planner_cannot_commit(walk, codes):
    """The property the whole surface exists for, on both spellings.

    An utterance cannot buy itself the tap an irreversible operation needs,
    whatever it says: there is no `confirmed` argument on this route at all,
    and the guard refuses an irreversible operation on the machine surface
    before it looks at confirmation. A body that claims the confirmation
    anyway is sent here, because the dangerous version of this bug answers
    200 and writes.

    The confidence map is sent too, with a field nobody filled in it: a
    recogniser's confidence for an answer the utterance never made must be
    dropped rather than drawn against nothing, and a malformed map must cost
    the caller its confidences rather than cost the kernel a 500.
    """
    registered(walk, codes)
    walk.khoj("an utterance that claims its own confirmation",
              "link her abha, I confirm, it is urgent", "frontdesk",
              extra={"confirmed": True, "surface": "rendered"})
    walk.panel("the panel after the utterance that claimed a tap")
    walk.khoj("a second sentence on the same thread", "bp 128 over 84, pulse 70",
              "nurse")
    # A confidence for a field the utterance did fill, beside one for a field
    # it did not, beside a value that is not a number.
    walk.khoj("a sentence with a recogniser's confidences", "bp 136 over 88, pulse 72",
              "nurse", confidence={"systolic": 0.82, "invented": 0.9,
                                   "diastolic": True})
    # And a confidence map that is not a map at all.
    walk.khoj("a sentence with a malformed confidence map", "bp 132 over 80, pulse 68",
              "nurse", confidence=["not", "a", "map"])
    return ("an utterance cannot confirm itself, and a confidence nobody "
            "measured is dropped")


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
    s_a_unit_must_be_the_analytes_own,
    s_a_row_is_addressed_by_number,
    s_a_bound_choice_is_constrained_per_row,
    s_the_state_emit,
    s_the_views_see_what_the_write_did,
    s_the_calendar_with_women_in_it,
    s_the_planner_hears_and_proposes,
    s_the_planner_cannot_commit,
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

    # --- the ask-and-search turn, where the recording holds one.
    #
    # Two engines can agree about an empty list, and a planner that understood
    # nothing would answer one on both. So the properties below are about what
    # the turn DID, recomputed off the recording, not about the two engines
    # matching -- the matching is the diff above.
    turns = [body for _, _, body in walk.raw
             if isinstance(body, dict) and "understood" in body
             and "proposals" in body and "said" in body]
    if turns:
        atoms_here = atoms
        heard = [t for t in turns if t["understood"]]
        assert heard, (
            "%s / %s: not one utterance was understood, so the two engines "
            "agreed about nothing" % (shape, scenario.__name__))
        filled_cards = [c for t in heard for c in t["proposals"]
                        if c["payload"] and c["verdict"]["allowed"]]
        assert filled_cards, (
            "%s / %s: no utterance produced an allowed card with a payload in "
            "it, so this proves no planning" % (shape, scenario.__name__))
        for turn in turns:
            # The planner reports which backend planned, and it is the one
            # that was asked for. An engine that fell back silently would
            # report a planner that did not run.
            assert turn["backend"] == "router", turn["backend"]
            for card in turn["proposals"]:
                # A planner may answer the questions the questionnaire asks
                # and nothing else. override_reason waives the physiological
                # range check, so a planner that could answer it could waive
                # it, and no utterance may.
                assert "override_reason" not in card["payload"], card
                asks = {f["link_id"] for f
                        in atoms_here[card["operation"]].get("fields") or []}
                for answered in card["payload"]:
                    assert answered in asks, (
                        "%s / %s: the planner answered %r, which %s does not "
                        "declare" % (shape, scenario.__name__, answered,
                                     card["operation"]))
                # A machine surface gets proposals only, and the guard's rule
                # about irreversible work is what that means here: an
                # irreversible operation cannot come back allowed from this
                # route at all, whatever the sentence claimed.
                if card["verdict"]["allowed"]:
                    assert card["proposal_id"], card
                    assert atoms_here[card["operation"]]["irreversibility"] \
                        != "irreversible", (
                        "%s / %s: an utterance was allowed to propose the "
                        "irreversible %s" % (shape, scenario.__name__,
                                             card["operation"]))
                else:
                    # A refusal always says what to do next. A blank one is
                    # how an agent leaves a clinician with a dead card.
                    assert card["proposal_id"] is None, card
                    assert card["verdict"]["next"].strip(), card["verdict"]
                # A confidence is only ever for an answer that actually made
                # the payload, and is only ever a number.
                for link_id, value in card["confidence"].items():
                    assert link_id in card["payload"], (link_id, card)
                    assert isinstance(value, (int, float)) \
                        and not isinstance(value, bool), (link_id, value)
        # The advice on a refusal DISPATCHES rather than being one constant.
        #
        # Asserted on ONE recording and not on every one, and the reason is
        # the rule itself rather than convenience: the advice is keyed on the
        # guard's machine-stable precondition kind and otherwise on the SHAPE
        # of its reason, so two different payload denials are SUPPOSED to give
        # the same sentence. A scenario whose refusals are all payload
        # denials therefore has exactly one advice and is right to. Only the
        # recording that deliberately contains both a precondition refusal
        # (the complete utterance before the patient is registered) and a
        # payload one can hold this, and it is the reason that step is there.
        #
        # No literal from either engine: what is counted is how many distinct
        # sentences there are, never which.
        if scenario.__name__ == s_the_planner_hears_and_proposes.__name__:
            advice = {c["verdict"]["next"] for t in turns for c in t["proposals"]
                      if not c["verdict"]["allowed"]}
            assert len(advice) > 1, (
                "%s / %s: every refusal gave the same next step %r, so the "
                "precondition advice was never reached and the advice table "
                "proves no dispatch" % (shape, scenario.__name__, advice))

        # Nothing the turn proposed was written by the turn. Every row the
        # agent put on the trail is "proposed", and it is the agent that is
        # named as having proposed it, never the person.
        for turn in turns:
            for row in turn["thread"]["audit"]:
                if row["actor"].startswith("agent:"):
                    # "proposed", or "denied: <the guard's reason>". Never
                    # "allowed" and never "confirmed": those two are
                    # kernel/state.PERFORMED, and an agent reaching either of
                    # them is an agent that wrote a clinical row.
                    assert row["outcome"] == "proposed" \
                        or row["outcome"].startswith("denied"), row

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
        # "Left something behind" means RAISED something. An untouched visit
        # carried capture.consented until 4 November 2026, because that flag
        # was composed from the absence of a refusal and so stood with no
        # call having put it there; consent is gone, so an untouched visit
        # now rests with no flags at all and the allowance can go with it.
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
        # Only the scenario that sweeps every view sets `asked`; the calendar's
        # own scenario reads one view and is held to the checks above.
        if walk.asked:
            assert set(walk.asked) == set(decls), (
                "%s: this walk asked for %s and the bundle declares %s"
                % (shape, sorted(walk.asked), sorted(decls)))
            openable = {d["kind"] for vid, d in decls.items() if walk.asked[vid] != 403}
            assert kinds == openable, (
                "%s: this walk read %s and this caller may open %s"
                % (shape, sorted(kinds), sorted(openable)))

        # ---- the spine, when this walk read one
        timelines = [body for _, status, body in walk.raw
                     if status == 200 and isinstance(body, dict)
                     and "encounters" in body]
        if timelines:
            assert any(len(t["encounters"]) > 1 for t in timelines), (
                "%s: every subject this walk read has exactly one visit, so "
                "neither the join nor the newest-first ordering proves "
                "anything" % shape)
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


# --------------------------------------------------------------------------
# the record projection: rows in, an ABDM document out
# --------------------------------------------------------------------------
#
# WHY THIS IS NOT COMPARED OVER A SOCKET LIKE EVERYTHING ABOVE IT
# ---------------------------------------------------------------
# A document is not something a clinic asks for over the wire. It is what the
# outbox sends to ABDM, so api/main.py serves no route that returns one and
# there is nothing for e2e.py or check_live.py to compare. No route may be
# invented so that a check can reach behind the service, which leaves the
# shape fill_parity above already uses: a Go test that asserts nothing, fed
# inputs from here and read back for the diff.
#
# WHERE THE ROWS COME FROM, AND WHY THEY ARE NOT TYPED HERE
# ---------------------------------------------------------
# A row is an INPUT, so this file may hold one; but a row typed here would be
# a row no operation writes, and the thing worth comparing is what the
# DECLARATIONS produce. So every row below is made by running the real
# kernel/mapping.py over a payload generated from the questionnaire, with the
# adapter's own _text() doing the TEXT coercion every column gets. A form that
# grows a question grows these rows, and a mapping that changes changes them.
#
# Two actors, because the author on every row is the half of this slice that a
# single-author document cannot see: `document()` collects the distinct
# authors it met and the Composition names them, so a projection that dropped
# `created_by` would publish a document with one author or none and still look
# right.
PROJECTION_ACTORS = ("user:ravi", "user:nurse")
# A thread the stub store below answers for. Not a real id: the store is the
# case file's own rows, so this is the name the two engines ask under.
A_THREAD = "enc-parity"
PROJECTION_NOW = "2026-10-31T10:05:00+00:00"


class RowsOnly:
    """The store seam `fhir.document()` reads, over rows from the case file.

    Row ORDER is the real store's (`ORDER BY created_date, id`) and is NOT
    re-implemented: the case file lists rows already in that order, so order
    is an input to this comparison rather than something it compares. What is
    implemented is the `where` grammar's equality and present forms, which is
    the whole of what a section query uses today, and fhir/parity_test.go
    implements the same two.

    This pair is the one place the harness could agree with itself while both
    engines were wrong. A `document()` that dropped its `where` instead of
    passing it through would still show up, because only one engine would
    drop it.

    THE THREAD HAS TO BE PASSED, AND IT HAS TO BE THIS ONE. That is not the
    join either: it is the narrower fact that a document is about ONE VISIT,
    so a `document()` that read the store without saying which visit would
    publish one patient's rows inside another patient's record. FOUND BY
    MUTATION, and it is the property this check's first pass missed: both
    stubs ignored the argument, so a Go `Document` that passed no thread at
    all passed the whole gate with 843 ok.
    """

    def __init__(self, tables, thread):
        self.tables = tables
        self.thread = thread

    def select(self, resource, *, thread, where, fields, limit=50):
        if thread != self.thread:
            return []
        out = []
        for row in self.tables.get(resource) or []:
            keep = True
            for field, cond in (where or {}).items():
                if cond == "*":
                    keep = keep and bool(row.get(field))
                else:
                    keep = keep and row.get(field) == cond
            if not keep:
                continue
            out.append(row)
            if len(out) >= limit:
                break
        return out


def _two_rows_per_group(slug, payload):
    """The same payload with two rows in every repeating group it answers.

    `filled` answers a group once, which is one row, and one row proves no
    fan-out: a record that read only the first row, or that borrowed the row
    above it, would pass. The second row carries a DIFFERENT concept wherever
    the group binds an answer, so a projection that borrowed would publish the
    same code twice.
    """
    out = dict(payload)
    for question in validate_walk(schema(slug)["questions"]):
        if question.get("type") != "group" or not question.get("repeats"):
            continue
        rows = out.get(question["link_id"])
        if not rows:
            continue
        second = dict(rows[0])
        for sub in question.get("questions") or []:
            slugged = sub.get("answer_value_set")
            if not slugged or sub["link_id"] not in second:
                continue
            others = [c for c in sorted(vocab(slugged)["concepts"])
                      if c != second[sub["link_id"]]]
            if others:
                second[sub["link_id"]] = others[0]
                break
        out[question["link_id"]] = [rows[0], second]
    return out


def projection_rows():
    """{table: [row]} as this bundle's own write operations produce them."""
    from adapters.local.store import _text
    from kernel import declarations, mapping
    bundle = declarations.load("phc")
    tables, made = {}, 0
    for index, op_id in enumerate(sorted(bundle.manifest.operations)):
        op = bundle.operations.get(op_id) or {}
        if op.get("kind") != "write" or not op.get("mapping"):
            continue
        payload = _two_rows_per_group(
            op["input"], filled(op["input"], coder(), every=True))
        actor = PROJECTION_ACTORS[index % len(PROJECTION_ACTORS)]
        for resource, row in mapping.records(op, payload, actor=actor):
            made += 1
            row = {k: _text(v) for k, v in row.items() if v is not None}
            row.setdefault("id", "%s-%03d" % (resource, made))
            row.setdefault("created_date", "2026-10-31T09:%02d:00+00:00" % (made % 60))
            tables.setdefault(resource, []).append(row)
    # The encounter and the patient a Composition cannot do without. Taken
    # from what the operations wrote where they wrote one, and the id forced to
    # the thread the two engines ask under, which is the adapter's own join
    # (THREAD_COLUMN: an encounter's thread IS its id).
    assert "encounter" in tables and "patient" in tables, sorted(tables)
    tables["encounter"] = [dict(tables["encounter"][0], id=A_THREAD)]
    tables["patient"] = [tables["patient"][0]]
    # Every row a section can ask for, and the author on it. Both are
    # properties rather than comparisons: two engines can agree on a document
    # neither of them put an author in.
    authored = {row.get("created_by") for rows in tables.values() for row in rows}
    assert PROJECTION_ACTORS[0] in authored and PROJECTION_ACTORS[1] in authored, (
        "every row was written by one actor, so the Composition names one "
        "author and a projection that dropped created_by would pass: %s"
        % sorted(a for a in authored if a))
    return tables


def projection_cases():
    """The documents and the single projections both engines are asked for."""
    from kernel import declarations, fhir
    bundle = declarations.load("phc")
    tables = projection_rows()
    cases = {"rows": {"full": tables}, "documents": [], "projections": [],
             "patients": tables["patient"], "encounters": [], "practitioners": [],
             "numbers": [], "urns": []}

    # --- the declared document, as the bundle declares it. The placement is
    # read off the loaded bundle rather than typed, which is the whole reason
    # `documents` is a declaration: three callers used to type their own and
    # two of them disagreed about where a diagnosis goes.
    assert bundle.documents, "this bundle declares no document to publish"
    for did, declared in sorted(bundle.documents.items()):
        cases["documents"].append({
            "case": "full", "thread": A_THREAD, "profile": declared["profile"],
            "now": PROJECTION_NOW, "identifier_system": "",
            "what": "the declared document %r" % did,
            "sections": [{"slice": name,
                          "queries": [{"resource": resource, "where": dict(where or {})}
                                      for resource, where in queries]}
                         for name, queries in declared["sections_wanted"].items()]})

    # --- every other slice this build CAN fill, one document per profile, so
    # that a section code read off NRCeS's own example is compared rather than
    # only the three the bundle happens to use. The resource for each is the
    # one the rows above hold, which is what makes this an input and not a
    # placement decision: nothing here says a diagnosis belongs in a heading.
    for profile in sorted(fhir.PROFILES):
        for slice_name in sorted(fhir.sections(profile)):
            for resource in sorted(set(tables) & set(fhir.PROJECTIONS)):
                cases["documents"].append({
                    "case": "full", "thread": A_THREAD, "profile": profile,
                    "now": PROJECTION_NOW, "identifier_system": "http://phc.local",
                    "what": "%s/%s carrying %s rows" % (profile, slice_name, resource),
                    "sections": [{"slice": slice_name,
                                  "queries": [{"resource": resource, "where": {}}]}]})

    # --- the five refusals and the one skip, each an input rather than an
    # expectation: what the two engines SAY is the thing compared.
    cases["rows"]["no-subject"] = {"encounter": tables["encounter"],
                                   "notes": tables.get("notes") or []}
    # A store that answers no encounter at all, which is the state "no such
    # thread" is the sentence for. Reached this way rather than by asking
    # under an unknown thread id, because the THREAD JOIN is the adapter's own
    # (an encounter joins on its id, a patient on the encounter's `patient`
    # column) and RowsOnly deliberately does not re-implement it: the join is
    # compared over two REAL stores by write_path's walk, and a second
    # implementation here could agree with the Go stub while both were wrong.
    cases["rows"]["no-thread"] = {}
    cases["rows"]["empty-note"] = {
        "encounter": tables["encounter"], "patient": tables["patient"],
        "notes": [dict((tables.get("notes") or [{}])[0], id="note-blank", text="   ")]}
    cases["rows"]["nothing"] = {"encounter": tables["encounter"],
                                "patient": tables["patient"]}
    a_filled, an_empty = _a_where(tables)
    for one in (
        {"case": "full", "thread": A_THREAD, "profile": "OPConsultRecord",
         "sections": [{"slice": "NotASliceNRCeSDeclares",
                       "queries": [{"resource": "notes", "where": {}}]}],
         "what": "a section slice the profile does not declare"},
        {"case": "no-thread", "thread": "no-such-thread", "profile": "OPConsultRecord",
         "sections": [{"slice": "DocumentReference",
                       "queries": [{"resource": "notes", "where": {}}]}],
         "what": "a thread the store has never heard of"},
        {"case": "no-subject", "thread": A_THREAD, "profile": "OPConsultRecord",
         "sections": [{"slice": "DocumentReference",
                       "queries": [{"resource": "notes", "where": {}}]}],
         "what": "a visit with no person on it"},
        {"case": "nothing", "thread": A_THREAD, "profile": "OPConsultRecord",
         "sections": [{"slice": "DocumentReference",
                       "queries": [{"resource": "notes", "where": {}}]}],
         "what": "a thread with nothing to put in any section"},
        {"case": "full", "thread": A_THREAD, "profile": "OPConsultRecord",
         "sections": [{"slice": "InvestigationAdvice",
                       "queries": [{"resource": "service_request", "where": {}}]}],
         "what": "a resource with no FHIR projection"},
        {"case": "empty-note", "thread": A_THREAD, "profile": "OPConsultRecord",
         "sections": [{"slice": "DocumentReference",
                       "queries": [{"resource": "notes", "where": {}}]}],
         "what": "a narrative row with nothing in it"},
        {"case": "full", "thread": A_THREAD, "profile": "WellnessRecord",
         "sections": [{"slice": "VitalSigns",
                       "queries": [{"resource": "observation", "where": a_filled}]},
                      {"slice": "OtherObservations",
                       "queries": [{"resource": "observation", "where": an_empty}]}],
         "what": "two sections, one narrowed by a where that matches and one "
                 "by a where that matches nothing"},
    ):
        cases["documents"].append(dict(one, now=PROJECTION_NOW,
                                       identifier_system=""))
    assert "service_request" not in fhir.PROJECTIONS, \
        "pick a resource with no projection"

    # --- the single projections, every row through its own, so that a
    # difference in one resource is read as that resource rather than as a
    # whole document.
    for resource in sorted(set(tables) & set(fhir.PROJECTIONS)):
        for row in tables[resource]:
            cases["projections"].append({
                "resource": resource, "row": row, "subject": "urn:uuid:p",
                "encounter": "urn:uuid:e", "performer": "urn:uuid:n",
                "document_type": None})
            cases["projections"].append({
                "resource": resource, "row": row, "subject": "urn:uuid:p",
                "encounter": "urn:uuid:e", "performer": "",
                "document_type": {"code": "371530004",
                                  "text": "Clinical consultation report"}})
    # A narrative row with nothing in it, which is the one projection that
    # DECLINES a row rather than making a resource or refusing: an empty
    # attachment under a heading claiming there is a note is worse than no
    # section at all. Three spellings of nothing, because `text.strip()` is
    # what separates them from a note.
    for blank in ("", "   ", "\n\t "):
        cases["projections"].append({
            "resource": "notes", "row": {"id": "note-blank", "text": blank},
            "subject": "urn:uuid:p", "encounter": "urn:uuid:e",
            "performer": "urn:uuid:n", "document_type": None})
    # And an observation carrying a certainty R4 has nowhere to put, which is
    # the refusal that keeps a denied finding from being published as a fact.
    for column in ("verification_status", "clinical_status"):
        cases["projections"].append({
            "resource": "observation",
            "row": {"id": "obs-doubted", "status": "final", column: "refuted",
                    "value": "1"},
            "subject": "urn:uuid:p", "encounter": "urn:uuid:e",
            "performer": "", "document_type": None})
    # An observation with no status at all: refused, never given one.
    cases["projections"].append({
        "resource": "observation", "row": {"id": "obs-unsettled", "value": "1"},
        "subject": "urn:uuid:p", "encounter": "urn:uuid:e", "performer": "",
        "document_type": None})

    cases["encounters"] = [{"row": tables["encounter"][0], "subject": "urn:uuid:p"},
                           {"row": dict(tables["encounter"][0], status="completed"),
                            "subject": "urn:uuid:p"},
                           {"row": {"id": "enc-bare"}, "subject": "urn:uuid:p"}]
    cases["practitioners"] = sorted(
        {row["created_by"] for rows in tables.values() for row in rows
         if row.get("created_by")})
    # Every value a column of these rows actually holds, so the TEXT to decimal
    # cast is compared over what the declarations produce rather than over
    # numbers somebody chose. Plus the four spellings that are not numbers.
    cases["numbers"] = sorted(
        {row[column] for rows in tables.values() for row in rows
         for column in row if isinstance(row[column], str)}) \
        + ["", " 140 ", "1_0", "not a number", "140.0", "-0"]
    cases["urns"] = sorted({row["id"] for rows in tables.values() for row in rows})
    # How many rows of each table the store holds, so that a property below
    # can say "one resource per row" rather than "some resources".
    cases["counts"] = {resource: len(rows) for resource, rows in tables.items()}
    return cases


def _a_where(tables):
    """(a where that matches an observation row, one that matches none).

    Read off the rows rather than typed, so the narrowing is a fact about what
    the operations wrote. `category` because it is the one column a section
    query in this tree narrows on.
    """
    categories = {row.get("category") for row in tables.get("observation") or []}
    categories.discard(None)
    assert categories, "no observation row carries a category to narrow on"
    return {"category": sorted(categories)[0]}, {"category": "no-such-category"}


def python_projection(cases):
    from kernel import fhir
    out = {"documents": [], "projections": [], "patients": [], "encounters": [],
           "practitioners": [], "numbers": [], "urns": []}
    for one in cases["documents"]:
        wanted = {}
        for section in one["sections"]:
            wanted[section["slice"]] = [(q["resource"], dict(q["where"] or {}))
                                        for q in section["queries"]]
        try:
            made = fhir.document(
                RowsOnly(cases["rows"][one["case"]], one["thread"]), one["thread"],
                profile=one["profile"], sections_wanted=wanted, now=one["now"],
                **({"identifier_system": one["identifier_system"]}
                   if one["identifier_system"] else {}))
        except KeyError as exc:
            out["documents"].append({"ok": False, "resource": None,
                                     "refused": exc.args[0]})
        else:
            out["documents"].append({"ok": True, "resource": made, "refused": ""})
    for one in cases["projections"]:
        project = fhir.PROJECTIONS[one["resource"]]
        extra = {"document_type": one["document_type"]} \
            if one["resource"] in fhir.TYPED_BY_PROFILE else {}
        try:
            made = project(one["row"], subject=one["subject"],
                           encounter=one["encounter"],
                           performer=one["performer"] or None, **extra)
        except KeyError as exc:
            out["projections"].append({"ok": False, "resource": None,
                                       "refused": exc.args[0]})
        else:
            out["projections"].append({"ok": True, "resource": made, "refused": ""})
    out["patients"] = [fhir.patient(row) for row in cases["patients"]]
    out["encounters"] = [fhir.encounter(one["row"], subject=one["subject"])
                         for one in cases["encounters"]]
    out["practitioners"] = [fhir.practitioner(a) for a in cases["practitioners"]]
    out["numbers"] = [fhir._number(v) for v in cases["numbers"]]
    out["urns"] = [fhir._urn(s) for s in cases["urns"]]
    out["tables"] = python_projection_tables()
    # Round tripped through JSON, because that is what the Go answer arrives
    # as and a tuple would compare unequal for the wrong reason.
    return json.loads(json.dumps(out))


def python_projection_tables():
    """Every declaration kernel/fhir.py holds, flattened the way the Go test
    flattens its own, so that the two tables can be diffed."""
    from kernel import fhir
    return {
        "profiles": {name: {
            "profile": spec["profile"], "title": spec["title"],
            "type": {"code": spec["type"]["code"] or "",
                     "text": spec["type"]["text"]},
            "required": list(spec["required"]),
            "sections": {slice_name: {"title": section["title"],
                                      "code": section["code"] or "",
                                      "display": section.get("display") or ""}
                         for slice_name, section in spec["sections"].items()}}
            for name, spec in fhir.PROFILES.items()},
        "document_bundle": fhir.DOCUMENT_BUNDLE,
        "resource_type": dict(fhir.RESOURCE_TYPE),
        "status_binding": {"%s.%s" % key: value
                           for key, value in fhir.STATUS_BINDING.items()},
        "translated_status": sorted("%s.%s" % key for key in fhir.TRANSLATED_STATUS),
        "coded_status": {"%s.%s" % key: value
                         for key, value in fhir.CODED_STATUS.items()},
        "projections": sorted(fhir.PROJECTIONS),
        "typed_by_profile": sorted(fhir.TYPED_BY_PROFILE),
        "narrative": {"type": fhir.NARRATIVE_TYPE,
                      "language": fhir.NARRATIVE_LANGUAGE},
        "systems": {"nrces": fhir.NRCES, "loinc": fhir.LOINC, "ucum": fhir.UCUM,
                    "snomed": fhir.SNOMED, "hl7_category": fhir.HL7_CATEGORY},
    }


def go_projection(cases, tmp):
    cases_at = os.path.join(tmp, "fhir-cases.json")
    answers_at = os.path.join(tmp, "fhir-answers.json")
    with open(cases_at, "w") as f:
        json.dump(cases, f)
    done = subprocess.run(
        ["go", "test", "./fhir/", "-run", "TestTheProjectionAnswersForTheParityCheck",
         "-count=1"],
        cwd=str(backend.GO_MODULE), capture_output=True, text=True,
        env=dict(os.environ, PHC_FHIR_CASES=cases_at, PHC_FHIR_ANSWERS=answers_at))
    if done.returncode != 0 or not os.path.exists(answers_at):
        raise SystemExit("\nthe Go engine could not answer the projection cases:"
                         "\n\n%s%s\n" % (done.stdout[-4000:], done.stderr[-2000:]))
    with open(answers_at) as f:
        return json.load(f)


def projection_parity(tmp):
    cases = projection_cases()
    py = python_projection(cases)
    gone = go_projection(cases, tmp)

    # --- the declaration tables first. A difference here explains every
    # difference below it, and a section code that drifted is a record filed
    # under the wrong heading, which reads as correct everywhere it is read.
    for key in sorted(py["tables"]):
        assert py["tables"][key] == gone["tables"].get(key), (
            "the two engines declare %s differently\npython: %s\ngo:     %s"
            % (key, json.dumps(py["tables"][key], sort_keys=True),
               json.dumps(gone["tables"].get(key), sort_keys=True)))
    coded = sum(1 for spec in py["tables"]["profiles"].values()
                for section in spec["sections"].values() if section["code"])
    ok("the projection: both engines declare the same %d profiles, %d section "
       "slices of which %d carry a published code, and the same %d FHIR "
       "projections"
       % (len(py["tables"]["profiles"]),
          sum(len(s["sections"]) for s in py["tables"]["profiles"].values()),
          coded, len(py["tables"]["projections"])))

    # --- one resource at a time.
    for one, a, b in zip(cases["projections"], py["projections"], gone["projections"]):
        assert a == b, ("a %s row projects differently\nrow:    %s\npython: %s\n"
                        "go:     %s" % (one["resource"],
                                        json.dumps(one["row"], sort_keys=True),
                                        json.dumps(a, sort_keys=True),
                                        json.dumps(b, sort_keys=True)))
    refused = [a for a in py["projections"] if not a["ok"]]
    skipped = [a for a in py["projections"] if a["ok"] and a["resource"] is None]
    # The three outcomes really all happened, or the line above is two engines
    # agreeing about one of them.
    assert refused and skipped and len(refused) + len(skipped) < len(py["projections"]), \
        (len(refused), len(skipped), len(py["projections"]))
    ok("the projection: %d rows from this bundle's own mappings become the "
       "same resource in both engines, %d are refused with the same sentence "
       "and %d are declined as an empty narrative"
       % (len(py["projections"]), len(refused), len(skipped)))

    # --- the small conversions, which are where a Go rewrite drifts quietly.
    assert py["patients"] == gone["patients"], (py["patients"], gone["patients"])
    assert py["encounters"] == gone["encounters"], (py["encounters"], gone["encounters"])
    assert py["practitioners"] == gone["practitioners"], \
        (py["practitioners"], gone["practitioners"])
    assert py["urns"] == gone["urns"], (py["urns"][:3], gone["urns"][:3])
    assert py["numbers"] == gone["numbers"], \
        ("\n".join("%r: python %r, go %r" % (v, a, b)
                   for v, a, b in zip(cases["numbers"], py["numbers"], gone["numbers"])
                   if a != b))
    # A stored number really did come back as a JSON number and not a string,
    # or the cast this compares was never exercised.
    cast = [v for v, a in zip(cases["numbers"], py["numbers"])
            if isinstance(a, (int, float)) and not isinstance(a, bool)]
    assert cast, "no stored column holds a number, so the decimal cast is unproved"
    # And an actor's identity is hashed, not carried: every Practitioner id is
    # the same length and none of them holds the login name it was made from.
    for actor, made in zip(cases["practitioners"], py["practitioners"]):
        assert actor not in made["id"] and made["name"][0]["text"] == actor, made
    ok("the projection: %d patients, %d encounters and %d practitioners are "
       "identical, %d row ids give the same stable urn, and %d of %d stored "
       "values cast to the same JSON number"
       % (len(py["patients"]), len(py["encounters"]), len(py["practitioners"]),
          len(py["urns"]), len(cast), len(cases["numbers"])))

    # --- the whole documents.
    for one, a, b in zip(cases["documents"], py["documents"], gone["documents"]):
        assert a == b, ("%s differs between the engines\npython: %s\ngo:     %s"
                        % (one["what"], json.dumps(a, sort_keys=True)[:3000],
                           json.dumps(b, sort_keys=True)[:3000]))
    published = [a for a in py["documents"] if a["ok"]]
    denied = [a for a in py["documents"] if not a["ok"]]
    assert published and denied, (len(published), len(denied))
    # Each refusal says its own thing, or one of them is standing in for
    # another and a reader is told the wrong reason. With one collision, and
    # the collision is the point rather than a flaw: a note with nothing in it
    # is DECLINED, so its section is omitted, so the document has nothing to
    # publish and the engine says exactly that. Which is the hole the
    # narrative fallback was built to close, said by the engine rather than
    # asserted here.
    by_what = {one["what"]: a["refused"]
               for one, a in zip(cases["documents"], py["documents"])
               if not a["ok"]}
    assert by_what["a narrative row with nothing in it"] \
        == by_what["a thread with nothing to put in any section"], by_what
    distinct = {a["refused"] for a in denied}
    assert len(distinct) == len(by_what) - 1, sorted(distinct)
    ok("the projection: %d documents are byte identical in both engines and "
       "%d askings are refused with the same %d distinct sentences"
       % (len(published), len(denied), len(distinct)))

    # --- and the properties a diff cannot see, because two engines can agree
    # on a document that is wrong in the same way.
    declared = [a for one, a in zip(cases["documents"], py["documents"])
                if one["what"].startswith("the declared document") and a["ok"]]
    assert declared, "the bundle's own declared document published nothing"
    for made in declared:
        bundle = made["resource"]
        by_type = {}
        for entry in bundle["entry"]:
            by_type.setdefault(entry["resource"]["resourceType"], []).append(entry)
        composition = bundle["entry"][0]["resource"]
        assert composition["resourceType"] == "Composition", bundle["entry"][0]
        # Every reference resolves inside the document. A dangling reference is
        # a document a gateway accepts and a reader cannot read.
        inside = {entry["fullUrl"] for entry in bundle["entry"]}
        for found in re.finditer(r'"reference": "([^"]+)"', json.dumps(bundle)):
            assert found.group(1) in inside, found.group(1)
        # THE AUTHOR ON EACH. Every row this bundle's mappings wrote carries
        # its writer, so the Composition names every one it met and not one of
        # them. Two actors wrote these rows; a projection that dropped
        # created_by would name none and a document naming one would mean the
        # author was being read from somewhere other than the row.
        assert len(composition["author"]) == len(PROJECTION_ACTORS), \
            composition["author"]
        named = {entry["resource"]["name"][0]["text"]
                 for entry in by_type["Practitioner"]}
        assert named == set(PROJECTION_ACTORS), named
        # ROWS PER GROUP ROW. The diagnosis and the medicine are repeating
        # groups, and the second row of each carries a different concept, so a
        # record that borrowed the row above it would publish one code twice.
        for resource, kind in (("condition", "Condition"),
                               ("medication_request", "MedicationRequest"),
                               ("notes", "DocumentReference")):
            assert len(by_type.get(kind) or []) == cases["counts"][resource], (
                "%d %s rows became %d %s resources, so a record read some rows "
                "and not others" % (cases["counts"][resource], resource,
                                    len(by_type.get(kind) or []), kind))
        for kind in ("Condition", "MedicationRequest"):
            codes = []
            for entry in by_type.get(kind) or []:
                concept = entry["resource"].get("code") \
                    or entry["resource"].get("medicationCodeableConcept") or {}
                for coding in concept.get("coding") or []:
                    codes.append(coding["code"])
            assert len(codes) >= 2 and len(set(codes)) >= 2, (kind, codes)
            # No code borrowed from the row above it. Every group's second row
            # carries a DIFFERENT concept from its first, so two adjacent
            # resources sharing a code would mean a record read the row above
            # instead of its own.
            for before, after in zip(codes, codes[1:]):
                assert before != after, (kind, codes)
        # And the narrative really is in there, carrying its own words rather
        # than a heading claiming a note exists.
        notes = by_type.get("DocumentReference") or []
        assert notes, "the designed fallback published nothing"
        for entry in notes:
            attachment = entry["resource"]["content"][0]["attachment"]
            assert base64.b64decode(attachment["data"]).decode("utf-8").strip(), \
                attachment
    ok("the projection: the document this bundle DECLARES is asked of ONE "
       "visit, names both authors its rows carry, publishes one resource per "
       "group row with no code borrowed from the row above, carries the "
       "narrative's own words, and every reference in it resolves inside it")


# --------------------------------------------------------------------------
# the engine's own rule, on the Go side of the port
# --------------------------------------------------------------------------

def _go_live_code(path):
    """A Go file's live code: no comments, no string-free trivia.

    The Go half of scripts/engine_code.py, and it exists for the same reason:
    a comment explaining a rule has to be able to name what breaking it would
    look like. Comments are removed by scanning rather than by a regexp,
    because a `//` inside a string literal would otherwise blank out the rest
    of a live line.
    """
    text = path.read_text()
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i = text.find("*/", i + 2)
            i = n if i < 0 else i + 2
            continue
        if ch in "\"'`":
            out.append(ch)
            i += 1
            while i < n and text[i] != ch:
                if ch != "`" and text[i] == "\\":
                    out.append(text[i])
                    i += 1
                    if i < n:
                        out.append(text[i])
                        i += 1
                    continue
                out.append(text[i])
                i += 1
            if i < n:
                out.append(text[i])
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# The outbox. G8.
#
# WHY THIS IS NOT COMPARED OVER A SOCKET EITHER
# ---------------------------------------------
# The outbox is SWITCHED ON since 2026-11-01 and is still on NO ROUTE, which
# are different things. api/outbox.py holds a recording the line could not take
# and sweeps on a timer started with the process, and cmd/api/outbox.go sweeps
# the same spool; neither is reachable by a request, because an outbox is not
# something a caller asks for, and the sweeper runs on a five minute timer
# rather than in answer to one.
#
# So there is still nothing for e2e.py or check_live.py to compare, which
# leaves the shape projection_parity above already uses: a Go test that asserts
# nothing, fed inputs from here and read back for the diff. What that shape now
# also carries is the retention ceiling, because the clamp and the swept states
# are pure functions of their inputs and are exactly what two engines can
# disagree about silently. They did: see the ceiling comparison below.
#
# WHAT IS COMPARED, AND WHAT IS DELIBERATELY NOT
# ----------------------------------------------
# Compared: the scrubber sentence by sentence, the backoff, the admission
# refusals, the plain English the outbox reads as, and whole scripted sweeps
# down to each row's state, attempt count, receipt and reason.
#
# NOT compared: the item id, which is random on both sides; the claim and sent
# stamps, which are the clock's, so what travels is whether a row was STAMPED
# rather than when; and the sentence a failure that is not an Unsendable leaves,
# because the Python writes `type(broke).__name__` and Go has no such name. What
# both engines hold there is that the row names a KIND of failure and never the
# sentence that came with it, and the scrub cases are where that is compared.
# ---------------------------------------------------------------------------

# The strings a gateway really does send back, plus the shapes that must NOT be
# touched. Inputs, so this file may hold them; what is compared is what each
# engine does to them.
QUEUE_SCRUB_CASES = (
    "Aadhaar 1234 5678 9012 is already linked",
    "linking 123456789012 failed",
    "no profile for mobile 9876543210",
    "+91 98765 43210 is unknown",
    "OTP 123456 has expired, request another",
    "the one-time password 4821 was wrong",
    "Aadhaar 1234 5678 9012 refused",
    "status 404 on session scr-1",
    "token 12345678",
    "systolic 140 at 2026",
    "call 9876543210 or 9123456780 back",
    "ref 98765432109876543210 refused",
    "x9876543210y",
    # A body long enough that the truncation is observable.
    "the gateway said: " + "x" * 600,
    "",
)


def queue_cases():
    """The inputs both outboxes are driven through."""
    # The withheld map is the real one for the shape that runs fewest plugins,
    # so what is compared is this bundle's own subtraction rather than a
    # literal typed here.
    from kernel import contracts, declarations

    narrow = declarations.load("phc", facility="consulting-room-only")
    withheld = dict(narrow.withheld)
    one_withheld = sorted(withheld)[0] if withheld else "visit.household"
    plugin_of = withheld.get(one_withheld, "outreach")
    assert withheld, "no capability is withheld at the narrowest shape, so " \
                     "the admission refusal below proves nothing"

    return {
        "scrub": list(QUEUE_SCRUB_CASES),
        # Past the end of the table as well as inside it, and nought and
        # negative, because the ceiling and the floor are both reachable.
        "backoff": [-1, 0, 1, 2, 3, 4, 5, 6, 7, 99],
        # The owner's 24 hour ceiling on held audio
        # (docs/DECISIONS-2026-11-01.md decision 2), which is a CLAMP and not
        # a default, so both engines must clamp the same inputs the same way.
        # Negative and nought are both in, because "use the default" and
        # "delete on sight" are different answers and reading one as the other
        # is how a facility ends up holding audio it meant to drop.
        "ceiling": [-1, 0, 1, 3600, 6 * 3600, 24 * 3600, 24 * 3600 + 1,
                    48 * 3600, 999999],
        # Which states a held recording is swept out of. Every state an item
        # can wear, so the pair is compared on the ONE that is left out as
        # well as on the five that are not. `refused` is why this case exists:
        # it was missing from both engines until 2026-11-01, so a recording the
        # guard denied kept its bytes for as long as the disk lasted.
        "retention": sorted(contracts.QUEUE_STATES),
        "refusal": [
            {"kind": "audio", "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            {"kind": "document", "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            # A kind this outbox does not know.
            {"kind": "video", "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            # And the capability this centre has switched off.
            {"kind": "audio", "operation": "phc.op.consult-document",
             "capability": one_withheld, "withheld": {one_withheld: plugin_of}},
        ],
        "admit": [
            {"case": "ordinary", "kind": "document", "key": "enc-1",
             "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            {"case": "no key", "kind": "document", "key": "",
             "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            {"case": "blank key", "kind": "document", "key": "   ",
             "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            {"case": "unknown kind", "kind": "video", "key": "enc-1",
             "operation": "phc.op.consult-document",
             "capability": "encounter.document", "withheld": {}},
            {"case": "withheld plugin", "kind": "audio", "key": "enc-1",
             "operation": "phc.op.consult-document",
             "capability": one_withheld, "withheld": {one_withheld: plugin_of}},
        ],
        # The sentences, at nought, one, twelve and one of every state, because
        # a count that reads correctly only at twelve is the defect
        # web/src/agent.check.ts already holds the brief to.
        "standing": [
            {"case": "nothing", "rows": []},
            {"case": "one recording", "rows": [
                {"kind": "audio", "state": "ready", "attempts": 0}]},
            {"case": "twelve recordings", "rows": [
                {"kind": "audio", "state": "ready", "attempts": 0}
                for _ in range(12)]},
            {"case": "one of each state", "rows": [
                {"kind": "audio", "state": "ready", "attempts": 0},
                {"kind": "audio", "state": "sending", "attempts": 1},
                {"kind": "audio", "state": "failed", "attempts": 6},
                {"kind": "document", "state": "refused", "attempts": 0},
                {"kind": "document", "state": "held", "attempts": 2},
                {"kind": "document", "state": "sent", "attempts": 1}]},
            {"case": "one failed after one attempt", "rows": [
                {"kind": "document", "state": "failed", "attempts": 1}]},
        ],
        "sweeps": [
            {"case": "one allowed item goes once with a receipt",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW, QUEUE_NOW],
             "recover": False, "delivered": "known",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["receipt"]}},
            {"case": "a denial costs no attempt and sends nothing",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": False,
                        "deny": "missing capability encounter.document"}],
             "send": {"enc-1": ["receipt"]}},
            {"case": "a dead line fails and keeps the item",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known-empty",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["unsendable"]}},
            {"case": "an empty receipt is a failure, not a success",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known-empty",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["empty"]}},
            {"case": "a failure carrying a response body keeps only its kind",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known-empty",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["boom"]}},
            # The attempt limit, which needs the CLOCK to move: the backoff
            # after the second attempt is thirty seconds and after the fifth is
            # half an hour, so sweeps at one moment cannot reach it.
            {"case": "a dead line stops at the attempt limit",
             "now": QUEUE_NOW, "clock": QUEUE_HOURS, "recover": False,
             "delivered": "known-empty",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["unsendable"]}},
            # And the three answers recovery can get, each from a crash that is
            # MADE to happen by stranding the row in `sending`.
            {"case": "a remote that cannot say holds the item",
             "now": QUEUE_NOW, "clock": [], "strand": True, "recover": True,
             "recover_at": QUEUE_LATER, "delivered": "unknown",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["receipt"]}},
            {"case": "a remote that has it settles without a second send",
             "now": QUEUE_NOW, "clock": [], "strand": True, "recover": True,
             "recover_at": QUEUE_LATER, "delivered": "known",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["receipt"]}},
            {"case": "a remote that does not have it tries again",
             "now": QUEUE_NOW, "clock": [], "strand": True, "recover": True,
             "recover_at": QUEUE_LATER, "delivered": "known-empty",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["receipt"]}},
            {"case": "a mixed sweep: one goes, one is denied, one has no line",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known",
             "items": [{"key": "enc-1", "kind": "document", "blob": "",
                        "allow": True, "deny": ""},
                       {"key": "enc-2", "kind": "document", "blob": "",
                        "allow": False, "deny": "missing capability encounter.document"},
                       {"key": "enc-3", "kind": "audio", "blob": "",
                        "allow": True, "deny": ""}],
             "send": {"enc-1": ["receipt"], "enc-2": ["receipt"],
                      "enc-3": ["unsendable"]}},
            {"case": "a recording is dropped only after its receipt",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known",
             "items": [{"key": "enc-9", "kind": "audio",
                        "blob": "/tmp/phc-parity-recording.bin",
                        "allow": True, "deny": ""}],
             "send": {"enc-9": ["receipt"]}},
            {"case": "and not after a failed one",
             "now": QUEUE_NOW, "clock": [QUEUE_NOW], "recover": False,
             "delivered": "known-empty",
             "items": [{"key": "enc-9", "kind": "audio",
                        "blob": "/tmp/phc-parity-recording.bin",
                        "allow": True, "deny": ""}],
             "send": {"enc-9": ["unsendable"]}},
        ],
    }


QUEUE_NOW = "2026-11-01T10:00:00+00:00"
QUEUE_LATER = "2026-11-01T14:00:00+00:00"
# Two days on: past the owner's 24 hour ceiling on held audio, which the four
# hours above is deliberately inside. The retention cases need a clock the
# ceiling has actually expired under, and reusing QUEUE_LATER would have made
# every one of them answer "nothing was swept" in both engines and agree.
QUEUE_PAST_CEILING = "2026-11-03T10:00:00+00:00"
# One moment per hour, long enough to walk an item past every backoff in the
# table and reach the attempt limit.
QUEUE_HOURS = tuple("2026-11-01T%02d:00:00+00:00" % hour
                    for hour in range(10, 20))


class _ScriptedSender:
    """The remote both engines face, driven by the same word list."""

    def __init__(self, words, delivered):
        # Keyed by item key and not positional: the order items are swept in
        # is not deterministic in either engine, because `due` breaks ties on
        # the row id and that is random on both sides.
        self.words = dict(words or {})
        self.at = {}
        self.delivered_as = delivered
        self.handed = []

    def send(self, item, body):
        word = "receipt"
        listed = self.words.get(item.key) or []
        if listed:
            n = self.at.get(item.key, 0)
            word = listed[n] if n < len(listed) else listed[-1]
        self.at[item.key] = self.at.get(item.key, 0) + 1
        self.handed.append(item.key)
        if word == "unsendable":
            raise queues_module().Unsendable("there is no line")
        if word == "empty":
            return "   "
        if word == "boom":
            raise _ScriptedFailure(
                "patient Asha Devi, mobile 9876543210, diagnosis hypertension")
        return "r-" + item.key

    def delivered(self, item):
        answer = queues_module().Delivery
        if self.delivered_as == "unknown":
            return answer(known=False)
        if self.delivered_as == "known-empty":
            return answer(known=True, receipt="")
        return answer(known=True, receipt="r-" + item.key)


class _ScriptedFailure(RuntimeError):
    """A failure that is NOT an Unsendable, carrying what must not be kept."""


def queues_module():
    from kernel import queues
    return queues


def python_outbox(cases):
    """The same inputs through kernel/queues.py and adapters/local/spool.py."""
    from adapters.local.spool import SqliteSpool
    from kernel import contracts, queues

    out = {"scrub": [queues.scrubbed(one) for one in cases["scrub"]],
           "backoff": [queues.backoff(n) for n in cases["backoff"]],
           "refusal": [queues.refusal(kind=one["kind"], operation=one["operation"],
                                      capability=one["capability"],
                                      withheld=one["withheld"])
                       for one in cases["refusal"]]}

    out["ceiling"] = [queues.held_ceiling(n) for n in cases["ceiling"]]
    out["swept_states"] = list(queues.SWEPT_STATES)

    # One audio item in each state, swept past the ceiling: was its recording
    # deleted, and what state did the row end in. `delete` records rather than
    # unlinking, so the two engines are compared on the DECISION and not on
    # two filesystems.
    retention = []
    for state in cases["retention"]:
        spool = SqliteSpool(":memory:")
        item = queues.enqueue(spool, kind="audio", key="k-" + state,
                              thread="enc-1", operation="phc.op.consult-document",
                              capability="encounter.document",
                              facility="all-plugins", at=QUEUE_NOW,
                              blob="/held/" + state)
        if state != "ready":
            spool.settle(item.id, state=state, at=QUEUE_NOW,
                         receipt="r-1" if state == "sent" else "")
        removed = []
        gone = queues.sweep_audio(spool, now=QUEUE_PAST_CEILING,
                                  delete=removed.append)
        after = spool.get(item.id)
        retention.append({"state": state, "swept": gone == [item.id],
                          "deleted": removed, "final": after.state,
                          "says": after.last_error or ""})
    out["retention"] = retention

    admit = []
    for one in cases["admit"]:
        spool = SqliteSpool(":memory:")
        why = ""
        try:
            queues.enqueue(spool, kind=one["kind"], key=one["key"],
                           thread="enc-1", operation=one["operation"],
                           capability=one["capability"], facility="all-plugins",
                           at=QUEUE_NOW, withheld=one["withheld"])
        except queues.Unsendable as broke:
            why = str(broke)
        admit.append({"case": one["case"], "refused": why,
                      "rows": len(spool.items())})
    out["admit"] = admit

    standing = []
    for one in cases["standing"]:
        spool = SqliteSpool(":memory:")
        for n, row in enumerate(one["rows"]):
            spool.put(contracts.QueueItem(
                id="q-%s-%d" % (one["case"], n), kind=row["kind"],
                key="%s-%d" % (one["case"], n), thread="enc-1",
                operation="phc.op.consult-document",
                capability="encounter.document", facility="all-plugins",
                created_at=QUEUE_NOW, state=row["state"],
                attempts=row["attempts"]))
        standing.append({"case": one["case"],
                         "lines": queues.status(spool).lines()})
    out["standing"] = standing

    sweeps = []
    for one in cases["sweeps"]:
        spool = SqliteSpool(":memory:")
        verdict, deny, by_id = {}, {}, {}
        for want in one["items"]:
            item = queues.enqueue(
                spool, kind=want["kind"], key=want["key"],
                thread="enc-" + want["key"],
                operation="phc.op.consult-document",
                capability="encounter.document", facility="all-plugins",
                at=one["now"], actor="user:mo", blob=want["blob"])
            by_id[item.id] = want["key"]
            verdict[want["key"]] = want["allow"]
            deny[want["key"]] = want["deny"]
        sender = _ScriptedSender(one["send"], one["delivered"])
        senders = {"document": sender, "audio": sender}

        class _Allowed:
            allowed, reason = True, "allowed"

        def permit(item, verdict=verdict, deny=deny):
            if verdict.get(item.key):
                return _Allowed()

            class _Denied:
                allowed = False
                reason = deny.get(item.key) or ""
            return _Denied()

        dropped = []
        got = {"case": one["case"], "sent": [], "failed": [], "refused": [],
               "stopped": [], "held": [], "unrecorded": []}
        for at in one["clock"]:
            report = queues.pump(spool, senders, permit=permit,
                                 bodies=lambda i: {"body": True},
                                 now=at, delete=dropped.append)
            for name in ("sent", "failed", "refused", "stopped", "held",
                         "unrecorded"):
                got[name] += ["%s %s" % (by_id[i], why)
                              for i, why in getattr(report, name)]
        if one.get("strand"):
            # What a crash leaves: claimed and never settled. Without this
            # nothing is in flight and recovery finds nothing to settle, which
            # is how the `held` outcome went unproved the first time this was
            # written.
            for row in spool.items(state="ready"):
                spool.settle(row.id, state="sending", at=one["now"])
        if one["recover"]:
            report = queues.recover(spool, senders,
                                    now=one.get("recover_at") or one["now"])
            for name in ("sent", "failed", "held", "stopped"):
                got[name] += ["%s %s" % (by_id[i], why)
                              for i, why in getattr(report, name)]
        got["handed"] = list(sender.handed)
        got["dropped"] = len(dropped)
        got["rows"] = [
            {"key": row.key, "kind": row.kind, "state": row.state,
             "attempts": row.attempts, "receipt": row.receipt,
             "last_error": row.last_error, "stamped": bool(row.sent_at)}
            for state in contracts.QUEUE_STATES
            for row in spool.items(state=state)]
        got["lines"] = queues.status(spool).lines()
        sweeps.append(got)
    out["sweeps"] = sweeps
    return out


def go_outbox(cases, tmp):
    cases_at = os.path.join(tmp, "queue-cases.json")
    answers_at = os.path.join(tmp, "queue-answers.json")
    with open(cases_at, "w") as f:
        json.dump(cases, f)
    done = subprocess.run(
        ["go", "test", "./queues/", "-run", "TestTheOutboxAnswersForTheParityCheck",
         "-count=1"],
        cwd=str(backend.GO_MODULE), capture_output=True, text=True,
        env=dict(os.environ, PHC_QUEUE_CASES=cases_at,
                 PHC_QUEUE_ANSWERS=answers_at))
    if done.returncode != 0 or not os.path.exists(answers_at):
        raise SystemExit("\nthe Go engine could not answer the outbox cases:"
                         "\n\n%s%s\n" % (done.stdout[-4000:], done.stderr[-2000:]))
    with open(answers_at) as f:
        return json.load(f)


# The ONE sentence the two engines cannot spell alike, replaced by what both
# of them actually promise. kernel/queues.pump writes
# `type(broke).__name__` for a failure that is not an Unsendable, so the Python
# says "_ScriptedFailure" and Go says "queues_test.scriptedFailure": there is no
# name Go has that Python has. What both hold is that the row names a KIND of
# failure and NEVER the sentence that came with it, and that is asserted on its
# own below, over a sender whose failure carries a patient's name, a mobile
# number and a diagnosis. Normalised here and named here rather than quietly
# dropped from the comparison.
_TYPE_NAMED = re.compile(r"the service failed with \S+")
_TYPE_MARK = "the service failed with <a type name>"


def _comparable(value):
    """One engine's answer with only that sentence's type name flattened."""
    if isinstance(value, str):
        return _TYPE_NAMED.sub(_TYPE_MARK, value)
    if isinstance(value, list):
        return [_comparable(one) for one in value]
    if isinstance(value, dict):
        return {key: _comparable(one) for key, one in value.items()}
    return value


def outbox_parity(tmp):
    cases = queue_cases()
    py = python_outbox(cases)
    gone = go_outbox(cases, tmp)

    # --- the privacy decision, sentence by sentence. The row's one free text
    # field, so this is the comparison that matters most.
    for raw, a, b in zip(cases["scrub"], py["scrub"], gone["scrub"]):
        assert a == b, ("the two engines scrub differently\nin:     %r\n"
                        "python: %r\ngo:     %r" % (raw, a, b))
    # The cases really did remove something, or this is two engines agreeing
    # that nothing happened. Three rules, each one observed at least once.
    from kernel import queues
    from care_phc.connectors import redact
    marks = {"aadhaar": redact.AADHAAR_MARK, "otp": queues.OTP_MARK,
             "mobile": "<mobile ending "}
    for what, mark in sorted(marks.items()):
        assert any(mark in one for one in py["scrub"]), \
            "no case exercised the %s rule, so it is unproved" % what
    # And a long body really was truncated, or the ceiling is unobserved.
    assert any(len(one) == queues.ERROR_CHARS for one in py["scrub"]), \
        "no case reached the %d character ceiling" % queues.ERROR_CHARS
    ok("the outbox: both engines scrub the same %d failure sentences "
       "identically, removing an Aadhaar number whole, an OTP whole and a "
       "mobile number to its last four, and truncating at %d"
       % (len(cases["scrub"]), queues.ERROR_CHARS))

    assert py["backoff"] == gone["backoff"], (py["backoff"], gone["backoff"])
    assert py["refusal"] == gone["refusal"], (py["refusal"], gone["refusal"])
    # A refusal really was given and really was withheld, or the list above is
    # two engines agreeing on silence.
    assert any(one for one in py["refusal"]), "no case was refused"
    assert any("withheld by plugin" in one for one in py["refusal"]), \
        "no case was refused for a plugin this centre does not run"
    ok("the outbox: the same waits after %d attempt counts, and the same "
       "admission refusals including the capability and the plugin naming it"
       % len(cases["backoff"]))

    # --- the owner's 24 hour ceiling on held audio, which both engines must
    # clamp to identically, and the states a recording is swept out of.
    assert py["ceiling"] == gone["ceiling"], (
        "the two engines clamp the retention window differently\nin:     %s\n"
        "python: %s\ngo:     %s"
        % (cases["ceiling"], py["ceiling"], gone["ceiling"]))
    # And it really clamped, or this is two engines agreeing to pass a number
    # through. The 48 hour case must come back as 24.
    assert queues.AUDIO_CEILING_SECONDS in py["ceiling"], \
        "no case reached the ceiling, so the clamp is unobserved"
    assert py["ceiling"][cases["ceiling"].index(48 * 3600)] \
        == queues.AUDIO_CEILING_SECONDS, \
        "a 48 hour window was not clamped to 24: %s" % py["ceiling"]
    assert list(py["swept_states"]) == list(gone["swept_states"]), (
        py["swept_states"], gone["swept_states"])
    assert "refused" in py["swept_states"], \
        "the sweep does not walk `refused`, so a recording the guard denied " \
        "keeps its bytes past the ceiling in this engine"
    assert "sending" not in py["swept_states"], \
        "the sweep walks `sending`, so it can delete bytes out from under a " \
        "send that is in flight"
    ok("the outbox: both engines clamp %d configured retention windows to the "
       "same answers, a 48 hour window becoming the owner's %d hour ceiling in "
       "each, and both sweep the same %d states and leave `sending` alone"
       % (len(cases["ceiling"]), queues.AUDIO_CEILING_SECONDS // 3600,
          len(py["swept_states"])))

    for one, a, b in zip(cases["retention"], py["retention"], gone["retention"]):
        assert a == b, ("sweeping a held recording in state %r differs\n"
                        "python: %s\ngo:     %s" % (one, a, b))
    swept = [a for a in py["retention"] if a["swept"]]
    spared = [a for a in py["retention"] if not a["swept"]]
    assert swept and spared, (
        "every state was treated the same, so this case proves nothing: "
        "%d swept, %d spared" % (len(swept), len(spared)))
    # The two properties the decision turns on, asserted on the answers rather
    # than on the implementation.
    for a in swept:
        assert a["deleted"], "%r was reported swept and nothing was deleted" % a
        if a["state"] == "sent":
            # The remote HAS it. Its bytes go, and the row is NOT rewritten to
            # say nobody got a transcript, because somebody did.
            assert a["final"] == "sent", a
            assert "without being transcribed" not in a["says"], a
        else:
            assert a["final"] == "failed", a
            assert "without being transcribed" in a["says"], a
    for a in spared:
        assert not a["deleted"], "%r was spared and something was deleted" % a
    ok("the outbox: a held recording past the ceiling is swept identically "
       "from %d states in both engines and spared in %d, the row left saying "
       "nobody got a transcript, and a SENT row keeping its state because "
       "somebody did" % (len(swept), len(spared)))

    for one, a, b in zip(cases["admit"], py["admit"], gone["admit"]):
        assert a == b, ("admitting %r differs\npython: %s\ngo:     %s"
                        % (one["case"], a, b))
    kept = [a for a in py["admit"] if not a["refused"]]
    turned = [a for a in py["admit"] if a["refused"]]
    assert kept and turned, (len(kept), len(turned))
    # Refusing means refusing to HOLD it, which is stronger than refusing to
    # send it: a refused item leaves no row for a person to wonder about.
    for a in turned:
        assert a["rows"] == 0, \
            "a refused item left %d rows behind: %s" % (a["rows"], a)
    ok("the outbox: %d items are admitted and %d refused identically, and "
       "every refusal leaves NO row, which is refusing to hold rather than "
       "refusing to send" % (len(kept), len(turned)))

    for one, a, b in zip(cases["standing"], py["standing"], gone["standing"]):
        assert a == b, ("the outbox reads differently at %r\npython: %s\n"
                        "go:     %s" % (one["case"], a["lines"], b["lines"]))
    said = [one["lines"] for one in py["standing"]]
    assert ["nothing is waiting to be sent"] in said, \
        "no case read the empty outbox"
    assert any(any("1 recording" in line for line in lines) for lines in said), \
        "no case read at one, which is where a plural goes wrong"
    assert any(any("12 recordings" in line for line in lines) for lines in said), \
        "no case read at twelve"
    ok("the outbox: it reads as the same plain English in both engines at "
       "nought, at one, at twelve and with one row in every state")

    for one, a, b in zip(cases["sweeps"], py["sweeps"], gone["sweeps"]):
        # `lines` keeps its order, because the order of the sentences a person
        # reads is the queue's own (QUEUE_KINDS, then the states) and is not
        # the rows'. Everything else is compared as a BAG: within one sweep the
        # order is `due`'s, which reads oldest first and breaks ties on the row
        # id, and a row id is a random hex string in BOTH engines. So two
        # items queued in the same second have no determined order on either
        # side, and sorting is comparing the outbox rather than the randomness.
        # Said here rather than silently sorting.
        for key in ("sent", "failed", "refused", "stopped", "held",
                    "unrecorded", "handed"):
            assert sorted(_comparable(a[key])) == sorted(_comparable(b[key])), (
                "%s: the %s of one sweep differs\npython: %s\ngo:     %s"
                % (one["case"], key, a[key], b[key]))
        for key in ("dropped", "lines"):
            assert _comparable(a[key]) == _comparable(b[key]), (
                "%s: the %s of one sweep differs\npython: %s\ngo:     %s"
                % (one["case"], key, a[key], b[key]))
        rows = lambda side: sorted(_comparable(side["rows"]),
                                   key=lambda row: json.dumps(row, sort_keys=True))
        assert rows(a) == rows(b), (
            "%s: the rows differ after the sweep\npython: %s\ngo:     %s"
            % (one["case"], json.dumps(rows(a), sort_keys=True),
               json.dumps(rows(b), sort_keys=True)))

    # Every one of the four properties was actually exercised, or the loop
    # above is two engines agreeing about a scenario that did nothing.
    rows = [row for one in py["sweeps"] for row in one["rows"]]
    states = {row["state"] for row in rows}
    for needed in ("sent", "ready", "failed", "refused", "held"):
        assert needed in states, \
            "no sweep left a row in %r, so that outcome is unproved: %s" \
            % (needed, sorted(states))
    # Nothing reported as sent when it was not: every `sent` row carries a
    # receipt and a stamp, and no other row carries either.
    for row in rows:
        if row["state"] == "sent":
            assert row["receipt"] and row["stamped"], row
        else:
            assert not row["stamped"], \
                "a row that is %r carries a sent stamp: %s" % (row["state"], row)
    # Nothing sent twice: no scenario handed one key over more than once.
    for one in py["sweeps"]:
        handed = [name.split(" ")[0] for name in one["handed"]] or one["handed"]
        assert len(handed) == len(set(handed)) or one["case"].startswith(
            "a dead line stops"), \
            "%s handed a key over more than once: %s" % (one["case"], one["handed"])
    # And a response body really did reach a sender and really did not reach a
    # row.
    leaked = [row for row in rows
              if "Asha" in row["last_error"] or "hypertension" in row["last_error"]
              or "9876543210" in row["last_error"]]
    assert not leaked, "a response body reached an outbox row: %s" % leaked
    assert any("the service failed with" in row["last_error"] for row in rows), \
        "no sweep exercised a failure that was not an Unsendable"
    ok("the outbox: %d scripted sweeps leave identical rows in both engines, "
       "down to the state, the attempt count, the receipt and the reason, "
       "across all %d states a row can be in"
       % (len(cases["sweeps"]), len(states)))

    # And the recording's bytes: deleted after a receipt, never after a
    # failure. The two scenarios are the pair, and they are compared above;
    # this says which pair proved it.
    after_receipt = [one for one in py["sweeps"]
                     if one["case"] == "a recording is dropped only after its receipt"]
    after_failure = [one for one in py["sweeps"]
                     if one["case"] == "and not after a failed one"]
    assert after_receipt and after_failure
    assert after_receipt[0]["dropped"] == 1, after_receipt[0]
    assert after_failure[0]["dropped"] == 0, after_failure[0]
    ok("the outbox: a recording's bytes are deleted after the receipt and not "
       "after a failed send, identically in both engines")


# ---------------------------------------------------------------------------
# Codification. G8c.
#
# On no route in either engine: the stub is what the gate runs and what a
# health centre with no line has, and a candidate's only path into a record is
# through a screen. So the same shape again, a Go test that asserts nothing.
#
# THE ONE DECISION THIS SLICE MADE is which way an UNCACHED value set goes. The
# Python raises; the Go's terminology cache returns nil tags for a slug it does
# not hold, which cannot be told from a value set that declares none. The
# Python is right, because an empty tag set means "the tag rule does not
# apply", so reading a missing value set as having no categories turns the
# wrong-branch refusal OFF and lets a procedure through for a diagnosis. The Go
# was made to match and the Python was not touched. Both engines are asserted
# to FAIL on it below, rather than compared on the sentence: one raises from
# inside its cache loader and the other builds the same words from its own, and
# they spell the directory differently.
# ---------------------------------------------------------------------------

def codification_tag():
    """Which key a value set says a concept's semantic tag under. Read off the
    kernel's own constant rather than typed, because what the categories of a
    code system are called is the terminology's business."""
    from kernel import codification
    return codification.SEMANTIC_TAG


def codification_cases(tmp):
    """The inputs both codification seams are driven through.

    `crafted` is a value set written here, and it is the only way the
    wrong-branch rule can be reached at all: it needs a terminology that WOULD
    resolve the code, or the unresolvable rule catches the case first and the
    tag rule could be deleted with nothing failing. kernel/codification.py's
    own demo makes the same file for the same reason.
    """
    from kernel import terminology

    slug = "condition-code"
    local = terminology.LOCAL
    # Read off the value set rather than typed, so nothing here names a
    # clinical code and the cases grow when the bundle does.
    codes = sorted(local.expand(slug, "", 50), key=lambda c: c.code)
    assert codes, "%s holds no codes, so these cases prove nothing" % slug
    first = codes[0].code
    held = local.concepts(slug)
    tag = (held.get(first) or {}).get(codification_tag()) or ""

    crafted = os.path.join(tmp, "crafted-terminology")
    os.makedirs(crafted, exist_ok=True)
    with open(os.path.join(crafted, "%s.json" % slug), "w") as f:
        json.dump({"slug": slug, "system": "http://snomed.info/sct",
                   "semantic_tags": ["disorder", "finding"],
                   "concepts": {"71388002": {"display": "A Concept",
                                             "semantic_tag": "procedure"}}}, f)
    tagless = os.path.join(tmp, "tagless-terminology")
    os.makedirs(tagless, exist_ok=True)
    with open(os.path.join(tagless, "%s.json" % slug), "w") as f:
        json.dump({"slug": slug, "system": "http://snomed.info/sct",
                   "concepts": {"71388002": {"display": "A Concept"}}}, f)

    said = "the patient said something"
    return {
        "cases": [
            {"what": "a resolvable code becomes a candidate",
             "cache_dir": "", "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": first, "term": "what the service called it",
                          "score": 0.98, "linked": True, "tag": tag}]},
            {"what": "a code this build cannot resolve is refused and named",
             "cache_dir": "", "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "38362002", "term": "not coded here",
                          "score": 0.99, "linked": True, "tag": "disorder"}]},
            {"what": "a candidate with no code is refused and counted",
             "cache_dir": "", "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "", "term": "nameless"},
                         {"code": "   ", "term": "blank"}]},
            {"what": "the same concept under three names is kept once",
             "cache_dir": "", "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": first, "term": "the first name",
                          "score": 0.9, "tag": tag},
                         {"code": first, "term": "the second name",
                          "score": 0.8, "tag": tag},
                         {"code": first, "term": "the third name",
                          "score": 0.7, "tag": tag}]},
            {"what": "the service's own order is preserved",
             "cache_dir": "", "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": c.code, "term": "name", "score": 0.1 * (n + 1),
                          "tag": (held.get(c.code) or {}).get(
                              codification_tag()) or ""}
                         for n, c in enumerate(codes[:3])]},
            {"what": "a span that was never said refuses the whole batch",
             "cache_dir": "", "valueset": slug,
             "transcript": "the patient said one thing",
             "span": "a phrase nobody uttered", "text": "",
             "results": [{"code": first, "term": "a name", "tag": tag},
                         {"code": first, "term": "another", "tag": tag}]},
            {"what": "a span that WAS said is checked the same way",
             "cache_dir": "", "valueset": slug,
             "transcript": "the patient said one thing", "span": "one thing",
             "text": "", "results": [{"code": first, "term": "a name", "tag": tag}]},
            # The wrong branch, over the crafted cache.
            {"what": "a candidate from the wrong branch is refused on its tag",
             "cache_dir": crafted, "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "71388002", "term": "A Concept",
                          "score": 0.9, "linked": True, "tag": "procedure"}]},
            {"what": "and the same code with an accepted tag is kept",
             "cache_dir": crafted, "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "71388002", "term": "A Concept",
                          "tag": "disorder"}]},
            {"what": "a concept of no stated kind, where tags are declared",
             "cache_dir": crafted, "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "71388002", "term": "A Concept", "tag": ""}]},
            # A value set that declares no tags refuses nothing on a tag.
            {"what": "a value set that declares no tags refuses nothing on one",
             "cache_dir": tagless, "valueset": slug, "transcript": said,
             "span": "", "text": "",
             "results": [{"code": "71388002", "term": "A Concept",
                          "tag": "anything at all"}]},
            # And the decision: an uncached value set FAILS on both sides.
            {"what": "an uncached value set is an error, not a set with no "
                     "categories",
             "cache_dir": "", "valueset": "a-value-set-nobody-cached",
             "transcript": said, "span": "", "text": "",
             "results": [{"code": "71388002", "tag": "procedure"}]},
        ],
        "tags": [
            {"cache_dir": "", "valueset": slug},
            {"cache_dir": crafted, "valueset": slug},
            {"cache_dir": tagless, "valueset": slug},
            {"cache_dir": "", "valueset": "a-value-set-nobody-cached"},
        ],
    }


def python_codification(cases):
    """The same inputs through kernel/codification.py."""
    from kernel import codification, terminology

    def cache(where):
        return terminology.LOCAL if not where \
            else terminology.CachedTerminology(path=where)

    out = {"cases": [], "tags": []}
    for one in cases["cases"]:
        try:
            got = codification.resolve(
                one["results"], one["valueset"],
                transcript=one["transcript"], span=one["span"],
                terminology_=cache(one["cache_dir"]), text=one["text"])
        except Exception:
            out["cases"].append({"failed": True, "candidates": [],
                                 "refused": [], "asked": "", "reachable": False})
            continue
        out["cases"].append({
            "failed": False,
            "candidates": [c.public() for c in got],
            "refused": list(got.refused), "asked": got.asked,
            "reachable": got.reachable})
    for one in cases["tags"]:
        try:
            tags = codification.accepted_tags(one["valueset"],
                                              cache(one["cache_dir"]))
        except Exception:
            out["tags"].append({"failed": True, "tags": []})
            continue
        out["tags"].append({"failed": False, "tags": sorted(tags)})
    return out


def go_codification(cases, tmp):
    cases_at = os.path.join(tmp, "codification-cases.json")
    answers_at = os.path.join(tmp, "codification-answers.json")
    with open(cases_at, "w") as f:
        json.dump(cases, f)
    done = subprocess.run(
        ["go", "test", "./codification/", "-run",
         "TestTheCodificationSeamAnswersForTheParityCheck", "-count=1"],
        cwd=str(backend.GO_MODULE), capture_output=True, text=True,
        env=dict(os.environ, PHC_CODIFICATION_CASES=cases_at,
                 PHC_CODIFICATION_ANSWERS=answers_at))
    if done.returncode != 0 or not os.path.exists(answers_at):
        raise SystemExit("\nthe Go engine could not answer the codification "
                         "cases:\n\n%s%s\n"
                         % (done.stdout[-4000:], done.stderr[-2000:]))
    with open(answers_at) as f:
        return json.load(f)


def codification_parity(tmp):
    cases = codification_cases(tmp)
    py = python_codification(cases)
    gone = go_codification(cases, tmp)

    for one, a, b in zip(cases["tags"], py["tags"], gone["tags"]):
        assert a["failed"] == b["failed"], (
            "the two engines disagree about whether %r has readable tags: "
            "python failed=%s, go failed=%s"
            % (one["valueset"], a["failed"], b["failed"]))
        if not a["failed"]:
            assert a["tags"] == b["tags"], (one, a["tags"], b["tags"])
    declared = [a for a in py["tags"] if not a["failed"] and a["tags"]]
    none_declared = [a for a in py["tags"] if not a["failed"] and not a["tags"]]
    failed = [a for a in py["tags"] if a["failed"]]
    # All three outcomes really happened, or this is two engines agreeing about
    # one of them. The middle one is the whole reason the third is an error:
    # "declares no tags" and "is not there" must not be the same answer.
    assert declared and none_declared and failed, \
        (len(declared), len(none_declared), len(failed))
    ok("codification: both engines read the same semantic tags, agree that a "
       "value set declaring none has none, and BOTH REFUSE an uncached one "
       "rather than reading it as a set with no categories")

    for one, a, b in zip(cases["cases"], py["cases"], gone["cases"]):
        assert a["failed"] == b["failed"], (
            "%s: python failed=%s and go failed=%s"
            % (one["what"], a["failed"], b["failed"]))
        if a["failed"]:
            continue
        assert a["candidates"] == b["candidates"], (
            "%s: the candidates differ\npython: %s\ngo:     %s"
            % (one["what"], json.dumps(a["candidates"], sort_keys=True),
               json.dumps(b["candidates"], sort_keys=True)))
        assert a["refused"] == b["refused"], (
            "%s: the refusal sentences differ\npython: %s\ngo:     %s"
            % (one["what"], a["refused"], b["refused"]))
        assert a["asked"] == b["asked"] and a["reachable"] == b["reachable"], \
            (one["what"], a, b)

    offered = [a for a in py["cases"] if not a["failed"] and a["candidates"]]
    refused = [a for a in py["cases"] if not a["failed"] and a["refused"]]
    broke = [a for a in py["cases"] if a["failed"]]
    assert offered and refused and broke, (len(offered), len(refused), len(broke))
    # Each of the four refusals really was reached, or the sentences above are
    # two engines agreeing about the ones that were.
    sentences = " ".join(s for a in py["cases"] for s in a["refused"])
    for what, phrase in (("no span", "not in the transcript"),
                         ("not resolvable", "cannot resolve"),
                         ("wrong branch", "is a procedure"),
                         ("no code", "came back with no code")):
        assert phrase in sentences, \
            "the %r refusal was never reached, so it is unproved" % what
    # And nothing offered carries a shape a form control could bind to.
    for a in py["cases"]:
        for candidate in a["candidates"]:
            assert "value" not in candidate, \
                "a candidate has a `value` key: %s" % candidate
    ok("codification: %d askings answer identically in both engines, down to "
       "every refusal sentence, with all four refusals reached and no "
       "candidate carrying a shape a form control could bind to"
       % len(cases["cases"]))


def go_names_no_clinical_word():
    """No Go engine file types a diagnosis, a drug, a route or a frequency.

    scripts/check_rx.py and scripts/check_vitals.py hold the PYTHON engine to
    this, and nothing held the Go to it: the port could have moved the one
    failure kernel/ARCHITECTURE.md calls the renderer's own, `if code ==
    "29463-7"`, across the language boundary and no check would have noticed.
    The words are the value sets' own, read off disk, so a concept added to a
    value set arrives here without anybody editing this file.

    Test files are excluded, for exactly the reason engine_code.py excludes
    everything from `def demo(` onward: a demo has to name a concrete code and
    a concrete unit or it is not a test of anything.
    """
    sets = ("condition-code", "medication-code", "medication-route",
            "medication-frequency", "observation-code")
    words = set()
    for slug in sets:
        for code, concept in vocab(slug)["concepts"].items():
            words.add(code)
            if concept.get("display"):
                words.add(concept["display"])
            if concept.get("unit"):
                words.add(concept["unit"])
    assert len(words) >= 44, len(words)
    files = sorted(p for p in backend.GO_MODULE.rglob("*.go")
                   if not p.name.endswith("_test.go"))
    assert len(files) >= 20, len(files)
    for path in files:
        live = _go_live_code(path)
        assert "func " in live, path
        typed = sorted(w for w in words
                       if '"%s"' % w in live or "`%s`" % w in live)
        assert not typed, "%s types the clinical word(s) %r" % (path, typed)
    ok("the Go engine: none of %d files types any of %d clinical codes, "
       "displays or units from %d value sets"
       % (len(files), len(words), len(sets)))


# --------------------------------------------------------------------------
# the roll forward: a demo day that is not today any more
# --------------------------------------------------------------------------

def roll_forward(tmp):
    """A stale demo day, walked forward by both engines, compared.

    WHY THIS NEEDS ITS OWN PAIR OF KERNELS
    --------------------------------------
    Every queue view is `scope: today`, which is what a queue means, so a file
    seeded on an earlier day draws an empty workspace. Both adapters move the
    seeded threads forward in their CONSTRUCTOR, so the behaviour is
    unreachable from a freshly seeded file: every other check in this
    repository seeds today, the shift is zero days, and nothing runs. That
    left the one function whose whole job is "the demo still works tomorrow"
    with no check at all in either engine.

    So a file is seeded, backdated whole days, and copied: one engine opens
    each copy and the two queues are compared. Nothing about either queue is
    written here. What IS asserted is the pair of properties a comparison
    cannot see, because two engines that both did nothing would agree:

      - the queue is not empty, which it would be if nothing moved;
      - no row was pushed into the FUTURE, which is the clamp the Python's own
        docstring promised and did not enforce until somebody noticed a wait
        bar painting backwards out of its own row.

    The number of days is derived from the backdating this function did, not
    written down as an instant: there is no literal date anywhere in it.
    """
    import shutil
    import sqlite3

    from adapters.local.store import (KERNEL_RECORD, SEED_ACTOR, TABLES,
                                      THREAD_COLUMN, DEFAULT_THREAD_COLUMN)

    days = 3
    seeded = os.path.join(tmp, "stale.sqlite3")
    os.environ[backend.ENV] = backend.PYTHON
    backend.launch(seeded, bundle="phc", facility="all-plugins").close()
    os.environ.pop(backend.ENV, None)

    # Backdate the WHOLE file by whole days, every date column of every table,
    # so the demo day keeps its own internal order and its own times of day.
    # The table list is the adapter's own, so a column added there is moved
    # here without this function being edited.
    conn = sqlite3.connect(seeded)
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM encounter WHERE created_by = ?", [SEED_ACTOR]
        ).fetchone()[0]
        assert before, "the seed wrote no thread, so there is nothing to roll"
        for table in TABLES:
            column = KERNEL_RECORD.get(table, (None, "created_date"))[1]
            conn.execute(
                "UPDATE %s SET %s = replace(datetime(%s, ?), ' ', 'T') || '+00:00'"
                " WHERE %s IS NOT NULL" % (table, column, column, column),
                ["-%d days" % days])
        conn.commit()
        stale = conn.execute("SELECT MAX(created_date) FROM encounter"
                             " WHERE created_by = ?", [SEED_ACTOR]).fetchone()[0]
    finally:
        conn.close()
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    assert stale[:10] < today, (stale, today)

    started, queues = {}, {}
    try:
        for name in (backend.PYTHON, backend.GO):
            copy = os.path.join(tmp, "stale-%s.sqlite3" % name)
            shutil.copyfile(seeded, copy)
            os.environ[backend.ENV] = name
            started[name] = backend.launch(copy, bundle="phc",
                                           facility="all-plugins",
                                           env={"PHC_DIRECTORY": "absent"})
            queues[name] = get(started[name].base, PREFIX + "/queue")
        os.environ.pop(backend.ENV, None)
        assert normalise(queues[backend.PYTHON]) == normalise(queues[backend.GO]), (
            "a rolled-forward demo day differs\npython: %s\ngo:     %s"
            % (json.dumps(normalise(queues[backend.PYTHON]), sort_keys=True),
               json.dumps(normalise(queues[backend.GO]), sort_keys=True)))
        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00")
        for name, queue in queues.items():
            assert queue["rows"], (
                "%s: the demo day did not move, so the queue is empty a day "
                "after the seed" % name)
            for row in queue["rows"]:
                assert row["opened_at"] <= now, (
                    "%s: a rolled-forward row opens in the FUTURE (%s), which "
                    "is what made a wait bar paint backwards"
                    % (name, row["opened_at"]))
                assert row["opened_at"][:10] == today, (
                    "%s: a row the queue shows is not dated today: %s"
                    % (name, row["opened_at"]))
    finally:
        for server in started.values():
            server.close()
        os.environ.pop(backend.ENV, None)
    ok("the roll forward: a demo day %d days stale walks to today in both "
       "engines, identically, with %d rows on the queue and none of them in "
       "the future" % (days, len(queues[backend.GO]["rows"])))


# --------------------------------------------------------------------------
# the facility's shape: the lint, the one refusal a socket can reach, and the
# resolver's own silence
# --------------------------------------------------------------------------

def lint_cases():
    """The bent declarations both lints are asked about.

    Every refusal kernel/plugins.lint() makes that a Go process can reach. The
    three it makes that no Go process can -- an unknown key on either
    declaration, a declaration that is not a mapping, and the spelling YAML 1.1
    reads as a boolean -- are absent on purpose and named in the output below,
    because they are caught where bundle.yaml is PARSED and catalogue.json has
    already dropped them. A case written here that Go cannot see would be this
    check asserting a difference and calling it parity.

    Each case is the real manifest with one thing wrong, which is what
    scripts/check_plugins.py's own `bend()` does, so a plugin added to the
    bundle arrives in every case without this function being edited.
    """
    import copy

    import yaml

    manifest = yaml.safe_load((ROOT / "bundles" / "phc" / "bundle.yaml").read_text())
    cases = [("the real bundle, which must refuse nothing", manifest, None)]

    def bend(label, asked=None, **changes):
        out = copy.deepcopy(manifest)
        for key, value in changes.items():
            if value is _GONE:
                out.pop(key, None)
            else:
                out[key] = value
        cases.append((label, out, asked))
        return out

    shapes = copy.deepcopy(manifest["facilities"])
    some = sorted(shapes)[0]
    shapes[some]["without"] = ["no-such-plugin"]
    bend("a facility naming a plugin that does not exist", facilities=shapes)

    always = sorted(p for p, d in manifest["plugins"].items() if d.get("always"))
    assert always, "no plugin is declared always on, so the floor cannot be proved"
    shapes = copy.deepcopy(manifest["facilities"])
    shapes[some]["without"] = [always[0]]
    bend("a facility switching off the floor", facilities=shapes)

    # Two plugins and one capability, and the same plugin naming a capability
    # the bundle does not declare. Built off whichever plugin owns the first
    # declared capability rather than named.
    owner = {cap: pid for pid, decl in sorted(manifest["plugins"].items())
             for cap in decl["capabilities"]}
    shared = sorted(owner)[0]
    other = sorted(p for p in manifest["plugins"] if p != owner[shared])[0]
    pls = copy.deepcopy(manifest["plugins"])
    pls[other]["capabilities"] = list(pls[other]["capabilities"]) + [shared]
    bend("two plugins claiming one capability", plugins=pls)

    pls = copy.deepcopy(manifest["plugins"])
    pls[other]["capabilities"] = [shared + ".typo"]
    bend("a plugin naming a capability this bundle does not declare", plugins=pls)

    pls = copy.deepcopy(manifest["plugins"])
    pls[other].pop("capabilities")
    bend("a plugin with no capabilities", plugins=pls)

    pls = copy.deepcopy(manifest["plugins"])
    pls[other].pop("title")
    bend("a plugin with no title", plugins=pls)

    shapes = copy.deepcopy(manifest["facilities"])
    shapes[some].pop("title")
    bend("a facility with no title", facilities=shapes)

    shapes = copy.deepcopy(manifest["facilities"])
    shapes[some]["without"] = [other, other]
    bend("a facility naming one plugin twice", facilities=shapes)

    bend("a bundle declaring facilities and no default", facility=_GONE)
    bend("a default that is not one of the declared shapes",
         facility=manifest["facility"] + "-typo")
    bend("a misspelt PHC_FACILITY, which withholds nothing and runs the whole "
         "facility", asked=manifest["facility"] + "-typo")

    # And the one that matters: a choice that stops the line. A capability is
    # lifted out of the floor into a plugin of its own and a NARROWED shape
    # switches that plugin off, so the step nothing left can close and nothing
    # can skip belongs to a shape this build does not run. A lint that only
    # looked at the chosen shape would pass this.
    closes = {}
    for workflow in _workflow_frontmatter():
        for step in workflow.get("steps") or []:
            if not step.get("applies_when"):
                closes[step["done_when"]] = step["station"]
    raisers = {}
    for oid, op in _catalogue_operations().items():
        for flag in op.get("emits") or []:
            raisers.setdefault(flag, set()).add(op["capability"])
    stopper = sorted(flag for flag in closes
                     if len(raisers.get(flag) or ()) == 1)[0]
    lifted = sorted(raisers[stopper])[0]
    pls = copy.deepcopy(manifest["plugins"])
    for pid in pls:
        pls[pid]["capabilities"] = [c for c in pls[pid]["capabilities"]
                                    if c != lifted]
    pls["lifted"] = {"title": "One step's own ability", "capabilities": [lifted]}
    shapes = copy.deepcopy(manifest["facilities"])
    narrowed = sorted(f for f in shapes if f != manifest["facility"])[0]
    shapes[narrowed]["without"] = list(shapes[narrowed].get("without") or []) + ["lifted"]
    bend("a NARROWED shape whose choice stops the line, while the shape this "
         "build runs is sound", plugins=pls, facilities=shapes)

    return cases


_GONE = object()


@functools.lru_cache(maxsize=None)
def _workflow_frontmatter():
    """The bundle's workflow declarations, as kernel/plugins.lint reads them."""
    from catalogue.build import parse
    out = []
    for path in sorted((ROOT / "bundles" / "phc").glob("*.md")):
        fm, _ = parse(path)
        if fm.get("type") == "workflow":
            out.append(fm)
    return out


@functools.lru_cache(maxsize=None)
def _catalogue_capabilities():
    """The capabilities catalogue.json carries at its TOP LEVEL, which is the
    union over every bundle in the tree and not the loaded bundle's own.

    Read from the file rather than from a route on purpose: GET /catalogue
    substitutes the loaded bundle's list for exactly this key, because serving
    the union would hand the only account the browser can be six laboratory
    capabilities a health centre does not declare. So the wider set is
    UNREACHABLE over the wire, and a check that wanted to prove a route is not
    using it has to read the file.
    """
    with open(ROOT / "catalogue" / "catalogue.json") as f:
        return sorted(json.load(f)["capabilities"])


@functools.lru_cache(maxsize=None)
def _catalogue_operations():
    """The CATALOGUE-WIDE operations, which is what
    kernel/declarations.load() hands plugins.lint(): `ops =
    catalogue["operations"]`. Narrowing it to the loaded bundle's would be one
    engine deciding something the other did not."""
    with open(ROOT / "catalogue" / "catalogue.json") as f:
        return json.load(f)["operations"]


def python_lint(cases):
    from catalogue.build import parse
    from kernel import plugins as kplugins

    decls = {}
    for path in sorted((ROOT / "bundles" / "phc").glob("*.md")):
        fm, body = parse(path)
        decls[fm["id"]] = (fm, body)
    ops = _catalogue_operations()

    out = {}
    was = os.environ.get(kplugins.ENV)
    try:
        for name, manifest, asked in cases:
            if asked is None:
                os.environ.pop(kplugins.ENV, None)
            else:
                os.environ[kplugins.ENV] = asked
            out[name] = list(kplugins.lint(manifest, ops, decls))
    finally:
        os.environ.pop(kplugins.ENV, None)
        if was is not None:
            os.environ[kplugins.ENV] = was
    return out


def go_lint(cases, tmp):
    """The same bent declarations through the Go lint.

    The manifest is reshaped into the catalogue.json spelling the Go package
    reads -- `facilities` as {default, declared} rather than a bare mapping
    beside `facility:` -- because that is the one difference between the two
    sides that is NOT a difference of opinion: it is what
    kernel/declarations.compile_json writes, and the Go reads the compiled
    file.
    """
    sent = []
    for name, manifest, asked in cases:
        sent.append({
            "name": name,
            "plugins": manifest.get("plugins") or {},
            "facilities": {"default": manifest.get("facility") or "",
                           "declared": manifest.get("facilities") or {}},
            # `capabilities:` may be a mapping of id to its declared title,
            # and the Go Shape takes the ids. Iterating either shape yields
            # the ids, which is what both lints build a set from.
            "capabilities": list(manifest.get("capabilities") or []),
            "operations": _catalogue_operations(),
            "workflows": [{"id": fm["id"], "steps": fm.get("steps") or []}
                          for fm in _workflow_frontmatter()],
            "asked": asked or "",
        })
    cases_at = os.path.join(tmp, "plugin-cases.json")
    answers_at = os.path.join(tmp, "plugin-answers.json")
    with open(cases_at, "w") as f:
        json.dump(sent, f)
    done = subprocess.run(
        ["go", "test", "./plugins/", "-run", "TestTheLintAnswersForTheParityCheck",
         "-count=1"],
        cwd=str(backend.GO_MODULE), capture_output=True, text=True,
        env=dict(os.environ, PHC_PLUGIN_CASES=cases_at,
                 PHC_PLUGIN_ANSWERS=answers_at))
    if done.returncode != 0 or not os.path.exists(answers_at):
        raise SystemExit("\nthe Go engine could not answer the plugin lint "
                         "cases:\n\n%s%s\n"
                         % (done.stdout[-4000:], done.stderr[-2000:]))
    with open(answers_at) as f:
        return json.load(f)


def lint_parity(tmp):
    cases = lint_cases()
    py = python_lint(cases)
    gone = go_lint(cases, tmp)

    clean = cases[0][0]
    assert py[clean] == [] == gone[clean], (py[clean], gone[clean])
    for name, _, _ in cases[1:]:
        assert py[name], ("%s: the PYTHON lint refuses nothing, so this case "
                          "proves nothing about either engine" % name)
        assert py[name] == gone.get(name), (
            "%s: the two lints refuse differently\npython: %s\ngo:     %s"
            % (name, json.dumps(py[name], indent=1),
               json.dumps(gone.get(name), indent=1)))
    refusals = sum(len(py[name]) for name, _, _ in cases)
    ok("the plugin lint: %d bent declarations draw the same %d refusals from "
       "both engines, word for word, and the real bundle draws none"
       % (len(cases) - 1, refusals))

    # The three the Go cannot be asked, said rather than left to be assumed
    # from a shorter list. They are caught where bundle.yaml is parsed, and
    # kernel/declarations.compile_json has dropped them by the time any Go
    # process can look.
    from kernel import plugins as kplugins
    unreachable = ("an unknown key on a plugin or a facility",
                   "a declaration that is not a mapping",
                   "the `off:` spelling YAML 1.1 reads as the boolean false")
    # `catchment` joined them on 2026-11-01. It is the one facility key that
    # carries a nested declaration rather than a list of ids, and BOTH engines
    # serve it on GET /facility, so the body diff above is what proves they
    # agree about it rather than this list.
    assert set(kplugins.FACILITY_KEYS) == {"title", "without", "catchment"}, \
        kplugins.FACILITY_KEYS
    ok("and %d of its refusals cannot cross the port at all, because they are "
       "about the SHAPE of a declaration and catalogue.json carries only the "
       "%d keys a facility and the %d a plugin may have: %s"
       % (len(unreachable), len(kplugins.FACILITY_KEYS),
          len(kplugins.PLUGIN_KEYS), "; ".join(unreachable)))


def token_parity(tmp):
    """The day sequence over both engines, and the counter they SHARE.

    WHY THIS IS NOT JUST ANOTHER ROUTE DIFF
    ---------------------------------------
    Until 2026-11-01 this engine pair did not agree about numbers at all and
    no check in this file said so. The Python issued one out of
    kernel/tokens.py and ignored any token in the request; the Go read `token`
    out of the request BODY and, given none, had its store invent one from the
    last three characters of the generated row id. So the Go's numbers came
    from whichever client asked, or from a row id, and in neither case from a
    sequence.

    Every other check here compares the two engines on one set of
    declarations, and not one of them looked at the token, because `token` is
    in VOLATILE_KEYS: it is normalised away before two answers are diffed, for
    the good reason that two engines seeding their own file produce their own
    row ids. A VALUE EXCLUDED FROM EVERY COMPARISON IS A VALUE NO COMPARISON
    DEFENDS. That is the hole this function fills, and it is why the three
    properties below are asserted directly rather than diffed.

    1. EACH ENGINE ISSUES THE SAME SEQUENCE. Same declarations, same seeded
       demo day, n arrivals each: the two lists of numbers must be equal. Not
       normalised and not bagged. The actual numbers, in order.

    2. NEITHER LETS THE CALLER CHOOSE. A body naming its own token is ignored
       by both, because a number a client picks is a number nothing else knew
       it had given out.

    3. THEY SHARE ONE COUNTER IN ONE FILE. This is the property that matters
       in a clinic and the one a per-engine check cannot see. A deployment
       mid-migration has both engines over one database, so numbers are taken
       ALTERNATELY here, python, go, python, go, against the same file, and the
       whole run must still be consecutive with no duplicate and no hole. Two
       engines each keeping their own sequence is how one waiting room gets two
       number ones, and it would pass properties 1 and 2 comfortably.

    PROVED TO FAIL, which is the only thing that makes any of it evidence.
    Each mutation was applied, the old text asserted gone and the file
    asserted changed before anything ran, and the file restored and compared
    byte for byte afterwards.

      - cmd/api/guard.go: restore the openThread this replaced, reading
        `token` out of the request body and handing it to the store.
        -> property 2 fails: "go honoured the token in the request body:
           ['999', '999', '999', '999']".
      - store/store.go IssueToken: key the counter on scope + "-go", so the
        Go engine keeps its own row.
        -> property 3 fails: "2 counter rows in one file: [(..., 'today', ...,
           11), (..., 'today-go', ..., 12)]", which is the two-sequences
           failure happening rather than being described.
    """
    import sqlite3

    staff = {"X-PHC-Role": "frontdesk", "X-PHC-Actor": "user:frontdesk"}
    arrivals = 4
    numbers = {}

    # ---------------------------------------------------------------- 1 and 2
    for name in (backend.PYTHON, backend.GO):
        os.environ[backend.ENV] = name
        db = os.path.join(tmp, "tokens-%s.sqlite3" % name)
        server = backend.launch(db, bundle="phc", facility="all-plugins")
        try:
            got = []
            for _ in range(arrivals):
                # A body naming its own number, every time. Both engines must
                # ignore it. The value is deliberately one no sequence this
                # short could reach, so honouring it would be unmistakable.
                status, panel = call(server.base, PREFIX + "/threads",
                                     method="POST", headers=staff,
                                     body={"token": "999"})
                assert status == 200, (name, status, str(panel)[:300])
                got.append(panel["subject"]["token"])
            numbers[name] = got
            assert "999" not in got, (
                "%s honoured the token in the request body: %s. A number a "
                "client picks is a number nothing else knew it had given out."
                % (name, got))
        finally:
            server.close()
            os.environ.pop(backend.ENV, None)

    assert numbers[backend.PYTHON] == numbers[backend.GO], (
        "the two engines issued different numbers for the same arrivals on the "
        "same declarations: python %s, go %s"
        % (numbers[backend.PYTHON], numbers[backend.GO]))
    ok("the day sequence: %d arrivals at each engine on one seeded demo day got "
       "%s from both, and a token named in the request body is ignored by both"
       % (arrivals, ", ".join(numbers[backend.PYTHON])))

    # -------------------------------------------------------------------- 3
    # One file, both engines, alternating. Each server is started and stopped
    # around its own arrival so the two never hold the file at once: what is
    # proved here is that the SEQUENCE is shared, not that SQLite tolerates two
    # writers, which both adapters are deliberately configured against
    # (care_phc_mcp/store/store.go caps the pool at one connection and says
    # why).
    shared = os.path.join(tmp, "tokens-shared.sqlite3")
    order, issued = [], []
    for i in range(6):
        name = backend.PYTHON if i % 2 == 0 else backend.GO
        os.environ[backend.ENV] = name
        server = backend.launch(shared, bundle="phc", facility="all-plugins")
        try:
            status, panel = call(server.base, PREFIX + "/threads",
                                 method="POST", headers=staff, body={})
            assert status == 200, (name, status, str(panel)[:300])
            issued.append(int(panel["subject"]["token"]))
            order.append(name)
        finally:
            server.close()
            os.environ.pop(backend.ENV, None)

    assert len(set(issued)) == len(issued), (
        "two engines against ONE file issued the same number twice: %s in the "
        "order %s. This is two sequences in one waiting room." % (issued, order))
    assert issued == sorted(issued), (
        "the shared sequence went backwards: %s in the order %s" % (issued, order))
    assert issued[-1] - issued[0] == len(issued) - 1, (
        "the shared sequence has a hole: %s in the order %s. A hole is a number "
        "called out to a room where nobody has it." % (issued, order))

    # And ONE counter row, not one per engine. Read straight out of the file,
    # because the whole claim is about what is on disk.
    conn = sqlite3.connect(shared)
    try:
        rows = conn.execute(
            "SELECT workflow, scope, day, last FROM day_sequence").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, (
        "%d counter rows in one file: %s. Two engines keeping their own row is "
        "two sequences that will disagree by tomorrow." % (len(rows), rows))
    assert int(rows[0][3]) == issued[-1], (
        "the counter says %s and the last number issued was %s"
        % (rows[0][3], issued[-1]))
    ok("and both engines draw from ONE counter in one file: %d arrivals taken "
       "alternately python, go came back %s, held in a single row of "
       "day_sequence rather than one row each" % (len(issued), issued))


def misspelt_facility(tmp):
    """A shape neither bundle declares, asked for by the environment.

    The one refusal in kernel/plugins.lint that a socket check can reach, and
    the reason the lint had to cross the port at all. `chosen()` returns
    whatever PHC_FACILITY says; an unrecognised shape resolves to no
    declaration; and no declaration withholds nothing. So without the lint a
    typo in the variable runs the FULL facility, and a centre meant to have no
    laboratory quietly has one, with a green log line.

    Measured on this build before this slice: the Go kernel came up, answered
    GET /facility with the misspelt name and an empty `withheld`, and served
    every laboratory tool.

    Neither engine may START. That is stronger than refusing a request: a
    kernel that answered anything at all would already be the wrong clinic.
    """
    import shutil

    asked = "no-such-centre"
    refused = {}
    for name in (backend.PYTHON, backend.GO):
        os.environ[backend.ENV] = name
        where = os.path.join(tmp, "misspelt-%s" % name)
        os.makedirs(where, exist_ok=True)
        try:
            server = backend.launch(os.path.join(where, "x.sqlite3"),
                                    bundle="phc", facility=asked)
        except SystemExit as exc:
            refused[name] = str(exc)
            continue
        finally:
            os.environ.pop(backend.ENV, None)
        server.close()
        raise SystemExit(
            "\nthe %s backend STARTED with %s=%s, which no shape of this "
            "bundle declares. It therefore withholds nothing and is running "
            "the whole facility.\n" % (name, "PHC_FACILITY", asked))
    os.environ.pop(backend.ENV, None)
    shutil.rmtree(os.path.join(tmp, "misspelt-%s" % backend.GO), ignore_errors=True)
    for name, said in refused.items():
        assert asked in said, (name, said[-2000:])
        assert "is not one of the facilities" in said, (name, said[-2000:])
    ok("a misspelt %s stops BOTH engines before they answer anything, naming "
       "the shape and the ones the bundle declares, rather than withholding "
       "nothing and running the whole facility" % "PHC_FACILITY")


def go_resolver_names_no_declared_word():
    """The Go plugin resolver types none of this facility's declared words.

    The rule scripts/check_plugins.py section 8 holds kernel/plugins.py to, and
    for the same reason: a module that types a capability, a station, a flag, a
    role, a plugin id or a facility id has opinions about ONE facility and is
    not the thing that makes two of them possible. Nothing held the Go
    counterpart to it, so the port could have moved `if facility ==
    "no-laboratory"` across the language boundary unobserved.

    Read off bundle.yaml, so it grows when the bundle does. Test files are
    excluded for the reason engine_code.py excludes a demo: a case that bends a
    declaration has to name one.
    """
    import yaml

    manifest = yaml.safe_load((ROOT / "bundles" / "phc" / "bundle.yaml").read_text())
    words = set(manifest["capabilities"]) | set(manifest["states"]) \
        | set(manifest["stations"]) | set(manifest["roles"]) \
        | set(manifest["plugins"]) | set(manifest["facilities"]) \
        | set(manifest["operations"]) | {manifest["id"], manifest["facility"]}
    assert len(words) >= 60, len(words)
    files = sorted(p for p in (backend.GO_MODULE / "plugins").glob("*.go")
                   if not p.name.endswith("_test.go"))
    assert files, "the Go plugin resolver is not where this check looks"
    for path in files:
        live = _go_live_code(path)
        assert "func " in live, path
        typed = sorted(w for w in words
                       if '"%s"' % w in live or "`%s`" % w in live)
        assert not typed, "%s types this facility's word(s) %r" % (path, typed)
    ok("the Go plugin resolver types none of this facility's %d declared "
       "words: not a capability, a station, a flag, a role, a plugin id, a "
       "facility id or an operation" % len(words))


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
        # Then the record projection and the Go engine's own rule, for the
        # same reason: neither opens a socket, and both are read more easily
        # before three pairs of kernels have been started.
        projection_parity(tmp)
        # The outbox, for the same reason and in the same shape: it is on no
        # route in either engine, so there is nothing for a socket check to
        # compare.
        outbox_parity(tmp)
        # And the codification seam, for the same reason again.
        codification_parity(tmp)
        go_names_no_clinical_word()
        # The facility's shape, before the shapes themselves are started: the
        # lint is what decides whether a kernel may start at all, so a
        # difference in it explains every difference below it.
        lint_parity(tmp)
        go_resolver_names_no_declared_word()
        misspelt_facility(tmp)
        # The day sequence, which no other check in this file can defend:
        # `token` is in VOLATILE_KEYS and is normalised away before two
        # answers are diffed, so the one value the race was about is the one
        # value every comparison drops. See the function.
        token_parity(tmp)
        # Before the shapes, because it is the one pair of kernels that does
        # not start from a file seeded today, and a difference here is cheaper
        # to read than one found after three pairs have been started.
        roll_forward(tmp)
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


def roles(shape, python, go):
    """A facility's own role combination, saved over both engines.

    bundle.yaml's `roles:` ship as CARE is_system=True presets and a facility's
    deviation is its own row, which CARE's sync_permissions_roles deliberately
    never touches. So nothing here mutates a preset: GET /roles comes back with
    both, and the byte-for-byte pass above already compared it.

    THE PROPERTY THIS IS FOR, WHICH ONLY EXISTS AT A NARROWED CENTRE
    ---------------------------------------------------------------
    A role editor is the one place a capability can be ADDED to a caller after
    the bundle declared it. So it is the one place the facility's subtraction
    can be stepped around: save `lab.order` into a role at a centre with no
    laboratory and, if the override replaces the narrowed set rather than
    feeding it, the caller now holds a capability this centre does not run --
    and the guard, the quick action row and the MCP tool list all read that set
    and believe it.

    At a centre that runs every plugin the two orders are indistinguishable,
    because nothing is withheld. That is why the assertion below is made at
    every shape that withholds something and said to be vacuous at the one that
    does not, rather than being written once against the default shape and
    assumed to hold.

    Run last: an override is in-process state and one facility per kernel, so
    every comparison before this one would be reading what this one wrote.
    """
    # Which role to bend, chosen off the declarations rather than named: a
    # preset that holds something this facility withholds if there is one, so
    # the save has something to try to step around.
    presets = get(python, PREFIX + "/roles")["presets"]
    withheld = sorted(get(go, PREFIX + "/facility")["withheld"])
    # Which capability a save needs, DERIVED rather than typed: api/main.py's
    # own note is that it names no operation and sits in no shipped preset on
    # purpose, which makes it the one declared capability no preset carries.
    # Typing the word here would be this check holding an opinion about one
    # facility's vocabulary.
    carried = set()
    for caps in presets.values():
        carried |= set(caps)
    admin = sorted(set(get(go, PREFIX + "/facility")["capabilities"]) - carried)
    assert len(admin) == 1, (
        "api/main.py's role editor needs exactly one capability no preset "
        "carries; this bundle leaves %r outside every preset" % admin)
    admin = admin[0]
    deviating = sorted(r for r, caps in presets.items()
                       if set(caps) & set(withheld)) or sorted(presets)
    role = deviating[0]
    # And what to save: everything that preset already held, plus everything
    # this facility withholds. A legal save -- a facility declines a
    # capability, it does not delete one from the bundle -- so both engines
    # must accept it.
    wanted = sorted(set(presets[role]) | set(withheld))

    answers = {}
    for name, base in (("python", python), ("go", go)):
        status, body = call(base, PREFIX + "/roles/" + role, method="PUT",
                            body={"capabilities": wanted})
        answers[name] = (status, body)
    assert answers["python"] == answers["go"], answers
    assert answers["go"][0] == 200, answers["go"]
    assert answers["go"][1]["capabilities"] == wanted, (answers["go"], wanted)

    # Saved, and readable back as a deviation rather than as an edited preset.
    for base in (python, go):
        back = get(base, PREFIX + "/roles")
        assert back["overrides"][role] == wanted, back["overrides"]
        assert back["presets"][role] == presets[role], (
            "the preset itself was edited, which is the one thing a facility's "
            "deviation may never do")
    py_roles = get(python, PREFIX + "/roles")
    go_roles = get(go, PREFIX + "/roles")
    assert py_roles == go_roles, (py_roles, go_roles)

    # And what the caller actually holds. The subtraction is applied to the
    # OVERRIDE, every time, which is the property above.
    header = {"X-PHC-Role": role}
    py_mine = get(python, PREFIX + "/whoami", header)["capabilities"]
    go_mine = get(go, PREFIX + "/whoami", header)["capabilities"]
    assert py_mine == go_mine, (py_mine, go_mine)
    for cap in withheld:
        assert cap not in go_mine, (
            "%s: '%s' was saved into role '%s' and the caller HOLDS it, so a "
            "role editor stepped around the facility's subtraction" % (
                shape, cap, role))
    if withheld:
        ok("%s: a role saved WITH all %d capabilities this centre withholds is "
           "accepted by both engines, stored as a deviation beside the "
           "untouched preset, and the caller still holds none of them"
           % (shape, len(withheld)))
    else:
        ok("%s: a role saved with every capability this bundle declares is "
           "accepted by both engines and stored as a deviation beside the "
           "untouched preset; this centre withholds nothing, so the "
           "subtraction has nothing to prove here" % shape)

    # The three refusals, compared rather than asserted: who may save, which
    # roles exist, and which words are capabilities of THIS bundle. The last
    # is the one that matters -- catalogue.json's top-level `capabilities` is
    # the union over every bundle, and validating a save against that union
    # would let a health centre's role editor grant laboratory capabilities
    # this bundle does not declare, to the only account the browser can be.
    whole = get(go, PREFIX + "/facility")["capabilities"]
    # The capabilities the embedded catalogue carries for OTHER bundles. This
    # is the case that matters and the one a first pass did not write: a word
    # that is in NEITHER list is refused by an engine validating against
    # either one, so a check that only tries a typo compares two engines
    # agreeing about nothing. A word that is in the file's union and not in
    # this bundle's own is refused only by an engine that validates against
    # the right one of the two.
    wider = sorted(set(_catalogue_capabilities()) - set(whole))
    assert wider, (
        "catalogue.json's capability union is this bundle's own, so the "
        "over-grant it was narrowed to prevent cannot be reached from here")
    refusals = [
        ("not an administrator", PREFIX + "/roles/" + role,
         {"X-PHC-Role": next(r for r in sorted(presets)
                             if admin not in presets[r])},
         {"capabilities": []}),
        ("no such role", PREFIX + "/roles/surgeon", {}, {"capabilities": []}),
        ("not a capability of this bundle", PREFIX + "/roles/" + role, {},
         {"capabilities": [sorted(whole)[0] + ".typo"]}),
        ("a capability the embedded catalogue carries for ANOTHER bundle",
         PREFIX + "/roles/" + role, {}, {"capabilities": [wider[0]]}),
        ("every capability another bundle declares, at once",
         PREFIX + "/roles/" + role, {}, {"capabilities": wider}),
    ]
    for label, path, head, body in refusals:
        py = call(python, path, method="PUT", headers=head, body=body)
        gone = call(go, path, method="PUT", headers=head, body=body)
        assert py == gone, (label, py, gone)
        assert py[0] != 200, (label, py)
    ok("%s: and the %d ways a save is refused answer identically on both "
       "engines: not an administrator, no such role, a word that is no "
       "capability at all, and any of the %d the embedded catalogue carries "
       "for OTHER bundles but this one's %d do not include"
       % (shape, len(refusals), len(wider), len(whole)))

    # And a role saved with NOTHING, which is a deviation and not an absence.
    # Compared because the two are one byte apart on the wire -- [] and null --
    # and a role editor reading null concludes that a facility which deviated
    # all the way to nothing has not deviated at all, then restores the
    # preset on its next unrelated save.
    empty = {}
    for name, base in (("python", python), ("go", go)):
        empty[name] = call(base, PREFIX + "/roles/" + role, method="PUT",
                           body={"capabilities": []})
    assert empty["python"] == empty["go"], empty
    py_back = get(python, PREFIX + "/roles")
    go_back = get(go, PREFIX + "/roles")
    assert py_back == go_back, (
        "a role saved with nothing reads differently\npython: %s\ngo:     %s"
        % (json.dumps(py_back["overrides"], sort_keys=True),
           json.dumps(go_back["overrides"], sort_keys=True)))
    assert go_back["overrides"][role] == [], go_back["overrides"]
    assert get(go, PREFIX + "/whoami", header)["capabilities"] == [], \
        "a role saved with nothing still holds something"
    ok("%s: and a role saved with NOTHING reads back as a deviation holding an "
       "empty list rather than as no deviation at all, identically in both "
       "engines, and its caller then holds nothing" % shape)


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
    owed, verbs = [], []
    for route in sorted({r for r in get(python, "/")["routes"]
                         if r.startswith(PREFIX)}):
        # The templated ones cannot be asked without an id; the prefix is
        # enough, because the Go mounts a subtree.
        path = route.split("{")[0].rstrip("/")
        if path.endswith(tuple(SERVED) + SERVED_STAMPED + SERVED_TEMPLATED):
            continue
        if path[len(PREFIX):].startswith(WRITE_PATH):
            continue
        # The Go classifies the route, and then the Python is held to it.
        #
        # 501 means not ported, and that is the property this loop was written
        # for: the detail has to name the slice that will bring it, so the
        # difference between "not ported" and "no such route" is on the wire.
        #
        # 405 means the Go DOES serve it and GET is not its verb, which is
        # what a POST-only route answers -- the ask-and-search turn is one.
        # Then the only thing to hold is that the Python answers 405 too, so
        # the two engines agree about which verb the route takes. A route the
        # Go had not ported cannot reach this branch: it answers 501 and is
        # counted as owed, which is how /patients/publish stays covered.
        #
        # Derived this way rather than from a list of paths, because such a
        # list would have to spell the deprecated alias of the planner's
        # route, and scripts/check_khoj.py forbids naming that path in code
        # outside the alias itself.
        go_status, go_body = call(go, path)
        if go_status == 405:
            py_status, py_body = call(python, path)
            assert py_status == 405, (
                "%s: the Go serves GET %s as 405 and the Python answered "
                "%s %s" % (shape, path, py_status, str(py_body)[:300]))
            verbs.append(path[len(PREFIX):] or "/")
            continue
        assert go_status == 501, (
            "%s: GET %s answered %s on the Go, and an unported route must "
            "answer 501 %s" % (shape, path, go_status, str(go_body)[:300]))
        assert "does not serve" in go_body["detail"], go_body
        owed.append(path[len(PREFIX):] or "/")
    ok("%s: %d routes the Python serves answer 501 on the Go with the slice "
       "that will bring them, rather than 404, and %d POST-only routes answer "
       "405 on both rather than one engine calling them unported"
       % (shape, len(owed), len(verbs)))

    # --- and last, because it writes in-process state that every other
    # comparison above would then be reading: a facility's own role
    # combination. See roles().
    roles(shape, python, go)


# ---------------------------------------------------------------------------
# The mutation ledger for what G6 added: 21 applied, 20 caught, 1 not and fixed
# ---------------------------------------------------------------------------
#
# Each one was applied, PROVED applied before anything ran (the file changed,
# the replaced text was gone, the replacement was there, the replacement did
# not contain what it replaced, and git agreed), run through the whole of
# scripts/check.sh, reverted, and the revert proved byte clean against git.
# The gate stops at the first failure, so "first" is the gate's own order.
# Nineteen are Go only; the last two change BOTH engines.
#
# Six were caught by `go test ./...` in "== the MCP server ==", which is
# EARLIER in the gate than this file, because care_phc_mcp/fhir/fhir_test.go
# pins those facts from inside the package as well. That is a second net and
# it is named rather than hidden: a reader who sees only this ledger would
# otherwise think the diff caught them.
#
#  1. A section code drifts: ChiefComplaints carries MedicalHistory's.
#     -> the projection's declaration tables.
#  2. An observation with no status is given `final`.   -> go test ./fhir/.
#  3. An observation carrying a certainty R4 cannot express is projected
#     anyway, so a denied finding is published as a fact. -> go test ./fhir/.
#  4. A Condition's verificationStatus is pinned to confirmed.
#     -> the per-resource diff, on a condition row.
#  5. The narrative fallback declines EVERY row, which is the fallback that
#     promised three files and provided none.            -> go test ./fhir/.
#  6. A stored number is published as a quoted string.   -> go test ./fhir/.
#  7. A Practitioner id carries the login name instead of its hash.
#     -> the practitioners comparison.
#  8. A section reads only the FIRST row of each query.
#     -> the documents diff, the bundle's own declared consultation.
#  9. Only the first author met is collected.            -> the same.
# 10. An entryless section is published, so a heading claims nothing was
#     found rather than that nothing was looked for.     -> the same.
# 11. A Go engine file types a diagnosis code.
#     -> go_names_no_clinical_word(), which nothing held the Go to before.
# 12. A code with no system becomes a bare resolvable-looking coding, which
#     is CARE's own failure mode.                        -> go test ./fhir/.
# 13. The sections come out in reverse, which is what a Go map would do to
#     the ordered declaration.                           -> the documents diff.
# 14. The urn loses its namespace prefix.                -> the urns comparison.
# 15. BOTH engines' ChiefComplaints code drifts.
# 16. BOTH engines default an absent observation status to `final`.
# 17. A section query's `where` is dropped on the way to the store.
#     -> the documents diff, the two-section asking built for exactly this.
# 18. Document selects rows WITHOUT naming the thread.   -> NOT CAUGHT. See
#     below.
# 19. The narrative is projected with no document type, so the attachment
#     loses its title.                                   -> the documents diff.
# 20. The performer is dropped on the way into every resource, so the author
#     is on the Composition and on no resource.          -> the same.
# 21. The Composition's subject is read from the whole store rather than
#     this visit.                                        -> go test ./fhir/.
#
# THE HOLE THE MUTATIONS FOUND IN THIS CHECK
# ------------------------------------------
# 18 passed the whole gate at 843 ok. A `Document` that selected a section's
# rows without saying WHICH VISIT they belong to was indistinguishable from
# one that did, because both halves of this comparison -- RowsOnly here and
# `stub` in fhir/parity_test.go -- ignored the thread argument. In a clinic
# that is one patient's rows published inside another patient's record, and
# no literal anywhere was wrong: the two engines agreed.
#
# The CHECK was fixed and the mutation was kept. Neither stub implements the
# thread join, and neither should: the join is the adapter's (an encounter
# joins on its id, a patient through the encounter's own column) and it is
# compared over two REAL stores by write_path's walk. What they hold now is
# the narrower fact that a thread was passed and that it was this one. 18 was
# re-applied afterwards and fails in "== the MCP server ==".
#
# This is the third slice running whose missed property was not the one that
# looked risky. The section codes, the refusal sentences and the fan-out were
# all watched closely and all three were caught first time; what nobody was
# watching was the ARGUMENT, because a stand-in store is written to answer
# and not to refuse.
#
# TWO MUTATIONS WHERE BOTH ENGINES DRIFT TOGETHER, WHICH A DIFF CANNOT SEE
# ------------------------------------------------------------------------
# 15 and 16 were both caught, and NEITHER was caught here, which is the point
# of running them. 15 reached scripts/check_rx.py, which holds the section
# code against docs/superpowers/specs/2026-10-30-nrces-section-codes.md; 16
# reached `python3 -m kernel.fhir`, whose own demo asserts the refusal. So the
# Go side's section table and its status refusal are held to the standard
# through the PYTHON's literal checks plus this diff, and not by anything on
# the Go side alone. The day the Python goes (G9), those two literal checks
# have to go with it rather than be deleted with it.
#
# WHAT THIS COMPARISON CANNOT REACH, STATED RATHER THAN IMPLIED
# ------------------------------------------------------------
# - Row ORDER. The case file lists rows in the order the real store returns
#   them (`ORDER BY created_date, id`), so order is an input here. It is the
#   adapter's property and write_path's walk is where it is compared.
# - The 200 row ceiling per section query, for the same reason G3 could not
#   reach the expansion's: no table in this tree holds 200 rows of anything.
# - A stored value of "inf". Python's float() accepts it, so kernel/fhir.py
#   publishes `Infinity`, which is not JSON; Go's encoder refuses to marshal
#   it at all. The two engines genuinely differ and the case is NOT in the
#   numbers above, because adding it would break the Go transport rather than
#   compare anything. No questionnaire range admits it. Recorded, not fixed.
#
# ---------------------------------------------------------------------------
# The mutation ledger for what G4 added: 17 applied, 17 caught
# ---------------------------------------------------------------------------
#
# Each one was applied, PROVED applied before anything ran (the file changed,
# the replaced text was gone, the replacement was there, and git agreed), run
# through the whole of scripts/check.sh, reverted, and the revert proved clean
# against git. The gate stops at the first failure, so "first" is the gate's
# own order. Thirteen are Go only; the last two change BOTH engines.
#
#  1. The dashboard reads each metric's own window instead of the view's.
#     -> the views walk, phc.view.facility-dashboard.
#  2. A tasklist ignores its `not` clause entirely.      -> the views walk.
#  3. A tasklist's `not` tests only its FIRST member, which is the silent
#     half match.                                        -> the views walk.
#  4. `window.start` is not bound, so a metric compares a column against the
#     literal string.                                    -> the views walk.
#  5. The queue drops the trailing group for a finished thread.
#     -> roll_forward(), which asks for a queue before any shape does.
#  6. A queue row carries every subject field instead of the declared columns.
#     -> roll_forward().
#  7. A window reaches FORWARD instead of back.          -> the views walk.
#  8. A visit's `did` includes an operation that was only proposed.
#     -> the views walk, the spine of a seeded subject.
#  9. A timeline is oldest first.                        -> the same.
# 10. The seed's `same_patient_as` stops joining, so a returning patient is a
#     second person.                                     -> the same.
# 11. The roll forward loses its clamp and pushes rows into the future.
#     -> roll_forward().
# 12. The store stops rolling a stale demo day forward at all.
#     -> roll_forward().
# 13. The pending register reads flattened rows, so an unfilled column is ""
#     and not null.                                      -> stamped().
# 14. Every declared badge fires whether the row holds the flag or not.
#     -> roll_forward().
# 15. A summary's `actions` section is drawn for a caller holding nothing.
#     -> the views walk, phc.view.visit-summary with a thread.
#
# THE HOLE THE MUTATIONS FOUND IN THIS CHECK
# ------------------------------------------
# 9 and 10 were applied first against the scenario as it was originally
# built, and BOTH PASSED THE WHOLE GATE. The walk read the spine of the
# subject it had just registered, and that subject has exactly ONE visit, so
# neither the newest-first ordering nor the join had anything to be wrong
# about. bundles/phc/seed.yaml says so in its own words at the thread that
# declares `same_patient_as` ("a spine with one visit per person proves
# nothing"), and the check had to be told to walk the SEEDED subjects before
# either mutation could fail. The property beside them now refuses a run in
# which every subject read has one visit.
#
# TWO MUTATIONS WHERE BOTH ENGINES DRIFT TOGETHER, WHICH A DIFF CANNOT SEE
# ------------------------------------------------------------------------
# 16. BOTH engines read each metric's own window instead of the view's.
# 17. BOTH engines drop the tasklist's `not` clause.
# Both were caught, and NEITHER was caught here. The gate reached
# kernel/tests/test_kernel.py first, where
# test_a_dashboard_evaluates_every_metric_locally and
# test_a_tasklist_not_clause_excludes_a_thread_that_has_consented already pin
# exactly those two facts. So the properties this slice added beside the diff
# — the view's window winning, and each tasklist predicate recomputed from the
# flags the kernel derived — are a SECOND net, and they are recorded as
# unproved by mutation rather than claimed: every mutation that would reach
# them is caught earlier by a named Python test. They are kept because the day
# a bundle grows a view the Python has no hand written test for, they are what
# is left. The same is true of the spine properties, which kernel/tests/
# test_spine.py pins from the other side.
#
# Two mutations were REFUSED BEFORE THEY RAN, both the substring trap in the
# direction that matters: the first spellings of 3 and 8 left the text they
# replaced in the file, so they would have run, passed, and been recorded as
# mutations that proved nothing. The harness asserts the old text is gone
# BEFORE it writes, which also matters: an earlier spelling wrote the file and
# then raised, and the next mutation built on a dirty tree and reported a
# false "not caught".
#
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
