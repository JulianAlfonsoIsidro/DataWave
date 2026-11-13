"""Measure the tokens the AI features use (Part 9 round 3, Requirement 34).

Not part of the app's runtime. Run from the repo root:

    $env:PYTHONPATH="src"; .\\.venv\\Scripts\\python.exe scripts\\measure_ai_tokens.py

What it does:

- Ask Assistant: a realistic chat on three campaign fixtures (form only; form
  plus a 2,000 character document; form plus a 30,000 character document), each
  with summarise, suggest improvements, what is missing, is the eligibility
  clear, draft an SMS, an email and an in-app message, and three follow-ups,
  with the run summary of a real default run attached.
- Persona naming: every persona of a default persona build, named one by one.
- Upload extraction: the three fixtures' documents.

When the four Bedrock variables are set, every call is real and the report says
"measured". Otherwise a stub answers and every figure is labelled "estimated,
not measured" (input: about four characters per token; output: a fixed
estimate per interaction type, listed in the report). Credentials and the
contents of .env are never printed or written. No vendor price is invented.

Writes docs/ai-token-report.md.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "app")]

import pandas as pd  # noqa: E402

from ai import assistant, bedrock, extractor  # noqa: E402
from ai.persona_narrator import BedrockNamer  # noqa: E402

REPORT = ROOT / "docs" / "ai-token-report.md"

FORM = {
    "product_type": "Savings",
    "mechanic": "Top Up",
    "threshold_type": "Top-Up Amount",
    "threshold_value": 530000,
    "reward": "Bonus interest",
    "eligible_segments": ["Affluent-Gold", "Affluent-Preferred", "Mass", "Mid-Market"],
    "min_adb": 0,
    "channels": ["In-app", "Email", "SMS"],
}

_SECTION = (
    "Campaign: Save-Up Bonus. Objective: grow savings balances among existing "
    "clients who keep money at other banks. Offer: a bonus interest rate for "
    "clients who top up at least PHP 530,000 during the promo window. Eligibility: "
    "Affluent-Gold, Affluent-Preferred, Mass and Mid-Market clients with an active "
    "savings account. Channels: in-app banner, email and SMS. Timeline: the promo "
    "runs for eight weeks from the first Monday of next month. Key messages: move "
    "your money home, earn more on what you already save, one simple step to "
    "qualify. Compliance: include the opt-out line on SMS and the full terms link "
    "in email. "
)


def _doc(chars: int) -> str:
    text = ""
    i = 1
    while len(text) < chars:
        text += f"Section {i}. " + _SECTION
        i += 1
    return text[:chars]


FIXTURES = (
    ("Form only", ""),
    ("Form + 2,000 character document", _doc(2_000)),
    ("Form + 30,000 character document", _doc(30_000)),
)

INTERACTIONS = (
    ("Summary", "Summarize This Campaign"),
    ("Improvements", "Suggest improvements to this proposal"),
    ("What is missing", "What's Missing From This Proposal?"),
    ("Eligibility", "Is The Eligibility Clear?"),
    ("SMS draft", "Draft An SMS For This Offer"),
    ("Email draft", "Draft an email for this offer"),
    ("In-app draft", "Draft an in-app message for this offer"),
    ("Follow-up", "Which segment should I act on first, and why?"),
    ("Follow-up", "How many leads will I send, and how many are expected to join?"),
    ("Follow-up", "Make the SMS shorter and add the end date"),
)

# Output estimates used only by the stub (no credentials): tokens per reply.
STUB_OUTPUT = {"Summary": 140, "Improvements": 150, "What is missing": 90, "Eligibility": 90,
               "SMS draft": 110, "Email draft": 150, "In-app draft": 100, "Follow-up": 120,
               "Persona": 160, "Upload": 220}


class StubClient:
    """Answers like Bedrock with estimated usage (only when no credentials)."""

    def __init__(self, kind: str):
        self.kind = kind

    def converse(self, **kwargs):
        sent = kwargs["system"][0]["text"] + kwargs["messages"][0]["content"][0]["text"]
        inp = bedrock.estimate_tokens(sent)
        out = STUB_OUTPUT.get(self.kind, 120)
        if self.kind == "Persona":
            text = json.dumps({"name": "Stub Persona Name", "description": "Stub.", "difference": "Stub.",
                               "actions": [{"channel": "SMS", "angle": "Stub", "message": "Stub"},
                                           {"channel": "Email", "angle": "Stub", "message": "Stub"}]})
        elif self.kind == "Upload":
            text = json.dumps({"fields": {}, "context": {}})
        else:
            text = "Stub answer.\n\n- one\n- two\n- three"
        return {"output": {"message": {"content": [{"text": text}]}},
                "usage": {"inputTokens": inp, "outputTokens": out, "totalTokens": inp + out}}


def _default_run():
    from part1_optin.config import Config as Part1Config
    from webapp_core.model_io import load_model
    from webapp_core.run_promo import PromoSpec, run_promo

    data = {
        "customer_dna": pd.read_csv(ROOT / "data/customer_dna.csv"),
        "adb_monthly": pd.read_csv(ROOT / "data/adb_monthly.csv"),
        "features": pd.read_csv(ROOT / "outputs/features_part2.csv"),
    }
    spec = PromoSpec(promo_id="NEW-001", product_type="Savings", mechanic="TOP_UP",
                     threshold_php=530000.0, reward="Bonus interest",
                     eligible_segments=FORM["eligible_segments"], min_adb=0.0,
                     channels=FORM["channels"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_promo(spec, model=load_model(ROOT / "outputs"), config=Part1Config(), data=data)


def _default_personas():
    from part5_personas.config import Config
    from webapp_core.personas import PersonaRunSpec, run_personas
    import persona_page

    spec = PersonaRunSpec(level="all", clustering_attributes=persona_page.default_attribute_set(), k=3)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_personas(spec, cfg=Config(compute_elbow=False), narration="builtin")


def _stats(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"avg": 0, "min": 0, "max": 0, "p95": 0}
    k = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {"avg": statistics.mean(ordered), "min": ordered[0], "max": ordered[-1], "p95": ordered[k]}


def main() -> int:
    real = bedrock.credentials_available()
    label = "measured" if real else "estimated, not measured"
    print(f"Mode: {label} (credentials present: {real})")

    from webapp_core.run_summary import run_summary

    run = _default_run()
    personas = _default_personas()
    summary = run_summary(run, threshold_label="₱530,000", persona_sets=personas.persona_sets)

    rows: list[dict] = []
    log = Path(tempfile.gettempdir()) / "datawave_token_measure.jsonl"
    for fixture, doc in FIXTURES:
        g = assistant.CampaignGrounding(form=FORM, tags={}, context={}, document_text=doc, run=summary)
        for kind, question in INTERACTIONS:
            client = None if real else StubClient(kind)
            res = assistant.answer(question, g, client=client, log_path=log)
            u = res.usage
            rows.append({"area": "Ask Assistant", "fixture": fixture, "type": kind, "question": question,
                         "mode": res.mode, "input": getattr(u, "input_tokens", None) or 0,
                         "output": getattr(u, "output_tokens", None) or 0,
                         "total": getattr(u, "total_tokens", None) or 0, "seconds": res.seconds})
            print(f"  {fixture[:22]:22s} {kind:16s} {res.mode:7s} {rows[-1]['total']:>6}")
    log.unlink(missing_ok=True)

    upload_rows = []
    for fixture, doc in FIXTURES[1:]:
        client = None if real else StubClient("Upload")
        res = extractor.extract_campaign(doc, client=client)
        u = res.usage
        upload_rows.append({"fixture": fixture, "mode": res.mode,
                            "input": getattr(u, "input_tokens", None) or 0,
                            "output": getattr(u, "output_tokens", None) or 0,
                            "total": getattr(u, "total_tokens", None) or 0})
        print(f"  upload {fixture[:22]:22s} {res.mode:7s} {upload_rows[-1]['total']:>6}")

    namer = BedrockNamer(client=None if real else StubClient("Persona"))
    taken: set[str] = set()
    for ps in personas.persona_sets:
        for p in ps.personas:
            naming = namer.name(p.profile, taken)
            taken.add(naming["name"])
    persona_rows = []
    for r in namer.records:
        u = r["usage"]
        persona_rows.append({"mode": r["mode"], "input": getattr(u, "input_tokens", None) or 0,
                             "output": getattr(u, "output_tokens", None) or 0,
                             "total": getattr(u, "total_tokens", None) or 0})
    print(f"  personas named: {len(persona_rows)}")

    _write_report(label, rows, upload_rows, persona_rows)
    print(f"Wrote {REPORT.relative_to(ROOT)}")
    return 0


def _write_report(label: str, rows, upload_rows, persona_rows) -> None:
    lines = [
        "# AI Token Report",
        "",
        f"Figures are **{label}**. Generated by `scripts/measure_ai_tokens.py` "
        "(Part 9 round 3, Requirement 34). Model id and credentials are not recorded here.",
        "",
        "Bedrock calls that fell back to the built-in rules are counted with the tokens "
        "Bedrock reported (0 when it never answered).",
        "",
        "## Ask Assistant, per interaction",
        "",
        "| Fixture | Interaction | Mode | Input | Output | Total |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['fixture']} | {r['type']}: {r['question']} | {r['mode']} | "
                     f"{r['input']:,} | {r['output']:,} | {r['total']:,} |")
    lines += ["", "## Ask Assistant, by interaction type", "",
              "| Type | Calls | Average total | Minimum | Maximum | 95th percentile |",
              "|---|---:|---:|---:|---:|---:|"]
    types = list(dict.fromkeys(r["type"] for r in rows))
    for t in types + ["All questions"]:
        vals = [r["total"] for r in rows if t == "All questions" or r["type"] == t]
        s = _stats(vals)
        lines.append(f"| {t} | {len(vals)} | {s['avg']:,.0f} | {s['min']:,} | {s['max']:,} | {s['p95']:,} |")
    lines += ["", "## Ask Assistant, by fixture", "",
              "| Fixture | Average input | Average output | Average total |", "|---|---:|---:|---:|"]
    for fixture, _doc_text in FIXTURES:
        mine = [r for r in rows if r["fixture"] == fixture]
        lines.append(f"| {fixture} | {statistics.mean(r['input'] for r in mine):,.0f} | "
                     f"{statistics.mean(r['output'] for r in mine):,.0f} | "
                     f"{statistics.mean(r['total'] for r in mine):,.0f} |")
    ps = _stats([r["total"] for r in persona_rows])
    lines += ["", "## Persona naming", "",
              f"- Personas named: {len(persona_rows)} (one call each); "
              f"Bedrock: {sum(1 for r in persona_rows if r['mode'] == 'Bedrock')}.",
              f"- Per persona: average {ps['avg']:,.0f}, minimum {ps['min']:,}, maximum {ps['max']:,} tokens.",
              f"- Per run of {len(persona_rows)} personas: {sum(r['total'] for r in persona_rows):,} tokens.",
              "", "## Upload extraction", "",
              "| Fixture | Mode | Input | Output | Total |", "|---|---|---:|---:|---:|"]
    for r in upload_rows:
        lines.append(f"| {r['fixture']} | {r['mode']} | {r['input']:,} | {r['output']:,} | {r['total']:,} |")
    avg_q = _stats([r["total"] for r in rows])["avg"]
    lines += ["", "## Growth", "",
              f"Average assistant question: {avg_q:,.0f} tokens. Monthly tokens assume 22 working days. "
              "Fill in the price per million tokens for your model to get a cost.", "",
              "| Users | Questions per user per day | Tokens per day | Tokens per month | Cost per month |",
              "|---:|---:|---:|---:|---|"]
    for users in (10, 50, 200, 1000):
        for per_day in (5, 20):
            day = users * per_day * avg_q
            lines.append(f"| {users:,} | {per_day} | {day:,.0f} | {day * 22:,.0f} | "
                         "tokens per month ÷ 1,000,000 × [price per million tokens] |")
    lines += ["", "Price per million input tokens: [fill in]. Price per million output tokens: [fill in]. "
              "No vendor price is assumed here.", ""]
    if label != "measured":
        lines += ["## Estimator", "",
                  "No credentials were set, so a stub answered. Input = request characters ÷ 4. "
                  "Output per type: " + ", ".join(f"{k} {v}" for k, v in STUB_OUTPUT.items()) + ".", ""]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
