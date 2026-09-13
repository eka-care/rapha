"""The guard. Every operation, from every surface, passes through evaluate().

CARE already gives us schema-shaped forms, a role and permission system, and an
audit log. What it has no concept of is a patient moving between stations, so
this module is deliberately small: it is only the part CARE does not do.

Steps 5 to 7 of the write path (audit persist, CARE write, state emit) belong to
the caller. evaluate() decides, and hands back the audit record to write.
"""
import re
from dataclasses import dataclass, field

# Surfaces an operation can be invoked from. There is no third.
RENDERED = "rendered"
MCP = "mcp"


# A precondition is a flag, or a fact about who acted on this thread before.
#
#   registered                      the flag is true
#   not dispensed.complete          the flag is false
#   actor of phc.op.lab-order       this caller performed that operation here
#   not actor of lab.op.result-enter    this caller did NOT perform it
#
# The second pair is separation of duties, which was a login convention until
# there was a way to write it down: a laboratory refuses the person who keyed a
# result the right to verify it, whatever capabilities they hold.
ACTOR_OF = "actor of "

# An agent acts FOR somebody. api/main.py proposes as "agent:<their id>" so a
# card can say a machine asked, not a colleague. For a separation of duties
# rule that prefix has to come off: the person who keyed a result must not be
# able to verify it by dictating the sentence instead of tapping the button.
# Stripped here, in the one predicate both enforcement and visibility read,
# because a rule an agent can launder around is not a rule.
AGENT_PREFIX = "agent:"


def person(actor):
    """The human behind an actor string. `agent:user:x` and `user:x` are the
    same person for every rule about who did what."""
    while actor and actor.startswith(AGENT_PREFIX):
        actor = actor[len(AGENT_PREFIX):]
    return actor


def parse_precondition(pre):
    """(kind, name, negated). kind is "flag" or "actor". One definition, so
    lint (catalogue/build.py) and enforcement (below) cannot drift."""
    negated = pre.startswith("not ")
    term = pre[4:] if negated else pre
    if term.startswith(ACTOR_OF):
        return "actor", term[len(ACTOR_OF):].strip(), negated
    return "flag", term, negated


def _words(name):
    """A flag or operation id, as words. `rx.confirmed` -> "rx confirmed",
    `lab.op.result-enter` -> "lab op result enter". No lookup table: this is
    the catalogue's own punctuation, split apart, so any bundle's flags read
    the same way PHC's do."""
    return re.sub(r"[._-]+", " ", name).strip()


def describe_precondition(pre, unevaluable=False):
    """A sentence a clerk reads correctly, never the literal precondition
    string. `not registered` unmet means the flag IS present, which is
    "Already registered.", not something that sounds like its opposite. A
    required flag that is absent reads what it requires. `unevaluable` is the
    separation-of-duties case where nobody said who is acting, so it is
    neither confirmed nor denied by the flag or the actor; it says that."""
    kind, name, negated = parse_precondition(pre)
    words = _words(name)
    if unevaluable:
        return f"Needs to know who is acting, to check whether they performed {words}."
    if kind == "actor":
        return f"Already performed {words}." if negated else f"Must be the person who performed {words}."
    return f"Already {words}." if negated else f"Requires {words}."


@dataclass
class Decision:
    allowed: bool
    reason: str
    audit: dict = field(default_factory=dict)

    def __bool__(self):
        return self.allowed


def _preconditions_met(op, state, actor=None, performers=None, unknown_actor=False):
    """state is the set of flags currently true for this patient thread.

    `performers` maps operation id to the set of actors who have already
    performed it on this thread; kernel/state.py builds it from the audit
    trail, which is the only record of who did what. `unknown_actor` says what
    to do when nobody supplied one: the guard passes True and denies, because
    a rule it cannot evaluate must never read as satisfied; a surface deciding
    what to draw passes False and shows the action, and the tap is refused.
    """
    for pre in op.get("preconditions") or []:
        kind, name, negated = parse_precondition(pre)
        if kind == "flag":
            held = name in state
        elif actor is None or performers is None:
            # Not evaluable: either nobody said who is acting, or nobody read
            # the thread's audit to find out who acted before.
            if unknown_actor:
                return False, pre, True
            continue
        else:
            held = person(actor) in {person(a) for a in (performers.get(name) or ())}
        if held == negated:
            return False, pre, False
    return True, None, False


def visible(op, caps, state, actor=None, performers=None):
    """Should this action be drawn at all?

    Addendum SSD.1: an action does not appear before its precondition. Not
    greyed out, not erroring on tap. Absent. This is the same predicate the
    guard enforces, so the surface cannot drift from the rule.

    With no actor, an `actor of` precondition cannot be evaluated and the
    action stays drawn; the guard then refuses the tap and says why. Pass the
    actor (kernel/state.actions does, when it is given one) and the button is
    absent for the person who may not press it.
    """
    if op["capability"] not in caps:
        return False
    met, _, _ = _preconditions_met(op, state, actor, performers)
    return met


def evaluate(op, *, caps, state, payload, surface, confirmed=False,
             scopes=None, validate=None, actor=None, performers=None):
    """Guard steps 1 to 4. Returns a Decision carrying the audit record.

    validate: callable(op, payload) -> list of problems. Required. There is no
    default, because a missing validator must not read as a passing one.

    performers: {operation id: set of actors who performed it on this thread}.
    Required only by an operation carrying an `actor of` precondition, and
    fail closed for exactly the same reason as validate: an unanswered
    separation of duties rule is a denial, never a pass.
    """
    audit = {
        "operation": op["id"], "actor": actor, "surface": surface,
        "payload": payload, "outcome": None,
    }

    def deny(reason):
        audit["outcome"] = f"denied: {reason}"
        return Decision(False, reason, audit)

    # 1. schema. Fail closed: no validator is a denial, never a pass.
    if validate is None:
        return deny("no validator registered for this operation")
    problems = validate(op, payload)
    if problems:
        return deny(f"payload invalid: {'; '.join(problems)}")

    # 2. capability, then its scope qualifier. A CHO's rx.prescribe is not an MO's.
    if op["capability"] not in caps:
        return deny(f"missing capability {op['capability']}")
    qualifier = op.get("scope_qualifier")
    if qualifier and qualifier not in (scopes or set()):
        return deny(f"outside scope of practice: {qualifier}")

    # 3. preconditions over thread state, and over who has already acted here.
    met, missing, unevaluable = _preconditions_met(op, state, actor, performers, unknown_actor=True)
    if not met:
        return deny(describe_precondition(missing, unevaluable))

    # 4. irreversibility. v0.1 SS5 and addendum SSB.2: the confirm for an
    #    irreversible operation is explicit and un-prefilled, and an agent can
    #    never satisfy it. Note this denies on surface before it looks at
    #    `confirmed` at all, so a machine caller asserting confirmation gets
    #    nowhere.
    if op["irreversibility"] == "irreversible":
        if surface != RENDERED:
            return deny("irreversible operations require a human confirmation "
                        "on the rendered surface")
        if not confirmed:
            return deny("irreversible operation needs an explicit confirm")

    # A write from the machine surface is a proposal, never a commit.
    outcome = "proposed" if (surface == MCP and op["kind"] == "write") else "allowed"
    audit["outcome"] = outcome
    return Decision(True, outcome, audit)
