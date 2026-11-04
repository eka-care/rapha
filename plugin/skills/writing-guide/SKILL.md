---
name: writing-guide
description: The binding prose rules for every word published in the ABDM Catalogue, the compiled skills, and anything else generated from them. Covers sentence construction, banned words, the absolute no em dash rule, acronym handling, honesty about uncertainty, and how to make technical instructions readable by a first-day developer. Use whenever writing or editing any Catalogue prose, when a style lint fails, when reviewing someone's draft for tone, or when configuring the compiler's prose pass.
---

# Writing Guide

Binding, not advisory. The compiler's prose pass is given this file. CI enforces the parts that can be mechanised. Reviewers enforce the rest.

## The rules

**Short sentences. One idea per sentence.** If a sentence has two clauses joined by "and" that could stand alone, it is two sentences.

**Say "you" and "your system".** Say "NHA's gateway", not "the platform". Never "one should". The reader is a specific person with a specific repository open.

**Explain the why once, then get to the how.** A paragraph of motivation before every step is a wall. One paragraph at the top of the atom, then instructions.

**No em dashes.** Not one, anywhere, in any generated content. Use a full stop, a comma, or a colon. CI blocks U+2014 and the build fails. This is not a stylistic preference to be weighed against others.

**No "simply", "just", "obviously", "of course", "merely".** If it were simple they would not be reading. These words tell a stuck reader that being stuck is their fault.

**Every acronym links to the glossary on first use in every atom.** Not the first use in the Catalogue. Readers arrive mid-way from search or from an agent citation.

**Every code sample runs as written** once placeholders are filled. Placeholders are named for what they are and where they came from: `<ACCESS_TOKEN_FROM_SESSIONS_CALL>`, not `<TOKEN>`.

**When we are not sure, we say so, in the frontmatter.** `unverified` on the atom, never narrated at the reader. Never guess and never smooth over a gap with confident phrasing. The portal is published in NHA's voice, so a page cannot tell an integrator that NHA has not run its own endpoint: see `nha-voice` for the ladder that replaces that sentence. This supersedes the earlier rule that put "We have not run this against sandbox yet" in the prose.

**Name the observable, not the feeling.** "You receive a callback with `status: SUCCESS` within 60 seconds", not "it should work".

## Banned constructions

| Do not write | Write instead |
|---|---|
| "Simply call the endpoint" | "Call the endpoint" |
| "This should work" | "You receive X. If you receive Y, see [error atom]" |
| "Various headers are required" | List them |
| "Refer to the documentation" | Link the atom |
| "It is recommended that you" | "Do X, because Y" |
| "In order to" | "To" |
| "Utilise" | "Use" |
| "Leverage the API" | "Call the API" |
| "Seamless integration" | Delete. Say what it does. |
| "Robust error handling" | Name the errors and the handling |

## Voice, with examples

Not this:

> The care context linking process involves several steps which should be followed in order to ensure that the patient's records are properly discoverable within the ABDM ecosystem, and it is recommended that appropriate error handling be implemented.

This:

> Linking a care context tells ABDM that this patient had a visit at your facility. Once linked, other systems can find the record when the patient consents. There are three steps. Each one can fail in a way you can detect, and section 5 lists the failures we see most.

## Handling uncertainty

Three honest positions, and the phrasing for each:

1. **Verified.** "We ran this against sandbox on 25 August. The response is below."
2. **Unverified.** "This follows NHA's published spec. We have not run it against sandbox. Treat the response shape as unconfirmed."
3. **Known broken.** "This endpoint returns 403 in sandbox as of 24 August. NHA has not published a fix. Here is what people do instead."

Never a fourth position where uncertainty is hidden behind fluent prose.

## Writing for two readers at once

Every atom is read by a person and parsed by a compiler. This does not mean writing twice. It means:

- Facts a machine needs go in frontmatter or fenced blocks with a declared schema
- Prose explains, contextualises and warns
- The prose never contradicts the block. If they disagree, the block is authoritative and the prose is a bug.

## Diagrams

- Flows get mermaid sequence diagrams. Concepts get whatever shape explains the idea.
- Every participant is named as the reader would name it: "Your system", "NHA gateway", "Patient's PHR app".
- A diagram that repeats the prose is clutter. A diagram that replaces three paragraphs is doing its job.

## Checklist before you commit

- [ ] No em dash anywhere in the file
- [ ] No banned word from the table
- [ ] Every acronym links to glossary on first use in this file
- [ ] Every placeholder names its source
- [ ] Section 4 states an observation, not a feeling
- [ ] Nothing claims verification that did not happen
- [ ] A person who has never heard of ABDM can read section 1

## Related

- Voice and audience, which outrank every rule here: `nha-voice`
- Structure and schema: `atom-authoring`
- Review process: `atom-review`
- Mechanised checks: `catalogue-linting`
