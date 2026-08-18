"""M3/M4 band and filter contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .base import (
    ArtifactMeta,
    BandKey,
    GraphKey,
    JsonValue,
    Tensor,
    _freeze_mapping,
    require_non_empty_text,
)
from .errors import ContractViolation


@dataclass(frozen=True)
class BandSpec:
    band_count: int
    tie_policy: str = "keep_ties_intact"

    def __post_init__(self) -> None:
        if isinstance(self.band_count, bool) or self.band_count <= 0:
            raise ContractViolation("band_count must be a positive integer")
        require_non_empty_text(self.tie_policy, "tie_policy")
        if self.tie_policy != "keep_ties_intact":
            raise ValueError("tie_policy must be keep_ties_intact")


@dataclass(frozen=True)
class FilterSpec:
    backend: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class CanonicalSpectrumArtifact:
    meta: ArtifactMeta
    graph_key: GraphKey
    spectrum_artifact_id: str
    u_coordinate: Tensor
    lambda_coordinate: Tensor

    def __post_init__(self) -> None:
        require_non_empty_text(self.spectrum_artifact_id, "spectrum_artifact_id")


@dataclass(frozen=True)
class BandDefinition:
    band_id: str
    lower_mass: float
    upper_mass: float
    lower_lambda: float | None = None
    upper_lambda: float | None = None

    def __post_init__(self) -> None:
        require_non_empty_text(self.band_id, "band_id")
        if not 0.0 <= self.lower_mass <= self.upper_mass <= 1.0:
            raise ValueError("band mass boundaries must satisfy 0 <= lower <= upper <= 1")


@dataclass(frozen=True)
class CanonicalSpectrumBundle:
    meta: ArtifactMeta
    spectra: tuple[CanonicalSpectrumArtifact, ...] = ()
    bands: tuple[BandDefinition, ...] = ()


@dataclass(frozen=True)
class BandSignalBundle:
    meta: ArtifactMeta
    signals: tuple[tuple[BandKey, Tensor], ...] = ()
