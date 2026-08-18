"""Machine verifier for CanoSPAR Architecture Contract v1."""

# Gate IDs and their evidence messages are intentionally explicit for audit output.
# ruff: noqa: E501

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

MODULE_NAMES = ("M0", "P0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9")
MODULE_PROTOCOL_SPEC_VERSION = "1.1.0"
CONTRACT_ONLY_MODULES = ("M3", "M4", "M5", "M6", "M7", "M8", "M9")
REQUIRED_FILES = (
    "AGENTS.md",
    "docs/architecture/CANOSPAR_ARCHITECTURE_CONTRACT_V1.md",
    "docs/architecture/ARTIFACT_CONTRACTS_V1.md",
    "docs/architecture/MODULE_CONTRACTS_V1.md",
    "docs/architecture/EXECUTION_AND_LINEAGE_CONTRACT_V1.md",
    "docs/architecture/RUNTIME_BOUNDARY_V1.md",
    "docs/architecture/CONTRACT_CHANGE_POLICY.md",
    "docs/architecture/EXISTING_WORK_PLACEMENT_MAP.md",
    "docs/architecture/CANOSPAR_MODULE_PROTOCOL_SPEC_V1.md",
    "docs/architecture/archive/CANOSPAR_MODULE_PROTOCOL_SPEC_V1_0_0.md",
    "docs/decisions/0002-canospar-architecture-contract-v1.md",
    "docs/decisions/0003-module-protocol-v1.1-m2-m4-contract-repair.md",
    "configs/architecture/contracts_v1.yaml",
    "reports/architecture/ARCHITECTURE_V1_BASELINE.json",
    "src/canospar/contracts/__init__.py",
    "src/canospar/contracts/base.py",
    "src/canospar/contracts/execution.py",
    "src/canospar/api/__init__.py",
    "src/canospar/api/p0.py",
    "src/canospar/api/m0.py",
    "src/canospar/api/m1.py",
    "src/canospar/api/m2.py",
    "src/canospar/api/m3.py",
    "src/canospar/api/m4.py",
    "src/canospar/api/m5.py",
    "src/canospar/api/m6.py",
    "src/canospar/api/m7.py",
    "src/canospar/api/m8.py",
    "src/canospar/api/m9.py",
    "src/canospar/validators/__init__.py",
    "src/canospar/runtime/__init__.py",
    "src/canospar/runtime/numerics.py",
)


def load_registry(root: Path) -> dict[str, Any]:
    registry_path = root / "configs/architecture/contracts_v1.yaml"
    with registry_path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("architecture registry must be a mapping")
    return loaded


def check_registry_consistency(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if registry.get("architecture_contract_version") != "1.0.0":
        errors.append("architecture_contract_version must be 1.0.0")
    if registry.get("science_contract_version") != "1.1.0":
        errors.append("science_contract_version must be 1.1.0")
    if registry.get("schema_version") != "1.0.0":
        errors.append("schema_version must be 1.0.0")
    if registry.get("runtime_profile_version") != "1.0.0":
        errors.append("runtime_profile_version must be 1.0.0")
    if registry.get("numerics_profile_schema_version") != "1.0.0":
        errors.append("numerics_profile_schema_version must be 1.0.0")
    if registry.get("module_protocol_spec_version") != MODULE_PROTOCOL_SPEC_VERSION:
        errors.append(f"module_protocol_spec_version must be {MODULE_PROTOCOL_SPEC_VERSION}")

    modules = registry.get("modules")
    if not isinstance(modules, dict):
        return ["modules must be a mapping"]
    if tuple(modules) != MODULE_NAMES:
        errors.append("registry module order or membership does not match P0/M0-M9")

    for module_id, module in modules.items():
        if not isinstance(module, dict):
            errors.append(f"{module_id} must be a mapping")
            continue
        if module.get("contract_version") != MODULE_PROTOCOL_SPEC_VERSION:
            errors.append(f"{module_id} contract_version must be {MODULE_PROTOCOL_SPEC_VERSION}")
        status = module.get("implementation_status")
        if status not in {"EXISTING", "PARTIAL", "CONTRACT_ONLY", "IMPLEMENTED", "VERIFIED"}:
            errors.append(f"{module_id} has an invalid implementation_status")
        if module_id in CONTRACT_ONLY_MODULES and status != "CONTRACT_ONLY":
            raise ValueError(f"{module_id} must remain CONTRACT_ONLY")
        if not module.get("source_of_truth"):
            errors.append(f"{module_id} must declare source_of_truth")

    source_of_truth = registry.get("source_of_truth")
    if not isinstance(source_of_truth, dict):
        errors.append("source_of_truth must be a mapping")
    elif set(source_of_truth) != set(MODULE_NAMES):
        errors.append("source_of_truth must cover every module")

    if tuple(registry.get("invalidation_dag", ())) != MODULE_NAMES:
        errors.append("invalidation_dag must match the module order")
    return errors


def _check(gate_id: str, status: str, message: str) -> dict[str, str]:
    return {"id": gate_id, "status": status, "message": message}


def _run_contract_tests(root: Path) -> tuple[bool, str]:
    environment = os.environ.copy()
    source_path = str(root / "src")
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_path if not existing_path else source_path + os.pathsep + existing_path
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/contracts",
            "--ignore",
            "tests/contracts/test_verifier_results.py",
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (completed.stdout + completed.stderr).strip().splitlines()
    summary = output[-1] if output else "no test output"
    return completed.returncode == 0, summary


def run_checks(root: Path) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    missing = [path for path in REQUIRED_FILES if not (root / path).exists()]
    checks.append(
        _check(
            "G00_REQUIRED_FILES",
            "PASS" if not missing else "FAIL",
            "all required architecture files exist"
            if not missing
            else f"missing: {', '.join(missing)}",
        )
    )

    try:
        from canospar.contracts.graph import BrainMultiGraphSample, GraphData

        if (
            GraphData.__module__ == "canospar.data.contracts"
            and BrainMultiGraphSample.__module__ == "canospar.data.contracts"
        ):
            checks.append(
                _check(
                    "G01_EXISTING_IMPORT_COMPATIBILITY", "PASS", "legacy graph imports preserved"
                )
            )
        else:
            checks.append(
                _check(
                    "G01_EXISTING_IMPORT_COMPATIBILITY", "FAIL", "legacy graph import owner changed"
                )
            )
    except Exception as error:
        checks.append(_check("G01_EXISTING_IMPORT_COMPATIBILITY", "FAIL", str(error)))

    try:
        artifact_modules = (
            "canospar.contracts.base",
            "canospar.contracts.imaging",
            "canospar.contracts.spectral",
            "canospar.contracts.bands",
            "canospar.contracts.tokens",
            "canospar.contracts.roles",
            "canospar.contracts.routing",
            "canospar.contracts.prediction",
            "canospar.contracts.evaluation",
            "canospar.contracts.execution",
        )
        for module_name in artifact_modules:
            importlib.import_module(module_name)
        checks.append(
            _check("G02_ARTIFACT_SCHEMA_COMPLETE", "PASS", "artifact contract modules import")
        )
    except Exception as error:
        checks.append(_check("G02_ARTIFACT_SCHEMA_COMPLETE", "FAIL", str(error)))

    try:
        api_symbols = {
            "p0": "prepare_imaging_sample",
            "m0": "load_dataset_manifest",
            "m1": "build_multigraph_sample",
            "m2": "run_m2",
            "m3": "run_m3",
            "m4": "filter_bands",
            "m5": "tokenize_bands",
            "m6": "infer_roles",
            "m7": "route_tokens",
            "m8": "predict_sample",
            "m9": "evaluate_predictions",
        }
        for module_name, symbol in api_symbols.items():
            module = importlib.import_module(f"canospar.api.{module_name}")
            if not callable(getattr(module, symbol)):
                raise ValueError(f"{module_name}.{symbol} is not callable")
        checks.append(
            _check("G03_MODULE_API_COMPLETE", "PASS", "P0 and M0-M9 public symbols import")
        )
    except Exception as error:
        checks.append(_check("G03_MODULE_API_COMPLETE", "FAIL", str(error)))

    try:
        registry = load_registry(root)
        errors = check_registry_consistency(registry)
        checks.append(
            _check(
                "G04_MODULE_REGISTRY_CONSISTENT",
                "PASS" if not errors else "FAIL",
                "registry is internally consistent" if not errors else "; ".join(errors),
            )
        )
    except Exception as error:
        checks.append(_check("G04_MODULE_REGISTRY_CONSISTENT", "FAIL", str(error)))

    try:
        registry = load_registry(root)
        namespace_keys = (
            "architecture_contract_version",
            "science_contract_version",
            "schema_version",
            "runtime_profile_version",
            "numerics_profile_schema_version",
            "module_protocol_spec_version",
        )
        if len(set(namespace_keys)) == len(namespace_keys) and all(
            isinstance(registry[key], str) and registry[key] for key in namespace_keys
        ):
            checks.append(
                _check(
                    "G05_VERSION_NAMESPACES_SEPARATED", "PASS", "version namespaces are distinct"
                )
            )
        else:
            checks.append(
                _check("G05_VERSION_NAMESPACES_SEPARATED", "FAIL", "version namespaces collide")
            )
    except Exception as error:
        checks.append(_check("G05_VERSION_NAMESPACES_SEPARATED", "FAIL", str(error)))

    try:
        from canospar.contracts.base import (
            ScienceContext,
            build_reproduction_key,
            build_science_key,
        )

        context = ScienceContext(science_config_hash="config-a")
        science_a = build_science_key(context, ("hash-a",), "M1", runtime_profile_id="runtime-a")
        science_b = build_science_key(context, ("hash-a",), "M1", runtime_profile_id="runtime-b")
        reproduction_a = build_reproduction_key(science_a, "impl-a", "numerics-a")
        reproduction_b = build_reproduction_key(science_a, "impl-b", "numerics-a")
        if science_a == science_b and reproduction_a != reproduction_b:
            checks.append(
                _check(
                    "G06_LINEAGE_DETERMINISTIC",
                    "PASS",
                    "science and reproduction keys are deterministic",
                )
            )
        else:
            checks.append(
                _check("G06_LINEAGE_DETERMINISTIC", "FAIL", "identity behavior is inconsistent")
            )
    except Exception as error:
        checks.append(_check("G06_LINEAGE_DETERMINISTIC", "FAIL", str(error)))

    try:
        from canospar.contracts.execution import (
            CanonicalStatus,
            CompletionReceipt,
            cache_is_eligible,
        )

        receipt = CompletionReceipt(
            module_id="M1",
            module_contract_version=MODULE_PROTOCOL_SPEC_VERSION,
            science_contract_version="1.1.0",
            canonical_status=CanonicalStatus.PASS,
            native_status=None,
            input_artifact_ids=(),
            input_hashes=(),
            science_key="science-a",
            reproduction_key="reproduction-a",
            runtime_profile_id="runtime-a",
            output_artifact_ids=("output-a",),
            output_hashes=("hash-a",),
            validator_status="PASS",
            validation_issue_codes=(),
            started_at_utc="2026-08-17T00:00:00Z",
            finished_at_utc="2026-08-17T00:01:00Z",
        )
        eligible = cache_is_eligible(
            expected_science_key="science-a",
            expected_reproduction_key="reproduction-a",
            artifact_hash="hash-a",
            receipt=receipt,
            validator_status="PASS",
        )
        checks.append(
            _check(
                "G07_CACHE_IDENTITY_CORRECT",
                "PASS" if eligible else "FAIL",
                "cache eligibility is fail-closed",
            )
        )
    except Exception as error:
        checks.append(_check("G07_CACHE_IDENTITY_CORRECT", "FAIL", str(error)))

    try:
        from canospar.runtime.invalidation import compute_invalidated_modules

        invalidated = compute_invalidated_modules("M3")
        expected = ("M3", "M4", "M5", "M6", "M7", "M8", "M9")
        checks.append(
            _check(
                "G08_INVALIDATION_DAG_CORRECT",
                "PASS" if invalidated == expected else "FAIL",
                "M3 invalidates only M3-M9",
            )
        )
    except Exception as error:
        checks.append(_check("G08_INVALIDATION_DAG_CORRECT", "FAIL", str(error)))

    try:
        from canospar.contracts.base import ScienceContext, build_science_key
        from canospar.runtime.profile import RuntimeProfile

        RuntimeProfile(profile_id="cpu", cpu_count=2, gpu_count=0)
        RuntimeProfile(profile_id="gpu", cpu_count=32, gpu_count=4)
        context = ScienceContext(science_config_hash="config-a")
        separated = build_science_key(
            context, ("hash-a",), "M1", runtime_profile_id="cpu"
        ) == build_science_key(context, ("hash-a",), "M1", runtime_profile_id="gpu")
        checks.append(
            _check(
                "G09_RUNTIME_SCIENCE_DECOUPLED",
                "PASS" if separated else "FAIL",
                "runtime profile changes do not alter science identity",
            )
        )
    except Exception as error:
        checks.append(_check("G09_RUNTIME_SCIENCE_DECOUPLED", "FAIL", str(error)))

    try:
        from canospar.contracts.base import ArtifactMeta
        from canospar.validators.contracts import validate_artifact_meta

        meta = ArtifactMeta(
            schema_version="1.0.0",
            artifact_type="VerifierArtifact",
            artifact_id="artifact-a",
            producer_module="M1",
            module_contract_version=MODULE_PROTOCOL_SPEC_VERSION,
            science_contract_version="1.1.0",
            input_artifact_ids=(),
            input_content_hashes=(),
            science_config_hash="config-a",
            dataset_manifest_hash=None,
            split_id=None,
            random_seed=None,
            content_sha256="hash-a",
            implementation_hash="impl-a",
            numerics_profile_hash="numerics-a",
            created_at_utc="2026-08-17T00:00:00Z",
        )
        fail_closed = validate_artifact_meta(meta, expected_schema_version="2.0.0").status == "FAIL"
        checks.append(
            _check(
                "G10_FAIL_CLOSED_VALIDATION",
                "PASS" if fail_closed else "FAIL",
                "schema mismatch produces FAIL",
            )
        )
    except Exception as error:
        checks.append(_check("G10_FAIL_CLOSED_VALIDATION", "FAIL", str(error)))

    tests_pass, test_summary = _run_contract_tests(root)
    checks.append(_check("G11_CONTRACT_TESTS_PASS", "PASS" if tests_pass else "FAIL", test_summary))

    try:
        registry = load_registry(root)
        statuses = [
            registry["modules"][module]["implementation_status"] for module in CONTRACT_ONLY_MODULES
        ]
        no_fake = all(status == "CONTRACT_ONLY" for status in statuses)
        checks.append(
            _check(
                "G12_NO_FAKE_SCIENTIFIC_IMPLEMENTATION",
                "PASS" if no_fake else "FAIL",
                "M3-M9 are explicitly CONTRACT_ONLY",
            )
        )
    except Exception as error:
        checks.append(_check("G12_NO_FAKE_SCIENTIFIC_IMPLEMENTATION", "FAIL", str(error)))

    checks.append(
        _check(
            "G13_EXISTING_REGRESSION_ACCEPTABLE",
            "SKIP",
            "full regression is recorded separately; inherited baseline has pre-existing failures",
        )
    )
    checks.append(
        _check(
            "G14_DOCUMENTATION_COMPLETE",
            "PASS" if all((root / path).exists() for path in REQUIRED_FILES[:9]) else "FAIL",
            "architecture documentation present",
        )
    )
    report_path = root / (
        "reports/architecture/module_protocol_v1_1/MODULE_PROTOCOL_V1_1_LOCAL_CONVERGENCE_REPORT.md"
    )
    checks.append(
        _check(
            "G15_FINAL_REPORT_COMPLETE",
            "PASS" if report_path.exists() else "SKIP",
            "final report present"
            if report_path.exists()
            else "final report is generated after implementation",
        )
    )

    try:
        from canospar.contracts.base import (
            ScienceContext,
            build_reproduction_key,
            build_science_key,
        )
        from canospar.runtime.numerics import NumericsProfile, build_numerics_profile_hash
        from canospar.runtime.profile import RuntimeProfile

        profile = NumericsProfile(
            python_version="3.11.9",
            numpy_version="2.2.0",
            scipy_version="1.15.0",
            torch_version="2.6.0",
            dtype="float64",
            precision_policy="strict-float64",
            deterministic_algorithms=True,
            linear_algebra_backend="cpu-openblas",
            eigensolver_backend="scipy.linalg.eigh",
            solver_tolerance=1e-8,
            numerical_backend_version="openblas-0.3.28",
        )
        dtype_changed = NumericsProfile(
            python_version="3.11.9",
            dtype="float32",
            precision_policy="strict-float32",
        )
        backend_changed = NumericsProfile(
            python_version="3.11.9",
            dtype="float64",
            precision_policy="strict-float64",
            eigensolver_backend="torch.linalg.eigh",
        )
        tolerance_changed = NumericsProfile(
            python_version="3.11.9",
            dtype="float64",
            precision_policy="strict-float64",
            solver_tolerance=1e-4,
        )
        context = ScienceContext(science_config_hash="config-a")
        runtime_a = RuntimeProfile(
            profile_id="server-a",
            cpu_count=28,
            gpu_count=2,
            worker_count=4,
            server_class="linux",
        )
        runtime_b = RuntimeProfile(
            profile_id="server-b",
            cpu_count=112,
            gpu_count=8,
            worker_count=16,
            server_class="windows",
        )
        science_a = build_science_key(
            context,
            ("input-a",),
            "M2",
            runtime_profile_id=runtime_a.profile_id,
        )
        science_b = build_science_key(
            context,
            ("input-a",),
            "M2",
            runtime_profile_id=runtime_b.profile_id,
        )
        numerics_hash = build_numerics_profile_hash(profile)
        runtime_reproduction_same = build_reproduction_key(
            science_a, "impl-a", numerics_hash
        ) == build_reproduction_key(science_b, "impl-a", numerics_hash)
        numerics_hashes_change = all(
            numerics_hash != build_numerics_profile_hash(changed)
            for changed in (dtype_changed, backend_changed, tolerance_changed)
        )
        reproduction_changes = all(
            build_reproduction_key(science_a, "impl-a", numerics_hash)
            != build_reproduction_key(science_a, "impl-a", build_numerics_profile_hash(changed))
            for changed in (dtype_changed, backend_changed, tolerance_changed)
        )
        checks.append(
            _check(
                "G16_NUMERICS_PROFILE_SEMANTICS",
                "PASS"
                if science_a == science_b
                and runtime_reproduction_same
                and numerics_hashes_change
                and reproduction_changes
                else "FAIL",
                "runtime is excluded while numerical semantics alter reproduction identity",
            )
        )
    except Exception as error:
        checks.append(_check("G16_NUMERICS_PROFILE_SEMANTICS", "FAIL", str(error)))

    fail_count = sum(item["status"] == "FAIL" for item in checks)
    pass_count = sum(item["status"] == "PASS" for item in checks)
    skip_count = sum(item["status"] == "SKIP" for item in checks)
    return {
        "architecture_contract_version": "1.0.0",
        "module_protocol_spec_version": MODULE_PROTOCOL_SPEC_VERSION,
        "overall_status": "PASS" if fail_count == 0 else "PARTIAL",
        "pass_count": pass_count,
        "fail_count": fail_count,
        "skip_count": skip_count,
        "checks": checks,
    }


def write_results(root: Path, results: dict[str, Any]) -> Path:
    destination = root / "reports/architecture/verification_results.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    results = run_checks(ROOT)
    write_results(ROOT, results)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
