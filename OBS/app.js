// --- Config ---
const dataPath = new URLSearchParams(window.location.search).get('data') || 'data.json';
const API_BASE = new URLSearchParams(window.location.search).get('api') || 'http://localhost:8088';

// --- State ---
let lastPayload = '';
let lastMediaUrl = '';
let lastProductActive = false;

// ---------------------------------------------------------------------------
// data.json polling (manual overrides: ticker, seller name, shipping, etc.)
// ---------------------------------------------------------------------------
async function loadData() {
  try {
    const res = await fetch(`${dataPath}?t=${Date.now()}`, { cache: 'no-store' });
    const text = await res.text();
    if (text !== lastPayload) {
      lastPayload = text;
      applyData(JSON.parse(text));
    }
  } catch (e) {
    console.error('Overlay data load failed', e);
  }
}

function applyData(data) {
  // Static overlay content only — product area is driven exclusively by live scan
  setText('sellerName', data.sellerName);
  setText('statLine', data.companyStats);
  setText('promoText', data.promoText);
  setText('bidText', data.bidText);
  setText('bidCount', data.bidCount);
  setText('statsLine', data.statsLine);
  setText('likeCount', data.likeCount);
  setText('ctaText', data.ctaText || data.bidText);
  setText('ctaCount', data.ctaCount ?? data.bidCount);

  const items = Array.isArray(data.tickerItems) ? data.tickerItems : [];
  const ticker = document.getElementById('ticker');
  ticker.textContent = items.length ? ` ${items.join('   •   ')} ` : '';
  startTicker();

  const chatLines = document.getElementById('chatLines');
  if (chatLines) {
    chatLines.innerHTML = '';
    (data.chatLines || []).slice(0, 4).forEach((line) => {
      const row = document.createElement('div');
      const user = document.createElement('span');
      const msg = document.createElement('span');
      user.className = 'user';
      msg.className = 'msg';
      user.textContent = `${line.user}: `;
      msg.textContent = line.message;
      row.appendChild(user);
      row.appendChild(msg);
      chatLines.appendChild(row);
    });
  }
}

// ---------------------------------------------------------------------------
// Live product polling — /api/obs/current
// ---------------------------------------------------------------------------
async function loadLiveProduct() {
  try {
    const res = await fetch(`${API_BASE}/api/obs/current?t=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) { clearProductDisplay(); return; }
    const data = await res.json();
    if (data.active && data.product) {
      lastProductActive = true;
      applyProductData(data.product);
    } else {
      if (lastProductActive) clearProductDisplay();
      lastProductActive = false;
    }
  } catch (e) {
    // Server not reachable — clear product content, static overlay stays visible
    if (lastProductActive) clearProductDisplay();
    lastProductActive = false;
  }
}

function clearProductDisplay() {
  setText('productTitle', '');
  setText('topNote', '');
  setText('midNote', '');
  setText('baseNote', '');
  setText('freeNotes', '');
  setText('retailPrice', '');
  setText('costPrice', '');
  const notesPanel = document.getElementById('notesPanel');
  const notesList = document.getElementById('notesList');
  const freeNotes = document.getElementById('freeNotes');
  if (notesPanel) notesPanel.style.display = 'none';
  if (notesList) notesList.style.display = '';
  if (freeNotes) freeNotes.style.display = 'none';
  applyMedia(null);
  lastMediaUrl = '';
}

function applyProductData(p) {
  if (!p) return;

  if (p.name) setText('productTitle', p.name);

  // Notes section — support both dedicated overlay note lines and free-form inventory notes
  const hasStructuredNotes = p.note_top || p.note_mid || p.note_base;
  const hasFreeNotes = !!(p.notes && String(p.notes).trim());
  const notesPanel = document.getElementById('notesPanel');
  const notesList = document.getElementById('notesList');
  const freeNotes = document.getElementById('freeNotes');

  if (notesPanel) notesPanel.style.display = (hasStructuredNotes || hasFreeNotes) ? '' : 'none';

  if (notesList) {
    notesList.style.display = hasStructuredNotes ? '' : 'none';
    setText('topNote', p.note_top || '—');
    setText('midNote', p.note_mid || '—');
    setText('baseNote', p.note_base || '—');
  }
  if (freeNotes) {
    freeNotes.style.display = !hasStructuredNotes && hasFreeNotes ? 'block' : 'none';
    freeNotes.textContent = !hasStructuredNotes && hasFreeNotes ? String(p.notes).trim() : '';
  }

  // Retail price
  if (p.retail_price !== undefined && p.retail_price !== null) {
    const formatted = typeof p.retail_price === 'number'
      ? `$${p.retail_price.toFixed(2)}`
      : String(p.retail_price);
    setText('retailPrice', formatted);
  }
  if (p.cost_price !== undefined && p.cost_price !== null) {
    const formatted = typeof p.cost_price === 'number'
      ? `$${p.cost_price.toFixed(2)}`
      : String(p.cost_price);
    setText('costPrice', formatted);
  }

  // Media: video or image
  const mediaUrl = p.media_url || null;
  if (mediaUrl !== lastMediaUrl) {
    lastMediaUrl = mediaUrl;
    applyMedia(mediaUrl);
  }
}

function applyMedia(url) {
  const video = document.getElementById('productVideo');
  const img = document.getElementById('productImage');

  // Reset animation so it re-triggers on every new scan
  function resetAnim(el) {
    el.style.animation = 'none';
    el.offsetHeight; // reflow
    el.style.animation = '';
  }

  if (!url) {
    if (video) { video.pause(); video.src = ''; video.style.display = 'none'; }
    if (img) { img.src = ''; img.style.display = 'none'; }
    return;
  }

  const isVideo = /\.(mp4|webm|mov|m4v)(\?|$)/i.test(url);

  if (isVideo) {
    if (img) { img.src = ''; img.style.display = 'none'; }
    if (video) {
      resetAnim(video);
      video.src = url;
      video.style.display = 'block';
      video.play().catch(() => {});
    }
  } else {
    if (video) { video.pause(); video.src = ''; video.style.display = 'none'; }
    if (img) {
      resetAnim(img);
      img.src = url;
      img.style.display = 'block';
    }
  }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function setText(id, value) {
  if (value === undefined || value === null) return;
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

let tickerRAF;
function startTicker() {
  cancelAnimationFrame(tickerRAF);
  const wrap = document.querySelector('.ticker-wrap');
  const ticker = document.getElementById('ticker');
  let x = wrap.clientWidth;
  const speed = 1.2;
  function step() {
    x -= speed;
    if (x < -ticker.clientWidth - 50) x = wrap.clientWidth;
    ticker.style.transform = `translateX(${x}px)`;
    tickerRAF = requestAnimationFrame(step);
  }
  step();
}

// ---------------------------------------------------------------------------
// Stars animation
// ---------------------------------------------------------------------------
function spawnStars() {
  const container = document.getElementById('stars-container');
  if (!container) return;
  setInterval(() => {
    const spawnCount = Math.floor(Math.random() * 4) + 2;
    for (let i = 0; i < spawnCount; i++) {
      const star = document.createElement('div');
      star.className = 'star';
      const x = Math.random() * 100;
      const y = Math.random() * 100;
      const isLarge = Math.random() > 0.9;
      const size = isLarge ? Math.random() * 5 + 20 : Math.random() * 1.5 + 0.5;
      const duration = Math.random() * 2 + 2;
      star.style.left = `${x}%`;
      star.style.top = `${y}%`;
      star.style.width = `${size}px`;
      star.style.height = `${size}px`;
      star.style.setProperty('--duration', `${duration}s`);
      container.appendChild(star);
      setTimeout(() => { if (star.parentNode) star.remove(); }, duration * 1000);
    }
  }, 50);
}

// ---------------------------------------------------------------------------
// Glitter Rain
// ---------------------------------------------------------------------------
function initGlitterRain() {
  const container = document.getElementById('glitterContainer');
  if (!container) return;

  // Colour palette: gold, white, purple, pink accents
  const colors = [
    'rgba(255,234,0,VAL)',   // gold
    'rgba(255,255,255,VAL)', // white
    'rgba(255,157,0,VAL)',   // amber
    'rgba(200,160,255,VAL)', // soft purple
    'rgba(255,180,220,VAL)', // soft pink
  ];

  const COUNT = 90; // number of glitter particles

  for (let i = 0; i < COUNT; i++) {
    const el = document.createElement('div');
    el.className = 'glitter';

    const size   = Math.random() * 5 + 2;           // 2–7 px
    const x      = Math.random() * 1080;             // random horizontal
    const dur    = (Math.random() * 6 + 5).toFixed(2); // 5–11 s fall time
    const delay  = (Math.random() * 10).toFixed(2); // 0–10 s stagger
    const op     = (Math.random() * 0.35 + 0.1).toFixed(2); // 0.10–0.45
    const color  = colors[Math.floor(Math.random() * colors.length)]
                     .replace('VAL', op);

    el.style.cssText = `
      left: ${x}px;
      width: ${size}px;
      height: ${size}px;
      background: ${color};
      box-shadow: 0 0 ${size + 2}px ${color};
      --dur: ${dur}s;
      --delay: -${delay}s;
      --op: ${op};
    `;

    container.appendChild(el);
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
loadData();
setInterval(loadData, 1500);
// Sequential poll: fetch → wait → fetch. Prevents overlapping requests for snappy updates.
(async function liveLoop() {
  while (true) {
    await loadLiveProduct();
    await new Promise(r => setTimeout(r, 200));
  }
})();
window.addEventListener('resize', startTicker);
spawnStars();
initGlitterRain();
