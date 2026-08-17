# Module Contracts v1

The public module boundary is src/canospar/api. P0 and M0-M9 receive typed inputs and return named artifact families. M4-M9 expose contract-only protocols and must not return fabricated scientific outputs.

M3 consumes SpectrumArtifact from M2 and never recalculates a spectrum from GraphData. M4 consumes canonical bands from M3. M6 consumes TokenBundle from M5. M7 consumes RoleBundle from M6. M9 is read-only and never retrains a model.
