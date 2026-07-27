"""Synthetic acceptance tests for PPMI MDS-UPDRS target audits."""

from __future__ import annotations

import pytest

from canospar.data.ppmi_targets import PPMITargetError, audit_ppmi_targets

TARGET_CONFIG = {
    "subject_id_column": "PATNO",
    "visit_column": "EVENT_ID",
    "date_column": "INFODT",
    "change_direction": "followup_total - baseline_total",
    "task_thresholds": {"stress_test": 120, "ready": 180},
    "target_confirmed": True,
    "selection": {
        "primary_target": "candidate_A",
        "target_definition": "MDS-UPDRS Part III follow-up score minus baseline score",
        "primary_policy": "prefer_off",
        "secondary_targets": ["candidate_B"],
        "sensitivity_policies": ["unique_only", "prefer_on"],
    },
    "month_horizons": {
        "baseline": {"selector": "code_list_event_id", "event_id": "BL"},
        "month12": {"selector": "code_list_month", "month": 12, "event_id_prefix": "V"},
        "month24": {"selector": "code_list_month", "month": 24, "event_id_prefix": "V"},
        "month48": {"selector": "code_list_month", "month": 48, "event_id_prefix": "V"},
    },
    "candidates": {
        "candidate_A": {"parts": ["part_iii"]},
        "candidate_B": {"parts": ["part_i_clinician", "part_i_patient", "part_ii", "part_iii"]},
    },
    "tables": {
        "part_i_clinician": {
            "source": "part_i_clinician",
            "dictionary_selector": {
                "modules": ["MDS_P1_CLIN"],
                "item_name_regex": "^P1C_[A-Z]+$",
                "official_total_column": "P1C_TOTAL",
                "expected_item_count": 1,
            },
        },
        "part_i_patient": {
            "source": "part_i_patient",
            "dictionary_selector": {
                "modules": ["MDS_P1_PAT"],
                "item_name_regex": "^P1P_[A-Z]+$",
                "official_total_column": "P1P_TOTAL",
                "expected_item_count": 1,
            },
        },
        "part_ii": {
            "source": "part_ii",
            "dictionary_selector": {
                "modules": ["MDS_P2"],
                "item_name_regex": "^P2_[A-Z]+$",
                "official_total_column": "P2_TOTAL",
                "expected_item_count": 1,
            },
        },
        "part_iii": {
            "source": "part_iii",
            "dictionary_selector": {
                "modules": ["MDS_P3"],
                "item_name_regex": "^P3_[A-Z]+$",
                "official_total_column": "P3_TOTAL",
                "expected_item_count": 1,
            },
        },
    },
    "part_iii_state": {
        "primary_field": "PDSTATE",
        "fields": {
            "PDSTATE": {"off_values": ["OFF"], "on_values": ["ON"]},
            "OFFEXAM": {"off_values": ["1"], "on_values": []},
            "ONEXAM": {"off_values": [], "on_values": ["1"]},
        },
        "audit_only_fields": ["PDMEDYN", "HRPOSTMED", "DBSYN"],
        "policies": {
            "unique_only": {"enabled": True},
            "prefer_off": {"enabled": True},
            "prefer_on": {"enabled": True},
        },
        "confirmed": True,
    },
}


def _dictionary() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for module, item, total in (
        ("MDS_P1_CLIN", "P1C_ITEM", "P1C_TOTAL"),
        ("MDS_P1_PAT", "P1P_ITEM", "P1P_TOTAL"),
        ("MDS_P2", "P2_ITEM", "P2_TOTAL"),
        ("MDS_P3", "P3_ITEM", "P3_TOTAL"),
    ):
        rows.extend(
            [
                {"MOD_NAME": module, "ITM_NAME": item, "ITM_TYPE": "NUMBER"},
                {"MOD_NAME": module, "ITM_NAME": total, "ITM_TYPE": "NUMBER"},
            ]
        )
    return rows + [{"MOD_NAME": "MDS_P3", "ITM_NAME": "PAG_NAME", "ITM_TYPE": "metadata"}]


def _rows(subject: str, visits: list[str], item: str, value: int) -> list[dict[str, str]]:
    total = item.replace("ITEM", "TOTAL")
    return [
        {
            "PATNO": subject,
            "EVENT_ID": visit,
            "INFODT": "2026-01-01",
            item: str(value),
            total: str(value),
        }
        for visit in visits
    ]


def _part_iii_row(visit: str, value: int, state: str) -> dict[str, str]:
    return {
        "PATNO": "PPMI_SYN_001",
        "EVENT_ID": visit,
        "INFODT": "2026-01-01" if visit == "BL" else f"20{26 + int(visit[-2:]) // 12:02d}-01-01",
        "P3_ITEM": str(value),
        "P3_TOTAL": str(value),
        "PDSTATE": state,
        "OFFEXAM": "1" if state == "OFF" else "0",
        "ONEXAM": "0" if state == "OFF" else "1",
    }


def _clinical_tables() -> dict[str, list[dict[str, str]]]:
    visits = ["BL", "V04", "V06", "V10"]
    return {
        "part_i_clinician": _rows("PPMI_SYN_001", visits, "P1C_ITEM", 1)
        + _rows("PPMI_SYN_002", visits, "P1C_ITEM", 1),
        "part_i_patient": _rows("PPMI_SYN_001", visits, "P1P_ITEM", 2)
        + _rows("PPMI_SYN_002", visits, "P1P_ITEM", 2),
        "part_ii": _rows("PPMI_SYN_001", visits, "P2_ITEM", 3)
        + _rows("PPMI_SYN_002", visits, "P2_ITEM", 3),
        "part_iii": [
            _part_iii_row("BL", 10, "OFF"),
            _part_iii_row("BL", 20, "ON"),
            _part_iii_row("V04", 14, "OFF"),
            _part_iii_row("V06", 16, "OFF"),
            _part_iii_row("V10", 18, "OFF"),
        ]
        + _rows("PPMI_SYN_002", visits, "P3_ITEM", 5),
    }


def _imaging_manifest() -> list[dict[str, object]]:
    return [
        {
            "subject_id": subject,
            "visit_id": "BL",
            "imaging_date": "2026-01-02",
            "t1_available": True,
            "fmri_available": True,
            "dwi_available": True,
            "row_status": "included",
        }
        for subject in ("PPMI_SYN_001", "PPMI_SYN_002")
    ]


def _code_list() -> list[dict[str, str]]:
    return [
        {"ITM_NAME": "EVENT_ID", "CODE": "BL", "DECODE": "Baseline"},
        {"ITM_NAME": "EVENT_ID", "CODE": "V01", "DECODE": "Visit 01 (Month 12)"},
        {"ITM_NAME": "EVENT_ID", "CODE": "V04", "DECODE": "Visit 04 (Month 12)"},
        {"ITM_NAME": "EVENT_ID", "CODE": "V02", "DECODE": "Visit 02 (Month 24)"},
        {"ITM_NAME": "EVENT_ID", "CODE": "V06", "DECODE": "Visit 06 (Month 24)"},
        {"ITM_NAME": "EVENT_ID", "CODE": "V10", "DECODE": "Visit 10 (Month 48)"},
    ]


def _audit(
    config: dict[str, object] = TARGET_CONFIG,
    dictionary_rows: list[dict[str, str]] | None = None,
) -> object:
    return audit_ppmi_targets(
        _clinical_tables(),
        _dictionary() if dictionary_rows is None else dictionary_rows,
        config,
        _imaging_manifest(),
        _code_list(),
    )


def test_audits_duplicates_and_reports_every_exam_state_strategy() -> None:
    result = _audit()

    assert result.audit["status"] == "READY_FOR_USER_SELECTED_TASK"
    assert result.audit["primary_target"] == "candidate_A"
    assert (
        result.audit["target_definition"]
        == "MDS-UPDRS Part III follow-up score minus baseline score"
    )
    assert result.audit["primary_policy"] == "prefer_off"
    assert result.audit["secondary_targets"] == ["candidate_B"]
    assert result.audit["sensitivity_policies"] == ["unique_only", "prefer_on"]
    assert result.audit["part_iii_duplicate_audit"]["duplicate_subject_visit_groups"] == 1
    assert set(result.branches["candidate_A"]) == {"unique_only", "prefer_off", "prefer_on"}
    assert result.branches["candidate_A"]["unique_only"]["12"]["independent_subject_count"] == 1
    assert result.branches["candidate_A"]["prefer_off"]["12"]["independent_subject_count"] == 2
    assert result.branches["candidate_A"]["prefer_on"]["12"]["independent_subject_count"] == 2


def test_rejects_confirmed_target_without_an_explicit_selection() -> None:
    config = {key: value for key, value in TARGET_CONFIG.items() if key != "selection"}

    with pytest.raises(PPMITargetError, match="selection"):
        _audit(config)


def test_resolves_month_horizons_from_decode_and_keeps_all_matching_event_codes() -> None:
    result = _audit()

    assert result.audit["resolved_horizon_event_ids"] == {
        "baseline": ("BL",),
        "12": ("V01", "V04"),
        "24": ("V02", "V06"),
        "48": ("V10",),
    }


def test_reports_candidate_b_all_horizons_overlap_and_date_intervals() -> None:
    result = _audit()

    coverage = result.branches["candidate_B"]["prefer_off"]
    assert set(coverage) == {"baseline", "12", "24", "48"}
    assert coverage["baseline"]["clinical_complete_subject_count"] == 2
    assert coverage["24"]["baseline_trimodal_target_subject_count"] == 2
    assert coverage["48"]["clinical_complete_subject_count"] == 2
    assert coverage["12"]["imaging_clinical_interval_days"] == {
        "count": 2,
        "min": 1,
        "max": 1,
        "mean": 1.0,
    }
    assert coverage["12"]["task_gate"]["recommendation"] == "STRESS_TEST_ONLY"


def test_requires_dictionary_number_items_and_official_total_headers() -> None:
    config = TARGET_CONFIG | {
        "tables": TARGET_CONFIG["tables"]
        | {
            "part_iii": TARGET_CONFIG["tables"]["part_iii"]
            | {
                "dictionary_selector": {
                    "modules": ["MDS_P3"],
                    "item_name_regex": "^P3_[A-Z]+$",
                    "official_total_column": "PAG_NAME",
                    "expected_item_count": 1,
                }
            }
        }
    }

    try:
        _audit(config)
    except PPMITargetError as error:
        assert "total" in str(error).casefold()
    else:  # pragma: no cover
        raise AssertionError("metadata column was accepted as an official total")


def test_excludes_numeric_administrative_dictionary_fields_with_the_configured_regex() -> None:
    dictionary = _dictionary() + [{"MOD_NAME": "MDS_P3", "ITM_NAME": "CNO", "ITM_TYPE": "NUMBER"}]

    result = _audit(dictionary_rows=dictionary)

    assert (
        result.branches["candidate_A"]["prefer_off"]["48"]["clinical_complete_subject_count"] == 2
    )


def test_marks_equal_preference_rows_ambiguous_without_selecting_first_row() -> None:
    tables = _clinical_tables()
    tables["part_iii"][1] = tables["part_iii"][1] | {"PDSTATE": "OFF"}

    result = audit_ppmi_targets(
        tables, _dictionary(), TARGET_CONFIG, _imaging_manifest(), _code_list()
    )

    duplicate_audit = result.audit["part_iii_duplicate_audit"]
    assert duplicate_audit["ambiguous_preference_groups"] == 1
    assert duplicate_audit["ambiguous_preference_groups_by_policy"] == {
        "prefer_off": 1,
        "prefer_on": 1,
    }
    assert result.branches["candidate_A"]["prefer_off"]["12"]["ambiguous_subject_count"] == 1
    assert result.branches["candidate_A"]["prefer_off"]["12"]["independent_subject_count"] == 1


def test_accepts_empty_secondary_state_value_sets_when_primary_state_is_missing() -> None:
    tables = _clinical_tables()
    tables["part_iii"][0] = tables["part_iii"][0] | {"PDSTATE": ""}
    tables["part_iii"][1] = tables["part_iii"][1] | {"PDSTATE": ""}

    result = audit_ppmi_targets(
        tables, _dictionary(), TARGET_CONFIG, _imaging_manifest(), _code_list()
    )

    assert result.branches["candidate_A"]["prefer_off"]["12"]["independent_subject_count"] == 2


def test_uses_24_month_independent_subject_count_for_every_branch_gate() -> None:
    subjects = [f"PPMI_SYN_GATE_{number:03d}" for number in range(180)]
    visits_by_subject = {
        subject: ["BL", "V04"] + (["V06"] if index < 179 else []) + (["V10"] if index < 100 else [])
        for index, subject in enumerate(subjects)
    }
    table_specs = {
        "part_i_clinician": ("P1C_ITEM", "P1C_TOTAL"),
        "part_i_patient": ("P1P_ITEM", "P1P_TOTAL"),
        "part_ii": ("P2_ITEM", "P2_TOTAL"),
        "part_iii": ("P3_ITEM", "P3_TOTAL"),
    }
    clinical_tables: dict[str, list[dict[str, str]]] = {}
    for source, (item, total) in table_specs.items():
        clinical_tables[source] = [
            {
                "PATNO": subject,
                "EVENT_ID": visit,
                "INFODT": "2026-01-01",
                item: "1",
                total: "1",
                "PDSTATE": "OFF",
            }
            for subject, visits in visits_by_subject.items()
            for visit in visits
        ]
    imaging = [
        {
            "subject_id": subject,
            "visit_id": "BL",
            "imaging_date": "2026-01-02",
            "t1_available": True,
            "fmri_available": True,
            "dwi_available": True,
            "row_status": "included",
        }
        for subject in subjects
    ]

    result = audit_ppmi_targets(
        clinical_tables, _dictionary(), TARGET_CONFIG, imaging, _code_list()
    )

    coverage = result.branches["candidate_A"]["prefer_off"]
    assert coverage["12"]["independent_subject_count"] == 180
    assert coverage["24"]["independent_subject_count"] == 179
    assert coverage["48"]["independent_subject_count"] == 100
    for horizon in ("12", "24", "48"):
        gate = coverage[horizon]["task_gate"]
        assert gate["recommendation"] == "SHORTER_WINDOW_RECOMMENDED"
        assert gate["basis_horizon"] == "24"
        assert gate["basis_independent_subject_count"] == 179


def test_computes_intervals_from_approved_slash_formatted_clinical_dates() -> None:
    tables = _clinical_tables()
    tables["part_iii"] = [row | {"INFODT": "01/01/2026"} for row in tables["part_iii"]]

    result = audit_ppmi_targets(
        tables, _dictionary(), TARGET_CONFIG, _imaging_manifest(), _code_list()
    )

    assert result.branches["candidate_A"]["prefer_off"]["12"]["imaging_clinical_interval_days"] == {
        "count": 2,
        "min": 1,
        "max": 1,
        "mean": 1.0,
    }


def test_does_not_choose_a_candidate_b_component_date_when_baseline_dates_conflict() -> None:
    tables = _clinical_tables()
    tables["part_i_patient"] = [
        row | {"INFODT": "01/03/2026"}
        if row["PATNO"] == "PPMI_SYN_001" and row["EVENT_ID"] == "BL"
        else row
        for row in tables["part_i_patient"]
    ]

    result = audit_ppmi_targets(
        tables, _dictionary(), TARGET_CONFIG, _imaging_manifest(), _code_list()
    )

    coverage = result.branches["candidate_B"]["prefer_off"]["12"]
    assert coverage["clinical_complete_subject_count"] == 2
    assert coverage["imaging_clinical_interval_days"]["count"] == 1
    assert coverage["exclusion_reasons"]["missing_or_ambiguous_baseline_clinical_date"] == 1


def test_reports_aggregate_clinical_date_precision_without_retaining_date_values() -> None:
    tables = {
        source: [row | {"INFODT": "01/2026"} for row in rows]
        for source, rows in _clinical_tables().items()
    }

    result = audit_ppmi_targets(
        tables, _dictionary(), TARGET_CONFIG, _imaging_manifest(), _code_list()
    )

    assert result.audit["clinical_date_precision_distribution"] == {
        "iso_day": 0,
        "mdy_day": 0,
        "month_year": sum(len(rows) for rows in tables.values()),
        "missing_or_invalid": 0,
    }
    assert result.audit["part_iii_baseline_date_precision_distribution"] == {
        "iso_day": 0,
        "mdy_day": 0,
        "month_year": sum(row["EVENT_ID"] == "BL" for row in tables["part_iii"]),
        "missing_or_invalid": 0,
    }
