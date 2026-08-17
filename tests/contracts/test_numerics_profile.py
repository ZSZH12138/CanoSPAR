from dataclasses import FrozenInstanceError

import pytest

from canospar.contracts.base import (
    ScienceContext,
    build_reproduction_key,
    build_science_key,
)
from canospar.runtime.numerics import NumericsProfile, build_numerics_profile_hash
from canospar.runtime.profile import RuntimeProfile


def make_numerics_profile(**overrides: object) -> NumericsProfile:
    values: dict[str, object] = {
        "python_version": "3.11.9",
        "numpy_version": "2.2.0",
        "scipy_version": "1.15.0",
        "torch_version": "2.6.0",
        "dtype": "float64",
        "precision_policy": "strict-float64",
        "deterministic_algorithms": True,
        "linear_algebra_backend": "cpu-openblas",
        "eigensolver_backend": "scipy.linalg.eigh",
        "solver_tolerance": 1e-8,
        "cuda_version": None,
        "numerical_backend_version": "openblas-0.3.28",
    }
    values.update(overrides)
    return NumericsProfile(**values)


def science_key_for(runtime: RuntimeProfile) -> str:
    context = ScienceContext(science_config_hash="config-a")
    return build_science_key(
        context,
        ("input-a",),
        "M2",
        runtime_profile_id=runtime.profile_id,
    )


def test_numerics_profile_is_immutable() -> None:
    profile = make_numerics_profile()

    assert profile.numerics_profile_hash == build_numerics_profile_hash(profile)

    with pytest.raises(FrozenInstanceError):
        profile.dtype = "float32"  # type: ignore[misc]


def test_worker_count_does_not_change_science_key() -> None:
    assert science_key_for(RuntimeProfile(profile_id="workers-4", worker_count=4)) == (
        science_key_for(RuntimeProfile(profile_id="workers-16", worker_count=16))
    )


def test_gpu_count_does_not_change_science_key() -> None:
    assert science_key_for(RuntimeProfile(profile_id="gpu-2", gpu_count=2)) == (
        science_key_for(RuntimeProfile(profile_id="gpu-8", gpu_count=8))
    )


def test_server_change_does_not_change_science_key() -> None:
    assert science_key_for(RuntimeProfile(profile_id="server-a", server_class="linux")) == (
        science_key_for(RuntimeProfile(profile_id="server-b", server_class="windows"))
    )


def test_runtime_profile_does_not_change_reproduction_key_when_numerics_unchanged() -> None:
    profile = make_numerics_profile()
    context = ScienceContext(science_config_hash="config-a")
    science_a = build_science_key(
        context,
        ("input-a",),
        "M2",
        runtime_profile_id=RuntimeProfile(profile_id="server-a", worker_count=4).profile_id,
    )
    science_b = build_science_key(
        context,
        ("input-a",),
        "M2",
        runtime_profile_id=RuntimeProfile(profile_id="server-b", worker_count=16).profile_id,
    )

    assert build_reproduction_key(science_a, "impl-a", profile.numerics_profile_hash) == (
        build_reproduction_key(science_b, "impl-a", profile.numerics_profile_hash)
    )


def test_dtype_change_changes_numerics_hash() -> None:
    assert build_numerics_profile_hash(make_numerics_profile()) != build_numerics_profile_hash(
        make_numerics_profile(dtype="float32")
    )


def test_eigensolver_backend_change_changes_numerics_hash() -> None:
    assert build_numerics_profile_hash(make_numerics_profile()) != build_numerics_profile_hash(
        make_numerics_profile(eigensolver_backend="torch.linalg.eigh")
    )


def test_solver_tolerance_change_changes_numerics_hash() -> None:
    assert build_numerics_profile_hash(make_numerics_profile()) != build_numerics_profile_hash(
        make_numerics_profile(solver_tolerance=1e-4)
    )


def test_numerics_change_changes_reproduction_key() -> None:
    science_key = science_key_for(RuntimeProfile(profile_id="server-a"))
    profile_a = make_numerics_profile()
    profile_b = make_numerics_profile(dtype="float32")

    assert build_reproduction_key(
        science_key,
        "impl-a",
        build_numerics_profile_hash(profile_a),
    ) != build_reproduction_key(
        science_key,
        "impl-a",
        build_numerics_profile_hash(profile_b),
    )
