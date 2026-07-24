"""The sole executable workflow rule for Week 1."""

rule smoke_test:
    output:
        "artifacts/smoke/resolved_config.yaml",
        "artifacts/smoke/provenance.json",
        "artifacts/smoke/smoke_report.json",
    shell:
        "python -m canospar.utils.smoke_test"
