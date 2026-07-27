# PPMI initial audit

- Validator and manifest audit: `PASS`.
- Distinct subjects: 6,101; subject-visits: 12,419; distinct visit codes: 22.
- Same-visit availability: T1 1,830; fMRI 862; DWI 1,777; trimodal intersection 366.
- Enrollment cohort distribution: Healthy Control 522; Parkinson's Disease 4,104; Prodromal 7,668; SWEDD 125.
- Scanner vendor availability: GE 488; Philips 351; Siemens 1,760; unknown 9,820. Field strength is unavailable in the final manifest export; 2,627 rows have a scanner batch.
- Current MRI records remain primary; archived MRI was used only as a left join. One archive-only record was not appended.
- Sequence audit excluded 3 contaminated descriptions.
- `site_id` is `unknown` for all rows; manufacturer is not treated as site.
- Clinical dates are month-only, so exact imaging-clinical day intervals are unavailable.
- Confirmed target: candidate A, defined as MDS-UPDRS Part III follow-up minus
  baseline; `prefer_off` is primary. Candidate B and
  `unique_only`/`prefer_on` remain secondary/sensitivity analyses.
- Target status: `READY_FOR_USER_SELECTED_TASK`; primary 24-month independent
  subject count: 151 (`SHORTER_WINDOW_RECOMMENDED`).
- Canonical rerun: byte-identical.
