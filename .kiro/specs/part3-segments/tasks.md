# Implementation Plan: Part 3 Segments

## Overview

Build the `src/part3_segments` pandas pipeline incrementally and test-first, in Python (the design uses concrete Python/pandas, so no language selection is needed). Start with project scaffolding and configuration, then the input-validating `Input_Loader`, then the `Segmenter` (capacity, per-promo median score, 2x2 segment assignment, and the segments-file writer), then the `Summary_Builder` (per-cell counts, expected joiners, treated-lead join rate, and the full promo x four-segment cross product), and finally wire everything through `main` with the summary print and run end-to-end against the real data. Each logic block is paired with its Hypothesis property test (Properties 1–6, six total) and light example/edge tests so correctness is validated as the module grows. Tests live under `tests/` as `test_part3_*.py` and run with `PYTHONPATH=src` using the project virtualenv.

## Tasks

- [ ] 1. Set up package scaffolding and configuration
  - [ ] 1.1 Create the package skeleton
    - Create `src/part3_segments/__init__.py` and empty module files `loader.py`, `segments.py`, `validation.py`, `main.py` to anchor imports
    - Confirm `pandas`, `pytest`, and `hypothesis` are present in `requirements.txt` (add any that are missing)
    - _Requirements: 1.1, 3.1, 4.6, 5.1_

  - [ ] 1.2 Implement `config.py` with the Config dataclass and domain constants
    - Define a frozen `Config` dataclass with the seven paths: `scores_path=outputs/scores.csv`, `features_path=outputs/features_part2.csv`, `adb_monthly_path=data/adb_monthly.csv`, `promo_history_path=data/promo_history.csv`, `promo_leads_path=data/promo_leads.csv`, `segments_out_path=outputs/segments.csv`, `summary_out_path=outputs/segment_summary.csv`
    - Define module constants: `SCORES_COLUMNS`, `FEATURES_REQUIRED`, `ADB_REQUIRED`, `PROMO_HISTORY_REQUIRED`, `PROMO_LEADS_REQUIRED`, `SEGMENTS` (the four labels in order), `TREATED_CONTROL_GROUP=0`
    - _Requirements: 1.1, 1.3, 3.1, 4.1, 4.6, 5.1_

- [ ] 2. Implement the input-validating Input_Loader
  - [ ] 2.1 Implement `loader.load(cfg)` with ordered validation and type coercion
    - For each of the five files: existence check raising `FileNotFoundError` naming the path; read with `dtype=str, keep_default_na=False`; required-column check raising `ValueError` naming the file and every missing column
    - Coerce `p_join`, `out_other_bank`, `adb_php`, `threshold_php` via `to_numeric`; keep `month` as a `YYYY-MM` string
    - Return a dict of frames keyed `scores`, `features`, `adb`, `promo_history`, `promo_leads`; never write any output
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.2 Write example/edge unit tests for the loader
    - Missing file raises `FileNotFoundError` naming the path for each of the five inputs (1.2)
    - Missing required column raises `ValueError` naming the file and the removed columns (1.3)
    - A small valid set coerces the numeric columns and keeps `month` as a `YYYY-MM` string (1.1, 1.4)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 3. Build the Segmenter: capacity, score, and segment
  - [ ] 3.1 Implement capacity computation in `segments.py`
    - Compute `latest_adb` per client as `adb_php` at the lexicographically greatest `month`; left-join onto leads by `client_id` and `fillna(0)`
    - Left-join features `out_other_bank` onto leads by `client_id` and `fillna(0)`; set `capacity_php = latest_adb + out_other_bank`
    - _Requirements: 1.5, 2.1_

  - [ ]* 3.2 Write property test for the capacity formula
    - **Property 1: Capacity equals latest-month ADB plus external outflow, with missing sources treated as zero**
    - **Validates: Requirements 1.5, 2.1**

  - [ ] 3.3 Implement capacity_high, per-promo median score, and segment assignment
    - Left-join promo-history `threshold_php` by `promo_id`; set `capacity_high = capacity_php >= threshold_php` so a NaN threshold yields `False` (missing promo -> capacity-low)
    - Compute `promo_median = leads.groupby("promo_id").p_join.transform("median")`; set `score_high = p_join >= promo_median`
    - Assign `segment` from `(score_high, capacity_high)` via `np.select` onto the four labels
    - _Requirements: 1.6, 2.2, 2.3, 2.4_

  - [ ]* 3.4 Write property test for the 2x2 segment quadrant
    - **Property 2: Segment matches the 2x2 quadrant of score-high by capacity-high**
    - **Validates: Requirements 1.6, 2.2, 2.4**

  - [ ]* 3.5 Write property test for the median tie-break score test
    - **Property 3: Score-high is the at-or-above-median test within each promo, with ties counting as high**
    - **Validates: Requirements 2.3**

- [ ] 4. Write the per-lead Segments_File
  - [ ] 4.1 Implement `segments.write(leads, path)`
    - `path.parent.mkdir(parents=True, exist_ok=True)` then `to_csv(index=False)` with the exact ordered columns `promo_id, client_id, p_join, capacity_php, segment, top_driver_1, top_driver_2, top_driver_3`, one row per lead
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 4.2 Write property test for one-row-per-lead output
    - **Property 6: The segments output has exactly one row per lead with preserved and bounded values**
    - **Validates: Requirements 3.2**

  - [ ]* 4.3 Write example/edge unit tests for the segments output
    - Header equals the exact ordered column list (3.1); writing to a path whose parent is absent creates `outputs/` (3.3)
    - _Requirements: 3.1, 3.3_

- [ ] 5. Checkpoint - Ensure Segmenter tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Build the Summary_Builder
  - [ ] 6.1 Implement per-cell aggregates and the promo x four-segment cross product
    - Group assigned leads by (`promo_id`, `segment`) for `n_clients` (count), `mean_p_join` (mean), `expected_joiners` (sum of `p_join`), and most common `top_driver_1` (mode, deterministic tie-break)
    - Reindex onto the full cross product of distinct scores `promo_id` x `SEGMENTS`; zero-fill counts/means/expected and blank-fill text for empty cells
    - _Requirements: 4.1, 4.2, 4.5_

  - [ ]* 6.2 Write property test for expected joiners per cell
    - **Property 4: Expected joiners per cell equals the sum of p_join of the cell's leads**
    - **Validates: Requirements 4.2**

  - [ ] 6.3 Implement the treated-lead actual join rate
    - Filter promo-leads to `control_group == 0`; inner-join to assigned leads on (`promo_id`, `client_id`) to attach each treated lead's segment; per cell compute `joined.mean()`
    - Leave `actual_join_rate` empty for cells with zero treated leads
    - _Requirements: 4.3, 4.4_

  - [ ]* 6.4 Write property test for summary completeness and empty-cell filling
    - **Property 5: The summary contains every promo crossed with all four segments, with empty cells zero- and blank-filled**
    - **Validates: Requirements 4.1, 4.4, 4.5**

  - [ ]* 6.5 Write example/edge unit tests for the join rate and summary write
    - Actual join rate uses treated (`control_group == 0`) leads only, is bounded in `[0, 1]`, and never counts control rows (4.3); a cell with zero treated leads shows an empty rate (4.4)
    - `validation.write` creates `outputs/` and writes a single header row (4.6)
    - _Requirements: 4.3, 4.4, 4.6_

- [ ] 7. Wire the pipeline together in main and print the summary
  - [ ] 7.1 Implement `main.main(argv)` with CLI wiring and summary print
    - Parse CLI path overrides into a `Config`; call `loader.load`, `segments.assign` + `segments.write`, `validation.build` + `validation.write` in order
    - Print one line per (promo, segment) summary cell showing `promo_id`, segment, `n_clients`, `mean_p_join`, `expected_joiners`, `actual_join_rate`, and most common `top_driver_1`, rendering empty rate/driver as 0 or blank
    - Propagate a loader error before any output is produced; expose `python -m part3_segments.main`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 7.2 Write example unit tests for the Reporter and error propagation
    - Capture stdout: one line per summary cell with the seven fields (5.2); empty rate/driver rendered as 0 or blank (5.3)
    - A loader error makes `main` write nothing and print no summary (5.4)
    - _Requirements: 5.2, 5.3, 5.4_

  - [ ]* 7.3 Write integration/smoke test against the real data
    - Run end-to-end against the real five inputs; assert `outputs/segments.csv` has one row per scored lead and `outputs/segment_summary.csv` has four rows per distinct promo, and the summary prints
    - _Requirements: 5.1_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are the unit, edge, property, and integration tests.
- There are exactly six Hypothesis property tests (Properties 1–6), honoring the MAX 6 cap. The loader-validation checks (1.2, 1.3) and the bounded treated-only join rate (4.3) are covered as light example/edge tests rather than properties.
- Property tests use Hypothesis (`@settings(max_examples=100)` or higher) and are tagged `# Feature: part3-segments, Property {number}: {property_text}`; reduction properties (1 and 4) assert against an independent reference computation.
- Shared Hypothesis generators go in a `tests/strategies*.py`-style module following the existing part1/part2 convention.
- Any temporary/debug output during implementation goes to a gitignored `scratch/` folder, never the repo root; `.gitignore` already ignores `outputs/`, `_*.txt`, and `*_out*.txt`.
- Each task references the specific requirement sub-clauses and/or design properties it implements for traceability.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "3.5", "4.1"] },
    { "id": 6, "tasks": ["4.2", "4.3", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3"] },
    { "id": 8, "tasks": ["6.4", "6.5", "7.1"] },
    { "id": 9, "tasks": ["7.2", "7.3"] }
  ]
}
```
