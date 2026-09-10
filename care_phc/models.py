"""The only state we store. Everything else about a thread is derived.

Subclasses CARE's EMRBaseModel so history, meta, created_by and updated_by come
along, and this appears in care/audit_log like every other resource.
"""
from django.contrib.postgres.fields import ArrayField
from django.db import models

from care.emr.models.base import EMRBaseModel

from care_phc.thread import STORED


class EncounterThread(EMRBaseModel):
    """Per-encounter baton. One row per encounter, created on registration.

    `flags` holds only what CARE cannot answer for us, which is currently three
    things: whether the patient consented to ambient capture for this visit,
    and whether a vital or a lab value crossed a critical threshold. The
    thresholds are ours, so the flags are ours; everything else is derived from
    CARE resources at read time. See care_phc/thread.py.
    """

    encounter = models.OneToOneField(
        "emr.Encounter", on_delete=models.CASCADE, related_name="phc_thread"
    )
    flags = ArrayField(models.CharField(max_length=64), default=list, blank=True)

    # Visit-scoped ambient capture consent. Deliberately NOT CARE's Consent
    # model, which is FHIR Consent for care and treatment, and deliberately not
    # ABDM consent, which governs record sharing. Addendum E.3 is explicit that
    # these are three different things and must not share a screen.
    capture_consent_at = models.DateTimeField(null=True, blank=True)
    capture_withdrawn_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "phc_encounter_thread"

    def raise_flag(self, flag):
        if flag not in STORED:
            raise ValueError(f"{flag} is derived from CARE, it cannot be stored")
        if flag not in self.flags:
            self.flags = [*self.flags, flag]
