"""Strict, deterministic PPMI imaging-sequence and scanner metadata parsing."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SequenceClassification:
    """One conservative sequence classification with an auditable reason."""

    modality: str | None
    reason: str


@dataclass(frozen=True)
class ScannerMetadata:
    """Scanner/protocol proxy values; these are explicitly not site identifiers."""

    vendor: str | None
    field_strength: float | None
    model: str | None
    normalized_protocol: str | None
    batch_id: str | None


_MODALITIES = ("t1", "fmri", "dwi")
_CONTAMINANTS = {
    "t1": ("dti", "dwi", "diffusion", "rest", "rs-fmri", "bold", "nm-mt"),
    "fmri": ("dti", "dwi", "diffusion", "nm-mt", "neuromelanin", "t1", "mprage", "spgr"),
    "dwi": ("t1", "mprage", "spgr", "t2", "rest", "rs-fmri", "bold", "nm-mt"),
}
_VENDORS = ("siemens", "philips", "ge")
_MODELS = ("prisma", "skyra", "trio", "vida", "discovery", "signa", "ingenia", "achieva")


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _aliases(aliases: Mapping[str, Sequence[str]], group: str) -> tuple[str, ...]:
    values = aliases.get(group)
    if not isinstance(values, Sequence) or isinstance(values, str):
        raise ValueError(f"PPMI sequence aliases lack '{group}'")
    result = tuple(
        _normalized(value) for value in values if isinstance(value, str) and value.strip()
    )
    if not result:
        raise ValueError(f"PPMI sequence aliases lack '{group}'")
    return result


def classify_sequence(
    description: str, aliases: Mapping[str, Sequence[str]]
) -> SequenceClassification:
    """Classify only unambiguous full acquisitions; short reverse scans never qualify."""
    text = _normalized(description)
    if not text:
        return SequenceClassification(None, "missing_description")
    modality_aliases = {
        modality: _aliases(aliases, alias_group)
        for modality, alias_group in (("t1", "smri"), ("fmri", "fmri"), ("dwi", "dwi"))
    }
    alias_terms = {token for terms in modality_aliases.values() for token in terms}
    excluded = tuple(token for token in _aliases(aliases, "exclude") if token not in alias_terms)
    short_reverse = aliases.get("reverse_phase_short_rules", ())
    if not isinstance(short_reverse, Sequence) or isinstance(short_reverse, str):
        short_reverse = ()
    short_reverse_match = any(
        isinstance(token, str) and re.search(rf"(?:^|\s){re.escape(token)}(?:$|\s)", text)
        for token in short_reverse
    )
    if any(token in text for token in excluded) or short_reverse_match:
        return SequenceClassification(None, "excluded")
    candidates = [
        modality
        for modality, alias_group in (("t1", "smri"), ("fmri", "fmri"), ("dwi", "dwi"))
        if any(token in text for token in modality_aliases[modality])
    ]
    if len(candidates) != 1:
        if candidates and any(
            token in text for candidate in candidates for token in _CONTAMINANTS[candidate]
        ):
            return SequenceClassification(None, "contaminated")
        return SequenceClassification(None, "ambiguous" if candidates else "unrecognized")
    modality = candidates[0]
    exclusion_group = {"t1": "smri_exclude", "fmri": "fmri_exclude", "dwi": "dwi_exclude"}
    modality_exclusions = aliases.get(exclusion_group[modality], ())
    if isinstance(modality_exclusions, Sequence) and not isinstance(modality_exclusions, str):
        if any(
            isinstance(token, str) and _normalized(token) in text for token in modality_exclusions
        ):
            return SequenceClassification(None, "contaminated")
    if any(token in text for token in _CONTAMINANTS[modality]):
        return SequenceClassification(None, "contaminated")
    return SequenceClassification(modality, "classified")


def scanner_metadata(protocol: str, *, manufacturer: str = "", model: str = "") -> ScannerMetadata:
    """Extract only scanner/protocol proxy fields, never a site mapping."""
    combined = _normalized(" ".join((manufacturer, model, protocol)))
    vendor = next((candidate for candidate in _VENDORS if candidate in combined), None)
    field_match = re.search(r"(?<![0-9])([1-9](?:\.\d+)?)\s*t\b", combined)
    field_strength = float(field_match.group(1)) if field_match else None
    supplied_model = _normalized(model)
    scanner_model = supplied_model or next(
        (candidate for candidate in _MODELS if candidate in combined), ""
    )
    normalized_protocol = re.sub(r"[^a-z0-9.]+", " ", _normalized(protocol)).strip() or None
    material = "|".join(
        (
            vendor or "",
            "" if field_strength is None else f"{field_strength:g}",
            scanner_model,
            normalized_protocol or "",
        )
    )
    batch_id = (
        f"scanner_batch_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:12]}"
        if any((vendor, field_strength, scanner_model, normalized_protocol))
        else None
    )
    return ScannerMetadata(
        vendor, field_strength, scanner_model or None, normalized_protocol, batch_id
    )
