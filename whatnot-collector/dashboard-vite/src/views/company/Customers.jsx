import { useEffect, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  EmptyRow,
  FilterBar,
  GhostBtn,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  SlidePanel,
  TableShell,
  Thead,
  fmt,
  fmtDate,
  fmtDt,
  clrProfit,
} from './utils';

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '8px 10px',
  fontSize: 13,
  width: '100%',
};

const cardStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-lg)',
  background: 'var(--bg-panel)',
  boxShadow: '0 12px 30px rgba(15, 23, 42, 0.04)',
};

const sectionTitleStyle = {
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
  color: 'var(--text-secondary)',
};

function customerInitials(customer) {
  const name = String(customer?.name || customer?.display_name || customer?.whatnot_username || customer?.tiktok_live_identity || customer?.tiktok_shop_identity || 'C').trim();
  const parts = name.replace(/^@/, '').split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2)).toUpperCase();
}

function platformLabel(value) {
  return String(value || 'unknown').replaceAll('_', ' ');
}

function InfoRow({ label, value, mono = false }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '120px minmax(0, 1fr)', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
      <div style={{ color: 'var(--text-secondary)', fontSize: 12, fontWeight: 650 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 650, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: mono ? 'var(--font-mono)' : undefined }}>{value || '—'}</div>
    </div>
  );
}

function StatTile({ label, value, sub, color }) {
  return (
    <div style={{ ...cardStyle, padding: 12, minHeight: 70 }}>
      <div style={{ ...sectionTitleStyle, fontSize: 10 }}>{label}</div>
      <div style={{ marginTop: 6, fontSize: 20, fontWeight: 850, color: color || 'var(--text-primary)' }}>{value}</div>
      {sub ? <div style={{ marginTop: 2, fontSize: 11, color: 'var(--text-secondary)' }}>{sub}</div> : null}
    </div>
  );
}

function PlatformPill({ label, value }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      gap: 10,
      alignItems: 'center',
      border: '1px solid var(--border-default)',
      borderRadius: 999,
      padding: '7px 10px',
      background: value ? 'rgba(108, 71, 255, 0.07)' : 'var(--bg-elevated)',
      minWidth: 0,
    }}>
      <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 800 }}>{label}</span>
      <span style={{ fontSize: 12, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value ? `@${value}` : '—'}</span>
    </div>
  );
}

function MiniProductList({ products }) {
  const rows = (products || []).slice(0, 8);
  if (!rows.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No product history yet.</div>;
  return (
    <div style={{ display: 'grid', gap: 8 }}>
      {rows.map((row, index) => (
        <div key={`${row.product_name}-${index}`} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 10, alignItems: 'center' }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 750, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.product_name || '—'}</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{row.purchase_count || 0} bought · last {fmtDate(row.last_sold_at)}</div>
          </div>
          <div style={{ textAlign: 'right', fontSize: 12, fontWeight: 800, color: clrProfit(row.total_profit) }}>{fmt(row.total_profit)}</div>
        </div>
      ))}
    </div>
  );
}

function CustomerOrders({ partnerId }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetchApi(`/api/customers/orders?scope=company&partner_id=${partnerId}`)
      .then((result) => setData(result))
      .catch(() => setData({ orders: [] }));
  }, [partnerId]);

  if (!data) return <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading orders...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
        <KpiCard label="Sales Orders" value={data.orders?.length ?? 0} icon="📋" />
        <KpiCard label="Total Spent" value={fmt(data.total_spent)} icon="💰" color="var(--accent-amber)" />
        <KpiCard label="Profit" value={fmt(data.total_profit)} icon="📈" color={clrProfit(data.total_profit)} />
      </div>
      <TableShell footer={`${data.orders?.length || 0} order${data.orders?.length === 1 ? '' : 's'}`}>
        <Thead cols={[
          { label: 'Order #' },
          { label: 'Date' },
          { label: 'Status' },
          { label: 'Session' },
          { label: 'Products' },
          { label: 'Profit', align: 'right' },
          { label: 'Amount', align: 'right' },
        ]} />
        <tbody>
          {!(data.orders || []).length ? <EmptyRow cols={7} msg="No company orders found." /> : data.orders.map((order) => (
            <tr key={order.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{order.name}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDate(order.date_order)}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{order.state}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{order.whatnot_session_id_name || '—'}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{order.product_names || '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: clrProfit(order.order_profit), fontWeight: 700 }}>{fmt(order.order_profit)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(order.amount_total)}</td>
            </tr>
          ))}
        </tbody>
      </TableShell>
    </div>
  );
}

function CustomerEditor({ detail, onSaved }) {
  const [form, setForm] = useState({
    display_name: detail.name || '',
    email: detail.email || '',
    phone: detail.phone || '',
    address: detail.address || '',
    notes: detail.notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  async function save() {
    setSaving(true);
    setMessage('');
    try {
      const result = await postApi('/api/customers/update', {
        customer_id: detail.id,
        display_name: form.display_name,
        email: form.email,
        phone: form.phone,
        address: form.address,
        notes: form.notes,
      });
      setMessage('Customer updated.');
      onSaved(result.customer || null);
    } catch (err) {
      setMessage(err.message || 'Unable to update customer.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 14, display: 'grid', gap: 12 }}>
      <div style={{ fontWeight: 700 }}>Customer Management</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Display Name</span>
          <input value={form.display_name} onChange={(e) => setForm((v) => ({ ...v, display_name: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Email</span>
          <input value={form.email} onChange={(e) => setForm((v) => ({ ...v, email: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Phone</span>
          <input value={form.phone} onChange={(e) => setForm((v) => ({ ...v, phone: e.target.value }))} style={inputStyle} />
        </label>
        <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Address</span>
          <textarea value={form.address} onChange={(e) => setForm((v) => ({ ...v, address: e.target.value }))} rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
        </label>
        <div style={{ display: 'grid', gap: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Whatnot Username</span>
          <div style={{ ...inputStyle, color: 'var(--text-secondary)' }}>@{detail.whatnot_username || '—'}</div>
        </div>
        <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Notes</span>
          <textarea value={form.notes} onChange={(e) => setForm((v) => ({ ...v, notes: e.target.value }))} rows={4} style={{ ...inputStyle, resize: 'vertical' }} />
        </label>
      </div>
      {message ? <div style={{ fontSize: 12, color: message.includes('Unable') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{message}</div> : null}
      <div style={{ display: 'flex', gap: 8 }}>
        <PrimaryBtn onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save Customer'}</PrimaryBtn>
      </div>
    </div>
  );
}

export default function Customers() {
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [platform, setPlatform] = useState('all');
  const [data, setData] = useState({ rows: [] });
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [editing, setEditing] = useState(false);

  function load(query, keepDetailId = null, nextPlatform = platform) {
    setLoading(true);
    const params = new URLSearchParams({ scope: 'company' });
    if (query) params.set('q', query);
    if (nextPlatform && nextPlatform !== 'all') params.set('platform', nextPlatform);
    fetchApi(`/api/customers?${params}`)
      .then((result) => {
        setData(result);
        if (keepDetailId) {
          const fresh = (result.rows || []).find((row) => row.id === keepDetailId);
          if (fresh) setDetail(fresh);
        }
      })
      .catch(() => setData({ rows: [] }))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    load(debounced, null, platform);
  }, [debounced, platform]);

  const rows = data.rows || [];

  useEffect(() => {
    if (!detail?.id) {
      setDetailData(null);
      return;
    }
    setDetailData(null);
    fetchApi(`/api/customers/detail?scope=company&customer_id=${detail.id}`)
      .then((result) => setDetailData(result))
      .catch(() => setDetailData({ customer: detail, sessions: [], products: [], summary: {} }));
  }, [detail?.id]);

  const activeCustomer = detailData?.customer || detail;
  const summary = detailData?.summary || {};
  const customerSessions = detailData?.sessions || [];
  const customerProducts = detailData?.products || [];
  const customerIdentities = detailData?.identities || [];
  const selectedId = activeCustomer?.id || detail?.id || null;
  const contactScore = [
    activeCustomer?.name || activeCustomer?.display_name,
    activeCustomer?.email,
    activeCustomer?.phone,
    activeCustomer?.address,
  ].filter(Boolean).length;
  const platformBadges = [
    ['Whatnot', activeCustomer?.whatnot_identity || detail?.whatnot_identity],
    ['TikTok Live', activeCustomer?.tiktok_live_identity || detail?.tiktok_live_identity],
    ['TikTok Shop', activeCustomer?.tiktok_shop_identity || detail?.tiktok_shop_identity],
  ];
  const selectedName = activeCustomer?.name || activeCustomer?.display_name || activeCustomer?.whatnot_username || activeCustomer?.tiktok_live_identity || activeCustomer?.tiktok_shop_identity || 'Select a customer';

  useEffect(() => {
    if (!detail && rows.length) setDetail(rows[0]);
  }, [rows, detail]);

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
        <div>
          <div style={{ ...sectionTitleStyle }}>Customer profiles</div>
          <h2 style={{ margin: '4px 0 0', fontSize: 24, lineHeight: 1.1 }}>Customers</h2>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 5 }}>
            Unified buyer records across TikTok Shop, TikTok Live, Whatnot, in-house sales, and imported labels.
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(110px, 1fr))', gap: 8, minWidth: 520 }}>
          <StatTile label="Visible" value={rows.length.toLocaleString()} />
          <StatTile label="Phone" value={rows.filter((row) => row.phone).length.toLocaleString()} color="var(--accent-emerald)" />
          <StatTile label="Email" value={rows.filter((row) => row.email).length.toLocaleString()} color="var(--accent-blue)" />
          <StatTile label="Address" value={rows.filter((row) => row.address).length.toLocaleString()} color="var(--accent-amber)" />
        </div>
      </div>

      <div style={{ ...cardStyle, padding: 12 }}>
        <FilterBar>
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, username, phone, email..." />
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {[
              ['all', 'All'],
              ['whatnot', 'Whatnot'],
              ['tiktok_live', 'TikTok Live'],
              ['tiktok_shop', 'TikTok Shop'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setPlatform(value)}
                style={{
                  border: '1px solid var(--border-default)',
                  borderRadius: 999,
                  padding: '8px 12px',
                  fontSize: 12,
                  fontWeight: 800,
                  background: platform === value ? 'var(--text-primary)' : 'var(--bg-panel)',
                  color: platform === value ? 'var(--bg-panel)' : 'var(--text-primary)',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <PrimaryBtn onClick={() => load(search.trim(), detail?.id || null)}>Refresh</PrimaryBtn>
        </FilterBar>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(440px, 0.92fr) minmax(520px, 1.08fr)', gap: 14, alignItems: 'start' }}>
        <div style={{ ...cardStyle, overflow: 'hidden' }}>
          <div style={{ padding: '13px 14px', borderBottom: '1px solid var(--border-default)', display: 'flex', justifyContent: 'space-between', gap: 10 }}>
            <div>
              <div style={{ fontWeight: 850 }}>Buyer directory</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{loading ? 'Loading customers...' : `${rows.length.toLocaleString()} matching customers`}</div>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', alignSelf: 'center' }}>Click a row</div>
          </div>
          <div style={{ maxHeight: 'calc(100vh - 310px)', overflow: 'auto' }}>
            {!loading && rows.length === 0 ? (
              <div style={{ padding: 24, color: 'var(--text-secondary)', fontSize: 13 }}>No company customers found.</div>
            ) : null}
            {loading ? (
              <div style={{ padding: 24, color: 'var(--text-secondary)', fontSize: 13 }}>Loading customers...</div>
            ) : rows.map((row) => {
              const rowSelected = String(row.id) === String(selectedId);
              const rowName = row.name || row.display_name || row.whatnot_identity || row.tiktok_live_identity || row.tiktok_shop_identity || 'Unnamed customer';
              return (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => { setDetail(row); setEditing(false); }}
                  style={{
                    width: '100%',
                    border: 0,
                    borderBottom: '1px solid var(--border-subtle)',
                    background: rowSelected ? 'rgba(108, 71, 255, 0.08)' : 'transparent',
                    color: 'var(--text-primary)',
                    padding: '11px 14px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    display: 'grid',
                    gridTemplateColumns: '42px minmax(0, 1fr) auto',
                    gap: 11,
                    alignItems: 'center',
                  }}
                >
                  <span style={{
                    width: 38,
                    height: 38,
                    borderRadius: 12,
                    background: rowSelected ? 'var(--accent-primary)' : 'var(--bg-elevated)',
                    color: rowSelected ? '#fff' : 'var(--text-primary)',
                    display: 'grid',
                    placeItems: 'center',
                    fontWeight: 850,
                    border: '1px solid var(--border-default)',
                  }}>{customerInitials(row)}</span>
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: 'block', fontSize: 13, fontWeight: 850, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rowName}</span>
                    <span style={{ display: 'block', marginTop: 3, fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.tiktok_shop_identity ? `TikTok Shop @${row.tiktok_shop_identity}` : row.tiktok_live_identity ? `TikTok Live @${row.tiktok_live_identity}` : row.whatnot_identity ? `Whatnot @${row.whatnot_identity}` : 'No platform username'}
                    </span>
                    <span style={{ display: 'block', marginTop: 3, fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {[row.phone, row.email].filter(Boolean).join(' · ') || row.address || 'No contact stored'}
                    </span>
                  </span>
                  <span style={{ textAlign: 'right' }}>
                    <span style={{ display: 'block', fontSize: 12, fontWeight: 850 }}>{Number(row.sale_order_count || 0).toLocaleString()}</span>
                    <span style={{ display: 'block', fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>orders</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ display: 'grid', gap: 14, position: 'sticky', top: 12 }}>
          {!activeCustomer ? (
            <div style={{ ...cardStyle, padding: 28, color: 'var(--text-secondary)' }}>Select a customer to view their profile.</div>
          ) : (
            <>
              <div style={{ ...cardStyle, padding: 18 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '64px minmax(0, 1fr) auto', gap: 14, alignItems: 'center' }}>
                  <div style={{ width: 60, height: 60, borderRadius: 18, background: 'var(--text-primary)', color: 'var(--bg-panel)', display: 'grid', placeItems: 'center', fontSize: 20, fontWeight: 900 }}>
                    {customerInitials(activeCustomer)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ ...sectionTitleStyle }}>Customer profile</div>
                    <div style={{ fontSize: 24, fontWeight: 900, lineHeight: 1.1, overflowWrap: 'anywhere' }}>{selectedName}</div>
                    <div style={{ marginTop: 7, display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                      {platformBadges.map(([label, value]) => <PlatformPill key={label} label={label} value={value} />)}
                    </div>
                  </div>
                  <div style={{ display: 'grid', justifyItems: 'end', gap: 8 }}>
                    <GhostBtn onClick={() => setEditing((v) => !v)}>{editing ? 'Close editor' : 'Edit'}</GhostBtn>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{contactScore}/4 profile fields</div>
                  </div>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
                <StatTile label="Revenue" value={fmt(summary.total_revenue ?? activeCustomer?.total_revenue ?? activeCustomer?.total_spent)} color="var(--accent-amber)" />
                <StatTile label="Profit / Loss" value={fmt(summary.total_profit ?? activeCustomer?.total_profit)} color={clrProfit(summary.total_profit ?? activeCustomer?.total_profit)} />
                <StatTile label="Orders" value={Number(activeCustomer?.sale_order_count ?? summary.sale_order_count ?? 0).toLocaleString()} />
                <StatTile label="Last Purchase" value={activeCustomer?.last_purchase_at ? fmtDate(activeCustomer.last_purchase_at) : '—'} />
              </div>

              {editing ? (
                <CustomerEditor detail={activeCustomer} onSaved={(updated) => { setEditing(false); load(search.trim(), updated?.id || detail.id); }} />
              ) : (
                <div style={{ ...cardStyle, padding: '14px 16px' }}>
                  <div style={{ ...sectionTitleStyle, marginBottom: 8 }}>Contact</div>
                  <InfoRow label="Name" value={activeCustomer?.name || activeCustomer?.display_name} />
                  <InfoRow label="Email" value={activeCustomer?.email} />
                  <InfoRow label="Phone" value={activeCustomer?.phone} mono />
                  <InfoRow label="Address" value={activeCustomer?.address} />
                  <InfoRow label="Notes" value={activeCustomer?.notes} />
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 0.95fr) minmax(0, 1.05fr)', gap: 14 }}>
                <div style={{ ...cardStyle, padding: 14 }}>
                  <div style={{ ...sectionTitleStyle, marginBottom: 10 }}>Linked identities</div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    {!customerIdentities.length ? <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No linked identities yet.</div> : customerIdentities.map((row, index) => (
                      <div key={`${row.platform}-${row.username}-${index}`} style={{ display: 'grid', gridTemplateColumns: '96px minmax(0, 1fr)', gap: 10, alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <div style={{ fontSize: 11, fontWeight: 850, textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{platformLabel(row.platform)}</div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.username ? `@${row.username}` : (row.platform_user_id || '—')}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{[row.email, row.phone].filter(Boolean).join(' · ') || row.display_name || 'No contact on identity'}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div style={{ ...cardStyle, padding: 14 }}>
                  <div style={{ ...sectionTitleStyle, marginBottom: 10 }}>Top products</div>
                  <MiniProductList products={customerProducts} />
                </div>
              </div>

              <div style={{ ...cardStyle, padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
                  <div>
                    <div style={{ ...sectionTitleStyle }}>Sessions bought in</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{customerSessions.length} sessions with matched auction history</div>
                  </div>
                </div>
                <TableShell footer={`${customerSessions.length} session${customerSessions.length === 1 ? '' : 's'}`}>
                  <Thead cols={[
                    { label: 'Session' },
                    { label: 'Purchases', align: 'right' },
                    { label: 'Revenue', align: 'right' },
                    { label: 'Profit', align: 'right' },
                    { label: 'Last Purchase' },
                  ]} />
                  <tbody>
                    {!customerSessions.length ? <EmptyRow cols={5} msg="No session history found." /> : customerSessions.map((row) => (
                      <tr key={row.id || row.session_name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '8px 14px', fontWeight: 750 }}>{row.session_name || '—'}</td>
                        <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.purchase_count ?? 0}</td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 750 }}>{fmt(row.total_revenue)}</td>
                        <td style={{ padding: '8px 14px', textAlign: 'right', color: clrProfit(row.total_profit), fontWeight: 750 }}>{fmt(row.total_profit)}</td>
                        <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{fmtDt(row.last_sold_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              </div>

              <div style={{ ...cardStyle, padding: 14 }}>
                <div style={{ ...sectionTitleStyle, marginBottom: 10 }}>Order history</div>
                <CustomerOrders partnerId={detail.id} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
