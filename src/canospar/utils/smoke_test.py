"""Deterministic, CPU-only smoke graphs and their PyG batch."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import torch
from torch_geometric.data import Batch
from torch_geometric.loader import DataLoader

from canospar.data.contracts import GraphData
from canospar.utils.config import compose_config, save_resolved_config
from canospar.utils.hashing import hash_json
from canospar.utils.paths import ensure_safe_output_dir, find_project_root
from canospar.utils.provenance import JsonValue, collect_provenance, write_provenance

_SMOKE_RELATIONS = (
    ("smri", "morphological_similarity"),
    ("dmri", "structural_connectivity"),
    ("fmri", "positive_functional_connectivity"),
)
_ARTIFACT_NAMES = ("resolved_config.yaml", "provenance.json", "smoke_report.json")


def _edge_index(num_nodes: int) -> torch.Tensor:
    source = torch.arange(num_nodes - 1, dtype=torch.long)
    return torch.stack((torch.cat((source, source + 1)), torch.cat((source + 1, source))))


def build_smoke_graphs(seed: int, num_nodes: int, feature_dim: int) -> tuple[GraphData, ...]:
    """Build the three required deterministic CPU graph fixtures."""
    if num_nodes < 2:
        raise ValueError("num_nodes must be at least 2 for smoke graph edges")
    if feature_dim <= 0:
        raise ValueError("feature_dim must be positive")

    generator = torch.Generator(device="cpu").manual_seed(seed)
    edge_index = _edge_index(num_nodes)
    graphs: list[GraphData] = []
    for modality, relation in _SMOKE_RELATIONS:
        x = torch.randn((num_nodes, feature_dim), generator=generator, device="cpu")
        edge_weight = torch.rand(edge_index.size(1), generator=generator, device="cpu")
        construction_hash = hash_json(
            {
                "feature_dim": feature_dim,
                "modality": modality,
                "num_nodes": num_nodes,
                "relation": relation,
                "seed": seed,
                "x": x.tolist(),
                "edge_weight": edge_weight.tolist(),
            }
        )
        graphs.append(
            GraphData(
                x=x,
                edge_index=edge_index,
                edge_weight=edge_weight,
                num_nodes=num_nodes,
                modality=modality,
                relation=relation,
                graph_qc={"generator": "smoke", "random_seed": seed},
                construction_hash=construction_hash,
            )
        )
    return tuple(graphs)


def batch_smoke_graphs(graphs: Sequence[GraphData]) -> Batch:
    """Batch smoke graphs through the real PyG ``DataLoader`` implementation."""
    if not graphs:
        raise ValueError("graphs must not be empty")
    loader = DataLoader(
        [graph.to_pyg_data() for graph in graphs], batch_size=len(graphs), shuffle=False
    )
    batch = next(iter(loader))
    if not isinstance(batch, Batch):
        raise TypeError("PyG DataLoader did not return a Batch")
    return batch


def _write_report(report: dict[str, JsonValue], destination: Path) -> None:
    destination.write_text(
        json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _publish_staged_artifacts(staging_dir: Path, output_dir: Path) -> None:
    """Publish a complete artifact set and restore prior files if publication fails."""
    destinations = tuple(output_dir / name for name in _ARTIFACT_NAMES)
    previous_contents: dict[Path, bytes | None] = {}
    for destination in destinations:
        if destination.exists() and not destination.is_file():
            raise IsADirectoryError(f"Smoke artifact destination is not a file: {destination.name}")
        previous_contents[destination] = destination.read_bytes() if destination.is_file() else None

    published: list[Path] = []
    try:
        for name, destination in zip(_ARTIFACT_NAMES, destinations, strict=True):
            (staging_dir / name).replace(destination)
            published.append(destination)
    except Exception:
        for destination in published:
            previous = previous_contents[destination]
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                destination.write_bytes(previous)
        raise


def _structure_summary(graphs: Sequence[GraphData], batch: Batch) -> dict[str, JsonValue]:
    return {
        "construction_hashes": [graph.construction_hash for graph in graphs],
        "edge_count": int(batch.edge_index.size(1)),
        "feature_dim": int(batch.x.size(1)),
        "graph_count": int(batch.num_graphs),
        "node_count": int(batch.x.size(0)),
        "relations": [{"modality": graph.modality, "relation": graph.relation} for graph in graphs],
    }


def run_smoke(overrides: Sequence[str] | None = None) -> dict[str, JsonValue]:
    """Run the deterministic CPU smoke workflow and save its three artifacts."""
    config = compose_config(overrides)
    device = torch.device("cpu")
    if config.device != device.type:
        raise ValueError("Smoke execution requires config.device='cpu'.")

    project_root = find_project_root(Path(__file__))
    output_dir = ensure_safe_output_dir(
        Path(cast(str, config.paths.output_dir)), project_root=project_root
    )
    graphs = build_smoke_graphs(
        seed=cast(int, config.random_seed),
        num_nodes=cast(int, config.graph.num_nodes),
        feature_dim=cast(int, config.graph.feature_dim),
    )
    batch = batch_smoke_graphs(graphs)
    if batch.x.device != device:
        raise RuntimeError("Smoke graph batch was not created on the CPU.")

    with TemporaryDirectory(prefix=".staging-", dir=output_dir) as staging_name:
        staging_dir = Path(staging_name)
        config_hash = save_resolved_config(config, staging_dir / "resolved_config.yaml")
        provenance = collect_provenance(
            contract_version=cast(str, config.contract_version),
            config_hash=config_hash,
            random_seed=cast(int, config.random_seed),
            command=[sys.executable, "-m", "canospar.utils.smoke_test", *(overrides or ())],
            project_root=project_root,
            device=device.type,
        )
        write_provenance(provenance, staging_dir / "provenance.json")
        structure = _structure_summary(graphs, batch)
        report: dict[str, JsonValue] = {
            "config_hash": config_hash,
            "contract_version": cast(str, config.contract_version),
            "device": device.type,
            "status": "success",
            "seed": cast(int, config.random_seed),
            "num_graphs": int(batch.num_graphs),
            "total_nodes": int(batch.x.size(0)),
            "total_edges": int(batch.edge_index.size(1)),
            "feature_dim": int(batch.x.size(1)),
            "modalities": [graph.modality for graph in graphs],
            "relations": [graph.relation for graph in graphs],
            "batch_shape": [int(dimension) for dimension in batch.x.shape],
            "structure": structure,
        }
        _write_report(report, staging_dir / "smoke_report.json")
        _publish_staged_artifacts(staging_dir, output_dir)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the smoke workflow from ``python -m`` and print a concise JSON result."""
    report = run_smoke(list(argv) if argv is not None else sys.argv[1:])
    print(
        json.dumps(
            {
                "config_hash": report["config_hash"],
                "device": report["device"],
                "num_graphs": report["num_graphs"],
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
