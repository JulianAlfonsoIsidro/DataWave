# Technical costing report: full batch evaluation

**Scope:** AWS Bedrock inference cost of PAM's AI features, measured in the full 3-repetition benchmark on the **experimental** configuration (branch `part-12-experiment`). This is an audit document: every figure can be recomputed from the CSV and raw files listed in section 11, and from `evaluation/build_cost_reports.py`, without any new Bedrock call.

**Read this first**
- **Experimental versus baseline.** The figures in this report are for the experimental configuration (assistant and extractor output caps 3,000, truncation treated as failure, segment-name fixes). They are not measurements of the submitted version (`part-11-final-changes`, caps 1,500 and 1,200). The submitted version was measured only in a 1-repetition pilot (section 9); no full batch was run on it. Experimental improvements must not be attributed to the submitted version.
- **Measured versus estimated.** Token counts, latency and per-operation costs are measured (Bedrock's own usage counts). Per-campaign costs and the usage scenarios are estimates built from measured per-operation averages (section 8 and the business report).
- **Scope of cost.** AWS Bedrock inference only. Excluded: hosting, storage, data integration, monitoring, maintenance, support and other production costs.
- **Status of this run:** 132 operations (10 categories, 3 repetitions); 132 succeeded on the final attempt. All operations succeeded on their final attempt.

## 1. Configuration and provenance

| Item | Experimental (this report) | Baseline (submitted version) |
|---|---|---|
| Branch / commit | `part-12-experiment` @ `0d85049` (base `ea775f5`) | `part-11-final-changes` @ `ea775f5` |
| Assistant output cap | 3,000 tokens | 1,500 tokens |
| Extractor output cap | 3,000 tokens | 1,200 tokens |
| Persona naming cap | 800 (unchanged) | 800 |
| `max_tokens` stop | treated as failed (reason `truncated`, usage kept) | not checked |
| Segment names | exact names in the prompt; common spellings mapped | exact match only |
| Repetitions | 3 (label `postfix`) | 1 (pilot, label `main`); a 1-repetition script-only 3,000 cap run (label `cap3000`) |
| Results | `evaluation/results/experimental/postfix/` | `evaluation/results/main/`, `evaluation/results/cap3000/` |
| Exact code differences | `evaluation/results/experimental/experimental_changes.patch` | n/a |

- **Model / inference profile:** `global.anthropic.claude-sonnet-5-5` (Amazon Bedrock Converse API, region from `.env.eval`, not recorded here).
- **Run date:** 2026-11-27. Benchmark script: `evaluation/run_benchmark.py` (identical in both configurations; no `--output-cap` override in the experimental run). Run log: `evaluation/results/experimental/postfix/run_log_full_batch.txt`.
- **Documents:** five proposals tested as PDFs (two were DOCX files converted to PDF; see `PILOT_README.md` section 4 for why).
- **Same-purpose reports:** `PILOT_README.md` (pilot results) and `CAP_COMPARISON.md` (cap test) contain pilot cost figures but are not full-batch costing reports. This report is new and separate from the business report.

## 2. Costing methodology

**Pricing (USD per 1,000,000 tokens):** input **$2.00**, output **$10.00**. Source: supplied and verified by the project owner and stored in `.env.eval` (`BEDROCK_INPUT_PRICE_PER_MILLION`, `BEDROCK_OUTPUT_PRICE_PER_MILLION`). The repository does not record a pricing-page URL or the verification date, so the pricing date is **not recorded** and I could not independently confirm the figures.

**Exchange rate:** ₱**64** per USD, a fixed rate chosen by the project owner (`USD_TO_PHP`). Source and date are **not recorded**. Peso figures are USD x 64 and would change with the actual rate.

**Formulas**
- `cost_USD = input_tokens / 1,000,000 x 2.00 + output_tokens / 1,000,000 x 10.00` (input and output costed separately, per Bedrock invocation, using the token counts returned by Bedrock).
- `cost_PHP = cost_USD x 64`.
- Operation cost = sum of its Bedrock invocations. Cost per persona = cost of one persona invocation. Campaign cost (section 8) = sum of its operations.
- Latency = wall-clock seconds measured around each call; an operation's latency is the sum of its invocations (the persona run is 3 sequential calls).

**Definitions**
- **User prompt:** a question or request a user types to the assistant (including "Summarize This Campaign").
- **Application operation:** one PAM feature execution: a summary, an assistant answer, a field extraction, or one full persona-naming run.
- **Bedrock invocation:** one actual model call. Almost every operation is 1 invocation; a persona run is 3 (one per persona). Uploads trigger the extraction without a user prompt.
- **Attempt:** one try of an operation. A failed attempt that is retried creates a new attempt; the failed one is kept.

**Aggregation**
- Per-operation statistics (average, minimum, maximum, standard deviation) are over **final attempts** of operations that returned token usage. Standard deviation is the sample standard deviation across operations (cases x repetitions), not a confidence interval.
- "Incurred" totals sum **every attempt**, so failed attempts and their cost are included.
- Operations that errored before any model response (no usage) have no tokens and no cost; they are counted as failed but excluded from token and cost averages.
- Sample sizes are small (3 repetitions; 5 proposals; the persona category has 1 case). Averages are indicative, not statistically precise.

## 3. Execution summary

- Operations: 132 (150 attempts). Bedrock invocations in final attempts: 138; all attempts: 156, of which 18 were rejected before reaching the model (expired credentials, no usage, no cost) and 138 were answered by the model.
- Tokens (all attempts): 997,785 input, 114,709 output, 1,112,494 total.
- **Incurred cost of this full batch (all attempts, including the pilot repetition): $3.143 (₱201.13).** Cost of failed attempts: $0.0000 (₱0.00).
- Other evaluation spend, for audit: baseline pilot `main` $1.359 (₱86.98); script-only 3,000 cap `cap3000` $1.371 (₱87.73); stop-reason diagnostic (2 calls, from printed usage) $0.068 (₱4.33). Program total: $5.940 (₱380.17).

## 4. Per prompt type / application operation

### 4.1 Counts and outcomes

| Category | Cases | Reps | Ops | Invocations / op | OK | Failed | Truncated | Retried ops | Failed attempts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Campaign summary, proposal attached | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Campaign summary, form values only (baseline case) | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Persona naming, full run (3 personas) | 1 | 3 | 3 | 3.00 | 3 | 0 | 0 | 0 | 0 |
| Upload field extraction (Bedrock) | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Assistant, low context, short prompt (no proposal) | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Assistant, medium context, medium prompt (no proposal) | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Assistant, high context, medium prompt (SMS + email draft) | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Assistant, high context, long prompt | 5 | 3 | 15 | 1.00 | 15 | 0 | 0 | 0 | 0 |
| Assistant, high context, proposal-specific prompts | 7 | 3 | 21 | 1.00 | 21 | 0 | 0 | 5 | 15 |
| Assistant, suggested question "Draft An SMS For This Offer" (FORWARD only) | 1 | 3 | 3 | 1.00 | 3 | 0 | 0 | 1 | 3 |

### 4.2 Tokens per operation (average / minimum / maximum / standard deviation)

| Category | Input avg | Input min-max | Input SD | Output avg | Output min-max | Output SD | Total avg | Total min-max | Total SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Campaign summary, proposal attached | 11,695 | 9,025-17,408 | 3,140 | 830 | 639-1,025 | 109 | 12,525 | 9,786-18,391 | 3,179 |
| Campaign summary, form values only (baseline case) | 468 | 440-510 | 24 | 458 | 350-607 | 81 | 926 | 790-1,117 | 96 |
| Persona naming, full run (3 personas) | 1,275 | 1,275-1,275 | 0 | 930 | 907-955 | 24 | 2,205 | 2,182-2,230 | 24 |
| Upload field extraction (Bedrock) | 10,862 | 8,842-14,021 | 1,945 | 915 | 657-1,193 | 195 | 11,777 | 9,499-15,149 | 2,023 |
| Assistant, low context, short prompt (no proposal) | 473 | 445-515 | 24 | 420 | 335-578 | 65 | 893 | 798-1,093 | 77 |
| Assistant, medium context, medium prompt (no proposal) | 663 | 628-695 | 26 | 656 | 459-890 | 111 | 1,319 | 1,154-1,576 | 116 |
| Assistant, high context, medium prompt (SMS + email draft) | 11,968 | 9,224-17,581 | 3,090 | 1,851 | 1,599-2,123 | 174 | 13,819 | 10,936-19,662 | 3,110 |
| Assistant, high context, long prompt | 12,032 | 9,288-17,645 | 3,090 | 1,216 | 976-1,458 | 141 | 13,248 | 10,395-18,689 | 3,006 |
| Assistant, high context, proposal-specific prompts | 11,382 | 9,232-17,579 | 2,753 | 629 | 180-1,290 | 342 | 12,011 | 9,504-18,836 | 2,925 |
| Assistant, suggested question "Draft An SMS For This Offer" (FORWARD only) | 10,839 | 10,839-10,839 | 0 | 1,174 | 1,054-1,330 | 141 | 12,013 | 11,893-12,169 | 141 |

### 4.3 Cost and latency per operation

| Category | Avg cost USD | Avg cost PHP | Min-max USD | SD USD | Avg latency (s) | Max latency (s) | Incurred total USD (all attempts) | Cost of failed attempts USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Campaign summary, proposal attached | 0.0317 | 2.03 | 0.0257-0.0446 | 0.0067 | 5.8 | 6.9 | 0.4754 | 0.0000 |
| Campaign summary, form values only (baseline case) | 0.0055 | 0.35 | 0.0044-0.0071 | 0.0008 | 3.5 | 4.3 | 0.0827 | 0.0000 |
| Persona naming, full run (3 personas) | 0.0118 | 0.76 | 0.0116-0.0121 | 0.0002 | 9.2 | 9.4 | 0.0355 | 0.0000 |
| Upload field extraction (Bedrock) | 0.0309 | 1.98 | 0.0243-0.0393 | 0.0049 | 5.8 | 7.6 | 0.4631 | 0.0000 |
| Assistant, low context, short prompt (no proposal) | 0.0051 | 0.33 | 0.0043-0.0068 | 0.0007 | 3.2 | 4.0 | 0.0772 | 0.0000 |
| Assistant, medium context, medium prompt (no proposal) | 0.0079 | 0.50 | 0.0060-0.0103 | 0.0011 | 5.1 | 6.9 | 0.1183 | 0.0000 |
| Assistant, high context, medium prompt (SMS + email draft) | 0.0424 | 2.72 | 0.0356-0.0560 | 0.0066 | 13.1 | 16.0 | 0.6367 | 0.0000 |
| Assistant, high context, long prompt | 0.0362 | 2.32 | 0.0296-0.0457 | 0.0054 | 9.0 | 11.4 | 0.5434 | 0.0000 |
| Assistant, high context, proposal-specific prompts | 0.0291 | 1.86 | 0.0212-0.0477 | 0.0077 | 4.6 | 8.6 | 0.6101 | 0.0000 |
| Assistant, suggested question "Draft An SMS For This Offer" (FORWARD only) | 0.0334 | 2.14 | 0.0322-0.0350 | 0.0014 | 9.1 | 10.1 | 0.1003 | 0.0000 |

Notes: "Failed" counts operations whose final attempt failed. "Truncated" counts final attempts that stopped at `max_tokens`. "Retried ops" counts operations whose final attempt is a second or later attempt. Averages exclude operations with no usage (credential errors), which is why the averages for categories with such operations rest on fewer operations than listed.

## 5. Persona generation

A persona run names 3 personas with one Bedrock request each. Clustering itself uses no model and has no inference cost.

| Measure | Value |
|---|---:|
| Full persona-generation run (3 personas): average cost | $0.0118 (₱0.76) |
| Full run: average tokens (input + output) | 2,205 |
| Runs measured | 3 |
| Per persona: invocations measured | 9 |
| Per persona: average input / output / total tokens | 425 / 310 / 735 |
| Per persona: average cost | $0.00395 (₱0.25) |
| Per persona: cost range | $0.00381 to $0.00414 |

Per-persona figures are **measured**, not estimated: each persona is its own request, so no apportioning of a shared call was needed. They describe the "short persona" case (name, description, difference, 2-3 actions) on the synthetic dataset's 3-persona default; a run with more personas would scale roughly linearly (estimate).

## 6. Failed, truncated and retried operations

- Operations whose final attempt failed: **0**. Operations retried: **6**. Failed attempts in total: 18. Truncated (`max_tokens`) final attempts: 0; stop reasons recorded in the experimental run: {'end_turn': 138, None: 18}.
- Cost of unsuccessful attempts: $0.0000 (₱0.00).
- Failure cause: every failed attempt is an immediate `error` with no model response. A separate no-cost probe afterwards returned `ExpiredTokenException`: the AWS session token in `.env.eval` expired during repetition 3. These calls returned no usage and incurred no cost. All failed attempts are preserved in `raw.jsonl`.

| Case | Rep | Attempt | Reason | Cost | Outcome |
|---|---:|---:|---|---:|---|
| assistant_specific:better_together:T1 | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:better_together:T1 | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:better_together:T1 | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:bonds:B1 | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:bonds:B1 | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:bonds:B1 | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:forex:X1 | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:forex:X1 | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:forex:X1 | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H2 | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H2 | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H2 | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H3 | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H3 | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_specific:horizon:H3 | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_suggested_draft:forward | 3 | 1 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_suggested_draft:forward | 3 | 2 | error | $0.0000 (₱0.00) | succeeded on retry |
| assistant_suggested_draft:forward | 3 | 3 | error | $0.0000 (₱0.00) | succeeded on retry |

## 7. Per campaign proposal

### 7.1 Documents

| Campaign | Document tested | Original format | Characters | Est. tokens (chars/4) | Actual input tokens (summary, proposal attached) |
|---|---|---|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | Project FORWARD_MM OF Remitters.pdf | PDF | 20,062 | 5,016 | 10,265 |
| Horizon Reactive Deepening | Horizon Reactive Deepening Campaign Proposal.pdf | PDF | 19,907 | 4,977 | 9,682 |
| Forex Solutions Campaign Refresh | 2026 Forex Solutions CRM Campaign Proposal ao 080326.pdf | PDF | 23,696 | 5,924 | 12,096 |
| 2026 Bonds Beyond Borders Manila | 2026 CRM Targeted Campaign Proposal_Bonds Beyond Borders Manila 052026.pdf | DOCX (converted to PDF) | 17,398 | 4,350 | 9,025 |
| 2026 Better Together Bundles | (1) Campaign Proposal 2026_Better Together Bundles.pdf | DOCX (converted to PDF) | 36,471 | 9,118 | 17,408 |

Estimated tokens use the app's characters-divided-by-4 rule; actual input tokens (which include the prompt, form values and tags) are about 1.9 times higher.

### 7.2 Prompts, operations and invocations

| Campaign | User prompts | Operations (excl. persona) | Invocations attempted | Attempts incl. retries | Failed attempts |
|---|---:|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 24 | 27 | 27 | 30 | 3 |
| Horizon Reactive Deepening | 27 | 30 | 30 | 36 | 6 |
| Forex Solutions Campaign Refresh | 21 | 24 | 24 | 27 | 3 |
| 2026 Bonds Beyond Borders Manila | 21 | 24 | 24 | 27 | 3 |
| 2026 Better Together Bundles | 21 | 24 | 24 | 27 | 3 |

User prompts and operations are counted over all repetitions. The persona run is not proposal-specific and is reported in section 5.

### 7.3 Assistant prompts by category and context level (per repetition)

| Campaign | summary_with_doc | summary_form_only | assistant_low_short | assistant_medium_medium | assistant_high_medium | assistant_high_long | assistant_specific | assistant_suggested_draft |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Horizon Reactive Deepening | 1 | 1 | 1 | 1 | 1 | 1 | 3 | 0 |
| Forex Solutions Campaign Refresh | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| 2026 Bonds Beyond Borders Manila | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| 2026 Better Together Bundles | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |

Context levels: `low` = form values only; `medium` = form + campaign context + known gaps (no document); `doc` = form + proposal; `high` = form + context + proposal (+ a PAM run summary for FORWARD). Summary-with-proposal is level `doc`; summary-form-only and low-short are level `low`.

### 7.4 Total and average tokens and cost across repetitions (all attempts, incurred)

| Campaign | Input tokens (total) | Output tokens (total) | Total tokens (total) | Avg total tokens per repetition | Total cost USD | Total cost PHP | Avg cost per repetition USD | Avg cost per repetition PHP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 196,293 | 24,637 | 220,930 | 73,643 | 0.6390 | 40.89 | 0.2130 | 13.63 |
| Horizon Reactive Deepening | 211,245 | 25,184 | 236,429 | 78,810 | 0.6743 | 43.16 | 0.2248 | 14.39 |
| Forex Solutions Campaign Refresh | 187,173 | 19,919 | 207,092 | 69,031 | 0.5735 | 36.71 | 0.1912 | 12.24 |
| 2026 Bonds Beyond Borders Manila | 141,414 | 18,958 | 160,372 | 53,457 | 0.4724 | 30.23 | 0.1575 | 10.08 |
| 2026 Better Together Bundles | 257,835 | 23,221 | 281,056 | 93,685 | 0.7479 | 47.86 | 0.2493 | 15.95 |

These totals cover every benchmark operation for the proposal (including the form-only and no-document cases, which are mutually exclusive alternatives in real use), so they are **not** campaign costs; the campaign estimate is in section 8.

### 7.5 Campaign summary with versus without the attached proposal

The two cases are alternatives, never summed. Both use the same form values. "Facts" is the share of known proposal facts present in the answer (deterministic check).

| Campaign | Input tokens with / without | Output tokens with / without | Cost USD with / without | Cost multiple | Latency s with / without | Facts with / without |
|---|---:|---:|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 10,265 / 474 | 751 / 470 | 0.0280 / 0.0056 | 5.0x | 5.8 / 3.7 | 100% / 40% |
| Horizon Reactive Deepening | 9,682 / 458 | 831 / 456 | 0.0277 / 0.0055 | 5.1x | 5.7 / 3.6 | 94% / 42% |
| Forex Solutions Campaign Refresh | 12,096 / 458 | 878 / 402 | 0.0330 / 0.0049 | 6.7x | 6.0 / 3.1 | 79% / 27% |
| 2026 Bonds Beyond Borders Manila | 9,025 / 440 | 803 / 428 | 0.0261 / 0.0052 | 5.1x | 5.3 / 3.2 | 100% / 20% |
| 2026 Better Together Bundles | 17,408 / 510 | 888 / 532 | 0.0437 / 0.0063 | 6.9x | 6.2 / 3.8 | 81% / 11% |

Without the proposal, the facts found come from the form values; no proposal-only figure appeared in any form-only answer.

## 8. Campaign-level estimate (derived from measured operations)

**Benchmark campaign bundle.** The benchmark never ran a complete campaign-planning session end to end, so a "campaign" is assembled from measured operations for one proposal in one repetition: 1 field extraction + 1 campaign summary with the proposal attached + the proposal-attached assistant prompts (1 SMS+email draft, 1 long prompt, plus 1 proposal-specific prompt; Horizon has 3) + 1 full persona-generation run. This costs each campaign one persona run (the persona step is not proposal-specific and was measured once per repetition). Mutually exclusive alternatives (the form-only summary, the no-proposal assistant cases) and the FORWARD-only suggested-question case are excluded, and repetitions are not treated as separate campaigns: each proposal's campaign figure is the mean of its repetitions. Only complete bundles (every operation successful) are used: **15 of 15**.

| Campaign | Complete reps | User prompts | Operations | Invocations | Avg input tokens | Avg output tokens | Avg total tokens | Avg cost USD | Avg cost PHP | Min-max cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Project FORWARD (Mid-Market OF Remitters) | 3 | 4 | 6 | 8 | 54,249 | 6,390 | 60,639 | 0.1724 | 11.03 | 0.1695-0.1757 |
| Horizon Reactive Deepening | 3 | 6 | 8 | 10 | 70,074 | 7,926 | 78,000 | 0.2194 | 14.04 | 0.2160-0.2254 |
| Forex Solutions Campaign Refresh | 3 | 4 | 6 | 8 | 62,117 | 6,091 | 68,208 | 0.1851 | 11.85 | 0.1841-0.1857 |
| 2026 Bonds Beyond Borders Manila | 3 | 4 | 6 | 8 | 46,886 | 5,844 | 52,730 | 0.1522 | 9.74 | 0.1519-0.1528 |
| 2026 Better Together Bundles | 3 | 4 | 6 | 8 | 85,509 | 6,861 | 92,370 | 0.2396 | 15.34 | 0.2366-0.2445 |

Overall average across the five campaigns (equal weight): **4.4 user prompts, 70,390 tokens, $0.1938 (₱12.40)**. User prompts = summary + assistant prompts; extraction and persona runs are application operations, not prompts. "User prompts" in this bundle is a benchmark test design, **not** evidence of how many prompts a CRM manager sends.

### 8.1 Unit costs used for usage scenarios (successful operations only, mean of the five proposals)

| Operation | Avg cost USD | Avg cost PHP | Avg total tokens | Range across proposals (USD) |
|---|---:|---:|---:|---:|
| Field extraction (per upload) | 0.0309 | 1.98 | 11,777 | 0.0244-0.0386 |
| Campaign summary, proposal attached | 0.0317 | 2.03 | 12,525 | 0.0261-0.0437 |
| Assistant prompt, proposal attached (mean of draft, long and specific prompts) | 0.0357 | 2.29 | 13,163 | 0.0299-0.0485 |
| Persona-generation run (3 invocations) | 0.0118 | 0.76 | 2,205 | single measurement series |

Scenario definitions and projections are in `BUSINESS_COST_REPORT.md` (section 4) and `results/experimental/costing/scenario_projection.csv`. The scenario counts are illustrative assumptions, not observed CRM behaviour.

## 9. Baseline versus experimental configuration

Baseline = submitted version (caps 1,500 / 1,200), pilot only: 1 repetition (`results/main`). Script-only = same code with the cap raised to 3,000 inside the script, 1 repetition (`results/cap3000`). Experimental = this report's configuration, 3 repetitions. Counts are not like-for-like (1 versus 3 repetitions); success is therefore shown as ok/operations, and average cost is per operation with usage.

| Category | Baseline ok/ops | Baseline avg USD | Script-only ok/ops | Script-only avg USD | Experimental ok/ops | Experimental avg USD |
|---|---:|---:|---:|---:|---:|---:|
| Campaign summary, proposal attached | 5/5 | 0.0311 | 5/5 | 0.0317 | 15/15 | 0.0317 |
| Campaign summary, form values only (baseline case) | 5/5 | 0.0057 | 5/5 | 0.0054 | 15/15 | 0.0055 |
| Persona naming, full run (3 personas) | 1/1 | 0.0120 | 0/1 | 0.0115 | 3/3 | 0.0118 |
| Upload field extraction (Bedrock) | 2/5 | 0.0331 | 5/5 | 0.0327 | 15/15 | 0.0309 |
| Assistant, low context, short prompt (no proposal) | 5/5 | 0.0053 | 5/5 | 0.0054 | 15/15 | 0.0051 |
| Assistant, medium context, medium prompt (no proposal) | 5/5 | 0.0078 | 5/5 | 0.0073 | 15/15 | 0.0079 |
| Assistant, high context, medium prompt (SMS + email draft) | 0/5 | 0.0389 | 5/5 | 0.0412 | 15/15 | 0.0424 |
| Assistant, high context, long prompt | 5/5 | 0.0354 | 5/5 | 0.0369 | 15/15 | 0.0362 |
| Assistant, high context, proposal-specific prompts | 7/7 | 0.0292 | 7/7 | 0.0285 | 21/21 | 0.0291 |
| Assistant, suggested question "Draft An SMS For This Offer" (FORWARD only) | 3/3 | 0.0338 | 3/3 | 0.0343 | 3/3 | 0.0334 |

- The baseline pilot also included 4 DOCX reference operations (original DOCX files as the app reads them). They cost $0.255 (₱16.31) for 4 operations against $0.137 (₱8.74) for their PDF equivalents; details in `PILOT_README.md` section 4. Not repeated in the experimental run.
- Pilot-level findings (baseline completed 35 of 43 standard operations in its 1-repetition pilot; the experimental pilot repetition completed 43 of 43) are in `PILOT_README.md` section 10. The failed baseline calls still cost money: the baseline pilot's failed attempts cost $0.302 (₱19.33).
- Per-operation costs are about equal across configurations; the experimental configuration differs mainly in how many operations succeed.

## 10. Assumptions, limitations and exclusions

- **Inference only.** No hosting, storage, data integration, monitoring, maintenance, support or development cost is included.
- **Measured versus estimated.** Operation tokens, latency and cost are measured. Campaign bundles and usage scenarios are estimates composed from them. Prompt counts in the benchmark are test design, not CRM behaviour.
- **Prices and exchange rate** are owner-supplied constants; their sources and dates are not recorded. AWS price changes or a different exchange rate change every figure proportionally.
- **Small samples.** 3 repetitions, 5 proposals, 1 persona case. Standard deviations are across 3 to 21 operations; no significance claims are made.
- **Different prompt mixes per proposal.** Horizon has 3 proposal-specific prompts, the others 1, so proposal totals are not like-for-like.
- **Experimental configuration only.** Full-batch figures do not describe the submitted version. The 3,000-token cap lets individual calls cost up to about $0.03 more output than the 1,500 cap would allow; observed averages are unchanged.
- **Synthetic data.** Persona runs use the project's synthetic customers; costs would scale with persona count and prompt size in real data.
- **Single model and region.** Costs apply to `global.anthropic.claude-sonnet-5-5` only; the benchmark ran outside Streamlit (no session token cap or question limit).
- **Failures.** 0 operation(s) failed on the final attempt; none are silently excluded, and the cost of every failed attempt is counted in the incurred totals.
- **Token estimates in the app** (characters / 4) understate real input tokens by roughly 1.9 times for these documents; this report uses Bedrock's counts.
- **Document handling.** Costs are for PDFs. The app's DOCX reader multiplies input tokens about 2.5 to 4.6 times (baseline pilot), so uploading the original DOCX files would cost more; not re-measured in the full batch.

## 11. Files for verification and reproduction

| File | Content |
|---|---|
| `evaluation/results/experimental/postfix/raw.jsonl` | every attempt: tokens, latency, stop reason, outputs, quality checks |
| `evaluation/results/experimental/postfix/results_detailed.csv`, `results_summary.csv` | per-invocation and per-category CSVs from the benchmark script |
| `evaluation/results/experimental/postfix/proposal_inventory.csv` | document sizes |
| `evaluation/results/experimental/postfix_pilot_snapshot/` | the earlier pilot-only copy (repetition 1) |
| `evaluation/results/experimental/costing/*.csv` | tables behind this report |
| `evaluation/results/main/`, `evaluation/results/cap3000/` | baseline pilot results (not modified) |
| `evaluation/results/experimental/RUN_INFO.md`, `experimental_changes.patch` | configuration record and exact code differences |

Reproduce all figures in this report (no Bedrock calls): `.venv/bin/python evaluation/build_cost_reports.py`.
Re-run the benchmark (paid): see `evaluation/README.md`.
