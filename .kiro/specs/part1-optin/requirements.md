# Requirements Document

## Introduction

Part 1 Opt-In is a Python batch machine-learning pipeline that builds a promo opt-in propensity model. For each client who was messaged about a promo (a treated lead), the pipeline assembles a feature row from several client data sources, trains a calibrated XGBoost binary classifier to predict whether the client opts in (joins the promo), validates the model with leave-one-promo-out cross-validation, and explains each scored lead with its top SHAP feature drivers. The pipeline persists a trained model artifact and a scores file, and exposes a scoring function that can estimate join probabilities for a new, previously unseen promo.

The pipeline runs as a module (`python -m part1_optin.main` with `PYTHONPATH=src`) and follows the same conventions as the existing `part2_network` package: a `Config` dataclass holding input and output paths, a `main(argv)` entry point returning an integer exit code, and argparse-based overrides. A strict safety rule applies throughout: the pipeline must never read any answer-key file.

## Glossary

- **Part1_Optin_Pipeline**: The system under specification. A Python module at `src/part1_optin` that loads treated leads, assembles features, trains and calibrates a model, validates it, scores leads, explains scores, and writes outputs.
- **Lead_Loader**: The component responsible for loading the promo lead list and selecting the treated leads used for training.
- **Feature_Assembler**: The component responsible for building one Feature_Row per lead by joining the client data sources.
- **Model_Trainer**: The component responsible for training the XGBoost classifier and applying isotonic calibration.
- **Validator**: The component responsible for leave-one-promo-out cross-validation and metric reporting.
- **Explainer**: The component responsible for computing SHAP values and deriving per-lead top feature drivers.
- **Scorer**: The component responsible for producing calibrated join probabilities for leads and for unseen promos.
- **Promo_Leads_File**: The input CSV at `data/promo_leads.csv` with columns `promo_id`, `client_id`, `control_group`, `channel_sent`, `joined`, `join_date`.
- **Treated_Lead**: A row in the Promo_Leads_File whose `control_group` equals 0, meaning the client was messaged. Treated leads are the training and scoring population.
- **Join_Label**: The binary target taken from the `joined` column of a Treated_Lead, where 1 means the client opted in and 0 means the client did not.
- **Feature_Row**: The assembled set of predictor values for a single Treated_Lead, joined on `client_id` and augmented with the lead's promo attributes.
- **Customer_DNA_File**: The input CSV at `data/customer_dna.csv` with client attribute columns `segment`, `age_band`, `tenure_years`, `region`, `sec_class`, `inflow_type`, `digital_app_user`, `online_shopper`, `frugal_flag`, `investment_propensity_decile`, `email_valid`, `mobile_valid`, keyed by `client_id`.
- **Product_Ownership_File**: The input CSV at `data/product_ownership.csv` with columns `client_id`, `product_code`, `product_type`, `open_date`, `status`.
- **Active_Product_Count**: For a client and a distinct `product_type`, the count of Product_Ownership_File rows for that client with `status` equal to "Active".
- **ADB_File**: The input CSV at `data/adb_monthly.csv` with columns `client_id`, `month` (`YYYY-MM`), `adb_php`.
- **Latest_ADB**: For a client, the `adb_php` value for that client's most recent `month` in the ADB_File.
- **ADB_Trend**: For a client, the slope of a linear regression of `adb_php` against month index over that client's most recent three months, or over the available months if fewer than three exist.
- **Contact_History_File**: The input CSV at `data/contact_history.csv` with columns `client_id`, `contact_date`, `campaign_id`, `channel`.
- **Avg_Contacts_Per_Month**: For a client, the average number of Contact_History_File rows per calendar month for that client.
- **NDB_File**: The input CSV at `data/ndb.csv` with columns `client_id`, `flag_type`, `flag_date`.
- **NDB_Flag**: For a client, 1 if the client appears in the NDB_File, otherwise 0.
- **Part2_Features_File**: The input CSV at `outputs/features_part2.csv` holding the part 2 network features, one row per `client_id`.
- **Promo_History_File**: The input CSV at `data/promo_history.csv` with columns `promo_id`, `promo_name`, `product_type`, `mechanic`, `threshold_php`, `reward`, `start_date`, `end_date`, `channels`.
- **Promo_Attributes**: For a lead, the `mechanic` and `threshold_php` values of that lead's promo, taken from the Promo_History_File by joining on `promo_id`.
- **Answer_Key_File**: Any file whose name contains the substring `_answer_key` (for example `data/_answer_key_clients.csv` or `data/_answer_key_promos.csv`).
- **Calibrated_Model**: An XGBoost binary classifier whose output scores have been mapped to calibrated probabilities using isotonic calibration.
- **Leave_One_Promo_Out**: A cross-validation scheme over the promos P001, P002, and P003 in which the model is trained on the Treated_Leads of two promos and evaluated on the Treated_Leads of the third held-out promo, repeated so that each promo is held out exactly once.
- **ROC_AUC**: The area under the receiver operating characteristic curve of predicted join probabilities against the Join_Label.
- **Capture_Rate_Top_Quintile**: Within a held-out promo, the number of actual joiners among the leads in the top 20 percent of predicted join probability divided by the total number of actual joiners.
- **Calibration_Table**: A table that bins leads by predicted join probability and reports, per bin, the mean predicted probability and the observed join rate.
- **SHAP_Driver**: A feature identified by SHAP as contributing to a lead's predicted score, ranked by the absolute value of its SHAP contribution for that lead.
- **Model_Artifact**: The persisted trained model written to `outputs/model_part1.json`.
- **Scores_File**: The output CSV at `outputs/scores.csv` with columns `promo_id`, `client_id`, `p_join`, `top_driver_1`, `top_driver_2`, `top_driver_3`.
- **Unseen_Promo**: A promo not present in the training data, described by a promo dictionary carrying at least `promo_id`, `mechanic`, and `threshold_php`.

## Requirements

### Requirement 1: Select training leads and label

**User Story:** As a data scientist, I want the pipeline to train only on messaged leads with a known opt-in outcome, so that the model learns promo uptake from the correct population.

#### Acceptance Criteria

1. WHEN the Part1_Optin_Pipeline starts, THE Lead_Loader SHALL read the Promo_Leads_File from `data/promo_leads.csv`.
2. WHEN the Lead_Loader selects the training population, THE Lead_Loader SHALL keep only the Treated_Leads, which are the rows where `control_group` equals 0, and exclude all rows where `control_group` is not equal to 0.
3. WHEN the Lead_Loader selects the training population, THE Lead_Loader SHALL keep only rows whose `promo_id` is one of P001, P002, or P003, and exclude any row whose `promo_id` is not one of those three values.
4. WHEN the Lead_Loader encounters more than one row sharing the same (`promo_id`, `client_id`) pair, THE Lead_Loader SHALL retain exactly one row for that pair and discard the remaining duplicate rows, so that each (`promo_id`, `client_id`) pair appears at most once in the Treated_Leads.
5. WHEN the Lead_Loader prepares the target, THE Lead_Loader SHALL set the Join_Label of each Treated_Lead to the value of that lead's `joined` column, where the value 1 denotes opted in and the value 0 denotes not opted in.
6. IF a Treated_Lead has a `joined` value that is missing or is any value other than 0 or 1, THEN THE Lead_Loader SHALL exclude that lead from the training population.
7. IF the Promo_Leads_File does not exist at `data/promo_leads.csv`, THEN THE Lead_Loader SHALL halt the Part1_Optin_Pipeline without producing any downstream output and SHALL raise an error that names the missing file path.
8. IF zero Treated_Leads remain after filtering to `control_group` equal to 0, restricting `promo_id` to P001/P002/P003, removing duplicate (`promo_id`, `client_id`) pairs, and excluding leads with a missing or non-0/1 `joined` value, THEN THE Lead_Loader SHALL halt the Part1_Optin_Pipeline without producing any downstream output and SHALL raise an error indicating that no treated leads were found.

### Requirement 2: Assemble features per lead and prohibit answer-key files

**User Story:** As a data scientist, I want each lead enriched with client and promo features from every approved source, so that the model has predictive inputs, while never touching answer-key data.

#### Acceptance Criteria

1. WHEN the Feature_Assembler builds a Feature_Row for a Treated_Lead, THE Feature_Assembler SHALL join on `client_id` all columns of the Customer_DNA_File except `client_id`, and SHALL encode each categorical column into a numeric predictor deterministically so that the same category value maps to the same numeric value on every run.
2. IF a Treated_Lead's `client_id` is absent from the Customer_DNA_File, THEN THE Feature_Assembler SHALL fill that lead's Customer_DNA predictors with 0 and set a Customer_DNA_Missing_Flag to 1, and otherwise set that flag to 0.
3. WHEN the Feature_Assembler processes the Product_Ownership_File, THE Feature_Assembler SHALL produce one Active_Product_Count column for each distinct `product_type` value present in the file, each holding the count of that client's rows with `status` equal to "Active".
4. WHERE a client has no Product_Ownership_File rows with `status` equal to "Active" for a given `product_type`, THE Feature_Assembler SHALL set that client's Active_Product_Count for that `product_type` to 0.
5. WHEN the Feature_Assembler processes the ADB_File, THE Feature_Assembler SHALL compute Latest_ADB as the `adb_php` of the client's chronologically most recent `month`, and SHALL compute ADB_Trend as the linear regression slope of `adb_php` against ascending month index over the client's most recent three months, or over the available months when fewer than three months exist.
6. WHERE a client has exactly one month of ADB data, THE Feature_Assembler SHALL set that client's ADB_Trend to 0.
7. IF a Treated_Lead's `client_id` is absent from the ADB_File, THEN THE Feature_Assembler SHALL fill that lead's Latest_ADB and ADB_Trend with 0 and set an ADB_Missing_Flag to 1, and otherwise set that flag to 0.
8. WHEN the Feature_Assembler processes the Contact_History_File, THE Feature_Assembler SHALL compute Avg_Contacts_Per_Month as the client's total count of contact rows divided by the number of distinct calendar months in which that client has at least one contact row.
9. WHERE a client has no rows in the Contact_History_File, THE Feature_Assembler SHALL set that client's Avg_Contacts_Per_Month to 0.
10. WHEN the Feature_Assembler processes the NDB_File, THE Feature_Assembler SHALL set NDB_Flag to 1 for a client that appears in the NDB_File and to 0 otherwise.
11. WHEN the Feature_Assembler incorporates part 2 features, THE Feature_Assembler SHALL join all columns of the Part2_Features_File on `client_id`.
12. IF a Treated_Lead's `client_id` is absent from the Part2_Features_File, THEN THE Feature_Assembler SHALL fill that lead's Part2 feature columns with 0 and set a Part2_Features_Missing_Flag to 1, and otherwise set that flag to 0.
13. WHEN the Feature_Assembler attaches Promo_Attributes, THE Feature_Assembler SHALL join the `mechanic` and `threshold_php` of each lead's promo from the Promo_History_File on `promo_id`.
14. THE Part1_Optin_Pipeline SHALL NOT read, open, or use any Answer_Key_File whose name contains the substring `_answer_key`.

### Requirement 3: Train a calibrated XGBoost classifier

**User Story:** As a data scientist, I want an XGBoost model with isotonic probability calibration, so that predicted join probabilities are both discriminative and well calibrated.

#### Acceptance Criteria

1. WHEN the Model_Trainer trains the model, THE Model_Trainer SHALL fit an XGBoost binary classifier on the assembled Feature_Rows of the Treated_Leads using the Join_Label as the target.
2. WHEN the Model_Trainer trains or calibrates the model, THE Model_Trainer SHALL use a fixed random seed for all stochastic operations so that two runs on identical inputs produce identical Calibrated_Model scores for every Treated_Lead.
3. WHEN the Model_Trainer calibrates the model, THE Model_Trainer SHALL apply isotonic calibration to the XGBoost scores to produce the Calibrated_Model, fitting the isotonic calibrator only on Treated_Leads that were not used to judge generalization in the current evaluation fold.
4. WHILE running Leave_One_Promo_Out cross-validation, THE Model_Trainer SHALL fit the XGBoost classifier and its isotonic calibrator using only the two training promos' Treated_Leads and SHALL NOT use any held-out promo's Treated_Leads to fit either the classifier or the calibrator.
5. WHEN the Scorer produces a join probability, THE Scorer SHALL emit a calibrated probability in the inclusive range 0 to 1.
6. IF the Join_Label of the Treated_Leads available for fitting the classifier or the isotonic calibrator contains only a single class, THEN THE Model_Trainer SHALL halt the Part1_Optin_Pipeline without producing a Calibrated_Model and raise an error indicating that calibration requires both opt-in and non-opt-in examples.

### Requirement 4: Validate with leave-one-promo-out cross-validation

**User Story:** As an analyst, I want the model evaluated on a promo it did not train on, so that I can judge how well it generalizes to each promo.

#### Acceptance Criteria

1. WHEN the Validator runs, THE Validator SHALL perform Leave_One_Promo_Out cross-validation across the promos P001, P002, and P003, training on two promos' Treated_Leads and evaluating on the held-out promo's Treated_Leads, so that each promo is held out exactly once for a total of three folds.
2. WHEN the Validator evaluates a held-out promo that contains both at least one joiner and at least one non-joiner, THE Validator SHALL report the ROC_AUC of predicted join probabilities against the Join_Label for that held-out promo as a value in the inclusive range 0 to 1.
3. WHEN the Validator evaluates a held-out promo with at least one actual joiner, THE Validator SHALL report the Capture_Rate_Top_Quintile as a value in the inclusive range 0 to 1, computed as the number of actual joiners whose predicted join probability ranks in the top 20 percent divided by the total number of actual joiners, where the top-20-percent cutoff position is ceil(0.20 x N) for N held-out leads and all leads whose predicted probability is greater than or equal to the probability at the cutoff position are counted as being in the top quintile.
4. WHEN the Validator evaluates a held-out promo, THE Validator SHALL report a Calibration_Table that assigns the held-out leads to 10 equal-width bins spanning the predicted-probability interval 0 to 1 and, for each bin that contains at least one lead, shows the mean predicted probability and the observed join rate, and SHALL omit or mark as empty any bin that contains zero leads rather than reporting a value for it.
5. IF a held-out promo contains zero actual joiners, THEN THE Validator SHALL omit the ROC_AUC and Capture_Rate_Top_Quintile for that promo and report an indication that these metrics are undefined due to the absence of joiners, without halting the remaining folds.
6. THE Validator SHALL present the ROC_AUC, Capture_Rate_Top_Quintile, and Calibration_Table separately for each of the three held-out promos.

### Requirement 5: Explain scores with top SHAP drivers

**User Story:** As a campaign manager, I want the main reasons behind each lead's score, so that I can understand and act on the model's predictions.

#### Acceptance Criteria

1. WHEN the Explainer runs, THE Explainer SHALL compute one SHAP contribution value per Feature_Row predictor for each scored Feature_Row, computed on the underlying XGBoost model of the Calibrated_Model.
2. WHEN the Explainer derives drivers for a scored lead, THE Explainer SHALL identify each driver by its Feature_Row predictor name as a string, and SHALL select the three predictors with the largest absolute SHAP contribution for that lead, ordered from largest to smallest absolute contribution.
3. IF two or more predictors share the same absolute SHAP contribution for a scored lead while competing for a driver position, THEN THE Explainer SHALL break the tie by ascending predictor name, so that the ordering is deterministic across repeated runs on identical inputs.
4. WHERE a scored lead has fewer than three predictors with a non-zero SHAP contribution, THE Explainer SHALL fill each remaining driver position with an empty string.

### Requirement 6: Persist model artifact and scores

**User Story:** As a downstream consumer, I want the trained model and per-lead scores saved to stable paths, so that I can reuse the model and inspect the predictions.

#### Acceptance Criteria

1. WHEN training and calibration complete, THE Model_Trainer SHALL fit the final model on all Treated_Leads and persist the Model_Artifact to `outputs/model_part1.json` as a valid JSON XGBoost booster document.
2. IF the pipeline run fails before the final model is fit, THEN THE Model_Trainer SHALL NOT write the Model_Artifact.
3. WHEN scoring completes, THE Scorer SHALL write the Scores_File to `outputs/scores.csv` as a comma-separated file with a single header row and the fixed column order `promo_id`, `client_id`, `p_join`, `top_driver_1`, `top_driver_2`, `top_driver_3`, and no index column.
4. THE Scorer SHALL write each `p_join` value as a decimal in the inclusive range 0 to 1 rounded to 6 decimal places.
5. THE Scorer SHALL order the rows of the Scores_File by ascending `promo_id` and then by ascending `client_id`.
6. THE Scorer SHALL write exactly one row in the Scores_File for each scored Treated_Lead.
7. IF the `outputs` directory does not exist, THEN THE Part1_Optin_Pipeline SHALL create the `outputs` directory before writing the Model_Artifact and the Scores_File.

### Requirement 7: Score unseen promos through the API and CLI

**User Story:** As a campaign manager, I want to score eligible clients for a brand-new promo and run the whole pipeline from one command, so that I can target a promo that has never been sent before.

#### Acceptance Criteria

1. THE Scorer SHALL expose a function `score_promo(promo_dict, clients_df)` that accepts an Unseen_Promo dictionary carrying at least `promo_id`, `mechanic`, and `threshold_php`, and a clients data frame carrying the eligible client identifiers.
2. WHEN `score_promo(promo_dict, clients_df)` is called, THE Scorer SHALL assemble Feature_Rows for the eligible clients using the Promo_Attributes from the supplied promo dictionary, producing feature columns that match the Calibrated_Model's trained feature schema in column set, column order, and categorical encoding.
3. WHEN `score_promo(promo_dict, clients_df)` scores the eligible clients, THE Scorer SHALL apply the existing Calibrated_Model without retraining or recalibrating it, and SHALL return one calibrated join probability in the inclusive range 0 to 1 for each eligible client.
4. IF the `mechanic` in the supplied promo dictionary was not present among the training Treated_Leads used to fit the Calibrated_Model, THEN THE Scorer SHALL still return a calibrated join probability for each eligible client and SHALL emit a warning indicating that predictions are less reliable for unseen promo mechanics.
5. WHEN `score_promo(promo_dict, clients_df)` returns, THE Scorer SHALL include, for each eligible client, the three top SHAP_Driver features ordered from largest to smallest absolute SHAP contribution, filling any position beyond the client's count of non-zero-contribution features with an empty value.
6. WHEN the pipeline is invoked as `python -m part1_optin.main` with `PYTHONPATH=src` and every step completes successfully, THE Part1_Optin_Pipeline SHALL load the Treated_Leads, assemble features, train and calibrate the model, run Leave_One_Promo_Out validation and report metrics, fit the final model on all Treated_Leads, score the leads, compute the top SHAP drivers, write the Model_Artifact and the Scores_File, and return the integer exit code 0.
7. IF any pipeline step fails before completion, THEN THE Part1_Optin_Pipeline SHALL halt without writing the Model_Artifact or the Scores_File, surface an error indicating the failing step, and return a non-zero integer exit code.
8. WHERE command-line arguments override input or output paths, THE Part1_Optin_Pipeline SHALL apply those overrides to the Config before loading inputs or writing outputs.
