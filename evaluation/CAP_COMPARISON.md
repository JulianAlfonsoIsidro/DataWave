# Output cap test: 1,500 tokens (app today) versus 3,000 (temporary)

Same pilot (one repetition, five proposals, plus the 4 DOCX reference calls) run twice. The 3,000 cap was set inside the benchmark script only (`--output-cap 3000`, assistant, extraction and persona naming); app code is unchanged. Results: `evaluation/results/main/` (app caps: assistant 1,500, extraction 1,200, persona 800) and `evaluation/results/cap3000/`. Prices $2 input and $10 output per 1M tokens; ₱64 per USD. One repetition each, so differences are indicative, not statistical.

## Verdict

**Worth it.** Raising the cap to 3,000 took successful operations from 39 of 47 to 46 of 47 for 1% more spend (+$0.010 for the whole pilot, +₱0.64). Cost per successful operation fell from $0.0323 to $0.0276 because the 1,500 cap paid for 8 calls ($0.30) that produced nothing usable.

## Why the cap matters (diagnostic, 2 calls)

| Request | Cap | Stop reason | Reply blocks | Output tokens |
|---|---:|---|---|---:|
| FORWARD heavy draft prompt (SMS, email, criteria) | 1,500 | `max_tokens` | reasoning, then 197 characters of text | 1,500 |
| FORWARD field extraction | 1,200 | `end_turn` | reasoning, then text | 1,090 |

The model reasons before it answers, and those reasoning tokens count against the cap. On the draft prompt the reasoning used most of the 1,500 tokens, so the answer was cut after 197 characters. The same request returned empty text in the pilot, so the amount of reasoning varies between runs. The extraction passed this time at 1,090 tokens but failed 3 of 5 times in the pilot at exactly 1,200: it sits at the edge of the cap.

## Results

Tokens are Bedrock's counts, per category and per repetition 1.

| Category | OK at 1,500 | OK at 3,000 | Avg output 1,500 | Avg output 3,000 | Cost at 1,500 | Cost at 3,000 | Cost per success 1,500 | Cost per success 3,000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| summary_with_doc | 5/5 | 5/5 | 766 | 827 | $0.1553 | $0.1583 | $0.0311 | $0.0317 |
| summary_form_only | 5/5 | 5/5 | 477 | 442 | $0.0285 | $0.0268 | $0.0057 | $0.0054 |
| persona | 1/1 | 0/1 | 943 | 900 | $0.0120 | $0.0115 | $0.0120 | $n/a |
| extraction | 2/5 | 5/5 | 1156 | 1121 | $0.1654 | $0.1637 | $0.0827 | $0.0327 |
| assistant_low_short | 5/5 | 5/5 | 440 | 445 | $0.0267 | $0.0270 | $0.0053 | $0.0054 |
| assistant_medium_medium | 5/5 | 5/5 | 645 | 595 | $0.0389 | $0.0364 | $0.0078 | $0.0073 |
| assistant_high_medium | 0/5 | 5/5 | 1500 | 1729 | $0.1947 | $0.2061 | no successes | $0.0412 |
| assistant_high_long | 5/5 | 5/5 | 1131 | 1282 | $0.1769 | $0.1844 | $0.0354 | $0.0369 |
| assistant_specific | 7/7 | 7/7 | 646 | 576 | $0.2045 | $0.1997 | $0.0292 | $0.0285 |
| docx_ref_summary | 2/2 | 2/2 | 786 | 772 | $0.1960 | $0.1957 | $0.0980 | $0.0978 |
| docx_ref_extraction | 2/2 | 2/2 | 792 | 764 | $0.0589 | $0.0583 | $0.0294 | $0.0292 |
| assistant_suggested_draft | 1/1 | 1/1 | 1328 | 1220 | $0.0350 | $0.0339 | $0.0350 | $0.0339 |

## Benefits

- **Heavy draft prompt:** 0 of 5 to 5 of 5. Answers were 112 to 146 words, with no unsupported figures. The largest used 1,913 output tokens, above the old cap.
- **Field extraction:** 2 of 5 to 5 of 5. No silent fall back to the Demo extractor. Field accuracy on the successful runs: FORWARD 100%, Horizon 50%, Forex 50%, Bonds 67%, Better Together 33%. The raised cap does not fix the segment-name problem, so accuracy stays low where segments are written as "Affluent – Gold".
- **App's suggested question "Draft An SMS For This Offer" (FORWARD, 3 repetitions):** 3 of 3 at both caps. Output 1,120 to 1,328 tokens at 1,500, so it passes with about 12% to 25% headroom; at 3,000 it used 1,220 to 1,296. It also flagged that SMS is not ticked for FORWARD in 5 of 6 runs.

## Costs

- **Operations that succeeded under both caps (38 operations):** mean output changed by +6 tokens and mean cost by +$0.00006. A higher cap does not make normal answers longer.
- **Operations that failed at 1,500:** each cost $0.032 to $0.053 (₱2 to ₱3.4) to complete at 3,000. At 1,500 the same calls cost about the same and returned nothing usable.
- **Worst case:** a call that uses the whole 3,000 cap costs at most $0.015 (₱0.96) more output than one that stops at 1,500.
- **Latency:** the 5 draft calls took 10 to 14 seconds at 3,000, against about 11 seconds for the failed 1,500 calls.
- **Highest output seen at 3,000:** 1,913 tokens, so 3,000 leaves about 57% headroom. A cap of 2,500 would also have worked in this sample.

## Not fixed by the cap

- **Persona naming:** 1 of 3 personas came back invalid at 3,000 (`invalid_reply`, so the app's built-in name was used). The pilot had 3 of 3 valid, so naming validity varies from run to run. It is not a cap problem: output was far below 800 tokens.
- **Segment-name validator:** unchanged (see the pilot README).
- **No stop-reason check in the app:** when a reply is cut by the cap but has some text, the app treats it as a normal answer. The pilot's empty replies fell back to the Demo answer, but the diagnostic shows a case where 197 characters of text came back, which the app would show as an answer.

## Recommendation (needs your approval; no app code was changed)

1. Raise the assistant and extractor caps to about 3,000 (persona naming does not need it).
2. Treat a `max_tokens` stop as a failure so a cut answer is never shown.
3. Fix the segment-name matching in extraction separately.

Caveats: single repetition per cap; extraction at 1,200 passed in the diagnostic and failed in the pilot, so the 1,500 versus 3,000 gap is real but the exact failure rates are uncertain. The full 3-repetition batch would tighten this.
