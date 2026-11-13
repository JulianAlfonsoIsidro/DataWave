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
 * 5. The app's colour scheme is copied to <html data-p9-scheme> so dialogs
 *    drawn outside the app root follow light and dark (section 28).
 *
 * 6. The Bedrock wait line: timer and Mining/Crafting label (section 29).
 *
 * 7. The assistant's live character count for the 500 character limit.
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

  // Owner request: the page itself changes as the water passes, not after.
  // A View Transition snapshots the page in the old theme, Streamlit switches
  // the theme, and the browser snapshots the new page. The new snapshot is
  // revealed through a mask (styles.css section 21), so every box, text and
  // table under the water is already in the new theme and everything above
  // it is still in the old one. Browsers without View Transitions keep the
  // liquid overlay.
  //
  // The water (owner request): a real moving wave surface, level overall.
  // One long, gentle swell travels left to right across the page, and many
  // small ripples ride on it, travelling the same way a little faster. The
  // surface is computed as the sum of the two sine waves at 48 moments over
  // the fill and animated as a changing SVG path (SMIL), so the crests and
  // troughs really travel and change rather than one shape sliding. A
  // separate eased rise lifts the water from under the page to above it.
  // The new theme shows through the water. Each switch gets a fresh image
  // URL so its animation starts from the beginning.
  var waveSeq = 0;
  function waveMask(ms) {
    var W = Math.max(1, window.innerWidth), H = Math.max(1, window.innerHeight);
    // The swell: about one wave across the page; the ripples: about nine.
    var L1 = W * 1.15, A1 = Math.max(10, Math.min(H * 0.055, 44));
    var L2 = Math.max(90, W / 9), A2 = Math.max(4, A1 * 0.28);
    var trav1 = 1.8, trav2 = 5;                         // wavelengths moved over the fill (owner: faster)
    var amp = A1 + A2;
    var step = Math.max(8, Math.round(W / 120));
    // More frames for the faster motion: a ripple moves about a tenth of its
    // length between frames, so the blend between them stays smooth.
    var frames = 48, bottom = H + amp * 4;
    function surface(f) {
      var s = f / (frames - 1), pts = [];
      for (var x = 0; x <= W + step; x += step) {
        var y = A1 * Math.sin(2 * Math.PI * (x / L1 - trav1 * s)) +
                A2 * Math.sin(2 * Math.PI * (x / L2 - trav2 * s) + 1.3);
        pts.push(x + " " + (-y).toFixed(1));
      }
      return "M" + pts.join(" L") + " L" + (W + step) + " " + bottom + " L0 " + bottom + "Z";
    }
    var values = [];
    for (var f = 0; f < frames; f++) values.push(surface(f));
    // Start with the highest crest just under the page; end with the
    // lowest trough just above it, so the page is covered exactly at the end.
    var yFrom = H + amp + 1, yTo = -amp - 1;
    var dur = (ms / 1000).toFixed(3) + "s";
    var svg =
      "<svg xmlns='http://www.w3.org/2000/svg' width='" + W + "' height='" + H +
      "' viewBox='0 0 " + W + " " + H + "' preserveAspectRatio='none'>" +
      "<!--" + (++waveSeq) + "-" + Date.now() + "-->" +
      "<g transform='translate(0 " + yFrom + ")'>" +
      "<animateTransform attributeName='transform' type='translate' from='0 " + yFrom +
      "' to='0 " + yTo + "' dur='" + dur + "' fill='freeze' calcMode='spline' " +
      "keyTimes='0;1' keySplines='0.3 0.1 0.7 0.95'/>" +
      "<path d='" + values[0] + "'><animate attributeName='d' dur='" + dur +
      "' fill='freeze' values='" + values.join(";") + "'/></path></g></svg>";
    return 'url("data:image/svg+xml,' + encodeURIComponent(svg) + '")';
  }
  function waveSwitch(btn, before) {
    var root = document.documentElement;
    root.style.setProperty("--pan-theme-mask", waveMask(tokenMs("--pan-dur-theme-fill", 1000)));
    root.classList.add("p9-theme-wave");                // before the snapshots are styled
    var transition = document.startViewTransition(function () {
      return new Promise(function (resolve) {
        replaying = true;
        btn.click();                                   // Streamlit switches the theme
        replaying = false;
        var t0 = performance.now();
        // Timers only: while the browser waits for this callback it renders
        // nothing, so requestAnimationFrame never fires here. Waiting on it
        // let the transition time out (4 s) and the browser skipped the
        // whole animation.
        (function wait() {
          if (scheme() !== before || performance.now() - t0 > 800) {
            setTimeout(resolve, 60);                   // let React finish the new colours
          } else {
            setTimeout(wait, 16);
          }
        })();
      });
    });
    // A skipped transition rejects these; the theme has still switched.
    transition.ready.catch(function () {});
    transition.finished.catch(function () {}).then(function () {
      root.classList.remove("p9-theme-wave");
      root.style.removeProperty("--pan-theme-mask");
      filling = false;
    });
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
    if (document.startViewTransition) { waveSwitch(btn, before); return; }
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
  /* ---- 4b. Instant answer to a job click ------------------------------- */
  // Run Analysis, Build Personas and "Not sure how many?" start a job whose
  // loader is drawn by the server, a round trip after the click. So the page
  // is dimmed and locked on the click itself (html[data-p9-job-click], a
  // scrim drawn by styles.css). page_lock.js hands the scrim to the real
  // loader when it mounts and clears the mark. If no loader ever comes (a
  // rejected form, an empty audience) the mark goes once the page is idle.
  var JOB_KEYS = ["st-key-p8_btn_", "st-key-persona_suggest"];
  var jobClickAt = 0, jobSeenBusy = false, jobTimer = null;
  function isJobKey(key) {
    return !!key && JOB_KEYS.some(function (k) { return key.indexOf(k) === 0; });
  }
  function clearJobClick() {
    document.documentElement.removeAttribute("data-p9-job-click");
    jobClickAt = 0; jobSeenBusy = false;
    if (jobTimer) { clearInterval(jobTimer); jobTimer = null; }
  }
  function watchJobClick() {
    if (!document.documentElement.hasAttribute("data-p9-job-click")) { clearJobClick(); return; }
    var now = performance.now();
    if (document.querySelector(".pan-loading:not(.is-finishing)")) return;   // page_lock.js takes over
    var app = document.querySelector('[data-testid="stApp"]');
    var running = !!app && app.getAttribute("data-test-script-state") === "running";
    if (running) jobSeenBusy = true;
    // Idle again after the rerun ran (or nothing ran at all): no loader coming.
    if ((jobSeenBusy && !running && now - jobClickAt > 400) || now - jobClickAt > 3000) clearJobClick();
  }
  window.addEventListener("p9-job-handoff", clearJobClick);

  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest && e.target.closest(BTN);
    if (!btn || btn.disabled) return;
    if (isJobKey(keyOf(btn))) {
      document.documentElement.setAttribute("data-p9-job-click", "");
      jobClickAt = performance.now(); jobSeenBusy = false;
      if (!jobTimer) jobTimer = setInterval(watchJobClick, 100);
    }
    var key = keyOf(btn);
    pressed = pressed.filter(function (p) { return p.el !== btn && (!key || p.key !== key); });
    pressed.push({ key: key, el: btn, t0: performance.now(), started: false, quietSince: 0 });
    btn.setAttribute("data-p9-pressed", "");
    if (!pollTimer) pollTimer = setTimeout(poll, 100);
  }, true);

  /* ---- 5. Colour scheme outside the app ------------------------------- */
  // Streamlit sets the theme's colour scheme on its app root only. Dialogs
  // (Help And FAQs) and popovers are drawn outside it, so the scheme is
  // copied to <html data-p9-scheme> (styles.css section 28). A cheap check,
  // twice a second; it writes only when the scheme changes.
  function syncScheme() {
    var s = scheme();
    var v = /dark/.test(s) && !/light/.test(s) ? "dark" : (/light/.test(s) && !/dark/.test(s) ? "light" : "");
    var root = document.documentElement;
    if (v && root.getAttribute("data-p9-scheme") !== v) root.setAttribute("data-p9-scheme", v);
    if (!v && root.hasAttribute("data-p9-scheme")) root.removeAttribute("data-p9-scheme");
  }
  syncScheme();
  setInterval(syncScheme, 500);

  /* ---- 6. The Bedrock wait line --------------------------------------- */
  // Each .pan-wait carries data-start (ms). The timer ticks every 100 ms; the
  // label swaps between Mining and Crafting every 1.6 s with a short fade.
  // With reduced motion the label stays (styles.css keeps the grid still);
  // the timer still counts (spec part9-layout-fixes, Requirement 35.6).
  var WAIT_LABELS = ["Mining", "Crafting"];
  function fmtElapsed(ms) {
    var total = Math.max(0, ms) / 1000;
    if (total < 60) return total.toFixed(1) + "s";
    return Math.floor(total / 60) + "m " + (total % 60).toFixed(1) + "s";
  }
  setInterval(function () {
    var nodes = document.querySelectorAll(".pan-wait[data-start]");
    if (!nodes.length) return;
    var now = Date.now();
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var start = Number(node.getAttribute("data-start")) || now;
      var time = node.querySelector(".pan-wait-time");
      if (time) time.textContent = fmtElapsed(now - start);
      if (reduce.matches) continue;
      var words = node.querySelectorAll(".pan-wait-word");
      if (words.length < 2) continue;
      // The word in view slides up and out while the next one slides up from
      // below (CSS transitions on transform and opacity); nothing is retyped.
      var step = Math.floor((now - start) / 1600) % WAIT_LABELS.length;
      var next = null, current = null;
      for (var w = 0; w < words.length; w++) {
        if (words[w].textContent === WAIT_LABELS[step]) next = words[w];
        if (words[w].classList.contains("is-on")) current = words[w];
      }
      if (next && next !== current) {
        next.style.transition = "none";            // restart from below, not from above
        next.classList.remove("is-out");
        void next.offsetWidth;
        next.style.transition = "";
        next.classList.add("is-on");
        if (current) { current.classList.remove("is-on"); current.classList.add("is-out"); }
      }
    }
  }, 100);

  /* ---- 7. Assistant character count ------------------------------------ */
  // Mirrors the chat input's length into .pan-chat-count ("12 / 500").
  document.addEventListener("input", function (e) {
    var t = e.target;
    if (!t || !t.closest || !t.closest('[data-testid="stChatInput"]')) return;
    var out = document.querySelector(".pan-chat-count");
    if (out) out.textContent = (t.value || "").length + " / 500 characters";
  }, true);

})();
