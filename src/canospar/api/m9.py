"""M9 read-only evaluation and interpretation API boundary."""

from __future__ import annotations

from canospar.contracts.bands import CanonicalSpectrumBundle
from canospar.contracts.evaluation import (
    EvaluationBundle,
    EvaluationSpec,
    ExperimentRegistry,
    MechanismReport,
    MetricReport,
    RobustnessReport,
    StabilityReport,
    StatisticalTestReport,
)
from canospar.contracts.prediction import PredictionBundle
from canospar.contracts.roles import RoleBundle
from canospar.contracts.routing import RoutingBundle
from canospar.contracts.spectral import SpectralBundle

from ._contract_only import contract_only


def evaluate_predictions(
    prediction: PredictionBundle,
    registry: ExperimentRegistry,
) -> MetricReport:
    del prediction, registry
    raise contract_only("M9")


def evaluate_spectral_mechanism(
    spectral: SpectralBundle,
    canonical: CanonicalSpectrumBundle,
    spec: EvaluationSpec,
) -> MechanismReport:
    del spectral, canonical, spec
    raise contract_only("M9")


def evaluate_robustness(
    prediction: PredictionBundle,
    spec: EvaluationSpec,
) -> RobustnessReport:
    del prediction, spec
    raise contract_only("M9")


def evaluate_route_stability(
    routes: RoutingBundle,
    roles: RoleBundle,
    spec: EvaluationSpec,
) -> StabilityReport:
    del routes, roles, spec
    raise contract_only("M9")


def run_statistical_tests(
    prediction: PredictionBundle,
    registry: ExperimentRegistry,
    spec: EvaluationSpec,
) -> StatisticalTestReport:
    del prediction, registry, spec
    raise contract_only("M9")


def evaluate(
    prediction: PredictionBundle,
    routes: RoutingBundle,
    roles: RoleBundle,
    spectral: SpectralBundle,
    canonical: CanonicalSpectrumBundle,
    registry: ExperimentRegistry,
) -> EvaluationBundle:
    del prediction, routes, roles, spectral, canonical, registry
    raise contract_only("M9")
