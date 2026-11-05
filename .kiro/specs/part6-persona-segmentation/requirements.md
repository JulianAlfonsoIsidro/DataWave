# Requirements Document

## Introduction

The persona-segmentation feature adds a persona layer on top of DataWave's existing decision cards. It clusters leads on lifestyle, demographic, and product-ownership attributes using k-prototypes (via the kmodes library) rather than k-means, because the clustering inputs mix numeric and categorical fields. A user selects which attributes to cluster on, runs k-prototypes, and views a set of named personas carrying profiles, sizes, and recommended actions. Personas can be generated for the whole lead list, for a chosen business segment, or for a single campaign.

The feature is delivered as a new pipeline-style package `src/part5_personas` (pure logic, no Streamlit imports), a `webapp_core`-style pure orchestration layer, and a new interactive Streamlit page/section in `app/`. It reuses the existing `outputs/` artifacts rather than recomputing upstream results and does not change `run_pipeline.py` behavior for existing steps; persona generation is an optional, separate step. The only new dependency is `kmodes`.

### Out of Scope (explicit)

- Changes to the Ask Assistant surface.
- Actual AWS Bedrock LLM integration (a clean replaceable interface is required, but the Bedrock implementation itself is excluded).
- The campaign-response dataset (tracked separately).
- Any change to the behavior of existing `run_pipeline.py` stages (Part 1 through Part 4).

### Open Design Questions (to resolve in design)

- **OPEN QUESTION (merged cards):** Whether the persona layer operates on combined/merged decision cards depends on whether the Part 4 cards module supports merging. If the cards module does not support merging, the persona layer attaches to the existing per-cell cards only. This is flagged for resolution during design (see Requirement 7).

## Glossary

- **Persona_Pipeline**: The new `src/part5_personas` package that performs persona clustering and profile generation. Pure logic with no Streamlit imports.
- **Persona_Core**: The `webapp_core`-style pure orchestration module that wires the Persona_Pipeline APIs into a single in-memory run for the Streamlit page, containing no Streamlit imports and no modelling beyond the Persona_Pipeline.
- **Persona_Page**: The new Streamlit page/section in `app/` that presents the attribute picker, clustering options, run control, persona summary cards, cluster comparison chart, and leads download.
- **Joined_Attribute_Set**: The per-client table formed by joining `customer_dna.csv`, the pivoted `product_ownership.csv`, and `outputs/features_part2.csv` on `client_id`.
- **Product_Ownership_Flags**: The per-client one-hot ownership columns (for example `owns_deposit`, `owns_investment`) produced by pivoting the long-format `product_ownership.csv`; treated as categorical features.
- **Attribute_Picker**: The Persona_Page control through which a user selects which attributes of the Joined_Attribute_Set to cluster on.
- **Clustering_Level**: The scope of a persona run, one of `all` (whole lead list), `business-segment` (a chosen business segment), or `campaign` (a single campaign).
- **Business_Segment_Field**: The selectable grouping level, one of the `customer_dna.segment` field (for example Affluent-Preferred, Mid-Market, Mass) or the Part 3 2x2 Segment_Label (Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now).
- **Segment_Label**: A Part 3 segment value, one of Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now.
- **Campaign_Lead_Pool**: The set of leads used for a `campaign`-level run, sourced either from the current webapp New Promo run's sendable leads in session state or from a past promo's leads in `promo_leads.csv` selected by `promo_id`.
- **Persona**: A single cluster output carrying a name, a one-line description, a size, a percentage of the clustered leads, a numeric and categorical profile, distinguishing attributes, and recommended actions.
- **Persona_Set**: The collection of Personas produced by one persona run at a given Clustering_Level; configurable per business segment rather than a single hard-coded global set.
- **Persona_Profile**: The computed statistics for one Persona: size, percentage of leads, numeric means and medians, top categories per categorical field, and the attributes that most distinguish the Persona from other Personas in the same Persona_Set.
- **Persona_Namer**: The component that produces a Persona's name, one-line description, and recommended actions from its Persona_Profile; rule-based initially, behind an interface that an LLM implementation can later replace.
- **Elbow_Plot**: The chart of k-prototypes clustering cost against candidate k values that helps the user choose k.
- **Persona_Labeled_Leads**: The downloadable leads CSV that includes a persona-label column in addition to the lead's richer joined attributes.
- **Grouping_Attributes**: The attributes a user selects to partition leads into groups before clustering; each distinct combination of Grouping_Attributes values defines one group.
- **Clustering_Attributes**: The attributes a user selects for k-prototypes to cluster on within each group; selected separately from the Grouping_Attributes.
- **Minimum_Group_Size**: The configurable minimum number of leads a group must have to be clustered; a group with fewer leads than this value is flagged "too small to cluster" and produces no Personas.
- **Persona_Mix**: The per-card distribution giving the share of a decision card cell's leads assigned to each Persona, with the shares across the Personas present in that cell summing to 100%.
- **Match_Rate**: The fraction of leads with a matching row in a given source (`customer_dna.csv`, the pivoted `product_ownership.csv`, or `outputs/features_part2.csv`); a configurable minimum Match_Rate threshold gates whether the run halts.
- **Random_Seed**: The fixed seed value (42) used for all stochastic operations so runs are reproducible.

## Requirements

### Requirement 1: Build the clustering input by joining and pivoting source data

**User Story:** As a marketing analyst, I want the clustering inputs assembled from the customer, product-ownership, and feature data, so that personas reflect demographics, product ownership, and behavior together.

#### Acceptance Criteria

1. WHEN a persona run is requested, THE Persona_Pipeline SHALL build the Joined_Attribute_Set by left-joining the pivoted `product_ownership.csv` and `outputs/features_part2.csv` onto `customer_dna.csv` on `client_id`, producing exactly one row per `client_id` in `customer_dna.csv`.
2. THE Persona_Pipeline SHALL pivot the long-format `product_ownership.csv` into one row per `client_id` with one Product_Ownership_Flag column per distinct `product_type`, where a client's flag is 1 WHERE the client has at least one row of that `product_type` and 0 otherwise.
3. THE Persona_Pipeline SHALL treat every Product_Ownership_Flag as a categorical feature taking exactly the two values 0 and 1.
4. WHERE a client is present in `customer_dna.csv` but absent from `product_ownership.csv`, THE Persona_Pipeline SHALL set all of that client's Product_Ownership_Flags to 0.
5. THE Persona_Pipeline SHALL source behavioral features exclusively from the existing `outputs/features_part2.csv` artifact and SHALL NOT recompute Part 2 features.
6. WHEN a persona run is requested, THE Persona_Pipeline SHALL compute and report the Match_Rate per source as the fraction of leads with a matching row in `customer_dna.csv`, in the pivoted `product_ownership.csv`, and in `outputs/features_part2.csv` respectively.
7. WHERE a lead has no matching row in a source, THE Persona_Pipeline SHALL impute the missing values for that lead according to the Requirement 2 imputation rules.
8. IF the Match_Rate for any source is zero or is below the configurable minimum Match_Rate threshold defined on the Config, THEN THE Persona_Pipeline SHALL halt before producing any output and emit an error naming the offending source and its Match_Rate.
9. THE Persona_Pipeline SHALL expose the minimum Match_Rate threshold as a configurable value on the Config.
10. IF any file named with the `_answer_key` marker is supplied as a clustering input, THEN THE Persona_Pipeline SHALL reject that file and halt before any output with an error that names the rejected file.

### Requirement 2: Cluster leads with k-prototypes

**User Story:** As a marketing analyst, I want leads clustered with a method built for mixed numeric and categorical data, so that both demographic categories and numeric behavior shape the personas.

#### Acceptance Criteria

1. THE Persona_Pipeline SHALL cluster the selected attributes using k-prototypes from the kmodes library.
2. THE Persona_Pipeline SHALL classify each selected column from the Joined_Attribute_Set schema as numeric WHERE its declared schema type is an integer or floating-point type, and as categorical otherwise.
3. WHERE a user overrides the auto-detected type of a column, THE Persona_Pipeline SHALL treat that column as the user-specified type.
4. THE Persona_Pipeline SHALL scale each numeric feature before clustering so that each numeric feature has zero mean and unit variance across the clustered leads.
5. WHEN the selected attributes contain missing values, THE Persona_Pipeline SHALL replace every missing numeric value with the mean of the non-missing values of that column and every missing categorical value with the most frequent non-missing value of that column before clustering, so that the clustered input contains zero missing values.
6. IF, after missing-value resolution, any selected column contains zero non-missing values, THEN THE Persona_Pipeline SHALL reject the run and report an error indicating the offending column, and SHALL produce no cluster assignments.
7. THE Persona_Pipeline SHALL pass the categorical column indices to k-prototypes so that categorical columns are matched by the categorical dissimilarity.
8. WHEN a user does not specify k, THE Persona_Pipeline SHALL use a default k of 3.
9. WHERE a user specifies an integer k from 2 through 6 inclusive, THE Persona_Pipeline SHALL accept the value and cluster into exactly k clusters.
10. IF a user specifies a value for k that is not an integer, or is an integer less than 2 or greater than 6, THEN THE Persona_Pipeline SHALL reject the value and report an error indicating that k must be an integer from 2 through 6 inclusive, and SHALL produce no cluster assignments.
11. THE Persona_Pipeline SHALL seed k-prototypes with the Random_Seed so that a run with identical inputs and identical options produces identical cluster assignments.
12. THE Persona_Pipeline SHALL compute an Elbow_Plot of clustering cost across each integer candidate k from 2 through 6 inclusive to support choosing k.

### Requirement 3: Select attributes and clustering level

**User Story:** As a marketing analyst, I want to choose which attributes and which scope to cluster on, so that I can produce personas tuned to a specific audience.

#### Acceptance Criteria

1. THE Persona_Page SHALL present an Attribute_Picker whose options are drawn from the columns of the Joined_Attribute_Set, including demographic fields, lifestyle fields, Product_Ownership_Flags, and spend and inflow behavioral features.
2. WHEN a user runs a persona generation, THE Persona_Pipeline SHALL cluster only on the attributes selected in the Attribute_Picker.
3. IF a user requests a persona run with fewer than one attribute selected, THEN THE Persona_Page SHALL reject the run, retain the current attribute and Clustering_Level selections, and display an error message indicating that at least one attribute is required.
4. THE Persona_Page SHALL let the user choose exactly one Clustering_Level from the set `all`, `business-segment`, or `campaign`, defaulting to `all` when the user has made no selection.
5. WHERE the Clustering_Level is `business-segment`, THE Persona_Page SHALL let the user choose the Business_Segment_Field as either the `customer_dna.segment` field or the Part 3 Segment_Label.
6. WHERE the Clustering_Level is `business-segment`, THE Persona_Pipeline SHALL produce one Persona_Set per distinct Business_Segment_Field value present in the audience rather than a single global Persona_Set.
7. IF the Clustering_Level is `business-segment` and the selected Business_Segment_Field contains no non-null values across the audience, THEN THE Persona_Pipeline SHALL reject the run and display an error message indicating that the chosen business segment field has no usable values.
8. WHERE the user requests a two-step flow, THE Persona_Page SHALL collect three choices in order: first the Grouping_Attributes that partition leads into groups, then the Clustering_Attributes that k-prototypes clusters on within each group, and then the number of Personas k generated per group, presenting the Grouping_Attributes selection and the Clustering_Attributes selection as separate controls.
9. WHERE the user requests a two-step flow, THE Persona_Pipeline SHALL first partition leads into groups by the chosen Grouping_Attributes and THEN cluster each resulting group on the chosen Clustering_Attributes into Personas.
10. WHERE a group's lead count is below the Minimum_Group_Size defined on the Config, THE Persona_Pipeline SHALL flag that group as "too small to cluster" and SHALL produce no Personas for that group.
11. WHERE a group's lead count is at or above the Minimum_Group_Size but below the requested k, THE Persona_Pipeline SHALL cap k to that group's lead count for that group.
12. THE Persona_Pipeline SHALL expose the Minimum_Group_Size as a configurable value on the Config.

### Requirement 4: Generate persona profiles, names, descriptions, and actions

**User Story:** As a marketing analyst, I want each cluster turned into a named persona with a profile and recommended actions, so that I can act on the clusters without reading raw statistics.

#### Acceptance Criteria

1. THE Persona_Pipeline SHALL compute, per Persona, the Persona_Profile comprising its size as a non-negative integer count of leads, its percentage of the clustered leads as a value from 0.0 to 100.0 rounded to one decimal place, the mean and median of each numeric attribute, and the top 3 categories per categorical attribute.
2. WHERE a categorical attribute has fewer than 3 distinct categories in a Persona, THE Persona_Pipeline SHALL report all of that attribute's categories present in the Persona.
3. THE Persona_Pipeline SHALL compute, per Persona, the 3 attributes that most distinguish the Persona from the other Personas in the same Persona_Set, ranked by descending absolute deviation of the Persona's attribute value from the across-Persona mean of that attribute.
4. THE Persona_Namer SHALL produce, per Persona, a name and a one-line description derived from the Persona_Profile.
5. THE Persona_Namer SHALL produce, per Persona, between 2 and 3 recommended campaign actions derived from the Persona_Profile.
6. THE Persona_Namer SHALL produce its name, description, and actions through a rule-based implementation that, given an identical Persona_Profile, yields identical name, description, and actions.
7. IF a Persona has a size of zero, THEN THE Persona_Pipeline SHALL omit it from the Persona_Set rather than attempt to profile or name it.
8. THE Persona_Pipeline SHALL expose the Persona_Namer behind an interface that an AWS Bedrock LLM implementation can later substitute without changing the Persona_Pipeline callers.
9. THE Persona_Namer SHALL produce Persona names that are unique within a Persona_Set, such that no two Personas in the same Persona_Set share a name.

### Requirement 5: Generate personas per campaign

**User Story:** As a marketing analyst, I want personas built from a specific campaign's own leads, so that I can tailor messaging to that campaign's audience.

#### Acceptance Criteria

1. WHERE the Clustering_Level is `campaign`, THE Persona_Page SHALL let the user choose the Campaign_Lead_Pool as either the current New Promo run's sendable leads held in session state or a past promo's leads from `promo_leads.csv`.
2. IF the Campaign_Lead_Pool choice is the current New Promo run but no New Promo run exists in session state, THEN THE Persona_Page SHALL disable that choice and display a message indicating that a New Promo run is required first.
3. WHERE the Campaign_Lead_Pool is a past promo, THE Persona_Page SHALL let the user select the promo by `promo_id` from exactly the values P001, P002, and P003.
4. WHEN the Clustering_Level is `campaign`, THE Persona_Pipeline SHALL cluster only the leads in the chosen Campaign_Lead_Pool and SHALL exclude every lead outside that pool.
5. WHEN the Clustering_Level is `campaign`, THE Persona_Pipeline SHALL NOT use any Business_Segment_Field as a clustering input feature, generating the campaign's Personas from the campaign's own leads independently.
6. IF the chosen Campaign_Lead_Pool contains zero leads, THEN THE Persona_Page SHALL report an empty-audience message, SHALL NOT attempt clustering, and SHALL retain the current configuration.

### Requirement 6: Present personas on the Streamlit page

**User Story:** As a marketing analyst, I want an interactive page to configure and view personas, so that I can explore clusters and export them without writing code.

#### Acceptance Criteria

1. THE Persona_Page SHALL provide the Attribute_Picker, a k selector constrained to integer values from 2 through 6 inclusive, a Clustering_Level selector, and a Run control.
2. IF a user activates the Run control while the configuration is invalid because the Attribute_Picker has fewer than one selected attribute, the k selector value is outside 2 through 6 inclusive, or no Clustering_Level is selected, THEN THE Persona_Page SHALL reject the run, retain the current configuration and displayed results, and display an error message identifying the invalid input.
3. WHEN a user activates the Run control with a valid configuration, THE Persona_Page SHALL display one persona summary card per Persona of the Persona_Set, each card showing the Persona name, description, size as an integer count of leads, percentage of leads rounded to one decimal place, and recommended actions.
4. WHEN a persona run completes, THE Persona_Page SHALL display a cluster comparison chart across all Personas of the Persona_Set.
5. WHEN a persona run completes, THE Persona_Page SHALL display the Elbow_Plot.
6. THE Persona_Page SHALL provide a download control that exports the Persona_Labeled_Leads.
7. IF a user activates the download control before a persona run has completed in the current session, THEN THE Persona_Page SHALL keep the download control disabled so that no export is produced.
8. THE Persona_Core SHALL contain no Streamlit imports.
9. THE Persona_Page SHALL contain the Streamlit composition and session-state wiring and SHALL delegate all clustering and profile computation to the Persona_Core and Persona_Pipeline.

### Requirement 7: Integrate personas with existing decision cards

**User Story:** As a marketing analyst, I want personas layered onto the existing decision cards, so that I can see persona context alongside each card's existing guidance.

#### Acceptance Criteria

1. WHEN the Persona_Page renders the existing decision cards, THE Persona_Page SHALL display a Persona_Mix on each rendered card giving the per-Persona share of that card's cell leads across the Personas present in the cell, such that every decision card present in the Part 4 output has an associated Persona_Mix and a card whose cell has leads shows per-Persona shares summing to 100%.
2. WHEN the Persona_Page renders a card's persona layer, THE Persona_Page SHALL display it as a visually distinct persona element (badge or tab) adjacent to the card's existing guidance, without overwriting, hiding, or reordering any existing card field.
3. WHEN the Persona_Page attaches the persona layer, THE Persona_Page SHALL leave every existing card field and its value byte-for-byte identical to the Part 4 output produced for the same inputs with the persona layer disabled.
4. THE Persona_Pipeline SHALL leave the existing Part 4 card-building logic unchanged, performing no modification, re-computation, or re-ordering of the card fields produced by the Part 4 Card_Builder.
5. IF no persona assignment is available for any lead in a card's cell so that the Persona_Mix cannot be computed, THEN THE Persona_Page SHALL render the card with its existing guidance intact and display an indication that persona context is unavailable for that card, without failing the rendering of the remaining cards.
6. WHERE the Part 4 cards module supports merged decision cards, THE Persona_Page SHALL attach the persona layer to the merged cards. (Whether the cards module supports merging is an **OPEN DESIGN QUESTION** to be resolved in the design phase; if merging is unsupported, the persona layer attaches to the existing per-cell cards only.)

### Requirement 8: Export leads with persona labels

**User Story:** As a marketing analyst, I want to download the clustered leads with their persona labels and richer attributes, so that I can use them in downstream campaign tooling.

#### Acceptance Criteria

1. WHEN a user requests the leads export, THE Persona_Pipeline SHALL produce the Persona_Labeled_Leads containing exactly one row per lead present in the Part 4 leads input, each carrying a persona-label column that assigns the lead to exactly one Persona.
2. THE Persona_Labeled_Leads SHALL carry, in addition to the `client_id`, `best_channel`, `p_join`, and `control` columns from the existing Part 4 leads, the richer lead attributes joined from `customer_dna.csv`, the pivoted `product_ownership.csv`, and `outputs/features_part2.csv`, with every column name preserved exactly as in its source.
3. WHEN joining the richer lead attributes, THE Persona_Pipeline SHALL match rows on `client_id` using a left join keyed on the Part 4 leads, so that no Part 4 lead is dropped and no duplicate lead rows are introduced.
4. IF a lead's `client_id` has no matching row in `customer_dna.csv`, the pivoted `product_ownership.csv`, or `outputs/features_part2.csv`, THEN THE Persona_Pipeline SHALL retain that lead in the Persona_Labeled_Leads and leave the unmatched source attributes empty for that lead.
5. THE Persona_Pipeline SHALL produce the Persona_Labeled_Leads only as the last step of a persona run, after clustering and profile computation have both completed successfully, and SHALL NOT write the Persona_Labeled_Leads if either clustering or profile computation fails.
6. THE Persona_Labeled_Leads SHALL carry a group column, alongside the persona-label column, identifying the group each lead belongs to as the lead's business-segment value or the campaign identifier, as applicable to the Clustering_Level.
7. WHERE the Clustering_Level is `campaign`, THE Persona_Pipeline SHALL leave the persona-label column and the group column empty for every lead that appears in the Persona_Labeled_Leads but lies outside the chosen Campaign_Lead_Pool, so that only Campaign_Lead_Pool leads carry a persona label.

### Requirement 9: Keep persona generation an optional, isolated add-on

**User Story:** As a developer, I want persona generation isolated from the existing batch pipeline, so that adding it cannot regress the existing stages.

#### Acceptance Criteria

1. THE Persona_Pipeline SHALL be packaged as `src/part5_personas` following the existing part-naming convention, exposing a frozen `Config` dataclass of input/output `Path` fields plus domain constants and a `main(argv: list[str] | None = None) -> int` entry point, with each processing stage implemented as a single-responsibility class or function.
2. THE Persona_Pipeline SHALL make no edits to any module under the existing `run_pipeline.py` stages (`part1_optin`, `part2_network`, `part3_segments`, `part4_cards`), such that those stages produce byte-identical `outputs/` artifacts whether or not `src/part5_personas` is present.
3. THE Persona_Pipeline SHALL execute only when invoked explicitly through its own `main` entry point and SHALL NOT be added to the `run_pipeline.py` stage sequence, so that a full `run_pipeline.py` run completes without triggering persona generation.
4. THE Persona_Pipeline SHALL read its upstream inputs exclusively from the existing files in `outputs/` produced by Part 1 through Part 4 and SHALL NOT recompute any Part 1 through Part 4 result.
5. IF any required upstream artifact in `outputs/` is absent, THEN THE Persona_Pipeline SHALL halt before writing any output, return a non-zero exit code from `main`, and emit a message naming the missing artifact.
6. WHEN the Persona_Pipeline `main` entry point completes successfully, THE Persona_Pipeline SHALL return exit code 0.
7. IF any persona stage fails, THEN THE Persona_Pipeline `main` entry point SHALL return a non-zero exit code and emit a message naming the failing step.
8. WHEN a persona run writes any output file, THE Persona_Pipeline SHALL perform every output write only after all clustering and profile computation stages have completed successfully, leaving the existing `outputs/` artifacts unchanged if any stage fails before the write phase.
9. THE project dependency manifest `requirements.txt` SHALL include `kmodes` and SHALL introduce no dependency other than `kmodes` and the chart libraries already listed in `requirements.txt`.
