# 004 — Gate hover movement behind a fine pointer, add press to Toggle_Card

- **Status**: TODO
- **Commit**: b092012
- **Severity**: LOW
- **Category**: Accessibility / Physicality
- **Estimated scope**: 2 files (`app/styles.css`, `app/static/group_picker/picker.css`), about 20 lines

## Problem

Hover transforms are not gated. On touch devices a tap fires `:hover`, and it
sticks until you tap somewhere else. A button stays lifted, or a ring arrow
stays enlarged, after you lift your finger.

```css
/* app/styles.css:1054-1056 — current: shared button lift */
.stButton > button:hover:not(:disabled), .stDownloadButton > button:hover:not(:disabled), .stFormSubmitButton > button:hover:not(:disabled) {
  transform: translateY(-1px);
}
```

```css
/* app/static/group_picker/picker.css:126 — current: ring arrow */
.rot:hover { transform: scale(1.06); }

/* app/static/group_picker/picker.css:173 — current: Toggle_Card option */
.opt:hover { transform: translateY(-2px); }

/* app/static/group_picker/picker.css:189-191 — current: map area lift */
g[data-area]:hover:not(.is-muted),
g[data-area]:focus-visible:not(.is-muted),
g[data-area].is-selected { transform: translateY(calc(var(--lift) * -1)); }
```

Also, the Toggle_Card `.opt` is a pressable `<button>` with **no `:active`
press feedback**. The ring arrow (`.rot:active { transform: scale(0.94); }`)
and the Job_Buttons (`scale(var(--pan-scale-press))`) both have one.

## Target

Wrap only the `:hover` transforms in
`@media (hover: hover) and (pointer: fine) { ... }`. Focus-visible and selected
states stay ungated, because keyboard and selection must still lift. Add press
feedback to `.opt`:

```css
/* target, picker.css */
@media (hover: hover) and (pointer: fine) {
  .rot:hover { transform: scale(1.06); }
  .opt:hover { transform: translateY(-2px); }
  g[data-area]:hover:not(.is-muted) { transform: translateY(calc(var(--lift) * -1)); }
}
.rot:active { transform: scale(0.94); }                 /* unchanged; must stay AFTER the media block */
.opt:active { transform: scale(0.97); }                 /* new press feedback */
g[data-area]:focus-visible:not(.is-muted),
g[data-area].is-selected { transform: translateY(calc(var(--lift) * -1)); }
```

`0.97` is the repo's press scale (`--pan-scale-press: 0.97` in
`app/styles.css`). That token is not passed into the iframe palette
(`theme.PICKER_TOKENS`, `app/theme.py:181`), so write the number `0.97`
directly. This is the same way `.rot:active` writes `0.94`. Numbers without
units are allowed. The asset test only forbids colours, URLs and `$`.

```css
/* target, styles.css */
@media (hover: hover) and (pointer: fine) {
  .stButton > button:hover:not(:disabled), .stDownloadButton > button:hover:not(:disabled), .stFormSubmitButton > button:hover:not(:disabled) {
    transform: translateY(-1px);
  }
}
```

## Repo conventions to follow

- Motion uses existing transitions. `.opt` already has `transition: transform var(--pan-dur) var(--pan-ease), opacity var(--pan-dur) var(--pan-ease);` (picker.css:160), so the press animates with no extra work.
- Source order matters. `:active` rules must come **after** the hover media block so a press wins over hover.
- The reduced-motion block at picker.css:208-212 sets `.opt:hover, .rot:hover, .rot:active { transform: none; }`. Add `.opt:active` to that selector list.
- `app/styles.css:1057-1059` (`:active` → `translateY(0)`) stays where it is, after the new media block.
- Reduced-motion block in styles.css (around line 1064-1069) already overrides the hover transform. Leave it.

## Steps

1. `app/styles.css:1054-1056`: wrap the hover rule in `@media (hover: hover) and (pointer: fine) { ... }`. Keep the following `:active` rule outside and after it.
2. `app/static/group_picker/picker.css`: remove line 126 (`.rot:hover ...`) and line 173 (`.opt:hover ...`), and remove `g[data-area]:hover:not(.is-muted),` from the selector list at line 189.
3. In `picker.css`, directly before `.rot:active` (line 127), insert the media block with the three hover rules from the target. Move `.rot:active` after the block if needed.
4. In `picker.css`, add `.opt:active { transform: scale(0.97); }` after the `.opt` rules, after the media block.
5. In `picker.css` reduced-motion block (line 211), change the selector to `.opt:hover, .opt:active, .rot:hover, .rot:active { transform: none; }`.

## Boundaries

- Do NOT change durations, easings or the transform values themselves.
- Do NOT gate `:focus-visible` or `.is-selected`.
- Do NOT touch `picker.js` (the map shadow's `mouseenter` handler is fine; it only changes opacity).
- Do NOT touch the Job_Button rules (`[class*="st-key-p8_btn_"]`). They already cancel the shared lift.
- If the code doesn't match the excerpts (drift since b092012), STOP and report.

## Verification

- **Mechanical**: `python -m pytest tests/test_part8_assets_unit.py tests/test_part8_tokens_unit.py tests/test_part8_group_picker_unit.py -q` passes.
- **Feel check**:
  - Desktop with a mouse: hovering buttons, ring arrows, Toggle_Card options and map areas lifts or scales exactly as before.
  - Press a Toggle_Card option and hold. It dips slightly (0.97). On release it settles.
  - DevTools device toolbar (touch emulation, e.g. "iPhone 12"): tap a ring arrow and a regular button. Neither stays enlarged or lifted after the tap.
  - Keyboard: Tab to a map area. It still lifts on focus.
- **Done when**: no sticky hover transforms under touch emulation, and `.opt` has press feedback.
