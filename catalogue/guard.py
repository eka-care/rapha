"""The guard. Every operation, from every surface, passes through evaluate().

CARE already gives us schema-shaped forms, a role and permission system, and an
audit log. What it has no concept of is a patient moving between stations, so
this module is deliberately small: it is only the part CARE does not do.

Steps 5 to 7 of the write path (audit persist, CARE write, state emit) belong to
the caller. evaluate() decides, and hands back the audit record to write.
"""
from dataclasses import dataclass, field

# Surfaces an operation can be invoked from. There is no third.
RENDERED = "rendered"
MCP = "mcp"


@dataclass
class Decision:
    allowed: bool
    reason: str
    audit: dict = field(default_factory=dict)

    def __bool__(self):
        return self.allowed


def _preconditions_met(op, state):
    """state is the set of flags currently true for this patient thread."""
    for pre in op.get("preconditions") or []:
        if pre.startswith("not "):
            if pre[4:] in state:
                return False, pre
        elif pre not in state:
            return False, pre
    return True, None


def visible(op, caps, state):
    """Should this action be drawn at all?

    Addendum SSD.1: an action does not appear before its precondition. Not
    greyed out, not erroring on tap. Absent. This is the same predicate the
    guard enforces, so the surface cannot drift from the rule.
    """
    if op["capability"] not in caps:
        return False
    met, _ = _preconditions_met(op, state)
    return met


def evaluate(op, *, caps, state, payload, surface, confirmed=False,
             scopes=None, validate=None, actor=None):
    """Guard steps 1 to 4. Returns a Decision carrying the audit record.

    validate: callable(op, payload) -> list of problems. Required. There is no
    default, because a missing validator must not read as a passing one.
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

    # 3. preconditions over thread state.
    met, missing = _preconditions_met(op, state)
    if not met:
        return deny(f"precondition not met: {missing}")

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
