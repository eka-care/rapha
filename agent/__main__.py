"""Take an utterance, print the proposed operations and the guard's verdict.

    python3 -m agent "bp is 140 over 90 and pulse 72" --role nurse
    python3 -m agent "dispense her tablets" --role pharmacist --flags rx.confirmed
    python3 -m agent "link her abha" --flags registered

Nothing this prints has been committed. Every line marked proposed is waiting
on a person at the rendered surface, and every line marked denied is the guard
refusing the agent, not the agent refusing itself.
"""
from __future__ import annotations

import argparse
import json
import sys

from catalogue import vocab

from agent import planner

BOLD, RED, GREEN, DIM, OFF = "\033[1m", "\033[31m", "\033[32m", "\033[2m", "\033[0m"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent", description=__doc__)
    ap.add_argument("utterance", nargs="+")
    ap.add_argument("--role", default="nurse", choices=sorted(vocab.BUNDLES),
                    help="whose capabilities to plan with")
    ap.add_argument("--flags", default="registered",
                    help="thread state flags, comma separated")
    ap.add_argument("--backend", choices=("router", "llm"), default=None,
                    help="default: llm when ANTHROPIC_API_KEY is set, else router")
    args = ap.parse_args(argv)

    utterance = " ".join(args.utterance)
    caps = set(vocab.BUNDLES[args.role])
    state = {f.strip() for f in args.flags.split(",") if f.strip()}
    unknown = state - vocab.STATES
    if unknown:
        print(f"unknown state flags: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2

    catalogue = planner.load()
    which = args.backend or planner.backend()
    print(f"{BOLD}{utterance}{OFF}")
    print(f"{DIM}{which} planner, as {args.role}, thread state {sorted(state)}{OFF}\n")

    proposals = planner.plan(utterance, catalogue, caps=caps, state=state, which=which)
    if not proposals:
        print("  nothing proposed. The router refuses rather than guessing.")
        return 0

    for v in planner.verdicts(proposals, catalogue, caps=caps, state=state):
        op = catalogue["operations"][v.proposed.operation]
        print(f"  {BOLD}{op['id']}{OFF}  {op['title']}")
        print(f"    why      {v.proposed.why}")
        print(f"    payload  {json.dumps(v.proposed.payload, sort_keys=True)}")
        if v.decision.allowed:
            print(f"    verdict  {GREEN}{v.outcome}{OFF}, awaiting a person on the "
                  "rendered surface")
        else:
            print(f"    verdict  {RED}denied{OFF}  {v.decision.reason}")
        print()

    print(f"{DIM}Nothing above was committed. There is no verb here that could.{OFF}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
