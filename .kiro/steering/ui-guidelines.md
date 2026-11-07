---
inclusion: fileMatch
fileMatchPattern: "app/**"
---

# UI Guidelines

## Purpose

DataWave is an analytical CRM tool for bank campaign planners. The UI should feel calm, trustworthy and efficient. Workflow and clarity come before decoration.

## Brand influence

- Take influence from the BPI mobile app and website: palette, type feel, spacing, tone.
- NEVER use the BPI logo, wordmark, or any asset copied from BPI. Never reproduce a logo-derived shape or pattern.
- The app name stays "Promo Audience Navigator" / DataWave.

## Fonts

- **FF Dax** for headings and display. **Avenir Next** for body and UI. **Manrope** sparingly.
- FF Dax and Avenir Next are commercial. Never download, scrape or embed them. Use them only if licensed files are placed in `app/static/fonts`. Otherwise use a fallback stack and tell the user.
- Bundle Manrope locally (SIL OFL) so the app works offline.

## Modes

- Light and dark mode, both fully styled.
- Text contrast meets WCAG AA in both modes.

## Motion

- Minimal, fluid, smooth: 120-250 ms, ease-out, opacity and transform only.
- Nothing loops except loading indicators.
- Respect `prefers-reduced-motion`.
- No motion on large tables or charts.

## Scope

- Styling and layout only.
- Do not change backend logic, calculations, widget keys, the meaning of `labels.py` wording, or any part5 behavior.
- Keep `tests/test_part5_theme.py` and `tests/test_part5_personas_apptest_smoke.py` passing.
- Update an existing test expectation only when the intentional restyle changed it, and list each change.

## Tokens

- One source of truth for colors, type scale, spacing, radius and motion durations.
- No hardcoded hex values or font names scattered in page code. Use shared helpers in `app/theme.py`.

## Views to cover

- Tabs
- Promo cards and chips
- Personas tab: controls, split-into-groups control, group dropdown, warning and caption, persona cards, "Expected Joiners By Persona" tables with collapsed "How to message this" and "Details" sections, downloads
- Results
- What-If
- Past Promos
- Error and empty states

## Process (per task)

1. Read the relevant code first.
2. Describe what you see in each attached reference image and list the approximate values you sample, labelled approximate.
3. Propose the design and WAIT for approval.
4. Implement.
5. Run only the affected tests plus the AppTest smoke test.
6. Report files changed and what to check in the browser, then stop.

## Off limits

- Do not modify Part 1-4 modules, `run_pipeline.py`, `outputs/` or `data/`.
- Do not run `pip install`.