"""Common validation report objects."""

from __future__ import annotations

from dataclasses import dataclass

from canospar.contracts.base import require_non_empty_text


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    field: str | None
    message: str

    def __post_init__(self) -> None:
        require_non_empty_text(self.code, "code")
        require_non_empty_text(self.severity, "severity")
        require_non_empty_text(self.message, "message")
        if self.field is not None:
            require_non_empty_text(self.field, "field")


@dataclass(frozen=True)
class ValidationReport:
    status: str
    checked_invariants: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    def __post_init__(self) -> None:
        require_non_empty_text(self.status, "status")
        object.__setattr__(self, "checked_invariants", tuple(self.checked_invariants))
        object.__setattr__(self, "issues", tuple(self.issues))

    @property
    def is_valid(self) -> bool:
        return self.status in {"PASS", "READY"}
