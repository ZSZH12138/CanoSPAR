"""Contract-layer exceptions with scientific/runtime separation."""

from __future__ import annotations


class ContractViolation(ValueError):
    """Base error for invalid architecture or artifact contracts."""


class SchemaVersionMismatch(ContractViolation):
    """An artifact schema is not supported by the consumer."""


class ArtifactHashMismatch(ContractViolation):
    """An artifact content hash does not match its recorded identity."""


class UpstreamArtifactInvalid(ContractViolation):
    """An upstream artifact failed validation."""


class DatasetLineageMismatch(ContractViolation):
    """An artifact belongs to a different dataset lineage."""


class SplitMismatch(ContractViolation):
    """An artifact belongs to a different split."""


class LeakageViolation(ContractViolation):
    """A scientific split or provenance invariant was violated."""


class NumericalValidationError(ContractViolation):
    """A numerical invariant failed."""


class ArtifactNotReady(ContractViolation):
    """An artifact is not in a consumable state."""


class RuntimeResourceBlocked(RuntimeError):
    """Execution was blocked by runtime resources, not scientific semantics."""
