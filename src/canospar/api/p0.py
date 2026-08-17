"""P0 imaging data-plane API."""

from __future__ import annotations

from typing import Protocol

from canospar.contracts.base import ScienceContext
from canospar.contracts.imaging import ImagingInputBundle, ROIAlignedSample

from ._contract_only import contract_only


class P0Backend(Protocol):
    def prepare_imaging_sample(
        self,
        bundle: ImagingInputBundle,
        context: ScienceContext,
    ) -> ROIAlignedSample: ...


def prepare_imaging_sample(
    bundle: ImagingInputBundle,
    context: ScienceContext,
) -> ROIAlignedSample:
    del bundle, context
    raise contract_only("P0")
