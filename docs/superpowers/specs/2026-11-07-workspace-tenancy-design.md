# One workspace, many stores: what the kernel has to own

**Date** 2026-11-07
**Status** design, not built
**Decided by the owner on 7 November 2026:** medical records, patients and the
scribe already belong to workspaces. This note works out what that leaves.

## The question this answers

The kernel is not multi-tenant. Not one of its nineteen tables carries a
column saying which facility a row belongs to; `PHC_DB` names one SQLite file
and `PHC_FACILITY` picks which *shape* of the bundle runs — which plugins are
withheld — not whose data is served. Two centres means two processes.

The obvious response is to put a tenant key on every table. That is the wrong
shape, and the repository's own README has said so since the beginning:

> CARE already provides the renderer (questionnaires), the permission
> primitive, the audit log and the clinical resources. Eka Scribe already has
> an official care_fe plugin. What is genuinely missing, and therefore all
> this repo contains, is the patient thread that carries state between
> stations, the operations that read it, and the community layer.

Most of what is in the local store is standing in for a system that is
already multi-tenant. Making the stand-in multi-tenant would be building the
wrong thing twice.

## What already belongs to a workspace

Three of these are wired and working today, against production.

| What | Whose | How Rapha reaches it | State |
| --- | --- | --- | --- |
| People | Eka patient directory | `care_phc/connectors/directory/eka.py`, the facility's own token | **live** |
| Documents | Eka medical records | `api/vault.py` proxy, `@eka-care/medical-records-ts-sdk` in the browser | **live** |
| Recordings and notes | Eka Scribe | `api/scribe.py`, `api/notes.py` | **live** |
| Clinical resources | CARE | nothing yet; `adapters/` holds only `local/` | **intended** |

Eka Scribe's backend is worth naming precisely, because "reuse it" is a
reasonable thing to ask and the answer is a qualified no. It is properly
multi-tenant — every row is keyed `{b_id}#{txn_id}` — but its five tables are
transactions, audio details, documents, templates and template results. There
is no patient, no encounter, no prescription, no queue. It is a scribe. It
cannot hold a clinic because it was never asked to.

## What is left, and it is small

Split the nineteen tables by who should own them.

**Eka's, once the local copy goes:** `patient` (the directory is already the
source of truth; `directory_id` is the join), `scribe_note`, `notes`.

**CARE's, when an adapter exists:** `condition`, `observation`,
`medication_request`, `medication_dispense`, `service_request`,
`diagnostic_report`, `specimen`, `episode_of_care`,
`questionnaire_response`.

**Genuinely the kernel's, and nobody else's:** `encounter`, `thread_flag`,
`proposal`, `audit`, `day_sequence`, `token_booking`, `inventory_item`.

That last row is the whole of what needs a tenant key. It is the day: who is
here, where they have got to, what a machine proposed, who did what, and the
token counter. It is small, it is short-lived, and it is the one thing no
other system has because no other system runs a health centre's morning.

## The shape of the work

1. **A workspace id reaches the kernel.** The browser has it now — the hub's
   configuration read carries the clinic, and `web/src/auth/session.ts` keeps
   it. It travels as a header beside `X-PHC-Role`, and the kernel refuses a
   request that carries none once the gate applies.
2. **A `workspace` column on the seven tables above**, set on write from that
   header and never from a payload, with a migration that stamps every
   existing row with the one workspace this database has always held.
3. **The filter is in the Store, not in callers.** `adapters/local/store.py`
   is the only place that builds a query; a caller that could forget the
   filter is the whole risk, so it must not be able to. The Store takes the
   workspace at construction and every `select` narrows by it.
4. **The guard checks it.** A thread belongs to a workspace; an operation on
   a thread from another one is refused at the guard like any other denial,
   and the refusal is audited.
5. **Both engines agree.** `scripts/check_go_parity.py` already asks the two
   engines the same questions; it asks them per workspace after this.

## The check that matters more than the feature

One centre reading another's row is not a bug, it is a disclosure. So the
test is not "does scoping work" but "can it be made to fail": two workspaces
seeded in one database, then every read route called as workspace A with
workspace B's ids, asserting each one answers nothing. It belongs in
`scripts/` beside the other engine checks, and it should be written before
the column, so it fails first.

## What this is not

It is not an argument for doing it now. Nothing in the demo needs it: the
patients already cross devices because the directory is shared, and the
visits around them are one centre's, which is true and shows well.

It is also not a reason to wait for CARE. The seven tables above need the
tenant key whether the clinical resources live locally or in CARE, because
they are the kernel's own either way. The adapter and the tenancy are
separate pieces of work and neither blocks the other.

## Open, and the owner's

- **Is a workspace a facility?** Today they are the same thing by accident:
  one process, one centre. A workspace with two centres in it is a real case
  (a trust, a block) and decides whether the key is the workspace, the
  facility, or both.
- **Does a clinician move between workspaces mid-shift?** If yes, the id
  cannot be read once at sign-in and held; it has to come with the request.
- **What happens to the day when the line is down?** The outbox already holds
  writes; a workspace id that arrived from a session that has since expired
  still has to be the right one when the write finally lands.
