"""Helpers for explicit contract-only boundaries."""

from __future__ import annotations


def contract_only(module_id: str) -> NotImplementedError:
    return NotImplementedError(
        f"{module_id} scientific backend is CONTRACT_ONLY; no result is available"
    )


def m0_read_only() -> NotImplementedError:
    return NotImplementedError(
        "M0 loader is a read-only adapter boundary; it does not regenerate manifests"
    )
