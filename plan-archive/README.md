# ABDM Developer Portal, project folder

Everything for the ABDM Developer Portal V1 in one place.

## Contents

- `abdm-v1-phase1-architecture-and-plan.md` the base architecture and execution plan. Four building blocks, the seven principles, the atom model, the OODA skill loops, the update pipeline, the schedule and definition of done.
- `plan-as-source-addendum.md` how the plan itself becomes a versioned source so the plugin never drifts from it. Read this second; it extends the plan above rather than replacing it.
- `plugin/` the `abdm-portal` plugin: 17 skills, 6 agents, 12 commands that build and operate the portal. Install this to start work. See `plugin/README.md`.
- `gantt/` the generator for the shared schedule, and the link to the Google Sheet partners are given. Structure compiles from the plan, live status lives in the Sheet. See `gantt/README.md`.
- `manifest.json` the plan's version, content hash and the list of skills compiled from it. This is what an installed plugin fetches to notice it is stale.
- `scripts/plan-check.sh` the gate. Fails when the plan has changed but the manifest, the compiled skills or the gantt generator have not.
- `plan-history/` superseded versions of the plan, never deleted, one file per `plan_version`.

## Install the plugin

This repo is a Claude Code marketplace. Two commands:

```sh
claude plugin marketplace add obadiah-1/abdm-ai-sandbox-plan
```

```sh
claude plugin install abdm-portal@abdm-portal
```

If the commands do not appear, restart Claude Code. Components load at startup.

## What you get

Twelve commands:

| Command | Does |
|---|---|
| `/atom-new <type> <gateway> <slug>` | Scaffold an atom with valid frontmatter and the five mandatory sections |
| `/atom-verify <atom-id>` | Run an atom against the sandbox and record what came back |
| `/catalogue-lint [--atoms\|--oas\|--compiled\|--fix]` | Every mechanised check, locally, before you push |
| `/catalogue-status [--gaps\|--stale]` | Coverage and verification state by gateway, milestone and type |
| `/docs-publish [--preview\|--check]` | Generate navigation, preview or publish the Scalar site |
| `/eval-run [<n>] [--record]` | The six eval tasks, scored against atom exit conditions |
| `/firstday-test [--prepare\|--score]` | Set up, run and score the first-day developer test |
| `/gantt-update [--read\|--propose\|--rebuild]` | Propose the gantt status changes landed work justifies, apply on approval |
| `/plan-check [--diff\|--breaking]` | Are these skills built from the current plan |
| `/skills-compile [<skill>\|--trace <skill>]` | Compile atoms into skills and report what fed what |
| `/source-check [<source>\|--dry-run]` | Sweep NHA sources and the plan, open a pull request on a change |
| `/standup [--checkpoint\|--done]` | What moved, what is blocked, what ships next |

Plus 17 skills and 6 agents. Start from the `abdm-portal-index` skill, which routes to the rest. Full inventory and token cost:

```sh
claude plugin details abdm-portal
```

## Working on the plugin

Point the marketplace at your checkout instead of GitHub:

```sh
claude plugin marketplace add ./
```

Re-run this after each change, then restart:

```sh
claude plugin marketplace update abdm-portal
```

Before committing any plugin change, because a malformed manifest fails the whole plugin rather than the part that is wrong:

```sh
claude plugin validate ./plugin --strict
```

To remove it:

```sh
claude plugin uninstall abdm-portal
```

## Reading order

1. `abdm-v1-phase1-architecture-and-plan.md`, for what is being built and why
2. `plan-as-source-addendum.md`, for how the plan stays authoritative as it changes
3. `plugin/README.md`, for the tools that do the work

## Changing the plan

The plan is the fundamental source. Every change to it must reach the plugin, so a plan edit is a five-step change, not a one-file change:

1. Edit `abdm-v1-phase1-architecture-and-plan.md`
2. Copy the version you replaced to `plan-history/plan-<old version>.md`
3. Rebuild the four plan-derived skills and restamp `plan_version` in each one's frontmatter. If the schedule moved, update the `TASKS` table and `PLAN_VERSION` in `gantt/build_gantt.py` too
4. Bump `plan_version` and `plan_hash` in `manifest.json`, and set `breaking: true` if a principle, a date, an owner or a definition of done criterion changed
5. Run the gate, which fails until 3 and 4 are both done

```sh
./scripts/plan-check.sh
```

`plan_version` is the date of the change, with a counter appended for a second change on the same day: `2026.08.24`, then `2026.08.24-2`.

Plan sections carry stable ids, declared as an anchor tag above each heading, so skills cite `plan#p4-skills` rather than a heading anchor that breaks on any reword. The gate checks that every id cited in the plugin still resolves, which makes renaming one a change you cannot half-finish.

Full procedure, and what the version stamp is for: `plugin/skills/plan-sync/SKILL.md`.

## The one thing to remember

The plan is the base layer. The plugin's `portal-architecture`, `portal-planning`, `dpg-governance` and index skills are compiled from `abdm-v1-phase1-architecture-and-plan.md` and its governance section, not written by hand. When the plan changes, those skills are rebuilt, never edited directly.

A hand edit to one of those four is overwritten on the next build, silently. A plan edit without a rebuild is caught loudly by `scripts/plan-check.sh`. That asymmetry is deliberate: the plan moves, the plugin follows, and the gate makes the second half non-optional.
