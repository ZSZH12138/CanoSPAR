# Execution and Lineage Contract v1

Execution objects are separate from scientific artifacts. `ModuleRunResult` carries canonical status, native status, optional artifact, receipt, and issues. `CompletionReceipt` records module/version, input/output IDs and hashes, `science_key`, `reproduction_key`, runtime profile ID, validator status, issue codes, and timestamps.

`science_key` is built only from scientific contract/version, input content hashes, science configuration, dataset manifest, split, and seed. `reproduction_key` additionally binds implementation identity and the canonical `numerics_profile_hash`. `RuntimeProfile` is recorded for execution provenance but is not itself a scientific or numerical identity.

A cache is eligible only when all of the following pass: expected `science_key`, expected `reproduction_key`, output artifact hash, receipt status `PASS`/`READY`, and validator status `PASS`. Any missing or mismatched condition fails closed. Same `science_key` with a different `reproduction_key` is not automatically reusable.
