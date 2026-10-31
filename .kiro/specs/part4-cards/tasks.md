# Implementation Plan: Part 4 Cards

## Overview

Build the `src/part4_cards` pandas pipeline incrementally and test-first, in Python (the design uses concrete Python/pandas, so no language selection is needed). Start with project scaffolding and configuration, then the input-validating `Input_Loader`, then the `Lead_Classifier` (average contacts per month and the exclusion cascade, best_channel selection, and the seeded per-cell control split), then the `Card_Builder` (per-cell counts and breakdowns, top drivers and dominant channel, expected joiners / cost / value with a 90% range, the action rule, the message angle, and the public `build_cards` wrapper), and finally wire everything through `main` with the output writers, the summary print, and an end-to-end run against the real data. Each logic block is paired with its Hypothesis property test (Properties 1–6, six total) and light example/edge tests so correctness is validated as the module grows. Tests live under `tests/` as `test_part4_*.py` and run with `PYTHONPATH=src` using the project virtualenv.

## Tasks

- [x] 1. Set up package scaffolding and configuration
  - [x] 1.1 Create the package skeleton
    - Create `src/part4_cards/__init__.py` and empty module files `loader.py`, `classify.py`, `cards.py`, `main.py` to anchor imports
    - Confirm `pandas`, `numpy`, `pytest`, and `hypothesis` are present in `requirements.txt` (add any that are missing)
    - _Requirements: 1.1_

  - [x] 1.2 Implement `config.py` with the Config dataclass and domain constants
    - Define a frozen `Config` dataclass with the input paths `segments_path=outputs/segments.csv`, `segment_summary_path=outputs/segment_summary.csv`, `ndb_path=data/ndb.csv`, `contact_history_path=data/contact_history.csv`, `channel_costs_path=data/channel_costs.csv`, `customer_dna_path=data/customer_dna.csv`, `promo_history_path=data/promo_history.csv` and the output paths `cards_out_path=outputs/cards.json`, `leads_out_dir=outputs/leads/`
    - Define the labelled-assumption constants `VALUE_PER_JOIN_PHP=1000`, `CONTROL_SEED=42`, `CONTROL_FRACTION=0.10`, `Z_90=1.645`, `CHANNEL_PRIORITY`, `SEGMENTS` (the four labels), `MESSAGE_ANGLES` (including `"Untapped Wealth"` → exact text `"Bring your savings home and keep your status"`), and `CHANNEL_FLAG`
    - Define the required-column constants `SEGMENTS_REQUIRED`, `CUSTOMER_DNA_REQUIRED`, `PROMO_HISTORY_REQUIRED`, `CHANNEL_COSTS_REQUIRED`, `NDB_REQUIRED`, `CONTACT_HISTORY_REQUIRED`
    - _Requirements: 1.1, 1.4, 6.1_

- [x] 2. Implement the input-validating Input_Loader
  - [x] 2.1 Implement `loader.load(cfg)` with ordered validation and type coercion
    - Existence pass over the seven configured paths in fixed order, raising `FileNotFoundError` naming the first missing path before anything is read
    - Read each file with `pd.read_csv(path, dtype=str, keep_default_na=False)`; then a columns pass validating each file against its required-column constant and raising a single `ValueError` naming each affected file with every column missing from it (the Segment_Summary_File has no column check)
    - Coerce `p_join` → float, the three DNA flags `digital_app_user`/`email_valid`/`mobile_valid` → int, and `cost_php_per_message` → float; keep `contact_date` as a `YYYY-MM-DD` string; return a dict of frames keyed `segments`, `segment_summary`, `ndb`, `contact_history`, `channel_costs`, `customer_dna`, `promo_history`; never write any output
    - _Requirements: 1.1, 1.2, 1.3, 6.6_

  - [x] 2.2 Write example/edge unit tests for the loader
    - Missing file raises `FileNotFoundError` naming the first missing path, parametrized across each of the seven inputs, with `outputs/` untouched (1.2)
    - Missing required column raises `ValueError` naming the file and every missing column, covering segments, customer_dna, promo_history, and channel_costs (1.3)
    - A small valid set coerces `p_join`, the three DNA flags, and `cost_php_per_message` and keeps `contact_date` as a `YYYY-MM-DD` string (1.1, 6.6)
    - _Requirements: 1.1, 1.2, 1.3, 6.6_

- [x] 3. Build the Lead_Classifier: exclusion, best_channel, and the control split
  - [x] 3.1 Implement Avg_Contacts_Per_Month and the exclusion cascade in `classify.py`
    - Derive a `YYYY-MM` month from each `contact_date`; per `client_id` compute `avg = total event count / number of distinct YYYY-MM months`; left-join onto Leads and treat clients with no contact rows as `0`
    - Apply the ordered cascade first-match-wins: `client_id` ∈ NDB set → excluded `"ndb"` (evaluated first so NDB clients never get `"over_contacted"`); else `Avg_Contacts_Per_Month > 3` → excluded `"over_contacted"`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Write property test for the exclusion cascade
    - **Property 1: Exclusion is exactly the ordered cascade, NDB taking precedence over over-contact**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4**

  - [x] 3.3 Implement best_channel selection gated by promo and reachability
    - For a not-yet-excluded Lead, walk `CHANNEL_PRIORITY` In-app → Email → SMS and set `best_channel` to the first channel both present in the promo's `Allowed_Channels` and reachable by the client's `CHANNEL_FLAG` flag (`digital_app_user`/`email_valid`/`mobile_valid`)
    - If no channel qualifies, mark the Lead excluded `"no reachable channel"` and leave `best_channel` empty
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.4 Write property test for best_channel selection
    - **Property 2: best_channel is the first allowed-and-reachable channel in priority order, else the Lead is excluded unreachable**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

  - [x] 3.5 Implement the seeded per-cell control split
    - Per Cell (`promo_id`, `segment`), take the non-excluded Leads sorted by `client_id` and draw `k = floor(CONTROL_FRACTION × count)` with a NumPy `Generator` seeded from a stable combination of `(CONTROL_SEED, promo_id, segment)`; drawn Leads get `control=1`
    - Mark every other non-excluded Lead `control=0` (Sendable); excluded Leads are never control or sendable; when `k == 0` every non-excluded Lead is sendable; the per-cell seeding makes the control set identical on re-run with the same seed
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 3.6 Write property test for the control holdout
    - **Property 3: The control holdout is a reproducible floor-10% subset of the non-excluded Leads**
    - **Validates: Requirements 4.1, 4.3, 4.5**

- [x] 4. Checkpoint - Ensure Lead_Classifier tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Build the Card_Builder
  - [x] 5.1 Implement per-cell counts, breakdowns, top drivers, and dominant channel
    - Per Cell record `segment`, `n_clients`, `excluded_by_reason` (dict reason → count), `control_count`, and `sendable_count`
    - Compute `top_drivers` as the three most common `top_driver_1` values ordered by descending count then ascending value (fewer than three when fewer distinct values); compute `dominant_channel` as the most common Sendable `best_channel` with ties broken by `CHANNEL_PRIORITY`, empty when no Sendable_Leads
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Write property test for the per-cell partition
    - **Property 4: Each Cell's Leads partition into excluded, control, and sendable**
    - **Validates: Requirements 5.1, 4.2, 4.4**

  - [x] 5.3 Implement expected joiners, channel cost, expected value, and the 90% range
    - Set `expected_joiners` = Σ `p_join` over Sendable_Leads, `total_channel_cost` = Σ `cost_map[best_channel]` over Sendable_Leads, and `expected_value` = `expected_joiners × VALUE_PER_JOIN_PHP − total_channel_cost`
    - Compute the 90% range by binomial normal approximation (`mean = Σ p_join`, `var = Σ p_join·(1−p_join)`, range `mean ± Z_90·√var` with `low` clamped to a lower bound of 0); a Cell with zero Sendable_Leads gets `expected_joiners`, both range bounds, `total_channel_cost`, and `expected_value` all 0
    - _Requirements: 5.4, 5.5, 5.6_

  - [x] 5.4 Write property test for the per-cell reductions and range
    - **Property 5: Expected joiners, channel cost, expected value, and the 90% range are the defined reductions over Sendable Leads**
    - **Validates: Requirements 5.4, 5.5, 5.6**

  - [x] 5.5 Implement the action rule, message angle, and the public build_cards wrapper
    - Set `action` to `"Prioritize"` when segment is `"Ready Toppers"` and `EV > 0`, else `"Offer lower tier"` when the promo `mechanic == "TOP_UP"` and segment is `"Willing but Stretched"` and `EV > 0`, else `"Include"` when `EV > 0`, else `"Skip"`; set `message_angle = MESSAGE_ANGLES[segment]`
    - Expose the public `build_cards(segments_df, promo_dict)` convenience wrapper that loads the reference frames, runs the classifier internally, and returns the list of Cards in memory without writing any file or printing
    - _Requirements: 5.7, 5.8_

  - [x] 5.6 Write property test for the action rule
    - **Property 6: Action follows the four-way decision rule exactly**
    - **Validates: Requirements 5.7**

  - [x] 5.7 Write example/edge unit tests for message angle and build_cards
    - `message_angle` maps each segment to its fixed text, including `"Untapped Wealth"` → `"Bring your savings home and keep your status"` (5.8)
    - `build_cards(segments_df, promo_dict)` returns a list of Cards in memory and writes no file and prints nothing (5.8)
    - _Requirements: 5.8_

- [x] 6. Wire the pipeline together in main and write the outputs
  - [x] 6.1 Implement `main.main(argv)` with CLI wiring, output writers, and summary print
    - Parse CLI path overrides into a `Config`; run `loader.load` → `classify.classify` → Card_Builder build in order, and only after all three complete without error produce output
    - Write `outputs/cards.json` as a list with exactly one Card per Cell (creating `outputs/` first); write one `outputs/leads/<promo_id>_<segment_slug>.csv` per Cell (creating `outputs/leads/` first), where `segment_slug` is the segment lowercased with runs of non-alphanumeric characters collapsed to a single underscore, columns `client_id,best_channel,p_join,control`, one row per Sendable_Lead, `control` always 0, no control/excluded rows
    - Print one summary line per Card with `promo_id`, `segment`, `n_clients`, `sendable_count`, `expected_joiners`, `expected_value`, and `action`; propagate a loader error before any output dir/file is created or anything is printed; end with the `if __name__ == "__main__"` guard for `python -m part4_cards.main`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.2 Write example unit tests for the Reporter and error propagation
    - `cards.json` has exactly one Card per Cell (6.2); per-Cell lead filenames use the slug (6.3); each per-Cell CSV has columns `client_id,best_channel,p_join,control`, sendable-only, with `control` always 0 (6.4); summary prints one line per Card with the seven fields (6.5)
    - A loader error makes `main` create no `outputs/`, write nothing, and print no summary (6.6)
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 6.3 Write integration/smoke test against the real data
    - Run `python -m part4_cards.main` end-to-end against the real seven inputs directing output to a gitignored scratch/tmp location; assert `cards.json` has exactly one Card per (promo, segment) Cell, one per-Cell lead file exists per Cell under `leads/`, and the summary prints
    - _Requirements: 6.1_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are the unit, edge, property, and integration tests.
- There are exactly six Hypothesis property tests (Properties 1–6), honoring the MAX 6 cap. The loader-validation checks (1.2, 1.3), the top-drivers and dominant-channel aggregations (5.2, 5.3), the message-angle/`build_cards` API (5.8), and the slug/output-shape criteria (6.2–6.5) are covered as example, edge, or integration tests rather than properties.
- Property tests use Hypothesis (`@settings(max_examples=100)` or higher) and are tagged `# Feature: part4-cards, Property {number}: {property_text}`; reduction properties (5, and the partition in 4) assert against an independent reference computation, and Property 3 asserts reproducibility by classifying identical inputs twice.
- Shared Hypothesis generators go in `tests/strategies_part4.py` following the existing part1/part2/part3 convention.
- Any temporary/debug output during implementation goes to a gitignored `scratch/` folder, never the repo root; `.gitignore` already ignores `outputs/` (add `scratch/` if not already ignored).
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
    { "id": 5, "tasks": ["3.4", "3.5"] },
    { "id": 6, "tasks": ["3.6", "5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3"] },
    { "id": 8, "tasks": ["5.4", "5.5"] },
    { "id": 9, "tasks": ["5.6", "5.7", "6.1"] },
    { "id": 10, "tasks": ["6.2", "6.3"] }
  ]
}
```
