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
