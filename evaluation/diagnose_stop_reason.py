"""Diagnostic: why do some replies stop at the output cap? (2 paid Bedrock calls, about $0.08.)

Sends the same request the benchmark sent for two failed pilot cases (FORWARD heavy draft prompt at the
assistant cap, FORWARD field extraction at the extractor cap) and prints only metadata: stop reason,
content block types, text length, token usage. It prints no reply text and no credentials.
Run:  PYTHONPATH=src .venv/bin/python evaluation/diagnose_stop_reason.py --yes
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_benchmark as rb  # noqa: E402
from ai import assistant, bedrock, extractor  # noqa: E402


def main() -> int:
    if "--yes" not in sys.argv:
        print("Add --yes to make 2 paid Bedrock calls.")
        return 0
    env = rb.load_eval_env()
    if not bedrock.credentials_available(env):
        print("Missing .env.eval values.")
        return 2
    if env.get("AWS_SESSION_TOKEN"):
        os.environ["AWS_SESSION_TOKEN"] = env["AWS_SESSION_TOKEN"]
    values = bedrock._read_env(env)
    client = bedrock._build_client(values)
    case = rb.Case("diag", "assistant_high_medium", "forward", "assistant", rb.PROMPTS["medium_draft"], "high")
    g = rb.grounding_for(case)
    jobs = [
        ("assistant heavy draft prompt", assistant.SYSTEM_PROMPT, assistant.build_payload(case.prompt, g), assistant.MAX_REPLY_TOKENS),
        ("field extraction", extractor.SYSTEM_PROMPT, extractor.request_payload(rb.doc_text("forward")), extractor.MAX_REPLY_TOKENS),
    ]
    for name, system, payload, cap in jobs:
        resp = client.converse(modelId=values["BEDROCK_MODEL_ID"], system=[{"text": system}],
                               messages=[{"role": "user", "content": [{"text": json.dumps(payload, default=str, ensure_ascii=False)}]}],
                               inferenceConfig={"maxTokens": cap})
        blocks = resp["output"]["message"]["content"]
        kinds = [next(iter(b)) for b in blocks]
        text_chars = sum(len(b.get("text", "")) for b in blocks)
        reasoning_chars = sum(len(json.dumps(b.get("reasoningContent", {}))) for b in blocks)
        u = resp.get("usage", {})
        print(f"{name}: cap={cap} stopReason={resp.get('stopReason')} blocks={kinds} text_chars={text_chars} "
              f"reasoning_chars~{reasoning_chars} usage in/out/total={u.get('inputTokens')}/{u.get('outputTokens')}/{u.get('totalTokens')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
