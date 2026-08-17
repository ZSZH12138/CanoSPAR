# Artifact Contracts v1

All formal artifacts carry ArtifactMeta and use immutable, deterministic identity.

Core artifacts: DatasetManifestArtifact, SplitRegistryArtifact, TaskDefinitionArtifact, ImagingInputBundle, ROIAlignedSample, MultiGraphArtifact, SpectralBundle, CanonicalSpectrumBundle, BandSignalBundle, TokenBundle, RoleBundle, RoutingBundle, SampleEmbedding, PredictionBundle, LossBundle, and EvaluationBundle.

Stable keys are GraphKey(subject, visit, modality, relation), BandKey(graph_key, band_id), and TokenKey(band_key, token_id). Parent keys must survive module boundaries and mismatches fail closed.

GraphData and BrainMultiGraphSample remain the payload objects used by existing code. Artifact wrappers add provenance without changing their fields.
