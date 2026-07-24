"""Unit tests for the deterministic CPU-only smoke graph components."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
import torch
from torch_geometric.data import Batch

from canospar.utils import smoke_test
from canospar.utils.smoke_test import batch_smoke_graphs, build_smoke_graphs

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_build_smoke_graphs_has_the_three_required_cpu_graphs() -> None:
    graphs = build_smoke_graphs(seed=17, num_nodes=4, feature_dim=3)

    assert [(graph.modality, graph.relation) for graph in graphs] == [
        ("smri", "morphological_similarity"),
        ("dmri", "structural_connectivity"),
        ("fmri", "positive_functional_connectivity"),
    ]
    assert all(graph.x.device.type == "cpu" for graph in graphs)
    assert all(graph.num_nodes == 4 and graph.x.shape == (4, 3) for graph in graphs)
    assert all(graph.edge_index.shape == (2, 6) for graph in graphs)
    assert all(graph.edge_weight.shape == (6,) for graph in graphs)
    assert all(graph.to_pyg_data().num_nodes == 4 for graph in graphs)


def test_build_smoke_graphs_is_reproducible_for_a_seed() -> None:
    first = build_smoke_graphs(seed=23, num_nodes=4, feature_dim=3)
    second = build_smoke_graphs(seed=23, num_nodes=4, feature_dim=3)

    for left, right in zip(first, second, strict=True):
        assert torch.equal(left.x, right.x)
        assert torch.equal(left.edge_index, right.edge_index)
        assert torch.equal(left.edge_weight, right.edge_weight)
        assert left.construction_hash == right.construction_hash


def test_batch_smoke_graphs_uses_a_real_pyg_dataloader_batch() -> None:
    graphs = build_smoke_graphs(seed=5, num_nodes=4, feature_dim=3)

    batch = batch_smoke_graphs(graphs)

    assert isinstance(batch, Batch)
    assert batch.num_graphs == 3
    assert batch.x.shape == (12, 3)
    assert batch.edge_index.shape == (2, 18)
    assert batch.edge_weight.shape == (18,)
    assert batch.batch.shape == (12,)
    assert batch.batch.tolist() == [0] * 4 + [1] * 4 + [2] * 4
    assert batch.ptr.tolist() == [0, 4, 8, 12]
    assert batch.x.device.type == "cpu"


def test_run_smoke_records_contract_version_in_report() -> None:
    output_dir = Path("artifacts") / f"smoke-contract-version-{uuid4().hex}"
    destination = _PROJECT_ROOT / output_dir

    try:
        report = smoke_test.run_smoke([f"paths.output_dir={output_dir.as_posix()}"])
        saved_report = json.loads((destination / "smoke_report.json").read_text(encoding="utf-8"))

        assert report["contract_version"] == saved_report["contract_version"] == "1.1.0"
    finally:
        shutil.rmtree(destination, ignore_errors=True)


def test_run_smoke_does_not_publish_partial_artifacts_on_write_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = Path("artifacts") / f"smoke-write-failure-{uuid4().hex}"
    destination = _PROJECT_ROOT / output_dir

    def fail_provenance_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("injected provenance write failure")

    monkeypatch.setattr(smoke_test, "write_provenance", fail_provenance_write)
    try:
        with pytest.raises(OSError, match="injected provenance write failure"):
            smoke_test.run_smoke([f"paths.output_dir={output_dir.as_posix()}"])

        assert not any(
            (destination / file_name).exists()
            for file_name in (
                "resolved_config.yaml",
                "provenance.json",
                "smoke_report.json",
            )
        )
    finally:
        shutil.rmtree(destination, ignore_errors=True)
