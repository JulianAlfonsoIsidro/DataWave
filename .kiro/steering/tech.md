# Tech Stack

## Language & runtime

- Python 3.10+ (uses `from __future__ import annotations`, PEP 604 `X | None` type hints).
- No build step — pure Python package run directly.

## Libraries

- **pandas / numpy** — all data loading and transformation.
- **scikit-learn** — model utilities, calibration, cross-validation (StratifiedGroupKFold, leave-one-promo-out).
- **xgboost** — the Part 1 propensity booster.
- **shap** — per-lead top-3 driver explanations.
- **streamlit** — the Part 5 webapp.
- **python-dotenv** — environment config.
- **pytest** — unit and integration tests.
- **hypothesis** — property-based testing (the dominant test style here).

Dependencies live in `requirements.txt` (unpinned). Install into the repo's `.venv`.

## Import model (important)

- The code uses a `src/` layout with **absolute imports** against package names (e.g. `from part1_optin.config import Config`), not relative-to-repo imports.
- Running any pipeline or the webapp requires `src` on the path via `PYTHONPATH=src`.
- Tests get this for free: `tests/conftest.py` prepends `src/` to `sys.path`.

## Common commands

Run from the repo root. On Windows PowerShell, set `PYTHONPATH` with `$env:`.

```powershell
# Install dependencies
pip install -r requirements.txt

# Run the full batch pipeline end to end (regenerates outputs/ artifacts)
$env:PYTHONPATH="src"; python src/run_pipeline.py

# Run a single stage
$env:PYTHONPATH="src"; python -m part1_optin.main
$env:PYTHONPATH="src"; python -m part4_cards.main

# Launch the webapp (reads the fitted model + artifacts from outputs/)
$env:PYTHONPATH="src"; streamlit run app/main.py

# Run the test suite
pytest

# Run one test file
pytest tests/test_part1_integration.py
```

Stages accept `--<name>` CLI flags to override input/output paths; defaults are the canonical `data/` and `outputs/` paths defined in each package's `config.py`.
