from __future__ import annotations

from pathlib import Path

import pytest
from omegaconf import OmegaConf

from canospar.utils.config import compose_config, save_resolved_config
from canospar.utils.hashing import hash_yaml_config


def test_default_config_forces_cpu() -> None:
    config = compose_config()

    assert config.device == "cpu"


def test_default_config_exposes_the_experiment_contract_fields() -> None:
    config = compose_config()

    assert config.contract_version == "1.0.0"
    assert config.random_seed == 7
    assert config.logging.level == "info"
    assert config.logging.save_resolved_config is True


def test_compose_config_applies_programmatic_cli_style_overrides() -> None:
    config = compose_config(overrides=["random_seed=17", "graph.num_nodes=5"])

    assert config.random_seed == 17
    assert config.graph.num_nodes == 5


def test_compose_config_accepts_an_integer_zero_random_seed() -> None:
    config = compose_config(overrides=["random_seed=0"])

    assert config.random_seed == 0


def test_compose_config_applies_hydra_config_group_override() -> None:
    config = compose_config(overrides=["data=toy"])

    assert config.data.name == "toy"
    assert config.data.modalities == ["smri", "dmri", "fmri"]


@pytest.mark.parametrize(
    "overrides",
    [
        ["random_seed=abc"],
        ["graph.num_nodes=abc"],
        ["logging.save_resolved_config=not_bool"],
        ["~logging"],
    ],
)
def test_compose_config_rejects_invalid_contract_overrides(overrides: list[str]) -> None:
    with pytest.raises(ValueError):
        compose_config(overrides=overrides)


@pytest.mark.parametrize(
    "override",
    [
        "paths.output_dir=../outside",
        "paths.output_dir=artifacts/../outside",
        "paths.output_dir=.",
        "paths.output_dir=''",
        "paths.output_dir=/outside",
        "paths.output_dir='C:/outside'",
    ],
)
def test_compose_config_rejects_unsafe_output_paths(override: str) -> None:
    with pytest.raises(ValueError, match=r"config\.paths\.output_dir"):
        compose_config(overrides=[override])


def test_compose_config_accepts_canonical_relative_artifact_path() -> None:
    config = compose_config(overrides=["paths.output_dir=artifacts/smoke"])

    assert config.paths.output_dir == "artifacts/smoke"


@pytest.mark.parametrize("field", ["num_nodes", "feature_dim"])
def test_graph_validation_reports_the_nested_field_name(field: str) -> None:
    with pytest.raises(ValueError, match=rf"config\.graph\.{field}"):
        compose_config(overrides=[f"graph.{field}=0"])


def test_compose_config_does_not_change_the_working_directory() -> None:
    original_directory = Path.cwd()

    compose_config()

    assert Path.cwd() == original_directory


def test_compose_config_rejects_non_cpu_device_override() -> None:
    with pytest.raises(ValueError, match="CPU"):
        compose_config(overrides=["device=cuda"])


def test_save_resolved_config_writes_reloadable_yaml_and_returns_its_hash(tmp_path: Path) -> None:
    config = compose_config(overrides=["random_seed=29", "graph.feature_dim=7"])
    destination = tmp_path / "nested" / "resolved.yaml"

    first_hash = save_resolved_config(config, destination)
    first_contents = destination.read_text(encoding="utf-8")
    second_hash = save_resolved_config(config, destination)

    reloaded = OmegaConf.load(destination)
    assert first_hash == second_hash == hash_yaml_config(config) == hash_yaml_config(reloaded)
    assert destination.read_text(encoding="utf-8") == first_contents
    assert OmegaConf.to_container(reloaded, resolve=True) == OmegaConf.to_container(
        config, resolve=True
    )


def test_default_config_contains_no_personal_absolute_paths() -> None:
    rendered = OmegaConf.to_yaml(compose_config(), resolve=True)

    assert "C:\\Users\\" not in rendered
    assert "/home/" not in rendered
