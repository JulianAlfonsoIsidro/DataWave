"""Build the technical and business costing reports from stored benchmark results.

No Bedrock calls: it reads ``raw.jsonl`` files only. Prices and the exchange rate are read from
``.env.eval`` (values only; no credentials are read or printed).

    .venv/bin/python evaluation/build_cost_reports.py

Writes evaluation/TECHNICAL_COST_REPORT.md, evaluation/BUSINESS_COST_REPORT.md and supporting CSVs in
evaluation/results/experimental/costing/.
"""
from __future__ import annotations

import csv
import json
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
RES = EVAL / "results"
EXP_DIR = RES / "experimental" / "postfix"
OUT = RES / "experimental" / "costing"
FACTS = json.loads((EVAL / "expected_facts.json").read_text(encoding="utf-8"))
PROPS = FACTS["proposals"]

env = dotenv_values(ROOT / ".env.eval")
P_IN = float(env["BEDROCK_INPUT_PRICE_PER_MILLION"])
P_OUT = float(env["BEDROCK_OUTPUT_PRICE_PER_MILLION"])
FX = float(env["USD_TO_PHP"])
MODEL = None

# Benchmark bundle (one "campaign" in the benchmark) and usage scenarios (documented assumptions).
BUNDLE_CATS = ("extraction", "summary_with_doc", "assistant_high_medium", "assistant_high_long", "assistant_specific")
DOC_ASSISTANT_CATS = ("assistant_high_medium", "assistant_high_long", "assistant_specific")
SCENARIOS = {  # extraction runs, summaries, persona runs, assistant prompts
    "Light": (1, 1, 1, 3),
    "Moderate": (1, 2, 2, 10),
    "Heavy": (2, 4, 3, 30),
}


def load(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def usd(inp: float, out: float) -> float:
    return inp / 1e6 * P_IN + out / 1e6 * P_OUT


def inv_tokens(o: dict) -> tuple[int, int, int]:
    invs = [i for i in o["invocations"] if i.get("total_tokens") is not None]
    return (sum(i["input_tokens"] or 0 for i in invs), sum(i["output_tokens"] or 0 for i in invs),
            sum(i["total_tokens"] or 0 for i in invs))


def op_usd(o: dict) -> float:
    i, t, _ = inv_tokens(o)
    return usd(i, t)


def secs(o: dict) -> float:
    return sum(i.get("seconds", 0) for i in o["invocations"])


def finals(rows: list[dict]) -> dict[tuple[str, int], dict]:
    best: dict[tuple[str, int], dict] = {}
    for r in rows:
        k = (r["case_id"], r["rep"])
        if k not in best or r["attempt"] > best[k]["attempt"]:
            best[k] = r
    return best


def is_trunc(o: dict) -> bool:
    return any(i.get("reason") == "truncated" or i.get("stop_reason") == "max_tokens" or i.get("mode") == "Truncated"
               for i in o["invocations"])


def fail_reasons(o: dict) -> list[str]:
    rs = [i.get("reason") or i.get("mode") for i in o["invocations"] if i.get("mode") != "Bedrock"]
    return rs or ([o["error"]] if o.get("error") else ["unknown"])


def sd(v: list[float]) -> float:
    return st.stdev(v) if len(v) > 1 else 0.0


def f0(x: float) -> str:
    return f"{x:,.0f}"


def f4(x: float) -> str:
    return f"{x:,.4f}"


def php(x: float) -> float:
    return x * FX


def table(headers: list[str], rows: list[list], align: str = "") -> str:
    a = align or ("l" + "r" * (len(headers) - 1))
    sep = "|" + "|".join("---:" if c == "r" else "---" for c in a) + "|"
    return "\n".join(["| " + " | ".join(headers) + " |", sep] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def norm(t: str) -> str:
    t = (t or "").lower().replace("₱", "").replace("–", "-").replace("—", "-")
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    return re.sub(r"\bphp\s*", "", t)


def doc_facts_rate(key: str, text: str) -> float:
    nt = norm(text)
    facts = PROPS[key]["doc_facts"]
    return sum(any(re.search(rx, nt) for rx in f["any"]) for f in facts) / len(facts)


def cat_of(o: dict) -> str:
    return o["category"]


# --------------------------------------------------------------------------- #
# Calculations
# --------------------------------------------------------------------------- #
rows = load(EXP_DIR / "raw.jsonl")
MODEL = rows[0]["model_id"]
fin = finals(rows)
ops = list(fin.values())
base_main, base_cap = load(RES / "main" / "raw.jsonl"), load(RES / "cap3000" / "raw.jsonl")
inventory = {(r["proposal"], r["format"]): r for r in csv.DictReader((EXP_DIR / "proposal_inventory.csv").open(encoding="utf-8"))}
CATS = list(dict.fromkeys(r["category"] for r in rows))
STD_CATS = [c for c in CATS]
REPS = sorted({r["rep"] for r in rows})
ORDER = [k for k, _ in sorted(PROPS.items(), key=lambda kv: kv[1]["rank"])]


def cat_stats(cat_rows_final: list[dict], cat_rows_all: list[dict]) -> dict:
    billed = [o for o in cat_rows_final if inv_tokens(o)[2] > 0]
    tin, tout, ttot = ([inv_tokens(o)[i] for o in billed] for i in range(3))
    cost = [op_usd(o) for o in billed]
    ok = [o for o in cat_rows_final if o["ok"]]
    failed_final = [o for o in cat_rows_final if not o["ok"]]
    waste = sum(op_usd(r) for r in cat_rows_all if not r["ok"])
    attempted = sum(len(o["invocations"]) for o in cat_rows_final)
    row = {
        "cases": len({o["case_id"] for o in cat_rows_final}), "repetitions": len({o["rep"] for o in cat_rows_final}),
        "operations": len(cat_rows_final), "attempts": len(cat_rows_all),
        "invocations_attempted": attempted, "invocations_billed": sum(1 for o in cat_rows_final for i in o["invocations"] if i.get("total_tokens")),
        "avg_invocations_per_op": attempted / len(cat_rows_final),
        "ops_with_usage": len(billed), "ok": len(ok), "failed": len(failed_final),
        "truncated": sum(is_trunc(o) for o in cat_rows_final),
        "retried_ops": sum(o["attempt"] > 1 for o in cat_rows_final),
        "failed_attempts_total": sum(not r["ok"] for r in cat_rows_all),
        "cost_failed_attempts_usd": waste,
    }
    for name, v in (("input", tin), ("output", tout), ("total", ttot)):
        row.update({f"{name}_avg": st.mean(v) if v else 0, f"{name}_min": min(v) if v else 0,
                    f"{name}_max": max(v) if v else 0, f"{name}_sd": sd(v)})
    row.update({"cost_avg_usd": st.mean(cost) if cost else 0, "cost_min_usd": min(cost) if cost else 0,
                "cost_max_usd": max(cost) if cost else 0, "cost_sd_usd": sd(cost),
                "latency_avg_s": st.mean(secs(o) for o in billed) if billed else 0,
                "latency_max_s": max((secs(o) for o in billed), default=0),
                "cost_total_incurred_usd": sum(op_usd(r) for r in cat_rows_all)})
    return row


cat_rows = {c: cat_stats([o for o in ops if o["category"] == c], [r for r in rows if r["category"] == c]) for c in CATS}

# Persona: per run and per persona (each persona is its own request)
pers_runs = [o for o in ops if o["category"] == "persona" and o["ok"]]
pers_inv = [i for o in pers_runs for i in o["invocations"] if i.get("total_tokens")]
per_persona = {
    "n": len(pers_inv),
    "input": st.mean(i["input_tokens"] for i in pers_inv), "output": st.mean(i["output_tokens"] for i in pers_inv),
    "total": st.mean(i["total_tokens"] for i in pers_inv),
    "cost": st.mean(usd(i["input_tokens"], i["output_tokens"]) for i in pers_inv),
    "cost_min": min(usd(i["input_tokens"], i["output_tokens"]) for i in pers_inv),
    "cost_max": max(usd(i["input_tokens"], i["output_tokens"]) for i in pers_inv),
}
PERSONA_RUN_COST = st.mean(op_usd(o) for o in pers_runs)
PERSONA_RUN_TOK = st.mean(inv_tokens(o)[2] for o in pers_runs)

# Per proposal
prop_rows = []
for p in ORDER:
    po = [o for o in ops if o["proposal"] == p]
    pa = [r for r in rows if r["proposal"] == p]
    inv = inventory.get((p, "pdf"))
    asst = [o for o in po if o["kind"] == "assistant"]
    tin = sum(inv_tokens(r)[0] for r in pa)
    tout = sum(inv_tokens(r)[1] for r in pa)
    ttot = sum(inv_tokens(r)[2] for r in pa)
    cost = sum(op_usd(r) for r in pa)
    nrep = len({o["rep"] for o in po})
    levels = Counter((o["category"], o["level"]) for o in asst)
    sumdoc = [o for o in po if o["category"] == "summary_with_doc" and o["ok"]]
    prop_rows.append({
        "proposal": p, "title": PROPS[p]["title"], "rank": PROPS[p]["rank"], "pdf_used": Path(PROPS[p]["pdf"]).name,
        "original_format": "DOCX (converted to PDF)" if PROPS[p]["docx"] else "PDF",
        "chars": int(inv["chars"]), "est_tokens": int(inv["est_tokens"]),
        "actual_summary_input_tokens": st.mean(inv_tokens(o)[0] for o in sumdoc) if sumdoc else 0,
        "user_prompts": len(asst), "operations": len(po), "invocations_attempted": sum(len(o["invocations"]) for o in po),
        "levels": levels, "tokens_in": tin, "tokens_out": tout, "tokens_total": ttot, "cost_total": cost,
        "reps": nrep, "attempts": len(pa), "failed_attempts": sum(not r["ok"] for r in pa),
        "cost_failed": sum(op_usd(r) for r in pa if not r["ok"]),
    })

# With vs without proposal
wv = []
for p in ORDER:
    w = [o for o in ops if o["category"] == "summary_with_doc" and o["proposal"] == p and o["ok"]]
    f = [o for o in ops if o["category"] == "summary_form_only" and o["proposal"] == p and o["ok"]]
    if not w or not f:
        continue
    wv.append({"proposal": p, "n_with": len(w), "n_without": len(f),
               "in_with": st.mean(inv_tokens(o)[0] for o in w), "in_without": st.mean(inv_tokens(o)[0] for o in f),
               "out_with": st.mean(inv_tokens(o)[1] for o in w), "out_without": st.mean(inv_tokens(o)[1] for o in f),
               "cost_with": st.mean(op_usd(o) for o in w), "cost_without": st.mean(op_usd(o) for o in f),
               "lat_with": st.mean(secs(o) for o in w), "lat_without": st.mean(secs(o) for o in f),
               "facts_with": st.mean(doc_facts_rate(p, o["response"]) for o in w),
               "facts_without": st.mean(doc_facts_rate(p, o["response"]) for o in f)})

# Benchmark bundle = one tested "campaign": extraction + summary with proposal + document-attached assistant prompts
# + one persona run. Complete bundles only (every operation succeeded).
bundles = []
for p in ORDER:
    for rep in REPS:
        members = [o for o in ops if o["proposal"] == p and o["rep"] == rep and o["category"] in BUNDLE_CATS]
        pers = fin.get(("persona:default", rep))
        ids = {o["case_id"] for o in members}
        attempts = [r for r in rows if r["rep"] == rep and (r["case_id"] in ids or r["case_id"] == "persona:default")]
        complete = bool(members) and all(o["ok"] for o in members) and pers is not None and pers["ok"]
        prompts = sum(1 for o in members if o["category"] != "extraction")
        bundles.append({
            "proposal": p, "rep": rep, "complete": complete, "operations": len(members) + 1, "prompts": prompts,
            "invocations": sum(len(o["invocations"]) for o in members) + (len(pers["invocations"]) if pers else 0),
            "in": sum(inv_tokens(r)[0] for r in attempts), "out": sum(inv_tokens(r)[1] for r in attempts),
            "total": sum(inv_tokens(r)[2] for r in attempts), "cost": sum(op_usd(r) for r in attempts),
        })
good = [b for b in bundles if b["complete"]]
camp = {}
for p in ORDER:
    g = [b for b in good if b["proposal"] == p]
    if g:
        camp[p] = {"n": len(g), "prompts": g[0]["prompts"], "ops": g[0]["operations"], "inv": g[0]["invocations"],
                   "tokens": st.mean(b["total"] for b in g), "cost": st.mean(b["cost"] for b in g),
                   "cost_min": min(b["cost"] for b in g), "cost_max": max(b["cost"] for b in g),
                   "tokens_in": st.mean(b["in"] for b in g), "tokens_out": st.mean(b["out"] for b in g)}
ALL_CAMP_COST = st.mean(c["cost"] for c in camp.values())
ALL_CAMP_TOK = st.mean(c["tokens"] for c in camp.values())
ALL_CAMP_PROMPTS = st.mean(c["prompts"] for c in camp.values())

# Unit costs for scenarios (successful operations only), per proposal then averaged
unit = {}
for p in ORDER:
    def mean_cost(cats):
        v = [op_usd(o) for o in ops if o["proposal"] == p and o["category"] in cats and o["ok"]]
        return st.mean(v) if v else None
    def mean_tok(cats):
        v = [inv_tokens(o)[2] for o in ops if o["proposal"] == p and o["category"] in cats and o["ok"]]
        return st.mean(v) if v else None
    unit[p] = {"ext": mean_cost(("extraction",)), "sum": mean_cost(("summary_with_doc",)), "asst": mean_cost(DOC_ASSISTANT_CATS),
               "ext_t": mean_tok(("extraction",)), "sum_t": mean_tok(("summary_with_doc",)), "asst_t": mean_tok(DOC_ASSISTANT_CATS)}
U = {k: st.mean(u[k] for u in unit.values() if u[k] is not None) for k in ("ext", "sum", "asst", "ext_t", "sum_t", "asst_t")}
U["pers"], U["pers_t"] = PERSONA_RUN_COST, PERSONA_RUN_TOK


def scen_cost(s, u):
    e, sm, pr, a = SCENARIOS[s]
    return e * u["ext"] + sm * u["sum"] + pr * PERSONA_RUN_COST + a * u["asst"]


def scen_tok(s):
    e, sm, pr, a = SCENARIOS[s]
    return e * U["ext_t"] + sm * U["sum_t"] + pr * PERSONA_RUN_TOK + a * U["asst_t"]


scen = {}
for s in SCENARIOS:
    per_p = [scen_cost(s, u) for u in unit.values()]
    scen[s] = {"avg": scen_cost(s, U), "min": min(per_p), "max": max(per_p), "tokens": scen_tok(s)}

# Totals and baseline
total_cost_all = sum(op_usd(r) for r in rows)
total_cost_fail = sum(op_usd(r) for r in rows if not r["ok"])
tot_in, tot_out = sum(inv_tokens(r)[0] for r in rows), sum(inv_tokens(r)[1] for r in rows)
exp_calls = sum(len(r["invocations"]) for r in rows)
no_usage_calls = sum(1 for r in rows for i in r["invocations"] if not i.get("total_tokens"))
prog = {"main": sum(op_usd(r) for r in base_main), "cap3000": sum(op_usd(r) for r in base_cap), "postfix": total_cost_all}
DIAG_USD = usd(10855 + 9988, 1500 + 1090)  # stop-reason diagnostic (2 calls), usage printed by the script


# --------------------------------------------------------------------------- #
# Supporting CSVs
# --------------------------------------------------------------------------- #
LABEL = {
    "summary_with_doc": "Campaign summary, proposal attached",
    "summary_form_only": "Campaign summary, form values only (baseline case)",
    "persona": "Persona naming, full run (3 personas)",
    "extraction": "Upload field extraction (Bedrock)",
    "assistant_low_short": "Assistant, low context, short prompt (no proposal)",
    "assistant_medium_medium": "Assistant, medium context, medium prompt (no proposal)",
    "assistant_high_medium": "Assistant, high context, medium prompt (SMS + email draft)",
    "assistant_high_long": "Assistant, high context, long prompt",
    "assistant_specific": "Assistant, high context, proposal-specific prompts",
    "assistant_suggested_draft": "Assistant, suggested question \"Draft An SMS For This Offer\" (FORWARD only)",
}
fail_final = [o for o in ops if not o["ok"]]
failed_attempts = sorted((r for r in rows if not r["ok"]), key=lambda r: (r["rep"], r["case_id"], r["attempt"]))
all_instant = bool(failed_attempts) and all(not any(i.get("total_tokens") for i in r["invocations"]) and
                                            all((i.get("reason") == "error") for i in r["invocations"]) for r in failed_attempts)
retried_final = [o for o in ops if o["attempt"] > 1]

write_csv(OUT / "operation_costing.csv", [{"category": c, **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()},
                                           "cost_avg_php": round(php(r["cost_avg_usd"]), 4)} for c, r in cat_rows.items()])
write_csv(OUT / "proposal_costing.csv", [{k: v for k, v in r.items() if k != "levels"} for r in prop_rows])
write_csv(OUT / "campaign_bundle_costs.csv", [{**b, "cost_php": round(php(b["cost"]), 4)} for b in bundles])
write_csv(OUT / "with_vs_without_proposal.csv", wv)
write_csv(OUT / "scenario_projection.csv", [
    {"scenario": s, "extraction_runs": SCENARIOS[s][0], "summaries": SCENARIOS[s][1], "persona_runs": SCENARIOS[s][2],
     "assistant_prompts": SCENARIOS[s][3], "avg_tokens_per_campaign": round(scen[s]["tokens"]),
     "usd_per_campaign": round(scen[s]["avg"], 4), "php_per_campaign": round(php(scen[s]["avg"]), 2),
     "usd_per_campaign_min": round(scen[s]["min"], 4), "usd_per_campaign_max": round(scen[s]["max"], 4),
     **{f"usd_{n}_campaigns": round(scen[s]["avg"] * n, 2) for n in (1, 100, 1000)},
     **{f"php_{n}_campaigns": round(php(scen[s]["avg"] * n), 2) for n in (1, 100, 1000)}} for s in SCENARIOS])


def base_stats(raw: list[dict]) -> dict:
    f = finals(raw)
    out = {}
    for c in dict.fromkeys(r["category"] for r in raw):
        g = [o for o in f.values() if o["category"] == c]
        billed = [o for o in g if inv_tokens(o)[2] > 0]
        out[c] = {"ops": len(g), "ok": sum(o["ok"] for o in g), "avg": st.mean(op_usd(o) for o in billed) if billed else 0,
                  "total": sum(op_usd(o) for o in g)}
    return out


B1, B2 = base_stats(base_main), base_stats(base_cap)
rep1 = [o for o in ops if o["rep"] == 1]
E1 = {c: {"ops": len([o for o in rep1 if o["category"] == c]), "ok": sum(o["ok"] for o in rep1 if o["category"] == c)} for c in CATS}
write_csv(OUT / "baseline_vs_experimental_by_category.csv", [
    {"category": c, "baseline_1500_ops": B1.get(c, {}).get("ops"), "baseline_1500_ok": B1.get(c, {}).get("ok"),
     "baseline_1500_avg_cost_usd": round(B1.get(c, {}).get("avg", 0), 5), "script3000_ops": B2.get(c, {}).get("ops"),
     "script3000_ok": B2.get(c, {}).get("ok"), "script3000_avg_cost_usd": round(B2.get(c, {}).get("avg", 0), 5),
     "experimental_ops": cat_rows[c]["operations"], "experimental_ok": cat_rows[c]["ok"],
     "experimental_avg_cost_usd": round(cat_rows[c]["cost_avg_usd"], 5)} for c in CATS])

# --------------------------------------------------------------------------- #
# Technical report
# --------------------------------------------------------------------------- #
usd_php = lambda x, d=4: f"${x:,.{d}f} (₱{php(x):,.2f})"
n_ops, n_att = len(ops), len(rows)
ex_ok = sum(o["ok"] for o in ops)
pending = len(fail_final)
fail_note = (f"{pending} operation(s) are still failed in the final results (listed in section 6); these are excluded from "
             "token and cost averages only where they returned no usage, and from complete campaign bundles."
             if pending else "All operations succeeded on their final attempt.")

T = []
T.append(f"""# Technical costing report: full batch evaluation

**Scope:** AWS Bedrock inference cost of PAM's AI features, measured in the full 3-repetition benchmark on the **experimental** configuration (branch `part-12-experiment`). This is an audit document: every figure can be recomputed from the CSV and raw files listed in section 11, and from `evaluation/build_cost_reports.py`, without any new Bedrock call.

**Read this first**
- **Experimental versus baseline.** The figures in this report are for the experimental configuration (assistant and extractor output caps 3,000, truncation treated as failure, segment-name fixes). They are not measurements of the submitted version (`part-11-final-changes`, caps 1,500 and 1,200). The submitted version was measured only in a 1-repetition pilot (section 9); no full batch was run on it. Experimental improvements must not be attributed to the submitted version.
- **Measured versus estimated.** Token counts, latency and per-operation costs are measured (Bedrock's own usage counts). Per-campaign costs and the usage scenarios are estimates built from measured per-operation averages (section 8 and the business report).
- **Scope of cost.** AWS Bedrock inference only. Excluded: hosting, storage, data integration, monitoring, maintenance, support and other production costs.
- **Status of this run:** {n_ops} operations ({len(CATS)} categories, {len(REPS)} repetitions); {ex_ok} succeeded on the final attempt. {fail_note}
""")

T.append(f"""## 1. Configuration and provenance

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

- **Model / inference profile:** `{MODEL}` (Amazon Bedrock Converse API, region from `.env.eval`, not recorded here).
- **Run date:** 2026-11-27. Benchmark script: `evaluation/run_benchmark.py` (identical in both configurations; no `--output-cap` override in the experimental run). Run log: `evaluation/results/experimental/postfix/run_log_full_batch.txt`.
- **Documents:** five proposals tested as PDFs (two were DOCX files converted to PDF; see `PILOT_README.md` section 4 for why).
- **Same-purpose reports:** `PILOT_README.md` (pilot results) and `CAP_COMPARISON.md` (cap test) contain pilot cost figures but are not full-batch costing reports. This report is new and separate from the business report.
""")

T.append(f"""## 2. Costing methodology

**Pricing (USD per 1,000,000 tokens):** input **${P_IN:.2f}**, output **${P_OUT:.2f}**. Source: supplied and verified by the project owner and stored in `.env.eval` (`BEDROCK_INPUT_PRICE_PER_MILLION`, `BEDROCK_OUTPUT_PRICE_PER_MILLION`). The repository does not record a pricing-page URL or the verification date, so the pricing date is **not recorded** and I could not independently confirm the figures.

**Exchange rate:** ₱**{FX:g}** per USD, a fixed rate chosen by the project owner (`USD_TO_PHP`). Source and date are **not recorded**. Peso figures are USD x {FX:g} and would change with the actual rate.

**Formulas**
- `cost_USD = input_tokens / 1,000,000 x {P_IN:.2f} + output_tokens / 1,000,000 x {P_OUT:.2f}` (input and output costed separately, per Bedrock invocation, using the token counts returned by Bedrock).
- `cost_PHP = cost_USD x {FX:g}`.
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
""")

T.append(f"""## 3. Execution summary

- Operations: {n_ops} ({n_att} attempts). Bedrock invocations in final attempts: {sum(len(o['invocations']) for o in ops)}; all attempts: {exp_calls}, of which {no_usage_calls} were rejected before reaching the model (expired credentials, no usage, no cost) and {exp_calls - no_usage_calls} were answered by the model.
- Tokens (all attempts): {tot_in:,} input, {tot_out:,} output, {tot_in+tot_out:,} total.
- **Incurred cost of this full batch (all attempts, including the pilot repetition): {usd_php(total_cost_all, 3)}.** Cost of failed attempts: {usd_php(total_cost_fail, 4)}.
- Other evaluation spend, for audit: baseline pilot `main` {usd_php(prog['main'], 3)}; script-only 3,000 cap `cap3000` {usd_php(prog['cap3000'], 3)}; stop-reason diagnostic (2 calls, from printed usage) {usd_php(DIAG_USD, 3)}. Program total: {usd_php(prog['main'] + prog['cap3000'] + total_cost_all + DIAG_USD, 3)}.
""")

hdr = ["Category", "Cases", "Reps", "Ops", "Invocations / op", "OK", "Failed", "Truncated", "Retried ops", "Failed attempts"]
T.append("## 4. Per prompt type / application operation\n\n### 4.1 Counts and outcomes\n\n" + table(hdr, [
    [LABEL[c], r["cases"], r["repetitions"], r["operations"], f"{r['avg_invocations_per_op']:.2f}", r["ok"], r["failed"],
     r["truncated"], r["retried_ops"], r["failed_attempts_total"]] for c, r in cat_rows.items()], "lrrrrrrrrr"))
T.append("\n### 4.2 Tokens per operation (average / minimum / maximum / standard deviation)\n\n" + table(
    ["Category", "Input avg", "Input min-max", "Input SD", "Output avg", "Output min-max", "Output SD", "Total avg", "Total min-max", "Total SD"],
    [[LABEL[c], f0(r["input_avg"]), f"{f0(r['input_min'])}-{f0(r['input_max'])}", f0(r["input_sd"]), f0(r["output_avg"]),
      f"{f0(r['output_min'])}-{f0(r['output_max'])}", f0(r["output_sd"]), f0(r["total_avg"]),
      f"{f0(r['total_min'])}-{f0(r['total_max'])}", f0(r["total_sd"])] for c, r in cat_rows.items()], "lrrrrrrrrr"))
T.append("\n### 4.3 Cost and latency per operation\n\n" + table(
    ["Category", "Avg cost USD", "Avg cost PHP", "Min-max USD", "SD USD", "Avg latency (s)", "Max latency (s)", "Incurred total USD (all attempts)", "Cost of failed attempts USD"],
    [[LABEL[c], f4(r["cost_avg_usd"]), f"{php(r['cost_avg_usd']):,.2f}", f"{r['cost_min_usd']:.4f}-{r['cost_max_usd']:.4f}", f4(r["cost_sd_usd"]),
      f"{r['latency_avg_s']:.1f}", f"{r['latency_max_s']:.1f}", f4(r["cost_total_incurred_usd"]), f4(r["cost_failed_attempts_usd"])]
     for c, r in cat_rows.items()], "lrrrrrrrr"))
T.append(f"""
Notes: "Failed" counts operations whose final attempt failed. "Truncated" counts final attempts that stopped at `max_tokens`. "Retried ops" counts operations whose final attempt is a second or later attempt. Averages exclude operations with no usage (credential errors), which is why the averages for categories with such operations rest on fewer operations than listed.

## 5. Persona generation

A persona run names 3 personas with one Bedrock request each. Clustering itself uses no model and has no inference cost.

{table(["Measure", "Value"], [
    ["Full persona-generation run (3 personas): average cost", usd_php(PERSONA_RUN_COST)],
    ["Full run: average tokens (input + output)", f"{PERSONA_RUN_TOK:,.0f}"],
    ["Runs measured", cat_rows['persona']['ok']],
    ["Per persona: invocations measured", per_persona['n']],
    ["Per persona: average input / output / total tokens", f"{per_persona['input']:,.0f} / {per_persona['output']:,.0f} / {per_persona['total']:,.0f}"],
    ["Per persona: average cost", usd_php(per_persona['cost'], 5)],
    ["Per persona: cost range", f"${per_persona['cost_min']:.5f} to ${per_persona['cost_max']:.5f}"]], "lr")}

Per-persona figures are **measured**, not estimated: each persona is its own request, so no apportioning of a shared call was needed. They describe the "short persona" case (name, description, difference, 2-3 actions) on the synthetic dataset's 3-persona default; a run with more personas would scale roughly linearly (estimate).
""")

fl = [[r["case_id"], r["rep"], r["attempt"], ", ".join(sorted(set(fail_reasons(r)))), usd_php(op_usd(r), 4),
       "still failed" if fin[(r["case_id"], r["rep"])] is r and not r["ok"] else ("succeeded on retry" if fin[(r["case_id"], r["rep"])]["ok"] else "failed")] for r in failed_attempts]
T.append(f"""## 6. Failed, truncated and retried operations

- Operations whose final attempt failed: **{len(fail_final)}**. Operations retried: **{len(retried_final)}**. Failed attempts in total: {sum(not r['ok'] for r in rows)}. Truncated (`max_tokens`) final attempts: {sum(is_trunc(o) for o in ops)}; stop reasons recorded in the experimental run: {dict(Counter(i.get('stop_reason') for r in rows for i in r['invocations']))}.
- Cost of unsuccessful attempts: {usd_php(total_cost_fail, 4)}.
""" + ((("- Failure cause: every failed attempt is an immediate `error` with no model response. A separate no-cost probe afterwards returned `ExpiredTokenException`: the AWS session token in `.env.eval` expired during repetition 3. These calls returned no usage and incurred no cost. " if all_instant else "- Failure reasons are listed per attempt below. ") +
  "All failed attempts are preserved in `raw.jsonl`.\n\n" + table(["Case", "Rep", "Attempt", "Reason", "Cost", "Outcome"], fl, "lrrlrl") + "\n") if fl else "- No failed attempts.\n"))

pr_tbl = [[r["title"], r["pdf_used"], r["original_format"], f"{r['chars']:,}", f"{r['est_tokens']:,}", f"{r['actual_summary_input_tokens']:,.0f}"] for r in prop_rows]
T.append("## 7. Per campaign proposal\n\n### 7.1 Documents\n\n" + table(
    ["Campaign", "Document tested", "Original format", "Characters", "Est. tokens (chars/4)", "Actual input tokens (summary, proposal attached)"], pr_tbl, "lllrrr"))
T.append("\n\nEstimated tokens use the app's characters-divided-by-4 rule; actual input tokens (which include the prompt, form values and tags) are about 1.9 times higher.")
T.append("\n\n### 7.2 Prompts, operations and invocations\n\n" + table(
    ["Campaign", "User prompts", "Operations (excl. persona)", "Invocations attempted", "Attempts incl. retries", "Failed attempts"],
    [[r["title"], r["user_prompts"], r["operations"], r["invocations_attempted"], r["attempts"], r["failed_attempts"]] for r in prop_rows], "lrrrrr"))
T.append("\n\nUser prompts and operations are counted over all repetitions. The persona run is not proposal-specific and is reported in section 5.")
T.append("\n\n### 7.3 Assistant prompts by category and context level (per repetition)\n\n" + table(
    ["Campaign"] + [f"{LABEL[c].split(',')[0] if False else c}" for c in ("summary_with_doc", "summary_form_only", "assistant_low_short", "assistant_medium_medium", "assistant_high_medium", "assistant_high_long", "assistant_specific", "assistant_suggested_draft")],
    [[r["title"]] + [sum(v for (c, _l), v in r["levels"].items() if c == cat) // max(1, r["reps"]) for cat in ("summary_with_doc", "summary_form_only", "assistant_low_short", "assistant_medium_medium", "assistant_high_medium", "assistant_high_long", "assistant_specific", "assistant_suggested_draft")] for r in prop_rows],
    "lrrrrrrrr"))
T.append("\n\nContext levels: `low` = form values only; `medium` = form + campaign context + known gaps (no document); `doc` = form + proposal; `high` = form + context + proposal (+ a PAM run summary for FORWARD). Summary-with-proposal is level `doc`; summary-form-only and low-short are level `low`.")
T.append("\n\n### 7.4 Total and average tokens and cost across repetitions (all attempts, incurred)\n\n" + table(
    ["Campaign", "Input tokens (total)", "Output tokens (total)", "Total tokens (total)", "Avg total tokens per repetition", "Total cost USD", "Total cost PHP", "Avg cost per repetition USD", "Avg cost per repetition PHP"],
    [[r["title"], f"{r['tokens_in']:,}", f"{r['tokens_out']:,}", f"{r['tokens_total']:,}", f"{r['tokens_total'] / r['reps']:,.0f}", f4(r["cost_total"]),
      f"{php(r['cost_total']):,.2f}", f4(r["cost_total"] / r["reps"]), f"{php(r['cost_total'] / r['reps']):,.2f}"] for r in prop_rows], "lrrrrrrrr"))
T.append("\n\nThese totals cover every benchmark operation for the proposal (including the form-only and no-document cases, which are mutually exclusive alternatives in real use), so they are **not** campaign costs; the campaign estimate is in section 8.")
T.append("\n\n### 7.5 Campaign summary with versus without the attached proposal\n\nThe two cases are alternatives, never summed. Both use the same form values. \"Facts\" is the share of known proposal facts present in the answer (deterministic check).\n\n" + table(
    ["Campaign", "Input tokens with / without", "Output tokens with / without", "Cost USD with / without", "Cost multiple", "Latency s with / without", "Facts with / without"],
    [[PROPS[w["proposal"]]["title"], f"{w['in_with']:,.0f} / {w['in_without']:,.0f}", f"{w['out_with']:,.0f} / {w['out_without']:,.0f}",
      f"{w['cost_with']:.4f} / {w['cost_without']:.4f}", f"{w['cost_with'] / w['cost_without']:.1f}x", f"{w['lat_with']:.1f} / {w['lat_without']:.1f}",
      f"{w['facts_with']:.0%} / {w['facts_without']:.0%}"] for w in wv], "lrrrrrr"))
T.append("\n\nWithout the proposal, the facts found come from the form values; no proposal-only figure appeared in any form-only answer.")

# 8. Campaign bundle and scenarios ------------------------------------------------------------
inc = [b for b in bundles if not b["complete"]]
T.append(f"""

## 8. Campaign-level estimate (derived from measured operations)

**Benchmark campaign bundle.** The benchmark never ran a complete campaign-planning session end to end, so a "campaign" is assembled from measured operations for one proposal in one repetition: 1 field extraction + 1 campaign summary with the proposal attached + the proposal-attached assistant prompts (1 SMS+email draft, 1 long prompt, plus 1 proposal-specific prompt; Horizon has 3) + 1 full persona-generation run. This costs each campaign one persona run (the persona step is not proposal-specific and was measured once per repetition). Mutually exclusive alternatives (the form-only summary, the no-proposal assistant cases) and the FORWARD-only suggested-question case are excluded, and repetitions are not treated as separate campaigns: each proposal's campaign figure is the mean of its repetitions. Only complete bundles (every operation successful) are used: **{len(good)} of {len(bundles)}**.{' Incomplete bundles are excluded, not zero-filled: ' + ', '.join(f"{b['proposal']} rep {b['rep']}" for b in inc) + '.' if inc else ''}

""" + table(["Campaign", "Complete reps", "User prompts", "Operations", "Invocations", "Avg input tokens", "Avg output tokens", "Avg total tokens", "Avg cost USD", "Avg cost PHP", "Min-max cost USD"], [
    [PROPS[p]["title"], c["n"], c["prompts"], c["ops"], c["inv"], f0(c["tokens_in"]), f0(c["tokens_out"]), f0(c["tokens"]), f4(c["cost"]),
     f"{php(c['cost']):,.2f}", f"{c['cost_min']:.4f}-{c['cost_max']:.4f}"] for p, c in camp.items()], "lrrrrrrrrrr") + f"""

Overall average across the five campaigns (equal weight): **{ALL_CAMP_PROMPTS:.1f} user prompts, {ALL_CAMP_TOK:,.0f} tokens, {usd_php(ALL_CAMP_COST)}**. User prompts = summary + assistant prompts; extraction and persona runs are application operations, not prompts. "User prompts" in this bundle is a benchmark test design, **not** evidence of how many prompts a CRM manager sends.

### 8.1 Unit costs used for usage scenarios (successful operations only, mean of the five proposals)

""" + table(["Operation", "Avg cost USD", "Avg cost PHP", "Avg total tokens", "Range across proposals (USD)"], [
    ["Field extraction (per upload)", f4(U["ext"]), f"{php(U['ext']):.2f}", f0(U["ext_t"]), f"{min(u['ext'] for u in unit.values()):.4f}-{max(u['ext'] for u in unit.values()):.4f}"],
    ["Campaign summary, proposal attached", f4(U["sum"]), f"{php(U['sum']):.2f}", f0(U["sum_t"]), f"{min(u['sum'] for u in unit.values()):.4f}-{max(u['sum'] for u in unit.values()):.4f}"],
    ["Assistant prompt, proposal attached (mean of draft, long and specific prompts)", f4(U["asst"]), f"{php(U['asst']):.2f}", f0(U["asst_t"]), f"{min(u['asst'] for u in unit.values()):.4f}-{max(u['asst'] for u in unit.values()):.4f}"],
    ["Persona-generation run (3 invocations)", f4(U["pers"]), f"{php(U['pers']):.2f}", f0(U["pers_t"]), "single measurement series"]], "lrrrr") + """

Scenario definitions and projections are in `BUSINESS_COST_REPORT.md` (section 4) and `results/experimental/costing/scenario_projection.csv`. The scenario counts are illustrative assumptions, not observed CRM behaviour.
""")

_bf = finals(base_main)
DOCX_COST = sum(op_usd(o) for o in _bf.values() if o["category"].startswith("docx_ref"))
PDF_EQ_COST = sum(op_usd(o) for (cid, rp), o in _bf.items() if rp == 1 and (cid.split(":")[0], o["proposal"]) in
                  {("summary_with_doc", "bonds"), ("summary_with_doc", "better_together"), ("extraction", "bonds"), ("extraction", "better_together")})
_std = [o for o in _bf.values() if not o["category"].startswith(("docx_ref", "assistant_suggested"))]
B_N, B_OK = len(_std), sum(o["ok"] for o in _std)
_er = [o for o in ops if o["rep"] == 1 and not o["category"].startswith("assistant_suggested")]
E_N, E_OK = len(_er), sum(o["ok"] for o in _er)
# 9. Baseline vs experimental ------------------------------------------------------------------
T.append("\n## 9. Baseline versus experimental configuration\n\n"
         "Baseline = submitted version (caps 1,500 / 1,200), pilot only: 1 repetition (`results/main`). Script-only = same code with the cap raised to 3,000 inside the script, 1 repetition (`results/cap3000`). "
         "Experimental = this report's configuration, 3 repetitions. Counts are not like-for-like (1 versus 3 repetitions); success is therefore shown as ok/operations, and average cost is per operation with usage.\n\n"
         + table(["Category", "Baseline ok/ops", "Baseline avg USD", "Script-only ok/ops", "Script-only avg USD", "Experimental ok/ops", "Experimental avg USD"],
                 [[LABEL[c], f"{B1[c]['ok']}/{B1[c]['ops']}" if c in B1 else "n/a", f"{B1[c]['avg']:.4f}" if c in B1 else "n/a",
                   f"{B2[c]['ok']}/{B2[c]['ops']}" if c in B2 else "n/a", f"{B2[c]['avg']:.4f}" if c in B2 else "n/a",
                   f"{cat_rows[c]['ok']}/{cat_rows[c]['operations']}", f"{cat_rows[c]['cost_avg_usd']:.4f}"] for c in CATS], "lrrrrrr")
         + f"""

- The baseline pilot also included 4 DOCX reference operations (original DOCX files as the app reads them). They cost {usd_php(DOCX_COST, 3)} for 4 operations against {usd_php(PDF_EQ_COST, 3)} for their PDF equivalents; details in `PILOT_README.md` section 4. Not repeated in the experimental run.
- Pilot-level findings (baseline completed {B_OK} of {B_N} standard operations in its 1-repetition pilot; the experimental pilot repetition completed {E_OK} of {E_N}) are in `PILOT_README.md` section 10. The failed baseline calls still cost money: the baseline pilot's failed attempts cost {usd_php(sum(op_usd(r) for r in base_main if not r['ok']), 3)}.
- Per-operation costs are about equal across configurations; the experimental configuration differs mainly in how many operations succeed.
""")

# 10-11 ---------------------------------------------------------------------------------------
T.append(f"""
## 10. Assumptions, limitations and exclusions

- **Inference only.** No hosting, storage, data integration, monitoring, maintenance, support or development cost is included.
- **Measured versus estimated.** Operation tokens, latency and cost are measured. Campaign bundles and usage scenarios are estimates composed from them. Prompt counts in the benchmark are test design, not CRM behaviour.
- **Prices and exchange rate** are owner-supplied constants; their sources and dates are not recorded. AWS price changes or a different exchange rate change every figure proportionally.
- **Small samples.** 3 repetitions, 5 proposals, 1 persona case. Standard deviations are across 3 to 21 operations; no significance claims are made.
- **Different prompt mixes per proposal.** Horizon has 3 proposal-specific prompts, the others 1, so proposal totals are not like-for-like.
- **Experimental configuration only.** Full-batch figures do not describe the submitted version. The 3,000-token cap lets individual calls cost up to about $0.03 more output than the 1,500 cap would allow; observed averages are unchanged.
- **Synthetic data.** Persona runs use the project's synthetic customers; costs would scale with persona count and prompt size in real data.
- **Single model and region.** Costs apply to `{MODEL}` only; the benchmark ran outside Streamlit (no session token cap or question limit).
- **Failures.** {len(fail_final)} operation(s) failed on the final attempt; none are silently excluded, and the cost of every failed attempt is counted in the incurred totals.
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
""")
(EVAL / "TECHNICAL_COST_REPORT.md").write_text("\n\n".join(str(x).strip("\n") for x in T) + "\n", encoding="utf-8")

# --------------------------------------------------------------------------- #
# Business report
# --------------------------------------------------------------------------- #
mn = min(camp.items(), key=lambda kv: kv[1]["cost"])
mx = max(camp.items(), key=lambda kv: kv[1]["cost"])
P = lambda x, d=2: f"₱{php(x):,.{d}f}"
D = lambda x, d=2: f"${x:,.{d}f}"
no_doc = st.mean(op_usd(o) for o in ops if o["category"] == "summary_form_only" and o["ok"])
S = list(SCENARIOS)
n_prompts_incomplete = len(inc)
B = []
B.append(f"""# Business costing report: AI inference cost of planning a campaign with PAM

**For:** BPI stakeholders. **Basis:** a benchmark of {len(PROPS)} real campaign proposals, 3 repetitions each, on Amazon Bedrock (`{MODEL}`), priced at ${P_IN:.2f} per 1M input tokens and ${P_OUT:.2f} per 1M output tokens, converted at ₱{FX:g} per US dollar (rates supplied by the project owner).

**What these numbers cover.** AWS Bedrock AI inference only. They exclude hosting, storage, data integration, maintenance, support and every other production cost. They are **not** revenue, ROI or conversion claims.

**Which version was measured.** The figures come from an experimental version of PAM (higher answer-length limit and extraction fixes) tested on a separate branch, not from the submitted version. In a one-repetition pilot the submitted version completed {B_OK} of {B_N} standard operations against {E_OK} of {E_N} for the experimental version; cost per completed operation was similar. Full technical detail and all raw data: `TECHNICAL_COST_REPORT.md`.

**Measured versus estimated.** The benchmark tested individual functions, not a full planning session from start to finish. Cost per campaign below is therefore an **estimate built from measured costs of each function**. The number of prompts used in the benchmark was chosen for testing and does not show how many a CRM manager would actually send.
""")
B.append("## 1. Headline metrics (benchmark campaign)\n\n"
         "One benchmark campaign = upload and field extraction + campaign summary with the proposal attached + the benchmark's proposal-based assistant prompts + one persona-generation run.\n\n"
         + table(["Metric", "Value"], [
             ["Unique campaign proposals tested", len(PROPS)],
             ["Average AI prompts per campaign (benchmark design)", f"{ALL_CAMP_PROMPTS:.1f}"],
             ["Average total tokens per campaign", f"{ALL_CAMP_TOK:,.0f}"],
             ["Average AI inference cost per campaign", f"{D(ALL_CAMP_COST, 3)} ({P(ALL_CAMP_COST)})"],
             ["Lowest / highest campaign cost", f"{D(mn[1]['cost'], 3)} ({P(mn[1]['cost'])}) / {D(mx[1]['cost'], 3)} ({P(mx[1]['cost'])})"],
             ["Projected cost, 100 campaigns of this size", f"{D(ALL_CAMP_COST * 100)} ({P(ALL_CAMP_COST * 100, 0)})"],
             ["Projected cost, 1,000 campaigns of this size", f"{D(ALL_CAMP_COST * 1000)} ({P(ALL_CAMP_COST * 1000, 0)})"]], "lr")
         + f"\n\nLowest: {PROPS[mn[0]]['title']}. Highest: {PROPS[mx[0]]['title']}. Cost follows document length (longer proposals send more text to the model); Horizon also had more questions. Based on {len(good)} complete campaign repetitions out of {len(bundles)}{' (the rest are excluded because a function failed to complete; see the technical report)' if inc else ''}.")
B.append("## 2. Campaign-level comparison\n\n" + table(
    ["Campaign", "Number of AI prompts", "Average total tokens", "Average AI cost (USD)", "Average AI cost (PHP)"],
    [[PROPS[p]["title"], c["prompts"], f0(c["tokens"]), f"{c['cost']:.4f}", f"{php(c['cost']):,.2f}"] for p, c in camp.items()]
    + [["**Overall average**", f"**{ALL_CAMP_PROMPTS:.1f}**", f"**{ALL_CAMP_TOK:,.0f}**", f"**{ALL_CAMP_COST:.4f}**", f"**{php(ALL_CAMP_COST):,.2f}**"]], "lrrrr")
    + "\n\nPrompts include the campaign summary and the assistant questions; Horizon was tested with more questions than the other campaigns, which raises its cost. Each figure averages the repetitions of one proposal (repetitions are not separate campaigns).")
B.append(f"""## 3. Representative campaign-planning workflow

1. **Upload** the campaign proposal; PAM reads it and fills in the form (AI field extraction).
2. **Summarize** the campaign with the proposal attached (and regenerate if needed).
3. **Generate personas** for the audience (AI names each persona; the grouping itself costs nothing in AI usage).
4. **Consult the AI assistant** with questions about the proposal (drafts, gaps, eligibility, targeting).

Unit costs (measured averages, proposal attached):

""" + table(["Step", "Cost (USD)", "Cost (PHP)"], [
    ["Upload and field extraction", f"{U['ext']:.4f}", f"{php(U['ext']):.2f}"],
    ["Campaign summary", f"{U['sum']:.4f}", f"{php(U['sum']):.2f}"],
    ["One assistant prompt", f"{U['asst']:.4f}", f"{php(U['asst']):.2f}"],
    ["One persona-generation run (3 personas)", f"{U['pers']:.4f}", f"{php(U['pers']):.2f}"]], "lrr")
    + f"\n\nFor comparison, a campaign summary **without** the proposal attached costs {D(no_doc, 4)} ({P(no_doc)}), about {U['sum'] / no_doc:.0f} times less, because the proposal text is what makes the request large. The two options are alternatives and are never added together.")
B.append("""## 4. Usage scenarios and projections (estimates)

The scenario sizes below are **illustrative assumptions**, not observed behaviour: PAM has not been used by CRM managers in this evaluation, so there is no evidence yet for how many prompts a real campaign involves. They show how cost moves as usage grows; replace them with real usage once the app has logged some.

""" + table(["Scenario", "Uploads", "Summaries (incl. regenerations)", "Persona runs", "Assistant prompts"],
            [[s, *SCENARIOS[s]] for s in S], "lrrrr")
    + "\n\n**Estimated cost per campaign and projection** (average across the five proposals; Bedrock inference only):\n\n"
    + table(["Scenario", "Tokens per campaign", "1 campaign", "100 campaigns", "1,000 campaigns", "Range per campaign (USD)"],
            [[s, f0(scen[s]["tokens"]), f"{D(scen[s]['avg'], 3)} / {P(scen[s]['avg'])}", f"{D(scen[s]['avg'] * 100)} / {P(scen[s]['avg'] * 100, 0)}",
              f"{D(scen[s]['avg'] * 1000)} / {P(scen[s]['avg'] * 1000, 0)}", f"{scen[s]['min']:.3f} to {scen[s]['max']:.3f}"] for s in S], "lrrrrr")
    + "\n\nFor reference, the benchmark campaign itself (section 1) costs "
    + f"{D(ALL_CAMP_COST, 3)} / {P(ALL_CAMP_COST)} per campaign: {D(ALL_CAMP_COST * 100)} for 100 and {D(ALL_CAMP_COST * 1000)} for 1,000.")
B.append(f"""## 5. What this means for feasibility and scalability

- **Cost is small per campaign and moves in proportion to usage.** Across the three scenarios a campaign costs about {P(scen['Light']['avg'], 0)} to {P(scen['Heavy']['avg'], 0)} in AI inference ({D(scen['Light']['avg'], 2)} to {D(scen['Heavy']['avg'], 2)}). Doubling the number of campaigns doubles the bill; there is no step cost in these measurements.
- **The assistant is the main variable.** Each question about an attached proposal costs about {P(U['asst'])}. The heavy scenario's 30 questions account for about {30 * U['asst'] / scen['Heavy']['avg']:.0%} of its cost; the persona run is about {P(U['pers'])} each.
- **Attaching the proposal drives cost.** It costs roughly {U['sum'] / no_doc:.0f} times more than asking without it, but it is what gives the assistant the campaign's facts (in the full batch, {min(w['facts_with'] for w in wv):.0%} to {max(w['facts_with'] for w in wv):.0%} of known facts were kept with the proposal against {min(w['facts_without'] for w in wv):.0%} to {max(w['facts_without'] for w in wv):.0%} without, per campaign). Long proposals cost more: the highest-cost campaign (the longest document) cost about {mx[1]['cost'] / mn[1]['cost']:.1f} times the lowest-cost one (the shortest).
- **Scale.** Even 1,000 heavy campaigns come to about {D(scen['Heavy']['avg'] * 1000, 0)} ({P(scen['Heavy']['avg'] * 1000, 0)}) of inference at these rates. Whether that is acceptable depends on BPI's budget and on the excluded costs. These measurements say nothing about revenue, return on investment or customer conversion; that needs its own measurement.
- **Risks to the estimate:** the usage scenarios are assumptions; prices and the exchange rate can change; only 3 repetitions and 5 proposals were measured; and the figures apply to the experimental version.
""")
B.append(f"""## 6. Headline figures for a slide

1. **About {P(ALL_CAMP_COST, 0)} ({D(ALL_CAMP_COST, 2)})** average AI inference cost for a benchmark campaign (upload, summary, persona run and {ALL_CAMP_PROMPTS:.1f} AI prompts), measured on {len(PROPS)} real proposals.
2. **About {P(scen['Light']['avg'], 0)} to {P(scen['Heavy']['avg'], 0)} per campaign** for light to heavy use (estimate from measured unit costs).
3. **About {P(scen['Moderate']['avg'] * 1000, 0)} ({D(scen['Moderate']['avg'] * 1000, 0)}) for 1,000 campaigns** at moderate use (estimate; Bedrock inference only).
4. **{P(U['asst'])} per assistant question** about an attached proposal; **{P(U['pers'])}** for a full 3-persona run.
5. Measured over **{len(ops)} operations and {exp_calls - no_usage_calls} model calls** across {len(PROPS)} proposals, 3 repetitions; total benchmark spend {D(total_cost_all, 2)} ({P(total_cost_all, 0)}).

*All figures: AWS Bedrock inference only, experimental configuration, ₱{FX:g}/USD, rates supplied by the project owner. Per-campaign and scenario figures are estimates from measured operation costs.*
""")
(EVAL / "BUSINESS_COST_REPORT.md").write_text("\n\n".join(x.strip("\n") for x in B) + "\n", encoding="utf-8")
print("reports written")
