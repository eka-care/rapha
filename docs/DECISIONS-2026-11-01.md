# Four decisions taken by the owner, 1 November 2026

Each of these had blocked recorded work, in some cases for five modules
running. They are written here once, and the documents that were waiting on
them point at this file rather than restating it.

## 1. The clinical lists are signed off

`terminology/condition-code.json` and `terminology/medication-code.json` are
approved for use.

**What this does and does not mean.** It removes the blocker, which was that
nobody had approved them. It does not make them complete: the condition list
holds **three** concepts and the medicine list **six**, and neither carries
anything obstetric. The antenatal form still codes nothing, and the long term
condition review can still code diabetes and nothing else.

So the work this unblocks is real, and the next thing those files need is not
another signature but more entries. The warning banners inside them should be
rewritten to say "approved, and short" rather than "not a real list", because
the two sentences warn about different things.

## 2. A recording may be held for 24 hours

This is the retention rule the outbox was waiting for. The outbox is built and
proved — nothing lost, nothing sent twice, nothing reported as sent when it was
not — and was switched off for exactly this reason.

It can now be switched on, with a 24 hour ceiling on any held audio, and that
ceiling enforced rather than documented.

Note the distinction this makes available: **text and audio are now different
questions**, and only audio has a clock on it. A household visit form held
offline in a village is text.

## 3. Staff sign in through login.eka.care

The authentication gap is closed as a decision. Today `caller()` reads an HTTP
header and one account holds every capability, including facility
administration; every "this is refused" proof in the system is a proof about a
program nobody can log in to.

This is the first time the product will talk to a real service.

Two things follow that are not yet decided and are flagged rather than assumed:

- **What a signed-in person maps to.** The kernel's roles and capabilities are
  declared per bundle. Whether login.eka.care carries a role, or whether the
  facility maps an identity to a role locally, is a question this decision does
  not answer.
- **A shared station device.** One phone serves a whole shift. Signing in as a
  person and handing the phone to a colleague is the normal case, not the
  exception, and the audit must record the person rather than the desk.

## 4. Fingerprint is the default, with OTP and face as fallbacks

For proving a patient's identity when registering them.

**This is the right order, and two parts of it cannot be built where they are
wanted yet.** Recorded here so the gap is not rediscovered:

- **Fingerprint cannot be reached from a phone browser.** The Aadhaar reader
  talks to Android applications through a channel a web page has no access to.
  It works from a browser on a Windows PC, where the same class of reader
  answers on a local connection. So a desk wanting fingerprint wants a PC; a
  phone wanting fingerprint needs the Android wrap.
- **Face is not ours to build.** It runs inside the patient's own ABHA
  application. See `nhcx.flow.biometric-face` in the ABDM catalogue.
- **OTP works today**, from anywhere, and is what the desk has until a reader
  is bought.

So the buildable reading of this decision is: **OTP now, fingerprint on the
desk PC as soon as a reader exists, face never — because the patient's own app
already does it.**

Confirm the reader's behaviour with whoever supplies it before buying. The
reasoning above is from how those services are built, not from a device
anybody here has held.
