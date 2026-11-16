# Requirements Document

## Introduction

Part 9 is a layout, clarity and polish pass over the DataWave Promo Audience Manager (the Streamlit webapp in `app/`; it was called Promo Audience Navigator until Requirement 23).

Requirements 1 to 19 describe what is already in the branch. Requirements 20 to 28 are a second round of fixes that are specified here and not yet built. Their tasks are open in `tasks.md` (task 16). It was written after the code on branch `part9-layout-fixes` (commits `0de779a` and `59b6824`, on top of Part 8 at `207d6a3`), so each requirement describes behavior that exists in that code. It does not change the Part 1 to 4 pipeline, the fitted model, or any calculation.

Guiding principles taken from the code:

- Guide the user along one path: design a promo, read the answer, test a threshold, build personas.
- Say each thing once. A figure, a note or a hint is not repeated in several places.
- Flat and calm. One flat page colour, one tight radius scale, no side bars, no red slabs. Red marks a risk, an error or a pressed button.
- Motion is short and earns its place. A run finishes in about 1.15 s with no fireworks. A slider move does not lock the page.

## Glossary

- **Header**: the slim page header with the wordmark and, once a run exists, the one large Expected Joiners number (`theme.run_header_html`).
- **Section**: one of the six top-level tabs in `theme.TAB_LABELS`: New Promo, Results, What-If, Personas, Past Promos, Ask Assistant.
- **Run**: the `RunResult` stored in `st.session_state["run_result"]` by Run Analysis or by a What-If rescore.
- **As_Run_Threshold**: the threshold New Promo ran, stored in `WHATIF_BASELINE_KEY` as `(expected joiners, label, type name, value)`.
- **Current_Threshold**: the threshold the Run was last scored at (New Promo or What-If).
- **Recommended_Segment**: a segment whose card action is `Prioritize`. It carries the "Act first" tag.
- **Action_Order**: `Prioritize`, `Offer lower tier`, `Include`, `Skip`, then more expected joiners first.
- **Job**: Run Analysis or Build Personas. A Job shows the loader and locks the page. A What-If slider rescore is not a Job.
- **Pressed_State**: the `data-p9-pressed` attribute set on a clicked button until its work is done.
- **Reduced_Motion**: `prefers-reduced-motion: reduce`.
- **Token**: a CSS custom property in `app/styles.css` section 1.
- **Forecast, Shown_Joiners, Sendable_Total, Segment_Flow, Help_Dialog, Display_Order**: defined at the start of the Round 2 requirements.

## Requirements

### Requirement 1: Scope and constraints

**User Story:** As the team lead, I want Part 9 to change presentation only, so that model results stay the same.

#### Acceptance Criteria

1. THE Part 9 changes SHALL leave Parts 1 to 4, `src/run_pipeline.py`, `outputs/` and `data/` unchanged.
2. THE Part 9 changes SHALL leave every calculation, the `labels.py` wording, and the `part5_personas` clustering unchanged.
3. THE existing widget keys SHALL stay unchanged. New keys SHALL be listed in the design document.
4. THE app SHALL work without a CDN, a build step or a runtime download.
5. THE only backend change SHALL be `aws_session_token` passed to the Bedrock client when `AWS_SESSION_TOKEN` is set (Requirement 18).

### Requirement 2: Header

**User Story:** As a planner, I want a quiet header that shows the current run's one number, so that I know where I am without a hero banner.

#### Acceptance Criteria

1. THE page SHALL show a `<header class="pan-shell">` holding the wordmark `Promo Audience Manager` (Requirement 23) as an `h1`.
2. THE hero columns, the hero text and the "Current Run" banner SHALL no longer be drawn on the page. `hero_kpi_html` and `hero_text_html` MAY remain in `theme.py` as helpers.
3. WHEN a Run exists, THE Header SHALL show Expected Joiners as one large number with its label, and SHALL NOT repeat the promo id, product, threshold or segment count.
4. WHEN no Run exists, THE Header SHALL keep the number slot, hidden with `aria-hidden="true"`, so the Header does not grow when the number first appears.
5. AFTER a successful Run Analysis, THE Header number SHALL count up once. On a later change it SHALL roll from the last shown value. On an unrelated rerun it SHALL be static.
6. THE page SHALL still emit a hidden `div.pan-nav-state` with `has-run` or `no-run`, plus `has-personas` when personas exist. Its container SHALL take no row (`display: none`). NO CSS rule SHALL read its classes for step states.
7. THE wordmark `h1.pan-wordmark` SHALL use `--pan-type-section-size` (24 px), one step larger than the earlier card-title size, in the heading font, bold, with a line height of `--pan-control-h`.

### Requirement 3: Navigation

**User Story:** As a planner, I want to move between sections with clear next steps, so that I never wonder what to do next.

#### Acceptance Criteria

1. THE six Sections SHALL stay as `st.tabs(theme.TAB_LABELS, key="main_nav", on_change="rerun")`, in the order New Promo, Results, What-If, Personas, Past Promos, Ask Assistant.
2. THE function `go_to(label)` SHALL store the label in `main_nav_pending`. At the start of the next render, before the tabs are created, THE app SHALL move it to `main_nav` when it is in `TAB_LABELS`.
3. THE callback `_go_to_now(label)` SHALL set `main_nav` directly, for use as a button `on_click`.
4. THE helper `_nav_button(label, section, key, primary=False)` SHALL draw a secondary button by default and a primary button only when asked.
5. WHEN a Run Analysis Job succeeds, THE app SHALL open the Results Section.
6. WHEN a Run exists, THE New Promo Section SHALL show a "View Results" button (key `nav_newpromo_results`).
7. WHEN no Run exists, THE Results and What-If Sections SHALL show their existing info message and a "Go To New Promo" button (keys `nav_results_empty`, `nav_whatif_empty`).
8. THE Results Section SHALL end with two buttons in a horizontal container `pan_next_actions`: "Build Personas" (primary) or "View Personas" (secondary) when personas exist, and "Try Another Threshold". These replace the earlier "Next:" sentence.
9. THE What-If Section SHALL end with a "View Results" button (key `nav_whatif_results`) in the container `pan_whatif_actions`, replacing its "Next:" sentence.
10. THE first four tabs (New Promo, Results, What-If, Personas) SHALL show a number from 1 to 4, counted by CSS. The tab labels SHALL stay exactly as written.
11. EVERY step number SHALL be a plain grey circle (20 px, 1 px `--pan-border-control` outline, muted number). ONLY the current tab's circle SHALL be filled red, with an `--pan-on-primary` number, and the current tab SHALL have a 2 px red rule on the tab-list divider.
12. THE stepper SHALL NOT show a "done" check mark or a dashed "needs a run first" circle. These states were removed on request.
13. Past Promos and Ask Assistant SHALL carry no number and SHALL be set apart on the right (`margin-left: auto` from the fifth tab).
14. WHEN the six tabs do not fit, THEY SHALL wrap to a second row. THE tab scroll arrows SHALL be hidden.

### Requirement 4: New Promo form

**User Story:** As a planner, I want the form to read in a natural order, so that I can fill it in quickly.

#### Acceptance Criteria

1. THE New Promo Section SHALL show two sub-tabs, "Fill In Details" first and "Upload Campaign File" second (key `new_promo_mode`).
2. THE upload panel SHALL still be rendered before the form widgets in the same script run, so its prefill reaches session state first (Part 7 Requirement 2.9).
3. THE Promo ID field SHALL sit under the "Promo Basics" section label, in a half-width column.
4. THE Mechanic selector SHALL show Top Up, New Account, ADB Increase and Other, while the stored value stays the code (`TOP_UP`, `NEW_ACCOUNT`, `ADB_INCREASE`, `OTHER`). THE assistant SHALL use the same display names.
5. WHEN a Run exists and its Current_Threshold differs from the As_Run_Threshold by at least half a slider step, THE New Promo Section SHALL show a banner saying the active results use the Current_Threshold and that Run Analysis uses the form.
6. THE form SHALL be at most 840 px wide for the sub-tab group.

### Requirement 5: Results page

**User Story:** As a planner, I want Results to tell me which threshold I am looking at and which segment to act on first, so that I can decide and send.

#### Acceptance Criteria

1. THE Results Section SHALL open with the threshold context, then an action bar, then the Results Grid, the Impact Summary, the Segment Flow chart (Requirement 27), the Decision Cards and the Download Leads dropdown (Requirement 25).
2. WHEN the Current_Threshold differs from the As_Run_Threshold by at least half a step, THE threshold context SHALL be an info banner stating that results and lead files use the Current_Threshold and what was run, plus a "Reset To <as-run>" button (key `whatif_reset_results`). OTHERWISE it SHALL be a caption "Threshold <label>, as run." (or "Threshold <label>." with no As_Run_Threshold).
3. THE action bar (container `pan_results_actions`) SHALL hold a primary "Download Recommended Leads (n)" button (key `download_leads_recommended`) and the Export Summary download. THE Export Summary SHALL have no heading of its own.
4. THE Recommended_Segment set SHALL be every segment whose card action is `Prioritize`. No tile SHALL be drawn as a red slab.
5. THE Results Grid SHALL be one labelled 2x2 (`.pan-grid`, `role="group"`): columns Low Capacity and High Capacity, rows High Score and Low Score. Every tile SHALL look the same except a Recommended_Segment, which gets a primary edge and an "Act first" tag.
6. THE Decision Cards and the Download Leads rows SHALL follow the Action_Order.
7. A Decision Card heading of the form `<promo id> · <segment>` SHALL show the promo id small and muted so the segment name leads.
8. EACH Decision Card SHALL show stats, Action, Dominant Channel and Message Angle first. THE drivers and the not-contacted reasons SHALL sit in a "Targeting Details" disclosure.
9. A stat label of the form `Key: value` or `About N Key` SHALL render as the key over the value, with the words unchanged.
10. WHEN no personas exist, THE Results Section SHALL show one caption above the cards ("Personas were not generated for this run...") and the cards SHALL NOT repeat it.
11. ONLY the Header and the Results Grid numbers SHALL count up after a run. THE Impact Summary and the Decision Cards SHALL show final numbers.

### Requirement 6: Download Leads

**User Story:** As a planner, I want each lead file to say what it was cut at, so that I can tell saved files apart.

#### Acceptance Criteria

1. THE Download Leads dropdown (Requirement 25) SHALL show one row per segment in container `pan_dl_row_<i>`: segment marker and name, an "Act first" tag when recommended, the card action (or "Not set"), then Clients, Not Contacted, Control Group, Sendable and a download button.
2. THE Not Contacted cell SHALL show the sum of `excluded_by_reason` and one plain reason line per reason, using the same labels as the Decision Card.
3. THE download button SHALL be labelled "Download <n> Leads", keep the key `download_leads_<segment>`, and be full width.
4. A segment file SHALL be named `<promo_id>_<threshold slug>_<segment_snake>_leads.csv`. THE recommended file SHALL be named `<promo_id>_<threshold slug>_recommended_leads.csv`.
5. THE threshold slug SHALL be the digits of the threshold label, followed by `pct` when the label contains `%`.
6. A caption `DOWNLOAD_NOTE` SHALL explain which clients the files leave out.

### Requirement 7: What-If page

**User Story:** As a planner, I want to move the slider and see the change from my run, so that I can pick a threshold without waiting on a loader.

#### Acceptance Criteria

1. THE What-If headline SHALL show, in plain figures: "As Run, At <base>", "At <now>" and "Change", where Change is a signed number with an up or down arrow, or "No change". At the as-run threshold it SHALL show "At <now> (as run)" only. With no baseline it SHALL show "At <now>".
2. THE What-If headline SHALL replace the second red KPI panel.
3. THE What-If Section SHALL show a per-segment table (Segment, Clients, Expected Joiners, Sendable). Expected Joiners SHALL be rounded with the forecast beside it (Requirement 20). Each cell SHALL show the change from the run only when the threshold differs from the As_Run_Threshold. Segments SHALL follow the order in Requirement 24.
4. A slider move SHALL NOT lock the page, draw the loader overlay or play a finish animation. WHILE it rescores, THE readout slot SHALL say "Rescoring at <value>" with the thinking dots.
5. THE threshold readout SHALL be plain text with no digit roll.
6. WHEN the rescore succeeds, THE app SHALL rerun and the headline number SHALL roll to its new value. WHEN it fails, THE result SHALL stay unchanged and its messages SHALL show without a rerun.
7. THE What-If flash SHALL keep only warnings and errors. THE New Promo success line SHALL NOT appear.
8. A Reset button (here or on Results) SHALL rescore at the As_Run_Threshold. THE slider SHALL then use a fresh key (`whatif_threshold_<TYPE>_r<n>`, counter `whatif_reset_count`) so the browser starts it from the result.
9. WHEN the baseline is saved, THE app SHALL store `WHATIF_BASELINE_KEY` and `WHATIF_SEGMENTS_KEY` (`{segment: (clients, expected joiners, sendable)}`) and clear `WHATIF_RESET_KEY`.

### Requirement 8: Personas page

**User Story:** As a planner, I want the persona breakdown for one segment at a time, so that the page is not a wall of cards.

#### Acceptance Criteria

1. THE "How the Personas Differ" heading and table SHALL no longer be rendered. The render function MAY remain defined.
2. WHEN there are two or more segments, THE page SHALL show a half-width "Segment" selector (key `persona_ej_segment`) ordered Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now, defaulting to the first. A stored value that is no longer valid SHALL reset to the first.
3. WHEN a single card remains and the mode is not "all", THE card SHALL be full width, split into guidance on the left and the persona breakdown on the right, stacking under 760 px.
4. THE Build Personas success message SHALL pluralise: "Built <n> personas across <k> group" or "groups".
5. THE Suggest loader SHALL draw into a slot reserved by the page, and the Build Personas loader SHALL use a slot drawn on every render, so starting a Job adds no element, nothing shifts, and no stale second "Build Personas" button appears.

### Requirement 9: Past Promos page

**User Story:** As a planner, I want past-promo gaps and similarity shown honestly, so that a missing value never reads as zero.

#### Acceptance Criteria

1. THE predicted-versus-actual table SHALL have a Gap column: actual minus predicted in points (`+1.2 pts`, `−0.4 pts`, `0.0 pts` under 0.05), or "No Leads" when either value is missing.
2. A similarity component that is unavailable SHALL render as a line "<name>: Unavailable" with no bar.
3. THE campaign facts SHALL render in one wrapping row.
4. A similarity row label SHALL read "(Similarity Score: N)".
5. THE past-promo data SHALL be loaded through a cache keyed on the modified times of `promo_history.csv`, `promo_leads.csv` and `customer_dna.csv`, because every tab switch now reruns the app.
6. WHEN Most Similar is available, THE page SHALL explain what it compares with: the New Promo form before a run, or the current run and its threshold after one.

### Requirement 10: Ask Assistant page

**User Story:** As a planner, I want the assistant to look and feel finished while it works, so that waiting is clear.

#### Acceptance Criteria

1. THE assistant avatar SHALL be a small CSS 3D stone block (`theme.bedrock_html`) in three states: `spin` while thinking, `finish` when the answer is ready (spin up, hop, land, wobble, a few sparks), and `rest` on every answer. The user avatar SHALL be gold.
2. THE waiting line SHALL be "Thinking" with three pulsing dots (`theme.thinking_html`, `role="status"`), replacing `st.spinner`.
3. THE question and answer SHALL be drawn into a thread container created before the input, so they stay above the box.
4. THE finish state SHALL last `--pan-dur-cube-finish` (900 ms fallback).
5. ONCE a Run exists, THE grounding SHALL take the threshold type and value from the Run's promo spec, not from the New Promo slider, because What-If changes the Run.
6. THE suggested-question buttons SHALL be outlined, equal in height across a row, and wrap their text. Chat replies SHALL be at most 72 characters wide.
7. WITH Reduced_Motion on, THE block SHALL breathe instead of spinning, and the dots SHALL fade instead of pulse.

### Requirement 11: Visual system

**User Story:** As a designer, I want one flat, consistent look, so that the app feels calm and trustworthy.

#### Acceptance Criteria

1. THE page background SHALL be the flat `--pan-bg` token only (charcoal in dark mode). The wash, dot grid, woven red lattice and its sparkles SHALL be removed.
2. THE radius scale SHALL be `--pan-radius-sm` 4 px (tags, tabs, tooltips), `--pan-radius-md` 6 px (every control and note) and `--pan-radius-lg` 8 px (cards). A pill SHALL be used only for chips and dots. THE text area radius SHALL equal `--pan-radius-md`. `.streamlit/config.toml` `baseRadius` and `buttonRadius` SHALL be 6 px.
3. TABS, inputs and buttons SHALL share one height, `--pan-control-h` (40 px).
4. NO note SHALL have a 3 px side bar. NO section label SHALL have a red dash. NO tile SHALL be a red slab.
5. RED SHALL mark a risk, an error or a pressed button. THE actual figure in a table SHALL be stressed by weight, not red. Series bars SHALL use `--pan-series-2`.
6. FOCUS rings SHALL be blue, not red.
7. TABLES SHALL use horizontal hairlines only.
8. CAPTIONS SHALL be fully opaque so they keep contrast.
9. EVERY new colour, duration and easing SHALL be a Token in section 1. Section 1 SHALL stay the only place with hex values.
10. THE Part 9 CSS SHALL be in sections 20 (hover texts), 21 (theme switch), 22 (assistant thinking), 24 (assistant avatars), 25 (round 3 fixes), 27 (buttons) and 23, plus the header, grid, What-If, download row, disclosure and split-card rules. Section 23 SHALL hold only the stone block texture (`--pan-cube-tex`).
11. THE main area SHALL NOT scroll sideways at 390 px.
12. THE page content SHALL stay centred at a maximum width of 1200 px (`.block-container`). A full-width layout SHALL NOT be used (see the rejected option in the design document).

### Requirement 12: Buttons

**User Story:** As a planner, I want buttons that stay quiet until I press them and then show that the app is working, so that I know the app heard me.

#### Acceptance Criteria

1. EVERY `st.button`, `st.download_button` and `st.form_submit_button` SHALL rest neutral: the page surface (`--pan-surface`), an ink label, a 1 px grey hairline (`--pan-border-control`) and a 2 px key edge (`--pan-border`) under it. NO button SHALL have a red fill at rest, including Download Recommended Leads.
2. THE main action of an area SHALL be marked only by an ink outline and a red key edge (`--pan-primary`), not by a fill. This applies to primary buttons and to the Job buttons Run Analysis and Build Personas (`st-key-p8_btn_*`).
3. ON hover a button SHALL lift 1 px and take an ink border. Hover styling SHALL apply only under `(hover: hover) and (pointer: fine)`. Job buttons SHALL drop their red hover plate.
4. WHILE a button is active (pressed), IT SHALL turn red at once, sink (2 px down, scale 0.96) and lose its key edge. ON release it SHALL spring back over `--pan-dur-bounce` (420 ms) with `--pan-ease-bounce`.
5. WHEN a button is clicked, `ui_interactions.js` SHALL set `data-p9-pressed`. THE button SHALL stay red, over its hover and disabled looks, until the rerun or Job it started has finished.
6. THE "busy" check SHALL be true when the script state is running (`data-test-script-state="running"`), OR `html` has `data-p8-locked`, OR `html` has the class `p9-await-run`. IT SHALL NOT look at `.pan-loading`, because a faded loader element stays in the DOM.
7. THE attribute SHALL be removed once the page has been quiet for 300 ms and work was seen, or when 1.5 s pass with no work. A Job button (`st-key-p8_btn_*`) SHALL also wait out `--pan-dur-finish` + `--pan-dur-hold` + `--pan-dur-finish-linger` before the attribute is removed. A press SHALL never last more than 15 minutes.
8. WHEN the attribute is removed, THE red SHALL fade out over `--pan-dur-press-out` (600 ms).
9. A disabled button SHALL use the muted surface, muted label and no key edge.
10. THE section 27 selectors SHALL be descendant selectors (`.stButton button`, not `.stButton > button`), because a button with a help tip sits inside a tooltip wrapper.
11. A stale copy of a Job button left by Streamlit while a Job locks the page SHALL be hidden.
12. WITH Reduced_Motion on, buttons SHALL not move and SHALL change colour only.

### Requirement 13: Tooltips

**User Story:** As a planner, I want hover texts that do not stay stuck open, so that they never cover the cards.

#### Acceptance Criteria

1. A pointer click on a tooltip trigger SHALL NOT pin its tooltip open. Keyboard focus SHALL still open it.
2. A closing tooltip SHALL fade out on `--pan-dur-tip`, then be removed, with a 400 ms safety net.
3. A tooltip SHALL NOT run past the screen. At 390 px the last tile's tip SHALL open to the left, so the page does not pan sideways.

### Requirement 14: Theme switch

**User Story:** As a user, I want switching light and dark to feel deliberate, so that the change is not a flash.

#### Acceptance Criteria

1. THE theme switch SHALL be a bubbling-liquid overlay. It SHALL NOT use a View Transition.
2. WHEN the user picks a different theme in the top-right menu, THE app SHALL hold the click and raise a `.p9-liquid` layer, coloured with the new theme's `--pan-bg`, from the bottom of the page over `--pan-dur-theme-fill` (1100 ms fallback). THE colour SHALL be resolved through a probe element in the new colour scheme, so nothing switches early.
3. THE top edge of the layer SHALL be 48 bubbles (2 to 6 rem, 2 to 4 s each) merged by an SVG blur (`stdDeviation` 10) and alpha-threshold filter (`#p9-blob`).
4. ONCE the page is covered, THE app SHALL replay the click once, wait up to 800 ms for the colour scheme to change, fade the layer out over `--pan-dur-slow`, and remove it 50 ms later.
5. THE app SHALL run one pour at a time.
6. THE app SHALL skip the liquid and pass the click through WHEN Reduced_Motion is on, OR the choice would not change the colour scheme, OR the item is already checked.
7. THE liquid SHALL be `aria-hidden`.

### Requirement 15: Narrow screens

**User Story:** As a user on a phone, I want the menu out of the way, so that it does not cover the cards.

#### Acceptance Criteria

1. UNDER 900 px, WHEN the user scrolls down past 48 px by more than 4 px, THE top-right menu SHALL slide away. WHEN the user scrolls up by more than 4 px or reaches the top, it SHALL return.
2. THE script SHALL listen only to `stMain` or the document scroller.
3. UNDER 640 px, stat tooltips SHALL anchor to the left.

### Requirement 16: Motion timing and loader

**User Story:** As a planner who runs the analysis many times a day, I want the finish to be short, so that I get to the answer fast.

#### Acceptance Criteria

1. THE Job finish SHALL be about 1.15 s: `--pan-dur-finish` 800 ms, `--pan-dur-hold` 150 ms, `--pan-dur-finish-linger` 200 ms. THE finish SHALL have no fireworks, and `--pan-reveal-start` SHALL NOT wait for spark time.
2. CARD entrances SHALL be 240 ms (`--pan-dur-swoop`) with steps of 60 ms (`--pan-reveal-step`).
3. `page_lock.js` SHALL, shortly before the finish card would fade, add the class `p9-await-run` to `html` if the script is still running, and remove it when the run ends or after 4 s, so reveal animations play on an idle page.
4. THE page lock SHALL apply to Run Analysis and Build Personas only.
5. THE ring carousel SHALL be a real 3D carousel in which each card faces the viewer (`rotateY(--a) translateZ(--R) rotateY(-a)`), so labels never read mirrored.
   - A turn SHALL change only the registered property `--a` (`@property --a`, `<angle>`), as one CSS transition on `--pan-dur-carousel` and `--pan-ease-carousel`. THERE SHALL be no per-frame script.
   - `S.pos` SHALL never be wrapped, so a turn goes the short way and can be retargeted mid-turn.
   - Items SHALL be placed without motion (`settleRing()`) on first draw, on resize and under Reduced_Motion.
   - THE page and body SHALL use `overflow: clip`, and the perspective SHALL be set by the script with its origin at 50% 18%.
6. `ui_effects.py` SHALL inject both `page_lock.js` and `ui_interactions.js` once, each guarded against double injection, and SHALL skip a missing file.

### Requirement 17: Files and names

**User Story:** As a maintainer, I want file names that do not carry the part number, so that the code reads cleanly.

#### Acceptance Criteria

1. `app/p8_effects.py` SHALL be `app/ui_effects.py`, and `app/static/p8_page_lock.js` SHALL be `app/static/page_lock.js`, with every import and reference updated.
2. THE key names `P8_BTN_RUN_ANALYSIS`, `P8_BTN_BUILD_PERSONAS`, `P8_GROUP_PREV`, `P8_LAST_SPLIT`, `P8_GROUP_VISUAL`, the class prefix `st-key-p8_btn_` and the toast element names SHALL stay unchanged.
3. `app/static/ui_interactions.js` SHALL be new.
4. `win_ca.pem` MAY exist at the repo root as a Windows CA bundle for Bedrock TLS. It is not a runtime asset.

### Requirement 18: Bedrock session token

**User Story:** As a developer on temporary AWS credentials, I want the session token passed through, so that Bedrock calls authenticate.

#### Acceptance Criteria

1. WHEN `AWS_SESSION_TOKEN` is set and not empty, THE Bedrock client SHALL receive it as `aws_session_token`. OTHERWISE it SHALL receive `None`.
2. THE token value SHALL NOT appear in any result, reason or exception text.

### Requirement 19: Tests

**User Story:** As a maintainer, I want the tests to match the restyle, so that the suite stays trustworthy.

#### Acceptance Criteria

1. `test_part5_personas_apptest_smoke.py` SHALL assert that "How the Personas Differ" is absent and no dataframe is drawn, and SHALL compare the card heading `P900 · Ready Toppers` against the markdown with HTML tags stripped.
2. `test_part7_apptest_smoke.py` SHALL require the subheaders Results Grid, Decision Cards and Download Leads, and SHALL require "Export Summary" among the download button labels.
3. `test_part8_tokens_unit.py` SHALL scan `page_lock.js` instead of `p8_page_lock.js`.
4. THE pure helpers added in Part 9 SHOULD have unit tests: `_action_rank`, `_threshold_context`, `_threshold_slug`, `_leads_file_name`, `_segment_figures`, `gap_text`, `_delta_text`, `whatif_change_html`, `whatif_segments_html`, `results_grid_html`, `run_header_html`, `bedrock_html` and `thinking_html`. This is a known gap in the code as written.
5. `ui_interactions.js` has no Python test. Its behavior SHALL be checked in the browser.

## Round 2 requirements (built 2026-11-13)

These nine requirements come from the owner's second list of fixes. They are presentation only. They add no model, calculation or pipeline change, and they keep Requirement 1.

Terms used below:

- **Forecast**: the unrounded Expected Joiners, the sum of `p_join` over sendable leads, shown with one decimal.
- **Shown_Joiners**: the Forecast rounded to the nearest whole number, with halves rounded up (`webapp_core.card_view.round_half_up`).
- **Sendable_Total**: the number of sendable leads across all segments of the Run (the sum of `len(sendable_by_segment[s])`).
- **Segment_Flow**: the stacked bar chart of Requirement 27.
- **Help_Dialog**: the Help And FAQs dialog of Requirement 28.
- **Display_Order**: Ready Toppers, Willing but Stretched, Untapped Wealth, Not Now.

### Requirement 20: Expected Joiners shown rounded, with the forecast beside it

**User Story:** As a CRM manager, I want whole-number joiners with the exact forecast beside them, so that I am not confused by a count of people with a decimal.

#### Acceptance Criteria

1. WHEN the page shows Expected Joiners as a count, IT SHALL show Shown_Joiners (a whole number) as the main figure.
2. THE main figure SHALL be followed on the same line by a smaller, muted text in brackets, `(Forecasted: 87.3)`, with the Forecast to one decimal.
3. THIS pair SHALL appear in the Header number, in each Results Grid tile, in the What-If headline and in the What-If segment table.
4. IN the What-If segment table, each cell SHALL show the Shown_Joiners and the bracket `(87.3)`, and the column heading SHALL read "Expected Joiners (Forecast)". The word "Forecasted:" SHALL NOT repeat in every row.
5. THE What-If "Change" figure SHALL be the difference of the two displayed whole numbers, so the figures on screen agree.
6. THE total Shown_Joiners SHALL be the rounded total Forecast, not the sum of the rounded segment figures. A caption or FAQ entry SHALL say the rows can differ from the total by 1 because each is rounded on its own.
7. THE Decision Card stat "About N Likely To Join" SHALL use the same Shown_Joiners rule. The Likely Range bounds SHALL stay whole numbers.
8. THE Export Summary workbook and the lead files SHALL NOT change.
9. A Forecast under 0.5 SHALL show 0 as the main figure and still show its bracket.
10. THE count-up and roll animations SHALL act on the whole number only. THE bracket text SHALL fade in with its number and SHALL NOT add digit columns.
11. Number definition 6 SHALL be updated when this requirement is built. It resolves the owner decision in task 14.1.

### Requirement 21: Header shows the share of sendable leads

**User Story:** As a CRM manager, I want to see how many leads the expected joiners come from, so that I can judge the number.

#### Acceptance Criteria

1. WHEN a Run exists, THE Header number block (top right) SHALL show, under the Shown_Joiners figure, a line `out of 1,595 sendable leads (12.8%)`.
2. THE count SHALL be the Sendable_Total. THE percentage SHALL be the unrounded Forecast divided by the Sendable_Total, with one decimal.
3. THE line SHALL use the caption size and the muted colour. It SHALL NOT add a second large number.
4. WHEN the Sendable_Total is 0, THE line SHALL read `out of 0 sendable leads` with no percentage and no division.
5. WHEN no Run exists, THE slot SHALL stay hidden and keep its space (Requirement 2.4).
6. THE line SHALL update after a What-If rescore, because it follows the Run.
7. THE Header SHALL still not repeat the promo id, product, threshold or segment count (Requirement 2.3).
8. THE Header SHALL give the line a plain-language tooltip: "The share of messages you can send that we expect to turn into joiners."

### Requirement 22: Plain descriptions for numbers

**User Story:** As a CRM manager, I want the figures that need context to explain themselves in plain words, so that I do not need a data analyst to read them.

#### Acceptance Criteria

1. EACH figure in the table below SHALL carry one short plain description in the place listed, as muted caption text or an existing hover text. A description SHALL be at most 90 characters and use no code names (`p_join`, `ADB`, `excluded_by_reason`).
2. A figure that is already self-explanatory (a date, a promo id, a segment name) SHALL NOT get a description.
3. NO page SHALL show more than one description line under any single block of figures.
4. THE descriptions SHALL be kept in one place per area (`webapp_core/number_help.py`, see the design document) so the Help_Dialog can reuse the same wording.
5. A description that quotes a rate or amount (10% control group, ₱1,000 per joiner) SHALL read it from `part4_cards.config` (`CONTROL_FRACTION`, `VALUE_PER_JOIN_PHP`, `Z_90`) and not hardcode it.

| Figure | Where | Plain description |
|---|---|---|
| Expected Joiners (Header) | Header | `out of <sendable> sendable leads (<pct>%)` (Requirement 21) |
| Clients | Results Grid tile | "Everyone in this group." |
| Expected Joiners | Results Grid tile | `out of <sendable> sendable leads (<pct>%)` for that segment |
| Likely Range | Decision Card | "We are 90% sure the number who join will land in this range." |
| Expected Value | Decision Card | "Joiners at ₱1,000 each, minus the cost of the messages." |
| Not Contacted | Download Leads row | "Left out: do-not-bother list, contacted too often, or no channel." |
| Control Group | Download Leads row | "Held back (about 10%) so you can measure the promo's effect." |
| Sendable | Download Leads row | "The leads in the file. You can message these." |
| Messages Saved, Joiners Kept, Cost Saved | Impact Summary | One line each, for example "Joiners Kept: the share of expected joiners you keep by skipping weak segments." |
| Threshold | Results, What-If | "Clients at or above this amount qualify." |
| Sendable | What-If table caption | "Sendable = leads you can message. Expected Joiners is the forecast among them." |
| Minimum ADB | New Promo form | "ADB is the average daily balance." |
| Persona group size | Personas | `<group> · 376 of 1,595 sendable leads` above each group's personas |
| Expected Joiners By Persona total | Personas | Keep "Total For <Segment>: about N of M likely to join" |
| Predicted, Actual | Past Promos | "Predicted: the join rate we forecast. Actual: the join rate that happened." |
| Gap | Past Promos | "Actual minus predicted, in percentage points." |
| Similarity Score | Past Promos | "0 to 100. How alike this promo is to the one you are designing." |

6. THE Personas caption in the table SHALL resolve the owner decision in task 14.2 for persona groups. The recommended-download caption SHALL read `about 87 of the 282 sendable leads are expected to join` and sit under the Download Recommended Leads button.

### Requirement 23: App title

**User Story:** As the product owner, I want the title to read "Promo Audience Manager", so that the name fits what the CRM manager does with it.

#### Acceptance Criteria

1. `theme.APP_TITLE` SHALL be `Promo Audience Manager`.
2. `st.set_page_config(page_title=...)` SHALL be `Promo Audience Manager`, so the browser tab matches.
3. THE Header wordmark and `theme.nav_bar()` / `theme.header()` SHALL show the new title and no image.
4. THE title SHALL be the only on-screen use of the app name, as in Part 9 Requirement 2.1.
5. THE docstrings and comments in `app/__init__.py`, `app/main.py`, `app/theme.py`, `app/persona_page.py`, `app/styles.css` (first comment) and `.streamlit/config.toml` SHALL use the new name.
6. THE project name DataWave SHALL not change. Older specs (Parts 1 to 8) SHALL keep their historical wording.
7. THE tests that assert the old title SHALL be updated: `test_part5_theme.py` (title text, `APP_TITLE`, and the `styles.css` first-line comment) and `test_part8_assets_unit.py` (`APP_TITLE`). Each change SHALL be listed.

### Requirement 24: What-If segment order

**User Story:** As a planner, I want the segment table in the same order every time, best first, so that I can scan it.

#### Acceptance Criteria

1. THE What-If segment table rows SHALL follow the Display_Order: Ready Toppers, Willing but Stretched, Untapped Wealth, Not Now.
2. A segment name not in the Display_Order SHALL be placed after those four, in name order.
3. THE Display_Order SHALL be one constant (`SEGMENT_DISPLAY_ORDER`) used by the What-If table and the Segment_Flow chart and table, so they cannot drift.
4. THE Results Grid layout, the Past Promos `SEGMENT_ORDER` and the Action_Order of the Decision Cards SHALL NOT change.

### Requirement 25: Download Leads dropdown

**User Story:** As a planner, I want the lead downloads tucked into a dropdown, so that the Results page is shorter.

#### Acceptance Criteria

1. THE Download Leads section SHALL be one collapsible dropdown (`st.expander`) labelled "Download Leads", closed by default.
2. THE dropdown SHALL hold the existing rows (`pan_dl_row_<i>`), the `DOWNLOAD_NOTE` caption and the no-sendable-leads caption, unchanged.
3. THE download button keys (`download_leads_<segment>`) and the primary action bar button (`download_leads_recommended`) SHALL NOT change.
4. THE dropdown SHALL use the same summary style as the "Targeting Details" disclosure (chevron, caption size) and SHALL be focusable by keyboard.
5. THE "Download Leads" heading SHALL no longer be an `st.subheader`. `test_part7_apptest_smoke.py` SHALL be updated to look for the expander label instead.
6. THE dropdown label SHALL show the file count, for example "Download Leads (4 files)", so a closed dropdown still says what is inside.

### Requirement 26: Space around button labels

**User Story:** As a user, I want button text centred with room on both sides, so that it does not touch the edges.

The reference image shows the Personas button "Not sure how many? Suggest a number" with its text running to the left and right borders. This requirement is read as a fix to that button and to buttons like it. If the owner meant the page gutters instead, task 14.6 records that question.

#### Acceptance Criteria

1. EVERY button label SHALL have horizontal padding of at least `--pan-space-4` on each side, including tertiary buttons (`stBaseButton-tertiary`).
2. THE label SHALL be centred in the button.
3. A long label SHALL wrap inside the padding at narrow widths and SHALL NOT be cut off.
4. THE button height SHALL stay `--pan-control-h` (40 px) for a one-line label.
5. THE rule SHALL use tokens only. No new hex values or pixel literals SHALL be added outside section 1.
6. THE Run Analysis and Build Personas buttons, the nav buttons, the download buttons and the suggested-question buttons SHALL be checked for the same fault.

### Requirement 27: Segment Flow chart

**User Story:** As a CRM manager, I want to see how each segment's clients split into not contacted, control and sendable, so that I can see why the file is smaller than the group.

#### Acceptance Criteria

1. THE Results Section SHALL show a Segment_Flow block under the Impact Summary with the heading "Where Each Segment's Clients Go" and one line of description: "Clients = Not Contacted + Control Group + Sendable."
2. THE block SHALL draw one horizontal stacked bar per segment in the Display_Order, plus a Total bar.
3. EACH bar SHALL have three parts in this order: Not Contacted, Control Group, Sendable. Their sum SHALL equal the segment's Clients.
4. THE bar length SHALL be proportional to the segment's Clients, scaled so the largest bar (the Total bar) fills the width. A segment too small to show a part SHALL still show a thin visible part.
5. THE three parts SHALL use three different token colours from the existing chart series: Sendable `--pan-series-2` (teal), Control Group `--pan-series-3` (purple), Not Contacted `--pan-series-6` (slate). They SHALL be exposed as `--pan-flow-sendable`, `--pan-flow-control` and `--pan-flow-excluded` in section 1 as `light-dark()` aliases. They SHALL read well in light and dark mode.
6. COLOUR SHALL NOT be the only cue. Each part SHALL have a legend entry with its name, and each bar SHALL show its counts as text (inside the part when it is wide enough, otherwise in the table).
7. THE block SHALL include a table with the columns Segment, Clients, Not Contacted, Control, Sendable and Expected Joiners, one row per segment in the Display_Order, and a bold Total row. This is the table the owner supplied as the reference. Expected Joiners SHALL follow Requirement 20.
8. THE table SHALL have a caption "Expected Joiners is the forecast among Sendable leads only."
9. THE values SHALL come from the Run's cards: Clients = `n_clients`, Not Contacted = the sum of `excluded_by_reason`, Control = `control_count`, Sendable = `sendable_count`, Expected Joiners = `expected_joiners`. THE chart SHALL use no new calculation.
10. WHEN the three parts do not add up to Clients, THE block SHALL draw the parts as given and SHALL show a caption "These figures do not add up for this run." No value SHALL be changed to make them agree.
11. THE chart SHALL be built from HTML and CSS using tokens (like `.pan-bar`), with no new chart dependency, so it follows light and dark mode and the page radius, type and spacing.
12. THE chart SHALL animate with `transform` or `opacity` only, once, on the render where a new Run arrived, and SHALL be static on an unrelated rerun. WITH Reduced_Motion it SHALL not animate.
13. THE chart SHALL carry `role="img"` and an `aria-label` that states each segment's three counts, and the table below it SHALL be readable by a screen reader.
14. THE block SHALL not appear when no Run exists.

### Requirement 28: Help And FAQs

**User Story:** As a CRM manager, I want a help section that explains where every number comes from and answers the questions I am likely to have, so that I do not get lost.

#### Acceptance Criteria

1. THE app SHALL show a question-mark button (key `help_open`) at the top of the page, outside the tab list. It SHALL NOT be a seventh tab and SHALL NOT sit in the `main_nav` tab bar.
2. THE button SHALL be a round control of `--pan-control-h`, with an accessible name "Help And FAQs" and a hover text with the same words.
3. THE button SHALL sit at the top right, immediately left of the Settings menu, and the Header's right padding SHALL grow to clear both.
4. WHEN the button is pressed, THE app SHALL open the Help_Dialog, an `st.dialog` titled "Help And FAQs", at large width.
5. THE dialog SHALL not replace the tabs, so no widget state is lost. Closing it SHALL return the user to the page they were on.
6. THE Help_Dialog SHALL have three parts, in this order:
   - "How The Numbers Fit Together": a short labelled list of the formulas.
   - "Common Questions": a list of closed dropdowns (`st.expander`), each a question that opens to its answer or formula.
   - "Where To Go Next": buttons or captions pointing to Results, What-If and Personas. NOTHING in this part SHALL change a widget value.
7. THE formulas SHALL include:
   - Clients = Not Contacted + Control Group + Sendable.
   - Expected Joiners = the sum of each sendable lead's chance of joining.
   - Percentage in the Header = Expected Joiners divided by Sendable leads.
   - Likely Range = Expected Joiners plus or minus 1.645 times the square root of the sum of p(1 - p), at 90%.
   - Expected Value = Expected Joiners times ₱1,000, minus message cost.
   - Joiners Kept = Recommended Expected Joiners divided by Baseline Expected Joiners.
   - Similarity Score = eight weighted components, weights adding to 100.
   - Gap = Actual minus Predicted, in points.
8. THE rates and amounts in the answers (10%, ₱1,000, 1.645) SHALL be read from `part4_cards.config`.
9. THE Common Questions list SHALL cover at least these questions, each answered in plain words in at most five sentences:
   - Why is Sendable smaller than Clients?
   - What does Expected Joiners mean, and why is it a forecast?
   - Why does it show 87 and also (Forecasted: 87.3)?
   - Why does the total not equal the sum of the rows?
   - What is the percentage at the top right?
   - What is a Control Group, and why are leads held back?
   - Who is Not Contacted, and why?
   - What does "Act first" mean?
   - What does the threshold do, and what does What-If change?
   - Why do my results not match the form after I used What-If?
   - What is Likely Range?
   - What is Expected Value?
   - What are Messages Saved, Joiners Kept and Cost Saved?
   - How are personas built, and why do their sizes differ by level?
   - What is Demo Mode?
   - Why does the page lock while it loads?
10. EACH answer SHALL end with a "Where to see it" pointer naming the section.
11. THE content SHALL live in a pure module (`webapp_core/help_content.py`) with no Streamlit import, as ordered entries `(id, question, answer, formula | None, where)`. `app/help_page.py` SHALL only draw it.
12. THE dialog SHALL follow the page theme: tokens only, light and dark, `--pan-radius-lg` corners, the same type scale, the muted caption colour, and a visible focus ring. THE dropdowns SHALL use the same summary style as Requirement 25.4.
13. THE dialog SHALL be keyboard operable (Esc closes it, Tab stays inside) and SHALL respect Reduced_Motion.
14. WHILE a Job loader locks the page, THE help button SHALL be locked with everything else.
15. UNDER 900 px, THE help button SHALL follow the Settings menu rule of Requirement 15.1 and SHALL return on scroll up.
16. THE help button and dialog SHALL NOT change any calculation, key or label outside their own.

## Round 3 requirements: the AI features (built 2026-11-13)

These requirements cover the three places that call Amazon Bedrock: Upload Campaign File (`ai.extractor`), persona naming (`ai.persona_narrator`, from `app/persona_page.py`) and Ask Assistant (`ai.assistant`). Every Bedrock call still goes through `ai.bedrock.converse`. The prediction model (Parts 1 to 4) is not a language model and does not change. Requirement 1 still holds, except the changes that Requirement 30 and Requirement 31 name.

Terms used below:

- **Bedrock_Feature**: one of Upload Campaign File, Persona Naming or Ask Assistant.
- **Usage**: the token counts Bedrock returns with a finished call: input, output and total.
- **Built_In**: the rule-based fallback for a Bedrock_Feature (`ai.mocks`, `RuleBasedNamer`).
- **Answer_Layout**: one short lead line, then 3 to 6 hyphen bullets, each one idea.
- **Run_Summary**: the aggregate figures of the current Run (segment counts, actions, expected joiners, threshold, impact), with no per-client data.

### Requirement 29: Assistant answer layout

**User Story:** As a CRM manager, I want every assistant answer laid out the same way, so that I can scan it.

#### Acceptance Criteria

1. EVERY assistant answer, Bedrock or Demo, SHALL follow the Answer_Layout.
2. A drafted message (SMS, email or in-app) SHALL appear as a quoted block with the channel name and its character count.
3. A "what is missing" answer SHALL list one bullet per gap, naming the field in plain words.
4. A pure function SHALL normalise a reply into the Answer_Layout, keep line breaks, cap it at 150 words by whole bullets (never cutting a bullet), and leave no underscores or code names.
5. THE function SHALL be idempotent: formatting a formatted answer changes nothing.
6. THE Bedrock system prompt SHALL ask for exactly this layout: plain hyphen bullets, no headings, no tables.
7. THE page SHALL render the answer as Markdown, with list spacing from the spacing tokens.

### Requirement 30: The assistant sees the current run

**User Story:** As a CRM manager, I want the assistant to answer about the results I just ran, so that I do not have to copy figures into it.

The owner reported as a bug that the assistant could not see the other tabs after Run Analysis. The cause was by design in Part 7: the payload held the form and document only, and any question that named segments, personas or scores was refused. This requirement replaces that rule.

#### Acceptance Criteria

1. WHEN a Run exists, THE assistant payload SHALL include the Run_Summary: per segment the clients, not contacted, control group, sendable, expected joiners, action and dominant channel; the threshold the Run uses; and the Impact Summary figures.
2. WHEN personas exist, THE payload SHALL include each persona's name, size and share, and nothing per client.
3. THE payload SHALL still pass `bedrock.assert_private`: no client id, no per-client row, no table.
4. A question about segments, personas or the forecast SHALL be answered from the Run_Summary. ONLY a question about one client SHALL be refused, with a message that says the assistant works with totals.
5. WHEN no Run exists, a question about results SHALL get an answer that says to press Run Analysis first.
6. THE Demo answer SHALL use the same Run_Summary, so it can answer "Which segment should I act on first?" without Bedrock.

### Requirement 31: Persona names, built-in by default and Bedrock on request

**User Story:** As a CRM manager, I want to choose when persona names come from Bedrock, so that I control what is sent and what it costs.

#### Acceptance Criteria

1. Build Personas SHALL name personas with the Built_In namer and make no Bedrock call.
2. A separate button, "Name Personas with Bedrock" (with the Bedrock icon), SHALL rename the existing personas with Bedrock.
3. A control SHALL switch between the built-in names and the Bedrock names at any time. Both name sets SHALL be kept in session state, so switching neither rebuilds nor calls Bedrock again.
4. RENAMING SHALL NOT change any cluster: every lead keeps its persona and every group size stays the same. A test SHALL prove it.
5. BEFORE the Bedrock call, THE page SHALL say what is sent (aggregate persona summaries, no client data) and the estimated tokens from the token report.
6. THE label SHALL be accurate: "Built-in names" for the rule-based set; a "Bedrock" tag when every persona was named by Bedrock; "Demo Mode" when Bedrock was asked for and every persona fell back; "Mixed" when some fell back, with the source shown on each persona.
7. THE Export Summary "Ai Source" row SHALL follow the name set on screen.

### Requirement 32: AI notices, tags and the mode chip

**User Story:** As a CRM manager, I want to know which figures and words come from a model, so that I check them before I act.

#### Acceptance Criteria

1. ONE notice component SHALL have two kinds, each with fixed words:
   - Bedrock kind: "AI-generated. It can be wrong or incomplete. Check it against your campaign before you use it. Do not rely on it alone."
   - Prediction kind: "These figures are forecasts from a prediction model. They are estimates, not promises. Use them to compare options, not as a guarantee."
2. THE Bedrock kind SHALL show near the top of Upload Campaign File, Ask Assistant, and Personas when Bedrock names are on screen. THE Prediction kind SHALL show near the top of Results, What-If and Personas.
3. EACH notice SHALL be compact (caption size, note surface, token spacing), always visible and not dismissible. NO section SHALL show more than one notice of a kind.
4. EACH Bedrock output (an assistant answer, a Bedrock persona name and text, a field read by Bedrock) SHALL carry a small "AI-generated" tag.
5. A status chip SHALL show the mode (Bedrock or Demo Mode) and the model id from `BEDROCK_MODEL_ID`. NO key, secret or `.env` content SHALL ever be shown.
6. EACH Bedrock notice SHALL carry a "Powered by Amazon Bedrock" chip with the Bedrock icon, and one line saying what the AI does and does not do (Requirement 39).

### Requirement 33: Token usage

**User Story:** As the team lead, I want to see the tokens each AI call uses, so that I can judge cost and limits.

#### Acceptance Criteria

1. `BedrockResult` SHALL carry a Usage value read from the response as `usage.inputTokens`, `usage.outputTokens` and `usage.totalTokens`, each an integer or none. Nothing SHALL be printed.
2. EVERY AI call SHALL be recorded in session state: feature, mode, tokens and seconds. A Demo or Local call SHALL record zero tokens and say so.
3. A token line SHALL show under each AI output as "Input 412 | Output 96 | Total 508 tokens": under an extraction, under each persona name and as a run total, and under each assistant answer.
4. WHILE a call runs, THE page SHALL show "Input about N tokens (estimated)" computed from the request size, labelled as an estimate, then replace it with the real Usage.
5. AN "AI Usage" dropdown SHALL show session totals per Bedrock_Feature, the Bedrock and Demo counts, and the plain reason for each fallback (timed out, no credentials, payload blocked, unreadable reply).
6. EACH Bedrock_Feature SHALL set `inferenceConfig.maxTokens`. A per-session token cap SHALL stop further Bedrock calls with a friendly message and use Built_In instead.
7. Token lines SHALL show numbers only, never a credential.

### Requirement 34: Measured token report

**User Story:** As the team lead, I want measured token averages, so that the cost plan rests on numbers.

#### Acceptance Criteria

1. A script (`scripts/measure_ai_tokens.py`, not part of the runtime) SHALL run a realistic assistant chat on three campaign fixtures (form only; form plus a 2,000 character document; form plus a 30,000 character document), plus persona naming and upload extraction.
2. WHEN credentials are present, THE script SHALL make real calls and label the figures measured. OTHERWISE it SHALL use a documented estimator and label every figure "estimated, not measured".
3. THE script SHALL write `docs/ai-token-report.md`: per interaction input, output and total; average, minimum, maximum and 95th percentile by type; persona and upload figures; and a growth table (users times interactions per day) with price-per-million-token cells left for the owner. NO vendor price SHALL be invented.
4. THE averages SHALL feed the persona note (Requirement 31.5) and a Help And FAQs entry.

### Requirement 35: Assistant transcript and the Bedrock wait line

**User Story:** As a CRM manager, I want the assistant to read like a plain transcript and to show that it is working, so that waiting is clear.

#### Acceptance Criteria

1. THE conversation SHALL be a plain transcript: no bubbles, no round avatars. Each turn SHALL have a narrow marker column: a small solid dot for the user, the stone block for the assistant (spin, finish and rest states kept).
2. USER text SHALL be muted ink. ASSISTANT text SHALL be full width within the 72 character measure.
3. THE input SHALL be one prompt line at the bottom with a top hairline and a hint row "Enter to send | 500 characters max", keeping the chat input and the `assistant_suggested_N` keys.
4. WHILE a Bedrock call runs (assistant, persona naming, upload reading), ONE status line SHALL show a 3 by 3 pixel loader, a shimmering label that alternates "Mining" and "Crafting", a live elapsed timer, and the token estimate.
5. THE loader SHALL be plain HTML and CSS: nine 4 px squares with a 1.5 px gap, each delayed by (column + |row - 1|) times 90 ms on a 650 ms cycle.
6. WITH Reduced_Motion, THE grid SHALL stay dim and still, THE label SHALL stop alternating, and THE timer SHALL still count.
7. AN answer SHALL appear in short steps on the page. NO streaming API SHALL be used.
8. A collapsed "What The AI Used" dropdown under each answer SHALL list the fields sent, the mode and the token line. IT SHALL NOT show hidden reasoning.

### Requirement 36: Bedrock icon

**User Story:** As a CRM manager, I want buttons that call Bedrock to say so, so that I know when data leaves the app.

#### Acceptance Criteria

1. EVERY button that triggers a Bedrock call SHALL show the Bedrock icon before its label.
2. THE icon SHALL be the supplied SVG in `currentColor`, stored as a data URI custom property and drawn with a CSS mask, so it follows light and dark with no image file.
3. THE label SHALL keep `--pan-space-4` padding and a gap of at least `--pan-space-2` after the icon.

### Requirement 37: Safeguards and human oversight

**User Story:** As the team lead, I want people to decide when data goes to Bedrock and to sign off before leads are sent, so that the AI never acts alone.

#### Acceptance Criteria

1. AFTER a file is read locally, THE page SHALL offer "Fill Form with Bedrock" (with the icon) and "Fill Form with Built-in Rules". NOTHING SHALL be sent before the user chooses.
2. BEFORE sending, THE text SHALL be masked: phone numbers, email addresses and long digit strings. THE page SHALL show how many items were masked and a one-line privacy note.
3. BEFORE Download Recommended Leads, A review card SHALL show the threshold used, who is left out, and the control group size, and the download SHALL stay disabled until the user confirms.
4. THE assistant SHALL offer "Report A Wrong Answer" (logs the question and answer), "Clear Conversation And Log", a per-session question limit, and a visible character count for the 500 character limit.
5. A number check SHALL flag any figure in an answer that is not in the payload, using the same approach as `persona_narrator.numbers_in`.
6. A "Use AI Features" switch SHALL force Built_In behaviour on purpose for every Bedrock_Feature.

### Requirement 38: Risk awareness

**User Story:** As the team lead, I want to see who is being targeted and when a forecast looks too good, so that I can catch bias and overconfidence.

#### Acceptance Criteria

1. A read-only "Who Is Being Targeted" view SHALL show, for age band, region and socio-economic class, each group's share of eligible clients and share of sendable leads.
2. THE same view SHALL show, for the past promos, the predicted and actual join rate by group.
3. WHEN a group's sendable share differs from its eligible share by 10 percentage points or more, THE view SHALL flag it in plain words.
4. WHEN a Run's expected join rate (forecast over sendable leads) is at least twice the historical join rate of treated past leads, THE Results page SHALL show a short caution with both rates.
5. NO model, score or segment SHALL change.

### Requirement 39: Purposeful AI use and transparency

**User Story:** As a CRM manager, I want to know what the AI does and does not do, so that I trust the right parts.

#### Acceptance Criteria

1. EACH Bedrock notice SHALL carry one line saying what the AI does in that section and that it never produces or changes a number; scoring is the prediction model; the built-in rules are the fallback.
2. Help And FAQs SHALL answer: what the AI does, why use AI instead of rules, how data is protected, how to check a persona name, and how many tokens it uses (from the token report).

### Requirement 40: Validation

**User Story:** As the team lead, I want a written plan and automated checks for the AI, so that we know it works before and after launch.

#### Acceptance Criteria

1. `docs/ai-validation-plan.md` SHALL cover extractor accuracy on sample files, assistant groundedness (answers use only payload figures), persona-name validity, and a post-launch A/B check with the control group.
2. AUTOMATED tests SHALL cover each, with Hypothesis where useful, including the payload privacy guard with masked text.

## Number definitions

Users have asked why some figures differ. These definitions were checked on the default run (threshold 530,000) and against the code in `src/part4_cards/cards.py` and `src/webapp_core/personas.py`. They describe how the numbers are made. They do not add behavior.

1. Clients per segment = Not Contacted + Control Group + Sendable, exactly. On the default run the totals are 2,000 = 230 + 175 + 1,595. In the code, `n_clients` is every lead in the cell, `excluded_by_reason` sums to the not-contacted count, `control_count` counts the non-excluded control leads, and the sendable leads are the rest.
2. Expected Joiners = the sum of `p_join` over a segment's sendable leads, not over all clients. For Ready Toppers it is 87.3 among 282 sendable leads. The total across segments is 204.4. It is a forecast, so it has decimals.
3. Download Recommended Leads = the sendable leads of the Act first segment(s) only. On the default run that is 282.
4. Personas at the "All leads" level cluster all 2,000 clients. At the "By campaign" level with the audience "Current New Promo run", they cluster the sendable leads (1,595).
5. With a region split, each region's persona sizes add up to that region's sendable count: NCR 719, Luzon 399, Visayas 287, Mindanao 190.
6. Expected Joiners is shown the same way everywhere (Requirement 20, built): the rounded whole number, halves up, with the forecast in brackets, for example `87 (Forecasted: 87.3)` (`87 (87.3)` in tables). The Decision Card stat "About 87" uses the same rounding. A total is rounded from the unrounded sum, so rounded rows can differ from it by 1.
7. Percentage shares use the unrounded Forecast over the Sendable count: 204.4 / 1,595 = 12.8% for the whole run, and 87.3 / 282 = 31.0% for Ready Toppers (Requirements 21 and 22).
