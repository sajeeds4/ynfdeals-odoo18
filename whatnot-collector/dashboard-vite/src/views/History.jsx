/**
 * History — Browse past stream sessions.
 * Select any ended session to see its full stats: revenue, profit,
 * winners list, top products, and top buyers.
 */
import { useState, useEffect } from 'react';
import { fetchApi } from '../hooks/useApi';
import StatCard from '../components/StatCard';
import DataTable from '../components/DataTable';

function fmt$(n) { return '$' + Number(n || 0).toFixed(2); }
function calcPlatformFee(revenue) { return Number(revenue || 0) * 0.06; }
function fmtBool(v) { return v ? 'Yes' : 'No'; }
function fmtTime(t) {
  if (!t) return '—';
  try { return new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return t; }
}
function fmtDate(t) {
  if (!t) return '—';
  try { return new Date(t).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch { return t; }
}
function fmtDuration(start, end) {
  if (!start || !end) return '—';
  const ms = new Date(end) - new Date(start);
  if (ms <= 0) return '—';
  const m = Math.floor(ms / 60000);
  const h = Math.floor(m / 60);
  return h > 0 ? `${h}h ${m % 60}m` : `${m}m`;
}

const WINNER_COLS = [
  { key: 'sold_at', label: 'Time', width: '90px', render: v => <span className="mono text-xs">{fmtTime(v)}</span> },
  { key: 'winner_username', label: 'Winner', render: v => <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>{v}</span> },
  {
    key: 'product_name', label: 'Product',
    render: v => v ? (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {String(v).split('\n').map((line, i) => (
          <span key={i} style={{ fontSize: i === 0 ? '0.85em' : '0.78em', color: i === 0 ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{line}</span>
        ))}
      </div>
    ) : '—'
  },
  { key: 'lot_number', label: 'Lot #', width: '55px' },
  { key: 'sale_price', label: 'Price', width: '80px', align: 'right', render: v => <span className="text-amber font-bold">{fmt$(v)}</span> },
  { key: 'fees', label: 'Fees', width: '70px', align: 'right', render: v => v != null ? <span className="text-muted">{fmt$(v)}</span> : '—' },
  { key: 'profit', label: 'Profit', width: '80px', align: 'right', render: v => v != null ? <span style={{ color: v >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)', fontWeight: 600 }}>{fmt$(v)}</span> : '—' },
];

const PRODUCT_COLS = [
  { key: 'product_name', label: 'Product' },
  { key: 'times_sold', label: 'Sold', width: '55px', align: 'right' },
  { key: 'total_revenue', label: 'Revenue', width: '90px', align: 'right', render: v => <span className="text-amber">{fmt$(v)}</span> },
];

const BUYER_COLS = [
  { key: 'buyer_username', label: 'Buyer', render: v => <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>{v}</span> },
  { key: 'total_lots', label: 'Lots', width: '55px', align: 'right' },
  { key: 'total_revenue', label: 'Spent', width: '90px', align: 'right', render: v => <span className="text-amber font-bold">{fmt$(v)}</span> },
];

const REPORT_COLS = [
  { key: 'username', label: 'Username', render: v => <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>{v ? `@${v}` : '—'}</span> },
  { key: 'lot_number', label: 'Lot #' },
  { key: 'item_count', label: 'Items', width: '60px', align: 'right' },
  {
    key: 'product_names', label: 'Product Names',
    render: v => <span style={{ color: 'var(--text-primary)' }}>{v || '—'}</span>,
  },
  { key: 'sold_at', label: 'Sold At', width: '170px', render: v => <span className="mono text-xs">{v ? new Date(v).toLocaleString() : '—'}</span> },
  { key: 'profile_made', label: 'Profile Made', width: '95px', render: v => <span style={{ color: v ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>{fmtBool(v)}</span> },
  { key: 'profile_created_at', label: 'Profile Created', width: '170px', render: v => <span className="mono text-xs">{v ? new Date(v).toLocaleString() : '—'}</span> },
  { key: 'sale_order_made', label: 'SO Made', width: '80px', render: v => <span style={{ color: v ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>{fmtBool(v)}</span> },
];

export default function History() {
  const [sessions, setSessions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [winners, setWinners] = useState([]);
  const [products, setProducts] = useState([]);
  const [buyers, setBuyers] = useState([]);
  const [reportRows, setReportRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState('winners');

  // Load session list on mount
  useEffect(() => {
    fetchApi('/api/history/company_sessions')
      .then(d => {
        const ended = (d.sessions || []).filter(s => s.status === 'ended');
        setSessions(ended);
        if (ended.length > 0) loadSession(ended[0]);
      })
      .catch(() => {});
  }, []);

  async function loadSession(session) {
    setSelected(session);
    setLoading(true);
    setWinners([]);
    setProducts([]);
    setBuyers([]);
    setReportRows([]);
    try {
      const detail = await fetchApi(`/api/history/company_detail?stream_id=${session.stream_id || session.id}`);
      setWinners(detail.winners || []);
      setProducts(detail.products || []);
      setBuyers(detail.buyers || []);
      setReportRows(detail.report_rows || []);
    } catch {}
    setLoading(false);
  }

  const avgPrice = selected && selected.total_products_sold > 0
    ? selected.total_revenue / selected.total_products_sold : 0;
  const platformFee = selected?.platform_fee ?? calcPlatformFee(selected?.total_revenue);

  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ minWidth: 0 }}>
        {!selected && (
          <div className="panel" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
            <p>No ended stream selected yet.</p>
          </div>
        )}

        {selected && (
          <>
            {/* Header */}
            <div className="panel animate-in" style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
                <div>
                  <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800 }}>{selected.name}</h2>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 3 }}>
                    {fmtDate(selected.start_time)}
                    {selected.end_time && <> · Duration: {fmtDuration(selected.start_time, selected.end_time)}</>}
                  </div>
                </div>
                <span className="chip chip--emerald" style={{ fontSize: '0.72rem' }}>✓ Ended</span>
              </div>
            </div>

            {/* KPI cards */}
            <div className="sv-metrics" style={{ marginBottom: 12 }}>
              <StatCard label="Products Sold" value={selected.total_products_sold || 0} icon="📦" />
              <StatCard label="Revenue" value={fmt$(selected.total_revenue)} icon="💰" color="var(--accent-amber)" />
              <StatCard label="Platform Fee (6%)" value={fmt$(platformFee)} icon="🏦" color="var(--text-secondary)" />
              <StatCard label="Fees" value={fmt$(selected.total_fees)} icon="🏦" color="var(--text-secondary)" />
              <StatCard label="Profit" value={fmt$(selected.total_profit)} icon="📈" color={Number(selected.total_profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'} />
              <StatCard label="Avg Price" value={fmt$(avgPrice)} icon="🏷️" />
              <StatCard label="Lots Sold" value={selected.total_lots_sold || winners.length} icon="🎯" />
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
              {[['winners', `🏅 Winners (${winners.length})`], ['products', `📦 Products (${products.length})`], ['buyers', `👥 Buyers (${buyers.length})`], ['report', `🧾 Report (${reportRows.length})`]].map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`btn ${tab === key ? 'btn--amber' : ''}`}
                  style={{ padding: '6px 14px', fontSize: '0.82rem', background: tab === key ? undefined : 'var(--bg-elevated)' }}
                >
                  {label}
                </button>
              ))}
            </div>

            {loading && <p className="text-muted text-sm">Loading…</p>}

            {!loading && tab === 'winners' && (
              <div className="panel animate-in">
                <DataTable columns={WINNER_COLS} rows={winners} emptyText="No winners recorded" maxHeight="60vh" />
              </div>
            )}
            {!loading && tab === 'products' && (
              <div className="panel animate-in">
                <DataTable columns={PRODUCT_COLS} rows={products} emptyText="No product data" maxHeight="60vh" />
              </div>
            )}
            {!loading && tab === 'buyers' && (
              <div className="panel animate-in">
                <DataTable columns={BUYER_COLS} rows={buyers} emptyText="No buyer data" maxHeight="60vh" />
              </div>
            )}
            {!loading && tab === 'report' && (
              <div className="panel animate-in">
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 10 }}>
                  End-of-stream report for `ynfdeals`: username, lot number, item count, product names, sold time, and profile/order status.
                </div>
                <DataTable columns={REPORT_COLS} rows={reportRows} emptyText="No report rows yet" maxHeight="60vh" />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
