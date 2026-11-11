# 005 — Stop the ring carousel from reading layout every animation frame

- **Status**: TODO
- **Commit**: b092012
- **Severity**: LOW
- **Category**: Performance
- **Estimated scope**: 1 file (`app/static/group_picker/picker.js`), about 15 lines

## Problem

The 3D ring rotation runs a `requestAnimationFrame` tween. Each frame calls
`layoutRing()`, which **reads** `root.clientWidth` and calls
`getComputedStyle` twice (through `cssVar`). Then it **writes** transforms and
z-index to every item. The next frame's read comes right after the previous
writes, which forces a synchronous style and layout pass every frame. The items
also carry `backdrop-filter` glass layers, which are already expensive to
composite. The rotation is only 250 ms, but it is the picker's main
interaction.

```js
// app/static/group_picker/picker.js:160-182 — current
  function layoutRing() {
    var items = root.querySelectorAll(".item");
    var n = items.length;
    if (!n) return;
    var step = (2 * Math.PI) / n;
    var w = root.clientWidth || 600;
    var R = Math.min(Math.max(w * 0.34, 140), 300);
    var s1 = parseFloat(cssVar("--pan-glass-scale-1")) || 0.92;
    var s2 = parseFloat(cssVar("--pan-glass-scale-2")) || 0.86;
    for (var i = 0; i < n; i++) {
      ...
      items[i].style.transform = "translate(" + x.toFixed(1) + "px," + y.toFixed(1) + "px) scale(" + scale.toFixed(3) + ")";
      items[i].style.zIndex = String(200 + Math.round(depth * 100));
    }
  }
```

`layoutRing` is called per frame from `rotateTo` → `frame()` (picker.js:218-228),
on rebuild (picker.js:305 in `render`) and on `resize` (picker.js:331).

## Target

Measure once and draw many times. Cache the geometry in `S`, and refresh it
only when it can change: on rebuild, on resize, and when a rotation starts.
Per-frame `layoutRing()` then does no DOM reads.

```js
// target
  var S = { ..., geo: null };            // add geo to the existing S object (picker.js:20)

  function measureRing() {
    var items = root.querySelectorAll(".item");
    var w = root.clientWidth || 600;
    S.geo = {
      items: items,
      R: Math.min(Math.max(w * 0.34, 140), 300),
      s1: parseFloat(cssVar("--pan-glass-scale-1")) || 0.92,
      s2: parseFloat(cssVar("--pan-glass-scale-2")) || 0.86,
    };
  }

  function layoutRing() {
    if (!S.geo) measureRing();
    var items = S.geo.items, R = S.geo.R, s1 = S.geo.s1, s2 = S.geo.s2;
    var n = items.length;
    if (!n) return;
    var step = (2 * Math.PI) / n;
    for (var i = 0; i < n; i++) { /* loop body unchanged */ }
  }
```

## Repo conventions to follow

- Plain ES5 in an IIFE (`var`, `function`, no arrow functions, no build step). Match it.
- No literal colours, no `$`, no `http(s)://` in this file (`tests/test_part8_tokens_unit.py::test_static_component_files_are_clean`).

## Steps

1. `picker.js:20`: add `geo: null` to the `S` object literal.
2. Add `measureRing()` (target above) directly above `layoutRing()`.
3. Rewrite the top of `layoutRing()` as in the target. Keep the `for` loop body exactly as it is.
4. In `render()`, in the `if (rebuild)` branch (picker.js:298), set `S.geo = null;` next to `S.mapSvg = null;`, so a rebuilt ring re-measures its new items.
5. In `rotateTo()`, just before `var from = S.pos, to = S.pos + steps;` (picker.js:212), call `measureRing();`. That is one read at the start of each rotation, before any writes in that rotation.
6. In the `resize` listener (picker.js:331), change `if (S.kind === "carousel") layoutRing();` to `if (S.kind === "carousel") { measureRing(); layoutRing(); }`.

## Boundaries

- Do NOT change easing, duration, the queueing in `stepBy`, the ring math, or `choose()` / message handling.
- Do NOT touch the map or toggle code paths.
- If line references don't match (drift since b092012), STOP and report.

## Verification

- **Mechanical**: `python -m pytest tests/test_part8_group_picker_unit.py tests/test_part8_tokens_unit.py -q` passes. `node --check app/static/group_picker/picker.js` passes, if Node is available.
- **Feel check**: build personas split by a column with 5+ values (so the ring shows).
  - Click the arrows and click side items. The rotation looks identical to before, with the same arc, scale and depth.
  - Resize the browser window. The ring radius adapts.
  - DevTools → Performance (inside the picker iframe), 4× CPU throttle, record a rotation. No purple "Layout" or forced-reflow warnings inside the rAF frames. Before the fix there is one per frame.
- **Done when**: zero forced layouts during a rotation, and the motion is unchanged.
