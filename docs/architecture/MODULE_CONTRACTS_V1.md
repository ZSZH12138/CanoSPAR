# Module Contracts v1

The public module boundary is `src/canospar/api`. The current frozen interface source is [`CANOSPAR_MODULE_PROTOCOL_SPEC_V1.md`](CANOSPAR_MODULE_PROTOCOL_SPEC_V1.md), document version `1.1.0`. The superseded v1.0.0 document is retained at [`archive/CANOSPAR_MODULE_PROTOCOL_SPEC_V1_0_0.md`](archive/CANOSPAR_MODULE_PROTOCOL_SPEC_V1_0_0.md).

P0 and M0-M9 receive typed inputs and return named artifact families. M2 exposes the implemented Laplacian, exact spectrum, spectral statistics and QC path described by protocol v1.1.0; M3 exposes the implemented canonical mass coordinate and mass-space bands described by protocol v1.1.0. M4-M9 remain contract-only and must not return fabricated scientific outputs. M0, P0, and M1 remain existing/partial boundaries; the protocol revision does not claim their scientific implementation is complete.

M3 consumes SpectrumArtifact from M2 and never recalculates a spectrum from GraphData. M4 consumes canonical bands from M3. M6 consumes TokenBundle from M5. M7 consumes RoleBundle from M6. M9 is read-only and never retrains a model.
