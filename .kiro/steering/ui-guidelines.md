---
inclusion: fileMatch
fileMatchPattern: "app/**"
---

# UI Guidelines

## Purpose

DataWave is an analytical CRM tool for bank campaign planners. The UI should feel calm, trustworthy and efficient. Workflow and clarity come before decoration.

## Brand influence

- Take influence from the BPI mobile app and website: palette, type feel, spacing, tone.
- NEVER use the BPI logo, wordmark, or any asset copied from BPI. Never reproduce a logo-derived shape or pattern.
- The app name is "Promo Audience Manager" / DataWave. It was "Promo Audience Navigator" until Part 9 round 2 (spec Requirement 23).

## Fonts

- **FF Dax** for headings and display. **Avenir Next** for body and UI. **Manrope** sparingly.
- FF Dax and Avenir Next are commercial. Never download, scrape or embed them. Use them only if licensed files are placed in `app/static/fonts`. Otherwise use a fallback stack and tell the user.
- Bundle Manrope locally (SIL OFL) so the app works offline.

## Modes

- Light and dark mode, both fully styled.
- Text contrast meets WCAG AA in both modes.

## Motion

- Minimal, fluid, smooth: 120-250 ms, ease-out, opacity and transform only.
- Nothing loops except loading indicators.
- Respect `prefers-reduced-motion`.
- No motion on large tables or charts.

## Part 8 motion and feedback

- Jobs (Run Analysis, Build Personas; the What-If slider rescore no longer, see Part 9) show a loader that locks the page: clicks, Tab and the top-right menu are blocked, wheel scroll still works. Script: `app/static/page_lock.js`.
- Toasts: a Start_Toast on job start and a Completion_Toast after the finishing overlay. Each toast sits in its own custom element (`<p8-toast-tN>`) so React does not reuse a finished animation clock.
- Hero and What-If numbers roll (about 600 ms) only on the render where the value changed. Pass `prev=` to `hero_kpi_html` / `metric_panel`. Unrelated reruns show static numbers.
- Persona cards get a one-shot reveal and a 150 ms group crossfade. Tables and charts do not move.
- Success and warning flashes are wrapped in `quiet_container` (`p8_quiet_<level>_<n>`) because alerts do not expose their kind in the DOM.
- Z-order and timing come from tokens (`--pan-z-loader/-finish/-ring/-toast`, `--pan-ease-breath`, `--pan-dur-toast-delay`). Do not hardcode them.
- Ring and map animate only `transform` and `opacity`. Never animate blur or use `preserve-3d` with `backdrop-filter`.
- Map credit "NAMRIA, PSA via OCHA" stays visible below the map. The Part 9 header wordmark is the only "Promo Audience Manager" (it replaced the hero).
- Every motion item must also work with Reduced_Motion on, in light and dark, and must not replay on an unrelated rerun.
- Known gap: dimmed map areas are low contrast in dark mode. Raise `--pan-dim` or the dark lattice tones if needed.

## Part 9 layout and polish

Governing spec: `.kiro/specs/part9-layout-fixes/` (requirements, design, tasks). Cite its requirement numbers in docstrings when editing Part 9 code.

- CSS sections 20-28 in `app/styles.css` are Part 9 (hover texts, theme switch, assistant thinking, assistant avatars, round 3 fixes, buttons, plain background). Section 1 stays the only place with hex values.
- Flat look: one flat page colour (no wash or dot grid), no 3px side bars on notes, no red slabs on tiles, no red dash above section labels. Red marks a risk, an error or a pressed button, so do not use it to stress an ordinary number; stress with weight.
- One tight radius scale: `--pan-radius-sm` (tags, tabs, tooltips), `--pan-radius-md` (every control and note), `--pan-radius-lg` (cards). Pill only for chips and dots.
- One control height (`--pan-control-h`, 40px) for tabs, inputs and buttons.
- One filled button per area. Secondary `st.button` (navigation, suggested questions) is outlined. The one primary download is filled.
- Buttons are neutral at rest, red while pressed, and stay red until the rerun or job finishes (`data-p9-pressed`, section 27), then fade back.
- Hover texts open on pointer hover or keyboard focus only, never pinned by a click, and fade on `--pan-dur-tip`. Tips never run past the screen at 390px.
- Theme switch plays a liquid fill (`--pan-dur-theme-fill`). It is skipped with Reduced_Motion or when the choice would not change the colours.
- The top-right menu slides away on screens under 900px while scrolling down and returns on scroll up.
- The main area must never scroll sideways at 390px.
- Run finish is short (about 1.15 s) with no fireworks. Card entrances are 240 ms; reveal steps are 60 ms. What-If slider rescores have no page lock, loader or finish animation.
- Only the headline figures count up (header and grid tiles). The What-If readout is plain.
- A stale copy of a job button is hidden while a job locks the page.
- Ask Assistant uses a stone block avatar and a gold user avatar. Its waiting indicator loops only while waiting.
- Radius scale is 4 / 6 / 8 px (sm / md / lg). `.streamlit/config.toml` `baseRadius` and `buttonRadius` are 6px and must match `--pan-radius-md`.
- Navigation uses `go_to()` / `_nav_button()` with keyed `st.tabs` (`main_nav`). Every tab switch reruns, so keep per-tab data loads cached (see `_cached_past_data`).
- Results: the recommended segment (`Prioritize`) gets the "Act first" tag, not a coloured slab. Cards and download rows follow `ACTION_ORDER`. Lead file names carry the threshold slug.
- What-If: a slider move is not a Job. Show "Rescoring at ..." in the readout slot; no loader, lock or finish.
- The hero is gone. `run_header_html` is the header. The `.pan-hero*` CSS and `hero_kpi_html` / `hero_text_html` / `metric_panel` are unused leftovers (spec task 13.5).
- The Mechanic dropdown shows words (`MECHANIC_DISPLAY`); the stored value stays the code.
- Buttons (built): neutral at rest for every button, including primary downloads. The main action has an ink outline and a red key edge. A press turns red until the work is done (`data-p9-pressed`). Never add a filled red button at rest.
- Stepper (built): four plain grey number circles; only the current tab is red. No check marks or dashed states.
- Page width (built): content is centred at 1200 px. A full-width layout (1680 px) was tried and rejected; do not reintroduce it.
- Theme switch (built): bubbling-liquid overlay, not a View Transition. Carousel cards face the viewer.
- Known gaps: no Python tests for the Part 9 pure helpers or for `ui_interactions.js`; check them in the browser (spec task 13).
- Static files are served from `app/static` (`enableStaticServing`). Script files are `page_lock.js` and `ui_interactions.js`.

## Part 9 round 2 (built)

Spec Requirements 20 to 28 and tasks 16 to 18. Keep to these rules.

- Expected Joiners is always a rounded whole number (halves up) with a smaller muted bracket beside it: `87 (Forecasted: 87.3)`. In tables the cell is `87 (87.3)` under the heading "Expected Joiners (Forecast)". Use `webapp_core/number_format.py`, not ad hoc formatting. The total is rounded from the unrounded sum, so rows may differ from it by 1.
- The Header's right side shows the whole number, the bracket, then `out of 1,595 sendable leads (12.8%)`. The percentage is the unrounded forecast over sendable leads.
- Describe a figure in plain words only when a CRM manager needs the context: one muted line per block, at most 90 characters, no code names. Wording comes from `webapp_core/number_help.py`, which reads rates from `part4_cards.config`. Do not add descriptions to dates, ids or segment names.
- Segment order in the What-If table and the Segment Flow chart is Ready Toppers, Willing but Stretched, Untapped Wealth, Not Now (`SEGMENT_DISPLAY_ORDER`).
- Download Leads is a closed `st.expander` holding the existing rows. Keep every download key.
- Every button label has at least `--pan-space-4` of horizontal padding, is centred, and wraps instead of being cut.
- Segment Flow chart: HTML and CSS stacked bars, not a chart library. Parts are Not Contacted (`--pan-flow-excluded`, slate), Control Group (`--pan-flow-control`, purple) and Sendable (`--pan-flow-sendable`, teal), defined in section 1 as aliases of `--pan-series-6`, `-3` and `-2`. Colour is never the only cue: keep the legend, the counts and the table.
- Dialogs are drawn outside the app root: `ui_interactions.js` part 5 copies the colour scheme to `html[data-p9-scheme]` so they follow light and dark.
- Help And FAQs: a round "?" button (key `help_open`) at the top right, outside the tab bar, opens an `st.dialog`. Do not make it a tab or a separate page, because widgets that are not rendered lose their state. Content lives in `webapp_core/help_content.py`; `app/help_page.py` only draws it. Dialog CSS is section 28 and uses tokens only.

## Scope

- Styling and layout only.
- Do not change backend logic, calculations, widget keys, the meaning of `labels.py` wording, or any part5 behavior.
- Keep `tests/test_part5_theme.py`, `tests/test_part5_personas_apptest_smoke.py` and `tests/test_part7_apptest_smoke.py` passing.
- Update an existing test expectation only when the intentional restyle changed it, and list each change.

## Tokens

- One source of truth for colors, type scale, spacing, radius and motion durations.
- No hardcoded hex values or font names scattered in page code. Use shared helpers in `app/theme.py`.

## Views to cover

- Tabs
- Promo cards and chips
- Personas tab: controls, split-into-groups control, group dropdown, warning and caption, persona cards, "Expected Joiners By Persona" tables with collapsed "How to message this" and "Details" sections, downloads
- Results
- What-If
- Past Promos
- Ask Assistant
- Upload Campaign File panel
- Header and navigation
- Error and empty states

## Process (per task)

1. Read the relevant code first.
2. Describe what you see in each attached reference image and list the approximate values you sample, labelled approximate.
3. Propose the design and WAIT for approval.
4. Implement.
5. Run only the affected tests plus the AppTest smoke test.
6. Report files changed and what to check in the browser, then stop.

## Off limits

- Do not modify Part 1-4 modules, `run_pipeline.py`, `outputs/` or `data/`.
- Do not run `pip install`.