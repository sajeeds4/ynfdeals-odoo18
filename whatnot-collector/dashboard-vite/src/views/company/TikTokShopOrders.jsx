import { useEffect, useMemo, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  fmt, fmtDt,
  Badge, FilterBar, SearchInput,
  TableShell, Thead, EmptyRow, PrimaryBtn,
} from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '6px 10px',
  fontSize: 12,
  minHeight: 34,
  lineHeight: 1.2,
  width: '100%',
};

function sourceBadge(source) {
  if (source === 'tiktok_shop') {
    return { label: 'TikTok Shop', bg: 'rgba(236,72,153,0.16)', color: '#ec4899' };
  }
  if (source === 'tiktok_live') {
    return { label: 'TikTok LIVE', bg: 'rgba(249,115,22,0.16)', color: '#ea580c' };
  }
  return { label: source || 'Other', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' };
}

function extractLotNumber(order) {
  const notes = String(order?.notes || '');
  const externalRef = String(order?.external_order_ref || '');
  const notesMatch = notes.match(/(?:^|\n)Lot:\s*([^\n]+)/i);
  if (notesMatch?.[1]) return notesMatch[1].trim();
  const refMatch = externalRef.match(/-LOT-([^-]+)$/i);
  if (refMatch?.[1]) return refMatch[1].trim();
  const colonMatch = externalRef.match(/^tiktok_(?:live|shop):[^:]+:([^:]+)$/i);
  if (colonMatch?.[1]) return colonMatch[1].trim();
  return '';
}

export default function TikTokShopOrders({
  source = 'tiktok_shop',
  title,
  createTitle,
  importTitle,
  emptyMessage,
  showCreate = true,
  showImport = true,
  liveLotMapCsvText = '',
  liveLotMapLabel = '',
  rowFilter = null,
  hideOrdersTable = false,
}) {
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [customerPeek, setCustomerPeek] = useState(null);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [message, setMessage] = useState('');
  const [csvText, setCsvText] = useState('');
  const [csvFileName, setCsvFileName] = useState('');
  const [auxCsvText, setAuxCsvText] = useState('');
  const [auxCsvFileName, setAuxCsvFileName] = useState('');
  const [csvPreview, setCsvPreview] = useState(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const [apiSyncBusy, setApiSyncBusy] = useState(false);
  const [form, setForm] = useState({
    product_id: '',
    qty: 1,
    unit_price: '',
    buyer_username: '',
    external_order_ref: '',
    ordered_at: '',
    notes: 'TikTok Shop order',
  });
  const isShop = source === 'tiktok_shop';
  const compactLiveImport = !isShop && showImport && !showCreate;
  const ordersTitle = title || (isShop ? 'TikTok Shop Orders' : 'TikTok LIVE Orders');
  const createPanelTitle = createTitle || (isShop ? 'Create TikTok Shop Order' : 'Create TikTok LIVE Order');
  const importPanelTitle = importTitle || (isShop ? 'Import TikTok Shop CSV' : 'Import TikTok LIVE CSV');
  const noOrdersMessage = emptyMessage || `No ${ordersTitle} yet.`;

  async function load() {
    setLoading(true);
    try {
      const requests = [
        fetchApi(`/api/sale_orders?source=${encodeURIComponent(source)}&summary=1&limit=250`),
      ];
      if (showCreate) {
        requests.unshift(fetchApi('/api/inventory?active=all&status=all&compact=1'));
      }
      const [productData, orderData] = showCreate
        ? await Promise.all(requests)
        : [null, ...(await Promise.all(requests))];
      setProducts(productData?.rows || []);
      setOrders(orderData.rows || []);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    // TikTok Shop API sync imports paid orders and leaves cancelled/unpaid orders undeducted.
  }, [isShop]);

  useEffect(() => {
    if (!isShop) {
      setAuxCsvText(liveLotMapCsvText || '');
      setAuxCsvFileName(liveLotMapLabel || '');
      setCsvPreview(null);
    }
  }, [isShop, liveLotMapCsvText, liveLotMapLabel]);

  const selectedProduct = useMemo(
    () => products.find((product) => String(product.id) === String(form.product_id)),
    [products, form.product_id],
  );

  const filteredOrders = useMemo(() => {
    const q = (search || '').trim().toLowerCase();
    const baseRows = rowFilter ? orders.filter((order) => rowFilter(order)) : orders;
    if (!q) return baseRows;
    return baseRows.filter((order) => (
      String(extractLotNumber(order) || '').toLowerCase().includes(q)
      || String(order.order_number || '').toLowerCase().includes(q)
      || String(order.first_product_name || '').toLowerCase().includes(q)
      || String(order.external_order_ref || '').toLowerCase().includes(q)
      || String(order.whatnot_buyer_username || '').toLowerCase().includes(q)
      || String(order.notes || '').toLowerCase().includes(q)
    ));
  }, [orders, rowFilter, search]);

  const totals = useMemo(() => {
    const amount = filteredOrders.reduce((sum, order) => sum + Number(order.total_amount || 0), 0);
    const paid = filteredOrders.filter((order) => order.payment_status === 'paid').length;
    const pendingFulfillment = filteredOrders.filter((order) => order.fulfillment_status === 'pending').length;
    return {
      count: filteredOrders.length,
      amount,
      paid,
      pendingFulfillment,
    };
  }, [filteredOrders]);

  async function createOrder() {
    const createPath = source === 'tiktok_live'
      ? '/api/tiktok_live_orders/create'
      : '/api/tiktok_shop_orders/create';
    if (!form.product_id || !form.unit_price) {
      setMessage('Choose a product and sale price first.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      await postApi(createPath, {
        product_id: Number(form.product_id),
        qty: Number(form.qty || 1),
        unit_price: Number(form.unit_price || 0),
        buyer_username: form.buyer_username,
        external_order_ref: form.external_order_ref,
        ordered_at: form.ordered_at ? new Date(form.ordered_at).toISOString() : null,
        notes: form.notes,
      });
      setForm({
        product_id: '',
        qty: 1,
        unit_price: '',
        buyer_username: '',
        external_order_ref: '',
        ordered_at: '',
        notes: isShop ? 'TikTok Shop order' : 'TikTok LIVE order',
      });
      setMessage(`${ordersTitle.replace(/s$/, '')} created and inventory deducted.`);
      await load();
    } catch (err) {
      setMessage(err.message || `Unable to create ${ordersTitle.replace(/s$/, '')}.`);
    } finally {
      setSaving(false);
    }
  }

  async function previewCsvImport() {
    if (!csvText.trim()) {
      setMessage(`Paste the ${isShop ? 'TikTok Shop' : 'TikTok LIVE'} CSV first.`);
      return;
    }
    setCsvBusy(true);
    setMessage('');
    try {
      const data = await postApi(isShop ? '/api/tiktok_shop_orders/import_csv' : '/api/tiktok_live_orders/import_csv', {
        csv_text: csvText,
        lot_map_csv_text: isShop ? undefined : auxCsvText,
        commit: false,
      });
      setCsvPreview(data);
      setMessage(`Preview ready: ${data.summary.ready_rows} ready, ${data.summary.cancelled_rows || 0} cancelled, ${data.summary.duplicate_rows} duplicates, ${data.summary.unmatched_rows} unmatched.`);
    } catch (err) {
      setMessage(err.message || 'Unable to preview TikTok CSV.');
    } finally {
      setCsvBusy(false);
    }
  }

  async function importCsvOrders() {
    if (!csvText.trim()) {
      setMessage(`Paste the ${isShop ? 'TikTok Shop' : 'TikTok LIVE'} CSV first.`);
      return;
    }
    setCsvBusy(true);
    setMessage('');
    try {
      const data = await postApi(isShop ? '/api/tiktok_shop_orders/import_csv' : '/api/tiktok_live_orders/import_csv', {
        csv_text: csvText,
        lot_map_csv_text: isShop ? undefined : auxCsvText,
        commit: true,
      });
      setCsvPreview(data);
      setMessage(`Imported ${data.summary.imported_rows} ${isShop ? 'TikTok Shop' : 'TikTok LIVE'} orders. Cancelled: ${data.summary.cancelled_rows || 0}. Duplicates skipped: ${data.summary.duplicate_rows}. Unmatched: ${data.summary.unmatched_rows}.`);
      await load();
    } catch (err) {
      setMessage(err.message || 'Unable to import TikTok CSV.');
    } finally {
      setCsvBusy(false);
    }
  }

  async function syncApiOrders() {
    setApiSyncBusy(true);
    setMessage('');
    try {
      const data = await postApi('/api/v2/integrations/tiktok-shop/orders/sync', {
        page_size: 100,
        max_pages: 5,
      });
      const counts = data.status_counts || {};
      setMessage(`TikTok API sync complete: ${data.orders_seen || 0} orders seen, ${counts.imported || 0} imported, ${counts.updated_existing || 0} updated, ${counts.skipped_no_items || 0} skipped.`);
      await load();
    } catch (err) {
      setMessage(err.message || 'Unable to sync TikTok Shop API orders.');
    } finally {
      setApiSyncBusy(false);
    }
  }

  async function handleCsvFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setCsvText(text);
      setCsvFileName(file.name);
      setCsvPreview(null);
      setMessage(`${file.name} loaded. Preview it before import.`);
    } catch (err) {
      setMessage(err.message || 'Could not read CSV file.');
    } finally {
      event.target.value = '';
    }
  }

  async function handleAuxCsvFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setAuxCsvText(text);
      setAuxCsvFileName(file.name);
      setCsvPreview(null);
      setMessage(`${file.name} loaded as lot/barcode map.`);
    } catch (err) {
      setMessage(err.message || 'Could not read lot map CSV file.');
    } finally {
      event.target.value = '';
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {showCreate ? <section className="company-panel">
        <div className="company-panel-head">
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>{createPanelTitle}</div>
        </div>
        <div className="company-panel-body" style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Product</span>
              <select
                value={form.product_id}
                onChange={(e) => {
                  const nextId = e.target.value;
                  const nextProduct = products.find((product) => String(product.id) === String(nextId));
                  setForm((current) => ({
                    ...current,
                    product_id: nextId,
                    unit_price: current.unit_price || nextProduct?.retail_price || '',
                  }));
                }}
                style={inputStyle}
              >
                <option value="">Select inventory product</option>
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name} · {Number(product.on_hand_qty || 0)} left
                  </option>
                ))}
              </select>
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Qty</span>
              <input type="number" min="1" step="1" value={form.qty} onChange={(e) => setForm((current) => ({ ...current, qty: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Sale Price</span>
              <input type="number" min="0" step="0.01" value={form.unit_price} onChange={(e) => setForm((current) => ({ ...current, unit_price: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Buyer Username</span>
              <input value={form.buyer_username} onChange={(e) => setForm((current) => ({ ...current, buyer_username: e.target.value }))} style={inputStyle} placeholder="@optional" />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>TikTok Order Ref</span>
              <input value={form.external_order_ref} onChange={(e) => setForm((current) => ({ ...current, external_order_ref: e.target.value }))} style={inputStyle} placeholder="Optional external order #" />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Ordered At</span>
              <input type="datetime-local" value={form.ordered_at} onChange={(e) => setForm((current) => ({ ...current, ordered_at: e.target.value }))} style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Internal Notes</span>
              <textarea value={form.notes} onChange={(e) => setForm((current) => ({ ...current, notes: e.target.value }))} rows={3} style={{ ...inputStyle, resize: 'vertical' }} />
            </label>
          </div>

          {selectedProduct ? (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <Badge custom={sourceBadge(source)} />
              <Badge label={`${Number(selectedProduct.on_hand_qty || 0)} left`} custom={{ bg: 'rgba(245,158,11,0.16)', color: '#d97706' }} />
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {selectedProduct.name} · cost {fmt(selectedProduct.cost_price)} · retail {fmt(selectedProduct.retail_price)}
              </span>
            </div>
          ) : null}

          {message ? (
            <div style={{ fontSize: 12, color: message.toLowerCase().includes('unable') || message.toLowerCase().includes('choose') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>
              {message}
            </div>
          ) : null}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <PrimaryBtn onClick={createOrder} disabled={saving}>{saving ? 'Creating...' : `Create Confirmed ${isShop ? 'TikTok Order' : 'TikTok LIVE Order'}`}</PrimaryBtn>
            <PrimaryBtn onClick={load} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</PrimaryBtn>
          </div>
        </div>
      </section> : null}

      {showImport ? <section className={compactLiveImport ? undefined : 'company-panel'} style={compactLiveImport ? { display: 'grid', gap: 10 } : undefined}>
        {!compactLiveImport ? (
          <div className="company-panel-head">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, letterSpacing: '0.04em' }}>{importPanelTitle}</div>
          </div>
        ) : null}
        <div className={compactLiveImport ? undefined : 'company-panel-body'} style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gap: 8 }}>
            {compactLiveImport ? (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 10, alignSelf: 'flex-start', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '10px 12px', background: 'var(--bg-panel)', cursor: 'pointer', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                  <input type="file" accept=".csv,text/csv" onChange={handleCsvFile} style={{ display: 'none' }} />
                  <span>{isShop ? 'Choose Shop Sales CSV' : 'Choose TikTok Lot Details CSV'}</span>
                </label>
                <PrimaryBtn onClick={previewCsvImport} disabled={csvBusy}>{csvBusy ? 'Working...' : 'Preview CSV'}</PrimaryBtn>
                <PrimaryBtn onClick={importCsvOrders} disabled={csvBusy}>{csvBusy ? 'Working...' : 'Import Confirmed Orders'}</PrimaryBtn>
              </div>
            ) : (
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: 10, alignSelf: 'flex-start', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '10px 12px', background: 'var(--bg-panel)', cursor: 'pointer', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                <input type="file" accept=".csv,text/csv" onChange={handleCsvFile} style={{ display: 'none' }} />
                <span>{isShop ? 'Choose Shop Sales CSV' : 'Choose TikTok Lot Details CSV'}</span>
              </label>
            )}
            {!compactLiveImport ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {csvFileName ? `Loaded file: ${csvFileName}` : `No ${isShop ? 'TikTok Shop' : 'TikTok LIVE lot details'} CSV selected yet.`}
              </div>
            ) : null}
          </div>
          {!isShop ? (
            <div style={{ display: 'grid', gap: 8 }}>
              {!liveLotMapCsvText ? (
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 10, alignSelf: 'flex-start', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '10px 12px', background: 'var(--bg-panel)', cursor: 'pointer', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                  <input type="file" accept=".csv,text/csv" onChange={handleAuxCsvFile} style={{ display: 'none' }} />
                  <span>Choose Lot / Barcode CSV</span>
                </label>
              ) : null}
            </div>
          ) : null}
          {!compactLiveImport ? (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <PrimaryBtn onClick={previewCsvImport} disabled={csvBusy}>{csvBusy ? 'Working...' : 'Preview CSV'}</PrimaryBtn>
              <PrimaryBtn onClick={importCsvOrders} disabled={csvBusy}>{csvBusy ? 'Working...' : 'Import Confirmed Orders'}</PrimaryBtn>
            </div>
          ) : null}
          {csvPreview ? (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Badge label={`${csvPreview.summary.total_rows} rows`} custom={{ bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                {csvPreview.summary.unique_orders ? <Badge label={`${csvPreview.summary.unique_orders} orders`} custom={{ bg: 'rgba(59,130,246,0.12)', color: '#2563eb' }} /> : null}
                {csvPreview.summary.unique_packages ? <Badge label={`${csvPreview.summary.unique_packages} packages`} custom={{ bg: 'rgba(139,92,246,0.12)', color: '#7c3aed' }} /> : null}
                <Badge label={`${csvPreview.summary.ready_rows} ready`} custom={{ bg: 'rgba(16,185,129,0.16)', color: '#059669' }} />
                <Badge label={`${csvPreview.summary.cancelled_rows || 0} cancelled`} custom={{ bg: 'rgba(148,163,184,0.16)', color: '#475569' }} />
                <Badge label={`${csvPreview.summary.duplicate_rows} duplicates`} custom={{ bg: 'rgba(245,158,11,0.16)', color: '#d97706' }} />
                <Badge label={`${csvPreview.summary.unmatched_rows} unmatched`} custom={{ bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }} />
                {(csvPreview.summary.missing_seller_sku_rows || 0) ? <Badge label={`${csvPreview.summary.missing_seller_sku_rows} missing lot`} custom={{ bg: 'rgba(249,115,22,0.16)', color: '#ea580c' }} /> : null}
                {(csvPreview.summary.missing_barcode_rows || 0) ? <Badge label={`${csvPreview.summary.missing_barcode_rows} missing barcode`} custom={{ bg: 'rgba(236,72,153,0.16)', color: '#db2777' }} /> : null}
                {(csvPreview.summary.barcode_mismatch_rows || 0) ? <Badge label={`${csvPreview.summary.barcode_mismatch_rows} barcode mismatches`} custom={{ bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }} /> : null}
              </div>
              <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                <div style={{ maxHeight: 320, overflow: 'auto' }}>
                  <table style={{ width: '100%', minWidth: 1080, borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead style={{ position: 'sticky', top: 0, background: 'var(--bg-elevated)' }}>
                      <tr>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Status</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Order Ref</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Lot / Seller SKU</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Barcode</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Buyer</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>CSV Product</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Matched Inventory</th>
                        <th style={{ padding: '8px 10px', textAlign: 'left' }}>Matched By</th>
                        <th style={{ padding: '8px 10px', textAlign: 'right' }}>Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {csvPreview.rows.slice(0, 100).map((row) => (
                        <tr key={`${row.row_number}-${row.external_order_ref}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '8px 10px' }}>
                            <Badge
                              label={row.status}
                              custom={
                                row.status === 'ready'
                                  ? { bg: 'rgba(16,185,129,0.16)', color: '#059669' }
                                  : row.status === 'cancelled'
                                    ? { bg: 'rgba(148,163,184,0.16)', color: '#475569' }
                                  : row.status === 'duplicate'
                                    ? { bg: 'rgba(245,158,11,0.16)', color: '#d97706' }
                                    : { bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }
                              }
                            />
                          </td>
                          <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)' }}>{row.external_order_ref || '—'}</td>
                          <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)' }}>{row.seller_sku || row.lot_number || '—'}</td>
                          <td style={{ padding: '8px 10px', fontFamily: 'var(--font-mono)' }}>{row.barcode || row.lot_map_barcode || '—'}</td>
                          <td style={{ padding: '8px 10px' }}>{row.buyer_username ? `@${row.buyer_username}` : '—'}</td>
                          <td style={{ padding: '8px 10px' }}>
                            <div style={{ fontWeight: row.original_product_name ? 800 : 500 }}>{row.product_name}</div>
                            {row.original_product_name ? (
                              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 3 }}>
                                TikTok label: {row.original_product_name}
                              </div>
                            ) : null}
                          </td>
                          <td style={{ padding: '8px 10px', color: row.matched_inventory_name ? 'var(--text-primary)' : 'var(--accent-coral)' }}>{row.matched_inventory_name || 'No match'}</td>
                          <td style={{ padding: '8px 10px', color: row.warning ? 'var(--accent-coral)' : 'var(--text-secondary)' }}>{row.matched_by || row.warning || '—'}</td>
                          <td style={{ padding: '8px 10px', textAlign: 'right' }}>{fmt(row.unit_price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </section> : null}

      {!hideOrdersTable ? (
        <>
          {message ? (
            <div style={{ fontSize: 12, color: message.toLowerCase().includes('unable') || message.toLowerCase().includes('choose') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>
              {message}
            </div>
          ) : null}
          <FilterBar>
            <SearchInput value={search} onChange={setSearch} placeholder="Search lot, order #, external ref, buyer..." />
            {isShop ? (
              <PrimaryBtn onClick={syncApiOrders} disabled={apiSyncBusy}>
                {apiSyncBusy ? 'Syncing...' : 'Sync TikTok API'}
              </PrimaryBtn>
            ) : null}
            <PrimaryBtn onClick={load} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</PrimaryBtn>
          </FilterBar>

          <TableShell footer={`${filteredOrders.length} ${ordersTitle}${filteredOrders.length === 1 ? '' : ''}`}>
            <Thead cols={[
              { label: 'Ordered At' },
              { label: 'Lot #' },
              { label: 'Order #' },
              { label: 'External Ref' },
              { label: 'Buyer' },
              { label: 'Product' },
              { label: 'Source' },
              { label: 'State' },
              { label: 'Payment' },
              { label: 'Fulfillment' },
              { label: 'Amount', align: 'right' },
            ]} />
            <tbody>
              {(loading || filteredOrders.length === 0) && <EmptyRow cols={11} loading={loading} msg={noOrdersMessage} />}
              {!loading && filteredOrders.map((order) => (
                <tr key={order.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12 }}>{fmtDt(order.ordered_at || order.created_at)}</td>
                  <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                    {extractLotNumber(order) || '—'}
                  </td>
                  <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 700, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{order.order_number}</td>
                  <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{order.external_order_ref || '—'}</td>
                  <td style={{ padding: '8px 14px', whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                    <CustomerLink username={order.whatnot_buyer_username} customerId={order.customer_id} label={order.whatnot_buyer_username ? `@${order.whatnot_buyer_username}` : '—'} onOpen={setCustomerPeek} />
                    {(order.customer_phone || order.customer_email || order.customer_address) ? (
                      <div style={{ marginTop: 4, color: 'var(--text-secondary)', fontSize: 11, lineHeight: 1.35 }}>
                        {[order.customer_phone, order.customer_email].filter(Boolean).join(' · ')}
                        {order.customer_address ? (
                          <div style={{ marginTop: 2 }}>{order.customer_address}</div>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                  <td style={{ padding: '8px 14px', minWidth: 260, maxWidth: 360, whiteSpace: 'normal', overflowWrap: 'anywhere', lineHeight: 1.35 }}>{order.first_product_name || '—'}</td>
                  <td style={{ padding: '8px 14px' }}><Badge custom={sourceBadge(order.order_source)} /></td>
                  <td style={{ padding: '8px 14px' }}><Badge status={order.state} label={order.state === 'sale' ? 'Confirmed' : order.state} /></td>
                  <td style={{ padding: '8px 14px' }}><Badge label={order.payment_status || '—'} custom={{ bg: 'var(--accent-emerald)', color: '#fff' }} /></td>
                  <td style={{ padding: '8px 14px' }}><Badge label={order.fulfillment_status || 'pending'} custom={{ bg: 'rgba(245,158,11,0.16)', color: '#d97706' }} /></td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: 'var(--accent-amber)' }}>{fmt(order.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </>
      ) : null}
      {customerPeek ? (
        <CustomerProfileDrawer
          customerId={customerPeek.customerId}
          username={customerPeek.username}
          onClose={() => setCustomerPeek(null)}
        />
      ) : null}
    </div>
  );
}
