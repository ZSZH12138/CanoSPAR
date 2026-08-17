# Runtime Boundary v1

`RuntimeProfile` describes **how, where, and with how many resources** a task runs: CPU, RAM, GPU count, worker/thread limits, container, scheduler, transport, server class, and other operational placement. These values belong to L4 and never enter scientific module APIs or `science_key`.

`NumericsProfile` describes **which numerical semantics** produce a result. It is immutable and separately versioned through `numerics_profile_schema_version`. Its identity includes dtype and precision policy, deterministic-algorithm settings, linear algebra/eigensolver backends, solver tolerance, numerical library versions, and CUDA/backend versions when they participate in numerical computation. Its canonical hash is `numerics_profile_hash`, which participates in `reproduction_key`.

The separation is intentional:

- changing CPU/GPU count, RAM, worker count, hostname/server class, Bita, SSH, WebTerminal, or scheduler concurrency does not change scientific identity when implementation and numerical identity are unchanged;
- changing float precision, eigensolver backend, numerical library identity, deterministic setting, or solver tolerance changes `numerics_profile_hash` and therefore `reproduction_key`.

Existing Week5-7 lifecycle, package, monitor, Bita handoff, SSH, and MRIQC v2 code is preserved and indexed as runtime evidence. This architecture task does not start a server or transfer data.
