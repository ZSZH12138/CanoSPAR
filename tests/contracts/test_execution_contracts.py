from canospar.contracts.base import ScienceContext, build_science_key
from canospar.contracts.execution import (
    CanonicalStatus,
    CompletionReceipt,
    ModuleRunResult,
    cache_is_eligible,
)
from canospar.runtime.profile import RuntimeProfile
from canospar.validators.base import ValidationIssue, ValidationReport


def make_receipt(
    *,
    science_key: str = "science-a",
    reproduction_key: str = "reproduction-a",
    status: CanonicalStatus = CanonicalStatus.PASS,
) -> CompletionReceipt:
    return CompletionReceipt(
        module_id="M1",
        module_contract_version="1.0.0",
        science_contract_version="1.1.0",
        canonical_status=status,
        native_status="PASS_WITH_MANUAL_REVIEW",
        input_artifact_ids=("input-a",),
        input_hashes=("hash-a",),
        science_key=science_key,
        reproduction_key=reproduction_key,
        runtime_profile_id="runtime-a",
        output_artifact_ids=("output-a",),
        output_hashes=("output-hash-a",),
        validator_status="PASS",
        validation_issue_codes=(),
        started_at_utc="2026-08-17T00:00:00Z",
        finished_at_utc="2026-08-17T00:01:00Z",
    )


def test_completion_receipt_and_module_result_are_immutable() -> None:
    receipt = make_receipt()
    result = ModuleRunResult(
        canonical_status=CanonicalStatus.PASS,
        native_status="PASS_WITH_MANUAL_REVIEW",
        artifact="synthetic-artifact",
        receipt=receipt,
        issues=(),
    )

    assert result.receipt is receipt
    assert result.canonical_status is CanonicalStatus.PASS


def test_cache_reuse_requires_all_identity_and_validation_conditions() -> None:
    receipt = make_receipt()

    assert cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="reproduction-a",
        artifact_hash="output-hash-a",
        receipt=receipt,
        validator_status="PASS",
    )
    assert not cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="different",
        artifact_hash="output-hash-a",
        receipt=receipt,
        validator_status="PASS",
    )
    assert not cache_is_eligible(
        expected_science_key="science-a",
        expected_reproduction_key="reproduction-a",
        artifact_hash="different",
        receipt=receipt,
        validator_status="PASS",
    )


def test_runtime_profile_changes_do_not_change_science_identity() -> None:
    context = ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="config-a",
        dataset_manifest_hash="manifest-a",
        split_id="outer-0",
        random_seed=7,
    )
    runtime_a = RuntimeProfile(profile_id="runtime-a", cpu_count=2, gpu_count=0)
    runtime_b = RuntimeProfile(profile_id="runtime-b", cpu_count=32, gpu_count=4)

    key_a = build_science_key(context, ("hash-a",), "M1", runtime_profile_id=runtime_a.profile_id)
    key_b = build_science_key(context, ("hash-a",), "M1", runtime_profile_id=runtime_b.profile_id)

    assert key_a == key_b


def test_validation_report_keeps_issue_details() -> None:
    issue = ValidationIssue(
        code="SCHEMA_VERSION_MISMATCH",
        severity="ERROR",
        field="schema_version",
        message="schema mismatch",
    )
    report = ValidationReport(
        status="FAIL",
        checked_invariants=("schema_version",),
        issues=(issue,),
    )

    assert report.issues[0].code == "SCHEMA_VERSION_MISMATCH"
