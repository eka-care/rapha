---
name: docs-ux
description: The UI and information architecture of the ABDM Developer Portal docs site, in the Mintlify style of code.claude.com/docs and developer.eka.care. Covers the four tabs (Overview, API References, What's New, Support), the module page ladder from overview to test cases, the chrome features (language selector, AI assistant, spotlight search), and the interlinking and chronological-progress rules. Use when deciding where a page goes, how a module's content is ordered, what the navigation generator must produce, or reviewing whether a rendered page follows the site structure.
---

# Docs UX

The site's structure is a specification, not a taste decision. A page in the wrong place, or a module ladder with a rung missing, fails review the same way a lint error does. This skill is the spec; `scalar-docs` covers the tooling that renders it. Plan source: plan#p3-9-docs-ux.

## The reference pattern

Mintlify-style, as seen on code.claude.com/docs and developer.eka.care: top bar with tabs, left sidebar scoped to the active tab, content pane with a right-hand on-page outline. Integrators already know this layout. Do not invent a new one.

For what goes inside a page, the benchmark is
[developers.cloudflare.com](https://developers.cloudflare.com): numbered
step headings that make the table of contents a procedure, a named
`Prerequisites` section, differences in tables rather than prose, and a
`Next steps` list closing every page. See `nha-voice` for the full pattern
list and how ours translate.

## Chrome, on every page

| Feature | What | Delivered by |
|---|---|---|
| Language selector | Locale switcher in the top bar, the `/en/` path segment | Deferred until a second locale exists. English only in V1. |
| Agent path | Not an embedded assistant. Answer synthesis stays in the consuming agent in V1 | The Docs MCP at `/mcp`. An on-site assistant in front of `/api/search` is a later addition, not built yet. |
| Spotlight search | Cmd+K, searches titles and full text | The site's local build-time index (`@easyops-cn/docusaurus-search-local`) |

Code blocks additionally carry their own language tabs (curl, Python, Node) where samples exist in more than one language. That is per-block, not the top-bar selector.

## Four principles

On top of the writing guide (plan#p3-5-writing-guide):

1. **Simple language.** Plain words first, the technical term in brackets on first use, linked to the glossary. Never an em dash.
2. **Interlinked.** Every mention of a concept, endpoint, error, test case or plan section is a hyperlink to its atom or anchor. A mention with no link is a defect: the reader is left to search for something we already wrote.
3. **Chronological.** Pages order by when a developer needs them, not alphabetically. Every page shows previous and next, so the reader is always on a step of a journey.
4. **Progress based.** Long content descends from orientation to verification. The reader who stops halfway has still completed something whole.

## The four tabs

### Tab 1: Overview

The landing tab. In order:

1. ABDM overview, in plain words
2. Get started: sandbox signup, first credentials
3. ABDM glossary
4. Building blocks:
   - Gateways
     - HIE-CM: modules M1 to M4, and the roles that use them (PHR; information management systems: HMIS, EMR, LIMS, pharmacy systems; HIP; HIU)
     - UHI: roles HSPA and EUA
     - NHCX
   - Registries: ABHA; NHPR (HPR, HFR)
5. What you can do with ABDM

### Tab 2: API References

Descend by choice, never by listing everything flat:

1. Choose your gateway: HIE-CM, UHI, NHCX
2. Choose your role: PHR or information management system
3. Choose your module: M1, M2, M3
4. Then the module ladder below

Phase scope renders honestly: HIE-CM M1 to M3 carry content. UHI and M4 pages say Phase 2 and stop. NHCX says out of scope. See the phase table in `abdm-portal-index`.

### Tab 3: What's New

The changelog, fed by the update pipeline (plan#p5-update-pipeline). Newest first, each entry linking to the atoms it touched.

### Tab 4: Support

Contact emails and channels, and links to connectors. Short. A support tab that tries to be documentation duplicates tab 2.

## The module page ladder

Every module (M1, M2, M3) walks the same ladder, in this order. The compiler and reviewer check for it the way they check the five atom sections:

1. **Overview**: building blocks used, prerequisites, each linking to the atom that gets you there
2. **User journey**: flow diagrams (mermaid), one per journey
3. **Use cases**: ABHA creation, scan and share, and the rest, each a page
4. **Agent skills**: skill download CTA and install CLI per agent (Claude, Cursor, others)
5. **Implementation methodology**: mandatory versus optional paths, and how to choose
6. **API sequence**: APIs and webhooks in call order
7. **Per API and webhook**: what to call, what to pass, what comes back
8. **Errors**: mapping and handling, each linking to its error atom
9. **Test cases**, each stated twice:
   - Functional: what the test accomplishes, in a layman's words
   - Technical: the exact success and failure conditions

The ladder is chronological on purpose. A developer reading top to bottom is also integrating in the right order.

## Navigation is still generated

The tab and sidebar tree above is what the navigation generator targets. It is produced from atom frontmatter, never hand-edited (`scalar-docs`). If a page renders in the wrong place, fix its frontmatter, not the config.

## Review checklist

Before approving a rendered page:

- Is it inside the right tab and rung of the ladder?
- Does every mentioned concept, API, error and section link somewhere?
- Are previous and next steps visible and correct?
- Does it read chronologically, no forward references the reader has not met?
- Any em dash, any "simply", any unexplained acronym? Reject.
- Does it read as NHA documenting ABDM, or as someone reporting on NHA's
  documents? Reject the second: see `nha-voice`.

## Related

- Tooling that renders this: `scalar-docs`
- Prose rules: `writing-guide`
- Voice and audience: `nha-voice`
- What each page body contains: `atom-authoring`
- Changelog feed: `update-pipeline`
