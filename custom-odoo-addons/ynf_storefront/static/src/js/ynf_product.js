/* =========================================================================
   YNF Deals — MFD v2 product detail page behaviors.
   -------------------------------------------------------------------------
   Plain vanilla JS — no framework, no Odoo OWL. Runs on every page but
   short-circuits when the `.ynf-mfd2-product` root isn't present.

   Provides:
     1. Gallery scroll-snap → active dot sync (IntersectionObserver),
        plus tap-a-dot-to-jump scrolling.
     2. Sticky add-to-cart bar reveal once the main CTA scrolls past.
     3. Quantity stepper (− / +) wired to BOTH the main `add_qty` input
        and the sticky bar's qty/price mirrors.
     4. Wishlist heart toggle persisted to localStorage.
     5. Sticky bar's "Add to bag" forwards a click to the real `#add_to_cart`
        so Odoo's website_sale handler (combination check + cart POST)
        runs once and only once.
   ========================================================================= */

(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== "loading") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    ready(function () {
        var root = document.querySelector(".ynf-mfd2-product");
        if (!root) {
            return;
        }

        initGallery(root);
        initWishlist(root);
        initQuantity(root);
        initStickyBar(root);
    });

    /* ------------------------------------------------------------------
       1. Gallery — scroll-snap track + dots
       ------------------------------------------------------------------ */
    function initGallery(root) {
        var track = root.querySelector(".ynf-mfd2-product-gallery-track");
        if (!track) return;
        var dots = root.querySelectorAll(".ynf-mfd2-product-gallery-dot");
        var slides = track.querySelectorAll(".ynf-mfd2-product-gallery-slide");
        if (slides.length <= 1 || dots.length === 0) return;

        function setActive(idx) {
            for (var i = 0; i < dots.length; i++) {
                if (i === idx) {
                    dots[i].classList.add("is-active");
                } else {
                    dots[i].classList.remove("is-active");
                }
            }
        }

        // Tap a dot → smooth scroll to that slide.
        for (var i = 0; i < dots.length; i++) {
            (function (idx, dot) {
                dot.addEventListener("click", function () {
                    var target = slides[idx];
                    if (!target) return;
                    track.scrollTo({
                        left: target.offsetLeft,
                        behavior: "smooth"
                    });
                    setActive(idx);
                });
            })(i, dots[i]);
        }

        // Scroll-snap → IntersectionObserver picks the centered slide.
        if ("IntersectionObserver" in window) {
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
                        var idx = parseInt(entry.target.getAttribute("data-index"), 10) || 0;
                        setActive(idx);
                    }
                });
            }, {
                root: track,
                threshold: [0.6, 0.9]
            });
            slides.forEach(function (s) { io.observe(s); });
        } else {
            // Fallback: throttled scroll handler.
            var raf = null;
            track.addEventListener("scroll", function () {
                if (raf) return;
                raf = window.requestAnimationFrame(function () {
                    raf = null;
                    var slideW = track.clientWidth || 1;
                    var idx = Math.round(track.scrollLeft / slideW);
                    setActive(Math.max(0, Math.min(slides.length - 1, idx)));
                });
            });
        }
    }

    /* ------------------------------------------------------------------
       2. Wishlist heart — localStorage-backed, visual only.
       ------------------------------------------------------------------ */
    function initWishlist(root) {
        var heart = root.querySelector(".ynf-mfd2-product-gallery-wish");
        if (!heart) return;
        var pid = heart.getAttribute("data-product-id") || "";
        var storageKey = "ynf.wishlist.v1";

        function readWish() {
            try {
                var raw = window.localStorage.getItem(storageKey);
                if (!raw) return [];
                var parsed = JSON.parse(raw);
                return Array.isArray(parsed) ? parsed : [];
            } catch (e) {
                return [];
            }
        }

        function writeWish(arr) {
            try {
                window.localStorage.setItem(storageKey, JSON.stringify(arr));
            } catch (e) {
                /* storage full / private mode — silently swallow */
            }
        }

        var wishList = readWish();
        if (pid && wishList.indexOf(pid) !== -1) {
            heart.classList.add("is-wished");
            heart.setAttribute("aria-pressed", "true");
        } else {
            heart.setAttribute("aria-pressed", "false");
        }

        heart.addEventListener("click", function (ev) {
            ev.preventDefault();
            if (!pid) return;
            var arr = readWish();
            var idx = arr.indexOf(pid);
            if (idx === -1) {
                arr.push(pid);
                heart.classList.add("is-wished");
                heart.setAttribute("aria-pressed", "true");
            } else {
                arr.splice(idx, 1);
                heart.classList.remove("is-wished");
                heart.setAttribute("aria-pressed", "false");
            }
            writeWish(arr);
        });
    }

    /* ------------------------------------------------------------------
       3. Quantity stepper — sync to main input + sticky mirrors.
       ------------------------------------------------------------------ */
    function initQuantity(root) {
        var input = root.querySelector(".ynf-mfd2-product-qty-input");
        var dec = root.querySelector(".js-qty-dec");
        var inc = root.querySelector(".js-qty-inc");
        if (!input) return;

        // Sticky mirrors live OUTSIDE the .ynf-mfd2-product root.
        var stickyQty = document.querySelector("[data-ynf-sticky-qty]");
        var stickyPrice = document.querySelector("[data-ynf-sticky-price] .ynf-mfd2-price-amount");
        var unitPrice = stickyPrice ? parseFloat(stickyPrice.textContent.replace(/[^0-9.]/g, "")) || 0 : 0;

        function clampInt(v) {
            var n = parseInt(v, 10);
            if (isNaN(n) || n < 1) n = 1;
            if (n > 999) n = 999;
            return n;
        }

        function sync() {
            var q = clampInt(input.value);
            if (String(q) !== input.value) {
                input.value = String(q);
            }
            if (stickyQty) {
                stickyQty.textContent = String(q);
            }
            if (stickyPrice && unitPrice > 0) {
                stickyPrice.textContent = (unitPrice * q).toFixed(2);
            }
        }

        if (dec) {
            dec.addEventListener("click", function () {
                input.value = String(clampInt(input.value) - 1);
                sync();
                fireInputEvent(input);
            });
        }
        if (inc) {
            inc.addEventListener("click", function () {
                input.value = String(clampInt(input.value) + 1);
                sync();
                fireInputEvent(input);
            });
        }
        input.addEventListener("input", sync);
        input.addEventListener("change", sync);

        // Initial paint to keep mirrors aligned with server-rendered value.
        sync();
    }

    function fireInputEvent(el) {
        try {
            el.dispatchEvent(new Event("change", { bubbles: true }));
        } catch (e) {
            // Old browser fallback
            var ev = document.createEvent("HTMLEvents");
            ev.initEvent("change", true, false);
            el.dispatchEvent(ev);
        }
    }

    /* ------------------------------------------------------------------
       4. Sticky add-to-cart bar — visibility via IntersectionObserver,
          taps forwarded to the real #add_to_cart.
       ------------------------------------------------------------------ */
    function initStickyBar(root) {
        var bar = document.querySelector(".ynf-mfd2-product-sticky[data-ynf-sticky-bar]");
        var mainAdd = root.querySelector("#add_to_cart");
        if (!bar || !mainAdd) return;

        var stickyAdd = bar.querySelector("[data-ynf-sticky-add]");
        if (stickyAdd) {
            stickyAdd.addEventListener("click", function (ev) {
                ev.preventDefault();
                // Fire a real click on the main button — Odoo's website_sale
                // handler is bound to that node and will run the combination
                // check + POST to /shop/cart/update for us.
                try {
                    mainAdd.click();
                } catch (e) {
                    var clickEv = document.createEvent("MouseEvents");
                    clickEv.initEvent("click", true, true);
                    mainAdd.dispatchEvent(clickEv);
                }
            });
        }

        // Only show the bar once the main CTA has scrolled off-screen.
        function showBar() {
            bar.classList.add("is-visible");
            bar.removeAttribute("aria-hidden");
        }
        function hideBar() {
            bar.classList.remove("is-visible");
            bar.setAttribute("aria-hidden", "true");
        }

        if ("IntersectionObserver" in window) {
            var io = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        hideBar();
                    } else {
                        // Only show when the user has scrolled past it
                        // (rect.top above viewport), not on the way down.
                        var rect = entry.boundingClientRect;
                        if (rect.bottom < 0) {
                            showBar();
                        } else {
                            hideBar();
                        }
                    }
                });
            }, { threshold: 0, rootMargin: "0px 0px -10% 0px" });
            io.observe(mainAdd);
        } else {
            // Fallback: scroll-based check.
            var lastShown = false;
            window.addEventListener("scroll", function () {
                var rect = mainAdd.getBoundingClientRect();
                var below = rect.bottom < 0;
                if (below && !lastShown) {
                    showBar();
                    lastShown = true;
                } else if (!below && lastShown) {
                    hideBar();
                    lastShown = false;
                }
            }, { passive: true });
        }
    }

})();
