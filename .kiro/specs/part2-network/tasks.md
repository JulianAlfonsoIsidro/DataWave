# Implementation Plan: Part 2 Network

## Overview

Build the `src/part2_network` pandas pipeline incrementally and test-first. Start with project scaffolding and configuration, then the input-validating `Transaction_Reader`, then each `Feature_Builder` feature block (total out, external outflow, ratio, month count, inflow shares, spend shares), then output assembly and writing, then the `Validation_Reporter`, and finally wire everything through `main` and run end-to-end against the real data. Each feature block is paired with its Hypothesis property tests (Properties 1–18) and targeted example/edge tests so correctness is validated as the module grows.

## Tasks

- [x] 1. Set up project scaffolding, dependencies, and configuration
  - [x] 1.1 Populate dependencies and create the package skeleton
    - Write `pandas`, `pytest`, and `hypothesis` into the empty `requirements.txt`
    - Create `src/part2_network/__init__.py` and an empty `tests/` package with `tests/__init__.py`
    - Create empty module files `src/part2_network/reader.py`, `features.py`, `validation.py`, `main.py` to anchor imports
    - _Requirements: 1.1, 8.1, 9.1_

  - [x] 1.2 Implement `config.py` with the Config dataclass and domain constants
    - Define frozen `Config` dataclass with `transactions_path=Path("data/transactions.csv")`, `promo_leads_path=Path("data/promo_leads.csv")`, `output_path=Path("outputs/features_part2.csv")`
    - Define module constants: `REQUIRED_COLUMNS`, `EXTERNAL_COUNTERPARTY_TYPE="Other bank"`, `INFLOW_SOURCES`, `INFLOW_SHARE_COLUMNS`, `P001_PROMO_ID="P001"`, `TREATED_CONTROL_GROUP=0`
    - _Requirements: 1.1, 8.1, 9.1, 9.2_

- [x] 2. Implement the input-validating Transaction_Reader
  - [x] 2.1 Implement `reader.read(path)` with ordered validation and type coercion
    - Existence check raising `FileNotFoundError` naming the path; read with `dtype=str, keep_default_na=False`
    - Empty-frame check (`ValueError`, no records); missing-column check (`ValueError` listing every missing column)
    - Coerce `amount_php` via `to_numeric(errors="coerce")` and `txn_date` via `to_datetime(format="%Y-%m-%d", errors="coerce")`, raising `ValueError` naming the column and ≥1 offending `txn_id`/row index on failure
    - Enforce validation order so the first structural defect is reported; never write any output
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.2 Write property test for missing-column reporting
    - **Property 13: Missing required columns are reported exactly**
    - **Validates: Requirements 1.3**

  - [x] 2.3 Write property test for unparseable-value reporting
    - **Property 14: Unparseable values are reported with column and offending row**
    - **Validates: Requirements 1.4, 1.5**

  - [x] 2.4 Write example/edge unit tests for the reader
    - Opens the configured default path and parses a small valid frame to float/datetime dtypes (1.1, 1.4)
    - Missing file raises `FileNotFoundError` naming the path (1.2); header-only file raises the no-records error (1.6)
    - _Requirements: 1.1, 1.2, 1.4, 1.6_

- [x] 3. Build shared Feature_Builder helpers and test strategy
  - [x] 3.1 Implement feature-frame scaffolding in `features.py`
    - Derive `clients = sorted(txns.client_id.unique())`, add a `txn_month` column via `txn_date.dt.strftime("%Y-%m")`
    - Create `outflows`, `inflows`, and `ext_outflows` slices (excluding missing/non-"Other bank" counterparty types)
    - Provide a reindex-and-zero-fill helper used by every feature block to align onto the sorted client universe
    - _Requirements: 8.2, 8.5, 3.2_

  - [x] 3.2 Build the shared Hypothesis transactions strategy
    - Composite strategy generating valid frames: small client-id set, `direction` in {IN, OUT}, non-negative `amount_php`, `txn_date` from the three observed months, domain `counterparty_type`/`counterparty_category`
    - Include targeted variants forcing Property 6 / Property 8 preconditions and injecting missing/other counterparty types for Property 2
    - _Requirements: 2.1, 3.1, 6.5, 7.7_

- [x] 4. Implement outflow, external-outflow, ratio, and month-count features
  - [x] 4.1 Implement `total_out` and `out_other_bank`
    - `total_out`: sum of OUT `amount_php` per client, reindexed, `fillna(0)`, `round(2)`
    - `out_other_bank`: sum of External_Outflow `amount_php` per client, reindexed, `fillna(0)`, `round(2)`
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 4.2 Write property test for total outflow
    - **Property 1: Total outflow equals the sum of a client's OUT amounts**
    - **Validates: Requirements 2.1, 2.2, 2.3**

  - [x] 4.3 Write property test for outflow to other banks
    - **Property 2: Outflow to other banks equals the sum of a client's External_Outflow amounts**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

  - [x] 4.4 Implement `ext_outflow_ratio` and `months_with_ext_transfer`
    - `ext_outflow_ratio`: guarded `out_other_bank / total_out` (0 when `total_out == 0`), `round(4)`
    - `months_with_ext_transfer`: `ext_outflows.groupby(client).txn_month.nunique()`, reindexed, `fillna(0)`, cast to `int`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.5 Write property test for external outflow ratio bounds
    - **Property 3: External outflow ratio is a bounded fraction of total outflow**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [x] 4.6 Write property test for months-with-external-transfer count
    - **Property 4: Months with external transfer is a bounded distinct-month count**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4**

  - [x] 4.7 Write edge unit test for ratio rounding
    - `ext_outflow_ratio` respects 4-decimal rounding
    - _Requirements: 4.4_

- [x] 5. Implement inflow-share features
  - [x] 5.1 Implement the three inflow shares
    - Compute per-client inflow totals; per-source sums for {Payroll, Remittance, Business receipts} via `groupby`/`unstack(fill_value=0)`
    - Divide by full inflow total with `inflow_total == 0` rows forced to 0; reindex onto all three sources and all clients; `round(6)`
    - Emit `inflow_share_payroll`, `inflow_share_remittance`, `inflow_share_business_receipts`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

  - [x] 5.2 Write property test for inflow-share bounds and definition
    - **Property 5: Inflow shares are bounded source fractions of total inflow**
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [x] 5.3 Write property test for inflow shares summing to one
    - **Property 6: Inflow shares sum to one when all inflows are known sources**
    - **Validates: Requirements 6.5**

  - [x] 5.4 Write edge unit test for inflow-share rounding
    - Inflow shares respect 6-decimal rounding
    - _Requirements: 6.4_

- [x] 6. Implement dynamic spend-share features
  - [x] 6.1 Implement category-name normalization
    - `re.sub(r"[^0-9a-z]+", "_", value.lower()).strip("_")` producing lowercase `[a-z0-9_]` suffixes with no consecutive underscores
    - _Requirements: 7.3_

  - [x] 6.2 Write property test for normalization well-formedness
    - **Property 10: Category-name normalization is well-formed and deterministic**
    - **Validates: Requirements 7.3**

  - [x] 6.3 Implement spend shares with globally discovered columns
    - Discover `spend_categories` once from distinct OUT `counterparty_category` across all clients
    - `pivot_table` sum per client/category divided by `total_out` (rows with `total_out == 0` forced to 0); reindex onto `spend_categories` and clients; `round(6)`
    - Name each column `spend_share_` + normalized category; include the identical complete set in every row
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 6.4 Write property test for spend-share bounds and definition
    - **Property 7: Spending shares are bounded category fractions of total outflow**
    - **Validates: Requirements 7.1, 7.4, 7.5, 7.6**

  - [x] 6.5 Write property test for spend shares summing to one
    - **Property 8: Spending shares sum to one for clients with outflow**
    - **Validates: Requirements 7.7**

  - [x] 6.6 Write property test for spend-share column set
    - **Property 9: Spend-share columns match the global distinct outflow categories**
    - **Validates: Requirements 7.2**

- [x] 7. Assemble and write the Features_File
  - [x] 7.1 Implement feature-frame assembly in `features.build`
    - Concatenate all feature blocks in the fixed column order with `client_id` first, followed by dynamic `spend_share_*` columns
    - Guarantee exactly one row per distinct client, ordered by ascending `client_id`; zero-client input yields a header-only frame
    - _Requirements: 8.2, 8.3, 8.5, 8.6_

  - [x] 7.2 Implement `features.write(features, path)`
    - `path.parent.mkdir(parents=True, exist_ok=True)` then `to_csv(index=False)` with a single header row
    - _Requirements: 8.1, 8.4_

  - [x] 7.3 Write property test for one row per distinct client
    - **Property 11: Exactly one output row per distinct client**
    - **Validates: Requirements 8.2**

  - [x] 7.4 Write property test for ascending client_id ordering
    - **Property 12: Output rows are ordered by ascending client_id**
    - **Validates: Requirements 8.5**

  - [x] 7.5 Write example/edge unit tests for output shape and writing
    - Single header row (8.1), `client_id` first (8.3), the three named inflow-share columns present (6.6)
    - Missing `outputs/` directory created on write (8.4); zero distinct clients yields a header-only file (8.6)
    - _Requirements: 6.6, 8.1, 8.3, 8.4, 8.6_

- [x] 8. Checkpoint - Ensure all feature tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement the Validation_Reporter
  - [x] 9.1 Implement P001 treated-lead selection and inner join
    - Read `promo_leads.csv`; keep rows where `promo_id == "P001"` and `control_group == 0`
    - Inner-join selected leads to the features frame on `client_id`
    - When zero treated leads are selected, print a no-match message and return without quartile computation
    - _Requirements: 9.1, 9.2, 9.3, 9.9_

  - [x] 9.2 Write property test for treated-lead selection
    - **Property 15: Treated-lead selection is exactly the P001 control-group-0 rows**
    - **Validates: Requirements 9.2**

  - [x] 9.3 Implement quartile binning and join-rate reporting
    - Rank joined leads by ascending `ext_outflow_ratio`, tie-break by ascending `client_id`, split into Q1–Q4 with counts differing by at most one
    - Compute per-quartile `Join_Rate` (mean of `joined`) and the overall inner-join rate, each in [0, 1]
    - Print one line per quartile in order Q1–Q4 (label, count, rate) plus the overall join rate
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.8_

  - [x] 9.4 Write property test for quartile binning
    - **Property 16: Quartile binning is near-equal, order-respecting, and deterministically tie-broken**
    - **Validates: Requirements 9.4, 9.5**

  - [x] 9.5 Write property test for per-quartile join rate
    - **Property 17: Per-quartile join rate is a bounded mean of the joined flag**
    - **Validates: Requirements 9.6**

  - [x] 9.6 Write property test for overall inner-join rate
    - **Property 18: Overall inner-join rate is a bounded fraction**
    - **Validates: Requirements 9.8**

  - [x] 9.7 Write example/edge unit tests for the reporter
    - Reads the configured leads path (9.1), inner-joins a mix of matching/non-matching client ids (9.3), prints exactly four lines Q1–Q4 with label, count, rate (9.7)
    - Zero P001 treated leads prints the no-match message and performs no quartile computation (9.9)
    - _Requirements: 9.1, 9.3, 9.7, 9.9_

- [x] 10. Wire the pipeline together in main and run end-to-end
  - [x] 10.1 Implement `main.main(argv)` with CLI wiring
    - Parse `--transactions`, `--promo-leads`, `--out` overrides into a `Config`
    - Call `reader.read`, `features.build` + `features.write`, then `validation.report` in order; propagate reader errors as a non-zero exit before any output
    - _Requirements: 1.1, 8.1, 9.1_

  - [x] 10.2 Write integration/smoke test against the real data
    - Run end-to-end against `data/transactions.csv` and `data/promo_leads.csv`; assert `outputs/features_part2.csv` is written with 2000 client rows, the fixed columns plus dynamic `spend_share_*` columns, and the four-quartile report plus overall join rate print
    - _Requirements: 1.1, 8.1, 8.2, 9.3, 9.7, 9.8_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; they are the unit, edge, property, and integration tests.
- Each task references the specific requirement sub-clauses and/or design properties it implements for traceability.
- Property tests use Hypothesis (`@settings(max_examples=100)` or higher) and are tagged `# Feature: part2-network, Property {number}: {property_text}`; reduction properties (1, 2, 4, 7) assert against an independent reference computation.
- Checkpoints ensure incremental validation before moving to the next component.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "3.2", "4.1", "5.1", "6.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "5.2", "5.3", "5.4", "6.2", "6.3"] },
    { "id": 5, "tasks": ["4.5", "4.6", "4.7", "6.4", "6.5", "6.6", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "7.4"] },
    { "id": 7, "tasks": ["7.5", "9.1"] },
    { "id": 8, "tasks": ["9.2", "9.3"] },
    { "id": 9, "tasks": ["9.4", "9.5", "9.6", "9.7", "10.1"] },
    { "id": 10, "tasks": ["10.2"] }
  ]
}
```
