# 001 — Pause the Job_Button breath loop while it is not hovered

- **Status**: TODO
- **Commit**: b092012
- **Severity**: MEDIUM
- **Category**: Performance
- **Estimated scope**: 1 file (`app/styles.css`), about 6 lines

## Problem

The two Job_Buttons ("Run Analysis", "Build Personas") each have a glow halo on
the container `::before`. Its breath loop runs **forever, on every page, even
when nobody hovers**. The halo is invisible then (opacity is
`--p8-hover × --p8-breath` and `--p8-hover` is 0), but the browser still does
the work. The loop animates a registered custom property (`--p8-breath`).
Custom properties cannot run on the compositor, so every frame forces a style
recalculation on the main thread. The `will-change` hint also keeps two layers
alive all the time.

```css
/* app/styles.css:1554-1570 — current */
[class*="st-key-p8_btn_"]::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: var(--pan-radius-md);
  box-shadow: 0 0 20px 4px var(--pan-breath-glow);
  pointer-events: none;
  z-index: 0;
  --p8-hover: 0;
  opacity: calc(var(--p8-hover) * var(--p8-breath));
  will-change: transform, opacity;
  transition: --p8-hover var(--pan-dur-slow) var(--pan-ease);
  animation: p8-breath calc(var(--pan-dur-breath) / 2) var(--pan-ease-breath) infinite alternate;
}
[class*="st-key-p8_btn_"]:hover::before {
  --p8-hover: 1;
}
```

The design doc (`.kiro/specs/part8-new-ui-features/design.md:369`, decision A4)
says the loop always runs so that (a) hovering never restarts it and (b) leaving
fades out from whatever phase it is in. **Both properties must be kept.**
`animation-play-state: paused` keeps both. A paused animation holds its current
phase, and setting it back to running resumes from that phase without
restarting. So the loop only costs anything while the pointer is over the
button.

## Target

```css
/* target */
[class*="st-key-p8_btn_"]::before {
  /* ...all existing declarations unchanged except will-change... */
  will-change: auto;
  transition: --p8-hover var(--pan-dur-slow) var(--pan-ease);
  animation: p8-breath calc(var(--pan-dur-breath) / 2) var(--pan-ease-breath) infinite alternate;
  animation-play-state: paused;
}
[class*="st-key-p8_btn_"]:hover::before {
  --p8-hover: 1;
  will-change: transform, opacity;
  animation-play-state: running;
}
```

On leave, the halo freezes at its current breath phase while `--p8-hover`
fades from 1 to 0 over `--pan-dur-slow` (250 ms). The fade still starts from
the current phase, which is the documented behaviour.

## Repo conventions to follow

- All durations and easings are tokens from section 1 of `app/styles.css`.
  Do not write a literal `ms`/`s` value: `tests/test_part8_tokens_unit.py::test_part8_css_has_no_literal_colours_or_durations` fails on any literal duration after the "8. PART 8 SHARED MOTION" heading.
- The comment block at `app/styles.css:1531-1540` documents this halo. Add one
  sentence to it: "The loop is paused while not hovered, so it costs nothing at
  rest; pausing keeps its phase, so hovering still never restarts it."

## Steps

1. In `app/styles.css`, in the rule `[class*="st-key-p8_btn_"]::before` (around line 1554), replace `will-change: transform, opacity;` with `will-change: auto;`, and add `animation-play-state: paused;` after the `animation:` line.
2. In the rule `[class*="st-key-p8_btn_"]:hover::before` (around line 1568), add `will-change: transform, opacity;` and `animation-play-state: running;` below `--p8-hover: 1;`.
3. Leave the running-state rule `[class*="st-key-p8_btn_"]:has(.p8-ring--running)::before` (sets `--p8-hover: 0`) alone. While a job runs the pointer is usually still over the button, so the loop keeps running underneath an invisible halo for the job's duration. That is acceptable. Do not add more selectors.
4. Add the sentence from "Repo conventions" to the comment at line 1531-1540.

## Boundaries

- Do NOT change `@keyframes p8-breath`, the `@property` blocks, durations, or easings.
- Do NOT touch the reduced-motion block (`app/styles.css` around line 1701). It already sets `animation: none` there.
- Do NOT touch any other file.
- If the rules don't match the excerpt above (drift since b092012), STOP and report.

## Verification

- **Mechanical**: `python -m pytest tests/test_part8_tokens_unit.py -q` passes.
- **Feel check** (run the app, e.g. `streamlit run app/main.py`):
  - Hover "Run Analysis". The halo breathes as before, about 1.6 s per full breath.
  - Move the pointer off mid-breath. The halo fades out smoothly from its current brightness, with no snap.
  - Hover again. The breath continues from where it paused, with no jump back to its dim start.
  - DevTools → Performance: record 5 s with the pointer away from both buttons. There should be **no** recurring "Recalculate Style" every frame (before the fix there is one).
  - Animations panel at 10% playback: no jump in halo scale on hover enter or leave.
- **Done when**: no per-frame style work at rest, and the hover behaviour looks the same as before.
