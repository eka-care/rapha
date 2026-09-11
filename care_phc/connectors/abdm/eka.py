"""Eka ABDM Connect implementation of the connector boundary.

Two halves behind one interface, and a caller cannot tell them apart:

  SDK backed, via the official `ekacare` package on PyPI
      auth and token handling   EkaCareClient
      profile, card, QR         client.abdm_profile.get_profile / get_abha_card
                                / get_abha_qr_code
      KYC                       initiate_kyc / verify_kyc_otp / resend_kyc_otp

  Raw REST, on that same authenticated client
      POST /abdm/na/v1/registration/phr/check     {abha_address} -> {exists}
      POST /abdm/na/v1/registration/aadhaar/init  {aadhaar_number} -> {txn_id, hint}
      POST /abdm/v1/care-contexts/link            202, the outcome arrives by webhook

The raw half exists because `ekacare.abdm` exposes exactly one class, Profile.
There is no enrolment, no care context and no consent in the SDK, so those stay
hand written. They ride on the SDK's client rather than a socket of our own, so
there is one token, one base URL and one place auth happens.

Every call returns a plain dict or raises AbdmError. That is the whole contract.

The base URL defaults to https://api.eka.care, which is where the credentials
in .env authenticate: login there returns a token with expires_in 1800, and the
same credentials are refused at https://api.dev.eka.care with "pwd mismatch",
checked on 2026-09-11. .env's own EKA_BASE_URL still names the dev host, so a
caller that passes it will fail to log in.

Compliance guards, enforced here rather than documented:
  - An Aadhaar number is scrubbed out of every error before it becomes an
    exception, a traceback or a log line. The SDK's own errors carry the
    gateway's response body verbatim (`f"API error {code}: {response.text}"`),
    so every SDK error is caught and re-raised as ours, scrubbed, with
    `from None` so the unscrubbed original cannot ride along in a traceback.
  - A mobile number is carried as last four digits only.
  - An OTP is passed straight through to the gateway and stored nowhere.
"""
from __future__ import annotations

import json
import re

from ekacare import EkaCareClient
from ekacare.utils.exceptions import EkaCareError

from care_phc.connectors.abdm.base import AbdmError, AbhaResult

CHECK_PHR = "/abdm/na/v1/registration/phr/check"
AADHAAR_INIT = "/abdm/na/v1/registration/aadhaar/init"
CARE_CONTEXT_LINK = "/abdm/v1/care-contexts/link"

# 12 digits, optionally spaced. Matched so it can be removed, never stored.
_AADHAAR = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b")

# The SDK carries the HTTP status in its message text and nowhere else, so a
# status we need for the 401 retry has to be read back out of the string.
_STATUS = re.compile(r"\b([1-5]\d\d)\b")


def _scrub(text):
    """Remove anything Aadhaar-shaped before it can reach a log or a traceback."""
    return _AADHAAR.sub("<aadhaar-redacted>", str(text))


def last4(mobile):
    """Mobile numbers are stored as last four digits only."""
    digits = re.sub(r"\D", "", str(mobile or ""))
    return digits[-4:] if len(digits) >= 4 else ""


def _fail(text, status=None):
    """The one exit for every failure. Scrubs, keeps the gateway's own code so
    the caller can act on it, and raises `from None` so nothing unscrubbed
    survives in __cause__ for a traceback to print."""
    code = None
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        err = parsed.get("error")
        code = err.get("code") if isinstance(err, dict) else parsed.get("code")
    raise AbdmError(_scrub(text)[:400], code=code, status=status) from None


def _translated(call):
    """Run an SDK call, turning its errors into ours. The SDK raises
    EkaCareAPIError / EkaCareAuthError whose message is the gateway's response
    body, which is exactly the string an Aadhaar number would be echoed in."""
    try:
        return call()
    except EkaCareError as e:
        found = _STATUS.search(str(e))
        _fail(str(e), status=int(found.group(1)) if found else None)


class EkaAbdm:
    """Implements AbdmConnector against Eka ABDM Connect."""

    def __init__(self, base_url=None, client_id=None, client_secret=None, *,
                 hip_id=None, client=None):
        # `client` is the seam: a real EkaCareClient in production, a double in
        # the checks, so neither a credential nor a socket is needed to test.
        self._client = client or EkaCareClient(
            client_id=client_id, client_secret=client_secret,
            base_url=base_url or "https://api.eka.care",
        )
        self._hip_id = hip_id

    def for_patient(self, access_token) -> "EkaAbdm":
        """The same connector bound to one patient's ABHA token.

        Profile, card, QR and KYC act on the ABHA holder, not on the facility,
        so they need the token that patient's enrolment or login returned. The
        facility's own client credentials will authenticate and then 403.
        """
        return EkaAbdm(client=EkaCareClient(
            client_id=self._client.client_id,
            client_secret=self._client.client_secret,
            base_url=self._client.base_url,
            access_token=access_token,
        ), hip_id=self._hip_id)

    # ---- plumbing ----------------------------------------------------------

    def _authed(self, call):
        """One retry after clearing the cached token.

        The SDK caches an access token on the client and never notices it
        expire: `EkaCareClient.access_token` logs in once and keeps the string
        forever. A 401 is therefore the only signal that it went stale, and
        clearing it makes the next call log in again. This replaces the
        TokenManager that used to live beside this file.
        """
        for attempt in (1, 2):
            try:
                return _translated(call)
            except AbdmError as e:
                if e.status == 401 and attempt == 1:
                    self._client.set_access_token(None)
                    continue
                raise

    def _raw(self, path, body, *, method="POST", extra_headers=None):
        """An endpoint the SDK does not implement, on the SDK's own client.

        `raw_response=True` hands back the response before the SDK can build an
        error message out of it, so the status and the gateway's code are read
        from the response itself rather than parsed out of a string.
        """
        headers = {}
        if self._hip_id:
            headers["X-Hip-Id"] = self._hip_id
        headers.update(extra_headers or {})

        def call():
            resp = self._client.request(method=method, endpoint=path, json=body,
                                        headers=headers, raw_response=True)
            if not resp.ok:
                _fail(resp.text, status=resp.status_code)
            try:
                return resp.json() if resp.content else {}
            except ValueError:
                return {}

        return self._authed(call)

    # ---- raw REST: enrolment -----------------------------------------------

    def abha_address_exists(self, abha_address) -> bool:
        """Whether this ABHA address is already taken.

        Search before create. Addendum SSB: most outpatient footfall is repeat
        patients, so defaulting to create is how duplicates get manufactured,
        and a duplicate ABHA can only be deprecated, never undone.

        UNVERIFIED against a working gateway. Eka's validation layer answers
        correctly (8 to 18 characters, letters digits and dots, per
        catalogue/ops/phc.op.abha-link.md) but every well formed address has
        returned 500 "couldn't connect with ABDM servers" since 2026-09-10,
        still reproducing on 2026-09-11 in about 200ms.
        That 500 reaches the caller as an AbdmError with status 500 and the
        gateway's own words, which is the honest thing to show a clerk.
        """
        return bool(self._raw(CHECK_PHR, {"abha_address": abha_address}).get("exists"))

    def start_aadhaar_enrolment(self, aadhaar_number) -> dict:
        """Send an OTP to the Aadhaar-linked mobile. Returns {txn_id, hint}.

        The Aadhaar number is passed straight through and never retained: not
        on self, not in the returned dict, and scrubbed out of any error.
        """
        out = self._raw(AADHAAR_INIT, {"aadhaar_number": str(aadhaar_number).strip()})
        return {"txn_id": out.get("txn_id"), "hint": out.get("hint")}

    def create_or_link_abha(self, *, method, patient, abha_number=None) -> AbhaResult:
        raise NotImplementedError(
            "The enrolment journey past OTP init is not written yet. It needs "
            "the verify-otp and create-abha schemas, and it cannot be exercised "
            "without a live OTP, so it is human-driven by construction. The SDK "
            "does not cover it either: ekacare.abdm offers Profile only."
        )

    # ---- raw REST: care contexts -------------------------------------------

    def link_care_context(self, *, abha_address, encounter_ref, display,
                          hi_type="OPConsultation", patient_ref=None) -> None:
        """Tell ABDM this patient had a visit here, so the record is findable
        elsewhere later. Irreversible.

        The gateway answers 202 and the real outcome (LINKED or ERRORED) comes
        back later on the `abha.link_care_context` webhook. Nothing here
        receives webhooks, so a return from this method means accepted, not
        linked, and no caller may record it as linked. UNVERIFIED: never run
        against the gateway, because it needs an ABHA this side cannot yet
        create.
        """
        headers = {}
        if patient_ref:
            headers["X-Partner-Pt-Id"] = str(patient_ref)
        self._raw(CARE_CONTEXT_LINK, {
            "abha_address": abha_address,
            "care_contexts": [{
                "care_context_id": encounter_ref,
                "display": display,
                "hi_type": hi_type,
            }],
        }, extra_headers=headers)

    # ---- SDK backed: profile, card, QR -------------------------------------

    def profile(self) -> dict:
        """The patient's ABHA profile. Needs a patient token: see for_patient."""
        return self._authed(self._client.abdm_profile.get_profile)

    def abha_card(self) -> bytes:
        """The ABHA card as PNG bytes.

        The SDK asks for a raw response here and returns `.content` without
        checking the status, so an error arrives as a JSON body wearing the
        type bytes. Caught here rather than handed to a caller as an image.
        """
        card = self._authed(self._client.abdm_profile.get_abha_card)
        if card[:1] == b"{":
            _fail(card.decode(errors="replace"))
        return card

    def abha_qr(self) -> dict:
        """The data for the ABHA QR code, for the counter to render."""
        return self._authed(self._client.abdm_profile.get_abha_qr_code)

    # ---- SDK backed: KYC ---------------------------------------------------

    def start_kyc(self, *, method, identifier) -> dict:
        """Begin a KYC upgrade. `method` is "aadhaar" or "abha-number".

        `identifier` may be an Aadhaar number. It is handed to the SDK and kept
        nowhere, and any error it comes back in is scrubbed.
        """
        return self._authed(
            lambda: self._client.abdm_profile.initiate_kyc(method, identifier))

    def verify_kyc(self, *, txn_id, otp) -> dict:
        """Finish a KYC upgrade with the OTP the patient read out. The OTP is
        never stored: it is an argument, it reaches the gateway, it is gone."""
        return self._authed(
            lambda: self._client.abdm_profile.verify_kyc_otp(txn_id, otp))

    def resend_kyc_otp(self, *, txn_id) -> dict:
        return self._authed(
            lambda: self._client.abdm_profile.resend_kyc_otp(txn_id))

    def __repr__(self):
        return f"<EkaAbdm {self._client.base_url}>"
