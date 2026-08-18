"""Numerical semantics that participate in reproducibility identity."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from canospar.contracts.base import _digest_parts, require_non_empty_text
from canospar.contracts.governance import NUMERICS_PROFILE_SCHEMA_VERSION


@dataclass(frozen=True)
class NumericsProfile:
    """Immutable description of the numerical semantics of a computation."""

    schema_version: str = NUMERICS_PROFILE_SCHEMA_VERSION
    python_version: str = ""
    numpy_version: str | None = None
    scipy_version: str | None = None
    torch_version: str | None = None
    dtype: str = ""
    precision_policy: str = ""
    deterministic_algorithms: bool | None = None
    linear_algebra_backend: str | None = None
    eigensolver_backend: str | None = None
    solver_tolerance: float | None = None
    zero_tolerance: float | None = None
    tie_tolerance: float | None = None
    dirichlet_epsilon: float | None = None
    cuda_version: str | None = None
    numerical_backend_version: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("schema_version", "python_version", "dtype", "precision_policy"):
            require_non_empty_text(getattr(self, field_name), field_name)
        for field_name in (
            "numpy_version",
            "scipy_version",
            "torch_version",
            "linear_algebra_backend",
            "eigensolver_backend",
            "cuda_version",
            "numerical_backend_version",
        ):
            value = getattr(self, field_name)
            if value is not None:
                require_non_empty_text(value, field_name)
        if self.deterministic_algorithms is not None and not isinstance(
            self.deterministic_algorithms, bool
        ):
            raise ValueError("deterministic_algorithms must be a bool or None")
        for field_name in (
            "solver_tolerance",
            "zero_tolerance",
            "tie_tolerance",
            "dirichlet_epsilon",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int | float)
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{field_name} must be a finite non-negative number or None")

    @property
    def numerics_profile_hash(self) -> str:
        """Return the canonical hash of all numerical identity fields."""
        return _digest_parts((asdict(self),))


def build_numerics_profile_hash(profile: NumericsProfile) -> str:
    """Build a numerical identity from a validated profile."""
    if not isinstance(profile, NumericsProfile):
        raise TypeError("profile must be NumericsProfile")
    return profile.numerics_profile_hash
