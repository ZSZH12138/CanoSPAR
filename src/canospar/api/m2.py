"""M2 Laplacian, spectrum, and graph-quality API boundary."""

from __future__ import annotations

from typing import Protocol

from canospar.contracts.base import MultiGraphArtifact, ScienceContext
from canospar.contracts.spectral import (
    LaplacianArtifact,
    M2Spec,
    NormalizedQCArtifact,
    SpectralBundle,
    SpectralStatistics,
    SpectrumArtifact,
)

from ._contract_only import contract_only


class M2Backend(Protocol):
    def run_m2(
        self,
        multigraph: MultiGraphArtifact,
        spec: M2Spec,
        context: ScienceContext,
    ) -> SpectralBundle: ...


def build_normalized_laplacian(graph: object, spec: M2Spec) -> LaplacianArtifact:
    del graph, spec
    raise contract_only("M2")


def compute_spectrum(laplacian: LaplacianArtifact, spec: M2Spec) -> SpectrumArtifact:
    del laplacian, spec
    raise contract_only("M2")


def compute_spectral_statistics(
    laplacian: LaplacianArtifact,
    spectrum: SpectrumArtifact,
    node_features: object,
) -> SpectralStatistics:
    del laplacian, spectrum, node_features
    raise contract_only("M2")


def fit_qc_transform(train_qc: object, spec: M2Spec) -> object:
    del train_qc, spec
    raise contract_only("M2")


def transform_qc(qc: object, state: object) -> NormalizedQCArtifact:
    del qc, state
    raise contract_only("M2")


def run_m2(
    multigraph: MultiGraphArtifact,
    spec: M2Spec,
    context: ScienceContext,
) -> SpectralBundle:
    del multigraph, spec, context
    raise contract_only("M2")
