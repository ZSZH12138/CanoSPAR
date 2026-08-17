import importlib
import inspect

import pytest

from canospar.contracts.bands import CanonicalSpectrumBundle
from canospar.contracts.evaluation import EvaluationBundle
from canospar.contracts.prediction import PredictionBundle
from canospar.contracts.roles import RoleBundle
from canospar.contracts.routing import RoutingBundle
from canospar.contracts.spectral import SpectralBundle
from canospar.contracts.tokens import TokenBundle


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("p0", "prepare_imaging_sample"),
        ("m0", "load_dataset_manifest"),
        ("m1", "build_multigraph_sample"),
        ("m2", "run_m2"),
        ("m3", "run_m3"),
        ("m4", "filter_bands"),
        ("m5", "tokenize_bands"),
        ("m6", "infer_roles"),
        ("m7", "route_tokens"),
        ("m8", "predict_sample"),
        ("m9", "evaluate_predictions"),
    ],
)
def test_public_module_api_symbol_exists(module_name: str, symbol: str) -> None:
    module = importlib.import_module(f"canospar.api.{module_name}")

    assert hasattr(module, symbol)
    assert callable(getattr(module, symbol))


def test_artifact_family_types_are_exported() -> None:
    assert SpectralBundle.__name__ == "SpectralBundle"
    assert CanonicalSpectrumBundle.__name__ == "CanonicalSpectrumBundle"
    assert TokenBundle.__name__ == "TokenBundle"
    assert RoleBundle.__name__ == "RoleBundle"
    assert RoutingBundle.__name__ == "RoutingBundle"
    assert PredictionBundle.__name__ == "PredictionBundle"
    assert EvaluationBundle.__name__ == "EvaluationBundle"


def test_m3_boundary_consumes_spectral_bundle_not_graph_data() -> None:
    parameters = inspect.signature(importlib.import_module("canospar.api.m3").run_m3).parameters

    assert tuple(parameters) == (
        "spectral_bundle",
        "coordinate_spec",
        "band_spec",
        "context",
    )


def test_contract_only_api_fails_closed_without_fabricating_artifacts() -> None:
    from canospar.api import m4, m5, m6, m7, m8, m9

    with pytest.raises(NotImplementedError, match="M4"):
        m4.filter_bands(None, None, None, None, None)
    with pytest.raises(NotImplementedError, match="M5"):
        m5.tokenize_bands(None, None, None)
    with pytest.raises(NotImplementedError, match="M6"):
        m6.infer_roles(None, None, None, None, None)
    with pytest.raises(NotImplementedError, match="M7"):
        m7.route_tokens(None, None, None, None)
    with pytest.raises(NotImplementedError, match="M8"):
        m8.predict_sample(None, None, None, None, None)
    with pytest.raises(NotImplementedError, match="M9"):
        m9.evaluate_predictions(None, None)
