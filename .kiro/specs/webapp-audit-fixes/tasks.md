# Implementation Plan

## Overview

Tests first (task 1 fails on unfixed code, task 2 passes on unfixed code), then one fix per audit item (3.1 to 3.13), then re-runs of both test sets (3.14, 3.15) and a checkpoint (4).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.6", "3.7", "3.8", "3.9", "3.10"] },
    { "id": 3, "tasks": ["3.5", "3.12", "3.13"] },
    { "id": 4, "tasks": ["3.11"] },
    { "id": 5, "tasks": ["3.14", "3.15"] },
    { "id": 6, "tasks": ["4"] }
  ]
}
```

Task 3.5 uses `figures_signature` and `persona_signature` from task 3.1. Task 3.11 must run after 3.5, because both edit the `_render_export_summary` call site in `app/main.py`. Task 3.12 runs after 3.10, because both edit `app/static/ui_interactions.js` (3.12 reads the `entry.job` flag and `isJobButton` that 3.10 adds). Task 3.13 runs after 3.9, because it changes `required_message`, which 3.9 tests. The other fix tasks are independent and can be run in any order.

## Notes

- Tasks 3.1 to 3.13 each add their own tests to `tests/test_webapp_audit_fixes_unit.py`, so any one can be run alone with its `-k` filter.
- Layout, callable `data` with a large workbook, two-session behavior and the loader timing in items 1.12 and 1.14 need a browser (see task 4). The scrim timing in item 1.14 cannot be run in pytest, so its test is a source scan of `ui_interactions.js` for the two named constants and the seen-running logic; the timing itself is checked by hand.
- Requirement numbers are those in `bugfix.md`: 1.12 to 1.15 (defects), 2.12 to 2.15 (expected) and 3.11 to 3.15 (preserved). Design Properties 11 to 15 map to them.

## Tasks

All new tests go in `tests/test_webapp_audit_fixes_unit.py` (Hypothesis, `deadline=None` on tests that touch real modules; follow the import setup in `tests/test_part9_round2_unit.py`). Run one task's tests with `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k <name>`.

- [x] 1. Write bug condition exploration tests
  - **Property 1: Bug Condition** - Sign-off survives changed figures, stale help, shared finishing state, failed-run rerun, eager workbook, small bottom padding
  - **CRITICAL**: These tests MUST FAIL on unfixed code - failure confirms the bugs exist
  - **DO NOT attempt to fix the tests or the code when they fail**
  - **NOTE**: These tests encode the expected behavior - they validate the fixes when they pass after implementation
  - **GOAL**: Surface counterexamples that demonstrate each bug exists
  - **Scoped PBT Approach**: Item 1.1 is the only item with real input variety, so use Hypothesis there. Items 1.2, 1.3, 1.5, 1.9 and 1.10 are deterministic, so scope each to its one concrete failing case (a text search, a source scan or an `ast` check)
  - 1.1 (isBugCondition: a tick made for signature A is still ticked under signature B != A): use a stand-in that mimics the old logic (key `review_ok_<slug>`, never cleared). Assert that after a changed threshold value, a changed threshold type, a changed promo id or a bumped `run_seq`, every `review_ok_*` key is `False`
  - 1.2: assert `help_content` text contains neither "Download Recommended Leads" nor "line under the button", and that the "recommended" and Act first entries mention Download Leads, Choose Leads To Download and Check Before You Download
  - 1.3: assert `app/ui_effects.py` has no module-level `_FINISH_HEADLINE` or `_FINISH_UID` list (source scan with `ast`)
  - 1.5: assert, with `ast` on `app/main.py`, that the `st.rerun()` after the Run Analysis loader sits under `if ok`
  - 1.9: assert `_render_export_summary` passes a callable (not the result of `_export_workbook_bytes(...)`) as `data`, and that `_export_workbook_bytes` does not use `id(` in its cache key
  - 1.10: read the `.stApp .block-container` `padding-bottom` from `app/styles.css` and assert it references `--pan-control-h` and `--pan-space-5`
  - 1.12 (Property 11): deterministic source scan of `app/static/ui_interactions.js` only. Assert the file defines an `isJobButton` helper that finds any `st-key-p8_btn_` ancestor (`closest('[class*="st-key-p8_btn_"]')`), that the part 4b click handler and `settleMs` (through the stored `entry.job`) both use it, and that neither relies only on `isJobKey(keyOf(btn))`, where `keyOf` returns the nearest key (`st-key-persona_run` for Build Personas). Fails today because the handler calls `isJobKey(keyOf(btn))` and `settleMs(key)` tests only `st-key-p8_btn_` at the start of that nearest key
  - 1.13 (Property 12): with `ast` on `app/main.py`, assert the `_render_export_summary(...)` call is not nested in the `else` branch of the no-sendable-leads check, so a run with no sendable leads still reaches it. Fails while the call sits inside that `else`
  - 1.14 (Property 13): source scan of `ui_interactions.js`. Assert the constants `JOB_NO_RUN_MS` and `JOB_SAFETY_CAP_MS` exist and that `watchJobClick` no longer clears on a bare `now - jobClickAt > 3000`. Fails today (no constants, a 3000 ms clear). The timing itself is browser-only and is checked in task 4
  - 1.15 (Property 14): assert `required_message` has an `action` parameter and that `persona_page.py` passes "building personas" to it. Fails while `required_message(missing)` has no `action` parameter and the Personas split error says "before running". The old wording to avoid on Personas is "before running"
  - Run the tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests FAIL (this is correct - it proves the bugs exist)
  - Document counterexamples (for example "tick stays True after threshold 530000 -> 600000", "help text still contains 'Download Recommended Leads'", "no isJobButton in ui_interactions.js; the click handler uses isJobKey(keyOf(btn))", "_render_export_summary is inside the else branch", "watchJobClick clears at 3000 ms; no JOB_SAFETY_CAP_MS", "required_message has no action parameter")
  - Mark task complete when the tests are written, run, and the failures are documented
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.9, 1.10, 1.12, 1.13, 1.14, 1.15_

- [x] 2. Write preservation property tests (BEFORE implementing the fixes)
  - **Property 2: Preservation** - Same figures keep ticks; names, keys, other help entries, forecast caution and finishing state for one session are unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe on UNFIXED code: with no change to figures a tick map stays as it was; `workbook_filename` and the lead file name helper return fixed strings for sample ids and thresholds; the keys `export_summary`, `export_summary_disabled` and `review_ok_` appear in `app/main.py`; `forecast_caution` and `historical_join_rate` return fixed values for sample inputs; every help entry other than the two to be rewritten has a fixed id and question
  - Write property-based tests: for all tick maps over random segment slugs with an unchanged signature, state is unchanged (also over repeated calls) and no key flips to `True`. Write the signature part against a small helper local to the test file that is replaced by `review_signoff` in task 3.1
  - Write example and property tests for the other observed behavior: download names and keys, frozen ids and question text of untouched help entries, formulas still carrying `part4_cards.config` values, `forecast_caution` against a reference computed from `CAUTION_FACTOR`, and one-session write then read of finishing headline and uid (reads through `_state()` with a plain dict stand-in)
  - Observe on UNFIXED code, for items 1.12 to 1.15 (Properties 11 to 15 preservation, bugfix 3.11 to 3.15):
    - `ui_interactions.js`: `JOB_KEYS` lists `st-key-p8_btn_` and `st-key-persona_suggest`; the Run Analysis click (`p8_btn_` container) and the Suggest click (`persona_suggest`) set `data-p9-job-click`; `settleMs` returns 300 for a button with no job key, and `300 + tokenMs("--pan-dur-finish") + tokenMs("--pan-dur-hold") + tokenMs("--pan-dur-finish-linger")` for a `p8_btn_` key
    - `required_message` for New Promo returns exactly "Fill in <names> before running. Fields marked * are required." for sample missing-name lists, and "" for none
    - `app/main.py` contains the keys `export_summary` and `export_summary_disabled` and `review_ok_`; the lead download keys and file names are as they are today
  - Write tests (3.11) Run Analysis click: source scan that the part 4b click handler still sets `data-p9-job-click` for a job key, hands the scrim to the loader (`p9-job-handoff`) and still clears the mark when the form is rejected, and that `JOB_KEYS` still contains `st-key-p8_btn_`
  - Write tests (3.12) Suggest and non-job buttons: source scan that `JOB_KEYS` still contains `st-key-persona_suggest`, that `settleMs` still returns 300 for a non-job button, and that `persona_use_suggestion` is not matched as a job key. The 300 ms settle is checked as a source scan, not by timing
  - Write tests (3.13, 3.14) Export Summary and sign-off keys: the keys `export_summary`, `export_summary_disabled` and `review_ok_` are present; the workbook file name helper returns the same string for sample inputs; the lead file name and download key helpers are unchanged
  - Write tests (3.15) New Promo message: Hypothesis over lists of missing names, `required_message(missing)` equals exactly "Fill in <names> before running. Fields marked * are required." (names joined as the current code joins them), and "" for an empty list; `app/main.py` still calls it without an `action` argument
  - Run the tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms the baseline behavior to preserve)
  - Mark task complete when the tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15_

- [x] 3. Fix the webapp audit defects

  - [x] 3.1 Sign-off reset (item 1.1): add `src/webapp_core/review_signoff.py` and wire it into `app/main.py`
    - New pure module (no Streamlit): `REVIEW_KEY_PREFIX = "review_ok_"`, `SIGNATURE_STATE_KEY = "review_figures_signature"`
    - `figures_signature(promo_id, threshold_type, threshold_value, run_seq)` returns `(str(promo_id), str(threshold_type), round(float(threshold_value), 6), int(run_seq))`
    - `clear_stale_signoffs(state, signature) -> bool`: first call (stored value `None`) stores the signature and clears nothing; a different signature sets every `review_ok_*` key to `False`, stores the new signature and returns `True`; the same signature changes nothing
    - `app/main.py`: bump `st.session_state["run_seq"]` (default 0) on the success path of Run Analysis; call `clear_stale_signoffs(st.session_state, figures_signature(promo_id, t_type.name, t_value, run_seq))` using `_current_threshold(result)` before the first `_render_review_card`. Keep the checkbox key `review_ok_{slug}`
    - If setting a drawn widget's key raises in Streamlit 1.66.1, pop the keys instead (no checkbox has rendered yet in that run)
    - Add `persona_signature(persona_result)` here too, returning `(promo id or "", n personas, narration_source)`, for task 3.5
    - Re-point the task 1 and task 2 sign-off tests at `review_signoff`; add unit tests that equal inputs give equal signatures, any single field changed gives a different one, the value is hashable, and float noise below 1e-6 does not change it
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "signoff or signature"`
    - _Bug_Condition: isBugCondition(input) where a tick made for sigAtTick is still ticked and sigAtTick != sigNow_
    - _Expected_Behavior: every review_ok_* key is False after clear_stale_signoffs with the new signature_
    - _Preservation: same signature keeps every tick; clearing never sets a key to True; non-prefixed keys untouched_
    - _Requirements: 1.1, 2.1, 3.1, 3.2_

  - [x] 3.2 Help text and CSS comments (item 1.2)
    - `src/webapp_core/help_content.py`: rewrite the "recommended" entry (question "How many of the leads in [[Download Leads]] are expected to join?", answer pointing at the Expected Joiners of the [[Act first]] segment, "Where to see it" set to "[[Results]] tab, in the [[Download Leads]] dropdown")
    - Rewrite the Act first entry to describe: open [[Download Leads]], pick the segment in [[Choose Leads To Download]], read [[Check Before You Download]], tick [[I Checked These Figures]], press Download Leads
    - Keep entry ids, `[[...]]` markup, every other entry, and figures read from `part4_cards.config`
    - `app/styles.css`: reword the two comments that use "Download Recommended Leads"
    - Add tests: no stale phrase in any entry, `[[ ]]` pairs balanced, rewritten entries mention the real flow
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k help`, then `tests/test_part9_round2_unit.py`
    - _Bug_Condition: help text mentions a "Download Recommended Leads" button or "line under the button"_
    - _Expected_Behavior: text describes Choose Leads To Download, Check Before You Download, I Checked These Figures, Download Leads_
    - _Preservation: every other help entry, formula and Where To Go Next button unchanged_
    - _Requirements: 1.2, 2.2, 3.4_

  - [x] 3.3 Per-session finishing state (item 1.3)
    - `app/ui_effects.py`: remove the module lists `_FINISH_HEADLINE` and `_FINISH_UID`
    - Add `_set_finish(headline, uid)` and `_get_finish() -> (headline, uid)` over `_state()` with keys `p8_fin_headline` and `p8_fin_uid`
    - Make `_pick_up_completions` write through `_set_finish` and `fx_container` read through `_get_finish()`; leave the `p8_fin_seq` uid logic as is
    - Add tests: two independent state dicts do not leak into each other (Hypothesis over random headlines and uids), and the module-level lists are gone
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k finish`, then `tests/test_part8_job_motion_unit.py`
    - _Bug_Condition: isBugCondition_1_3(input) where sessionCount >= 2 and finish state is a module-level list_
    - _Expected_Behavior: each session reads only its own headline and uid_
    - _Preservation: one session sees the same headline and the same alternating animation id_
    - _Requirements: 1.3, 2.3, 3.3_

  - [x] 3.4 Failed run does not rerun (item 1.5)
    - `app/main.py`: move `st.rerun()` under `if ok:`
    - In the failure path call `_show_messages(messages)` directly and `st.session_state.pop(FLASH_KEY, None)` so the messages show once and are not shown again at the top of the New Promo tab
    - Success keeps storing `FLASH_KEY` and calling `st.rerun()`; keep the loader through the rerun and the finishing overlay once
    - If AppTest can drive a run, add one check that a failed run (empty audience) shows its error once; otherwise rely on the `ast` check from task 1
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k rerun`, then `tests/test_part7_apptest_smoke.py`
    - _Bug_Condition: isBugCondition_1_5(input) where runFailed and rerunCalled_
    - _Expected_Behavior: no st.rerun() on failure; messages shown once in the same render; FLASH_KEY empty afterwards_
    - _Preservation: a successful run still lands on Results, refreshes the header, stores the What-If baseline and plays the overlay once_
    - _Requirements: 1.5, 2.5, 3.5_

  - [x] 3.5 Lazy workbook with a stable cache key (item 1.9)
    - `app/main.py` `_render_export_summary`: pass `data=lambda: _export_workbook_bytes(result)` to `st.download_button` (callable `data` is supported in Streamlit 1.66.1)
    - Catch a build failure inside the callable, set a session flag `export_error`, and show the same plain error text on the next render
    - Change the `_export_workbook_bytes` cache key to `(figures_signature(...), persona_signature(persona_result), narration source, date.today())`, with no `id()`
    - If a build error raised inside the callable cannot be recovered, keep the eager build with the new key and note it in the task result
    - Keep the file name, the keys `export_summary` and `export_summary_disabled`, and the workbook contents
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "workbook or persona_signature"`, then `tests/test_part7_export_workbook*.py`
    - _Bug_Condition: isBugCondition_1_9(input) where resultsRendered and workbookBuilt and not exportPressed_
    - _Expected_Behavior: workbook built only when the download callable runs; cache key from stable signatures_
    - _Preservation: same workbook, same file name, same plain error on failure_
    - _Requirements: 1.9, 2.9, 3.8_

  - [x] 3.6 Bottom padding with tokens (item 1.10)
    - `app/styles.css`: set `.stApp .block-container` `padding-bottom` to `calc(var(--pan-space-5) + var(--pan-control-h) + var(--pan-space-5))` (88 px), tokens only, no new hex value outside section 1
    - Add a test that the rule references both tokens and that the resolved value is at least `--pan-space-5 + --pan-control-h`
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k padding`, then `tests/test_part5_theme.py` and `tests/test_part8_tokens_unit.py`
    - Layout at 390 px is checked in the browser (see the checkpoint list)
    - _Bug_Condition: block-container bottom padding (48 px) is smaller than the "?" button footprint (64 px)_
    - _Expected_Behavior: padding-bottom at least --pan-space-5 + --pan-control-h, written with tokens_
    - _Preservation: "?" button, toasts and other controls look the same on wide windows in light and dark_
    - _Requirements: 1.10, 2.10, 3.9_

  - [x] 3.7 Dead code, comments and caption cleanup, with the test removals (items 1.6, 1.7, 1.8)
    - Remove from `src/webapp_core/fairness.py`: `group_shares`, `past_join_rates`, `GroupShare`, `PastRate`, `GROUP_COLUMNS`, `FLAG_GAP_PTS`. Keep `forecast_caution`, `historical_join_rate`, `CAUTION_FACTOR` and what they use
    - Remove `status_chips_html` from `app/ai_ui.py`, `user_marker_html` from `app/theme.py`, `recommended_caption` from `src/webapp_core/number_help.py`
    - Remove `_render_persona_comparison` and `persona_comparison_frame` from `app/persona_page.py`
    - `app/styles.css`: delete `.st-key-pan_results_actions`, `.pan-ai-status`, `.pan-turn-dot`, `--pan-turn-marker`, `--pan-turn-dot` and the misplaced "red fading out" comment
    - Search the repo for each removed name and fix any leftover import
    - Remove the tests that only call removed code (item 2.6): `test_group_shares_add_to_100_and_flag_large_moves`, the `recommended_caption` assertion, and any test of `persona_comparison_frame`
    - Comments and docstrings (1.7): "two per row on wide screens" in `app/main.py` now says one column; fix the `persona_page.py` docstring and comments about "laid out two per row" and the "How the Personas Differ" table; fix "the block turns beside them" in `styles.css` section 22
    - Caption (1.8): in `app/persona_page.py` use "Each card keeps its usual guidance, with expected joiners split by persona."
    - Add tests: no removed name is referenced anywhere in `app/` or `src/`; `forecast_caution`, `historical_join_rate` and `CAUTION_FACTOR` keep their results; the Personas caption has no "Part 4"
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "removed or caption or caution"`, then `tests/test_part9_ai_unit.py`, `tests/test_part9_round2_unit.py` and `tests/test_part5_personas_apptest_smoke.py`
    - _Bug_Condition: dead code, stale comments and the "Part 4" caption are present_
    - _Expected_Behavior: removed names unreferenced; comments describe current behavior; caption in plain words_
    - _Preservation: forecast_caution, historical_join_rate, CAUTION_FACTOR, persona cards and Expected Joiners By Persona unchanged_
    - _Requirements: 1.6, 1.7, 1.8, 2.6, 2.7, 2.8, 3.6, 3.7, 3.10_

  - [x] 3.8 Validation doc (item 1.4)
    - `docs/ai-validation-plan.md`: replace check 4 step 4 with a step that checks the forecast caution and the past join rates, or delete it and renumber
    - Add a small test that the doc does not mention "Who Is Being Targeted"
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k validation_doc`
    - _Bug_Condition: check 4 step 4 refers to a removed "Who Is Being Targeted" view_
    - _Expected_Behavior: step refers only to things the app still has, or is dropped_
    - _Requirements: 1.4, 2.4_

  - [x] 3.9 Tests for required fields and model display (item 1.11)
    - Read `src/webapp_core/required_fields.py` and `theme.model_display` first to get exact field names, messages and the empty-string value
    - Hypothesis tests for `missing_promo_fields`, `missing_persona_split` and `required_message` over empty, partial and complete inputs: each names exactly the missing items; complete input gives none
    - Tests for `theme.model_display`: a known Bedrock id gives a readable name, an unknown id gives a non-empty fallback, an empty string gives the documented value
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "required or model_display"`
    - _Requirements: 1.11, 2.11_

  - [x] 3.10 Job-button detection with `isJobButton` (item 1.12)
    - `app/static/ui_interactions.js`: add `isJobButton(btn)`. It returns true when `btn.closest('[class*="st-key-p8_btn_"]')` exists (any `st-key-p8_btn_` ancestor, at any depth), or when the button's own key (`keyOf(btn)`) starts with `st-key-persona_suggest`. It returns false for `st-key-persona_use_suggestion`, which sits in the suggestion row but is a normal button
    - Use it in the part 4b click handler in place of `isJobKey(keyOf(btn))`, and store the result on the pressed entry (`entry.job = isJobButton(btn)`) so `settleMs` uses the entry's flag instead of testing the nearest key prefix (`settleMs` already exists; change what it reads, do not add it)
    - Keep `JOB_KEYS` and `isJobKey` as an extra `||` so Run Analysis (`p8_btn_` container) and Suggest keep working
    - Keep widget keys and labels; JS reads the DOM only and never changes a widget value
    - Add tests (source scan): `isJobButton` is defined with the `st-key-p8_btn_` ancestor lookup and the `persona_suggest` own-key check, excludes `persona_use_suggestion`, is called in the click handler, and `settleMs` is driven by `entry.job`
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "job_button or settle"`, then `tests/test_part8_job_motion_unit.py` and `tests/test_part8_assets_unit.py`
    - Instant dim and the red button through the ending for Build Personas are checked in the browser (task 4)
    - _Bug_Condition: isBugCondition_1_12(input) where the button has a p8_btn_ ancestor or a persona_suggest own key, is not persona_use_suggestion, and jobClickHandled is false_
    - _Expected_Behavior: isJobButton(btn) is true for Build Personas; the click dims and locks the page at once and the button keeps its pressed state through the finish (settleMs)_
    - _Preservation: Run Analysis and Suggest clicks unchanged; non-job buttons, including persona_use_suggestion, keep the 300 ms settle_
    - _Requirements: 1.12, 2.12, 3.11, 3.12_

  - [x] 3.11 Export Summary after the if/else (item 1.13)
    - `app/main.py`, `_render_results_tab`: remove the `_render_export_summary(result)` call from the `else` branch of the Download Leads expander and call it once after the whole if/else, at the expander's indent level, so it shows with and without sendable leads. The "No sendable leads were produced for this run." note stays above it
    - Do this after task 3.5, because 3.5 edits the same function (the lazy `data=` callable and the new cache key). Keep the 3.5 changes, the file name and the keys `export_summary` and `export_summary_disabled`
    - Add tests: with `ast`, the call sits in the expander body after the if/else and not inside either branch; the workbook helpers still accept a run with zero sendable leads (no Send List sheets, no lead file added)
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "export_summary or no_sendable"`, then `tests/test_part7_export_workbook*.py`
    - _Bug_Condition: isBugCondition_1_13(input) where sendableLeads = 0 and Export Summary is not rendered_
    - _Expected_Behavior: _render_export_summary(result) is called exactly once per Results render, after the if/else_
    - _Preservation: same workbook, file name and keys; a run with sendable leads shows Export Summary once at the bottom of the dropdown; no lead file is added_
    - _Requirements: 1.13, 2.13, 3.13, 3.14_

  - [x] 3.12 Scrim timing in `watchJobClick` (item 1.14)
    - `app/static/ui_interactions.js`, `watchJobClick`: after a job click, keep the scrim (`data-p9-job-click`) while the script is running. Clear it when a run was seen (`jobSeenBusy`) and the app is now idle, or when no run started within `JOB_NO_RUN_MS = 1500`. Clear it regardless at `JOB_SAFETY_CAP_MS = 15000`. Replace the bare `now - jobClickAt > 3000` clear
    - Define `JOB_NO_RUN_MS` and `JOB_SAFETY_CAP_MS` as plain JS constants at the top of the job-click block, with a comment that they are timing guards and not design tokens (JS cannot read the section-1 CSS tokens for them). No colour or size value is added
    - Keep the `p9-job-handoff` clear (loader mounted) and the interval timer cleanup as they are
    - Depends on 3.10 (same file)
    - Add tests (source scan): both constants exist with those values and a comment, `watchJobClick` uses `jobSeenBusy`, and the old 3000 clear is gone
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k scrim`, then `tests/test_part8_job_motion_unit.py` and `tests/test_part5_theme.py`
    - _Bug_Condition: isBugCondition_1_14(input) where the scrim clears before the run ends, or stays after 1500 ms with no run, or is shown after 15000 ms_
    - _Expected_Behavior: scrim cleared on seen-running then idle, or after JOB_NO_RUN_MS with no run, never later than JOB_SAFETY_CAP_MS_
    - _Preservation: a job that runs normally keeps its scrim until the run ends; the handoff to the loader and the finishing overlay are unchanged_
    - _Requirements: 1.14, 2.14, 3.11_

  - [x] 3.13 `required_message` action parameter and the Personas call (item 1.15)
    - `src/webapp_core/required_fields.py`: change the signature to `required_message(missing, action="running")`. The sentence becomes `f"Fill in {joined} before {action}. Fields marked * are required."`; the default output is identical to today's, and an empty list still gives an empty string. Update the module docstring to mention `action`
    - `app/persona_page.py` (line near `required_message(["Split by"])`): pass `action="building personas"`. `app/main.py` keeps calling it without `action`
    - Do this after task 3.9, which tests `required_message` (re-run those tests after the change)
    - Add tests: Hypothesis over missing-name lists and action text; the default text equals the previous sentence exactly; the Personas text says "before building personas" and not "before running"
    - Check: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py -k "required or action"`, then `tests/test_part5_personas_apptest_smoke.py`
    - _Bug_Condition: isBugCondition_1_15(input) where the Personas split message contains "before running"_
    - _Expected_Behavior: required_message(missing, action="building personas") gives "Fill in <names> before building personas. Fields marked * are required."_
    - _Preservation: the New Promo message stays exactly "Fill in <names> before running. Fields marked * are required."_
    - _Requirements: 1.15, 2.15, 3.15_

  - [x] 3.14 Verify bug condition exploration tests now pass
    - **Property 1: Expected Behavior** - Sign-off clears, help text is current, finishing state is per session, failed run does not rerun, workbook is lazy, padding covers the "?" button, Build Personas is a job button, Export Summary always shows, scrim timing constants are used, Personas message names the action
    - **IMPORTANT**: Re-run the SAME tests from task 1 - do NOT write new tests
    - The task 1 tests encode the expected behavior; when they pass, the expected behavior is satisfied
    - The real scrim timing (item 1.14) is checked in the browser in task 4
    - Run: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py`
    - **EXPECTED OUTCOME**: Tests PASS (confirms the bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.9, 2.10, 2.12, 2.13, 2.14, 2.15_

  - [x] 3.15 Verify preservation tests still pass
    - **Property 2: Preservation** - Same figures keep ticks; names, keys, other help entries, forecast caution and one-session finishing state unchanged; Run Analysis, Suggest and non-job button behavior unchanged; Export Summary and download keys unchanged; New Promo required message unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run: `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py`
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the new file plus the regression set in one command:
    `.\.venv\Scripts\python.exe -m pytest tests/test_webapp_audit_fixes_unit.py tests/test_part5_theme.py tests/test_part5_personas_apptest_smoke.py tests/test_part7_apptest_smoke.py tests/test_part9_round2_unit.py tests/test_part9_ai_unit.py tests/test_part8_*_unit.py`
  - Expect only the tests removed in task 3.7 to be gone. Do not count the six known Part 1 Hypothesis timeouts (unrelated)
  - Ensure all tests pass, ask the user if questions arise
  - List these manual browser checks for the user (not covered by tests; run `$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run app/main.py` yourself):
    - Tick "I Checked These Figures", move the What-If slider, and confirm the box is cleared and Download Leads is disabled; tick again and confirm it enables
    - Tick the box, switch to Personas and back, and confirm it is still ticked
    - Tick the box, press Reset to the as-run threshold, and confirm it clears; run a new analysis with the same promo and threshold and confirm it clears
    - Run Analysis on an empty audience: the error shows once and the page does not redraw twice
    - Open Results and confirm it loads without building the workbook; press Export Summary and confirm the same file name and a working .xlsx
    - Open Ask Assistant at 390 px width and scroll to the bottom: the send button and last row are clear of the "?" button
    - Confirm toasts still sit above the "?" button, in light and dark
    - Open Help And FAQs and read the two rewritten entries in light and dark
    - Open Personas with a live campaign and read the new caption
    - Open two browser sessions, run an analysis in each, and confirm each finishing headline is its own
    - Press Build Personas: the page dims at the click, with no delay before the loader, and the button stays red through the ending
    - Run an analysis that leaves no sendable leads: Export Summary still shows on Results and downloads a workbook
    - Run a slow job (a heavy Personas rerun or a Run Analysis): the scrim stays until the loader mounts or the run ends; click a button that starts no run and confirm the scrim clears after about 1.5 s; confirm nothing keeps it past 15 s
    - Leave the Personas split incomplete and press Build Personas: the error says "before building personas", not "before running"
    - Press "Use N" in the suggestion row: it behaves as a normal button, with no scrim
    - Run Analysis and Suggest still dim, load and finish as before; the New Promo required message is still "Fill in ... before running. Fields marked * are required."
  - _Requirements: 1.12, 1.13, 1.14, 1.15, 2.12, 2.13, 2.14, 2.15, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15_
