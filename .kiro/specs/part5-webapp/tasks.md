# Implementation Plan: Part 5 Webapp

## Overview

Build the Streamlit app and its pipeline runner in Python, reusing the Part 1-4 packages. Start with a behavior-preserving refactor of `part3_segments` that exposes a reusable `assign_segments` and is gated by a byte-identical `segment_summary.csv` regression check. Then build the pure logic in `src/webapp_core/` (model reload, eligibility filter, promo-id, run-promo orchestration, predicted-vs-actual), each paired with its tests, followed by the `src/run_pipeline.py` orchestrator, the Theme, and finally `app/main.py` wiring the four surfaces (NEW PROMO, RESULTS, WHAT-IF/ASK ASSISTANT, PAST PROMOS). Exactly five Hypothesis property tests (Properties 1-5) cover the pure logic; the UI and I/O are covered by example/edge tests plus a final app smoke. Tests live under `tests/` as `test_part5_*.py` and run with `PYTHONPATH=src` using the project virtualenv; any temporary output goes under `scratch/`.

## Tasks

- [x] 1. Refactor part3_segments and expose assign_segments
  - [x] 1.1 Snapshot the current segment_summary.csv as a regression baseline
    - Before any code change, run `.\.venv\Scripts\python.exe -m part3_segments.main` (with `PYTHONPATH=src`) to regenerate `outputs/segment_summary.csv` and `outputs/segments.csv`, then copy `outputs/segment_summary.csv` to `scratch/segment_summary.baseline.csv` as the byte-for-byte baseline the refactor must preserve
    - _Requirements: 3.3_

  - [x] 1.2 Extract the shared quadrant helper and add assign_segments
    - In `src/part3_segments/segments.py`, refactor the 2x2 label assignment inside `assign` into a private helper (e.g. `_assign_quadrant_labels(leads)`) that both `assign` and the new wrapper call, leaving `assign`'s public behavior byte-identical
    - Add `assign_segments(scored, promo_dict, frames)` that builds the `frames["scores"]`-shaped input from `scored`, synthesizes a one-row `promo_history` carrying `promo_dict["threshold_php"]`, invokes the shared capacity + quadrant logic, and returns a Segments_File-shaped frame (`promo_id`, `client_id`, `p_join`, `capacity_php`, `segment`, `top_driver_1..3`)
    - _Requirements: 3.3, 4.1_

  - [x] 1.3 Checkpoint - verify the refactor changed no part3 output
    - Run the existing part3 suite (`.\.venv\Scripts\python.exe -m pytest tests -k part3`) and confirm it passes; run `.\.venv\Scripts\python.exe -m part3_segments.main` again and confirm the regenerated `outputs/segment_summary.csv` is byte-identical to `scratch/segment_summary.baseline.csv`; stop and report if either check fails
    - _Requirements: 3.3_

- [x] 2. Build webapp_core pure logic (model IO, audience, promo id)
  - [x] 2.1 Create the webapp_core package skeleton
    - Create `src/webapp_core/__init__.py` and empty module files `model_io.py`, `audience.py`, `run_promo.py`, `past_promos.py`, `promo_id.py`; confirm `streamlit` and `hypothesis` are in `requirements.txt` (add any missing)
    - _Requirements: 1.3_

  - [x] 2.2 Implement model_io.load_model
    - In `src/webapp_core/model_io.py` implement `load_model(outputs_dir)` reconstructing `Calibrated_Model` from `model_part1.json` (booster via `xgboost.Booster().load_model`), the `.sidecar.json` (`FeatureSchema.from_dict`, plus the `calibrated_path`), and the `.calibrated.pkl` (`pickle.load`); raise `FileNotFoundError` naming the first missing artifact
    - _Requirements: 1.3, 1.4_

  - [x] 2.3 Implement audience.select_eligible_clients
    - In `src/webapp_core/audience.py` implement latest-month ADB per client (max `month` per `client_id`, missing -> 0) and `select_eligible_clients(customer_dna, adb_monthly, eligible_segments, min_adb)` returning the `client_id`/`latest_adb`/`segment` frame filtered to DNA segment in `eligible_segments` AND latest ADB >= `min_adb`, in stable `client_id` order
    - _Requirements: 3.2_

  - [x] 2.4 Implement promo_id.next_promo_id
    - In `src/webapp_core/promo_id.py` implement `next_promo_id(existing)` returning `NEW-001` when no `NEW-###` id exists else `NEW-<max+1>` zero-padded to three digits
    - _Requirements: 3.1_

  - [x] 2.5 Write property tests for eligibility, segment quadrant, and promo id
    - Add Hypothesis tests Property 1 (eligibility is exactly the ADB-and-segment predicate over `select_eligible_clients`), Property 2 (`assign_segments` is exactly the score-vs-capacity quadrant in the fixed label order), and Property 3 (`next_promo_id` is the successor of the max NEW-id and always matches `NEW-\d{3}`); put shared generators in `tests/strategies_part5.py`; tag each with its `# Feature: part5-webapp, Property N: ...` line
    - _Requirements: 3.1, 3.2, 3.3, 4.1_

  - [x] 2.6 Write example/edge unit tests for model_io
    - Add tests that `load_model` round-trips a model saved by `Calibrated_Model.save` into `scratch/` and that it raises `FileNotFoundError` naming the first missing artifact
    - _Requirements: 1.3, 1.4_

- [x] 3. Build the run_promo and past_promos orchestration logic
  - [x] 3.1 Implement run_promo.run_promo and the PromoSpec/RunResult models
    - In `src/webapp_core/run_promo.py` define `PromoSpec` (with `to_promo_dict`) and `RunResult`, and `run_promo(promo_spec, model, config, data)` wiring select -> `score_promo` -> `assign_segments` -> `build_cards`, deriving `sendable_by_segment`; an empty eligible audience returns a `RunResult` with empty frames and `cards=[]`
    - _Requirements: 3.3, 3.4, 3.5, 6.2_

  - [x] 3.2 Implement past_promos.predicted_vs_actual
    - In `src/webapp_core/past_promos.py` implement `predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell)` computing per cell `predicted = expected_joiners / sendable_count` (NA when `sendable_count == 0`) and `actual = mean(joined)` over that cell's sendable leads in `promo_leads` (NA when none); add a helper to read the sendable ids per cell from `outputs/leads/`
    - _Requirements: 5.2, 5.4_

  - [x] 3.3 Write property tests for predicted/actual rates and WHAT-IF monotonicity
    - Add Hypothesis tests Property 4 (`predicted_vs_actual` rates are in `[0,1]` or NA, NA exactly when a cell has no sendable leads) and Property 5 (capacity-high count, hence Ready Toppers + Untapped Wealth, is non-increasing as `threshold_php` rises for a fixed scored audience, exercised through `assign_segments`); tag each with its `# Feature: part5-webapp, Property N: ...` line
    - _Requirements: 5.2, 5.4, 6.2_

  - [x] 3.4 Write example unit tests for run_promo and the empty-audience path
    - Add tests that `run_promo` returns an empty `RunResult` (no cards) when every client is filtered out, and a smoke test that a tiny eligible audience yields one card per populated cell
    - _Requirements: 3.4, 3.5_

- [x] 4. Implement the pipeline runner
  - [x] 4.1 Implement src/run_pipeline.py
    - Implement `main(argv=None)` running `part2_network.main([])`, `part1_optin.main([])`, `part3_segments.main([])`, `part4_cards.main([])` in order, stopping and returning a stage's non-zero exit code before the next stage, returning 0 on success; end with the `__main__` guard
    - _Requirements: 1.1, 1.2_

  - [x] 4.2 Write example unit tests for the pipeline runner ordering
    - Add tests (stages monkeypatched) asserting the four stages run in order on success and that a non-zero stage halts the run and returns its code with no later stage invoked
    - _Requirements: 1.1, 1.2_

- [x] 5. Build the Theme and app shell helpers
  - [x] 5.1 Sample Theme colors and write .streamlit/config.toml, app/styles.css, and app/theme.py
    - Sample the exact reds from the BPI website reference screenshot (deep red, lighter red for the gradient) plus white and charcoal; record them in `.streamlit/config.toml` `[theme]` and as the `PALETTE` dict in `app/theme.py`; author the single stylesheet `app/styles.css` (Poppins import, white 1200px-centered page, hidden Streamlit chrome, utility bar, nav bar, breadcrumb, red-gradient hero KPI panel, red-gradient pill buttons, underline tabs, rounded cards, 2x2 tiles, stat chips, rounded inputs and red sliders); have `app/theme.py` load it once via `build_css()`/`inject_css()` and expose `utility_bar`, `nav_bar`, `breadcrumb`, `hero_text_html`/`hero_kpi_html`, `card`, `tile`, `chip` (plus a `header` alias); gold only as a small accent; no logo image, text brand only
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 5.2 Write example unit tests for the Theme
    - Add tests that `.streamlit/config.toml` parses and carries the sampled base colors, that `build_css()` loads the single `app/styles.css`, imports Poppins, hides the default Streamlit chrome, uses the red gradient, and contains every palette color, that `nav_bar()`/`header()` render the "Promo Audience Navigator" text brand with no image tag, and that the nav items are Title Case
    - _Requirements: 2.1, 2.2_

- [x] 6. Build app/main.py and wire the tabs
  - [x] 6.1 Implement the app shell, routing, and NEW PROMO tab
    - In `app/main.py` set wide layout, inject the Theme once, render the BPI-web chrome (utility bar, nav bar with the red text brand, breadcrumb, hero with the red-gradient KPI panel) and the Title Case tabs, and build the New Promo form (product_type, mechanic, threshold_php, reward, eligible segments, min_adb, channels) with an auto-generated `NEW-001` promo_id; on Run Analysis call `run_promo`, store the `RunResult` in session state, surface the empty-audience message and the unseen-mechanic warning, and show the missing-model message if `load_model` raises
    - _Requirements: 1.4, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 6.2 Implement the RESULTS tab and DOWNLOAD LEADS
    - Render the 2x2 Results_Grid (rows score high/low, columns capacity low/high) with each cell's Segment_Label, client count, and expected joiners; render the four decision cards (action, dominant channel, message angle, expected joiners with 90% range, expected value, top drivers, exclusions-by-reason); wire DOWNLOAD LEADS to offer a per-segment sendable-leads CSV; show the run-first prompt when no `RunResult` exists
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.3 Implement the WHAT-IF and ASK ASSISTANT surfaces
    - Add the WHAT-IF threshold slider initialized to the current `threshold_php` that on change re-runs `run_promo` with the new threshold (rescore, reassign, rebuild) and updates results, with a run-first prompt when no run exists; add the ASK ASSISTANT placeholder panel ("coming in the next spec") that makes no LLM call
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 6.4 Implement the PAST PROMOS tab
    - Render one card per P001-P003 from `outputs/cards.json` showing per-segment predicted vs actual join rate via `predicted_vs_actual`; show the run-pipeline message if `cards.json` is absent and NA where a cell has no sendable leads
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 7. Final checkpoint - full suite and app smoke
  - Run the full part5 test suite plus the existing part1-4 suites and confirm all pass; launch `streamlit run app/main.py` with `PYTHONPATH=src` long enough to confirm it starts without error and the header/tabs render; keep any temporary output under `scratch/`
  - _Requirements: 1.1, 2.1, 3.3, 4.1, 5.1, 6.2_

## Task Dependency Graph
```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "2.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 4, "tasks": ["2.5", "2.6", "3.1"] },
    { "id": 5, "tasks": ["3.2", "4.1", "5.1"] },
    { "id": 6, "tasks": ["3.3", "3.4", "4.2", "5.2"] },
    { "id": 7, "tasks": ["6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3", "6.4"] },
    { "id": 9, "tasks": ["7"] }
  ]
}
```

## Notes

- There are exactly five Hypothesis property tests (Properties 1-5), honoring the MAX 5 cap. The model-reload, pipeline-ordering, empty-audience, Theme-color, and UI rendering behaviors are covered as example/edge tests rather than properties.
- Property tests use Hypothesis (`@settings(max_examples=100)` or higher) and are tagged `# Feature: part5-webapp, Property {number}: {property_text}`; reduction/relationship properties assert against an independent reference computation. Shared generators live in `tests/strategies_part5.py` following the part1-4 convention.
- Task 1 is a behavior-preserving refactor of already-shipped `part3_segments` code; task 1.1 captures a byte-for-byte `segment_summary.csv` baseline and task 1.3 gates the refactor on the existing part3 tests passing AND the regenerated summary matching that baseline, so the change cannot silently alter part3 output.
- The app is a presentation/orchestration layer only: no model is retrained, and there is no LLM (ASK ASSISTANT is a static placeholder).
- All commands use `.\.venv\Scripts\python.exe` with `PYTHONPATH=src`; the app launches with `streamlit run app/main.py`. Any temporary/debug output goes to a gitignored `scratch/` folder, never the repo root.
- Each task references the specific requirement sub-clauses and/or design properties it implements for traceability.
