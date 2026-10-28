# Implementation Plan: Part 1 Opt-In

## Overview

Build the `src/part1_optin` pipeline incrementally and test-first, mirroring `src/part2_network`. Start with package scaffolding and the `Config` dataclass, then the halt-gate `Lead_Loader`, then the `Feature_Assembler` one feature block at a time (customer DNA, product counts, ADB, contacts, NDB, part2 join, promo attributes) behind a fitted `FeatureSchema`, then the `Model_Trainer` / `Calibrated_Model` (out-of-fold `CalibratedClassifierCV(method="isotonic", cv=3)` plus a separate full-data booster), the LOPO `Validator`, the SHAP `Explainer`, the `Scorer` (batch + `score_promo`), and finally the `main` CLI wiring and an end-to-end run against the real data. Each component is paired with its Hypothesis property tests (Properties 1-20 from the design) and targeted example/edge tests so correctness is validated as the package grows.

All Python/pytest commands run with `.venv\Scripts\python.exe` and `PYTHONPATH=src` on Windows. The `.venv` already has `pandas`, `numpy`, `scikit-learn`, `xgboost`, `shap`, `pytest`, and `hypothesis`; `requirements.txt` already lists them, so scaffolding only confirms imports rather than re-adding deps. No module, test, fixture, or path ever references a `*_answer_key*` file (Requirement 2.14).

## Tasks

- [x] 1. Set up package scaffolding and configuration
  - [x] 1.1 Create the `part1_optin` package skeleton and confirm imports
    - Create `src/part1_optin/__init__.py` and empty module files `config.py`, `leads.py`, `features.py`, `model.py`, `validation.py`, `explain.py`, `scoring.py`, `main.py`
    - Create dedicated part1 test files anchor under `tests/` (reuse the existing `tests/__init__.py`); keep part1 test files named `tests/test_part1_*.py` to avoid colliding with part2 tests
    - Confirm the package imports with `.venv\Scripts\python.exe -c "import part1_optin"` using `PYTHONPATH=src`; confirm `pandas`, `numpy`, `sklearn`, `xgboost`, `shap`, `hypothesis` import (add any missing dep to `requirements.txt` only if an import fails)
    - _Requirements: 7.6_

  - [x] 1.2 Implement `config.py` with the Config dataclass and domain constants
    - Define frozen `Config` dataclass with the eight input paths (`promo_leads_path`, `customer_dna_path`, `product_ownership_path`, `adb_monthly_path`, `contact_history_path`, `ndb_path`, `features_part2_path=Path("outputs/features_part2.csv")`, `promo_history_path`) and two output paths (`model_output_path=Path("outputs/model_part1.json")`, `scores_output_path=Path("outputs/scores.csv")`)
    - Define module constants: `TREATED_CONTROL_GROUP=0`, `PROMO_IDS=["P001","P002","P003"]`, `RANDOM_SEED=42`, `N_CALIBRATION_BINS=10`, `TOP_QUINTILE=0.20`, `DNA_CATEGORICAL_COLUMNS`, `DNA_NUMERIC_COLUMNS`, `PROMO_MECHANIC_COLUMN="mechanic"`, `KNOWN_MECHANICS=["TOP_UP","NEW_ACCOUNT","ADB_INCREASE"]`, `ANSWER_KEY_MARKER="_answer_key"`
    - _Requirements: 1.1, 6.1, 6.3, 7.8_

- [x] 2. Implement the Lead_Loader halt gate
  - [x] 2.1 Implement `Lead_Loader.load` with ordered selection, labeling, and halt gates
    - Existence check raising `FileNotFoundError` naming `promo_leads_path` before any downstream work; read via `pd.read_csv` coercing `control_group`/`joined` with `pd.to_numeric(errors="coerce")`
    - Keep `control_group == TREATED_CONTROL_GROUP` and `promo_id in PROMO_IDS`; set `Join_Label = joined`; drop rows whose `joined` is NaN or not in `{0,1}`; `drop_duplicates(subset=["promo_id","client_id"], keep="first")`
    - Raise `ValueError` indicating no treated leads when the result is empty, halting before any output
    - Note: run under `.venv\Scripts\python.exe` with `PYTHONPATH=src`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 2.2 Write property test for treated-lead selection
    - **Property 1: Treated-lead selection keeps exactly the valid treated P001/P002/P003 rows**
    - **Validates: Requirements 1.2, 1.3, 1.4, 1.5, 1.6**

  - [x] 2.3 Write example/edge unit tests for the Lead_Loader
    - Reads the configured default path and labels a small valid frame (1.1, 1.5); missing file raises `FileNotFoundError` naming the path (1.7)
    - Zero treated leads after filtering raises the no-treated-leads error with no output (1.8); a row with missing/non-0/1 `joined` is excluded (1.6)
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 1.8_

- [x] 3. Build shared Feature_Assembler scaffolding, answer-key guard, and test strategy
  - [x] 3.1 Implement the `FeatureSchema` dataclass and assembler skeleton with answer-key guard
    - Implement `FeatureSchema` (`columns`, `categorical_maps`, `product_type_columns`, `part2_columns`, `to_dict`, `from_dict`); add `Feature_Assembler.__init__` and the `fit_transform`/`transform` signatures
    - Add a guard helper asserting each path about to be opened does not contain `ANSWER_KEY_MARKER`, turning Requirement 2.14 into a runtime invariant
    - _Requirements: 2.1, 2.14, 7.2_

  - [x] 3.2 Build the part1 Hypothesis strategies module
    - Add a part1-specific strategy module/additions (e.g. `tests/strategies_part1.py`, kept separate from part2's `tests/strategies.py`) generating valid leads and source frames: small client-id pools, `control_group`/`joined` with injected bad values, `promo_id` from the three promos plus out-of-set ids, DNA categoricals from known domains, ADB monthly series of varied length, contact histories, product-ownership rows with varied `status`, part2 feature rows, and promo dicts with known and unseen mechanics
    - _Requirements: 2.1, 2.3, 2.5, 2.8, 2.13_

  - [x] 3.3 Write the answer-key-prohibition guard tests
    - Record paths passed to `pandas.read_csv` / `open` during a representative assembly and assert none contains `_answer_key`; repo-grep test asserts the `part1_optin` package and part1 test suite contain no `_answer_key` reference
    - _Requirements: 2.14_

- [x] 4. Implement Customer_DNA, product-count, and ADB feature blocks
  - [x] 4.1 Implement the Customer_DNA block with deterministic encoding and missing flag
    - Ordinal-encode `DNA_CATEGORICAL_COLUMNS` via a deterministic `value -> code` map from sorted distinct fit-time values (code `0` reserved for missing/unseen); pass through `DNA_NUMERIC_COLUMNS`
    - Absent `client_id` -> all DNA predictors `0` and `Customer_DNA_Missing_Flag = 1`, else `0`
    - _Requirements: 2.1, 2.2_

  - [x] 4.2 Implement the Active_Product_Count block
    - One `active_count_<product_type>` column per distinct `product_type` discovered at fit time, each the count of that client's `status == "Active"` rows; absent client/product pairs `0`
    - _Requirements: 2.3, 2.4_

  - [x] 4.3 Implement the ADB block (Latest_ADB, ADB_Trend, missing flag)
    - `latest_adb` = `adb_php` at the client's max `month`; `adb_trend` = least-squares slope of `adb_php` vs ascending month index over the last up-to-3 months (single month -> slope `0`); absent client -> both `0` and `ADB_Missing_Flag = 1`, else `0`
    - _Requirements: 2.5, 2.6, 2.7_

  - [x] 4.4 Write property test for feature determinism and stable encoding
    - **Property 2: Feature assembly is deterministic with stable categorical encoding**
    - **Validates: Requirements 2.1**

  - [x] 4.5 Write property test for active product counts
    - **Property 4: Active product counts equal the Active-status row counts per product_type**
    - **Validates: Requirements 2.3, 2.4**

  - [x] 4.6 Write property test for Latest_ADB and ADB_Trend
    - **Property 5: Latest ADB and ADB trend match an independent recompute**
    - **Validates: Requirements 2.5, 2.6**

  - [x] 4.7 Write edge unit test for single-month ADB and inactive-only product
    - Single-month ADB client yields `adb_trend == 0` (2.6); inactive-only client yields `active_count == 0` (2.4)
    - _Requirements: 2.4, 2.6_

- [x] 5. Implement contact, NDB, part2-join, and promo-attribute feature blocks
  - [x] 5.1 Implement the Contact_History and NDB blocks
    - `avg_contacts_per_month` = total contact rows / distinct `YYYY-MM` months with a contact (guarded division, `0` when no contacts); `ndb_flag` = 1 when `client_id` appears in NDB_File else `0`
    - _Requirements: 2.8, 2.9, 2.10_

  - [x] 5.2 Implement the Part2-join block with missing flag
    - Join all Part2_Features_File columns on `client_id`; absent client -> those columns `0` and `Part2_Features_Missing_Flag = 1`, else `0`
    - _Requirements: 2.11, 2.12_

  - [x] 5.3 Implement the Promo_Attributes block and finalize schema column order
    - Join `mechanic` (ordinal-encoded via its own deterministic map) and `threshold_php` (numeric pass-through) on `promo_id`
    - Assemble the fixed final column order into `schema.columns`: DNA numeric -> DNA categorical codes -> `Customer_DNA_Missing_Flag` -> sorted product-type active counts -> `latest_adb`, `adb_trend`, `ADB_Missing_Flag` -> `avg_contacts_per_month` -> `ndb_flag` -> part2 columns -> `Part2_Features_Missing_Flag` -> `mechanic` code -> `threshold_php`; `transform` reindexes onto `schema.columns`, reusing frozen maps and zero-filling absent columns
    - _Requirements: 2.1, 2.11, 2.13, 7.2_

  - [x] 5.4 Write property test for missing-source flags and zero-fill
    - **Property 3: Missing-source flags and zero-fill track client presence**
    - **Validates: Requirements 2.2, 2.7, 2.12**

  - [x] 5.5 Write property test for average contacts per month
    - **Property 6: Average contacts per month equals contacts over distinct months**
    - **Validates: Requirements 2.8, 2.9**

  - [x] 5.6 Write property test for NDB flag membership
    - **Property 7: NDB flag equals NDB membership**
    - **Validates: Requirements 2.10**

  - [x] 5.7 Write property test for promo attributes
    - **Property 8: Promo attributes match the joined promo's mechanic and threshold**
    - **Validates: Requirements 2.11, 2.13**

  - [x] 5.8 Write property test for schema stability at score time
    - **Property 9: The fitted schema reapplies identically at score time**
    - **Validates: Requirements 2.1, 7.2**

  - [x] 5.9 Write edge unit test for no-contact client
    - No-contact client yields `avg_contacts_per_month == 0`
    - _Requirements: 2.9_

- [x] 6. Checkpoint - Ensure all lead and feature tests pass
  - Ensure all tests pass, ask the user if questions arise. Run with `.venv\Scripts\python.exe -m pytest` and `PYTHONPATH=src`.

- [x] 7. Implement Model_Trainer and Calibrated_Model
  - [x] 7.1 Implement `Model_Trainer.fit` with out-of-fold calibration and full-data booster
    - Build `CalibratedClassifierCV(estimator=XGBClassifier(random_state=RANDOM_SEED,...), method="isotonic", cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED))` and fit on the given leads; separately fit one plain `XGBClassifier(random_state=RANDOM_SEED,...)` on all given rows and extract its `Booster`
    - Single-class guard: raise `ValueError` ("requires both opt-in and non-opt-in") before fitting when the labels for a fit have one unique class, halting without a `Calibrated_Model`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.6_

  - [x] 7.2 Implement the `Calibrated_Model` wrapper (`predict_proba`, `save`)
    - Bundle `calibrated`, `booster`, and `schema`; `predict_proba` delegates to the calibrated CV model's positive-class column clipped to `[0,1]`
    - `save` creates `outputs/` if absent, writes the full-data booster via `booster.save_model(model_path)` so `outputs/model_part1.json` is a valid JSON booster, and writes the calibration representation + `schema.to_dict()` to `outputs/model_part1.sidecar.json`
    - _Requirements: 3.5, 6.1, 6.7_

  - [x] 7.3 Write property test for calibrated-scoring determinism
    - **Property 10: Calibrated scoring is deterministic under a fixed seed**
    - **Validates: Requirements 3.2**

  - [x] 7.4 Write property test for calibrated-probability bounds
    - **Property 12: Calibrated probabilities are bounded in [0, 1]**
    - **Validates: Requirements 3.5, 7.3**

  - [x] 7.5 Write example/edge unit tests for the trainer and artifact
    - Fits a booster on a small two-class set and predicts probabilities (3.1); single-class fitting data raises the both-classes error and writes no artifact (3.6)
    - `outputs/model_part1.json` reloads as an XGBoost booster and predicts; sidecar carries calibration representation + schema (6.1); missing `outputs/` created on save (6.7)
    - _Requirements: 3.1, 3.6, 6.1, 6.7_

- [x] 8. Implement the LOPO (cold-start) and headline stratified Validator
  - [x] 8.1 Implement `Validator.run` LOPO folds with per-promo metrics
    - For each held-out promo, fit a fresh `Model_Trainer` on only the other two promos' leads; predict the held-out leads
    - Per fold compute ROC_AUC (only when both a joiner and non-joiner exist, else `None`); Capture_Rate_Top_Quintile when >=1 joiner (cutoff `ceil(0.20*N)`, leads with prob >= prob at cutoff counted, rate = joiners-in-top / total joiners); 10-equal-width-bin Calibration_Table over `[0,1]` reporting mean predicted prob, observed rate, count per non-empty bin
    - Zero-joiner held-out promo: omit/mark ROC_AUC and Capture undefined without halting other folds
    - _Requirements: 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 8.2 Implement `Validator.print_report`
    - Present ROC_AUC, Capture_Rate_Top_Quintile, and Calibration_Table separately per held-out promo, marking AUC/capture undefined for zero-joiner folds
    - _Requirements: 4.5, 4.6_

  - [x] 8.3 Write property test for LOPO leakage
    - **Property 11: Leave-one-promo-out fitting never touches the held-out promo**
    - **Validates: Requirements 3.3, 3.4, 4.1**

  - [x] 8.4 Write property test for ROC_AUC bounds
    - **Property 13: ROC_AUC is bounded when defined**
    - **Validates: Requirements 4.2**

  - [x] 8.5 Write property test for capture-rate definition and bounds
    - **Property 14: Capture rate matches the cutoff/tie definition and is bounded**
    - **Validates: Requirements 4.3**

  - [x] 8.6 Write property test for calibration-table well-formedness
    - **Property 15: Calibration table bins are well-formed**
    - **Validates: Requirements 4.4**

  - [x] 8.7 Write example/edge unit tests for the Validator
    - The result has a per-promo entry for each of P001/P002/P003 with the three metric fields (4.6); a zero-joiner held-out promo omits/marks ROC_AUC and Capture undefined while the other folds still report (4.5)
    - _Requirements: 4.5, 4.6_

  - [x] 8.12 Write example/edge unit tests for the stratified headline report
    - The `ValidationResult.stratified` result carries overall and per-promo AUC/capture fields (8.4, 8.5); `print_report` labels the stratified block as headline and the LOPO block as "cold-start: unseen promo type" (8.6)
    - _Requirements: 8.4, 8.5, 8.6_

  - [x] 8.8 Implement `Validator.run_stratified` headline StratifiedGroupKFold validation
    - Add `StratifiedValidationResult` (overall_auc, overall_capture_rate_top_quintile, per_promo_auc, per_promo_capture, n, joiners) and give `ValidationResult` a `stratified` field; `run` returns both `folds` (LOPO) and `stratified`
    - `run_stratified(X, y, promo_ids, client_ids, schema)` uses `sklearn.model_selection.StratifiedGroupKFold(n_splits=5)` with `groups=client_ids`, `y=Join_Label`; per fold fit a fresh `Model_Trainer` on that fold''s training leads only and predict the held-out leads, assembling one out-of-fold probability per lead (every lead held out exactly once; no client straddles a fold split)
    - Compute Overall_Stratified_AUC and overall capture over all leads, and Per_Promo_Stratified_AUC + per-promo capture by slicing the OOF vector per `promo_id`, reusing the existing roc_auc guard (both classes) and the `ceil(TOP_QUINTILE*N)` cutoff/tie helper; undefined slices -> `None` without halting
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.7_

  - [x] 8.9 Update `Validator.print_report` to present headline stratified first and relabel LOPO
    - Print the Stratified group k-fold block first (overall + per-promo AUC/capture), then the LOPO block under the heading "Cold-start: unseen promo type"; mark undefined stratified/LOPO metrics as undefined without halting
    - Thread `client_ids` (from `leads["client_id"]`) through `main` so `run`/`run_stratified` receive it
    - _Requirements: 4.6, 8.6_

  - [x] 8.10 Write property test for stratified group k-fold coverage and grouping
    - **Property 21: Stratified group k-fold keeps every client in one fold and covers every lead once**
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [x] 8.11 Write property test for stratified AUC and capture bounds
    - **Property 22: Stratified AUC and capture are bounded when defined**
    - **Validates: Requirements 8.4, 8.5, 8.7**

- [x] 9. Implement the SHAP Explainer
  - [x] 9.1 Implement `Explainer.shap_values` and `top_drivers`
    - `shap_values` builds a `shap.TreeExplainer` on the Calibrated_Model's single full-data booster, one contribution per predictor per row
    - `top_drivers` selects per row the `k=3` predictors with the largest `|SHAP|` ordered largest-to-smallest; ties broken by ascending predictor name; positions beyond the count of non-zero-contribution predictors filled with `""`
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 9.2 Write property test for SHAP matrix shape
    - **Property 16: SHAP matrix has one contribution per predictor per scored row**
    - **Validates: Requirements 5.1**

  - [x] 9.3 Write property test for top-3 driver selection, tie-break, and padding
    - **Property 17: Top-3 SHAP drivers are the largest-by-absolute, name-tie-broken, empty-padded**
    - **Validates: Requirements 5.2, 5.3, 5.4, 7.5**

  - [x] 9.4 Write edge unit test for <3 non-zero SHAP contributions
    - Fewer than three non-zero SHAP contributions pads trailing drivers with `""`
    - _Requirements: 5.4_

- [x] 10. Implement the Scorer (batch and score_promo)
  - [x] 10.1 Implement `Scorer.score_leads` and `write_scores`
    - `score_leads` calibrated-scores every treated lead, attaches top-3 SHAP drivers, returns a frame with `promo_id`, `client_id`, `p_join`, `top_driver_1..3`
    - `write_scores` creates `outputs/` if absent, rounds `p_join` to 6 dp in `[0,1]`, sorts by ascending `promo_id` then `client_id`, writes exactly one row per scored lead with the fixed six-column header and no index column
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 10.2 Implement `score_promo(promo_dict, clients_df, model, config)`
    - Build eligible-client leads from `clients_df` using the promo's `mechanic`/`threshold_php`; call `Feature_Assembler.transform` with the model's frozen `schema` so columns/order/encoding match the trained matrix; apply the existing `Calibrated_Model` without retraining; return one calibrated prob in `[0,1]` per client plus top-3 SHAP drivers with empty padding
    - If `mechanic` not in `KNOWN_MECHANICS`, still score every client but emit a `warnings.warn` about reduced reliability for unseen mechanics
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 10.3 Write property test for written p_join bounds and rounding
    - **Property 18: Written p_join values are bounded and rounded**
    - **Validates: Requirements 6.4**

  - [x] 10.4 Write property test for score ordering
    - **Property 19: Scores are ordered by promo_id then client_id**
    - **Validates: Requirements 6.5**

  - [x] 10.5 Write property test for one row per treated lead
    - **Property 20: Exactly one scores row per treated lead**
    - **Validates: Requirements 6.6**

  - [x] 10.6 Write example/edge unit tests for scoring and score_promo
    - `scores.csv` header is exactly the six columns in order with no index column (6.3); `score_promo` accepts a `promo_dict` with `promo_id`/`mechanic`/`threshold_php` and a `clients_df` and returns per-client results matching the trained schema (7.1, 7.2), applies the model without retraining (7.3), and includes top-3 drivers (7.5)
    - `score_promo` with an unseen mechanic emits a warning and still returns valid `[0,1]` probabilities for every client (7.4)
    - _Requirements: 6.3, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 11. Wire the pipeline together in main
  - [x] 11.1 Implement `main.main(argv) -> int` with CLI overrides and orchestration
    - Parse `--promo-leads`, `--customer-dna`, `--product-ownership`, `--adb`, `--contact-history`, `--ndb`, `--features-part2`, `--promo-history`, `--model-out`, `--scores-out` overrides into a `Config` before load/write
    - Orchestrate Lead_Loader.load -> Feature_Assembler.fit_transform -> Validator.run + print_report -> Model_Trainer.fit (final on all treated leads) -> Scorer.score_leads + Explainer -> `Calibrated_Model.save` + `write_scores`; return `0` on full success; catch any step exception, report the failing step to stderr, write no outputs, and return a non-zero exit; end with `raise SystemExit(main())`
    - _Requirements: 6.2, 7.6, 7.7, 7.8_

  - [x] 11.2 Write example/edge unit tests for the CLI
    - CLI path overrides are applied to `Config` before load/write (7.8); a successful run returns exit code 0 (7.6)
    - A mid-pipeline failure (e.g. pre-final-fit) yields a non-zero exit, a stderr message naming the failing step, and no `model_part1.json` or `scores.csv` written (6.2, 7.7)
    - _Requirements: 6.2, 7.6, 7.7, 7.8_

- [x] 12. Integration/smoke test against the real data
  - [x] 12.1 Run `python -m part1_optin.main` end-to-end and assert outputs
    - Run end-to-end with `.venv\Scripts\python.exe -m part1_optin.main` and `PYTHONPATH=src` against the real `data/` CSVs and `outputs/features_part2.csv`; assert the headline Stratified group k-fold block and the "Cold-start: unseen promo type" LOPO block both print (the stratified Overall AUC should be materially above 0.5), `outputs/model_part1.json` is written and reloads as a valid XGBoost booster, the sidecar is written, `outputs/scores.csv` has one row per treated lead with the six fixed columns sorted by `promo_id` then `client_id`, and the exit code is 0
    - Assert no path containing `_answer_key` was opened during the run (record paths passed to `pandas.read_csv` / `open`)
    - _Requirements: 2.14, 6.1, 6.3, 7.6_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure the entire part1 suite passes, ask the user if questions arise. Run with `.venv\Scripts\python.exe -m pytest` and `PYTHONPATH=src`.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are the unit, edge, property, and integration tests.
- Each task references the specific requirement sub-clauses and/or design properties it implements for traceability.
- Property tests use Hypothesis with `@settings(max_examples=100)` (or higher) and are tagged `# Feature: part1-optin, Property {number}: {property_text}`; reduction properties (4, 5, 6, 8, 14) assert against an independent reference recompute.
- Property/edge tests that actually fit the calibrated model generate small data with enough per-class examples for `cv=3`, or reduce the fold count in tiny fixtures while leaving the production default at `cv=3`; determinism tests hold the seeded `StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_SEED)` fixed.
- All commands use `.venv\Scripts\python.exe` with `PYTHONPATH=src` on Windows; no module, test, or path references a `*_answer_key*` file.
- Checkpoints ensure incremental validation before moving to the next component.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "3.1", "3.2"] },
    { "id": 3, "tasks": ["2.2", "2.3", "3.3", "4.1", "4.2", "4.3", "5.1", "5.2"] },
    { "id": 4, "tasks": ["4.4", "4.5", "4.6", "4.7", "5.3", "5.5", "5.6", "5.9"] },
    { "id": 5, "tasks": ["5.4", "5.7", "5.8", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "7.4", "8.1"] },
    { "id": 7, "tasks": ["7.5", "8.2", "8.3", "8.4", "8.5", "8.6", "9.1"] },
    { "id": 8, "tasks": ["8.7", "9.2", "9.3", "9.4", "10.1", "10.2"] },
    { "id": 9, "tasks": ["10.3", "10.4", "10.5", "10.6", "11.1"] },
    { "id": 10, "tasks": ["11.2"] },
    { "id": 11, "tasks": ["8.8"] },
    { "id": 12, "tasks": ["8.9", "8.10", "8.11", "8.12"] },
    { "id": 13, "tasks": ["12.1"] }
  ]
}
```
