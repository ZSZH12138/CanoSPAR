"""Unit tests for the preregistered, label-free PPMI task gate."""

from __future__ import annotations

import pytest

from canospar.data.task_gate import TaskGateError, evaluate_task_gate


@pytest.mark.parametrize(
    ("subject_count", "recommendation"),
    [
        (119, "STRESS_TEST_ONLY"),
        (120, "SHORTER_WINDOW_RECOMMENDED"),
        (179, "SHORTER_WINDOW_RECOMMENDED"),
        (180, "TWENTY_FOUR_MONTH_RECOMMENDED"),
    ],
)
def test_task_gate_uses_independent_subject_boundaries(
    subject_count: int, recommendation: str
) -> None:
    decision = evaluate_task_gate(subject_count)

    assert decision.independent_subject_count == subject_count
    assert decision.recommendation == recommendation


@pytest.mark.parametrize(
    (
        "target_confirmed",
        "part_iii_state_policy_confirmed",
        "expected_status",
        "expected_confirmations",
        "expected_final",
    ),
    [
        (
            False,
            False,
            "PART_III_STATE_POLICY_REQUIRED",
            ("PART_III_STATE_POLICY_REQUIRED", "TARGET_CONFIRMATION_REQUIRED"),
            False,
        ),
        (
            True,
            False,
            "PART_III_STATE_POLICY_REQUIRED",
            ("PART_III_STATE_POLICY_REQUIRED",),
            False,
        ),
        (
            False,
            True,
            "TARGET_CONFIRMATION_REQUIRED",
            ("TARGET_CONFIRMATION_REQUIRED",),
            False,
        ),
        (True, True, "READY_FOR_USER_SELECTED_TASK", (), True),
    ],
)
def test_task_gate_confirmation_precedence(
    target_confirmed: bool,
    part_iii_state_policy_confirmed: bool,
    expected_status: str,
    expected_confirmations: tuple[str, ...],
    expected_final: bool,
) -> None:
    decision = evaluate_task_gate(
        180,
        target_confirmed=target_confirmed,
        part_iii_state_policy_confirmed=part_iii_state_policy_confirmed,
    )

    assert decision.status == expected_status
    assert decision.required_confirmations == expected_confirmations
    assert decision.final_task_selected is expected_final


def test_task_gate_rejects_negative_subject_counts() -> None:
    with pytest.raises(TaskGateError, match="non-negative"):
        evaluate_task_gate(-1)


def test_task_gate_rejects_non_integer_counts_and_changed_preregistered_thresholds() -> None:
    with pytest.raises(TaskGateError, match="integer"):
        evaluate_task_gate("120")  # type: ignore[arg-type]
    with pytest.raises(TaskGateError, match="120 and 180"):
        evaluate_task_gate(120, stress_test_threshold=121)
