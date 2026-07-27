"""Synthetic PPMI sequence and scanner parsing tests."""

from __future__ import annotations

from canospar.data.ppmi_sequences import classify_sequence, scanner_metadata

ALIASES = {
    "smri": ["t1", "mprage", "spgr"],
    "fmri": ["rest", "rs-fmri", "bold"],
    "dwi": ["dti", "dwi", "diffusion"],
    "exclude": ["localizer", "scout", "reverse phase", "field map"],
}


def test_classifies_t1_without_diffusion_or_functional_contamination() -> None:
    assert classify_sequence("3D T1 MPRAGE", ALIASES).modality == "t1"
    assert classify_sequence("DTI T1 reference", ALIASES).reason == "contaminated"


def test_classifies_complete_rest_but_rejects_short_reverse_phase_and_nm_mt() -> None:
    assert classify_sequence("Resting state BOLD", ALIASES).modality == "fmri"
    assert classify_sequence("rest reverse phase", ALIASES).reason == "excluded"
    assert classify_sequence("rest NM-MT", ALIASES).reason == "contaminated"
    assert (
        classify_sequence("rest BOLD RL", ALIASES | {"reverse_phase_short_rules": ["rl"]}).reason
        == "excluded"
    )


def test_classifies_diffusion_but_rejects_t1_and_t2_contamination() -> None:
    assert classify_sequence("DTI diffusion", ALIASES).modality == "dwi"
    assert classify_sequence("DTI T1", ALIASES).reason == "contaminated"
    assert classify_sequence("DWI T2", ALIASES).reason == "contaminated"


def test_applies_modality_exclusions_before_accepting_a_candidate() -> None:
    strict = ALIASES | {
        "smri_exclude": ["flair", "survey"],
        "fmri_exclude": ["survey"],
        "dwi_exclude": ["flair", "survey"],
    }

    assert classify_sequence("DTI survey", strict).modality is None
    assert classify_sequence("DTI flair", strict).modality is None
    assert classify_sequence("resting state survey", strict).modality is None
    assert classify_sequence("MPRAGE flair", strict).modality is None


def test_scanner_batch_is_deterministic_and_manufacturer_is_not_site() -> None:
    first = scanner_metadata("SIEMENS Prisma 3.0T resting state BOLD")
    second = scanner_metadata("SIEMENS Prisma 3.0T resting state BOLD")

    assert first == second
    assert first.vendor == "siemens"
    assert first.field_strength == 3.0
    assert first.model == "prisma"
    assert first.batch_id.startswith("scanner_batch_")


def test_scanner_batch_is_unavailable_when_no_scanner_or_protocol_metadata_exists() -> None:
    parsed = scanner_metadata("")

    assert parsed.vendor is None
    assert parsed.field_strength is None
    assert parsed.model is None
    assert parsed.normalized_protocol is None
    assert parsed.batch_id is None
