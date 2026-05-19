/**
 * SessionDetail — Full drill-down for a single session.
 * Shows lot-by-lot timeline, revenue chart, top buyers, unsold lots,
 * and bulk sale order creation for all linked buyer groups.
 */
import { useState, useEffect, useMemo } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  LineChart, Line, Area, AreaChart,
} from 'recharts';
import { fmt, fmtDt, fmtPct, clrProfit, clrMargin, KpiCard, SlidePanel } from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';

const fmt$ = (n) => (n == null ? '—' : `$${Number(n).toFixed(2)}`);
const fmtK = (n) => {
  if (n == null) return '—';
  const v = Number(n);
  return Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(2)}`;
};

function ChartTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, padding: '10px 14px', fontSize: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>Lot {label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, display: 'flex', gap: 8, justifyContent: 'space-between' }}>
          <span>{p.name}</span><span style={{ fontWeight: 700 }}>${Number(p.value).toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export default function SessionDetail({ sessionId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('overview');
  const [bulking, setBulking] = useState(false);
  const [bulkResult, setBulkResult] = useState(null);
  const [selectedGroups, setSelectedGroups] = useState(new Set());
  const [customerPeek, setCustomerPeek] = useState(null);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    setBulkResult(null);
    fetchApi(`/api/sessions/${sessionId}/detail`)
      .then((d) => {
        setData(d);
        // Pre-select groups without a sale order
        const noSO = (d.groups || []).filter((g) => !g.sale_order_id).map((g) => g.id);
        setSelectedGroups(new Set(noSO));
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [sessionId]);

  const session = data?.session || {};
  const results = data?.results || [];
  const topBuyers = data?.top_buyers || [];
  const unsold = data?.unsold || [];
  const groups = data?.groups || [];

  const timelineChart = useMemo(() => {
    let cumRevenue = 0;
    return (data?.timeline || []).slice(-40).map((t) => {
      cumRevenue += t.revenue || 0;
      return { lot: t.lot, revenue: t.revenue || 0, profit: t.profit || 0, cum: Math.round(cumRevenue * 100) / 100 };
    });
  }, [data]);

  const noSOCount = groups.filter((g) => !g.sale_order_id).length;

  async function bulkCreateSO() {
    if (selectedGroups.size === 0) return;
    setBulking(true);
    setBulkResult(null);
    try {
      const res = await postApi('/api/sessions/bulk_sale_orders', { group_ids: [...selectedGroups] });
      setBulkResult(res);
      // Reload
      const d = await fetchApi(`/api/sessions/${sessionId}/detail`);
      setData(d);
    } catch (e) {
      setBulkResult({ ok: false, error: e.message });
    } finally {
      setBulking(false);
    }
  }

  const TABS = [
    { id: 'overview', label: '📊 Overview' },
    { id: 'timeline', label: '📈 Timeline' },
    { id: 'buyers', label: '👑 Buyers' },
    { id: 'unsold', label: `⚠ Unsold (${unsold.length})` },
    { id: 'orders', label: `📋 Orders (${groups.length})` },
    { id: 'lots', label: `📦 All Results (${results.length})` },
  ];

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1100,
      background: 'rgba(0,0,0,0.6)',
      display: 'flex', justifyContent: 'flex-end',
    }} onClick={onClose}>
      <div
        style={{
          background: 'var(--bg-page)',
          border: '1px solid var(--border-default)',
          width: 'min(920px, 100vw)',
          height: '100vh',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ padding: '20px 24px 0', borderBottom: '1px solid var(--border-default)', background: 'var(--bg-panel)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 20, fontWeight: 800 }}>{session.name || `Session #${sessionId}`}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                {session.started_at ? new Date(session.started_at).toLocaleString() : '—'}
                {session.ended_at ? ` → ${new Date(session.ended_at).toLocaleString()}` : ''}
              </div>
            </div>
            <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', fontSize: 20, cursor: 'pointer', color: 'var(--text-secondary)', padding: 4 }}>✕</button>
          </div>

          {/* KPI strip */}
          {!loading && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginBottom: 14 }}>
              <KpiCard label="Revenue" value={fmtK(session.total_revenue)} color="var(--accent-amber)" />
              <KpiCard label="Profit" value={fmtK(session.total_profit)} color={clrProfit(session.total_profit)} />
              <KpiCard label="Lots Sold" value={session.total_lots_sold ?? results.length} />
              <KpiCard label="Products" value={session.total_products_sold ?? '—'} />
              <KpiCard label="Unsold" value={unsold.length} color={unsold.length > 0 ? 'var(--accent-coral)' : 'var(--text-secondary)'} />
              <KpiCard label="Buyers" value={topBuyers.length} />
              <KpiCard label="Pending SOs" value={noSOCount} color={noSOCount > 0 ? 'var(--accent-amber)' : 'var(--text-secondary)'} />
            </div>
          )}

          {/* Tab bar */}
          <div style={{ display: 'flex', gap: 0, marginBottom: -1 }}>
            {TABS.map((t) => (
              <button key={t.id} type="button" onClick={() => setTab(t.id)} style={{
                border: 'none', background: 'transparent',
                padding: '8px 16px', cursor: 'pointer', fontSize: 13,
                fontWeight: tab === t.id ? 700 : 400,
                color: tab === t.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
                borderBottom: tab === t.id ? '2px solid var(--accent-amber)' : '2px solid transparent',
              }}>{t.label}</button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div style={{ flex: 1, padding: '20px 24px', overflowY: 'auto' }}>
          {loading && <p style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading session data…</p>}

          {/* ── Overview ── */}
          {!loading && tab === 'overview' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Cumulative revenue chart */}
              {timelineChart.length > 1 && (
                <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, padding: '16px 18px' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
                    💰 Cumulative Revenue
                  </div>
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={timelineChart} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                      <defs>
                        <linearGradient id="cumGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#fbbf24" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#fbbf24" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                      <XAxis dataKey="lot" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                      <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={55} tickFormatter={(v) => `$${v}`} />
                      <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, fontSize: 12 }} />
                      <Area type="monotone" dataKey="cum" stroke="#fbbf24" fill="url(#cumGrad)" strokeWidth={2} name="Cumulative Revenue" dot={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Top buyers mini chart */}
              {topBuyers.length > 0 && (
                <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, padding: '16px 18px' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
                    👑 Top Buyers
                  </div>
                  <ResponsiveContainer width="100%" height={170}>
                    <BarChart data={topBuyers.slice(0, 8)} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
                      <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
                      <YAxis type="category" dataKey="username" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={90} />
                      <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, fontSize: 12 }} />
                      <Bar dataKey="revenue" fill="#fbbf24" radius={[0, 3, 3, 0]} name="Revenue" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {/* ── Timeline ── */}
          {!loading && tab === 'timeline' && (
            <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, padding: '16px 18px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>
                📈 Revenue &amp; Profit per Lot
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={timelineChart} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                  <XAxis dataKey="lot" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                  <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={55} tickFormatter={(v) => `$${v}`} />
                  <Tooltip content={<ChartTip />} />
                  <Bar dataKey="revenue" fill="#fbbf24" radius={[2, 2, 0, 0]} name="Revenue" />
                  <Bar dataKey="profit" fill="#34d399" radius={[2, 2, 0, 0]} name="Profit" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Buyers ── */}
          {!loading && tab === 'buyers' && (
            <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                    {['#', 'Buyer', 'Lots Won', 'Revenue', 'Profit'].map((h, i) => (
                      <th key={h} style={{ padding: '10px 14px', textAlign: i >= 2 ? 'right' : 'left', color: 'var(--text-secondary)', fontWeight: 700, fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topBuyers.map((b, i) => (
                    <tr key={b.username} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontSize: 12 }}>{i + 1}</td>
                      <td style={{ padding: '10px 14px', fontWeight: 700 }}>@{b.username}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right' }}>{b.lots}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt$(b.revenue)}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right', color: clrProfit(b.profit), fontWeight: 600 }}>{fmt$(b.profit)}</td>
                    </tr>
                  ))}
                  {topBuyers.length === 0 && <tr><td colSpan={5} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>No buyer data.</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {/* ── Unsold ── */}
          {!loading && tab === 'unsold' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {unsold.length === 0 && <p style={{ color: 'var(--accent-emerald)', fontSize: 13 }}>✅ All lots were sold!</p>}
              {unsold.map((lot) => (
                <div key={lot.id} style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 10, padding: '12px 16px', display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
                  <div>
                    <span style={{ fontWeight: 700 }}>Lot #{lot.lot_number || lot.id}</span>
                    <span style={{ color: 'var(--text-secondary)', marginLeft: 10, fontSize: 12 }}>{lot.status}</span>
                  </div>
                  <span style={{ color: 'var(--accent-coral)', fontSize: 12, fontWeight: 600 }}>Unsold</span>
                </div>
              ))}
            </div>
          )}

          {/* ── Buyer Orders / Bulk SO ── */}
          {!loading && tab === 'orders' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Bulk action bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 10, padding: '12px 16px' }}>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>
                  {selectedGroups.size} group{selectedGroups.size !== 1 ? 's' : ''} selected · {noSOCount} without Sale Order
                </span>
                <button type="button"
                  onClick={() => setSelectedGroups(new Set(groups.filter((g) => !g.sale_order_id).map((g) => g.id)))}
                  style={{ background: 'none', border: '1px solid var(--border-default)', borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}
                >
                  Select unlinked
                </button>
                <button type="button"
                  onClick={() => setSelectedGroups(new Set())}
                  style={{ background: 'none', border: '1px solid var(--border-default)', borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)' }}
                >
                  Clear
                </button>
                <button type="button"
                  onClick={bulkCreateSO}
                  disabled={bulking || selectedGroups.size === 0}
                  style={{
                    background: selectedGroups.size === 0 ? 'var(--bg-elevated)' : '#fbbf24',
                    color: selectedGroups.size === 0 ? 'var(--text-secondary)' : '#1a1200',
                    border: 'none', borderRadius: 6, padding: '8px 16px', fontSize: 13,
                    fontWeight: 700, cursor: selectedGroups.size === 0 ? 'default' : 'pointer',
                  }}
                >
                  {bulking ? 'Creating…' : `Create ${selectedGroups.size} Sale Order${selectedGroups.size !== 1 ? 's' : ''}`}
                </button>
              </div>
              {bulkResult && (
                <div style={{ fontSize: 13, padding: '10px 14px', borderRadius: 8,
                  background: bulkResult.ok ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                  color: bulkResult.ok ? 'var(--accent-emerald)' : 'var(--accent-coral)',
                  border: `1px solid ${bulkResult.ok ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}` }}>
                  {bulkResult.ok
                    ? `✅ Created ${bulkResult.created}, skipped ${bulkResult.skipped} already linked`
                    : `❌ Error: ${bulkResult.error}`}
                </div>
              )}
              {/* Group list */}
              <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                      <th style={{ padding: '10px 14px', width: 36 }}></th>
                      {['Buyer', 'Revenue', 'Profit', 'Sale Order'].map((h, i) => (
                        <th key={h} style={{ padding: '10px 14px', textAlign: i >= 1 && i <= 2 ? 'right' : 'left', color: 'var(--text-secondary)', fontWeight: 700, fontSize: 11, textTransform: 'uppercase' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => {
                      const checked = selectedGroups.has(g.id);
                      return (
                        <tr key={g.id} style={{ borderTop: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                          onClick={() => setSelectedGroups((prev) => {
                            const next = new Set(prev);
                            if (next.has(g.id)) next.delete(g.id); else next.add(g.id);
                            return next;
                          })}>
                          <td style={{ padding: '10px 14px' }}>
                            <input type="checkbox" readOnly checked={checked} style={{ cursor: 'pointer' }} />
                          </td>
                          <td style={{ padding: '10px 14px', fontWeight: 600 }}>
                            <CustomerLink username={g.whatnot_buyer_username || g.winner_username} customerId={g.customer_id} label={`@${g.whatnot_buyer_username || g.winner_username || '—'}`} onOpen={setCustomerPeek} />
                          </td>
                          <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt$(g.total_revenue)}</td>
                          <td style={{ padding: '10px 14px', textAlign: 'right', color: clrProfit(g.total_profit) }}>{fmt$(g.total_profit)}</td>
                          <td style={{ padding: '10px 14px' }}>
                            {g.sale_order_id
                              ? <span style={{ color: 'var(--accent-emerald)', fontSize: 12, fontWeight: 600 }}>✓ Linked</span>
                              : <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>No SO</span>}
                          </td>
                        </tr>
                      );
                    })}
                    {groups.length === 0 && <tr><td colSpan={5} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>No buyer groups found.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── All Results ── */}
          {!loading && tab === 'lots' && (
            <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-elevated)', zIndex: 1 }}>
                    <tr style={{ borderBottom: '1px solid var(--border-default)' }}>
                      {['Lot #', 'Buyer', 'Product', 'Price', 'Cost', 'Profit', 'Margin', 'Sold At'].map((h, i) => (
                        <th key={h} style={{ padding: '9px 12px', textAlign: i >= 3 && i <= 6 ? 'right' : 'left', color: 'var(--text-secondary)', fontWeight: 700, fontSize: 11, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((r) => (
                      <tr key={r.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '8px 12px', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>{r.lot_number || '—'}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 600 }}>
                          <CustomerLink username={r.winner_username} customerId={r.customer_id} label={`@${r.winner_username || '—'}`} onOpen={setCustomerPeek} />
                        </td>
                        <td style={{ padding: '8px 12px', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{r.product_name || '—'}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt$(r.sale_price)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt$(r.cost_price)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: clrProfit(r.profit), fontWeight: 600 }}>{fmt$(r.profit)}</td>
                        <td style={{ padding: '8px 12px', textAlign: 'right', color: clrMargin(r.margin_pct) }}>{fmtPct(r.margin_pct)}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)', fontSize: 11, whiteSpace: 'nowrap' }}>{fmtDt(r.sold_at)}</td>
                      </tr>
                    ))}
                    {results.length === 0 && <tr><td colSpan={8} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>No results.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
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
