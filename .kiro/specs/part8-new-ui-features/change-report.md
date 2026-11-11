# Part 8 Change Report

Branch `part8-new-ui-features`. Presentation only. Streamlit 1.66.1.

## 1. Files

### Added

| File | Purpose |
|---|---|
| `src/webapp_core/region_map.py` | Region_Mapping: four Map_Areas, PSGC codes (outlines only), lead-count entries. Pure. |
| `src/webapp_core/number_roll.py` | Digit-diff plan for the CSS number roll. Pure. |
| `src/webapp_core/group_picker_items.py` | Which Group_Visual fits a run (map, ring, Toggle_Card, none; Multi_Split option A), items, glass level, shortest ring step, component-value sync rule, group-change check. Pure. |
| `app/group_picker.py` | `declare_component` wrapper, palette hand-off, `pending_selection` (read before the dropdown). |
| `app/static/group_picker/index.html`, `picker.js`, `picker.css` | The one iframe component: 3D ring with liquid-glass depth, Toggle_Card, region map. No build step, no external host. |
| `app/static/group_picker/illustrations.svg` | Original flat sprite: 24 value illustrations, 8 distinct yes/no icons, check, cross, placeholder. |
| `app/static/group_picker/ph_regions.svg` | Four dissolved Map_Areas + NCR callout, 27.5 KB, built from the approved geometry. |
| `app/static/group_picker/LICENSE-ph-regions.txt` | Licence notice for the one vendored asset. |
| `app/static/p8_page_lock.js` | Page lock while a job loader is shown (decision A7). |
| `scripts/build_ph_regions.py` | One-off stdlib build of `ph_regions.svg` (edge-cancellation union). |
| `tests/test_part8_tokens_unit.py`, `test_part8_number_roll_unit.py`, `test_part8_region_map_unit.py`, `test_part8_group_picker_unit.py`, `test_part8_assets_unit.py` | Unit and Hypothesis tests. |

### Changed

| File | Change |
|---|---|
| `app/styles.css` | Section 1: new tokens (`--pan-ease-breath`, `--pan-z-loader/-finish/-ring/-toast`, `--pan-dur-toast-delay`). Loader overlay catches clicks and sits above the header. Tab fade fill mode `backwards`. Section 12 (F2) hover rebuilt as one halo. New sections 13 (toasts, stories, finishing overlay, quiet alerts), 14 (number roll), 15 (reveal, crossfade, group visual height). `stMain` focus frame suppressed; `p8_fx` wrapper out of flow. |
| `app/theme.py` | `LoaderHandle` / `loading(...)` keep-on-success; `finishing_overlay_html`; `toast_stack_html`; `completion_story_html`; `roll_number_html`; `hero_kpi_html(prev=)`; `metric_panel(prev=)`; `card(reveal_index=, xfade=)`. Defaults give the old markup. |
| `app/p8_effects.py` | `p8_fx` children (lock, toast slot, finishing overlay), toasts, completion pick-up, `number_prev`, `quiet_container`, `end_job` sets the one-shot. |
| `app/main.py` | Start_Toast, loader keep on success, results saved inside the loader block (keyboard guard), quiet flashes, hero and What-If numbers roll. |
| `app/persona_page.py` | Same job wiring; component value read before the dropdown; reveal and crossfade; Group_Visual after the Demo Mode notice; `P8_LAST_SPLIT`. |
| `src/webapp_core/toast_queue.py` | Toast queue (`Toast`, `ToastView`, `push`, `prune`, `plan_view`, `settle`, `start_text`). |
| `tests/test_part8_toast_queue_unit.py` | Properties 5 and 6 and examples added. |
| `.kiro/specs/part8-new-ui-features/*` | Decisions A3 to A7, design notes, tasks. |

### Deleted

None. The downloaded geometry working file lived outside the repository and was deleted after the build.

### Protected paths

`git diff` shows zero changed lines in `src/part1_optin/`, `src/part2_network/`, `src/part3_segments/`, `src/part4_cards/`, `src/part5_personas/`, `src/run_pipeline.py`, `outputs/`, `data/`, `requirements.txt`. No `pip install`. Widget keys and labels unchanged (new keys only: containers `p8_*`, the component key `p8_group_picker`).

## 2. Changed test expectations

None. No existing assertion was edited. `PALETTE` gained nothing in this round (`MAP_RED`, `MAP_RED_SELECTED` were added in task 1.1 and change no expectation).

## 3. Tests run

| Task | Test files | Result |
|---|---|---|
| F2 smoothing, page lock | `test_part5_theme`, `test_part5_personas_apptest_smoke`, `test_part8_job_motion_unit`, `test_part8_toast_queue_unit` | 32 passed |
| F3 to F9 | the above plus `test_part8_tokens_unit`, `test_part8_number_roll_unit`, `test_part8_region_map_unit`, `test_part8_group_picker_unit`, `test_part8_assets_unit` | see section 7 (final run) |

The six pre-existing Part 1 Hypothesis timeouts are excluded and out of scope.

## 4. Deviations from the design (recorded for review)

1. **Toast element identity.** React reuses a DOM element when the tag at a position is unchanged, so a new toast inherited the previous toast's finished animation clock. Each toast is wrapped in its own custom element (`<p8-toast-tN>`, `display: contents`). The group crossfade alternates two identical keyframes for the same reason.
2. **Completion_Toast timing.** It is queued on the completion render (not before `st.rerun()`, which would have used up its time during the rerun) and enters after `--pan-dur-toast-delay` (ring fill + half the sparks, about 600 ms), as the sparks fade (Requirement 7.7). The reveal starts 80 ms after that (Requirement 17.1).
3. **Ring rendering.** The ring is laid out in 2D by `picker.js` (sin/cos projection, depth by scale and z-index) and animated with requestAnimationFrame on the shared `--pan-ease` curve and `--pan-dur-slow`, instead of a CSS `preserve-3d` ring. Reason: `backdrop-filter` is unreliable inside a 3D context (design Risks), and the JS path rotates along the arc for multi-step moves. Only `transform` moves; glass layers crossfade by `opacity`; blur is never animated.
4. **"By campaign" with a split.** The design table lists level `campaign` as "none", but Requirement 12.8 shows a visual whenever a run yields more than one group. The requirement wins: any run with a split and 2+ groups gets its visual.
5. **Quiet alerts.** Streamlit 1.66.1 alerts do not expose their kind in the DOM, so success and warning flashes are wrapped in keyed containers (`p8_quiet_<level>_<n>`). Text, role and trigger are unchanged.
6. **Number roll units.** Cells are `1lh` tall so roll and static markup share one line box; roll markup is drawn only on the render where the text changed.
7. **Page lock.** Uses `st.components.v1.html` to copy one script into the main page. Streamlit 1.66.1 logs that `components.v1.html` will be replaced by `st.iframe`; it still works. If it is removed, the CSS click block remains.

## 5. Streamlit internals used (1.66.1)

See design.md, "Streamlit internals used", plus: alert test ids `stAlertContainer`, `stAlertDynamicIcon`; component protocol messages; `components.html` iframe `allow-same-origin`.

## 6. Fonts

No licensed Dax or Avenir Next files are in `app/static/fonts`. `--pan-font-display` (FF Dax) and `--pan-font-body` (Avenir Next) render their fallback stacks as defined in `app/theme.py`. The picker iframe uses the font Streamlit passes in its render message.

## 7. Browser checklists

"Verified" = checked by Claude in headless Chrome 1.66.1 (screenshots and DOM/animation state). Motion *feel* cannot be judged headless, so every motion item still needs the reviewer. For each feature also check: light, dark, Reduced_Motion on, off, and no replay on an unrelated rerun.

**Page lock (A7)**
- [x] Verified: during Run Analysis and Build Personas, clicks hit nothing, Tab reaches nothing (skip link included), the top-right menu is under the scrim; unlocks when the loader goes.
- [x] Verified: wheel scrolling works while locked; the loader stays fixed and visible.
- [ ] What-If slider rescore locks the page (same loader; not driven headless).

**F2 Job buttons**
- [ ] Hover breath: one soft halo, about 1.6 s, no bounce at the small end, fades out from any phase; label still.
- [ ] Press dips to about 0.97 and releases; ring starts right after; constant-speed loop; fill, glow, sparks; error fades.
- [ ] Space during a job: one result, one flash, no second run.

**F3 Toasts and stories**
- [x] Verified: Start_Toast "Running analysis for NEW-001..." rises in bottom-right above the scrim and dismisses after about 4 s.
- [x] Verified: finishing overlay appears on the completion render and fades; Completion_Toast "Analysis complete" enters about 0.6 s later; the magnifier story ends on the lens with a green check.
- [x] Verified: success flash renders quietly (compact, tinted, no icon).
- [ ] Persona squares story (gooey merge into two blobs, "Personas ready").
- [ ] Hover over a toast pauses it; a rerun mid-toast continues it without replay.

**F5 Animated numbers**
- [ ] Run Analysis twice with different inputs: hero Expected Joiners rolls about 600 ms from the old value; no reflow.
- [ ] Move the What-If slider: the headline rolls; an unrelated rerun shows it static.

**F8 Reveal and crossfade**
- [x] Verified: after a successful build the persona cards carry the one-shot reveal class (3 of 3); it is gone on the next rerun.
- [ ] The rise and stagger start as the Completion_Toast enters; tables do not move.
- [ ] Changing the group (dropdown or visual) fades the cards in once, 150 ms, each time.

**F7 Ring and Toggle_Card** (verified in an isolated harness with the real component)
- [x] Verified: 5-item ring: front sharp with selected outline, neighbours frosted (level 1), far items more frosted (level 2); rotate-right sets the dropdown to the new front; live region announces "25-34, 637 leads".
- [x] Verified: yes/no Toggle_Card: column icon, check (Yes) and cross (No), counts; selecting "Yes" sets the group.
- [x] Verified: two-value Toggle_Card (Salary / Business) with value illustrations.
- [x] Verified: same 360 px reserved height for ring, Toggle_Card and map; light and dark palettes.
- [ ] Ring rotation feel (shortest direction, glass defrost in step); dropdown change rotates the ring; reduced motion makes it instant.

**F6 Map**
- [x] Verified: four dissolved areas, no internal borders visible at 1x, lattice continuous, NCR bubble with leader line, credit "NAMRIA, PSA via OCHA" below.
- [x] Verified: clicking Visayas selects it (fill, lift) and dims the rest; the dropdown follows.
- [ ] Hover lift and shadow; 2x zoom seam check; keyboard tab order NCR, Luzon, Visayas, Mindanao.

**F9 Multi-split**
- [x] Verified: 8 combined groups give one ring labelled "Mass · 25-34" with the first column's illustration.
- [ ] More than 12 combined groups: dropdown only, no iframe.

**Requirement 22 (seamless transitions) items 1 to 19:** see design.md section "j. Browser checklist" items 1 to 16; items 1, 2, 12 and 14 verified as above (scan test, reserved height, stale override, overlay exit); the rest are for the reviewer.

## 8. Final test run

`test_part5_theme`, `test_part5_personas_apptest_smoke`, and every `tests/test_part8_*_unit.py` (tokens, toast_queue, job_motion, number_roll, region_map, group_picker, assets): **67 passed, 0 failed**. Only `picker.js` (no Python test covers it) changed after that run. The six pre-existing Part 1 Hypothesis timeouts were not run and are out of scope.

## 9. Notes for the reviewer

- Four other `streamlit run app/main.py` servers were running on this machine during testing (not started by Claude). They slowed every run (persona builds took minutes); close unused ones.
- The header-removal confirmation (Requirement 6.8): "You are in Campaign Analytics" and the top brand line are gone; the hero title is the only on-screen "Promo Audience Navigator" (verified in screenshots).
- Map in dark mode: the dimmed areas (lattice at 0.6 opacity) are low contrast on the dark page; if that reads too faint, raise `--pan-dim` or the dark lattice tones.
