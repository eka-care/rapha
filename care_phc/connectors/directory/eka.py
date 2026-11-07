"""Eka's patient directory, behind kernel.contracts.PatientDirectory.

Why the interface is in the kernel's contracts and not in a base.py here, the
way the ABDM and scribe connectors keep theirs: the kernel needs this one.
Resolving who is standing at the desk is kernel logic (kernel/directory.py),
so a protocol kept in this directory would make the kernel import a
connector, which the layer table forbids. This is the Store pattern instead:
the protocol beside Store, the implementation out here. An unexplained
asymmetry between connectors is worse than either choice, so it is explained.

The surface, established from the docs rather than guessed
---------------------------------------------------------
`https://api.eka.care/profiles/v1/patient/...`, bearer token plus a
`client-id` header. Read from the Patient Directory OpenAPI specification on
developer.eka.care on 2026-10-31:

    POST /profiles/v1/patient/            create, 201 -> {"oid": "..."}
    GET  /profiles/v1/patient/search      ?prefix= &limit= &select=
    GET  /profiles/v1/patient/by-mobile/  ?mob= &full_profile=
    GET  /profiles/v1/patient/{oid}       retrieve
    PATCH/DELETE /profiles/v1/patient/{oid}    not called, see base.py

**A package the brief named does not exist.** The work was requested against
`@eka-care/patient-ts-sdk`. No package of that name appears anywhere in Eka's
developer documentation. What does exist is `@eka-care/eka-care-core`, a
BROWSER SDK whose `patients` module has `addPatientToDirectory`,
`searchPatientByMobile`, `getPatientDetailsById` and `updatePatientDetails`,
and the REST API above. This connector is built on the REST API, server side,
for three reasons:

- a browser SDK puts the credential in the browser, and this product's trust
  boundary is the API. api/scribe.py already says the Eka credentials never
  leave this process.
- the SDK's cache is per browser. Identity has to be readable by the server,
  because the write path resolves a subject and the queue draws names.
- Eka's changelog records a `forceApiSearch` flag added to bypass that cache
  and a fix for "stale or partial cached state" surfacing incorrect patient
  search results. A cache whose staleness has already caused wrong matches is
  not the cache to put patient identity behind. Ours is in the store, it is
  the row the queue already needed, and it says when it was last agreed.

**One documented limit that is a product blocker, not an engineering one.**
The specification's own description of the search endpoint reads: "Global
Search is exclusive to specific workspaces only. Please reach out to support."
So prefix search across the directory may not be enabled for our workspace,
while `by-mobile` carries no such note. `kernel/directory.py` therefore treats
a numeric query as a mobile lookup, which is also what a PHC clerk has: in
practice they have the phone number. Raised in the architecture
document as an item for the owner, because enabling it is a conversation with
Eka and not a code change.

What is checked here and what is not
------------------------------------
Honest, because the difference matters. Checked, by `python3 -m
care_phc.connectors.directory.eka`: every field translation in both
directions, over the exact shapes the specification gives. That is where the
decisions are, and the decisions are listed at `_OUR_SEX` and in `to_wire`
below. NOT checked, and marked `unverified` wherever it appears: the HTTP
calls. They are four lines each, they need a credential and a socket, and no
request has been made against api.eka.care from this branch. Nothing in
`scripts/check.sh` exercises them.

Run: python3 -m care_phc.connectors.directory.eka
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from care_phc.connectors import redact
from kernel.contracts import DirectoryError, DirectoryPatient

BASE = os.environ.get("EKA_DIRECTORY_BASE", "https://api.eka.care")
TIMEOUT = 10

# Our word for a sex, and the directory's. The directory has three values and
# so do we, so this is total in both directions and there is nothing to drop.
# `gen` is the wire's name for it.
_OUR_SEX = {"female": "F", "male": "M", "other": "O"}
_THEIR_SEX = {v: k for k, v in _OUR_SEX.items()}

# Our questionnaire asks for an age; the directory holds a date of birth.
# Neither is derivable from the other without losing something, so the rule is
# written down once, here, and it is deliberately lossy in the safe direction:
#
#   their dob -> our age     exact, computed against a date the caller passes
#   our age   -> their dob   an approximation, and marked as one
#
# A PHC register has an age in it because that is what a patient knows. Sending
# a made up birthday as though it were a fact would put a false precision in a
# national directory, so the approximation carries `_approx_dob` in `extras`
# and the day is the first of January. The underscore matters: the
# specification says keys starting with `_` are ignored, so this is a note to
# ourselves that the directory will drop, which is the right fate for it.
APPROX_DAY = "01-01"

# Two of our register's answers have no field in the directory. They are a
# facility's own words, not a person's identity, so they go in `extras` with
# their own short keys. The specification limits a key to 16 characters, forbids
# nested lists and dictionaries inside lists, and allows one level of nesting.
EXTRA_KEYS = {"village": "phc_village", "category": "phc_category"}
assert all(len(k) <= 16 for k in EXTRA_KEYS.values()), EXTRA_KEYS


def age_from_dob(dob, *, today):
    """Whole years between an ISO date and `today`, or None.

    `today` is passed and never read from the clock, so this is pure and a
    check can pin it. A dob in the future, which a directory can hold because
    somebody typed it, gives None rather than a negative age.
    """
    try:
        born = datetime.date.fromisoformat(str(dob)[:10])
    except (TypeError, ValueError):
        return None
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return years if years >= 0 else None


def dob_from_age(age, *, today):
    """An approximate ISO date of birth for a whole age, or "".

    Approximate on purpose, and the only place that approximation is made.
    """
    try:
        years = int(age)
    except (TypeError, ValueError):
        return ""
    if years < 0 or years > 150:
        return ""
    return "%d-%s" % (today.year - years, APPROX_DAY)


def from_wire(profile, *, today, matched_on=""):
    """One directory profile as a DirectoryPatient.

    The wire's abbreviations stop here. `fln` is the full name, and a profile
    that carries only parts gets them joined, because the specification says a
    create may send either and so a read may return either.
    """
    profile = dict(profile or {})
    oid = str(profile.get("oid") or "").strip()
    if not oid:
        # A profile with no id is not a person we could ever point an
        # encounter at. Refused here rather than cached and discovered later.
        raise DirectoryError("a directory profile arrived with no oid")
    name = str(profile.get("fln") or "").strip()
    if not name:
        name = " ".join(str(profile.get(k) or "").strip()
                        for k in ("fn", "mn", "ln")).strip()
        name = " ".join(name.split())
    dob = str(profile.get("dob") or "").strip()
    abha = profile.get("abha") or ""
    return DirectoryPatient(
        directory_id=oid,
        name=name,
        sex=_THEIR_SEX.get(str(profile.get("gen") or "").upper(), ""),
        dob=dob,
        age=age_from_dob(dob, today=today),
        phone=str(profile.get("mobile") or "").strip(),
        # The wire has one `abha` field and the specification's example is an
        # ABHA ADDRESS ("xyz@abdm"), not a 14 digit number. Read as an address,
        # and the number is left empty rather than guessed from it, because
        # phc.op.abha-link is the operation that establishes a number and it is
        # declared irreversible.
        abha_address=str(abha).strip(),
        matched_on=matched_on,
        extras=dict(profile.get("extras") or {}),
    )


def to_wire(row, *, today):
    """A local patient row as a create body.

    Every answer our register asks for has somewhere to go, and the two that
    have no directory field are named in EXTRA_KEYS rather than dropped. That
    is the same rule the mapping lint enforces on the way in: an answer with
    nowhere to go is a clinical value dropped in silence, so dropping one has
    to be written down.
    """
    row = dict(row or {})
    name = str(row.get("name") or "").strip()
    if not name:
        # The specification requires `fln`, or at least `fn`. A publish with
        # neither is a 400 we can see coming, so it is refused here where the
        # message can say which field.
        raise DirectoryError("a patient with no name cannot be published")
    body = {"fln": name}
    sex = _OUR_SEX.get(str(row.get("sex") or "").lower())
    if sex:
        body["gen"] = sex
    phone = str(row.get("phone") or "").strip()
    if phone:
        body["mobile"] = phone
    dob = dob_from_age(row.get("age"), today=today)
    extras = {}
    if dob:
        body["dob"] = dob
        extras["_approx_dob"] = "from age %s at registration" % row.get("age")
    for ours, theirs in sorted(EXTRA_KEYS.items()):
        value = str(row.get(ours) or "").strip()
        if value:
            extras[theirs] = value
    if extras:
        body["extras"] = extras
    return body


class EkaDirectory:
    """kernel.contracts.PatientDirectory over Eka's REST API.

    UNVERIFIED. The four HTTP calls below have never been made against
    api.eka.care from this branch: they need a credential and a socket, and
    nothing in scripts/check.sh exercises them. The translations they wrap are
    checked exhaustively. Treat a first live run as the verification step and
    record what came back here, the way api/scribe.py records it.
    """

    def __init__(self, *, token=None, client_id=None, base=BASE, today=None):
        # A STRING OR A WAY TO GET ONE. `EKA_ACCESS_TOKEN` is a signed-in
        # person's token and a developer rarely has one to hand, so the
        # facility's own token is passed as a callable instead: this process
        # can mint one from the client id and secret it already holds. It is
        # fetched when a call is made rather than here, so a kernel with no
        # network still starts and simply degrades to its own register.
        self._mint = token if callable(token) else None
        self.token = "" if self._mint else (token or os.environ.get("EKA_ACCESS_TOKEN") or "")
        self.client_id = client_id or os.environ.get("EKA_CLIENT_ID") or ""
        self.base = base.rstrip("/")
        self._today = today
        if not (self.token or self._mint) or not self.client_id:
            # Not a crash. api/main.py reads this and falls back to
            # AbsentDirectory, which is the designed degraded path, so a
            # developer with no Eka account gets a working clinic.
            raise DirectoryError(
                "EKA_ACCESS_TOKEN and EKA_CLIENT_ID are needed to reach the "
                "patient directory. Without them the facility runs on its own "
                "cache and publishes nothing.", reachable=False)

    def _bearer(self):
        """The token for this call. Minted once and held by whoever minted
        it; a failure to mint is a directory that cannot be reached, which is
        the degraded path this connector already has a name for."""
        if not self._mint:
            return self.token
        try:
            return self._mint()
        except Exception as broke:
            raise DirectoryError(
                "Could not sign in to the patient directory (%s). The centre "
                "runs on its own register until it can."
                % str(broke)[:200], reachable=False) from None

    @property
    def today(self):
        return self._today or datetime.date.today()

    # ------------------------------------------------------------ unverified
    def _call(self, method, path, *, query=None, body=None):
        """One request. UNVERIFIED: see the class docstring.

        Every failure becomes a DirectoryError, and `reachable` separates "the
        directory answered and said no" from "there was no directory to ask",
        because kernel/directory.py treats those differently and a clinic
        depends on the difference.
        """
        url = "%s%s" % (self.base, path)
        if query:
            url = "%s?%s" % (url, urllib.parse.urlencode(query))
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": "Bearer %s" % self._bearer(),
            "client-id": self.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
                raw = answer.read().decode() or "{}"
                return json.loads(raw), answer.status
        except urllib.error.HTTPError as broke:
            # Reachable and refusing. The body is scrubbed because it carries
            # a profile and may carry an Aadhaar shaped number.
            detail = ""
            try:
                detail = broke.read().decode()[:300]
            except Exception:
                pass
            raise DirectoryError(redact.aadhaar("the directory refused: %s" % detail),
                                 status=broke.code, reachable=True)
        except Exception as broke:
            # No line, DNS, timeout, a TLS failure. The clinic keeps going.
            raise DirectoryError(redact.aadhaar("the directory could not be reached: %s"
                                                % broke), reachable=False)

    def search(self, prefix, *, limit=10):
        found, _ = self._call("GET", "/profiles/v1/patient/search",
                              query={"prefix": prefix, "limit": min(int(limit), 50),
                                     "select": "abha,dob,gen"})
        return [from_wire(p, today=self.today, matched_on="search")
                for p in (found if isinstance(found, list) else [])]

    def by_mobile(self, mobile):
        found, _ = self._call("GET", "/profiles/v1/patient/by-mobile/",
                              query={"mob": mobile, "full_profile": "true"})
        listed = found if isinstance(found, list) else [found] if found else []
        return [from_wire(p, today=self.today, matched_on="mobile") for p in listed]

    def fetch(self, directory_id):
        try:
            found, _ = self._call(
                "GET", "/profiles/v1/patient/%s" % urllib.parse.quote(str(directory_id)))
        except DirectoryError as broke:
            if broke.status == 404:
                return None
            raise
        return from_wire(found, today=self.today, matched_on="id") if found else None

    def publish(self, patient):
        answer, _ = self._call("POST", "/profiles/v1/patient/",
                               body=to_wire(patient, today=self.today))
        oid = str((answer or {}).get("oid") or "").strip()
        if not oid:
            raise DirectoryError("the directory accepted the patient and returned "
                                 "no oid, so nothing can point at them")
        return oid


def demo():
    today = datetime.date(2026, 10, 31)

    # ---- their profile becomes ours
    p = from_wire({"oid": "17552615662165", "fln": "Sunita Devi", "gen": "F",
                   "dob": "1992-03-14", "mobile": "+919876500000",
                   "abha": "sunita@abdm", "extras": {"phc_village": "Yadiki"}},
                  today=today, matched_on="mobile")
    assert p.directory_id == "17552615662165" and p.name == "Sunita Devi", p
    assert p.sex == "female", p
    assert p.age == 34 and p.dob == "1992-03-14", p
    assert p.abha_address == "sunita@abdm" and p.abha_number == "", \
        "the wire's abha field is an address; a number is phc.op.abha-link's"
    assert p.extras == {"phc_village": "Yadiki"}, p
    assert p.matched_on == "mobile"

    # name parts, because a create may send either and so a read may return either
    joined = from_wire({"oid": "1", "fn": "sunita", "ln": "devi"}, today=today)
    assert joined.name == "sunita devi", joined
    assert from_wire({"oid": "1", "fn": "sunita", "mn": "", "ln": "devi"},
                     today=today).name == "sunita devi", "an empty middle name"

    for gen, ours in (("F", "female"), ("M", "male"), ("O", "other"),
                      ("f", "female"), ("", ""), ("X", "")):
        got = from_wire({"oid": "1", "gen": gen}, today=today).sex
        assert got == ours, (gen, got)

    try:
        from_wire({"fln": "No Id"}, today=today)
    except DirectoryError:
        pass
    else:
        raise AssertionError("a profile with no oid was accepted")

    # ---- ours becomes theirs
    body = to_wire({"name": "Sunita Devi", "age": 34, "sex": "female",
                    "phone": "9876500000", "village": "Yadiki",
                    "category": "anc"}, today=today)
    assert body["fln"] == "Sunita Devi" and body["gen"] == "F", body
    assert body["mobile"] == "9876500000", body
    assert body["dob"] == "1992-01-01", body
    assert body["extras"]["phc_village"] == "Yadiki", body
    assert body["extras"]["phc_category"] == "anc", body
    assert body["extras"]["_approx_dob"].startswith("from age 34"), body
    assert set(body) <= {"fln", "fn", "mn", "ln", "s", "dob", "gen", "bloodgroup",
                         "mobile", "email", "abha", "username", "extras"}, body
    assert all(len(k) <= 16 for k in body["extras"]), body["extras"]
    assert all(not isinstance(v, (list, dict)) for v in body["extras"].values()), \
        "the specification forbids nested lists and dictionaries inside lists"

    bare = to_wire({"name": "No Phone"}, today=today)
    assert bare == {"fln": "No Phone"}, bare
    try:
        to_wire({"age": 30}, today=today)
    except DirectoryError:
        pass
    else:
        raise AssertionError("a nameless patient was publishable")

    # ---- the age and birthday rule, in both directions
    assert age_from_dob("1992-03-14", today=today) == 34
    assert age_from_dob("1992-11-14", today=today) == 33, "not had the birthday yet"
    assert age_from_dob("", today=today) is None
    assert age_from_dob("not a date", today=today) is None
    assert age_from_dob("2030-01-01", today=today) is None, "a future dob is not an age"
    assert dob_from_age(0, today=today) == "2026-01-01"
    assert dob_from_age("34", today=today) == "1992-01-01"
    assert dob_from_age(-1, today=today) == ""
    assert dob_from_age(None, today=today) == ""
    assert dob_from_age(200, today=today) == ""
    # The round trip is lossy and the loss is in the safe direction: an age
    # survives, a birthday was never claimed.
    assert age_from_dob(dob_from_age(34, today=today), today=today) == 34

    # ---- no credential is a degradation, not a crash
    try:
        EkaDirectory(token="", client_id="", today=today)
    except DirectoryError as broke:
        assert broke.reachable is False, "a missing credential is an unreachable directory"
    else:
        raise AssertionError("a directory with no credential was built")

    print("ok   care_phc.connectors.directory.eka (translations only; the HTTP "
          "calls are unverified)")


if __name__ == "__main__":
    demo()
