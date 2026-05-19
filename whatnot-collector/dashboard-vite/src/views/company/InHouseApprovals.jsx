import { useEffect, useMemo, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import { EmptyRow, GhostBtn, KpiCard, PrimaryBtn, SearchInput, TableShell, Thead } from './utils';

const fmt = (n) => (n == null ? '--' : `$${Number(n).toFixed(2)}`);
const fmtQty = (n) => (n == null ? '--' : Number(n).toLocaleString());
const statusTone = {
  pending_approval: { bg: 'rgba(245,158,11,0.12)', fg: 'var(--accent-amber)' },
  approved: { bg: 'rgba(16,185,129,0.12)', fg: 'var(--accent-emerald)' },
  rejected: { bg: 'rgba(239,68,68,0.12)', fg: 'var(--accent-coral)' },
};

export default function InHouseApprovals() {
  const [orders, setOrders] = useState([]);
  const [summary, setSummary] = useState({});
  const [employees, setEmployees] = useState([]);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [tokenLinks, setTokenLinks] = useState({});
  const [loading, setLoading] = useState(false);

  async function load(orderIdToKeep) {
    setLoading(true);
    try {
      const [ordersData, salesData] = await Promise.all([
        fetchApi('/api/in_house_orders'),
        fetchApi('/api/in_house_sales'),
      ]);
      setOrders(ordersData.rows || []);
      setSummary(ordersData.summary || {});
      setEmployees(salesData.employees || []);
      const chosenId = orderIdToKeep || selectedOrder?.id;
      if (chosenId) {
        const detail = await fetchApi(`/api/in_house_orders/detail?id=${chosenId}`);
        setSelectedOrder(detail.order || null);
      } else if ((ordersData.rows || [])[0]) {
        const detail = await fetchApi(`/api/in_house_orders/detail?id=${ordersData.rows[0].id}`);
        setSelectedOrder(detail.order || null);
      } else {
        setSelectedOrder(null);
      }
    } catch (error) {
      setMessage(error.message || 'Could not load in-house approval queue.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filteredOrders = useMemo(() => {
    const q = String(query || '').trim().toLowerCase();
    if (!q) return orders;
    return orders.filter((order) => (
      String(order.employee_name || '').toLowerCase().includes(q)
      || String(order.payment_method || '').toLowerCase().includes(q)
      || String(order.status || '').toLowerCase().includes(q)
      || String(order.id || '').includes(q)
    ));
  }, [orders, query]);

  const grouped = useMemo(() => ({
    pending_approval: filteredOrders.filter((row) => row.status === 'pending_approval'),
    approved: filteredOrders.filter((row) => row.status === 'approved'),
    rejected: filteredOrders.filter((row) => row.status === 'rejected'),
  }), [filteredOrders]);

  async function pickOrder(orderId) {
    try {
      const detail = await fetchApi(`/api/in_house_orders/detail?id=${orderId}`);
      setSelectedOrder(detail.order || null);
    } catch (error) {
      setMessage(error.message || 'Could not open order.');
    }
  }

  async function act(orderId, action) {
    setBusyId(orderId);
    setMessage('');
    try {
      if (action === 'approve') {
        await postApi('/api/in_house_orders/approve', { id: orderId, approved_by: 'manager' });
      } else if (action === 'reject') {
        const reason = window.prompt('Reason for rejection?', 'Needs manager review') || '';
        await postApi('/api/in_house_orders/reject', { id: orderId, rejected_by: 'manager', rejection_reason: reason });
      } else if (action === 'cancel') {
        await postApi('/api/in_house_orders/cancel', { id: orderId });
      }
      await load(orderId);
    } catch (error) {
      setMessage(error.message || `Could not ${action} order.`);
    } finally {
      setBusyId(null);
    }
  }

  async function createToken(employee) {
    try {
      const data = await postApi('/api/employees/pos_token/create', {
        employee_id: employee.id,
        device_label: `${employee.name} mobile POS`,
      });
      const link = `${window.location.origin}/internal-pos?token=${data?.token?.token || ''}`;
      setTokenLinks((current) => ({ ...current, [employee.id]: link }));
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link);
        setMessage(`Mobile POS link copied for ${employee.name}.`);
      } else {
        setMessage(`Mobile POS link created for ${employee.name}.`);
      }
    } catch (error) {
      setMessage(error.message || 'Could not create mobile POS link.');
    }
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
        <KpiCard label="Pending Approval" value={summary.pending_count ?? 0} sub={`${fmt(summary.pending_value || 0)} waiting`} color="var(--accent-amber)" />
        <KpiCard label="Approved Orders" value={summary.approved_count ?? 0} sub={`${fmt(summary.approved_value || 0)} approved`} color="var(--accent-emerald)" />
        <KpiCard label="Rejected" value={summary.rejected_count ?? 0} />
        <KpiCard label="Employee Accounts" value={employees.length} />
      </div>

      <section style={panelStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <div>
            <div style={eyebrowStyle}>Manager Queue</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>Employees submit from mobile. Inventory only deducts when you approve.</div>
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <SearchInput value={query} onChange={setQuery} placeholder="Search employee, status, order..." />
            <GhostBtn onClick={() => load(selectedOrder?.id)}>Refresh</GhostBtn>
          </div>
        </div>
        {message ? <div style={{ fontSize: 13, color: message.toLowerCase().includes('could not') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{message}</div> : null}
      </section>

      <div style={{ display: 'grid', gridTemplateColumns: '360px minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <section style={{ ...panelStyle, gap: 12 }}>
          <div style={eyebrowStyle}>Employee POS Links</div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Generate one-tap mobile order links for each employee. These are ready for QR codes later.</div>
          <div style={{ display: 'grid', gap: 10, maxHeight: 'calc(100vh - 280px)', overflowY: 'auto' }}>
            {employees.length ? employees.map((employee) => (
              <div key={employee.id} style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: 12, display: 'grid', gap: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                  <div>
                    <div style={{ fontWeight: 800 }}>{employee.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{employee.sale_count || 0} in-house sales · {fmt(employee.revenue || 0)}</div>
                  </div>
                  <PrimaryBtn onClick={() => createToken(employee)} style={{ padding: '7px 12px' }}>Create Link</PrimaryBtn>
                </div>
                {tokenLinks[employee.id] ? (
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', wordBreak: 'break-all' }}>{tokenLinks[employee.id]}</div>
                ) : null}
              </div>
            )) : <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>No employee accounts yet.</div>}
          </div>
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 16 }}>
          {[
            { key: 'pending_approval', title: 'Pending Approval' },
            { key: 'approved', title: 'Approved' },
            { key: 'rejected', title: 'Rejected' },
          ].map((column) => (
            <section key={column.key} style={{ ...panelStyle, minHeight: 320 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                <div style={eyebrowStyle}>{column.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{grouped[column.key].length}</div>
              </div>
              <div style={{ display: 'grid', gap: 12 }}>
                {grouped[column.key].length ? grouped[column.key].map((order) => (
                  <button
                    key={order.id}
                    type="button"
                    onClick={() => pickOrder(order.id)}
                    style={{
                      border: selectedOrder?.id === order.id ? '1px solid rgba(59,130,246,0.35)' : '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-lg)',
                      padding: 12,
                      display: 'grid',
                      gap: 8,
                      background: selectedOrder?.id === order.id ? 'rgba(59,130,246,0.06)' : 'var(--bg-panel)',
                      textAlign: 'left',
                      cursor: 'pointer',
                      color: 'inherit',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                      <div style={{ fontWeight: 800 }}>{order.employee_name}</div>
                      <StatusPill status={order.status} />
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{fmtQty(order.units_requested)} units · {order.line_count} lines · {fmt(order.total_amount)}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{order.payment_method || 'payroll'} · Order #{order.id}</div>
                    {order.status === 'pending_approval' ? (
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <PrimaryBtn onClick={(event) => { event.stopPropagation(); act(order.id, 'approve'); }} disabled={busyId === order.id} style={{ padding: '7px 12px' }}>
                          {busyId === order.id ? 'Working...' : 'Approve'}
                        </PrimaryBtn>
                        <GhostBtn onClick={(event) => { event.stopPropagation(); act(order.id, 'reject'); }} style={{ padding: '7px 12px' }}>Reject</GhostBtn>
                      </div>
                    ) : null}
                  </button>
                )) : (
                  <div style={{ color: 'var(--text-secondary)', fontSize: 13, padding: '8px 0' }}>
                    {loading ? 'Loading…' : 'No orders in this column.'}
                  </div>
                )}
              </div>
            </section>
          ))}
        </div>
      </div>

      <section style={panelStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <div style={eyebrowStyle}>Selected Order</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 4 }}>
              {selectedOrder ? `${selectedOrder.employee_name} · ${selectedOrder.payment_method} · ${fmt(selectedOrder.total_amount)}` : 'Pick an order to inspect lines before approval.'}
            </div>
          </div>
          {selectedOrder && selectedOrder.status === 'pending_approval' ? (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <PrimaryBtn onClick={() => act(selectedOrder.id, 'approve')} disabled={busyId === selectedOrder.id}>
                {busyId === selectedOrder.id ? 'Approving...' : 'Approve Order'}
              </PrimaryBtn>
              <GhostBtn onClick={() => act(selectedOrder.id, 'reject')}>Reject</GhostBtn>
              <GhostBtn onClick={() => act(selectedOrder.id, 'cancel')}>Cancel</GhostBtn>
            </div>
          ) : null}
        </div>

        <TableShell footer={selectedOrder ? `${selectedOrder.line_count || 0} lines · ${fmtQty(selectedOrder.units_requested || 0)} units requested` : 'No order selected'}>
          <Thead cols={[
            { label: 'Product' },
            { label: 'Code' },
            { label: 'Qty', align: 'right' },
            { label: 'Employee Price', align: 'right' },
            { label: 'On Hand', align: 'right' },
            { label: 'Total', align: 'right' },
          ]} />
          <tbody>
            {!selectedOrder?.lines?.length ? <EmptyRow cols={6} msg="No order lines yet." loading={loading} /> : null}
            {(selectedOrder?.lines || []).map((line) => (
              <tr key={line.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                <td style={tdStrong}>{line.description}</td>
                <td style={tdMono}>{line.barcode || line.sku || '--'}</td>
                <td style={tdRight}>{fmtQty(line.qty)}</td>
                <td style={tdRight}>{fmt(line.unit_price)}</td>
                <td style={{ ...tdRight, color: Number(line.on_hand_qty || 0) <= Number(line.low_stock_threshold || 3) ? 'var(--accent-coral)' : 'var(--text-primary)', fontWeight: 800 }}>{fmtQty(line.on_hand_qty)}</td>
                <td style={{ ...tdRight, color: 'var(--accent-amber)', fontWeight: 800 }}>{fmt(line.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </TableShell>
      </section>
    </div>
  );
}

function StatusPill({ status }) {
  const tone = statusTone[status] || { bg: 'rgba(148,163,184,0.12)', fg: 'var(--text-secondary)' };
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', borderRadius: 999, padding: '4px 9px', fontSize: 11, fontWeight: 900, background: tone.bg, color: tone.fg, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
      {String(status || 'draft').replace(/_/g, ' ')}
    </span>
  );
}

const panelStyle = {
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-xl)',
  background: 'linear-gradient(135deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94))',
  padding: 16,
  display: 'grid',
  gap: 14,
};

const eyebrowStyle = {
  fontSize: 12,
  fontWeight: 900,
  color: 'var(--text-secondary)',
  letterSpacing: '0.08em',
  textTransform: 'uppercase',
};

const td = { padding: '8px 14px' };
const tdStrong = { ...td, fontWeight: 800 };
const tdMono = { ...td, color: 'var(--text-secondary)', fontSize: 12, fontFamily: 'var(--font-mono)' };
const tdRight = { ...td, textAlign: 'right' };
