"""The ABDM connector boundary.

One interface, deliberately small: it holds only what Phase 0 calls. M3 consent
and M4 registry work arrive in later phases and can add methods then. A small
interface is also the one a second implementation can actually satisfy, which
is the point of having a boundary at all.

The v1 implementation is Eka ABDM Connect. ohcnetwork/care_abdm exists as an
alternative target and is the honest test of this interface: if it cannot be
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
    """Any failure from the ABDM side. Carries the code the gateway gave us."""

    def __init__(self, message, *, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class AbdmConnector(Protocol):
    """What the operation catalogue needs from ABDM in Phase 0."""

    def create_or_link_abha(self, *, method: str, patient: dict,
                            abha_number: str | None = None) -> AbhaResult:
        """Run the create or link journey. Irreversible: a duplicate ABHA can
        only be deprecated, never undone, which is why phc.op.abha-link carries
        irreversibility: irreversible and can never be confirmed by an agent."""

    def link_care_context(self, *, abha_number: str, encounter_ref: str,
                          display: str) -> None:
        """Tell ABDM this patient had a visit here, so the record is findable
        elsewhere later. Also irreversible."""
