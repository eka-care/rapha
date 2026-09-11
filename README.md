# Agentic EMR for public health facilities

A composable EMR built as a CARE App. Clinical and administrative capability is
a catalogue of typed operations, and both the rendered interface and the agent
are clients of that catalogue.

The load-bearing rule, from Product Scope v0.1 §4: **if an operation cannot be
invoked identically from the rendered surface and from the agent, it does not
ship.** Here that is not a rule people remember, it is a lint failure. An
operation atom missing `surfaces: [rendered, mcp]` does not compile.

## The shape

```
catalogue/          the operation atoms, the linter, the compiler, the guard
  ops/*.md            one atom per operation. These are the specification.
  vocab.py            capabilities, bundles, states, CARE resources
  build.py            lint and compile atoms -> catalogue.json
  guard.py            the four checks CARE does not do
care_phc/           backend plug: thread state, community layer, connectors
web/                the renderer: a chat workspace drawn from the declarations
care_phc_mcp/       MCP server, tools generated from catalogue.json
questionnaires/     Phase 0 forms, authored not coded
plan-archive/       the ABDM Developer Portal plan this repo used to hold
```

## Why the atoms are the specification

Humans need narrative, warnings and examples. Machines need schemas,
identifiers and exact values. Written separately they drift within a month, so
they are written once. An atom's frontmatter is the machine half and compiles
into the guard's operation table and the MCP tool list. Its body is the human
half and compiles into the tool description an agent reads and the page a
developer reads.

The format is borrowed from the ABDM Catalogue in `plan-archive/`, with a
stricter linter. There, a wrong frontmatter field produces a bad document.
Here it produces a permission hole, so `catalogue/vocab.py` is closed: an atom
naming a capability, state or CARE resource that is not already in those lists
is a failure, never a new entry.

## What we do not build

CARE already provides the renderer (questionnaires), the permission primitive
(`care/security`), the audit log (`care/audit_log`) and the clinical resources.
Eka Scribe already has an official care_fe plugin. What is genuinely missing,
and therefore all this repo contains, is the patient thread that carries state
between stations, the operations that read it, and the community layer.

## Checks

```sh
python3 -m catalogue.build          # lint the atoms, compile catalogue.json
python3 -m catalogue.tests.test_guard
./scripts/plan-check.sh             # the archived portal plan's own gate
```
