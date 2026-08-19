from __future__ import annotations

from typing import get_type_hints

import pytest

from canospar.api.m3 import build_canonical_bands, run_m3, validate_canonical_bands
from canospar.contracts.bands import BandDefinition, BandSpec, CanonicalSpectrumBundle
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import CanonicalCoordinateSpec


def test_mass_bands_are_equal_width_and_have_no_lambda_boundaries(
    m2_bundle, coordinate_spec
) -> None:
    bands = build_canonical_bands(
        m2_bundle,
        coordinate_spec,
        BandSpec(band_count=4),
    )

    assert [(band.lower_mass, band.upper_mass) for band in bands] == [
        (0.0, 0.25),
        (0.25, 0.5),
        (0.5, 0.75),
        (0.75, 1.0),
    ]
    assert all(band.lower_lambda is None and band.upper_lambda is None for band in bands)
    assert validate_canonical_bands(bands).is_valid


def test_invalid_band_sequence_is_rejected() -> None:
    report = validate_canonical_bands(
        (
            BandDefinition("band_0", 0.0, 0.5),
            BandDefinition("band_1", 0.6, 1.0),
        )
    )

    assert not report.is_valid
    assert "M3_BAND_GAP" in {issue.code for issue in report.issues}


def test_band_definition_rejects_zero_width_boundaries() -> None:
    with pytest.raises(ValueError, match="lower < upper"):
        BandDefinition("band_0", 0.5, 0.5)


def test_canonical_bundle_requires_at_least_one_band(
    m2_bundle, m2_context, coordinate_spec
) -> None:
    result = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)

    with pytest.raises(ContractViolation, match="at least one band"):
        CanonicalSpectrumBundle(meta=result.meta, spectra=result.spectra)


def test_canonical_bundle_validation_issue_type_hints_resolve() -> None:
    hints = get_type_hints(CanonicalSpectrumBundle)

    assert "_validation_issues" in hints


def test_band_spec_rejects_any_policy_that_could_split_ties() -> None:
    with pytest.raises((ContractViolation, ValueError)):
        BandSpec(band_count=4, tie_policy="split_ties")
    with pytest.raises(ContractViolation, match="positive integer"):
        BandSpec(band_count=2.0)


def test_empty_band_policy_fails_closed_or_records_warning(
    m2_bundle, m2_context, coordinate_spec
) -> None:
    with pytest.raises(ContractViolation, match="M3_EMPTY_BAND"):
        run_m3(m2_bundle, coordinate_spec, BandSpec(band_count=10), m2_context)

    warning_spec = CanonicalCoordinateSpec(
        method="empirical_mid_cdf",
        parameters={
            "tie_atol": 0.0,
            "tie_rtol": 0.0,
            "empty_band_policy": "allow_with_warning",
        },
    )
    result = run_m3(m2_bundle, warning_spec, BandSpec(band_count=10), m2_context)

    assert result.receipt is not None
    assert "M3_EMPTY_BAND" in result.receipt.validation_issue_codes
    empty_issues = [issue for issue in result.validation_issues if issue.code == "M3_EMPTY_BAND"]
    assert empty_issues
    assert empty_issues[0].field == (
        "subject=synthetic-subject|visit=baseline|modality=dmri|"
        "relation=structural_connectivity:band_0"
    )
    assert "realized_mass=0" in empty_issues[0].message
