/* Part 8 page lock (decision A7).
 *
 * While a job loader is on the page (Run Analysis, Build Personas, What-If
 * rescore), nothing else on the page can be used: not by mouse, not by Tab,
 * Enter or Space, and not the top-right menu. Scrolling stays allowed. CSS alone can stop the mouse
 * (the overlay catches clicks) but not the keyboard, so this script marks the
 * page `inert` while a loader exists and removes it when the loader goes.
 *
 * Runs in the main page (injected once by app/p8_effects.install_page_lock).
 * It reads the DOM only; it never talks to Streamlit and changes no widget.
 * The F3 finishing overlay (.is-finishing) does not lock: it only fades out.
 */
(function () {
  "use strict";
  var LOADER = ".pan-loading:not(.is-finishing)";
  // stMain itself is the page's scroll container, so it stays live: only its
  // children are made inert. A wheel or touchpad scroll over the locked page
  // then lands on stMain and scrolls it, while clicks and keys reach nothing.
  var TARGETS = [
    '[data-testid="stMain"] > *',
    'header[data-testid="stHeader"]',
    '[data-testid="stSkipToContent"]',
    'section[data-testid="stSidebar"]',
    '[data-testid="stBottom"]'
  ].join(", ");
  var MARK = "data-p8-inert";

  function lock() {
    document.querySelectorAll(TARGETS).forEach(function (el) {
      if (!el.hasAttribute("inert")) {
        el.setAttribute("inert", "");
        el.setAttribute(MARK, "");
      }
    });
    var active = document.activeElement;
    if (active && active !== document.body && active.closest && active.closest("[" + MARK + "]")) {
      active.blur();
    }
  }

  function unlock() {
    document.querySelectorAll("[" + MARK + "]").forEach(function (el) {
      el.removeAttribute("inert");
      el.removeAttribute(MARK);
    });
  }

  // Seamless loader finish (Part 8 polish). The finishing overlay is drawn
  // over the still-running loader; before its first paint, copy the live
  // positions (trace, document strip, magnifier, tiles) into its start frame.
  function matrix(el) {
    var m = el ? /matrix\(([^)]+)\)/.exec(getComputedStyle(el).transform) : null;
    if (!m) return { a: 1, e: 0, f: 0 };
    var v = m[1].split(",").map(parseFloat);
    return { a: v[0], e: v[4], f: v[5] };
  }
  function adopt(fin) {
    var run = document.querySelector(LOADER);
    if (!run) return;                                   // fallbacks from the server stay
    var line = run.querySelector(".pan-trace-line"), trace = fin.querySelector(".pan-trace");
    if (line && trace) {
      var off = parseFloat(getComputedStyle(line).strokeDashoffset) || 0;
      trace.style.setProperty("--p8-phase", (((-off / 100) % 1) + 1) % 1);
    }
    var docs = fin.querySelector(".pan-docs.is-story");
    var track = run.querySelector(".pan-docs-track");
    if (docs && track) {
      var x0 = matrix(track).e, x1 = x0 - 21.5;         // same glide as theme._DOC_SETTLE
      var target = Math.round((84 - x1) / 84);
      docs.style.setProperty("--x0", x0 + "px");
      docs.style.setProperty("--x1", x1 + "px");
      docs.style.setProperty("--lens-dx", (target * 84 + 28 + x1 - 112) + "px");
      docs.style.setProperty("--m0", matrix(run.querySelector(".pan-mag")).f + "px");
      docs.querySelectorAll(".pan-doc").forEach(function (d, i) {
        d.classList.toggle("is-target", i === target);
      });
    }
    // Suggest dots: copy each running dot's live position (orbits rotate the
    // dots, so read where they are on screen relative to the swarm's centre).
    var sgRun = run.querySelector(".pan-sg"), sgFin = fin.querySelector(".pan-sg.is-story");
    if (sgRun && sgFin) {
      var c = sgRun.getBoundingClientRect(), cx = c.left + c.width / 2, cy = c.top + c.height / 2;
      var live = sgRun.querySelectorAll(".pan-sg-dot"), fdots = sgFin.querySelectorAll(".pan-sg-fdot");
      for (var di = 0; di < fdots.length && di < live.length; di++) {
        var r = live[di].getBoundingClientRect();
        fdots[di].style.setProperty("--x0", (r.left + r.width / 2 - cx) + "px");
        fdots[di].style.setProperty("--y0", (r.top + r.height / 2 - cy) + "px");
      }
    }
    fin.querySelectorAll(".pan-pz.is-story .pan-pz-tile").forEach(function (t) {
      var key = [].slice.call(t.classList).filter(function (c) { return /^pan-pz-[a-h]$/.test(c); })[0];
      var live = key ? run.querySelector(".pan-pz-tile." + key) : null;
      if (!live) return;
      var m = matrix(live);
      // The story squashes from the tile's bottom edge; keep its centre where it is.
      t.style.setProperty("--x0", m.e + "px");
      t.style.setProperty("--y0", (m.f - 11 * (1 - m.a)) + "px");
      t.style.setProperty("--s0", String(m.a));
    });
  }

  // The ending is drawn at the start of the rerun that follows a job, but the
  // rest of that rerun can keep the browser too busy to paint for seconds, and
  // the ending would play unseen. So it is held on its first frame until the
  // browser is free again: the old running loader has been replaced (the rerun
  // reached it) and three animation frames in a row arrive on time. Then the
  // live positions are copied and it plays. A 4 s cap means it never waits
  // forever.
  function hold(fin) {
    fin.setAttribute("data-p8-adopted", "");
    fin.classList.add("is-held");
    var t0 = performance.now(), last = t0, smooth = 0;
    fin.setAttribute("data-p8-held-at", String(Math.round(t0)));
    function release() {
      adopt(fin);
      // Restart the overlay's own fade so its hold-and-fade counts from now.
      fin.style.animation = "none";
      void fin.offsetWidth;
      fin.style.animation = "";
      fin.classList.remove("is-held");
      fin.setAttribute("data-p8-released-after", String(Math.round(performance.now() - t0)));
    }
    function frame(now) {
      var oldGone = !document.querySelector(LOADER);
      smooth = (now - last < 50) ? smooth + 1 : 0;
      last = now;
      if ((oldGone && smooth >= 3) || now - t0 > 4000) { release(); return; }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function sync() {
    document.querySelectorAll(".pan-loading.is-finishing:not([data-p8-adopted])").forEach(hold);
    var on = document.querySelector(LOADER) !== null;
    if (on) {
      lock();
    } else if (document.querySelector("[" + MARK + "]") !== null) {
      unlock();
    }
    document.documentElement.toggleAttribute("data-p8-locked", on);
  }

  new MutationObserver(sync).observe(document.body, { childList: true, subtree: true });
  sync();

  // Once-only animations (Part 8 polish). Reveals and count-ups keyed to a
  // generation must not replay when a hidden tab panel is shown again (a
  // display change restarts CSS animations). When one finishes, its element
  // is marked; CSS then keeps it at its final frame (.p8-anim-done).
  // A loader ending that has faded out stops delaying reveals (CSS
  // --p8-gen-start), so tabs opened afterwards show their numbers at once.
  document.addEventListener("animationend", function (e) {
    var t = e.target;
    if (e.animationName === "p8-fade-out" && t && t.classList && t.classList.contains("is-finishing")) {
      t.classList.add("p8-ended");
    }
  }, true);

  var ONCE = { "p8-drop-card": 1, "p8-drop-in": 1, "p8-count": 1, "p8-swoop": 1, "p8-swoop-b": 1 };
  document.addEventListener("animationend", function (e) {
    var t = e.target;
    if (ONCE[e.animationName] && t && t.classList) t.classList.add("p8-anim-done");
  }, true);
})();
