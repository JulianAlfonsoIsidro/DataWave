# DataWave: Promo Audience Manager (PAM)
How can CRMs leverage AI + data to link the right customers with the right offers? 

**Promo Audience Manager** is a hackathon project that helps a retail bank design and target customer promotions. This repository contains a Streamlit web app allowing CRMs to turns customer profiles, balances, transactions, contact history and past promos into a **ranked leads, audience personas, and actionable insights**. for a given promo. 

This repository is submitted for BPI's DataWave 2026.

> **Prototype.** PAM uses **2,000 synthetic customers**, not actual bank records. Its predictions are illustrative, not validated for real-world deployment. A human must review recommendations before any campaign is sent.

## The problem

A CRM manager planning a promotion (e.g. "top up your savings by ₱50,000") must decide who should receive it. Sending messages to everyone increases costs and customer fatigue, while choosing an audience without evidence can miss potential participants. 

**PAM helps answer three questions:** Who should we target? How should we reach them? What results might we expect?

**Intended users:** CRM and campaign managers at a bank. They are not expected to read code or model output, so every figure in the app carries a plain-language description, and a **?** button opens Help And FAQs.

## What PAM does


- **Predicts participation:** estimates each customer's likelihood of joining a promotion and explains the top three factors behind the score.
- **Creates four actionable segments:** Ready Toppers, Untapped Wealth, Willing but Stretched, and Not Now, based on predicted interest and financial capacity.
- **Recommends campaign actions:** provides a decision card for each segment with a suggested channel, message angle, expected joiners, and expected value.
- **Explores customer personas:** groups similar customers and suggests relevant actions.
- **Lets managers explore:** compare different promotional thresholds, review past campaigns, and ask an AI assistant questions about campaign-level results.
- **Exports reviewable lead lists:** prepares eligible send lists and summary reports.

## How PAM works

1. **New Promo:** Enter its product, mechanic, threshold, reward, eligible segments, and channels; or open the upload tab and add a campaign PDF or DOCX (up to 10 MB). Uploaded fields are tagged "Found in Document" or "Needs Input", and uploading never runs the analysis. Click Run Analysis to display findings in Results tab.
2. **Results:** Shows the threshold used, the 2x2 segment grid and the decision cards. **Download Recommended Leads** gives the sendable leads for the segment marked "Act first". The **Download Leads** dropdown gives one file per segment, with the threshold in the file name. 3. **What-If:** Move the threshold slider to see how changing the promotional threshold affects the forecast.
4. **Personas:** Pick a grouping, choose attributes and build personas. Shows the traits and recommended actions per persona.
5. **Past Promos:** Browse completed campaigns, sorted by Newest, Oldest or Most Similar to current campaign.
6. **Ask Assistant:** Ask about campaign-level questions. It sees aggregate results only and declines questions about a single client.

### A quick guide to the results
The app's **?** button opens **Help And FAQs** for plain-language explanations of the numbers, definitions, and assumptions.

- **Clients** = Not Contacted + Control Group + Sendable.
- **Expected Joiners** = sum of the predicted joining probabilities for sendable customers. This is a **forecast**, not a guaranteed outcome.
- **Control Group** = approximately 10% of otherwise eligible leads, held out to help assess campaign impact.
- **Expected Value** uses a prototype assumption of **₱1,000 per joiner**.
- **Act first** identifies the segment PAM recommends prioritizing; it is not an automatic campaign launch.

## Technology at a glance

PAM combines predictive machine learning, transparent business rules, clustering, and generative AI. Each has a different job:

| Component | Technique | Purpose |
| --- | --- | --- |
| Lead scoring | XGBoost with probability calibration | Predicts each customer's chance of joining a promotion |
| Score explanations | SHAP | Identifies three key factors for each prediction |
| Personas | K-prototypes, KMeans, or KModes | Finds patterns among customers based on selected attributes |
| Language assistance | Amazon Bedrock, with rule-based Demo Mode | Helps read campaign files, answer questions, and optionally name personas |

**Important distinction:** Generative AI does **not** calculate forecasts, score customers, or assign segments. Numeric results come from the predictive model and the app's business logic.

## Setup

**Requirements:** Python 3.10 or newer. Run all commands from the **repository root**. The pipeline must generate the model and output files before the app can display results on a fresh clone.

### 1. Install dependencies

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

### 2. Generate the model and outputs

**Windows PowerShell**

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe src/run_pipeline.py
```

**macOS / Linux**

```bash
PYTHONPATH=src .venv/bin/python src/run_pipeline.py
```

This prepares customer/network features, the opt-in model, segments, and decision cards. Generated files are stored in `outputs/`, which is excluded from Git. Synthetic input data is provided in `data/` and can be updated using official pseudonymized banking datasets.

### 3. Launch PAM

**Windows PowerShell**

```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m streamlit run app/main.py
```

**macOS / Linux**

```bash
PYTHONPATH=src .venv/bin/python -m streamlit run app/main.py
```

Open **http://localhost:8501** in your browser.

**No AWS credentials?** You can still explore PAM. AI-powered features fall back to a clearly labeled **Demo Mode** using built-in rules.

## Optional: enable Amazon Bedrock

Bedrock supports optional language features, including campaign-file extraction, the assistant, and persona naming. **Never commit or share your `.env` file.** Copy `.env.example` to `.env` in the repository root and provide your own AWS settings:

```dotenv
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_SESSION_TOKEN=...  # temporary credentials only
AWS_REGION=...
BEDROCK_MODEL_ID=...
```

The chosen model must be available in your AWS region and support Bedrock's Converse API. The AWS identity needs permission to invoke it. When a Bedrock request cannot run, that feature uses rule-based Demo Mode instead. 

Uploaded campaign text is sent to Bedrock only after the user chooses the Bedrock option. phones, email addresses, and long digit strings are masked first. For implementation details and token usage, see [`docs/ai-token-report.md`](docs/ai-token-report.md) and the code in `src/ai/`.

## Limitations and Responsible Use

PAM is a proof-of-concept developed for BPI DataWave 2026. It demonstrates how predictive analytics, customer segmentation, and generative AI can support more informed campaign decisions. The following considerations guide its evaluation and potential future deployment:

- **Synthetic Data:** PAM uses 2,000 synthetically generated customers and historical promotion records. This allows the complete workflow to be demonstrated without exposing actual banking information. Future deployment would require training and validating the model using representative real-world data.

- **Prototype Assumptions:** Campaign value (₱1,000 per joiner), control-group allocation (10%), and channel costs are predefined for demonstration and can be refined to reflect actual business requirements.

- **Predictive Estimates:** Expected joiners and campaign savings are model-based forecasts rather than guaranteed outcomes. Actual performance would need to be measured through campaign testing.

- **Model and AI Validation:** Predictive performance and fairness require evaluation on real-world data. Generative AI responses may require verification, particularly for campaign recommendations and messaging.

- **Human Oversight:** PAM supports CRM decision-making rather than replacing it. Campaign parameters, recommendations, and generated content remain subject to human review and approval. The application does not automatically send messages.

- **Future Deployment:** Integration with banking systems would involve additional safeguards, including data privacy, consent management, access controls, security, ongoing model monitoring, and real-world performance evaluation.

For planned AI evaluation procedures, see [`docs/ai-validation-plan.md`](docs/ai-validation-plan.md).

## Tests and known issues

The project uses **pytest** and **Hypothesis**. From the repository root:

**Windows PowerShell**

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

**macOS / Linux**

```bash
.venv/bin/python -m pytest tests
```

## Project layout

```
app/        Streamlit app: composition and styling only (main.py, pages, styles.css, static/)
src/        Pipeline and logic (run with PYTHONPATH=src)
  part1_optin/ part2_network/ part3_segments/ part4_cards/   batch stages
  part5_personas/   optional persona generation
  ai/               Bedrock client, extractor, assistant, privacy, mock fallbacks
  webapp_core/      pure logic behind the app, no Streamlit imports
data/       Synthetic input CSVs and the generator
outputs/    Generated model, scores, cards and leads (git-ignored)
scripts/    One-off tools (token measurement, map build)
tests/      pytest and Hypothesis suite
docs/       AI token report and AI validation plan
.kiro/specs/ Per-part specs (Parts 1 to 9)
.env.example Template for Bedrock settings
```

## Reproducibility notes

- Customer records ending in `_answer_key` are **not** used as model inputs.
- The scoring model trains on historical synthetic promotions **P001–P003**.
- Random operations use **seed 42**.
- Channel names must match `In-app`, `Email`, and `SMS` exactly.

## Additional resources

- [`TECH_STACK.md`](TECH_STACK.md) — libraries, technologies, assets, and credits.
- [`docs/ai-validation-plan.md`](docs/ai-validation-plan.md) — proposed AI evaluation approach.
- [`docs/ai-token-report.md`](docs/ai-token-report.md) — AI feature token measurements.
- [`docs/PITCH_CHEATSHEET.md`](docs/PITCH_CHEATSHEET.md) — how every number is calculated, model results, feasibility, and pitch Q&A.
