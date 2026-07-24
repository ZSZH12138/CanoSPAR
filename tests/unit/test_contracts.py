from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from typing import Any

import pytest
import torch
from torch_geometric.data import Data

from canospar.data.contracts import BrainMultiGraphSample, GraphData


@pytest.fixture
def valid_graph() -> GraphData:
    return GraphData(
        x=torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32),
        edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
        edge_weight=torch.tensor([0.5, 1.5], dtype=torch.float32),
        num_nodes=2,
        modality="smri",
        relation="morphometry",
        graph_qc={"motion": 0.1},
        construction_hash="a" * 64,
    )


def _sample(
    *, graphs: Mapping[str, Mapping[str, GraphData]], **overrides: Any
) -> BrainMultiGraphSample:
    fields: dict[str, Any] = {
        "subject_id": "subject-001",
        "visit_id": "baseline",
        "group_id": "subject-001",
        "site_id": "site-a",
        "graphs": graphs,
        "modality_available": {"smri": True, "dmri": False, "fmri": False},
        "qc_vector": {"mean_fd": 0.12},
        "target": 1.5,
        "covariates": {"age": 30.0, "sex": "F"},
        "cohort_metadata": {
            "cohort_source": "hcp_official_unrelated",
            "unrelated_list_version": "S900-unrelated.csv",
            "kinship_control_method": "official_unrelated_cohort",
        },
    }
    return BrainMultiGraphSample(**(fields | overrides))


def test_valid_graph_converts_to_pyg(valid_graph: GraphData) -> None:
    valid_graph.validate()

    data = valid_graph.to_pyg_data()

    assert isinstance(data, Data)
    assert data.num_nodes == valid_graph.num_nodes
    assert torch.equal(data.x, valid_graph.x)
    assert torch.equal(data.edge_index, valid_graph.edge_index)
    assert torch.equal(data.edge_weight, valid_graph.edge_weight)
    assert data.modality == valid_graph.modality
    assert data.relation == valid_graph.relation


def test_graph_copies_constructor_tensors_and_nested_metadata() -> None:
    x = torch.tensor([[1.0], [2.0]], dtype=torch.float32)
    edge_index = torch.tensor([[0], [1]], dtype=torch.long)
    edge_weight = torch.tensor([0.5], dtype=torch.float32)
    graph_qc = {"scanner": {"name": "A"}}

    graph = GraphData(
        x=x,
        edge_index=edge_index,
        edge_weight=edge_weight,
        num_nodes=2,
        modality="smri",
        relation="morphometry",
        graph_qc=graph_qc,
        construction_hash="a" * 64,
    )
    x[0, 0] = 99.0
    edge_index[0, 0] = 1
    edge_weight[0] = 99.0
    graph_qc["scanner"]["name"] = "B"

    assert graph.x[0, 0].item() == 1.0
    assert graph.edge_index[0, 0].item() == 0
    assert graph.edge_weight[0].item() == 0.5
    assert graph.graph_qc == {"scanner": {"name": "A"}}


def test_pyg_conversion_copies_tensors_and_nested_metadata(valid_graph: GraphData) -> None:
    graph = GraphData(
        **{
            **valid_graph.__dict__,
            "graph_qc": {"scanner": {"name": "A"}},
        }
    )

    data = graph.to_pyg_data()
    data.x[0, 0] = 99.0
    data.edge_index[0, 0] = 1
    data.edge_weight[0] = 99.0
    data.graph_qc["scanner"]["name"] = "B"

    assert graph.x[0, 0].item() == 1.0
    assert graph.edge_index[0, 0].item() == 0
    assert graph.edge_weight[0].item() == 0.5
    assert graph.graph_qc == {"scanner": {"name": "A"}}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("x", torch.tensor([1.0, 2.0])),
        ("edge_index", torch.tensor([0, 1], dtype=torch.long)),
        ("edge_index", torch.tensor([[0], [1]], dtype=torch.int32)),
        ("edge_weight", torch.tensor([[1.0]])),
    ],
)
def test_graph_rejects_invalid_tensor_rank_or_dtype(
    valid_graph: GraphData, field: str, value: torch.Tensor
) -> None:
    with pytest.raises(ValueError):
        GraphData(**({**valid_graph.__dict__, field: value})).validate()


@pytest.mark.parametrize("field", ["x", "edge_index", "edge_weight"])
def test_graph_rejects_non_tensor_inputs_with_value_error(
    valid_graph: GraphData, field: str
) -> None:
    with pytest.raises(ValueError):
        GraphData(**({**valid_graph.__dict__, field: []})).validate()


@pytest.mark.parametrize("floating_dtype", [torch.float16, torch.float32, torch.float64])
def test_graph_accepts_all_floating_tensor_dtypes(
    valid_graph: GraphData, floating_dtype: torch.dtype
) -> None:
    graph = GraphData(
        **{
            **valid_graph.__dict__,
            "x": valid_graph.x.to(floating_dtype),
            "edge_weight": valid_graph.edge_weight.to(floating_dtype),
        }
    )

    graph.validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("edge_weight", torch.tensor([1.0], dtype=torch.float32)),
        ("num_nodes", 3),
        ("num_nodes", 0),
        ("num_nodes", True),
        ("edge_index", torch.tensor([[-1, 1], [1, 0]], dtype=torch.long)),
        ("edge_index", torch.tensor([[0, 2], [1, 0]], dtype=torch.long)),
        ("x", torch.tensor([[math.nan, 2.0], [3.0, 4.0]])),
        ("edge_weight", torch.tensor([math.inf, 1.0])),
    ],
)
def test_graph_rejects_invalid_shape_indices_or_non_finite_values(
    valid_graph: GraphData, field: str, value: object
) -> None:
    with pytest.raises(ValueError):
        GraphData(**({**valid_graph.__dict__, field: value})).validate()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("modality", ""),
        ("relation", ""),
        ("construction_hash", ""),
        ("graph_qc", {}),
        ("graph_qc", {"bad": {1, 2}}),
    ],
)
def test_graph_rejects_empty_or_non_json_metadata(
    valid_graph: GraphData, field: str, value: object
) -> None:
    with pytest.raises(ValueError):
        GraphData(**({**valid_graph.__dict__, field: value})).validate()


def test_graph_accepts_empty_edges_without_requiring_symmetry(valid_graph: GraphData) -> None:
    graph = GraphData(
        **{
            **valid_graph.__dict__,
            "edge_index": torch.empty((2, 0), dtype=torch.long),
            "edge_weight": torch.empty((0,), dtype=torch.float32),
        }
    )

    graph.validate()


def test_graph_validation_does_not_modify_input_tensors_or_mapping(valid_graph: GraphData) -> None:
    graph_qc = {"motion": 0.1}
    x = valid_graph.x.clone()
    edge_index = valid_graph.edge_index.clone()
    edge_weight = valid_graph.edge_weight.clone()
    graph = GraphData(
        **{
            **valid_graph.__dict__,
            "x": x,
            "edge_index": edge_index,
            "edge_weight": edge_weight,
            "graph_qc": graph_qc,
        }
    )
    before = (x.clone(), edge_index.clone(), edge_weight.clone(), graph_qc.copy())

    graph.validate()

    assert torch.equal(x, before[0])
    assert torch.equal(edge_index, before[1])
    assert torch.equal(edge_weight, before[2])
    assert graph_qc == before[3]


def test_graph_is_frozen(valid_graph: GraphData) -> None:
    with pytest.raises(FrozenInstanceError):
        valid_graph.num_nodes = 3  # type: ignore[misc]


def test_valid_multi_graph_sample_validates(valid_graph: GraphData) -> None:
    sample = _sample(graphs={"smri": {"morphometry": valid_graph}})

    sample.validate()


@pytest.mark.parametrize("modality", ["pet", "SMRI", ""])
def test_sample_rejects_invalid_outer_modality(valid_graph: GraphData, modality: str) -> None:
    sample = _sample(graphs={modality: {"morphometry": valid_graph}})

    with pytest.raises(ValueError):
        sample.validate()


def test_sample_rejects_graph_whose_inner_modality_disagrees_with_outer_key(
    valid_graph: GraphData,
) -> None:
    sample = _sample(graphs={"dmri": {"morphometry": valid_graph}})

    with pytest.raises(ValueError, match="modality"):
        sample.validate()


@pytest.mark.parametrize(
    "availability",
    [
        {"smri": False, "dmri": False, "fmri": False},
        {"smri": True, "dmri": True, "fmri": False},
        {"smri": True, "dmri": False},
        {"smri": 1, "dmri": False, "fmri": False},
    ],
)
def test_sample_requires_bidirectional_availability_consistency(
    valid_graph: GraphData, availability: Mapping[str, object]
) -> None:
    sample = _sample(graphs={"smri": {"morphometry": valid_graph}}, modality_available=availability)

    with pytest.raises(ValueError):
        sample.validate()


@pytest.mark.parametrize(
    ("qc_vector", "target"),
    [
        ({"mean_fd": math.nan}, 1.0),
        ({"mean_fd": math.inf}, 1.0),
        ({"mean_fd": 0.1}, math.nan),
        ({"mean_fd": 0.1}, True),
        ({"mean_fd": True}, 1.0),
    ],
)
def test_sample_rejects_non_finite_or_boolean_qc_and_target(
    valid_graph: GraphData, qc_vector: Mapping[str, object], target: object
) -> None:
    sample = _sample(
        graphs={"smri": {"morphometry": valid_graph}},
        qc_vector=qc_vector,
        target=target,
    )

    with pytest.raises(ValueError):
        sample.validate()


@pytest.mark.parametrize(
    "covariates",
    [
        {"scanner": {"model": "A"}},
        {"age": True},
        {"age": 30},
        {1: "F"},
        {"bad": {1, 2}},
    ],
)
def test_sample_requires_flat_string_or_float_covariates(
    valid_graph: GraphData, covariates: Mapping[str, object]
) -> None:
    sample = _sample(graphs={"smri": {"morphometry": valid_graph}}, covariates=covariates)

    with pytest.raises(ValueError):
        sample.validate()


@pytest.mark.parametrize(
    "cohort_metadata",
    [
        {},
        {
            "cohort_source": "hcp_official_unrelated",
            "unrelated_list_version": "S900-unrelated.csv",
        },
        {
            "cohort_source": "hcp_official_unrelated",
            "unrelated_list_version": "",
            "kinship_control_method": "official_unrelated_cohort",
        },
        {
            "cohort_source": "hcp_official_unrelated",
            "unrelated_list_version": "S900-unrelated.csv",
            "kinship_control_method": 1,
        },
    ],
)
def test_sample_requires_complete_string_cohort_metadata(
    valid_graph: GraphData, cohort_metadata: Mapping[str, object]
) -> None:
    sample = _sample(
        graphs={"smri": {"morphometry": valid_graph}},
        cohort_metadata=cohort_metadata,
    )

    with pytest.raises(ValueError, match="cohort_metadata"):
        sample.validate()


def test_sample_accepts_explicit_not_applicable_cohort_metadata(
    valid_graph: GraphData,
) -> None:
    sample = _sample(
        graphs={"smri": {"morphometry": valid_graph}},
        cohort_metadata={
            "cohort_source": "ppmi",
            "unrelated_list_version": "not_applicable",
            "kinship_control_method": "not_applicable",
        },
    )

    sample.validate()


def test_sample_copies_constructor_mappings(valid_graph: GraphData) -> None:
    graphs = {"smri": {"morphometry": valid_graph}}
    availability = {"smri": True, "dmri": False, "fmri": False}
    qc_vector = {"mean_fd": 0.12}
    covariates = {"age": 30.0}
    cohort_metadata = {
        "cohort_source": "hcp_official_unrelated",
        "unrelated_list_version": "S900-unrelated.csv",
        "kinship_control_method": "official_unrelated_cohort",
    }

    sample = _sample(
        graphs=graphs,
        modality_available=availability,
        qc_vector=qc_vector,
        covariates=covariates,
        cohort_metadata=cohort_metadata,
    )
    graphs["smri"].clear()
    availability["smri"] = False
    qc_vector["mean_fd"] = 99.0
    covariates["age"] = 99.0
    cohort_metadata["cohort_source"] = "mutated"
    valid_graph.x[0, 0] = 99.0
    valid_graph.edge_index[0, 0] = 1
    valid_graph.edge_weight[0] = 99.0
    valid_graph.graph_qc["motion"] = 99.0

    sample_graph = sample.graphs["smri"]["morphometry"]

    assert sample_graph is not valid_graph
    assert sample_graph.x[0, 0].item() == 1.0
    assert sample_graph.edge_index[0, 0].item() == 0
    assert sample_graph.edge_weight[0].item() == 0.5
    assert sample_graph.graph_qc == {"motion": 0.1}
    assert sample.modality_available == {"smri": True, "dmri": False, "fmri": False}
    assert sample.qc_vector == {"mean_fd": 0.12}
    assert sample.covariates == {"age": 30.0}
    assert sample.cohort_metadata["cohort_source"] == "hcp_official_unrelated"


def test_sample_validation_does_not_modify_mappings(valid_graph: GraphData) -> None:
    graphs = {"smri": {"morphometry": valid_graph}}
    availability = {"smri": True, "dmri": False, "fmri": False}
    qc_vector = {"mean_fd": 0.12}
    covariates = {"age": 30.0}
    cohort_metadata = {
        "cohort_source": "hcp_official_unrelated",
        "unrelated_list_version": "S900-unrelated.csv",
        "kinship_control_method": "official_unrelated_cohort",
    }
    sample = _sample(
        graphs=graphs,
        modality_available=availability,
        qc_vector=qc_vector,
        covariates=covariates,
        cohort_metadata=cohort_metadata,
    )
    before = (
        graphs.copy(),
        availability.copy(),
        qc_vector.copy(),
        covariates.copy(),
        cohort_metadata.copy(),
    )

    sample.validate()

    assert graphs == before[0]
    assert availability == before[1]
    assert qc_vector == before[2]
    assert covariates == before[3]
    assert cohort_metadata == before[4]


def test_sample_cohort_metadata_is_immutable(valid_graph: GraphData) -> None:
    sample = _sample(graphs={"smri": {"morphometry": valid_graph}})

    with pytest.raises(TypeError):
        sample.cohort_metadata["cohort_source"] = "mutated"  # type: ignore[index]


def test_sample_is_frozen(valid_graph: GraphData) -> None:
    sample = _sample(graphs={"smri": {"morphometry": valid_graph}})

    with pytest.raises(FrozenInstanceError):
        sample.target = 2.0  # type: ignore[misc]
