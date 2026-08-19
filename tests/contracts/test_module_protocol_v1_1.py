from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

from canospar.api import m0, m2, m3, m4
from canospar.contracts.bands import BandDefinition, BandSpec
from canospar.contracts.base import MODULE_PROTOCOL_SPEC_VERSION, ScienceContext
from canospar.contracts.errors import ContractViolation
from canospar.contracts.execution import CanonicalStatus, CompletionReceipt, cache_is_eligible
from canospar.contracts.imaging import ROIAlignedSample
from canospar.contracts.spectral import (
    LaplacianArtifact,
    SpectrumArtifact,
)
from canospar.contracts.tokens import TokenBundle
from canospar.validators.base import ValidationReport


def _receipt(module_contract_version: str, module_id: str = "M2") -> CompletionReceipt:
    return CompletionReceipt(
        module_id=module_id,
        module_contract_version=module_contract_version,
        science_contract_version="1.1.0",
        canonical_status=CanonicalStatus.PASS,
        native_status=None,
        input_artifact_ids=("input-a",),
        input_hashes=("hash-a",),
        science_key="science-a",
        reproduction_key="reproduction-a",
        runtime_profile_id="runtime-a",
        output_artifact_ids=("output-a",),
        output_hashes=("output-hash-a",),
        validator_status="PASS",
        validation_issue_codes=(),
        started_at_utc="2026-08-18T00:00:00Z",
        finished_at_utc="2026-08-18T00:01:00Z",
    )


def test_module_protocol_version_is_independent() -> None:
    assert MODULE_PROTOCOL_SPEC_VERSION == "1.1.0"


def test_v1_1_qc_state_shape_is_explicit() -> None:
    from canospar.contracts.base import QCFeatureState

    state: QCFeatureState = (0.0, -1.0, 1.0, 1.0)
    assert len(state) == 4


def test_run_m2_accepts_keyword_only_qc_state() -> None:
    parameters = inspect.signature(m2.run_m2).parameters

    assert tuple(parameters) == ("multigraph", "spec", "context", "qc_state")
    assert parameters["qc_state"].kind is inspect.Parameter.KEYWORD_ONLY


def test_m2_helpers_have_v1_1_contract_signatures() -> None:
    assert tuple(inspect.signature(m2.build_normalized_laplacian).parameters) == (
        "graph",
        "spec",
        "context",
        "parent_meta",
    )
    assert inspect.signature(m2.build_normalized_laplacian).parameters["parent_meta"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert tuple(inspect.signature(m2.transform_qc).parameters) == (
        "qc",
        "state",
        "context",
        "source_artifact_id",
        "source_content_hash",
    )
    assert inspect.signature(m2.transform_qc).parameters["source_artifact_id"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )


def test_m3_signatures_close_types_and_context() -> None:
    canonical_parameters = inspect.signature(m3.canonical_mass_coordinate).parameters
    assert tuple(canonical_parameters) == ("spectrum", "coordinate_spec", "context")

    bands_parameters = inspect.signature(m3.build_canonical_bands).parameters
    assert tuple(bands_parameters) == ("spectral_bundle", "coordinate_spec", "band_spec")

    validate_parameters = inspect.signature(m3.validate_canonical_bands).parameters
    assert tuple(validate_parameters) == ("bands",)

    canonical_hints = get_type_hints(m3.canonical_mass_coordinate)
    bands_hints = get_type_hints(m3.build_canonical_bands)
    validate_hints = get_type_hints(m3.validate_canonical_bands)
    assert canonical_hints["spectrum"] is SpectrumArtifact
    assert canonical_hints["context"] is ScienceContext
    assert bands_hints["return"] == tuple[BandDefinition, ...]
    assert validate_hints["return"] is ValidationReport


def test_v1_1_band_policy_keeps_ties_intact() -> None:
    assert BandSpec(band_count=4).tie_policy == "keep_ties_intact"
    with pytest.raises(ValueError, match="keep_ties_intact"):
        BandSpec(band_count=4, tie_policy="split_ties_by_rank")


def test_m0_required_adapters_exist_and_fail_closed() -> None:
    assert hasattr(m0, "load_split_registry")
    assert hasattr(m0, "load_task_definition")
    assert hasattr(m0, "build_imaging_input_bundle")

    with pytest.raises(NotImplementedError, match="read-only"):
        m0.load_split_registry("reports/split.json")
    with pytest.raises(NotImplementedError, match="read-only"):
        m0.load_task_definition("configs/task.yaml")
    with pytest.raises(NotImplementedError, match="read-only"):
        m0.build_imaging_input_bundle(
            None,
            None,
            None,
            subject_id="subject-a",
            visit_id="baseline",
            dataset="synthetic",
            raw_or_derivative_refs={},
            modality_available={},
            acquisition_metadata={},
            source_hashes={},
        )


def test_v1_0_module_receipt_is_not_a_v1_1_cache_hit() -> None:
    assert not cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="reproduction-a",
        artifact_hash="output-hash-a",
        receipt=_receipt("1.0.0"),
        validator_status="PASS",
    )
    assert cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="reproduction-a",
        artifact_hash="output-hash-a",
        receipt=_receipt(MODULE_PROTOCOL_SPEC_VERSION),
        validator_status="PASS",
    )
    assert cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="reproduction-a",
        artifact_hash="output-hash-a",
        receipt=_receipt("1.0.0", module_id="M1"),
        validator_status="PASS",
    )


def test_artifact_fields_no_longer_use_unbounded_object_annotations() -> None:
    for artifact_type, fields in (
        (LaplacianArtifact, ("graph_key", "payload")),
        (SpectrumArtifact, ("graph_key", "eigenvalues")),
        (ROIAlignedSample, ("modality_payloads",)),
        (TokenBundle, ("tokens", "assignment", "token_mass", "assignment_entropy")),
    ):
        hints = get_type_hints(artifact_type)
        for field_name in fields:
            annotation = repr(hints[field_name])
            assert "<class 'object'>" not in annotation
            assert "typing.Any" not in annotation


def test_m2_m3_are_implemented_but_m4_stays_fail_closed() -> None:
    with pytest.raises(ContractViolation, match="MultiGraphArtifact"):
        m2.run_m2(None, None, None)
    with pytest.raises(ContractViolation, match="spectral_bundle"):
        m3.run_m3(None, None, None, None)
    with pytest.raises(NotImplementedError, match="M4"):
        m4.filter_bands(None, None, None, None, None)
