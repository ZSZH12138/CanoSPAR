from __future__ import annotations

import pytest
import torch
from conftest import make_spectrum

from canospar.api.m3 import canonical_mass_coordinate
from canospar.contracts.errors import ContractViolation


def test_empirical_mid_cdf_uses_mid_ranks_for_unique_values(coordinate_spec, context) -> None:
    result = canonical_mass_coordinate(
        make_spectrum([1.0, 2.0, 3.0, 4.0]), coordinate_spec, context
    )

    assert torch.allclose(
        result.u_coordinate,
        torch.tensor([0.125, 0.375, 0.625, 0.875], dtype=torch.float64),
    )
    assert torch.equal(
        result.lambda_coordinate,
        torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=torch.float64),
    )


def test_tied_values_share_one_mid_rank_without_arbitrary_split(coordinate_spec, context) -> None:
    result = canonical_mass_coordinate(
        make_spectrum([1.0, 1.0, 2.0, 3.0, 3.0]), coordinate_spec, context
    )

    assert torch.allclose(
        result.u_coordinate,
        torch.tensor([0.2, 0.2, 0.5, 0.8, 0.8], dtype=torch.float64),
    )


@pytest.mark.parametrize("values, expected", [([2.0], [0.5]), ([2.0, 2.0, 2.0], [0.5, 0.5, 0.5])])
def test_singleton_and_all_tied_spectra_are_defined(
    values, expected, coordinate_spec, context
) -> None:
    result = canonical_mass_coordinate(make_spectrum(values), coordinate_spec, context)

    assert torch.allclose(result.u_coordinate, torch.tensor(expected, dtype=torch.float64))


@pytest.mark.parametrize(
    "parameters",
    [
        {"tie_atol": 0.0, "tie_rtol": 0.0},
        {"tie_atol": -1.0, "tie_rtol": 0.0, "empty_band_policy": "fail"},
        {"tie_atol": 0.0, "tie_rtol": float("nan"), "empty_band_policy": "fail"},
        {"tie_atol": 0.0, "tie_rtol": 0.0, "empty_band_policy": "unknown"},
    ],
)
def test_coordinate_parameters_are_explicit_and_validated(parameters, context) -> None:
    from canospar.contracts.spectral import CanonicalCoordinateSpec

    spec = CanonicalCoordinateSpec(method="empirical_mid_cdf", parameters=parameters)
    with pytest.raises(ContractViolation):
        canonical_mass_coordinate(make_spectrum([1.0, 2.0]), spec, context)


def test_coordinate_generation_does_not_mutate_upstream_spectrum(coordinate_spec, context) -> None:
    source = make_spectrum([1.0, 1.0, 3.0])
    before = source.eigenvalues.clone()

    canonical_mass_coordinate(source, coordinate_spec, context)

    assert torch.equal(source.eigenvalues, before)
