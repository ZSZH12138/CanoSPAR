from canospar.contracts.base import ArtifactMeta
from canospar.validators.contracts import validate_artifact_meta


def make_meta(schema_version: str = "1.0.0") -> ArtifactMeta:
    return ArtifactMeta(
        schema_version=schema_version,
        artifact_type="SyntheticArtifact",
        artifact_id="artifact-a",
        producer_module="M1",
        module_contract_version="1.0.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="config-a",
        dataset_manifest_hash=None,
        split_id=None,
        random_seed=None,
        content_sha256="hash-a",
        implementation_hash="impl-a",
        numerics_profile_hash="numerics-a",
        created_at_utc="2026-08-17T00:00:00Z",
    )


def test_schema_mismatch_fails_closed() -> None:
    report = validate_artifact_meta(make_meta(), expected_schema_version="2.0.0")

    assert report.status == "FAIL"
    assert report.issues[0].code == "SCHEMA_VERSION_MISMATCH"


def test_recorded_content_hash_can_be_checked() -> None:
    report = validate_artifact_meta(make_meta(), expected_content_sha256="different")

    assert report.status == "FAIL"
    assert report.issues[0].code == "ARTIFACT_HASH_MISMATCH"


def test_valid_artifact_meta_is_ready() -> None:
    report = validate_artifact_meta(make_meta(), expected_schema_version="1.0.0")

    assert report.status == "PASS"
    assert report.issues == ()
