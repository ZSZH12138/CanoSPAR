"""Pure preregistered PPMI task-gating rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


class TaskGateError(ValueError):
    """A task-gate input is not valid."""


@dataclass(frozen=True)
class TaskGateDecision:
    """A recommendation derived only from independent-subject count."""

    independent_subject_count: int
    recommendation: str
    status: str
    required_confirmations: tuple[str, ...]
    final_task_selected: bool

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready copy without changing the decision."""
        return asdict(self)


def evaluate_task_gate(
    independent_subject_count: int,
    *,
    target_confirmed: bool = False,
    part_iii_state_policy_confirmed: bool = False,
    stress_test_threshold: int = 120,
    ready_threshold: int = 180,
) -> TaskGateDecision:
    """Apply the fixed task gate without looking at model results or row count."""
    if not isinstance(independent_subject_count, int):
        raise TaskGateError("independent subject count must be an integer")
    if isinstance(independent_subject_count, bool) or independent_subject_count < 0:
        raise TaskGateError("independent subject count must be a non-negative integer")
    if (stress_test_threshold, ready_threshold) != (120, 180):
        raise TaskGateError("PPMI task thresholds must remain 120 and 180")
    if independent_subject_count < stress_test_threshold:
        recommendation = "STRESS_TEST_ONLY"
    elif independent_subject_count < ready_threshold:
        recommendation = "SHORTER_WINDOW_RECOMMENDED"
    else:
        recommendation = "TWENTY_FOUR_MONTH_RECOMMENDED"

    confirmations = tuple(
        status
        for status, confirmed in (
            ("PART_III_STATE_POLICY_REQUIRED", part_iii_state_policy_confirmed),
            ("TARGET_CONFIRMATION_REQUIRED", target_confirmed),
        )
        if not confirmed
    )
    return TaskGateDecision(
        independent_subject_count=independent_subject_count,
        recommendation=recommendation,
        status=confirmations[0] if confirmations else "READY_FOR_USER_SELECTED_TASK",
        required_confirmations=confirmations,
        final_task_selected=not confirmations,
    )
