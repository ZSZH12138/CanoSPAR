"""M6 role and reliability contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .base import ArtifactMeta, JsonValue, Tensor, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class RoleSpec:
    backend: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class RoleBundle:
    meta: ArtifactMeta
    token_ids: tuple[str, ...] = ()
    shared_probability: Tensor | None = None
    private_probability: Tensor | None = None
    noisy_probability: Tensor | None = None
    reliability: Tensor | None = None
