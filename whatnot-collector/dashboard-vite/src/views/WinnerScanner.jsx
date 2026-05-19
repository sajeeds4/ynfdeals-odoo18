import { useEffect, useMemo, useRef, useState } from 'react';
import { postApi, usePolling } from '../hooks/useApi';
import { useLocalState, useSessionState } from '../hooks/useBrowserState';
import OperatorSubnav from '../components/OperatorSubnav';

function fmt$(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

function fmtAssignedSummary(row) {
  const items = row?.assigned_items || [];
  if (items.length) {
    return items.map((item) => `${item.product_name} x${item.qty || 1}`).join(', ');
  }
  return row?.assigned_product_name || '';
}

function normalizeScanCode(value) {
  return String(value || '')
    .replace(/[\u0000-\u001f\u007f]+/g, '')
    .replace(/\s+/g, '')
    .trim();
}

function stockBadgeMeta(qty) {
  const value = Number(qty ?? 0);
  if (value <= 0) {
    return {
      bg: 'rgba(239,68,68,0.16)',
      border: '1px solid rgba(239,68,68,0.32)',
      color: 'var(--accent-coral)',
      label: 'Out',
    };
  }
  if (value <= 3) {
    return {
      bg: 'rgba(239,68,68,0.12)',
      border: '1px solid rgba(239,68,68,0.22)',
      color: 'var(--accent-coral)',
      label: 'Attention',
    };
  }
  return {
    bg: 'rgba(245, 158, 11, 0.12)',
    border: '1px solid rgba(245, 158, 11, 0.28)',
    color: 'var(--accent-amber)',
    label: '',
  };
}

function tiktokStatusTone(value) {
  const family = String(value || '').toLowerCase();
  if (family === 'cancelled') return { color: 'var(--accent-coral)', label: 'Cancelled' };
  if (family === 'confirmed') return { color: 'var(--accent-emerald)', label: 'Confirmed' };
  if (family === 'pending') return { color: 'var(--accent-amber)', label: 'Pending' };
  return { color: 'var(--text-secondary)', label: 'Unmatched' };
}

export default function WinnerScanner() {
  const { data: streamStatus } = usePolling('/api/stream_status', 1500, true, { useCache: false });
  const tiktokOperator = streamStatus?.tiktok_operator || {};
  const isTikTokMode = !!tiktokOperator?.enabled;
  const tiktokSessionId = tiktokOperator?.enabled ? tiktokOperator?.session_id : null;
  const statePath = tiktokSessionId
    ? `/api/winner_assignment/state?session_id=${encodeURIComponent(tiktokSessionId)}`
    : '/api/winner_assignment/state';
  const { data, refresh } = usePolling(statePath, 1200, true, { useCache: false });
  const { data: stats } = usePolling(['/api/v2/sessions/current/stats', '/api/session_stats'], 1000, true, { useCache: false });
  const [selectedId, setSelectedId] = useSessionState('winnerScanner.selectedId', null);
  const [scanInput, setScanInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [lotInput, setLotInput] = useState('');
  const [autoConfirm, setAutoConfirm] = useLocalState('winnerScanner.autoConfirm.v3', true);
  const inputRef = useRef(null);
  const seenPendingIdsRef = useRef(new Set());
  const forcedWinnerEventIdsRef = useRef(new Set());
  const scanBufferRef = useRef('');
  const scanTimerRef = useRef(null);
  const inputScanTimerRef = useRef(null);
  const scanBusyRef = useRef(false);

  const rows = data?.rows || [];
  const pendingRows = rows.filter((row) => row.status === 'pending');
  const assignedRows = rows.filter((row) => row.status === 'assigned');
  const reviewRows = rows.filter((row) => row.status === 'needs_review');
  const confirmedRows = rows.filter((row) => row.status === 'confirmed');
  const cancelledRows = rows.filter((row) => row.status === 'payment_cancelled');
  const selected = useMemo(() => rows.find((row) => row.id === selectedId) || rows[0] || null, [rows, selectedId]);

  useEffect(() => {
    if (!selectedId && rows.length) setSelectedId(rows[0].id);
    if (selectedId && !rows.some((row) => row.id === selectedId)) setSelectedId(rows[0]?.id || null);
  }, [rows, selectedId]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [selected?.id]);

  useEffect(() => {
    setLotInput(String(selected?.lot_number || ''));
  }, [selected?.id, selected?.lot_number]);

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
    const previous = seenPendingIdsRef.current;
    const currentPending = new Set(pendingRows.map((row) => row.id));
    const newRows = pendingRows.filter((row) => !previous.has(row.id));
    if (newRows.length) {
      const newest = newRows[0];
      setSelectedId(newest.id);
      showFeedback(`New winner pending: lot ${newest.lot_number || '—'} @${newest.winner_username || 'unknown'}`, 'warning');
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 880;
        gain.gain.value = 0.03;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.16);
      } catch {
        // ignore alert audio failures
      }
    }
    seenPendingIdsRef.current = currentPending;
  }, [pendingRows]);

  useEffect(() => {
    const rawWinner = stats?.latest_db_winner || {};
    const rawEventId = rawWinner?._event_id;
    const rawWinnerName = rawWinner?.winner_username || rawWinner?.winner;
    const rawLot = rawWinner?.lot_number;
    const rawPrice = rawWinner?.price_value;
    // If TikTok operator mode is enabled, do NOT auto-ingest Whatnot collector winners here.
    if (tiktokOperator?.enabled) return;
    if (!rawEventId || !rawWinnerName || rawLot == null || rawPrice == null) return;
    const sourceEventId = `collector_event_${rawEventId}`;
    const alreadyQueued = rows.some((row) => row.source_event_id === sourceEventId);
    if (alreadyQueued || forcedWinnerEventIdsRef.current.has(rawEventId)) return;
    forcedWinnerEventIdsRef.current.add(rawEventId);
    postApi('/api/ingest_winner', {
      event_id: rawEventId,
      winner_username: rawWinnerName,
      lot_number: String(rawLot),
      sale_price: rawPrice,
      sold_at: rawWinner?._created_at,
    })
      .then(() => refresh())
      .catch(() => {
        forcedWinnerEventIdsRef.current.delete(rawEventId);
      });
  }, [stats, rows, refresh, tiktokOperator?.enabled]);

  function showFeedback(msg, tone = 'info') {
    setFeedback({ msg, tone });
    window.setTimeout(() => setFeedback(null), 3200);
  }

  function flushBufferedScan() {
    const code = normalizeScanCode(scanBufferRef.current);
    scanBufferRef.current = '';
    if (scanTimerRef.current) {
      window.clearTimeout(scanTimerRef.current);
      scanTimerRef.current = null;
    }
    setScanInput('');
    if (code && selected && !scanBusyRef.current) {
      handleScan(code);
    }
  }

  function queueBufferedChar(char) {
    if (!char || !selected) return;
    scanBufferRef.current += char;
    setScanInput(normalizeScanCode(scanBufferRef.current));
    if (scanTimerRef.current) {
      window.clearTimeout(scanTimerRef.current);
    }
    scanTimerRef.current = window.setTimeout(flushBufferedScan, 180);
  }

  useEffect(() => {
    function onKeyDown(event) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const active = document.activeElement;
      const isTypingField = active && (
        active.tagName === 'TEXTAREA' ||
        active.tagName === 'INPUT'
      );
      if (isTypingField) return;

      if (event.key === 'Enter') {
        if (scanBufferRef.current.trim()) {
          event.preventDefault();
          flushBufferedScan();
        }
        return;
      }
      if (event.key.length !== 1 || !selected) return;
      queueBufferedChar(event.key);
    }

    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      window.removeEventListener('keydown', onKeyDown, true);
      if (scanTimerRef.current) {
        window.clearTimeout(scanTimerRef.current);
        scanTimerRef.current = null;
      }
      if (inputScanTimerRef.current) {
        window.clearTimeout(inputScanTimerRef.current);
        inputScanTimerRef.current = null;
      }
    };
  }, [selected]);

  async function handleScan(raw) {
    const code = normalizeScanCode(raw || scanInput);
    if (!code || !selected) return;
    setBusy(true);
    scanBusyRef.current = true;
    const addingMore = Boolean((selected?.assigned_items_count || 0) > 0 || selected?.assigned_product_name) && selected?.status !== 'confirmed';
    try {
      const result = await postApi('/api/winner_assignment/scan', { barcode: code, assignment_id: selected.id });
      const assignment = result?.assignment;
      const nextPending = pendingRows.find((row) => row.id !== selected.id);
      setScanInput('');
      scanBufferRef.current = '';
      if (autoConfirm && assignment?.id) {
        await postApi('/api/winner_assignment/confirm', { assignment_id: assignment.id });
        setSelectedId(nextPending?.id || assignment.id || selected.id);
        showFeedback(`Assigned and confirmed ${fmtAssignedSummary(assignment) || code} for lot ${selected.lot_number || '—'}`, 'success');
      } else {
        setSelectedId(assignment?.id || selected.id);
        showFeedback(`${addingMore ? 'Added' : 'Assigned'} ${fmtAssignedSummary(assignment) || code} for lot ${selected.lot_number || '—'}`, 'success');
      }
      refresh();
      inputRef.current?.focus();
      inputRef.current?.select();
    } catch (err) {
      showFeedback(`${autoConfirm ? 'Scan/confirm' : 'Assignment'} failed: ${err.message}`, 'error');
    } finally {
      scanBusyRef.current = false;
      setBusy(false);
    }
  }

  function handleInputChange(value) {
    const normalized = normalizeScanCode(value);
    setScanInput(normalized);
    if (inputScanTimerRef.current) {
      window.clearTimeout(inputScanTimerRef.current);
      inputScanTimerRef.current = null;
    }
    if (!normalized || busy || !selected) return;
    inputScanTimerRef.current = window.setTimeout(() => {
      inputScanTimerRef.current = null;
      if (!scanBusyRef.current) {
        handleScan(normalized);
      }
    }, 220);
  }

  async function handleConfirm() {
    if (!selected) return;
    setBusy(true);
    try {
      const nextPending = pendingRows.find((row) => row.id !== selected.id);
      await postApi('/api/winner_assignment/confirm', { assignment_id: selected.id });
      setSelectedId(nextPending?.id || selected.id);
      showFeedback(`Winner lot ${selected.lot_number || '—'} confirmed`, 'success');
      refresh();
    } catch (err) {
      showFeedback(`Confirm failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleStatus(status) {
    if (!selected) return;
    setBusy(true);
    try {
      await postApi('/api/winner_assignment/status', { assignment_id: selected.id, status });
      showFeedback(`Lot ${selected.lot_number || '—'} moved to ${status.replace('_', ' ')}`, 'success');
      refresh();
    } catch (err) {
      showFeedback(`Status update failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleUndo() {
    if (!selected) return;
    setBusy(true);
    try {
      await postApi('/api/winner_assignment/undo', { assignment_id: selected.id });
      showFeedback(`Undo complete for lot ${selected.lot_number || '—'}`, 'success');
      refresh();
    } catch (err) {
      showFeedback(`Undo failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveAssignedItem(itemId) {
    if (!selected || !itemId) return;
    setBusy(true);
    try {
      await postApi('/api/winner_assignment/item/delete', { assignment_id: selected.id, item_id: itemId });
      showFeedback(`Removed scanned item from lot ${selected.lot_number || '—'}`, 'success');
      refresh();
      inputRef.current?.focus();
    } catch (err) {
      showFeedback(`Remove failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleClearAssignedItems() {
    if (!selected || !(selected.assigned_items || []).length) return;
    setBusy(true);
    try {
      for (const item of selected.assigned_items) {
        // Remove one assigned row at a time so the existing backend path
        // keeps status/cost math consistent while the operator is correcting scans.
        await postApi('/api/winner_assignment/item/delete', { assignment_id: selected.id, item_id: item.id });
      }
      showFeedback(`Cleared scanned products for lot ${selected.lot_number || '—'}`, 'success');
      refresh();
      inputRef.current?.focus();
    } catch (err) {
      showFeedback(`Clear failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveLotNumber() {
    if (!selected || !isTikTokMode) return;
    const nextLot = String(lotInput || '').trim();
    if (!nextLot || nextLot === String(selected.lot_number || '').trim()) return;
    setBusy(true);
    try {
      const result = await postApi('/api/winner_assignment/lot', {
        assignment_id: selected.id,
        lot_number: nextLot,
      });
      setLotInput(String(result?.assignment?.lot_number || nextLot));
      showFeedback(`TikTok lot updated to ${nextLot}`, 'success');
      refresh();
    } catch (err) {
      showFeedback(`Lot update failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  async function handleDeleteLot() {
    if (!selected) return;
    const lotLabel = selected.lot_number || '—';
    const winnerLabel = selected.winner_username ? ` @${selected.winner_username}` : '';
    const ok = window.confirm(`Delete lot ${lotLabel}${winnerLabel}?\n\nThis will remove the winner ticket and its linked auction result/order records.`);
    if (!ok) return;
    setBusy(true);
    try {
      const nextSelectable =
        rows.find((row) => row.id !== selected.id && row.status === 'pending') ||
        rows.find((row) => row.id !== selected.id) ||
        null;
      await postApi('/api/winner_assignment/delete', { assignment_id: selected.id });
      setSelectedId(nextSelectable?.id || null);
      showFeedback(`Deleted lot ${lotLabel}`, 'success');
      refresh();
    } catch (err) {
      showFeedback(`Delete failed: ${err.message}`, 'error');
    } finally {
      setBusy(false);
    }
  }

  function renderQueueSection(title, queueRows, emptyText) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>{title}</div>
        {!queueRows.length ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>{emptyText}</div>
        ) : (
          queueRows.map((row) => (
            <button
              key={row.id}
              className="btn"
              onClick={() => setSelectedId(row.id)}
              style={{
                textAlign: 'left',
                borderRadius: 16,
                border: `1px solid ${row.id === selected?.id ? 'var(--accent-emerald)' : 'var(--border-default)'}`,
                background: row.id === selected?.id ? 'rgba(16,185,129,0.08)' : 'var(--bg-elevated)',
                padding: 14,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                <div style={{ fontSize: '1rem', fontWeight: 900, color: 'var(--text-primary)' }}>Lot {row.lot_number || '—'}</div>
                <span className={`chip ${row.status === 'assigned' ? 'chip--emerald' : row.status === 'needs_review' ? 'chip--coral' : row.status === 'payment_cancelled' ? 'chip--muted' : 'chip--amber'}`}>{row.status === 'payment_cancelled' ? 'cancelled' : row.status}</span>
              </div>
              <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>@{row.winner_username || 'unknown'} · {fmt$(row.sale_price)}</div>
              <div style={{ marginTop: 6, fontSize: 12, color: 'var(--text-muted)' }}>{row.detected_at ? new Date(row.detected_at).toLocaleString() : '—'}</div>
              {row.tiktok_order ? (
                <div style={{ marginTop: 8, display: 'grid', gap: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                  <div>
                    TikTok: <strong style={{ color: 'var(--text-primary)' }}>{row.tiktok_order.order_id || '—'}</strong>
                  </div>
                  <div>
                    Buyer: <strong style={{ color: 'var(--text-primary)' }}>{row.tiktok_buyer_name || row.tiktok_buyer_username || row.tiktok_order.recipient_name || '—'}</strong>
                  </div>
                  <div>
                    Status:{' '}
                    <strong style={{ color: tiktokStatusTone(row.tiktok_order_status_family).color }}>
                      {row.tiktok_order.status || tiktokStatusTone(row.tiktok_order_status_family).label}
                    </strong>
                    {row.tiktok_sale_price ? (
                      <span style={{ color: 'var(--text-muted)' }}> · {fmt$(row.tiktok_sale_price)}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {row.assigned_product_name ? (
                <div style={{ marginTop: 8, fontSize: 13, fontWeight: 700, color: row.status === 'needs_review' ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{row.assigned_product_name}</div>
              ) : null}
            </button>
          ))
        )}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <OperatorSubnav />
      <div className="panel" style={{ borderRadius: 18, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Winner Scanner</div>
            <div style={{ fontSize: '1.8rem', fontWeight: 900, color: 'var(--text-primary)', marginTop: 6 }}>Assistant winner assignment scanner</div>
            <div style={{ color: 'var(--text-secondary)', marginTop: 8, maxWidth: 780 }}>
              {isTikTokMode
                ? 'TikTok mode is active. Use the detected winner, lot number, and price, correct the lot if OCR needs help, then scan the real sold barcode here and confirm it.'
                : 'This station is for the person sitting next to the live streamer. Use only the winner, lot number, and price from Whatnot. Ignore the Whatnot product title, then scan the actual sold barcode here and confirm it.'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <span className="chip chip--amber">{pendingRows.length} pending</span>
            <span className="chip chip--emerald">{assignedRows.length} assigned</span>
            <span className="chip chip--coral">{reviewRows.length} review</span>
            <span className="chip chip--blue">{confirmedRows.length} confirmed</span>
            {cancelledRows.length > 0 && <span className="chip chip--muted">{cancelledRows.length} cancelled</span>}
            {selected ? <span className={`chip ${selected.status === 'assigned' ? 'chip--emerald' : selected.status === 'needs_review' ? 'chip--coral' : 'chip--blue'}`}>Selected lot {selected.lot_number || '—'}</span> : <span className="chip chip--muted">No pending winners</span>}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', gap: 18, alignItems: 'start' }}>
        <div className="panel" style={{ borderRadius: 18, padding: 18, maxHeight: '70vh', overflow: 'auto' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {renderQueueSection('Pending Winner Queue', pendingRows, 'No pending winner assignments yet.')}
            {renderQueueSection('Assigned Waiting Confirm', assignedRows, 'No assigned winner tickets right now.')}
            {renderQueueSection('Needs Review', reviewRows, 'No review tickets right now.')}
            {renderQueueSection('Recently Confirmed', confirmedRows, 'No recently confirmed tickets right now.')}
            {cancelledRows.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--accent-coral)' }}>
                  Cancelled Payments — Review After Stream
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: -6 }}>
                  These lots had payment cancelled. Review and follow up after the stream ends.
                </div>
                {cancelledRows.map((row) => (
                  <button
                    key={row.id}
                    className="btn"
                    onClick={() => setSelectedId(row.id)}
                    style={{
                      textAlign: 'left',
                      borderRadius: 16,
                      border: `1px solid ${row.id === selected?.id ? 'var(--accent-coral)' : 'rgba(239,68,68,0.3)'}`,
                      background: row.id === selected?.id ? 'rgba(239,68,68,0.08)' : 'var(--bg-elevated)',
                      padding: 14,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                      <div style={{ fontSize: '1rem', fontWeight: 900, color: 'var(--text-primary)' }}>Lot {row.lot_number || '—'}</div>
                      <span className="chip chip--muted">cancelled</span>
                    </div>
                    <div style={{ marginTop: 8, color: 'var(--text-secondary)' }}>@{row.winner_username || 'unknown'} · {fmt$(row.sale_price)}</div>
                    <div style={{ marginTop: 6, fontSize: 12, color: 'var(--accent-coral)', fontWeight: 700 }}>Payment cancelled — needs follow-up</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className="panel" style={{ borderRadius: 18, padding: 18 }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 14 }}>Assignment Scanner</div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                Normal flow: scan and move to the next pending winner automatically.
              </div>
              <label className="toggle-label" style={{ margin: 0 }}>
                <input type="checkbox" checked={autoConfirm} onChange={(e) => setAutoConfirm(e.target.checked)} />
                <span className="text-sm">Auto-confirm after scan</span>
              </label>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: 12 }}>
              <input
                ref={inputRef}
                className="input"
                type="text"
                placeholder={selected ? `${(selected.assigned_items_count || 0) > 0 || selected.assigned_product_name ? 'Scan another product for' : 'Scan winner product for'} lot ${selected.lot_number || '—'}…` : 'Waiting for winner…'}
                value={scanInput}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.metaKey || e.ctrlKey || e.altKey) return;
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    if (inputScanTimerRef.current) {
                      window.clearTimeout(inputScanTimerRef.current);
                      inputScanTimerRef.current = null;
                    }
                    handleScan(e.currentTarget.value);
                  }
                }}
                onPaste={(e) => {
                  e.preventDefault();
                  const pasted = normalizeScanCode(e.clipboardData?.getData('text') || '');
                  if (pasted) handleScan(pasted);
                }}
                disabled={!selected || busy}
              />
              <button className="btn btn--amber" onClick={() => handleScan(scanInput)} disabled={!selected || busy}>{(selected?.assigned_items_count || 0) > 0 || (selected?.assigned_product_name && selected?.status !== 'confirmed') ? 'Add Product' : 'Assign To Winner'}</button>
              <button className="btn" onClick={handleConfirm} disabled={!selected || selected?.status !== 'assigned' || busy}>Confirm</button>
            </div>
            {selected ? (
              <div style={{ marginTop: 10, fontSize: 13, color: 'var(--text-secondary)' }}>
                {autoConfirm
                  ? 'Auto-confirm is on, so a scan will finish this lot and move to the next winner. Turn it off for multi-product lots.'
                  : 'Scan as many sold products as needed for this lot before confirm. If one was scanned by mistake, delete it from the assigned list before confirm.'}
              </div>
            ) : null}
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
              <button className="btn" onClick={() => handleStatus('needs_review')} disabled={!selected || busy}>Mark Review</button>
              <button className="btn" onClick={() => handleStatus('pending')} disabled={!selected || busy}>Return to Pending</button>
              <button className="btn" onClick={handleUndo} disabled={!selected || selected?.status !== 'confirmed' || busy}>Undo Last Confirm</button>
              <button
                className="btn"
                onClick={() => handleStatus('payment_cancelled')}
                disabled={!selected || selected?.status === 'payment_cancelled' || busy}
                style={{ color: 'var(--accent-coral)', borderColor: 'var(--accent-coral)' }}
                title="Mark this lot as payment cancelled — will appear in post-stream payment review"
              >
                Cancel Payment
              </button>
              <button
                className="btn"
                onClick={handleDeleteLot}
                disabled={!selected || busy}
                style={{ color: 'var(--accent-coral)', borderColor: 'var(--accent-coral)' }}
                title="Delete this lot and remove its linked winner/result records"
              >
                Delete Lot
              </button>
            </div>
            {feedback ? (
              <div className={`global-scan-dock__feedback ${feedback.tone}`} style={{ marginTop: 14 }}>{feedback.msg}</div>
            ) : null}
          </div>

          <div className="panel" style={{ borderRadius: 18, padding: 18 }}>
            <div style={{ fontSize: '0.78rem', fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: 14 }}>Selected Winner Ticket</div>
            {!selected ? (
              <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>No pending winner selected.</div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: (selected.assigned_items_count || 0) > 0 || selected.assigned_product_name ? '140px 1fr' : '1fr', gap: 18 }}>
                {(selected.assigned_items_count || 0) > 0 || selected.assigned_product_name ? (
                  <div style={{ width: 140, height: 140, borderRadius: 16, overflow: 'hidden', background: 'var(--bg-elevated)', display: 'grid', placeItems: 'center' }}>
                    {(selected.image_url || selected.assigned_product_image_url || selected.assigned_product_image_path) ? (
                      <img
                        src={selected.image_url || selected.assigned_product_image_url || selected.assigned_product_image_path}
                        alt=""
                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                      />
                    ) : <span style={{ fontSize: 36 }}>📦</span>}
                  </div>
                ) : null}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <div style={{ fontSize: '1.45rem', fontWeight: 900, color: 'var(--text-primary)' }}>Lot {selected.lot_number || '—'}</div>
                  <div style={{ color: 'var(--text-secondary)' }}>Winner: <strong style={{ color: 'var(--text-primary)' }}>@{selected.winner_username || 'unknown'}</strong></div>
                  <div style={{ color: 'var(--text-secondary)' }}>Sale price: <strong style={{ color: 'var(--accent-amber)' }}>{fmt$(selected.sale_price)}</strong></div>
                  <div style={{ color: 'var(--text-secondary)' }}>Status: <strong style={{ color: selected.status === 'assigned' ? 'var(--accent-emerald)' : selected.status === 'needs_review' ? 'var(--accent-coral)' : selected.status === 'confirmed' ? 'var(--accent-emerald)' : selected.status === 'payment_cancelled' ? 'var(--accent-coral)' : 'var(--text-primary)' }}>{selected.status === 'payment_cancelled' ? 'Payment Cancelled' : selected.status}</strong></div>
                  {selected.tiktok_order ? (
                    <div style={{ borderRadius: 14, border: '1px solid rgba(59,130,246,0.18)', background: 'rgba(59,130,246,0.06)', padding: 12, display: 'grid', gap: 8, maxWidth: 460 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#2563eb' }}>
                        TikTok Seller Order Match
                      </div>
                      <div style={{ display: 'grid', gap: 4, fontSize: 13, color: 'var(--text-secondary)' }}>
                        <div>Order ID: <strong style={{ color: 'var(--text-primary)' }}>{selected.tiktok_order.order_id || '—'}</strong></div>
                        <div>Buyer: <strong style={{ color: 'var(--text-primary)' }}>{selected.tiktok_buyer_name || selected.tiktok_buyer_username || selected.tiktok_order.recipient_name || '—'}</strong></div>
                        <div>Status: <strong style={{ color: tiktokStatusTone(selected.tiktok_order_status_family).color }}>{selected.tiktok_order.status || tiktokStatusTone(selected.tiktok_order_status_family).label}</strong></div>
                        <div>Seller SKU / Lot: <strong style={{ color: 'var(--text-primary)' }}>{selected.tiktok_order.seller_sku || selected.lot_number || '—'}</strong></div>
                        <div>Price: <strong style={{ color: 'var(--text-primary)' }}>{fmt$(selected.tiktok_sale_price || selected.tiktok_order.total_price || selected.tiktok_order.unit_price)}</strong></div>
                      </div>
                    </div>
                  ) : null}
                  {isTikTokMode ? (
                    <div style={{ borderRadius: 14, border: '1px solid rgba(249,115,22,0.22)', background: 'rgba(249,115,22,0.06)', padding: 12, display: 'grid', gap: 8, maxWidth: 420 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#ea580c' }}>
                        TikTok Lot Override
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                        If TikTok OCR misses or shifts the lot number, correct it here. This will update the linked TikTok auction result and downstream order views too.
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8 }}>
                        <input
                          className="input"
                          type="text"
                          value={lotInput}
                          onChange={(e) => setLotInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              handleSaveLotNumber();
                            }
                          }}
                          disabled={busy}
                          placeholder="Edit TikTok lot #"
                        />
                        <button className="btn btn--amber" onClick={handleSaveLotNumber} disabled={busy || !String(lotInput || '').trim()}>
                          Save Lot
                        </button>
                      </div>
                    </div>
                  ) : null}
                  <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>Whatnot product titles are intentionally ignored here.</div>
                  <div style={{ borderRadius: 14, border: '1px solid var(--border-default)', padding: 12, background: 'var(--bg-layer2)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, marginBottom: 8 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Assigned products</div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{selected.assigned_items_count || 0} item(s)</div>
                        {(selected.assigned_items || []).length && selected.status !== 'confirmed' ? (
                          <button
                            className="btn"
                            onClick={handleClearAssignedItems}
                            disabled={busy}
                            style={{
                              minWidth: 0,
                              padding: '6px 10px',
                              borderRadius: 10,
                              fontSize: 12,
                              fontWeight: 800,
                              color: 'var(--accent-coral)',
                            }}
                          >
                            Clear All
                          </button>
                        ) : null}
                      </div>
                    </div>
                    {(selected.assigned_items || []).length ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {selected.assigned_items.map((item) => (
                          <div key={item.id || `${item.product_id}-${item.barcode || item.product_name}`} style={{ borderRadius: 10, border: '1px solid var(--border-default)', padding: 10, background: 'var(--bg-elevated)' }}>
                            {(() => {
                              const stockMeta = stockBadgeMeta(item.on_hand_qty);
                              return (
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
                              <div>
                                <div style={{ color: 'var(--text-primary)', fontSize: 14, fontWeight: 700 }}>{item.product_name}</div>
                                <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                                  Qty {item.qty || 1}{item.barcode ? ` · ${item.barcode}` : ''}{item.unit_cost != null ? ` · Cost ${fmt$(item.unit_cost)}` : ''}
                                </div>
                                <div style={{
                                  marginTop: 8,
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: 6,
                                  padding: '6px 10px',
                                  borderRadius: 999,
                                  background: stockMeta.bg,
                                  border: stockMeta.border,
                                  fontSize: 13,
                                  fontWeight: 900,
                                  color: stockMeta.color,
                                }}>
                                  {item.on_hand_qty != null ? `${Number(item.on_hand_qty || 0)} left in inventory` : 'Inventory count unavailable'}
                                  {item.on_hand_qty != null && stockMeta.label ? <span style={{ fontSize: 10, fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{stockMeta.label}</span> : null}
                                </div>
                              </div>
                              {selected.status !== 'confirmed' ? (
                                <button
                                  className="btn"
                                  onClick={() => handleRemoveAssignedItem(item.id)}
                                  disabled={busy}
                                  title="Delete scanned item"
                                  style={{
                                    minWidth: 0,
                                    minHeight: 0,
                                    padding: '8px 12px',
                                    borderRadius: 10,
                                    fontSize: 13,
                                    fontWeight: 900,
                                    lineHeight: 1,
                                    color: 'var(--accent-coral)',
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: 8,
                                  }}
                                >
                                  <span style={{ fontSize: 18, lineHeight: 1 }}>×</span>
                                  <span>Remove</span>
                                </button>
                              ) : null}
                            </div>
                              );
                            })()}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div style={{ color: 'var(--text-muted)', fontSize: 14, fontWeight: 700 }}>
                        {selected.assigned_product_name || 'Waiting for sold-product scan'}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
