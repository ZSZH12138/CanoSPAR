# Week 2–4 manual verification checklist

Use an activated project environment and set `$MetadataRoot` to the approved private metadata directory. Commands deliberately avoid printing participant rows.

## 1. Real data is not tracked

- Command: `git ls-files -- data/metadata`
- File path: `data/metadata`
- Expected: no output.
- Failure means: private data has entered the Git index.

## 2. Original source hashes are unchanged

- Command: `python -c "import json; from pathlib import Path; p=json.loads(Path('reports/data_qc/week02_04/manifest_validation_summary.json').read_text()); print(p['source_integrity']['unchanged'])"`
- File path: `reports/data_qc/week02_04/manifest_validation_summary.json`
- Expected: `True`, with identical before/after composite SHA-256.
- Failure means: at least one CSV, PDF, or JSON source changed during execution.

## 3. Current/latest source selection

- Command: `python -m canospar.data.metadata_discovery --config configs/data/ppmi.yaml --metadata-root $MetadataRoot --output-dir artifacts/manifests/week02_04/manual/ppmi --dry-run`
- File path: `configs/data/ppmi.yaml`
- Expected: exit 0; the source-manifest/current-guidance contract resolves without ambiguity.
- Failure means: the current source is missing, ambiguous, or inconsistent with its recorded hash.

## 4. Old dictionary remains archive-only

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/ppmi_source_inventory.json')); print([x['status'] for x in p['sources'] if x['logical_name']=='archived_data_dictionary'])"`
- File path: `reports/data_qc/week02_04/ppmi_source_inventory.json`
- Expected: `['archive_only']`.
- Failure means: archived guidance may have been promoted into the active contract.

## 5. HCP unrelated constraint

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/hcp_initial_audit.json')); print(p['summary']['official_unrelated_count'], p['summary']['manifest_subject_count'])"`
- File path: `reports/data_qc/week02_04/hcp_initial_audit.json`
- Expected: `339 339`.
- Failure means: the manifest no longer equals the official-unrelated intersection.

## 6. HCP cohort remains provisional

- Command: `python -c "import json; print(json.load(open('reports/data_qc/week02_04/hcp_initial_audit.json'))['summary']['cohort_status'])"`
- File path: `reports/data_qc/week02_04/hcp_initial_audit.json`
- Expected: `provisional`.
- Failure means: the audit is overstating package availability.

## 7. Completion is not package inventory

- Command: `python -c "import json; print(json.load(open('reports/data_qc/week02_04/hcp_initial_audit.json'))['summary']['processed_package_inventory'])"`
- File path: `reports/data_qc/week02_04/hcp_initial_audit.json`
- Expected: `not_available`.
- Failure means: acquisition completion may be misrepresented as processed-package inventory.

## 8. HCP target state

- Command: `python -c "import csv; r=list(csv.DictReader(open('reports/data_qc/week02_04/hcp_target_candidate_audit.csv'))); print([(x['target'],x['role'],x['status']) for x in r])"`
- File path: `reports/data_qc/week02_04/hcp_target_candidate_audit.csv`
- Expected: `CogFluidComp_Unadj` is `primary`; the other two rows are
  `secondary`; every status is `CONFIRMED`.
- Failure means: the tracked audit does not match the confirmed HCP task.

## 9. PPMI current and archive were not concatenated

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/ppmi_initial_audit.json'))['summary']['archive_join']; print(p['method'],p['archived_only_record_count'])"`
- File path: `reports/data_qc/week02_04/ppmi_initial_audit.json`
- Expected: `left_join_on_record_id 1`.
- Failure means: archived-only records may have been appended as current rows.

## 10. PPMI trimodal matching uses subject plus visit

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/ppmi_initial_audit.json'))['summary']; print(p['subject_visit_count'],p['trimodal_subject_visit_count'])"`
- File path: `reports/data_qc/week02_04/ppmi_initial_audit.json`
- Expected: `12419 366`.
- Failure means: the same-visit intersection changed or subject-only matching may have leaked in.

## 11. Sequence contamination is excluded

- Command: `python -c "import csv; print([r['count'] for r in csv.DictReader(open('reports/data_qc/week02_04/ppmi_sequence_classification_audit.csv')) if r['name']=='excluded_contamination'])"`
- File path: `reports/data_qc/week02_04/ppmi_sequence_classification_audit.csv`
- Expected: `['3']`.
- Failure means: contaminated sequence descriptions may be classified as valid modalities.

## 12. Site identifiers remain unknown

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/ppmi_initial_audit.json'))['summary']; print(p['site_id_unknown_count'],p['subject_visit_count'])"`
- File path: `reports/data_qc/week02_04/ppmi_initial_audit.json`
- Expected: `12419 12419`.
- Failure means: unavailable site metadata may have been fabricated.

## 13. Manufacturer is not used as site

- Command: `python -c "import json; print(json.load(open('reports/data_qc/week02_04/ppmi_initial_audit.json'))['summary']['site_metadata_status'])"`
- File path: `reports/data_qc/week02_04/ppmi_initial_audit.json`
- Expected: `unavailable_in_current_ppmi_export`.
- Failure means: scanner vendor may have been mislabeled as site.

## 14. Part III duplicate policies remain explicit

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/ppmi_task_gate.json')); b=p['branches']['candidate_A']['prefer_off']; print(p['primary_target'],p['primary_policy'],b['basis_independent_subject_count'],b['final_task_selected'],b['required_confirmations'],sorted(p['sensitivity_policies']))"`
- File path: `reports/data_qc/week02_04/ppmi_task_gate.json`
- Expected: `candidate_A prefer_off 151 True [] ['prefer_on', 'unique_only']`.
- Failure means: the confirmed primary branch or required sensitivity policies
  do not match the scientific configuration.

## 15. Boundary tests 119/120/179/180

- Command: `python -m pytest -q tests/unit/data/test_task_gate.py`
- File path: `tests/unit/data/test_task_gate.py`
- Expected: exit 0 with the four thresholds covered.
- Failure means: the decision-tree boundary behavior is not trustworthy.

## 16. Canonical rerun hashes match

- Command: `python -c "import json; print(json.load(open('reports/data_qc/week02_04/manifest_validation_summary.json'))['determinism'])"`
- File path: `reports/data_qc/week02_04/manifest_validation_summary.json`
- Expected: both values are `true`.
- Failure means: a builder is nondeterministic or its inputs changed.

## 17. Full lint, type, and test acceptance

- Command: `python scripts/verify_week2_4.py`
- File path: `reports/data_qc/week02_04/verification_results.json`
- Expected: exit 0 and `overall_status` equal to `PASS`.
- Failure means: at least one required engineering acceptance check failed.

## 18. Inspect acceptance WARN/FAIL

- Command: `python -c "import json; p=json.load(open('reports/data_qc/week02_04/verification_results.json')); print([(x['name'],x['status']) for x in p['checks'] if x['status']!='PASS'])"`
- File path: `reports/data_qc/week02_04/verification_results.json`
- Expected: an empty list.
- Failure means: a required check is failed, warned, or skipped and needs review before scientific use.
