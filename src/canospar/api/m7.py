"""M7 sparse cross-graph routing API boundary."""

from __future__ import annotations

from canospar.contracts.base import ScienceContext
from canospar.contracts.roles import RoleBundle
from canospar.contracts.routing import (
    RouteCandidateGraph,
    RouteScoreGraph,
    RoutingBundle,
    RoutingSpec,
)
from canospar.contracts.tokens import TokenBundle

from ._contract_only import contract_only


def build_route_candidates(
    tokens: TokenBundle,
    roles: RoleBundle,
    spec: RoutingSpec,
    context: ScienceContext,
) -> RouteCandidateGraph:
    del tokens, roles, spec, context
    raise contract_only("M7")


def score_routes(
    candidates: RouteCandidateGraph,
    tokens: TokenBundle,
    roles: RoleBundle,
    spec: RoutingSpec,
    context: ScienceContext,
) -> RouteScoreGraph:
    del candidates, tokens, roles, spec, context
    raise contract_only("M7")


def route_tokens(
    tokens: TokenBundle,
    roles: RoleBundle,
    spec: RoutingSpec,
    context: ScienceContext,
) -> RoutingBundle:
    del tokens, roles, spec, context
    raise contract_only("M7")
