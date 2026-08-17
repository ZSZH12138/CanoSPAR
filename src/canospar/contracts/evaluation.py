"""M9 evaluation contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class EvaluationSpec:
    backend: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class ExperimentRegistry:
    artifact_ref: str
    registry_hash: str

    def __post_init__(self) -> None:
        require_non_empty_text(self.artifact_ref, "artifact_ref")
        require_non_empty_text(self.registry_hash, "registry_hash")


@dataclass(frozen=True)
class MetricReport:
    meta: ArtifactMeta
    metrics: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", _freeze_mapping(self.metrics, "metrics"))


@dataclass(frozen=True)
class MechanismReport:
    meta: ArtifactMeta
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class RobustnessReport:
    meta: ArtifactMeta
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class StabilityReport:
    meta: ArtifactMeta
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class StatisticalTestReport:
    meta: ArtifactMeta
    values: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class EvaluationBundle:
    meta: ArtifactMeta
    reports: tuple[object, ...] = ()
