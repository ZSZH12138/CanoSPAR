"""M0 read-only references to existing metadata artifacts."""

from __future__ import annotations

from dataclasses import dataclass

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
