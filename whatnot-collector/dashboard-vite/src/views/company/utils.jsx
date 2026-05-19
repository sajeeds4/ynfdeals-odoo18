export const fmt = (n) => n == null ? '—' : `$${Number(n).toFixed(2)}`;
export const fmtK = (n) => {
  if (n == null) return '—';
  const v = Number(n);
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  return `$${v.toFixed(2)}`;
};
export const fmtPct = (n) => n == null ? '—' : `${Number(n).toFixed(1)}%`;
export const fmtNum = (n) => n == null ? '—' : Number(n).toLocaleString();
export const fmtDate = (s) => s ? new Date(s).toLocaleDateString() : '—';
export const fmtDt = (s) => s ? new Date(s).toLocaleString() : '—';

export function formatSessionLabel(session, index) {
  if (!session) return 'Session';

  const source = session.started_at || session.start_time || session.created_at;
  const dt = source ? new Date(source) : null;
  const hasValidDate = dt && !Number.isNaN(dt.getTime());
  const sessionNumber = index != null ? index + 1 : (session.stream_id || session.id || 1);

  if (!hasValidDate) {
    return `S${sessionNumber}`;
  }

  const day = dt.toLocaleDateString([], { weekday: 'long' });
  const date = dt.toLocaleDateString('en-CA');
  const time = dt.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });

  return `S${sessionNumber} ${day} : ${date} : ${time}`;
}

export const clrProfit = (v) => {
  if (v == null) return 'var(--text-secondary)';
  return v >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)';
};

export const clrMargin = (v) => {
  if (v == null) return 'var(--text-secondary)';
  if (v >= 25) return 'var(--accent-emerald)';
  if (v >= 15) return 'var(--accent-amber)';
  return 'var(--accent-coral)';
};

export const STATUS_BADGE = {
  live: { label: '● LIVE', bg: 'var(--status-live)', color: '#fff' },
  draft: { label: '◌ Draft', bg: 'var(--status-pending)', color: '#000' },
  ended: { label: '○ Ended', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' },
  open: { label: 'Open', bg: 'var(--accent-blue)', color: '#fff' },
  awaiting_auction: { label: 'Awaiting', bg: 'var(--accent-amber)', color: '#000' },
  sold: { label: 'Sold', bg: 'var(--accent-emerald)', color: '#fff' },
  dropped: { label: 'Dropped', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' },
  sale: { label: 'Sale Order', bg: 'var(--accent-emerald)', color: '#fff' },
  draft_order: { label: 'Quotation', bg: 'var(--status-pending)', color: '#000' },
  cancel: { label: 'Cancelled', bg: 'var(--accent-coral)', color: '#fff' },
};

export function Badge({ status, label, custom }) {
  const badge = custom || STATUS_BADGE[status] || {
    label: status || '—',
    bg: 'var(--bg-elevated)',
    color: 'var(--text-secondary)',
  };

  return (
    <span
      style={{
        fontSize: 10,
        fontWeight: 700,
        padding: '2px 7px',
        borderRadius: 999,
        background: badge.bg,
        color: badge.color,
        whiteSpace: 'nowrap',
        letterSpacing: '0.04em',
      }}
    >
      {label || badge.label}
    </span>
  );
}

export function KpiCard({ label, value, sub, color, icon, onClick, tone }) {
  return (
    <div
      className={`company-kpi${tone ? ` tone-${tone}` : ''}`}
      onClick={onClick}
      style={{
        borderRadius: 'var(--radius-lg)',
        padding: '14px 18px',
        cursor: onClick ? 'pointer' : 'default',
      }}
    >
      <div className="company-kpi-label">
        {icon ? <span className="company-kpi-icon" aria-hidden="true">{icon}</span> : null}
        <span className="company-kpi-label-text">{label}</span>
      </div>
      <div className="company-kpi-value" style={{ color: color || 'var(--text-primary)' }}>{value}</div>
      {sub ? <div className="company-kpi-sub">{sub}</div> : null}
    </div>
  );
}

export function SortTh({ col, label, sortBy, sortAsc, onSort, align = 'left' }) {
  const active = sortBy === col;

  return (
    <th
      onClick={() => onSort(col)}
      style={{
        padding: '9px 14px',
        textAlign: align,
        cursor: 'pointer',
        userSelect: 'none',
        color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
        fontWeight: 600,
        fontSize: 11,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        whiteSpace: 'nowrap',
      }}
    >
      {label}{active ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </th>
  );
}

export function TableShell({ children, footer, tableStyle, colGroup }) {
  return (
    <div className="company-table-shell" style={{ borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ overflowX: 'auto', maxHeight: 'calc(100vh - 380px)', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, ...(tableStyle || {}) }}>
          {colGroup || null}
          {children}
        </table>
      </div>
      {footer ? (
        <div style={{ padding: '7px 14px', borderTop: '1px solid var(--border-subtle)', fontSize: 12, color: 'var(--text-secondary)' }}>
          {footer}
        </div>
      ) : null}
    </div>
  );
}

export function Thead({ cols }) {
  return (
    <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
      <tr>
        {cols.map((col, index) => (
          <th key={index} style={{ padding: '9px 14px', textAlign: col.align || 'left', color: 'var(--text-secondary)', fontWeight: 600, fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap' }}>
            {col.label}
          </th>
        ))}
      </tr>
    </thead>
  );
}

export function EmptyRow({ cols, msg = 'No records found.', loading }) {
  return (
    <tr>
      <td colSpan={cols} style={{ padding: 32, textAlign: 'center', color: 'var(--text-secondary)' }}>
        {loading ? 'Loading…' : msg}
      </td>
    </tr>
  );
}

export function FilterBar({ children, style = null }) {
  return (
    <div className="company-filter-bar" style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 2, ...(style || {}) }}>
      {children}
    </div>
  );
}

export function SearchInput({ value, onChange, placeholder = 'Search…' }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      className="company-input"
      style={{ color: 'var(--text-primary)', borderRadius: 'var(--radius-md)', padding: '6px 10px', fontSize: 12, minHeight: 34, flex: 1, minWidth: 200 }}
    />
  );
}

export function SessionSelect({ sessions, value, onChange, allLabel = 'All Sessions' }) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="company-input"
      style={{
        color: '#1f2937',
        borderRadius: 'var(--radius-md)',
        padding: '6px 30px 6px 10px',
        fontSize: 12,
        minHeight: 34,
        minWidth: 290,
        fontWeight: 700,
        border: '1px solid rgba(59,130,246,0.28)',
        background: 'linear-gradient(135deg, #fef3c7 0%, #dbeafe 48%, #fde68a 100%)',
        boxShadow: '0 8px 24px rgba(59,130,246,0.12), inset 0 1px 0 rgba(255,255,255,0.7)',
      }}
    >
      <option value="">{allLabel}</option>
      {sessions.map((session, index) => (
        <option key={session.id} value={session.id}>
          {formatSessionLabel(session, sessions.length - index - 1)}
        </option>
      ))}
    </select>
  );
}

export function PrimaryBtn({ onClick, disabled, children, style }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="btn-3d btn-3d-primary"
      style={{ padding: '8px 18px', ...style }}
    >
      {children}
    </button>
  );
}

export function GhostBtn({ onClick, children, disabled, style }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="btn-3d btn-3d-ghost"
      style={{ padding: '8px 16px', ...style }}
    >
      {children}
    </button>
  );
}

export function SlidePanel({ title, sub, onClose, children }) {
  return (
    <>
      <div className="company-slide-backdrop" onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 199 }} />
      <div className="company-slide-panel" style={{ position: 'fixed', right: 0, top: 0, bottom: 0, width: 560, maxWidth: '100vw', zIndex: 200, display: 'flex', flexDirection: 'column' }}>
        <div className="company-slide-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '16px 22px', borderBottom: '1px solid var(--border-default)' }}>
          <div>
            <div style={{ fontWeight: 800, fontSize: 16, letterSpacing: '-0.02em' }}>{title}</div>
            {sub && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{sub}</div>}
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 22, lineHeight: 1 }}>×</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>
          {children}
        </div>
      </div>
    </>
  );
}

export function FullPageForm({ title, sub, onClose, actions, children, fullWidth, maxWidth }) {
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 300, background: '#f8f9fb', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Top bar */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '0 28px',
        height: 56,
        borderBottom: '1.5px solid #e2e8f0',
        background: '#ffffff',
        flexShrink: 0,
        gap: 16,
        boxShadow: '0 1px 3px rgba(15,23,42,0.04)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', fontSize: 20, lineHeight: 1, padding: '4px 8px 4px 0', flexShrink: 0 }}
            title="Back"
          >
            ←
          </button>
          <div style={{ minWidth: 0 }}>
            {title && <div style={{ fontWeight: 800, fontSize: 15, color: '#0f172a', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>}
            {sub && (
              <div style={{ fontSize: 11, color: '#64748b', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub}</div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          {actions}
          <button onClick={onClose} className="btn-3d btn-3d-ghost" style={{ padding: '7px 16px' }}>
            Discard
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      {fullWidth ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
          {children}
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 0' }}>
          <div style={{ width: '100%', maxWidth: maxWidth ?? 860, margin: '0 auto', padding: '0 16px' }}>
            {children}
          </div>
        </div>
      )}
    </div>
  );
}
