"""Run the ordered Week 1 acceptance checks and persist machine-readable evidence."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Literal, Protocol, TypeAlias

Status: TypeAlias = Literal["PASS", "FAIL", "SKIP_WITH_REASON"]

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPORT_PATH = _PROJECT_ROOT / "reports" / "week1" / "verification_results.json"
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[a-z]:[\\/][^\r\n\"']+")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_:])/[^\r\n\"']+")

_STRUCTURE_CHECK = dedent(
    """
    from pathlib import Path

    required = (
        ".github/workflows/ci.yml",
        ".pre-commit-config.yaml",
        ".gitignore",
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "environment.yml",
        "environment.lock.yml",
        "configs/config.yaml",
        "configs/data/toy.yaml",
        "configs/graph/toy.yaml",
        "configs/model/smoke.yaml",
        "configs/experiment/smoke.yaml",
        "configs/paths/local.example.yaml",
        "containers/model.def",
        "containers/versions.md",
        "docs/experiment_contract.md",
        "docs/decisions/README.md",
        "src/canospar/__init__.py",
        "src/canospar/data/__init__.py",
        "src/canospar/data/contracts.py",
        "src/canospar/graph/__init__.py",
        "src/canospar/spectral/__init__.py",
        "src/canospar/models/__init__.py",
        "src/canospar/training/__init__.py",
        "src/canospar/evaluation/__init__.py",
        "src/canospar/utils/__init__.py",
        "src/canospar/utils/config.py",
        "src/canospar/utils/hardware_gate.py",
        "src/canospar/utils/hashing.py",
        "src/canospar/utils/paths.py",
        "src/canospar/utils/provenance.py",
        "src/canospar/utils/smoke_test.py",
        "scripts/bootstrap.ps1",
        "scripts/bootstrap.sh",
        "scripts/check_no_hardcoded_paths.py",
        "scripts/verify_week1.py",
        "tests/fixtures",
        "tests/unit",
        "tests/unit/test_contracts.py",
        "tests/unit/test_config.py",
        "tests/unit/test_hashing.py",
        "tests/unit/test_paths.py",
        "tests/unit/test_smoke_components.py",
        "tests/integration",
        "tests/integration/test_smoke_cli.py",
        "tests/regression",
        "workflow/Snakefile",
        "workflow/rules/smoke.smk",
        "reports/data_qc",
        "reports/graph_qc",
        "reports/experiments",
        "reports/final",
        "reports/week1",
        "reports/week1/hardware_gate.json",
        "reports/week1/BLOCKER_REPORT.md",
        "reports/week1/WEEK1_IMPLEMENTATION_REPORT.md",
        "artifacts",
    )
    missing = [item for item in required if not Path(item).exists()]
    assert not missing, f"Missing required paths: {missing}"
    """
).strip()

_CORE_IMPORT_CHECK = dedent(
    """
    import importlib.metadata

    import entmax
    import hydra
    import numpy
    import omegaconf
    import psutil
    import scipy
    import sklearn
    import snakemake
    import tensorboard
    import torch
    import torch_geometric
    import yaml

    import canospar
    import canospar.data.contracts
    import canospar.utils.smoke_test

    for distribution in (
        "build",
        "mypy",
        "pre-commit",
        "pytest",
        "pytest-cov",
        "ruff",
        "types-PyYAML",
    ):
        assert importlib.metadata.version(distribution)
    """
).strip()

_ARTIFACT_CHECK = dedent(
    """
    import json
    from pathlib import Path

    from omegaconf import OmegaConf

    from canospar.utils.hashing import hash_yaml_config

    artifact_dir = Path("artifacts/smoke")
    config_path = artifact_dir / "resolved_config.yaml"
    provenance_path = artifact_dir / "provenance.json"
    report_path = artifact_dir / "smoke_report.json"
    expected = (config_path, provenance_path, report_path)
    missing = [path.as_posix() for path in expected if not path.is_file()]
    assert not missing, f"Missing smoke artifacts: {missing}"
    config_hash = hash_yaml_config(OmegaConf.load(config_path))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    smoke_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert config_hash == provenance["config_hash"] == smoke_report["config_hash"]
    """
).strip()

_PROVENANCE_CHECK = dedent(
    """
    import json
    from pathlib import Path

    from scripts.check_no_hardcoded_paths import POSIX_USER_PATH, WINDOWS_USER_PATH

    from canospar.utils.provenance import _is_path_value

    record = json.loads(
        Path("artifacts/smoke/provenance.json").read_text(encoding="utf-8")
    )
    required = {
        "timestamp_utc",
        "contract_version",
        "commit_hash",
        "commit_hash_status",
        "git_dirty",
        "config_hash",
        "dataset_manifest_hash",
        "dataset_manifest_hash_status",
        "container_digest",
        "container_digest_status",
        "random_seed",
        "python_version",
        "platform",
        "torch_version",
        "torch_geometric_version",
        "device",
        "cuda_available",
        "command",
    }
    missing = sorted(required.difference(record))
    assert not missing, f"Missing provenance fields: {missing}"
    assert record["timestamp_utc"].endswith("Z")
    assert record["device"] == "cpu"
    assert record["cuda_available"] is False
    assert record["dataset_manifest_hash"] is None
    assert record["dataset_manifest_hash_status"] == "not_available_in_week1"
    assert record["dataset_manifest_hash_reason"]
    assert record["container_digest"] is None
    assert record["container_digest_status"] == "not_available_in_week1"
    assert record["container_digest_reason"]
    serialized = json.dumps(record).casefold()
    forbidden = ("username", "hostname", "token", '"cwd"')
    assert not any(value in serialized for value in forbidden)
    assert WINDOWS_USER_PATH.search(serialized) is None
    assert POSIX_USER_PATH.search(serialized) is None
    assert isinstance(record["command"], list)
    assert not any(_is_path_value(str(token)) for token in record["command"])
    """
).strip()

_GITIGNORE_CHECK = dedent(
    """
    import subprocess

    for candidate in ("artifacts/example.txt", "data/example.nii.gz"):
        result = subprocess.run(
            ["git", "check-ignore", "--quiet", candidate],
            check=False,
        )
        assert result.returncode == 0, f"Git does not ignore {candidate}"
    """
).strip()


@dataclass(frozen=True)
class CheckSpec:
    """One ordered acceptance check."""

    name: str
    command: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CheckResult:
    """Serializable outcome plus diagnostics retained for console reporting."""

    name: str
    status: Status
    required: bool
    returncode: int | None
    reason: str | None
    stdout: str = ""
    stderr: str = ""

    def as_record(self) -> dict[str, str | bool | int | None]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "returncode": self.returncode,
            "reason": self.reason,
        }


class Runner(Protocol):
    """The subprocess surface injected by unit tests."""

    def __call__(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]: ...


def _subprocess_runner(
    command: Sequence[str],
    *,
    cwd: Path,
    capture_output: bool,
    text: bool,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=capture_output,
        text=text,
        check=check,
    )


def _sanitize_diagnostic(text: str) -> str:
    """Redact absolute paths before diagnostics reach console or JSON evidence."""
    sanitized = _WINDOWS_ABSOLUTE_PATH.sub("<path>", text)
    return _POSIX_ABSOLUTE_PATH.sub("<path>", sanitized)


CHECKS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "python_version",
        (
            sys.executable,
            "-c",
            "import sys; assert sys.version_info[:2] == (3, 11), sys.version",
        ),
    ),
    CheckSpec("repository_structure", (sys.executable, "-c", _STRUCTURE_CHECK)),
    CheckSpec(
        "cpu_torch",
        (
            sys.executable,
            "-c",
            (
                "import torch; "
                "assert torch.version.cuda is None, torch.version.cuda; "
                "assert not torch.cuda.is_available(); "
                "assert torch.ones(1).device.type == 'cpu'"
            ),
        ),
    ),
    CheckSpec(
        "core_imports",
        (sys.executable, "-c", _CORE_IMPORT_CHECK),
    ),
    CheckSpec(
        "hydra_config",
        (
            sys.executable,
            "-c",
            (
                "from canospar.utils.config import compose_config; "
                "config = compose_config(); "
                "assert config.device == 'cpu'; "
                "assert config.paths.output_dir == 'artifacts/smoke'"
            ),
        ),
    ),
    CheckSpec(
        "data_contracts",
        (sys.executable, "-m", "pytest", "-q", "tests/unit/test_contracts.py"),
    ),
    CheckSpec(
        "smoke_execution",
        (sys.executable, "-m", "canospar.utils.smoke_test"),
    ),
    CheckSpec("smoke_artifacts", (sys.executable, "-c", _ARTIFACT_CHECK)),
    CheckSpec("provenance", (sys.executable, "-c", _PROVENANCE_CHECK)),
    CheckSpec(
        "git_ignore",
        (sys.executable, "-c", _GITIGNORE_CHECK),
    ),
    CheckSpec(
        "hardcoded_path_scan",
        (
            sys.executable,
            "scripts/check_no_hardcoded_paths.py",
            "--root",
            ".",
        ),
    ),
    CheckSpec("ruff", (sys.executable, "-m", "ruff", "check", "src", "tests")),
    CheckSpec("mypy", (sys.executable, "-m", "mypy", "src/canospar")),
    CheckSpec(
        "unit_tests",
        (sys.executable, "-m", "pytest", "-q", "tests/unit"),
    ),
    CheckSpec(
        "integration_tests",
        (sys.executable, "-m", "pytest", "-q", "tests/integration"),
    ),
    CheckSpec(
        "coverage",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "--cov=canospar",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
            "tests",
        ),
    ),
    CheckSpec(
        "snakemake_dry_run",
        (
            sys.executable,
            "-m",
            "snakemake",
            "-n",
            "-s",
            "workflow/Snakefile",
        ),
    ),
)


def execute_check(spec: CheckSpec, project_root: Path, runner: Runner) -> CheckResult:
    """Execute one check without raising away its diagnostic evidence."""
    try:
        completed = runner(
            spec.command,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as error:
        status: Status = "FAIL" if spec.required else "SKIP_WITH_REASON"
        return CheckResult(
            name=spec.name,
            status=status,
            required=spec.required,
            returncode=None,
            reason=f"{type(error).__name__}: {_sanitize_diagnostic(str(error))}",
        )

    safe_stdout = _sanitize_diagnostic(completed.stdout)
    safe_stderr = _sanitize_diagnostic(completed.stderr)
    if completed.returncode == 0:
        return CheckResult(
            name=spec.name,
            status="PASS",
            required=spec.required,
            returncode=completed.returncode,
            reason=None,
            stdout=safe_stdout,
            stderr=safe_stderr,
        )

    status = "FAIL" if spec.required else "SKIP_WITH_REASON"
    return CheckResult(
        name=spec.name,
        status=status,
        required=spec.required,
        returncode=completed.returncode,
        reason=f"subprocess exited with code {completed.returncode}",
        stdout=safe_stdout,
        stderr=safe_stderr,
    )


def _print_result(index: int, result: CheckResult) -> None:
    print(f"{index:02d}. {result.name}: {result.status}")
    if result.reason is not None:
        print(f"    {result.reason}", file=sys.stderr)
    if result.stdout.strip() and result.status != "PASS":
        print(result.stdout.rstrip(), file=sys.stderr)
    if result.stderr.strip() and result.status != "PASS":
        print(result.stderr.rstrip(), file=sys.stderr)


def _write_report(results: Sequence[CheckResult], report_path: Path) -> None:
    summary = {
        status: sum(result.status == status for result in results)
        for status in ("FAIL", "PASS", "SKIP_WITH_REASON")
    }
    required_failed = any(result.required and result.status == "FAIL" for result in results)
    payload = {
        "overall_status": "FAIL" if required_failed else "PASS",
        "summary": summary,
        "checks": [result.as_record() for result in results],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_verification(
    *,
    project_root: Path,
    report_path: Path,
    runner: Runner = _subprocess_runner,
) -> int:
    """Run all checks in order, write the report, and return a process status."""
    results: list[CheckResult] = []
    for index, spec in enumerate(CHECKS, start=1):
        result = execute_check(spec, project_root, runner)
        results.append(result)
        _print_result(index, result)

    _write_report(results, report_path)
    return int(any(result.required and result.status == "FAIL" for result in results))


def main() -> int:
    """Run verification relative to the repository containing this script."""
    return run_verification(project_root=_PROJECT_ROOT, report_path=_REPORT_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
