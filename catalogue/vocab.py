"""Vocabularies. The kernel's are here; a facility's own are in its bundle.

Two kinds of list were mixed in this file until now, and the mixing is what
made a laboratory's draw room called `nurse`:

  - the grammar the kernel and the adapter speak (which resources exist, what
    irreversibility means, which instrument kinds there are). Universal: an
    adapter has one set of tables whatever bundle is loaded, and the guard has
    one meaning for "irreversible". These stay below, each with the reason it
    survived.
  - the words a facility uses for its own line: stations, state flags,
    capabilities and role bundles. A primary health centre has a pharmacy and
    a laboratory has a bench, and neither of them is a subset of the other.
    Those now live in `bundles/<id>/bundle.yaml` and are closed PER BUNDLE:
    `for_bundle("lab")` is the whole of what a lab declaration may name.

Nothing here may be extended by an atom: a capability, state or resource that
is not in the loaded bundle's vocabulary is a lint failure, not a new entry.
That is still the whole point. What changed is which list is consulted.

`every()` is the union across bundles. It exists for one caller:
catalogue/build.py lints `catalogue/ops/*.md`, which is shared between
bundles, so it cannot know which vocabulary an atom belongs to. The per bundle
closure check is in kernel/declarations.py, over the operations a manifest
actually lists, which is where it bites.

The module level STATIONS, STATES, CAPABILITIES and BUNDLES are the ACTIVE
bundle's, chosen by PHC_BUNDLE exactly as the API chooses which bundle to
load. They are a convenience for code that has no bundle in hand (the API's
role table, the renderer's capability list, the Django permission generator);
code that does have one should ask `for_bundle(id)`.
"""
import functools
import os
import pathlib

import yaml

BUNDLES_DIR = pathlib.Path(__file__).parents[1] / "bundles"

# --------------------------------------------------------------------------
# The shared base. One justification per survivor: if a line below is not true
# of every facility that could ever load this kernel, it belongs in a bundle.
# --------------------------------------------------------------------------

# The adapter's tables, not a facility's words. Names match care/emr/models/*.py.
# A lab and a PHC both write observations into the same column of the same
# table; only the meaning of the row differs, and meaning is the bundle's.
CARE_RESOURCES = frozenset({
    "patient", "encounter", "observation", "condition", "notes",
    "medication_request", "medication_dispense", "inventory_item",
    "service_request", "specimen", "diagnostic_report",
    "questionnaire_response", "consent", "organization", "location",
    # care/emr/models/scheduling/booking.py TokenBooking. Unverified name;
    # read only, no operation writes it yet.
    "token_booking",
})

# §10 of the UI/UX spec: the first-class objects a thread can contain. An
# operation's record is drawn as one of these, and which one is the atom's own
# answer (`presents:`), because a renderer cannot derive it -- a handover and a
# clinical event are both "an operation committed a row", and nothing about
# the row says which. Defaults to "event".
#
# Closed on purpose, exactly like INSTRUMENT_KINDS: the renderer implements
# these and a bundle cannot invent a sixth without renderer code, so a
# declaration naming one is a promise the screen can keep.
THREAD_OBJECTS = ("event", "artifact", "handover", "task", "comment")

# Records the kernel keeps that CARE does not: the stored thread flags. A
# declaration may count them (a metric) but no operation may write them. The
# kernel's own table, so the kernel's own list.
KERNEL_RESOURCES = frozenset({"thread_flag"})

# Guard grammar. `irreversible` means the same thing to every bundle, because
# catalogue/guard.py is what enforces it and there is one guard.
IRREVERSIBILITY = ("reversible", "correctable", "irreversible")

# Capture grammar, and the one vocabulary behind both instrument fields.
#
# INSTRUMENT_KINDS is the master list: every sort of instrument the renderer
# implements, and so the whole of what an instrument atom's `kind:` may name.
# A bundle cannot invent a sixth without renderer code, which is what makes a
# declaration naming one a promise the screen can keep. kernel/contracts.py
# re-exports it, because declaration lint reads it there; it is defined here
# because this is the lower layer (kernel imports catalogue, never the other
# way round) and because "which instrument kinds there are" is what this
# module is for.
INSTRUMENT_KINDS = ("form", "device", "constrained-voice", "scribe", "spoken-prompt")

# INSTRUMENTS is the narrower question: what an OPERATION's `instrument:` may
# name as its default. The renderer draws that default as a pill icon and a
# tag and nothing else (web/src/icons.tsx, and TAG in
# web/src/screens/Encounter.tsx), so it is exactly the kinds a pill can draw.
#
# A strict subset on purpose. A spoken-prompt is not a way of capturing
# anything: it is a line the agent speaks TO the patient, mounted inside a
# form beside the fields and rendered from the instrument declaration
# (web/src/form/Panel.tsx), never from an operation's default. There is no
# pill for it, and an operation defaulting to one would be a promise no screen
# keeps.
#
# Derived rather than typed out a second time, so the two lists cannot drift
# apart again. They had: `palette` was written out here, outlived the
# Palette-to-Khoj rename because scripts/check_khoj.py hunts the capital P
# identifier and this was a lowercase string, and was still accepted by lint
# for an instrument no renderer implements. scripts/check_instruments.py now
# fails if any of this disagrees, in either direction.
NOT_AN_OPERATION_DEFAULT = ("spoken-prompt",)
INSTRUMENTS = tuple(k for k in INSTRUMENT_KINDS if k not in NOT_AN_OPERATION_DEFAULT)
KINDS = ("read", "write")

# The five sections an operation atom's body must carry. A writing rule about
# the documentation, not about any clinic.
BODY_SECTIONS = (
    "In plain words", "Before you start", "What happens",
    "How you know it worked", "When it goes wrong",
)


# --------------------------------------------------------------------------
# Per bundle vocabularies, read from bundles/<id>/bundle.yaml
# --------------------------------------------------------------------------

class Vocabulary:
    """One bundle's own closed lists. Frozen after construction."""

    __slots__ = ("id", "stations", "states", "capabilities", "roles",
                 "capability_titles", "role_titles")

    def __init__(self, id, stations, states, capabilities, roles,
                 capability_titles=None, role_titles=None):
        self.id = id
        self.stations = tuple(stations)
        self.states = frozenset(states)
        self.capabilities = frozenset(capabilities)
        self.roles = {k: list(v) for k, v in (roles or {}).items()}
        # What a person reads for a capability and for a role. Empty for a
        # bundle that declares its words as a plain list of ids, which is the
        # whole of the backward compatibility: no title, no entry, and every
        # reader falls back to what it fell back to before. A key present
        # with an empty value is a declaration that forgot its title, which
        # `problems()` refuses rather than passes on to a screen.
        self.capability_titles = dict(capability_titles or {})
        self.role_titles = dict(role_titles or {})

    def __repr__(self):
        return "Vocabulary(%r, %d stations, %d states, %d capabilities, %d roles)" % (
            self.id, len(self.stations), len(self.states),
            len(self.capabilities), len(self.roles))

    def problems(self):
        """Failures in the vocabulary itself. Lint calls this before anything
        that reads it, so a role holding a capability the bundle does not
        declare is a build failure and not a quiet permission hole."""
        bad = []
        for key in ("stations", "states", "capabilities"):
            if not getattr(self, key):
                bad.append("bundle.yaml: %s is empty; a bundle declares its own" % key)
        for role, caps in sorted(self.roles.items()):
            for cap in caps:
                if cap not in self.capabilities:
                    bad.append("bundle.yaml: role '%s' holds '%s', which this bundle "
                               "does not declare" % (role, cap))
        # A capability or a role declared in the mapping form has said it
        # carries a name, so a missing one is a declaration half written and
        # not a bundle that chose the plain list. Same sentence
        # kernel/plugins.py fails a titleless plugin under, because it is the
        # same mistake.
        for key, titles in (("capabilities", self.capability_titles),
                            ("roles", self.role_titles)):
            for id_, word in sorted(titles.items()):
                if not str(word).strip():
                    bad.append("bundle.yaml %s.%s: missing title" % (key, id_))
        return bad


def _manifest(bundle_id):
    return yaml.safe_load((BUNDLES_DIR / bundle_id / "bundle.yaml").read_text())


def _capabilities(declared):
    """`capabilities:` either way round, as (ids, {id: title}).

    A mapping of id to the words a person reads for it is the shape
    bundles/phc writes, and it is `plugins:`' shape. A plain list of ids is
    what bundles/lab writes, and it declares no names, so the titles come back
    empty and nothing downstream has a word to print. An entry whose title is
    missing is carried as the empty string rather than dropped, so
    `problems()` can refuse it.
    """
    if isinstance(declared, dict):
        return (list(declared),
                {cap: (body or {}).get("title") or "" for cap, body in declared.items()})
    return list(declared or ()), {}


def _roles(declared):
    """`roles:` either way round, as ({role: capabilities}, {role: title}).

    `role: {title, capabilities}` is bundles/phc's and is `plugins:`' shape; a
    bare `role: [capabilities]` is bundles/lab's and names nothing. The
    capability lists are identical either way, which is the point: a title is
    the only thing being added, and what a role HOLDS has not changed shape
    for anybody reading it.
    """
    roles, titles = {}, {}
    for role, body in (declared or {}).items():
        if isinstance(body, dict):
            roles[role] = list(body.get("capabilities") or ())
            titles[role] = body.get("title") or ""
        else:
            roles[role] = list(body or ())
    return roles, titles


def from_manifest(fm):
    """The vocabulary a parsed bundle.yaml declares."""
    caps, cap_titles = _capabilities(fm.get("capabilities"))
    roles, role_titles = _roles(fm.get("roles"))
    return Vocabulary(id=fm.get("id", "?"), stations=fm.get("stations") or (),
                      states=fm.get("states") or (), capabilities=caps,
                      roles=roles, capability_titles=cap_titles,
                      role_titles=role_titles)


@functools.lru_cache(maxsize=None)
def for_bundle(bundle_id):
    """The vocabulary bundles/<bundle_id>/bundle.yaml declares."""
    return from_manifest(_manifest(bundle_id))


def bundle_ids():
    return sorted(p.name for p in BUNDLES_DIR.iterdir()
                  if (p / "bundle.yaml").exists())


@functools.lru_cache(maxsize=None)
def every():
    """The union over every bundle on disk. For linting catalogue/ops/*.md,
    which is shared, and for nothing else: a union is not a closure."""
    stations, states, caps, roles = [], set(), set(), {}
    cap_titles, role_titles = {}, {}
    for bid in bundle_ids():
        v = for_bundle(bid)
        stations += [s for s in v.stations if s not in stations]
        states |= set(v.states)
        caps |= set(v.capabilities)
        roles.update(v.roles)
        cap_titles.update(v.capability_titles)
        role_titles.update(v.role_titles)
    return Vocabulary(id="*", stations=stations, states=states,
                      capabilities=caps, roles=roles,
                      capability_titles=cap_titles, role_titles=role_titles)


ACTIVE = os.environ.get("PHC_BUNDLE", "phc")
_active = for_bundle(ACTIVE)

STATIONS = _active.stations
STATES = _active.states
CAPABILITIES = _active.capabilities
BUNDLES = _active.roles          # role name -> capabilities, this bundle's
