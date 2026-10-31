"""A facility's shape: which plugins a centre runs, resolved to one subtraction.

What a plugin is
----------------
A plugin is a NAMED GROUP OF ONE BUNDLE'S OWN WORDS. It is manifest data in
`bundles/<id>/bundle.yaml` beside `roles:`, and it is deliberately not a sixth
declaration type, for the reason the spine and plugins spec gives: each of the
five costs a required manifest entry, a lint pass, a dataclass, a compile_json
key, a Go struct and a renderer type, and a plugin is a grouping of ids, which
is precisely what `roles:` already is.

What a facility's shape is
--------------------------
A facility is one line: which of those groups this centre does not run. Two
primary health centres then run the same code, the same bundle and the same
compiled catalogue, and differ by one declared list.

THE MECHANISM, AND WHY IT IS THE ONLY ONE AVAILABLE
---------------------------------------------------
A plugin that is off is a capability the caller does not hold. Subtracted
once, here, before anything reads it.

That is forced rather than chosen. Clinical capability lives in declared atoms
compiled to catalogue.json, and the renderer may never name a station, a flag,
a capability or a bundle, so "switch the laboratory off" cannot be a condition
in a screen. A second bundle file would be the fork this module exists to
avoid. What is left is the one per caller set that catalogue/guard.py,
`guard.visible`, `kernel/state.actions`, `GET /whoami`, `GET /views/{id}` and
care_phc_mcp's `For()` all ALREADY read: the capability set. Anything expressed
as a second set has to be taught to six places, and the six then drift.

So the off switch is not a new concept. It is a subtraction applied to an old
one, and every consequence the brief asks for falls out of machinery that was
already there:

- the guard denies, naming the capability AND the plugin, and writes the audit
  row before execute like every other denial. It does not hide.
- `guard.visible` and `kernel/state.actions` stop drawing the action, because
  they read the same narrowed set.
- care_phc_mcp's tool list narrows, because it builds itself from `/whoami`.
- a view whose own `capability:` is withheld answers 403, so its metrics are
  unreachable too.
- a workflow step whose `applies_when` can no longer be raised is skipped
  rather than pending, so the line is shorter and nobody waits at a station
  this centre does not have.

What a facility may NOT change
------------------------------
Everything clinical, and that is the point of putting the switch here. A
facility declaration holds plugin ids and nothing else: no condition, no
medicine, no value set, no threshold, no interval, no question, no section
heading, no station, no flag. It cannot add a capability, only decline one the
bundle already declares. It cannot reach inside a form, a mapping or a
document placement. And it cannot switch off a plugin declared `always: true`,
which is the floor.

Pure: reads the parsed manifest and the parsed declarations, touches no
database and no network.
"""
from __future__ import annotations

import os

# What a plugin declaration may say, and nothing else.
PLUGIN_KEYS = ("title", "capabilities", "always")
PLUGIN_REQUIRED = ("title", "capabilities")

# What a facility declaration may say, and nothing else. `without` is the
# whole of a centre's choice: there is no positive list, because one means a
# plugin added later ships off for everybody and nobody notices until a
# clinician cannot do their job.
#
# The key is `without` and not `off`, which is what the spec wrote and what
# this was written as first. YAML 1.1 reads a bare off as the boolean false,
# so that spelling parses as a key named False and the facility silently
# withholds nothing. It is refused by name below rather than as an unknown
# key, because "unknown key 'False'" tells a reader nothing about what they
# typed. That is how this was found.
FACILITY_KEYS = ("title", "without")
FACILITY_REQUIRED = ("title",)
# The two bare words YAML turns into booleans and a reader does not expect to.
YAML_BOOLEAN_KEYS = (False, True)

# The environment variable that picks a shape, read exactly where PHC_BUNDLE is
# read and for the same reason: one kernel serves one facility.
ENV = "PHC_FACILITY"


def declared(manifest):
    """{plugin id: declaration} this bundle declares, or {}."""
    return dict(manifest.get("plugins") or {})


def facilities(manifest):
    """{facility id: declaration} this bundle declares, or {}."""
    return dict(manifest.get("facilities") or {})


def chosen(manifest, facility=None):
    """Which shape this kernel is running, or None if the bundle declares none.

    The argument wins over the environment, which wins over the bundle's own
    default. A bundle with no `facilities:` has one shape and no choice to
    make, which is what keeps bundles/lab valid with nothing added to it.
    """
    if not facilities(manifest):
        return None
    return facility or os.environ.get(ENV) or manifest.get("facility")


def off(manifest, facility=None):
    """The plugin ids this facility does not run, in declaration order."""
    which = chosen(manifest, facility)
    decl = facilities(manifest).get(which) or {}
    return [p for p in (decl.get("without") or []) if p in declared(manifest)]


def withheld(manifest, facility=None):
    """{capability: the plugin id that withholds it} for this facility.

    The whole of the runtime effect, as one dict. The guard reads it to name a
    denial, and `effective()` reads it to subtract. There is no second form.
    """
    plugins = declared(manifest)
    out = {}
    for pid in off(manifest, facility):
        for cap in plugins[pid].get("capabilities") or []:
            out[cap] = pid
    return out


def effective(caps, held_back):
    """`caps` minus what this facility withholds, order preserved.

    One function, called once, in api/main.py `caller()`. A second subtraction
    somewhere else would be a second place to forget.
    """
    return [cap for cap in caps if cap not in (held_back or {})]


def seeded(threads, ops, held_back):
    """This facility's demo day: the seeded threads it could really have had.

    A seed is fixture data rather than a declaration, but a thread whose
    history names an operation nobody at this centre may perform is a lie
    about what happened here, and it draws a pending card no person can
    confirm. So a thread is dropped whole rather than edited: half a visit
    with its laboratory step quietly deleted reads as a visit that finished.
    """
    if not held_back:
        return list(threads or [])
    kept = []
    for thread in threads or []:
        named = {entry.get("operation")
                 for entry in (thread.get("proposals") or []) + (thread.get("audit") or [])}
        if any((ops.get(oid) or {}).get("capability") in held_back for oid in named):
            continue
        kept.append(thread)
    return kept


# --------------------------------------------------------------------------
# lint
# --------------------------------------------------------------------------

def _closers(workflow_fm, ops, held_back):
    """{done_when: whether any operation still available raises it}.

    An operation raises a flag by declaring it in `emits`, which is the only
    place that claim is made and is already linted against the bundle's own
    states. Station is deliberately NOT part of this: `phc.op.household-visit`
    stands at one station and closes another's step, which is a fact about
    this line and not a mistake.
    """
    out = {}
    for step in workflow_fm.get("steps") or []:
        flag = step.get("done_when")
        out.setdefault(flag, False)
        for oid, op in ops.items():
            if flag in (op.get("emits") or []) and op["capability"] not in held_back:
                out[flag] = True
    return out


def lint(manifest, ops, decls):
    """Return a list of failure strings. Empty means every shape is sound.

    `ops` is the compiled operations this bundle loads, `decls` the bundle
    directory's {id: (frontmatter, body)}.

    What this refuses, each one a centre that would look configured and be
    broken:

    - a plugin naming a capability this bundle does not declare, or two
      plugins claiming the same one. A capability no plugin claims is always
      on, which is the default on rule: a plugin added later cannot silently
      take an ability away from a facility that never heard of it.
    - a facility naming a plugin that does not exist, which is a switch
      wired to nothing.
    - a facility switching off a plugin declared `always: true`.
    - a bundle declaring facilities and no default, or a default that is not
      one of them, or an unknown shape asked for by the environment.
    - and the one that matters: A FACILITY WHOSE CHOICE STOPS THE LINE. If no
      operation this centre may still perform raises a step's `done_when`, and
      that step has no `applies_when` to skip it, every patient waits at that
      station forever. A step that CAN be skipped is the mechanism, not the
      bug: that is how a centre with no laboratory has no laboratory queue.

    What this does NOT refuse, and why
    ----------------------------------
    A view or a metric left unreachable. A facility that withholds
    `reporting.view` means to stop reading its own numbers on that screen, and
    `GET /views/{id}` already answers 403 with the capability named. Refusing
    it would make the switch unusable for the one thing it is for.
    """
    bad = []
    plugins = declared(manifest)
    shapes = facilities(manifest)
    if not plugins and not shapes:
        return bad

    caps = set(manifest.get("capabilities") or [])
    owner = {}
    for pid, decl in sorted(plugins.items()):
        where = "bundle.yaml plugins.%s" % pid
        if not isinstance(decl, dict):
            bad.append("%s: not a declaration" % where)
            continue
        for key in sorted(set(decl) - set(PLUGIN_KEYS)):
            bad.append("%s: unknown key '%s'" % (where, key))
        for key in PLUGIN_REQUIRED:
            if not decl.get(key):
                bad.append("%s: missing %s" % (where, key))
        for cap in decl.get("capabilities") or []:
            if cap not in caps:
                bad.append("%s: names '%s', which this bundle does not declare, "
                           "so the switch is wired to nothing" % (where, cap))
            elif cap in owner:
                bad.append("%s: claims '%s', which plugin '%s' already claims. "
                           "Two switches on one ability means neither one "
                           "turns it off" % (where, cap, owner[cap]))
            else:
                owner[cap] = pid

    if shapes and not manifest.get("facility"):
        bad.append("bundle.yaml: declares facilities and no `facility:` saying "
                   "which one this build runs")
    if manifest.get("facility") and manifest["facility"] not in shapes:
        bad.append("bundle.yaml facility: '%s' is not one of the declared "
                   "facilities %s" % (manifest["facility"], sorted(shapes)))
    asked = os.environ.get(ENV)
    if asked and asked not in shapes:
        bad.append("%s=%s is not one of the facilities bundle.yaml declares: %s"
                   % (ENV, asked, sorted(shapes)))

    workflows = [fm for fm, _ in decls.values() if fm.get("type") == "workflow"]
    for fid, decl in sorted(shapes.items()):
        where = "bundle.yaml facilities.%s" % fid
        if not isinstance(decl, dict):
            bad.append("%s: not a declaration" % where)
            continue
        for key in sorted(set(decl) - set(FACILITY_KEYS), key=str):
            if key in YAML_BOOLEAN_KEYS:
                bad.append("%s: the key is `without`. YAML reads a bare on or "
                           "off as a boolean, so this facility lists its "
                           "plugins under a key named %r and switches nothing "
                           "off" % (where, key))
            else:
                bad.append("%s: unknown key '%s'" % (where, key))
        for key in FACILITY_REQUIRED:
            if not decl.get(key):
                bad.append("%s: missing %s" % (where, key))
        listed = list(decl.get("without") or [])
        for pid in listed:
            if pid not in plugins:
                bad.append("%s: switches off '%s', which is not a plugin this "
                           "bundle declares" % (where, pid))
            elif plugins[pid].get("always"):
                bad.append("%s: switches off '%s', which is declared always on"
                           % (where, pid))
        if len(set(listed)) != len(listed):
            bad.append("%s: names a plugin twice" % where)

        held_back = withheld(manifest, fid)
        for workflow_fm in workflows:
            raisable = _closers(workflow_fm, ops, held_back)
            for step in workflow_fm.get("steps") or []:
                if step.get("applies_when"):
                    continue
                flag = step.get("done_when")
                if not raisable.get(flag):
                    bad.append(
                        "%s: nothing this centre may do raises '%s', and the "
                        "'%s' step of %s has no applies_when to skip it, so "
                        "every visit waits there forever"
                        % (where, flag, step.get("station"), workflow_fm["id"]))

    return bad
