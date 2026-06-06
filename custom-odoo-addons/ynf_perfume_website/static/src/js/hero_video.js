/** YNF Perfume — cinematic hero video fade loop (Phase 3)
 *  Custom requestAnimationFrame-driven cross-fade so the loop seam is invisible:
 *    • fade IN  over 0.5s at the start
 *    • fade OUT over 0.5s before the end
 *    • on `ended`: opacity 0 → wait 100ms → currentTime = 0 → play()
 *  Respects prefers-reduced-motion (then it just holds the poster frame).
 */
(function () {
    "use strict";

    var FADE = 0.5; // seconds

    function setup(video) {
        if (video.dataset.ynfHero === "1") return;
        video.dataset.ynfHero = "1";

        var reduce = window.matchMedia &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        video.muted = true;
        video.playsInline = true;
        video.setAttribute("playsinline", "");
        video.loop = false; // we drive the loop manually for the seamless fade

        if (reduce) {
            video.style.opacity = "1";
            return;
        }

        var raf = null;

        function frame() {
            var d = video.duration;
            var t = video.currentTime;
            var op = 1;
            if (!isFinite(d) || d <= 0) {
                op = 1;
            } else if (t < FADE) {
                op = t / FADE;                       // fade in
            } else if (t > d - FADE) {
                op = Math.max(0, (d - t) / FADE);    // fade out before end
            }
            video.style.opacity = op.toFixed(3);
            raf = requestAnimationFrame(frame);
        }

        function start() {
            video.style.opacity = "0";
            var p = video.play();
            if (p && p.catch) { p.catch(function () { /* autoplay blocked; poster shows */ }); }
            if (!raf) raf = requestAnimationFrame(frame);
        }

        video.addEventListener("ended", function () {
            video.style.opacity = "0";
            setTimeout(function () {
                video.currentTime = 0;
                var p = video.play();
                if (p && p.catch) { p.catch(function () {}); }
            }, 100);
        });

        // Pause the rAF loop when the hero scrolls out of view (battery/CPU).
        if ("IntersectionObserver" in window) {
            new IntersectionObserver(function (entries) {
                entries.forEach(function (en) {
                    if (en.isIntersecting) {
                        if (video.paused) video.play().catch(function () {});
                        if (!raf) raf = requestAnimationFrame(frame);
                    } else {
                        if (raf) { cancelAnimationFrame(raf); raf = null; }
                        video.pause();
                    }
                });
            }, { threshold: 0.05 }).observe(video);
        }

        if (video.readyState >= 2) start();
        else video.addEventListener("loadeddata", start, { once: true });
    }

    function init() {
        document.querySelectorAll("video.y-hero-video").forEach(setup);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
