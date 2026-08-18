"""M1 multi-graph construction API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from canospar.contracts.base import (
    JsonValue,
    MultiGraphArtifact,
    ScienceContext,
    _freeze_mapping,
    require_non_empty_text,
)
from canospar.contracts.imaging import ROIAlignedSample
from canospar.data.contracts import GraphData
from canospar.validators.base import ValidationReport

from ._contract_only import contract_only


@dataclass(frozen=True)
class GraphConstructionSpec:
    backend: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


class M1Backend(Protocol):
    def build_multigraph_sample(
        self,
        sample: ROIAlignedSample,
        spec: GraphConstructionSpec,
        context: ScienceContext,
    ) -> MultiGraphArtifact: ...


def build_multigraph_sample(
    sample: ROIAlignedSample,
    spec: GraphConstructionSpec,
    context: ScienceContext,
) -> MultiGraphArtifact:
    del sample, spec, context
    raise contract_only("M1")


def validate_graph(graph: GraphData) -> ValidationReport:
    del graph
    raise contract_only("M1")
