"""M8 readout, prediction, and objective API boundary."""

from __future__ import annotations

from canospar.contracts.base import ScienceContext
from canospar.contracts.prediction import (
    LossBundle,
    PredictionBundle,
    ReadoutSpec,
    SampleEmbedding,
)
from canospar.contracts.roles import RoleBundle
from canospar.contracts.routing import RoutingBundle
from canospar.contracts.tokens import TokenBundle

from ._contract_only import contract_only


def readout_sample(
    tokens: TokenBundle,
    roles: RoleBundle,
    routes: RoutingBundle,
    spec: ReadoutSpec,
    context: ScienceContext,
) -> SampleEmbedding:
    del tokens, roles, routes, spec, context
    raise contract_only("M8")


def predict_sample(
    tokens: TokenBundle,
    roles: RoleBundle,
    routes: RoutingBundle,
    spec: ReadoutSpec,
    context: ScienceContext,
) -> PredictionBundle:
    del tokens, roles, routes, spec, context
    raise contract_only("M8")


def compute_objective(
    prediction: PredictionBundle,
    context: ScienceContext,
) -> LossBundle:
    del prediction, context
    raise contract_only("M8")
