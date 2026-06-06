/** YNF Perfume — Recently viewed (Phase 14)
 *  On a product page, records the product in localStorage. On any page with a
 *  [data-ynf-recent] container, renders a rail of recently-viewed mini-cards.
 *  Pure client-side, no tracking beyond the visitor's own browser.
 */
(function () {
    "use strict";
    var KEY = "ynf-recent";
    var MAX = 10;

    function read() {
        try { return JSON.parse(localStorage.getItem(KEY)) || []; }
        catch (e) { return []; }
    }
    function write(list) {
        try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); }
        catch (e) {}
    }

    function record() {
        var el = document.getElementById("ynf-pdp-data");
        if (!el) return;
        var item = {
            id: el.dataset.id,
            name: el.dataset.name,
            brand: el.dataset.brand || "",
            price: el.dataset.price || "",
            img: el.dataset.img || "",
            url: el.dataset.url || "#",
        };
        if (!item.id) return;
        var list = read().filter(function (x) { return x.id !== item.id; });
        list.unshift(item);
        write(list);
    }

    function render() {
        var host = document.querySelector("[data-ynf-recent]");
        if (!host) return;
        var current = host.getAttribute("data-current-id");
        var list = read().filter(function (x) { return x.id !== current; });
        if (list.length < 2) { host.style.display = "none"; return; }

        var cards = list.slice(0, 8).map(function (x) {
            return (
                '<a class="y-card" href="' + x.url + '" style="width:158px;flex:0 0 158px">' +
                  '<div class="y-card__stage">' +
                    (x.img ? '<img class="y-card__img" src="' + x.img + '" alt="" loading="lazy"/>' : '') +
                  '</div>' +
                  '<div class="y-card__body">' +
                    '<div class="y-card__meta"><span class="y-card__brand">' + esc(x.brand) + '</span></div>' +
                    '<div class="y-card__name">' + esc(x.name) + '</div>' +
                    (x.price ? '<div class="y-card__foot"><span class="y-card__price y-price">' + esc(x.price) + '</span></div>' : '') +
                  '</div>' +
                '</a>'
            );
        }).join("");

        host.innerHTML =
            '<div class="ynf-recent__title">Recently viewed</div>' +
            '<div class="y-rail y-noscroll">' + cards + '</div>';
        host.style.display = "";
    }

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
        });
    }

    function init() { record(); render(); }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
