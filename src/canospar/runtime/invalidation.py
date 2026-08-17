"""Fixed scientific invalidation DAG."""

from __future__ import annotations

MODULE_ORDER: tuple[str, ...] = (
    "M0",
    "P0",
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M7",
    "M8",
    "M9",
)


def compute_invalidated_modules(changed_module: str) -> tuple[str, ...]:
    if changed_module not in MODULE_ORDER:
        raise ValueError(f"unknown module: {changed_module}")
    start = MODULE_ORDER.index(changed_module)
    return MODULE_ORDER[start:]
