import { useEffect, useMemo, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  FilterBar,
  GhostBtn,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  fmtDt,
} from './utils';

const badgeStyle = (active) => ({
  padding: '7px 12px',
  borderRadius: 999,
  border: '1px solid var(--border-default)',
  background: active ? 'linear-gradient(135deg, rgba(251,191,36,0.22), rgba(96,165,250,0.16))' : 'var(--bg-panel)',
  color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
  fontWeight: 700,
  fontSize: 12,
});

export default function CustomerReviews() {
  const [search, setSearch] = useState('');
  const [matchedOnly, setMatchedOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [status, setStatus] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ scope: 'company' });
      if (search.trim()) params.set('q', search.trim());
      if (matchedOnly) params.set('matched_only', '1');
      const [feed, stat] = await Promise.all([
        fetchApi(`/api/customers/reviews?${params}`),
        fetchApi('/api/customers/reviews/status?scope=company'),
      ]);
      setRows(feed.rows || []);
      setSummary(feed.summary || {});
      setStatus(stat.status || null);
    } catch {
      setRows([]);
      setSummary({});
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [matchedOnly]);

  useEffect(() => {
    const timer = setTimeout(() => {
      load();
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);

  const derived = useMemo(() => {
    const total = rows.length;
    const matched = rows.filter((row) => row.matched_customer_id).length;
    const replied = rows.filter((row) => row.reply_text).length;
    const avg = rows.length
      ? rows.reduce((acc, row) => acc + Number(row.rating || 0), 0) / rows.filter((row) => row.rating != null).length || 0
      : 0;
    return { total, matched, replied, avg };
  }, [rows]);

  const board = useMemo(() => {
    const columns = [
      {
        id: 'needs-reply',
        label: 'Needs Reply',
        tone: 'rgba(245,158,11,0.18)',
        border: 'rgba(245,158,11,0.28)',
        rows: [],
      },
      {
        id: 'replied',
        label: 'Replied',
        tone: 'rgba(16,185,129,0.14)',
        border: 'rgba(16,185,129,0.24)',
        rows: [],
      },
      {
        id: 'unmatched',
        label: 'Unmatched',
        tone: 'rgba(239,68,68,0.12)',
        border: 'rgba(239,68,68,0.22)',
        rows: [],
      },
    ];
    const byId = Object.fromEntries(columns.map((col) => [col.id, col]));
    rows.forEach((row) => {
      if (!row.matched_customer_id) {
        byId.unmatched.rows.push(row);
      } else if (row.reply_text) {
        byId.replied.rows.push(row);
      } else {
        byId['needs-reply'].rows.push(row);
      }
    });
    return columns;
  }, [rows]);

  async function syncReviews() {
    setSyncing(true);
    try {
      const result = await postApi('/api/customers/reviews/sync', {});
      setStatus(result.status || null);
      await load();
    } catch (err) {
      setStatus((prev) => ({
        ...(prev || {}),
        last_status: 'error',
        last_error: err.message || 'Unable to sync reviews',
      }));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <KpiCard label="Reviews" value={summary.total_reviews ?? derived.total} icon="⭐" />
        <KpiCard label="Matched Customers" value={summary.matched_reviews ?? derived.matched} icon="🧩" color="var(--accent-emerald)" />
        <KpiCard label="Seller Replies" value={summary.replied_reviews ?? derived.replied} icon="💬" color="var(--accent-blue)" />
        <KpiCard label="Avg Rating" value={Number((summary.avg_rating ?? derived.avg) || 0).toFixed(1)} icon="🌟" color="var(--accent-amber)" />
      </div>

      <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '16px 18px', display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, letterSpacing: '-0.02em' }}>Whatnot Reviews</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 12, marginTop: 3 }}>
              Seller: @{status?.seller_username || 'ynfdeals'} · {status?.last_finished_at ? `last sync ${fmtDt(status.last_finished_at)}` : 'not synced yet'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ ...badgeStyle(Boolean(status?.last_status === 'ok')) }}>
              {status?.last_status === 'ok' ? `OK · ${status?.last_count || 0} cached` : (status?.last_status || 'idle')}
            </span>
            {status?.last_error ? (
              <span style={{ ...badgeStyle(false), color: 'var(--accent-coral)', maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {status.last_error}
              </span>
            ) : null}
          </div>
        </div>

        <FilterBar>
          <SearchInput value={search} onChange={setSearch} placeholder="Search reviewer, customer, review text..." />
          <GhostBtn onClick={() => setMatchedOnly((value) => !value)}>
            {matchedOnly ? 'Showing Matched Only' : 'Showing All Reviews'}
          </GhostBtn>
          <GhostBtn onClick={load} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</GhostBtn>
          <PrimaryBtn onClick={syncReviews} disabled={syncing}>{syncing ? 'Syncing Reviews...' : 'Sync Reviews'}</PrimaryBtn>
        </FilterBar>
      </div>

      {loading ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} style={{ borderRadius: 'var(--radius-xl)', border: '1px solid var(--border-default)', background: 'var(--bg-panel)', minHeight: 320, padding: 14 }} />
          ))}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14, alignItems: 'start' }}>
          {board.map((column) => (
            <div
              key={column.id}
              style={{
                borderRadius: 'var(--radius-xl)',
                border: `1px solid ${column.border}`,
                background: `linear-gradient(180deg, ${column.tone} 0%, var(--bg-panel) 16%, var(--bg-panel) 100%)`,
                boxShadow: 'var(--shadow-card)',
                overflow: 'hidden',
                minHeight: 420,
              }}
            >
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <div>
                  <div style={{ fontWeight: 800, fontSize: 14, letterSpacing: '0.01em' }}>{column.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {column.id === 'needs-reply' ? 'Matched buyers without a stored reply' : column.id === 'replied' ? 'Reviews where our reply was captured' : 'Reviewer not linked to a customer yet'}
                  </div>
                </div>
                <span style={{ ...badgeStyle(true), padding: '6px 10px', fontSize: 11 }}>{column.rows.length}</span>
              </div>

              <div style={{ padding: 12, display: 'grid', gap: 12, maxHeight: 'calc(100vh - 320px)', overflowY: 'auto' }}>
                {!column.rows.length ? (
                  <div style={{ borderRadius: 'var(--radius-lg)', border: '1px dashed var(--border-default)', padding: 18, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>
                    No reviews in this lane.
                  </div>
                ) : column.rows.map((row) => (
                  <div
                    key={row.review_key || row.id}
                    style={{
                      borderRadius: 'var(--radius-lg)',
                      border: '1px solid var(--border-default)',
                      background: 'linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.96) 100%)',
                      padding: 14,
                      display: 'grid',
                      gap: 10,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ fontWeight: 800, fontSize: 14 }}>{row.reviewer_display_name || row.reviewer_username || '—'}</div>
                        <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{row.reviewer_username || '—'}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <span style={{ ...badgeStyle(Boolean(row.rating != null)), padding: '5px 9px', fontSize: 11, color: 'var(--accent-amber)' }}>
                          {row.rating != null ? `${Number(row.rating).toFixed(1)}★` : 'No rating'}
                        </span>
                        <span style={{ ...badgeStyle(Boolean(row.matched_customer_id)), padding: '5px 9px', fontSize: 11, color: row.matched_customer_id ? 'var(--accent-emerald)' : 'var(--accent-coral)' }}>
                          {row.matched_customer_id ? 'Matched' : 'Unmatched'}
                        </span>
                      </div>
                    </div>

                    <div style={{ display: 'grid', gap: 4 }}>
                      <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Customer Link</div>
                      {row.matched_customer_id ? (
                        <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                          <strong>{row.customer_name || row.customer_username || 'Matched customer'}</strong>
                          <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>@{row.customer_username || row.reviewer_username}</div>
                        </div>
                      ) : (
                        <div style={{ color: 'var(--accent-coral)', fontSize: 13, fontWeight: 600 }}>No linked customer yet</div>
                      )}
                    </div>

                    <div style={{ display: 'grid', gap: 4 }}>
                      <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Review</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, color: 'var(--text-primary)' }}>
                        {row.review_text || 'No review text captured'}
                      </div>
                    </div>

                    <div style={{ display: 'grid', gap: 4 }}>
                      <div style={{ fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>Our Reply</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.5, color: row.reply_text ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>
                        {row.reply_text || 'No reply captured'}
                      </div>
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', paddingTop: 6, borderTop: '1px solid var(--border-subtle)', color: 'var(--text-secondary)', fontSize: 12 }}>
                      <span>@{row.seller_username || 'ynfdeals'}</span>
                      <span>{fmtDt(row.updated_at || row.scraped_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
