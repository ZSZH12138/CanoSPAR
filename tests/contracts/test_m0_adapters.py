import pytest

from canospar.api.m0 import DatasetManifestArtifact, SplitRegistryArtifact, TaskDefinitionArtifact


def test_m0_outputs_are_read_only_references() -> None:
    manifest = DatasetManifestArtifact(
        artifact_ref="reports/data_qc/week02_04/manifest_validation_summary.json",
        content_hash="hash-a",
    )
    split = SplitRegistryArtifact(
        artifact_ref="reports/data_qc/week02_04/verification_results.json",
        content_hash="hash-b",
    )
    task = TaskDefinitionArtifact(
        artifact_ref="configs/data/hcp.yaml",
        content_hash="hash-c",
    )

    assert manifest.artifact_ref.startswith("reports/")
    assert split.content_hash == "hash-b"
    assert task.artifact_ref.startswith("configs/")


def test_m0_loader_does_not_regenerate_manifests() -> None:
    from canospar.api.m0 import load_dataset_manifest

    with pytest.raises(NotImplementedError, match="read-only"):
        load_dataset_manifest("reports/data_qc/week02_04/manifest_validation_summary.json")
