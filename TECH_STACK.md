# Promo Audience Manager: Tech Stack And Build Notes

DataWave is the project name. The product is the **Promo Audience Manager**. This file lists what was used to build it, what each piece does, and the licence or credit that goes with it.

## Language and runtime

| Item | Use |
| --- | --- |
| Python 3.10+ | The whole project is plain Python in a `src/` layout. It runs with `PYTHONPATH=src` and has no build step. It uses modern type hints such as `X | None`. |
| Virtual environment (`.venv`) | All dependencies install into the repo's local venv from an unpinned `requirements.txt`. Tests add `src/` to the path through `tests/conftest.py`. |

## Data and modelling

| Library | Licence | Use |
| --- | --- | --- |
| pandas, numpy | BSD-3-Clause | Load and transform all customer, transaction and promo data. Seeded subsampling in the pipeline. |
| XGBoost | Apache-2.0 | The opt-in propensity model, which predicts each lead's chance of joining a promo. The fitted model is saved as JSON in `outputs/`. |
| scikit-learn | BSD-3-Clause | Isotonic probability calibration, stratified and leave-one-promo-out cross-validation, and `KMeans` for personas when every chosen attribute is numeric. |
| SHAP | MIT | Top three drivers behind each lead's score (`TreeExplainer`). They feed the action cards and lead exports. |
| kmodes | MIT | `KPrototypes` for personas on mixed numeric and categorical attributes, and `KModes` for categorical-only selections. Both are seeded with 42. |

## Web app and front end

| Item | Use |
| --- | --- |
| Streamlit (Apache-2.0) | Runs the app: tabs, widgets, dialogs and downloads. Built and checked on 1.66.1. It relies on some Streamlit internals, so recheck after upgrades. |
| Custom CSS design system (`app/styles.css`) | Every colour, size and duration is a named token, with `light-dark()` for the light and dark themes. A unit test blocks hard-coded colours and durations in the newer sections. |
| Vanilla JavaScript (`page_lock.js`, `ui_interactions.js`) | Page lock during long jobs, the liquid theme switch, tooltip fades, and the phone menu that hides on scroll. No npm, CDN or framework. |
| Group picker (`app/static/group_picker/`) | A Streamlit custom-component iframe in plain HTML, JS and CSS. It draws the ring, the toggle card and the Philippine region map, and runs fully offline. |
| SVG and CSS graphics | The woven background uses generated SVG masks. The stone block on assistant messages is a pure CSS cube. Loaders, count-up numbers and finish animations are CSS only. |
| HTML and CSS charts | Bar charts are built from design tokens, with no chart library, so they follow the theme and add no dependency. |

## AI and document handling

| Item | Use |
| --- | --- |
| AWS Bedrock via boto3 (Apache-2.0) | Powers Ask Assistant, campaign-file extraction and persona naming. Without AWS credentials the app runs in **Demo Mode** with rule-based answers. |
| Privacy filter (`src/ai/privacy.py`) | Masks phones, emails and long digit strings before an upload is sent. The assistant sees aggregate run results only and never per-client data. Every number shown comes from the model run, not from the AI. |
| Token tracking (`scripts/measure_ai_tokens.py`) | Measures input, output and total tokens per AI feature. Each feature has a capped `maxTokens`. Results go to `docs/ai-token-report.md`. |
| pdfplumber, python-docx (MIT) | Read uploaded PDF and Word campaign files locally. Bedrock receives extracted text only, never the original file. |
| openpyxl (MIT) | Builds the Export Workbook (.xlsx) with Summary, Decision Cards, Personas and a send list per non-Skip segment. |
| python-dotenv (BSD-3-Clause) | Loads AWS settings from a git-ignored `.env` file, so credentials stay out of source. |

## Testing

| Item | Use |
| --- | --- |
| pytest (MIT) | Unit, integration and Streamlit `AppTest` smoke tests in `tests/`. The smoke tests load each tab without a browser. |
| Hypothesis (MPL-2.0) | Property-based testing is the main style. Tests that fit real models set `deadline=None`. |
| Headless Chrome over the DevTools Protocol | A small Python driver (`video/scripts/capture_app.py`) loaded the running app for screenshots and layout checks in light mode, dark mode and at phone width. It also checked smoothness under CPU throttling. |

## Development tools

- **Kiro (AI-assisted IDE):** wrote most of the coding logic: the data pipeline, models, segmentation, personas and AI integration. It worked from specs in `.kiro/specs/` (Parts 1 to 9), with steering docs for product, structure, tech stack and UI rules.
- **Claude Code:** did most of the UI work: the Part 9 redesign, animations, layout fixes and design critique rounds in VS Code. It also ran the tests and the headless-browser checks.
- **Git and GitHub:** version control, with each part on its own branch and the UI work on `part9-layout-fixes`.

- **HyperFrames:** used to make the app demo video. HyperFrames renders HTML to video. The screens it shows were captured from the running app with the headless Chrome driver in `video/scripts/capture_app.py`, in dark mode at 1920x1080.

### Claude Code skills

- **Impeccable:** a design critique skill that scores the UI against usability principles and runs a pattern detector. Across three saved rounds the score went from 22 to 24 to 27 out of 40.
- **Hallmark:** a static check for generic, templated design patterns. The few remaining flags are deliberate and documented.
- **HyperFrames skills** (hyperframes, hyperframes-cli, hyperframes-registry, media-use): guided building and rendering the demo video.
- **Animation skills** (animate, review-animations, improve-animations and related): guided the stone block's spin and finish, the theme-switch fill, tooltip fades, and the fixes for jitter after Run Analysis. The audit plans are in `plans/`.

## Animation and visual resources

- **Beautiful UI (beautifului.dev):** reference for the AI-related animations, such as the assistant's thinking and response motion. They were adapted to the design tokens and to reduced-motion settings.
- **CodePen (codepen.io):** free CSS animations from public pens were starting points for loaders and micro-interactions, rewritten to fit the token system. Public pens are MIT-licensed by default, so keep the credit to the original authors.
- **Microsoft Copilot (images only):** generated the vector illustrations used in the app. It was not used for code or UI work. The images are local SVG assets.

## Fonts

- **Manrope** (SIL OFL 1.1): bundled in `app/static/fonts/manrope`, so the app works offline. This is the font that renders throughout the UI.
- **FF Dax and Avenir Next** (commercial, not bundled): the intended heading and body fonts. They cannot ship without licensed files, so the fallback stacks in `app/theme.py` render instead.

## Assets and credits

- **Philippine region map** (MIT plus CC BY-IGO 3.0): `ph_regions.svg` is derived from James Faeldon's `philippines-json-maps` v1.1.1 (MIT). The boundaries come from OCHA COD-AB data produced by NAMRIA and PSA. The credit "NAMRIA, PSA via OCHA" stays visible below the map.
- **`scripts/build_ph_regions.py`:** a one-off, standard-library-only script that merges the 18 regions into four areas (NCR, Luzon, Visayas, Mindanao), then simplifies and reprojects them. The app does not use it at runtime.
- **Copilot-generated illustrations:** AI-generated with Microsoft Copilot. They are not from any stock or third-party library.
- **BPI visual influence (inspiration only):** the palette, type feel and background styling take cues from BPI's app and website. No BPI logo, wordmark or asset is used.
- **Synthetic data (`data/gen_data.py`):** all input data comes from a seeded generator covering 2,000 customers. It is not real bank data. The `_answer_key_*.csv` files are never used as model inputs.

## How the system is built

1. **Part 1, opt-in propensity:** a calibrated XGBoost model gives each lead `p_join`, with top-3 SHAP drivers. Only promos P001 to P003 train it.
2. **Part 2, network features:** derives customer features such as outflows to other banks and inflow and spend shares.
3. **Part 3, segments:** a 2x2 of propensity against capacity gives Ready Toppers, Untapped Wealth, Willing but Stretched and Not Now.
4. **Part 4, cards:** one action card per segment (channel, message angle, expected joiners, expected value) and per-segment send lists that honour do-not-contact and control-group rules.
5. **Part 5, personas (optional):** leads are grouped first, then clustered into personas within each group.
6. **Parts 5 to 9, webapp:** Streamlit app with New Promo, Results, What-If, Personas, Past Promos and Ask Assistant. It reloads the fitted model and never retrains.

All random operations use seed 42. Output files are written last, so a failed run leaves `outputs/` untouched.
