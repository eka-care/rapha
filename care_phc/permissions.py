"""Register our capabilities and bundles with CARE's own permission system.

CARE's primitive is already the one addendum SSC asks for: a Permission granted
to Roles, scoped by context, assigned to a person through organization
membership. So we add to it rather than building a second one beside it. Two
permission layers over one record is two places to get permissions wrong.

Everything here is generated from catalogue/vocab.py, so adding a capability
there registers it. A hand-written copy of that list would drift from the
catalogue the guard reads, and a capability the guard enforces but CARE has
never heard of is a operation nobody can invoke.

Bundles ship as is_system=True roles. A facility's own combination is an
is_system=False role made in the admin, which CARE's sync_permissions_roles
command deliberately leaves alone. That is addendum SSC's "bundles are
defaults, not walls", and it is already built.
"""
import enum

from care.security.permissions.constants import Permission, PermissionContext
from care.security.roles.role import Role, RoleContext

from catalogue import vocab

# Which part of CARE a capability acts on. Used only for grouping in the admin.
CONTEXTS = {
    "patient.find": PermissionContext.PATIENT,
    "patient.register": PermissionContext.PATIENT,
    "abha.link": PermissionContext.PATIENT,
    "vitals.record": PermissionContext.ENCOUNTER,
    "assessment.record": PermissionContext.ENCOUNTER,
    "encounter.document": PermissionContext.ENCOUNTER,
    "rx.prescribe": PermissionContext.ENCOUNTER,
    "lab.order": PermissionContext.ENCOUNTER,
    "lab.result.enter": PermissionContext.ENCOUNTER,
    "lab.result.validate": PermissionContext.ENCOUNTER,
    "pharmacy.dispense": PermissionContext.ENCOUNTER,
    "visit.household": PermissionContext.ENCOUNTER,
    "appointment.book": PermissionContext.FACILITY,
    "handover": PermissionContext.ENCOUNTER,
    "facility.admin": PermissionContext.FACILITY,
    "reporting.view": PermissionContext.FACILITY,
}

BUNDLE_DESCRIPTIONS = {
    "frontdesk": "Front desk. Finds patients, registers, links ABHA, books slots.",
    "nurse": "Nurse. Front desk plus vitals and assessments.",
    "mo": "Medical officer. Broadest read of the record, writes confined to "
          "clinical scope. Deliberately not master access.",
    "lab": "Laboratory technician. Enters results, cannot release them.",
    "lab_incharge": "Laboratory in-charge. Enters and releases results.",
    "pharmacist": "Pharmacist. Dispenses against a confirmed prescription.",
    "asha": "Accredited social health activist. Household visits and assessments.",
    "anm": "Auxiliary nurse midwife. ASHA plus vitals.",
    "cho": "Community health officer. ANM plus documentation, orders, and "
           "prescribing bounded by an approved formulary.",
}


def slug(capability):
    """`lab.result.enter` -> `can_lab_result_enter`. This is the DB slug."""
    return "can_" + capability.replace(".", "_")


ROLES = {
    name: Role(
        name=BUNDLE_DESCRIPTIONS[name].split(".")[0],
        description=BUNDLE_DESCRIPTIONS[name],
        contexts=[RoleContext.FACILITY],
    )
    for name in vocab.BUNDLES
}

PhcPermissions = enum.Enum(
    "PhcPermissions",
    {
        slug(cap): Permission(
            cap,
            f"Capability {cap}",
            CONTEXTS[cap],
            [ROLES[b] for b, caps in vocab.BUNDLES.items() if cap in caps],
        )
        for cap in sorted(vocab.CAPABILITIES)
    },
)


def register():
    """Called from the plug's AppConfig.ready()."""
    from care.security.permissions.base import PermissionController
    from care.security.roles.role import RoleController

    for role in ROLES.values():
        RoleController.register_role(role)
    PermissionController.override_permission_handlers.append(PhcPermissions)
