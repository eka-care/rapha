# Agentic Clinical Workspace
## Complete UI + UX Specification
### v0.3

---

## 0. Document status

**Product:** Agentic EMR / Clinical Workspace  
**Version:** 0.3  
**Status:** Design system + UX specification  
**Primary references:** Current Agentic EMR prototype, Glass Health, Heidi, Slack, Claude-style command interaction patterns  
**Modes:** Light / Dark  
**Primary platforms:** Desktop web application, responsive tablet/mobile

---

# 1. Product definition

## 1.1 Product thesis

The product is not:

- an EMR with a chatbot
- a chatbot with an EMR
- a collection of role-specific modules
- a Scribe product with forms around it

It is:

> **A clinical workspace where patient state, conversation, people, records, AI and actions share one persistent context.**

The product has one persistent interaction layer:

**the clinical thread**

and one universal control surface:

**the composer**

The system should allow a clinician or care worker to move fluidly between:

- conversation
- structured clinical data
- people
- tasks
- handovers
- AI
- clinical actions

without changing products or mentally switching applications.

---

# 2. Core UX principles

## 2.1 One patient, one living thread

Every encounter has a persistent thread.

The thread can contain:

- messages
- comments
- mentions
- handovers
- tasks
- clinical events
- AI observations
- command results
- notes
- prescriptions
- referrals
- documents

The thread is not merely a chat transcript.

It is the conversational representation of clinical work.

---

## 2.2 Patient Lists manage the many

A clinician needs to manage groups of patients without opening every record individually.

Patient Lists are first-class.

Examples:

- Today's OPD
- NCD Clinic
- My patients
- Waiting for vitals
- Critical results
- Lab pending
- Follow-up overdue
- TB cohort
- ANC clinic

A list is a working surface, not merely a filter.

---

## 2.3 Encounters manage the one

A patient can have multiple encounters.

An encounter contains:

- current clinical state
- thread
- structured record
- context
- owners
- contributors
- tasks
- handovers
- clinical artifacts

The current encounter is always the primary workspace when one exists.

---

## 2.4 Handover means responsibility, not location

Handover is not synonymous with station transfer.

A doctor can hand one task to a nurse while retaining ownership of the encounter.

A nurse can send the task back.

An ASHA can be assigned follow-up while the doctor remains encounter owner.

A handover can:

- be commented on
- be reassigned
- be acknowledged
- be reopened
- be resolved

---

## 2.5 The composer is the universal control plane

The bottom composer supports:

- natural-language messages
- `@` people
- `/` commands
- attachments
- voice input / Scribe
- agent invocation

The user should not have to navigate to a module to access a capability.

---

## 2.6 Scribe is a composer mode

Scribe does not get:

- its own navigation item
- its own dashboard
- its own persistent panel
- its own product surface

The microphone lives in the composer.

Narrative conversation is captured there.

The resulting clinical note becomes an artifact in the thread.

---

## 2.7 AI is a participant, not a destination

The agent can:

- answer questions
- summarise
- retrieve patient context
- identify changes
- draft artifacts
- suggest actions
- explain clinical data
- prepare commands

It should not require a dedicated AI page.

AI should feel embedded in the clinical workflow.

---

## 2.8 Structured values remain structured

Use:

- Scribe for narrative
- forms/devices for discrete clinical values
- constrained voice for numeric values where appropriate

Vitals, lab values, doses, stock quantities and deterministic assessment scores require validation before commit.

---

## 2.9 Find before create

Patient search is the default path.

Create patient is the explicit fallback.

A search miss must not silently become patient creation.

---

## 2.10 Read, propose, commit

AI operations are separated into:

1. Read
2. Propose
3. Review
4. Commit

The AI never silently writes clinical data.

---

# 3. Information architecture

```text
APP
│
├── TODAY
│
├── PATIENT LISTS
│   ├── My Lists
│   ├── Shared Lists
│   └── Create List
│
├── PATIENTS
│   └── Patient
│       ├── Overview
│       ├── Encounters
│       ├── Documents
│       └── Timeline
│
├── TASKS
│
├── SEARCH
│
└── SETTINGS
```

Inside an encounter:

```text
ENCOUNTER
│
├── THREAD
│   ├── messages
│   ├── comments
│   ├── handovers
│   ├── tasks
│   ├── clinical events
│   ├── agent insights
│   └── artifacts
│
├── CONTEXT
│
└── RECORD
```

Universal interaction:

```text
                     COMPOSER
                        │
           ┌────────────┼────────────┐
           │            │            │
         text           @            /
           │            │            │
        message       people       actions
           │
           └──────── microphone
                        │
                      Scribe
```

---

# 4. Navigation

## 4.1 Sidebar

Width:

- Desktop: 248px
- Compact: 64px
- Mobile: hidden behind drawer

Structure:

```text
Brand

+ New

Today
Patient Lists
Patients
Tasks
Search

RECENTS

Patient / encounter threads

User / organisation
```

Do not put these into primary navigation:

- Scribe
- Handover
- Vitals
- Lab
- Pharmacy
- ABHA
- AI

These are contextual capabilities.

---

## 4.2 New menu

`+ New`

```text
New

Patient
Patient list
Encounter

Task
Handover

Workspace conversation
```

---

## 4.3 User menu

Bottom-left.

```text
Sam Dennis
Medical Officer
PHC Yadiki

Profile
Switch role
Preferences
Appearance
Keyboard shortcuts
Sign out
```

Role switching is mainly a prototype/admin affordance. Production permissions come from assigned capabilities.

---

# 5. Today screen

## Purpose

Answer:

> What requires my attention right now?

Do not make this a KPI dashboard.

### Structure

```text
TODAY
16 Sep · Wednesday

12 patients
4 need attention
2 handovers awaiting response
3 tasks due today
```

### Needs you

Each item:

```text
Critical result
Ravi Kumar
HbA1c 9.4%
Assigned to you

[Review]
```

```text
Handover awaiting response
@NursePriya
Repeat BP
Ravi Kumar

[Open]
```

```text
Task due
Meena Shah
ANC follow-up

[Open]
```

### Patient Lists

```text
MY LISTS

NCD Clinic
28 patients

Today's OPD
41 patients

High risk
7 patients
```

### Recent

Four most recently active threads.

---

# 6. Patient Lists

## 6.1 List types

### Personal

Visible to current user.

### Shared

Visible to a team or organisation.

### Operational

Examples:

- Waiting for vitals
- Lab pending
- Pharmacy pending
- Critical results

### Cohort

Examples:

- Diabetes
- Hypertension
- ANC
- TB

### Dynamic

Saved query / filter.

---

## 6.2 Patient List screen

Default desktop view:

```text
NCD CLINIC                                  28 patients

[ Search patients... ] [Filter] [Sort] [View] [+ Add]

Patient          Status          Owner          Last activity   Next action
────────────────────────────────────────────────────────────────────────────
Ravi Kumar       In consult      Dr Mehta       3 min           Review result
Lakshmi Devi     Waiting         Nurse Priya     8 min           Record vitals
Meena Shah       Follow-up       ASHA Lakshmi    Yesterday       Book review
```

Required row data:

- patient
- age / sex
- status
- owner
- last activity
- next action

Optional:

- village
- ABHA
- active problem
- vitals
- outstanding tasks
- handover

---

## 6.3 List actions

Row click:

**Open patient**

Context menu:

```text
Open
Open current encounter
Start encounter
Assign
Handover
Record vitals
Start Scribe
Create task
```

---

## 6.4 Create patient list

```text
Create patient list

Name
Description

Patients
○ Search and add
○ Add by filter
○ Import

Visibility
● Only me
○ Team
○ Facility

[Cancel] [Create list]
```

---

## 6.5 Configure columns

Columns are configurable.

Recommended default:

```text
Patient
Status
Owner
Last activity
Next action
```

Do not expose 15 columns by default.

---

# 7. Patient screen

## 7.1 Header

```text
Ravi Kumar
62 M · Male · Yadiki

Diabetes · Hypertension

ABHA linked · Encounter active

[···]
```

Primary action:

```text
Start encounter
```

when no encounter is active.

---

## 7.2 Patient navigation

```text
Overview
Encounters
Timeline
Documents
```

The active encounter opens the workspace.

---

# 8. Encounter workspace

Desktop:

```text
┌────────────────────────────────────────────────────────────┐
│ Ravi Kumar                                                 │
│ Consultation · Active                                      │
├─────────────────────────────────────┬──────────────────────┤
│                                     │                      │
│ THREAD                              │ CONTEXT              │
│                                     │                      │
│ conversation                        │ summary              │
│ clinical events                     │ medications          │
│ handovers                            │ allergies             │
│ tasks                                │ vitals               │
│ agent activity                      │ problems              │
│                                     │ previous visits       │
│                                     │ timeline              │
│                                     │                      │
│                                     │                      │
│ [composer]                          │                      │
└─────────────────────────────────────┴──────────────────────┘
```

The context panel collapses below 1100px.

---

# 9. Thread

## 9.1 Message appearance

Avoid heavy chat bubbles.

Use open message blocks.

```text
Dr Mehta · 10:42

BP is still elevated.
Please repeat after 10 minutes.

Nurse Priya · 10:55

Repeated: 154/94.
Patient asymptomatic.
```

## 9.2 Message anatomy

```text
Actor · time

Content

Optional:
- mentions
- attachments
- comments
- actions
```

---

# 10. Message types

The design system has exactly eight first-class thread objects.

| Type | Function |
|---|---|
| Message | Conversation |
| Comment | Discussion attached to an object |
| Handover | Responsibility transfer |
| Task | Work to be completed |
| Clinical event | Structured clinical data |
| Agent insight | AI observation |
| Command result | Result of a command |
| Artifact | Note, prescription, referral, document |

---

# 11. Comments

Comments belong to the object being discussed.

Example:

```text
LAB RESULT

HbA1c
9.4 %

Dr Mehta
Why is this higher than June?

Nurse Priya
Patient reports missed evening doses.

Dr Mehta
I'll address this today.

3 comments
```

Clicking comments expands them inline.

Comments are not separate channels.

---

# 12. Handover

## 12.1 Handover states

```text
Draft
Open
Acknowledged
In progress
Resolved
Reopened
Reassigned
```

## 12.2 Handover object

```text
┌──────────────────────────────────────────────┐
│ HANDOVER                                     │
│                                              │
│ @DrMehta → @NursePriya                       │
│                                              │
│ Repeat BP after 10 min rest and report back. │
│                                              │
│ Open · Normal priority                       │
│                                              │
│ Reply · Reassign · Resolve                  │
└──────────────────────────────────────────────┘
```

## 12.3 Handover thread

```text
HANDOVER

@DrMehta → @NursePriya

Repeat BP after rest.

Nurse Priya
Done. 154/94.

Dr Mehta
Thanks. Keep patient in observation.

Agent
BP improved from 168/102 → 154/94.

Status: In progress
```

The object remains open until explicitly resolved.

---

# 13. Mentions

Typing `@` opens:

```text
PEOPLE

@Priya
@Mehta
@Lakshmi

ROLES

@Nurse
@Doctor
@ASHA

TEAMS

@NCD-clinic
@Lab
@Pharmacy
```

Mention search must be:

- patient-context aware
- role/capability aware
- permission aware

---

# 14. Slash commands

Typing `/` opens:

```text
PATIENT
/find
/patient
/abha

CLINICAL
/vitals
/assessment
/prescribe
/order
/refer

WORKFLOW
/handover
/assign
/task
/follow-up

DOCUMENT
/note
/referral
/discharge

AI
/summarise
/review
/ask
```

Commands are filtered by:

1. role
2. capability
3. patient state
4. encounter state
5. facility configuration

Do not display unusable commands.

---

# 15. Command grammar

Both forms are valid:

```text
/handover @Priya repeat BP
```

```text
@Priya please repeat BP.
```

```text
Please hand this to Priya and ask her
to repeat the BP.
```

All resolve into the same underlying operation.

---

# 16. Composer

The composer is fixed to the bottom of the thread.

### Default

```text
┌──────────────────────────────────────────────────────────┐
│ Ask, type @someone, or /command...                    ◉ ↑│
└──────────────────────────────────────────────────────────┘
```

### Components

Left:

`+`

Center:

text field

Right:

mic + send

### Context line

```text
Ravi Kumar · Consultation
```

Optional:

```text
[Current encounter] [Previous visits ×3]
```

---

# 17. Composer states

### Empty

```text
Ask, type @someone, or /command...
```

### Typing

Normal text.

### Mentioning

```text
@Pri...
```

Mention menu.

### Commanding

```text
/order...
```

Command menu.

### Replying

```text
Reply to @Priya...
```

### Recording

```text
● Listening · 02:31
```

### Generating

```text
Generating draft...
```

---

# 18. Scribe

Scribe is triggered from the microphone.

## Idle

```text
Ask, type @someone, or /command...            ◉
```

## Recording

Composer expands:

```text
┌──────────────────────────────────────────────────────────┐
│ ● Listening · 02:31                                      │
│                                                          │
│ The consultation is being captured.                      │
│                                                          │
│                                                ■ Stop     │
└──────────────────────────────────────────────────────────┘
```

Live transcript appears in the thread, not in a separate Scribe panel.

---

# 19. Scribe transcript

```text
LIVE TRANSCRIPT

Clinician
How long have you been feeling dizzy?

Patient
About two weeks.

Clinician
Are you taking the BP tablets regularly?

Patient
No, they ran out ten days ago.
```

Use low visual weight.

Transcript is evidence, not the primary clinical record.

---

# 20. Scribe output

After stopping:

```text
AGENT

Drafted from today's conversation

────────────────────────────

Assessment

Uncontrolled hypertension with
recent medication adherence lapse.

Plan

Review medication adherence.
Consider HbA1c.

────────────────────────────

[Edit] [Accept] [Ask AI]
```

Once accepted:

```text
CLINICAL NOTE
Confirmed · Dr Mehta · 11:02
```

The note becomes an artifact in the thread.

---

# 21. Contextual AI

AI may generate:

```text
Agent · 10:58

HbA1c increased from 7.8% to 9.4%.

Relevant:
• adherence lapse
• current medication
• previous result

[Review history]
[Draft assessment]
```

AI responses must display:

- what was read
- what was inferred
- what was proposed

where clinically meaningful.

---

# 22. AI invocation

Supported:

```text
What changed since the last visit?
```

```text
@AI what changed since the last visit?
```

```text
/summarise last 3 visits
```

No dedicated AI page is required.

---

# 23. AI operation model

```text
READ
 ↓
PROPOSE
 ↓
REVIEW
 ↓
COMMIT
```

The product must never blur these states.

Example:

```text
AI

Suggested prescription

Metformin 500 mg BD

[Edit]
[Confirm]
```

After confirmation:

```text
PRESCRIPTION
Confirmed
```

---

# 24. AI provenance

Use meaningful provenance labels.

```text
Captured
Retrieved
Detected
Suggested
Drafted
Confirmed
```

Avoid generic labels such as "AI generated" whenever a more useful explanation exists.

Example:

```text
Assessment

Drafted from:
• today's conversation
• 3 previous visits
• latest HbA1c
```

---

# 25. Context panel

Default sections:

```text
PATIENT

Problems
Medications
Allergies
Vitals
Labs
Previous visits
Documents
Timeline
```

Collapsed sections stay collapsed across the current session.

---

# 26. Timeline

Timeline is longitudinal, not conversational.

```text
16 Sep 2026
Consultation
HbA1c 9.4%
Prescription

12 Jun 2026
Consultation
HbA1c 7.8%

05 Mar 2026
Lab
HbA1c 7.4%
```

Clicking a timeline item jumps to the relevant thread/event.

---

# 27. Clinical events

Clinical events are structured objects in the thread.

### Vitals

```text
VITALS

BP
154 / 94 mmHg

Source
Device · Nurse Priya

10:55
```

### Lab

```text
LAB RESULT

HbA1c
9.4 %

Source
Lab analyser

Critical
```

### Prescription

```text
PRESCRIPTION

Metformin 500 mg
1-0-1 × 30 days

Confirmed
Dr Mehta
```

### ABDM event

```text
ABHA

Linked
16 Sep · 09:42
```

---

# 28. Task system

Tasks are first-class but should originate naturally from work.

Example:

```text
Agent

Follow-up required.

[Create task]
```

Creates:

```text
TASK

Follow up BP in 7 days

Patient
Ravi Kumar

Owner
@ASHA-Lakshmi

Due
23 Sep

Status
Open
```

Tasks can exist without a handover.

---

# 29. Task screen

```text
TASKS

My tasks   Team   All

TODAY

Follow up BP
Ravi Kumar
Due 10:00
@ASHA Lakshmi

Review HbA1c
Meena Shah
Due 12:30

Awaiting response
Lakshmi Devi
@NursePriya
```

Filters:

- owner
- due
- patient
- status
- task type

---

# 30. Station model

Stations represent location of work:

```text
Reception
Vitals
Consultation
Lab
Pharmacy
Follow-up
```

Stations do not define ownership.

A single person may operate multiple stations.

---

# 31. Ownership model

Every encounter can contain:

```text
Primary owner
Care team
Open handovers
Open tasks
Contributors
```

Example:

```text
OWNER
Dr Mehta

CARE TEAM
Dr Mehta
Nurse Priya
ASHA Lakshmi
Lab

OPEN HANDOVERS
@NursePriya
Repeat BP

@ASHA-Lakshmi
Follow up in 7 days
```

---

# 32. Role and capability model

Person:

```text
Sam
```

holds one or more bundles:

```text
Medical Officer
Nurse
```

Each bundle maps to capabilities.

Example:

```text
patient.find
patient.register
abha.link
vitals.record
assessment.record
encounter.document
rx.prescribe
lab.order
lab.result.enter
lab.result.validate
pharmacy.dispense
visit.household
appointment.book
facility.admin
reporting.view
```

The UI should not expose raw capability IDs to normal users.

Instead:

```text
/prescribe
/order
/vitals
```

---

# 33. State-driven actions

Actions appear according to:

- patient state
- encounter state
- role
- capability
- facility configuration

Maximum visible quick actions:

**6**

Everything else goes behind `/`.

Examples:

```text
Registered, no vitals
→ Record vitals

Vitals abnormal
→ Review flagged vitals

Consultation active
→ Scribe
→ Prescribe
→ Order
→ Refer

Lab ordered
→ Enter result

Result critical
→ Review result

Rx confirmed
→ Dispense
```

Ordering is deterministic and auditable.

---

# 34. Quick actions

Quick action row:

```text
[Scribe] [Review result] [Prescribe] [Order] [Handover] ···
```

The actions are not navigation.

They execute or open the appropriate contextual flow.

---

# 35. Patient search

Global shortcut:

`⌘K`

Searches:

- patients
- patient lists
- encounters
- tasks
- people
- commands

Search result:

```text
Ravi Kumar
62 M · Yadiki

Current
Consultation · Needs review

Last visit
12 Jun 2026

[Open]
```

---

# 36. Find before create

Search fields:

- name
- phone
- ABHA
- village
- token
- approximate age

Search should tolerate:

- transliteration
- shared household phone numbers
- surname differences
- partial names
- approximate age

Create requires explicit confirmation.

---

# 37. Registration

Default:

```text
Find patient
↓
Match?
↓
Open existing
```

No match:

```text
No matching patient.

[Register new patient]
```

ABHA:

```text
ABHA create/link
```

is offered but does not block care.

Register without ABHA:

```text
ABHA pending
```

The agent places the patient into an unlinked worklist.

---

# 38. ABHA UX

ABHA is infrastructure.

Visible patient state:

```text
ABHA linked
```

or:

```text
ABHA not linked
```

Action:

```text
Link ABHA
```

Do not create an "ABHA dashboard" for ordinary users.

---

# 39. Forms

Forms are used for:

- vitals
- lab results
- prescriptions
- stock quantities
- demographic data
- assessment instruments

Form rules:

- compact
- clear labels
- validation close to field
- keyboard accessible
- numeric fields use tabular numerals
- no excessive card nesting

---

# 40. Clinical numeric input

Example:

```text
Blood pressure

Systolic
[ 154 ] mmHg

Diastolic
[ 94 ] mmHg

[Save]
```

If outside valid range:

```text
Check value
1540 mmHg is outside the expected range.
```

Critical result:

```text
Critical value

HbA1c 9.4%

Confirm readback before commit.

☐ I have verified this result.

[Commit result]
```

---

# 41. Offline mode

Offline is a product state.

Display:

```text
Offline
Changes will sync when connection returns.
```

Every offline write receives:

- local timestamp
- actor
- object ID
- sync state

Example:

```text
TASK
Queued offline
```

The user must never wonder whether an operation was saved.

---

# 42. Sync states

```text
Saved
Syncing
Queued offline
Synced
Conflict
Needs review
```

Conflict requires explicit resolution.

Never silently overwrite clinical information.

---

# 43. Audit

Audit is not a normal user-facing feature but is available where trust matters.

Example:

```text
HbA1c 9.4%

Entered by
Lab Tech

10:58

Validated by
Lab In-charge

11:01
```

Clinical corrections use amendment rather than silent overwrite.

---

# 44. Design tokens

## Typography

Primary:

**Inter** or **Geist Sans**

Recommended:

**Geist Sans**

Monospace:

**Geist Mono** or system monospace

### Scale

```text
Display     28 / 34 / 600
Page        22 / 28 / 600
Section     17 / 24 / 600
Body        14 / 21 / 400
Body strong 14 / 21 / 550
Label       13 / 18 / 500
Metadata    12 / 17 / 400
Micro       11 / 15 / 500
```

---

# 45. Spacing scale

Base unit:

**4px**

```text
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

---

# 46. Radius

```text
--radius-sm: 6px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-pill: 999px;
```

Use:

- 6px for controls
- 8px for inputs
- 12px for panels
- 16px for prominent surfaces
- pill only for compact statuses/filters

---

# 47. Shadow

Prefer borders over shadows.

```text
--shadow-sm:
0 1px 2px rgba(20,18,15,.05);

--shadow-md:
0 6px 18px rgba(20,18,15,.08);

--shadow-lg:
0 16px 48px rgba(20,18,15,.14);

--shadow-overlay:
0 24px 70px rgba(20,18,15,.20);
```

Use shadows only for:

- popovers
- menus
- dialogs
- floating surfaces

---

# 48. Light colour system

```css
:root {
  --color-bg-canvas: #F7F5F1;
  --color-bg-surface: #FFFDFC;
  --color-bg-subtle: #F1EEE8;
  --color-bg-hover: #ECE8E1;
  --color-bg-selected: #E7E4DE;

  --color-border-subtle: #E4DFD6;
  --color-border-strong: #D1CBC1;

  --color-text-primary: #1C1B19;
  --color-text-secondary: #625F59;
  --color-text-tertiary: #8D8981;
  --color-text-disabled: #AAA69F;

  --color-accent: #26231F;
  --color-accent-soft: #ECE8E1;

  --color-agent: #72798A;
  --color-agent-soft: #ECEEF2;

  --color-abdm: #657FB8;
  --color-abdm-soft: #EDF1F8;
  --color-abdm-border: #D7E0F0;

  --color-success: #74856B;
  --color-success-soft: #EFF2EC;
  --color-success-border: #DCE3D6;

  --color-warning: #9A7B48;
  --color-warning-soft: #FAF3E5;
  --color-warning-border: #EBDDC2;

  --color-critical: #A96E67;
  --color-critical-soft: #F8ECEA;
  --color-critical-border: #EACFCB;
}
```

---

# 49. Dark colour system

```css
[data-theme="dark"] {
  --color-bg-canvas: #111210;
  --color-bg-surface: #181A18;
  --color-bg-subtle: #202320;
  --color-bg-hover: #272A27;
  --color-bg-selected: #2D312D;

  --color-border-subtle: #2C302C;
  --color-border-strong: #3B403B;

  --color-text-primary: #ECEDE9;
  --color-text-secondary: #A7ABA4;
  --color-text-tertiary: #777C76;
  --color-text-disabled: #555A55;

  --color-accent: #F0EEE8;
  --color-accent-soft: #2A2925;

  --color-agent: #A2A9BA;
  --color-agent-soft: #292D36;

  --color-abdm: #91A8DE;
  --color-abdm-soft: #1B2233;
  --color-abdm-border: #303B58;

  --color-success: #9CAF8C;
  --color-success-soft: #1D261A;
  --color-success-border: #33422E;

  --color-warning: #D4AA5C;
  --color-warning-soft: #292216;
  --color-warning-border: #514224;

  --color-critical: #DA9185;
  --color-critical-soft: #2B1B18;
  --color-critical-border: #53302A;
}
```

---

# 50. Semantic colour rules

Colour means something.

| Colour | Meaning |
|---|---|
| Neutral | Default / informational |
| Agent blue-grey | Agent activity |
| Blue | ABDM / external identity |
| Green | Confirmed / success |
| Amber | Attention / pending |
| Red | Critical / destructive |

Do not use semantic colours decoratively.

Do not use purple gradients for AI.

Do not use saturated colours on ordinary UI.

---

# 51. CSS foundation

```css
:root {
  --font-sans:
    "Geist",
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;

  --font-mono:
    "Geist Mono",
    ui-monospace,
    SFMono-Regular,
    Menlo,
    Monaco,
    Consolas,
    monospace;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-pill: 999px;

  --duration-fast: 100ms;
  --duration-normal: 180ms;
  --duration-slow: 240ms;

  --ease-out: cubic-bezier(.22,.61,.36,1);

  --shadow-sm:
    0 1px 2px rgba(20,18,15,.05);

  --shadow-md:
    0 6px 18px rgba(20,18,15,.08);

  --shadow-lg:
    0 16px 48px rgba(20,18,15,.14);
}

* {
  box-sizing: border-box;
}

html,
body {
  width: 100%;
  height: 100%;
}

body {
  margin: 0;
  background: var(--color-bg-canvas);
  color: var(--color-text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

button,
input,
textarea,
select {
  font: inherit;
}

button {
  color: inherit;
}

:focus-visible {
  outline: 2px solid var(--color-agent);
  outline-offset: 2px;
}
```

---

# 52. App shell CSS

```css
.app-shell {
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--color-bg-subtle);
  border-right: 1px solid var(--color-border-subtle);
}

.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.topbar {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  background: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border-subtle);
}

.workspace {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
```

---

# 53. Sidebar CSS

```css
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 13px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
}

.nav-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}

.nav-item[data-active="true"] {
  background: var(--color-bg-selected);
  color: var(--color-text-primary);
  font-weight: 600;
}
```

---

# 54. Patient List CSS

```css
.patient-list {
  width: 100%;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--color-bg-surface);
}

.patient-row {
  display: grid;
  grid-template-columns:
    minmax(220px, 1.7fr)
    minmax(130px, 1fr)
    minmax(130px, 1fr)
    minmax(140px, 1fr)
    minmax(160px, 1fr);

  align-items: center;
  gap: 16px;
  min-height: 58px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  cursor: pointer;
}

.patient-row:last-child {
  border-bottom: 0;
}

.patient-row:hover {
  background: var(--color-bg-hover);
}
```

---

# 55. Thread CSS

```css
.thread {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

.message {
  display: flex;
  gap: 12px;
  max-width: 760px;
}

.message-content {
  min-width: 0;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 5px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}

.message-body {
  color: var(--color-text-secondary);
  font-size: 14px;
  line-height: 1.65;
}

.message-body strong {
  color: var(--color-text-primary);
}
```

---

# 56. Thread object CSS

```css
.thread-object {
  width: min(100%, 760px);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  overflow: hidden;
}

.thread-object__header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
}

.thread-object__body {
  padding: 14px 16px;
}

.thread-object__footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 12px;
  border-top: 1px solid var(--color-border-subtle);
  color: var(--color-text-tertiary);
  font-size: 12px;
}
```

---

# 57. Handover CSS

```css
.handover {
  border-color: var(--color-agent);
  background: var(--color-bg-surface);
}

.handover__route {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-primary);
  font-weight: 600;
}

.handover__message {
  margin-top: 10px;
  color: var(--color-text-secondary);
}

.handover__state {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--color-text-tertiary);
  font-size: 12px;
}
```

---

# 58. Composer CSS

```css
.composer {
  position: sticky;
  bottom: 0;
  z-index: 20;
  padding: 12px 20px 16px;
  background:
    linear-gradient(
      to top,
      var(--color-bg-surface) 72%,
      transparent
    );
}

.composer__inner {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 900px;
  min-height: 48px;
  margin: 0 auto;
  padding: 5px 6px 5px 12px;
  border: 1px solid var(--color-border-strong);
  border-radius: 14px;
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-md);
}

.composer__input {
  flex: 1;
  min-width: 0;
  padding: 8px 4px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--color-text-primary);
  resize: none;
}

.composer__input::placeholder {
  color: var(--color-text-tertiary);
}

.composer__mic,
.composer__send {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.composer__mic:hover,
.composer__send:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-primary);
}
```

---

# 59. Composer recording CSS

```css
.composer[data-state="recording"] .composer__inner {
  border-color: var(--color-critical);
}

.composer__recording {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-critical);
  font-size: 12px;
  font-weight: 600;
}

.recording-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse-recording 1.2s ease-in-out infinite;
}

@keyframes pulse-recording {
  0%, 100% {
    opacity: 1;
  }

  50% {
    opacity: .35;
  }
}

@media (prefers-reduced-motion: reduce) {
  .recording-dot {
    animation: none;
  }
}
```

---

# 60. Mention / command menu

```css
.composer-menu {
  position: absolute;
  right: 20px;
  bottom: calc(100% + 8px);
  width: min(420px, calc(100vw - 40px));
  max-height: 360px;
  overflow-y: auto;
  padding: 6px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  box-shadow: var(--shadow-lg);
}

.composer-menu__section {
  padding: 8px 10px 5px;
  color: var(--color-text-tertiary);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.composer-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.composer-menu__item:hover,
.composer-menu__item[data-active="true"] {
  background: var(--color-bg-hover);
}
```

---

# 61. Chips

```css
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-pill);
  background: var(--color-bg-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 500;
}
```

---

# 62. Status chip

```css
.status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 22px;
  padding: 2px 7px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  font-size: 11px;
  font-weight: 600;
}

.status[data-tone="success"] {
  background: var(--color-success-soft);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.status[data-tone="warning"] {
  background: var(--color-warning-soft);
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

.status[data-tone="critical"] {
  background: var(--color-critical-soft);
  border-color: var(--color-critical-border);
  color: var(--color-critical);
}

.status[data-tone="agent"] {
  background: var(--color-agent-soft);
  border-color: transparent;
  color: var(--color-agent);
}
```

---

# 63. Dialogs

Dialogs are only for operations requiring:

- confirmation
- structured input
- irreversible action
- detailed review

Do not use dialogs for routine conversation.

Dialog structure:

```text
Title
Description

Content

Cancel
Primary action
```

---

# 64. Drawer

Use drawers for contextual material:

- patient context
- timeline
- attachments
- comments
- command details

Drawers should preserve thread position.

---

# 65. Dark mode

Dark mode is not an inverted light mode.

Use:

```text
Canvas
↓
Surface
↓
Subtle surface
↓
Raised surface
```

Hierarchy comes primarily from luminosity and border contrast.

Do not use black + white card inversion.

---

# 66. Responsive behaviour

## Desktop > 1280px

- 248px sidebar
- full thread
- context panel
- patient list table

## 1000–1280px

- sidebar
- thread
- context collapsible

## 768–1000px

- sidebar collapses
- context becomes drawer
- patient list becomes compact table

## <768px

- single column
- bottom composer fixed
- context in sheet
- patient list becomes compact cards

---

# 67. Mobile patient list

```text
NCD Clinic
28 patients

[Search]

Ravi Kumar
62 M
In consultation
Needs review

Lakshmi Devi
52 F
Waiting for vitals
```

Do not force desktop tables onto mobile.

---

# 68. Accessibility

Target:

**WCAG 2.2 AA**

Requirements:

- keyboard navigation
- visible focus states
- semantic HTML
- aria labels for icon-only buttons
- minimum 44px touch target
- reduced motion
- non-colour status communication
- strong contrast
- error text adjacent to fields
- screen-reader support for live agent states

---

# 69. Motion

Motion communicates state.

```text
Hover      100ms
Press       80ms
Popover    160ms
Drawer     200ms
Dialog     180ms
```

Use:

- opacity
- small translation
- height expansion

Avoid:

- bounce
- excessive spring
- glow
- large scale effects

---

# 70. Icons

Recommended:

**Lucide**

Properties:

```text
16px default
20px emphasis
1.5px stroke
rounded joins
no mixed icon families
```

AI should not rely on sparkle icons.

Use a dedicated agent glyph.

---

# 71. Brand / AI visual identity

The product's AI feeling should come from:

- persistent context
- intelligent ordering
- natural-language actions
- command palette
- inline suggestions
- provenance
- state awareness
- cross-station continuity

It should not come from:

- gradients
- glowing borders
- purple backgrounds
- robot avatars
- excessive sparkle icons

---

# 72. Empty states

### Patient list

```text
No patients yet.

Add patients or create a filtered list.
```

### Thread

```text
Start the encounter.

Type a message, @mention someone,
use / for an action, or dictate.
```

### Tasks

```text
You're clear.

Nothing needs your attention.
```

---

# 73. Loading states

Lists:

**Skeleton rows**

Thread:

```text
Agent is reading patient context
```

Scribe:

```text
Listening · 02:31
```

Generation:

```text
Drafting clinical note...
```

Never use full-page spinners for normal loading.

---

# 74. Offline state

Persistent but unobtrusive:

```text
Offline
Changes will sync when connection returns.
```

Operation state:

```text
Queued offline
```

After connection:

```text
Syncing
```

then:

```text
Synced
```

---

# 75. Error states

Errors should state:

1. what failed
2. whether the record changed
3. what to do next

Example:

```text
Unable to submit lab result.

The result was not committed.

[Retry]
```

Never:

```text
Something went wrong.
```

---

# 76. Undo

Use undo for reversible actions.

Example:

```text
Prescription confirmed.

Undo · 5 min
```

Irreversible actions require explicit confirmation before commit.

---

# 77. Notification rules

Notifications should resolve to an object.

Bad:

```text
You have a notification.
```

Good:

```text
Critical result
Ravi Kumar
HbA1c 9.4%

[Review]
```

Clicking takes the user directly to the relevant thread object.

---

# 78. Data hierarchy

The system should distinguish:

```text
Patient
Encounter
Thread
Event
Artifact
Task
Handover
```

These are different domain objects.

Avoid representing every object as a "message."

---

# 79. Domain object anatomy

Every object should support:

```text
id
patientId
encounterId
actor
createdAt
updatedAt
status
source
provenance
comments
audit
```

Actions should operate against object IDs, not rendered UI.

---

# 80. Clinical record model

The clinical record contains confirmed structured information.

The thread contains discussion around that information.

Example:

```text
THREAD
"BP is still high."

        ↓

CLINICAL EVENT
BP 154/94

        ↓

DISCUSSION
"Repeat after rest."

        ↓

TASK
Repeat BP

        ↓

CONFIRMED RECORD
BP 154/94
```

---

# 81. Information architecture rule

Three questions must remain independent:

```text
WHERE IS THE PATIENT?
Station

WHO OWNS THE WORK?
Owner / handover

WHAT HAS HAPPENED?
Thread / record
```

This is the core architecture.

---

# 82. UX flow: registration

```text
Open search
↓
Search patient
↓
Matches?
├── Yes → Select
│          ↓
│       Existing patient
│
└── No → Explicit "Register new"
           ↓
        Registration
           ↓
        ABHA optional
           ↓
        Queue
```

---

# 83. UX flow: consultation

```text
Open current encounter
↓
Thread
↓
Composer
↓
Mic
↓
Consent
↓
Record
↓
Stop
↓
Draft note
↓
Review
↓
Accept
↓
Clinical note confirmed
↓
Prescription / order / referral
```

---

# 84. UX flow: handover

```text
Thread
↓
/handover
↓
@person / @team / @role
↓
Reason / request
↓
Send
↓
Open
↓
Acknowledged
↓
Reply / comment / update
↓
Resolve
```

Handover can loop:

```text
Resolve
↓
New information
↓
Reopen
```

---

# 85. UX flow: task

```text
Thread
↓
/task
↓
Action
↓
@owner
↓
Due date
↓
Create
↓
Owner receives task
↓
Work
↓
Comment
↓
Complete
```

---

# 86. UX flow: clinical command

Example:

```text
/order HbA1c
```

```text
COMMAND
HbA1c

Patient
Ravi Kumar

Priority
Routine

[Edit] [Confirm]
```

After confirmation:

```text
LAB ORDERED

Assigned to
Lab

[View worklist]
```

---

# 87. UX flow: AI query

```text
"What changed since the last visit?"
```

AI:

```text
HbA1c
7.8% → 9.4%

Medication adherence
Patient reported missing evening doses.

Last documented visit
12 Jun 2026
```

Sources should be inspectable.

No unsupported clinical claim.

---

# 88. Patient list + workflow

Patient lists should preserve:

- current filter
- sort
- scroll position
- selected columns

Sequence:

```text
Patient List
 ↓
Ravi Kumar
 ↓
Resolve work
 ↓
Back
 ↓
Ravi row updates
 ↓
Next patient
```

---

# 89. Design-system component inventory

## Foundations

- colour tokens
- typography
- spacing
- radius
- shadows
- motion
- breakpoints
- iconography

## Shell

- sidebar
- topbar
- user switcher
- command palette
- mobile navigation

## Lists

- patient list
- task list
- result list
- work queue
- filters
- sorting
- saved views

## Clinical

- patient header
- encounter header
- timeline
- vitals
- lab result
- medication
- prescription
- referral
- document
- problem
- allergy

## Thread

- message
- comment
- handover
- task
- clinical event
- agent insight
- command result
- artifact

## Composer

- text input
- @ mention
- / command
- context chips
- attachment
- microphone
- recording state
- generation state

## Interaction

- buttons
- inputs
- textarea
- select
- popover
- dropdown
- dialog
- drawer
- toast
- tooltip
- skeleton

---

# 90. Component state matrix

Every interactive component defines:

```text
default
hover
focus
pressed
selected
disabled
loading
error
success
light
dark
```

AI components additionally define:

```text
reading
drafting
drafted
needs-review
accepted
rejected
edited
source-available
source-unavailable
```

---

# 91. Naming conventions

Use semantic names.

Good:

```text
--color-text-primary
--color-border-subtle
--color-agent-soft
```

Bad:

```text
--blue-500
--grey-200
--purple-300
```

Components:

```text
PatientList
PatientRow
EncounterThread
ThreadMessage
ThreadObject
HandoverCard
TaskCard
Composer
MentionMenu
CommandMenu
ClinicalEvent
AgentInsight
```

---

# 92. Design principles for the frontend

1. Components do not own clinical rules.
2. Clinical rules live in operation/state logic.
3. Components render state.
4. Commands resolve to operations.
5. Natural-language actions resolve to the same operations.
6. AI proposals are never direct commits.
7. The audit layer receives every write.
8. Permission checks run server-side.
9. UI permission states are derived from authoritative capability data.
10. Offline operations are explicit and recoverable.

---

# 93. Product language

Use:

- patient
- encounter
- thread
- owner
- team
- task
- handover
- context
- event
- draft
- confirm
- review
- source
- record

Avoid:

- AI copilot
- magic
- smart card
- intelligent widget
- workflow automation
- AI powered

unless marketing context requires it.

---

# 94. UI writing style

Short.

Concrete.

Operational.

Prefer:

> Review critical result

over:

> Let AI help you review this critical result

Prefer:

> Drafted from today's conversation

over:

> Your AI assistant has intelligently created a draft

Prefer:

> 2 handovers awaiting response

over:

> You have some important pending collaboration requests

---

# 95. Accessibility language

Avoid:

- "green means good"
- "red means bad"

Use:

```text
Confirmed
Pending
Critical
```

and reinforce with:

- text
- icons
- position
- labels

---

# 96. AI safety UX

AI-generated content must expose enough provenance to allow review.

For important outputs:

```text
Drafted from

Current encounter
3 previous visits
Latest lab result
Medication list
```

For protocol guidance:

```text
Source
Approved protocol library
v2026.1
```

For unsupported questions:

```text
No supported source found.

I did not write to the record.
```

---

# 97. Clinical action confirmation

Before commit:

```text
ACTION

Prescription

Amlodipine 5 mg
1-0-0 × 30 days

Metformin 500 mg
1-0-1 × 30 days

[Cancel]
[Confirm prescription]
```

After commit:

```text
Prescription confirmed

Rx is now available to Pharmacy.
```

---

# 98. Dark/light QA

Every component must be reviewed in:

- light
- dark
- hover
- focus
- disabled
- critical
- agent
- empty
- loading

No component should rely on colour that disappears in dark mode.

---

# 99. Interaction hierarchy

The visual hierarchy should generally be:

```text
1. Patient identity
2. Current clinical state
3. Required action
4. Clinical content
5. Context
6. Metadata
7. System information
```

AI is not automatically above clinical content.

---

# 100. The final design language

The product should feel:

**Quiet**

because healthcare interfaces already contain enough noise.

**Precise**

because clinical information cannot behave like generic chat.

**Fluid**

because clinical work moves between people and stations.

**Human**

because patients are not workflow objects.

**Intelligent**

because the system remembers, connects and acts on context.

The visual expression:

```text
warm neutral surfaces
+
fine borders
+
strong typography
+
low colour saturation
+
minimal shadow
+
one restrained agent colour
+
high information density
+
large conversational surface
```

The interaction expression:

```text
Patient Lists
        ↓
Patient
        ↓
Encounter
        ↓
Thread
        ↓
Composer
   ┌────┼────┐
   @    /    mic
   │    │     │
people actions Scribe
        │
       AI
        │
       state
        │
     next action
```

The product should ultimately feel like:

> **one clinical workspace, with conversation as its universal interface.**

---

# 101. Implementation priority

## Phase 1: Foundation

- tokens
- light/dark
- typography
- shell
- sidebar
- command palette
- patient list
- patient header
- thread
- composer

## Phase 2: Clinical thread

- messages
- mentions
- commands
- handovers
- comments
- tasks
- clinical events
- artifacts

## Phase 3: Scribe

- composer microphone
- recording state
- transcript
- draft note
- edit
- confirm

## Phase 4: Clinical actions

- vitals
- prescription
- lab
- result
- pharmacy
- referral
- follow-up

## Phase 5: Intelligence

- agent context
- agent insights
- source provenance
- action proposals
- patient summaries
- list intelligence

## Phase 6: Operational intelligence

- saved patient lists
- dynamic cohorts
- work queues
- cross-patient tasks
- facility views
- analytics

---

# 102. Acceptance criteria

The design is successful when:

### Patient management

- A repeat patient can be found faster than a new patient can be registered.
- Patient Lists can be created, filtered and shared.
- Returning to a list preserves position.

### Clinical work

- A user can move through an encounter without navigating between modules.
- Structured clinical values remain structured.
- The thread contains the complete context of the episode.

### Collaboration

- A user can `@mention` another user.
- A user can mention roles and teams.
- Handover can move back and forth.
- Handover supports comments.
- Tasks can be assigned independently of handover.

### AI

- AI is available from the composer.
- `/` exposes contextual actions.
- `@AI` is supported.
- AI can read context without automatically writing.
- AI proposals require confirmation.

### Scribe

- Scribe starts from the composer.
- Scribe remains inside the thread.
- The transcript is available for verification.
- The generated note is a draft.
- The clinical note enters the record only after confirmation.

### Trust

- Provenance is visible for clinically significant AI output.
- Audit information can be inspected.
- Offline writes show explicit status.
- No silent clinical overwrites occur.

### Visual

- Light and dark modes are visually coherent.
- Semantic colour is restrained.
- No component depends on heavy shadow for hierarchy.
- AI does not rely on decorative "AI" aesthetics.
- The interface remains readable at high information density.

---

# 103. North-star interaction

The complete interaction should be as simple as:

```text
Find patient
    ↓
Open encounter
    ↓
Talk / type / @ / /
    ↓
Agent understands context
    ↓
People collaborate in the thread
    ↓
Clinical actions become structured objects
    ↓
Responsibility moves through handover / tasks
    ↓
Patient state updates
    ↓
Next action surfaces automatically
```

That is the product.

Everything else is implementation.
