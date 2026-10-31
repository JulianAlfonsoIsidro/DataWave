# Requirements Document

## Introduction

Part 5 Webapp is a Streamlit desktop web application plus a thin pipeline-orchestration script that let a marketing analyst design a promo, score and segment its eligible audience with the existing Part 1-4 models, and read back the resulting action cards. The app is a presentation and orchestration layer only: all scoring, segmentation, and card logic lives in the already-built `part1_optin`, `part3_segments`, and `part4_cards` packages, which this spec reuses without retraining any model. There is no LLM in this spec; the ASK ASSISTANT surface is a non-functional placeholder.

The app presents its surfaces as Title Case tabs (New Promo, Results, Past Promos, plus What-If and Ask Assistant) under a fixed visual identity matching the BPI public website, rendered for a desktop web layout. A separate command-line script, `src/run_pipeline.py`, runs the four batch pipelines end to end in dependency order so the on-disk artifacts the app reads (the fitted Part 1 model, `outputs/cards.json`) can be regenerated from raw data.

All code runs under the project virtualenv (`.\.venv\Scripts\python.exe`) with `PYTHONPATH=src`; the app launches with `streamlit run app/main.py`. Any temporary output is written only under `scratch/`.

## Glossary

- **Webapp**: The system under specification. A Streamlit application rooted at `app/main.py` plus a `src/run_pipeline.py` orchestration script.
- **Pipeline_Runner**: The component at `src/run_pipeline.py` that runs the four batch pipelines in order.
- **Theme**: The fixed visual identity (colors, fonts, utility bar, nav bar, breadcrumb, hero, cards, tiles, buttons) matching the BPI public website, adapted to the desktop web app.
- **Theme_Reference**: The BPI website reference screenshot from which the exact reds are sampled.
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

### Requirement 2: Apply the Theme matching the BPI website

**User Story:** As a brand-conscious analyst, I want the app styled like the BPI public website, so that it reads as a polished, official-looking promo tool.

#### Acceptance Criteria

1. WHEN the Webapp renders THEN it SHALL apply a white page background, generous whitespace, a centered content column about 1200px wide, the Poppins web font, and dark charcoal text, with the exact reds sampled from Theme_Reference (a deep red primary and a deep-to-lighter red gradient) defined in `.streamlit/config.toml` and a single stylesheet `app/styles.css` loaded once; gold is used only as a small accent, if at all.
2. WHEN any page renders THEN the Webapp SHALL hide Streamlit's default header, menu, footer and sidebar toggle, and SHALL render all titles, tabs, buttons and labels in Title Case (e.g. "New Promo", "Download Leads"), not uppercase.
3. WHEN the page chrome renders THEN the Webapp SHALL show a top utility bar (small gray context text on the left, small links on the right, thin gray divider), then a main nav bar with the text title "Promo Audience Navigator" in bold red on the left (no BPI logo image), the nav items New Promo / Results / Past Promos in dark text on the right with the active item in red under a thin red underline, then a gray breadcrumb row below the nav.
4. WHEN a page hero renders THEN the Webapp SHALL show, on the left, a large bold title with a one-line subtitle and a red-gradient pill button with an arrow, and, on the right, a rounded red-gradient panel showing the headline KPI (expected joiners) in large white text (in place of a photo).
5. WHEN buttons and the 2x2 grid render THEN primary buttons SHALL be red-gradient with white Title Case text, rounded, with a subtle hover lift (secondary buttons white with a red border), and the four 2x2 tiles SHALL be rounded with Ready Toppers in the red gradient with white text and the other three white with a thin red border.
6. WHEN content cards, form inputs, sliders, and stat chips render THEN cards SHALL be white with 16px rounded corners, a soft shadow, a red section heading, and light gray dividers (two per row on wide screens); form inputs and sliders SHALL be rounded with light gray borders and a red focus/slider color; and numeric stat chips SHALL be small rounded pills.

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
