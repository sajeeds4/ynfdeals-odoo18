import { useEffect, useMemo, useRef, useState } from 'react';
import { clearCachedApiPrefix, fetchApi, getCachedApi, postApi, setCachedApi } from '../../hooks/useApi';
import { useLocalState, useSessionState } from '../../hooks/useBrowserState';
import {
  EmptyRow,
  FullPageForm,
  GhostBtn,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  SlidePanel,
  SortTh,
  TableShell,
} from './utils';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Card, CardContent } from '../../components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '../../components/ui/tabs';

const fmt = (n) => (n == null ? '—' : `$${Number(n).toFixed(2)}`);
const fmtQty = (n) => (n == null ? '—' : Number(n).toLocaleString());
const fmtPct = (n) => (n == null ? '—' : `${Number(n).toFixed(1)}%`);
const INVENTORY_PAGE_SIZE = 120;
const hasNumericValue = (value) => value !== '' && value != null && Number.isFinite(Number(value));
const numericOrNull = (value) => (hasNumericValue(value) ? Number(value) : null);
const positivePriceOrNull = (value) => {
  const number = numericOrNull(value);
  return number != null && number > 0 ? number : null;
};
const pricingLadder = (row) => {
  const cost = positivePriceOrNull(row?.standard_price ?? row?.cost_price);
  const raw = numericOrNull(row?.raw_cost) ?? cost;
  const plus12 = numericOrNull(row?.cost_plus_12);
  const plus20 = numericOrNull(row?.cost_plus_20);
  return {
    raw,
    plus12: plus12 ?? (raw != null ? raw * 1.12 : null),
    plus20: plus20 ?? (raw != null ? raw * 1.2 : null),
  };
};
const cleanName = (name) => (name || '').replace(/^\[[^\]]+\]\s*/, '');
const DESCRIPTION_FIELD_PREFIXES = ['Product Name', 'Description', 'Top Notes', 'Middle Notes', 'Base Notes', 'Size', 'Gender'];
const panelSignature = (mode, productId) => {
  const normalizedMode = String(mode || '').trim();
  const normalizedId = Number(productId || 0);
  return normalizedMode && normalizedId ? `${normalizedMode}:${normalizedId}` : '';
};
const compactSku = (value, keepStart = 24, keepEnd = 8) => {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.length <= keepStart + keepEnd + 3) return text;
  return `${text.slice(0, keepStart)}...${text.slice(-keepEnd)}`;
};
const friendlyInventoryName = (rowOrName) => {
  const row = typeof rowOrName === 'object' && rowOrName !== null ? rowOrName : {};
  const brand = String(row.brand || '').trim();
  let name = cleanName(typeof rowOrName === 'string' ? rowOrName : row.name);

  if (brand) {
    const escapedBrand = brand.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '[\\s-]+');
    name = name
      .replace(new RegExp(`^\\s*${escapedBrand}\\s*[-:·]?\\s*`, 'i'), '')
      .replace(new RegExp(`\\s+by\\s+${escapedBrand}\\b`, 'ig'), '')
      .replace(new RegExp(`\\b${escapedBrand}\\b`, 'ig'), '');
  }

  return name
    .replace(/\bAl[\s-]?Rehab\b/ig, '')
    .replace(/\bEau\s+de\s+(Natural\s+)?Parfum\s+Spray\b/ig, '')
    .replace(/\bEau\s+de\s+Parfum\b/ig, '')
    .replace(/\bEDP\s+Spray\b/ig, '')
    .replace(/\bEDP\b/ig, '')
    .replace(/\bFragrances?\b/ig, '')
    .replace(/\bUPC\s*Code\b/ig, '')
    .replace(/[[({]?\s*\d{12,14}\s*[\])}]?/g, '')
    .replace(/\s*[{}]\s*/g, ' ')
    .replace(/\s+,\s+/g, ', ')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+([,)])/g, '$1')
    .replace(/^\s*[-:·,]\s*|\s*[-:·,]\s*$/g, '')
    .trim() || cleanName(typeof rowOrName === 'string' ? rowOrName : row.name);
};
const exactInventoryName = (rowOrName) => {
  if (typeof rowOrName === 'string') return String(rowOrName || '').trim();
  const row = rowOrName && typeof rowOrName === 'object' ? rowOrName : {};
  return String(row.name || row.tiktok_title || '').trim();
};
const editableInventoryName = (row) => {
  const raw = String(row?.name || '').trim();
  const tiktokTitle = String(row?.tiktok_title || '').trim();
  if (tiktokTitle) return tiktokTitle;
  return raw;
};
const generateSkuFromName = (name) => {
  const normalized = friendlyInventoryName(String(name || ''))
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, ' ')
    .trim();
  if (!normalized) return 'PRODUCT';
  const stopWords = new Set(['EAU', 'DE', 'PARFUM', 'SPRAY', 'PERFUME', 'OIL', 'FOR', 'MEN', 'WOMEN', 'UNISEX', 'FL', 'OZ', 'EDP']);
  const tokens = normalized.split(/\s+/).filter(Boolean);
  const sizeTokens = [];
  const keywordTokens = [];
  tokens.forEach((token, index) => {
    if (/^\d+(?:\.\d+)?$/.test(token) && tokens[index + 1] && /^(ML|OZ)$/.test(tokens[index + 1])) {
      sizeTokens.push(`${token}${tokens[index + 1]}`);
      return;
    }
    if (/^\d+(?:ML|OZ)$/.test(token)) {
      sizeTokens.push(token);
      return;
    }
    if (!stopWords.has(token)) keywordTokens.push(token);
  });
  const base = keywordTokens.slice(0, 3).map((token) => token.slice(0, 4)).join('-');
  const size = sizeTokens[0] || '';
  return [base || normalized.split(/\s+/).slice(0, 2).map((token) => token.slice(0, 4)).join('-'), size]
    .filter(Boolean)
    .join('-')
    .slice(0, 24);
};

const inventoryDetailStyles = `
@keyframes inventoryFloatIn {
  from { opacity: 0; transform: translateY(10px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.inventory-detail-shell{
  position:relative;
  background:
    radial-gradient(circle at top right, rgba(108,71,255,0.10), transparent 26%),
    linear-gradient(180deg, #faf7ff 0%, #f7f8fc 100%);
}
.inventory-detail-shell::before{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(180deg, rgba(255,255,255,0.64), transparent 24%);
}
.inventory-detail-hero,
.inventory-detail-card,
.inventory-detail-kpi,
.inventory-detail-sidecard{
  position:relative;
  overflow:hidden;
  background:rgba(255,255,255,0.92);
  border:1px solid rgba(226, 218, 255, 0.92);
  box-shadow:0 18px 42px rgba(29, 26, 36, 0.06), inset 0 1px 0 rgba(255,255,255,0.92);
}
.inventory-detail-hero::after,
.inventory-detail-card::after,
.inventory-detail-kpi::after,
.inventory-detail-sidecard::after{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(180deg, rgba(255,255,255,0.58), transparent 26%);
}
.inventory-detail-kpi,
.inventory-detail-card,
.inventory-detail-thumb,
.inventory-detail-pedestal{
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.inventory-detail-kpi:hover,
.inventory-detail-card:hover,
.inventory-detail-sidecard:hover{
  transform:translateY(-2px);
  box-shadow:0 24px 44px rgba(108,71,255,0.10), inset 0 1px 0 rgba(255,255,255,0.92);
}
.inventory-detail-pedestal{
  position:relative;
  transform-style:preserve-3d;
}
.inventory-detail-pedestal::before{
  content:"";
  position:absolute;
  left:12%;
  right:12%;
  bottom:18px;
  height:22px;
  border-radius:999px;
  background:radial-gradient(circle, rgba(108,71,255,0.22), rgba(108,71,255,0.02) 70%);
  filter:blur(10px);
}
.inventory-detail-pedestal::after{
  content:"";
  position:absolute;
  left:16%;
  right:16%;
  bottom:0;
  height:38px;
  border-radius:18px;
  background:linear-gradient(180deg, #f8f2ff 0%, #ece6f8 100%);
  border:1px solid rgba(226, 218, 255, 0.92);
  box-shadow:0 10px 20px rgba(29, 26, 36, 0.06);
}
.inventory-detail-product{
  position:relative;
  z-index:2;
  transform:translateY(-2px);
  filter:drop-shadow(0 16px 20px rgba(29,26,36,0.10));
}
.inventory-detail-thumb:hover{
  transform:translateY(-2px);
  box-shadow:0 12px 22px rgba(108,71,255,0.10);
}
.inventory-detail-modal{
  animation:inventoryFloatIn .18s ease-out;
}
.inventory-editor-shell{
  position:relative;
  background:
    radial-gradient(circle at top right, rgba(79,70,229,0.12), transparent 24%),
    radial-gradient(circle at top left, rgba(139,92,246,0.08), transparent 20%),
    linear-gradient(180deg, #f7f8fc 0%, #f4f6fb 100%);
}
.inventory-editor-shell::before{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(180deg, rgba(255,255,255,0.6), transparent 22%);
}
.inventory-editor-hero,
.inventory-editor-panel,
.inventory-editor-rail-card,
.inventory-editor-kpi{
  position:relative;
  overflow:hidden;
  background:rgba(255,255,255,0.93);
  border:1px solid rgba(226, 232, 240, 0.9);
  box-shadow:0 16px 34px rgba(79,70,229,0.08), inset 0 1px 0 rgba(255,255,255,0.9);
}
.inventory-editor-hero::after,
.inventory-editor-panel::after,
.inventory-editor-rail-card::after,
.inventory-editor-kpi::after{
  content:"";
  position:absolute;
  inset:0;
  pointer-events:none;
  background:linear-gradient(180deg, rgba(255,255,255,0.56), transparent 24%);
}
.inventory-editor-kpi,
.inventory-editor-panel,
.inventory-editor-rail-card,
.inventory-editor-media-card,
.inventory-editor-glass-chip{
  transition:transform .16s ease, box-shadow .16s ease, border-color .16s ease;
}
.inventory-editor-kpi:hover,
.inventory-editor-panel:hover,
.inventory-editor-rail-card:hover{
  transform:translateY(-2px);
  box-shadow:0 22px 40px rgba(79,70,229,0.12), inset 0 1px 0 rgba(255,255,255,0.9);
}
.inventory-editor-pedestal{
  position:relative;
  min-height:116px;
}
.inventory-editor-pedestal::before{
  content:"";
  position:absolute;
  left:16%;
  right:16%;
  bottom:18px;
  height:18px;
  border-radius:999px;
  background:radial-gradient(circle, rgba(79,70,229,0.24), rgba(79,70,229,0.04) 72%);
  filter:blur(10px);
}
.inventory-editor-pedestal::after{
  content:"";
  position:absolute;
  left:12%;
  right:12%;
  bottom:0;
  height:34px;
  border-radius:18px;
  background:linear-gradient(180deg, #f5f3ff 0%, #e9e6fb 100%);
  border:1px solid rgba(196,181,253,0.65);
}
.inventory-editor-product{
  position:relative;
  z-index:2;
  filter:drop-shadow(0 14px 18px rgba(15,23,42,0.12));
}
.inventory-editor-glass-chip{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid rgba(196,181,253,0.42);
  background:rgba(238,242,255,0.78);
  backdrop-filter:blur(10px);
  color:#4338ca;
  font-size:11px;
  font-weight:800;
}
.inventory-editor-grid{
  display:grid;
  grid-template-columns:minmax(0, 1.75fr) 340px;
  gap:16px;
  min-height:0;
  flex:1;
}
@media (max-width: 1200px){
  .inventory-editor-grid{
    grid-template-columns:minmax(0, 1fr);
  }
}
.inventory-editor-field-grid{
  display:grid;
  grid-template-columns:repeat(6, minmax(100px, 1fr));
  gap:10px;
  align-items:end;
}
@media (max-width: 1400px){
  .inventory-editor-field-grid{
    grid-template-columns:repeat(3, minmax(0, 1fr));
  }
}
.inventory-editor-field-grid-compact{
  display:grid;
  grid-template-columns:repeat(4, minmax(120px, 1fr));
  gap:10px;
  align-items:end;
}
@media (max-width: 1400px){
  .inventory-editor-field-grid-compact{
    grid-template-columns:repeat(2, minmax(0, 1fr));
  }
}
`;
if (typeof document !== 'undefined' && !document.getElementById('inventory-detail-style')) {
  const styleEl = document.createElement('style');
  styleEl.id = 'inventory-detail-style';
  styleEl.textContent = inventoryDetailStyles;
  document.head.appendChild(styleEl);
}
const normalizeName = (name) => cleanName(name).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const extractDescriptionBody = (text) => {
  const raw = String(text || '').trim();
  if (!raw) return '';
  const lines = raw.split(/\r?\n/);
  const bodyLines = [];
  let inDescription = false;
  lines.forEach((line) => {
    const trimmed = String(line || '').trim();
    if (!trimmed) {
      if (inDescription) bodyLines.push('');
      return;
    }
    const matchedPrefix = DESCRIPTION_FIELD_PREFIXES.find((prefix) => new RegExp(`^${prefix}\\s*:`, 'i').test(trimmed));
    if (matchedPrefix) {
      if (/^Description\s*:/i.test(trimmed)) {
        inDescription = true;
        const value = trimmed.replace(/^Description\s*:\s*/i, '').trim();
        if (value) bodyLines.push(value);
      } else {
        inDescription = false;
      }
      return;
    }
    if (inDescription) bodyLines.push(trimmed);
  });
  return bodyLines.join('\n').trim() || raw;
};
const deriveProductSize = ({ name, tiktok_volume }) => {
  const explicitVolume = String(tiktok_volume || '').trim();
  if (explicitVolume) return explicitVolume;
  const sourceName = String(name || '').trim();
  if (!sourceName) return '';
  const parenMatch = sourceName.match(/\(([^)]+)\)/);
  if (parenMatch?.[1]) return parenMatch[1].trim();
  const sizeMatches = sourceName.match(/\d+(?:\.\d+)?\s*(?:ml|oz|fl oz)/gi);
  return sizeMatches?.join(' / ') || '';
};
const formatSeparateSize = ({ sizeOz, sizeMl, tiktokVolume, name }) => {
  const parts = [];
  if (hasNumericValue(sizeOz)) parts.push(`${Number(sizeOz)} oz`);
  if (hasNumericValue(sizeMl)) parts.push(`${Number(sizeMl)} mL`);
  if (parts.length) return parts.join(' / ');
  return deriveProductSize({ name, tiktok_volume: tiktokVolume });
};
const normalizeGenderValue = (value) => {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return '';
  if (raw === 'men' || raw === 'male') return 'Male';
  if (raw === 'women' || raw === 'female') return 'Female';
  if (raw === 'unisex') return 'Unisex';
  if (raw === 'boys') return 'Boys';
  if (raw === 'girls') return 'Girls';
  return String(value || '').trim();
};
const deriveTikTokFragranceCategory = (gender) => {
  const normalized = normalizeGenderValue(gender);
  if (normalized === 'Male') return "Beauty & Personal Care - Fragrance - Men's Fragrance";
  if (normalized === 'Female') return "Beauty & Personal Care - Fragrance - Women's Fragrance";
  return 'Beauty & Personal Care - Fragrance - Unisex Fragrance';
};
const parseSizeOrVolumePair = ({ sizeOz, sizeMl, volumeOz, volumeMl, tiktokVolume, name }) => {
  const pickNumber = (value) => (hasNumericValue(value) ? Number(value) : null);
  let oz = pickNumber(volumeOz) ?? pickNumber(sizeOz);
  let ml = pickNumber(volumeMl) ?? pickNumber(sizeMl);
  const source = String(tiktokVolume || name || '').trim();
  if (source) {
    if (ml == null) {
      const mlMatch = source.match(/(\d+(?:\.\d+)?)\s*m(?:l|L)\b/i);
      if (mlMatch?.[1]) ml = Number(mlMatch[1]);
    }
    if (oz == null) {
      const ozMatch = source.match(/(\d+(?:\.\d+)?)\s*(?:fl\s*)?oz\b/i);
      if (ozMatch?.[1]) oz = Number(ozMatch[1]);
    }
  }
  return { oz, ml };
};
const parseGalleryUrls = (value) => {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  const raw = String(value || '').trim();
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(Boolean).map(String) : [];
  } catch {
    return [];
  }
};
const sdsPreviewUrl = (path) => {
  const raw = String(path || '').trim();
  if (!raw) return '';
  if (raw.startsWith('/product-uploads/')) return raw;
  const marker = '/product_uploads/';
  const index = raw.indexOf(marker);
  if (index >= 0) {
    return raw.slice(index).replace('/product_uploads/', '/product-uploads/');
  }
  return '';
};
const buildStructuredProductDescription = ({
  productName,
  descriptionBody,
  noteTop,
  noteMid,
  noteBase,
  size,
  gender,
}) => {
  const title = String(productName || '').trim() || '—';
  const body = String(descriptionBody || '').trim() || '—';
  return [
    title,
    '',
    body,
    `Top Notes: ${String(noteTop || '').trim() || '—'}`,
    `Middle Notes: ${String(noteMid || '').trim() || '—'}`,
    `Base Notes: ${String(noteBase || '').trim() || '—'}`,
    `Size: ${String(size || '').trim() || '—'}`,
    `Gender: ${String(gender || '').trim() || '—'}`,
  ].join('\n');
};
const LIVE_ATTENTION_QTY = 3;
const DEFAULT_EXPORT_FIELDS = [
  'id',
  'name',
  'default_code',
  'barcode',
  'brand',
  'gender',
  'categ_name',
  'supplier_name',
  'type',
  'active',
  'qty_available',
  'low_stock_threshold',
  'low_stock',
  'standard_price',
  'raw_cost',
  'cost_plus_12',
  'cost_plus_20',
  'list_price',
  'stock_value',
  'storage_bin',
  'note_top',
  'note_mid',
  'note_base',
  'dupe_inspiration',
  'notes',
  'image_url',
];

const TIKTOK_FIELD_DEFAULTS = {
  tiktok_title: '',
  tiktok_category_id: '',
  tiktok_category_name: 'Beauty & Personal Care - Fragrance - Unisex Fragrance',
  tiktok_brand: '',
  tiktok_search_keywords: '',
  tiktok_image_urls: '',
  tiktok_pack_type: 'Single Item',
  tiktok_scent: '',
  tiktok_region_of_origin: 'United Arab Emirates',
  tiktok_product_form: 'Eau De Parfum',
  tiktok_edition: 'Regular',
  tiktok_contains_alcohol_or_aerosol: 'Contains Alcohol',
  tiktok_manufacturer: '',
  tiktok_shelf_life: '36 Months',
  tiktok_inactive_ingredients: '',
  tiktok_age_group: 'Adults',
  tiktok_item_name: '',
  tiktok_feature: '',
  tiktok_fragrance_concentration: 'Eau De Parfum',
  tiktok_material_type_free: '',
  tiktok_ingredients: '',
  tiktok_container_type: 'Spray',
  tiktok_allergen_information: '',
  tiktok_ingredient_feature: '',
  tiktok_volume: '',
  tiktok_description: '',
  tiktok_highlights: '',
  tiktok_quantity: '',
  tiktok_retail_price: '',
  tiktok_seller_sku: '',
  tiktok_ean: '',
  tiktok_product_identifier_code_type: 'EAN',
  tiktok_ca_prop_65_repro_chems: 'No',
  tiktok_ca_prop_65_carcinogens: 'No',
  tiktok_flammable_liquid: 'No',
  tiktok_aerosols: 'No',
  tiktok_dangerous_goods_or_hazardous_materials: 'Yes',
  tiktok_environmental_feature: '',
  tiktok_sds_file_path: '',
  tiktok_package_weight_oz: '',
};

const TIKTOK_FIELD_NAMES = Object.keys(TIKTOK_FIELD_DEFAULTS);
const TIKTOK_NUMERIC_FIELDS = new Set([
  'tiktok_quantity',
  'tiktok_retail_price',
  'tiktok_package_weight_oz',
]);

const TIKTOK_KEY_ATTRIBUTES = [
  ['tiktok_pack_type', 'Pack Type'],
  ['tiktok_scent', 'Scent'],
  ['tiktok_region_of_origin', 'Region Of Origin'],
];

  const TIKTOK_OPTIONAL_ATTRIBUTES = [
  ['tiktok_product_form', 'Product Form'],
  ['tiktok_edition', 'Edition'],
  ['tiktok_contains_alcohol_or_aerosol', 'Contains Alcohol Or Aerosol'],
  ['tiktok_manufacturer', 'Manufacturer'],
  ['tiktok_shelf_life', 'Shelf Life'],
  ['tiktok_inactive_ingredients', '(Inactive) Ingredients'],
  ['tiktok_age_group', 'Age Group'],
  ['tiktok_feature', 'Feature'],
  ['tiktok_fragrance_concentration', 'Fragrance Concentration'],
  ['tiktok_material_type_free', 'Material Type Free'],
  ['tiktok_ingredients', 'Ingredients'],
  ['tiktok_container_type', 'Container Type'],
  ['tiktok_allergen_information', 'Allergen Information'],
];

const TIKTOK_COMPLIANCE_FIELDS = [
  ['tiktok_ca_prop_65_repro_chems', 'CA Prop 65: Repro. Chems'],
  ['tiktok_ca_prop_65_carcinogens', 'CA Prop 65: Carcinogens'],
  ['tiktok_flammable_liquid', 'Flammable Liquid'],
  ['tiktok_aerosols', 'Aerosols'],
  ['tiktok_dangerous_goods_or_hazardous_materials', 'Dangerous Goods Or Hazardous Materials'],
];

function prettifyFieldName(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function formatAuditValue(value) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (Array.isArray(value)) return value.join(', ') || '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function csvEscape(value) {
  if (value == null) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function typeMeta(type) {
  if (type === 'product' || type === 'storable') return { label: 'Storable', color: '#fbbf24' };
  if (type === 'consu') return { label: 'Consumable', color: 'var(--accent-emerald)' };
  if (type === 'service') return { label: 'Service', color: 'var(--text-secondary)' };
  return { label: type || '—', color: 'var(--text-secondary)' };
}

function stockAttentionMeta(qty) {
  const value = Number(qty ?? 0);
  if (value <= 0) {
    return {
      color: 'var(--accent-coral)',
      bg: 'rgba(239,68,68,0.14)',
      border: '1px solid rgba(239,68,68,0.32)',
      label: 'Out',
    };
  }
  if (value <= LIVE_ATTENTION_QTY) {
    return {
      color: 'var(--accent-coral)',
      bg: 'rgba(239,68,68,0.10)',
      border: '1px solid rgba(239,68,68,0.22)',
      label: 'Attention',
    };
  }
  return {
    color: 'var(--text-primary)',
    bg: 'transparent',
    border: '1px solid transparent',
    label: '',
  };
}

// ─── Product Detail (full-page with tabs) ───────────────────────────────────

function ProductDetailPanel({ product, onClose, onEdit, onArchive, onAdjust, showCostUplifts = false }) {
  const [data, setData] = useState(null);
  const [auditRows, setAuditRows] = useState([]);
  const [tab, setTab] = useState('overview');

  useEffect(() => {
    Promise.all([
      fetchApi(`/api/inventory/product_detail?product_id=${product.id}`),
      fetchApi(`/api/inventory/audit?product_id=${product.id}&limit=40`).catch(() => ({ rows: [] })),
    ])
      .then(([detailResult, auditResult]) => {
        setData(detailResult);
        setAuditRows(auditResult.rows || []);
      })
      .catch(() => {
        setData({ product, movements: [], sales: [], sales_summary: { times_sold: 0, total_revenue: 0, total_profit: 0 } });
        setAuditRows([]);
      });
  }, [product]);

  const detail = data?.product || product;
  const detailVolumes = parseSizeOrVolumePair({
    sizeOz: detail?.size_oz,
    sizeMl: detail?.size_ml,
    volumeOz: detail?.volume_oz,
    volumeMl: detail?.volume_ml,
    tiktokVolume: detail?.tiktok_volume,
    name: detail?.name,
  });
  const movements = data?.movements || [];
  const sales = data?.sales || [];
  const summary = data?.sales_summary || { times_sold: 0, total_revenue: 0, total_profit: 0 };
  const type = typeMeta(detail.type || detail.product_type);
  const onHandQty = Number(detail.qty_available ?? detail.on_hand_qty ?? 0);
  const galleryUrls = parseGalleryUrls(detail.image_gallery_urls);
  const primaryImage = detail.image_url || galleryUrls[0] || '';
  const heroGallery = Array.from(new Set([primaryImage, ...galleryUrls].filter(Boolean))).slice(0, 5);
  const marginPct = Number(detail.list_price || detail.retail_price || 0) > 0
    ? (((Number(detail.list_price || detail.retail_price || 0) - Number(detail.standard_price || detail.cost_price || 0)) / Number(detail.list_price || detail.retail_price || 1)) * 100)
    : null;
  const avgSalePrice = summary.times_sold > 0 ? summary.total_revenue / summary.times_sold : null;

  const TABS = [
    { id: 'overview', label: 'Overview' },
    { id: 'pricing', label: 'Pricing' },
    { id: 'inventory', label: 'Inventory' },
    { id: 'notes', label: 'Notes' },
    { id: 'sales', label: `Sales history` },
    { id: 'moves', label: `Stock moves` },
    { id: 'audit', label: `Audit` },
  ];

  return (
    <FullPageForm
      fullWidth
      onClose={onClose}
      actions={<Button onClick={() => onEdit(detail)}>Edit product</Button>}
    >
      {!data || String(data.product?.id) !== String(product.id) ? (
        <div className="py-16 text-center text-sm text-slate-500">Loading product…</div>
      ) : (
        <div className="inventory-detail-shell flex h-full flex-col overflow-hidden text-slate-950">
          <div className="border-b border-slate-200/80 px-6 py-5">
            <div className="inventory-detail-hero rounded-[24px] px-5 py-5 md:px-6">
              <div className="grid items-start gap-6 xl:grid-cols-[260px_minmax(0,1fr)_auto]">
                <div className="grid gap-3">
                  <div className="inventory-detail-pedestal grid min-h-[220px] place-items-center rounded-[24px] border border-violet-100/90 bg-[linear-gradient(180deg,#fff_0%,#f6efff_100%)] px-4 pt-6 pb-12">
                    {primaryImage
                      ? <img src={primaryImage} alt="" className="inventory-detail-product max-h-[176px] max-w-full object-contain" />
                      : <span className="relative z-[2] text-xs font-medium text-slate-400">No image</span>}
                  </div>
                  {heroGallery.length ? (
                    <div className="flex gap-2 overflow-x-auto pb-1">
                      {heroGallery.map((url, index) => (
                        <a
                          key={`${url}-${index}`}
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          className="inventory-detail-thumb block shrink-0 rounded-2xl border border-violet-100/90 bg-white p-1.5"
                          title={`Open image ${index + 1}`}
                        >
                          <img src={url} alt={`Product image ${index + 1}`} className="h-14 w-14 rounded-xl object-contain" />
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="min-w-0">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <Badge tone={detail.active === false ? 'default' : 'success'}>{detail.active === false ? 'Inactive' : 'Active'}</Badge>
                    {detail.low_stock ? <Badge tone="danger">Low stock</Badge> : null}
                    <Badge>{type.label}</Badge>
                  </div>
                  <h2 className="text-balance text-[2rem] font-semibold tracking-[-0.04em] text-slate-950">{exactInventoryName(detail) || friendlyInventoryName(detail)}</h2>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                    <span title={detail.default_code || detail.sku || ''}>SKU <span className="font-mono text-slate-700">{compactSku(detail.default_code || detail.sku, 32, 10) || '—'}</span></span>
                    <span>Barcode <span className="font-mono text-slate-700">{detail.barcode || '—'}</span></span>
                    <span>{detail.categ_name || 'Uncategorized'}</span>
                    {detail.brand ? <span>{detail.brand}</span> : null}
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    {[
                      ['Supplier', detail.supplier_name || 'Not linked'],
                      ['Storage bin', detail.storage_bin || 'Unset'],
                      ['Threshold', fmtQty(detail.low_stock_threshold)],
                    ].map(([label, value]) => (
                      <div key={label} className="inventory-detail-card rounded-2xl px-4 py-3">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</div>
                        <div className="mt-1 text-sm font-semibold text-slate-900">{value || '—'}</div>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col gap-2 xl:items-end">
                  <Button onClick={() => onEdit(detail)} className="min-w-[132px]">Edit product</Button>
                  <Button variant="secondary" onClick={() => onArchive?.(detail)} className="min-w-[132px]">Archive</Button>
                  <Button variant="secondary" onClick={() => onAdjust?.(detail)} className="min-w-[132px] border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100">Adjust stock</Button>
                </div>
              </div>
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {[
                ['On hand', fmtQty(onHandQty)],
                ['Cost', fmt(detail.standard_price ?? detail.cost_price)],
                ['Raw cost', fmt(detail.raw_cost)],
                ...(showCostUplifts ? [
                  ['Cost + 12%', fmt(detail.cost_plus_12)],
                  ['Cost + 20%', fmt(detail.cost_plus_20)],
                ] : []),
                ['Retail', fmt(detail.list_price ?? detail.retail_price)],
              ].map(([label, value]) => (
                <Card key={label} className="inventory-detail-kpi rounded-2xl border-violet-100/90 bg-white/95">
                  <CardContent className="p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</div>
                    <div className="mt-1 text-[1.35rem] font-semibold tracking-[-0.03em] text-slate-950">{value}</div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">
            <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="mb-5 rounded-2xl border border-violet-100 bg-white/90 p-1 shadow-sm">
              {TABS.map((t) => (
                <TabsTrigger key={t.id} value={t.id}>
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
            </Tabs>

              {tab === 'overview' && (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <Card className="inventory-detail-card rounded-3xl border-violet-100/90">
                    <CardContent className="p-0">
                      <div className="border-b border-slate-100 px-5 py-4">
                        <div className="text-sm font-semibold text-slate-950">Product information</div>
                        <div className="mt-1 text-sm text-slate-500">Core identifiers and operational details.</div>
                      </div>
                      {[
                        ['SKU', detail.default_code || detail.sku, true],
                        ['Barcode', detail.barcode, true],
                        ['Brand', detail.brand, false],
                        ['Gender', normalizeGenderValue(detail.gender), false],
                        ['Supplier', detail.supplier_name, false],
                        ['Storage bin', detail.storage_bin, false],
                        ['Low stock threshold', fmtQty(detail.low_stock_threshold), false],
                      ].map(([label, value, mono]) => (
                        <div key={label} className="flex items-start justify-between gap-6 border-b border-slate-100 px-5 py-3 last:border-0">
                          <span className="text-sm text-slate-500">{label}</span>
                          <span className={mono ? 'break-all text-right font-mono text-sm font-medium text-slate-800' : 'break-words text-right text-sm font-medium text-slate-800'}>
                            {value || '—'}
                          </span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  <div className="grid gap-4">
                    <Card className="inventory-detail-sidecard rounded-3xl border-violet-100/90">
                      <CardContent>
                        <div className="text-sm font-semibold text-slate-950">Description</div>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{detail.description || 'No description added yet.'}</p>
                        {galleryUrls.length ? (
                          <div className="mt-4">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Image Gallery</div>
                            <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                              {galleryUrls.map((url, index) => (
                                <a
                                  key={`${url}-${index}`}
                                  href={url}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="block shrink-0 rounded-lg border border-slate-200 bg-white p-1"
                                  title={`Open image ${index + 1}`}
                                >
                                  <img
                                    src={url}
                                    alt={`Product gallery ${index + 1}`}
                                    className="h-20 w-20 rounded object-contain"
                                  />
                                </a>
                              ))}
                            </div>
                            <div className="mt-1 text-xs text-slate-500">{galleryUrls.length} image{galleryUrls.length === 1 ? '' : 's'} attached</div>
                          </div>
                        ) : null}
                        {detail.tiktok_highlights ? (
                          <div className="mt-4">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Highlights</div>
                            <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700">{detail.tiktok_highlights}</p>
                          </div>
                        ) : null}
                      </CardContent>
                    </Card>
                    <Card className="inventory-detail-sidecard rounded-3xl border-violet-100/90">
                      <CardContent className="space-y-3">
                        <div>
                          <div className="text-sm font-semibold text-slate-950">Display notes</div>
                          <div className="mt-1 text-sm text-slate-500">What appears on scanner/display workflows.</div>
                        </div>
                        {[
                          ['Top', detail.note_top],
                          ['Middle', detail.note_mid],
                          ['Base', detail.note_base],
                          ['Similar to', detail.similar_to],
                          ['Inspired by', detail.dupe_inspiration],
                          ['Media', detail.media_url],
                        ].map(([label, value]) => (
                          <div key={label} className="flex items-start justify-between gap-4 text-sm">
                            <span className="text-slate-500">{label}</span>
                            <span className="max-w-[220px] break-words text-right font-medium text-slate-800">{value || '—'}</span>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  </div>
                </div>
              )}

              {tab === 'pricing' && (
                <Card>
                  <CardContent className="grid gap-0 p-0">
                    {[
                      ['Cost', fmt(detail.standard_price ?? detail.cost_price)],
                      ['Raw cost', fmt(detail.raw_cost)],
                      ...(showCostUplifts ? [
                        ['Cost + 12%', fmt(detail.cost_plus_12)],
                        ['Cost + 20%', fmt(detail.cost_plus_20)],
                      ] : []),
                      ['Retail', fmt(detail.list_price ?? detail.retail_price)],
                      ['Margin', marginPct == null ? '—' : fmtPct(marginPct)],
                      ['Average sale price', fmt(avgSalePrice)],
                    ].map(([label, value]) => (
                      <div key={label} className="flex items-center justify-between border-b border-slate-100 px-5 py-4 last:border-0">
                        <span className="text-sm text-slate-500">{label}</span>
                        <span className="font-semibold text-slate-950">{value}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {tab === 'inventory' && (
                <Card>
                  <CardContent className="grid gap-0 p-0">
                    {[
                      ['On hand', fmtQty(onHandQty)],
                      ['Forecast qty', fmtQty(detail.virtual_available ?? detail.on_hand_qty)],
                      ['Low stock threshold', fmtQty(detail.low_stock_threshold)],
                      ['Storage bin', detail.storage_bin || '—'],
                      ['Supplier', detail.supplier_name || '—'],
                    ].map(([label, value]) => (
                      <div key={label} className="flex items-center justify-between border-b border-slate-100 px-5 py-4 last:border-0">
                        <span className="text-sm text-slate-500">{label}</span>
                        <span className="font-semibold text-slate-950">{value}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {tab === 'notes' && (
                <Card>
                  <CardContent className="space-y-4">
                    {[
                      ['Top', detail.note_top],
                      ['Middle', detail.note_mid],
                      ['Base', detail.note_base],
                      ['Quick note', detail.notes],
                      ['Title (approval-safe)', detail.tiktok_title],
                      ['Item name', detail.tiktok_item_name],
                      ['Manufacturer', detail.tiktok_manufacturer],
                      ['Size (oz)', detail.size_oz],
                      ['Size (mL)', detail.size_ml],
                      ['Volume (oz)', detail.volume_oz ?? detailVolumes.oz],
                      ['Volume (mL)', detail.volume_ml ?? detailVolumes.ml],
                      ['Volume', detail.tiktok_volume],
                      ['Package weight (oz)', detail.tiktok_package_weight_oz],
                      ['Scent', detail.tiktok_scent],
                      ['Features', detail.tiktok_feature],
                      ['Ingredients', detail.tiktok_ingredients],
                      ['Search keywords', detail.tiktok_search_keywords],
                      ['Similar to', detail.similar_to],
                      ['Inspired by', detail.dupe_inspiration],
                      ['Fragrantica', detail.source_fragrantica_url],
                      ['Jomashop', detail.source_jomashop_url],
                      ['Parfumo', detail.source_parfumo_url],
                      ['Official source', detail.source_official_url],
                      ['Media URL', detail.media_url],
                    ].map(([label, value]) => (
                      <div key={label}>
                        <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
                        <div className="mt-1 text-sm text-slate-800">{value || '—'}</div>
                      </div>
                    ))}
                    {detail.fragrance_research ? (
                      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                        <div className="text-sm font-semibold text-slate-950">Fragrance Research</div>
                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                          {[
                            ['Accords', detail.fragrance_research.accords],
                            ['Family', detail.fragrance_research.fragrance_family],
                            ['DNA', detail.fragrance_research.fragrance_dna],
                            ['Best for seasons', detail.fragrance_research.best_for_seasons],
                            ['Best for occasions', detail.fragrance_research.best_for_occasions],
                            ['Best for time', detail.fragrance_research.best_for_time_of_day],
                            ['Longevity', detail.fragrance_research.longevity],
                            ['Projection', detail.fragrance_research.projection],
                            ['Sillage', detail.fragrance_research.sillage],
                            ['Compliment factor', detail.fragrance_research.compliment_factor],
                            ['Mood keywords', detail.fragrance_research.mood_keywords],
                            ['Similar signature', detail.fragrance_research.similar_signature],
                            ['Inspired by signature', detail.fragrance_research.inspired_by_signature],
                            ['Source confidence', detail.fragrance_research.source_confidence],
                            ['Verified sources', detail.fragrance_research.verified_sources_count],
                            ['Manual review', detail.fragrance_research.needs_manual_review ? 'Yes' : 'No'],
                          ].map(([label, value]) => (
                            <div key={label}>
                              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
                              <div className="mt-1 text-sm text-slate-800">{value || '—'}</div>
                            </div>
                          ))}
                        </div>
                        {detail.fragrance_research.source_summary ? (
                          <div className="mt-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Research summary</div>
                            <div className="mt-1 whitespace-pre-wrap text-sm text-slate-800">{detail.fragrance_research.source_summary}</div>
                          </div>
                        ) : null}
                        {Array.isArray(detail.fragrance_research_sources) && detail.fragrance_research_sources.length ? (
                          <div className="mt-3">
                            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Research sources</div>
                            <div className="mt-2 space-y-2">
                              {detail.fragrance_research_sources.map((source) => (
                                <div key={`${source.id || source.source_url}-${source.source_type}`} className="rounded-lg border border-slate-200 bg-white p-3">
                                  <div className="text-sm font-medium text-slate-900">{source.source_label || source.source_type || 'Source'}</div>
                                  <div className="mt-1 text-xs text-slate-500">{source.evidence_kind || 'reference'}</div>
                                  {source.source_url ? (
                                    <a href={source.source_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-blue-600 hover:text-blue-700">
                                      {source.source_url}
                                    </a>
                                  ) : null}
                                  {source.evidence_excerpt ? (
                                    <div className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{source.evidence_excerpt}</div>
                                  ) : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              )}

              {/* Sales History */}
              {tab === 'sales' && (
                !sales.length
                  ? <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>No Whatnot sales linked to this product yet.</div>
                  : <TableShell footer={`${sales.length} sale${sales.length === 1 ? '' : 's'} · Revenue ${fmt(summary.total_revenue)} · Profit ${fmt(summary.total_profit)}`}>
                      <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                        <tr>{['Date', 'Session', 'Buyer', 'Lot #', 'Sale Price', 'Profit'].map((h) => <th key={h} style={thStyle}>{h}</th>)}</tr>
                      </thead>
                      <tbody>
                        {sales.map((sale) => (
                          <tr key={sale.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                            <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{sale.sold_at ? new Date(sale.sold_at).toLocaleString() : '—'}</td>
                            <td style={{ padding: '10px 14px', fontSize: 13 }}>{sale.session_name || '—'}</td>
                            <td style={{ padding: '10px 14px', fontWeight: 700 }}>@{sale.buyer_username || 'unknown'}</td>
                            <td style={{ padding: '10px 14px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{sale.lot_number || '—'}</td>
                            <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(sale.allocated_revenue ?? sale.sale_price)}</td>
                            <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700, color: Number(sale.profit || 0) >= 0 ? 'var(--accent-emerald)' : 'var(--accent-coral)' }}>{fmt(sale.profit)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </TableShell>
              )}

              {/* Stock Moves */}
              {tab === 'moves' && (
                !movements.length
                  ? <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>No stock moves found.</div>
                  : <TableShell footer={`${movements.length} movement${movements.length === 1 ? '' : 's'}`}>
                      <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                        <tr>{['Date', 'Type', 'Reference', 'Qty', 'From → To'].map((h) => <th key={h} style={thStyle}>{h}</th>)}</tr>
                      </thead>
                      <tbody>
                        {movements.map((move) => {
                          const outflow = (move.location_dest_id_name || '').toLowerCase().includes('customer')
                            || (move.location_dest_id_name || '').toLowerCase().includes('output')
                            || Number(move.qty_delta || 0) < 0;
                          return (
                            <tr key={move.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                              <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{move.date || move.created_at ? new Date(move.date || move.created_at).toLocaleString() : '—'}</td>
                              <td style={{ padding: '10px 14px', fontSize: 12 }}>{move.movement_type || '—'}</td>
                              <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)' }}>{move.reason || move.name || '—'}</td>
                              <td style={{ padding: '10px 14px', textAlign: 'right', fontWeight: 700, color: outflow ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{outflow ? '−' : '+'}{fmtQty(Math.abs(move.product_uom_qty ?? move.qty_delta ?? 0))}</td>
                              <td style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-secondary)' }}>{move.location_id_name || move.reference_type || '—'} → {move.location_dest_id_name || '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </TableShell>
              )}

              {tab === 'audit' && (
                !auditRows.length
                  ? <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '40px 0', textAlign: 'center' }}>No audit activity recorded yet for this product.</div>
                  : <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {auditRows.map((entry) => {
                        const changedFields = Object.entries(entry.changed_fields || {});
                        return (
                          <Card key={entry.id}>
                            <CardContent className="p-4">
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', marginBottom: changedFields.length ? 10 : 0 }}>
                              <div>
                                <div style={{ fontSize: 13, fontWeight: 800, color: '#0f172a' }}>
                                  {prettifyFieldName(entry.event_type || 'event')}
                                </div>
                                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                                  {entry.actor || entry.source || 'system'} · {entry.created_at ? new Date(entry.created_at).toLocaleString() : '—'}
                                </div>
                              </div>
                              <span style={{ display: 'inline-flex', alignItems: 'center', padding: '3px 10px', borderRadius: 999, background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569', fontSize: 11, fontWeight: 700 }}>
                                {entry.source || 'inventory'}
                              </span>
                            </div>
                            {changedFields.length ? (
                              <div style={{ display: 'grid', gap: 8 }}>
                                {changedFields.map(([field, values]) => (
                                  <div key={field} style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr) minmax(0,1fr)', gap: 10, alignItems: 'start', fontSize: 12 }}>
                                    <div style={{ color: '#64748b', fontWeight: 700 }}>{prettifyFieldName(field)}</div>
                                    <div style={{ color: '#b42318', wordBreak: 'break-word' }}>Was: {formatAuditValue(values?.before)}</div>
                                    <div style={{ color: '#027a48', wordBreak: 'break-word' }}>Now: {formatAuditValue(values?.after)}</div>
                                  </div>
                                ))}
                              </div>
                            ) : null}
                            {entry.metadata && Object.keys(entry.metadata).length ? (
                              <div style={{ marginTop: 10, fontSize: 12, color: '#64748b' }}>
                                {Object.entries(entry.metadata).map(([key, value]) => (
                                  <span key={key} style={{ display: 'inline-block', marginRight: 14, marginTop: 6 }}>
                                    <strong style={{ color: '#0f172a' }}>{prettifyFieldName(key)}:</strong> {formatAuditValue(value)}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                            </CardContent>
                          </Card>
                        );
                      })}
                    </div>
              )}
          </div>
        </div>
      )}
    </FullPageForm>
  );
}

function normalizeEditorFormSnapshot(form) {
  if (!form) return '';
  const base = {
    name: String(form.name ?? ''),
    default_code: String(form.default_code ?? ''),
    barcode: String(form.barcode ?? ''),
    categ_id: String(form.categ_id ?? ''),
    brand: String(form.brand ?? ''),
    gender: String(form.gender ?? ''),
    supplier_name: String(form.supplier_name ?? ''),
    storage_bin: String(form.storage_bin ?? ''),
    type: String(form.type ?? ''),
    standard_price: String(form.standard_price ?? ''),
    raw_cost: String(form.raw_cost ?? ''),
    cost_plus_12: String(form.cost_plus_12 ?? ''),
    cost_plus_20: String(form.cost_plus_20 ?? ''),
    list_price: String(form.list_price ?? ''),
    qty_available: String(form.qty_available ?? ''),
    low_stock_threshold: String(form.low_stock_threshold ?? ''),
    size_oz: String(form.size_oz ?? ''),
    size_ml: String(form.size_ml ?? ''),
    volume_oz: String(form.volume_oz ?? ''),
    volume_ml: String(form.volume_ml ?? ''),
    active: !!form.active,
    description_body: String(form.description_body ?? ''),
    notes: String(form.notes ?? ''),
    notes_verified: !!form.notes_verified,
    dupe_inspiration: String(form.dupe_inspiration ?? ''),
    dupe_confidence: String(form.dupe_confidence ?? ''),
    dupe_classification: String(form.dupe_classification ?? ''),
    dupe_notes: String(form.dupe_notes ?? ''),
    note_top: String(form.note_top ?? ''),
    note_mid: String(form.note_mid ?? ''),
    note_base: String(form.note_base ?? ''),
    media_url: String(form.media_url ?? ''),
  };
  TIKTOK_FIELD_NAMES.forEach((key) => {
    base[key] = form[key] == null ? '' : String(form[key]);
  });
  return JSON.stringify(base);
}

// ─── Product Editor ──────────────────────────────────────────────────────────

function ProductEditor({ product, categories, onClose, onSaved, onPrev, onNext, canPrev, canNext, positionLabel, showCostUplifts = false }) {
  const isNew = !product?.id;
  const touchStartRef = useRef(null);
  const dragDepthRef = useRef(0);
  const hydrationSnapshotRef = useRef('');
  const buildEditorForm = (sourceProduct) => {
    const editableName = editableInventoryName(sourceProduct) || '';
    const generatedSku = generateSkuFromName(editableName || sourceProduct?.name || '');
    const parsedVolumes = parseSizeOrVolumePair({
      sizeOz: sourceProduct.size_oz,
      sizeMl: sourceProduct.size_ml,
      volumeOz: sourceProduct.volume_oz,
      volumeMl: sourceProduct.volume_ml,
      tiktokVolume: sourceProduct.tiktok_volume,
      name: sourceProduct.name,
    });
    const baseForm = {
      name: editableName,
      default_code: sourceProduct.default_code || sourceProduct.sku || generatedSku,
      barcode: sourceProduct.barcode || '',
      categ_id: sourceProduct.categ_id || sourceProduct.category_id || '',
      brand: sourceProduct.brand || '',
      gender: normalizeGenderValue(sourceProduct.gender),
      supplier_name: sourceProduct.supplier_name || '',
      storage_bin: sourceProduct.storage_bin || '',
      type: sourceProduct.type || sourceProduct.product_type || 'product',
      standard_price: sourceProduct.standard_price ?? sourceProduct.cost_price ?? 0,
      raw_cost: sourceProduct.raw_cost ?? 0,
      cost_plus_12: sourceProduct.cost_plus_12 ?? 0,
      cost_plus_20: sourceProduct.cost_plus_20 ?? 0,
      list_price: sourceProduct.list_price ?? sourceProduct.retail_price ?? 0,
      qty_available: sourceProduct.qty_available ?? sourceProduct.on_hand_qty ?? 0,
      low_stock_threshold: sourceProduct.low_stock_threshold ?? 3,
      size_oz: sourceProduct.size_oz ?? parsedVolumes.oz ?? '',
      size_ml: sourceProduct.size_ml ?? parsedVolumes.ml ?? '',
      volume_oz: sourceProduct.volume_oz ?? parsedVolumes.oz ?? '',
      volume_ml: sourceProduct.volume_ml ?? parsedVolumes.ml ?? '',
      active: sourceProduct.active !== false,
      description: sourceProduct.description || '',
      description_body: extractDescriptionBody(sourceProduct.description || ''),
      notes: sourceProduct.notes || '',
      notes_verified: !!sourceProduct.notes_verified,
      notes_verified_at: sourceProduct.notes_verified_at || '',
      dupe_inspiration: sourceProduct.dupe_inspiration || '',
      dupe_confidence: sourceProduct.dupe_confidence || '',
      dupe_classification: sourceProduct.dupe_classification || '',
      dupe_notes: sourceProduct.dupe_notes || '',
      note_top: sourceProduct.note_top || '',
      note_mid: sourceProduct.note_mid || '',
      note_base: sourceProduct.note_base || '',
      media_url: sourceProduct.media_url || '',
      ...TIKTOK_FIELD_NAMES.reduce((acc, key) => {
        acc[key] = sourceProduct[key] ?? TIKTOK_FIELD_DEFAULTS[key];
        return acc;
      }, {}),
      sds_pdf_base64: '',
      sds_pdf_filename: '',
      image_128: null,
    };
    const effectiveCategoryName = String(sourceProduct.tiktok_category_name || '').trim() || deriveTikTokFragranceCategory(sourceProduct.gender);
    const effectiveName = editableName || '';
    return {
      ...baseForm,
      name: effectiveName,
      tiktok_title: effectiveName || baseForm.tiktok_title,
      tiktok_item_name: effectiveName || baseForm.tiktok_item_name,
      tiktok_category_name: effectiveCategoryName,
    };
  };
  const initialGeneratedSku = generateSkuFromName(editableInventoryName(product) || product.name || '');
  const [form, setForm] = useState(() => buildEditorForm(product));
  const [preview, setPreview] = useState(product.image_url || product.media_url || null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [skuManuallyEdited, setSkuManuallyEdited] = useState(() => {
    const existingSku = String(product.default_code || product.sku || '').trim();
    return !!existingSku && existingSku !== initialGeneratedSku;
  });
  const [sellerSkuManuallyEdited, setSellerSkuManuallyEdited] = useState(() => {
    const existingSellerSku = String(product.tiktok_seller_sku || '').trim();
    const canonicalSku = String(product.default_code || product.sku || initialGeneratedSku).trim();
    return !!existingSellerSku && existingSellerSku !== canonicalSku;
  });
  const [channelTab, setChannelTab] = useState('listing');
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState(() => normalizeEditorFormSnapshot(buildEditorForm(product)));
  const [isPdfDragActive, setIsPdfDragActive] = useState(false);
  const currentSdsPreviewUrl = sdsPreviewUrl(form.tiktok_sds_file_path);

  useEffect(() => {
    const nextForm = buildEditorForm(product);
    const nextSnapshot = normalizeEditorFormSnapshot(nextForm);
    const nextGeneratedSku = generateSkuFromName(nextForm.name || product.name || '');
    setForm(nextForm);
    setLastSavedSnapshot(nextSnapshot);
    hydrationSnapshotRef.current = nextSnapshot;
    setPreview(product.image_url || product.media_url || null);
    setMessage(null);
    const existingSku = String(product.default_code || product.sku || '').trim();
    setSkuManuallyEdited(!!existingSku && existingSku !== nextGeneratedSku);
    const existingSellerSku = String(product.tiktok_seller_sku || '').trim();
    const canonicalSku = String(product.default_code || product.sku || nextGeneratedSku).trim();
    setSellerSkuManuallyEdited(!!existingSellerSku && existingSellerSku !== canonicalSku);
    setChannelTab('listing');

    let cancelled = false;
    if (product?.id) {
      fetchApi(`/api/inventory/product_detail?product_id=${product.id}`)
        .then((detailResult) => {
          if (cancelled) return;
          const freshProduct = detailResult?.product;
          if (!freshProduct) return;
          const hydratedSource = {
            ...product,
            ...freshProduct,
            image_url: freshProduct.image_url || product.image_url || null,
            media_url: freshProduct.media_url || product.media_url || '',
          };
          const hydratedForm = buildEditorForm(hydratedSource);
          const hydratedSnapshot = normalizeEditorFormSnapshot(hydratedForm);
          setForm((current) => (
            normalizeEditorFormSnapshot(current) === hydrationSnapshotRef.current
              ? hydratedForm
              : current
          ));
          setLastSavedSnapshot((current) => (
            current === hydrationSnapshotRef.current
              ? hydratedSnapshot
              : current
          ));
          if (!preview) {
            setPreview(hydratedSource.image_url || hydratedSource.media_url || null);
          }
          hydrationSnapshotRef.current = hydratedSnapshot;
        })
        .catch(() => {});
    }
    return () => {
      cancelled = true;
    };
  }, [product]);

  const currentSnapshot = normalizeEditorFormSnapshot(form);
  const isDirty = currentSnapshot !== lastSavedSnapshot;

  function normalizeOptionalText(value) {
    return value === '' ? null : value;
  }

  function confirmDiscardChanges(actionLabel = 'leave this page') {
    if (!isDirty) return true;
    return window.confirm(`You have unsaved changes. Do you want to discard them and ${actionLabel}?`);
  }

  function handleClose() {
    if (!confirmDiscardChanges('close the product')) return;
    onClose?.();
  }

  function handlePrev() {
    if (!canPrev) return;
    if (!confirmDiscardChanges('go to the previous product')) return;
    onPrev?.();
  }

  function handleNext() {
    if (!canNext) return;
    if (!confirmDiscardChanges('go to the next product')) return;
    onNext?.();
  }

  function setField(key, value) {
    setForm((current) => {
      if (key === 'tiktok_title') {
        return { ...current, tiktok_title: value, tiktok_item_name: value, name: value };
      }
      if (key === 'tiktok_item_name') {
        return { ...current, tiktok_item_name: value, tiktok_title: value, name: value };
      }
      if (key === 'gender') {
        return {
          ...current,
          gender: value,
          tiktok_category_name: deriveTikTokFragranceCategory(value),
        };
      }
      return { ...current, [key]: value };
    });
  }

  function setProductName(value) {
    setForm((current) => {
      const next = { ...current, name: value };
      next.tiktok_title = value;
      next.tiktok_item_name = value;
      next.tiktok_category_name = deriveTikTokFragranceCategory(current.gender);
      const autoSku = generateSkuFromName(value);
      const currentAutoSku = generateSkuFromName(current.name);
      const shouldSyncSku = !skuManuallyEdited || !String(current.default_code || '').trim() || String(current.default_code || '').trim() === currentAutoSku;
      const shouldSyncSellerSku = !sellerSkuManuallyEdited || !String(current.tiktok_seller_sku || '').trim() || String(current.tiktok_seller_sku || '').trim() === String(current.default_code || '').trim() || String(current.tiktok_seller_sku || '').trim() === currentAutoSku;
      if (shouldSyncSku) next.default_code = autoSku;
      if (shouldSyncSellerSku) next.tiktok_seller_sku = autoSku;
      return next;
    });
  }

  function setSkuValue(value) {
    setSkuManuallyEdited(true);
    setForm((current) => ({ ...current, default_code: value }));
  }

  function setSellerSkuValue(value) {
    setSellerSkuManuallyEdited(true);
    setForm((current) => ({ ...current, tiktok_seller_sku: value }));
  }

  function handleFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      setField('image_128', base64);
      setPreview(result);
    };
    reader.readAsDataURL(file);
  }

  function handleSdsFile(file) {
    if (!file) return;
    const lowerName = String(file.name || '').toLowerCase();
    const mimeType = String(file.type || '').toLowerCase();
    if (mimeType !== 'application/pdf' && !lowerName.endsWith('.pdf')) {
      setMessage({ type: 'error', text: 'Only PDF files can be attached as SDS documents.' });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      setForm((current) => ({
        ...current,
        sds_pdf_base64: base64,
        sds_pdf_filename: file.name || 'sds.pdf',
      }));
    };
    reader.readAsDataURL(file);
  }

  function handleEditorDragEnter(event) {
    const hasFiles = Array.from(event.dataTransfer?.types || []).includes('Files');
    if (!hasFiles) return;
    dragDepthRef.current += 1;
    setIsPdfDragActive(true);
  }

  function handleEditorDragOver(event) {
    const hasFiles = Array.from(event.dataTransfer?.types || []).includes('Files');
    if (!hasFiles) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }

  function handleEditorDragLeave() {
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) setIsPdfDragActive(false);
  }

  function handleEditorDrop(event) {
    const files = Array.from(event.dataTransfer?.files || []);
    if (!files.length) return;
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsPdfDragActive(false);
    const pdf = files.find((file) => {
      const lowerName = String(file.name || '').toLowerCase();
      const mimeType = String(file.type || '').toLowerCase();
      return mimeType === 'application/pdf' || lowerName.endsWith('.pdf');
    });
    if (!pdf) {
      setMessage({ type: 'error', text: 'Drop a PDF file to attach an SDS document.' });
      return;
    }
    if (String(form.tiktok_dangerous_goods_or_hazardous_materials || '') !== 'Yes') {
      setField('tiktok_dangerous_goods_or_hazardous_materials', 'Yes');
    }
    handleSdsFile(pdf);
    setMessage({ type: 'success', text: `SDS PDF ready to save: ${pdf.name}` });
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      let savedSnapshot = {};
      try {
        savedSnapshot = JSON.parse(lastSavedSnapshot || '{}') || {};
      } catch {
        savedSnapshot = {};
      }
      const canonicalSku = String(form.default_code || '').trim() || generateSkuFromName(form.name);
      const desiredQty = Number(form.qty_available || 0);
      const expectedQty = Number(savedSnapshot.qty_available || 0);
      const qtyChanged = isNew || Math.abs(desiredQty - expectedQty) > 0.0001;
      const payload = {
        name: form.name,
        default_code: canonicalSku,
        barcode: normalizeOptionalText(form.barcode),
        categ_id: form.categ_id || false,
        brand: normalizeOptionalText(form.brand),
        gender: normalizeOptionalText(form.gender),
        supplier_name: normalizeOptionalText(form.supplier_name),
        storage_bin: normalizeOptionalText(form.storage_bin),
        type: form.type,
        standard_price: Number(form.standard_price || 0),
        raw_cost: Number(form.raw_cost || 0),
        cost_plus_12: Number(form.cost_plus_12 || 0),
        cost_plus_20: Number(form.cost_plus_20 || 0),
        list_price: Number(form.list_price || 0),
        low_stock_threshold: Number(form.low_stock_threshold || 0),
        size_oz: form.size_oz === '' ? null : Number(form.size_oz),
        size_ml: form.size_ml === '' ? null : Number(form.size_ml),
        volume_oz: form.volume_oz === '' ? null : Number(form.volume_oz),
        volume_ml: form.volume_ml === '' ? null : Number(form.volume_ml),
        active: !!form.active,
        description: buildStructuredProductDescription({
          productName: friendlyInventoryName({ name: form.name, brand: form.brand }) || form.name,
          descriptionBody: form.description_body,
          noteTop: form.note_top,
          noteMid: form.note_mid,
          noteBase: form.note_base,
          size: formatSeparateSize({ name: form.name, tiktokVolume: form.tiktok_volume, sizeOz: form.size_oz, sizeMl: form.size_ml }),
          gender: form.gender,
        }),
        notes: normalizeOptionalText(form.notes),
        notes_verified: !!form.notes_verified,
        dupe_inspiration: normalizeOptionalText(form.dupe_inspiration),
        dupe_confidence: normalizeOptionalText(form.dupe_confidence),
        dupe_classification: normalizeOptionalText(form.dupe_classification),
        dupe_notes: normalizeOptionalText(form.dupe_notes),
        note_top: normalizeOptionalText(form.note_top),
        note_mid: normalizeOptionalText(form.note_mid),
        note_base: normalizeOptionalText(form.note_base),
        media_url: normalizeOptionalText(form.media_url),
      };
      TIKTOK_FIELD_NAMES.forEach((key) => {
        if (key === 'tiktok_quantity' && !qtyChanged) return;
        let value = form[key];
        if (key === 'tiktok_title') value = form.tiktok_title;
        else if (key === 'tiktok_category_name') value = deriveTikTokFragranceCategory(form.gender);
        else if (key === 'tiktok_brand') value = form.brand;
        else if (key === 'tiktok_quantity') value = form.qty_available;
        else if (key === 'tiktok_retail_price') value = form.list_price;
        else if (key === 'tiktok_ean') value = form.barcode;
        else if (key === 'tiktok_volume') value = formatSeparateSize({ name: form.name, tiktokVolume: form.tiktok_volume, sizeOz: form.volume_oz || form.size_oz, sizeMl: form.volume_ml || form.size_ml });
        else if (key === 'tiktok_seller_sku') value = String(form.tiktok_seller_sku || '').trim() || canonicalSku;
        payload[key] = TIKTOK_NUMERIC_FIELDS.has(key)
          ? (value === '' || value == null ? null : Number(value))
          : normalizeOptionalText(value);
      });
      if (form.sds_pdf_base64) {
        payload.sds_pdf_base64 = form.sds_pdf_base64;
        payload.sds_pdf_filename = form.sds_pdf_filename || 'sds.pdf';
      }
      if (product.id) payload.product_id = product.id;
      if (form.image_128) payload.image_128 = form.image_128;
      if (qtyChanged) {
        payload.qty_available = desiredQty;
        payload.stock_adjustment_intent = true;
        payload.adjustment_reason = isNew ? 'initial_stock' : 'product_editor_stock_edit';
      }
      const result = await postApi('/api/inventory/product/update', payload);
      let savedProduct = result.product || null;
      const savedId = savedProduct?.id || product?.id || result?.product_id || null;
      if (savedId) {
        try {
          const detail = await fetchApi(`/api/inventory/product_detail?product_id=${savedId}`);
          if (detail?.product) savedProduct = detail.product;
        } catch {
          // Fall back to the update response if the detail refresh fails.
        }
      }
      if (savedProduct) setLastSavedSnapshot(normalizeEditorFormSnapshot(buildEditorForm(savedProduct)));
      setMessage({ type: 'success', text: result.stock_adjusted ? 'Product and stock updated.' : (isNew ? 'Product created.' : 'Product updated.') });
      onSaved(savedProduct);
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Save failed.' });
    } finally {
      setSaving(false);
    }
  }

  const cost = Number(form.standard_price || 0);
  const retail = Number(form.list_price || 0);
  const qty = Number(form.qty_available || 0);
  const lowStockThreshold = Number(form.low_stock_threshold || 0);
  const profitUnit = retail - cost;
  const stockValue = qty * cost;
  const marginNumber = retail > 0 ? ((profitUnit / retail) * 100) : null;
  const margin = marginNumber == null ? null : marginNumber.toFixed(1);
  const displayedImage = preview || form.media_url || product.image_url || null;
  const hasNotes = !!(form.note_top || form.note_mid || form.note_base || form.notes);
  const completionItems = [
    { label: 'Image', done: !!displayedImage },
    { label: 'Barcode', done: !!form.barcode },
    { label: 'Cost', done: cost > 0 },
    { label: 'Retail', done: retail > 0 },
    { label: 'Notes', done: hasNotes },
    { label: 'Verified', done: !!form.notes_verified },
  ];
  const completionScore = Math.round((completionItems.filter((item) => item.done).length / completionItems.length) * 100);
  const stockTone = qty <= 0 ? '#dc2626' : qty <= lowStockThreshold ? '#d97706' : '#059669';
  const headerProductName = friendlyInventoryName({ name: form.name, brand: form.brand });
  const canonicalSku = String(form.default_code || '').trim() || generateSkuFromName(form.name);
  const unifiedTikTokTitle = form.name;
  const unifiedTikTokBrand = form.brand;
  const unifiedTikTokQty = qty;
  const unifiedTikTokRetail = retail;
  const unifiedTikTokEan = form.barcode;
  const headerProductMeta = [
    form.brand,
    compactSku(canonicalSku || form.sku, 34, 8),
    form.barcode,
  ].filter(Boolean).join(' / ');

  useEffect(() => {
    function handleKeyDown(event) {
      const tag = String(event.target?.tagName || '').toLowerCase();
      const typingTarget = tag === 'input' || tag === 'textarea' || tag === 'select' || event.target?.isContentEditable;
      if (typingTarget) return;
      if (event.key === 'ArrowLeft' && canPrev) {
        event.preventDefault();
        handlePrev();
      } else if (event.key === 'ArrowRight' && canNext) {
        event.preventDefault();
        handleNext();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [canNext, canPrev, handleNext, handlePrev]);

  useEffect(() => {
    function handleBeforeUnload(event) {
      if (!isDirty) return;
      event.preventDefault();
      event.returnValue = '';
    }
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  function handleTouchStart(event) {
    const touch = event.touches?.[0];
    if (!touch) return;
    touchStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      tag: String(event.target?.tagName || '').toLowerCase(),
    };
  }

  function handleTouchEnd(event) {
    const touch = event.changedTouches?.[0];
    const start = touchStartRef.current;
    touchStartRef.current = null;
    if (!touch || !start) return;
    if (start.tag === 'input' || start.tag === 'textarea' || start.tag === 'select') return;
    const deltaX = touch.clientX - start.x;
    const deltaY = touch.clientY - start.y;
    if (Math.abs(deltaX) < 70 || Math.abs(deltaX) < Math.abs(deltaY) * 1.25) return;
    if (deltaX < 0 && canNext) handleNext();
    if (deltaX > 0 && canPrev) handlePrev();
  }

  const shellCardStyle = {
    border: '1px solid #e5e7eb',
    borderRadius: 18,
    padding: '18px 20px',
    background: '#fff',
    boxShadow: '0 2px 10px rgba(15,23,42,0.04)',
  };
  const compactInputStyle = {
    ...inputStyle,
    minHeight: 40,
    padding: '9px 12px',
    fontSize: 13,
    borderRadius: 10,
    border: '1px solid #d7dde7',
    boxShadow: '0 1px 2px rgba(15,23,42,0.04)',
  };
  const compactTextareaStyle = {
    ...compactInputStyle,
    width: '100%',
    resize: 'vertical',
    lineHeight: 1.5,
  };
  const compactLabelStyle = {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  };
  const compactHeaderInputStyle = {
    ...compactInputStyle,
    minHeight: 36,
    padding: '7px 10px',
    fontSize: 12.5,
  };
  const sectionTitleStyle = {
    fontSize: 12,
    fontWeight: 900,
    color: '#334155',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: 14,
    paddingBottom: 12,
    borderBottom: '1px solid #f1f5f9',
  };
  const pillStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 8px',
    borderRadius: 999,
    border: '1px solid rgba(148, 163, 184, 0.2)',
    background: 'rgba(248,250,252,0.94)',
    color: '#334155',
    fontSize: 11,
    fontWeight: 700,
  };
  const mappingRowStyle = {
    display: 'grid',
    gridTemplateColumns: '92px minmax(0, 1fr)',
    gap: 8,
    alignItems: 'start',
    padding: '8px 10px',
    borderRadius: 10,
    background: '#f8fafc',
    border: '1px solid rgba(148,163,184,0.14)',
  };
  const sectionTitleStyleSoft = {
    fontSize: 11,
    fontWeight: 800,
    color: '#475569',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    marginBottom: 14,
  };
  const helperTextStyle = {
    fontSize: 12,
    color: '#64748b',
    lineHeight: 1.5,
  };
  const complianceRadioRowStyle = {
    display: 'flex',
    gap: 10,
    flexWrap: 'wrap',
    marginTop: 6,
  };
  const complianceRadioPillStyle = (active) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    minHeight: 38,
    padding: '0 14px',
    borderRadius: 999,
    border: active ? '1px solid rgba(92,106,196,0.42)' : '1px solid #d7dde7',
    background: active ? 'rgba(92,106,196,0.10)' : '#fff',
    color: active ? '#4454be' : '#334155',
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    userSelect: 'none',
  });
  const channelTabs = [
    ['listing', 'Listing'],
    ['attributes', 'Attributes'],
    ['compliance', 'Compliance'],
  ];
  const mainChannelTabs = channelTabs.filter(([key]) => key !== 'compliance');

  useEffect(() => {
    if (channelTab === 'compliance') setChannelTab('listing');
  }, [channelTab]);

  return (
    <FullPageForm
      title="Products"
      sub={`${form.brand || 'Inventory'} / ${exactInventoryName(form) || friendlyInventoryName({ name: form.name, brand: form.brand }) || (isNew ? 'New Product' : 'Edit Product')}${positionLabel ? ` · ${positionLabel}` : ''}`}
      onClose={handleClose}
      maxWidth="calc(100vw - 56px)"
      actions={
        <>
          {!isNew ? <GhostBtn onClick={handlePrev} disabled={!canPrev}>← Prev</GhostBtn> : null}
          {!isNew ? <GhostBtn onClick={handleNext} disabled={!canNext}>Next →</GhostBtn> : null}
          <PrimaryBtn onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save product'}</PrimaryBtn>
        </>
      }
    >
      <div
        className="erp-product-editor inventory-editor-shell"
        style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 14, padding: '8px 10px 0', position: 'relative' }}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        onDragEnter={handleEditorDragEnter}
        onDragOver={handleEditorDragOver}
        onDragLeave={handleEditorDragLeave}
        onDrop={handleEditorDrop}
      >
        {isPdfDragActive ? (
          <div style={{ position: 'absolute', inset: 10, zIndex: 20, borderRadius: 20, border: '2px dashed rgba(92,106,196,0.55)', background: 'rgba(92,106,196,0.08)', display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
            <div style={{ padding: '18px 22px', borderRadius: 16, background: 'rgba(255,255,255,0.94)', color: '#334155', fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em', boxShadow: '0 12px 30px rgba(15,23,42,0.08)' }}>
              Drop SDS PDF anywhere to attach it to this product
            </div>
          </div>
        ) : null}
        {message ? (
          <div style={{ margin: '0 6px', padding: '10px 12px', borderRadius: 12, border: `1px solid ${message.type === 'error' ? 'rgba(220,38,38,0.18)' : 'rgba(22,163,74,0.18)'}`, background: message.type === 'error' ? '#fef2f2' : '#f0fdf4', color: message.type === 'error' ? '#b91c1c' : '#166534', fontSize: 13, fontWeight: 600 }}>
            {message.text}
          </div>
        ) : null}

        <section className="inventory-editor-hero" style={{ borderRadius: 24, padding: '18px 18px 16px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '110px minmax(0, 1fr) auto', gap: 18, alignItems: 'start' }}>
            <label className="inventory-editor-media-card" style={{ width: 110, minHeight: 138, flexShrink: 0, border: '1px solid rgba(196,181,253,0.35)', borderRadius: 20, background: 'linear-gradient(180deg, #f9f7ff 0%, #eef2ff 100%)', display: 'grid', placeItems: 'center', cursor: 'pointer', color: '#8a8a9a', textTransform: 'uppercase', fontSize: 9, fontWeight: 700, letterSpacing: '0.05em', padding: '10px 8px', boxShadow: '0 16px 30px rgba(79,70,229,0.08)' }}>
              <div className="inventory-editor-pedestal" style={{ width: '100%', display: 'grid', placeItems: 'center' }}>
                <div className="inventory-editor-product" style={{ display: 'grid', placeItems: 'center', minHeight: 104 }}>
                  <div style={{ display: 'grid', placeItems: 'center', gap: 5 }}>
                    {displayedImage ? (
                      <img src={displayedImage} alt="" style={{ width: 78, height: 92, objectFit: 'contain' }} />
                    ) : (
                      <>
                        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>
                        <span>Upload</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div style={{ fontSize: 10, color: '#6366f1', fontWeight: 800 }}>Hero image</div>
              <input type="file" accept="image/*" onChange={(event) => handleFile(event.target.files?.[0])} style={{ display: 'none' }} />
            </label>

            <div style={{ minWidth: 0, display: 'grid', gap: 12 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className="inventory-editor-glass-chip" style={{ color: form.active ? '#047857' : '#b91c1c', background: form.active ? 'rgba(220,252,231,0.88)' : 'rgba(254,226,226,0.88)', borderColor: 'transparent' }}>{form.active ? 'Active' : 'Inactive'}</span>
                <span className="inventory-editor-glass-chip">{qty.toLocaleString()} on hand</span>
                <span className="inventory-editor-glass-chip" style={{ color: '#a16207', background: 'rgba(254,243,199,0.88)', borderColor: 'transparent' }}>{completionScore}% complete</span>
                {isDirty ? <span className="inventory-editor-glass-chip" style={{ color: '#c2410c', background: 'rgba(255,237,213,0.9)', borderColor: 'transparent' }}>Unsaved changes</span> : null}
              </div>
              <div style={{ fontSize: 29, lineHeight: 1.08, fontWeight: 800, color: '#0f172a', letterSpacing: '-0.035em' }}>
                {exactInventoryName(form) || friendlyInventoryName({ name: form.name, brand: form.brand }) || form.name || 'Untitled product'}
              </div>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', color: '#475569', fontSize: 12, fontWeight: 600 }}>
                <span>SKU {canonicalSku || '—'}</span>
                {form.barcode ? <span>Barcode {form.barcode}</span> : null}
                <span>{categories.find((category) => String(category.id) === String(form.categ_id))?.complete_name || 'Uncategorized'}</span>
                {form.brand ? <span>{form.brand}</span> : null}
              </div>
              <label style={{ ...compactLabelStyle, maxWidth: 520 }}>
                <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Product name</span>
                <input value={form.name} onChange={(e) => setProductName(e.target.value)} style={compactHeaderInputStyle} placeholder="Product name" />
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Category</span>
                  <select value={form.categ_id} onChange={(e) => setField('categ_id', e.target.value)} style={compactHeaderInputStyle}>
                    <option value="">Uncategorized</option>
                    {categories.map((c) => <option key={c.id} value={c.id}>{c.complete_name || c.name}</option>)}
                  </select>
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Brand</span>
                  <input value={form.brand} onChange={(e) => setField('brand', e.target.value)} style={compactHeaderInputStyle} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Supplier</span>
                  <input value={form.supplier_name} onChange={(e) => setField('supplier_name', e.target.value)} style={compactHeaderInputStyle} placeholder="—" />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Gender</span>
                  <select value={form.gender || ''} onChange={(e) => setField('gender', e.target.value)} style={compactHeaderInputStyle}>
                    <option value="">Unspecified</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Unisex">Unisex</option>
                    <option value="Boys">Boys</option>
                    <option value="Girls">Girls</option>
                  </select>
                </label>
              </div>
              <label style={{ ...compactLabelStyle, maxWidth: 560 }}>
                <span style={{ fontSize: 11, color: '#64748b', fontWeight: 700 }}>Image URL</span>
                <input value={form.media_url} onChange={(e) => setField('media_url', e.target.value)} style={{ ...compactHeaderInputStyle, fontFamily: 'SF Mono, monospace', fontSize: 11, background: '#f8fafc', color: '#475569' }} placeholder="https://..." />
              </label>
            </div>

            <div style={{ display: 'grid', gap: 10, minWidth: 210 }}>
              {[
                ['Cost', fmt(cost)],
                ['Retail', fmt(retail)],
                ['Margin', margin ? `${margin}%` : '—'],
                ['Stock value', fmt(stockValue)],
              ].map(([label, value]) => (
                <div key={label} className="inventory-editor-kpi" style={{ borderRadius: 16, padding: '12px 14px' }}>
                  <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#64748b' }}>{label}</div>
                  <div style={{ marginTop: 6, fontSize: 22, fontWeight: 800, letterSpacing: '-0.03em', color: label === 'Margin' ? stockTone : '#111827' }}>{value}</div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="inventory-editor-grid">
          <div style={{ minWidth: 0, overflowY: 'auto', paddingRight: 4, display: 'grid', gap: 16 }}>
            <section className="inventory-editor-panel" style={{ ...shellCardStyle, borderRadius: 20 }}>
              <div style={sectionTitleStyleSoft}>Inventory & Pricing</div>
              <div className="inventory-editor-field-grid">
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>On hand</span>
                  <input type="number" value={form.qty_available} onChange={(e) => setField('qty_available', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Low stock alert</span>
                  <input type="number" value={form.low_stock_threshold} onChange={(e) => setField('low_stock_threshold', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Cost</span>
                  <input type="number" step="0.01" value={form.standard_price} onChange={(e) => setField('standard_price', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                {showCostUplifts ? (
                  <>
                    <label style={compactLabelStyle}>
                      <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>+12%</span>
                      <input type="number" step="0.01" value={form.cost_plus_12} onChange={(e) => setField('cost_plus_12', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                    </label>
                    <label style={compactLabelStyle}>
                      <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>+20%</span>
                      <input type="number" step="0.01" value={form.cost_plus_20} onChange={(e) => setField('cost_plus_20', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                    </label>
                  </>
                ) : null}
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Retail</span>
                  <input type="number" step="0.01" value={form.list_price} onChange={(e) => setField('list_price', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
              </div>
              <div className="inventory-editor-field-grid-compact" style={{ marginTop: 10 }}>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Size (oz)</span>
                  <input type="number" step="0.01" value={form.size_oz} onChange={(e) => setField('size_oz', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Size (mL)</span>
                  <input type="number" step="0.01" value={form.size_ml} onChange={(e) => setField('size_ml', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Volume (oz)</span>
                  <input type="number" step="0.01" value={form.volume_oz} onChange={(e) => setField('volume_oz', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Volume (mL)</span>
                  <input type="number" step="0.01" value={form.volume_ml} onChange={(e) => setField('volume_ml', e.target.value)} style={{ ...compactInputStyle, minHeight: 36, padding: '7px 10px' }} />
                </label>
              </div>
            </section>

            <section className="inventory-editor-panel" style={{ ...shellCardStyle, borderRadius: 20 }}>
              <div style={sectionTitleStyleSoft}>Product details</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <label style={{ ...compactLabelStyle, gridColumn: 'span 2' }}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Description</span>
                  <textarea value={form.description_body ?? ''} onChange={(e) => setField('description_body', e.target.value)} rows={5} style={compactTextareaStyle} placeholder="Write the core product description once here. It will save as Product Name, Description, Top Notes, Middle Notes, Base Notes, Size, and Gender." />
                  <span style={{ fontSize: 10, color: '#8a8a9a' }}>Saved automatically in this format: Product Name, Description, Top Notes, Middle Notes, Base Notes, Size, Gender.</span>
                </label>
                <label style={{ ...compactLabelStyle, gridColumn: 'span 2' }}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Product highlights</span>
                  <textarea value={form.tiktok_highlights ?? ''} onChange={(e) => setField('tiktok_highlights', e.target.value)} rows={4} style={compactTextareaStyle} placeholder="One highlight per line" />
                </label>
              </div>
            </section>

            <section className="inventory-editor-panel" style={{ ...shellCardStyle, borderRadius: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <div style={sectionTitleStyleSoft}>TikTok channel</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <span style={{ ...pillStyle, background: '#eaebf8', color: '#3d4ab0', borderColor: 'transparent' }}>{form.tiktok_category_name || deriveTikTokFragranceCategory(form.gender)}</span>
                  <span style={{ ...pillStyle, background: '#eaebf8', color: '#3d4ab0', borderColor: 'transparent' }}>{form.tiktok_product_identifier_code_type || 'EAN'}</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid #e2e2ea', marginBottom: 16 }}>
                {mainChannelTabs.map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setChannelTab(key)}
                    style={{
                      fontSize: 12,
                      fontWeight: 500,
                      padding: '8px 16px',
                      cursor: 'pointer',
                      color: channelTab === key ? '#5c6ac4' : '#8a8a9a',
                      border: 'none',
                      borderBottom: channelTab === key ? '2px solid #5c6ac4' : '2px solid transparent',
                      marginBottom: -1,
                      background: 'transparent',
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {channelTab === 'listing' ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Category</span>
                    <input value={form.tiktok_category_name || deriveTikTokFragranceCategory(form.gender)} readOnly style={{ ...compactInputStyle, background: '#f8fafc', color: '#475569' }} />
                  </label>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Weight oz</span>
                    <input type="number" step="0.01" value={form.tiktok_package_weight_oz ?? ''} onChange={(e) => setField('tiktok_package_weight_oz', e.target.value)} style={compactInputStyle} />
                  </label>
                  <label style={{ ...compactLabelStyle, gridColumn: 'span 3' }}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Scent profile</span>
                    <input value={form.tiktok_scent ?? ''} onChange={(e) => setField('tiktok_scent', e.target.value)} style={compactInputStyle} placeholder="Sweet, musk, vanilla" />
                  </label>
                  <label style={{ ...compactLabelStyle, gridColumn: 'span 3' }}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Search keywords</span>
                    <input value={form.tiktok_search_keywords ?? ''} onChange={(e) => setField('tiktok_search_keywords', e.target.value)} style={compactInputStyle} placeholder="Keyword phrases for TikTok search" />
                  </label>
                </div>
              ) : null}

              {channelTab === 'attributes' ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
                  <label style={{ ...compactLabelStyle, gridColumn: 'span 3' }}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Item Name</span>
                    <input value={form.tiktok_item_name ?? ''} onChange={(e) => setField('tiktok_item_name', e.target.value)} style={compactInputStyle} />
                  </label>
                  {[...TIKTOK_KEY_ATTRIBUTES, ...TIKTOK_OPTIONAL_ATTRIBUTES].map(([key, label]) => (
                    <label key={key} style={compactLabelStyle}>
                      <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>{label}</span>
                      <input value={form[key] ?? ''} onChange={(e) => setField(key, e.target.value)} style={compactInputStyle} />
                    </label>
                  ))}
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Size (oz)</span>
                    <input type="number" step="0.01" value={form.size_oz} onChange={(e) => setField('size_oz', e.target.value)} style={compactInputStyle} />
                  </label>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Size (mL)</span>
                    <input type="number" step="0.01" value={form.size_ml} onChange={(e) => setField('size_ml', e.target.value)} style={compactInputStyle} />
                  </label>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Volume (oz)</span>
                    <input type="number" step="0.01" value={form.volume_oz} onChange={(e) => setField('volume_oz', e.target.value)} style={compactInputStyle} />
                  </label>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Volume (mL)</span>
                    <input type="number" step="0.01" value={form.volume_ml} onChange={(e) => setField('volume_ml', e.target.value)} style={compactInputStyle} />
                  </label>
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Volume</span>
                    <input value={formatSeparateSize({ name: form.name, tiktokVolume: form.tiktok_volume, sizeOz: form.volume_oz || form.size_oz, sizeMl: form.volume_ml || form.size_ml })} readOnly style={{ ...compactInputStyle, background: '#f8fafc', color: '#64748b' }} />
                  </label>
                </div>
              ) : null}

            </section>
          </div>

          <aside style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
            <div className="inventory-editor-rail-card" style={{ borderRadius: 20, padding: '18px 18px 20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Compliance & SDS</div>
                {String(form.tiktok_dangerous_goods_or_hazardous_materials || '') === 'Yes' ? <span className="inventory-editor-glass-chip" style={{ padding: '4px 8px', fontSize: 10 }}>Hazmat</span> : null}
              </div>
              <div style={{ display: 'grid', gap: 14 }}>
                {TIKTOK_COMPLIANCE_FIELDS.map(([key, label]) => (
                  <div key={key} style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>{label}</span>
                    <div role="radiogroup" aria-label={label} style={complianceRadioRowStyle}>
                      {['Yes', 'No'].map((option) => {
                        const active = String(form[key] || '') === option;
                        return (
                          <label key={option} style={complianceRadioPillStyle(active)}>
                            <input
                              type="radio"
                              name={key}
                              value={option}
                              checked={active}
                              onChange={() => setField(key, option)}
                              style={{ margin: 0 }}
                            />
                            {option}
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ))}
                {String(form.tiktok_dangerous_goods_or_hazardous_materials || '') === 'Yes' ? (
                  <label style={compactLabelStyle}>
                    <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>SDS PDF</span>
                    <div style={{ display: 'grid', gap: 10 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 10, alignItems: 'center' }}>
                        <button
                          type="button"
                          onClick={() => {
                            if (currentSdsPreviewUrl) window.open(currentSdsPreviewUrl, '_blank', 'noopener,noreferrer');
                          }}
                          disabled={!currentSdsPreviewUrl}
                          style={{
                            minHeight: 40,
                            padding: '0 14px',
                            borderRadius: 10,
                            border: '1px solid #d7dde7',
                            background: currentSdsPreviewUrl ? '#f8fafc' : '#f6f6f9',
                            color: currentSdsPreviewUrl ? '#334155' : '#94a3b8',
                            fontSize: 12,
                            fontWeight: 600,
                            textAlign: 'center',
                            cursor: currentSdsPreviewUrl ? 'pointer' : 'not-allowed',
                          }}
                        >
                          {currentSdsPreviewUrl ? 'Preview PDF' : 'No PDF attached'}
                        </button>
                        <label style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', minHeight: 40, padding: '0 14px', borderRadius: 10, border: '1px solid #d7dde7', background: '#fff', color: '#334155', fontSize: 12, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                          Upload PDF
                          <input type="file" accept="application/pdf,.pdf" onChange={(e) => handleSdsFile(e.target.files?.[0])} style={{ display: 'none' }} />
                        </label>
                      </div>
                      <div style={{ border: '1.5px dashed rgba(99,102,241,0.24)', borderRadius: 16, background: 'linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%)', padding: '18px 16px', textAlign: 'center', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.72)' }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#334155' }}>Drag and drop SDS PDF here</div>
                        <div style={{ marginTop: 6, fontSize: 11, color: '#64748b' }}>You can also drop the PDF anywhere in this product editor. It will be stored on this server when you save.</div>
                      </div>
                    </div>
                    {form.sds_pdf_filename ? (
                      <span style={{ fontSize: 11, color: '#64748b' }}>Selected: {form.sds_pdf_filename}</span>
                    ) : currentSdsPreviewUrl ? (
                      <span style={{ fontSize: 11, color: '#64748b' }}>Attached PDF ready to preview.</span>
                    ) : null}
                  </label>
                ) : null}
              </div>
            </div>

            <div className="inventory-editor-rail-card" style={{ borderRadius: 20, padding: '18px 18px 20px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Notes</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Quick note</span>
                  <textarea value={form.notes} onChange={(e) => setField('notes', e.target.value)} rows={3} style={{ ...compactTextareaStyle, minHeight: 52 }} />
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#4a4a5a', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={!!form.notes_verified}
                    onChange={(e) => setForm((current) => ({
                      ...current,
                      notes_verified: e.target.checked,
                      notes_verified_at: e.target.checked ? (current.notes_verified_at || new Date().toISOString()) : '',
                    }))}
                    style={{ width: 14, height: 14 }}
                  />
                  Notes verified
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Top notes</span>
                  <input value={form.note_top} onChange={(e) => setField('note_top', e.target.value)} style={compactInputStyle} />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Mid notes</span>
                  <input value={form.note_mid} onChange={(e) => setField('note_mid', e.target.value)} style={compactInputStyle} placeholder="—" />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Base notes</span>
                  <input value={form.note_base} onChange={(e) => setField('note_base', e.target.value)} style={compactInputStyle} placeholder="—" />
                </label>
              </div>
            </div>

            <div className="inventory-editor-rail-card" style={{ borderRadius: 20, padding: '18px 18px 20px' }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Assistant</div>
              <div style={{ display: 'grid', gap: 8 }}>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Inspired by / similar to</span>
                  <input value={form.dupe_inspiration} onChange={(e) => setField('dupe_inspiration', e.target.value)} style={compactInputStyle} placeholder="—" />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Classification</span>
                  <input value={form.dupe_classification} onChange={(e) => setField('dupe_classification', e.target.value)} style={compactInputStyle} placeholder="—" />
                </label>
                <label style={compactLabelStyle}>
                  <span style={{ fontSize: 11, color: '#8a8a9a', fontWeight: 500 }}>Notes</span>
                  <textarea value={form.dupe_notes} onChange={(e) => setField('dupe_notes', e.target.value)} rows={4} style={{ ...compactTextareaStyle, minHeight: 68 }} placeholder="—" />
                </label>
              </div>
            </div>
          </aside>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 20px', background: '#ffffff', borderTop: '1px solid #e2e2ea', flexShrink: 0 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#0a0a0f' }}>{exactInventoryName(form) || friendlyInventoryName({ name: form.name, brand: form.brand }) || form.name || 'Product'}</div>
            <div style={{ fontSize: 11, color: '#8a8a9a', marginTop: 2 }}>{completionScore}% complete · {fmtQty(qty)} in stock · {margin ? `${margin}% margin` : 'margin not set'}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {!isNew ? <GhostBtn onClick={handleNext} disabled={!canNext}>Next →</GhostBtn> : null}
            <button onClick={handleClose} className="btn-3d btn-3d-ghost" style={{ padding: '7px 16px', color: '#c0392b' }}>Discard</button>
            <PrimaryBtn onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save product'}</PrimaryBtn>
          </div>
        </div>
      </div>
    </FullPageForm>
  );
}

// ─── Category Manager ────────────────────────────────────────────────────────

function CategoryManager({ onClose, onCategoriesChanged }) {
  const [categories, setCategories] = useState(null);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function load() {
    fetchApi('/api/inventory/categories')
      .then((data) => setCategories(data.rows || []))
      .catch(() => setCategories([]));
  }

  useEffect(() => { load(); }, []);

  async function handleCreate() {
    if (!newName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await postApi('/api/inventory/categories', { name: newName.trim() });
      setNewName('');
      load();
      onCategoriesChanged?.();
    } catch (err) {
      setError(err.message || 'Failed to create category.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id, name) {
    if (!confirm(`Delete category "${name}"? Products in this category will become uncategorized.`)) return;
    try {
      await postApi('/api/inventory/categories/delete', { id });
      load();
      onCategoriesChanged?.();
    } catch (err) {
      setError(err.message || 'Failed to delete category.');
    }
  }

  return (
    <FullPageForm title="Manage Categories" sub="Create and delete product categories" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        <fieldset style={{ border: '1px solid var(--border-default)', borderRadius: 10, padding: '0 20px 20px' }}>
          <legend style={{ padding: '0 8px', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>New Category</legend>
          <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              placeholder="Category name…"
              style={{ ...inputStyle, flex: 1 }}
            />
            <PrimaryBtn onClick={handleCreate} disabled={saving || !newName.trim()}>
              {saving ? 'Adding…' : 'Add Category'}
            </PrimaryBtn>
          </div>
          {error && <div style={{ marginTop: 8, fontSize: 13, color: 'var(--accent-coral)' }}>{error}</div>}
        </fieldset>

        <div style={{ border: '1px solid var(--border-default)', borderRadius: 10, overflow: 'hidden' }}>
          <div style={{ padding: '12px 18px', background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)', fontSize: 11, fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {categories ? `${categories.length} Categor${categories.length === 1 ? 'y' : 'ies'}` : 'Categories'}
          </div>
          {!categories ? (
            <div style={{ padding: 24, color: 'var(--text-secondary)', fontSize: 13 }}>Loading…</div>
          ) : !categories.length ? (
            <div style={{ padding: 24, color: 'var(--text-secondary)', fontSize: 13 }}>No categories yet. Add one above.</div>
          ) : (
            categories.map((cat) => (
              <div key={cat.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 18px', borderTop: '1px solid var(--border-subtle)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>{cat.complete_name || cat.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>ID: {cat.id}</div>
                </div>
                <button
                  onClick={() => handleDelete(cat.id, cat.name)}
                  style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.2)', color: 'var(--accent-coral)', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}
                >
                  Delete
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </FullPageForm>
  );
}

// ─── Vendor List ─────────────────────────────────────────────────────────────

function VendorList({ onClose, onSelectVendor }) {
  const [vendors, setVendors] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchApi('/api/inventory/vendors')
      .then((data) => setVendors(data.rows || []))
      .catch(() => setVendors([]));
  }, []);

  const filtered = useMemo(() => {
    if (!vendors) return [];
    const term = search.trim().toLowerCase();
    if (!term) return vendors;
    return vendors.filter((v) => (v.name || '').toLowerCase().includes(term));
  }, [vendors, search]);

  return (
    <FullPageForm title="Vendors / Suppliers" sub="All suppliers with products in inventory" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Search vendors…" />

        {!vendors ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '24px 0' }}>Loading…</div>
        ) : !filtered.length ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '24px 0' }}>No vendors found.</div>
        ) : (
          <TableShell footer={`${filtered.length} vendor${filtered.length === 1 ? '' : 's'}`}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
              <tr>
                {['Supplier', 'Products', 'Active', 'Stock Value'].map((h) => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
                <th style={{ ...thStyle, textAlign: 'center' }}>Filter</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((v) => (
                <tr key={v.name} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '10px 14px', fontWeight: 700, fontSize: 14 }}>{v.name}</td>
                  <td style={{ padding: '10px 14px' }}>{v.product_count}</td>
                  <td style={{ padding: '10px 14px' }}>{v.active_count}</td>
                  <td style={{ padding: '10px 14px', color: 'var(--accent-amber)', fontWeight: 700 }}>{fmt(v.stock_value)}</td>
                  <td style={{ padding: '10px 14px', textAlign: 'center' }}>
                    <GhostBtn onClick={() => { onSelectVendor(v.name); onClose(); }}>View Products</GhostBtn>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableShell>
        )}
      </div>
    </FullPageForm>
  );
}

function StockAdjustmentPanel({ product, onClose, onSaved }) {
  const currentQty = Number(product.qty_available ?? product.on_hand_qty ?? 0);
  const [mode, setMode] = useState('add');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('restock');
  const [customReason, setCustomReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const fieldStyle = {
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

  const computedQty = useMemo(() => {
    const amount = Number(quantity || 0);
    if (!Number.isFinite(amount)) return currentQty;
    if (mode === 'set') return amount;
    if (mode === 'remove') return Math.max(0, currentQty - amount);
    return currentQty + amount;
  }, [currentQty, mode, quantity]);

  async function submitAdjustment() {
    const amount = Number(quantity || 0);
    if (!Number.isFinite(amount) || amount < 0 || (mode !== 'set' && amount === 0)) {
      setError('Enter a valid quantity.');
      return;
    }
    const adjustmentReason = reason === 'other' ? customReason.trim() : reason;
    if (!adjustmentReason) {
      setError('Choose a reason for this stock change.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await postApi('/api/inventory/adjust_stock', {
        product_id: product.id,
        target_qty: computedQty,
        qty_delta: computedQty - currentQty,
        adjustment_reason: adjustmentReason,
      });
      onSaved(result.product || null);
      onClose();
    } catch (err) {
      setError(err.message || 'Stock adjustment failed.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <SlidePanel
      title="Adjust Stock"
      sub={`${cleanName(product.name)} · Current on hand ${fmtQty(currentQty)}`}
      onClose={onClose}
    >
      <div style={{ display: 'grid', gap: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            ['add', 'Add Stock'],
            ['remove', 'Remove Stock'],
            ['set', 'Set Exact Qty'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              style={{
                padding: '8px 12px',
                borderRadius: 999,
                border: '1px solid var(--border-default)',
                background: mode === value ? 'rgba(245,158,11,0.16)' : 'var(--bg-panel)',
                color: mode === value ? 'var(--accent-amber)' : 'var(--text-primary)',
                fontWeight: 700,
                cursor: 'pointer',
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>{mode === 'set' ? 'New Quantity' : 'Adjustment Amount'}</div>
          <input type="number" min="0" step="1" value={quantity} onChange={(event) => setQuantity(event.target.value)} placeholder={mode === 'set' ? String(currentQty) : '0'} style={fieldStyle} />
        </label>
        <div style={{ padding: '12px 14px', borderRadius: 10, border: '1px solid var(--border-default)', background: 'var(--bg-panel)' }}>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Resulting on hand quantity</div>
          <div style={{ fontSize: 24, fontWeight: 800, marginTop: 6, color: computedQty <= 0 ? 'var(--accent-coral)' : 'var(--text-primary)' }}>{fmtQty(computedQty)}</div>
        </div>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Reason</div>
          <select value={reason} onChange={(event) => setReason(event.target.value)} style={fieldStyle}>
            <option value="restock">Restock</option>
            <option value="cycle_count">Cycle Count</option>
            <option value="damaged">Damaged / Broken</option>
            <option value="missing">Missing / Shrink</option>
            <option value="sample">Sample / Giveaway</option>
            <option value="return">Customer Return</option>
            <option value="correction">Manual Correction</option>
            <option value="other">Other</option>
          </select>
        </label>
        {reason === 'other' ? (
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Custom Reason</div>
            <input value={customReason} onChange={(event) => setCustomReason(event.target.value)} placeholder="Write the reason that should appear in the audit log" style={fieldStyle} />
          </label>
        ) : null}
        {error ? <div style={{ fontSize: 13, color: 'var(--accent-coral)' }}>{error}</div> : null}
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <PrimaryBtn onClick={submitAdjustment} disabled={saving}>{saving ? 'Saving…' : 'Apply Adjustment'}</PrimaryBtn>
          <GhostBtn onClick={onClose}>Cancel</GhostBtn>
        </div>
      </div>
    </SlidePanel>
  );
}

// ─── Main CompanyInventory ────────────────────────────────────────────────────

const inputStyle = {
  background: '#ffffff',
  color: '#0f1729',
  border: '1px solid #e8ecf1',
  borderRadius: 8,
  padding: '8px 12px',
  fontSize: 13,
  fontWeight: 500,
  minHeight: 38,
  lineHeight: 1.2,
  transition: 'border-color 150ms ease, box-shadow 150ms ease',
  outline: 'none',
};

const thStyle = {
  padding: '12px 14px',
  textAlign: 'left',
  color: '#5e6c84',
  fontWeight: 600,
  fontSize: 11,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
  whiteSpace: 'nowrap',
};

const stickyManageHeaderStyle = {
  ...thStyle,
  position: 'sticky',
  right: 0,
  zIndex: 4,
  textAlign: 'center',
  background: '#f8f9fb',
  boxShadow: '-8px 0 16px rgba(15,23,42,0.03)',
  minWidth: 148,
};

const stickyManageCellStyle = {
  padding: '8px 10px',
  textAlign: 'center',
  position: 'sticky',
  right: 0,
  zIndex: 3,
  background: '#ffffff',
  boxShadow: '-8px 0 16px rgba(15,23,42,0.03)',
  minWidth: 148,
};

const SAVED_VIEWS_KEY = 'companyInventory.savedViews.v1';
const INVENTORY_SESSION_KEY = 'companyInventory.filters.v1';
const INVENTORY_ACTIVE_PANEL_KEY = 'companyInventory.activePanel.v1';

function calcMarginPct(row) {
  const retail = Number(row?.list_price || 0);
  const cost = Number(row?.standard_price || 0);
  if (!retail) return null;
  return ((retail - cost) / retail) * 100;
}

function hasFragranceNotes(row) {
  return Boolean(
    String(row?.note_top || '').trim()
    || String(row?.note_mid || '').trim()
    || String(row?.note_base || '').trim()
    || String(row?.notes || '').trim()
  );
}

function daysSince(value) {
  if (!value) return null;
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return null;
  return Math.floor((Date.now() - dt.getTime()) / 86400000);
}

function productHealth(row, duplicateIds = new Set()) {
  const issues = [];
  if (!String(row?.image_url || '').trim()) issues.push('Image');
  if (!String(row?.barcode || '').trim()) issues.push('Barcode');
  if (!hasFragranceNotes(row)) issues.push('Notes');
  if (!row?.notes_verified) issues.push('Verify');
  if (Number(row?.standard_price || 0) <= 0) issues.push('Cost');
  if (Number(row?.list_price || 0) <= 0) issues.push('Retail');
  if (duplicateIds.has(row?.id)) issues.push('Duplicate');
  if (Number(row?.qty_available || 0) <= 0 && row?.type === 'product') issues.push('Out');
  if (row?.low_stock) issues.push('Low');
  const score = Math.max(0, 100 - issues.length * 12);
  if (!issues.length) return { label: 'Complete', tone: 'success', score, issues };
  if (issues.length <= 2) return { label: 'Needs polish', tone: 'warn', score, issues };
  return { label: 'Needs work', tone: 'danger', score, issues };
}

function HealthBadge({ health }) {
  const palette = {
    success: { bg: '#ecfdf3', color: '#047857', dot: '#10b981' },
    warn: { bg: '#fef9ee', color: '#b45309', dot: '#f59e0b' },
    danger: { bg: '#fef2f2', color: '#dc2626', dot: '#ef4444' },
  };
  const p = palette[health.tone] || palette.warn;
  return (
    <span title={health.issues?.length ? health.issues.join(', ') : 'All key fields complete'} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '3px 8px', borderRadius: 6, background: p.bg, color: p.color, fontSize: 11, fontWeight: 600, letterSpacing: '0.01em' }}>
      <span style={{ width: 6, height: 6, borderRadius: 999, background: p.dot }} />
      {health.label}
    </span>
  );
}

export default function CompanyInventory({ initialData = null, initialCategories = null }) {
  const inventoryCacheKey = '/api/inventory?low_stock=3&active=all&pricing_schema=2';
  const categoryCacheKey = '/api/inventory/categories';
  const cachedCategories = getCachedApi(categoryCacheKey, { rows: [] });
  const seedInventory = initialData || { rows: [] };
  const seedCategories = initialCategories || cachedCategories;
  const [uiState, setUiState] = useSessionState(INVENTORY_SESSION_KEY, {
    search: '',
    filterType: '',
    filterCategory: '',
    filterActive: 'all',
    filterVendor: '',
    filterBrand: '',
    filterGender: '',
    showLowOnly: false,
    showBarcodeMissing: false,
    showNoImage: false,
    showNoNotes: false,
    showHighMarginOnly: false,
    showDeadStockOnly: false,
    showDuplicateOnly: false,
    showUnverifiedNotes: false,
    showRecentlySoldOnly: false,
    showNeverSoldOnly: false,
    qtyLessThan: '',
    qtyGreaterThan: '',
    valueLessThan: '',
    valueGreaterThan: '',
    marginGreaterThan: '',
    marginLessThan: '',
    groupByCategory: false,
    sortBy: 'name',
    sortAsc: true,
    viewMode: 'table',
    problemView: '',
    selectedExportFields: DEFAULT_EXPORT_FIELDS,
  });
  const [activePanelState, setActivePanelState] = useSessionState(INVENTORY_ACTIVE_PANEL_KEY, {
    mode: '',
    productId: null,
  });
  const [data, setData] = useState(seedInventory);
  const [categories, setCategories] = useState(seedCategories?.rows || seedCategories || []);
  const [loading, setLoading] = useState(!((seedInventory?.rows || []).length || (seedCategories?.rows || seedCategories || []).length));
  const [search, setSearch] = useState(uiState.search || '');
  const [filterType, setFilterType] = useState(uiState.filterType || '');
  const [filterCategory, setFilterCategory] = useState(uiState.filterCategory || '');
  const [filterActive, setFilterActive] = useState(uiState.filterActive || 'all');
  const [filterVendor, setFilterVendor] = useState(uiState.filterVendor || '');
  const [filterBrand, setFilterBrand] = useState(uiState.filterBrand || '');
  const [filterGender, setFilterGender] = useState(uiState.filterGender || '');
  const [showLowOnly, setShowLowOnly] = useState(!!uiState.showLowOnly);
  const [showBarcodeMissing, setShowBarcodeMissing] = useState(!!uiState.showBarcodeMissing);
  const [showNoImage, setShowNoImage] = useState(!!uiState.showNoImage);
  const [showNoNotes, setShowNoNotes] = useState(!!uiState.showNoNotes);
  const [showHighMarginOnly, setShowHighMarginOnly] = useState(!!uiState.showHighMarginOnly);
  const [showDeadStockOnly, setShowDeadStockOnly] = useState(!!uiState.showDeadStockOnly);
  const [showDuplicateOnly, setShowDuplicateOnly] = useState(!!uiState.showDuplicateOnly);
  const [showUnverifiedNotes, setShowUnverifiedNotes] = useState(!!uiState.showUnverifiedNotes);
  const [showRecentlySoldOnly, setShowRecentlySoldOnly] = useState(!!uiState.showRecentlySoldOnly);
  const [showNeverSoldOnly, setShowNeverSoldOnly] = useState(!!uiState.showNeverSoldOnly);
  const [qtyLessThan, setQtyLessThan] = useState(uiState.qtyLessThan || '');
  const [qtyGreaterThan, setQtyGreaterThan] = useState(uiState.qtyGreaterThan || '');
  const [valueLessThan, setValueLessThan] = useState(uiState.valueLessThan || '');
  const [valueGreaterThan, setValueGreaterThan] = useState(uiState.valueGreaterThan || '');
  const [marginGreaterThan, setMarginGreaterThan] = useState(uiState.marginGreaterThan || '');
  const [marginLessThan, setMarginLessThan] = useState(uiState.marginLessThan || '');
  const [groupByCategory, setGroupByCategory] = useState(!!uiState.groupByCategory);
  const [sortBy, setSortBy] = useState(uiState.sortBy || 'name');
  const [sortAsc, setSortAsc] = useState(uiState.sortAsc !== false);
  const [movementProduct, setMovementProduct] = useState(null);
  const [editProduct, setEditProduct] = useState(null);
  const [detailProduct, setDetailProduct] = useState(null);
  const [showCategoryMgr, setShowCategoryMgr] = useState(false);
  const [showVendors, setShowVendors] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [showBulkEdit, setShowBulkEdit] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState({});
  const [viewMode, setViewMode] = useState(uiState.viewMode || 'table');
  const [problemView, setProblemView] = useState(uiState.problemView || '');
  const [selectedExportFields, setSelectedExportFields] = useState(uiState.selectedExportFields || DEFAULT_EXPORT_FIELDS);
  const [selectedIds, setSelectedIds] = useState([]);
  const [editingRowId, setEditingRowId] = useState(null);
  const [editingDraft, setEditingDraft] = useState(null);
  const [adjustProduct, setAdjustProduct] = useState(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showCategoryRail, setShowCategoryRail] = useState(!!uiState.showCategoryRail);
  const [showMore, setShowMore] = useState(false);
  const [showCostUplifts, setShowCostUplifts] = useState(false);
  const [savedViews, setSavedViews] = useLocalState(SAVED_VIEWS_KEY, []);
  const [lastUndo, setLastUndo] = useState(null);
  const dismissedPanelSignatureRef = useRef('');
  const inventoryLoadingRef = useRef(false);
  const inventoryMutationVersionRef = useRef(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [bulkForm, setBulkForm] = useState({
    brand: '',
    gender: '',
    categ_id: '',
    standard_price: '',
    list_price: '',
    active: '',
    barcode_lines: '',
  });

  const blankProduct = {
    id: null, name: '', default_code: '', barcode: '', categ_id: '', brand: '', gender: '',
    supplier_name: '', storage_bin: '', type: 'product', standard_price: 0,
    raw_cost: 0, cost_plus_12: 0, cost_plus_20: 0,
    list_price: 0, qty_available: 0, low_stock_threshold: 3, active: true,
    notes: '', dupe_inspiration: '', dupe_confidence: '', dupe_classification: '', dupe_notes: '',
    note_top: '', note_mid: '', note_base: '', media_url: '', image_url: null,
  };

  function clearInventoryCaches() {
    clearCachedApiPrefix('/api/inventory');
  }

  function markInventoryMutated() {
    inventoryMutationVersionRef.current += 1;
    clearInventoryCaches();
  }

  useEffect(() => {
    const handleKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && String(event.key || '').toLowerCase() === 'h') {
        event.preventDefault();
        setShowCostUplifts((current) => !current);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  function loadInventory({ append = false, force = false } = {}) {
    if (inventoryLoadingRef.current && !force) return;
    inventoryLoadingRef.current = true;
    setLoadingMore(!!append);
    const activeParam = filterActive === 'all' ? 'all' : filterActive;
    const offset = append ? (data?.rows || []).length : 0;
    const refreshParam = force ? `&refresh=${Date.now()}` : '';
    const inventoryPath = `/api/inventory?low_stock=3&active=${activeParam}&pricing_schema=2&limit=${INVENTORY_PAGE_SIZE}&offset=${offset}${refreshParam}`;
    const loadVersion = inventoryMutationVersionRef.current;
    if (!(data?.rows?.length || categories?.length)) setLoading(true);
    Promise.all([
      fetchApi(inventoryPath).catch(() => ({ ok: false, rows: [] })),
      fetchApi('/api/inventory/categories').catch(() => ({ rows: [] })),
    ])
      .then(([inventory, categoryData]) => {
        if (loadVersion !== inventoryMutationVersionRef.current && !force) return;
        setData((current) => {
          if (inventory?.ok === false) return current;
          if (!append) return inventory;
          const existingRows = current?.rows || [];
          const seen = new Set(existingRows.map((row) => row.id));
          const nextRows = [
            ...existingRows,
            ...(inventory.rows || []).filter((row) => !seen.has(row.id)),
          ];
          return { ...inventory, rows: nextRows };
        });
        setCategories(categoryData.rows || []);
        if (activeParam === 'all' && !append) setCachedApi(inventoryCacheKey, inventory);
        setCachedApi(categoryCacheKey, categoryData);
      })
      .finally(() => {
        inventoryLoadingRef.current = false;
        setLoadingMore(false);
        setLoading(false);
      });
  }

  useEffect(() => {
    const timer = window.setTimeout(() => loadInventory(), 0);
    return () => window.clearTimeout(timer);
    // Inventory reload is intentionally keyed to the active-state filter only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterActive]);

  useEffect(() => {
    setUiState({
      search,
      filterType,
      filterCategory,
      filterActive,
      filterVendor,
      filterBrand,
      filterGender,
      showLowOnly,
      showBarcodeMissing,
      showNoImage,
      showNoNotes,
      showHighMarginOnly,
      showDeadStockOnly,
      showDuplicateOnly,
      showUnverifiedNotes,
      showRecentlySoldOnly,
      showNeverSoldOnly,
      qtyLessThan,
      qtyGreaterThan,
      valueLessThan,
      valueGreaterThan,
      marginGreaterThan,
      marginLessThan,
      groupByCategory,
      sortBy,
      sortAsc,
      viewMode,
      problemView,
      selectedExportFields,
      showCategoryRail,
    });
  }, [
    filterActive,
    filterBrand,
    filterCategory,
    filterGender,
    filterType,
    filterVendor,
    groupByCategory,
    search,
    selectedExportFields,
    setUiState,
    showCategoryRail,
    showBarcodeMissing,
    showDeadStockOnly,
    showDuplicateOnly,
    showHighMarginOnly,
    showLowOnly,
    showNoImage,
    showNoNotes,
    showNeverSoldOnly,
    showRecentlySoldOnly,
    showUnverifiedNotes,
    sortAsc,
    sortBy,
    viewMode,
    qtyGreaterThan,
    qtyLessThan,
    valueGreaterThan,
    valueLessThan,
    marginGreaterThan,
    marginLessThan,
    problemView,
  ]);

  useEffect(() => {
    if (editProduct?.id) {
      setActivePanelState({ mode: 'edit', productId: editProduct.id });
      return;
    }
    if (detailProduct?.id) {
      setActivePanelState({ mode: 'detail', productId: detailProduct.id });
      return;
    }
    setActivePanelState({ mode: '', productId: null });
  }, [detailProduct, editProduct, setActivePanelState]);

  const duplicateIds = useMemo(() => {
    const nameMap = new Map();
    const barcodeMap = new Map();
    for (const row of (data.rows || [])) {
      const nameKey = normalizeName(row.name);
      if (nameKey) {
        if (!nameMap.has(nameKey)) nameMap.set(nameKey, []);
        nameMap.get(nameKey).push(row.id);
      }
      const barcodeKey = String(row.barcode || '').trim();
      if (barcodeKey) {
        if (!barcodeMap.has(barcodeKey)) barcodeMap.set(barcodeKey, []);
        barcodeMap.get(barcodeKey).push(row.id);
      }
    }
    const dupes = new Set();
    [...nameMap.values(), ...barcodeMap.values()].forEach((ids) => {
      if (ids.length > 1) ids.forEach((id) => dupes.add(id));
    });
    return dupes;
  }, [data.rows]);

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    let filtered = (data.rows || []).filter((row) => {
      const marginPct = calcMarginPct(row);
      const matchesSearch = !term
        || (row.name || '').toLowerCase().includes(term)
        || (row.default_code || '').toLowerCase().includes(term)
        || (row.barcode || '').toLowerCase().includes(term)
        || (row.categ_name || '').toLowerCase().includes(term)
        || (row.supplier_name || '').toLowerCase().includes(term)
        || (row.brand || '').toLowerCase().includes(term);
      const matchesType = !filterType || row.type === filterType;
      const matchesCategory = !filterCategory
        || (filterCategory === '__uncategorized' ? !row.categ_id : String(row.categ_id || '') === String(filterCategory));
      const matchesVendor = !filterVendor || (row.supplier_name || '').toLowerCase() === filterVendor.toLowerCase();
      const matchesBrand = !filterBrand || (row.brand || '').toLowerCase() === filterBrand.toLowerCase();
      const matchesGender = !filterGender || (row.gender || '').toLowerCase() === filterGender.toLowerCase();
      const matchesLow = !showLowOnly || row.low_stock;
      const matchesBarcodeMissing = !showBarcodeMissing || !String(row.barcode || '').trim();
      const matchesNoImage = !showNoImage || !String(row.image_url || '').trim();
      const matchesNoNotes = !showNoNotes || !hasFragranceNotes(row);
      const matchesUnverifiedNotes = !showUnverifiedNotes || !row.notes_verified;
      const matchesHighMargin = !showHighMarginOnly || ((marginPct ?? -Infinity) >= 25);
      const matchesDeadStock = !showDeadStockOnly || (Number(row.qty_available || 0) > 0 && Number(row.stock_value || 0) > 0 && row.active !== false && !row.low_stock);
      const matchesDuplicate = !showDuplicateOnly || duplicateIds.has(row.id);
      const matchesRecentlySold = !showRecentlySoldOnly || (daysSince(row.last_sold_at) != null && daysSince(row.last_sold_at) <= 14);
      const matchesNeverSold = !showNeverSoldOnly || Number(row.times_sold || 0) <= 0;
      const qty = Number(row.qty_available || 0);
      const value = Number(row.stock_value || 0);
      const matchesQtyLess = qtyLessThan === '' || qty < Number(qtyLessThan);
      const matchesQtyGreater = qtyGreaterThan === '' || qty > Number(qtyGreaterThan);
      const matchesValueLess = valueLessThan === '' || value < Number(valueLessThan);
      const matchesValueGreater = valueGreaterThan === '' || value > Number(valueGreaterThan);
      const matchesMarginGreater = marginGreaterThan === '' || ((marginPct ?? -Infinity) > Number(marginGreaterThan));
      const matchesMarginLess = marginLessThan === '' || ((marginPct ?? Infinity) < Number(marginLessThan));
      const matchesProblemView =
        problemView !== 'out_of_stock'
        || (Number(row.qty_available || 0) <= 0 && row.type === 'product');
      return matchesSearch && matchesType && matchesCategory && matchesVendor && matchesBrand && matchesGender
        && matchesLow && matchesBarcodeMissing && matchesNoImage && matchesNoNotes && matchesUnverifiedNotes
        && matchesHighMargin && matchesDeadStock && matchesDuplicate && matchesRecentlySold && matchesNeverSold
        && matchesQtyLess && matchesQtyGreater && matchesValueLess && matchesValueGreater && matchesMarginGreater
        && matchesMarginLess && matchesProblemView;
    });

    filtered = [...filtered].sort((left, right) => {
      const a = left[sortBy] ?? '';
      const b = right[sortBy] ?? '';
      if (typeof a === 'number' && typeof b === 'number') return sortAsc ? a - b : b - a;
      return sortAsc ? String(a).localeCompare(String(b)) : String(b).localeCompare(String(a));
    });

    return filtered;
  }, [data.rows, duplicateIds, filterBrand, filterCategory, filterGender, filterType, filterVendor, marginGreaterThan, marginLessThan, problemView, qtyGreaterThan, qtyLessThan, search, showBarcodeMissing, showDeadStockOnly, showDuplicateOnly, showHighMarginOnly, showLowOnly, showNeverSoldOnly, showNoImage, showNoNotes, showRecentlySoldOnly, showUnverifiedNotes, sortAsc, sortBy, valueGreaterThan, valueLessThan]);

  useEffect(() => {
    const targetId = Number(activePanelState?.productId || 0);
    if (!targetId || !rows.length) return;
    const rememberedSignature = panelSignature(activePanelState?.mode, targetId);
    if (rememberedSignature && rememberedSignature === dismissedPanelSignatureRef.current) return;
    const match = rows.find((row) => Number(row.id) === targetId) || (data.rows || []).find((row) => Number(row.id) === targetId);
    if (!match) return;
    if (activePanelState?.mode === 'edit' && (!editProduct || Number(editProduct.id) !== targetId)) {
      setEditProduct(match);
      setDetailProduct(null);
    } else if (activePanelState?.mode === 'detail' && (!detailProduct || Number(detailProduct.id) !== targetId)) {
      setDetailProduct(match);
      setEditProduct(null);
    }
  }, [activePanelState, data.rows, detailProduct, editProduct, rows]);
  const editNavigation = useMemo(() => {
    if (!editProduct?.id) {
      return { index: -1, total: rows.length, prev: null, next: null };
    }
    const index = rows.findIndex((row) => row.id === editProduct.id);
    return {
      index,
      total: rows.length,
      prev: index > 0 ? rows[index - 1] : null,
      next: index >= 0 && index < rows.length - 1 ? rows[index + 1] : null,
    };
  }, [editProduct, rows]);

  const brandOptions = useMemo(() => [...new Set((data.rows || []).map((row) => (row.brand || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b)), [data.rows]);
  const genderOptions = useMemo(() => [...new Set((data.rows || []).map((row) => (row.gender || '').trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b)), [data.rows]);
  const selectedRows = useMemo(() => rows.filter((row) => selectedIds.includes(row.id)), [rows, selectedIds]);
  const anomalyCounts = useMemo(() => ({
    missingBarcode: (data.rows || []).filter((row) => !String(row.barcode || '').trim()).length,
    missingImage: (data.rows || []).filter((row) => !String(row.image_url || '').trim()).length,
    missingNotes: (data.rows || []).filter((row) => !hasFragranceNotes(row)).length,
    unverifiedNotes: (data.rows || []).filter((row) => !row.notes_verified).length,
    duplicateCandidates: duplicateIds.size,
    highMargin: (data.rows || []).filter((row) => (calcMarginPct(row) ?? -Infinity) >= 25).length,
    outOfStock: (data.rows || []).filter((row) => Number(row.qty_available || 0) <= 0 && row.type === 'product').length,
    deadStock: (data.rows || []).filter((row) => Number(row.qty_available || 0) > 0 && Number(row.stock_value || 0) > 0 && row.active !== false && !row.low_stock).length,
    recentlySold: (data.rows || []).filter((row) => daysSince(row.last_sold_at) != null && daysSince(row.last_sold_at) <= 14).length,
    neverSold: (data.rows || []).filter((row) => Number(row.times_sold || 0) <= 0).length,
  }), [data.rows, duplicateIds]);

  const visibleStockValue = rows.reduce((sum, row) => sum + (row.stock_value || 0), 0);

  const categoryGroups = useMemo(() => {
    const groups = new Map();
    rows.forEach((row) => {
      const name = row.categ_name || 'Uncategorized';
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(row);
    });
    return [...groups.entries()]
      .map(([name, items]) => ({
        name, items,
        count: items.length,
        qty: items.reduce((sum, item) => sum + Number(item.qty_available || 0), 0),
        value: items.reduce((sum, item) => sum + Number(item.stock_value || 0), 0),
        lowStock: items.filter((item) => item.low_stock).length,
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [rows]);

  const categoryTree = useMemo(() => {
    const stats = new Map();
    (data.rows || []).forEach((row) => {
      const key = row.categ_id ? String(row.categ_id) : '__uncategorized';
      const current = stats.get(key) || { count: 0, qty: 0, value: 0 };
      current.count += 1;
      current.qty += Number(row.qty_available || 0);
      current.value += Number(row.stock_value || 0);
      stats.set(key, current);
    });

    const root = [];
    const rootIndex = new Map();
    const ensureNode = (container, index, key, label, id = null) => {
      if (index.has(key)) {
        const existing = index.get(key);
        if (id != null) existing.id = id;
        return existing;
      }
      const node = { key, id, label, count: 0, qty: 0, value: 0, children: [], childIndex: new Map() };
      container.push(node);
      index.set(key, node);
      return node;
    };

    (categories || []).forEach((category) => {
      const path = String(category.complete_name || category.name || 'Uncategorized')
        .split(/\s*\/\s*/)
        .map((part) => part.trim())
        .filter(Boolean);
      if (!path.length) path.push(category.name || 'Uncategorized');
      let container = root;
      let index = rootIndex;
      let pathKey = '';
      path.forEach((part, partIndex) => {
        pathKey = pathKey ? `${pathKey}/${part}` : part;
        const isLeaf = partIndex === path.length - 1;
        const node = ensureNode(container, index, pathKey, part, isLeaf ? category.id : null);
        if (isLeaf) {
          const directStats = stats.get(String(category.id)) || { count: 0, qty: 0, value: 0 };
          node.count += directStats.count;
          node.qty += directStats.qty;
          node.value += directStats.value;
        }
        container = node.children;
        index = node.childIndex;
      });
    });

    const uncategorizedStats = stats.get('__uncategorized') || { count: 0, qty: 0, value: 0 };
    if (uncategorizedStats.count) {
      root.push({
        key: '__uncategorized',
        id: '__uncategorized',
        label: 'Uncategorized',
        count: uncategorizedStats.count,
        qty: uncategorizedStats.qty,
        value: uncategorizedStats.value,
        children: [],
        childIndex: new Map(),
      });
    }

    function rollup(node) {
      node.children.sort((a, b) => a.label.localeCompare(b.label));
      node.children.forEach(rollup);
      node.children.forEach((child) => {
        node.count += child.count;
        node.qty += child.qty;
        node.value += child.value;
      });
      delete node.childIndex;
    }

    root.sort((a, b) => a.label.localeCompare(b.label));
    root.forEach(rollup);
    return root;
  }, [categories, data.rows]);

  const exportFieldOptions = useMemo(() => {
    const fieldSet = new Set(DEFAULT_EXPORT_FIELDS);
    (data?.rows || []).forEach((row) => {
      Object.keys(row || {}).forEach((key) => fieldSet.add(key));
    });
    return [...fieldSet]
      .sort((a, b) => a.localeCompare(b))
      .map((key) => ({ key, label: prettifyFieldName(key) }));
  }, [data?.rows]);

  function toggleSort(column) {
    if (sortBy === column) { setSortAsc((value) => !value); return; }
    setSortBy(column);
    setSortAsc(column === 'name');
  }

  function toggleCategoryGroup(name) {
    setExpandedCategories((current) => ({ ...current, [name]: current[name] === false }));
  }

  function renderCategoryNode(node, depth = 0) {
    const selected = String(filterCategory || '') === String(node.id || '');
    const hasChildren = node.children?.length > 0;
    const canSelect = node.id != null;
    const button = (
      <button
        key={`${node.key}-button`}
        type="button"
        onClick={() => canSelect && setFilterCategory(selected ? '' : String(node.id))}
        disabled={!canSelect}
        style={{
          width: '100%',
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) auto',
          gap: 8,
          alignItems: 'center',
          border: selected ? '1px solid rgba(245,158,11,0.42)' : '1px solid transparent',
          borderRadius: 12,
          padding: '8px 9px',
          paddingLeft: 9 + depth * 14,
          background: selected ? 'linear-gradient(90deg, rgba(245,158,11,0.16), rgba(245,158,11,0.05))' : 'transparent',
          color: canSelect ? 'var(--text-primary)' : 'var(--text-secondary)',
          cursor: canSelect ? 'pointer' : 'default',
          textAlign: 'left',
        }}
      >
        <span style={{ minWidth: 0 }}>
          <span style={{ display: 'block', fontSize: 13, fontWeight: selected ? 900 : 750, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {hasChildren ? '▾ ' : ''}{node.label}
          </span>
          <span style={{ display: 'block', marginTop: 2, fontSize: 11, color: 'var(--text-secondary)' }}>
            {fmtQty(node.qty)} units · {fmt(node.value)}
          </span>
        </span>
        <span style={{ justifySelf: 'end', minWidth: 28, textAlign: 'center', padding: '3px 7px', borderRadius: 999, background: selected ? 'rgba(245,158,11,0.22)' : 'var(--bg-elevated)', color: selected ? 'var(--accent-amber)' : 'var(--text-secondary)', fontSize: 11, fontWeight: 900 }}>
          {node.count}
        </span>
      </button>
    );

    return (
      <div key={node.key}>
        {button}
        {hasChildren ? (
          <div style={{ display: 'grid', gap: 2, marginTop: 2 }}>
            {node.children.map((child) => renderCategoryNode(child, depth + 1))}
          </div>
        ) : null}
      </div>
    );
  }

  function renderCategoryRail() {
    const allSelected = !filterCategory;
    return (
      <aside style={{ position: 'sticky', top: 86, alignSelf: 'start', width: 220, border: '1px solid var(--border-default)', borderRadius: 18, background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94))', boxShadow: '0 18px 44px rgba(15,23,42,0.07)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 14px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Category Tree</div>
              <div style={{ marginTop: 4, fontSize: 18, fontWeight: 900, letterSpacing: '-0.03em' }}>Browse Stock</div>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <button
                type="button"
                onClick={() => setShowCategoryRail(false)}
                title="Hide category rail"
                style={{ width: 30, height: 30, borderRadius: 10, border: '1px solid rgba(148,163,184,0.18)', background: '#fff', color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 900 }}
              >
                ×
              </button>
              <button
                type="button"
                onClick={() => setShowCategoryMgr(true)}
                title="Manage categories"
                style={{ width: 30, height: 30, borderRadius: 10, border: '1px solid rgba(148,163,184,0.18)', background: '#fff', color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 900 }}
              >
                +
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setFilterCategory('')}
            style={{ marginTop: 12, width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', border: allSelected ? '1px solid rgba(245,158,11,0.42)' : '1px solid rgba(148,163,184,0.14)', borderRadius: 14, padding: '10px 11px', background: allSelected ? 'rgba(245,158,11,0.12)' : '#fff', color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 900 }}
          >
            <span>All Products</span>
            <span style={{ fontSize: 12, color: allSelected ? 'var(--accent-amber)' : 'var(--text-secondary)' }}>{data.rows?.length || 0}</span>
          </button>
        </div>
        <div style={{ maxHeight: 'calc(100vh - 250px)', overflow: 'auto', padding: 10, display: 'grid', gap: 4 }}>
          {categoryTree.length ? (
            categoryTree.map((node) => renderCategoryNode(node))
          ) : (
            <div style={{ padding: 14, color: 'var(--text-secondary)', fontSize: 13 }}>No categories yet.</div>
          )}
        </div>
      </aside>
    );
  }

  function toggleExportField(field) {
    setSelectedExportFields((current) => (
      current.includes(field)
        ? current.filter((value) => value !== field)
        : [...current, field]
    ));
  }

  function toggleSelected(rowId) {
    setSelectedIds((current) => current.includes(rowId) ? current.filter((id) => id !== rowId) : [...current, rowId]);
  }

  function closeRememberedPanel() {
    dismissedPanelSignatureRef.current = panelSignature(
      editProduct?.id ? 'edit' : detailProduct?.id ? 'detail' : activePanelState?.mode,
      editProduct?.id || detailProduct?.id || activePanelState?.productId,
    );
    setActivePanelState({ mode: '', productId: null });
    setEditProduct(null);
    setDetailProduct(null);
  }

  function openDetailPanel(row) {
    dismissedPanelSignatureRef.current = '';
    const productId = row?.id || null;
    setActivePanelState({ mode: productId ? 'detail' : '', productId });
    setEditProduct(null);
    setDetailProduct(row || null);
  }

  function openEditPanel(row) {
    dismissedPanelSignatureRef.current = '';
    const productId = row?.id || null;
    setActivePanelState({ mode: productId ? 'edit' : '', productId });
    setDetailProduct(null);
    setEditProduct(row || null);
  }

  function toggleSelectAllVisible() {
    const visibleIds = rows.map((row) => row.id);
    setSelectedIds((current) => (
      visibleIds.every((id) => current.includes(id))
        ? current.filter((id) => !visibleIds.includes(id))
        : [...new Set([...current, ...visibleIds])]
    ));
  }

  function startInlineEdit(row) {
    setEditingRowId(row.id);
    setEditingDraft({
      id: row.id,
      name: row.name || '',
      default_code: row.default_code || '',
      barcode: row.barcode || '',
      categ_id: row.categ_id || '',
      brand: row.brand || '',
      gender: row.gender || '',
      type: row.type || 'product',
      active: row.active !== false,
      qty_available: row.qty_available ?? 0,
      standard_price: row.standard_price ?? 0,
      raw_cost: row.raw_cost ?? 0,
      cost_plus_12: row.cost_plus_12 ?? 0,
      cost_plus_20: row.cost_plus_20 ?? 0,
      list_price: row.list_price ?? 0,
    });
  }

  function updateInlineDraft(field, value) {
    setEditingDraft((current) => ({ ...current, [field]: value }));
  }

  function cancelInlineEdit() {
    setEditingRowId(null);
    setEditingDraft(null);
  }

  async function saveInlineEdit(row) {
    if (!editingDraft || editingDraft.id !== row.id) return;
    const previous = { ...row };
    const payload = {
      product_id: row.id,
      name: editingDraft.name,
      default_code: editingDraft.default_code,
      barcode: editingDraft.barcode,
      categ_id: editingDraft.categ_id || false,
      brand: editingDraft.brand,
      gender: editingDraft.gender,
      type: editingDraft.type,
      active: !!editingDraft.active,
      standard_price: Number(editingDraft.standard_price || 0),
      raw_cost: Number(editingDraft.raw_cost || 0),
      cost_plus_12: Number(editingDraft.cost_plus_12 || 0),
      cost_plus_20: Number(editingDraft.cost_plus_20 || 0),
      list_price: Number(editingDraft.list_price || 0),
    };
    const desiredQty = Number(editingDraft.qty_available || 0);
    const expectedQty = Number(row.qty_available || 0);
    if (Math.abs(desiredQty - expectedQty) > 0.0001) {
      payload.qty_available = desiredQty;
      payload.stock_adjustment_intent = true;
      payload.adjustment_reason = 'inline_stock_edit';
    }
    const result = await postApi('/api/inventory/product/update', payload);
    setLastUndo({ kind: 'update', rows: [previous] });
    handleSaved(result.product || null);
    cancelInlineEdit();
  }

  async function handleUndoLastChange() {
    if (!lastUndo?.rows?.length) return;
    for (const row of lastUndo.rows) {
      await postApi('/api/inventory/product/update', {
        product_id: row.id,
        name: row.name,
        default_code: row.default_code,
        barcode: row.barcode,
        categ_id: row.categ_id || false,
        brand: row.brand,
        gender: row.gender,
        supplier_name: row.supplier_name,
        storage_bin: row.storage_bin,
        type: row.type,
        standard_price: Number(row.standard_price || 0),
        raw_cost: Number(row.raw_cost || 0),
        cost_plus_12: Number(row.cost_plus_12 || 0),
        cost_plus_20: Number(row.cost_plus_20 || 0),
        list_price: Number(row.list_price || 0),
        low_stock_threshold: Number(row.low_stock_threshold || 0),
        active: row.active !== false,
        notes: row.notes,
        dupe_inspiration: row.dupe_inspiration,
        note_top: row.note_top,
        note_mid: row.note_mid,
        note_base: row.note_base,
        media_url: row.media_url,
      });
    }
    setLastUndo(null);
    loadInventory();
  }

  function applySavedView(view) {
    const filters = view?.filters || {};
    setSearch(filters.search || '');
    setFilterType(filters.filterType || '');
    setFilterCategory(filters.filterCategory || '');
    setFilterActive(filters.filterActive || 'all');
    setFilterVendor(filters.filterVendor || '');
    setFilterBrand(filters.filterBrand || '');
    setFilterGender(filters.filterGender || '');
    setShowLowOnly(!!filters.showLowOnly);
    setShowBarcodeMissing(!!filters.showBarcodeMissing);
    setShowNoImage(!!filters.showNoImage);
    setShowNoNotes(!!filters.showNoNotes);
    setShowHighMarginOnly(!!filters.showHighMarginOnly);
    setShowDeadStockOnly(!!filters.showDeadStockOnly);
    setShowDuplicateOnly(!!filters.showDuplicateOnly);
    setShowUnverifiedNotes(!!filters.showUnverifiedNotes);
    setShowRecentlySoldOnly(!!filters.showRecentlySoldOnly);
    setShowNeverSoldOnly(!!filters.showNeverSoldOnly);
    setQtyLessThan(filters.qtyLessThan || '');
    setQtyGreaterThan(filters.qtyGreaterThan || '');
    setValueLessThan(filters.valueLessThan || '');
    setValueGreaterThan(filters.valueGreaterThan || '');
    setMarginGreaterThan(filters.marginGreaterThan || '');
    setMarginLessThan(filters.marginLessThan || '');
    setProblemView(filters.problemView || '');
  }

  function saveCurrentView() {
    const name = window.prompt('Saved view name');
    if (!name) return;
    const filters = {
      search,
      filterType,
      filterCategory,
      filterActive,
      filterVendor,
      filterBrand,
      filterGender,
      showLowOnly,
      showBarcodeMissing,
      showNoImage,
      showNoNotes,
      showHighMarginOnly,
      showDeadStockOnly,
      showDuplicateOnly,
      showUnverifiedNotes,
      showRecentlySoldOnly,
      showNeverSoldOnly,
      qtyLessThan,
      qtyGreaterThan,
      valueLessThan,
      valueGreaterThan,
      marginGreaterThan,
      marginLessThan,
      problemView,
    };
    setSavedViews((current) => [...current.filter((view) => view.name !== name), { name, filters }]);
  }

  function clearAllFilters() {
    setSearch('');
    setFilterType('');
    setFilterCategory('');
    setFilterActive('all');
    setFilterVendor('');
    setFilterBrand('');
    setFilterGender('');
    setShowLowOnly(false);
    setShowBarcodeMissing(false);
    setShowNoImage(false);
    setShowNoNotes(false);
    setShowHighMarginOnly(false);
    setShowDeadStockOnly(false);
    setShowDuplicateOnly(false);
    setShowUnverifiedNotes(false);
    setShowRecentlySoldOnly(false);
    setShowNeverSoldOnly(false);
    setQtyLessThan('');
    setQtyGreaterThan('');
    setValueLessThan('');
    setValueGreaterThan('');
    setMarginGreaterThan('');
    setMarginLessThan('');
    setGroupByCategory(false);
    setProblemView('');
  }

  function activateProblemView(next) {
    setProblemView(next);
    setShowLowOnly(next === 'low_stock');
    setShowBarcodeMissing(next === 'missing_barcode');
    setShowNoImage(next === 'missing_image');
    setShowNoNotes(next === 'missing_notes');
    setShowHighMarginOnly(next === 'high_margin');
    setShowDeadStockOnly(next === 'dead_stock');
    setShowDuplicateOnly(next === 'duplicates');
    setShowUnverifiedNotes(next === 'unverified_notes');
    setShowRecentlySoldOnly(next === 'recently_sold');
    setShowNeverSoldOnly(next === 'never_sold');
  }

  function deleteSavedView(name) {
    setSavedViews((current) => current.filter((view) => view.name !== name));
  }

  async function applyBulkEdit() {
    if (!selectedRows.length) return;
    const previousRows = selectedRows.map((row) => ({ ...row }));
    const barcodeLines = String(bulkForm.barcode_lines || '')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (const [index, row] of selectedRows.entries()) {
      const payload = {
        product_id: row.id,
        name: row.name,
        default_code: row.default_code,
        barcode: barcodeLines[index] ?? row.barcode,
        categ_id: bulkForm.categ_id !== '' ? (bulkForm.categ_id || false) : (row.categ_id || false),
        brand: bulkForm.brand !== '' ? bulkForm.brand : row.brand,
        gender: bulkForm.gender !== '' ? bulkForm.gender : row.gender,
        supplier_name: row.supplier_name,
        storage_bin: row.storage_bin,
        type: row.type,
        standard_price: bulkForm.standard_price !== '' ? Number(bulkForm.standard_price) : Number(row.standard_price || 0),
        list_price: bulkForm.list_price !== '' ? Number(bulkForm.list_price) : Number(row.list_price || 0),
        low_stock_threshold: Number(row.low_stock_threshold || 0),
        active: bulkForm.active === '' ? (row.active !== false) : bulkForm.active === 'true',
        notes: row.notes,
        dupe_inspiration: row.dupe_inspiration,
        note_top: row.note_top,
        note_mid: row.note_mid,
        note_base: row.note_base,
        media_url: row.media_url,
      };
      await postApi('/api/inventory/product/update', payload);
    }
    setLastUndo({ kind: 'bulk', rows: previousRows });
    setShowBulkEdit(false);
    setSelectedIds([]);
    setBulkForm({ brand: '', gender: '', categ_id: '', standard_price: '', list_price: '', active: '', barcode_lines: '' });
    loadInventory();
  }

  async function handleBulkArchive() {
    if (!selectedRows.length || !window.confirm(`Archive ${selectedRows.length} selected product(s)?`)) return;
    const previousRows = selectedRows.map((row) => ({ ...row }));
    for (const row of selectedRows) {
      await postApi('/api/inventory/product/update', {
        product_id: row.id,
        name: row.name,
        default_code: row.default_code,
        barcode: row.barcode,
        categ_id: row.categ_id || false,
        brand: row.brand,
        gender: row.gender,
        supplier_name: row.supplier_name,
        storage_bin: row.storage_bin,
        type: row.type,
        standard_price: Number(row.standard_price || 0),
        list_price: Number(row.list_price || 0),
        low_stock_threshold: Number(row.low_stock_threshold || 0),
        active: false,
        notes: row.notes,
        dupe_inspiration: row.dupe_inspiration,
        note_top: row.note_top,
        note_mid: row.note_mid,
        note_base: row.note_base,
        media_url: row.media_url,
      });
    }
    setLastUndo({ kind: 'archive', rows: previousRows });
    setSelectedIds([]);
    loadInventory();
  }

  async function handleBulkDelete() {
    if (!selectedRows.length || !window.confirm(`Hard delete/archive ${selectedRows.length} selected product(s)?`)) return;
    for (const row of selectedRows) {
      await postApi('/api/inventory/product/delete', { product_id: row.id });
    }
    setSelectedIds([]);
    loadInventory();
  }

  function downloadInventoryCsv(sourceRows, suffix) {
    if (!selectedExportFields.length) {
      alert('Select at least one field to export.');
      return;
    }
    const header = selectedExportFields;
    const lines = [
      header.map(csvEscape).join(','),
      ...sourceRows.map((row) => header.map((field) => csvEscape(row?.[field])).join(',')),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
    link.href = url;
    link.download = `inventory_export_${suffix}_${stamp}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setShowExport(false);
  }

  async function handleDelete(row) {
    if (!window.confirm(`Delete "${cleanName(row.name)}"?\n\nThis cannot be undone.`)) return;
    try {
      const result = await postApi('/api/inventory/product/delete', { product_id: row.id });
      setData((current) => {
        const nextRows = (current.rows || []).filter((r) => r.id !== row.id);
        setCachedApi(inventoryCacheKey, { ...current, rows: nextRows, total_products: nextRows.length, total_stock_value: nextRows.reduce((s, r) => s + (r.stock_value || 0), 0), low_stock_count: nextRows.filter((r) => r.low_stock).length });
        return { ...current, rows: nextRows, total_products: nextRows.length, total_stock_value: nextRows.reduce((s, r) => s + (r.stock_value || 0), 0), low_stock_count: nextRows.filter((r) => r.low_stock).length };
      });
      if (result?.archived) {
        alert('This product is linked to historical records, so it was archived and removed from active inventory instead of being permanently deleted.');
      }
    } catch (err) {
      alert(`Delete failed: ${err.message}`);
    }
  }

  async function handleArchiveSingle(row) {
    if (!row?.id || !window.confirm(`Archive "${cleanName(row.name)}"?`)) return;
    try {
      await postApi('/api/inventory/product/update', {
        product_id: row.id,
        name: row.name,
        default_code: row.default_code,
        barcode: row.barcode,
        categ_id: row.categ_id || false,
        brand: row.brand,
        gender: row.gender,
        supplier_name: row.supplier_name,
        storage_bin: row.storage_bin,
        type: row.type,
        standard_price: Number(row.standard_price || 0),
        raw_cost: Number(row.raw_cost || 0),
        cost_plus_12: Number(row.cost_plus_12 || 0),
        cost_plus_20: Number(row.cost_plus_20 || 0),
        list_price: Number(row.list_price || 0),
        low_stock_threshold: Number(row.low_stock_threshold || 0),
        active: false,
        notes: row.notes,
        notes_verified: !!row.notes_verified,
        dupe_inspiration: row.dupe_inspiration,
        dupe_confidence: row.dupe_confidence,
        dupe_classification: row.dupe_classification,
        dupe_notes: row.dupe_notes,
        note_top: row.note_top,
        note_mid: row.note_mid,
        note_base: row.note_base,
        media_url: row.media_url,
      });
      setDetailProduct(null);
      loadInventory();
    } catch (err) {
      alert(`Archive failed: ${err.message}`);
    }
  }

  function handleSaved(updated, options = {}) {
    const closeEditor = options.closeEditor !== false;
    markInventoryMutated();
    if (updated?.id) {
      setData((current) => {
        const currentRows = current.rows || [];
        const existing = currentRows.some((row) => row.id === updated.id);
        const nextRows = existing
          ? currentRows.map((row) => {
              if (row.id !== updated.id) return row;
              const qty = updated.qty_available ?? row.qty_available;
              const cost = updated.standard_price ?? row.standard_price;
              return { ...row, ...updated, stock_value: Number(qty || 0) * Number(cost || 0), low_stock: (updated.type || row.type) === 'product' ? Number(qty || 0) <= Number(updated.low_stock_threshold ?? row.low_stock_threshold ?? 3) : false };
            })
          : [{ ...updated, stock_value: Number(updated.qty_available || 0) * Number(updated.standard_price || 0), low_stock: updated.type === 'product' ? Number(updated.qty_available || 0) <= Number(updated.low_stock_threshold ?? 3) : false }, ...currentRows];
        setCachedApi(inventoryCacheKey, { ...current, rows: nextRows, total_products: nextRows.length, total_stock_value: nextRows.reduce((sum, row) => sum + (row.stock_value || 0), 0), low_stock_count: nextRows.filter((row) => row.low_stock).length });
        return { ...current, rows: nextRows, total_products: nextRows.length, total_stock_value: nextRows.reduce((sum, row) => sum + (row.stock_value || 0), 0), low_stock_count: nextRows.filter((row) => row.low_stock).length };
      });
    }
    if (closeEditor) setEditProduct(null);
    else if (updated) openEditPanel(updated);
    window.setTimeout(() => loadInventory({ force: true }), 0);
  }

  function renderProductRow(row) {
    const isEditing = editingRowId === row.id && editingDraft;
    const isSelected = selectedIds.includes(row.id);
    const marginPct = calcMarginPct(row);
    const health = productHealth(row, duplicateIds);
    const qtyMeta = stockAttentionMeta(row.qty_available);
    const ladder = pricingLadder(row);
    const skuValue = String(row.default_code || row.sku || '').trim();
    return (
      <tr key={row.id} className="company-list-row inventory-premium-row" style={{ borderTop: '1px solid #f1f4f8' }}>
        <td style={{ padding: '10px 8px', textAlign: 'center' }}>
          <input type="checkbox" checked={selectedIds.includes(row.id)} onChange={() => toggleSelected(row.id)} />
        </td>
        <td style={{ padding: '10px 12px', minWidth: 220 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            {row.image_url
              ? <img src={row.image_url} alt="" style={{ width: 34, height: 34, objectFit: 'contain', borderRadius: 8, background: '#fff', border: '1px solid #f1f4f8', flexShrink: 0 }} />
              : <div style={{ width: 34, height: 34, borderRadius: 8, background: '#f8f9fb', border: '1px solid #f1f4f8', display: 'grid', placeItems: 'center', fontSize: 12, color: '#c4cad4', flexShrink: 0 }}>{'\u25a3'}</div>
            }
            <div style={{ minWidth: 0, flex: 1 }}>
              {isEditing ? (
                <>
                  <input className="input" value={editingDraft.name} onChange={(e) => updateInlineDraft('name', e.target.value)} style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 13 }} />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 6, marginTop: 6 }}>
                    <input className="input" value={editingDraft.brand} onChange={(e) => updateInlineDraft('brand', e.target.value)} placeholder="Brand" style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 12 }} />
                    <input className="input" value={editingDraft.default_code} onChange={(e) => updateInlineDraft('default_code', e.target.value)} placeholder="SKU" style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 12 }} />
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0,1fr))', gap: 6, marginTop: 6 }}>
                    <select value={editingDraft.categ_id} onChange={(e) => updateInlineDraft('categ_id', e.target.value)} style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 12 }}>
                      <option value="">Category{'\u2026'}</option>
                      {categories.map((category) => <option key={category.id} value={category.id}>{category.complete_name || category.name}</option>)}
                    </select>
                    <select value={editingDraft.active ? 'true' : 'false'} onChange={(e) => updateInlineDraft('active', e.target.value === 'true')} style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 12 }}>
                      <option value="true">Active</option>
                      <option value="false">Inactive</option>
                    </select>
                  </div>
                  <div style={{ marginTop: 6 }}>
                    <input className="input" value={editingDraft.barcode} onChange={(e) => updateInlineDraft('barcode', e.target.value)} placeholder="Barcode" style={{ ...inputStyle, width: '100%', padding: '6px 8px', fontSize: 12 }} />
                  </div>
                </>
              ) : (
                <>
                  <button title={cleanName(row.name)} onClick={() => openDetailPanel(row)} onDoubleClick={() => startInlineEdit(row)} style={{ background: 'none', border: 'none', padding: 0, margin: 0, color: '#0f1729', fontWeight: 600, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%', textAlign: 'left', fontSize: 12.5, letterSpacing: '-0.01em', lineHeight: 1.3 }}>{exactInventoryName(row) || friendlyInventoryName(row)}</button>
                  <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                    {row.brand ? (
                      <span style={{ fontSize: 11, color: '#64748b', fontWeight: 650, flexShrink: 0 }}>{row.brand}</span>
                    ) : null}
                    {skuValue ? (
                      <button
                        type="button"
                        title={`SKU: ${skuValue}`}
                        onClick={() => navigator.clipboard?.writeText(skuValue).catch(() => {})}
                        style={{
                          minWidth: 0,
                          maxWidth: 190,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          border: '1px solid #e5e7eb',
                          borderRadius: 999,
                          background: '#f8fafc',
                          color: '#475569',
                          padding: '2px 7px',
                          fontSize: 10.5,
                          fontFamily: 'var(--font-mono)',
                          cursor: 'copy',
                        }}
                      >
                        {compactSku(skuValue)}
                      </button>
                    ) : null}
                  </div>
                  <div title={row.categ_name || 'Uncategorized'} style={{ marginTop: 4, fontSize: 10.5, color: '#9aa5b4', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', lineHeight: 1.3 }}>{row.categ_name || 'Uncategorized'}</div>
                  <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', marginTop: 4 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 6px', borderRadius: 6, fontSize: 10, fontWeight: 600, letterSpacing: '0.02em', background: row.active === false ? '#f3f4f6' : '#ecfdf3', color: row.active === false ? '#9aa5b4' : '#047857' }}>{row.active === false ? 'Inactive' : 'Active'}</span>
                    <HealthBadge health={health} />
                    {row.low_stock ? <span style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 6px', borderRadius: 6, fontSize: 10, fontWeight: 600, background: '#fef2f2', color: '#dc2626' }}>Low</span> : null}
                  </div>
                </>
              )}
            </div>
          </div>
        </td>
        <td style={{ padding: '10px 10px', minWidth: 118 }}>
          {isEditing ? (
            <input className="input" value={editingDraft.barcode} onChange={(e) => updateInlineDraft('barcode', e.target.value)} style={{ ...inputStyle, width: 132, padding: '6px 8px', fontSize: 12, fontFamily: 'var(--font-mono)' }} />
          ) : (
            <span onDoubleClick={() => startInlineEdit(row)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: row.barcode ? '#5e6c84' : '#b8c0cc' }}>
              {row.barcode || '—'}
            </span>
          )}
        </td>
        <td style={{ padding: '10px 10px', textAlign: 'right', fontWeight: 600, color: qtyMeta.label ? '#ef4444' : '#0f1729', minWidth: 70 }}>
          {isEditing ? <input className="input" type="number" value={editingDraft.qty_available} onChange={(e) => updateInlineDraft('qty_available', e.target.value)} style={{ ...inputStyle, width: 90, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : (
            <span onDoubleClick={() => startInlineEdit(row)} style={{ minWidth: 50, display: 'inline-block', textAlign: 'right' }}>
              {fmtQty(row.qty_available)}
            </span>
          )}
        </td>
        <td style={{ padding: '10px 10px', textAlign: 'right', color: '#5e6c84', minWidth: 78 }}>
          {isEditing ? <input className="input" type="number" step="0.01" value={editingDraft.standard_price} onChange={(e) => updateInlineDraft('standard_price', e.target.value)} style={{ ...inputStyle, width: 100, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : <span onDoubleClick={() => startInlineEdit(row)}>{fmt(row.standard_price)}</span>}
        </td>
        <td style={{ padding: '10px 10px', textAlign: 'right', color: '#64748b', minWidth: 78 }}>
          {isEditing ? <input className="input" type="number" step="0.01" value={editingDraft.raw_cost} onChange={(e) => updateInlineDraft('raw_cost', e.target.value)} style={{ ...inputStyle, width: 100, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : <span onDoubleClick={() => startInlineEdit(row)}>{fmt(ladder.raw)}</span>}
        </td>
        {showCostUplifts ? (
          <>
            <td style={{ padding: '10px 10px', textAlign: 'right', color: '#64748b', minWidth: 78 }}>
              {isEditing ? <input className="input" type="number" step="0.01" value={editingDraft.cost_plus_12} onChange={(e) => updateInlineDraft('cost_plus_12', e.target.value)} style={{ ...inputStyle, width: 100, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : <span onDoubleClick={() => startInlineEdit(row)}>{fmt(ladder.plus12)}</span>}
            </td>
            <td style={{ padding: '10px 10px', textAlign: 'right', color: '#64748b', minWidth: 78 }}>
              {isEditing ? <input className="input" type="number" step="0.01" value={editingDraft.cost_plus_20} onChange={(e) => updateInlineDraft('cost_plus_20', e.target.value)} style={{ ...inputStyle, width: 100, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : <span onDoubleClick={() => startInlineEdit(row)}>{fmt(ladder.plus20)}</span>}
            </td>
          </>
        ) : null}
        <td style={{ padding: '10px 10px', textAlign: 'right', color: '#0f1729', fontWeight: 600, minWidth: 82 }}>
          {isEditing ? <input className="input" type="number" step="0.01" value={editingDraft.list_price} onChange={(e) => updateInlineDraft('list_price', e.target.value)} style={{ ...inputStyle, width: 100, padding: '6px 8px', fontSize: 12, textAlign: 'right' }} /> : <span onDoubleClick={() => startInlineEdit(row)}>{fmt(row.list_price)}</span>}
        </td>
        <td style={{ padding: '10px 10px', textAlign: 'right', color: '#0f1729', fontWeight: 600, minWidth: 84 }}>
          <div>{fmt(row.stock_value)}</div>
          <div style={{ marginTop: 2, fontSize: 10, color: marginPct == null ? '#9aa5b4' : marginPct >= 25 ? '#10b981' : '#5e6c84', fontWeight: 500 }}>
            {marginPct == null ? 'No margin' : `${fmtPct(marginPct)} margin`}
          </div>
        </td>
        <td style={stickyManageCellStyle}>
          <div className="inv-row-actions" style={{ display: 'inline-flex', gap: 4, opacity: (isEditing || isSelected) ? 1 : undefined, flexWrap: 'wrap', justifyContent: 'center' }}>
            {isEditing ? (
              <>
                <PrimaryBtn onClick={() => saveInlineEdit(row)} style={{ padding: '5px 10px' }}>Save</PrimaryBtn>
                <GhostBtn onClick={cancelInlineEdit}>Cancel</GhostBtn>
              </>
            ) : (
              <>
                <Button variant="ghost" size="sm" onClick={() => openDetailPanel(row)} style={{ padding: '4px 8px', fontSize: 11 }}>View</Button>
                <Button variant="ghost" size="sm" onClick={() => setAdjustProduct(row)} style={{ padding: '4px 8px', fontSize: 11 }}>Adj</Button>
                <Button variant="secondary" size="sm" onClick={() => openEditPanel(row)} style={{ padding: '4px 8px', fontSize: 11 }}>Edit</Button>
              </>
            )}
          </div>
        </td>
      </tr>
    );
  }

  function renderKanbanCard(row) {
    const type = typeMeta(row.type);
    const marginPct = calcMarginPct(row);
    const health = productHealth(row, duplicateIds);
    const qtyMeta = stockAttentionMeta(row.qty_available);
    return (
      <div key={row.id} style={{ background: 'linear-gradient(180deg, rgba(255,255,255,0.02), transparent)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', padding: 14, display: 'flex', flexDirection: 'column', gap: 10, boxShadow: '0 12px 30px rgba(0,0,0,0.12)' }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          {row.image_url
            ? <img src={row.image_url} alt="" style={{ width: 56, height: 56, objectFit: 'contain', borderRadius: 8, background: '#fff', flexShrink: 0 }} />
            : <div style={{ width: 56, height: 56, borderRadius: 8, background: 'var(--bg-elevated)', display: 'grid', placeItems: 'center', fontSize: 20, color: 'var(--text-muted)', flexShrink: 0 }}>▪</div>
          }
          <div style={{ flex: 1, minWidth: 0 }}>
            <button title={cleanName(row.name)} onClick={() => openDetailPanel(row)} style={{ background: 'none', border: 'none', padding: 0, margin: 0, color: 'var(--text-primary)', fontWeight: 700, cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', textAlign: 'left', fontSize: 13, lineHeight: 1.4, width: '100%' }}>{exactInventoryName(row) || friendlyInventoryName(row)}</button>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
              {row.brand || 'No brand'}{row.categ_name ? ` · ${row.categ_name}` : ''}
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 5 }}>
              <HealthBadge health={health} />
              {row.low_stock ? <span style={{ display: 'inline-block', fontSize: 10, fontWeight: 700, color: '#fff', background: 'var(--accent-coral)', borderRadius: 999, padding: '2px 7px' }}>LOW STOCK</span> : null}
            </div>
          </div>
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.default_code || '—'}{row.barcode ? ` · ${row.barcode}` : ''}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 999, background: 'rgba(251,191,36,0.10)', color: type.color, fontSize: 10, fontWeight: 700 }}>{type.label}</span>
          <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 999, background: row.active === false ? 'rgba(148,163,184,0.14)' : 'rgba(34,197,94,0.12)', color: row.active === false ? 'var(--text-secondary)' : 'var(--accent-emerald)', fontSize: 10, fontWeight: 700 }}>{row.active === false ? 'Inactive' : 'Active'}</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, borderTop: '1px solid var(--border-subtle)', paddingTop: 10 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>On Hand</div>
            <div style={{ fontWeight: 800, fontSize: 15, color: qtyMeta.color, marginTop: 2 }}>{fmtQty(row.qty_available)}</div>
            {qtyMeta.label ? (
              <div style={{ marginTop: 4, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', padding: '3px 8px', borderRadius: 999, background: qtyMeta.bg, border: qtyMeta.border, fontSize: 10, fontWeight: 900, color: qtyMeta.color, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {qtyMeta.label}
              </div>
            ) : null}
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Cost</div>
            <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-secondary)', marginTop: 2 }}>{fmt(row.standard_price)}</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Retail</div>
            <div style={{ fontWeight: 600, fontSize: 13, marginTop: 2 }}>{fmt(row.list_price)}</div>
          </div>
        </div>
        <div style={{ textAlign: 'center', background: 'var(--bg-elevated)', borderRadius: 8, padding: '6px 0' }}>
          <div style={{ fontSize: 10, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Stock Value</div>
          <div style={{ fontWeight: 800, color: 'var(--accent-amber)', fontSize: 16, marginTop: 2 }}>{fmt(row.stock_value)}</div>
          <div style={{ fontSize: 11, marginTop: 4, color: marginPct == null ? 'var(--text-muted)' : marginPct >= 25 ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>
            {marginPct == null ? 'No margin' : `${fmtPct(marginPct)} margin`}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr)) auto', gap: 6, alignItems: 'center' }}>
          <GhostBtn onClick={() => openDetailPanel(row)} style={{ width: '100%', padding: '7px 10px', fontSize: 12 }}>View</GhostBtn>
          <GhostBtn onClick={() => setAdjustProduct(row)} style={{ width: '100%', padding: '7px 10px', fontSize: 12 }}>Adjust</GhostBtn>
          <div />
          <button
            onClick={() => handleDelete(row)}
            className="btn-3d btn-3d-danger"
            title="Delete"
            aria-label="Delete"
            style={{ width: 36, height: 32, padding: 0, borderRadius: 10, display: 'inline-grid', placeItems: 'center', fontSize: 14 }}
          >
            ×
          </button>
        </div>
        <PrimaryBtn onClick={() => openEditPanel(row)} style={{ width: '100%', padding: '9px 12px', fontSize: 13, fontWeight: 800 }}>
          Edit
        </PrimaryBtn>
      </div>
    );
  }

  // If a sub-panel is open full-screen, render it
  if (showCategoryMgr) return (
    <CategoryManager
      onClose={() => setShowCategoryMgr(false)}
      onCategoriesChanged={() => {
        fetchApi('/api/inventory/categories').then((d) => setCategories(d.rows || [])).catch(() => {});
      }}
    />
  );
  if (showVendors) return (
    <VendorList
      onClose={() => setShowVendors(false)}
      onSelectVendor={(name) => setFilterVendor(name)}
    />
  );
  if (showFilters) return (
    <SlidePanel
      title="Filters"
      sub="Narrow inventory, then save as a view."
      onClose={() => setShowFilters(false)}
    >
      <div style={{ display: 'grid', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Category</div>
            <select value={filterCategory} onChange={(event) => setFilterCategory(event.target.value)} style={inputStyle}>
              <option value="">All Categories</option>
              {categories.map((category) => <option key={category.id} value={category.id}>{category.complete_name || category.name}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Type</div>
            <select value={filterType} onChange={(event) => setFilterType(event.target.value)} style={inputStyle}>
              <option value="">All Types</option>
              <option value="product">Storable</option>
              <option value="consu">Consumable</option>
              <option value="service">Service</option>
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Brand</div>
            <select value={filterBrand} onChange={(event) => setFilterBrand(event.target.value)} style={inputStyle}>
              <option value="">All Brands</option>
              {brandOptions.map((brand) => <option key={brand} value={brand}>{brand}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Gender</div>
            <select value={filterGender} onChange={(event) => setFilterGender(event.target.value)} style={inputStyle}>
              <option value="">All Genders</option>
              {genderOptions.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Status</div>
            <select value={filterActive} onChange={(event) => setFilterActive(event.target.value)} style={inputStyle}>
              <option value="all">All Statuses</option>
              <option value="true">Active Only</option>
              <option value="false">Inactive Only</option>
            </select>
          </label>
          <label>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Sort</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} style={{ ...inputStyle, flex: 1 }}>
                <option value="name">Name</option>
                <option value="qty_available">Qty</option>
                <option value="stock_value">Stock Value</option>
                <option value="standard_price">Cost</option>
                <option value="list_price">Retail</option>
                <option value="brand">Brand</option>
                <option value="categ_name">Category</option>
              </select>
              <button type="button" onClick={() => setSortAsc((v) => !v)} className="btn-3d btn-3d-ghost" style={{ padding: '8px 12px' }}>
                {sortAsc ? 'Asc' : 'Desc'}
              </button>
            </div>
          </label>
        </div>

        <div style={{ padding: 12, borderRadius: 12, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>Toggles</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showLowOnly} onChange={(event) => setShowLowOnly(event.target.checked)} />
              Low stock only
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showDeadStockOnly} onChange={(event) => setShowDeadStockOnly(event.target.checked)} />
              Dead stock only
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showBarcodeMissing} onChange={(event) => setShowBarcodeMissing(event.target.checked)} />
              Barcode missing
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showNoImage} onChange={(event) => setShowNoImage(event.target.checked)} />
              No image
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showNoNotes} onChange={(event) => setShowNoNotes(event.target.checked)} />
              No notes
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showUnverifiedNotes} onChange={(event) => setShowUnverifiedNotes(event.target.checked)} />
              Notes unverified
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showRecentlySoldOnly} onChange={(event) => setShowRecentlySoldOnly(event.target.checked)} />
              Recently sold
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showNeverSoldOnly} onChange={(event) => setShowNeverSoldOnly(event.target.checked)} />
              Never sold
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showHighMarginOnly} onChange={(event) => setShowHighMarginOnly(event.target.checked)} />
              High margin
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={showDuplicateOnly} onChange={(event) => setShowDuplicateOnly(event.target.checked)} />
              Duplicate candidates
            </label>
            <label style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 13, color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={groupByCategory} onChange={(event) => setGroupByCategory(event.target.checked)} />
              Group by category
            </label>
          </div>
        </div>

        <div style={{ padding: 12, borderRadius: 12, background: 'var(--bg-elevated)', border: '1px solid var(--border-default)' }}>
          <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>Advanced Numeric Filters</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
            {[
              ['Qty less than', qtyLessThan, setQtyLessThan, 'e.g. 5'],
              ['Qty greater than', qtyGreaterThan, setQtyGreaterThan, 'e.g. 20'],
              ['Stock value less than', valueLessThan, setValueLessThan, 'e.g. 100'],
              ['Stock value greater than', valueGreaterThan, setValueGreaterThan, 'e.g. 500'],
              ['Margin greater than %', marginGreaterThan, setMarginGreaterThan, 'e.g. 40'],
              ['Margin less than %', marginLessThan, setMarginLessThan, 'e.g. 10'],
            ].map(([label, value, setter, placeholder]) => (
              <label key={label}>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>{label}</div>
                <input
                  type="number"
                  value={value}
                  onChange={(event) => setter(event.target.value)}
                  placeholder={placeholder}
                  style={inputStyle}
                />
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <GhostBtn onClick={() => { setShowVendors(true); setShowFilters(false); }}>Choose Vendor</GhostBtn>
          {filterVendor ? <GhostBtn onClick={() => setFilterVendor('')}>Clear Vendor</GhostBtn> : null}
          <GhostBtn onClick={clearAllFilters}>Clear All</GhostBtn>
          <PrimaryBtn onClick={() => setShowFilters(false)}>Done</PrimaryBtn>
        </div>
      </div>
    </SlidePanel>
  );
  if (showExport) return (
    <SlidePanel
      title="Export Inventory"
      sub="Choose the inventory fields to include in the CSV download."
      onClose={() => setShowExport(false)}
    >
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
        <GhostBtn onClick={() => setSelectedExportFields(exportFieldOptions.map((item) => item.key))}>Select All</GhostBtn>
        <GhostBtn onClick={() => setSelectedExportFields(DEFAULT_EXPORT_FIELDS.filter((field) => exportFieldOptions.some((item) => item.key === field)))}>Default Fields</GhostBtn>
        <GhostBtn onClick={() => setSelectedExportFields([])}>Clear</GhostBtn>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
        Selected {selectedExportFields.length} field{selectedExportFields.length === 1 ? '' : 's'} · Visible rows {rows.length} · Loaded rows {(data?.rows || []).length}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
        {exportFieldOptions.map((item) => (
          <label
            key={item.key}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 12px',
              background: selectedExportFields.includes(item.key) ? 'var(--bg-elevated)' : 'var(--bg-panel)',
              cursor: 'pointer',
              fontSize: 13,
              color: 'var(--text-primary)',
            }}
          >
            <input
              type="checkbox"
              checked={selectedExportFields.includes(item.key)}
              onChange={() => toggleExportField(item.key)}
            />
            <span>{item.label}</span>
          </label>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
        <PrimaryBtn onClick={() => downloadInventoryCsv(rows, 'visible')}>Export Visible Rows</PrimaryBtn>
        <GhostBtn onClick={() => downloadInventoryCsv(data?.rows || [], 'all')}>Export All Loaded Rows</GhostBtn>
      </div>
    </SlidePanel>
  );
  if (showBulkEdit) return (
    <SlidePanel
      title="Bulk Edit Inventory"
      sub={`Update ${selectedRows.length} selected product${selectedRows.length === 1 ? '' : 's'} on this page.`}
      onClose={() => setShowBulkEdit(false)}
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Brand</div>
          <input className="input" value={bulkForm.brand} onChange={(e) => setBulkForm((current) => ({ ...current, brand: e.target.value }))} placeholder="Leave blank to keep current" />
        </label>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Gender</div>
          <select className="input" value={bulkForm.gender} onChange={(e) => setBulkForm((current) => ({ ...current, gender: e.target.value }))}>
            <option value="">Keep current</option>
            {genderOptions.map((gender) => <option key={gender} value={gender}>{gender}</option>)}
          </select>
        </label>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Category</div>
          <select className="input" value={bulkForm.categ_id} onChange={(e) => setBulkForm((current) => ({ ...current, categ_id: e.target.value }))}>
            <option value="">Keep current</option>
            {categories.map((category) => <option key={category.id} value={category.id}>{category.complete_name || category.name}</option>)}
          </select>
        </label>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Status</div>
          <select className="input" value={bulkForm.active} onChange={(e) => setBulkForm((current) => ({ ...current, active: e.target.value }))}>
            <option value="">Keep current</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </label>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Cost</div>
          <input className="input" type="number" step="0.01" value={bulkForm.standard_price} onChange={(e) => setBulkForm((current) => ({ ...current, standard_price: e.target.value }))} placeholder="Leave blank to keep current" />
        </label>
        <label>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Retail</div>
          <input className="input" type="number" step="0.01" value={bulkForm.list_price} onChange={(e) => setBulkForm((current) => ({ ...current, list_price: e.target.value }))} placeholder="Leave blank to keep current" />
        </label>
      </div>
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>Bulk Barcode Assign</div>
        <textarea
          className="input"
          rows={8}
          value={bulkForm.barcode_lines}
          onChange={(e) => setBulkForm((current) => ({ ...current, barcode_lines: e.target.value }))}
          placeholder="Optional: one barcode per line. They will be assigned in the current selected row order."
          style={{ width: '100%', resize: 'vertical' }}
        />
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 18 }}>
        <PrimaryBtn onClick={applyBulkEdit}>Apply Bulk Edit</PrimaryBtn>
        <GhostBtn onClick={() => setShowBulkEdit(false)}>Cancel</GhostBtn>
      </div>
    </SlidePanel>
  );
  if (adjustProduct) return (
    <StockAdjustmentPanel
      product={adjustProduct}
      onClose={() => setAdjustProduct(null)}
      onSaved={handleSaved}
    />
  );
  if (detailProduct) return (
    <ProductDetailPanel
      product={detailProduct}
      onClose={closeRememberedPanel}
      onEdit={openEditPanel}
      onArchive={handleArchiveSingle}
      showCostUplifts={showCostUplifts}
      onAdjust={(row) => {
        setDetailProduct(null);
        setAdjustProduct(row);
      }}
    />
  );
  if (editProduct) return (
    <ProductEditor
      key={editProduct.id || 'new-product'}
      product={editProduct}
      categories={categories}
      onClose={closeRememberedPanel}
      onSaved={(updated) => handleSaved(updated, { closeEditor: false })}
      onPrev={editNavigation.prev ? () => openEditPanel(editNavigation.prev) : undefined}
      onNext={editNavigation.next ? () => openEditPanel(editNavigation.next) : undefined}
      canPrev={!!editNavigation.prev}
      canNext={!!editNavigation.next}
      positionLabel={editNavigation.index >= 0 ? `Product ${editNavigation.index + 1} of ${editNavigation.total}` : `Product editor`}
      showCostUplifts={showCostUplifts}
    />
  );

  const colSpanFull = showCostUplifts ? 11 : 9;
  const inventoryTableColGroup = (
    <colgroup>
      <col style={{ width: 42 }} />
      <col style={{ width: showCostUplifts ? '34%' : '42%' }} />
      <col style={{ width: '12%' }} />
      <col style={{ width: '7%' }} />
      <col style={{ width: '7%' }} />
      <col style={{ width: '7%' }} />
      {showCostUplifts ? (
        <>
          <col style={{ width: '7%' }} />
          <col style={{ width: '7%' }} />
        </>
      ) : null}
      <col style={{ width: '7%' }} />
      <col style={{ width: '7%' }} />
      <col style={{ width: 148 }} />
    </colgroup>
  );
  const activeChips = [];
  const pushChip = (key, label, clear) => activeChips.push({ key, label, clear });
  if (search.trim()) pushChip('search', `Search: ${search.trim()}`, () => setSearch(''));
  if (problemView) pushChip('problemView', `Problem: ${prettifyFieldName(problemView)}`, () => activateProblemView(''));
  if (filterVendor) pushChip('vendor', `Vendor: ${filterVendor}`, () => setFilterVendor(''));
  if (filterBrand) pushChip('brand', `Brand: ${filterBrand}`, () => setFilterBrand(''));
  if (filterGender) pushChip('gender', `Gender: ${filterGender}`, () => setFilterGender(''));
  if (filterType) pushChip('type', `Type: ${filterType}`, () => setFilterType(''));
  if (filterActive !== 'all') pushChip('active', `Status: ${filterActive === 'true' ? 'Active' : 'Inactive'}`, () => setFilterActive('all'));
  if (filterCategory) {
    const name = filterCategory === '__uncategorized'
      ? 'Uncategorized'
      : (categories || []).find((c) => String(c.id) === String(filterCategory))?.complete_name
      || (categories || []).find((c) => String(c.id) === String(filterCategory))?.name
      || filterCategory;
    pushChip('category', `Category: ${name}`, () => setFilterCategory(''));
  }
  if (showLowOnly) pushChip('lowOnly', 'Low stock only', () => setShowLowOnly(false));
  if (showBarcodeMissing) pushChip('barcodeMissing', 'Barcode missing', () => setShowBarcodeMissing(false));
  if (showNoImage) pushChip('noImage', 'No image', () => setShowNoImage(false));
  if (showNoNotes) pushChip('noNotes', 'No notes', () => setShowNoNotes(false));
  if (showUnverifiedNotes) pushChip('unverifiedNotes', 'Unverified notes', () => setShowUnverifiedNotes(false));
  if (showRecentlySoldOnly) pushChip('recentlySold', 'Recently sold', () => setShowRecentlySoldOnly(false));
  if (showNeverSoldOnly) pushChip('neverSold', 'Never sold', () => setShowNeverSoldOnly(false));
  if (showHighMarginOnly) pushChip('highMargin', 'High margin', () => setShowHighMarginOnly(false));
  if (showDeadStockOnly) pushChip('deadStock', 'Dead stock', () => setShowDeadStockOnly(false));
  if (showDuplicateOnly) pushChip('duplicates', 'Duplicate candidates', () => setShowDuplicateOnly(false));
  if (qtyLessThan !== '') pushChip('qtyLessThan', `Qty < ${qtyLessThan}`, () => setQtyLessThan(''));
  if (qtyGreaterThan !== '') pushChip('qtyGreaterThan', `Qty > ${qtyGreaterThan}`, () => setQtyGreaterThan(''));
  if (valueLessThan !== '') pushChip('valueLessThan', `Value < ${fmt(valueLessThan)}`, () => setValueLessThan(''));
  if (valueGreaterThan !== '') pushChip('valueGreaterThan', `Value > ${fmt(valueGreaterThan)}`, () => setValueGreaterThan(''));
  if (marginGreaterThan !== '') pushChip('marginGreaterThan', `Margin > ${marginGreaterThan}%`, () => setMarginGreaterThan(''));
  if (marginLessThan !== '') pushChip('marginLessThan', `Margin < ${marginLessThan}%`, () => setMarginLessThan(''));
  if (groupByCategory) pushChip('groupByCategory', 'Grouped by category', () => setGroupByCategory(false));

  return (
    <div className="stripe-inventory-page">
      <div className="stripe-page-header" style={{ padding: '14px 16px 12px', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div style={{ minWidth: 0 }}>
            <div className="stripe-page-kicker">Inventory</div>
            <div className="stripe-page-title">Products</div>
            <div style={{ marginTop: 4, fontSize: 13, color: '#5e6c84', fontWeight: 400, lineHeight: 1.4 }}>Manage product readiness, stock health, and pricing controls.</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <PrimaryBtn onClick={() => openEditPanel(blankProduct)} style={{ padding: '9px 14px', fontSize: 13 }}>+ New Product</PrimaryBtn>
            <GhostBtn onClick={() => selectedRows.length === 1 ? setAdjustProduct(selectedRows[0]) : null} disabled={selectedRows.length !== 1}>Adjust</GhostBtn>
            <GhostBtn onClick={() => setShowExport(true)}>Export</GhostBtn>
            <GhostBtn onClick={loadInventory}>Refresh</GhostBtn>
            <div style={{ position: 'relative' }}>
              <GhostBtn onClick={() => setShowMore((v) => !v)}>More ▾</GhostBtn>
              {showMore ? (
                <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 8px)', width: 220, background: '#ffffff', border: '1px solid #e8ecf1', borderRadius: 10, boxShadow: '0 4px 16px rgba(15,23,42,0.08), 0 1px 3px rgba(15,23,42,0.04)', padding: 6, zIndex: 50 }}>
                  <button type="button" onClick={() => { setShowFilters(true); setShowMore(false); }} style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', color: '#0f1729', fontSize: 13, fontWeight: 500, transition: 'background 120ms ease' }}>Filters</button>
                  <button type="button" onClick={() => { setShowCategoryMgr(true); setShowMore(false); }} style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', color: '#0f1729', fontSize: 13, fontWeight: 500, transition: 'background 120ms ease' }}>Categories</button>
                  <button type="button" onClick={() => { setShowVendors(true); setShowMore(false); }} style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', color: '#0f1729', fontSize: 13, fontWeight: 500, transition: 'background 120ms ease' }}>Vendors</button>
                  <button type="button" onClick={() => { saveCurrentView(); setShowMore(false); }} style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '10px 12px', borderRadius: 8, cursor: 'pointer', color: '#0f1729', fontSize: 13, fontWeight: 500, transition: 'background 120ms ease' }}>Save View</button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className="stripe-filter-bar">
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <SearchInput value={search} onChange={setSearch} placeholder="Search name, SKU, barcode, supplier…" />
          <select value={problemView} onChange={(event) => activateProblemView(event.target.value)} style={inputStyle}>
            <option value="">All products</option>
            <option value="low_stock">Low stock ({data.low_stock_count || 0})</option>
            <option value="out_of_stock">Out of stock ({anomalyCounts.outOfStock})</option>
            <option value="missing_barcode">Missing barcode ({anomalyCounts.missingBarcode})</option>
            <option value="missing_image">Missing image ({anomalyCounts.missingImage})</option>
            <option value="missing_notes">Missing notes ({anomalyCounts.missingNotes})</option>
            <option value="duplicates">Duplicates ({anomalyCounts.duplicateCandidates})</option>
            <option value="dead_stock">Dead stock ({anomalyCounts.deadStock})</option>
            <option value="recently_sold">Recently sold ({anomalyCounts.recentlySold})</option>
            <option value="never_sold">Never sold ({anomalyCounts.neverSold})</option>
          </select>
          <select value={filterActive} onChange={(event) => setFilterActive(event.target.value)} style={inputStyle}>
            <option value="all">Any status</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
          <div style={{ display: 'inline-flex', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
            <button
              title="Table view"
              onClick={() => setViewMode('table')}
              style={{ background: viewMode === 'table' ? 'rgba(245,158,11,0.18)' : 'var(--bg-panel)', border: 'none', cursor: 'pointer', padding: '7px 10px', display: 'flex', alignItems: 'center', color: viewMode === 'table' ? 'var(--accent-amber)' : 'var(--text-secondary)' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="4" rx="1"/><rect x="3" y="10" width="18" height="4" rx="1"/><rect x="3" y="17" width="18" height="4" rx="1"/></svg>
            </button>
            <button
              title="Kanban view"
              onClick={() => setViewMode('kanban')}
              style={{ background: viewMode === 'kanban' ? 'rgba(245,158,11,0.18)' : 'var(--bg-panel)', border: 'none', borderLeft: '1px solid var(--border-default)', cursor: 'pointer', padding: '7px 10px', display: 'flex', alignItems: 'center', color: viewMode === 'kanban' ? 'var(--accent-amber)' : 'var(--text-secondary)' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="8" rx="1"/><rect x="14" y="3" width="7" height="8" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            </button>
          </div>
          <GhostBtn onClick={() => setShowCategoryRail((value) => !value)}>{showCategoryRail ? 'Hide Categories' : 'Show Categories'}</GhostBtn>
          <GhostBtn onClick={() => setShowFilters(true)}>Filters</GhostBtn>
          <GhostBtn onClick={clearAllFilters}>Clear All</GhostBtn>
        </div>
        {activeChips.length ? (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            {activeChips.map((chip) => (
              <span key={chip.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderRadius: 999, background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.18)', color: 'var(--text-primary)', fontSize: 12, fontWeight: 700 }}>
                {chip.label}
                <button type="button" onClick={chip.clear} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 14, lineHeight: 1 }}>×</button>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="stripe-table-layout" style={{ display: 'grid', gridTemplateColumns: showCategoryRail ? '220px minmax(0,1fr)' : 'minmax(0,1fr)', gap: 12, alignItems: 'start' }}>
        {showCategoryRail ? renderCategoryRail() : null}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>

      {selectedRows.length ? (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', padding: '10px 12px', borderRadius: 10, background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}>
          <strong>{selectedRows.length} selected</strong>
          <GhostBtn onClick={() => setShowBulkEdit(true)}>Bulk Edit</GhostBtn>
          <GhostBtn onClick={handleBulkArchive}>Bulk Archive</GhostBtn>
          <GhostBtn onClick={handleBulkDelete}>Bulk Delete</GhostBtn>
          <GhostBtn onClick={() => downloadInventoryCsv(selectedRows, 'selected')}>Export Selected</GhostBtn>
          {lastUndo ? <GhostBtn onClick={handleUndoLastChange}>Undo Last Change</GhostBtn> : null}
          <GhostBtn onClick={() => setSelectedIds([])}>Clear Selection</GhostBtn>
        </div>
      ) : lastUndo ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '10px 12px', borderRadius: 10, background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Last inventory change can be reverted.</span>
          <GhostBtn onClick={handleUndoLastChange}>Undo Last Change</GhostBtn>
        </div>
      ) : null}

      {savedViews.length ? (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {savedViews.map((view) => (
            <div key={view.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, border: '1px solid var(--border-default)', borderRadius: 999, padding: '4px 8px', background: 'var(--bg-panel)' }}>
              <button onClick={() => applySavedView(view)} style={{ background: 'none', border: 'none', color: 'var(--text-primary)', cursor: 'pointer', fontSize: 12, fontWeight: 700 }}>{view.name}</button>
              <button onClick={() => deleteSavedView(view.name)} style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>×</button>
            </div>
          ))}
        </div>
      ) : null}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, marginTop: 4 }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#5e6c84', letterSpacing: '0.04em', textTransform: 'uppercase' }}>Inventory List</div>
        <div style={{ fontSize: 12, color: '#9aa5b4', fontWeight: 500 }}>
          {rows.length} visible · {(data?.rows || []).length} loaded{data?.total_count ? ` of ${Number(data.total_count).toLocaleString()}` : ''}
        </div>
      </div>
      {groupByCategory ? (
        <div style={{ display: 'grid', gap: 12 }}>
          {categoryGroups.map((group) => {
            const collapsed = expandedCategories[group.name] === false;
            return (
              <div key={group.name} style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', overflow: 'hidden', background: 'var(--bg-panel)' }}>
                <button
                  type="button"
                  onClick={() => toggleCategoryGroup(group.name)}
                  style={{ width: '100%', background: 'linear-gradient(180deg, rgba(255,255,255,0.02), transparent)', border: 'none', borderBottom: collapsed ? 'none' : '1px solid var(--border-subtle)', color: 'inherit', cursor: 'pointer', padding: '14px 16px', display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) repeat(4, auto)', gap: 14, alignItems: 'center', textAlign: 'left' }}
                >
                  <div>
                    <div style={{ fontWeight: 800, fontSize: 15 }}>{group.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>{group.count} product{group.count === 1 ? '' : 's'} · {fmtQty(group.qty)} units</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Stock Value</div>
                    <div style={{ fontWeight: 800, color: 'var(--accent-amber)', marginTop: 4 }}>{fmt(group.value)}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Low Stock</div>
                    <div style={{ fontWeight: 800, color: group.lowStock ? 'var(--accent-coral)' : 'var(--text-secondary)', marginTop: 4 }}>{group.lowStock}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Status</div>
                    <div style={{ fontWeight: 700, marginTop: 4 }}>{collapsed ? 'Collapsed' : 'Expanded'}</div>
                  </div>
                  <div style={{ fontSize: 18, color: 'var(--text-secondary)' }}>{collapsed ? '▸' : '▾'}</div>
                </button>
                {!collapsed ? (
                  viewMode === 'kanban' ? (
                    <div style={{ padding: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                      {group.items.map((row) => renderKanbanCard(row))}
                    </div>
                  ) : (
                    <TableShell footer={`${group.count} product${group.count === 1 ? '' : 's'} in ${group.name}`} tableStyle={{ tableLayout: 'fixed' }} colGroup={inventoryTableColGroup}>
                      <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
                        <tr>
                          <th style={{ ...thStyle, textAlign: 'center', width: 44 }}>
                            <input type="checkbox" checked={group.items.every((row) => selectedIds.includes(row.id)) && group.items.length > 0} onChange={() => {
                              const groupIds = group.items.map((item) => item.id);
                              setSelectedIds((current) => groupIds.every((id) => current.includes(id)) ? current.filter((id) => !groupIds.includes(id)) : [...new Set([...current, ...groupIds])]);
                            }} />
                          </th>
                          <SortTh col="name" label="Product" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} />
                          <th style={thStyle}>Barcode</th>
                          <SortTh col="qty_available" label="On Hand" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                          <SortTh col="standard_price" label="Cost" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                          <SortTh col="raw_cost" label="Raw" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                          {showCostUplifts ? (
                            <>
                              <SortTh col="cost_plus_12" label="+12%" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                              <SortTh col="cost_plus_20" label="+20%" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                            </>
                          ) : null}
                          <SortTh col="list_price" label="Retail" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                          <SortTh col="stock_value" label="Value" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                          <th style={stickyManageHeaderStyle}>Manage</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.items.map((row) => renderProductRow(row))}
                      </tbody>
                    </TableShell>
                  )
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        viewMode === 'kanban' ? (
          loading ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="inv-skeleton-card" style={{ borderRadius: 'var(--radius-xl)', border: '1px solid var(--border-default)', background: 'var(--bg-panel)', padding: 14 }}>
                  <div className="inv-skel" style={{ height: 56, borderRadius: 10, marginBottom: 10 }} />
                  <div className="inv-skel" style={{ height: 14, borderRadius: 8, width: '88%', marginBottom: 8 }} />
                  <div className="inv-skel" style={{ height: 12, borderRadius: 8, width: '62%', marginBottom: 12 }} />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 10 }}>
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                  </div>
                  <div className="inv-skel" style={{ height: 44, borderRadius: 10, marginBottom: 10 }} />
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6 }}>
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                    <div className="inv-skel" style={{ height: 34, borderRadius: 10 }} />
                  </div>
                </div>
              ))}
            </div>
          ) : !rows.length ? (
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '32px 0', textAlign: 'center' }}>No products found.</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
              {rows.map((row) => renderKanbanCard(row))}
            </div>
          )
        ) : (
          <TableShell footer={`${rows.length} product${rows.length === 1 ? '' : 's'} · Visible stock value ${fmt(visibleStockValue)}`} tableStyle={{ tableLayout: 'fixed' }} colGroup={inventoryTableColGroup}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 2, background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-default)' }}>
              <tr>
                <th style={{ ...thStyle, textAlign: 'center', width: 44 }}>
                  <input type="checkbox" checked={rows.length > 0 && rows.every((row) => selectedIds.includes(row.id))} onChange={toggleSelectAllVisible} />
                </th>
                <SortTh col="name" label="Product" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} />
                <th style={thStyle}>Barcode</th>
                <SortTh col="qty_available" label="On Hand" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                <SortTh col="standard_price" label="Cost" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                <SortTh col="raw_cost" label="Raw" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                {showCostUplifts ? (
                  <>
                    <SortTh col="cost_plus_12" label="+12%" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                    <SortTh col="cost_plus_20" label="+20%" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                  </>
                ) : null}
                <SortTh col="list_price" label="Retail" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                <SortTh col="stock_value" label="Value" sortBy={sortBy} sortAsc={sortAsc} onSort={toggleSort} align="right" />
                <th style={stickyManageHeaderStyle}>Manage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td colSpan={colSpanFull} style={{ padding: '10px 14px' }}>
                      <div className="inv-skel" style={{ height: 16, borderRadius: 10, width: `${85 - (i % 5) * 10}%` }} />
                    </td>
                  </tr>
                ))
              ) : rows.length === 0 ? (
                <EmptyRow cols={colSpanFull} loading={false} />
              ) : null}
              {!loading && rows.map((row) => renderProductRow(row))}
            </tbody>
          </TableShell>
        )
      )}
          {data?.has_more ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 0 12px' }}>
              <GhostBtn onClick={() => loadInventory({ append: true })} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : 'Load More Products'}
              </GhostBtn>
            </div>
          ) : null}
        </div>
      </div>

      {movementProduct ? (
        <SlidePanel title="Stock Movements" sub={movementProduct.name} onClose={() => setMovementProduct(null)}>
          <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Use the View button on a product to see stock moves.</div>
        </SlidePanel>
      ) : null}
    </div>
  );
}
