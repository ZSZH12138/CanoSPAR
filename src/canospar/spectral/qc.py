"""Train-only QC fitting and immutable transform state."""

from __future__ import annotations

import math
import warnings
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import cast

import numpy as np

from canospar.contracts.base import FittedQCState, QCVector, ScienceContext, require_non_empty_text
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec, NormalizedQCArtifact

from .lineage import canonical_json_hash, ensure_mapping, make_meta, numerics_profile


class _QCFeatureState(tuple[float, float, float, float]):
    """Four-value QC state tuple carrying its fit-time diagnostic bit."""

    constant_feature: bool

    def __new__(
        cls,
        values: tuple[float, float, float, float],
        *,
        constant_feature: bool,
    ) -> _QCFeatureState:
        state = super().__new__(cls, values)
        state.constant_feature = constant_feature
        return state


def _finite_value(value: object, field_name: str) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ContractViolation(f"{field_name} must be a finite number")
    return result


def qc_features(spec: M2Spec) -> tuple[str, ...]:
    parameters = spec.parameters
    feature_names = parameters.get("qc_features")
    if isinstance(feature_names, str | bytes) or not isinstance(feature_names, Sequence):
        raise ContractViolation("qc_features must be a non-empty sequence of names")
    result = tuple(feature_names)
    if not result or any(not isinstance(name, str) or not name.strip() for name in result):
        raise ContractViolation("qc_features must contain non-empty strings")
    if len(set(result)) != len(result):
        raise ContractViolation("qc_features must not contain duplicates")
    return tuple(cast(str, name) for name in result)


def _qc_parameters(spec: M2Spec) -> tuple[tuple[str, ...], float, float, float]:
    features = qc_features(spec)
    required = ("winsor_lower_quantile", "winsor_upper_quantile", "robust_scale_epsilon")
    if any(name not in spec.parameters for name in required):
        raise ContractViolation("QC winsor quantiles and robust_scale_epsilon must be explicit")
    lower = _finite_value(spec.parameters["winsor_lower_quantile"], required[0])
    upper = _finite_value(spec.parameters["winsor_upper_quantile"], required[1])
    epsilon = _finite_value(spec.parameters["robust_scale_epsilon"], required[2])
    if not 0 <= lower < upper <= 1:
        raise ContractViolation("winsor quantiles must satisfy 0 <= lower < upper <= 1")
    if epsilon <= 0:
        raise ContractViolation("robust_scale_epsilon must be positive")
    return features, lower, upper, epsilon


def _validate_qc_vector(qc: QCVector, field_name: str) -> Mapping[str, object]:
    values = ensure_mapping(qc, field_name)
    for name, value in values.items():
        _finite_value(value, f"{field_name}[{name!r}]")
    return values


def fitted_qc_state_hash(state: FittedQCState) -> str:
    values = ensure_mapping(state, "state")
    serializable: dict[str, tuple[float, float, float, float]] = {}
    for feature, raw_state in values.items():
        if isinstance(raw_state, str | bytes) or not isinstance(raw_state, Sequence):
            raise ContractViolation("each fitted QC feature state must be a four-value sequence")
        if len(raw_state) != 4:
            raise ContractViolation("each fitted QC feature state must contain four values")
        serializable[feature] = tuple(
            _finite_value(value, f"state[{feature!r}]") for value in raw_state
        )  # type: ignore[assignment]
    return canonical_json_hash(serializable)


def fit_qc_state(train_qc: Sequence[QCVector], spec: M2Spec) -> FittedQCState:
    if isinstance(train_qc, str | bytes) or not isinstance(train_qc, Sequence) or not train_qc:
        raise ContractViolation("train_qc must be a non-empty sequence")
    features, lower, upper, epsilon = _qc_parameters(spec)
    validated = [_validate_qc_vector(vector, "train_qc") for vector in train_qc]
    result: dict[str, tuple[float, float, float, float]] = {}
    for feature in features:
        observed = np.asarray(
            [
                _finite_value(values[feature], f"train_qc[{feature!r}]")
                for values in validated
                if feature in values
            ],
            dtype=np.float64,
        )
        if observed.size == 0:
            raise ContractViolation(f"all training values are missing for QC feature {feature!r}")
        median = float(np.median(observed))
        imputed = np.asarray(
            [
                median
                if feature not in values
                else _finite_value(values[feature], f"train_qc[{feature!r}]")
                for values in validated
            ],
            dtype=np.float64,
        )
        low, high = (
            float(value) for value in np.quantile(imputed, [lower, upper], method="linear")
        )
        clipped = np.clip(imputed, low, high)
        iqr = float(
            np.quantile(clipped, 0.75, method="linear")
            - np.quantile(clipped, 0.25, method="linear")
        )
        constant_feature = iqr <= epsilon
        scale = iqr if not constant_feature else 1.0
        if constant_feature:
            warnings.warn(
                f"QC_CONSTANT_FEATURE: {feature}",
                UserWarning,
                stacklevel=2,
            )
        result[feature] = _QCFeatureState(
            (median, low, high, scale),
            constant_feature=constant_feature,
        )
    return MappingProxyType(result)


def transform_qc_values(qc: QCVector, state: FittedQCState) -> dict[str, float]:
    values = _validate_qc_vector(qc, "qc")
    state_values = ensure_mapping(state, "state")
    output: dict[str, float] = {}
    for feature in sorted(state_values):
        raw_state = state_values[feature]
        if (
            isinstance(raw_state, str | bytes)
            or not isinstance(raw_state, Sequence)
            or len(raw_state) != 4
        ):
            raise ContractViolation("each fitted QC feature state must contain four values")
        median, low, high, scale = (
            _finite_value(value, f"state[{feature!r}]") for value in raw_state
        )
        if scale <= 0 or low > high:
            raise ContractViolation("fitted QC state has invalid bounds or scale")
        raw_value = (
            median if feature not in values else _finite_value(values[feature], f"qc[{feature!r}]")
        )
        clipped = min(max(raw_value, low), high)
        output[feature] = (clipped - median) / scale
    return output


def qc_issue_codes(state: FittedQCState, spec: M2Spec) -> tuple[str, ...]:
    """Return deterministic receipt diagnostics recoverable from a frozen state."""
    _, _, _, epsilon = _qc_parameters(spec)
    state_values = ensure_mapping(state, "state")
    issues: list[str] = []
    for feature in qc_features(spec):
        if feature not in state_values:
            raise ContractViolation(f"state is missing QC feature {feature!r}")
        raw_state = state_values[feature]
        if isinstance(raw_state, str | bytes) or not isinstance(raw_state, Sequence):
            raise ContractViolation("each fitted QC feature state must contain four values")
        if len(raw_state) != 4:
            raise ContractViolation("each fitted QC feature state must contain four values")
        _, low, high, scale = (_finite_value(value, f"state[{feature!r}]") for value in raw_state)
        if scale <= 0 or low > high:
            raise ContractViolation("fitted QC state has invalid bounds or scale")
        fit_diagnostic = getattr(raw_state, "constant_feature", None)
        if fit_diagnostic is True or (
            fit_diagnostic is None and scale == 1.0 and high - low <= epsilon
        ):
            issues.append("QC_CONSTANT_FEATURE")
    return tuple(dict.fromkeys(issues))


def build_normalized_qc_artifact(
    qc: QCVector,
    state: FittedQCState,
    context: ScienceContext,
    *,
    source_artifact_id: str,
    source_content_hash: str,
    numerics_profile_hash: str | None = None,
) -> NormalizedQCArtifact:
    require_non_empty_text(source_artifact_id, "source_artifact_id")
    require_non_empty_text(source_content_hash, "source_content_hash")
    values = transform_qc_values(qc, state)
    state_hash = fitted_qc_state_hash(state)
    content_hash = canonical_json_hash(values)
    meta = make_meta(
        artifact_type="NormalizedQCArtifact",
        context=context,
        content_sha256=content_hash,
        input_artifact_ids=(source_artifact_id, f"qc-state:{state_hash}"),
        input_content_hashes=(source_content_hash, state_hash),
        numerics_profile_hash=(
            numerics_profile_hash
            if numerics_profile_hash is not None
            else numerics_profile(M2Spec(backend="numpy")).numerics_profile_hash
        ),
    )
    return NormalizedQCArtifact(meta=meta, values=values)
