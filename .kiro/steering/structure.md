# Project Structure

## Top-level layout

```
DataWave/
├── app/                  # Part 5 Streamlit webapp (presentation layer only)
│   ├── main.py           # Streamlit entry point — wires widgets to webapp_core
│   ├── theme.py          # styling / HTML chrome helpers
│   └── styles.css
├── data/                 # input CSVs (customer_dna, transactions, promo_history, ...)
│   ├── gen_data.py       # synthetic data generator
│   └── _answer_key_*.csv # FORBIDDEN as model inputs
├── outputs/              # generated artifacts (model, scores, cards.json, leads/)
├── src/                  # all pipeline + webapp logic (PYTHONPATH=src)
│   ├── run_pipeline.py   # orchestrates the four stages in dependency order
│   ├── part1_optin/      # opt-in propensity model
│   ├── part2_network/    # network / customer features
│   ├── part3_segments/   # 2x2 segment labels
│   ├── part4_cards/      # action cards + sendable leads
│   └── webapp_core/      # pure logic behind the webapp (no Streamlit imports)
├── tests/                # pytest + hypothesis suite
├── .kiro/specs/          # per-part requirements/design/tasks specs
└── requirements.txt
```

## Pipeline package convention

Each `src/partN_*` package follows the same shape:

- `config.py` — a frozen `@dataclass Config` of input/output `Path` fields (canonical defaults), plus domain constants (seeds, column lists, markers). One place for discrepancy-prone values.
- `main.py` — the CLI entry point: `_parse_args` maps `--flag` overrides onto `Config`, a `main(argv: list[str] | None = None) -> int` runs the stage, and the module ends with `if __name__ == "__main__": raise SystemExit(main())`.
- Remaining modules are single-responsibility stages (loader → features/classify → model/cards), each a small class or function.

### Dependency order

`run_pipeline.py` runs stages as: **part2_network → part1_optin → part3_segments → part4_cards**. A stage returning a non-zero exit code stops the run before later stages execute.

### Output safety

Output-producing steps (writing the model, scores, cards, leads) run **last**, after all computation succeeds, so a failure leaves `outputs/` untouched. Validation/loader gates are the only stages allowed to halt before output.

## Webapp layering

- `app/` is the declarative composition layer — it only wires Streamlit widgets and session state.
- `src/webapp_core/` holds all real logic (model reload, eligibility, promo-id generation, run orchestration). It reuses the Part 1/3/4 APIs and adds no modelling.
- Keep Streamlit imports out of `webapp_core`; keep business logic out of `app/`.

## Conventions

- Thorough module and function docstrings; many cite the governing spec requirement (e.g. "Requirement 6.2"). Preserve these references when editing.
- `main()` entry points return an `int` exit code; failures print to stderr naming the failing step and return non-zero.
- Error handling halts early on bad input and reports the step by name.

## Testing conventions

- Tests live in `tests/` and are named `test_<area>_<kind>.py` where kind is `unit`, `integration`, `property`, or `edge`.
- Property-based tests (hypothesis) are the primary style; shared input generators live in `tests/strategies*.py`.
- `tests/conftest.py` makes `src/` importable — never hardcode `sys.path` in individual tests.
