---
id: phc.inst.consent-speak
type: instrument
kind: spoken-prompt
title: Ask for consent
summary: The clerk says the line; the clerk taps what the patient answered.
operations: [phc.op.patient-register]
fields: [capture_consent, capture_declined]
says: >-
  May we record this visit to write your notes?
  You can say no, or stop it any time.
spoken: false
commit: tap
readback: required
fallback: text
---

## In plain words

The clerk used to read fifty-three words off the screen to every patient, at a
counter, with a queue behind them. Nobody reads fifty-three words the fortieth
time, so the consent became a tick. The agent says the line instead, in the
facility's language, and the clerk taps what the patient answered.

Seventeen words carrying four things: that it is a recording, what it is for,
that saying no is free, and that it can be stopped. Dropping any one of them
makes it not a consent, which is why the linter checks the sentence rather
than trusting a later edit.

## Where this is asked

At reception, on the registration form, not in the consulting room. The
recording it authorises happens later at the doctor. That costs the doctor no
consultation time, and by the time the scribe is available the answer is
already a thread flag.

## The off switch, and why it is off

`spoken: false`, 2026-11-03, the owner's call. The browser no longer reads
the line aloud; the same sentence renders on screen, via `fallback: text`,
for the clerk to say in their own voice. Nothing else changes -- the clerk
still taps what the patient answered, and the four things the sentence
carries are unchanged, because the consent is the sentence and not the
speaker.

A synthesised voice at a reception counter is the wrong instrument for this.
It talks over a queue, it reads in the browser's accent rather than the
patient's language, and it fails silently in more ways than anyone notices:
a muted device, no audio hardware, no Web Speech API, an autoplay policy
refusing an utterance with no gesture behind it. A clerk reading seventeen
words aloud does none of that.

The switch itself stays declared, so turning the voice back on is one word
in this file. The linter refuses a `spoken-prompt` with an empty `says`
whether `spoken` is true or false, because the off switch must always have
something to fall back to.

## What this cannot do

It cannot commit. It sets no flag. The clerk's tap is what raises
`capture.agreed` or `capture.declined`, through the same form validation every
other answer goes through. A prompt that recorded its own answer would be a
consent nobody gave.

## Withdrawal

`phc.op.capture-withdraw` is the doctor's, asks one question, and is absent
unless there is a consent to withdraw. A consent that cannot be withdrawn is
not a consent.
