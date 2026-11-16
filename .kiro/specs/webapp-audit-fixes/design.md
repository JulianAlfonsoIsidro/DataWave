# Webapp Audit Fixes Bugfix Design

## Overview

An audit of the Promo Audience Manager webapp found eleven defects (bugfix.md items 1.1 to 1.11). One is a bypassed safeguard: the "I Checked These Figures" box keeps its tick when the figures change (1.1). Three tell users something wrong or let sessions mix: stale help text (1.2), module-level finishing state shared by every session (1.3), and a validation step for a removed view (1.4). The rest are dead code, stale comments, a jargon caption, wasted work and a layout risk (1.5 to 1.10), plus missing tests (1.11).

The fix is small and local. No Part 1 to 4 code, `run_pipeline.py`, `outputs/` or `data/` changes, and no number, score or segment changes.

- **1.1** A new pure module `src/webapp_core/review_signoff.py` builds a "figures signature" and decides which `review_ok_*` keys to clear. `app/main.py` only wires it.
- **1.2** Rewrite two entries in `src/webapp_core/help_content.py` and two CSS comments.
- **1.3** Move `_FINISH_HEADLINE` and `_FINISH_UID` into `st.session_state` through the existing `_state()` helper in `app/ui_effects.py`.
- **1.4, 1.7, 1.8** Edit a doc step, comments, docstrings and one caption.
- **1.5** Move `st.rerun()` into the success path. On failure, show the messages directly in that run.
- **1.6** Delete the listed dead code and the tests that only call it.
- **1.9** Build the workbook lazily. Streamlit 1.66.1 `st.download_button` accepts a callable for `data` (checked in `.venv/Lib/site-packages/streamlit/elements/widgets/button.py`: "deferred data generation by passing a callable"; the callable takes no arguments and Streamlit commands inside it are ignored).
- **1.10** Raise the main block's bottom padding with tokens so the fixed "?" button never covers the last row.
- **1.11** Add `tests/test_webapp_audit_fixes_unit.py` with Hypothesis tests.

A second audit pass added four items (bugfix.md 1.12 to 1.15). The design for 1.1 to 1.11 above and below is unchanged.

- **1.12** The Build Personas job click is not recognised by `app/static/ui_interactions.js`, so no loader settle or scrim logic runs for it. Add `isJobButton(btn)` and use it in the part 4b click handler and in `settleMs`.
- **1.13** Export Summary is hidden when there are no sendable leads, because `_render_export_summary(result)` sits in the `else` branch of the Download Leads expander. Call it once after the if/else.
- **1.14** The job scrim can clear too early or too late. `watchJobClick` clears only when a run was seen and has ended, or when none started within a short window, with a hard cap.
- **1.15** The Personas split message reuses the New Promo sentence ("before running"). Add an optional `action` parameter to `required_message`; the default output is unchanged.

## Glossary

- **Bug_Condition (C)**: The input that triggers a defect. For 1.1, a tick made for one set of figures that is still ticked after the figures change.
- **Property (P)**: The correct behavior for inputs where C holds.
- **Preservation**: Behavior for inputs where C does not hold, which must not change (bugfix.md 3.1 to 3.10).
- **Figures signature**: A hashable tuple identifying the figures behind a download: promo id, threshold type name, threshold value, and the run sequence number. Two renders with equal signatures show the same figures.
- **Run sequence**: A per-session counter, `run_seq`, bumped each time a Run Analysis succeeds. It separates two runs that share promo id and threshold (for example a re-run after the audience data changed).
- **review_ok_<slug>**: The session key of the "I Checked These Figures" checkbox for one Choose Leads To Download selection (`slug` comes from the selection's name). Created in `_render_review_card` in `app/main.py`.
- **_current_threshold(result)**: Helper in `app/main.py` returning the threshold type and value the results currently use (as run, or after a What-If rescore).
- **_state()**: Helper in `app/ui_effects.py` returning `st.session_state` (imports Streamlit lazily).
- **Export_Workbook**: The `.xlsx` built by `webapp_core.export_workbook.build_workbook`.
- **FLASH_KEY**: Session key in `app/main.py` holding run messages. They are popped and shown at the top of the New Promo tab, before the form.

## Bug Details

### Bug Condition

Item 1.1 is the one defect with real logic. The checkbox key is `review_ok_<slug>`, and `<slug>` depends only on the selection name. Streamlit keeps a keyed widget's value for as long as the key is rendered, so the tick survives a What-If rescore, a reset, or a new run. The download button is enabled by that tick, so it can unlock a file for figures nobody checked.

The other items are described by a short condition each and are covered in "Fix Implementation".

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ReviewSession
         (ticks: map slug -> bool, sigAtTick: Signature, sigNow: Signature)
  OUTPUT: boolean

  RETURN EXISTS slug IN input.ticks WHERE input.ticks[slug] = true
         AND input.sigAtTick != input.sigNow
         AND checkboxStillTicked(slug)
END FUNCTION
```

For the supporting items:

```
FUNCTION isBugCondition_1_3(input)     // finishing state
  RETURN input.sessionCount >= 2
         AND finishStateStoredIn = "module-level list"
END FUNCTION

FUNCTION isBugCondition_1_5(input)     // failed run
  RETURN input.runFailed = true AND rerunCalled(input)
END FUNCTION

FUNCTION isBugCondition_1_9(input)     // eager workbook
  RETURN input.resultsRendered = true AND workbookBuilt(input)
         AND NOT input.exportPressed
END FUNCTION
```

**Bug conditions for items 1.12 to 1.15:**

```
FUNCTION isBugCondition_1_12(input)    // Build Personas click
  INPUT: input of type ClickEvent (button: element)
  RETURN (button.closest('[class*="st-key-p8_btn_"]') exists
          OR keyOf(button) STARTS WITH "st-key-persona_suggest")
         AND keyOf(button) != "st-key-persona_use_suggestion"
         AND NOT jobClickHandled(button)        // part 4b handler and settleMs
END FUNCTION

FUNCTION isBugCondition_1_13(input)    // Export Summary hidden
  INPUT: input of type ResultsRender (sendableLeads: int)
  RETURN input.sendableLeads = 0 AND NOT exportSummaryRendered(input)
END FUNCTION

FUNCTION isBugCondition_1_14(input)    // scrim timing
  INPUT: input of type JobClick (runStartMs: int or none, runEndMs: int or none)
  RETURN (scrimClearedAfter(3000 ms) AND scriptStillRunning(input))
         OR (input.runStartMs = none AND scrimStillShownAfter(1500 ms))
         OR scrimStillShownAfter(15000 ms)
END FUNCTION

FUNCTION isBugCondition_1_15(input)    // Personas split wording
  INPUT: input of type (missing: list of str, action: str or none)
  RETURN input.action = none AND callerIsPersonaPage(input)
         AND requiredMessage(input.missing) CONTAINS "before running"
END FUNCTION
```

### Examples

- 1.12: The user presses Build Personas (`st.button(key="persona_run")` inside the `p8_btn_build_personas` container). `keyOf` returns the nearest key, `st-key-persona_run`, so the click is not treated as a job click: no instant scrim or page lock, and only a 300 ms settle. Expected: treated as a job. Run Analysis is not affected, because `st.form_submit_button` has no key. The "Use N" button (`persona_use_suggestion`) inside the suggestion row stays a normal button.
- 1.13: A run has 0 sendable leads. The Download Leads expander shows only its empty note and no Export Summary. Expected: Export Summary still appears, drawn the same way as when there are sendable leads.
- 1.14: A heavy rerun keeps the script running for more than 3 s before the loader mounts. `watchJobClick` clears the scrim at 3 s while the script is still running, so the page un-dims and unlocks briefly and then the loader appears (a flash). Expected: the scrim stays until the loader mounts or the run ends, is cleared after about 1.5 s when no run starts, and never stays later than 15 s.
- 1.15: The Personas page asks for a split attribute and says "Fill in Split By before running." Expected: "Fill in Split By before building personas. Fields marked * are required."
- 1.1: The user ticks the box for "Ready Toppers" at threshold 530,000, moves the What-If slider to 600,000, and the box is still ticked, so "Download N Leads" is enabled. Expected: the box is cleared and the button is disabled.
- 1.1: The user ticks the box, switches to Personas and back. Nothing changed. Expected: still ticked (3.1).
- 1.1: The user ticks "Ready Toppers" only. "Not Now" must stay unticked (3.1).
- 1.1: The user runs a new analysis for the same promo id and the same threshold. `run_seq` changes, so the tick clears.
- 1.2: Help says "The line under the button says it" but there is no such button. Expected: it names Choose Leads To Download and the Check Before You Download card.
- 1.3: Session A finishes a run and writes its headline into `_FINISH_HEADLINE[0]`. Session B writes its own before A's `fx_container` reads it. A shows B's headline. Expected: each reads its own.
- 1.5: A run on an empty audience shows its error. The page draws twice. Expected: once, with the error shown once.
- 1.9: Open Results and the workbook is built without pressing Export Summary. Expected: built when the button is pressed.
- 1.10: At the bottom of Ask Assistant on a narrow window, the last row sits 48 px from the bottom, and the "?" button covers 64 px. Expected: at least 64 px plus a margin.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- A tick stays when run and threshold are unchanged, including tab switches and ordinary reruns. One selection's tick never unlocks another (3.1).
- Lead files keep the same names (promo id, threshold slug, segment), contents and download keys (3.2).
- A single user sees the same finishing headline and the same alternating animation (3.3).
- Every other Help And FAQs entry, formula and Where To Go Next button is unchanged. Figures still come from `part4_cards.config` (3.4).
- A successful run still lands on Results, refreshes the header number, stores the What-If baseline and segment figures, keeps the loader through the rerun and plays the finishing overlay once (3.5).
- The forecast caution still uses `fairness.forecast_caution` with `historical_join_rate` (3.6).
- Persona cards and "Expected Joiners By Persona" are unchanged (3.7).
- Export Summary produces the same workbook and file name, and a failure shows the same plain error (3.8).
- The "?" button, toasts and other controls look and behave the same on wide windows, in light and dark, and toasts still sit above the "?" button (3.9).
- Existing Part 5, 7, 8 and 9 tests pass, apart from the tests removed with the dead code in 2.6 (3.10).
- Run Analysis keeps dimming and locking the page on the click, handing the scrim to the loader, holding the pressed state through the finish, and clearing the mark when the form is rejected (3.11).
- The Suggest click (`persona_suggest`) stays a job click exactly as now. Buttons outside `st-key-p8_btn_*` and `persona_suggest` (tabs, navigation, downloads, What-If controls, and `persona_use_suggestion`) get no scrim and keep the 300 ms settle (3.12).
- The review sign-off, the Download Leads rows, picker, file names, contents and download keys are unchanged. Export Summary in the no-sendable case adds no lead file (3.13).
- When there are sendable leads, Export Summary is shown once, at the bottom of the Download Leads dropdown, with the same workbook and file name as 3.8 (3.14).
- The New Promo required message stays exactly "Fill in X before running. Fields marked * are required." for every set of names and every existing caller (3.15).

**Scope:**
All inputs where nothing about the figures changed, or where the item's trigger is absent, are unaffected. This includes:
- Reruns with the same run and threshold
- Successful runs (apart from the same rerun they already had)
- Downloads, the What-If slider, Past Promos, Ask Assistant and Personas behavior

**Note:** The expected correct behavior is defined in the Correctness Properties section. This section lists what must not change.

## Hypothesized Root Cause

1. **1.1 Key depends on the selection only**: `st.checkbox(..., key=f"review_ok_{slug}")` has no link to the figures. Streamlit retains the value while the key keeps rendering. Nothing in the app clears it on a rescore, reset or run.
2. **1.2 Help text not updated after the download redesign**: the "Download Recommended Leads" button was replaced by Choose Leads To Download and the review card, and `help_content.py` (lines near 137 to 142 and 164 to 167) was not edited.
3. **1.3 Module-level mutable defaults**: `_FINISH_HEADLINE: list = [None]` and `_FINISH_UID: list = [0]` live at the bottom of `app/ui_effects.py`. Streamlit runs every session in one process, so the lists are shared. The rest of the file already uses `_state()`.
4. **1.5 `st.rerun()` indented outside `if ok`**: in `app/main.py` the call after the `with theme.loading(...)` block runs for failures too.
5. **1.9 Eager data build**: `_render_export_summary` calls `_export_workbook_bytes(result)` before `st.download_button`, and the cache key uses `id(result)` and `id(persona_result)`, which can be reused after garbage collection.
6. **1.10 Padding smaller than the button footprint**: `.stApp .block-container` has `padding-bottom: 3rem` (48 px). The fixed button needs `--pan-space-5` (24) + `--pan-control-h` (40) = 64 px.
7. **1.3, 1.6, 1.7, 1.8, 1.4, 1.11**: leftover code, stale text and missing tests after earlier rounds. No logic cause.
8. **1.12 Job detection by nearest key only**: the part 4b `isJobKey` and part 4 `settleMs` in `app/static/ui_interactions.js` test `keyOf(btn)`, which is the NEAREST keyed ancestor (`btn.closest('[class*="st-key-"]')`). Build Personas is `persona_run` inside the `p8_btn_build_personas` container, so the nearest key is `st-key-persona_run`, which neither test knows. The test must look at all keyed ancestors.
9. **1.13 Call placed in the `else` branch**: in `app/main.py` the `_render_export_summary(result)` call is indented inside the branch that handles sendable leads.
10. **1.14 Scrim cleared by a fixed 3 s timer**: `watchJobClick` clears the job-click mark when `now - jobClickAt > 3000`, even while the script is still running. Every tab renders on every run and Personas renders last, so on a heavy rerun the loader can mount after 3 s. There is no "seen running, now idle" state and no longer safety cap. This is read from the code only and needs a browser check.
11. **1.15 One message for two pages**: `required_message` hardcodes "before running", and `persona_page.py` reuses it.

## Correctness Properties

Property 1: Bug Condition - Sign-off clears when the figures change

_For any_ review session where a checkbox was ticked for one figures signature and the current signature is different (isBugCondition returns true), the fixed code SHALL clear every `review_ok_*` key before the checkboxes are drawn, so the download button is disabled until the user ticks again.

**Validates: Requirements 2.1**

Property 2: Preservation - Sign-off stays when the figures are the same

_For any_ review session where the current signature equals the signature at tick time (isBugCondition returns false), the fixed code SHALL leave every `review_ok_*` key unchanged, so each selection keeps its own tick and no tick unlocks another selection.

**Validates: Requirements 3.1, 3.2**

Property 3: Bug Condition - Signature separates different figures

_For any_ two figures inputs that differ in promo id, threshold type, threshold value or run sequence, `figures_signature` SHALL return different values, and for equal inputs it SHALL return equal values (deterministic, hashable).

**Validates: Requirements 2.1, 3.1**

Property 4: Bug Condition - Help text describes the real download flow

_For any_ help entry rendered by `help_content`, the text SHALL NOT contain "Download Recommended Leads" or "line under the button", and the entries "recommended" and the Act first entry SHALL mention Download Leads, Choose Leads To Download and Check Before You Download, with every `[[...]]` pair balanced.

**Validates: Requirements 2.2, 3.4**

Property 5: Bug Condition - Finishing state is per session

_For any_ two independent session-state mappings, writing a headline and uid into one SHALL NOT change what is read from the other.

**Validates: Requirements 2.3, 3.3**

Property 6: Bug Condition - Failed run does not rerun and shows messages once

_For any_ run whose messages contain no success level, the fixed flow SHALL NOT call `st.rerun()` and SHALL show the messages in that same render exactly once, and SHALL leave nothing in `FLASH_KEY` to be shown again on the next render.

**Validates: Requirements 2.5, 3.5**

Property 7: Bug Condition - Workbook is built only on request and cached by a stable signature

_For any_ Results render, the workbook SHALL NOT be built until the download callable runs, and the cache key SHALL be built from the figures signature, the persona generation signature, the narration source and the date, not from `id()`.

**Validates: Requirements 2.9, 3.8**

Property 8: Bug Condition - Required-field and model-name helpers are tested

_For any_ combination of empty, partial and complete inputs, `missing_promo_fields`, `missing_persona_split` and `required_message` SHALL name exactly the missing items, and `theme.model_display` SHALL return a readable name for a known id, a non-empty fallback for an unknown id, and the documented value for an empty string.

**Validates: Requirements 2.11**

Property 9: Preservation - Removed code is unreferenced and kept code works

_For any_ module in `app/` and `src/`, no import or call SHALL reference a removed name (`group_shares`, `past_join_rates`, `GroupShare`, `PastRate`, `GROUP_COLUMNS`, `FLAG_GAP_PTS`, `status_chips_html`, `user_marker_html`, `recommended_caption`, `_render_persona_comparison`, `persona_comparison_frame`), and `forecast_caution`, `historical_join_rate` and `CAUTION_FACTOR` SHALL keep their results for the same inputs.

**Validates: Requirements 2.6, 2.7, 3.6, 3.7, 3.10**

Property 10: Bug Condition - Bottom space covers the "?" button

_For any_ tab, the main block's bottom padding SHALL be at least `--pan-space-5 + --pan-control-h`, written with tokens only and no hex value outside section 1.

**Validates: Requirements 2.10, 3.9**

Property 11: Bug Condition - Build Personas click counts as a job click

_For any_ pressed button where `isJobButton(btn)` holds (a `st-key-p8_btn_*` ancestor, or its own key starts with `st-key-persona_suggest` and is not `persona_use_suggestion`), the part 4b click handler and `settleMs` SHALL treat it as a job button, and neither SHALL depend only on the nearest `st-key` prefix.

**Validates: Requirements 2.12, 3.11, 3.12**

Property 12: Bug Condition - Export Summary is drawn with no sendable leads

_For any_ Results render, whatever the number of sendable leads, `_render_export_summary(result)` SHALL be called exactly once, after the if/else inside the Download Leads expander, and not inside the `else` branch.

**Validates: Requirements 2.13, 3.13, 3.14**

Property 13: Bug Condition - Scrim clears on run end, no-run timeout or cap

_For any_ job click, `watchJobClick` SHALL clear the scrim only when a run was seen and is now idle, or when no run started within about 1500 ms, and SHALL clear it no later than 15 s after the click.

**Validates: Requirements 2.14, 3.11**

Property 14: Bug Condition - Required message uses the caller's action

_For any_ list of missing names and any action text, `required_message(missing, action=action)` SHALL return "Fill in <names> before <action>. Fields marked * are required." and `persona_page.py` SHALL pass "building personas".

**Validates: Requirements 2.15**

Property 15: Preservation - Default required message is unchanged

_For any_ list of missing names, `required_message(missing)` with no action SHALL return exactly the previous sentence "Fill in <names> before running. Fields marked * are required." (empty string for no names).

**Validates: Requirements 3.15**

## Fix Implementation

### Changes Required

**File**: `src/webapp_core/review_signoff.py` (new, pure, no Streamlit)

**Specific Changes**:
1. `figures_signature(promo_id: str, threshold_type: str, threshold_value: float, run_seq: int) -> tuple`: returns `(str(promo_id), str(threshold_type), round(float(threshold_value), 6), int(run_seq))`. Rounding keeps float noise from clearing a tick.
2. `REVIEW_KEY_PREFIX = "review_ok_"` and `SIGNATURE_STATE_KEY = "review_figures_signature"`.
3. `clear_stale_signoffs(state: MutableMapping, signature) -> bool`: if `state.get(SIGNATURE_STATE_KEY)` differs from `signature`, set every key starting with the prefix to `False` (not delete: a keyed widget cannot be deleted after it is drawn in the same run, and this is called before any checkbox renders; setting `False` is safe either way), store the new signature, and return whether it cleared. When the stored value is `None` (first draw), store the signature and clear nothing.

**File**: `app/main.py`

**Specific Changes**:
1. **Run sequence**: on the success path of Run Analysis, bump `st.session_state["run_seq"]` (default 0).
2. **Sign-off reset (1.1)**: at the top of the Download Leads block (before the first `_render_review_card`), call `clear_stale_signoffs(st.session_state, figures_signature(promo_id, t_type.name, t_value, run_seq))`, using `_current_threshold(result)`, so a rescore, a reset and a new run all change it. The checkbox key stays `review_ok_{slug}` (3.1, 3.2). If setting a widget key after its widget exists in an earlier run raises in this Streamlit version, use a callback-free fallback: pop the keys, since no checkbox has rendered yet in this run.
3. **Failed run (1.5)**: move `st.rerun()` under `if ok:`. In the `else` path call `_show_messages(messages)` right there and `st.session_state.pop(FLASH_KEY, None)`, so the top-of-tab pop does not show them a second time on the next render. Success still stores `FLASH_KEY` and reruns as now.
4. **Lazy workbook (1.9)**: in `_render_export_summary`, pass `data=lambda: _export_workbook_bytes(result)` to `st.download_button` (callable supported in 1.66.1). Move the error message into the callable's failure path: wrap the build so an exception is caught by the callable and shown on the next render through a session flag `export_error`, rendered by the same plain text as now (3.8). Change the cache key in `_export_workbook_bytes` to `(figures_signature(...), persona generation signature, source, date.today())`, where the persona generation signature is `(promo id or "", n personas, narration_source)` from a small pure helper `persona_signature(persona_result)` in `review_signoff.py`. If a quick check shows the build raises inside the callable are not recoverable, keep the eager build with the new key (fallback agreed in the audit guidance).
5. **Comments (1.7)**: change "two per row on wide screens" to describe one column.
6. **1.8**: the Personas caption moves to `persona_page.py` (below).

**File**: `src/webapp_core/help_content.py`

1. Rewrite the "recommended" entry: question "How many of the leads in [[Download Leads]] are expected to join?" and an answer that points at the Expected Joiners of the segment tagged [[Act first]], with the example figure still read from the run style text, and the "Where to see it" line set to "[[Results]] tab, in the [[Download Leads]] dropdown".
2. Rewrite the Act first entry: it marks the Prioritize segment; to get its leads open [[Download Leads]], pick it in [[Choose Leads To Download]], read [[Check Before You Download]], tick [[I Checked These Figures]] and press Download Leads.
3. Keep the `[[...]]` markup, the entry ids and every other entry. Figures keep coming from `part4_cards.config`.

**File**: `app/styles.css`

1. Reword the two comments that use "Download Recommended Leads".
2. Delete `.st-key-pan_results_actions`, `.pan-ai-status`, `.pan-turn-dot`, `--pan-turn-marker`, `--pan-turn-dot`, and the misplaced "red fading out" comment on the `--pan-turn-dot` line.
3. Fix the "the block turns beside them" comment in section 22.
4. `.stApp .block-container` (line near 344): set `padding-bottom: calc(var(--pan-space-5) + var(--pan-control-h) + var(--pan-space-5));` (88 px), tokens only. Check that the Ask Assistant send row is not under the button at 390 px, in the browser (not verifiable from CSS alone).

**File**: `app/ui_effects.py`

1. Replace the two module lists with helpers `_set_finish(headline, uid)` and `_get_finish() -> (headline, uid)` over `_state()` under keys `p8_fin_headline` and `p8_fin_uid`. `p8_fin_seq` already lives there, so the uid logic is unchanged (3.3). `fx_container` reads through `_get_finish()`.

**File**: `app/persona_page.py`, `app/ai_ui.py`, `app/theme.py`, `src/webapp_core/fairness.py`, `src/webapp_core/number_help.py`

1. Delete the dead code listed in 1.6. Keep `forecast_caution`, `historical_join_rate`, `CAUTION_FACTOR` and what they use.
2. Fix the `persona_page.py` docstrings and comments about the comparison table and "two per row" (1.7).
3. Change the caption to "Each card keeps its usual guidance, with expected joiners split by persona." (1.8).
4. Do not call `_show_messages`-style helpers from removed code. Check imports with a search after deleting.

**File**: `docs/ai-validation-plan.md`

1. Replace check 4 step 4 with a step that checks the forecast caution and the past join rates, or delete it, and renumber (1.4).

**File**: `app/static/ui_interactions.js` (items 1.12 and 1.14)

1. **`isJobButton(btn)` (1.12)**: returns true when `btn.closest('[class*="st-key-p8_btn_"]')` exists (any depth, not just the nearest key), or when the button's own key (`keyOf(btn)`) starts with `st-key-persona_suggest`. `persona_use_suggestion` ("Use N") is explicitly excluded, even though it sits in the suggestion row, so it keeps the 300 ms settle with no scrim (3.12). Plain vanilla JS, no new dependency.
2. **Use it in the part 4b click handler and `settleMs`**: the handler calls `isJobButton(btn)` instead of testing only the nearest `st-key-` prefix. `settleMs` receives the button, or a flag stored on the pressed entry when the click is recorded (`entry.job = isJobButton(btn)`), and reads that. Existing prefix checks stay as an extra `||` so current job buttons keep working (3.11).
3. **`watchJobClick` (1.14)**: track two facts, `sawRunning` (the app was seen running after the click) and the click time. Clear the scrim only when `sawRunning` is true and the app is now idle, or when no run started within `JOB_NO_RUN_MS = 1500`. A `JOB_SAFETY_CAP_MS = 15000` timer clears it regardless. These two constants are timing guards, not design tokens. JS cannot read the section-1 CSS tokens for them, so they are plain constants at the top of the script with a comment saying so. No colour or size value is added.

**File**: `app/main.py` (item 1.13)

1. In the Download Leads expander, remove the `_render_export_summary(result)` call from the `else` branch and call it once after the whole if/else, at the expander's indent level. Keep the keys `export_summary` and `export_summary_disabled` and the lazy callable from 1.9 unchanged.

**File**: `src/webapp_core/required_fields.py` and `app/persona_page.py` (item 1.15)

1. Change the signature to `required_message(missing: Iterable[str], action: str = "running") -> str`. The sentence becomes `f"Fill in {joined} before {action}. Fields marked * are required."`. With the default, the text is identical to today's. New Promo callers are untouched.
2. In `persona_page.py`, call `required_message(..., action="building personas")` where the split message is built. Update the module docstring in `required_fields.py` to mention the parameter.

**Tests changed with the dead code (2.6)**: remove `test_group_shares_add_to_100_and_flag_large_moves`, the `recommended_caption` assertion, and any test of `persona_comparison_frame`.

## Testing Strategy

### Validation Approach

First, show the bug on the unfixed code. Then check that the fix holds for buggy inputs and that every other input behaves as before. The logic that matters (1.1, 1.3, 1.9 key, 1.11) is in pure helpers, so Hypothesis can test it without a browser. Imports follow `tests/test_part9_round2_unit.py`: put the repo root on `sys.path`, then `from app import theme` and `from webapp_core import ...`. Set `deadline=None` on tests that touch real modules. Tests go in `tests/test_webapp_audit_fixes_unit.py`, with generators in the same file (small, no model fits).

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples on the UNFIXED code. Confirm or refute the root causes.

**Test Plan**: Write the tests below first. On unfixed code the new module does not exist, so the 1.1 tests are written against a stand-in that mimics the old key logic (key = `review_ok_<slug>`, never cleared), then re-pointed at `review_signoff`.

**Test Cases**:
1. **Sign-off survives a rescore**: tick, change threshold value, assert cleared (fails on unfixed code).
2. **Sign-off survives a new run**: tick, bump `run_seq`, assert cleared (fails on unfixed code).
3. **Finishing state shared**: two state dicts, write to one, read the other (fails with module-level lists; the module-level check is a source scan: no `_FINISH_*` list at module level).
4. **Help text stale**: search `help_content` text for "Download Recommended Leads" and "line under the button" (fails on unfixed code).
5. **Failed run reruns**: an `ast` check that `st.rerun()` after the run loader sits under `if ok` (fails on unfixed code).
6. **Padding too small** (may fail): read the `.block-container` padding-bottom and assert it references `--pan-control-h`.

**Expected Counterexamples**:
- Tick state is `True` after the threshold changed.
- Help text still contains the removed button name.
- Possible causes: key without the figures, text not edited, module-level mutable state, rerun outside the success path.

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed code behaves correctly.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  state := apply(input.ticks)
  clear_stale_signoffs(state, input.sigNow)
  ASSERT every review_ok_* value in state is False
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does not hold, the result is the same as before.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT original(input) = fixed(input)
END FOR
```

**Testing Approach**: Property-based testing, because it covers many segment names, thresholds and tick patterns that example tests miss.

**Test Plan**: Observe on unfixed code that the same inputs keep their ticks and that download names and keys are as they are, then write tests that hold after the fix.

**Test Cases**:
1. **Same signature keeps ticks**: for any tick map and equal signatures, state is unchanged (also across repeated calls).
2. **Selections independent**: clearing never sets a key to `True`; keys that were `False` stay `False`; non-prefixed keys are untouched.
3. **Download names and keys**: `workbook_filename` and the lead file name helper return the same strings for sample ids and thresholds; the keys `export_summary`, `export_summary_disabled`, `review_ok_<slug>` appear in the `app/main.py` source.
4. **Other help entries**: every entry other than the two rewritten ones is equal to a frozen copy of its entry id and question text, and formulas still carry values from `part4_cards.config`.
5. **Forecast caution**: `forecast_caution` and `historical_join_rate` give the same results for generated inputs as a reference computed from `CAUTION_FACTOR`.
6. **Finishing state, one session**: write then read gives the same headline and uid, and the uid sequence alternates as before.

### Unit Tests

- `figures_signature`: equal inputs equal, any single field changed differs, hashable, float noise below 1e-6 does not change it.
- `clear_stale_signoffs`: first call stores the signature without clearing, changed signature clears, same signature keeps.
- `persona_signature`: `None` result gives a stable value, different persona generations differ.
- `missing_promo_fields`, `missing_persona_split`, `required_message`: empty, partial and complete inputs (1.11). Read the module first to get the exact field names and messages.
- `theme.model_display`: a known Bedrock id, an unknown id, and an empty string.
- Help content: no stale phrases, balanced `[[ ]]`, rewritten entries mention the real flow.
- Source scans: no removed name is referenced; `_FINISH_HEADLINE` and `_FINISH_UID` no longer exist at module level; the Personas caption has no "Part 4".

### Property-Based Tests

- Random tick maps over random segment slugs plus random signature pairs: fixed behavior for Properties 1 and 2.
- Random promo ids, threshold types, values and run sequences: Property 3.
- Two random session dicts with random headlines and uids: Property 5.
- Random combinations of present and missing fields: Property 8.
- Random lists of names (including empty) and random action text: Property 14 (the sentence uses the action) and Property 15 (the default output equals the old sentence, built in the test from the old format string).
- Random channel and impact inputs are not needed, because nothing in the model changes.

### Tests For Items 1.12 To 1.15

All go in `tests/test_webapp_audit_fixes_unit.py`.

- **1.12 source scan** (Property 11): read `app/static/ui_interactions.js` as text. Assert `isJobButton` is defined, contains `st-key-p8_btn_` and `st-key-persona_suggest`, and that the part 4b click handler and `settleMs` both reference `isJobButton` (or the stored `job` flag) instead of depending only on the nearest `st-key` prefix. Assert `persona_use_suggestion` is not matched by the helper. No Python test can run the JS.
- **1.13 AST scan** (Property 12): parse `app/main.py`, find the Download Leads expander, and assert `_render_export_summary` is called there and is not inside the `orelse` of the sendable-leads `If`. Add an AppTest check only if it is cheap with the existing smoke setup.
- **1.14 source scan** (Property 13): assert `watchJobClick` contains the seen-running flag, the `1500` and `15000` constants, and no colour or token value. Timing is browser-only.
- **1.15 property tests** (Properties 14 and 15): Hypothesis over lists of non-empty names and action text. Default call equals the old sentence built from the old format string; a call with `action` contains `before <action>.`; empty names give "". A source scan asserts `persona_page.py` passes `action="building personas"`.

### Integration Tests

- AppTest smoke: run `test_part7_apptest_smoke` and `test_part5_personas_apptest_smoke` unchanged; both must pass. If AppTest can drive a run, add one check that a failed run shows its error once.
- Run the affected regression set: `test_part5_theme`, `test_part5_personas_apptest_smoke`, `test_part7_apptest_smoke`, `test_part9_round2_unit`, `test_part9_ai_unit` and every `test_part8_*_unit.py`, plus the new file. Expect only the removed-code tests from 2.6 to change.
- Browser check (not covered by tests): tick a box, move the What-If slider, confirm the box is cleared; open Ask Assistant at 390 px and confirm the send button is clear of the "?" button; confirm toasts still sit above it; open Help And FAQs and read the two rewritten entries in light and dark.
- Browser checks for 1.12 and 1.14: press Build Personas and confirm the scrim and settle show and clear when the run ends; press "Use N" on a suggestion and confirm it is not treated as a job; click a job button that starts no run and confirm the scrim clears after about 1.5 s; confirm a long job never keeps the scrim past 15 s.
- Browser check for 1.13: run with 0 sendable leads and confirm Export Summary shows in Download Leads; with sendable leads confirm it shows once.
- Browser check for 1.15: tick "Split into groups first" with no "Split by" and confirm the message says "before building personas".
- Not verifiable here: the 1.10 layout and the callable `data` behavior with a large workbook in a real browser. Both need a manual look.
