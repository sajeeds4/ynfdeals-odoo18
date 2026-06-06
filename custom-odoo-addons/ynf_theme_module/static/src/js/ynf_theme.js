/* YNF Deals theme — frontend animations (vanilla, no framework). */
(function () {
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }
  ready(function () {
    /* Scroll reveal */
    var els = document.querySelectorAll(".ynf-rev");
    if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
        });
      }, { rootMargin: "0px 0px -6% 0px", threshold: 0.06 });
      els.forEach(function (e) { io.observe(e); });
      setTimeout(function () { els.forEach(function (e) { e.classList.add("in"); }); }, 2500);
    } else {
      els.forEach(function (e) { e.classList.add("in"); });
    }

    /* Count-up stats (setInterval so it finishes even in background tabs) */
    document.querySelectorAll(".ynf-count").forEach(function (el) {
      var to = parseFloat(el.getAttribute("data-to")) || 0;
      var suffix = el.getAttribute("data-suffix") || "";
      var i = 0, steps = 30;
      var id = setInterval(function () {
        i++; var t = Math.min(1, i / steps);
        el.textContent = Math.round(to * (1 - Math.pow(1 - t, 3))).toLocaleString() + suffix;
        if (t >= 1) clearInterval(id);
      }, 40);
    });

    /* Drop-alert inline confirmation */
    document.querySelectorAll(".ynf-dropalert form").forEach(function (f) {
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        f.innerHTML = '<div class="ynf-dropalert-done">✓ You\u2019re on the list — see you live.</div>';
      });
    });

    /* Decorative butterfly — wanders the viewport, non-interactive */
    var bf = document.querySelector(".ynf-butterfly");
    if (bf && !(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) {
      var W = window.innerWidth, H = window.innerHeight;
      var x = W / 2, y = H / 2, vx = 0.5, vy = -0.2, ang = -90, steerT = 0, last = performance.now();
      window.addEventListener("resize", function () { W = window.innerWidth; H = window.innerHeight; });
      function tick(now) {
        var dt = Math.min(40, now - last); last = now; var f = dt / 16.67;
        steerT -= dt;
        if (steerT <= 0) {
          var h = Math.atan2(vy, vx) + (Math.random() - 0.5) * 1.9, p = 0.55 + Math.random() * 1.25;
          vx += Math.cos(h) * p; vy += Math.sin(h) * p; steerT = 95 + Math.random() * 260;
        }
        if (x < 52) vx += 0.55; else if (x > W - 52) vx -= 0.55;
        if (y < 80) vy += 0.55; else if (y > H - 80) vy -= 0.55;
        vx *= 0.93; vy *= 0.93;
        var sp = Math.hypot(vx, vy); if (sp > 1.75) { vx = vx / sp * 1.75; vy = vy / sp * 1.75; }
        x += vx * f; y += vy * f;
        var ph = (now % 260) / 260, bob = (ph < 0.4 ? -(ph / 0.4) : -(1 - (ph - 0.4) / 0.6)) * 6;
        var tang = Math.atan2(vy, vx) * 180 / Math.PI, da = ((tang - ang + 540) % 360) - 180; ang += da * 0.14;
        bf.style.transform = "translate(" + x + "px," + (y + bob) + "px) rotate(" + (ang + 90) + "deg)";
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }
  });
})();
