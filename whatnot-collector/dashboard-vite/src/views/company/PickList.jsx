/**
 * PickList — Upload a Whatnot packing-slip PDF, match lots to real products,
 * and generate a compact printable pick list for the shipping guy.
 * Saves pick list to DB, syncs customers, confirms sale orders, deducts inventory.
 */
import { useState, useEffect, useRef } from 'react';
import { fetchApi } from '../../hooks/useApi';

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
function fmt$(n) { return '$' + Number(n || 0).toFixed(2); }

function isGiveawayItem(item) {
  const name = String(item.product_name || item.whatnot_name || '').toLowerCase();
  return /give\s*away|givey|giveyyy|random give|freebie/.test(name);
}

// Merge shipments with the same username into one, dedup lots within each
function mergeShipmentsByUsername(shipments) {
  const byUsername = {};
  for (const ship of shipments) {
    const uname = (ship.username || '').toLowerCase().trim();
    if (!uname) continue;
    const filtered = (ship.items || []).filter((i) => !isGiveawayItem(i));
    if (!byUsername[uname]) {
      byUsername[uname] = { ...ship, items: [...filtered] };
    } else {
      byUsername[uname].items.push(...filtered);
      if (ship.tracking_number && ship.tracking_number !== byUsername[uname].tracking_number) {
        byUsername[uname].tracking_number = [byUsername[uname].tracking_number, ship.tracking_number].filter(Boolean).join(', ');
      }
    }
  }
  return Object.values(byUsername).map((ship) => {
    // Deduplicate by lot_number within the merged shipment
    const seenLots = new Set();
    ship.items = ship.items.filter((item) => {
      const key = String(item.lot_number || '').trim();
      if (!key) return true;
      if (seenLots.has(key)) return false;
      seenLots.add(key);
      return true;
    });
    ship.total_items = ship.items.length;
    ship.total_price = ship.items.reduce((s, i) => s + (i.price || i.sale_price || 0), 0);
    return ship;
  });
}
function esc(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export default function PickList({ sessions }) {
  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [sessionId, setSessionId] = useState('');
  const [savedLists, setSavedLists] = useState([]);
  const [loadingList, setLoadingList] = useState(false);
  const [pdfMessage, setPdfMessage] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  // Load saved pick lists on mount
  useEffect(() => { loadSavedLists(); }, []);

  async function loadSavedLists() {
    try {
      const d = await fetchApi('/api/picklists');
      setSavedLists(d.pick_lists || []);
    } catch {}
  }

  async function requestAnnotatedPdf(file, { openPreview = false } = {}) {
    const annotateParams = new URLSearchParams();
    if (sessionId) annotateParams.set('session_id', sessionId);
    annotateParams.set('filename', file.name);
    const buf = await file.arrayBuffer();
    const annotateRes = await fetch(`${API_BASE}/api/whatnot_labels/enrich_pdf?${annotateParams}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/pdf' },
      body: buf,
    });
    if (!annotateRes.ok) {
      const annotateError = await annotateRes.text().catch(() => '');
      throw new Error(annotateError || 'Annotated PDF generation failed');
    }
    const blob = await annotateRes.blob();
    const contentDisposition = annotateRes.headers.get('Content-Disposition') || '';
    const filenameMatch = contentDisposition.match(/filename="([^"]+)"/i);
    const downloadName = filenameMatch?.[1] || file.name.replace(/\.pdf$/i, '-with-products.pdf');
    const blobUrl = URL.createObjectURL(blob);
    if (openPreview) {
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      return { blobUrl, downloadName };
    }
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = downloadName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    return { blobUrl, downloadName };
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setError(null);
    setPdfMessage('');
  }

  async function handlePreviewPdf() {
    if (!selectedFile) return;
    setPreviewing(true);
    setError(null);
    setPdfMessage('');
    try {
      await requestAnnotatedPdf(selectedFile, { openPreview: true });
      setPdfMessage('Preview opened in a new tab with matched product names.');
    } catch (err) {
      setError(err.message || 'Unable to preview PDF.');
    } finally {
      setPreviewing(false);
    }
  }

  async function handleDownloadPdf() {
    if (!selectedFile) return;
    setPreviewing(true);
    setError(null);
    setPdfMessage('');
    try {
      await requestAnnotatedPdf(selectedFile, { openPreview: false });
      setPdfMessage('Annotated packing slip downloaded with matched product names.');
    } catch (err) {
      setError(err.message || 'Unable to download annotated PDF.');
    } finally {
      setPreviewing(false);
    }
  }

  async function handleUpload() {
    const file = selectedFile;
    if (!file) return;
    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const buf = await file.arrayBuffer();
      const params = new URLSearchParams();
      if (sessionId) params.set('session_id', sessionId);
      params.set('filename', file.name);
      const url = `${API_BASE}/api/picklist/upload?${params}`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/pdf' },
        body: buf,
      });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || 'Upload failed');
      // Merge same-username shipments and filter giveaways
      data.shipments = mergeShipmentsByUsername(data.shipments || []);
      data.summary = {
        ...data.summary,
        total_shipments: data.shipments.length,
        total_lots: data.shipments.reduce((s, sh) => s + sh.items.length, 0),
        total_revenue: data.shipments.reduce((s, sh) => s + sh.total_price, 0),
      };
      setResult(data);
      loadSavedLists(); // refresh saved list
      setPdfMessage('Pick list synced. Matching orders were confirmed, and missing lots were cancelled.');
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setError(err.message);
    }
    setUploading(false);
  }

  async function loadSavedPickList(plId) {
    setLoadingList(true);
    setError(null);
    try {
      const d = await fetchApi(`/api/picklists/detail?id=${plId}`);
      const pl = d.pick_list;
      const items = d.items || [];

      // Group flat items back into shipment objects by shipment_index
      const groups = {};
      for (const item of items) {
        const si = item.shipment_index;
        if (!groups[si]) {
          groups[si] = {
            username: item.username,
            buyer_name: item.buyer_name,
            address: item.address,
            tracking_number: item.tracking_number,
            shipping_method: item.shipping_method,
            ship_date: item.ship_date,
            weight: item.weight,
            customer_id: item.customer_id,
            sale_order_id: item.sale_order_id,
            items: [],
            total_price: 0,
            total_items: 0,
          };
        }
        groups[si].items.push({
          lot_number: item.lot_number,
          product_name: item.product_name,
          barcode: item.barcode,
          sku: item.sku,
          price: item.sale_price,
          order_id: item.order_id,
          matched: !!item.matched,
        });
      }

      // Merge same-username shipments, filter giveaways, dedup lots
      const shipments = mergeShipmentsByUsername(Object.values(groups));
      const totalLots = shipments.reduce((s, sh) => s + sh.items.length, 0);
      const totalRevenue = shipments.reduce((s, sh) => s + sh.total_price, 0);

      setResult({
        shipments,
        pick_list_id: pl.id,
        summary: {
          total_shipments: shipments.length,
          total_lots: totalLots,
          matched: pl.matched_lots,
          unmatched: pl.unmatched_lots,
          total_revenue: totalRevenue,
          customers_synced: pl.customers_synced,
          orders_synced: pl.orders_synced,
          inventory_deducted: pl.inventory_deducted,
          payments_approved: 0,
          payment_approval_orders: 0,
          session_id: pl.session_id,
          pick_list_id: pl.id,
        },
      });
    } catch (err) {
      setError(err.message);
    }
    setLoadingList(false);
  }

  const summary = result?.summary;
  const shipments = result?.shipments || [];
  const pullSummary = buildPullSummary(shipments);

  function printSheet(mode) {
    if (!shipments.length) return;
    const html = buildPrintHtml({ mode, shipments, summary, pullSummary });
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, '_blank', 'width=1100,height=900');
    if (!win) return;
    win.focus();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  return (
    <div style={{ padding: 20, maxWidth: 1100, margin: '0 auto' }}>

      {/* Upload Section */}
      <div className="company-panel no-print" style={{ marginBottom: 16 }}>
        <div className="company-panel-head">
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>
            Upload Packing Slip PDF
          </div>
        </div>
        <div className="company-panel-body" style={{ padding: '16px 20px' }}>
          <div style={{
            marginBottom: 14,
            padding: '12px 14px',
            borderRadius: 14,
            background: 'rgba(37, 99, 235, 0.06)',
            border: '1px solid rgba(147, 197, 253, 0.45)',
            color: '#334155',
            fontSize: 13,
            lineHeight: 1.5,
          }}>
            Uploading the Whatnot label PDF will confirm matching pending orders as paid and shipped. Orders in that session with lot numbers missing from the uploaded labels are marked cancelled automatically.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <select
              value={sessionId}
              onChange={e => setSessionId(e.target.value)}
              style={{
                padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border-default)',
                background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontSize: 13,
              }}
            >
              <option value="">All Sessions (auto-match)</option>
              {(sessions || []).map(s => (
                <option key={s.id} value={s.id}>
                  {s.name || `Session #${s.id}`} — {s.status}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 8,
                padding: '8px 18px', borderRadius: 8, cursor: (uploading || previewing) ? 'wait' : 'pointer',
                background: 'var(--accent)', color: '#000', fontWeight: 700, fontSize: 13,
                opacity: (uploading || previewing) ? 0.6 : 1,
                border: 'none',
              }}
            >
              Choose PDF
            </button>
            <input ref={fileInputRef} type="file" accept=".pdf" onChange={handleFileSelect} style={{ display: 'none' }} disabled={uploading || previewing} />
            {selectedFile ? (
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{selectedFile.name}</span>
            ) : null}
            <button
              type="button"
              onClick={handlePreviewPdf}
              disabled={!selectedFile || uploading || previewing}
              style={{
                padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border-default)',
                background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontWeight: 700,
                fontSize: 13, cursor: (!selectedFile || uploading || previewing) ? 'not-allowed' : 'pointer',
                opacity: (!selectedFile || uploading || previewing) ? 0.5 : 1,
              }}
            >
              {previewing ? 'Opening…' : 'Preview Clean PDF'}
            </button>
            <button
              type="button"
              onClick={handleDownloadPdf}
              disabled={!selectedFile || uploading || previewing}
              style={{
                padding: '8px 14px', borderRadius: 8, border: '1px solid var(--border-default)',
                background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontWeight: 700,
                fontSize: 13, cursor: (!selectedFile || uploading || previewing) ? 'not-allowed' : 'pointer',
                opacity: (!selectedFile || uploading || previewing) ? 0.5 : 1,
              }}
            >
              Download Clean PDF
            </button>
            <button
              type="button"
              onClick={handleUpload}
              disabled={!selectedFile || uploading || previewing}
              style={{
                padding: '8px 18px', borderRadius: 8, border: '1px solid rgba(16,185,129,0.22)',
                background: 'rgba(16,185,129,0.12)', color: '#047857', fontWeight: 800, fontSize: 13,
                cursor: (!selectedFile || uploading || previewing) ? 'not-allowed' : 'pointer',
                opacity: (!selectedFile || uploading || previewing) ? 0.5 : 1,
              }}
            >
              {uploading ? 'Syncing…' : 'Confirm & Sync Orders'}
            </button>
            {result && (
              <>
                <button onClick={() => printSheet('pick')} style={{
                  padding: '8px 18px', borderRadius: 8, border: '1px solid var(--border-default)',
                  background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontWeight: 700,
                  fontSize: 13, cursor: 'pointer',
                }}>
                  Print Pick List
                </button>
                <button onClick={() => printSheet('grab')} style={{
                  padding: '8px 18px', borderRadius: 8, border: '1px solid var(--border-default)',
                  background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontWeight: 700,
                  fontSize: 13, cursor: 'pointer',
                }}>
                  Print Grab List
                </button>
                <button onClick={() => printSheet('both')} style={{
                  padding: '8px 18px', borderRadius: 8, border: '1px solid var(--border-default)',
                  background: 'var(--bg-elevated)', color: 'var(--text-primary)', fontWeight: 700,
                  fontSize: 13, cursor: 'pointer',
                }}>
                  Print Both
                </button>
              </>
            )}
          </div>
          {error && <div style={{ color: 'var(--accent-coral)', marginTop: 10, fontSize: 13 }}>{error}</div>}
          {!error && pdfMessage ? <div style={{ color: 'var(--accent-emerald)', marginTop: 10, fontSize: 13 }}>{pdfMessage}</div> : null}
        </div>
      </div>

      {/* Saved Pick Lists */}
      {savedLists.length > 0 && (
        <div className="company-panel no-print" style={{ marginBottom: 16 }}>
          <div className="company-panel-head">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600 }}>
              Saved Pick Lists ({savedLists.length})
            </div>
          </div>
          <div className="company-panel-body" style={{ padding: 0 }}>
            {savedLists.map(pl => (
              <button
                key={pl.id}
                onClick={() => loadSavedPickList(pl.id)}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  width: '100%', padding: '10px 20px', border: 'none', cursor: 'pointer',
                  borderBottom: '1px solid var(--border-default)', background: 'transparent',
                  color: 'var(--text-primary)', textAlign: 'left',
                  outline: result?.pick_list_id === pl.id ? '2px solid var(--accent)' : 'none',
                }}
              >
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {pl.filename || `Pick List #${pl.id}`}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {pl.total_shipments} shipments · {pl.total_lots} lots · {pl.matched_lots} matched
                    {pl.session_id ? ` · Session #${pl.session_id}` : ''}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--accent-amber)' }}>{fmt$(pl.total_revenue)}</div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    {new Date(pl.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Summary Stats */}
      {summary && (
        <div className="no-print" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10, marginBottom: 16 }}>
          <MiniStat label="Shipments" value={summary.total_shipments} />
          <MiniStat label="Lots" value={summary.total_lots} />
          <MiniStat label="Matched" value={summary.matched} color="var(--accent-emerald)" />
          <MiniStat label="Unmatched" value={summary.unmatched} color={summary.unmatched > 0 ? 'var(--accent-coral)' : 'var(--text-secondary)'} />
          <MiniStat label="Revenue" value={fmt$(summary.total_revenue)} color="var(--accent-amber)" />
          <MiniStat label="Customers" value={summary.customers_synced || 0} color="var(--accent-blue, #60a5fa)" />
          <MiniStat label="Orders" value={summary.orders_synced || 0} color="var(--accent-emerald)" />
          <MiniStat label="Cancelled" value={summary.orders_cancelled || 0} color={summary.orders_cancelled > 0 ? 'var(--accent-coral)' : 'var(--text-secondary)'} />
          <MiniStat label="Inventory" value={`-${summary.inventory_deducted || 0}`} color="var(--accent-coral)" />
          <MiniStat label="Payments Approved" value={summary.payments_approved || 0} color="var(--accent-blue, #60a5fa)" />
        </div>
      )}

      {loadingList && <p style={{ color: 'var(--text-muted)', fontSize: 13, padding: 20 }}>Loading...</p>}

      {/* Pick List — compact printable format */}
      {shipments.length > 0 && (
        <div className="picklist-printable">
          <style>{`
            .picklist-printable {
              width: 100%;
              max-width: 1000px;
              margin: 0 auto;
              background: #fff;
            }
            .pick-print-grid {
              display: grid;
              grid-template-columns: minmax(0, 1.6fr) minmax(250px, 0.9fr);
              gap: 14px;
              align-items: start;
            }
            .pick-side-card {
              border: 1px solid var(--border-default);
              border-radius: 10px;
              padding: 8px;
              background: #fff;
            }
            .pick-table { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
            .pick-table th { background: var(--bg-elevated); text-align: left; padding: 5px 7px; font-size: 10px; font-weight: 800; color: var(--text-secondary); border-bottom: 2px solid var(--border-default); text-transform: uppercase; letter-spacing: 0.06em; }
            .pick-table td { padding: 5px 7px; border-bottom: 1px solid var(--border-default); vertical-align: middle; line-height: 1.25; }
            .pick-buyer-cell { width: 120px; }
            .pick-product-cell { width: auto; }
            .pick-price-cell { width: 72px; text-align: right; }
            .pick-ok-cell { width: 30px; text-align: center; }
            .pull-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
            .pull-table th { text-align: left; padding: 4px 6px; font-size: 9px; font-weight: 800; color: var(--text-secondary); border-bottom: 2px solid var(--border-default); text-transform: uppercase; letter-spacing: 0.06em; }
            .pull-table td { padding: 4px 6px; border-bottom: 1px solid var(--border-default); vertical-align: top; line-height: 1.2; }
            .pull-qty-cell { width: 34px; text-align: center; font-weight: 900; }
            .pull-ok-cell { width: 26px; text-align: center; }
            .pull-lots-cell { width: 74px; font-size: 10px; color: var(--text-secondary); }

            @media print {
              /* Full-page readable packing sheet */
              @page {
                size: A4 portrait;
                margin: 8mm 8mm;
              }

              /* Hide everything on the page */
              body > * { display: none !important; }

              /* Then show only the printable container — walk up and unhide ancestors */
              .picklist-printable {
                display: block !important;
                visibility: visible !important;
              }
              .picklist-printable * {
                visibility: visible !important;
              }
              .no-print, .no-print * { display: none !important; }

              /* Remove all scroll/overflow/height constraints on every ancestor */
              html, body,
              body > *, body > * > *, body > * > * > *,
              body > * > * > * > *, body > * > * > * > * > *,
              body > * > * > * > * > * > *,
              body > * > * > * > * > * > * > * {
                display: block !important;
                height: auto !important;
                max-height: none !important;
                overflow: visible !important;
                position: static !important;
              }

              /* The picklist itself: full width, natural flow */
              .picklist-printable {
                position: static !important;
                width: 100% !important;
                max-width: none !important;
                height: auto !important;
                overflow: visible !important;
                margin: 0 !important;
                padding: 0 !important;
              }
              .pick-print-grid {
                display: grid !important;
                grid-template-columns: minmax(0, 1.55fr) minmax(0, 0.95fr) !important;
                gap: 8px !important;
                align-items: start !important;
              }
              .pick-side-card {
                border: 1pt solid #aaa !important;
                border-radius: 0 !important;
                padding: 5px !important;
              }

              /* Table printing — pack tight, no forced breaks */
              .pick-table { page-break-inside: auto; width: 100% !important; }
              .pick-table thead { display: table-header-group; }
              .pick-row { page-break-inside: avoid; page-break-before: auto; page-break-after: auto; }
              .pick-buyer { page-break-inside: avoid; page-break-before: auto; page-break-after: auto; }

              /* Force all black ink — no color printing */
              .picklist-printable, .picklist-printable * {
                color: #000 !important;
                background: #fff !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
              }
              .pick-table { font-size: 10.5pt !important; table-layout: fixed !important; }
              .pick-table th { background: #ececec !important; color: #000 !important; border-bottom: 1.5pt solid #000 !important; font-size: 8.5pt !important; padding: 4px 6px !important; }
              .pick-table td { border-bottom: 0.5pt solid #aaa !important; padding: 4px 6px !important; line-height: 1.15 !important; font-size: 9.5pt !important; }
              .pick-buyer-cell { width: 24% !important; max-width: none !important; }
              .pick-product-cell { width: 50% !important; }
              .pick-price-cell { width: 14% !important; }
              .pick-ok-cell { width: 6% !important; }
              .pull-table { width: 100% !important; font-size: 8.5pt !important; table-layout: fixed !important; }
              .pull-table th { background: #ececec !important; color: #000 !important; border-bottom: 1.5pt solid #000 !important; font-size: 7.5pt !important; padding: 3px 4px !important; }
              .pull-table td { border-bottom: 0.5pt solid #aaa !important; padding: 3px 4px !important; line-height: 1.15 !important; font-size: 8pt !important; }
              .pull-qty-cell { width: 12% !important; }
              .pull-lots-cell { width: 26% !important; font-size: 7.5pt !important; color: #000 !important; }
              .pull-ok-cell { width: 10% !important; }

              /* Checkboxes */
              .pick-check-box {
                border: 2px solid #000 !important;
                background: #fff !important;
                width: 14px !important;
                height: 14px !important;
              }

              /* Header */
              .picklist-print-header { font-size: 17pt !important; }
              .pick-print-meta { font-size: 10pt !important; }
            }
          `}</style>

          {/* Compact flat table — one row per item, username inline */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, gap: 12 }}>
            <h3 className="picklist-print-header" style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>
              Pick List — {shipments.length} shipments, {summary?.total_lots} lots
            </h3>
            <span className="pick-print-meta" style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {new Date().toLocaleDateString()} {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>

          <div className="pick-print-grid">
            <div>
              <table className="pick-table">
                <thead>
                  <tr>
                    <th style={{ width: 22 }}>#</th>
                    <th className="pick-buyer-cell">Buyer</th>
                    <th style={{ width: 35 }}>Lot</th>
                    <th className="pick-product-cell">Product</th>
                    <th className="pick-price-cell">Price</th>
                    <th className="pick-ok-cell" style={{ padding: 2 }}>
                      <span style={{ fontSize: 9 }}>OK</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shipments.flatMap((ship, si) =>
                    ship.items.map((item, ii) => (
                      <tr key={`${si}-${ii}`} className="pick-row">
                        <td style={{ fontSize: 10, color: 'var(--text-muted)' }}>{si + 1}</td>
                        <td className="pick-buyer-cell" style={{ fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {ii === 0 ? (
                            <span style={{ fontWeight: 700 }}>@{ship.username}</span>
                          ) : (
                            <span style={{ color: 'var(--text-muted)' }}>〃</span>
                          )}
                        </td>
                        <td style={{ fontWeight: 700, fontSize: 11 }}>#{item.lot_number}</td>
                        <td className="pick-product-cell" style={{ fontSize: 11, color: item.matched ? 'var(--text-primary)' : 'var(--accent-coral)', wordBreak: 'break-word' }}>
                          {item.product_name}
                        </td>
                        <td className="pick-price-cell" style={{ fontWeight: 700, fontSize: 11 }}>{fmt$(item.price)}</td>
                        <td className="pick-ok-cell" style={{ padding: 2 }}>
                          <span className="pick-check-box" style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid var(--border-default)', borderRadius: 2 }} />
                        </td>
                      </tr>
                    ))
                  )}
                  <tr style={{ fontWeight: 800, borderTop: '2px solid var(--border-default)' }}>
                    <td colSpan={4} style={{ textAlign: 'right', paddingTop: 6 }}>
                      {shipments.length} buyers / {summary?.total_lots} items
                    </td>
                    <td style={{ textAlign: 'right', paddingTop: 6 }}>{fmt$(summary?.total_revenue)}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="pick-side-card">
              <div style={{ fontSize: 12, fontWeight: 800, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Bulk Pull Summary
              </div>
              <table className="pull-table">
                <thead>
                  <tr>
                    <th className="pull-qty-cell">Qty</th>
                    <th>Product</th>
                    <th className="pull-lots-cell">Lots</th>
                    <th className="pull-ok-cell">OK</th>
                  </tr>
                </thead>
                <tbody>
                  {pullSummary.map((row) => (
                    <tr key={row.key}>
                      <td className="pull-qty-cell">{row.qty}</td>
                      <td style={{ fontWeight: 700, wordBreak: 'break-word' }}>{row.product_name}</td>
                      <td className="pull-lots-cell">{row.lots_label}</td>
                      <td className="pull-ok-cell">
                        <span className="pick-check-box" style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid var(--border-default)', borderRadius: 2 }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function buildPullSummary(shipments) {
  const map = new Map();
  for (const ship of shipments || []) {
    for (const item of ship.items || []) {
      const parsed = parseProductLabel(item.product_name);
      const key = String(item.barcode || item.sku || parsed.name).trim().toLowerCase();
      const current = map.get(key) || {
        key,
        product_name: parsed.name,
        qty: 0,
        lots: [],
      };
      current.qty += 1;
      if (item.lot_number != null && item.lot_number !== '') current.lots.push(String(item.lot_number));
      map.set(key, current);
    }
  }
  return [...map.values()]
    .map((row) => ({
      ...row,
      lots_label: row.lots.sort((a, b) => Number(a) - Number(b)).map((lot) => `#${lot}`).join(', '),
    }))
    .sort((a, b) => b.qty - a.qty || a.product_name.localeCompare(b.product_name));
}

function parseProductLabel(label) {
  const raw = String(label || '').trim();
  const qtyMatch = raw.match(/\s+x(\d+)\s*$/i);
  const qty = qtyMatch ? Number(qtyMatch[1] || 1) : 1;
  let name = qtyMatch ? raw.slice(0, qtyMatch.index).trim() : raw;
  name = name.replace(/^\[[^\]]+\]\s*/, '').trim();
  return { name, qty: Number.isFinite(qty) && qty > 0 ? qty : 1 };
}

function buildPrintHtml({ mode, shipments, summary, pullSummary }) {
  const now = new Date();
  const nowLabel = now.toLocaleDateString('en-US', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' })
    + ' · ' + now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  // Alternate row shading per buyer group
  let rowIdx = 0;
  const pickRows = shipments.flatMap((ship, si) => {
    const shade = si % 2 === 0 ? '#fff' : '#f7f7f9';
    return (ship.items || []).map((item, ii) => {
      rowIdx++;
      return `
      <tr style="background:${shade}">
        <td class="num" style="color:#888;font-size:7.5pt">${rowIdx}</td>
        <td class="buyer">${ii === 0
          ? `<span class="tag">@${esc(ship.username)}</span>`
          : `<span style="color:#bbb;font-size:9pt;padding-left:4px">〃</span>`}</td>
        <td class="lot"><span class="lot-badge">#${esc(item.lot_number)}</span></td>
        <td class="product">${esc(item.product_name)}</td>
        <td class="price">${fmt$(item.price || item.sale_price)}</td>
        <td class="ok"><span class="box"></span></td>
      </tr>`;
    });
  }).join('');

  const grabRows = (pullSummary || []).map((row, i) => `
    <tr style="background:${i % 2 === 0 ? '#fff' : '#f7f7f9'}">
      <td class="qty"><span class="qty-badge">${esc(row.qty)}</span></td>
      <td class="product">${esc(row.product_name)}</td>
      <td class="lots">${esc(row.lots_label)}</td>
      <td class="ok"><span class="box"></span></td>
    </tr>`).join('');

  const totalLots = summary?.total_lots || 0;
  const totalRev = summary?.total_revenue || 0;
  const totalShip = shipments.length;

  const header = (title, sub) => `
    <div class="page-header">
      <div class="header-left">
        <div class="brand">ynfdeals</div>
        <div class="title-block">
          <h1>${title}</h1>
          <div class="sub">${sub}</div>
        </div>
      </div>
      <div class="header-right">
        <div class="stat-pill">${totalShip} Shipments</div>
        <div class="stat-pill">${totalLots} Lots</div>
        <div class="stat-pill rev">${fmt$(totalRev)}</div>
        <div class="meta">${esc(nowLabel)}</div>
      </div>
    </div>
    <div class="divider"></div>`;

  const pickSection = `
    <section class="sheet">
      ${header('Pick List', 'One row per item — check off as packed')}
      <table class="main-table">
        <thead>
          <tr>
            <th class="num">#</th>
            <th class="buyer">Buyer</th>
            <th class="lot">Lot</th>
            <th class="product">Product</th>
            <th class="price">Price</th>
            <th class="ok">✓</th>
          </tr>
        </thead>
        <tbody>
          ${pickRows}
          <tr class="total-row">
            <td colspan="3"></td>
            <td style="text-align:right;font-size:8pt;color:#555">${totalShip} buyers · ${totalLots} items</td>
            <td class="price" style="font-size:10pt">${fmt$(totalRev)}</td>
            <td></td>
          </tr>
        </tbody>
      </table>
    </section>`;

  const grabSection = `
    <section class="sheet${mode === 'both' ? ' break-before' : ''}">
      ${header('Grab List', 'Pull from shelf before packing — check off each product')}
      <table class="grab-table">
        <thead>
          <tr>
            <th class="qty">Qty</th>
            <th class="product">Product</th>
            <th class="lots">Lot Numbers</th>
            <th class="ok">✓</th>
          </tr>
        </thead>
        <tbody>
          ${grabRows}
        </tbody>
      </table>
    </section>`;

  const body = mode === 'pick' ? pickSection : mode === 'grab' ? grabSection : `${pickSection}${grabSection}`;

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>${mode === 'grab' ? 'Grab List' : mode === 'pick' ? 'Pick List' : 'Pick & Grab List'} · ynfdeals</title>
  <style>
    @page { size: A4 portrait; margin: 10mm 10mm 12mm 10mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
      background: #fff;
      color: #111;
      font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
      font-size: 9pt;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }

    /* ── Header ── */
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      padding: 0 0 8px 0;
    }
    .header-left { display: flex; align-items: center; gap: 14px; }
    .brand {
      font-size: 13pt;
      font-weight: 900;
      letter-spacing: -0.5px;
      color: #fff;
      background: #1a1a2e;
      padding: 5px 11px;
      border-radius: 6px;
    }
    h1 {
      font-size: 16pt;
      font-weight: 800;
      color: #1a1a2e;
      line-height: 1;
    }
    .sub { font-size: 7.5pt; color: #888; margin-top: 3px; }
    .header-right {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 4px;
    }
    .stat-pills { display: flex; gap: 6px; }
    .stat-pill {
      display: inline-block;
      background: #f0f0f5;
      border-radius: 20px;
      padding: 2px 10px;
      font-size: 7.5pt;
      font-weight: 700;
      color: #444;
    }
    .stat-pill.rev { background: #e8f5e9; color: #2e7d32; }
    .meta { font-size: 7pt; color: #aaa; margin-top: 2px; }
    .divider {
      height: 2.5px;
      background: linear-gradient(90deg, #1a1a2e 0%, #7c3aed 60%, #e5e7eb 100%);
      border-radius: 2px;
      margin-bottom: 8px;
    }

    /* ── Tables ── */
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    thead tr { background: #1a1a2e; }
    th {
      color: #fff;
      padding: 5px 7px;
      font-size: 7pt;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.07em;
      text-align: left;
    }
    td {
      padding: 4.5px 7px;
      font-size: 8.5pt;
      line-height: 1.2;
      vertical-align: middle;
      border-bottom: 1px solid #e8e8ee;
    }

    /* Pick List columns */
    .num    { width: 5%; text-align: center; }
    .buyer  { width: 19%; }
    .lot    { width: 8%; text-align: center; }
    .product{ width: auto; word-break: break-word; }
    .price  { width: 11%; text-align: right; font-weight: 700; color: #1a1a2e; }
    .ok     { width: 6%; text-align: center; }

    /* Grab List columns */
    .qty    { width: 9%; text-align: center; }
    .lots   { width: 24%; font-size: 7.5pt; color: #555; }

    /* Badges */
    .tag {
      display: inline-block;
      background: #ede9fe;
      color: #5b21b6;
      border-radius: 4px;
      padding: 1px 6px;
      font-size: 8pt;
      font-weight: 700;
    }
    .lot-badge {
      display: inline-block;
      background: #1a1a2e;
      color: #fff;
      border-radius: 4px;
      padding: 1px 6px;
      font-size: 8pt;
      font-weight: 800;
    }
    .qty-badge {
      display: inline-block;
      background: #7c3aed;
      color: #fff;
      border-radius: 20px;
      padding: 1px 9px;
      font-size: 9pt;
      font-weight: 900;
    }

    /* Checkbox */
    .box {
      display: inline-block;
      width: 13px; height: 13px;
      border: 1.5px solid #999;
      border-radius: 3px;
      background: #fff;
    }

    /* Total row */
    .total-row td {
      font-weight: 800;
      border-top: 2px solid #1a1a2e;
      border-bottom: none;
      background: #f7f7fb;
    }

    /* Page break */
    .break-before { page-break-before: always; padding-top: 6px; }
    .sheet { width: 100%; }
  </style>
</head>
<body>
  ${body}
  <script>window.addEventListener('load',function(){setTimeout(function(){window.print();},150);});</script>
</body>
</html>`;
}

function MiniStat({ label, value, color }) {
  return (
    <div style={{
      background: 'var(--bg-panel)', border: '1px solid var(--border-default)',
      borderRadius: 10, padding: '12px 16px',
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}
