from canospar.contracts.base import ArtifactMeta
from canospar.contracts.imaging import ImagingInputBundle, ROIAlignedSample


def make_meta(artifact_type: str) -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type=artifact_type,
        artifact_id="artifact-a",
        producer_module="P0",
        module_contract_version="1.0.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="config-a",
        dataset_manifest_hash=None,
        split_id=None,
        random_seed=None,
        content_sha256="content-a",
        implementation_hash="impl-a",
        numerics_profile_hash="numerics-a",
        created_at_utc="2026-08-17T00:00:00Z",
    )


def test_imaging_input_bundle_defensively_copies_mappings() -> None:
    refs = {"t1": "source-ref"}
    bundle = ImagingInputBundle(
        subject_id="subject-a",
        visit_id="baseline",
        dataset="synthetic",
        raw_or_derivative_refs=refs,
        modality_available={"smri": True, "dmri": False, "fmri": False},
        acquisition_metadata={"scanner": "synthetic"},
        source_hashes={"t1": "hash-a"},
    )
    refs["t1"] = "changed"

    assert bundle.raw_or_derivative_refs["t1"] == "source-ref"


def test_roi_aligned_sample_exposes_atlas_and_qc_identity() -> None:
    sample = ROIAlignedSample(
        meta=make_meta("ROIAlignedSample"),
        subject_id="subject-a",
        visit_id="baseline",
        atlas_id="toy-atlas",
        atlas_hash="atlas-hash",
        roi_table_hash="roi-hash",
        node_order_hash="node-order-hash",
        modality_payloads={"smri": {"thickness": [1.0, 2.0]}},
        modality_available={"smri": True, "dmri": False, "fmri": False},
        qc_vector={"smri_qc": 1.0},
        qc_status="PASS_WITH_MANUAL_REVIEW",
        source_artifact_ids=("source-a",),
    )

    assert sample.atlas_id == "toy-atlas"
    assert sample.qc_status == "PASS_WITH_MANUAL_REVIEW"
