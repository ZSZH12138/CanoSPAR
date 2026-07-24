# Software and container versions

`model.def` is a CPU-only reproducibility placeholder, not evidence of a
container build. Week 1 does not build, publish, pull, or run an image.

## A. Week 1 software actually installed and verified

The following versions come from the isolated `canospar-week1` environment on
`win-64`; `environment.lock.yml` records the complete resolved environment.

| Component | Verified version |
| --- | --- |
| Python | `3.11.15` |
| PyTorch | `2.12.1+cpu` (`torch.version.cuda is None`) |
| PyTorch Geometric | `2.8.0.post1` (base package only) |
| NumPy | `2.4.6` |
| SciPy | `1.17.1` |
| scikit-learn | `1.9.0` |
| Hydra Core | `1.3.4` |
| OmegaConf | `2.3.1` |
| PyYAML | `6.0.3` |
| entmax | `1.3` |
| TensorBoard | `2.21.0` |
| psutil | `7.2.2` |
| Snakemake | `9.23.1` |
| pytest / pytest-cov | `8.4.2` / `6.3.0` |
| Ruff / mypy / pre-commit | `0.15.22` / `1.20.2` / `4.6.1` |
| build / types-PyYAML | `1.5.0` / `6.0.12.20260518` |

## B. Planned later, not installed in Week 1

MRIQC, fMRIPrep, QSIPrep, QSIRecon, FreeSurfer, and MRtrix3 are names of
possible later workflow components only. No version, image, binary, or digest
for any of them was installed, downloaded, resolved, or verified this week.
Their exact version, upstream source, license constraints, and immutable image
digest must be selected and recorded only when a later approved phase requires
them.

## C. Unresolved container digest

| Declaration | Week 1 status |
| --- | --- |
| Base image reference | `python:3.11.11-slim-bookworm` |
| Immutable base image digest | `null` — not resolved in Week 1 |
| Built CanoSPAR image digest | `null` — no image was built in Week 1 |

The base tag is deliberately not `latest`, but it is not an immutable digest.
Before a future container build, resolve and review the base-image digest,
replace the definition reference with that digest, and record the resulting
image digest here. No neuroimaging, MRI, CUDA, or GPU tooling is installed or
invoked by the Week 1 definition.
