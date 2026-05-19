import { useMemo, useState } from 'react';
import { Link, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { fetchApi, postApi, usePolling } from '../src/hooks/useApi.js';

const NAV_ITEMS = [
  { to: '/ops-next/operator', label: 'Operator' },
  { to: '/ops-next/tv-display', label: 'TV Display' },
  { to: '/ops-next/tv-scanner', label: 'TV Scanner' },
  { to: '/ops-next/winner-scanner', label: 'Winner Scanner' },
  { to: '/ops-next/session', label: 'Session' },
  { to: '/ops-next/auction-results', label: 'Auction Results' },
  { to: '/ops-next/session-sales', label: 'Session Sales' },
  { to: '/ops-next/inventory', label: 'Inventory' },
  { to: '/ops-next/users', label: 'Users' },
];

function fmtMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `$${Number(value).toFixed(2)}`;
}

function calcPlatformFee(revenue) {
  return Number(revenue || 0) * 0.06;
}

function Shell({ children }) {
  const location = useLocation();
  return (
    <div className="opsnext-shell">
      <aside className="opsnext-sidebar">
        <div className="opsnext-brand">
          <div className="opsnext-logo">YNF</div>
          <div>
            <div className="opsnext-brand-title">Ops Next</div>
            <div className="opsnext-brand-sub">Parallel replacement frontend</div>
          </div>
        </div>
        <nav className="opsnext-nav">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`opsnext-navlink ${location.pathname === item.to ? 'is-active' : ''}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main className="opsnext-main">{children}</main>
    </div>
  );
}

function Page({ title, subtitle, actions, children }) {
  return (
    <section className="opsnext-page">
      <header className="opsnext-pagehead">
        <div>
          <p className="opsnext-kicker">YNF Deals live ops</p>
          <h1>{title}</h1>
          <p className="opsnext-subtitle">{subtitle}</p>
        </div>
        <div className="opsnext-actions">{actions}</div>
      </header>
      {children}
    </section>
  );
}

function Stat({ label, value, hint }) {
  return (
    <article className="opsnext-stat">
      <div className="opsnext-stat-label">{label}</div>
      <div className="opsnext-stat-value">{value}</div>
      {hint ? <div className="opsnext-stat-hint">{hint}</div> : null}
    </article>
  );
}

function Panel({ title, children, aside }) {
  return (
    <section className="opsnext-panel">
      <div className="opsnext-panelhead">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

function SimpleTable({ columns, rows }) {
  return (
    <div className="opsnext-tablewrap">
      <table className="opsnext-table">
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? rows.map((row, index) => (
            <tr key={row.id || row.key || index}>
              {columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : row[column.key] ?? '—'}</td>)}
            </tr>
          )) : (
            <tr>
              <td colSpan={columns.length} className="opsnext-empty">No records yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function OperatorPage() {
  const { data: streamStatus, refresh: refreshStatus } = usePolling('/api/stream_status', 1500);
  const { data: sessionStats, refresh: refreshStats } = usePolling(['/api/v2/sessions/current/stats', '/api/session_stats'], 1500);
  const { data: lotProducts, refresh: refreshLotProducts } = usePolling('/api/current_lot/products', 1200);
  const { data: failedIngests, refresh: refreshFailed } = usePolling('/api/failed_ingests', 4000);
  const [streamUrl, setStreamUrl] = useState('');
  const [message, setMessage] = useState('');

  async function handleStart() {
    if (!streamUrl.trim()) {
      setMessage('Paste the Whatnot stream URL first.');
      return;
    }
    const result = await postApi('/api/live_collector/start', { stream_url: streamUrl.trim(), mode: 'our_stream' });
    setMessage(result?.running ? 'Live collector started.' : 'Collector start request sent.');
    refreshStatus();
    refreshStats();
  }

  async function handleStop() {
    await postApi('/api/live_collector/stop', {});
    setMessage('Live collector stopped.');
    refreshStatus();
    refreshStats();
  }

  async function handleRelease() {
    await postApi('/api/current_lot/drop', {});
    setMessage('Current lot released.');
    refreshLotProducts();
    refreshStats();
  }

  const lotRows = lotProducts?.rows || [];
  const failedRows = failedIngests?.records || [];
  const session = sessionStats?.session || {};

  return (
    <Page
      title="Operator"
      subtitle="This is the live control room. Start the collector, stage items into the current lot, and watch the ingest flow without leaving the page."
      actions={
        <>
          <input className="opsnext-input" placeholder="Paste Whatnot live URL" value={streamUrl} onChange={(event) => setStreamUrl(event.target.value)} />
          <button className="opsnext-btn is-primary" onClick={handleStart}>Start Collector</button>
          <button className="opsnext-btn" onClick={handleStop}>Stop</button>
        </>
      }
    >
      <div className="opsnext-grid opsnext-grid--stats">
        <Stat label="Collector" value={streamStatus?.running ? 'Running' : 'Stopped'} hint={streamStatus?.stream_url || 'No active stream'} />
        <Stat label="Session" value={session?.name || 'No live session'} hint={session?.status || 'idle'} />
        <Stat label="Current Lot" value={session?.current_lot_number || '—'} hint={`${lotRows.length} staged items`} />
        <Stat label="Failed Ingests" value={failedRows.length} hint="Needs manual review" />
      </div>
      {message ? <div className="opsnext-message">{message}</div> : null}
      <div className="opsnext-grid opsnext-grid--split">
        <Panel title="Current Lot Staging" aside={<button className="opsnext-btn" onClick={handleRelease}>Release Lot</button>}>
          <SimpleTable
            columns={[
              { key: 'product_name', label: 'Product' },
              { key: 'barcode', label: 'Barcode' },
              { key: 'sku', label: 'SKU' },
              { key: 'unit_cost', label: 'Cost', render: (row) => fmtMoney(row.unit_cost) },
              { key: 'status', label: 'Status' },
            ]}
            rows={lotRows}
          />
        </Panel>
        <Panel title="Failed Ingest Queue">
          <SimpleTable
            columns={[
              { key: 'winner_username', label: 'Winner' },
              { key: 'lot_number', label: 'Lot' },
              { key: 'sale_price', label: 'Price', render: (row) => fmtMoney(row.sale_price) },
              { key: 'error_message', label: 'Issue' },
            ]}
            rows={failedRows}
          />
        </Panel>
      </div>
    </Page>
  );
}

function TVDisplayPage() {
  const { data: obsData } = usePolling('/api/obs/current', 1200);
  const product = obsData?.product || {};
  const tray = obsData?.tray || [];
  return (
    <Page title="TV Display" subtitle="Large-screen product storytelling and current item display for the live show.">
      <div className="opsnext-hero-card">
        <div className="opsnext-hero-copy">
          <p className="opsnext-kicker">Now showing</p>
          <h2>{product.name || 'Waiting for next scan'}</h2>
          <p>{product.notes || product.description || 'Scan a product to feed the display.'}</p>
          <div className="opsnext-chiprow">
            <span className="opsnext-chip">{product.barcode || 'No barcode'}</span>
            <span className="opsnext-chip">{fmtMoney(product.retail_price)}</span>
            <span className="opsnext-chip">{product.gender || 'No segment'}</span>
          </div>
        </div>
        <div className="opsnext-display-preview">
          {product.image_url ? <img src={product.image_url} alt={product.name || 'Product'} /> : <div className="opsnext-image-placeholder">TV</div>}
        </div>
      </div>
      <Panel title="Preview Tray">
        <SimpleTable
          columns={[
            { key: 'product_name', label: 'Product' },
            { key: 'barcode', label: 'Barcode' },
            { key: 'retail_price', label: 'Retail', render: (row) => fmtMoney(row.retail_price) },
          ]}
          rows={tray}
        />
      </Panel>
    </Page>
  );
}

function TVScannerPage() {
  const { data: obsData, refresh } = usePolling('/api/obs/current', 1500);
  const [barcode, setBarcode] = useState('');
  const [message, setMessage] = useState('');

  async function handleScan() {
    if (!barcode.trim()) return;
    await postApi('/api/obs/demo/scan', { barcode: barcode.trim() });
    setMessage(`Preview scanned: ${barcode.trim()}`);
    setBarcode('');
    refresh();
  }

  return (
    <Page title="TV Scanner" subtitle="This scanner is for previewing products on the TV display before or during the show.">
      <div className="opsnext-inline-actions">
        <input className="opsnext-input" placeholder="Scan barcode or SKU" value={barcode} onChange={(event) => setBarcode(event.target.value)} onKeyDown={(event) => event.key === 'Enter' ? handleScan() : null} />
        <button className="opsnext-btn is-primary" onClick={handleScan}>Preview Scan</button>
      </div>
      {message ? <div className="opsnext-message">{message}</div> : null}
      <Panel title="Current Display Payload">
        <pre className="opsnext-json">{JSON.stringify(obsData || {}, null, 2)}</pre>
      </Panel>
    </Page>
  );
}

function WinnerScannerPage() {
  const { data: streamStatus } = usePolling('/api/stream_status', 1500);
  const sessionId = streamStatus?.session_id;
  const { data: winnerState, refresh } = usePolling(sessionId ? `/api/winner_assignment/state?session_id=${encodeURIComponent(sessionId)}` : null, 1500, !!sessionId);
  const selected = (winnerState?.rows || [])[0] || null;
  const [barcode, setBarcode] = useState('');
  const [message, setMessage] = useState('');

  async function handleAssign() {
    if (!selected || !barcode.trim()) return;
    const result = await postApi('/api/winner_assignment/scan', { barcode: barcode.trim(), assignment_id: selected.id });
    if (result?.assignment?.id) {
      setMessage(`Assigned ${barcode.trim()} to lot ${selected.lot_number || '—'}.`);
      setBarcode('');
      refresh();
    }
  }

  async function handleConfirm() {
    if (!selected) return;
    await postApi('/api/winner_assignment/confirm', { assignment_id: selected.id });
    setMessage(`Confirmed lot ${selected.lot_number || '—'}.`);
    refresh();
  }

  return (
    <Page title="Winner Scanner" subtitle="This is the assistant station. Ignore the marketplace product title, scan the real sold barcode, then confirm the winner ticket.">
      <div className="opsnext-grid opsnext-grid--split">
        <Panel title="Current Winner Ticket">
          {selected ? (
            <div className="opsnext-ticket">
              <div><strong>Winner:</strong> @{selected.winner_username || 'unknown'}</div>
              <div><strong>Lot:</strong> {selected.lot_number || '—'}</div>
              <div><strong>Price:</strong> {fmtMoney(selected.sale_price)}</div>
              <div><strong>Status:</strong> {selected.status || 'pending'}</div>
            </div>
          ) : (
            <div className="opsnext-emptyblock">No pending winner ticket right now.</div>
          )}
        </Panel>
        <Panel title="Assign Sold Product">
          <div className="opsnext-inline-actions">
            <input className="opsnext-input" placeholder="Scan sold barcode" value={barcode} onChange={(event) => setBarcode(event.target.value)} onKeyDown={(event) => event.key === 'Enter' ? handleAssign() : null} />
            <button className="opsnext-btn is-primary" onClick={handleAssign} disabled={!selected}>Assign</button>
            <button className="opsnext-btn" onClick={handleConfirm} disabled={!selected}>Confirm</button>
          </div>
          {message ? <div className="opsnext-message">{message}</div> : null}
        </Panel>
      </div>
      <Panel title="Queue">
        <SimpleTable
          columns={[
            { key: 'winner_username', label: 'Winner' },
            { key: 'lot_number', label: 'Lot' },
            { key: 'sale_price', label: 'Sale Price', render: (row) => fmtMoney(row.sale_price) },
            { key: 'status', label: 'Status' },
          ]}
          rows={winnerState?.rows || []}
        />
      </Panel>
    </Page>
  );
}

function SessionPage() {
  const { data: sessionStats } = usePolling(['/api/v2/sessions/current/stats', '/api/session_stats'], 1500);
  const { data: topBuyers } = usePolling('/api/live_top_buyers', 3000);
  const session = sessionStats?.session || {};
  return (
    <Page title="Session" subtitle="Session-first monitoring for revenue, lots, buyers, and live health.">
      <div className="opsnext-grid opsnext-grid--stats">
        <Stat label="Revenue" value={fmtMoney(session.total_revenue)} />
        <Stat label="Platform Fee (6%)" value={fmtMoney(session.platform_fee ?? calcPlatformFee(session.total_revenue))} />
        <Stat label="Profit" value={fmtMoney(session.total_profit)} />
        <Stat label="Lots Sold" value={session.total_lots_sold ?? '—'} />
        <Stat label="Products Sold" value={session.total_products_sold ?? '—'} />
      </div>
      <Panel title="Top Buyers">
        <SimpleTable
          columns={[
            { key: 'username', label: 'Buyer' },
            { key: 'lots_won', label: 'Lots' },
            { key: 'spend', label: 'Spend', render: (row) => fmtMoney(row.spend) },
          ]}
          rows={topBuyers?.buyers || []}
        />
      </Panel>
    </Page>
  );
}

function AuctionResultsPage() {
  const [sessionId, setSessionId] = useState('');
  const query = useMemo(() => sessionId ? `/api/auction_results?session_id=${encodeURIComponent(sessionId)}` : '/api/auction_results', [sessionId]);
  const { data: sessions } = usePolling('/api/sessions/list?scope=company', 6000);
  const { data: results } = usePolling(query, 4000);
  return (
    <Page title="Auction Results" subtitle="Session-aware result review, profitability, and post-show cleanup." actions={
      <select className="opsnext-select" value={sessionId} onChange={(event) => setSessionId(event.target.value)}>
        <option value="">All sessions</option>
        {(sessions?.rows || []).map((session) => <option key={session.id} value={session.id}>{session.name || `Session ${session.id}`}</option>)}
      </select>
    }>
      <Panel title="Results">
        <SimpleTable
          columns={[
            { key: 'session_id_name', label: 'Session' },
            { key: 'winner_username', label: 'Winner' },
            { key: 'product_name', label: 'Product' },
            { key: 'sale_price', label: 'Sale', render: (row) => fmtMoney(row.sale_price) },
            { key: 'profit', label: 'Profit', render: (row) => fmtMoney(row.profit) },
          ]}
          rows={results?.rows || []}
        />
      </Panel>
    </Page>
  );
}

function SessionSalesPage() {
  const { data: sales } = usePolling('/api/sale_orders?scope=company', 5000);
  return (
    <Page title="Session Sales" subtitle="Session-wise sales and order review, matching the backoffice side of the current dashboard.">
      <Panel title="Orders">
        <SimpleTable
          columns={[
            { key: 'whatnot_session_id_name', label: 'Session' },
            { key: 'name', label: 'Order' },
            { key: 'whatnot_buyer_username', label: 'Buyer' },
            { key: 'amount_total', label: 'Total', render: (row) => fmtMoney(row.amount_total) },
            { key: 'fulfillment_status', label: 'Fulfillment' },
          ]}
          rows={sales?.rows || []}
        />
      </Panel>
    </Page>
  );
}

function InventoryPage() {
  const { data: inventory } = usePolling('/api/inventory?status=all', 6000);
  return (
    <Page title="Inventory" subtitle="Inventory and prep control from the new frontend, while the current backend remains intact.">
      <Panel title="Products">
        <SimpleTable
          columns={[
            { key: 'name', label: 'Product' },
            { key: 'sku', label: 'SKU' },
            { key: 'barcode', label: 'Barcode' },
            { key: 'on_hand_qty', label: 'On Hand' },
            { key: 'retail_price', label: 'Retail', render: (row) => fmtMoney(row.retail_price) },
          ]}
          rows={inventory?.rows || []}
        />
      </Panel>
    </Page>
  );
}

function UsersPage() {
  const { data: customers } = usePolling('/api/customers?scope=company', 6000);
  return (
    <Page title="Users" subtitle="Customer and user intelligence pulled from the current backend.">
      <Panel title="Customers">
        <SimpleTable
          columns={[
            { key: 'whatnot_username', label: 'Username' },
            { key: 'display_name', label: 'Display Name' },
            { key: 'email', label: 'Email' },
            { key: 'total_orders', label: 'Orders' },
          ]}
          rows={customers?.rows || []}
        />
      </Panel>
    </Page>
  );
}

export default function OpsNextApp() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/ops-next/operator" replace />} />
        <Route path="/ops-next/operator" element={<OperatorPage />} />
        <Route path="/ops-next/tv-display" element={<TVDisplayPage />} />
        <Route path="/ops-next/tv-scanner" element={<TVScannerPage />} />
        <Route path="/ops-next/winner-scanner" element={<WinnerScannerPage />} />
        <Route path="/ops-next/session" element={<SessionPage />} />
        <Route path="/ops-next/auction-results" element={<AuctionResultsPage />} />
        <Route path="/ops-next/session-sales" element={<SessionSalesPage />} />
        <Route path="/ops-next/inventory" element={<InventoryPage />} />
        <Route path="/ops-next/users" element={<UsersPage />} />
      </Routes>
    </Shell>
  );
}
