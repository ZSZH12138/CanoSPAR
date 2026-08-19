"""M3/M4 band and filter contract objects."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

import torch

from canospar.validators.base import ValidationIssue

from .base import (
    MODULE_PROTOCOL_SPEC_VERSION,
    ArtifactMeta,
    BandKey,
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
class BandSpec:
    band_count: int
    tie_policy: str = "keep_ties_intact"

    def __post_init__(self) -> None:
        if (
            isinstance(self.band_count, bool)
            or not isinstance(self.band_count, int)
            or self.band_count <= 0
        ):
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
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        if not isinstance(self.graph_key, GraphKey):
            raise ContractViolation("graph_key must be GraphKey")
        require_non_empty_text(self.spectrum_artifact_id, "spectrum_artifact_id")
        for field_name, tensor in (
            ("u_coordinate", self.u_coordinate),
            ("lambda_coordinate", self.lambda_coordinate),
        ):
            if not isinstance(tensor, torch.Tensor) or tensor.dim() != 1:
                raise ContractViolation(f"{field_name} must be a one-dimensional tensor")
            if not tensor.is_floating_point() or not bool(torch.isfinite(tensor).all()):
                raise ContractViolation(f"{field_name} must be finite floating-point")
        if self.u_coordinate.numel() == 0:
            raise ContractViolation("canonical coordinates must not be empty")
        if self.u_coordinate.numel() != self.lambda_coordinate.numel():
            raise ContractViolation("canonical coordinates must have equal lengths")
        if not bool((self.u_coordinate > 0.0).all()) or not bool((self.u_coordinate < 1.0).all()):
            raise ContractViolation("u_coordinate values must be in (0, 1)")
        if self.u_coordinate.numel() > 1 and not bool(
            (self.u_coordinate[:-1] <= self.u_coordinate[1:]).all()
        ):
            raise ContractViolation("u_coordinate must be nondecreasing")
        if self.lambda_coordinate.numel() > 1 and not bool(
            (self.lambda_coordinate[:-1] <= self.lambda_coordinate[1:]).all()
        ):
            raise ContractViolation("lambda_coordinate must be nondecreasing")
        object.__setattr__(self, "u_coordinate", self.u_coordinate.detach().clone())
        object.__setattr__(self, "lambda_coordinate", self.lambda_coordinate.detach().clone())


@dataclass(frozen=True)
class BandDefinition:
    band_id: str
    lower_mass: float
    upper_mass: float
    lower_lambda: float | None = None
    upper_lambda: float | None = None

    def __post_init__(self) -> None:
        require_non_empty_text(self.band_id, "band_id")
        if not 0.0 <= self.lower_mass < self.upper_mass <= 1.0:
            raise ValueError("band mass boundaries must satisfy 0 <= lower < upper <= 1")


@dataclass(frozen=True)
class CanonicalSpectrumBundle:
    meta: ArtifactMeta
    spectra: tuple[CanonicalSpectrumArtifact, ...] = ()
    bands: tuple[BandDefinition, ...] = ()
    _validation_issues: tuple[ValidationIssue, ...] = field(default=(), repr=False, compare=False)
    _validated_receipt: CompletionReceipt | None = field(default=None, repr=False, compare=False)
    _validated_fingerprint: str | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        spectra = tuple(self.spectra)
        bands = tuple(self.bands)
        if not spectra:
            raise ContractViolation("CanonicalSpectrumBundle requires at least one spectrum")
        if not bands:
            raise ContractViolation("CanonicalSpectrumBundle requires at least one band")
        if any(not isinstance(item, CanonicalSpectrumArtifact) for item in spectra):
            raise ContractViolation("spectra must contain CanonicalSpectrumArtifact instances")
        if any(not isinstance(item, BandDefinition) for item in bands):
            raise ContractViolation("bands must contain BandDefinition instances")
        object.__setattr__(self, "_validation_issues", tuple(self._validation_issues))
        if self._validated_receipt is not None and not isinstance(
            self._validated_receipt, CompletionReceipt
        ):
            raise ContractViolation("_validated_receipt must be CompletionReceipt or None")
        if self._validated_fingerprint is not None and not isinstance(
            self._validated_fingerprint, str
        ):
            raise ContractViolation("_validated_fingerprint must be a string or None")
        object.__setattr__(self, "spectra", spectra)
        object.__setattr__(self, "bands", bands)

    @staticmethod
    def _graph_key_identity(graph_key: GraphKey) -> tuple[str, str, str, str]:
        return graph_key.subject, graph_key.visit, graph_key.modality, graph_key.relation

    def _validation_fingerprint(self) -> str:
        return _canonical_json_hash(
            {
                "meta": asdict(self.meta),
                "spectra": [
                    {
                        "meta": asdict(item.meta),
                        "graph_key": self._graph_key_identity(item.graph_key),
                        "spectrum_artifact_id": item.spectrum_artifact_id,
                        "u": _tensor_content_hash(item.u_coordinate),
                        "lambda": _tensor_content_hash(item.lambda_coordinate),
                    }
                    for item in self.spectra
                ],
                "bands": [asdict(item) for item in self.bands],
                "validation_issues": [
                    {
                        "code": issue.code,
                        "severity": issue.severity,
                        "field": issue.field,
                        "message": issue.message,
                    }
                    for issue in self._validation_issues
                ],
            }
        )

    def _content_hash_is_consistent(self) -> bool:
        expected = _canonical_json_hash(
            {
                "spectra": [item.meta.content_sha256 for item in self.spectra],
                "bands": [
                    {
                        "band_id": item.band_id,
                        "lower_mass": item.lower_mass,
                        "upper_mass": item.upper_mass,
                        "lower_lambda": item.lower_lambda,
                        "upper_lambda": item.upper_lambda,
                    }
                    for item in self.bands
                ],
            }
        )
        return self.meta.content_sha256 == expected and all(
            item.meta.content_sha256
            == _canonical_json_hash(
                {
                    "u_coordinate": _tensor_content_hash(item.u_coordinate),
                    "lambda_coordinate": _tensor_content_hash(item.lambda_coordinate),
                }
            )
            for item in self.spectra
        )

    @property
    def science_key(self) -> str:
        context = ScienceContext(
            science_contract_version=self.meta.science_contract_version,
            science_config_hash=self.meta.science_config_hash,
            dataset_manifest_hash=self.meta.dataset_manifest_hash,
            split_id=self.meta.split_id,
            random_seed=self.meta.random_seed,
        )
        return build_science_key(
            context, self.meta.input_content_hashes, self.meta.module_contract_version
        )

    @property
    def reproduction_key(self) -> str:
        return build_reproduction_key(
            self.science_key,
            self.meta.implementation_hash,
            self.meta.numerics_profile_hash,
        )

    @property
    def validation_issues(self) -> tuple[ValidationIssue, ...]:
        return self._validation_issues

    @property
    def receipt(self) -> CompletionReceipt | None:
        receipt = self._validated_receipt
        if receipt is None or self._validated_fingerprint != self._validation_fingerprint():
            return None
        if (
            not self._content_hash_is_consistent()
            or receipt.module_id != "M3"
            or receipt.module_contract_version != MODULE_PROTOCOL_SPEC_VERSION
            or receipt.science_contract_version != self.meta.science_contract_version
            or receipt.canonical_status != CanonicalStatus.PASS
            or receipt.native_status != "SYNTHETIC_ANALYTIC_ONLY"
            or receipt.validator_status != "PASS"
            or receipt.validation_issue_codes
            != tuple(dict.fromkeys(issue.code for issue in self._validation_issues))
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
        return {
            "verification_scope": "SYNTHETIC_ANALYTIC_ONLY",
            "scientific_verification_status": "NOT_VERIFIED",
            "m3_executed": "true",
            "m4_executed": "false",
        }


@dataclass(frozen=True)
class BandSignalBundle:
    meta: ArtifactMeta
    signals: tuple[tuple[BandKey, Tensor], ...] = ()
