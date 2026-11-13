# Project Structure

## Top-level layout

```
DataWave/
├── app/                  # Streamlit webapp (presentation layer only)
│   ├── main.py           # Streamlit entry point; builds the tabs and wires widgets to webapp_core
│   ├── persona_page.py   # Personas tab: controls, persona cards, comparison table, downloads
│   ├── upload_panel.py   # Part 7: Upload Campaign File panel on New Promo (second tab beside the form)
│   ├── assistant_page.py # Part 7: Ask Assistant tab (chat, suggested questions, Demo badge)
│   ├── past_promos_page.py # Part 7: Past Promos tab (sort, filter, paging, similarity chart)
│   ├── theme.py          # palette, CSS injection, and page chrome helpers
│   ├── ui_effects.py     # Part 8 motion: toasts, finishing overlay, page lock, number_prev, quiet_container
│   ├── group_picker.py   # declare_component wrapper for the Group_Visual (ring / Toggle_Card / map)
│   ├── styles.css        # all CSS; section 1 is the token source of truth (sections 20-27 are Part 9)
│   └── static/
│       ├── page_lock.js        # page lock while a job loader is shown
│       ├── ui_interactions.js  # Part 9: liquid theme switch, hover-text fades, menu hide, pressed buttons
│       └── group_picker/          # iframe component: index.html, picker.js, picker.css, SVG assets, licence
├── .kiro/specs/          # per-part specs; part9-layout-fixes is the latest (requirements, design, tasks)
├── plans/                # numbered UI fix plans (001-005) and a README
├── scripts/              # one-off build scripts (e.g. build_ph_regions.py)
├── data/                 # input CSVs (customer_dna, transactions, promo_history, ...)
│   ├── gen_data.py       # synthetic data generator
│   └── _answer_key_*.csv # FORBIDDEN as model inputs
├── outputs/              # generated artifacts (model, scores, cards.json, leads/)
├── src/                  # all pipeline + webapp logic (PYTHONPATH=src)
│   ├── run_pipeline.py   # orchestrates the four stages in dependency order
│   ├── ai/               # Part 7: bedrock.py (shared client), extractor, assistant, persona_narrator, archetypes, mocks
│   ├── part1_optin/      # opt-in propensity model
│   ├── part2_network/    # network / customer features
│   ├── part3_segments/   # 2x2 segment labels
│   ├── part4_cards/      # action cards + sendable leads
│   ├── part5_personas/   # persona generation (optional, not in run_pipeline.py)
│   └── webapp_core/      # pure logic behind the webapp (no Streamlit imports)
├── tests/                # pytest + hypothesis suite
├── .kiro/specs/          # per-part requirements/design/tasks specs
└── requirements.txt
```

## Pipeline package convention

Each `src/partN_*` package follows the same shape:

- `config.py` — a frozen `@dataclass Config` of input/output `Path` fields (canonical defaults), plus domain constants (seeds, column lists, markers). One place for discrepancy-prone values.
- `main.py` — the CLI entry point: `_parse_args` maps `--flag` overrides onto `Config`, a `main(argv: list[str] | None = None) -> int` runs the stage, and the module ends with `if __name__ == "__main__": raise SystemExit(main())`.
- Remaining modules are single-responsibility stages (loader → features/classify → model/cards), each a small class or function.

### Dependency order

`run_pipeline.py` runs stages as: **part2_network → part1_optin → part3_segments → part4_cards**. A stage returning a non-zero exit code stops the run before later stages execute.

### Persona generation (optional)

`part5_personas` is not part of `run_pipeline.py`. It runs on demand (`python -m part5_personas.main`, or from the Personas tab) and reads the outputs of the four stages above.

- `config.py` — frozen `Config` of paths and persona constants.
- `join.py` — builds the joined attribute set (customer profile + product ownership + Part 2 features) and gates on match rate.
- `preprocess.py` — classifies column types, imputes, scales, and returns categorical indices.
- `cluster.py` — seeded clustering, k validation, subsampling, and the elbow sweep.
- `grouping.py` — clustering levels and the group-first flow; returns named persona sets.
- `profile.py` — per-persona size, stats, and distinguishing attributes.
- `naming.py` — persona name, description, and recommended actions.
- `labels.py` — shared plain-language attribute labels, used by both naming and the page.
- `export.py` — persona-labeled leads and campaign leads exports.
- `main.py` — CLI entry point.

### Output safety

Output-producing steps (writing the model, scores, cards, leads) run **last**, after all computation succeeds, so a failure leaves `outputs/` untouched. Validation/loader gates are the only stages allowed to halt before output.

## Webapp layering

- `app/` is the declarative composition layer — it only wires Streamlit widgets and session state.
- `src/webapp_core/` holds all real logic (model reload, eligibility, promo-id generation, run orchestration). It reuses the Part 1/3/4 APIs and adds no modelling.
- `src/webapp_core/personas.py` runs the in-memory persona generation and computes the persona mix for the live cards.
- Part 7 logic in `webapp_core`: `past_campaigns.py` (load, sort, filter, page), `similarity.py` (eight-component Similarity_Score), `impact.py` (Baseline vs Recommended plan), `export_workbook.py` (.xlsx), `card_view.py`, `persona_view.py`, `threshold.py`. All pure: no Streamlit, Bedrock or network.
- `src/ai/` also has no Streamlit imports. Every AI call goes through `ai.bedrock.converse`, which never raises and falls back to a Mock (Demo Mode).
- Keep Streamlit imports out of `webapp_core`; keep business logic out of `app/`.
- Part 9 round 2, planned (spec tasks 16.1 to 16.9, not yet built):
  - New pure modules in `webapp_core`: `number_format.py` (rounded joiners, forecast text, share), `segment_flow.py` (`SEGMENT_DISPLAY_ORDER`, flow rows), `number_help.py` (plain descriptions), `help_content.py` (FAQ entries and formulas).
  - New `app/help_page.py`: the `st.dialog` opened by the `help_open` button; it only draws `help_content`.
  - Segment tables that show a fixed order import `SEGMENT_DISPLAY_ORDER` and do not define their own.
  - Figures in a rate or amount (10% control group, ₱1,000 per joiner, 1.645) are read from `part4_cards.config`, never copied into UI text.
- Part 9 navigation: the six sections are `st.tabs(theme.TAB_LABELS, key=NAV_KEY)` in `app/main.py`. Use `go_to(label)` after the tabs exist, or `_go_to_now` in a button callback. Signpost buttons use `_nav_button`.
- Part 8 presentation logic that is pure lives in `webapp_core`: `toast_queue.py` (toast queue and view planning), `number_roll.py` (digit-diff plan for the CSS number roll), `region_map.py` (four Map_Areas, PSGC codes, lead-count entries), `group_picker_items.py` (which Group_Visual fits a run, items, glass level, ring step, value sync, group-change check).
- `app/group_picker.py` is the only bridge to the picker iframe. Read its component value (`pending_selection`) before the group dropdown renders. Widget keys and labels are unchanged; new keys are `p8_*` containers and the component key `p8_group_picker`.

### Tabs in `app/main.py`

Order comes from `theme.TAB_LABELS`:

- **New Promo** — fill in the form or upload a campaign file (`upload_panel.py`), run the analysis, land on Results.
- **Results** — threshold context, action bar, 2x2 segment grid, decision cards, Download Leads (one row per segment, threshold in the file name).
- **What-If** — threshold slider that rescores the audience; shows as-run vs current. No page lock or finish animation for the slider.
- **Personas** — persona generation page (`persona_page.py`).
- **Past Promos** — sortable, filterable past campaigns with similarity and predicted vs actual (`past_promos_page.py`).
- **Ask Assistant** — campaign-only chat (`assistant_page.py`).

## Conventions

- Thorough module and function docstrings; many cite the governing spec requirement (e.g. "Requirement 6.2"). Preserve these references when editing.
- `main()` entry points return an `int` exit code; failures print to stderr naming the failing step and return non-zero.
- Error handling halts early on bad input and reports the step by name.

## Testing conventions

- Tests live in `tests/` and are named `test_<area>_<kind>.py` where kind is `unit`, `integration`, `property`, or `edge`.
- Property-based tests (hypothesis) are the primary style; shared input generators live in `tests/strategies*.py`.
- `tests/conftest.py` makes `src/` importable — never hardcode `sys.path` in individual tests.
- Part 7 tests are `tests/test_part7_*` with generators in `tests/strategies_part7.py`.
- Part 8 tests are `tests/test_part8_*_unit.py` (tokens, toast_queue, job_motion, number_roll, region_map, group_picker, assets). `picker.js` has no Python test; check it in the browser.