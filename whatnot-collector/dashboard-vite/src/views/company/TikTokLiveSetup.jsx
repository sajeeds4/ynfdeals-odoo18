import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchApi, getCachedApi, getStoredCsrfToken, postApi } from '../../hooks/useApi';
import { getScopedStorageKey } from '../../hooks/useBrowserState';
import { Badge, EmptyRow, GhostBtn, KpiCard, PrimaryBtn, TableShell, Thead, clrMargin, clrProfit, fmt, fmtDt, fmtPct } from './utils';
import { buildPullSummary, downloadPickListPdf } from './TikTokLivePickList';

const STORAGE_KEY = 'ynf_tiktok_live_setup_v3';
const STORE_EVENT = 'ynf:tiktok-live-store-updated';
const TIKTOK_PLATFORM_FEE_RATE = 0.06;

function getTikTokLiveStoreKey() {
  return getScopedStorageKey(STORAGE_KEY);
}

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-md)',
  padding: '8px 10px',
  fontSize: 13,
  width: '100%',
};

function normalizeCode(value) {
  return String(value || '').trim().toLowerCase();
}

function productSearchText(product) {
  return [
    product?.name,
    product?.brand,
    product?.barcode,
    product?.default_code,
    product?.sku,
  ].filter(Boolean).join(' ').toLowerCase();
}

function productBarcode(product) {
  return String(product?.barcode || product?.default_code || product?.sku || '').trim();
}

function compactLiveProductName(value) {
  return String(value || '')
    .replace(/\s*\([^)]*\boz\b[^)]*\)/gi, '')
    .replace(/\s+\bPerfume\b\s*$/i, '')
    .replace(/\s+\bFragrances?\b\s*$/i, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function isProductNameSearch(value, inventoryMap) {
  const query = String(value || '').trim();
  if (!query) return false;
  if (inventoryMap?.has?.(normalizeCode(query))) return false;
  return /[a-z]/i.test(query);
}

function normalizeSeedBarcode(value) {
  const raw = String(value || '').trim();
  if (raw === '3220360598918') return '6290360598918';
  return raw;
}

function extractOrderLotNumber(order) {
  const direct = String(order?.lot_number || '').trim();
  if (direct) return direct;
  const externalRef = String(order?.external_order_ref || '').trim();
  const colonMatch = externalRef.match(/^tiktok_(?:live|shop):[^:]+:([^:]+)$/i);
  if (colonMatch?.[1]) return colonMatch[1].trim();
  const suffixMatch = externalRef.match(/-LOT-([^-]+)$/i);
  if (suffixMatch?.[1]) return suffixMatch[1].trim();
  const notes = String(order?.notes || '');
  const notesMatch = notes.match(/(?:^|\n)Lot:\s*([^\n]+)/i);
  return notesMatch?.[1] ? notesMatch[1].trim() : '';
}

function buildRows(count) {
  const size = Math.max(1, Number(count || 0));
  return Array.from({ length: size }, (_, index) => ({
    lotNo: String(index + 1),
    barcode: '',
  }));
}

export function rowsToLotMapCsv(rows, inventoryMap = null) {
  const lines = ['Lot No,Barcode,SKU,Product Name'];
  rows.forEach((row) => {
    if (!String(row.barcode || '').trim()) return;
    const match = inventoryMap?.get?.(normalizeCode(row.barcode));
    const values = [
      row.lotNo || '',
      row.barcode || '',
      match?.default_code || '',
      match?.name || '',
    ].map((value) => `"${String(value || '').replace(/"/g, '""')}"`);
    lines.push(values.join(','));
  });
  return lines.join('\n');
}

function defaultDraft() {
  return {
    lotCount: '200',
    rows: [],
    isLive: false,
    liveName: '',
    detailsCsvText: '',
    detailsCsvName: '',
  };
}

function countScannedRows(rows) {
  return (Array.isArray(rows) ? rows : []).filter((row) => String(row?.barcode || '').trim()).length;
}

function parseLotNumber(value) {
  const numeric = Number(String(value || '').trim());
  return Number.isFinite(numeric) ? numeric : null;
}

function sortRowsByLotNumber(rows) {
  return [...(Array.isArray(rows) ? rows : [])].sort((left, right) => {
    const leftNum = parseLotNumber(left?.lotNo);
    const rightNum = parseLotNumber(right?.lotNo);
    if (leftNum != null && rightNum != null) return leftNum - rightNum;
    return String(left?.lotNo || '').localeCompare(String(right?.lotNo || ''));
  });
}

function mergeDraftRows(primaryRows, secondaryRows) {
  const merged = new Map();
  const ingest = (rows, preferExisting = false) => {
    (Array.isArray(rows) ? rows : []).forEach((row, index) => {
      const lotNo = String(row?.lotNo || '').trim() || `__idx_${index}`;
      const current = merged.get(lotNo);
      if (!current) {
        merged.set(lotNo, { ...row });
        return;
      }
      const nextRow = preferExisting
        ? {
            ...row,
            ...current,
            barcode: String(current?.barcode || '').trim() || String(row?.barcode || '').trim(),
            productName: String(current?.productName || '').trim() || String(row?.productName || '').trim(),
            sku: String(current?.sku || '').trim() || String(row?.sku || '').trim(),
            notes: String(current?.notes || '').trim() || String(row?.notes || '').trim(),
            cost: Number(current?.cost || 0) || Number(row?.cost || 0),
            productId: current?.productId || row?.productId || null,
            itemId: current?.itemId || row?.itemId || null,
            matched: Boolean(current?.matched || row?.matched),
          }
        : {
            ...current,
            ...row,
            barcode: String(row?.barcode || '').trim() || String(current?.barcode || '').trim(),
            productName: String(row?.productName || '').trim() || String(current?.productName || '').trim(),
            sku: String(row?.sku || '').trim() || String(current?.sku || '').trim(),
            notes: String(row?.notes || '').trim() || String(current?.notes || '').trim(),
            cost: Number(row?.cost || 0) || Number(current?.cost || 0),
            productId: row?.productId || current?.productId || null,
            itemId: row?.itemId || current?.itemId || null,
            matched: Boolean(row?.matched || current?.matched),
          };
      merged.set(lotNo, nextRow);
    });
  };
  ingest(primaryRows);
  ingest(secondaryRows);
  return sortRowsByLotNumber([...merged.values()]);
}

function nextHistoryContainsDraft(history, draft) {
  const sessionId = Number(draft?.serverSessionId || 0);
  const sequence = Number(draft?.sequence || 0);
  return (Array.isArray(history) ? history : []).some((item) => {
    if (sessionId && Number(item?.serverSessionId || 0) === sessionId) return true;
    if (sequence && Number(item?.sequence || 0) === sequence) return true;
    return false;
  });
}

function protectActiveDraft(existingDraft, nextDraft, nextHistory) {
  const currentLive = Boolean(existingDraft?.isLive);
  const nextLive = Boolean(nextDraft?.isLive);
  if (!currentLive) return false;
  if (!nextLive && !nextHistoryContainsDraft(nextHistory, existingDraft)) return true;

  if (currentLive && nextLive) {
    const currentScanned = countScannedRows(existingDraft?.rows);
    const nextScanned = countScannedRows(nextDraft?.rows);
    if (nextScanned < currentScanned) return true;
    const currentPrepared = Array.isArray(existingDraft?.rows) ? existingDraft.rows.length : 0;
    const nextPrepared = Array.isArray(nextDraft?.rows) ? nextDraft.rows.length : 0;
    if (nextPrepared < currentPrepared && nextScanned <= currentScanned) return true;
  }
  return false;
}

function sanitizeHistory(items) {
  return (Array.isArray(items) ? items : []).filter((item) => {
    const hasCustomDisplay = Boolean(String(item?.displayName || '').trim());
    const lotCount = Array.isArray(item?.rows) ? item.rows.length : 0;
    if (!hasCustomDisplay && lotCount <= 2) return false;
    return true;
  });
}

function isLocalHistoryDraft(item) {
  const status = String(item?.status || '').trim().toLowerCase();
  return ['live', 'open', 'draft'].includes(status) || Boolean(item?.isLive);
}

function stripPersistedSessionHistory(items) {
  return (Array.isArray(items) ? items : []).filter(isLocalHistoryDraft);
}

function normalizeSessionIdentity(item) {
  const serverKey = Number(item?.serverSessionId || 0);
  if (serverKey > 0) return `server:${serverKey}`;
  const sequence = Number(item?.sequence || 0);
  const displayName = String(item?.displayName || '').trim().toLowerCase();
  const liveName = String(item?.liveName || '').trim().toLowerCase();
  if (sequence > 0) return `sequence:${sequence}`;
  return `local:${String(item?.id || '').trim()}`;
}

function getSessionSortTimestamp(item) {
  const raw = item?.endedAt || item?.updatedAt || item?.startedAt || '';
  const value = raw ? new Date(raw).getTime() : NaN;
  return Number.isFinite(value) ? value : 0;
}

function getSessionStatusRank(item) {
  const status = String(item?.status || '').trim().toLowerCase();
  if (status === 'live') return 3;
  if (status === 'open' || status === 'draft') return 2;
  if (status === 'ended') return 1;
  return 0;
}

function sortSessionHistory(items) {
  return [...(Array.isArray(items) ? items : [])].sort((a, b) => {
    const rankDiff = getSessionStatusRank(b) - getSessionStatusRank(a);
    if (rankDiff) return rankDiff;
    const timeDiff = getSessionSortTimestamp(b) - getSessionSortTimestamp(a);
    if (timeDiff) return timeDiff;
    return Number(b?.sequence || 0) - Number(a?.sequence || 0);
  });
}

function mergeSessionHistory(serverRows, localRows) {
  const merged = new Map();
  const rowOrderScore = (rows) => (Array.isArray(rows) ? rows : []).reduce((score, row) => {
    const hasBuyer = Boolean(String(row?.buyer || row?.buyerUsername || row?.tiktokOrder?.buyer_username || '').trim());
    const hasSale = Number(row?.salesPrice || row?.tiktokOrder?.total_amount || 0) > 0;
    const hasOrder = Boolean(row?.tiktokOrder || row?.orderId || row?.saleOrderId || hasBuyer || hasSale);
    if (!hasOrder) return score;
    return score + (hasBuyer ? 4 : 0) + (hasSale ? 4 : 0) + (row?.tiktokOrder ? 4 : 0) + 1;
  }, 0);
  const combine = (current, incoming) => {
    if (!current) return incoming;
    if (!incoming) return current;
    const currentRows = Array.isArray(current?.rows) ? current.rows : [];
    const incomingRows = Array.isArray(incoming?.rows) ? incoming.rows : [];
    const currentOrderScore = rowOrderScore(currentRows);
    const incomingOrderScore = rowOrderScore(incomingRows);
    const keepRows = incomingOrderScore > currentOrderScore
      ? incomingRows
      : currentOrderScore > incomingOrderScore
        ? currentRows
        : incomingRows.length > currentRows.length
          ? incomingRows
          : currentRows;
    const importedOrderRefs = [
      ...new Set([
        ...(Array.isArray(current?.importedOrderRefs) ? current.importedOrderRefs : []),
        ...(Array.isArray(incoming?.importedOrderRefs) ? incoming.importedOrderRefs : []),
      ]),
    ];
    return {
      ...current,
      ...incoming,
      serverSessionId: incoming?.serverSessionId || current?.serverSessionId || null,
      showId: incoming?.showId || current?.showId || '',
      rows: keepRows,
      importedOrderRefs,
      lotCount: String(
        Math.max(
          Number(incoming?.lotCount || incomingRows.length || 0),
          Number(current?.lotCount || currentRows.length || 0),
        ) || '',
      ),
    };
  };
  [...(serverRows || []), ...(localRows || [])].forEach((item) => {
    const key = normalizeSessionIdentity(item);
    if (!key) return;
    merged.set(key, combine(merged.get(key), item));
  });
  return sortSessionHistory([...merged.values()]);
}

function withSeedSessions(store) {
  const currentHistory = stripPersistedSessionHistory(sanitizeHistory(store?.history));
  const sortedHistory = sortSessionHistory(currentHistory);
  return {
    draft: { ...defaultDraft(), ...(store?.draft || {}) },
    history: sortedHistory,
    seq: Math.max(Number(store?.seq || 0), ...sortedHistory.map((item) => Number(item.sequence || 0))),
  };
}

function getSessionOrderRefs(item) {
  return new Set(
    (Array.isArray(item?.importedOrderRefs) ? item.importedOrderRefs : [])
      .map((ref) => String(ref || '').trim())
      .filter(Boolean),
  );
}

function getOrderTimestampMs(order) {
  const raw = order?.ordered_at || order?.created_at || order?.updated_at || '';
  const value = raw ? new Date(raw).getTime() : NaN;
  return Number.isFinite(value) ? value : null;
}

function isInLegacySessionWindow(order, item) {
  const endedAt = item?.endedAt ? new Date(item.endedAt).getTime() : NaN;
  if (!Number.isFinite(endedAt)) return true;
  const orderAt = getOrderTimestampMs(order);
  if (!orderAt) return false;
  const windowStart = endedAt - (12 * 60 * 60 * 1000);
  const windowEnd = endedAt + (90 * 60 * 1000);
  return orderAt >= windowStart && orderAt <= windowEnd;
}

function getOrderProductQty(order) {
  const lineQty = Number(order?.line_qty || 0);
  if (lineQty > 0) return lineQty;
  const linkedProducts = Number(order?.linked_products_sold || 0);
  if (linkedProducts > 0) return linkedProducts;
  return 1;
}

function filterOrdersForSession(saleOrders, item) {
  const serverSessionId = Number(item?.serverSessionId || 0);
  if (serverSessionId > 0) {
    return saleOrders.filter((order) => Number(order?.session_id || 0) === serverSessionId);
  }
  const importedRefs = getSessionOrderRefs(item);
  const allowedLots = new Set((item?.rows || []).map((row) => String(row?.lotNo || '').trim()).filter(Boolean));
  if (importedRefs.size) {
    return saleOrders.filter((order) => importedRefs.has(String(order?.external_order_ref || '').trim()));
  }
  if (item?.matchMode === 'legacy_lot_numbers') {
    const scopedOrders = saleOrders.filter((order) => (
      allowedLots.has(extractOrderLotNumber(order)) && isInLegacySessionWindow(order, item)
    ));
    if (scopedOrders.length) return scopedOrders;
    return saleOrders.filter((order) => (
      !Number(order?.session_id || 0) && allowedLots.has(extractOrderLotNumber(order))
    ));
  }
  return [];
}

export function readStore() {
  try {
    const scopedKey = getTikTokLiveStoreKey();
    const legacyKey = STORAGE_KEY;
    const raw = window.localStorage.getItem(scopedKey)
      ?? (scopedKey !== legacyKey ? window.localStorage.getItem(legacyKey) : null);
    if (!raw) return withSeedSessions({ draft: defaultDraft(), history: [], seq: 0 });
    const saved = JSON.parse(raw);
    if (saved && saved.draft) {
      return withSeedSessions(saved);
    }
    return withSeedSessions({
      draft: {
        lotCount: saved.lotCount || '200',
        rows: Array.isArray(saved.rows) ? saved.rows : [],
        isLive: !!saved.isLive,
        liveName: saved.liveName || '',
        detailsCsvText: saved.detailsCsvText || '',
        detailsCsvName: saved.detailsCsvName || '',
      },
      history: [],
      seq: 0,
    });
  } catch {
    return withSeedSessions({ draft: defaultDraft(), history: [], seq: 0 });
  }
}

export function writeStore(next) {
  try {
    const scopedKey = getTikTokLiveStoreKey();
    const rawExisting = window.localStorage.getItem(scopedKey)
      ?? (scopedKey !== STORAGE_KEY ? window.localStorage.getItem(STORAGE_KEY) : null);
    let existing = null;
    if (rawExisting) {
      try {
        existing = withSeedSessions(JSON.parse(rawExisting));
      } catch {
        existing = null;
      }
    }
    const current = existing || withSeedSessions({ draft: defaultDraft(), history: [], seq: 0 });
    const incoming = withSeedSessions(next || {});
    const mergedHistory = mergeSessionHistory(incoming.history || [], current.history || []);
    let mergedDraft = { ...current.draft, ...incoming.draft };
    if (protectActiveDraft(current.draft, incoming.draft, mergedHistory)) {
      mergedDraft = {
        ...incoming.draft,
        ...current.draft,
        isLive: true,
        serverSessionId: current.draft?.serverSessionId || incoming.draft?.serverSessionId || null,
        liveName: current.draft?.liveName || incoming.draft?.liveName || '',
        detailsCsvText: current.draft?.detailsCsvText || incoming.draft?.detailsCsvText || '',
        detailsCsvName: current.draft?.detailsCsvName || incoming.draft?.detailsCsvName || '',
        lotCount: String(Math.max(Number(current.draft?.lotCount || 0), Number(incoming.draft?.lotCount || 0)) || incoming.draft?.lotCount || current.draft?.lotCount || '1'),
        rows: mergeDraftRows(current.draft?.rows, incoming.draft?.rows),
      };
    }
    const normalized = withSeedSessions({
      draft: mergedDraft,
      history: stripPersistedSessionHistory(mergedHistory),
      seq: Math.max(Number(current.seq || 0), Number(incoming.seq || 0)),
    });
    const serialized = JSON.stringify(normalized);
    if (window.localStorage.getItem(scopedKey) === serialized) return;
    window.localStorage.setItem(scopedKey, serialized);
    if (scopedKey !== STORAGE_KEY) {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(STORE_EVENT));
  } catch {
    // ignore storage issues
  }
}

export function archiveLabel(item) {
  if (item?.displayName) return item.displayName;
  const dt = item?.endedAt ? new Date(item.endedAt) : null;
  const dateLabel = dt && !Number.isNaN(dt.getTime()) ? dt.toLocaleDateString() : 'No date';
  return `Go Live ${item.sequence || 1} (${dateLabel})${item.liveName ? ` ${item.liveName}` : ''}`;
}

function sessionCardTitle(item) {
  return `Go Live Session ${item?.sequence || 1}`;
}

function sessionCardDate(item) {
  const dt = item?.endedAt ? new Date(item.endedAt) : null;
  if (!dt || Number.isNaN(dt.getTime())) return 'No date';
  return dt.toLocaleDateString(undefined, {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
}

function formatRelativeSyncTime(value) {
  const stamp = Date.parse(String(value || ''));
  if (!Number.isFinite(stamp)) return 'Not synced yet';
  const diffSeconds = Math.max(0, Math.round((Date.now() - stamp) / 1000));
  if (diffSeconds < 5) return 'just now';
  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return new Date(stamp).toLocaleString();
}

function labelSessionKey(item) {
  if (item?.serverSessionId) return `server-${item.serverSessionId}`;
  return String(item?.id || '').trim();
}

function labelArtifactUrl(download) {
  if (download?.url) return download.url;
  if (download?.artifactId) {
    const apiBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
    return `${apiBase}/api/tiktok_live_labels/artifact?id=${encodeURIComponent(download.artifactId)}`;
  }
  return '';
}

function tikTokPlatformFee(value) {
  return Math.round(Number(value || 0) * TIKTOK_PLATFORM_FEE_RATE * 100) / 100;
}

function metricCardStyle(tone) {
  const tones = {
    amber: { background: '#fff7ed', border: '#fed7aa', color: '#c2410c' },
    green: { background: '#ecfdf5', border: '#bbf7d0', color: '#047857' },
    blue: { background: '#eff6ff', border: '#bfdbfe', color: '#1d4ed8' },
    violet: { background: '#f5f3ff', border: '#ddd6fe', color: '#6d28d9' },
    red: { background: '#fef2f2', border: '#fecaca', color: '#dc2626' },
  };
  const selected = tones[tone] || tones.blue;
  return {
    background: selected.background,
    border: `1px solid ${selected.border}`,
    color: selected.color,
    borderRadius: 18,
    padding: '14px 16px',
    display: 'grid',
    gap: 6,
    minWidth: 0,
  };
}

function compactMetricPillStyle(tone, active = false) {
  const base = metricCardStyle(tone);
  return {
    ...base,
    borderRadius: 14,
    padding: '8px 10px',
    minHeight: 48,
    width: '100%',
    textAlign: 'left',
    boxShadow: active ? 'inset 0 0 0 2px rgba(15,23,42,0.08)' : 'none',
    transform: active ? 'translateY(-1px)' : 'none',
  };
}

function sessionActionButtonStyle(tone = 'plain') {
  const tones = {
    plain: { border: '#cbd5e1', background: '#ffffff', color: '#0f172a', shadow: '0 1px 2px rgba(15,23,42,0.04)' },
    blue: { border: '#dbeafe', background: '#2563eb', color: '#ffffff', shadow: '0 1px 2px rgba(37,99,235,0.25)' },
    green: { border: '#bbf7d0', background: '#ecfdf5', color: '#047857', shadow: '0 1px 2px rgba(5,150,105,0.14)' },
    amber: { border: '#fed7aa', background: '#fff7ed', color: '#c2410c', shadow: '0 1px 2px rgba(194,65,12,0.12)' },
  };
  const selected = tones[tone] || tones.plain;
  return {
    border: `1px solid ${selected.border}`,
    background: selected.background,
    color: selected.color,
    borderRadius: 10,
    padding: '9px 12px',
    fontSize: 12,
    fontWeight: 800,
    cursor: 'pointer',
    boxShadow: selected.shadow,
  };
}

function sessionToolPanelStyle(tone = 'plain') {
  const tones = {
    plain: { border: '#e2e8f0', background: '#ffffff' },
    blue: { border: '#bfdbfe', background: '#eff6ff' },
    green: { border: '#bbf7d0', background: '#ecfdf5' },
    amber: { border: '#fed7aa', background: '#fff7ed' },
  };
  const selected = tones[tone] || tones.plain;
  return {
    border: `1px solid ${selected.border}`,
    background: selected.background,
    borderRadius: 18,
    padding: 16,
    display: 'grid',
    gap: 12,
    minWidth: 0,
  };
}

function overviewStatCardStyle() {
  return {
    border: '1px solid #e2e8f0',
    background: 'linear-gradient(180deg, #ffffff 0%, #fafaf9 100%)',
    borderRadius: 16,
    padding: '14px 16px',
    display: 'grid',
    gap: 4,
    minWidth: 0,
  };
}

function overviewStatLabelStyle() {
  return {
    fontSize: 11,
    fontWeight: 800,
    color: '#64748b',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  };
}

function overviewStatValueStyle(color = '#0f172a') {
  return {
    fontSize: 18,
    fontWeight: 900,
    color,
    letterSpacing: '-0.02em',
    lineHeight: 1.1,
  };
}

function buildInlineLotMapCsv(rows, inventoryByBarcode) {
  const lines = ['Lot No,Barcode,SKU,Product Name'];
  (rows || []).forEach((row) => {
    const barcode = normalizeSeedBarcode(row?.barcode);
    if (!barcode) return;
    const product = inventoryByBarcode.get(barcode);
    const values = [
      row?.lotNo || '',
      barcode,
      product?.default_code || product?.sku || '',
      product?.name || '',
    ].map((value) => `"${String(value || '').replace(/"/g, '""')}"`);
    lines.push(values.join(','));
  });
  return lines.join('\n');
}

function isExcelUpload(file) {
  const name = String(file?.name || '').toLowerCase();
  const type = String(file?.type || '').toLowerCase();
  return name.endsWith('.xlsx') || name.endsWith('.xlsm') || type.includes('spreadsheetml');
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',').pop() : result);
    };
    reader.onerror = () => reject(reader.error || new Error('Could not read Excel file.'));
    reader.readAsDataURL(file);
  });
}

function getTikTokSessionRows(item, orders, inventoryByBarcode) {
  const scopedOrders = filterOrdersForSession(Array.isArray(orders) ? orders : [], item);
  const orderByLot = new Map(scopedOrders.map((order) => [String(extractOrderLotNumber(order) || '').trim(), order]));
  return (item?.rows || []).map((row) => {
    const lotNo = String(row?.lotNo || '').trim();
    const order = orderByLot.get(lotNo) || null;
    const product = inventoryByBarcode.get(normalizeSeedBarcode(row?.barcode));
    const salePrice = Number(order?.total_amount || row?.salesPrice || 0);
    const tiktokSellerSku = String(order?.seller_sku || row?.tiktokOrder?.sellerSku || row?.sellerSku || row?.sku || '').trim();
    const statusFamily = String(row?.statusFamily || '').trim().toLowerCase();
    const orderDelivered = Boolean(order && order.state !== 'cancel' && (
      order.fulfillment_status === 'delivered'
      || order.tracking_status === 'delivered'
      || String(order.delivered_at || '').trim()
    ));
    const resolvedStatus = order
      ? (orderDelivered ? 'delivered' : order.state === 'cancel' ? 'cancelled' : 'pending')
      : statusFamily;
    const hasSessionOrder = Boolean(order || row?.tiktokOrder || row?.buyer || row?.buyerUsername || salePrice > 0 || ['confirmed', 'pending'].includes(statusFamily));
    const fees = hasSessionOrder ? Number(row?.fees ?? tikTokPlatformFee(salePrice)) : 0;
    const cost = Number(product?.cost_price || row?.cost || 0);
    return {
      lotNo,
      barcode: normalizeSeedBarcode(row?.barcode || ''),
      productName: product?.name || row?.productName || order?.combined_listing || order?.product_name || '',
      sku: product?.default_code || product?.sku || tiktokSellerSku || '',
      tiktokSellerSku,
      cost,
      retail: Number(product?.retail_price || row?.retail || 0),
      buyer: order?.whatnot_buyer_username || row?.buyerUsername || row?.buyer || '',
      salePrice,
      fees,
      profit: hasSessionOrder ? Number(row?.profit ?? (salePrice - cost - fees)) : 0,
      status: hasSessionOrder ? (String(resolvedStatus || statusFamily).trim() || 'pending') : 'missing',
      soldAt: order?.date_order || order?.sold_at || order?.created_at || row?.orderedAt || '',
      orderNumber: order?.order_number || row?.orderId || '',
    };
  });
}

function downloadTikTokSessionCsv(item, orders, inventoryByBarcode) {
  const rows = getTikTokSessionRows(item, orders, inventoryByBarcode);
  const escapeCell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const lines = [
    ['Session', 'Lot #', 'Buyer', 'Product', 'Barcode', 'Sale Price', 'Cost', 'Fees', 'Profit', 'Status', 'Sold At', 'Order #'],
    ...rows.map((row) => [
      archiveLabel(item),
      row.lotNo,
      row.buyer,
      row.productName,
      row.barcode,
      row.salePrice,
      row.cost,
      row.fees,
      row.profit,
      row.status,
      row.soldAt,
      row.orderNumber,
    ]),
  ].map((line) => line.map(escapeCell).join(','));
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${archiveLabel(item).replace(/[^A-Za-z0-9._ -]+/g, '').replace(/\s+/g, '-') || 'tiktok-live-session'}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function printTikTokSessionReport(item, summary, orders, inventoryByBarcode) {
  const rows = getTikTokSessionRows(item, orders, inventoryByBarcode);
  const confirmedRows = rows.filter((row) => row.status !== 'missing');
  const $ = (value) => `$${Number(value || 0).toFixed(2)}`;
  const pct = summary.revenue ? `${((Number(summary.profit || 0) / Number(summary.revenue || 0)) * 100).toFixed(1)}%` : '0.0%';
  const htmlRows = rows.map((row, index) => `
    <tr style="background:${index % 2 === 0 ? '#fff' : '#f9fafb'}">
      <td>${row.lotNo || ''}</td>
      <td>${row.buyer || ''}</td>
      <td>${row.productName || ''}</td>
      <td class="r">${row.status === 'missing' ? '' : $(row.salePrice)}</td>
      <td class="r">${row.status === 'missing' ? '' : $(row.fees)}</td>
      <td class="r" style="color:${row.profit >= 0 ? '#047857' : '#dc2626'}">${row.status === 'missing' ? '' : $(row.profit)}</td>
      <td>${row.status}</td>
    </tr>
  `).join('');
  const html = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${archiveLabel(item)} Report</title>
  <style>
    body{font-family:Arial,sans-serif;color:#111827;font-size:11px;margin:24px}
    .head{display:flex;justify-content:space-between;border-bottom:2px solid #111827;padding-bottom:12px;margin-bottom:14px}
    h1{font-size:22px;margin:0}.meta{text-align:right;color:#64748b;line-height:1.6}
    .kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0}
    .kpi{border:1px solid #e5e7eb;border-radius:8px;padding:8px 10px;background:#f9fafb}
    .label{font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;font-weight:700}
    .value{font-size:16px;font-weight:900;margin-top:4px} table{width:100%;border-collapse:collapse;margin-top:12px}
    th{background:#111827;color:white;text-align:left;font-size:9px;text-transform:uppercase;letter-spacing:.06em;padding:7px 8px}
    td{border-bottom:1px solid #e5e7eb;padding:6px 8px}.r{text-align:right}
  </style>
</head>
<body>
  <div class="head"><div><h1>ynfdeals</h1><div>TikTok Live Auction Report</div></div><div class="meta"><strong>${archiveLabel(item)}</strong><br/>Generated ${new Date().toLocaleString()}</div></div>
  <div class="kpis">
    <div class="kpi"><div class="label">Results</div><div class="value">${confirmedRows.length}</div></div>
    <div class="kpi"><div class="label">Revenue</div><div class="value">${$(summary.revenue)}</div></div>
    <div class="kpi"><div class="label">Fees 6%</div><div class="value">${$(summary.platformFees || tikTokPlatformFee(summary.revenue))}</div></div>
    <div class="kpi"><div class="label">Profit</div><div class="value">${$(summary.profit)}</div></div>
    <div class="kpi"><div class="label">Margin</div><div class="value">${pct}</div></div>
  </div>
  <table><thead><tr><th>Lot #</th><th>Buyer</th><th>Product</th><th class="r">Sale</th><th class="r">Fees</th><th class="r">Profit</th><th>Status</th></tr></thead><tbody>${htmlRows}</tbody></table>
  <script>window.addEventListener('load',function(){setTimeout(function(){window.print();},150);});</script>
</body>
</html>`;
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const win = window.open(url, '_blank', 'width=900,height=700');
  if (win) win.focus();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function TikTokLiveHistoryPanel({ selectedId = '', onSelect, onPrint, onImported, refreshToken = 0, renderExpandedContent }) {
  const cachedHistoryRows = useMemo(() => {
    const cachedServerHistory = getCachedApi('/api/tiktok_live_sessions?limit=120&summary=1', { rows: [] });
    return Array.isArray(cachedServerHistory?.rows) ? sortSessionHistory(cachedServerHistory.rows) : [];
  }, []);
  const [history, setHistory] = useState(cachedHistoryRows);
  const [orders, setOrders] = useState([]);
  const [inventory, setInventory] = useState([]);
  const [sessionSearch, setSessionSearch] = useState('');
  const [orderLookup, setOrderLookup] = useState('');
  const [orderLookupBusy, setOrderLookupBusy] = useState(false);
  const [orderLookupMessage, setOrderLookupMessage] = useState('');
  const [allCsvBusy, setAllCsvBusy] = useState(false);
  const [detailSearch, setDetailSearch] = useState('');
  const [csvFileName, setCsvFileName] = useState('');
  const [csvText, setCsvText] = useState('');
  const [csvWorkbookBase64, setCsvWorkbookBase64] = useState('');
  const [csvBusy, setCsvBusy] = useState(false);
  const [csvSummary, setCsvSummary] = useState(null);
  const [csvMessage, setCsvMessage] = useState('');
  const [labelBusy, setLabelBusy] = useState(false);
  const [labelMessage, setLabelMessage] = useState('');
  const [labelDownloads, setLabelDownloads] = useState({});
  const [historyMessage, setHistoryMessage] = useState('');
  const [historyLoading, setHistoryLoading] = useState(cachedHistoryRows.length === 0);
  const [detailDataLoading, setDetailDataLoading] = useState(false);
  const [detailDataSessionKey, setDetailDataSessionKey] = useState('');
  const [draggingId, setDraggingId] = useState('');
  const [detailViews, setDetailViews] = useState({});
  const [overviewMode, setOverviewMode] = useState('all');
  const detailDataCacheRef = useRef({});
  const detailDataRequestRef = useRef(0);
  const fileInputRef = useRef(null);
  const labelInputRef = useRef(null);
  const summaryRepairRef = useRef(new Set());

  const selectedSessionMeta = useMemo(() => {
    if (!selectedId) return null;
    return (history || []).find((item) => String(item?.id || '') === String(selectedId || '')) || null;
  }, [history, selectedId]);
  const selectedServerSessionId = Number(selectedSessionMeta?.serverSessionId || 0);
  const selectedHasDetailRows = Array.isArray(selectedSessionMeta?.rows) && selectedSessionMeta.rows.length > 0;

  const lastHistoryFingerprintRef = useRef('');
  useEffect(() => {
    const fingerprint = (rows) => rows
      .map((r) => `${r?.id || ''}:${r?.serverSessionId || ''}:${r?.lotCount || ''}:${r?.summary?.revenue || ''}:${r?.endedAt || ''}`)
      .join('|');
    const sync = ({ background = false } = {}) => {
      // Skip background polls when the tab is hidden; resume on visibility change below.
      if (background && typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      const store = readStore();
      setHistory((current) => (current.length ? current : (cachedHistoryRows.length ? cachedHistoryRows : (store.history || []))));
      // Only show the loading state on a true cold start, not on background refreshes.
      if (!background) {
        setHistoryMessage('');
        setHistoryLoading(true);
      }
      fetchApi('/api/tiktok_live_sessions?limit=120&summary=1')
        .then((data) => {
          const serverRows = Array.isArray(data?.rows) ? data.rows : [];
          if (!serverRows.length) {
            if (!background) {
              setHistory(store.history || []);
              setHistoryMessage('');
            }
            return;
          }
          const serverHistory = sortSessionHistory(serverRows);
          const nextFingerprint = fingerprint(serverHistory);
          // Skip the state update entirely if nothing changed. Otherwise every
          // 60s tick passes a new array reference to children, triggering a
          // full sale_orders + inventory refetch and "page reload" flicker.
          if (nextFingerprint !== lastHistoryFingerprintRef.current) {
            lastHistoryFingerprintRef.current = nextFingerprint;
            setHistory(serverHistory);
          }
          setHistoryMessage('');

          const currentMerged = serverHistory.find((item) => String(item?.id || '') === String(selectedId || '')) || null;
          if (selectedId && !currentMerged) onSelect?.(null);
        })
        .catch((error) => {
          if (!background) {
            setHistory(store.history || []);
            setHistoryMessage(`Could not load saved TikTok sessions: ${error?.message || 'request failed'}`);
          }
        })
        .finally(() => {
          if (!background) setHistoryLoading(false);
        });
    };
    sync();
    // No polling. Archived TikTok Live sessions are immutable once confirmed.
    // Refresh only on: explicit user action (handled elsewhere via refreshToken),
    // local mutations (STORE_EVENT / storage), or tab return after being away.
    const syncForeground = () => sync({ background: false });
    const syncBackground = () => sync({ background: true });
    window.addEventListener(STORE_EVENT, syncForeground);
    window.addEventListener('storage', syncForeground);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') syncBackground();
    };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility);
    return () => {
      window.removeEventListener(STORE_EVENT, syncForeground);
      window.removeEventListener('storage', syncForeground);
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [cachedHistoryRows, onSelect, refreshToken, selectedId]);

  useEffect(() => {
    if (!selectedId) {
      setOrders([]);
      setInventory([]);
      setDetailDataLoading(false);
      setDetailDataSessionKey('');
      return () => {};
    }
    // Wait for the session list merge to populate the real DB id. Firing a
    // session-less /api/sale_orders fetch returns 250 unrelated orders that
    // never join to this session's lots and show as "0 rows / Loading...".
    if (!selectedServerSessionId) {
      setDetailDataLoading(false);
      return () => {};
    }
    let cancelled = false;
    const requestId = detailDataRequestRef.current + 1;
    detailDataRequestRef.current = requestId;
    const nextSessionKey = String(selectedServerSessionId);
    const cachedDetail = detailDataCacheRef.current[nextSessionKey] || null;
    const orderPath = `/api/sale_orders?source=tiktok_live&summary=1&limit=5000&session_id=${encodeURIComponent(selectedServerSessionId)}`;
    if (cachedDetail) {
      setOrders(Array.isArray(cachedDetail.orders) ? cachedDetail.orders : []);
      setInventory(Array.isArray(cachedDetail.inventory) ? cachedDetail.inventory : []);
    }
    setDetailDataLoading(!cachedDetail);
    setDetailDataSessionKey(nextSessionKey);
    Promise.all([
      fetchApi(orderPath),
      cachedDetail?.inventory?.length
        ? Promise.resolve({ rows: cachedDetail.inventory })
        : fetchApi('/api/inventory?active=all&status=all&compact=1'),
    ])
      .then(([orderData, inventoryData]) => {
        if (cancelled || detailDataRequestRef.current !== requestId) return;
        const nextOrders = Array.isArray(orderData?.rows) ? orderData.rows : [];
        const nextInventory = Array.isArray(inventoryData?.rows) ? inventoryData.rows : [];
        detailDataCacheRef.current[nextSessionKey] = {
          orders: nextOrders.length || !cachedDetail ? nextOrders : (cachedDetail.orders || []),
          inventory: nextInventory.length || !cachedDetail ? nextInventory : (cachedDetail.inventory || []),
        };
        if (nextOrders.length || !cachedDetail) setOrders(nextOrders);
        if (nextInventory.length || !cachedDetail) setInventory(nextInventory);
      })
      .catch(() => {
        // Keep the last good session data visible. A short backend/API miss
        // should not blank the results table while the operator is working.
      })
      .finally(() => {
        if (!cancelled && detailDataRequestRef.current === requestId) setDetailDataLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken, selectedId, selectedServerSessionId]);

  useEffect(() => {
    if (!selectedId) return () => {};
    if (!selectedServerSessionId || selectedHasDetailRows) return () => {};

    let cancelled = false;
    fetchApi(`/api/tiktok_live_sessions/detail?session_id=${encodeURIComponent(selectedServerSessionId)}`)
      .then((data) => {
        if (cancelled) return;
        const detailSession = data?.session || null;
        if (!detailSession) return;
        setHistory((current) => current.map((entry) => (
          String(entry?.id || '') === String(selectedId || '') ? { ...entry, ...detailSession } : entry
        )));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedHasDetailRows, selectedId, selectedServerSessionId]);

  useEffect(() => {
    const needsRepair = (history || []).filter((item) => {
      const key = String(item?.id || '');
      if (!key || summaryRepairRef.current.has(key)) return false;
      if (!Number(item?.serverSessionId || 0)) return false;
      if (Array.isArray(item?.rows) && item.rows.length) return false;
      const serverSummary = item?.summary || {};
      const lotTotal = Number(item?.lotCount || serverSummary.totalLots || 0);
      const resultTotal = Number(serverSummary.confirmedLots || 0) + Number(serverSummary.cancelledLots || 0);
      return lotTotal > 0 && resultTotal > lotTotal;
    });
    if (!needsRepair.length) return () => {};

    let cancelled = false;
    needsRepair.slice(0, 3).forEach((item) => {
      const key = String(item?.id || '');
      summaryRepairRef.current.add(key);
      fetchApi(`/api/tiktok_live_sessions/detail?session_id=${encodeURIComponent(item.serverSessionId)}`)
        .then((data) => {
          if (cancelled) return;
          const detailSession = data?.session || null;
          if (!detailSession) return;
          setHistory((current) => current.map((entry) => (
            String(entry?.id || '') === key ? { ...entry, ...detailSession } : entry
          )));
        })
        .catch(() => {
          summaryRepairRef.current.delete(key);
        });
    });
    return () => {
      cancelled = true;
    };
  }, [history]);

  useEffect(() => {
    let cancelled = false;
    const selectedItem = (history || []).find((item) => String(item?.id || '') === String(selectedId || ''));
    const itemId = String(selectedItem?.id || '');
    const sessionKey = labelSessionKey(selectedItem);
    if (!itemId || !sessionKey || labelDownloads[itemId]?.artifactId || labelDownloads[itemId]?.url) return () => {
      cancelled = true;
    };
    fetchApi(`/api/tiktok_live_labels/artifacts?session_key=${encodeURIComponent(sessionKey)}`)
      .then((data) => {
        if (cancelled) return;
        const artifact = data?.artifact || null;
        if (!artifact?.id) return;
        setLabelDownloads((current) => {
          if (current[itemId]?.url || current[itemId]?.artifactId) return current;
          return {
            ...current,
            [itemId]: {
              artifactId: artifact.id,
              filename: artifact.filename || 'tiktok-live-labels-with-products.pdf',
              annotated: Number(artifact.annotated || 0),
              total: Number(artifact.total || 0),
              persisted: true,
            },
          };
        });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [history, labelDownloads, selectedId]);

  const inventoryByBarcode = useMemo(() => {
    const map = new Map();
    inventory.forEach((product) => {
      const barcode = normalizeSeedBarcode(product?.barcode);
      if (barcode) map.set(barcode, product);
    });
    return map;
  }, [inventory]);

  const summaries = useMemo(() => {
    const saleOrders = Array.isArray(orders) ? orders : [];
    return new Map(history.map((item) => {
      const allowedLots = new Set((item?.rows || []).map((row) => String(row?.lotNo || '').trim()).filter(Boolean));
      const matchedOrders = filterOrdersForSession(saleOrders, item);
      const serverSummary = item?.summary || {};
      if (item?.summaryOnly && Object.keys(serverSummary).length) {
        return [String(item?.id || ''), {
          revenue: Number(serverSummary.revenue || 0),
          platformFees: Number(serverSummary.platformFees || tikTokPlatformFee(serverSummary.revenue || 0)),
          costOfGoods: Number(serverSummary.costOfGoods || 0),
          profit: Number(serverSummary.profit || 0),
          lastSoldAt: item?.endedAt ? new Date(item.endedAt).getTime() : 0,
          totalOrders: Number(serverSummary.confirmedLots || serverSummary.pendingLots || 0),
          totalProducts: Number(serverSummary.confirmedLots || serverSummary.pendingLots || 0),
          uniqueCustomers: Number(serverSummary.customerCount || 0),
          cancelledOrders: Number(serverSummary.cancelledLots || 0),
        }];
      }
      if (!matchedOrders.length && Array.isArray(item?.rows) && item.rows.length) {
        const sessionRows = getTikTokSessionRows(item, [], inventoryByBarcode);
        const soldRows = sessionRows.filter((row) => row.status !== 'missing');
        const revenue = soldRows.reduce((sum, row) => sum + Number(row.salePrice || 0), 0);
        const platformFees = soldRows.reduce((sum, row) => sum + Number(row.fees || 0), 0);
        const costOfGoods = soldRows.reduce((sum, row) => sum + Number(row.cost || 0), 0);
        const profit = soldRows.reduce((sum, row) => sum + Number(row.profit || 0), 0);
        const uniqueCustomers = new Set(soldRows.map((row) => String(row.buyer || '').trim().toLowerCase()).filter(Boolean)).size;
        return [String(item?.id || ''), {
          revenue,
          platformFees,
          costOfGoods,
          profit,
          lastSoldAt: 0,
          totalOrders: soldRows.length,
          totalProducts: soldRows.length,
          uniqueCustomers,
          cancelledOrders: Math.max(0, allowedLots.size - soldRows.length),
        }];
      }
      const revenue = matchedOrders.reduce((sum, order) => sum + Number(order?.total_amount || 0), 0);
      const totalOrders = matchedOrders.length;
      const totalProducts = matchedOrders.reduce((sum, order) => sum + getOrderProductQty(order), 0);
      const lastSoldAt = matchedOrders.reduce((latest, order) => {
        const rawDate = order?.date_order || order?.sold_at || order?.created_at || order?.updated_at;
        const timestamp = rawDate ? new Date(rawDate).getTime() : 0;
        return timestamp && timestamp > latest ? timestamp : latest;
      }, 0);
      const uniqueCustomers = new Set(
        matchedOrders
          .map((order) => String(order?.whatnot_buyer_username || '').trim().toLowerCase())
          .filter(Boolean),
      ).size;
      const soldLotNumbers = new Set(matchedOrders.map((order) => extractOrderLotNumber(order)).filter(Boolean));
      const hasAuthoritativeOrderScope = Number(item?.serverSessionId || 0) > 0 || getSessionOrderRefs(item).size > 0;
      const cancelledOrders = hasAuthoritativeOrderScope
        ? Math.max(0, allowedLots.size - soldLotNumbers.size)
        : 0;
      const hasLineProfit = matchedOrders.some((order) => Number(order?.line_count || 0) > 0);
      const platformFees = matchedOrders.reduce((sum, order) => {
        const explicitFees = Number(order?.order_fees ?? order?.linked_fees ?? order?.fees);
        if (Number.isFinite(explicitFees) && explicitFees > 0) return sum + explicitFees;
        return sum + tikTokPlatformFee(order?.total_amount);
      }, 0);
      const lotMapProfit = (item?.rows || []).reduce((sum, row) => {
        if (!soldLotNumbers.has(String(row?.lotNo || '').trim())) return sum;
        const product = inventoryByBarcode.get(normalizeSeedBarcode(row?.barcode));
        return sum + (Number(matchedOrders.find((order) => extractOrderLotNumber(order) === String(row?.lotNo || '').trim())?.total_amount || 0) - Number(product?.cost_price || 0));
      }, 0);
      const grossProfit = hasLineProfit
        ? matchedOrders.reduce((sum, order) => sum + Number(order?.line_profit || 0), 0)
        : lotMapProfit;
      const costOfGoods = Math.max(0, revenue - grossProfit);
      const profit = grossProfit - platformFees;
      return [String(item?.id || ''), {
        revenue,
        platformFees,
        costOfGoods,
        profit,
        lastSoldAt,
        totalOrders,
        totalProducts,
        uniqueCustomers,
        cancelledOrders,
      }];
    }));
  }, [history, inventoryByBarcode, orders]);

  const overallDashboard = useMemo(() => {
    const sessionRows = history.map((item) => {
      const summary = summaries.get(String(item?.id || '')) || {};
      const ordersCount = Number(summary.totalOrders || 0);
      const cancelled = Number(summary.cancelledOrders || 0);
      const attemptedLots = ordersCount + cancelled;
      return {
        item,
        label: sessionCardTitle(item).replace('Go Live ', ''),
        date: sessionCardDate(item),
        revenue: Number(summary.revenue || 0),
        profit: Number(summary.profit || 0),
        cogs: Number(summary.costOfGoods || 0),
        orders: ordersCount,
        products: Number(summary.totalProducts || 0),
        customers: Number(summary.uniqueCustomers || 0),
        cancelled,
        fees: Number(summary.platformFees || 0),
        marginPct: Number(summary.revenue || 0) ? (Number(summary.profit || 0) / Number(summary.revenue || 0)) * 100 : null,
        lastSoldAt: Number(summary.lastSoldAt || 0),
        cancelRate: attemptedLots ? (cancelled / attemptedLots) * 100 : 0,
      };
    });
    const totals = sessionRows.reduce((acc, row) => ({
      revenue: acc.revenue + row.revenue,
      profit: acc.profit + row.profit,
      cogs: acc.cogs + row.cogs,
      orders: acc.orders + row.orders,
      products: acc.products + row.products,
      customers: acc.customers + row.customers,
      cancelled: acc.cancelled + row.cancelled,
      fees: acc.fees + row.fees,
    }), { revenue: 0, profit: 0, cogs: 0, orders: 0, products: 0, customers: 0, cancelled: 0, fees: 0 });
    const maxRevenue = Math.max(1, ...sessionRows.map((row) => row.revenue));
    const maxOrders = Math.max(1, ...sessionRows.map((row) => row.orders));
    const bestRevenue = [...sessionRows].sort((a, b) => b.revenue - a.revenue)[0] || null;
    const bestProfit = [...sessionRows].sort((a, b) => b.profit - a.profit)[0] || null;
    const riskSession = [...sessionRows].sort((a, b) => b.cancelRate - a.cancelRate)[0] || null;
    const marginPct = totals.revenue ? (totals.profit / totals.revenue) * 100 : 0;
    const avgOrder = totals.orders ? totals.revenue / totals.orders : 0;
    return {
      sessionRows,
      totals,
      maxRevenue,
      maxOrders,
      bestRevenue,
      bestProfit,
      riskSession,
      marginPct,
      avgOrder,
    };
  }, [history, summaries]);

  function setDetailView(sessionId, nextView) {
    setDetailViews((current) => ({ ...current, [String(sessionId)]: nextView }));
  }

  async function findOrderAcrossSessions() {
    const cleanOrderId = String(orderLookup || '').trim();
    if (!cleanOrderId) {
      setOrderLookupMessage('Enter a TikTok order ID first.');
      return;
    }
    setOrderLookupBusy(true);
    setOrderLookupMessage('');
    try {
      const data = await fetchApi(`/api/tiktok_live_sessions/search_order?order_id=${encodeURIComponent(cleanOrderId)}`);
      const matches = Array.isArray(data?.matches) ? data.matches : [];
      const match = matches[0] || null;
      if (!match?.session_id && !match?.session_key) {
        setOrderLookupMessage(`No TikTok Live session found for order ${cleanOrderId}.`);
        return;
      }
      const target = history.find((item) => (
        String(item?.serverSessionId || '') === String(match.session_id || '')
        || String(item?.id || '') === String(match.session_key || '')
      ));
      if (!target) {
        setOrderLookupMessage(`Order found in ${match.session_name || `session ${match.session_id}`}, but that session is not loaded in this view. Refresh and try again.`);
        return;
      }
      setDetailSearch(cleanOrderId);
      setDetailView(String(target.id || ''), 'orders');
      onSelect?.(target);
      setOrderLookupMessage(`Opened ${archiveLabel(target)}${match.lot_no ? ` · lot ${match.lot_no}` : ''}${match.buyer ? ` · ${match.buyer}` : ''}.`);
    } catch (err) {
      setOrderLookupMessage(err.message || 'Could not search TikTok Live orders.');
    } finally {
      setOrderLookupBusy(false);
    }
  }

  async function downloadAllTikTokSessionsCsv() {
    setAllCsvBusy(true);
    setOrderLookupMessage('');
    try {
      const response = await fetch('/api/tiktok_live_sessions/export_all.csv', {
        method: 'GET',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { Accept: 'text/csv' },
      });
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          message = payload?.error || payload?.message || message;
        } catch {
          // CSV export errors are often plain text or empty responses.
        }
        throw new Error(message);
      }
      const contentType = response.headers.get('Content-Type') || '';
      if (!contentType.toLowerCase().includes('text/csv')) {
        let message = 'Export did not return a CSV file.';
        try {
          const payload = await response.clone().json();
          message = payload?.error || payload?.message || message;
        } catch {
          // Keep the generic CSV mismatch message.
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition') || '';
      const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
      const fallbackName = `tiktok-go-live-all-sessions-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`;
      const filename = filenameMatch?.[1] || fallbackName;
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => window.URL.revokeObjectURL(url), 30000);
      setOrderLookupMessage('Downloaded all TikTok Go Live sessions CSV.');
    } catch (err) {
      setOrderLookupMessage(err.message || 'Could not download all sessions CSV.');
    } finally {
      setAllCsvBusy(false);
    }
  }

  function printSessionCard(item, mode = 'both') {
    onSelect?.(item);
    try {
      const lotBarcodeMap = new Map(
        (item?.rows || [])
          .map((row) => [String(row?.lotNo || '').trim(), normalizeSeedBarcode(row?.barcode)])
          .filter(([lotNo, barcode]) => lotNo && barcode),
      );
      const scopedOrders = filterOrdersForSession(Array.isArray(orders) ? orders : [], item);
      const shipmentsByBuyer = new Map();
      const ensureShipment = (buyerKey, payload = {}) => {
        const current = shipmentsByBuyer.get(buyerKey) || {
          sale_order_id: payload.sale_order_id || null,
          order_number: payload.order_number || '',
          username: payload.username || '',
          buyer_name: payload.buyer_name || payload.username || 'Unknown customer',
          order_count: 0,
          total_items: 0,
          total_lines: 0,
          total_price: 0,
          items: [],
        };
        if (payload.sale_order_id && !current.sale_order_id) current.sale_order_id = payload.sale_order_id;
        if (payload.order_number && !current.order_number) current.order_number = payload.order_number;
        if (payload.username && !current.username) current.username = payload.username;
        if (payload.buyer_name && (!current.buyer_name || current.buyer_name === 'Unknown customer')) current.buyer_name = payload.buyer_name;
        shipmentsByBuyer.set(buyerKey, current);
        return current;
      };

      scopedOrders.forEach((order) => {
        const username = String(order?.whatnot_buyer_username || '').trim();
        const buyerKey = username || `order-${order?.id}`;
        const current = ensureShipment(buyerKey, {
          sale_order_id: order?.id,
          order_number: order?.order_number,
          username,
          buyer_name: username || order?.partner_id_name || 'Unknown customer',
        });
        current.order_count += 1;
        const lotNumber = String(extractOrderLotNumber(order) || '').trim();
        const barcode = lotBarcodeMap.get(lotNumber) || '';
        const product = inventoryByBarcode.get(normalizeSeedBarcode(barcode));
        const price = Number(order?.total_amount || order?.subtotal || 0);
        const sellerSku = String(order?.seller_sku || order?.sku || '').trim();
        current.items.push({
          lot_number: lotNumber,
          barcode,
          sku: product?.default_code || product?.sku || sellerSku,
          tiktok_seller_sku: sellerSku,
          product_name: product?.name || order?.combined_listing || order?.product_name || `Lot ${lotNumber || ''}`.trim() || 'Unknown product',
          qty: 1,
          price,
          sale_price: price,
        });
        current.total_items += 1;
        current.total_lines += 1;
        current.total_price += price;
      });

      if (!shipmentsByBuyer.size) {
        (item?.rows || []).forEach((row) => {
          const statusFamily = String(row?.statusFamily || '').trim().toLowerCase();
          if (!['pending', 'confirmed'].includes(statusFamily)) return;
          const lotNumber = String(row?.lotNo || '').trim();
          if (!lotNumber) return;
          const buyerName = String(row?.buyer || row?.buyerDisplayName || '').trim();
          const buyerUsername = String(row?.buyerUsername || '').trim();
          const buyerKey = buyerUsername || buyerName || `lot-${lotNumber}`;
          const current = ensureShipment(buyerKey, {
            order_number: String(row?.orderId || '').trim(),
            username: buyerUsername,
            buyer_name: buyerName || buyerUsername || 'Unknown customer',
          });
          current.order_count += 1;
          const rowItems = Array.isArray(row?.items) && row.items.length
	            ? row.items.map((entry) => ({
	                lot_number: lotNumber,
	                barcode: normalizeSeedBarcode(entry?.barcode || row?.barcode || ''),
	                sku: String(entry?.sku || row?.tiktokSellerSku || row?.sku || '').trim(),
	                tiktok_seller_sku: String(row?.tiktokSellerSku || row?.tiktokOrder?.sellerSku || '').trim(),
	                product_name: String(entry?.productName || row?.productName || '').trim() || `Lot ${lotNumber}`,
                qty: 1,
                price: Number(row?.salesPrice || 0),
                sale_price: Number(row?.salesPrice || 0),
              }))
            : [{
	                lot_number: lotNumber,
	                barcode: normalizeSeedBarcode(row?.barcode || ''),
	                sku: String(row?.tiktokSellerSku || row?.sku || '').trim(),
	                tiktok_seller_sku: String(row?.tiktokSellerSku || row?.tiktokOrder?.sellerSku || '').trim(),
                product_name: String(row?.productName || '').trim() || `Lot ${lotNumber}`,
                qty: 1,
                price: Number(row?.salesPrice || 0),
                sale_price: Number(row?.salesPrice || 0),
              }];
          rowItems.forEach((entry) => {
            current.items.push(entry);
            current.total_items += Number(entry.qty || 1);
            current.total_lines += 1;
          });
          current.total_price += Number(row?.salesPrice || 0);
        });
      }

      const scopedShipments = [...shipmentsByBuyer.values()]
        .map((ship) => ({
          ...ship,
          items: ship.items.sort((left, right) => Number(left.lot_number || 0) - Number(right.lot_number || 0)),
          total_price: Number(ship.total_price.toFixed(2)),
        }))
        .sort((left, right) => String(left.username || left.buyer_name || '').localeCompare(String(right.username || right.buyer_name || '')));
      const summary = {
        total_shipments: scopedShipments.length,
        total_lots: scopedShipments.reduce((sum, ship) => sum + (ship.items || []).length, 0),
        total_units: scopedShipments.reduce((sum, ship) => sum + Number(ship.total_items || 0), 0),
        total_revenue: Number(scopedShipments.reduce((sum, ship) => sum + Number(ship.total_price || 0), 0).toFixed(2)),
        matched: scopedShipments.reduce((sum, ship) => sum + (ship.items || []).length, 0),
        orders_synced: scopedOrders.length,
      };
      const pullSummary = buildPullSummary(scopedShipments);
      downloadPickListPdf({
        mode,
        sessionName: archiveLabel(item),
        shipments: scopedShipments,
        summary,
        pullSummary,
      });
    } catch (error) {
      window.alert(`Unable to prepare PDF.\n\n${String(error?.message || error || 'Unknown error')}`);
    }
  }

  async function loadCsvFile(file) {
    if (!file) return;
    try {
      setCsvFileName(file.name);
      setCsvSummary(null);
      if (isExcelUpload(file)) {
        const workbookBase64 = await readFileAsBase64(file);
        setCsvText('');
        setCsvWorkbookBase64(workbookBase64);
        setCsvMessage(`${file.name} loaded. Excel workbook will be converted during import.`);
      } else {
        const text = await file.text();
        setCsvText(text);
        setCsvWorkbookBase64('');
        setCsvMessage(`${file.name} loaded.`);
      }
    } catch (err) {
      setCsvMessage(err.message || 'Could not read CSV/XLSX file.');
    }
  }

  function rememberImportedOrders(item, imported) {
    const importedRefs = [...new Set(
      (Array.isArray(imported) ? imported : [])
        .map((row) => String(row?.external_order_ref || '').trim())
        .filter(Boolean),
    )];
    if (!importedRefs.length) return;

    const itemId = String(item?.id || '');
    const mergeItem = (entry) => {
      if (String(entry?.id || '') !== itemId) return entry;
      return {
        ...entry,
        importedOrderRefs: [...new Set([...(entry.importedOrderRefs || []), ...importedRefs])],
        matchMode: 'imported_order_refs',
      };
    };

    setHistory((current) => current.map(mergeItem));
    const store = readStore();
    writeStore({
      ...store,
      history: (store.history || []).map(mergeItem),
    });
  }

  async function processCsv(item, commit) {
    if (!csvText.trim() && !csvWorkbookBase64) {
      setCsvMessage('Choose or drop the TikTok CSV/XLSX file first.');
      return;
    }
    setCsvBusy(true);
    setCsvMessage('');
    try {
      const data = await postApi('/api/tiktok_live_orders/import_csv', {
        csv_text: csvText,
        xlsx_base64: csvWorkbookBase64,
        xlsx_filename: csvFileName,
        lot_map_csv_text: buildInlineLotMapCsv(item?.rows || [], inventoryByBarcode),
        session_id: item?.serverSessionId || null,
        commit,
      });
      setCsvSummary(data?.summary || null);
      setCsvMessage(commit
        ? `Imported ${data?.summary?.imported_rows || 0} rows for ${archiveLabel(item)}.`
        : `Preview ready: ${data?.summary?.ready_rows || 0} ready, ${data?.summary?.duplicate_rows || 0} duplicates, ${data?.summary?.unmatched_rows || 0} unmatched.`);
      if (commit) {
        rememberImportedOrders(item, data?.imported || []);
        onImported?.();
      }
    } catch (err) {
      setCsvMessage(err.message || 'Could not process TikTok CSV.');
    } finally {
      setCsvBusy(false);
    }
  }

  async function waitForLatestLabelArtifact(sessionKey, startedAtMs, sessionFilename) {
    if (!sessionKey) return null;
    const minCreatedAtMs = Number(startedAtMs || 0);
    const targetFilename = String(sessionFilename || '').trim();
    for (let attempt = 0; attempt < 18; attempt += 1) {
      try {
        const data = await fetchApi(`/api/tiktok_live_labels/artifacts?session_key=${encodeURIComponent(sessionKey)}`);
        const artifact = data?.artifact || null;
        const createdAtMs = artifact?.created_at ? Date.parse(artifact.created_at) : 0;
        const sameFilename = !targetFilename || String(artifact?.filename || '').trim() === targetFilename;
        if (artifact?.id && sameFilename && (!minCreatedAtMs || createdAtMs >= (minCreatedAtMs - 5000))) {
          return artifact;
        }
      } catch (_) {
        // Ignore polling failures and keep trying briefly.
      }
      await new Promise((resolve) => window.setTimeout(resolve, 5000));
    }
    return null;
  }

  async function enrichLabelPdf(file, item) {
    if (!file) return;
    setLabelBusy(true);
    setLabelMessage('');
    const itemId = String(item?.id || '');
    const previous = labelDownloads[itemId];
    if (previous?.url) URL.revokeObjectURL(previous.url);
    setLabelDownloads((current) => {
      const next = { ...current };
      delete next[itemId];
      return next;
    });
    const startedAtMs = Date.now();
    let sessionFilename = '';
    let sessionKey = '';
    try {
      const csrf = getStoredCsrfToken();
      sessionFilename = `${archiveLabel(item).replace(/[^A-Za-z0-9._ -]+/g, '').replace(/\s+/g, '-').replace(/-+/g, '-')}-labels-with-product-names.pdf`;
      sessionKey = labelSessionKey(item);
      const params = new URLSearchParams({
        filename: sessionFilename || file.name || 'tiktok-live-labels.pdf',
      });
      if (item?.serverSessionId) params.set('session_id', String(item.serverSessionId));
      if (sessionKey) params.set('session_key', sessionKey);
      const endpoint = `/api/tiktok_live_labels/enrich_pdf?${params.toString()}`;
      const form = new FormData();
      form.append('pdf', file, file.name || sessionFilename || 'tiktok-live-labels.pdf');
      form.append('filename', sessionFilename || file.name || 'tiktok-live-labels.pdf');
      form.append('lot_map_csv_text', buildInlineLotMapCsv(item?.rows || [], inventoryByBarcode));
      if (item?.serverSessionId) form.append('session_id', String(item.serverSessionId));
      if (sessionKey) form.append('session_key', sessionKey);
      const res = await fetch(endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        body: form,
      });
      if (!res.ok) {
        const errorBody = await res.json().catch(() => ({}));
        const recovered = await waitForLatestLabelArtifact(sessionKey, startedAtMs, sessionFilename);
        if (recovered?.id) {
          setLabelDownloads((current) => ({
            ...current,
            [itemId]: {
              artifactId: recovered.id,
              filename: recovered.filename || sessionFilename,
              annotated: Number(recovered.annotated || 0),
              total: Number(recovered.total || 0),
              persisted: true,
            },
          }));
          setLabelMessage(`Labels PDF finished in background: ${Number(recovered.annotated || 0)} packing slips updated${recovered.total ? ` out of ${Number(recovered.total || 0)} pages` : ''}. Click Download Labels PDF when you want it.`);
          return;
        }
        throw new Error(errorBody.error || `Unable to enrich label PDF (${res.status})`);
      }
      const annotated = Number(res.headers.get('X-YNF-Annotated-Pages') || 0);
      const total = Number(res.headers.get('X-YNF-Total-Pages') || 0);
      const artifactId = res.headers.get('X-YNF-Label-Artifact-Id') || '';
      const artifactFilename = res.headers.get('X-YNF-Label-Artifact-Filename') || sessionFilename;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setLabelDownloads((current) => ({
        ...current,
        [itemId]: {
          url,
          artifactId,
          filename: artifactFilename || sessionFilename,
          annotated,
          total,
          persisted: Boolean(artifactId),
        },
      }));
      setLabelMessage(`Labels PDF ready: ${annotated} packing slips updated${total ? ` out of ${total} pages` : ''}. Click Download Labels PDF when you want it.`);
    } catch (err) {
      const recovered = await waitForLatestLabelArtifact(sessionKey, startedAtMs, sessionFilename);
      if (recovered?.id) {
        setLabelDownloads((current) => ({
          ...current,
          [itemId]: {
            artifactId: recovered.id,
            filename: recovered.filename || sessionFilename || 'tiktok-live-labels.pdf',
            annotated: Number(recovered.annotated || 0),
            total: Number(recovered.total || 0),
            persisted: true,
          },
        }));
        setLabelMessage(`Labels PDF finished in background: ${Number(recovered.annotated || 0)} packing slips updated${recovered.total ? ` out of ${Number(recovered.total || 0)} pages` : ''}. Click Download Labels PDF when you want it.`);
      } else {
        setLabelMessage(err.message || 'Could not prepare product-name label PDF.');
      }
    } finally {
      setLabelBusy(false);
    }
  }

  const activeItem = useMemo(() => {
    if (!history.length) return null;
    return history.find((item) => String(item?.id || '') === String(selectedId || '')) || null;
  }, [history, selectedId]);

  const activeSummary = useMemo(() => {
    if (!activeItem) {
      return {
        revenue: 0,
        profit: 0,
        platformFees: 0,
        costOfGoods: 0,
        totalOrders: 0,
        totalProducts: 0,
        uniqueCustomers: 0,
        cancelledOrders: 0,
      };
    }
    return summaries.get(String(activeItem?.id || '')) || {
      revenue: 0,
      profit: 0,
      platformFees: 0,
      costOfGoods: 0,
      totalOrders: 0,
      totalProducts: 0,
      uniqueCustomers: 0,
      cancelledOrders: 0,
    };
  }, [activeItem, summaries]);

  const activeDetailView = detailViews[String(activeItem?.id || '')] || 'products';
  const activeLabelDownload = labelDownloads[String(activeItem?.id || '')] || null;
  const filteredSessionRows = useMemo(() => {
    const term = sessionSearch.trim().toLowerCase();
    const searchedRows = overallDashboard.sessionRows.filter((row) => {
      if (!term) return true;
      return [
        row.label,
        row.date,
        archiveLabel(row.item),
        row.item?.liveName,
        row.item?.serverSessionId,
      ].some((value) => String(value || '').toLowerCase().includes(term));
    });
    if (overviewMode === 'revenue') return [...searchedRows].sort((left, right) => right.revenue - left.revenue);
    if (overviewMode === 'profit') return [...searchedRows].sort((left, right) => right.profit - left.profit);
    if (overviewMode === 'risk') return [...searchedRows].sort((left, right) => right.cancelRate - left.cancelRate);
    if (overviewMode === 'recent') return [...searchedRows].sort((left, right) => right.lastSoldAt - left.lastSoldAt);
    return searchedRows;
  }, [overallDashboard.sessionRows, overviewMode, sessionSearch]);

  const totalFees = overallDashboard.totals.fees || tikTokPlatformFee(overallDashboard.totals.revenue);
  const overviewModes = [
    { id: 'all', label: 'All Sessions' },
    { id: 'revenue', label: 'Best Revenue' },
    { id: 'profit', label: 'Best Profit' },
    { id: 'risk', label: 'High Risk' },
    { id: 'recent', label: 'Recent' },
  ];
  const bestRevenueShare = overallDashboard.totals.revenue > 0 && overallDashboard.bestRevenue
    ? (overallDashboard.bestRevenue.revenue / overallDashboard.totals.revenue) * 100
    : 0;
  const riskSessionOrders = Number(overallDashboard.riskSession?.orders || 0);
  const topSnapshotStats = [
    {
      label: 'Sessions',
      value: filteredSessionRows.length.toLocaleString(),
      sub: `${history.length} tracked`,
      active: overviewMode === 'all',
      onClick: () => setOverviewMode('all'),
    },
    {
      label: 'Revenue',
      value: fmt(overallDashboard.totals.revenue),
      sub: `${fmtPct(bestRevenueShare)} from top session`,
      color: 'var(--accent-amber)',
      active: overviewMode === 'revenue',
      onClick: () => setOverviewMode('revenue'),
    },
    {
      label: 'Profit',
      value: fmt(overallDashboard.totals.profit),
      sub: overallDashboard.bestProfit ? `${archiveLabel(overallDashboard.bestProfit.item)} leads` : 'No profit data yet',
      color: clrProfit(overallDashboard.totals.profit),
      active: overviewMode === 'profit',
      onClick: () => setOverviewMode('profit'),
    },
    {
      label: 'Cancel Risk',
      value: overallDashboard.riskSession ? fmtPct(overallDashboard.riskSession.cancelRate) : '—',
      sub: riskSessionOrders ? `${riskSessionOrders.toLocaleString()} sold in riskiest session` : 'No cancel variance yet',
      color: overallDashboard.riskSession?.cancelRate > 0 ? 'var(--accent-coral)' : 'var(--text-secondary)',
      active: overviewMode === 'risk',
      onClick: () => setOverviewMode('risk'),
    },
    {
      label: 'Avg Order',
      value: fmt(overallDashboard.avgOrder),
      sub: `${overallDashboard.totals.customers.toLocaleString()} customers`,
      color: '#2563eb',
      active: overviewMode === 'recent',
      onClick: () => setOverviewMode('recent'),
    },
  ];

  return (
    <section className="company-panel" style={{ overflow: 'hidden', borderColor: '#dbe3ec', background: '#ffffff' }}>
      <div className="company-panel-body" style={{ display: 'grid', gap: 16, background: '#ffffff' }}>
        {historyMessage ? (
          <div style={{
            padding: '9px 12px',
            borderRadius: 12,
            border: '1px solid #dbe3ec',
            background: historyMessage.startsWith('Could not') ? '#fef2f2' : '#f8fafc',
            color: historyMessage.startsWith('Could not') ? '#b91c1c' : '#475569',
            fontSize: 12,
            fontWeight: 700,
          }}>
            {historyMessage}
          </div>
        ) : null}
        <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel.sheet.macroEnabled.12"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) loadCsvFile(file);
                event.target.value = '';
              }}
              style={{ display: 'none' }}
            />
            <input
              ref={labelInputRef}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file && activeItem) enrichLabelPdf(file, activeItem);
                event.target.value = '';
              }}
              style={{ display: 'none' }}
            />

            <div style={{ display: 'grid', gap: 14 }}>
              <div style={sessionToolPanelStyle('plain')}>
                <div style={{ display: 'grid', gap: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <div style={{ fontSize: 11, fontWeight: 900, color: '#2563eb', letterSpacing: '0.1em', textTransform: 'uppercase' }}>TikTok Live Auctions</div>
                        <Badge custom={{ label: `${filteredSessionRows.length} visible`, bg: '#eff6ff', color: '#2563eb' }} />
                        {overallDashboard.bestProfit ? <Badge custom={{ label: `Best profit ${fmt(overallDashboard.bestProfit.profit)}`, bg: '#ecfdf5', color: '#047857' }} /> : null}
                      </div>
                      <div style={{ marginTop: 6, fontSize: 28, fontWeight: 950, color: '#0f172a', letterSpacing: '-0.03em' }}>Session overview</div>
                    </div>
	                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
	                      <button type="button" onClick={() => window.dispatchEvent(new Event(STORE_EVENT))} style={sessionActionButtonStyle('blue')}>Refresh</button>
	                      <button type="button" onClick={() => labelInputRef.current?.click()} disabled={labelBusy || !activeItem} style={{ ...sessionActionButtonStyle('plain'), opacity: labelBusy || !activeItem ? 0.6 : 1 }}>Upload Labels PDF</button>
	                      <button type="button" onClick={() => activeItem && printSessionCard(activeItem, 'pick')} disabled={!activeItem} style={{ ...sessionActionButtonStyle('plain'), opacity: !activeItem ? 0.6 : 1 }}>Picklist</button>
	                      <button type="button" onClick={() => activeItem && printSessionCard(activeItem, 'grab')} disabled={!activeItem} style={{ ...sessionActionButtonStyle('plain'), opacity: !activeItem ? 0.6 : 1 }}>Grablist</button>
	                      <button type="button" onClick={() => activeItem && downloadTikTokSessionCsv(activeItem, orders, inventoryByBarcode)} disabled={!activeItem} style={{ ...sessionActionButtonStyle('plain'), opacity: !activeItem ? 0.6 : 1 }}>CSV</button>
		                      <button type="button" onClick={downloadAllTikTokSessionsCsv} disabled={allCsvBusy} style={{ ...sessionActionButtonStyle('plain'), opacity: allCsvBusy ? 0.6 : 1 }}>{allCsvBusy ? 'Downloading...' : 'All CSV'}</button>
	                      <button type="button" onClick={() => activeItem && printTikTokSessionReport(activeItem, activeSummary, orders, inventoryByBarcode)} disabled={!activeItem} style={{ ...sessionActionButtonStyle('plain'), opacity: !activeItem ? 0.6 : 1 }}>Print Report</button>
	                    </div>
	                  </div>
	                  <div style={{ marginTop: -4, fontSize: 11, color: '#64748b', fontWeight: 700 }}>
	                    Label upload automatically maps TikTok batches: B1 lots 1-300, B2 lots 301-600, B3 lots 601-900, and continues by 300.
	                  </div>

	                  <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 260px) minmax(280px, 1fr)', gap: 10, alignItems: 'center', padding: 12, border: '1px solid #dbe3ec', borderRadius: 16, background: 'linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)' }}>
                    <select
                      value={String(selectedId || '')}
                      onChange={(event) => {
                        if (!event.target.value) {
                          onSelect?.(null);
                          return;
                        }
                        const next = history.find((item) => String(item?.id || '') === String(event.target.value || ''));
                        if (next) onSelect?.(next);
                      }}
                      style={{ background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1', borderRadius: 10, padding: '10px 12px', fontSize: 13, fontWeight: 700, width: '100%', maxWidth: '100%' }}
                    >
                      <option value="">All Sessions</option>
                      {history.map((item) => (
                        <option key={item.id} value={String(item.id)}>
                          {archiveLabel(item)}
                        </option>
                      ))}
                    </select>
                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(210px, 0.8fr) minmax(260px, 1fr) auto', gap: 10, alignItems: 'center' }}>
                      <input value={sessionSearch} onChange={(event) => setSessionSearch(event.target.value)} placeholder="Search session, date, ID..." style={{ ...inputStyle, minWidth: 220, width: '100%' }} />
                      <input
                        value={orderLookup}
                        onChange={(event) => {
                          setOrderLookup(event.target.value);
                          if (orderLookupMessage) setOrderLookupMessage('');
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') findOrderAcrossSessions();
                        }}
                        placeholder="Find order ID across all Go Live sessions..."
                        style={{ ...inputStyle, minWidth: 240, width: '100%' }}
                      />
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                        <button
                          type="button"
                          onClick={findOrderAcrossSessions}
                          disabled={orderLookupBusy}
                          style={{
                            border: '1px solid #dbe3ec',
                            background: orderLookupBusy ? '#f8fafc' : '#111827',
                            color: orderLookupBusy ? '#94a3b8' : '#ffffff',
                            borderRadius: 10,
                            padding: '8px 11px',
                            fontSize: 11,
                            fontWeight: 900,
                            letterSpacing: '0.03em',
                            cursor: orderLookupBusy ? 'default' : 'pointer',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {orderLookupBusy ? 'Searching...' : 'Find Order'}
                        </button>
                        {overviewModes.map((mode) => (
                          <button
                            key={mode.id}
                            type="button"
                            onClick={() => setOverviewMode(mode.id)}
                            style={{
                              border: overviewMode === mode.id ? '1px solid #c7d2fe' : '1px solid #dbe3ec',
                              background: overviewMode === mode.id ? '#eef2ff' : '#ffffff',
                              color: overviewMode === mode.id ? '#3730a3' : '#475569',
                              borderRadius: 999,
                              padding: '7px 10px',
                              fontSize: 11,
                              fontWeight: 800,
                              letterSpacing: '0.03em',
                              cursor: 'pointer',
                              boxShadow: overviewMode === mode.id ? '0 10px 22px rgba(79,70,229,0.12)' : 'none',
                            }}
                          >
                            {mode.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                  {orderLookupMessage ? (
	                    <div style={{ marginTop: -2, fontSize: 12, fontWeight: 700, color: /^(No |Could not|Enter )/.test(orderLookupMessage) ? '#b91c1c' : '#047857' }}>
                      {orderLookupMessage}
                    </div>
                  ) : null}

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: 10 }}>
                    {topSnapshotStats.map((stat) => (
                      <button
                        key={stat.label}
                        type="button"
                        onClick={stat.onClick}
                        style={{
                          ...compactMetricPillStyle('indigo', stat.active),
                          border: stat.active ? '1px solid rgba(99,102,241,0.28)' : '1px solid #dbe3ec',
                          background: stat.active ? 'linear-gradient(180deg, #ffffff 0%, #eef2ff 100%)' : 'linear-gradient(180deg, #ffffff 0%, #fafafa 100%)',
                          minHeight: 88,
                          alignContent: 'start',
                          gap: 6,
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ fontSize: 11, fontWeight: 900, color: '#64748b', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{stat.label}</div>
                        <div style={{ fontSize: 16, fontWeight: 950, color: stat.color || '#0f172a', letterSpacing: '-0.02em' }}>{stat.value}</div>
                        <div style={{ fontSize: 11, color: '#64748b', lineHeight: 1.4 }}>{stat.sub}</div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {!activeItem ? (
            <section style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.7fr) minmax(280px, 0.72fr)', gap: 14, alignItems: 'start' }}>
              <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: '16px 18px', display: 'grid', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Session Summary</div>
                  <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                    Ranked live-session performance with direct drill-in to order, label, and picklist work.
                  </div>
                </div>
                <TableShell footer={`${filteredSessionRows.length} session${filteredSessionRows.length !== 1 ? 's' : ''}`} tableStyle={{ tableLayout: 'fixed' }}>
                  <colgroup>
                    <col style={{ width: '19%' }} />
                    <col style={{ width: '10%' }} />
                    <col style={{ width: '14%' }} />
                    <col style={{ width: '12%' }} />
                    <col style={{ width: '14%' }} />
                    <col style={{ width: '10%' }} />
                    <col style={{ width: '14%' }} />
                    <col style={{ width: '7%' }} />
                  </colgroup>
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
                    {!filteredSessionRows.length ? <EmptyRow cols={8} loading={historyLoading} msg={historyLoading ? 'Loading TikTok sessions…' : 'No matching TikTok sessions.'} /> : null}
                    {filteredSessionRows.map((row) => (
                      <tr key={row.item?.id || row.label} style={{ borderTop: '1px solid var(--border-subtle)', cursor: 'pointer' }} onClick={() => onSelect?.(row.item)}>
                        <td style={{ padding: '10px 14px', fontWeight: 800 }}>
                          <div>{row.label}</div>
                          <div style={{ marginTop: 3, fontSize: 11, color: 'var(--text-secondary)', fontWeight: 600 }}>{row.date}</div>
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 800 }}>{row.orders.toLocaleString()}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 900, color: 'var(--accent-amber)' }}>{fmt(row.revenue)}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(row.fees || tikTokPlatformFee(row.revenue))}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 900, color: clrProfit(row.profit) }}>{fmt(row.profit)}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minWidth: 62, padding: '4px 8px', borderRadius: 999, background: row.marginPct >= 25 ? '#ecfdf5' : row.marginPct >= 15 ? '#fff7ed' : '#fef2f2', color: clrMargin(row.marginPct), fontSize: 11, fontWeight: 900, letterSpacing: '0.03em' }}>
                            {fmtPct(row.marginPct)}
                          </span>
                        </td>
                        <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontSize: 12 }}>{row.lastSoldAt ? fmtDt(row.lastSoldAt) : '—'}</td>
                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                          <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', borderRadius: 999, padding: '5px 10px', border: '1px solid #dbeafe', background: '#eff6ff', color: '#2563eb', fontSize: 11, fontWeight: 900, letterSpacing: '0.03em' }}>
                            Open
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              </div>

              <aside style={{ display: 'grid', gap: 12, position: 'sticky', top: 0, alignSelf: 'start' }}>
                <div style={{ ...sessionToolPanelStyle('plain'), gap: 10, padding: 14 }}>
                  <div style={{ fontSize: 11, fontWeight: 900, color: '#64748b', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Intelligence Rail</div>
                  <div style={overviewStatCardStyle()}>
                    <div style={overviewStatLabelStyle()}>Best revenue session</div>
                    <div style={overviewStatValueStyle('#d97706')}>{overallDashboard.bestRevenue ? archiveLabel(overallDashboard.bestRevenue.item) : '—'}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{overallDashboard.bestRevenue ? `${fmt(overallDashboard.bestRevenue.revenue)} revenue` : 'No session data yet'}</div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
                    <div style={overviewStatCardStyle()}>
                      <div style={overviewStatLabelStyle()}>Avg order</div>
                      <div style={overviewStatValueStyle('#2563eb')}>{fmt(overallDashboard.avgOrder)}</div>
                    </div>
                    <div style={overviewStatCardStyle()}>
                      <div style={overviewStatLabelStyle()}>Customers</div>
                      <div style={overviewStatValueStyle('#0f766e')}>{overallDashboard.totals.customers.toLocaleString()}</div>
                    </div>
                  </div>
                  <div style={overviewStatCardStyle()}>
                    <div style={overviewStatLabelStyle()}>Highest cancel risk</div>
                    <div style={overviewStatValueStyle(overallDashboard.riskSession?.cancelRate > 0 ? '#dc2626' : '#0f172a')}>{overallDashboard.riskSession ? archiveLabel(overallDashboard.riskSession.item) : '—'}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{overallDashboard.riskSession ? `${fmtPct(overallDashboard.riskSession.cancelRate)} cancel rate` : 'No cancellation variance yet'}</div>
                  </div>
                  <div style={overviewStatCardStyle()}>
                    <div style={overviewStatLabelStyle()}>Best profit</div>
                    <div style={overviewStatValueStyle(clrProfit(overallDashboard.bestProfit?.profit || 0))}>{overallDashboard.bestProfit ? fmt(overallDashboard.bestProfit.profit) : '—'}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{overallDashboard.bestProfit ? archiveLabel(overallDashboard.bestProfit.item) : 'No profit spread yet'}</div>
                  </div>
                </div>
              </aside>
            </section>
            ) : null}

            {activeItem ? (
              <>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={!activeItem}
                    style={{ ...sessionActionButtonStyle('plain'), opacity: !activeItem ? 0.6 : 1 }}
                  >
                    Upload Orders CSV
                  </button>
                  <button
                    type="button"
                    onClick={() => activeItem && processCsv(activeItem, false)}
                    disabled={csvBusy || !activeItem || (!csvText.trim() && !csvWorkbookBase64)}
                    style={{ ...sessionActionButtonStyle('plain'), opacity: csvBusy || !activeItem || (!csvText.trim() && !csvWorkbookBase64) ? 0.6 : 1 }}
                  >
                    {csvBusy ? 'Working…' : 'Preview Orders'}
                  </button>
                  <button
                    type="button"
                    onClick={() => activeItem && processCsv(activeItem, true)}
                    disabled={csvBusy || !activeItem || (!csvText.trim() && !csvWorkbookBase64)}
                    style={{ ...sessionActionButtonStyle('blue'), opacity: csvBusy || !activeItem || (!csvText.trim() && !csvWorkbookBase64) ? 0.6 : 1 }}
                  >
                    {csvBusy ? 'Working…' : 'Import Orders'}
                  </button>
                  {csvFileName ? (
                    <span style={{ fontSize: 12, color: '#64748b', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {csvFileName}
                    </span>
                  ) : null}
                  {activeLabelDownload ? (
                    <a
                      href={labelArtifactUrl(activeLabelDownload)}
                      download={activeLabelDownload.filename}
                      style={{ ...sessionActionButtonStyle('plain'), textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}
                    >
                      Download Updated PDF
                    </a>
                  ) : null}
                </div>

                {csvMessage ? (
                  <div style={{ fontSize: 13, color: '#64748b' }}>{csvMessage}</div>
                ) : null}
                {csvSummary ? (
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Badge custom={{ label: `${csvSummary.total_rows || 0} rows`, bg: '#f8fafc', color: '#475569' }} />
                    <Badge custom={{ label: `${csvSummary.ready_rows || 0} ready`, bg: '#ecfdf5', color: '#047857' }} />
                    <Badge custom={{ label: `${csvSummary.duplicate_rows || 0} duplicates`, bg: '#fff7ed', color: '#c2410c' }} />
                    <Badge custom={{ label: `${csvSummary.unmatched_rows || 0} unmatched`, bg: '#fef2f2', color: '#dc2626' }} />
                  </div>
                ) : null}
                {labelMessage ? (
                  <div style={{ fontSize: 13, color: '#047857', fontWeight: 700 }}>{labelMessage}</div>
                ) : null}

                {renderExpandedContent ? renderExpandedContent(activeItem, activeDetailView, {
                  orders,
                  inventory,
                  detailSearch,
                  detailDataLoading,
                  detailDataSessionKey,
                }) : null}
              </>
            ) : null}
        </>
      </div>
    </section>
  );
}

export default function TikTokLiveSetup() {
  const [inventory, setInventory] = useState([]);
  const [lotCount, setLotCount] = useState('200');
  const [rows, setRows] = useState([]);
  const [isLive, setIsLive] = useState(false);
  const [liveName, setLiveName] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const [detailsCsvText, setDetailsCsvText] = useState('');
  const [detailsCsvName, setDetailsCsvName] = useState('');
  const [preview, setPreview] = useState(null);
  const [history, setHistory] = useState([]);
  const [liveSequence, setLiveSequence] = useState(0);
  const [serverSessionId, setServerSessionId] = useState(null);
  const [barcodeSearchRow, setBarcodeSearchRow] = useState(null);
  const barcodeRefs = useRef({});

  useEffect(() => {
    setLoading(true);
    fetchApi('/api/inventory?active=all&status=all&compact=1')
      .then((data) => setInventory(data.rows || []))
      .catch(() => setInventory([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const store = readStore();
    setLotCount(store.draft.lotCount || '200');
    setRows(Array.isArray(store.draft.rows) ? store.draft.rows : []);
    setIsLive(!!store.draft.isLive);
    setLiveName(store.draft.liveName || '');
    setDetailsCsvText(store.draft.detailsCsvText || '');
    setDetailsCsvName(store.draft.detailsCsvName || '');
    setHistory(store.history || []);
    setLiveSequence(Number(store.seq || 0));
    setServerSessionId(store.draft.serverSessionId || null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchApi('/api/tiktok_live_sessions/active?fast=1')
      .then((data) => {
        if (cancelled) return;
        const session = data?.session || null;
        const sessionRows = Array.isArray(session?.rows) ? session.rows : [];
        const scannedRows = countScannedRows(sessionRows);
        if (!session?.serverSessionId || !scannedRows) return;

        const store = readStore();
        const draftRows = Array.isArray(store.draft?.rows) ? store.draft.rows : [];
        const sameSession = Number(store.draft?.serverSessionId || 0) === Number(session.serverSessionId || 0);
        if (sameSession && countScannedRows(draftRows) >= scannedRows && draftRows.length >= sessionRows.length) return;

        setRows((currentRows) => mergeDraftRows(currentRows, sessionRows));
        setLotCount(String(Math.max(sessionRows.length, Number(store.draft?.lotCount || 0), 1)));
        setIsLive(true);
        setLiveName(session.liveName || store.draft?.liveName || '');
        setServerSessionId(session.serverSessionId || null);
        setLiveSequence((current) => Math.max(Number(current || 0), Number(session.sequence || 0)));
        writeStore({
          ...store,
          draft: {
            ...store.draft,
            lotCount: String(Math.max(sessionRows.length, Number(store.draft?.lotCount || 0), 1)),
            rows: mergeDraftRows(draftRows, sessionRows),
            isLive: true,
            liveName: session.liveName || store.draft?.liveName || '',
            serverSessionId: session.serverSessionId || null,
          },
          seq: Math.max(Number(store.seq || 0), Number(session.sequence || 0)),
        });
        setMessage(`Recovered active TikTok Go Live Session #${session.serverSessionId} from the server.`);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const sync = () => {
      const store = readStore();
      setLotCount(store.draft.lotCount || '200');
      const storeRows = Array.isArray(store.draft.rows) ? store.draft.rows : [];
      const storeIsLive = !!store.draft.isLive;
      setRows((currentRows) => {
        if (!storeIsLive) return storeRows;
        const currentScanned = countScannedRows(currentRows);
        const storeScanned = countScannedRows(storeRows);
        if (currentScanned > storeScanned || currentRows.length > storeRows.length) {
          return mergeDraftRows(storeRows, currentRows);
        }
        return storeRows;
      });
      setIsLive(!!store.draft.isLive);
      setLiveName(store.draft.liveName || '');
      setDetailsCsvText(store.draft.detailsCsvText || '');
      setDetailsCsvName(store.draft.detailsCsvName || '');
      setHistory(store.history || []);
      setLiveSequence(Number(store.seq || 0));
      setServerSessionId(store.draft.serverSessionId || null);
    };
    window.addEventListener(STORE_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(STORE_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  useEffect(() => {
    writeStore({
      draft: { lotCount, rows, isLive, liveName, detailsCsvText, detailsCsvName, serverSessionId },
      history,
      seq: liveSequence,
    });
  }, [lotCount, rows, isLive, liveName, detailsCsvText, detailsCsvName, serverSessionId, history, liveSequence]);

  const inventoryMap = useMemo(() => {
    const map = new Map();
    inventory.forEach((product) => {
      const barcode = normalizeCode(product.barcode);
      const sku = normalizeCode(product.default_code || product.sku);
      if (barcode) map.set(barcode, product);
      if (sku) map.set(sku, product);
    });
    return map;
  }, [inventory]);

  const productSearchRows = useMemo(() => (
    inventory
      .filter((product) => productBarcode(product))
      .map((product) => ({ product, searchText: productSearchText(product) }))
  ), [inventory]);

  function productSuggestions(query) {
    const q = String(query || '').trim().toLowerCase();
    if (q.length < 2 || !isProductNameSearch(q, inventoryMap)) return [];
    const terms = q.split(/\s+/).filter(Boolean);
    return productSearchRows
      .filter(({ searchText }) => terms.every((term) => searchText.includes(term)))
      .slice(0, 8)
      .map(({ product }) => product);
  }

  const matchedRows = useMemo(() => (
    rows.map((row) => ({
      ...row,
      match: inventoryMap.get(normalizeCode(row.barcode)) || null,
    }))
  ), [rows, inventoryMap]);

  const matchedCount = matchedRows.filter((row) => row.match).length;
  const unmappedCount = matchedRows.filter((row) => row.barcode && !row.match).length;
  const activeProductQuery = String(rows[Number(barcodeSearchRow)]?.barcode || '').trim();
  const showProductCatalog = isLive && isProductNameSearch(activeProductQuery, inventoryMap);
  const activeProductSuggestions = showProductCatalog ? productSuggestions(activeProductQuery) : [];

  async function handleDetailsFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      setDetailsCsvText(text);
      setDetailsCsvName(file.name);
      setPreview(null);
      setMessage(`${file.name} loaded.`);
    } catch (err) {
      setMessage(err.message || 'Could not read TikTok details CSV.');
    } finally {
      event.target.value = '';
    }
  }

  function startLive() {
    const total = Math.max(1, Number(lotCount || 0));
    setRows(buildRows(total));
    setIsLive(true);
    setDetailsCsvText('');
    setDetailsCsvName('');
    setServerSessionId(null);
    setPreview(null);
    setMessage(`Prepared ${total} lots. Start scanning barcodes into each row.`);
  }

  function endLive() {
    if (!rows.length) return;
    const nextSequence = Number(liveSequence || 0) + 1;
    const endedAt = new Date().toISOString();
    const archived = {
      id: `go-live-${nextSequence}-${Date.now()}`,
      sequence: nextSequence,
      liveName: liveName || '',
      endedAt,
      rows,
      lotCount,
      serverSessionId: serverSessionId || undefined,
    };
    setHistory((current) => [archived, ...current]);
    setLiveSequence(nextSequence);
    setIsLive(false);
    setRows([]);
    setDetailsCsvText('');
    setDetailsCsvName('');
    setServerSessionId(null);
    setPreview(null);
    setMessage(`${archiveLabel(archived)} moved to Live Auctions. Upload the TikTok lot-details CSV there.`);
  }

  function updateRow(index, key, value) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, [key]: value } : row)));
  }

  function focusNextBarcode(index) {
    const nextRef = barcodeRefs.current[index + 1];
    if (nextRef) {
      nextRef.focus();
      nextRef.select?.();
    }
  }

  function handleBarcodeCommit(index, rawValue) {
    const value = String(rawValue || '').replace(/[\r\n\t]+/g, '').trim();
    updateRow(index, 'barcode', value);
    if (value) {
      window.requestAnimationFrame(() => focusNextBarcode(index));
    }
  }

  function selectProductForLot(index, product) {
    const barcode = productBarcode(product);
    if (!barcode) return;
    setBarcodeSearchRow(null);
    handleBarcodeCommit(index, barcode);
  }

  async function runImport(commit) {
    if (!detailsCsvText.trim()) {
      setMessage('Upload the TikTok lot-details CSV first.');
      return;
    }
    setCsvBusy(true);
    setMessage('');
    try {
      const lotMapCsvText = rowsToLotMapCsv(rows, inventoryMap);
      const data = await postApi('/api/tiktok_live_orders/import_csv', {
        csv_text: detailsCsvText,
        lot_map_csv_text: lotMapCsvText,
        session_id: readStore().draft?.serverSessionId || null,
        commit,
      });
      setPreview(data);
      setMessage(commit
        ? `Imported ${data.summary.imported_rows} TikTok LIVE auction orders.`
        : `Preview ready: ${data.summary.ready_rows} ready, ${data.summary.duplicate_rows} duplicates, ${data.summary.unmatched_rows} unmatched.`);
    } catch (err) {
      setMessage(err.message || 'Could not process TikTok LIVE import.');
    } finally {
      setCsvBusy(false);
    }
  }

  const cols = [
    { label: 'Lot No' },
    { label: 'Barcode / SKU' },
    { label: 'Matching Product' },
    { label: 'On Hand', align: 'right' },
    { label: 'Retail', align: 'right' },
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <KpiCard label="Prepared Lots" value={rows.length || 0} />
        <KpiCard label="Matched Products" value={matchedCount} color="var(--accent-emerald)" />
        <KpiCard label="Needs Attention" value={unmappedCount} color={unmappedCount ? 'var(--accent-coral)' : 'var(--accent-amber)'} />
        <KpiCard label="Live Status" value={isLive ? 'LIVE' : 'Ready'} color={isLive ? 'var(--accent-emerald)' : 'var(--text-primary)'} />
        <KpiCard label="Ended Lives" value={history.length} />
      </div>

      <section className="company-panel">
        <div className="company-panel-head">
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, letterSpacing: '0.05em' }}>TikTok LIVE Prep</div>
        </div>
        <div className="company-panel-body" style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 180px auto auto', gap: 10, alignItems: 'end' }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Live name / note</span>
              <input value={liveName} onChange={(e) => setLiveName(e.target.value)} placeholder="Tonight's TikTok live" style={inputStyle} />
            </label>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>How many lots?</span>
              <input type="number" min="1" step="1" value={lotCount} onChange={(e) => setLotCount(e.target.value)} style={inputStyle} />
            </label>
            <PrimaryBtn onClick={startLive}>I'm Going Live</PrimaryBtn>
            <GhostBtn onClick={endLive} disabled={!rows.length}>Live Ends</GhostBtn>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Click <strong>I'm Going Live</strong>, generate your lots, then scan each sold product barcode into the matching lot row. When the live ends, upload the TikTok lot-details CSV and we'll match it against your prepared lot sheet.
          </div>
          {message ? <div style={{ fontSize: 13, color: message.toLowerCase().includes('could not') || message.toLowerCase().includes('upload') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{message}</div> : null}
        </div>
      </section>

      <section className="company-panel">
        <div className="company-panel-head">
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, letterSpacing: '0.05em' }}>Lot Sheet</div>
        </div>
        <div className="company-panel-body" style={{ display: 'grid', gridTemplateColumns: showProductCatalog ? 'minmax(0, 1fr) minmax(420px, 460px)' : 'minmax(0, 1fr)', gap: 12, alignItems: 'start' }}>
          <TableShell footer={`${matchedRows.length} lots prepared`}>
            <Thead cols={cols} />
            <tbody>
              {(!matchedRows.length || loading) ? <EmptyRow cols={cols.length} loading={loading} msg={'Click "I\'m Going Live" to generate your lot sheet.'} /> : null}
              {!loading && matchedRows.map((row, index) => {
                return (
                <tr key={`${row.lotNo}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={tdStrong}>
                    <input value={row.lotNo} onChange={(e) => updateRow(index, 'lotNo', e.target.value)} style={{ ...inputStyle, maxWidth: 100 }} />
                  </td>
                  <td style={td}>
                    <input
                      ref={(node) => {
                        if (node) barcodeRefs.current[index] = node;
                        else delete barcodeRefs.current[index];
                      }}
                      value={row.barcode}
                      autoComplete="off"
                      onChange={(e) => {
                        const nextValue = e.target.value;
                        if (/[\r\n]/.test(nextValue)) {
                          handleBarcodeCommit(index, nextValue);
                          return;
                        }
                        updateRow(index, 'barcode', nextValue);
                        setBarcodeSearchRow(isProductNameSearch(nextValue, inventoryMap) ? index : null);
                      }}
                      onFocus={(e) => {
                        if (isProductNameSearch(e.target.value, inventoryMap)) setBarcodeSearchRow(index);
                      }}
                      onBlur={(e) => {
                        window.setTimeout(() => setBarcodeSearchRow((current) => (current === index ? null : current)), 120);
                        if (e.target.value && !isProductNameSearch(e.target.value, inventoryMap)) handleBarcodeCommit(index, e.target.value);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Escape') setBarcodeSearchRow(null);
                        if (e.key === 'Enter' || e.key === 'Tab') {
                          const suggestions = productSuggestions(e.currentTarget.value);
                          if (isProductNameSearch(e.currentTarget.value, inventoryMap) && suggestions[0]) {
                            e.preventDefault();
                            selectProductForLot(index, suggestions[0]);
                            return;
                          }
                          handleBarcodeCommit(index, e.currentTarget.value);
                        }
                      }}
                      placeholder="Scan barcode or type product name"
                      style={inputStyle}
                    />
                  </td>
                  <td style={td}>
                    {row.match ? (
                      <div style={{ display: 'grid', gap: 4 }}>
                        <strong title={row.match.name} style={{ color: 'var(--text-primary)' }}>{compactLiveProductName(row.match.name)}</strong>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{row.match.barcode || row.match.default_code || 'No code'}</div>
                      </div>
                    ) : row.productName ? (
                      <div style={{ display: 'grid', gap: 4 }}>
                        <strong title={row.productName} style={{ color: 'var(--text-primary)' }}>{compactLiveProductName(row.productName)}</strong>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                          {row.itemCount > 1 ? `${row.itemCount} products in this lot` : 'Saved lot item'}
                        </div>
                        {row.barcode ? (
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                            {row.barcode}
                          </div>
                        ) : null}
                      </div>
                    ) : row.barcode ? (
                      <Badge custom={{ label: 'No match', bg: 'rgba(239,68,68,0.14)', color: '#dc2626' }} />
                    ) : (
                      <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>Waiting for scan</span>
                    )}
                  </td>
                  <td style={tdRight}>{row.match ? Number(row.match.on_hand_qty ?? row.match.qty_available ?? 0).toLocaleString() : '—'}</td>
                  <td style={tdRight}>{row.match ? fmt(row.match.retail_price) : '—'}</td>
                </tr>
                );
              })}
            </tbody>
          </TableShell>
          {showProductCatalog ? (
            <aside style={{ position: 'sticky', top: 8, maxHeight: 520, overflowY: 'auto', borderRadius: 14, border: '1px solid rgba(249,115,22,0.28)', background: '#fff', boxShadow: '0 18px 42px rgba(15,23,42,0.12)' }}>
              <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(226,232,240,0.95)', background: 'rgba(255,247,237,0.78)' }}>
                <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#c2410c' }}>Product Catalog</div>
                <div style={{ marginTop: 3, fontSize: 13, fontWeight: 900, color: '#0f172a' }}>Lot {rows[Number(barcodeSearchRow)]?.lotNo || Number(barcodeSearchRow) + 1}</div>
                <div style={{ marginTop: 2, fontSize: 12, color: '#64748b' }}>Search: {activeProductQuery}</div>
              </div>
              <div style={{ display: 'grid', gap: 6, padding: 8 }}>
                {activeProductSuggestions.length ? activeProductSuggestions.map((product) => (
                  <button
                    key={`${product.id || productBarcode(product)}-${productBarcode(product)}`}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      selectProductForLot(Number(barcodeSearchRow), product);
                    }}
                    style={{ display: 'grid', gap: 5, width: '100%', padding: '11px 12px', border: '1px solid rgba(226,232,240,0.95)', borderRadius: 10, background: '#fff', color: '#0f172a', textAlign: 'left', cursor: 'pointer' }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 900, lineHeight: 1.35, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>{product.name}</span>
                    <span style={{ fontSize: 11, color: '#64748b', fontFamily: 'var(--font-mono)' }}>{productBarcode(product)}</span>
                    <span style={{ fontSize: 11, color: '#475569' }}>
                      {product.brand || 'No brand'} · Stock {Number(product.on_hand_qty ?? product.qty_available ?? 0).toLocaleString()} · Cost {fmt(product.cost_price)}
                    </span>
                  </button>
                )) : (
                  <div style={{ padding: 16, color: '#64748b', fontSize: 13 }}>No matching products found.</div>
                )}
              </div>
            </aside>
          ) : null}
        </div>
      </section>

      {!isLive && rows.length ? (
        <section className="company-panel">
          <div className="company-panel-head">
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, letterSpacing: '0.05em' }}>After Live Import</div>
          </div>
          <div className="company-panel-body" style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              Upload the TikTok CSV that contains lot number, product name, buyer, price won, and other live-auction details. We'll match it against the lot sheet you just prepared.
            </div>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 10, alignSelf: 'flex-start', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', padding: '10px 12px', background: 'var(--bg-panel)', cursor: 'pointer', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
              <input type="file" accept=".csv,text/csv" onChange={handleDetailsFile} style={{ display: 'none' }} />
              <span>Choose TikTok Lot Details CSV</span>
            </label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {detailsCsvName ? `Loaded details file: ${detailsCsvName}` : 'No TikTok lot-details CSV selected yet.'}
            </div>
            <textarea
              value={detailsCsvText}
              onChange={(e) => setDetailsCsvText(e.target.value)}
              rows={8}
              placeholder="TikTok lot-details CSV contents will appear here after upload. You can also paste the file manually if needed."
              style={{ ...inputStyle, minHeight: 180, resize: 'vertical', fontFamily: 'var(--font-mono)' }}
            />
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <PrimaryBtn onClick={() => runImport(false)} disabled={csvBusy}>{csvBusy ? 'Working…' : 'Preview Import'}</PrimaryBtn>
              <PrimaryBtn onClick={() => runImport(true)} disabled={csvBusy}>{csvBusy ? 'Working…' : 'Import Live Results'}</PrimaryBtn>
            </div>

            {preview ? (
              <div style={{ display: 'grid', gap: 10 }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Badge custom={{ label: `${preview.summary.total_rows} rows`, bg: 'var(--bg-elevated)', color: 'var(--text-secondary)' }} />
                  <Badge custom={{ label: `${preview.summary.ready_rows} ready`, bg: 'rgba(16,185,129,0.16)', color: '#059669' }} />
                  <Badge custom={{ label: `${preview.summary.duplicate_rows} duplicates`, bg: 'rgba(245,158,11,0.16)', color: '#d97706' }} />
                  <Badge custom={{ label: `${preview.summary.unmatched_rows} unmatched`, bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }} />
                </div>
                <TableShell footer={`${preview.rows.length} TikTok live rows preview`}>
                  <Thead cols={[
                    { label: 'Status' },
                    { label: 'Lot No' },
                    { label: 'Buyer' },
                    { label: 'TikTok Product' },
                    { label: 'Matched Inventory' },
                    { label: 'Price', align: 'right' },
                  ]} />
                  <tbody>
                    {preview.rows.slice(0, 80).map((row) => (
                      <tr key={`${row.row_number}-${row.external_order_ref || row.lot_number || row.product_name}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={td}><Badge custom={row.status === 'ready'
                          ? { label: 'Ready', bg: 'rgba(16,185,129,0.16)', color: '#059669' }
                          : row.status === 'duplicate'
                            ? { label: 'Duplicate', bg: 'rgba(245,158,11,0.16)', color: '#d97706' }
                            : { label: 'Unmatched', bg: 'rgba(239,68,68,0.16)', color: '#dc2626' }} /></td>
                        <td style={tdMono}>{row.lot_number || '—'}</td>
                        <td style={td}>{row.buyer_username || '—'}</td>
                        <td style={td}>
                          <div style={{ fontWeight: row.original_product_name ? 800 : 600 }}>{row.product_name || '—'}</div>
                          {row.original_product_name ? (
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 3 }}>
                              TikTok label: {row.original_product_name}
                            </div>
                          ) : null}
                        </td>
                        <td style={td}>
                          {row.matched_inventory_name || '—'}
                          {row.lot_map_barcode ? (
                            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 3 }}>
                              Lot map barcode: {row.lot_map_barcode}
                            </div>
                          ) : null}
                        </td>
                        <td style={tdRight}>{fmt(row.subtotal || row.unit_price)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}

const td = { padding: '8px 14px' };
const tdStrong = { ...td, fontWeight: 800 };
const tdMono = { ...td, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' };
const tdRight = { ...td, textAlign: 'right' };
