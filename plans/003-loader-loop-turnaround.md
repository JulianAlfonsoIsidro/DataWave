# 003 — Use the symmetric breath curve on the loader's alternate loops

- **Status**: TODO
- **Commit**: b092012
- **Severity**: MEDIUM
- **Category**: Easing & duration
- **Estimated scope**: 1 file (`app/styles.css`), 2 lines

## Problem

Two loader loops use `infinite alternate` with the ease-out token `--pan-ease`.
An alternate loop plays its reverse leg on the reversed curve. With ease-out,
that means it arrives back at the start **at full speed** and leaves again at
full speed. You see a tick or bounce at one end of every cycle. Decision A4
(`.kiro/specs/part8-new-ui-features/design.md:369`) diagnosed exactly this on
the Job_Button breath ("the ease-out curve bounced at each turn of the
alternate loop") and fixed it with `--pan-ease-breath`. These two loops were
missed:

```css
/* app/styles.css:733 — current: skeleton bars pulse */
.pan-skel span { display: block; height: 10px; border-radius: var(--pan-radius-sm); background: var(--pan-skel); animation: pan-pulse 1.4s var(--pan-ease) infinite alternate; }

/* app/styles.css:767 — current: magnifier bob in the analysis loader */
.pan-mag { position: absolute; left: 50%; top: 4px; width: 0; height: 0; animation: pan-mag-bob 1.8s var(--pan-ease) infinite alternate; }
```

People watch the loader for several seconds on every job, so the tick shows.

## Target

Swap only the timing function to the existing symmetric token:

```css
--pan-ease-breath: cubic-bezier(0.37, 0, 0.63, 1);   /* already defined, app/styles.css:184 */
```

```css
/* target */
.pan-skel span { ...; animation: pan-pulse 1.4s var(--pan-ease-breath) infinite alternate; }
.pan-mag { ...; animation: pan-mag-bob 1.8s var(--pan-ease-breath) infinite alternate; }
```

## Repo conventions to follow

- `--pan-ease-breath` is documented as "Symmetric (sine-like) curve for the
  breath loop only: it slows at both ends, so the alternate loop never turns
  around at full speed" (`app/styles.css:181-184`). Update that comment to say
  it is for **alternate loops** (breath, loader pulse, magnifier bob), not the
  breath only.
- These lines are in section 5 (LOADING), before the Part 8 no-literal scan, so
  the existing literal `1.4s` / `1.8s` stay as they are.

## Steps

1. `app/styles.css:733`: in the `.pan-skel span` rule, replace `var(--pan-ease)` with `var(--pan-ease-breath)`.
2. `app/styles.css:767`: in the `.pan-mag` rule, replace `var(--pan-ease)` with `var(--pan-ease-breath)`.
3. `app/styles.css:181-183`: reword the comment above `--pan-ease-breath` as described.

## Boundaries

- Do NOT change durations, keyframes, `.pan-docs-track` (linear is correct for a constant conveyor), or the persona puzzle tiles (their curve is baked into keyframes and played `linear`).
- Do NOT change the token's value.
- If the lines don't match (drift since b092012), STOP and report.

## Verification

- **Mechanical**: `python -m pytest tests/test_part8_tokens_unit.py -q` passes.
- **Feel check**: trigger Run Analysis on a promo (use a slow one, or temporarily throttle CPU 6× in DevTools so the loader stays up).
  - DevTools Animations panel at 10% speed: the magnifier slows down at **both** the top and the bottom of its bob. Before the fix it reversed sharply at the bottom.
  - The skeleton bars' brightness eases in and out at both ends, with no flash at the dim end.
- **Done when**: no visible turnaround tick on either loop.
