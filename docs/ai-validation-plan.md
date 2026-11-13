# AI Validation Plan

Part 9 round 3, Requirement 40. Covers the three places that call Amazon Bedrock: Upload Campaign File, persona naming and Ask Assistant. The prediction model (Parts 1 to 4) has its own validation and is out of scope here.

Each check says what is measured, how, the pass mark, and where the automated part lives.

## 1. Extractor accuracy (Upload Campaign File)

**What:** how many form fields Bedrock reads correctly from a campaign file, compared with the built-in rules.

**How:**

1. Build a labelled set of at least 20 campaign files (PDF and DOCX): real past proposals with personal details removed, plus written variants (tables, bullet lists, long prose, missing fields).
2. For each file, write down the correct value of the eight fields (product, mechanic, threshold type and value, reward, eligible segments, minimum ADB, channels).
3. Run "Fill Form with Bedrock" and "Fill Form with Built-in Rules" on each file.
4. Score each field: correct, wrong, or left as Needs Input. A wrong value counts worse than an empty one, because a planner may not notice it.

**Pass mark:** Bedrock reads at least 90% of stated fields correctly, with no more than 2% wrong values, and is at least as accurate as the built-in rules on every field.

**Automated now:** `tests/test_part7_extractor_unit.py` and `tests/test_part7_extraction_validity_property.py` prove that invalid values are dropped, never repaired, and that every field is tagged. `tests/test_part9_ai_unit.py` proves masking (phones, emails, long numbers) before sending, and that masked text passes the privacy guard while a client id is still blocked.

## 2. Assistant groundedness (Ask Assistant)

**What:** answers use only figures that are in the campaign or the run.

**How:**

1. Use the question set in `scripts/measure_ai_tokens.py` (10 interaction types) on the three fixtures, plus 20 free questions from planners.
2. For each answer, the app's number check lists any figure not found in the payload. Review every flagged answer by hand.
3. Two reviewers mark each answer: grounded, partly grounded, or not grounded; and useful or not.

**Pass mark:** at least 95% of answers grounded, no answer with an invented figure that is not flagged, and at least 80% marked useful.

**Automated now:** `tests/test_part9_ai_unit.py` covers the number check (invented figures flagged, payload figures and draft character counts allowed), the answer layout (Hypothesis: at most 150 words, whole bullets only, idempotent, line breaks kept, one layout for Demo and Bedrock), the run summary passing the privacy guard, and the routing (one-client questions refused, segment questions answered from the run).

## 3. Persona-name validity (persona naming)

**What:** Bedrock names describe the persona's real traits and follow the naming rules.

**How:**

1. Build personas at three levels (All leads, by campaign, split by region).
2. Name them with Bedrock. Every reply already passes `validate_narration`: length, exact channels, no field codes, unique names, and only numbers present in the persona's totals.
3. Two reviewers read each name against the card's size, share and "what sets them apart": fits, partly fits, or misleading.

**Pass mark:** no misleading name; at least 85% "fits". The fallback rate (Mixed or Demo Mode) stays under 10% when Bedrock is reachable.

**Automated now:** `tests/test_part7_persona_narrator_unit.py` covers the validation rules. `tests/test_part9_ai_unit.py` proves that renaming never moves a lead or changes a group size, and that the Bedrock, Mixed and Demo labels are accurate.

## 4. After launch: A/B check with the control group

**What:** whether campaigns planned with the app do better than the baseline, and whether the forecast is honest.

**How:**

1. Every lead file already holds back a control group (about 10% of each segment's contactable leads, `CONTROL_FRACTION`).
2. After the promo ends, compare the join rate of the messaged leads with the control group, per segment: the uplift is the promo's real effect.
3. Compare the forecast (Expected Joiners over sendable leads) with the actual join rate of messaged leads. Past Promos already shows predicted and actual by segment, with the gap in points.
4. Review the "Who Is Being Targeted" view for each campaign: any group flagged for a 10 point or larger shift is checked with the campaign owner.

**Pass mark:** a positive uplift over the control group in the Act first segment; forecast within the Likely Range for most segments; every flagged group explained.

## Ownership and cadence

- Before launch: checks 1 to 3 once, on the labelled sets.
- Monthly: re-run check 2 on a fresh sample of 20 logged questions (the assistant log, including answers reported as wrong).
- Per campaign: check 4 when the promo ends.
