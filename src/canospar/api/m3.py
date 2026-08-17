"""M3 canonical spectral-mass coordinate API."""

from __future__ import annotations

from typing import Protocol

from canospar.contracts.bands import (
    BandDefinition,
    BandSpec,
    CanonicalSpectrumArtifact,
    CanonicalSpectrumBundle,
)
from canospar.contracts.base import ScienceContext
from canospar.contracts.spectral import CanonicalCoordinateSpec, SpectralBundle

from ._contract_only import contract_only


class M3Backend(Protocol):
    def run_m3(
        self,
        spectral_bundle: SpectralBundle,
        coordinate_spec: CanonicalCoordinateSpec,
        band_spec: BandSpec,
        context: ScienceContext,
    ) -> CanonicalSpectrumBundle: ...


def canonical_mass_coordinate(
    spectrum: object,
    coordinate_spec: CanonicalCoordinateSpec,
) -> CanonicalSpectrumArtifact:
    del spectrum, coordinate_spec
    raise contract_only("M3")


def build_canonical_bands(
    spectral_bundle: SpectralBundle,
    coordinate_spec: CanonicalCoordinateSpec,
    band_spec: BandSpec,
) -> BandDefinition:
    del spectral_bundle, coordinate_spec, band_spec
    raise contract_only("M3")


def validate_canonical_bands(bands: BandDefinition) -> object:
    del bands
    raise contract_only("M3")


def run_m3(
    spectral_bundle: SpectralBundle,
    coordinate_spec: CanonicalCoordinateSpec,
    band_spec: BandSpec,
    context: ScienceContext,
) -> CanonicalSpectrumBundle:
    del spectral_bundle, coordinate_spec, band_spec, context
    raise contract_only("M3")
