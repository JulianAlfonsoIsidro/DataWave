# Animation improvement plans

From an `improve-animations` audit at commit `b092012` (2026-11-11). Each plan is
self-contained. Hand any one to an agent as-is.

| # | Plan | Severity | Status |
| --- | --- | --- | --- |
| 001 | [Pause the Job_Button breath loop while not hovered](001-pause-idle-breath-loop.md) | MEDIUM | OBSOLETE: the breath glow was removed (polish fix 4) |
| 002 | [Honour reduced motion on the Group_Visual reveal](002-group-visual-reduced-motion.md) | MEDIUM | DONE: the inline rise was removed; the iframe reveal handles reduced motion |
| 003 | [Symmetric curve on the loader's alternate loops](003-loader-loop-turnaround.md) | MEDIUM | DONE |
| 004 | [Gate hover movement; press feedback on Toggle_Card](004-gate-hover-motion.md) | LOW | DONE |
| 005 | [No per-frame layout reads in the ring carousel](005-ring-layout-no-per-frame-reads.md) | LOW | DONE |

## Recommended order

002 → 003 → 001 → 004 → 005. The first three are one-to-six-line CSS/string
edits. 004 touches two files. 005 is the only JS change.

## Dependencies

None between plans. 001, 003 and 004 all edit `app/styles.css` in different
rules. Run them one after another (not in parallel worktrees) to avoid merge
noise.

## Audited but not planned

- **Ring carousel drops rapid inputs** (`picker.js` `stepBy`, around line 233):
  while a rotation runs, at most one more step is queued. Three quick arrow
  presses move two items, and each queued step restarts the ease from zero
  velocity. Retargeting the animation mid-flight is straightforward, but every
  step also posts a value and triggers a Streamlit rerun. A late rerun could
  rotate the ring back to an older selection. Needs a decision on rerun
  debouncing before a safe plan can be written.
- **`--pan-ease` is a soft ease-out** (`cubic-bezier(0, 0, 0.2, 1)`). A stronger
  `cubic-bezier(0.23, 1, 0.32, 1)` would make the 120–250 ms UI feel snappier.
  But it is one global token that also drives the 600 ms number roll and the
  toast life, so judge it by feel before planning it.
