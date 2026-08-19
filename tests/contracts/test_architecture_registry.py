from pathlib import Path

import pytest

from scripts.verify_architecture_contract import (
    MODULE_NAMES,
    REQUIRED_FILES,
    check_registry_consistency,
    load_registry,
)

ROOT = Path(__file__).resolve().parents[2]


def test_registry_contains_p0_and_m0_to_m9() -> None:
    registry = load_registry(ROOT)

    assert tuple(registry["modules"]) == MODULE_NAMES
    assert registry["numerics_profile_schema_version"] == "1.0.0"
    assert registry["module_protocol_spec_version"] == "1.1.0"
    assert registry["modules"]["M2"]["implementation_status"] == "IMPLEMENTED"
    assert registry["modules"]["M3"]["implementation_status"] == "IMPLEMENTED"
    assert registry["modules"]["M4"]["implementation_status"] == "CONTRACT_ONLY"
    assert registry["modules"]["M9"]["implementation_status"] == "CONTRACT_ONLY"


def test_required_architecture_files_are_present() -> None:
    missing = [relative for relative in REQUIRED_FILES if not (ROOT / relative).exists()]

    assert missing == []


def test_registry_source_of_truth_is_one_to_one() -> None:
    registry = load_registry(ROOT)

    assert check_registry_consistency(registry) == []


def test_contract_only_modules_cannot_be_marked_implemented() -> None:
    registry = load_registry(ROOT)
    invalid = dict(registry)
    invalid["modules"] = {
        **registry["modules"],
        "M4": {**registry["modules"]["M4"], "implementation_status": "IMPLEMENTED"},
    }

    with pytest.raises(ValueError, match="CONTRACT_ONLY"):
        check_registry_consistency(invalid)


def test_m2_implementation_status_is_consistent_across_governance_docs() -> None:
    registry = load_registry(ROOT)
    assert registry["modules"]["M2"]["implementation_status"] == "IMPLEMENTED"

    protocol = (ROOT / "docs/architecture/CANOSPAR_MODULE_PROTOCOL_SPEC_V1.md").read_text(
        encoding="utf-8"
    )
    m2_section = protocol.split("## 10. M2：", 1)[1].split("## 11. M3：", 1)[0]
    assert "当前状态：** `IMPLEMENTED`" in m2_section
    assert "| M2 |" in protocol
    assert "| M2 | `build_normalized_laplacian`" in protocol
    assert (
        "| M2 | `build_normalized_laplacian`、`compute_spectrum`、`compute_spectral_statistics`、"
        "`fit_qc_transform`、`transform_qc`、`run_m2` | IMPLEMENTED" in protocol
    )

    architecture = (ROOT / "docs/architecture/CANOSPAR_ARCHITECTURE_CONTRACT_V1.md").read_text(
        encoding="utf-8"
    )
    assert (
        "| M2 | MultiGraphArtifact, M2Spec, ScienceContext | SpectralBundle | "
        "IMPLEMENTED |" in architecture
    )

    adr = (ROOT / "docs/decisions/0003-module-protocol-v1.1-m2-m4-contract-repair.md").read_text(
        encoding="utf-8"
    )
    assert "M2 is implemented" in adr
    assert "M4-M9 remain `CONTRACT_ONLY`" in adr
