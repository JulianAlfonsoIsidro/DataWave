# Implementation Plan: Part 9 Layout Fixes

## Overview

Part 9 is presentation only. This plan was written after the code on branch `part9-layout-fixes`, so tasks 1 to 12 are checked: they describe work already in the branch (commits `0de779a`, `59b6824`). Task 13 holds the follow-up work the code still lacks (tests and browser checks) and is unchecked.

Hard constraints for every task:

- Parts 1 to 4, `src/run_pipeline.py`, `outputs/`, `data/`, `labels.py` and `part5_personas` stay at zero changed lines.
- No `pip install`, no CDN, no runtime download.
- Existing widget keys and visible labels stay unchanged.
- New colour, duration and easing values live only in `app/styles.css` section 1.
- No Streamlit imports under `src/webapp_core/`.
- Preserve existing docstring requirement references.
- Per task, run only the affected tests plus `tests/test_part5_personas_apptest_smoke.py`, `tests/test_part5_theme.py` and `tests/test_part7_apptest_smoke.py`. The six Part 1 Hypothesis timeouts are excluded.

## Tasks

- [x] 1. Rename Part 8 files and wire both scripts
  - [x] 1.1 Rename `app/p8_effects.py` to `app/ui_effects.py` and `app/static/p8_page_lock.js` to `app/static/page_lock.js`; update imports, docstrings (`job_motion.py`, `toast_queue.py`) and `tests/test_part8_tokens_unit.py`
    - _Requirements: 17.1, 17.2, 19.3_
  - [x] 1.2 Inject `page_lock.js` and `ui_interactions.js` once from `ui_effects._draw_page_lock()` with `_page_lock_html(code, script_id)` and double-inject guards
    - _Requirements: 16.6, 17.3_

- [x] 2. Tokens and base look in `app/styles.css` section 1
  - [x] 2.1 Set the radius scale (4, 6, 8 px) and the textarea radius; add `--pan-control-h`
    - _Requirements: 11.2, 11.3_
  - [x] 2.2 Shorten finish and entrance durations; drop `--pan-dur-spark` from `--pan-reveal-start`
    - _Requirements: 16.1, 16.2_
  - [x] 2.3 Add Part 9 tokens: tip, theme fill, bubble, bounce, press-out, gold, thinking, constant ease, carousel, cube
    - _Requirements: 11.9_
  - [x] 2.4 Set `baseRadius` and `buttonRadius` to 6px in `.streamlit/config.toml`
    - _Requirements: 11.2_
  - [x] 2.5 Make the page background one flat colour (section 23); remove the wash, dot grid and lattice; make captions opaque
    - _Requirements: 11.1, 11.8_

- [x] 3. Header and navigation
  - [x] 3.1 Add `theme.run_header_html`, `_kpi_number_html` and `nav_state_html`; replace the hero in `main()`
    - _Requirements: 2.1 to 2.7_
  - [x] 3.2 Add `NAV_KEY`, `NAV_PENDING_KEY`, `go_to`, `_go_to_now` and `_nav_button`; build the tabs with `key=NAV_KEY, on_change="rerun"`
    - _Requirements: 3.1 to 3.4_
  - [x] 3.3 Land on Results after a successful Run Analysis; add the View Results, Go To New Promo, Build/View Personas and Try Another Threshold buttons; remove the "Next:" sentences they replace
    - _Requirements: 3.5 to 3.9_

- [x] 4. New Promo form
  - [x] 4.1 Put Fill In Details before Upload Campaign File (key `new_promo_mode`) with the upload panel still rendered first
    - _Requirements: 4.1, 4.2, 4.6_
  - [x] 4.2 Move the Promo ID under "Promo Basics"; add `MECHANIC_DISPLAY` and use it in the selectbox and the assistant
    - _Requirements: 4.3, 4.4_
  - [x] 4.3 Add the threshold-changed banner above the sub-tabs
    - _Requirements: 4.5_

- [x] 5. Results page
  - [x] 5.1 Add the threshold helpers `_current_threshold`, `_as_run_threshold`, `_threshold_context`, `_threshold_slug`, `_request_threshold_reset`
    - _Requirements: 5.2, 6.5_
  - [x] 5.2 Add `_render_threshold_context` and `_render_results_actions`; move Export Summary into the action bar
    - _Requirements: 5.1 to 5.3_
  - [x] 5.3 Replace the red emphasis tile with `RECOMMENDED_ACTION`, `ACTION_ORDER`, `_action_rank`, `act_first_tag_html`, `tile_html`, `results_grid_html` and `GRID_AXIS_LABELS`
    - _Requirements: 5.4 to 5.6_
  - [x] 5.4 Restyle cards: muted promo-id prefix, `_stat_parts` key/value stats, "Targeting Details" disclosure, `decision_card_split_body_html`, single personas caption
    - _Requirements: 5.7 to 5.10_
  - [x] 5.5 Limit `theme.counting` to the header and the grid
    - _Requirements: 5.11_
  - [x] 5.6 Replace the two-up download buttons with `_render_download_row`, `_download_cell`, `DOWNLOAD_NOTE`; add the threshold to file names
    - _Requirements: 6.1 to 6.6_

- [x] 6. What-If page
  - [x] 6.1 Add `WHATIF_BASELINE_KEY`, `WHATIF_SEGMENTS_KEY`, `WHATIF_RESET_KEY`, `WHATIF_RESET_COUNT_KEY`, `_segment_figures`; save the baseline after a successful run
    - _Requirements: 7.9_
  - [x] 6.2 Add `theme.whatif_change_html`, `_delta_text` and `whatif_segments_html`; add `_render_whatif_segments`
    - _Requirements: 7.1 to 7.3_
  - [x] 6.3 Rewrite `_run_rescore` with no page lock, loader or finish; plain readout in a reusable slot; thinking dots while rescoring; failure handling
    - _Requirements: 7.4 to 7.7_
  - [x] 6.4 Add the Reset button on Results and What-If, and the fresh slider key after a reset
    - _Requirements: 7.8_

- [x] 7. Personas page
  - [x] 7.1 Remove the "How the Personas Differ" table call; add the Segment selector (`persona_ej_segment`) and the full-width split card
    - _Requirements: 8.1 to 8.3_
  - [x] 7.2 Pluralise the success message; give `theme.loading` a `slot` parameter and reserve slots for Suggest and Build Personas
    - _Requirements: 8.4, 8.5_

- [x] 8. Past Promos and Ask Assistant
  - [x] 8.1 Add `gap_text` and the Gap column, `unavailable_line_html`, `fields_row_html`, the "(Similarity Score: N)" label and the two similarity captions
    - _Requirements: 9.1 to 9.4, 9.6_
  - [x] 8.2 Add `_cached_past_data(stamps)` keyed on file modified times
    - _Requirements: 9.5_
  - [x] 8.3 Add `bedrock_html` and `thinking_html`; rewrite `_handle_question` around the `thread` container; add `_finish_seconds`; read the threshold from the Run in `build_grounding`
    - _Requirements: 10.1 to 10.5_
  - [x] 8.4 Style suggested questions and chat width
    - _Requirements: 10.6, 10.7_

- [x] 9. Buttons and tooltips
  - [x] 9.1 CSS section 27: neutral rest, hover gate, red `data-p9-pressed`, press-out fade, Reduced_Motion
    - _Requirements: 12.1 to 12.4, 12.8, 12.9, 12.12_
  - [x] 9.2 `ui_interactions.js` part 4: pressed-button tracking and polling; hide the stale Job button copy in CSS
    - _Requirements: 12.5 to 12.7, 12.10, 12.11_
  - [x] 9.3 CSS section 20 and `ui_interactions.js` part 2: hover texts that a click cannot pin, with a fade-out; keep tips on screen at 390 px
    - _Requirements: 13.1 to 13.3_

- [x] 10. Theme switch and narrow screens
  - [x] 10.1 CSS section 21 and `ui_interactions.js` part 1: the liquid theme switch with its skip rules
    - _Requirements: 14.1 to 14.7_
  - [x] 10.2 `ui_interactions.js` part 3 and the 900px CSS: hide the top-right menu while scrolling down
    - _Requirements: 15.1 to 15.3_

- [x] 11. Job timing and carousel
  - [x] 11.1 Add `awaitRun()` and `p9-await-run` to `page_lock.js`
    - _Requirements: 16.3, 16.4_
  - [x] 11.2 Rebuild the ring as a 3D carousel in `picker.css` and `picker.js`; add `--pan-dur-carousel` and `--pan-ease-carousel` to `_EXTRA_TOKENS` in `group_picker.py`
    - _Requirements: 16.5_

- [x] 12. Backend and tests
  - [x] 12.1 Pass `aws_session_token` to the Bedrock client; add `win_ca.pem`
    - _Requirements: 17.4, 18.1, 18.2_
  - [x] 12.2 Update the three smoke and token tests for the restyle
    - _Requirements: 19.1 to 19.3_

- [ ] 13. Follow-up (not in the branch yet)
  - [ ]* 13.1 Write unit tests for the pure helpers: `_action_rank`, `_threshold_slug`, `_leads_file_name`, `_segment_figures`, `gap_text`, `_delta_text`
    - Create `tests/test_part9_helpers_unit.py`; import `main.py` helpers carefully, since the module runs `main()` on import (consider moving the pure helpers to `webapp_core` first)
    - _Requirements: 19.4_
  - [ ]* 13.2 Write unit tests for the HTML builders: `run_header_html`, `whatif_change_html`, `whatif_segments_html`, `results_grid_html`, `bedrock_html`, `thinking_html`
    - Check the empty-run header keeps `is-empty` and `aria-hidden`; check the three What-If figure cases; check the six cube faces and six sparks only in `finish`
    - _Requirements: 19.4_
  - [ ]* 13.3 Extend `tests/test_part8_tokens_unit.py` to scan `ui_interactions.js` for hex colours and hardcoded durations
    - _Requirements: 11.9_
  - [ ] 13.4 Browser checklist (record results in the Change_Report)
    - Theme switch both ways, with and without Reduced_Motion
    - Tooltip click versus keyboard focus
    - Menu hide under 900 px
    - Pressed-button red and fade on Run Analysis, Build Personas and a plain button
    - No sideways scroll at 390 px
    - Dark-mode contrast of the new surfaces and the dimmed map areas
    - Rapid arrow presses on the carousel
    - _Requirements: 11.11, 12.5 to 12.8, 13.3, 14.2 to 14.6, 15.1_
  - [ ] 13.5 Decide whether to remove the unused hero code: `.pan-hero*` and `--pan-hero-*`/`--pan-dot` in `styles.css`, and `hero_kpi_html`, `hero_text_html`, `metric_panel` in `theme.py`. The rules still exist; check callers and `tests/test_part5_theme.py` first
    - _Requirements: 2.2_

- [ ] 14. Pending owner decisions (no work until the owner decides)
  - [x] 14.1 Decided (round 2, fix 1): Expected Joiners show a rounded whole number with `(Forecasted: 87.3)` beside it. Work is in task 16.1. Before this, the Header was whole (204), a grid tile showed 87.3, and a card said "About 87"
    - _Requirements: 20, Number definitions 2, 6_
  - [x] 14.2 Decided (round 2, fix 3): add the linking captions, for example "Luzon · 376 of 1,595 sendable leads" above persona groups and "about 87 of the 282 sendable leads are expected to join" on the recommended download. Work is in task 16.3
    - _Requirements: 22, Number definitions 1 to 5, 5.3_
  - [ ] 14.3 Decide whether to remove the unused hero code (same item as task 13.5)
    - _Requirements: 2.2_
  - [ ] 14.4 Decide how to fix the failing `tests/test_part7_ui_text_unit.py` case for `app/theme.py`. Per the owner it is a pre-existing failure (not re-run here). The test strips `--pan-*` names before it looks for `--`, but a CSS custom-property name such as `--loader-accent` in a `theme.py` string is reported as a double hyphen
    - _Requirements: 19.4_
  - [ ] 14.5 Decide whether to untrack the 32 committed `__pycache__` files (`git rm --cached`); `.gitignore` already lists `__pycache__/`
    - _Requirements: none (repository hygiene)_
  - [x] 14.6 Confirmed by the reference image: round 2 fix 7 is button-label padding (built in 16.7). Original note: Confirm how to read round 2 fix 7. It is built as horizontal padding on every button label, because the reference image shows the "Suggest a number" label touching both borders. Say so if wider page gutters were meant instead
    - _Requirements: 26_
  - [x] 14.7 Built as a collapsible section (`st.expander`, 16.6). Original note: Confirm that "dropdown" in round 2 fix 6 means a collapsible section (`st.expander`) and not a segment selector
    - _Requirements: 25_

- [x] 15. Later changes that corrected the first version of this spec
  - [x] 15.1 Buttons: neutral at rest for every button including Download Recommended Leads; ink outline and red key edge for the main action; press turns red, sinks and springs back; red stays until the work is done, then fades over `--pan-dur-press-out`; the busy check ignores `.pan-loading`; descendant selectors for tooltip wrappers
    - _Requirements: 12.1 to 12.12_
  - [x] 15.2 Stepper: four plain grey numbered circles, only the current one filled red; no "done" check mark or dashed circle; `pan-nav-state` still emitted but unread by CSS
    - _Requirements: 2.6, 3.10 to 3.14_
  - [x] 15.3 Header: wordmark at `--pan-type-section-size` (24 px)
    - _Requirements: 2.7_
  - [x] 15.4 Page width: content stays centred at 1200 px; the full-width layout (1680 px) was built and reverted
    - _Requirements: 11.12_
  - [x] 15.5 Theme switch: bubbling-liquid overlay (`.p9-liquid`, `#p9-blob`, 48 bubbles), not a View Transition
    - _Requirements: 15.1 to 14.7_
  - [x] 15.6 Carousel: each card faces the viewer; one CSS transition on the registered property `--a`; `S.pos` never wrapped
    - _Requirements: 16.5_
  - [x] 15.7 Background: flat; the woven lattice and sparkles removed; section 23 holds only `--pan-cube-tex`
    - _Requirements: 11.1, 11.10_
  - [x] 15.8 Spec: add the Decisions log and Rejected options to the design document, and the Number definitions to the requirements
    - _Requirements: Number definitions_

- [x] 16. Round 2 fixes (built 2026-11-13)
  - [x] 16.1 Rounded joiners with the forecast
    - Add `src/webapp_core/number_format.py` (`shown_joiners`, `forecast_text`, `share_pct`) reusing `card_view.round_half_up`
    - Add `theme.joiners_pair_html` and use it in the Header, Results Grid tile (`_tile_body_html`), What-If headline and What-If segment table; make the What-If Change figure the difference of the shown whole numbers
    - Use `round_half_up` for the Decision Card "About N Likely To Join" figure
    - Rename the What-If column to "Expected Joiners (Forecast)" and use the short `(87.3)` bracket in cells
    - _Requirements: 20.1 to 20.11_
  - [x] 16.2 Header sub-line
    - Pass the Forecast and the Sendable_Total into `run_header_html`; draw `out of 1,595 sendable leads (12.8%)`; handle 0 sendable leads and the empty-run slot; add the tooltip
    - Add `--pan-help-clearance` and widen the `.pan-shell` right padding
    - _Requirements: 21.1 to 21.8_
  - [x] 16.3 Plain descriptions
    - Add `src/webapp_core/number_help.py` with one function per figure in the Requirement 22 table, reading `CONTROL_FRACTION`, `VALUE_PER_JOIN_PHP` and `Z_90` from `part4_cards.config`
    - Add the captions and hover texts on Results (tiles, Download Leads cells, Impact Summary), What-If, New Promo (Minimum ADB), Personas (`<group> · N of M sendable leads`) and Past Promos (Predicted, Actual, Gap, Similarity Score)
    - Add the caption `about 87 of the 282 sendable leads are expected to join` under Download Recommended Leads
    - Reword `VALUE_TOOLTIP` in `card_view.py`; update any `test_part7_card_view_*` expectation it changes and list each change
    - _Requirements: 22.1 to 22.6_
  - [x] 16.4 Title
    - Set `APP_TITLE` and `page_title` to "Promo Audience Manager"; update the docstrings and comments in Requirement 23.5
    - Update `test_part5_theme.py` and `test_part8_assets_unit.py` and list each change
    - _Requirements: 23.1 to 23.7_
  - [x] 16.5 What-If segment order
    - Add `SEGMENT_DISPLAY_ORDER` in `segment_flow.py`; sort `_render_whatif_segments` by it
    - _Requirements: 24.1 to 24.4_
  - [x] 16.6 Download Leads dropdown
    - Wrap the rows and captions in `st.expander("Download Leads (N files)", expanded=False)`; keep every key; share the disclosure summary style
    - Update `test_part7_apptest_smoke.py` (the subheader list)
    - _Requirements: 25.1 to 25.6_
  - [x] 16.7 Button label space
    - Add `padding-inline: var(--pan-space-4)`, centred text and wrapping to section 27; check the tertiary "Suggest a number" button, Run Analysis, Build Personas, nav, download and suggested-question buttons
    - _Requirements: 26.1 to 26.6_
  - [x] 16.8 Segment Flow chart
    - Add `src/webapp_core/segment_flow.py` (`FlowRow`, `flow_rows`, `flow_total`, `reconciles`)
    - Add `--pan-flow-sendable`, `--pan-flow-control`, `--pan-flow-excluded` to section 1
    - Add `theme.segment_flow_html` and the `.pan-flow-*` CSS (legend, bars, thin minimum part, in-bar numbers, Total row, table, caption, reveal on a new Run, Reduced_Motion)
    - Draw the block under the Impact Summary in `_render_results_tab`
    - _Requirements: 27.1 to 27.14_
  - [x] 16.9 Help And FAQs
    - Add `src/webapp_core/help_content.py` (entries, formulas, config constants) and `app/help_page.py` (`st.dialog`)
    - Add the `help_open` button in `main()`, the `.st-key-pan_help` and dialog CSS (section 28), and the narrow-screen rule
    - _Requirements: 28.1 to 28.16_

- [ ] 17. Tests for round 2 (17.1 to 17.3 written in `tests/test_part9_round2_unit.py` and the smoke tests)
  - [x]* 17.1 Property tests for `number_format` and `segment_flow` (rounding within 0.5, one decimal, no division by zero, parts add to Clients, stable order)
    - _Requirements: 20, 21, 24, 27_
  - [x]* 17.2 Unit tests for `joiners_pair_html`, `run_header_html`, `whatif_segments_html`, `segment_flow_html`, `number_help` and `help_content`
    - _Requirements: 20 to 22, 27, 28_
  - [x]* 17.3 AppTest smoke: Results shows the Download Leads expander, the flow heading and the `help_open` button; the title is "Promo Audience Manager"
    - _Requirements: 23, 25, 27, 28_
  - [ ] 17.4 Run the Part 9 affected set: `test_part5_theme`, `test_part5_personas_apptest_smoke`, `test_part7_apptest_smoke`, every `tests/test_part8_*_unit.py`, and the new tests
    - _Requirements: 19_

- [ ] 18. Browser checks for round 2 (open)
  - [ ] 18.1 Header: whole number, bracket, sub-line, percentage, zero-sendable case, light and dark, 390 px
    - _Requirements: 20, 21_
  - [ ] 18.2 Segment Flow: colours and in-bar text contrast in light and dark, small segments still visible, reveal once, Reduced_Motion, screen reader reads the table
    - _Requirements: 27_
  - [ ] 18.3 Help dialog: opens from the button, Esc and Tab behave, New Promo form values survive open and close, theme in light and dark, narrow screens
    - _Requirements: 28_
  - [ ] 18.4 Button padding on every button type, a long label at 390 px
    - _Requirements: 26_
  - [ ] 18.5 Download Leads dropdown opens and closes, files download with the threshold in their names
    - _Requirements: 25_
## Round 2 build notes (2026-11-13)

- Built: `webapp_core/number_format.py`, `segment_flow.py`, `number_help.py`, `help_content.py`, `app/help_page.py`; `theme.joiners_pair_html`, `segment_flow_html`, header sub-line, What-If cells; CSS section 28; `ui_interactions.js` part 5.
- Found while building: Streamlit draws `st.dialog` outside the app root, where the app's colour scheme does not reach, so the dialog showed light in dark mode. `ui_interactions.js` part 5 copies the scheme to `html[data-p9-scheme]` and section 28 sets `color-scheme` from it.
- Found while building: the Segment Flow table is wider than 390 px; it scrolls inside its own box (`.pan-flow-scroll`) so the page never scrolls sideways.
- Found while building: under 640 px the header stacks (wordmark, then the number block) so the wordmark is not squeezed by the two fixed buttons.
- Download Leads dropdown label uses the section heading size (not caption size) so a closed dropdown still reads as a section; it keeps the disclosure look otherwise (no box). A deviation from 25.4's "caption size", for visibility.
- The persona group caption says "sendable leads" only when the build used the current run's sendable leads (new session key `persona_pool_sendable`); otherwise "leads".
- Test expectations changed (each listed): `test_part5_theme.py` and `test_part8_assets_unit.py` (title); `test_part7_apptest_smoke.py` (Download Leads is an expander, the flow heading, the `help_open` button); `test_part5_personas_apptest_smoke.py` (group heading is `pan-group-head`, not `**Segment: X**`).
- Owner follow-up (2026-11-13): each formula in Help And FAQs is its own card (bold name, the equation in an inner box set in `--pan-font-math`, a Cambria Math stack added to `theme.FONT_STACKS`, and a short muted note). `help_content.FORMULAS` is now `HelpFormula(name, equation, note)`. The Common Questions were reworded to name the tab, section and figure they are about (for example "On the Results tab, why are the sendable leads fewer than the total clients in each segment?"), and a question about Download Recommended Leads was added (17 in total). Requirement 28.9's list is the topic list; the wording on screen follows this note.
- Owner follow-up 2 (2026-11-13):
  - Header: the forecast bracket is removed from the Header only (it stays on the grid, What-If and tables); the label, number and "out of N sendable leads (pct)" line are one right-aligned stack (left-aligned under 640 px). Supersedes Requirement 20.3 for the Header.
  - Segment Flow: a "Segment" dropdown (key `pan_flow_segment`, display order, "All Segments" last) shows one stacked bar for the chosen segment, with each part's count and share inside the bar and in a legend under it. The separate table is removed. Supersedes Requirement 27.2, 27.4 and 27.7 to 27.8.
  - Help: a page section, tab or button named in a question, answer or "Where to see it" line is written `[[Name]]` in `help_content` and shown bold in quotes (`help_page.marked_html` / `marked_md`). Answers get room under "Where to see it" (Streamlit's negative markdown margin is reset inside the dialog).
  - Download Leads dropdown: its label style no longer resets the font of the icon span, which made the arrow show as the text "keyboard_arrow_right".
