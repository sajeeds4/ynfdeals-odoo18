"""
Predictive analytics engine.

Compares competitor stream data (SQLite: competitor_listings + events)
against our own business data (auction results, inventory)
to surface actionable insights:

  - Product priorities      : what we should sell first based on demand + stock
  - Product opportunities   : our inventory items competitors also sell at high demand
  - Trending products       : competitor listings ranked by demand score
  - Price benchmarks        : our avg sell price vs competitor starting price
  - Top competitor buyers   : high-value spenders on competitor streams
  - Category trends         : keyword demand weighted by bid activity + chat
  - Chat-only demand        : keywords from chat not present in any listing (hidden demand)
  - Summary KPIs            : headline numbers for the overview card
"""

import json
import math
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from statistics import median

from .config import POSTGRES_SIDECAR_SCHEMA
from .company_db import list_products, list_auction_results_for_sessions, list_company_sessions, list_sale_orders
from .postgres_cutover import _pg_connect, ensure_wave1_postgres_schema, postgres_available


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_STOP_WORDS = {
    "the", "and", "for", "lot", "item", "with", "new", "used", "set",
    "pack", "pcs", "pce", "piece", "pieces", "box", "case", "nos",
    "you", "your", "yours", "are", "was", "were", "have", "has", "had",
    "this", "that", "these", "those", "they", "them", "their", "there",
    "what", "when", "where", "which", "who", "whom", "why", "how",
    "from", "into", "onto", "about", "after", "before", "over", "under",
    "again", "more", "most", "very", "just", "like", "dont", "cant",
    "does", "did", "done", "been", "being", "get", "got", "make", "made",
    "will", "would", "could", "should", "yall", "guys", "pls", "please",
    "thanks", "thank", "hello", "hey", "yeah", "okay", "ok", "yes", "not",
    "want", "need", "good", "great", "nice", "wild", "joined",
}

_POSITIVE_WORDS = {
    "need", "want", "fire", "good", "great", "love", "nice", "buy", "take",
    "deal", "steal", "wow", "yes", "clean", "beautiful", "favorite", "please",
}
_NEGATIVE_WORDS = {
    "bad", "fake", "slow", "late", "expensive", "high", "crazy", "pass", "skip",
    "hate", "broken", "weak", "wack", "trash", "cap", "wtf", "fault",
}
_CATALOG_NOISE_TERMS = {
    "bookmark",
    "banger",
    "alert",
    "givy",
    "givvy",
    "giveaway",
    "filler",
    "mystery",
    "random",
    "pull",
    "buyers",
    "buyer",
    "start",
    "starter",
    "sample",
    "samples",
    "free",
    "bundle",
    "bundles",
    "pulls",
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def _fuzzy_score(a, b):
    """0-1 similarity between two product name strings — combined fuzzy + keyword overlap."""
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    kw_a = set(_keywords(a))
    kw_b = set(_keywords(b))
    if kw_a and kw_b:
        overlap = len(kw_a & kw_b)
        union = len(kw_a | kw_b)
        jaccard = overlap / union if union else 0.0
        return round(0.6 * ratio + 0.4 * jaccard, 4)
    return ratio


def _data_freshness(snapshot_ts):
    """Return age in minutes and staleness flag for a snapshot timestamp."""
    if not snapshot_ts:
        return None, True
    try:
        t = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        age_minutes = round((datetime.now(timezone.utc) - t).total_seconds() / 60, 1)
        return age_minutes, age_minutes > 60
    except Exception:
        return None, True


def _keywords(text):
    """Extract meaningful alpha keywords (≥3 chars, not stop words) from a product name."""
    if not text:
        return []
    text = re.sub(r"\$[\d,.]+", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    return [w for w in re.findall(r"[a-zA-Z]{3,}", text.lower()) if w not in _STOP_WORDS]


def _keyword_allowed_for_products(keyword, product_keyword_map):
    if not keyword:
        return False
    if keyword in _STOP_WORDS or keyword in _CATALOG_NOISE_TERMS:
        return False
    return keyword in product_keyword_map


def _parse_price(payload):
    pv = payload.get("price_value") or payload.get("winning_price") or payload.get("sale_price")
    if pv is not None:
        try:
            return float(pv)
        except Exception:
            pass
    raw = str(payload.get("price") or payload.get("footer_text") or "")
    m = re.findall(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)", raw)
    if m:
        try:
            return float(m[-1].replace(",", ""))
        except Exception:
            pass
    return 0.0


def _parse_winner_price(payload):
    return _parse_price(payload)


def _parse_dt(ts):
    """Parse an ISO timestamp string to a timezone-aware datetime, or None on failure."""
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t
    except Exception:
        return None


def _in_window(sold_at_str, started_at_str, ended_at_str):
    """Return True if sold_at falls within [started_at, ended_at]. Inclusive, None = no bound."""
    t = _parse_dt(sold_at_str)
    if t is None:
        return True  # can't determine, include
    s = _parse_dt(started_at_str)
    if s and t < s:
        return False
    e = _parse_dt(ended_at_str)
    if e and t > e:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Result cache — keyed by (stream_id, snapshot_ts).
# Invalidates automatically when the snapshot changes (new scrape).
# ─────────────────────────────────────────────────────────────────────────────

_cache: dict = {}
_cache_lock = threading.Lock()
_timed_cache: dict = {}
_timed_cache_lock = threading.Lock()


def _require_postgres_analytics(db_path=None):
    if db_path:
        raise RuntimeError("analytics_sqlite_runtime_retired")
    if not postgres_available():
        raise RuntimeError("analytics_postgres_unavailable")


def _fetchall_dict_pg(cur):
    cols = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _cache_get(stream_id, snapshot_ts):
    if not snapshot_ts:
        return None
    with _cache_lock:
        return _cache.get((stream_id, snapshot_ts))


def _cache_set(stream_id, snapshot_ts, result):
    if not snapshot_ts:
        return
    with _cache_lock:
        # Evict stale entries for this stream before inserting
        stale = [k for k in _cache if k[0] == stream_id and k[1] != snapshot_ts]
        for k in stale:
            del _cache[k]
        _cache[(stream_id, snapshot_ts)] = result


def _timed_cache_get(key, ttl_seconds=60):
    with _timed_cache_lock:
        rec = _timed_cache.get(key)
        if not rec:
            return None
        if (datetime.now(timezone.utc) - rec["ts"]).total_seconds() > ttl_seconds:
            _timed_cache.pop(key, None)
            return None
        return rec["value"]


def _timed_cache_set(key, value):
    with _timed_cache_lock:
        _timed_cache[key] = {"ts": datetime.now(timezone.utc), "value": value}


def _analytics_db_path(db_path=None):
    if db_path:
        raise RuntimeError("analytics_sqlite_runtime_retired")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Data loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_competitor_data(stream_id, db_path):
    _analytics_db_path(db_path)
    _require_postgres_analytics(db_path=db_path)
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT streamer_name, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams WHERE id = %s",
                (int(stream_id),),
            )
            stream_row = cur.fetchone()
            streamer_name = stream_row[0] if stream_row else None
            stream_started_at = stream_row[1] if stream_row else None
            stream_ended_at = stream_row[2] if stream_row else None

            cur.execute(
                f"SELECT MAX(scraped_at) FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s",
                (int(stream_id),),
            )
            row = cur.fetchone()
            latest_ts = row[0] if row else None

            listings = []
            if latest_ts:
                cur.execute(
                    f"""
                    SELECT product_name, qty, starting_price, bid_count, listing_type, image_url, button_label, badge_text, catalog_position
                    FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings
                    WHERE stream_id = %s AND scraped_at = %s
                    ORDER BY id ASC
                    """,
                    (int(stream_id), latest_ts),
                )
                listings = [
                    {
                        "product_name": r[0],
                        "qty": r[1],
                        "starting_price": r[2] or 0.0,
                        "bid_count": r[3] or 0,
                        "listing_type": r[4] or "unknown",
                        "image_url": r[5],
                        "button_label": r[6],
                        "badge_text": r[7],
                        "catalog_position": r[8],
                    }
                    for r in cur.fetchall()
                ]

            cur.execute(
                f"SELECT event_type, payload, created_at FROM {POSTGRES_SIDECAR_SCHEMA}.events WHERE stream_id = %s ORDER BY id ASC",
                (int(stream_id),),
            )
            raw_events = cur.fetchall()

    winners = []
    chat_words = defaultdict(int)

    for event_type, raw_payload, created_at in raw_events:
        try:
            p = json.loads(raw_payload or "{}")
        except Exception:
            p = {}

        if event_type == "auction_winner":
            username = (p.get("winner") or p.get("winner_username") or "").strip()
            price = _parse_price(p)
            product = (p.get("product_name") or p.get("title") or "").strip()
            if username:
                winners.append({
                    "username": username,
                    "price": price,
                    "product": product,
                    "time": created_at,
                })

        elif event_type == "chat_message":
            msg = p.get("message") or p.get("text") or ""
            for kw in _keywords(msg):
                chat_words[kw] += 1

    return listings, winners, chat_words, latest_ts, streamer_name, stream_started_at, stream_ended_at


def _load_our_data():
    """Pull our local inventory + auction history."""
    our_products = []
    our_results = []
    try:
        for row in list_products(active_only=False):
            our_products.append({
                "id": row.get("id"),
                "name": row.get("name"),
                "barcode": row.get("barcode"),
                "default_code": row.get("sku"),
                "standard_price": row.get("cost_price"),
                "list_price": row.get("retail_price"),
                "qty_available": row.get("on_hand_qty"),
            })
    except Exception:
        pass
    try:
        from .company_db import list_company_sessions
        for session in list_company_sessions("ynfdeals", limit=500):
            for row in list_auction_results(session["id"], limit=5000):
                our_results.append({
                    "product_name": row.get("product_name"),
                    "sale_price": row.get("sale_price"),
                    "profit": row.get("profit"),
                    "margin_pct": row.get("margin_pct"),
                    "winner_username": row.get("winner_username"),
                    "barcode": row.get("barcode"),
                    "sold_at": row.get("sold_at"),
                })
    except Exception:
        pass
    return our_products, our_results


def _build_listing_keyword_index(listings):
    """Inverted index: keyword -> [listing index]. Reduces matching from O(N×M) to O(N+M)."""
    index = defaultdict(list)
    for i, comp in enumerate(listings):
        for kw in _keywords(comp.get("product_name") or ""):
            index[kw].append(i)
    return index


# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def _score_demand(listings):
    """
    Attach a demand_score (0-100) to each listing.
    Formula: bid velocity (50%) + price signal (30%) + scarcity (20%)

    Scarcity: qty=0 (sold out) = 20pts; qty=1 = 19pts; qty≥20 = 0pts.
    qty=None (unknown) = 0pts (no scarcity signal rather than inflate).
    """
    max_bids = max((c["bid_count"] for c in listings), default=1) or 1
    max_price = max((c["starting_price"] for c in listings), default=1) or 1

    for item in listings:
        bid_score = (item["bid_count"] / max_bids) * 50
        price_score = (math.log(item["starting_price"] + 1) / math.log(max_price + 1)) * 30

        qty = item["qty"]
        if qty is None:
            scarcity_score = 0.0          # unknown — don't inflate score
        elif qty == 0:
            scarcity_score = 20.0         # sold out = maximum scarcity
        else:
            scarcity_score = max(0.0, 20.0 - min(20.0, float(qty)))

        item["demand_score"] = round(bid_score + price_score + scarcity_score, 1)

    return listings


def _buyer_tier(total_spent):
    if total_spent >= 500:
        return "whale"
    if total_spent >= 100:
        return "heavy"
    return "regular"


def _priority_band(score):
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_analytics_overview(stream_id, db_path=None):
    """
    Full analytics overview comparing competitor stream vs our business.

    Returns:
      summary                : headline KPIs (our revenue/profit scoped to stream time window)
      priority_recommendations : products we should push first
      trending_products      : top 20 competitor listings by demand score
      product_opportunities  : our inventory items that match high-demand comp products
      price_benchmarks       : our avg sell price vs competitor starting price (matched products)
      top_competitor_buyers  : top spenders on the competitor stream (with tier)
      category_trends        : keyword demand ranking from listings + chat signals (time-decayed)
      chat_only_demand       : keywords prominent in chat but absent from all listings (hidden demand)
      streamer_name          : name of the competitor streamer
    """
    _require_postgres_analytics(db_path=db_path)
    _analytics_db_path(db_path)

    # ── Cache check — requires snapshot_ts, so load it first ──────────────
    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT MAX(scraped_at) FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings WHERE stream_id = %s",
                (int(stream_id),),
            )
            snap_row = cur.fetchone()
            snapshot_ts_check = snap_row[0] if snap_row else None

    cached = _cache_get(stream_id, snapshot_ts_check)
    if cached is not None:
        return cached

    # ── Full data load ─────────────────────────────────────────────────────
    (listings, comp_winners, chat_words,
     snapshot_ts, streamer_name,
     stream_started_at, stream_ended_at) = _load_competitor_data(stream_id, db_path)

    our_products, our_results = _load_our_data()

    # ── 1. Demand scoring ──────────────────────────────────────────────────
    _score_demand(listings)
    trending_products = sorted(listings, key=lambda x: x["demand_score"], reverse=True)[:20]

    # ── 2. Product opportunity matching (keyword-indexed, O(N+M)) ──────────
    listing_kw_index = _build_listing_keyword_index(listings)
    opportunities = []

    for prod in our_products:
        our_name = (prod.get("name") or "").strip()
        if not our_name:
            continue

        our_kws = _keywords(our_name)
        # Get candidate listings that share at least one keyword
        candidate_indices = set()
        for kw in our_kws:
            candidate_indices.update(listing_kw_index.get(kw, []))

        if not candidate_indices:
            continue  # no keyword overlap with any listing — skip expensive fuzzy

        best_score, best_comp = 0.0, None
        for idx in candidate_indices:
            comp = listings[idx]
            s = _fuzzy_score(our_name, comp.get("product_name") or "")
            if s > best_score:
                best_score, best_comp = s, comp

        if best_score >= 0.45 and best_comp:
            opportunities.append({
                "our_product": our_name,
                "our_sku": prod.get("default_code") or "",
                "our_cost": prod.get("standard_price") or 0,
                "our_list_price": prod.get("list_price") or 0,
                "our_qty_available": prod.get("qty_available") or 0,
                "comp_product": best_comp["product_name"],
                "comp_price": best_comp["starting_price"],
                "comp_bids": best_comp["bid_count"],
                "comp_demand_score": best_comp["demand_score"],
                "match_confidence": round(best_score * 100, 1),
            })

    opportunities.sort(key=lambda x: x["comp_demand_score"], reverse=True)

    # ── 3. Price benchmarks ────────────────────────────────────────────────
    # Use all-time average — more statistically robust for pricing decisions.
    our_avg_by_name = defaultdict(list)
    for r in our_results:
        pname = (r.get("product_name") or "").strip()
        sp = r.get("sale_price")
        if pname and sp:
            try:
                our_avg_by_name[pname].append(float(sp))
            except Exception:
                pass

    price_benchmarks = []
    for opp in opportunities[:20]:
        our_prices = our_avg_by_name.get(opp["our_product"], [])
        our_avg = round(sum(our_prices) / len(our_prices), 2) if our_prices else None
        comp_price = opp["comp_price"]
        if our_avg and comp_price:
            delta_pct = round((comp_price - our_avg) / our_avg * 100, 1)
            if delta_pct > 10:
                signal = "underpricing"
            elif delta_pct < -10:
                signal = "overpricing"
            else:
                signal = "aligned"
            price_benchmarks.append({
                "product": opp["our_product"],
                "our_avg_price": our_avg,
                "comp_price": comp_price,
                "delta_pct": delta_pct,
                "signal": signal,
                "times_sold_by_us": len(our_prices),
            })

    # ── 3b. Product priorities — turn matches into an action list ─────────
    priority_recommendations = []
    for opp in opportunities:
        our_prices = our_avg_by_name.get(opp["our_product"], [])
        our_avg = round(sum(our_prices) / len(our_prices), 2) if our_prices else None
        stock = float(opp.get("our_qty_available") or 0)
        demand = float(opp.get("comp_demand_score") or 0)
        bids = float(opp.get("comp_bids") or 0)
        confidence = float(opp.get("match_confidence") or 0)
        comp_price = float(opp.get("comp_price") or 0)

        pricing_gap_pct = None
        price_signal = "new_opportunity"
        if our_avg and comp_price:
            pricing_gap_pct = round((comp_price - our_avg) / our_avg * 100, 1)
            if pricing_gap_pct >= 10:
                price_signal = "price_upside"
            elif pricing_gap_pct <= -10:
                price_signal = "price_pressure"
            else:
                price_signal = "price_aligned"

        stock_score = 0.0
        action = "source_next"
        if stock >= 10:
            stock_score = 25.0
            action = "push_now"
        elif stock >= 3:
            stock_score = 18.0
            action = "push_now"
        elif stock > 0:
            stock_score = 10.0
            action = "test_now"

        score = (
            min(45.0, demand * 0.55) +
            min(15.0, bids * 2.0) +
            min(15.0, confidence * 0.15) +
            min(10.0, len(our_prices) * 2.0) +
            stock_score
        )
        if pricing_gap_pct is not None and pricing_gap_pct >= 10:
            score += 10.0
        elif pricing_gap_pct is not None and pricing_gap_pct <= -10:
            score -= 8.0

        score = round(max(0.0, min(100.0, score)), 1)

        reasons = []
        if demand >= 70:
            reasons.append("strong competitor demand")
        elif demand >= 45:
            reasons.append("steady competitor demand")
        if bids >= 5:
            reasons.append(f"{int(bids)}+ bids on competitor listings")
        if stock > 0:
            reasons.append(f"{int(stock)} on hand")
        else:
            reasons.append("not in stock now")
        if pricing_gap_pct is not None and pricing_gap_pct >= 10:
            reasons.append("competitor sells higher than our average")
        elif pricing_gap_pct is not None and pricing_gap_pct <= -10:
            reasons.append("competitor prices lower than our average")
        elif not our_prices:
            reasons.append("low internal sales history")

        priority_recommendations.append({
            "our_product": opp["our_product"],
            "our_sku": opp["our_sku"],
            "our_qty_available": opp["our_qty_available"],
            "our_cost": opp["our_cost"],
            "our_list_price": opp["our_list_price"],
            "our_avg_sell_price": our_avg,
            "comp_product": opp["comp_product"],
            "comp_price": opp["comp_price"],
            "comp_bids": opp["comp_bids"],
            "comp_demand_score": opp["comp_demand_score"],
            "match_confidence": opp["match_confidence"],
            "times_sold_by_us": len(our_prices),
            "pricing_gap_pct": pricing_gap_pct,
            "price_signal": price_signal,
            "recommended_action": action,
            "priority_score": score,
            "priority_band": _priority_band(score),
            "why": reasons[:4],
        })

    priority_recommendations.sort(
        key=lambda x: (
            {"push_now": 0, "test_now": 1, "source_next": 2}.get(x["recommended_action"], 9),
            -x["priority_score"],
        )
    )

    # ── 4. Top competitor buyers ───────────────────────────────────────────
    buyer_map = defaultdict(lambda: {"username": "", "lots_won": 0, "total_spent": 0.0, "products": []})
    for w in comp_winners:
        u = w["username"]
        if not u:
            continue
        buyer_map[u]["username"] = u
        buyer_map[u]["lots_won"] += 1
        buyer_map[u]["total_spent"] = round(buyer_map[u]["total_spent"] + w["price"], 2)
        if w["product"]:
            buyer_map[u]["products"].append(w["product"])

    top_buyers = sorted(buyer_map.values(), key=lambda x: x["total_spent"], reverse=True)[:25]
    for b in top_buyers:
        # Deduplicate products (preserve order, keep last 5) — fixed antipattern
        seen, deduped = set(), []
        for p in b["products"][::-1]:      # reverse once: newest-first
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        b["products"] = deduped[:5]        # newest 5 unique products
        b["tier"] = _buyer_tier(b["total_spent"])

    # ── 5. Category / keyword trends (with time-decay on winner boost) ─────
    keyword_demand = defaultdict(float)
    now_ts = datetime.now(timezone.utc)

    # Weight from shop listings (demand score × keyword presence)
    for item in listings:
        score = item.get("demand_score", 0)
        for kw in _keywords(item.get("product_name") or ""):
            keyword_demand[kw] += score

    # Boost with competitor auction winner product names — time-decayed
    for w in comp_winners:
        recency = 1.0
        w_dt = _parse_dt(w.get("time"))
        if w_dt:
            age_days = (now_ts - w_dt).total_seconds() / 86400
            recency = max(0.2, 1.0 / (1.0 + age_days * 0.1))
        for kw in _keywords(w.get("product") or ""):
            keyword_demand[kw] += w["price"] * 0.1 * recency

    # Chat signal boost (lower weight — indirect demand indicator)
    # Only boosts keywords already present in listings (not chat-only ones)
    for kw, count in chat_words.items():
        if kw in keyword_demand:
            keyword_demand[kw] += count * 0.5

    category_trends = sorted(
        [{"keyword": k, "score": round(v, 1)} for k, v in keyword_demand.items()],
        key=lambda x: x["score"],
        reverse=True,
    )[:25]

    # ── 6. Chat-only demand — hidden demand signal ─────────────────────────
    # Keywords appearing in chat but NOT in any listing: customers asking for
    # things the competitor doesn't carry. Potential untapped market.
    listing_keywords = set(keyword_demand.keys())
    chat_only_demand = sorted(
        [
            {"keyword": kw, "chat_count": count, "score": round(count * 0.5, 1)}
            for kw, count in chat_words.items()
            if kw not in listing_keywords and count >= 2  # min threshold avoids noise
        ],
        key=lambda x: x["score"],
        reverse=True,
    )[:20]

    # ── 7. Summary KPIs ───────────────────────────────────────────────────
    comp_total_revenue = round(sum(w["price"] for w in comp_winners), 2)

    # Scope our revenue/profit to the same time window as the competitor stream
    our_in_window = [
        r for r in our_results
        if _in_window(r.get("sold_at"), stream_started_at, stream_ended_at)
    ]
    # If no results fall within the window (stream was in the past), show all-time
    our_windowed = our_in_window if our_in_window else our_results
    our_total_revenue = round(sum(float(r.get("sale_price") or 0) for r in our_windowed), 2)
    our_total_profit = round(sum(float(r.get("profit") or 0) for r in our_windowed), 2)
    our_revenue_is_windowed = bool(our_in_window and stream_started_at)

    snapshot_age_minutes, data_is_stale = _data_freshness(snapshot_ts)
    comp_prices = [float(w["price"] or 0) for w in comp_winners if float(w["price"] or 0) > 0]
    comp_avg_sale_price = round(sum(comp_prices) / len(comp_prices), 2) if comp_prices else 0.0
    comp_price_range = _price_range(comp_prices)
    posture = _competitor_posture(
        comp_avg_sale_price,
        len(buyer_map),
        sum(chat_words.values()),
        len(listings),
    )
    top_listing_share = round(
        sum(float(item.get("demand_score") or 0) for item in trending_products[:5]) /
        max(sum(float(item.get("demand_score") or 0) for item in trending_products), 1.0) * 100,
        1,
    ) if trending_products else 0.0
    white_space_pressure = round(sum(float(row.get("score") or 0) for row in chat_only_demand[:5]), 1)
    counter_moves = []
    if posture["model"] == "premium":
        counter_moves.append("Counter with trust-heavy hero products and avoid racing them to the bottom on price.")
    elif posture["model"] == "volume":
        counter_moves.append("Counter with cleaner sequencing and stronger value bundles instead of matching raw lot tempo.")
    else:
        counter_moves.append("Counter with sharper product curation and timing, because this seller is mixing pace with moderate pricing.")
    if white_space_pressure >= 6:
        counter_moves.append("Chat is asking for products not covered by their visible catalog. That is a good opening for your own inventory.")
    if price_benchmarks:
        upside_count = len([row for row in price_benchmarks if row["signal"] == "underpricing"])
        if upside_count >= max(2, len(price_benchmarks) // 3):
            counter_moves.append("They appear to be leaving price on the table in parts of the catalog. You can likely price selected matches higher.")

    result = {
        "stream_id": stream_id,
        "streamer_name": streamer_name,
        "snapshot_ts": snapshot_ts,
        "snapshot_age_minutes": snapshot_age_minutes,
        "data_is_stale": data_is_stale,
        "stream_started_at": stream_started_at,
        "stream_ended_at": stream_ended_at,
        "our_revenue_is_windowed": our_revenue_is_windowed,
        "summary": {
            "comp_listings_count": len(listings),
            "comp_winners_count": len(comp_winners),
            "comp_total_revenue": comp_total_revenue,
            "comp_unique_buyers": len(buyer_map),
            "comp_avg_sale_price": comp_avg_sale_price,
            "our_total_revenue": our_total_revenue,
            "our_total_profit": our_total_profit,
            "our_products_in_inventory": len(our_products),
            "opportunity_matches": len(opportunities),
            "priority_products": len([r for r in priority_recommendations if r["recommended_action"] in ("push_now", "test_now")]),
        },
        "priority_recommendations": priority_recommendations[:12],
        "trending_products": trending_products,
        "product_opportunities": opportunities[:30],
        "price_benchmarks": price_benchmarks,
        "top_competitor_buyers": top_buyers,
        "category_trends": category_trends,
        "chat_only_demand": chat_only_demand,
        "advanced_intelligence": {
            "selling_posture": posture,
            "price_range": comp_price_range,
            "catalog_concentration_pct": top_listing_share,
            "white_space_pressure": white_space_pressure,
            "counter_moves": counter_moves[:4],
            "buyer_quality": {
                "whale_buyers": len([b for b in top_buyers if b.get("tier") == "whale"]),
                "heavy_buyers": len([b for b in top_buyers if b.get("tier") == "heavy"]),
                "top_buyer_share_pct": round(
                    sum(float(b.get("total_spent") or 0) for b in top_buyers[:5]) / max(comp_total_revenue, 1.0) * 100,
                    1,
                ) if comp_total_revenue else 0.0,
            },
        },
    }

    _cache_set(stream_id, snapshot_ts, result)
    return result


def _parse_payload(raw_payload):
    try:
        return json.loads(raw_payload or "{}")
    except Exception:
        return {}


def _parse_ts_local(ts):
    dt = _parse_dt(ts)
    if not dt:
        return None
    try:
        return dt.astimezone()
    except Exception:
        return dt


def _safe_pct(num, den):
    return round((num / den) * 100, 1) if den else 0.0


def _safe_pct_capped(num, den):
    return min(100.0, _safe_pct(num, den))


def _price_range(values):
    vals = sorted(float(v) for v in values if v is not None)
    if not vals:
        return {"low": 0.0, "mid": 0.0, "high": 0.0}
    low_idx = max(0, math.floor((len(vals) - 1) * 0.25))
    high_idx = max(0, math.floor((len(vals) - 1) * 0.75))
    return {
        "low": round(vals[low_idx], 2),
        "mid": round(median(vals), 2),
        "high": round(vals[high_idx], 2),
    }


def _competitor_posture(avg_sale_price, avg_buyers, avg_chat, listings_count):
    if avg_sale_price >= 65:
        model = "premium"
        note = "This seller extracts high dollars per win and likely leans on trust and higher-ticket positioning."
    elif avg_sale_price <= 15 and listings_count >= 15:
        model = "volume"
        note = "This room behaves like a low-start / tempo seller where pace matters more than ticket size."
    else:
        model = "hybrid"
        note = "This competitor mixes pace with mid-ticket pricing and is not purely premium or liquidation."

    if avg_buyers >= 90 or avg_chat >= 1800:
        audience = "broad"
    elif avg_buyers >= 35 or avg_chat >= 600:
        audience = "healthy"
    else:
        audience = "niche"

    confidence = round(_clamp(
        (min(avg_sale_price, 120) / 120) * 30 +
        min(avg_buyers, 120) * 0.25 +
        min(avg_chat, 2500) * 0.01 +
        min(listings_count, 30) * 1.2,
        35,
        96,
    ), 1)

    return {
        "model": model,
        "audience_shape": audience,
        "confidence": confidence,
        "note": note,
    }


def get_spectator_market_pulse(our_stream_urls=None, our_streamer_names=None, allowed_stream_ids=None, db_path=None):
    _require_postgres_analytics(db_path=db_path)
    db = _analytics_db_path(db_path)
    our_urls = {u for u in (our_stream_urls or []) if u}
    our_base_urls = {u.split("?")[0] for u in our_urls}
    our_names = {n.lower() for n in (our_streamer_names or []) if n} | {"ynfdeals"}
    allowed_ids = {int(sid) for sid in (allowed_stream_ids or []) if sid is not None}
    cache_key = (
        "market_pulse",
        tuple(sorted(our_base_urls)),
        tuple(sorted(our_names)),
        tuple(sorted(allowed_ids)),
        db,
    )
    cached = _timed_cache_get(cache_key, ttl_seconds=60)
    if cached is not None:
        return cached

    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, stream_url, streamer_name, title, started_at, ended_at FROM {POSTGRES_SIDECAR_SCHEMA}.streams ORDER BY id DESC"
            )
            stream_rows = _fetchall_dict_pg(cur)
            cur.execute(
                f"""
                SELECT cl.stream_id, cl.product_name, cl.qty, cl.starting_price, cl.bid_count,
                       cl.listing_type, cl.image_url, cl.button_label, cl.badge_text, cl.catalog_position
                FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings cl
                JOIN (
                    SELECT stream_id, MAX(scraped_at) AS scraped_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.competitor_listings
                    GROUP BY stream_id
                ) latest
                  ON latest.stream_id = cl.stream_id
                 AND latest.scraped_at = cl.scraped_at
                ORDER BY cl.stream_id, cl.catalog_position, cl.id
                """
            )
            listing_rows = _fetchall_dict_pg(cur)
            cur.execute(
                f"""
                SELECT e.stream_id, e.event_type, e.payload, e.created_at,
                       s.stream_url, s.streamer_name, s.title, s.started_at, s.ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.events e
                JOIN {POSTGRES_SIDECAR_SCHEMA}.streams s ON s.id = e.stream_id
                ORDER BY e.id ASC
                """
            )
            event_rows = _fetchall_dict_pg(cur)

    valid_stream_ids = set()
    stream_meta = {}
    for row in stream_rows:
        url = row["stream_url"] or ""
        base_url = url.split("?")[0] if url else ""
        name = (row["streamer_name"] or "").strip()
        if url in our_urls or base_url in our_base_urls:
            continue
        if name and name.lower() in our_names:
            continue
        if allowed_ids and row["id"] not in allowed_ids:
            continue
        valid_stream_ids.add(row["id"])
        stream_meta[row["id"]] = {
            "stream_id": row["id"],
            "stream_url": url,
            "streamer_name": name or row["title"] or (url.split("/")[-1] if url else f"stream-{row['id']}"),
            "title": row["title"] or "",
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
        }

    stream_stats = {}
    streamer_stats = defaultdict(lambda: {
        "streamer_name": "",
        "sessions": 0,
        "revenue": 0.0,
        "lots_sold": 0,
        "messages": 0,
        "buyers": set(),
        "chatters": set(),
        "viewer_peak": 0,
        "active_minutes": 0.0,
    })
    buyer_streamers = defaultdict(set)
    buyer_sessions = defaultdict(set)
    buyer_spend = defaultdict(float)
    buyer_messages = defaultdict(int)
    keyword_stats = defaultdict(lambda: {"keyword": "", "mentions": 0, "conversions": 0, "buyers": set()})
    product_keyword_map = defaultdict(lambda: {"count": 0, "products": set()})
    product_market = defaultdict(lambda: {
        "product_name": "",
        "streams": set(),
        "streamers": set(),
        "prices": [],
        "bids": 0,
        "low_stock_hits": 0,
        "top_slot_hits": 0,
        "listing_types": defaultdict(int),
        "button_labels": defaultdict(int),
        "image_url": None,
    })
    catalog_type_mix = defaultdict(int)
    button_label_mix = defaultdict(int)
    hour_map = {h: {"hour": h, "revenue": 0.0, "wins": 0, "messages": 0, "active_streams": set()} for h in range(24)}
    first_chat_by_stream_user = {}
    now_local = datetime.now().astimezone()
    recent_cutoff = now_local.timestamp() - 600
    baseline_cutoff = now_local.timestamp() - 2400

    def get_stream_stat(stream_id):
        meta = stream_meta[stream_id]
        if stream_id not in stream_stats:
            stream_stats[stream_id] = {
                **meta,
                "revenue": 0.0,
                "lots_sold": 0,
                "messages": 0,
                "buyers": set(),
                "chatters": set(),
                "viewer_peak": 0,
                "first_event_at": None,
                "last_event_at": None,
                "recent_messages": 0,
                "recent_wins": 0,
                "recent_revenue": 0.0,
                "recent_viewer_peak": 0,
                "baseline_messages": 0,
                "baseline_wins": 0,
                "baseline_revenue": 0.0,
                "sentiment_positive": 0,
                "sentiment_negative": 0,
                "sentiment_score": 0.0,
            }
        return stream_stats[stream_id]

    for row in event_rows:
        stream_id = row["stream_id"]
        if stream_id not in valid_stream_ids:
            continue
        event_type = row["event_type"]
        payload = _parse_payload(row["payload"])
        event_dt = _parse_ts_local(row["created_at"])
        if not event_dt:
            continue

        stat = get_stream_stat(stream_id)
        streamer_name = stat["streamer_name"]
        sstat = streamer_stats[streamer_name]
        sstat["streamer_name"] = streamer_name
        if not stat["first_event_at"] or row["created_at"] < stat["first_event_at"]:
            stat["first_event_at"] = row["created_at"]
        if not stat["last_event_at"] or row["created_at"] > stat["last_event_at"]:
            stat["last_event_at"] = row["created_at"]

        hour_row = hour_map[event_dt.hour]
        hour_row["active_streams"].add(stream_id)
        is_recent = event_dt.timestamp() >= recent_cutoff
        is_baseline = baseline_cutoff <= event_dt.timestamp() < recent_cutoff

        if event_type == "chat_message":
            username = (payload.get("username") or payload.get("user") or "").strip()
            message = payload.get("message") or payload.get("text") or ""
            stat["messages"] += 1
            sstat["messages"] += 1
            hour_row["messages"] += 1
            words = _keywords(message)
            positives = sum(1 for w in words if w in _POSITIVE_WORDS)
            negatives = sum(1 for w in words if w in _NEGATIVE_WORDS)
            stat["sentiment_positive"] += positives
            stat["sentiment_negative"] += negatives
            stat["sentiment_score"] += positives - negatives
            if is_recent:
                stat["recent_messages"] += 1
            elif is_baseline:
                stat["baseline_messages"] += 1
            if username:
                stat["chatters"].add(username.lower())
                sstat["chatters"].add(username.lower())
                first_chat_by_stream_user.setdefault((stream_id, username.lower()), []).append(message)
                buyer_messages[username.lower()] += 1
            for kw in words:
                rec = keyword_stats[kw]
                rec["keyword"] = kw
                rec["mentions"] += 1

        elif event_type == "auction_winner":
            username = (payload.get("winner") or payload.get("winner_username") or payload.get("username") or "").strip()
            price = _parse_price(payload)
            stat["revenue"] = round(stat["revenue"] + price, 2)
            stat["lots_sold"] += 1
            sstat["revenue"] = round(sstat["revenue"] + price, 2)
            sstat["lots_sold"] += 1
            hour_row["revenue"] += price
            hour_row["wins"] += 1
            if is_recent:
                stat["recent_wins"] += 1
                stat["recent_revenue"] = round(stat["recent_revenue"] + price, 2)
            elif is_baseline:
                stat["baseline_wins"] += 1
                stat["baseline_revenue"] = round(stat["baseline_revenue"] + price, 2)
            if username:
                lower = username.lower()
                stat["buyers"].add(lower)
                sstat["buyers"].add(lower)
                buyer_streamers[lower].add(streamer_name)
                buyer_sessions[lower].add(stream_id)
                buyer_spend[lower] = round(buyer_spend[lower] + price, 2)
                for msg in first_chat_by_stream_user.get((stream_id, lower), [])[-5:]:
                    for kw in _keywords(msg):
                        rec = keyword_stats[kw]
                        rec["keyword"] = kw
                        rec["conversions"] += 1
                        rec["buyers"].add(lower)

        elif event_type == "live_viewers":
            count = payload.get("viewer_count", payload.get("count"))
            try:
                count = int(count)
            except Exception:
                count = None
            if count is not None:
                stat["viewer_peak"] = max(stat["viewer_peak"], count)
                sstat["viewer_peak"] = max(sstat["viewer_peak"], count)
                if is_recent:
                    stat["recent_viewer_peak"] = max(stat["recent_viewer_peak"], count)

    for row in listing_rows:
        stream_id = row["stream_id"]
        if stream_id not in valid_stream_ids:
            continue
        product_name = (row["product_name"] or "").strip()
        if not product_name:
            continue
        key = product_name.lower()
        rec = product_market[key]
        rec["product_name"] = product_name
        rec["streams"].add(stream_id)
        rec["streamers"].add(stream_meta[stream_id]["streamer_name"])
        if row["starting_price"] is not None:
            rec["prices"].append(float(row["starting_price"]))
        rec["bids"] += int(row["bid_count"] or 0)
        if row["qty"] is not None and int(row["qty"]) <= 3:
            rec["low_stock_hits"] += 1
        if row["catalog_position"] is not None and int(row["catalog_position"]) <= 12:
            rec["top_slot_hits"] += 1
        listing_type = (row["listing_type"] or "unknown").strip() or "unknown"
        button_label = (row["button_label"] or "").strip() or listing_type
        rec["listing_types"][listing_type] += 1
        rec["button_labels"][button_label] += 1
        catalog_type_mix[listing_type] += 1
        button_label_mix[button_label] += 1
        if not rec["image_url"] and row["image_url"]:
            rec["image_url"] = row["image_url"]
        for kw in _keywords(product_name):
            product_keyword_map[kw]["count"] += 1
            product_keyword_map[kw]["products"].add(product_name)

    stream_rows_out = []
    total_revenue = 0.0
    total_messages = 0
    total_lots = 0
    all_buyers = set()
    viewer_peaks = []
    active_minutes_samples = []

    for stream_id, stat in stream_stats.items():
        active_minutes = 0.0
        if stat["first_event_at"] and stat["last_event_at"]:
            start_dt = _parse_dt(stat["first_event_at"])
            end_dt = _parse_dt(stat["last_event_at"])
            if start_dt and end_dt:
                active_minutes = round(max(0.0, (end_dt - start_dt).total_seconds()) / 60.0, 1)
        total_revenue += stat["revenue"]
        total_messages += stat["messages"]
        total_lots += stat["lots_sold"]
        all_buyers.update(stat["buyers"])
        if stat["viewer_peak"]:
            viewer_peaks.append(stat["viewer_peak"])
        if active_minutes:
            active_minutes_samples.append(active_minutes)
        stream_rows_out.append({
            "stream_id": stream_id,
            "streamer_name": stat["streamer_name"],
            "title": stat["title"],
            "revenue": round(stat["revenue"], 2),
            "lots_sold": stat["lots_sold"],
            "messages": stat["messages"],
            "unique_buyers": len(stat["buyers"]),
            "unique_chatters": len(stat["chatters"]),
            "viewer_peak": stat["viewer_peak"] or 0,
            "active_minutes": active_minutes,
            "revenue_per_message": round(stat["revenue"] / stat["messages"], 2) if stat["messages"] else 0.0,
            "conversion_rate": _safe_pct_capped(len(stat["buyers"]), len(stat["chatters"])),
            "recent_messages": stat["recent_messages"],
            "recent_wins": stat["recent_wins"],
            "recent_revenue": round(stat["recent_revenue"], 2),
            "recent_viewer_peak": stat["recent_viewer_peak"],
            "baseline_messages": stat["baseline_messages"],
            "baseline_wins": stat["baseline_wins"],
            "baseline_revenue": round(stat["baseline_revenue"], 2),
            "sentiment_score": round(stat["sentiment_score"], 1),
            "sentiment_positive": stat["sentiment_positive"],
            "sentiment_negative": stat["sentiment_negative"],
        })
        sstat = streamer_stats[stat["streamer_name"]]
        sstat["sessions"] += 1
        sstat["active_minutes"] += active_minutes

    streamer_rows = sorted([
        {
            "streamer_name": row["streamer_name"],
            "sessions": row["sessions"],
            "revenue": round(row["revenue"], 2),
            "lots_sold": row["lots_sold"],
            "messages": row["messages"],
            "unique_buyers": len(row["buyers"]),
            "unique_chatters": len(row["chatters"]),
            "viewer_peak": row["viewer_peak"],
            "avg_revenue_per_session": round(row["revenue"] / row["sessions"], 2) if row["sessions"] else 0.0,
            "conversion_rate": _safe_pct_capped(len(row["buyers"]), len(row["chatters"])),
            "avg_active_minutes": round(row["active_minutes"] / row["sessions"], 1) if row["sessions"] else 0.0,
        }
        for row in streamer_stats.values()
    ], key=lambda x: (x["revenue"], x["conversion_rate"], x["messages"]), reverse=True)[:20]

    best_hours = sorted([
        {
            "hour": hour,
            "revenue": round(row["revenue"], 2),
            "wins": row["wins"],
            "messages": row["messages"],
            "active_streams": len(row["active_streams"]),
            "revenue_per_stream": round(row["revenue"] / len(row["active_streams"]), 2) if row["active_streams"] else 0.0,
        }
        for hour, row in hour_map.items()
        if row["messages"] > 0 or row["wins"] > 0 or row["revenue"] > 0
    ], key=lambda x: (x["revenue"], x["wins"], x["messages"]), reverse=True)[:12]

    repeat_buyers = sorted([
        {
            "username": username,
            "streamers": len(buyer_streamers[username]),
            "sessions": len(buyer_sessions[username]),
            "spend": round(buyer_spend[username], 2),
            "streamer_names": sorted(buyer_streamers[username])[:6],
        }
        for username in buyer_streamers
        if len(buyer_streamers[username]) >= 2
    ], key=lambda x: (x["streamers"], x["spend"], x["sessions"]), reverse=True)[:20]

    keyword_rows = sorted([
        {
            "keyword": row["keyword"],
            "mentions": row["mentions"],
            "conversions": row["conversions"],
            "buyers": len(row["buyers"]),
            "catalog_matches": product_keyword_map[row["keyword"]]["count"],
            "example_products": sorted(product_keyword_map[row["keyword"]]["products"])[:3],
            "conversion_rate": _safe_pct(row["conversions"], row["mentions"]),
            "signal_score": round(
                row["conversions"] * 4 +
                row["mentions"] * 0.6 +
                len(row["buyers"]) * 2 +
                product_keyword_map[row["keyword"]]["count"] * 6,
                1,
            ),
        }
        for row in keyword_stats.values()
        if _keyword_allowed_for_products(row["keyword"], product_keyword_map)
        if row["mentions"] >= 3
    ], key=lambda x: (x["signal_score"], x["catalog_matches"], x["conversions"], x["mentions"]), reverse=True)[:20]

    white_space_keywords = sorted([
        {
            "keyword": row["keyword"],
            "chat_count": row["mentions"],
            "score": round(row["mentions"] * 0.7 + len(row["buyers"]) * 2.0, 1),
        }
        for row in keyword_stats.values()
        if row["mentions"] >= 3
        if row["keyword"] not in product_keyword_map
    ], key=lambda x: (x["score"], x["chat_count"]), reverse=True)[:12]

    product_hotspots = sorted([
        {
            "product_name": row["product_name"],
            "market_presence": len(row["streams"]),
            "streamers": len(row["streamers"]),
            "avg_price": round(sum(row["prices"]) / len(row["prices"]), 2) if row["prices"] else 0.0,
            "price_points": len(row["prices"]),
            "bid_pressure": row["bids"],
            "low_stock_hits": row["low_stock_hits"],
            "top_slot_hits": row["top_slot_hits"],
            "listing_type": max(row["listing_types"].items(), key=lambda item: item[1])[0] if row["listing_types"] else "unknown",
            "button_label": max(row["button_labels"].items(), key=lambda item: item[1])[0] if row["button_labels"] else None,
            "image_url": row["image_url"],
            "signal_score": round(
                len(row["streams"]) * 18 +
                row["bids"] * 3 +
                row["low_stock_hits"] * 10 +
                row["top_slot_hits"] * 5,
                1,
            ),
        }
        for row in product_market.values()
        if not any(term in (row["product_name"] or "").lower() for term in _CATALOG_NOISE_TERMS)
        if not row["prices"] or median(row["prices"]) <= 5000
        if len(row["streams"]) >= 2 or row["bids"] >= 2 or row["low_stock_hits"] >= 1
    ], key=lambda x: (x["signal_score"], x["market_presence"], x["bid_pressure"]), reverse=True)[:20]

    catalog_strategy = {
        "listing_types": sorted(
            [{"type": key, "count": value} for key, value in catalog_type_mix.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:8],
        "button_labels": sorted(
            [{"label": key, "count": value} for key, value in button_label_mix.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:8],
    }

    def _launch_score(row):
        return round(
            row["revenue"] * 1.0 +
            row["wins"] * 35 +
            row["messages"] * 0.8 +
            row["revenue_per_stream"] * 0.6,
            1,
        )

    launch_windows = []
    for row in best_hours[:6]:
        score = _launch_score(row)
        if score >= 400:
            band = "high"
        elif score >= 180:
            band = "medium"
        else:
            band = "low"
        launch_windows.append({
            "hour": row["hour"],
            "score": score,
            "band": band,
            "reason": f"{row['wins']} wins · {row['messages']} chats · ${row['revenue_per_stream']:.2f}/stream",
            "revenue": row["revenue"],
            "messages": row["messages"],
            "wins": row["wins"],
            "revenue_per_stream": row["revenue_per_stream"],
        })

    quiet_windows = sorted([
        {
            "hour": row["hour"],
            "score": round(row["revenue_per_stream"] * 1.4 + row["wins"] * 24 - row["messages"] * 0.25, 1),
            "band": "low_competition" if row["messages"] <= 25 else "balanced",
            "reason": f"{row['messages']} chats · {row['wins']} wins · ${row['revenue_per_stream']:.2f}/stream",
            "revenue": row["revenue"],
            "messages": row["messages"],
            "wins": row["wins"],
            "revenue_per_stream": row["revenue_per_stream"],
        }
        for row in best_hours
        if row["revenue_per_stream"] > 0 and row["messages"] <= 80
    ], key=lambda x: (x["score"], x["revenue_per_stream"], x["wins"]), reverse=True)[:6]
    if not quiet_windows:
        quiet_windows = sorted([
            {
                "hour": row["hour"],
                "score": round(row["revenue_per_stream"] * 1.1 + row["wins"] * 18 - row["messages"] * 0.15, 1),
                "band": "balanced",
                "reason": f"{row['messages']} chats · {row['wins']} wins · ${row['revenue_per_stream']:.2f}/stream",
                "revenue": row["revenue"],
                "messages": row["messages"],
                "wins": row["wins"],
                "revenue_per_stream": row["revenue_per_stream"],
            }
            for row in sorted(best_hours, key=lambda x: (x["messages"], -x["revenue_per_stream"], -x["wins"]))
            if row["revenue_per_stream"] > 0
        ], key=lambda x: (x["score"], x["revenue_per_stream"], x["wins"]), reverse=True)[:6]

    stream_watch_scores = []
    alerts = []
    for row in stream_rows_out:
        recent_score = round(
            row["recent_revenue"] * 1.2 +
            row["recent_wins"] * 30 +
            row["recent_messages"] * 1.3 +
            row["recent_viewer_peak"] * 0.35 +
            max(-20, min(20, row["sentiment_score"] * 3)),
            1,
        )
        baseline_score = (
            row["baseline_revenue"] * 1.2 +
            row["baseline_wins"] * 30 +
            row["baseline_messages"] * 1.3
        )
        if recent_score > 0 or row["recent_messages"] > 0 or row["recent_wins"] > 0:
            stream_watch_scores.append({
                "stream_id": row["stream_id"],
                "streamer_name": row["streamer_name"],
                "score": recent_score,
                "recent_revenue": row["recent_revenue"],
                "recent_wins": row["recent_wins"],
                "recent_messages": row["recent_messages"],
                "recent_viewer_peak": row["recent_viewer_peak"],
                "sentiment_score": row["sentiment_score"],
                "sentiment_label": (
                    "bullish" if row["sentiment_score"] >= 8
                    else "bearish" if row["sentiment_score"] <= -4
                    else "neutral"
                ),
            })
        if recent_score >= max(60, baseline_score * 1.5):
            alerts.append({
                "type": "momentum_spike",
                "streamer_name": row["streamer_name"],
                "message": f"{row['streamer_name']} is spiking now: {row['recent_messages']} chats and {row['recent_wins']} wins in the last 10 minutes.",
                "score": recent_score,
            })
        if row["recent_messages"] >= 18 and row["recent_wins"] == 0:
            alerts.append({
                "type": "chat_without_conversion",
                "streamer_name": row["streamer_name"],
                "message": f"{row['streamer_name']} has heavy chat but weak conversion right now.",
                "score": row["recent_messages"],
            })

    stream_watch_scores.sort(key=lambda x: (x["score"], x["recent_revenue"], x["recent_messages"]), reverse=True)
    alerts = sorted(alerts, key=lambda x: x["score"], reverse=True)[:12]

    buyer_segments = []
    for username, spend in buyer_spend.items():
        streams = len(buyer_streamers[username])
        sessions = len(buyer_sessions[username])
        chats = buyer_messages.get(username, 0)
        if spend >= 250 or sessions >= 5:
            segment = "whale"
        elif chats >= 10 and spend < 80:
            segment = "engaged_non_buyer"
        elif streams >= 2 and spend >= 75:
            segment = "cross_stream_loyalist"
        else:
            segment = "regular"
        buyer_segments.append({
            "username": username,
            "segment": segment,
            "spend": round(spend, 2),
            "streams": streams,
            "sessions": sessions,
            "chat_messages": chats,
        })

    buyer_segment_summary = sorted([
        {
            "segment": segment,
            "buyers": len(rows),
            "avg_spend": round(sum(r["spend"] for r in rows) / len(rows), 2) if rows else 0.0,
            "avg_sessions": round(sum(r["sessions"] for r in rows) / len(rows), 1) if rows else 0.0,
        }
        for segment, rows in {
            "whale": [r for r in buyer_segments if r["segment"] == "whale"],
            "cross_stream_loyalist": [r for r in buyer_segments if r["segment"] == "cross_stream_loyalist"],
            "engaged_non_buyer": [r for r in buyer_segments if r["segment"] == "engaged_non_buyer"],
            "regular": [r for r in buyer_segments if r["segment"] == "regular"],
        }.items()
        if rows
    ], key=lambda x: (x["buyers"], x["avg_spend"]), reverse=True)

    total_positive = sum(r["sentiment_positive"] for r in stream_rows_out)
    total_negative = sum(r["sentiment_negative"] for r in stream_rows_out)
    net_sentiment = total_positive - total_negative
    if net_sentiment >= 80:
        sentiment_label = "bullish"
    elif net_sentiment <= -30:
        sentiment_label = "bearish"
    else:
        sentiment_label = "neutral"

    recommendations = []
    if streamer_rows:
        leader = streamer_rows[0]
        recommendations.append(
            f"Study {leader['streamer_name']} first: highest tracked revenue across spectator sessions."
        )
    if best_hours:
        hour = best_hours[0]
        recommendations.append(
            f"Peak market hour is {hour['hour']:02d}:00 with {hour['wins']} wins and {hour['messages']} chat messages."
        )
    if keyword_rows:
        top_kw = keyword_rows[0]
        recommendations.append(
            f"Keyword '{top_kw['keyword']}' is converting strongly across streams."
        )
    if repeat_buyers:
        recommendations.append(
            f"{repeat_buyers[0]['username']} appears across {repeat_buyers[0]['streamers']} different streamers — strong cross-market buyer signal."
        )
    if launch_windows:
        recommendations.append(
            f"Best go-live window looks like {launch_windows[0]['hour']:02d}:00 based on market revenue, wins, and chat intensity."
        )
    if quiet_windows:
        recommendations.append(
            f"If you want lower competition, test {quiet_windows[0]['hour']:02d}:00 where revenue per stream stays healthy with lighter chat volume."
        )
    if stream_watch_scores:
        recommendations.append(
            f"Watch {stream_watch_scores[0]['streamer_name']} now — strongest current momentum score in the live market."
        )
    if product_hotspots:
        recommendations.append(
            f"Catalog signal says push products like '{product_hotspots[0]['product_name']}' — broad market presence with strong bid pressure."
        )

    avg_stream_price = round(total_revenue / max(total_lots, 1), 2) if total_lots else 0.0
    if avg_stream_price >= 60:
        regime = "premium-led"
    elif avg_stream_price <= 18 and total_messages >= 1000:
        regime = "volume-led"
    else:
        regime = "hybrid"
    heat_score = round(_clamp(
        (sum(row["score"] for row in stream_watch_scores[:5]) / max(len(stream_watch_scores[:5]), 1)) * 0.18 +
        total_messages * 0.002 +
        len(all_buyers) * 0.08 +
        max(net_sentiment, 0) * 0.12,
        0,
        100,
    ), 1)
    if heat_score >= 70:
        heat_label = "hot"
    elif heat_score >= 40:
        heat_label = "warm"
    else:
        heat_label = "cool"
    advanced_signals = {
        "market_regime": {
            "label": regime,
            "avg_realized_price": avg_stream_price,
            "note": (
                "Higher-ticket rooms are driving the market."
                if regime == "premium-led"
                else "Low-start / pace sellers are setting the tone."
                if regime == "volume-led"
                else "The market is mixed between pace and price extraction."
            ),
        },
        "demand_temperature": {
            "label": heat_label,
            "score": heat_score,
            "note": f"{total_messages} chat events and {len(all_buyers)} buyers are shaping the current market temperature.",
        },
        "timing_confidence": {
            "best_hour": best_hours[0]["hour"] if best_hours else None,
            "confidence": round(_clamp(
                (best_hours[0]["revenue_per_stream"] if best_hours else 0) * 0.03 +
                (best_hours[0]["wins"] if best_hours else 0) * 2.5 +
                (best_hours[0]["messages"] if best_hours else 0) * 0.08,
                0,
                100,
            ), 1) if best_hours else 0.0,
        },
        "white_space_keywords": white_space_keywords[:8],
        "playbook": [
            recommendations[0] if recommendations else "Wait for stronger signal concentration before forcing a move.",
            f"Current market regime looks {regime}." if regime else None,
            f"Demand temperature is {heat_label} with score {heat_score}." if heat_score else None,
            f"Use {keyword_rows[0]['keyword']} style language when relevant." if keyword_rows else None,
        ],
    }
    advanced_signals["playbook"] = [item for item in advanced_signals["playbook"] if item]

    result = {
        "summary": {
            "tracked_streams": len(stream_rows_out),
            "tracked_streamers": len(streamer_rows),
            "total_revenue": round(total_revenue, 2),
            "lots_sold": total_lots,
            "chat_messages": total_messages,
            "unique_buyers": len(all_buyers),
            "avg_viewer_peak": round(sum(viewer_peaks) / len(viewer_peaks), 1) if viewer_peaks else 0.0,
            "avg_active_minutes": round(sum(active_minutes_samples) / len(active_minutes_samples), 1) if active_minutes_samples else 0.0,
        },
        "market_sentiment": {
            "label": sentiment_label,
            "score": net_sentiment,
            "positive_mentions": total_positive,
            "negative_mentions": total_negative,
        },
        "top_streamers": streamer_rows,
        "best_hours": best_hours,
        "launch_windows": launch_windows,
        "quiet_windows": quiet_windows,
        "stream_watch_scores": stream_watch_scores[:20],
        "alerts": alerts,
        "repeat_buyers": repeat_buyers,
        "buyer_segments": buyer_segment_summary,
        "product_hotspots": product_hotspots,
        "catalog_strategy": catalog_strategy,
        "keyword_signals": keyword_rows,
        "top_streams": sorted(stream_rows_out, key=lambda x: (x["revenue"], x["messages"], x["viewer_peak"]), reverse=True)[:25],
        "recommendations": recommendations,
        "advanced_signals": advanced_signals,
    }
    _timed_cache_set(cache_key, result)
    return result


def get_company_livestream_intelligence(db_path=None, whatnot_account="ynfdeals"):
    _require_postgres_analytics(db_path=db_path)
    db = _analytics_db_path(db_path)
    cache_key = ("company_livestream_intelligence", db, (whatnot_account or "").lower())
    cached = _timed_cache_get(cache_key, ttl_seconds=45)
    if cached is not None:
        return cached
    sessions = list_company_sessions(whatnot_account, limit=500)
    if not sessions:
        result = {
            "summary": {},
            "hourly": [],
            "by_day": [],
            "top_buyers": [],
            "silent_buyers": [],
            "chat_keywords": [],
            "products": [],
            "recommendations": {},
            "live_mode": {"running": False, "suggestions": []},
            "data_limits": [
            "Need more session history to generate intelligence.",
            ],
        }
        _timed_cache_set(cache_key, result)
        return result

    catalog_rows = list_products(active_only=False, low_stock_only=False, include_sales_metrics=False)
    catalog_by_name = {
        (row.get("name") or "").strip().lower(): row
        for row in catalog_rows
        if (row.get("name") or "").strip()
    }

    auction_rows = list_auction_results_for_sessions(
        [session.get("id") for session in sessions],
        limit_per_session=5000,
    )

    ensure_wave1_postgres_schema()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, streamer_name, started_at, ended_at
                FROM {POSTGRES_SIDECAR_SCHEMA}.streams
                WHERE LOWER(COALESCE(streamer_name, '')) = %s
                ORDER BY id DESC
                """,
                (whatnot_account.lower(),),
            )
            our_stream_rows = _fetchall_dict_pg(cur)
            our_stream_ids = [row["id"] for row in our_stream_rows]
            events = []
            if our_stream_ids:
                cur.execute(
                    f"""
                    SELECT stream_id, event_type, payload, created_at
                    FROM {POSTGRES_SIDECAR_SCHEMA}.events
                    WHERE stream_id = ANY(%s)
                      AND event_type IN ('chat_message', 'bid_update', 'bid_event', 'auction_winner', 'live_viewers', 'lot_update', 'viewer_join', 'viewer_leave')
                    ORDER BY id ASC
                    """,
                    (our_stream_ids,),
                )
                events = _fetchall_dict_pg(cur)

    hour_map = {hour: {
        "hour": hour, "revenue": 0.0, "profit": 0.0, "wins": 0, "avg_bid": 0.0,
        "chat_count": 0, "bid_count": 0, "active_users": set(), "buyers": set(),
    } for hour in range(24)}
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_map = {day: {
        "day": day, "sessions": 0, "revenue": 0.0, "profit": 0.0, "engagement": 0,
        "active_users": set(), "buyers": set(), "chat_count": 0, "bid_count": 0, "wins": 0,
    } for day in day_names}

    session_revenues = []
    session_durations = []
    session_start_hours = defaultdict(list)
    buyer_map = defaultdict(lambda: {"username": "", "orders": 0, "sessions": set(), "revenue": 0.0, "profit": 0.0, "products": set()})
    product_map = defaultdict(lambda: {
        "product_name": "", "wins": 0, "revenue": 0.0, "profit": 0.0, "margin_samples": [],
        "hours": defaultdict(int), "days": defaultdict(int), "competition_score": 0,
        "our_cost": 0.0, "our_retail_price": 0.0, "sale_prices": [],
    })
    session_stream_by_id = {
        int(session.get("id")): session.get("stream_id")
        for session in sessions
        if session.get("id") is not None
    }

    for session in sessions:
        start_dt = _parse_ts_local(session.get("started_at"))
        end_dt = _parse_ts_local(session.get("ended_at"))
        if start_dt:
            day = day_names[start_dt.weekday()]
            day_row = day_map[day]
            day_row["sessions"] += 1
            day_row["revenue"] += float(session.get("total_revenue") or 0)
            day_row["profit"] += float(session.get("total_profit") or 0)
            session_start_hours[start_dt.hour].append(float(session.get("total_revenue") or 0))
            session_revenues.append(float(session.get("total_revenue") or 0))
        if start_dt and end_dt:
            session_durations.append(max(1, round((end_dt - start_dt).total_seconds() / 60)))

    for row in auction_rows:
        sold_dt = _parse_ts_local(row.get("sold_at"))
        if not sold_dt:
            continue
        hour_row = hour_map[sold_dt.hour]
        day_row = day_map[day_names[sold_dt.weekday()]]
        sale_price = float(row.get("sale_price") or 0)
        profit = float(row.get("profit") or 0)
        username = (row.get("winner_username") or "").strip()
        product_name = (row.get("product_name") or "Unknown").strip()

        hour_row["revenue"] += sale_price
        hour_row["profit"] += profit
        hour_row["wins"] += 1
        if username:
            hour_row["buyers"].add(username.lower())
            day_row["buyers"].add(username.lower())

        day_row["revenue"] += sale_price
        day_row["profit"] += profit
        day_row["wins"] += 1

        if username:
            buyer = buyer_map[username.lower()]
            buyer["username"] = username
            buyer["orders"] += 1
            buyer["sessions"].add(row.get("session_id"))
            buyer["revenue"] += sale_price
            buyer["profit"] += profit
            if product_name:
                buyer["products"].add(product_name)

        product = product_map[product_name]
        product["product_name"] = product_name
        product["wins"] += 1
        product["revenue"] += sale_price
        product["profit"] += profit
        if sale_price > 0:
            product["sale_prices"].append(sale_price)
        product["hours"][sold_dt.hour] += 1
        product["days"][day_names[sold_dt.weekday()]] += 1
        if row.get("margin_pct") is not None:
            try:
                product["margin_samples"].append(float(row.get("margin_pct")))
            except Exception:
                pass
        if row.get("cost_price") is not None:
            try:
                product["our_cost"] = max(float(product["our_cost"] or 0), float(row.get("cost_price") or 0))
            except Exception:
                pass
        catalog_match = catalog_by_name.get(product_name.lower())
        if catalog_match and catalog_match.get("retail_price") is not None:
            try:
                product["our_retail_price"] = max(
                    float(product["our_retail_price"] or 0),
                    float(catalog_match.get("retail_price") or 0),
                )
            except Exception:
                pass

    chat_by_stream_user = defaultdict(list)
    first_activity_by_stream_user = {}
    buyer_event_usernames = set()
    keyword_stats = defaultdict(lambda: {"keyword": "", "mentions": 0, "conversions": 0, "buyers": set()})
    recent_now = datetime.now(timezone.utc)
    live_event_rows = []
    viewer_history = []
    lot_updates = []
    bidder_map = defaultdict(lambda: {"username": "", "bid_count": 0, "lots": set(), "max_bid": 0.0})
    viewer_events_available = False
    bidder_events_available = False
    bid_updates_by_stream_lot = defaultdict(int)
    named_bid_events_by_stream_lot = defaultdict(int)
    events_by_stream = defaultdict(list)

    for event in events:
        event_dt = _parse_dt(event.get("created_at"))
        local_dt = _parse_ts_local(event.get("created_at"))
        if not event_dt or not local_dt:
            continue
        payload = _parse_payload(event.get("payload"))
        stream_id = event.get("stream_id")
        event_type = event.get("event_type")
        lot_number = str(payload.get("lot_number") or "").strip()
        hour_row = hour_map[local_dt.hour]
        day_row = day_map[day_names[local_dt.weekday()]]
        events_by_stream[stream_id].append(
            {
                "event_type": event_type,
                "event_dt": event_dt,
                "created_at": event.get("created_at"),
                "payload": payload,
                "lot_number": lot_number,
            }
        )

        if event_type == "chat_message":
            username = (payload.get("username") or payload.get("user") or "").strip()
            hour_row["chat_count"] += 1
            day_row["chat_count"] += 1
            if username:
                key = (stream_id, username.lower())
                hour_row["active_users"].add(username.lower())
                day_row["active_users"].add(username.lower())
                chat_by_stream_user[key].append({"message": payload.get("message") or "", "time": event_dt})
                first_activity_by_stream_user[key] = min(first_activity_by_stream_user.get(key, event_dt), event_dt)
        elif event_type == "bid_update":
            hour_row["bid_count"] += 1
            day_row["bid_count"] += 1
            if lot_number:
                bid_updates_by_stream_lot[(stream_id, lot_number)] += 1
        elif event_type == "bid_event":
            username = (payload.get("username") or "").strip()
            hour_row["bid_count"] += 1
            day_row["bid_count"] += 1
            bidder_events_available = True
            if lot_number:
                named_bid_events_by_stream_lot[(stream_id, lot_number)] += 1
            if username:
                bidder = bidder_map[username.lower()]
                bidder["username"] = username
                bidder["bid_count"] += 1
                if lot_number:
                    bidder["lots"].add(lot_number)
                try:
                    bidder["max_bid"] = max(bidder["max_bid"], float(payload.get("amount") or 0))
                except Exception:
                    pass
        elif event_type == "auction_winner":
            username = (payload.get("winner") or payload.get("winner_username") or payload.get("username") or "").strip()
            if username:
                key = (stream_id, username.lower())
                buyer_event_usernames.add(username.lower())
                first_activity_by_stream_user.setdefault(key, event_dt)
                hour_row["active_users"].add(username.lower())
                day_row["active_users"].add(username.lower())
                prior_messages = [
                    m for m in chat_by_stream_user.get(key, [])
                    if m["time"] <= event_dt and (event_dt - m["time"]).total_seconds() <= 1800
                ]
                seen_kw = set()
                for msg in prior_messages:
                    for kw in _keywords(msg["message"]):
                        stat = keyword_stats[kw]
                        stat["keyword"] = kw
                        stat["mentions"] += 1
                        if kw not in seen_kw:
                            stat["conversions"] += 1
                            stat["buyers"].add(username.lower())
                            seen_kw.add(kw)
        elif event_type == "live_viewers":
            viewer_count = payload.get("viewer_count")
            try:
                viewer_count = int(viewer_count)
            except Exception:
                viewer_count = None
            if viewer_count is not None:
                viewer_history.append({
                    "time": event.get("created_at"),
                    "viewer_count": viewer_count,
                })
        elif event_type in ("viewer_join", "viewer_leave"):
            viewer_events_available = True
            username = (payload.get("username") or "").strip()
            if username:
                if event_type == "viewer_join":
                    hour_row["active_users"].add(username.lower())
                    day_row["active_users"].add(username.lower())
        elif event_type == "lot_update":
            lot_updates.append({
                "stream_id": stream_id,
                "lot_number": str(payload.get("lot_number") or "").strip(),
                "product_name": (payload.get("product_name") or "").strip(),
                "shown_at": event.get("created_at"),
            })
        if (recent_now - event_dt).total_seconds() <= 900:
            live_event_rows.append({"event_type": event_type, "payload": payload, "time": event_dt})

    for row in auction_rows:
        product_name = (row.get("product_name") or "Unknown").strip()
        if not product_name:
            continue
        stream_id = session_stream_by_id.get(int(row.get("session_id") or 0))
        lot_number = str(row.get("lot_number") or "").strip()
        product_map[product_name]["competition_score"] += named_bid_events_by_stream_lot.get(
            (stream_id, lot_number),
            bid_updates_by_stream_lot.get((stream_id, lot_number), 0),
        )

    hourly = []
    for hour in range(24):
        row = hour_map[hour]
        avg_bid = row["revenue"] / row["wins"] if row["wins"] else 0
        hourly.append({
            "hour": hour,
            "revenue": round(row["revenue"], 2),
            "profit": round(row["profit"], 2),
            "wins": row["wins"],
            "avg_bid": round(avg_bid, 2),
            "chat_count": row["chat_count"],
            "bid_count": row["bid_count"],
            "conversion_rate": _safe_pct(len(row["buyers"]), len(row["active_users"])),
        })

    by_day = []
    for day in day_names:
        row = day_map[day]
        by_day.append({
            "day": day,
            "sessions": row["sessions"],
            "revenue": round(row["revenue"], 2),
            "profit": round(row["profit"], 2),
            "engagement": row["chat_count"] + row["bid_count"] + row["wins"],
            "avg_revenue_per_session": round((row["revenue"] / row["sessions"]), 2) if row["sessions"] else 0,
            "avg_profit_per_session": round((row["profit"] / row["sessions"]), 2) if row["sessions"] else 0,
            "conversion_rate": _safe_pct(len(row["buyers"]), len(row["active_users"])),
        })

    top_buyers = sorted(
        [{
            "username": buyer["username"],
            "orders": buyer["orders"],
            "session_count": len(buyer["sessions"]),
            "revenue": round(buyer["revenue"], 2),
            "profit": round(buyer["profit"], 2),
            "products": sorted(list(buyer["products"]))[:6],
        } for buyer in buyer_map.values()],
        key=lambda x: (x["revenue"], x["orders"]),
        reverse=True,
    )[:20]

    chatted_usernames = {username for (_, username) in chat_by_stream_user.keys()}
    silent_buyers = sorted(
        [buyer["username"] for buyer in buyer_map.values() if buyer["username"].lower() not in chatted_usernames],
    )[:20]

    time_to_buy_samples = []
    for event in events:
        if event.get("event_type") != "auction_winner":
            continue
        payload = _parse_payload(event.get("payload"))
        username = (payload.get("winner") or payload.get("winner_username") or payload.get("username") or "").strip()
        event_dt = _parse_dt(event.get("created_at"))
        if not username or not event_dt:
            continue
        first_dt = first_activity_by_stream_user.get((event.get("stream_id"), username.lower()))
        if first_dt and event_dt >= first_dt:
            time_to_buy_samples.append((event_dt - first_dt).total_seconds() / 60.0)

    chat_keywords = sorted(
        [{
            "keyword": stat["keyword"],
            "mentions": stat["mentions"],
            "conversions": stat["conversions"],
            "conversion_score": round(stat["conversions"] * 3 + stat["mentions"] * 0.5, 1),
        } for stat in keyword_stats.values() if stat["conversions"] > 0],
        key=lambda x: (x["conversions"], x["mentions"]),
        reverse=True,
    )[:20]

    products = sorted(
        [{
            "product_name": product["product_name"],
            "wins": product["wins"],
            "revenue": round(product["revenue"], 2),
            "profit": round(product["profit"], 2),
            "margin_pct": round(sum(product["margin_samples"]) / len(product["margin_samples"]), 1) if product["margin_samples"] else 0,
            "competition_score": product["competition_score"],
            "best_hour": max(product["hours"], key=product["hours"].get) if product["hours"] else None,
            "best_day": max(product["days"], key=product["days"].get) if product["days"] else None,
            "our_cost": round(float(product["our_cost"] or 0), 2),
            "our_retail_price": round(float(product["our_retail_price"] or 0), 2),
            "expected_price_range": _price_range(product["sale_prices"]),
        } for product in product_map.values()],
        key=lambda x: (x["profit"], x["revenue"]),
        reverse=True,
    )[:25]

    profitable_hours = [row for row in hourly if row["profit"] > 0]
    best_hour = max(profitable_hours or hourly, key=lambda x: x["profit"] if x["profit"] else x["revenue"])
    best_day_profit = max(by_day, key=lambda x: x["avg_profit_per_session"] if x["sessions"] else -1)
    best_day_engagement = max(by_day, key=lambda x: x["engagement"])
    best_day_conversion = max(by_day, key=lambda x: x["conversion_rate"])
    best_start_hour = max(
        [{"hour": h, "avg_revenue": round(sum(vals) / len(vals), 2)} for h, vals in session_start_hours.items()],
        key=lambda x: x["avg_revenue"],
        default={"hour": best_hour["hour"], "avg_revenue": 0},
    )
    avg_duration = round(sum(session_durations) / len(session_durations)) if session_durations else 90
    sorted_revenues = sorted(session_revenues)
    expected_low = round(sorted_revenues[max(0, len(sorted_revenues) // 4 - 1)], 2) if sorted_revenues else 0
    expected_high = round(sorted_revenues[min(len(sorted_revenues) - 1, max(len(sorted_revenues) - 1, 0))], 2) if sorted_revenues else 0
    if sorted_revenues:
        expected_high = round(sorted_revenues[max(0, math.ceil(len(sorted_revenues) * 0.75) - 1)], 2)

    sequence = []
    high_margin = [p for p in products if p["margin_pct"] >= 20][:3]
    high_comp = [p for p in products if p["competition_score"] >= 3][:3]
    if high_margin:
        sequence.append("Start with proven high-margin winners to establish profitable momentum.")
    if high_comp:
        sequence.append("Move competitive, bid-heavy products into the middle of the stream when chat energy is highest.")
    sequence.append("Close with bundles or value stacks if bid pace slows near the end.")

    live_stream = next((s for s in sessions if s.get("status") == "live"), None)
    live_mode = {"running": bool(live_stream), "suggestions": [], "current_revenue": 0.0, "historical_avg_revenue": 0.0}
    if live_stream:
        started_dt = _parse_dt(live_stream.get("started_at"))
        elapsed_minutes = round((datetime.now(timezone.utc) - started_dt).total_seconds() / 60) if started_dt else 0
        current_revenue = float(live_stream.get("total_revenue") or 0)
        hist_avg = round(sum(session_revenues) / len(session_revenues), 2) if session_revenues else 0
        recent_chat = sum(1 for e in live_event_rows if e["event_type"] == "chat_message")
        recent_wins = sum(1 for e in live_event_rows if e["event_type"] == "auction_winner")
        recent_avg_price = round(sum(_parse_winner_price(e["payload"]) for e in live_event_rows if e["event_type"] == "auction_winner") / recent_wins, 2) if recent_wins else 0
        live_mode.update({
            "elapsed_minutes": elapsed_minutes,
            "current_revenue": round(current_revenue, 2),
            "historical_avg_revenue": hist_avg,
        })
        if recent_chat >= 8 and recent_wins == 0:
            live_mode["suggestions"].append("Switch product now: chat is active but not converting into wins.")
        if recent_chat >= 6 and recent_wins <= 1:
            live_mode["suggestions"].append("Increase urgency messaging: engagement is present but purchase conversion is lagging.")
        if recent_wins >= 1 and recent_avg_price < best_hour["avg_bid"]:
            live_mode["suggestions"].append("Run a bundle deal: recent win prices are below your stronger historical price range.")
        if current_revenue < hist_avg * 0.5 and elapsed_minutes >= 30:
            top_profit_product = next((p for p in products if p.get("product_name")), None)
            if top_profit_product:
                live_mode["suggestions"].append({
                    "message": "Push a top-profit product earlier than usual to catch up to historical pace.",
                    "product_name": top_profit_product.get("product_name"),
                    "retail_price": top_profit_product.get("our_retail_price"),
                    "our_cost": top_profit_product.get("our_cost"),
                })
            else:
                live_mode["suggestions"].append("Push a top-profit product earlier than usual to catch up to historical pace.")

    next_best_products = []
    current_hour = datetime.now().astimezone().hour
    for product in products:
        expected = product.get("expected_price_range") or {"low": 0.0, "mid": 0.0, "high": 0.0}
        timing_bonus = 10.0 if product.get("best_hour") == current_hour else 4.0 if product.get("best_hour") in {(current_hour - 1) % 24, (current_hour + 1) % 24} else 0.0
        stock_signal = 8.0 if float(product.get("our_retail_price") or 0) > float(product.get("our_cost") or 0) else 0.0
        score = round(_clamp(
            float(product.get("profit") or 0) * 0.18 +
            float(product.get("margin_pct") or 0) * 0.9 +
            float(product.get("competition_score") or 0) * 3.8 +
            float(product.get("wins") or 0) * 2.8 +
            timing_bonus + stock_signal,
            0.0,
            100.0,
        ), 1)
        next_best_products.append({
            "product_name": product["product_name"],
            "score": score,
            "why": [
                f"{product['wins']} wins",
                f"{product['margin_pct']}% avg margin",
                f"expected {expected['low']}-{expected['high']}",
                f"best hour {product.get('best_hour') if product.get('best_hour') is not None else '—'}",
            ],
            "expected_price_range": expected,
            "profit": product["profit"],
            "margin_pct": product["margin_pct"],
        })
    next_best_products.sort(key=lambda row: (row["score"], row["profit"], row["margin_pct"]), reverse=True)

    sale_orders = list_sale_orders()
    unpaid_orders = [order for order in sale_orders if order.get("payment_status") == "unpaid" and order.get("state") != "cancel"]
    paid_users = {
        (order.get("whatnot_buyer_username") or "").strip().lower()
        for order in sale_orders
        if order.get("payment_status") == "paid" and (order.get("whatnot_buyer_username") or "").strip()
    }
    unpaid_winner_signals = sorted({
        (order.get("whatnot_buyer_username") or "").strip()
        for order in unpaid_orders
        if (order.get("whatnot_buyer_username") or "").strip()
    })
    unpaid_winner_signal_set = {u.lower() for u in unpaid_winner_signals}
    repeat_buyers = [
        buyer for buyer in top_buyers
        if buyer["session_count"] >= 2
    ]
    top_bidders = sorted(
        [{
            "username": bidder["username"],
            "bid_count": bidder["bid_count"],
            "lot_count": len(bidder["lots"]),
            "max_bid": round(bidder["max_bid"], 2),
        } for bidder in bidder_map.values()],
        key=lambda x: (x["bid_count"], x["max_bid"]),
        reverse=True,
    )[:20]

    product_timeline = []
    for update in lot_updates[-100:]:
        shown_dt = _parse_dt(update["shown_at"])
        if not shown_dt:
            continue
        chat_count = 0
        bid_update_count = 0
        named_bid_count = 0
        final_sale = 0.0
        winner = None
        unique_chatters = set()
        unique_bidders = set()
        sold_at = None
        viewer_joins = 0
        viewer_leaves = 0
        for event in events_by_stream.get(update["stream_id"], []):
            event_dt = event.get("event_dt")
            if not event_dt or event_dt < shown_dt or (event_dt - shown_dt).total_seconds() > 600:
                continue
            payload = event.get("payload") or {}
            if event.get("event_type") == "chat_message":
                chat_count += 1
                chatter = (payload.get("username") or payload.get("user") or "").strip()
                if chatter:
                    unique_chatters.add(chatter.lower())
            elif event.get("event_type") == "bid_update" and event.get("lot_number") == update["lot_number"]:
                bid_update_count += 1
            elif event.get("event_type") == "bid_event" and event.get("lot_number") == update["lot_number"]:
                named_bid_count += 1
                bidder = (payload.get("username") or "").strip()
                if bidder:
                    unique_bidders.add(bidder.lower())
            elif event.get("event_type") == "viewer_join" and event.get("lot_number") == update["lot_number"]:
                viewer_joins += 1
            elif event.get("event_type") == "viewer_leave" and event.get("lot_number") == update["lot_number"]:
                viewer_leaves += 1
            elif event.get("event_type") == "auction_winner" and event.get("lot_number") == update["lot_number"]:
                final_sale = _parse_winner_price(payload)
                winner = (payload.get("winner") or payload.get("winner_username") or "").strip() or None
                sold_at = event.get("created_at")
        bid_count = named_bid_count or bid_update_count
        viewer_net = viewer_joins - viewer_leaves
        conversion_score = round(
            min(100.0, (
                chat_count * 2.5 +
                len(unique_chatters) * 3.0 +
                bid_count * 6.0 +
                len(unique_bidders) * 8.0 +
                (18.0 if final_sale > 0 else 0.0) +
                max(-10.0, min(10.0, viewer_net * 2.0))
            )),
            1,
        )
        product_timeline.append({
            "product_name": update["product_name"] or "Unknown",
            "lot_number": update["lot_number"] or "—",
            "shown_at": update["shown_at"],
            "sold_at": sold_at,
            "seconds_to_sale": round((_parse_dt(sold_at) - shown_dt).total_seconds()) if sold_at and _parse_dt(sold_at) else None,
            "chat_count_10m": chat_count,
            "unique_chatters_10m": len(unique_chatters),
            "bid_count_10m": bid_count,
            "named_bid_count_10m": named_bid_count,
            "unique_bidders_10m": len(unique_bidders),
            "viewer_joins_10m": viewer_joins,
            "viewer_leaves_10m": viewer_leaves,
            "viewer_net_10m": viewer_net,
            "conversion_score": conversion_score,
            "final_sale": round(final_sale, 2),
            "winner": winner,
        })

    buyer_intent_scores = []
    recent_cutoff = recent_now.timestamp() - 900
    for (stream_id, username), messages in chat_by_stream_user.items():
        recent_messages = [m for m in messages if m["time"].timestamp() >= recent_cutoff]
        bidder = bidder_map.get(username, {})
        buyer = buyer_map.get(username, {})
        score = (
            len(recent_messages) * 7.0 +
            bidder.get("bid_count", 0) * 15.0 +
            len(buyer.get("sessions", set())) * 5.0 +
            min(float(buyer.get("revenue", 0.0)), 300.0) * 0.08
        )
        if username in paid_users:
            score += 12.0
        if username in unpaid_winner_signal_set:
            score -= 8.0
        score = round(_clamp(score, 0.0, 100.0), 1)
        if score <= 0:
            continue
        buyer_intent_scores.append({
            "username": username,
            "intent_score": score,
            "recent_messages": len(recent_messages),
            "bid_count": bidder.get("bid_count", 0),
            "historical_revenue": round(float(buyer.get("revenue", 0.0)), 2),
            "is_paid_customer": username in paid_users,
        })
    buyer_intent_scores.sort(key=lambda row: (row["intent_score"], row["bid_count"], row["historical_revenue"]), reverse=True)

    lot_health = []
    for row in product_timeline[-12:]:
        score = float(row.get("conversion_score") or 0)
        if row.get("final_sale", 0) > 0 and score >= 45:
            status = "hot"
        elif row.get("bid_count_10m", 0) >= 1 or row.get("chat_count_10m", 0) >= 6:
            status = "steady"
        else:
            status = "stalling"
        stall_risk = round(_clamp(100 - score + (10 if row.get("final_sale", 0) <= 0 else -10), 0, 100), 1)
        lot_health.append({
            "lot_number": row["lot_number"],
            "product_name": row["product_name"],
            "status": status,
            "stall_risk": stall_risk,
            "conversion_score": score,
            "final_sale": row["final_sale"],
        })

    chat_counts = [row["chat_count"] for row in hourly if row["chat_count"] > 0]
    win_counts = [row["wins"] for row in hourly if row["wins"] > 0]
    dropoff_windows = []
    if chat_counts:
        chat_mid = median(chat_counts)
        win_mid = median(win_counts) if win_counts else 1
        for row in hourly:
            if row["chat_count"] >= chat_mid and row["wins"] <= win_mid:
                dropoff_windows.append(f"{row['hour']:02d}:00")

    result = {
        "summary": {
            "total_sessions": len(sessions),
            "total_revenue": round(sum(session_revenues), 2),
            "total_profit": round(sum(float(s.get("total_profit") or 0) for s in sessions), 2),
            "avg_minutes_to_buy": round(sum(time_to_buy_samples) / len(time_to_buy_samples), 1) if time_to_buy_samples else None,
            "peak_profit_window": f"{best_hour['hour']:02d}:00-{best_hour['hour']:02d}:59",
            "repeat_buyer_count": len(repeat_buyers),
            "unpaid_order_count": len(unpaid_orders),
        },
        "hourly": hourly,
        "by_day": by_day,
        "top_buyers": top_buyers,
        "top_bidders": top_bidders,
        "repeat_buyers": repeat_buyers,
        "silent_buyers": silent_buyers,
        "chat_keywords": chat_keywords,
        "products": products,
        "viewer_history": viewer_history[-200:],
        "product_timeline": product_timeline[-60:],
        "unpaid_winner_signals": unpaid_winner_signals[:25],
        "advanced_models": {
            "price_expectations": products[:10],
            "next_best_products": next_best_products[:8],
            "buyer_intent_scores": buyer_intent_scores[:12],
            "lot_health": lot_health,
        },
        "recommendations": {
            "best_day_to_go_live": best_day_profit["day"],
            "highest_engagement_day": best_day_engagement["day"],
            "best_conversion_day": best_day_conversion["day"],
            "best_start_time_hour": best_start_hour["hour"],
            "recommended_duration_minutes": avg_duration,
            "expected_revenue_low": expected_low,
            "expected_revenue_high": expected_high,
            "best_product_sequence_strategy": sequence,
            "dropoff_windows": dropoff_windows[:5],
        },
        "live_mode": live_mode,
        "data_limits": [
            *([] if viewer_events_available else ["Exact viewer join/leave tracking is not active yet. Set viewer list selectors in the collector to capture named viewer join/leave events."]),
            *([] if bidder_events_available else ["Per-user bid attribution is not active yet. Set bid feed selectors in the collector to capture bidder usernames from the auction UI."]),
        ],
    }
    _timed_cache_set(cache_key, result)
    return result
