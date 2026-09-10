"""Eka ABDM Connect implementation of the connector boundary.

Schemas here were taken from developer.eka.care doc pages, not from memory:
  POST /abdm/na/v1/registration/phr/check      {abha_address} -> {exists}
  POST /abdm/na/v1/registration/aadhaar/init   {aadhaar_number} -> {txn_id, hint}

Auth is `Authorization: Bearer <token>` for these endpoints. Other ABDM
endpoints use an `auth` header instead, so each one's doc page decides; do not
assume this header everywhere.

Compliance guards from the M1 skill are enforced here rather than documented:
an Aadhaar number is never logged, never stored, and never placed in an
exception message; a mobile number is carried as last four digits only; an OTP
is never persisted. `_scrub` is applied to everything that could reach a log.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from care_phc.connectors.abdm.base import AbdmError, AbhaResult
from care_phc.connectors.abdm.token import TokenManager

CHECK_PHR = "/abdm/na/v1/registration/phr/check"
AADHAAR_INIT = "/abdm/na/v1/registration/aadhaar/init"

# 12 digits, optionally spaced. Matched so it can be removed, never stored.
_AADHAAR = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")


def _scrub(text):
    """Remove anything Aadhaar-shaped before it can reach a log or a traceback."""
    return _AADHAAR.sub("<aadhaar-redacted>", str(text))


def last4(mobile):
    """Mobile numbers are stored as last four digits only."""
    digits = re.sub(r"\D", "", str(mobile or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def _post(url, body, headers=None, timeout=30):
    """Plain POST returning parsed JSON. Raises AbdmError with the gateway's code."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        code = None
        try:
            parsed = json.loads(raw)
            err = parsed.get("error")
            code = (err or {}).get("code") if isinstance(err, dict) else parsed.get("code")
        except json.JSONDecodeError:
            pass
        raise AbdmError(_scrub(raw)[:400], code=code, status=e.code) from None


class EkaAbdm:
    """Implements AbdmConnector against Eka ABDM Connect."""

    def __init__(self, base_url, client_id, client_secret, *, hip_id=None,
                 transport=_post):
        self._base = base_url.rstrip("/")
        self._hip_id = hip_id
        self._post = transport
        self._tokens = TokenManager(
            base_url, client_id, client_secret,
            transport=lambda url, body: transport(url, body),
        )

    def _call(self, path, body, *, extra_headers=None):
        """Authenticated POST. One retry after re-auth, because a token can
        expire between the check and the call."""
        for attempt in (1, 2):
            headers = {"Authorization": f"Bearer {self._tokens.token()}"}
            if self._hip_id:
                headers["X-Hip-Id"] = self._hip_id
            headers.update(extra_headers or {})
            try:
                return self._post(self._base + path, body, headers)
            except AbdmError as e:
                if e.status == 401 and attempt == 1:
                    self._tokens.invalidate()
                    continue
                raise

    # ---- reads -------------------------------------------------------------

    def abha_address_exists(self, abha_address) -> bool:
        """Whether this ABHA address is already taken.

        Search before create. Addendum §B: most outpatient footfall is repeat
        patients, so defaulting to create is how duplicates get manufactured,
        and a duplicate ABHA can only be deprecated, never undone.
        """
        return bool(self._call(CHECK_PHR, {"abha_address": abha_address}).get("exists"))

    # ---- the enrolment journey ---------------------------------------------

    def start_aadhaar_enrolment(self, aadhaar_number) -> dict:
        """Send an OTP to the Aadhaar-linked mobile. Returns {txn_id, hint}.

        The Aadhaar number is passed straight through and never retained: not
        on self, not in the returned dict, and scrubbed out of any error.
        """
        out = self._call(AADHAAR_INIT, {"aadhaar_number": str(aadhaar_number).strip()})
        return {"txn_id": out.get("txn_id"), "hint": out.get("hint")}

    def create_or_link_abha(self, *, method, patient, abha_number=None) -> AbhaResult:
        raise NotImplementedError(
            "The enrolment journey past OTP init is not written yet. It needs the "
            "verify-otp and create-abha schemas, and it cannot be exercised "
            "without a live OTP, so it is human-driven by construction."
        )

    def link_care_context(self, *, abha_number, encounter_ref, display) -> None:
        raise NotImplementedError("M2 care context linking is a later phase.")

    def __repr__(self):
        return f"<EkaAbdm {self._base}>"
