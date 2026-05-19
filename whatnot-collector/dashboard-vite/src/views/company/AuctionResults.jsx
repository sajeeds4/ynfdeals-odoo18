import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import {
  fmt, fmtPct, fmtDt, clrProfit, clrMargin,
  Badge, KpiCard, FilterBar, SearchInput, SessionSelect,
  TableShell, Thead, EmptyRow, PrimaryBtn, SlidePanel,
  formatSessionLabel,
} from './utils';
import CustomerProfileDrawer, { CustomerLink } from './CustomerProfileDrawer';
import { buildPullSummary, downloadPickListPdf } from './TikTokLivePickList';

function parseAuctionProductNames(value) {
  return String(value || '')
    .split(/\s*\/\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function summarizeAuctionProductNames(row) {
  const names = parseAuctionProductNames(row?.product_name);
  const count = Number(row?.products_sold_count || 0);
  if (!names.length) return { title: '', subtitle: '', names: [] };
  if ((count > 1 || names.length > 1) && names.length > 1) {
    return {
      title: `(${count || names.length} products) ${names[0]}`,
      subtitle: names.slice(1).join(' + '),
      names,
    };
  }
  return { title: names[0], subtitle: '', names };
}

function buildAuctionPicklistShipments(rows) {
  const shipmentsByBuyer = new Map();
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const status = String(row?.assignment_status || '').trim().toLowerCase();
    if (status === 'payment_cancelled') return;
    const winner = String(row?.winner_username || '').trim();
    const buyerKey = winner || `lot-${row?.lot_number || row?.id || Math.random()}`;
    const current = shipmentsByBuyer.get(buyerKey) || {
      sale_order_id: row?.sale_order_id || null,
      order_number: row?.sale_order_number || '',
      username: winner,
      buyer_name: winner || 'Unknown customer',
      order_count: 0,
      total_items: 0,
      total_lines: 0,
      total_price: 0,
      items: [],
    };
    const names = summarizeAuctionProductNames(row).names;
    const productNames = names.length ? names : [String(row?.product_name || '').trim() || `Lot ${row?.lot_number || ''}`.trim() || 'Unknown product'];
    const unitPrice = Number(row?.sale_price || 0) / Math.max(1, productNames.length);
    productNames.forEach((productName, index) => {
      current.items.push({
        lot_number: String(row?.lot_number || '').trim(),
        barcode: String(row?.barcode || '').trim(),
        sku: String(row?.sku || '').trim(),
        product_name: productName,
        qty: 1,
        price: unitPrice,
        sale_price: unitPrice,
        row_id: `${row?.id || row?.lot_number || buyerKey}-${index}`,
      });
      current.total_items += 1;
      current.total_lines += 1;
      current.total_price += unitPrice;
    });
    current.order_count = Math.max(current.order_count, 1);
    shipmentsByBuyer.set(buyerKey, current);
  });
  return [...shipmentsByBuyer.values()]
    .map((ship) => ({
      ...ship,
      total_price: Number(ship.total_price.toFixed(2)),
      items: ship.items.sort((left, right) => Number(left.lot_number || 0) - Number(right.lot_number || 0)),
    }))
    .sort((left, right) => String(left.username || left.buyer_name || '').localeCompare(String(right.username || right.buyer_name || '')));
}

function printAuctionReport(rows, data, sessionLabel) {
  const totalRevenue = rows.reduce((s, r) => s + (r.sale_price || 0), 0);
  const totalCost = rows.reduce((s, r) => s + (r.cost_price || 0), 0);
  const totalFees = rows.reduce((s, r) => s + (r.fees || 0), 0);
  const totalProfit = rows.reduce((s, r) => s + (r.profit || 0), 0);
  const profitableLots = rows.filter((r) => (r.profit || 0) >= 0);
  const lossLots = rows.filter((r) => (r.profit || 0) < 0);
  const avgMargin = totalRevenue ? (totalProfit / totalRevenue) * 100 : 0;
  const avgSalePrice = rows.length ? totalRevenue / rows.length : 0;
  const bestLot = rows.reduce((b, r) => (!b || (r.profit || 0) > (b.profit || 0)) ? r : b, null);
  const worstLot = rows.reduce((w, r) => (!w || (r.profit || 0) < (w.profit || 0)) ? r : w, null);
  const $ = (n) => n == null ? '—' : `$${Number(n).toFixed(2)}`;
  const pct = (n) => n == null ? '—' : `${Number(n).toFixed(1)}%`;
  const profitColor = (v) => v == null ? '#555' : v >= 0 ? '#16a34a' : '#dc2626';
  const marginColor = (v) => v == null ? '#555' : v >= 25 ? '#16a34a' : v >= 15 ? '#d97706' : '#dc2626';

  const lotRows = rows.map((r, i) => {
    const profit = r.profit ?? (r.sale_price - (r.cost_price || 0) - (r.fees || 0));
    const margin = r.margin_pct ?? (r.sale_price ? (profit / r.sale_price) * 100 : null);
    const summary = summarizeAuctionProductNames(r);
    return `
      <tr style="background:${i % 2 === 0 ? '#fff' : '#f9fafb'}">
        <td style="padding:6px 8px;font-weight:700;text-align:center;font-family:monospace">${r.lot_number || '—'}</td>
        <td style="padding:6px 8px;max-width:240px;overflow:hidden">
          <div style="font-weight:700;white-space:normal;line-height:1.35">${summary.title || '<span style="color:#999">No scan</span>'}</div>
          ${summary.subtitle ? `<div style="font-size:9px;color:#6b7280;margin-top:2px;white-space:normal;line-height:1.3">${summary.subtitle}</div>` : ''}
        </td>
        <td style="padding:6px 8px;font-weight:600">@${r.winner_username || '—'}</td>
        <td style="padding:6px 8px;text-align:right;font-weight:700;color:#d97706">${$(r.sale_price)}</td>
        <td style="padding:6px 8px;text-align:right;color:#555">${$(r.cost_price)}</td>
        <td style="padding:6px 8px;text-align:right;color:#555">${$(r.fees)}</td>
        <td style="padding:6px 8px;text-align:right;font-weight:700;color:${profitColor(profit)}">${$(profit)}</td>
        <td style="padding:6px 8px;text-align:right;color:${marginColor(margin)}">${pct(margin)}</td>
      </tr>`;
  }).join('');

  const html = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Auction Results Report — ${sessionLabel || 'Stream'}</title>
  <style>
    @page { size: A4; margin: 16mm 14mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 11px; color: #111; background: #fff; }

    .report-header { display: flex; justify-content: space-between; align-items: flex-start; padding-bottom: 12px; border-bottom: 2px solid #111; margin-bottom: 14px; }
    .company-name { font-size: 22px; font-weight: 900; letter-spacing: -0.5px; }
    .report-title { font-size: 13px; font-weight: 700; color: #555; margin-top: 3px; }
    .report-meta { text-align: right; font-size: 10px; color: #555; line-height: 1.7; }
    .report-meta strong { color: #111; font-size: 11px; }

    .kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin-bottom: 14px; }
    .kpi { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 10px; background: #f9fafb; }
    .kpi-label { font-size: 9px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; }
    .kpi-value { font-size: 16px; font-weight: 900; }
    .kpi-sub { font-size: 9px; color: #6b7280; margin-top: 2px; }

    .section-title { font-size: 9px; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: #6b7280; margin-bottom: 6px; }

    table { width: 100%; border-collapse: collapse; }
    thead th { background: #111; color: #fff; padding: 7px 8px; font-size: 9px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; white-space: nowrap; }
    thead th.r { text-align: right; }
    tbody tr:last-child td { border-bottom: 1px solid #e5e7eb; }
    tbody td { border-bottom: 1px solid #f3f4f6; font-size: 10.5px; }

    .totals-row td { padding: 7px 8px; background: #f3f4f6; font-weight: 700; border-top: 2px solid #111; font-size: 11px; }

    .highlights { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
    .highlight-box { border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 10px; }
    .highlight-box .hl-label { font-size: 9px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; }
    .highlight-box .hl-lot { font-size: 11px; font-weight: 900; }
    .highlight-box .hl-detail { font-size: 10px; color: #555; margin-top: 2px; }

    .footer { margin-top: 14px; padding-top: 10px; border-top: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: flex-end; font-size: 9px; color: #9ca3af; }
    .sig-line { border-top: 1px solid #9ca3af; width: 160px; padding-top: 4px; text-align: center; color: #555; font-size: 9px; }

    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .no-print { display: none; }
    }

    .print-btn { display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; background: #111; color: #fff; border: none; border-radius: 8px; font-size: 12px; font-weight: 700; cursor: pointer; margin-bottom: 16px; }
    .print-btn:hover { background: #333; }
  </style>
</head>
<body>

  <div class="report-header">
    <div>
      <div class="company-name">ynfdeals</div>
      <div class="report-title">Auction Results Report</div>
    </div>
    <div class="report-meta">
      <strong>${sessionLabel || 'All Sessions'}</strong><br/>
      Generated: ${new Date().toLocaleString()}<br/>
      Total lots: ${rows.length}
    </div>
  </div>

  <!-- KPI Summary -->
  <div class="section-title">Session Summary</div>
  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">Revenue</div>
      <div class="kpi-value" style="color:#d97706">${$(totalRevenue)}</div>
      <div class="kpi-sub">${rows.length} lots sold</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Total Cost</div>
      <div class="kpi-value">${$(totalCost)}</div>
      <div class="kpi-sub">COGS</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Fees</div>
      <div class="kpi-value">${$(totalFees)}</div>
      <div class="kpi-sub">Platform fees</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Net Profit</div>
      <div class="kpi-value" style="color:${profitColor(totalProfit)}">${$(totalProfit)}</div>
      <div class="kpi-sub">${profitableLots.length} profit · ${lossLots.length} loss</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Avg Margin</div>
      <div class="kpi-value" style="color:${marginColor(avgMargin)}">${pct(avgMargin)}</div>
      <div class="kpi-sub">Avg sale ${$(avgSalePrice)}</div>
    </div>
  </div>

  <!-- Lot Table -->
  <div class="section-title" style="margin-top:6px">Lot-by-Lot Breakdown</div>
  <table>
    <thead>
      <tr>
        <th style="text-align:center;width:48px">Lot #</th>
        <th>Product</th>
        <th>Winner</th>
        <th class="r">Price</th>
        <th class="r">Cost</th>
        <th class="r">Fees</th>
        <th class="r">Profit / Loss</th>
        <th class="r">Margin</th>
      </tr>
    </thead>
    <tbody>
      ${lotRows}
      <tr class="totals-row">
        <td colspan="3" style="padding:7px 8px;text-align:left">TOTALS (${rows.length} lots)</td>
        <td style="padding:7px 8px;text-align:right;color:#d97706">${$(totalRevenue)}</td>
        <td style="padding:7px 8px;text-align:right">${$(totalCost)}</td>
        <td style="padding:7px 8px;text-align:right">${$(totalFees)}</td>
        <td style="padding:7px 8px;text-align:right;color:${profitColor(totalProfit)}">${$(totalProfit)}</td>
        <td style="padding:7px 8px;text-align:right;color:${marginColor(avgMargin)}">${pct(avgMargin)}</td>
      </tr>
    </tbody>
  </table>

  <!-- Highlights -->
  ${(bestLot || worstLot) ? `
  <div class="highlights">
    ${bestLot ? `
    <div class="highlight-box">
      <div class="hl-label">Best Lot</div>
      <div class="hl-lot">Lot ${bestLot.lot_number || '—'} — ${$(bestLot.profit)} profit</div>
      <div class="hl-detail">${bestLot.product_name || 'No product'} · @${bestLot.winner_username || '—'} · ${$(bestLot.sale_price)}</div>
    </div>` : ''}
    ${worstLot && worstLot.id !== bestLot?.id ? `
    <div class="highlight-box">
      <div class="hl-label">Worst Lot</div>
      <div class="hl-lot" style="color:#dc2626">Lot ${worstLot.lot_number || '—'} — ${$(worstLot.profit)}</div>
      <div class="hl-detail">${worstLot.product_name || 'No product'} · @${worstLot.winner_username || '—'} · ${$(worstLot.sale_price)}</div>
    </div>` : ''}
  </div>` : ''}

  <div class="footer">
    <div>ynfdeals · Confidential · ${new Date().toLocaleDateString()}</div>
    <div style="display:flex;gap:40px">
      <div class="sig-line">Reviewed by</div>
      <div class="sig-line">Approved by</div>
    </div>
  </div>
  <script>window.addEventListener('load',function(){setTimeout(function(){window.print();},150);});</script>
</body>
</html>`;

  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, '_blank', 'width=900,height=700');
  if (win) win.focus();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function ChartTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 8, padding: '10px 14px', fontSize: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 6, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, display: 'flex', gap: 8, justifyContent: 'space-between' }}>
          <span>{p.name}</span>
          <span style={{ fontWeight: 700 }}>${Number(p.value).toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export default function AuctionResults({ sessions }) {
  const fileInputRef = useRef(null);
  const [session, setSession] = useState('');
  const [search, setSearch] = useState('');
  const [debSearch, setDebSearch] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [createForm, setCreateForm] = useState(null);
  const [products, setProducts] = useState([]);
  const [saveMessage, setSaveMessage] = useState('');
  const [customerPeek, setCustomerPeek] = useState(null);
  const [selectedPdf, setSelectedPdf] = useState(null);
  const [pdfActionBusy, setPdfActionBusy] = useState('');
  const [pdfMessage, setPdfMessage] = useState('');

  useEffect(() => { const t = setTimeout(() => setDebSearch(search), 350); return () => clearTimeout(t); }, [search]);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams();
    p.set('scope', 'company');
    if (session) p.set('session_id', session);
    if (debSearch) p.set('q', debSearch);
    try {
      const d = await fetchApi(`/api/auction_results?${p}`);
      setData(d);
      return d;
    } catch {
      return null;
    } finally {
      setLoading(false);
    }
  }, [session, debSearch]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const heldFinance = ['payment_review', 'payment_cancelled'].includes(detail?.assignment_status);
    if (!detail) {
      setEditing(false);
      setEditForm(null);
      setSaveMessage('');
      return;
    }
    setEditForm({
      lot_number: detail.lot_number || '',
      winner_username: detail.winner_username || '',
      product_name: detail.product_name || '',
      sale_price: heldFinance ? (detail.original_sale_price ?? detail.sale_price ?? 0) : (detail.sale_price ?? 0),
      cost_price: heldFinance ? (detail.original_cost_price ?? detail.cost_price ?? 0) : (detail.cost_price ?? 0),
      fees: heldFinance ? (detail.original_fees ?? detail.fees ?? 0) : (detail.fees ?? 0),
      barcode: detail.barcode || '',
      sku: detail.sku || '',
      products_sold_count: heldFinance ? (detail.original_products_sold_count ?? detail.products_sold_count ?? 1) : (detail.products_sold_count ?? 1),
      sold_at: detail.sold_at ? new Date(detail.sold_at).toISOString().slice(0, 16) : '',
      assignment_status: detail.assignment_status || 'confirmed',
    });
  }, [detail]);

  useEffect(() => {
    if (!creating) {
      setCreateForm(null);
      return;
    }
    setCreateForm({
      lot_number: '',
      winner_username: '',
      customer_name: '',
      product_name: '',
      sale_price: '',
      cost_price: '',
      fees: '',
      barcode: '',
      sku: '',
      products_sold_count: 1,
      sold_at: new Date().toISOString().slice(0, 16),
    });
    setSaveMessage('');
  }, [creating]);

  useEffect(() => {
    fetchApi('/api/inventory?status=all&compact=1').then((d) => setProducts(d.rows || [])).catch(() => setProducts([]));
  }, []);

  const inventoryProductByName = useMemo(() => {
    const map = new Map();
    products.forEach((product) => {
      const name = String(product?.name || '').trim().toLowerCase();
      if (name && !map.has(name)) map.set(name, product);
    });
    return map;
  }, [products]);

  function syncResultProductFields(form, productName) {
    const normalizedName = String(productName || '').trim();
    if (!normalizedName) return { ...form, product_name: '' };
    const matched = inventoryProductByName.get(normalizedName.toLowerCase());
    return {
      ...form,
      product_name: normalizedName,
      barcode: String(matched?.barcode || matched?.ean || form?.barcode || '').trim(),
      sku: String(matched?.sku || form?.sku || '').trim(),
      cost_price: matched?.cost != null && matched?.cost !== ''
        ? Number(matched.cost)
        : form?.cost_price,
    };
  }

  async function requestAnnotatedPdf(file, { openPreview = false } = {}) {
    const params = new URLSearchParams();
    if (session) params.set('session_id', session);
    params.set('filename', file.name);
    const buf = await file.arrayBuffer();
    const res = await fetch(`/api/whatnot_labels/enrich_pdf?${params}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/pdf' },
      body: buf,
    });
    if (!res.ok) {
      const message = await res.text().catch(() => '');
      throw new Error(message || 'Unable to build updated PDF.');
    }
    const blob = await res.blob();
    const contentDisposition = res.headers.get('Content-Disposition') || '';
    const filenameMatch = contentDisposition.match(/filename="([^"]+)"/i);
    const downloadName = filenameMatch?.[1] || file.name.replace(/\.pdf$/i, '-with-products.pdf');
    const blobUrl = URL.createObjectURL(blob);
    if (openPreview) {
      window.open(blobUrl, '_blank', 'noopener,noreferrer');
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      return;
    }
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = downloadName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
  }

  async function confirmPdfSync(file) {
    const params = new URLSearchParams();
    if (session) params.set('session_id', session);
    params.set('filename', file.name);
    const buf = await file.arrayBuffer();
    const res = await fetch(`/api/picklist/upload?${params}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/pdf' },
      body: buf,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data?.ok) {
      throw new Error(data?.error || `HTTP ${res.status}`);
    }
    return data;
  }

  async function handlePdfPreview() {
    if (!selectedPdf || !session) return;
    setPdfActionBusy('preview');
    setPdfMessage('');
    try {
      await requestAnnotatedPdf(selectedPdf, { openPreview: true });
      setPdfMessage('Preview opened in a new tab with matched product names.');
    } catch (err) {
      setPdfMessage(err.message || 'Unable to preview the updated PDF.');
    } finally {
      setPdfActionBusy('');
    }
  }

  async function handlePdfDownload() {
    if (!selectedPdf || !session) return;
    setPdfActionBusy('download');
    setPdfMessage('');
    try {
      await requestAnnotatedPdf(selectedPdf, { openPreview: false });
      setPdfMessage('Updated PDF downloaded with matched product names.');
    } catch (err) {
      setPdfMessage(err.message || 'Unable to download the updated PDF.');
    } finally {
      setPdfActionBusy('');
    }
  }

  async function handlePdfSync() {
    if (!selectedPdf || !session) return;
    setPdfActionBusy('sync');
    setPdfMessage('');
    try {
      const data = await confirmPdfSync(selectedPdf);
      await load();
      setPdfMessage(`Sales synced. ${data?.summary?.orders_synced || 0} orders confirmed and ${data?.summary?.orders_cancelled || 0} cancelled.`);
      setSelectedPdf(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      setPdfMessage(err.message || 'Unable to sync labels into sales.');
    } finally {
      setPdfActionBusy('');
    }
  }

  const rows = data?.rows || [];
  const whatnotPicklistShipments = useMemo(() => buildAuctionPicklistShipments(rows), [rows]);
  const whatnotPullSummary = useMemo(() => buildPullSummary(whatnotPicklistShipments), [whatnotPicklistShipments]);
  const whatnotPicklistSummary = useMemo(() => ({
    total_shipments: whatnotPicklistShipments.length,
    total_lots: whatnotPicklistShipments.reduce((sum, ship) => sum + (ship.items || []).length, 0),
    total_units: whatnotPicklistShipments.reduce((sum, ship) => sum + Number(ship.total_items || 0), 0),
    total_revenue: Number(whatnotPicklistShipments.reduce((sum, ship) => sum + Number(ship.total_price || 0), 0).toFixed(2)),
    matched: whatnotPicklistShipments.reduce((sum, ship) => sum + (ship.items || []).length, 0),
    orders_synced: whatnotPicklistShipments.length,
  }), [whatnotPicklistShipments]);

  function handleWhatnotListDownload(mode = 'grab') {
    if (!rows.length) return;
    downloadPickListPdf({
      mode,
      sessionName: sessionLabel,
      shipments: whatnotPicklistShipments,
      summary: whatnotPicklistSummary,
      pullSummary: whatnotPullSummary,
    });
  }

  const detailHeldFinance = ['payment_review', 'payment_cancelled'].includes(detail?.assignment_status);
  const detailRevenue = detailHeldFinance ? (detail?.original_sale_price ?? detail?.sale_price) : detail?.sale_price;
  const detailProfit = detailHeldFinance ? (detail?.original_profit ?? detail?.profit) : detail?.profit;
  const detailMargin = detailHeldFinance ? (detail?.original_margin_pct ?? detail?.margin_pct) : detail?.margin_pct;

  const sessionChartData = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      const key = r.session_id_name || `Session ${r.session_id}` || 'Unknown';
      if (!map[key]) map[key] = { name: key.slice(0, 20), Revenue: 0, Profit: 0 };
      map[key].Revenue += r.sale_price || 0;
      map[key].Profit += r.profit || 0;
    });
    return Object.values(map).sort((a, b) => b.Revenue - a.Revenue).slice(0, 12);
  }, [rows]);

  const sessionSummaries = useMemo(() => {
    const map = new Map();
    rows.forEach((row) => {
      const key = String(row.session_id || row.session_id_name || 'unknown');
      if (!map.has(key)) {
        map.set(key, {
          sessionId: row.session_id,
          sessionName: row.session_id_name || `Session ${row.session_id || 'Unknown'}`,
          results: 0,
          revenue: 0,
          profit: 0,
          fees: 0,
          lastSoldAt: null,
        });
      }
      const entry = map.get(key);
      entry.results += 1;
      entry.revenue += Number(row.sale_price || 0);
      entry.profit += Number(row.profit || 0);
      entry.fees += Number(row.fees || 0);
      const soldAt = row.sold_at ? new Date(row.sold_at).getTime() : 0;
      if (soldAt && (!entry.lastSoldAt || soldAt > entry.lastSoldAt)) {
        entry.lastSoldAt = soldAt;
      }
    });
    return Array.from(map.values())
      .map((entry) => ({
        ...entry,
        marginPct: entry.revenue ? (entry.profit / entry.revenue) * 100 : null,
      }))
      .sort((a, b) => (b.lastSoldAt || 0) - (a.lastSoldAt || 0));
  }, [rows]);

  const visibleSessions = useMemo(() => {
    const sourceSessions = Array.isArray(sessions) ? sessions : [];
    if (!sourceSessions.length) return [];
    const sessionIdsWithResults = new Set(
      sessionSummaries
        .map((entry) => String(entry.sessionId || '').trim())
        .filter(Boolean),
    );
    const filtered = sourceSessions.filter((item) => {
      const id = String(item?.id || '').trim();
      if (!id) return false;
      if (sessionIdsWithResults.has(id)) return true;
      const lotsSold = Number(item?.total_lots_sold || item?.lots_sold || 0);
      const revenue = Number(item?.total_revenue || 0);
      return lotsSold > 0 || revenue > 0;
    });
    return filtered.length ? filtered : sourceSessions;
  }, [sessionSummaries, sessions]);

  useEffect(() => {
    if (!session) return;
    const exists = visibleSessions.some((item) => String(item?.id) === String(session));
    if (!exists) setSession('');
  }, [session, visibleSessions]);

  const sessionLabel = useMemo(() => {
    if (!session) return 'All Sessions';
    const idx = visibleSessions.findIndex((s) => String(s.id) === String(session));
    const s = visibleSessions[idx >= 0 ? idx : 0];
    return s ? formatSessionLabel(s, idx >= 0 ? idx : 0) : `Session ${session}`;
  }, [session, visibleSessions]);
  const totalRevenue = Number(data?.total_revenue || 0);
  const totalFees = Number(data?.total_fees ?? rows.reduce((sum, row) => sum + Number(row?.fees || 0), 0));
  const totalProfit = Number(data?.total_profit || 0);
  const avgMargin = totalRevenue ? (totalProfit / totalRevenue) * 100 : null;

  const COLS = [
    { label: 'Sold At' }, { label: 'Session' }, { label: 'Lot #' },
    { label: 'Winner' }, { label: 'Product' }, { label: 'Sale Price', align: 'right' },
    { label: 'Cost', align: 'right' }, { label: 'Fees', align: 'right' },
    { label: 'Profit', align: 'right' }, { label: 'Margin', align: 'right' },
    { label: 'Sale Order' }, { label: '' },
  ];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
        <KpiCard label="Results" value={rows.length} icon="🎯" />
        <KpiCard label="Revenue" value={fmt(totalRevenue)} icon="💰" color="var(--accent-amber)" />
        <KpiCard label="Platform Fees" value={fmt(totalFees)} icon="🏦" color="var(--text-secondary)" />
        <KpiCard label="Profit"  value={fmt(totalProfit)}  icon="📈" color={clrProfit(totalProfit)} />
        <KpiCard label="Avg Margin" value={fmtPct(avgMargin)} icon="%" color={clrMargin(avgMargin)} />
      </div>

      <FilterBar>
        <SessionSelect sessions={visibleSessions} value={session} onChange={v => { setSession(v); }} />
        <SearchInput value={search} onChange={setSearch} placeholder="Search winner, product, lot #…" />
        <PrimaryBtn onClick={load}>Refresh</PrimaryBtn>
        <button
          type="button"
          onClick={() => {
            setDetail(null);
            setCreating(true);
          }}
          disabled={!session}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: !session ? 'var(--bg-elevated)' : 'rgba(16,185,129,0.12)', border: '1px solid var(--border-default)', color: !session ? 'var(--text-muted)' : '#047857', fontSize: 12, fontWeight: 700, cursor: !session ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          Add Missing Lot
        </button>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={!session || !!pdfActionBusy}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: !session ? 'var(--bg-elevated)' : 'rgba(124,58,237,0.12)', border: '1px solid var(--border-default)', color: !session ? 'var(--text-muted)' : '#6d28d9', fontSize: 12, fontWeight: 700, cursor: !session || pdfActionBusy ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          Upload Labels PDF
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0] || null;
            setSelectedPdf(file);
            setPdfMessage(file
              ? 'PDF loaded. Preview or download the updated PDF, then use Confirm Sales + Cancel Missing when you are ready.'
              : '');
          }}
        />
        {selectedPdf ? (
          <>
            <span style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selectedPdf.name}</span>
            <button
              type="button"
              onClick={handlePdfPreview}
              disabled={!session || !selectedPdf || !!pdfActionBusy}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: !session || !selectedPdf || pdfActionBusy ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: !session || !selectedPdf || pdfActionBusy ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
            >
              {pdfActionBusy === 'preview' ? 'Opening…' : 'Preview PDF'}
            </button>
            <button
              type="button"
              onClick={handlePdfDownload}
              disabled={!session || !selectedPdf || !!pdfActionBusy}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: !session || !selectedPdf || pdfActionBusy ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: !session || !selectedPdf || pdfActionBusy ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
            >
              {pdfActionBusy === 'download' ? 'Downloading…' : 'Download Updated PDF'}
            </button>
            <button
              type="button"
              onClick={handlePdfSync}
              disabled={!session || !selectedPdf || !!pdfActionBusy}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.22)', color: !session || !selectedPdf || pdfActionBusy ? 'var(--text-muted)' : '#047857', fontSize: 12, fontWeight: 700, cursor: !session || !selectedPdf || pdfActionBusy ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
            >
              {pdfActionBusy === 'sync' ? 'Syncing…' : 'Confirm Sales + Cancel Missing'}
            </button>
          </>
        ) : null}
        <button
          type="button"
          onClick={() => handleWhatnotListDownload('pick')}
          disabled={rows.length === 0}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: rows.length === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: rows.length === 0 ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          Picklist
        </button>
        <button
          type="button"
          onClick={() => handleWhatnotListDownload('grab')}
          disabled={rows.length === 0}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: rows.length === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: rows.length === 0 ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          Grablist
        </button>
        <a
          href={`/api/export/auction_results.csv${session ? `?session_id=${session}` : ''}`}
          download="auction_results.csv"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', fontSize: 12, fontWeight: 600, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          ⬇ CSV
        </a>
        <button
          onClick={() => printAuctionReport(rows, data, sessionLabel)}
          disabled={rows.length === 0}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '8px 12px', borderRadius: 'var(--radius-md)', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', color: rows.length === 0 ? 'var(--text-muted)' : 'var(--text-secondary)', fontSize: 12, fontWeight: 600, cursor: rows.length === 0 ? 'default' : 'pointer', whiteSpace: 'nowrap' }}
        >
          🖨 Print Report
        </button>
      </FilterBar>
      {pdfMessage ? (
        <div style={{ marginTop: -6, fontSize: 12, color: pdfMessage.toLowerCase().includes('unable') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>
          {pdfMessage}
        </div>
      ) : null}

      {/* Revenue by Session chart */}
      {sessionChartData.length > 1 && (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '18px 20px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 14 }}>
            📊 Revenue &amp; Profit by Session
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={sessionChartData} margin={{ top: 4, right: 8, left: 0, bottom: 55 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
              <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} angle={-35} textAnchor="end" interval={0} />
              <YAxis tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} width={58} tickFormatter={(v) => `$${v}`} />
              <Tooltip content={<ChartTip />} />
              <Bar dataKey="Revenue" fill="#fbbf24" radius={[3, 3, 0, 0]} />
              <Bar dataKey="Profit" fill="#34d399" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!session && sessionSummaries.length > 0 ? (
        <section style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '18px 20px', display: 'grid', gap: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Session Summary</div>
              <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>Auction results are minimized by session here. Open one session to see lot-by-lot detail.</div>
            </div>
          </div>
          <TableShell footer={`${sessionSummaries.length} session${sessionSummaries.length !== 1 ? 's' : ''}`}>
            <Thead cols={[
              { label: 'Session' },
              { label: 'Results', align: 'right' },
              { label: 'Revenue', align: 'right' },
              { label: 'Fees', align: 'right' },
              { label: 'Profit', align: 'right' },
              { label: 'Margin', align: 'right' },
              { label: 'Last Sold' },
              { label: '' },
            ]} />
            <tbody>
              {sessionSummaries.map((item) => (
                <tr
                  key={item.sessionId || item.sessionName}
                  style={{ borderTop: '1px solid var(--border-subtle)', cursor: item.sessionId ? 'pointer' : 'default' }}
                  onClick={() => {
                    if (item.sessionId) setSession(String(item.sessionId));
                  }}
                >
                  <td style={{ padding: '8px 14px', fontWeight: 700 }}>{item.sessionName}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700 }}>{item.results}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: 'var(--accent-amber)' }}>{fmt(item.revenue)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(item.fees)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 700, color: clrProfit(item.profit) }}>{fmt(item.profit)}</td>
                  <td style={{ padding: '8px 14px', textAlign: 'right', color: clrMargin(item.marginPct) }}>{fmtPct(item.marginPct)}</td>
                  <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12 }}>{item.lastSoldAt ? fmtDt(item.lastSoldAt) : '—'}</td>
                  <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 11 }}>{item.sessionId ? 'Open Session →' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        </section>
      ) : null}

      <TableShell footer={session ? `${rows.length} result${rows.length !== 1 ? 's' : ''} in ${sessionLabel}` : `${rows.length} total result${rows.length !== 1 ? 's' : ''} across all sessions`}>
        <Thead cols={COLS} />
        <tbody>
          {(loading || rows.length === 0) && <EmptyRow cols={COLS.length} loading={loading} />}
          {!loading && !session && rows.length > 0 ? (
            <tr>
              <td colSpan={COLS.length} style={{ padding: '18px 14px', color: 'var(--text-secondary)', fontSize: 13, textAlign: 'center' }}>
                Pick a session above or use the Session Summary section to open one specific live and see lot-level auction results.
              </td>
            </tr>
          ) : null}
          {!loading && !!session && rows.map(r => (
            <tr key={r.id} style={{ borderTop: '1px solid var(--border-subtle)', cursor: 'pointer' }} onClick={() => setDetail(r)}>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>{fmtDt(r.sold_at)}</td>
              <td style={{ padding: '8px 14px', fontSize: 12, color: 'var(--text-secondary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.session_id_name || '—'}</td>
              <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{r.lot_number || '—'}</td>
              <td style={{ padding: '8px 14px', fontWeight: 600 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}>
                  <CustomerLink username={r.winner_username} customerId={r.customer_id} label={r.winner_username ? `@${r.winner_username}` : '—'} onOpen={setCustomerPeek} />
                  {r.assignment_status === 'payment_review' ? (
                    <Badge custom={{ label: 'Payment Review', bg: 'rgba(245,158,11,0.12)', color: 'var(--accent-amber)' }} />
                  ) : null}
                  {r.assignment_status === 'payment_cancelled' ? (
                    <Badge custom={{ label: 'Cancelled Payment', bg: 'rgba(239,68,68,0.12)', color: 'var(--accent-coral)' }} />
                  ) : null}
                </div>
              </td>
              <td style={{ padding: '8px 14px', maxWidth: 280, color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : undefined }}>
                {(() => {
                  const summary = summarizeAuctionProductNames(r);
                  return summary.title ? (
                    <div style={{ display: 'grid', gap: 3 }}>
                      <div style={{ fontWeight: 600, lineHeight: 1.35 }}>{summary.title}</div>
                      {summary.subtitle ? (
                        <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.3 }}>{summary.subtitle}</div>
                      ) : null}
                    </div>
                  ) : <span style={{ color: 'var(--text-muted)' }}>(no scan)</span>;
                })()}
              </td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : 'var(--accent-amber)' }}>{fmt(r.sale_price)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : 'var(--text-secondary)' }}>{fmt(r.cost_price)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : 'var(--text-secondary)' }}>{fmt(r.fees)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', fontWeight: 600, color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : clrProfit(r.profit) }}>{fmt(r.profit)}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right', color: ['payment_review','payment_cancelled'].includes(r.assignment_status) ? 'var(--text-muted)' : clrMargin(r.margin_pct) }}>{fmtPct(r.margin_pct)}</td>
              <td style={{ padding: '8px 14px' }}>
                {r.assignment_status === 'payment_review'
                  ? <Badge custom={{ label: 'Review', bg: 'rgba(245,158,11,0.12)', color: 'var(--accent-amber)' }} />
                  : r.assignment_status === 'payment_cancelled'
                  ? <Badge custom={{ label: 'Cancelled', bg: 'rgba(239,68,68,0.12)', color: 'var(--accent-coral)' }} />
                  : r.sale_order_id
                  ? <Badge custom={{ label: r.sale_order_id_name || 'SO', bg: 'var(--accent-emerald)', color: '#fff' }} />
                  : <Badge custom={{ label: 'No SO', bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />}
              </td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', fontSize: 11 }}>View / Edit →</td>
            </tr>
          ))}
        </tbody>
      </TableShell>

      {detail && (
        <SlidePanel title="Auction Result" sub={`${summarizeAuctionProductNames(detail).title || 'No product'} · @${detail.winner_username}`} onClose={() => setDetail(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* Finance row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 10 }}>
              <KpiCard label={detailHeldFinance ? 'Held Sale Price' : 'Sale Price'} value={fmt(detailRevenue)} color="var(--accent-amber)" />
              <KpiCard label={detailHeldFinance ? 'Held Profit' : 'Profit'} value={fmt(detailProfit)} color={clrProfit(detailProfit)} />
              <KpiCard label={detailHeldFinance ? 'Held Margin' : 'Margin'} value={fmtPct(detailMargin)} color={clrMargin(detailMargin)} />
            </div>
            {detail.assignment_status === 'payment_review' ? (
              <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-md)', background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.25)', color: 'var(--accent-amber)', fontSize: 13, fontWeight: 700 }}>
                This lot is in payment review and is excluded from revenue, profit, fees, and product sold totals.
              </div>
            ) : null}
            {detail.assignment_status === 'payment_cancelled' ? (
              <div style={{ padding: '10px 12px', borderRadius: 'var(--radius-md)', background: 'rgba(239,68,68,0.10)', border: '1px solid rgba(239,68,68,0.24)', color: 'var(--accent-coral)', fontSize: 13, fontWeight: 700 }}>
                This lot was marked as cancelled payment and is excluded from revenue, profit, fees, and product sold totals.
              </div>
            ) : null}
            {[
              ['Session', detail.session_id_name],
              ['Sold At', fmtDt(detail.sold_at)],
              ['Lot #', detail.lot_number],
              ['Winner', detail.winner_username ? <CustomerLink username={detail.winner_username} customerId={detail.customer_id} label={`@${detail.winner_username}`} onOpen={setCustomerPeek} /> : '—'],
              ['Product', (
                <div style={{ display: 'grid', justifyItems: 'end', gap: 4, textAlign: 'right' }}>
                  <span>{summarizeAuctionProductNames(detail).title || '—'}</span>
                  {summarizeAuctionProductNames(detail).subtitle ? (
                    <span style={{ color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.3 }}>
                      {summarizeAuctionProductNames(detail).subtitle}
                    </span>
                  ) : null}
                </div>
              )],
              ['SKU', detail.sku],
              ['Barcode', detail.barcode],
              ['Cost', fmt(detail.cost_price)],
              ['Fees', fmt(detail.fees)],
              ['Products in Lot', detail.products_sold_count],
              ['Buyer Group', detail.buyer_group_id_name],
              ['Sale Order', detail.sale_order_id_name],
              ['Source Event', detail.source_event_id],
            ].map(([k, v]) => v && (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: 13 }}>
                <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                <span style={{ fontWeight: 500 }}>{v}</span>
              </div>
            ))}

            <div style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: 14, display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
                <div style={{ fontWeight: 700 }}>Swap / Fix Result</div>
                <PrimaryBtn onClick={() => setEditing((v) => !v)}>{editing ? 'Close Editor' : 'Edit Result'}</PrimaryBtn>
              </div>
              {editing && editForm ? (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Lot #</span>
                      <input value={editForm.lot_number} onChange={(e) => setEditForm((v) => ({ ...v, lot_number: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Winner</span>
                      <input value={editForm.winner_username} onChange={(e) => setEditForm((v) => ({ ...v, winner_username: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Product</span>
                      <input list={`auction-products-${detail.id}`} value={editForm.product_name} onChange={(e) => setEditForm((v) => syncResultProductFields(v, e.target.value))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                      <datalist id={`auction-products-${detail.id}`}>
                        {products.map((p) => <option key={p.id} value={p.name} />)}
                      </datalist>
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Sale Price</span>
                      <input type="number" step="0.01" value={editForm.sale_price} onChange={(e) => setEditForm((v) => ({ ...v, sale_price: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Cost</span>
                      <input type="number" step="0.01" value={editForm.cost_price} onChange={(e) => setEditForm((v) => ({ ...v, cost_price: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Fees</span>
                      <input type="number" step="0.01" value={editForm.fees} onChange={(e) => setEditForm((v) => ({ ...v, fees: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Products in Lot</span>
                      <input type="number" step="1" min="0" value={editForm.products_sold_count} onChange={(e) => setEditForm((v) => ({ ...v, products_sold_count: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Barcode</span>
                      <input value={editForm.barcode} onChange={(e) => setEditForm((v) => ({ ...v, barcode: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>SKU</span>
                      <input value={editForm.sku} onChange={(e) => setEditForm((v) => ({ ...v, sku: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                    <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Sold At</span>
                      <input type="datetime-local" value={editForm.sold_at} onChange={(e) => setEditForm((v) => ({ ...v, sold_at: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                    </label>
                  </div>
                  {detailHeldFinance ? (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      Held lots still keep their original financial truth. Saving here uses the original sale price, cost, and fees instead of the zeroed reporting values.
                    </div>
                  ) : null}
                  {saveMessage ? <div style={{ fontSize: 12, color: saveMessage.includes('Unable') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{saveMessage}</div> : null}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <PrimaryBtn
                      onClick={async () => {
                        try {
                          const res = await postApi('/api/auction_results/update', {
                            result_id: detail.id,
                            lot_number: editForm.lot_number,
                            winner_username: editForm.winner_username,
                            product_name: editForm.product_name,
                            sale_price: Number(editForm.sale_price || 0),
                            cost_price: Number(editForm.cost_price || 0),
                            fees: Number(editForm.fees || 0),
                            products_sold_count: Number(editForm.products_sold_count || 0),
                            barcode: editForm.barcode,
                            sku: editForm.sku,
                            sold_at: editForm.sold_at ? new Date(editForm.sold_at).toISOString() : null,
                          });
                          const updated = res?.result;
                          setSaveMessage('Auction result updated.');
                          if (updated) {
                            setDetail(updated);
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(updated.id));
                            if (refreshed) setDetail(refreshed);
                          }
                        } catch (err) {
                          setSaveMessage(err.message || 'Unable to update auction result.');
                        }
                      }}
                    >
                      Save Result
                    </PrimaryBtn>
                    {detail.assignment_id ? (
                      <button
                        className="btn"
                        onClick={async () => {
                          try {
                            const res = await postApi('/api/winner_assignment/status', { assignment_id: detail.assignment_id, status: 'confirmed' });
                            setSaveMessage('Sale restored to confirmed flow.');
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(detail.id));
                            if (refreshed) setDetail(refreshed);
                            else if (res?.assignment) setDetail((prev) => prev ? { ...prev, assignment_status: res.assignment.status } : prev);
                          } catch (err) {
                            setSaveMessage(err.message || 'Unable to restore sale.');
                          }
                        }}
                        style={{ color: 'var(--accent-emerald)', borderColor: 'rgba(16,185,129,0.35)' }}
                      >
                        Restore Confirmed Sale
                      </button>
                    ) : null}
                    {detail.assignment_id ? (
                      <button
                        className="btn"
                        onClick={async () => {
                          try {
                            const res = await postApi('/api/winner_assignment/status', { assignment_id: detail.assignment_id, status: 'assigned' });
                            setSaveMessage('Lot reopened for scanner edits.');
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(detail.id));
                            if (refreshed) setDetail(refreshed);
                            else if (res?.assignment) setDetail((prev) => prev ? { ...prev, assignment_status: res.assignment.status } : prev);
                          } catch (err) {
                            setSaveMessage(err.message || 'Unable to reopen lot.');
                          }
                        }}
                      >
                        Reopen For Re-Scan
                      </button>
                    ) : null}
                    {detail.assignment_id ? (
                      <button
                        className="btn"
                        onClick={async () => {
                          try {
                            const res = await postApi('/api/winner_assignment/status', { assignment_id: detail.assignment_id, status: 'needs_review' });
                            setSaveMessage('Lot moved to needs review.');
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(detail.id));
                            if (refreshed) setDetail(refreshed);
                            else if (res?.assignment) setDetail((prev) => prev ? { ...prev, assignment_status: res.assignment.status } : prev);
                          } catch (err) {
                            setSaveMessage(err.message || 'Unable to move lot to review.');
                          }
                        }}
                      >
                        Needs Review
                      </button>
                    ) : null}
                    {detail.assignment_id ? (
                      <button
                        className="btn"
                        onClick={async () => {
                          try {
                            const res = await postApi('/api/winner_assignment/status', { assignment_id: detail.assignment_id, status: 'payment_review' });
                            setSaveMessage('Marked for payment review.');
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(detail.id));
                            if (refreshed) setDetail(refreshed);
                          } catch (err) {
                            setSaveMessage(err.message || 'Unable to mark payment review.');
                          }
                        }}
                        style={{ color: 'var(--accent-amber)', borderColor: 'rgba(245,158,11,0.35)' }}
                      >
                        Mark Payment Review
                      </button>
                    ) : null}
                    {detail.assignment_id ? (
                      <button
                        className="btn"
                        onClick={async () => {
                          try {
                            const res = await postApi('/api/winner_assignment/status', { assignment_id: detail.assignment_id, status: 'payment_cancelled' });
                            setSaveMessage('Marked as cancelled payment.');
                            const next = await load();
                            const refreshed = next?.rows?.find((row) => String(row.id) === String(detail.id));
                            if (refreshed) setDetail(refreshed);
                          } catch (err) {
                            setSaveMessage(err.message || 'Unable to cancel payment.');
                          }
                        }}
                        style={{ color: 'var(--accent-coral)', borderColor: 'rgba(239,68,68,0.35)' }}
                      >
                        Cancel Payment
                      </button>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>
          </div>
        </SlidePanel>
      )}
      {creating && createForm ? (
        <SlidePanel title="Add Missing Lot" sub={sessionLabel} onClose={() => setCreating(false)}>
          <div style={{ display: 'grid', gap: 14 }}>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Use this to add a missed final lot or record a manual customer/product swap after the live ended.
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Lot #</span>
                <input value={createForm.lot_number} onChange={(e) => setCreateForm((v) => ({ ...v, lot_number: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Customer Username</span>
                <input value={createForm.winner_username} onChange={(e) => setCreateForm((v) => ({ ...v, winner_username: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Customer Name</span>
                <input value={createForm.customer_name} onChange={(e) => setCreateForm((v) => ({ ...v, customer_name: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Product</span>
                <input list="auction-create-products" value={createForm.product_name} onChange={(e) => setCreateForm((v) => syncResultProductFields(v, e.target.value))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
                <datalist id="auction-create-products">
                  {products.map((p) => <option key={`create-${p.id}`} value={p.name} />)}
                </datalist>
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Sale Price</span>
                <input type="number" step="0.01" value={createForm.sale_price} onChange={(e) => setCreateForm((v) => ({ ...v, sale_price: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Cost</span>
                <input type="number" step="0.01" value={createForm.cost_price} onChange={(e) => setCreateForm((v) => ({ ...v, cost_price: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Fees</span>
                <input type="number" step="0.01" value={createForm.fees} onChange={(e) => setCreateForm((v) => ({ ...v, fees: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Products in Lot</span>
                <input type="number" step="1" min="1" value={createForm.products_sold_count} onChange={(e) => setCreateForm((v) => ({ ...v, products_sold_count: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Barcode</span>
                <input value={createForm.barcode} onChange={(e) => setCreateForm((v) => ({ ...v, barcode: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6 }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>SKU</span>
                <input value={createForm.sku} onChange={(e) => setCreateForm((v) => ({ ...v, sku: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
              <label style={{ display: 'grid', gap: 6, gridColumn: '1 / -1' }}>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Sold At</span>
                <input type="datetime-local" value={createForm.sold_at} onChange={(e) => setCreateForm((v) => ({ ...v, sold_at: e.target.value }))} style={{ background: 'var(--bg-panel)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '8px 10px', fontSize: 13 }} />
              </label>
            </div>
            {saveMessage ? <div style={{ fontSize: 12, color: saveMessage.includes('Unable') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{saveMessage}</div> : null}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <PrimaryBtn
                onClick={async () => {
                  try {
                    const res = await postApi('/api/auction_results/create', {
                      session_id: Number(session),
                      lot_number: createForm.lot_number,
                      winner_username: createForm.winner_username,
                      customer_name: createForm.customer_name,
                      product_name: createForm.product_name,
                      sale_price: Number(createForm.sale_price || 0),
                      cost_price: Number(createForm.cost_price || 0),
                      fees: Number(createForm.fees || 0),
                      products_sold_count: Number(createForm.products_sold_count || 1),
                      barcode: createForm.barcode,
                      sku: createForm.sku,
                      sold_at: createForm.sold_at ? new Date(createForm.sold_at).toISOString() : null,
                    });
                    setSaveMessage('Missing lot added.');
                    const next = await load();
                    const created = next?.rows?.find((row) => String(row.id) === String(res?.result?.id));
                    setCreating(false);
                    if (created) setDetail(created);
                  } catch (err) {
                    setSaveMessage(err.message || 'Unable to create auction result.');
                  }
                }}
              >
                Save Missing Lot
              </PrimaryBtn>
            </div>
          </div>
        </SlidePanel>
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
