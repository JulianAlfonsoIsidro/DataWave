/* Part 8 Group_Component (F6 region map, F7 3D ring + Toggle_Card, F9).
 *
 * A plain Streamlit bidirectional component with no build step: it speaks
 * the component protocol directly (componentReady / render / setComponentValue
 * / setFrameHeight). Python decides WHICH visual to draw (webapp_core
 * group_picker_items.plan_picker) and sends every colour and motion value.
 *
 * Rules (Requirement 12): only user actions post a value ({value, nonce});
 * a change that arrives in the args (dropdown -> visual) never posts, so one
 * user action causes exactly one rerun. The ring rotates by the shortest
 * direction (shortest_step mirrors the Python helper), the glass layers
 * crossfade by opacity only, and reduced motion makes every change instant.
 */
(function () {
  "use strict";

  var root = document.getElementById("root");
  var live = document.getElementById("live");
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var S = { sig: null, kind: null, args: null, front: 0, pos: 0, anim: null, queued: 0, mapSvg: null,
            geo: null, revealK: 1, revealAnim: null, revealGen: null, revealTimer: null,
            cam: null, focus: null, flight: null };

  // ---------------------------------------------------------------- protocol
  function send(type, data) {
    var msg = { isStreamlitMessage: true, type: type };
    for (var k in data || {}) msg[k] = data[k];
    window.parent.postMessage(msg, "*");
  }
  function choose(value) {
    send("streamlit:setComponentValue", {
      value: { value: value, nonce: Date.now() + Math.random() },
      dataType: "json",
    });
  }

  // ------------------------------------------------------------------ helpers
  function el(tag, cls, attrs) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    return e;
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    return e;
  }
  function ill(art) {
    var s = svgEl("svg", { "class": "ill", viewBox: "0 0 64 64", "aria-hidden": "true", focusable: "false" });
    s.appendChild(svgEl("use", { href: "#" + art }));
    return s;
  }
  // One picture per item (cut from the supplied category sheets): a single
  // <img>, object-fit: contain. Items without a picture keep their sprite.
  function illFor(item) {
    if (item && item.image) {
      var img = el("img", "ill ill-img", { src: item.image, alt: "", draggable: "false" });
      img.decoding = "async";
      return img;
    }
    return ill(item ? item.art : "unknown");
  }
  function countText(n) {
    if (n === null || n === undefined) return "";
    return Number(n).toLocaleString() + (n === 1 ? " lead" : " leads");
  }
  // NumberFlow-style count-up (aria-hidden; the real value stays in the
  // item's aria-label). Each digit is a 0-9 column that rolls from 0 to its
  // target; the ones place rolls two extra cycles and the tens one, so it
  // reads as counting. Separators and words stay fixed.
  function countRoll(n, delayMs) {
    var text = countText(n);
    if (!text) return null;
    var wrap = el("span", "pk-num", { "aria-hidden": "true" });
    var digitsLeft = (text.match(/[0-9]/g) || []).length;
    for (var i = 0; i < text.length; i++) {
      var ch = text.charAt(i);
      if (ch >= "0" && ch <= "9") {
        digitsLeft -= 1;                       // 0 = ones place
        var cycles = digitsLeft === 0 ? 2 : digitsLeft === 1 ? 1 : 0;
        var col = el("span", "pk-d");
        var strip = el("span", "pk-strip");
        for (var c = 0; c <= cycles; c++) {
          for (var d = 0; d < 10; d++) {
            var cell = el("span");
            cell.textContent = String(d);
            strip.appendChild(cell);
          }
        }
        strip.style.setProperty("--d", String(cycles * 10 + Number(ch)));
        strip.style.animationDelay = delayMs + "ms";
        col.appendChild(strip);
        wrap.appendChild(col);
      } else {
        var fixed = el("span", "pk-c");
        fixed.textContent = ch;
        wrap.appendChild(fixed);
      }
    }
    return wrap;
  }
  function ariaFor(item) {
    var c = countText(item.count);
    return c ? item.label + ", " + c : item.label;
  }
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function ms(name, fallback) {
    var v = cssVar(name);
    var m = /^([0-9.]+)(ms|s)$/.exec(v);
    if (!m) return fallback;
    return parseFloat(m[1]) * (m[2] === "s" ? 1000 : 1);
  }
  function bezier(spec) {
    // cubic-bezier(x1, y1, x2, y2) -> easing function (the shared --pan-ease)
    var m = /cubic-bezier\(([^)]+)\)/.exec(spec || "");
    var p = m ? m[1].split(",").map(parseFloat) : [0, 0, 0.2, 1];
    var x1 = p[0], y1 = p[1], x2 = p[2], y2 = p[3];
    function at(a, b, t) { return 3 * a * t * (1 - t) * (1 - t) + 3 * b * t * t * (1 - t) + t * t * t; }
    return function (x) {
      var lo = 0, hi = 1, t = x;
      for (var i = 0; i < 24; i++) {
        t = (lo + hi) / 2;
        if (at(x1, x2, t) < x) lo = t; else hi = t;
      }
      return at(y1, y2, t);
    };
  }
  function shortestStep(front, target, n) {
    if (n <= 1) return 0;
    var half = Math.floor(n / 2);
    return ((target - front + n + half) % n) - half;
  }
  function glassLevel(index, front, n) {
    var d = Math.min(((index - front) % n + n) % n, ((front - index) % n + n) % n);
    if (d === 0) return 0;
    return (d === 1 || n <= 4) ? 1 : 2;
  }

  // ------------------------------------------------------------------ palette
  function isDark(theme) {
    if (theme && theme.base) return theme.base === "dark";
    var bg = (theme && theme.backgroundColor) || "";
    var m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(bg);
    if (!m) return false;
    var l = 0.2126 * parseInt(m[1], 16) + 0.7152 * parseInt(m[2], 16) + 0.0722 * parseInt(m[3], 16);
    return l < 128;
  }
  function applyPalette(args, theme) {
    // All variables are set in one pass, so the frame never mixes modes.
    var values = (args.palette || {})[isDark(theme) ? "dark" : "light"] || {};
    var style = document.documentElement.style;
    for (var k in values) style.setProperty(k, values[k]);
    style.setProperty("--h", args.height + "px");
    document.documentElement.toggleAttribute("data-dark", isDark(theme));
    if (theme && theme.font) document.body.style.fontFamily = theme.font;
  }

  // ------------------------------------------------------------------ sprite
  var spriteReady = null;
  function loadSprite() {
    if (!spriteReady) {
      spriteReady = fetch("illustrations.svg").then(function (r) { return r.text(); }).then(function (txt) {
        var holder = el("div", "sr", { "aria-hidden": "true" });
        holder.innerHTML = txt;
        document.body.appendChild(holder);
      }).catch(function () {});
    }
    return spriteReady;
  }

  // -------------------------------------------------------------------- ring
  function buildRing(args) {
    var view = el("div", "view ring");
    var stage = el("div", "stage", { tabindex: "0", role: "group", "aria-label": args.column_label || "Groups" });
    var items = args.items;
    items.forEach(function (it, i) {
      var item = el("div", "item", { role: "button", tabindex: "-1", "aria-label": ariaFor(it), "data-i": String(i) });
      var card = el("div", "card");
      card.appendChild(illFor(it));
      var lbl = el("div", "lbl"); lbl.textContent = it.label; card.appendChild(lbl);
      var cnt = el("div", "cnt"); cnt.textContent = countText(it.count); card.appendChild(cnt);
      item.appendChild(card);
      item.appendChild(el("div", "glass glass-1"));
      item.appendChild(el("div", "glass glass-2"));
      item.addEventListener("click", function () { onItemClick(i); });
      stage.appendChild(item);
    });
    var left = el("button", "rot rot-left", { type: "button", "aria-label": "Rotate left" });
    left.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var right = el("button", "rot rot-right", { type: "button", "aria-label": "Rotate right" });
    right.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    left.addEventListener("click", function () { stepBy(-1); });
    right.addEventListener("click", function () { stepBy(1); });
    stage.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); stepBy(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); stepBy(1); }
      else if ((e.key === "Enter" || e.key === " ") && S.args) { e.preventDefault(); choose(S.args.items[S.front].value); }
    });
    view.appendChild(stage);
    view.appendChild(left);
    view.appendChild(right);
    return view;
  }

  // Measure once (rebuild, resize, rotation start); layoutRing() then does
  // no DOM reads, so animation frames never force a layout.
  function measureRing() {
    var w = root.clientWidth || 600;
    S.geo = {
      items: root.querySelectorAll(".item"),
      // Narrow screens: the floor scales with the width, so side items stay
      // inside the frame instead of being cut at its edges.
      R: Math.min(Math.max(w * 0.34, Math.min(140, w * 0.3)), 300),
      s1: parseFloat(cssVar("--pan-glass-scale-1")) || 0.92,
      s2: parseFloat(cssVar("--pan-glass-scale-2")) || 0.86,
    };
  }

  // Part 9: real 3D. Each item gets its angle on the circle (--a, in
  // degrees, from the unbounded position S.pos so a turn never goes the long
  // way round) and the radius (--R); the view gets the perspective. The CSS
  // transition on --a does the motion; this only writes the end values.
  function layoutRing() {
    if (!S.geo) measureRing();
    var items = S.geo.items;
    var n = items.length;
    if (!n) return;
    var R = (S.geo.R * S.revealK).toFixed(1) + "px";  // the reveal grows the ring
    var stage = root.querySelector(".stage");
    var view = root.querySelector(".view.ring");
    if (stage) stage.style.setProperty("--R", R);
    if (view) view.style.setProperty("--persp", Math.max(900, S.geo.R * 3.2).toFixed(0) + "px");
    var step = 360 / n;
    for (var i = 0; i < n; i++) {
      items[i].style.setProperty("--a", ((i - S.pos) * step).toFixed(2) + "deg");
      items[i].style.setProperty("--R", R);
    }
  }

  // Place without motion (first draw, resize, reduced motion), then allow it.
  function settleRing() {
    root.classList.add("no-anim");
    layoutRing();
    void root.offsetWidth;
    if (!reduce.matches) {
      requestAnimationFrame(function () { root.classList.remove("no-anim"); });
    }
  }

  function setLevels() {
    var items = root.querySelectorAll(".item");
    var n = items.length;
    var sel = S.args ? S.args.selected : null;
    for (var i = 0; i < n; i++) {
      items[i].setAttribute("data-level", String(glassLevel(i, S.front, n)));
      items[i].classList.toggle("is-selected", !!sel && S.args.items[i].value === sel);
      items[i].setAttribute("tabindex", i === S.front ? "0" : "-1");
    }
  }

  function announce() {
    if (!S.args || !S.args.items[S.front]) return;
    live.textContent = ariaFor(S.args.items[S.front]);
  }

  // Part 9: S.pos moves by the shortest step and is never wrapped, like the
  // running angle of a CSS carousel; the transition on --a carries the turn,
  // and a click mid-turn simply retargets it from where it is.
  function rotateTo(target, animate) {
    var n = S.args.items.length;
    var steps = shortestStep(S.front, target, n);
    S.front = ((target % n) + n) % n;
    S.pos += steps;
    setLevels();                                        // glass crossfades in step
    if (!animate || reduce.matches) { settleRing(); return; }
    layoutRing();
  }

  function stepBy(dir) {
    if (!S.args) return;
    var n = S.args.items.length;
    var target = ((S.front + dir) % n + n) % n;
    rotateTo(target, true);
    announce();
    choose(S.args.items[target].value);
  }

  function onItemClick(i) {
    if (!S.args) return;
    if (i !== S.front) { rotateTo(i, true); announce(); }
    if (S.args.items[i].value !== S.args.selected) choose(S.args.items[i].value);
  }

  // ------------------------------------------------------------------ toggle
  function buildToggle(args) {
    var view = el("div", "view");
    var box = el("div", "toggle" + (args.yes_no ? " yes-no" : ""));
    if (args.yes_no) {
      var head = el("div", "toggle-head");
      // With option pictures the column name alone heads the card.
      var pictured = args.items.some(function (it) { return !!it.image; });
      if (!pictured) head.appendChild(ill(args.column_art || "unknown"));
      var hl = el("div", "lbl"); hl.textContent = args.column_label || ""; head.appendChild(hl);
      box.appendChild(head);
    }
    var opts = el("div", "options", { role: "radiogroup", "aria-label": args.column_label || "Groups" });
    args.items.forEach(function (it, i) {
      var b = el("button", "opt", { type: "button", role: "radio", "aria-checked": "false", "aria-label": ariaFor(it), "data-i": String(i) });
      b.appendChild(illFor(it));
      // Yes/no: the column name is the heading, so the option shows "Yes" /
      // "No"; its aria-label keeps the full phrase (Requirement 15.16).
      var shown = args.yes_no && it.label.indexOf(": ") >= 0 ? it.label.split(": ").pop() : it.label;
      var lbl = el("div", "lbl"); lbl.textContent = shown; b.appendChild(lbl);
      var cnt = el("div", "cnt"); cnt.textContent = countText(it.count); b.appendChild(cnt);
      b.addEventListener("click", function () {
        if (S.args && it.value !== S.args.selected) choose(it.value);
      });
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          var all = opts.querySelectorAll(".opt");
          all[(i + 1) % all.length].focus();
        }
      });
      opts.appendChild(b);
    });
    box.appendChild(opts);
    view.appendChild(box);
    return view;
  }

  function syncToggle() {
    var sel = S.args.selected;
    var box = root.querySelector(".toggle");
    var any = false;
    root.querySelectorAll(".opt").forEach(function (b, i) {
      var on = !!sel && S.args.items[i].value === sel;
      any = any || on;
      b.setAttribute("aria-checked", on ? "true" : "false");
      b.setAttribute("tabindex", on || (!sel && i === 0) ? "0" : "-1");
    });
    if (box) box.classList.toggle("has-choice", any);
  }

  // --------------------------------------------------------------------- map
  var mapReady = null;
  function loadMap() {
    if (!mapReady) {
      mapReady = fetch("ph_regions.svg").then(function (r) { return r.text(); });
    }
    return mapReady;
  }

  function buildMap(args) {
    var view = el("div", "view");
    var wrap = el("div", "map");
    var box = el("div", "map-box");
    var credit = el("div", "credit");
    credit.textContent = args.credit || "NAMRIA, PSA via OCHA";
    wrap.appendChild(box);
    wrap.appendChild(credit);
    view.appendChild(wrap);
    loadMap().then(function (txt) {
      box.innerHTML = txt;
      var svg = box.querySelector("svg");
      if (!svg) return;
      svg.setAttribute("role", "group");
      svg.setAttribute("aria-label", args.column_label || "Region");
      var defs = svgEl("defs");
      // Diamond_Lattice: original generic geometry in map units, one
      // userSpaceOnUse pattern so it runs unbroken across every area.
      var pat = svgEl("pattern", { id: "pk-lattice", patternUnits: "userSpaceOnUse", width: "9", height: "9", patternTransform: "rotate(45)" });
      pat.appendChild(svgEl("rect", { "class": "lat-b", width: "9", height: "9" }));
      pat.appendChild(svgEl("rect", { "class": "lat-a", x: "1.2", y: "1.2", width: "6.6", height: "6.6" }));
      defs.appendChild(pat);
      // Fluid edge for the fill: turbulence displaces the growing circle's rim.
      var fluid = svgEl("filter", { id: "pk-fluid", x: "-20%", y: "-20%", width: "140%", height: "140%" });
      fluid.appendChild(svgEl("feTurbulence", { type: "fractalNoise", baseFrequency: "0.06", numOctaves: "2", seed: "7", result: "n" }));
      fluid.appendChild(svgEl("feDisplacementMap", { "in": "SourceGraphic", in2: "n", scale: "9", xChannelSelector: "R", yChannelSelector: "G" }));
      defs.appendChild(fluid);
      var blur = svgEl("filter", { id: "pk-blur", x: "-10%", y: "-10%", width: "120%", height: "120%" });
      blur.appendChild(svgEl("feGaussianBlur", { stdDeviation: "3" }));
      defs.appendChild(blur);
      svg.insertBefore(defs, svg.firstChild);
      // Pre-drawn shadows (one per area) behind every area; only opacity moves.
      var shadows = svgEl("g", { "aria-hidden": "true" });
      svg.querySelectorAll("g[data-area]").forEach(function (g) {
        var p = g.querySelector(".area-shape");
        var sh = svgEl("path", { "class": "shadow", d: p.getAttribute("d"), "fill-rule": "evenodd", filter: "url(#pk-blur)", transform: "translate(0 4)", "data-for": g.getAttribute("data-area") });
        shadows.appendChild(sh);
        g.addEventListener("click", function (e) { onArea(g.getAttribute("data-area"), e); });
        g.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onArea(g.getAttribute("data-area")); }
        });
        g.addEventListener("mouseenter", function () { if (!g.classList.contains("is-muted")) sh.classList.add("is-on"); });
        g.addEventListener("mouseleave", function () { if (!g.classList.contains("is-selected")) sh.classList.remove("is-on"); });
        g.addEventListener("focus", function () { if (!g.classList.contains("is-muted")) sh.classList.add("is-on"); });
        g.addEventListener("blur", function () { if (!g.classList.contains("is-selected")) sh.classList.remove("is-on"); });
      });
      svg.insertBefore(shadows, defs.nextSibling);
      S.mapSvg = svg;
      S.cam = null;
      S.focus = null;
      S.mapSel = undefined;
      layoutMap();
      syncMap();
    }).catch(function () {});
    return view;
  }

  // ------------------------------------------------------------- map camera
  // A high-altitude camera: the map is drawn large enough to fill the section
  // (pieces crop at the edges), pitched and banked (--pan-map-pitch,
  // --pan-map-bearing) under a deep perspective so it reads as seen from near
  // space. The camera looks at the selected region; choosing another flies
  // there (flyTo). Measured once per build/resize, never per frame.
  var MAP_FILL = 0.85;        // map width as a share of the section width
  function layoutMap() {
    var svg = S.mapSvg;
    if (!svg) return;
    var box = svg.parentNode;
    var vb = svg.viewBox.baseVal;
    var w = box.clientWidth || 600, h = box.clientHeight || 300;
    var ws = Math.max(w * MAP_FILL, h * 1.25 * vb.width / vb.height);
    var hs = ws * vb.height / vb.width;
    svg.style.width = ws + "px";
    svg.style.height = hs + "px";
    box.style.perspective = Math.max(2000, hs * 2.4) + "px";   // deep: near-space flatness
    S.cam = { w: w, h: h, ws: ws, hs: hs, vb: vb,
              pitch: cssVar("--pan-map-pitch") || "45deg", bearing: cssVar("--pan-map-bearing") || "-15deg" };
    // --pan-lift is in CSS px; the hover/selected lift runs in viewBox units.
    var px = parseFloat(cssVar("--pan-lift")) || 3;
    svg.style.setProperty("--lift", (px * vb.height / hs).toFixed(2) + "px");
    var f = focusFor(S.args ? S.args.selected : null);
    S.focus = f;
    svg.style.transform = camTransform(f, 1);
  }
  function focusFor(area) {
    // Centre of the area (or of the whole map) in the svg's own px.
    var svg = S.mapSvg, c = S.cam, b = null;
    var g = area ? svg.querySelector('g[data-area="' + area + '"] .area-shape') : null;
    try { b = (g || svg.querySelector("g[data-area]").parentNode).getBBox(); } catch (e) { b = null; }
    if (!b || !b.width) b = { x: c.vb.x, y: c.vb.y, width: c.vb.width, height: c.vb.height };
    return { x: (b.x + b.width / 2 - c.vb.x) / c.vb.width * c.ws,
             y: (b.y + b.height / 2 - c.vb.y) / c.vb.height * c.hs };
  }
  function camTransform(f, alt) {
    // Same function list every time, so flights interpolate function by function.
    var c = S.cam;
    return "translate(" + (c.w / 2).toFixed(1) + "px," + (c.h / 2).toFixed(1) + "px) " +
           "rotateX(" + c.pitch + ") rotateZ(" + c.bearing + ") scale(" + alt + ") " +
           "translate(" + (-f.x).toFixed(1) + "px," + (-f.y).toFixed(1) + "px)";
  }
  function flyTo(area) {
    var svg = S.mapSvg;
    if (!svg || !S.cam) return;
    var to = focusFor(area);
    var from = S.focus || to;
    if (Math.abs(to.x - from.x) < 1 && Math.abs(to.y - from.y) < 1) return;
    var end = camTransform(to, 1);
    if (reduce.matches) {                      // no flight: the camera cuts
      if (S.flight) S.flight.cancel();
      svg.style.transform = end; S.focus = to; return;
    }
    // Interrupted mid-flight: start from where the camera is now.
    var start = S.flight ? getComputedStyle(svg).transform : camTransform(from, 1);
    if (S.flight) S.flight.cancel();
    var mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
    var dur = ms("--pan-dur-fly", 900);
    var ease = cssVar("--pan-ease-fly") || "ease-in-out";
    var keys = S.flight
      ? [{ transform: start }, { transform: end }]
      : [{ transform: start }, { transform: camTransform(mid, 0.86), offset: 0.5 }, { transform: end }];
    svg.style.transform = end;
    S.flight = svg.animate(keys, { duration: dur, easing: ease });
    S.flight.onfinish = function () { S.flight = null; };
    S.focus = to;
  }

  // -------------------------------------------------------------- fluid fill
  // Selecting a region floods it with the selected red from where it was
  // clicked (or from its centre for the dropdown and keyboard), like water
  // filling a tray: a circle clipped to the region's outline grows outward
  // with a turbulent, wobbling edge, fast at first and slowing as it spreads.
  function clientToMap(clientX, clientY) {
    // Invert the camera (perspective x pitch x bank x pan) for the map plane:
    // a 3x3 homography from the svg's own px to the box's px.
    var svg = S.mapSvg, box = svg.parentNode, c = S.cam;
    var r = box.getBoundingClientRect();
    var sx = clientX - r.left, sy = clientY - r.top;
    var d = parseFloat(box.style.perspective) || 2000;
    var pd = new DOMMatrix(); pd.m34 = -1 / d;
    var m = new DOMMatrix().translate(c.w / 2, c.h / 2).multiply(pd)
      .translate(-c.w / 2, -c.h / 2).multiply(new DOMMatrix(getComputedStyle(svg).transform));
    var a1 = m.m11 - sx * m.m14, b1 = m.m21 - sx * m.m24, c1 = sx * m.m44 - m.m41;
    var a2 = m.m12 - sy * m.m14, b2 = m.m22 - sy * m.m24, c2 = sy * m.m44 - m.m42;
    var det = a1 * b2 - a2 * b1;
    if (!det) return null;
    var x = (c1 * b2 - c2 * b1) / det, y = (a1 * c2 - a2 * c1) / det;
    return { x: c.vb.x + x / c.ws * c.vb.width, y: c.vb.y + y / c.hs * c.vb.height };
  }
  function clipFor(g, area) {
    var id = "pk-clip-" + area.replace(/[^A-Za-z0-9_-]/g, "");
    var svg = S.mapSvg;
    if (!svg.getElementById(id)) {
      var cp = svgEl("clipPath", { id: id });
      g.querySelectorAll(".area-shape").forEach(function (sh) {
        cp.appendChild(svgEl("path", { d: sh.getAttribute("d"), "fill-rule": "evenodd" }));
      });
      svg.querySelector("defs").appendChild(cp);
    }
    return id;
  }
  function fluidFill(area, origin) {
    var svg = S.mapSvg;
    if (!svg) return;
    var g = svg.querySelector('g[data-area="' + area + '"]');
    if (!g || reduce.matches) return;
    svg.querySelectorAll(".fill-wave").forEach(function (w) { w.remove(); });
    svg.querySelectorAll("g.is-filling").forEach(function (x) { x.classList.remove("is-filling"); });
    var b = g.querySelector(".area-shape").getBBox();
    g.querySelectorAll(".area-shape").forEach(function (sh) {
      var bb = sh.getBBox();
      var x0 = Math.min(b.x, bb.x), y0 = Math.min(b.y, bb.y);
      b = { x: x0, y: y0, width: Math.max(b.x + b.width, bb.x + bb.width) - x0,
            height: Math.max(b.y + b.height, bb.y + bb.height) - y0 };
    });
    var o = origin || { x: b.x + b.width / 2, y: b.y + b.height / 2 };
    var reach = Math.max(
      Math.hypot(o.x - b.x, o.y - b.y), Math.hypot(o.x - b.x - b.width, o.y - b.y),
      Math.hypot(o.x - b.x, o.y - b.y - b.height), Math.hypot(o.x - b.x - b.width, o.y - b.y - b.height));
    var wave = svgEl("g", { "class": "fill-wave", "clip-path": "url(#" + clipFor(g, area) + ")", "aria-hidden": "true" });
    var drop = svgEl("circle", { cx: o.x.toFixed(2), cy: o.y.toFixed(2), r: (reach * 1.15).toFixed(2), filter: "url(#pk-fluid)" });
    wave.appendChild(drop);
    g.appendChild(wave);
    g.classList.add("is-filling");             // keep the old look under the rising fill
    var anim = drop.animate([{ transform: "scale(0)" }, { transform: "scale(1)" }],
      { duration: ms("--pan-dur-fill", 1000), easing: cssVar("--pan-ease-fill") || "ease-out", fill: "forwards" });
    anim.onfinish = function () {
      g.classList.remove("is-filling");
      wave.remove();
    };
  }

  function itemFor(area) {
    var items = (S.args && S.args.items) || [];
    for (var i = 0; i < items.length; i++) if (items[i].value === area) return items[i];
    return null;
  }

  function syncMap() {
    var svg = S.mapSvg;
    if (!svg || !S.args) return;
    var sel = S.args.selected;
    // A dropdown change fills from the centre; a click already filled from
    // its point (S.filledFor), which is consumed only when that selection
    // arrives (an earlier render may still carry the old one).
    if (sel && S.mapSel !== undefined && sel !== S.mapSel && S.filledFor !== sel) fluidFill(sel, null);
    if (sel === S.filledFor) S.filledFor = null;
    S.mapSel = sel;
    if (!S.flight || sel) flyTo(sel);            // no-op when already there
    var selItem = sel ? itemFor(sel) : null;
    svg.querySelectorAll("g[data-area]").forEach(function (g) {
      var area = g.getAttribute("data-area");
      var it = itemFor(area);
      var selectable = !!(it && it.selectable);
      var on = !!selItem && area === sel;
      g.classList.toggle("is-muted", !selectable);
      g.classList.toggle("is-selected", on);
      g.classList.toggle("is-dimmed", !!selItem && !on && selectable);
      if (selectable) {
        g.setAttribute("tabindex", "0");
        g.setAttribute("role", "button");
        g.setAttribute("aria-label", ariaFor(it));
        g.removeAttribute("aria-disabled");
      } else {
        g.setAttribute("tabindex", "-1");
        g.setAttribute("role", "img");
        g.setAttribute("aria-label", it ? ariaFor(it) : area);
        g.setAttribute("aria-disabled", "true");
      }
      var sh = svg.querySelector('.shadow[data-for="' + area + '"]');
      if (sh) sh.classList.toggle("is-on", on);
    });
  }

  function onArea(area, e) {
    var it = itemFor(area);
    if (!it || !it.selectable || !S.args) return;
    if (area === S.args.selected) return;                // already selected: no event
    S.filledFor = area;
    fluidFill(area, e && e.clientX !== undefined ? clientToMap(e.clientX, e.clientY) : null);
    flyTo(area);                                         // fly now, before the rerun
    choose(area);
  }

  // ------------------------------------------------------------------ reveal
  // Plays once per persona generation (args.reveal_gen): carousel inside out
  // (front first, then neighbours by ring distance, ring radius 60% -> 100%),
  // map bottom to top, toggles bottom to top a beat later; counts roll up.
  function seenGen(gen) {
    try { return window.sessionStorage.getItem("p8-reveal-gen") === gen; } catch (e) { return false; }
  }
  function markGen(gen) {
    try { window.sessionStorage.setItem("p8-reveal-gen", gen); } catch (e) { return; }
  }
  function ringDistance(i, front, n) {
    return Math.min(((i - front) % n + n) % n, ((front - i) % n + n) % n);
  }
  function swapCount(node, n, delayMs) {
    if (!node) return;
    var roll = countRoll(n, delayMs);
    if (!roll) return;
    node.textContent = "";
    node.appendChild(roll);
  }
  function playReveal() {
    var reduced = reduce.matches;
    var cls = reduced ? "is-revealing-still" : "is-revealing";
    var ringStep = ms("--pan-reveal-ring-step", 70);
    var countStep = ms("--pan-count-step", 60);
    var lag = ms("--pan-reveal-toggle-lag", 80);
    var dur = ms("--pan-dur-reveal", 400);
    var countDur = 2 * ms("--pan-dur-roll", 600);
    // Start as the finishing loader fades (--pan-reveal-start on the page:
    // story + fireworks + hold); items stay hidden until then.
    // Part 9: no fireworks, so the spark time is not part of the wait.
    var lead = reduced ? 0 : ms("--pan-dur-finish", 800) + ms("--pan-dur-hold", 150)
      + ms("--pan-dur-finish-linger", 200);
    var lastStart = 0;
    root.style.setProperty("--pk-start", lead + "ms");
    root.classList.remove("is-revealing", "is-revealing-still");
    void root.offsetWidth;                                // restart if replayed
    root.classList.add(cls);
    if (S.kind === "carousel") {
      var items = root.querySelectorAll(".item");
      var n = items.length;
      for (var i = 0; i < n; i++) {
        var rd = ringDistance(i, S.front, n);
        items[i].style.setProperty("--rd", String(rd));
        var start = rd * ringStep;
        lastStart = Math.max(lastStart, start);
        if (!reduced) swapCount(items[i].querySelector(".cnt"), S.args.items[i].count, lead + start);
      }
      if (!reduced) {
        var ease = bezier(cssVar("--pan-ease"));
        var t0 = null;
        if (S.revealAnim) cancelAnimationFrame(S.revealAnim);
        measureRing();
        S.revealK = 0.6;
        settleRing();
        var frame = function (ts) {
          if (t0 === null) t0 = ts + lead;
          if (ts < t0) { S.revealAnim = requestAnimationFrame(frame); return; }
          var k = Math.min((ts - t0) / dur, 1);
          S.revealK = 0.6 + 0.4 * ease(k);
          layoutRing();
          S.revealAnim = k < 1 ? requestAnimationFrame(frame) : null;
        };
        S.revealAnim = requestAnimationFrame(frame);
      }
    } else if (S.kind === "toggle" && !reduced) {
      root.querySelectorAll(".opt").forEach(function (b, i) {
        var start = lag + i * countStep;
        lastStart = Math.max(lastStart, start);
        swapCount(b.querySelector(".cnt"), S.args.items[i].count, lead + start);
      });
    }
    // Back to plain markup once everything has landed (no lingering layers).
    clearTimeout(S.revealTimer);
    S.revealTimer = setTimeout(function () {
      root.classList.remove("is-revealing", "is-revealing-still");
      root.querySelectorAll(".cnt").forEach(function (c, i) {
        if (S.args && S.args.items[i]) c.textContent = countText(S.args.items[i].count);
      });
    }, lead + lastStart + Math.max(dur, countDur) + 100);
  }

  // ------------------------------------------------------------------ render
  function render(args, theme) {
    applyPalette(args, theme);
    var sig = args.kind + "|" + args.items.map(function (i) { return i.value; }).join("\u0001");
    var rebuild = sig !== S.sig;
    S.args = args;
    if (rebuild) {
      S.sig = sig;
      S.kind = args.kind;
      S.mapSvg = null;
      S.geo = null;
      root.innerHTML = "";
      if (args.kind === "carousel") {
        root.appendChild(buildRing(args));
        var idx = args.items.findIndex(function (i) { return i.value === args.selected; });
        if (idx < 0) idx = Math.max(0, args.items.findIndex(function (i) { return i.value === args.front_value; }));
        S.front = idx; S.pos = idx;
        setLevels();
        settleRing();
      } else if (args.kind === "toggle") {
        root.appendChild(buildToggle(args));
        syncToggle();
      } else if (args.kind === "map") {
        root.appendChild(buildMap(args));
      }
    } else if (args.kind === "carousel") {
      // Dropdown -> visual: rotate the newly selected item to the front by the
      // shortest direction (Requirement 12.15); "All groups" keeps the front.
      var t = args.items.findIndex(function (i) { return i.value === args.selected; });
      if (t >= 0 && t !== S.front) rotateTo(t, true); else setLevels();
    } else if (args.kind === "toggle") {
      syncToggle();
    } else if (args.kind === "map") {
      syncMap();
    }
    if (args.reveal_gen && args.reveal_gen !== S.revealGen && !seenGen(args.reveal_gen)) {
      S.revealGen = args.reveal_gen;
      markGen(args.reveal_gen);
      playReveal();
    }
    send("streamlit:setFrameHeight", { height: args.height });
  }

  window.addEventListener("message", function (e) {
    var d = e.data;
    if (!d || d.type !== "streamlit:render" || !d.args) return;
    loadSprite().then(function () { render(d.args, d.theme); });
  });
  window.addEventListener("resize", function () {
    if (S.kind === "carousel") { measureRing(); settleRing(); }
    if (S.kind === "map") { if (S.flight) S.flight.cancel(); S.flight = null; layoutMap(); }
  });
  send("streamlit:componentReady", { apiVersion: 1 });
})();
