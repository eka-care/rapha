"""Load and lint a declaration bundle into the dataclasses in contracts.py.

catalogue/build.py lints and compiles the operation atoms. This is the same
job for the other four declaration types, and it is deliberately the same
shape: parse() from build.py reads the file, vocab.py owns every closed list,
and a dangling reference is a build failure and not a warning. A capability
misspelt in frontmatter is not a typo, it is a screen nobody can open or one
anybody can.

`documents` is the exception, and for the reason kernel/mapping.py gives for
its own: it is not compiled into catalogue.json. Nothing outside the kernel
projects a document, the Go server proposes only, and the renderer must never
learn a section heading. Add it to the compiled artifact when an out of
process consumer needs it.

compile_json() returns exactly the five new catalogue.json keys, so the
compiler can stay one writer: build.py adds them with one update() call and
keeps writing the file. Until it does, the kernel loads declarations from
bundles/<id>/ directly, which is the same data by the same lint.

Pure: reads files, touches no database and no network.
"""
from __future__ import annotations

import dataclasses
import pathlib
from typing import Optional

import yaml

from catalogue import guard, validate, vocab
from catalogue.build import parse
from kernel import contracts as c
from kernel import fhir
from kernel import mapping
from kernel import plugins
from kernel import templates

ROOT = pathlib.Path(__file__).parents[1]
BUNDLES = ROOT / "bundles"

REQUIRED = {
    "workflow": ("id", "type", "title", "summary", "subject", "steps", "states"),
    "view": ("id", "type", "title", "summary", "kind", "capability"),
    "instrument": ("id", "type", "title", "summary", "kind", "operations",
                   "readback", "commit", "fallback"),
    "metric": ("id", "type", "title", "summary", "unit", "window", "numerator"),
}
BADGE_STYLES = ("warn", "crit", "ok", "mute")
RULE_FORMS = ("stored", "exists", "gte", "all_of")


class DeclarationError(Exception):
    """Raised with every failure, one per line. Never partial-load a bundle."""


@dataclasses.dataclass(frozen=True)
class Bundle:
    """One loaded declaration package. `operations` are the compiled entries
    catalogue.json already holds; the kernel does not recompile them.

    `seed` is the facility's own demo day, read from bundles/<id>/seed.yaml,
    and it defaults to none. It is fixture data and not a declaration: the
    adapter writes it, the renderer never sees it, and it stays out of
    catalogue.json. It lives here because a seed speaks a facility's words,
    and one kept in the adapter put six outpatients on a laboratory's bench.
    """
    manifest: c.Manifest
    operations: dict
    workflows: dict
    views: dict
    instruments: dict
    metrics: dict
    seed: list = dataclasses.field(default_factory=list)
    scribe: dict = dataclasses.field(default_factory=dict)
    documents: dict = dataclasses.field(default_factory=dict)
    instruments_raw: list = dataclasses.field(default_factory=list)
    # Which shape of this facility the kernel is running, and the one dict
    # that is the whole of its runtime effect: {capability: the plugin id
    # withholding it}. See kernel/plugins.py. None and {} for a bundle that
    # declares no facilities, which is what keeps bundles/lab untouched.
    facility: Optional[str] = None
    withheld: dict = dataclasses.field(default_factory=dict)
    # The same fact in the words a person reads: {plugin id: its declared
    # title} for what this centre does not run. Served at GET /facility so a
    # screen can explain a switch it has disabled. See kernel/plugins.absent.
    without: dict = dataclasses.field(default_factory=dict)
    # The DECLARATIONS the three fields above are derived from, carried
    # through to catalogue.json unresolved: {plugin id: its declaration} and
    # {facility id: its declaration} as bundle.yaml wrote them, plus this
    # bundle's own vocabulary.
    #
    # Here because an engine that is not this one has to be able to answer
    # GET /facility, and the three resolved fields above are PHC_FACILITY's
    # answer for one process rather than the bundle's own words. Carrying the
    # declarations means the shape is chosen at runtime by whichever engine is
    # running, from the same line of YAML, instead of being compiled in. They
    # are shape independent on purpose: scripts/check_plugins.py asserts the
    # compiled catalogue is byte identical across all three shapes of one
    # bundle, and that stays true because nothing resolved is added here.
    plugins: dict = dataclasses.field(default_factory=dict)
    # {default: the shape bundle.yaml's own `facility:` picks, declared:
    # {facility id: its declaration}}. The default is carried beside the
    # shapes it chooses between rather than on the manifest, because it is
    # only meaningful against them: kernel/plugins.chosen() reads the
    # argument, then PHC_FACILITY, then this.
    facilities: dict = dataclasses.field(default_factory=dict)
    # {capabilities, roles, states} for the bundle this build loaded. The
    # catalogue wide `capabilities`, `bundles` and `states` keys are the UNION
    # over every bundle, because the Go MCP server embeds the whole file and
    # narrows at runtime; api/main.py has always overridden them per bundle
    # when it serves /catalogue, from catalogue/vocab.py's module constants.
    # This is that same narrowing, written down rather than recomputed by
    # every reader that is not the Python.
    vocabulary: dict = dataclasses.field(default_factory=dict)

    def workflow(self, wid: Optional[str] = None) -> c.Workflow:
        if wid is None:
            (wid,) = self.workflows
        return self.workflows[wid]


def load_seed(path):
    """The threads bundles/<id>/seed.yaml declares, or none.

    A bundle need not have one. No seed is not an error and not an empty
    screen worth apologising for: it is a facility whose demo day has not
    been written, and the kernel starts with an empty queue.
    """
    f = pathlib.Path(path) / "seed.yaml"
    if not f.exists():
        return []
    return list((yaml.safe_load(f.read_text()) or {}).get("threads") or [])


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------

def _query(q, where, fail, *, resources, allow_window):
    """Validate one Query. `where` is the label used in failure messages."""
    if not isinstance(q, dict) or "resource" not in q:
        return fail(f"{where}: not a query")
    if q["resource"] not in resources:
        fail(f"{where}: unknown resource '{q['resource']}'")
    for key in set(q) - {"resource", "where"}:
        fail(f"{where}: unknown query key '{key}'")
    for fld, cond in (q.get("where") or {}).items():
        if not isinstance(cond, dict):
            continue                                  # a literal, or "*"
        for op, val in cond.items():
            if op not in ("gte", "lt"):
                fail(f"{where}: unknown condition '{op}' on {fld}")
            if val == "window.start" and not allow_window:
                fail(f"{where}: window.start is only for a metric")


def _rule(flag, rule, seen, fail, stored):
    if not isinstance(rule, dict) or len(rule) != 1:
        return fail(f"state '{flag}': a rule is one of {RULE_FORMS}")
    (form, arg), = rule.items()
    if form not in RULE_FORMS:
        return fail(f"state '{flag}': unknown rule form '{form}'")
    q = dict(resources=vocab.CARE_RESOURCES, allow_window=False)
    if form == "stored":
        if arg is not True:
            fail(f"state '{flag}': stored takes true")
        stored.append(flag)
    elif form == "exists":
        _query(arg, f"state '{flag}'", fail, **q)
    elif form == "gte":
        if not isinstance(arg, list) or len(arg) != 2:
            return fail(f"state '{flag}': gte takes exactly two queries")
        for side in arg:
            _query(side, f"state '{flag}'", fail, **q)
    elif form == "all_of":
        if not isinstance(arg, list) or not arg:
            return fail(f"state '{flag}': all_of takes a non empty list")
        for item in arg:
            if isinstance(item, str):
                ref = item[4:] if item.startswith("not ") else item
                if ref not in seen:
                    fail(f"state '{flag}': references '{ref}' before it is declared")
            else:
                _rule(flag, item, seen, fail, [])


def _lint_workflow(fm, ops, fail, voc):
    if fm["subject"] not in vocab.CARE_RESOURCES:
        fail(f"subject '{fm['subject']}' is not a CARE resource")

    # `spine` names both a resource and the field on `subject` that points at
    # it. Optional; a workflow without one has no continuing subject and the
    # spine route answers 404 for it, which is the honest answer rather than
    # a guess at which field means "the same person again".
    if fm.get("spine") is not None:
        if fm["spine"] not in vocab.CARE_RESOURCES:
            fail(f"spine '{fm['spine']}' is not a CARE resource")
        elif fm["spine"] == fm["subject"]:
            fail(f"spine '{fm['spine']}' is the subject itself, so it joins nothing")

    states = fm["states"] or {}
    if set(states) != set(voc.states):
        missing = sorted(set(voc.states) - set(states))
        extra = sorted(set(states) - set(voc.states))
        fail(f"states must cover this bundle's vocabulary exactly: "
             f"missing {missing}, unknown {extra}")

    for step in fm["steps"] or []:
        for key in ("station", "done_when"):
            if key not in step:
                fail(f"step {step} has no '{key}'")
        if step.get("station") not in voc.stations:
            fail(f"unknown station '{step.get('station')}'")
        for key in ("done_when", "applies_when"):
            flag = step.get(key)
            if flag is not None and flag not in voc.states:
                fail(f"step {step.get('station')}: {key} names unknown state '{flag}'")
        for oid in step.get("operations") or []:
            if oid not in ops:
                fail(f"step {step.get('station')}: operation '{oid}' does not exist")
            elif ops[oid]["station"] != step.get("station"):
                fail(f"'{oid}' is drawn at {step.get('station')} but declares "
                     f"station {ops[oid]['station']}")

    seen, stored = [], []
    for flag, rule in states.items():
        _rule(flag, rule, seen, fail, stored)
        seen.append(flag)
    return stored


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _lint_view(fm, refs, fail, voc, ops):
    if fm["kind"] not in c.VIEW_KINDS:
        fail(f"kind must be one of {c.VIEW_KINDS}")
    if fm["capability"] not in voc.capabilities:
        fail(f"unknown capability '{fm['capability']}'")
    if fm.get("scope", "today") not in c.VIEW_SCOPES:
        fail(f"scope must be one of {c.VIEW_SCOPES}")
    if fm.get("window", "day") not in c.METRIC_WINDOWS:
        fail(f"window must be one of {c.METRIC_WINDOWS}")

    if fm["kind"] == "dashboard":
        for mid in fm.get("metrics") or []:
            if mid not in refs["metric"]:
                fail(f"dashboard names metric '{mid}' which does not exist")
    else:
        if fm.get("workflow") not in refs["workflow"]:
            fail(f"{fm['kind']} view names workflow '{fm.get('workflow')}' which does not exist")

    group_by = fm.get("group_by")
    if group_by is not None and group_by != "station" and group_by not in voc.states:
        fail(f"group_by '{group_by}' is neither 'station' nor a state")
    for flag, style in (fm.get("badges") or {}).items():
        if flag not in voc.states:
            fail(f"badge names unknown state '{flag}'")
        if style not in BADGE_STYLES:
            fail(f"badge style '{style}' must be one of {BADGE_STYLES}")

    if fm["kind"] == "tasklist":
        for task in fm.get("tasks") or []:
            title = task.get("title", "?")
            if "title" not in task or "where" not in task:
                fail(f"task '{title}' needs 'title' and 'where'")
                continue
            where = task["where"]
            if not isinstance(where, dict) or "flag" not in where:
                fail(f"task '{title}': where needs a 'flag'")
            else:
                for key in ("flag", "not"):
                    for flag in _as_list(where.get(key)):
                        if flag not in voc.states:
                            fail(f"task '{title}': where names unknown state '{flag}'")
            op = task.get("operation")
            if op is not None and op not in ops:
                fail(f"task '{title}': operation '{op}' does not exist")

    for section in fm.get("sections") or []:
        title = section.get("title", "?")
        if (section.get("show") is None) == (section.get("resource") is None):
            fail(f"section '{title}' needs exactly one of show or resource")
        if section.get("show") is not None and section["show"] not in c.SUMMARY_SHOW:
            fail(f"section '{title}': show must be one of {c.SUMMARY_SHOW}")
        if section.get("resource") is not None:
            _query({"resource": section["resource"], "where": section.get("where") or {}},
                   f"section '{title}'", fail,
                   resources=vocab.CARE_RESOURCES, allow_window=False)


def _lint_instrument(fm, ops, fail, voc):
    if fm["kind"] not in c.INSTRUMENT_KINDS:
        fail(f"kind must be one of {c.INSTRUMENT_KINDS}")
    # The gate, if there is one, is this bundle's own flag. A typo here would
    # otherwise be a gate that never opens, which looks exactly like an
    # instrument that is simply never offered.
    if fm.get("requires") is not None and fm["requires"] not in voc.states:
        fail(f"requires '{fm['requires']}' is not one of this bundle's states")
    # The ambient speech rule, made unwritable. See kernel/DECLARATIONS.md 4.
    if fm["readback"] != "required":
        fail("readback must be 'required': a captured value is always shown back")
    if fm["commit"] != "tap":
        fail("commit must be 'tap': no instrument is a commit path")
    if fm["fallback"] not in ("keypad", "form", "text"):
        fail("fallback must be 'keypad', 'form' or 'text'")
    if fm["kind"] == "constrained-voice" and fm.get("grammar") not in c.VOICE_GRAMMARS:
        fail(f"constrained-voice needs a grammar from {c.VOICE_GRAMMARS}")
    if fm["kind"] == "spoken-prompt":
        # `spoken` is the facility's off switch: true speaks the line, false
        # renders it on screen instead. Either way `says` is what gets shown
        # or said, so an empty one is refused regardless of which way the
        # switch is set, not just when it happens to be off today.
        if not (fm.get("says") or "").strip():
            fail("a spoken-prompt with no `says` has nothing to fall back to "
                 "when a facility turns the voice off, whether `spoken` is "
                 "true or false")

    link_ids = set()
    for oid in fm["operations"] or []:
        if oid not in ops:
            fail(f"names operation '{oid}' which does not exist")
            continue
        link_ids |= {f["link_id"] for f in ops[oid]["fields"]}
    for field in fm.get("fields") or []:
        if field not in link_ids:
            fail(f"field '{field}' is not a question on any of its operations")
    for qtype in fm.get("types") or []:
        if qtype not in validate.TYPES:
            fail(f"question type '{qtype}' is not a CARE type")


def _lint_scribe(manifest, instruments):
    """Every station default and choice is an operation a scribe may fill."""
    allowed = {oid for fm in instruments if fm.get("kind") == "scribe"
               for oid in fm.get("operations") or []}
    stations = set(manifest.get("stations") or [])
    bad = []
    for station, cfg in (manifest.get("scribe") or {}).items():
        if stations and station not in stations:
            bad.append(f"bundle.yaml scribe: '{station}' is not a station")
        choose = list(cfg.get("choose") or [])
        for oid in choose + ([cfg["default"]] if cfg.get("default") else []):
            if oid not in allowed:
                bad.append(f"bundle.yaml scribe.{station}: '{oid}' is not in a scribe "
                           "instrument's operations")
        if cfg.get("default") and cfg["default"] not in choose:
            bad.append(f"bundle.yaml scribe.{station}: default must be one of choose")
    return bad


def _lint_documents(manifest, ops):
    """Every ABDM document this facility publishes, against ABDM's own grammar.

    Where a row goes in a published document is a declaration: ABDM names the
    section slices and fixes their codes, and this bundle says what it files
    under each. It was typed at three call sites instead, which is how the
    same diagnosis came to be filed under Chief complaints in one check and
    under Medical History in another.

    Four failures, each one a document a gateway would reject or a record
    filed under the wrong heading:

    - a profile this build does not emit. kernel/fhir.PROFILES is the whole
      of what it emits, and its table is the NRCeS one.
    - a section slice the profile does not declare, or one whose code NRCeS
      has not published. Both are absent from that profile's section table,
      which is why one check covers them: a slice with no published code
      cannot be matched by a reader, and the nearest code that looks close is
      how a record gets filed under the wrong heading.
    - a resource with no FHIR projection, which would publish something else.
    - a resource no operation in this bundle writes, so the section can never
      have anything in it. The same per bundle closure the capabilities and
      the stations get.
    """
    bad = []
    written = {r for oid in manifest.get("operations") or []
               for r in (ops.get(oid, {}).get("writes") or [])}
    for did, doc in (manifest.get("documents") or {}).items():
        where = f"bundle.yaml documents.{did}"
        for key in sorted(set(doc) - {"profile", "sections"}):
            bad.append(f"{where}: unknown key '{key}'")
        profile = doc.get("profile")
        if profile not in fhir.PROFILES:
            bad.append(f"{where}: '{profile}' is not a profile this build emits; "
                       f"it emits {sorted(fhir.PROFILES)}")
            continue
        slices = fhir.sections(profile)
        if not doc.get("sections"):
            bad.append(f"{where}: declares no section, and every profile "
                       f"requires at least one")
        for slice_name, queries in (doc.get("sections") or {}).items():
            if slice_name not in slices:
                bad.append(f"{where}: {profile} declares no section "
                           f"'{slice_name}'; it has {sorted(slices)}")
                continue
            for q in queries or []:
                if not isinstance(q, dict) or "resource" not in q:
                    bad.append(f"{where}.{slice_name}: not a query")
                    continue
                for key in sorted(set(q) - {"resource", "where"}):
                    bad.append(f"{where}.{slice_name}: unknown query key '{key}'")
                resource = q["resource"]
                if resource not in fhir.PROJECTIONS:
                    bad.append(f"{where}.{slice_name}: no FHIR projection for a "
                               f"'{resource}' row, so the section would publish "
                               f"something else")
                elif resource not in written:
                    bad.append(f"{where}.{slice_name}: no operation this bundle "
                               f"loads writes a '{resource}' row, so the section "
                               f"can never have anything in it")
    return bad


def _documents(manifest):
    """The declared documents as kwargs for kernel/fhir.document().

    The compiled shape is the projection's own argument names, so a caller
    says `fhir.document(store, thread, now=..., **bundle.documents[id])` and
    cannot retype a placement on the way.
    """
    out = {}
    for did, doc in (manifest.get("documents") or {}).items():
        out[did] = {
            "profile": doc["profile"],
            "sections_wanted": {
                name: [(q["resource"], dict(q.get("where") or {}))
                       for q in queries or []]
                for name, queries in (doc.get("sections") or {}).items()},
        }
    return out


def _lint_metric(fm, fail):
    if fm["unit"] not in c.METRIC_UNITS:
        fail(f"unit must be one of {c.METRIC_UNITS}")
    if fm["window"] not in c.METRIC_WINDOWS:
        fail(f"window must be one of {c.METRIC_WINDOWS}")
    # thread_flag is countable and never writable: a metric numerator is the
    # only place a kernel resource may appear.
    _query(fm["numerator"], "numerator", fail,
           resources=vocab.CARE_RESOURCES | vocab.KERNEL_RESOURCES, allow_window=True)
    den = fm.get("denominator")
    if (den is None) != (fm["unit"] == "count"):
        fail("a count has no denominator; a percent or ratio needs one")
    if den is not None:
        _query(den, "denominator", fail,
               resources=vocab.CARE_RESOURCES, allow_window=True)


def _lint_seed(threads, manifest, voc, ops):
    """Check the demo day against the facility's own words.

    The one failure this exists for: a seeded proposal naming an operation
    the bundle does not load. That is what put a pending Amoxicillin on a
    laboratory thread, drawn as an agent card the kernel would then 404.

    The second: an audit line whose payload does not answer that operation's
    own questionnaire. The thread draws a posted card's values from it, so a
    key that is not a link_id renders as a raw identifier and no key at all
    renders as a card with nothing in it. The health centre's seed had no
    payloads for a while and every demo thread read "Nothing has been recorded
    on this visit yet" over three ticked steps.
    """
    bad, seen = [], set()
    for i, t in enumerate(threads or []):
        where = "seed.yaml thread %d" % (i + 1)
        if not isinstance(t, dict) or not t.get("id"):
            bad.append(f"{where}: needs an 'id'")
            continue
        where = "seed.yaml '%s'" % t["id"]
        if t["id"] in seen:
            bad.append(f"{where}: two threads share this id")
        seen.add(t["id"])
        for key in set(t) - {"id", "token", "status", "patient", "rows",
                             "flags", "proposals", "audit", "minutes_ago",
                             "same_patient_as"}:
            bad.append(f"{where}: unknown key '{key}'")
        if "minutes_ago" in t and not isinstance(t["minutes_ago"], (int, float)):
            bad.append(f"{where}: minutes_ago must be a number")
        if "same_patient_as" in t:
            if "patient" in t:
                bad.append(f"{where}: has both 'patient' and 'same_patient_as'; "
                           "a returning visit does not re-register the person")
            elif t["same_patient_as"] not in seen:
                bad.append(f"{where}: same_patient_as '{t['same_patient_as']}' "
                           "is not an earlier thread in this file")
        for row in t.get("rows") or []:
            if not isinstance(row, dict) or "resource" not in row:
                bad.append(f"{where}: a row needs a 'resource'")
            elif row["resource"] not in vocab.CARE_RESOURCES:
                bad.append(f"{where}: unknown resource '{row['resource']}'")
        for flag in t.get("flags") or []:
            if flag not in voc.states:
                bad.append(f"{where}: flag '{flag}' is not this bundle's vocabulary")
        for entry in (t.get("proposals") or []) + (t.get("audit") or []):
            op = entry.get("operation")
            if op not in (manifest["operations"] or []):
                bad.append(f"{where}: names operation '{op}', which this bundle "
                           f"does not load")
                continue
            bad += _lint_seed_payload(where, op, entry.get("payload") or {}, ops)
    return bad


def _lint_seed_payload(where, op, payload, ops):
    """Every key a seeded payload carries answers a question that operation's
    questionnaire declares. An empty payload is allowed on a proposal, which is
    a machine that filled in nothing; on an audit line it is a posted card with
    no values under its title, so it is refused."""
    schema_id = (ops.get(op) or {}).get("input")
    if not schema_id:
        return []
    try:
        asked = {q["link_id"] for q in validate.walk(validate.load(schema_id)["questions"])}
    except (FileNotFoundError, KeyError):
        return []  # the missing questionnaire is already a failure of its own
    return [f"{where}: '{op}' payload answers '{k}', which "
            f"{schema_id} does not ask" for k in sorted(set(payload) - asked)]


def lint(manifest, decls, ops, seed=()):
    """Return a list of failure strings. Empty means the bundle is sound.

    `decls` is {id: (frontmatter, body)} for the bundle directory, `ops` the
    compiled operations from catalogue.json.
    """
    bad = []
    refs = {t: {i for i, (fm, _) in decls.items() if fm.get("type") == t}
            for t in c.DECLARATION_TYPES}
    stored_by_workflow = {}

    for key in ("id", "version", "title", "stations", "states", "capabilities",
                "roles", "operations", "workflows", "views", "instruments", "metrics"):
        if key not in manifest:
            bad.append(f"bundle.yaml: missing '{key}'")
    if bad:
        return bad

    # This bundle's own closed vocabulary. Everything below is checked against
    # it and not against a union: a laboratory that can reach a PHC's flags is
    # how a released report came to be called `dispensed.complete`.
    voc = vocab.from_manifest(manifest)
    bad += voc.problems()
    bad += _lint_seed(seed, manifest, voc, ops)

    listed = {i for k in ("workflows", "views", "instruments", "metrics")
              for i in manifest[k] or []}
    for i in sorted(listed - set(decls)):
        bad.append(f"bundle.yaml: lists '{i}' but there is no such declaration file")
    for i in sorted(set(decls) - listed):
        bad.append(f"bundle.yaml: '{i}' is in the directory but not listed")
    for oid in manifest["operations"] or []:
        if oid not in ops:
            bad.append(f"bundle.yaml: operation '{oid}' is not in the catalogue")
            continue
        # The per bundle closure. catalogue/build.py linted this atom against
        # every bundle's words at once, because catalogue/ops is shared; here
        # is where an atom belonging to another facility is caught.
        op = ops[oid]
        if op["capability"] not in voc.capabilities:
            bad.append(f"{oid}: capability '{op['capability']}' is not this "
                       f"bundle's vocabulary")
        if op["station"] not in voc.stations:
            bad.append(f"{oid}: station '{op['station']}' is not this bundle's line")
        for pre in op.get("preconditions") or []:
            kind, name, _ = guard.parse_precondition(pre)
            if kind == "actor":
                if name not in (manifest["operations"] or []):
                    bad.append(f"{oid}: precondition names '{name}', which this "
                               f"bundle does not load, so the rule can never fire")
            elif name not in voc.states:
                bad.append(f"{oid}: precondition names state '{name}', which is "
                           f"not this bundle's vocabulary")
        for flag in op.get("emits") or []:
            if flag not in voc.states:
                bad.append(f"{oid}: emits '{flag}', which is not this bundle's "
                           f"vocabulary")

    for did, (fm, body) in sorted(decls.items()):
        def fail(msg, did=did):
            bad.append(f"{did}: {msg}")

        kind = fm.get("type")
        if kind not in REQUIRED:
            fail(f"type must be one of {tuple(REQUIRED)}")
            continue
        for key in REQUIRED[kind]:
            if key not in fm:
                fail(f"missing required field '{key}'")
        if any(f"{did}: missing required" in line for line in bad):
            continue
        if "## In plain words" not in body:
            fail("body must start with '## In plain words'")
        if "—" in body or "—" in str(fm):
            fail("em dash: the writing guide forbids it")

        if kind == "workflow":
            stored_by_workflow[did] = _lint_workflow(fm, ops, fail, voc)
        elif kind == "view":
            _lint_view(fm, refs, fail, voc, ops)
        elif kind == "instrument":
            _lint_instrument(fm, ops, fail, voc)
        elif kind == "metric":
            _lint_metric(fm, fail)

    return bad


# --------------------------------------------------------------------------
# compile
# --------------------------------------------------------------------------

def _workflow(fm, stored):
    return c.Workflow(
        id=fm["id"], title=fm["title"], summary=fm["summary"].strip(),
        subject=fm["subject"], spine=fm.get("spine"), states=fm["states"], stored=stored,
        steps=[c.Step(station=s["station"], done_when=s["done_when"],
                      applies_when=s.get("applies_when"),
                      operations=list(s.get("operations") or []))
               for s in fm["steps"]])


def _view(fm):
    known = {f.name for f in dataclasses.fields(c.View)}
    kwargs = {k: v for k, v in fm.items() if k in known and k not in ("sections", "tasks")}
    kwargs["summary"] = fm["summary"].strip()
    kwargs["sections"] = [c.Section(**s) for s in fm.get("sections") or []]
    kwargs["tasks"] = [c.Task(**t) for t in fm.get("tasks") or []]
    return c.View(**kwargs)


def _plain(cls, fm):
    known = {f.name for f in dataclasses.fields(cls)}
    return cls(**{**{k: v for k, v in fm.items() if k in known},
                  "summary": fm["summary"].strip()})


def load(bundle_id="phc", catalogue=None, facility=None):
    """Parse, lint and compile bundles/<bundle_id>/. Raises DeclarationError.

    `facility` picks which of the bundle's declared shapes to run, overriding
    PHC_FACILITY and the bundle's own `facility:` default. Which plugins a
    centre runs is resolved here, once, so that everything downstream reads
    one narrowed capability set rather than asking a config question of its
    own. See kernel/plugins.py.
    """
    import json
    if catalogue is None:
        catalogue = json.loads((ROOT / "catalogue" / "catalogue.json").read_text())
    ops = catalogue["operations"]

    path = BUNDLES / bundle_id
    manifest = yaml.safe_load((path / "bundle.yaml").read_text())
    decls = {}
    for f in sorted(path.glob("*.md")):
        fm, body = parse(f)
        if fm.get("id") != f.stem:
            raise DeclarationError(f"{f.name}: id '{fm.get('id')}' does not match filename")
        decls[fm["id"]] = (fm, body)

    # Which answer becomes which column lives on the operation atom, so it is
    # linted here with everything else that references a questionnaire, and
    # attached to the operations this bundle loads. See kernel/mapping.py.
    # This facility's demo day, which is a shorter one at a centre that runs
    # fewer plugins: a seeded thread whose history names an operation nobody
    # here may perform is a lie about what happened here.
    held_back = plugins.withheld(manifest, facility)
    seed = plugins.seeded(load_seed(path), ops, held_back)
    mappings, bad_mappings = mapping.load()
    bad = lint(manifest, decls, ops, seed) + bad_mappings
    raw_instruments = [fm for fm, _ in decls.values() if fm.get("type") == "instrument"]
    bad += _lint_scribe(manifest, raw_instruments)
    bad += _lint_documents(manifest, ops)
    # The doctor's templates, which are generated operations. Linted here with
    # everything else that references a questionnaire, and against the
    # declarations that have to offer them: the per bundle closure above
    # already holds a template's inherited capability and station, and this
    # holds its narrowing, its bindings and the files it generated.
    bad += templates.lint(manifest, ops, decls)
    # Which plugins this centre runs. Linted here with everything else that
    # groups this bundle's own words, and against the workflow, because the
    # failure worth refusing is a choice that stops the line: a step nothing
    # left can close and nothing can skip.
    bad += plugins.lint(manifest, ops, decls)
    if bad:
        raise DeclarationError("\n".join(bad))

    workflows, views, instruments, metrics = {}, {}, {}, {}
    for did, (fm, _) in decls.items():
        if fm["type"] == "workflow":
            workflows[did] = _workflow(fm, [f for f, r in fm["states"].items()
                                            if r == {"stored": True}])
        elif fm["type"] == "view":
            views[did] = _view(fm)
        elif fm["type"] == "instrument":
            instruments[did] = _plain(c.Instrument, fm)
        elif fm["type"] == "metric":
            metrics[did] = _plain(c.Metric, fm)

    return Bundle(
        manifest=c.Manifest(id=manifest["id"], version=str(manifest["version"]),
                            title=manifest["title"],
                            **{k: list(manifest[k] or []) for k in
                               ("operations", "workflows", "views", "instruments", "metrics")}),
        operations={oid: dict(ops[oid], mapping=mappings.get(oid, []))
                    for oid in manifest["operations"]},
        workflows=workflows, views=views, instruments=instruments, metrics=metrics,
        seed=seed, scribe=dict(manifest.get("scribe") or {}),
        documents=_documents(manifest), instruments_raw=raw_instruments,
        facility=plugins.chosen(manifest, facility), withheld=held_back,
        without=plugins.absent(manifest, facility),
        plugins=plugins.declared(manifest),
        facilities={"default": manifest.get("facility"),
                    "declared": plugins.facilities(manifest)},
        vocabulary=_vocabulary(manifest["id"]))


def _vocabulary(bundle_id):
    """{capabilities, roles, states} for one bundle, from its own bundle.yaml.

    Not the module level vocab.CAPABILITIES, which is PHC_BUNDLE's: a caller
    may load a bundle that is not the active one, and scripts/check_plugins.py
    does exactly that.
    """
    v = vocab.for_bundle(bundle_id)
    return {"capabilities": sorted(v.capabilities),
            "roles": {role: list(caps) for role, caps in dict(v.roles).items()},
            "states": sorted(v.states)}


def compile_json(bundle):
    """The loaded bundle's catalogue.json keys, as plain JSON-able dicts.
    build.py can add them with one update(); the four catalogue wide keys do
    not change. kernel/contracts.BUNDLE_KEYS is the list, and a new key
    belongs there and nowhere else."""
    return {
        "manifest": dataclasses.asdict(bundle.manifest),
        "workflows": {k: dataclasses.asdict(v) for k, v in bundle.workflows.items()},
        "views": {k: dataclasses.asdict(v) for k, v in bundle.views.items()},
        "instruments": {k: dataclasses.asdict(v) for k, v in bundle.instruments.items()},
        "metrics": {k: dataclasses.asdict(v) for k, v in bundle.metrics.items()},
        "scribe": bundle.scribe,
        # The unresolved declarations a second engine needs to answer
        # GET /facility for itself. See the Bundle fields.
        "plugins": bundle.plugins,
        "facilities": bundle.facilities,
        "vocabulary": bundle.vocabulary,
    }


def write_catalogue(bundle):
    """Merge the five declaration keys into the catalogue.json that
    catalogue/build.py just wrote, and into the copy the Go server embeds.

    This runs here and not in build.py because the layering only goes one way:
    kernel imports catalogue, so catalogue importing kernel.declarations back
    would be a circular import. Run build first, then this; check.sh does.
    """
    import json
    out = ROOT / "catalogue" / "catalogue.json"
    cat = json.loads(out.read_text())
    cat.update(compile_json(bundle))
    # The four original keys stay catalogue wide, because `operations` is: the
    # Go server embeds every bundle's atoms and narrows at runtime by asking
    # the kernel which bundle it loaded (/facility), and its own test asserts
    # that `capabilities` covers every operation it holds. So capabilities,
    # bundles and states here are the union that catalogue/build.py wrote, and
    # the five keys added above are the one loaded bundle's. The API is the
    # place that answers per bundle: it serves vocab for the bundle it loaded.
    blob = json.dumps(cat, indent=2, sort_keys=True) + "\n"
    out.write_text(blob)
    (ROOT / "care_phc_mcp" / "catalogue.json").write_text(blob)
    return sorted(compile_json(bundle))


def main():
    import json
    import sys
    named = [a for a in sys.argv[1:] if not a.startswith("-")]
    try:
        bundle = load(named[0] if named else "phc")
    except DeclarationError as e:
        for line in str(e).splitlines():
            print(f"FAIL {line}")
        return 1
    if "--json" not in sys.argv:
        print("ok   catalogue.json now carries %s" % ", ".join(write_catalogue(bundle)))
    print("ok   %d records mapped from %d operations' answers to their columns"
          % (sum(len(op["mapping"]) for op in bundle.operations.values()),
             sum(1 for op in bundle.operations.values() if op["mapping"])),
          file=sys.stderr if "--json" in sys.argv else sys.stdout)
    print(f"ok   bundle {bundle.manifest.id} {bundle.manifest.version}: "
          f"{len(bundle.operations)} operations, {len(bundle.workflows)} workflows, "
          f"{len(bundle.views)} views, {len(bundle.instruments)} instruments, "
          f"{len(bundle.metrics)} metrics, {len(bundle.seed)} seeded threads", file=sys.stderr if "--json" in sys.argv else sys.stdout)
    if "--json" in sys.argv:
        print(json.dumps(compile_json(bundle), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
