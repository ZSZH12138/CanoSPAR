from pathlib import Path

from scripts.verify_architecture_contract import run_checks

ROOT = Path(__file__).resolve().parents[2]


def test_verifier_has_named_core_gates() -> None:
    result = run_checks(ROOT)
    checks = {item["id"]: item["status"] for item in result["checks"]}

    for gate in (
        "G01_EXISTING_IMPORT_COMPATIBILITY",
        "G02_ARTIFACT_SCHEMA_COMPLETE",
        "G03_MODULE_API_COMPLETE",
        "G04_MODULE_REGISTRY_CONSISTENT",
        "G05_VERSION_NAMESPACES_SEPARATED",
        "G06_LINEAGE_DETERMINISTIC",
        "G07_CACHE_IDENTITY_CORRECT",
        "G08_INVALIDATION_DAG_CORRECT",
        "G09_RUNTIME_SCIENCE_DECOUPLED",
        "G10_FAIL_CLOSED_VALIDATION",
        "G11_CONTRACT_TESTS_PASS",
        "G12_NO_FAKE_SCIENTIFIC_IMPLEMENTATION",
    ):
        assert checks[gate] == "PASS"
