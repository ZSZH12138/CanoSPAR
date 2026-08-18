"""M8 prediction and objective contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .base import ArtifactMeta, JsonValue, Tensor, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class ReadoutSpec:
    backend: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class SampleEmbedding:
    meta: ArtifactMeta
    shared_embedding: Tensor | None = None
    private_embedding: Tensor | None = None
    global_embedding: Tensor | None = None


@dataclass(frozen=True)
class PredictionBundle:
    meta: ArtifactMeta
    prediction: Tensor
    embedding: SampleEmbedding | None = None


@dataclass(frozen=True)
class LossBundle:
    meta: ArtifactMeta
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))
