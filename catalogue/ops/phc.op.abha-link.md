---
id: phc.op.abha-link
type: operation
kind: write
short: Link ABHA
title: Create or link an ABHA
summary: Link this patient to their national health account.
capability: abha.link
scope_qualifier: null
station: reception
instrument: form
preconditions:
  - registered
  - not abha.linked
irreversibility: irreversible
input: phc.schema.abha-link-v1
writes: [patient]
mapping:
  # The method and the consent are the reason the write is allowed, not part
  # of the row. Both are on the audit line for this operation.
  ignored: [method, consent_given]
  records:
    - resource: patient
      fields:
        created_by: {actor: id}
        abha_number: {answer: abha_number}
emits: [abha.linked]
surfaces: [rendered, mcp]
verified:
  status: unverified
  against: care-local
  # Auth to Eka ABDM Connect IS verified against api.eka.care on 2026-09-10:
  # login returns access_token, expires_in, refresh_token, and one token serves
  # many calls. The operation itself is not verified, because the enrolment
  # journey needs a live OTP and the gateway hop to NHA was failing. See
  # "When it goes wrong".
related:
  operations: [phc.op.patient-register]
  concepts: []
---

## In plain words

An ABHA is the patient's national health number. Linking one to their record
here is how a hospital in another district finds their history later.

## Before you start

The patient must be registered. Registration comes first and is never blocked
by this: a patient with no ABHA is registered, given a token, and seen.
Addendum SSB.3 makes register now and link later a first class path, and the
gap becomes a worklist item rather than a queue blocker at the counter.

You need `abha.link`. The patient must consent and must be present, because
the journey involves one time passwords sent to them.

## What happens

Eka's own ABHA web SDK is mounted on this screen, not a form this product
drew. It is skippable, by the SDK's own Skip ABHA. If the patient declines or
has no time, the record is flagged ABHA pending and joins the unlinked
worklist, which whoever is free picks up at the next contact.

If the patient proceeds, the journey returns an identifier, it lands in the
field below it as a readback, and the tap on this panel is what writes it to
the patient record. The other two answers on this form are asked of the person
who watched the journey: the success payload says neither whether an account
was created or logged into, nor that the patient consented, and filling them in
from a guess would record the software's answer as the clerk's.

## How you know it worked

The patient record carries an ABHA number and the thread stops showing the
link action. The unlinked worklist no longer lists this patient.

## When it goes wrong

- **This operation is irreversible.** A duplicate ABHA cannot be undone, only
  deprecated. The confirm is explicit and un-prefilled, per v0.1 SS5, and it
  cannot be satisfied by an agent. There is no `confirm` verb on the machine
  surface for this or any other write.
- **The patient may already have one.** Search before creating. Most footfall
  at an outpatient department is repeat patients, and defaulting to create is
  how duplicate records get manufactured. ABDM enforces this itself: on OTP
  verify, a `skip_state` of `abha_create` alongside a non empty `abha_profiles`
  means an account already exists, and the correct next call is auto login
  rather than create.
- **The one time password fails at the counter.** Skip it. Flag ABHA pending
  and move the queue. Do not retry while twenty people wait.

### Observed responses

Recorded against `https://api.eka.care` on 2026-09-10. The address rules were
not in the documentation and were learned from the gateway.

```
POST /abdm/na/v1/registration/phr/check   {"abha_address": "..."}

"zzz-not-a-real-abha-97531"
  400 {"error":"Only alphabets, numbers and dot(.) are allowed in ABHA address"}
"ramesh"
  400 {"error":"ABHA address should have atleast 8 characters."}
"zznotarealabha97531"
  400 {"error":"ABHA address should not be more than 18 characters."}
"abhatest", "testuser99", "zznotareal1234"
  500 {"error":"couldn't connect with ABDM servers"}
```

So an ABHA address is 8 to 18 characters, letters, digits and dots only.

Every address that passed those rules returned the same 500, reproducibly, on
repeated attempts. Eka's own validation layer is reached and answers correctly;
the hop onward to NHA is what fails. Two causes fit and this side cannot
separate them: NHA's gateway being unreachable, or this client not being
onboarded to the ABDM bridge. A missing scope would more likely return 403 than
a 500 carrying Eka's own wrapper text, which points at the first.
