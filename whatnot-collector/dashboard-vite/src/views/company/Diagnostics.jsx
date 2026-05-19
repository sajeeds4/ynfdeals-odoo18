import { useMemo, useState } from 'react';
import { postApi, usePolling } from '../../hooks/useApi';
import { useSessionState } from '../../hooks/useBrowserState';

function fmtBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1024 * 1024 * 1024) return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

function ageFrom(ts) {
  if (!ts) return '—';
  try {
    const diff = Date.now() - new Date(ts).getTime();
    const sec = Math.max(0, Math.round(diff / 1000));
    if (sec < 60) return `${sec}s ago`;
    const min = Math.round(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = (min / 60).toFixed(1);
    return `${hr}h ago`;
  } catch {
    return '—';
  }
}

function tone(level) {
  if (level === 'error') return 'var(--accent-coral)';
  if (level === 'warning') return 'var(--accent-amber)';
  return 'var(--accent-emerald)';
}

function chipStyle(level) {
  const color = tone(level);
  return {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    padding: '4px 10px',
    border: `1px solid color-mix(in srgb, ${color} 32%, transparent)`,
    background: `color-mix(in srgb, ${color} 10%, var(--bg-elevated))`,
    color,
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.06em',
    textTransform: 'uppercase',
  };
}

function Section({ title, sub, children, action }) {
  return (
    <section className="company-panel" style={{ minWidth: 0, overflow: 'hidden' }}>
      <div className="company-panel-head">
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 800 }}>{title}</div>
          {sub ? <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div> : null}
        </div>
        {action}
      </div>
      <div className="company-panel-body">{children}</div>
    </section>
  );
}

function StatGrid({ items }) {
  return (
    <div className="diag-grid-4">
      {items.map((item) => (
        <div key={item.label} className="company-kpi" style={{ padding: '16px 18px', borderRadius: 'var(--radius-lg)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{item.label}</div>
          <div style={{ fontSize: 24, fontWeight: 900, color: item.color || 'var(--text-primary)', marginTop: 8 }}>{item.value}</div>
          {item.sub ? <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 6 }}>{item.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}

export default function Diagnostics() {
  const [logLevel, setLogLevel] = useSessionState('company.diagnostics.logLevel', 'all');
  const [logSearch, setLogSearch] = useSessionState('company.diagnostics.logSearch', '');
  const [showOnlyProblems, setShowOnlyProblems] = useSessionState('company.diagnostics.onlyProblems', false);
  const [tableSearch, setTableSearch] = useSessionState('company.diagnostics.tableSearch', '');
  const [logLimit, setLogLimit] = useSessionState('company.diagnostics.logLimit', 200);
  const { data, loading, error, refresh } = usePolling(`/api/system/diagnostics?log_limit=${encodeURIComponent(logLimit)}`, 5000, true, { useCache: false });
  const [actionBusy, setActionBusy] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const {
    data: frontendErrorData,
    loading: frontendErrorsLoading,
    error: frontendErrorsError,
    refresh: refreshFrontendErrors,
  } = usePolling('/api/v2/diagnostics/frontend-errors?limit=80', 10000, true, { useCache: false });

  const filteredLogs = useMemo(() => {
    const rows = data?.logs?.entries || [];
    return rows.filter((row) => {
      if (showOnlyProblems && row.level === 'info') return false;
      if (logLevel !== 'all' && row.level !== logLevel) return false;
      if (logSearch && !String(row.message || '').toLowerCase().includes(logSearch.toLowerCase())) return false;
      return true;
    });
  }, [data?.logs?.entries, logLevel, logSearch, showOnlyProblems]);

  const filteredTables = useMemo(() => {
    const rows = data?.database?.tables || [];
    return rows.filter((row) => !tableSearch || String(row.name || '').toLowerCase().includes(tableSearch.toLowerCase()));
  }, [data?.database?.tables, tableSearch]);

  const frontendErrors = useMemo(() => frontendErrorData?.rows || [], [frontendErrorData?.rows]);
  const frontendErrorCounts = useMemo(() => {
    const counts = { total: frontendErrors.length, runtime: 0, react: 0, api: 0 };
    for (const row of frontendErrors) {
      const source = String(row.source || '');
      if (source.includes('react')) counts.react += 1;
      else if (source.includes('api')) counts.api += 1;
      else counts.runtime += 1;
    }
    return counts;
  }, [frontendErrors]);

  const flags = data?.flags || [];
  const unresolved = data?.failed_ingests?.recent || [];
  const stream = data?.stream || {};
  const api = data?.api || {};
  const collectorHealth = data?.collector_health || {};
  const dbFiles = data?.database?.files || [];
  const liveSafety = data?.live_safety || {};
  const duplicates = data?.duplicates || [];
  const timeline = data?.timeline || [];

  async function runAction(kind) {
    setActionBusy(kind);
    setActionMessage('');
    try {
      if (kind === 'retry') {
        const result = await postApi('/api/retry_all_ingests', {});
        setActionMessage(`Retried ingests: ${result.succeeded || 0} succeeded, ${result.failed || 0} failed.`);
      } else if (kind === 'dismiss') {
        const result = await postApi('/api/dismiss_all_ingests', {});
        setActionMessage(`Dismissed ${result.dismissed || 0} failed-ingest records.`);
      } else if (kind === 'demo') {
        await postApi('/api/system/clear_demo_scan', {});
        setActionMessage('Cleared demo TV scan state.');
      }
      await refresh();
    } catch (err) {
      setActionMessage(err.message || 'Action failed.');
    } finally {
      setActionBusy('');
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0, width: '100%' }}>
      <StatGrid items={[
        { label: 'API PID', value: api.pid || '—', sub: api.started_at ? `Started ${ageFrom(api.started_at)}` : 'Process info' },
        { label: 'Collector', value: stream.running ? 'RUNNING' : 'STOPPED', color: stream.running ? 'var(--accent-emerald)' : 'var(--accent-coral)', sub: stream.stream_url || 'No active stream' },
        { label: 'Failed Ingests', value: data?.failed_ingests?.unresolved_count ?? 0, color: (data?.failed_ingests?.unresolved_count ?? 0) > 0 ? 'var(--accent-amber)' : 'var(--accent-emerald)', sub: `${data?.failed_ingests?.needs_review_count ?? 0} need review` },
        { label: 'Log Errors', value: data?.logs?.counts?.error ?? 0, color: (data?.logs?.counts?.error ?? 0) > 0 ? 'var(--accent-coral)' : 'var(--text-primary)', sub: `${data?.logs?.counts?.warning ?? 0} warnings` },
      ]} />

      <Section
        title="Frontend Error Capture"
        sub="Browser runtime errors, React render crashes, unhandled promises, and server/network API failures."
        action={
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={chipStyle(frontendErrorCounts.total ? 'warning' : 'info')}>{frontendErrorCounts.total} captured</span>
            <button type="button" className="btn-3d btn-3d-ghost" onClick={refreshFrontendErrors}>Refresh</button>
          </div>
        }
      >
        <div className="diag-grid-4" style={{ marginBottom: 12 }}>
          {[
            ['React', frontendErrorCounts.react, 'Render boundary crashes'],
            ['Runtime', frontendErrorCounts.runtime, 'Window errors / promises'],
            ['API', frontendErrorCounts.api, 'Network + 5xx failures'],
            ['Storage', frontendErrorData?.storage || '—', 'Diagnostics backend'],
          ].map(([label, value, sub]) => (
            <div key={label} className="company-kpi" style={{ padding: '12px 14px', borderRadius: 'var(--radius-lg)' }}>
              <div style={{ fontSize: 10, color: 'var(--text-secondary)', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</div>
              <div style={{ fontSize: 20, fontWeight: 900, marginTop: 6 }}>{value}</div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{sub}</div>
            </div>
          ))}
        </div>
        <div style={{ maxHeight: 360, overflow: 'auto', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', background: 'var(--bg-panel)', minWidth: 0 }}>
          {frontendErrors.length === 0 ? (
            <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 13 }}>
              {frontendErrorsLoading ? 'Loading frontend errors...' : frontendErrorsError ? `Failed to load frontend errors: ${frontendErrorsError}` : 'No captured frontend errors yet.'}
            </div>
          ) : (
            frontendErrors.map((row) => (
              <div key={row.id || row.event_id || `${row.created_at}-${row.message}`} style={{ borderTop: '1px solid var(--border-subtle)', padding: '12px 14px', minWidth: 0 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '88px 120px minmax(0, 1fr) auto', gap: 10, alignItems: 'start' }}>
                  <span style={chipStyle(row.level || 'error')}>{row.source || 'frontend'}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700 }}>{ageFrom(row.created_at || row.client_ts)}</span>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, overflowWrap: 'anywhere' }}>{row.message || 'Unknown frontend error'}</div>
                    <div style={{ marginTop: 5, color: 'var(--text-secondary)', fontSize: 11, overflowWrap: 'anywhere' }}>{row.route || row.url || 'No route captured'}</div>
                    {row.api_url ? (
                      <div style={{ marginTop: 5, color: 'var(--text-secondary)', fontSize: 11, overflowWrap: 'anywhere' }}>
                        {row.api_method || 'GET'} {row.api_url} {row.api_status ? `· ${row.api_status}` : ''}
                      </div>
                    ) : null}
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>#{row.id || 'file'}</span>
                </div>
                {(row.stack || row.component_stack) ? (
                  <details style={{ marginTop: 10 }}>
                    <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700 }}>Stack trace</summary>
                    {row.stack ? (
                      <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-coral)' }}>{row.stack}</pre>
                    ) : null}
                    {row.component_stack ? (
                      <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent-amber)' }}>{row.component_stack}</pre>
                    ) : null}
                  </details>
                ) : null}
              </div>
            ))
          )}
        </div>
      </Section>

      <Section
        title="Live Safety"
        sub="Current stream/session safety, queue pressure, and duplicate-lot risk."
        action={<span style={chipStyle(liveSafety.safe ? 'info' : 'warning')}>{liveSafety.safe ? 'stable' : 'attention'}</span>}
      >
        <div className="diag-grid-3">
          {[
            ['Session', liveSafety.session_name || (liveSafety.session_id ? `#${liveSafety.session_id}` : 'No active session'), liveSafety.session_id ? `Session ${liveSafety.session_id}` : ''],
            ['Current Lot', liveSafety.current_lot_number || '—', 'Current working lot'],
            ['Pending Queue', liveSafety.pending_queue_depth ?? 0, 'Waiting for scan'],
            ['Assigned Queue', liveSafety.assigned_queue_depth ?? 0, 'Scanned, waiting confirm'],
            ['Needs Review', liveSafety.needs_review_depth ?? 0, 'Manual follow-up'],
            ['Duplicate Lots', liveSafety.duplicate_lot_count ?? 0, 'Should stay at zero'],
          ].map(([label, value, sub]) => (
            <div key={label} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>{label}</div>
              <div style={{ marginTop: 8, fontWeight: 900, fontSize: 20 }}>{value}</div>
              <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 11 }}>{sub}</div>
            </div>
          ))}
        </div>
        <div className="diag-grid-2" style={{ marginTop: 14 }}>
          <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>Latest Pending</div>
            <div style={{ marginTop: 8, fontWeight: 800 }}>{liveSafety.latest_pending?.lot_number ? `Lot ${liveSafety.latest_pending.lot_number}` : 'No pending ticket'}</div>
            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
              {liveSafety.latest_pending ? `@${liveSafety.latest_pending.winner_username || 'unknown'} · $${Number(liveSafety.latest_pending.sale_price || 0).toFixed(2)}` : 'Winner queue is clear.'}
            </div>
          </div>
          <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>Latest Confirmed</div>
            <div style={{ marginTop: 8, fontWeight: 800 }}>{liveSafety.latest_confirmed?.lot_number ? `Lot ${liveSafety.latest_confirmed.lot_number}` : 'No confirmed ticket yet'}</div>
            <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
              {liveSafety.latest_confirmed ? `@${liveSafety.latest_confirmed.winner_username || 'unknown'} · $${Number(liveSafety.latest_confirmed.sale_price || 0).toFixed(2)}` : 'Nothing confirmed recently.'}
            </div>
          </div>
        </div>
      </Section>

      <Section
        title="System Flags"
        sub="Fast read on cautions, failures, and stall signals."
        action={<button type="button" className="btn-3d btn-3d-ghost" onClick={refresh}>Refresh</button>}
      >
        {!flags.length ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No active warning flags right now.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {flags.map((flag, idx) => (
              <div key={`${flag.message}-${idx}`} style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <span style={chipStyle(flag.level)}>{flag.level}</span>
                <div style={{ fontSize: 13, lineHeight: 1.45 }}>{flag.message}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <div className="diag-grid-2" style={{ minWidth: 0 }}>
        <Section title="Duplicate Detector" sub="Same-lot duplicates across auction results and winner queue.">
          {!duplicates.length ? (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No duplicate lot rows detected right now.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {duplicates.map((row) => (
                <div key={`${row.source}-${row.lot_number}`} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                    <div style={{ fontWeight: 800 }}>Lot {row.lot_number}</div>
                    <span style={chipStyle(row.source === 'auction_results' ? 'error' : 'warning')}>{row.source === 'auction_results' ? 'auction duplicate' : 'queue duplicate'}</span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-secondary)' }}>Rows: {row.dup_count} · prices: {row.prices || '—'}</div>
                  <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)' }}>IDs: {row.row_ids || '—'}</div>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section title="Recovery Actions" sub="Safe maintenance actions when the system needs help.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button type="button" className="btn-3d btn-3d-primary" onClick={() => runAction('retry')} disabled={actionBusy === 'retry'}>
              {actionBusy === 'retry' ? 'Retrying…' : 'Retry Failed Ingests'}
            </button>
            <button type="button" className="btn-3d btn-3d-ghost" onClick={() => runAction('dismiss')} disabled={actionBusy === 'dismiss'}>
              {actionBusy === 'dismiss' ? 'Dismissing…' : 'Dismiss All Failed Ingests'}
            </button>
            <button type="button" className="btn-3d btn-3d-ghost" onClick={() => runAction('demo')} disabled={actionBusy === 'demo'}>
              {actionBusy === 'demo' ? 'Clearing…' : 'Clear Demo TV Scan'}
            </button>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Use retry first for collector sync issues. Dismiss only when you plan to handle those rows manually.
            </div>
            {actionMessage ? <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{actionMessage}</div> : null}
          </div>
        </Section>
      </div>

      <div className="diag-grid-2" style={{ minWidth: 0 }}>
        <Section title="Collector Health" sub="Last event timing by event type.">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            {[
              ['Last Event', collectorHealth.last_event_at],
              ['Chat', collectorHealth.chat_message],
              ['Lot Update', collectorHealth.lot_update],
              ['Bid Update', collectorHealth.bid_update],
              ['Winner', collectorHealth.auction_winner],
              ['Viewers', collectorHealth.live_viewers],
            ].map(([label, value]) => (
              <div key={label} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700 }}>{label}</div>
                <div style={{ marginTop: 8, fontWeight: 800, fontSize: 15 }}>{ageFrom(value)}</div>
                <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis' }}>{value || 'No data'}</div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="DB Health" sub="File size and table-level row counts.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
            {dbFiles.map((file) => (
              <div key={file.path} style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto auto', gap: 12, alignItems: 'center', borderBottom: '1px solid var(--border-subtle)', paddingBottom: 10 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(file.path || '').split('/').pop() || 'DB file'}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 11 }}>{file.modified_at ? `Updated ${ageFrom(file.modified_at)}` : 'Missing file'}</div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{file.exists ? 'present' : 'missing'}</div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{fmtBytes(file.size_bytes)}</div>
              </div>
            ))}
            <div style={{ marginTop: 8 }}>
              <input
                type="text"
                value={tableSearch}
                onChange={(e) => setTableSearch(e.target.value)}
                placeholder="Filter DB tables..."
                style={{ width: '100%', background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '10px 12px', fontSize: 13 }}
              />
            </div>
            <div style={{ maxHeight: 260, overflow: 'auto', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', minWidth: 0 }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ background: 'var(--bg-elevated)' }}>
                    <th style={{ textAlign: 'left', padding: '10px 12px' }}>Table</th>
                    <th style={{ textAlign: 'right', padding: '10px 12px' }}>Rows</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTables.map((row) => (
                    <tr key={row.name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '9px 12px' }}>{row.name}</td>
                      <td style={{ padding: '9px 12px', textAlign: 'right', fontWeight: 700 }}>{row.row_count ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Section>
      </div>

      <div className="diag-grid-2" style={{ minWidth: 0 }}>
        <Section title="Failed Ingests" sub="Winner sync failures, retries, and review-needed records.">
          {!unresolved.length ? (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No unresolved failed ingests right now.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 320, overflow: 'auto' }}>
              {unresolved.map((row) => (
                <div key={row.id} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', padding: '12px 14px', background: 'var(--bg-panel)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                    <div style={{ fontWeight: 800 }}>{row.lot_number ? `Lot ${row.lot_number}` : 'Missing lot'}</div>
                    <span style={chipStyle(row.needs_review ? 'error' : 'warning')}>{row.needs_review ? 'needs review' : 'pending retry'}</span>
                  </div>
                  <div style={{ marginTop: 6, fontSize: 13 }}>{row.winner_username ? `@${row.winner_username}` : 'No winner username'} · ${Number(row.sale_price || 0).toFixed(2)}</div>
                  <div style={{ marginTop: 6, color: 'var(--text-secondary)', fontSize: 12 }}>{row.error_message || 'No error message'}</div>
                  <div style={{ marginTop: 6, color: 'var(--text-secondary)', fontSize: 11 }}>Seen {ageFrom(row.created_at)} · retries {row.retry_count || 0}</div>
                </div>
              ))}
            </div>
          )}
        </Section>

        <Section
          title="Collector / API Logs"
          sub="Tail logs with severity and text filters."
          action={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <select value={logLimit} onChange={(e) => setLogLimit(Number(e.target.value) || 200)} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 12 }}>
                <option value={100}>100 lines</option>
                <option value={200}>200 lines</option>
                <option value={300}>300 lines</option>
              </select>
            </div>
          }
        >
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10, minWidth: 0 }}>
            <select value={logLevel} onChange={(e) => setLogLevel(e.target.value)} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 12 }}>
              <option value="all">All levels</option>
              <option value="error">Errors</option>
              <option value="warning">Warnings</option>
              <option value="info">Info</option>
            </select>
            <input
              type="text"
              value={logSearch}
              onChange={(e) => setLogSearch(e.target.value)}
              placeholder="Search logs..."
              style={{ flex: '1 1 220px', minWidth: 0, background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 12 }}
            />
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)', flex: '0 1 auto' }}>
              <input type="checkbox" checked={showOnlyProblems} onChange={(e) => setShowOnlyProblems(e.target.checked)} />
              Show only warnings/errors
            </label>
          </div>
          <div style={{ maxHeight: 420, overflow: 'auto', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-lg)', background: 'var(--bg-panel)', minWidth: 0 }}>
            {filteredLogs.length === 0 ? (
              <div style={{ padding: 16, color: 'var(--text-secondary)', fontSize: 13 }}>{loading ? 'Loading diagnostics…' : error ? `Failed to load diagnostics: ${error}` : 'No log lines match the current filters.'}</div>
            ) : (
              filteredLogs.map((row) => (
                <div key={row.id} style={{ display: 'grid', gridTemplateColumns: '72px 72px minmax(0, 1fr)', gap: 10, padding: '10px 12px', borderTop: '1px solid var(--border-subtle)', alignItems: 'start', minWidth: 0 }}>
                  <span style={chipStyle(row.level)}>{row.level}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase' }}>{row.source}</span>
                  <code style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', wordBreak: 'break-word', minWidth: 0, fontFamily: 'var(--font-mono)', fontSize: 11, color: row.level === 'error' ? 'var(--accent-coral)' : row.level === 'warning' ? 'var(--accent-amber)' : 'var(--text-primary)' }}>
                    {row.message}
                  </code>
                </div>
              ))
            )}
          </div>
        </Section>
      </div>

      <Section title="Recent Timeline" sub="Latest sales, queue events, and failures in one chronological feed.">
        {!timeline.length ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No recent diagnostic events yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {timeline.map((row, idx) => (
              <div key={`${row.kind}-${row.at}-${idx}`} style={{ display: 'grid', gridTemplateColumns: '88px 120px minmax(0, 1fr)', gap: 12, alignItems: 'start', borderTop: idx === 0 ? 'none' : '1px solid var(--border-subtle)', paddingTop: idx === 0 ? 0 : 10 }}>
                <span style={chipStyle(row.level)}>{row.kind.replace('_', ' ')}</span>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{ageFrom(row.at)}</div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{row.label}</div>
                  <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 12, overflowWrap: 'anywhere' }}>{row.detail}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
