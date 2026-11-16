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
  - [x] 4.4 Classify binary flag columns as categorical (`preprocess.py`)
    - Conflict being resolved: Requirement 1.3 says every Product_Ownership_Flag is categorical, but `classify_types` classified by dtype only, so the 0/1 integer flags (`owns_*`, `digital_app_user`, `frugal_flag`, `email_valid`, `mobile_valid`) were treated as numeric (standardized, clustered with k-means distance, profiled with high/low) -- and the channel suggestion, which reads the dominant "1" category of those flags, never fired
    - Write the failing tests FIRST: flag columns classified categorical; other int/float columns (counts, ratios, amounts, a column with values outside {0, 1}) stay numeric; a float column holding only 0.0/1.0 with NaN is a flag; boolean dtype is a flag; a `type_overrides` entry still wins in both directions; the `preprocess()` orchestrator reports the flag's positional index as categorical; and (with 14.9) `age_band` (a text column) + `owns_Deposit` is categorical-only, `tenure_years` (numeric) + `owns_Deposit` is mixed, and `digital_app_user` + `frugal_flag` is categorical-only; also note that `inflow_share_business_receipts` holds only 0.0/1.0 in the sample data and therefore classifies as a flag
    - Apply the smallest fix in `classify_types` only; update Requirement 2.2, `design.md` Preprocessing and traceability. Update ONLY existing test expectations that changed because of the classification, listing each with the reason
    - _Requirements: 1.3, 2.2, 2.3, 2.7_
    - NOTE (spec revision): the float 0.0/1.0 flag rule above is narrowed by task 4.5 (integer/boolean dtypes and known flag names only); this task's completed status is not altered
  - [x] 4.5 Restrict the binary-flag rule to integer/boolean dtypes and known flag names (`preprocess.py`, `profile.py`)
    - NOTE (follow-up to 4.4, whose completed status is unchanged): 4.4's "float 0.0/1.0 is a flag" rule over-matched -- `inflow_share_business_receipts` is a float share that holds only 0.0 and 1.0 in the sample data and was reclassified as categorical
    - Write the failing tests FIRST: every `inflow_share_*` column stays numeric on the real sample data; a float column holding only 0.0/1.0 stays numeric; an integer or boolean column holding only {0, 1} is categorical; `owns_*` columns and the explicit names `digital_app_user`, `frugal_flag`, `email_valid`, `mobile_valid` are categorical even when stored as float with missing values; an unnamed float 0/1 column stays numeric (documented limit); overrides still win both ways; and a float-stored known flag reports its categories as `"1"`/`"0"` (not `"1.0"`/`"0.0"`)
    - Apply the smallest fix: in `classify_types` keep the `owns_*` prefix and the explicit known-name list, limit the value rule to integer/boolean dtypes; in `profile._top_categories_for` normalise integral floats to integer text. Update ONLY existing test expectations changed by the narrower rule (the 4.4 tests that expected float 0/1 columns to be flags), listing each with the reason
    - Report whether any flag stored as float would now be misclassified
    - _Requirements: 1.3, 2.2, 2.3, 2.7_
  - [x] 4.6 Fix the direction of binary flags (compare the share of "yes", not of the dominant category) (`profile.py`, `app/persona_page.py`)
    - Bug (introduced when 4.4 made 0/1 flags categorical, found while prototyping 8.1e): `profile._categorical_direction` compares the share of a persona's DOMINANT category with the other personas'. For a 0/1 flag whose dominant category is "0" that means "more non-users", yet the name and trait tag read "More App Users" (real example: a 215-person persona with 145 non-app and 70 app users was named "Low Payroll Income / More App Users"). The page's plain sentences (`_standardized_direction`) have the same defect
    - Write the failing tests FIRST: a persona whose members are mostly non-users must be "fewer", never "more"; the persona with the highest "1" share is "more"; equal shares are "flat"; a non-binary categorical attribute (for example `age_band`) keeps the dominant-category comparison; the name, the trait tag and the plain sentence for the mostly-non-user persona all read Fewer/fewer, never More/more
    - Fix: for a binary flag (category values within {"0","1"}) compare the persona's share of "1" with the other personas' pooled share of "1"; make the page's sentence logic read `PersonaProfile.distinguishing_directions` (one source of truth) instead of re-deriving it; make flag-style sentence wording read naturally ("use the mobile app", "shop online")
    - Show 2-3 before/after names from the same runs; keep names unique and deterministic; the distinguishing-attribute ranking is unchanged
    - _Requirements: 4.3, 4.4, 4.10, 6.4_

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
  - [x] 5.5 Add a seeded single-type fallback for numeric-only and categorical-only selections (`cluster.py`)
    - Reproduced crashes: numeric-only raises `NotImplementedError: No categorical data selected, effectively doing k-means`; categorical-only raises `AssertionError: All columns are categorical, use k-modes instead of k-prototypes` (both from `KPrototypes.fit`), so a Persona_Page run on such a selection ends in "Could not build personas"
    - Write the failing tests FIRST: cluster unit tests for both degenerate cases (label contract 0..k-1 with every lead labeled once, `validate_k` behavior, determinism under seed 42, sampling cap with full-population assignment, elbow costs for each feasible k, k-cap on a small group, mixed selections unchanged) in `tests/test_part5_personas_cluster_single_type_unit.py`, plus one integration case each (numeric-only and categorical-only `run_personas` on the real sample data: every lead assigned, names unique with no "(cluster", exports built, deterministic) in `tests/test_part5_personas_single_type_integration.py`; use `deadline=None` for any hypothesis test that fits real models
    - Then apply the smallest fix in `cluster.py`: numeric-only -> seeded `sklearn.cluster.KMeans` (cost = `inertia_`), categorical-only -> seeded `kmodes.kmodes.KModes` (cost = `cost_`), mixed -> `KPrototypes` unchanged; reuse `validate_k`, the subsample, `predict` for the full group, and the elbow sweep; no new dependency; do not change profiling, naming, grouping, or export
    - _Requirements: 2.1, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 3.11_

- [x] 6. Checkpoint - Ensure all tests pass
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

- [x] 8. Implement persona naming (`naming.py`)
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
  - [x] 8.1e Data-driven channel suggestion from persona-vs-group channel reach (`profile.py`, `grouping.py`, `naming.py`)
    - Problem: with the flags categorical the channel rule read the dominant "1" category of `digital_app_user`, which is "1" for almost every persona, so 11 of 12 personas suggested In-app and the channel no longer differentiated
    - Add a profile field (for example `channel_reach`) holding, per channel, the persona's share of members reachable on it, the group's overall share, and the persona size, using `digital_app_user` (In-app), `email_valid` (Email) and `mobile_valid` (SMS); compute it in `grouping.py` from the group's rows so it exists even when those flags are not clustering attributes; the `PersonaNamer` interface is unchanged; do NOT use Part 4 `best_channel`
    - Rule: a channel stands out when the persona's share exceeds the group's by at least 3 percentage points AND by at least 2 standard errors; the strongest (highest z) wins, ties go In-app, then Email, then SMS; otherwise the first action reads "Reachable on every channel about equally; lead with SMS (widest reach)" (naming the widest-reach channel, ties In-app, Email, SMS) followed by the offer angle; an empty `channel_reach` keeps the previous behaviour
    - Write the failing tests FIRST (stands out, strongest wins, tie precedence, 3-point gap not met, 2-standard-error test not met on a small persona, fallback wording and widest-reach choice, empty reach keeps the old rule, determinism, names still unique, profile-level shares and group overall computed correctly including flags that are not clustering attributes, and a real-data run)
    - Show before/after channels for the same runs as before; keep names unique and deterministic
    - _Requirements: 4.5, 4.6, 4.8, 4.9_
  - [x] 8.1f Reword the channel fallback sentence (`naming.py`)
    - Problem: the fallback action read "Reachable on every channel about equally; lead with SMS (widest reach) with a savings-bundle offer", with an awkward double "with"
    - Write the failing tests FIRST (exact new wording, no double "with", still names the widest-reach channel with the In-app/Email/SMS tie order, still carries the offer angle, the stand-out wording "Best reached by {channel} with a {angle}" is unchanged, empty `channel_reach` behaviour unchanged, deterministic, names unchanged and unique)
    - New fallback: "Reachable on every channel about equally; lead with {channel} (widest reach). Offer angle: a {angle}." (for example "... lead with SMS (widest reach). Offer angle: a savings-bundle offer."); update ONLY the existing 8.1e test expectations that assert the old fallback text, listing each with the reason
    - _Requirements: 4.5, 4.6_

- [x] 9. Implement levels and the two-step flow (`grouping.py`)
  - [x] 9.1 Implement clustering levels, two-step grouping, and group-size handling
    - Support levels `all` (one set), `business-segment` (one set per distinct `Business_Segment_Field` value using `customer_dna.segment` or Part 3 `Segment_Label`; reject naming the field when it has no usable values), and `campaign` (cluster only the chosen pool, exclude out-of-pool leads, use no `Business_Segment_Field` as a clustering feature; report empty-audience without clustering on an empty pool)
    - Implement the two-step flow: partition by `Grouping_Attributes`, then cluster each group on `Clustering_Attributes` with k per group
    - Flag groups below `min_group_size` as "too small to cluster" (`too_small=True`, no personas); cap k to the group size when the group is at/above `min_group_size` but below the requested k
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 5.4, 5.5, 5.6_
  - [x] 9.2 Write grouping edge tests in `tests/test_part5_personas_grouping_edge.py`
    - Verify the too-small group flag, k-cap-to-group-size, empty business-segment field rejection, and empty campaign pool handling
    - _Requirements: 3.7, 3.10, 3.11, 5.6_
  - [x] 9.3 Restrict the business-segment grouping field to `customer_dna.segment` (`grouping.py`, `app/persona_page.py`)
    - NOTE (numbering): requested as "3.13"; the 3.x tasks are the data-join tasks and this change belongs to grouping (Requirement 3.5), so it is 9.3. Earlier tasks' completed statuses are unchanged; 9.1's text offering "Part 3 `Segment_Label`" is superseded by this task
    - Why: the Part 3 Segment_Label is per (client, promo), not a column of the joined data, so choosing it on the page failed; it is still used for decision-card cells and the Persona_Mix
    - Write the failing tests FIRST: the group-field options offered to the user contain only `customer_dna.segment` (pure functions in the grouping module and the page module); the "By customer segment" level uses `segment` directly (no picker) and other levels use none; an unknown field (for example `segment_label`) raises `InvalidSegmentFieldError` naming the field and the valid option and mentioning the per-client/per-promo reason; a missing field (None) lists the valid option; the all-null-field error and valid runs are unchanged; the page source no longer offers a "Part 3 segment label" choice
    - Apply: remove the dropdown from the page and use `segment` directly; add `BUSINESS_SEGMENT_FIELD` / `BUSINESS_SEGMENT_FIELD_OPTIONS` and `InvalidSegmentFieldError` in `grouping.py` with the actionable messages; the page shows that error message as-is; update docstrings and UI text that mention the Part 3 label as a grouping option; leave the Part 4 cell key, the Persona_Mix, the export `group` column, the group dropdown and the downloads untouched
    - _Requirements: 3.5, 3.6, 3.7, 3.20_

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

- [x] 12. Checkpoint - Ensure all tests pass
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
  - NOTE: 14.3 (NOT DOING) and 14.4 (optional, deferred) are intentionally not done, so this parent stays unchecked; all other sub-tasks are complete.
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
    - NOT DOING: the page is now covered by the group-filter, selection-kind, sentence and segment-field unit tests plus the AppTest smoke test of the Personas tab, so a separate helper-test file is not needed (decision recorded; status left unchecked because there is no skipped state)

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
  - [x] 14.9 Warn on single-type attribute selections and caption the clustering kind (`app/persona_page.py`)
    - NOTE: requested as "task 14.5 after 14.2", but 14.5 already exists (completed elbow removal) and earlier tasks are not renumbered, so this is 14.9
    - Add a pure function that classifies the current selection (using the pipeline's `classify_types`, so it matches what the backend runs) as `numeric` / `categorical` / `mixed` / `none`, and a pure function mapping that to the warning text; show a non-blocking `st.warning` above the Run button for numeric-only ("Only numeric attributes selected. Personas will be based on those alone. Adding a categorical attribute (such as region or a product owned) gives richer personas.") and categorical-only ("Only categorical attributes selected. Personas will be based on those alone. Adding a numeric attribute (such as years with the bank or spend) gives richer personas."); no confirmation step; nothing for mixed; an empty selection keeps the existing "pick at least one attribute" error
    - Do NOT claim k-prototypes gives better results; the copy may only say mixing both types gives richer personas
    - After a run, show a short caption stating the kind of clustering used (e.g. "Clustered on numeric attributes only"); no caption for mixed selections
    - Unit-test the pure functions in `tests/test_part5_personas_selection_kind_unit.py` (numeric-only, categorical-only, mixed, empty; warning/caption text; no Streamlit UI)
    - _Requirements: 6.2, 6.11, 6.12_
  - [x] 14.10 Name the dominant category in sentences for non-flag categorical attributes (`app/persona_page.py`)
    - Problem: the persona-card sentence for a non-flag categorical said "more likely to be age band" (the attribute label, not the category); `online_shopper` is an ordinal text column (High / Medium / Low ...), so its flag-style wording is also wrong
    - Write the failing tests FIRST: age_band reads "more likely to be in the 35-44 age band"; region, customer segment, socio-economic class, main money-in type and online shopper level each name the persona's dominant category in natural wording; an unknown categorical falls back to "have <label> of <category>"; binary 0/1 flags keep their wording ("fewer likely to use the mobile app"); numeric wording is unchanged; deterministic; names unchanged and unique
    - Fix in the pure sentence helper only: for a non-binary categorical attribute the phrase names the persona's dominant category (`top_categories[column][0][0]`), the same category the recorded more/fewer direction compares
    - _Requirements: 4.10_
  - [x] 14.11 Say "less likely" instead of "fewer likely" in persona sentences (`app/persona_page.py`)
    - Problem: the plain sentence for a "fewer" direction read "fewer likely to use the mobile app" / "fewer likely to be in the 25-34 age band", which is ungrammatical
    - Write the failing tests FIRST: a flag with direction fewer reads "less likely to use the mobile app"; a non-flag categorical reads "less likely to be in the 55+ age band"; owns/has/shops flag wording uses "less likely"; "more likely" is unchanged; the word "fewer" never appears in a sentence's "likely" phrase; numeric wording ("higher"/"lower") is unchanged; the trait tags ("Fewer app users") and the persona names are unchanged; deterministic
    - Fix only the sentence phrase composition (map the "fewer" direction to "less" in the "<direction> likely ..." phrases); update ONLY the sentence expectations that asserted "fewer likely", listing each with the reason
    - _Requirements: 4.10_
  - [x] 14.12 Fix the numeric-only warning example (`app/persona_page.py`)
    - Problem: the numeric-only warning suggested "such as marital status", but no such attribute exists in the data
    - Write the failing test FIRST (the exact warning text), then change the copy to: "Only numeric attributes selected. Personas will be based on those alone. Adding a categorical attribute (such as region or a product owned) gives richer personas."
    - _Requirements: 6.11_
  - [x] 4.7 Choose the focus category of a text attribute by lift (`profile.py`)
    - Problem: names, tags and sentences showed the persona's most common category, which is often just the most common category overall (for example the biggest age band), so it says little about the persona
    - Add a profile field (for example `focus_categories`) giving, per non-flag categorical attribute, the category where the persona is most over-represented: lift = the persona's share of the category divided by the group's overall share; ties go to the persona's most common category, then to the category name; only categories making up at least 10% of the persona are candidates (a floor so a tiny category cannot win on noise; if none qualifies, all categories are candidates); with no baseline (for example a single persona) all lifts are equal and the most common category wins
    - Direction of a non-flag categorical attribute now compares the persona's share of its focus category with the other personas' pooled share of that category; the distinguishing-attribute ranking is unchanged; yes/no flags are unchanged
    - Write the failing tests FIRST, including one where the persona's most common category equals the overall most common and a smaller category has higher lift (the smaller category must win), the tiebreaks, the 10% floor, no-baseline, flag columns unchanged, determinism; show a before/after (most common vs lift) on one real run; update ONLY existing expectations that changed because the focus category replaced the most common one, listing each with the reason
    - _Requirements: 4.3, 4.4, 4.6_
  - [x] 8.1g Name the focus category in persona names (`naming.py`, `labels.py`)
    - Names show the focus category for text categoricals, for example "25-34 Age Band / Luzon Region", "Class C1 / Salary Inflows"; yes/no flags and numeric wording are unchanged; a rare "fewer" reads "Fewer <phrase>"
    - Shared category wording lives in `labels.py` (the pipeline must not import `app/`): age_band "<c> Age Band", region "<c> Region", segment "<c> Segment", sec_class "Class <c>", inflow_type "<c> Inflows", online_shopper "<c> Online Shoppers", any other text column "<Label>: <c>"
    - Keep names unique and deterministic: a base name has at most two parts; on a collision keep the existing third-attribute extension (capped at three parts), then the letter suffix; the description and the category-specific action also name the focus category so a card never contradicts its name
    - Write the failing tests FIRST (wording per column, flags and numerics unchanged, collision order and the three-part cap, uniqueness and determinism, fallback to the most common category when a profile has no focus categories); update ONLY the expectations that changed, listing each
    - _Requirements: 4.4, 4.6, 4.9_
  - [x] 14.13 Name the focus category in trait tags and sentences (`app/persona_page.py`)
    - Tags and sentences use the focus category from 4.7 instead of the most common one; tag wording is consistent and natural: "More aged 25-34", "More from Luzon", "More in the Mass segment", "More in class C1", "More Salary-led money-in", "More High-tier online shoppers", other text columns "More <label>: <value>"; "Fewer ..." for the rare opposite; yes/no flags and numeric tags are unchanged; sentence wording from 14.10/14.11 is unchanged except for the category shown
    - Write the failing tests FIRST (each column's tag and sentence names the focus category, not the most common one; fallback when a profile has no focus categories; flags and numerics unchanged); update ONLY the expectations that changed, listing each
    - _Requirements: 4.10, 6.4_
  - [x] 14.14 Hide constant columns from the attribute picker and default set (`app/persona_page.py`)
    - A column with a single distinct value across the joined data (for example `owns_Deposit`, which every client has) cannot distinguish personas, so it is omitted from the picker and the default set
    - Write the failing pure-function tests FIRST (constant columns detected, ignores NaN, keeps varying columns, the default set drops hidden columns, `client_id` untouched), then wire it into the picker's column list
    - _Requirements: 3.1, 3.13, 3.21_
  - [x] 14.15 Add a Streamlit AppTest smoke test of the Personas tab (`tests/test_part5_personas_apptest_smoke.py`)
    - Render the Personas tab headlessly with Streamlit's `AppTest` on a small sampled dataset (k=2 or 3) and check: personas render with the default attributes at "All leads"; the single-type warning appears for numeric-only and for categorical-only selections and not for a mix; the group dropdown appears with the split option and scoping a group scopes the output; an invalid grouping field shows the actionable error message as-is
    - Keep it as fast as possible; this smoke test replaces the separate page-helper test file (14.3 is not being done)
    - _Requirements: 3.16, 3.17, 3.20, 6.3, 6.11_
  - [x] 8.1h Use business labels in every persona name, description and action (`naming.py`, `labels.py`)
    - Problem: actions and descriptions used raw column wording ("Highlight total out as the campaign hook", "led by inflow share payroll (avg 0.08)")
    - Use the shared `labels.py` wording for every user-facing string from `RuleBasedNamer`, so persona cards, the export and the New Promo breakdown read the same; keep names unique within a set and deterministic
    - Write the failing tests FIRST: for every known joined column, no raw column name (underscored or with spaces, for example "total out", "inflow share payroll") appears in any name, description or action; uniqueness and determinism unchanged; update ONLY expectations that changed, listing each
    - _Requirements: 4.4, 4.5, 4.6, 4.9, 4.11_
  - [x] 13.4 Compute expected joiners by persona for the New Promo cards (`src/webapp_core/personas.py`)
    - Pure function, no Streamlit: inputs are the New Promo `RunResult` cards and `sendable_by_segment`, the persona run's labels and each persona's actions; one breakdown per card
    - Rows keyed by `(group, persona)` with leads, lead share, expected joiners (sum of `p_join`) and rate, ordered by expected joiners then name; unlabeled leads go to "Not in this persona run"; personas under 5% of the card's leads OR under 5 leads fold into "Other personas" (lead count only); the total equals the card's `expected_joiners`
    - Per shown row, the persona's first action that is not the generic channel fallback; a short generic line when it repeats a higher row's action on the same card
    - Takeaway: with at least two shown personas and best rate at least 1.2x the lowest, "<Persona> is a% of leads but j% of expected joiners. Lead with its hook."; otherwise "Personas respond about equally; one message fits this card."
    - Write the failing tests FIRST (sum equals card joiners incl. folded and unlabeled leads, both fold rules, ordering, action dedup and channel-line skip, takeaway both branches and the 1.2 boundary, same persona name in two groups not merged, inputs not mutated, determinism); keep `persona_mix_by_cell` and its tests unchanged
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8_
  - [x] 14.16 Show the breakdown on the New Promo cards and remove the past-promo mix (`app/persona_page.py`)
    - After a persona run, render the current New Promo run's cards read-only with the 13.4 breakdown (column "Expected joiners") and the takeaway; with no New Promo run show "Run a New Promo first to see expected joiners by persona."
    - Remove the "Decision Cards With Persona Mix" section built on `outputs/cards.json`; the group selector no longer scopes card output
    - Tests: pure render helpers unit-tested; extend the AppTest smoke test for the no-run message and for the breakdown after a New Promo run placed in session state; update ONLY the expectations that changed, listing each
    - _Requirements: 3.17, 7.1, 7.2, 7.6, 7.8, 7.9_
  - [x] 13.5 Scope the breakdown to one group and add the per-group summary (`src/webapp_core/personas.py`)
    - Pure functions, no Streamlit: a group-scoped breakdown per card (the card's Sendable_Leads whose label is in that group; total = the group's expected joiners; the card's overall expected joiners carried for the note; empty cards dropped; an all-folded card flagged for the one-line message), and an "All groups" summary per card (one row per group with leads, share and expected joiners; a no-group row only when non-empty; total equals the card)
    - Expose the takeaway persona (or none) so the page can show only its action; keep `expected_joiners_by_persona` and `persona_mix_by_cell` behaviour and tests unchanged
    - Write the failing tests FIRST (group totals sum to the card total across groups, only the selected group's personas appear, empty cards dropped, all-folded flag, no-group row only when non-empty, takeaway persona, inputs not mutated, determinism)
    - _Requirements: 7.1, 7.3, 7.5, 7.6a, 7.6b, 7.6c, 7.7_
  - [x] 14.17 Offer one way to group: two levels plus the split control (`app/persona_page.py`)
    - Level selector offers only "All leads" and "By campaign"; backend `business-segment` level, CLI and their tests unchanged
    - Split control above the Attribute_Picker, at both levels, listing `split_columns` (categorical, 2-12 distinct values, no `client_id`, no constant columns, no numerics) with a short caption naming what is offered and each left-out categorical column with its reason
    - Chosen split columns removed from the Attribute_Picker options and defaults, with a short caption; too-small groups keep the existing message
    - Write the failing pure-function tests FIRST (split columns on real-shaped data, reasons, the 12-value cutoff, picker filtering incl. defaults); run "By campaign" with a split once on real data and report what happens
    - _Requirements: 3.4, 3.5, 3.8, 3.10, 3.22, 3.23_
  - [x] 14.18 Render the group-scoped, compact breakdown (`app/persona_page.py`)
    - Single group: that group's personas only, total for the group and the note "This card's Joiners across all groups: X (group is Y of it)."; "All groups": the visible instruction "Pick a group above to see the persona detail." and one row per group per card
    - Default columns Persona, Leads (share), Expected joiners and the takeaway; rates in a collapsed "Details"; the takeaway persona's action (or the equal-response line) in a collapsed "How to message this"; hide empty cards; one-line message for all-folded cards; "Not in this persona run" only when non-empty; Part 4 fields unchanged
    - Tests: pure render helpers first; AppTest smoke test updated (level options, split by customer segment replacing the old level test, split at "By campaign", single-group and All-groups views); list every changed expectation
    - _Requirements: 3.17, 7.6a, 7.6b, 7.6c, 7.8_

- [x] 15. Shared test strategies and end-to-end verification
  - [x] 15.1 Add shared hypothesis strategies in `tests/strategies_part5_personas.py`
    - Provide generators for joined attribute sets, run specs, and lead pools shared by the property tests; rely on `tests/conftest.py` for `sys.path` (never hardcode it)
    - _Requirements: 2.1, 4.1, 8.1_
  - [x] 15.2 Write the integration test in `tests/test_part5_personas_integration.py`
    - Run an end-to-end persona run over the sample `data/` + `outputs/` producing a labeled-leads CSV and per-cell mixes; confirm `run_pipeline.py` behavior and `outputs/` byte-identity are unaffected by the presence of `src/part5_personas`
    - _Requirements: 9.2, 9.3, 9.4_
  - [x] 15.3 Run `pytest` and confirm the existing pipeline is unchanged
    - Run the full `pytest` suite; confirm all persona tests pass and that the existing stages still produce byte-identical `outputs/` artifacts
    - _Requirements: 9.2, 9.3_

- [x] 16. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All test tasks are required except the optional Persona_Brief task 14.4 and its test, which may be skipped if time is short.
- Each task references specific requirements for traceability, and property-test tasks name the correctness property they verify.
- The Streamlit page uses only Streamlit built-ins (`st.dataframe` for the "How the Personas Differ" table); the earlier bar chart and Elbow_Plot were removed from the page (tasks 14.5, 14.6), keeping `kmodes` the only new dependency.
- No module under the existing `run_pipeline.py` stages is modified, and `src/part5_personas` is never added to the stage sequence.
- Checkpoints ensure incremental validation at the end of the pure pipeline, after the CLI, and at the end.

## Task Dependency Graph

Order reflects what actually ran. Tasks 14.3 and 14.4 were deliberately deferred (left unstarted) and sit in the last wave; they do not block 15.3.

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
    { "id": 11, "tasks": ["7.2b", "14.1b"] },
    { "id": 12, "tasks": ["8.1c"] },
    { "id": 13, "tasks": ["8.1d", "14.5"] },
    { "id": 14, "tasks": ["14.6"] },
    { "id": 15, "tasks": ["14.7"] },
    { "id": 16, "tasks": ["14.8"] },
    { "id": 17, "tasks": ["15.2"] },
    { "id": 18, "tasks": ["5.5"] },
    { "id": 19, "tasks": ["4.4"] },
    { "id": 20, "tasks": ["14.9"] },
    { "id": 21, "tasks": ["15.3"] },
    { "id": 22, "tasks": ["4.5"] },
    { "id": 23, "tasks": ["4.6"] },
    { "id": 24, "tasks": ["8.1e"] },
    { "id": 25, "tasks": ["8.1f", "14.10"] },
    { "id": 26, "tasks": ["14.11"] },
    { "id": 27, "tasks": ["9.3"] },
    { "id": 28, "tasks": ["14.12"] },
    { "id": 29, "tasks": ["4.7"] },
    { "id": 30, "tasks": ["8.1g"] },
    { "id": 31, "tasks": ["14.13"] },
    { "id": 32, "tasks": ["14.14"] },
    { "id": 33, "tasks": ["14.15"] },
    { "id": 34, "tasks": ["8.1h", "13.4"] },
    { "id": 35, "tasks": ["14.16"] },
    { "id": 36, "tasks": ["13.5", "14.17"] },
    { "id": 37, "tasks": ["14.18"] },
    { "id": 38, "tasks": ["14.3", "14.4"] }
  ]
}
```
