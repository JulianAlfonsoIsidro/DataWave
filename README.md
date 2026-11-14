# DataWave: Promo Audience Manager

DataWave is a hackathon project that helps a retail bank design and target customer promotions. It turns customer profiles, balances, transactions, contact history and past promos into a ranked, segmented audience for a given promo. The app is the **Promo Audience Manager**, a Streamlit web app for CRM managers.

All data is synthetic (2,000 generated customers). No real bank records are used.

## What it does

- **Scores each lead** with a calibrated model that predicts the chance of joining a promo, and explains the top three reasons.
- **Splits clients into four segments** by propensity and capacity: Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now.
- **Builds a decision card per segment** with the channel, message angle, expected joiners and expected value.
- **Exports sendable lead lists** that respect do-not-contact and control-group rules.
- **Groups leads into personas** with plain-language traits and recommended actions.
- **Answers questions** about the current campaign with an AI assistant (AWS Bedrock), or a rule-based Demo Mode without credentials.

## Setup

Requires Python 3.10 or newer. Run these from the repo root in PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run the pipeline

The app reads the fitted model and artifacts from `outputs/`, which is git-ignored. Generate them first:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src/run_pipeline.py
```

This runs the stages in order: network features, opt-in model, segments, action cards. If a stage fails, later stages do not run and `outputs/` stays as it was.

To run one stage on its own:

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m part1_optin.main
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m part4_cards.main
```

If `data/` has no input CSVs, generate them with `data/gen_data.py`.

## Launch the app

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Then open http://localhost:8501.

## How to use the app

1. **New Promo:** fill in the promo form, or open the upload tab and add a campaign PDF or DOCX (up to 10 MB). Uploaded fields are tagged "Found in Document" or "Needs Input", and uploading never runs the analysis. Click Run Analysis. You land on Results.
2. **Results:** shows the threshold used, the 2x2 segment grid and the decision cards. **Download Recommended Leads** gives the sendable leads for the segment marked "Act first". The **Download Leads** dropdown gives one file per segment, with the threshold in the file name. Use the **?** button for Help And FAQs, which explains how every number is calculated.
3. **What-If:** move the threshold slider to rescore the audience. It shows the result as run, at the new threshold, and the change.
4. **Personas:** pick a grouping, choose attributes and build personas. The page shows one segment's personas at a time, and Expected Joiners By Persona appears on the cards.
5. **Past Promos:** browse completed campaigns, sorted by Newest, Oldest or Most Similar, with predicted against actual join rates.
6. **Ask Assistant:** ask about the current campaign. It sees aggregate results only and declines questions about a single client.

### Reading the numbers

- **Clients** = Not Contacted + Control Group + Sendable.
- **Expected Joiners** is the sum of each sendable lead's chance of joining. It is a forecast, so it is shown as a whole number with the forecast in brackets, such as `87 (Forecasted: 87.3)`.
- The **control group** is a holdout of about 10% of each group's non-excluded leads.
- Value per joiner is ₱1,000.

## AI features and Demo Mode

AI features call AWS Bedrock. Put the settings in a `.env` file at the repo root. It is git-ignored, so never commit it.

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...      # only if your credentials are temporary
AWS_REGION=...
BEDROCK_MODEL_ID=...
```

Without credentials, or if any call fails, each AI feature falls back to a rule-based mock and shows a **Demo Mode** badge. Uploaded text is sent to Bedrock only after a deliberate click, with phones, emails and long digit strings masked. Token use per feature is in `docs/ai-token-report.md`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

Tests use pytest and Hypothesis (property-based testing is the main style). To run the UI-related set only:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_part5_theme.py tests/test_part5_personas_apptest_smoke.py tests/test_part7_apptest_smoke.py
```

Six Part 1 Hypothesis tests time out today. They are known and unrelated to personas.

## Project layout

```
app/        Streamlit app: composition and styling only (main.py, pages, styles.css, static/)
src/        Pipeline and logic (run with PYTHONPATH=src)
  part1_optin/ part2_network/ part3_segments/ part4_cards/   batch stages
  part5_personas/   optional persona generation
  ai/               Bedrock client, extractor, assistant, privacy, mock fallbacks
  webapp_core/      pure logic behind the app, no Streamlit imports
data/       Input CSVs and the synthetic generator
outputs/    Generated model, scores, cards and leads (git-ignored)
tests/      pytest and Hypothesis suite
docs/       AI token report and validation plan
.kiro/specs/ Per-part specs (Parts 1 to 9)
```

## Rules to keep

- Files containing `_answer_key` are never used as model inputs.
- All random operations use seed 42.
- Channel labels must match exactly (`In-app`, `Email`, `SMS`). A mismatch makes leads unreachable and zeroes out expected joiners.

## Demo video

The app demo video was made with HyperFrames, which renders HTML to video. Its screens were captured from the running app with `video/scripts/capture_app.py`. That script needs the app running at http://localhost:8501 and Chrome installed.

## More

See [TECH_STACK.md](TECH_STACK.md) for the full list of libraries, tools, fonts, assets and credits.
