/* Part 8 page lock (decision A7).
 *
 * While a job loader is on the page (Run Analysis, Build Personas, What-If
 * rescore), nothing else on the page can be used: not by mouse, not by Tab,
 * Enter or Space, and not the top-right menu. Scrolling stays allowed. CSS alone can stop the mouse
 * (the overlay catches clicks) but not the keyboard, so this script marks the
 * page `inert` while a loader exists and removes it when the loader goes.
 *
 * Runs in the main page (injected once by app/ui_effects.install_page_lock).
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

  function running() {
    var app = document.querySelector('[data-testid="stApp"]');
    return !!app && app.getAttribute("data-test-script-state") === "running";
  }
  function tokenMs(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    var m = /^([0-9.]+)(ms|s)$/.exec(v);
    if (!m) return fallback;
    return parseFloat(m[1]) * (m[2] === "s" ? 1000 : 1);
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
    // Copy the live positions NOW, in the same task the ending mounts: the
    // old running loader is still on the page for the first moments of the
    // rerun. Waiting until it is gone (as before) left nothing to copy, so
    // the ending started from a server-side guess and the trace, strip and
    // tiles visibly jumped.
    adopt(fin);
    var t0 = performance.now(), last = t0, smooth = 0;
    fin.setAttribute("data-p8-held-at", String(Math.round(t0)));
    function release() {
      // Positions were adopted when the ending mounted; copy again only if
      // the old loader is somehow still here (cap reached), else keep them.
      if (document.querySelector(LOADER)) adopt(fin);
      // Restart the overlay's own fade so its hold-and-fade counts from now.
      fin.style.animation = "none";
      void fin.offsetWidth;
      fin.style.animation = "";
      fin.classList.remove("is-held");
      fin.setAttribute("data-p8-released-after", String(Math.round(performance.now() - t0)));
      frameLock(fin);
      awaitRun();
    }
    // Owner request: the ending always takes its full 2 s on screen. CSS
    // animations run on the clock, so when the browser stalls (the rest of the
    // rerun drawing the page) they jump ahead and look rushed. Each frame, any
    // time beyond one normal frame is given back to the ending's animations,
    // so a stall freezes the ending instead of skipping part of it.
    function frameLock(el) {
      var prev = performance.now(), started = prev;
      var FRAME = 1000 / 60;
      function tick(now) {
        if (!el.isConnected || el.classList.contains("p8-ended") || now - started > 12000) return;
        var lost = (now - prev) - FRAME * 1.5;
        prev = now;
        if (lost > 0 && el.getAnimations) {
          el.getAnimations({ subtree: true }).forEach(function (a) {
            if (a.playState === "running" && a.currentTime !== null) {
              a.currentTime = Math.max(0, a.currentTime - lost);
            }
          });
        }
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }
    // Part 9: the ending plays now, but Streamlit may still be drawing the
    // rest of the page (every tab renders on each run). Just before the card
    // would fade, if the run is still going, the card and the page's reveal
    // animations wait on the finished frame until it ends (cap 4 s), so the
    // reveal plays on an idle page instead of stuttering through it.
    function awaitRun() {
      var root = document.documentElement;
      var lead = Math.max(0, tokenMs("--pan-dur-finish", 800) + tokenMs("--pan-dur-hold", 150)
        + tokenMs("--pan-dur-finish-linger", 200) - 60);
      setTimeout(function () {
        if (!running()) return;
        root.classList.add("p9-await-run");
        var t1 = performance.now();
        (function poll() {
          if (!running() || performance.now() - t1 > 4000) {
            requestAnimationFrame(function () { root.classList.remove("p9-await-run"); });
          } else {
            setTimeout(poll, 50);
          }
        })();
      }, lead);
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

  // Part 9: a job click dims the page at once (ui_interactions.js, scrim on
  // <html>). When the real loader mounts it takes that scrim over at full
  // strength and fades in only its card, then the click scrim goes: the page
  // never dips or jumps between the two.
  function handoff() {
    var root = document.documentElement;
    var loaders = document.querySelectorAll(LOADER + ":not([data-p9-handoff])");
    if (!loaders.length) return;
    if (root.hasAttribute("data-p9-job-click")) {
      loaders.forEach(function (l) { l.setAttribute("data-p9-handoff", ""); });
      root.removeAttribute("data-p9-job-click");
    }
  }

  function sync() {
    handoff();
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
