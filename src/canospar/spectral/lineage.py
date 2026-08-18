"""Stable M2 numerical identity and artifact metadata helpers."""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Mapping, Sequence
from typing import Any, cast

import numpy as np
import torch

from canospar.contracts.base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    GraphKey,
    ScienceContext,
    _digest_parts,
    require_non_empty_text,
)
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec
from canospar.data.contracts import BrainMultiGraphSample, GraphData
from canospar.runtime.numerics import NumericsProfile

M2_IMPLEMENTATION_HASH = hashlib.sha256(b"canospar-m2-implementation-v1.1.3").hexdigest()
DEFAULT_CREATED_AT_UTC = "1970-01-01T00:00:00Z"
_NUMERICAL_SPEC_KEYS = frozenset(
    {
        "solver_tolerance",
        "zero_tolerance",
        "tie_tolerance",
        "dirichlet_epsilon",
        "eigensolver_backend",
    }
)


def graph_key_sort_key(key: GraphKey) -> tuple[str, str, str, str]:
    return key.subject, key.visit, key.modality, key.relation


def graph_key_value(key: GraphKey) -> tuple[str, str, str, str]:
    return key.subject, key.visit, key.modality, key.relation


def canonical_json_hash(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ContractViolation("value must be finite JSON serializable") from error
    return hashlib.sha256(encoded).hexdigest()


def tensor_content_hash(tensor: torch.Tensor) -> str:
    if not isinstance(tensor, torch.Tensor):
        raise ContractViolation("tensor must be a torch.Tensor")
    contiguous = tensor.detach().cpu().contiguous()
    payload = {
        "dtype": str(contiguous.dtype),
        "shape": tuple(int(value) for value in contiguous.shape),
    }
    digest = hashlib.sha256()
    digest.update(canonical_json_hash(payload).encode("ascii"))
    digest.update(contiguous.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _graph_content_record(graph: GraphData) -> dict[str, object]:
    graph.validate()
    return {
        "x": tensor_content_hash(graph.x),
        "edge_index": tensor_content_hash(graph.edge_index),
        "edge_weight": tensor_content_hash(graph.edge_weight),
        "num_nodes": graph.num_nodes,
        "modality": graph.modality,
        "relation": graph.relation,
        "graph_qc": dict(graph.graph_qc),
        "construction_hash": graph.construction_hash,
    }


def multigraph_content_hash(
    sample: BrainMultiGraphSample,
    atlas_id: str,
    atlas_hash: str,
    roi_table_hash: str,
    node_order_hash: str,
) -> str:
    """Hash the complete M1 MultiGraphArtifact scientific content deterministically."""
    if not isinstance(sample, BrainMultiGraphSample):
        raise ContractViolation("sample must be BrainMultiGraphSample")
    sample.validate()
    for name, value in (
        ("atlas_id", atlas_id),
        ("atlas_hash", atlas_hash),
        ("roi_table_hash", roi_table_hash),
        ("node_order_hash", node_order_hash),
    ):
        require_non_empty_text(value, name)

    graphs: dict[str, dict[str, dict[str, object]]] = {}
    for modality in sorted(sample.graphs):
        relations = sample.graphs[modality]
        graphs[modality] = {
            relation: _graph_content_record(relations[relation]) for relation in sorted(relations)
        }
    return canonical_json_hash(
        {
            "subject_id": sample.subject_id,
            "visit_id": sample.visit_id,
            "group_id": sample.group_id,
            "site_id": sample.site_id,
            "graphs": graphs,
            "modality_available": dict(sorted(sample.modality_available.items())),
            "qc_vector": dict(sorted(sample.qc_vector.items())),
            "target": float(sample.target),
            "covariates": dict(sorted(sample.covariates.items())),
            "cohort_metadata": dict(sorted(sample.cohort_metadata.items())),
            "atlas_id": atlas_id,
            "atlas_hash": atlas_hash,
            "roi_table_hash": roi_table_hash,
            "node_order_hash": node_order_hash,
        }
    )


def spec_content_hash(spec: M2Spec) -> str:
    if not isinstance(spec, M2Spec):
        raise ContractViolation("spec must be M2Spec")
    return canonical_json_hash({"backend": spec.backend, "parameters": dict(spec.parameters)})


def science_spec_content_hash(spec: M2Spec) -> str:
    """Hash scientific M2 configuration while excluding numerical identity knobs."""
    if not isinstance(spec, M2Spec):
        raise ContractViolation("spec must be M2Spec")
    scientific_parameters = {
        key: value for key, value in spec.parameters.items() if key not in _NUMERICAL_SPEC_KEYS
    }
    return canonical_json_hash({"parameters": scientific_parameters})


def _finite_float(parameters: Mapping[str, object], name: str, default: float) -> float:
    value = parameters.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not np.isfinite(value):
        raise ContractViolation(f"{name} must be a finite number")
    return float(value)


def solver_tolerance(spec: M2Spec) -> float:
    value = _finite_float(spec.parameters, "solver_tolerance", 1e-8)
    if value <= 0:
        raise ContractViolation("solver_tolerance must be positive")
    return value


def zero_tolerance(spec: M2Spec) -> float:
    value = _finite_float(spec.parameters, "zero_tolerance", max(1e-8, solver_tolerance(spec) * 10))
    if value <= 0:
        raise ContractViolation("zero_tolerance must be positive")
    return value


def tie_tolerance(spec: M2Spec) -> float:
    value = _finite_float(spec.parameters, "tie_tolerance", max(1e-8, solver_tolerance(spec) * 10))
    if value <= 0:
        raise ContractViolation("tie_tolerance must be positive")
    return value


def dirichlet_epsilon(spec: M2Spec) -> float:
    value = _finite_float(spec.parameters, "dirichlet_epsilon", 1e-12)
    if value <= 0:
        raise ContractViolation("dirichlet_epsilon must be positive")
    return value


def numerics_profile(spec: M2Spec) -> NumericsProfile:
    if spec.backend not in {"numpy", "cpu"}:
        raise ContractViolation("M2 CPU backend must be declared as 'numpy' or 'cpu'")
    backend = spec.parameters.get("eigensolver_backend", "numpy.linalg.eigh")
    if not isinstance(backend, str) or not backend.strip():
        raise ContractViolation("eigensolver_backend must be a non-empty string")
    if backend != "numpy.linalg.eigh":
        raise ContractViolation("only numpy.linalg.eigh is supported by the CPU M2 backend")
    return NumericsProfile(
        python_version=platform.python_version(),
        numpy_version=np.__version__,
        torch_version=torch.__version__.split("+")[0],
        dtype="float64",
        precision_policy="strict-float64",
        deterministic_algorithms=True,
        linear_algebra_backend="numpy",
        eigensolver_backend=backend,
        solver_tolerance=solver_tolerance(spec),
        zero_tolerance=zero_tolerance(spec),
        tie_tolerance=tie_tolerance(spec),
        dirichlet_epsilon=dirichlet_epsilon(spec),
    )


def _artifact_id(
    artifact_type: str,
    content_sha256: str,
    graph_key: GraphKey | None,
    input_artifact_ids: Sequence[str],
) -> str:
    return _digest_parts(
        (
            artifact_type,
            content_sha256,
            graph_key_value(graph_key) if graph_key is not None else None,
            tuple(input_artifact_ids),
        )
    )


def make_meta(
    *,
    artifact_type: str,
    context: ScienceContext,
    content_sha256: str,
    input_artifact_ids: Sequence[str],
    input_content_hashes: Sequence[str],
    numerics_profile_hash: str,
    graph_key: GraphKey | None = None,
    created_at_utc: str = DEFAULT_CREATED_AT_UTC,
) -> ArtifactMeta:
    require_non_empty_text(content_sha256, "content_sha256")
    artifact_ids = tuple(
        require_non_empty_text(value, "input_artifact_id") for value in input_artifact_ids
    )
    content_hashes = tuple(
        require_non_empty_text(value, "input_content_hash") for value in input_content_hashes
    )
    if len(artifact_ids) != len(content_hashes):
        raise ContractViolation("input artifact IDs and content hashes must have equal lengths")
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type=artifact_type,
        artifact_id=_artifact_id(artifact_type, content_sha256, graph_key, artifact_ids),
        producer_module="M2",
        module_contract_version=MODULE_PROTOCOL_SPEC_VERSION,
        science_contract_version=context.science_contract_version,
        input_artifact_ids=artifact_ids,
        input_content_hashes=content_hashes,
        science_config_hash=context.science_config_hash,
        dataset_manifest_hash=context.dataset_manifest_hash,
        split_id=context.split_id,
        random_seed=context.random_seed,
        content_sha256=content_sha256,
        implementation_hash=M2_IMPLEMENTATION_HASH,
        numerics_profile_hash=numerics_profile_hash,
        created_at_utc=created_at_utc,
    )


def fixed_graph_key(graph_modality: str, graph_relation: str) -> GraphKey:
    return GraphKey("synthetic-subject", "synthetic-visit", graph_modality, graph_relation)


def ensure_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractViolation(f"{name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{name} keys must be strings")
    return cast(Mapping[str, Any], value)
