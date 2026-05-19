import { useMemo } from 'react';
import { usePolling } from '../hooks/useApi';

const fmtMoney = (value) => (value == null ? '—' : `$${Number(value).toFixed(2)}`);

function priceOrNull(value) {
  const number = Number(value || 0);
  return number > 0 ? number : null;
}

function buildPricingLadder(product = {}) {
  const cost = priceOrNull(product.cost_price);
  const raw = priceOrNull(product.raw_cost) ?? cost;
  return {
    raw,
    plus12: priceOrNull(product.cost_plus_12) ?? (raw ? raw * 1.12 : null),
    plus20: priceOrNull(product.cost_plus_20) ?? (raw ? raw * 1.2 : null),
  };
}

function splitNotes(value) {
  if (!value) return [];
  return String(value)
    .split(/[,|\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildTile(product = {}, index = 0, fallbackTitle = 'Waiting for scan') {
  const top = splitNotes(product.note_top);
  const mid = splitNotes(product.note_mid);
  const base = splitNotes(product.note_base);
  const dupe = product.dupe_research || null;
  const pricing = buildPricingLadder(product);
  const inventoryQty = Number(product.on_hand_qty ?? product.qty_available ?? 0);
  return {
    id: product.id || product.product_id || product.barcode || `${fallbackTitle}-${index}`,
    title: product.product_name || product.name || fallbackTitle,
    gender: product.gender || '',
    retail: product.retail_price,
    cost: product.cost_price,
    rawCost: pricing.raw,
    costPlus12: pricing.plus12,
    costPlus20: pricing.plus20,
    selected: Boolean(product.selected),
    top,
    mid,
    base,
    dupe,
    inventoryQty,
    empty: !product.product_name && !product.name,
  };
}

function buildDemoTiles() {
  return [
    {
      id: 'demo-1',
      title: 'Scan Product 1',
      gender: '',
      retail: null,
      cost: null,
      selected: true,
      top: ['Top notes'],
      mid: ['Middle notes'],
      base: ['Base notes'],
      dupe: { inspiration_fragrance: 'Inspired by / dupe of', notes: 'Scan from TV Scanner to preview product details here.' },
      empty: true,
    },
    {
      id: 'demo-2',
      title: 'Scan Product 2',
      gender: '',
      retail: null,
      cost: null,
      selected: false,
      top: ['Top notes'],
      mid: ['Middle notes'],
      base: ['Base notes'],
      dupe: { inspiration_fragrance: 'Next scanned product', notes: 'The TV tray keeps the latest four products automatically.' },
      empty: true,
    },
    {
      id: 'demo-3',
      title: 'Scan Product 3',
      gender: '',
      retail: null,
      cost: null,
      selected: false,
      top: ['Top notes'],
      mid: ['Middle notes'],
      base: ['Base notes'],
      dupe: { inspiration_fragrance: 'Rolling tray', notes: 'When a new product is scanned, the oldest tile drops off.' },
      empty: true,
    },
    {
      id: 'demo-4',
      title: 'Scan Product 4',
      gender: '',
      retail: null,
      cost: null,
      selected: false,
      top: ['Top notes'],
      mid: ['Middle notes'],
      base: ['Base notes'],
      dupe: { inspiration_fragrance: 'Live selling board', notes: 'Product name, gender, notes, and dupe info appear here.' },
      empty: true,
    },
  ];
}

function Chip({ children, tone = 'muted' }) {
  const toneClass = tone === 'amber'
    ? 'chip chip--amber'
    : tone === 'coral'
      ? 'chip chip--coral'
      : tone === 'emerald'
        ? 'chip chip--emerald'
        : tone === 'blue'
          ? 'chip chip--blue'
          : 'chip chip--muted';
  return (
    <span
      className={toneClass}
      style={{
        fontSize: '0.92rem',
        fontWeight: 950,
        padding: '8px 12px',
        letterSpacing: '0.04em',
      }}
    >
      {children}
    </span>
  );
}

function MiniNotes({ title, items, hero = false }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{ fontSize: hero ? '0.82rem' : '0.68rem', fontWeight: 900, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
        {title}
      </div>
      <div style={{ fontSize: hero ? '1.28rem' : '0.9rem', lineHeight: hero ? 1.5 : 1.45, fontWeight: hero ? 850 : 500, color: hero ? 'var(--text-primary)' : 'var(--text-secondary)', minHeight: hero ? 82 : 38 }}>
        {items.length ? items.slice(0, 3).join(', ') : '—'}
      </div>
    </div>
  );
}

function ProductTile({ tile, tileNumber, hero = false }) {
  const inspiration = tile.dupe?.inspiration_fragrance || '';
  const dupeNotes = tile.dupe?.notes || tile.dupe?.classification || '';
  return (
    <div
      className="panel animate-in"
      style={{
        padding: hero ? '24px 28px' : 18,
        borderRadius: 20,
        minHeight: hero ? 360 : 320,
        display: 'flex',
        flexDirection: 'column',
        gap: hero ? 18 : 14,
        border: `1px solid ${tile.selected ? 'rgba(16,185,129,0.35)' : 'var(--border-default)'}`,
        background: tile.selected ? 'rgba(16,185,129,0.05)' : 'var(--bg-elevated)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
            {hero ? 'Live Product' : `Tile ${tileNumber}`}
          </div>
          <div style={{ fontSize: hero ? '2.55rem' : '1.35rem', lineHeight: hero ? 1.02 : 1.15, fontWeight: 950, color: 'var(--text-primary)', letterSpacing: hero ? '-0.03em' : undefined }}>
            {tile.title}
          </div>
        </div>
        <Chip tone={tile.selected ? 'emerald' : 'blue'}>{tile.selected ? 'Live' : 'Queued'}</Chip>
      </div>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <Chip tone="blue">{tile.gender ? `Gender ${tile.gender}` : 'Gender —'}</Chip>
        <Chip tone="amber">{tile.retail != null ? `Retail ${fmtMoney(tile.retail)}` : 'Retail —'}</Chip>
        <Chip tone="coral">{tile.cost != null ? `Our cost ${fmtMoney(tile.cost)}` : 'Our cost —'}</Chip>
        <Chip tone="emerald">{Number.isFinite(tile.inventoryQty) ? `${tile.inventoryQty} left` : 'Qty —'}</Chip>
        <Chip tone="muted">{tile.rawCost != null ? `Raw ${fmtMoney(tile.rawCost)}` : 'Raw —'}</Chip>
        <Chip tone="emerald">{tile.costPlus12 != null ? `+12 ${fmtMoney(tile.costPlus12)}` : '+12 —'}</Chip>
        <Chip tone="emerald">{tile.costPlus20 != null ? `+20 ${fmtMoney(tile.costPlus20)}` : '+20 —'}</Chip>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: hero ? 'repeat(3, minmax(0, 1fr))' : '1fr', gap: hero ? 18 : 12 }}>
        <MiniNotes title="Top Notes" items={tile.top} hero={hero} />
        <MiniNotes title="Mid Notes" items={tile.mid} hero={hero} />
        <MiniNotes title="Base Notes" items={tile.base} hero={hero} />
      </div>

      <div
        style={{
          marginTop: 'auto',
          borderRadius: 14,
          border: '1px solid var(--border-default)',
          background: 'var(--bg-layer2)',
          padding: hero ? '16px 18px' : 14,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          minHeight: hero ? 130 : 112,
        }}
      >
        <div style={{ fontSize: '0.72rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
          Inspired / Dupe Of
        </div>
        <div style={{ fontSize: hero ? '1.45rem' : '1rem', fontWeight: 950, color: 'var(--text-primary)' }}>
          {inspiration || '—'}
        </div>
        <div style={{ fontSize: hero ? '1.08rem' : '0.9rem', lineHeight: hero ? 1.6 : 1.45, fontWeight: hero ? 700 : 500, color: 'var(--text-secondary)' }}>
          {dupeNotes || (tile.empty ? 'Scan from TV Scanner to load this tile.' : 'No dupe research available yet.')}
        </div>
      </div>
    </div>
  );
}

export default function LargeScreen() {
  const { data: streamStatus } = usePolling('/api/stream_status', 3000);
  const { data: obsData } = usePolling('/api/obs/current', 400);
  const isRunning = streamStatus?.running || false;
  const scannedRows = obsData?.tray || [];

  const tiles = useMemo(() => {
    const orderedRows = [...scannedRows].sort((left, right) => {
      const leftSelected = Boolean(left?.selected || left?.status === 'active');
      const rightSelected = Boolean(right?.selected || right?.status === 'active');
      if (leftSelected === rightSelected) return 0;
      return leftSelected ? -1 : 1;
    });
    const rows = orderedRows.slice(0, 4).map((row, index) => buildTile(row, index));
    if (rows.length >= 4) return rows;

    const obsProduct = obsData?.product;
    if (obsProduct && !rows.some((row) => row.title === (obsProduct.name || obsProduct.product_name))) {
      rows.unshift(buildTile(obsProduct, 0, 'Live product'));
    }

    const trimmed = rows.slice(0, 4);
    while (trimmed.length < 4) {
      trimmed.push(buildDemoTiles()[trimmed.length]);
    }
    return trimmed;
  }, [scannedRows, obsData]);

  const liveTile = tiles[0];
  const queuedTiles = tiles.slice(1);

  return (
    <div style={{ padding: '18px 20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="panel animate-in" style={{ padding: '18px 22px', borderRadius: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '0.62rem', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              TV Display
            </div>
            <div style={{ marginTop: 4, fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-secondary)' }}>
              Four Product Preview Tiles
            </div>
            <div style={{ marginTop: 4, color: 'var(--text-muted)', fontSize: '0.78rem', fontWeight: 400 }}>
              Live streamer board showing the newest 4 scanned products from TV Scanner.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <Chip tone="blue">{isRunning ? 'Live stream active' : 'Waiting for live stream'}</Chip>
            <Chip tone="muted">Showing {tiles.length} tiles</Chip>
          </div>
        </div>
      </div>

      <ProductTile tile={liveTile} tileNumber={1} hero />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
        {queuedTiles.map((tile, index) => (
          <ProductTile key={tile.id || index} tile={tile} tileNumber={index + 2} />
        ))}
      </div>
    </div>
  );
}
