# Requirements Document

## Introduction

Part 2 Network is a Python (pandas) batch feature-engineering pipeline that reads client transaction records and produces one row of network- and money-flow features per client. The features characterize each client's outflow behavior (how much money leaves the bank and to where), the stability of external transfers over the observation window, the composition of inflows by funding source, and the composition of outflows by spending category. The pipeline also runs a validation routine that joins the engineered features to a promo lead list and reports the promo-join rate across external-outflow-ratio quartiles.

The transaction data spans three calendar months (2026-07, 2026-08, 2026-09) and covers a fixed set of clients. "External" money movement is defined by outflows to counterparties of type "Other bank" (which in this dataset are settled over the InstaPay and PESONet channels). The engineered feature set feeds downstream promo-targeting analysis, so correctness and reproducibility of the per-client aggregates are the primary concerns.

## Glossary

- **Part2_Network_Pipeline**: The system under specification. A Python module at `src/part2_network` that reads transaction data, computes per-client features, writes the feature output file, and runs the validation report.
- **Transaction_Reader**: The component of the Part2_Network_Pipeline responsible for loading and validating the input transactions file.
- **Feature_Builder**: The component of the Part2_Network_Pipeline responsible for computing all per-client features.
- **Validation_Reporter**: The component of the Part2_Network_Pipeline responsible for joining features to promo leads and printing the join-rate report.
- **Transactions_File**: The input CSV at `data/transactions.csv` with columns `txn_id`, `client_id`, `txn_date`, `direction`, `amount_php`, `counterparty_id`, `counterparty_type`, `counterparty_category`, `channel`.
- **Promo_Leads_File**: The input CSV at `data/promo_leads.csv` with columns `promo_id`, `client_id`, `control_group`, `channel_sent`, `joined`, `join_date`.
- **Features_File**: The output CSV at `outputs/features_part2.csv`, one row per `client_id`.
- **Outflow**: A transaction whose `direction` equals "OUT".
- **Inflow**: A transaction whose `direction` equals "IN".
- **External_Outflow**: An Outflow whose `counterparty_type` equals "Other bank".
- **Total_Out**: For a client, the sum of `amount_php` over that client's Outflow transactions.
- **Out_Other_Bank**: For a client, the sum of `amount_php` over that client's External_Outflow transactions.
- **Ext_Outflow_Ratio**: For a client, Out_Other_Bank divided by Total_Out.
- **Transaction_Month**: The year-and-month (`YYYY-MM`) portion of a transaction's `txn_date`.
- **Months_With_Ext_Transfer**: For a client, the count of distinct Transaction_Month values in which that client has at least one External_Outflow, ranging from 0 to 3.
- **Inflow_Source**: One of the funding categories "Payroll", "Remittance", or "Business receipts", taken from `counterparty_category` on Inflow transactions.
- **Inflow_Share**: For a client and a given Inflow_Source, the sum of `amount_php` for Inflow transactions in that source divided by the client's total Inflow amount.
- **Spending_Category**: A distinct `counterparty_category` value appearing on Outflow transactions.
- **Spending_Share**: For a client and a given Spending_Category, the sum of `amount_php` for Outflow transactions in that category divided by the client's Total_Out.
- **Treated_Lead**: A row in the Promo_Leads_File whose `control_group` equals 0, meaning the lead was messaged (treated).
- **Ext_Outflow_Quartile**: One of four groups formed by splitting clients into four equal-count bins ordered by Ext_Outflow_Ratio.
- **Join_Rate**: Within a group of leads, the number of leads whose `joined` equals 1 divided by the number of leads in that group.

## Requirements

### Requirement 1: Load and validate transaction input

**User Story:** As a data engineer, I want the pipeline to load the transactions file and confirm its structure, so that downstream feature computation operates on known, valid columns.

#### Acceptance Criteria

1. WHEN the Part2_Network_Pipeline starts, THE Transaction_Reader SHALL read the Transactions_File from `data/transactions.csv`.
2. IF the Transactions_File does not exist at `data/transactions.csv`, THEN THE Transaction_Reader SHALL halt the Part2_Network_Pipeline without producing any downstream output and raise an error that names the missing file path.
3. IF the Transactions_File is missing any of the columns `client_id`, `txn_date`, `direction`, `amount_php`, `counterparty_type`, or `counterparty_category`, THEN THE Transaction_Reader SHALL halt the Part2_Network_Pipeline without producing any downstream output and raise an error that names each missing column.
4. WHEN the Transactions_File is read, THE Transaction_Reader SHALL parse `amount_php` as a numeric value and `txn_date` as a calendar date in the format `YYYY-MM-DD`.
5. IF any value in the `amount_php` column cannot be parsed as a numeric value, or any value in the `txn_date` column cannot be parsed as a date in the format `YYYY-MM-DD`, THEN THE Transaction_Reader SHALL halt the Part2_Network_Pipeline without producing any downstream output and raise an error that names the affected column and at least one offending row identifier.
6. IF the Transactions_File contains zero data rows after the header, THEN THE Transaction_Reader SHALL halt the Part2_Network_Pipeline without producing any downstream output and raise an error indicating that the Transactions_File contains no transaction records.

### Requirement 2: Compute total outflow per client

**User Story:** As an analyst, I want each client's total outflow amount, so that I can measure how much money the client moves out.

#### Acceptance Criteria

1. WHEN the Feature_Builder processes a client, THE Feature_Builder SHALL compute Total_Out as the sum of `amount_php` over that client's Outflow transactions, treating each `amount_php` as a non-negative amount.
2. WHERE a client has no Outflow transactions, THE Feature_Builder SHALL set Total_Out to 0.
3. THE Feature_Builder SHALL record Total_Out in the `total_out` column of the Features_File as a numeric value rounded to 2 decimal places.

### Requirement 3: Compute outflow to other banks per client

**User Story:** As an analyst, I want each client's outflow amount sent to other banks, so that I can quantify money leaving BPI.

#### Acceptance Criteria

1. WHEN the Feature_Builder processes a client, THE Feature_Builder SHALL compute Out_Other_Bank as the sum of `amount_php` over that client's External_Outflow transactions, treating each `amount_php` as a non-negative amount.
2. WHEN the Feature_Builder classifies an Outflow as an External_Outflow, THE Feature_Builder SHALL treat a transaction whose `counterparty_type` is missing or not equal to "Other bank" as not an External_Outflow and exclude it from Out_Other_Bank.
3. WHERE a client has no External_Outflow transactions, THE Feature_Builder SHALL set Out_Other_Bank to 0.
4. THE Feature_Builder SHALL record Out_Other_Bank in the `out_other_bank` column of the Features_File as a numeric value rounded to 2 decimal places.

### Requirement 4: Compute external outflow ratio per client

**User Story:** As an analyst, I want each client's external outflow as a fraction of total outflow, so that I can rank clients by how much of their spending leaves the bank.

#### Acceptance Criteria

1. WHEN a client's Total_Out is greater than 0, THE Feature_Builder SHALL compute Ext_Outflow_Ratio as Out_Other_Bank divided by Total_Out.
2. IF a client's Total_Out equals 0, THEN THE Feature_Builder SHALL set Ext_Outflow_Ratio to 0.
3. THE Feature_Builder SHALL produce an Ext_Outflow_Ratio value in the inclusive range 0 to 1 for every client.
4. THE Feature_Builder SHALL record Ext_Outflow_Ratio in the `ext_outflow_ratio` column of the Features_File as a numeric value rounded to 4 decimal places.

### Requirement 5: Count months with an external transfer per client

**User Story:** As an analyst, I want to know in how many of the three observed months a client sent money externally, so that I can distinguish habitual external movers from one-off movers.

#### Acceptance Criteria

1. WHEN the Feature_Builder processes a client, THE Feature_Builder SHALL compute Months_With_Ext_Transfer as the count of distinct Transaction_Month values for which that client has at least one External_Outflow transaction.
2. WHERE a client has no External_Outflow transactions, THE Feature_Builder SHALL set Months_With_Ext_Transfer to 0.
3. THE Feature_Builder SHALL produce a Months_With_Ext_Transfer value that is a non-negative integer in the inclusive range 0 to 3, with no fractional component.
4. IF a client has more than one External_Outflow transaction within the same Transaction_Month, THEN THE Feature_Builder SHALL count that Transaction_Month exactly once toward Months_With_Ext_Transfer.
5. THE Feature_Builder SHALL record Months_With_Ext_Transfer in the `months_with_ext_transfer` column of the Features_File.

### Requirement 6: Compute inflow share by funding source per client

**User Story:** As an analyst, I want each client's inflows broken down into Payroll, Remittance, and Business receipts shares, so that I can characterize how the client is funded.

#### Acceptance Criteria

1. WHEN the Feature_Builder processes a client, THE Feature_Builder SHALL compute Inflow_Share for each Inflow_Source in the set {Payroll, Remittance, Business receipts} as the sum of `amount_php` over that client's Inflow transactions whose `counterparty_category` equals that source, divided by the sum of `amount_php` over all of that client's Inflow transactions.
2. IF a client's total Inflow amount equals 0, THEN THE Feature_Builder SHALL set each of the three Inflow_Share values for that client to 0.
3. WHERE a client has a positive total Inflow amount but no Inflow transactions for a given Inflow_Source, THE Feature_Builder SHALL set that source's Inflow_Share to 0.
4. THE Feature_Builder SHALL produce each Inflow_Share value as a number in the inclusive range 0 to 1, rounded to 6 decimal places.
5. WHERE a client has a positive total Inflow amount and every one of that client's Inflow transactions has a `counterparty_category` in the set {Payroll, Remittance, Business receipts}, THE Feature_Builder SHALL produce three Inflow_Share values whose sum equals 1 within an absolute tolerance of 0.001.
6. THE Feature_Builder SHALL record the three inflow shares in the columns `inflow_share_payroll`, `inflow_share_remittance`, and `inflow_share_business_receipts` of the Features_File.

### Requirement 7: Compute spending share by counterparty category per client

**User Story:** As an analyst, I want each client's outflows broken down by spending category, so that I can profile where the client spends money.

#### Acceptance Criteria

1. WHEN the Feature_Builder processes a client, THE Feature_Builder SHALL compute Spending_Share for each Spending_Category as the sum of `amount_php` over that client's Outflow transactions whose `counterparty_category` equals that category, divided by that client's Total_Out.
2. THE Feature_Builder SHALL derive the set of Spending_Category output columns from the distinct `counterparty_category` values appearing on Outflow transactions across all clients, and SHALL include the same complete set of these columns in every row of the Features_File.
3. THE Feature_Builder SHALL name each Spending_Category column with the prefix `spend_share_` followed by the category value lowercased with each run of non-alphanumeric characters replaced by a single underscore.
4. IF a client has no Outflow transactions in a given Spending_Category, THEN THE Feature_Builder SHALL set that client's Spending_Share for that category to 0.
5. IF a client's Total_Out equals 0, THEN THE Feature_Builder SHALL set each Spending_Share for that client to 0.
6. THE Feature_Builder SHALL produce each Spending_Share value as a number in the inclusive range 0 to 1, rounded to 6 decimal places.
7. WHERE a client has a Total_Out greater than 0, THE Feature_Builder SHALL produce Spending_Share values across all Spending_Category columns whose sum equals 1 within an absolute tolerance of 0.001.

### Requirement 8: Emit one feature row per client

**User Story:** As a downstream consumer, I want exactly one feature row per client written to a stable output path, so that I can join the features reliably.

#### Acceptance Criteria

1. WHEN feature computation completes, THE Feature_Builder SHALL write the Features_File to `outputs/features_part2.csv` as a comma-separated file with a single header row naming every column.
2. THE Feature_Builder SHALL write exactly one row for each distinct `client_id` present in the Transactions_File, and SHALL NOT write more than one row for any `client_id`.
3. THE Feature_Builder SHALL include the `client_id` column as the first column of the Features_File.
4. IF the `outputs` directory does not exist, THEN THE Feature_Builder SHALL create the `outputs` directory before writing the Features_File.
5. THE Feature_Builder SHALL order the rows of the Features_File by ascending `client_id`.
6. IF the Transactions_File contains zero distinct clients, THEN THE Feature_Builder SHALL write a Features_File consisting of only the header row.

### Requirement 9: Validate features against promo leads by external outflow ratio quartile

**User Story:** As an analyst, I want the promo-join rate reported across external-outflow-ratio quartiles for promo P001 Treated_Leads, so that I can check whether external outflow behavior relates to promo uptake.

#### Acceptance Criteria

1. WHEN the Validation_Reporter runs, THE Validation_Reporter SHALL read the Promo_Leads_File from `data/promo_leads.csv`.
2. WHEN the Validation_Reporter selects leads, THE Validation_Reporter SHALL keep only the P001 Treated_Leads, which are the rows where `promo_id` equals "P001" and `control_group` equals 0.
3. WHEN the Validation_Reporter has the P001 Treated_Leads, THE Validation_Reporter SHALL inner-join those leads to the Features_File on `client_id`.
4. WHEN the joined P001 Treated_Leads are available, THE Validation_Reporter SHALL assign each joined lead to one of four Ext_Outflow_Quartile bins labeled Q1, Q2, Q3, and Q4, formed by ordering the joined leads by ascending Ext_Outflow_Ratio and splitting them into four groups whose counts differ by at most one.
5. IF two or more joined P001 Treated_Leads at a bin boundary share the same Ext_Outflow_Ratio, THEN THE Validation_Reporter SHALL order them by ascending `client_id` when assigning them to bins.
6. WHEN quartiles are assigned, THE Validation_Reporter SHALL compute the Join_Rate for each non-empty Ext_Outflow_Quartile as the count of joined P001 Treated_Leads with `joined` equal to 1 divided by the count of joined P001 Treated_Leads in that quartile, producing a value in the inclusive range 0 to 1.
7. WHEN the Join_Rate per quartile is computed, THE Validation_Reporter SHALL print one line per Ext_Outflow_Quartile in the order Q1, Q2, Q3, Q4, showing the quartile label, the lead count, and the Join_Rate.
8. THE Validation_Reporter SHALL print the overall inner-join rate as the count of P001 Treated_Leads matched to the Features_File divided by the total count of P001 Treated_Leads, producing a value in the inclusive range 0 to 1.
9. IF zero P001 Treated_Leads are selected after filtering to `promo_id` "P001" and `control_group` 0, THEN THE Validation_Reporter SHALL print a message indicating no matching leads were found and SHALL NOT attempt quartile computation.
