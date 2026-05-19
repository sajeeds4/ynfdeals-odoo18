import { useEffect, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  EmptyRow,
  FilterBar,
  GhostBtn,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  TableShell,
  Thead,
  fmt,
  fmtPct,
} from './utils';

const REC_META = {
  restock_now: { label: 'Restock Now', color: 'var(--accent-coral)', bg: 'rgba(239,68,68,0.12)' },
  push_next_show: { label: 'Push Next Show', color: 'var(--accent-emerald)', bg: 'rgba(34,197,94,0.12)' },
  slow_moving: { label: 'Slow Moving', color: 'var(--accent-amber)', bg: 'rgba(245,158,11,0.14)' },
  watch: { label: 'Watch', color: 'var(--text-secondary)', bg: 'rgba(255,255,255,0.05)' },
};

function RecommendationBadge({ value }) {
  const meta = REC_META[value] || REC_META.watch;
  return (
    <span style={{ display: 'inline-block', padding: '3px 9px', borderRadius: 999, background: meta.bg, color: meta.color, fontSize: 11, fontWeight: 700 }}>
      {meta.label}
    </span>
  );
}

export default function Prep() {
  const [data, setData] = useState({ priority_rows: [], category_rows: [], summary: {} });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [mode, setMode] = useState('');

  function load() {
    setLoading(true);
    fetchApi('/api/company/prep')
      .then((result) => setData(result))
      .catch(() => setData({ priority_rows: [], category_rows: [], summary: {} }))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  const term = search.trim().toLowerCase();
  const priorities = (data.priority_rows || []).filter((row) => {
    const matchesSearch = !term
      || (row.name || '').toLowerCase().includes(term)
      || (row.sku || '').toLowerCase().includes(term)
      || (row.barcode || '').toLowerCase().includes(term)
      || (row.category_name || '').toLowerCase().includes(term);
    const matchesMode = !mode || row.recommendation === mode;
    return matchesSearch && matchesMode;
  });

  const categoryRows = data.category_rows || [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Restock Now" value={data.summary?.restock_now ?? 0} icon="🚨" color="var(--accent-coral)" />
        <KpiCard label="Push Next Show" value={data.summary?.push_next_show ?? 0} icon="🔥" color="var(--accent-emerald)" />
        <KpiCard label="Slow Moving" value={data.summary?.slow_moving ?? 0} icon="🕰" color="var(--accent-amber)" />
        <KpiCard label="Watch List" value={data.summary?.watch ?? 0} icon="👀" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 0.9fr)', gap: 16 }}>
        <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: 16, background: 'var(--bg-panel)' }}>
          <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 6 }}>Live Prep Recommendations</div>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, lineHeight: 1.5, marginBottom: 14 }}>
            Use this before a show to decide what to restock, what to feature, and what inventory is sitting too long.
          </div>
          <FilterBar>
            <SearchInput value={search} onChange={setSearch} placeholder="Search product, SKU, barcode, category..." />
            <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '7px 12px', fontSize: 13 }}>
              <option value="">All recommendations</option>
              <option value="restock_now">Restock Now</option>
              <option value="push_next_show">Push Next Show</option>
              <option value="slow_moving">Slow Moving</option>
              <option value="watch">Watch</option>
            </select>
            <PrimaryBtn onClick={load}>Refresh</PrimaryBtn>
          </FilterBar>

          <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
            {!loading && priorities.length === 0 ? <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No recommendations found.</div> : null}
            {loading ? <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Loading prep recommendations...</div> : priorities.map((row) => (
              <div key={row.id} style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: '12px 14px', display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start' }}>
                  <div>
                    <div style={{ fontWeight: 800 }}>{row.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                      {row.category_name} · {row.sku || row.barcode || 'No code'}
                    </div>
                  </div>
                  <RecommendationBadge value={row.recommendation} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>On Hand</div>
                    <div style={{ fontWeight: 700, marginTop: 4 }}>{row.on_hand_qty}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Threshold</div>
                    <div style={{ fontWeight: 700, marginTop: 4 }}>{row.low_stock_threshold}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Units Sold</div>
                    <div style={{ fontWeight: 700, marginTop: 4 }}>{row.units_sold}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Revenue</div>
                    <div style={{ fontWeight: 700, marginTop: 4, color: 'var(--accent-amber)' }}>{fmt(row.total_revenue)}</div>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{row.reason}</div>
              </div>
            ))}
          </div>
        </div>

        <TableShell footer={`${categoryRows.length} category${categoryRows.length === 1 ? '' : 'ies'} tracked`}>
          <Thead cols={[
            { label: 'Category' },
            { label: 'Products', align: 'right' },
            { label: 'Units Sold', align: 'right' },
            { label: 'Revenue', align: 'right' },
            { label: 'Profit', align: 'right' },
            { label: 'Margin', align: 'right' },
            { label: 'Stock Value', align: 'right' },
          ]} />
          <tbody>
            {(loading || categoryRows.length === 0) && <EmptyRow cols={7} loading={loading} msg="No category intelligence yet." />}
            {!loading && categoryRows.map((row) => (
              <tr key={row.category_name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '8px 14px', fontWeight: 700 }}>{row.category_name}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.product_count}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.units_sold}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.total_revenue)}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right', color: row.total_profit >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)', fontWeight: 700 }}>{fmt(row.total_profit)}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmtPct(row.margin_pct)}</td>
                <td style={{ padding: '8px 14px', textAlign: 'right' }}>{fmt(row.stock_value)}</td>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </div>
    </div>
  );
}
