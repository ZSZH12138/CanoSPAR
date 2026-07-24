# CanoSPAR

CanoSPAR is currently at the **Week 1 infrastructure stage**. This repository
provides a reproducible, CPU-only foundation for later research work; it does
**not** yet implement, train, or evaluate a CanoSPAR model.

## Week 1 scope

Week 1 provides:

- a Python package with deterministic hashing and safe output-path utilities;
- validated graph data contracts with defensive copying and real PyTorch
  Geometric conversion/batching;
- Hydra/OmegaConf configuration groups with a forced `device: cpu` policy;
- a deterministic three-graph smoke workflow using generated in-memory data;
- resolved-configuration, provenance, and smoke-report artifacts;
- unit and subprocess integration tests, quality checks, and a minimal
  Snakemake smoke DAG; and
- CPU-only environment declarations, a Windows-specific lock, and container
  metadata placeholders.

The following are deliberately **not implemented in Week 1**: the CanoSPAR
model, M1 or later research modules, model training, scientific evaluation,
dataset download or preprocessing, MRI/neuroimaging tools, and container image
build or publication. The smoke workflow is infrastructure verification, not a
scientific result.

## Requirements

- Python `>=3.11,<3.12` (use Python 3.11).
- Conda from the Anaconda installation selected for this project.
- A CPU is sufficient. A GPU, CUDA toolkit, and CUDA-enabled PyTorch wheel are
  neither required nor used.
- Run installation commands from the repository root because the project is
  installed in editable mode.

`environment.lock.yml` was exported from the actual verified
`canospar-week1` environment on **win-64**. It is platform-specific and must not
be used to reproduce Linux or macOS environments. It contains resolved package
versions and intentionally contains no local Conda prefix. Use
`environment.yml` for the portable installation path.

## Install on Windows PowerShell

Keep this project isolated from `base`. Replace `<ANACONDA_ROOT>` with the
Anaconda root selected for this machine; do not write that machine-specific
path into project files.

```powershell
Set-Location "<REPOSITORY_ROOT>"
$AnacondaRoot = "<ANACONDA_ROOT>"
$env:CONDA_EXE = Join-Path $AnacondaRoot "Scripts\conda.exe"
.\scripts\bootstrap.ps1
```

The bootstrap creates `canospar-week1` from `environment.yml`, runs
`pip check`, and verifies that the installed PyTorch build has no CUDA runtime.
To recreate the exact verified win-64 resolution instead, use the lock and then
install only the local editable package:

```powershell
$env:PIP_EXTRA_INDEX_URL = "https://download.pytorch.org/whl/cpu"
& $env:CONDA_EXE env create --file environment.lock.yml
& $env:CONDA_EXE run --name canospar-week1 python -m pip install --no-deps -e .
& $env:CONDA_EXE run --name canospar-week1 python -m pip check
```

## Install on Linux or macOS

Use the portable environment declaration, not the win-64 lock:

```sh
cd "<REPOSITORY_ROOT>"
export CONDA_EXE="<ANACONDA_ROOT>/bin/conda"
sh scripts/bootstrap.sh
```

The shell bootstrap creates the same isolated environment, performs dependency
checks, and asserts a CPU-only PyTorch installation. If `conda` is already on
`PATH`, `CONDA_EXE=conda sh scripts/bootstrap.sh` is sufficient.

## Verify the installation

Activate the environment first, or prefix commands with
`conda run --name canospar-week1`. Run unit and integration tests separately so
failures remain easy to locate:

```text
python -m pytest -q tests/unit
python -m pytest -q tests/integration
python -m pytest --cov=canospar --cov-report=term-missing
```

The deterministic smoke command builds three tiny CPU graphs, batches them with
the real PyTorch Geometric `DataLoader`, and writes three files under
`artifacts/smoke/`:

```text
python -m canospar.utils.smoke_test
```

The expected files are `resolved_config.yaml`, `provenance.json`, and
`smoke_report.json`. Inspect the minimal workflow without executing it with:

```text
snakemake -n -s workflow/Snakefile
```

## Configuration

`configs/config.yaml` composes the `data`, `graph`, `model`, `experiment`, and
`paths` groups. The checked-in defaults use only generated toy data, set a
reproducible seed, keep Hydra from changing the working directory, and force
CPU execution. Hydra-style overrides may be passed to the smoke command:

```text
python -m canospar.utils.smoke_test random_seed=11 graph.num_nodes=8 paths.output_dir=artifacts/smoke-seed11
```

`device=cuda`, parent traversal, personal absolute paths, restricted-data
directories, and project-local output paths outside `artifacts/` are rejected.

## Data, artifacts, and provenance

Do not place controlled, raw, or redistributability-restricted data in Git.
The repository ignores common dataset roots and neuroimaging/model files,
including `data/`, `raw/`, `derivatives/`, `bids/`, `hcp/`, and `ppmi/`.
Week 1 does not download or inspect real participant data.

Generated outputs belong under `artifacts/`. That tree is ignored by Git, so
smoke outputs and later run artifacts are not committed accidentally. Do not
force-add artifacts or restricted data.

Each smoke run writes a privacy-preserving provenance record containing:

- `timestamp_utc`, `contract_version`, `commit_hash`, and `git_dirty`;
- `config_hash`, `dataset_manifest_hash`, `container_digest`, and
  `random_seed`;
- `python_version`, `platform`, `torch_version`, and
  `torch_geometric_version`; and
- `device`, `cuda_available`, and a sanitized `command`.

Unavailable Git commits, dataset manifests, or container digests are recorded
as explicit null values with status/reason fields; they are never fabricated.
Provenance excludes usernames, hostnames, credentials, working directories,
and sensitive absolute paths. See `docs/experiment_contract.md` for the full
data-separation and reproducibility contract.

## Common installation problems

- **Conda is not found:** set `CONDA_EXE` to the executable below
  `<ANACONDA_ROOT>` as shown above. Do not install packages into `base`.
- **The environment already exists:** either use a new environment name with
  the bootstrap argument or intentionally update the existing isolated
  environment with `conda env update --name canospar-week1 --file
  environment.yml --prune`.
- **Python has the wrong version:** confirm `python --version` reports 3.11
  inside `canospar-week1`; recreating the isolated environment is safer than
  modifying `base`.
- **PyTorch resolves a CUDA build:** stop and recreate the environment from the
  supplied files. `python -c "import torch; print(torch.version.cuda)"` must
  print `None`.
- **A CPU wheel cannot be downloaded:** check proxy/TLS access to the official
  PyTorch CPU wheel index and retry; do not substitute a CUDA wheel.
- **Editable installation cannot find the project:** run the command from the
  repository root, where `pyproject.toml` is located.
- **Snakemake is not found:** confirm the `workflow` dependencies were
  installed and run the command inside `canospar-week1`.

## GPU policy

Week 1 requires no GPU. All smoke tensors are created on CPU,
`cuda_available` is recorded as `false`, and non-CPU configuration is rejected.
A detected physical GPU does not change this policy.

## License

License selection is pending. No open-source license has been granted, so the
repository may not be redistributed without explicit permission from the
copyright holder. See `LICENSE` for the current notice.
