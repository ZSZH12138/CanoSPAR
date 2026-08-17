"""M6 role and reliability API boundary."""

from __future__ import annotations

from canospar.contracts.base import ScienceContext
from canospar.contracts.roles import RoleBundle, RoleSpec
from canospar.contracts.tokens import TokenBundle

from ._contract_only import contract_only


def infer_roles(
    tokens: TokenBundle,
    normalized_qc: object,
    availability: object,
    spec: RoleSpec,
    context: ScienceContext,
) -> RoleBundle:
    del tokens, normalized_qc, availability, spec, context
    raise contract_only("M6")


def validate_role_bundle(roles: RoleBundle) -> object:
    del roles
    raise contract_only("M6")
