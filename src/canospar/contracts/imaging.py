"""P0 imaging-plane artifact contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .base import (
    ArtifactMeta,
    JsonObject,
    Tensor,
    _freeze_mapping,
    _freeze_string_tuple,
    require_non_empty_text,
)
from .errors import ContractViolation


@dataclass(frozen=True)
class ImagingInputBundle:
    subject_id: str
    visit_id: str
    dataset: str
    raw_or_derivative_refs: Mapping[str, str]
    modality_available: Mapping[str, bool]
    acquisition_metadata: JsonObject
    source_hashes: Mapping[str, str]

    def __post_init__(self) -> None:
        for field_name in ("subject_id", "visit_id", "dataset"):
            require_non_empty_text(getattr(self, field_name), field_name)
        object.__setattr__(
            self,
            "raw_or_derivative_refs",
            _freeze_mapping(self.raw_or_derivative_refs, "raw_or_derivative_refs"),
        )
        object.__setattr__(
            self,
            "modality_available",
            _freeze_mapping(self.modality_available, "modality_available"),
        )
        if any(type(value) is not bool for value in self.modality_available.values()):
            raise ContractViolation("modality_available values must be bool")
        object.__setattr__(
            self,
            "acquisition_metadata",
            _freeze_mapping(self.acquisition_metadata, "acquisition_metadata"),
        )
        object.__setattr__(
            self,
            "source_hashes",
            _freeze_mapping(self.source_hashes, "source_hashes"),
        )


@dataclass(frozen=True)
class ROIAlignedSample:
    meta: ArtifactMeta
    subject_id: str
    visit_id: str
    atlas_id: str
    atlas_hash: str
    roi_table_hash: str
    node_order_hash: str
    modality_payloads: Mapping[str, Mapping[str, Tensor]]
    modality_available: Mapping[str, bool]
    qc_vector: Mapping[str, float]
    qc_status: str
    source_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.meta, ArtifactMeta):
            raise ContractViolation("meta must be ArtifactMeta")
        for field_name in (
            "subject_id",
            "visit_id",
            "atlas_id",
            "atlas_hash",
            "roi_table_hash",
            "node_order_hash",
            "qc_status",
        ):
            require_non_empty_text(getattr(self, field_name), field_name)
        object.__setattr__(
            self,
            "modality_payloads",
            _freeze_mapping(self.modality_payloads, "modality_payloads"),
        )
        object.__setattr__(
            self,
            "modality_available",
            _freeze_mapping(self.modality_available, "modality_available"),
        )
        if any(type(value) is not bool for value in self.modality_available.values()):
            raise ContractViolation("modality_available values must be bool")
        object.__setattr__(self, "qc_vector", _freeze_mapping(self.qc_vector, "qc_vector"))
        object.__setattr__(
            self,
            "source_artifact_ids",
            _freeze_string_tuple(self.source_artifact_ids, "source_artifact_ids"),
        )
