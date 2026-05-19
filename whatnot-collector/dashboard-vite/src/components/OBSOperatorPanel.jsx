import { usePolling } from '../hooks/useApi';

export default function OBSOperatorPanel() {
  const { data: obsData } = usePolling('/api/obs/current', 250);

  const active = obsData?.active || false;
  const product = obsData?.product || null;

  const statusColor = !active ? 'var(--text-secondary)' : 'var(--accent-emerald)';
  const statusLabel = !active ? 'OFF' : 'LIVE';
  const statusDot = !active ? 'status-dot--off' : 'status-dot--live';

  return (
    <div className="panel animate-in">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 8 }}>
        <h2 className="panel__title" style={{ margin: 0 }}>📺 OBS Overlay</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className={`status-dot ${statusDot}`} />
          <span style={{ fontSize: 12, fontWeight: 800, color: statusColor, letterSpacing: '0.08em' }}>{statusLabel}</span>
        </div>
      </div>

      <div style={{ background: 'var(--bg-elevated)', borderRadius: 10, padding: '12px 14px', marginBottom: 14, minHeight: 68 }}>
        {active && product ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'start' }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontWeight: 800, fontSize: 15, marginBottom: 4 }}>{product.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {product.cost_price ? <span>Cost <strong style={{ color: 'var(--accent-coral)' }}>${Number(product.cost_price).toFixed(2)}</strong></span> : null}
                {product.retail_price ? <span>Retail <strong style={{ color: 'var(--accent-amber)' }}>${Number(product.retail_price).toFixed(2)}</strong></span> : null}
                {product.on_hand_qty != null ? <span>Left <strong style={{ color: 'var(--accent-emerald)' }}>{Number(product.on_hand_qty)}</strong></span> : null}
                {product.note_top ? <span>Top <strong>{product.note_top}</strong></span> : null}
                {product.note_mid ? <span>Mid <strong>{product.note_mid}</strong></span> : null}
                {product.note_base ? <span>Base <strong>{product.note_base}</strong></span> : null}
                {product.media_url ? <span style={{ color: 'var(--accent-emerald)' }}>▶ Media ready</span> : null}
              </div>
              {(product.script || product.description) ? (
                <div style={{
                  marginTop: 10,
                  padding: '10px 12px',
                  borderRadius: 8,
                  background: 'rgba(99,102,241,0.08)',
                  border: '1px solid rgba(99,102,241,0.14)',
                  color: 'var(--text-primary)',
                  fontSize: 12,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  maxHeight: 140,
                  overflowY: 'auto',
                }}>
                  <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent-blue)', marginBottom: 6 }}>
                    Live Script
                  </div>
                  {product.script || product.description}
                </div>
              ) : null}
            </div>
            <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 8px', borderRadius: 99, background: 'rgba(34,197,94,0.15)', color: statusColor }}>
              {statusLabel}
            </span>
          </div>
        ) : (
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Nothing showing on overlay</span>
        )}
      </div>

      <p className="text-xs text-muted" style={{ margin: 0 }}>
        Overlay content follows the live scanned product from the current operator bucket.
      </p>
    </div>
  );
}
