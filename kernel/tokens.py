"""The facility's day sequence: the number the waiting area calls out.

What a token is
---------------
A number. 1, 2, 3. One sequence per facility per day, issued at the moment a
person arrives, and shared by everybody who arrives however they got here: the
patient a clerk registered at the desk and the patient who registered
themselves at the printed poster by the door draw from the same sequence, in
the order they actually walked in.

Why one sequence and not two
----------------------------
Because a waiting room is one room. Two sequences put two people called
"seven" in it, and the second one is told to wait for a number that has
already been called. Where somebody came from is recorded beside the number
(`provenance` on the queue view) and never inside it: a label can be ignored
by a patient who does not care, a different numbering scheme cannot.

So the poster saves the clerk the typing. It never saves a place in the line.

Why the kernel issues it
------------------------
Because the number is a promise to a person standing in a room, and the only
thing that can keep it is whatever can see every arrival. A renderer sees one
screen; the poster's arrival never touches a renderer at all. Two callers each
numbering their own arrivals is how a queue ends up with two number ones.

It used to be invented in two places instead: the adapter fell back to the
tail of a generated row id when nobody passed a token, and the seed shipped
`A01`. Neither was on a sequence and neither was a number.

What it reads
-------------
`Store.threads`, which is on the protocol, and nothing else. There is
deliberately no new Store method here: issuing a number is a question about
the rows the store already serves, so it needs no eleventh method and the
kernel gains no second off-protocol call. One process serves one facility
(api/main.py), so "today's threads" is this facility's day.

Honest limit, and it is a real one
----------------------------------
Reading the day's numbers and then writing the next one is two steps, so two
arrivals racing inside the same instant can be handed the same number. There
is no lock here and there is no transaction, because the Store protocol has
neither and inventing one for this would put a transaction in the kernel and a
new method on every adapter.

At a primary health centre desk, where arrivals are a person walking up to a
counter, this is a narrow window. It is not zero, and a shared poster that
several patients scan at once is exactly where it would be reached. The fix is
a sequence the store itself issues atomically, which is a change to the
protocol and to every adapter behind it, and it is the owner's to schedule.
Written down rather than left to be discovered from two patients holding the
same slip.

Pure: takes a Store, touches no network and no file. Python 3.9.
"""
from __future__ import annotations

# The first number of a facility's day. Not zero: nobody calls out "zero".
FIRST = 1


def numbers(tokens):
    """The tokens that are on this sequence, as integers, in order.

    A token that is not a plain number is not on the sequence and is skipped
    rather than rejected. Two reasons, and neither is tidiness. A laboratory
    numbers its racks (`25-0414`) and that is its own business, not a gap in
    anybody's queue. And a facility whose file still holds a pre-numeric
    token must still be able to open tomorrow: skipping it means the next
    arrival gets 1 and the day is countable again, where refusing would mean
    the desk cannot register anybody until somebody edits a database.
    """
    out = []
    for token in tokens:
        text = str(token or "").strip()
        if text.isdigit():
            out.append(int(text))
    return sorted(out)


def after(tokens):
    """The next number, given the ones already issued.

    One past the HIGHEST issued, not one past the count. A visit that was
    opened and closed still spent its number: counting instead would hand the
    next arrival a number somebody in the room was already answering to.
    """
    issued = numbers(tokens)
    return max(issued) + 1 if issued else FIRST


def issue(store, *, workflow, scope="today"):
    """The next number for this facility's day, as the string a row stores.

    A string because that is what the token column holds and what a screen
    draws; the sequence is arithmetic, the token is a label.
    """
    seen = [ref.subject.get("token") for ref in store.threads(workflow=workflow, scope=scope)]
    return str(after(seen))


if __name__ == "__main__":
    # The sequence rule, exercised on its own, because the arithmetic is the
    # whole of what this module promises and it needs no store to check.
    assert numbers([]) == []
    assert after([]) == FIRST == 1, "an empty day starts at one"
    assert after(["1"]) == 2 and after(["1", "2", "3"]) == 4, "it increments"
    assert after([1, 2, 3]) == 4, "an integer token counts the same as its string"
    assert after(["3", "1", "2"]) == 4, "arrival order is not storage order"
    # The one that matters: a closed visit still spent its number.
    assert after(["1", "3"]) == 4, "a gap does not reissue a number"
    assert after(["2"]) == 3, "one past the highest, not one past the count"
    # Not on the sequence, and not fatal.
    assert after(["A01"]) == FIRST, "a pre-numeric token is not a number"
    assert after(["25-0414"]) == FIRST, "another facility's rack is not this queue"
    assert after([None, ""]) == FIRST, "a visit with no token spent no number"
    assert after(["A01", "7"]) == 8, "a numeric token still counts beside one that is not"
    assert numbers(["1", "A01", None, "2"]) == [1, 2], "exactly the numeric ones, in order"
    print("ok   the day sequence: numeric, one per facility, "
          "one past the highest issued, and nothing else is on it")
