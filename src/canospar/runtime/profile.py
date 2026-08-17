"""Replaceable execution/runtime profile."""

from __future__ import annotations

from dataclasses import dataclass

from canospar.contracts.base import require_non_empty_text
from canospar.contracts.governance import RUNTIME_PROFILE_VERSION


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    profile_version: str = RUNTIME_PROFILE_VERSION
    cpu_count: int | None = None
    ram_gib: float | None = None
    gpu_count: int | None = None
    gpu_model: str | None = None
    cuda_version: str | None = None
    worker_count: int | None = None
    thread_limit: int | None = None
    container_runtime: str | None = None
    scheduler: str | None = None
    transport: str | None = None
    server_class: str | None = None

    def __post_init__(self) -> None:
        require_non_empty_text(self.profile_id, "profile_id")
        require_non_empty_text(self.profile_version, "profile_version")
        for field_name in ("cpu_count", "gpu_count", "worker_count", "thread_limit"):
            value = getattr(self, field_name)
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.ram_gib is not None and self.ram_gib < 0:
            raise ValueError("ram_gib must be non-negative or None")
