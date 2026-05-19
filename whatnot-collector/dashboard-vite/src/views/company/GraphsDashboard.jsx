/**
 * GraphsDashboard — 10 interactive charts with collapse/expand + full-screen
 * Each card: collapsible header, ⛶ fullscreen button, type-toggle, Brush zoom
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  AreaChart, Area, BarChart, Bar, ComposedChart, LineChart, Line,
  ScatterChart, Scatter, PieChart, Pie, Cell,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  ReferenceLine, Brush, Legend,
} from 'recharts';

// ─── Indicator math ───────────────────────────────────────────────────────────

const sma = (arr, n) => arr.map((_, i) => {
  if (i < n - 1) return null;
  return +(arr.slice(i - n + 1, i + 1).reduce((s, v) => s + v, 0) / n).toFixed(2);
});

const ema = (arr, n) => {
  const k = 2 / (n + 1);
  return arr.reduce((out, v, i) => {
    out.push(i === 0 ? +v.toFixed(2) : +(v * k + out[i - 1] * (1 - k)).toFixed(2));
    return out;
  }, []);
};

const bollingerBands = (arr, n) => {
  const m = sma(arr, n);
  return arr.map((_, i) => {
    if (m[i] == null) return { upper: null, lower: null };
    const slice = arr.slice(Math.max(0, i - n + 1), i + 1);
    const std = Math.sqrt(slice.reduce((s, v) => s + (v - m[i]) ** 2, 0) / slice.length);
    return { upper: +(m[i] + 2 * std).toFixed(2), lower: +(Math.max(0, m[i] - 2 * std)).toFixed(2) };
  });
};

const rsiCalc = (arr, n) => arr.map((_, i) => {
  if (i < n) return null;
  const slice = arr.slice(i - n, i + 1);
  let g = 0, l = 0;
  for (let j = 1; j < slice.length; j++) { const d = slice[j] - slice[j-1]; d >= 0 ? (g += d) : (l -= d); }
  const rs = l === 0 ? 100 : g / l;
  return +(100 - 100 / (1 + rs)).toFixed(1);
});

const macdCalc = (arr, fast, slow, sig) => {
  const f = ema(arr, fast), s = ema(arr, slow);
  const line = f.map((v, i) => +(v - s[i]).toFixed(2));
  const signal = ema(line, sig);
  return { line, signal: signal.map(v => +v.toFixed(2)), hist: line.map((v, i) => +(v - signal[i]).toFixed(2)) };
};

const linReg = (arr) => {
  const n = arr.length;
  if (n < 2) return { slope: 0, intercept: arr[0] || 0 };
  const sumX = (n * (n-1)) / 2;
  const sumY = arr.reduce((s, v) => s + v, 0);
  const sumXY = arr.reduce((s, v, i) => s + i * v, 0);
  const sumX2 = (n * (n-1) * (2*n-1)) / 6;
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  return { slope: +slope.toFixed(2), intercept: +((sumY - slope * sumX) / n).toFixed(2) };
};

// ─── Formatting ───────────────────────────────────────────────────────────────

const fmt = (n) => `$${Number(n || 0).toFixed(2)}`;
const fmtK = (n) => {
  if (n == null) return '—';
  const v = Number(n);
  return Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`;
};
const clrProfit = (v) => (Number(v || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)');

function renderLiveSuggestion(item) {
  if (item && typeof item === 'object') {
    const productName = item.product_name || item.name;
    return (
      <>
        {item.message || item.text || ''}
        {productName ? (
          <>
            {' '}
            <strong>{productName}</strong>
            {item.retail_price != null ? ` · Retail ${fmt(item.retail_price)}` : ''}
            {item.our_cost != null ? ` · Our cost ${fmt(item.our_cost)}` : ''}
          </>
        ) : null}
      </>
    );
  }
  return item;
}

const COLORS = ['#fbbf24','#34d399','#818cf8','#f87171','#fb923c','#38bdf8','#a78bfa','#4ade80','#f472b6','#facc15'];

// ─── Tooltip ─────────────────────────────────────────────────────────────────

function Tip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#0d0d14', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '10px 14px', fontSize: 12, minWidth: 160, boxShadow: '0 8px 32px rgba(0,0,0,0.6)' }}>
      <div style={{ fontWeight: 800, marginBottom: 7, color: '#fff', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
      {payload.filter(p => p.value != null && p.value !== 0).map((p) => (
        <div key={p.name} style={{ color: p.color || p.fill || '#aaa', display: 'flex', gap: 10, justifyContent: 'space-between', marginTop: 3 }}>
          <span style={{ opacity: 0.85 }}>{p.name}</span>
          <span style={{ fontWeight: 700 }}>
            {['RSI','Hist','Lots','Dropped','Sold','Sold×5','Margin×3','Revenue÷10','ItemsPerLot','value','Orders','Products','Wins'].includes(p.name)
              ? p.value
              : p.name === 'MarginPct'
                ? `${p.value}%`
              : fmtK(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Full-screen portal ───────────────────────────────────────────────────────

function FullscreenModal({ title, subtitle, signal, onClose, children }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(5,5,10,0.97)', display: 'flex', flexDirection: 'column', backdropFilter: 'blur(4px)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '18px 28px', borderBottom: '1px solid rgba(255,255,255,0.08)', flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 900, color: '#fff', letterSpacing: '-0.02em' }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: 3 }}>{subtitle}</div>}
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {signal && (
            <div style={{ padding: '4px 12px', borderRadius: 999, fontSize: 12, fontWeight: 800, background: signal.bg, color: signal.color, border: `1px solid ${signal.border}` }}>
              {signal.text}
            </div>
          )}
          <button
            onClick={onClose}
            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', color: '#fff', borderRadius: 10, padding: '8px 16px', cursor: 'pointer', fontSize: 13, fontWeight: 700 }}
          >
            ✕ Close (Esc)
          </button>
        </div>
      </div>
      {/* Chart area */}
      <div style={{ flex: 1, padding: '24px 28px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
        {children}
      </div>
    </div>
  );
}

// ─── Chart card wrapper ───────────────────────────────────────────────────────

function ChartCard({ id, title, subtitle, signal, controls, children, fullscreenContent, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);
  const [fs, setFs] = useState(false);

  return (
    <>
      <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, overflow: 'hidden', transition: 'box-shadow 0.2s' }}>
        {/* ── Card header ── */}
        <div
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', cursor: 'pointer', userSelect: 'none', borderBottom: open ? '1px solid var(--border-subtle)' : 'none', gap: 12 }}
          onClick={() => setOpen(v => !v)}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
            {subtitle && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{subtitle}</div>}
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }} onClick={e => e.stopPropagation()}>
            {signal && (
              <div style={{ padding: '2px 9px', borderRadius: 999, fontSize: 10, fontWeight: 800, background: signal.bg, color: signal.color, border: `1px solid ${signal.border}`, whiteSpace: 'nowrap' }}>
                {signal.text}
              </div>
            )}
            {controls}
            <button
              onClick={(e) => { e.stopPropagation(); setFs(true); }}
              title="Full screen"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', borderRadius: 8, padding: '5px 9px', cursor: 'pointer', fontSize: 13, lineHeight: 1 }}
            >⛶</button>
            <button
              onClick={(e) => { e.stopPropagation(); setOpen(v => !v); }}
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', borderRadius: 8, padding: '5px 9px', cursor: 'pointer', fontSize: 12, lineHeight: 1, minWidth: 28, textAlign: 'center' }}
            >{open ? '▲' : '▼'}</button>
          </div>
        </div>
        {/* ── Collapsible body ── */}
        {open && (
          <div style={{ padding: '16px 18px 18px' }}>
            {children}
          </div>
        )}
      </div>

      {/* ── Full-screen overlay ── */}
      {fs && (
        <FullscreenModal title={title} subtitle={subtitle} signal={signal} onClose={() => setFs(false)}>
          {fullscreenContent || children}
        </FullscreenModal>
      )}
    </>
  );
}

// ─── Small toggle-button group ────────────────────────────────────────────────

function ToggleGroup({ options, value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 4 }}>
      {options.map(o => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          style={{
            padding: '3px 9px', fontSize: 10, fontWeight: 700, borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--border-default)',
            background: value === o.id ? '#fbbf24' : 'var(--bg-elevated)',
            color: value === o.id ? '#1a1200' : 'var(--text-secondary)',
          }}
        >{o.label}</button>
      ))}
    </div>
  );
}

// ─── Axis / Brush shared props ────────────────────────────────────────────────

const xProps = { tick: { fill: 'var(--text-secondary)', fontSize: 10 }, angle: -30, textAnchor: 'end', interval: 0, height: 50 };
const yProps = (fmt) => ({ tick: { fill: 'var(--text-secondary)', fontSize: 10 }, width: 60, tickFormatter: fmt });
const grid = <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />;
const brushStyle = { height: 20, fill: 'var(--bg-elevated)', stroke: 'var(--border-default)', travellerWidth: 6 };

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function GraphsDashboard() {
  const [sessions, setSessions] = useState([]);
  const [products, setProducts] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [auctionRows, setAuctionRows] = useState([]);
  const [categories, setCategories] = useState([]);
  const [latestEndedStream, setLatestEndedStream] = useState(null);
  const [latestStreamDetail, setLatestStreamDetail] = useState({ report_rows: [] });
  const [intelligence, setIntelligence] = useState(null);
  const [loading, setLoading] = useState(true);

  // per-chart UI state
  const [chart1Mode, setChart1Mode] = useState('area');  // area | line | bar
  const [chart2Mode, setChart2Mode] = useState('grouped'); // grouped | stacked
  const [chart3Frame, setChart3Frame] = useState('all'); // all | 5 | 3
  const [chart10Mode, setChart10Mode] = useState('combo'); // combo | lots | price
  const [selectedChart, setSelectedChart] = useState('revenue-trend');
  const [hiddenSeries, setHiddenSeries] = useState({});

  const toggleSeries = (key) => setHiddenSeries(prev => ({ ...prev, [key]: !prev[key] }));

  useEffect(() => {
    let cancelled = false;
    async function loadDashboard() {
      const [s, p, inv, ar, prep, history, intel] = await Promise.all([
        fetchApi('/api/sessions/list?scope=company').catch(() => ({ sessions: [] })),
        fetchApi('/api/reports/product_profit?scope=company').catch(() => ({ rows: [] })),
        fetchApi('/api/inventory?scope=company&compact=1').catch(() => ({ rows: [] })),
        fetchApi('/api/auction_results?scope=company').catch(() => ({ rows: [] })),
        fetchApi('/api/company/prep').catch(() => ({ category_rows: [] })),
        fetchApi('/api/history/company_sessions').catch(() => ({ sessions: [] })),
        fetchApi('/api/company/intelligence').catch(() => null),
      ]);

      if (cancelled) return;

      const endedStream = (history.sessions || []).find((row) => row.status === 'ended' && row.total_products_sold > 0) || null;
      let detail = { report_rows: [] };
      if (endedStream?.stream_id || endedStream?.id) {
        detail = await fetchApi(`/api/history/company_detail?stream_id=${endedStream.stream_id || endedStream.id}`).catch(() => ({ report_rows: [] }));
      }
      if (cancelled) return;

      setSessions((s.sessions || []).filter(x => (x.total_revenue || 0) > 0).sort((a, b) => new Date(a.start_time || 0) - new Date(b.start_time || 0)));
      setProducts((p.rows || []).filter(x => x.product_name).slice(0, 50));
      setInventory((inv.rows || []).filter(x => x.name).slice(0, 20));
      setAuctionRows(ar.rows || []);
      setCategories(prep.category_rows || []);
      setLatestEndedStream(endedStream);
      setLatestStreamDetail(detail);
      setIntelligence(intel);
      setLoading(false);
    }

    loadDashboard();
    return () => { cancelled = true; };
  }, []);

  const d = useMemo(() => {
    if (sessions.length < 2) return null;
    const names = sessions.map((s, i) => (s.name || `S${i+1}`).slice(0, 12));
    const revs = sessions.map(s => s.total_revenue || 0);
    const profs = sessions.map(s => s.total_profit || 0);
    const lots = sessions.map(s => s.total_lots_sold || 0);

    const p = Math.min(5, revs.length);
    const sma5 = sma(revs, p);
    const ema5 = ema(revs, p);
    const bb = bollingerBands(revs, p);
    const rsiArr = rsiCalc(revs, Math.min(7, revs.length - 1));
    const { line: macdLine, signal: macdSig, hist: macdHist } = macdCalc(revs, Math.min(5, revs.length), Math.min(10, revs.length), 3);
    const { slope, intercept } = linReg(revs);

    const predictions = [1, 2, 3].map(offset => ({
      name: `Pred+${offset}`,
      Price: Math.max(0, +(intercept + slope * (revs.length - 1 + offset)).toFixed(2)),
      isPred: true,
    }));

    const lastRsi = rsiArr.filter(v => v != null).slice(-1)[0] ?? null;
    const lastML = macdLine.slice(-1)[0];
    const lastMS = macdSig.slice(-1)[0];
    const macdAbove = lastML > lastMS;
    let sig = null;
    if (lastRsi != null) {
      if (lastRsi < 30 && macdAbove && slope > 0)      sig = { text: '🚀 Strong Buy', bg: 'rgba(52,211,153,0.18)', color: '#34d399', border: 'rgba(52,211,153,0.35)' };
      else if (lastRsi > 70 && !macdAbove)              sig = { text: '⚠️ Overbought', bg: 'rgba(248,113,113,0.18)', color: '#f87171', border: 'rgba(248,113,113,0.35)' };
      else if (macdAbove && slope > 0)                  sig = { text: '📈 Bullish', bg: 'rgba(52,211,153,0.12)', color: '#34d399', border: 'rgba(52,211,153,0.25)' };
      else if (!macdAbove && slope < 0)                 sig = { text: '📉 Bearish', bg: 'rgba(248,113,113,0.12)', color: '#f87171', border: 'rgba(248,113,113,0.25)' };
      else                                               sig = { text: '➡️ Neutral', bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.25)' };
    }

    // chart data
    const c1 = sessions.map((_, i) => ({
      name: names[i], Revenue: revs[i],
      Cumulative: +(revs.slice(0, i+1).reduce((a, v) => a+v, 0)).toFixed(2),
    }));
    const c2 = sessions.map((_, i) => ({ name: names[i], Revenue: revs[i], Profit: profs[i] }));
    const c3full = [
      ...sessions.map((_, i) => ({
        name: names[i], Price: revs[i],
        SMA5: sma5[i], EMA5: ema5[i],
        Upper: bb[i]?.upper ?? null, Lower: bb[i]?.lower ?? null,
      })),
      ...predictions,
    ];
    const c4 = sessions.map((_, i) => ({ name: names[i], RSI: rsiArr[i] })).filter(d => d.RSI != null);
    const c5 = sessions.map((_, i) => ({ name: names[i], MACD: macdLine[i], Signal: macdSig[i], Hist: macdHist[i] }));
    const c10 = sessions.map((_, i) => ({
      name: names[i], Lots: lots[i],
      Dropped: sessions[i].total_dropped_products || 0,
      AvgPrice: lots[i] ? +(revs[i] / lots[i]).toFixed(2) : 0,
    }));
    const c11 = sessions.map((session, i) => ({
      name: names[i],
      MarginPct: revs[i] ? +((profs[i] / revs[i]) * 100).toFixed(1) : 0,
      Profit: profs[i],
      Revenue: revs[i],
      Lots: lots[i],
    }));
    const c12 = sessions.map((session, i) => ({
      name: names[i],
      RevenuePerLot: lots[i] ? +(revs[i] / lots[i]).toFixed(2) : 0,
      ItemsPerLot: lots[i] ? +(((session.total_products_sold || 0) / lots[i]).toFixed(2)) : 0,
      Lots: lots[i],
    }));

    // buyer pie
    const bmap = {};
    auctionRows.forEach(r => { const k = r.winner_username || 'Unknown'; bmap[k] = (bmap[k] || 0) + (r.sale_price || 0); });
    const buyerPie = Object.entries(bmap).sort(([,a],[,b]) => b-a).slice(0, 9).map(([name, value]) => ({ name: `@${name}`, value: +value.toFixed(2) }));

    // scatter
    const scatter = products.map(p => ({ x: p.total_revenue || 0, y: p.avg_margin || 0, z: p.times_sold || 1, label: p.product_name }));

    // inventory
    const invBar = inventory.map(item => ({ name: (item.name||'').slice(0,16), Stock: item.on_hand_qty||0, Reorder: item.reorder_point||0 })).sort((a,b) => b.Stock-a.Stock).slice(0,14);

    // radar
    const radarData = categories.slice(0, 8).map(c => ({
      subject: (c.category_name||'Other').slice(0, 14),
      'Revenue÷10': Math.round((c.total_revenue||0)/10),
      'Sold×5': (c.units_sold||0) * 5,
      'Margin×3': Math.max(0, Math.round((c.margin_pct||0)*3)),
    }));

    const reportRows = latestStreamDetail.report_rows || [];
    const profileCount = reportRows.filter((row) => row.profile_made).length;
    const saleOrderCount = reportRows.filter((row) => row.sale_order_made).length;
    const c13 = [
      { name: 'Winners', value: reportRows.length, fill: '#fbbf24' },
      { name: 'Profiles', value: profileCount, fill: '#818cf8' },
      { name: 'Sale Orders', value: saleOrderCount, fill: '#34d399' },
    ];
    const basketMap = reportRows.reduce((acc, row) => {
      const count = Number(row.item_count || 0);
      const bucket = count <= 1 ? '1 Item' : count === 2 ? '2 Items' : count === 3 ? '3 Items' : '4+ Items';
      acc[bucket] = (acc[bucket] || 0) + 1;
      return acc;
    }, {});
    const c14 = ['1 Item', '2 Items', '3 Items', '4+ Items'].map((name) => ({
      name,
      Orders: basketMap[name] || 0,
    }));
    const c15 = sessions.map((session, i) => ({
      name: names[i],
      Products: session.total_products_sold || 0,
      Lots: lots[i],
    }));
    const bucketDefs = [
      { name: '$0-25', min: 0, max: 25 },
      { name: '$25-50', min: 25, max: 50 },
      { name: '$50-100', min: 50, max: 100 },
      { name: '$100-200', min: 100, max: 200 },
      { name: '$200+', min: 200, max: Infinity },
    ];
    const c16 = bucketDefs.map((bucket) => ({
      name: bucket.name,
      Orders: auctionRows.filter((row) => {
        const price = Number(row.sale_price || 0);
        return price >= bucket.min && price < bucket.max;
      }).length,
    }));
    const buyerValueMap = {};
    auctionRows.forEach((row) => {
      const key = `@${row.winner_username || 'Unknown'}`;
      if (!buyerValueMap[key]) buyerValueMap[key] = { name: key, Revenue: 0, Wins: 0 };
      buyerValueMap[key].Revenue += Number(row.sale_price || 0);
      buyerValueMap[key].Wins += 1;
    });
    const c17 = Object.values(buyerValueMap).sort((a, b) => b.Revenue - a.Revenue).slice(0, 10);
    const c18 = [...products]
      .sort((a, b) => (b.total_revenue || 0) - (a.total_revenue || 0))
      .slice(0, 12)
      .map((product) => ({
        name: (product.product_name || '').slice(0, 20),
        Revenue: product.total_revenue || 0,
        Profit: product.total_profit || 0,
      }));
    const c19 = [...products]
      .filter((product) => (product.times_sold || 0) > 0)
      .sort((a, b) => (a.avg_margin || 0) - (b.avg_margin || 0))
      .slice(0, 10)
      .map((product) => ({
        name: (product.product_name || '').slice(0, 20),
        MarginPct: +(product.avg_margin || 0).toFixed(1),
        Revenue: product.total_revenue || 0,
      }));

    return { c1, c2, c3full, c4, c5, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, buyerPie, scatter, invBar, radarData, lastRsi, lastML, lastMS, slope, sig, predictions, profileCount, saleOrderCount };
  }, [sessions, products, inventory, auctionRows, categories, latestStreamDetail]);

  if (loading) return <div style={{ color: 'var(--text-secondary)', padding: 24 }}>Loading charts...</div>;
  if (!d) return <div style={{ color: 'var(--text-secondary)', padding: 24 }}>Need at least 2 sessions with revenue data.</div>;

  const { c1, c2, c3full, c4, c5, c10, c11, c12, c13, c14, c15, c16, c17, c18, c19, buyerPie, scatter, invBar, radarData, lastRsi, lastML, lastMS, slope, sig, profileCount, saleOrderCount } = d;

  const c3 = chart3Frame === 'all' ? c3full : c3full.slice(Math.max(0, c3full.length - (chart3Frame === '5' ? 7 : 5)));

  const nextPred = d.predictions[0]?.Price;
  const rsiSignal = lastRsi != null ? (
    lastRsi > 70
      ? { text: `🔴 Overbought ${lastRsi}`, bg: 'rgba(248,113,113,0.15)', color: '#f87171', border: 'rgba(248,113,113,0.3)' }
      : lastRsi < 30
        ? { text: `🟢 Oversold ${lastRsi} — Buy`, bg: 'rgba(52,211,153,0.15)', color: '#34d399', border: 'rgba(52,211,153,0.3)' }
        : { text: `RSI ${lastRsi} — Neutral`, bg: 'rgba(255,255,255,0.04)', color: 'var(--text-secondary)', border: 'var(--border-default)' }
  ) : null;
  const macdSignal = lastML != null ? (
    lastML > lastMS
      ? { text: '📈 Bullish crossover', bg: 'rgba(52,211,153,0.15)', color: '#34d399', border: 'rgba(52,211,153,0.3)' }
      : { text: '📉 Bearish crossover', bg: 'rgba(248,113,113,0.15)', color: '#f87171', border: 'rgba(248,113,113,0.3)' }
  ) : null;

  // ── Render helpers ────────────────────────────────────────────────────────

  function renderC1(height = 220) {
    const data = c1;
    if (chart1Mode === 'bar') return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Bar dataKey="Revenue" fill="#fbbf24" radius={[3,3,0,0]} />
          <Bar dataKey="Cumulative" fill="#818cf8" radius={[3,3,0,0]} />
        </BarChart>
      </ResponsiveContainer>
    );
    if (chart1Mode === 'line') return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Line type="monotone" dataKey="Revenue" stroke="#fbbf24" strokeWidth={2.5} dot={{ r: 4, fill: '#fbbf24' }} />
          <Line type="monotone" dataKey="Cumulative" stroke="#818cf8" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    );
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1"><stop offset="10%" stopColor="#fbbf24" stopOpacity={0.4}/><stop offset="95%" stopColor="#fbbf24" stopOpacity={0}/></linearGradient>
            <linearGradient id="gCum" x1="0" y1="0" x2="0" y2="1"><stop offset="10%" stopColor="#818cf8" stopOpacity={0.25}/><stop offset="95%" stopColor="#818cf8" stopOpacity={0}/></linearGradient>
          </defs>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Area type="monotone" dataKey="Cumulative" stroke="#818cf8" fill="url(#gCum)" strokeWidth={2} dot={false} />
          <Area type="monotone" dataKey="Revenue" stroke="#fbbf24" fill="url(#gRev)" strokeWidth={2.5} dot={{ r: 4, fill: '#fbbf24' }} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  function renderC2(height = 220) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={c2} margin={{ top: 4, right: 8, left: 0, bottom: 0 }} stackOffset={chart2Mode === 'stacked' ? 'none' : undefined}>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          {chart2Mode === 'stacked' ? (
            <>
              <Bar dataKey="Revenue" stackId="a" fill="#fbbf24" radius={[0,0,0,0]} />
              <Bar dataKey="Profit"  stackId="a" fill="#34d399" radius={[3,3,0,0]} />
            </>
          ) : (
            <>
              <Bar dataKey="Revenue" fill="#fbbf24" radius={[3,3,0,0]} />
              <Bar dataKey="Profit"  fill="#34d399" radius={[3,3,0,0]} />
            </>
          )}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderStock(height = 260) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c3} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gBand" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#818cf8" stopOpacity={0.12}/><stop offset="100%" stopColor="#818cf8" stopOpacity={0.02}/></linearGradient>
          </defs>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Area type="monotone" dataKey="Upper" stroke="none" fill="url(#gBand)" legendType="none" />
          <Area type="monotone" dataKey="Lower" stroke="none" fill="transparent" legendType="none" />
          <Line type="monotone" dataKey="Upper" stroke="#818cf8" strokeWidth={1} dot={false} strokeDasharray="5 3" name="BB Upper" connectNulls />
          <Line type="monotone" dataKey="Lower" stroke="#818cf8" strokeWidth={1} dot={false} strokeDasharray="5 3" name="BB Lower" connectNulls />
          <Line type="monotone" dataKey="SMA5"  stroke="#fbbf24" strokeWidth={1.5} dot={false} connectNulls />
          <Line type="monotone" dataKey="EMA5"  stroke="#34d399" strokeWidth={1.5} dot={false} connectNulls />
          <Line
            type="monotone" dataKey="Price" stroke="#fff" strokeWidth={2.5} connectNulls
            dot={(props) => {
              const { cx, cy, payload } = props;
              const fill = payload.isPred ? '#f87171' : '#fff';
              return <circle key={`d-${cx}`} cx={cx} cy={cy} r={payload.isPred ? 7 : 4} fill={fill} stroke={fill} strokeWidth={1} />;
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderRsi(height = 210) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={c4} margin={{ top: 4, right: 20, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gRsi" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#818cf8" stopOpacity={0.35}/><stop offset="95%" stopColor="#818cf8" stopOpacity={0}/></linearGradient>
          </defs>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis domain={[0, 100]} tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={35} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <ReferenceLine y={70} stroke="#f87171" strokeDasharray="4 2" label={{ value: 'OB 70', position: 'insideTopRight', fill: '#f87171', fontSize: 10 }} />
          <ReferenceLine y={50} stroke="var(--border-subtle)" strokeDasharray="2 4" />
          <ReferenceLine y={30} stroke="#34d399" strokeDasharray="4 2" label={{ value: 'OS 30', position: 'insideBottomRight', fill: '#34d399', fontSize: 10 }} />
          <Area type="monotone" dataKey="RSI" stroke="#818cf8" fill="url(#gRsi)" strokeWidth={2.5} dot={{ r: 4, fill: '#818cf8' }} />
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  function renderMacd(height = 220) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c5} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}<XAxis dataKey="name" {...xProps} /><YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <ReferenceLine y={0} stroke="var(--border-default)" />
          <Bar dataKey="Hist" fill="#818cf8" opacity={0.7} radius={[2,2,0,0]} />
          <Line type="monotone" dataKey="MACD"   stroke="#fbbf24" strokeWidth={2.5} dot={false} />
          <Line type="monotone" dataKey="Signal" stroke="#f87171" strokeWidth={1.5} dot={false} strokeDasharray="5 3" />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderRadar(height = 260) {
    if (!radarData.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No category data.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={radarData} margin={{ top: 10, right: 40, left: 40, bottom: 10 }}>
          <PolarGrid stroke="var(--border-subtle)" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
          <PolarRadiusAxis tick={{ fill: 'var(--text-secondary)', fontSize: 9 }} />
          <Radar name="Revenue÷10" dataKey="Revenue÷10" stroke="#fbbf24" fill="#fbbf24" fillOpacity={0.2} />
          <Radar name="Sold×5"     dataKey="Sold×5"     stroke="#34d399" fill="#34d399" fillOpacity={0.15} />
          <Radar name="Margin×3"   dataKey="Margin×3"   stroke="#818cf8" fill="#818cf8" fillOpacity={0.15} />
          <Legend />
          <Tooltip />
        </RadarChart>
      </ResponsiveContainer>
    );
  }

  function renderScatter(height = 250) {
    if (!scatter.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No product data.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 4, right: 20, left: 0, bottom: 30 }}>
          {grid}
          <XAxis type="number" dataKey="x" name="Revenue" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} tickFormatter={v => `$${v}`} label={{ value: 'Revenue →', position: 'insideBottom', offset: -12, fill: 'var(--text-muted)', fontSize: 10 }} />
          <YAxis type="number" dataKey="y" name="Margin %" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} tickFormatter={v => `${v}%`} label={{ value: 'Margin %', angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 10 }} />
          <ReferenceLine y={0} stroke="#f87171" strokeDasharray="4 2" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const dd = payload[0]?.payload;
            return (
              <div style={{ background: '#0d0d14', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: '8px 12px', fontSize: 12 }}>
                <div style={{ fontWeight: 800, marginBottom: 4, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#fff' }}>{dd?.label}</div>
                <div style={{ color: '#fbbf24' }}>Revenue: {fmtK(dd?.x)}</div>
                <div style={{ color: '#34d399' }}>Margin: {dd?.y?.toFixed(1)}%</div>
                <div style={{ color: '#818cf8' }}>Sold: {dd?.z}×</div>
              </div>
            );
          }} />
          <Scatter data={scatter} fill="#818cf8" opacity={0.8} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  function renderPie(height = 260) {
    if (!buyerPie.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No buyer data.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={buyerPie} cx="50%" cy="50%" innerRadius={60} outerRadius={height > 350 ? 140 : 95} paddingAngle={3} dataKey="value"
            label={({ name, percent }) => `${name} ${(percent*100).toFixed(0)}%`}
            labelLine={{ stroke: 'var(--text-muted)', strokeWidth: 1 }}
          >
            {buyerPie.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
          </Pie>
          <Tooltip formatter={v => fmtK(v)} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  function renderInv(height) {
    if (!invBar.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No inventory data.</div>;
    const h = height || Math.min(280, invBar.length * 26 + 50);
    return (
      <ResponsiveContainer width="100%" height={h}>
        <BarChart layout="vertical" data={invBar} margin={{ top: 4, right: 50, left: 100, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={95} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="Stock"   fill="#34d399" radius={[0,3,3,0]} />
          <Bar dataKey="Reorder" fill="#f87171" radius={[0,3,3,0]} opacity={0.7} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderVelocity(height = 220) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c10} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis yAxisId="left" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={35} />
          <YAxis yAxisId="right" orientation="right" {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          {(chart10Mode === 'combo' || chart10Mode === 'lots') && <>
            <Bar yAxisId="left" dataKey="Lots"    fill="#818cf8" radius={[3,3,0,0]} opacity={0.85} />
            <Bar yAxisId="left" dataKey="Dropped" fill="#f87171" radius={[3,3,0,0]} opacity={0.75} />
          </>}
          {(chart10Mode === 'combo' || chart10Mode === 'price') &&
            <Line yAxisId="right" type="monotone" dataKey="AvgPrice" stroke="#fbbf24" strokeWidth={2.5} dot={{ r: 4, fill: '#fbbf24' }} name="AvgPrice" />
          }
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderMarginQuality(height = 320) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c11} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis yAxisId="left" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={42} tickFormatter={(v) => `${v}%`} />
          <YAxis yAxisId="right" orientation="right" {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <ReferenceLine yAxisId="left" y={15} stroke="#fbbf24" strokeDasharray="4 2" />
          <ReferenceLine yAxisId="left" y={25} stroke="#34d399" strokeDasharray="4 2" />
          <Bar yAxisId="right" dataKey="Profit" fill="#34d399" radius={[3, 3, 0, 0]} opacity={0.35} />
          <Line yAxisId="left" type="monotone" dataKey="MarginPct" stroke="#fbbf24" strokeWidth={2.5} dot={{ r: 4, fill: '#fbbf24' }} name="MarginPct" />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderLotEfficiency(height = 320) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c12} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis yAxisId="left" {...yProps(v => `$${v}`)} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={42} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Bar yAxisId="left" dataKey="RevenuePerLot" fill="#fbbf24" radius={[3, 3, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="ItemsPerLot" stroke="#818cf8" strokeWidth={2.5} dot={{ r: 4, fill: '#818cf8' }} name="ItemsPerLot" />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderBuyerConversion(height = 320) {
    if (!latestEndedStream || !c13.some((row) => row.value > 0)) {
      return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No ended stream conversion data yet.</div>;
    }
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart layout="vertical" data={c13} margin={{ top: 10, right: 18, left: 40, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={85} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="value" radius={[0, 6, 6, 0]}>
            {c13.map((entry, index) => <Cell key={index} fill={entry.fill} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderBasketSize(height = 320) {
    if (!latestEndedStream || !c14.some((row) => row.Orders > 0)) {
      return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No basket-size data for the latest ended stream.</div>;
    }
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={c14} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
          <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={40} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="Orders" fill="#60a5fa" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderSessionVolume(height = 320) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={c15} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={42} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Bar dataKey="Products" fill="#60a5fa" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Lots" fill="#fbbf24" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderSalePriceBands(height = 320) {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={c16} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
          <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={40} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="Orders" fill="#a78bfa" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderBuyerValue(height = 320) {
    if (!c17.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No buyer sales data yet.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={c17} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis yAxisId="left" {...yProps(v => `$${v}`)} />
          <YAxis yAxisId="right" orientation="right" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={38} />
          <Tooltip content={<Tip />} />
          <Bar yAxisId="left" dataKey="Revenue" fill="#fbbf24" radius={[3, 3, 0, 0]} />
          <Line yAxisId="right" type="monotone" dataKey="Wins" stroke="#34d399" strokeWidth={2.5} dot={{ r: 4, fill: '#34d399' }} />
        </ComposedChart>
      </ResponsiveContainer>
    );
  }

  function renderTopProducts(height = 320) {
    if (!c18.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No product sales data yet.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={c18} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          {grid}
          <XAxis dataKey="name" {...xProps} />
          <YAxis {...yProps(v => `$${v}`)} />
          <Tooltip content={<Tip />} />
          <Brush dataKey="name" height={20} style={brushStyle} />
          <Bar dataKey="Revenue" fill="#fbbf24" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Profit" fill="#34d399" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderLowMarginProducts(height = 320) {
    if (!c19.length) return <div style={{ color: 'var(--text-secondary)', fontSize: 12, padding: 20 }}>No low-margin product data yet.</div>;
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart layout="vertical" data={c19} margin={{ top: 4, right: 40, left: 110, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
          <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} width={105} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="MarginPct" radius={[0, 6, 6, 0]}>
            {c19.map((entry, index) => (
              <Cell key={index} fill={entry.MarginPct >= 15 ? '#fbbf24' : '#f87171'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  function renderIntelligence() {
    if (!intelligence) {
      return <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: 20 }}>Loading intelligence…</div>;
    }

    const rec = intelligence.recommendations || {};
    const summary = intelligence.summary || {};
    const topBuyers = intelligence.top_buyers || [];
    const keywordRows = intelligence.chat_keywords || [];
    const productRows = intelligence.products || [];
    const hourlyRows = (intelligence.hourly || []).filter((row) => row.revenue > 0 || row.chat_count > 0 || row.bid_count > 0);
    const dayRows = intelligence.by_day || [];
    const liveMode = intelligence.live_mode || { running: false, suggestions: [] };

    const bestHourLabel = rec.best_start_time_hour != null
      ? new Date(2000, 0, 1, rec.best_start_time_hour).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
      : '—';

    return (
      <div style={{ display: 'grid', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
          <div className="company-kpi" style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Best Day</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{rec.best_day_to_go_live || '—'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>Highest profit day</div>
          </div>
          <div className="company-kpi" style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Best Start Time</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{bestHourLabel}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>Best revenue by start hour</div>
          </div>
          <div className="company-kpi" style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Recommended Duration</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{rec.recommended_duration_minutes ? `${rec.recommended_duration_minutes}m` : '—'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>Based on historical session length</div>
          </div>
          <div className="company-kpi" style={{ padding: '16px 18px' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>Expected Revenue</div>
            <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{fmtK(rec.expected_revenue_low)} - {fmtK(rec.expected_revenue_high)}</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>Historical range</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1.3fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 10 }}>AI Recommendations</div>
            <div style={{ display: 'grid', gap: 10, fontSize: 13 }}>
              <div><span style={{ color: 'var(--text-secondary)' }}>Peak profit window:</span> <strong>{summary.peak_profit_window || '—'}</strong></div>
              <div><span style={{ color: 'var(--text-secondary)' }}>Highest engagement day:</span> <strong>{rec.highest_engagement_day || '—'}</strong></div>
              <div><span style={{ color: 'var(--text-secondary)' }}>Best conversion day:</span> <strong>{rec.best_conversion_day || '—'}</strong></div>
              <div><span style={{ color: 'var(--text-secondary)' }}>Avg time from first activity to buy:</span> <strong>{summary.avg_minutes_to_buy != null ? `${summary.avg_minutes_to_buy} min` : '—'}</strong></div>
            </div>
            <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
              {(rec.best_product_sequence_strategy || []).map((line, index) => (
                <div key={index} style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.16)', fontSize: 13 }}>
                  {line}
                </div>
              ))}
              {(rec.dropoff_windows || []).length ? (
                <div style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.16)', fontSize: 13 }}>
                  Drop-off windows detected around: <strong>{rec.dropoff_windows.join(', ')}</strong>
                </div>
              ) : null}
            </div>
          </div>

          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 10 }}>Real-Time Mode</div>
            <div style={{ fontSize: 13, color: liveMode.running ? 'var(--accent-emerald)' : 'var(--text-secondary)', fontWeight: 700 }}>
              {liveMode.running ? 'Live stream detected' : 'No live stream running'}
            </div>
            {liveMode.running ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 8, lineHeight: 1.6 }}>
                Revenue now: <strong>{fmt(summary.current_revenue || liveMode.current_revenue)}</strong><br />
                Historical average: <strong>{fmt(summary.historical_avg_revenue || liveMode.historical_avg_revenue)}</strong>
              </div>
            ) : null}
            <div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              {(liveMode.suggestions || []).length
                ? liveMode.suggestions.map((item, index) => (
                  <div key={index} style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.16)', fontSize: 13 }}>
                    {renderLiveSuggestion(item)}
                  </div>
                ))
                : <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Live suggestions will appear here when a stream is running.</div>}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 12 }}>Hourly Profitability</div>
            <div style={{ maxHeight: 260, overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', paddingBottom: 8, color: 'var(--text-secondary)' }}>Hour</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Revenue</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Profit</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Conv%</th>
                  </tr>
                </thead>
                <tbody>
                  {hourlyRows.map((row) => (
                    <tr key={row.hour} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '8px 0' }}>{String(row.hour).padStart(2, '0')}:00</td>
                      <td style={{ padding: '8px 0', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.revenue)}</td>
                      <td style={{ padding: '8px 0', textAlign: 'right', color: clrProfit(row.profit), fontWeight: 700 }}>{fmt(row.profit)}</td>
                      <td style={{ padding: '8px 0', textAlign: 'right' }}>{row.conversion_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: 13, fontWeight: 800, marginBottom: 12 }}>Day-Based Performance</div>
            <div style={{ maxHeight: 260, overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    <th style={{ textAlign: 'left', paddingBottom: 8, color: 'var(--text-secondary)' }}>Day</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Avg Rev</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Engagement</th>
                    <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Conv%</th>
                  </tr>
                </thead>
                <tbody>
                  {dayRows.map((row) => (
                    <tr key={row.day} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '8px 0' }}>{row.day}</td>
                      <td style={{ padding: '8px 0', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.avg_revenue_per_session)}</td>
                      <td style={{ padding: '8px 0', textAlign: 'right' }}>{row.engagement}</td>
                      <td style={{ padding: '8px 0', textAlign: 'right' }}>{row.conversion_rate}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: '13px', fontWeight: 800, marginBottom: 12 }}>High-Value Buyers</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {topBuyers.slice(0, 8).map((buyer) => (
                <div key={buyer.username} style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <strong>@{buyer.username}</strong>
                    <span style={{ color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(buyer.revenue)}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {buyer.orders} wins · {buyer.session_count} sessions · Profit {fmt(buyer.profit)}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
            <div style={{ fontSize: '13px', fontWeight: 800, marginBottom: 12 }}>Chat to Purchase Keywords</div>
            <div style={{ display: 'grid', gap: 8 }}>
              {keywordRows.slice(0, 8).map((row) => (
                <div key={row.keyword} style={{ padding: '10px 12px', borderRadius: 12, background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.16)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                    <strong>{row.keyword}</strong>
                    <span style={{ color: 'var(--accent-blue)' }}>score {row.conversion_score}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                    {row.mentions} mentions · {row.conversions} purchase-linked conversions
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 18, padding: '16px 18px' }}>
          <div style={{ fontSize: '13px', fontWeight: 800, marginBottom: 12 }}>Product Intelligence</div>
          <div style={{ maxHeight: 320, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', paddingBottom: 8, color: 'var(--text-secondary)' }}>Product</th>
                  <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Revenue</th>
                  <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Profit</th>
                  <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Margin%</th>
                  <th style={{ textAlign: 'right', paddingBottom: 8, color: 'var(--text-secondary)' }}>Competition</th>
                  <th style={{ textAlign: 'left', paddingBottom: 8, color: 'var(--text-secondary)' }}>Best Time</th>
                </tr>
              </thead>
              <tbody>
                {productRows.slice(0, 12).map((row, index) => (
                  <tr key={`${row.product_name}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 0', fontWeight: 700 }}>{row.product_name}</td>
                    <td style={{ padding: '8px 0', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(row.revenue)}</td>
                    <td style={{ padding: '8px 0', textAlign: 'right', color: clrProfit(row.profit), fontWeight: 700 }}>{fmt(row.profit)}</td>
                    <td style={{ padding: '8px 0', textAlign: 'right' }}>{row.margin_pct}%</td>
                    <td style={{ padding: '8px 0', textAlign: 'right' }}>{row.competition_score}</td>
                    <td style={{ padding: '8px 0' }}>
                      {row.best_day || '—'}{row.best_hour != null ? ` · ${String(row.best_hour).padStart(2, '0')}:00` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(intelligence.data_limits || []).length ? (
            <div style={{ marginTop: 12, fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {intelligence.data_limits.map((item, index) => <div key={index}>{item}</div>)}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const chartOptions = [
    {
      id: 'livestream-intelligence',
      label: 'AI • Livestream Intelligence',
      subtitle: 'Profit windows, best days, buyer behavior, chat conversion, product intelligence, and live recommendations',
      insights: {
        meaning: 'Turns your historical sessions and live events into schedule, conversion, buyer, and product recommendations.',
        good: 'Best days and hours are clear, high-value buyers repeat, chat keywords correlate with wins, and top products stay profitable.',
        bad: 'Revenue is spread randomly, conversion is weak, buyers do not repeat, and profitable products are hard to identify.',
        action: 'Use this view to decide when to go live, what to sell first, which buyers matter most, and what to change mid-stream.',
      },
      signal: intelligence?.live_mode?.running ? { text: 'Live Mode Active', bg: 'rgba(34,197,94,0.15)', color: '#34d399', border: 'rgba(34,197,94,0.3)' } : null,
      controls: null,
      body: renderIntelligence(),
      fullscreen: renderIntelligence(),
    },
    {
      id: 'revenue-trend',
      label: 'Session • Revenue Trend',
      subtitle: 'Per-session revenue & cumulative growth · drag brush to zoom',
      insights: {
        meaning: 'Shows how session revenue changes over time and whether total business growth is compounding.',
        good: 'Later sessions trend upward and cumulative revenue rises steadily without long flat periods.',
        bad: 'Revenue is flat, volatile, or declining across recent sessions.',
        action: 'Review show timing, lot mix, pricing, and audience retention when recent sessions underperform.',
      },
      signal: null,
      controls: <ToggleGroup options={[{id:'area',label:'Area'},{id:'line',label:'Line'},{id:'bar',label:'Bar'}]} value={chart1Mode} onChange={setChart1Mode} />,
      body: renderC1(320),
      fullscreen: renderC1(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'revenue-profit',
      label: 'Session • Revenue vs Profit',
      subtitle: 'Side-by-side or stacked bars per session',
      insights: {
        meaning: 'Compares sales dollars to the dollars you actually keep after product cost and fees.',
        good: 'Profit grows alongside revenue and does not lag too far behind sales.',
        bad: 'Revenue looks strong but profit stays small, inconsistent, or negative.',
        action: 'Tighten pricing, reduce weak-margin products, and watch fees or bundle composition.',
      },
      signal: null,
      controls: <ToggleGroup options={[{id:'grouped',label:'Grouped'},{id:'stacked',label:'Stacked'}]} value={chart2Mode} onChange={setChart2Mode} />,
      body: renderC2(320),
      fullscreen: renderC2(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'stock-market',
      label: 'Session • Stock-Market Chart',
      subtitle: 'Revenue as price with SMA, EMA, Bollinger Bands, and predictions',
      insights: {
        meaning: 'Treats session revenue like a trend chart so momentum and direction are easier to spot.',
        good: 'Revenue stays above moving averages and the trend line points upward.',
        bad: 'Revenue breaks below trend lines and momentum softens across recent sessions.',
        action: 'Use this as an early warning that the current session formula may be losing strength.',
      },
      signal: sig,
      controls: <ToggleGroup options={[{id:'all',label:'All'},{id:'5',label:'Last 5'},{id:'3',label:'Last 3'}]} value={chart3Frame} onChange={setChart3Frame} />,
      body: (
        <>
          {renderStock(360)}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 6 }}>
            Dashed = Bollinger Bands · red dots = linear-regression prediction · drag brush to zoom
          </div>
        </>
      ),
      fullscreen: (
        <>
          {renderStock(Math.round(window.innerHeight * 0.75))}
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Dashed = Bollinger Bands · red dots = linear-regression prediction · drag brush to zoom
          </div>
        </>
      ),
    },
    {
      id: 'rsi',
      label: 'Indicators • RSI',
      subtitle: 'Relative Strength Index · period 7 · overbought and oversold zones',
      insights: {
        meaning: 'Measures whether recent session performance is running unusually hot or unusually weak.',
        good: 'RSI stays in a balanced middle zone instead of extreme spikes.',
        bad: 'Very high RSI can signal unsustainable performance, while very low RSI can show recent weakness.',
        action: 'Use with business charts, not alone, to confirm whether momentum is overheating or recovering.',
      },
      signal: rsiSignal,
      controls: null,
      body: renderRsi(320),
      fullscreen: renderRsi(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'macd',
      label: 'Indicators • MACD',
      subtitle: 'Histogram = MACD minus signal · crossover = momentum shift',
      insights: {
        meaning: 'Shows whether session momentum is strengthening or weakening over time.',
        good: 'Bullish crossover with improving histogram supports upward business momentum.',
        bad: 'Bearish crossover and weakening histogram suggest fading strength.',
        action: 'Pair this with revenue and margin charts before changing strategy.',
      },
      signal: macdSignal,
      controls: null,
      body: renderMacd(320),
      fullscreen: renderMacd(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'category-radar',
      label: 'Products • Category Radar',
      subtitle: 'Revenue, volume, and margin across product categories',
      insights: {
        meaning: 'Compares which categories drive sales, sell-through, and profit quality.',
        good: 'Strong categories perform well in both revenue and margin, not just volume.',
        bad: 'A category dominates volume but contributes weak margin.',
        action: 'Push high-performing categories harder and reprice or reduce weak-margin categories.',
      },
      signal: null,
      controls: null,
      body: renderRadar(340),
      fullscreen: renderRadar(Math.round(window.innerHeight * 0.75)),
    },
    {
      id: 'scatter',
      label: 'Products • Revenue vs Margin Scatter',
      subtitle: 'Each dot is one product · X = revenue · Y = margin',
      insights: {
        meaning: 'Shows which products sell a lot and which products actually make money.',
        good: 'More products cluster in the top-right area with high revenue and high margin.',
        bad: 'Too many products sit low on margin, especially if they still generate high revenue.',
        action: 'Protect top-right products, fix bottom-right pricing, and cut weak bottom-left items.',
      },
      signal: null,
      controls: null,
      body: renderScatter(340),
      fullscreen: renderScatter(Math.round(window.innerHeight * 0.75)),
    },
    {
      id: 'buyer-pie',
      label: 'Buyers • Revenue Concentration',
      subtitle: 'Top buyers by total spend',
      insights: {
        meaning: 'Shows how dependent the business is on a small group of top-spending buyers.',
        good: 'Revenue is spread across several meaningful buyers instead of one or two carrying everything.',
        bad: 'One buyer dominates too much of total revenue.',
        action: 'Protect key buyers but work to broaden the buyer base through better onboarding and follow-up.',
      },
      signal: null,
      controls: null,
      body: renderPie(340),
      fullscreen: renderPie(Math.round(window.innerHeight * 0.78)),
    },
    {
      id: 'inventory',
      label: 'Inventory • Stock vs Reorder',
      subtitle: 'Green = on-hand · red = reorder threshold',
      insights: {
        meaning: 'Shows which products are close to running out and which may be overstocked.',
        good: 'High-demand items stay above reorder level without piling up excessive stock.',
        bad: 'Fast movers are understocked or slow movers are tying up too much inventory.',
        action: 'Reorder proven winners and avoid replenishing inventory that is not converting well.',
      },
      signal: null,
      controls: null,
      body: renderInv(340),
      fullscreen: renderInv(Math.round(window.innerHeight * 0.78)),
    },
    {
      id: 'velocity',
      label: 'Session • Velocity',
      subtitle: 'Lots sold, dropped, and average sale price per session',
      insights: {
        meaning: 'Measures how efficiently each session converts lots into sold revenue.',
        good: 'Lots sold stays high, dropped lots stay low, and average sale price remains healthy.',
        bad: 'Dropped lots rise or average sale price falls while volume stays flat.',
        action: 'Adjust lot quality, sequencing, and opening pricing when velocity weakens.',
      },
      signal: null,
      controls: <ToggleGroup options={[{id:'combo',label:'All'},{id:'lots',label:'Lots'},{id:'price',label:'Price'}]} value={chart10Mode} onChange={setChart10Mode} />,
      body: renderVelocity(320),
      fullscreen: renderVelocity(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'margin-quality',
      label: 'Session • Margin Quality',
      subtitle: 'Which sessions are profitable enough, not just high-revenue',
      insights: {
        meaning: 'Highlights whether sessions are healthy financially, not just visually strong on sales.',
        good: 'Margin stays above your acceptable range while profit dollars remain positive.',
        bad: 'High revenue sessions still post weak margin.',
        action: 'This is one of the best charts for pricing discipline and sourcing quality decisions.',
      },
      signal: null,
      controls: null,
      body: renderMarginQuality(320),
      fullscreen: renderMarginQuality(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'lot-efficiency',
      label: 'Session • Revenue per Lot',
      subtitle: 'Revenue per lot and items per lot for lot-building decisions',
      insights: {
        meaning: 'Shows how much each lot earns and whether adding more items is paying off.',
        good: 'Revenue per lot rises without needing too many extra items per lot.',
        bad: 'Items per lot increase but revenue per lot barely improves.',
        action: 'Rework bundling strategy and avoid overstuffing lots that do not command better prices.',
      },
      signal: null,
      controls: null,
      body: renderLotEfficiency(320),
      fullscreen: renderLotEfficiency(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'buyer-conversion',
      label: 'Sales • Buyer Conversion',
      subtitle: latestEndedStream ? `Latest ended stream: ${latestEndedStream.name || 'Stream report'}` : 'Post-show buyer follow-up funnel',
      insights: {
        meaning: 'Tracks how auction winners move into profiles and then into sale orders after the stream.',
        good: 'A strong portion of winners become profiles and sale orders.',
        bad: 'Many winners never convert into structured follow-up business.',
        action: 'Improve post-show workflow, customer capture, and sales-order follow-through.',
      },
      signal: null,
      controls: null,
      body: (
        <>
          {renderBuyerConversion(300)}
          {latestEndedStream ? (
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
              Winners: {c13[0]?.value || 0} · Profiles made: {profileCount || 0} · Sale orders: {saleOrderCount || 0}
            </div>
          ) : null}
        </>
      ),
      fullscreen: renderBuyerConversion(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'basket-size',
      label: 'Sales • Basket Size Mix',
      subtitle: latestEndedStream ? 'Order count by item quantity in the latest ended stream' : 'Basket size distribution',
      insights: {
        meaning: 'Shows whether customers tend to buy single items or multiple items in one order.',
        good: 'You see healthy movement into 2-item, 3-item, and 4+ item baskets.',
        bad: 'Almost all sales are single-item orders.',
        action: 'Use bundling, complementary offers, and better session flow to increase average basket size.',
      },
      signal: null,
      controls: null,
      body: renderBasketSize(300),
      fullscreen: renderBasketSize(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'session-volume',
      label: 'Session • Products vs Lots',
      subtitle: 'Per-session sold products compared with lots sold',
      insights: {
        meaning: 'Shows whether sessions rely more on single-item lots or larger grouped lots.',
        good: 'Product count and lot count move in a balanced way that supports margin.',
        bad: 'Products sold per session rise mainly because bundles are getting larger without better profit.',
        action: 'Compare this chart with margin and revenue-per-lot before changing bundle size.',
      },
      signal: null,
      controls: null,
      body: renderSessionVolume(320),
      fullscreen: renderSessionVolume(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'sale-price-bands',
      label: 'Sales • Sale Price Bands',
      subtitle: 'How many wins land in each selling-price bucket',
      insights: {
        meaning: 'Shows where most winning prices fall across low, mid, and higher ticket ranges.',
        good: 'Sales are spread into healthy mid and higher bands, not trapped at the bottom.',
        bad: 'Most wins cluster only in low-price ranges.',
        action: 'Use this to evaluate whether your audience is accepting higher-value lots and pricing.',
      },
      signal: null,
      controls: null,
      body: renderSalePriceBands(320),
      fullscreen: renderSalePriceBands(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'buyer-value',
      label: 'Buyers • Spend vs Wins',
      subtitle: 'Top buyers by total spend and number of auction wins',
      insights: {
        meaning: 'Separates buyers who win often from buyers who create the most revenue.',
        good: 'Several buyers show both healthy spend and repeat wins.',
        bad: 'Wins are frequent but low-value, or one buyer dominates too heavily.',
        action: 'Identify VIP buyers for retention while also growing mid-tier buyers into repeat spenders.',
      },
      signal: null,
      controls: null,
      body: renderBuyerValue(320),
      fullscreen: renderBuyerValue(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'top-products',
      label: 'Products • Top Sellers',
      subtitle: 'Top products by revenue with profit beside them',
      insights: {
        meaning: 'Shows which products are carrying sales and whether they also carry profit.',
        good: 'Top-selling products also create solid profit.',
        bad: 'Top products generate revenue but weak or disappointing profit.',
        action: 'Protect and restock strong winners, and fix pricing on high-volume weak-margin items.',
      },
      signal: null,
      controls: null,
      body: renderTopProducts(320),
      fullscreen: renderTopProducts(Math.round(window.innerHeight * 0.72)),
    },
    {
      id: 'low-margin-products',
      label: 'Products • Low Margin Risk',
      subtitle: 'Lowest-margin sold products so pricing issues stand out',
      insights: {
        meaning: 'Surfaces the sold products most likely dragging profitability down.',
        good: 'Even weaker products remain above your acceptable margin floor.',
        bad: 'Products are repeatedly sold near break-even or at poor margin.',
        action: 'Reprice, source cheaper, rebundle, or reduce emphasis on these risky products.',
      },
      signal: null,
      controls: null,
      body: renderLowMarginProducts(320),
      fullscreen: renderLowMarginProducts(Math.round(window.innerHeight * 0.72)),
    },
  ];

  const activeChart = chartOptions.find((chart) => chart.id === selectedChart) || chartOptions[0];

  // ── Signal banner ─────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* Global signal banner */}
      {sig && (
        <div style={{ padding: '14px 20px', borderRadius: 14, background: sig.bg, border: `1px solid ${sig.border}`, display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 17, fontWeight: 900, color: sig.color }}>{sig.text}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
            RSI <b style={{ color: lastRsi > 70 ? '#f87171' : lastRsi < 30 ? '#34d399' : '#fbbf24' }}>{lastRsi ?? '—'}</b>
            {' · '}MACD <b style={{ color: lastML > lastMS ? '#34d399' : '#f87171' }}>{lastML > lastMS ? 'above signal ↑' : 'below signal ↓'}</b>
            {' · '}Slope <b>{slope > 0 ? `+$${slope}` : `$${slope}`}/session</b>
            {' · '}Next predicted: <b style={{ color: '#fbbf24' }}>{fmtK(nextPred)}</b>
          </div>
        </div>
      )}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
        padding: '14px 18px',
        borderRadius: 16,
        background: 'linear-gradient(135deg, rgba(251,191,36,0.12), rgba(129,140,248,0.08))',
        border: '1px solid var(--border-default)',
      }}>
        <div style={{ minWidth: 0, flex: '1 1 240px' }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            Chart Selector
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
            One chart page with a dropdown for switching between indicators.
          </div>
        </div>
        <select
          value={selectedChart}
          onChange={(event) => setSelectedChart(event.target.value)}
          className="company-input chart-selector-input"
          style={{
            minWidth: 280,
            maxWidth: '100%',
            padding: '10px 14px',
            borderRadius: 12,
            border: '1px solid rgba(251,191,36,0.28)',
            background: 'linear-gradient(135deg, #111827 0%, #1f2937 100%)',
            color: '#f9fafb',
            colorScheme: 'dark',
            fontSize: 13,
            fontWeight: 700,
            boxShadow: '0 10px 26px rgba(0,0,0,0.22)',
          }}
        >
          {chartOptions.map((chart) => (
            <option key={chart.id} value={chart.id}>{chart.label}</option>
          ))}
        </select>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 12,
      }}>
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 16, padding: '14px 16px' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
            What It Means
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
            {activeChart.insights?.meaning}
          </div>
        </div>
        <div style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.18)', borderRadius: 16, padding: '14px 16px' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: '#34d399', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
            What Good Looks Like
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
            {activeChart.insights?.good}
          </div>
        </div>
        <div style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.18)', borderRadius: 16, padding: '14px 16px' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: '#f87171', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
            What Bad Looks Like
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
            {activeChart.insights?.bad}
          </div>
        </div>
        <div style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.18)', borderRadius: 16, padding: '14px 16px' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
            Action To Take
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.6 }}>
            {activeChart.insights?.action}
          </div>
        </div>
      </div>

      <ChartCard
        id={activeChart.id}
        title={activeChart.label}
        subtitle={activeChart.subtitle}
        signal={activeChart.signal}
        controls={activeChart.controls}
        fullscreenContent={activeChart.fullscreen}
      >
        {activeChart.body}
      </ChartCard>

    </div>
  );
}
