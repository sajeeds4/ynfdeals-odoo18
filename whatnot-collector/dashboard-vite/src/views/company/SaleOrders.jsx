import { useState, useEffect, useCallback, useMemo } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  fmt, fmtDt, fmtDate,
  Badge, KpiCard, SearchInput,
  TableShell, Thead, EmptyRow, PrimaryBtn, GhostBtn, SlidePanel,
} from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';

const ORDER_PAGE_SIZE = 120;

const STATE_MAP = {
  draft: { label: 'Pending', bg: 'var(--status-pending)', color: '#000' },
  sent: { label: 'Sent', bg: 'var(--accent-blue)', color: '#fff' },
  sale: { label: 'Open', bg: 'var(--accent-emerald)', color: '#fff' },
  cancel: { label: 'Cancelled', bg: 'var(--accent-coral)', color: '#fff' },
};

const FULFILLMENT_MAP = {
  pending: { label: 'Pending', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' },
  packed: { label: 'Packed', bg: 'rgba(251,191,36,0.16)', color: '#fbbf24' },
  shipped: { label: 'Shipped', bg: 'var(--accent-emerald)', color: '#fff' },
};

const PAYMENT_MAP = {
  unpaid: { label: 'Unpaid', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' },
  paid: { label: 'Paid', bg: 'var(--accent-emerald)', color: '#fff' },
  refunded: { label: 'Refunded', bg: 'var(--accent-coral)', color: '#fff' },
};

const TRACKING_STATUS_MAP = {
  pending: { label: 'Pending', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' },
  label_created: { label: 'Label Created', bg: 'rgba(96,165,250,0.16)', color: '#93c5fd' },
  accepted: { label: 'Accepted', bg: 'rgba(251,191,36,0.16)', color: '#fbbf24' },
  in_transit: { label: 'In Transit', bg: 'rgba(96,165,250,0.16)', color: '#60a5fa' },
  out_for_delivery: { label: 'Out for Delivery', bg: 'rgba(167,139,250,0.16)', color: '#a78bfa' },
  delivered: { label: 'Delivered', bg: 'var(--accent-emerald)', color: '#fff' },
  exception: { label: 'Exception', bg: 'var(--accent-coral)', color: '#fff' },
};

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '8px 10px',
  fontSize: 13,
  width: '100%',
};

function toInputDateTime(value) {
  if (!value) return '';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function fromInputDateTime(value) {
  return value ? new Date(value).toISOString() : null;
}

function OrderLineEditor({ orderId, line, products, onSaved, onCancel }) {
  const [form, setForm] = useState({
    product_id: line?.product_id || '',
    description: line?.name || '',
    qty: line?.product_uom_qty ?? 1,
    unit_price: line?.price_unit ?? 0,
    inventory_applied: !!line?.whatnot_inventory_applied,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function save() {
    setSaving(true);
    setError('');
    try {
      await postApi('/api/sale_orders/line/save', {
        line_id: line?.id,
        order_id: orderId,
        product_id: form.product_id || null,
        description: form.description,
        qty: Number(form.qty || 0),
        unit_price: Number(form.unit_price || 0),
        inventory_applied: !!form.inventory_applied,
      });
      onSaved();
    } catch (err) {
      setError(err.message || 'Unable to save line.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 12, display: 'grid', gap: 10 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {line?.id ? 'Edit Line' : 'New Line'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Product</span>
          <select value={form.product_id} onChange={(e) => setForm((v) => ({ ...v, product_id: e.target.value }))} style={inputStyle}>
            <option value="">Custom / not linked</option>
            {products.map((product) => (
              <option key={product.id} value={product.id}>{product.name}</option>
            ))}
          </select>
        </label>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Qty</span>
          <input type="number" min="0" step="0.01" value={form.qty} onChange={(e) => setForm((v) => ({ ...v, qty: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Description</span>
          <input value={form.description} onChange={(e) => setForm((v) => ({ ...v, description: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Unit Price</span>
          <input type="number" min="0" step="0.01" value={form.unit_price} onChange={(e) => setForm((v) => ({ ...v, unit_price: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
          <input type="checkbox" checked={form.inventory_applied} onChange={(e) => setForm((v) => ({ ...v, inventory_applied: e.target.checked }))} />
          Inventory already applied
        </label>
      </div>
      {error ? <div style={{ color: 'var(--accent-coral)', fontSize: 12 }}>{error}</div> : null}
      <div style={{ display: 'flex', gap: 8 }}>
        <PrimaryBtn onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save Line'}</PrimaryBtn>
        <GhostBtn onClick={onCancel}>Cancel</GhostBtn>
      </div>
    </div>
  );
}

function OrderLines({ orderId, products, onChanged }) {
  const [rows, setRows] = useState(null);
  const [editing, setEditing] = useState(null);
  const [showNew, setShowNew] = useState(false);

  const load = useCallback(() => {
    fetchApi(`/api/sale_orders/lines?order_id=${orderId}`)
      .then((d) => setRows(d.rows || []))
      .catch(() => setRows([]));
  }, [orderId]);

  useEffect(() => {
    load();
  }, [load]);

  async function removeLine(lineId) {
    if (!window.confirm('Delete this order line?')) return;
    await postApi('/api/sale_orders/line/delete', { line_id: lineId });
    setEditing(null);
    load();
    onChanged();
  }

  if (!rows) return <div style={{ padding: 12, color: 'var(--text-secondary)' }}>Loading…</div>;

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>Order Lines</div>
        <GhostBtn onClick={() => { setShowNew((v) => !v); setEditing(null); }}>
          {showNew ? 'Close New Line' : 'Add Line'}
        </GhostBtn>
      </div>

      {showNew ? (
        <OrderLineEditor
          orderId={orderId}
          products={products}
          onSaved={() => {
            setShowNew(false);
            load();
            onChanged();
          }}
          onCancel={() => setShowNew(false)}
        />
      ) : null}

      {!rows.length ? (
        <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No lines.</div>
      ) : (
        rows.map((l) => (
          <div key={l.id} style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 12, display: 'grid', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
              <div>
                <div style={{ fontWeight: 700 }}>{l.product_id_name || l.name || 'Line item'}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                  {l.buyer_username ? `@${l.buyer_username}` : 'No buyer'} · Lot {l.lot_number || '—'} · {fmtDt(l.sold_at)}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 3 }}>
                  Qty {l.product_uom_qty} · {fmt(l.price_unit)} each · On hand {l.on_hand_qty ?? '—'}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(l.price_subtotal)}</div>
                <div style={{ display: 'flex', gap: 8, marginTop: 8, justifyContent: 'flex-end' }}>
                  <GhostBtn onClick={() => { setEditing(l); setShowNew(false); }}>Edit</GhostBtn>
                  <GhostBtn onClick={() => removeLine(l.id)}>Delete</GhostBtn>
                </div>
              </div>
            </div>
            {editing?.id === l.id ? (
              <OrderLineEditor
                orderId={orderId}
                line={editing}
                products={products}
                onSaved={() => {
                  setEditing(null);
                  load();
                  onChanged();
                }}
                onCancel={() => setEditing(null)}
              />
            ) : null}
          </div>
        ))
      )}
    </div>
  );
}

function OrderDetailPanel({ order, onClose, onSaved, onOpenCustomer, buyerLabel = 'Buyer' }) {
  const [form, setForm] = useState({
    state: order.state || 'draft',
    fulfillment_status: order.fulfillment_status || 'pending',
    payment_status: order.payment_status || 'unpaid',
    tracking_number: order.tracking_number || '',
    tracking_carrier: order.tracking_carrier || 'usps',
    tracking_status: order.tracking_status || 'pending',
    tracking_status_detail: order.tracking_status_detail || '',
    ordered_at: toInputDateTime(order.date_order),
    whatnot_buyer_username: order.whatnot_buyer_username || '',
    customer_id: order.customer_id || '',
    notes: order.notes || '',
  });
  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchApi('/api/customers?scope=company').then((d) => setCustomers(d.rows || [])).catch(() => setCustomers([]));
    fetchApi('/api/inventory?status=all&compact=1').then((d) => setProducts(d.rows || [])).catch(() => setProducts([]));
  }, []);

  async function saveOrder() {
    setSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/sale_orders/update', {
        order_id: order.id,
        state: form.state,
        fulfillment_status: form.fulfillment_status,
        payment_status: form.payment_status,
        tracking_number: form.tracking_number,
        tracking_carrier: form.tracking_carrier,
        tracking_status: form.tracking_status,
        tracking_status_detail: form.tracking_status_detail,
        packed_at: form.fulfillment_status === 'packed' ? (order.packed_at || new Date().toISOString()) : null,
        shipped_at: form.fulfillment_status === 'shipped' ? (order.shipped_at || new Date().toISOString()) : null,
        delivered_at: form.tracking_status === 'delivered' ? (order.delivered_at || new Date().toISOString()) : null,
        ordered_at: fromInputDateTime(form.ordered_at),
        whatnot_buyer_username: form.whatnot_buyer_username,
        customer_id: form.customer_id || null,
        notes: form.notes,
      });
      setMessage('Order updated.');
      onSaved(result.order || null);
    } catch (err) {
      setMessage(err.message || 'Unable to update order.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlidePanel
      title={order.name}
      sub={`${order.partner_id_name || 'No customer'}${order.whatnot_buyer_username ? ` · @${order.whatnot_buyer_username}` : ''}`}
      onClose={onClose}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
          <KpiCard label="Total" value={fmt(order.amount_total)} color="var(--accent-amber)" />
          <KpiCard label="Status" value={STATE_MAP[order.state]?.label || order.state} />
          <KpiCard label="Payment" value={PAYMENT_MAP[order.payment_status]?.label || order.payment_status || 'Unpaid'} />
          <KpiCard label="Fulfillment" value={FULFILLMENT_MAP[order.fulfillment_status]?.label || order.fulfillment_status || 'Pending'} />
        </div>

        <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 14, display: 'grid', gap: 12 }}>
          <div style={{ fontWeight: 700 }}>Order Management</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Status</span>
              <select value={form.state} onChange={(e) => setForm((v) => ({ ...v, state: e.target.value }))} style={inputStyle}>
                <option value="draft">Pending</option>
                <option value="sent">Sent</option>
                <option value="sale">Open</option>
                <option value="cancel">Cancelled</option>
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Fulfillment</span>
              <select value={form.fulfillment_status} onChange={(e) => setForm((v) => ({ ...v, fulfillment_status: e.target.value }))} style={inputStyle}>
                <option value="pending">Pending</option>
                <option value="packed">Packed</option>
                <option value="shipped">Shipped</option>
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Payment</span>
              <select value={form.payment_status} onChange={(e) => setForm((v) => ({ ...v, payment_status: e.target.value }))} style={inputStyle}>
                <option value="unpaid">Unpaid</option>
                <option value="paid">Paid</option>
                <option value="refunded">Refunded</option>
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Ordered At</span>
              <input type="datetime-local" value={form.ordered_at} onChange={(e) => setForm((v) => ({ ...v, ordered_at: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{buyerLabel}</span>
              <input value={form.whatnot_buyer_username} onChange={(e) => setForm((v) => ({ ...v, whatnot_buyer_username: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Customer</span>
              <select value={form.customer_id} onChange={(e) => setForm((v) => ({ ...v, customer_id: e.target.value }))} style={inputStyle}>
                <option value="">Unassigned</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>
                    {customer.name || customer.whatnot_username}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Tracking Number</span>
              <input value={form.tracking_number} onChange={(e) => setForm((v) => ({ ...v, tracking_number: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Carrier</span>
              <select value={form.tracking_carrier} onChange={(e) => setForm((v) => ({ ...v, tracking_carrier: e.target.value }))} style={inputStyle}>
                <option value="usps">USPS</option>
                <option value="ups">UPS</option>
                <option value="fedex">FedEx</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Tracking Status</span>
              <select value={form.tracking_status} onChange={(e) => setForm((v) => ({ ...v, tracking_status: e.target.value }))} style={inputStyle}>
                <option value="pending">Pending</option>
                <option value="label_created">Label Created</option>
                <option value="accepted">Accepted</option>
                <option value="in_transit">In Transit</option>
                <option value="out_for_delivery">Out for Delivery</option>
                <option value="delivered">Delivered</option>
                <option value="exception">Exception</option>
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Tracking Detail</span>
              <input value={form.tracking_status_detail} onChange={(e) => setForm((v) => ({ ...v, tracking_status_detail: e.target.value }))} style={inputStyle} placeholder="Awaiting USPS API sync or manual note" />
            </label>
            <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Internal Notes</span>
              <textarea value={form.notes} onChange={(e) => setForm((v) => ({ ...v, notes: e.target.value }))} rows={4} style={{ ...inputStyle, resize: 'vertical' }} />
            </label>
          </div>
          {order.tracking_url ? (
            <div>
              <a href={order.tracking_url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: 'var(--accent-blue)', fontWeight: 700, textDecoration: 'none' }}>
                Open Tracking Page
              </a>
            </div>
          ) : null}
          {message ? <div style={{ fontSize: 12, color: message.includes('Unable') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{message}</div> : null}
          <div style={{ display: 'flex', gap: 8 }}>
            <PrimaryBtn onClick={saveOrder} disabled={saving}>{saving ? 'Saving...' : 'Save Order'}</PrimaryBtn>
          </div>
        </div>

        <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
          {[
            ['Order #', order.name],
            ['Session', order.whatnot_session_id_name],
            ['Customer', order.partner_id_name ? <CustomerLink username={order.whatnot_buyer_username} customerId={order.customer_id} label={order.partner_id_name} onOpen={onOpenCustomer} /> : '—'],
            ['Created', fmtDt(order.date_order)],
            ['Fulfillment', FULFILLMENT_MAP[order.fulfillment_status]?.label || order.fulfillment_status],
            ['Payment', PAYMENT_MAP[order.payment_status]?.label || order.payment_status],
            ['Tracking', order.tracking_number],
            ['Carrier', (order.tracking_carrier || 'usps').toUpperCase()],
            ['Tracking Status', TRACKING_STATUS_MAP[order.tracking_status || 'pending']?.label || order.tracking_status || 'Pending'],
            ['Tracking Detail', order.tracking_status_detail],
            ['Last Checked', fmtDt(order.tracking_last_checked_at)],
            ['Delivered At', fmtDt(order.delivered_at)],
            ['Subtotal', fmt(order.amount_untaxed)],
            ['Linked Results', order.linked_results_count || 0],
            ['Linked Products', order.linked_products_sold || 0],
            ['Lots', order.linked_lot_numbers || '—'],
            [buyerLabel, order.whatnot_buyer_username ? <CustomerLink username={order.whatnot_buyer_username} customerId={order.customer_id} label={`@${order.whatnot_buyer_username}`} onOpen={onOpenCustomer} /> : '—'],
          ].filter(([, value]) => value).map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
              <span style={{ fontWeight: 600 }}>{value}</span>
            </div>
          ))}
        </div>

        <OrderLines orderId={order.id} products={products} onChanged={() => onSaved()} />
      </div>
    </SlidePanel>
  );
}

const ORDER_TABS = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'paid', label: 'Paid' },
  { id: 'shipped', label: 'Shipped' },
  { id: 'delivered', label: 'Delivered' },
  { id: 'cancel', label: 'Cancelled' },
];

const FINAL_ORDER_TABS = [
  { id: 'delivered', label: 'Confirmed' },
  { id: 'cancel', label: 'Cancelled' },
];

export default function SaleOrders({
  sessions = [],
  source = '',
  title = 'Sales Orders',
  rowFilter = null,
  initialOrderTab = 'all',
  finalOnly = false,
  treatUnconfirmedAsCancelled = false,
  onOpenPickList = null,
}) {
  const [search, setSearch] = useState('');
  const [debSearch, setDebSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFilter, setDateFilter] = useState('all');
  const [platformFilter, setPlatformFilter] = useState(source || 'all');
  const [affiliateFilter, setAffiliateFilter] = useState('all');
  const [sessionFilter, setSessionFilter] = useState('all');
  const [orderTab, setOrderTab] = useState(finalOnly ? (initialOrderTab === 'cancel' ? 'cancel' : 'delivered') : (initialOrderTab || 'all'));
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [actionBusyId, setActionBusyId] = useState(null);
  const [customerPeek, setCustomerPeek] = useState(null);
  const [showExtraFilters, setShowExtraFilters] = useState(false);
  const [showInsights, setShowInsights] = useState(false);

  const activeFilterCount = [
    platformFilter !== 'all' && platformFilter !== source ? 1 : 0,
    affiliateFilter !== 'all' ? 1 : 0,
    sessionFilter !== 'all' ? 1 : 0,
    statusFilter ? 1 : 0,
  ].reduce((a, b) => a + b, 0);

  useEffect(() => {
    const t = setTimeout(() => setDebSearch(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async (keepDetailId = null, append = false, offset = 0) => {
    setLoading(true);
    const p = new URLSearchParams();
    p.set('scope', 'company');
    p.set('summary', '1');
    p.set('limit', String(ORDER_PAGE_SIZE));
    if (append) p.set('offset', String(offset || 0));
    if (debSearch) p.set('q', debSearch);
    if (source) p.set('source', source);
    else if (platformFilter !== 'all') p.set('source', platformFilter);
    if (sessionFilter !== 'all') p.set('session_id', sessionFilter);
    const serverStatus = statusFilter || (orderTab !== 'all' ? orderTab : '');
    if (serverStatus) p.set('status', serverStatus);
    try {
      const d = await fetchApi(`/api/sale_orders?${p}`);
      if (append) {
        setData((current) => ({
          ...d,
          rows: [...(current?.rows || []), ...(d?.rows || [])],
        }));
      } else {
        setData(d);
      }
      if (keepDetailId) {
        const fresh = (d.rows || []).find((row) => row.id === keepDetailId);
        if (fresh) setDetail(fresh);
      }
    } catch {
      setData({ rows: [] });
    } finally {
      setLoading(false);
    }
  }, [debSearch, orderTab, platformFilter, sessionFilter, source, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOrderTab(finalOnly ? (initialOrderTab === 'cancel' ? 'cancel' : 'delivered') : (initialOrderTab || 'all'));
  }, [finalOnly, initialOrderTab]);

  const rawRows = (data?.rows || []).map(r => {
    // Fix: cancelled orders should not show shipped/packed
    if (r.state === 'cancel' && r.fulfillment_status !== 'pending') {
      return { ...r, fulfillment_status: 'pending' };
    }
    return r;
  });
  function isPendingOrder(row) {
    return row.state !== 'cancel' && !matchesDelivered(row);
  }

  function matchesDelivered(row) {
    return row.state !== 'cancel' && (
      row.fulfillment_status === 'delivered'
      || row.tracking_status === 'delivered'
      || Boolean(String(row.delivered_at || '').trim())
    );
  }

  function matchesStatus(row, status) {
    if (!status || status === 'all') return true;
    if (status === 'pending') return isPendingOrder(row);
    if (status === 'paid') return row.payment_status === 'paid' && row.state !== 'cancel';
    if (status === 'shipped') return row.fulfillment_status === 'shipped' && row.state !== 'cancel';
    if (status === 'delivered' || status === 'confirmed') return matchesDelivered(row);
    if (status === 'cancel') {
      if (!treatUnconfirmedAsCancelled) return row.state === 'cancel';
      return row.state === 'cancel' || row.payment_status !== 'paid' || row.state !== 'sale';
    }
    return true;
  }

  function displayStateBadge(row) {
    if (treatUnconfirmedAsCancelled && matchesStatus(row, 'cancel') && row.state !== 'cancel') {
      return { label: 'Cancelled / Missing', bg: 'rgba(239,68,68,0.16)', color: '#dc2626' };
    }
    return STATE_MAP[row.state] || { label: row.state, bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' };
  }

  function matchesDate(row) {
    if (dateFilter === 'all') return true;
    if (!row.date_order) return false;
    const dt = new Date(row.date_order);
    if (Number.isNaN(dt.getTime())) return false;
    const now = new Date();
    if (dateFilter === 'today') return dt.toDateString() === now.toDateString();
    const days = dateFilter === '7d' ? 7 : dateFilter === '30d' ? 30 : 0;
    if (!days) return true;
    return dt >= new Date(now.getTime() - days * 24 * 60 * 60 * 1000);
  }

  function platformFingerprint(row) {
    return [
      row.source,
      row.platform,
      row.sales_channel,
      row.order_source,
      row.external_order_ref,
      row.origin,
      row.channel,
      row.session_name,
      row.notes,
    ].map((value) => String(value || '').toLowerCase()).join(' ');
  }

  function platformValue(row) {
    const value = platformFingerprint(row);
    if (value.includes('tiktok_shop')) return 'tiktok_shop';
    if (value.includes('tiktok shop')) return 'tiktok_shop';
    if (value.includes('tiktok') || value.includes('tik tok')) return 'tiktok_live';
    if (value.includes('affiliate')) return 'affiliate';
    if (value.includes('in_house') || value.includes('in-house')) return 'in_house';
    return 'whatnot';
  }

  function platformLabel(value) {
    if (value === 'tiktok_shop') return 'TikTok Shop';
    if (value === 'tiktok_live') return 'TikTok Live';
    if (value === 'affiliate') return 'Partner';
    return 'Whatnot Live';
  }

  function affiliateValue(row) {
    return String(row.affiliate_id || row.affiliate_name || row.affiliate_account_name || row.source_affiliate || '').trim();
  }

  const affiliateOptions = Array.from(
    new Map(rawRows
      .map((row) => {
        const value = affiliateValue(row);
        const label = row.affiliate_name || row.affiliate_account_name || value;
        return value ? [value, label] : null;
      })
      .filter(Boolean)).entries(),
  );

  function sessionValue(row) {
    return String(row.whatnot_session_id || row.session_id || row.whatnot_session_id_name || row.session_name || '').trim();
  }

  function sessionLabel(row) {
    return row.whatnot_session_id_name || row.session_name || `Session ${row.whatnot_session_id || row.session_id || ''}` || 'No session';
  }

  const sessionOptions = Array.from(
    new Map(rawRows
      .map((row) => {
        const value = sessionValue(row);
        const label = sessionLabel(row);
        return value ? [value, label] : null;
      })
      .filter(Boolean)).entries(),
  );

  function normalizeSessionOption(session) {
    const value = String(session?.id || '').trim();
    if (!value) return null;
    return {
      value,
      label: String(session?.name || `Session ${value}`).trim(),
      status: String(session?.status || '').trim().toLowerCase(),
      sortAt: String(session?.ended_at || session?.updated_at || session?.started_at || session?.created_at || ''),
    };
  }

  const sessionSeedOptions = useMemo(() => (
    (sessions || [])
      .map(normalizeSessionOption)
      .filter(Boolean)
      .sort((a, b) => {
        const rank = (value) => {
          if (value === 'live') return 0;
          if (value === 'draft') return 1;
          if (value === 'ended') return 2;
          return 3;
        };
        const rankDiff = rank(a.status) - rank(b.status);
        if (rankDiff !== 0) return rankDiff;
        const aTime = a.sortAt ? new Date(a.sortAt).getTime() : 0;
        const bTime = b.sortAt ? new Date(b.sortAt).getTime() : 0;
        if (aTime !== bTime) return bTime - aTime;
        return Number(b.value || 0) - Number(a.value || 0);
      })
  ), [sessions]);

  const mergedSessionOptions = useMemo(() => {
    const merged = new Map();
    sessionSeedOptions.forEach((option) => {
      merged.set(option.value, option.label);
    });
    sessionOptions.forEach(([value, label]) => {
      if (!merged.has(value)) merged.set(value, label);
    });
    return Array.from(merged.entries());
  }, [sessionOptions, sessionSeedOptions]);

  const sourceRows = rawRows.filter((row) => !rowFilter || rowFilter(row));
  const tabFiltered = sourceRows.filter((row) => matchesStatus(row, orderTab));
  const rows = tabFiltered.filter((row) => (
    matchesStatus(row, statusFilter)
    && matchesDate(row)
    && (platformFilter === 'all' || platformValue(row) === platformFilter)
    && (affiliateFilter === 'all' || affiliateValue(row) === affiliateFilter)
    && (sessionFilter === 'all' || sessionValue(row) === sessionFilter)
  ));
  const grossRevenue = rows
    .filter((row) => row.state !== 'cancel')
    .reduce((sum, row) => sum + Number(row.amount_total || 0), 0);
  const paidRevenue = rows
    .filter((row) => row.state !== 'cancel' && row.payment_status === 'paid')
    .reduce((sum, row) => sum + Number(row.amount_total || 0), 0);
  const avgOrderValue = rows.length ? grossRevenue / rows.length : 0;
  const shippingExceptions = rows.filter((row) => String(row.tracking_status || '').toLowerCase() === 'exception').length;
  const platformBreakdown = useMemo(() => (
    ['whatnot', 'tiktok_live', 'tiktok_shop', 'affiliate']
      .map((platform) => {
        const platformRows = rows.filter((row) => platformValue(row) === platform);
        return {
          id: platform,
          label: platformLabel(platform),
          count: platformRows.length,
          revenue: platformRows
            .filter((row) => row.state !== 'cancel')
            .reduce((sum, row) => sum + Number(row.amount_total || 0), 0),
          pending: platformRows.filter(isPendingOrder).length,
        };
      })
      .filter((item) => item.count > 0),
  ), [rows]);
  const sessionBreakdown = useMemo(() => (
    Array.from(
      rows.reduce((acc, row) => {
        const key = sessionValue(row) || 'none';
        const current = acc.get(key) || {
          id: key,
          label: sessionLabel(row) || 'No session',
          count: 0,
          revenue: 0,
          paid: 0,
        };
        current.count += 1;
        if (row.state !== 'cancel') current.revenue += Number(row.amount_total || 0);
        if (row.state !== 'cancel' && row.payment_status === 'paid') current.paid += Number(row.amount_total || 0);
        acc.set(key, current);
        return acc;
      }, new Map()).values(),
    )
      .sort((a, b) => b.revenue - a.revenue)
      .slice(0, 6)
  ), [rows]);
  const topBuyers = useMemo(() => (
    Array.from(
      rows.reduce((acc, row) => {
        const key = String(row.partner_id_name || row.whatnot_buyer_username || 'Unknown').trim();
        if (!key) return acc;
        const current = acc.get(key) || { label: key, count: 0, revenue: 0 };
        current.count += 1;
        if (row.state !== 'cancel') current.revenue += Number(row.amount_total || 0);
        acc.set(key, current);
        return acc;
      }, new Map()).values(),
    )
      .sort((a, b) => b.revenue - a.revenue)
      .slice(0, 5)
  ), [rows]);
  const todayRows = sourceRows.filter((row) => {
    if (!row.date_order) return false;
    const dt = new Date(row.date_order);
    return !Number.isNaN(dt.getTime()) && dt.toDateString() === new Date().toDateString();
  });
  const revenueToday = todayRows
    .filter((row) => row.state !== 'cancel')
    .reduce((sum, row) => sum + Number(row.amount_total || 0), 0);
  const pendingActions = sourceRows.filter(isPendingOrder).length;
  const visibleOrderTabs = finalOnly ? FINAL_ORDER_TABS : ORDER_TABS;
  const summaryCounts = data?.base_summary || data || {};
  function orderTabCount(tabId) {
    if (tabId === 'all') return Number(summaryCounts.total_count ?? sourceRows.length);
    if (tabId === 'pending') return Number(summaryCounts.pending_count ?? sourceRows.filter((row) => matchesStatus(row, 'pending')).length);
    if (tabId === 'paid') return Number(summaryCounts.paid_count ?? sourceRows.filter((row) => matchesStatus(row, 'paid')).length);
    if (tabId === 'shipped') return Number(summaryCounts.shipped_count ?? sourceRows.filter((row) => matchesStatus(row, 'shipped')).length);
    if (tabId === 'delivered' || tabId === 'confirmed') return Number(summaryCounts.confirmed_count ?? sourceRows.filter((row) => matchesStatus(row, 'delivered')).length);
    if (tabId === 'cancel') return Number(summaryCounts.cancel_count ?? sourceRows.filter((row) => matchesStatus(row, 'cancel')).length);
    return sourceRows.filter((row) => matchesStatus(row, tabId)).length;
  }
  const buyerLabel = source === 'tiktok_live' || source === 'tiktok_shop' || source === 'affiliate' ? 'Buyer' : 'Whatnot Buyer';
  const searchPlaceholder = source === 'tiktok_live'
    ? 'Search order #, customer, buyer, lot...'
    : source === 'affiliate'
      ? 'Search order #, partner, customer, buyer...'
      : 'Search order #, customer, buyer...';
  const COLS = [
    { label: 'Order #' },
    { label: 'Customer' },
    { label: 'Status' },
    { label: 'Payment' },
    { label: 'Fulfillment' },
    { label: 'Total', align: 'right' },
    { label: 'Action' },
  ];

  async function updateOrderAction(order, action) {
    setActionBusyId(`${order.id}-${action}`);
    try {
      const payload = { order_ids: [order.id] };
      if (action === 'shipped') payload.mark_shipped = true;
      if (action === 'paid') payload.payment_status = 'paid';
      if (action === 'cancel') {
        if (!window.confirm(`Cancel ${order.name}?`)) {
          setActionBusyId(null);
          return;
        }
        payload.state = 'cancel';
      }
      await postApi('/api/sale_orders/bulk_update', payload);
      load(detail?.id || null);
    } finally {
      setActionBusyId(null);
    }
  }

  return (
    <div className="orders-ops-page">
      {title ? (
        <div className="orders-ops-header">
          <div>
            <div className="orders-ops-header-title">{title}</div>
            <div className="orders-ops-header-sub">
              {source === 'tiktok_live'
                ? 'Manage TikTok LIVE auction orders, payments, and fulfillment.'
                : source === 'affiliate'
                  ? 'Manage partner-uploaded orders, payments, and fulfillment from one table.'
                  : source === 'whatnot'
                    ? 'Manage Whatnot live orders, payments, and fulfillment.'
                    : 'Manage payments, shipping, and cancellations from one table.'}
            </div>
          </div>
          {source === 'whatnot' && typeof onOpenPickList === 'function' ? (
            <button
              type="button"
              onClick={onOpenPickList}
              style={{
                border: '1px solid rgba(226, 232, 240, 0.95)',
                background: '#fff',
                color: '#1a1f36',
                borderRadius: 999,
                padding: '9px 14px',
                fontSize: 12,
                fontWeight: 800,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                boxShadow: '0 4px 14px rgba(15,23,42,0.04)',
              }}
            >
              Pick List / Labels
            </button>
          ) : null}
        </div>
      ) : null}

      {/* ── KPI Strip — hero emphasis on actionable metrics ────── */}
      <div className="orders-ops-metrics">
        {!finalOnly ? (
          <div className={`orders-ops-metric${pendingActions > 0 ? ' is-alert' : ''}`}>
            <span>Pending Actions</span>
            <strong>{pendingActions.toLocaleString()}</strong>
          </div>
        ) : null}
        <div className="orders-ops-metric is-hero">
          <span>Revenue Today</span>
          <strong>{fmt(revenueToday)}</strong>
        </div>
        <div className="orders-ops-metric is-hero">
          <span>Filtered Revenue</span>
          <strong>{fmt(grossRevenue)}</strong>
        </div>
        <div className="orders-ops-metric">
          <span>Orders Today</span>
          <strong>{todayRows.length.toLocaleString()}</strong>
        </div>
        <div className="orders-ops-metric">
          <span>Avg Order</span>
          <strong>{fmt(avgOrderValue)}</strong>
        </div>
        {shippingExceptions > 0 ? (
          <div className="orders-ops-metric is-alert">
            <span>Ship Exceptions</span>
            <strong>{shippingExceptions.toLocaleString()}</strong>
          </div>
        ) : null}
      </div>

      {/* ── Status Tabs ──────────────────────────────────────── */}
      <div className="orders-ops-tabs">
        {visibleOrderTabs.map(tab => {
          const count = orderTabCount(tab.id);
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setOrderTab(tab.id)}
              className={orderTab === tab.id ? 'is-active' : ''}
            >
              {tab.label} <span style={{ fontSize: 11, opacity: 0.7 }}>({count})</span>
            </button>
          );
        })}
      </div>

      {/* ── Compact Filter Bar ────────────────────────────────── */}
      <div className="orders-ops-filterbar">
        <div className="orders-ops-search-wrap">
          <SearchInput value={search} onChange={setSearch} placeholder={searchPlaceholder} />
        </div>
        <select value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} style={inputStyle}>
          <option value="all">All dates</option>
          <option value="today">Today</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
        </select>
        <button
          type="button"
          className={`orders-ops-filter-toggle${showExtraFilters ? ' is-active' : ''}`}
          onClick={() => setShowExtraFilters((v) => !v)}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
          </svg>
          Filters {activeFilterCount > 0 ? `(${activeFilterCount})` : ''}
        </button>
        <button
          type="button"
          className={`orders-ops-refresh${loading ? ' is-loading' : ''}`}
          onClick={() => load(detail?.id || null)}
          title="Refresh"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
        </button>

        <div className={`orders-ops-extra-filters${showExtraFilters ? ' is-open' : ''}`}>
          <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)} style={inputStyle} disabled={!!source}>
            <option value="all">All platforms</option>
            <option value="whatnot">Whatnot Live</option>
            <option value="tiktok_live">TikTok Live</option>
            <option value="tiktok_shop">TikTok Shop</option>
            <option value="affiliate">Partner / Affiliate</option>
          </select>
          <select value={affiliateFilter} onChange={(e) => setAffiliateFilter(e.target.value)} style={inputStyle}>
            <option value="all">All partners</option>
            {affiliateOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select value={sessionFilter} onChange={(e) => setSessionFilter(e.target.value)} style={inputStyle}>
            <option value="all">All sessions</option>
            {mergedSessionOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={inputStyle}>
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
            <option value="shipped">Shipped</option>
            <option value="cancel">Cancelled</option>
          </select>
        </div>
      </div>

      {/* ── Orders Table — now above the fold ─────────────────── */}
      <div className="orders-ops-table">
      <TableShell footer={`${rows.length} shown${data?.total_count ? ` of ${Number(data.total_count).toLocaleString()}` : ''}`}>
        <Thead cols={COLS} />
        <tbody>
          {(loading || rows.length === 0) && <EmptyRow cols={COLS.length} loading={loading} />}
          {!loading && rows.map((r) => {
            const badge = displayStateBadge(r);
            const fulfillment = FULFILLMENT_MAP[r.fulfillment_status] || FULFILLMENT_MAP.pending;
            const payment = PAYMENT_MAP[r.payment_status] || PAYMENT_MAP.unpaid;
            return (
              <tr key={r.id} onClick={() => setDetail(r)}>
                <td>
                  <div style={{ display: 'grid', gap: 4 }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 800 }}>{r.name}</span>
                    <span style={{ color: '#697386', fontSize: 12 }}>{platformLabel(platformValue(r))} · {fmtDate(r.date_order)}</span>
                  </div>
                </td>
                <td>
                  {r.partner_id_name ? <CustomerLink username={r.whatnot_buyer_username} customerId={r.customer_id} label={r.partner_id_name} onOpen={setCustomerPeek} /> : (
                    <CustomerLink username={r.whatnot_buyer_username} customerId={r.customer_id} label={r.whatnot_buyer_username ? `@${r.whatnot_buyer_username}` : '—'} onOpen={setCustomerPeek} />
                  )}
                </td>
                <td><Badge custom={badge} /></td>
                <td><Badge custom={payment} /></td>
                <td><Badge custom={fulfillment} /></td>
                <td style={{ textAlign: 'right', fontWeight: 800, color: '#1a1f36' }}>{fmt(r.amount_total)}</td>
                <td onClick={(event) => event.stopPropagation()}>
                  <div className="orders-ops-actions">
                    <button type="button" disabled={r.payment_status === 'paid' || r.state === 'cancel' || actionBusyId === `${r.id}-paid`} onClick={() => updateOrderAction(r, 'paid')}>
                      Paid
                    </button>
                    <button type="button" disabled={r.fulfillment_status === 'shipped' || r.state === 'cancel' || actionBusyId === `${r.id}-shipped`} onClick={() => updateOrderAction(r, 'shipped')}>
                      Ship
                    </button>
                    <button type="button" className="danger" disabled={r.state === 'cancel' || actionBusyId === `${r.id}-cancel`} onClick={() => updateOrderAction(r, 'cancel')}>
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
	      </TableShell>
        {data?.has_more ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '14px 0 4px' }}>
            <button
              type="button"
              className="orders-ops-refresh"
              disabled={loading}
              onClick={() => load(null, true, data?.rows?.length || 0)}
              style={{ width: 'auto', minWidth: 140, padding: '9px 14px' }}
            >
              Load more
            </button>
          </div>
        ) : null}
	      </div>

      {/* ── Collapsible Insights ──────────────────────────────── */}
      <button
        type="button"
        className={`orders-ops-insights-toggle${showInsights ? ' is-open' : ''}`}
        onClick={() => setShowInsights((v) => !v)}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9" />
        </svg>
        {showInsights ? 'Hide Insights' : 'Show Insights'} — Sales Mix · Sessions · Top Buyers
      </button>

      <div className={`orders-ops-insights${showInsights ? ' is-open' : ''}`}>
        <div className="orders-ops-insights-inner">
          <div className="orders-ops-insights-grid">
            {/* Sales Mix */}
            <section className="orders-ops-insight-panel">
              <div className="orders-ops-insight-eyebrow">Sales Mix</div>
              <div className="orders-ops-insight-title">Platform performance</div>
              <div className="orders-ops-insight-rows">
                {platformBreakdown.length ? platformBreakdown.map((item) => (
                  <div key={item.id} className="orders-ops-insight-row">
                    <div>
                      <div className="orders-ops-insight-row-label">{item.label}</div>
                      <div className="orders-ops-insight-row-sub">{item.count} orders · {item.pending} pending</div>
                    </div>
                    <div className="orders-ops-insight-row-value">{fmt(item.revenue)}</div>
                  </div>
                )) : <div style={{ fontSize: 13, color: '#697386', padding: '8px 0' }}>No orders in the current filter.</div>}
              </div>
            </section>

            {/* Session View */}
            <section className="orders-ops-insight-panel">
              <div className="orders-ops-insight-eyebrow">Session View</div>
              <div className="orders-ops-insight-title">Top sessions</div>
              <div className="orders-ops-insight-rows">
                {sessionBreakdown.length ? sessionBreakdown.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSessionFilter(item.id)}
                    className={`orders-ops-insight-row${sessionFilter === item.id ? ' is-active' : ''}`}
                  >
                    <div>
                      <div className="orders-ops-insight-row-label">{item.label}</div>
                      <div className="orders-ops-insight-row-sub">{item.count} orders · paid {fmt(item.paid)}</div>
                    </div>
                    <div className="orders-ops-insight-row-value">{fmt(item.revenue)}</div>
                  </button>
                )) : <div style={{ fontSize: 13, color: '#697386', padding: '8px 0' }}>No session-linked orders in this filter.</div>}
              </div>
            </section>

            {/* Buyer Signal */}
            <section className="orders-ops-insight-panel">
              <div className="orders-ops-insight-eyebrow">Buyer Signal</div>
              <div className="orders-ops-insight-title">Top buyers</div>
              <div className="orders-ops-insight-rows">
                {topBuyers.length ? topBuyers.map((item) => (
                  <div key={item.label} className="orders-ops-insight-row">
                    <div>
                      <div className="orders-ops-insight-row-label">{item.label}</div>
                      <div className="orders-ops-insight-row-sub">{item.count} orders</div>
                    </div>
                    <div className="orders-ops-insight-row-value">{fmt(item.revenue)}</div>
                  </div>
                )) : <div style={{ fontSize: 13, color: '#697386', padding: '8px 0' }}>No buyer data in the current slice.</div>}
              </div>
              <div style={{ marginTop: 14, paddingTop: 10, borderTop: '1px solid #eef2f7', display: 'grid', gap: 4 }}>
                <div style={{ fontSize: 11, color: '#697386' }}>Paid revenue</div>
                <div style={{ fontSize: 22, fontWeight: 900, color: '#1a1f36', letterSpacing: '-0.03em' }}>{fmt(paidRevenue)}</div>
              </div>
            </section>
          </div>
        </div>
      </div>

      {detail ? (
        <OrderDetailPanel
          order={detail}
          onClose={() => setDetail(null)}
          onSaved={(updated) => load(updated?.id || detail.id)}
          onOpenCustomer={setCustomerPeek}
          buyerLabel={buyerLabel}
        />
      ) : null}
      {customerPeek ? (
        <CustomerProfileDrawer
          customerId={customerPeek.customerId}
          username={customerPeek.username}
          onClose={() => setCustomerPeek(null)}
        />
      ) : null}
    </div>
  );
}
