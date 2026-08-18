"""Version and implementation governance for Architecture Contract v1."""

from __future__ import annotations

from enum import StrEnum

ARCHITECTURE_CONTRACT_VERSION = "1.0.0"
SCIENCE_CONTRACT_VERSION = "1.1.0"
SCHEMA_VERSION = "1.0.0"
RUNTIME_PROFILE_VERSION = "1.0.0"
NUMERICS_PROFILE_SCHEMA_VERSION = "1.0.0"
MODULE_PROTOCOL_SPEC_VERSION = "1.1.0"


class ImplementationStatus(StrEnum):
    """Allowed registry states."""

    EXISTING = "EXISTING"
    PARTIAL = "PARTIAL"
    CONTRACT_ONLY = "CONTRACT_ONLY"
    IMPLEMENTED = "IMPLEMENTED"
    VERIFIED = "VERIFIED"
