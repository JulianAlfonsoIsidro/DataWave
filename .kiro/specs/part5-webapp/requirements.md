# Requirements Document

## Introduction

Part 5 Webapp is a Streamlit desktop web application plus a thin pipeline-orchestration script that let a marketing analyst design a promo, score and segment its eligible audience with the existing Part 1-4 models, and read back the resulting action cards. The app is a presentation and orchestration layer only: all scoring, segmentation, and card logic lives in the already-built `part1_optin`, `part3_segments`, and `part4_cards` packages, which this spec reuses without retraining any model. There is no LLM in this spec; the ASK ASSISTANT surface is a non-functional placeholder.

The app presents three tabs (NEW PROMO, RESULTS, PAST PROMOS) under a fixed visual identity adapted from `data/theme_reference.png` (the BPI mobile app), rendered for a desktop web layout. A separate command-line script, `src/run_pipeline.py`, runs the four batch pipelines end to end in dependency order so the on-disk artifacts the app reads (the fitted Part 1 model, `outputs/cards.json`) can be regenerated from raw data.

All code runs under the project virtualenv (`.\.venv\Scripts\python.exe`) with `PYTHONPATH=src`; the app launches with `streamlit run app/main.py`. Any temporary output is written only under `scratch/`.

## Glossary

- **Webapp**: The system under specification. A Streamlit application rooted at `app/main.py` plus a `src/run_pipeline.py` orchestration script.
- **Pipeline_Runner**: The component at `src/run_pipeline.py` that runs the four batch pipelines in order.
- **Theme**: The fixed visual identity (colors, header, tabs, panels, buttons, cards) sampled from `data/theme_reference.png` and adapted to desktop web.
- **Theme_Reference**: The image at `data/theme_reference.png` from which exact colors are sampled.
- **New_Promo_Form**: The input form on the NEW PROMO tab capturing a promo's attributes.
- **Promo_Spec**: The in-memory promo description built from the New_Promo_Form, carrying at least `promo_id`, `product_type`, `mechanic`, `threshold_php`, `reward`, `eligible_segments`, `min_adb`, and `channels`. Its `promo_id` is auto-generated in the form `NEW-001`.
- **Eligible_Clients**: The subset of clients from `data/` that satisfy the Promo_Spec's eligibility filters (min ADB and eligible segments).
- **Score_Promo**: The existing function `part1_optin.scoring.score_promo(promo_dict, clients_df, model, config)` returning one row per client with `client_id`, `p_join`, and three top drivers. `threshold_php` is one of the promo features it consumes.
- **Assign_Segments**: A reusable entry point in `part3_segments` that assigns each scored lead one of the four segment labels from its score and capacity; exposed by this spec if not already present.
- **Build_Cards**: The existing function `part4_cards.build_cards(segments_df, promo_dict)` returning one Card per Cell in memory.
- **Segment_Label**: One of the four Part 3 labels in fixed order: "Ready Toppers" (score high, capacity high), "Willing but Stretched" (score high, capacity low), "Untapped Wealth" (score low, capacity high), "Not Now" (score low, capacity low).
- **Card**: A per-Cell result dict as produced by Build_Cards, carrying `segment`, `sendable_count`, `expected_joiners`, `joiners_90_low`, `joiners_90_high`, `expected_value`, `action`, `dominant_channel`, `message_angle`, `top_drivers`, and `excluded_by_reason`.
- **Results_Grid**: The 2x2 layout on the RESULTS tab whose rows are score high/low and whose columns are capacity low/high.
- **Sendable_Leads**: For a segment, the leads that are neither excluded nor held out as control, as produced by Part 4.
- **Cards_File**: The on-disk `outputs/cards.json` produced by the Part 4 batch pipeline, read by the PAST PROMOS tab.
- **Past_Promo**: One of the historical promos P001, P002, P003 whose predicted results come from the Cards_File.
- **Predicted_Join_Rate**: For a Past_Promo and segment, that segment Card's `expected_joiners` divided by its `sendable_count`.
- **Actual_Join_Rate**: For a Past_Promo and segment, the fraction of that segment's Sendable_Leads in `data/promo_leads.csv` whose `joined` equals 1.
- **What_If_Threshold**: The threshold_php value chosen by the WHAT-IF slider, used to rescore and recompute cards for the current eligible audience.

## Requirements

### Requirement 1: Orchestrate the batch pipelines and reuse the fitted model

**User Story:** As an analyst, I want a one-command pipeline run and an app that reuses the already-fitted model, so that the artifacts the app reads are reproducible and scoring never retrains.

#### Acceptance Criteria

1. WHEN `src/run_pipeline.py` is run THEN the Pipeline_Runner SHALL execute `part2_network`, then `part1_optin`, then `part3_segments`, then `part4_cards`, in that order.
2. IF any pipeline stage exits non-zero THEN the Pipeline_Runner SHALL stop before the next stage and surface that stage's failure, running no later stage.
3. WHEN the Webapp needs to score a promo THEN it SHALL load the already-fitted Part 1 model from its persisted artifacts under `outputs/` and pass it to Score_Promo without retraining or recalibrating.
4. WHERE a persisted model artifact required for scoring is missing THEN the Webapp SHALL show an error message directing the user to run `src/run_pipeline.py`, rather than raising an unhandled exception.

### Requirement 2: Apply the Theme adapted from the reference image

**User Story:** As a brand-conscious analyst, I want the app styled like the reference mobile app on a desktop layout, so that it reads as an official-looking promo tool.

#### Acceptance Criteria

1. WHEN the Webapp renders THEN it SHALL apply exact colors sampled from Theme_Reference -- a deep red primary, a gold/mustard accent, white panels, and dark text -- defined in `.streamlit/config.toml` and a single CSS block injected via `st.markdown`.
2. WHEN any page renders THEN the Webapp SHALL show a full-width deep-red header bar containing the title "Promo Audience Navigator" in bold white, with no BPI logo image (text title only).
3. WHEN the header renders THEN it SHALL show the three tab labels NEW PROMO, RESULTS, PAST PROMOS in uppercase, the active tab in white with a gold underline and the inactive tabs in gold text.
4. WHEN a results headline renders THEN the Webapp SHALL show one large bold headline number (the selected promo's expected joiners) above a small uppercase caption, styled like the account balance in Theme_Reference inside a white panel.
5. WHEN the action band renders THEN the Webapp SHALL show a deep-red band with four circular white buttons that have gold rings and red icons, labelled below in white: RUN, WHAT-IF, DOWNLOAD LEADS, ASK ASSISTANT.
6. WHEN content cards render THEN the Webapp SHALL show white cards with rounded corners, red headings, and gold dividers.

### Requirement 3: Build a promo and compute its audience on the NEW PROMO tab

**User Story:** As an analyst, I want to describe a promo and run it, so that I get a scored, segmented, carded audience from the existing models.

#### Acceptance Criteria

1. WHEN the NEW PROMO tab renders THEN the New_Promo_Form SHALL capture `product_type`, `mechanic`, `threshold_php`, `reward`, eligible segments, `min_adb`, and `channels`, and the Webapp SHALL auto-generate the Promo_Spec's `promo_id` in the form `NEW-001`.
2. WHEN RUN is pressed THEN the Webapp SHALL select Eligible_Clients from `data/` by keeping only clients whose latest ADB is at least `min_adb` and whose segment is among the Promo_Spec's eligible segments.
3. WHEN Eligible_Clients are selected THEN the Webapp SHALL score them with Score_Promo using the Promo_Spec and the loaded model, then assign each a Segment_Label with Assign_Segments, then build Cards with Build_Cards.
4. IF no client satisfies the eligibility filters THEN the Webapp SHALL show an empty-audience message and produce no Cards, rather than erroring.
5. WHEN a RUN completes THEN the Webapp SHALL retain the resulting Cards, Sendable_Leads, and the eligible audience so the RESULTS, DOWNLOAD LEADS, and WHAT-IF surfaces operate on that run.

### Requirement 4: Present results, decision cards, and lead download on the RESULTS tab

**User Story:** As an analyst, I want to see the audience split four ways with its decision cards and download the leads, so that I can act on the recommendation.

#### Acceptance Criteria

1. WHEN the RESULTS tab renders after a RUN THEN the Results_Grid SHALL show a 2x2 layout with rows score high/low and columns capacity low/high, each cell naming its Segment_Label with that segment's client count and expected joiners.
2. WHEN the RESULTS tab renders after a RUN THEN the Webapp SHALL show the four decision Cards, each displaying action, dominant channel, message angle, expected joiners with its 90% range, expected value, top drivers, and exclusions-by-reason.
3. WHEN DOWNLOAD LEADS is pressed THEN the Webapp SHALL offer a CSV of the Sendable_Leads for each segment.
4. IF the RESULTS tab is opened before any RUN has completed THEN the Webapp SHALL show a prompt to run a promo first, rather than an empty or broken grid.

### Requirement 5: Compare predicted versus actual on the PAST PROMOS tab

**User Story:** As an analyst, I want to see how past promos' predictions compared to what actually happened, so that I can judge the model's track record.

#### Acceptance Criteria

1. WHEN the PAST PROMOS tab renders THEN the Webapp SHALL show one Card per Past_Promo (P001, P002, P003) built from the Cards_File.
2. WHEN a Past_Promo Card renders THEN it SHALL show, per segment, the Predicted_Join_Rate (that segment Card's `expected_joiners` divided by its `sendable_count`) alongside the Actual_Join_Rate computed over that same segment's Sendable_Leads using `joined` in `data/promo_leads.csv`.
3. WHERE the Cards_File is absent THEN the Webapp SHALL show a message directing the user to run `src/run_pipeline.py`, rather than raising an unhandled exception.
4. WHERE a Past_Promo or segment has no Sendable_Leads THEN the Webapp SHALL show its Actual_Join_Rate as not-available rather than dividing by zero.

### Requirement 6: Rescore with WHAT-IF and stub ASK ASSISTANT

**User Story:** As an analyst, I want to vary the threshold and see the audience rescored, and I want a visible placeholder for the future assistant, so that I can explore scenarios today and know what is coming.

#### Acceptance Criteria

1. WHEN WHAT-IF is opened after a RUN THEN the Webapp SHALL show a threshold slider initialized to the current Promo_Spec's `threshold_php`.
2. WHEN the What_If_Threshold changes THEN the Webapp SHALL rescore the current eligible audience by calling Score_Promo with the new threshold on the already-loaded model (no retraining or recalibration), then reassign segments with Assign_Segments and rebuild Cards with Build_Cards, and update the displayed results.
3. IF WHAT-IF is opened before any RUN has completed THEN the Webapp SHALL show a prompt to run a promo first, rather than an inert slider.
4. WHEN ASK ASSISTANT is opened THEN the Webapp SHALL show a placeholder panel reading that it is coming in the next spec, performing no LLM call.
