"""Read-only, standard-library helpers for non-imaging metadata tables."""

from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest without retaining a table's contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_table(path: Path) -> list[dict[str, str]]:
    """Read a CSV as strings so leading-zero identifiers remain intact."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t" if path.suffix.casefold() == ".tsv" else ",")
        if reader.fieldnames is None:
            raise ValueError("CSV table has no header")
        return [dict(row) for row in reader]


def csv_columns(path: Path) -> tuple[str, ...]:
    """Return headers only; callers do not need row values for discovery."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t" if path.suffix.casefold() == ".tsv" else ",")
        try:
            return tuple(next(reader))
        except StopIteration as error:
            raise ValueError("CSV table has no header") from error


def parse_iso_date(value: str) -> date:
    """Accept only ISO-8601 calendar dates, never locale-dependent formats."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("date must be ISO-8601 YYYY-MM-DD") from error


def canonical_json_bytes(record: Any) -> bytes:
    """Placeholder retained for callers that need a stable JSON representation."""
    import json

    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )
