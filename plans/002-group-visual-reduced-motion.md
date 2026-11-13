# 002 — Honour reduced motion on the Group_Visual reveal

- **Status**: TODO
- **Commit**: b092012
- **Severity**: MEDIUM
- **Category**: Accessibility
- **Estimated scope**: 1 file (`app/persona_page.py`), 1 string

## Problem

After a successful persona build, the group visual (map, ring or Toggle_Card)
rises 14 px into place as item 1 of the Results_Reveal. The rule is injected as
an inline `<style>`. Unlike every other Part 8 motion, it has **no
`prefers-reduced-motion` override**, so users who asked for reduced motion
still get the movement.

```python
# app/persona_page.py:2170-2175 — current
    if reveal:
        # One-shot rise of the visual as item 1 of the reveal (F8, Req 17.2).
        ui_effects.emit(
            '<style>.st-key-p8_group_visual{animation:p8-rise var(--pan-dur-slow) '
            "var(--pan-ease) backwards;animation-delay:calc(var(--pan-dur-toast-delay) "
            "+ var(--pan-reveal-base))}</style>"
        )
```

The sibling persona cards already do this correctly
(`app/styles.css:1974-1977`):

```css
@media (prefers-reduced-motion: reduce) {
  .p8-reveal { animation: p8-fade-in var(--pan-dur-xfade-short) var(--pan-ease) backwards; }
}
```

## Target

Under reduced motion, the visual fades in over `--pan-dur-xfade-short` (150 ms)
with `--pan-ease`. There is no rise and no delay, which matches `.p8-reveal`.
Reduced motion keeps the opacity feedback and drops the movement.

```python
# target
    if reveal:
        # One-shot rise of the visual as item 1 of the reveal (F8, Req 17.2).
        # Reduced motion: opacity only, no delay (same as .p8-reveal).
        ui_effects.emit(
            '<style>.st-key-p8_group_visual{animation:p8-rise var(--pan-dur-slow) '
            "var(--pan-ease) backwards;animation-delay:calc(var(--pan-dur-toast-delay) "
            "+ var(--pan-reveal-base))}"
            "@media (prefers-reduced-motion: reduce){.st-key-p8_group_visual{"
            "animation:p8-fade-in var(--pan-dur-xfade-short) var(--pan-ease) backwards;"
            "animation-delay:0s}}</style>"
        )
```

## Repo conventions to follow

- Tokens only. `--pan-dur-xfade-short` and `--pan-ease` are defined in
  `app/styles.css` section 1. `@keyframes p8-fade-in` is at `app/styles.css:1122`.
- Exemplar: `.p8-reveal` reduced-motion rule at `app/styles.css:1975`.

## Steps

1. In `app/persona_page.py` around line 2170, replace the string passed to `ui_effects.emit(...)` with the target string above, exactly. Add the one-line comment.

## Boundaries

- Do NOT move the rule into `styles.css`. It is one-shot by design: it only exists in the reveal render.
- Do NOT change the non-reduced animation.
- Do NOT touch other files.
- If the code doesn't match the excerpt (drift since b092012), STOP and report.

## Verification

- **Mechanical**: `python -m pytest tests -q -k "part8 or persona"` passes.
- **Feel check**:
  - Build personas with a split column (so a group visual shows). The visual rises in, timed with the cards, as before.
  - DevTools → Rendering → "Emulate CSS media feature prefers-reduced-motion: reduce". Build again. The visual fades in over about 150 ms with no upward movement and no wait.
- **Done when**: no transform animation on `.st-key-p8_group_visual` under reduced motion.
