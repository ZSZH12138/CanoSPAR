"""M4 spectral filtering API boundary."""

from __future__ import annotations

from canospar.contracts.bands import BandSignalBundle, CanonicalSpectrumBundle, FilterSpec
from canospar.contracts.base import MultiGraphArtifact, ScienceContext
from canospar.contracts.spectral import SpectralBundle

from ._contract_only import contract_only


def filter_exact(
    multigraph: MultiGraphArtifact,
    spectral_bundle: SpectralBundle,
    canonical_bundle: CanonicalSpectrumBundle,
    spec: FilterSpec,
    context: ScienceContext,
) -> BandSignalBundle:
    del multigraph, spectral_bundle, canonical_bundle, spec, context
    raise contract_only("M4")


def filter_chebyshev(
    multigraph: MultiGraphArtifact,
    spectral_bundle: SpectralBundle,
    canonical_bundle: CanonicalSpectrumBundle,
    spec: FilterSpec,
    context: ScienceContext,
) -> BandSignalBundle:
    del multigraph, spectral_bundle, canonical_bundle, spec, context
    raise contract_only("M4")


def filter_bands(
    multigraph: MultiGraphArtifact,
    spectral_bundle: SpectralBundle,
    canonical_bundle: CanonicalSpectrumBundle,
    spec: FilterSpec,
    context: ScienceContext,
) -> BandSignalBundle:
    del multigraph, spectral_bundle, canonical_bundle, spec, context
    raise contract_only("M4")
