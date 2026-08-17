import torch

from canospar.contracts.base import ArtifactMeta
from canospar.contracts.graph import BrainMultiGraphSample, GraphData, MultiGraphArtifact


def make_graph() -> GraphData:
    return GraphData(
        x=torch.ones((2, 1)),
        edge_index=torch.tensor([[0, 1], [1, 0]], dtype=torch.long),
        edge_weight=torch.ones(2),
        num_nodes=2,
        modality="smri",
        relation="morphology",
        graph_qc={"finite": 1.0},
        construction_hash="construction-a",
    )


def make_sample() -> BrainMultiGraphSample:
    return BrainMultiGraphSample(
        subject_id="subject-a",
        visit_id="baseline",
        group_id="subject-a",
        site_id="site-a",
        graphs={"smri": {"morphology": make_graph()}},
        modality_available={"smri": True, "dmri": False, "fmri": False},
        qc_vector={"motion": 0.1},
        target=1.0,
        covariates={"age": 30.0},
        cohort_metadata={
            "cohort_source": "synthetic",
            "unrelated_list_version": "not_applicable",
            "kinship_control_method": "synthetic",
        },
    )


def make_meta() -> ArtifactMeta:
    return ArtifactMeta(
        schema_version="1.0.0",
        artifact_type="MultiGraphArtifact",
        artifact_id="artifact-a",
        producer_module="M1",
        module_contract_version="1.0.0",
        science_contract_version="1.1.0",
        input_artifact_ids=(),
        input_content_hashes=(),
        science_config_hash="config-a",
        dataset_manifest_hash="manifest-a",
        split_id="outer-0",
        random_seed=7,
        content_sha256="content-a",
        implementation_hash="impl-a",
        numerics_profile_hash="numerics-a",
        created_at_utc="2026-08-17T00:00:00Z",
    )


def test_existing_graph_imports_remain_compatible() -> None:
    assert GraphData.__module__ == "canospar.data.contracts"
    assert BrainMultiGraphSample.__module__ == "canospar.data.contracts"


def test_multigraph_artifact_wraps_existing_sample_without_replacing_it() -> None:
    sample = make_sample()
    artifact = MultiGraphArtifact(
        meta=make_meta(),
        sample=sample,
        atlas_id="toy-atlas",
        atlas_hash="atlas-hash",
        roi_table_hash="roi-hash",
        node_order_hash="node-order-hash",
    )

    assert artifact.sample is sample
    assert artifact.sample.graphs["smri"]["morphology"].modality == "smri"
