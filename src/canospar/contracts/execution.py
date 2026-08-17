"""Execution receipts and fail-closed cache eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from canospar.validators.base import ValidationIssue

from .base import _freeze_string_tuple, require_non_empty_text

_Artifact = TypeVar("_Artifact")


class CanonicalStatus(StrEnum):
    PASS = "PASS"
    READY = "READY"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class CompletionReceipt:
    module_id: str
    module_contract_version: str
    science_contract_version: str
    canonical_status: CanonicalStatus
    native_status: str | None
    input_artifact_ids: tuple[str, ...]
    input_hashes: tuple[str, ...]
    science_key: str
    reproduction_key: str
    runtime_profile_id: str
    output_artifact_ids: tuple[str, ...]
    output_hashes: tuple[str, ...]
    validator_status: str
    validation_issue_codes: tuple[str, ...]
    started_at_utc: str
    finished_at_utc: str

    def __post_init__(self) -> None:
        for field_name in (
            "module_id",
            "module_contract_version",
            "science_contract_version",
            "science_key",
            "reproduction_key",
            "runtime_profile_id",
            "validator_status",
            "started_at_utc",
            "finished_at_utc",
        ):
            require_non_empty_text(getattr(self, field_name), field_name)
        if not isinstance(self.canonical_status, CanonicalStatus):
            raise ValueError("canonical_status must be CanonicalStatus")
        for field_name in (
            "input_artifact_ids",
            "input_hashes",
            "output_artifact_ids",
            "output_hashes",
            "validation_issue_codes",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_string_tuple(getattr(self, field_name), field_name),
            )
        if len(self.input_artifact_ids) != len(self.input_hashes):
            raise ValueError("input artifact IDs and hashes must have equal lengths")
        if len(self.output_artifact_ids) != len(self.output_hashes):
            raise ValueError("output artifact IDs and hashes must have equal lengths")


@dataclass(frozen=True)
class ModuleRunResult(Generic[_Artifact]):
    canonical_status: CanonicalStatus
    native_status: str | None
    artifact: _Artifact | None
    receipt: CompletionReceipt | None
    issues: tuple[ValidationIssue, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_status, CanonicalStatus):
            raise ValueError("canonical_status must be CanonicalStatus")
        object.__setattr__(self, "issues", tuple(self.issues))


def cache_is_eligible(
    *,
    expected_science_key: str,
    expected_reproduction_key: str,
    artifact_hash: str,
    receipt: CompletionReceipt,
    validator_status: str,
) -> bool:
    return (
        receipt.canonical_status in {CanonicalStatus.PASS, CanonicalStatus.READY}
        and receipt.science_key == expected_science_key
        and receipt.reproduction_key == expected_reproduction_key
        and artifact_hash in receipt.output_hashes
        and receipt.validator_status == validator_status == "PASS"
    )
