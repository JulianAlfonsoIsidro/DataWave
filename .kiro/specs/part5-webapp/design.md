# Design Document

## Overview

Part 5 Webapp is a thin Streamlit presentation-and-orchestration layer over the existing Part 1-4 packages. It adds no new modelling: the NEW PROMO and WHAT-IF flows call `part1_optin.scoring.score_promo` (reusing the already-fitted calibrated model), a new reusable `part3_segments` segment-assignment entry point, and `part4_cards.build_cards`. PAST PROMOS reads the on-disk `outputs/cards.json` and `data/promo_leads.csv`. A separate `src/run_pipeline.py` regenerates those on-disk artifacts by running the four batch pipelines in order.

The design keeps all testable logic in small pure functions in `src/webapp_core/` so the UI file (`app/main.py`) stays a declarative composition of Streamlit calls and styling. The five property tests target those pure functions.

### Goals

- Reuse the fitted model and the Part 1/3/4 APIs unchanged except for exposing one reusable segment-assignment function.
- Keep scoring/segmentation/card logic out of `app/main.py`; put it in importable, unit- and property-testable functions.
- Apply the Theme matching the BPI public website (white page, Poppins, deep red + red gradient), with the exact reds sampled from the website reference screenshot.

### Non-Goals

- No model retraining or recalibration anywhere in the app.
- No LLM; ASK ASSISTANT is a static placeholder.
- No persistence of app runs; results live in Streamlit session state for the session only.

## Architecture

```
app/
  main.py                 # Streamlit entry: page config, Theme, chrome (utility/nav/breadcrumb/hero)+tabs, routing
  theme.py                # loads styles.css + utility_bar/nav_bar/breadcrumb/hero/card/tile/chip helpers
  styles.css              # single stylesheet (BPI-web look): Poppins, reds, cards, tiles, chips
.streamlit/
  config.toml             # [theme] base colors (deep red / white / charcoal) matching the website
src/
  run_pipeline.py         # Pipeline_Runner: part2 -> part1 -> part3 -> part4
  webapp_core/
    __init__.py
    model_io.py           # load_model(outputs_dir) -> Calibrated_Model (no retrain)
    audience.py           # select_eligible_clients(...), latest_adb(...)
    run_promo.py          # run_promo(promo_spec, model, config, data) -> RunResult
    past_promos.py        # predicted_vs_actual(cards, promo_leads, sendable) -> rows
    promo_id.py           # next_promo_id(existing) -> "NEW-001"
src/part3_segments/
  segments.py             # + assign_segments(scored, promo_dict, frames) wrapper
```

Data flow for a RUN (Requirement 3):

```
New_Promo_Form -> Promo_Spec (promo_dict, min_adb, eligible_segments)
   -> select_eligible_clients(data/) -> clients_df (client_id)
   -> score_promo(promo_dict, clients_df, model, config) -> scored (p_join, drivers)
   -> assign_segments(scored, promo_dict, frames) -> segments_df (segment, capacity_php, ...)
   -> build_cards(segments_df, promo_dict) -> cards
   -> RunResult{promo_spec, scored, segments_df, cards} held in st.session_state
```

WHAT-IF (Requirement 6) reruns the middle three steps with a new `threshold_php`, on the same `clients_df` and the same loaded `model` -- `score_promo` is called again because `threshold_php` is a model feature, but the model object is never refit.

## Components and Interfaces

### Pipeline_Runner (`src/run_pipeline.py`)

`main(argv=None) -> int`. Runs the four stages in order by invoking each package's `main([])` in-process (`part2_network.main`, `part1_optin.main`, `part3_segments.main`, `part4_cards.main`). A stage returning non-zero stops the run and returns that code before the next stage; a clean run returns 0 (Requirements 1.1, 1.2). Ends with `if __name__ == "__main__": raise SystemExit(main())`.

### model_io.load_model (`src/webapp_core/model_io.py`)

`load_model(outputs_dir: Path) -> Calibrated_Model`. Reconstructs the `Calibrated_Model` from the three persisted artifacts (there is no existing loader; `Calibrated_Model.save` writes them):

- `model_part1.json` -> `xgboost.Booster().load_model(...)` (the SHAP booster).
- `model_part1.sidecar.json` -> `FeatureSchema.from_dict(doc["schema"])` and the `calibrated_path` filename.
- `<calibrated_path>` -> `pickle.load(...)` for the `CalibratedClassifierCV`.

Returns `Calibrated_Model(calibrated=..., booster=..., schema=...)`. Raises `FileNotFoundError` naming the first missing artifact; the app catches it and shows the "run src/run_pipeline.py" message (Requirements 1.3, 1.4). All three fields are required because `score_promo` uses `schema` and `predict_proba` (calibrated) and `Explainer(model)` builds `shap.TreeExplainer(model.booster)`.

### audience.select_eligible_clients (`src/webapp_core/audience.py`)

`select_eligible_clients(customer_dna, adb_monthly, eligible_segments, min_adb) -> DataFrame`. Pure. Computes each client's latest-month ADB (max `month` per `client_id` in `adb_monthly`, missing -> 0), keeps clients whose `customer_dna.segment` is in `eligible_segments` AND whose latest ADB >= `min_adb`, and returns a frame with at least `client_id` (plus `latest_adb`, `segment`) in stable `client_id` order. Eligible segments here are the Customer_DNA segments (e.g. "Affluent-Preferred"), distinct from the four Part 3 Segment_Labels used in the Results_Grid.

### part3_segments.assign_segments (new wrapper in `segments.py`)

`assign_segments(scored, promo_dict, frames) -> DataFrame`. Exposes the existing quadrant logic for an in-memory scored frame. The existing `assign(frames)` expects `frames["scores"]` plus `adb`, `features`, `promo_history`; the wrapper assembles those from the scored frame and the promo (synthesizing a one-row `promo_history` carrying `promo_dict["threshold_php"]`), calls the shared internal quadrant computation, and returns a Segments_File-shaped frame (`promo_id`, `client_id`, `p_join`, `capacity_php`, `segment`, `top_driver_1..3`). The quadrant assignment inside `assign` is refactored into a helper both `assign` and `assign_segments` call, so the logic is defined once.

### run_promo.run_promo (`src/webapp_core/run_promo.py`)

`run_promo(promo_spec, model, config, data) -> RunResult`. Orchestrates select -> score -> assign -> cards and returns a `RunResult` dataclass `{promo_spec, scored, segments_df, cards, sendable_by_segment}`. If no client is eligible, returns a `RunResult` with empty frames and `cards=[]` so the UI shows the empty-audience message (Requirement 3.4). WHAT-IF calls `run_promo` again with a patched `threshold_php` (Requirement 6.2).

### past_promos.predicted_vs_actual (`src/webapp_core/past_promos.py`)

`predicted_vs_actual(cards, promo_leads, sendable_ids_by_cell) -> list[Row]`. Pure. For each Past_Promo card: `predicted = expected_joiners / sendable_count` (NA when `sendable_count == 0`); `actual = mean(joined)` over that cell's Sendable_Leads found in `promo_leads` (NA when the cell has no Sendable_Leads) (Requirements 5.2, 5.4). Sendable lead ids per cell come from the per-segment leads files the Part 4 pipeline wrote under `outputs/leads/` (the same sendable set the cards summarize).

### promo_id.next_promo_id (`src/webapp_core/promo_id.py`)

`next_promo_id(existing) -> str`. Pure. Returns `NEW-001` when no `NEW-###` ids exist, else one past the max seen, zero-padded to three digits (Requirement 3.1).

### UI (`app/main.py` + `app/theme.py`)

`app/main.py` sets `st.set_page_config(layout="wide")`, injects the Theme stylesheet once, renders the BPI-web chrome (top utility bar, main nav bar with the red text brand, a breadcrumb row, and a hero with a red-gradient KPI panel), then the Title Case tabs (New Promo, Results, What-If, Ask Assistant, Past Promos), and routes to each tab body. Session state holds the current `RunResult`. `app/theme.py` loads the single stylesheet `app/styles.css` (via `build_css()`/`inject_css()`) and exposes small render helpers (`utility_bar()`, `nav_bar()`, `breadcrumb()`, `hero_text_html()`/`hero_kpi_html()`, `card()`, `tile()`, `chip()`; `header()` is kept as a back-compat alias for `nav_bar()`), so `main.py` reads as composition.

## Theme (Requirement 2)

The reds are sampled from the BPI website reference screenshot and recorded once in both `.streamlit/config.toml` `[theme]` and the `PALETTE` dict in `app/theme.py`; the full visual system lives in the single stylesheet `app/styles.css`, which `app/theme.py` loads once (its palette hexes also appear there as CSS variables, keeping the two in sync). Palette: `PRIMARY_RED` `#AE1319` (deep red brand/buttons), `RED_BRIGHT` `#D8232A` (gradient end), `ACCENT_GOLD` `#C9A227` (small accent, used sparingly if at all), `PANEL_WHITE` `#FFFFFF`, `TEXT_DARK` `#2B2B2B` (charcoal). The stylesheet imports Poppins; sets a white page with a centered ~1200px column and generous whitespace; hides Streamlit's default header, menu, footer and sidebar toggle; and styles the top utility bar, the main nav bar (red text brand, dark Title Case nav items, active item red under a thin red underline), the gray breadcrumb, the hero (left: big title + one-line subtitle + red-gradient pill button with an arrow; right: a rounded red-gradient KPI panel with the expected-joiners number in large white text), the red-gradient pill buttons (white secondary buttons with a red border), the underline tab strip, the white 16px-rounded cards with a soft shadow and red headings, the 2x2 tiles (Ready Toppers red-gradient with white text, the rest white with a thin red border), the rounded form inputs and red sliders, and the small stat chips. No logo image is used; the brand is text only (Requirement 2.2, 2.3).

## Data Models

```python
@dataclass(frozen=True)
class PromoSpec:
    promo_id: str            # "NEW-001"
    product_type: str
    mechanic: str            # TOP_UP | NEW_ACCOUNT | ADB_INCREASE | other (warns)
    threshold_php: float
    reward: str
    eligible_segments: list[str]   # Customer_DNA segments
    min_adb: float
    channels: list[str]
    def to_promo_dict(self) -> dict  # keys score_promo/build_cards expect

@dataclass
class RunResult:
    promo_spec: PromoSpec
    scored: pd.DataFrame            # client_id, p_join, top_driver_1..3
    segments_df: pd.DataFrame       # Segments_File-shaped
    cards: list[dict]               # one per Cell
    sendable_by_segment: dict[str, pd.DataFrame]
```

Segment grid mapping (Requirement 4.1): rows = score high/low, columns = capacity low/high ->
`(high, low)=Willing but Stretched`, `(high, high)=Ready Toppers`, `(low, low)=Not Now`, `(low, high)=Untapped Wealth`.

## Error Handling

- Missing model artifact -> `load_model` raises `FileNotFoundError`; `app/main.py` catches and renders the run-pipeline message (Requirement 1.4).
- Missing `outputs/cards.json` -> PAST PROMOS catches and renders the run-pipeline message (Requirement 5.3).
- Empty eligible audience -> `run_promo` returns empty `RunResult`; NEW PROMO shows the empty-audience message (Requirement 3.4).
- RESULTS / WHAT-IF opened before any RUN -> session has no `RunResult`; those tabs render a "run a promo first" prompt (Requirements 4.4, 6.3).
- Zero Sendable_Leads in a cell -> predicted and/or actual rate is NA, never a divide-by-zero (Requirement 5.4).
- Unseen mechanic -> `score_promo` already emits a soft warning; the UI surfaces it as an `st.warning` and still shows results.

## Correctness Properties

The five property tests (your max 5) verify these invariants. Each targets a pure function in `src/webapp_core/` or the `assign_segments` wrapper.

### Property 1: Eligibility is exactly the ADB-and-segment predicate

For any `customer_dna`, `adb_monthly`, `eligible_segments`, and `min_adb`, every client returned by `select_eligible_clients` has `segment` in `eligible_segments` and latest-month ADB >= `min_adb`; every client present in the inputs but not returned fails at least one of those two conditions; and the returned `client_id`s are unique.

**Validates: Requirements 3.2**

### Property 2: assign_segments is exactly the score-vs-capacity quadrant

For any scored frame and `threshold_php`, each lead's `segment` equals the 2x2 of (`p_join` >= that promo's median `p_join`) and (`capacity_php` >= `threshold_php`) mapped onto the fixed label order Ready Toppers / Willing but Stretched / Untapped Wealth / Not Now, and every lead receives exactly one of the four labels.

**Validates: Requirements 3.3, 4.1**

### Property 3: next_promo_id is the successor of the max NEW-id

For any iterable of existing ids, `next_promo_id` returns `NEW-001` when none match `NEW-###`, otherwise `NEW-` followed by (max matched number + 1) zero-padded to three digits; the result always matches the pattern `NEW-\d{3}`.

**Validates: Requirements 3.1**

### Property 4: Predicted and actual rates are well-formed and NA-guarded

For any cards and `promo_leads`, `predicted_vs_actual` yields `predicted = expected_joiners / sendable_count` and `actual = mean(joined)` over the cell's Sendable_Leads; each rate is either in `[0, 1]` or NA, and a rate is NA exactly when its cell has no Sendable_Leads.

**Validates: Requirements 5.2, 5.4**

### Property 5: Capacity-high count is monotone non-increasing in the threshold

For a fixed eligible audience and fixed scored `p_join` / `capacity_php`, raising `threshold_php` never increases the number of capacity-high leads, so the combined Ready Toppers + Untapped Wealth count is non-increasing as the WHAT-IF threshold rises.

**Validates: Requirements 6.2**

## Testing Strategy

Pure functions are unit- and property-tested; the Streamlit UI is smoke-checked by importing `app/` render helpers, not by browser automation. Temporary artifacts go under `scratch/` only. The five properties above are implemented with Hypothesis.

### Example/edge unit tests

- `load_model` round-trips a saved model and raises naming the first missing artifact.
- `run_promo` returns an empty `RunResult` for an all-filtered-out audience.
- `run_pipeline.main` stops after a failing stage and returns its non-zero code (stages monkeypatched).
- Theme: `.streamlit/config.toml` parses and carries the sampled base colors; the single stylesheet `app/styles.css` is loaded by `build_css()`, imports Poppins, hides the default Streamlit chrome, uses the red gradient, and carries every palette color; `nav_bar()`/`header()` render the text brand with no image; and the nav items are Title Case.
- PAST PROMOS: a Past_Promo/segment with zero sendable leads renders actual as NA.
