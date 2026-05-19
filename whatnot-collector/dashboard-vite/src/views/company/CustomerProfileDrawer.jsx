import { useEffect, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  EmptyRow,
  KpiCard,
  SlidePanel,
  TableShell,
  Thead,
  fmt,
  fmtDate,
  fmtDt,
  clrProfit,
} from './utils';

const sectionTitleStyle = {
  fontWeight: 800,
  fontSize: 15,
  letterSpacing: '-0.01em',
};

const softPanelStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 18,
  background: 'var(--bg-panel)',
  overflow: 'hidden',
};

const linkButtonStyle = {
  background: 'none',
  border: 'none',
  padding: 0,
  margin: 0,
  color: 'var(--accent-blue)',
  fontWeight: 700,
  cursor: 'pointer',
  textAlign: 'left',
};

export function CustomerLink({ username, customerId, label, onOpen, style, profileSeed }) {
  const uname = String(username || '').trim().replace(/^@/, '');
  const hasTarget = customerId || uname;
  if (!hasTarget) {
    return <span style={style}>{label || '—'}</span>;
  }
  return (
    <button
      type="button"
      style={{ ...linkButtonStyle, ...style }}
      onClick={(event) => {
        event.stopPropagation();
        onOpen?.({ customerId: customerId || null, username: uname || null, ...(profileSeed || {}) });
      }}
    >
      {label || (uname ? `@${uname}` : 'Open')}
    </button>
  );
}

function ActivityBadge({ role }) {
  const map = {
    chat: { label: 'Chat', bg: 'rgba(96,165,250,0.16)', color: '#60a5fa' },
    bidder: { label: 'Bid', bg: 'rgba(245,158,11,0.16)', color: '#d97706' },
    winner: { label: 'Win', bg: 'rgba(34,197,94,0.16)', color: '#22c55e' },
  };
  const badge = map[role] || { label: role || 'Event', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' };
  return (
    <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 999, background: badge.bg, color: badge.color }}>
      {badge.label}
    </span>
  );
}

function parseTikTokNotes(notes) {
  const text = String(notes || '');
  const parts = text.split('|').map((part) => part.trim()).filter(Boolean);
  const parsed = {};
  parsed.__segments = parts;
  parts.forEach((part) => {
    const idx = part.indexOf(':');
    if (idx === -1) return;
    const key = part.slice(0, idx).trim().toLowerCase();
    const value = part.slice(idx + 1).trim();
    parsed[key] = value;
  });
  return parsed;
}

function extractLotFromExternalRef(ref) {
  const value = String(ref || '').trim();
  const colonMatch = value.match(/^tiktok_(?:live|shop):[^:]+:([^:]+)$/i);
  if (colonMatch?.[1]) return colonMatch[1].trim();
  const suffixMatch = value.match(/-LOT-([^-]+)$/i);
  if (suffixMatch?.[1]) return suffixMatch[1].trim();
  return '';
}

function normalizeBarcode(value) {
  const raw = String(value || '').trim();
  if (raw === '3220360598918') return '6290360598918';
  return raw;
}

function parseShippingInfo(raw) {
  const text = String(raw || '').trim();
  if (!text) return {};
  const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  return {
    recipient: lines[0] || '',
    phone: lines[1] || '',
    cityState: lines[2] || '',
    zipcode: lines[3] || '',
    country: lines[4] || '',
  };
}

function splitCityState(value) {
  const parts = String(value || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  return {
    city: parts[0] || '',
    state: parts[1] || '',
  };
}

function extractStructuredAddress(notes) {
  const segments = String(notes || '').split('|').map((part) => part.trim()).filter(Boolean);
  const addressSegment = segments.find((segment) => {
    const lower = segment.toLowerCase();
    return !lower.startsWith('shipping info:')
      && !lower.startsWith('status:')
      && !lower.startsWith('substatus:')
      && !lower.startsWith('buyer nickname:')
      && !lower.startsWith('buyer message:')
      && !lower.startsWith('payment:')
      && !lower.startsWith('package id:')
      && !lower.startsWith('tracking id:')
      && segment.split(',').length >= 5;
  });
  if (!addressSegment) return {};
  const parts = addressSegment.split(',').map((part) => part.trim());
  return {
    address1: parts[0] || '',
    address2: parts[1] || '',
    city: parts[2] || '',
    state: parts[3] || '',
    zipcode: parts[4] || '',
    country: parts[5] || '',
  };
}

function getOrderLineRevenue(order) {
  const orderTotal = Number(order?.amount_total ?? order?.total_amount ?? 0) || 0;
  if (orderTotal) return orderTotal;
  const lines = Array.isArray(order?.lines) ? order.lines : [];
  const revenue = lines.reduce((sum, line) => {
    const qty = Number(line.product_uom_qty ?? line.qty ?? 0) || 0;
    const unitPrice = Number(line.price_unit ?? line.unit_price ?? 0) || 0;
    const subtotal = Number(line.price_subtotal ?? line.subtotal ?? (qty * unitPrice)) || 0;
    return sum + subtotal;
  }, 0);
  return revenue || 0;
}

function getOrderLineCost(order) {
  const lines = Array.isArray(order?.lines) ? order.lines : [];
  return lines.reduce((sum, line) => {
    const qty = Number(line.product_uom_qty ?? line.qty ?? 0) || 0;
    const unitCost = Number(line.unit_cost ?? line.cost_price ?? 0) || 0;
    return sum + (unitCost * qty);
  }, 0);
}

function orderHasMissingCost(order) {
  const lines = Array.isArray(order?.lines) ? order.lines : [];
  if (!lines.length) return false;
  return lines.some((line) => {
    const hasProductIdentity = Boolean(line?.barcode || line?.product_name || line?.product_id_name || line?.name);
    const unitCost = Number(line.unit_cost ?? line.cost_price ?? 0) || 0;
    return hasProductIdentity && unitCost <= 0;
  });
}

function getOrderProfit(order) {
  if (orderHasMissingCost(order)) return null;
  const revenue = getOrderLineRevenue(order);
  const cost = getOrderLineCost(order);
  const derived = revenue - cost;
  if (Number.isFinite(derived)) return derived;
  return Number(order?.order_profit || 0) || 0;
}

function formatOrderProfit(order) {
  const profit = getOrderProfit(order);
  return profit == null ? 'Cost missing' : fmt(profit);
}

function infoRowsFromOrder(order) {
  const notes = parseTikTokNotes(order?.notes);
  const lines = Array.isArray(order?.lines) ? order.lines : [];
  const firstLine = lines[0] || {};
  const totalQty = lines.reduce((sum, line) => sum + (Number(line.product_uom_qty ?? line.qty ?? 0) || 0), 0);
  const unitPrice = Number(firstLine.price_unit ?? firstLine.unit_price ?? 0);
  const subtotal = lines.reduce((sum, line) => {
    const qty = Number(line.product_uom_qty ?? line.qty ?? 0) || 0;
    const lineUnitPrice = Number(line.price_unit ?? line.unit_price ?? 0) || 0;
    const lineSubtotal = Number(line.price_subtotal ?? line.subtotal ?? (qty * lineUnitPrice)) || 0;
    return sum + lineSubtotal;
  }, 0);
  const cost = lines.reduce((sum, line) => {
    const qty = Number(line.product_uom_qty ?? line.qty ?? 0) || 0;
    const unitCost = Number(line.unit_cost ?? line.cost_price ?? 0) || 0;
    return sum + (unitCost * qty);
  }, 0);
  const barcode = firstLine.barcode || '';
  const productName = firstLine.product_name || firstLine.product_id_name || firstLine.name || order?.product_names || '';
  const sellerSku = firstLine.tiktok_seller_sku || firstLine.seller_sku || notes['seller sku'] || extractLotFromExternalRef(order?.external_order_ref) || notes.lot || '';
  const shippingInfo = parseShippingInfo(notes['shipping info']);
  const cityState = splitCityState(shippingInfo.cityState);
  const address = extractStructuredAddress(order?.notes);
  const derivedProfit = getOrderProfit(order);
  return [
    ['Order ID', order?.external_order_ref || order?.order_number || '—'],
    ['Order Status', notes.status || order?.state || '—'],
    ['Order Substatus', notes.substatus || '—'],
    ['Cancelation/Return Type', order?.state === 'cancel' ? 'Cancelled' : '—'],
    ['Normal or Pre-order', 'normal'],
    ['SKU ID', firstLine.sku || '—'],
    ['Barcodes', barcode || '—'],
    ['Seller SKU', sellerSku || '—'],
    ['Product Name', productName || '—'],
    ['Variation', notes.variant || '—'],
    ['Virtual Bundle Seller SKU', '—'],
    ['Quantity', totalQty ? String(totalQty) : '—'],
    ['Sku Quantity of return', '—'],
    ['SKU Unit Original Price', unitPrice ? fmt(unitPrice) : '—'],
    ['SKU Subtotal Before Discount', subtotal ? fmt(subtotal) : '—'],
    ['SKU Platform Discount', '—'],
    ['SKU Seller Discount', '—'],
    ['SKU Subtotal After Discount', subtotal ? fmt(subtotal) : '—'],
    ['Shipping Fee After Discount', '—'],
    ['Original Shipping Fee', '—'],
    ['Shipping Fee Seller Discount', '—'],
    ['Co-Funded Shipping Fee Discount', '—'],
    ['Shipping Fee Platform Discount', '—'],
    ['Payment platform discount', '—'],
    ['Retail Delivery Fee', '—'],
    ['Taxes', '—'],
    ['Order Amount', order?.amount_total ? fmt(order.amount_total) : '—'],
    ['Order Refund Amount', order?.state === 'cancel' ? fmt(order.amount_total || 0) : '—'],
    ['Created Time', order?.created_at ? fmtDt(order.created_at) : '—'],
    ['Paid Time', order?.payment_status === 'paid' ? fmtDt(order.date_order) : '—'],
    ['RTS Time', '—'],
    ['Shipped Time', order?.fulfillment_status === 'shipped' ? fmtDt(order.updated_at || order.date_order) : '—'],
    ['Delivered Time', order?.fulfillment_status === 'delivered' ? fmtDt(order.updated_at || order.date_order) : '—'],
    ['Cancelled Time', order?.state === 'cancel' ? fmtDt(order.updated_at || order.date_order) : '—'],
    ['Cancel By', '—'],
    ['Cancel Reason', order?.state === 'cancel' ? 'Cancelled order' : '—'],
    ['Fulfillment Type', 'Seller fulfilled'],
    ['Warehouse Name', '—'],
    ['Tracking ID', notes['tracking id'] || order?.tracking_number || '—'],
    ['Delivery Option Type', '—'],
    ['Delivery Option', '—'],
    ['Shipping Provider Name', order?.tracking_carrier || '—'],
    ['Buyer Message', notes['buyer message'] || '—'],
    ['Buyer Nickname', notes['buyer nickname'] || '—'],
    ['Buyer Username', order?.whatnot_buyer_username ? `@${order.whatnot_buyer_username}` : '—'],
    ['Recipient', shippingInfo.recipient || '—'],
    ['Phone #', shippingInfo.phone || customerPhoneFromOrder(order) || '—'],
    ['Country', address.country || shippingInfo.country || '—'],
    ['State', address.state || cityState.state || '—'],
    ['City', address.city || cityState.city || '—'],
    ['Zipcode', address.zipcode || shippingInfo.zipcode || '—'],
    ['Address Line 1', address.address1 || '—'],
    ['Address Line 2', address.address2 || '—'],
    ['Delivery Instruction', notes['delivery note'] || '—'],
    ['Payment Method', notes.payment || order?.payment_status || '—'],
    ['Weight(kg)', '—'],
    ['Product Category', '—'],
    ['Package ID', notes['package id'] || '—'],
    ['Seller Note', notes['seller note'] || '—'],
    ['Shipping Information', notes['shipping info'] || '—'],
    ['Combined Listing', order?.product_names || '—'],
    ['Our Cost', cost ? fmt(cost) : '—'],
    ['Profit / Loss', derivedProfit == null ? 'Cost missing' : fmt(derivedProfit)],
  ];
}

function customerPhoneFromOrder(order) {
  const text = String(order?.notes || '');
  const first = text.split('|').map((part) => part.trim()).filter(Boolean)[1];
  if (!first || /order id:|package id:|tracking id:/i.test(first)) return '';
  return first;
}

function extractAddressPart(notes, index) {
  const text = String(notes || '');
  const segments = text.split('|').map((part) => part.trim()).filter(Boolean);
  const addressSegment = segments.find((segment) => segment.includes(',') && !segment.toLowerCase().startsWith('status:') && !segment.toLowerCase().startsWith('substatus:'));
  if (!addressSegment) return '';
  const parts = addressSegment.split(',').map((part) => part.trim());
  return parts[index] || '';
}

function SectionTitle({ children, sub }) {
  return (
    <div style={{ display: 'grid', gap: 4 }}>
      <div style={sectionTitleStyle}>{children}</div>
      {sub ? <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{sub}</div> : null}
    </div>
  );
}

function DetailGrid({ rows, columns = 2 }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
        gap: 0,
        ...softPanelStyle,
      }}
    >
      {rows.map(([label, value]) => (
        <div
          key={label}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 12,
            padding: '11px 14px',
            borderTop: '1px solid var(--border-subtle)',
          }}
        >
          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{label}</span>
          <span style={{ fontWeight: 700, fontSize: 12, textAlign: 'right', maxWidth: '60%', overflowWrap: 'anywhere' }}>{value}</span>
        </div>
      ))}
    </div>
  );
}

function seedProfileData(username, seedOrders = [], seedCustomer = null) {
  const orders = Array.isArray(seedOrders) ? seedOrders : [];
  const revenue = orders.reduce((sum, order) => sum + (Number(order.amount_total ?? order.total_amount ?? 0) || 0), 0);
  const profit = orders.reduce((sum, order) => {
    const lines = Array.isArray(order.lines) ? order.lines : [];
    const cost = lines.reduce((lineSum, line) => {
      const qty = Number(line.product_uom_qty ?? line.qty ?? 0) || 0;
      const unitCost = Number(line.unit_cost ?? line.cost_price ?? 0) || 0;
      return lineSum + (qty * unitCost);
    }, 0);
    return sum + ((Number(order.amount_total ?? order.total_amount ?? 0) || 0) - cost);
  }, 0);
  const uname = String(username || '').trim().replace(/^@/, '');
  return {
    ok: true,
    customer: {
      id: null,
      name: seedCustomer?.name || seedCustomer?.display_name || uname || null,
      display_name: seedCustomer?.display_name || seedCustomer?.name || uname || null,
      whatnot_username: seedCustomer?.whatnot_username || uname || null,
      identities: seedCustomer?.identities || [],
      sale_order_count: orders.length,
      total_revenue: revenue,
      total_profit: profit,
      last_purchase_at: orders[0]?.date_order || orders[0]?.ordered_at || null,
      ...(seedCustomer || {}),
    },
    sessions: [],
    products: [],
    summary: {
      purchase_count: orders.length,
      total_revenue: revenue,
      total_profit: profit,
    },
    orders,
    audience: {},
  };
}

export default function CustomerProfileDrawer({ customerId, username, onClose, seedOrders = [], seedCustomer = null }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [orderLineMap, setOrderLineMap] = useState({});
  const [inventoryMap, setInventoryMap] = useState({});

  useEffect(() => {
    const seeded = Array.isArray(seedOrders) && seedOrders.length ? seedProfileData(username, seedOrders, seedCustomer) : null;
    if (!customerId && !username) {
      setData(seeded);
      setOrderLineMap({});
      return;
    }
    if (seeded) setData(seeded);
    setLoading(true);
    const params = new URLSearchParams({ scope: 'company' });
    if (customerId) params.set('customer_id', customerId);
    if (username) params.set('username', username);
    fetchApi(`/api/customers/profile_lookup?${params}`)
      .then((result) => {
        const fetchedOrders = Array.isArray(result?.orders) ? result.orders : [];
        if (!fetchedOrders.length && seeded) {
          setData({
            ...seeded,
            ...(result || {}),
            customer: { ...(seeded.customer || {}), ...((result || {}).customer || {}) },
            summary: { ...(seeded.summary || {}), ...((result || {}).summary || {}) },
            orders: seeded.orders,
          });
        } else {
          setData(result);
        }
      })
      .catch(() => setData(seeded || { customer: { whatnot_username: username || null }, sessions: [], products: [], summary: {}, orders: [], audience: {} }))
      .finally(() => setLoading(false));
  }, [customerId, username, seedCustomer, seedOrders]);

  useEffect(() => {
    const orders = Array.isArray(data?.orders) ? data.orders : [];
    if (!orders.length) {
      setOrderLineMap({});
      return;
    }
    let cancelled = false;
    Promise.all(
      orders.map(async (order) => {
        const existingLines = Array.isArray(order?.lines) ? order.lines : [];
        if (existingLines.length) return [String(order.id), existingLines];
        try {
          const result = await fetchApi(`/api/sale_orders/lines?order_id=${encodeURIComponent(order.id)}`);
          return [String(order.id), Array.isArray(result?.rows) ? result.rows : []];
        } catch {
          return [String(order.id), []];
        }
      }),
    ).then((entries) => {
      if (cancelled) return;
      setOrderLineMap(Object.fromEntries(entries));
    });
    return () => {
      cancelled = true;
    };
  }, [data]);

  useEffect(() => {
    let cancelled = false;
    fetchApi('/api/inventory?active=all&status=all&compact=1')
      .then((result) => {
        if (cancelled) return;
        const rows = Array.isArray(result?.rows) ? result.rows : [];
        const next = {};
        rows.forEach((row) => {
          const barcode = normalizeBarcode(row?.barcode);
          if (!barcode) return;
          next[barcode] = {
            cost_price: Number(row?.cost_price || 0) || 0,
            retail_price: Number(row?.retail_price || 0) || 0,
          };
        });
        setInventoryMap(next);
      })
      .catch(() => {
        if (!cancelled) setInventoryMap({});
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const customer = data?.customer || {};
  const summary = data?.summary || {};
  const identities = Array.isArray(customer?.identities) ? customer.identities : [];
  const sessions = data?.sessions || [];
  const products = data?.products || [];
  const orders = (data?.orders || []).map((order) => ({
    ...order,
    lines: ((Array.isArray(orderLineMap[String(order.id)]) && orderLineMap[String(order.id)].length)
      ? orderLineMap[String(order.id)]
      : (Array.isArray(order?.lines) ? order.lines : [])
    ).map((line) => {
      const barcode = normalizeBarcode(line?.barcode);
      const inventory = inventoryMap[barcode] || null;
      const existingCost = Number(line?.unit_cost ?? line?.cost_price ?? 0) || 0;
      return {
        ...line,
        barcode,
        unit_cost: existingCost > 0 ? existingCost : Number(inventory?.cost_price || 0) || 0,
        retail_price: Number(line?.retail_price ?? 0) || Number(inventory?.retail_price || 0) || 0,
      };
    }),
  }));
  const audience = data?.audience || {};
  const timeline = audience.timeline || [];
  const streams = audience.streams || [];
  const tiktokOrders = orders.filter((order) => String(order.order_source || '').startsWith('tiktok'));
  const derivedRevenue = orders.reduce((sum, order) => sum + Number(order.amount_total || 0), 0);
  const knownProfits = orders
    .map((order) => getOrderProfit(order))
    .filter((value) => value != null);
  const hasProfitGaps = orders.some((order) => getOrderProfit(order) == null);
  const derivedProfit = knownProfits.reduce((sum, value) => sum + Number(value || 0), 0);
  const totalRevenue = orders.length
    ? derivedRevenue
    : Number(summary.total_revenue || customer.total_revenue || 0);
  const totalProfit = orders.length
    ? derivedProfit
    : Number(summary.total_profit || customer.total_profit || 0);
  const whatnotIdentity = identities.find((identity) => String(identity?.platform || '').toLowerCase() === 'whatnot');
  const tiktokLiveIdentity = identities.find((identity) => String(identity?.platform || '').toLowerCase() === 'tiktok_live');
  const tiktokShopIdentity = identities.find((identity) => String(identity?.platform || '').toLowerCase() === 'tiktok_shop');
  const profileEmail = customer.email || tiktokLiveIdentity?.email || whatnotIdentity?.email || tiktokShopIdentity?.email || '';
  const profilePhone = customer.phone || tiktokLiveIdentity?.phone || whatnotIdentity?.phone || tiktokShopIdentity?.phone || '';
  const profileAddress = customer.address || '';
  const fallbackUsername = String(username || '').trim().replace(/^@/, '');
  const usefulMetaRows = [
    ['Username', customer.whatnot_username ? `@${customer.whatnot_username}` : (fallbackUsername ? `@${fallbackUsername}` : '—')],
    ['TikTok LIVE Username', tiktokLiveIdentity?.username ? `@${tiktokLiveIdentity.username}` : '—'],
    ['TikTok Shop Username', tiktokShopIdentity?.username ? `@${tiktokShopIdentity.username}` : '—'],
    ['Email', profileEmail || '—'],
    ['Phone', profilePhone || '—'],
    ['Address', profileAddress || '—'],
    ['Last Purchase', customer.last_purchase_at ? fmtDt(customer.last_purchase_at) : (orders[0]?.date_order ? fmtDt(orders[0].date_order) : '—')],
    ['First Seen', audience.first_seen ? fmtDt(audience.first_seen) : '—'],
    ['Last Seen', audience.last_seen ? fmtDt(audience.last_seen) : '—'],
    ['Roles', (audience.roles || []).length ? audience.roles.join(', ') : '—'],
    ['Tier', audience.tier || '—'],
  ].filter(([, value]) => value && value !== '—');
  const title = customer.name || customer.display_name || tiktokLiveIdentity?.display_name || customer.whatnot_username || fallbackUsername || 'Customer';
  const subtitle = tiktokLiveIdentity?.username
    ? `TikTok LIVE · @${tiktokLiveIdentity.username}`
    : customer.whatnot_username
      ? `@${customer.whatnot_username}`
      : (fallbackUsername ? `@${fallbackUsername}` : '');

  return (
    <SlidePanel title={title} sub={subtitle} onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {loading ? <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading customer profile…</div> : null}

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
          <KpiCard label="Revenue" value={fmt(totalRevenue)} color="var(--accent-amber)" />
          <KpiCard label="Profit / Loss" value={hasProfitGaps ? 'Cost missing' : fmt(totalProfit)} color={hasProfitGaps ? 'var(--text-secondary)' : clrProfit(totalProfit)} />
          <KpiCard label="Orders" value={orders.length || customer.sale_order_count || 0} />
          <KpiCard label="Last Purchase" value={orders[0]?.date_order ? fmtDate(orders[0].date_order) : '—'} />
        </div>

        {usefulMetaRows.length ? <DetailGrid rows={usefulMetaRows} /> : null}

        {tiktokOrders.length ? (
          <>
            <SectionTitle sub="Imported TikTok live or shop orders for this customer.">TikTok Order Details</SectionTitle>
            <div style={{ display: 'grid', gap: 14 }}>
              {tiktokOrders.map((order) => {
                const rows = infoRowsFromOrder(order).filter(([, value]) => value && value !== '—');
                return (
                  <div key={`tiktok-order-${order.id}`} style={softPanelStyle}>
                    <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                      <div style={{ display: 'grid', gap: 5 }}>
                        <div style={{ fontWeight: 800, fontSize: 16 }}>{order.name || order.order_number}</div>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          {(order.order_source || '').replace('_', ' ').toUpperCase()} {order.whatnot_buyer_username ? `· @${order.whatnot_buyer_username}` : ''}
                        </div>
                      </div>
                      <div style={{ display: 'grid', justifyItems: 'end', gap: 5 }}>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{fmtDt(order.date_order)}</div>
                        <div style={{ fontWeight: 800, fontSize: 18, color: 'var(--accent-emerald)' }}>{fmt(order.amount_total)}</div>
                      </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 0 }}>
                      {rows.map(([label, value]) => (
                        <div key={`${order.id}-${label}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '10px 14px', borderTop: '1px solid var(--border-subtle)' }}>
                          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{label}</span>
                          <span style={{ fontWeight: 700, fontSize: 12, textAlign: 'right', maxWidth: '60%', overflowWrap: 'anywhere' }}>{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : null}

        <SectionTitle sub="Company-side order records for this customer.">Order History</SectionTitle>
        <TableShell footer={`${orders.length} order${orders.length === 1 ? '' : 's'}`}>
          <Thead cols={[
            { label: 'Order #' },
            { label: 'Date' },
            { label: 'Status' },
            { label: 'Session' },
            { label: 'Profit', align: 'right' },
            { label: 'Amount', align: 'right' },
          ]} />
          <tbody>
            {!orders.length ? <EmptyRow cols={6} msg="No company orders found." /> : orders.map((order) => (
              <tr key={order.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{order.name}</td>
                <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDate(order.date_order)}</td>
                <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{order.state}</td>
                <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{order.whatnot_session_id_name || '—'}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right', color: getOrderProfit(order) == null ? 'var(--text-secondary)' : clrProfit(getOrderProfit(order)), fontWeight: 700 }}>{formatOrderProfit(order)}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(order.amount_total)}</td>
              </tr>
            ))}
          </tbody>
        </TableShell>

        {sessions.length ? (
          <>
            <SectionTitle>Sessions Bought In</SectionTitle>
            <TableShell footer={`${sessions.length} session${sessions.length === 1 ? '' : 's'}`}>
              <Thead cols={[
                { label: 'Session' },
                { label: 'Purchases', align: 'right' },
                { label: 'Revenue', align: 'right' },
                { label: 'Profit', align: 'right' },
                { label: 'Last Purchase' },
              ]} />
              <tbody>
                {sessions.map((row) => (
                  <tr key={row.id || row.session_name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.session_name || '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.purchase_count ?? 0}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.total_revenue)}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: clrProfit(row.total_profit), fontWeight: 700 }}>{fmt(row.total_profit)}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDt(row.last_sold_at)}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </>
        ) : null}

        {products.length ? (
          <>
            <SectionTitle>Products Bought</SectionTitle>
            <TableShell footer={`${products.length} product${products.length === 1 ? '' : 's'}`}>
              <Thead cols={[
                { label: 'Product' },
                { label: 'Times Bought', align: 'right' },
                { label: 'Avg Price', align: 'right' },
                { label: 'Revenue', align: 'right' },
                { label: 'Profit', align: 'right' },
                { label: 'Last Purchase' },
              ]} />
              <tbody>
                {products.map((row, index) => (
                  <tr key={`${row.product_name}-${row.sku}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.product_name || '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.purchase_count ?? 0}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)' }}>{fmt(row.avg_sale_price)}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.total_revenue)}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: clrProfit(row.total_profit), fontWeight: 700 }}>{fmt(row.total_profit)}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDt(row.last_sold_at)}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </>
        ) : null}

        {timeline.length ? (
          <>
            <SectionTitle>Activity Timeline</SectionTitle>
            <TableShell footer={`${timeline.length} event${timeline.length === 1 ? '' : 's'}`}>
              <Thead cols={[
                { label: 'Time' },
                { label: 'Streamer' },
                { label: 'Type' },
                { label: 'Lot' },
                { label: 'Product' },
                { label: 'Price', align: 'right' },
              ]} />
              <tbody>
                {timeline.slice(0, 80).map((item, index) => (
                  <tr key={`${item.time}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12 }}>{fmtDt(item.time)}</td>
                    <td style={{ padding: '8px 14px', fontWeight: 700 }}>{item.streamer || '—'}</td>
                    <td style={{ padding: '8px 14px' }}><ActivityBadge role={item.role} /></td>
                    <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)' }}>{item.lot || '—'}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.product || '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: item.price ? 'var(--accent-amber)' : 'var(--text-secondary)', fontWeight: 700 }}>{item.price ? fmt(item.price) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </>
        ) : null}

        {streams.length ? (
          <>
            <SectionTitle>Streams Seen In</SectionTitle>
            <TableShell footer={`${streams.length} stream${streams.length === 1 ? '' : 's'}`}>
              <Thead cols={[
                { label: 'Streamer' },
                { label: 'Chats', align: 'right' },
                { label: 'Bids', align: 'right' },
                { label: 'Wins', align: 'right' },
                { label: 'Spent', align: 'right' },
                { label: 'Last Seen' },
              ]} />
              <tbody>
                {streams.map((row) => (
                  <tr key={row.stream_id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.streamer_name || '—'}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.chat_messages ?? 0}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.bids ?? 0}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.wins ?? 0}</td>
                    <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.spent)}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDt(row.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </TableShell>
          </>
        ) : null}
      </div>
    </SlidePanel>
  );
}
