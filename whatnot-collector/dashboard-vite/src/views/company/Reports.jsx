import { useEffect, useState, useMemo } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts';
import {
  EmptyRow,
  FilterBar,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  SessionSelect,
  TableShell,
  Thead,
  clrMargin,
  clrProfit,
  fmt,
  fmtPct,
} from './utils';

const CHART_MODES = [
  { id: 'revenue', label: 'Revenue vs Profit' },
  { id: 'margin', label: 'Margin %' },
  { id: 'sold', label: 'Times Sold' },
];

function ChartTooltip({ active, payload, label, mode }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, padding: '10px 14px', fontSize: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 6, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, display: 'flex', gap: 8, justifyContent: 'space-between' }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 700 }}>
            {mode === 'margin' ? `${Number(p.value).toFixed(1)}%` : mode === 'sold' ? p.value : `$${Number(p.value).toFixed(2)}`}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function Reports({ sessions }) {
  const [session, setSession] = useState('');
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [data, setData] = useState({ rows: [] });
  const [loading, setLoading] = useState(false);
  const [chartMode, setChartMode] = useState('revenue');

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const load = () => {
    setLoading(true);
    const params = new URLSearchParams({ scope: 'company' });
    if (session) params.set('session_id', session);
    if (debounced) params.set('q', debounced);
    fetchApi(`/api/reports/product_profit?${params}`)
      .then((result) => setData(result))
      .catch(() => setData({ rows: [] }))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [session, debounced]);

  const rows = data.rows || [];
  const totalRevenue = rows.reduce((sum, row) => sum + (row.total_revenue || 0), 0);
  const totalProfit = rows.reduce((sum, row) => sum + (row.total_profit || 0), 0);

  const chartData = useMemo(() => {
    const top = [...rows]
      .sort((a, b) => {
        if (chartMode === 'sold') return (b.times_sold || 0) - (a.times_sold || 0);
        if (chartMode === 'margin') return (b.avg_margin || 0) - (a.avg_margin || 0);
        return (b.total_revenue || 0) - (a.total_revenue || 0);
      })
      .slice(0, 15);
    return top.map((r) => ({
      name: (r.product_name || 'Unknown').slice(0, 22),
      Revenue: r.total_revenue || 0,
      Profit: r.total_profit || 0,
      Margin: r.avg_margin || 0,
      Sold: r.times_sold || 0,
    }));
  }, [rows, chartMode]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Products" value={rows.length} icon="📦" />
        <KpiCard label="Revenue" value={fmt(totalRevenue)} icon="💰" color="var(--accent-amber)" />
        <KpiCard label="Profit" value={fmt(totalProfit)} icon="📈" color={clrProfit(totalProfit)} />
        <KpiCard label="Avg Margin" value={fmtPct(totalRevenue ? (totalProfit / totalRevenue) * 100 : null)} icon="%" color={clrMargin(totalRevenue ? (totalProfit / totalRevenue) * 100 : null)} />
      </div>

      <FilterBar>
        <SessionSelect sessions={sessions} value={session} onChange={setSession} />
        <SearchInput value={search} onChange={setSearch} placeholder="Search product, SKU, barcode..." />
        <PrimaryBtn onClick={load}>Refresh</PrimaryBtn>
        <a
          href={`/api/export/reports.csv${session ? `?session_id=${session}` : ''}`}
          download="product_report.csv"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 600, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          ⬇ CSV
        </a>
      </FilterBar>

      {/* Chart */}
      {chartData.length > 0 && (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '18px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
              📊 Top 15 Products
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {CHART_MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setChartMode(m.id)}
                  style={{
                    padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: 'pointer', borderRadius: 6,
                    border: '1px solid var(--border-default)',
                    background: chartMode === m.id ? 'var(--accent-amber)' : 'var(--bg-elevated)',
                    color: chartMode === m.id ? '#1a1200' : 'var(--text-secondary)',
                  }}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} angle={-40} textAnchor="end" interval={0} />
              <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={55}
                tickFormatter={(v) => chartMode === 'margin' ? `${v}%` : chartMode === 'sold' ? v : `$${v}`} />
              <Tooltip content={<ChartTooltip mode={chartMode} />} />
              {chartMode === 'revenue' && (
                <>
                  <Bar dataKey="Revenue" fill="#fbbf24" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Profit" fill="#34d399" radius={[3, 3, 0, 0]} />
                </>
              )}
              {chartMode === 'margin' && (
                <Bar dataKey="Margin" radius={[3, 3, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.Margin >= 25 ? '#34d399' : entry.Margin >= 15 ? '#fbbf24' : '#f87171'} />
                  ))}
                </Bar>
              )}
              {chartMode === 'sold' && (
                <Bar dataKey="Sold" fill="#818cf8" radius={[3, 3, 0, 0]} />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <TableShell footer={`${rows.length} product profit row${rows.length === 1 ? '' : 's'}`}>
        <Thead cols={[
          { label: 'Product' },
          { label: 'SKU / Barcode' },
          { label: 'Session' },
          { label: 'Times Sold', align: 'right' },
          { label: 'Avg Price', align: 'right' },
          { label: 'Revenue', align: 'right' },
          { label: 'Cost', align: 'right' },
          { label: 'Profit', align: 'right' },
          { label: 'Margin', align: 'right' },
        ]} />
        <tbody>
          {(loading || rows.length === 0) && <EmptyRow cols={9} loading={loading} msg="No company report data found." />}
          {!loading && rows.map((row) => (
            <tr key={row.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <td style={{ padding: '8px 14px', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 700 }}>{row.product_name || '—'}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                <div>{row.sku || '—'}</div>
                {row.barcode ? <div style={{ marginTop: 2 }}>{row.barcode}</div> : null}
              </td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>{row.session_id_name || '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.times_sold ?? 0}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)' }}>{fmt(row.avg_winning_price)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.total_revenue)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(row.total_cost)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: clrProfit(row.total_profit), fontWeight: 700 }}>{fmt(row.total_profit)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: clrMargin(row.avg_margin) }}>{fmtPct(row.avg_margin)}</td>
            </tr>
          ))}
        </tbody>
      </TableShell>
    </div>
  );
}
