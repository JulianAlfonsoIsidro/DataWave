# Implementation Plan: Persona Segmentation

## Overview

This plan implements the persona-segmentation feature as a new pure pipeline package `src/part5_personas`, a `webapp_core`-style orchestration module `src/webapp_core/personas.py`, and a Streamlit `Persona_Page` in `app/`. It reuses existing `outputs/` artifacts and the Part 3/Part 4 in-memory APIs read-only, makes no edits to the existing `run_pipeline.py` stages, and adds only `kmodes` as a new dependency.

The build order follows the design's module breakdown: dependency → config → join → preprocess → cluster → profile → naming → grouping → export → CLI → webapp_core orchestration → Streamlit page, with tests placed close to the code they validate. All test tasks are required. The Streamlit page uses only Streamlit built-in charts (`st.bar_chart` / `st.line_chart`) for both the cluster comparison chart and the Elbow_Plot, so no new chart dependency is introduced.

## Tasks

- [x] 1. Add the `kmodes` dependency
  - Append `kmodes` to `requirements.txt` as the only new dependency (`hypothesis` and `pytest` are already listed — do not re-add them)
  - Introduce no dependency other than `kmodes` and the chart libraries already listed
  - _Requirements: 9.9_

- [x] 2. Create the `src/part5_personas` package and frozen Config
  - [x] 2.1 Create `src/part5_personas/__init__.py` and `src/part5_personas/config.py`
    - Define a frozen `@dataclass Config` with the input `Path` fields (`customer_dna_path`, `product_ownership_path`, `features_part2_path`, `segments_path`, `cards_path`, `leads_dir`, `promo_leads_path`) and the output field `labeled_leads_out_path`, using the design's canonical defaults
    - Add the D4 domain constants as Config fields: `min_match_rate=0.5`, `min_group_size=30`, `max_sample_size=2000`, `random_seed=42`, `default_k=3`, `k_min=2`, `k_max=6`
    - Add module-level constants `ANSWER_KEY_MARKER = "_answer_key"`, `ELBOW_K_RANGE = (2, 3, 4, 5, 6)`, `CAMPAIGN_PROMO_IDS = ("P001", "P002", "P003")`
    - Cite the governing requirements in the module docstring
    - _Requirements: 1.9, 2.8, 2.9, 3.12, 9.1_

- [x] 3. Build the Joined_Attribute_Set (`join.py`)
  - [x] 3.1 Implement `join.py` to assemble the clustering input
    - Pivot long-format `product_ownership.csv` into one row per `client_id` with one `owns_<product_type>` flag per distinct `product_type` (1 when the client has at least one row of that type, else 0), each flag categorical over `{0, 1}`
    - Left-join the pivoted flags and `outputs/features_part2.csv` onto `customer_dna.csv` on `client_id`, producing exactly one row per `client_id` in `customer_dna.csv`; set absent-ownership clients' flags to 0; source behavioral features only from `features_part2.csv`
    - Compute `Match_Rate` per source (customer_dna, pivoted product_ownership, features_part2) as the fraction of leads with a matching row
    - Add the answer-key guard: reject any input path containing `ANSWER_KEY_MARKER` and halt before output naming the file
    - Add the match-rate halt: if any source's rate is 0 or below `min_match_rate`, halt before output naming the source and its rate
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.10_
  - [x] 3.2 Write join unit tests in `tests/test_part5_personas_join_unit.py`
    - Verify pivot one-hot correctness, Match_Rate values, imputation of absent-product clients (flags all 0), and the answer-key rejection and low-match-rate halt messages
    - _Requirements: 1.2, 1.4, 1.6, 1.8, 1.10_

- [x] 4. Implement preprocessing (`preprocess.py`)
  - [x] 4.1 Implement type detection, scaling, imputation, and categorical indices
    - Classify each selected column as numeric when its schema dtype is integer/float, categorical otherwise; apply user `type_overrides` over auto-detection
    - Standardize each numeric feature to zero mean / unit variance across the clustered leads
    - Impute every missing numeric value with the column mean and every missing categorical value with the column mode so the clustered input has zero missing values
    - Reject the run naming the column (and produce no assignments) if, after imputation, a selected column has zero non-missing values
    - Compute and return the categorical column indices for k-prototypes
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  - [x] 4.2 Write the scaling property test in `tests/test_part5_personas_scaling_property.py`
    - **Property 5: Scaling yields zero mean and unit variance**
    - **Validates: Requirements 2.4**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 5: Scaling yields zero mean and unit variance`
    - _Requirements: 2.4_
  - [x] 4.3 Write the imputation property test in `tests/test_part5_personas_imputation_property.py`
    - **Property 6: Imputation leaves zero missing values**
    - **Validates: Requirements 2.5**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 6: Imputation leaves zero missing values`
    - _Requirements: 2.5_

- [ ] 5. Implement clustering (`cluster.py`)
  - [x] 5.1 Implement seeded k-prototypes fit, k validation, sampling cap, assignment, and elbow sweep
    - Cluster with `kmodes.kprototypes.KPrototypes` seeded with `random_seed=42`; default k to 3 when unspecified; accept integer k in `[2, 6]`; reject non-integer or out-of-range k with an error stating the valid range and produce no assignments
    - When a group exceeds `max_sample_size`, fit on a seeded `numpy.random.default_rng(random_seed)` subsample of the group sorted by `client_id`, then assign the full group to the nearest learned prototype using the k-prototypes mixed dissimilarity with `model.gamma_`
    - Compute the elbow cost sweep for each `k = 2..6` on the shared subsample, recording `cost_` per k
    - _Requirements: 2.1, 2.8, 2.9, 2.10, 2.11, 2.12_
  - [ ] 5.2 Write cluster unit tests in `tests/test_part5_personas_cluster_unit.py`
    - Verify invalid-k rejection message, default k=3, and that elbow costs cover k=2..6
    - _Requirements: 2.8, 2.10, 2.12_
  - [ ] 5.3 Write the cluster-count property test in `tests/test_part5_personas_cluster_count_property.py`
    - **Property 1: Cluster label count equals k (or the capped k)**
    - **Validates: Requirements 2.9, 3.11**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 1: Cluster label count equals k (or the capped k)`
    - _Requirements: 2.9, 3.11_
  - [ ] 5.4 Write the assignment/coverage property test in `tests/test_part5_personas_assignment_property.py`
    - **Property 2: Every clustered lead is assigned exactly one persona**
    - **Property 11: Sampling-then-assign covers all leads**
    - **Validates: Requirements 2.1, 5.4, 8.1**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 2: Every clustered lead is assigned exactly one persona` and `# Feature: persona-segmentation, Property 11: Sampling-then-assign covers all leads`
    - _Requirements: 2.1, 5.4, 8.1_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement persona profiling (`profile.py`)
  - [ ] 7.1 Implement `PersonaProfile` stats and distinguishing attributes
    - Compute per persona: `size` (non-negative integer), `pct_of_leads` (0.0–100.0 rounded to one decimal), numeric mean and median per numeric attribute, and top-3 categories per categorical attribute with a fallback to all categories when fewer than 3 are present
    - Compute the top-3 distinguishing attributes via standardized numeric z-score (`abs(mean_p - mu)/sigma`, 0 when sigma is 0) and categorical max absolute proportion-difference against pooled other-personas, never raw values, with ties broken by ascending attribute name
    - Omit zero-size personas from the set rather than profiling them
    - _Requirements: 4.1, 4.2, 4.3, 4.7_
  - [ ] 7.2 Write the distinguishing-metric determinism property test in `tests/test_part5_personas_determinism_property.py`
    - **Property 4: Determinism under fixed seed**
    - **Property 10: Distinguishing-metric determinism and standardization**
    - **Validates: Requirements 2.11, 4.3, 4.6**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 4: Determinism under fixed seed` and `# Feature: persona-segmentation, Property 10: Distinguishing-metric determinism and standardization`
    - _Requirements: 2.11, 4.3, 4.6_
  - [ ] 7.3 Write the profile-bounds property test in `tests/test_part5_personas_profile_bounds_property.py`
    - **Property 12: Percentage bounds and size consistency**
    - **Validates: Requirements 4.1, 4.7**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 12: Percentage bounds and size consistency`
    - _Requirements: 4.1, 4.7_

- [ ] 8. Implement persona naming (`naming.py`)
  - [ ] 8.1 Implement the `PersonaNamer` interface and `RuleBasedNamer`
    - Define the `PersonaNaming` TypedDict (`name`, `description`, `actions`) and the `PersonaNamer` Protocol with `name(profile, taken) -> PersonaNaming`
    - Implement `RuleBasedNamer` deriving name, one-line description, and 2–3 recommended actions purely from the `PersonaProfile` so identical profiles yield identical output
    - Guarantee unique names within a set using the `taken` set with a deterministic suffix when a base name is already taken; name personas in ascending cluster-label order
    - _Requirements: 4.4, 4.5, 4.6, 4.8, 4.9_
  - [ ] 8.2 Write naming unit tests in `tests/test_part5_personas_naming_unit.py`
    - Verify rule-based name/description/2–3 actions for representative profiles and the disambiguation suffix path
    - _Requirements: 4.4, 4.5, 4.8_
  - [ ] 8.3 Write the unique-names property test in `tests/test_part5_personas_naming_unique_property.py`
    - **Property 7: Persona names are unique within a set**
    - **Validates: Requirements 4.9**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 7: Persona names are unique within a set`
    - _Requirements: 4.9_

- [ ] 9. Implement levels and the two-step flow (`grouping.py`)
  - [ ] 9.1 Implement clustering levels, two-step grouping, and group-size handling
    - Support levels `all` (one set), `business-segment` (one set per distinct `Business_Segment_Field` value using `customer_dna.segment` or Part 3 `Segment_Label`; reject naming the field when it has no usable values), and `campaign` (cluster only the chosen pool, exclude out-of-pool leads, use no `Business_Segment_Field` as a clustering feature; report empty-audience without clustering on an empty pool)
    - Implement the two-step flow: partition by `Grouping_Attributes`, then cluster each group on `Clustering_Attributes` with k per group
    - Flag groups below `min_group_size` as "too small to cluster" (`too_small=True`, no personas); cap k to the group size when the group is at/above `min_group_size` but below the requested k
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 5.4, 5.5, 5.6_
  - [ ] 9.2 Write grouping edge tests in `tests/test_part5_personas_grouping_edge.py`
    - Verify the too-small group flag, k-cap-to-group-size, empty business-segment field rejection, and empty campaign pool handling
    - _Requirements: 3.7, 3.10, 3.11, 5.6_

- [ ] 10. Implement the leads export (`export.py`)
  - [ ] 10.1 Implement `Persona_Labeled_Leads` construction
    - Produce exactly one row per Part 4 leads-input lead with a `persona_label` column assigning each to one persona and a `group` column (business-segment value or campaign identifier per level)
    - Left-join on `client_id` the richer attributes from `customer_dna.csv`, the pivoted `product_ownership.csv`, and `features_part2.csv`, preserving every source column name, dropping no lead and introducing no duplicates, leaving unmatched source attributes empty
    - At `campaign` level, leave `persona_label` and `group` empty for leads outside the chosen pool
    - Make the export the last step, produced only after clustering and profiling both succeed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - [ ] 10.2 Write the export-rows property test in `tests/test_part5_personas_export_rows_property.py`
    - **Property 8: Export row count equals the input lead count**
    - **Property 9: Group column correctness**
    - **Validates: Requirements 8.1, 8.3, 8.6, 8.7**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 8: Export row count equals the input lead count` and `# Feature: persona-segmentation, Property 9: Group column correctness`
    - _Requirements: 8.1, 8.3, 8.6, 8.7_

- [ ] 11. Implement the CLI entry point (`main.py`)
  - [ ] 11.1 Implement `main(argv: list[str] | None = None) -> int`
    - Parse path-override flags (`--customer-dna`, `--product-ownership`, `--features-part2`, `--segments`, `--cards`, `--leads-dir`, `--promo-leads`, `--labeled-leads-out`) onto `Config`
    - Run the pipeline in order (join → preprocess → cluster → profile → name → group → export); halt before any write when a required `outputs/` artifact is missing, returning non-zero and naming the missing artifact
    - Perform every output write only after all clustering and profiling succeed (output-last); return 0 on success and a non-zero code naming the failing step otherwise; end with the `if __name__ == "__main__": raise SystemExit(main())` guard
    - _Requirements: 9.1, 9.3, 9.5, 9.6, 9.7, 9.8_
  - [ ] 11.2 Write main unit tests in `tests/test_part5_personas_main_unit.py`
    - Verify `main` exit codes, missing-artifact halt message, and output-last write safety (no file written on a mid-run failure)
    - _Requirements: 9.5, 9.6, 9.7, 9.8_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Implement the `Persona_Core` orchestration (`src/webapp_core/personas.py`)
  - [ ] 13.1 Implement `run_personas` and `persona_mix_by_cell` with no Streamlit imports
    - Implement `run_personas(spec, namer, cfg, *, live_leads=None) -> PersonaRunResult` building the joined set and running levels/grouping/clustering/profiling/naming deterministically; use the current New Promo session leads for the campaign live pool and `promo_leads.csv` / `outputs/leads/` for past promos
    - Implement `persona_mix_by_cell(labels, cards) -> dict[(promo_id, segment), PersonaMix]` computing per-cell shares normalized to sum to 100% for non-empty cells and aligning them onto the existing Part 4 cards by `(promo_id, segment)` without mutating any card; mark `available=False` when a cell has no assignment
    - Reuse Part 3 `assign_segments` and Part 4 `build_cards` read-only; add no modelling and no Streamlit imports
    - _Requirements: 5.1, 5.3, 6.8, 7.1, 7.3, 7.4, 7.5_
  - [ ] 13.2 Write the persona-mix sum property test in `tests/test_part5_personas_mix_sum_property.py`
    - **Property 3: Persona mix sums to 100% per non-empty cell**
    - **Validates: Requirements 7.1**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 3: Persona mix sums to 100% per non-empty cell`
    - _Requirements: 7.1_
  - [ ] 13.3 Write cards-mix unit tests in `tests/test_part5_personas_cards_mix_unit.py`
    - Verify the mix is joined by `(promo_id, segment)`, that every Part 4 card field is unchanged byte-for-byte, and the unavailable-mix fallback
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [ ] 14. Implement the Streamlit `Persona_Page` (`app/`)
  - [ ] 14.1 Build the page composition and session-state wiring
    - Render the Attribute_Picker over Joined_Attribute_Set columns, a k selector constrained to integers 2–6, a Clustering_Level selector (default `all`), the optional two-step grouping controls (separate Grouping_Attributes and Clustering_Attributes controls), the campaign pool selector (live session leads or past promo by `promo_id` in P001/P002/P003, disabling the live choice when no run exists), and a Run control
    - On an invalid configuration (fewer than one attribute, k outside 2–6, or no level) reject the run, retain current configuration and displayed results, and show an error naming the invalid input
    - Render one summary card per persona (name, description, integer size, one-decimal percentage, recommended actions), and a download control that stays disabled until a run completes in the session
    - Delegate all clustering and profile computation to `Persona_Core` / `Persona_Pipeline`; own the `st.cache_data` wrappers in this layer
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.6, 6.7, 6.9_
  - [ ] 14.2 Render the charts and the persona mix on cards using Streamlit built-ins only
    - Render the cluster comparison chart with a Streamlit built-in chart (`st.bar_chart`) and the Elbow_Plot with a Streamlit built-in chart (`st.line_chart`); do NOT introduce matplotlib or plotly so Requirement 9.9's "no dependency other than kmodes and existing chart libs" holds
    - Render each existing Part 4 card with its Persona_Mix as a visually distinct badge/tab adjacent to the card without overwriting, hiding, or reordering any field; when the mix is unavailable for a cell, render that card intact plus a "persona context unavailable" indication while the remaining cards still render
    - _Requirements: 6.4, 6.5, 7.1, 7.2, 7.5, 9.9_

- [ ] 15. Shared test strategies and end-to-end verification
  - [ ] 15.1 Add shared hypothesis strategies in `tests/strategies_part5_personas.py`
    - Provide generators for joined attribute sets, run specs, and lead pools shared by the property tests; rely on `tests/conftest.py` for `sys.path` (never hardcode it)
    - _Requirements: 2.1, 4.1, 8.1_
  - [ ] 15.2 Write the integration test in `tests/test_part5_personas_integration.py`
    - Run an end-to-end persona run over the sample `data/` + `outputs/` producing a labeled-leads CSV and per-cell mixes; confirm `run_pipeline.py` behavior and `outputs/` byte-identity are unaffected by the presence of `src/part5_personas`
    - _Requirements: 9.2, 9.3, 9.4_
  - [ ] 15.3 Run `pytest` and confirm the existing pipeline is unchanged
    - Run the full `pytest` suite; confirm all persona tests pass and that the existing stages still produce byte-identical `outputs/` artifacts
    - _Requirements: 9.2, 9.3_

- [ ] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All test tasks are required; none are optional.
- Each task references specific requirements for traceability, and property-test tasks name the correctness property they verify.
- The Streamlit page uses only Streamlit built-in charts (`st.bar_chart` / `st.line_chart`) for both the cluster comparison chart and the Elbow_Plot, keeping `kmodes` the only new dependency.
- No module under the existing `run_pipeline.py` stages is modified, and `src/part5_personas` is never added to the stage sequence.
- Checkpoints ensure incremental validation at the end of the pure pipeline, after the CLI, and at the end.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2.1"] },
    { "id": 1, "tasks": ["3.1", "4.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "4.3", "5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "5.4", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "8.1", "9.1"] },
    { "id": 5, "tasks": ["8.2", "8.3", "9.2", "10.1"] },
    { "id": 6, "tasks": ["10.2", "11.1"] },
    { "id": 7, "tasks": ["11.2", "13.1"] },
    { "id": 8, "tasks": ["13.2", "13.3", "14.1"] },
    { "id": 9, "tasks": ["14.2", "15.1"] },
    { "id": 10, "tasks": ["15.2"] },
    { "id": 11, "tasks": ["15.3"] }
  ]
}
```
