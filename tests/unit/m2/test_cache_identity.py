from __future__ import annotations

from dataclasses import replace

from canospar.api.m2 import run_m2
from canospar.contracts.execution import CanonicalStatus, cache_is_eligible
from tests.integration.test_m2_synthetic_multigraph import _artifact, _context, _spec


def test_cache_requires_current_protocol_and_all_identity_fields() -> None:
    bundle = run_m2(_artifact(), _spec(), _context())
    receipt = bundle.receipt
    assert receipt is not None
    assert cache_is_eligible(
        expected_science_key=bundle.science_key,
        expected_reproduction_key=bundle.reproduction_key,
        artifact_hash=bundle.meta.content_sha256,
        receipt=receipt,
        validator_status="PASS",
    )
    assert not cache_is_eligible(
        expected_science_key=bundle.science_key,
        expected_reproduction_key=bundle.reproduction_key,
        artifact_hash=bundle.meta.content_sha256,
        receipt=replace(receipt, module_contract_version="1.0.0"),
        validator_status="PASS",
    )
    assert not cache_is_eligible(
        expected_science_key=bundle.science_key,
        expected_reproduction_key=bundle.reproduction_key,
        artifact_hash=bundle.meta.content_sha256,
        receipt=replace(receipt, canonical_status=CanonicalStatus.INVALIDATED),
        validator_status="PASS",
    )
    assert not cache_is_eligible(
        expected_science_key=bundle.science_key,
        expected_reproduction_key=bundle.reproduction_key,
        artifact_hash=bundle.meta.content_sha256,
        receipt=replace(receipt, validator_status="FAIL"),
        validator_status="PASS",
    )
