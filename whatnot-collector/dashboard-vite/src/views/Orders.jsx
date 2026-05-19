import { useState, useEffect, useCallback } from 'react';
import StatCard from '../components/StatCard';
import { fetchApi, postApi } from '../hooks/useApi';

const fmt = (n) => (n == null ? '—' : `$${Number(n).toFixed(2)}`);
const fmtPct = (n) => (n == null ? '—' : `${Number(n).toFixed(1)}%`);
const marginColor = (m) => {
  if (m == null) return 'var(--text-muted)';
  if (m >= 30) return 'var(--accent-green)';
  if (m >= 15) return 'var(--accent-yellow)';
  return 'var(--accent-coral)';
};

function BuyerLines({ groupId }) {
  const [lines, setLines] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApi(`/api/buyer_lines?group_id=${groupId}`)
      .then(d => setLines(d.rows || []))
      .catch(() => setLines([]))
      .finally(() => setLoading(false));
  }, [groupId]);

  if (loading) return <div style={{ padding: '12px 24px', color: 'var(--text-muted)', fontSize: 13 }}>Loading lines…</div>;
  if (!lines?.length) return <div style={{ padding: '12px 24px', color: 'var(--text-muted)', fontSize: 13 }}>No line items found.</div>;

  return (
    <div style={{ padding: '0 0 8px 0', background: 'var(--bg-card)', borderTop: '1px solid var(--border)' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--bg-main)' }}>
            {['Lot #', 'Product', 'SKU / Barcode', 'Revenue', 'Cost', 'Fees', 'Profit', 'Margin', 'Sold At'].map(h => (
              <th key={h} style={{ padding: '6px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => (
            <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
              <td style={{ padding: '6px 12px', color: 'var(--text-muted)' }}>{l.lot_number || '—'}</td>
              <td style={{ padding: '6px 12px', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.product_name || '—'}</td>
              <td style={{ padding: '6px 12px', color: 'var(--text-muted)', fontFamily: 'monospace' }}>{l.sku || l.barcode || '—'}</td>
              <td style={{ padding: '6px 12px' }}>{fmt(l.allocated_revenue ?? l.sale_price)}</td>
              <td style={{ padding: '6px 12px', color: 'var(--text-muted)' }}>{fmt(l.cost_price)}</td>
              <td style={{ padding: '6px 12px', color: 'var(--text-muted)' }}>{fmt(l.fees)}</td>
              <td style={{ padding: '6px 12px', color: (l.profit || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-coral)', fontWeight: 600 }}>{fmt(l.profit)}</td>
              <td style={{ padding: '6px 12px', color: marginColor(l.margin_pct) }}>{fmtPct(l.margin_pct)}</td>
              <td style={{ padding: '6px 12px', color: 'var(--text-muted)' }}>{l.sold_at ? new Date(l.sold_at).toLocaleString() : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Orders() {
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState('');
  const [search, setSearch] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [creating, setCreating] = useState(null); // group_id being created
  const [error, setError] = useState(null);
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Debounce search
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 400);
    return () => clearTimeout(t);
  }, [search]);

  // Load session list
  useEffect(() => {
    fetchApi('/api/sessions/list')
      .then(d => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  const loadOrders = useCallback(() => {
    setLoading(true);
    setError(null);
    const params = new URLSearchParams();
    if (selectedSession) params.set('session_id', selectedSession);
    if (debouncedSearch) params.set('q', debouncedSearch);
    fetchApi(`/api/orders?${params}`)
      .then(d => setData(d))
      .catch(e => setError(e.message || 'Failed to load orders'))
      .finally(() => setLoading(false));
  }, [selectedSession, debouncedSearch]);

  useEffect(() => { loadOrders(); }, [loadOrders]);

  const toggleExpand = (id) => setExpanded(e => e === id ? null : id);

  const ensureSaleOrder = async (groupId) => {
    setCreating(groupId);
    try {
      const result = await postApi('/api/orders/ensure_sale_order', { group_id: groupId });
      if (result.ok) {
        loadOrders();
      } else {
        alert(`Failed: ${result.error}`);
      }
    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      setCreating(null);
    }
  };

  const rows = data?.rows || [];

  return (
    <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <StatCard label="Total Orders" value={data?.total_orders ?? '—'} icon="📦" />
        <StatCard label="Total Revenue" value={data ? fmt(data.total_revenue) : '—'} icon="💰" color="var(--accent-green)" />
        <StatCard label="Total Cost" value={data ? fmt(data.total_cost) : '—'} icon="🏷️" color="var(--text-muted)" />
        <StatCard label="Total Profit" value={data ? fmt(data.total_profit) : '—'} icon="📈" color="var(--accent-green)" />
        <StatCard label="Avg Margin" value={data ? fmtPct(data.avg_margin) : '—'} icon="%" color={marginColor(data?.avg_margin)} />
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
        <select
          value={selectedSession}
          onChange={e => { setSelectedSession(e.target.value); setExpanded(null); }}
          style={{ background: 'var(--bg-card)', color: 'var(--text-main)', border: '1px solid var(--border)', borderRadius: 6, padding: '7px 12px', fontSize: 13, minWidth: 200 }}
        >
          <option value="">All Sessions</option>
          {sessions.map(s => (
            <option key={s.id} value={s.id}>{s.name || `Session #${s.id}`}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Search buyer username…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ background: 'var(--bg-card)', color: 'var(--text-main)', border: '1px solid var(--border)', borderRadius: 6, padding: '7px 12px', fontSize: 13, flex: 1, minWidth: 200 }}
        />
        <button
          onClick={loadOrders}
          style={{ background: 'var(--accent-blue)', color: '#fff', border: 'none', borderRadius: 6, padding: '7px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 600 }}
        >
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'var(--accent-coral)', color: '#fff', padding: '8px 14px', borderRadius: 6, fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Table */}
      <div style={{ background: 'var(--bg-card)', borderRadius: 8, border: '1px solid var(--border)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ background: 'var(--bg-main)', borderBottom: '2px solid var(--border)' }}>
              <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}></th>
              <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}>Buyer</th>
              <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600 }}>Session</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>Items</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>Revenue</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>Cost</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>Profit</th>
              <th style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 600 }}>Margin</th>
              <th style={{ padding: '10px 14px', textAlign: 'center', color: 'var(--text-muted)', fontWeight: 600 }}>Sale Order</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={9} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={9} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>No orders found.</td></tr>
            )}
            {!loading && rows.map(row => (
              <>
                <tr
                  key={row.id}
                  onClick={() => toggleExpand(row.id)}
                  style={{ borderTop: '1px solid var(--border)', cursor: 'pointer', background: expanded === row.id ? 'var(--bg-main)' : 'transparent', transition: 'background 0.15s' }}
                >
                  <td style={{ padding: '10px 14px', color: 'var(--text-muted)', fontSize: 11 }}>
                    {expanded === row.id ? '▼' : '▶'}
                  </td>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>
                    @{row.buyer_username}
                    {row.partner_id_name && (
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 400 }}>{row.partner_id_name}</div>
                    )}
                  </td>
                  <td style={{ padding: '10px 14px', color: 'var(--text-muted)', fontSize: 12 }}>
                    {row.session_id_name || `#${row.session_id}`}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right' }}>{row.total_items ?? 0}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600 }}>{fmt(row.total_revenue)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-muted)' }}>{fmt(row.total_cost)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 600, color: (row.total_profit || 0) >= 0 ? 'var(--accent-green)' : 'var(--accent-coral)' }}>
                    {fmt(row.total_profit)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'right', color: marginColor(row.overall_margin) }}>
                    {fmtPct(row.overall_margin)}
                  </td>
                  <td style={{ padding: '10px 14px', textAlign: 'center' }} onClick={e => e.stopPropagation()}>
                    {row.sale_order_id ? (
                      <span style={{ background: 'var(--accent-green)', color: '#fff', padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 600 }}>
                        {row.sale_order_id_name || `SO#${row.sale_order_id}`}
                      </span>
                    ) : (
                      <button
                        onClick={() => ensureSaleOrder(row.id)}
                        disabled={creating === row.id}
                        style={{
                          background: 'var(--accent-blue)', color: '#fff', border: 'none',
                          borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontSize: 11, fontWeight: 600,
                          opacity: creating === row.id ? 0.6 : 1,
                        }}
                      >
                        {creating === row.id ? 'Creating…' : '+ Create SO'}
                      </button>
                    )}
                  </td>
                </tr>
                {expanded === row.id && (
                  <tr key={`${row.id}-lines`}>
                    <td colSpan={9} style={{ padding: 0 }}>
                      <BuyerLines groupId={row.id} />
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
        {rows.length > 0 && (
          <div style={{ padding: '8px 14px', borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)' }}>
            {rows.length} order{rows.length !== 1 ? 's' : ''}
            {selectedSession && ` in this session`}
          </div>
        )}
      </div>
    </div>
  );
}
