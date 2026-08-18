"""M0 read-only references to existing metadata artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from canospar.contracts.base import AvailabilityMask, JsonObject
from canospar.contracts.imaging import ImagingInputBundle

from ._contract_only import m0_read_only


@dataclass(frozen=True)
class DatasetManifestArtifact:
    artifact_ref: str
    content_hash: str


@dataclass(frozen=True)
class SplitRegistryArtifact:
    artifact_ref: str
    content_hash: str


@dataclass(frozen=True)
class TaskDefinitionArtifact:
    artifact_ref: str
    content_hash: str


def load_dataset_manifest(artifact_ref: str) -> DatasetManifestArtifact:
    del artifact_ref
    raise m0_read_only()


def load_split_registry(artifact_ref: str) -> SplitRegistryArtifact:
    del artifact_ref
    raise m0_read_only()


def load_task_definition(artifact_ref: str) -> TaskDefinitionArtifact:
    del artifact_ref
    raise m0_read_only()


def build_imaging_input_bundle(
    manifest: DatasetManifestArtifact,
    split: SplitRegistryArtifact,
    task: TaskDefinitionArtifact,
    *,
    subject_id: str,
    visit_id: str,
    dataset: str,
    raw_or_derivative_refs: Mapping[str, str],
    modality_available: AvailabilityMask,
    acquisition_metadata: JsonObject,
    source_hashes: Mapping[str, str],
) -> ImagingInputBundle:
    del (
        manifest,
        split,
        task,
        subject_id,
        visit_id,
        dataset,
        raw_or_derivative_refs,
        modality_available,
        acquisition_metadata,
        source_hashes,
    )
    raise m0_read_only()
