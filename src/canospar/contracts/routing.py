"""M7 route contract objects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .base import ArtifactMeta, _freeze_mapping, require_non_empty_text


@dataclass(frozen=True)
class RoutingSpec:
    backend: str
    top_k: int
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        if isinstance(self.top_k, bool) or self.top_k <= 0:
            raise ValueError("top_k must be a positive integer")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class RouteCandidateGraph:
    meta: ArtifactMeta
    edges: tuple[object, ...] = ()


@dataclass(frozen=True)
class RouteScoreGraph:
    meta: ArtifactMeta
    scores: tuple[object, ...] = ()


@dataclass(frozen=True)
class RouteGraph:
    meta: ArtifactMeta
    edges: tuple[object, ...] = ()


@dataclass(frozen=True)
class RoutedTokenBundle:
    meta: ArtifactMeta
    values: tuple[object, ...] = ()


@dataclass(frozen=True)
class RoutingBundle:
    meta: ArtifactMeta
    candidates: RouteCandidateGraph | None = None
    scores: RouteScoreGraph | None = None
    routes: RouteGraph | None = None
    routed_tokens: RoutedTokenBundle | None = None
