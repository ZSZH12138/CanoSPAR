"""Validators for cross-module artifact contracts."""

from __future__ import annotations

from canospar.contracts.base import ArtifactMeta
from canospar.contracts.errors import ContractViolation
from canospar.validators.base import ValidationIssue, ValidationReport


def validate_artifact_meta(
    meta: ArtifactMeta,
    *,
    expected_schema_version: str | None = None,
    expected_content_sha256: str | None = None,
) -> ValidationReport:
    issues: list[ValidationIssue] = []
    checked: list[str] = ["artifact_meta_type", "artifact_identity_fields"]

    if not isinstance(meta, ArtifactMeta):
        raise ContractViolation("meta must be ArtifactMeta")

    if expected_schema_version is not None:
        checked.append("schema_version")
        if meta.schema_version != expected_schema_version:
            issues.append(
                ValidationIssue(
                    code="SCHEMA_VERSION_MISMATCH",
                    severity="ERROR",
                    field="schema_version",
                    message=(f"expected {expected_schema_version}, got {meta.schema_version}"),
                )
            )

    if expected_content_sha256 is not None:
        checked.append("content_sha256")
        if meta.content_sha256 != expected_content_sha256:
            issues.append(
                ValidationIssue(
                    code="ARTIFACT_HASH_MISMATCH",
                    severity="ERROR",
                    field="content_sha256",
                    message="recorded content hash does not match expected hash",
                )
            )

    return ValidationReport(
        status="FAIL" if issues else "PASS",
        checked_invariants=tuple(checked),
        issues=tuple(issues),
    )
