"""M2 and spectral-coordinate contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text
from .errors import ContractViolation


@dataclass(frozen=True)
class M2Spec:
    backend: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class CanonicalCoordinateSpec:
    method: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.method, "method")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class LaplacianArtifact:
    meta: ArtifactMeta
    graph_key: object
    payload: object


@dataclass(frozen=True)
class SpectrumArtifact:
    meta: ArtifactMeta
    graph_key: object
    eigenvalues: object


@dataclass(frozen=True)
class SpectralStatistics:
    meta: ArtifactMeta
    graph_key: object
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class NormalizedQCArtifact:
    meta: ArtifactMeta
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class SpectralBundle:
    meta: ArtifactMeta
    laplacians: tuple[LaplacianArtifact, ...] = ()
    spectra: tuple[SpectrumArtifact, ...] = ()
    statistics: tuple[SpectralStatistics, ...] = ()
    normalized_qc: NormalizedQCArtifact | None = None
