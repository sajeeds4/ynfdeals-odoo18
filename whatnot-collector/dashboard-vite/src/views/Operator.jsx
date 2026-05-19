/**
 * Operator — Livestream operator's workstation.
 *
 * Improvements:
 *  - sync status badge (green/red) + failed ingests panel with retry
 *  - 10-second undo after Release
 *  - Manual lot number override input
 *  - Out-of-stock warning on scan
 *  - Collector health warning banner
 *  - Mobile responsive layout
 */
import { Fragment, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { usePolling, postApi, fetchApi } from '../hooks/useApi';
import { getScopedStorageKey, useLocalState, useSessionState } from '../hooks/useBrowserState';
import OBSOperatorPanel from '../components/OBSOperatorPanel';
import { readStore, writeStore } from './company/TikTokLiveSetup';

const TIKTOK_STORE_EVENT = 'ynf:tiktok-live-store-updated';
const TIKTOK_ACTIVE_FAST_POLL_MS = 1200;
const TIKTOK_EXTERNAL_ORDER_SYNC_MS = 1800;
const TIKTOK_DEMO_PLAYGROUND_LOTS = [1];

function fmt$(n) { return '$' + Number(n || 0).toFixed(2); }

function safeNowIso() {
  try { return new Date().toISOString(); } catch { return ''; }
}

const TIKTOK_PENDING_SCANS_STORAGE_KEY = 'operator.tiktokPendingScans.v1';
const TIKTOK_BUYER_MEMORY_STORAGE_KEY = 'operator.tiktokBuyerMemory.v1';
const AL_REHAB_RE = /\bal[\s-]*rehab\b/i;
const SUGGEST_NOISE = new Set(['the', 'and', 'for', 'lot', 'set', 'box', 'pack', 'card', 'cards', 'with', 'inc', 'new', 'used', 'item', 'items', 'pcs', 'piece']);

const compactBadgeStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '3px 7px',
  borderRadius: 999,
  fontSize: '0.64rem',
  fontWeight: 800,
  letterSpacing: '0.02em',
  whiteSpace: 'nowrap',
};

function countTikTokScannedRows(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => isTikTokRowFilled(row)).length;
}

function isTikTokReviewLaterValue(value) {
  return /^d1$/i.test(String(value || '').trim());
}

function isTikTokRowReviewLater(row) {
  return Boolean(
    row?.reviewLater
    || /^review later$/i.test(String(row?.statusLabel || '').trim())
    || /^review later$/i.test(String(row?.productName || '').trim())
    || /^review_later$/i.test(String(row?.notes || '').trim())
  );
}

function isTikTokRowFilled(row) {
  return Boolean(String(row?.barcode || '').trim() || isTikTokRowReviewLater(row) || String(row?.productName || '').trim());
}

function tiktokProductKey(row) {
  return String(
    row?.productId
    || row?.match?.id
    || row?.barcode
    || row?.productName
    || row?.match?.name
    || row?.lotNo
    || ''
  ).trim().toLowerCase();
}

function tiktokRowSalePrice(row) {
  return Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0);
}

function tiktokIsActivePaidSoldRow(row) {
  if (!row?.tiktokOrder) return false;
  const family = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').trim().toLowerCase();
  if (family === 'cancelled' || family === 'payment_failed') return false;
  if (isTikTokPaymentFailedRow(row)) return false;
  return tiktokRowSalePrice(row) > 0;
}

function tiktokDisplaySellerSku(row) {
  const lotNo = Number.parseInt(String(row?.lotNo || row?.tiktokOrder?.liveLotNumber || '').trim(), 10);
  if (Number.isFinite(lotNo) && lotNo > 0) {
    return String(((lotNo - 1) % 300) + 1);
  }
  return String(row?.tiktokOrder?.sellerSku || '').trim();
}

function tiktokRowCost(row) {
  return Number(row?.cost || row?.match?.cost_price || 0);
}

function tiktokRowFees(row) {
  return Number(row?.fees || 0);
}

function tiktokRowProfit(row) {
  return Number((tiktokRowSalePrice(row) - (tiktokRowCost(row) + tiktokRowFees(row))).toFixed(2));
}

function isTikTokPaymentFailedRow(row) {
  const text = [
    row?.statusFamily,
    row?.statusLabel,
    row?.paymentStatus,
    row?.payment_status,
    row?.tiktokOrder?.status,
    row?.tiktokOrder?.statusFamily,
    row?.tiktokOrder?.statusLabel,
    row?.tiktokOrder?.paymentStatus,
    row?.tiktokOrder?.payment_status,
  ].filter(Boolean).join(' ').toLowerCase();
  return /\b(unpaid|payment[_\s-]*(failed|cancelled|canceled)|payment[_\s-]*fail|payment[_\s-]*cancel|pay[_\s-]*fail)\b/.test(text);
}

function tiktokInlineOrderStatus(row) {
  const family = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').trim().toLowerCase();
  const text = [
    row?.paymentStatus,
    row?.payment_status,
    row?.statusLabel,
    row?.tiktokOrder?.paymentStatus,
    row?.tiktokOrder?.payment_status,
    row?.tiktokOrder?.statusLabel,
    row?.tiktokOrder?.status,
  ].filter(Boolean).join(' ').toLowerCase();
  if (isTikTokPaymentFailedRow(row)) return 'pay fail';
  if (family === 'cancelled' || /\b(cancelled|canceled|refunded)\b/.test(text)) return 'cancelled';
  if (/\b(paid|delivered|shipped|to ship|awaiting shipment)\b/.test(text) || family === 'confirmed') return 'paid';
  if (/\b(unpaid|pending|processing)\b/.test(text) || family === 'pending') return 'pending';
  return row?.tiktokOrder ? 'pending' : '';
}

function fmtPct(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return '0.0%';
  return `${numeric.toFixed(1)}%`;
}

function tiktokLotNumber(value) {
  const numeric = Number.parseInt(String(value || '').trim(), 10);
  return Number.isFinite(numeric) ? numeric : 0;
}

function tiktokExpectedBatchForLot(value) {
  const lotNo = tiktokLotNumber(value);
  if (!lotNo) return 1;
  return Math.floor((lotNo - 1) / 300) + 1;
}

function tiktokBatchRangeLabel(batchNumber) {
  const batch = Math.max(1, Number.parseInt(String(batchNumber || 1), 10) || 1);
  return `${((batch - 1) * 300) + 1}-${batch * 300}`;
}

function tiktokDemoPlaygroundRows() {
  return TIKTOK_DEMO_PLAYGROUND_LOTS.map((lotNo) => ({ lotNo: String(lotNo), barcode: '' }));
}

function tiktokRowEventTime(row) {
  return String(
    row?.orderedAt
    || row?.tiktokOrder?.soldAt
    || row?.tiktokOrder?.createdAt
    || row?.tiktokOrder?.paidAt
    || ''
  ).trim();
}

function parseTikTokTime(value) {
  const text = String(value || '').trim();
  if (!text) return 0;
  const millis = Date.parse(text);
  return Number.isFinite(millis) ? millis : 0;
}

function tiktokSessionSnapshot(rows, lotLimit = Infinity) {
  return (Array.isArray(rows) ? rows : []).reduce((acc, row) => {
    const lotNo = tiktokLotNumber(row?.lotNo);
    if (!lotNo || lotNo > lotLimit) return acc;
    if (!isTikTokRowFilled(row)) return acc;
    acc.lastLot = Math.max(acc.lastLot, lotNo);
    acc.filledLots += 1;
    const family = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').trim().toLowerCase();
    if (family === 'cancelled') {
      acc.cancelledLots += 1;
    }
    if ((family === 'pending' || family === 'confirmed') && !isTikTokPaymentFailedRow(row)) {
      acc.revenue += tiktokRowSalePrice(row);
      acc.cogs += tiktokRowCost(row);
      acc.fees += tiktokRowFees(row);
      acc.profit += tiktokRowProfit(row);
      acc.soldLots += 1;
      const eventTs = parseTikTokTime(tiktokRowEventTime(row));
      if (eventTs > acc.lastEventTs) acc.lastEventTs = eventTs;
    }
    return acc;
  }, {
    revenue: 0,
    cogs: 0,
    fees: 0,
    profit: 0,
    filledLots: 0,
    soldLots: 0,
    cancelledLots: 0,
    lastLot: 0,
    lastEventTs: 0,
  });
}

function pctDelta(currentValue, baselineValue) {
  const current = Number(currentValue || 0);
  const baseline = Number(baselineValue || 0);
  if (!Number.isFinite(current) || !Number.isFinite(baseline) || baseline === 0) return null;
  return ((current - baseline) / Math.abs(baseline)) * 100;
}

function averageNumber(values) {
  const clean = (Array.isArray(values) ? values : [])
    .map((value) => Number(value || 0))
    .filter((value) => Number.isFinite(value));
  if (!clean.length) return 0;
  return clean.reduce((sum, value) => sum + value, 0) / clean.length;
}

function signedDeltaLabel(value, positiveLabel = 'Ahead', negativeLabel = 'Behind') {
  if (value == null) return 'Need history';
  return `${value >= 0 ? positiveLabel : negativeLabel} ${fmtPct(Math.abs(value))}`;
}

function hasTikTokOrderData(row) {
  return Boolean(
    row?.tiktokOrder
    || String(row?.buyer || row?.buyer_username || row?.buyerName || '').trim()
    || String(row?.orderId || row?.externalOrderRef || '').trim()
    || String(row?.statusFamily || row?.statusLabel || '').trim()
  );
}

function mergeTikTokLiveRows(localRows, serverRows, sessionId = null) {
  const buyerMemory = rememberTikTokBuyerRows([...(Array.isArray(localRows) ? localRows : []), ...(Array.isArray(serverRows) ? serverRows : [])], sessionId);
  const localByLot = new Map((Array.isArray(localRows) ? localRows : []).map((row) => [String(row?.lotNo || '').trim(), row]));
  const merged = (Array.isArray(serverRows) ? serverRows : []).map((serverRow) => {
    const lotNo = String(serverRow?.lotNo || '').trim();
    const rowWithRememberedBuyer = applyRememberedTikTokBuyer(serverRow, buyerMemory, sessionId);
    const localRow = localByLot.get(lotNo);
    if (!localRow) return rowWithRememberedBuyer;
    const localHasValue = isTikTokRowFilled(localRow);
    const serverHasValue = isTikTokRowFilled(rowWithRememberedBuyer);
    if (hasTikTokOrderData(localRow) && !hasTikTokOrderData(rowWithRememberedBuyer)) {
      return {
        ...rowWithRememberedBuyer,
        ...localRow,
        tiktokBatchGuard: rowWithRememberedBuyer.tiktokBatchGuard || localRow.tiktokBatchGuard,
      };
    }
    if (!localHasValue || serverHasValue) return rowWithRememberedBuyer;
    return {
      ...rowWithRememberedBuyer,
      barcode: localRow.barcode,
      productName: localRow.productName || serverRow.productName,
      notes: localRow.notes || serverRow.notes,
      sku: localRow.sku || serverRow.sku,
      cost: Number(localRow.cost || 0) || serverRow.cost,
      productId: localRow.productId || serverRow.productId,
      itemId: localRow.itemId || serverRow.itemId,
      matched: localRow.matched || serverRow.matched,
    };
  });
  for (const localRow of Array.isArray(localRows) ? localRows : []) {
    const lotNo = String(localRow?.lotNo || '').trim();
    if (lotNo && !merged.some((row) => String(row?.lotNo || '').trim() === lotNo)) merged.push(localRow);
  }
  return merged;
}

function liveInventoryQty(product) {
  const value = Number(product?.on_hand_qty ?? product?.qty_available ?? product?.quantity ?? product?.virtual_available ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function liveInventoryKey(product, barcode) {
  const productId = String(product?.id || product?.product_id || '').trim();
  if (productId) return `product:${productId}`;
  return `code:${String(barcode || product?.barcode || product?.default_code || product?.sku || '').trim().toLowerCase()}`;
}

function productSearchText(product) {
  return [
    product?.name,
    product?.brand,
    product?.barcode,
    product?.default_code,
    product?.sku,
    product?.notes,
    product?.note_top,
    product?.note_mid,
    product?.note_base,
    product?.description,
    product?.dupe_inspiration,
    product?.dupe_classification,
    product?.dupe_notes,
    product?.similar_to,
    product?.dupe_research?.inspiration_fragrance,
    product?.dupe_research?.classification,
    product?.dupe_research?.notes,
    product?.fragrance_research?.top_notes,
    product?.fragrance_research?.heart_notes,
    product?.fragrance_research?.base_notes,
    product?.fragrance_research?.inspired_by_signature,
  ].filter(Boolean).join(' ').toLowerCase();
}

function normalizeProductSearchValue(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function productSearchScore(product, query, includeNotes = true) {
  const q = normalizeProductSearchValue(query);
  if (!q) return 0;
  const terms = q.split(/\s+/).filter(Boolean);
  const name = normalizeProductSearchValue(product?.name);
  const brand = normalizeProductSearchValue(product?.brand);
  const code = normalizeProductSearchValue([product?.barcode, product?.default_code, product?.sku].filter(Boolean).join(' '));
  const nameWords = name.split(/\s+/).filter(Boolean);
  const brandWords = brand.split(/\s+/).filter(Boolean);
  const notes = normalizeProductSearchValue([
    product?.notes,
    product?.note_top,
    product?.note_mid,
    product?.note_base,
    product?.description,
    product?.dupe_inspiration,
    product?.dupe_classification,
    product?.dupe_notes,
    product?.similar_to,
    product?.dupe_research?.inspiration_fragrance,
    product?.dupe_research?.classification,
    product?.dupe_research?.notes,
    product?.fragrance_research?.top_notes,
    product?.fragrance_research?.heart_notes,
    product?.fragrance_research?.base_notes,
    product?.fragrance_research?.inspired_by_signature,
  ].filter(Boolean).join(' '));
  const combined = [name, brand, code, includeNotes ? notes : ''].filter(Boolean).join(' ');
  if (!terms.every((term) => combined.includes(term))) return 0;

  let score = 1;
  if (code === q) score += 10000;
  if (code.startsWith(q)) score += 6000;
  if (name === q) score += 8000;
  if (name.startsWith(q)) score += 2500;
  if (nameWords.some((word) => word === q)) score += 9000;
  if (nameWords.some((word) => word.startsWith(q))) score += 8500;
  if (brandWords.some((word) => word.startsWith(q))) score += 2500;
  if (name.includes(q)) score += 5000;

  for (const term of terms) {
    if (nameWords.includes(term)) score += 2200;
    else if (nameWords.some((word) => word.startsWith(term))) score += 4200;
    else if (name.includes(term)) score += 350;
    if (brandWords.includes(term)) score += 250;
    else if (brandWords.some((word) => word.startsWith(term))) score += 500;
    if (code.includes(term)) score += 900;
    if (includeNotes && notes.includes(term)) score += 20;
  }

  if (terms.every((term) => name.includes(term))) score += 1800;
  if (includeNotes && terms.every((term) => notes.includes(term)) && !terms.some((term) => name.includes(term))) score -= 250;
  return score;
}

function productDupeLabel(product) {
  return String(
    product?.dupe_inspiration
    || product?.similar_to
    || product?.dupe_research?.inspiration_fragrance
    || product?.fragrance_research?.inspired_by_signature
    || ''
  ).trim();
}

function productNotesLabel(product) {
  return [
    product?.notes,
    product?.dupe_notes,
    product?.dupe_research?.notes,
    product?.description,
  ].map((value) => String(value || '').trim()).filter(Boolean).join(' ');
}

function productFragranceNotesLabel(product) {
  const top = String(product?.note_top || product?.fragrance_research?.top_notes || '').trim();
  const mid = String(product?.note_mid || product?.fragrance_research?.heart_notes || product?.fragrance_research?.mid_notes || '').trim();
  const base = String(product?.note_base || product?.fragrance_research?.base_notes || '').trim();
  return [
    top ? `Top: ${top}` : '',
    mid ? `Mid: ${mid}` : '',
    base ? `Base: ${base}` : '',
  ].filter(Boolean).join(' · ');
}

function productFragranceNotesCompact(product) {
  const top = String(product?.note_top || product?.fragrance_research?.top_notes || '').trim();
  const mid = String(product?.note_mid || product?.fragrance_research?.heart_notes || product?.fragrance_research?.mid_notes || '').trim();
  const base = String(product?.note_base || product?.fragrance_research?.base_notes || '').trim();
  return [top, mid, base].filter(Boolean).join('; ');
}

function compactProductClipboardText(product) {
  const parts = [];
  const dupe = productDupeLabel(product);
  const notes = productFragranceNotesCompact(product);
  if (dupe) parts.push(`Inspired by ${dupe}`);
  if (notes) parts.push(notes);
  const raw = parts.join('. ').replace(/\s+/g, ' ').trim();
  if (raw.length <= 100) return raw;
  const clipped = raw.slice(0, 100).replace(/\s+\S*$/, '').trim();
  return clipped || raw.slice(0, 100).trim();
}

function isProductNameSearch(value, inventoryMap) {
  const query = String(value || '').trim();
  if (!query) return false;
  if (inventoryMap?.has?.(query.toLowerCase())) return false;
  return /[a-z]/i.test(query);
}

function productBarcode(product) {
  return String(product?.barcode || product?.default_code || product?.sku || '').trim();
}

function shortDisplayProductName(value) {
  const original = String(value || '').trim();
  if (!original) return '';
  return original
    .replace(/\bEau de Parfum\b/ig, '')
    .replace(/\bEau de Toilette\b/ig, '')
    .replace(/\bExtrait de Parfum\b/ig, '')
    .replace(/\bParfum Spray\b/ig, '')
    .replace(/\bEDP Spray\b/ig, '')
    .replace(/\bEDT Spray\b/ig, '')
    .replace(/\bEDP\b/ig, '')
    .replace(/\bEDT\b/ig, '')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+\(\s*/g, ' (')
    .replace(/\(\s*\)/g, '')
    .replace(/\s+([,.)])/g, '$1')
    .trim() || original;
}

function cleanTikTokBuyer(value) {
  return String(value || '').replace(/^tiktok_live:/i, '').trim();
}

function tiktokRowBuyer(row) {
  return cleanTikTokBuyer(row?.tiktokOrder?.buyerDisplay || row?.buyer || row?.tiktokOrder?.buyerUsername || row?.tiktokOrder?.buyerName || '');
}

function tiktokBuyerKey(value) {
  return cleanTikTokBuyer(value).toLowerCase();
}

function readTikTokBuyerMemory() {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(window.localStorage.getItem(TIKTOK_BUYER_MEMORY_STORAGE_KEY) || '{}') || {};
  } catch {
    return {};
  }
}

function writeTikTokBuyerMemory(memory) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TIKTOK_BUYER_MEMORY_STORAGE_KEY, JSON.stringify(memory || {}));
  } catch {}
}

function tiktokBuyerMemoryKeys(row, sessionId = null) {
  const sessionPart = String(sessionId || row?.serverSessionId || row?.sessionId || row?.session_id || '').trim();
  const orderPart = String(row?.tiktokOrder?.orderId || row?.orderId || row?.externalOrderRef || '').trim();
  const lotPart = String(row?.lotNo || row?.lot_no || '').trim();
  return [
    sessionPart && orderPart ? `${sessionPart}:order:${orderPart}` : '',
    sessionPart && lotPart ? `${sessionPart}:lot:${lotPart}` : '',
    orderPart ? `order:${orderPart}` : '',
    lotPart ? `lot:${lotPart}` : '',
  ].filter(Boolean);
}

function rememberTikTokBuyerRows(rows, sessionId = null) {
  if (typeof window === 'undefined') return {};
  const memory = readTikTokBuyerMemory();
  let changed = false;
  (Array.isArray(rows) ? rows : []).forEach((row) => {
    const buyer = tiktokRowBuyer(row);
    const keys = tiktokBuyerMemoryKeys(row, sessionId);
    if (!buyer || !keys.length) return;
    const rememberedBuyer = {
      buyer,
      buyerDisplay: row?.tiktokOrder?.buyerDisplay || row?.buyer || buyer,
      buyerUsername: row?.tiktokOrder?.buyerUsername || row?.buyer_username || buyer,
      buyerName: row?.tiktokOrder?.buyerName || row?.buyerName || buyer,
      rememberedAt: safeNowIso(),
    };
    keys.forEach((key) => {
      memory[key] = rememberedBuyer;
    });
    changed = true;
  });
  if (changed) writeTikTokBuyerMemory(memory);
  return memory;
}

function applyRememberedTikTokBuyer(row, memory, sessionId = null) {
  if (tiktokRowBuyer(row)) return row;
  const remembered = tiktokBuyerMemoryKeys(row, sessionId).map((key) => memory?.[key]).find((entry) => entry?.buyer);
  if (!remembered?.buyer) return row;
  return {
    ...row,
    buyer: row?.buyer || remembered.buyerDisplay || remembered.buyer,
    buyer_username: row?.buyer_username || remembered.buyerUsername || remembered.buyer,
    tiktokOrder: row?.tiktokOrder
      ? {
          ...row.tiktokOrder,
          buyerDisplay: row.tiktokOrder.buyerDisplay || remembered.buyerDisplay || remembered.buyer,
          buyerUsername: row.tiktokOrder.buyerUsername || remembered.buyerUsername || remembered.buyer,
          buyerName: row.tiktokOrder.buyerName || remembered.buyerName || remembered.buyer,
        }
      : row?.tiktokOrder,
  };
}

function focusWithoutScroll(node, select = false) {
  if (!node) return;
  try {
    node.focus({ preventScroll: true });
  } catch {
    node.focus();
  }
  if (select) {
    try {
      node.select?.();
    } catch {}
  }
}

function normalizeTasteProductName(value) {
  return shortDisplayProductName(value).toLowerCase().replace(/\s+/g, ' ').trim();
}

function extractTasteTerms(value) {
  return normalizeTasteProductName(value)
    .split(/[\s,/|()\-]+/)
    .filter((term) => term.length > 2 && !SUGGEST_NOISE.has(term) && !AL_REHAB_RE.test(term));
}

function PosTile({ title, accent = 'var(--border-default)', children, style = {} }) {
  return (
    <div
      className="panel animate-in"
      style={{
        borderRadius: 18,
        border: `1px solid ${accent}`,
        background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01))',
        boxShadow: '0 14px 32px rgba(0,0,0,0.18)',
        ...style,
      }}
    >
      <div style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 12 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function CandidateTile({ item, selected, onSelect, onRemove }) {
  return (
    <div
      style={{
        borderRadius: 16,
        border: `2px solid ${selected ? 'var(--accent-emerald)' : 'var(--border-default)'}`,
        background: selected
          ? 'linear-gradient(180deg, rgba(16,185,129,0.12), rgba(16,185,129,0.05))'
          : 'var(--bg-elevated)',
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minHeight: 210,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        {item.image_url ? (
          <img src={item.image_url} alt="" style={{ width: 64, height: 64, borderRadius: 12, objectFit: 'cover', flexShrink: 0 }} />
        ) : (
          <div style={{ width: 64, height: 64, borderRadius: 12, background: 'var(--bg-layer2)', display: 'grid', placeItems: 'center', fontSize: '1.6rem' }}>📦</div>
        )}
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: selected ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>
            {selected ? 'Live Choice' : 'Candidate'}
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.22, marginTop: 4 }}>
            {shortDisplayProductName(item.product_name) || 'Unnamed product'}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {item.barcode ? <span className="chip chip--blue">{item.barcode}</span> : null}
        <span className="chip chip--amber">Cost {fmt$(item.cost)}</span>
        <span className="chip chip--emerald">Scanned x{Math.max(1, Number(item.scanned_qty || item.qty_snapshot || 1))}</span>
        {item.qty_remaining != null ? <span className="chip chip--blue">{Math.max(0, Number(item.qty_remaining || 0))} left</span> : null}
      </div>

      <div style={{ marginTop: 'auto', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <button
          className="btn"
          onClick={() => onSelect(item)}
          style={{
            minHeight: 58,
            borderRadius: 14,
            fontSize: '1rem',
            fontWeight: 800,
            background: selected ? 'var(--accent-emerald)' : 'linear-gradient(135deg, #2563eb, #1d4ed8)',
            color: '#fff',
          }}
        >
          {selected ? 'Showing Live' : 'Show This'}
        </button>
        <button
          className="btn"
          onClick={() => onRemove(item)}
          style={{
            minHeight: 58,
            borderRadius: 14,
            fontSize: '1rem',
            fontWeight: 800,
            background: 'linear-gradient(135deg, #4b5563, #374151)',
            color: '#fff',
          }}
        >
          Remove
        </button>
      </div>
    </div>
  );
}

function ActionTile({ label, value, hint, onClick, disabled = false, tone = 'blue' }) {
  const backgrounds = {
    blue: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
    emerald: 'linear-gradient(135deg, #059669, #047857)',
    coral: 'linear-gradient(135deg, #dc2626, #b91c1c)',
    slate: 'linear-gradient(135deg, #475569, #334155)',
    amber: 'linear-gradient(135deg, #d97706, #b45309)',
  };
  return (
    <button
      className="btn"
      onClick={onClick}
      disabled={disabled}
      style={{
        minHeight: 132,
        borderRadius: 18,
        padding: '16px 18px',
        textAlign: 'left',
        border: 'none',
        color: '#fff',
        background: backgrounds[tone] || backgrounds.blue,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        opacity: disabled ? 0.45 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        boxShadow: '0 12px 30px rgba(0,0,0,0.2)',
      }}
    >
      <div style={{ fontSize: '0.8rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', opacity: 0.9 }}>
        {label}
      </div>
      <div style={{ fontSize: '1.55rem', fontWeight: 900, lineHeight: 1.05 }}>
        {value}
      </div>
      {hint ? <div style={{ fontSize: '0.92rem', lineHeight: 1.3, opacity: 0.92 }}>{hint}</div> : <div />}
    </button>
  );
}

export default function Operator({ includeObsPanel = false }) {
  const [viewportWidth, setViewportWidth] = useState(() => (typeof window === 'undefined' ? 1600 : window.innerWidth));
  const operatorPollingOptions = { hydrateFromCache: false, pauseWhenHidden: true, refreshOnFocus: true };
  const { data: stats, refresh: refreshStats } = usePolling(['/api/v2/sessions/current/stats', '/api/session_stats'], 1800, true, operatorPollingOptions);
  const { data: streamStatus } = usePolling('/api/stream_status', 2500, true, operatorPollingOptions);
  const { data: lotProducts, refresh: refreshLotProducts } = usePolling('/api/current_lot/products', 1800, true, operatorPollingOptions);
  const { data: failedData, refresh: refreshFailed } = usePolling('/api/failed_ingests', 8000, true, { pauseWhenHidden: true, refreshOnFocus: true });
  const { data: healthData } = usePolling('/api/collector/health', 20000, true, { pauseWhenHidden: true, refreshOnFocus: true });
  const { data: livebuyers } = usePolling('/api/live_top_buyers', 8000, true, { pauseWhenHidden: true, refreshOnFocus: true });

  const [scanInput, setScanInput] = useSessionState('operator.scanInput', '');
  const [feedback, setFeedback] = useState(null);
  const [scanMode, setScanMode] = useSessionState('operator.scanMode', true);
  const [bulkRetrying, setBulkRetrying] = useState(false);
  const [bulkDismissing, setBulkDismissing] = useState(false);
  const [failedExpanded, setFailedExpanded] = useSessionState('operator.failedExpanded', false);
  const [manualLotNumber, setManualLotNumber] = useSessionState('operator.manualLotNumber', '');
  const [showLotInput, setShowLotInput] = useSessionState('operator.showLotInput', false);
  const [streamUrlInput, setStreamUrlInput] = useSessionState('operator.streamUrlInput', '');
  const [streamUrlBusy, setStreamUrlBusy] = useState(false);
  // Undo state after release
  const [undoAvailable, setUndoAvailable] = useState(false);
  const [undoSeconds, setUndoSeconds] = useState(0);
  const undoTimerRef = useRef(null);
  const lastDroppedLotRef = useRef(null);
  const scanQueueRef = useRef([]);
  const scanProcessingRef = useRef(false);

  const scanRef = useRef(null);

  const isRunning = streamStatus?.running || false;
  const session = stats?.session || {};
  const activeItem = stats?.active_item || {};
  const currentLot = stats?.current_lot || {};
  const auctionState = stats?.latest_auction_state || {};

  const auctionStarted = auctionState.state === 'awaiting_auction';
  const hasActiveLot = !!currentLot.lot_number;
  const showRelease = hasActiveLot && !auctionStarted;

  const activeLotRows = (lotProducts?.rows || []).filter(
    p => p.status !== 'dropped' && p.status !== 'released'
  );
  const selectedCandidate = activeLotRows.find((row) => row.selected || row.status === 'active') || null;
  const candidateRows = [...activeLotRows].sort((a, b) => {
    if ((a.selected || a.status === 'active') && !(b.selected || b.status === 'active')) return -1;
    if (!(a.selected || a.status === 'active') && (b.selected || b.status === 'active')) return 1;
    return Number(b.id || 0) - Number(a.id || 0);
  });

  const failedIngests = (failedData?.records || []).filter(r => !r.resolved);
  const healthWarnings = healthData?.warnings || [];
  const collectorUnhealthy = isRunning && healthWarnings.length > 0;
  const activeMode = 'our_stream';
  const isSpectator = false;
  const currentStreamUrl = streamStatus?.stream_url || stats?.current_stream_url || '';
  const tiktokOperator = streamStatus?.tiktok_operator || {};
  const [tiktokHandleInput, setTikTokHandleInput] = useSessionState('operator.tiktokHandleInput', (tiktokOperator?.streamer || ''));
  const [tiktokBusy, setTikTokBusy] = useState(false);
  const [platform, setPlatform] = useSessionState('operator.platform', 'whatnot'); // 'whatnot' | 'tiktok'
  const tiktokSessionId = tiktokOperator?.session_id;
  const { data: tiktokWinnerState, refresh: refreshTikTokWinnerState } = usePolling(
    `/api/winner_assignment/state?session_id=${encodeURIComponent(tiktokSessionId || '')}`,
    1200,
    !!tiktokOperator?.enabled,
    { useCache: false, hydrateFromCache: false },
  );
  const [tiktokWinnerScanInput, setTikTokWinnerScanInput] = useSessionState('operator.tiktokWinnerScanInput', '');
  const [tiktokAutoConfirm, setTikTokAutoConfirm] = useSessionState('operator.tiktokAutoConfirm', true);
  const [tiktokWinnerBusy, setTikTokWinnerBusy] = useState(false);
  const [tiktokLotInput, setTikTokLotInput] = useSessionState('operator.tiktokLotInput', '');
  const tiktokScanRef = useRef(null);
  const tiktokStreamUrl = tiktokOperator?.stream_url || '';
  const { data: tiktokLotState, refresh: refreshTikTokLotState } = usePolling(
    tiktokStreamUrl ? `/api/tiktok_extractor/lot_state?stream_url=${encodeURIComponent(tiktokStreamUrl)}` : null,
    1200,
    !!tiktokOperator?.enabled && !!tiktokStreamUrl,
    { useCache: false, hydrateFromCache: false },
  );

  // --- TikTok Go Live state (shared with Company > TikTok > Go Live via localStorage) ---
  const [liveInventory, setLiveInventory] = useState([]);
  const [lotCount, setLotCount] = useState('1');
  const [liveRows, setLiveRows] = useState([]);
  const [isGoingLive, setIsGoingLive] = useState(false);
  const [liveSequence, setLiveSequence] = useState(0);
  const [goLiveHistory, setGoLiveHistory] = useState([]);
  const [goLiveSessionId, setGoLiveSessionId] = useState(null);
  const [tiktokActiveSessionMeta, setTikTokActiveSessionMeta] = useState(null);
  const tiktokPendingScansStorageKey = getScopedStorageKey(TIKTOK_PENDING_SCANS_STORAGE_KEY);
  const [tiktokPendingScans, setTikTokPendingScans] = useLocalState(tiktokPendingScansStorageKey, []);
  const [tiktokSaveState, setTikTokSaveState] = useState({ status: 'idle', message: '' });
  const [tiktokEndArmedUntil, setTikTokEndArmedUntil] = useState(0);
  const [tiktokEndArmSeconds, setTikTokEndArmSeconds] = useState(0);
  const [tiktokDemoMode, setTikTokDemoMode] = useSessionState('operator.tiktokDemoMode', false);
  const [tiktokRecoverableLocalDraft, setTikTokRecoverableLocalDraft] = useState(null);
  const [tiktokRecoverableServerSession, setTikTokRecoverableServerSession] = useState(null);
  const [tiktokRecoveryChecked, setTikTokRecoveryChecked] = useState(false);
  const [tiktokSessionHydrating, setTikTokSessionHydrating] = useState(true);
  const [tiktokNextSequence, setTikTokNextSequence] = useState(null);
  const [tiktokBarcodeSearchRow, setTikTokBarcodeSearchRow] = useState(null);
  const [tiktokBarcodeDraft, setTikTokBarcodeDraft] = useState({ row: null, value: '' });
  const [tiktokInventorySearch, setTikTokInventorySearch] = useSessionState('operator.tiktokInventorySearch', '');
  const [tiktokCustomerLookup, setTikTokCustomerLookup] = useSessionState('operator.tiktokCustomerLookup', '');
  const [tiktokCustomerContext, setTikTokCustomerContext] = useState(null);
  const [tiktokInspectedProduct, setTikTokInspectedProduct] = useState(null);
  const [tiktokCopiedProductNote, setTikTokCopiedProductNote] = useState(false);
  const [tiktokCustomerProfile, setTikTokCustomerProfile] = useState(null);
  const [tiktokCustomerOrders, setTikTokCustomerOrders] = useState([]);
  const [tiktokCustomerOrderLinesById, setTikTokCustomerOrderLinesById] = useState({});
  const [tiktokCustomerLoading, setTikTokCustomerLoading] = useState(false);
  const [tiktokApiLog, setTikTokApiLog] = useState([]);
  const [tiktokKpiView, setTikTokKpiView] = useState(null);
  const tiktokBarcodeRefs = useRef({});
  const tiktokActiveSyncInFlightRef = useRef(false);
  const tiktokExternalSyncLastRunRef = useRef(0);
  const tiktokSavingLotsRef = useRef(new Set());
  const tiktokCommittedValuesRef = useRef(new Map());
  const tiktokLastRemotePreviewRef = useRef('');
  const tiktokStartLiveRef = useRef(false);
  const tiktokEndLiveRef = useRef(false);

  const loadTikTokGoLiveHistory = useCallback(async () => {
    try {
      const data = await fetchApi('/api/tiktok_live_sessions?limit=40');
      setGoLiveHistory(Array.isArray(data?.rows) ? data.rows : []);
    } catch {
      // ignore history refresh failures
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handleResize = () => setViewportWidth(window.innerWidth || 1600);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  function pushTikTokApiLog(status, message) {
    const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setTikTokApiLog((prev) => [{ ts, status, message }, ...prev].slice(0, 12));
  }

  // Read Go Live store on mount
  useEffect(() => {
    const store = readStore();
    const draftRows = Array.isArray(store.draft.rows) ? store.draft.rows : [];
    const draftHasServerSession = Number(store.draft.serverSessionId || 0) > 0;
    const hasRecoverableDraft = !!store.draft.isLive && !draftHasServerSession && draftRows.some((row) => String(row?.barcode || '').trim());
    if (hasRecoverableDraft) {
      setTikTokRecoverableLocalDraft({
        rows: draftRows,
        serverSessionId: store.draft.serverSessionId || null,
        sequence: Number(store.seq || 0),
      });
    }
    setLotCount(store.draft.lotCount || '1');
    setLiveRows(hasRecoverableDraft ? draftRows : []);
    setIsGoingLive(false);
    setGoLiveSessionId(null);
    setLiveSequence(Number(store.seq || 0));
    setTikTokActiveSessionMeta(null);
    setTikTokSessionHydrating(true);

    let cancelled = false;
    fetchApi('/api/tiktok_live_sessions/active?fast=1')
      .then((data) => {
        if (cancelled) return;
        const session = data?.session || null;
        if (!session?.serverSessionId) {
          if (store.draft?.isLive || draftRows.length) {
            writeStore({
              draft: {
                lotCount: '1',
                rows: [],
                isLive: false,
                liveName: '',
                serverSessionId: null,
                detailsCsvText: '',
                detailsCsvName: '',
              },
              history: [],
              seq: Number(store.seq || 0),
            });
          }
          setLiveRows(hasRecoverableDraft ? draftRows : []);
          setIsGoingLive(false);
          setGoLiveSessionId(null);
          setTikTokActiveSessionMeta(null);
          setTikTokRecoveryChecked(true);
          setTikTokSessionHydrating(false);
          return;
        }
        const serverRows = Array.isArray(session.rows) ? session.rows : [];
        const localRows = draftHasServerSession && Number(store.draft.serverSessionId || 0) === Number(session.serverSessionId || 0)
          ? draftRows
          : [];
        const restoredRows = mergeTikTokLiveRows(localRows, serverRows, session.serverSessionId);
        setLiveRows(restoredRows);
        setIsGoingLive(true);
        setGoLiveSessionId(session.serverSessionId || null);
        setLiveSequence(Number(session.sequence || store.seq || 0));
        setTikTokActiveSessionMeta(session);
        setTikTokRecoverableLocalDraft(null);
        setTikTokRecoverableServerSession(null);
        setTikTokRecoveryChecked(true);
        setTikTokSessionHydrating(false);
        writeStore({
          draft: {
            lotCount: String(Math.max(1, restoredRows.length || 1)),
            rows: restoredRows,
            isLive: true,
            liveName: '',
            serverSessionId: session.serverSessionId || null,
            detailsCsvText: '',
            detailsCsvName: '',
          },
          history: [],
          seq: Math.max(Number(store.seq || 0), Number(session.sequence || 0)),
        });
      })
      .catch(() => {
        if (!cancelled) {
          setTikTokRecoveryChecked(true);
          setTikTokSessionHydrating(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (platform !== 'tiktok') return undefined;
    let cancelled = false;
    const refreshHistory = async () => {
      try {
        const data = await fetchApi('/api/tiktok_live_sessions?limit=40');
        if (!cancelled) setGoLiveHistory(Array.isArray(data?.rows) ? data.rows : []);
      } catch {
        // ignore history refresh failures
      }
    };
    refreshHistory();
    const timer = window.setInterval(refreshHistory, isGoingLive ? 45000 : 90000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [platform, isGoingLive]);

  useEffect(() => {
    if (platform !== 'tiktok' || tiktokDemoMode || !isGoingLive || !goLiveSessionId) return undefined;
    let cancelled = false;
    const syncActiveSession = () => {
      if (tiktokActiveSyncInFlightRef.current) return;
      tiktokActiveSyncInFlightRef.current = true;
      const now = Date.now();
      const shouldSyncTikTokOrders = now - Number(tiktokExternalSyncLastRunRef.current || 0) > TIKTOK_EXTERNAL_ORDER_SYNC_MS;
      const activeSessionUrl = shouldSyncTikTokOrders
        ? '/api/tiktok_live_sessions/active?sync=1'
        : '/api/tiktok_live_sessions/active?fast=1';
      if (shouldSyncTikTokOrders) tiktokExternalSyncLastRunRef.current = now;
      fetchApi(activeSessionUrl)
        .then((data) => {
          if (cancelled) return;
          const session = data?.session || null;
          if (!session?.serverSessionId) {
            setTikTokActiveSessionMeta(null);
            return;
          }
          if (Number(session.serverSessionId || 0) !== Number(goLiveSessionId || 0)) return;
          const serverRows = Array.isArray(session.rows) ? session.rows : [];
          setLiveRows((currentRows) => {
            const nextRows = mergeTikTokLiveRows(currentRows, serverRows, session.serverSessionId);
            setLotCount(String(Math.max(1, nextRows.length || 1)));
            writeStore({
              draft: {
                lotCount: String(Math.max(1, nextRows.length || 1)),
                rows: nextRows,
                isLive: true,
                liveName: '',
                serverSessionId: session.serverSessionId || null,
                detailsCsvText: '',
                detailsCsvName: '',
              },
              history: [],
              seq: Math.max(Number(readStore().seq || 0), Number(session.sequence || 0)),
            });
            return nextRows;
          });
          setLiveSequence((current) => Math.max(Number(current || 0), Number(session.sequence || 0)));
          setTikTokActiveSessionMeta(session);
          setTikTokRecoverableLocalDraft(null);
          setTikTokRecoverableServerSession(null);
        })
        .catch(() => {})
        .finally(() => {
          tiktokActiveSyncInFlightRef.current = false;
        });
    };
    syncActiveSession();
    const timer = window.setInterval(syncActiveSession, TIKTOK_ACTIVE_FAST_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [platform, tiktokDemoMode, isGoingLive, goLiveSessionId]);

  useEffect(() => {
    if (platform !== 'tiktok' || isGoingLive || tiktokDemoMode) return undefined;
    let cancelled = false;
    fetchApi('/api/tiktok_live_sessions/next_sequence')
      .then((data) => {
        if (cancelled) return;
        const sequence = Number(data?.sequence || 0);
        if (Number.isFinite(sequence) && sequence > 0) setTikTokNextSequence(sequence);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [platform, isGoingLive, tiktokDemoMode, tiktokRecoveryChecked]);

  useEffect(() => {
    const sync = () => {
      const store = readStore();
      setLiveSequence(Number(store.seq || 0));

      const draftRows = Array.isArray(store.draft.rows) ? store.draft.rows : [];
      if (isGoingLive) {
        const localSessionId = Number(goLiveSessionId || 0);
        const incomingSessionId = Number(store.draft.serverSessionId || 0);
        const sameSession = localSessionId > 0 && localSessionId === incomingSessionId;
        const incomingScanned = countTikTokScannedRows(draftRows);
        const localScanned = countTikTokScannedRows(liveRows);
        if (sameSession && incomingScanned >= localScanned && draftRows.length >= liveRows.length) {
	          setLiveRows(mergeTikTokLiveRows(liveRows, draftRows, goLiveSessionId));
          setLotCount(store.draft.lotCount || '1');
        }
        return;
      }

      const draftHasServerSession = Number(store.draft.serverSessionId || 0) > 0;
      setLotCount(store.draft.lotCount || '1');
      setLiveRows([]);
      setIsGoingLive(false);
      setGoLiveSessionId(null);
      setTikTokActiveSessionMeta(null);
      if (!!store.draft.isLive && !draftHasServerSession && draftRows.some((row) => String(row?.barcode || '').trim())) {
        setTikTokRecoverableLocalDraft({
          rows: draftRows,
          serverSessionId: store.draft.serverSessionId || null,
          sequence: Number(store.seq || 0),
        });
      }
    };
    window.addEventListener(TIKTOK_STORE_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(TIKTOK_STORE_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, [goLiveSessionId, isGoingLive, liveRows]);

  // Write Go Live store whenever draft changes
  useEffect(() => {
    writeStore({
      draft: { lotCount, rows: liveRows, isLive: isGoingLive, liveName: '', serverSessionId: goLiveSessionId, detailsCsvText: '', detailsCsvName: '' },
      history: [],
      seq: liveSequence,
    });
  }, [lotCount, liveRows, isGoingLive, goLiveSessionId, goLiveHistory, liveSequence]);

  // Fetch inventory for barcode matching when TikTok mode is active
  useEffect(() => {
    if (platform !== 'tiktok') return;
    let cancelled = false;
    const loadInventory = () => fetchApi('/api/inventory?active=all&status=all&compact=1')
      .then((data) => {
        if (!cancelled) setLiveInventory(data.rows || []);
      })
      .catch(() => {});
    loadInventory();
    const timer = isGoingLive ? window.setInterval(() => {
      if (!cancelled) loadInventory();
    }, 30000) : null;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [platform, isGoingLive]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (tiktokPendingScansStorageKey === TIKTOK_PENDING_SCANS_STORAGE_KEY) return;
    try {
      const scopedRaw = window.localStorage.getItem(tiktokPendingScansStorageKey);
      if (scopedRaw != null) {
        window.localStorage.removeItem(TIKTOK_PENDING_SCANS_STORAGE_KEY);
        return;
      }
      const legacyRaw = window.localStorage.getItem(TIKTOK_PENDING_SCANS_STORAGE_KEY);
      if (!legacyRaw) return;
      const parsed = JSON.parse(legacyRaw);
      if (!Array.isArray(parsed) || !parsed.length) {
        window.localStorage.removeItem(TIKTOK_PENDING_SCANS_STORAGE_KEY);
        return;
      }
      setTikTokPendingScans(parsed);
      window.localStorage.removeItem(TIKTOK_PENDING_SCANS_STORAGE_KEY);
    } catch {
      // ignore storage migration issues
    }
  }, [setTikTokPendingScans, tiktokPendingScansStorageKey]);

  const tiktokInventoryMap = useMemo(() => {
    const map = new Map();
    liveInventory.forEach((p) => {
      const barcode = String(p.barcode || '').trim().toLowerCase();
      const sku = String(p.default_code || p.sku || '').trim().toLowerCase();
      if (barcode) map.set(barcode, p);
      if (sku) map.set(sku, p);
    });
    return map;
  }, [liveInventory]);

  const tiktokProductSearchRows = useMemo(() => (
    liveInventory
      .filter((product) => productBarcode(product))
      .map((product) => ({ product, searchText: productSearchText(product) }))
  ), [liveInventory]);

  function tiktokProductSuggestions(query) {
    const q = String(query || '').trim().toLowerCase();
    if (q.length < 2 || !isProductNameSearch(q, tiktokInventoryMap)) return [];
    return tiktokProductSearchRows
      .map(({ product }) => ({ product, score: productSearchScore(product, q, false) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score || liveInventoryQty(b.product) - liveInventoryQty(a.product) || String(a.product?.name || '').localeCompare(String(b.product?.name || '')))
      .slice(0, 8)
      .map(({ product }) => product);
  }

  const tiktokMatchedRows = useMemo(() => (
    liveRows.map((row) => ({
      ...row,
      match: tiktokInventoryMap.get(String(row.barcode || '').trim().toLowerCase()) || null,
    })).reduce((acc, row) => {
      if (!String(row?.barcode || '').trim() || !row.match) {
        acc.rows.push(row);
        return acc;
      }
      const key = liveInventoryKey(row.match, row.barcode);
      const originalQty = liveInventoryQty(row.match);
      const scannedThroughThisLot = Number(acc.counts.get(key) || 0) + 1;
      acc.counts.set(key, scannedThroughThisLot);
      const scannedBeforeThisLot = Math.max(0, scannedThroughThisLot - 1);
      acc.rows.push({
        ...row,
        liveOriginalQty: originalQty,
        liveScannedBeforeQty: scannedBeforeThisLot,
        liveScannedQty: scannedThroughThisLot,
        liveRemainingQty: originalQty - scannedThroughThisLot,
      });
      return acc;
    }, { rows: [], counts: new Map() }).rows
  ), [liveRows, tiktokInventoryMap]);

  const tiktokSessionScanCounts = useMemo(() => (
    tiktokMatchedRows.reduce((acc, row) => {
      if (!row.match) return acc;
      const key = liveInventoryKey(row.match, row.barcode);
      acc.set(key, Number(acc.get(key) || 0) + 1);
      return acc;
    }, new Map())
  ), [tiktokMatchedRows]);

  const tiktokDisplayRows = useMemo(() => {
    const orderedRows = tiktokMatchedRows
      .map((row, sourceIndex) => ({ ...row, _sourceIndex: sourceIndex }))
      .sort((left, right) => {
        const leftNo = Number.parseInt(String(left?.lotNo || ''), 10);
        const rightNo = Number.parseInt(String(right?.lotNo || ''), 10);
        const leftRank = Number.isFinite(leftNo) ? leftNo : Number.NEGATIVE_INFINITY;
        const rightRank = Number.isFinite(rightNo) ? rightNo : Number.NEGATIVE_INFINITY;
        return rightRank - leftRank;
      });
    return orderedRows;
  }, [tiktokMatchedRows]);

  const tiktokMatchedCount = tiktokMatchedRows.filter((r) => r.match || r.productName).length;
  const tiktokUnmappedCount = tiktokMatchedRows.filter((r) => r.barcode && !r.match && !r.productName).length;
  const tiktokLiveSummary = useMemo(() => (
    tiktokMatchedRows.reduce((acc, row) => {
      if (!isTikTokRowFilled(row)) return acc;
      const family = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').trim().toLowerCase();
      if (family === 'pending') acc.pending += 1;
      else if (family === 'confirmed') acc.confirmed += 1;
      else if (family === 'cancelled') acc.cancelled += 1;
      if ((family === 'pending' || family === 'confirmed') && !isTikTokPaymentFailedRow(row)) {
        acc.revenue += tiktokRowSalePrice(row);
        acc.fees += tiktokRowFees(row);
        acc.profit += tiktokRowProfit(row);
      }
      const buyer = tiktokBuyerKey(tiktokRowBuyer(row));
      if (buyer) acc.customers.add(buyer);
      return acc;
    }, { pending: 0, confirmed: 0, cancelled: 0, revenue: 0, fees: 0, profit: 0, customers: new Set() })
  ), [tiktokMatchedRows]);
  const realGoLiveHistory = useMemo(() => (
    (Array.isArray(goLiveHistory) ? goLiveHistory : []).filter((item) => item?.matchMode !== 'demo')
  ), [goLiveHistory]);
  const realLiveSequence = useMemo(() => (
    Math.max(
      0,
      ...realGoLiveHistory
        .map((item) => Number(item?.sequence || 0))
        .filter((value) => Number.isFinite(value)),
    )
  ), [realGoLiveHistory]);
  const activeTikTokSessionSequence = useMemo(() => {
    const current = Number(liveSequence || 0);
    if (isGoingLive && Number.isFinite(current) && current > 0) return current;
    const serverNext = Number(tiktokNextSequence || 0);
    if (Number.isFinite(serverNext) && serverNext > 0) return serverNext;
    const draft = Number(realLiveSequence || 0) + 1;
    return draft > 0 ? draft : 1;
  }, [isGoingLive, liveSequence, realLiveSequence, tiktokNextSequence]);
  const activePendingTikTokScans = useMemo(() => (
    tiktokDemoMode
      ? []
      :
    (Array.isArray(tiktokPendingScans) ? tiktokPendingScans : [])
      .filter((scan) => !goLiveSessionId || Number(scan?.sessionId || 0) === Number(goLiveSessionId))
  ), [goLiveSessionId, tiktokPendingScans, tiktokDemoMode]);
  const scannedTikTokRows = useMemo(() => (
    liveRows.filter((row) => isTikTokRowFilled(row))
  ), [liveRows]);
  const tiktokLastRowHasBarcode = isTikTokRowFilled(liveRows[liveRows.length - 1]);
  const tiktokEndArmed = isGoingLive && tiktokEndArmedUntil > Date.now();
  const activeTikTokProductQuery = String(
    Number(tiktokBarcodeDraft?.row) === Number(tiktokBarcodeSearchRow)
      ? tiktokBarcodeDraft.value
      : liveRows[Number(tiktokBarcodeSearchRow)]?.barcode || '',
  ).trim();
  const showTikTokProductCatalog = isGoingLive && isProductNameSearch(activeTikTokProductQuery, tiktokInventoryMap);
  const activeTikTokProductSuggestions = showTikTokProductCatalog ? tiktokProductSuggestions(activeTikTokProductQuery) : [];
  const tiktokSoldCountByProduct = useMemo(() => (
    tiktokMatchedRows.reduce((acc, row) => {
      if (!tiktokIsActivePaidSoldRow(row)) return acc;
      const key = tiktokProductKey(row);
      if (!key) return acc;
      acc.set(key, Number(acc.get(key) || 0) + 1);
      return acc;
    }, new Map())
  ), [tiktokMatchedRows]);
  const tiktokBuyerOrderCounts = useMemo(() => (
    tiktokMatchedRows.reduce((acc, row) => {
      if (!row?.tiktokOrder) return acc;
      const buyer = tiktokBuyerKey(tiktokRowBuyer(row));
      if (!buyer) return acc;
      const current = acc.get(buyer) || { paid: 0, cancelled: 0 };
      const family = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').trim().toLowerCase();
      if (family === 'cancelled') {
        current.cancelled += 1;
      } else if (tiktokIsActivePaidSoldRow(row)) {
        current.paid += 1;
      }
      acc.set(buyer, current);
      return acc;
    }, new Map())
  ), [tiktokMatchedRows]);
  const activeTikTokCatalogRows = useMemo(() => (
    activeTikTokProductSuggestions.map((product) => {
      const key = liveInventoryKey(product, productBarcode(product));
      const onHandQty = liveInventoryQty(product);
      const scannedInSession = Number(tiktokSessionScanCounts.get(key) || 0);
      const soldCount = Number(tiktokSoldCountByProduct.get(String(product?.id || productBarcode(product) || product?.name || '').trim().toLowerCase()) || 0);
      return {
        product,
        onHandQty,
        scannedInSession,
        remainingInSession: Math.max(0, onHandQty - scannedInSession),
        soldCount,
      };
    })
  ), [activeTikTokProductSuggestions, tiktokSessionScanCounts, tiktokSoldCountByProduct]);
  const selectedTikTokBuyerKey = tiktokBuyerKey(tiktokCustomerContext?.buyer);
  const selectedTikTokBuyerRows = useMemo(() => {
    if (!selectedTikTokBuyerKey) return [];
    return tiktokMatchedRows.filter((row) => tiktokBuyerKey(tiktokRowBuyer(row)) === selectedTikTokBuyerKey);
  }, [selectedTikTokBuyerKey, tiktokMatchedRows]);
  const selectedTikTokBuyerCancelledRows = useMemo(() => (
    selectedTikTokBuyerRows.filter((row) => String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').toLowerCase() === 'cancelled')
  ), [selectedTikTokBuyerRows]);
  const selectedTikTokBuyerPaymentFailedRows = useMemo(() => (
    selectedTikTokBuyerRows.filter((row) => isTikTokPaymentFailedRow(row))
  ), [selectedTikTokBuyerRows]);
  const selectedTikTokBuyerActiveRows = useMemo(() => (
    selectedTikTokBuyerRows.filter((row) => String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').toLowerCase() !== 'cancelled')
  ), [selectedTikTokBuyerRows]);
  const selectedTikTokBuyerTotal = selectedTikTokBuyerActiveRows.reduce((sum, row) => sum + Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0), 0);
  const selectedTikTokBuyerProfit = selectedTikTokBuyerActiveRows.reduce((sum, row) => sum + tiktokRowProfit(row), 0);
  const selectedTikTokCustomer = tiktokCustomerProfile?.customer || null;
  const selectedTikTokSummary = tiktokCustomerProfile?.summary || {};
  const selectedTikTokIdentities = Array.isArray(tiktokCustomerProfile?.identities)
    ? tiktokCustomerProfile.identities
    : (Array.isArray(selectedTikTokCustomer?.identities) ? selectedTikTokCustomer.identities : []);
  const selectedTikTokReturnRows = Array.isArray(tiktokCustomerProfile?.return_rows) ? tiktokCustomerProfile.return_rows : [];
  const selectedTikTokRecentProducts = Array.isArray(tiktokCustomerProfile?.recent_products) ? tiktokCustomerProfile.recent_products : [];
  const selectedTikTokCancelledProducts = Array.isArray(tiktokCustomerProfile?.cancelled_products) ? tiktokCustomerProfile.cancelled_products : [];
  const selectedTikTokAddress = String(
    selectedTikTokCustomer?.address
    || selectedTikTokIdentities
      .map((row) => [row?.address, row?.city, row?.state, row?.zip].filter(Boolean).join(', '))
      .find(Boolean)
    || ''
  ).trim();
  const selectedTikTokEmail = String(
    selectedTikTokCustomer?.email
    || selectedTikTokIdentities.find((row) => String(row?.email || '').trim())?.email
    || ''
  ).trim();
  const selectedTikTokPhone = String(
    selectedTikTokCustomer?.phone
    || selectedTikTokIdentities.find((row) => String(row?.phone || '').trim())?.phone
    || ''
  ).trim();
  const selectedTikTokCurrentProductNames = useMemo(() => (
    selectedTikTokBuyerRows
      .map((row) => row?.productName || row?.match?.name || '')
      .map((name) => shortDisplayProductName(name))
      .filter(Boolean)
  ), [selectedTikTokBuyerRows]);
  const selectedTikTokHistoricalProductNames = useMemo(() => {
    const names = [];
    (Array.isArray(tiktokCustomerOrders) ? tiktokCustomerOrders : []).forEach((order) => {
      (Array.isArray(order?.lines) ? order.lines : []).forEach((line) => {
        const name = shortDisplayProductName(
          line?.product_name
          || line?.name
          || line?.display_name
          || line?.product_display_name
          || '',
        );
        if (name) names.push(name);
      });
    });
    return names;
  }, [tiktokCustomerOrders]);
  const tiktokTopBuyerRows = useMemo(() => {
    const grouped = new Map();
    tiktokMatchedRows.forEach((row) => {
      if (!row?.tiktokOrder) return;
      const buyerLabel = row.tiktokOrder.buyerDisplay || row.tiktokOrder.buyerUsername || row.tiktokOrder.buyerName || row.buyer || '';
      const buyerKey = tiktokBuyerKey(buyerLabel);
      if (!buyerKey) return;
      const current = grouped.get(buyerKey) || {
        key: buyerKey,
        buyer: buyerLabel,
        total: 0,
        lots: 0,
      };
      current.total += Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0);
      current.lots += 1;
      grouped.set(buyerKey, current);
    });
    return Array.from(grouped.values())
      .sort((left, right) => {
        if (right.total !== left.total) return right.total - left.total;
        return right.lots - left.lots;
      })
      .slice(0, 5);
  }, [tiktokMatchedRows]);
  const tiktokAvgSale = useMemo(() => {
    const saleRows = tiktokMatchedRows.filter((row) => row?.tiktokOrder && Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0) > 0);
    if (!saleRows.length) return 0;
    return saleRows.reduce((sum, row) => sum + Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0), 0) / saleRows.length;
  }, [tiktokMatchedRows]);
  const tiktokCog = useMemo(() => (
    tiktokMatchedRows.reduce((sum, row) => {
      if (!row?.tiktokOrder) return sum;
      if (String(row?.statusFamily || '').toLowerCase() === 'cancelled') return sum;
      return sum + Number(row?.cost || row?.match?.cost_price || 0);
    }, 0)
  ), [tiktokMatchedRows]);
  const tiktokCurrentLot = useMemo(() => (
    scannedTikTokRows.reduce((highest, row) => Math.max(highest, tiktokLotNumber(row?.lotNo)), 0)
  ), [scannedTikTokRows]);
  const tiktokBatchGuard = useMemo(() => {
    const guards = tiktokMatchedRows
      .map((row) => row?.tiktokBatchGuard)
      .filter(Boolean);
    return guards.find((guard) => guard?.blocking)
      || guards.find((guard) => guard?.detectedBatch)
      || guards[0]
      || null;
  }, [tiktokMatchedRows]);
  const tiktokExpectedBatch = Number(tiktokBatchGuard?.expectedBatch || tiktokExpectedBatchForLot(tiktokCurrentLot || 1));
  const tiktokExpectedBatchRange = String(tiktokBatchGuard?.expectedRange || tiktokBatchRangeLabel(tiktokExpectedBatch));
  const tiktokDetectedBatch = Number(tiktokBatchGuard?.detectedBatch || 0);
  const tiktokEffectiveBatch = Number(tiktokBatchGuard?.effectiveBatch || tiktokDetectedBatch || 0);
  const tiktokEffectiveBatchRange = String(tiktokBatchGuard?.effectiveRange || (tiktokEffectiveBatch ? tiktokBatchRangeLabel(tiktokEffectiveBatch) : '—'));
  const tiktokBatchBlocking = Boolean(tiktokBatchGuard?.blocking);
  const tiktokBatchOverrideActive = Boolean(tiktokBatchGuard?.overrideActive);
  const tiktokBatchStatusLabel = tiktokBatchBlocking
    ? 'Blocked'
    : tiktokBatchOverrideActive
      ? 'Override active'
      : tiktokDetectedBatch === tiktokExpectedBatch
      ? 'Matched'
      : tiktokDetectedBatch
        ? 'Waiting'
        : 'No orders yet';
  const tiktokCurrentSnapshot = useMemo(() => (
    tiktokSessionSnapshot(tiktokMatchedRows, tiktokCurrentLot || Infinity)
  ), [tiktokMatchedRows, tiktokCurrentLot]);
  const tiktokEndedHistorySessions = useMemo(() => (
    realGoLiveHistory.filter((sessionRow) => {
      const status = String(sessionRow?.status || '').trim().toLowerCase();
      if (!['ended', 'closed', 'archived'].includes(status)) return false;
      if (Number(sessionRow?.sequence || 0) === Number(activeTikTokSessionSequence || 0)) return false;
      return Array.isArray(sessionRow?.rows) && sessionRow.rows.length > 0;
    })
  ), [realGoLiveHistory, activeTikTokSessionSequence]);
  const tiktokSessionComparisons = useMemo(() => (
    tiktokEndedHistorySessions.map((sessionRow) => {
      const atCurrentLot = tiktokSessionSnapshot(sessionRow.rows, tiktokCurrentLot || Infinity);
      const finalSnapshot = tiktokSessionSnapshot(sessionRow.rows, Infinity);
      return {
        session: sessionRow,
        atCurrentLot,
        finalSnapshot,
      };
    }).filter((entry) => entry.atCurrentLot.lastLot > 0)
  ), [tiktokEndedHistorySessions, tiktokCurrentLot]);
  const tiktokPredictedProfit = useMemo(() => {
    if (tiktokCurrentSnapshot.profit <= 0) return 0;
    const multipliers = tiktokSessionComparisons
      .map((entry) => {
        const progressProfit = Number(entry?.atCurrentLot?.profit || 0);
        const finalProfit = Number(entry?.finalSnapshot?.profit || 0);
        if (progressProfit <= 0 || finalProfit <= 0) return 0;
        return finalProfit / progressProfit;
      })
      .filter((value) => Number.isFinite(value) && value > 0);
    if (multipliers.length) {
      const averageMultiplier = multipliers.reduce((sum, value) => sum + value, 0) / multipliers.length;
      return tiktokCurrentSnapshot.profit * averageMultiplier;
    }
    const finalLotCounts = tiktokSessionComparisons
      .map((entry) => Number(entry?.finalSnapshot?.lastLot || 0))
      .filter((value) => value > 0);
    if (!finalLotCounts.length || !tiktokCurrentLot) return tiktokCurrentSnapshot.profit;
    const avgFinalLots = finalLotCounts.reduce((sum, value) => sum + value, 0) / finalLotCounts.length;
    return (tiktokCurrentSnapshot.profit / tiktokCurrentLot) * avgFinalLots;
  }, [tiktokCurrentSnapshot.profit, tiktokCurrentLot, tiktokSessionComparisons]);
  const tiktokCurrentProfitPct = useMemo(() => {
    if (tiktokCog <= 0) return 0;
    return (Number(tiktokLiveSummary.profit || 0) / tiktokCog) * 100;
  }, [tiktokLiveSummary.profit, tiktokCog]);
  const tiktokPositionBenchmark = useMemo(() => {
    const revenueBaseline = averageNumber(tiktokSessionComparisons.map((entry) => entry?.atCurrentLot?.revenue).filter((value) => Number(value || 0) > 0));
    const profitBaseline = averageNumber(tiktokSessionComparisons.map((entry) => entry?.atCurrentLot?.profit).filter((value) => Number(value || 0) > 0));
    const soldLotsBaseline = averageNumber(tiktokSessionComparisons.map((entry) => entry?.atCurrentLot?.soldLots).filter((value) => Number(value || 0) > 0));
    const cancelledLotsBaseline = averageNumber(tiktokSessionComparisons.map((entry) => entry?.atCurrentLot?.cancelledLots));
    const avgSaleBaseline = averageNumber(tiktokSessionComparisons.map((entry) => {
      const soldLots = Number(entry?.atCurrentLot?.soldLots || 0);
      return soldLots > 0 ? Number(entry?.atCurrentLot?.revenue || 0) / soldLots : 0;
    }).filter((value) => value > 0));
    const paceBaseline = averageNumber(tiktokSessionComparisons.map((entry) => {
      const startedAt = parseTikTokTime(entry?.session?.startedAt);
      const lastEventTs = Number(entry?.atCurrentLot?.lastEventTs || 0);
      if (!startedAt || !lastEventTs || lastEventTs <= startedAt || !tiktokCurrentLot) return 0;
      return tiktokCurrentLot / ((lastEventTs - startedAt) / 1000);
    }).filter((value) => value > 0));
    const currentStartedAt = parseTikTokTime(tiktokActiveSessionMeta?.startedAt);
    const currentLastEventTs = Number(tiktokCurrentSnapshot.lastEventTs || 0);
    const currentPace = currentStartedAt && currentLastEventTs > currentStartedAt && tiktokCurrentLot
      ? tiktokCurrentLot / ((currentLastEventTs - currentStartedAt) / 1000)
      : 0;
    const currentAvgSale = tiktokCurrentSnapshot.soldLots > 0
      ? tiktokCurrentSnapshot.revenue / tiktokCurrentSnapshot.soldLots
      : 0;
    return {
      historyCount: tiktokSessionComparisons.length,
      revenueBaseline,
      profitBaseline,
      soldLotsBaseline,
      cancelledLotsBaseline,
      avgSaleBaseline,
      paceBaseline,
      currentPace,
      currentAvgSale,
      revenueDelta: pctDelta(tiktokCurrentSnapshot.revenue, revenueBaseline),
      profitDelta: pctDelta(tiktokCurrentSnapshot.profit, profitBaseline),
      soldLotsDelta: pctDelta(tiktokCurrentSnapshot.soldLots, soldLotsBaseline),
      avgSaleDelta: pctDelta(currentAvgSale, avgSaleBaseline),
      paceDelta: pctDelta(currentPace, paceBaseline),
      cancelDelta: pctDelta(tiktokCurrentSnapshot.cancelledLots, cancelledLotsBaseline),
    };
  }, [
    tiktokActiveSessionMeta?.startedAt,
    tiktokCurrentLot,
    tiktokCurrentSnapshot.cancelledLots,
    tiktokCurrentSnapshot.lastEventTs,
    tiktokCurrentSnapshot.profit,
    tiktokCurrentSnapshot.revenue,
    tiktokCurrentSnapshot.soldLots,
    tiktokSessionComparisons,
  ]);
  const tiktokMarketSignal = useMemo(() => {
    if (!tiktokCurrentLot) {
      return {
        label: 'Warming Up',
        sub: 'Scan the first sold lot to start the show comparison.',
        tone: '#475569',
        bg: '#f8fafc',
        border: '#e2e8f0',
      };
    }
    if (tiktokPositionBenchmark.historyCount < 2) {
      return {
        label: 'Need History',
        sub: 'Need at least two completed shows with matching lot progress.',
        tone: '#475569',
        bg: '#f8fafc',
        border: '#e2e8f0',
      };
    }
    const profitDelta = Number(tiktokPositionBenchmark.profitDelta || 0);
    const revenueDelta = Number(tiktokPositionBenchmark.revenueDelta || 0);
    const orderDelta = Number(tiktokPositionBenchmark.soldLotsDelta || 0);
    const paceDelta = tiktokPositionBenchmark.paceDelta;
    const averageSignal = averageNumber([profitDelta, revenueDelta, orderDelta]);
    if (profitDelta <= -20 || revenueDelta <= -20) {
      return {
        label: 'Bearish',
        sub: `Behind previous shows at lot ${tiktokCurrentLot}. Push stronger lots or tighten pricing.`,
        tone: '#b91c1c',
        bg: '#fff1f2',
        border: '#fecaca',
      };
    }
    if (paceDelta != null && paceDelta <= -20) {
      return {
        label: 'Slow Down',
        sub: 'Selling pace is slower than previous shows at this position.',
        tone: '#b45309',
        bg: '#fff7ed',
        border: '#fdba74',
      };
    }
    if (profitDelta >= 20 && revenueDelta >= 10) {
      return {
        label: 'Bullish',
        sub: `Profit and revenue are ahead of prior shows at lot ${tiktokCurrentLot}.`,
        tone: '#047857',
        bg: '#ecfdf3',
        border: '#86efac',
      };
    }
    if (paceDelta != null && paceDelta >= 20) {
      return {
        label: 'Speeding Up',
        sub: 'Orders are coming in faster than the historical pace.',
        tone: '#2563eb',
        bg: '#eff6ff',
        border: '#bfdbfe',
      };
    }
    if (averageSignal >= 8) {
      return {
        label: 'Doing Great',
        sub: 'Current position is modestly ahead of previous streams.',
        tone: '#047857',
        bg: '#ecfdf3',
        border: '#86efac',
      };
    }
    if (averageSignal <= -8) {
      return {
        label: 'Watch Pace',
        sub: 'Current stream is drifting below previous performance.',
        tone: '#b45309',
        bg: '#fff7ed',
        border: '#fdba74',
      };
    }
    return {
      label: 'Steady',
      sub: 'Performance is close to the previous show average at this position.',
      tone: '#2563eb',
      bg: '#eff6ff',
      border: '#bfdbfe',
    };
  }, [tiktokCurrentLot, tiktokPositionBenchmark]);
  const tiktokComparisonCards = useMemo(() => {
    const deltaTone = (delta, invert = false) => {
      if (delta == null) return 'var(--text-secondary)';
      const favorable = invert ? delta <= 0 : delta >= 0;
      return favorable ? '#047857' : '#b91c1c';
    };
    const cards = [
      {
        label: 'Position check',
        value: tiktokCurrentLot ? `Lot ${tiktokCurrentLot}` : 'Not started',
        detail: tiktokCurrentLot
          ? `${tiktokPositionBenchmark.historyCount} prior shows compared`
          : 'Scan sold lots to compare live progress',
        tone: tiktokCurrentLot ? '#2563eb' : 'var(--text-secondary)',
      },
      {
        label: 'Revenue vs history',
        value: signedDeltaLabel(tiktokPositionBenchmark.revenueDelta),
        detail: `${fmt$(tiktokCurrentSnapshot.revenue)} now · avg ${fmt$(tiktokPositionBenchmark.revenueBaseline)}`,
        tone: deltaTone(tiktokPositionBenchmark.revenueDelta),
      },
      {
        label: 'Profit vs history',
        value: signedDeltaLabel(tiktokPositionBenchmark.profitDelta),
        detail: `${fmt$(tiktokCurrentSnapshot.profit)} now · avg ${fmt$(tiktokPositionBenchmark.profitBaseline)}`,
        tone: deltaTone(tiktokPositionBenchmark.profitDelta),
      },
      {
        label: 'Orders vs history',
        value: signedDeltaLabel(tiktokPositionBenchmark.soldLotsDelta),
        detail: `${tiktokCurrentSnapshot.soldLots} orders · avg ${tiktokPositionBenchmark.soldLotsBaseline.toFixed(1)}`,
        tone: deltaTone(tiktokPositionBenchmark.soldLotsDelta),
      },
      {
        label: 'Average sale',
        value: signedDeltaLabel(tiktokPositionBenchmark.avgSaleDelta),
        detail: `${fmt$(tiktokPositionBenchmark.currentAvgSale)} now · avg ${fmt$(tiktokPositionBenchmark.avgSaleBaseline)}`,
        tone: deltaTone(tiktokPositionBenchmark.avgSaleDelta),
      },
      {
        label: 'Selling pace',
        value: signedDeltaLabel(tiktokPositionBenchmark.paceDelta, 'Faster', 'Slower'),
        detail: tiktokPositionBenchmark.currentPace > 0
          ? `${(tiktokPositionBenchmark.currentPace * 60).toFixed(1)} lots/min`
          : 'Waiting for live timestamps',
        tone: tiktokPositionBenchmark.paceDelta == null ? 'var(--text-secondary)' : (tiktokPositionBenchmark.paceDelta >= 0 ? '#2563eb' : '#b45309'),
      },
      {
        label: 'Cancel risk',
        value: tiktokPositionBenchmark.cancelDelta == null
          ? `${tiktokCurrentSnapshot.cancelledLots} cancelled`
          : signedDeltaLabel(tiktokPositionBenchmark.cancelDelta, 'Higher', 'Lower'),
        detail: `${tiktokCurrentSnapshot.cancelledLots} now · avg ${tiktokPositionBenchmark.cancelledLotsBaseline.toFixed(1)}`,
        tone: deltaTone(tiktokPositionBenchmark.cancelDelta, true),
      },
      {
        label: 'Predicted profit',
        value: fmt$(tiktokPredictedProfit),
        detail: tiktokPositionBenchmark.profitBaseline > 0 ? 'Projected from prior show curves' : 'Uses current progress',
        tone: Number(tiktokPredictedProfit) < 0 ? '#b91c1c' : '#059669',
      },
      {
        label: 'Profit %',
        value: tiktokCog > 0 ? fmtPct(tiktokCurrentProfitPct) : '0.0%',
        detail: `${fmt$(tiktokCog)} COG tracked`,
        tone: tiktokCurrentProfitPct < 0 ? '#b91c1c' : '#2563eb',
      },
    ];
    return cards;
  }, [
    tiktokCog,
    tiktokCurrentLot,
    tiktokCurrentProfitPct,
    tiktokCurrentSnapshot.cancelledLots,
    tiktokCurrentSnapshot.profit,
    tiktokCurrentSnapshot.revenue,
    tiktokCurrentSnapshot.soldLots,
    tiktokPositionBenchmark,
    tiktokPredictedProfit,
  ]);
  const tiktokRecentSoldRows = useMemo(() => (
    tiktokDisplayRows
      .filter((row) => row?.tiktokOrder)
      .slice(0, 6)
  ), [tiktokDisplayRows]);

  const tiktokAiSuggestions = useMemo(() => {
    const soldNames = tiktokRecentSoldRows
      .map((row) => String(row.productName || row.match?.name || '').toLowerCase())
      .filter(Boolean);
    if (!soldNames.length) return [];
    const termFreq = new Map();
    soldNames.forEach((name) => {
      name.split(/[\s,/|()\-]+/).filter((t) => t.length > 2 && !SUGGEST_NOISE.has(t)).forEach((term) => {
        termFreq.set(term, (termFreq.get(term) || 0) + 1);
      });
    });
    const topTerms = [...termFreq.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([term]) => term);
    if (!topTerms.length) return [];
    const scannedBarcodes = new Set(
      tiktokMatchedRows
        .filter((row) => String(row.barcode || '').trim())
        .map((row) => String(row.barcode || '').trim().toLowerCase()),
    );
    return liveInventory
      .filter((product) => {
        const name = String(product.name || '').toLowerCase();
        if (AL_REHAB_RE.test(name)) return false;
        if (liveInventoryQty(product) <= 0) return false;
        const bc = productBarcode(product)?.toLowerCase();
        if (bc && scannedBarcodes.has(bc)) return false;
        return true;
      })
      .map((product) => {
        const name = String(product.name || '').toLowerCase();
        const score = topTerms.reduce((s, term) => s + (name.includes(term) ? 1 : 0), 0);
        return { product, score };
      })
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score || liveInventoryQty(b.product) - liveInventoryQty(a.product))
      .slice(0, 4)
      .map(({ product }) => product);
  }, [liveInventory, tiktokRecentSoldRows, tiktokMatchedRows]);
  const tiktokInventorySearchResults = useMemo(() => {
    const query = String(tiktokInventorySearch || '').trim().toLowerCase();
    if (!query) return [];
    return tiktokProductSearchRows
      .map(({ product }) => ({ product, score: productSearchScore(product, query) }))
      .filter(({ score }) => score > 0)
      .sort((a, b) => b.score - a.score || liveInventoryQty(b.product) - liveInventoryQty(a.product) || String(a.product?.name || '').localeCompare(String(b.product?.name || '')))
      .slice(0, 8)
      .map(({ product }) => {
        const key = liveInventoryKey(product, productBarcode(product));
        const onHandQty = liveInventoryQty(product);
        const scannedInSession = Number(tiktokSessionScanCounts.get(key) || 0);
        const soldCount = Number(tiktokSoldCountByProduct.get(String(product?.id || productBarcode(product) || product?.name || '').trim().toLowerCase()) || 0);
        return {
          product,
          onHandQty,
          scannedInSession,
          remainingInSession: Math.max(0, onHandQty - scannedInSession),
          soldCount,
        };
      });
  }, [liveInventory, tiktokInventorySearch, tiktokProductSearchRows, tiktokSessionScanCounts, tiktokSoldCountByProduct]);

  const tiktokProductPreview = useMemo(() => {
    const inspectedKey = String(tiktokInspectedProduct?.id || tiktokInspectedProduct?.barcode || tiktokInspectedProduct?.default_code || tiktokInspectedProduct?.sku || '').trim().toLowerCase();
	    if (inspectedKey) {
	      const current = liveInventory.find((product) => (
	        String(product?.id || '').trim().toLowerCase() === inspectedKey
	        || String(product?.barcode || '').trim().toLowerCase() === inspectedKey
	        || String(product?.default_code || product?.sku || '').trim().toLowerCase() === inspectedKey
	      ));
	      if (current) return current;
	      return tiktokInspectedProduct;
	    }
    if (showTikTokProductCatalog && activeTikTokProductSuggestions[0]) return activeTikTokProductSuggestions[0];
	    if (tiktokInventorySearchResults[0]?.product) return tiktokInventorySearchResults[0].product;
	    const row = liveRows[Number(tiktokBarcodeSearchRow)] || null;
	    return row?.match || null;
	  }, [activeTikTokProductSuggestions, liveInventory, liveRows, showTikTokProductCatalog, tiktokBarcodeSearchRow, tiktokInspectedProduct, tiktokInventorySearchResults]);

  const tiktokProductPreviewStats = useMemo(() => {
    if (!tiktokProductPreview) return null;
    const key = liveInventoryKey(tiktokProductPreview, productBarcode(tiktokProductPreview));
    const onHandQty = liveInventoryQty(tiktokProductPreview);
    const scannedInSession = Number(tiktokSessionScanCounts.get(key) || 0);
    const soldCount = Number(tiktokSoldCountByProduct.get(String(tiktokProductPreview?.id || productBarcode(tiktokProductPreview) || tiktokProductPreview?.name || '').trim().toLowerCase()) || 0);
    return {
      onHandQty,
      scannedInSession,
      remainingInSession: Math.max(0, onHandQty - scannedInSession),
      soldCount,
    };
  }, [tiktokProductPreview, tiktokSessionScanCounts, tiktokSoldCountByProduct]);
  const tiktokProductClipboardText = useMemo(() => (
    tiktokProductPreview ? compactProductClipboardText(tiktokProductPreview) : ''
  ), [tiktokProductPreview]);

  useEffect(() => {
    if (platform !== 'tiktok' || !isGoingLive || !tiktokMatchedRows.length) return;
    if (typeof document !== 'undefined' && document.activeElement?.dataset?.manualInput === 'true') return;

    const syncedRow = [...tiktokMatchedRows]
      .filter((row) => isTikTokRowFilled(row))
      .sort((left, right) => tiktokLotNumber(right?.lotNo) - tiktokLotNumber(left?.lotNo))[0];
    if (!syncedRow) return;

    const rowQuery = String(syncedRow?.barcode || syncedRow?.productName || '').trim();
    let product = syncedRow?.match || null;
    if (!product && rowQuery) {
      product = tiktokInventoryMap.get(rowQuery.toLowerCase()) || tiktokProductSuggestions(rowQuery)[0] || null;
    }
    if (!product) return;

    const productKey = String(product?.id || productBarcode(product) || product?.name || '').trim();
    const previewKey = `${Number(goLiveSessionId || 0)}:${String(syncedRow?.lotNo || '')}:${productKey}:${rowQuery}`;
    if (!productKey || tiktokLastRemotePreviewRef.current === previewKey) return;

    tiktokLastRemotePreviewRef.current = previewKey;
    setTikTokInspectedProduct(product);
  }, [goLiveSessionId, isGoingLive, platform, tiktokInventoryMap, tiktokMatchedRows]);

  async function copyTikTokProductNotes() {
    const text = compactProductClipboardText(tiktokProductPreview);
    if (!text) {
      showFeedback('No fragrance notes or dupe info to copy for this product.', 'error');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setTikTokCopiedProductNote(true);
      window.setTimeout(() => setTikTokCopiedProductNote(false), 1200);
    } catch {
      showFeedback('Could not copy product notes on this device.', 'error');
    }
  }

  const tiktokRevenueRows = useMemo(() => {
    const soldRows = tiktokMatchedRows.filter((row) => tiktokIsActivePaidSoldRow(row));
    return soldRows.map((row) => {
      const productKey = tiktokProductKey(row);
      return {
        lotNo: row?.lotNo || '—',
        barcode: row?.barcode || '',
        productName: shortDisplayProductName(row?.productName || row?.match?.name || 'Unknown product'),
        cost: tiktokRowCost(row),
        retail: Number(row?.match?.price || row?.match?.retail_price || row?.retailPrice || 0),
        salePrice: tiktokRowSalePrice(row),
        profit: tiktokRowProfit(row),
        customer: tiktokRowBuyer(row) || '—',
        soldCount: Number(tiktokSoldCountByProduct.get(productKey) || 1),
        soldAt: row?.tiktokOrder?.soldAt || '',
        orderId: row?.tiktokOrder?.orderId || row?.orderId || '',
      };
    });
  }, [tiktokMatchedRows, tiktokSoldCountByProduct]);

  const tiktokProfitRows = useMemo(() => {
    const grouped = tiktokRevenueRows.reduce((acc, row) => {
      const key = String(row?.barcode || row?.productName || '').trim().toLowerCase();
      if (!key) return acc;
      const current = acc.get(key) || {
        key,
        productName: row.productName,
        barcode: row.barcode,
        totalProfit: 0,
        totalRevenue: 0,
        totalCost: 0,
        soldCount: 0,
        topCustomer: row.customer,
      };
      current.totalProfit += Number(row.profit || 0);
      current.totalRevenue += Number(row.salePrice || 0);
      current.totalCost += Number(row.cost || 0);
      current.soldCount += 1;
      if (!current.topCustomer) current.topCustomer = row.customer;
      acc.set(key, current);
      return acc;
    }, new Map());
    return Array.from(grouped.values()).sort((left, right) => {
      if (right.totalProfit !== left.totalProfit) return right.totalProfit - left.totalProfit;
      return right.soldCount - left.soldCount;
    });
  }, [tiktokRevenueRows]);

  const tiktokMostSoldProducts = useMemo(() => (
    [...tiktokProfitRows]
      .sort((left, right) => {
        if (right.soldCount !== left.soldCount) return right.soldCount - left.soldCount;
        return right.totalRevenue - left.totalRevenue;
      })
      .slice(0, 5)
  ), [tiktokProfitRows]);

  const tiktokLossProductRows = useMemo(() => (
    [...tiktokProfitRows]
      .filter((row) => Number(row.totalProfit || 0) < 0)
      .sort((left, right) => left.totalProfit - right.totalProfit)
      .slice(0, 5)
  ), [tiktokProfitRows]);

  const tiktokOrderRows = useMemo(() => (
    tiktokMatchedRows
      .filter((row) => row?.tiktokOrder)
      .map((row) => ({
        lotNo: row?.lotNo || '—',
        customer: tiktokRowBuyer(row) || '—',
        productName: shortDisplayProductName(row?.productName || row?.match?.name || 'Unknown product'),
        orderId: row?.tiktokOrder?.orderId || row?.orderId || '',
        salePrice: Number(row?.tiktokOrder?.salePrice || row?.salesPrice || 0),
        profit: tiktokRowProfit(row),
        statusFamily: String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').toLowerCase() || 'pending',
        statusLabel: row?.statusLabel || row?.tiktokOrder?.statusLabel || 'Pending',
        soldAt: row?.tiktokOrder?.soldAt || '',
        rawRow: row,
      }))
      .sort((left, right) => {
        const leftLot = Number.parseInt(String(left.lotNo || '0'), 10);
        const rightLot = Number.parseInt(String(right.lotNo || '0'), 10);
        return rightLot - leftLot;
      })
  ), [tiktokMatchedRows]);

  const selectedTikTokTasteSuggestions = useMemo(() => {
    if (!selectedTikTokBuyerKey) return [];
    const currentNames = selectedTikTokCurrentProductNames;
    const historicalNames = selectedTikTokHistoricalProductNames;
    const purchasedNames = [...currentNames, ...historicalNames];
    if (!purchasedNames.length) return [];

    const purchasedNameSet = new Set(purchasedNames.map(normalizeTasteProductName));
    const streamTermFreq = tiktokRevenueRows.reduce((acc, row) => {
      extractTasteTerms(row.productName).forEach((term) => {
        acc.set(term, Number(acc.get(term) || 0) + 1);
      });
      return acc;
    }, new Map());
    const tasteTermFreq = new Map();
    historicalNames.forEach((name) => {
      extractTasteTerms(name).forEach((term) => {
        tasteTermFreq.set(term, Number(tasteTermFreq.get(term) || 0) + 2);
      });
    });
    currentNames.forEach((name) => {
      extractTasteTerms(name).forEach((term) => {
        tasteTermFreq.set(term, Number(tasteTermFreq.get(term) || 0) + 5);
      });
    });
    if (!tasteTermFreq.size) return [];

    const scannedBarcodes = new Set(
      tiktokMatchedRows
        .filter((row) => String(row?.barcode || '').trim())
        .map((row) => String(row?.barcode || '').trim().toLowerCase()),
    );

    return liveInventory
      .filter((product) => {
        const name = shortDisplayProductName(product?.name || '');
        if (!name) return false;
        if (AL_REHAB_RE.test(name)) return false;
        if (liveInventoryQty(product) <= 0) return false;
        const normalized = normalizeTasteProductName(name);
        if (purchasedNameSet.has(normalized)) return false;
        const barcode = productBarcode(product)?.toLowerCase();
        if (barcode && scannedBarcodes.has(barcode)) return false;
        return true;
      })
      .map((product) => {
        const displayName = shortDisplayProductName(product.name);
        const terms = extractTasteTerms(displayName);
        const tasteScore = terms.reduce((sum, term) => sum + Number(tasteTermFreq.get(term) || 0), 0);
        const streamScore = terms.reduce((sum, term) => sum + Number(streamTermFreq.get(term) || 0), 0);
        const overlap = terms.filter((term) => tasteTermFreq.has(term));
        const score = (tasteScore * 3) + streamScore + overlap.length + Math.min(3, liveInventoryQty(product) / 2);
        return {
          product,
          score,
          overlap,
          reason: overlap.slice(0, 3).join(', '),
        };
      })
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score || liveInventoryQty(right.product) - liveInventoryQty(left.product))
      .slice(0, 6);
  }, [liveInventory, selectedTikTokBuyerKey, selectedTikTokCurrentProductNames, selectedTikTokHistoricalProductNames, tiktokMatchedRows, tiktokRevenueRows]);

  const tiktokCancelledRows = useMemo(() => (
    tiktokOrderRows.filter((row) => row.statusFamily === 'cancelled')
  ), [tiktokOrderRows]);
  const tiktokPaymentFailedRows = useMemo(() => (
    tiktokOrderRows.filter((row) => isTikTokPaymentFailedRow(row.rawRow))
  ), [tiktokOrderRows]);

  const tiktokCustomerRoster = useMemo(() => {
    const grouped = tiktokOrderRows.reduce((acc, row) => {
      const key = tiktokBuyerKey(row.customer);
      if (!key) return acc;
      const current = acc.get(key) || {
        key,
        buyer: row.customer,
        liveOrders: 0,
        cancelled: 0,
        paymentFailed: 0,
        revenue: 0,
        profit: 0,
        products: new Set(),
      };
      current.liveOrders += 1;
      const isPaymentFailed = isTikTokPaymentFailedRow(row.rawRow);
      if (isPaymentFailed) current.paymentFailed += 1;
      if (row.statusFamily === 'cancelled') current.cancelled += 1;
      if (row.statusFamily !== 'cancelled' && !isPaymentFailed) {
        current.revenue += Number(row.salePrice || 0);
        current.profit += Number(row.profit || 0);
      }
      current.products.add(row.productName);
      acc.set(key, current);
      return acc;
    }, new Map());
    return Array.from(grouped.values())
      .map((entry) => ({
        ...entry,
        cancelledRate: entry.liveOrders ? entry.cancelled / entry.liveOrders : 0,
        paymentFailedRate: entry.liveOrders ? entry.paymentFailed / entry.liveOrders : 0,
        products: Array.from(entry.products).slice(0, 3),
      }))
      .sort((left, right) => {
        if (right.liveOrders !== left.liveOrders) return right.liveOrders - left.liveOrders;
        return right.revenue - left.revenue;
      });
  }, [tiktokOrderRows]);
  const tiktokTopCustomerRows = useMemo(() => (
    [...tiktokCustomerRoster]
      .sort((left, right) => {
        if (right.revenue !== left.revenue) return right.revenue - left.revenue;
        if (right.profit !== left.profit) return right.profit - left.profit;
        return right.liveOrders - left.liveOrders;
      })
      .slice(0, 5)
  ), [tiktokCustomerRoster]);
  const tiktokCustomerLookupRows = useMemo(() => {
    const query = String(tiktokCustomerLookup || '').trim().toLowerCase();
    if (!query) return tiktokTopCustomerRows.slice(0, 4);
    const terms = query.split(/\s+/).filter(Boolean);
    return tiktokCustomerRoster
      .filter((row) => {
        const text = [
          row.buyer,
          ...(Array.isArray(row.products) ? row.products : []),
        ].filter(Boolean).join(' ').toLowerCase();
        return terms.every((term) => text.includes(term));
      })
      .slice(0, 6);
  }, [tiktokCustomerLookup, tiktokCustomerRoster, tiktokTopCustomerRows]);
  const tiktokAbuseRiskRows = useMemo(() => (
    tiktokCustomerRoster
      .filter((row) => row.cancelled > 0 || row.paymentFailed > 0)
      .sort((left, right) => (
        (right.paymentFailed - left.paymentFailed)
        || (right.cancelled - left.cancelled)
        || (right.paymentFailedRate - left.paymentFailedRate)
        || (right.cancelledRate - left.cancelledRate)
        || (right.liveOrders - left.liveOrders)
      ))
      .slice(0, 6)
  ), [tiktokCustomerRoster]);

  const tiktokNeedsAttentionRows = useMemo(() => {
    const rows = [];
    if (tiktokBatchBlocking) {
      rows.push({
        type: 'Batch guard',
        lotNo: tiktokCurrentLot ? `B${tiktokExpectedBatch} ${tiktokExpectedBatchRange}` : '—',
        barcode: '',
        detail: tiktokBatchGuard?.message || `Expected B${tiktokExpectedBatch}, detected B${tiktokDetectedBatch || '—'}.`,
        severity: 'critical',
      });
    }
    tiktokMatchedRows.forEach((row) => {
      const hasBarcode = Boolean(String(row?.barcode || '').trim());
      const hasMappedProduct = Boolean(row?.match || row?.productName);
      const hasBuyer = Boolean(tiktokRowBuyer(row));
      if (hasBarcode && !hasMappedProduct) {
        rows.push({
          type: 'Inventory match',
          lotNo: row?.lotNo || '—',
          barcode: row?.barcode || '',
          detail: 'No inventory product matched this barcode.',
          severity: 'warning',
        });
      } else if (hasMappedProduct && !hasBuyer && String(row?.statusFamily || '').toLowerCase() !== 'cancelled') {
        rows.push({
          type: 'Buyer sync',
          lotNo: row?.lotNo || '—',
          barcode: row?.barcode || '',
          detail: shortDisplayProductName(row?.productName || row?.match?.name || 'Buyer pending'),
          severity: 'info',
        });
      }
    });
    activePendingTikTokScans.forEach((scan) => {
      rows.push({
        type: 'Pending save',
        lotNo: scan?.lotNo || '—',
        barcode: scan?.barcode || '',
        detail: 'Saved locally and waiting to sync to the live session.',
        severity: 'info',
      });
    });
    return rows;
  }, [activePendingTikTokScans, tiktokBatchBlocking, tiktokBatchGuard, tiktokCurrentLot, tiktokDetectedBatch, tiktokExpectedBatch, tiktokExpectedBatchRange, tiktokMatchedRows]);

  const tiktokKpiTabs = useMemo(() => ([
    { key: 'revenue', label: 'Revenue', count: tiktokRevenueRows.length },
    { key: 'profit', label: 'Profit', count: tiktokProfitRows.length },
    { key: 'orders', label: 'Orders', count: tiktokOrderRows.length },
    { key: 'cancelled', label: 'Cancelled', count: tiktokCancelledRows.length },
    { key: 'customers', label: 'Customers', count: tiktokCustomerRoster.length },
    { key: 'needs_attention', label: 'Needs Attention', count: tiktokNeedsAttentionRows.length },
  ]), [tiktokCancelledRows.length, tiktokCustomerRoster.length, tiktokNeedsAttentionRows.length, tiktokOrderRows.length, tiktokProfitRows.length, tiktokRevenueRows.length]);

  function openTikTokCustomerContext(row) {
    const buyer = tiktokRowBuyer(row);
    if (!buyer) return;
    setTikTokCustomerContext({
      buyer,
      username: cleanTikTokBuyer(row?.tiktokOrder?.buyerUsername || row?.buyer_username || buyer),
      orderId: row?.tiktokOrder?.orderId || row?.orderId || '',
      lotNo: row?.lotNo || '',
    });
  }

  useEffect(() => {
    if (!tiktokCustomerContext?.buyer) {
      setTikTokCustomerProfile(null);
      setTikTokCustomerOrders([]);
      setTikTokCustomerOrderLinesById({});
      return;
    }
    let cancelled = false;
    const q = tiktokCustomerContext.username || tiktokCustomerContext.buyer;
    const params = new URLSearchParams({ scope: 'company', summary: '1', limit: '12', source: 'tiktok', q });
    setTikTokCustomerLoading(true);
    Promise.all([
      fetchApi(`/api/customers/profile_lookup?username=${encodeURIComponent(q)}`).catch(() => null),
      fetchApi(`/api/sale_orders?${params.toString()}`).catch(() => null),
    ])
      .then(async ([profileData, orderData]) => {
        if (cancelled) return;
        if (profileData?.ok) {
          setTikTokCustomerProfile(profileData);
        } else {
          setTikTokCustomerProfile(null);
        }
        const key = tiktokBuyerKey(tiktokCustomerContext.username || tiktokCustomerContext.buyer);
        const profileOrders = (profileData?.orders || []).filter((order) => String(order.order_source || '').toLowerCase().startsWith('tiktok'));
        const rows = [...profileOrders, ...((orderData?.rows || []))].filter((order) => {
          const orderKey = tiktokBuyerKey(order.whatnot_buyer_username || order.display_name || order.partner_id_name);
          return !key || orderKey.includes(key) || key.includes(orderKey);
        });
        const seen = new Set();
        const uniqueOrders = rows.filter((order) => {
          const orderKey = String(order.id || order.order_number || order.external_order_ref || '').trim();
          if (!orderKey || seen.has(orderKey)) return false;
          seen.add(orderKey);
          return true;
        }).slice(0, 10);
        setTikTokCustomerOrders(uniqueOrders);
        const linePairs = await Promise.all(uniqueOrders.map(async (order) => {
          const orderKey = String(order.id || order.order_number || order.external_order_ref || '').trim();
          const existingLines = Array.isArray(order?.lines) ? order.lines : [];
          if (!order?.id || existingLines.length) return [orderKey, existingLines];
          try {
            const lineData = await fetchApi(`/api/sale_orders/lines?order_id=${encodeURIComponent(order.id)}`);
            return [orderKey, Array.isArray(lineData?.rows) ? lineData.rows : (Array.isArray(lineData?.lines) ? lineData.lines : [])];
          } catch {
            return [orderKey, []];
          }
        }));
        if (cancelled) return;
        const lineMap = Object.fromEntries(linePairs);
        setTikTokCustomerOrderLinesById(lineMap);
        setTikTokCustomerOrders(uniqueOrders.map((order) => {
          const orderKey = String(order.id || order.order_number || order.external_order_ref || '').trim();
          return {
            ...order,
            lines: Array.isArray(order?.lines) && order.lines.length ? order.lines : (lineMap[orderKey] || []),
          };
        }));
      })
      .catch(() => {
        if (!cancelled) {
          setTikTokCustomerProfile(null);
          setTikTokCustomerOrders([]);
          setTikTokCustomerOrderLinesById({});
        }
      })
      .finally(() => {
        if (!cancelled) setTikTokCustomerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tiktokCustomerContext?.buyer, tiktokCustomerContext?.username]);

  useEffect(() => {
    if (!goLiveSessionId) return;
    const savedLots = new Set(
      (Array.isArray(liveRows) ? liveRows : [])
        .filter((row) => String(row?.barcode || '').trim())
        .map((row) => `${Number(goLiveSessionId)}:${String(row?.lotNo || '').trim()}`)
    );
    if (!savedLots.size) return;
    setTikTokPendingScans((current) => {
      const rows = Array.isArray(current) ? current : [];
      const next = rows.filter((item) => !savedLots.has(`${Number(item?.sessionId || 0)}:${String(item?.lotNo || '').trim()}`));
      return next.length === rows.length ? rows : next;
    });
  }, [goLiveSessionId, liveRows, setTikTokPendingScans]);

  useEffect(() => {
    if (!tiktokHandleInput && tiktokOperator?.streamer) {
      setTikTokHandleInput(tiktokOperator.streamer);
    }
  }, [tiktokOperator?.streamer]);

  useEffect(() => {
    // Keep UI aligned: if TikTok is enabled, show TikTok platform by default.
    if (tiktokOperator?.enabled) setPlatform('tiktok');
  }, [tiktokOperator?.enabled]);

  useEffect(() => {
    if (platform !== 'tiktok' || isGoingLive || tiktokDemoMode) return;
    let cancelled = false;
    fetchApi('/api/tiktok_live_sessions/active?fast=1')
      .then((data) => {
        if (cancelled) return;
        const session = data?.session || null;
        if (session?.serverSessionId && Number(session.serverSessionId) !== Number(goLiveSessionId || 0)) {
          const hasLocalDraftRows = (Array.isArray(liveRows) ? liveRows : []).some((row) => String(row?.barcode || '').trim());
          if (!hasLocalDraftRows && !goLiveSessionId) {
            const serverRows = Array.isArray(session.rows) ? session.rows : [];
            setPlatform('tiktok');
            setLiveRows(serverRows);
            setIsGoingLive(true);
            setGoLiveSessionId(session.serverSessionId || null);
            setLiveSequence((current) => Math.max(Number(current || 0), Number(session.sequence || 0)));
            setTikTokRecoverableServerSession(null);
            writeStore({
              draft: {
                lotCount: String(Math.max(1, serverRows.length || 1)),
                rows: serverRows,
                isLive: true,
                liveName: '',
                serverSessionId: session.serverSessionId || null,
                detailsCsvText: '',
                detailsCsvName: '',
              },
              history: [],
              seq: Math.max(Number(readStore().seq || 0), Number(session.sequence || 0)),
            });
            return;
          }
          setTikTokRecoverableServerSession(session);
        } else {
          setTikTokRecoverableServerSession(null);
        }
      })
      .catch(() => {
        if (!cancelled) setTikTokRecoverableServerSession(null);
      });
    return () => {
      cancelled = true;
    };
  }, [platform, isGoingLive, tiktokDemoMode, goLiveSessionId, liveRows]);

  useEffect(() => {
    if (!tiktokEndArmedUntil) {
      setTikTokEndArmSeconds(0);
      return undefined;
    }
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((tiktokEndArmedUntil - Date.now()) / 1000));
      setTikTokEndArmSeconds(remaining);
      if (remaining <= 0) setTikTokEndArmedUntil(0);
    };
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [tiktokEndArmedUntil]);

  useEffect(() => {
    if (isRunning || !currentStreamUrl) return;
    setStreamUrlInput((prev) => prev || currentStreamUrl);
  }, [currentStreamUrl, isRunning]);

  const focusScanInput = useCallback((select = false) => {
    const input = scanRef.current;
    if (!input || !scanMode || showLotInput || isSpectator) return;
    window.requestAnimationFrame(() => {
      focusWithoutScroll(input, select);
    });
  }, [scanMode, showLotInput, isSpectator]);

  // --- Scan mode: capture keyboard input globally (Whatnot only) ---
  useEffect(() => {
    if (!scanMode || platform !== 'whatnot') return;
    let buffer = '';
    let timer = null;
    const handler = (e) => {
      const target = e.target;
      const tag = target?.tagName;
      const isManualInput = tag === 'INPUT' && target?.dataset?.manualInput === 'true';
      const isBarcodeInput = target?.id === 'barcode-input';
      const isTikTokWinnerBarcodeInput = target?.id === 'tiktok-winner-barcode-input';
      const isTextArea = tag === 'TEXTAREA' || target?.isContentEditable;

      // Let the barcode field handle itself, and never hijack deliberate manual text areas.
      if (isBarcodeInput || isTikTokWinnerBarcodeInput || isManualInput || isTextArea) return;

      if (e.key === 'Enter' && buffer.length > 0) {
        e.preventDefault();
        handleScan(buffer);
        buffer = '';
      } else if (e.key.length === 1) {
        buffer += e.key;
        clearTimeout(timer);
        timer = setTimeout(() => { buffer = ''; }, 500);
      }
    };
    window.addEventListener('keydown', handler);
    return () => { window.removeEventListener('keydown', handler); clearTimeout(timer); };
  }, [scanMode, platform]);

  useEffect(() => {
    focusScanInput();
  }, [focusScanInput, selectedCandidate?.id, currentLot?.id]);

  useEffect(() => {
    if (!scanMode || showLotInput || isSpectator) return undefined;
    const handleWindowFocus = () => focusScanInput();
    const handleVisibility = () => {
      if (!document.hidden) focusScanInput();
    };
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [focusScanInput, scanMode, showLotInput, isSpectator]);

  const showFeedback = useCallback((msg, type = 'info') => {
    setFeedback({ msg, type });
    setTimeout(() => setFeedback(null), 4000);
  }, []);

  const tiktokAssignments = tiktokWinnerState?.rows || [];
  const tiktokNext = (
    tiktokAssignments.find((r) => r.status === 'pending')
    || tiktokAssignments.find((r) => r.status === 'assigned')
    || tiktokAssignments.find((r) => r.status === 'needs_review')
    || null
  );

  useEffect(() => {
    if (!tiktokOperator?.enabled) return;
    if (!tiktokNext || !tiktokNext.id) return;
    // Keep the station ready for the next scan.
    window.requestAnimationFrame(() => {
      try {
        focusWithoutScroll(tiktokScanRef.current, true);
      } catch {}
    });
  }, [tiktokOperator?.enabled, tiktokNext?.id]);

  async function handleTikTokWinnerScan(raw) {
    const code = String(raw || tiktokWinnerScanInput || '').trim();
    if (!tiktokOperator?.enabled) {
      showFeedback('Enable TikTok auction mode first', 'error');
      return;
    }
    if (!tiktokNext?.id) {
      showFeedback('No pending TikTok winner yet', 'info');
      return;
    }
    if (!code) {
      showFeedback('Scan or type a barcode first', 'error');
      return;
    }
    setTikTokWinnerBusy(true);
    try {
      const assignedRes = await postApi('/api/winner_assignment/scan', {
        assignment_id: tiktokNext.id,
        barcode: code,
        session_id: tiktokSessionId,
      });
      const assigned = assignedRes?.assignment;
      if (tiktokAutoConfirm && assigned?.id) {
        await postApi('/api/winner_assignment/confirm', { assignment_id: assigned.id });
        showFeedback(`Confirmed lot ${tiktokNext.lot_number || '—'} @${tiktokNext.winner_username || 'unknown'}`, 'success');
      } else {
        showFeedback(`Assigned barcode to lot ${tiktokNext.lot_number || '—'}`, 'success');
      }
      setTikTokWinnerScanInput('');
      refreshStats();
      refreshTikTokWinnerState();
      window.requestAnimationFrame(() => {
        tiktokScanRef.current?.focus();
        tiktokScanRef.current?.select?.();
      });
    } catch (err) {
      showFeedback(`TikTok scan failed: ${err.message}`, 'error');
    } finally {
      setTikTokWinnerBusy(false);
    }
  }

  // --- Undo timer ---
  const startUndoTimer = useCallback((lotId) => {
    lastDroppedLotRef.current = lotId;
    setUndoAvailable(true);
    setUndoSeconds(10);
    clearTimeout(undoTimerRef.current);
    let count = 10;
    const tick = () => {
      count--;
      if (count <= 0) {
        setUndoAvailable(false);
        setUndoSeconds(0);
        lastDroppedLotRef.current = null;
      } else {
        setUndoSeconds(count);
        undoTimerRef.current = setTimeout(tick, 1000);
      }
    };
    undoTimerRef.current = setTimeout(tick, 1000);
  }, []);

  useEffect(() => () => clearTimeout(undoTimerRef.current), []);

  async function handleUndo() {
    clearTimeout(undoTimerRef.current);
    setUndoAvailable(false);
    setUndoSeconds(0);
    try {
      await postApi('/api/current_lot/reuse');
      showFeedback('↩️ Undone — lot restored, ready to scan', 'success');
      refreshStats();
      refreshLotProducts();
    } catch (err) {
      showFeedback(`Undo failed: ${err.message}`, 'error');
    }
  }

  const processWhatnotScanQueue = useCallback(async () => {
    if (scanProcessingRef.current) return;
    const nextCode = scanQueueRef.current.shift();
    if (!nextCode) return;
    scanProcessingRef.current = true;
    try {
      const res = await postApi('/api/scan', { barcode: nextCode, session_id: session.id });
      if (res.command === 'release_bucket') {
        showFeedback('Released — scan next product for a new lot', 'success');
        refreshStats();
        refreshLotProducts();
        if (res.lot_id) startUndoTimer(res.lot_id);
        return;
      }
      if (res.command === 'undo_release') {
        clearTimeout(undoTimerRef.current);
        setUndoAvailable(false);
        setUndoSeconds(0);
        showFeedback('↩️ Undone — lot restored, ready to scan', 'success');
        refreshStats();
        refreshLotProducts();
        return;
      }
      const qtyMsg = res.active_item?.qty_remaining != null
        ? ` — ${res.active_item.qty_remaining} remaining in stock`
        : '';
      const scannedMsg = res.active_item?.scanned_qty > 1
        ? ` x${res.active_item.scanned_qty}`
        : '';
      showFeedback(`✅ Scanned: ${shortDisplayProductName(res.active_item?.product_name) || nextCode}${scannedMsg}${qtyMsg}`, 'success');
      refreshStats();
      refreshLotProducts();
    } catch (err) {
      let msg = err.message;
      if (msg.includes('out_of_stock') || msg.includes('not_enough_stock') || err.status === 409) {
        msg = '⚠️ Not enough stock — all available units are already reserved';
      } else if (msg.includes('no_reusable_lot')) {
        msg = '⚠️ Nothing to undo right now';
      } else if (msg.includes('no_current_lot')) {
        msg = '⚠️ Open a new lot first, then scan the product';
      }
      showFeedback(`Scan failed: ${msg}`, 'error');
      focusScanInput(true);
    } finally {
      scanProcessingRef.current = false;
      if (scanQueueRef.current.length) {
        window.setTimeout(() => {
          processWhatnotScanQueue();
        }, 0);
      }
    }
  }, [focusScanInput, refreshLotProducts, refreshStats, session.id, showFeedback, startUndoTimer]);

  const handleScan = useCallback((barcode) => {
    const fallbackInput = scanRef.current?.value || scanInput;
    const code = String(barcode || fallbackInput || '').trim();
    if (!code) {
      showFeedback('Enter or scan a barcode', 'error');
      return;
    }
    setScanInput('');
    if (scanRef.current) scanRef.current.value = '';
    focusScanInput(true);
    scanQueueRef.current.push(code);
    processWhatnotScanQueue();
  }, [focusScanInput, processWhatnotScanQueue, scanInput, showFeedback]);

  async function handleRelease() {
    // Save lot id before dropping for undo
    const lotId = currentLot.id;
    try {
      await postApi('/api/current_lot/drop');
      showFeedback('Released — scan next product for a new lot', 'success');
      refreshStats();
      refreshLotProducts();
      if (lotId) startUndoTimer(lotId);
    } catch (err) {
      showFeedback(`Release failed: ${err.message}`, 'error');
    }
  }

  async function handleSelectCandidate(item) {
    if (!item?.id) return;
    try {
      await postApi('/api/current_lot/select_product', { item_id: item.id });
      showFeedback(`Live choice set: ${shortDisplayProductName(item.product_name) || item.barcode}`, 'success');
      refreshStats();
      refreshLotProducts();
    } catch (err) {
      showFeedback(`Unable to set live choice: ${err.message}`, 'error');
    }
  }

  async function handleRemoveCandidate(item) {
    if (!item?.id) return;
    try {
      await postApi('/api/current_lot/remove_candidate', { item_id: item.id });
      showFeedback(`Removed: ${shortDisplayProductName(item.product_name) || item.barcode}`, 'info');
      refreshStats();
      refreshLotProducts();
    } catch (err) {
      showFeedback(`Unable to remove candidate: ${err.message}`, 'error');
    }
  }

  // Dedicated operator hotkeys so a USB foot pedal / macro button can trigger
  // release/undo without touching the laptop.
  useEffect(() => {
    const handler = (e) => {
      const tag = e.target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      if (e.repeat) return;

      if (e.key === 'F8' && showRelease) {
        e.preventDefault();
        handleRelease();
      }

      if (e.key === 'F7' && undoAvailable) {
        e.preventDefault();
        handleUndo();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [showRelease, undoAvailable, currentLot.id]);

  async function handleSetLotNumber() {
    const lot = manualLotNumber.trim();
    if (!lot) return;
    try {
      await postApi('/api/current_lot/set', { lot_number: lot, session_id: session.id });
      showFeedback(`Lot #${lot} set`, 'success');
      setManualLotNumber('');
      setShowLotInput(false);
      refreshStats();
    } catch (err) {
      showFeedback(`Failed: ${err.message}`, 'error');
    }
  }

  async function handleStartStream() {
    setPlatform('whatnot');
    const streamUrl = String(streamUrlInput || currentStreamUrl || '').trim();
    if (!streamUrl) {
      showFeedback('Paste your Whatnot live stream URL (optional if already set)', 'error');
      return;
    }
    setStreamUrlBusy(true);
    try {
      await postApi('/api/live_collector/start', { stream_url: streamUrl, mode: 'our_stream' });
      showFeedback('Live collector started', 'success');
      refreshStats();
      setTimeout(() => refreshStats(), 600);
    } catch (err) {
      showFeedback(`Unable to start collector: ${err.message}`, 'error');
    } finally {
      setStreamUrlBusy(false);
    }
  }

  async function handleStopStream() {
    setStreamUrlBusy(true);
    try {
      await postApi('/api/live_collector/stop', {});
      showFeedback('Live collector stopped', 'info');
      refreshStats();
    } catch (err) {
      showFeedback(`Unable to stop collector: ${err.message}`, 'error');
    } finally {
      setStreamUrlBusy(false);
    }
  }

  async function handleToggleTikTok(enabled) {
    const streamer = String(tiktokHandleInput || '').trim().replace(/^@/, '');
    if (enabled && !streamer) {
      showFeedback('Enter your TikTok handle first (e.g. giftexpress)', 'error');
      return;
    }
    setTikTokBusy(true);
    try {
      await postApi('/api/tiktok_operator/config', { enabled: !!enabled, streamer });
      showFeedback(enabled ? 'TikTok auction mode enabled' : 'TikTok auction mode disabled', enabled ? 'success' : 'info');
      if (enabled) setPlatform('tiktok');
      refreshStats();
    } catch (err) {
      showFeedback(`TikTok mode failed: ${err.message}`, 'error');
    } finally {
      setTikTokBusy(false);
    }
  }

  async function handleSetTikTokLot() {
    const lot = String(tiktokLotInput || '').trim();
    if (!tiktokOperator?.enabled || !tiktokStreamUrl) {
      showFeedback('Enable TikTok mode first', 'error');
      return;
    }
    if (!lot) return;
    setTikTokBusy(true);
    try {
      await postApi('/api/tiktok_extractor/lot_state', {
        stream_url: tiktokStreamUrl,
        next_lot: Number(lot),
      });
      showFeedback(`TikTok current lot set to ${lot}`, 'success');
      refreshTikTokLotState();
      refreshTikTokWinnerState();
    } catch (err) {
      showFeedback(`TikTok lot set failed: ${err.message}`, 'error');
    } finally {
      setTikTokBusy(false);
    }
  }

  async function handleRetryIngest(failedId) {
    try {
      const res = await postApi('/api/retry_ingest', { failed_id: failedId });
      if (res.ok || res.already_resolved) {
        showFeedback('✅ Retry succeeded — winner synced', 'success');
      } else {
        showFeedback('Retry failed — check server state', 'error');
      }
      refreshFailed();
    } catch (err) {
      showFeedback(`Retry failed: ${err.message}`, 'error');
    }
  }

  async function handleDismissIngest(failedId) {
    try {
      await postApi('/api/mark_ingest_resolved', { failed_id: failedId });
      showFeedback('Dismissed', 'info');
      refreshFailed();
    } catch (err) {}
  }

  async function handleRetryAll() {
    const retryable = failedIngests.filter(f => !f.needs_review);
    if (retryable.length === 0) return;
    setBulkRetrying(true);
    try {
      const res = await postApi('/api/retry_all_ingests', {});
      showFeedback(`Retry all: ${res.succeeded} synced, ${res.failed} still failed`, res.failed === 0 ? 'success' : 'info');
      refreshFailed();
    } catch (err) {
      showFeedback(`Retry all failed: ${err.message}`, 'error');
    } finally {
      setBulkRetrying(false);
    }
  }

  async function handleDismissAll() {
    if (!window.confirm(`Dismiss all ${failedIngests.length} failed syncs? This won't delete data — just clears the error queue.`)) return;
    setBulkDismissing(true);
    try {
      const res = await postApi('/api/dismiss_all_ingests', {});
      showFeedback(`Dismissed ${res.dismissed} failed sync${res.dismissed !== 1 ? 's' : ''}`, 'info');
      refreshFailed();
    } catch (err) {
      showFeedback(`Dismiss all failed: ${err.message}`, 'error');
    } finally {
      setBulkDismissing(false);
    }
  }

  // --- TikTok Go Live handlers ---
  async function tiktokStartLive() {
    if (tiktokStartLiveRef.current || tiktokBusy || isGoingLive) return;
    tiktokStartLiveRef.current = true;
    const total = 1;
    if (tiktokDemoMode) {
      const demoRows = tiktokDemoPlaygroundRows();
      setLiveRows(demoRows);
      setGoLiveSessionId(null);
      setIsGoingLive(true);
      setTikTokActiveSessionMeta({
        sequence: Number(realLiveSequence || 0) + 1,
        matchMode: 'demo',
        rows: demoRows,
        lotCount: demoRows.length,
      });
      setTikTokSaveState({ status: 'saved', message: 'Demo playground is active. No real session, orders, or inventory changes will be made.' });
      showFeedback('Demo playground started — scan lot 1 and practice safely without touching real data.', 'success');
      window.requestAnimationFrame(() => {
        focusWithoutScroll(tiktokBarcodeRefs.current[0]);
      });
      tiktokStartLiveRef.current = false;
      return;
    }
    setTikTokBusy(true);
    try {
      const data = await postApi('/api/tiktok_live_sessions/start', {
        lot_count: total,
        live_name: '',
        sequence: 0,
      });
      const sessionData = data?.session || {};
      setLiveRows(Array.isArray(sessionData.rows) ? sessionData.rows : Array.from({ length: total }, (_, i) => ({ lotNo: String(i + 1), barcode: '' })));
      setGoLiveSessionId(sessionData.serverSessionId || null);
      setLiveSequence(Number(sessionData.sequence || 0));
      setTikTokActiveSessionMeta(sessionData);
      setIsGoingLive(true);
      loadTikTokGoLiveHistory();
      pushTikTokApiLog('ok', `POST start — session #${sessionData.sequence || '?'}`);
      showFeedback('Open-ended TikTok live started — scan lot 1, and the next lot will appear automatically.', 'success');
      window.requestAnimationFrame(() => {
        focusWithoutScroll(tiktokBarcodeRefs.current[0]);
      });
    } catch (err) {
      showFeedback(`Could not start TikTok Go Live session: ${err.message}`, 'error');
    } finally {
      setTikTokBusy(false);
      tiktokStartLiveRef.current = false;
    }
  }

  function tiktokResumeLocalDraft() {
    const draft = tiktokRecoverableLocalDraft;
    if (!draft) return;
    setLiveRows(Array.isArray(draft.rows) ? draft.rows : []);
    setGoLiveSessionId(draft.serverSessionId || null);
    setIsGoingLive(true);
    setTikTokRecoverableLocalDraft(null);
    showFeedback('Recovered your unfinished TikTok live from local storage.', 'success');
    window.requestAnimationFrame(() => {
      const nextIndex = Math.max(0, (Array.isArray(draft.rows) ? draft.rows : []).findIndex((row) => !String(row?.barcode || '').trim()));
      focusWithoutScroll(tiktokBarcodeRefs.current[nextIndex]);
    });
  }

  function tiktokResumeServerSession() {
    const session = tiktokRecoverableServerSession;
    if (!session) return;
    setLiveRows(Array.isArray(session.rows) ? session.rows : []);
    setGoLiveSessionId(session.serverSessionId || null);
    setIsGoingLive(true);
    setLiveSequence((current) => Math.max(Number(current || 0), Number(session.sequence || 0)));
    setTikTokActiveSessionMeta(session);
    setTikTokRecoverableServerSession(null);
    showFeedback(`Resumed TikTok live Session #${session.sequence || session.serverSessionId}.`, 'success');
    window.requestAnimationFrame(() => {
      const rows = Array.isArray(session.rows) ? session.rows : [];
      const nextIndex = Math.max(0, rows.findIndex((row) => !String(row?.barcode || '').trim()));
      focusWithoutScroll(tiktokBarcodeRefs.current[nextIndex]);
    });
  }

  async function tiktokEndLive() {
    if (tiktokEndLiveRef.current) return;
    if (!liveRows.length) return;
    if (!isGoingLive) return;
    if (activePendingTikTokScans.length) {
      showFeedback(`${activePendingTikTokScans.length} scan${activePendingTikTokScans.length !== 1 ? 's are' : ' is'} still syncing. Keep this page open until the queue clears.`, 'error');
      return;
    }
    if (!scannedTikTokRows.length) {
      if (!tiktokEndArmed) {
        setTikTokEndArmedUntil(Date.now() + 10000);
        showFeedback(
          tiktokDemoMode
            ? 'No lots scanned. Click Live Ends again within 10 seconds to cancel this demo live.'
            : 'No lots scanned. Click Live Ends again within 10 seconds to cancel and delete this empty live.',
          'info',
        );
        return;
      }
      setTikTokEndArmedUntil(0);
      if (tiktokDemoMode) {
        setIsGoingLive(false);
        setLiveRows([]);
        setGoLiveSessionId(null);
        setTikTokSaveState({ status: 'idle', message: '' });
        showFeedback('Empty demo live cancelled.', 'success');
        return;
      }
      tiktokEndLiveRef.current = true;
      setTikTokBusy(true);
      try {
        if (goLiveSessionId) {
          await postApi('/api/tiktok_live_sessions/delete_empty', { session_id: goLiveSessionId });
        }
        setIsGoingLive(false);
        setLiveRows([]);
        setGoLiveSessionId(null);
        showFeedback('Empty TikTok live cancelled and removed.', 'success');
      } catch (err) {
        showFeedback(`Could not cancel empty live: ${err.message}`, 'error');
      } finally {
        setTikTokBusy(false);
        tiktokEndLiveRef.current = false;
      }
      return;
    }
    if (tiktokLastRowHasBarcode) {
      showFeedback('Last scanned lot has not advanced to a blank row yet. Scan next item or wait for the next blank lot before ending.', 'error');
      return;
    }
    if (!tiktokEndArmed) {
      setTikTokEndArmedUntil(Date.now() + 10000);
      showFeedback(`Live End armed for 10 seconds. Click Live Ends again only if the TikTok live is truly finished. ${scannedTikTokRows.length} lots will be closed.`, 'info');
      return;
    }
    const nextSeq = tiktokDemoMode ? Number(realLiveSequence || 0) + 1 : Number(liveSequence || 0);
    setTikTokEndArmedUntil(0);
    tiktokEndLiveRef.current = true;
    setTikTokBusy(true);
    let archived = null;
    if (tiktokDemoMode) {
      archived = {
        id: `demo-go-live-${nextSeq}-${Date.now()}`,
        sequence: nextSeq,
        liveName: 'Demo Mode',
        endedAt: new Date().toISOString(),
        rows: liveRows,
        lotCount,
        matchMode: 'demo',
      };
    }
    try {
      if (!tiktokDemoMode && goLiveSessionId) {
        pushTikTokApiLog('pending', `POST end — session #${goLiveSessionId}`);
        const data = await postApi('/api/tiktok_live_sessions/end', { session_id: goLiveSessionId });
        archived = data?.session || null;
        pushTikTokApiLog('ok', `end — session #${goLiveSessionId} archived`);
      }
    } catch (err) {
      pushTikTokApiLog('error', `end — ${err.message || 'failed'}`);
      showFeedback(`Live was not closed. Server archive failed: ${err.message}. Keep this page open and try Live Ends again.`, 'error');
      return;
    } finally {
      setTikTokBusy(false);
      tiktokEndLiveRef.current = false;
    }
    if (!archived) {
      archived = {
        id: `go-live-${nextSeq}-${Date.now()}`,
        sequence: nextSeq,
        liveName: '',
        endedAt: new Date().toISOString(),
        rows: liveRows,
        lotCount,
        serverSessionId: goLiveSessionId || undefined,
      };
    }
    setTikTokActiveSessionMeta(null);
    if (!tiktokDemoMode) setLiveSequence(Math.max(nextSeq, Number(archived?.sequence || 0)));
    setIsGoingLive(false);
    setLiveRows([]);
    setGoLiveSessionId(null);
    loadTikTokGoLiveHistory();
    showFeedback(
      tiktokDemoMode
        ? `Demo live closed as Go Live ${nextSeq}. No real TikTok or inventory data was changed.`
        : `Live closed as Go Live ${nextSeq}. Open Company → TikTok Live Auctions to review the saved session.`,
      'success',
    );
  }

  function tiktokUpdateRow(index, key, value) {
    setLiveRows((current) => current.map((row, i) => (i === index ? { ...row, [key]: value } : row)));
  }

  function tiktokSelectProductForLot(index, product) {
    const barcode = productBarcode(product);
    if (!barcode) return;
    setTikTokInspectedProduct(product);
    setTikTokBarcodeSearchRow(null);
    clearTikTokBarcodeDraft(index);
    tiktokHandleBarcodeCommit(index, barcode);
  }

  async function tiktokSaveLotNote(index, rawValue) {
    const row = liveRows[index] || {};
    const notes = String(rawValue || '').trim();
    tiktokUpdateRow(index, 'notes', notes);
    if (tiktokDemoMode) {
      return;
    }
    if (!goLiveSessionId || !String(row?.lotNo || '').trim() || !row?.itemId) {
      return;
    }
    try {
      const data = await postApi('/api/tiktok_live_sessions/update_lot_note', {
        session_id: goLiveSessionId,
        lot_no: row.lotNo,
        item_id: row.itemId,
        notes,
      });
      if (data?.row) {
        setLiveRows((current) => current.map((entry, i) => (i === index ? { ...entry, ...data.row } : entry)));
      }
    } catch (err) {
      showFeedback(`Could not save note for lot ${row.lotNo}: ${err.message}`, 'error');
    }
  }

  function tiktokQueuePendingScan(scan, error = '') {
    const normalized = {
      sessionId: Number(scan?.sessionId || goLiveSessionId || 0),
      lotNo: String(scan?.lotNo || '').trim(),
      barcode: String(scan?.barcode || '').trim(),
      reviewLater: Boolean(scan?.reviewLater),
      rowIndex: Number(scan?.rowIndex || 0),
      queuedAt: scan?.queuedAt || safeNowIso(),
      lastError: String(error || scan?.lastError || '').slice(0, 240),
    };
    if (!normalized.sessionId || !normalized.lotNo) return;
    const key = `${normalized.sessionId}:${normalized.lotNo}`;
    setTikTokPendingScans((current) => {
      const rows = Array.isArray(current) ? current : [];
      return [...rows.filter((item) => `${Number(item?.sessionId || 0)}:${String(item?.lotNo || '').trim()}` !== key), normalized];
    });
    setTikTokSaveState({ status: 'queued', message: `Lot ${normalized.lotNo} is backed up locally and retrying.` });
  }

  function tiktokMarkScanSynced(sessionId, lotNo, barcode = null) {
    const key = `${Number(sessionId || 0)}:${String(lotNo || '').trim()}`;
    setTikTokPendingScans((current) => (Array.isArray(current) ? current : []).filter((item) => (
      `${Number(item?.sessionId || 0)}:${String(item?.lotNo || '').trim()}` !== key
      || (barcode !== null && String(item?.barcode || '').trim() !== String(barcode || '').trim())
    )));
  }

  function tiktokEnsureNextBlankLot(index) {
    setLiveRows((current) => {
      const isLastRow = index >= current.length - 1;
      const currentRow = current[index] || {};
      if (!isLastRow || !isTikTokRowFilled(currentRow)) return current;
      const nextLotNo = String(Math.max(
        0,
        ...current.map((row) => Number(row?.lotNo || 0)).filter((value) => Number.isFinite(value)),
      ) + 1);
      return [...current, { lotNo: nextLotNo, barcode: '' }];
    });
  }

  function tiktokApplyOptimisticScan(index, barcode) {
    const normalizedBarcode = String(barcode || '').trim();
    const reviewLater = normalizedBarcode === 'review_later';
    const localMatch = tiktokInventoryMap.get(String(barcode || '').trim().toLowerCase()) || null;
    setLiveRows((current) => {
      const nextRows = current.map((row, rowIndex) => (
        rowIndex === index
          ? {
              ...row,
              barcode: reviewLater ? '' : barcode,
              productName: reviewLater ? 'Review later' : (localMatch?.name || row.productName || ''),
              notes: reviewLater ? 'review_later' : '',
              sku: reviewLater ? '' : (localMatch?.default_code || localMatch?.sku || row.sku || ''),
              cost: reviewLater ? 0 : Number(localMatch?.cost_price || row.cost || 0),
              productId: reviewLater ? null : (localMatch?.id || row.productId || null),
              matched: reviewLater ? false : Boolean(localMatch || row.matched),
              reviewLater,
              statusLabel: reviewLater ? 'Review later' : '',
              statusFamily: reviewLater ? 'review_later' : '',
            }
          : row
      ));
      const isLastRow = index >= nextRows.length - 1;
      if (!isLastRow || !isTikTokRowFilled(nextRows[index])) return nextRows;
      const nextLotNo = String(Math.max(
        0,
        ...nextRows.map((row) => Number(row?.lotNo || 0)).filter((number) => Number.isFinite(number)),
      ) + 1);
      return [...nextRows, { lotNo: nextLotNo, barcode: '' }];
    });
  }

  async function tiktokSaveScanToServer({ sessionId, lotNo, barcode, rowIndex, fromRetry = false, reviewLater = false }) {
    if (!sessionId || !lotNo) return false;
    const lotKey = `${Number(sessionId || 0)}:${String(lotNo || '').trim()}`;
    if (tiktokSavingLotsRef.current.has(lotKey)) return false;
    tiktokSavingLotsRef.current.add(lotKey);
    if (!fromRetry) setTikTokSaveState({ status: 'saving', message: `Saving lot ${lotNo}...` });
    if (!fromRetry) pushTikTokApiLog('pending', `POST scan_lot — lot ${lotNo}`);
    try {
      const data = await postApi('/api/tiktok_live_sessions/scan_lot', {
        session_id: sessionId,
        lot_no: lotNo,
        barcode,
        review_later: reviewLater,
      });
      if (data?.row) {
        setLiveRows((current) => current.map((row, index) => (
          String(row?.lotNo || '').trim() === String(lotNo)
            ? { ...row, ...data.row }
            : row
        )));
      }
      tiktokMarkScanSynced(sessionId, lotNo, barcode);
      setTikTokSaveState({ status: 'saved', message: reviewLater ? `Lot ${lotNo} marked for review.` : `Lot ${lotNo} saved.` });
      pushTikTokApiLog('ok', reviewLater ? `scan_lot #${lotNo} — review later` : `scan_lot #${lotNo} — saved`);
      return true;
    } catch (err) {
      pushTikTokApiLog('error', `scan_lot #${lotNo} — ${err.message || 'failed'}`);
      tiktokQueuePendingScan({ sessionId, lotNo, barcode, rowIndex, reviewLater }, err.message || 'Save failed');
      return false;
    } finally {
      tiktokSavingLotsRef.current.delete(lotKey);
    }
  }

  async function tiktokClearLot(index) {
    const currentRow = liveRows[index] || {};
    const lotNo = String(currentRow?.lotNo || index + 1).trim();
    if (!lotNo) return;
    const resetRow = { ...currentRow, barcode: '', productName: '', notes: '', sku: '', cost: 0, productId: null, matched: false, reviewLater: false, statusLabel: '', statusFamily: '' };
    if (tiktokDemoMode) {
      setLiveRows((current) => current.map((row, rowIndex) => (rowIndex === index ? resetRow : row)));
      setTikTokSaveState({ status: 'saved', message: `Demo lot ${lotNo} cleared.` });
      window.requestAnimationFrame(() => {
        focusWithoutScroll(tiktokBarcodeRefs.current[index], true);
      });
      return;
    }
    if (!goLiveSessionId) {
      setLiveRows((current) => current.map((row, rowIndex) => (rowIndex === index ? resetRow : row)));
      return;
    }
    setTikTokSaveState({ status: 'saving', message: `Clearing lot ${lotNo}...` });
    pushTikTokApiLog('pending', `POST clear_lot — lot ${lotNo}`);
    try {
      tiktokCommittedValuesRef.current.delete(`${Number(goLiveSessionId || 0)}:${lotNo}`);
      const data = await postApi('/api/tiktok_live_sessions/clear_lot', {
        session_id: goLiveSessionId,
        lot_no: lotNo,
      });
      setLiveRows((current) => current.map((row, rowIndex) => (
        rowIndex === index
          ? { ...row, ...(data?.row || resetRow) }
          : row
      )));
      tiktokMarkScanSynced(goLiveSessionId, lotNo, '');
      setTikTokSaveState({ status: 'saved', message: `Lot ${lotNo} cleared.` });
      pushTikTokApiLog('ok', `clear_lot #${lotNo} — cleared`);
      window.requestAnimationFrame(() => {
        focusWithoutScroll(tiktokBarcodeRefs.current[index], true);
      });
    } catch (err) {
      showFeedback(`Could not clear lot ${lotNo}: ${err.message}`, 'error');
      setTikTokSaveState({ status: 'idle', message: '' });
    }
  }

  useEffect(() => {
    if (!activePendingTikTokScans.length) return undefined;
    let cancelled = false;
    const retry = async () => {
      if (cancelled) return;
      const next = activePendingTikTokScans[0];
      if (!next?.sessionId || !next?.lotNo) return;
      await tiktokSaveScanToServer({
        sessionId: next.sessionId,
        lotNo: next.lotNo,
        barcode: next.barcode,
        rowIndex: next.rowIndex,
        fromRetry: true,
        reviewLater: Boolean(next.reviewLater),
      });
    };
    const timer = window.setInterval(retry, 2500);
    retry();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activePendingTikTokScans]);

  function tiktokFocusNextBarcode(index) {
    const next = tiktokBarcodeRefs.current[index + 1];
    if (next) focusWithoutScroll(next, true);
  }

  function clearTikTokBarcodeDraft(index) {
    setTikTokBarcodeDraft((current) => (
      Number(current?.row) === Number(index) ? { row: null, value: '' } : current
    ));
  }

  function commitTikTokBarcodeInput(index, rawValue) {
    const value = String(rawValue || '').replace(/[\r\n\t]+/g, '').trim();
    clearTikTokBarcodeDraft(index);
    if (!value) {
      tiktokUpdateRow(index, 'barcode', '');
      return;
    }
    if (isProductNameSearch(value, tiktokInventoryMap)) {
      const [bestMatch] = tiktokProductSuggestions(value);
      if (bestMatch) {
        tiktokSelectProductForLot(index, bestMatch);
        return;
      }
    }
    tiktokHandleBarcodeCommit(index, value);
  }

  async function tiktokHandleBarcodeCommit(index, rawValue) {
    const value = String(rawValue || '').replace(/[\r\n\t]+/g, '').trim();
    if (isTikTokReviewLaterValue(value)) {
      const lotNo = String(liveRows[index]?.lotNo || index + 1).trim();
      const sessionKey = Number(goLiveSessionId || 0);
      const commitKey = `${sessionKey}:${lotNo}`;
      if (tiktokCommittedValuesRef.current.get(commitKey) === 'review_later') return;
      tiktokCommittedValuesRef.current.set(commitKey, 'review_later');
      tiktokApplyOptimisticScan(index, 'review_later');
      if (tiktokDemoMode) {
        tiktokEnsureNextBlankLot(index);
        setTikTokSaveState({ status: 'saved', message: `Lot ${lotNo} marked for review.` });
        window.requestAnimationFrame(() => tiktokFocusNextBarcode(index));
        return;
      }
      if (goLiveSessionId && lotNo) {
        tiktokQueuePendingScan({ sessionId: goLiveSessionId, lotNo, barcode: 'review_later', rowIndex: index, reviewLater: true }, 'Waiting for server confirmation');
        tiktokSaveScanToServer({ sessionId: goLiveSessionId, lotNo, barcode: 'review_later', rowIndex: index, reviewLater: true });
      }
      if (!goLiveSessionId) tiktokEnsureNextBlankLot(index);
      window.requestAnimationFrame(() => tiktokFocusNextBarcode(index));
      return;
    }
    if (isProductNameSearch(value, tiktokInventoryMap)) {
      setTikTokBarcodeSearchRow(index);
      const suggestions = tiktokProductSuggestions(value);
      if (suggestions[0]) {
        setTikTokInspectedProduct(suggestions[0]);
      }
      if (!suggestions.length) {
        showFeedback(`No inventory product matched "${value}"`, 'error');
      }
      return;
    }
    const lotNo = String(liveRows[index]?.lotNo || index + 1).trim();
    const sessionKey = Number(goLiveSessionId || 0);
    const commitKey = `${sessionKey}:${lotNo}`;
    const previousValue = tiktokCommittedValuesRef.current.get(commitKey);
    if (previousValue === value) return;
    tiktokCommittedValuesRef.current.set(commitKey, value);
    const scannedProduct = tiktokInventoryMap.get(String(value || '').trim().toLowerCase()) || null;
    if (scannedProduct) {
      setTikTokInspectedProduct(scannedProduct);
    }
    tiktokApplyOptimisticScan(index, value);
    if (tiktokDemoMode) {
      if (value) {
        tiktokEnsureNextBlankLot(index);
        setTikTokSaveState({ status: 'saved', message: `Demo lot ${lotNo} saved locally.` });
        window.requestAnimationFrame(() => tiktokFocusNextBarcode(index));
      }
      return;
    }
    if (goLiveSessionId && lotNo) {
      tiktokQueuePendingScan({ sessionId: goLiveSessionId, lotNo, barcode: value, rowIndex: index }, 'Waiting for server confirmation');
      tiktokSaveScanToServer({ sessionId: goLiveSessionId, lotNo, barcode: value, rowIndex: index });
    }
    if (!goLiveSessionId && value) tiktokEnsureNextBlankLot(index);
    if (value) window.requestAnimationFrame(() => tiktokFocusNextBarcode(index));
  }

  function downloadTikTokLiveCsv() {
    if (!tiktokMatchedRows.length) {
      showFeedback('No TikTok live rows to download', 'error');
      return;
    }
    const lines = [
      ['lot_no', 'barcode', 'product_name', 'cost', 'buyer_name', 'sale_price', 'fee', 'profit', 'status'].join(','),
      ...tiktokMatchedRows.map((row) => ([
        JSON.stringify(String(row?.lotNo || '')),
        JSON.stringify(String(row?.barcode || '')),
        JSON.stringify(String(row?.productName || row?.match?.name || '')),
        tiktokRowCost(row),
        JSON.stringify(String(row?.tiktokOrder?.buyerDisplay || row?.tiktokOrder?.buyerUsername || row?.tiktokOrder?.buyerName || '')),
        tiktokRowSalePrice(row),
        tiktokRowFees(row),
        tiktokRowProfit(row),
        JSON.stringify(String(row?.statusLabel || 'Pending')),
      ].join(','))),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `tiktok-go-live-session-${activeTikTokSessionSequence || 'draft'}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function calibrateTikTokWorkspace() {
    refreshStats();
    refreshTikTokWinnerState();
    refreshTikTokLotState();
    if (isGoingLive && goLiveSessionId && !tiktokDemoMode) {
      try {
        const data = await fetchApi('/api/tiktok_live_sessions/active?sync=1');
        const session = data?.session || null;
        if (Number(session?.serverSessionId || 0) === Number(goLiveSessionId || 0)) {
          const serverRows = Array.isArray(session.rows) ? session.rows : [];
          const nextRows = mergeTikTokLiveRows(liveRows, serverRows, session.serverSessionId);
          setLiveRows(nextRows);
          setLotCount(String(Math.max(1, nextRows.length || 1)));
          setTikTokActiveSessionMeta(session);
          writeStore({
            draft: {
              lotCount: String(Math.max(1, nextRows.length || 1)),
              rows: nextRows,
              isLive: true,
              liveName: '',
              serverSessionId: session.serverSessionId || null,
              detailsCsvText: '',
              detailsCsvName: '',
            },
            history: [],
            seq: Math.max(Number(readStore().seq || 0), Number(session.sequence || 0)),
          });
        }
      } catch (err) {
        pushTikTokApiLog('error', `TikTok order sync — ${err.message || 'failed'}`);
        showFeedback(`Workspace refreshed, but TikTok order sync was slow or failed: ${err.message}`, 'error');
        return;
      }
    }
    setTikTokSaveState({ status: 'saved', message: 'Workspace refreshed from live APIs.' });
    pushTikTokApiLog('ok', 'Calibrate API — refreshed stats, winner state, lot state');
    showFeedback('TikTok workspace refreshed', 'success');
  }

  function openTopTikTokBuyer() {
    const topBuyer = tiktokTopBuyerRows[0];
    if (!topBuyer?.buyer) {
      showFeedback('No top buyer available yet', 'error');
      return;
    }
    setTikTokCustomerContext({
      buyer: topBuyer.buyer,
      username: cleanTikTokBuyer(topBuyer.buyer),
      orderId: '',
      lotNo: '',
    });
  }

  return (
    <div className="operator">
      {feedback && (
        <div className={`toast toast--${feedback.type} animate-in`}>{feedback.msg}</div>
      )}

      {/* PLATFORM SWITCHER */}
	      <div style={{ display: 'inline-flex', gap: 3, width: 'fit-content', background: 'var(--bg-elevated)', borderRadius: 8, padding: 3, marginBottom: 2, border: '1px solid var(--border-default)' }}>
	        <button
	          className="btn"
	          onClick={() => setPlatform('whatnot')}
	          style={{
	            minHeight: 25, borderRadius: 6, fontWeight: 900, fontSize: '0.72rem', padding: '0 10px',
	            background: platform === 'whatnot' ? 'linear-gradient(135deg, #2563eb, #1d4ed8)' : 'transparent',
	            color: platform === 'whatnot' ? '#fff' : 'var(--text-secondary)',
	            border: 'none',
          }}
        >
          Whatnot Live {isRunning ? '🟢' : '⚫'}
        </button>
	        <button
	          className="btn"
	          onClick={() => setPlatform('tiktok')}
	          style={{
	            minHeight: 25, borderRadius: 6, fontWeight: 900, fontSize: '0.72rem', padding: '0 10px',
	            background: platform === 'tiktok' ? 'linear-gradient(135deg, #f97316, #ea580c)' : 'transparent',
	            color: platform === 'tiktok' ? '#fff' : 'var(--text-secondary)',
	            border: 'none',
          }}
        >
          TikTok Live {tiktokOperator?.enabled ? '🟢' : (isGoingLive ? '🔴' : '⚫')}
        </button>
      </div>

      {/* ===== WHATNOT MODE ===== */}
      {platform === 'whatnot' && (<>

      {collectorUnhealthy && (
        <div className="banner banner--warn animate-in">
          ⚠️ Collector signal weak — {healthWarnings[0]}
          {healthWarnings.length > 1 && ` (+${healthWarnings.length - 1} more)`}
        </div>
      )}

      {/* FAILED INGESTS PANEL */}
      {failedIngests.length > 0 && (
        <div className="panel panel--danger animate-in" style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
            <button
              onClick={() => setFailedExpanded(v => !v)}
              style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-coral)', fontSize: '1rem', fontWeight: 700 }}
            >
              <span>{failedExpanded ? '▼' : '▶'}</span>
              🚨 {failedIngests.length} Winner{failedIngests.length > 1 ? 's' : ''} Failed to Sync
            </button>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
              {failedIngests.some(f => !f.needs_review) && (
                <button
                  className="btn btn--amber"
                  style={{ padding: '5px 14px', fontSize: '0.82rem' }}
                  onClick={handleRetryAll}
                  disabled={bulkRetrying}
                >
                  {bulkRetrying ? '⏳ Retrying…' : `↺ Retry All (${failedIngests.filter(f => !f.needs_review).length})`}
                </button>
              )}
              <button
                className="btn btn--outline"
                style={{ padding: '5px 14px', fontSize: '0.82rem' }}
                onClick={handleDismissAll}
                disabled={bulkDismissing}
              >
                {bulkDismissing ? '⏳…' : `✕ Dismiss All`}
              </button>
            </div>
          </div>
          {failedExpanded && <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
            {failedIngests.map(f => (
              <div key={f.id} className="failed-ingest-row">
                <div className="failed-ingest-info">
                  <span className="font-bold">{f.winner_username}</span>
                  <span className="text-amber"> {fmt$(f.sale_price)}</span>
                  {f.lot_number && <span className="text-muted text-xs"> Lot #{f.lot_number}</span>}
                  {f.needs_review ? (
                    <span className="chip chip--coral" style={{ fontSize: '0.68rem', marginLeft: 6 }}>
                      ⛔ Needs Manual Review ({f.retry_count} fails)
                    </span>
                  ) : (
                    <span className="text-muted text-xs" style={{ marginLeft: 6 }}>
                      {f.retry_count > 0 ? `retried ${f.retry_count}×` : 'not retried'}
                    </span>
                  )}
                  {f.error_message && (
                    <span className="text-coral text-xs" title={f.error_message}> — {f.error_message.slice(0, 60)}{f.error_message.length > 60 ? '…' : ''}</span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  {!f.needs_review && (
                    <button className="btn btn--amber" style={{ padding: '4px 12px', fontSize: '0.8rem' }} onClick={() => handleRetryIngest(f.id)}>
                      Retry
                    </button>
                  )}
                  <button className="btn btn--outline" style={{ padding: '4px 12px', fontSize: '0.8rem' }} onClick={() => handleDismissIngest(f.id)}>
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
          </div>}
        </div>
      )}

      {/* MAIN WORK AREA */}
          {/* UNDO BANNER */}
          {undoAvailable && (
            <div className="banner banner--undo animate-in" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span>Lot released — {undoSeconds}s to undo</span>
              <button className="btn btn--emerald" style={{ padding: '6px 18px' }} onClick={handleUndo}>
                ↩️ Undo
              </button>
            </div>
          )}

          {/* BIG RELEASE BUTTON */}
          {showRelease && (
            <div className="animate-in" style={{ marginBottom: 14 }}>
              <button
                id="big-release-btn"
                onClick={handleRelease}
                style={{
                  width: '100%',
                  padding: '20px 0',
                  fontSize: '1.25rem',
                  fontWeight: 800,
                  background: 'linear-gradient(135deg, #e03131, #c92a2a)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 12,
                  cursor: 'pointer',
                  letterSpacing: '0.03em',
                  boxShadow: '0 4px 20px rgba(224,49,49,0.4)',
                  transition: 'transform 0.1s, box-shadow 0.1s',
                }}
                onMouseDown={e => e.currentTarget.style.transform = 'scale(0.98)'}
                onMouseUp={e => e.currentTarget.style.transform = ''}
              >
                🔓 RELEASE — Drop Bucket, Start Next · F8
              </button>
            </div>
          )}

          {/* TOP BUYERS & SHOUTOUTS — Live engagement helper */}
          {(livebuyers?.buyers?.length > 0 || livebuyers?.recent_winners?.length > 0) && (
            <div className="panel animate-in" style={{
              marginBottom: 14,
              background: 'linear-gradient(135deg, rgba(245,158,11,0.06), rgba(234,88,12,0.04))',
              border: '1.5px solid rgba(245,158,11,0.2)',
              borderRadius: 12,
              padding: '12px 16px',
            }}>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {/* Recent Winners */}
                {livebuyers?.recent_winners?.length > 0 && (
                  <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                    <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--accent-emerald)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                      Recent Winners
                    </div>
                    {livebuyers.recent_winners.map((w, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent-blue)' }}>@{w.username}</span>
                        <span style={{ fontSize: '0.82rem', color: 'var(--accent-amber)', fontWeight: 600 }}>{fmt$(w.price)}</span>
                        {w.lot_number && <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Lot #{w.lot_number}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {/* Top Buyers */}
                {livebuyers?.buyers?.length > 0 && (
                  <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                    <div style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--accent-amber)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                      Top Buyers — Shoutout!
                    </div>
                    {livebuyers.buyers.slice(0, 5).map((b, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: '0.82rem', fontWeight: 800, color: i === 0 ? 'var(--accent-amber)' : 'var(--text-primary)', minWidth: 16 }}>
                          {i === 0 ? '👑' : i === 1 ? '🥈' : i === 2 ? '🥉' : `#${i + 1}`}
                        </span>
                        <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--accent-blue)' }}>@{b.username}</span>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{b.lots_won} lot{b.lots_won !== 1 ? 's' : ''}</span>
                        <span style={{ fontSize: '0.82rem', color: 'var(--accent-amber)', fontWeight: 600 }}>{fmt$(b.total_spent)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 14, alignItems: 'stretch' }}>
            <PosTile title="Touch Scan" accent="rgba(245,158,11,0.3)" style={{ minHeight: 220 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                <div style={{ fontSize: '1.4rem', fontWeight: 900, color: 'var(--text-primary)' }}>Scan Products Into This Lot</div>
                <label className="toggle-label" style={{ margin: 0 }}>
                  <input type="checkbox" checked={scanMode} onChange={e => setScanMode(e.target.checked)} />
                  <span className="text-sm">Auto-capture {scanMode ? '🟢' : '⚫'}</span>
                </label>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 170px', gap: 12 }}>
                <input
                  ref={scanRef}
                  id="barcode-input"
                  type="text"
                  className="input"
                  placeholder="Scan or type barcode…"
                  value={scanInput}
                  onChange={e => setScanInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== 'Enter') return;
                    e.preventDefault();
                    handleScan(e.currentTarget.value);
                  }}
                  onBlur={() => {
                    if (!scanMode || showLotInput) return;
                    setTimeout(() => {
                      const active = document.activeElement;
                      if (active?.dataset?.manualInput === 'true') return;
                      focusScanInput();
                    }, 50);
                  }}
                  autoComplete="off"
                  autoFocus
                  style={{ minHeight: 70, fontSize: '1.4rem', borderRadius: 16 }}
                />
                <button
                  id="scan-submit-btn"
                  className="btn btn--amber"
                  onClick={() => handleScan(scanRef.current?.value)}
                  style={{ minHeight: 70, fontSize: '1.2rem', borderRadius: 16, fontWeight: 900 }}
                >
                  Scan
                </button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
                <span className="chip chip--blue">Candidates: {candidateRows.length}</span>
                <span className="chip chip--emerald">Selected: {selectedCandidate ? 1 : 0}</span>
                <span className="chip chip--amber">Total Cost {fmt$(candidateRows.reduce((s, r) => s + (r.cost || 0), 0))}</span>
              </div>
              <p className="text-sm text-muted" style={{ marginTop: 12 }}>
                Scan 3-5 options if needed, then tap the buyer's choice below. The selected tile is what goes to TV/OBS and what the winner will attach to.
              </p>
            </PosTile>

            <PosTile title="Current Lot" accent="rgba(59,130,246,0.28)" style={{ minHeight: 220 }}>
              <div style={{ fontSize: '2.35rem', fontWeight: 900, color: 'var(--accent-blue)', lineHeight: 1.05 }}>
                {currentLot.lot_number
                  ? (String(currentLot.lot_number).startsWith('P-') ? `Bucket ${currentLot.lot_number}` : `Lot #${currentLot.lot_number}`)
                  : 'Open A New Lot'}
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
                {currentLot.status && (
                  <span className={`chip chip--${
                    currentLot.status === 'sold' ? 'emerald' :
                    currentLot.status === 'awaiting_auction' ? 'amber' :
                    currentLot.status === 'dropped' || currentLot.status === 'released' ? 'coral' : 'blue'
                  }`}>
                    {currentLot.status === 'awaiting_auction' ? 'Products Staged' :
                     currentLot.status === 'sold' ? 'Sold' :
                     currentLot.status === 'dropped' || currentLot.status === 'released' ? 'Released' : 'Open'}
                  </span>
                )}
                <span className={`chip ${failedIngests.length === 0 ? 'chip--emerald' : 'chip--coral'}`}>
                  {failedIngests.length === 0 ? 'Sync OK' : `${failedIngests.length} sync issue${failedIngests.length > 1 ? 's' : ''}`}
                </span>
              </div>
              {undoAvailable ? (
                <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
                  <button className="btn btn--emerald" onClick={handleUndo} style={{ minHeight: 56, borderRadius: 14, fontWeight: 900 }}>
                    Undo {undoSeconds}s
                  </button>
                </div>
              ) : null}
            </PosTile>
          </div>

          <div style={{ marginTop: 14 }}>
            <PosTile title="Whatnot Live Stream" accent="rgba(168,85,247,0.28)">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 180px 160px', gap: 12, alignItems: 'center' }}>
                <input
                  type="text"
                  className="input"
                  value={streamUrlInput}
                  onChange={(e) => setStreamUrlInput(e.target.value)}
                  placeholder="https://www.whatnot.com/live/… (optional)"
                  data-manual-input="true"
                  autoComplete="off"
                  style={{ minHeight: 62, fontSize: '1rem', borderRadius: 14 }}
                />
                <button
                  className="btn btn--blue"
                  onClick={handleStartStream}
                  disabled={streamUrlBusy}
                  style={{ minHeight: 62, borderRadius: 14, fontWeight: 900 }}
                >
                  {streamUrlBusy ? 'Working…' : 'Start Collector'}
                </button>
                <button
                  className="btn btn--outline"
                  onClick={handleStopStream}
                  disabled={streamUrlBusy || !isRunning}
                  style={{ minHeight: 62, borderRadius: 14, fontWeight: 900 }}
                >
                  Stop Collector
                </button>
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
                <span className={`chip ${isRunning ? 'chip--emerald' : 'chip--muted'}`}>
                  {isRunning ? 'Live collector running' : 'Collector stopped'}
                </span>
                {currentStreamUrl ? <span className="chip chip--blue" title={currentStreamUrl}>{currentStreamUrl}</span> : null}
                {activeMode ? <span className="chip chip--amber">Mode: {activeMode}</span> : null}
              </div>
              <p className="text-sm text-muted" style={{ marginTop: 12 }}>
                If you leave URL blank, we use the last known Whatnot URL already stored by the server.
              </p>
            </PosTile>
          </div>

          {includeObsPanel ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 14, marginTop: 14 }}>
              <div />
              <OBSOperatorPanel />
            </div>
          ) : null}

      </>)}
      {/* ===== END WHATNOT MODE ===== */}

      {/* ===== TIKTOK MODE ===== */}
      {platform === 'tiktok' && (<>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, minHeight: 'calc(100vh - 152px)', maxWidth: '100%', overflow: 'hidden' }}>
          <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 16 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                      <span style={{ width: 10, height: 10, borderRadius: '50%', background: isGoingLive ? '#10b981' : '#94a3b8', boxShadow: isGoingLive ? '0 0 0 4px rgba(16,185,129,0.14)' : 'none', flexShrink: 0 }} />
                      <span style={{ fontSize: '0.7rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: isGoingLive ? '#047857' : 'var(--text-secondary)' }}>
                        {isGoingLive ? 'Live Session' : 'Pre-Session Prep'}
                      </span>
                      <span style={{ ...compactBadgeStyle, background: tiktokDemoMode ? '#fff7ed' : '#eef2ff', color: tiktokDemoMode ? '#c2410c' : '#4f46e5', border: `1px solid ${tiktokDemoMode ? '#fdba74' : '#c7d2fe'}` }}>
                        {tiktokDemoMode ? 'Demo Mode' : 'TikTok Live'}
                      </span>
                      <span style={{ ...compactBadgeStyle, background: tiktokMarketSignal.bg, color: tiktokMarketSignal.tone, border: `1px solid ${tiktokMarketSignal.border}` }}>
                        {tiktokMarketSignal.label}
                      </span>
                    </div>
                    <div style={{ fontSize: '1.35rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1.2 }}>
                      {isGoingLive ? `Go Live Session #${activeTikTokSessionSequence}` : `Go Live Session #${activeTikTokSessionSequence} Draft`}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: 8, flexShrink: 0 }}>
                    {[
                      { label: 'Download', fn: downloadTikTokLiveCsv },
                      { label: 'Refresh', fn: calibrateTikTokWorkspace },
                    ].map((btn) => (
                      <button
                        key={btn.label}
                        type="button"
                        onClick={btn.fn}
                        style={{ height: 34, padding: '0 14px', borderRadius: 9, border: '1px solid var(--border-default)', background: '#fff', fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-secondary)', cursor: 'pointer' }}
                      >
                        {btn.label}
                      </button>
                    ))}
                    <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '0 10px', height: 34, borderRadius: 9, border: '1px solid var(--border-default)', background: '#fff', fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-secondary)', cursor: isGoingLive ? 'default' : 'pointer' }}>
                      <input type="checkbox" checked={!!tiktokDemoMode} onChange={(e) => setTikTokDemoMode(e.target.checked)} disabled={isGoingLive} style={{ width: 13, height: 13, accentColor: '#6C47FF' }} />
                      Demo
                    </label>
                    <button
                      onClick={tiktokStartLive}
                      disabled={isGoingLive || tiktokBusy || (tiktokSessionHydrating && !tiktokDemoMode)}
                      style={{ height: 34, padding: '0 16px', borderRadius: 9, fontWeight: 800, fontSize: '0.78rem', border: 'none', cursor: isGoingLive ? 'default' : 'pointer', background: isGoingLive ? '#ecfdf3' : '#6C47FF', color: isGoingLive ? '#047857' : '#fff', opacity: (tiktokBusy || (tiktokSessionHydrating && !tiktokDemoMode)) ? 0.5 : 1 }}
                    >
                      {isGoingLive ? 'Live In Progress' : (tiktokSessionHydrating && !tiktokDemoMode ? 'Checking…' : 'Go Live')}
                    </button>
                    <button
                      onClick={tiktokEndLive}
                      disabled={!isGoingLive || !liveRows.length || tiktokBusy || activePendingTikTokScans.length > 0}
                      style={{ height: 34, padding: '0 16px', borderRadius: 9, fontWeight: 800, fontSize: '0.78rem', border: '1px solid #fecaca', cursor: (!isGoingLive || !liveRows.length || tiktokBusy) ? 'default' : 'pointer', background: tiktokEndArmed ? '#dc2626' : '#fff', color: tiktokEndArmed ? '#fff' : '#b91c1c', opacity: (!isGoingLive || !liveRows.length || tiktokBusy) ? 0.45 : 1 }}
                    >
                      {tiktokEndArmed ? `End Live (${tiktokEndArmSeconds}s)` : 'Live End'}
                    </button>
                  </div>
                </div>

                {(tiktokBatchBlocking || tiktokBatchOverrideActive) ? (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: viewportWidth < 1200 ? '1fr' : 'minmax(0, 1fr) auto',
                      gap: 12,
                      alignItems: 'center',
                      border: `1px solid ${tiktokBatchBlocking ? '#fecaca' : '#bfdbfe'}`,
                      borderRadius: 12,
                      background: tiktokBatchBlocking ? '#fff1f2' : '#eff6ff',
                      padding: '10px 12px',
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 900, color: tiktokBatchBlocking ? '#b91c1c' : '#1d4ed8' }}>
                        {tiktokBatchGuard?.message || (tiktokBatchBlocking ? 'Wrong TikTok batch selected.' : 'TikTok batch override active for this session.')}
                      </div>
                      <div style={{ marginTop: 4, fontSize: '0.68rem', fontWeight: 700, color: tiktokBatchBlocking ? '#7f1d1d' : '#1e3a8a' }}>
                        Orders are mapped only when the effective batch matches the current lot range.
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: viewportWidth < 1200 ? 'flex-start' : 'flex-end' }}>
                      <span style={{ ...compactBadgeStyle, background: '#fff', color: '#334155', border: '1px solid #cbd5e1' }}>Expected B{tiktokExpectedBatch} · {tiktokExpectedBatchRange}</span>
                      <span style={{ ...compactBadgeStyle, background: '#fff', color: '#334155', border: '1px solid #cbd5e1' }}>TikTok B{tiktokDetectedBatch || '—'}</span>
                      {tiktokBatchOverrideActive ? (
                        <span style={{ ...compactBadgeStyle, background: '#dbeafe', color: '#1d4ed8', border: '1px solid #93c5fd' }}>Using B{tiktokEffectiveBatch} · {tiktokEffectiveBatchRange}</span>
                      ) : null}
                      <span style={{ ...compactBadgeStyle, background: tiktokBatchBlocking ? '#fee2e2' : '#dcfce7', color: tiktokBatchBlocking ? '#b91c1c' : '#047857', border: `1px solid ${tiktokBatchBlocking ? '#fecaca' : '#86efac'}` }}>{tiktokBatchStatusLabel}</span>
                    </div>
                  </div>
                ) : null}

	                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12, alignItems: 'stretch' }}>
	                  <div style={{ border: '1px solid var(--border-default)', borderRadius: 14, background: '#fff', padding: 12, display: 'grid', gap: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                      <div style={{ fontSize: '0.64rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Live Stats</div>
                      <div style={{ fontSize: '0.72rem', fontWeight: 900, color: tiktokMarketSignal.tone }}>{tiktokMarketSignal.label} · L{tiktokCurrentLot || 'Prep'} · B{tiktokExpectedBatch}</div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
                      {[
                        { label: 'Revenue', value: fmt$(tiktokLiveSummary.revenue), tone: 'var(--text-primary)', view: 'revenue' },
                        { label: 'Profit', value: fmt$(tiktokLiveSummary.profit), tone: Number(tiktokLiveSummary.profit) < 0 ? '#dc2626' : '#059669', view: 'profit' },
                        { label: 'COG', value: fmt$(tiktokCog), tone: 'var(--text-primary)' },
                        { label: 'Orders', value: String(tiktokLiveSummary.pending + tiktokLiveSummary.confirmed), tone: 'var(--text-primary)', view: 'orders' },
                        { label: 'Cancelled', value: String(tiktokLiveSummary.cancelled), tone: tiktokLiveSummary.cancelled > 0 ? '#dc2626' : 'var(--text-primary)', view: 'cancelled' },
                        { label: 'Customers', value: String(tiktokLiveSummary.customers.size), tone: 'var(--text-primary)', view: 'customers' },
                        { label: 'Avg Sale', value: fmt$(tiktokAvgSale), tone: 'var(--text-primary)' },
                        { label: 'Attention', value: String(tiktokNeedsAttentionRows.length), tone: tiktokNeedsAttentionRows.length > 0 ? '#d97706' : 'var(--text-primary)', view: 'needs_attention' },
                      ].map((kpi) => (
                        <button
                          key={kpi.label}
                          type="button"
                          onClick={() => {
                            if (!kpi.view) return;
                            setTikTokKpiView(kpi.view);
                            if (kpi.view !== 'customers') setTikTokCustomerContext(null);
                          }}
                          style={{ border: '1px solid #f1e7d5', borderRadius: 10, background: tiktokKpiView === kpi.view ? '#fff7ed' : '#fffdfa', padding: '8px 9px', textAlign: 'left', cursor: kpi.view ? 'pointer' : 'default' }}
                        >
                          <div style={{ fontSize: '0.55rem', fontWeight: 900, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{kpi.label}</div>
                          <div style={{ marginTop: 4, fontSize: '0.92rem', fontWeight: 900, fontVariantNumeric: 'tabular-nums', color: kpi.tone }}>{kpi.value}</div>
                        </button>
                      ))}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {tiktokComparisonCards.filter((card) => card.label !== 'Position check').slice(0, 5).map((card) => (
                        <span key={card.label} title={card.detail || ''} style={{ fontSize: '0.66rem', fontWeight: 850, color: card.tone, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 999, padding: '4px 8px' }}>
                          {card.label}: {card.value}
                        </span>
	                      ))}
	                    </div>
	                  </div>
		                  </div>
		                </div>
	              </div>
	            </div>

	          <div style={{ display: 'grid', gridTemplateColumns: viewportWidth < 1380 ? 'minmax(0, 1fr)' : 'minmax(0, calc(100% - 346px)) 330px', gap: 16, height: viewportWidth < 1380 ? 'auto' : 'calc(100vh - 252px)', minHeight: viewportWidth < 1380 ? 0 : 420, maxHeight: viewportWidth < 1380 ? 'none' : 'calc(100vh - 252px)', flex: 1, maxWidth: '100%', overflow: 'hidden', alignItems: 'stretch' }}>
            <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
              <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-default)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontSize: '0.66rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Live Lot Sheet</div>
                  <div style={{ marginTop: 4, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                    {isGoingLive ? `${liveRows.length} rows · ${scannedTikTokRows.length} scanned · buyer data fills as orders sync` : 'Start the session, then scan each sold lot barcode in sequence.'}
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  <span style={{ ...compactBadgeStyle, background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe' }}>{isGoingLive ? `${liveRows.length} lots` : 'Draft workspace'}</span>
                  <span style={{ ...compactBadgeStyle, background: '#ecfdf3', color: '#047857', border: '1px solid #86efac' }}>{scannedTikTokRows.length} scanned</span>
                </div>
              </div>

              <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                {isGoingLive && liveRows.length > 0 ? (
                  <div style={{ height: '100%', overflow: 'auto' }}>
	                    <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', minWidth: 800 }}>
	                      <colgroup>
	                        <col style={{ width: '44px' }} />
	                        <col style={{ width: '118px' }} />
	                        <col style={{ width: '252px' }} />
	                        <col style={{ width: '60px' }} />
	                        <col style={{ width: '142px' }} />
	                        <col style={{ width: '66px' }} />
	                        <col style={{ width: '66px' }} />
	                        <col style={{ width: '82px' }} />
	                        <col style={{ width: '46px' }} />
	                      </colgroup>
	                      <thead>
	                        <tr style={{ background: '#FDFCFF', position: 'sticky', top: 0, zIndex: 2 }}>
	                          {['Lot', 'Barcode', 'Product', 'Cost', 'Buyer', 'Price', 'Profit', 'Status', ''].map((h) => (
	                            <th key={h} style={{ padding: '10px 10px', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)', textAlign: 'left', borderBottom: '1px solid var(--border-default)', whiteSpace: 'nowrap' }}>{h}</th>
	                          ))}
                        </tr>
                      </thead>
                      <tbody>
	                        {tiktokDisplayRows.map((row, index) => {
	                          const sourceIndex = Number(row._sourceIndex ?? index);
	                          const rowProfit = tiktokRowProfit(row);
	                          const reviewLater = isTikTokRowReviewLater(row);
	                          const isCancelledOrder = String(row?.statusFamily || row?.tiktokOrder?.statusFamily || '').toLowerCase() === 'cancelled';
	                          const isPaymentFailedOrder = isTikTokPaymentFailedRow(row);
	                          const isLossRow = row.tiktokOrder && rowProfit < 0 && !isPaymentFailedOrder;
	                          const isProfitRow = row.tiktokOrder && rowProfit > 0 && !isCancelledOrder && !isPaymentFailedOrder;
	                          const soldCount = Number(tiktokSoldCountByProduct.get(tiktokProductKey(row)) || 0);
	                          const rowSellerSku = tiktokDisplaySellerSku(row);
	                          const rowOrderId = String(row?.tiktokOrder?.orderId || row?.tiktokOrder?.orderNumber || row?.orderId || '').trim();
	                          const inlineOrderStatus = tiktokInlineOrderStatus(row);
                              const rowStatusLabel = isPaymentFailedOrder
                                ? 'Pay fail'
                                : isCancelledOrder
                                  ? 'Cancelled'
                                  : inlineOrderStatus === 'paid'
                                    ? 'To ship'
                                    : inlineOrderStatus === 'pending'
                                      ? 'Pending'
                                      : row.statusFamily === 'batch_mismatch'
                                        ? 'Batch mismatch'
                                        : row.statusFamily === 'review_later'
                                          ? 'Review'
                                          : row.tiktokOrder
                                            ? (row.statusLabel || 'To ship')
                                            : '';
                              const rowStatusTone = isPaymentFailedOrder
                                ? { color: '#b45309', border: '#fde68a', background: '#fffbeb' }
                                : isCancelledOrder
                                  ? { color: '#dc2626', border: '#fecaca', background: '#fff1f2' }
                                  : rowStatusLabel === 'To ship'
                                    ? { color: '#047857', border: '#bbf7d0', background: '#ecfdf3' }
                                    : rowStatusLabel
                                      ? { color: '#2563eb', border: '#c7d2fe', background: '#eef2ff' }
                                      : { color: 'var(--text-secondary)', border: 'transparent', background: 'transparent' };
			                          const rowBg = isPaymentFailedOrder ? '#fffbeb' : isLossRow ? '#fff1f2' : isProfitRow ? '#f0fdf4' : 'transparent';
			                          const stickyBg = isPaymentFailedOrder ? '#fffbeb' : isLossRow ? '#fff1f2' : isProfitRow ? '#f0fdf4' : row.match ? '#fcfffd' : '#ffffff';
			                          const isActiveProductSearch = showTikTokProductCatalog && Number(tiktokBarcodeSearchRow) === sourceIndex;
                              const isBarcodeDraftActive = Number(tiktokBarcodeDraft?.row) === sourceIndex;
                              const barcodeInputValue = isBarcodeDraftActive ? tiktokBarcodeDraft.value : row.barcode;
			                          return (
			                            <Fragment key={`lot-${row.lotNo}-${sourceIndex}`}>
		                            <tr style={{ borderBottom: isActiveProductSearch ? 'none' : '1px solid #F1EEFF', background: rowBg }}>
                              <td style={{ padding: '8px 10px', position: 'sticky', left: 0, zIndex: 1, background: stickyBg }}>
                                <input
                                  type="text"
                                  value={row.lotNo}
                                  onChange={(e) => tiktokUpdateRow(sourceIndex, 'lotNo', e.target.value)}
                                  data-manual-input="true"
                                  style={{ width: '100%', background: 'transparent', border: 'none', fontWeight: 800, fontSize: '0.76rem', color: 'var(--text-primary)', outline: 'none', padding: 0, fontVariantNumeric: 'tabular-nums' }}
                                />
                              </td>
                              <td style={{ padding: '8px 10px', position: 'sticky', left: 52, zIndex: 1, background: stickyBg }}>
	                                <input
	                                  ref={(node) => { if (node) tiktokBarcodeRefs.current[sourceIndex] = node; else delete tiktokBarcodeRefs.current[sourceIndex]; }}
	                                  type="text"
	                                  value={barcodeInputValue}
	                                  autoComplete="off"
	                                  onFocus={() => {
	                                    setTikTokBarcodeSearchRow(sourceIndex);
                                      setTikTokBarcodeDraft({ row: sourceIndex, value: String(row.barcode || '') });
                                    }}
	                                  onChange={(e) => {
	                                    const v = e.target.value;
	                                    if (/[\r\n]/.test(v)) {
	                                      commitTikTokBarcodeInput(sourceIndex, v);
	                                      return;
	                                    }
	                                    setTikTokBarcodeSearchRow(sourceIndex);
                                      setTikTokBarcodeDraft({ row: sourceIndex, value: v });
	                                  }}
	                                  onBlur={(e) => {
	                                    const value = String(e.target.value || '').trim();
	                                    if (!value) {
                                        clearTikTokBarcodeDraft(sourceIndex);
                                        tiktokUpdateRow(sourceIndex, 'barcode', '');
	                                      if (tiktokBarcodeSearchRow === sourceIndex) setTikTokBarcodeSearchRow(null);
	                                      return;
	                                    }
	                                    if (!isProductNameSearch(value, tiktokInventoryMap)) {
	                                      commitTikTokBarcodeInput(sourceIndex, value);
	                                    }
	                                  }}
	                                  onKeyDown={(e) => {
	                                    if (e.key === 'Enter' || e.key === 'Tab') {
	                                      e.preventDefault();
	                                      const value = String(e.currentTarget.value || '').trim();
	                                      commitTikTokBarcodeInput(sourceIndex, value);
	                                    }
	                                    if (e.key === 'Escape' && tiktokBarcodeSearchRow === sourceIndex) {
                                      clearTikTokBarcodeDraft(sourceIndex);
	                                      setTikTokBarcodeSearchRow(null);
	                                    }
	                                  }}
                                  placeholder="Scan barcode or search product"
                                  style={{ width: '100%', background: 'transparent', border: 'none', fontSize: '0.74rem', color: 'var(--text-primary)', outline: 'none', padding: 0, fontFamily: 'monospace' }}
                                />
                              </td>
                              <td style={{ padding: '8px 10px', overflow: 'hidden' }}>
                                {row.productName || row.match?.name ? (
                                  <div style={{ display: 'grid', gap: 3 }}>
                                    <span style={{ fontSize: '0.76rem', color: 'var(--text-primary)', fontWeight: row.match ? 700 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}>
                                      {shortDisplayProductName(row.productName || row.match?.name)}
                                    </span>
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                                      {row.match ? (
                                        <span style={{ fontSize: '0.66rem', color: Number(row.liveRemainingQty || 0) <= 0 ? '#dc2626' : '#059669', fontWeight: 700, whiteSpace: 'nowrap' }}>
                                          {Math.max(0, Number(row.liveRemainingQty || 0))} left in inventory
                                        </span>
                                      ) : null}
                                      {soldCount > 0 ? (
                                        <span style={{ fontSize: '0.66rem', color: '#4338ca', fontWeight: 700, whiteSpace: 'nowrap' }}>
                                          Sold {soldCount} this live
                                        </span>
                                      ) : null}
                                    </div>
                                  </div>
                                ) : (
                                  <span style={{ fontSize: '0.72rem', color: reviewLater ? '#d97706' : 'var(--text-secondary)', fontStyle: 'italic' }}>{reviewLater ? 'Review later' : (String(row.barcode || '').trim() ? 'No match' : 'Waiting…')}</span>
                                )}
                              </td>
                              <td style={{ padding: '8px 10px', fontSize: '0.74rem', fontVariantNumeric: 'tabular-nums', color: 'var(--text-secondary)' }}>{Number(row.cost || row.match?.cost_price || 0) ? fmt$(row.cost || row.match?.cost_price) : '—'}</td>
	                              <td style={{ padding: '8px 10px' }}>
	                                {row.tiktokOrder
		                                  ? <button type="button" onClick={() => openTikTokCustomerContext(row)} style={{ background: 'none', border: 'none', cursor: tiktokRowBuyer(row) ? 'pointer' : 'default', padding: 0, textAlign: 'left', width: '100%', display: 'grid', gap: 2 }}>
	                                      <span style={{ display: 'flex', alignItems: 'center', gap: 5, minWidth: 0 }}>
	                                        <span style={{ fontSize: '0.74rem', fontWeight: 800, color: isPaymentFailedOrder ? '#b45309' : isCancelledOrder ? '#dc2626' : '#6C47FF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
	                                          {tiktokRowBuyer(row) || (isCancelledOrder ? 'Cancelled buyer unknown' : '—')}
	                                        </span>
	                                      </span>
	                                      {(rowSellerSku || rowOrderId) ? (
	                                        <span style={{ fontSize: '0.61rem', color: 'var(--text-secondary)', fontWeight: 700, fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
	                                          {rowSellerSku ? `SKU ${rowSellerSku}` : ''}
	                                          {rowSellerSku && rowOrderId ? ' · ' : ''}
	                                          {rowOrderId ? `Order ${rowOrderId}` : ''}
	                                        </span>
	                                      ) : null}
	                                    </button>
	                                  : <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>—</span>}
	                              </td>
                              <td style={{ padding: '8px 10px', fontSize: '0.74rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: 'var(--text-primary)' }}>
                                {row.tiktokOrder ? fmt$(row.tiktokOrder.salePrice || row.salesPrice || 0) : '—'}
                              </td>
		                              <td style={{ padding: '8px 10px', fontSize: '0.74rem', fontWeight: 800, fontVariantNumeric: 'tabular-nums', color: isPaymentFailedOrder ? '#b45309' : isLossRow ? '#dc2626' : rowProfit > 0 ? '#059669' : 'var(--text-secondary)' }}>
		                                {row.tiktokOrder ? fmt$(rowProfit) : '—'}
		                              </td>
                              <td style={{ padding: '8px 8px' }}>
                                {rowStatusLabel ? (
                                  <span style={{
                                    display: 'inline-flex',
                                    maxWidth: '100%',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    padding: '4px 7px',
                                    borderRadius: 999,
                                    border: `1px solid ${rowStatusTone.border}`,
                                    background: rowStatusTone.background,
                                    color: rowStatusTone.color,
                                    fontSize: '0.58rem',
                                    fontWeight: 900,
                                    lineHeight: 1,
                                    textTransform: 'uppercase',
                                    whiteSpace: 'nowrap',
                                  }}>
                                    {rowStatusLabel}
                                  </span>
                                ) : (
                                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>—</span>
                                )}
                              </td>
                              <td style={{ padding: '8px 8px' }}>
                                {isTikTokRowFilled(row) ? (
                                  <button type="button" onClick={() => tiktokClearLot(sourceIndex)} style={{ fontSize: '0.62rem', fontWeight: 700, padding: '4px 7px', borderRadius: 8, border: '1px solid var(--border-default)', background: '#fff', cursor: 'pointer', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                                    Clear
                                  </button>
                                ) : null}
                              </td>
	                            </tr>
                              {isActiveProductSearch ? (
                                <tr style={{ background: '#fffbff', borderBottom: '1px solid #F1EEFF' }}>
                                  <td colSpan={9} style={{ padding: '0 10px 12px 62px' }}>
                                    <div style={{ maxWidth: 760, border: '1px solid #ddd6fe', borderRadius: 14, background: '#fff', boxShadow: '0 16px 34px rgba(76,29,149,0.14)', overflow: 'hidden' }}>
                                      <div style={{ padding: '10px 12px', borderBottom: '1px solid #f1eeff', background: '#faf5ff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                                        <div style={{ minWidth: 0 }}>
                                          <div style={{ fontSize: '0.62rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6C47FF' }}>
                                            Lot {row.lotNo || '—'} product search
                                          </div>
                                          <div style={{ marginTop: 2, fontSize: '0.74rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                                            {activeTikTokProductQuery}
                                          </div>
                                        </div>
                                        <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                                          Enter uses best match
                                        </div>
                                      </div>
                                      <div style={{ display: 'grid', gap: 6, padding: 8, maxHeight: 260, overflowY: 'auto' }}>
                                        {activeTikTokCatalogRows.length ? activeTikTokCatalogRows.slice(0, 8).map(({ product, onHandQty, remainingInSession, soldCount }) => (
                                          <button
                                            key={`inline-lot-search-${product.id}`}
                                            type="button"
                                            onMouseDown={(event) => event.preventDefault()}
                                            onClick={() => tiktokSelectProductForLot(sourceIndex, product)}
                                            style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, alignItems: 'center', padding: '10px 12px', border: '1px solid #ede9fe', borderRadius: 10, background: '#fff', textAlign: 'left', cursor: 'pointer' }}
                                          >
                                            <div style={{ minWidth: 0 }}>
                                              <div style={{ fontSize: '0.78rem', fontWeight: 850, color: 'var(--text-primary)', lineHeight: 1.35, whiteSpace: 'normal' }}>
                                                {product.name}
                                              </div>
                                              <div style={{ marginTop: 5, display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                                                <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{productBarcode(product) || 'No code'}</span>
                                                <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>On hand <strong style={{ color: 'var(--text-primary)' }}>{onHandQty}</strong></span>
                                                <span style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>Left <strong style={{ color: remainingInSession <= 0 ? '#dc2626' : '#059669' }}>{remainingInSession}</strong></span>
                                                <span style={{ fontSize: '0.68rem', color: '#4338ca' }}>Sold <strong>{soldCount}</strong></span>
                                              </div>
                                            </div>
                                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>
                                              Use
                                            </span>
                                          </button>
                                        )) : (
                                          <div style={{ padding: '12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>
                                            No product-name matches found for this lot.
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              ) : null}
                              </Fragment>
	                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ padding: 18, display: 'grid', gap: 14 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 180px))', gap: 12 }}>
                      {[
                        { label: 'Next Lot', value: `#${liveRows[0]?.lotNo || '1'}` },
                        { label: 'Mode', value: tiktokDemoMode ? 'Demo' : 'Real' },
                        { label: 'Session', value: isGoingLive ? `#${activeTikTokSessionSequence}` : `Draft #${activeTikTokSessionSequence}` },
                      ].map((s) => (
                        <div key={s.label} style={{ padding: '14px 16px', border: '1px solid var(--border-default)', borderRadius: 12, background: '#fff' }}>
                          <div style={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 800 }}>{s.label}</div>
                          <div style={{ fontSize: '1.12rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: 6 }}>{s.value}</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ padding: '18px 20px', border: '1px dashed #d8ccff', borderRadius: 14, background: '#faf7ff', display: 'grid', gap: 10 }}>
                      <div style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6C47FF' }}>Scan-ready prep dock</div>
                      <div style={{ fontSize: '1.08rem', fontWeight: 800, color: 'var(--text-primary)' }}>Start the session, then scan each sold lot barcode in sequence.</div>
                      <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                        {tiktokDemoMode ? (
                          <>
                            Demo opens the same lot-1 workflow as a real session. It does not call TikTok, save orders, or deduct inventory.
                          </>
                        ) : (
                          <>
                            Use <strong>Go Live</strong> to open the session. The lot sheet will stay focused on the current row, buyer data will sync into the table, and the next lot advances automatically as the stream moves.
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateRows: 'auto', gap: 14, minHeight: 0, maxHeight: '100%', minWidth: 0, alignContent: 'start', overflowX: 'hidden', overflowY: viewportWidth < 1380 ? 'visible' : 'auto' }}>
              <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 14 }}>
                <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Inventory Search</div>
                <input
                  type="text"
                  className="input"
                  value={tiktokInventorySearch}
                  onChange={(e) => {
                    const nextValue = e.target.value;
                    setTikTokInventorySearch(nextValue);
                    const query = String(nextValue || '').trim().toLowerCase();
                    const previewRow = query
                      ? tiktokProductSearchRows
                        .map(({ product }) => ({ product, score: productSearchScore(product, query) }))
                        .filter(({ score }) => score > 0)
                        .sort((a, b) => b.score - a.score || liveInventoryQty(b.product) - liveInventoryQty(a.product) || String(a.product?.name || '').localeCompare(String(b.product?.name || '')))[0]
                      : null;
                    if (previewRow?.product) {
                      setTikTokInspectedProduct(previewRow.product);
                    } else {
                      setTikTokInspectedProduct(null);
                    }
                  }}
                  placeholder="Search product, barcode, SKU…"
                  data-manual-input="true"
                  style={{ height: 36, borderRadius: 10, fontSize: '0.8rem', padding: '0 10px', marginTop: 10 }}
                />
                <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 172, overflowY: 'auto' }}>
                  {tiktokInventorySearch
                    ? tiktokInventorySearchResults.length
                      ? tiktokInventorySearchResults.slice(0, 5).map(({ product, onHandQty, remainingInSession, soldCount }) => (
                        <button
                          key={`qs-${product.id}`}
                          type="button"
                          onClick={() => {
                            setTikTokInspectedProduct(product);
                          }}
                          style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'start', padding: '10px 10px', border: '1px solid var(--border-default)', borderRadius: 10, background: '#fff', textAlign: 'left', cursor: 'pointer' }}
                        >
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.25, whiteSpace: 'normal' }}>{product.name}</div>
                            <div style={{ marginTop: 4, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              <span style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>On hand <strong style={{ color: 'var(--text-primary)' }}>{onHandQty}</strong></span>
                              <span style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>Left <strong style={{ color: remainingInSession <= 0 ? '#dc2626' : '#059669' }}>{remainingInSession}</strong></span>
                              <span style={{ fontSize: '0.66rem', color: '#4338ca' }}>Sold <strong>{soldCount}</strong></span>
                            </div>
                          </div>
                          <span style={{ ...compactBadgeStyle, background: remainingInSession <= 0 ? '#fff1f2' : '#ecfdf3', color: remainingInSession <= 0 ? '#dc2626' : '#059669', border: `1px solid ${remainingInSession <= 0 ? '#fecaca' : '#bbf7d0'}` }}>
                            {remainingInSession <= 0 ? 'Empty' : 'Available'}
                          </span>
                        </button>
                      ))
                      : <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>No inventory match found.</div>
                    : <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Search a product to check on-hand stock and remaining quantity for this live.</div>}
	                </div>
		              </div>

	              {tiktokProductPreview ? (
	                <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 12, display: 'grid', gap: 9, minWidth: 0, overflow: 'visible' }}>
	                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
	                    <div style={{ minWidth: 0 }}>
	                      <div style={{ fontSize: '0.64rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#047857' }}>Product Info</div>
	                      <div style={{ marginTop: 5, fontSize: '0.8rem', fontWeight: 900, color: 'var(--text-primary)', lineHeight: 1.3, overflowWrap: 'anywhere' }}>{tiktokProductPreview.name}</div>
	                      <div style={{ marginTop: 4, fontSize: '0.66rem', color: 'var(--text-secondary)', fontFamily: 'monospace', overflowWrap: 'anywhere' }}>{productBarcode(tiktokProductPreview) || 'No barcode'}</div>
	                    </div>
	                    <span style={{ ...compactBadgeStyle, background: (tiktokProductPreviewStats?.remainingInSession || 0) <= 0 ? '#fff1f2' : '#ecfdf3', color: (tiktokProductPreviewStats?.remainingInSession || 0) <= 0 ? '#dc2626' : '#047857', border: `1px solid ${(tiktokProductPreviewStats?.remainingInSession || 0) <= 0 ? '#fecaca' : '#bbf7d0'}` }}>
	                      {tiktokProductPreviewStats?.remainingInSession ?? 0} left
	                    </span>
	                  </div>
	                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 5 }}>
	                    {[
	                      { label: 'On hand', value: tiktokProductPreviewStats?.onHandQty ?? liveInventoryQty(tiktokProductPreview) },
	                      { label: 'Sold live', value: tiktokProductPreviewStats?.soldCount ?? 0 },
	                      { label: 'Cost', value: Number(tiktokProductPreview.cost_price || 0) ? fmt$(tiktokProductPreview.cost_price) : '—' },
	                    ].map((metric) => (
	                      <div key={metric.label} style={{ border: '1px solid var(--border-default)', borderRadius: 9, padding: '6px 7px', background: '#FDFCFF', minWidth: 0 }}>
	                        <div style={{ fontSize: '0.54rem', fontWeight: 900, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{metric.label}</div>
	                        <div style={{ marginTop: 3, fontSize: '0.78rem', fontWeight: 900, color: 'var(--text-primary)' }}>{metric.value}</div>
	                      </div>
	                    ))}
	                  </div>
	                  {productDupeLabel(tiktokProductPreview) ? (
	                    <div style={{ border: '1px solid #dbeafe', borderRadius: 10, background: '#eff6ff', padding: '8px 9px' }}>
	                      <div style={{ fontSize: '0.56rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#2563eb' }}>Inspired by / dupe of</div>
	                      <div style={{ marginTop: 4, fontSize: '0.74rem', fontWeight: 850, color: '#1e3a8a', lineHeight: 1.35, overflowWrap: 'anywhere' }}>{productDupeLabel(tiktokProductPreview)}</div>
	                    </div>
	                  ) : null}
	                  {productFragranceNotesLabel(tiktokProductPreview) ? (
	                    <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', lineHeight: 1.4, overflowWrap: 'anywhere', maxHeight: 76, overflowY: 'auto' }}>
	                      <strong style={{ color: 'var(--text-primary)' }}>Fragrance notes:</strong> {productFragranceNotesLabel(tiktokProductPreview)}
	                    </div>
	                  ) : null}
	                  {tiktokProductClipboardText ? (
	                    <div style={{ borderTop: '1px solid var(--border-default)', paddingTop: 8, display: 'grid', gap: 6 }}>
	                      <div style={{ fontSize: '0.58rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Copy-ready note</div>
	                      <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', lineHeight: 1.35, overflowWrap: 'anywhere' }}>{tiktokProductClipboardText}</div>
	                      <button
	                        type="button"
	                        onClick={copyTikTokProductNotes}
	                        style={{ justifySelf: 'start', border: '1px solid #c7d2fe', background: tiktokCopiedProductNote ? '#ecfdf3' : '#eef2ff', color: tiktokCopiedProductNote ? '#047857' : '#4338ca', borderRadius: 9, padding: '6px 9px', fontSize: '0.68rem', fontWeight: 850, cursor: 'pointer' }}
	                      >
	                        {tiktokCopiedProductNote ? 'Copied' : 'Copy 100-char note'}
	                      </button>
	                    </div>
	                  ) : (
	                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>No fragrance notes or dupe research saved yet.</div>
	                  )}
	                </div>
	              ) : null}

	              {false && !tiktokCustomerContext ? (
	                <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 14, display: 'grid', gap: 12 }}>
	                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
	                    <div>
	                      <div style={{ fontSize: '0.64rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Live Stats</div>
	                      <div style={{ marginTop: 3, fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Click a buyer in the lot sheet for full profile.</div>
	                    </div>
	                    <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>
	                      {tiktokOrderRows.length} orders
	                    </span>
	                  </div>

	                  <div style={{ display: 'grid', gap: 10 }}>
	                    <div style={{ display: 'grid', gap: 6 }}>
	                      <div style={{ fontSize: '0.58rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#5b21b6' }}>Top Buyers</div>
	                      {tiktokTopCustomerRows.length ? tiktokTopCustomerRows.map((row) => (
	                        <button
	                          key={`top-buyer-${row.key}`}
	                          type="button"
	                          onClick={() => setTikTokCustomerContext({ buyer: row.buyer, username: cleanTikTokBuyer(row.buyer), orderId: '', lotNo: '' })}
	                          style={{ border: '1px solid #ede9fe', borderRadius: 10, background: '#faf5ff', padding: '8px 9px', textAlign: 'left', cursor: 'pointer', display: 'grid', gap: 5 }}
	                        >
	                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
	                            <span style={{ fontSize: '0.74rem', fontWeight: 900, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.buyer}</span>
	                            <span style={{ fontSize: '0.74rem', fontWeight: 900, color: '#5b21b6', flexShrink: 0 }}>{fmt$(row.revenue)}</span>
	                          </div>
	                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
	                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{row.liveOrders} lots</span>
	                            <span style={{ ...compactBadgeStyle, background: row.profit < 0 ? '#fff1f2' : '#ecfdf3', color: row.profit < 0 ? '#dc2626' : '#047857', border: `1px solid ${row.profit < 0 ? '#fecaca' : '#86efac'}` }}>{fmt$(row.profit)} profit</span>
	                          </div>
	                        </button>
	                      )) : (
	                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Top buyers appear after synced orders arrive.</div>
	                      )}
	                    </div>

	                    <div style={{ display: 'grid', gap: 6 }}>
	                      <div style={{ fontSize: '0.58rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#047857' }}>Most Sold Products</div>
	                      {tiktokMostSoldProducts.length ? tiktokMostSoldProducts.map((row) => (
	                        <div key={`most-sold-${row.key}`} style={{ border: '1px solid var(--border-default)', borderRadius: 10, background: '#fff', padding: '8px 9px', display: 'grid', gap: 4 }}>
	                          <div style={{ fontSize: '0.72rem', fontWeight: 850, color: 'var(--text-primary)', lineHeight: 1.25 }}>{row.productName}</div>
	                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: '0.66rem', color: 'var(--text-secondary)' }}>
	                            <span>{row.soldCount} sold · {fmt$(row.totalRevenue)}</span>
	                            <span style={{ fontWeight: 900, color: row.totalProfit < 0 ? '#dc2626' : '#059669' }}>{fmt$(row.totalProfit)}</span>
	                          </div>
	                        </div>
	                      )) : (
	                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Most-sold products appear after sales sync.</div>
	                      )}
	                    </div>

	                    {tiktokLossProductRows.length ? (
	                      <div style={{ display: 'grid', gap: 6 }}>
	                        <div style={{ fontSize: '0.58rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#dc2626' }}>Loss Makers</div>
	                        {tiktokLossProductRows.map((row) => (
	                          <div key={`loss-maker-${row.key}`} style={{ border: '1px solid #fecaca', borderRadius: 10, background: '#fff1f2', padding: '8px 9px', display: 'grid', gap: 4 }}>
	                            <div style={{ fontSize: '0.72rem', fontWeight: 850, color: '#7f1d1d', lineHeight: 1.25 }}>{row.productName}</div>
	                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: '0.66rem', color: '#991b1b' }}>
	                              <span>{row.soldCount} sold · cost {fmt$(row.totalCost)}</span>
	                              <span style={{ fontWeight: 900 }}>{fmt$(row.totalProfit)}</span>
	                            </div>
	                          </div>
	                        ))}
	                      </div>
	                    ) : null}
	                  </div>
	                </div>
	              ) : null}

	              {false && !tiktokCustomerContext && tiktokAbuseRiskRows.length ? (
	                <div className="panel" style={{ borderRadius: 16, border: '1px solid #fed7aa', background: '#fffaf0', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 14 }}>
	                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
	                    <div>
	                      <div style={{ fontSize: '0.64rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#b45309' }}>Buyer Risk</div>
	                      <div style={{ marginTop: 3, fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Most cancellations and payment failures in this live.</div>
	                    </div>
	                    <span style={{ ...compactBadgeStyle, background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74' }}>
	                      {tiktokPaymentFailedRows.length} pay fail
	                    </span>
	                  </div>
	                  <div style={{ marginTop: 10, display: 'grid', gap: 7 }}>
	                    {tiktokAbuseRiskRows.map((row) => {
	                      const risky = row.paymentFailed > 0 || row.cancelled >= 2 || row.cancelledRate >= 0.5;
	                      return (
	                        <button
	                          key={`risk-${row.key}`}
	                          type="button"
	                          onClick={() => setTikTokCustomerContext({ buyer: row.buyer, username: cleanTikTokBuyer(row.buyer), orderId: '', lotNo: '' })}
	                          style={{ border: `1px solid ${risky ? '#fdba74' : 'var(--border-default)'}`, borderRadius: 9, background: '#fff', padding: '8px 9px', textAlign: 'left', cursor: 'pointer', display: 'grid', gap: 5 }}
	                        >
	                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
	                            <span style={{ fontSize: '0.74rem', fontWeight: 900, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.buyer}</span>
	                            {risky ? <span style={{ fontSize: '0.58rem', fontWeight: 900, color: '#c2410c', whiteSpace: 'nowrap' }}>Review/block</span> : null}
	                          </div>
	                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
	                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{row.liveOrders} orders</span>
	                            {row.cancelled > 0 ? <span style={{ ...compactBadgeStyle, background: '#fff1f2', color: '#dc2626', border: '1px solid #fecaca' }}>{row.cancelled} cancels</span> : null}
	                            {row.paymentFailed > 0 ? <span style={{ ...compactBadgeStyle, background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a' }}>{row.paymentFailed} pay fails</span> : null}
	                          </div>
	                        </button>
	                      );
	                    })}
	                  </div>
	                </div>
	              ) : null}

	              {tiktokCustomerContext ? (
	                <div className="panel" style={{ borderRadius: 16, border: '1px solid var(--border-default)', background: '#fff', boxShadow: '0 8px 24px rgba(15,23,42,0.06)', padding: 14 }}>
	                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
	                    <div style={{ minWidth: 0 }}>
	                      <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Customer Info</div>
	                      <div style={{ marginTop: 5, fontSize: '0.92rem', fontWeight: 900, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
	                        {selectedTikTokCustomer?.display_name || selectedTikTokCustomer?.name || tiktokCustomerContext.buyer}
	                      </div>
	                      <div style={{ marginTop: 2, fontSize: '0.7rem', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
	                        {selectedTikTokPhone || selectedTikTokEmail || selectedTikTokAddress || (tiktokCustomerLoading ? 'Loading history…' : 'No contact info on file')}
	                      </div>
	                    </div>
	                    <button
	                      type="button"
	                      onClick={() => setTikTokCustomerContext(null)}
	                      style={{ border: '1px solid var(--border-default)', background: '#fff', borderRadius: 8, height: 26, padding: '0 8px', fontSize: '0.68rem', fontWeight: 800, color: 'var(--text-secondary)', cursor: 'pointer' }}
	                    >
	                      Close
	                    </button>
	                  </div>
	                  {(selectedTikTokPhone || selectedTikTokEmail || selectedTikTokAddress) ? (
	                    <div style={{ marginTop: 10, border: '1px solid var(--border-default)', borderRadius: 10, background: '#FDFCFF', padding: '8px 9px', display: 'grid', gap: 5 }}>
	                      {selectedTikTokPhone ? (
	                        <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>Phone:</strong> {selectedTikTokPhone}</div>
	                      ) : null}
	                      {selectedTikTokEmail ? (
	                        <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}><strong style={{ color: 'var(--text-primary)' }}>Email:</strong> {selectedTikTokEmail}</div>
	                      ) : null}
	                      {selectedTikTokAddress ? (
	                        <div style={{ fontSize: '0.68rem', color: 'var(--text-secondary)', lineHeight: 1.35 }}><strong style={{ color: 'var(--text-primary)' }}>Address:</strong> {selectedTikTokAddress}</div>
	                      ) : null}
	                    </div>
	                  ) : null}
	                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 6, marginTop: 10 }}>
	                    {[
	                      { label: 'Live', value: selectedTikTokBuyerRows.length },
	                      { label: 'Active', value: fmt$(selectedTikTokBuyerTotal) },
	                      { label: 'Cancelled', value: selectedTikTokBuyerCancelledRows.length, danger: selectedTikTokBuyerCancelledRows.length > 0 },
	                      { label: 'Pay Fail', value: selectedTikTokBuyerPaymentFailedRows.length, warn: selectedTikTokBuyerPaymentFailedRows.length > 0 },
	                      { label: 'History', value: tiktokCustomerLoading ? '…' : tiktokCustomerOrders.length },
	                    ].map((metric) => (
	                      <div key={metric.label} style={{ border: '1px solid var(--border-default)', borderRadius: 8, padding: '7px 8px', background: metric.danger ? '#fff1f2' : metric.warn ? '#fffbeb' : '#FDFCFF' }}>
	                        <div style={{ fontSize: '0.54rem', fontWeight: 900, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{metric.label}</div>
	                        <div style={{ marginTop: 3, fontSize: '0.78rem', fontWeight: 900, color: metric.danger ? '#dc2626' : metric.warn ? '#b45309' : 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{metric.value}</div>
	                      </div>
	                    ))}
	                  </div>
	                  {selectedTikTokBuyerCancelledRows.length ? (
	                    <div style={{ marginTop: 9, border: '1px solid #fecaca', borderRadius: 9, background: '#fff1f2', padding: '8px 9px' }}>
	                      <div style={{ fontSize: '0.58rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#dc2626' }}>Cancelled in this live</div>
	                      <div style={{ marginTop: 5, display: 'grid', gap: 4 }}>
	                        {selectedTikTokBuyerCancelledRows.slice(0, 4).map((row) => (
	                          <div key={`side-cancel-${row.lotNo}-${row?.tiktokOrder?.orderId || row.productName}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: '0.7rem', color: '#7f1d1d' }}>
	                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>L{row.lotNo} · {shortDisplayProductName(row.productName || row.match?.name || 'Unknown product')}</span>
	                            <span style={{ flexShrink: 0 }}>{fmt$(row?.tiktokOrder?.salePrice || row.salesPrice || 0)}</span>
	                          </div>
	                        ))}
	                      </div>
	                    </div>
	                  ) : null}
	                  <div style={{ marginTop: 10, display: 'grid', gap: 8 }}>
	                    <div style={{ fontSize: '0.62rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Previous Orders</div>
	                    {tiktokCustomerLoading ? (
	                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Loading customer history…</div>
	                    ) : tiktokCustomerOrders.length ? (
	                      <div style={{ display: 'grid', gap: 6, maxHeight: 178, overflowY: 'auto' }}>
	                        {tiktokCustomerOrders.slice(0, 6).map((order) => (
	                          <div key={`side-order-${order.id || order.order_number || order.external_order_ref}`} style={{ border: '1px solid var(--border-default)', borderRadius: 10, padding: '8px 9px', background: '#fff', display: 'grid', gap: 6 }}>
	                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
	                              <span style={{ fontSize: '0.72rem', fontWeight: 800, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{order.order_number || order.external_order_ref || `Order ${order.id}`}</span>
	                              <span style={{ fontSize: '0.72rem', fontWeight: 900, color: '#5b21b6', flexShrink: 0 }}>{fmt$(order.total_amount || order.amount_total || order.subtotal || 0)}</span>
	                            </div>
	                            <div style={{ display: 'grid', gap: 5 }}>
	                              {(() => {
	                                const orderKey = String(order.id || order.order_number || order.external_order_ref || '').trim();
	                                const lines = (Array.isArray(order.lines) && order.lines.length ? order.lines : (tiktokCustomerOrderLinesById[orderKey] || [])).slice(0, 4);
	                                return lines.length ? lines.map((line, lineIndex) => {
	                                  const lineName = shortDisplayProductName(line.product_name || line.productName || line.name || line.display_name || line.product_display_name || line.description || '');
	                                  const tikTokOrderId = line.tiktok_order_id || line.external_order_ref || order.external_order_ref || order.marketplace_order_id || order.tiktok_order_id || order.order_id || '';
	                                  const sessionLabel = order.session_name || order.session_title || (order.session_id ? `Go Live Session ${order.session_id}` : '');
	                                  return (
	                                    <div key={`side-order-line-${orderKey}-${line.id || lineIndex}`} style={{ borderTop: lineIndex ? '1px solid #F1EEFF' : 'none', paddingTop: lineIndex ? 5 : 0 }}>
	                                      <div style={{ fontSize: '0.7rem', fontWeight: 850, color: 'var(--text-primary)', lineHeight: 1.25 }}>
	                                        {lineName || 'Unknown product'}
	                                      </div>
	                                      <div style={{ marginTop: 2, display: 'flex', flexWrap: 'wrap', gap: 6, fontSize: '0.61rem', color: 'var(--text-secondary)' }}>
	                                        {tikTokOrderId ? <span>TikTok {tikTokOrderId}</span> : null}
	                                        {sessionLabel ? <span>{sessionLabel}</span> : null}
	                                        {line.quantity || line.qty ? <span>Qty {Number(line.quantity || line.qty || 1)}</span> : null}
	                                      </div>
	                                    </div>
	                                  );
	                                }) : (
	                                  <div style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>
	                                    {order.state || order.fulfillment_status || 'sale'} · Product lines not loaded
	                                  </div>
	                                );
	                              })()}
	                            </div>
	                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, fontSize: '0.61rem', color: 'var(--text-secondary)' }}>
	                              <span>{order.state || order.fulfillment_status || 'sale'}</span>
	                              {order.ordered_at || order.created_at ? <span>{new Date(order.ordered_at || order.created_at).toLocaleDateString()}</span> : null}
	                            </div>
	                          </div>
	                        ))}
	                      </div>
	                    ) : (
	                      <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>No previous TikTok orders found for this username.</div>
	                    )}
	                  </div>
	                </div>
	              ) : null}

	            </div>
	          </div>

          {tiktokKpiView ? (
            <div style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', justifyContent: 'flex-end', background: 'rgba(15,23,42,0.18)' }}>
              <button
                type="button"
                aria-label="Close drilldown"
                onClick={() => setTikTokKpiView(null)}
                style={{ position: 'absolute', inset: 0, border: 'none', background: 'transparent', cursor: 'pointer' }}
              />
              <div style={{ position: 'relative', width: 'min(1180px, 82vw)', height: '100%', background: '#fff', borderLeft: '1px solid var(--border-default)', boxShadow: '-18px 0 42px rgba(15,23,42,0.12)', display: 'grid', gridTemplateColumns: '176px minmax(0, 1fr)', overflow: 'hidden' }}>
                <div style={{ borderRight: '1px solid var(--border-default)', background: '#fcfbff', padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontSize: '0.66rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)', padding: '2px 4px 8px' }}>Drilldown</div>
                  {tiktokKpiTabs.map((tab) => (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => setTikTokKpiView(tab.key)}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr auto',
                        gap: 8,
                        alignItems: 'center',
                        padding: '10px 11px',
                        borderRadius: 10,
                        border: `1px solid ${tiktokKpiView === tab.key ? '#c4b5fd' : 'var(--border-default)'}`,
                        background: tiktokKpiView === tab.key ? '#f5f0ff' : '#fff',
                        color: tiktokKpiView === tab.key ? '#5b21b6' : 'var(--text-primary)',
                        fontSize: '0.76rem',
                        fontWeight: 700,
                        textAlign: 'left',
                        cursor: 'pointer',
                      }}
                    >
                      <span>{tab.label}</span>
                      <span style={{ ...compactBadgeStyle, background: tiktokKpiView === tab.key ? '#ede9fe' : '#f8fafc', color: tiktokKpiView === tab.key ? '#5b21b6' : 'var(--text-secondary)', border: `1px solid ${tiktokKpiView === tab.key ? '#ddd6fe' : 'var(--border-default)'}` }}>{tab.count}</span>
                    </button>
                  ))}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0 }}>
                  <div style={{ padding: '16px 18px', borderBottom: '1px solid var(--border-default)', display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, alignItems: 'start' }}>
                    <div style={{ display: 'grid', gap: 10 }}>
                      <div>
                        <div style={{ fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
                          {tiktokKpiTabs.find((tab) => tab.key === tiktokKpiView)?.label || 'Drilldown'}
                        </div>
                        <div style={{ marginTop: 4, fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                          {tiktokKpiView === 'revenue' && 'Sold Products'}
                          {tiktokKpiView === 'profit' && 'Highest Profit Products'}
                          {tiktokKpiView === 'orders' && 'Customer Orders'}
                          {tiktokKpiView === 'cancelled' && 'Cancelled Orders'}
                          {tiktokKpiView === 'customers' && 'Customer Roster'}
                          {tiktokKpiView === 'needs_attention' && 'Needs Attention'}
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {tiktokKpiView === 'revenue' ? (
                          <>
                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>Revenue {fmt$(tiktokLiveSummary.revenue)}</span>
                            <span style={{ ...compactBadgeStyle, background: '#ecfdf3', color: '#047857', border: '1px solid #86efac' }}>Profit {fmt$(tiktokLiveSummary.profit)}</span>
                            <span style={{ ...compactBadgeStyle, background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74' }}>{tiktokRevenueRows.length} sold rows</span>
                          </>
                        ) : null}
                        {tiktokKpiView === 'profit' ? (
                          <>
                            <span style={{ ...compactBadgeStyle, background: '#ecfdf3', color: '#047857', border: '1px solid #86efac' }}>Top profit {fmt$(tiktokProfitRows[0]?.totalProfit || 0)}</span>
                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{tiktokProfitRows.length} grouped products</span>
                          </>
                        ) : null}
                        {tiktokKpiView === 'orders' ? (
                          <>
                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{tiktokOrderRows.length} orders</span>
                            <span style={{ ...compactBadgeStyle, background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74' }}>{tiktokLiveSummary.customers.size} customers</span>
                          </>
                        ) : null}
                        {tiktokKpiView === 'cancelled' ? (
                          <span style={{ ...compactBadgeStyle, background: '#fff1f2', color: '#dc2626', border: '1px solid #fecaca' }}>{tiktokCancelledRows.length} cancelled rows</span>
                        ) : null}
                        {tiktokKpiView === 'customers' ? (
                          <>
                            <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{tiktokCustomerRoster.length} live customers</span>
                            <span style={{ ...compactBadgeStyle, background: '#ecfdf3', color: '#047857', border: '1px solid #86efac' }}>{tiktokCustomerOrders.length} loaded history rows</span>
                          </>
                        ) : null}
                        {tiktokKpiView === 'needs_attention' ? (
                          <span style={{ ...compactBadgeStyle, background: '#fff7ed', color: '#c2410c', border: '1px solid #fdba74' }}>{tiktokNeedsAttentionRows.length} open items</span>
                        ) : null}
                      </div>
                    </div>
                    <button type="button" onClick={() => setTikTokKpiView(null)} style={{ height: 34, padding: '0 14px', borderRadius: 10, border: '1px solid var(--border-default)', background: '#fff', fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-secondary)', cursor: 'pointer' }}>
                      Close
                    </button>
                  </div>

                  <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: 18 }}>
                    {tiktokKpiView === 'revenue' ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ background: '#FDFCFF' }}>
                            {['Lot', 'Product', 'Cost', 'Retail', 'Sale', 'Profit', 'Customer', 'Sold'].map((label) => (
                              <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tiktokRevenueRows.map((row) => (
                            <tr key={`${row.orderId || row.lotNo}-${row.barcode}`} style={{ borderBottom: '1px solid #F1EEFF' }}>
                              <td style={{ padding: '10px 12px', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>#{row.lotNo}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.75rem', color: 'var(--text-primary)', fontWeight: 700 }}>{row.productName}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{fmt$(row.cost)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{fmt$(row.retail)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: '#5b21b6', fontWeight: 800 }}>{fmt$(row.salePrice)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: row.profit < 0 ? '#dc2626' : '#059669', fontWeight: 800 }}>{fmt$(row.profit)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)' }}>{row.customer}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{row.soldCount}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}

                    {tiktokKpiView === 'profit' ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ background: '#FDFCFF' }}>
                            {['Product', 'Sold', 'Revenue', 'Cost', 'Profit'].map((label) => (
                              <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tiktokProfitRows.map((row) => (
                            <tr key={row.key} style={{ borderBottom: '1px solid #F1EEFF' }}>
                              <td style={{ padding: '10px 12px', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>{row.productName}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{row.soldCount}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: '#5b21b6', fontWeight: 800 }}>{fmt$(row.totalRevenue)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{fmt$(row.totalCost)}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: row.totalProfit < 0 ? '#dc2626' : '#059669', fontWeight: 800 }}>{fmt$(row.totalProfit)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}

                    {tiktokKpiView === 'orders' ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ background: '#FDFCFF' }}>
                            {['Lot', 'Customer', 'Product', 'Order ID', 'Sale', 'Status'].map((label) => (
                              <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tiktokOrderRows.map((row) => (
                            <tr key={`${row.orderId || row.lotNo}-${row.productName}`} style={{ borderBottom: '1px solid #F1EEFF' }}>
                              <td style={{ padding: '10px 12px', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>#{row.lotNo}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)' }}>{row.customer}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)', fontWeight: 700 }}>{row.productName}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.72rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{row.orderId || '—'}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: '#5b21b6', fontWeight: 800 }}>{fmt$(row.salePrice)}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <span style={{ ...compactBadgeStyle, background: row.statusFamily === 'cancelled' ? '#fff1f2' : '#eef2ff', color: row.statusFamily === 'cancelled' ? '#dc2626' : '#2563eb', border: `1px solid ${row.statusFamily === 'cancelled' ? '#fecaca' : '#c7d2fe'}` }}>{row.statusLabel}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}

                    {tiktokKpiView === 'cancelled' ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ background: '#FDFCFF' }}>
                            {['Lot', 'Customer', 'Product', 'Order ID', 'Sale', 'Status'].map((label) => (
                              <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tiktokCancelledRows.map((row) => (
                            <tr key={`${row.orderId || row.lotNo}-${row.productName}`} style={{ borderBottom: '1px solid #F1EEFF' }}>
                              <td style={{ padding: '10px 12px', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>#{row.lotNo}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)' }}>{row.customer}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)', fontWeight: 700 }}>{row.productName}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.72rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{row.orderId || '—'}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{fmt$(row.salePrice)}</td>
                              <td style={{ padding: '10px 12px' }}>
                                <span style={{ ...compactBadgeStyle, background: '#fff1f2', color: '#dc2626', border: '1px solid #fecaca' }}>{row.statusLabel}</span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}

                    {tiktokKpiView === 'customers' ? (
                      <div style={{ display: 'grid', gridTemplateColumns: viewportWidth < 1440 ? 'minmax(0, 1fr)' : '340px minmax(0, 1fr)', gap: 16, minHeight: 0 }}>
                        <div style={{ border: '1px solid var(--border-default)', borderRadius: 12, overflow: 'hidden' }}>
                          <div style={{ background: '#FDFCFF', padding: '10px 12px', borderBottom: '1px solid var(--border-default)', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Current Live Customers</div>
                          <div style={{ maxHeight: 'calc(100vh - 240px)', overflow: 'auto' }}>
                            {tiktokCustomerRoster.map((entry) => (
                              <button
                                key={entry.key}
                                type="button"
                                onClick={() => setTikTokCustomerContext({ buyer: entry.buyer, username: cleanTikTokBuyer(entry.buyer), orderId: '', lotNo: '' })}
                                style={{ width: '100%', padding: '11px 12px', border: 'none', borderBottom: '1px solid #F1EEFF', background: selectedTikTokBuyerKey === entry.key ? '#faf5ff' : '#fff', textAlign: 'left', cursor: 'pointer', display: 'grid', gap: 6 }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                                  <span style={{ fontSize: '0.76rem', fontWeight: 700, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.buyer}</span>
                                  <span style={{ fontSize: '0.74rem', fontWeight: 800, color: '#5b21b6' }}>{fmt$(entry.revenue)}</span>
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
	                                  <span style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{entry.liveOrders} orders</span>
	                                  <span style={{ ...compactBadgeStyle, background: '#ecfdf3', color: '#047857', border: '1px solid #86efac' }}>{fmt$(entry.profit)} profit</span>
	                                  {entry.cancelled > 0 ? <span style={{ ...compactBadgeStyle, background: '#fff1f2', color: '#dc2626', border: '1px solid #fecaca' }}>{entry.cancelled} cancelled</span> : null}
	                                  {entry.paymentFailed > 0 ? <span style={{ ...compactBadgeStyle, background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a' }}>{entry.paymentFailed} pay fail</span> : null}
	                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                        <div style={{ border: '1px solid var(--border-default)', borderRadius: 12, padding: 14, display: 'grid', gap: 12, alignContent: 'start' }}>
                          {tiktokCustomerContext ? (
                            <>
                              <div>
                                <div style={{ fontSize: '0.66rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Selected Customer</div>
                                <div style={{ marginTop: 6, fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)' }}>{selectedTikTokCustomer?.display_name || selectedTikTokCustomer?.name || tiktokCustomerContext.buyer}</div>
                                <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{selectedTikTokPhone || selectedTikTokEmail || 'No contact info on file'}</div>
                                {selectedTikTokAddress ? (
                                  <div style={{ marginTop: 4, fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>{selectedTikTokAddress}</div>
                                ) : null}
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8 }}>
                                {[
                                  { label: 'Orders', value: tiktokCustomerLoading ? '…' : (selectedTikTokSummary.sale_order_count || tiktokCustomerOrders.length || 0) },
                                  { label: 'Returns', value: tiktokCustomerLoading ? '…' : selectedTikTokReturnRows.length },
                                  { label: 'Revenue', value: fmt$(selectedTikTokSummary.total_revenue || selectedTikTokCustomer?.total_spent || 0) },
                                  { label: 'Profit', value: fmt$(selectedTikTokSummary.total_profit || 0) },
                                ].map((metric) => (
                                  <div key={metric.label} style={{ border: '1px solid var(--border-default)', borderRadius: 10, background: '#fff', padding: '10px 12px' }}>
                                    <div style={{ fontSize: '0.6rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)' }}>{metric.label}</div>
                                    <div style={{ marginTop: 4, fontSize: '0.86rem', fontWeight: 800, color: 'var(--text-primary)' }}>{metric.value}</div>
                                  </div>
                                ))}
                              </div>
                              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                                <div style={{ border: '1px solid var(--border-default)', borderRadius: 10, padding: 10, display: 'grid', gap: 8 }}>
                                  <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Recent bought products</div>
                                  {selectedTikTokRecentProducts.length ? (
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                      {selectedTikTokRecentProducts.slice(0, 8).map((name) => (
                                        <span key={`drawer-recent-${name}`} style={{ ...compactBadgeStyle, background: '#eef2ff', color: '#4338ca', border: '1px solid #c7d2fe' }}>{shortDisplayProductName(name)}</span>
                                      ))}
                                    </div>
                                  ) : (
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>No completed product history yet.</div>
                                  )}
                                </div>
                                <div style={{ border: '1px solid var(--border-default)', borderRadius: 10, padding: 10, display: 'grid', gap: 8 }}>
                                  <div style={{ fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#dc2626' }}>Cancelled products</div>
                                  {selectedTikTokCancelledProducts.length ? (
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                      {selectedTikTokCancelledProducts.slice(0, 8).map((name) => (
                                        <span key={`drawer-cancelled-${name}`} style={{ ...compactBadgeStyle, background: '#fff1f2', color: '#dc2626', border: '1px solid #fecaca' }}>{shortDisplayProductName(name)}</span>
                                      ))}
                                    </div>
                                  ) : (
                                    <div style={{ fontSize: '0.74rem', color: 'var(--text-secondary)' }}>No cancelled products.</div>
                                  )}
                                </div>
                              </div>
                              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                  <tr style={{ background: '#FDFCFF' }}>
                                    {['Order', 'State', 'Amount'].map((label) => (
                                      <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                                    ))}
                                  </tr>
                                </thead>
                                <tbody>
                                  {tiktokCustomerOrders.slice(0, 8).map((order) => (
                                    <tr key={order.id || order.order_number} style={{ borderBottom: '1px solid #F1EEFF' }}>
                                      <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)', fontWeight: 700 }}>{order.order_number || `Order ${order.id}`}</td>
                                      <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-secondary)' }}>{order.state || order.fulfillment_status || 'sale'}</td>
                                      <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: '#5b21b6', fontWeight: 800 }}>{fmt$(order.total_amount || order.amount_total || order.subtotal)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              {selectedTikTokTasteSuggestions.length ? (
                                <div style={{ display: 'grid', gap: 8 }}>
                                  <div style={{ fontSize: '0.66rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#6C47FF' }}>Predicted next items</div>
                                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                                    {selectedTikTokTasteSuggestions.map(({ product, reason }, idx) => (
                                      <div key={`drawer-taste-${product.id || idx}`} style={{ border: '1px solid #ddd6fe', borderRadius: 10, background: '#faf5ff', padding: '10px 12px' }}>
                                        <div style={{ fontSize: '0.74rem', fontWeight: 700, color: 'var(--text-primary)' }}>{shortDisplayProductName(product.name)}</div>
                                        <div style={{ marginTop: 4, fontSize: '0.68rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                                          {reason ? `Taste overlap: ${reason}` : 'Based on this buyer’s previous products and current stream activity.'}
                                        </div>
                                        <div style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                                          <span style={{ fontSize: '0.66rem', color: 'var(--text-secondary)' }}>Retail {fmt$(product?.price || product?.retail_price || 0)}</span>
                                          <span style={{ fontSize: '0.66rem', fontWeight: 800, color: '#047857' }}>Qty {liveInventoryQty(product)}</span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : null}
                            </>
                          ) : (
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>Select a customer on the left to load current-live totals and past order history.</div>
                          )}
                        </div>
                      </div>
                    ) : null}

                    {tiktokKpiView === 'needs_attention' ? (
                      <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
                        <thead>
                          <tr style={{ background: '#FDFCFF' }}>
                            {['Type', 'Lot', 'Barcode', 'Detail'].map((label) => (
                              <th key={label} style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-default)', textAlign: 'left', fontSize: '0.64rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tiktokNeedsAttentionRows.map((row, idx) => (
                            <tr key={`${row.type}-${row.lotNo}-${idx}`} style={{ borderBottom: '1px solid #F1EEFF' }}>
                              <td style={{ padding: '10px 12px' }}>
                                <span style={{ ...compactBadgeStyle, background: row.severity === 'warning' ? '#fff7ed' : '#eef2ff', color: row.severity === 'warning' ? '#c2410c' : '#4338ca', border: `1px solid ${row.severity === 'warning' ? '#fdba74' : '#c7d2fe'}` }}>{row.type}</span>
                              </td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)', fontWeight: 700 }}>#{row.lotNo}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.72rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{row.barcode || '—'}</td>
                              <td style={{ padding: '10px 12px', fontSize: '0.74rem', color: 'var(--text-primary)' }}>{row.detail}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

      </>)}
      {/* ===== END TIKTOK MODE ===== */}

    </div>
  );
}
