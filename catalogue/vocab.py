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

# Capture grammar. The renderer implements these four and no more, so a bundle
# cannot invent a fifth without renderer code.
INSTRUMENTS = ("form", "device", "constrained-voice", "scribe", "palette")
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

    __slots__ = ("id", "stations", "states", "capabilities", "roles")

    def __init__(self, id, stations, states, capabilities, roles):
        self.id = id
        self.stations = tuple(stations)
        self.states = frozenset(states)
        self.capabilities = frozenset(capabilities)
        self.roles = {k: list(v) for k, v in (roles or {}).items()}

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
        return bad


def _manifest(bundle_id):
    return yaml.safe_load((BUNDLES_DIR / bundle_id / "bundle.yaml").read_text())


def from_manifest(fm):
    """The vocabulary a parsed bundle.yaml declares."""
    return Vocabulary(id=fm.get("id", "?"), stations=fm.get("stations") or (),
                      states=fm.get("states") or (), capabilities=fm.get("capabilities") or (),
                      roles=fm.get("roles") or {})


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
    for bid in bundle_ids():
        v = for_bundle(bid)
        stations += [s for s in v.stations if s not in stations]
        states |= set(v.states)
        caps |= set(v.capabilities)
        roles.update(v.roles)
    return Vocabulary(id="*", stations=stations, states=states,
                      capabilities=caps, roles=roles)


ACTIVE = os.environ.get("PHC_BUNDLE", "phc")
_active = for_bundle(ACTIVE)

STATIONS = _active.stations
STATES = _active.states
CAPABILITIES = _active.capabilities
BUNDLES = _active.roles          # role name -> capabilities, this bundle's
