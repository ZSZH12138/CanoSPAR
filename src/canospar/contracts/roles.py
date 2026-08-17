"""M6 role and reliability contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class RoleSpec:
    backend: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class RoleBundle:
    meta: ArtifactMeta
    token_ids: tuple[str, ...] = ()
    shared_probability: object | None = None
    private_probability: object | None = None
    noisy_probability: object | None = None
    reliability: object | None = None
