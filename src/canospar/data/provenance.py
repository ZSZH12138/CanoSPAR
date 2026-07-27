"""Manifest-level provenance with no subject-level data."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from canospar.data.metadata_discovery import DiscoveredInput


def manifest_provenance(discovered: Mapping[str, DiscoveredInput]) -> dict[str, object]:
    """Return deterministic source hashes keyed by logical source name only."""
    inputs = {
        name: {"relative_path": item.relative_path, "sha256": item.sha256, "legacy": item.legacy}
        for name, item in sorted(discovered.items())
    }
    digest = hashlib.sha256(
        json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"contract_version": "1.1.0", "inputs": inputs, "input_manifest_hash": digest}
