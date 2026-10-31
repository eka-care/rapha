# Mobile first, an installable web app, and the Android wrap

**Status.** Settled with the owner on 2026-11-01, after the front desk was
agreed. Read `2026-11-01-front-desk-and-design-system-design.md` first; this
changes the shape every screen in it is built to.

## The decision

**This is a mobile-first application, delivered as an installable web app, and
wrapped as an Android app later when a native capability forces it.**

Not because stations lack desktops, though most do. Because of one user.

## Who this is really for

The ASHA. A community health worker covering roughly a thousand people in a
habitation, visiting households, with a phone and frequently no signal at all.

Every other user is inside the building on wifi: the clerk, the nurse, the
medical officer, the pharmacist. For all of them offline is a convenience. For
the ASHA it is the job. `bundles/phc/bundle.yaml` already declares her station
and `questionnaires/phc.schema.household-visit-v1.json` already declares her
form, so she is not a new user — she is the one the interface was never built
for.

**Design for her and the rest come free.** A screen that works on a phone with
no network works on a tablet in a corridor and on a PC at a desk.

## What the web app can and cannot do, said plainly

### It cannot reliably sync in the background

A web app does not get to run when it is closed. Background sync exists on
some browsers and is not dependable. In practice **work syncs when she next
opens the app with a signal.**

This is a design constraint, not a bug to hide. **The app must always show her
what has not gone yet**, on every screen, without being asked. A count she can
see is the difference between trusting it and keeping a paper notebook as well.

### It cannot reach the Aadhaar fingerprint reader on Android

The reader talks to Android applications through a channel a web page has no
access to. Two consequences, and they pull in opposite directions:

- **On a Windows PC** the same class of reader answers on a local connection a
  browser can call. So a desk that wants fingerprint registration wants a PC
  with a browser — one machine, in one room. That, rather than the keyboard,
  is the reason the front desk is the one place that is not a phone.
- **On a phone** it needs the Android wrap below.

**Confirm this with whoever supplies the reader before anybody buys one.**
Behaviour varies between suppliers and this document is reasoning from how the
services are built, not from a device anyone here has held.

### Face authentication is not ours to build

It runs inside the patient's own ABHA application. See the ABDM catalogue's
`nhcx.flow.biometric-face`, which has the patient's app and the Aadhaar face
service talking to each other. Nothing to build here.

### Device biometrics are a different thing, and worth having

Unlocking the app with the phone's own fingerprint sensor proves the person
holding it is the person who enrolled. It does **not** prove an Aadhaar
identity. But the product has **no authentication at all** today, and a nurse
unlocking a shared station phone with her thumb is the cheapest login that
suits a shared device. Recorded here as the strongest candidate for the
authentication decision that is still open, not as a thing being built.

## The Android wrap

**Not now.** Ship the web app first.

Wrapping it later is cheap and wastes none of this work: both routes wrap the
same web application.

- The light route produces an installable package with its own icon, and is
  roughly a day.
- The fuller route adds a native bridge, and is what the three items below
  need.

**Wrap when one of these bites, and not before:**

1. The Aadhaar fingerprint reader on a phone.
2. Recording that survives the screen locking mid-consultation. This product is
   scribe-first, so this one is likely.
3. Storage the operating system will not quietly clear when the phone runs low.

Wrapping early buys release cycles, store review and version drift across every
centre's phones — which is the cost the web app exists to avoid.

## Constraints this adds to every screen

- **Phone width is the target, not the fallback.** Verify at 375px first.
- **No hover-only information anywhere.** It is invisible on a phone.
- **Every tap target at least 44 by 44 CSS pixels.**
- **Keyboard support is an enhancement, never a requirement.** The desk may
  have one; nobody else does. A screen that needs Tab and Enter is a screen the
  nurse cannot use.
- **The microphone outranks the keyboard on a phone.** Typing on a phone is
  slow, this product already has a scribe, and the clerk is talking to the
  patient anyway.

## What is not decided

- **How long a recording may sit on a device.** The outbox is built and proved
  and is switched off for exactly this reason. **Text and audio are different
  questions**: a household visit form is text, and holding text offline does
  not need that signature. Audio does.
- **Patient records resting on a personal phone in a village.** A data
  protection question of the same family as the audio retention one, and
  louder, because the ASHA's phone is hers and not the centre's. Raised here so
  it is not discovered late.
- **Authentication.** Still open, still not an agent's call. See the device
  biometrics note above.
