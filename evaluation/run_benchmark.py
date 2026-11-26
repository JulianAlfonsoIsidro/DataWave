"""PAM Bedrock benchmark: token use, cost, latency and output checks.

Hackathon validation only. Standalone: it imports PAM's own functions
(``ai.assistant.answer``, ``ai.extractor``, ``ai.persona_narrator``) and does not
change the app, the Streamlit UI or ``.env``. Credentials, model id and prices
come from ``.env.eval``. Results go to ``evaluation/results/<label>/`` (git-ignored).

Run from the repo root (macOS):

    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --dry-run
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --reps 1 --docx-reference --local-compare --yes
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --reps 3 --yes
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --report-only

Every Bedrock call goes through ``ai.bedrock.converse`` (30 s cap, one attempt,
Demo fallback on failure). A Demo fallback counts as a FAILED operation here.
Token counts are the ones Bedrock returns, never estimates. A run re-uses any
(case, repetition) already stored in ``raw.jsonl`` for the same label.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import shutil
import statistics
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "app"), str(ROOT / "scripts")]
warnings.filterwarnings("ignore")

from ai import assistant, bedrock, extractor, persona_narrator  # noqa: E402
from ai.answer_format import numbers_in, word_count  # noqa: E402
from ai.persona_narrator import BedrockNamer, allowed_numbers, build_aggregate  # noqa: E402
from ai.persona_narrator import estimated_tokens_per_persona  # noqa: E402
from ai.privacy import mask_pii  # noqa: E402

FACTS = json.loads((EVAL / "expected_facts.json").read_text(encoding="utf-8"))
PROPOSALS: dict[str, dict] = FACTS["proposals"]
PROMPTS: dict[str, str] = FACTS["standard_prompts"]

CATEGORIES = (
    "summary_with_doc", "summary_form_only", "persona", "extraction",
    "assistant_low_short", "assistant_medium_medium", "assistant_high_medium",
    "assistant_high_long", "assistant_specific", "assistant_suggested_draft",
)
DOCX_REF_CATEGORIES = ("docx_ref_summary", "docx_ref_extraction")
APP_TIMEOUT_NOTE = f"{bedrock.TIMEOUT_SECONDS} s app timeout, one attempt, no retries"

# --------------------------------------------------------------------------- #
# Environment, prices
# --------------------------------------------------------------------------- #


def load_eval_env() -> dict[str, str]:
    from dotenv import dotenv_values

    path = ROOT / ".env.eval"
    if not path.exists():
        return {}
    return {k: (v or "").strip() for k, v in dotenv_values(path).items()}


def prices(env: dict[str, str]) -> dict[str, Any]:
    """Per-1M-token prices (USD) and an optional USD to PHP rate, all from .env.eval."""

    def num(*keys: str) -> float | None:
        for key in keys:
            try:
                return float(env.get(key, ""))
            except ValueError:
                continue
        return None

    return {"input": num("BEDROCK_INPUT_PRICE_PER_MILLION", "PRICE_INPUT_PER_1M"),
            "output": num("BEDROCK_OUTPUT_PRICE_PER_MILLION", "PRICE_OUTPUT_PER_1M"),
            "currency": env.get("PRICE_CURRENCY") or "USD", "usd_to_php": num("USD_TO_PHP")}


def cost(inp: int | None, out: int | None, pr: dict[str, Any]) -> tuple[float | None, float | None]:
    if pr["input"] is None or pr["output"] is None or inp is None or out is None:
        return None, None
    return inp / 1e6 * pr["input"], out / 1e6 * pr["output"]


# --------------------------------------------------------------------------- #
# Documents (local extraction, no Bedrock)
# --------------------------------------------------------------------------- #

_DOC_CACHE: dict[tuple[str, str], str] = {}


def doc_path(key: str, variant: str) -> Path:
    rel = PROPOSALS[key]["docx"] if variant == "docx" else PROPOSALS[key]["pdf"]
    return ROOT / rel


def doc_text(key: str, variant: str = "pdf") -> str:
    """Text as the app's upload reads it, then masked like the app does."""
    if (key, variant) not in _DOC_CACHE:
        path = doc_path(key, variant)
        raw = extractor.extract_text(path.read_bytes(), path.name)
        _DOC_CACHE[(key, variant)] = mask_pii(raw).text
    return _DOC_CACHE[(key, variant)]


def inventory_rows() -> list[dict]:
    rows = []
    for key in PROPOSALS:
        for variant in ("pdf", "docx"):
            if variant == "docx" and not PROPOSALS[key]["docx"]:
                continue
            path = doc_path(key, variant)
            row = {"proposal": key, "file": path.name, "format": path.suffix[1:], "bytes": None,
                   "chars": None, "words": None, "est_tokens": None, "over_30k_extraction_cap": None,
                   "chars_cut_for_extraction": None, "pii_items_masked": None, "ticked": None,
                   "unticked": None, "status": "ok"}
            try:
                row["bytes"] = path.stat().st_size
                raw = extractor.extract_text(path.read_bytes(), path.name)
                row.update(chars=len(raw), words=len(raw.split()), est_tokens=bedrock.estimate_tokens(raw),
                           over_30k_extraction_cap=len(raw) > extractor.MAX_PROMPT_CHARS,
                           chars_cut_for_extraction=max(0, len(raw) - extractor.MAX_PROMPT_CHARS),
                           pii_items_masked=mask_pii(raw).total, ticked=raw.count("☒"),
                           unticked=raw.count("☐"))
            except Exception as exc:  # noqa: BLE001 - flag, never stop
                row["status"] = f"failed: {type(exc).__name__}"
            rows.append(row)
    return rows


def _squash(text: str) -> str:
    return re.sub(r"[\s\u200b]+", "", text).lower()


def local_docx_pdf_rows() -> list[dict]:
    """Local DOCX vs converted PDF comparison. No Bedrock."""
    rows = []
    for key, checks in FACTS["local_docx_pdf_checks"].items():
        for variant in ("docx", "pdf"):
            path = doc_path(key, variant)
            text = extractor.extract_text(path.read_bytes(), path.name)
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            long_lines = [ln for ln in lines if len(ln) > 60]
            sq = _squash(text)
            hits = [c for c in checks if _squash(c) in sq]
            rows.append({
                "proposal": key, "variant": variant, "file": path.name, "chars": len(text),
                "est_tokens": bedrock.estimate_tokens(text), "lines": len(lines),
                "unique_line_pct": round(100 * len(set(lines)) / max(1, len(lines))),
                "repeated_long_lines_pct": round(100 * (1 - len(set(long_lines)) / max(1, len(long_lines)))),
                "ticked_boxes": text.count("☒"), "unticked_boxes": text.count("☐"),
                "facts_checked": len(checks), "facts_found": len(hits),
                "facts_missing": "; ".join(c for c in checks if c not in hits),
                "over_30k_extraction_cap": len(text) > extractor.MAX_PROMPT_CHARS,
            })
    return rows


# --------------------------------------------------------------------------- #
# Dry-run client (no network)
# --------------------------------------------------------------------------- #


class DryClient:
    """Stands in for Bedrock in --dry-run: canned text, estimated usage."""

    def __init__(self) -> None:
        self.n = 0

    def converse(self, **kw: Any) -> dict:
        system = kw["system"][0]["text"]
        user = kw["messages"][0]["content"][0]["text"]
        inp = bedrock.estimate_tokens(system + user)
        if system.startswith("You extract campaign"):
            text, out = json.dumps({"fields": {"channels": ["Email"]}, "context": {}}), 60
        elif system.startswith("You name customer personas"):
            self.n += 1
            letter = chr(64 + (self.n - 1) % 26 + 1)
            text = json.dumps({"name": f"Dry Run Persona {letter}", "description": "A dry run description.",
                               "difference": "A dry run difference.",
                               "actions": [{"channel": "Email", "angle": "Angle", "message": "Message"},
                                           {"channel": "SMS", "angle": "Angle", "message": "Message"}]})
            out = 80
        else:
            text, out = "This is a dry run answer.\n\n- Point one\n- Point two\n- Point three", 40
        return {"output": {"message": {"content": [{"text": text}]}}, "stopReason": "end_turn",
                "usage": {"inputTokens": inp, "outputTokens": out, "totalTokens": inp + out}}


class StopReasonClient:
    """Wraps the Bedrock client to record each call's stopReason (the app's converse() does not expose it).

    Benchmark assumption: a reply that stopped at ``max_tokens`` counts as a FAILED operation,
    even if some text came back. App code is not changed.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.stops: list[str | None] = []

    def converse(self, **kw: Any) -> dict:
        resp = self.inner.converse(**kw)
        self.stops.append(resp.get("stopReason") if isinstance(resp, dict) else None)
        return resp


def apply_stop_reasons(op: dict, stops: list[str | None]) -> None:
    invs = op.get("invocations") or []
    if len(stops) != len(invs):
        return
    for inv, stop in zip(invs, stops):
        inv["stop_reason"] = stop
        if stop == "max_tokens":
            inv["mode"], inv["reason"] = "Truncated", "max_tokens"
            op["ok"] = False
            op.setdefault("quality", {})["truncated_at_max_tokens"] = True


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    proposal: str
    kind: str            # assistant | extraction | persona
    prompt: str = ""
    level: str = ""      # low | medium | doc | high
    variant: str = "pdf"  # pdf | docx

    @property
    def source_file(self) -> str:
        if self.kind == "persona":
            return ""
        path = doc_path(self.proposal, self.variant)
        return path.name if self.level in ("doc", "high") or self.kind == "extraction" else ""


def build_cases(keys: list[str], cats: list[str], docx_ref: bool) -> list[Case]:
    out: list[Case] = []
    for cat in cats:
        if cat == "persona":
            out.append(Case("persona:default", "persona", "", "persona"))
            continue
        for key in keys:
            if cat == "summary_with_doc":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["summary"], "doc"))
            elif cat == "summary_form_only":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["summary"], "low"))
            elif cat == "extraction":
                out.append(Case(f"{cat}:{key}", cat, key, "extraction"))
            elif cat == "assistant_low_short":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["short"], "low"))
            elif cat == "assistant_medium_medium":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["medium_gaps"], "medium"))
            elif cat == "assistant_high_medium":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["medium_draft"], "high"))
            elif cat == "assistant_high_long":
                out.append(Case(f"{cat}:{key}", cat, key, "assistant", PROMPTS["long"], "high"))
            elif cat == "assistant_suggested_draft":
                # The app's own suggested question, FORWARD only (the proposal it was first seen working on).
                if key == "forward":
                    draft_q = next(q for q in assistant.SUGGESTED_QUESTIONS if q.startswith("Draft"))
                    out.append(Case(f"{cat}:{key}", cat, key, "assistant", draft_q, "high"))
            elif cat == "assistant_specific":
                for sp in PROPOSALS[key]["specific"]:
                    out.append(Case(f"{cat}:{key}:{sp['id']}", cat, key, "assistant", sp["prompt"], "high"))
    if docx_ref:
        for key in keys:
            if PROPOSALS[key]["docx"]:
                out.append(Case(f"docx_ref_summary:{key}", "docx_ref_summary", key, "assistant",
                                PROMPTS["summary"], "doc", "docx"))
                out.append(Case(f"docx_ref_extraction:{key}", "docx_ref_extraction", key, "extraction",
                                variant="docx"))
    return out


_FORWARD_RUN: dict[str, Any] = {}


def forward_run_summary(key: str) -> dict | None:
    """PAM run summary for FORWARD only (the one proposal with a real threshold)."""
    rf = PROPOSALS[key].get("run_form")
    if not rf:
        return None
    if key in _FORWARD_RUN:
        return _FORWARD_RUN[key]
    summary = None
    try:
        import pandas as pd
        from part1_optin.config import Config as P1
        from webapp_core.model_io import load_model
        from webapp_core.run_promo import PromoSpec, run_promo
        from webapp_core.run_summary import run_summary
        from webapp_core.threshold import ThresholdType

        data = {"customer_dna": pd.read_csv(ROOT / "data/customer_dna.csv"),
                "adb_monthly": pd.read_csv(ROOT / "data/adb_monthly.csv"),
                "features": pd.read_csv(ROOT / "outputs/features_part2.csv")}
        spec = PromoSpec(promo_id="NEW-001", product_type=rf["product_type"], mechanic=rf["mechanic"],
                         threshold_php=float(rf["threshold_php"]), reward="",
                         eligible_segments=rf["eligible_segments"], min_adb=0.0, channels=rf["channels"],
                         threshold_type=ThresholdType(rf["threshold_type"]))
        result = run_promo(spec, model=load_model(ROOT / "outputs"), config=P1(), data=data)
        summary = run_summary(result, threshold_label=rf["threshold_label"])
    except Exception as exc:  # noqa: BLE001
        print(f"  [note] run summary for {key} unavailable: {type(exc).__name__}")
    _FORWARD_RUN[key] = summary
    return summary


def tags_for(form: dict) -> dict[str, str]:
    return {name: (extractor.FOUND if form.get(name) not in (None, "", [], ()) else extractor.NEEDS_INPUT)
            for name in extractor.CAMPAIGN_FIELDS}


def grounding_for(case: Case) -> assistant.CampaignGrounding:
    p = PROPOSALS[case.proposal]
    form = dict(p["form"])
    ctx = dict(p["context"])
    if case.level == "low":
        return assistant.CampaignGrounding(form, {}, {}, "", None)
    if case.level == "medium":
        return assistant.CampaignGrounding(form, {}, ctx, "", None)
    text = doc_text(case.proposal, case.variant)
    if case.level == "doc":
        return assistant.CampaignGrounding(form, tags_for(form), {}, text, None)
    return assistant.CampaignGrounding(form, tags_for(form), ctx, text, forward_run_summary(case.proposal))


_PERSONA_SETS: list = []


def persona_sets() -> list:
    if not _PERSONA_SETS:
        import measure_ai_tokens as m

        _PERSONA_SETS.extend(m._default_personas().persona_sets)
    return _PERSONA_SETS


def persona_list() -> list:
    return [p for ps in persona_sets() for p in ps.personas]


def estimate_input(case: Case) -> int:
    if case.kind == "persona":
        return sum(estimated_tokens_per_persona(p.profile) for p in persona_list())
    if case.kind == "extraction":
        return extractor.estimated_input_tokens(doc_text(case.proposal, case.variant))
    return assistant.estimated_input_tokens(case.prompt, grounding_for(case))


def invocations_for(case: Case) -> int:
    return len(persona_list()) if case.kind == "persona" else 1


# --------------------------------------------------------------------------- #
# Quality checks (deterministic, local)
# --------------------------------------------------------------------------- #

_SEG_RX = {"Affluent-Gold": "gold", "Affluent-Preferred": "preferred", "Mass": "mass", "Mid-Market": "mid-market"}
_CH_RX = {"SMS": "sms", "Email": "email|edm", "In-app": "in-app|in app"}


def norm_text(text: str) -> str:
    t = (text or "").lower().replace("₱", "").replace("–", "-").replace("—", "-")
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    return re.sub(r"\bphp\s*", "", t)


def hit(rxs: list[str], nt: str) -> bool:
    return any(re.search(rx, nt) for rx in rxs)


def layout(text: str) -> dict:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    bullets = sum(1 for ln in lines if ln.lstrip().startswith("- "))
    lead = bool(lines) and not lines[0].lstrip().startswith(("- ", "> "))
    words = word_count(text or "")
    return {"words": words, "bullets": bullets, "layout_ok": bool(lead and words <= 150 and bullets >= 1)}


def assistant_quality(case: Case, ans: assistant.AssistantAnswer) -> dict:
    p = PROPOSALS[case.proposal]
    nt = norm_text(ans.text)
    q: dict[str, Any] = {"routed_local": ans.mode == "Local", "unsupported_numbers": list(ans.flagged)}
    q.update(layout(ans.text))
    doc_in_prompt = case.level in ("doc", "high")
    if doc_in_prompt and case.category in ("summary_with_doc", "docx_ref_summary", "assistant_high_long"):
        hits = [(f["id"], hit(f["any"], nt)) for f in p["doc_facts"]]
        q["facts_total"], q["facts_hit"] = len(hits), sum(h for _i, h in hits)
        q["facts_rate"] = round(q["facts_hit"] / len(hits), 3)
        q["facts_missed"] = [i for i, h in hits if not h]
    if not doc_in_prompt:
        q["forbidden_hits"] = [n for n in p["doc_only_numbers"] if re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", nt)]
    if case.prompt in (PROMPTS["short"], PROMPTS["summary"]):
        segs = p["form"].get("eligible_segments", [])
        chans = p["form"].get("channels", [])
        want = [_SEG_RX[s] for s in segs] + [_CH_RX[c] for c in chans]
        got = [w for w in want if re.search(w, nt)]
        q["form_facts_rate"] = round(len(got) / len(want), 3) if want else None
    if case.category == "assistant_suggested_draft":
        q["flags_sms_not_ticked"] = bool(re.search(
            r"sms.{0,90}(not (ticked|selected|listed|in scope|included)|isn't|outside|unticked)|(not|isn't).{0,70}sms", nt))
    if case.category == "assistant_specific":
        spec = next(s for s in p["specific"] if s["id"] == case.case_id.split(":")[-1])
        g = [hit(grp, nt) for grp in spec["groups"]]
        q["group_rate"] = round(sum(g) / len(g), 3)
        q["groups_missed"] = [spec["groups"][i][0] for i, ok in enumerate(g) if not ok]
    if case.prompt in (PROMPTS["medium_gaps"], PROMPTS["long"]) and doc_in_prompt or case.category == "assistant_medium_medium":
        issues = {}
        for issue in p["known_issues"]:
            issues[issue["id"]] = all(hit(grp, nt) for grp in issue["all_of"])
        if issues:
            q["known_issues_detected"] = issues
    return q


def extraction_quality(case: Case, res: extractor.ExtractionResult) -> dict:
    exp = PROPOSALS[case.proposal]["expected_extraction"]
    f = res.fields
    detail, scored, matched = {}, 0, 0
    for k in ("product_type", "threshold_type", "threshold_value", "eligible_segments", "channels"):
        if k not in exp:
            continue
        scored += 1
        got = f.get(k)
        ok = (set(got) == set(exp[k])) if isinstance(exp[k], list) and isinstance(got, list) else got == exp[k]
        detail[k] = "match" if ok else ("missing" if got is None else f"mismatch:{got}")
        matched += ok
    extra = [k for k in exp.get("absent", []) if k in f]
    return {"accuracy": round(matched / scored, 3) if scored else None, "fields_scored": scored,
            "fields_matched": matched, "detail": detail, "extra_fields_returned": extra,
            "ambiguous_values": {k: f.get(k) for k in exp.get("ambiguous", [])},
            "mechanic": f.get("mechanic"), "reward": f.get("reward"), "fields_found": sorted(f),
            "context_keys_filled": sorted(k for k, v in res.context.items() if v)}


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


def _inv(mode: str, usage: Any, seconds: float, reason: str, idx: int = 1, text_len: int = 0) -> dict:
    return {"inv_idx": idx, "mode": mode, "reason": reason or "",
            "input_tokens": getattr(usage, "input_tokens", None), "output_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None), "seconds": round(float(seconds or 0), 2),
            "output_chars": text_len}


def run_case(case: Case, env: dict, client: Any) -> dict:
    """Run one operation. Never raises: failures are recorded."""
    op: dict[str, Any] = {"case_id": case.case_id, "category": case.category, "proposal": case.proposal,
                          "kind": case.kind, "level": case.level, "variant": case.variant,
                          "source_file": case.source_file, "prompt": case.prompt}
    op["output_cap"] = {"assistant": assistant.MAX_REPLY_TOKENS, "extraction": extractor.MAX_REPLY_TOKENS,
                        "persona": persona_narrator.MAX_REPLY_TOKENS}[case.kind]
    if isinstance(client, StopReasonClient):
        client.stops.clear()
    try:
        if case.kind == "assistant":
            g = grounding_for(case)
            payload = assistant.build_payload(case.prompt, g)
            op["input_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
            ans = assistant.answer(case.prompt, g, client=client, env=env,
                                   log_path=EVAL / "results" / "_assistant_log.jsonl")
            inv = _inv(ans.mode, ans.usage, ans.seconds, ans.reason, text_len=len(ans.text))
            op["invocations"] = [inv] if ans.mode != "Local" else []
            op["ok"] = ans.mode == "Bedrock"
            op["response"] = ans.text
            op["quality"] = assistant_quality(case, ans)
        elif case.kind == "extraction":
            text = doc_text(case.proposal, case.variant)
            op["input_hash"] = hashlib.sha256(text[: extractor.MAX_PROMPT_CHARS].encode()).hexdigest()[:12]
            res = extractor.extract_campaign(text, client=client, env=env)
            op["invocations"] = [_inv(res.mode, res.usage, res.seconds, res.reason)]
            op["ok"] = res.mode == "Bedrock"
            op["response"] = json.dumps({"fields": res.fields, "tags": res.tags, "context": res.context},
                                        ensure_ascii=False, indent=1)
            op["quality"] = extraction_quality(case, res) if op["ok"] else {"note": "Demo fallback, not scored"}
        else:
            namer = BedrockNamer(client=client, env=env)
            taken: set[str] = set()
            invs, namings, grounded, ok_all = [], [], [], True
            op["input_hash"] = f"personas{len(persona_list())}"
            for i, p in enumerate(persona_list(), 1):
                agg = build_aggregate(p.profile)
                naming = namer.name(p.profile, taken)
                taken.add(naming["name"])
                rec = namer.records[-1]
                invs.append(_inv(rec["mode"], rec["usage"], rec["seconds"], rec["reason"], i,
                                 len(json.dumps(naming, ensure_ascii=False))))
                ok = rec["mode"] == "Bedrock"
                ok_all &= ok
                act_ok = numbers_in(" ".join(naming["actions"])) <= allowed_numbers(agg)
                grounded.append(act_ok)
                namings.append({"persona": i, "size": agg.size, "share_pct": agg.share_pct, "source": rec["mode"],
                                "from_mock": not ok, "reason": rec["reason"], "naming": naming,
                                "action_numbers_grounded": act_ok})
            op["invocations"], op["ok"] = invs, ok_all
            op["response"] = json.dumps(namings, ensure_ascii=False, indent=1)
            op["quality"] = {"bedrock_valid_personas": sum(i["mode"] == "Bedrock" for i in invs),
                             "personas": len(invs), "action_numbers_grounded": sum(grounded),
                             "names": [n["naming"]["name"] for n in namings],
                             "per_persona_tokens_basis": "measured: one request per persona"}
    except Exception as exc:  # noqa: BLE001 - one failure never stops the batch
        op.setdefault("invocations", [])
        op["ok"], op["error"] = False, type(exc).__name__
        op.setdefault("quality", {})
    if isinstance(client, StopReasonClient):
        apply_stop_reasons(op, list(client.stops))
    return op


def raw_path(label: str) -> Path:
    return EVAL / "results" / label / "raw.jsonl"


def read_raw(label: str) -> list[dict]:
    path = raw_path(label)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def append_raw(label: str, record: dict) -> None:
    path = raw_path(label)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


def mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.mean(vals), 4) if vals else None


def fmt(v: Any, nd: int = 0) -> str:
    if v is None or v == "":
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{nd}f}"
    return f"{v:,}" if isinstance(v, int) else str(v)


def final_ops(raw: list[dict]) -> list[dict]:
    best: dict[tuple[str, int], dict] = {}
    for r in raw:
        k = (r["case_id"], r["rep"])
        if k not in best or r["attempt"] > best[k]["attempt"]:
            best[k] = r
    return list(best.values())


def op_tokens(op: dict) -> tuple[int | None, int | None, int | None]:
    invs = [i for i in op.get("invocations", []) if i.get("total_tokens") is not None]
    if not invs:
        return None, None, None
    return (sum(i["input_tokens"] or 0 for i in invs), sum(i["output_tokens"] or 0 for i in invs),
            sum(i["total_tokens"] or 0 for i in invs))


def op_cost(op: dict, pr: dict) -> float | None:
    tin, tout, _ = op_tokens(op)
    ci, co = cost(tin, tout, pr)
    return None if ci is None else ci + co


def op_seconds(op: dict) -> float:
    return round(sum(i.get("seconds", 0) for i in op.get("invocations", [])), 2)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9₱.%]+", (text or "").lower()))


def _jac(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def _pair_mean(items: list, fn) -> float | None:
    pairs = list(itertools.combinations(items, 2))
    return round(statistics.mean(fn(a, b) for a, b in pairs), 3) if pairs else None


def consistency(ops: list[dict]) -> dict[str, dict]:
    """Per case_id similarity across repetitions (successful runs only)."""
    out: dict[str, dict] = {}
    by_case: dict[str, list[dict]] = {}
    for op in ops:
        if op.get("ok"):
            by_case.setdefault(op["case_id"], []).append(op)
    for cid, group in by_case.items():
        if len(group) < 2:
            continue
        kind = group[0]["kind"]
        if kind == "assistant":
            texts = [g["response"] for g in group]
            out[cid] = {"text_similarity": _pair_mean(texts, lambda a, b: _jac(_words(a), _words(b))),
                        "number_overlap": _pair_mean(texts, lambda a, b: _jac(numbers_in(a), numbers_in(b)))}
        elif kind == "extraction":
            flat = [{(k, json.dumps(v, sort_keys=True)) for k, v in json.loads(g["response"])["fields"].items()}
                    for g in group]
            out[cid] = {"field_agreement": _pair_mean(flat, _jac)}
        else:
            names = [{n.casefold() for n in g["quality"].get("names", [])} for g in group]
            out[cid] = {"name_overlap": _pair_mean(names, _jac)}
    return out


def doc_facts_rate(key: str, text: str) -> float:
    nt = norm_text(text)
    facts = PROPOSALS[key]["doc_facts"]
    return round(sum(hit(f["any"], nt) for f in facts) / len(facts), 3)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def detailed_rows(raw: list[dict], pr: dict) -> list[dict]:
    finals = {(r["case_id"], r["rep"]): r["attempt"] for r in final_ops(raw)}
    rows = []
    for r in sorted(raw, key=lambda x: (x["case_id"], x["rep"], x["attempt"])):
        q = r.get("quality", {})
        base = {
            "category": r["category"], "case_id": r["case_id"], "repetition": r["rep"], "attempt": r["attempt"],
            "is_final_attempt": r["attempt"] == finals[(r["case_id"], r["rep"])],
            "proposal": r["proposal"], "source_file": r["source_file"], "doc_variant": r["variant"] if r["source_file"] else "",
            "context_level": r["level"], "model_id": r["model_id"], "prompt": r["prompt"], "input_hash": r.get("input_hash", ""),
            "operation_ok": r["ok"], "error": r.get("error", ""), "output_cap": r.get("output_cap"),
            "facts_rate": q.get("facts_rate"), "form_facts_rate": q.get("form_facts_rate"), "group_rate": q.get("group_rate"),
            "unsupported_numbers": ", ".join(q.get("unsupported_numbers", [])) if "unsupported_numbers" in q else "",
            "forbidden_hits": ", ".join(q.get("forbidden_hits", [])) if "forbidden_hits" in q else "",
            "layout_ok": q.get("layout_ok"), "words": q.get("words"),
            "extraction_accuracy": q.get("accuracy"), "extraction_extra_fields": ", ".join(q.get("extra_fields_returned", [])) if "extra_fields_returned" in q else "",
            "known_issues_detected": json.dumps(q["known_issues_detected"]) if "known_issues_detected" in q else "",
            "quality_json": json.dumps(q, ensure_ascii=False, default=str),
        }
        invs = r.get("invocations") or [None]
        for inv in invs:
            row = dict(base)
            if inv is None:
                row.update(invocation=0, status="failed", reason=r.get("error") or "routed_locally_no_call")
            else:
                ci, co = cost(inv["input_tokens"], inv["output_tokens"], pr)
                row.update(invocation=inv["inv_idx"], status="ok" if inv["mode"] == "Bedrock" else "failed",
                           reason=inv["reason"], input_tokens=inv["input_tokens"], output_tokens=inv["output_tokens"],
                           total_tokens=inv["total_tokens"], latency_s=inv["seconds"], output_chars=inv["output_chars"],
                           stop_reason=inv.get("stop_reason"),
                           cost_input=ci, cost_output=co, cost_total=None if ci is None else ci + co)
            rows.append(row)
    return rows


def summary_rows(ops: list[dict], pr: dict) -> list[dict]:
    cons = consistency(ops)
    rows = []
    for cat in dict.fromkeys(o["category"] for o in ops):
        g = [o for o in ops if o["category"] == cat]
        toks = [op_tokens(o) for o in g if op_tokens(o)[0] is not None]
        tin, tout, ttot = ([t[i] for t in toks] for i in range(3))
        ok = [o for o in g if o["ok"]]
        costs = [op_cost(o, pr) for o in g]
        costs = [c for c in costs if c is not None]
        n_inv = [len(o.get("invocations", [])) for o in g]
        per_op = mean(costs)
        qs = [o.get("quality", {}) for o in ok]
        fails: dict[str, int] = {}
        for o in g:
            if not o["ok"]:
                reasons = {i["reason"] for i in o.get("invocations", []) if i["mode"] != "Bedrock"} or {o.get("error", "unknown")}
                for rs in reasons:
                    fails[rs or "unknown"] = fails.get(rs or "unknown", 0) + 1
        cs = [cons[o["case_id"]] for o in g if o["case_id"] in cons]
        seen = set()
        cs = [c for o in g for c in [cons.get(o["case_id"])] if c and not (o["case_id"] in seen or seen.add(o["case_id"]))]
        row = {
            "category": cat, "operations": len(g), "ok_operations": len(ok),
            "success_rate": round(len(ok) / len(g), 3), "failure_reasons": json.dumps(fails),
            "invocations": sum(n_inv), "avg_invocations_per_op": mean(n_inv),
            "avg_input_tokens": mean(tin), "min_input_tokens": min(tin) if tin else None, "max_input_tokens": max(tin) if tin else None,
            "avg_output_tokens": mean(tout), "min_output_tokens": min(tout) if tout else None, "max_output_tokens": max(tout) if tout else None,
            "avg_total_tokens": mean(ttot), "min_total_tokens": min(ttot) if ttot else None, "max_total_tokens": max(ttot) if ttot else None,
            "avg_latency_s_per_op": mean([op_seconds(o) for o in g]), "max_latency_s_per_op": max((op_seconds(o) for o in g), default=None),
            "avg_cost_per_op": per_op,
            "avg_cost_per_invocation": round(sum(costs) / max(1, sum(n_inv)), 6) if costs else None,
            "projected_cost_100_ops": None if per_op is None else round(per_op * 100, 4),
            "projected_cost_1000_ops": None if per_op is None else round(per_op * 1000, 4),
            "currency": pr["currency"],
            "avg_cost_per_op_php": None if per_op is None or not pr["usd_to_php"] else round(per_op * pr["usd_to_php"], 4),
            "projected_cost_100_ops_php": None if per_op is None or not pr["usd_to_php"] else round(per_op * 100 * pr["usd_to_php"], 2),
            "projected_cost_1000_ops_php": None if per_op is None or not pr["usd_to_php"] else round(per_op * 1000 * pr["usd_to_php"], 2),
            "facts_rate_mean": mean([q.get("facts_rate") for q in qs]),
            "form_facts_rate_mean": mean([q.get("form_facts_rate") for q in qs]),
            "group_rate_mean": mean([q.get("group_rate") for q in qs]),
            "unsupported_numbers_mean": mean([len(q["unsupported_numbers"]) for q in qs if "unsupported_numbers" in q]),
            "forbidden_hits_total": sum(len(q.get("forbidden_hits", [])) for q in qs),
            "layout_ok_rate": mean([1.0 if q["layout_ok"] else 0.0 for q in qs if "layout_ok" in q]),
            "extraction_accuracy_mean": mean([q.get("accuracy") for q in qs]),
            "extraction_extra_fields_mean": mean([len(q["extra_fields_returned"]) for q in qs if "extra_fields_returned" in q]),
            "persona_valid_rate": mean([q["bedrock_valid_personas"] / q["personas"] for q in qs if "personas" in q]),
            "persona_actions_grounded_rate": mean([q["action_numbers_grounded"] / q["personas"] for q in qs if "personas" in q]),
            "consistency_text_similarity": mean([c.get("text_similarity") for c in cs]),
            "consistency_number_overlap": mean([c.get("number_overlap") for c in cs]),
            "consistency_field_agreement": mean([c.get("field_agreement") for c in cs]),
            "consistency_persona_name_overlap": mean([c.get("name_overlap") for c in cs]),
        }
        rows.append(row)
    return rows


def comparison_rows(ops: list[dict], pr: dict) -> list[dict]:
    rows = []
    for key in PROPOSALS:
        w = [o for o in ops if o["category"] == "summary_with_doc" and o["proposal"] == key]
        f = [o for o in ops if o["category"] == "summary_form_only" and o["proposal"] == key]
        if not w and not f:
            continue

        def agg(g: list[dict], with_doc: bool) -> dict:
            ok = [o for o in g if o["ok"]]
            toks = [op_tokens(o) for o in g if op_tokens(o)[0] is not None]
            cst = [c for c in (op_cost(o, pr) for o in g) if c is not None]
            return {"runs": len(g), "ok": len(ok), "avg_input": mean([t[0] for t in toks]), "avg_output": mean([t[1] for t in toks]),
                    "avg_latency_s": mean([op_seconds(o) for o in g]), "avg_cost": mean(cst),
                    "doc_facts_rate": mean([doc_facts_rate(key, o["response"]) for o in ok]),
                    "unsupported_numbers": mean([len(o["quality"].get("unsupported_numbers", [])) for o in ok]),
                    "forbidden_doc_numbers": sum(len(o["quality"].get("forbidden_hits", [])) for o in ok),
                    "form_facts_rate": mean([o["quality"].get("form_facts_rate") for o in ok])}
        a, b = agg(w, True), agg(f, False)
        row = {"proposal": key, "title": PROPOSALS[key]["title"]}
        row.update({f"with_doc_{k}": v for k, v in a.items()})
        row.update({f"form_only_{k}": v for k, v in b.items()})
        if a["avg_input"] and b["avg_input"]:
            row["input_token_multiple"] = round(a["avg_input"] / b["avg_input"], 1)
        rows.append(row)
    return rows


def docx_reference_rows(ops: list[dict], pr: dict) -> list[dict]:
    rows = []
    for key in PROPOSALS:
        if not PROPOSALS[key]["docx"]:
            continue
        for task, dcat, pcat in (("summary", "docx_ref_summary", "summary_with_doc"), ("extraction", "docx_ref_extraction", "extraction")):
            for variant, cat in (("docx_as_app_reads_it", dcat), ("pdf_workaround", pcat)):
                g = [o for o in ops if o["category"] == cat and o["proposal"] == key and o["rep"] == 1]
                if not g:
                    continue
                o = g[0]
                tin, tout, ttot = op_tokens(o)
                q = o.get("quality", {})
                rows.append({"proposal": key, "task": task, "variant": variant, "ok": o["ok"], "input_tokens": tin,
                             "output_tokens": tout, "total_tokens": ttot, "latency_s": op_seconds(o),
                             "cost": op_cost(o, pr), "facts_rate": q.get("facts_rate"), "extraction_accuracy": q.get("accuracy"),
                             "unsupported_numbers": len(q.get("unsupported_numbers", [])) if "unsupported_numbers" in q else None,
                             "reason": ", ".join(i["reason"] for i in o.get("invocations", []) if i["reason"])})
    return rows


def write_reports(label: str, pr: dict) -> None:
    out = EVAL / "results" / label
    raw = read_raw(label)
    if not raw:
        print("No raw results to report.")
        return
    ops = final_ops(raw)
    write_csv(out / "results_detailed.csv", detailed_rows(raw, pr))
    summ = summary_rows(ops, pr)
    write_csv(out / "results_summary.csv", summ)
    write_csv(out / "comparison_with_vs_without_proposal.csv", comparison_rows(ops, pr))
    write_csv(out / "docx_vs_pdf_bedrock.csv", docx_reference_rows(ops, pr))
    with (out / "responses_for_review.md").open("w", encoding="utf-8") as fh:
        fh.write(f"# Generated responses for manual review ({label})\n\nSubjective criteria (actionability, plausibility) are judged from this file. "
                 "Persona results use synthetic data: they show consistency and groundedness, not real-world accuracy.\n\n")
        for o in sorted(raw, key=lambda x: (x["case_id"], x["rep"], x["attempt"])):
            tin, tout, ttot = op_tokens(o)
            fh.write(f"## {o['case_id']} | rep {o['rep']} attempt {o['attempt']} | ok={o['ok']} | tokens in/out/total {tin}/{tout}/{ttot}\n\n")
            if o["prompt"]:
                fh.write(f"**Prompt:** {o['prompt']}\n\n")
            fh.write(f"**Quality checks:** `{json.dumps(o.get('quality', {}), ensure_ascii=False, default=str)[:900]}`\n\n")
            fh.write("```\n" + (o.get("response") or f"(no response; error={o.get('error', '')})") + "\n```\n\n")
    cur = pr["currency"]
    with (out / "presentation_summary.md").open("w", encoding="utf-8") as fh:
        dry = raw[-1]["model_id"] == "dry-run"
        price_txt = (f"Cost in {cur} per 1M tokens from `.env.eval`: input {pr['input']}, output {pr['output']}"
                     + (f"; PHP shown at {pr['usd_to_php']} per USD (your rate)." if pr["usd_to_php"] else ".")
                     if pr["input"] is not None and pr["output"] is not None else "Prices not set in `.env.eval`: costs left blank.")
        basis = "DRY RUN: stub answers and character-based token estimates, not Bedrock." if dry else "Tokens are Bedrock's own counts."
        fh.write(f"# PAM Bedrock benchmark summary ({label})\n\nModel: `{raw[-1]['model_id']}`. {basis} {price_txt}\n\n")
        fh.write("| Category | Ops | Success | Avg input | Avg output | Avg latency (s) | Avg cost / op (USD) | Avg cost / op (PHP) | Quality headline |\n|---|---:|---:|---:|---:|---:|---:|---:|---|\n")
        for r in summ:
            head = []
            if r["facts_rate_mean"] is not None:
                head.append(f"facts {r['facts_rate_mean']:.0%}")
            if r["group_rate_mean"] is not None:
                head.append(f"prompt facts {r['group_rate_mean']:.0%}")
            if r["extraction_accuracy_mean"] is not None:
                head.append(f"field accuracy {r['extraction_accuracy_mean']:.0%}")
            if r["persona_valid_rate"] is not None:
                head.append(f"valid personas {r['persona_valid_rate']:.0%}")
            if r["forbidden_hits_total"]:
                head.append(f"doc-only figures leaked {r['forbidden_hits_total']}")
            if r["unsupported_numbers_mean"]:
                head.append(f"unsupported figures/answer {r['unsupported_numbers_mean']}")
            fh.write(f"| {r['category']} | {r['operations']} | {r['success_rate']:.0%} | {fmt(r['avg_input_tokens'])} | {fmt(r['avg_output_tokens'])} | "
                     f"{fmt(r['avg_latency_s_per_op'], 1)} | {fmt(r['avg_cost_per_op'], 5)} | {fmt(r['avg_cost_per_op_php'], 4)} | {'; '.join(head) or 'n/a'} |\n")
    print(f"Reports written to {out.relative_to(ROOT)}")


def write_cap_comparison(labels: list[str], pr: dict) -> None:
    """Compare two labels (for example main,cap3000): benefit (success, quality) against cost."""
    if len(labels) != 2:
        print("--compare-caps needs two labels, e.g. main,cap3000")
        return
    data = {lb: final_ops(read_raw(lb)) for lb in labels}
    rows = []
    for cat in dict.fromkeys(o["category"] for lb in labels for o in data[lb]):
        row: dict[str, Any] = {"category": cat}
        for lb in labels:
            g = [o for o in data[lb] if o["category"] == cat and o["rep"] == 1]
            if not g:
                continue
            ok = [o for o in g if o["ok"]]
            toks = [op_tokens(o) for o in g if op_tokens(o)[0] is not None]
            costs = [op_cost(o, pr) or 0.0 for o in g]
            row.update({
                f"{lb}_cap": g[0].get("output_cap"), f"{lb}_ops": len(g), f"{lb}_ok": len(ok),
                f"{lb}_avg_output_tokens": mean([t[1] for t in toks]), f"{lb}_avg_latency_s": mean([op_seconds(o) for o in g]),
                f"{lb}_total_cost": round(sum(costs), 4),
                f"{lb}_cost_per_success": round(sum(costs) / len(ok), 4) if ok else None,
                f"{lb}_facts_rate": mean([o["quality"].get("facts_rate") for o in ok]),
                f"{lb}_accuracy": mean([o["quality"].get("accuracy") for o in ok]),
            })
        rows.append(row)
    out = EVAL / "results" / f"cap_comparison_{labels[0]}_vs_{labels[1]}.csv"
    write_csv(out, rows)
    # Operations that succeeded under both caps: did the higher cap change cost or output?
    a, b = ({(o["case_id"], o["rep"]): o for o in data[lb]} for lb in labels)
    both = [(a[k], b[k]) for k in a if k in b and a[k]["ok"] and b[k]["ok"]]
    if both:
        d_cost = [(op_cost(y, pr) or 0) - (op_cost(x, pr) or 0) for x, y in both]
        d_out = [(op_tokens(y)[1] or 0) - (op_tokens(x)[1] or 0) for x, y in both]
        print(f"Succeeded under both caps: {len(both)} ops; mean output change {statistics.mean(d_out):+.0f} tokens, "
              f"mean cost change {statistics.mean(d_cost):+.5f} USD")
    print(f"Wrote {out.relative_to(ROOT)}")
    for r in rows:
        print({k: v for k, v in r.items()})


# --------------------------------------------------------------------------- #
# Plan and main
# --------------------------------------------------------------------------- #


def routing_problems(cases: list[Case]) -> list[str]:
    """Prompts the assistant would answer locally (no Bedrock call) are a test-design error."""
    return [c.case_id for c in cases if c.kind == "assistant" and assistant.route(c.prompt) != "campaign"
            or c.kind == "assistant" and len(c.prompt) > assistant.MAX_QUESTION_CHARS]


def print_plan(cases: list[Case], reps: int, done: set, pr: dict) -> tuple[int, int]:
    bad = routing_problems(cases)
    if bad:
        print("WARNING: these prompts would be answered locally, not by Bedrock: " + ", ".join(bad))
    print("\nPlanned Bedrock invocations (estimated input tokens are character-based estimates)")
    print(f"{'category':26s} {'ops/rep':>8s} {'inv/rep':>8s} {'est input tokens/rep':>22s}")
    tot_inv_rep = tot_tok_rep = remaining_inv = remaining_tok = 0
    for cat in dict.fromkeys(c.category for c in cases):
        cs = [c for c in cases if c.category == cat]
        inv = sum(invocations_for(c) for c in cs)
        tok = sum(estimate_input(c) for c in cs)
        print(f"{cat:26s} {len(cs):8d} {inv:8d} {tok:22,d}")
        r = 1 if cat in DOCX_REF_CATEGORIES else reps
        tot_inv_rep += inv * r
        tot_tok_rep += tok * r
        for c in cs:
            for rep in range(1, r + 1):
                if (c.case_id, rep) not in done:
                    remaining_inv += invocations_for(c)
                    remaining_tok += estimate_input(c)
    print(f"\nAll repetitions: {tot_inv_rep} invocations, about {tot_tok_rep:,} input tokens (estimate).")
    print(f"Still to run now (stored results are reused): {remaining_inv} invocations, about {remaining_tok:,} input tokens (estimate).")
    if pr["input"] is None or pr["output"] is None:
        print("NOTE: BEDROCK_INPUT_PRICE_PER_MILLION / BEDROCK_OUTPUT_PRICE_PER_MILLION not found in .env.eval; costs will be blank until added (re-run --report-only).")
    return remaining_inv, tot_inv_rep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="main")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--proposals", default="")
    ap.add_argument("--categories", default="")
    ap.add_argument("--docx-reference", action="store_true", help="add the pilot-only DOCX-as-the-app-reads-it arm (4 calls)")
    ap.add_argument("--local-compare", action="store_true", help="write the local inventory and DOCX vs PDF comparison")
    ap.add_argument("--dry-run", action="store_true", help="stub client, no network, results in results/dryrun")
    ap.add_argument("--yes", action="store_true", help="confirm real, paid Bedrock calls")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--max-invocations", type=int, default=0)
    ap.add_argument("--output-cap", type=int, default=0,
                    help="TEMPORARY maxTokens override for this process only (assistant, extraction, persona); app code unchanged")
    ap.add_argument("--compare-caps", default="", help="two labels, e.g. main,cap3000: write the cap comparison and exit")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between real calls")
    a = ap.parse_args(argv)

    env = load_eval_env()
    pr = prices(env)
    if a.compare_caps:
        write_cap_comparison([x.strip() for x in a.compare_caps.split(",")], pr)
        return 0
    if a.output_cap:
        assistant.MAX_REPLY_TOKENS = extractor.MAX_REPLY_TOKENS = persona_narrator.MAX_REPLY_TOKENS = a.output_cap
        print(f"TEMPORARY output cap override: {a.output_cap} tokens for assistant, extraction and persona (this process only).")
    label = "dryrun" if a.dry_run else a.label
    out = EVAL / "results" / label
    if a.report_only:
        write_reports(label, pr)
        return 0
    keys = [k.strip() for k in a.proposals.split(",") if k.strip()] or list(PROPOSALS)
    cats = [c.strip() for c in a.categories.split(",") if c.strip()] or list(CATEGORIES)
    out.mkdir(parents=True, exist_ok=True)
    if a.dry_run:
        raw_path(label).unlink(missing_ok=True)

    if a.dry_run or a.local_compare:
        write_csv(out / "proposal_inventory.csv", inventory_rows())
        write_csv(out / "docx_vs_pdf_local.csv", local_docx_pdf_rows())
        print("Local inventory and DOCX vs PDF comparison written (no Bedrock).")

    cases = build_cases(keys, cats, a.docx_reference)
    raw = read_raw(label)
    last = {(r["case_id"], r["rep"]): r for r in final_ops(raw)}
    done = {k for k, r in last.items() if r["ok"] or not a.retry_failed}
    remaining, _total = print_plan(cases, a.reps, done, pr)

    client: Any = None
    model = "dry-run"
    if a.dry_run:
        client = StopReasonClient(DryClient())
    else:
        if not bedrock.credentials_available(env):
            print("ERROR: .env.eval is missing AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION or BEDROCK_MODEL_ID.")
            return 2
        if not a.yes:
            print("\nNo calls made. Add --yes to run these paid Bedrock calls.")
            return 0
        model = bedrock.model_id(env)
        if env.get("AWS_SESSION_TOKEN"):
            os.environ["AWS_SESSION_TOKEN"] = env["AWS_SESSION_TOKEN"]
        else:
            os.environ.pop("AWS_SESSION_TOKEN", None)
        client = StopReasonClient(bedrock._build_client(bedrock._read_env(env)))
    cap = a.max_invocations or remaining + 3
    used = 0
    for rep in range(1, a.reps + 1):
        for case in cases:
            if case.category in DOCX_REF_CATEGORIES and rep > 1:
                continue
            if (case.case_id, rep) in done:
                continue
            if used + invocations_for(case) > cap:
                print(f"Stopped: invocation cap {cap} reached.")
                write_reports(label, pr)
                return 3
            attempt = (last[(case.case_id, rep)]["attempt"] + 1) if (case.case_id, rep) in last else 1
            op = run_case(case, env, client)
            used += len(op.get("invocations", []))
            op.update(rep=rep, attempt=attempt, label=label, model_id=model, timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"))
            append_raw(label, op)
            tin, tout, _ = op_tokens(op)
            print(f"[rep {rep}] {case.case_id:48s} {'ok ' if op['ok'] else 'FAIL'} in={tin} out={tout} {op_seconds(op)}s"
                  f"{'' if op['ok'] else ' reason=' + ','.join({i['reason'] for i in op.get('invocations', []) if i['reason']} | ({op['error']} if op.get('error') else set()))}")
            if not a.dry_run:
                time.sleep(a.pause)
    write_reports(label, pr)
    print(f"Invocations made this run: {used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
