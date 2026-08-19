from __future__ import annotations

from dataclasses import replace

import pytest

from canospar.api.m3 import run_m3
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import CanonicalCoordinateSpec
from canospar.validators.m3 import validate_m3_bundle


def test_m3_is_deterministic_and_runtime_profile_independent(
    m2_bundle, m2_context, coordinate_spec
) -> None:
    from canospar.contracts.bands import BandSpec

    first = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)
    second = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)

    assert first.meta.artifact_id == second.meta.artifact_id
    assert first.meta.content_sha256 == second.meta.content_sha256
    assert first.science_key == second.science_key
    assert first.reproduction_key == second.reproduction_key
    assert first.receipt is not None


def test_upstream_producer_mismatch_fails_closed(m2_bundle, m2_context, coordinate_spec) -> None:
    from canospar.contracts.bands import BandSpec

    bad_meta = replace(m2_bundle.meta, producer_module="M1")
    bad_bundle = replace(m2_bundle, meta=bad_meta)

    with pytest.raises(ContractViolation):
        run_m3(bad_bundle, coordinate_spec, BandSpec(3), m2_context)


def test_coordinate_method_mismatch_fails_closed(m2_bundle, m2_context) -> None:
    from canospar.contracts.bands import BandSpec

    spec = CanonicalCoordinateSpec(
        method="lambda_quantile",
        parameters={"tie_atol": 0.0, "tie_rtol": 0.0, "empty_band_policy": "fail"},
    )

    with pytest.raises(ContractViolation):
        run_m3(m2_bundle, spec, BandSpec(3), m2_context)


def test_tampering_with_a_canonical_coordinate_invalidates_the_receipt(
    m2_bundle, m2_context, coordinate_spec
) -> None:
    from canospar.contracts.bands import BandSpec

    result = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)
    changed = replace(
        result.spectra[0],
        u_coordinate=result.spectra[0].u_coordinate + 0.001,
    )
    tampered = replace(result, spectra=(changed, *result.spectra[1:]))

    assert tampered.receipt is None


def test_source_spectrum_id_must_match_canonical_artifact_lineage(
    m2_bundle, m2_context, coordinate_spec
) -> None:
    from canospar.contracts.bands import BandSpec

    band_spec = BandSpec(3)
    result = run_m3(m2_bundle, coordinate_spec, band_spec, m2_context)
    changed = replace(result.spectra[0], spectrum_artifact_id="forged-source-id")
    tampered = replace(result, spectra=(changed, *result.spectra[1:]))

    report = validate_m3_bundle(tampered, m2_bundle, coordinate_spec, band_spec, m2_context)

    assert not report.is_valid
    assert "M3_SPECTRUM_ARTIFACT_ID" in {issue.code for issue in report.issues}


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("science_contract_version", "tampered-science-contract"),
        ("native_status", "SCIENTIFICALLY_VERIFIED"),
        ("validation_issue_codes", ("M3_EMPTY_BAND",)),
    ),
)
def test_receipt_status_and_lineage_tampering_invalidates_receipt(
    m2_bundle, m2_context, coordinate_spec, field_name, value
) -> None:
    from canospar.contracts.bands import BandSpec

    result = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)
    assert result._validated_receipt is not None
    changed_receipt = replace(result._validated_receipt, **{field_name: value})
    tampered = replace(result, _validated_receipt=changed_receipt)

    assert tampered.receipt is None
