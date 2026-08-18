"""CPU exact symmetric eigensolver for M2 Laplacians."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import torch

from canospar.contracts.base import ScienceContext
from canospar.contracts.errors import ContractViolation, NumericalValidationError
from canospar.contracts.spectral import LaplacianArtifact, M2Spec, SpectrumArtifact

from .lineage import make_meta, numerics_profile, solver_tolerance, tensor_content_hash


@dataclass(frozen=True)
class ExactSpectrum:
    eigenvalues: torch.Tensor
    eigenvectors: torch.Tensor
    residual_max: float
    orthogonality_residual_max: float


def compute_exact_spectrum(laplacian: LaplacianArtifact, spec: M2Spec) -> ExactSpectrum:
    if not isinstance(laplacian, LaplacianArtifact):
        raise ContractViolation("laplacian must be LaplacianArtifact")
    payload = laplacian.payload.detach().cpu().to(torch.float64)
    if payload.dim() != 2 or payload.size(0) != payload.size(1):
        raise ContractViolation("laplacian payload must be square")
    if not bool(torch.isfinite(payload).all()):
        raise NumericalValidationError("laplacian must be finite")
    if not torch.equal(payload, payload.T):
        raise NumericalValidationError("laplacian must be symmetric")
    tolerance = solver_tolerance(spec)
    eigenvalues_np, eigenvectors_np = np.linalg.eigh(payload.numpy())
    eigenvalues = torch.from_numpy(np.asarray(eigenvalues_np, dtype=np.float64)).clone()
    eigenvectors = torch.from_numpy(np.asarray(eigenvectors_np, dtype=np.float64)).clone()
    if eigenvalues.dim() != 1 or eigenvalues.numel() != payload.size(0):
        raise NumericalValidationError("eigensolver must return N finite eigenvalues")
    if not bool(torch.isfinite(eigenvalues).all()):
        raise NumericalValidationError("eigenvalues must be finite")
    if bool((eigenvalues[:-1] > eigenvalues[1:]).any()):
        raise NumericalValidationError("eigenvalues must be sorted ascending")
    if float(eigenvalues.min()) < -tolerance or float(eigenvalues.max()) > 2.0 + tolerance:
        raise NumericalValidationError("normalized Laplacian eigenvalues must lie in [0, 2]")
    residual = payload @ eigenvectors - eigenvectors * eigenvalues.unsqueeze(0)
    residual_max = float(residual.abs().max().item()) if residual.numel() else 0.0
    orthogonality = eigenvectors.T @ eigenvectors - torch.eye(payload.size(0), dtype=torch.float64)
    orthogonality_max = float(orthogonality.abs().max().item()) if orthogonality.numel() else 0.0
    bound = max(tolerance * 100.0, 1e-10)
    if residual_max > bound:
        raise NumericalValidationError(
            f"eigendecomposition residual exceeds tolerance: {residual_max}"
        )
    if orthogonality_max > bound:
        raise NumericalValidationError(
            f"eigenvector orthogonality residual exceeds tolerance: {orthogonality_max}"
        )
    return ExactSpectrum(eigenvalues, eigenvectors, residual_max, orthogonality_max)


def build_spectrum_artifact(
    laplacian: LaplacianArtifact,
    spec: M2Spec,
    context: ScienceContext,
) -> tuple[SpectrumArtifact, ExactSpectrum]:
    result = compute_exact_spectrum(laplacian, spec)
    content_hash = tensor_content_hash(result.eigenvalues)
    meta = make_meta(
        artifact_type="SpectrumArtifact",
        context=context,
        content_sha256=content_hash,
        input_artifact_ids=(laplacian.meta.artifact_id,),
        input_content_hashes=(laplacian.meta.content_sha256,),
        numerics_profile_hash=numerics_profile(spec).numerics_profile_hash,
        graph_key=laplacian.graph_key,
        created_at_utc=laplacian.meta.created_at_utc,
    )
    return SpectrumArtifact(
        meta=meta, graph_key=laplacian.graph_key, eigenvalues=result.eigenvalues
    ), result
