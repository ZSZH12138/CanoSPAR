"""Stable M3 coordinate, band, and artifact lineage helpers."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence

import torch

from canospar.contracts.bands import BandDefinition, BandSpec, CanonicalSpectrumArtifact
from canospar.contracts.base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    GraphKey,
    ScienceContext,
    Tensor,
    _digest_parts,
    require_non_empty_text,
)
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import CanonicalCoordinateSpec
from canospar.spectral.lineage import canonical_json_hash, graph_key_value, tensor_content_hash

M3_IMPLEMENTATION_HASH = hashlib.sha256(b"canospar-m3-implementation-v1.1.0").hexdigest()
DEFAULT_CREATED_AT_UTC = "1970-01-01T00:00:00Z"
M3_COORDINATE_METHOD = "empirical_mid_cdf"


def coordinate_spec_content_hash(spec: CanonicalCoordinateSpec) -> str:
    if not isinstance(spec, CanonicalCoordinateSpec):
        raise ContractViolation("coordinate_spec must be CanonicalCoordinateSpec")
    return canonical_json_hash({"method": spec.method, "parameters": dict(spec.parameters)})


def band_spec_content_hash(spec: BandSpec) -> str:
    if not isinstance(spec, BandSpec):
        raise ContractViolation("band_spec must be BandSpec")
    return canonical_json_hash({"band_count": spec.band_count, "tie_policy": spec.tie_policy})


def canonical_spectrum_content_hash(u_coordinate: Tensor, lambda_coordinate: Tensor) -> str:
    return canonical_json_hash(
        {
            "u_coordinate": tensor_content_hash(u_coordinate),
            "lambda_coordinate": tensor_content_hash(lambda_coordinate),
        }
    )


def canonical_bundle_content_hash(
    spectra: Sequence[CanonicalSpectrumArtifact], bands: Sequence[BandDefinition]
) -> str:
    return canonical_json_hash(
        {
            "spectra": [item.meta.content_sha256 for item in spectra],
            "bands": [
                {
                    "band_id": item.band_id,
                    "lower_mass": item.lower_mass,
                    "upper_mass": item.upper_mass,
                    "lower_lambda": item.lower_lambda,
                    "upper_lambda": item.upper_lambda,
                }
                for item in bands
            ],
        }
    )


def validate_coordinate_spec(spec: CanonicalCoordinateSpec) -> tuple[float, float, str]:
    if not isinstance(spec, CanonicalCoordinateSpec):
        raise ContractViolation("coordinate_spec must be CanonicalCoordinateSpec")
    if spec.method != M3_COORDINATE_METHOD:
        raise ContractViolation(f"M3 coordinate method must be {M3_COORDINATE_METHOD}")
    parameters: Mapping[str, object] = spec.parameters
    missing = {"tie_atol", "tie_rtol", "empty_band_policy"}.difference(parameters)
    if missing:
        raise ContractViolation(
            "coordinate_spec.parameters must explicitly declare " + ", ".join(sorted(missing))
        )
    tie_atol = _nonnegative_float(parameters["tie_atol"], "tie_atol")
    tie_rtol = _nonnegative_float(parameters["tie_rtol"], "tie_rtol")
    empty_policy = parameters["empty_band_policy"]
    if empty_policy not in {"fail", "allow_with_warning"}:
        raise ContractViolation("empty_band_policy must be fail or allow_with_warning")
    return tie_atol, tie_rtol, str(empty_policy)


def _nonnegative_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{name} must be a finite non-negative number")
    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise ContractViolation(f"{name} must be a finite non-negative number")
    return converted


def validate_band_spec(spec: BandSpec) -> None:
    if not isinstance(spec, BandSpec):
        raise ContractViolation("band_spec must be BandSpec")
    if isinstance(spec.band_count, bool) or not isinstance(spec.band_count, int):
        raise ContractViolation("band_count must be a positive integer")
    if spec.band_count <= 0:
        raise ContractViolation("band_count must be a positive integer")
    if spec.tie_policy != "keep_ties_intact":
        raise ContractViolation("tie_policy must be keep_ties_intact")


def empirical_mid_rank_coordinate(
    eigenvalues: torch.Tensor,
    tie_atol: float,
    tie_rtol: float,
) -> torch.Tensor:
    if not isinstance(eigenvalues, torch.Tensor):
        raise ContractViolation("eigenvalues must be a torch.Tensor")
    if eigenvalues.dim() != 1 or eigenvalues.numel() == 0:
        raise ContractViolation("eigenvalues must be a non-empty one-dimensional tensor")
    if not eigenvalues.is_floating_point() or not bool(torch.isfinite(eigenvalues).all()):
        raise ContractViolation("eigenvalues must be finite floating-point values")
    if eigenvalues.numel() > 1 and bool((eigenvalues[:-1] > eigenvalues[1:]).any()):
        raise ContractViolation("eigenvalues must be sorted in ascending order")
    output = torch.empty_like(eigenvalues)
    count = eigenvalues.numel()
    start = 0
    while start < count:
        end = start
        while end + 1 < count and bool(
            torch.isclose(
                eigenvalues[end],
                eigenvalues[end + 1],
                atol=tie_atol,
                rtol=tie_rtol,
            )
        ):
            end += 1
        mid_rank = (start + end + 1) / (2.0 * count)
        output[start : end + 1] = mid_rank
        start = end + 1
    return output


def m3_artifact_id(
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


def make_m3_meta(
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
        artifact_id=m3_artifact_id(artifact_type, content_sha256, graph_key, artifact_ids),
        producer_module="M3",
        module_contract_version=MODULE_PROTOCOL_SPEC_VERSION,
        science_contract_version=context.science_contract_version,
        input_artifact_ids=artifact_ids,
        input_content_hashes=content_hashes,
        science_config_hash=context.science_config_hash,
        dataset_manifest_hash=context.dataset_manifest_hash,
        split_id=context.split_id,
        random_seed=context.random_seed,
        content_sha256=content_sha256,
        implementation_hash=M3_IMPLEMENTATION_HASH,
        numerics_profile_hash=numerics_profile_hash,
        created_at_utc=created_at_utc,
    )
