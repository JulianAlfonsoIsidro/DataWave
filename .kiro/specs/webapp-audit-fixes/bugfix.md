# Bugfix Requirements Document

## Introduction

An audit of the Promo Audience Manager webapp (`app/` and `src/webapp_core/`) found a safeguard that can be bypassed, help text that describes a removed button, shared state that can mix up two users, and some leftover dead code and wasted work. Each item below was checked by reading the code. Items from the audit list that turned out not to be real are named at the end so nobody fixes them by mistake. Nothing here changes Parts 1 to 4, `run_pipeline.py`, `outputs/` or `data/`, and no number, score or segment changes.

Items are grouped by severity: High (a safeguard fails), Medium (users are told something wrong, or users can affect each other), Low (dead code, wasted work, small layout risk, missing tests).

## Bug Analysis

### Current Behavior (Defect)

**High**

1.1 WHEN a user ticks "I Checked These Figures" for a segment in Download Leads, and then the figures change (a What-If rescore, a reset to the as-run threshold, or a brand-new Run Analysis) THEN the system keeps the box ticked, because its widget key (`review_ok_<segment>`) depends only on the segment name, so the download button stays enabled for figures the user never checked.

**Medium**

1.2 WHEN a user opens Help And FAQs and reads the entries "How many of the leads in Download Recommended Leads are expected to join?" and "What does the Act first tag mean?" THEN the system tells them to use a "Download Recommended Leads" button and to read "the line under the button", but that button and line no longer exist. Downloads are now made with "Choose Leads To Download" and the "Check Before You Download" card inside the Download Leads dropdown. The help entry also points to a "Results tab, under Download Recommended Leads" location that does not exist. Two CSS comments in `styles.css` still use the old button name.

1.3 WHEN two users run the app at the same time THEN the system can show one user the other's finishing headline or animation id, because `_FINISH_HEADLINE` and `_FINISH_UID` in `app/ui_effects.py` are module-level lists shared by every session. They are written in `_pick_up_completions` and read a moment later in `fx_container`, so another session's run can write between the two.

1.4 WHEN a user follows the validation plan, `docs/ai-validation-plan.md` check 4 step 4 tells them to review a "Who Is Being Targeted" view, but that view was removed from the app, so the step cannot be done.

1.12 WHEN a user clicks Build Personas THEN the system gives no instant scrim or page lock, and holds the red pressed state only 300 ms after the page goes quiet. `ui_interactions.js` (part 4b `isJobKey`, part 4 `settleMs`) counts a click as a job click only when `keyOf(btn)` starts with `st-key-p8_btn_` or `st-key-persona_suggest`. `keyOf` returns the NEAREST keyed ancestor (`btn.closest('[class*="st-key-"]')`). The button is `st.button(..., key="persona_run")` inside `st.container(key=ui_effects.P8_BTN_BUILD_PERSONAS)`, so the nearest key is `st-key-persona_run`, not `st-key-p8_btn_build_personas`. The red state can therefore fade before the loader's finish plays. Run Analysis is not affected: `st.form_submit_button` has no key, so its nearest keyed element is the `p8_btn_` container.

1.13 WHEN a run exists but has no sendable leads (every lead excluded or held back) THEN the system hides Export Summary, because `_render_results_tab` in `app/main.py` calls `_render_export_summary(result)` only inside the `else:` branch of the Download Leads expander (taken when `result.sendable_by_segment` is non-empty). The workbook (Summary, Decision Cards, Personas) is still meaningful for such a run, but it cannot be exported.

**Low**

1.5 WHEN a user presses Run Analysis and the run fails (for example an empty audience or no model) THEN the system still calls `st.rerun()` after the loader, because that call sits outside `if ok`. The error is not lost (it is saved under `FLASH_KEY` and shown after the rerun) and there is no loop (the form is no longer submitted on the rerun), but the page is drawn twice for no reason.

1.6 WHEN a developer reads the code THEN the system contains code that nothing in the app uses:
- `src/webapp_core/fairness.py`: `group_shares`, `past_join_rates`, `GroupShare`, `PastRate`, `GROUP_COLUMNS` and `FLAG_GAP_PTS` (only a test calls `group_shares`; the others are not called anywhere). `forecast_caution` and `historical_join_rate` are used and stay.
- `app/ai_ui.py` `status_chips_html`, `app/theme.py` `user_marker_html`, and `number_help.recommended_caption` (only a test calls it).
- `app/persona_page.py` `_render_persona_comparison` and `persona_comparison_frame` (the "How the Personas Differ" table is no longer drawn, and a comment says the renderer is only kept "available").
- In `app/styles.css`: `.st-key-pan_results_actions` (no widget uses that key), `.pan-ai-status` and `.pan-turn-dot` (only used by the dead helpers above), and the tokens `--pan-turn-marker` and `--pan-turn-dot`. Note that `--pan-turn-dot` shares a line with a misplaced comment about red fading out.

1.7 WHEN a developer reads comments and docstrings THEN the system shows text that no longer matches the app: "decision cards, two per row on wide screens" in `app/main.py` (cards are one column), "laid out two per row to match the Results tab" in a `persona_page.py` docstring, "the block turns beside them" in `styles.css` section 22, and module and function docstrings in `persona_page.py` that still describe the "How the Personas Differ" table as part of the page.

1.8 WHEN a user opens the Personas tab with a live campaign THEN the system shows the caption "Each card keeps its Part 4 guidance unchanged, with expected joiners split by persona." This uses an internal project term ("Part 4") that CRM managers do not know.

1.9 WHEN a run exists and the Results tab is drawn THEN the system builds the whole Export_Workbook (`_export_workbook_bytes`) on that render, even if the user never presses Export Summary. It is cached per session, so the cost is paid once per run, per persona result and per day, but it is paid up front. The cache key also uses `id()` of the run and persona objects, and Python can reuse an `id()` after an object is freed, so a stale workbook is possible in theory.

1.10 WHEN a user is on a window narrower than the 1200 px content column, or scrolls to the very bottom of a page THEN the system may draw the fixed "?" help button (bottom right, 24 px from the edges, 40 px high) over page controls such as the Ask Assistant chat send button or a control at the right end of the last row. The page's bottom padding (3 rem, 48 px) is smaller than the button's footprint (64 px), so the last row can sit under it. This is read from the CSS only and has not been checked in a browser.

1.11 WHEN a developer runs the tests THEN the system has no tests for `src/webapp_core/required_fields.py` (`missing_promo_fields`, `missing_persona_split`, `required_message`), which block a run and a persona build, or for `theme.model_display`, which turns a Bedrock model id into the name shown in the AI chips.

1.14 WHEN a job click is made and the script keeps running for more than 3 seconds before the loader mounts THEN the system may un-dim and unlock the page briefly and then show the loader (a flash). `watchJobClick` in `ui_interactions.js` clears the job-click mark when `now - jobClickAt > 3000`, even while the script is still running. Every tab renders on every run and the Personas tab renders after New Promo, Results and What-If, so on a heavy rerun the Build Personas loader can mount after 3 s. This is read from the code only; it needs a browser check.

1.15 WHEN Build Personas is pressed with "Split into groups first" ticked and no "Split by" attribute chosen THEN the system shows "Fill in Split by before running. Fields marked * are required." The wording comes from `required_message(["Split by"])` in `src/webapp_core/required_fields.py`, which always says "before running". On Personas the action is Build Personas, not a run.

### Expected Behavior (Correct)

2.1 WHEN the figures behind a download change (a What-If rescore, a reset, or a new Run Analysis) THEN the system SHALL clear every "I Checked These Figures" box, so the download button is disabled until the user ticks it again for the new figures. The same segment and threshold, with no new run, SHALL keep its tick.

2.2 WHEN a user reads Help And FAQs THEN the system SHALL describe the real download flow (Choose Leads To Download, Check Before You Download, I Checked These Figures, Download Leads), SHALL give the "How many are expected to join" answer in terms of the Expected Joiners of the Act first segment and the Download Leads dropdown, SHALL point to a place that exists, and SHALL contain no mention of a "Download Recommended Leads" button. The two stale CSS comments SHALL be reworded.

2.3 WHEN two users run the app at the same time THEN the system SHALL keep each user's finishing headline and animation id in that user's own session state, so one session can never read another's.

2.4 WHEN a user follows `docs/ai-validation-plan.md` THEN the system SHALL give a check 4 step 4 that refers only to things the app still has (for example the forecast caution and the past join rates), or drop the step.

2.5 WHEN a Run Analysis fails THEN the system SHALL show the error messages without an extra rerun, and SHALL still show them exactly once.

2.6 WHEN the dead code in 1.6 is removed THEN the system SHALL keep `forecast_caution`, `historical_join_rate`, `CAUTION_FACTOR` and everything they need, and SHALL update or delete only the tests that call the removed code (`test_group_shares_add_to_100_and_flag_large_moves`, the `recommended_caption` assertion, and any test of the removed persona comparison frame).

2.7 WHEN the comments and docstrings in 1.7 are read THEN the system SHALL describe the current behaviour (cards in one column, no comparison table, no avatar-turning animation).

2.8 WHEN the Personas tab shows the caption in 1.8 THEN the system SHALL use plain words with no "Part 4" (for example "Each card keeps its usual guidance, with expected joiners split by persona.").

2.9 WHEN the Results tab is drawn THEN the system SHALL build the Export_Workbook only when the user asks for it (or at least not on every Results render), and SHALL key the cache on a value that cannot be reused by a different run.

2.10 WHEN the "?" help button is shown THEN the system SHALL leave enough bottom space on every tab (at least the button's height plus its offset) that no control or last row can be hidden under it, and SHALL keep the Ask Assistant send button clickable at every window width.

2.11 WHEN the tests are run THEN the system SHALL include tests for `missing_promo_fields`, `missing_persona_split`, `required_message` (empty, partial and complete inputs) and for `theme.model_display` (known model id, unknown id, empty string).

2.12 WHEN a user clicks any button inside an `st-key-p8_btn_*` container (at any depth) or the `persona_suggest` button THEN the system SHALL treat it as a job click: dim and lock the page at once, and keep the pressed state through the loader's finish. `settleMs` SHALL use the same test as `isJobKey`, so Build Personas waits out the finish like Run Analysis. The test SHALL look at all keyed ancestors of the button, not only the nearest.

2.13 WHEN a run exists THEN the system SHALL show Export Summary at the bottom of the Download Leads dropdown, including when there are no sendable leads (the "No sendable leads were produced for this run." note stays, with Export Summary below it).

2.14 WHEN the script is still running after a job click THEN the system SHALL keep the scrim until the loader mounts or the run ends, with a longer safety cap (for example 15 s) instead of 3 s. When no rerun starts at all, the existing idle clear SHALL still apply.

2.15 WHEN the Personas split check fails THEN the system SHALL say the action is building personas (for example "Fill in Split by before building personas. Fields marked * are required."). The New Promo message SHALL stay exactly "Fill in <fields> before running. Fields marked * are required."

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user ticks "I Checked These Figures" and nothing about the run or threshold changes (including switching tabs and normal reruns) THEN the system SHALL CONTINUE TO keep it ticked and the download enabled, and ticking one selection SHALL CONTINUE TO not unlock another.

3.2 WHEN a user downloads leads THEN the system SHALL CONTINUE TO produce the same files, with the same file names (promo id, threshold slug, segment), contents and download keys.

3.3 WHEN a single user runs an analysis THEN the system SHALL CONTINUE TO show the same finishing overlay headline and the same per-run alternating animation as before.

3.4 WHEN Help And FAQs is opened THEN the system SHALL CONTINUE TO show every other entry, every formula and the Where To Go Next buttons unchanged, and the figures in them SHALL CONTINUE TO come from `part4_cards.config`.

3.5 WHEN a Run Analysis succeeds THEN the system SHALL CONTINUE TO land on Results, refresh the header number, store the What-If baseline and segment figures, keep the loader overlay through the rerun, and play the finishing overlay once.

3.6 WHEN the forecast is far above past join rates THEN the system SHALL CONTINUE TO show the forecast caution from `fairness.forecast_caution` using `historical_join_rate`.

3.7 WHEN personas are built THEN the system SHALL CONTINUE TO show persona cards and "Expected Joiners By Persona" exactly as now, with no change to clustering, names or numbers.

3.8 WHEN a user presses Export Summary THEN the system SHALL CONTINUE TO download the same workbook (Summary, Decision Cards, Personas, a Send List per non-Skip segment) with the same file name, and a failure SHALL CONTINUE TO show the plain error message.

3.9 WHEN a user uses the "?" button, toasts or any other control on a window wide enough to show them apart THEN the system SHALL CONTINUE TO look and behave as now, in light and dark mode, including toasts sitting above the "?" button.

3.10 WHEN the existing tests that cover Parts 5, 7, 8 and 9 are run THEN the system SHALL CONTINUE TO pass them (apart from the six known Part 1 Hypothesis timeouts), except for the tests listed in 2.6, which change only because the code they test was deliberately removed.

3.11 WHEN a user clicks Run Analysis THEN the system SHALL CONTINUE TO dim and lock the page on the click, hand the scrim to the loader, hold the pressed state through the finish, and clear the mark when the form is rejected.

3.12 WHEN a user clicks the Suggest button ("Not sure how many?", key `persona_suggest`) THEN the system SHALL CONTINUE TO behave as a job click exactly as now. Buttons outside `st-key-p8_btn_*` and `persona_suggest` (tabs, navigation, downloads, What-If controls) SHALL CONTINUE TO get no scrim and keep the 300 ms settle.

3.13 WHEN a user ticks "I Checked These Figures" and downloads leads THEN the system SHALL CONTINUE TO use the same review sign-off, and the Download Leads rows, picker, file names, contents and download keys SHALL be unchanged. Adding Export Summary to the no-sendable case SHALL NOT add any lead file.

3.14 WHEN a run has sendable leads THEN the system SHALL CONTINUE TO show Export Summary once, at the bottom of the Download Leads dropdown, with the same workbook and file name (3.8).

3.15 WHEN New Promo required fields are missing THEN the system SHALL CONTINUE TO show the same "Fill in ... before running. Fields marked * are required." message, and `required_message` SHALL CONTINUE TO give the same text for its existing callers unless a caller asks for the Personas wording.

## Audit items checked and found not to be defects

- Candidate 4 (rerun after a failed run) is real but only wasteful, not a lost error or a loop, so it is Low (1.5).
- Candidate 10 (`_live_leads_fingerprint` on every render of the persona helper): it sorts about 1,600 client ids, which is negligible. No change.
- Candidate 11 (`page_lock.js` `frameLock`): it stops when the element is removed, when the ending is marked ended, or after 12 s, and only touches animations on frames that ran long. No change.
- Candidate 9, header `_run_forecast()` called twice: it sums a handful of cards, so the cost is negligible. It may be tidied while editing the header but is not a defect.
