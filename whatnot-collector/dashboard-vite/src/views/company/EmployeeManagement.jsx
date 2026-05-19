import { useEffect, useMemo, useState } from 'react';
import { fetchApi, postApi } from '../../hooks/useApi';
import { EmptyRow, GhostBtn, KpiCard, PrimaryBtn, SearchInput, TableShell, Thead } from './utils';

const fmt = (n) => (n == null ? '--' : `$${Number(n).toFixed(2)}`);
const fmtQty = (n) => (n == null ? '--' : Number(n).toLocaleString());
const fmtDt = (value) => {
  if (!value) return '—';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return '—';
  return dt.toLocaleString();
};

const EMPLOYEE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'access', label: 'Access' },
  { id: 'sessions', label: 'Sessions' },
  { id: 'activity', label: 'Activity' },
  { id: 'sales', label: 'Internal Sales' },
];

function normalizeText(value) {
  return String(value || '').trim().toLowerCase();
}

function countBy(rows, status) {
  return rows.filter((row) => normalizeText(row.status) === normalizeText(status)).length;
}

function MiniStat({ label, value, tone = 'default', helper }) {
  const tones = {
    default: { bg: 'rgba(255,255,255,0.84)', border: 'rgba(226,232,240,0.92)', color: 'var(--text-primary)' },
    amber: { bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.18)', color: 'var(--accent-amber)' },
    emerald: { bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.16)', color: 'var(--accent-emerald)' },
    coral: { bg: 'rgba(239,68,68,0.09)', border: 'rgba(239,68,68,0.16)', color: 'var(--accent-coral)' },
    blue: { bg: 'rgba(59,130,246,0.10)', border: 'rgba(59,130,246,0.16)', color: '#2563eb' },
    plum: { bg: 'rgba(124,58,237,0.10)', border: 'rgba(124,58,237,0.16)', color: '#7c3aed' },
  };
  const theme = tones[tone] || tones.default;
  return (
    <div style={{ border: `1px solid ${theme.border}`, background: theme.bg, borderRadius: 18, padding: '14px 16px', display: 'grid', gap: 6 }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: '-0.04em', color: theme.color }}>{value}</div>
      {helper ? <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{helper}</div> : null}
    </div>
  );
}

function StatusPill({ label, tone = 'default' }) {
  const tones = {
    default: { bg: 'rgba(148,163,184,0.12)', color: 'var(--text-secondary)' },
    amber: { bg: 'rgba(245,158,11,0.12)', color: 'var(--accent-amber)' },
    emerald: { bg: 'rgba(16,185,129,0.12)', color: 'var(--accent-emerald)' },
    coral: { bg: 'rgba(239,68,68,0.12)', color: 'var(--accent-coral)' },
    blue: { bg: 'rgba(59,130,246,0.12)', color: '#2563eb' },
    plum: { bg: 'rgba(124,58,237,0.12)', color: '#7c3aed' },
  };
  const theme = tones[tone] || tones.default;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', padding: '5px 10px', borderRadius: 999, background: theme.bg, color: theme.color, fontSize: 11, fontWeight: 800 }}>
      {label}
    </span>
  );
}

function SectionCard({ eyebrow, title, description, actions, children }) {
  return (
    <section style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94))', padding: 18, display: 'grid', gap: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div style={{ minWidth: 0 }}>
          {eyebrow ? <div style={{ fontSize: 11, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.10em', textTransform: 'uppercase', marginBottom: 6 }}>{eyebrow}</div> : null}
          {title ? <div style={{ fontSize: 22, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>{title}</div> : null}
          {description ? <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 760 }}>{description}</div> : null}
        </div>
        {actions ? <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export default function EmployeeManagement() {
  const [employees, setEmployees] = useState([]);
  const [salesRows, setSalesRows] = useState([]);
  const [salesSummary, setSalesSummary] = useState({});
  const [ordersRows, setOrdersRows] = useState([]);
  const [ordersSummary, setOrdersSummary] = useState({});
  const [authEnabled, setAuthEnabled] = useState(false);
  const [loginUsers, setLoginUsers] = useState([]);
  const [loginSessions, setLoginSessions] = useState([]);
  const [loginActivity, setLoginActivity] = useState([]);
  const [posTokens, setPosTokens] = useState([]);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [query, setQuery] = useState('');
  const [directoryFilter, setDirectoryFilter] = useState('all');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [tokenLinks, setTokenLinks] = useState({});
  const [qrPreview, setQrPreview] = useState(null);
  const [employeePolicyForm, setEmployeePolicyForm] = useState({
    autoApproveInHouseOrders: false,
    allowSelfServiceReturns: false,
  });
  const [loginForm, setLoginForm] = useState({ email: '', password: '', role: 'staff', active: true });
  const [quickCreateForm, setQuickCreateForm] = useState({ display_name: '', email: '', password: '', role: 'staff' });

  async function load() {
    setLoading(true);
    setMessage('');
    try {
      const [salesData, ordersData, loginData, tokenData] = await Promise.all([
        fetchApi('/api/in_house_sales'),
        fetchApi('/api/in_house_orders'),
        fetchApi('/api/employee_logins').catch(() => ({ auth_enabled: false, users: [], sessions: [], activity: [] })),
        fetchApi('/api/employees/pos_tokens').catch(() => ({ rows: [] })),
      ]);
      setEmployees(salesData?.employees || []);
      setSalesRows(salesData?.rows || []);
      setSalesSummary(salesData?.summary || {});
      setOrdersRows(ordersData?.rows || []);
      setOrdersSummary(ordersData?.summary || {});
      setAuthEnabled(!!loginData?.auth_enabled);
      setLoginUsers(loginData?.users || []);
      setLoginSessions(loginData?.sessions || []);
      setLoginActivity(loginData?.activity || []);
      setPosTokens(tokenData?.rows || []);
    } catch (error) {
      setMessage(error.message || 'Could not load employee management.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const employeeEnriched = useMemo(() => {
    const merged = employees.map((employee) => {
      const employeeName = normalizeText(employee.name);
      const login = loginUsers.find((user) => (
        normalizeText(user.display_name) === employeeName
        || normalizeText(user.email).split('@')[0] === employeeName.replace(/\s+/g, '')
        || normalizeText(user.email).includes(employeeName.replace(/\s+/g, '.'))
      )) || null;

      const orders = ordersRows.filter((row) => (
        String(row.employee_id || '') === String(employee.id)
        || normalizeText(row.employee_name) === employeeName
      ));
      const sales = salesRows.filter((row) => (
        String(row.employee_id || '') === String(employee.id)
        || normalizeText(row.employee_name) === employeeName
      ));
      const sessions = login?.email ? loginSessions.filter((row) => normalizeText(row.email) === normalizeText(login.email)) : [];
      return { ...employee, login, orders, sales, sessions };
    });

    loginUsers.forEach((user) => {
      const userName = normalizeText(user.display_name || user.email || '');
      const exists = merged.some((employee) => (
        normalizeText(employee.name) === userName
        || normalizeText(employee.login?.email) === normalizeText(user.email)
      ));
      if (exists) return;
      const sessions = user.email ? loginSessions.filter((row) => normalizeText(row.email) === normalizeText(user.email)) : [];
      merged.push({
        id: `login:${user.email}`,
        name: user.display_name || user.email,
        sale_count: 0,
        revenue: 0,
        units_sold: 0,
        last_sale_at: null,
        login: user,
        orders: [],
        sales: [],
        sessions,
      });
    });

    return merged;
  }, [employees, loginUsers, ordersRows, salesRows, loginSessions]);

  const filteredEmployees = useMemo(() => {
    const q = normalizeText(query);
    return employeeEnriched.filter((employee) => {
      if (q) {
        const matches = normalizeText(employee.name).includes(q)
          || String(employee.id || '').includes(q)
          || normalizeText(employee.login?.email).includes(q)
          || normalizeText(employee.login?.role).includes(q);
        if (!matches) return false;
      }
      if (directoryFilter === 'missing-login') return !employee.login;
      if (directoryFilter === 'mfa-off') return !!employee.login && !employee.login.mfa_enabled;
      if (directoryFilter === 'admins') return employee.login?.role === 'admin';
      if (directoryFilter === 'online') return (employee.sessions || []).length > 0;
      return true;
    });
  }, [employeeEnriched, query, directoryFilter]);

  useEffect(() => {
    if (!selectedEmployee && filteredEmployees.length) {
      setSelectedEmployee(filteredEmployees[0]);
      return;
    }
    if (selectedEmployee && !filteredEmployees.some((employee) => employee.id === selectedEmployee.id)) {
      setSelectedEmployee(filteredEmployees[0] || null);
    }
  }, [filteredEmployees, selectedEmployee]);

  const selected = useMemo(() => {
    if (!selectedEmployee) return null;
    return employeeEnriched.find((employee) => employee.id === selectedEmployee.id) || null;
  }, [employeeEnriched, selectedEmployee]);

  const selectedLogin = selected?.login || null;
  const selectedOrders = selected?.orders || [];
  const selectedSales = selected?.sales || [];
  const selectedSessions = selected?.sessions || [];
  const selectedPosTokens = useMemo(() => {
    if (!selected) return [];
    return posTokens.filter((row) => String(row.employee_id || '') === String(selected.id));
  }, [posTokens, selected]);
  const activePosTokens = selectedPosTokens.filter((row) => row.active && !row.expired);
  const selectedActivity = useMemo(() => {
    const selectedEmail = selectedLogin?.email || '';
    if (!selectedLogin?.email && !selected?.name) return [];
    return loginActivity.filter((row) => (
      normalizeText(row.email) === normalizeText(selectedEmail)
      || normalizeText(row.target_email) === normalizeText(selectedEmail)
      || normalizeText(row.actor_email) === normalizeText(selectedEmail)
      || normalizeText(row.employee_name) === normalizeText(selected?.name)
      || String(row.employee_id || '') === String(selected?.id || '')
    )).slice(0, 30);
  }, [loginActivity, selected, selectedLogin]);

  useEffect(() => {
    if (!selected) return;
    setLoginForm((current) => ({
      ...current,
      email: selectedLogin?.email || `${normalizeText(selected.name).replace(/\s+/g, '.')}@ynfdeals.com`,
      role: selectedLogin?.role || 'staff',
      active: selectedLogin ? selectedLogin.active !== false : true,
      password: '',
    }));
  }, [selected?.id, selectedLogin?.email, selectedLogin?.role, selectedLogin?.active]);

  useEffect(() => {
    if (!selected) return;
    setEmployeePolicyForm({
      autoApproveInHouseOrders: !!selected.auto_approve_in_house_orders,
      allowSelfServiceReturns: !!selected.allow_self_service_returns,
    });
  }, [selected?.id, selected?.auto_approve_in_house_orders, selected?.allow_self_service_returns]);

  async function createToken(employee) {
    setBusyId(`token-${employee.id}`);
    setMessage('');
    try {
      const data = await postApi('/api/employees/pos_token/create', {
        employee_id: employee.id,
        device_label: `${employee.name} mobile POS`,
      });
      const link = `${window.location.origin}/internal-pos?token=${data?.token?.token || ''}`;
      setTokenLinks((current) => ({ ...current, [employee.id]: link }));
      setPosTokens((current) => [data.token, ...current.filter((row) => row.id !== data?.token?.id)]);
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(link);
      setMessage(`Mobile POS link ready for ${employee.name}.`);
    } catch (error) {
      setMessage(error.message || 'Could not create employee POS link.');
    } finally {
      setBusyId(null);
    }
  }

  async function revokeToken(token) {
    if (!token?.id) return;
    setBusyId(`revoke-token-${token.id}`);
    setMessage('');
    try {
      const data = await postApi('/api/employees/pos_token/revoke', { id: token.id });
      setPosTokens((current) => current.map((row) => (row.id === token.id ? data.token : row)));
      setMessage('POS token revoked.');
    } catch (error) {
      setMessage(error.message || 'Could not revoke POS token.');
    } finally {
      setBusyId(null);
    }
  }

  async function rotateToken(token) {
    if (!token?.id || !selected) return;
    setBusyId(`rotate-token-${token.id}`);
    setMessage('');
    try {
      const data = await postApi('/api/employees/pos_token/rotate', {
        id: token.id,
        device_label: token.device_label || `${selected.name} mobile POS`,
      });
      const link = `${window.location.origin}/internal-pos?token=${data?.token?.token || ''}`;
      setTokenLinks((current) => ({ ...current, [selected.id]: link }));
      setPosTokens((current) => [data.token, ...current.map((row) => (row.id === token.id ? { ...row, active: 0 } : row))]);
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(link);
      setMessage('POS token rotated and copied.');
    } catch (error) {
      setMessage(error.message || 'Could not rotate POS token.');
    } finally {
      setBusyId(null);
    }
  }

  async function showQr(title, link) {
    if (!link) return;
    setBusyId(`qr-${title}`);
    setMessage('');
    try {
      const data = await fetchApi(`/api/qr_code?value=${encodeURIComponent(link)}`);
      setQrPreview({
        title,
        link,
        qrCodeDataUrl: data?.qr_code_data_url || '',
      });
    } catch (error) {
      setMessage(error.message || 'Could not generate QR code.');
    } finally {
      setBusyId(null);
    }
  }

  async function saveLogin() {
    if (!selected) return;
    setBusyId(`login-${selected.id}`);
    setMessage('');
    try {
      await postApi('/api/employee_logins/upsert', {
        email: loginForm.email,
        display_name: selected.name,
        password: loginForm.password,
        role: loginForm.role,
        active: loginForm.active,
      });
      setMessage(`Login credentials updated for ${selected.name}.`);
      await load();
    } catch (error) {
      setMessage(error.message || 'Could not save login credentials.');
    } finally {
      setBusyId(null);
    }
  }

  async function saveEmployeePolicy() {
    if (!selected?.id || String(selected.id).startsWith('login:')) return;
    setBusyId(`policy-${selected.id}`);
    setMessage('');
    try {
      await postApi('/api/employees/settings', {
        employee_id: selected.id,
        auto_approve_in_house_orders: employeePolicyForm.autoApproveInHouseOrders,
        allow_self_service_returns: employeePolicyForm.allowSelfServiceReturns,
      });
      setMessage(`Trusted workflow updated for ${selected.name}.`);
      await load();
    } catch (error) {
      setMessage(error.message || 'Could not update employee policy.');
    } finally {
      setBusyId(null);
    }
  }

  async function createStaffUser() {
    setBusyId('quick-create');
    setMessage('');
    try {
      await postApi('/api/employee_logins/upsert', {
        email: quickCreateForm.email,
        display_name: quickCreateForm.display_name,
        password: quickCreateForm.password,
        role: quickCreateForm.role,
        active: true,
      });
      setQuickCreateForm({ display_name: '', email: '', password: '', role: 'staff' });
      setMessage('Staff user created.');
      await load();
    } catch (error) {
      setMessage(error.message || 'Could not create staff user.');
    } finally {
      setBusyId(null);
    }
  }

  async function revokeSelectedSessions() {
    if (!selectedLogin?.email) return;
    setBusyId(`revoke-${selectedLogin.email}`);
    setMessage('');
    try {
      const result = await postApi('/api/employee_logins/revoke_sessions', { email: selectedLogin.email });
      setMessage(`Revoked ${result?.revoked || 0} active session(s) for ${selected?.name || selectedLogin.email}.`);
      await load();
    } catch (error) {
      setMessage(error.message || 'Could not revoke sessions.');
    } finally {
      setBusyId(null);
    }
  }

  const totals = useMemo(() => {
    const withLogins = employeeEnriched.filter((employee) => employee.login).length;
    const mfaEnabled = employeeEnriched.filter((employee) => employee.login?.mfa_enabled).length;
    const online = employeeEnriched.filter((employee) => (employee.sessions || []).length > 0).length;
    return { withLogins, mfaEnabled, online };
  }, [employeeEnriched]);

  const orderCols = [
    { label: 'Order #' },
    { label: 'Status' },
    { label: 'Payment' },
    { label: 'Units', align: 'right' },
    { label: 'Total', align: 'right' },
    { label: 'Submitted' },
  ];

  const saleCols = [
    { label: 'Sold At' },
    { label: 'Product' },
    { label: 'Qty', align: 'right' },
    { label: 'Employee Price', align: 'right' },
    { label: 'Total', align: 'right' },
  ];

  const sessionCols = [
    { label: 'Device / IP' },
    { label: 'Started' },
    { label: 'Idle Expiry' },
  ];

  const activityCols = [
    { label: 'Event' },
    { label: 'When' },
    { label: 'Detail' },
  ];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <KpiCard label="Staff Users" value={employeeEnriched.length} />
        <KpiCard label="Can Sign In" value={totals.withLogins} color="var(--accent-amber)" />
        <KpiCard label="MFA Enabled" value={totals.mfaEnabled} color="var(--accent-emerald)" />
        <KpiCard label="Active Sessions" value={loginSessions.length} color="#2563eb" />
        <KpiCard label="Staff Purchases" value={salesSummary.sale_count ?? 0} />
        <KpiCard label="Pending Staff Orders" value={ordersSummary.pending_count ?? 0} color="var(--accent-amber)" />
      </div>

      <SectionCard
        eyebrow="Staff Workspace"
        title="Staff users and access"
        description="Create staff logins fast, then open any person to manage sign-in access, sessions, and staff-purchase history."
        actions={<><SearchInput value={query} onChange={setQuery} placeholder="Search employee, login, role..." /><GhostBtn onClick={load}>Refresh</GhostBtn></>}
      >
        <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 18, padding: 14, background: 'rgba(255,255,255,0.84)', display: 'grid', gap: 12 }}>
          <div>
            <div style={{ fontSize: 12, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Quick Create Staff User</div>
            <div style={{ marginTop: 4, fontSize: 13, color: 'var(--text-secondary)' }}>Just create the login first. Sales and activity can come later.</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.2fr 1fr 160px 160px', gap: 10 }}>
            <input
              value={quickCreateForm.display_name}
              onChange={(event) => setQuickCreateForm((current) => ({ ...current, display_name: event.target.value }))}
              placeholder="Staff name"
              style={inputStyle}
            />
            <input
              value={quickCreateForm.email}
              onChange={(event) => setQuickCreateForm((current) => ({ ...current, email: event.target.value }))}
              placeholder="staff@ynfdeals.com"
              style={inputStyle}
            />
            <input
              type="password"
              value={quickCreateForm.password}
              onChange={(event) => setQuickCreateForm((current) => ({ ...current, password: event.target.value }))}
              placeholder="Temporary password"
              style={inputStyle}
            />
            <select value={quickCreateForm.role} onChange={(event) => setQuickCreateForm((current) => ({ ...current, role: event.target.value }))} style={inputStyle}>
              <option value="staff">Staff</option>
              <option value="admin">Admin</option>
            </select>
            <PrimaryBtn onClick={createStaffUser} disabled={busyId === 'quick-create' || !quickCreateForm.display_name.trim() || !quickCreateForm.email.trim() || !quickCreateForm.password.trim()}>
              {busyId === 'quick-create' ? 'Creating…' : 'Create User'}
            </PrimaryBtn>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[
            { id: 'all', label: 'All staff' },
            { id: 'missing-login', label: 'No login' },
            { id: 'mfa-off', label: 'MFA off' },
            { id: 'admins', label: 'Admins' },
            { id: 'online', label: 'Online now' },
          ].map((filter) => (
            <button
              key={filter.id}
              type="button"
              onClick={() => setDirectoryFilter(filter.id)}
              style={{
                border: directoryFilter === filter.id ? '1px solid rgba(245,158,11,0.28)' : '1px solid var(--border-subtle)',
                background: directoryFilter === filter.id ? 'rgba(245,158,11,0.10)' : 'rgba(255,255,255,0.78)',
                color: directoryFilter === filter.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
                borderRadius: 999,
                padding: '8px 12px',
                fontSize: 12,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
        {message ? <div style={{ fontSize: 13, color: message.toLowerCase().includes('could not') ? 'var(--accent-coral)' : 'var(--accent-emerald)' }}>{message}</div> : null}
      </SectionCard>

      <div style={{ display: 'grid', gridTemplateColumns: '360px minmax(0, 1fr)', gap: 16, alignItems: 'start' }}>
        <section style={{ border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)', background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.94))', overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-subtle)', display: 'grid', gap: 4 }}>
            <div style={{ fontSize: 11, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Staff Directory</div>
            <div style={{ fontSize: 20, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>Team users</div>
          </div>

          <div style={{ display: 'grid', gap: 10, padding: 12, maxHeight: 'calc(100vh - 320px)', overflowY: 'auto' }}>
            {filteredEmployees.length ? filteredEmployees.map((employee) => {
              const active = selected?.id === employee.id;
              const loginTone = !employee.login ? 'amber' : employee.login.active === false ? 'coral' : 'emerald';
              const statusLabel = !employee.login ? 'No login' : employee.login.active === false ? 'Disabled' : 'Active';
              return (
                <button
                  key={employee.id}
                  type="button"
                  onClick={() => {
                    setSelectedEmployee(employee);
                    setActiveTab('overview');
                  }}
                  style={{
                    border: active ? '1px solid rgba(245,158,11,0.34)' : '1px solid var(--border-subtle)',
                    borderRadius: 20,
                    padding: 14,
                    display: 'grid',
                    gap: 10,
                    background: active ? 'linear-gradient(180deg, rgba(245,158,11,0.10), rgba(255,255,255,0.92))' : 'rgba(255,255,255,0.88)',
                    textAlign: 'left',
                    color: 'inherit',
                    cursor: 'pointer',
                    boxShadow: active ? '0 16px 34px rgba(245,158,11,0.10)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 16, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>{employee.name}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)' }}>
                        {employee.login?.email || 'No login email yet'}
                      </div>
                    </div>
                    <span style={{ fontSize: 11, padding: '4px 9px', borderRadius: 999, background: 'rgba(59,130,246,0.12)', color: '#2563eb', fontWeight: 800 }}>#{employee.id}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <StatusPill label={statusLabel} tone={loginTone} />
                    {employee.login?.mfa_enabled ? <StatusPill label="MFA On" tone="plum" /> : <StatusPill label="MFA Off" tone="default" />}
                    {employee.sessions?.length ? <StatusPill label={`${employee.sessions.length} live session${employee.sessions.length === 1 ? '' : 's'}`} tone="blue" /> : null}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 8 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      <strong style={{ color: 'var(--text-primary)' }}>{employee.sale_count || 0}</strong> sales
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', textAlign: 'right' }}>
                      <strong style={{ color: 'var(--accent-amber)' }}>{fmt(employee.revenue || 0)}</strong>
                    </div>
                  </div>
                </button>
              );
            }) : (
              <div style={{ padding: 18, color: 'var(--text-secondary)', fontSize: 13 }}>
                {loading ? 'Loading employees…' : 'No employees matched this filter.'}
              </div>
            )}
          </div>
        </section>

        <div style={{ display: 'grid', gap: 16 }}>
          <SectionCard
            eyebrow="Selected Staff User"
            title={selected?.name || 'Select a staff user'}
            description={selected ? 'Use the tabs below to manage sign-in access, security posture, active sessions, audit history, and staff-purchase activity.' : 'Pick someone from the left directory to open their login and activity workspace.'}
            actions={selected ? (
              <>
                <StatusPill label={selectedLogin ? (selectedLogin.active === false ? 'Login disabled' : 'Can sign in') : 'No login yet'} tone={!selectedLogin ? 'amber' : selectedLogin.active === false ? 'coral' : 'emerald'} />
                {selectedLogin?.role ? <StatusPill label={selectedLogin.role} tone="blue" /> : null}
                {selectedLogin?.mfa_enabled ? <StatusPill label="MFA enabled" tone="plum" /> : null}
                {!!selected?.auto_approve_in_house_orders ? <StatusPill label="Trusted auto-approve" tone="emerald" /> : null}
                {!!selected?.allow_self_service_returns ? <StatusPill label="Self returns allowed" tone="blue" /> : null}
              </>
            ) : null}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
              <MiniStat label="Revenue at cost" value={fmt(selected?.revenue || 0)} tone="amber" helper={selected?.last_sale_at ? `Last sale ${fmtDt(selected.last_sale_at)}` : 'No recorded sale yet'} />
              <MiniStat label="Recorded sales" value={selected?.sale_count || 0} helper={`${fmtQty(selected?.units_sold || 0)} units sold`} />
              <MiniStat label="Pending approvals" value={countBy(selectedOrders, 'pending_approval')} tone="amber" helper="Orders waiting for manager review" />
              <MiniStat label="Live sessions" value={selectedSessions.length} tone={selectedSessions.length ? 'blue' : 'default'} helper={selectedLogin?.email || 'No linked login account'} />
              <MiniStat label="Purchase autonomy" value={selected?.auto_approve_in_house_orders ? 'Trusted' : 'Review'} tone={selected?.auto_approve_in_house_orders ? 'emerald' : 'amber'} helper={selected?.auto_approve_in_house_orders ? 'Employee purchases approve automatically' : 'Manager approval still required'} />
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {EMPLOYEE_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  style={{
                    border: activeTab === tab.id ? '1px solid rgba(245,158,11,0.28)' : '1px solid var(--border-subtle)',
                    background: activeTab === tab.id ? 'rgba(245,158,11,0.10)' : 'rgba(255,255,255,0.8)',
                    color: activeTab === tab.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
                    borderRadius: 999,
                    padding: '8px 13px',
                    fontSize: 12,
                    fontWeight: 800,
                    cursor: 'pointer',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </SectionCard>

          {!selected ? (
            <SectionCard eyebrow="Staff Workspace" title="No staff user selected" description="Choose someone from the left directory and we’ll show their login access, sessions, activity, and staff-order history here." />
          ) : null}

          {selected && activeTab === 'overview' ? (
            <SectionCard
              eyebrow="Overview"
              title="Employee snapshot"
              description="A quick view of login readiness, active sessions, and internal sales signals."
              actions={
                <>
                  <PrimaryBtn onClick={() => createToken(selected)} disabled={busyId === `token-${selected.id}`}>
                    {busyId === `token-${selected.id}` ? 'Creating…' : 'Create Mobile POS Link'}
                  </PrimaryBtn>
                  {tokenLinks[selected.id] ? <GhostBtn onClick={() => navigator.clipboard?.writeText(tokenLinks[selected.id])}>Copy POS Link</GhostBtn> : null}
                  <GhostBtn onClick={() => showQr('Self-Checkout', `${window.location.origin}/self-checkout`)} disabled={busyId === 'qr-Self-Checkout'}>
                    {busyId === 'qr-Self-Checkout' ? 'Opening QR…' : 'Self-Checkout QR'}
                  </GhostBtn>
                </>
              }
            >
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 16 }}>
                <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 20, background: 'rgba(255,255,255,0.82)', padding: 16, display: 'grid', gap: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Access Summary</div>
                  <div style={{ display: 'grid', gap: 10 }}>
                    <div style={summaryRowStyle}><span>Login email</span><strong>{selectedLogin?.email || 'Not created yet'}</strong></div>
                    <div style={summaryRowStyle}><span>Login role</span><strong>{selectedLogin?.role || 'staff'}</strong></div>
                    <div style={summaryRowStyle}><span>MFA status</span><strong>{selectedLogin?.mfa_enabled ? 'Enabled' : 'Off'}</strong></div>
                    <div style={summaryRowStyle}><span>Last login</span><strong>{selectedLogin?.last_login_at ? fmtDt(selectedLogin.last_login_at) : 'No recent login'}</strong></div>
                    <div style={summaryRowStyle}><span>Live sessions</span><strong>{selectedSessions.length}</strong></div>
                    <div style={summaryRowStyle}><span>Active POS tokens</span><strong>{activePosTokens.length}</strong></div>
                  </div>
                </div>

                <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 20, background: 'rgba(255,255,255,0.82)', padding: 16, display: 'grid', gap: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>POS Access</div>
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                    Generate a dedicated mobile POS entry link for this employee so they can place internal orders from their own phone.
                  </div>
                  {tokenLinks[selected.id] ? (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', wordBreak: 'break-all', padding: 10, borderRadius: 14, background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.16)' }}>
                      {tokenLinks[selected.id]}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>No active POS link generated in this session yet.</div>
                  )}
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {tokenLinks[selected.id] ? (
                      <GhostBtn onClick={() => showQr(`${selected.name} POS`, tokenLinks[selected.id])} disabled={busyId === `qr-${selected.name} POS`}>
                        {busyId === `qr-${selected.name} POS` ? 'Opening QR…' : 'Show POS QR'}
                      </GhostBtn>
                    ) : null}
                    <GhostBtn onClick={() => showQr('Self-Checkout', `${window.location.origin}/self-checkout`)} disabled={busyId === 'qr-Self-Checkout'}>
                      {busyId === 'qr-Self-Checkout' ? 'Opening QR…' : 'Show Self-Checkout QR'}
                    </GhostBtn>
                  </div>
                  {qrPreview ? (
                    <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 18, padding: 14, background: 'rgba(255,255,255,0.92)', display: 'grid', gap: 10, justifyItems: 'center' }}>
                      <div style={{ width: '100%', display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                        <div>
                          <div style={{ fontSize: 11, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>QR Code</div>
                          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>{qrPreview.title}</div>
                        </div>
                        <GhostBtn onClick={() => setQrPreview(null)}>Close</GhostBtn>
                      </div>
                      {qrPreview.qrCodeDataUrl ? (
                        <img src={qrPreview.qrCodeDataUrl} alt={`${qrPreview.title} QR`} style={{ width: 220, maxWidth: '100%', borderRadius: 18, background: 'white', padding: 8, border: '1px solid var(--border-subtle)' }} />
                      ) : null}
                      <div style={{ fontSize: 12, color: 'var(--text-secondary)', wordBreak: 'break-all', textAlign: 'center' }}>{qrPreview.link}</div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
                        <GhostBtn onClick={() => navigator.clipboard?.writeText(qrPreview.link)}>Copy Link</GhostBtn>
                      </div>
                    </div>
                  ) : null}
                  <div style={{ display: 'grid', gap: 8 }}>
                    {selectedPosTokens.slice(0, 5).map((token) => {
                      const active = !!token.active && !token.expired;
                      return (
                        <div key={token.id} style={{ display: 'grid', gap: 8, padding: 10, borderRadius: 14, border: '1px solid var(--border-subtle)', background: 'rgba(255,255,255,0.72)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                            <StatusPill label={active ? 'Active' : token.expired ? 'Expired' : 'Revoked'} tone={active ? 'emerald' : token.expired ? 'amber' : 'coral'} />
                            <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>#{token.id}</span>
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            {token.device_label || 'Mobile POS'} · expires {fmtDt(token.expires_at)}
                          </div>
                          {active ? (
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              <GhostBtn onClick={() => rotateToken(token)} disabled={busyId === `rotate-token-${token.id}`}>{busyId === `rotate-token-${token.id}` ? 'Rotating…' : 'Rotate'}</GhostBtn>
                              <GhostBtn onClick={() => revokeToken(token)} disabled={busyId === `revoke-token-${token.id}`}>{busyId === `revoke-token-${token.id}` ? 'Revoking…' : 'Revoke'}</GhostBtn>
                            </div>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              {!String(selected.id).startsWith('login:') ? (
                <div style={{ border: '1px solid rgba(16,185,129,0.18)', borderRadius: 20, background: 'linear-gradient(180deg, rgba(16,185,129,0.08), rgba(255,255,255,0.94))', padding: 16, display: 'grid', gap: 14 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 900, color: 'var(--text-secondary)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Trusted Employee Workflow</div>
                    <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                      Turn this on when you trust this employee to finish normal in-house purchases without waiting for you. We also store a returns permission here so the future self-serve returns flow can follow the same policy.
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
                    <label style={policyCardStyle}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>Auto-approve employee purchases</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            New in-house orders from this employee will approve themselves instead of landing in your pending queue.
                          </div>
                        </div>
                        <input type="checkbox" checked={employeePolicyForm.autoApproveInHouseOrders} onChange={(event) => setEmployeePolicyForm((current) => ({ ...current, autoApproveInHouseOrders: event.target.checked }))} />
                      </div>
                    </label>
                    <label style={policyCardStyle}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--text-primary)' }}>Allow self-service returns</div>
                          <div style={{ marginTop: 4, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                            Saves the trust policy now so we can use it for employee-driven return/exchange tools without making you reconfigure everyone later.
                          </div>
                        </div>
                        <input type="checkbox" checked={employeePolicyForm.allowSelfServiceReturns} onChange={(event) => setEmployeePolicyForm((current) => ({ ...current, allowSelfServiceReturns: event.target.checked }))} />
                      </div>
                    </label>
                  </div>
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    <PrimaryBtn onClick={saveEmployeePolicy} disabled={busyId === `policy-${selected.id}`}>
                      {busyId === `policy-${selected.id}` ? 'Saving…' : 'Save Trust Settings'}
                    </PrimaryBtn>
                    <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {employeePolicyForm.autoApproveInHouseOrders ? 'Employee purchases will bypass manager approval.' : 'Employee purchases still require manager approval.'}
                    </span>
                  </div>
                </div>
              ) : null}
            </SectionCard>
          ) : null}

          {selected && activeTab === 'access' ? (
            <SectionCard
              eyebrow="Staff Login"
              title="Sign-in details"
              description={`Create or update ${selected.name}'s login, reset their password, and disable access if needed.`}
              actions={selectedLogin ? (
                <GhostBtn onClick={revokeSelectedSessions} disabled={busyId === `revoke-${selectedLogin.email}`}>
                  {busyId === `revoke-${selectedLogin.email}` ? 'Revoking…' : 'Revoke All Sessions'}
                </GhostBtn>
              ) : null}
            >
              {!authEnabled ? (
                <div style={{ padding: 14, borderRadius: 16, background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.18)', color: 'var(--accent-amber)', fontSize: 13, fontWeight: 700 }}>
                  Authentication is currently disabled in server settings. Accounts are stored, but login enforcement is not active until auth is enabled.
                </div>
              ) : null}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
                <label>
                  <div style={fieldLabelStyle}>Login email</div>
                  <input value={loginForm.email} onChange={(event) => setLoginForm((current) => ({ ...current, email: event.target.value }))} placeholder="employee@ynfdeals.com" style={inputStyle} />
                </label>
                <label>
                  <div style={fieldLabelStyle}>{selectedLogin ? 'New password' : 'Password'}</div>
                  <input type="password" value={loginForm.password} onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))} placeholder={selectedLogin ? 'Leave blank to keep current password' : 'Set first password'} style={inputStyle} />
                </label>
              </div>
              <details style={{ border: '1px solid var(--border-subtle)', borderRadius: 16, padding: 12, background: 'rgba(255,255,255,0.7)' }}>
                <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 800, color: 'var(--text-primary)' }}>Advanced access options</summary>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, marginTop: 12 }}>
                  <label>
                    <div style={fieldLabelStyle}>Role</div>
                    <select value={loginForm.role} onChange={(event) => setLoginForm((current) => ({ ...current, role: event.target.value }))} style={inputStyle}>
                      <option value="staff">Staff</option>
                      <option value="admin">Admin</option>
                    </select>
                  </label>
                  <label>
                    <div style={fieldLabelStyle}>Account status</div>
                    <select value={loginForm.active ? 'true' : 'false'} onChange={(event) => setLoginForm((current) => ({ ...current, active: event.target.value === 'true' }))} style={inputStyle}>
                      <option value="true">Active</option>
                      <option value="false">Disabled</option>
                    </select>
                  </label>
                </div>
              </details>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                <PrimaryBtn onClick={saveLogin} disabled={!loginForm.email.trim() || busyId === `login-${selected.id}` || (!selectedLogin && !loginForm.password.trim())}>
                  {busyId === `login-${selected.id}` ? 'Saving…' : selectedLogin ? 'Save Changes' : 'Create Login'}
                </PrimaryBtn>
                {selectedLogin ? <StatusPill label={`MFA ${selectedLogin.mfa_enabled ? 'On' : 'Off'}`} tone={selectedLogin.mfa_enabled ? 'plum' : 'default'} /> : null}
                {selectedLogin ? <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Last login {selectedLogin.last_login_at ? fmtDt(selectedLogin.last_login_at) : 'never'}</span> : null}
              </div>
            </SectionCard>
          ) : null}

          {selected && activeTab === 'sessions' ? (
            <SectionCard eyebrow="Sessions" title="Active device sessions" description="See where this employee is currently signed in and revoke access if a device should no longer stay connected.">
              <TableShell footer={selectedLogin ? `${selectedSessions.length} active session${selectedSessions.length === 1 ? '' : 's'} for ${selectedLogin.email}` : 'No linked login account yet'}>
                <Thead cols={sessionCols} />
                <tbody>
                  {loading || !selectedSessions.length ? <EmptyRow cols={sessionCols.length} loading={loading} msg={selectedLogin ? 'No active sessions for this employee.' : 'Create or match a login account first.'} /> : null}
                  {!loading && selectedSessions.map((row) => (
                    <tr key={row.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={td}>
                        <div style={{ color: 'var(--text-primary)', fontWeight: 800 }}>{row.client_ip || 'Unknown IP'}</div>
                        <div style={{ marginTop: 4, fontSize: 11, color: 'var(--text-secondary)', wordBreak: 'break-word' }}>{row.user_agent || 'Unknown browser/device'}</div>
                      </td>
                      <td style={td}>{fmtDt(row.created_at ? new Date(Number(row.created_at) * 1000).toISOString() : null)}</td>
                      <td style={td}>{fmtDt(row.idle_expires_at ? new Date(Number(row.idle_expires_at) * 1000).toISOString() : null)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableShell>
            </SectionCard>
          ) : null}

          {selected && activeTab === 'activity' ? (
            <SectionCard eyebrow="Activity" title="Recent auth audit trail" description="Review login successes, failures, password rotations, revokes, and other auth events tied to this employee.">
              <TableShell footer={selectedLogin ? `${selectedActivity.length} recent auth activity row${selectedActivity.length === 1 ? '' : 's'}` : 'No linked login activity yet'}>
                <Thead cols={activityCols} />
                <tbody>
                  {loading || !selectedActivity.length ? <EmptyRow cols={activityCols.length} loading={loading} msg={selectedLogin ? 'No recorded login activity yet.' : 'Create or match a login account to see activity.'} /> : null}
                  {!loading && selectedActivity.map((row, index) => (
                    <tr key={`${row.ts}-${row.event}-${index}`} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={tdStrong}>{row.event || 'activity'}</td>
                      <td style={td}>{fmtDt(row.ts ? new Date(Number(row.ts) * 1000).toISOString() : null)}</td>
                      <td style={td}>{row.client_ip || row.reason || row.role || row.target_email || row.previous_session_id || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </TableShell>
            </SectionCard>
          ) : null}

          {selected && activeTab === 'sales' ? (
            <div style={{ display: 'grid', gap: 16 }}>
              <SectionCard eyebrow="Approvals" title="In-house order requests" description="Submitted internal orders from this employee, including approval state and payment method.">
                <TableShell footer={`${selectedOrders.length} in-house order${selectedOrders.length === 1 ? '' : 's'} for ${selected.name}`}>
                  <Thead cols={orderCols} />
                  <tbody>
                    {loading || !selectedOrders.length ? <EmptyRow cols={orderCols.length} loading={loading} msg="No in-house orders for this employee yet." /> : null}
                    {!loading && selectedOrders.map((order) => (
                      <tr key={order.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={tdStrong}>#{order.id}</td>
                        <td style={td}>
                          <StatusPill
                            label={order.status}
                            tone={order.status === 'approved' ? 'emerald' : order.status === 'rejected' ? 'coral' : 'amber'}
                          />
                        </td>
                        <td style={td}>{order.payment_method || 'payroll'}</td>
                        <td style={tdRight}>{fmtQty(order.units_requested)}</td>
                        <td style={{ ...tdRight, color: 'var(--accent-amber)', fontWeight: 800 }}>{fmt(order.total_amount)}</td>
                        <td style={td}>{fmtDt(order.submitted_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              </SectionCard>

              <SectionCard eyebrow="Recorded Sales" title="Approved employee purchases" description="Confirmed internal sales tied to this employee, synced into inventory and reporting.">
                <TableShell footer={`${selectedSales.length} recorded sale${selectedSales.length === 1 ? '' : 's'} for ${selected.name}`}>
                  <Thead cols={saleCols} />
                  <tbody>
                    {loading || !selectedSales.length ? <EmptyRow cols={saleCols.length} loading={loading} msg="No recorded in-house sales for this employee yet." /> : null}
                    {!loading && selectedSales.map((row) => (
                      <tr key={row.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <td style={td}>{fmtDt(row.sold_at)}</td>
                        <td style={tdStrong}>{row.product_name}</td>
                        <td style={tdRight}>{fmtQty(row.qty)}</td>
                        <td style={tdRight}>{fmt(row.unit_price)}</td>
                        <td style={{ ...tdRight, color: 'var(--accent-amber)', fontWeight: 800 }}>{fmt(row.subtotal)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableShell>
              </SectionCard>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

const inputStyle = {
  background: 'var(--bg-panel)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-default)',
  borderRadius: 16,
  padding: '10px 12px',
  fontSize: 13,
  minHeight: 40,
  lineHeight: 1.2,
  width: '100%',
  boxSizing: 'border-box',
};

const fieldLabelStyle = {
  fontSize: 12,
  color: 'var(--text-secondary)',
  marginBottom: 6,
  fontWeight: 700,
};

const summaryRowStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: 12,
  alignItems: 'center',
  fontSize: 13,
  color: 'var(--text-secondary)',
  paddingBottom: 10,
  borderBottom: '1px solid var(--border-subtle)',
};

const policyCardStyle = {
  border: '1px solid var(--border-subtle)',
  borderRadius: 18,
  background: 'rgba(255,255,255,0.82)',
  padding: 14,
  display: 'block',
};

const td = { padding: '10px 14px', color: 'var(--text-secondary)', fontSize: 13 };
const tdStrong = { padding: '10px 14px', color: 'var(--text-primary)', fontWeight: 800, fontSize: 13 };
const tdRight = { padding: '10px 14px', textAlign: 'right', color: 'var(--text-secondary)', fontSize: 13 };
