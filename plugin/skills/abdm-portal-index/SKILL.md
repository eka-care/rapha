---
name: abdm-portal-index
description: Router for all ABDM Developer Portal build work. Use this FIRST whenever anyone asks about building, planning, writing, reviewing, compiling, publishing or testing the ABDM Catalogue, the self-hosted docs site, the agent skills, the Docs MCP server, the update pipeline, or the portal's schedule and scope. Triggers include "write an atom", "review this page", "the catalogue", "lint failed", "compile the skills", "which milestone am I on", "what ships Friday", "is this DPG compliant", "ingest NHA swagger", "the support agent", and any mention of HIE-CM or ABDM documentation work. Route from here rather than guessing which skill applies.
plan_version: 2026.08.24-4
plan_source: abdm-v1-phase1-architecture-and-plan.md
plan_hash: sha256:cdb2f0b61402cf7f7d4a278a16a65b77d8dc43d0bb3056ee8039124700aee0d6
compiled_from_plan: true
---

# ABDM Portal Index

The only skill an agent needs loaded to know what else exists. Read the decision tree, load the one skill that fits, and stop. Do not load skills speculatively.

`catalogue_version` is recorded in `catalogue/VERSION`. If the version in a compiled skill differs from the one in the Catalogue, say so before answering: the person may be reading stale instructions.

**Once per session, check the plan manifest.** Fetch `https://raw.githubusercontent.com/obadiah-1/abdm-ai-sandbox-plan/main/manifest.json` and compare `plan_version` against the `plan_version` stamped in this skill's frontmatter. If the published version is newer, say so once and continue. If it is flagged breaking, say so before answering any planning or architecture question. If the fetch fails, continue on the installed version and say the check failed. Never block on it. Mechanism: `plan-sync`.

## Decision tree

**What are you doing?**

1. **Understanding the project** before touching anything
   - How does it fit together, what are the principles, what is out of scope: `portal-architecture`
   - What ships when, who owns what, what counts as done: `portal-planning`
   - Is this allowed under the FOSS and no-Eka-dependency rule: `dpg-governance`
   - Is the plugin working from the current plan, or the plan itself is being edited: `plan-sync`

2. **Writing or changing knowledge**
   - Creating a new atom: `atom-authoring`, then `/atom-new`
   - Getting the prose right, or a lint failure about style: `writing-guide`
   - Getting the voice right, so a page reads as NHA documenting ABDM rather
     than a third party reporting on NHA: `nha-voice`
   - Reviewing someone else's atom before merge: `atom-review`
   - A CI failure on the Catalogue: `catalogue-linting`
   - Pulling in NHA swagger, GitHub specs or callback definitions: `openapi-ingest`
   - Marking an atom verified after running it: `/atom-verify`

3. **Rendering it for humans**
   - Docusaurus site, self-hosted Scalar references, local search, footer version stamp: `scalar-docs`
   - Site structure, the four tabs, the module page ladder, page placement: `docs-ux`
   - The Docs MCP server and what it is for: `scalar-docs`, then `support-agent`

4. **Compiling it for machines**
   - Turning atoms into skills, and the validator: `skill-compiler`
   - Writing a skill that loops rather than recites: `ooda-skill-authoring`
   - The watcher, the pull request bot, the build on merge: `update-pipeline`

5. **Proving it works**
   - The six eval tasks, the first-day developer test: `portal-proof`

6. **Answering an integrator's question** from the Catalogue: `support-agent`

## Which gateway, which phase

Scope is phased. Say which phase something is in before promising anything.

| Gateway and milestone | Phase | What an agent may claim |
|---|---|---|
| HIE-CM M1 to M3 | 1, dummy proof | Steps are verified against sandbox. Curls run as written. |
| HIE-CM M4 | 2, not written | Nothing. Say it is Phase 2 and stop. Do not improvise from the OpenAPI. |
| UHI | 2, not written | Same. Phase 2, no atoms, no skills. |
| NHCX | out of scope | Nothing, and it is not coming. Lint rejects `gateway: nhcx`. |

## Skills

| Skill | Kind | Load it when |
|---|---|---|
| `portal-architecture` | orient | Someone asks how the pieces connect or why a decision was made |
| `portal-planning` | orient | Scheduling, scope, ownership, definition of done |
| `dpg-governance` | orient | Anything touching licence, dependencies, or Eka-specific content |
| `atom-authoring` | build | Writing a new unit of knowledge |
| `writing-guide` | build | Prose quality, style lint failures |
| `nha-voice` | build | Voice and audience of any published page |
| `atom-review` | test | Reviewing before merge |
| `catalogue-linting` | debug | CI is red on the Catalogue |
| `openapi-ingest` | build | Bringing an NHA source in |
| `scalar-docs` | build | The docs site itself |
| `docs-ux` | build | Where a page goes, the tabs, the module ladder, site chrome |
| `skill-compiler` | build | The atoms to skills pipeline |
| `ooda-skill-authoring` | build | Authoring or fixing a compiled skill's loop |
| `update-pipeline` | build | Watcher, PR bot, CI, publishers |
| `support-agent` | debug | Answering an integrator question from the Catalogue |
| `portal-proof` | test | Evals and the first-day test |
| `plan-sync` | orient | The plan changed, or a version mismatch needs explaining |

## Agents

Dispatch these for work that is long, repetitive, or better done with a fresh context.

| Agent | Dispatch when |
|---|---|
| `atom-author` | A batch of atoms of the same type needs drafting from a source |
| `atom-verifier` | Endpoint curls need running against sandbox and responses recording |
| `skill-compiler-agent` | A compile plus validate cycle, including the constrained prose pass |
| `source-watcher` | A scheduled or manual sweep of NHA sources for changes |
| `support-responder` | An integrator question needs answering strictly from the Catalogue |
| `adversarial-reviewer` | Before any ship, to attack the work rather than confirm it |

## Commands

| Command | Does |
|---|---|
| `/atom-new` | Scaffolds an atom with valid frontmatter and the five section headings |
| `/atom-verify` | Runs an endpoint atom's curl against sandbox and records the response |
| `/catalogue-lint` | Runs every lint rule and explains each failure |
| `/catalogue-status` | Coverage and verification state by gateway and milestone |
| `/skills-compile` | Compiles, validates and reports which atoms fed which skill |
| `/docs-publish` | Generates navigation, previews, and publishes the Scalar site |
| `/source-check` | Hashes NHA sources, diffs, and opens a pull request on change |
| `/eval-run` | Runs the six eval tasks and records the score |
| `/firstday-test` | Sets up and scores the first-day developer test |
| `/standup` | What moved, what is blocked, what ships at the next checkpoint |
| `/plan-check` | Compares installed plan version against the published manifest |

## Tools

Scripts registered under skills. Each is deterministic and should be called rather than reimplemented.

| Tool | Does |
|---|---|
| `fhir-validate` | Wraps the NRCeS validator over a bundle |
| `callback-tunnel` | Public URL for receiving sandbox callbacks |
| `request-id` | Fresh REQUEST-ID and TIMESTAMP pair |
| `error-decode` | Reads a response, prints the matching error atom |

## Rules that apply no matter which skill you load

1. The Catalogue is the source. Never hand-edit a compiled skill, a navigation file, or llms.txt. Fix the atom and recompile. `portal-architecture`, `portal-planning`, `dpg-governance` and this index are compiled from the plan; edit the plan, not them.
2. Never write an em dash. Not in atoms, not in skills, not in commit messages.
3. Never claim verification you did not observe. `unverified` is an honest word and it is in the schema for a reason.
4. If an atom does not exist for what you are being asked, say so and offer to create it. Do not improvise the answer.
