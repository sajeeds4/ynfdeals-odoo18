import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import { Badge, EmptyRow, FilterBar, SearchInput, TableShell, Thead, fmt, fmtDt } from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';

const TIKTOK_PLATFORM_FEE_RATE = 0.06;
const TIKTOK_SELLER_ORDER_DETAIL_URL = 'https://seller-us.tiktok.com/order/detail';

function normalizeBarcode(value) {
  const raw = String(value || '').trim();
  if (raw === '3220360598918') return '6290360598918';
  return raw;
}

function compactLiveProductName(value) {
  return String(value || '')
    .replace(/\s*\([^)]*\boz\b[^)]*\)/gi, '')
    .replace(/\s+\bPerfume\b\s*$/i, '')
    .replace(/\s+\bFragrances?\b\s*$/i, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function extractLotNumber(order) {
  const direct = String(order?.lot_number || '').trim();
  if (direct) return direct;
  const externalRef = String(order?.external_order_ref || '').trim();
  const refParts = externalRef.split(':');
  if (refParts.length >= 3 && /^tiktok_(?:live|shop)$/i.test(refParts[0])) {
    const last = String(refParts[refParts.length - 1] || '').trim();
    const previous = String(refParts[refParts.length - 2] || '').trim();
    if (/^\d{15,22}$/.test(last) && /^\d+$/.test(previous)) return previous;
    if (/^\d+$/.test(last)) return last;
  }
  const suffixMatch = externalRef.match(/-LOT-([^-]+)$/i);
  if (suffixMatch?.[1]) return suffixMatch[1].trim();
  const notes = String(order?.notes || '');
  const notesMatch = notes.match(/(?:^|\n)Lot:\s*([^\n]+)/i);
  return notesMatch?.[1] ? notesMatch[1].trim() : '';
}

function extractTikTokOrderId(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^\d{15,22}$/.test(raw)) return raw;
  const longNumericParts = raw.match(/\b\d{15,22}\b/g) || [];
  return longNumericParts[0] || '';
}

function getSessionOrderRefs(item) {
  return new Set(
    (Array.isArray(item?.importedOrderRefs) ? item.importedOrderRefs : [])
      .map((ref) => String(ref || '').trim())
      .filter(Boolean),
  );
}

function profitColor(value) {
  return Number(value || 0) < 0 ? 'var(--accent-coral)' : 'var(--accent-emerald)';
}

function signedPct(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return '0.0%';
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}%`;
}

function comparePct(current, baseline) {
  const left = Number(current || 0);
  const right = Number(baseline || 0);
  if (!Number.isFinite(left) || !Number.isFinite(right) || Math.abs(right) < 0.0001) return null;
  return ((left - right) / Math.abs(right)) * 100;
}

function pickSignal(value, goodWhenHigh = true) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return { label: 'No history', tone: 'slate' };
  if (Math.abs(num) < 5) return { label: 'Flat', tone: 'slate' };
  const positive = num > 0;
  if ((positive && goodWhenHigh) || (!positive && !goodWhenHigh)) return { label: positive ? 'Bullish' : 'Improving', tone: 'green' };
  return { label: positive ? 'Risk up' : 'Bearish', tone: 'red' };
}

function platformFee(value) {
  return Math.round(Number(value || 0) * TIKTOK_PLATFORM_FEE_RATE * 100) / 100;
}

function resolvePlatformFee(salesPrice, ...values) {
  const explicitFee = values
    .map((value) => Number(value))
    .find((value) => Number.isFinite(value) && value > 0);
  return explicitFee ?? platformFee(salesPrice);
}

function firstPositiveNumber(...values) {
  return values
    .map((value) => Number(value))
    .find((value) => Number.isFinite(value) && value > 0);
}

function isDeliveredOrder(order) {
  return Boolean(
    order
    && order.state !== 'cancel'
    && (
      order.fulfillment_status === 'delivered'
      || order.tracking_status === 'delivered'
      || String(order.delivered_at || '').trim()
    ),
  );
}

function detailToggleStyle(active = false, tone = 'blue') {
  const tones = {
    slate: { bg: '#f8fafc', border: '#cbd5e1', color: '#334155' },
    blue: { bg: '#eff6ff', border: '#bfdbfe', color: '#1d4ed8' },
    green: { bg: '#ecfdf5', border: '#bbf7d0', color: '#047857' },
    red: { bg: '#fef2f2', border: '#fecaca', color: '#dc2626' },
    amber: { bg: '#fff7ed', border: '#fed7aa', color: '#c2410c' },
  };
  const selected = tones[tone] || tones.blue;
  return {
    appearance: 'none',
    border: `1px solid ${selected.border}`,
    background: selected.bg,
    color: selected.color,
    borderRadius: 999,
    padding: '8px 12px',
    fontSize: 12,
    fontWeight: 800,
    cursor: 'pointer',
    boxShadow: active ? 'inset 0 0 0 1px rgba(15,23,42,0.08)' : 'none',
    transform: active ? 'translateY(-1px)' : 'none',
  };
}

function analysisPillStyle(tone = 'slate') {
  const tones = {
    slate: { bg: '#f8fafc', border: '#cbd5e1', color: '#334155' },
    blue: { bg: '#eff6ff', border: '#bfdbfe', color: '#1d4ed8' },
    green: { bg: '#ecfdf5', border: '#bbf7d0', color: '#047857' },
    red: { bg: '#fef2f2', border: '#fecaca', color: '#dc2626' },
    amber: { bg: '#fff7ed', border: '#fed7aa', color: '#c2410c' },
  };
  const selected = tones[tone] || tones.slate;
  return {
    border: `1px solid ${selected.border}`,
    background: selected.bg,
    color: selected.color,
    borderRadius: 999,
    padding: '4px 8px',
    fontSize: 11,
    fontWeight: 850,
    whiteSpace: 'nowrap',
  };
}

function AnalysisMetric({ label, value, sub, tone = 'slate' }) {
  const colorMap = {
    green: '#047857',
    red: '#dc2626',
    amber: '#c2410c',
    blue: '#1d4ed8',
    slate: '#0f172a',
  };
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 10, color: '#64748b', fontWeight: 850, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ marginTop: 3, fontSize: 18, fontWeight: 900, color: colorMap[tone] || colorMap.slate, lineHeight: 1.1 }}>{value}</div>
      {sub ? <div style={{ marginTop: 3, fontSize: 11, color: '#64748b', lineHeight: 1.25 }}>{sub}</div> : null}
    </div>
  );
}

function MiniMetric({ label, value, sub, tone = 'slate' }) {
  const colorMap = {
    green: '#047857',
    red: '#b91c1c',
    amber: '#b45309',
    blue: '#1d4ed8',
    slate: '#111827',
  };
  return (
    <div style={{ background: '#f8f7f1', borderRadius: 8, padding: '14px 16px', minWidth: 130 }}>
      <div style={{ fontSize: 13, color: '#333', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 23, lineHeight: 1, fontWeight: 850, color: colorMap[tone] || colorMap.slate }}>{value}</div>
      {sub ? <div style={{ marginTop: 8, color: '#6b6b63', fontSize: 12, lineHeight: 1.25 }}>{sub}</div> : null}
    </div>
  );
}

function AnalysisBarList({ title, rows, maxValue, color = '#1fa37a', valueColor = '#1f2937', empty = 'No data yet.' }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: 13, fontWeight: 750, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#2f2f2a', marginBottom: 10 }}>{title}</div>
      <div style={{ display: 'grid', gap: 8 }}>
        {rows.length ? rows.map(([name, value]) => {
          const width = maxValue > 0 ? Math.max(10, Math.min(100, (Math.abs(Number(value || 0)) / maxValue) * 100)) : 0;
          return (
            <div key={name} style={{ display: 'grid', gridTemplateColumns: 'minmax(120px, 1fr) 74px 70px', gap: 10, alignItems: 'center', minWidth: 0 }}>
              <div style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13, color: '#222' }}>{name}</div>
              <div style={{ height: 12, borderRadius: 999, background: '#faf9f3', overflow: 'hidden' }}>
                <div style={{ width: `${width}%`, height: '100%', borderRadius: 999, background: color }} />
              </div>
              <div style={{ textAlign: 'right', fontSize: 12, color: valueColor, fontVariantNumeric: 'tabular-nums' }}>{fmt(value)}</div>
            </div>
          );
        }) : <div style={{ color: '#777', fontSize: 13 }}>{empty}</div>}
      </div>
    </div>
  );
}

function StatusTile({ label, value, pct, tone = 'slate' }) {
  const colors = {
    slate: '#111827',
    green: '#047857',
    red: '#b91c1c',
    blue: '#1d4ed8',
  };
  return (
    <div style={{ background: '#f8f7f1', borderRadius: 8, padding: '16px 18px', textAlign: 'center' }}>
      <div style={{ fontSize: 13, color: '#333' }}>{label}</div>
      <div style={{ marginTop: 8, fontSize: 20, fontWeight: 850, color: colors[tone] || colors.slate }}>{value}</div>
      <div style={{ marginTop: 5, fontSize: 12, color: '#686862' }}>{pct}</div>
    </div>
  );
}

function openTikTokVideoReceipt(orderId) {
  const cleanOrderId = extractTikTokOrderId(orderId);
  if (!cleanOrderId) return;
  if (navigator?.clipboard?.writeText) {
    navigator.clipboard.writeText(cleanOrderId).catch(() => {});
  }
  const params = new URLSearchParams({ order_no: cleanOrderId, shop_region: 'US' });
  window.open(`${TIKTOK_SELLER_ORDER_DETAIL_URL}?${params.toString()}`, '_blank', 'noopener,noreferrer');
}

function buildTikTokCustomerSeedOrder(row, sessionName) {
  const lotNo = String(row?.lotNo || '').trim();
  const orderId = extractTikTokOrderId(row?.orderId) || String(row?.orderId || '').trim();
  const orderedAt = String(row?.orderedAt || '').trim();
  const amount = Number(row?.salesPrice || 0) || 0;
  const cost = Number(row?.cost || 0) || 0;
  const buyerUsername = String(row?.buyerUsername || row?.buyer || '').trim();
  const displayName = String(row?.buyer || row?.recipientName || buyerUsername || '').trim();
  return {
    id: `tiktok-live-seed-${orderId || lotNo}`,
    order_number: orderId || `TikTok LIVE Lot ${lotNo}`,
    name: orderId || `TikTok LIVE Lot ${lotNo}`,
    session_name: sessionName || 'TikTok LIVE',
    whatnot_session_id_name: sessionName || 'TikTok LIVE',
    whatnot_buyer_username: buyerUsername,
    display_name: displayName,
    partner_id_name: displayName,
    order_source: 'tiktok_live',
    external_order_ref: orderId ? `tiktok_live:${orderId}:${lotNo}` : `tiktok_live:session:${lotNo}`,
    state: row?.statusFamily === 'cancelled' ? 'cancel' : 'sale',
    fulfillment_status: row?.statusFamily === 'confirmed' ? 'delivered' : 'pending',
    payment_status: row?.paymentStatus || 'paid',
    ordered_at: orderedAt,
    date_order: orderedAt,
    created_at: orderedAt,
    updated_at: orderedAt,
    total_amount: amount,
    amount_total: amount,
    subtotal: amount,
    lines: [{
      id: `tiktok-live-seed-line-${orderId || lotNo}`,
      product_name: row?.productName || 'TikTok LIVE item',
      product_id_name: row?.productName || 'TikTok LIVE item',
      name: row?.productName || 'TikTok LIVE item',
      barcode: row?.barcode || '',
      sku: row?.tiktokSellerSku || row?.sellerSku || row?.sku || row?.barcode || '',
      lot_number: lotNo,
      qty: 1,
      product_uom_qty: 1,
      unit_price: amount,
      price_unit: amount,
      subtotal: amount,
      price_subtotal: amount,
      unit_cost: cost,
      cost_price: cost,
      retail_price: Number(row?.retail || 0) || 0,
    }],
  };
}

function buildTikTokCustomerProfileSeed(rowsForCustomer, username, sessionName) {
  const seedRows = (rowsForCustomer || []).filter((row) => row?.hasLinkedOrder);
  return {
    seedCustomer: {
      name: username,
      display_name: username,
      whatnot_username: username,
      identities: [{ platform: 'tiktok_live', username, display_name: username }],
    },
    seedOrders: seedRows.map((row) => buildTikTokCustomerSeedOrder(row, sessionName)),
  };
}

export default function TikTokLiveSessionDetail({
  archivedLive,
  refreshToken = 0,
  view = 'products',
  providedInventory = null,
  providedOrders = null,
  externalLoading = false,
  initialSearch = '',
}) {
  const [sessionSnapshot, setSessionSnapshot] = useState(archivedLive || null);
  const [inventory, setInventory] = useState(Array.isArray(providedInventory) ? providedInventory : []);
  const [orders, setOrders] = useState(Array.isArray(providedOrders) ? providedOrders : []);
  const [loading, setLoading] = useState(false);
  const [customerPeek, setCustomerPeek] = useState(null);
  const [activeView, setActiveView] = useState(view || 'products');
  const [search, setSearch] = useState('');
  const [analyticsDetail, setAnalyticsDetail] = useState(null);
  const [commerceIntelligence, setCommerceIntelligence] = useState(null);
  const [sessionBenchmarks, setSessionBenchmarks] = useState([]);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [localRefreshToken, setLocalRefreshToken] = useState(0);
  const [editingProductLot, setEditingProductLot] = useState(null);
  const [replacementValue, setReplacementValue] = useState('');
  const [replacementBusy, setReplacementBusy] = useState(false);
  const dataRequestRef = useRef(0);

  useEffect(() => {
    setActiveView(view || 'products');
  }, [view]);

  useEffect(() => {
    // Order IDs only match in the orders view; pre-filling the lots/products
    // filter with one blanks the table out and looks like a load failure.
    if (initialSearch && activeView === 'orders') setSearch(String(initialSearch || ''));
  }, [initialSearch, activeView]);

  useEffect(() => {
    setSessionSnapshot((current) => {
      if (!archivedLive) return null;
      const nextSessionId = Number(archivedLive?.serverSessionId || 0);
      const currentSessionId = Number(current?.serverSessionId || 0);
      const nextHasRows = Array.isArray(archivedLive?.rows) && archivedLive.rows.length > 0;
      const currentHasRows = Array.isArray(current?.rows) && current.rows.length > 0;

      if (
        current
        && nextSessionId > 0
        && currentSessionId === nextSessionId
        && currentHasRows
        && !nextHasRows
      ) {
        return {
          ...current,
          ...archivedLive,
          rows: current.rows,
        };
      }

      return archivedLive;
    });
  }, [archivedLive]);

  useEffect(() => {
    if (Array.isArray(providedInventory) && providedInventory.length) setInventory(providedInventory);
  }, [providedInventory]);

  useEffect(() => {
    if (Array.isArray(providedOrders) && providedOrders.length) setOrders(providedOrders);
  }, [providedOrders]);

  useEffect(() => {
    let cancelled = false;
    const targetId = Number(archivedLive?.serverSessionId || sessionSnapshot?.serverSessionId || 0);
    if (!targetId) return () => {
      cancelled = true;
    };
    setAnalyticsLoading(true);
    Promise.all([
      fetchApi(`/api/tiktok_live_analytics/sessions/${encodeURIComponent(targetId)}`).catch(() => null),
      fetchApi('/api/tiktok_live_analytics/sessions?page_size=200').catch(() => null),
      fetchApi(`/api/live_commerce_intelligence/sessions/${encodeURIComponent(targetId)}`).catch(() => null),
    ])
      .then(([detail, sessionsData, intelligenceData]) => {
        if (cancelled) return;
        setAnalyticsDetail(detail?.ok ? detail : null);
        setSessionBenchmarks(Array.isArray(sessionsData?.rows) ? sessionsData.rows : []);
        setCommerceIntelligence(intelligenceData?.ok ? intelligenceData : null);
      })
      .finally(() => {
        if (!cancelled) setAnalyticsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [archivedLive?.serverSessionId, localRefreshToken, refreshToken, sessionSnapshot?.serverSessionId]);

  useEffect(() => {
    let cancelled = false;
    const targetId = Number(archivedLive?.serverSessionId || 0);
    if (!targetId) return () => {
      cancelled = true;
    };
    if (Array.isArray(archivedLive?.rows) && archivedLive.rows.length) return () => {
      cancelled = true;
    };
    fetchApi(`/api/tiktok_live_sessions/detail?session_id=${encodeURIComponent(targetId)}`)
      .then((data) => {
        if (cancelled) return;
        const fresh = data?.session || null;
        if (fresh) setSessionSnapshot(fresh);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [archivedLive?.serverSessionId, localRefreshToken, refreshToken]);

  useEffect(() => {
    const hasProvidedInventory = Array.isArray(providedInventory) && providedInventory.length > 0;
    const hasProvidedOrders = Array.isArray(providedOrders) && providedOrders.length > 0;
    if (hasProvidedInventory && hasProvidedOrders) return () => {};
    const targetSessionId = Number(archivedLive?.serverSessionId || sessionSnapshot?.serverSessionId || 0);
    // Refuse to fetch without a session id. Without it, /api/sale_orders returns
    // the most recent 5000 orders across all sessions, which never join to this
    // session's lots and render as "No live session rows yet."
    if (!hasProvidedOrders && !targetSessionId) return () => {};
    let cancelled = false;
    const orderParams = new URLSearchParams();
    orderParams.set('source', 'tiktok_live');
    orderParams.set('summary', '1');
    orderParams.set('limit', '5000');
    orderParams.set('session_id', String(targetSessionId));
    // Only show the loading state on a true cold start (no data yet).
    // Refetches keep showing stale rows so the table doesn't blank out.
    const hasExistingData = (inventory?.length || 0) > 0 || (orders?.length || 0) > 0;
    if (!hasExistingData) setLoading(true);
    const requestId = dataRequestRef.current + 1;
    dataRequestRef.current = requestId;
    Promise.all([
      hasProvidedInventory ? Promise.resolve({ rows: providedInventory }) : fetchApi('/api/inventory?active=all&status=all&compact=1'),
      hasProvidedOrders ? Promise.resolve({ rows: providedOrders }) : fetchApi(`/api/sale_orders?${orderParams}`),
    ])
      .then(([inventoryData, orderData]) => {
        if (cancelled || dataRequestRef.current !== requestId) return;
        const nextInventory = Array.isArray(inventoryData?.rows) ? inventoryData.rows : [];
        const nextOrders = Array.isArray(orderData?.rows) ? orderData.rows : [];
        if (nextInventory.length || !hasExistingData) setInventory(nextInventory);
        if (nextOrders.length || !hasExistingData) setOrders(nextOrders);
      })
      .catch(() => {
        // Preserve the last visible data during transient background refresh
        // failures. Emptying this state causes the session table to flicker
        // between real rows and "Loading..." on slow API responses.
      })
      .finally(() => {
        if (!cancelled && dataRequestRef.current === requestId) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [archivedLive?.serverSessionId, localRefreshToken, providedInventory, providedOrders, refreshToken, sessionSnapshot?.serverSessionId]);

  const inventoryMap = useMemo(() => {
    const map = new Map();
    (inventory || []).forEach((product) => {
      const barcode = normalizeBarcode(product.barcode);
      const sku = String(product.default_code || product.sku || '').trim().toLowerCase();
      if (barcode) map.set(barcode, product);
      if (sku) map.set(sku, product);
    });
    return map;
  }, [inventory]);

  const orderMap = useMemo(() => {
    const map = new Map();
    const currentSession = sessionSnapshot || archivedLive || {};
    const serverSessionId = Number(currentSession?.serverSessionId || 0);
    const importedRefs = getSessionOrderRefs(currentSession);
    if (!serverSessionId && !importedRefs.size && currentSession?.matchMode !== 'legacy_lot_numbers') return map;
    (orders || []).forEach((order) => {
      const externalRef = String(order?.external_order_ref || '').trim();
      if (serverSessionId && Number(order?.session_id || 0) !== serverSessionId) return;
      if (!serverSessionId && importedRefs.size && !importedRefs.has(externalRef)) return;
      const lot = extractLotNumber(order);
      if (!lot) return;
      const current = map.get(lot) || [];
      current.push(order);
      map.set(lot, current);
    });
    return map;
  }, [archivedLive, orders, sessionSnapshot]);

  const rows = useMemo(() => {
    const currentSession = sessionSnapshot || archivedLive || {};
    const liveRows = Array.isArray(currentSession?.rows) ? currentSession.rows : [];
    return liveRows.map((row) => {
      const lotNo = String(row?.lotNo || '').trim();
      const barcode = normalizeBarcode(row?.barcode);
      const product = inventoryMap.get(barcode) || null;
      const matchingOrders = orderMap.get(lotNo) || [];
      const primaryOrder = matchingOrders[0] || null;
      const linkedTiktokOrder = row?.tiktokOrder || null;
      const rowProductName = String(row?.productName || '').trim();
      const tiktokSellerSku = String(linkedTiktokOrder?.sellerSku || row?.tiktokSellerSku || row?.sellerSku || row?.sku || '').trim();
      const salesPrice = primaryOrder
        ? Number(primaryOrder?.total_amount || primaryOrder?.subtotal || 0)
        : Number(row?.salesPrice ?? linkedTiktokOrder?.salePrice ?? 0);
      const rowStatusFamily = String(row?.statusFamily || '').trim().toLowerCase();
      const rowHasOrderData = Boolean(row?.buyer || row?.buyerUsername || salesPrice > 0 || ['confirmed', 'pending'].includes(rowStatusFamily));
      const hasLinkedOrder = Boolean(primaryOrder || linkedTiktokOrder || rowHasOrderData);
      const cost = firstPositiveNumber(
        primaryOrder?.order_cost,
        primaryOrder?.linked_cost,
        row?.cost,
        product?.cost_price,
      ) ?? 0;
      const retail = Number(product?.retail_price ?? row?.retail ?? 0);
      const buyerUsername = String(primaryOrder?.whatnot_buyer_username || linkedTiktokOrder?.buyerUsername || row?.buyerUsername || '').trim();
      const buyerNickname = String(primaryOrder?.display_name || linkedTiktokOrder?.buyerName || linkedTiktokOrder?.buyerDisplay || row?.buyer || '').trim();
      const buyer = String(buyerUsername || buyerNickname || '').trim();
      const recipientName = String(linkedTiktokOrder?.recipientName || primaryOrder?.display_name || '').trim();
      const orderRef = String(
        primaryOrder?.external_order_ref
        || linkedTiktokOrder?.externalRef
        || linkedTiktokOrder?.orderId
        || primaryOrder?.order_number
        || '',
      ).trim();
      const orderId = extractTikTokOrderId(orderRef);
      const orderedAt = String(primaryOrder?.ordered_at || primaryOrder?.created_at || linkedTiktokOrder?.orderedAt || '').trim();
      const state = String(primaryOrder?.state || row?.statusFamily || '').trim();
      const paymentStatus = String(primaryOrder?.payment_status || linkedTiktokOrder?.status || '').trim();
      const fulfillmentStatus = String(primaryOrder?.fulfillment_status || '').trim();
      const statusFamily = primaryOrder
        ? (isDeliveredOrder(primaryOrder) ? 'confirmed' : primaryOrder.state === 'cancel' ? 'cancelled' : 'pending')
        : String(row?.statusFamily || (linkedTiktokOrder || rowHasOrderData ? 'pending' : 'cancelled')).trim();
      const statusLabel = primaryOrder
        ? (isDeliveredOrder(primaryOrder) ? 'Delivered' : primaryOrder.state === 'cancel' ? 'Cancelled' : 'Pending')
        : String(row?.statusLabel || (linkedTiktokOrder || rowHasOrderData ? 'Pending' : 'Cancelled / Missing CSV')).trim();
      const paidLikeStatus = `${paymentStatus} ${statusLabel} ${fulfillmentStatus}`.toLowerCase();
      const isFinancialFinal = hasLinkedOrder
        && statusFamily !== 'cancelled'
        && salesPrice > 0
        && (
          statusFamily === 'confirmed'
          || paidLikeStatus.includes('paid')
          || paidLikeStatus.includes('delivered')
          || paidLikeStatus.includes('confirmed')
        );
      const fees = hasLinkedOrder
        ? resolvePlatformFee(
          salesPrice,
          primaryOrder?.order_fees,
          primaryOrder?.linked_fees,
          row?.fees,
          linkedTiktokOrder?.fees,
        )
        : 0;
      const profit = primaryOrder
        ? salesPrice - cost - fees
        : Number(row?.profit ?? (hasLinkedOrder ? (salesPrice - cost - fees) : 0));
      return {
        lotNo,
        barcode,
        productName: rowProductName || product?.name || primaryOrder?.first_product_name || 'Unmatched inventory product',
        tiktokSellerSku,
        cost,
        retail,
        orderId,
        hasLinkedOrder,
        externalRef: primaryOrder?.external_order_ref || linkedTiktokOrder?.externalRef || linkedTiktokOrder?.orderId || '',
        buyer,
        buyerUsername,
        buyerNickname,
        recipientName,
        orderedAt,
        state,
        paymentStatus,
        fulfillmentStatus,
        salesPrice,
        fees,
        profit,
        isFinancialFinal,
        statusFamily,
        statusLabel,
      };
    });
  }, [archivedLive, inventoryMap, orderMap, sessionSnapshot]);

  const startLotProductEdit = (row) => {
    setEditingProductLot(String(row?.lotNo || '').trim());
    setReplacementValue(String(row?.barcode || row?.productName || '').trim());
  };

  const submitLotProductReplacement = async () => {
    const lotNo = String(editingProductLot || '').trim();
    const value = String(replacementValue || '').trim();
    const sessionId = Number(archivedLive?.serverSessionId || sessionSnapshot?.serverSessionId || 0);
    if (!lotNo || !value || !sessionId || replacementBusy) return;
    setReplacementBusy(true);
    try {
      const result = await fetchApi('/api/tiktok_live_sessions/replace_lot_product', {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          lot_number: lotNo,
          query: value,
        }),
      });
      if (!result?.ok) throw new Error(result?.error || 'Product replacement failed');
      if (result?.product) {
        setSessionSnapshot((current) => {
          if (!current || !Array.isArray(current.rows)) return current;
          return {
            ...current,
            rows: current.rows.map((row) => (
              String(row?.lotNo || '').trim() === lotNo
                ? {
                  ...row,
                  barcode: result.product.barcode || row.barcode,
                  productName: result.product.name || row.productName,
                  cost: result.product.cost_price ?? row.cost,
                  retail: result.product.retail_price ?? row.retail,
                }
                : row
            )),
          };
        });
        setInventory((current) => {
          const next = Array.isArray(current) ? [...current] : [];
          const idx = next.findIndex((item) => Number(item?.id || 0) === Number(result.product.id || 0));
          if (idx >= 0) next[idx] = { ...next[idx], ...result.product };
          return next;
        });
      }
      setEditingProductLot(null);
      setReplacementValue('');
      setLocalRefreshToken((value) => value + 1);
    } catch (error) {
      window.alert(error?.message || 'Product replacement failed');
    } finally {
      setReplacementBusy(false);
    }
  };

  const summary = useMemo(() => ({
    totalLots: rows.length,
    matchedLots: rows.filter((row) => row.hasLinkedOrder).length,
    confirmedLots: rows.filter((row) => row.statusFamily === 'confirmed').length,
    pendingLots: rows.filter((row) => row.statusFamily === 'pending').length,
    cancelledLots: rows.filter((row) => !row.hasLinkedOrder || row.statusFamily === 'cancelled').length,
    revenue: rows.filter((row) => row.isFinancialFinal).reduce((sum, row) => sum + Number(row.salesPrice || 0), 0),
    costOfGoods: rows.filter((row) => row.isFinancialFinal).reduce((sum, row) => sum + Number(row.cost || 0), 0),
    fees: rows.filter((row) => row.isFinancialFinal).reduce((sum, row) => sum + Number(row.fees || 0), 0),
    profit: rows.filter((row) => row.isFinancialFinal).reduce((sum, row) => sum + Number(row.profit || 0), 0),
  }), [rows]);

  const analysis = useMemo(() => {
    const matchedRows = rows.filter((row) => row.hasLinkedOrder);
    const confirmedRows = matchedRows.filter((row) => row.statusFamily === 'confirmed');
    const financialRows = matchedRows.filter((row) => row.isFinancialFinal);
    const cancelledRows = rows.filter((row) => !row.hasLinkedOrder || row.statusFamily === 'cancelled');
    const pendingRows = matchedRows.filter((row) => row.statusFamily === 'pending');
    const negativeRows = financialRows.filter((row) => Number(row.profit || 0) < 0);
    const currentSessionId = Number(archivedLive?.serverSessionId || sessionSnapshot?.serverSessionId || 0);
    const historicalRows = (sessionBenchmarks || []).filter((item) => Number(item.session_id || 0) !== currentSessionId);
    const previousSessions = historicalRows.length || 0;
    const averageOf = (key) => {
      if (!historicalRows.length) return 0;
      return historicalRows.reduce((sum, item) => sum + Number(item?.[key] || 0), 0) / historicalRows.length;
    };
    const benchmark = {
      revenue: averageOf('revenue'),
      profit: averageOf('profit'),
      orders: averageOf('orders'),
      customers: averageOf('unique_buyers'),
      avgOrder: averageOf('avg_order_value'),
      cancelRate: averageOf('cancel_rate'),
      margin: averageOf('margin_pct'),
    };
    const financialCount = financialRows.length;
    const avgOrder = summary.revenue / Math.max(1, financialCount);
    const marginPct = summary.revenue > 0 ? (summary.profit / summary.revenue) * 100 : 0;
    const cancelRate = rows.length ? (cancelledRows.length / rows.length) * 100 : 0;
    const pendingRate = rows.length ? (pendingRows.length / rows.length) * 100 : 0;
    const customerRevenue = new Map();
    const customerProfit = new Map();
    const productRevenue = new Map();
    const productProfit = new Map();
    const productUnits = new Map();
    const productPrices = new Map();
    let deliveredCount = 0;
    let confirmedOnlyCount = 0;
    financialRows.forEach((row) => {
      const customerKey = String(row.buyer || 'Unknown customer').trim() || 'Unknown customer';
      const productKey = String(row.productName || 'Unknown product').trim() || 'Unknown product';
      customerRevenue.set(customerKey, (customerRevenue.get(customerKey) || 0) + Number(row.salesPrice || 0));
      customerProfit.set(customerKey, (customerProfit.get(customerKey) || 0) + Number(row.profit || 0));
      productRevenue.set(productKey, (productRevenue.get(productKey) || 0) + Number(row.salesPrice || 0));
      productProfit.set(productKey, (productProfit.get(productKey) || 0) + Number(row.profit || 0));
      productUnits.set(productKey, (productUnits.get(productKey) || 0) + 1);
      const prices = productPrices.get(productKey) || [];
      if (Number(row.salesPrice || 0) > 0) prices.push(Number(row.salesPrice || 0));
      productPrices.set(productKey, prices);
      const statusText = `${row.statusLabel || ''} ${row.fulfillmentStatus || ''}`.toLowerCase();
      if (statusText.includes('delivered')) deliveredCount += 1;
      else confirmedOnlyCount += 1;
    });
    const topCustomers = [...customerRevenue.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    const topCustomersByProfit = [...customerProfit.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    const bestProducts = [...productRevenue.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    const topProductsByProfit = [...productProfit.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    const worstProducts = [...productProfit.entries()].filter(([, value]) => Number(value || 0) < 0).sort((a, b) => a[1] - b[1]).slice(0, 5);
    const topCustomerShare = topCustomers[0] && summary.revenue > 0 ? (topCustomers[0][1] / summary.revenue) * 100 : 0;
    const velocity = matchedRows.length / Math.max(1, rows.length);
    const revenueDelta = comparePct(summary.revenue, benchmark.revenue);
    const profitDelta = comparePct(summary.profit, benchmark.profit);
    const orderDelta = comparePct(matchedRows.length, benchmark.orders);
    const avgOrderDelta = comparePct(avgOrder, benchmark.avgOrder);
    const cancelDelta = comparePct(cancelRate, benchmark.cancelRate);
    const marginDelta = comparePct(marginPct, benchmark.margin);
    const revenueRank = [...sessionBenchmarks]
      .sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0))
      .findIndex((item) => Number(item.session_id || 0) === currentSessionId) + 1;
    const profitRank = [...sessionBenchmarks]
      .sort((a, b) => Number(b.profit || 0) - Number(a.profit || 0))
      .findIndex((item) => Number(item.session_id || 0) === currentSessionId) + 1;
    const insights = [];
    if (revenueDelta != null) {
      insights.push(`${revenueDelta >= 0 ? 'Revenue is ahead' : 'Revenue is behind'} previous-session average by ${signedPct(revenueDelta)}.`);
    }
    if (profitDelta != null) {
      insights.push(`${profitDelta >= 0 ? 'Profit is stronger' : 'Profit is weaker'} than history by ${signedPct(profitDelta)}.`);
    }
    if (cancelDelta != null && cancelDelta > 20) insights.push(`Cancellation risk is elevated: ${cancelRate.toFixed(1)}% now vs ${benchmark.cancelRate.toFixed(1)}% historical average.`);
    if (topCustomerShare >= 18) insights.push(`Customer concentration is high: top buyer controls ${topCustomerShare.toFixed(1)}% of revenue.`);
    if (negativeRows.length) insights.push(`${negativeRows.length} lot${negativeRows.length === 1 ? '' : 's'} sold below profit after cost and fee.`);
    if (pendingRows.length) insights.push(`${pendingRows.length} order${pendingRows.length === 1 ? '' : 's'} still pending; check payment/fulfillment before finalizing profit.`);
    if (!insights.length) insights.push('No major leakage signal found in the loaded session data.');
    return {
      previousSessions,
      benchmark,
      avgOrder,
      marginPct,
      cancelRate,
      pendingRate,
      negativeRows,
      topCustomers,
      topCustomersByProfit,
      bestProducts,
      topProductsByProfit,
      worstProducts,
      deliveredCount,
      confirmedOnlyCount,
      topCustomerShare,
      velocity,
      revenueDelta,
      profitDelta,
      orderDelta,
      avgOrderDelta,
      cancelDelta,
      marginDelta,
      revenueRank,
      profitRank,
      totalRankedSessions: sessionBenchmarks.length,
      insights,
      revenueSignal: pickSignal(revenueDelta, true),
      profitSignal: pickSignal(profitDelta, true),
      orderSignal: pickSignal(orderDelta, true),
      cancelSignal: pickSignal(cancelDelta, false),
      productPrices,
      productUnits,
    };
  }, [archivedLive?.serverSessionId, rows, sessionBenchmarks, sessionSnapshot?.serverSessionId, summary.profit, summary.revenue]);

  const visibleRows = useMemo(() => {
    if (activeView === 'orders') return rows.filter((row) => row.hasLinkedOrder);
    if (activeView === 'cancelled') return rows.filter((row) => !row.hasLinkedOrder || row.statusFamily === 'cancelled');
    if (activeView === 'analysis') return rows;
    return rows;
  }, [rows, activeView]);

  const customerGroups = useMemo(() => {
    const groups = new Map();
    rows
      .filter((row) => row.hasLinkedOrder && row.buyer)
      .forEach((row) => {
        const key = String(row.buyer || '').trim().toLowerCase();
        const current = groups.get(key) || {
          buyer: row.buyer,
          buyerUsername: row.buyerUsername || row.buyer,
          count: 0,
          revenue: 0,
          profit: 0,
          rows: [],
        };
        current.count += 1;
        current.revenue += row.isFinancialFinal ? Number(row.salesPrice || 0) : 0;
        current.profit += row.isFinancialFinal ? Number(row.profit || 0) : 0;
        current.rows.push(row);
        if (!current.buyerUsername && row.buyerUsername) current.buyerUsername = row.buyerUsername;
        groups.set(key, current);
      });
    return [...groups.values()].sort((left, right) => right.count - left.count || right.revenue - left.revenue);
  }, [rows]);

  const normalizedSearch = String(search || '').trim().toLowerCase();

  const filteredRows = useMemo(() => {
    if (!normalizedSearch) return visibleRows;
    const lotSearchTokens = [...new Set(normalizedSearch.split(/[\s,]+/).map((token) => token.trim()).filter(Boolean))];
    const exactLotSearch = lotSearchTokens.length > 0 && lotSearchTokens.every((token) => /^\d+$/.test(token));
    if (exactLotSearch) {
      const wantedLots = new Set(lotSearchTokens.map((token) => String(Number(token))));
      return visibleRows.filter((row) => wantedLots.has(String(Number(row.lotNo || 0))));
    }
    return visibleRows.filter((row) => (
      String(row.lotNo || '').toLowerCase().includes(normalizedSearch)
      || String(row.barcode || '').toLowerCase().includes(normalizedSearch)
      || String(row.productName || '').toLowerCase().includes(normalizedSearch)
      || String(row.buyer || '').toLowerCase().includes(normalizedSearch)
      || String(row.orderId || '').toLowerCase().includes(normalizedSearch)
    ));
  }, [normalizedSearch, visibleRows]);

  const filteredCustomerGroups = useMemo(() => {
    if (!normalizedSearch) return customerGroups;
    return customerGroups.filter((group) => (
      String(group.buyer || '').toLowerCase().includes(normalizedSearch)
      || group.rows.some((row) => (
        String(row.lotNo || '').toLowerCase().includes(normalizedSearch)
        || String(row.productName || '').toLowerCase().includes(normalizedSearch)
        || String(row.orderId || '').toLowerCase().includes(normalizedSearch)
      ))
    ));
  }, [customerGroups, normalizedSearch]);

  const footerLabel = useMemo(() => {
    if (activeView === 'customers') return `${filteredCustomerGroups.length} customer${filteredCustomerGroups.length !== 1 ? 's' : ''} in this live session`;
    if (activeView === 'analysis') return `${analysis.insights.length} insight${analysis.insights.length !== 1 ? 's' : ''} for this live session`;
    if (activeView === 'orders') return `${filteredRows.length} matched order row${filteredRows.length !== 1 ? 's' : ''} in this live session`;
    if (activeView === 'cancelled') return `${filteredRows.length} cancelled / missing lot${filteredRows.length !== 1 ? 's' : ''} in this live session`;
    return `${filteredRows.length} lot row${filteredRows.length !== 1 ? 's' : ''} in this live session`;
  }, [activeView, analysis.insights.length, filteredCustomerGroups.length, filteredRows.length]);

  const emptyMessage = activeView === 'customers'
    ? 'No customers found for this live session yet.'
    : activeView === 'cancelled'
      ? 'No cancelled or missing lots in this live session.'
      : activeView === 'orders'
        ? 'No matched order rows in this live session yet.'
      : 'No live session rows yet.';
  const hasVisibleSessionData = (
    visibleRows.length > 0
    || customerGroups.length > 0
    || analysis.insights.length > 0
  );
  const detailLoading = (loading || externalLoading) && !hasVisibleSessionData;

  return (
    <>
      <section
        className="company-panel"
        style={{
          overflow: 'hidden',
          borderColor: '#dbe3ec',
          background: '#ffffff',
          boxShadow: '0 14px 34px rgba(15,23,42,0.06)',
        }}
      >
        <div
          className="company-panel-head"
          style={{
            background: '#ffffff',
            borderBottom: '1px solid #e2e8f0',
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start', width: '100%', flexWrap: 'wrap' }}>
            <div style={{ display: 'grid', gap: 5, minWidth: 0 }}>
              <div style={{ fontSize: 11, color: '#64748b', fontWeight: 850, letterSpacing: '0.11em', textTransform: 'uppercase' }}>
                TikTok live session
              </div>
              <div style={{ fontSize: 20, fontWeight: 900, letterSpacing: '-0.03em', color: '#0f172a', lineHeight: 1.15 }}>
                {archivedLive?.displayName || archivedLive?.liveName || 'TikTok LIVE Session'}
              </div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Confirmed TikTok Live orders deduct inventory automatically. 6% TikTok platform fee included in profit.
              </div>
            </div>
          </div>
        </div>
        <div className="company-panel-body" style={{ display: 'grid', gap: 14, padding: 0 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, padding: '14px 14px 0' }}>
            {[
              ['Lots', summary.totalLots, '#1d4ed8'],
              ['Matched', summary.matchedLots, '#047857'],
              ['Missing', summary.cancelledLots, '#dc2626'],
              ['Customers', customerGroups.length, '#c2410c'],
              ['Revenue', fmt(summary.revenue), '#0f172a'],
              ['COGS', fmt(summary.costOfGoods), '#7c2d12'],
              ['Fees 6%', fmt(summary.fees), '#64748b'],
              ['Profit', fmt(summary.profit), profitColor(summary.profit)],
            ].map(([label, value, color]) => (
              <div key={label} style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: '10px 12px', background: '#f8fafc', minWidth: 0 }}>
                <div style={{ fontSize: 10, fontWeight: 850, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#64748b' }}>{label}</div>
                <div style={{ marginTop: 4, fontSize: 17, fontWeight: 900, color, lineHeight: 1.1 }}>{value}</div>
              </div>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: '0 14px' }}>
            <button type="button" onClick={() => setActiveView('products')} style={detailToggleStyle(activeView === 'products', 'blue')}>
              Lots
            </button>
            <button type="button" onClick={() => setActiveView('orders')} style={detailToggleStyle(activeView === 'orders', 'green')}>
              Orders
            </button>
            <button type="button" onClick={() => setActiveView('cancelled')} style={detailToggleStyle(activeView === 'cancelled', 'red')}>
              Missing
            </button>
            <button type="button" onClick={() => setActiveView('customers')} style={detailToggleStyle(activeView === 'customers', 'amber')}>
              Customers
            </button>
            <button type="button" onClick={() => setActiveView('analysis')} style={detailToggleStyle(activeView === 'analysis', 'slate')}>
              Analysis
            </button>
            {summary.pendingLots ? (
              <Badge custom={{ label: `${summary.pendingLots} pending`, bg: 'rgba(59,130,246,0.14)', color: '#2563eb' }} />
            ) : null}
            {summary.confirmedLots ? (
              <Badge custom={{ label: `${summary.confirmedLots} confirmed`, bg: 'rgba(16,185,129,0.14)', color: '#059669' }} />
            ) : null}
          </div>

          <FilterBar style={{ padding: '0 14px' }}>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder={activeView === 'customers' ? 'Search customer, lot, product, order…' : 'Search lot no, barcode, buyer, product…'}
            />
            {search ? (
              <button type="button" onClick={() => setSearch('')} style={detailToggleStyle(false, 'slate')}>
                Clear Search
              </button>
            ) : null}
          </FilterBar>

          {activeView === 'analysis' ? (
            <div style={{ display: 'grid', gap: 22, padding: '0 24px 24px', background: '#fff' }}>
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 11, color: '#6b7280', fontWeight: 850, letterSpacing: '0.1em', textTransform: 'uppercase' }}>Data recognized for this session</div>
                    <div style={{ marginTop: 4, fontSize: 15, color: '#333' }}>
                      {commerceIntelligence?.data_catalog?.length
                        ? `${commerceIntelligence.data_catalog.length} intelligence source groups: sessions, lots, orders, products, customers, and returns.`
                        : 'Lots, buyers, products, barcodes, delivered/cancelled status, sale price, cost, 6% TikTok fees, profit/loss, and previous-session benchmarks.'}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <span style={analysisPillStyle(analysis.revenueSignal.tone)}>{analysis.revenueSignal.label}</span>
                    <span style={analysisPillStyle(analysis.profitSignal.tone)}>{analysis.profitSignal.label}</span>
                    <span style={analysisPillStyle(analysis.cancelSignal.tone)}>Cancel {analysis.cancelSignal.label}</span>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(135px, 1fr))', gap: 12 }}>
                  <MiniMetric label="Total lots" value={summary.totalLots.toLocaleString()} sub={`${summary.cancelledLots.toLocaleString()} cancelled`} />
                  <MiniMetric label="Active sales" value={summary.confirmedLots.toLocaleString()} sub="confirmed + delivered" />
                  <MiniMetric label="Total revenue" value={fmt(summary.revenue)} sub="active lots only" />
                  <MiniMetric label="Net profit" value={fmt(summary.profit)} sub={`${analysis.marginPct.toFixed(0)}% margin`} tone={summary.profit >= 0 ? 'green' : 'red'} />
                  <MiniMetric label="Avg sale price" value={fmt(analysis.avgOrder)} sub="per active lot" />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 0.9fr) minmax(360px, 1fr)', gap: 34, alignItems: 'start' }}>
                <div style={{ display: 'grid', gap: 22, minWidth: 0 }}>
                  <AnalysisBarList
                    title="Top products by profit"
                    rows={analysis.topProductsByProfit}
                    maxValue={Math.max(0, ...analysis.topProductsByProfit.map(([, value]) => Math.abs(Number(value || 0))))}
                    color="#1fa37a"
                    valueColor="#1f2937"
                    empty="No profitable product data yet."
                  />
                  <AnalysisBarList
                    title="Loss-making products"
                    rows={analysis.worstProducts}
                    maxValue={Math.max(0, ...analysis.worstProducts.map(([, value]) => Math.abs(Number(value || 0))))}
                    color="#ef4444"
                    valueColor="#b91c1c"
                    empty="No loss-making products found."
                  />
                </div>

                <div style={{ display: 'grid', gap: 22, minWidth: 0 }}>
                  <AnalysisBarList
                    title="Top buyers by profit generated"
                    rows={analysis.topCustomersByProfit}
                    maxValue={Math.max(0, ...analysis.topCustomersByProfit.map(([, value]) => Math.abs(Number(value || 0))))}
                    color="#7c6ee6"
                    valueColor="#1f2937"
                    empty="No buyer profit data yet."
                  />

                  <div style={{ display: 'grid', gap: 12 }}>
                    <div style={{ fontSize: 13, fontWeight: 750, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#2f2f2a' }}>Order status breakdown</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(110px, 1fr))', gap: 10 }}>
                      <StatusTile
                        label="Delivered"
                        value={analysis.deliveredCount.toLocaleString()}
                        pct={`${summary.totalLots ? ((analysis.deliveredCount / summary.totalLots) * 100).toFixed(1) : '0.0'}%`}
                        tone="slate"
                      />
                      <StatusTile
                        label="Confirmed"
                        value={analysis.confirmedOnlyCount.toLocaleString()}
                        pct={`${summary.totalLots ? ((analysis.confirmedOnlyCount / summary.totalLots) * 100).toFixed(1) : '0.0'}%`}
                        tone="slate"
                      />
                      <StatusTile
                        label="Cancelled"
                        value={summary.cancelledLots.toLocaleString()}
                        pct={`${summary.totalLots ? ((summary.cancelledLots / summary.totalLots) * 100).toFixed(1) : '0.0'}%`}
                        tone="red"
                      />
                    </div>
                  </div>

                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 13, fontWeight: 750, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#2f2f2a' }}>Financial summary</div>
                    {[
                      ['Gross revenue', fmt(summary.revenue), '#1f2937'],
                      ['Cost of goods', `-${fmt(summary.costOfGoods)}`, '#1f2937'],
                      ['Platform fees (6%)', `-${fmt(summary.fees)}`, '#1f2937'],
                      ['Net profit', fmt(summary.profit), profitColor(summary.profit)],
                    ].map(([label, value, color]) => (
                      <div key={label} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 20, borderBottom: '1px solid #dedbd2', padding: '4px 0', fontSize: 13 }}>
                        <div style={{ fontWeight: label === 'Net profit' ? 750 : 450, color: '#333' }}>{label}</div>
                        <div style={{ color, fontWeight: label === 'Net profit' ? 850 : 500, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gap: 8 }}>
                <div style={{ fontSize: 17, fontWeight: 650, color: '#111' }}>Key takeaways from this session</div>
                {(commerceIntelligence?.live_operator_signals?.actions?.length ? commerceIntelligence.live_operator_signals.actions : analysis.insights).map((item) => (
                  <div key={item} style={{ color: '#333', fontSize: 14, lineHeight: 1.4 }}>
                    {item}
                  </div>
                ))}
                {commerceIntelligence?.live_operator_signals?.status ? (
                  <div style={{ color: '#666', fontSize: 13 }}>
                    Intelligence status: {commerceIntelligence.live_operator_signals.status}.
                  </div>
                ) : null}
                {analysis.previousSessions ? (
                  <div style={{ color: '#666', fontSize: 13 }}>
                    Comparison baseline: {analysis.previousSessions} earlier session{analysis.previousSessions === 1 ? '' : 's'}.
                    Revenue rank {analysis.revenueRank ? `#${analysis.revenueRank}` : 'not ranked'} and profit rank {analysis.profitRank ? `#${analysis.profitRank}` : 'not ranked'} of {analysis.totalRankedSessions || 0}.
                  </div>
                ) : null}
              </div>
            </div>
          ) : activeView === 'customers' ? (
            <TableShell footer={footerLabel}>
              <Thead cols={[
                { label: 'Customer' },
                { label: 'Lots' },
                { label: 'Orders', align: 'right' },
                { label: 'Revenue', align: 'right' },
                { label: 'Profit / Loss', align: 'right' },
              ]} />
              <tbody>
                {filteredCustomerGroups.length === 0 && <EmptyRow cols={5} loading={detailLoading} msg={detailLoading ? 'Loading this session...' : emptyMessage} />}
                {filteredCustomerGroups.map((group) => (
                  <tr key={group.buyer} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 800 }}>
                      <CustomerLink
                        username={group.buyerUsername || group.buyer}
                        label={`@${group.buyer}`}
                        onOpen={setCustomerPeek}
                        profileSeed={buildTikTokCustomerProfileSeed(
                          group.rows,
                          group.buyerUsername || group.buyer,
                          archivedLive?.displayName || archivedLive?.liveName || sessionSnapshot?.displayName || sessionSnapshot?.liveName,
                        )}
                      />
                    </td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {group.rows.map((row) => (
                          <button
                            key={`${group.buyer}-${row.lotNo}`}
                            type="button"
                            onClick={() => {
                              setActiveView('products');
                              setSearch(String(row.lotNo || ''));
                            }}
                            style={detailToggleStyle(false, 'slate')}
                          >
                            Lot #{row.lotNo}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 800 }}>{group.count}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 800 }}>{fmt(group.revenue)}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 800, color: profitColor(group.profit) }}>{fmt(group.profit)}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          ) : (
            <TableShell footer={footerLabel}>
              <Thead cols={[
                { label: 'Lot No' },
                { label: 'Barcode' },
                { label: 'Product Name' },
                { label: 'Our Cost', align: 'right' },
                { label: 'Retail', align: 'right' },
                { label: 'Buyer' },
                { label: 'Sales Price', align: 'right' },
                { label: 'Fee', align: 'right' },
                { label: 'Profit / Loss', align: 'right' },
                { label: 'Status' },
              ]} />
              <tbody>
                {filteredRows.length === 0 && <EmptyRow cols={10} loading={detailLoading} msg={detailLoading ? 'Loading this session...' : emptyMessage} />}
                {filteredRows.map((row) => (
                  <tr key={`${row.lotNo}-${row.barcode}`} style={{ borderTop: '1px solid #eef2f7', background: row.hasLinkedOrder ? '#fff' : '#fff7f7' }}>
                    <td style={{ padding: '8px 14px', fontWeight: 900 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        {row.lotNo ? (
                          <button
                            type="button"
                            onClick={() => setSearch(String(row.lotNo || ''))}
                            style={{ border: 'none', background: 'transparent', padding: 0, font: 'inherit', fontWeight: 900, color: 'var(--text-primary)', cursor: 'pointer' }}
                          >
                            {row.lotNo}
                          </button>
                        ) : '—'}
                        {row.orderId ? (
                          <button
                            type="button"
                            title="Copies the TikTok order ID and opens Seller Center. TikTok does not expose video receipts as downloadable API files."
                            onClick={() => openTikTokVideoReceipt(row.orderId)}
                            style={{
                              border: '1px solid #fed7aa',
                              background: '#fff7ed',
                              color: '#c2410c',
                              borderRadius: 999,
                              padding: '4px 7px',
                              fontSize: 10.5,
                              fontWeight: 850,
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            Video
                          </button>
                        ) : null}
                      </div>
                    </td>
                    <td style={{ padding: '8px 14px', minWidth: 170 }}>
                      {editingProductLot === String(row.lotNo || '').trim() ? (
                        <input
                          autoFocus
                          value={replacementValue}
                          disabled={replacementBusy}
                          placeholder="Barcode or product name"
                          onChange={(event) => setReplacementValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') submitLotProductReplacement();
                            if (event.key === 'Escape') {
                              setEditingProductLot(null);
                              setReplacementValue('');
                            }
                          }}
                          onBlur={() => {
                            if (!replacementBusy) {
                              setEditingProductLot(null);
                              setReplacementValue('');
                            }
                          }}
                          style={{
                            width: '100%',
                            minWidth: 170,
                            border: '1px solid #c7d2fe',
                            borderRadius: 8,
                            padding: '7px 9px',
                            fontFamily: 'var(--font-mono)',
                            fontSize: 12,
                            outline: 'none',
                            boxShadow: '0 0 0 3px rgba(99,102,241,0.12)',
                          }}
                        />
                      ) : (
                        <button
                          type="button"
                          title="Click to replace this lot product by barcode or product name"
                          onClick={() => startLotProductEdit(row)}
                          style={{
                            border: '1px solid transparent',
                            background: 'transparent',
                            borderRadius: 8,
                            padding: '5px 6px',
                            fontFamily: 'var(--font-mono)',
                            color: 'var(--text-secondary)',
                            cursor: 'text',
                            textAlign: 'left',
                          }}
                        >
                          {row.barcode || '—'}
                        </button>
                      )}
                    </td>
                    <td title={row.productName} style={{ padding: '8px 14px', fontWeight: 700, minWidth: 260 }}>{compactLiveProductName(row.productName)}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmt(row.cost)}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmt(row.retail)}</td>
                    <td style={{ padding: '8px 14px' }}>
                      {row.buyer ? (
                        row.buyerUsername ? (
                          <CustomerLink
                            username={row.buyerUsername}
                            label={`@${row.buyerUsername}`}
                            onOpen={setCustomerPeek}
                            profileSeed={buildTikTokCustomerProfileSeed(
                              rows.filter((candidate) => {
                                const left = String(candidate.buyerUsername || candidate.buyer || '').trim().toLowerCase();
                                const right = String(row.buyerUsername || row.buyer || '').trim().toLowerCase();
                                return left && left === right;
                              }),
                              row.buyerUsername || row.buyer,
                              archivedLive?.displayName || archivedLive?.liveName || sessionSnapshot?.displayName || sessionSnapshot?.liveName,
                            )}
                          />
                        ) : (
                          <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{row.buyer}</span>
                        )
                      ) : '—'}
                      {row.buyerNickname && row.buyerNickname !== row.buyerUsername ? (
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>Nickname: {row.buyerNickname}</div>
                      ) : null}
                      {row.orderedAt ? <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{fmtDt(row.orderedAt)}</div> : null}
                      {row.orderId ? (
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>Order ID: {row.orderId}</div>
                      ) : null}
                      {row.tiktokSellerSku ? (
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>SKU ID: {row.tiktokSellerSku}</div>
                      ) : null}
                      {row.recipientName && row.recipientName !== row.buyer ? (
                        <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>Ship: {row.recipientName}</div>
                      ) : null}
                    </td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 800 }}>{row.isFinancialFinal ? fmt(row.salesPrice) : '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: '#64748b' }}>{row.isFinancialFinal ? fmt(row.fees) : '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 800, color: row.isFinancialFinal ? profitColor(row.profit) : '#64748b' }}>{row.isFinancialFinal ? fmt(row.profit) : '—'}</td>
                    <td style={{ padding: '8px 14px' }}>
                      <Badge custom={row.hasLinkedOrder
                        ? row.statusFamily === 'pending'
                          ? { label: `${row.statusLabel} · ${row.paymentStatus || row.state || 'pending'}`, bg: 'rgba(59,130,246,0.14)', color: '#2563eb' }
                          : row.statusFamily === 'confirmed'
                            ? { label: `${row.statusLabel} · ${row.paymentStatus || row.state || 'paid'}`, bg: 'rgba(16,185,129,0.16)', color: '#059669' }
                            : { label: `${row.statusLabel} · ${row.paymentStatus || row.state || 'cancelled'}`, bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }
                        : { label: row.statusLabel, bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          )}
        </div>
      </section>
      {customerPeek ? (
        <CustomerProfileDrawer
          customerId={customerPeek.customerId}
          username={customerPeek.username}
          seedOrders={customerPeek.seedOrders}
          seedCustomer={customerPeek.seedCustomer}
          onClose={() => setCustomerPeek(null)}
        />
      ) : null}
    </>
  );
}
