"""CPU-only Week 2-4 metadata workflow.

The default ``all`` rule remains Week 1-only.  Private metadata is reachable
only through the explicit ``metadata_private`` target and an environment gate.
"""

import os
import subprocess
import sys


_FIXTURE_ROOT = "tests/fixtures/metadata"
_FIXTURE_ARTIFACTS = "artifacts/manifests/week02_04/fixture"
_FIXTURE_REPORTS = "reports/data_qc/week02_04/fixture"
_PYTHON = sys.executable


rule fixture_hcp_discovery:
    input:
        config=f"{_FIXTURE_ROOT}/hcp_synthetic/hcp.yaml",
    output:
        f"{_FIXTURE_ARTIFACTS}/source_inventory/hcp/metadata_discovery.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.metadata_discovery "
            "--config {input.config} "
            f"--metadata-root {_FIXTURE_ROOT}/hcp_synthetic/data "
            f"--output-dir {_FIXTURE_ARTIFACTS}/source_inventory/hcp"
        )


rule fixture_ppmi_discovery:
    input:
        config=f"{_FIXTURE_ROOT}/ppmi_synthetic/ppmi.yaml",
    output:
        f"{_FIXTURE_ARTIFACTS}/source_inventory/ppmi/metadata_discovery.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.metadata_discovery "
            "--config {input.config} "
            f"--metadata-root {_FIXTURE_ROOT}/ppmi_synthetic/data "
            f"--output-dir {_FIXTURE_ARTIFACTS}/source_inventory/ppmi"
        )


rule fixture_hcp_manifest:
    input:
        discovery=f"{_FIXTURE_ARTIFACTS}/source_inventory/hcp/metadata_discovery.json",
        config=f"{_FIXTURE_ROOT}/hcp_synthetic/hcp.yaml",
    output:
        manifest=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_manifest.json",
        exclusions=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_exclusions.json",
        audit=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_audit.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_provenance.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.hcp_manifest "
            "--config {input.config} "
            f"--metadata-root {_FIXTURE_ROOT}/hcp_synthetic/data "
            f"--output-dir {_FIXTURE_ARTIFACTS}/hcp"
        )


rule fixture_ppmi_manifest:
    input:
        discovery=f"{_FIXTURE_ARTIFACTS}/source_inventory/ppmi/metadata_discovery.json",
        config=f"{_FIXTURE_ROOT}/ppmi_synthetic/ppmi.yaml",
    output:
        manifest=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_manifest.json",
        exclusions=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_exclusions.json",
        audit=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_sequence_audit.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_provenance.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.ppmi_manifest "
            "--config {input.config} "
            f"--metadata-root {_FIXTURE_ROOT}/ppmi_synthetic/data "
            f"--output-dir {_FIXTURE_ARTIFACTS}/ppmi"
        )


rule fixture_hcp_validation:
    input:
        manifest=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_manifest.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_provenance.json",
        builder_audit=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_audit.json",
        schema="configs/data/manifest_schema.yaml",
    output:
        f"{_FIXTURE_REPORTS}/hcp/manifest_validation_summary.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.validate_manifest "
            "--manifest {input.manifest} "
            "--schema {input.schema} "
            f"--output-dir {_FIXTURE_REPORTS}/hcp"
        )


rule fixture_ppmi_validation:
    input:
        manifest=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_manifest.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_provenance.json",
        sequence_audit=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_sequence_audit.json",
        schema="configs/data/manifest_schema.yaml",
    output:
        f"{_FIXTURE_REPORTS}/ppmi/manifest_validation_summary.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.validate_manifest "
            "--manifest {input.manifest} "
            "--schema {input.schema} "
            f"--output-dir {_FIXTURE_REPORTS}/ppmi"
        )


rule fixture_hcp_audit:
    input:
        manifest=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_manifest.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_provenance.json",
        builder_audit=f"{_FIXTURE_ARTIFACTS}/hcp/hcp_audit.json",
        schema="configs/data/manifest_schema.yaml",
    output:
        f"{_FIXTURE_REPORTS}/hcp/hcp_initial_audit.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.audit_manifest "
            "--manifest {input.manifest} --dataset hcp "
            f"--output-dir {_FIXTURE_REPORTS}/hcp"
        )


rule fixture_ppmi_audit:
    input:
        manifest=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_manifest.json",
        provenance=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_provenance.json",
        sequence_audit=f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_sequence_audit.json",
        config=f"{_FIXTURE_ROOT}/ppmi_synthetic/ppmi.yaml",
        targets=f"{_FIXTURE_ROOT}/ppmi_synthetic/ppmi_targets.yaml",
    output:
        audit=f"{_FIXTURE_REPORTS}/ppmi/ppmi_initial_audit.json",
        targets=f"{_FIXTURE_REPORTS}/ppmi/ppmi_target_candidate_audit.json",
        gate=f"{_FIXTURE_REPORTS}/ppmi/ppmi_task_gate.json",
    shell:
        (
            f"{_PYTHON} -m canospar.data.audit_manifest "
            "--manifest {input.manifest} --dataset ppmi "
            "--config {input.config} "
            f"--metadata-root {_FIXTURE_ROOT}/ppmi_synthetic/data "
            f"--output-dir {_FIXTURE_REPORTS}/ppmi"
        )


rule metadata_fixture:
    input:
        f"{_FIXTURE_ARTIFACTS}/hcp/hcp_manifest.json",
        f"{_FIXTURE_ARTIFACTS}/hcp/hcp_provenance.json",
        f"{_FIXTURE_ARTIFACTS}/hcp/hcp_audit.json",
        f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_manifest.json",
        f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_provenance.json",
        f"{_FIXTURE_ARTIFACTS}/ppmi/ppmi_sequence_audit.json",
        f"{_FIXTURE_REPORTS}/hcp/manifest_validation_summary.json",
        f"{_FIXTURE_REPORTS}/ppmi/manifest_validation_summary.json",
        f"{_FIXTURE_REPORTS}/hcp/hcp_initial_audit.json",
        f"{_FIXTURE_REPORTS}/ppmi/ppmi_initial_audit.json",
        f"{_FIXTURE_REPORTS}/ppmi/ppmi_target_candidate_audit.json",
        f"{_FIXTURE_REPORTS}/ppmi/ppmi_task_gate.json",


rule metadata_private:
    output:
        hcp="artifacts/manifests/week02_04/private/hcp/hcp_manifest.json",
        ppmi="artifacts/manifests/week02_04/private/ppmi/ppmi_manifest.json",
    run:
        if os.environ.get("CANOSPAR_ALLOW_PRIVATE_METADATA") != "1":
            raise ValueError(
                "metadata_private requires CANOSPAR_ALLOW_PRIVATE_METADATA=1"
            )
        metadata_root = os.environ.get("CANOSPAR_METADATA_ROOT", "data/metadata")
        commands = (
            (
                sys.executable,
                "-m",
                "canospar.data.hcp_manifest",
                "--config",
                "configs/data/hcp.yaml",
                "--metadata-root",
                metadata_root,
                "--output-dir",
                "artifacts/manifests/week02_04/private/hcp",
            ),
            (
                sys.executable,
                "-m",
                "canospar.data.ppmi_manifest",
                "--config",
                "configs/data/ppmi.yaml",
                "--metadata-root",
                metadata_root,
                "--output-dir",
                "artifacts/manifests/week02_04/private/ppmi",
            ),
        )
        for command in commands:
            subprocess.run(command, check=True)


rule verify_week2_4:
    output:
        "reports/data_qc/week02_04/verification_results.json",
    shell:
        f"{_PYTHON} scripts/verify_week2_4.py"
