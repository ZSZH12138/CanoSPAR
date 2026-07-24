"""Validated, frozen data contracts with defensive copies of caller-owned state."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from numbers import Real
from types import MappingProxyType
from typing import Any

import torch
from torch_geometric.data import Data

_VALID_MODALITIES = frozenset({"smri", "dmri", "fmri"})
_REQUIRED_COHORT_METADATA = frozenset(
    {
        "cohort_source",
        "unrelated_list_version",
        "kinship_control_method",
    }
)


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_json_mapping(value: object, field_name: str, *, allow_empty: bool) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must not be empty")
    if any(not isinstance(key, str) for key in value):
        raise ValueError(f"{field_name} keys must be strings")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be JSON serializable") from error


def _validate_finite_number(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite non-boolean number")


def _validate_tensor(value: object, field_name: str) -> None:
    if not isinstance(value, torch.Tensor):
        raise ValueError(f"{field_name} must be a torch.Tensor")


def _validate_covariates(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("covariates must be a mapping")
    for name, covariate in value.items():
        if not isinstance(name, str):
            raise ValueError("covariates keys must be strings")
        if isinstance(covariate, bool) or not isinstance(covariate, float | str):
            raise ValueError("covariates values must be floats or strings")
        if isinstance(covariate, float) and not math.isfinite(covariate):
            raise ValueError("covariates float values must be finite")


def _validate_cohort_metadata(value: object) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("cohort_metadata must be a mapping")
    missing = sorted(_REQUIRED_COHORT_METADATA.difference(value))
    if missing:
        raise ValueError(f"cohort_metadata is missing required fields: {missing}")
    for name, metadata_value in value.items():
        _require_non_empty_string(name, "cohort_metadata key")
        _require_non_empty_string(metadata_value, f"cohort_metadata[{name!r}]")


@dataclass(frozen=True)
class GraphData:
    """A single graph with tensor and provenance metadata."""

    x: torch.Tensor
    edge_index: torch.Tensor
    edge_weight: torch.Tensor
    num_nodes: int
    modality: str
    relation: str
    graph_qc: Mapping[str, Any]
    construction_hash: str

    def __post_init__(self) -> None:
        """Detach tensors and metadata from caller-owned mutable objects."""
        if isinstance(self.x, torch.Tensor):
            object.__setattr__(self, "x", self.x.clone())
        if isinstance(self.edge_index, torch.Tensor):
            object.__setattr__(self, "edge_index", self.edge_index.clone())
        if isinstance(self.edge_weight, torch.Tensor):
            object.__setattr__(self, "edge_weight", self.edge_weight.clone())
        if isinstance(self.graph_qc, Mapping):
            object.__setattr__(self, "graph_qc", deepcopy(dict(self.graph_qc)))

    def validate(self) -> None:
        """Validate graph shape, values, metadata, and index bounds without mutation."""
        _validate_tensor(self.x, "x")
        _validate_tensor(self.edge_index, "edge_index")
        _validate_tensor(self.edge_weight, "edge_weight")
        if self.x.dim() != 2:
            raise ValueError("x must have shape [num_nodes, num_features]")
        if not self.x.is_floating_point():
            raise ValueError("x must use a floating-point dtype")
        if isinstance(self.num_nodes, bool) or not isinstance(self.num_nodes, int):
            raise ValueError("num_nodes must be an integer")
        if self.num_nodes <= 0:
            raise ValueError("num_nodes must be positive")
        if self.x.size(0) != self.num_nodes:
            raise ValueError("x row count must equal num_nodes")
        if not bool(torch.isfinite(self.x).all()):
            raise ValueError("x must contain only finite values")

        if self.edge_index.dim() != 2 or self.edge_index.size(0) != 2:
            raise ValueError("edge_index must have shape [2, num_edges]")
        if self.edge_index.dtype != torch.long:
            raise ValueError("edge_index must use torch.long dtype")
        if self.edge_weight.dim() != 1:
            raise ValueError("edge_weight must have shape [num_edges]")
        if not self.edge_weight.is_floating_point():
            raise ValueError("edge_weight must use a floating-point dtype")
        if self.edge_weight.size(0) != self.edge_index.size(1):
            raise ValueError("edge_weight length must equal the number of edges")
        if not bool(torch.isfinite(self.edge_weight).all()):
            raise ValueError("edge_weight must contain only finite values")
        if self.edge_index.numel() and (
            int(self.edge_index.min()) < 0 or int(self.edge_index.max()) >= self.num_nodes
        ):
            raise ValueError("edge_index contains an out-of-range node index")

        _require_non_empty_string(self.modality, "modality")
        _require_non_empty_string(self.relation, "relation")
        _require_non_empty_string(self.construction_hash, "construction_hash")
        _validate_json_mapping(self.graph_qc, "graph_qc", allow_empty=False)

    def to_pyg_data(self) -> Data:
        """Validate and convert this contract to a real PyG ``Data`` object."""
        self.validate()
        return Data(
            x=self.x.clone(),
            edge_index=self.edge_index.clone(),
            edge_weight=self.edge_weight.clone(),
            num_nodes=self.num_nodes,
            modality=self.modality,
            relation=self.relation,
            graph_qc=deepcopy(dict(self.graph_qc)),
            construction_hash=self.construction_hash,
        )


def _copy_graph_mappings(graphs: object) -> object:
    if not isinstance(graphs, Mapping):
        return graphs
    return {
        modality: (
            {
                relation: _copy_graph(graph) if isinstance(graph, GraphData) else graph
                for relation, graph in relations.items()
            }
            if isinstance(relations, Mapping)
            else relations
        )
        for modality, relations in graphs.items()
    }


def _copy_graph(graph: GraphData) -> GraphData:
    return GraphData(
        x=graph.x,
        edge_index=graph.edge_index,
        edge_weight=graph.edge_weight,
        num_nodes=graph.num_nodes,
        modality=graph.modality,
        relation=graph.relation,
        graph_qc=graph.graph_qc,
        construction_hash=graph.construction_hash,
    )


@dataclass(frozen=True)
class BrainMultiGraphSample:
    """A subject visit containing the available structural, diffusion, and fMRI graphs."""

    subject_id: str
    visit_id: str
    group_id: str
    site_id: str
    graphs: Mapping[str, Mapping[str, GraphData]]
    modality_available: Mapping[str, bool]
    qc_vector: Mapping[str, float]
    target: float | int
    covariates: Mapping[str, float | str]
    cohort_metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        """Detach nested graph mappings and scalar metadata from caller-owned mappings."""
        object.__setattr__(self, "graphs", _copy_graph_mappings(self.graphs))
        if isinstance(self.modality_available, Mapping):
            object.__setattr__(self, "modality_available", dict(self.modality_available))
        if isinstance(self.qc_vector, Mapping):
            object.__setattr__(self, "qc_vector", dict(self.qc_vector))
        if isinstance(self.covariates, Mapping):
            object.__setattr__(self, "covariates", dict(self.covariates))
        if isinstance(self.cohort_metadata, Mapping):
            object.__setattr__(
                self,
                "cohort_metadata",
                MappingProxyType(dict(self.cohort_metadata)),
            )

    def validate(self) -> None:
        """Validate sample identifiers, graph/modality consistency, and scalar metadata."""
        for field_name in ("subject_id", "visit_id", "group_id", "site_id"):
            _require_non_empty_string(getattr(self, field_name), field_name)

        if not isinstance(self.graphs, Mapping):
            raise ValueError("graphs must be a mapping")
        if not set(self.graphs).issubset(_VALID_MODALITIES):
            raise ValueError("graphs contains an unsupported modality")

        if not isinstance(self.modality_available, Mapping):
            raise ValueError("modality_available must be a mapping")
        if set(self.modality_available) != _VALID_MODALITIES:
            raise ValueError("modality_available must contain exactly the supported modalities")
        if any(type(available) is not bool for available in self.modality_available.values()):
            raise ValueError("modality_available values must be bool")

        for modality in _VALID_MODALITIES:
            relations = self.graphs.get(modality)
            has_graphs = relations is not None and bool(relations)
            if self.modality_available[modality] != has_graphs:
                raise ValueError("modality_available must agree bidirectionally with graphs")
            if relations is None:
                continue
            if not isinstance(relations, Mapping) or not relations:
                raise ValueError("each available modality must contain graph relations")
            for relation_name, graph in relations.items():
                _require_non_empty_string(relation_name, "relation name")
                if not isinstance(graph, GraphData):
                    raise ValueError("graph relations must contain GraphData instances")
                if graph.modality != modality:
                    raise ValueError("inner graph modality must match its outer modality")
                if graph.relation != relation_name:
                    raise ValueError("inner graph relation must match its outer relation")
                graph.validate()

        if not isinstance(self.qc_vector, Mapping):
            raise ValueError("qc_vector must be a mapping")
        for qc_name, qc_value in self.qc_vector.items():
            _require_non_empty_string(qc_name, "qc_vector key")
            _validate_finite_number(qc_value, f"qc_vector[{qc_name!r}]")
        _validate_finite_number(self.target, "target")
        _validate_covariates(self.covariates)
        _validate_cohort_metadata(self.cohort_metadata)
