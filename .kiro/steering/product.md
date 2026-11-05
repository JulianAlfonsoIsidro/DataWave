# Product

DataWave is a hackathon project that helps a retail bank design and target customer promotions. It turns raw banking data (customer profiles, balances, transactions, contact history, past promos) into a ranked, segmented, and actionable audience for a given promo.

## What it does

The product is built as four batch pipeline stages plus an interactive webapp:

- **Part 1 — Opt-in propensity**: fits a calibrated model that predicts each lead's probability of joining a promo (`p_join`), with top-3 SHAP drivers per lead.
- **Part 2 — Network features**: derives customer features (e.g. outflows to other banks, inflow/spend shares) consumed by later stages.
- **Part 3 — Segments**: assigns each client one of four segment labels from a 2x2 of score (propensity) vs capacity: Ready Toppers, Untapped Wealth, Willing but Stretched, Not Now.
- **Part 4 — Cards**: builds one action card per segment cell (dominant channel, message angle, expected joiners, expected value) and writes per-segment sendable-lead CSVs, honoring do-not-contact and control-group rules.
- **Part 5 — Webapp (Promo Audience Navigator)**: a Streamlit UI to design a promo, score and segment the audience, inspect decision cards, run What-If threshold analysis, download sendable leads, and compare predicted vs actual join rates on past promos. The app never retrains — it only reloads the fitted Part 1 model.

## Key domain rules

- Answer-key files (anything containing `_answer_key`) are forbidden as model inputs — never train or score on them.
- Only promos `P001`, `P002`, `P003` are used for training; leads are "treated" when `control_group == 0`.
- All stochastic operations use a fixed random seed (42) for determinism.
- Channel labels must match exactly (`In-app`, `Email`, `SMS`); a mismatch makes leads unreachable and zeroes out expected joiners.
