import { useEffect, useMemo, useState } from 'react';
import { fetchApi } from '../../hooks/useApi';
import {
  EmptyRow,
  FilterBar,
  KpiCard,
  PrimaryBtn,
  SearchInput,
  SessionSelect,
  TableShell,
  Thead,
  fmtDate,
  fmtDt,
} from './utils';

function yesNo(value) {
  return value ? 'Yes' : 'No';
}

export default function StreamReport() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState('');
  const [detail, setDetail] = useState({ report_rows: [] });
  const [search, setSearch] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    setLoadingSessions(true);
    fetchApi('/api/history/company_sessions')
      .then((result) => {
        const ended = (result.sessions || []).filter((row) => row.status === 'ended' && row.total_products_sold > 0);
        setSessions(ended);
        if (ended.length > 0) {
          setSessionId(String(ended[0].stream_id || ended[0].id));
        }
      })
      .catch(() => setSessions([]))
      .finally(() => setLoadingSessions(false));
  }, []);

  useEffect(() => {
    if (!sessionId) {
      setDetail({ report_rows: [] });
      return;
    }
    setLoadingDetail(true);
    fetchApi(`/api/history/company_detail?stream_id=${sessionId}`)
      .then((result) => setDetail(result))
      .catch(() => setDetail({ report_rows: [] }))
      .finally(() => setLoadingDetail(false));
  }, [sessionId]);

  const rows = detail.report_rows || [];
  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) =>
      (row.username || '').toLowerCase().includes(q) ||
      String(row.lot_number || '').toLowerCase().includes(q) ||
      (row.product_names || '').toLowerCase().includes(q) ||
      (row.profile_name || '').toLowerCase().includes(q)
    );
  }, [rows, search]);

  const selectedSession = sessions.find((row) => String(row.stream_id || row.id) === String(sessionId));
  const profileCount = filteredRows.filter((row) => row.profile_made).length;
  const saleOrderCount = filteredRows.filter((row) => row.sale_order_made).length;
  const totalItems = filteredRows.reduce((sum, row) => sum + (row.item_count || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
        <KpiCard label="Report Rows" value={filteredRows.length} icon="🧾" />
        <KpiCard label="Lots Sold" value={selectedSession?.total_lots_sold ?? 0} icon="🎯" />
        <KpiCard label="Items" value={totalItems} icon="📦" />
        <KpiCard label="Profiles Made" value={profileCount} icon="👤" />
        <KpiCard label="Sale Orders" value={saleOrderCount} icon="📋" />
      </div>

      <FilterBar>
        <SessionSelect
          sessions={sessions.map((row) => ({ id: row.stream_id || row.id, name: `${fmtDate(row.start_time)} · ${row.name || `Stream #${row.id}`}` }))}
          value={sessionId}
          onChange={setSessionId}
          allLabel={loadingSessions ? 'Loading sessions…' : 'Select ended stream'}
        />
        <SearchInput value={search} onChange={setSearch} placeholder="Search username, lot, product..." />
        <PrimaryBtn onClick={() => {
          if (!sessionId) return;
          setLoadingDetail(true);
          fetchApi(`/api/history/company_detail?stream_id=${sessionId}`)
            .then((result) => setDetail(result))
            .catch(() => setDetail({ report_rows: [] }))
            .finally(() => setLoadingDetail(false));
        }}>
          Refresh
        </PrimaryBtn>
      </FilterBar>

      <TableShell footer={selectedSession ? `${selectedSession.name || 'Ended stream'} · ${selectedSession.total_products_sold || 0} products sold` : undefined}>
        <Thead cols={[
          { label: 'Username' },
          { label: 'Lot #' },
          { label: 'Items', align: 'right' },
          { label: 'Product Names' },
          { label: 'Sold At' },
          { label: 'Profile Made' },
          { label: 'Profile Created' },
          { label: 'SO Made' },
        ]} />
        <tbody>
          {(loadingDetail || filteredRows.length === 0) && (
            <EmptyRow cols={8} loading={loadingDetail} msg="No end-of-stream report data found." />
          )}
          {!loadingDetail && filteredRows.map((row) => (
            <tr key={row.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <td style={{ padding: '8px 14px', fontWeight: 700 }}>@{row.username || '—'}</td>
              <td style={{ padding: '8px 14px', fontFamily: 'var(--font-mono)' }}>{row.lot_number || '—'}</td>
              <td style={{ padding: '8px 14px', textAlign: 'right' }}>{row.item_count ?? 0}</td>
              <td style={{ padding: '8px 14px', maxWidth: 340, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.product_names || '—'}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtDt(row.sold_at)}</td>
              <td style={{ padding: '8px 14px', color: row.profile_made ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>{yesNo(row.profile_made)}</td>
              <td style={{ padding: '8px 14px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{fmtDt(row.profile_created_at)}</td>
              <td style={{ padding: '8px 14px', color: row.sale_order_made ? 'var(--accent-emerald)' : 'var(--text-secondary)' }}>{yesNo(row.sale_order_made)}</td>
            </tr>
          ))}
        </tbody>
      </TableShell>
    </div>
  );
}
