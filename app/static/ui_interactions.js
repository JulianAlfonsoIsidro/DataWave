/* Part 9 page behaviours (injected once by app/ui_effects, like the page lock).
 *
 * 1. Theme switch as liquid. A click on the ⋮ menu's System / Light / Dark
 *    is held while a liquid in the new theme's background colour rises
 *    from the bottom, its top edge bubbling (round blobs melted together
 *    by an SVG blur + threshold filter, styles.css section 21). When it
 *    covers the page the click goes through, Streamlit switches the theme
 *    underneath, and the liquid fades away. Skipped with reduced motion or
 *    when the choice would not change the colours (the click goes through).
 *
 * 2. Hover texts. Streamlit's help tooltips also open on focus, so a pointer
 *    click (which focuses the button) left them pinned open. A focus that a
 *    pointer caused, inside a tooltip trigger, is kept from reaching
 *    Streamlit; keyboard focus still opens them. Streamlit unmounts a closing
 *    tooltip at once, so the removed node is put back for one fade-out
 *    (styles.css section 20) and then removed.
 *
 * 4. Pressed buttons stay red (data-p9-pressed) until the rerun or job they
 *    started has finished, then fade back (styles.css section 27).
 *
 * Reads the DOM only; never talks to Streamlit and changes no widget value.
 */
(function () {
  "use strict";

  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ---- 1. Theme switch ------------------------------------------------- */
  function scheme() {
    var app = document.querySelector('[data-testid="stApp"]');
    return app ? getComputedStyle(app).colorScheme : "";
  }
  function targetScheme(btn) {
    var id = btn.getAttribute("data-testid") || "";
    if (/Dark$/.test(id)) return "dark";
    if (/Light$/.test(id)) return "light";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  var replaying = false;
  var filling = false;

  function tokenMs(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    var n = parseFloat(v);
    if (!isFinite(n)) return fallback;
    return /ms$/.test(v) ? n : n * 1000;
  }
  // The new theme's page colour: a probe in that colour scheme resolves the
  // light-dark() background token without switching anything.
  function bgFor(target) {
    var app = document.querySelector('[data-testid="stApp"]') || document.body;
    var probe = document.createElement("div");
    probe.style.cssText = "position:fixed;inline-size:0;block-size:0;color-scheme:" + target +
      ";background:var(--pan-bg)";
    app.appendChild(probe);
    var c = getComputedStyle(probe).backgroundColor;
    probe.remove();
    return c;
  }
  function blobFilter() {
    if (document.getElementById("p9-blob-defs")) return;
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("id", "p9-blob-defs");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "p9-liquid-defs");
    svg.innerHTML = '<defs><filter id="p9-blob">' +
      '<feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur"/>' +
      '<feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 19 -9"/>' +
      "</filter></defs>";
    document.body.appendChild(svg);
  }
  function liquid(colour) {
    blobFilter();
    var box = document.createElement("div");
    box.className = "p9-liquid";
    box.setAttribute("aria-hidden", "true");
    box.style.setProperty("--liquid", colour);
    var rise = document.createElement("div");
    rise.className = "p9-liquid-rise";
    var bubbles = document.createElement("div");
    bubbles.className = "p9-liquid-bubbles";
    for (var i = 0; i < 48; i++) {
      var b = document.createElement("i");
      var t = 2 + Math.random() * 2;
      b.style.cssText = "--size:" + (2 + Math.random() * 4).toFixed(2) + "rem;--distance:" +
        (6 + Math.random() * 4).toFixed(2) + "rem;--position:" + (-5 + Math.random() * 110).toFixed(1) +
        "%;--time:" + t.toFixed(2) + "s;--delay:" + (-1 * (2 + Math.random() * 2)).toFixed(2) + "s";
      bubbles.appendChild(b);
    }
    var body = document.createElement("div");
    body.className = "p9-liquid-body";
    rise.appendChild(bubbles);
    rise.appendChild(body);
    box.appendChild(rise);
    document.body.appendChild(box);
    return box;
  }

  document.addEventListener("click", function (e) {
    if (replaying || reduce.matches) return;
    var btn = e.target && e.target.closest && e.target.closest('[data-testid^="stMainMenuItem-theme-"]');
    if (!btn || btn.getAttribute("aria-checked") === "true") return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (filling) return;                               // one pour at a time
    var before = scheme();
    var target = targetScheme(btn);
    if (!before || before.indexOf(target) !== -1) {    // no visible change: plain click
      replaying = true; btn.click(); replaying = false;
      return;
    }
    filling = true;
    var box = liquid(bgFor(target));
    var fill = tokenMs("--pan-dur-theme-fill", 1100);
    var fade = tokenMs("--pan-dur-slow", 250);
    void box.offsetWidth;
    box.classList.add("is-rising");
    setTimeout(function () {
      replaying = true;
      btn.click();                                     // Streamlit switches the theme
      replaying = false;
      var t0 = performance.now();
      (function wait() {
        if (scheme() !== before || performance.now() - t0 > 800) {
          box.classList.add("is-done");                // the liquid fades away
          setTimeout(function () { box.remove(); filling = false; }, fade + 50);
        } else {
          setTimeout(wait, 16);
        }
      })();
    }, fill);
  }, true);

  /* ---- 2. Hover texts -------------------------------------------------- */
  var TRIGGER = '[data-testid="stTooltipHoverTarget"]';
  var lastPointer = 0;
  document.addEventListener("pointerdown", function () { lastPointer = performance.now(); }, true);

  function pointerFocus(e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest(TRIGGER)) return;
    if (performance.now() - lastPointer < 800) e.stopImmediatePropagation();
  }
  // Window capture runs before React's listeners on its root.
  window.addEventListener("focusin", pointerFocus, true);
  window.addEventListener("focus", pointerFocus, true);

  function fadeOut(node, parent) {
    if (!node || node.nodeType !== 1 || !parent || !parent.isConnected) return;
    if (!node.querySelector || !node.querySelector('[data-testid="stTooltipContent"]')) return;
    if (node.classList.contains("p9-tip-out")) return;
    node.classList.add("p9-tip-out");
    node.setAttribute("aria-hidden", "true");
    parent.appendChild(node);
    var done = false;
    function remove() { if (!done) { done = true; node.remove(); } }
    node.addEventListener("animationend", remove);
    setTimeout(remove, 400);                           // safety net
  }

  new MutationObserver(function (records) {
    records.forEach(function (r) {
      r.removedNodes.forEach(function (n) { fadeOut(n, r.target); });
    });
  }).observe(document.body, { childList: true, subtree: true });

  /* ---- 3. The ⋮ menu on narrow screens --------------------------------- */
  // Scrolling down past the top hides it (it sat on the cards); any scroll
  // up, or reaching the top, brings it back. CSS applies it under 900px only.
  var lastTop = 0;
  document.addEventListener("scroll", function (e) {
    var el = e.target && e.target.nodeType === 1 ? e.target : document.scrollingElement;
    if (!el || (el.getAttribute && el.getAttribute("data-testid") !== "stMain" && el !== document.scrollingElement)) return;
    var top = el.scrollTop, root = document.documentElement;
    if (top < 48) root.classList.remove("p9-menu-away");
    else if (top > lastTop + 4) root.classList.add("p9-menu-away");
    else if (top < lastTop - 4) root.classList.remove("p9-menu-away");
    lastTop = top;
  }, { capture: true, passive: true });

  /* ---- 4. Pressed buttons stay red until their work is done ------------- */
  // A clicked button keeps data-p9-pressed (styles.css section 27 draws it
  // red) until what it started has finished: the rerun, or for Run Analysis
  // and Build Personas the whole job (page lock, loader and its finish).
  // Then the attribute goes and the red fades out. Streamlit may redraw the
  // button during a job, so it is found again by its st-key class.
  var BTN = ".stButton button, .stDownloadButton button, .stFormSubmitButton button";
  var pressed = [];                                   // {key, el, t0, started, quietSince}
  var pollTimer = null;

  function busy() {
    var app = document.querySelector('[data-testid="stApp"]');
    var root = document.documentElement;
    return (app && app.getAttribute("data-test-script-state") === "running") ||
      root.hasAttribute("data-p8-locked") || root.classList.contains("p9-await-run");
  }
  // How long the page must stay quiet before the red fades. A job button
  // also waits out the loader's finish (story, hold, linger), which plays
  // over the page after the script stops, so the fade is seen.
  function settleMs(key) {
    if (!key || key.indexOf("st-key-p8_btn_") !== 0) return 300;
    return 300 + tokenMs("--pan-dur-finish", 800) + tokenMs("--pan-dur-hold", 150) +
      tokenMs("--pan-dur-finish-linger", 200);
  }
  function keyOf(btn) {
    var holder = btn.closest('[class*="st-key-"]');
    if (!holder) return null;
    var m = holder.className.toString().match(/st-key-[\w-]+/);
    return m ? m[0] : null;
  }
  function currentButton(entry) {
    if (entry.el && entry.el.isConnected) return entry.el;
    if (!entry.key) return null;
    var found = document.querySelectorAll("." + entry.key + " :is(" + BTN + ")");
    for (var i = 0; i < found.length; i++) {
      if (found[i].offsetParent !== null) return (entry.el = found[i]);
    }
    return found[0] ? (entry.el = found[0]) : null;
  }
  function poll() {
    var now = performance.now();
    var isBusy = busy();
    pressed = pressed.filter(function (entry) {
      var btn = currentButton(entry);
      if (isBusy) { entry.started = true; entry.quietSince = 0; }
      else if (!entry.quietSince) entry.quietSince = now;
      // Done: the work ran and has been quiet a moment, or nothing ran
      // (a click that started no rerun); capped at 15 minutes.
      var quiet = entry.quietSince && now - entry.quietSince > settleMs(entry.key);
      var done = (quiet && (entry.started || now - entry.t0 > 1500)) || now - entry.t0 > 900000;
      if (btn) {
        if (done) btn.removeAttribute("data-p9-pressed");
        else btn.setAttribute("data-p9-pressed", "");
      }
      return !done;
    });
    pollTimer = pressed.length ? setTimeout(poll, 100) : null;
  }
  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest(BTN);
    if (!btn || btn.disabled) return;
    var key = keyOf(btn);
    pressed = pressed.filter(function (p) { return p.el !== btn && (!key || p.key !== key); });
    pressed.push({ key: key, el: btn, t0: performance.now(), started: false, quietSince: 0 });
    btn.setAttribute("data-p9-pressed", "");
    if (!pollTimer) pollTimer = setTimeout(poll, 100);
  }, true);

})();
