import { useState, useEffect, useCallback } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  fmt, fmtDt, clrProfit,
  Badge, KpiCard, FilterBar, SessionSelect,
  TableShell, Thead, EmptyRow, PrimaryBtn, SlidePanel,
} from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';

function LotProducts({ lotId }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    fetchApi(`/api/lots/products?lot_id=${lotId}`)
      .then(d => setRows(d.rows || []))
      .catch(() => setRows([]));
  }, [lotId]);

  if (!rows) return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Loading products…</div>;
  if (!rows.length) return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>No products.</div>;

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr style={{ background: 'var(--bg-elevated)' }}>
          {['Product', 'SKU / Barcode', 'Cost', 'Scan Qty', 'On Hand', 'Status', 'Scanned At'].map(h => (
            <th key={h} style={{ padding: '6px 10px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((p, i) => (
          <tr key={i} style={{ borderTop: '1px solid var(--border-subtle)' }}>
            <td style={{ padding: '7px 10px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.product_name}</td>
            <td style={{ padding: '7px 10px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>{p.sku || p.barcode || '—'}</td>
            <td style={{ padding: '7px 10px' }}>{fmt(p.cost)}</td>
            <td style={{ padding: '7px 10px', color: 'var(--text-secondary)' }}>{p.qty_snapshot ?? '—'}</td>
            <td style={{ padding: '7px 10px', color: p.on_hand_qty != null && Number(p.on_hand_qty) <= 0 ? 'var(--accent-coral)' : 'var(--text-secondary)', fontWeight: p.on_hand_qty != null ? 600 : 400 }}>
              {p.on_hand_qty ?? '—'}
            </td>
            <td style={{ padding: '7px 10px' }}><Badge status={p.status} /></td>
            <td style={{ padding: '7px 10px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>{fmtDt(p.scanned_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const STATUS_OPTS = [
  { value: '', label: 'All Statuses' },
  { value: 'open', label: 'Open' },
  { value: 'awaiting_auction', label: 'Awaiting' },
  { value: 'sold', label: 'Sold' },
  { value: 'dropped', label: 'Dropped' },
];

export default function Lots({ sessions }) {
  const [session, setSession] = useState('');
  const [status, setStatus] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [customerPeek, setCustomerPeek] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    const p = new URLSearchParams();
    p.set('scope', 'company');
    if (session) p.set('session_id', session);
    if (status) p.set('status', status);
    fetchApi(`/api/lots?${p}`)
      .then(d => setRows(d.rows || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [session, status]);

  useEffect(() => { load(); }, [load]);

  const COLS = [
    { label: 'Lot #' }, { label: 'Session' }, { label: 'Status' },
    { label: 'Winner' }, { label: 'Price', align: 'right' }, { label: 'Fees', align: 'right' },
    { label: 'Products', align: 'right' }, { label: 'Sold', align: 'right' }, { label: 'Dropped', align: 'right' },
    { label: 'Cost', align: 'right' }, { label: 'Profit', align: 'right' },
    { label: 'Created' }, { label: '' },
  ];

  const totals = {
    revenue: rows.reduce((s, r) => s + (r.winning_price || 0), 0),
    profit:  rows.reduce((s, r) => s + (r.total_profit || 0), 0),
    sold:    rows.filter(r => r.status === 'sold').length,
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
        <KpiCard label="Lots" value={rows.length} icon="📦" />
        <KpiCard label="Sold" value={totals.sold} icon="✅" color="var(--accent-emerald)" />
        <KpiCard label="Revenue" value={fmt(totals.revenue)} icon="💰" color="var(--accent-amber)" />
        <KpiCard label="Profit" value={fmt(totals.profit)} icon="📈" color={clrProfit(totals.profit)} />
      </div>

      <FilterBar>
        <SessionSelect sessions={sessions} value={session} onChange={setSession} />
        <select value={status} onChange={e => setStatus(e.target.value)}
          style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '7px 12px', fontSize: 13 }}>
          {STATUS_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <PrimaryBtn onClick={load}>Refresh</PrimaryBtn>
      </FilterBar>

      <TableShell footer={`${rows.length} lot${rows.length !== 1 ? 's' : ''}`}>
        <Thead cols={COLS} />
        <tbody>
          {(loading || rows.length === 0) && <EmptyRow cols={COLS.length} loading={loading} />}
          {!loading && rows.map(r => (
            <tr key={r.id} style={{ borderTop: '1px solid var(--border-subtle)', cursor: 'pointer' }} onClick={() => setDetail(r)}>
              <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>{r.lot_number}</td>
              <td style={{ padding: '8px 14px', fontSize: 12, color: 'var(--text-secondary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.session_id_name || '—'}</td>
              <td style={{ padding: '8px 14px' }}><Badge status={r.status} /></td>
              <td style={{ padding: '8px 14px' }}>
                {r.winner_username ? <CustomerLink username={r.winner_username} label={`@${r.winner_username}`} onOpen={setCustomerPeek} /> : <span style={{ color: 'var(--text-muted)' }}>—</span>}
              </td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 600 }}>{r.winning_price ? fmt(r.winning_price) : '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{r.fees ? fmt(r.fees) : '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right' }}>{r.total_products ?? 0}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--accent-emerald)' }}>{r.sold_products ?? 0}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: r.dropped_products ? 'var(--accent-coral)' : 'var(--text-secondary)' }}>{r.dropped_products ?? 0}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{r.total_cost ? fmt(r.total_cost) : '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: clrProfit(r.total_profit) }}>{r.total_profit != null ? fmt(r.total_profit) : '—'}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>{fmtDt(r.created_at)}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 11 }}>Details →</td>
            </tr>
          ))}
        </tbody>
      </TableShell>

      {detail && (
        <SlidePanel
          title={`Lot #${detail.lot_number}`}
          sub={`${detail.session_id_name || ''} · ${detail.status}`}
          onClose={() => setDetail(null)}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
              <KpiCard label="Price"    value={fmt(detail.winning_price)} color="var(--accent-amber)" />
              <KpiCard label="Cost"     value={fmt(detail.total_cost)} />
              <KpiCard label="Profit"   value={fmt(detail.total_profit)} color={clrProfit(detail.total_profit)} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
              <KpiCard label="Products" value={detail.total_products ?? 0} icon="📦" />
              <KpiCard label="Sold"     value={detail.sold_products ?? 0} icon="✅" color="var(--accent-emerald)" />
              <KpiCard label="Dropped"  value={detail.dropped_products ?? 0} icon="🗑️" color={detail.dropped_products ? 'var(--accent-coral)' : undefined} />
            </div>
            {detail.winner_username && (
              <div style={{ padding: '10px 14px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius-md)', fontSize: 13 }}>
                <span style={{ color: 'var(--text-secondary)' }}>Winner: </span>
                <CustomerLink username={detail.winner_username} label={`@${detail.winner_username}`} onOpen={setCustomerPeek} />
              </div>
            )}
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Products in Lot</div>
            <LotProducts lotId={detail.id} />
          </div>
        </SlidePanel>
      )}
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
