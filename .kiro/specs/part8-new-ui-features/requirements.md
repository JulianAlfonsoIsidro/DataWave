# Requirements Document

## Introduction

Part 8 adds presentation features to the DataWave Promo Audience Navigator (the Streamlit webapp in `app/`). It removes two redundant header lines, gives the two long-running buttons a running state, adds stacked toasts with short completion animations, restyles text inputs, animates a small set of headline numbers, and adds a clickable Philippine map, a 3D carousel, and a two-option Toggle_Card that pick the persona group on the Personas tab. It also reveals the Personas results in a short sequence after Build Personas, and defers the multi-category split visual to an approved design option.

Guiding principle: less is more. Every animation has a job: show progress, confirm a result, or show where something came from. Motion is fluid (ease-out, no linear tweens) and short, and never decorative. Where a feature can be built two ways, the design chooses the simpler one and states why.

Decisions recorded after review:

- Tokens: `app/styles.css` section 1 stays the single source for new colour, motion, easing, radius, and spacing tokens (as `light-dark()` pairs where relevant); `app/theme.py` only exposes helpers and token names, with no migration.
- Iframe colours: the Group_Component receives every colour from Python and holds no hex colour literals.
- Illustrations: flat, simple, one accent colour, light life-stage cues, at most one prop per figure, no frailty cues, no stereotypes.
- Age bands: graduation cap (18-24), laptop or phone (25-34), young child or family (35-44), house keys or a home (45-54), grey hair or glasses with a newspaper, garden, or grandchild (55+).
- Any single split column with exactly two values in a run uses a Toggle_Card, not the 3D ring; the ring is for a single non-region column with 3 or more values.
- Region map: four clickable Map_Areas (NCR, Luzon, Visayas, Mindanao), each one solid dissolved outline with no internal region borders, with NCR also shown as an enlarged, clickable inset bubble tied to its true location by a leader line.
- Header: `theme.header()` and `theme.nav_bar()` stay in `theme.py`; neither "You are in Campaign Analytics" nor a top brand line appears on screen.
- Flash messages: `st.success` and `st.warning` keep their text and role but are styled quietly so they read below the Completion_Toast.
- Approved values: map hover lift about 3 px, unselected Map_Areas dim to about 60%, at most 3 Toasts visible, number roll about 600 ms.
- Gates closed: the Motion_Exceptions, third-party files, Illustration_List, Region_Mapping, Animated_Number_List, and Multi_Split_Options are approved as recorded in Requirement 1.14; a departure from an approved item still needs approval (Requirement 1.11).
- Motion exceptions: all three Motion_Exceptions are approved as designed with their reduced-motion versions, plus a fourth: a static (non-animated) `backdrop-filter` on carousel Glass_Layers. No other exception is allowed.
- Region outlines: the approved 18-shape-to-4-area mapping is used only to build the dissolved outlines; the lattice runs unbroken across each whole area.
- Two-value columns: any single column with exactly two values in a run gets the Toggle_Card; a run with 0 or 1 group shows neither the Group_Visual nor the Group_Dropdown.
- Icons: all 13 non-region split columns are named in Requirement 16, and the 8 yes/no columns each have their own distinct icon.
- Text inputs: a thin outline of about 1 px from a Design_Tokens_Block token surrounds the Input_Pill, and the low-saturation underline and end line are removed.
- Carousel depth: non-front ring items sit behind a Glass_Layer (liquid-glass blur, tint, edge highlight, soft shadow) that frosts further with distance from the front; the front item is clear and sharp.
- Seamless transitions: Requirement 22 makes every state change one continuous flow, with reserved space, shared motion tokens, and no jump or flash.
- Start_Toast text: the analysis Start_Toast uses the Promo ID, and the persona Start_Toast reads "Building personas for all leads..." when no split is chosen.
- No Completion_Toast: none is shown for the empty-audience warning or a missing-model error.
- Animated numbers: only hero Expected Joiners and the What-If headline animate, through a CSS-only roll; NumberFlow and Sonner are not used, and toasts and numbers are plain CSS.
- Multi-split: option A is approved (one ring of combined groups, capped at 12, Group_Dropdown only above 12).
- Loader and sync: the existing loader overlay is kept, and the Group_Component value is read before the Group_Dropdown is created, with no extra rerun.
- Group change: a change of the Selected_Group plays only the Group_Change_Crossfade (opacity only, about 150 ms, once, on the render where the group changed) and never the Results_Reveal (Requirements 5.4 and 22).
- Loader exit: on a successful Job the loader overlay is drawn one final time in a finishing state that fades out with a CSS-only animation while the Completion_Toast arrives; no finishing overlay on error (Requirement 22).
- Dropdown to visual sync: a Group_Dropdown change moves the Group_Visual smoothly to the matching group, so the two never show different groups (Requirement 12).
- Streamlit internals: the design document records Streamlit 1.66.1 and lists every Streamlit internal selector or attribute Part 8 uses (Requirement 22).
- Two-group splits: a region split with two groups shows the Region_Map, not a Toggle_Card; a Multi_Split with exactly two combined groups shows a Toggle_Card labelled with the combined values.
- Category list: the category list in the design document is approved as written.
- A1 (F2 redesign, motion exceptions): after testing F2 the user approved three more exceptions, and only these: the Hover_Breath loop on Job_Buttons, constant-speed (linear) timing with `stroke-dashoffset`/`stroke-dasharray` for the running ring loop only, and one-shot Completion_Fireworks (Requirement 4.12 to 4.14). The rotating conic-gradient trace and the container Soft_Pulse are superseded.
- A2 (F2 redesign, sequence): Requirement 7 now describes hover breath, press, a seamless constant-speed running ring, a fill-and-sparks finish on success, a fade-out on error, a static ring under Reduced_Motion, and a guard against a keyboard double run within 1.5 s.
- A3 (F4 width): the Input_Pill width change stays instant; a smooth width would need JavaScript and is out of scope unless approved later (Requirement 10.14). Reconfirmed by the user on 2026-11-10.
- A4 (F2 breath easing, approved 2026-11-10): the Hover_Breath loop uses its own symmetric ease-in-out token `--pan-ease-breath` (`cubic-bezier(0.37, 0, 0.63, 1)`) instead of `--pan-ease`, because an ease-out curve on an alternate loop turns around at full speed and reads as a bounce. Used by the breath loop only.
- A5 (F2 label colour, approved 2026-11-10): when the Running_State starts or ends, the Job_Button label colour may transition over `--pan-dur` with `--pan-ease`, in step with the disabled plate crossfade. This is the only colour transition allowed by Requirement 4.3.
- A6 (F2 keyboard double run, approved 2026-11-10): each Job stores its results, flash messages and job-end record inside the loader block, before the loader's cleanup makes the next Streamlit call, so a keypress queued during the Job (which interrupts the run at that call) is caught by the Requirement 7.12 guard on the next run. Lines are reordered only; no logic changes.
- A7 (page lock, approved 2026-11-10): while a job loader is shown (Run Analysis, Build Personas, What-If rescore), the user can use nothing else on the page: no click, no Tab, Enter or Space, and not the top-right menu (which now sits under the loader scrim). The overlay catches clicks from the moment it is drawn, and a small main-page script (`app/static/page_lock.js`, injected once per run through a zero-height `components.html` iframe) sets `inert` on the page while `.pan-loading:not(.is-finishing)` exists and removes it when the loader goes. Scrolling stays allowed (user, 2026-11-10): `stMain`, the scroll container, stays live and only its children are inert, so wheel and touchpad scrolling still move the page. This is the one approved exception to "no script in the main page". A Cancel button was considered and dropped by the user (it would have needed the Job on a background thread that cannot be stopped).

Scope and constraints that apply to every requirement:

- Presentation only. Part 1 to 4 modules, `src/run_pipeline.py`, `outputs/`, `data/`, backend calculations, widget keys, the wording in `labels.py`, and all `part5_personas` behaviour stay unchanged.
- No `pip install`. No asset is loaded from a CDN at runtime.
- The BPI logo, wordmark, and any asset copied or traced from BPI are never used. Reference images attached by the user are used for colour, mood, silhouette, and style only.
- The process in `.kiro/steering/ui-guidelines.md` applies per task: read the code, propose the design, wait for approval, implement, run only the affected tests plus `tests/test_part5_personas_apptest_smoke.py` and `tests/test_part5_theme.py`, then report.
- The six pre-existing Part 1 Hypothesis timeouts are out of scope.

Repository facts these requirements build on (inspected before writing):

- `app/main.py` `main()` calls `theme.utility_bar()` (the "You are in Campaign Analytics" line), `theme.nav_bar()` (the "Promo Audience Navigator" brand line), and `theme.context_banner()`, then renders the hero with `theme.hero_text_html("Promo Audience Navigator", ...)` and the hero KPI panel (`theme.hero_kpi_html`, "Expected Joiners").
- `tests/test_part5_theme.py` calls `theme.nav_bar()` and `theme.header()` directly and checks `theme.APP_TITLE == "Promo Audience Navigator"`. It does not render `main.py`.
- "Run Analysis" is an `st.form_submit_button` inside `st.form("new_promo_form")`. "Build Personas" is `st.button("Build Personas", type="primary", key="persona_run")`. Both jobs run inside `theme.loading(...)`, which shows the existing loader overlay: documents under a magnifier for analysis and rescore, and swapping red and gold squares for personas.
- After each job the page stores flash messages in session state (`flash_messages`, and the persona flash key) and calls `st.rerun()`. The flash messages render as `st.success` and `st.warning` alerts. AppTest smoke tests assert on the persona success alert text ("Built 2 personas").
- `app/styles.css` section 1 ("design tokens") holds every colour as a `light-dark()` pair plus radius, spacing, and motion tokens (`--pan-dur-fast` 120 ms, `--pan-dur` 180 ms, `--pan-dur-slow` 250 ms, `--pan-ease`). `app/theme.py` holds the type tokens and `PALETTE`, which tests compare against `.streamlit/config.toml`.
- `.streamlit/config.toml` sets `enableStaticServing = true`, so files in `app/static/` are served by the app.
- The Personas tab group dropdown is `st.selectbox("Show group", ..., key="persona_group_select")`. Its options are the persona set group keys in run order followed by "All groups". It appears only when a run yields more than one group. The "Demo Mode" badge renders at the top of the persona summary cards when persona text came from the Mock.
- The split control offers 14 columns: `segment`, `age_band`, `region`, `sec_class`, `inflow_type`, `digital_app_user`, `online_shopper`, `frugal_flag`, `email_valid`, `mobile_valid`, `owns_Credit Card`, `owns_Insurance`, `owns_Investment`, `owns_Loan`.
- The `region` column holds four values, which are island groups and NCR, not the 17 administrative regions: NCR (891 clients), Luzon (506), Visayas (362), Mindanao (241). The map therefore needs a mapping from these four values to groups of administrative-region shapes. A starting proposal for the design to confirm: NCR to the NCR shape; Luzon to CAR, Regions I, II, III, IV-A, MIMAROPA and V; Visayas to Regions VI, VII, VIII and the Negros Island Region if the source has it; Mindanao to Regions IX to XIII and BARMM.
- Other split values in the data: `age_band` 18-24, 25-34, 35-44, 45-54, 55+; `segment` Affluent-Gold, Affluent-Preferred, Mass, Mid-Market; `sec_class` A, B1, B2, C1, C2, D; `inflow_type` Business, Mixed, Remittance, Salary; `online_shopper` Low, Medium, High, Very High, Ultra High; the yes/no columns hold 0 and 1.

## Glossary

- **Webapp**: The Streamlit application rooted at `app/main.py`, including all its tabs.
- **Personas_Tab**: The Personas tab rendered by `app/persona_page.py`.
- **Design_Tokens_Block**: Section 1 ("design tokens") at the top of `app/styles.css`. It is the single home for colour, radius, spacing, motion, and easing tokens, with `light-dark()` pairs for colours. `app/theme.py` keeps the type tokens and only exposes helpers and token names to Python; no existing token is migrated.
- **Page_Code**: Python and markup in `app/` outside the Design_Tokens_Block and outside `app/theme.py` type tokens, plus any static HTML, CSS, or JS added under `app/static/` for this feature.
- **Micro_Interaction**: A hover, press, focus, chip, or toast enter or leave transition.
- **Motion_Exception**: One of the approved animations or effects outside the Micro_Interaction budget: the Border_Trace loop, the Gooey_Merge filter, the Completion_Story, the static (non-animated) `backdrop-filter` on carousel Glass_Layers, and (approved in the F2 redesign) the Hover_Breath loop and the Completion_Fireworks.
- **Reduced_Motion**: The state in which the browser reports `prefers-reduced-motion: reduce`.
- **Job_Button**: Either the "Run Analysis" button on New Promo or the "Build Personas" button on the Personas_Tab.
- **Job**: The computation started by a Job_Button: the promo analysis run or the persona build.
- **Running_State**: The visual and interactive state of a Job_Button while its Job runs.
- **Border_Trace**: A thin red line that travels at constant speed around the rounded border of a Job_Button while its Job runs (the running ring), drawn on an overlay and never on the button label.
- **Soft_Pulse**: Superseded by the F2 redesign and no longer used; the former container scale pulse while a Job runs.
- **Hover_Breath**: A soft glow layer behind a Job_Button label that scales between 1.00 and at most 1.02 in a loop of about 1.6 s per breath while the pointer is over the Job_Button, and eases back to rest when the pointer leaves.
- **Completion_Fireworks**: A one-shot burst of 8 to 12 short streaks or dots from the Job_Button border after a successful Job, lasting 500 to 700 ms.
- **Toast**: A small notification card shown bottom-right in the browser viewport, styled after Sonner.
- **Toast_Stack**: The ordered set of visible Toasts.
- **Start_Toast**: The Toast shown when a Job starts.
- **Completion_Toast**: The Toast shown when a Job finishes successfully, carrying a Completion_Story.
- **Completion_Story**: A short one-shot animation inside a Completion_Toast that continues the existing loader motif into a result: the magnifier story for analysis ("Analysis complete") and the squares story for personas ("Personas ready").
- **Gooey_Merge**: An SVG filter (blur plus colour-matrix threshold) that makes shapes appear to merge like blobs.
- **One_Shot_Flag**: A session-state value set when a Job finishes, read and cleared on the next render, that permits an entry animation to play once.
- **Unrelated_Rerun**: Any Streamlit rerun not caused by a Job finishing, for example a widget change, a carousel arrow click, a map region click, or a dropdown change.
- **Group_Change_Crossfade**: A short opacity-only crossfade of about 150 ms on the persona cards area that plays only on the render where the Selected_Group changed (from the Group_Dropdown, a Map_Area, a ring step, or a Toggle_Card option). It also applies to the comparison table and the Expected Joiners By Persona section only where they are not tables; tables stay still per Requirement 4.8. It has no rise and no stagger, and it is distinct from the Results_Reveal.
- **Text_Entry_Widget**: Any `st.text_input` or `st.text_area` rendered by the Webapp.
- **Input_Pill**: The soft background shape behind the typed text of a Text_Entry_Widget, whose width follows the text and has a minimum width.
- **Animated_Number**: A headline number rendered with a CSS-only roll so that a change in value animates between the old and new value.
- **Animated_Number_List**: The exact set of numbers that become Animated_Numbers: hero Expected Joiners and the What-If headline.
- **NumberFlow**: The NumberFlow library (https://number-flow.barvian.me/), which is not used; the Animated_Number roll is CSS-only.
- **Group_Visual**: The Region_Map, the Group_Carousel, or the Toggle_Card shown on the Personas_Tab for the current split.
- **Group_Component**: The single bidirectional Streamlit custom component, declared with `components.declare_component(path=...)` pointing at a static `index.html` under `app/static/` with no npm build, that renders the Region_Map, the Group_Carousel, and the Toggle_Card, and reports the chosen group back to Python.
- **Toggle_Card**: A two-option card for any single split column that has exactly two values in the current run. For a yes/no column (values 0 and 1) it shows the column's own icon with a check option (1) and a cross option (0). For any other two-value column it shows the two values side by side, each with its value Group_Illustration and plain-words label. Selecting an option sets the Selected_Group like the Group_Dropdown. The Toggle_Card has no Glass_Layer.
- **Group_Dropdown**: The existing Streamlit-native "Show group" selectbox with key `persona_group_select`.
- **Selected_Group**: The session-state value bound to the Group_Dropdown; it decides which group's persona cards render.
- **Region_Map**: A minimalist map of the Philippines that shows exactly four Map_Areas (NCR, Luzon, Visayas, Mindanao) plus the NCR callout bubble, shown when the split is `region`.
- **Map_Area**: One `region` data value (for example, Visayas) drawn as a single solid dissolved outline, built by merging the administrative-region shapes that the Region_Mapping assigns to it, with no internal region borders drawn. The NCR Map_Area also includes the NCR callout bubble.
- **Region_Mapping**: The pure mapping from `region` data values to Map_Areas, kept in `src/webapp_core/`.
- **Diamond_Lattice**: An original, generic red diamond-lattice SVG `<pattern>` in map coordinates used to fill the Map_Areas as one seamless texture, not traced from any BPI asset and not derived from any logo.
- **Group_Carousel**: A 3D circular carousel (the ring) of illustrations, one per category value, shown when the split is a single non-region column with 3 or more values.
- **Glass_Layer**: A liquid-glass layer drawn in front of a non-front Group_Carousel item, made of `backdrop-filter: blur() saturate()` (with the `-webkit-` prefix), a light translucent tint, a thin bright inner edge highlight, and a soft shadow, with every colour and value taken from Design_Tokens_Block tokens defined for light and dark.
- **Group_Illustration**: One simple, original, flat SVG illustration for one category value, or one distinct icon for one yes/no column's Toggle_Card.
- **Illustration_List**: The list of every value of each non-region split column with 3 or more values (`segment`, `age_band`, `sec_class`, `inflow_type`, `online_shopper`) with its Group_Illustration concept, plus exactly one distinct icon concept for each yes/no column (`digital_app_user`, `frugal_flag`, `email_valid`, `mobile_valid`, `owns_Credit Card`, `owns_Insurance`, `owns_Investment`, `owns_Loan`). The concepts are approved; the design adds the remaining icons for the user to see.
- **Results_Reveal**: The staged entry of the Group_Visual and persona cards after a successful persona build.
- **Multi_Split**: A split that uses more than one category column.
- **Multi_Split_Options**: The 2 or 3 design options for showing a Multi_Split, with one recommended. Option A (one ring of combined groups) is approved.
- **Vendored_Asset**: A third-party JS, CSS, font, or geometry file copied into `app/static/` so the Webapp works offline. The only approved Vendored_Asset is the faeldon/philippines-json-maps geometry file.
- **Asset_Register**: The list in the design document of every proposed third-party asset with source URL, version, and licence.
- **Change_Report**: The final report listing files changed, every changed test expectation with its reason, and a browser checklist per feature.

## Requirements

### Requirement 1: Approval Gates

**User Story:** As the product owner, I want the risky choices shown to me before they are built, so that nothing off-brand, unlicensed, or overdone ships without my yes.

#### Acceptance Criteria

1. THE design document SHALL list each of the three Motion_Exceptions (Border_Trace loop, Gooey_Merge, Completion_Story) with its job (show progress, confirm a result, or show where something came from), its duration in milliseconds, its easing curve, and its Reduced_Motion behaviour. Implementation of each Motion_Exception SHALL start only after the design document records the user's approval of that Motion_Exception.
2. IF the user rejects a Motion_Exception, THEN THE design document SHALL record a fallback for it that runs for 120 to 250 ms with an ease-out curve, animates only `transform` and `opacity`, and states its Reduced_Motion behaviour, and the implementation SHALL use that fallback in place of the rejected Motion_Exception.
3. THE design document SHALL contain an Asset_Register entry with source URL, version, and licence for every proposed Vendored_Asset and every other third-party asset. Each asset SHALL be copied into the repository only after the design document records the user's approval of its Asset_Register entry, and SHALL be loaded at runtime only from the Webapp's own server.
4. THE design document SHALL contain the full Illustration_List, with one Group_Illustration concept for every value of each non-region split column that has 3 or more values (`segment`, `age_band`, `sec_class`, `inflow_type`, `online_shopper`) and exactly one icon concept for each yes/no column, and Group_Illustrations SHALL be drawn only after the design document records the user's approval of the Illustration_List.
5. THE design document SHALL contain the proposed Region_Mapping covering the four current `region` values (NCR, Luzon, Visayas, Mindanao), with each `region` value that has no Map_Area and each administrative-region shape in the approved source that belongs to no Map_Area flagged as unmatched. The Region_Map SHALL be built only after the design document records the user's approval of the Region_Mapping.
6. THE design document SHALL contain the Animated_Number_List, naming each number and the tab where it appears, and numbers SHALL be animated only after the design document records the user's approval of the Animated_Number_List.
7. THE design document SHALL contain 2 or 3 Multi_Split_Options with exactly one marked as recommended, and Multi_Split visuals SHALL be built only after the design document records the user's choice of exactly one option.
8. IF a feature has two candidate approaches, THEN THE design document SHALL name both approaches, choose the one that needs fewer Vendored_Assets (and, when tied, fewer iframes, then fewer new files), and state the reason for the choice.
9. THE design document SHALL describe each user-attached reference image and list each value sampled from it (colour, radius, shadow, or spacing), with each sampled value labelled approximate and mapped to the Design_Tokens_Block token it informs.
10. IF the user rejects or asks for changes to an Asset_Register entry, the Illustration_List, the Region_Mapping, the Animated_Number_List, or the Multi_Split_Options, THEN THE design document SHALL record a revised proposal for that item, and implementation of that item SHALL not start until the design document records the user's approval of the revised proposal.
11. IF implementation would depart from an approved item (a changed duration, easing, asset version, illustration concept, Map_Area assignment, animated number, or Multi_Split option), THEN THE design document SHALL record the change, and the changed part SHALL be implemented only after the design document records the user's approval of the change.
12. IF the user attaches no reference image, THEN THE design document SHALL state that no reference image was provided and SHALL list no sampled values.
13. THE design document SHALL record the following values as already approved, so that they need no further approval gate: Map_Area hover lift of 3 px, unselected Map_Area opacity of 0.6, a maximum of 3 visible Toasts, an Animated_Number roll of about 600 ms, the age-band cues in Requirement 16, and the Toggle_Card for two-value columns. The gates in criteria 1, 3, 4, 5, 6, and 7 (Motion_Exceptions, third-party files, Illustration_List, Region_Mapping, Animated_Number_List, and Multi_Split_Options) are closed by the approvals in criterion 14.
14. THE design document SHALL record the following as approved by the user, so that the gates in criteria 1, 3, 4, 5, 6, and 7 are closed:
    - Motion_Exceptions: the Border_Trace, the Gooey_Merge, and the Completion_Story, as designed and with their Reduced_Motion versions, plus a fourth: a static (non-animated) `backdrop-filter` on Group_Carousel Glass_Layers. No other Motion_Exception is approved.
    - Asset_Register: only faeldon/philippines-json-maps v1.1.1 (MIT licence; underlying boundaries CC BY-IGO), with the credit "NAMRIA, PSA via OCHA" shown below the map. NumberFlow and Sonner are not used.
    - Illustration_List: the illustration concepts, under the no-stereotype rule of Requirement 16. The design adds the remaining icons (one distinct icon for each of the 8 yes/no columns) for the user to see.
    - Animated_Number_List: hero Expected Joiners and the What-If headline only, rolled with CSS only.
    - Region_Mapping: approved for building the dissolved outlines only.
    - Multi_Split_Options: option A, one ring of combined groups capped at 12, with the Group_Dropdown only above 12.
    - D1: the existing loader overlay is kept.
    - D2: the analysis Start_Toast uses the Promo ID ("Running analysis for <Promo ID>..."), and the persona Start_Toast reads "Building personas for all leads..." when no split is chosen.
    - D3: no Completion_Toast is shown for the empty-audience warning or a missing-model error.
    - D4: text inputs get a thin outline.
    - D5: any single column with exactly two values in a run uses the Toggle_Card, and a run with 0 or 1 group shows neither the Group_Visual nor the Group_Dropdown.
    - Number inputs keep a fixed width with the same fill and outline as the Input_Pill.
    - Toasts and numbers are plain CSS.
    - Component sync: THE Webapp reads the Group_Component value before the Group_Dropdown is created, with no extra rerun.
    - F2 redesign Motion_Exceptions: the Hover_Breath loop, linear timing with `stroke-dashoffset`/`stroke-dasharray` for the running ring loop only, and the Completion_Fireworks (Requirement 4.12 to 4.14). The rotating conic-gradient Border_Trace and the Soft_Pulse are superseded.

### Requirement 2: Presentation-Only Scope

**User Story:** As a developer, I want Part 8 to touch only the presentation layer, so that model results, exports, and persona behaviour stay exactly as they are.

#### Acceptance Criteria

1. WHEN the Webapp is given the same inputs before and after Part 8, THE Webapp SHALL produce identical run results (every lead's `p_join`, top-3 drivers, and segment label), persona results (persona count, membership, names, descriptions, and recommended actions), decision cards (every displayed field and value), and flash message text. "Same inputs" means the same `data/` files, the same fitted model and artifacts in `outputs/`, and the same widget values.
2. WHEN the user downloads any file from the Webapp with the same inputs before and after Part 8, THE Webapp SHALL produce a file with the same name, the same columns in the same order, and the same row values in the same order.
3. THE Part 8 changes SHALL leave the following with zero changed lines in a diff against the pre-Part 8 commit: the Part 1 to 4 modules (`src/part1_optin/`, `src/part2_network/`, `src/part3_segments/`, `src/part4_cards/`), `src/run_pipeline.py`, every file in `outputs/` and `data/`, the label wording in `labels.py`, and every module in `part5_personas`.
4. THE Part 8 changes SHALL keep every widget key and every visible widget label that exists before Part 8 character-for-character unchanged, including the "Run Analysis" form membership in `new_promo_form`, the `persona_run` key, and the `persona_group_select` key.
5. THE Part 8 changes SHALL place every new pure logic function, including the Region_Mapping, in `src/webapp_core/`, with zero Streamlit imports in any file under `src/webapp_core/`.
6. THE Part 8 changes SHALL place all new Streamlit widget, session-state, and component wiring in `app/`.
7. THE Part 8 changes SHALL install no package and SHALL leave `requirements.txt` with zero changed lines in a diff against the pre-Part 8 commit.
8. IF a Part 8 change would require modifying any item named in criteria 3, 4, or 7, THEN THE design document SHALL name the item and the reason, and the change SHALL start only after the user approves it.
9. WHEN a Part 8 task is complete, THE Webapp SHALL pass `tests/test_part5_personas_apptest_smoke.py`, `tests/test_part5_theme.py`, and the affected tests, and THE Change_Report SHALL list every changed test expectation with its reason. The six pre-existing Part 1 Hypothesis timeouts are excluded.

### Requirement 3: Design Tokens

**User Story:** As a developer, I want every new colour, radius, spacing, and duration to come from one place, so that light and dark mode stay consistent and easy to tune.

#### Acceptance Criteria

1. THE Design_Tokens_Block SHALL define every colour, radius, spacing, shadow, easing, and motion duration token that Part 8 adds, where "added" means a token name not present in the Design_Tokens_Block before Part 8, and each added token name SHALL start with the existing `--pan-` prefix.
2. THE Design_Tokens_Block SHALL define each colour token added by Part 8 as one `light-dark()` pair that holds both a light value and a dark value, and each shadow token that contains a colour SHALL take that colour from a `light-dark()` colour token.
3. THE Page_Code SHALL reference colours, radii, spacing, shadows, easings, and durations only through Design_Tokens_Block custom properties, and SHALL contain zero hex colour literals, zero `rgb()`, `rgba()`, `hsl()`, or `hsla()` colour literals, zero named colours other than `transparent` and `currentColor`, and zero literal `ms` or `s` duration values in Part 8 animations and transitions.
4. THE Page_Code SHALL reference fonts only through the `--pan-font-*` and `--pan-type-*` tokens that `app/theme.py` defines, and SHALL contain zero font family names.
5. WHERE a static file under `app/static/` runs inside an iframe that cannot read the parent page's custom properties, THE Group_Component SHALL receive the token values, both the light value and the dark value of each colour token, from Python helpers in `app/theme.py` that read the Design_Tokens_Block, and each received value SHALL equal the value in the Design_Tokens_Block for the same token name.
6. IF a Python helper in `app/theme.py` is asked for a token name that the Design_Tokens_Block does not define, or the helper cannot read the Design_Tokens_Block, THEN THE helper SHALL raise an error that names the missing token or the unreadable block, and SHALL return no fallback value.
7. THE `PALETTE` values in `app/theme.py` and the `[theme]` colours in `.streamlit/config.toml` SHALL stay equal to the light values of the matching tokens in the Design_Tokens_Block, where equal means the same hex value compared case-insensitively.
8. IF a Part 8 change makes a `PALETTE` value or a `[theme]` colour differ from the light value of its matching Design_Tokens_Block token, THEN `tests/test_part5_theme.py` SHALL fail and name the differing value.
9. WHERE a new Part 8 colour token is one that the light-mode `PALETTE` mirror in `app/theme.py` should track (for example the map reds), THE `PALETTE` SHALL gain an entry equal to that token's light value, and THE Change_Report SHALL list any test expectation that changed as a result or state that none changed.
10. THE Group_Component SHALL receive every colour value from Python through `app/theme.py` helpers that read the Design_Tokens_Block, and SHALL contain zero hex colour literals in their HTML, CSS, or JS files.
11. THE `app/theme.py` module SHALL only expose helpers and token names for the Design_Tokens_Block, and Part 8 SHALL migrate no existing token out of the Design_Tokens_Block.

### Requirement 4: Motion Budget And Reduced Motion

**User Story:** As a campaign planner, I want motion that is short and purposeful and that switches off when I ask my system for less motion, so that the tool stays calm.

#### Acceptance Criteria

1. THE Webapp SHALL run every Micro_Interaction for 120 to 250 ms inclusive, taking its duration from the `--pan-dur-fast`, `--pan-dur`, or `--pan-dur-slow` token in the Design_Tokens_Block and its easing from the `--pan-ease` token or the CSS `ease-out` keyword.
2. THE Webapp SHALL use no linear timing function in any Part 8 animation or transition, meaning no `linear` keyword, no `linear()` function, and no `cubic-bezier()` value equivalent to linear timing in Part 8 CSS or JS, except for the Job_Button running ring loop (Border_Trace), which uses constant-speed timing because easing a loop stutters at each lap.
3. THE Webapp SHALL animate only `transform` and `opacity` in Part 8 animations and transitions, and SHALL animate no `width`, `height`, `margin`, `padding`, `box-shadow`, `filter`, colour, or background property, except for the approved Motion_Exceptions: `stroke-dashoffset` and `stroke-dasharray` on the running ring SVG for the Border_Trace and its completion fill (replacing the former conic-gradient rotation), the Gooey_Merge filter inside the persona Completion_Story, a static (non-animated, never transitioned) `backdrop-filter` on Group_Carousel Glass_Layers, and the Job_Button label colour transition at the start and end of the Running_State (decision A5).
4. THE Webapp SHALL draw the Hover_Breath glow on the Job_Button as a pseudo-element that appears and fades only through `opacity` and `transform`, and SHALL resize the Input_Pill with no transition, so that neither feature animates `width` or `box-shadow`.
5. THE Webapp SHALL limit each Completion_Story to 1.6 s or less, measured from the Completion_Story's first animated frame to its final frame.
6. WHILE a Job runs, THE Webapp SHALL loop the Border_Trace on that Job's Job_Button, and WHEN that Job ends, THE Webapp SHALL end the loop as Requirement 7 describes and return the Job_Button to its rest style.
7. THE Webapp SHALL play every Part 8 animation other than the Border_Trace loop and the Hover_Breath loop at most once per trigger, where a trigger is one Job finishing, one change in an Animated_Number's value, or one user hover, press, focus, select, or rotate action.
8. THE Webapp SHALL render tables and charts, including `st.dataframe`, the Past Promos rate tables, and the Expected Joiners By Persona tables, with no Part 8 transition, keyframe animation, or Results_Reveal entry applied to the table or chart element or its cells.
9. THE Webapp SHALL treat the Region_Map and the Group_Carousel as controls, so that each hover, select, and carousel rotation step runs within the Micro_Interaction budget using only `transform` and `opacity`, with the Region_Map hover shadow shown by fading the `opacity` of a pre-drawn shadow layer.
10. WHILE Reduced_Motion is active, THE Webapp SHALL replace every Part 8 animation, including Micro_Interactions, the Border_Trace, the Hover_Breath, the Completion_Fireworks, the Completion_Story, the Results_Reveal, Animated_Number rolls, and Group_Visual hover, select, and rotate motion, with either an instant state change or an opacity fade of 150 ms or less and no `transform` movement.
11. WHILE Reduced_Motion is active, THE Job_Button SHALL show the Running_State as a static style, as defined in the design document, with no looping motion and no `transform` or `opacity` change over time.
12. WHILE the pointer is over a Job_Button that is not running, THE Webapp SHALL loop the Hover_Breath (soft glow plus a scale of at most 1.02 of a glow layer behind the label, about 1.6 s per breath), and WHEN the pointer leaves, THE Webapp SHALL ease the glow back to rest from its current phase with no stop mid-pulse. This approved Motion_Exception is off under Reduced_Motion.
13. THE Webapp SHALL use constant-speed (linear) timing for the Job_Button running ring loop only, animated through `stroke-dashoffset` and `stroke-dasharray` on the ring SVG, as an approved Motion_Exception.
14. WHEN a Job finishes successfully, THE Webapp SHALL play the Completion_Fireworks once: 8 to 12 short streaks or dots that burst from the Job_Button border within 500 to 700 ms, animated only with `transform` and `opacity`, coloured with the brand reds and accent from Design_Tokens_Block tokens, with no confetti and no screen-wide effect. This approved Motion_Exception is replaced under Reduced_Motion as Requirement 7 describes.

### Requirement 5: One-Shot Entry Animations

**User Story:** As a campaign planner, I want completion animations to play once and stay put, so that clicking around the page does not replay them.

#### Acceptance Criteria

1. WHEN a Job finishes successfully, THE Webapp SHALL set a One_Shot_Flag for that Job only: for the analysis Job the One_Shot_Flag covers the Completion_Toast, and for the persona Job the One_Shot_Flag covers the Completion_Toast and the Results_Reveal.
2. WHEN the Webapp renders with a One_Shot_Flag set, THE Webapp SHALL play the entry animations covered by that One_Shot_Flag exactly once and clear that One_Shot_Flag in the same render, so that the One_Shot_Flag is unset at the start of the next rerun.
3. WHEN an Unrelated_Rerun occurs that leaves the Selected_Group unchanged, THE Webapp SHALL render the persona cards and Group_Visual in their final static state (full opacity, no transform offset, Completion_Story on its final frame) with zero entry animations played.
4. WHEN the user clicks a carousel arrow, clicks a Map_Area, selects a Toggle_Card option, or changes the Group_Dropdown so that the Selected_Group changes, THE Webapp SHALL replay none of the persona card entry animation, the Results_Reveal, the Start_Toast, and the Completion_Toast, and SHALL play only the Group_Change_Crossfade (Requirement 22). WHEN the user moves the What-If slider or switches tabs, THE Webapp SHALL replay none of those animations.
5. THE Webapp SHALL show each Start_Toast and each Completion_Toast at most once per Job, where each activation of a Job_Button that starts a computation counts as one new Job with its own Start_Toast and Completion_Toast.
6. IF a Job ends with an error, THEN THE Webapp SHALL set no One_Shot_Flag, SHALL show no Completion_Toast and no Results_Reveal for that Job, and SHALL leave any One_Shot_Flag from an earlier Job unchanged.
7. IF an Unrelated_Rerun occurs after a Toast has been dismissed, THEN THE Webapp SHALL not show that Toast again, and IF an Unrelated_Rerun occurs while a Toast is still within its display time, THEN THE Webapp SHALL keep that Toast in its final static position with no second slide-up or fade-in.
8. WHILE Reduced_Motion is active, THE Webapp SHALL set and clear the One_Shot_Flag under the same rules as criteria 1 and 2, and SHALL replace the covered entry animations with the Reduced_Motion behaviour from Requirement 4.

### Requirement 6: Remove Redundant Header Lines

**User Story:** As a campaign planner, I want the top of the page to start with the hero, so that I do not read the app name twice.

#### Acceptance Criteria

1. WHEN the Webapp renders, THE Webapp SHALL render no element containing the text "You are in Campaign Analytics", on any tab and in light and dark mode.
2. WHEN the Webapp renders, THE Webapp SHALL render no brand line reading "Promo Audience Navigator" above the Current Run context banner, so that the text "Promo Audience Navigator" appears exactly once in the page body, as the large hero title.
3. WHEN the Webapp renders, THE Webapp SHALL show the Current Run context banner as the first visible page element, followed by the large hero title "Promo Audience Navigator", the hero subtitle with its current text, and the hero KPI panel ("Expected Joiners"), each with the same content as before Part 8.
4. WHEN the Webapp renders, THE Webapp SHALL leave no empty placeholder band where the two removed lines were, so that no blank block taller than the existing spacing token above the context banner remains.
5. THE Webapp SHALL keep the browser tab title "Promo Audience Navigator" unchanged.
6. THE `app/theme.py` module SHALL keep `APP_TITLE` equal to "Promo Audience Navigator" and SHALL keep `nav_bar()` and `header()` callable with their current signatures and output, so that `tests/test_part5_theme.py` passes with no change to its expectations.
7. IF a test expectation changes because of the header removal, THEN THE Change_Report SHALL list that expectation with its test file, the old and new expected value, and the reason for the change.
8. THE Change_Report SHALL confirm that neither "You are in Campaign Analytics" nor a top brand line "Promo Audience Navigator" appears on screen, and that the hero title is the only on-screen "Promo Audience Navigator".
9. THE `app/theme.py` module SHALL keep `header()` and `nav_bar()` unchanged.

### Requirement 7: Job Button Running State

**User Story:** As a campaign planner, I want the button I pressed to show that work is happening, so that I know the app heard me and I do not press it twice.

#### Acceptance Criteria

1. WHEN the user activates a Job_Button, THE Webapp SHALL render the Running_State on that Job_Button only, visible in the browser before the Job's computation starts and kept for the whole time the computation blocks the Webapp, while the other Job_Button stays in its rest style.
2. WHILE the pointer is over a Job_Button that is not running, THE Job_Button SHALL play the Hover_Breath (Requirement 4.12), and WHEN the pointer leaves, THE Job_Button SHALL ease the glow back to rest from its current phase.
3. WHEN the user presses a Job_Button, THE Job_Button SHALL scale to about 0.97 and release within 120 to 180 ms, and THE Hover_Breath SHALL hand off to the press with no visible jump.
4. WHILE a Job runs, starting straight after the press, THE Job_Button SHALL show the Border_Trace: a red line that travels around the button border at constant speed, seamlessly and infinitely, with no visible start or end point and no hitch at the loop point, until the Job ends.
5. WHILE a Job runs, THE Border_Trace SHALL survive reruns during the Job with no restart and no flicker, SHALL stay visible above the loader overlay, and SHALL be drawn only on a pseudo-element or overlay, so that the button label never blurs, scales, or shifts.
6. WHILE a Job runs, THE Job_Button SHALL be styled with the disabled tokens and SHALL ignore the pointer, with no hover or press feedback.
7. WHEN a Job ends successfully, THE Job_Button SHALL play this sequence once: the Border_Trace line extends from its current position until it fills the whole border within 250 to 350 ms, the full border glows briefly, then the Completion_Fireworks burst outward and fade, with the glow and sparks lasting 500 to 700 ms in total; THE Job_Button SHALL then settle to its rest style, and THE Completion_Toast (Requirement 8) SHALL arrive as the sparks fade.
8. WHEN the completion render draws the finish, THE Webapp SHALL start the fill from the Border_Trace's computed current position (a server-timed phase), so that the handoff from the running render to the completion render looks continuous.
9. IF a Job ends with an error, THEN THE Job_Button SHALL show no fill and no Completion_Fireworks, SHALL fade the Border_Trace out from its current position, SHALL return to its rest style and accept a new activation on the next render, THE Webapp SHALL show the existing error message with its current text, and THE Webapp SHALL show no Completion_Toast for that Job.
10. WHILE Reduced_Motion is active, THE Job_Button SHALL show no Hover_Breath and no press scale, SHALL show a static red ring while the Job runs, and SHALL show a brief border highlight with an opacity fade of 150 ms or less on completion in place of the fill and the Completion_Fireworks.
11. IF the user activates a Job_Button again with the pointer while its Job runs, THEN THE Webapp SHALL start no second Job, and the results, flash messages, Start_Toast, and Completion_Toast SHALL each appear once, as for a single activation.
12. IF a second activation of the same Job (Enter or Space, or a queued click) arrives within 1.5 s after a Job with the same inputs finished, ignoring the auto-generated Promo ID, THEN THE Webapp SHALL start no second Job and SHALL show no second Start_Toast and no second Completion_Toast. (Streamlit queues the second click and reruns after the first Job; CSS cannot block keyboard activation.)
13. THE Running_State SHALL apply to "Run Analysis" and "Build Personas" only, and SHALL keep each button's label, key, type, and form membership ("Run Analysis" inside `new_promo_form`) unchanged.

### Requirement 8: Toasts

**User Story:** As a campaign planner, I want short notifications in the corner that tell me a job started and finished, so that I can keep my place on the page.

#### Acceptance Criteria

1. THE Webapp SHALL render Toasts in a Toast_Stack fixed to the bottom-right of the browser viewport. The Toast_Stack SHALL stay in that position while the page scrolls, and it SHALL be inset from the bottom and right viewport edges by a spacing token from the Design_Tokens_Block. Each Toast SHALL have a corner radius of 12 to 14 px and a shadow, and both values SHALL come from Design_Tokens_Block tokens.
2. WHEN a Toast enters, THE Webapp SHALL move the Toast upward from below its resting position to its resting position while fading it from opacity 0 to 1. The animation SHALL last 120 to 250 ms with an ease-out curve and SHALL animate only `transform` and `opacity`.
3. WHEN more than one Toast is visible, THE Toast_Stack SHALL show the Toasts stacked with the most recently shown Toast at the front (bottom-most and fully visible) and older Toasts offset behind it, with at most 3 Toasts visible at once.
4. WHEN a 4th Toast is shown while 3 Toasts are visible, THE Toast_Stack SHALL remove the oldest visible Toast with the fade-out transition from criterion 5.
5. WHEN 4 s (±0.25 s) of unpaused display time have passed since a Toast appeared, THE Webapp SHALL dismiss that Toast by fading it from opacity 1 to 0 over 120 to 250 ms with an ease-out curve, and SHALL then remove it from the Toast_Stack.
6. WHILE the pointer hovers over the Toast_Stack, THE Webapp SHALL pause the auto-dismiss timer of every visible Toast. WHEN the pointer leaves the Toast_Stack, each Toast's timer SHALL resume from its remaining time and SHALL NOT restart at 4 s.
7. THE Toast SHALL carry `role="status"` and `aria-live="polite"`, so that screen readers announce its text without moving keyboard focus.
8. WHEN the user starts a Job, THE Webapp SHALL show one Start_Toast. For Run Analysis it SHALL read "Running analysis for <Promo ID>...", where "<Promo ID>" is the value shown in the "Promo ID (Auto-Generated)" field. For Build Personas with one or more selected split columns it SHALL read "Building personas by <split>...", where "<split>" is the existing attribute display label of each selected split column, joined in selection order, and with no split column selected it SHALL read "Building personas for all leads...". The Start_Toast SHALL NOT show raw column names such as `age_band` or `owns_Loan`.
9. WHEN a Job finishes successfully, THE Webapp SHALL show one Completion_Toast for that Job, reading "Analysis complete" for Run Analysis or "Personas ready" for Build Personas. THE Webapp SHALL show no Completion_Toast when the analysis ends with the empty-audience warning or with a missing-model error.
10. IF a Job ends with an error, THEN THE Webapp SHALL show no Completion_Toast for that Job, SHALL let any visible Start_Toast for that Job dismiss on its normal timer, and SHALL show the existing error message unchanged.
11. THE Webapp SHALL keep the existing `st.success` and `st.warning` flash messages, with their current text and their current trigger conditions, so that the existing AppTest assertions (including "Built 2 personas") pass unchanged.
12. THE design document SHALL compare two approaches against each other: a CSS and HTML recreation injected with `st.markdown(unsafe_allow_html=True)`, and Sonner in a custom component mounted to the parent document. The comparison SHALL cover how each approach meets criteria 1 to 7, whether it needs an iframe, whether it needs a Vendored_Asset, and how it behaves across `st.rerun()`. The design document SHALL recommend one approach.
13. WHERE the CSS and HTML recreation is chosen, THE Webapp SHALL inject the Toast_Stack with `st.markdown(unsafe_allow_html=True)` using `position: fixed`, with no iframe.
14. THE Webapp SHALL style the success and warning flash messages quietly, with compact padding, a subtle tinted background and text from Design_Tokens_Block status tokens, and no large icon, so that the flash messages read below the Completion_Toast in visual weight, while keeping their text, a text contrast ratio of at least 4.5:1, and their alert role unchanged.

### Requirement 9: Completion Stories

**User Story:** As a campaign planner, I want the finish to feel like the loader I just watched coming to rest, so that the result clearly comes from the work I started.

#### Acceptance Criteria

1. WHEN the analysis Job finishes successfully, THE Completion_Toast SHALL play the magnifier story in this order: the existing magnifier loader motif zooms on one document, the magnified area resolves into the text "Analysis complete", and a check mark draws on, with the whole sequence finishing within 1.6 s of the Completion_Toast entering.
2. WHEN the persona Job finishes successfully, THE Completion_Toast SHALL play the squares story in this order: the existing red and gold squares do one last shuffle, slide together, merge with the Gooey_Merge into exactly two rounded groups, and end on the text "Personas ready", with the whole sequence finishing within 1.6 s of the Completion_Toast entering.
3. WHEN a Completion_Story finishes, THE Completion_Toast SHALL hold the final frame (the "Analysis complete" text with the drawn check mark, or the two rounded groups with the "Personas ready" text) with no further motion until the Toast starts its dismiss fade.
4. THE Completion_Story SHALL play at most once per successful Job, gated by that Job's One_Shot_Flag, and on any Unrelated_Rerun while the Completion_Toast is still visible THE Completion_Toast SHALL show the final frame with no replay.
5. THE Completion_Story SHALL take every colour from the existing loader tokens in the Design_Tokens_Block, with zero hex colour literals, so that light mode uses the light values and dark mode uses the dark values of the same tokens.
6. WHILE Reduced_Motion is active, THE Completion_Toast SHALL skip the zoom, shuffle, slide, merge, and check-mark draw, and SHALL show only the final frame with an opacity fade of 150 ms or less.
7. THE Completion_Toast SHALL include the text "Analysis complete" or "Personas ready" as real text in the Toast's live region from the moment the Toast enters, so that screen readers announce it once regardless of animation progress or Reduced_Motion.
8. IF a Job ends with an error, the empty-audience warning, or a missing-model error, THEN THE Webapp SHALL show no Completion_Toast and play no Completion_Story for that Job.
9. WHERE the user rejects the Completion_Story or the Gooey_Merge in the design phase, THE Completion_Toast SHALL show the approved fallback recorded in the design document, which stays within the Micro_Interaction budget and still ends on the same text.
10. WHEN a Job finishes successfully, THE Webapp SHALL hand off from the loader overlay to the Completion_Story through the finishing overlay of Requirement 22.16.

### Requirement 10: Text Input Styling

**User Story:** As a campaign planner, I want text fields to look like soft pills that fit what I type, so that the form looks calm and clearly clickable.

#### Acceptance Criteria

1. THE Webapp SHALL render every Text_Entry_Widget with no low-saturation bottom underline and no low-saturation end (right-hand) line, and SHALL draw a thin outline of about 1 px, taken from a Design_Tokens_Block token, around the Input_Pill, with a contrast ratio of at least 3:1 against the adjacent page background in light and dark mode (WCAG 1.4.11), kept subtle, in the rest, hover, focus, and disabled states.
2. THE Webapp SHALL draw an Input_Pill behind the typed text of every Text_Entry_Widget, with a fully rounded radius and a background colour from the Design_Tokens_Block that differs from the surrounding page background in light and dark mode.
3. WHILE a Text_Entry_Widget is empty, THE Input_Pill SHALL keep a minimum width of at least 120 px, set by a Design_Tokens_Block token, and SHALL show any existing placeholder text in full inside the pill.
4. WHEN the text in an `st.text_input` changes, THE Input_Pill SHALL set its width to fit the typed text plus the pill's horizontal padding, bounded below by the minimum width and above by 100% of the widget's container width.
5. WHEN the text in an `st.text_area` changes, THE Input_Pill SHALL wrap the text within 100% of the widget's container width and SHALL grow in height to show every typed line.
6. WHEN the text in a Text_Entry_Widget changes, THE Input_Pill SHALL apply the new width or height in the same frame with no width or height animation, so that Part 8 motion stays limited to `transform` and `opacity`.
7. IF the typed text in an `st.text_input` is wider than 100% of the widget's container width, THEN THE Input_Pill SHALL stay at 100% of the container width and SHALL scroll the text horizontally so that the caret stays visible, with no typed character lost.
8. THE design document SHALL record an inspection of Streamlit's BaseWeb input DOM before choosing selectors, and SHALL evaluate CSS `field-sizing: content` first, with a fallback for browsers without it.
9. IF the browser lacks support for `field-sizing: content`, THEN THE Input_Pill SHALL fall back to a pill fixed at 100% of the widget's container width, with the same radius, background, padding, and text size as the fitted pill, and with the whole pill area accepting clicks.
10. WHEN a Text_Entry_Widget receives keyboard focus, THE Webapp SHALL show a focus ring drawn from the `--pan-focus` token around the Input_Pill, with at least 3:1 contrast against the adjacent page background (WCAG AA non-text contrast) in light and dark mode.
11. WHEN a Text_Entry_Widget loses focus, THE Webapp SHALL remove the focus ring.
12. THE Webapp SHALL render every `st.number_input` at a fixed width with the same fill and the same thin outline as the Input_Pill, and with no width fitting.
13. WHILE a Text_Entry_Widget is disabled (for example "Promo ID (Auto-Generated)"), THE Input_Pill SHALL take its background and text colours from the disabled tokens in the Design_Tokens_Block, SHALL keep its current value readable, and SHALL accept no typed input.
14. WHEN the text in an `st.text_input` changes, THE Input_Pill SHALL change its width instantly, with no width transition. Note: with `field-sizing: content` the used width changes while the computed value stays `auto`, so no CSS transition fires, and `interpolate-size: allow-keywords` only interpolates when the specified value changes; a smooth width would need JavaScript writing pixel widths into the page, which is out of scope unless approved later.

### Requirement 11: Animated Headline Numbers

**User Story:** As a campaign planner, I want the key numbers to roll from their old value to their new one, so that I see what changed after a new run or a slider move.

#### Acceptance Criteria

1. THE Animated_Number_List SHALL contain exactly two numbers: the hero Expected Joiners figure on New Promo and the headline figure that changes with the What-If slider. No number inside `st.dataframe`, the Past Promos rate tables, or the Expected Joiners By Persona tables SHALL be on the list.
2. WHEN a value in the Animated_Number_List changes because a Job finishes or the What-If slider moves, THE Animated_Number SHALL animate from the previous value stored in session state to the new value in one animation of about 600 ms (within 400 to 900 ms) with an ease-out curve and no linear timing function, and SHALL then store the new value in session state as the previous value.
3. WHEN an Animated_Number renders with no previous value in session state, THE Webapp SHALL show the final value with no roll animation, unless the design document records that the one-time first-view animation is adopted, in which case criterion 4 applies.
4. WHERE the design document records that the one-time first-view animation is adopted, THE Animated_Number SHALL animate only the first time it enters the viewport, at most once per distinct value, and SHALL show the final value with no animation on every later scroll into view.
5. WHEN an Unrelated_Rerun occurs and a value's formatted text is identical to its previous formatted text in session state, THE Animated_Number SHALL show the value with no animation.
6. THE Webapp SHALL render each Animated_Number's plain formatted value as text in Streamlit-native markup outside any iframe, so that a screen reader reads it and an AppTest test finds the same text as the static value.
7. THE Webapp SHALL render each Animated_Number with plain CSS and Streamlit-native markup, with no iframe and no JavaScript library.
8. THE Animated_Number SHALL show the same text as the current static value at every final frame, including thousands separators, the peso sign, the percent sign, and the number of decimal places.
9. THE Webapp SHALL render every number outside the Animated_Number_List as static text with no animation.
10. WHEN a value in the Animated_Number_List changes again before its running animation ends, THE Animated_Number SHALL start a new animation from the value currently shown to the latest value, and SHALL end showing the latest value only.
11. WHILE Reduced_Motion is active, THE Animated_Number SHALL change to the new value instantly or with an opacity fade of 150 ms or less, with no rolling digits.
12. IF the CSS roll cannot run, THEN THE Webapp SHALL show each number in the Animated_Number_List as its static formatted value with no animation, show no error to the user, and leave the session-state previous values unchanged.

### Requirement 12: Group Component And Dropdown Fallback

**User Story:** As a campaign planner, I want to pick a persona group from a map or carousel and still have the dropdown work, so that the page works with or without the visual.

#### Acceptance Criteria

1. THE Webapp SHALL render the Region_Map, the Group_Carousel, and the Toggle_Card through one Group_Component.
2. THE Group_Component SHALL load only files under `app/static/` and SHALL make no network request to any host other than the Webapp's own server.
3. THE Webapp SHALL keep the Group_Dropdown with its key `persona_group_select`, its label "Show group", and its options: the persona set group keys in run order followed by "All groups".
4. WHEN the user selects a group in the Group_Visual, THE Webapp SHALL set the Selected_Group to the Group_Dropdown option equal to that group key, and THE Group_Dropdown SHALL show that option on the next render.
5. WHEN the user changes the Group_Dropdown, THE Group_Visual SHALL show the group equal to the new Selected_Group as the only selected group on the next render.
6. WHEN the Selected_Group changes from either control, THE Personas_Tab SHALL render the same persona cards, comparison table, Expected Joiners By Persona section, and downloads that setting the Group_Dropdown alone to that group renders.
7. WHILE the Selected_Group is "All groups", THE Group_Visual SHALL show zero groups in the selected state.
8. IF the persona run yields more than one group, THEN THE Webapp SHALL render the Group_Visual, and IF the persona run yields zero or one group, THEN THE Webapp SHALL render neither the Group_Visual nor the Group_Dropdown.
9. WHILE the "Demo Mode" notice is shown, THE Webapp SHALL place the Group_Visual after the "Demo Mode" notice and before the persona cards and group sections, and WHILE the "Demo Mode" notice is not shown, THE Webapp SHALL place the Group_Visual before the persona cards and group sections.
10. IF the Group_Component fails to load or returns no value, as in AppTest where component JS does not run, THEN THE Personas_Tab SHALL keep the Selected_Group unchanged, SHALL show no error or exception for the Group_Component, and SHALL update the persona cards, comparison table, Expected Joiners By Persona section, and downloads when the Group_Dropdown changes.
11. WHILE the Group_Visual is rendered, THE Webapp SHALL render exactly one iframe for the Group_Visual per Personas_Tab render, and WHILE the Group_Visual is not rendered, THE Webapp SHALL render zero iframes for it.
12. IF the Group_Component returns a value that is not one of the current Group_Dropdown options, THEN THE Webapp SHALL leave the Selected_Group unchanged and SHALL leave the Group_Dropdown showing its current option.
13. WHEN the user changes the Group_Dropdown after an earlier Group_Visual selection, THE Webapp SHALL keep the Group_Dropdown's new value as the Selected_Group on that render and on later Unrelated_Reruns, and SHALL not revert it to the Group_Component's earlier value.
14. THE Webapp SHALL read the Group_Component value before the Group_Dropdown is created in the same render, so that a Group_Visual selection updates the Selected_Group with no extra rerun.
15. WHEN the user changes the Group_Dropdown, THE Group_Visual SHALL move smoothly to match on the next render, so that the Group_Visual and the Group_Dropdown never show different groups: the Group_Carousel SHALL rotate the newly selected item to the front by the shortest direction around the ring, using the ring rotation timing (about 250 ms, shared ease-out token) and the Glass_Layer opacity crossfade; the Region_Map SHALL move the selected state to the matching Map_Area within the Micro_Interaction budget; and the Toggle_Card SHALL move its selected state within the Micro_Interaction budget.
16. WHILE Reduced_Motion is active, THE Group_Visual SHALL apply the change in criterion 15 instantly.
17. WHILE the Selected_Group is "All groups", THE Group_Visual SHALL apply the existing "no item selected" rules of Requirements 13.12, 15.9, and 15.19 and SHALL not move any selected state.

### Requirement 13: Philippine Region Map

**User Story:** As a campaign planner, I want to click a part of the Philippines to see that area's personas, so that I can explore regional groups the way I picture them.

#### Acceptance Criteria

1. WHILE the split is `region` alone and the persona run yields more than one group, THE Group_Visual SHALL be the Region_Map, with one Map_Area for each `region` value the approved Region_Mapping matches (NCR, Luzon, Visayas, Mindanao in the current data).
2. THE Region_Map SHALL build its four Map_Area outlines from the faeldon/philippines-json-maps v1.1.1 geometry listed in the Asset_Register, and SHALL show the credit "NAMRIA, PSA via OCHA" as visible text inside the Group_Component frame, directly below the map, with no scrolling or interaction needed to read it.
3. THE Region_Map SHALL fill every Map_Area with one shared Diamond_Lattice pattern in map coordinates, so that the lattice runs continuously across each whole Map_Area with no break or restart inside it, and also lines up across the borders between Map_Areas with no offset.
4. WHEN the pointer enters a selectable Map_Area, THE Region_Map SHALL move that Map_Area's dissolved outline upward by 3 px (within 2 to 4 px) and add a drop shadow from a Design_Tokens_Block shadow token, within the Micro_Interaction budget (120 to 250 ms, ease-out, `transform` and `opacity` only), and WHEN the pointer leaves that Map_Area while it is not selected, THE Region_Map SHALL return it to its resting position within the same budget.
5. WHEN the user clicks a selectable Map_Area, THE Region_Map SHALL fill that Map_Area's dissolved outline with the selected-state colour token, keep that Map_Area raised by the same 3 px (within 2 to 4 px), set every other selectable Map_Area to an opacity of 0.6 (within 0.5 to 0.7), and set the Selected_Group to the group whose `region` value matches that Map_Area.
6. THE Region_Map SHALL make each selectable Map_Area a single keyboard tab stop in a fixed order (NCR, Luzon, Visayas, Mindanao, then any further matched values in run order), with an `aria-label` that names the `region` value and the lead count that the Region_Mapping returns for that Map_Area.
7. WHEN a selectable Map_Area has keyboard focus and the user presses Enter or Space, THE Region_Map SHALL apply the same selected state and Selected_Group change as a click on that Map_Area, and SHALL show a focus ring from the `--pan-focus` token on that Map_Area while it has focus.
8. IF a Map_Area has a lead count of 0 in the current run, THEN THE Region_Map SHALL fill that Map_Area with the muted token, SHALL apply no hover raise to it, SHALL leave it out of the keyboard tab order, and SHALL leave the Selected_Group unchanged when the user clicks it.
9. WHILE dark mode is active, THE Region_Map SHALL draw the Diamond_Lattice, the selected state, the dimmed state, the muted state, and the attribution text from dark-mode tokens in the Design_Tokens_Block.
10. THE Diamond_Lattice SHALL be an original, generic geometric pattern, not traced from any BPI asset and not derived from any logo.
11. THE Region_Map geometry SHALL come from the approved source and not from any user-attached reference image.
12. IF the Selected_Group is "All groups" or a group whose `region` value has no Map_Area, THEN THE Region_Map SHALL show no Map_Area in the selected state and SHALL show every selectable Map_Area at full opacity with no dimming.
13. WHEN the user clicks or presses Enter or Space on the Map_Area that is already selected, THE Region_Map SHALL keep that Map_Area selected and SHALL leave the Selected_Group unchanged.
14. THE Region_Map SHALL provide exactly four clickable Map_Areas (NCR, Luzon, Visayas, Mindanao), each drawn as one solid dissolved outline, and SHALL draw no border between the administrative-region shapes inside a Map_Area. THE Region_Mapping of administrative-region shapes to Map_Areas SHALL be used only to build these outlines.
15. THE Region_Map SHALL show NCR as an enlarged inset or callout bubble, linked to NCR's true location by a leader line or marker, sized to at least 44 by 44 CSS px, that is clickable, keyboard-focusable, carries the same `aria-label` as criterion 6, shows the same hover, selected, dimmed, and muted behaviour as the other Map_Areas, and counts as the NCR Map_Area for selection.

### Requirement 14: Region Mapping Logic

**User Story:** As a developer, I want the link between data values and map shapes in one tested function, so that a renamed or new region is caught instead of silently missing.

#### Acceptance Criteria

1. THE Region_Mapping SHALL live in `src/webapp_core/` as pure functions that import no Streamlit module, read no file or session state, and leave their input arguments unmodified.
2. THE Region_Mapping SHALL map each of the current `region` data values (NCR, Luzon, Visayas, Mindanao) to exactly one Map_Area, matching on the exact, case-sensitive data value, so that a renamed value such as "Metro Manila" or "ncr" is not matched.
3. THE Region_Mapping SHALL assign each administrative-region shape to at most one Map_Area, so that no shape is shared between two Map_Areas.
4. WHEN given group lead counts as pairs of `region` value and non-negative integer lead count, THE Region_Mapping SHALL return exactly one entry per Map_Area, in the same order on every call with the same input, and each entry SHALL hold the Map_Area's region value, its lead count, and a selectable flag that is true only when the lead count is greater than 0.
5. IF a Map_Area's region value is absent from the given group lead counts, THEN THE Region_Mapping SHALL return that Map_Area with a lead count of 0 and a selectable flag of false.
6. IF a `region` data value in the given group lead counts has no Map_Area, THEN THE Region_Mapping SHALL report that value in a list of unmatched values, SHALL exclude it from the Map_Area entries, and THE Personas_Tab SHALL keep that group selectable through the Group_Dropdown.
7. IF a given lead count is negative or not an integer, THEN THE Region_Mapping SHALL raise an error naming the offending `region` value and SHALL return no partial result.
8. THE Region_Mapping SHALL have unit tests in `tests/test_part8_<area>_unit.py` that cover each current value (NCR, Luzon, Visayas, Mindanao) mapping to exactly one Map_Area, at least one unmatched value appearing in the unmatched list, a zero-lead value returning a selectable flag of false, a Map_Area absent from the input returning a lead count of 0, a check that no administrative-region shape belongs to two Map_Areas, and a negative lead count raising an error.

### Requirement 15: 3D Category Carousel

**User Story:** As a campaign planner, I want to turn a ring of simple pictures to pick a group, so that categories like age band feel concrete.

#### Acceptance Criteria

1. WHILE the split is a single non-region column with 3 or more values in the current persona run and is not a Multi_Split, THE Group_Visual SHALL be the Group_Carousel.
2. THE Group_Carousel SHALL place exactly one Group_Illustration per category value of the current persona run on a ring using CSS 3D transforms, with the active item front and centre at full scale and full opacity, and every other item at a smaller scale than the active item and behind a Glass_Layer.
3. WHEN the user activates the left or right button, or presses the Left or Right arrow key while the Group_Carousel has keyboard focus, THE Group_Carousel SHALL rotate exactly one step in the direction of the button or key pressed over 120 to 250 ms with an ease-out curve, animating only `transform` and `opacity`, and SHALL set the Selected_Group to the new active value.
4. THE Group_Carousel SHALL give the left and right buttons accessible names that state the direction of rotation, and WHEN the active value changes, THE Group_Carousel SHALL announce the new active value and its lead count through a screen-reader live region.
5. IF the persona run yields zero or one group, whatever the column, THEN THE Webapp SHALL render neither the Group_Visual nor the Group_Dropdown, as Requirement 12.8 states.
6. THE Group_Carousel SHALL contain no administrative-region shapes, no Map_Area, and no Diamond_Lattice fill.
7. THE Group_Carousel SHALL show each item's category value as a visible plain-language text label next to that item's Group_Illustration.
8. WHEN the user rotates past the last category value in either direction, THE Group_Carousel SHALL wrap to the first value on the opposite end of the ring, so that every value is reachable from every other value by repeated presses of either button.
9. WHEN the Group_Carousel renders, THE Group_Carousel SHALL make the Selected_Group the active item, and WHILE the Selected_Group is "All groups", THE Group_Carousel SHALL show the first category value in Group_Dropdown order at the front with no item marked as selected, as defined in the design.
10. IF the user activates a button or arrow key while a rotation is still in progress, THEN THE Group_Carousel SHALL finish at most one further step per activation and SHALL end with the Selected_Group equal to the item shown at the front.
11. THE Webapp SHALL NOT use the Group_Carousel for a column with two values, and SHALL NOT fall back to the Group_Dropdown alone for a two-value column.
12. WHILE the split is a single non-region column with exactly two values in the current persona run and is not a Multi_Split, THE Group_Visual SHALL be the Toggle_Card. A `region` split with two groups SHALL show the Region_Map (Requirement 13.1), not a Toggle_Card.
13. WHERE the two-value column is a yes/no column (values 0 and 1), THE Toggle_Card SHALL show the column's own icon with a check option for 1 and a cross option for 0.
14. WHERE the two-value column is not a yes/no column, THE Toggle_Card SHALL show the two values side by side, each with its value Group_Illustration and its plain-words label.
15. THE Toggle_Card SHALL make each option keyboard focusable, activatable with Enter or Space, and reachable from the other option with the arrow keys.
16. THE Toggle_Card SHALL give each option an `aria-label` that names the column's plain-language label, the option's value, and the lead count for that value.
17. WHEN the user selects a Toggle_Card option, THE Toggle_Card SHALL show that option with the selected-state token, keep the other option fully readable, and set the Selected_Group to the group key for that value.
18. THE Toggle_Card SHALL switch between options with a Micro_Interaction that animates only `opacity` and `transform`.
19. WHILE the Selected_Group is "All groups", THE Toggle_Card SHALL show neither option as selected.
20. THE Group_Carousel SHALL show the front (selected) item clear and sharp, at full opacity and full scale, with no Glass_Layer.
21. THE Group_Carousel SHALL place every item other than the front item behind a Glass_Layer made of `backdrop-filter: blur() saturate()` with the `-webkit-` prefix, a light translucent tint, a thin bright inner edge highlight (a light catch at the top-left), and a soft shadow.
22. THE Group_Carousel SHALL take every colour, blur value, saturation value, and shadow of the Glass_Layer from Design_Tokens_Block tokens defined for light and dark.
23. THE Group_Carousel SHALL apply the Glass_Layer in stepped fixed levels, with at least two levels (near and far), so that the further an item is from the front, the more frosted and tinted its Glass_Layer is and the slightly lower its scale is, with the blur value fixed per level.
24. WHEN an item moves between levels during a rotation, THE Group_Carousel SHALL animate only that item's `transform` and its Glass_Layer `opacity`, so that an item reaching the front defrosts and an item leaving the front frosts over, with the same duration (about 250 ms) and the same shared ease-out token as the rotation, and SHALL use no refraction and no SVG displacement.
25. THE Group_Carousel SHALL keep the label of the front item sharp, and SHALL give all Group_Carousel text a contrast ratio of at least 4.5:1 (WCAG AA) in light mode and in dark mode.
26. IF the browser does not support `backdrop-filter` (tested with `@supports`), THEN THE Group_Carousel SHALL draw each Glass_Layer as a solid translucent tint with the same edge highlight.
27. WHEN the user clicks an item that sits behind a Glass_Layer, THE Group_Carousel SHALL rotate that item to the front and SHALL set the Selected_Group to its value.
28. WHILE Reduced_Motion is active, THE Group_Carousel SHALL keep the static Glass_Layer levels and SHALL switch the active item instantly with no rotation.
29. THE Toggle_Card SHALL have no Glass_Layer and no `backdrop-filter`.

### Requirement 16: Group Illustrations

**User Story:** As the product owner, I want the carousel pictures to be simple, original, and respectful, so that they help recognition without stereotyping anyone.

#### Acceptance Criteria

1. THE Group_Illustration SHALL be an original, flat SVG drawn for this project, with no stock image, no photograph, no embedded raster image, and no artwork copied or traced from another source.
2. THE Group_Illustration SHALL use exactly one accent colour token from the Design_Tokens_Block plus neutral tokens from the Design_Tokens_Block, with no gradients, no drop shadows, and zero hex colour literals.
3. THE Illustration_List SHALL cover all 13 non-region split columns by name: exactly one Group_Illustration for every value of each column with 3 or more values (`segment` 4 values, `age_band` 5, `sec_class` 6, `inflow_type` 4, `online_shopper` 5, shown on the ring), and exactly one icon for each yes/no column (`digital_app_user`, `frugal_flag`, `email_valid`, `mobile_valid`, `owns_Credit Card`, `owns_Insurance`, `owns_Investment`, `owns_Loan`, shown on the Toggle_Card), with no separate illustration for the 0 and 1 values.
4. IF the Group_Carousel or the Toggle_Card is asked to show a category value that has no Group_Illustration in the Illustration_List, THEN THE Webapp SHALL show a neutral placeholder Group_Illustration labelled with the category value, and SHALL keep showing every other Group_Illustration.
5. THE Group_Illustration SHALL contain at most one prop per figure, where a prop is any held, worn, or adjacent object other than the figure's body, hair, and plain clothing.
6. THE `age_band` Group_Illustrations SHALL show light life-stage cues, with each of the 5 bands visibly different from the other 4: a graduation cap for 18-24; a laptop or phone for 25-34; a young child or family for 35-44; house keys or a home (an established household) for 45-54; and grey hair or glasses, with a newspaper, a garden, or a grandchild, for 55+. Grey hair and glasses count as the figure's hair or plain appearance, not as a prop, and the one activity is the figure's one prop.
7. THE Group_Illustration SHALL show no cane, no walker, no wheelchair, no stooped posture, and no other frailty cue, and SHALL show no stereotyped depiction in any category.
8. WHERE a Group_Illustration shows money, THE Group_Illustration SHALL use the peso sign (₱) and SHALL contain no dollar sign ($).
9. THE Group_Illustrations for `segment`, `sec_class`, `online_shopper`, and `inflow_type` SHALL tell values apart using objects or symbols (for example, the count of coins or the type of icon) and SHALL NOT tell them apart through a figure's clothing quality, skin tone, body shape, or gender.
10. THE Group_Illustration SHALL show no ethnic costume, regional caricature, or gender-coded role (for example, only women with children or only men with laptops) as a way to mark a category value.
11. WHILE dark mode is active, THE Group_Illustration SHALL use the dark values of its Design_Tokens_Block colour tokens and keep a contrast ratio of at least 3:1 between its accent colour and its background.
12. THE Illustration_List SHALL give each of the 8 yes/no columns its own distinct icon, so that 8 different icons exist and none is reused for another column.
13. WHEN a non-yes/no column has exactly two values in a run, THE Webapp SHALL show it on the Toggle_Card using that column's value Group_Illustrations from the Illustration_List.

### Requirement 17: Results Reveal After Build Personas

**User Story:** As a campaign planner, I want the persona results to rise into place in a clear order after a build, so that I see where to look first.

#### Acceptance Criteria

1. WHEN a persona build succeeds, THE Webapp SHALL play this order once: Start_Toast and Running_State during the Job, then the Completion_Toast, then the Group_Visual rising into place, then the persona cards following. Under this order, the Results_Reveal SHALL start no earlier than the start of the Completion_Toast enter transition.
2. THE Results_Reveal SHALL treat the Group_Visual as item 1 when the Group_Visual is rendered, followed by each persona card as one item in on-page order. When the Group_Visual is not rendered, the first persona card SHALL be item 1.
3. WHEN a Results_Reveal item plays, THE Results_Reveal SHALL move the item from a translateY between 12 and 16 px to 0, and from opacity 0 to 1, over 200 to 250 ms with ease-out, ending at translateY 0 and opacity 1.
4. THE Results_Reveal SHALL use one stagger interval between 40 and 60 ms. Item n, for n from 1 to 6, SHALL start (n − 1) × that interval after item 1 starts, and every item after the sixth SHALL start at the same time as the sixth.
5. THE Results_Reveal SHALL play only under the One_Shot_Flag set by that build, and SHALL play at most once per successful persona build.
6. IF a persona build ends with an error, THEN THE Webapp SHALL play no Results_Reveal and SHALL render any persona cards and Group_Visual already on the page in their final static state.
7. WHILE Reduced_Motion is active, THE Results_Reveal SHALL show every item with an opacity fade of 150 ms or less, no translateY movement, and no stagger.
8. THE Results_Reveal SHALL apply no motion to tables, including the persona comparison table and the Expected Joiners By Persona tables. These tables SHALL render in their final state in the same render as item 1 of the reveal.

### Requirement 18: Multi-Category Split

**User Story:** As the product owner, I want to choose how a split on several categories is shown, so that the result is clear before anyone builds it.

#### Acceptance Criteria

1. THE design document SHALL present 2 or 3 Multi_Split_Options. Candidate options include a carousel of combined groups ("NCR · 25-34"), the Region_Map for `region` plus a Group_Carousel for the second category, and a Group_Carousel by the first category with chips for the second.
2. THE design document SHALL describe each Multi_Split_Option by its layout, how the user selects a group, how it shows a split on 3 or more category columns, which motion it uses within the Micro_Interaction budget, and whether it needs any Motion_Exception or new Asset_Register entry.
3. THE design document SHALL mark exactly one Multi_Split_Option as recommended, state at least one reason for the recommendation, and apply the simpler-choice rule of Requirement 1.8.
4. WHILE the split is a Multi_Split and the run yields 3 to 12 combined groups, THE Group_Visual SHALL be one Group_Carousel ring of combined groups, each item labelled with its plain-language values joined by " · " (for example "NCR · 25-34") and showing the Group_Illustration of the first split column's value where one exists and a neutral placeholder Group_Illustration otherwise, and WHILE the run yields exactly 2 combined groups, THE Group_Visual SHALL be a Toggle_Card with the combined-group labels as its option text.
5. IF a Multi_Split run yields more than 12 combined groups, THEN THE Personas_Tab SHALL show only the existing Group_Dropdown, with its key `persona_group_select`, its options, and its "All groups" option unchanged, and SHALL render no Group_Visual and no Group_Component iframe for that split.
6. WHEN the user approves a Multi_Split_Option, THE Webapp SHALL implement only that option, render it through the single Group_Component, and keep the Group_Dropdown and Selected_Group in sync as Requirement 12 criteria 4 to 8 state.
7. IF the approved Multi_Split_Option's Group_Visual fails to load or sends no value, THEN THE Personas_Tab SHALL keep working through the Group_Dropdown alone, as Requirement 12.10 states.

### Requirement 19: Third-Party Assets And Offline Use

**User Story:** As the product owner, I want every outside file listed, licensed, and stored locally, so that the demo runs offline and stays legally clean.

#### Acceptance Criteria

1. THE Webapp SHALL load every Vendored_Asset from a file under `app/static/`, served either through Streamlit static serving (enabled by `enableStaticServing = true` in `.streamlit/config.toml`) or through the Group_Component's declared `path`, and from no other location.
2. WHILE the host machine has no internet connection, THE Webapp SHALL render every Part 8 feature (Toasts, Animated_Numbers, Region_Map, Group_Carousel, Text_Entry_Widget styling) with zero failed requests for scripts, styles, fonts, or geometry, as observed in the browser's network panel.
3. THE Webapp SHALL make zero runtime requests for scripts, styles, fonts, or geometry to any host other than the Webapp's own server, including CDNs, font services, and map tile or geometry services.
4. THE `app/static/` folder SHALL hold, in the same folder as each Vendored_Asset, a licence file or licence notice that names the asset, its version, and its licence, with exactly one licence file or notice per Vendored_Asset.
5. THE Asset_Register SHALL contain exactly one entry, for the faeldon/philippines-json-maps v1.1.1 geometry file (source URL, version, MIT licence for the file, and CC BY-IGO for the underlying boundaries), and SHALL list no other Vendored_Asset, so that NumberFlow and Sonner are not present in `app/static/`.
6. THE Webapp SHALL use each Vendored_Asset as a pre-built file that requires no `pip install`, no npm install, and no build step, and the Part 8 changes SHALL add zero entries to `requirements.txt`.
7. IF the user rejects an Asset_Register entry, THEN THE design document SHALL record an asset-free alternative for that asset, THE implementation SHALL use that alternative, and `app/static/` SHALL contain zero files from the rejected asset.
8. IF a Vendored_Asset file is missing from `app/static/` at runtime, THEN THE Webapp SHALL keep the Group_Dropdown usable and show affected numbers as plain static text, and SHALL make zero attempts to fetch the asset from an external host.

### Requirement 20: Light, Dark, And Contrast

**User Story:** As a campaign planner, I want every new element to look right in both modes, so that I can read everything whichever theme I use.

#### Acceptance Criteria

1. THE Webapp SHALL take every colour of every Part 8 element (Job_Buttons including the Running_State, Border_Trace, Hover_Breath and Completion_Fireworks; Toasts in the Toast_Stack including Completion_Stories; Input_Pills; Animated_Numbers; the Group_Visual; and the Results_Reveal) from Design_Tokens_Block tokens, so that in light mode each element uses only the light value of each `light-dark()` pair and in dark mode uses only the dark value.
2. THE Webapp SHALL give all Part 8 text a contrast ratio of at least 4.5:1 against its background in light mode and in dark mode, or at least 3:1 for text that is at least 18.66 px bold or at least 24 px at any weight, including text drawn over the Diamond_Lattice fill and text inside the Running_State.
3. THE Webapp SHALL give every Part 8 non-text element needed to read state, namely the focus ring, the selected Map_Area or selected Group_Carousel item outline, Map_Area borders, and the Toast edge, a contrast ratio of at least 3:1 against the adjacent background in light mode and in dark mode.
4. WHEN the user switches theme in Streamlit Settings, THE Toasts, Job_Buttons, Input_Pills, and any Animated_Numbers rendered in the parent page SHALL show the new mode's token values without a Streamlit rerun and without a page reload, and a visible Toast or a Job_Button in the Running_State SHALL keep its content, position, and animation progress.
5. WHEN the user switches theme in Streamlit Settings, THE Group_Visual running inside an iframe SHALL show the new mode's token values, received from the `app/theme.py` helpers, no later than the first Streamlit rerun after the switch.
6. WHILE the Group_Visual is waiting for that first rerun after a theme switch, THE Webapp SHALL keep the whole iframe in the previous mode's token values, with no mix of light and dark values inside the iframe.
7. THE Webapp SHALL make every Part 8 interactive element, including each Map_Area (including the NCR inset bubble), each Group_Carousel item and its rotate controls, each Toggle_Card option, and each dismissible Toast, reachable with the Tab and Shift+Tab keys, and activatable with Enter or Space with the same effect as a mouse click.
8. WHEN a Part 8 interactive element receives keyboard focus, THE Webapp SHALL draw a focus ring at least 2 px wide in the `--pan-focus` token colour that is fully visible and not clipped by the element's container, in light mode and in dark mode.

### Requirement 21: Verification And Report

**User Story:** As the product owner, I want each feature checked the same way and reported clearly, so that I know what changed and what to look at.

#### Acceptance Criteria

1. WHEN a task is implemented, THE developer SHALL run the affected tests for that task, meaning every test file under `tests/` that imports a module changed by the task or a module that imports one, plus `tests/test_part5_personas_apptest_smoke.py` and `tests/test_part5_theme.py`, and SHALL run no other test files for that task.
2. WHEN the tests for a task have run, THE developer SHALL mark the task complete only if every test in `tests/test_part5_personas_apptest_smoke.py`, `tests/test_part5_theme.py`, and the affected tests passes, with only the six pre-existing Part 1 Hypothesis timeouts excluded from this pass condition.
3. IF any test required by criterion 2 fails, THEN THE developer SHALL leave the task incomplete, and THE Change_Report SHALL name each failing test and the task it belongs to.
4. THE Part 8 changes SHALL add, for every new pure helper in `src/webapp_core/` (a function or class with no Streamlit import and no file, network, or session-state access), a unit test file named `tests/test_part8_<area>_unit.py` containing at least one test that calls that helper and checks its return value.
5. THE Change_Report SHALL list every file added, changed, or deleted by Part 8, and for every changed test expectation SHALL give the test name, the old expectation, the new expectation, and the reason for the change.
6. THE Change_Report SHALL contain one browser checklist per Part 8 feature, and each checklist SHALL have a pass/fail item for each of: light mode, dark mode, Reduced_Motion on, Reduced_Motion off, and no entry animation replaying on an Unrelated_Rerun.
7. IF the licensed Dax or Avenir Next font file is missing when the Change_Report is written, THEN THE Change_Report SHALL state, for each missing font, the `--pan-font-*` token it backs and the fallback font family the Webapp rendered in its place.
8. THE Change_Report SHALL list the test files run for each task with their pass/fail result, and SHALL list the six pre-existing Part 1 Hypothesis timeouts as excluded from the pass condition and out of scope.

### Requirement 22: Seamless Transitions

**User Story:** As a campaign planner, I want every state change to feel like one continuous flow, so that I never see a jump or flash.

#### Acceptance Criteria

1. THE Webapp SHALL take the duration and easing of every Part 8 transition and animation from the shared Design_Tokens_Block motion tokens, with no one-off duration or easing value in Page_Code.
2. WHEN content that appears later (the Group_Visual, the persona cards area, or the results) is rendered, THE Webapp SHALL render it into reserved space, a fixed-height container or a skeleton placeholder, so that the page above and below it does not shift when it appears.
3. THE Group_Visual SHALL use one fixed reserved height for the Region_Map, the Group_Carousel, and the Toggle_Card, so that switching between kinds does not shift the page.
4. WHEN a Job runs, THE Webapp SHALL run the button press, the Border_Trace, the loader overlay, the Completion_Story, the Toast, and the Results_Reveal in that order, with no blank frame, no hard cut, and no double flash between steps.
5. WHEN an input or the What-If slider changes a shown result, THE Webapp SHALL update the result in place with a crossfade or a number roll, and SHALL NOT remove the result and redraw it.
6. WHEN the user switches tabs, THE Webapp SHALL crossfade the tab content over 150 to 200 ms using the shared motion tokens, animating only `opacity`.
7. WHEN the split visual kind changes between the Region_Map, the Group_Carousel, and the Toggle_Card, THE Webapp SHALL crossfade the new kind in the same reserved space over 150 to 200 ms.
8. WHILE a Streamlit rerun is running, THE Webapp SHALL restyle the default stale styling of element containers (`data-stale="true"`) so that stale elements stay fully readable and change only through the shared motion tokens, for example a subtle opacity no lower than a floor defined in the design, with no sudden grey-out and no flash.
9. THE design document SHALL state what Streamlit allows for the stale-element restyle in criterion 8, and SHALL record the closest allowed behaviour where Streamlit does not allow the full restyle.
10. THE Webapp SHALL make everything that enters use the same rise plus fade, everything that leaves use a fade, and the carousel rotation move in the direction of the arrow or key pressed.
11. IF a transition does not make a change easier to follow, THEN THE Webapp SHALL omit that transition rather than add it.
12. WHILE Reduced_Motion is active, THE Webapp SHALL replace every transition in criteria 1 to 10 with an instant change or an opacity fade of 150 ms or less.
13. WHEN the Selected_Group changes, THE Webapp SHALL play the Group_Change_Crossfade once on the persona cards, using opacity only, for about 150 ms with the shared ease-out token, and SHALL NOT play the Results_Reveal.
14. THE Group_Change_Crossfade SHALL use the one-shot approach: THE Webapp SHALL draw the animated markup only on the render where the Selected_Group changed, detected by comparing the Selected_Group to the value stored for the previous render, and every other render SHALL draw the finished state, so that the crossfade never replays on an Unrelated_Rerun that leaves the Selected_Group unchanged.
15. WHILE Reduced_Motion is active, THE persona cards SHALL swap instantly with no Group_Change_Crossfade.
16. WHEN a Job finishes successfully, THE Webapp SHALL draw the loader overlay one final time in a finishing state on the completion render, which plays the Completion_Story's hand-off and then fades the overlay out with a CSS animation using `animation-fill-mode: forwards`, ending at opacity 0 with `pointer-events: none`, with no JavaScript. THE Completion_Toast SHALL arrive while the overlay fades, and on the next rerun THE Webapp SHALL draw no overlay.
17. IF the finishing overlay proves unworkable in Streamlit, THEN THE design document SHALL record why, and THE Webapp SHALL keep the approved timing approach, in which the overlay is removed at the same time as the Completion_Toast enters.
18. IF a Job ends with an error, THEN THE Webapp SHALL draw no finishing overlay.
19. WHILE Reduced_Motion is active, THE finishing overlay SHALL fade out in 150 ms or less, or be removed instantly.
20. THE design document SHALL record the Streamlit version (1.66.1) against which every Streamlit internal selector or attribute used by Part 8 was checked, and SHALL list each one (for example `data-stale`, `stElementContainer`, `st-key-*` classes, `stTabPanel`, `stTextInput*`, `stNumberInput*`, `stAlert`, `stMainMenu`), so that a future break can be traced.
21. THE Change_Report SHALL contain one browser checklist item for each of criteria 1 to 19, since automated tests cannot verify them.
