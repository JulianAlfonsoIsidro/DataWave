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

- [x] 5. Implement clustering (`cluster.py`)
  - [x] 5.1 Implement seeded k-prototypes fit, k validation, sampling cap, assignment, and elbow sweep
    - Cluster with `kmodes.kprototypes.KPrototypes` seeded with `random_seed=42`; default k to 3 when unspecified; accept integer k in `[2, 6]`; reject non-integer or out-of-range k with an error stating the valid range and produce no assignments
    - When a group exceeds `max_sample_size`, fit on a seeded `numpy.random.default_rng(random_seed)` subsample of the group sorted by `client_id`, then assign the full group to the nearest learned prototype using the k-prototypes mixed dissimilarity with `model.gamma_`
    - Compute the elbow cost sweep for each `k = 2..6` on the shared subsample, recording `cost_` per k
    - _Requirements: 2.1, 2.8, 2.9, 2.10, 2.11, 2.12_
  - [x] 5.2 Write cluster unit tests in `tests/test_part5_personas_cluster_unit.py`
    - Verify invalid-k rejection message, default k=3, and that elbow costs cover k=2..6
    - _Requirements: 2.8, 2.10, 2.12_
  - [x] 5.3 Write the cluster-count property test in `tests/test_part5_personas_cluster_count_property.py`
    - **Property 1: Cluster label count equals k (or the capped k)**
    - **Validates: Requirements 2.9, 3.11**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 1: Cluster label count equals k (or the capped k)`
    - _Requirements: 2.9, 3.11_
  - [x] 5.4 Write the assignment/coverage property test in `tests/test_part5_personas_assignment_property.py`
    - **Property 2: Every clustered lead is assigned exactly one persona**
    - **Property 11: Sampling-then-assign covers all leads**
    - **Validates: Requirements 2.1, 5.4, 8.1**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 2: Every clustered lead is assigned exactly one persona` and `# Feature: persona-segmentation, Property 11: Sampling-then-assign covers all leads`
    - _Requirements: 2.1, 5.4, 8.1_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement persona profiling (`profile.py`)
  - [x] 7.1 Implement `PersonaProfile` stats and distinguishing attributes
    - Compute per persona: `size` (non-negative integer), `pct_of_leads` (0.0–100.0 rounded to one decimal), numeric mean and median per numeric attribute, and top-3 categories per categorical attribute with a fallback to all categories when fewer than 3 are present
    - Compute the top-3 distinguishing attributes via standardized numeric z-score (`abs(mean_p - mu)/sigma`, 0 when sigma is 0) and categorical max absolute proportion-difference against pooled other-personas, never raw values, with ties broken by ascending attribute name
    - Omit zero-size personas from the set rather than profiling them
    - _Requirements: 4.1, 4.2, 4.3, 4.7_
  - [x] 7.2 Write the distinguishing-metric determinism property test in `tests/test_part5_personas_determinism_property.py`
    - **Property 4: Determinism under fixed seed**
    - **Property 10: Distinguishing-metric determinism and standardization**
    - **Validates: Requirements 2.11, 4.3, 4.6**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 4: Determinism under fixed seed` and `# Feature: persona-segmentation, Property 10: Distinguishing-metric determinism and standardization`
    - _Requirements: 2.11, 4.3, 4.6_
  - [x] 7.2b Fix the degenerate sigma=0 case in the distinguishing-metric scale-invariance test (`tests/test_part5_personas_determinism_property.py`)
    - In `test_distinguishing_metric_deterministic_and_standardized`, exclude the degenerate case where every persona shares the same mean for a column (across-persona population std == 0) from the affine scale-invariance assertion, because `a*mean + b` can introduce ~1e-13 floating-point noise that makes the rescaled std non-zero and the z-score spurious
    - Keep the determinism checks; add an explicit assertion that when the across-persona std is 0 the numeric distinctiveness score is exactly 0.0 (the design's `sigma == 0 -> 0.0` rule, Requirement 4.3)
    - Do NOT change `profile.py`; this is a test-only correction to an over-broad property assertion
    - _Requirements: 4.3, 4.6_
  - [x] 7.3 Write the profile-bounds property test in `tests/test_part5_personas_profile_bounds_property.py`
    - **Property 12: Percentage bounds and size consistency**
    - **Validates: Requirements 4.1, 4.7**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 12: Percentage bounds and size consistency`
    - _Requirements: 4.1, 4.7_

- [ ] 8. Implement persona naming (`naming.py`)
  - [x] 8.1 Implement the `PersonaNamer` interface and `RuleBasedNamer`
    - Define the `PersonaNaming` TypedDict (`name`, `description`, `actions`) and the `PersonaNamer` Protocol with `name(profile, taken) -> PersonaNaming`
    - Implement `RuleBasedNamer` deriving name, one-line description, and 2–3 recommended actions purely from the `PersonaProfile` so identical profiles yield identical output
    - Phrase the recommended actions as campaign guidance a campaign planner can act on and, where the profile supports it, name a suggested channel and an offer angle (e.g. "Best reached by SMS with a savings-bundle offer"); keep the channel/angle a deterministic function of the profile and keep names unique and output deterministic (Requirement 4.5)
    - Guarantee unique names within a set using the `taken` set with a deterministic suffix when a base name is already taken; name personas in ascending cluster-label order
    - _Requirements: 4.4, 4.5, 4.6, 4.8, 4.9_
    - NOTE (spec revision): 8.1 is already implemented and completed; the campaign-guidance action wording above is a follow-up refinement to `RuleBasedNamer._actions` to apply the next time this module is edited. It does not change the `PersonaNamer` interface, name uniqueness, or determinism, and does not require re-running the completed task now. The companion naming unit test (8.2) should assert the channel/offer-angle phrasing when that refinement lands.

  - [x] 8.1b Revise `RuleBasedNamer` (`naming.py`) so recommended actions read as campaign guidance
    - Revise `RuleBasedNamer._actions` (and any helper it needs) so each recommended action reads as campaign guidance a campaign planner can act on and, WHERE the `PersonaProfile` supports it, names a suggested channel and an offer angle (e.g. "Best reached by SMS with a savings-bundle offer"), per updated Requirement 4.5
    - Derive the suggested channel deterministically from the profile (e.g. the dominant category of a channel-like categorical attribute when present, otherwise a deterministic default) and the offer angle from the persona's top distinguishing attributes; keep 2–3 actions
    - Keep the `PersonaNamer` interface, the `PersonaNaming` shape, name uniqueness within a set, and full determinism for identical profiles unchanged; update any earlier naming code/tests this affects
    - _Requirements: 4.5, 4.6_
  - [x] 8.2 Write naming unit tests in `tests/test_part5_personas_naming_unit.py`
    - Verify rule-based name/description/2–3 actions for representative profiles and the disambiguation suffix path
    - _Requirements: 4.4, 4.5, 4.8_
  - [x] 8.3 Write the unique-names property test in `tests/test_part5_personas_naming_unique_property.py`
    - **Property 7: Persona names are unique within a set**
    - **Validates: Requirements 4.9**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 7: Persona names are unique within a set`
    - _Requirements: 4.9_
  - [x] 8.1c Revise persona naming to be direction-aware and readable (`naming.py`, `profile.py`)
    - Add a `distinguishing_directions: dict[str, str]` field to `PersonaProfile` computed in the profiling stage from the across-persona average (per distinguishing attribute: `high`/`low` for numeric, `more`/`fewer` for categorical, `flat` when there is no contrast), a pure deterministic function of the already-computed stats; do NOT change the distinguishing-attribute ranking (Requirement 4.3)
    - Rewrite `RuleBasedNamer._base_name` to compose the name from the top distinguishing attributes using their plain-language labels plus a direction word, reading only `profile.distinguishing` and the new `profile.distinguishing_directions`; keep the `PersonaNamer.name(profile, taken)` Protocol signature unchanged (Requirement 4.8) and the output deterministic (Requirement 4.6)
    - Flag-phrasing refinement (approved): for boolean/flag-style attributes render "More/Fewer <plural label>" (e.g. "More app users") rather than an awkward "High <verb-phrase label>"; reserve High/Low for genuinely numeric attributes (e.g. "High total outflows", "Low payroll income"); drop the redundant trailing "Persona"
    - Use the same plain-language attribute labels the Attribute_Picker uses; move that raw-column -> label map into a shared location importable by the pure pipeline (so `naming.py` does not import `app/`), or duplicate a minimal map in the pipeline with a title-cased fallback — keep it a pure function
    - Disambiguation: when the composed base name is still taken, extend to the third distinguishing attribute before falling back; as a last resort replace " (cluster N)" with a letter suffix (" (A)", " (B)"). Keep names unique within a set (Requirement 4.9)
    - Keep the recommended actions unchanged
    - _Requirements: 4.3, 4.4, 4.6, 4.8, 4.9_
  - [x] 8.1d Update naming tests for the direction-aware format
    - Update `tests/test_part5_personas_naming_unit.py` and the Property 7 test `tests/test_part5_personas_naming_unique_property.py` to match the new name format; add a test that two personas with the same top attributes but opposite directions receive different names; keep determinism and uniqueness assertions
    - _Requirements: 4.6, 4.9_

- [x] 9. Implement levels and the two-step flow (`grouping.py`)
  - [x] 9.1 Implement clustering levels, two-step grouping, and group-size handling
    - Support levels `all` (one set), `business-segment` (one set per distinct `Business_Segment_Field` value using `customer_dna.segment` or Part 3 `Segment_Label`; reject naming the field when it has no usable values), and `campaign` (cluster only the chosen pool, exclude out-of-pool leads, use no `Business_Segment_Field` as a clustering feature; report empty-audience without clustering on an empty pool)
    - Implement the two-step flow: partition by `Grouping_Attributes`, then cluster each group on `Clustering_Attributes` with k per group
    - Flag groups below `min_group_size` as "too small to cluster" (`too_small=True`, no personas); cap k to the group size when the group is at/above `min_group_size` but below the requested k
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 5.4, 5.5, 5.6_
  - [x] 9.2 Write grouping edge tests in `tests/test_part5_personas_grouping_edge.py`
    - Verify the too-small group flag, k-cap-to-group-size, empty business-segment field rejection, and empty campaign pool handling
    - _Requirements: 3.7, 3.10, 3.11, 5.6_

- [x] 10. Implement the leads export (`export.py`)
  - [x] 10.1 Implement `Persona_Labeled_Leads` construction and the default `Campaign_Leads_Export`
    - Produce exactly one row per Part 4 leads-input lead with a `persona_label` column assigning each to one persona and a `group` column (business-segment value or campaign identifier per level)
    - Left-join on `client_id` the richer attributes from `customer_dna.csv`, the pivoted `product_ownership.csv`, and `features_part2.csv`, preserving every source column name, dropping no lead and introducing no duplicates, leaving unmatched source attributes empty
    - At `campaign` level, leave `persona_label` and `group` empty for leads outside the chosen pool
    - Expose a default `Campaign_Leads_Export` variant with exactly `client_id`, the `persona_label` column, the `group` column, `best_channel`, `p_join`, and `control` (a column projection of the full frame, one row per Part 4 lead, agreeing row-for-row on `client_id`/persona label/group), and keep the full `Persona_Labeled_Leads` (all richer joined attributes) as the optional second variant; both preserve the one-row-per-lead guarantee
    - Make the export the last step, produced only after clustering and profiling both succeed
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_
  - [x] 10.2 Write the export-rows property test in `tests/test_part5_personas_export_rows_property.py`
    - **Property 8: Export row count equals the input lead count**
    - **Property 9: Group column correctness**
    - **Validates: Requirements 8.1, 8.3, 8.6, 8.7**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 8: Export row count equals the input lead count` and `# Feature: persona-segmentation, Property 9: Group column correctness`
    - _Requirements: 8.1, 8.3, 8.6, 8.7_

- [x] 11. Implement the CLI entry point (`main.py`)
  - [x] 11.1 Implement `main(argv: list[str] | None = None) -> int`
    - Parse path-override flags (`--customer-dna`, `--product-ownership`, `--features-part2`, `--segments`, `--cards`, `--leads-dir`, `--promo-leads`, `--labeled-leads-out`) onto `Config`
    - Run the pipeline in order (join → preprocess → cluster → profile → name → group → export); halt before any write when a required `outputs/` artifact is missing, returning non-zero and naming the missing artifact
    - Perform every output write only after all clustering and profiling succeed (output-last); return 0 on success and a non-zero code naming the failing step otherwise; end with the `if __name__ == "__main__": raise SystemExit(main())` guard
    - _Requirements: 9.1, 9.3, 9.5, 9.6, 9.7, 9.8_
  - [x] 11.2 Write main unit tests in `tests/test_part5_personas_main_unit.py`
    - Verify `main` exit codes, missing-artifact halt message, and output-last write safety (no file written on a mid-run failure)
    - _Requirements: 9.5, 9.6, 9.7, 9.8_

- [ ] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Implement the `Persona_Core` orchestration (`src/webapp_core/personas.py`)
  - [x] 13.1 Implement `run_personas` and `persona_mix_by_cell` with no Streamlit imports
    - Implement `run_personas(spec, namer, cfg, *, live_leads=None) -> PersonaRunResult` building the joined set and running levels/grouping/clustering/profiling/naming deterministically; use the current New Promo session leads for the campaign live pool and `promo_leads.csv` / `outputs/leads/` for past promos
    - Implement `persona_mix_by_cell(labels, cards) -> dict[(promo_id, segment), PersonaMix]` computing per-cell shares normalized to sum to 100% for non-empty cells and aligning them onto the existing Part 4 cards by `(promo_id, segment)` without mutating any card; mark `available=False` when a cell has no assignment
    - Reuse Part 3 `assign_segments` and Part 4 `build_cards` read-only; add no modelling and no Streamlit imports
    - _Requirements: 5.1, 5.3, 6.8, 7.1, 7.3, 7.4, 7.5_
  - [x] 13.2 Write the persona-mix sum property test in `tests/test_part5_personas_mix_sum_property.py`
    - **Property 3: Persona mix sums to 100% per non-empty cell**
    - **Validates: Requirements 7.1**
    - hypothesis, minimum 100 iterations, tagged `# Feature: persona-segmentation, Property 3: Persona mix sums to 100% per non-empty cell`
    - _Requirements: 7.1_
  - [x] 13.3 Write cards-mix unit tests in `tests/test_part5_personas_cards_mix_unit.py`
    - Verify the mix is joined by `(promo_id, segment)`, that every Part 4 card field is unchanged byte-for-byte, and the unavailable-mix fallback
    - _Requirements: 7.2, 7.3, 7.4, 7.5_

- [ ] 14. Implement the Streamlit `Persona_Page` (`app/`)
  - [x] 14.1 Build the CRM-friendly page composition and session-state wiring
    - Render the Clustering_Level selector with the plain labels "All leads" / "By customer segment" / "By campaign" mapped to internal values `all` / `business-segment` / `campaign` (default `all`); a k selector labeled "Number of personas", integers 2–6, default 3; and a Run control
    - Render the Attribute_Picker over Joined_Attribute_Set columns grouped under Demographics / Lifestyle / Products owned / Spending behavior with readable display labels (e.g. "Owns deposit account" for `owns_deposit`) while passing the raw column name as the selected value; preselect a Default_Attribute_Set so Run works immediately; do NOT render any numeric/categorical type-override control (auto-detect stays in the backend; override stays available via Config/API). Keep the raw→(group,label) mapping and Default_Attribute_Set in the `app/` layer with a graceful fallback for unmapped columns
    - Replace the two separate Grouping/Clustering controls with one optional control phrased "Split by [attributes] first, then create personas within each group": its attributes become `grouping_attributes` in the spec, the Attribute_Picker selection stays `clustering_attributes`, and "Number of personas" stays per-group k (the spec handed to the pipeline is unchanged)
    - Render the campaign pool selector (live session leads or past promo by `promo_id` in P001/P002/P003, disabling the live choice when no run exists), showing the promo name or date next to the `promo_id` when available while still selecting by `promo_id`
    - On an invalid configuration (fewer than one attribute, k outside 2–6, or no level) reject the run, retain current configuration and displayed results, and show an actionable error that names the invalid input and how to fix it; render any "too small to cluster" group as an actionable instruction stating the lead count (e.g. "This segment has only 12 leads. Pick a larger segment or combine segments.")
    - Render one summary card per persona (name, description, integer size, one-decimal percentage, distinguishing attributes as plain sentences, and recommended actions as campaign guidance); default the download control to the `Campaign_Leads_Export` and offer the full `Persona_Labeled_Leads` as a clearly labeled optional second download, both disabled until a run completes in the session
    - Delegate all clustering and profile computation to `Persona_Core` / `Persona_Pipeline`; own the `st.cache_data` wrappers in this layer; keep all label/mapping/message/standardization helpers as pure functions so they can be unit-tested (see 14.3)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.13, 3.14, 3.15, 4.5, 4.10, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.6, 6.7, 6.9, 6.10, 8.8, 8.9, 8.10_
  - [x] 14.1b Fix the Persona_Page `st.cache_data` key so changing the spec refits (`app/persona_page.py`)
    - Root cause of the "changing level / split-first / attributes / k returns the same personas" bug: the `st.cache_data`-wrapped run function was defined nested inside its caller and closed over the spec instead of taking it as an argument, and a later variant named every cached parameter with a leading underscore (which tells Streamlit to skip hashing it), so the cache key collapsed to a constant and every run served a stale hit
    - Fix: define the cached run function ONCE at module scope (`_run_personas_impl`), keyed on a full `_spec_fingerprint` (level, sorted clustering_attributes, sorted grouping_attributes, k, business_segment_field, campaign_pool, type_overrides, seed) plus a `_live_leads_fingerprint`, with the two fingerprint parameters NOT underscore-prefixed (so Streamlit hashes them) and only the pass-through spec/live_leads underscore-prefixed; build/memoize the `st.cache_data` wrapper lazily so the module still imports without Streamlit
    - Add a pure-Python regression test `tests/test_part5_personas_run_varies_unit.py` asserting that `run_personas` outputs differ when the spec differs only in level, only in attributes, only in k, or only in the two-step grouping, and that `_spec_fingerprint` differs for each pair (no Streamlit UI)
    - _Requirements: 6.1, 6.9_
  - [x] 14.2 Render the charts and the persona mix on cards using Streamlit built-ins only
    - Render the cluster comparison chart with a Streamlit built-in chart (`st.bar_chart`) comparing standardized differences per attribute (each persona shown as above/below the across-persona average), not raw values on mixed scales; compute the standardization in the `app/` layer from the already-returned per-persona numeric means (center on the across-persona mean, divide by the across-persona std, 0 when std is 0)
    - Render the Elbow_Plot with a Streamlit built-in chart (`st.line_chart`) inside a collapsed "Advanced" expander titled "How many personas fit best?" with the caption "Pick the point where the line starts to flatten."; rendering inside the expander counts as displaying the Elbow_Plot (Requirement 6.5). Do NOT introduce matplotlib or plotly so Requirement 9.9's "no dependency other than kmodes and existing chart libs" holds
    - Render each existing Part 4 card with its Persona_Mix as a visually distinct badge/tab adjacent to the card without overwriting, hiding, or reordering any field; when the mix is unavailable for a cell, render that card intact plus a "persona context unavailable" indication while the remaining cards still render
    - _Requirements: 6.4, 6.5, 7.1, 7.2, 7.5, 9.9_
    - NOTE (spec revision): the standardized `st.bar_chart` and the Elbow_Plot expander described above are SUPERSEDED. Task 14.5 removed the Elbow_Plot from the page (backend sweep kept) and task 14.6 replaced the bar chart with the "How the Personas Differ" comparison table (revised Requirements 6.4 and 6.5). The persona-mix-on-cards part of this task is unchanged. This task's completed status is not altered.

  - [ ] 14.3 Write Persona_Page helper unit tests in `tests/test_part5_personas_page_unit.py`
    - Unit-test the pure presentation helpers from 14.1/14.2: the raw-column → (Attribute_Group, Attribute_Display_Label) mapping and the Default_Attribute_Set; the plain-label ↔ internal-value level mapping; the plain-sentence rendering of distinguishing attributes; the "How the Personas Differ" comparison helpers (`persona_trait_tags` / `persona_comparison_frame`: plain tags, no z-scores or costs, flag attributes read More/Fewer); the `Campaign_Leads_Export` column projection (exactly client_id, persona label, group, best_channel, p_join, control, one row per lead); and the actionable too-small / validation message strings
    - Keep these helpers importable without launching Streamlit (test the pure functions, not the rendered widgets)
    - _Requirements: 3.1, 3.4, 3.8, 3.13, 3.14, 4.10, 6.2, 6.4, 6.10, 8.8_

  - [ ] 14.4 (Optional) Add a downloadable one-page Persona_Brief
    - Implement a pure Persona_Brief builder (in the `app/` layer or a small pure helper beside `webapp_core/personas.py`) that renders, per persona in a `PersonaSet`, the persona name, size (integer lead count), key traits as plain sentences (Requirement 4.10), and a recommended campaign angle derived from the recommended actions (Requirement 4.5); the brief is a deterministic function of the `PersonaSet`
    - Add a Persona_Page download control for the brief that stays disabled until a persona run has completed in the session
    - This task is OPTIONAL and may be skipped if time is short; skipping it does not affect any other task
    - Write `tests/test_part5_personas_brief_unit.py` asserting the brief carries each persona's name/size/key-traits/campaign-angle and that an identical `PersonaSet` yields an identical brief (determinism)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 14.5 Remove the Elbow_Plot from the Persona_Page (`app/persona_page.py`)
    - Delete the "Advanced" elbow expander and the page-side `elbow_frame` helper (and any page unit test that only covers it) so the page no longer renders the Elbow_Plot, per revised Requirement 6.5
    - KEEP the backend elbow computation in `cluster.py` and its tests unchanged (`PersonaSet.elbow_costs` still populated; Requirement 2.12 is unaffected)
    - _Requirements: 6.5_
  - [x] 14.6 Replace the standardized comparison chart with a CRM-friendly comparison table (`app/persona_page.py`)
    - Replace the `st.bar_chart` standardized-difference chart with a "How the Personas Differ" side-by-side comparison TABLE: one row per persona with the persona name, size, share, and plain-language trait tags (e.g. "Higher inflows", "Fewer products", "Mostly SMS-reachable"); never show z-scores or clustering cost values, per revised Requirement 6.4
    - Derive the trait tags from the same distinguishing-attribute ranking and direction signal (reuse the `distinguishing_directions` from 8.1c) using the plain-language labels; keep the tag/table builder a pure, unit-testable function
    - Remove `standardized_comparison_frame` and its unit tests if they become unused
    - _Requirements: 6.4_
  - [x] 14.7 Add a group selector that filters the whole page to one group (`app/persona_page.py`)
    - When the user checks "Split into groups first, then build personas within each group", render a dropdown listing each resulting group (e.g. each age band), defaulting to the first group, with an "All groups" option at the end
    - When one group is selected, scope EVERYTHING on the page to that group only: the persona cards, the "How the Personas Differ" comparison, the Decision Cards With Persona Mix (compute the mix from only that group's leads), and the download (the file contains only that group's leads, with the group named in the filename); add a caption stating what the download contains
    - Groups flagged "too small to cluster" still appear in the dropdown, showing the actionable message instead of personas
    - Switching groups must NOT refit the clustering (serve from the existing `st.cache_data` result) and must NOT reset the other settings
    - Keep the group-filtering logic as pure functions (filter a `PersonaRunResult`/labels to a group, scope the mix inputs, project the per-group download frame + filename) so they are unit-testable without Streamlit
    - _Requirements: 3.8, 3.10, 6.3, 6.4, 6.10, 7.1, 8.8, 8.10_
  - [x] 14.8 Write group-filter unit tests in `tests/test_part5_personas_group_filter_unit.py`
    - Unit-test the pure group-filtering helpers from 14.7 (no Streamlit UI): selecting one group yields only that group's persona set / labels / mix inputs / download rows and filename; "All groups" is the unfiltered view; a too-small group surfaces its message; and the group selection does NOT alter the underlying persona assignments (same labels for a client regardless of the selected view)
    - _Requirements: 3.8, 3.10, 7.1, 8.8_

- [ ] 15. Shared test strategies and end-to-end verification
  - [x] 15.1 Add shared hypothesis strategies in `tests/strategies_part5_personas.py`
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

- All test tasks are required except the optional Persona_Brief task 14.4 and its test, which may be skipped if time is short.
- Each task references specific requirements for traceability, and property-test tasks name the correctness property they verify.
- The Streamlit page uses only Streamlit built-ins (`st.dataframe` for the "How the Personas Differ" table); the earlier bar chart and Elbow_Plot were removed from the page (tasks 14.5, 14.6), keeping `kmodes` the only new dependency.
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
    { "id": 5, "tasks": ["8.1b"] },
    { "id": 6, "tasks": ["8.2", "8.3", "9.2", "10.1"] },
    { "id": 7, "tasks": ["10.2", "11.1"] },
    { "id": 8, "tasks": ["11.2", "13.1"] },
    { "id": 9, "tasks": ["13.2", "13.3", "14.1"] },
    { "id": 10, "tasks": ["14.2", "15.1"] },
    { "id": 11, "tasks": ["7.2b", "14.1b", "8.1c"] },
    { "id": 12, "tasks": ["8.1d", "14.5", "14.6", "14.7"] },
    { "id": 13, "tasks": ["14.8", "14.3", "14.4"] },
    { "id": 14, "tasks": ["15.2"] },
    { "id": 15, "tasks": ["15.3"] }
  ]
}
```

