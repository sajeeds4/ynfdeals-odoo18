/** @odoo-module **/

/* YNF Deals theme — mobile interactions */
(function () {
    "use strict";

    function init() {
        // Lock body scroll when mobile nav opens
        const navToggler = document.querySelector("header#top .navbar-toggler");
        const navCollapse = document.querySelector("header#top .navbar-collapse");
        if (navToggler && navCollapse) {
            navCollapse.addEventListener("show.bs.collapse", () => {
                document.body.classList.add("ynf-mobile-nav-open");
            });
            navCollapse.addEventListener("hide.bs.collapse", () => {
                document.body.classList.remove("ynf-mobile-nav-open");
            });
        }

        // Inject mobile sticky add-to-cart bar on product pages
        const productForm = document.querySelector("form#add_to_cart_form, form[action*='/shop/cart/update']");
        const priceEl = document.querySelector(".product_price .oe_price .oe_currency_value, #product_detail .product_price");
        const addBtn = document.querySelector("#add_to_cart, button#add_to_cart");
        if (productForm && addBtn && window.matchMedia("(max-width: 767px)").matches) {
            if (!document.querySelector(".ynf-mobile-cta-bar")) {
                const bar = document.createElement("div");
                bar.className = "ynf-mobile-cta-bar";
                const priceText = priceEl ? priceEl.textContent.trim() : "";
                bar.innerHTML = `
                    <div class="ynf-mobile-price">${priceText}</div>
                    <button type="button" class="btn btn-primary ynf-mobile-add">Add to cart</button>
                `;
                document.body.appendChild(bar);
                bar.querySelector(".ynf-mobile-add").addEventListener("click", () => {
                    addBtn.click();
                });
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
