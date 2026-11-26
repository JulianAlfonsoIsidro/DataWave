# Business costing report: AI inference cost of planning a campaign with PAM

**For:** BPI stakeholders. **Basis:** a benchmark of 5 real campaign proposals, 3 repetitions each, on Amazon Bedrock (`global.anthropic.claude-sonnet-5-5`), priced at $2.00 per 1M input tokens and $10.00 per 1M output tokens, converted at ₱64 per US dollar (rates supplied by the project owner).

**What these numbers cover.** AWS Bedrock AI inference only. They exclude hosting, storage, data integration, maintenance, support and every other production cost. They are **not** revenue, ROI or conversion claims.

**Which version was measured.** The figures come from an experimental version of PAM (higher answer-length limit and extraction fixes) tested on a separate branch, not from the submitted version. In a one-repetition pilot the submitted version completed 35 of 43 standard operations against 43 of 43 for the experimental version; cost per completed operation was similar. Full technical detail and all raw data: `TECHNICAL_COST_REPORT.md`.

**Measured versus estimated.** The benchmark tested individual functions, not a full planning session from start to finish. Cost per campaign below is therefore an **estimate built from measured costs of each function**. The number of prompts used in the benchmark was chosen for testing and does not show how many a CRM manager would actually send.

## 1. Headline metrics (benchmark campaign)

One benchmark campaign = upload and field extraction + campaign summary with the proposal attached + the benchmark's proposal-based assistant prompts + one persona-generation run.

| Metric | Value |
|---|---:|
| Unique campaign proposals tested | 5 |
| Average AI prompts per campaign (benchmark design) | 4.4 |
| Average total tokens per campaign | 70,390 |
| Average AI inference cost per campaign | $0.194 (₱12.40) |
| Lowest / highest campaign cost | $0.152 (₱9.74) / $0.240 (₱15.34) |
| Projected cost, 100 campaigns of this size | $19.38 (₱1,240) |
| Projected cost, 1,000 campaigns of this size | $193.76 (₱12,401) |

Lowest: 2026 Bonds Beyond Borders Manila. Highest: 2026 Better Together Bundles. Cost follows document length (longer proposals send more text to the model); Horizon also had more questions. Based on 15 complete campaign repetitions out of 15.

## 2. Campaign-level comparison

| Campaign | Number of AI prompts | Average total tokens | Average AI cost (USD) | Average AI cost (PHP) |
|---|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 4 | 60,639 | 0.1724 | 11.03 |
| Horizon Reactive Deepening | 6 | 78,000 | 0.2194 | 14.04 |
| Forex Solutions Campaign Refresh | 4 | 68,208 | 0.1851 | 11.85 |
| 2026 Bonds Beyond Borders Manila | 4 | 52,730 | 0.1522 | 9.74 |
| 2026 Better Together Bundles | 4 | 92,370 | 0.2396 | 15.34 |
| **Overall average** | **4.4** | **70,390** | **0.1938** | **12.40** |

Prompts include the campaign summary and the assistant questions; Horizon was tested with more questions than the other campaigns, which raises its cost. Each figure averages the repetitions of one proposal (repetitions are not separate campaigns).

## 3. Representative campaign-planning workflow

1. **Upload** the campaign proposal; PAM reads it and fills in the form (AI field extraction).
2. **Summarize** the campaign with the proposal attached (and regenerate if needed).
3. **Generate personas** for the audience (AI names each persona; the grouping itself costs nothing in AI usage).
4. **Consult the AI assistant** with questions about the proposal (drafts, gaps, eligibility, targeting).

Unit costs (measured averages, proposal attached):

| Step | Cost (USD) | Cost (PHP) |
|---|---:|---:|
| Upload and field extraction | 0.0309 | 1.98 |
| Campaign summary | 0.0317 | 2.03 |
| One assistant prompt | 0.0357 | 2.29 |
| One persona-generation run (3 personas) | 0.0118 | 0.76 |

For comparison, a campaign summary **without** the proposal attached costs $0.0055 (₱0.35), about 6 times less, because the proposal text is what makes the request large. The two options are alternatives and are never added together.

## 4. Usage scenarios and projections (estimates)

The scenario sizes below are **illustrative assumptions**, not observed behaviour: PAM has not been used by CRM managers in this evaluation, so there is no evidence yet for how many prompts a real campaign involves. They show how cost moves as usage grows; replace them with real usage once the app has logged some.

| Scenario | Uploads | Summaries (incl. regenerations) | Persona runs | Assistant prompts |
|---|---:|---:|---:|---:|
| Light | 1 | 1 | 1 | 3 |
| Moderate | 1 | 2 | 2 | 10 |
| Heavy | 2 | 4 | 3 | 30 |

**Estimated cost per campaign and projection** (average across the five proposals; Bedrock inference only):

| Scenario | Tokens per campaign | 1 campaign | 100 campaigns | 1,000 campaigns | Range per campaign (USD) |
|---|---:|---:|---:|---:|---:|
| Light | 65,996 | $0.182 / ₱11.62 | $18.16 / ₱1,162 | $181.59 / ₱11,622 | 0.152 to 0.240 |
| Moderate | 172,864 | $0.475 / ₱30.41 | $47.52 / ₱3,041 | $475.21 / ₱30,413 | 0.400 to 0.635 |
| Heavy | 475,150 | $1.296 / ₱82.93 | $129.58 / ₱8,293 | $1,295.81 / ₱82,932 | 1.087 to 1.743 |

For reference, the benchmark campaign itself (section 1) costs $0.194 / ₱12.40 per campaign: $19.38 for 100 and $193.76 for 1,000.

## 5. What this means for feasibility and scalability

- **Cost is small per campaign and moves in proportion to usage.** Across the three scenarios a campaign costs about ₱12 to ₱83 in AI inference ($0.18 to $1.30). Doubling the number of campaigns doubles the bill; there is no step cost in these measurements.
- **The assistant is the main variable.** Each question about an attached proposal costs about ₱2.29. The heavy scenario's 30 questions account for about 83% of its cost; the persona run is about ₱0.76 each.
- **Attaching the proposal drives cost.** It costs roughly 6 times more than asking without it, but it is what gives the assistant the campaign's facts (in the full batch, 79% to 100% of known facts were kept with the proposal against 11% to 42% without, per campaign). Long proposals cost more: the highest-cost campaign (the longest document) cost about 1.6 times the lowest-cost one (the shortest).
- **Scale.** Even 1,000 heavy campaigns come to about $1,296 (₱82,932) of inference at these rates. Whether that is acceptable depends on BPI's budget and on the excluded costs. These measurements say nothing about revenue, return on investment or customer conversion; that needs its own measurement.
- **Risks to the estimate:** the usage scenarios are assumptions; prices and the exchange rate can change; only 3 repetitions and 5 proposals were measured; and the figures apply to the experimental version.

## 6. Headline figures for a slide

1. **About ₱12 ($0.19)** average AI inference cost for a benchmark campaign (upload, summary, persona run and 4.4 AI prompts), measured on 5 real proposals.
2. **About ₱12 to ₱83 per campaign** for light to heavy use (estimate from measured unit costs).
3. **About ₱30,413 ($475) for 1,000 campaigns** at moderate use (estimate; Bedrock inference only).
4. **₱2.29 per assistant question** about an attached proposal; **₱0.76** for a full 3-persona run.
5. Measured over **132 operations and 138 model calls** across 5 proposals, 3 repetitions; total benchmark spend $3.14 (₱201).

*All figures: AWS Bedrock inference only, experimental configuration, ₱64/USD, rates supplied by the project owner. Per-campaign and scenario figures are estimates from measured operation costs.*
