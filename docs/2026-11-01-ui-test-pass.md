# A test pass over the screens, 1 November 2026

Run against commit `b3683af` on a clean copy, a fresh database and the seeded
demo day, in a real browser at 1280 and at 375 wide. Every case below was
driven by hand, not asserted from the source. Eight failed.

**This is not a readiness certificate.** It covers what a person can do with
the screens. What stands between this build and a real primary health centre
is mostly not on this list, and is in "What this pass could not test" at the
bottom.

## The cases, and what each one did

### Getting in and getting around

| # | What was tried | Result |
|---|---|---|
| 1 | Open the workspace cold | **Pass.** Home draws, tab reads "Today · Primary health centre" |
| 2 | Every screen has one main region and one top heading | **Pass** on home, the line, the desk, the control panel |
| 3 | Heading levels never skip a step | **Pass** on all four |
| 4 | A skip control is the first thing the keyboard reaches | **Pass** |
| 5 | Something on screen can announce a change to a screen reader | **Pass**, two regions present on every screen |
| 6 | Nothing falls off the edge at 375 wide | **Pass** on all four |
| 7 | Every control that can be reached has a name | **Pass** on the four screens, **FAIL inside the registration form** (see F3) |

### The front desk

| # | What was tried | Result |
|---|---|---|
| 8 | The box has the keyboard on arrival | **Pass** |
| 9 | Typing part of a name finds the patient | **Pass.** "Kam" finds Kamala Devi |
| 10 | Tab reaches the row that registers somebody new | **Pass** |
| 11 | Enter on that row starts the registration | **FAIL — F1** |
| 12 | Clicking that row starts the registration | **Pass** |
| 13 | What was typed becomes the new patient's name | **FAIL — F2** |
| 14 | Skipping the national account reaches the plain form | **Pass** |
| 15 | The form commits and opens the visit | **Pass** |
| 16 | The new patient joins the line with the next number | **Pass.** Savitri Bai, number 7, at the nurse |

### The line

| # | What was tried | Result |
|---|---|---|
| 17 | Numbers are plain and in one sequence | **Pass.** 1 to 7, no letters |
| 18 | Filtering by station narrows the list | **Pass** |
| 19 | Filtering by programme narrows the list | **Pass** |
| 20 | Programme names read as names | **Pass.** General, NCD, RCH |
| 21 | Self registered patients carry a mark and a filter | **Pass** |
| 22 | The list reads on a phone | **Pass** |

### The visit

| # | What was tried | Result |
|---|---|---|
| 23 | A committed registration appears as a card in the visit | **Pass** |
| 24 | The next actions are offered, not taken | **Pass** |
| 25 | The right rail says what is held | **FAIL — F7** |

## The eight failures

**F1. The keyboard path breaks at its first step.** Tab moves to the row that
registers a new patient and the row takes the focus, and then Enter does
nothing. Pressed twice, nothing opened. The mouse works. The whole desk is
designed around "new: Tab, then four answers", and the Tab is where it stops.
*This is the most important one on the list.*

**F2. What the clerk typed is lost.** Type "Savitri Bai", register, skip the
national account, and the form opens with an empty name. The mockup's own
promise is "keeps what you typed as the name". Worse, the form opens already
scolding: "Missing: Full name, Age, Sex, Mobile, Village" before a single key
has been pressed.

**F3. Seven fields in the registration form have no name.** Name, age, sex,
mobile, directory id, village and programme are drawn with a visible label
that is not attached to the field, so anybody using a screen reader is asked
to fill in seven blanks. This is the form the product is used through, and it
is a WCAG 2.2 AA failure. The earlier accessibility sweep missed it because it
never opened the form.

**F4. A warning dominates every search.** An orange block saying the patient
directory could not be asked sits above the results on every search. In this
deployment it is permanently true. Already being fixed.

**F5. The national account step offers two routes that do not exist here.**
"Face Auth" and "Biometric" are drawn as choices. The owner's own decision of
1 November is that face is never ours to build and fingerprint needs a reader
that no desk has. A clerk will pick one and be stuck.

**F6. A clerk is shown a field called "Patient directory id".** Nobody at a
desk has that, and nothing says what it is for.

**F7. The visit screen lists raw machine codes.** The right rail shows about
twenty capability identifiers in a block. The control panel was just fixed for
exactly this; the same words are still raw here.

**F8. A row in the line reads "enc-001 / reception" with no person on it.**
This is the seeded walk-in who has arrived and not been registered, which is a
real state, but two screens disagree about what to call somebody with no name
and one of them shows the internal code.

## What this pass could not test, and it matters more than the eight

- **There is no way to log in.** One account holds every capability, including
  facility administration, and a header decides who you are. Every "this is
  refused" proof in the system is a proof about a program nobody can sign in
  to. This alone keeps it out of a clinic.
- **The clinical lists are three conditions and six medicines.** Approved, and
  far too short to run an outpatient day.
- **The national account runs on staging only.** Production creates permanent
  real health accounts, which is not something to point at a demo.
- **Nothing has been sent to ABDM.** The sending queue is built, proved and
  running, and no document has ever left this machine.
- **The scribe needs the Python engine and a live credential.** No recording
  has gone from this product to the speech service and back.
- **One database file, no backup and no restore story**, and no answer for two
  people editing the same patient at once.
- **No real patient data, no load, no slow network, no power cut.**

## The verdict

**Ready for a walkthrough. Not ready for patients.**

The screens hold up. A clerk can register somebody, they get a number, they
reach the nurse, and the record is what the clerk confirmed. Three of the
eight failures above are an afternoon's work, and F1 and F2 are the ones to
fix first because they break the path the desk was designed around.

What is not ready is underneath. A clinic needs people to sign in as
themselves, a medicine list longer than six, and a believable answer to
"the power went out, where is today's work". None of those is a screen.

---

# Retested after the desk work, same day, at commit `1810de4`

Driven by hand again, same clean copy, same seeded day.

| Was | Now |
|---|---|
| F1 Enter on the register row did nothing | **Fixed.** Tab then Enter opens the registration. The row hung its action off a mouse-only event, so nothing was listening for the click a keyboard makes. |
| F2 the typed name was lost, and the form scolded before anybody typed | **Fixed, both halves.** "Lata Devi" carries into the name field, and the list of what is missing is drawn only once a machine has filled the form in. |
| F3 seven fields had no name | **Fixed at the source.** All nine controls on the registration form report a name. Three of the six field kinds carried no id; every kind does now, so this is fixed for every operation, not just this form. |
| F4 the directory warning dominated every search | **Fixed.** One quiet line under the results, in the screen's own ink, leading with the fact a clerk needs. |
| The screen called itself "Register a new patient" | **Fixed.** It is "Reception", taken from the workflow's first station rather than typed in. |
| Nothing on screen before typing | **Fixed.** Who is waiting and has not been to the desk, who has already been sent on today, and the day's number. |

**A ninth failure, which the first pass missed and which was mine.**
A clerk could type one character into any field of any panel and the rest went
nowhere: name, age, mobile and village typed in turn all ended up in the name
field. The cause was the focus-return fix made earlier the same day. It was
written as an inline function, which React takes apart and puts back after
every keystroke, and the "closing" branch of it fired on every one of those,
dragging the keyboard back onto the dialog. The first test pass did not catch
it because the fields were filled by script rather than typed.

**Still open from the first pass:** F5 (the national account step offers face
and fingerprint, which this deployment has neither of), F6 ("Patient directory
id" shown to a clerk), F7 (raw machine codes in the visit's right rail), F8
(two screens disagree about what to call a thread with nobody on it).

**Found while retesting, and worse than it sounds:** a returning patient is
listed once per visit, because each registration writes a new patient row and
nothing tells the rows apart. Two identical "Kamala Devi" lines, and nothing
merges two records. This is the strongest argument for declaring when somebody
was last here, which is the one thing the mockup's row has that the build
cannot draw.
