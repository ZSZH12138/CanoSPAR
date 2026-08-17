from dataclasses import FrozenInstanceError

import pytest

from canospar.contracts.bands import BandDefinition, BandSpec, FilterSpec
from canospar.contracts.spectral import CanonicalCoordinateSpec, M2Spec
from canospar.contracts.tokens import TokenizationSpec


def test_specs_are_frozen_and_have_explicit_backend_identity() -> None:
    spec = M2Spec(backend="exact", parameters={"normalization": "symmetric"})

    assert spec.backend == "exact"
    with pytest.raises(FrozenInstanceError):
        spec.backend = "other"  # type: ignore[misc]


def test_band_and_token_specs_keep_science_parameters() -> None:
    coordinate = CanonicalCoordinateSpec(method="empirical_spectral_cdf")
    bands = BandSpec(band_count=4, tie_policy="right")
    filtering = FilterSpec(backend="exact", parameters={"order": 3})
    tokenization = TokenizationSpec(backend="entmax", token_count=4)

    assert coordinate.method == "empirical_spectral_cdf"
    assert bands.band_count == 4
    assert filtering.parameters["order"] == 3
    assert tokenization.token_count == 4


def test_band_definition_rejects_empty_boundaries() -> None:
    with pytest.raises(ValueError):
        BandDefinition(band_id="", lower_mass=0.0, upper_mass=0.5)
