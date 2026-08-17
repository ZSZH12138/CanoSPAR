import pytest

from canospar.runtime.invalidation import MODULE_ORDER, compute_invalidated_modules


def test_m3_change_invalidates_only_m3_and_downstream() -> None:
    assert compute_invalidated_modules("M3") == (
        "M3",
        "M4",
        "M5",
        "M6",
        "M7",
        "M8",
        "M9",
    )


def test_m0_change_invalidates_p0_and_all_scientific_downstream() -> None:
    assert compute_invalidated_modules("M0") == MODULE_ORDER


def test_unknown_module_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown module"):
        compute_invalidated_modules("X1")
