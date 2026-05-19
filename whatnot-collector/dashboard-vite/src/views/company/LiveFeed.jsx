/**
 * LiveFeed — Real-time auction event feed for the company's own stream.
 * Polls the events API filtered to the current company session's stream.
 */
import { useState, useEffect, useRef } from 'react';
import { useEvents, fetchApi } from '../../hooks/useApi';
import { fmt, KpiCard } from './utils';

const fmt$ = (n) => `$${Number(n || 0).toFixed(2)}`;
const calcPlatformFee = (revenue) => Number(revenue || 0) * 0.06;

const EVENT_STYLE = {
  auction_winner: { bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.3)', icon: '🏆', color: '#fbbf24' },
  auction_start:  { bg: 'rgba(99,102,241,0.10)', border: 'rgba(99,102,241,0.28)', icon: '🎬', color: '#818cf8' },
  auction_end:    { bg: 'rgba(34,197,94,0.10)',  border: 'rgba(34,197,94,0.28)',  icon: '✅', color: '#34d399' },
  lot_open:       { bg: 'rgba(99,102,241,0.10)', border: 'rgba(99,102,241,0.28)', icon: '📦', color: '#818cf8' },
  lot_dropped:    { bg: 'rgba(239,68,68,0.10)',  border: 'rgba(239,68,68,0.28)',  icon: '🔻', color: '#f87171' },
  chat_message:   { bg: 'transparent',           border: 'var(--border-subtle)',  icon: '💬', color: 'var(--text-secondary)' },
  live_viewers:   { bg: 'transparent',           border: 'var(--border-subtle)',  icon: '👁', color: 'var(--text-secondary)' },
};

function fmtTime(t) {
  if (!t) return '';
  try { return new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
  catch { return ''; }
}

function parsePayload(p) {
  if (!p) return {};
  if (typeof p === 'object') return p;
  try { return JSON.parse(p); } catch { return {}; }
}

function EventRow({ event }) {
  const style = EVENT_STYLE[event.event_type] || { bg: 'transparent', border: 'var(--border-subtle)', icon: '•', color: 'var(--text-secondary)' };
  const payload = parsePayload(event.payload);

  let summary = '';
  if (event.event_type === 'auction_winner') {
    summary = `@${payload.winner || '?'} won Lot ${payload.lot_number || '?'} for ${payload.price || fmt$(payload.price_value)}`;
  } else if (event.event_type === 'chat_message') {
    summary = `@${payload.username || '?'}: ${(payload.message || '').slice(0, 80)}`;
  } else if (event.event_type === 'auction_start') {
    summary = `Auction started${payload.lot_number ? ` — Lot ${payload.lot_number}` : ''}`;
  } else if (event.event_type === 'auction_end') {
    summary = `Auction ended`;
  } else if (event.event_type === 'lot_open') {
    summary = `Lot opened${payload.lot_number ? ` — #${payload.lot_number}` : ''}`;
  } else if (event.event_type === 'lot_dropped') {
    summary = `Lot dropped${payload.lot_number ? ` — #${payload.lot_number}` : ''}`;
  } else if (event.event_type === 'live_viewers') {
    summary = `${payload.viewer_count || '?'} viewers`;
  } else {
    summary = JSON.stringify(payload).slice(0, 100);
  }

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '28px 80px minmax(0,1fr)',
      gap: 10,
      alignItems: 'flex-start',
      padding: '8px 14px',
      borderBottom: `1px solid ${style.border}`,
      background: style.bg,
      fontSize: 13,
    }}>
      <span style={{ fontSize: 16, lineHeight: 1.2 }}>{style.icon}</span>
      <span style={{ color: 'var(--text-secondary)', fontSize: 11, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap', paddingTop: 1 }}>
        {fmtTime(event.occurred_at || event.created_at)}
      </span>
      <span style={{ color: style.color, wordBreak: 'break-word', lineHeight: 1.45 }}>{summary}</span>
    </div>
  );
}

const FILTER_OPTIONS = [
  { id: 'all',     label: 'All Events' },
  { id: 'auction', label: 'Auctions Only' },
  { id: 'chat',    label: 'Chat Only' },
];

export default function LiveFeed({ sessions }) {
  const [streamId, setStreamId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const [liveSessionStats, setLiveSessionStats] = useState(null);
  const feedRef = useRef(null);

  // Find current live session's stream_id
  useEffect(() => {
    const liveSession = sessions.find((s) => s.status === 'live');
    if (liveSession?.show_id || liveSession?.stream_url) {
      // Look up stream_id via the streams list
      fetchApi('/api/streams')
        .then((d) => {
          const streams = d.streams || d.rows || [];
          const match = streams.find((s) =>
            (liveSession.stream_url && s.stream_url === liveSession.stream_url) ||
            (liveSession.show_id && s.show_id === liveSession.show_id) ||
            (s.streamer_name === 'ynfdeals')
          );
          if (match) setStreamId(match.id);
        })
        .catch(() => {});
      // Stats from the live session
      setLiveSessionStats(liveSession);
    } else {
      // Use most recent session
      setLiveSessionStats(sessions[0] || null);
    }
  }, [sessions]);

  const { events: rawEvents } = useEvents(3000, null, streamId);

  const events = (rawEvents || []).filter((e) => {
    if (filter === 'auction') return e.event_type.startsWith('auction') || e.event_type.startsWith('lot');
    if (filter === 'chat') return e.event_type === 'chat_message';
    return true;
  });

  // Auto scroll
  useEffect(() => {
    if (autoScroll && feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  const winners = events.filter((e) => e.event_type === 'auction_winner');
  const totalLive = winners.length;
  const liveRevenue = winners.reduce((s, e) => {
    const p = parsePayload(e.payload);
    return s + (parseFloat(p.price_value) || 0);
  }, 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* KPIs for live session */}
      {liveSessionStats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px,1fr))', gap: 10 }}>
          <KpiCard label="Session Revenue" value={`$${Number(liveSessionStats.total_revenue || 0).toFixed(2)}`} icon="💰" color="var(--accent-amber)" />
          <KpiCard label="Platform Fee (6%)" value={`$${Number(liveSessionStats.platform_fee ?? calcPlatformFee(liveSessionStats.total_revenue)).toFixed(2)}`} icon="🏦" color="var(--text-secondary)" />
          <KpiCard label="Session Profit" value={`$${Number(liveSessionStats.total_profit || 0).toFixed(2)}`} icon="📈" color={liveSessionStats.total_profit > 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)'} />
          <KpiCard label="Lots Sold" value={liveSessionStats.total_lots_sold || 0} icon="🎯" />
          <KpiCard label="Live Feed Wins" value={totalLive} icon="🏆" color="var(--accent-amber)" />
          <KpiCard label="Feed Revenue" value={fmt$(liveRevenue)} icon="💵" />
        </div>
      )}

      {!streamId && (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, padding: '20px 24px', color: 'var(--text-secondary)', fontSize: 13 }}>
          No active company stream detected. Start the collector with your stream URL to see the live feed.
        </div>
      )}

      {streamId && (
        <>
          {/* Controls */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            {FILTER_OPTIONS.map((f) => (
              <button key={f.id} type="button" onClick={() => setFilter(f.id)} style={{
                padding: '6px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                border: '1px solid var(--border-default)',
                background: filter === f.id ? '#fbbf24' : 'var(--bg-panel)',
                color: filter === f.id ? '#1a1200' : 'var(--text-secondary)',
              }}>{f.label}</button>
            ))}
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', cursor: 'pointer', marginLeft: 'auto' }}>
              <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
              Auto-scroll
            </label>
          </div>

          {/* Feed */}
          <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
            <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-emerald)', display: 'inline-block' }} />
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Live Event Feed</span>
              <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-secondary)' }}>{events.length} events</span>
            </div>
            <div ref={feedRef} style={{ maxHeight: '55vh', overflowY: 'auto' }}>
              {events.length === 0 && (
                <div style={{ padding: '20px 14px', color: 'var(--text-secondary)', fontSize: 13, textAlign: 'center' }}>
                  Waiting for events… (stream {streamId})
                </div>
              )}
              {events.map((e) => <EventRow key={e.id} event={e} />)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
