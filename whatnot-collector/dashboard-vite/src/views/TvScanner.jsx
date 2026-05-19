import { useCallback, useEffect, useRef, useState } from 'react';
import { postApi, usePolling } from '../hooks/useApi';
import OperatorSubnav from '../components/OperatorSubnav';

export default function TvScanner() {
  const { data: obsData, refresh } = usePolling('/api/obs/current', 1200);
  const [scanInput, setScanInput] = useState('');
  const [feedback, setFeedback] = useState(null);
  const inputRef = useRef(null);
  const scanBufferRef = useRef('');
  const scanTimerRef = useRef(null);
  const scanBusyRef = useRef(false);

  const showFeedback = useCallback((msg, tone = 'info') => {
    setFeedback({ msg, tone });
    window.setTimeout(() => setFeedback(null), 3000);
  }, []);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function focusInput() {
      inputRef.current?.focus();
    }
    window.addEventListener('focus', focusInput);
    document.addEventListener('visibilitychange', focusInput);
    return () => {
      window.removeEventListener('focus', focusInput);
      document.removeEventListener('visibilitychange', focusInput);
    };
  }, []);

  useEffect(() => {
    function flushBufferedScan() {
      const code = scanBufferRef.current.trim();
      scanBufferRef.current = '';
      if (scanTimerRef.current) {
        window.clearTimeout(scanTimerRef.current);
        scanTimerRef.current = null;
      }
      if (code && !scanBusyRef.current) {
        handleScan(code);
      }
    }

    function onKeyDown(event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const active = document.activeElement;
      const isTypingField = active && (
        active.tagName === 'TEXTAREA' ||
        (active.tagName === 'INPUT' && active !== inputRef.current)
      );
      if (isTypingField) return;

      if (event.key === 'Enter') {
        if (scanBufferRef.current.trim()) {
          event.preventDefault();
          flushBufferedScan();
        }
        return;
      }
      if (event.key.length !== 1) return;
      scanBufferRef.current += event.key;
      setScanInput(scanBufferRef.current);
      if (scanTimerRef.current) {
        window.clearTimeout(scanTimerRef.current);
      }
      scanTimerRef.current = window.setTimeout(flushBufferedScan, 80);
    }

    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
      if (scanTimerRef.current) {
        window.clearTimeout(scanTimerRef.current);
        scanTimerRef.current = null;
      }
    };
  }, []);

  async function handleScan(raw) {
    const code = String(raw || scanInput || '').trim();
    if (!code) return;
    scanBusyRef.current = true;
    try {
      const result = await postApi('/api/obs/demo/scan', { barcode: code });
      setScanInput('');
      scanBufferRef.current = '';
      showFeedback(`Preview loaded: ${result?.product?.name || code}`, 'success');
      refresh();
      inputRef.current?.focus();
      inputRef.current?.select();
    } catch (err) {
      showFeedback(`Preview scan failed: ${err.message}`, 'error');
    } finally {
      scanBusyRef.current = false;
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <OperatorSubnav />
      <div className="panel" style={{ borderRadius: 18, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>TV Scanner</div>
            <div style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-primary)', marginTop: 6 }}>Live streamer product info scanner</div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 8, maxWidth: 780 }}>
              The live streamer uses this scanner to check the product on TV Display before or during the show. Scan here to show product name, gender, notes, and inspiration / dupe information on the TV screen. The TV tray keeps the latest 4 products automatically and drops the oldest one when a new scan comes in. This page never assigns the winner product and never deducts inventory.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <span className="chip chip--blue">TV display only</span>
            <span className={`chip ${obsData?.active ? 'chip--emerald' : 'chip--muted'}`}>{obsData?.active ? 'Product loaded' : 'Idle'}</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12, marginTop: 18 }}>
          <input
            ref={inputRef}
            className="input"
            type="text"
            placeholder="Scan barcode for TV display information…"
            value={scanInput}
            onChange={(e) => setScanInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleScan(e.currentTarget.value);
              }
            }}
          />
          <button className="btn btn--amber" onClick={() => handleScan(scanInput)}>Show On TV</button>
        </div>
        {feedback ? (
          <div className={`global-scan-dock__feedback ${feedback.tone}`} style={{ marginTop: 14 }}>{feedback.msg}</div>
        ) : null}
      </div>
    </div>
  );
}
