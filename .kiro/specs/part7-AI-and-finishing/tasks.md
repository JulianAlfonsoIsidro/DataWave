# Implementation Plan: Part 7 AI And Finishing

## Overview

The design uses Python, so all tasks use Python 3.10+ with the existing `src/` layout (`PYTHONPATH=src`). Foundations come first (dependencies, Label_Map, threshold module, Bedrock client), then the features that depend on them (card view, run_promo changes, extractor, assistant, persona narrator, persona view, impact, export, past promos), then cross-cutting tests, screenshots, and the report.

Ground rules for every task:

- Run all Python commands with `./.venv/bin/python` (for example `./.venv/bin/python -m pytest tests/test_part7_*.py`). Never use system Python or global installs.
- Install new dependencies (`boto3`, `pdfplumber`, `python-docx`, `openpyxl`) only into `.venv`.
- Write temporary files only under `scratch/`.
- Property tests: exactly 8 across Part 7 (Properties 1 to 8 from the design), each with `@settings(max_examples=100, deadline=None)`. All other tests are unit, example, edge, or integration tests.
- Do not modify Parts 1 to 4, `run_pipeline.py`, `outputs/`, or `data/`. UI text uses Title Case and no em dash or `--`.
- Bedrock tests inject a fake client and never touch the network.

## Tasks

- [x] 1. Set up dependencies and test scaffolding
  - [x] 1.1 Add dependencies, package marker, and shared test strategies
    - Append `boto3`, `pdfplumber`, `python-docx`, `openpyxl` (unpinned) to `requirements.txt`
    - Install into the venv with `./.venv/bin/python -m pip install -r requirements.txt`
    - Create `src/ai/__init__.py`
    - Create `tests/strategies_part7.py` with shared generators (payload trees, card dicts, ADB series, baseline frames, campaign profiles)
    - Confirm `.env` and `scratch/` are listed in `.gitignore`
    - _Requirements: 1.2, 1.3, scope note on requirements.txt_

- [x] 2. Implement the Label_Map
  - [x] 2.1 Create `src/labels.py`
    - Implement `FEATURE_LABELS`, `EXCLUSION_LABELS`, `HIDDEN_DRIVER_CODES`, `plain_label`, `is_known`, `plain_driver_phrase` (max 60 chars)
    - Resolve in order: exclusions, features, delegate to `part5_personas.labels.attribute_label`, then Title Case fallback with no underscores
    - Seed entries for `out_other_bank`, `ext_outflow_ratio`, `spend_share_retail`, `latest_adb`, `avg_contacts_per_month`, `digital_app_user`, `ndb_flag`, `ndb`, `over_contacted`, `no reachable channel`, `investment_propensity_decile`
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 2.2 Write unit tests for the Label_Map
    - Enumerate driver codes from `outputs/cards.json`, exclusion codes from `part4_cards`, and all UI-visible feature codes; assert each is known (not fallback) and has no underscore
    - Test the fallback output for unmapped codes
    - File: `tests/test_part7_labels_unit.py`
    - _Requirements: 4.1, 4.3, 10.2_

- [x] 3. Implement threshold types
  - [x] 3.1 Create `src/webapp_core/threshold.py`
    - Implement `ThresholdType`, `ThresholdSpec`, `THRESHOLD_SPECS` (four fixed ranges and steps), `default_value`, `format_value`, `per_client_amounts`, `effective_threshold`, `ThresholdResolution`
    - Balance Increase: per-client amounts = pct/100 times `latest_adb`, `threshold_php` = median of usable amounts, missing ADB fails capacity, error when no usable ADB, note at most 200 characters
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.10, 5.11_

  - [x] 3.2 Write property test for Balance Increase threshold
    - **Property 4: Balance Increase threshold equals the median of per-client amounts**
    - File: `tests/test_part7_threshold_property.py`
    - **Validates: Requirements 5.4, 5.5, 5.6, 5.10, 5.11**

  - [x] 3.3 Write unit tests for threshold types
    - Per type: min, max, step, default inside range and on the step grid; formatting with ₱ and %; note length
    - File: `tests/test_part7_threshold_unit.py`
    - _Requirements: 5.1, 5.2, 5.3, 5.7, 10.3_

- [x] 4. Implement the shared Bedrock client
  - [x] 4.1 Create `src/ai/bedrock.py`
    - Implement `BedrockResult`, `PayloadRejected`, `assert_private`, `credentials_available`, `converse`
    - Lazy boto3 import, `.env` via python-dotenv, 30 s worker-thread timeout, single attempt (`retries={"max_attempts": 1}`), one-fence JSON stripping
    - Every failure returns Demo with a fixed reason code; no credential values in output; Demo reported per call (not latched)
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.8, 1.10, 1.11, 1.12, 1.13_

  - [x] 4.2 Write property test for payload privacy
    - **Property 1: Bedrock payload privacy**
    - File: `tests/test_part7_bedrock_privacy_property.py`
    - **Validates: Requirements 1.10, 1.11, 3.13, 6.2, 6.13, 9.13**

  - [x] 4.3 Write unit tests for the Bedrock client
    - Four Demo cases (missing credentials, failed call, slow call with shortened timeout, invalid JSON); Demo not latched; reason/exception text free of credentials; single attempt counted with a fake
    - File: `tests/test_part7_bedrock_unit.py`
    - _Requirements: 1.4, 1.5, 1.6, 1.8, 1.13, 10.5_

- [~] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement the shared decision-card view
  - [x] 6.1 Create `src/webapp_core/card_view.py`
    - Implement `StatView`, `CardView`, `round_half_up`, `build_card_view`
    - Drop `mechanic` and `threshold_php`, keep up to 3 plain drivers, sorted `"<Plain Reason>: N"` exclusions (count desc, then alphabetical), whole-number stats with `L <= N <= H` clamping, tooltips at most 120 chars, title `"<promo_id> · <Segment>"`, fixed "None" choice for no exclusions
    - Never mutate the input card dict
    - _Requirements: 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12_

  - [x] 6.2 Write property test for card view
    - **Property 3: No raw codes reach decision-card text**
    - File: `tests/test_part7_card_view_property.py`
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6, 4.8, 4.11, 4.12**

  - [x] 6.3 Write unit tests for card view
    - Title format, tooltip lengths, "None" choice, headings, `cards.json` hash unchanged after rendering
    - File: `tests/test_part7_card_view_unit.py`
    - _Requirements: 4.7, 4.9, 4.10, 4.11_

  - [x] 6.4 Add shared card renderer and switch both card pages to it
    - Add badge, banner, stat tile, bar, tooltip helpers to `app/theme.py` and `app/styles.css` using existing tokens
    - Replace `_decision_card_html` in `app/main.py` and `_part4_card_readonly_html` in `app/persona_page.py` with one renderer over `CardView`
    - _Requirements: 4.2, 4.12, 1.7_

- [x] 7. Extend run_promo for threshold types
  - [x] 7.1 Edit `src/webapp_core/run_promo.py`
    - Add optional `threshold_type` and `threshold_pct` to `PromoSpec` and optional `non_excluded` frame to `RunResult` (defaults keep old constructors valid)
    - Populate `non_excluded` from the same classification call used for sendable leads
    - For Balance Increase, recompute `capacity_high` per client after `assign_segments` and re-derive segment labels without editing Part 3 files
    - _Requirements: 5.5, 5.6, 5.9, 8.1_

  - [x] 7.2 Wire threshold controls into New Promo and What-If
    - In `app/main.py`, move the Threshold_Type selector and slider above the `st.form`, keyed by type so a type change resets to the default
    - Replace `_whatif_slider_bounds` with `THRESHOLD_SPECS`; show the Balance Increase note; show the error and block the run when no usable ADB
    - _Requirements: 5.1, 5.2, 5.3, 5.7, 5.8, 5.11_

  - [x] 7.3 Write integration test for run_promo threshold handling
    - Balance Increase segments match recomputed per-client capacity; old `PromoSpec` calls still work; Part 3 files untouched
    - File: `tests/test_part7_run_promo_integration.py`
    - _Requirements: 5.5, 5.9, 10.3_

- [x] 8. Implement mocks, campaign extractor, and upload panel
  - [x] 8.1 Create `src/ai/mocks.py` with the extraction mock
    - Implement deterministic `mock_extract(text)` using keyword, mechanic, channel, and peso-amount rules plus labeled-line context parsing
    - _Requirements: 2.8, 1.9_

  - [x] 8.2 Create `src/ai/extractor.py`
    - Implement `UploadError` (type, size, unreadable, empty), `extract_text` (pdfplumber / python-docx, lazy imports, 10 MB limit), `validate_fields`, `extract_campaign`, `ExtractionResult`
    - Send at most 30,000 characters; drop invalid values; map channels to exactly `In-app`, `Email`, `SMS`; tag every field; Mock for non-JSON, Demo, or over 60 s (injectable clock); never raise
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.10, 2.11, 2.13_

  - [x] 8.3 Write property test for extraction validity
    - **Property 2: Extraction output is always valid and tagged**
    - File: `tests/test_part7_extraction_validity_property.py`
    - **Validates: Requirements 2.5, 2.6, 2.7, 2.9, 2.11**

  - [x] 8.4 Write unit tests for the extractor
    - DOCX/PDF fixtures in `tmp_path` or `scratch/`; wrong type, oversize, unreadable, empty errors; 30,000-char truncation; valid JSON accepted, missing/wrong-type/invalid rejected; Mock rules; 60 s budget
    - File: `tests/test_part7_extractor_unit.py`
    - _Requirements: 2.3, 2.4, 2.5, 2.10, 10.4, 10.5_

  - [x] 8.5 Create `app/upload_panel.py` and wire the two New Promo tabs
    - Add "Upload Campaign File" and "Fill In Details" tabs in `app/main.py`, prefill session state before widgets are created, show Field_Tag captions and the Demo Mode badge, store document text and context for the assistant
    - Show specific upload errors and leave form state unchanged on failure; never auto-run the analysis
    - _Requirements: 2.1, 2.3, 2.9, 2.11, 2.12, 2.13, 1.7_

- [x] 9. Implement the Campaign Assistant
  - [x] 9.1 Create `src/ai/assistant.py` and assistant mock templates
    - Implement `CampaignGrounding`, `AssistantAnswer`, `validate_question` (1 to 500 chars), `route`, `missing_items`, `truncate_words` (150), `answer`, `SUGGESTED_QUESTIONS`
    - Add Demo templates to `src/ai/mocks.py` built only from form fields and context
    - Append one JSON line (question, answer, ISO timestamp) to `scratch/assistant_log.jsonl`, creating `scratch/` if needed; log failure sets `log_saved=False`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.9, 3.10, 3.11, 3.13_

  - [x] 9.2 Write unit tests for the assistant
    - Question validation edges (0, 1, 500, 501, whitespace); routing; `missing_items`; four suggested questions; 150-word truncation; log line validity; log failure still answers; empty campaign makes no call
    - File: `tests/test_part7_assistant_unit.py`
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.10, 3.11, 3.12_

  - [x] 9.3 Create `app/assistant_page.py` and replace the Ask Assistant placeholder
    - Chat UI with four suggested-question buttons, Demo Mode badge, non-blocking log notice, and the "fill in or upload first" prompt
    - Route the tab in `app/main.py`
    - _Requirements: 3.8, 3.9, 3.11, 3.12, 1.7_

- [~] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement the Persona Narrator
  - [x] 11.1 Create `src/ai/persona_narrator.py` and the persona mock namer
    - Add `NotRequired[str]` `difference` key to `PersonaNaming` in `src/part5_personas/naming.py` (additive only)
    - Implement `PersonaAggregate`, `build_aggregate`, `validate_narration`, `BedrockNamer` (per-persona request, per-persona Mock fallback, `sources` map)
    - Add `MockPersonaNamer` to `src/ai/mocks.py`: plain language, no feature codes or banned phrases, deterministic, unique names
    - Leave clustering and `RuleBasedNamer` untouched
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12, 6.13_

  - [x] 11.2 Write unit tests for the persona narrator
    - Valid JSON accepted; each rule violation rejected individually; one failing persona does not affect others; Mock output free of underscores and banned phrases and stable on repeat
    - File: `tests/test_part7_persona_narrator_unit.py`
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.12, 10.4, 10.5_

  - [x] 11.3 Plug the narrator into persona generation and the page
    - Edit `src/webapp_core/personas.py` to accept a narration mode, build the narrator inside the runner, and carry `narration_source` on `PersonaRunResult`
    - Show the Demo Mode badge in `app/persona_page.py` when any persona text is Mock; use the Label_Map for any displayed code
    - _Requirements: 6.11, 4.2, 1.7_

  - [x] 11.4 Write integration test for unchanged clustering
    - With `BedrockNamer` in Demo Mode, labels and sizes at seed 42 equal those from `RuleBasedNamer`
    - File: `tests/test_part7_persona_clustering_integration.py`
    - _Requirements: 6.1_

- [x] 12. Implement the Expected Joiners By Persona view
  - [x] 12.1 Create `src/webapp_core/persona_view.py`
    - Implement `PersonaLine`, `PersonaSection`, `build_persona_section` over the existing `CardPersonaBreakdown` / `GroupCardBreakdown`
    - Sentence rows, zero-lead rows, "Total For <Segment Name>", "Other Personas" remainder row only when greater than 0, takeaway with first-in-order tie-break and all-zero case, "personas not generated" line, no group index in any string
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12_

  - [x] 12.2 Write property test for persona rows
    - **Property 6: Persona rows account for the whole card**
    - File: `tests/test_part7_persona_section_property.py`
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.6, 7.11**

  - [x] 12.3 Render the new section in the card pages
    - Pass `persona_lines` into the shared card renderer; use it in `app/main.py` live cards and `app/persona_page.py`; remove the old group-index wording
    - _Requirements: 7.1, 7.4, 7.5, 7.10, 7.12_

  - [x] 12.4 Write unit tests and update affected existing tests
    - Wording, total row, note, takeaway ties and all-zero, missing persona data line, no group index
    - Update existing tests asserting the old wording (`test_part5_personas_breakdown_render_unit.py`, `test_part5_personas_group_breakdown_unit.py`, any matching "Total for" or the `" -- "` title) and list each change for the report
    - File: `tests/test_part7_persona_view_unit.py`
    - _Requirements: 7.4, 7.5, 7.7, 7.8, 7.9, 4.10_

- [x] 13. Implement the Impact Summary
  - [x] 13.1 Create `src/webapp_core/impact.py`
    - Implement `load_channel_costs`, `plan_totals`, `compute_impact`, `ImpactSummary`
    - Baseline from `RunResult.non_excluded`; Recommended from sendable leads of non-Skip segments; X, Y, Z rounding and clamps; neutral message for zero baseline; cost-unavailable handling that keeps the other tiles
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.7, 8.8, 8.9, 8.10_

  - [x] 13.2 Write property test for impact invariants
    - **Property 5: Impact summary invariants**
    - File: `tests/test_part7_impact_property.py`
    - **Validates: Requirements 8.3, 8.4, 8.7, 8.10**

  - [x] 13.3 Write unit tests for the impact summary
    - Hand-computed X, Y, Z example; zero baseline messages and zero baseline joiners; missing cost file keeps two tiles; What-If rescore recomputes
    - File: `tests/test_part7_impact_unit.py`
    - _Requirements: 8.3, 8.6, 8.7, 8.8, 10.7_

  - [x] 13.4 Show the banner and tiles on Results and What-If
    - Banner above the decision cards, tiles "Messages Saved", "Joiners Kept (%)", "Cost Saved (₱)" with formula tooltips (at most 200 chars); What-If refreshes them after rescoring
    - _Requirements: 8.3, 8.5, 8.6, 8.7, 8.8_

- [x] 14. Implement the Export Workbook
  - [x] 14.1 Create `src/webapp_core/export_workbook.py`
    - Implement `build_workbook` and `workbook_filename` with openpyxl: Summary, Decision Cards (plain labels), Personas (or single "not generated" row), and Send List sheets for non-Skip segments with sendable leads (names at most 31 chars)
    - Title Case headers, bold header row, `freeze_panes = "A2"`, widths 10 to 60, `0.0%` and `"₱"#,##0` formats, no em dash or `--`
    - _Requirements: 9.1, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.13_

  - [x] 14.2 Write unit tests for the workbook
    - Opens with `openpyxl.load_workbook`; required sheets present; Skip/empty segments have no Send List; bold header and `A2` freeze on every sheet; sheet name length; column widths; no raw codes or `client_id` outside Send Lists
    - File: `tests/test_part7_export_unit.py`
    - _Requirements: 9.4, 9.7, 9.8, 9.9, 9.11, 10.8_

  - [x] 14.3 Add the Export Summary button to Results
    - Download button named `<promo_id>_campaign_summary.xlsx`; hidden or disabled with a message when no run exists; plain-language error and no download if the build fails
    - _Requirements: 9.1, 9.2, 9.12_

- [~] 15. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Implement the smarter Past Promos tab
  - [x] 16.1 Create `src/webapp_core/similarity.py`
    - Implement `WEIGHTS` (sum 100), `ComponentScore`, `SimilarityResult`, `similarity`, `duration_days` (inclusive), `rescale_weights`
    - Eight deterministic components per the design; Unavailable components excluded and weights rescaled; `score = None` when all unavailable
    - _Requirements: 11.8, 11.9, 11.10, 11.11, 11.12, 11.19_

  - [x] 16.2 Write property test for similarity
    - **Property 7: Similarity score bounds, determinism, and renormalization**
    - File: `tests/test_part7_similarity_property.py`
    - **Validates: Requirements 11.8, 11.9, 11.10, 11.11, 11.12**

  - [x] 16.3 Create `src/webapp_core/past_campaigns.py`
    - Implement loaders for `promo_history.csv` / `promo_leads.csv` (error naming the missing file, no partial data), audience derivation from leads joined to `customer_dna.csv`, `sort_campaigns`, `filter_campaigns`, `page`, and campaign detail (opt-in rate on treated leads, "Not Available" when zero)
    - Reuse existing `predicted_vs_actual` logic unchanged; no Bedrock or network imports
    - _Requirements: 11.1, 11.2, 11.4, 11.5, 11.6, 11.7, 11.13, 11.15, 11.16, 11.17, 11.18, 11.19, 11.20_

  - [x] 16.4 Write property test for past campaign ordering
    - **Property 8: Past campaign ordering is deterministic**
    - File: `tests/test_part7_past_sort_property.py`
    - **Validates: Requirements 11.2, 11.12, 11.13**

  - [x] 16.5 Write unit tests for past campaigns
    - Inclusive duration (same day equals 1); weights sum to 100; Unavailable rendering; opt-in division guard; paging 5 then 10 and "View More" hidden at the end; reset on sort/filter change; default "Newest" with "Most Similar" disabled; missing-file errors; existing `predicted_vs_actual` tests still pass
    - File: `tests/test_part7_past_campaigns_unit.py`
    - _Requirements: 11.3, 11.5, 11.6, 11.7, 11.10, 11.16, 11.18_

  - [x] 16.6 Create `app/past_promos_page.py` and wire the tab
    - Sort and filter controls, 5-at-a-time list with "View More", detail view with eight-component horizontal bar chart (Unavailable labeled), "Not Enough Data" display, existing predicted-vs-actual content kept
    - Route the tab in `app/main.py`
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.12, 11.14, 11.15, 11.17, 11.20_

- [x] 17. Cross-cutting tests
  - [x] 17.1 Write the UI text rule test
    - Scan string constants and rendered text of new Part 7 modules for an em dash or `--`
    - File: `tests/test_part7_ui_text_unit.py`
    - _Requirements: 10.9, 9.11_

  - [x] 17.2 Write AppTest smoke tests
    - Extend the pattern in `tests/test_part5_personas_apptest_smoke.py` to open New Promo (both tabs), Results with a seeded run, Personas, What-If, Ask Assistant, and Past Promos with no AWS variables set; assert no exception
    - File: `tests/test_part7_apptest_smoke.py`
    - _Requirements: 1.9, 10.9_

- [ ] 18. Final verification and report
  - [x] 18.1 Run the full test suite and fix regressions
    - Run `./.venv/bin/python -m pytest tests` and record pass and fail counts
    - Leave the six existing Part 1 Hypothesis timeout failures unchanged; verify exactly 8 `@given` property tests exist in `tests/test_part7_*.py`
    - _Requirements: 10.1, 10.13_

  - [x] 18.2 Capture and verify the six screenshots
    - Start the app manually (long-running, run by the user): `PYTHONPATH=src ./.venv/bin/python -m streamlit run app/main.py`
    - Save screenshots to `scratch/`: New Promo "Upload Campaign File", New Promo "Fill In Details", Results, Personas, What-If, Ask Assistant
    - Fix any screen that errors or fails to render and recapture it
    - _Requirements: 10.10, 10.11_

  - [~] 18.3 Write the final report
    - Create `scratch/part7_report.md` listing modified files, assumptions, known limitations, updated existing tests, and test commands with pass/fail counts; note the open Poppins font question (font stack unchanged)
    - _Requirements: 10.12, 10.15_

  - [~] 18.4 Clean up temporary files
    - Remove temporary verification files under `scratch/` that are not deliverables (keep screenshots and the report)
    - _Requirements: scope note on temporary files_

- [~] 19. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Exactly 8 property tests exist (Properties 1 to 8); everything else is unit, example, edge, or integration
- `app/main.py` edits are serialized across waves because several tasks write to it
- Task 18.2 needs the user to run the Streamlit server; the agent should not start it in a blocking shell

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "4.2", "4.3", "6.1", "7.1", "8.1"] },
    { "id": 3, "tasks": ["6.2", "6.3", "6.4", "7.3", "8.2", "9.1", "13.1", "16.1"] },
    { "id": 4, "tasks": ["7.2", "8.3", "8.4", "9.2", "11.1", "12.1", "13.2", "13.3", "14.1", "16.2", "16.3"] },
    { "id": 5, "tasks": ["8.5", "11.2", "11.3", "12.2", "14.2", "16.4", "16.5"] },
    { "id": 6, "tasks": ["9.3", "11.4"] },
    { "id": 7, "tasks": ["12.3"] },
    { "id": 8, "tasks": ["12.4", "13.4"] },
    { "id": 9, "tasks": ["14.3"] },
    { "id": 10, "tasks": ["16.6"] },
    { "id": 11, "tasks": ["17.1", "17.2"] },
    { "id": 12, "tasks": ["18.1"] },
    { "id": 13, "tasks": ["18.2"] },
    { "id": 14, "tasks": ["18.3"] },
    { "id": 15, "tasks": ["18.4"] }
  ]
}
```
