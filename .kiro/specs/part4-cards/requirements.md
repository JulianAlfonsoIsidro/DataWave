# Requirements Document

## Introduction

Part 4 Cards is a Python (pandas) batch pipeline that turns the Part 3 per-lead segment output into per-(promo, segment) "action cards". For each lead it decides whether the lead is excluded (national do-not-contact list, over-contacted, or unreachable on any allowed channel), picks the single best contact channel, and splits the reachable leads of each cell into a reproducible 10% control holdout and the remaining sendable leads. For each (promo, segment) cell it then builds one card carrying client counts, exclusion and control breakdowns, expected joiners with a 90% range, the dominant channel, total channel cost, expected value, the top drivers, a recommended action, and a fixed message angle.

The pipeline consumes the Part 3 segments and summary files plus six reference files, and produces three outputs: a cards JSON file listing one card per (promo, segment), one sendable-lead CSV per cell under `outputs/leads/`, and a summary table printed to standard output. All logic is deterministic pandas; the only randomness is the control holdout, which is governed by a fixed seed so that runs are reproducible. The pipeline also exposes a callable `build_cards(segments_df, promo_dict)` that returns the cards in memory for an application to use, separate from the file-writing and printing entry point. Config constants (the peso value of a join, the control seed, and the per-segment message angles) are stated as labelled assumptions.

## Glossary

- **Part4_Cards_Pipeline**: The system under specification. A Python package at `src/part4_cards`, invoked as `python -m part4_cards.main` with `PYTHONPATH=src`, that loads the inputs, builds the cards, writes the output files, and prints the summary table.
- **Input_Loader**: The component of the Part4_Cards_Pipeline responsible for loading and validating the input files.
- **Lead_Classifier**: The component of the Part4_Cards_Pipeline responsible for per-lead exclusion, best_channel selection, and the control-versus-sendable split.
- **Card_Builder**: The component of the Part4_Cards_Pipeline responsible for aggregating leads into per-(promo, segment) cards and for exposing the callable `build_cards` function.
- **Reporter**: The component of the Part4_Cards_Pipeline responsible for writing the output files, printing the summary table, and owning the command-line entry point.
- **Segments_File**: The input CSV at `outputs/segments.csv` with columns `promo_id`, `client_id`, `p_join`, `capacity_php`, `segment`, `top_driver_1`, `top_driver_2`, `top_driver_3`.
- **Segment_Summary_File**: The input CSV at `outputs/segment_summary.csv`, the Part 3 per-cell summary.
- **Ndb_File**: The input CSV at `data/ndb.csv`, the national do-not-contact list, keyed by `client_id`.
- **Contact_History_File**: The input CSV at `data/contact_history.csv`, per-client contact events, used to compute the average number of contacts per month per client.
- **Channel_Costs_File**: The input CSV at `data/channel_costs.csv` giving the cost per send for each channel.
- **Customer_Dna_File**: The input CSV at `data/customer_dna.csv` with columns including `client_id`, `digital_app_user`, `email_valid`, and `mobile_valid`.
- **Promo_History_File**: The input CSV at `data/promo_history.csv` with columns including `promo_id`, `channels`, `mechanic`, and `threshold_php`.
- **Cards_File**: The output JSON file at `outputs/cards.json`, a list of cards, one per (promo, segment).
- **Leads_Dir**: The output directory `outputs/leads/` holding one sendable-lead CSV per (promo, segment) cell.
- **Lead**: One row of the Segments_File, identified by the pair (`promo_id`, `client_id`).
- **Cell**: The set of Leads sharing the same (`promo_id`, `segment`).
- **Allowed_Channels**: For a promo, the set of channels parsed from the `channels` column of the Promo_History_File for that `promo_id`.
- **Avg_Contacts_Per_Month**: For a client, the client's total count of contact events in the Contact_History_File divided by the number of distinct calendar months in which those events occurred.
- **Excluded_Lead**: A Lead removed from contact, carrying one Exclusion_Reason of "ndb", "over_contacted", or "no reachable channel".
- **Exclusion_Reason**: The recorded cause of a Lead's exclusion.
- **best_channel**: For a non-excluded Lead, the single channel selected by the deterministic priority order In-app, then Email, then SMS, gated by Allowed_Channels and the client's reachability flags.
- **Control_Lead**: A non-excluded Lead marked `control=1` by the control holdout.
- **Sendable_Lead**: A non-excluded Lead marked `control=0`.
- **Expected_Joiners**: For a Cell, the sum of `p_join` over the Cell's Sendable_Leads.
- **Joiners_90_Range**: For a Cell, the 90% range for Expected_Joiners computed by a binomial normal approximation over the Cell's Sendable_Leads.
- **Dominant_Channel**: For a Cell, the most common best_channel among the Cell's Sendable_Leads.
- **Total_Channel_Cost**: For a Cell, the sum over the Cell's Sendable_Leads of the per-send cost of each Lead's best_channel from the Channel_Costs_File.
- **Expected_Value**: For a Cell, Expected_Joiners multiplied by VALUE_PER_JOIN_PHP, minus Total_Channel_Cost.
- **Action**: For a Card, one of "Prioritize", "Include", "Offer lower tier", or "Skip".
- **Message_Angle**: For a Card, the fixed text mapped to the Card's segment by the message-angle mapping.
- **Card**: The aggregate record for one Cell written to the Cards_File.
- **VALUE_PER_JOIN_PHP**: A config constant, the peso value of one join, default 1000 (assumption).
- **Control_Seed**: A config constant, the fixed random seed governing the control holdout (assumption).

## Requirements

### Requirement 1: Load inputs, validate columns, and define config constants

**User Story:** As a data engineer, I want the pipeline to load its inputs, confirm the columns it depends on exist, and expose its tunable constants, so that card building operates on known, valid data.

#### Acceptance Criteria

1. WHEN the Part4_Cards_Pipeline starts, THE Input_Loader SHALL read, before any output file or directory is created, the Segments_File from `outputs/segments.csv`, the Segment_Summary_File from `outputs/segment_summary.csv`, the Ndb_File from `data/ndb.csv`, the Contact_History_File from `data/contact_history.csv`, the Channel_Costs_File from `data/channel_costs.csv`, the Customer_Dna_File from `data/customer_dna.csv`, and the Promo_History_File from `data/promo_history.csv`.
2. IF any of the seven required input files does not exist at its specified path, THEN THE Input_Loader SHALL halt the Part4_Cards_Pipeline before the Lead_Classifier runs, SHALL NOT create or write the Cards_File, the Leads_Dir, or any per-Cell lead CSV, and SHALL raise an error whose message contains the path of the first missing file detected.
3. IF, after all seven input files exist, the Segments_File is missing any of the columns `promo_id`, `client_id`, `p_join`, `segment`, or `top_driver_1`, or the Customer_Dna_File is missing any of the columns `client_id`, `digital_app_user`, `email_valid`, or `mobile_valid`, or the Promo_History_File is missing any of the columns `promo_id`, `channels`, or `mechanic`, or the Channel_Costs_File is missing its channel column or its cost column, THEN THE Input_Loader SHALL halt the Part4_Cards_Pipeline before the Lead_Classifier runs, SHALL NOT create or write the Cards_File, the Leads_Dir, or any per-Cell lead CSV, and SHALL raise an error whose message names each affected file together with every column missing from that file.
4. THE Part4_Cards_Pipeline SHALL define, each labelled in the code as an assumption, the config constant VALUE_PER_JOIN_PHP equal to the integer 1000 by default, the config constant Control_Seed as a single fixed integer literal that does not change between runs, and a message-angle mapping that assigns exactly one fixed text string to each segment, including the entry mapping segment "Untapped Wealth" to the exact text "Bring your savings home and keep your status".

### Requirement 2: Exclude leads on do-not-contact and over-contact rules

**User Story:** As a campaign manager, I want leads on the do-not-contact list or contacted too often removed with a recorded reason, so that the pipeline respects contact policy.

#### Acceptance Criteria

1. IF the Lead_Classifier processes a Lead whose `client_id` matches a `client_id` present in the Ndb_File, THEN THE Lead_Classifier SHALL mark that Lead as an Excluded_Lead with Exclusion_Reason "ndb" and SHALL NOT assign that Lead the Exclusion_Reason "over_contacted".
2. IF the Lead_Classifier processes a Lead whose `client_id` is absent from the Ndb_File and whose Avg_Contacts_Per_Month is strictly greater than 3 contacts per month, THEN THE Lead_Classifier SHALL mark that Lead as an Excluded_Lead with Exclusion_Reason "over_contacted".
3. WHEN the Lead_Classifier computes Avg_Contacts_Per_Month for a client that has at least one row in the Contact_History_File, THE Lead_Classifier SHALL divide the client's total count of Contact_History_File events by the number of distinct calendar months in which those events occurred.
4. WHERE a client in the Segments_File has no row in the Contact_History_File, THE Lead_Classifier SHALL treat that client's Avg_Contacts_Per_Month as 0, so that the client is not excluded with Exclusion_Reason "over_contacted".

### Requirement 3: Select best_channel gated by promo-allowed channels

**User Story:** As a campaign manager, I want each remaining lead assigned the single best reachable channel its promo allows, so that sends use an appropriate and permitted channel.

#### Acceptance Criteria

1. WHEN the Lead_Classifier processes a Lead that is not already an Excluded_Lead, THE Lead_Classifier SHALL evaluate candidate channels in the strict priority order In-app, then Email, then SMS, and SHALL set best_channel to the first channel whose conditions in criteria 2 through 4 are satisfied.
2. IF the Lead client's `digital_app_user` equals 1 and "In-app" is in the Lead promo's Allowed_Channels, THEN THE Lead_Classifier SHALL set best_channel to "In-app".
3. IF best_channel was not set to "In-app" and the Lead client's `email_valid` equals 1 and "Email" is in the Lead promo's Allowed_Channels, THEN THE Lead_Classifier SHALL set best_channel to "Email".
4. IF best_channel was not set to "In-app" or "Email" and the Lead client's `mobile_valid` equals 1 and "SMS" is in the Lead promo's Allowed_Channels, THEN THE Lead_Classifier SHALL set best_channel to "SMS".
5. IF a Lead that is not already an Excluded_Lead has no channel satisfying criteria 2 through 4, THEN THE Lead_Classifier SHALL mark that Lead as an Excluded_Lead with Exclusion_Reason "no reachable channel" and SHALL NOT set best_channel for that Lead.

### Requirement 4: Split reachable leads into control and sendable

**User Story:** As an analyst, I want a reproducible 10% control holdout per cell, so that campaign lift can be measured against an unsent group.

#### Acceptance Criteria

1. WHEN the Lead_Classifier splits a Cell, THE Lead_Classifier SHALL draw exactly floor(0.1 × the count of that Cell's non-excluded Leads) of those non-excluded Leads at random using the Control_Seed and mark each drawn Lead as a Control_Lead with `control=1`.
2. THE Lead_Classifier SHALL mark every non-excluded Lead of a Cell that is not a Control_Lead as a Sendable_Lead with `control=0`.
3. IF floor(0.1 × the count of a Cell's non-excluded Leads) equals 0, THEN THE Lead_Classifier SHALL assign zero Control_Leads for that Cell and mark all of that Cell's non-excluded Leads as Sendable_Leads with `control=0`.
4. THE Lead_Classifier SHALL NOT mark any Excluded_Lead as a Control_Lead or a Sendable_Lead.
5. WHEN the Lead_Classifier is run more than once on identical inputs with the same Control_Seed, THE Lead_Classifier SHALL assign the identical set of Leads to the control group on each run.

### Requirement 5: Build per-(promo, segment) cards and expose build_cards

**User Story:** As a campaign manager, I want one action card per promo and segment with counts, expected value, a recommended action, and a message angle, so that I can decide how to run each cell.

#### Acceptance Criteria

1. WHEN the Card_Builder builds a Card for a Cell, THE Card_Builder SHALL record the segment label, the number of clients in the Cell, the Excluded_Lead count broken down by Exclusion_Reason, the Control_Lead count, and the Sendable_Lead count.
2. WHEN the Card_Builder records the top drivers for a Cell, THE Card_Builder SHALL record the three most common `top_driver_1` values among the Cell's Leads ordered by descending count and then ascending value, recording fewer than three values when the Cell has fewer than three distinct `top_driver_1` values.
3. WHEN the Card_Builder sets the Dominant_Channel for a Cell with at least one Sendable_Lead, THE Card_Builder SHALL set Dominant_Channel to the most common best_channel among the Cell's Sendable_Leads, breaking ties by the priority order In-app, then Email, then SMS.
4. WHEN the Card_Builder computes join estimates for a Cell, THE Card_Builder SHALL set Expected_Joiners to the sum of `p_join` over the Cell's Sendable_Leads, SHALL set Total_Channel_Cost to the sum over the Cell's Sendable_Leads of the per-send cost of each Lead's best_channel, and SHALL set Expected_Value to Expected_Joiners multiplied by VALUE_PER_JOIN_PHP minus Total_Channel_Cost.
5. WHEN the Card_Builder computes the Joiners_90_Range for a Cell, THE Card_Builder SHALL treat each Sendable_Lead as an independent Bernoulli trial with success probability equal to its `p_join`, compute the mean as the sum of `p_join` and the variance as the sum of `p_join` multiplied by one minus `p_join` over the Cell's Sendable_Leads, and SHALL report the range as the mean minus 1.645 times the square root of the variance (clamped to a lower bound of 0) through the mean plus 1.645 times the square root of the variance.
6. IF a Cell has zero Sendable_Leads, THEN THE Card_Builder SHALL set Expected_Joiners to 0, both bounds of the Joiners_90_Range to 0, Total_Channel_Cost to 0, Expected_Value to 0, and Dominant_Channel to an empty value.
7. WHEN the Card_Builder assigns the Action for a Card, THE Card_Builder SHALL set Action to "Prioritize" when the segment is "Ready Toppers" and Expected_Value is greater than 0, otherwise to "Offer lower tier" when the Cell promo's `mechanic` equals "TOP_UP" and the segment is "Willing but Stretched" and Expected_Value is greater than 0, otherwise to "Include" when Expected_Value is greater than 0, and otherwise to "Skip".
8. WHEN the Card_Builder assigns the Message_Angle for a Card, THE Card_Builder SHALL set Message_Angle to the fixed text mapped to the Card's segment by the message-angle mapping, and THE Card_Builder SHALL expose a callable `build_cards(segments_df, promo_dict)` that returns the list of Cards in memory without writing any output file or printing.

### Requirement 6: Write outputs, print the summary, and provide the entry point

**User Story:** As an operator, I want to run the pipeline with one command and get the cards file, per-cell lead files, and a printed summary, so that I can review and hand off the campaign.

#### Acceptance Criteria

1. WHEN the Part4_Cards_Pipeline is invoked as `python -m part4_cards.main`, THE Reporter SHALL run the Input_Loader, the Lead_Classifier, and the Card_Builder in order, and only after all three complete without error SHALL write the outputs and print the summary table.
2. WHEN card building completes, THE Reporter SHALL write the Cards_File to `outputs/cards.json` as a list containing exactly one Card per (promo, segment) Cell, creating the `outputs` directory first if it does not exist.
3. WHEN card building completes, THE Reporter SHALL write one CSV per Cell to `outputs/leads/<promo_id>_<segment_slug>.csv`, where segment_slug is the Cell's segment label lowercased with every run of one or more non-alphanumeric characters replaced by a single underscore, creating the Leads_Dir first if it does not exist.
4. WHEN the Reporter writes a per-Cell lead CSV, THE Reporter SHALL write one row per Sendable_Lead of that Cell with columns `client_id`, `best_channel`, `p_join`, and `control`, where `control` is 0 for every row, and SHALL NOT write Control_Leads or Excluded_Leads to that file.
5. WHEN the Reporter prints the summary table, THE Reporter SHALL print one line per Card showing the `promo_id`, the segment, the number of clients, the Sendable_Lead count, Expected_Joiners, Expected_Value, and the Action.
6. IF the Input_Loader raises an error, THEN THE Reporter SHALL propagate that error and SHALL NOT create the `outputs` directory, write any output file, or print the summary table.
