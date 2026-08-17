"""M8 prediction and objective contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class ReadoutSpec:
    backend: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class SampleEmbedding:
    meta: ArtifactMeta
    shared_embedding: object | None = None
    private_embedding: object | None = None
    global_embedding: object | None = None


@dataclass(frozen=True)
class PredictionBundle:
    meta: ArtifactMeta
    prediction: object
    embedding: SampleEmbedding | None = None


@dataclass(frozen=True)
class LossBundle:
    meta: ArtifactMeta
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))
