# Execution and Lineage Contract v1

Execution objects are separate from scientific artifacts. ModuleRunResult carries canonical status, native status, optional artifact, receipt, and issues. CompletionReceipt records module/version, input/output IDs and hashes, science_key, reproduction_key, runtime profile ID, validator status, issue codes, and timestamps.

A cache is eligible only when all identity, artifact hash, receipt, and validator checks pass. Same science_key with a different reproduction_key is not automatically reusable.
