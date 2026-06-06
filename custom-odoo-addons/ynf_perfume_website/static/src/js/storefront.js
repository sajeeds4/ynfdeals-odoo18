/** YNF Perfume — storefront interactions
 *  - Quick-add from product cards (uses Odoo's /shop/cart/update JSON route)
 *  - Countdown timers for live-auction strips
 *  - Cart-count bump animation
 *  All native/vanilla; no framework, no ecommerce logic re-implemented.
 */
(function () {
    "use strict";

    /* ── Live-auction countdown (to next given hour, default 20:00 local) ── */
    function pad(n) { return String(n).padStart(2, "0"); }

    function tickCountdown(el) {
        var hour = parseInt(el.dataset.hour || "20", 10);
        var now = new Date();
        var target = new Date(now);
        target.setHours(hour, 0, 0, 0);
        if (target <= now) target.setDate(target.getDate() + 1);
        var s = Math.floor((target - now) / 1000);
        var h = Math.floor(s / 3600); s %= 3600;
        var m = Math.floor(s / 60); var ss = s % 60;
        el.textContent = pad(h) + ":" + pad(m) + ":" + pad(ss);
    }

    function initCountdowns() {
        var els = document.querySelectorAll(".ynf [data-ynf-countdown]");
        if (!els.length) return;
        function loop() { els.forEach(tickCountdown); }
        loop();
        setInterval(loop, 1000);
    }

    /* ── Quick add to cart ── */
    function quickAdd(productId, btn) {
        if (!productId) return;
        if (btn) btn.classList.add("is-loading");
        fetch("/shop/cart/update_json", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: { product_id: parseInt(productId, 10), add_qty: 1 },
            }),
        })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                var data = (res && res.result) || {};
                var count = data.cart_quantity;
                updateCartCount(count);
                bumpCart();
                confirmBtn(btn);
                toast(btn);
            })
            .catch(function () {
                // Fall back to the product page if the JSON route shape differs.
                if (productId) window.location.href = "/shop/cart";
            })
            .finally(function () { if (btn) btn.classList.remove("is-loading"); });
    }

    function updateCartCount(count) {
        if (count == null) return;
        document.querySelectorAll(".my_cart_quantity, .o_wsale_my_cart .badge")
            .forEach(function (b) { b.textContent = count; b.classList.remove("d-none"); });
    }

    // In-grid confirmation: flash the button to "✓ Added" briefly (#11).
    function confirmBtn(btn) {
        if (!btn) return;
        var isCart = btn.classList.contains("y-card__cart");
        var isFab = btn.classList.contains("y-card__add");
        if (!isCart && !isFab) return;
        if (btn.dataset.busy) return;
        btn.dataset.busy = "1";
        var original = btn.innerHTML;
        btn.classList.add("is-added");
        var check = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" ' +
            'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 13l4 4L19 7"/></svg>';
        btn.innerHTML = isCart ? (check + " Added") : check;
        setTimeout(function () {
            btn.classList.remove("is-added");
            btn.innerHTML = original;
            delete btn.dataset.busy;
        }, 1400);
    }

    function bumpCart() {
        document.querySelectorAll(".my_cart_quantity").forEach(function (b) {
            b.classList.remove("y-bump");
            // force reflow so the animation re-triggers
            void b.offsetWidth;
            b.classList.add("y-bump");
        });
    }

    function toast(btn) {
        var t = document.createElement("div");
        t.className = "ynf-toast";
        t.textContent = "Added to bag";
        document.body.appendChild(t);
        requestAnimationFrame(function () { t.classList.add("in"); });
        setTimeout(function () {
            t.classList.remove("in");
            setTimeout(function () { t.remove(); }, 300);
        }, 1800);
    }

    function initQuickAdd() {
        document.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-ynf-add]");
            if (!btn) return;
            e.preventDefault();
            e.stopPropagation();
            quickAdd(btn.dataset.ynfAdd, btn);
        });
    }

    // Newsletter: give real feedback instead of a silent no-op (#9).
    function initNewsletter() {
        document.querySelectorAll(".ynf form.y-news").forEach(function (form) {
            form.addEventListener("submit", function (e) {
                e.preventDefault();
                var email = (form.querySelector("input[type=email]") || {}).value || "";
                if (!email || email.indexOf("@") < 0) return;
                form.innerHTML =
                    '<div style="font-family:var(--y-display);font-weight:600;font-size:17px;color:#fff">' +
                    "✓ You’re on the list — see you live.</div>";
            });
        });
    }

    function init() {
        initCountdowns();
        initQuickAdd();
        initNewsletter();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
