from __future__ import annotations

import hashlib

import pytest

from canospar.api.m2 import run_m2
from canospar.contracts.base import ScienceContext
from canospar.runtime.numerics import NumericsProfile, build_numerics_profile_hash
from canospar.runtime.profile import RuntimeProfile
from canospar.spectral.lineage import M2_IMPLEMENTATION_HASH
from tests.integration.test_m2_synthetic_multigraph import _artifact, _spec


def _context() -> ScienceContext:
    return ScienceContext(
        science_contract_version="1.1.0",
        science_config_hash="m2-synthetic-config",
        dataset_manifest_hash="synthetic-manifest",
        split_id="synthetic-outer-0",
        random_seed=13,
    )


def test_runtime_profile_changes_do_not_change_run_science_identity() -> None:
    first = run_m2(_artifact(), _spec(), _context())
    second = run_m2(_artifact(), _spec(), _context())
    RuntimeProfile(profile_id="cpu-a", cpu_count=2, worker_count=1)
    RuntimeProfile(profile_id="cpu-b", cpu_count=64, worker_count=16, scheduler="batch")
    assert first.science_key == second.science_key


def test_numerical_profile_changes_reproduction_identity_not_science_identity() -> None:
    base = run_m2(_artifact(), _spec(), _context())
    changed_spec = _spec()
    changed_spec = type(changed_spec)(
        backend="numpy",
        parameters={**dict(changed_spec.parameters), "solver_tolerance": 1e-5},
    )
    changed = run_m2(_artifact(), changed_spec, _context())
    assert base.science_key == changed.science_key
    assert base.reproduction_key != changed.reproduction_key


@pytest.mark.parametrize(
    ("parameter", "value"),
    (
        ("zero_tolerance", 1e-3),
        ("tie_tolerance", 1e-3),
        ("dirichlet_epsilon", 1e-3),
    ),
)
def test_all_active_m2_tolerances_change_reproduction_identity(
    parameter: str,
    value: float,
) -> None:
    base = run_m2(_artifact(), _spec(), _context())
    changed_spec = type(_spec())(
        backend="numpy",
        parameters={**dict(_spec().parameters), parameter: value},
    )
    changed = run_m2(_artifact(), changed_spec, _context())

    assert base.science_key == changed.science_key
    assert base.meta.numerics_profile_hash != changed.meta.numerics_profile_hash
    assert base.reproduction_key != changed.reproduction_key


def test_numerics_profile_hash_changes_for_dtype_backend_and_tolerance() -> None:
    base = NumericsProfile(
        python_version="3.11.0",
        dtype="float64",
        precision_policy="strict-float64",
        eigensolver_backend="numpy.linalg.eigh",
        solver_tolerance=1e-8,
    )
    dtype = NumericsProfile(
        python_version="3.11.0",
        dtype="float32",
        precision_policy="strict-float32",
        eigensolver_backend="numpy.linalg.eigh",
        solver_tolerance=1e-8,
    )
    backend = NumericsProfile(
        python_version="3.11.0",
        dtype="float64",
        precision_policy="strict-float64",
        eigensolver_backend="torch.linalg.eigh",
        solver_tolerance=1e-8,
    )
    tolerance = NumericsProfile(
        python_version="3.11.0",
        dtype="float64",
        precision_policy="strict-float64",
        eigensolver_backend="numpy.linalg.eigh",
        solver_tolerance=1e-5,
    )
    hashes = {build_numerics_profile_hash(item) for item in (base, dtype, backend, tolerance)}
    assert len(hashes) == 4


def test_repaired_m2_implementation_identity_is_bumped() -> None:
    old_identity = hashlib.sha256(b"canospar-m2-implementation-v1.1.0").hexdigest()

    assert M2_IMPLEMENTATION_HASH != old_identity
