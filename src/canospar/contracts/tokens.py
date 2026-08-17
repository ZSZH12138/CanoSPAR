"""M5 token contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class TokenizationSpec:
    backend: str
    token_count: int
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        if isinstance(self.token_count, bool) or self.token_count <= 0:
            raise ValueError("token_count must be a positive integer")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class TokenBundle:
    meta: ArtifactMeta
    tokens: tuple[object, ...] = ()
    assignment: object | None = None
    token_ids: tuple[str, ...] = ()
    token_metadata: Mapping[str, object] = field(default_factory=dict)
    token_mass: object | None = None
    assignment_entropy: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "token_metadata",
            _freeze_mapping(self.token_metadata, "token_metadata"),
        )
