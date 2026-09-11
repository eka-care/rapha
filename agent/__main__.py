"""Talk to the kernel in sentences. Nothing said here can commit anything.

    python3 -m agent                                   # a conversation
    python3 -m agent "bp 140 over 90, pulse 72"        # one turn and out
    python3 -m agent "order a blood sugar" --thread enc-004 --role mo

An utterance goes to a planner, the plan is sorted into the order the KERNEL
already put this thread's actions in, and every operation is POSTed to
/operations/{op}/propose. What comes back is a proposal id, or the guard's own
refusal in the guard's own words.

Read the two things this deliberately does not do. It does not rank the work:
ThreadView.actions arrives ordered and the agent explains that order rather
than forming one. And it cannot finish anything: agent/client.py holds no
verb that commits, and refuses to assemble a URL that would.

In the conversation:  :queue   :thread <id>   :quit
"""
from __future__ import annotations

import argparse
import json
import sys

from agent import client, planner

BOLD, RED, GREEN, YELLOW, DIM, OFF = (
    "\033[1m", "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m")

UNSURE = ("I do not know which operation that is. I will not guess: a wrong "
          "proposal in front of a busy clinician is worse than none.\n"
          "Say what you want recorded, or :queue to see who is waiting.")


def header(view: dict) -> str:
    """Who this thread is about and where the kernel says it stands."""
    subject = view.get("subject") or {}
    who = subject.get("name") or view["id"]
    return ("%s%s%s  %s  station %s  flags %s\n%s%s%s"
            % (BOLD, who, OFF, view["id"], view.get("station") or "line complete",
               ", ".join(view["flags"]) or "none", DIM, view.get("nudge", ""), OFF))


def respond(kernel, catalogue: dict, view: dict, utterance: str,
            which: str = None) -> str:
    """One turn. Plan, order by the kernel, propose each, report each verdict.

    Every operation the planner named is sent, including one the kernel does
    not currently offer, because the refusal is the guard's to state and an
    agent that pre-filters is an agent quietly making clinical decisions.
    """
    if not utterance.strip():
        return ""
    try:
        plan = planner.plan(utterance, catalogue, caps=set(view["held"]),
                            state=set(view["flags"]), which=which)
    except Exception as broke:  # the SDK, a key, a rate limit, a network
        # Say what went wrong and stop. A planner that failed has proposed
        # nothing, and falling back to the other backend silently would hide
        # which one produced what.
        return ("the %s planner failed: %s: %s\nrerun with --backend router, "
                "which needs no key and no network." % (which, type(broke).__name__, broke))
    if not plan:
        return UNSURE

    actions = view.get("actions") or []
    lines = []
    for p in planner.by_kernel_order(plan, actions):
        op = catalogue["operations"][p.operation]
        lines.append("  %s%s%s  %s" % (BOLD, op["id"], OFF, op["title"]))
        lines.append("    heard    %s" % p.why)
        lines.append("    order    %s" % planner.explain_order(p, actions, view.get("station")))
        lines.append("    payload  %s" % json.dumps(p.payload, sort_keys=True))
        for question in p.ask:
            lines.append("    ask      %s%s%s" % (YELLOW, question, OFF))
        try:
            answer = kernel.propose(p.operation, view["id"], p.payload)
        except client.Refused as no:
            lines.append("    verdict  %srefused%s  %s" % (RED, OFF, no.reason))
            lines.append("             %s(the kernel's words, not mine)%s" % (DIM, OFF))
            continue
        lines.append("    verdict  %s%s%s as %s" % (GREEN, answer["status"], OFF,
                                                    answer["proposal_id"]))
        if answer.get("flags_raised"):
            lines.append("    flagged  %s%s%s" % (YELLOW, ", ".join(answer["flags_raised"]), OFF))
        lines.append("    %sopen %s on screen and confirm it there. I cannot.%s"
                     % (DIM, answer["proposal_id"], OFF))
    return "\n".join(lines)


def show_queue(kernel) -> str:
    rows = kernel.queue()
    return "\n".join(
        "  %-8s %-22s %-10s %s" % (r["thread"], (r["subject"] or {}).get("name") or "-",
                                   r["station"] or "complete", ", ".join(r["flags"]) or "")
        for r in rows) or "  the queue is empty"


def pick_thread(kernel, wanted: str = None) -> dict:
    """The thread under discussion. With none named, the first one waiting."""
    if wanted:
        return kernel.thread(wanted)
    rows = kernel.queue()
    waiting = [r for r in rows if r["station"]] or rows
    if not waiting:
        raise SystemExit("no threads: the kernel's queue is empty")
    return kernel.thread(waiting[0]["thread"])


def converse(kernel, catalogue, view, which) -> int:
    """Read a line, answer it, and refresh the thread so the next turn sees the
    proposals the last one raised."""
    print(DIM + "an utterance, or :queue  :thread <id>  :quit" + OFF)
    while True:
        try:
            said = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if said in (":quit", ":q"):
            return 0
        if said == ":queue":
            print(show_queue(kernel))
            continue
        if said.startswith(":thread"):
            rest = said[len(":thread"):].strip()
            try:
                view = kernel.thread(rest) if rest else kernel.thread(view["id"])
            except client.Refused as no:
                print("  %s" % no.reason)
                continue
            print(header(view))
            continue
        if said.startswith(":"):
            print("  :queue, :thread <id>, :quit")
            continue
        out = respond(kernel, catalogue, view, said, which)
        if out:
            print(out)
        view = kernel.thread(view["id"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("utterance", nargs="*", help="one turn; omit for a conversation")
    ap.add_argument("--thread", default=None, help="default: the first thread waiting")
    ap.add_argument("--role", default=None, help="default: the kernel's demo role")
    ap.add_argument("--api", default=client.BASE)
    ap.add_argument("--backend", choices=("router", "llm"), default=None,
                    help="default: llm when ANTHROPIC_API_KEY is set, else router")
    args = ap.parse_args(argv)

    kernel = client.Kernel(args.api, role=args.role)
    which = args.backend or planner.backend()
    try:
        catalogue = kernel.catalogue()
        view = pick_thread(kernel, args.thread)
    except client.Unreachable as down:
        print(down, file=sys.stderr)
        return 3
    except client.Refused as no:
        print(no.reason, file=sys.stderr)
        return 4

    print("%s%s planner against %s, %d operations%s"
          % (DIM, which, kernel.base, len(catalogue["operations"]), OFF))
    print(header(view))
    if args.utterance:
        out = respond(kernel, catalogue, view, " ".join(args.utterance), which)
        print(out)
        print("\n%sProposed, not committed. There is no verb in this process "
              "that could commit.%s" % (DIM, OFF))
        return 0
    return converse(kernel, catalogue, view, which)


if __name__ == "__main__":
    sys.exit(main())
