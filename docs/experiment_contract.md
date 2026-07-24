# Experiment contract

Contract version: `1.1.0`

This contract applies to every CanoSPAR experiment. Week 1 supplies only
CPU-only infrastructure; it does not implement or train a CanoSPAR model,
download data, or execute MRI tooling.

1. **Permanent test-set seal.** The test partition is permanently sealed from
   development, QC selection, feature design, hyperparameter tuning, and model
   selection. It may be opened only for an approved final evaluation after the
   analysis is locked; results remain immutable and cannot feed another design
   cycle.
2. **Split before learning.** Dataset partitions are assigned at the required
   grouping unit before any data-dependent preprocessing, feature selection,
   graph construction, or statistical estimation is fitted.
3. **Train-only preprocessing.** Every learned preprocessing operation is fitted
   exclusively on the training partition. Its frozen parameters may be applied
   to validation and test data, but must never be refitted on either partition.
4. **HCP official-unrelated-cohort boundary.** The preregistered HCP main
   protocol uses HCP-Young Adult 2025 Open Access imaging and an official
   unrelated-subject list as its candidate whitelist. The final cohort is
   frozen only after intersecting that whitelist with modality availability,
   target completeness, and QC results. Main-experiment partitions are
   subject-level (`group_id=subject_id`), and every sample records
   `cohort_source`, `unrelated_list_version`, and `kinship_control_method`.
   The official-list SHA-256 is recorded once in manifest-level provenance
   rather than duplicated in every sample.
   The full Open Access cohort may be used for pipeline debugging but must not
   be randomly split and reported as the main result. HCP-YA 2025 imaging must
   not be mixed with 2017 S1200 processed imaging. If Restricted Access is
   later approved, `Family_ID` grouping may be added only as an explicitly
   labeled extension experiment and must not replace this main protocol.
5. **PPMI subject boundary.** PPMI records are grouped by `subject_id`; every
   visit from one subject must remain in the same partition. PPMI samples use
   an explicit `not_applicable` value for unrelated-list metadata so that
   missing HCP-specific provenance is never confused with an omitted field.
6. **Label-free graph construction.** Graph topology, edge weights, node
   features, and graph filters must not use labels, targets, or statistics
   derived from them.
7. **Label-free QC selection.** QC rules and thresholds are declared in advance
   or selected with training data only. Test labels must never be consulted to
   choose, relax, or revise QC criteria.
8. **Seed provenance.** Every run records all random seeds used by Python,
   numerical libraries, sampling, splitting, and model code.
9. **Code provenance.** Every run records an immutable code revision or code
   hash together with dirty-worktree status; an unavailable value must be
   explicit rather than fabricated.
10. **Configuration provenance.** Every run stores its fully resolved
    configuration and a deterministic configuration hash.
11. **Manifest provenance.** Every run records the immutable input-manifest hash
    used to select data; missing manifests must be represented explicitly.
12. **Container provenance.** Containerized runs record an immutable image
    digest, never a mutable tag. Non-containerized runs record that the digest
    is unavailable and why.
13. **Portable paths only.** Source, configuration, scripts, documentation,
    tests, metadata, and reports must not contain a personal absolute path or
    real user name. Examples may use only explicit placeholders such as
    `C:/Users/<user>/artifacts` or `/home/<user>/artifacts`.
14. **Restricted data stays outside Git.** Raw, controlled-access, and otherwise
    non-redistributable data or derivatives must never be committed to Git.
    Version-controlled material is limited to non-sensitive manifests, hashes,
    schemas, approved documentation, summary reports, and synthetic or smoke
    fixtures that contain no restricted subject-level data.
15. **Versioned contract changes.** Any change to this contract requires an
    architecture decision record in `docs/decisions/` and a version increment.
    Every experiment artifact and metadata record must include
    `contract_version` with the exact version used for that run.

Runtime-generated intermediate data, graph caches, model checkpoints, and
other rerunnable artifacts remain confined to `artifacts/`. Curated,
non-sensitive documentation and summary reports may live under `docs/` and
`reports/` when intentionally version-controlled. The Week 1 smoke run
produces a resolved configuration, provenance record, and smoke report from
small, generated in-memory graphs; it is not a scientific evaluation.
