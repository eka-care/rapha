"""Reading a photographed document, server side: a picture in, a draft out.

The browser photographs the paper and uploads it with the medical records
SDK -- the same @eka-care/medical-records-ts-sdk the claims portal uses --
pointed at this kernel, which attaches the credential and passes the call on.
So the picture never travels through this process and the credential never
reaches the browser. What arrives here is a document id.

What comes back is a Draft in the sense of kernel/contracts.py. Nothing in
this module writes, proposes or commits. It has no Store, and api/main.py's
route hands it nothing that could reach one. A person reads the draft in
editable fields and taps, which is the architecture's third rule and is not
weakened here.

THE PAPER IS KEPT, ON THE PATIENT'S OWN RECORD. The owner decided this on 4
November 2026, once the patient directory's Eka `oid` turned out to be the
identifier the medical records API scopes by: a document the patient brought
to this centre is filed against them and follows them to the next one, which
is the whole point of a health record that is theirs rather than ours.

It is filed under their oid and nothing else, so a patient this centre has
not published to the directory has nowhere for it to go. That case is not
fudged: the form says so and offers to publish them first.

What Eka actually answers, seen live against https://api.eka.care on
2026-11-04 with a synthetic one page report (not read from a document):

  upload   client.records.upload_document(file_path=..., document_type="lr",
             tags=[...], title=...) -> {"document_id": "<uuid>"}

  read     client.records.get_document(id) ->
             {"document_type": "lr",
              "source": "EC_1789058387727",      <- OUR client tag, not the lab
              "document_date_epoch": 1793644200,
              "tags": [...],
              "files": [{"asset_url": ..., "file_type": "PDF"}],
              "smart_report": {"verified": [...], "unverified": [...]}}
           `smart_report` is absent until the parse finishes, which took
           about thirty seconds for one page. No X-Pt-Id header was needed.

  each row {"name": "Haemoglobin", "value": "9.2", "unit": "g/dL",
             "range": "13.0 - 17.0 g/dL", "result": "LOW",
             "display_result": "Low", "page_num": 1, ...}

  delete   client.records.delete_document(id) -> {"status": "success",
                                                  "status_code": 204}

Run the check: python3 -m api.paper
"""
from __future__ import annotations

import datetime
import os
import uuid

from api.scribe import ScribeError, client, sdk
from care_phc.connectors.scribe.eka import _scrub

# WHAT MAY BE UPLOADED IS THE SDK'S RULE NOW, not this module's. It carries
# UPLOAD_CONSTRAINTS -- the accepted content types, 25 MB for a PDF and 10 MB
# for an image -- and it refuses in the browser, before anything is sent,
# which is the only place a person can do something about it. A second copy
# of those numbers here would be a second copy to keep in step with a
# library that owns them.

# Every value a read fills is unconfirmed, whatever the service thought. The
# same cap the scribe uses, and for a stronger reason: a recording is of
# words somebody in the room just said, and a scan is of a document nobody in
# the room wrote. A misread decimal point in somebody else's creatinine is
# harder to notice and easier to believe.
CAP = 0.0


class PaperError(ScribeError):
    """Anything the read could not do, in words that say what to do instead.

    It is a ScribeError because the two share one rule: every message ends by
    naming the way through that always works, which here is typing the three
    fields that were there before this instrument existed.
    """


# ------------------------------------------------------------------ connector
#
# THE PICTURE NO LONGER PASSES THROUGH HERE. The browser uploads it with
# @eka-care/medical-records-ts-sdk, which is the SDK the claims portal uses,
# straight to the presigned bucket the service hands back. What reaches this
# module is a document id, and what this module does is wait for the service
# to finish reading it and say what it read.
#
# Two things are better for that. A ten megabyte photograph no longer travels
# through this process at all, and the paper is filed against the patient's
# own Eka record instead of being thrown away, which is the owner's decision
# of 4 November 2026: a document the patient brought follows the patient.
#
# The credential still never reaches the browser. The SDK is pointed at this
# kernel, which proxies to the service and attaches the authorisation; see
# `/mr/api/v1/...` in api/main.py.


def describe(document_id, *, patient=None, sleep=None, now=None):
    """Wait for the service to finish reading one uploaded document.

    `patient` is the Eka oid the document was filed under, which the service
    wants as `X-Pt-Id`. The Python SDK's own `get_document` does not send it,
    so the header goes on by hand through the same client.
    """
    if not document_id:
        raise PaperError("No document to read. Photograph the paper again.")

    import time
    nap = sleep or time.sleep
    clock = now or time.monotonic

    started = clock()
    while True:
        try:
            body = sdk(lambda: client().request(
                method="GET", endpoint="/mr/api/v1/docs/%s" % document_id,
                headers={"X-Pt-Id": patient} if patient else None))
        except Exception as broke:
            raise PaperError(
                "Could not reach the reader to collect what it read (%s). "
                "Type what the paper says." % _scrub(str(broke))[:300]) from None
        if (body or {}).get("smart_report"):
            return body
        if clock() - started > PATIENCE_SECONDS:
            raise PaperError(
                "The reader is still working after %d seconds, so it has been "
                "given up on. The paper is saved on the patient's record; type "
                "what it says for this visit." % PATIENCE_SECONDS)
        nap(EVERY)


# ------------------------------------------------- reading the response
# Pure from here down: no network, no store, no clock passed in. Checked by
# demo() at the foot of this file.

def _day(epoch):
    """The date the paper carries, as the one unambiguous written form.

    `<input type="date">` in the renderer reads and writes exactly this, and
    03/04 is two different days in two countries.
    """
    if not epoch:
        return None
    try:
        return datetime.datetime.utcfromtimestamp(int(epoch)).date().isoformat()
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def _line(row):
    """One reading, as a line somebody can read against the paper in hand.

    Name, value, unit, the laboratory's own reference range, and the
    laboratory's own verdict. Every part of it is the document's; nothing
    here decides whether a number is high, which is the laboratory's call and
    is already in the response.
    """
    name = str(row.get("name") or "").strip()
    if not name:
        return None
    value = str(row.get("value") or "").strip()
    unit = str(row.get("unit") or "").strip()
    said = " ".join(p for p in (name, value, unit) if p)
    rng = str(row.get("range") or "").strip()
    if rng:
        said += " (reference %s)" % rng
    # `display_result` is the service's own wording -- "High", "Low" -- and
    # is preferred over the shouting enum beside it.
    verdict = str(row.get("display_result") or row.get("result") or "").strip()
    if verdict and verdict.lower() not in ("normal", "n"):
        said += " — %s" % verdict
    return said


def findings(body):
    """Every reading the service was sure of, then every one it was not.

    Both are shown. An unverified row is a row the service read and could not
    match to a known analyte, and dropping it would be dropping something
    printed on the paper in front of the person. They land in the same box,
    in the same unconfirmed state, to be checked against the paper.
    """
    report = (body or {}).get("smart_report") or {}
    out = []
    for key in ("verified", "unverified"):
        for row in report.get(key) or []:
            said = _line(row)
            if said:
                out.append(said)
    return out


def parse(body, *, operation, instrument, fills):
    """A draft, from what the service read and the instrument's own map.

    `fills` is the declaration's: which question takes which part. A part the
    bundle did not map is not filled, and a part the service did not answer
    is not invented. Returns None when nothing could be filled at all, which
    is the honest answer for a handwritten note the parser made nothing of.
    """
    parts = {"date": _day((body or {}).get("document_date_epoch")),
             "findings": "\n".join(findings(body)) or None}

    values, evidence = {}, {}
    for part, link_id in (fills or {}).items():
        said = parts.get(part)
        if not said:
            continue
        values[link_id] = said
        evidence[link_id] = _evidence(part, body)
    if not values:
        return None

    return {
        "instrument": instrument,
        "operation": operation,
        "values": values,
        # Nothing the service returns is a per field recognition score, so
        # every value is capped at unconfirmed. See CAP.
        "confidence": {k: CAP for k in values},
        "evidence": evidence,
        # Every filled value is owed a tick. Both parts are prose, which
        # api/fill.py's TICK_TYPES would not ask a tick for, and that rule is
        # right for a recording of a sentence somebody just said. It is wrong
        # here: this is a reading of somebody else's document and the whole
        # of the readback is a person holding the paper beside the screen.
        "tick": sorted(values),
        "unfilled": sorted(
            link_id for part, link_id in (fills or {}).items()
            if link_id not in values),
        "transcript": "",
    }


def _evidence(part, body):
    """Where the value came from, in words, beside the field.

    Not the value again. For the date it is the fact that the paper carried
    one; for the findings it is how many rows were read and off how many
    pages, which is the thing a person checks first against the paper.
    """
    if part == "date":
        return "the date printed on the document"
    rows = findings(body)
    pages = {r.get("page_num") for key in ("verified", "unverified")
             for r in ((body or {}).get("smart_report") or {}).get(key) or []}
    pages.discard(None)
    said = "%d reading%s read off the document" % (len(rows), "" if len(rows) == 1 else "s")
    if len(pages) > 1:
        said += ", over %d pages" % len(pages)
    return said


# ------------------------------------------------------------------- the check

def demo():
    """python3 -m api.paper -- the pure half, against the live response shape."""
    checks = 0

    def ok(what):
        nonlocal checks
        checks += 1
        print("ok   %s" % what)

    # The shape below is the body this kernel actually received on
    # 2026-11-04, trimmed to the keys that are read.
    body = {
        "document_type": "lr",
        "source": "EC_1789058387727",
        "document_date_epoch": 1793644200,
        "smart_report": {
            "verified": [
                {"name": "Haemoglobin", "value": "9.2", "unit": "g/dL",
                 "range": "13.0 - 17.0 g/dL", "result": "LOW",
                 "display_result": "Low", "page_num": 1},
                {"name": "Platelet Count", "value": "1.9", "unit": "lakh/cumm",
                 "range": "1.5 - 4.1 lakh/cumm", "result": "NORMAL",
                 "display_result": "Normal", "page_num": 1},
            ],
            "unverified": [
                {"name": "Impression", "value": "Anaemia", "unit": "",
                 "range": "", "result": "", "page_num": 2},
            ],
        },
    }
    FILLS = {"date": "dated", "findings": "body"}

    said = findings(body)
    assert len(said) == 3, said
    assert said[0] == "Haemoglobin 9.2 g/dL (reference 13.0 - 17.0 g/dL) — Low", said[0]
    ok("a reading keeps its unit, the laboratory's range and the laboratory's verdict")

    assert "—" not in said[1], said[1]
    ok("a normal result is not decorated with the word normal")

    assert said[2] == "Impression Anaemia", said[2]
    ok("a row the service could not match is still shown, not dropped")

    draft = parse(body, operation="phc.op.context-add",
                  instrument="phc.inst.context-scan", fills=FILLS)
    assert draft["values"]["dated"] == "2026-11-02", draft["values"]["dated"]
    ok("the date the paper carries is written the one unambiguous way")

    assert draft["values"]["body"].count("\n") == 2
    ok("every reading lands in the one box the declaration named")

    assert set(draft["confidence"].values()) == {0.0}
    assert sorted(draft["tick"]) == ["body", "dated"]
    ok("nothing is confident and everything is owed a tick")

    assert "the date printed" in draft["evidence"]["dated"]
    assert "3 readings" in draft["evidence"]["body"], draft["evidence"]["body"]
    assert "2 pages" in draft["evidence"]["body"], draft["evidence"]["body"]
    ok("the evidence says where it came from and over how many pages")

    # WHO WROTE IT IS NEVER FILLED. The service answers `source` and it holds
    # our own client tag; a form that put that in "who wrote it" would be
    # claiming a laboratory's paper came from us.
    assert "EC_1789058387727" not in str(draft)
    assert "source" not in draft["values"]
    ok("the service's own client tag never reaches a field meaning who wrote it")

    # A PART THE BUNDLE DID NOT MAP IS NOT FILLED, whatever the paper held.
    only_date = parse(body, operation="o", instrument="i", fills={"date": "dated"})
    assert list(only_date["values"]) == ["dated"], only_date["values"]
    ok("a part the declaration does not map is left alone")

    # NOTHING READ MEANS NOTHING FILLED. A handwritten note the parser made
    # nothing of must not arrive as an empty draft that looks like an answer.
    assert parse({"smart_report": {"verified": [], "unverified": []}},
                 operation="o", instrument="i", fills=FILLS) is None
    assert parse({}, operation="o", instrument="i", fills=FILLS) is None
    ok("a document nothing was read from produces no draft at all")

    # A date the service did not answer leaves that field empty and names it.
    no_date = parse({"smart_report": body["smart_report"]},
                    operation="o", instrument="i", fills=FILLS)
    assert "dated" not in no_date["values"]
    assert no_date["unfilled"] == ["dated"]
    ok("a part the paper did not carry is named as unfilled, never guessed")

    for bad, what in ((0, "no epoch"), ("nonsense", "a word"), (10 ** 20, "the far future")):
        assert _day(bad) is None, what
    ok("an unreadable date is no date, rather than a wrong one")

    print("\n%d paper checks passed" % checks)


if __name__ == "__main__":
    demo()
