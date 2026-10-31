# Eka Scribe for PHCs — can it go live on Monday?

Written 31 October 2026. All seventeen build modules are finished. 744 automated
checks pass.

## The short answer

**No, not to a clinician.** The plumbing is built and proven. The medicine is
not signed off, and nothing has ever spoken to a real service.

It is ready to demonstrate. It is not ready to treat a patient with.

## What genuinely works

- A visit becomes the document India's health network accepts. Five versions
  were put through the official structure checker and came back clean,
  including the version that codes nothing and travels as plain text.
- A diagnosis, a medicine and a lab result are checked field by field. A
  symptom the patient denied can no longer be stored as a confirmed disease.
- A lab value that nobody has verified no longer claims it was signed off.
- A health centre can switch off what it does not have — no lab, no pharmacy.
  Three different shapes run one copy of the code.
- Work waits safely when the internet drops. Proven by killing the process
  mid-send: nothing lost, nothing sent twice, nothing reported as sent when it
  was not.

## The five things that stop Monday

### 1. There is no login
One account exists and it holds every permission, including facility
administration. Who you are is decided by a line in a web request. Every
"this is refused" proof in the system is a proof about a program nobody can
actually log in to.

One concrete consequence, found while porting the backend to Go: the route
that serves the compiled rules answers anyone, without even naming a role,
while every neighbouring route refuses an unknown one. What it returns
includes every role's full list of permissions. Harmless while there is no
login at all. It stops being harmless on the day there is one.

**Needed:** a decision on how staff sign in. This is a build job, not a
decision only you can make, but it has not been built.

### 2. Nothing has ever talked to a real service
Not Eka, not the national network, not a real medical dictionary. All 744
checks run entirely on one machine. The speech service runs against a recorded
answer. The code-suggestion service runs against a stand-in.

**Needed:** one real call to each, by someone whose credentials they are,
recording what actually comes back.

### 3. The clinical lists are placeholders, and unsigned
Three conditions. Six medicines. Nothing related to pregnancy at all. Both
lists carry warnings in the files saying they are not real lists.

Consequences today: the antenatal form codes nothing. The long-term-condition
review can code diabetes and nothing else. Everything else a doctor says
travels as plain text — which works, and was built for exactly this, but it
is not coded data.

**Needed:** a named clinical officer to sign off a condition list and a
facility medicine list, against published sources. This has blocked five
modules in a row and is the single highest-value thing outstanding.

### 4. Offline recording is built, proven, and switched off
Holding a recording through an outage means writing a patient's voice to a
clinic's hard drive. Nobody has decided how long we may keep it.

**Needed:** a retention rule somebody signs. Until then this stays off.

### 5. One invented thing is left on screen
The home screen draws a clinic day running 9am to 2pm with a progress bar.
No health centre told us that. It is the last piece of made-up data on any
screen, and it is named rather than hidden.

**Needed:** either remove it, or record each centre's real opening hours.

## Smaller things worth knowing

- A lab result a pathologist verifies still reads "preliminary". We cannot yet
  update a saved row, and this was the safer of the two errors.
- Our lab's words "verified" and "rejected" are not valid national terms.
  Known, flagged, not changed, because renaming them moves other machinery.
- A visit currently leaves as two documents, not one, because the national
  standard publishes no heading for the section that would hold vital signs.
- Validation so far is structural only. It checks the shape of the document,
  not whether every medical code inside it is real.

## What to do first

Get the condition list and the medicine list signed off. That one decision
unblocks more than anything else on this page.
