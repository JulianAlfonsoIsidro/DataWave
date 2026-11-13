# Product

DataWave is a hackathon project that helps a retail bank design and target customer promotions. It turns raw banking data (customer profiles, balances, transactions, contact history, past promos) into a ranked, segmented, and actionable audience for a given promo.

## What it does

The product is built as four batch pipeline stages plus an interactive webapp and an optional persona step:

- **Part 1 — Opt-in propensity**: fits a calibrated model that predicts each lead's probability of joining a promo (`p_join`), with top-3 SHAP drivers per lead.
- **Part 2 — Network features**: derives customer features (e.g. outflows to other banks, inflow/spend shares) consumed by later stages.
- **Part 3 — Segments**: assigns each client one of four segment labels from a 2x2 of score (propensity) vs capacity: Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now.
- **Part 4 — Cards**: builds one action card per segment cell (dominant channel, message angle, expected joiners, expected value) and writes per-segment sendable-lead CSVs, honoring do-not-contact and control-group rules.
- **Part 5 — Webapp (Promo Audience Manager)**: a Streamlit UI to design a promo, score and segment the audience, inspect decision cards, run What-If threshold analysis, explore personas, download sendable leads, and compare predicted vs actual join rates on past promos. The app never retrains — it only reloads the fitted Part 1 model.

## Personas tab

- Leads are split into groups first, then clustered into personas within each group.
- Each persona gets a name, plain-language traits, and recommended actions.
- The live New Promo cards show an "Expected Joiners By Persona" breakdown.
- A Group_Visual follows the Demo Mode notice when a run has a split with 2+ groups: a 3D ring, a yes/no Toggle_Card, or a Philippine region map (four areas plus an NCR callout). Selecting an item sets the group dropdown. Runs with more than 12 combined groups use the dropdown only.
- Persona generation is optional and runs on demand; it does not change the Part 1–4 outputs.

## Past Promos

- The Past Promos tab shows completed campaigns only.
- Sort by Newest (default), Oldest or Most Similar; filter by Product Type and Target Audience; five campaigns at a time with View More.
- Most Similar uses a deterministic eight-component Similarity_Score (weights sum to 100, unavailable components are rescaled). No LLM or embeddings.

## AI features (Part 7)

- **Upload Campaign File**: a PDF or DOCX (max 10 MB) is read locally and Campaign_Fields are extracted and prefilled. Each field is tagged "Found in Document" or "Needs Input". Uploading never runs the analysis.
- **Ask Assistant**: answers questions about the current campaign only. Scores, segments and personas never enter the payload.
- **Persona Narrator**: Bedrock names personas from one persona's plain-language aggregate. Clustering is untouched.
- **Demo Mode**: with no Bedrock access, or on any failure, each AI feature falls back to a deterministic rule-based Mock, shown with a Demo Mode badge. It is reported per call and never latched.
- No numeric business logic in AI code. Every number comes from the run.
- **Impact summary and Export_Workbook**: Baseline vs Recommended plan, and one .xlsx with Summary, Decision Cards, Personas and a Send List per non-Skip segment.

## Part 9 round 2 (built)

The product is now called **Promo Audience Manager** (DataWave is the project name). Its users are CRM managers, so figures must be plain and explained.

- Expected Joiners shows a whole number with the forecast in brackets, `87 (Forecasted: 87.3)`, and the Header adds `out of <sendable> sendable leads (<pct>%)`.
- Figures that need context carry one short plain description.
- The What-If table runs Ready Toppers, Willing but Stretched, Untapped Wealth, Not Now.
- Results has a Download Leads dropdown and a stacked bar chart per segment (Not Contacted, Control Group, Sendable) with its table.
- A "?" button opens Help And FAQs: how each number is calculated, plus common questions with formulas.
- Spec: Requirements 20 to 28 in `.kiro/specs/part9-layout-fixes/`.

### Number definitions (checked on the default run, threshold 530,000)

- Clients = Not Contacted + Control Group + Sendable (2,000 = 230 + 175 + 1,595).
- Expected Joiners = the sum of each sendable lead's chance of joining (204.4 in total; Ready Toppers 87.3 among 282 sendable leads). It is a forecast.
- The control group is a holdout of about 10% of each group's non-excluded leads (`CONTROL_FRACTION`). Value per joiner is ₱1,000 (`VALUE_PER_JOIN_PHP`).
- Download Recommended Leads = the sendable leads of the "Act first" segment(s).
- Personas at "All leads" cluster all clients; "By campaign" on the current run clusters the sendable leads.

## Part 9 (current branch: part9-layout-fixes)

A UI layout and polish pass. No pipeline, model or calculation changes. Spec: `.kiro/specs/part9-layout-fixes/`.

- A slim header replaces the hero: wordmark on the left, and once a run exists the current run with Expected Joiners as the one large number.
- Results opens with the threshold the results use, then an action bar. Signpost buttons move the user between sections, and a run lands on Results.
- What-If shows the figure as run, at the new threshold, and the change.
- Downloaded lead file names include the threshold. A primary "Download Recommended Leads" button covers the segment marked "Act first" (card action `Prioritize`).
- What-If rescoring is a plain slider interaction (no loader). Resetting to the as-run threshold is one click on Results or What-If.
- Personas shows one segment's persona breakdown at a time; the "How the Personas Differ" table is gone.
- Ask Assistant has a 3D stone-block avatar and a thinking indicator.
- Light/dark switch plays a liquid fill animation (skipped with reduced motion).

## Key domain rules

- Answer-key files (anything containing `_answer_key`) are forbidden as model inputs — never train or score on them.
- Only promos `P001`, `P002`, `P003` are used for training; leads are "treated" when `control_group == 0`.
- All stochastic operations use a fixed random seed (42) for determinism.
- Channel labels must match exactly (`In-app`, `Email`, `SMS`); a mismatch makes leads unreachable and zeroes out expected joiners.