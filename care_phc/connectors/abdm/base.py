"""The ABDM connector boundary.

One interface, deliberately small: it holds only what Phase 0 calls. M3 consent
and M4 registry work arrive in later phases and can add methods then. A small
interface is also the one a second implementation can actually satisfy, which
is the point of having a boundary at all.

The v1 implementation is Eka ABDM Connect, half of it through the official
`ekacare` SDK and half raw REST where the SDK has nothing (see eka.py). Which
half a method lands in is not visible here, and must not become visible: every
method returns plain data or raises AbdmError. ohcnetwork/care_abdm exists as
an alternative target and is the honest test of this interface: if it cannot be
written behind these methods, the methods are wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AbhaResult:
    """Outcome of an ABHA create or link journey."""
    abha_number: str
    abha_address: str | None = None
    linked: bool = True


class AbdmError(RuntimeError):
    """Any failure from the ABDM side. Carries the code the gateway gave us.

    The only error type that crosses this boundary. An SDK exception is
    translated into one of these and scrubbed on the way, so no Aadhaar number
    can reach a caller, a log or a traceback through an error object we did not
    build ourselves.
    """

    def __init__(self, message, *, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class AbdmConnector(Protocol):
    """What the operation catalogue needs from ABDM in Phase 0."""

    def abha_address_exists(self, abha_address) -> bool:
        """Whether this ABHA address is taken. Search before create."""

    def start_aadhaar_enrolment(self, aadhaar_number) -> dict:
        """Send an OTP to the Aadhaar-linked mobile. Returns {txn_id, hint}.
        The Aadhaar number is never retained by an implementation."""

    def create_or_link_abha(self, *, method: str, patient: dict,
                            abha_number: str | None = None) -> AbhaResult:
        """Run the create or link journey. Irreversible: a duplicate ABHA can
        only be deprecated, never undone, which is why phc.op.abha-link carries
        irreversibility: irreversible and can never be confirmed by an agent."""

    def link_care_context(self, *, abha_address: str, encounter_ref: str,
                          display: str, hi_type: str = "OPConsultation",
                          patient_ref: str | None = None) -> None:
        """Tell ABDM this patient had a visit here, so the record is findable
        elsewhere later. Also irreversible.

        Keyed on the ABHA address rather than the ABHA number, because that is
        what Eka's link API takes. Returning means the gateway accepted the
        request, not that the context is linked: the outcome arrives later on a
        webhook, and a caller that has no webhook must not record it as linked.
        """

    # The ABHA holder's own surfaces. These act on the patient, not on the
    # facility, so they need a connector bound to that patient's token.

    def for_patient(self, access_token: str) -> "AbdmConnector":
        """The same connector authenticated as one ABHA holder."""

    def profile(self) -> dict:
        """The patient's ABHA profile."""

    def abha_card(self) -> bytes:
        """The ABHA card as PNG bytes, for the counter to print or show."""

    def abha_qr(self) -> dict:
        """The data behind the ABHA QR code."""

    def start_kyc(self, *, method: str, identifier: str) -> dict:
        """Begin a KYC upgrade with an Aadhaar or ABHA number."""

    def verify_kyc(self, *, txn_id: str, otp: str) -> dict:
        """Finish it with the OTP the patient read out. Never persist the OTP."""

    def resend_kyc_otp(self, *, txn_id: str) -> dict:
        """Send that OTP again."""
