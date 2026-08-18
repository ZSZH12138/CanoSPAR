from __future__ import annotations

import pytest

from canospar.api.m2 import fit_qc_transform
from canospar.contracts.errors import ContractViolation
from canospar.contracts.spectral import M2Spec
from canospar.spectral.qc import fitted_qc_state_hash


def _spec(**overrides: object) -> M2Spec:
    parameters: dict[str, object] = {
        "qc_features": ["motion", "snr"],
        "winsor_lower_quantile": 0.25,
        "winsor_upper_quantile": 0.75,
        "robust_scale_epsilon": 1e-6,
    }
    parameters.update(overrides)
    return M2Spec(backend="numpy", parameters=parameters)


def test_qc_fit_is_train_only_winsorized_and_immutable() -> None:
    state = fit_qc_transform(
        [
            {"motion": 1.0, "snr": 10.0},
            {"motion": 2.0, "snr": 20.0},
            {"motion": 3.0, "snr": 30.0},
            {"motion": 4.0, "snr": 40.0},
        ],
        _spec(),
    )

    assert state["motion"][0] == 2.5
    assert state["motion"][1] == pytest.approx(1.75)
    assert state["motion"][2] == pytest.approx(3.25)
    assert state["motion"][3] == pytest.approx(1.125)
    assert fitted_qc_state_hash(state) == fitted_qc_state_hash(dict(state))
    with pytest.raises(TypeError):
        state["motion"] = (0.0, 0.0, 0.0, 1.0)  # type: ignore[index]


def test_qc_fit_imputes_missing_training_keys_before_winsorization() -> None:
    state = fit_qc_transform(
        [{"motion": 0.0}, {"motion": 10.0}, {}, {}],
        _spec(qc_features=["motion"]),
    )

    assert state["motion"] == pytest.approx((5.0, 3.75, 6.25, 0.625))


@pytest.mark.parametrize(
    "spec",
    [
        M2Spec(backend="numpy"),
        _spec(winsor_lower_quantile=0.8),
        _spec(winsor_upper_quantile=0.1),
        _spec(robust_scale_epsilon=0.0),
        _spec(qc_features=[]),
    ],
)
def test_qc_fit_requires_explicit_valid_configuration(spec: M2Spec) -> None:
    with pytest.raises(ContractViolation):
        fit_qc_transform([{"motion": 1.0, "snr": 2.0}], spec)


def test_qc_fit_rejects_all_missing_and_nonfinite_values() -> None:
    with pytest.raises(ContractViolation, match="all training"):
        fit_qc_transform([{"snr": 2.0}, {"snr": 3.0}], _spec(qc_features=["motion"]))
    with pytest.raises(ContractViolation):
        fit_qc_transform([{"motion": None, "snr": 2.0}], _spec())
    with pytest.raises(ContractViolation):
        fit_qc_transform([{"motion": float("nan"), "snr": 2.0}], _spec())


def test_constant_feature_warns_and_uses_unit_scale() -> None:
    with pytest.warns(UserWarning, match="QC_CONSTANT_FEATURE"):
        state = fit_qc_transform(
            [{"motion": 1.0}, {"motion": 1.0}],
            _spec(qc_features=["motion"]),
        )
    assert state["motion"][3] == 1.0
