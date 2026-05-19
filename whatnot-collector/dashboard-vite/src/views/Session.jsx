/**
 * Session — Live feed monitor.
 *
 * Shows: now-selling panel, continuous chat (with filter), winners table,
 * live users from chat, and session metric overview.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { usePolling, useEvents } from '../hooks/useApi';
import StatCard from '../components/StatCard';
import DataTable from '../components/DataTable';

function fmt$(n) { return '$' + Number(n || 0).toFixed(2); }
function calcPlatformFee(revenue) { return Number(revenue || 0) * 0.06; }

// calcFees uses live config fetched from /api/fee_settings.
// feeCfg = { fee_pct: 10.9, fixed_fee: 0.50 } — passed as a prop.
function calcFees(salePrice, feeCfg) {
  const p = Number(salePrice) || 0;
  const pct = (feeCfg?.fee_pct ?? 10.9) / 100;
  const fixed = feeCfg?.fixed_fee ?? 0.50;
  return (p * pct + fixed).toFixed(2);
}
function fmtTime(t) {
  if (!t) return '—';
  try {
    const d = new Date(t);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return t; }
}

// Generate a consistent color for a username
function usernameColor(name) {
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 65%, 65%)`;
}

function makeWinnerColumns(feeCfg) {
  return [
    { key: 'sold_at', label: 'Time', width: '100px', render: v => <span className="mono text-xs">{fmtTime(v)}</span> },
    { key: 'winner_username', label: 'Winner', render: (v) => <span style={{ color: usernameColor(v), fontWeight: 600 }}>{v}</span> },
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
    { key: 'lot_number', label: 'Lot #', width: '60px' },
    { key: 'sale_price', label: 'Price', width: '90px', align: 'right', render: v => <span className="text-amber font-bold">{fmt$(v)}</span> },
    {
      key: 'fees', label: 'Fees', width: '80px', align: 'right',
      render: (fees, row) => {
        const displayed = fees || calcFees(row?.sale_price, feeCfg);
        const pct = feeCfg?.fee_pct ?? 10.9;
        const fixed = feeCfg?.fixed_fee ?? 0.50;
        return (
          <span
            className="text-coral text-xs"
            title={`${pct}% + $${fixed.toFixed(2)} = $${calcFees(row?.sale_price, feeCfg)}`}
            style={{ cursor: 'help' }}
          >
            {fmt$(displayed)}
          </span>
        );
      },
    },
    { key: 'profit', label: 'Profit', width: '90px', align: 'right', render: v => <span className={Number(v) >= 0 ? 'text-emerald' : 'text-coral'}>{fmt$(v)}</span> },
  ];
}

// ─── Status badge for lot ────────────────────────────────────────────────────
function LotStatusBadge({ status }) {
  const map = {
    open:              { label: '🔓 Open',              cls: 'chip--blue'    },
    awaiting_auction:  { label: '⏳ Awaiting Auction',  cls: 'chip--amber'   },
    dropped:           { label: '⛔ Dropped',            cls: 'chip--coral'   },
  };
  const { label, cls } = map[status] || { label: status, cls: 'chip--muted' };
  return <span className={`chip ${cls}`} style={{ fontSize: '0.72rem' }}>{label}</span>;
}

// ─── Now Selling Panel ────────────────────────────────────────────────────────
function NowSellingPanel({ isRunning }) {
  const { data: lotData } = usePolling('/api/current_lot/products', 1500, isRunning);
  const lot = lotData?.lot;
  const products = lotData?.rows || [];

  if (!isRunning) return null;
  if (!lot || !lot.lot_number) return null;

  const totalCost = products.reduce((s, p) => s + (p.cost || 0), 0);

  return (
    <div className="panel animate-in" style={{
      marginBottom: 14,
      borderLeft: '3px solid var(--accent-amber)',
      background: 'rgba(245,158,11,0.05)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontWeight: 800, fontSize: '1rem' }}>🎯 Now Selling</span>
        <span className="mono text-xs text-muted">Lot #{lot.lot_number}</span>
        <LotStatusBadge status={lot.status} />
        <span className="text-xs text-muted" style={{ marginLeft: 'auto' }}>
          {lot.total_products || products.length} item{(lot.total_products || products.length) !== 1 ? 's' : ''}
          {totalCost > 0 && <> · Cost: <span className="text-amber">{fmt$(totalCost)}</span></>}
        </span>
      </div>
      {products.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {products.map((p, i) => (
            <div key={i} style={{
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border-default)',
              borderRadius: 6,
              padding: '4px 10px',
              fontSize: '0.8rem',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}>
              {p.image_url && (
                <img src={p.image_url} alt="" style={{ width: 24, height: 24, borderRadius: 3, objectFit: 'cover' }} />
              )}
              <span style={{ fontWeight: 600 }}>{p.product_name || p.sku || p.barcode}</span>
              {p.cost > 0 && <span className="text-muted text-xs">{fmt$(p.cost)}</span>}
              {p.status === 'sold' && <span className="chip chip--emerald" style={{ fontSize: '0.65rem', padding: '1px 5px' }}>sold</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Session() {
  const { data: streamStatus } = usePolling('/api/stream_status', 3000);
  const { data: collectorHealth } = usePolling('/api/collector/health', 15000);
  const isRunning = streamStatus?.running || false;
  const sessionId = streamStatus?.session_id || null;

  // Fee settings change rarely; one refresh per hour is plenty.
  const { data: feeData } = usePolling('/api/fee_settings', 3600000);
  const feeCfg = feeData || null;

  const sessionStatsPath = sessionId
    ? ['/api/v2/sessions/current/stats', `/api/session_stats?session_id=${sessionId}`, '/api/session_stats']
    : ['/api/v2/sessions/current/stats', '/api/session_stats'];
  const auctionUrl = sessionId ? `/api/auction_results?session_id=${sessionId}` : '/api/auction_results';
  const { data: stats } = usePolling(sessionStatsPath, 1500, isRunning);
  const { data: auctionData } = usePolling(auctionUrl, 3000, isRunning);
  const currentStreamId = isRunning ? (stats?.current_stream_id || null) : null;
  const currentStreamUrl = isRunning ? (stats?.current_stream_url || null) : null;
  const {
    events,
    error: eventsError,
    stale: eventsStale,
    loading: eventsLoading,
    lastSuccessAt,
    isCatchingUp,
  } = useEvents(2000, currentStreamUrl, currentStreamId, {
    bootstrapLimit: 1200,
    maxEvents: 4000,
    batchLimit: 800,
    maxCatchUpBatches: 10,
  });
  const chatEndRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [chatFilter, setChatFilter] = useState('');

  const session = isRunning ? (stats?.session || {}) : {};
  const platformFee = session?.platform_fee ?? calcPlatformFee(session?.total_revenue);
  const healthWarnings = collectorHealth?.warnings || [];
  const showLiveFeedWarning = isRunning && (!currentStreamId || eventsStale || !!eventsError || healthWarnings.length > 0);

  // --- Chat messages ---
  const chatMessages = useMemo(() => {
    if (!isRunning) return [];
    return events
      .filter(e => e.event_type === 'chat_message')
      .map(e => {
        try {
          const p = JSON.parse(e.payload || '{}');
          return {
            id: e.id,
            time: e.created_at,
            username: p.username || p.user || 'anonymous',
            message: p.message || p.text || '',
          };
        } catch {
          return null;
        }
      })
      .filter(Boolean)
      .slice(-500);
  }, [events, isRunning]);

  // --- Filtered chat ---
  const filteredChat = useMemo(() => {
    const q = chatFilter.trim().toLowerCase();
    if (!q) return chatMessages;
    return chatMessages.filter(m =>
      m.username.toLowerCase().includes(q) ||
      m.message.toLowerCase().includes(q)
    );
  }, [chatMessages, chatFilter]);

  // --- Live users from chat ---
  const liveUsers = useMemo(() => {
    if (!isRunning) return [];
    const userMap = {};
    events.filter(e => e.event_type === 'chat_message').forEach(e => {
      try {
        const p = JSON.parse(e.payload || '{}');
        const u = p.username || p.user;
        if (u) userMap[u] = e.created_at;
      } catch {}
    });
    return Object.entries(userMap)
      .sort((a, b) => (b[1] || '').localeCompare(a[1] || ''))
      .map(([name, lastSeen]) => ({ name, lastSeen }));
  }, [events, isRunning]);

  // --- Viewer count ---
  const viewerCount = useMemo(() => {
    if (!isRunning) return null;
    const viewerEvents = events.filter(e => e.event_type === 'live_viewers');
    if (viewerEvents.length === 0) return null;
    try {
      const p = JSON.parse(viewerEvents[viewerEvents.length - 1].payload || '{}');
      return p.count || p.viewers || null;
    } catch { return null; }
  }, [events, isRunning]);

  // Auto-scroll chat
  useEffect(() => {
    if (autoScroll && !chatFilter && chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, autoScroll, chatFilter]);

  const winners = isRunning ? (auctionData?.rows || []) : [];

  // Session history is past/immutable; refresh every 5 min for newly-ended sessions.
  const { data: historyData } = usePolling('/api/session_history', 300000);
  const [showHistory, setShowHistory] = useState(false);
  const historySessions = historyData?.sessions || [];
  const maxRevenue = Math.max(...historySessions.map(s => s.total_revenue || 0), 1);
  // Scale by max absolute profit so losses and gains are proportional to each other
  const maxAbsProfit = Math.max(...historySessions.map(s => Math.abs(s.total_profit || 0)), 1);

  return (
    <div className="session-view">
      {/* NOW SELLING */}
      <NowSellingPanel isRunning={isRunning} />

      {showLiveFeedWarning && (
        <div className="banner banner--warn animate-in" style={{ marginBottom: 14 }}>
          {!currentStreamId
            ? 'Live feed is waiting for a confirmed stream identity, so chat and viewer updates may be incomplete.'
            : eventsStale
              ? 'Live event polling looks stale right now. The stream may still be running, but chat/viewer updates may be delayed.'
              : eventsError
                ? `Live event polling error: ${eventsError}`
                : `Collector health warning: ${healthWarnings.join(' · ')}`}
          {lastSuccessAt && !eventsStale && !eventsError ? ` Last successful live refresh: ${fmtTime(lastSuccessAt)}.` : ''}
        </div>
      )}

      {isRunning && isCatchingUp && (
        <div className="banner banner--warn animate-in" style={{ marginBottom: 14 }}>
          ⏳ Catching up delayed live chat and winner events.
        </div>
      )}

      {/* METRICS BAR */}
      <div className="sv-metrics">
        <StatCard label="Products Sold" value={session.total_products_sold || 0} icon="📦" />
        <StatCard label="Revenue" value={fmt$(session.total_revenue)} icon="💰" color="var(--accent-amber)" />
        <StatCard label="Platform Fee (6%)" value={fmt$(platformFee)} icon="🏦" color="var(--text-secondary)" />
        <StatCard label="Profit" value={fmt$(session.total_profit)} icon="📈" color={session.total_profit >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)'} />
        <StatCard label="Avg Price" value={fmt$(stats?.avg_price)} icon="🏷️" />
        <StatCard label="Viewers" value={viewerCount != null ? viewerCount : '—'} icon="👁️" color="var(--accent-blue)" />
        <StatCard label="Chat Users" value={liveUsers.length} icon="💬" color="var(--accent-purple)" />
      </div>

      {/* MAIN GRID: Chat (left) + Winners & Users (right) */}
      <div className="sv-grid">
        {/* CHAT FEED */}
        <div className="panel sv-chat animate-in">
          <div className="sv-chat__header">
            <h2 className="panel__title">💬 Live Chat</h2>
            <input
              type="text"
              placeholder="Filter chat…"
              value={chatFilter}
              onChange={e => setChatFilter(e.target.value)}
              style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-default)',
                borderRadius: 6,
                color: 'var(--text-primary)',
                fontSize: '0.78rem',
                padding: '3px 8px',
                width: 140,
                outline: 'none',
              }}
            />
            <label className="toggle-label text-xs">
              <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
              Auto-scroll
            </label>
          </div>
          {chatFilter && (
            <div className="text-xs text-muted" style={{ padding: '4px 0 2px 0' }}>
              {filteredChat.length} match{filteredChat.length !== 1 ? 'es' : ''} for "{chatFilter}"
            </div>
          )}
          <div className="sv-chat__feed" onScroll={e => {
            const el = e.target;
            setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 50);
          }}>
            {filteredChat.length === 0 && (
              <p className="text-muted text-sm" style={{ padding: 16 }}>
                {chatFilter ? 'No messages match your filter.' : 'Waiting for chat messages…'}
              </p>
            )}
            {filteredChat.map(msg => (
              <div key={msg.id} className="chat-msg">
                <span className="chat-msg__time mono text-xs">{fmtTime(msg.time)}</span>
                <span className="chat-msg__user" style={{ color: usernameColor(msg.username) }}>{msg.username}</span>
                <span className="chat-msg__text">{msg.message}</span>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        </div>

        {/* RIGHT COLUMN */}
        <div className="sv-right">
          {/* WINNERS TABLE */}
          <div className="panel animate-in" style={{ animationDelay: '0.05s' }}>
            <h2 className="panel__title">🏅 Winners ({winners.length})</h2>
            <DataTable columns={makeWinnerColumns(feeCfg)} rows={winners} emptyText="No winners yet" maxHeight="40vh" />
          </div>

          {/* LIVE USERS */}
          <div className="panel animate-in" style={{ animationDelay: '0.1s' }}>
            <h2 className="panel__title">👥 Live Users ({liveUsers.length})</h2>
            <div className="sv-users">
              {liveUsers.length === 0 && <p className="text-muted text-sm">No users detected in chat yet</p>}
              {liveUsers.map(u => (
                <span key={u.name} className="user-tag" style={{ borderColor: usernameColor(u.name) }}>
                  <span className="user-dot" style={{ background: usernameColor(u.name) }} />
                  {u.name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      {/* SESSION HISTORY */}
      {historySessions.length > 1 && (
        <div className="panel animate-in" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 className="panel__title" style={{ margin: 0 }}>📊 Session History (last {historySessions.length})</h2>
            <button
              className="btn text-xs"
              style={{ padding: '4px 10px', background: 'var(--bg-layer2)', fontSize: '0.75rem' }}
              onClick={() => setShowHistory(v => !v)}
            >
              {showHistory ? 'Hide' : 'Show'}
            </button>
          </div>
          {showHistory && (
            <div className="session-history" style={{ marginTop: 12 }}>
              {[...historySessions].reverse().map(s => {
                const revPct = Math.round(((s.total_revenue || 0) / maxRevenue) * 100);
                // Scale by max absolute profit — loss bars show actual magnitude vs gains
                const profitPct = Math.round((Math.abs(s.total_profit || 0) / maxAbsProfit) * 100);
                const isLoss = (s.total_profit || 0) < 0;
                return (
                  <div key={s.id} className="sh-row">
                    <div className="sh-label" title={s.name}>{s.name}</div>
                    <div className="sh-bars">
                      <div className="sh-bar-wrap">
                        <div className="sh-bar" style={{ width: `${revPct}%`, background: 'var(--accent-amber)' }} />
                        <span className="sh-val text-amber">{fmt$(s.total_revenue)}</span>
                      </div>
                      <div className="sh-bar-wrap">
                        <div className="sh-bar" style={{ width: `${profitPct}%`, background: isLoss ? 'var(--accent-coral)' : 'var(--accent-emerald)' }} />
                        <span className={`sh-val ${isLoss ? 'text-coral' : 'text-emerald'}`}>{fmt$(s.total_profit)}</span>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', width: 48, textAlign: 'right' }}>
                      {s.total_products_sold || 0} sold
                    </div>
                  </div>
                );
              })}
              <div style={{ display: 'flex', gap: 16, marginTop: 6, fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'var(--accent-amber)', marginRight: 4 }} />Revenue</span>
                <span><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: 'var(--accent-emerald)', marginRight: 4 }} />Profit</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
