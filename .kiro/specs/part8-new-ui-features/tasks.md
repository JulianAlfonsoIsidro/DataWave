# Implementation Plan: Part 8 New UI Features

## Overview

Part 8 is presentation only. The plan follows F1 → F4 → F2 → F3 → F5 → F8 → F7 → F6 → F9, with shared foundations first. Each top-level task ships on its own. Implementation language is Python (plus static HTML/CSS/JS for the one iframe component), as in the design.

Per-task process: read the code you will touch, implement, run only the affected tests plus `tests/test_part5_personas_apptest_smoke.py` and `tests/test_part5_theme.py`, then report. The six pre-existing Part 1 Hypothesis timeouts are excluded.

Hard constraints for every task:

- Presentation only. Parts 1 to 4, `src/run_pipeline.py`, `outputs/`, `data/`, `requirements.txt`, the wording in `labels.py`, and all `part5_personas` code stay at zero changed lines.
- No `pip install`, no CDN, no runtime download. The only third-party file is the approved faeldon/philippines-json-maps v1.1.1 geometry. NumberFlow and Sonner are not used.
- Widget keys and visible labels stay unchanged.
- New colour, radius, spacing, shadow, easing and duration tokens live only in `app/styles.css` section 1. Page and component code carry no hex or `rgb()`/`hsl()` colours, no literal `ms`/`s` durations, no `linear` timing, and no font family names.
- No Streamlit imports under `src/webapp_core/`. Streamlit wiring stays in `app/`.
- Preserve existing docstring requirement references when editing.

## Tasks

- [x] 1. Shared foundations (tokens, token reader, shared motion)
  - [x] 1.1 Add Part 8 tokens and PALETTE entries
    - Add every token in the design's "New tokens" table to `app/styles.css` section 1 as `light-dark()` pairs where they are colours
    - Add `MAP_RED` and `MAP_RED_SELECTED` to `PALETTE` in `app/theme.py` (light values of `--pan-map-fill-a` and `--pan-map-selected`)
    - Measure `--pan-input-outline` in dark mode and write a lighter dark value if under 3:1
    - _Requirements: 3.1, 3.2, 3.7, 3.9, 3.11, 10.1_
  - [x] 1.2 Implement the token reader and iframe palette in `app/theme.py`
    - Add `TokenError`, `read_tokens`, `token_pair`, `iframe_palette`, `PALETTE_TOKENS`, `PICKER_TOKENS`
    - Resolve `light-dark(a, b)` and `var(--x)`; raise `TokenError` naming the token or unreadable block, with no fallback
    - _Requirements: 3.5, 3.6, 3.8, 3.10_
  - [x]* 1.3 Write property test for the token reader
    - Create `tests/test_part8_tokens_unit.py`
    - **Property 10: The iframe palette equals the stylesheet**
    - Add the `PALETTE_TOKENS` mirror test that names the differing entry on failure
    - **Validates: Requirements 3.5, 3.6, 3.7, 3.8, 3.10**
  - [x] 1.4 Add shared motion, stale override and tab fade to `app/styles.css`
    - New CSS sections for `p8-rise`, `p8-fade-in`, `p8-fade-out`, the `data-stale="true"` override (floor `--pan-stale-opacity`, delay `--pan-stale-delay`), the tab panel opacity fade, and a `prefers-reduced-motion` branch for each
    - Use tokens only; animate `transform` and `opacity` only
    - Confirm `stElementContainer` / `data-stale` / `stTabPanel` selectors against Streamlit 1.66.1 and record them for the Change_Report
    - _Requirements: 4.1, 4.2, 4.3, 4.10, 22.1, 22.6, 22.8, 22.9, 22.10, 22.11, 22.12, 22.20_
  - [x]* 1.5 Write the no-literals scan example test
    - Extend `tests/test_part8_tokens_unit.py`
    - Scan Part 8 CSS sections and `app/static/group_picker/*` for hex, `rgb()`/`hsl()`, named colours, `linear`, literal `ms`/`s` outside section 1, and `http(s)://`
    - Assert no file under `src/webapp_core/` imports `streamlit`
    - _Requirements: 2.5, 3.3, 3.4, 12.2, 19.3, 22.1_
  - [x] 1.6 Checkpoint - foundations
    - Run `tests/test_part8_tokens_unit.py` (if written), `tests/test_part5_theme.py`, `tests/test_part5_personas_apptest_smoke.py`; update the browser checklist entries for this feature
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 2.9, 21.1, 21.2_

- [x] 2. F1 - Remove the two redundant header lines
  - [x] 2.1 Remove `theme.utility_bar()` and `theme.nav_bar()` calls from `main()`
    - Keep both functions, `header()`, `APP_TITLE`, `page_title` and the `.pan-utility`/`.pan-nav` CSS unchanged
    - Context banner becomes the first visible element, with no blank band left behind
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.9_
  - [x]* 2.2 Write a header-removal example test
    - Create `tests/test_part8_header_unit.py` checking `main.py` no longer calls `utility_bar`/`nav_bar` and that `theme.nav_bar()`, `theme.header()` and `APP_TITLE` are unchanged
    - _Requirements: 6.6, 6.7, 6.9_
  - [x] 2.3 Checkpoint - F1
    - Run `tests/test_part8_header_unit.py` (if written) plus the two named tests; update the browser checklist entries for this feature
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 6.8, 21.1, 21.2_

- [x] 3. F4 - Text input pill
  - [x] 3.1 Style `st.text_input` as an Input_Pill
    - Inspect the 1.66.1 input DOM (`stTextInput`, `stTextInputRootElement`, `stTextInputField`) and record it
    - Remove the underline and end line; apply pill fill, 1 px outline, `field-sizing: content`, min width token, max 100%, no width transition, hover/focus/disabled states, `@supports not (field-sizing: content)` full-width fallback
    - Replace the old `div[data-baseweb="input"]` rules for inputs only
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 10.13, 4.4_
  - [x] 3.2 Style `st.number_input` and `st.text_area`
    - Number input: fixed column width, same fill and outline, pill radius, steppers stable
    - Text area rules (`stTextAreaRootElement`): full width, grows in height, 20 px radius
    - _Requirements: 10.5, 10.12_
  - [x] 3.3 Checkpoint - F4
    - Run the two named tests plus `tests/test_part8_tokens_unit.py` if present; update the browser checklist entries (including dark-mode outline 3:1 measurement)
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 4. F2 - Job button running state
  - [x] 4.1 Create `consume_flag` and `app/ui_effects.py`
    - `src/webapp_core/toast_queue.py`: add `consume_flag(state, key)` (pop with default False)
    - `app/ui_effects.py`: the keyed `p8_fx` container, one-shot and settle flag helpers, session-state key constants
    - _Requirements: 5.1, 5.2, 5.8, 7.1_
  - [x] 4.2 Write property test for `consume_flag`
    - Create `tests/test_part8_toast_queue_unit.py`
    - **Property 7: A one-shot flag is consumed exactly once**
    - **Validates: Requirements 5.1, 5.2, 5.8**
  - [x] 4.3 Add running and settle style builders and CSS
    - `theme.running_style_html` and `theme.settle_style_html`; CSS for the 2400 ms cycle (trace lap, crossfade, pulse, crossfade back) targeting `.st-key-<key>`, `pointer-events: none`, disabled tokens, static ring under Reduced_Motion
    - _Requirements: 7.2, 7.3, 7.4, 7.5, 4.6, 4.11, 20.1_
  - [x] 4.4 Wire the running state into Run Analysis and Build Personas
    - Wrap each Job_Button in `st.container(key="p8_btn_run_analysis")` / `st.container(key="p8_btn_build_personas")` without changing widget keys, labels, type or form membership
    - Emit the running style into `p8_fx` before the blocking call; set the settle flag on success and on error and consume it once
    - _Requirements: 7.1, 7.6, 7.7, 7.8, 2.4_
  - [x] 4.5 Checkpoint - F2
    - Run `tests/test_part8_toast_queue_unit.py` plus the two named tests; update the browser checklist entries (ring visible through the loader scrim; keyboard double-submit residual risk)
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_
  - [x] 4.6 Add redesign tokens, `job_motion.py` and `theme.job_ring_html`
    - Add `--pan-dur-breath`, `--pan-scale-breath`, `--pan-scale-press`, `--pan-dur-ring-lap`, `--pan-dur-ring-fill`, `--pan-dur-spark`, `--pan-ring-dash`, `--pan-z-ring` to `app/styles.css` section 1
    - Create `src/webapp_core/job_motion.py` with `ring_phase(started_at, now, lap_s)` and `is_duplicate_submit(last_end, signature, now, window_s=1.5)`
    - Add `theme.job_ring_html(state, phase)` (running, done with 10 sparks, error); remove `running_style_html` and `settle_style_html`
    - _Requirements: 4.2, 4.3, 4.12, 4.13, 4.14, 7.4, 7.7, 7.8, 7.9, 7.12_
  - [x] 4.7 Write property tests for `ring_phase` and `is_duplicate_submit`
    - Create `tests/test_part8_job_motion_unit.py`
    - **Property 14: The ring phase is a periodic fraction of a lap**
    - **Property 15: A duplicate submit needs the same inputs inside the window**
    - **Validates: Requirements 7.5, 7.8, 7.11, 7.12**
  - [x] 4.8 Replace `app/styles.css` section 12 with the redesign CSS
    - Hover breath glow plate (`button::after`, opacity in/out over `--pan-dur-slow`), drop the shared hover lift on Job_Buttons, `:active` press scale
    - Ring states via `:has(.p8-ring--running|--done|--error)`: linear `stroke-dashoffset` loop with the phase delay, disabled plate crossfade, fill, glow, sparks, error fade; ring container above the loader overlay (`--pan-z-ring`)
    - `prefers-reduced-motion` branch: no breath or press scale, static ring, highlight fade at most 150 ms, instant error removal
    - _Requirements: 4.2, 4.3, 4.4, 4.10, 4.11, 4.12, 4.13, 4.14, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.9, 7.10_
  - [x] 4.9 Wire the redesigned running state into the app
    - In `app/main.py`, `app/persona_page.py` and `app/ui_effects.py`: ring slot (`st.empty()` before the button inside the keyed container; inside the form for Run Analysis), `started_at` and phase, `p8_job_end` record set before `st.rerun()` and consumed once, done ring drawn in place on success, error ring on error / empty audience / missing model, in-place error ring for persona exceptions
    - Duplicate-submit guard before starting a Job (signature: PromoSpec fields except `promo_id`; persona spec fingerprint)
    - Remove the old running/settle wiring; widget keys, labels, `type` and form membership unchanged
    - _Requirements: 7.1, 7.4, 7.5, 7.7, 7.8, 7.9, 7.11, 7.12, 7.13, 2.4_
  - [x] 4.10 Checkpoint - F2 redesign
    - Run `tests/test_part8_job_motion_unit.py`, `tests/test_part8_toast_queue_unit.py` and the two named tests; update the browser checklist entries (design checklist items 17 to 26)
    - Ensure all tests pass, ask the user if questions arise.

  - [x] 4.11 Make the Job_Button hover breath visible in both modes
    - Add a glow colour token `--pan-breath-glow` to `app/styles.css` section 1 as a `light-dark()` pair that is red in both modes (light about the primary red at ~0.35 alpha, dark the brighter primary red at ~0.45 alpha)
    - In section 12, animate the hover plate's glow opacity on each breath (soft to stronger) together with the existing scale, using only opacity and transform; keep the plate's fade in/out on hover and leave; keep the label still; keep reduced motion off
    - Run `tests/test_part5_theme.py` and `tests/test_part5_personas_apptest_smoke.py`
    - _Requirements: 4.12, 7.2, 20.1_
    - _Requirements: 21.1, 21.2, 21.6_

  - [x] 4.12 Smooth the F2 sequence (decisions A4 to A6)
    - Add `--pan-ease-breath` to section 1; replace the two competing glow layers with one container halo driven by `@property` numbers (`--p8-hover` transition × `--p8-breath` loop); the hover colour plate only fades
    - Container above the overlay for every ring state; reduced-motion done highlight holds `--pan-dur-hold` then fades 150 ms
    - Store results, flash and job-end record inside the `theme.loading` block in `main.py` and `persona_page.py` (keyboard double run)
    - Run `tests/test_part8_job_motion_unit.py`, `tests/test_part8_toast_queue_unit.py` and the two named tests
    - _Requirements: 4.3, 4.12, 7.2, 7.3, 7.7, 7.10, 7.11, 7.12_

  - [x] 4.13 Page lock while a job loader is shown (decision A7)
    - Overlay catches clicks from the moment it is drawn; `--pan-z-loader` above Streamlit's header, `--pan-z-ring` above the loader; tab fade fill mode `backwards`
    - `app/static/page_lock.js` plus `ui_effects.install_page_lock()` (called from `main()` and `render_persona_tab`): `inert` on the page while `.pan-loading:not(.is-finishing)` exists
    - `p8_fx` layout wrapper taken out of flow (no gap above the banner); `stMain` focus frame suppressed
    - Verified in headless Chrome: Run Analysis and Build Personas lock mouse, Tab and the menu, and unlock when the loader goes
    - _Requirements: 7.6, 7.11, 22.2_

- [x] 5. F3 - Toasts, completion stories and loader exit
  - [x] 5.1 Implement the toast queue in `src/webapp_core/toast_queue.py`
    - `Toast`, `ToastView`, `push`, `prune`, `plan_view`, `settle`, `start_text`, constants `LIFE_S`, `ENTER_S`, `MAX_VISIBLE`
    - _Requirements: 8.3, 8.4, 8.5, 8.8, 5.7_
  - [x] 5.2 Write property test for the toast queue bound
    - **Property 5: The toast queue never shows more than three and never shows an expired toast**
    - **Validates: Requirements 5.7, 8.3, 8.4, 8.5**
  - [x] 5.3 Write property test for start toast text
    - **Property 6: Start toast text uses display labels in order**
    - **Validates: Requirements 8.8**
  - [x] 5.4 Add toast and completion story builders, CSS and quiet alerts
    - `theme.toast_stack_html`, `theme.completion_story_html` (magnifier and squares stories, static Gooey_Merge filter, fallback if the filter is stripped), CSS for the fixed stack, hover pause, elapsed-offset delays, `role="status"` `aria-live="polite"`
    - Quiet `st.success`/`st.warning` styling at 4.5:1 contrast; verify `<filter>` survives `st.markdown`
    - _Requirements: 8.1, 8.2, 8.5, 8.6, 8.7, 8.12, 8.13, 8.14, 9.1, 9.2, 9.3, 9.5, 9.6, 9.7, 9.9, 4.5, 20.2, 20.3_
  - [x] 5.5 Wire toasts into both jobs
    - `ui_effects.push_toast` and stack rendering in `p8_fx`; Start_Toast before the blocking call (Promo ID / display labels); Completion_Toast only on success; set `p8_oneshot_analysis` / `p8_oneshot_personas` before `st.rerun()`; consume once; no completion toast for the empty-audience warning, missing-model error or any error
    - Existing flash messages, text and AppTest assertions unchanged
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 8.8, 8.9, 8.10, 8.11, 9.4, 9.8_
  - [x] 5.6 Add the finishing loader overlay exit
    - On a successful Job draw the overlay once in a finishing state that fades out with CSS (`animation-fill-mode: forwards`, `pointer-events: none`); none on error; Reduced_Motion fade at most 150 ms; if unworkable, record why and remove the overlay as the toast enters
    - Keep the existing loader overlay otherwise unchanged
    - _Requirements: 9.10, 22.4, 22.16, 22.17, 22.18, 22.19_
  - [x]* 5.7 Write example tests for the toast and story HTML
    - Create `tests/test_part8_toasts_theme_unit.py`: real text present, animated glyphs `aria-hidden`, `role="status"`, no hex literals
    - _Requirements: 9.7, 8.7, 3.3_
  - [x] 5.8 Checkpoint - F3
    - Run `tests/test_part8_toast_queue_unit.py`, `tests/test_part8_toasts_theme_unit.py` if present, plus the two named tests; update the browser checklist entries
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 6. F5 - Animated headline numbers (CSS roll)
  - [x] 6.1 Implement `src/webapp_core/number_roll.py`
    - `RollCell` and `plan_roll(prev, cur, placeholders)` with right-aligned digit diff
    - _Requirements: 11.2, 11.3, 11.5, 11.8_
  - [x]* 6.2 Write property test for the roll plan
    - Create `tests/test_part8_number_roll_unit.py`
    - **Property 4: The roll plan always ends on the current value and animates only what changed**
    - **Validates: Requirements 11.2, 11.3, 11.5, 11.8**
  - [x] 6.3 Add `roll_number_html`, extend `hero_kpi_html`, and roll CSS
    - Plain value in an `sr-only` span, `aria-hidden` strips, `p8-roll` keyframes (transform only, `--pan-dur-roll`), fixed `ch` width with tabular numerals; `prev=None` output identical to today
    - _Requirements: 11.6, 11.7, 11.8, 11.11, 11.12, 4.3, 22.2_
  - [x] 6.4 Wire the two animated numbers
    - Hero "Expected Joiners" and the What-If headline only, using `p8_num_prev`; first render static; unchanged text static; every other number stays static
    - _Requirements: 11.1, 11.2, 11.3, 11.5, 11.9, 11.10, 22.5_
  - [x] 6.5 Checkpoint - F5
    - Run `tests/test_part8_number_roll_unit.py` if present plus the two named tests; update the browser checklist entries
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 7. F8 - Results reveal and group-change crossfade
  - [x] 7.1 Add `group_changed` to `src/webapp_core/group_picker_items.py`
    - Pure comparison of the Selected_Group to the stored previous value
    - _Requirements: 22.13, 22.14_
  - [x] 7.2 Add reveal and crossfade support in `theme.py` and CSS
    - `theme.card(reveal_index=...)` adds `p8-reveal` and `--i` (capped at 5); `.p8-reveal` rise 14 px with 80 ms base and 50 ms step; opacity-only Group_Change_Crossfade class; Reduced_Motion fade at most 150 ms
    - _Requirements: 17.2, 17.3, 17.4, 17.7, 22.13, 22.15_
  - [x] 7.3 Wire the reveal and crossfade into the Personas tab
    - Consume `p8_oneshot_personas`; Group_Visual container is item 1 when rendered, otherwise the first card; tables get no class; crossfade markup only on the render where the group changed (`p8_last_group`); no reveal on group change or unrelated reruns; no reveal on error
    - _Requirements: 5.3, 5.4, 17.1, 17.5, 17.6, 17.8, 22.14_
  - [x]* 7.4 Write unit tests for `group_changed`
    - Create `tests/test_part8_group_picker_unit.py`
    - _Requirements: 22.14_
  - [x]* 7.5 Write example tests for the reveal markup
    - Create `tests/test_part8_reveal_unit.py`: `card(reveal_index=None)` output unchanged, index capped at 5
    - _Requirements: 17.4, 17.8_
  - [x] 7.6 Checkpoint - F8
    - Run `tests/test_part8_group_picker_unit.py` and `tests/test_part8_reveal_unit.py` if present plus the two named tests; update the browser checklist entries
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 8. F7 - Group picker component (ring with glass, Toggle_Card, illustrations)
  - [x] 8.1 Implement the picker plan helpers in `src/webapp_core/group_picker_items.py`
    - `PickerItem`, `PickerPlan`, `plan_picker` (single-column rules: none / map / toggle with `yes_no` / carousel), `glass_level`, `shortest_step`, `resolve_component_value`, `SyncDecision`
    - Multi-split handling is added in task 10
    - _Requirements: 12.4, 12.8, 12.11, 12.12, 12.13, 13.1, 15.1, 15.11, 15.12, 15.13, 15.14, 15.23_
  - [x] 8.2 Write property test for `plan_picker`
    - **Property 8: The picker kind follows the split and the groups**
    - **Validates: Requirements 12.8, 12.11, 13.1, 15.1, 15.11, 15.12**
  - [x] 8.3 Write property test for `resolve_component_value`
    - **Property 9: Component events are applied once and never revert a dropdown change**
    - **Validates: Requirements 12.4, 12.10, 12.12, 12.13**
  - [x]* 8.4 Write property tests for `glass_level` and `shortest_step`
    - **Property 11: Glass levels are symmetric around the front and wrap**
    - **Validates: Requirements 15.2, 15.8, 15.20, 15.21, 15.23**
  - [x] 8.5 Draw `app/static/group_picker/illustrations.svg`
    - One `<symbol>` per value for `segment`, `age_band`, `sec_class`, `inflow_type`, `online_shopper`; eight distinct yes/no icons; shared check and cross; neutral `unknown`
    - Flat, one accent via CSS variable, no hex, no gradients, peso sign for money, no frailty cues
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12, 16.13_
  - [x]* 8.6 Write sprite coverage tests
    - Create `tests/test_part8_illustrations_unit.py`: every Category list value has a sprite id, unknown falls back to `unknown`, the eight yes/no ids are distinct, no hex or `$` in the sprite
    - _Requirements: 16.3, 16.4, 16.8, 16.12_
  - [x] 8.7 Build the iframe component shell
    - `index.html`, `picker.js`, `picker.css` under `app/static/group_picker/`: 3D ring with two crossfading glass layers per item, flat item cards, Toggle_Card radiogroup, rotate buttons, arrow-key stepping, live region, `setComponentValue {value, nonce}`, `setFrameHeight` with the reserved height, `@supports` tint fallback, Reduced_Motion static levels and instant switch
    - All colours from the palette arg; no hex, no external host
    - _Requirements: 12.1, 12.2, 12.15, 12.16, 15.2, 15.3, 15.4, 15.7, 15.8, 15.9, 15.10, 15.15, 15.16, 15.17, 15.18, 15.19, 15.20, 15.21, 15.22, 15.24, 15.25, 15.26, 15.27, 15.28, 15.29, 20.7, 20.8, 22.3, 22.7_
  - [x] 8.8 Add the component wrapper `app/group_picker.py`
    - `render_group_picker` (skips silently when the static folder or geometry is missing) and `pending_selection`; palette from `theme.iframe_palette`
    - _Requirements: 3.5, 12.1, 12.10, 19.8, 20.5, 20.6_
  - [x] 8.9 Wire the picker into the Personas tab
    - Call `pending_selection` before the `persona_group_select` selectbox; keyed `p8_group_visual` container at the reserved height; placement after the Demo Mode notice; no visual and no dropdown for 0 or 1 group; dropdown to visual sync; store `p8_last_split`
    - _Requirements: 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.11, 12.13, 12.14, 12.15, 12.17, 22.2, 22.3_
  - [x] 8.10 Checkpoint - F7
    - Run `tests/test_part8_group_picker_unit.py`, `tests/test_part8_illustrations_unit.py` if present, `tests/test_part8_tokens_unit.py` if present, plus the two named tests; update the browser checklist entries (glass in 3D, 12-item performance, focus rings)
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 9. F6 - Philippine region map
  - [x] 9.1 Implement `src/webapp_core/region_map.py`
    - `MAP_AREAS`, `AREA_SHAPES`, `MapAreaEntry`, `RegionMapResult`, `build_region_map` (case-sensitive match, fixed order, `ValueError` naming the region), `area_label`, `shape_owner`, `unassigned_shape_codes`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_
  - [x] 9.2 Write property test for region entries
    - Create `tests/test_part8_region_map_unit.py`
    - **Property 1: Region entries are complete, ordered and consistent**
    - **Validates: Requirements 13.1, 13.6, 13.8, 14.2, 14.4, 14.5, 14.6**
  - [x] 9.3 Write property test for invalid counts
    - **Property 2: Invalid counts are rejected without a partial result**
    - **Validates: Requirements 14.1, 14.7**
  - [x] 9.4 Write property test for shape ownership
    - **Property 3: Every shape has at most one owner**
    - Include example checks that all 18 source codes are owned
    - **Validates: Requirements 14.3**
  - [x] 9.5 Download the approved geometry file
    - Fetch only the faeldon/philippines-json-maps v1.1.1 country-level GeoJSON (low or medium resolution) into a working location outside `data/`; no other download
    - _Requirements: 1.14, 19.5, 13.2_
  - [x] 9.6 Write the one-off script `scripts/build_ph_regions.py`
    - Stdlib only; equirectangular projection, grid snap, per-area edge cancellation (union), chaining into outer rings, Douglas-Peucker simplify, per-area under-stroke fallback, NCR bubble, report of ring counts, unmatched edges, fallback areas and unmapped codes; import the mapping from `webapp_core.region_map`
    - _Requirements: 13.2, 13.11, 13.14, 14.3_
  - [x] 9.7 Run the script and add the outputs
    - Run with `PYTHONPATH=src`; write `app/static/group_picker/ph_regions.svg` (about 150 KB or less) and `LICENSE-ph-regions.txt` (asset, v1.1.1, MIT and CC BY-IGO, attribution line)
    - Review the report; delete the downloaded working file afterwards
    - _Requirements: 13.2, 19.1, 19.4, 19.5_
  - [x] 9.8 Add the map view to the component
    - In `picker.js` / `picker.css`: shared `Diamond_Lattice` pattern, per-area groups, hover lift 3 px with pre-drawn shadow opacity, selected fill, 0.6 dim, muted zero-lead areas, NCR bubble with leader line, tab order, `aria-label`, Enter/Space, visible "NAMRIA, PSA via OCHA" credit below the map, kind-switch crossfade in the reserved height
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 13.12, 13.13, 13.14, 13.15, 4.9, 22.7_
  - [x]* 9.9 Write asset example tests
    - Create `tests/test_part8_assets_unit.py`: four `data-area` groups, licence file beside the geometry, size limit, no external URLs, no hex in the SVG
    - _Requirements: 19.4, 19.5, 13.14_
  - [x] 9.10 Wire region data into the picker
    - Build lead counts per region value with `build_region_map` in `app/group_picker.py` and the Personas tab; unmatched values stay selectable in the dropdown; on `ValueError` fall back to the dropdown only
    - _Requirements: 12.12, 13.1, 14.6, 14.7_
  - [x] 9.11 Checkpoint - F6
    - Run `tests/test_part8_region_map_unit.py`, `tests/test_part8_assets_unit.py` if present, plus the two named tests; update the browser checklist entries (no seams at 1x and 2x zoom, light and dark)
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 10. F9 - Multi-category split (option A)
  - [x] 10.1 Extend `plan_picker` for Multi_Split
    - Two or more columns: 3 to 12 combined groups give a carousel labelled with values joined by " · " (first column's illustration, else `unknown`); exactly 2 give a Toggle_Card with the combined labels (`yes_no` false); more than 12 give `none`; `MAX_COMBINED_GROUPS = 12`
    - _Requirements: 18.4, 18.5, 18.6_
  - [x] 10.2 Wire Multi_Split into the Personas tab
    - Pass all selected split columns; combined keys use the existing `" | "` separator; above 12 groups render the dropdown only with no iframe; a failed picker leaves the dropdown working
    - _Requirements: 18.4, 18.5, 18.6, 18.7, 12.10_
  - [x] 10.3 Write property test for the Multi_Split plan
    - Extend `tests/test_part8_group_picker_unit.py`
    - **Property 8: The picker kind follows the split and the groups** (Multi_Split branches: 2, 3 to 12, more than 12)
    - **Validates: Requirements 18.4, 18.5**
  - [x] 10.4 Checkpoint - F9
    - Run `tests/test_part8_group_picker_unit.py` plus the two named tests; update the browser checklist entries
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 21.1, 21.2, 21.6_

- [x] 11. Change_Report
  - [x] 11.1 Write the Change_Report at `.kiro/specs/part8-new-ui-features/change-report.md`
    - Files added, changed or deleted; every changed test expectation with name, old, new and reason (expected none; the `PALETTE` additions `MAP_RED` and `MAP_RED_SELECTED` change none)
    - Streamlit internals table for version 1.66.1 (`data-stale`, `stElementContainer`, `st-key-*`, `stTabPanel`, `stTextInput*`, `stNumberInput*`, `stAlert`, `stMainMenu`)
    - Font statement: for any missing Dax or Avenir Next file, name the `--pan-font-*` token and the fallback family rendered
    - Test files run per task with pass/fail, and the six pre-existing Part 1 Hypothesis timeouts listed as excluded
    - One browser checklist per feature (light, dark, Reduced_Motion on, off, no replay on an unrelated rerun) plus one item for every Requirement 22 criterion 1 to 19
    - Confirm "You are in Campaign Analytics" and the top brand line are gone and the hero title is the only on-screen "Promo Audience Navigator"
    - _Requirements: 6.7, 6.8, 21.3, 21.5, 21.6, 21.7, 21.8, 22.20, 22.21_
  - [x] 11.2 Final checkpoint - Ensure all tests pass
    - Run every `tests/test_part8_*_unit.py`, `tests/test_part5_theme.py` and `tests/test_part5_personas_apptest_smoke.py`; confirm zero changed lines in the protected paths
    - Ensure all tests pass, ask the user if questions arise.
    - _Requirements: 2.3, 2.7, 2.9, 21.2_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. Property tests for `region_map`, `toast_queue`, `plan_picker`, `resolve_component_value` and `job_motion` are required and unmarked.
- Each task references specific requirements for traceability.
- Tasks that edit the same file sit in different waves to avoid conflicts.
- Browser-only checks (motion, glass, map seams, stale override) are listed in the Change_Report checklist because automated tests cannot verify them.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["1.3", "2.1", "3.1", "4.1", "6.1", "7.1", "9.1"] },
    { "id": 3, "tasks": ["1.5", "2.2", "3.2", "4.2", "5.1", "6.2", "7.4", "8.1", "8.5", "9.2", "9.5"] },
    { "id": 4, "tasks": ["1.6", "2.3", "3.3", "4.3", "5.2", "8.2", "8.6", "8.7", "9.3", "9.6"] },
    { "id": 5, "tasks": ["4.4", "5.3", "5.4", "8.3", "8.8", "9.4", "9.7"] },
    { "id": 6, "tasks": ["4.5", "5.5", "5.7", "8.4", "9.8", "9.9"] },
    { "id": 7, "tasks": ["4.6"] },
    { "id": 8, "tasks": ["4.7", "4.8", "4.9"] },
    { "id": 9, "tasks": ["4.10"] },
    { "id": 10, "tasks": ["4.11"] },
    { "id": 11, "tasks": ["5.6", "10.1"] },
    { "id": 12, "tasks": ["5.8", "6.3", "10.3"] },
    { "id": 13, "tasks": ["6.4", "7.2"] },
    { "id": 14, "tasks": ["6.5", "7.3", "7.5"] },
    { "id": 15, "tasks": ["7.6", "8.9"] },
    { "id": 16, "tasks": ["8.10", "9.10"] },
    { "id": 17, "tasks": ["9.11", "10.2"] },
    { "id": 18, "tasks": ["10.4"] },
    { "id": 19, "tasks": ["11.1"] },
    { "id": 20, "tasks": ["11.2"] }
  ]
}
```
