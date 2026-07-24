"""Hydra composition and reproducible resolved-configuration persistence."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import cast

from hydra import compose, initialize_config_dir
from omegaconf import DictConfig, OmegaConf

from canospar.utils.hashing import hash_yaml_config
from canospar.utils.paths import find_project_root


def _config_directory() -> Path:
    """Return the repository's Hydra configuration directory."""
    return find_project_root(Path(__file__)) / "configs"


def _require_mapping(config: DictConfig, key: str, *, parent: str = "config") -> DictConfig:
    value = config.get(key)
    if not isinstance(value, DictConfig):
        raise ValueError(f"{parent}.{key} must be present and a mapping")
    return value


def _require_nonempty_string(config: DictConfig, key: str, *, parent: str = "config") -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{parent}.{key} must be a non-empty string")
    return value


def _require_positive_int(config: DictConfig, key: str, *, parent: str = "config") -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{parent}.{key} must be a positive integer")
    return cast(int, value)


def _require_int(config: DictConfig, key: str, *, parent: str = "config") -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{parent}.{key} must be an integer")
    return cast(int, value)


def _validate_config(config: DictConfig) -> None:
    _require_nonempty_string(config, "contract_version")
    _require_int(config, "random_seed")
    if _require_nonempty_string(config, "device") != "cpu":
        raise ValueError("Only CPU execution is supported; config.device must be 'cpu'")

    for key in ("data", "graph", "model", "experiment", "paths", "logging"):
        _require_mapping(config, key)

    graph = _require_mapping(config, "graph")
    _require_positive_int(graph, "num_nodes", parent="config.graph")
    _require_positive_int(graph, "feature_dim", parent="config.graph")

    paths = _require_mapping(config, "paths")
    output_dir = _require_nonempty_string(paths, "output_dir", parent="config.paths")
    path_components = output_dir.replace("\\", "/").split("/")
    is_absolute = (
        Path(output_dir).is_absolute()
        or PurePosixPath(output_dir).is_absolute()
        or PureWindowsPath(output_dir).is_absolute()
    )
    if is_absolute or any(component in {".", ".."} for component in path_components):
        raise ValueError("config.paths.output_dir must be a canonical relative path")

    logging = _require_mapping(config, "logging")
    _require_nonempty_string(logging, "level", parent="config.logging")
    if not isinstance(logging.get("save_resolved_config"), bool):
        raise ValueError("config.logging.save_resolved_config must be a boolean")


def compose_config(overrides: Sequence[str] | None = None) -> DictConfig:
    """Compose the project's Hydra configuration without changing the CWD.

    Overrides use ordinary Hydra CLI syntax, such as ``["random_seed=11"]`` or
    ``["graph.num_nodes=5"]``. The Week 1 infrastructure intentionally accepts
    only CPU execution, including after overrides have been applied.
    """
    cli_overrides = list(overrides) if overrides is not None else []
    with initialize_config_dir(config_dir=str(_config_directory()), version_base="1.3"):
        config = compose(config_name="config", overrides=cli_overrides)

    _validate_config(config)
    return config


def save_resolved_config(config: DictConfig, destination: Path) -> str:
    """Write a fully resolved YAML configuration and return its stable hash."""
    config_hash = hash_yaml_config(config)
    serialized = OmegaConf.to_yaml(config, resolve=True, sort_keys=True)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding="utf-8")
    return config_hash
