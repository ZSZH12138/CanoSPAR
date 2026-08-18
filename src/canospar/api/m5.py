"""M5 band tokenization API boundary."""

from __future__ import annotations

from canospar.contracts.bands import BandSignalBundle
from canospar.contracts.base import ScienceContext
from canospar.contracts.tokens import TokenBundle, TokenizationSpec
from canospar.validators.base import ValidationReport

from ._contract_only import contract_only


def tokenize_bands(
    band_signals: BandSignalBundle,
    spec: TokenizationSpec,
    context: ScienceContext,
) -> TokenBundle:
    del band_signals, spec, context
    raise contract_only("M5")


def validate_token_bundle(tokens: TokenBundle) -> ValidationReport:
    del tokens
    raise contract_only("M5")
