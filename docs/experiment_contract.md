# Experiment contract

Contract version: `1.0.0`

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
4. **HCP family boundary.** HCP records are grouped by `Family_ID`; members of
   one family must never cross training, validation, or test partitions.
5. **PPMI subject boundary.** PPMI records are grouped by `subject_id`; every
   visit from one subject must remain in the same partition.
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
    restricted data—including derived files that cannot be redistributed—must
    never be committed to Git. Only non-sensitive manifests, hashes, schemas,
    and generated smoke fixtures are permitted.
15. **Versioned contract changes.** Any change to this contract requires an
    architecture decision record in `docs/decisions/` and a version increment.
    Every experiment artifact and metadata record must include
    `contract_version` with the exact version used for that run.

Outputs remain confined to `artifacts/`. The Week 1 smoke run produces a
resolved configuration, provenance record, and smoke report from small,
generated in-memory graphs; it is not a scientific evaluation.
