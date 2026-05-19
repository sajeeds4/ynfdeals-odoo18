import { useEffect, useMemo, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import { KpiCard, PrimaryBtn, TableShell, Thead, EmptyRow, fmtDt } from './utils';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, LineChart, Line, AreaChart, Area, ComposedChart, Legend,
} from 'recharts';

const fmt = (n) => (n == null ? '--' : `$${Number(n).toFixed(2)}`);
const fmtQty = (n) => (n == null ? '--' : Number(n).toLocaleString());
const fmtPct = (n) => (n == null ? '--' : `${Number(n).toFixed(1)}%`);

const SOURCE_LABELS = {
  whatnot: 'Whatnot Auctions',
  tiktok_live: 'TikTok LIVE Auctions',
  tiktok_shop: 'TikTok Shop Sales',
  in_house: 'In-House Employee Sales',
};
const SOURCE_COLORS = {
  whatnot: '#f59e0b',
  tiktok_live: '#10b981',
  tiktok_shop: '#06b6d4',
  in_house: '#6366f1',
};

export default function MegaDashboard({ onTabChange }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadedAt, setLoadedAt] = useState(null);

  function load() {
    setLoading(true);
    fetchApi('/api/company/mega_dashboard')
      .then((payload) => {
        setData(payload || {});
        setLoadedAt(new Date());
      })
      .catch(() => setData({}))
      .finally(() => setLoading(false));
  }

  useEffect(() => { load(); }, []);

  const totals = data?.totals || {};
  const sources = data?.sources || {};
  const sourceRows = useMemo(() => (
    Object.entries(sources).map(([key, row]) => ({
      key,
      label: SOURCE_LABELS[key] || key,
      ...row,
      margin_pct: Number(row.revenue || 0) ? (Number(row.profit || 0) / Number(row.revenue || 0)) * 100 : 0,
    }))
  ), [sources]);
  const sessionTrend = useMemo(() => (
    [...(data?.recent_sessions || [])]
      .reverse()
      .map((session) => ({
        name: String(session.name || `S${session.id}`).replace(/^(.{18}).+$/, '$1...'),
        revenue: Number(session.total_revenue || 0),
        profit: Number(session.total_profit || 0),
        lots: Number(session.total_lots_sold || 0),
      }))
  ), [data?.recent_sessions]);
  const mixRows = sourceRows
    .filter((row) => Number(row.revenue || 0) > 0)
    .map((row) => ({ name: row.label, value: Number(row.revenue || 0), key: row.key }));
  const inventoryHealthRows = [
    { name: 'Low Stock', value: Number(data?.inventory?.low_stock_count || 0), fill: '#f59e0b' },
    { name: 'Out', value: Number(data?.inventory?.out_of_stock_count || 0), fill: '#ef4444' },
    { name: 'No Image', value: Number(data?.inventory?.missing_image_count || 0), fill: '#06b6d4' },
    { name: 'Unverified', value: Number(data?.inventory?.unverified_notes_count || 0), fill: '#8b5cf6' },
  ];
  const dailyRows = useMemo(() => (
    (data?.daily_performance || []).map((row) => ({
      ...row,
      label: row.day ? new Date(`${row.day}T00:00:00`).toLocaleDateString([], { month: 'short', day: 'numeric' }) : 'Unknown',
      revenue: Number(row.revenue || 0),
      profit: Number(row.profit || 0),
      margin_pct: Number(row.margin_pct || 0),
      whatnot: Number(row.whatnot || 0),
      tiktok_live: Number(row.tiktok_live || 0),
      tiktok_shop: Number(row.tiktok_shop || 0),
      in_house: Number(row.in_house || 0),
    }))
  ), [data?.daily_performance]);
  const paymentRows = useMemo(() => (
    (data?.payment_status || []).map((row) => ({
      status: formatStatus(row.status),
      count: Number(row.count || 0),
      live_revenue: Number(row.live_revenue || 0),
      held_revenue: Number(row.held_revenue || 0),
    }))
  ), [data?.payment_status]);
  const customerRows = useMemo(() => (
    (data?.top_customers || []).map((row) => ({
      customer: row.customer || 'Unknown',
      wins: Number(row.wins || 0),
      revenue: Number(row.revenue || 0),
      profit: Number(row.profit || 0),
    }))
  ), [data?.top_customers]);
  const sourcePerformance = useMemo(() => {
    const maxRevenue = Math.max(1, ...sourceRows.map((row) => Number(row.revenue || 0)));
    return sourceRows
      .map((row) => ({
        ...row,
        revenueShare: Number(totals.revenue || 0) ? (Number(row.revenue || 0) / Number(totals.revenue || 0)) * 100 : 0,
        profitShare: Number(totals.profit || 0) ? (Number(row.profit || 0) / Math.max(1, Number(totals.profit || 0))) * 100 : 0,
        efficiency: Number(row.revenue || 0) ? ((Number(row.profit || 0) - Number(row.fees || 0)) / Number(row.revenue || 0)) * 100 : 0,
        intensity: (Number(row.revenue || 0) / maxRevenue) * 100,
      }))
      .sort((a, b) => Number(b.revenue || 0) - Number(a.revenue || 0));
  }, [sourceRows, totals.profit, totals.revenue]);
  const productLeaders = useMemo(() => {
    const maxRevenue = Math.max(1, ...(data?.top_products || []).map((row) => Number(row.revenue || 0)));
    return (data?.top_products || []).map((row) => ({
      ...row,
      intensity: (Number(row.revenue || 0) / maxRevenue) * 100,
      margin_pct: Number(row.revenue || 0) ? (Number(row.profit || 0) / Number(row.revenue || 0)) * 100 : 0,
    }));
  }, [data?.top_products]);
  const advanced = useMemo(() => {
    const revenue = Number(totals.revenue || 0);
    const profit = Number(totals.profit || 0);
    const fees = Number(totals.fees || 0);
    const cost = Number(totals.cost || 0);
    const ordersWins = Number(totals.orders || 0) + Number(totals.results || 0);
    const topCustomerRevenue = customerRows.reduce((sum, row) => sum + Number(row.revenue || 0), 0);
    const bestSource = [...sourceRows].sort((a, b) => Number(b.profit || 0) - Number(a.profit || 0))[0];
    const riskCount = Number(data?.inventory?.low_stock_count || 0) + Number(data?.inventory?.out_of_stock_count || 0) + Number(data?.inventory?.missing_image_count || 0);
    return {
      avgTicket: ordersWins ? revenue / ordersWins : 0,
      feeRate: revenue ? (fees / revenue) * 100 : 0,
      costRate: revenue ? (cost / revenue) * 100 : 0,
      profitPerUnit: Number(totals.units || 0) ? profit / Number(totals.units || 0) : 0,
      topCustomerShare: revenue ? (topCustomerRevenue / revenue) * 100 : 0,
      bestSource,
      riskScore: Math.min(100, Math.round(riskCount * 0.7)),
    };
  }, [customerRows, data?.inventory, sourceRows, totals]);

  const health = [
    { label: 'Inventory Value', value: fmt(data?.inventory?.total_stock_value || 0), tab: 'inventory' },
    { label: 'Low Stock', value: fmtQty(data?.inventory?.low_stock_count || 0), tab: 'inventory' },
    { label: 'Out Of Stock', value: fmtQty(data?.inventory?.out_of_stock_count || 0), tab: 'inventory' },
    { label: 'Missing Images', value: fmtQty(data?.inventory?.missing_image_count || 0), tab: 'inventory' },
    { label: 'Unverified Notes', value: fmtQty(data?.inventory?.unverified_notes_count || 0), tab: 'inventory' },
    { label: 'Customers', value: fmtQty(data?.customers?.count || 0), tab: 'customers' },
  ];

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {/* ── Hero Banner ── */}
      <section style={{
        borderRadius: 24,
        padding: '28px 28px 24px',
        background: 'linear-gradient(135deg, #0d0d1a 0%, #12122a 40%, #1a1040 100%)',
        border: '1px solid rgba(139,92,246,0.25)',
        boxShadow: '0 0 0 1px rgba(139,92,246,0.08), 0 24px 64px rgba(0,0,0,0.5), 0 0 80px rgba(139,92,246,0.08)',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* glow orbs */}
        <div style={{ position:'absolute', top:-60, left:-40, width:280, height:280, borderRadius:'50%', background:'radial-gradient(circle, rgba(139,92,246,0.18) 0%, transparent 70%)', pointerEvents:'none' }} />
        <div style={{ position:'absolute', bottom:-80, right:-20, width:320, height:320, borderRadius:'50%', background:'radial-gradient(circle, rgba(245,158,11,0.10) 0%, transparent 70%)', pointerEvents:'none' }} />
        <div style={{ position:'relative', display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:20, flexWrap:'wrap' }}>
          <div>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:10 }}>
              <div style={{ width:8, height:8, borderRadius:'50%', background:'#10b981', boxShadow:'0 0 8px #10b981' }} />
              <span style={{ fontSize:10, fontWeight:800, letterSpacing:'0.18em', textTransform:'uppercase', color:'rgba(255,255,255,0.4)' }}>Company Command Center</span>
            </div>
            <div style={{ fontSize:34, fontWeight:900, letterSpacing:'-0.03em', color:'#fff', lineHeight:1.1 }}>
              Mega Dashboard
            </div>
            <div style={{ marginTop:8, fontSize:13, color:'rgba(255,255,255,0.45)', maxWidth:520 }}>
              Unified view · Auctions · TikTok · In-House · Revenue · Profit · Inventory
            </div>
            <div style={{ marginTop:16, display:'flex', gap:10, flexWrap:'wrap' }}>
              <HeroPill label="Revenue" value={fmt(totals.revenue || 0)} color="#f59e0b" />
              <HeroPill label="Profit" value={fmt(totals.profit || 0)} color={Number(totals.profit||0)>=0?'#10b981':'#f43f5e'} />
              <HeroPill label="Margin" value={fmtPct(totals.margin_pct || 0)} color="#8b5cf6" />
              <HeroPill label="Ops Risk" value={`${advanced.riskScore}/100`} color={advanced.riskScore>=55?'#f43f5e':'#10b981'} />
            </div>
          </div>
          <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:10 }}>
            <button
              onClick={load}
              style={{ padding:'10px 22px', borderRadius:12, background:'linear-gradient(135deg,#8b5cf6,#6d28d9)', color:'#fff', border:'1px solid rgba(139,92,246,0.5)', fontWeight:700, fontSize:13, cursor:'pointer', boxShadow:'0 0 20px rgba(139,92,246,0.3)', letterSpacing:'0.02em' }}
            >{loading ? '⟳ Loading…' : '↻ Refresh'}</button>
            <div style={{ fontSize:11, color:'rgba(255,255,255,0.3)', fontWeight:600 }}>
              {loadedAt ? `Updated ${loadedAt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'})}` : 'Awaiting load…'}
            </div>
          </div>
        </div>
      </section>

      {/* ── KPI Strip ── */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))', gap:12 }}>
        {[
          { label:'Revenue',     value:fmt(totals.revenue||0),   color:'#f59e0b', icon:'💰', tab:'orders' },
          { label:'Profit',      value:fmt(totals.profit||0),    color:Number(totals.profit||0)>=0?'#10b981':'#f43f5e', icon:'📈', tab:'auction-results' },
          { label:'Cost',        value:fmt(totals.cost||0),      color:'#94a3b8', icon:'🏷️', tab:'inventory' },
          { label:'Fees',        value:fmt(totals.fees||0),      color:'#f43f5e', icon:'💸' },
          { label:'Margin',      value:fmtPct(totals.margin_pct||0), color:Number(totals.margin_pct||0)>=20?'#10b981':'#f59e0b', icon:'📊' },
          { label:'Units Sold',  value:fmtQty(totals.units||0), color:'#60a5fa', icon:'📦' },
          { label:'Orders/Wins', value:fmtQty((totals.orders||0)+(totals.results||0)), color:'#a78bfa', icon:'🏆' },
          { label:'Sessions',    value:fmtQty(totals.sessions||0), color:'#34d399', icon:'🎥', tab:'sessions' },
        ].map((k) => (
          <div
            key={k.label}
            onClick={() => k.tab && onTabChange?.(k.tab)}
            style={{ borderRadius:16, padding:'16px 14px', background:'var(--bg-panel)', border:'1px solid var(--border-default)', boxShadow:'var(--shadow-card)', cursor:k.tab?'pointer':'default', transition:'transform 120ms', position:'relative', overflow:'hidden' }}
            onMouseEnter={(e)=>{ if(k.tab) e.currentTarget.style.transform='translateY(-2px)'; }}
            onMouseLeave={(e)=>{ e.currentTarget.style.transform='translateY(0)'; }}
          >
            <div style={{ position:'absolute', top:0, left:0, right:0, height:3, background:`linear-gradient(90deg, ${k.color}, ${k.color}44)`, borderRadius:'16px 16px 0 0' }} />
            <div style={{ fontSize:18, marginBottom:8 }}>{k.icon}</div>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-muted)', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:6 }}>{k.label}</div>
            <div style={{ fontSize:22, fontWeight:900, color:k.color, letterSpacing:'-0.02em', lineHeight:1 }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* ── Advanced Metric Tiles ── */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))', gap:12 }}>
        {[
          { label:'Avg Ticket',         value:fmt(advanced.avgTicket),        sub:'Revenue ÷ orders & wins',          tone:'#f59e0b', icon:'🎫' },
          { label:'Profit / Unit',      value:fmt(advanced.profitPerUnit),     sub:'Real margin quality per item',     tone:'#10b981', icon:'💎' },
          { label:'Fee Rate',           value:fmtPct(advanced.feeRate),        sub:'Fees as % of revenue',             tone:'#f43f5e', icon:'⚡' },
          { label:'Buyer Concentration',value:fmtPct(advanced.topCustomerShare),sub:'Revenue in top customers',       tone:'#6366f1', icon:'👥' },
        ].map((m) => (
          <div key={m.label} style={{ borderRadius:18, padding:'18px 16px', background:`linear-gradient(145deg, ${m.tone}15 0%, var(--bg-panel) 60%)`, border:`1px solid ${m.tone}30`, boxShadow:`0 0 0 1px ${m.tone}10, var(--shadow-card)` }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
              <span style={{ fontSize:20 }}>{m.icon}</span>
              <span style={{ fontSize:11, fontWeight:800, color:m.tone, textTransform:'uppercase', letterSpacing:'0.08em' }}>{m.label}</span>
            </div>
            <div style={{ fontSize:28, fontWeight:900, color:'var(--text-primary)', letterSpacing:'-0.03em', lineHeight:1 }}>{m.value}</div>
            <div style={{ marginTop:8, fontSize:12, color:'var(--text-secondary)', lineHeight:1.4 }}>{m.sub}</div>
          </div>
        ))}
      </div>

      <section style={glassPanelStyle}>
        <div style={{ ...panelHeadStyle, background: 'transparent' }}>
          <div>Source Performance Matrix</div>
          <span>Advanced channel readout</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12, padding: 14 }}>
          {sourcePerformance.length ? sourcePerformance.map((row) => (
            <SourceCard
              key={row.key}
              label={row.label}
              revenue={row.revenue}
              profit={row.profit}
              margin={row.margin_pct}
              revenueShare={row.revenueShare}
              efficiency={row.efficiency}
              intensity={row.intensity}
              color={SOURCE_COLORS[row.key] || '#94a3b8'}
            />
          )) : <div style={emptyStyle}>No source performance data yet.</div>}
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.3fr) minmax(300px, 0.7fr)', gap: 16, alignItems: 'stretch' }}>
        <ChartCard title="Revenue / Profit By Channel" sub="Fast view of where the money is coming from">
          <ResponsiveContainer width="100%" height={270}>
            <BarChart data={sourceRows} margin={{ top: 8, right: 12, left: 0, bottom: 44 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="label" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} angle={-22} textAnchor="end" interval={0} />
              <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `$${value}`} width={58} />
              <Tooltip content={<MoneyTooltip />} />
              <Bar dataKey="revenue" name="Revenue" fill="#f59e0b" radius={[5, 5, 0, 0]} />
              <Bar dataKey="profit" name="Profit" fill="#10b981" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Revenue Mix" sub="Channel share">
          {mixRows.length ? (
            <ResponsiveContainer width="100%" height={270}>
              <PieChart>
                <Pie data={mixRows} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={58} outerRadius={92} paddingAngle={3}>
                  {mixRows.map((entry) => <Cell key={entry.key} fill={SOURCE_COLORS[entry.key] || '#94a3b8'} />)}
                </Pie>
                <Tooltip content={<MoneyTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div style={emptyChartStyle}>No revenue yet.</div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, padding: '0 14px 14px' }}>
            {mixRows.map((row) => (
              <span key={row.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)' }}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: SOURCE_COLORS[row.key] || '#94a3b8' }} />
                {row.name}
              </span>
            ))}
          </div>
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 16 }}>
        <ChartCard title="30-Day Channel Revenue" sub="Stacked by Whatnot, TikTok, and in-house">
          {dailyRows.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={dailyRows} margin={{ top: 8, right: 14, left: 0, bottom: 28 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="label" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `$${value}`} width={58} />
                <Tooltip content={<MoneyTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11, fontWeight: 800 }} />
                <Bar dataKey="whatnot" name="Whatnot" stackId="a" fill={SOURCE_COLORS.whatnot} radius={[0, 0, 0, 0]} />
                <Bar dataKey="tiktok_live" name="TikTok LIVE" stackId="a" fill={SOURCE_COLORS.tiktok_live} radius={[0, 0, 0, 0]} />
                <Bar dataKey="tiktok_shop" name="TikTok Shop" stackId="a" fill={SOURCE_COLORS.tiktok_shop} radius={[0, 0, 0, 0]} />
                <Bar dataKey="in_house" name="In-House" stackId="a" fill={SOURCE_COLORS.in_house} radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={emptyChartStyle}>No daily revenue yet.</div>}
        </ChartCard>

        <ChartCard title="Profit + Margin Trend" sub="Profit bars with margin line">
          {dailyRows.length ? (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={dailyRows} margin={{ top: 8, right: 14, left: 0, bottom: 28 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="label" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis yAxisId="money" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `$${value}`} width={58} />
                <YAxis yAxisId="pct" orientation="right" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `${value}%`} width={48} />
                <Tooltip content={<SmartTooltip />} />
                <Bar yAxisId="money" dataKey="profit" name="Profit" fill="#10b981" radius={[5, 5, 0, 0]} />
                <Line yAxisId="pct" type="monotone" dataKey="margin_pct" name="Margin %" stroke="#6366f1" strokeWidth={3} dot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          ) : <div style={emptyChartStyle}>No profit trend yet.</div>}
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 16 }}>
        <ChartCard title="Recent Session Trend" sub="Revenue and profit across the latest sessions">
          {sessionTrend.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={sessionTrend} margin={{ top: 8, right: 14, left: 0, bottom: 42 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} angle={-22} textAnchor="end" interval={0} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `$${value}`} width={58} />
                <Tooltip content={<MoneyTooltip />} />
                <Line type="monotone" dataKey="revenue" name="Revenue" stroke="#f59e0b" strokeWidth={3} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="profit" name="Profit" stroke="#10b981" strokeWidth={3} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div style={emptyChartStyle}>No session trend yet.</div>}
        </ChartCard>

        <ChartCard title="Inventory Cleanup Load" sub="What blocks clean selling">
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={inventoryHealthRows} margin={{ top: 8, right: 14, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
              <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={45} />
              <Tooltip />
              <Area type="monotone" dataKey="value" stroke="#8b5cf6" fill="rgba(139,92,246,0.22)" strokeWidth={3} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 16 }}>
        <ChartCard title="Payment Risk Exposure" sub="Confirmed vs review/cancelled impact">
          {paymentRows.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={paymentRows} margin={{ top: 8, right: 14, left: 0, bottom: 32 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis dataKey="status" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={45} />
                <Tooltip content={<SmartTooltip />} />
                <Bar dataKey="count" name="Lots" fill="#6366f1" radius={[5, 5, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={emptyChartStyle}>No payment status data yet.</div>}
        </ChartCard>

        <ChartCard title="Top Buyer Concentration" sub="Buyer revenue and profit quality">
          {customerRows.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={customerRows.slice(0, 8)} layout="vertical" margin={{ top: 8, right: 14, left: 24, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
                <XAxis type="number" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} tickFormatter={(value) => `$${value}`} />
                <YAxis type="category" dataKey="customer" width={120} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} />
                <Tooltip content={<MoneyTooltip />} />
                <Bar dataKey="revenue" name="Revenue" fill="#f59e0b" radius={[0, 5, 5, 0]} />
                <Bar dataKey="profit" name="Profit" fill="#10b981" radius={[0, 5, 5, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div style={emptyChartStyle}>No buyer concentration yet.</div>}
        </ChartCard>
      </div>

      <section style={insightPanelStyle}>
        <div style={{ ...panelHeadStyle, borderBottom: 'none', paddingBottom: 4 }}>
          <div>Advanced Algorithmic Signals</div>
          <span>Decision support</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12, padding: 14 }}>
          <InsightCard
            title="Best Channel Right Now"
            value={advanced.bestSource?.label || 'No clear winner'}
            sub={advanced.bestSource ? `${fmt(advanced.bestSource.profit)} profit at ${fmtPct(advanced.bestSource.margin_pct)} margin` : 'Need more sales data.'}
            color="#10b981"
            score={Math.max(0, Math.min(100, Number(advanced.bestSource?.margin_pct || 0) * 2))}
          />
          <InsightCard
            title="Inventory Risk"
            value={`${advanced.riskScore}/100`}
            sub="Combines low stock, out-of-stock, and missing image workload."
            color={advanced.riskScore >= 55 ? '#ef4444' : '#f59e0b'}
            score={advanced.riskScore}
          />
          <InsightCard
            title="Cost Pressure"
            value={fmtPct(advanced.costRate)}
            sub="Cost as share of revenue. Lower is healthier."
            color={advanced.costRate >= 70 ? '#ef4444' : '#6366f1'}
            score={Math.min(100, advanced.costRate)}
          />
          <InsightCard
            title="Buyer Concentration"
            value={fmtPct(advanced.topCustomerShare)}
            sub="If this is high, nurture whales but keep acquiring new buyers."
            color={advanced.topCustomerShare >= 45 ? '#f59e0b' : '#06b6d4'}
            score={Math.min(100, advanced.topCustomerShare)}
          />
        </div>
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
        <ActionCard title="Clean Inventory Notes" value={fmtQty(data?.inventory?.unverified_notes_count || 0)} sub="Products need note verification before confident selling." color="#8b5cf6" onClick={() => onTabChange?.('inventory')} />
        <ActionCard title="Fix Product Images" value={fmtQty(data?.inventory?.missing_image_count || 0)} sub="Missing images hurt scanning and packing speed." color="#06b6d4" onClick={() => onTabChange?.('inventory')} />
        <ActionCard title="Restock Watch" value={fmtQty(data?.inventory?.low_stock_count || 0)} sub="Low stock products need reorder or sell-stop decisions." color="#f59e0b" onClick={() => onTabChange?.('prep')} />
        <ActionCard title="Employee Sales" value={fmt(data?.in_house?.summary?.revenue || 0)} sub="Track at-cost purchases without mixing them into auction orders." color="#6366f1" onClick={() => onTabChange?.('in-house-sales')} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(320px, 0.8fr)', gap: 16, alignItems: 'start' }}>
        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>Revenue, Cost, Profit By Source</div>
            <span>{sourceRows.length} streams</span>
          </div>
          <TableShell footer="Source-level rollup excludes cancelled/payment-review auction results.">
            <Thead cols={[
              { label: 'Source' },
              { label: 'Revenue', align: 'right' },
              { label: 'Cost', align: 'right' },
              { label: 'Fees', align: 'right' },
              { label: 'Profit', align: 'right' },
              { label: 'Margin', align: 'right' },
              { label: 'Units', align: 'right' },
              { label: 'Orders/Wins', align: 'right' },
            ]} />
            <tbody>
              {loading || !sourceRows.length ? <EmptyRow cols={8} loading={loading} msg="No source data yet." /> : null}
              {!loading && sourceRows.map((row) => (
                <tr key={row.key} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={tdStrong}>{row.label}</td>
                  <td style={tdMoney}>{fmt(row.revenue)}</td>
                  <td style={tdRight}>{fmt(row.cost)}</td>
                  <td style={tdRight}>{fmt(row.fees)}</td>
                  <td style={{ ...tdRight, color: Number(row.profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)', fontWeight: 900 }}>{fmt(row.profit)}</td>
                  <td style={tdRight}>{fmtPct(row.margin_pct)}</td>
                  <td style={tdRight}>{fmtQty(row.units)}</td>
                  <td style={tdRight}>{fmtQty((row.orders || 0) + (row.results || 0))}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </section>

        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>Business Health</div>
            <span>Live cleanup</span>
          </div>
          <div style={{ display: 'grid' }}>
            {health.map((row, index) => (
              <button
                key={row.label}
                type="button"
                onClick={() => onTabChange?.(row.tab)}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '12px 14px',
                  border: 'none',
                  borderTop: index ? '1px solid var(--border-subtle)' : 'none',
                  background: 'transparent',
                  color: 'inherit',
                  cursor: 'pointer',
                  textAlign: 'left',
                }}
              >
                <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{row.label}</span>
                <strong>{row.value}</strong>
              </button>
            ))}
          </div>
        </section>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>Recent Sessions</div>
            <button type="button" onClick={() => onTabChange?.('sessions')} style={linkButtonStyle}>Open</button>
          </div>
          {(data?.recent_sessions || []).length ? (data.recent_sessions || []).map((session) => (
            <div key={session.id} style={rowStyle}>
              <div>
                <div style={{ fontWeight: 800 }}>{session.name || `Session ${session.id}`}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 3 }}>{fmtDt(session.started_at || session.ended_at)}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--accent-amber)', fontWeight: 900 }}>{fmt(session.total_revenue)}</div>
                <div style={{ color: Number(session.total_profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)', fontSize: 12, fontWeight: 800 }}>{fmt(session.total_profit)} profit</div>
              </div>
            </div>
          )) : <div style={emptyStyle}>No sessions yet.</div>}
        </section>

        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>Top Products</div>
            <button type="button" onClick={() => onTabChange?.('inventory')} style={linkButtonStyle}>Inventory</button>
          </div>
          {(data?.top_products || []).length ? (data.top_products || []).map((product) => (
            <div key={product.product_name} style={rowStyle}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 800, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.product_name}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 3 }}>{fmtQty(product.units_sold)} units - {fmtQty(product.times_sold)} wins</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: 'var(--accent-amber)', fontWeight: 900 }}>{fmt(product.revenue)}</div>
                <div style={{ color: Number(product.profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)', fontSize: 12, fontWeight: 800 }}>{fmt(product.profit)}</div>
              </div>
            </div>
          )) : <div style={emptyStyle}>No product sales yet.</div>}
        </section>

        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>Product Revenue Leaderboard</div>
            <span>Advanced mix</span>
          </div>
          <div style={{ padding: 14, display: 'grid', gap: 12 }}>
            {productLeaders.length ? productLeaders.slice(0, 6).map((product) => (
              <LeaderboardRow
                key={product.product_name}
                label={product.product_name}
                value={fmt(product.revenue)}
                sub={`${fmt(product.profit)} profit • ${fmtPct(product.margin_pct)} margin`}
                progress={product.intensity}
                color={product.margin_pct >= 20 ? '#10b981' : product.margin_pct >= 10 ? '#f59e0b' : '#ef4444'}
              />
            )) : <div style={emptyStyle}>No product leaderboard yet.</div>}
          </div>
        </section>

        <section style={panelStyle}>
          <div style={panelHeadStyle}>
            <div>In-House Employee Sales</div>
            <button type="button" onClick={() => onTabChange?.('in-house-sales')} style={linkButtonStyle}>Open</button>
          </div>
          <div style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
            <Mini label="Sales" value={fmtQty(data?.in_house?.summary?.sale_count || 0)} />
            <Mini label="Units" value={fmtQty(data?.in_house?.summary?.units_sold || 0)} />
            <Mini label="Revenue" value={fmt(data?.in_house?.summary?.revenue || 0)} />
          </div>
          {(data?.in_house?.by_employee || []).slice(0, 5).map((employee) => (
            <div key={employee.employee_name} style={rowStyle}>
              <div>
                <div style={{ fontWeight: 800 }}>{employee.employee_name}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 3 }}>{fmtQty(employee.units_sold)} units - {employee.sale_count} sales</div>
              </div>
              <div style={{ color: 'var(--accent-amber)', fontWeight: 900 }}>{fmt(employee.revenue)}</div>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function Mini({ label, value }) {
  return (
    <div style={{ border:'1px solid var(--border-subtle)', borderRadius:14, padding:'12px 10px', background:'var(--bg-elevated)', textAlign:'center' }}>
      <div style={{ fontSize:10, color:'var(--text-muted)', fontWeight:800, letterSpacing:'0.1em', textTransform:'uppercase', marginBottom:6 }}>{label}</div>
      <div style={{ fontSize:18, fontWeight:900, color:'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

function ChartCard({ title, sub, children }) {
  return (
    <section style={panelStyle}>
      <div style={panelHeadStyle}>
        <div style={{ color:'var(--text-primary)', fontSize:12 }}>{title}</div>
        <span style={{ fontSize:11, fontWeight:600, color:'var(--text-muted)', textTransform:'none', letterSpacing:'normal' }}>{sub}</span>
      </div>
      <div style={{ padding:'14px 10px 6px' }}>
        {children}
      </div>
    </section>
  );
}

function ActionCard({ title, value, sub, color, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        textAlign: 'left',
        border: `1px solid ${color}35`,
        borderRadius: 20,
        padding: '18px 16px',
        background: `linear-gradient(145deg, ${color}18 0%, var(--bg-panel) 60%)`,
        color: 'var(--text-primary)',
        cursor: 'pointer',
        boxShadow: `0 0 0 1px ${color}10, 0 8px 24px rgba(0,0,0,0.3)`,
        transition: 'transform 120ms, box-shadow 120ms',
        position: 'relative', overflow: 'hidden',
      }}
      onMouseEnter={(e) => { e.currentTarget.style.transform='translateY(-3px)'; e.currentTarget.style.boxShadow=`0 0 0 1px ${color}20, 0 16px 40px rgba(0,0,0,0.4), 0 0 24px ${color}20`; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform='translateY(0)'; e.currentTarget.style.boxShadow=`0 0 0 1px ${color}10, 0 8px 24px rgba(0,0,0,0.3)`; }}
    >
      <div style={{ position:'absolute', top:0, left:0, right:0, height:3, background:`linear-gradient(90deg,${color},${color}44)` }} />
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{ fontSize:10, color, fontWeight:800, letterSpacing:'0.1em', textTransform:'uppercase' }}>{title}</div>
        <span style={{ fontSize:16, opacity:0.5 }}>→</span>
      </div>
      <div style={{ marginTop:10, fontSize:28, fontWeight:900, letterSpacing:'-0.03em', color }}>{value}</div>
      <div style={{ marginTop:6, fontSize:12, color:'var(--text-secondary)', lineHeight:1.4 }}>{sub}</div>
    </button>
  );
}

function MoneyTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 10, padding: '10px 12px', boxShadow: 'var(--shadow-panel)' }}>
      {label ? <div style={{ fontSize: 12, fontWeight: 900, marginBottom: 6 }}>{label}</div> : null}
      {payload.map((item) => (
        <div key={item.dataKey || item.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 18, color: item.color || 'var(--text-primary)', fontSize: 12 }}>
          <span>{item.name || item.dataKey}</span>
          <strong>{fmt(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function SmartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 10, padding: '10px 12px', boxShadow: 'var(--shadow-panel)' }}>
      {label ? <div style={{ fontSize: 12, fontWeight: 900, marginBottom: 6 }}>{label}</div> : null}
      {payload.map((item) => {
        const value = item.value;
        const display = String(item.name || item.dataKey || '').toLowerCase().includes('margin')
          ? fmtPct(value)
          : (String(item.name || item.dataKey || '').toLowerCase().includes('count') || String(item.name || item.dataKey || '').toLowerCase().includes('lot'))
              ? fmtQty(value)
              : fmt(value);
        return (
          <div key={item.dataKey || item.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 18, color: item.color || 'var(--text-primary)', fontSize: 12 }}>
            <span>{item.name || item.dataKey}</span>
            <strong>{display}</strong>
          </div>
        );
      })}
    </div>
  );
}

function MetricTile({ label, value, sub, tone }) {
  return (
    <div style={{
      border: `1px solid ${tone}35`,
      borderRadius: 18,
      padding: '18px 16px',
      background: `linear-gradient(145deg, ${tone}18 0%, var(--bg-panel) 65%)`,
      boxShadow: `0 0 0 1px ${tone}12, 0 8px 24px rgba(0,0,0,0.3)`,
    }}>
      <div style={{ fontSize: 11, color: tone, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 900, letterSpacing: '-0.03em', color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{sub}</div>
    </div>
  );
}

function InsightCard({ title, value, sub, color, score }) {
  const pct = Math.max(0, Math.min(100, Number(score || 0)));
  return (
    <div style={{
      border: `1px solid ${color}35`,
      borderRadius: 20,
      padding: '18px 16px',
      background: `linear-gradient(145deg, ${color}15 0%, var(--bg-panel) 55%)`,
      boxShadow: `0 0 0 1px ${color}10, 0 8px 28px rgba(0,0,0,0.35)`,
      position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position:'absolute', top:0, left:0, right:0, height:3, background:`linear-gradient(90deg,${color},${color}44)` }} />
      <div style={{ display:'flex', justifyContent:'space-between', gap:10, alignItems:'center', marginBottom:10 }}>
        <div style={{ fontSize:10, color, fontWeight:800, letterSpacing:'0.1em', textTransform:'uppercase' }}>{title}</div>
        <div style={{ fontSize:11, fontWeight:700, color:'var(--text-muted)', background:'rgba(255,255,255,0.06)', padding:'2px 8px', borderRadius:6 }}>{pct}/100</div>
      </div>
      <div style={{ fontSize:26, fontWeight:900, letterSpacing:'-0.02em', color:'var(--text-primary)', marginBottom:10 }}>{value}</div>
      <div style={{ height:6, borderRadius:999, background:'rgba(255,255,255,0.08)', overflow:'hidden', marginBottom:10 }}>
        <div style={{ width:`${pct}%`, height:'100%', background:`linear-gradient(90deg,${color},${color}77)`, borderRadius:999, transition:'width 0.6s cubic-bezier(0.4,0,0.2,1)' }} />
      </div>
      <div style={{ fontSize:12, color:'var(--text-secondary)', lineHeight:1.4 }}>{sub}</div>
    </div>
  );
}

function formatStatus(status) {
  const value = String(status || 'unknown').replace(/_/g, ' ').trim();
  return value ? value.replace(/\b\w/g, (char) => char.toUpperCase()) : 'Unknown';
}

function HeroPill({ label, value, color }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '8px 14px', borderRadius: 999,
      background: `${color}18`, border: `1px solid ${color}35`,
      backdropFilter: 'blur(8px)',
    }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: 'rgba(255,255,255,0.45)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 900, color }}>{value}</span>
    </div>
  );
}

function StatusPill({ label, value, tone }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 8,
      padding: '7px 12px', borderRadius: 999,
      background: `${tone}18`, border: `1px solid ${tone}30`,
      fontSize: 11, fontWeight: 900, letterSpacing: '0.05em',
    }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ color: tone }}>{value}</span>
    </div>
  );
}

function SourceCard({ label, revenue, profit, margin, revenueShare, efficiency, intensity, color }) {
  return (
    <div style={{
      borderRadius: 20,
      border: `1px solid ${color}35`,
      padding: '18px 16px',
      background: `linear-gradient(145deg, ${color}18 0%, var(--bg-panel) 60%)`,
      boxShadow: `0 0 0 1px ${color}10, 0 8px 24px rgba(0,0,0,0.3)`,
      position: 'relative', overflow: 'hidden',
    }}>
      <div style={{ position:'absolute', top:0, left:0, bottom:0, width:4, background:`linear-gradient(180deg,${color},${color}44)`, borderRadius:'20px 0 0 20px' }} />
      <div style={{ paddingLeft:12 }}>
        <div style={{ display:'flex', justifyContent:'space-between', gap:10, alignItems:'center', marginBottom:12 }}>
          <div style={{ fontSize:13, fontWeight:800, color:'var(--text-primary)' }}>{label}</div>
          <div style={{ fontSize:13, fontWeight:900, color, background:`${color}18`, padding:'3px 10px', borderRadius:8 }}>{fmtPct(margin)}</div>
        </div>
        <div style={{ fontSize:26, fontWeight:900, letterSpacing:'-0.03em', color:'var(--text-primary)', lineHeight:1 }}>{fmt(revenue)}</div>
        <div style={{ fontSize:12, color:'var(--text-secondary)', marginTop:4, marginBottom:14 }}>{fmt(profit)} profit</div>
        <div style={{ display:'grid', gap:8 }}>
          <ProgressStat label="Revenue Share" value={fmtPct(revenueShare)} progress={revenueShare} color={color} />
          <ProgressStat label="Channel Strength" value={fmtPct(intensity)} progress={intensity} color={color} />
          <ProgressStat label="Efficiency" value={fmtPct(efficiency)} progress={Math.max(0,Math.min(100,efficiency+50))} color={color} />
        </div>
      </div>
    </div>
  );
}

function ProgressStat({ label, value, progress, color }) {
  const pct = Math.max(0, Math.min(100, Number(progress || 0)));
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', gap:8, marginBottom:5, fontSize:11, fontWeight:700 }}>
        <span style={{ color:'var(--text-muted)' }}>{label}</span>
        <span style={{ color, fontWeight:800 }}>{value}</span>
      </div>
      <div style={{ height:5, borderRadius:999, background:'rgba(255,255,255,0.07)', overflow:'hidden' }}>
        <div style={{ width:`${pct}%`, height:'100%', background:`linear-gradient(90deg,${color},${color}66)`, borderRadius:999 }} />
      </div>
    </div>
  );
}

function LeaderboardRow({ label, value, sub, progress, color }) {
  const pct = Math.max(0, Math.min(100, Number(progress || 0)));
  return (
    <div style={{ display:'grid', gap:8, padding:'12px 14px', borderRadius:12, background:'var(--bg-elevated)', border:'1px solid var(--border-subtle)' }}>
      <div style={{ display:'flex', justifyContent:'space-between', gap:10, alignItems:'flex-start' }}>
        <div style={{ minWidth:0 }}>
          <div style={{ fontWeight:800, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', fontSize:13 }}>{label}</div>
          <div style={{ fontSize:11, color:'var(--text-secondary)', marginTop:2 }}>{sub}</div>
        </div>
        <div style={{ fontWeight:900, color, fontSize:14, whiteSpace:'nowrap' }}>{value}</div>
      </div>
      <div style={{ height:6, borderRadius:999, background:'rgba(255,255,255,0.07)', overflow:'hidden' }}>
        <div style={{ width:`${pct}%`, height:'100%', background:`linear-gradient(90deg,${color},${color}66)`, borderRadius:999 }} />
      </div>
    </div>
  );
}

const panelStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 20,
  background: 'var(--bg-panel)',
  overflow: 'hidden',
  boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset, 0 4px 6px rgba(0,0,0,0.4), 0 12px 32px rgba(0,0,0,0.25)',
};
const panelHeadStyle = {
  padding: '14px 18px',
  borderBottom: '1px solid var(--border-subtle)',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  gap: 12,
  color: 'var(--text-secondary)',
  fontSize: 11,
  fontWeight: 900,
  letterSpacing: '0.10em',
  textTransform: 'uppercase',
  background: 'linear-gradient(180deg, rgba(255,255,255,0.03), transparent)',
};
const rowStyle = {
  padding: '13px 18px',
  borderTop: '1px solid var(--border-subtle)',
  display: 'flex',
  justifyContent: 'space-between',
  gap: 12,
  alignItems: 'center',
  transition: 'background 120ms',
};
const emptyStyle = { padding: '20px 18px', color: 'var(--text-muted)', fontSize: 13 };
const emptyChartStyle = { height: 250, display: 'grid', placeItems: 'center', color: 'var(--text-muted)', fontSize: 13 };
const insightPanelStyle = {
  border: '1px solid rgba(139,92,246,0.25)',
  borderRadius: 20,
  background: 'linear-gradient(135deg, rgba(139,92,246,0.08) 0%, var(--bg-panel) 60%)',
  boxShadow: '0 0 40px rgba(139,92,246,0.06), 0 12px 32px rgba(0,0,0,0.3)',
  overflow: 'hidden',
};
const glassPanelStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 20,
  background: 'var(--bg-panel)',
  boxShadow: '0 1px 0 rgba(255,255,255,0.06) inset, 0 4px 6px rgba(0,0,0,0.4), 0 12px 32px rgba(0,0,0,0.25)',
  overflow: 'hidden',
};
const linkButtonStyle = { border: 'none', background: 'rgba(245,158,11,0.12)', color: 'var(--accent-amber)', cursor: 'pointer', fontWeight: 800, fontSize: 11, padding: '4px 10px', borderRadius: 8, letterSpacing: '0.04em' };
const td = { padding: '9px 14px' };
const tdStrong = { ...td, fontWeight: 800 };
const tdRight = { ...td, textAlign: 'right' };
const tdMoney = { ...tdRight, color: 'var(--accent-amber)', fontWeight: 900 };
