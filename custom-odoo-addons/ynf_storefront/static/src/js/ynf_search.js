/* YNF Deals — live-search overlay v2.
 *
 * Vanilla JS enhancement attached to the existing #ynf-search-overlay
 * element rendered by views/templates.xml. Adds:
 *   - Debounced live suggestions (POST /ynf/search/suggestions via JSON-RPC).
 *   - Popular brand chips (POST /ynf/search/popular_brands).
 *   - Recent-search chips persisted in localStorage (key: ynf_recent_searches).
 *   - Keyboard nav: ArrowUp/ArrowDown highlight, Enter navigate, Esc close.
 *
 * Plays nicely with the existing inline onclick handlers that toggle the
 * `.is-open` class on #ynf-search-overlay (we use a MutationObserver to
 * react to open/close).
 */
(function () {
  "use strict";

  var OVERLAY_ID = "ynf-search-overlay";
  var INPUT_ID = "ynf-search-input";
  var SUGGEST_URL = "/ynf/search/suggestions";
  var BRANDS_URL = "/ynf/search/popular_brands";
  var RECENT_KEY = "ynf_recent_searches";
  var RECENT_MAX = 5;
  var DEBOUNCE_MS = 200;
  var MIN_CHARS = 2;
  var SUGGEST_LIMIT = 6;
  var BRANDS_LIMIT = 8;

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function jsonrpc(url, params) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: params || {},
        id: Math.floor(Math.random() * 1e9),
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (j) { return (j && j.result) || {}; });
  }

  function readRecent() {
    try {
      var raw = localStorage.getItem(RECENT_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr.filter(function (s) {
        return typeof s === "string" && s.trim();
      }) : [];
    } catch (e) {
      return [];
    }
  }

  function pushRecent(q) {
    q = (q || "").trim();
    if (q.length < MIN_CHARS) return;
    var arr = readRecent().filter(function (s) {
      return s.toLowerCase() !== q.toLowerCase();
    });
    arr.unshift(q);
    arr = arr.slice(0, RECENT_MAX);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify(arr)); } catch (e) {}
  }

  function formatPrice(n) {
    var v = Number(n) || 0;
    return "$" + v.toFixed(2);
  }

  ready(function () {
    var overlay = document.getElementById(OVERLAY_ID);
    var input = document.getElementById(INPUT_ID);
    if (!overlay || !input) return;

    var form = input.closest("form") || overlay.querySelector("form");
    if (!form) return;

    /* Build the augmented panel below the existing form. */
    var panel = document.createElement("div");
    panel.className = "ynf-mfd2-search-panel";
    panel.innerHTML =
      '<div class="ynf-mfd2-search-recent" data-role="recent" hidden=""></div>' +
      '<div class="ynf-mfd2-search-chips" data-role="brands" hidden=""></div>' +
      '<div class="ynf-mfd2-search-results" data-role="results" role="listbox" hidden=""></div>' +
      '<div class="ynf-mfd2-search-empty" data-role="empty" hidden="">No matches — try another note.</div>';
    /* Insert after the search form so the existing layout is untouched. */
    if (form.parentNode) {
      form.parentNode.insertBefore(panel, form.nextSibling);
    } else {
      overlay.appendChild(panel);
    }

    var recentEl = panel.querySelector('[data-role="recent"]');
    var brandsEl = panel.querySelector('[data-role="brands"]');
    var resultsEl = panel.querySelector('[data-role="results"]');
    var emptyEl = panel.querySelector('[data-role="empty"]');

    var debounceTimer = null;
    var lastQuery = "";
    var currentResults = [];
    var activeIndex = -1;
    var brandsLoaded = false;
    var inflightSeq = 0;

    function show(el) { if (el) el.hidden = false; }
    function hide(el) { if (el) el.hidden = true; }

    function clearActive() {
      activeIndex = -1;
      var rows = resultsEl.querySelectorAll(".ynf-mfd2-search-row");
      rows.forEach(function (r) { r.classList.remove("is-active"); });
    }

    function setActive(idx) {
      var rows = resultsEl.querySelectorAll(".ynf-mfd2-search-row");
      if (!rows.length) { activeIndex = -1; return; }
      if (idx < 0) idx = rows.length - 1;
      if (idx >= rows.length) idx = 0;
      rows.forEach(function (r) { r.classList.remove("is-active"); });
      rows[idx].classList.add("is-active");
      activeIndex = idx;
      try { rows[idx].scrollIntoView({ block: "nearest" }); } catch (e) {}
    }

    function renderResults(items) {
      currentResults = items || [];
      activeIndex = -1;
      if (!currentResults.length) {
        resultsEl.innerHTML = "";
        hide(resultsEl);
        return;
      }
      var html = currentResults.map(function (p, i) {
        var brandLine = p.brand ? '<span class="ynf-mfd2-search-row-brand">' + escapeHtml(p.brand) + "</span>" : "";
        var familyLine = p.family ? '<span class="ynf-mfd2-search-row-family">' + escapeHtml(p.family) + "</span>" : "";
        return (
          '<a class="ynf-mfd2-search-row" role="option" data-idx="' + i + '" href="' + escapeHtml(p.url) + '">' +
            '<img class="ynf-mfd2-search-row-thumb" loading="lazy" alt="" src="' + escapeHtml(p.image_url) + '"/>' +
            '<div class="ynf-mfd2-search-row-meta">' +
              brandLine +
              '<span class="ynf-mfd2-search-row-name">' + escapeHtml(p.name) + "</span>" +
              familyLine +
            "</div>" +
            '<span class="ynf-mfd2-search-row-price">' + escapeHtml(formatPrice(p.price)) + "</span>" +
          "</a>"
        );
      }).join("");
      resultsEl.innerHTML = html;
      show(resultsEl);
      /* Persist the search term once results come back so we don't store
       * partial keystrokes. */
      pushRecent(lastQuery);
    }

    function renderEmpty(visible) {
      if (visible) show(emptyEl); else hide(emptyEl);
    }

    function renderBrands(brands) {
      if (!brands || !brands.length) {
        brandsEl.innerHTML = "";
        hide(brandsEl);
        return;
      }
      var html =
        '<div class="ynf-mfd2-search-chips-label">Popular brands</div>' +
        '<div class="ynf-mfd2-search-chips-row">' +
        brands.map(function (b) {
          var label = b.brand;
          return (
            '<a class="ynf-mfd2-search-chip" href="/shop?search=' +
            encodeURIComponent(label) + '" data-brand="' + escapeHtml(label) + '">' +
            escapeHtml(label) +
            "</a>"
          );
        }).join("") +
        "</div>";
      brandsEl.innerHTML = html;
      show(brandsEl);
    }

    function renderRecent() {
      var arr = readRecent();
      if (!arr.length) {
        recentEl.innerHTML = "";
        hide(recentEl);
        return;
      }
      var html =
        '<div class="ynf-mfd2-search-recent-label">Recent</div>' +
        '<div class="ynf-mfd2-search-recent-row">' +
        arr.map(function (q) {
          return (
            '<button type="button" class="ynf-mfd2-search-chip is-recent" data-recent="' +
            escapeHtml(q) + '">' + escapeHtml(q) + "</button>"
          );
        }).join("") +
        '<button type="button" class="ynf-mfd2-search-recent-clear" data-clear="1" aria-label="Clear recent searches">Clear</button>' +
        "</div>";
      recentEl.innerHTML = html;
      show(recentEl);
    }

    function loadBrandsOnce() {
      if (brandsLoaded) return;
      brandsLoaded = true;
      jsonrpc(BRANDS_URL, { limit: BRANDS_LIMIT })
        .then(function (res) {
          if (res && res.ok) renderBrands(res.brands || []);
        })
        .catch(function () { /* silent */ });
    }

    function runQuery(q) {
      var seq = ++inflightSeq;
      jsonrpc(SUGGEST_URL, { q: q, limit: SUGGEST_LIMIT })
        .then(function (res) {
          if (seq !== inflightSeq) return; /* stale */
          if (!res || !res.ok) return;
          var items = res.results || [];
          renderResults(items);
          renderEmpty(items.length === 0 && q.length >= MIN_CHARS);
        })
        .catch(function () { /* silent */ });
    }

    function onInput() {
      var q = (input.value || "").trim();
      lastQuery = q;
      clearActive();
      if (debounceTimer) clearTimeout(debounceTimer);
      if (q.length < MIN_CHARS) {
        resultsEl.innerHTML = "";
        hide(resultsEl);
        hide(emptyEl);
        renderRecent();
        show(brandsEl.children.length ? brandsEl : brandsEl);
        if (!brandsEl.children.length) hide(brandsEl);
        return;
      }
      /* Hide the resting chips while the user is typing. */
      hide(recentEl);
      hide(brandsEl);
      debounceTimer = setTimeout(function () { runQuery(q); }, DEBOUNCE_MS);
    }

    function onKeyDown(e) {
      var key = e.key;
      if (key === "Escape") {
        e.preventDefault();
        overlay.classList.remove("is-open");
        return;
      }
      if (key === "ArrowDown") {
        if (currentResults.length) {
          e.preventDefault();
          setActive(activeIndex < 0 ? 0 : activeIndex + 1);
        }
        return;
      }
      if (key === "ArrowUp") {
        if (currentResults.length) {
          e.preventDefault();
          setActive(activeIndex < 0 ? currentResults.length - 1 : activeIndex - 1);
        }
        return;
      }
      if (key === "Enter") {
        if (activeIndex >= 0 && currentResults[activeIndex]) {
          e.preventDefault();
          pushRecent(lastQuery);
          window.location.href = currentResults[activeIndex].url;
        } else if (lastQuery.length >= MIN_CHARS) {
          /* Let the form submit naturally — record it first. */
          pushRecent(lastQuery);
        }
      }
    }

    /* Click handling for results + chips (event-delegated). */
    panel.addEventListener("click", function (e) {
      var clearBtn = e.target.closest("[data-clear]");
      if (clearBtn) {
        e.preventDefault();
        try { localStorage.removeItem(RECENT_KEY); } catch (err) {}
        renderRecent();
        return;
      }
      var recentBtn = e.target.closest("[data-recent]");
      if (recentBtn) {
        e.preventDefault();
        input.value = recentBtn.getAttribute("data-recent") || "";
        input.focus();
        onInput();
        return;
      }
      var row = e.target.closest(".ynf-mfd2-search-row");
      if (row) {
        pushRecent(lastQuery);
        /* Normal anchor navigation handles the rest. */
      }
    });

    input.addEventListener("input", onInput);
    input.addEventListener("keydown", onKeyDown);

    /* Make sure submitting the form records the term. */
    form.addEventListener("submit", function () {
      pushRecent((input.value || "").trim());
    });

    /* Detect overlay open via MutationObserver — the existing inline
     * onclick handlers toggle `.is-open`; we have no event to listen to. */
    function handleOpen() {
      try { input.focus(); } catch (e) {}
      loadBrandsOnce();
      renderRecent();
      if (!(input.value || "").trim()) {
        if (brandsEl.children.length) show(brandsEl);
      }
    }
    function handleClose() {
      /* Clear transient highlights but preserve typed text + last results
       * so reopening feels instant. */
      clearActive();
      hide(emptyEl);
    }

    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        if (m.type !== "attributes" || m.attributeName !== "class") return;
        if (overlay.classList.contains("is-open")) handleOpen();
        else handleClose();
      });
    });
    observer.observe(overlay, { attributes: true, attributeFilter: ["class"] });

    /* If the overlay is already open on load (unlikely), prime it. */
    if (overlay.classList.contains("is-open")) handleOpen();
  });
})();
