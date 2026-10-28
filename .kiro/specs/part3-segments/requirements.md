# Requirements Document

## Introduction

Part 3 Segments is a Python (pandas) batch pipeline that assigns every promo lead produced by the scoring stage into one of four action segments arranged on a 2x2 matrix of propensity (score) against financial capacity, writes the per-lead assignment and a per-cell summary to disk, and prints the summary to standard output. A "lead" is one row of the scores file, keyed by the pair (`promo_id`, `client_id`).

Each lead's capacity is the client's most recent average daily balance plus the client's recent external outflow, compared against the lead's promo threshold to decide whether capacity is high. Each lead's score is high when its join probability is at or above the median join probability computed within the lead's own promo. Crossing these two binary dimensions yields four segments: "Ready Toppers" (high score, high capacity), "Willing but Stretched" (high score, low capacity), "Untapped Wealth" (low score, high capacity), and "Not Now" (low score, low capacity).

The pipeline consumes five inputs — the scored leads, the Part 2 network features, a monthly average-daily-balance history, the promo history, and the promo lead list — and produces two outputs: a per-lead segments file and a per-cell summary file. The promo lead list is used for validation only, to compute the actual observed join rate among treated leads in each cell. The summary enumerates every promo crossed with all four segments, so cells with zero clients still appear with zeroed or empty values. Determinism and reproducibility of the per-lead assignments and per-cell aggregates are the primary concerns; edge cases (missing clients in a source, ties at the median, promos absent from the promo history, cells with no treated leads) have explicitly defined handling.

## Glossary

- **Part3_Segments_Pipeline**: The system under specification. A Python module at `src/part3_segments` that loads the five inputs, assigns a segment to each lead, writes the two output files, and prints the summary.
- **Input_Loader**: The component of the Part3_Segments_Pipeline responsible for loading and validating the five input files.
- **Segmenter**: The component of the Part3_Segments_Pipeline responsible for computing per-lead capacity, score, and segment assignment.
- **Summary_Builder**: The component of the Part3_Segments_Pipeline responsible for building and writing the per-cell summary, including the treated-lead actual join rate.
- **Reporter**: The component of the Part3_Segments_Pipeline responsible for printing the summary to standard output and owning the command-line entry point.
- **Scores_File**: The input CSV at `outputs/scores.csv` with columns `promo_id`, `client_id`, `p_join`, `top_driver_1`, `top_driver_2`, `top_driver_3`.
- **Features_File**: The input CSV at `outputs/features_part2.csv` containing a `client_id` column and an `out_other_bank` column, among others; only those two columns are used.
- **Adb_Monthly_File**: The input CSV at `data/adb_monthly.csv` with columns `client_id`, `month` (format `YYYY-MM`), and `adb_php`.
- **Promo_History_File**: The input CSV at `data/promo_history.csv` containing at least the columns `promo_id` and `threshold_php`.
- **Promo_Leads_File**: The input CSV at `data/promo_leads.csv` with columns `promo_id`, `client_id`, `control_group`, `channel_sent`, `joined`, `join_date`; used for validation only.
- **Segments_File**: The output CSV at `outputs/segments.csv`, one row per Lead.
- **Segment_Summary_File**: The output CSV at `outputs/segment_summary.csv`, one row per (promo, segment) combination.
- **Lead**: One row of the Scores_File, identified by the pair (`promo_id`, `client_id`).
- **Latest_Adb**: For a client, the `adb_php` value from the row of the Adb_Monthly_File having the greatest `month` value (lexicographic maximum of the `YYYY-MM` strings) for that client.
- **Out_Other_Bank**: For a client, the `out_other_bank` value from the Features_File.
- **Capacity_Php**: For a Lead, Latest_Adb for the Lead's client plus Out_Other_Bank for the Lead's client.
- **Threshold_Php**: For a promo, the `threshold_php` value from the Promo_History_File for that `promo_id`.
- **Capacity_High**: For a Lead, true when Capacity_Php is greater than or equal to the Threshold_Php of the Lead's promo.
- **Promo_Median_PJoin**: For a promo, the median of `p_join` over the Leads of that promo in the Scores_File.
- **Score_High**: For a Lead, true when the Lead's `p_join` is greater than or equal to Promo_Median_PJoin for the Lead's promo.
- **Segment**: One of the four values "Ready Toppers", "Willing but Stretched", "Untapped Wealth", and "Not Now", determined by the pair (Score_High, Capacity_High).
- **Treated_Lead**: A row of the Promo_Leads_File whose `control_group` equals 0.
- **Expected_Joiners**: For a (promo, segment) cell, the sum of `p_join` over the Leads assigned to that cell.
- **Actual_Join_Rate**: For a (promo, segment) cell, the count of Treated_Leads joined to that cell on (`promo_id`, `client_id`) whose `joined` equals 1, divided by the count of Treated_Leads joined to that cell.

## Requirements

### Requirement 1: Load and validate the five input files

**User Story:** As a data engineer, I want the pipeline to load the five inputs and confirm the columns it depends on exist, so that segmentation operates on known, valid data.

#### Acceptance Criteria

1. WHEN the Part3_Segments_Pipeline starts, THE Input_Loader SHALL read the Scores_File from `outputs/scores.csv`, the Features_File from `outputs/features_part2.csv`, the Adb_Monthly_File from `data/adb_monthly.csv`, the Promo_History_File from `data/promo_history.csv`, and the Promo_Leads_File from `data/promo_leads.csv`.
2. IF any of the five input files does not exist at its specified path, THEN THE Input_Loader SHALL halt the Part3_Segments_Pipeline without producing any output file and raise an error that names the missing file path.
3. IF the Scores_File is missing any of the columns `promo_id`, `client_id`, `p_join`, `top_driver_1`, `top_driver_2`, or `top_driver_3`, or the Features_File is missing either of the columns `client_id` or `out_other_bank`, or the Adb_Monthly_File is missing any of the columns `client_id`, `month`, or `adb_php`, or the Promo_History_File is missing either of the columns `promo_id` or `threshold_php`, or the Promo_Leads_File is missing any of the columns `promo_id`, `client_id`, `control_group`, or `joined`, THEN THE Input_Loader SHALL halt the Part3_Segments_Pipeline without producing any output file and raise an error that names the affected file and each missing column.
4. WHEN the input files are read, THE Input_Loader SHALL parse `p_join` from the Scores_File, `out_other_bank` from the Features_File, `adb_php` from the Adb_Monthly_File, and `threshold_php` from the Promo_History_File as numeric values, and SHALL parse `month` from the Adb_Monthly_File as a string in the format `YYYY-MM`.
5. WHERE a client in the Scores_File has no row in the Adb_Monthly_File, THE Input_Loader SHALL treat that client's Latest_Adb as 0, and WHERE a client in the Scores_File has no row in the Features_File, THE Input_Loader SHALL treat that client's Out_Other_Bank as 0.
6. IF a `promo_id` present in the Scores_File has no row in the Promo_History_File, THEN THE Segmenter SHALL treat every Lead of that promo as having Capacity_High equal to false.

### Requirement 2: Assign capacity, score, and segment per lead

**User Story:** As an analyst, I want each lead placed on the 2x2 score-by-capacity matrix, so that I can target promo actions by segment.

#### Acceptance Criteria

1. WHEN the Segmenter processes a Lead, THE Segmenter SHALL compute Capacity_Php as the Lead client's Latest_Adb plus the Lead client's Out_Other_Bank, where Latest_Adb is taken from the row of the Adb_Monthly_File having the lexicographically greatest `month` value for that client.
2. WHEN the Segmenter evaluates capacity, THE Segmenter SHALL set Capacity_High to true for a Lead whose Capacity_Php is greater than or equal to the Threshold_Php of the Lead's promo, and to false otherwise.
3. WHEN the Segmenter evaluates score, THE Segmenter SHALL compute Promo_Median_PJoin as the median of `p_join` over the Leads of the same promo in the Scores_File, and SHALL set Score_High to true for a Lead whose `p_join` is greater than or equal to Promo_Median_PJoin and to false otherwise.
4. WHEN the Segmenter assigns a Segment, THE Segmenter SHALL set the Segment to "Ready Toppers" when Score_High and Capacity_High are both true, to "Willing but Stretched" when Score_High is true and Capacity_High is false, to "Untapped Wealth" when Score_High is false and Capacity_High is true, and to "Not Now" when Score_High and Capacity_High are both false.

### Requirement 3: Write the per-lead segments file

**User Story:** As a downstream consumer, I want one segment row per scored lead written to a stable path, so that I can join segment assignments reliably.

#### Acceptance Criteria

1. WHEN segment assignment completes, THE Segmenter SHALL write the Segments_File to `outputs/segments.csv` as a comma-separated file with a single header row whose columns are, in order, `promo_id`, `client_id`, `p_join`, `capacity_php`, `segment`, `top_driver_1`, `top_driver_2`, `top_driver_3`.
2. THE Segmenter SHALL write exactly one row in the Segments_File for each Lead in the Scores_File, carrying that Lead's `p_join`, computed Capacity_Php, assigned Segment, and the three `top_driver` values from the Scores_File.
3. IF the `outputs` directory does not exist, THEN THE Segmenter SHALL create the `outputs` directory before writing the Segments_File.

### Requirement 4: Build and write the per-cell segment summary

**User Story:** As an analyst, I want a per-cell summary of client counts, expected joiners, and the observed treated-lead join rate, so that I can compare predicted and actual uptake across the four segments of each promo.

#### Acceptance Criteria

1. WHEN the Summary_Builder builds the summary, THE Summary_Builder SHALL emit one row for every combination of a `promo_id` present in the Scores_File with each of the four Segment values "Ready Toppers", "Willing but Stretched", "Untapped Wealth", and "Not Now".
2. WHEN the Summary_Builder populates a (promo, segment) cell, THE Summary_Builder SHALL compute the number of clients as the count of Leads assigned to that cell, the mean `p_join` as the mean of `p_join` over the Leads assigned to that cell, and Expected_Joiners as the sum of `p_join` over the Leads assigned to that cell.
3. WHEN the Summary_Builder computes the actual join rate for a (promo, segment) cell, THE Summary_Builder SHALL use only Treated_Leads, which are Promo_Leads_File rows with `control_group` equal to 0, joined to the cell's Leads on the pair (`promo_id`, `client_id`), and SHALL compute Actual_Join_Rate as the fraction of those Treated_Leads whose `joined` equals 1.
4. IF a (promo, segment) cell has zero Treated_Leads joined to it, THEN THE Summary_Builder SHALL represent that cell's Actual_Join_Rate as an empty value.
5. WHERE a (promo, segment) cell contains at least one Lead, THE Summary_Builder SHALL record the most common `top_driver_1` value among that cell's Leads, and WHERE a (promo, segment) cell contains zero Leads, THE Summary_Builder SHALL record the number of clients as 0, the mean `p_join` as 0, Expected_Joiners as 0, an empty Actual_Join_Rate, and an empty most-common `top_driver_1`.
6. WHEN the summary is complete, THE Summary_Builder SHALL write the Segment_Summary_File to `outputs/segment_summary.csv` as a comma-separated file with a single header row, creating the `outputs` directory first if it does not exist.

### Requirement 5: Print the summary and provide the command-line entry point

**User Story:** As an operator, I want to run the whole pipeline with one command and see the summary printed, so that I can review segment results without opening a file.

#### Acceptance Criteria

1. WHEN the Part3_Segments_Pipeline is invoked as `python -m part3_segments.main`, THE Reporter SHALL run the Input_Loader, the Segmenter, and the Summary_Builder in order and then print the summary.
2. WHEN the Reporter prints the summary, THE Reporter SHALL print one line for every (promo, segment) cell written to the Segment_Summary_File, showing the `promo_id`, the Segment, the number of clients, the mean `p_join`, Expected_Joiners, the Actual_Join_Rate, and the most common `top_driver_1`.
3. WHERE a (promo, segment) cell has an empty Actual_Join_Rate or an empty most-common `top_driver_1`, THE Reporter SHALL print that field as 0 or as an empty field.
4. IF the Input_Loader raises an error, THEN THE Reporter SHALL propagate that error and SHALL NOT print a summary or write any output file.
