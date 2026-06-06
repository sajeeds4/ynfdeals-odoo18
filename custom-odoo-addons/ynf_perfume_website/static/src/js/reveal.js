/** YNF Perfume — reveal-on-scroll
 *  Adds `.in` to `.y-rev` elements as they enter the viewport.
 *  Vanilla JS, no framework. Mirrors the design's useReveal hook + failsafe.
 */
(function () {
    "use strict";

    function initReveal() {
        var els = document.querySelectorAll(".ynf .y-rev:not(.in)");
        if (!els.length) return;

        if (!("IntersectionObserver" in window)) {
            els.forEach(function (e) { e.classList.add("in"); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) {
                    en.target.classList.add("in");
                    io.unobserve(en.target);
                }
            });
        }, { rootMargin: "0px 0px -6% 0px", threshold: 0.05 });

        els.forEach(function (e) { io.observe(e); });

        // Failsafe: if observer never fires (e.g. odd layout), reveal anyway.
        setTimeout(function () {
            els.forEach(function (e) { e.classList.add("in"); });
        }, 2400);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initReveal);
    } else {
        initReveal();
    }
    // Re-run after Odoo website editor saves / dynamic content swaps.
    window.addEventListener("load", initReveal);
})();
