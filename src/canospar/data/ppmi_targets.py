"""Aggregate-only, configuration-driven PPMI MDS-UPDRS target audits."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean

from canospar.data.task_gate import evaluate_task_gate


class PPMITargetError(ValueError):
    """PPMI clinical inputs cannot safely support a target audit."""


@dataclass(frozen=True)
class PPMITargetAuditResult:
    """Aggregate results only; no subject identifiers or clinical rows are retained."""

    audit: dict[str, object]
    branches: dict[str, dict[str, dict[str, dict[str, object]]]]


_PARTS = ("part_i_clinician", "part_i_patient", "part_ii", "part_iii")
_POLICIES = ("unique_only", "prefer_off", "prefer_on")
_CANDIDATES = {
    "candidate_A": ("part_iii",),
    "candidate_B": _PARTS,
}


@dataclass(frozen=True)
class _Selection:
    row: Mapping[str, object] | None
    reason: str | None


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PPMITargetError(f"PPMI target configuration lacks valid {name}")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PPMITargetError(f"PPMI target configuration lacks {name}")
    return value.strip()


def _strings(value: object, name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PPMITargetError(f"PPMI target configuration lacks valid {name}")
    values = tuple(_text(item, name) for item in value)
    if not values or len(set(values)) != len(values):
        raise PPMITargetError(f"PPMI target configuration lacks valid {name}")
    return values


def _state_strings(value: object, name: str) -> tuple[str, ...]:
    """Validate a state-value sequence, allowing the configured empty opposite state."""
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise PPMITargetError(f"PPMI target configuration lacks valid {name}")
    values = tuple(_text(item, name) for item in value)
    if len(set(values)) != len(values):
        raise PPMITargetError(f"PPMI target configuration lacks valid {name}")
    return values


def _part_configs(config: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    tables = _mapping(config.get("tables"), "tables")
    result: dict[str, Mapping[str, object]] = {}
    for part in _PARTS:
        item = _mapping(tables.get(part), f"tables.{part}")
        _text(item.get("source"), f"tables.{part}.source")
        if "item_columns" in item:
            raise PPMITargetError("PPMI target configuration must not list item_columns")
        selector = _mapping(item.get("dictionary_selector"), f"tables.{part}.dictionary_selector")
        _strings(selector.get("modules"), f"tables.{part}.dictionary_selector.modules")
        item_name_regex = _text(
            selector.get("item_name_regex"),
            f"tables.{part}.dictionary_selector.item_name_regex",
        )
        try:
            re.compile(item_name_regex)
        except re.error as error:
            raise PPMITargetError(
                f"PPMI target configuration has invalid {part} item regex"
            ) from error
        _text(
            selector.get("official_total_column"),
            f"tables.{part}.dictionary_selector.official_total_column",
        )
        expected = selector.get("expected_item_count")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            raise PPMITargetError(f"PPMI target configuration has invalid {part} item count")
        result[part] = item
    return result


def _approved_items(
    dictionary_rows: Sequence[Mapping[str, object]],
    part_config: Mapping[str, object],
    part: str,
    rows: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, ...], str]:
    selector = _mapping(
        part_config.get("dictionary_selector"), f"tables.{part}.dictionary_selector"
    )
    modules = set(_strings(selector.get("modules"), f"tables.{part}.dictionary_selector.modules"))
    pages = (
        set(_strings(selector.get("pages"), f"tables.{part}.dictionary_selector.pages"))
        if "pages" in selector
        else None
    )
    total = _text(
        selector.get("official_total_column"),
        f"tables.{part}.dictionary_selector.official_total_column",
    )
    expected = selector["expected_item_count"]
    assert isinstance(expected, int)
    item_pattern = re.compile(
        _text(
            selector.get("item_name_regex"),
            f"tables.{part}.dictionary_selector.item_name_regex",
        )
    )
    numeric_fields = {
        str(row.get("ITM_NAME", "")).strip()
        for row in dictionary_rows
        if str(row.get("MOD_NAME", "")).strip() in modules
        and (pages is None or str(row.get("PAG_NAME", "")).strip() in pages)
        and str(row.get("ITM_TYPE", "")).strip() == "NUMBER"
    }
    if total not in numeric_fields:
        raise PPMITargetError(f"PPMI dictionary does not approve the official total for {part}")
    items = tuple(
        sorted(name for name in numeric_fields if name != total and item_pattern.fullmatch(name))
    )
    if len(items) != expected:
        raise PPMITargetError(f"PPMI dictionary item count does not match configured {part} count")
    headers = {str(column) for row in rows for column in row}
    if total not in headers or any(item not in headers for item in items):
        raise PPMITargetError(f"PPMI clinical table lacks configured {part} item or total columns")
    return items, total


def _key(row: Mapping[str, object], subject_column: str, visit_column: str) -> tuple[str, str]:
    subject = str(row.get(subject_column, "")).strip()
    visit = str(row.get(visit_column, "")).strip()
    if not subject or not visit:
        raise PPMITargetError("PPMI clinical table has missing subject or visit values")
    return subject, visit


def _group_rows(
    rows: Sequence[Mapping[str, object]], subject_column: str, visit_column: str
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[_key(row, subject_column, visit_column)].append(row)
    return grouped


def _unique_selections(
    grouped: Mapping[tuple[str, str], Sequence[Mapping[str, object]]], part: str
) -> dict[tuple[str, str], _Selection]:
    return {
        key: _Selection(rows[0], None) if len(rows) == 1 else _Selection(None, f"duplicate_{part}")
        for key, rows in grouped.items()
    }


def _state_value(
    row: Mapping[str, object], column: str, fields: Mapping[str, object]
) -> str | None:
    values = _mapping(fields.get(column), f"part_iii_state.fields.{column}")
    off_values = set(
        _state_strings(values.get("off_values"), f"part_iii_state.fields.{column}.off_values")
    )
    on_values = set(
        _state_strings(values.get("on_values"), f"part_iii_state.fields.{column}.on_values")
    )
    value = str(row.get(column, "")).strip()
    if value in off_values and value not in on_values:
        return "off"
    if value in on_values and value not in off_values:
        return "on"
    return None


def _state(
    row: Mapping[str, object], fields: Mapping[str, object], primary_field: str
) -> str | None:
    primary = _state_value(row, primary_field, fields)
    if primary is not None:
        return primary
    votes: set[str] = set()
    for column, _definition in fields.items():
        if column == primary_field:
            continue
        state = _state_value(row, str(column), fields)
        if state is not None:
            votes.add(state)
    return next(iter(votes)) if len(votes) == 1 else None


def _part_iii_selections(
    grouped: Mapping[tuple[str, str], Sequence[Mapping[str, object]]], config: Mapping[str, object]
) -> tuple[dict[str, dict[tuple[str, str], _Selection]], dict[str, object]]:
    state_config = _mapping(config.get("part_iii_state"), "part_iii_state")
    fields = _mapping(state_config.get("fields"), "part_iii_state.fields")
    primary_field = _text(state_config.get("primary_field"), "part_iii_state.primary_field")
    if primary_field not in fields:
        raise PPMITargetError("PPMI target configuration lacks PDSTATE primary field")
    policies = _mapping(state_config.get("policies"), "part_iii_state.policies")
    if set(policies) != set(_POLICIES) or not all(
        bool(_mapping(policies[name], f"part_iii_state.policies.{name}").get("enabled"))
        for name in _POLICIES
    ):
        raise PPMITargetError("PPMI target configuration must enable all Part III policies")
    if not fields:
        raise PPMITargetError("PPMI target configuration lacks part_iii_state.fields")
    result: dict[str, dict[tuple[str, str], _Selection]] = {policy: {} for policy in _POLICIES}
    duplicate_groups = 0
    ambiguous_state_groups = 0
    ambiguous_groups_by_policy = {"prefer_off": 0, "prefer_on": 0}
    for key, rows in grouped.items():
        if len(rows) == 1:
            for policy in _POLICIES:
                result[policy][key] = _Selection(rows[0], None)
            continue
        duplicate_groups += 1
        result["unique_only"][key] = _Selection(None, "duplicate_part_iii")
        group_is_ambiguous = False
        for policy, preferred_state in (("prefer_off", "off"), ("prefer_on", "on")):
            matches = [row for row in rows if _state(row, fields, primary_field) == preferred_state]
            if len(matches) == 1:
                result[policy][key] = _Selection(matches[0], None)
            else:
                result[policy][key] = _Selection(None, "ambiguous_part_iii_state")
                ambiguous_groups_by_policy[policy] += 1
                group_is_ambiguous = True
        if group_is_ambiguous:
            ambiguous_state_groups += 1
    return result, {
        "duplicate_subject_visit_groups": duplicate_groups,
        "ambiguous_preference_groups": ambiguous_state_groups,
        "ambiguous_preference_groups_by_policy": ambiguous_groups_by_policy,
    }


def _score(row: Mapping[str, object], items: Sequence[str], official_total: str) -> float | None:
    values: list[float] = []
    for item in items:
        value = row.get(item)
        try:
            parsed = float(str(value).strip())
        except (TypeError, ValueError):
            return None
        values.append(parsed)
    computed = sum(values)
    try:
        official = float(str(row.get(official_total, "")).strip())
    except (TypeError, ValueError):
        return None
    return computed if official == computed else None


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        try:
            return datetime.strptime(value.strip(), "%m/%d/%Y").date()
        except ValueError:
            return None


def _date_precision(value: object) -> str:
    """Classify an approved clinical date representation without retaining it."""
    if not isinstance(value, str) or not value.strip():
        return "missing_or_invalid"
    normalized = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized) and _parse_date(normalized) is not None:
        return "iso_day"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", normalized) and _parse_date(normalized) is not None:
        return "mdy_day"
    try:
        datetime.strptime(normalized, "%m/%Y")
    except ValueError:
        return "missing_or_invalid"
    return "month_year"


def _date_precision_distribution(
    rows: Sequence[Mapping[str, object]], date_column: str
) -> dict[str, int]:
    distribution: Counter[str] = Counter()
    for row in rows:
        distribution[_date_precision(row.get(date_column))] += 1
    return {
        precision: distribution[precision]
        for precision in ("iso_day", "mdy_day", "month_year", "missing_or_invalid")
    }


def _baseline_clinical_date(
    scored: Mapping[str, Mapping[tuple[str, str], tuple[float, date | None]]],
    candidate_parts: Sequence[str],
    subject: str,
    baseline: str,
) -> tuple[date | None, str | None]:
    dates = [scored[part][(subject, baseline)][1] for part in candidate_parts]
    if any(value is None for value in dates):
        return None, "missing_or_ambiguous_baseline_clinical_date"
    concrete_dates = {value for value in dates if value is not None}
    if len(concrete_dates) != 1:
        return None, "missing_or_ambiguous_baseline_clinical_date"
    return next(iter(concrete_dates)), None


def _trimodal_imaging(
    imaging_manifest: Sequence[Mapping[str, object]], baseline_visit: str
) -> dict[str, date | None]:
    result: dict[str, date | None] = {}
    for row in imaging_manifest:
        subject = str(row.get("subject_id", "")).strip()
        if not subject or str(row.get("visit_id", "")).strip() != baseline_visit:
            continue
        if not all(
            bool(row.get(field)) for field in ("t1_available", "fmri_available", "dwi_available")
        ):
            continue
        if row.get("row_status") not in (None, "included"):
            continue
        if subject in result:
            result[subject] = None
        else:
            result[subject] = _parse_date(row.get("imaging_date"))
    return result


def _distribution(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {"count": len(values), "min": min(values), "max": max(values), "mean": mean(values)}


def _resolve_horizons(
    target_config: Mapping[str, object], code_list_rows: Sequence[Mapping[str, object]]
) -> dict[str, tuple[str, ...]]:
    configured = _mapping(target_config.get("month_horizons"), "month_horizons")
    event_rows: list[tuple[str, str]] = []
    for row in code_list_rows:
        if str(row.get("ITM_NAME", "")).strip() != "EVENT_ID":
            continue
        code = str(row.get("CODE", "")).strip()
        if code:
            event_rows.append((code, str(row.get("DECODE", "")).strip()))
    result: dict[str, tuple[str, ...]] = {}
    for horizon, config_key in (
        ("baseline", "baseline"),
        ("12", "month12"),
        ("24", "month24"),
        ("48", "month48"),
    ):
        definition = _mapping(configured.get(config_key), f"month_horizons.{config_key}")
        selector = _text(definition.get("selector"), f"month_horizons.{config_key}.selector")
        event_ids: tuple[str, ...]
        if selector == "code_list_event_id":
            event_id = _text(definition.get("event_id"), f"month_horizons.{config_key}.event_id")
            event_ids = (event_id,) if any(code == event_id for code, _ in event_rows) else ()
        elif selector == "code_list_month":
            month = definition.get("month")
            prefix = _text(
                definition.get("event_id_prefix"),
                f"month_horizons.{config_key}.event_id_prefix",
            )
            if isinstance(month, bool) or not isinstance(month, int) or month < 1:
                raise PPMITargetError(f"PPMI target configuration has invalid {config_key} month")
            event_ids = tuple(
                sorted(
                    {
                        code
                        for code, decode in event_rows
                        if code.startswith(prefix)
                        and (
                            match := re.search(
                                r"\bmonth\b[\s:;,_()\-]*([0-9]+)\b",
                                decode,
                                flags=re.IGNORECASE,
                            )
                        )
                        is not None
                        and int(match.group(1)) == month
                    }
                )
            )
        else:
            raise PPMITargetError(f"PPMI target configuration has invalid {config_key} selector")
        if not event_ids:
            raise PPMITargetError(f"PPMI code list cannot resolve {horizon} month horizon")
        result[horizon] = event_ids
    return result


def _candidates(target_config: Mapping[str, object]) -> dict[str, tuple[str, ...]]:
    configured = _mapping(target_config.get("candidates"), "candidates")
    result: dict[str, tuple[str, ...]] = {}
    for candidate, required_parts in _CANDIDATES.items():
        definition = _mapping(configured.get(candidate), f"candidates.{candidate}")
        parts = _strings(definition.get("parts"), f"candidates.{candidate}.parts")
        if parts != required_parts:
            raise PPMITargetError(f"PPMI target configuration has invalid {candidate} composition")
        result[candidate] = parts
    return result


def _branch(
    candidate_parts: Sequence[str],
    selections: Mapping[str, Mapping[tuple[str, str], _Selection]],
    items: Mapping[str, Sequence[str]],
    official_totals: Mapping[str, str],
    horizons: Mapping[str, tuple[str, ...]],
    imaging: Mapping[str, date | None],
    date_column: str,
    target_confirmed: bool,
    policy_confirmed: bool,
    task_thresholds: Mapping[str, int],
) -> dict[str, dict[str, object]]:
    all_subjects = {subject for part in candidate_parts for subject, _ in selections[part]}
    baseline_codes = horizons["baseline"]
    if len(baseline_codes) != 1:
        raise PPMITargetError("PPMI code list has ambiguous baseline horizon")
    baseline = baseline_codes[0]
    scored: dict[str, dict[tuple[str, str], tuple[float, date | None]]] = {}
    invalid_scores: dict[str, set[tuple[str, str]]] = {}
    for part in candidate_parts:
        scored[part] = {}
        invalid_scores[part] = set()
        for key, selection in selections[part].items():
            if selection.row is None:
                continue
            total = _score(selection.row, items[part], official_totals[part])
            if total is None:
                invalid_scores[part].add(key)
                continue
            scored[part][key] = (total, _parse_date(selection.row.get(date_column)))
    result: dict[str, dict[str, object]] = {}
    baseline_complete = {
        subject
        for subject in all_subjects
        if all((subject, baseline) in scored[part] for part in candidate_parts)
    }
    baseline_intervals: list[int] = []
    baseline_date_reasons: Counter[str] = Counter()
    for subject in baseline_complete.intersection(imaging):
        imaging_date = imaging[subject]
        clinical_date, reason = _baseline_clinical_date(scored, candidate_parts, subject, baseline)
        if reason is not None:
            baseline_date_reasons[reason] += 1
        if imaging_date is not None and clinical_date is not None:
            baseline_intervals.append(abs((imaging_date - clinical_date).days))
    result["baseline"] = {
        "clinical_complete_subject_count": len(baseline_complete),
        "baseline_trimodal_target_subject_count": len(baseline_complete.intersection(imaging)),
        "independent_subject_count": len(baseline_complete.intersection(imaging)),
        "imaging_clinical_interval_days": _distribution(baseline_intervals),
        "exclusion_reasons": {
            "missing_baseline_clinical": len(all_subjects.difference(baseline_complete)),
            "missing_baseline_trimodal_imaging": len(baseline_complete.difference(imaging)),
            **dict(sorted(baseline_date_reasons.items())),
        },
    }
    for horizon_name in ("12", "24", "48"):
        followup_codes = horizons[horizon_name]
        changes: list[float] = []
        complete: set[str] = set()
        clinical_dates: dict[str, date | None] = {}
        clinical_date_reasons: Counter[str] = Counter()
        exclusions: Counter[str] = Counter()
        for subject in all_subjects:
            base_key = (subject, baseline)
            base_parts = [scored[part].get(base_key) for part in candidate_parts]
            if any(value is None for value in base_parts):
                exclusions["missing_or_ambiguous_baseline_clinical"] += 1
                continue
            matched_followups = tuple(
                visit
                for visit in followup_codes
                if all((subject, visit) in scored[part] for part in candidate_parts)
            )
            if len(matched_followups) > 1:
                exclusions["ambiguous_followup_visit"] += 1
                continue
            if not matched_followups:
                exclusions["missing_or_ambiguous_followup_clinical"] += 1
                continue
            followup = matched_followups[0]
            followup_key = (subject, followup)
            followup_parts = [scored[part].get(followup_key) for part in candidate_parts]
            if any(value is None for value in followup_parts):
                exclusions["missing_or_ambiguous_followup_clinical"] += 1
                continue
            base_total = sum(value[0] for value in base_parts if value is not None)
            followup_total = sum(value[0] for value in followup_parts if value is not None)
            changes.append(followup_total - base_total)
            complete.add(subject)
            clinical_date, reason = _baseline_clinical_date(
                scored, candidate_parts, subject, baseline
            )
            clinical_dates[subject] = clinical_date
            if reason is not None:
                clinical_date_reasons[reason] += 1
        trimodal_complete = complete.intersection(imaging)
        exclusions["missing_baseline_trimodal_imaging"] += len(complete.difference(imaging))
        intervals: list[int] = []
        for subject in trimodal_complete:
            imaging_date = imaging[subject]
            clinical_date = clinical_dates[subject]
            if imaging_date is not None and clinical_date is not None:
                intervals.append(abs((imaging_date - clinical_date).days))
        exclusions["missing_imaging_or_clinical_date"] += len(trimodal_complete) - len(intervals)
        exclusions.update(clinical_date_reasons)
        result[horizon_name] = {
            "clinical_complete_subject_count": len(complete),
            "baseline_trimodal_target_subject_count": len(trimodal_complete),
            "independent_subject_count": len(trimodal_complete),
            "ambiguous_subject_count": sum(
                1
                for subject in all_subjects
                if any(
                    selections[part].get((subject, visit), _Selection(None, None)).reason
                    == "ambiguous_part_iii_state"
                    for part in candidate_parts
                    for visit in (baseline, *followup_codes)
                )
            ),
            "target_distribution": _distribution(changes),
            "imaging_clinical_interval_days": _distribution(intervals),
            "exclusion_reasons": dict(sorted(exclusions.items())),
        }
    basis_value = result["24"]["independent_subject_count"]
    if isinstance(basis_value, bool) or not isinstance(basis_value, int):
        raise PPMITargetError("PPMI 24-month branch has invalid independent subject count")
    basis_count = basis_value
    branch_gate = evaluate_task_gate(
        basis_count,
        target_confirmed=target_confirmed,
        part_iii_state_policy_confirmed=policy_confirmed,
        stress_test_threshold=task_thresholds["stress_test"],
        ready_threshold=task_thresholds["ready"],
    ).as_dict() | {
        "basis_horizon": "24",
        "basis_independent_subject_count": basis_count,
    }
    for horizon_name in ("12", "24", "48"):
        result[horizon_name]["task_gate"] = dict(branch_gate)
    return result


def audit_ppmi_targets(
    clinical_tables: Mapping[str, Sequence[Mapping[str, object]]],
    dictionary_rows: Sequence[Mapping[str, object]],
    target_config: Mapping[str, object],
    imaging_manifest: Sequence[Mapping[str, object]],
    code_list_rows: Sequence[Mapping[str, object]],
) -> PPMITargetAuditResult:
    """Audit all candidate-target and Part III policy branches without selecting one."""
    subject_column = _text(target_config.get("subject_id_column"), "subject_id_column")
    visit_column = _text(target_config.get("visit_column"), "visit_column")
    date_column = _text(target_config.get("date_column"), "date_column")
    if target_config.get("change_direction") != "followup_total - baseline_total":
        raise PPMITargetError("PPMI target configuration has unsupported change_direction")
    horizons = _resolve_horizons(target_config, code_list_rows)
    part_configs = _part_configs(target_config)
    grouped: dict[str, dict[tuple[str, str], list[Mapping[str, object]]]] = {}
    approved_items: dict[str, tuple[str, ...]] = {}
    official_totals: dict[str, str] = {}
    for part, config in part_configs.items():
        source = _text(config.get("source"), f"tables.{part}.source")
        rows = clinical_tables.get(source)
        if rows is None or isinstance(rows, str | bytes):
            raise PPMITargetError(f"PPMI clinical logical table {source} is unavailable")
        approved_items[part], official_totals[part] = _approved_items(
            dictionary_rows, config, part, rows
        )
        grouped[part] = _group_rows(rows, subject_column, visit_column)
    date_precision_distribution = _date_precision_distribution(
        [row for rows in clinical_tables.values() for row in rows], date_column
    )
    part_iii_baseline_date_precision_distribution = _date_precision_distribution(
        [
            row
            for (_, visit), grouped_rows in grouped["part_iii"].items()
            if visit == horizons["baseline"][0]
            for row in grouped_rows
        ],
        date_column,
    )
    interval_status = (
        "UNAVAILABLE_MONTH_ONLY_CLINICAL_DATE"
        if date_precision_distribution["month_year"]
        and not (date_precision_distribution["iso_day"] + date_precision_distribution["mdy_day"])
        else "AVAILABLE_OR_PARTIAL"
    )
    p3_by_policy, duplicate_audit = _part_iii_selections(grouped["part_iii"], target_config)
    non_p3 = {
        part: _unique_selections(grouped[part], part) for part in _PARTS if part != "part_iii"
    }
    if len(horizons["baseline"]) != 1:
        raise PPMITargetError("PPMI code list has ambiguous baseline horizon")
    imaging = _trimodal_imaging(imaging_manifest, horizons["baseline"][0])
    selection_config = target_config.get("selection")
    selected_target: str | None = None
    target_definition: str | None = None
    selected_policy: str | None = None
    secondary_targets: list[str] = []
    sensitivity_policies: list[str] = []
    if selection_config is not None:
        if not isinstance(selection_config, Mapping):
            raise PPMITargetError("PPMI target selection is invalid")
        selected_target = selection_config.get("primary_target")
        target_definition = selection_config.get("target_definition")
        selected_policy = selection_config.get("primary_policy")
        secondary = selection_config.get("secondary_targets")
        sensitivities = selection_config.get("sensitivity_policies")
        if (
            selected_target != "candidate_A"
            or target_definition != "MDS-UPDRS Part III follow-up score minus baseline score"
            or selected_policy != "prefer_off"
            or secondary != ["candidate_B"]
            or sensitivities != ["unique_only", "prefer_on"]
        ):
            raise PPMITargetError("PPMI target selection is unsupported")
        secondary_targets = list(secondary)
        sensitivity_policies = list(sensitivities)
    target_confirmed = bool(target_config.get("target_confirmed", False))
    policy_config = _mapping(target_config.get("part_iii_state"), "part_iii_state")
    policy_confirmed = bool(policy_config.get("confirmed", False))
    if (target_confirmed or policy_confirmed) and selection_config is None:
        raise PPMITargetError("confirmed PPMI target requires an explicit selection")
    threshold_config = _mapping(target_config.get("task_thresholds"), "task_thresholds")
    task_thresholds = {name: threshold_config.get(name) for name in ("stress_test", "ready")}
    if task_thresholds != {"stress_test": 120, "ready": 180}:
        raise PPMITargetError("PPMI target configuration has invalid task thresholds")
    candidates = _candidates(target_config)
    branches: dict[str, dict[str, dict[str, dict[str, object]]]] = {}
    for candidate, candidate_parts in candidates.items():
        branches[candidate] = {}
        for policy in _POLICIES:
            selections = non_p3 | {"part_iii": p3_by_policy[policy]}
            branches[candidate][policy] = _branch(
                candidate_parts,
                selections,
                approved_items,
                official_totals,
                horizons,
                imaging,
                date_column,
                target_confirmed,
                policy_confirmed,
                {"stress_test": 120, "ready": 180},
            )
    return PPMITargetAuditResult(
        audit={
            "status": "PART_III_STATE_POLICY_REQUIRED"
            if not policy_confirmed
            else "TARGET_CONFIRMATION_REQUIRED"
            if not target_confirmed
            else "READY_FOR_USER_SELECTED_TASK",
            "change_direction": target_config["change_direction"],
            "primary_target": selected_target,
            "target_definition": target_definition,
            "primary_policy": selected_policy,
            "secondary_targets": secondary_targets,
            "sensitivity_policies": sensitivity_policies,
            "candidate_definitions": {
                "candidate_A": "part_iii_total_change",
                "candidate_B": (
                    "part_i_clinician_plus_part_i_patient_plus_part_ii_plus_part_iii_total_change"
                ),
            },
            "part_iii_duplicate_audit": duplicate_audit,
            "coverage_horizons": ("baseline", "12", "24", "48"),
            "resolved_horizon_event_ids": horizons,
            "clinical_date_precision_distribution": date_precision_distribution,
            "part_iii_baseline_date_precision_distribution": (
                part_iii_baseline_date_precision_distribution
            ),
            "imaging_clinical_interval_status": interval_status,
        },
        branches=branches,
    )
