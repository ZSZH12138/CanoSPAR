"""M2 and spectral-coordinate contract objects."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from types import MappingProxyType

import torch

from .base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    GraphKey,
    JsonValue,
    ScienceContext,
    Tensor,
    _freeze_mapping,
    build_reproduction_key,
    build_science_key,
    require_non_empty_text,
)
from .errors import ContractViolation
from .execution import CanonicalStatus, CompletionReceipt


def _canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tensor_content_hash(tensor: torch.Tensor) -> str:
    contiguous = tensor.detach().cpu().contiguous()
    digest = hashlib.sha256()
    digest.update(
        _canonical_json_hash(
            {
                "dtype": str(contiguous.dtype),
                "shape": tuple(int(value) for value in contiguous.shape),
            }
        ).encode("ascii")
    )
    digest.update(contiguous.numpy().tobytes(order="C"))
    return digest.hexdigest()


@dataclass(frozen=True)
class M2Spec:
    backend: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.backend, "backend")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))
        try:
            json.dumps(dict(self.parameters), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ContractViolation("parameters must be finite JSON serializable") from error


@dataclass(frozen=True)
class CanonicalCoordinateSpec:
    method: str
    parameters: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_text(self.method, "method")
        object.__setattr__(self, "parameters", _freeze_mapping(self.parameters, "parameters"))


@dataclass(frozen=True)
class LaplacianArtifact:
    meta: ArtifactMeta
    graph_key: GraphKey
    payload: Tensor

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        if not isinstance(self.graph_key, GraphKey):
            raise ContractViolation("graph_key must be GraphKey")
        if not isinstance(self.payload, torch.Tensor):
            raise ContractViolation("payload must be a torch.Tensor")
        if self.payload.dim() != 2 or self.payload.size(0) != self.payload.size(1):
            raise ContractViolation("Laplacian payload must be square")
        if not self.payload.is_floating_point() or not bool(torch.isfinite(self.payload).all()):
            raise ContractViolation("Laplacian payload must be finite floating-point")
        if not torch.allclose(self.payload, self.payload.T, atol=1e-12, rtol=1e-12):
            raise ContractViolation("Laplacian payload must be symmetric")
        object.__setattr__(self, "payload", self.payload.detach().clone())


@dataclass(frozen=True)
class SpectrumArtifact:
    meta: ArtifactMeta
    graph_key: GraphKey
    eigenvalues: Tensor

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        if not isinstance(self.graph_key, GraphKey):
            raise ContractViolation("graph_key must be GraphKey")
        if not isinstance(self.eigenvalues, torch.Tensor):
            raise ContractViolation("eigenvalues must be a torch.Tensor")
        if self.eigenvalues.dim() != 1 or not self.eigenvalues.is_floating_point():
            raise ContractViolation("eigenvalues must be a one-dimensional floating tensor")
        if not bool(torch.isfinite(self.eigenvalues).all()):
            raise ContractViolation("eigenvalues must be finite")
        if self.eigenvalues.numel() > 1 and bool(
            (self.eigenvalues[:-1] > self.eigenvalues[1:]).any()
        ):
            raise ContractViolation("eigenvalues must be ascending")
        object.__setattr__(self, "eigenvalues", self.eigenvalues.detach().clone())


@dataclass(frozen=True)
class SpectralStatistics:
    meta: ArtifactMeta
    graph_key: GraphKey
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        if not isinstance(self.graph_key, GraphKey):
            raise ContractViolation("graph_key must be GraphKey")
        for key, value in self.values.items():
            if (
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, int | float)
            ):
                raise ContractViolation("statistics values must be finite numeric values")
            if not math.isfinite(float(value)):
                raise ContractViolation("statistics values must be finite numeric values")
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class NormalizedQCArtifact:
    meta: ArtifactMeta
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        for key, value in self.values.items():
            if (
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, int | float)
            ):
                raise ContractViolation("normalized QC values must be finite numeric values")
            if not math.isfinite(float(value)):
                raise ContractViolation("normalized QC values must be finite numeric values")
        object.__setattr__(self, "values", _freeze_mapping(self.values, "values"))


@dataclass(frozen=True)
class SpectralBundle:
    meta: ArtifactMeta
    laplacians: tuple[LaplacianArtifact, ...] = ()
    spectra: tuple[SpectrumArtifact, ...] = ()
    statistics: tuple[SpectralStatistics, ...] = ()
    normalized_qc: NormalizedQCArtifact | None = None
    _validated_receipt: CompletionReceipt | None = field(default=None, repr=False, compare=False)
    _validated_fingerprint: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        laplacians = tuple(self.laplacians)
        spectra = tuple(self.spectra)
        statistics = tuple(self.statistics)
        if not (len(laplacians) == len(spectra) == len(statistics)):
            raise ContractViolation("laplacians, spectra, and statistics lengths must match")
        if not laplacians:
            raise ContractViolation("SpectralBundle requires at least one graph")
        if any(not isinstance(item, LaplacianArtifact) for item in laplacians):
            raise ContractViolation("laplacians must contain LaplacianArtifact instances")
        if any(not isinstance(item, SpectrumArtifact) for item in spectra):
            raise ContractViolation("spectra must contain SpectrumArtifact instances")
        if any(not isinstance(item, SpectralStatistics) for item in statistics):
            raise ContractViolation("statistics must contain SpectralStatistics instances")
        if self.normalized_qc is not None and not isinstance(
            self.normalized_qc, NormalizedQCArtifact
        ):
            raise ContractViolation("normalized_qc must be NormalizedQCArtifact or None")
        if self._validated_receipt is not None and not isinstance(
            self._validated_receipt, CompletionReceipt
        ):
            raise ContractViolation("_validated_receipt must be CompletionReceipt or None")
        if self._validated_fingerprint is not None and not isinstance(
            self._validated_fingerprint, str
        ):
            raise ContractViolation("_validated_fingerprint must be a string or None")
        if (
            spectra
            and laplacians
            and tuple(item.graph_key for item in spectra)
            != tuple(item.graph_key for item in laplacians)
        ):
            raise ContractViolation("laplacian and spectrum GraphKey ordering must match")
        if (
            statistics
            and spectra
            and tuple(item.graph_key for item in statistics)
            != tuple(item.graph_key for item in spectra)
        ):
            raise ContractViolation("spectrum and statistics GraphKey ordering must match")
        object.__setattr__(self, "laplacians", laplacians)
        object.__setattr__(self, "spectra", spectra)
        object.__setattr__(self, "statistics", statistics)

    @staticmethod
    def _meta_identity(meta: ArtifactMeta) -> dict[str, object]:
        return asdict(meta)

    @staticmethod
    def _graph_key_identity(graph_key: GraphKey) -> tuple[str, str, str, str]:
        return graph_key.subject, graph_key.visit, graph_key.modality, graph_key.relation

    def _validation_fingerprint(self) -> str:
        return _canonical_json_hash(
            {
                "bundle": self._meta_identity(self.meta),
                "laplacians": [
                    {
                        "meta": self._meta_identity(item.meta),
                        "graph_key": self._graph_key_identity(item.graph_key),
                    }
                    for item in self.laplacians
                ],
                "spectra": [
                    {
                        "meta": self._meta_identity(item.meta),
                        "graph_key": self._graph_key_identity(item.graph_key),
                    }
                    for item in self.spectra
                ],
                "statistics": [
                    {
                        "meta": self._meta_identity(item.meta),
                        "graph_key": self._graph_key_identity(item.graph_key),
                    }
                    for item in self.statistics
                ],
                "normalized_qc": (
                    self._meta_identity(self.normalized_qc.meta)
                    if self.normalized_qc is not None
                    else None
                ),
            }
        )

    def _identity_inputs(self) -> tuple[ScienceContext, tuple[str, ...]] | None:
        if not self.meta.input_content_hashes or len(self.meta.input_content_hashes) < 3:
            return None
        science_spec_hashes = [
            content_hash
            for artifact_id, content_hash in zip(
                self.meta.input_artifact_ids,
                self.meta.input_content_hashes,
                strict=True,
            )
            if artifact_id.startswith("science-spec:")
        ]
        if len(science_spec_hashes) != 1:
            return None
        graph_hashes: list[str] = []
        for laplacian in self.laplacians:
            if len(laplacian.meta.input_content_hashes) < 2:
                return None
            graph_hashes.append(laplacian.meta.input_content_hashes[1])
        state_hashes = [
            content_hash
            for artifact_id, content_hash in zip(
                self.meta.input_artifact_ids,
                self.meta.input_content_hashes,
                strict=True,
            )
            if artifact_id.startswith("qc-state:")
        ]
        if len(state_hashes) > 1:
            return None
        context = ScienceContext(
            science_contract_version=self.meta.science_contract_version,
            science_config_hash=self.meta.science_config_hash,
            dataset_manifest_hash=self.meta.dataset_manifest_hash,
            split_id=self.meta.split_id,
            random_seed=self.meta.random_seed,
        )
        inputs = [
            self.meta.input_content_hashes[0],
            science_spec_hashes[0],
            *graph_hashes,
            *state_hashes,
        ]
        return context, tuple(inputs)

    @property
    def science_key(self) -> str:
        identity_inputs = self._identity_inputs()
        if identity_inputs is None:
            return ""
        context, inputs = identity_inputs
        return build_science_key(context, inputs, self.meta.module_contract_version)

    @property
    def reproduction_key(self) -> str:
        if not self.science_key:
            return ""
        return build_reproduction_key(
            self.science_key,
            self.meta.implementation_hash,
            self.meta.numerics_profile_hash,
        )

    def _content_hashes_are_consistent(self) -> bool:
        if any(
            item.meta.content_sha256 != _tensor_content_hash(item.payload)
            for item in self.laplacians
        ):
            return False
        if any(
            item.meta.content_sha256 != _tensor_content_hash(item.eigenvalues)
            for item in self.spectra
        ):
            return False
        if any(
            item.meta.content_sha256 != _canonical_json_hash(dict(item.values))
            for item in self.statistics
        ):
            return False
        if self.normalized_qc is not None and (
            self.normalized_qc.meta.content_sha256
            != _canonical_json_hash(dict(self.normalized_qc.values))
        ):
            return False
        expected_bundle_hash = _canonical_json_hash(
            {
                "laplacians": [item.meta.content_sha256 for item in self.laplacians],
                "spectra": [item.meta.content_sha256 for item in self.spectra],
                "statistics": [item.meta.content_sha256 for item in self.statistics],
                "normalized_qc": (
                    self.normalized_qc.meta.content_sha256
                    if self.normalized_qc is not None
                    else None
                ),
            }
        )
        return self.meta.content_sha256 == expected_bundle_hash

    @property
    def receipt(self) -> CompletionReceipt | None:
        receipt = self._validated_receipt
        if receipt is None or self._validated_fingerprint is None:
            return None
        if self._validated_fingerprint != self._validation_fingerprint():
            return None
        if (
            not self.science_key
            or not self.reproduction_key
            or not self._content_hashes_are_consistent()
            or receipt.module_id != "M2"
            or receipt.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION
            or receipt.canonical_status != CanonicalStatus.PASS
            or receipt.validator_status != "PASS"
            or receipt.input_artifact_ids != self.meta.input_artifact_ids
            or receipt.input_hashes != self.meta.input_content_hashes
            or receipt.science_key != self.science_key
            or receipt.reproduction_key != self.reproduction_key
            or receipt.output_artifact_ids != (self.meta.artifact_id,)
            or receipt.output_hashes != (self.meta.content_sha256,)
        ):
            return None
        return receipt

    @property
    def evidence(self) -> Mapping[str, str]:
        if not self.science_key:
            return {}
        return MappingProxyType(
            {
                "verification_scope": "SYNTHETIC_ANALYTIC_ONLY",
                "scientific_verification_status": "NOT_VERIFIED",
                "m3_executed": "false",
                "m4_executed": "false",
            }
        )
