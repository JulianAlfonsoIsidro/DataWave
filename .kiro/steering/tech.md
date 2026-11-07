# Tech Stack

## Language & runtime

- Python 3.10+ (uses `from __future__ import annotations`, PEP 604 `X | None` type hints).
- No build step — pure Python package run directly.

## Libraries

- **pandas / numpy** — all data loading and transformation.
- **scikit-learn** — model utilities, calibration, cross-validation (StratifiedGroupKFold, leave-one-promo-out), and `KMeans` for the numeric-only persona fallback.
- **xgboost** — the Part 1 propensity booster.
- **shap** — per-lead top-3 driver explanations.
- **kmodes** — `KPrototypes` for persona clustering and `KModes` for the categorical-only fallback.
- **streamlit** — the webapp.
- **python-dotenv** — environment config.
- **pytest** — unit and integration tests.
- **hypothesis** — property-based testing (the dominant test style here).

Dependencies live in `requirements.txt` (unpinned). Install into the repo's `.venv`.

## Clustering (personas)

- Mixed numeric/categorical selections use k-prototypes, seeded with 42.
- `KPrototypes` rejects single-type selections, so numeric-only uses `KMeans` and categorical-only uses `KModes`, both seeded with 42.

## Import model (important)

- The code uses a `src/` layout with **absolute imports** against package names (e.g. `from part1_optin.config import Config`), not relative-to-repo imports.
- Running any pipeline or the webapp requires `src` on the path via `PYTHONPATH=src`.
- Tests get this for free: `tests/conftest.py` prepends `src/` to `sys.path`.

## Common commands

Run from the repo root. On Windows PowerShell, set `PYTHONPATH` with `$env:`. This machine has no venv activate script, so call the venv interpreter directly.

```powershell
# Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run the full batch pipeline end to end (regenerates outputs/ artifacts)
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src/run_pipeline.py

# Run a single stage
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m part1_optin.main
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m part4_cards.main

# Launch the webapp (reads the fitted model + artifacts from outputs/)
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run app/main.py

# Run the test suite
.\.venv\Scripts\python.exe -m pytest tests

# Run one test file
.\.venv\Scripts\python.exe -m pytest tests/test_part1_integration.py
```

Stages accept `--<name>` CLI flags to override input/output paths; defaults are the canonical `data/` and `outputs/` paths defined in each package's `config.py`.

## Test conventions

- pytest plus hypothesis; property tests are the primary style.
- Set `deadline=None` on hypothesis tests that fit real models.
- The Personas page has Streamlit `AppTest` smoke tests (`tests/test_part5_personas_apptest_smoke.py`).
- Six Part 1 Hypothesis timeouts fail today. They are pre-existing and unrelated to personas.