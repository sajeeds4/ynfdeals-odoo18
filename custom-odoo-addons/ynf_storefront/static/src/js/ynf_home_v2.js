/* YNF Deals — animated homepage behaviour (design-system handoff).
   Runs only on the storefront homepage (root .ynfx). Product grids are
   server-rendered by QWeb; this only drives animation/interaction:
   marquee, hero entrance + rotation + count-up + parallax, scroll progress,
   scroll-reveal, live countdown. Robust: hard fallbacks so nothing loads blank. */
(function () {
  "use strict";

  function init() {
    var root = document.querySelector(".ynfx");
    if (!root) return;

    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // ── Marquee ──
    var mq = document.getElementById("yxMq");
    if (mq && !mq.children.length) {
      var msgs = ["Free shipping over $75", "100% authentic guarantee", "Live auctions nightly · 8 PM ET", "New drops every week"];
      var run = "";
      for (var k = 0; k < 2; k++) { msgs.forEach(function (m) { run += '<span>' + m + '<span class="sep">✦</span></span>'; }); }
      mq.innerHTML = run;
    }

    // ── Hero entrance (transition-driven + hard fallback) ──
    var heroEl = root.querySelector(".hero");
    function startHero() { if (heroEl) heroEl.classList.add("in"); }
    requestAnimationFrame(function () { requestAnimationFrame(startHero); });
    setTimeout(startHero, 140);
    window.addEventListener("load", startHero);
    setTimeout(function () {
      root.querySelectorAll(".hero [data-anim], .hero__bottlewrap, .hero__float").forEach(function (el) {
        el.style.transition = "none"; el.style.opacity = "1"; el.style.transform = "none";
      });
    }, 1800);

    // ── Scroll reveal ──
    var io = ("IntersectionObserver" in window) ? new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }) : null;
    if (io) { root.querySelectorAll(".reveal:not(.in)").forEach(function (el) { io.observe(el); }); }
    else { root.querySelectorAll(".reveal").forEach(function (el) { el.classList.add("in"); }); }

    // ── Hero parallax ──
    if (!reduce) {
      var bottle = document.getElementById("yxHeroBottle");
      var halo = root.querySelector(".hero__halo");
      var ticking = false;
      window.addEventListener("scroll", function () {
        if (ticking) return; ticking = true;
        requestAnimationFrame(function () {
          var y = window.scrollY;
          if (y < 900) {
            if (bottle) bottle.style.transform = "translateY(" + (y * 0.06) + "px)";
            if (halo) halo.style.transform = "translateY(" + (y * 0.12) + "px) scale(" + (1 + y * 0.0003) + ")";
          }
          ticking = false;
        });
      }, { passive: true });
    }

    // ── Live countdown ──
    var cd = document.getElementById("yxCd");
    if (cd) {
      var t = 42 * 60 + 18;
      setInterval(function () {
        if (t > 0) t--;
        var mm = String(Math.floor(t / 60)).padStart(2, "0");
        var ss = String(t % 60).padStart(2, "0");
        cd.textContent = mm + ":" + ss;
      }, 1000);
    }

    // ── Hero rotation (crossfade through real featured products) ──
    var HERO = [];
    var nodes = root.querySelectorAll("#yxHeroData > *");
    HERO = Array.prototype.map.call(nodes, function (n) {
      return { img: n.dataset.img, name: n.dataset.name || "", brand: n.dataset.brand || "", price: n.dataset.price || "" };
    }).filter(function (h) { return h.img; });
    var heroBottle = document.getElementById("yxHeroBottle");
    var floatName = document.getElementById("yxFloatName");
    var floatPrice = document.getElementById("yxFloatPrice");
    var heroDots = document.getElementById("yxHeroDots");
    var hIdx = 0, hTimer = null;
    if (HERO.length > 1 && heroBottle) {
      HERO.forEach(function (h) { var im = new Image(); im.src = h.img; });
      if (heroDots) {
        HERO.forEach(function (h, i) {
          var b = document.createElement("button");
          b.setAttribute("aria-label", h.name || ("Slide " + (i + 1)));
          b.className = i === 0 ? "on" : "";
          b.addEventListener("click", function () { goHero(i, true); });
          heroDots.appendChild(b);
        });
      }
      var paintHero = function (i) {
        var h = HERO[i];
        heroBottle.classList.add("swap");
        setTimeout(function () { heroBottle.src = h.img; heroBottle.alt = h.name || ""; heroBottle.classList.remove("swap"); }, 450);
        if (floatName) floatName.innerHTML = (h.name || "") + "<b>" + (h.brand || "") + "</b>";
        if (floatPrice && h.price) floatPrice.textContent = h.price;
        if (heroDots) { var dd = heroDots.children; for (var z = 0; z < dd.length; z++) dd[z].className = (z === i) ? "on" : ""; }
      };
      var goHero = function (i, manual) { hIdx = (i + HERO.length) % HERO.length; paintHero(hIdx); if (manual && hTimer) { clearInterval(hTimer); startRotate(); } };
      var startRotate = function () { if (reduce) return; hTimer = setInterval(function () { goHero(hIdx + 1); }, 4200); };
      startRotate();
    }

    // ── Count-up hero stats (with hard final-value guarantee) ──
    var stats = root.querySelectorAll(".hero__meta b[data-count]");
    function countUp(el) {
      var target = parseFloat(el.getAttribute("data-count"));
      var dec = parseInt(el.getAttribute("data-dec") || "0", 10);
      var suf = el.getAttribute("data-suffix") || "";
      var dur = 1100, start = performance.now();
      function step(now) {
        var p = Math.min(1, (now - start) / dur);
        var v = target * (1 - Math.pow(1 - p, 3));
        el.textContent = (dec ? v.toFixed(dec) : Math.round(v)) + suf;
        if (p < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    }
    setTimeout(function () { stats.forEach(countUp); }, 700);
    setTimeout(function () {
      stats.forEach(function (el) {
        var t2 = parseFloat(el.getAttribute("data-count")), d = parseInt(el.getAttribute("data-dec") || "0", 10);
        el.textContent = (d ? t2.toFixed(d) : Math.round(t2)) + (el.getAttribute("data-suffix") || "");
      });
    }, 2100);

    // ── Scroll progress bar ──
    var sb = document.getElementById("yxScrollbar");
    function updateBar() {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      if (sb) sb.style.width = (max > 0 ? (h.scrollTop / max) * 100 : 0) + "%";
    }
    if (sb) { window.addEventListener("scroll", updateBar, { passive: true }); updateBar(); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
