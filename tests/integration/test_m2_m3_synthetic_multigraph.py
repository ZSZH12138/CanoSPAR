from __future__ import annotations

import torch

from canospar.api.m2 import run_m2
from canospar.api.m3 import run_m3
from canospar.contracts.bands import BandSpec
from canospar.contracts.spectral import CanonicalCoordinateSpec
from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec


def test_m2_to_m3_synthetic_multigraph_preserves_graph_order_and_lineage() -> None:
    context = _context()
    m2_bundle = run_m2(_artifact(), _spec(), context)
    coordinate_spec = CanonicalCoordinateSpec(
        method="empirical_mid_cdf",
        parameters={"tie_atol": 0.0, "tie_rtol": 0.0, "empty_band_policy": "fail"},
    )

    m3_bundle = run_m3(m2_bundle, coordinate_spec, BandSpec(2), context)

    assert [item.graph_key.modality for item in m3_bundle.spectra] == ["dmri", "fmri", "smri"]
    assert all(
        torch.all((item.u_coordinate > 0) & (item.u_coordinate < 1)) for item in m3_bundle.spectra
    )
    assert all(
        torch.all(item.u_coordinate[1:] >= item.u_coordinate[:-1]) for item in m3_bundle.spectra
    )
    assert m3_bundle.meta.producer_module == "M3"
    assert m3_bundle.receipt is not None
    assert m3_bundle.receipt.module_id == "M3"
    assert m3_bundle.receipt.canonical_status.value == "PASS"
    assert m3_bundle.evidence["m4_executed"] == "false"
