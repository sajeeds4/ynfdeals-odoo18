import { useEffect, useMemo, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  FilterBar, SessionSelect, PrimaryBtn,
  SearchInput, TableShell, Thead, EmptyRow, formatSessionLabel,
} from './utils';

function fmt$(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

function esc(v) {
  return String(v ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function parseProductLabel(label) {
  const raw = String(label || '').trim();
  const qtyMatch = raw.match(/\s+x(\d+)\s*$/i);
  const qty = qtyMatch ? Number(qtyMatch[1] || 1) : 1;
  let name = qtyMatch ? raw.slice(0, qtyMatch.index).trim() : raw;
  name = name.replace(/^\[[^\]]+\]\s*/, '').trim();
  return { name, qty: Number.isFinite(qty) && qty > 0 ? qty : 1 };
}

export function buildPullSummary(shipments) {
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
      current.qty += parsed.qty;
      if (item.lot_number != null && item.lot_number !== '') current.lots.push(String(item.lot_number));
      map.set(key, current);
    }
  }
  return [...map.values()]
    .map((row) => ({
      ...row,
      lots_label: row.lots
        .sort((a, b) => Number(a) - Number(b))
        .map((lot) => `#${lot}`)
        .join(', '),
    }))
    .sort((a, b) => b.qty - a.qty || a.product_name.localeCompare(b.product_name));
}

export function buildPrintHtml({ mode, sessionName, shipments, summary, pullSummary }) {
  const nowLabel = new Date().toLocaleString();
  const orderedShipments = [...(shipments || [])].sort((left, right) => {
    const leftItems = Number(left?.total_items || 0);
    const rightItems = Number(right?.total_items || 0);
    if (rightItems !== leftItems) return rightItems - leftItems;
    const leftLines = Number(left?.total_lines || 0);
    const rightLines = Number(right?.total_lines || 0);
    if (rightLines !== leftLines) return rightLines - leftLines;
    return String(left?.buyer_name || left?.username || '').localeCompare(String(right?.buyer_name || right?.username || ''));
  });
  const pickBlocks = orderedShipments.map((ship, shipmentIndex) => `
    <section class="pick-group">
      <div class="pick-group-head">
        <div>
          <div class="pick-buyer">${esc(ship.buyer_name || ship.username || 'Unknown customer')} ${ship.username ? `(@${esc(ship.username)})` : ''} — ${Number(ship.total_items || 0)} order${Number(ship.total_items || 0) === 1 ? '' : 's'}</div>
        </div>
        <div class="pick-chip">${shipmentIndex + 1}</div>
      </div>
      <table>
        <thead><tr><th>Lot</th><th>Barcode</th><th>Product</th></tr></thead>
        <tbody>
          ${(ship.items || []).map((item) => `
            <tr>
              <td>${esc(item.lot_number || '—')}</td>
              <td>${esc(item.barcode || '—')}</td>
              <td class="product-name">${esc(item.product_name || 'Unknown product')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </section>
  `).join('');

  const grabRows = (pullSummary || []).map((row) => `
    <tr>
      <td style="font-weight:800">${esc(row.qty)}</td>
      <td class="product-name">${esc(row.product_name)}</td>
      <td class="lots-cell">${esc(row.lots_label)}</td>
    </tr>
  `).join('');

  const header = (title, sub) => `
    <div class="head">
      <div>
        <div class="brand">ynfdeals · TikTok LIVE</div>
        <h1>${esc(title)}</h1>
        <div class="sub">${esc(sub)}</div>
      </div>
      <div class="meta">
        <div>${esc(sessionName || 'TikTok LIVE Session')}</div>
        <div>${esc(nowLabel)}</div>
      </div>
    </div>
  `;

  const pickSection = `
    <section class="sheet">
      ${header('PICK LIST (PRINT OPTIMIZED)', `${summary.total_shipments || 0} customers · ${summary.total_lots || 0} lots`)}
      ${pickBlocks}
    </section>`;

  const grabSection = `
    <section class="sheet">
      ${header('GRAB LIST', `${pullSummary.length || 0} grouped products · ${summary.total_units || 0} total units`)}
      <table>
        <thead><tr><th>Qty</th><th>Product</th><th>Lots</th></tr></thead>
        <tbody>${grabRows}</tbody>
      </table>
    </section>`;

  const body = mode === 'pick' ? pickSection : mode === 'grab' ? grabSection : `${grabSection}<div class="break"></div>${pickSection}`;
  return `<!doctype html>
  <html><head><meta charset="utf-8"/><title>TikTok Pick List</title>
  <style>
    @page { size: A4 portrait; margin: 10mm; }
    * { box-sizing: border-box; }
    html, body {
      width: 210mm;
      min-width: 210mm;
    }
    body {
      font-family: Arial, Helvetica, sans-serif;
      color: #0f172a;
      margin: 0;
      font-size: 8.5pt;
      background: #fff;
    }
    .sheet {
      width: 190mm;
      max-width: 190mm;
      margin: 0 auto;
      background: #ffffff;
      padding: 0;
    }
    .break { break-before: page; page-break-before: always; }
    .head {
      display:flex;
      justify-content:space-between;
      gap:20px;
      align-items:flex-start;
      margin-bottom:8px;
      padding-bottom:6px;
      border-bottom: 1px solid #111827;
    }
    .brand {
      font-size: 8pt;
      font-weight: 800;
      color: #111827;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    h1 {
      margin: 0;
      font-size: 17pt;
      line-height: 1;
      letter-spacing: -0.04em;
      color: #0f172a;
    }
    .sub {
      color:#4b5563;
      font-size:9pt;
      margin-top: 6px;
    }
    .meta {
      color:#374151;
      font-size:8.5pt;
      text-align: right;
      display: grid;
      gap: 4px;
      padding: 0;
      background: #fff;
      min-width: 220px;
    }
    .pick-group {
      margin-bottom: 9px;
      border: 1px solid #d1d5db;
      background: #fff;
      page-break-inside: avoid;
    }
    .pick-group-head {
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:flex-start;
      padding:6px 8px;
      background: #fff;
      border-bottom:1px solid #d1d5db;
    }
    .pick-buyer {
      font-size: 11pt;
      font-weight: 800;
      line-height: 1.2;
      color: #0f172a;
    }
    .pick-meta {
      color:#6b7280;
      font-size:8pt;
      margin-top:4px;
    }
    .pick-chip {
      min-width: 28px;
      height: 28px;
      border-radius: 999px;
      display:flex;
      align-items:center;
      justify-content:center;
      font-size:8pt;
      font-weight:800;
      color:#0f172a;
      border: 1px solid #d1d5db;
    }
    .grab-summary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .grab-stat {
      border: 1px solid #d1d5db;
      border-radius: 12px;
      padding: 10px 12px;
      background: #fff;
    }
    .grab-stat-label {
      font-size: 7.5pt;
      text-transform: uppercase;
      letter-spacing: .08em;
      color: #6b7280;
      font-weight: 800;
      margin-bottom: 4px;
    }
    .grab-stat-value {
      font-size: 15pt;
      line-height: 1;
      letter-spacing: -0.03em;
      font-weight: 800;
      color: #0f172a;
    }
    table { width:100%; border-collapse: collapse; table-layout: fixed; }
    thead th {
      background:#fff;
      color:#111827;
      font-size:7pt;
      text-transform:uppercase;
      letter-spacing:.08em;
      padding:5px 7px;
      text-align:left;
      font-weight: 800;
      border-bottom: 1px solid #d1d5db;
    }
    td {
      border-bottom:1px solid #e5e7eb;
      padding:5px 7px;
      vertical-align:top;
      word-break:break-word;
      color: #0f172a;
    }
    th:nth-child(1), td:nth-child(1) { width: 55px; }
    th:nth-child(2), td:nth-child(2) { width: 120px; }
    .muted { color:#6b7280; font-size:8pt; }
    .box {
      display:inline-block;
      width:13px;
      height:13px;
      border:1.5px solid #111827;
      border-radius:3px;
      background: #fff;
    }
    .lots-cell {
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 8.2pt;
      color: #334155;
      line-height: 1.45;
    }
    .product-name {
      font-weight: 700;
      color: #0f172a;
    }
    @media print {
      body { background: #fff; }
      .sheet {
        border-radius: 0;
        border: none;
        box-shadow: none;
        width: 190mm;
        max-width: 190mm;
        padding: 0;
      }
      .pick-group { page-break-inside: avoid; }
      table, tr, td, th { page-break-inside: avoid; }
    }
  </style></head><body>${body}</body></html>`;
}

function pdfSafeText(value) {
  return String(value ?? '')
    .normalize('NFKD')
    .replace(/[^\x20-\x7E]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function pdfEscape(value) {
  return pdfSafeText(value).replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
}

function wrapPdfText(value, maxWidth, fontSize) {
  const text = pdfSafeText(value);
  if (!text) return [''];
  const avg = fontSize * 0.48;
  const maxChars = Math.max(8, Math.floor(maxWidth / avg));
  const words = text.split(/\s+/);
  const lines = [];
  let current = '';
  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars) {
      current = next;
      return;
    }
    if (current) lines.push(current);
    if (word.length <= maxChars) {
      current = word;
      return;
    }
    for (let index = 0; index < word.length; index += maxChars) {
      const chunk = word.slice(index, index + maxChars);
      if (chunk.length === maxChars) lines.push(chunk);
      else current = chunk;
    }
  });
  if (current) lines.push(current);
  return lines.length ? lines : [''];
}

function currencyPdf(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function createPdfWriter() {
  const width = 595.28;
  const height = 841.89;
  const margin = 34;
  const pages = [];
  let current = null;

  function page() {
    current = { ops: [] };
    pages.push(current);
    return current;
  }

  function ensurePage() {
    if (!current) page();
    return current;
  }

  function op(line) {
    ensurePage().ops.push(line);
  }

  function text(x, y, value, size = 9, font = 'F1') {
    op(`BT /${font} ${size} Tf 1 0 0 1 ${x.toFixed(2)} ${y.toFixed(2)} Tm (${pdfEscape(value)}) Tj ET`);
  }

  function line(x1, y1, x2, y2, color = '0.80 0.84 0.90', lineWidth = 0.6) {
    op(`${color} RG ${lineWidth} w ${x1.toFixed(2)} ${y1.toFixed(2)} m ${x2.toFixed(2)} ${y2.toFixed(2)} l S 0 0 0 RG`);
  }

  function rect(x, y, w, h, color = '0.96 0.97 0.98') {
    op(`${color} rg ${x.toFixed(2)} ${y.toFixed(2)} ${w.toFixed(2)} ${h.toFixed(2)} re f 0 0 0 rg`);
  }

  function checkbox(x, y) {
    op(`0.25 0.29 0.35 RG 0.8 w ${x.toFixed(2)} ${y.toFixed(2)} 9 9 re S 0 0 0 RG`);
  }

  function finish() {
    const objects = [];
    const add = (body) => {
      objects.push(body);
      return objects.length;
    };
    const fontRegular = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
    const fontBold = add('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>');
    const pageRefs = [];
    pages.forEach((pdfPage, index) => {
      pdfPage.ops.push(`0.42 0.45 0.50 rg BT /F1 8 Tf 1 0 0 1 ${(width / 2 - 30).toFixed(2)} 18 Tm (Page ${index + 1} of ${pages.length}) Tj ET 0 0 0 rg`);
      const stream = pdfPage.ops.join('\n');
      const contentRef = add(`<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
      pageRefs.push(add(`<< /Type /Page /Parent __PAGES__  /MediaBox [0 0 ${width.toFixed(2)} ${height.toFixed(2)}] /Resources << /Font << /F1 ${fontRegular} 0 R /F2 ${fontBold} 0 R >> >> /Contents ${contentRef} 0 R >>`));
    });
    const pagesRef = objects.length + 1;
    objects.push(`<< /Type /Pages /Kids [${pageRefs.map((ref) => `${ref} 0 R`).join(' ')}] /Count ${pageRefs.length} >>`);
    const catalogRef = add(`<< /Type /Catalog /Pages ${pagesRef} 0 R >>`);
    const resolved = objects.map((body) => body.replace(/__PAGES__/g, `${pagesRef} 0 R`));
    let pdf = '%PDF-1.4\n';
    const offsets = [0];
    resolved.forEach((body, index) => {
      offsets.push(pdf.length);
      pdf += `${index + 1} 0 obj\n${body}\nendobj\n`;
    });
    const xref = pdf.length;
    pdf += `xref\n0 ${resolved.length + 1}\n0000000000 65535 f \n`;
    offsets.slice(1).forEach((offset) => {
      pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
    });
    pdf += `trailer\n<< /Size ${resolved.length + 1} /Root ${catalogRef} 0 R >>\nstartxref\n${xref}\n%%EOF`;
    return new Blob([pdf], { type: 'application/pdf' });
  }

  return { width, height, margin, pages, page, text, line, rect, checkbox, finish };
}

export function buildPickListPdfBlob({ mode = 'both', sessionName = '', shipments = [], summary = {}, pullSummary = [] }) {
  const pdf = createPdfWriter();
  const contentWidth = pdf.width - (pdf.margin * 2);
  const nowLabel = new Date().toLocaleString();
  let y = 0;

  const orderedShipments = [...(shipments || [])].sort((left, right) => {
    const leftItems = Number(left?.total_items || 0);
    const rightItems = Number(right?.total_items || 0);
    if (rightItems !== leftItems) return rightItems - leftItems;
    return String(left?.buyer_name || left?.username || '').localeCompare(String(right?.buyer_name || right?.username || ''));
  });

  function beginPage(title, subtitle) {
    pdf.page();
    y = pdf.height - pdf.margin;
    pdf.text(pdf.margin, y, 'YNFDEALS · TIKTOK LIVE', 8, 'F2');
    pdf.text(pdf.margin, y - 20, title, 21, 'F2');
    pdf.text(pdf.margin, y - 35, subtitle, 9, 'F1');
    pdf.text(pdf.width - pdf.margin - 210, y - 2, sessionName || 'TikTok LIVE Session', 9, 'F1');
    pdf.text(pdf.width - pdf.margin - 210, y - 16, nowLabel, 8, 'F1');
    pdf.line(pdf.margin, y - 47, pdf.width - pdf.margin, y - 47, '0.15 0.18 0.25', 1);
    y -= 65;
  }

  function ensureSpace(height, title, subtitle) {
    if (y - height < pdf.margin + 24) beginPage(title, subtitle);
  }

  function drawTableHeader(columns) {
    pdf.rect(pdf.margin, y - 16, contentWidth, 16, '0.94 0.96 0.98');
    columns.forEach((col) => pdf.text(col.x, y - 11, col.label, 7, 'F2'));
    y -= 18;
  }

  function drawWrappedText(x, topY, lines, size, leading) {
    lines.forEach((line, index) => pdf.text(x, topY - (index * leading), line, size, 'F1'));
  }

  function drawGrabList() {
    const subtitle = `${pullSummary.length || 0} grouped products · ${summary.total_units || 0} total units`;
    beginPage('Grab List', subtitle);
    const columns = [
      { label: 'Qty', x: pdf.margin, width: 34 },
      { label: 'Product', x: pdf.margin + 48, width: 250 },
      { label: 'Lots', x: pdf.margin + 320, width: contentWidth - 320 },
    ];
    drawTableHeader(columns);
    (pullSummary || []).forEach((row) => {
      const productLines = wrapPdfText(row.product_name, columns[1].width, 9);
      const lotLines = wrapPdfText(row.lots_label, columns[2].width, 8);
      const rowHeight = Math.max(20, Math.max(productLines.length, lotLines.length) * 10 + 8);
      ensureSpace(rowHeight + 18, 'Grab List', subtitle);
      pdf.text(columns[0].x, y - 10, row.qty, 10, 'F2');
      drawWrappedText(columns[1].x, y - 9, productLines, 9, 10);
      drawWrappedText(columns[2].x, y - 9, lotLines, 8, 10);
      pdf.line(pdf.margin, y - rowHeight, pdf.width - pdf.margin, y - rowHeight);
      y -= rowHeight;
    });
  }

  function drawPickList() {
    const subtitle = `${summary.total_shipments || orderedShipments.length || 0} customers · ${summary.total_lots || 0} lots`;
    beginPage('Pick List', subtitle);
    orderedShipments.forEach((ship, shipmentIndex) => {
      const buyer = `${ship.buyer_name || ship.username || 'Unknown customer'}${ship.username ? ` (@${ship.username})` : ''}`;
      const groupTitleLines = wrapPdfText(`${buyer} - ${Number(ship.total_items || 0)} item${Number(ship.total_items || 0) === 1 ? '' : 's'}`, contentWidth - 40, 11);
      const groupHeaderHeight = groupTitleLines.length * 12 + 12;
      ensureSpace(groupHeaderHeight + 38, 'Pick List', subtitle);
      pdf.rect(pdf.margin, y - groupHeaderHeight + 2, contentWidth, groupHeaderHeight, '0.97 0.98 0.99');
      groupTitleLines.forEach((line, index) => pdf.text(pdf.margin + 8, y - 12 - (index * 12), line, 11, 'F2'));
      pdf.text(pdf.width - pdf.margin - 22, y - 12, String(shipmentIndex + 1), 10, 'F2');
      y -= groupHeaderHeight + 4;
      const columns = [
        { label: 'Lot', x: pdf.margin + 4, width: 38 },
        { label: 'Barcode', x: pdf.margin + 62, width: 92 },
        { label: 'Product', x: pdf.margin + 176, width: 290 },
        { label: 'Qty', x: pdf.width - pdf.margin - 56, width: 22 },
        { label: 'OK', x: pdf.width - pdf.margin - 24, width: 18 },
      ];
      drawTableHeader(columns);
      (ship.items || []).forEach((item) => {
        const productLines = wrapPdfText(item.product_name || 'Unknown product', columns[2].width, 8.5);
        const barcodeLines = wrapPdfText(item.barcode || '-', columns[1].width, 8);
        const rowHeight = Math.max(18, Math.max(productLines.length, barcodeLines.length) * 10 + 7);
        ensureSpace(rowHeight + 42, 'Pick List', subtitle);
        pdf.text(columns[0].x, y - 9, item.lot_number || '-', 8.5, 'F2');
        drawWrappedText(columns[1].x, y - 9, barcodeLines, 8, 10);
        drawWrappedText(columns[2].x, y - 9, productLines, 8.5, 10);
        pdf.text(columns[3].x, y - 9, item.qty || 1, 8.5, 'F2');
        pdf.checkbox(columns[4].x, y - 14);
        pdf.line(pdf.margin, y - rowHeight, pdf.width - pdf.margin, y - rowHeight);
        y -= rowHeight;
      });
      y -= 8;
    });
  }

  if (mode === 'grab') drawGrabList();
  else if (mode === 'pick') drawPickList();
  else {
    drawGrabList();
    drawPickList();
  }

  return pdf.finish();
}

export function downloadPickListPdf({ mode = 'both', sessionName = '', shipments = [], summary = {}, pullSummary = [] }) {
  const blob = buildPickListPdfBlob({ mode, sessionName, shipments, summary, pullSummary });
  const safeSession = pdfSafeText(sessionName || 'tiktok-live-session')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 70) || 'tiktok-live-session';
  const suffix = mode === 'both' ? 'picklist-grablist' : `${mode}-list`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeSession}-${suffix}.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export default function TikTokLivePickList({ sessions = [], orderedDate = '', archiveName = '', lotNumbers = [], autoPrintMode = '', autoPrintToken = '', refreshToken = 0 }) {
  const [session, setSession] = useState('');
  const [payload, setPayload] = useState({ shipments: [], summary: {} });
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [query, setQuery] = useState('');
  const [lastPrintedToken, setLastPrintedToken] = useState('');

  useEffect(() => {
    if (orderedDate || lotNumbers.length) {
      setSession('');
      return;
    }
    if (!sessions.length) {
      setSession('');
      return;
    }
    if (!session || !sessions.some((candidate) => String(candidate.id) === String(session))) {
      setSession(String(sessions[0].id));
    }
  }, [session, sessions]);

  useEffect(() => {
    if (!session && !orderedDate && !lotNumbers.length) {
      setPayload({ shipments: [], summary: {} });
      return;
    }
    let cancelled = false;
    setLoading(true);
    const url = orderedDate
      ? `/api/tiktok_live_picklist?ordered_date=${encodeURIComponent(orderedDate)}`
      : session
        ? `/api/tiktok_live_picklist?session_id=${encodeURIComponent(session)}`
        : '/api/tiktok_live_picklist';
    fetchApi(url)
      .then((data) => {
        if (!cancelled) setPayload(data || { shipments: [], summary: {} });
      })
      .catch(() => {
        if (!cancelled) setPayload({ shipments: [], summary: {} });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [lotNumbers.length, orderedDate, refreshKey, refreshToken, session]);

  const selectedSession = useMemo(
    () => sessions.find((candidate) => String(candidate.id) === String(session)) || null,
    [session, sessions],
  );
  const shipments = payload?.shipments || [];
  const summary = payload?.summary || {};
  const lotNumberSet = useMemo(() => {
    const values = Array.isArray(lotNumbers) ? lotNumbers : [];
    return new Set(values.map((value) => String(value || '').trim()).filter(Boolean));
  }, [lotNumbers]);
  const scopedShipments = useMemo(() => {
    if (!lotNumberSet.size) return shipments;
    return shipments
      .map((ship) => {
        const items = (ship.items || []).filter((item) => lotNumberSet.has(String(item.lot_number || '').trim()));
        if (!items.length) return null;
        const totalItems = items.reduce((sum, item) => sum + Number(item.qty || 1), 0);
        const totalLines = items.length;
        const totalPrice = items.reduce((sum, item) => sum + Number(item.price || item.sale_price || 0), 0);
        return {
          ...ship,
          items,
          total_items: totalItems,
          total_lines: totalLines,
          total_price: totalPrice,
        };
      })
      .filter(Boolean);
  }, [lotNumberSet, shipments]);
  const scopedSummary = useMemo(() => ({
    ...summary,
    total_shipments: scopedShipments.length,
    total_lots: scopedShipments.reduce((sum, ship) => sum + (ship.items || []).length, 0),
    total_units: scopedShipments.reduce((sum, ship) => sum + Number(ship.total_items || 0), 0),
    total_revenue: Number(scopedShipments.reduce((sum, ship) => sum + Number(ship.total_price || 0), 0).toFixed(2)),
  }), [scopedShipments, summary]);
  const pullSummary = useMemo(() => buildPullSummary(scopedShipments), [scopedShipments]);
  const filteredShipments = useMemo(() => {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return scopedShipments;
    return scopedShipments.filter((ship) => {
      const buyerName = String(ship.buyer_name || '').toLowerCase();
      const username = String(ship.username || '').toLowerCase();
      const orderNumber = String(ship.order_number || '').toLowerCase();
      if (buyerName.includes(q) || username.includes(q) || orderNumber.includes(q)) return true;
      return (ship.items || []).some((item) => (
        String(item.lot_number || '').toLowerCase().includes(q)
        || String(item.barcode || '').toLowerCase().includes(q)
        || String(item.product_name || '').toLowerCase().includes(q)
      ));
    });
  }, [query, scopedShipments]);
  const hasVisibleData = filteredShipments.length > 0 || pullSummary.length > 0;

  function printSheet(mode) {
    if (!filteredShipments.length) return;
    downloadPickListPdf({
      mode,
      sessionName: archiveName || selectedSession?.name || selectedSession?.stream_url || `TikTok Session #${session}`,
      shipments: filteredShipments,
      summary: scopedSummary,
      pullSummary,
    });
  }

  useEffect(() => {
    if (!autoPrintMode || !autoPrintToken) return;
    if (lastPrintedToken === autoPrintToken) return;
    if (!filteredShipments.length) return;
    printSheet(autoPrintMode);
    setLastPrintedToken(autoPrintToken);
  }, [autoPrintMode, autoPrintToken, filteredShipments, lastPrintedToken]);

  const grabCols = [
    { label: 'Qty' },
    { label: 'Product' },
    { label: 'Lots' },
  ];

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      {!hasVisibleData ? null : (
      <FilterBar>
        {!orderedDate && !lotNumbers.length ? <SessionSelect sessions={sessions} value={session} onChange={setSession} allLabel="Select TikTok LIVE Session" /> : null}
        <SearchInput value={query} onChange={setQuery} placeholder="Search customer, lot, barcode, product..." />
        <PrimaryBtn onClick={() => setRefreshKey((value) => value + 1)}>Refresh</PrimaryBtn>
        <button type="button" className="btn-3d btn-3d-ghost" onClick={() => printSheet('pick')}>Download Pick PDF</button>
        <button type="button" className="btn-3d btn-3d-ghost" onClick={() => printSheet('grab')}>Download Grab PDF</button>
        <button type="button" className="btn-3d btn-3d-ghost" onClick={() => printSheet('both')}>Download Both PDF</button>
      </FilterBar>
      )}

      {hasVisibleData && selectedSession && !lotNumbers.length ? (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '16px 18px', display: 'grid', gap: 6 }}>
          <div style={{ fontSize: 17, fontWeight: 900, letterSpacing: '-0.02em' }}>{selectedSession.name || `TikTok Session #${selectedSession.id}`}</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {formatSessionLabel(selectedSession, sessions.findIndex((candidate) => String(candidate.id) === String(selectedSession.id)))} · derived live pick list from confirmed TikTok LIVE sale orders
          </div>
        </div>
      ) : null}

      {!hasVisibleData ? null : (
      <div style={{ display: 'grid', gap: 14 }}>
          {loading ? (
            <div style={{ padding: 32, borderRadius: 'var(--radius-lg)', background: 'var(--bg-panel)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', textAlign: 'center' }}>
              Loading pick list…
            </div>
          ) : null}
          {!loading && filteredShipments.length === 0 ? (
            <div style={{ padding: 32, borderRadius: 'var(--radius-lg)', background: 'var(--bg-panel)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', textAlign: 'center' }}>
              No TikTok LIVE sale orders ready for pick list yet.
            </div>
          ) : null}
          {!loading && filteredShipments.map((ship) => (
            <div
              key={`${ship.sale_order_id}-${ship.username || ship.buyer_name || 'buyer'}`}
              style={{
                display: 'grid',
                gap: 10,
                borderRadius: 'var(--radius-lg)',
                padding: '16px 18px',
                background: 'var(--bg-panel)',
                border: '1px solid var(--border-default)',
                boxShadow: 'var(--shadow-soft)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div style={{ display: 'grid', gap: 4 }}>
                  <div style={{ fontSize: 17, fontWeight: 900, letterSpacing: '-0.02em' }}>{ship.buyer_name || ship.username || 'Unknown customer'}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {ship.username ? `@${ship.username}` : 'No username'} · {ship.order_count > 1 ? `${ship.order_count} orders` : (ship.order_number || `SO-${ship.sale_order_id}`)}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                  <span style={{ padding: '6px 10px', borderRadius: 999, background: 'rgba(59,130,246,0.10)', color: 'var(--accent-blue)', fontWeight: 800, fontSize: 12 }}>
                    {ship.total_items || 0} product{Number(ship.total_items || 0) === 1 ? '' : 's'}
                  </span>
                  <span style={{ padding: '6px 10px', borderRadius: 999, background: 'rgba(245,158,11,0.12)', color: 'var(--accent-amber)', fontWeight: 800, fontSize: 12 }}>
                    {fmt$(ship.total_price || 0)}
                  </span>
                </div>
              </div>

              <TableShell
                footer={`${ship.total_lines || (ship.items || []).length} line${Number(ship.total_lines || (ship.items || []).length) === 1 ? '' : 's'} across ${ship.order_count || 1} order${Number(ship.order_count || 1) === 1 ? '' : 's'}`}
                tableStyle={{ tableLayout: 'fixed' }}
                colGroup={(
                  <colgroup>
                    <col style={{ width: '72px' }} />
                    <col style={{ width: '150px' }} />
                    <col />
                    <col style={{ width: '64px' }} />
                    <col style={{ width: '92px' }} />
                  </colgroup>
                )}
              >
                <Thead cols={[
                  { label: 'Lot No' },
                  { label: 'Barcode' },
                  { label: 'Product Name' },
                  { label: 'Qty', align: 'center' },
                  { label: 'Price', align: 'right' },
                ]} />
                <tbody>
                  {(ship.items || []).map((item, index) => (
                    <tr key={`${ship.sale_order_id}-${item.lot_number || index}-${item.barcode || item.product_name}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px 14px', fontWeight: 900 }}>#{item.lot_number || '—'}</td>
                      <td style={{ padding: '10px 14px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, color: 'var(--text-secondary)' }}>{item.barcode || '—'}</td>
                      <td style={{ padding: '10px 14px', fontWeight: 700 }}>{item.product_name || 'Unassigned item'}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'center', fontWeight: 800 }}>{item.qty || 1}</td>
                      <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 800, color: 'var(--accent-amber)' }}>{fmt$(item.price || item.sale_price || 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableShell>
            </div>
          ))}
        <TableShell footer={`${pullSummary.length} grouped product${pullSummary.length === 1 ? '' : 's'} for shelf pull`}>
          <Thead cols={grabCols} />
          <tbody>
            {(loading || pullSummary.length === 0) ? (
              <EmptyRow cols={grabCols.length} loading={loading} msg="No grouped TikTok products yet." />
            ) : null}
            {!loading && pullSummary.map((row) => (
              <tr key={row.key} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <td style={{ padding: '10px 14px', fontWeight: 900 }}>{row.qty}</td>
                <td style={{ padding: '10px 14px', fontWeight: 700 }}>{row.product_name}</td>
                <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)' }}>{row.lots_label || '—'}</td>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </div>
      )}
    </div>
  );
}
