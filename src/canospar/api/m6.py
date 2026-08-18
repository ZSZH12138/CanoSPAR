"""M6 role and reliability API boundary."""

from __future__ import annotations

from canospar.contracts.base import AvailabilityMask, ScienceContext
from canospar.contracts.roles import RoleBundle, RoleSpec
from canospar.contracts.spectral import NormalizedQCArtifact
from canospar.contracts.tokens import TokenBundle
from canospar.validators.base import ValidationReport

from ._contract_only import contract_only


def infer_roles(
    tokens: TokenBundle,
    normalized_qc: NormalizedQCArtifact,
    availability: AvailabilityMask,
    spec: RoleSpec,
    context: ScienceContext,
) -> RoleBundle:
    del tokens, normalized_qc, availability, spec, context
    raise contract_only("M6")


def validate_role_bundle(roles: RoleBundle) -> ValidationReport:
    del roles
    raise contract_only("M6")
