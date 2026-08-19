from __future__ import annotations

import torch

from canospar.api.m3 import run_m3
from canospar.contracts.bands import BandSpec


def test_m3_does_not_call_an_eigensolver(
    m2_bundle, m2_context, coordinate_spec, monkeypatch
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("M3 must consume M2 eigenvalues and never eigendecompose")

    monkeypatch.setattr(torch.linalg, "eigh", forbidden)
    monkeypatch.setattr(torch.linalg, "eigvalsh", forbidden)

    result = run_m3(m2_bundle, coordinate_spec, BandSpec(3), m2_context)

    assert result.receipt is not None
