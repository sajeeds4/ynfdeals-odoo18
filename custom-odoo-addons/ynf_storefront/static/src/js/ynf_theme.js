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

/* ---- LIVE TONIGHT countdown timer ---- */
(function () {
    function tickTimers() {
        document.querySelectorAll('[data-live-timer]').forEach((el) => {
            // Target time: today at 20:00 local (or tomorrow if already past)
            const now = new Date();
            const target = new Date(now);
            target.setHours(20, 0, 0, 0);
            if (target <= now) target.setDate(target.getDate() + 1);
            const diff = Math.max(0, target - now);
            const h = String(Math.floor(diff / 3600000)).padStart(2, '0');
            const m = String(Math.floor((diff % 3600000) / 60000)).padStart(2, '0');
            const s = String(Math.floor((diff % 60000) / 1000)).padStart(2, '0');
            el.textContent = `${h}:${m}:${s}`;
        });
    }
    if (document.readyState !== 'loading') tickTimers();
    else document.addEventListener('DOMContentLoaded', tickTimers);
    setInterval(tickTimers, 1000);
})();

/* ============================================================
   Cookie consent banner
   ============================================================ */
(function () {
    function init() {
        const banner = document.getElementById('ynf-cookie-banner');
        if (!banner) return;
        let consent = null;
        try { consent = localStorage.getItem('ynf-cookies'); } catch (e) {}
        if (consent) return;
        setTimeout(() => banner.classList.add('is-visible'), 600);
        banner.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-cookie]');
            if (!btn) return;
            try { localStorage.setItem('ynf-cookies', btn.dataset.cookie); } catch (e) {}
            banner.classList.remove('is-visible');
        });
    }
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();

/* ============================================================
   Butterfly flight — wanders the screen with flap-bobbing
   ============================================================ */
(function () {
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    function init() {
        const bf = document.querySelector('.ynf-butterfly');
        if (!bf) return;
        let x = window.innerWidth / 2, y = window.innerHeight / 2;
        let vx = 0, vy = 0;
        let heading = 0;
        let lastImpulse = 0;
        let lastFlap = 0;
        let bob = 0;
        function step(ts) {
            if (!lastImpulse) lastImpulse = ts;
            if (!lastFlap)    lastFlap    = ts;
            // Erratic heading impulses every ~120-380ms
            if (ts - lastImpulse > 120 + Math.random() * 260) {
                heading += (Math.random() - 0.5) * 2.4;
                lastImpulse = ts;
            }
            // Flap-synced bob every 260ms (matches wing flap)
            if (ts - lastFlap > 260) {
                bob = -7;
                lastFlap = ts;
            } else {
                bob *= 0.85;
            }
            // Target speed
            const speed = 0.45 + Math.random() * 0.25;
            const tvx = Math.cos(heading) * speed;
            const tvy = Math.sin(heading) * speed * 0.6;
            // Damped steering
            vx += (tvx - vx) * 0.06;
            vy += (tvy - vy) * 0.06;
            x += vx;
            y += vy + bob * 0.05;
            // Soft edge steering — turn away when near borders
            const margin = 60;
            if (x < margin)                       heading += 0.05;
            if (x > window.innerWidth - margin)   heading += Math.PI - 0.05;
            if (y < margin)                       heading = Math.abs(heading) * 0.5;
            if (y > window.innerHeight - margin)  heading = -Math.abs(heading) * 0.5;
            const angle = Math.atan2(vy, vx) * 180 / Math.PI;
            bf.style.transform = `translate3d(${x.toFixed(1)}px, ${(y + bob).toFixed(1)}px, 0) rotate(${angle.toFixed(1)}deg)`;
            requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();

/* ============================================================
   Add-to-bag toast — intercept .ynf-pc-add-form submits
   ============================================================ */
(function () {
    const toastEl     = () => document.getElementById('ynf-toast');
    const toastNameEl = () => document.getElementById('ynf-toast-name');

    function showToast(name) {
        const el = toastEl();
        const nameEl = toastNameEl();
        if (!el || !nameEl) return;
        nameEl.textContent = name || 'Item added';
        el.classList.add('is-visible');
        clearTimeout(showToast._t);
        showToast._t = setTimeout(() => el.classList.remove('is-visible'), 2800);
    }

    function bumpCartBadge() {
        const candidates = document.querySelectorAll(
            '.my_cart_quantity, .o_wsale_my_cart, .ynf-mfd-tab[href="/shop/cart"]'
        );
        candidates.forEach((el) => {
            el.classList.remove('ynf-bump');
            // force reflow to re-trigger animation
            void el.offsetWidth;
            el.classList.add('ynf-bump');
        });
    }

    function init() {
        document.addEventListener('submit', (ev) => {
            const form = ev.target.closest('.ynf-pc-add-form');
            if (!form) return;
            ev.preventDefault();
            const card = form.closest('.ynf-pc');
            const name = (card && card.querySelector('.ynf-pc-name')?.textContent || '').trim();
            const data = new FormData(form);
            fetch(form.action, {
                method: 'POST',
                body: data,
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.text())
                .then(() => {
                    showToast(name);
                    bumpCartBadge();
                })
                .catch(() => {
                    // fall back to native submit so user still progresses
                    form.submit();
                });
        });
    }
    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();

/* ============================================================
   Cinematic hero video — manual fade in/out loop.
   - Fades opacity 0 → 1 over the first 0.5s of playback.
   - Fades opacity 1 → 0 over the last 0.5s before the end.
   - On `ended`: opacity 0, wait 100ms, reset currentTime, play() again.
   This is a seamless loop without the visible black frame the native
   `loop` attribute leaves on most browsers.
   ============================================================ */
(function () {
    function init() {
        const video = document.querySelector('.ynf-cinema-video');
        if (!video) return;
        const FADE = 0.5;  // seconds of fade in/out

        function tick() {
            if (video.paused || !isFinite(video.duration) || video.duration <= 0) {
                requestAnimationFrame(tick);
                return;
            }
            const t = video.currentTime;
            const d = video.duration;
            let opacity;
            if (t < FADE) {
                opacity = Math.max(0, Math.min(1, t / FADE));
            } else if (t > d - FADE) {
                opacity = Math.max(0, Math.min(1, (d - t) / FADE));
            } else {
                opacity = 1;
            }
            video.style.opacity = String(opacity);
            requestAnimationFrame(tick);
        }

        video.addEventListener('ended', function () {
            video.style.opacity = '0';
            setTimeout(function () {
                try {
                    video.currentTime = 0;
                    const p = video.play();
                    if (p && typeof p.catch === 'function') p.catch(function () { /* autoplay blocked — give up quietly */ });
                } catch (e) { /* noop */ }
            }, 100);
        });

        // Kick things off — modern browsers require muted+playsinline for autoplay
        const p = video.play();
        if (p && typeof p.catch === 'function') {
            p.catch(function () {
                // Autoplay blocked (rare with muted). Try once on first user interaction.
                const startOnTap = function () {
                    video.play().catch(function () {});
                    document.removeEventListener('click', startOnTap);
                    document.removeEventListener('touchstart', startOnTap);
                };
                document.addEventListener('click', startOnTap, { once: true });
                document.addEventListener('touchstart', startOnTap, { once: true });
            });
        }
        requestAnimationFrame(tick);
    }

    if (document.readyState !== 'loading') init();
    else document.addEventListener('DOMContentLoaded', init);
})();
