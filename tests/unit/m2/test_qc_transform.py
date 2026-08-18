from __future__ import annotations

import pytest

from canospar.api.m2 import fit_qc_transform, transform_qc
from canospar.contracts.base import ScienceContext
from canospar.contracts.spectral import M2Spec
from canospar.spectral.qc import fitted_qc_state_hash


def _spec() -> M2Spec:
    return M2Spec(
        backend="numpy",
        parameters={
            "qc_features": ["motion", "snr"],
            "winsor_lower_quantile": 0.25,
            "winsor_upper_quantile": 0.75,
            "robust_scale_epsilon": 1e-6,
        },
    )


def test_transform_uses_frozen_state_for_missing_and_extreme_test_values() -> None:
    state = fit_qc_transform(
        [{"motion": 1.0, "snr": 10.0}, {"motion": 2.0, "snr": 20.0}],
        _spec(),
    )
    state_hash = fitted_qc_state_hash(state)
    context = ScienceContext(science_config_hash="qc-config")
    transformed = transform_qc(
        {"motion": 1e9},
        state,
        context,
        source_artifact_id="sample-a",
        source_content_hash="sample-content-a",
    )

    assert set(transformed.values) == {"motion", "snr"}
    assert transformed.values["motion"] == pytest.approx(1.0)
    assert transformed.values["snr"] == pytest.approx(0.0)
    assert state_hash == fitted_qc_state_hash(state)
    assert state_hash in transformed.meta.input_content_hashes
    assert transformed.meta.input_artifact_ids[0] == "sample-a"
