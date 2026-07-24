# ADR 0001: HCP unrelated-cohort and output boundaries

- Status: Accepted
- Date: 2026-07-24
- Experiment contract version: `1.1.0`

## Context

The authoritative project description and implementation plan were revised to
make HCP-Young Adult 2025 Open Access imaging and the official unrelated-subject
list the main HCP protocol. The previous experiment contract and Week 1 sample
object instead treated `Family_ID` as mandatory. That field is Restricted
Access data and is no longer required by the preregistered main protocol.

The previous contract also said that all outputs belonged under `artifacts/`,
although the implementation plan reserves `docs/` and `reports/` for curated,
non-sensitive evidence.

## Decision

- The HCP main protocol uses the official unrelated list as a candidate
  whitelist, freezes the final cohort after availability, target, and QC
  intersections, and splits at subject level with `group_id=subject_id`.
- Every `BrainMultiGraphSample` carries `cohort_source`,
  `unrelated_list_version`, and `kinship_control_method` in
  `cohort_metadata`.
- `Family_ID` grouping is allowed only in a clearly labeled extension
  experiment if Restricted Access is obtained later.
- Rerunnable runtime artifacts remain under ignored `artifacts/`; curated,
  non-sensitive documentation and summary reports may be version-controlled
  under `docs/` and `reports/`.

## Consequences

- The experiment contract advances from `1.0.0` to `1.1.0`, and new provenance
  records use the new version.
- Artifacts produced under `1.0.0` remain valid historical evidence and are not
  relabeled.
- Future HCP manifests must record the official-list source, version, hash, and
  cohort-intersection procedure in manifest-level provenance without
  committing restricted subject data.
- Non-HCP samples retain the common metadata shape with an explicit
  `not_applicable` sentinel for HCP-only fields.

## Alternatives considered

- Requiring `Family_ID` for the main experiment was rejected because it would
  make the registered protocol depend on Restricted Access.
- Randomly splitting the full Open Access cohort was rejected as a main
  protocol because it would not enforce the revised unrelated-subject
  boundary.
