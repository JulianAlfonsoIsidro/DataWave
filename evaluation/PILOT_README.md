# PAM Bedrock benchmark: pilot run report

**Test assumptions (apply to the benchmark and to the app's intended use):** (1) the assistant output cap is 3,000 tokens (the pilot ran both 1,500, the app's current value, and 3,000; see `CAP_COMPARISON.md`); (2) a reply that stops at `max_tokens` counts as a failed operation, even if some text came back; (3) users always upload the campaign proposal, so results with the document attached are the primary figures and the form-values-only and no-document cases are kept only as baselines. The benchmark applies these inside the script only; the app's code is unchanged. The pilot data predates stop-reason capture, so assumption 2 is checked there by output size: no successful pilot operation reached its cap.

Pilot of the automated Bedrock benchmark for the Promo Audience Manager (PAM) prototype. Hackathon validation only. Run on 2026-11-27 (about 5 minutes), model/profile `global.anthropic.claude-sonnet-5-5`.
All token counts are the ones Bedrock returned, not estimates. Prices: $2.00 per 1M input tokens and $10.00 per 1M output tokens (your verified figures); ₱64 per USD (your rate).
No production code, prompts, UI or `.env` were changed.

## 1. What was run

- **49 Bedrock invocations** in 47 operations (43 standard plus 4 DOCX reference), one repetition each. A persona operation is 3 invocations. 39 operations succeeded and 8 failed (see section 6).
- **Total pilot spend: $1.26 (₱80.5)**, 432,914 input and 39,199 output tokens. Failed operations are included: they cost $0.30.
- **Five real proposals**, tested as PDFs (the two DOCX files were converted to PDF; see section 4): FORWARD, Horizon, Forex Solutions, Bonds Beyond Borders, Better Together Bundles.
- **Test categories:** summary with proposal, summary from form values only, assistant (low, medium and high context; short, medium and long prompts), proposal-specific assistant prompts (Horizon is the main baseline with 3; the others 1 each), persona naming (3 personas, one request each), Bedrock field extraction.
- **Deterministic checks only.** No LLM judge. Outputs are saved for manual review in `evaluation/results/main/responses_for_review.md`.

## 2. Results by category

Costs are per operation. Tokens are averages per operation. "Total range" is the minimum to maximum total tokens.

| Category | Success | Avg input | Avg output | Total range | Avg latency (s) | Cost (USD) | Cost (PHP) | Quality check |
|---|---:|---:|---:|---|---:|---:|---:|---|
| summary_with_doc | 5/5 | 11,695 | 766 | 9,657–18,288 | 6.1 | $0.0311 | ₱1.99 | known facts kept 94% |
| summary_form_only | 5/5 | 468 | 477 | 797–1,095 | 3.9 | $0.0057 | ₱0.36 | no invented figures; no proposal-only figures leaked |
| persona | 1/1 | 1,275 | 943 | 2,218–2,218 | 9.9 | $0.0120 | ₱0.77 | valid personas 100% |
| extraction | 2/5 | 10,766 | 1,156 | 9,871–15,125 | 7.7 | $0.0331 | ₱2.12 | field accuracy 58% |
| assistant_low_short | 5/5 | 473 | 440 | 868–969 | 3.5 | $0.0053 | ₱0.34 | no invented figures; no proposal-only figures leaked |
| assistant_medium_medium | 5/5 | 663 | 645 | 1,209–1,398 | 5.3 | $0.0078 | ₱0.50 | no invented figures; no proposal-only figures leaked |
| assistant_high_medium | 0/5 | 11,968 | 1,500 | 10,724–19,081 | 11.4 | $0.0389 | ₱2.49 | all failed |
| assistant_high_long | 5/5 | 12,032 | 1,131 | 10,487–18,626 | 8.8 | $0.0354 | ₱2.27 | known facts kept 71% |
| assistant_specific | 7/7 | 11,382 | 646 | 9,548–18,604 | 4.9 | $0.0292 | ₱1.87 | expected facts present 100% |
| docx_ref_summary | 2/2 | 45,062 | 786 | 41,935–49,760 | 6.5 | $0.0980 | ₱6.27 | known facts kept 73% |
| docx_ref_extraction | 2/2 | 10,758 | 792 | 11,273–11,825 | 5.6 | $0.0294 | ₱1.88 | field accuracy 17% |

Cost per call and cost per operation match for every category except persona naming, where 1 operation = 3 calls (about 425 input and 314 output tokens per persona, measured because each persona is its own request).

### Projected cost

Averages from the pilot, one repetition, so treat them as indicative.

| Category | 100 operations | 1,000 operations |
|---|---:|---:|
| summary_with_doc | $3.11 (₱199) | $31.10 (₱1,990) |
| summary_form_only | $0.57 (₱36) | $5.70 (₱365) |
| persona | $1.20 (₱77) | $12.00 (₱768) |
| extraction | $3.31 (₱212) | $33.10 (₱2,118) |
| assistant_low_short | $0.53 (₱34) | $5.30 (₱339) |
| assistant_medium_medium | $0.78 (₱50) | $7.80 (₱499) |
| assistant_high_medium | $3.89 (₱249) | $38.90 (₱2,490) |
| assistant_high_long | $3.54 (₱227) | $35.40 (₱2,266) |
| assistant_specific | $2.92 (₱187) | $29.20 (₱1,869) |

## 3. With versus without the proposal

Same form values in both. Doc-facts = share of known proposal facts present in the answer. Without the document, the facts found come from the form itself (segments, channels, product); no proposal-only figure (lead counts, targets) appeared in any form-only answer.

| Proposal | Input with doc | Input form only | Multiple | Cost with doc | Cost form only | Facts with doc | Facts form only |
|---|---:|---:|---:|---:|---:|---:|---:|
| forward | 10,265 | 474 | 21.7× | $0.0274 | $0.0060 | 100% | 40% |
| horizon | 9,682 | 458 | 21.1× | $0.0275 | $0.0043 | 100% | 42% |
| forex | 12,096 | 458 | 26.4× | $0.0324 | $0.0066 | 82% | 27% |
| bonds | 9,025 | 440 | 20.5× | $0.0244 | $0.0048 | 100% | 20% |
| better_together | 17,408 | 510 | 34.1× | $0.0436 | $0.0069 | 89% | 11% |

## 4. DOCX versus PDF

The app's DOCX reader repeats merged-cell text and drops checkboxes (ticked segments, channels, objectives) and form-control text (for Better Together, the campaign name and dates). Word was used to convert both DOCX files to PDF (originals untouched). The PDFs keep every checkbox with the right state.

Local comparison (no Bedrock):

| Proposal | Format | Characters | Est. tokens | Unique lines | Ticked / unticked | Known facts found |
|---|---|---:|---:|---:|---:|---:|
| better_together | docx | 115,979 | 28,995 | 23% | 0 / 6 | 13 of 24 |
| better_together | pdf | 36,471 | 9,118 | 79% | 60 / 117 | 23 of 24 |
| bonds | docx | 93,139 | 23,285 | 20% | 0 / 0 | 16 of 19 |
| bonds | pdf | 17,398 | 4,350 | 82% | 38 / 119 | 19 of 19 |

Bedrock comparison (pilot, 1 repetition; DOCX is the file as the app reads it):

| Proposal | Task | Variant | OK | Input tokens | Cost | Facts / accuracy / reason |
|---|---|---|---|---:|---:|---|
| bonds | summary | docx as app reads it | True | 41,289 | $0.0890 | 90% |
| bonds | summary | pdf workaround | True | 9,025 | $0.0244 | 100% |
| bonds | extraction | docx as app reads it | True | 10,763 | $0.0266 | 33% |
| bonds | extraction | pdf workaround | True | 8,746 | $0.0287 | 67% |
| better_together | summary | docx as app reads it | True | 48,834 | $0.1069 | 56% |
| better_together | summary | pdf workaround | True | 17,408 | $0.0436 | 89% |
| better_together | extraction | docx as app reads it | True | 10,752 | $0.0322 | 0% |
| better_together | extraction | pdf workaround | False | 13,925 | $0.0398 | bad_json |

Impact: the DOCX summaries cost 2.5 to 3.7 times more than the PDF summaries and kept fewer facts (Bonds 90% against 100%; Better Together 56% against 89%). DOCX extraction found none of Better Together's fields. The Better Together PDF extraction failed for the cap reason in section 6, so that pair is incomplete.

## 5. Quality notes

- **Accuracy and groundedness:** no unsupported figures in any successful answer (checked against the payload). No proposal-only figure appeared when the proposal was not attached.
- **Gaps detected:** the assistant flagged Bonds' "promo marked Yes but no mechanics" and Better Together's "July 2027 until December 2026" date error.
- **Long prompts:** the app's 150-word answer cap limits how many facts a long prompt can cover (facts kept 71%). Treated as a design limit.
- **Personas:** 3 of 3 valid, unique names, numbers match the data. The data is synthetic, so this shows consistency and groundedness, not real-world accuracy.
- **Consistency:** needs 3 repetitions; not measurable from the pilot.

## 6. Defects and limitations

| # | Severity | Finding | Likely cause | Proposed fix (needs approval) |
|---|---|---|---|---|
| 1 | Critical | 3 of 5 field extractions returned broken JSON. The app then silently falls back to its Demo extractor. | Output reached the 1,200-token cap in all 3 failures. Some of the model's output tokens are not visible text, so the cap leaves too little room. Not yet confirmed with the stop reason. | Raise the extractor cap or switch off reasoning. |
| 2 | Critical (scope narrowed) | The benchmark's draft prompt ("Draft an SMS and an email for this offer, and mention the key eligibility criteria") failed on all 5 proposals (output stopped at the 1,500-token cap, no text). | Same cap. This prompt asks for two messages plus criteria. The app's own suggested question asks for one SMS and worked in the app log (see section 7). | Raise the assistant cap, then retest with the suggested question. |
| 3 | Moderate | Extraction drops segments written as "Affluent – Gold" or "Core Mass Market". Horizon returned only Mid-Market; Bonds returned none. | The validator accepts only names like "Affluent-Gold"; reproduced locally. | List allowed names in the prompt and accept common spellings. |
| 4 | Moderate | DOCX reader duplicates text and drops checkboxes. | Reader uses plain paragraph text. | PDF workaround now; fix the reader later. |
| 5 | Low | The wait-time token estimate is about 1.75× too low. | Characters divided by 4. | Use about 2.3 characters per token. |
| 6 | Low | 150-word answer cap limits long answers. | Design choice. | None. |

Evaluation-script errors: one test prompt (Bonds) routed to the app's local reply with no model call. Fixed before the run. None found since.

Deviations from real app use: the script runs outside Streamlit (no session token cap or question limit); FORWARD's high-context cases also include a PAM run summary built from the synthetic customers (687 Mid-Market clients), which does not match the proposal's lead counts; no minimum ADB is sent because no proposal states one (the run itself uses 0.0); document context is attached as the app does after an upload, using expected form values for the tags.

## 7. Why the app's "Draft An SMS For This Offer" worked but the benchmark's draft prompt failed

- The benchmark did not use the suggested question. It used a heavier prompt (SMS and email and eligibility criteria), so the comparison was not like for like.
- The app log (`scratch/assistant_log.jsonl`) has a successful Bedrock answer to the exact suggested question on FORWARD (12 Nov, 150 words).
- Follow-up tests confirmed it: the suggested question passed 3 of 3 times at the app's 1,500 cap (1,120 to 1,328 output tokens). The heavier prompt hit the cap (stop reason `max_tokens`): the model reasons first, those tokens count against the cap, and the amount varies per run.
- Details and the 1,500 versus 3,000 comparison: `evaluation/CAP_COMPARISON.md`.

## 8. Files

All in `evaluation/results/main/` (git-ignored): `results_detailed.csv` (one row per call, including failures), `results_summary.csv`, `comparison_with_vs_without_proposal.csv`, `docx_vs_pdf_local.csv`, `docx_vs_pdf_bedrock.csv`, `proposal_inventory.csv`, `responses_for_review.md`, `presentation_summary.md`, `raw.jsonl`.
Script: `evaluation/run_benchmark.py`. Expected facts and prompts: `evaluation/expected_facts.json`. Commands: `evaluation/README.md`.

## 9. Next steps

1. Done after this pilot: stop-reason diagnostic, suggested-question test and the 3,000-token cap test (`evaluation/CAP_COMPARISON.md`). The 3,000 cap lifted successful operations from 39 of 47 to 46 of 47 for 1% more spend.
2. Full batch: 3 repetitions, about 90 more calls on the app's current caps (pilot results reused), with the suggested-question case now added (+2 calls). A second full set at 3,000 is optional.


## 10. Post-fix experiment (branch `part-12-experiment`)

**Baseline versus experimental.** Everything above is the baseline: the app as committed (`part-11-final-changes`, 1,500 and 1,200 token caps), plus the `cap3000` run where the cap was raised inside the script only. This section is the experimental run: the fixes applied as real code changes in a separate git worktree. The original application source was not modified. Full record (branch, commits, caps, model, patch): `evaluation/results/experimental/RUN_INFO.md`.

### What was changed (experimental branch only)

| File | Change |
|---|---|
| `src/ai/assistant.py` | output cap 1,500 to 3,000 |
| `src/ai/extractor.py` | output cap 1,200 to 3,000; prompt lists the exact segment names; common spellings ("Affluent – Gold", "Core Mass Market", "Mass Market", with or without "(Segment Code 02)") map to PAM's names; Top Personal, Next and Private Wealth are still dropped |
| `src/ai/bedrock.py` | a `max_tokens` stop returns the Demo fallback with reason `truncated`, token usage kept; new `stop_reason` field |
| `src/webapp_core/ai_usage.py` | plain wording for `truncated` |
| two test files | 20 new tests; persona cap checked to stay at 800 |

### Results (one repetition, 43 standard operations, five proposals as PDFs)

| | App as committed (1,500) | Script-only 3,000 cap | Experimental code (3,000 + fixes) |
|---|---:|---:|---:|
| Successful operations | 35 of 43 | 42 of 43 | **43 of 43** |
| Cost of those operations | $1.003 | $1.014 | $1.018 |
| Cost per successful operation | $0.0287 | $0.0241 | $0.0237 |
| Extraction: runs that returned usable fields | 2 of 5 | 5 of 5 | 5 of 5 |
| Extraction: mean field accuracy (successful runs) | 58% | 60% | **93%** |
| Heavy draft prompt (SMS, email, criteria) | 0 of 5 | 5 of 5 | 5 of 5 |

- **Segment fix.** Extraction accuracy rose from 60% to 93% on the same five PDFs. Horizon, Forex and Bonds went to 100%; FORWARD stayed at 100%; Better Together reached 67% (its base product is not stated clearly, so `product_type` came back empty). Segments were now matched in all five.
- **Truncation handling.** All 46 post-fix calls ended normally (`end_turn`); none stopped at the cap. The new truncation check could therefore not be exercised against the live model, but unit tests cover it.
- **Cap headroom.** The longest reply was 2,123 tokens (a draft prompt), so 3,000 leaves about 41% headroom. The suggested question "Draft An SMS For This Offer" again passed (1,054 tokens) and again noted that SMS is not ticked for FORWARD.
- **Quality unchanged.** No unsupported figures and no proposal-only figures leaked in any answer. Known facts kept in summaries were 92% (90% in the script-only run); long-prompt facts 71% (75%), which is within normal variation for one repetition and the 150-word answer cap. Known issues (Bonds promo without mechanics, Better Together date error) were still caught.
- **Cost.** Total post-fix pilot spend was $1.051 (₱67.2) for 46 calls; the 43 comparable operations cost $1.018, about the same as the other two arms ($1.003 and $1.014). The old cap did not save money: it paid for failed calls.
- **Persona naming:** 3 of 3 valid this time (1 of 3 was rejected in the script-only run), so naming validity still varies between runs; this fix does not target it.

### Assumptions and limitations

- Assumptions from the top of this file apply (3,000 assistant cap, truncation counts as failure, users always upload the proposal).
- One repetition per arm. Differences of a few percent in fact rates or cost are noise; the success-rate and extraction gains are large and consistent with the cause found in the diagnostic.
- Extraction accuracy is scored on five fields against expected values I derived from the proposals; Better Together's `product_type` is treated as expected "Savings", which is a judgment call.
- The DOCX reference arm was not rerun; the DOCX findings in section 4 stand unchanged.
- The worktree used copies of the model outputs and proposals and a read-only link to `.env.eval`.

### Recommendation

The fixes work as intended and cost no more per successful operation. Next: (1) run the full 3-repetition batch on the experimental branch to confirm consistency (about 92 calls, roughly $2.2 or ₱140, with this pilot reused); (2) if it holds, review the patch (`experimental_changes.patch`) and merge `part-12-experiment` into your branch yourself. I have not merged or pushed anything, and the worktree is still in place.


## 11. Full batch and costing reports

The full 3-repetition batch was run on the experimental branch (`part-12-experiment` @ `0d85049`): 132 operations, all succeeded on their final attempt. Six operations in repetition 3 first failed because the AWS session token expired; they were rejected before reaching the model (no usage, no cost), kept in the raw results, and succeeded on retry after the credentials were refreshed.

- Technical costing report (audit detail): `evaluation/TECHNICAL_COST_REPORT.md`
- Business costing report (stakeholders): `evaluation/BUSINESS_COST_REPORT.md`
- Regenerate both from stored results, no Bedrock calls: `.venv/bin/python evaluation/build_cost_reports.py`
- Results: `evaluation/results/experimental/postfix/` (full batch) and `evaluation/results/experimental/costing/` (report tables)

These figures are for the experimental configuration. The submitted version was measured only in the pilot above.
