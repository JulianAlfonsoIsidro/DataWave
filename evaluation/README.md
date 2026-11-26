# PAM Bedrock benchmark (hackathon validation)

Standalone script that reuses PAM's own assistant, extractor and persona-naming code. It does not change the app, the UI or `.env`.

Setup: copy `.env.eval.example` to `.env.eval` and fill it in (git-ignored). Prices (`BEDROCK_INPUT_PRICE_PER_MILLION`, `BEDROCK_OUTPUT_PRICE_PER_MILLION`, in USD) are your verified per-1M-token figures; optional `USD_TO_PHP` adds a peso column; the script assumes none.
Inputs: `evaluation/proposals/` (originals), `evaluation/proposals_pdf/` (PDF versions of the two DOCX files), `evaluation/expected_facts.json` (form values, expected facts, prompts).
Outputs: `evaluation/results/<label>/` (git-ignored).

Run from the repo root on macOS:

    # 1. Free check: plan, invocation count, full pipeline with a stub client (no network)
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --dry-run --reps 3 --docx-reference

    # 2. Pilot: 1 repetition + DOCX reference calls (49 paid invocations)
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --reps 1 --docx-reference --local-compare --yes

    # 3. Full: 3 repetitions; pilot results are reused (90 more invocations)
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --reps 3 --yes

    # Retry only failed operations (the failed attempt stays in the detailed CSV)
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --reps 3 --retry-failed --yes

    # Rebuild reports (for example after adding prices to .env.eval)
    PYTHONPATH=src .venv/bin/python evaluation/run_benchmark.py --label main --report-only

Without `--yes` a real run only prints the plan. A Demo fallback counts as a failed operation. Prompts that the assistant would answer locally are flagged in the plan.
