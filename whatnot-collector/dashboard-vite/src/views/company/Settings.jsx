import { useEffect, useState } from 'react';
import {
  BadgeCheck,
  CreditCard,
  KeyRound,
  Laptop2,
  LayoutGrid,
  Percent,
  ShieldCheck,
  ShieldX,
  ShoppingBag,
  Upload,
  UserCog,
  Users,
} from 'lucide-react';
import { fetchApi, postApi } from '../../hooks/useApi';
import { useLocalState } from '../../hooks/useBrowserState';
import { Button } from '../../components/ui/button';
import { Input as UIInput } from '../../components/ui/input';
import { Switch } from '../../components/ui/switch';
import { Tabs as UITabs, TabsList as UITabsList, TabsTrigger as UITabsTrigger } from '../../components/ui/tabs';

const DEFAULT_NAV_VISIBILITY = {
  dashboard: false,
  users: false,
  spectator: false,
  analytics: false,
  competitors: false,
  history: false,
};

const COLORS = {
  pageBg: '#f5f7fb',
  cardBg: '#ffffff',
  cardAlt: '#f8fafc',
  border: '#e2e8f0',
  borderSoft: '#eef2f7',
  text: '#0f172a',
  textMuted: '#64748b',
  textSoft: '#94a3b8',
  indigo: '#4f46e5',
  indigoSoft: '#eef2ff',
  emerald: '#059669',
  emeraldSoft: '#ecfdf5',
  amber: '#d97706',
  amberSoft: '#fffbeb',
  rose: '#dc2626',
  roseSoft: '#fff1f2',
  sky: '#0369a1',
  skySoft: '#f0f9ff',
  shadow: '0 1px 2px rgba(15, 23, 42, 0.04), 0 10px 24px -20px rgba(15, 23, 42, 0.22)',
  shadowSoft: '0 1px 2px rgba(15, 23, 42, 0.04)',
};

function SettingsCard({ eyebrow, title, description, action, children }) {
  return (
    <section
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 10,
        padding: 20,
        boxShadow: COLORS.shadow,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 16,
          flexWrap: 'wrap',
          marginBottom: 20,
        }}
      >
        <div style={{ minWidth: 0 }}>
          {eyebrow ? (
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: '0.18em',
                textTransform: 'uppercase',
                color: COLORS.textSoft,
                marginBottom: 6,
              }}
            >
              {eyebrow}
            </div>
          ) : null}
          <div style={{ fontSize: 21, fontWeight: 750, color: COLORS.text }}>{title}</div>
          {description ? (
            <div style={{ marginTop: 6, maxWidth: 760, fontSize: 14, lineHeight: 1.65, color: COLORS.textMuted }}>{description}</div>
          ) : null}
        </div>
        {action ? <div>{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

function StatusBadge({ tone = 'slate', children }) {
  const map = {
    slate: { bg: '#f1f5f9', border: '#e2e8f0', text: '#475569' },
    indigo: { bg: COLORS.indigoSoft, border: '#c7d2fe', text: '#4338ca' },
    green: { bg: COLORS.emeraldSoft, border: '#a7f3d0', text: '#047857' },
    amber: { bg: COLORS.amberSoft, border: '#fde68a', text: '#b45309' },
    red: { bg: COLORS.roseSoft, border: '#fecdd3', text: '#be123c' },
    blue: { bg: COLORS.skySoft, border: '#bae6fd', text: '#0369a1' },
  };
  const toneStyle = map[tone] || map.slate;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 12px',
        borderRadius: 999,
        border: `1px solid ${toneStyle.border}`,
        background: toneStyle.bg,
        color: toneStyle.text,
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      {children}
    </span>
  );
}

function ModernButton({ children, tone = 'primary', disabled, onClick, type = 'button' }) {
  const variant = tone === 'secondary' ? 'secondary' : tone === 'danger' ? 'danger' : tone === 'blue' ? 'outline' : 'default';
  return (
    <Button
      type={type}
      disabled={disabled}
      onClick={onClick}
      variant={variant}
      size="lg"
      className={tone === 'blue' ? 'border-sky-200 bg-sky-50 text-sky-700 hover:bg-sky-100' : undefined}
    >
      {children}
    </Button>
  );
}

function MetricCard({ icon, title, value, helper, tone = 'slate' }) {
  const Icon = icon;
  const tones = {
    slate: { bg: '#f8fafc', iconBg: '#ffffff', iconColor: '#475569' },
    amber: { bg: COLORS.amberSoft, iconBg: '#ffffff', iconColor: COLORS.amber },
    green: { bg: COLORS.emeraldSoft, iconBg: '#ffffff', iconColor: COLORS.emerald },
    indigo: { bg: COLORS.indigoSoft, iconBg: '#ffffff', iconColor: COLORS.indigo },
    red: { bg: COLORS.roseSoft, iconBg: '#ffffff', iconColor: COLORS.rose },
  };
  const palette = tones[tone] || tones.slate;
  return (
    <div
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 10,
        padding: 16,
        boxShadow: COLORS.shadowSoft,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: 8,
            background: palette.bg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: palette.iconColor,
            border: `1px solid ${COLORS.borderSoft}`,
          }}
        >
          <Icon size={20} strokeWidth={2.2} />
        </div>
      </div>
      <div style={{ marginTop: 14, fontSize: 11, fontWeight: 750, letterSpacing: '0.12em', textTransform: 'uppercase', color: COLORS.textSoft }}>
        {title}
      </div>
      <div style={{ marginTop: 6, fontSize: 28, lineHeight: 1, fontWeight: 750, color: COLORS.text }}>{value}</div>
      {helper ? <div style={{ marginTop: 10, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.5 }}>{helper}</div> : null}
    </div>
  );
}

function ToggleCard({ label, description, enabled, onToggle }) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onToggle}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onToggle();
        }
      }}
      style={{
        width: '100%',
        textAlign: 'left',
        borderRadius: 10,
        border: `1px solid ${enabled ? '#c7d2fe' : COLORS.border}`,
        background: enabled ? COLORS.indigoSoft : COLORS.cardBg,
        padding: 14,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 16,
        cursor: 'pointer',
        transition: 'all 150ms ease',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text }}>{label}</div>
        <div style={{ marginTop: 6, fontSize: 13, color: COLORS.textMuted, lineHeight: 1.5 }}>{description}</div>
      </div>
      <Switch checked={enabled} aria-label={`${label} visibility`} />
    </div>
  );
}

function Field({ label, helper, children }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.textMuted }}>{label}</span>
      {children}
      {helper ? <span style={{ fontSize: 12, color: COLORS.textSoft, lineHeight: 1.45 }}>{helper}</span> : null}
    </label>
  );
}

function Input(props) {
  return (
    <UIInput
      {...props}
      className="min-h-11 rounded-md"
      style={props.style}
    />
  );
}

function Select(props) {
  return (
    <select
      {...props}
      style={{
        width: '100%',
        minHeight: 46,
        padding: '0 14px',
        borderRadius: 8,
        border: `1px solid ${COLORS.border}`,
        background: '#fff',
        color: COLORS.text,
        fontSize: 14,
        outline: 'none',
        boxShadow: '0 1px 2px rgba(15,23,42,0.03)',
        ...props.style,
      }}
    />
  );
}

function MessageBox({ message }) {
  if (!message) return null;
  const success = message.type === 'success';
  return (
    <div
      style={{
        padding: '12px 14px',
        borderRadius: 18,
        border: `1px solid ${success ? '#a7f3d0' : '#fecdd3'}`,
        background: success ? COLORS.emeraldSoft : COLORS.roseSoft,
        color: success ? '#047857' : '#be123c',
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      {message.text}
    </div>
  );
}

function EmptyState({ icon, title, description }) {
  const Icon = icon;
  return (
    <div
      style={{
        borderRadius: 10,
        border: `1px dashed ${COLORS.border}`,
        background: COLORS.cardAlt,
        padding: '32px 24px',
        textAlign: 'center',
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 18,
          background: '#fff',
          border: `1px solid ${COLORS.borderSoft}`,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: COLORS.textSoft,
          marginBottom: 14,
        }}
      >
        <Icon size={22} />
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text }}>{title}</div>
      <div style={{ marginTop: 6, fontSize: 14, lineHeight: 1.6, color: COLORS.textMuted }}>{description}</div>
    </div>
  );
}

function UserAvatar({ label, admin }) {
  const initials = (label || '?')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
  return (
    <div
      style={{
        width: 44,
        height: 44,
        borderRadius: 16,
        background: admin ? COLORS.indigo : COLORS.sky,
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 800,
        fontSize: 14,
      }}
    >
      {initials}
    </div>
  );
}

const SETTINGS_SECTIONS = [
  { id: 'business', label: 'Business', description: 'Fees and navigation', icon: Percent },
  { id: 'security', label: 'Security', description: 'MFA, password, sessions', icon: ShieldCheck },
  { id: 'team', label: 'Team', description: 'Users and roles', icon: Users, adminOnly: true },
  { id: 'tiktok', label: 'TikTok Shop', description: 'Seller API and catalog tools', icon: ShoppingBag },
];

function SettingsSectionNav({ sections, active, onChange }) {
  return (
    <UITabs
      value={active}
      onValueChange={onChange}
      style={{
        background: COLORS.cardBg,
        border: `1px solid ${COLORS.borderSoft}`,
        borderRadius: 10,
        padding: 10,
        boxShadow: COLORS.shadowSoft,
        display: 'grid',
        gap: 6,
        alignSelf: 'start',
        position: 'sticky',
        top: 12,
        flex: '0 1 260px',
      }}
    >
      <UITabsList style={{ display: 'grid', gap: 6, borderBottom: 0 }}>
        {sections.map((section) => {
          const Icon = section.icon;
          const selected = section.id === active;
          return (
            <UITabsTrigger
              key={section.id}
              value={section.id}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                textAlign: 'left',
                border: `1px solid ${selected ? '#c7d2fe' : 'transparent'}`,
                background: selected ? COLORS.indigoSoft : 'transparent',
                color: selected ? COLORS.indigo : COLORS.text,
            borderRadius: 8,
                padding: 12,
                cursor: 'pointer',
                justifyContent: 'flex-start',
              }}
            >
              <span
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 12,
                  background: selected ? '#fff' : COLORS.cardAlt,
                  border: `1px solid ${COLORS.borderSoft}`,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flex: '0 0 auto',
                }}
              >
                <Icon size={17} />
              </span>
              <span style={{ minWidth: 0 }}>
                <span style={{ display: 'block', fontSize: 14, fontWeight: 800 }}>{section.label}</span>
                <span style={{ display: 'block', marginTop: 3, fontSize: 12, lineHeight: 1.35, color: selected ? '#4338ca' : COLORS.textMuted }}>
                  {section.description}
                </span>
              </span>
            </UITabsTrigger>
          );
        })}
      </UITabsList>
    </UITabs>
  );
}

export default function Settings() {
  const [data, setData] = useState(null);
  const [feePct, setFeePct] = useState('');
  const [fixedFee, setFixedFee] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [mfaStatus, setMfaStatus] = useState(null);
  const [mfaSetup, setMfaSetup] = useState(null);
  const [mfaCode, setMfaCode] = useState('');
  const [mfaDisableCode, setMfaDisableCode] = useState('');
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaMessage, setMfaMessage] = useState(null);
  const [sessionRows, setSessionRows] = useState([]);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionMessage, setSessionMessage] = useState(null);
  const [authMe, setAuthMe] = useState(null);
  const [authUsers, setAuthUsers] = useState([]);
  const [authUsersMessage, setAuthUsersMessage] = useState(null);
  const [authUsersBusy, setAuthUsersBusy] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current_password: '', new_password: '', confirm_password: '' });
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState(null);
  const [userForm, setUserForm] = useState({ email: '', display_name: '', role: 'staff', password: '', active: true });
  const [editingUser, setEditingUser] = useState(null);
  const [showUserForm, setShowUserForm] = useState(false);
  const [revokeBusy, setRevokeBusy] = useState(null);
  const [navVisibility, setNavVisibility] = useLocalState('wn-nav-visibility', DEFAULT_NAV_VISIBILITY);
  const [activeSection, setActiveSection] = useLocalState('company-settings-section', 'business');
  const [tiktokConnection, setTiktokConnection] = useState(null);
  const [tiktokBusy, setTiktokBusy] = useState(false);
  const [tiktokMessage, setTiktokMessage] = useState(null);
  const [tiktokAuthUrl, setTiktokAuthUrl] = useState('');
  const [addShopAuthUrl, setAddShopAuthUrl] = useState('');
  const [bulkUploadBusy, setBulkUploadBusy] = useState(false);
  const [bulkUploadResult, setBulkUploadResult] = useState(null);
  const [bulkUploadMessage, setBulkUploadMessage] = useState(null);
  const [tiktokForm, setTiktokForm] = useState({
    app_key: '',
    app_secret: '',
    service_id: '',
    auth_code: '',
    merchant_id: '',
    shop_id: '',
    shop_cipher: '',
    region: 'US',
  });
  const [addShopForm, setAddShopForm] = useState({
    app_key: '',
    app_secret: '',
    service_id: '',
    auth_code: '',
    merchant_id: '',
    shop_id: '',
    shop_cipher: '',
    region: 'US',
  });

  function load() {
    fetchApi('/api/fee_settings')
      .then((result) => {
        setData(result);
        setFeePct(String(result.fee_pct ?? ''));
        setFixedFee(String(result.fixed_fee ?? ''));
      })
      .catch(() => {});
    fetchApi('/api/auth/mfa/status')
      .then((result) => setMfaStatus(result))
      .catch(() => setMfaStatus(null));
    fetchApi('/api/auth/me')
      .then((result) => setAuthMe(result?.user || null))
      .catch(() => setAuthMe(null));
    fetchApi('/api/auth/sessions')
      .then((result) => setSessionRows(result.sessions || []))
      .catch(() => setSessionRows([]));
    fetchApi('/api/auth/users')
      .then((result) => setAuthUsers(result.users || []))
      .catch(() => setAuthUsers([]));
    fetchApi('/api/v2/integrations/tiktok-shop/status')
      .then((result) => {
        const connection = result.connection || {};
        setTiktokConnection(connection);
        setTiktokForm((current) => ({
          ...current,
          app_key: connection.app_key || current.app_key,
          service_id: connection.service_id || current.service_id,
          merchant_id: connection.merchant_id || current.merchant_id,
          shop_id: connection.shop_id || current.shop_id,
          shop_cipher: connection.shop_cipher || current.shop_cipher,
          region: connection.region || current.region || 'US',
        }));
      })
      .catch(() => setTiktokConnection(null));
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search || '');
    const authCode = String(params.get('code') || '').trim();
    if (!authCode) return;
    const appKey = String(params.get('app_key') || '').trim();
    const region = String(params.get('shop_region') || '').trim();
    const isAddShop = String(params.get('tiktok_add') || '').trim() === '1';
    setActiveSection('tiktok');
    if (isAddShop) {
      setAddShopForm((current) => ({
        ...current,
        app_key: appKey || current.app_key,
        auth_code: authCode,
        region: region || current.region || 'US',
      }));
      setTiktokMessage({ type: 'success', text: 'Second-shop authorization returned. Review the Add Another TikTok Shop fields, then click Save Additional Shop.' });
    } else {
      setTiktokForm((current) => ({
        ...current,
        app_key: appKey || current.app_key,
        auth_code: authCode,
        region: region || current.region || 'US',
      }));
      setTiktokMessage({ type: 'success', text: 'TikTok authorization returned. Review the fields, then click Connect TikTok Shop.' });
    }
    params.delete('code');
    params.delete('app_key');
    params.delete('locale');
    params.delete('shop_region');
    params.delete('tiktok_add');
    const nextQuery = params.toString();
    const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}${window.location.hash || ''}`;
    window.history.replaceState({}, '', nextUrl);
  }, [setActiveSection]);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      await postApi('/api/fee_settings/save', {
        platform_fee_pct: Number(feePct),
        fixed_fee: Number(fixedFee),
      });
      setMessage({ type: 'success', text: 'Fee settings saved.' });
      load();
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Failed to save settings.' });
    } finally {
      setSaving(false);
    }
  }

  async function startMfaSetup() {
    setMfaBusy(true);
    setMfaMessage(null);
    try {
      const result = await postApi('/api/auth/mfa/setup', {});
      setMfaSetup(result);
      setMfaMessage({ type: 'success', text: 'Scan the QR code, then enter the 6-digit code to enable MFA.' });
    } catch (error) {
      setMfaMessage({ type: 'error', text: error.message || 'Unable to start MFA setup.' });
    } finally {
      setMfaBusy(false);
    }
  }

  async function confirmMfaSetup() {
    setMfaBusy(true);
    setMfaMessage(null);
    try {
      const result = await postApi('/api/auth/mfa/confirm', { otp_code: mfaCode.trim() });
      setMfaStatus(result);
      setMfaSetup(null);
      setMfaCode('');
      setMfaMessage({ type: 'success', text: 'Multi-factor authentication is enabled.' });
      load();
    } catch (error) {
      setMfaMessage({ type: 'error', text: error.message || 'Verification failed.' });
    } finally {
      setMfaBusy(false);
    }
  }

  async function disableMfa() {
    setMfaBusy(true);
    setMfaMessage(null);
    try {
      const result = await postApi('/api/auth/mfa/disable', { otp_code: mfaDisableCode.trim() });
      setMfaStatus(result);
      setMfaSetup(null);
      setMfaDisableCode('');
      setMfaMessage({ type: 'success', text: 'Multi-factor authentication is disabled.' });
      load();
    } catch (error) {
      setMfaMessage({ type: 'error', text: error.message || 'Unable to disable MFA.' });
    } finally {
      setMfaBusy(false);
    }
  }

  async function revokeAllSessions() {
    setSessionBusy(true);
    setSessionMessage(null);
    try {
      const result = await postApi('/api/auth/sessions/revoke_all', {});
      setSessionMessage({ type: 'success', text: `Revoked ${result.revoked || 0} active session(s). Please sign in again on this device.` });
      setSessionRows([]);
    } catch (error) {
      setSessionMessage({ type: 'error', text: error.message || 'Unable to revoke sessions.' });
    } finally {
      setSessionBusy(false);
    }
  }

  async function handlePasswordChange() {
    setPasswordBusy(true);
    setPasswordMessage(null);
    if (!passwordForm.new_password || passwordForm.new_password !== passwordForm.confirm_password) {
      setPasswordBusy(false);
      setPasswordMessage({ type: 'error', text: 'New password and confirmation must match.' });
      return;
    }
    try {
      await postApi('/api/auth/password/change', passwordForm);
      setPasswordForm({ current_password: '', new_password: '', confirm_password: '' });
      setPasswordMessage({ type: 'success', text: 'Password changed. Sign in again with the new password.' });
    } catch (error) {
      setPasswordMessage({ type: 'error', text: error.message || 'Unable to change password.' });
    } finally {
      setPasswordBusy(false);
    }
  }

  async function handleUpsertUser() {
    setAuthUsersBusy(true);
    setAuthUsersMessage(null);
    try {
      await postApi('/api/auth/users/upsert', userForm);
      setAuthUsersMessage({ type: 'success', text: editingUser ? `User ${userForm.email} updated.` : `User ${userForm.email} created.` });
      setUserForm({ email: '', display_name: '', role: 'staff', password: '', active: true });
      setEditingUser(null);
      setShowUserForm(false);
      load();
    } catch (error) {
      setAuthUsersMessage({ type: 'error', text: error.message || 'Unable to save user.' });
    } finally {
      setAuthUsersBusy(false);
    }
  }

  function openEditUser(user) {
    setUserForm({ email: user.email, display_name: user.display_name || '', role: user.role || 'staff', password: '', active: user.active !== false });
    setEditingUser(user.email);
    setShowUserForm(true);
    setAuthUsersMessage(null);
  }

  function openAddUser() {
    setUserForm({ email: '', display_name: '', role: 'staff', password: '', active: true });
    setEditingUser(null);
    setShowUserForm(true);
    setAuthUsersMessage(null);
  }

  function cancelUserForm() {
    setShowUserForm(false);
    setEditingUser(null);
    setUserForm({ email: '', display_name: '', role: 'staff', password: '', active: true });
    setAuthUsersMessage(null);
  }

  async function handleRevokeUserSessions(email) {
    setRevokeBusy(email);
    setAuthUsersMessage(null);
    try {
      const result = await postApi('/api/auth/users/revoke_sessions', { email });
      setAuthUsersMessage({ type: 'success', text: `Revoked ${result.revoked || 0} session(s) for ${email}.` });
    } catch (error) {
      setAuthUsersMessage({ type: 'error', text: error.message || 'Unable to revoke sessions.' });
    } finally {
      setRevokeBusy(null);
    }
  }

  function toggleNavItem(key) {
    setNavVisibility((current) => ({ ...DEFAULT_NAV_VISIBILITY, ...current, [key]: !current?.[key] }));
  }

  function setTiktokField(key, value) {
    setTiktokForm((current) => ({ ...current, [key]: value }));
  }

  function setAddShopField(key, value) {
    setAddShopForm((current) => ({ ...current, [key]: value }));
  }

  async function generateTikTokAuthUrl() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    setTiktokAuthUrl('');
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/auth-url', {
        app_key: tiktokForm.app_key,
        service_id: tiktokForm.service_id,
      });
      if (!result.ok) throw new Error(result.error || 'Unable to create TikTok authorization URL.');
      setTiktokAuthUrl(result.auth_url || '');
      setTiktokMessage({ type: 'success', text: 'Authorization URL created. Open it, approve the shop, then paste the returned code here.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Unable to create TikTok authorization URL.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function generateAdditionalShopAuthUrl() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    setAddShopAuthUrl('');
    try {
      const redirectUri = `${window.location.origin}/company?tab=settings&tiktok_add=1`;
      const result = await postApi('/api/v2/integrations/tiktok-shop/auth-url', {
        app_key: addShopForm.app_key,
        service_id: addShopForm.service_id,
        redirect_uri: redirectUri,
      });
      if (!result.ok) throw new Error(result.error || 'Unable to create second-shop authorization URL.');
      setAddShopAuthUrl(result.auth_url || '');
      setTiktokMessage({ type: 'success', text: 'Second-shop authorization URL created. Open it, approve the shop, then return here.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Unable to create second-shop authorization URL.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function connectTikTokShop() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/connect', {
        ...tiktokForm,
        make_active: !tiktokConnected,
      });
      if (!result.ok) throw new Error(result.error || 'TikTok Shop connection failed.');
      setTiktokConnection(result.connection || {});
      setTiktokForm((current) => ({ ...current, app_secret: '', auth_code: '' }));
      setTiktokMessage({ type: 'success', text: tiktokConnected ? 'TikTok Shop saved. Your current active shop was not changed.' : 'TikTok Shop connected. Tokens are stored server-side and hidden from the browser.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'TikTok Shop connection failed.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function connectAdditionalTikTokShop() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/connect', {
        ...addShopForm,
        make_active: false,
      });
      if (!result.ok) throw new Error(result.error || 'Second TikTok Shop connection failed.');
      setTiktokConnection(result.connection || {});
      setAddShopForm((current) => ({ ...current, app_secret: '', auth_code: '', merchant_id: '', shop_id: '', shop_cipher: '' }));
      setAddShopAuthUrl('');
      setTiktokMessage({ type: 'success', text: 'Second TikTok Shop saved. Main shop remains active until you press Use on another shop.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Second TikTok Shop connection failed.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function refreshTikTokShop() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/refresh', {});
      if (!result.ok) throw new Error(result.error || 'Unable to refresh TikTok token.');
      setTiktokConnection(result.connection || {});
      setTiktokMessage({ type: 'success', text: 'TikTok Shop token refreshed.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Unable to refresh TikTok token.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function testTikTokShop() {
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/test', {});
      if (!result.ok) throw new Error(result.error || 'TikTok Shop test failed.');
      setTiktokConnection(result.connection || {});
      const shopCount = Array.isArray(result.shops) ? result.shops.length : 0;
      setTiktokMessage({ type: 'success', text: `TikTok Shop connection works. Found ${shopCount} authorized shop${shopCount === 1 ? '' : 's'}.` });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'TikTok Shop test failed.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function switchTikTokShop(shopKey) {
    if (!shopKey || shopKey === tiktokConnection?.active_shop_key) return;
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/switch', { shop_key: shopKey });
      if (!result.ok) throw new Error(result.error || 'Unable to switch TikTok shop.');
      setTiktokConnection(result.connection || {});
      setTiktokMessage({ type: 'success', text: 'Active TikTok shop switched. New API calls will use this shop.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Unable to switch TikTok shop.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function disconnectTikTokShop() {
    if (!window.confirm('Disconnect the active TikTok Shop? Other saved shops will stay connected.')) return;
    setTiktokBusy(true);
    setTiktokMessage(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/disconnect', {});
      if (!result.ok) throw new Error(result.error || 'Unable to disconnect TikTok Shop.');
      setTiktokConnection(result.connection || {});
      setTiktokMessage({ type: 'success', text: 'TikTok Shop disconnected.' });
    } catch (error) {
      setTiktokMessage({ type: 'error', text: error.message || 'Unable to disconnect TikTok Shop.' });
    } finally {
      setTiktokBusy(false);
    }
  }

  async function dryRunBulkUpload(forceStatuses = []) {
    setBulkUploadBusy(true);
    setBulkUploadMessage(null);
    setBulkUploadResult(null);
    try {
      const result = await postApi('/api/v2/integrations/tiktok-shop/products/push-missing-image-drafts', { dry_run: true, force_statuses: forceStatuses });
      setBulkUploadResult({ ...result, mode: 'dry_run', force_statuses: forceStatuses });
      const already = result.already_mapped_count ?? 0;
      const note = already > 0 ? ` ${already} already on TikTok (skipped).` : '';
      setBulkUploadMessage({ type: 'success', text: `Dry run complete. ${result.candidate_count ?? 0} product(s) ready to upload, ${result.skipped_count ?? 0} skipped.${note}` });
    } catch (error) {
      setBulkUploadMessage({ type: 'error', text: error.message || 'Dry run failed.' });
    } finally {
      setBulkUploadBusy(false);
    }
  }

  async function pollTaskStatus(taskKey, onResult, onError) {
    for (let i = 0; i < 180; i++) {
      await new Promise((r) => setTimeout(r, 4000));
      try {
        const state = await fetchApi(`/api/v2/integrations/tiktok-shop/task-status/${taskKey}`);
        if (state.status === 'completed') { onResult(state.result || state); return; }
        if (state.status === 'failed') { onError(state.error || 'Task failed.'); return; }
      } catch (_) {}
    }
    onError('Timed out waiting for task. Check back in a moment.');
  }

  async function runBulkUpload(forceStatuses = []) {
    const forceNote = forceStatuses.length ? `\n\nThis will RE-PUSH products currently in [${forceStatuses.join(', ')}] status, creating new TikTok listings alongside existing ones.` : '\n\nProducts already mapped to TikTok will be skipped.';
    if (!window.confirm(`Upload eligible inventory products to TikTok Shop as drafts?${forceNote}\n\nThis cannot be undone.`)) return;
    setBulkUploadBusy(true);
    setBulkUploadMessage({ type: 'success', text: 'Upload queued — running in background. This page will update automatically…' });
    setBulkUploadResult(null);
    try {
      await postApi('/api/v2/integrations/tiktok-shop/products/push-missing-image-drafts', { dry_run: false, force_statuses: forceStatuses });
      await pollTaskStatus(
        'bulk_push_tiktok_products',
        (result) => {
          setBulkUploadResult({ ...result, mode: 'upload', force_statuses: forceStatuses });
          const msg = result.ok
            ? `Upload complete. ${result.pushed_count ?? 0} product(s) pushed to TikTok Shop drafts.`
            : `Upload finished with errors. ${result.pushed_count ?? 0} pushed, ${result.error_count ?? 0} failed.`;
          setBulkUploadMessage({ type: result.ok ? 'success' : 'error', text: msg });
          setBulkUploadBusy(false);
        },
        (err) => {
          setBulkUploadMessage({ type: 'error', text: err });
          setBulkUploadBusy(false);
        }
      );
    } catch (error) {
      setBulkUploadMessage({ type: 'error', text: error.message || 'Bulk upload failed.' });
      setBulkUploadBusy(false);
    }
  }

  const [deleteUploadBusy, setDeleteUploadBusy] = useState(false);
  const [deleteUploadResult, setDeleteUploadResult] = useState(null);
  const [deleteUploadMessage, setDeleteUploadMessage] = useState(null);

  async function deleteTikTokProducts(statuses) {
    const label = statuses.length ? statuses.join(' + ') : 'ALL';
    if (!window.confirm(`Permanently delete all [${label}] products from TikTok Shop?\n\nThis removes them from TikTok and clears the local mapping. This CANNOT be undone.`)) return;
    setDeleteUploadBusy(true);
    setDeleteUploadMessage({ type: 'success', text: 'Delete queued — running in background. This page will update automatically…' });
    setDeleteUploadResult(null);
    try {
      await postApi('/api/v2/integrations/tiktok-shop/products/delete', { statuses });
      await pollTaskStatus(
        'bulk_delete_tiktok_products',
        (result) => {
          setDeleteUploadResult(result);
          const msg = result.ok
            ? `Deleted ${result.deleted_count ?? 0} product(s) from TikTok Shop.`
            : `Delete finished with errors. ${result.deleted_count ?? 0} deleted, ${result.error_count ?? 0} failed.`;
          setDeleteUploadMessage({ type: result.ok ? 'success' : 'error', text: msg });
          setDeleteUploadBusy(false);
        },
        (err) => {
          setDeleteUploadMessage({ type: 'error', text: err });
          setDeleteUploadBusy(false);
        }
      );
    } catch (error) {
      setDeleteUploadMessage({ type: 'error', text: error.message || 'Delete failed.' });
      setDeleteUploadBusy(false);
    }
  }

  const sessionCount = sessionRows.length;
  const mfaEnabled = !!mfaStatus?.mfa_enabled;
  const tiktokConnected = !!tiktokConnection?.connected;
  const enabledTabs = Object.values({ ...DEFAULT_NAV_VISIBILITY, ...navVisibility }).filter(Boolean).length;
  const visibleSections = SETTINGS_SECTIONS.filter((section) => !section.adminOnly || authMe?.role === 'admin');
  const currentSection = visibleSections.some((section) => section.id === activeSection) ? activeSection : 'business';
  const headerNavItems = [
    ['dashboard', 'Dashboard', 'Ops landing page'],
    ['users', 'Users', 'Staff accounts and roles'],
    ['history', 'History', 'Long-range archive and review'],
  ];

  return (
    <div style={{ background: '#f8fafc', margin: '-12px', padding: 18, minHeight: 'calc(100vh - 120px)' }}>
      <div style={{ maxWidth: 1480, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
        <section
          style={{
            background: COLORS.cardBg,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 10,
            padding: 20,
            boxShadow: COLORS.shadowSoft,
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.6fr) minmax(280px, 0.9fr)',
            gap: 18,
          }}
        >
          <div>
            <div
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                padding: '7px 12px',
                borderRadius: 999,
                background: COLORS.indigoSoft,
                color: COLORS.indigo,
                fontSize: 12,
                fontWeight: 700,
                marginBottom: 14,
              }}
            >
              <LayoutGrid size={14} />
              Settings
            </div>
            <div style={{ fontSize: 30, lineHeight: 1.1, fontWeight: 800, color: COLORS.text, maxWidth: 880 }}>
              Business and account controls
            </div>
            <div style={{ marginTop: 12, fontSize: 15, lineHeight: 1.75, color: COLORS.textMuted, maxWidth: 820 }}>
              Manage fee math, access security, team accounts, and TikTok Shop tools from clear sections instead of one long mixed page.
            </div>
          </div>

          <div
            style={{
              background: COLORS.cardBg,
              border: `1px solid ${COLORS.border}`,
              borderRadius: 10,
              padding: 12,
              boxShadow: COLORS.shadowSoft,
              display: 'grid',
              gap: 10,
              alignContent: 'start',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, borderRadius: 8, background: COLORS.cardAlt, padding: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: mfaEnabled ? COLORS.emerald : COLORS.amber }}>
                <ShieldCheck size={18} />
              </div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.textSoft }}>Security Posture</div>
                <div style={{ marginTop: 6 }}>
                  <StatusBadge tone={mfaEnabled ? 'green' : 'amber'}>{mfaEnabled ? 'Protected' : 'Action Needed'}</StatusBadge>
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, borderRadius: 8, background: COLORS.cardAlt, padding: 12 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.indigo }}>
                <LayoutGrid size={18} />
              </div>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.textSoft }}>Visible Top Tabs</div>
                <div style={{ marginTop: 4, fontSize: 16, fontWeight: 700, color: COLORS.text }}>{enabledTabs} enabled</div>
              </div>
            </div>
          </div>
        </section>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
          <MetricCard icon={Percent} title="Platform Fee" value={data ? `${Number(data.fee_pct).toFixed(1)}%` : '—'} helper="Used in profitability calculations" tone="amber" />
          <MetricCard icon={CreditCard} title="Fixed Fee" value={data ? `$${Number(data.fixed_fee).toFixed(2)}` : '—'} helper="Per transaction adjustment" tone="indigo" />
          <MetricCard icon={mfaEnabled ? ShieldCheck : ShieldX} title="MFA Status" value={mfaEnabled ? 'Enabled' : 'Disabled'} helper={mfaEnabled ? `${mfaStatus?.backup_codes_remaining || 0} backup codes left` : 'Authenticator setup recommended'} tone={mfaEnabled ? 'green' : 'red'} />
          <MetricCard icon={Laptop2} title="Active Sessions" value={String(sessionCount)} helper={sessionCount ? 'Devices signed into this account' : 'No active device sessions'} />
          <MetricCard icon={ShoppingBag} title="TikTok Shop" value={tiktokConnected ? 'Connected' : 'Not set'} helper={tiktokConnected ? 'Seller API tokens are stored server-side' : 'Connect seller account before API sync'} tone={tiktokConnected ? 'green' : 'amber'} />
        </div>

        <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <SettingsSectionNav sections={visibleSections} active={currentSection} onChange={setActiveSection} />
          <div style={{ display: 'grid', gap: 20, minWidth: 320, flex: '1 1 720px' }}>
        {currentSection === 'tiktok' ? (
          <>
        <SettingsCard
          eyebrow="Integration"
          title="TikTok Shop seller connection"
          description="Connect YNF Deals to TikTok Shop with seller API credentials. TikTok and affiliate CSV imports can keep working, but this enables direct Shop API sync once your app is approved."
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(320px, 0.8fr)', gap: 18 }}>
            <div style={{ display: 'grid', gap: 16 }}>
              <MessageBox message={tiktokMessage} />

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                <Field label="App Key">
                  <Input value={tiktokForm.app_key} onChange={(event) => setTiktokField('app_key', event.target.value)} placeholder="TikTok Shop app key" />
                </Field>
                <Field label="App Secret" helper={tiktokConnected ? 'Leave blank unless rotating credentials.' : 'Stored encrypted on the server.'}>
                  <Input type="password" value={tiktokForm.app_secret} onChange={(event) => setTiktokField('app_secret', event.target.value)} placeholder={tiktokConnected ? 'Already stored' : 'TikTok Shop app secret'} />
                </Field>
                <Field label="Service ID" helper="From your TikTok Shop Partner Center app. Used to open seller authorization.">
                  <Input value={tiktokForm.service_id} onChange={(event) => setTiktokField('service_id', event.target.value)} placeholder="TikTok Shop service ID" />
                </Field>
                <Field label="Region">
                  <Input value={tiktokForm.region} onChange={(event) => setTiktokField('region', event.target.value)} placeholder="US" />
                </Field>
              </div>

              <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16, display: 'grid', gap: 14 }}>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text }}>OAuth / seller approval</div>
                <div style={{ marginTop: 6, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.65 }}>
                    Generate the authorization link, approve access in TikTok Shop, then paste the returned authorization code. For Partner Center apps, use the Service ID from your in-house sales app.
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <ModernButton tone="secondary" onClick={generateTikTokAuthUrl} disabled={tiktokBusy || (!tiktokForm.app_key && !tiktokForm.service_id)}>
                    {tiktokBusy ? 'Preparing…' : 'Generate Auth URL'}
                  </ModernButton>
                  {tiktokAuthUrl ? (
                    <a href={tiktokAuthUrl} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 16px', borderRadius: 18, background: COLORS.indigoSoft, color: COLORS.indigo, fontSize: 14, fontWeight: 700, textDecoration: 'none' }}>
                      Open TikTok authorization
                    </a>
                  ) : null}
                </div>
                {tiktokAuthUrl ? (
                  <div style={{ borderRadius: 18, border: `1px solid ${COLORS.border}`, background: '#fff', padding: 12, fontSize: 12, color: COLORS.textMuted, wordBreak: 'break-all' }}>
                    {tiktokAuthUrl}
                  </div>
                ) : null}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                <Field label="Authorization Code">
                  <Input value={tiktokForm.auth_code} onChange={(event) => setTiktokField('auth_code', event.target.value)} placeholder="Paste code from TikTok redirect" />
                </Field>
                <Field label="Merchant ID">
                  <Input value={tiktokForm.merchant_id} onChange={(event) => setTiktokField('merchant_id', event.target.value)} placeholder="Optional merchant ID" />
                </Field>
                <Field label="Shop ID">
                  <Input value={tiktokForm.shop_id} onChange={(event) => setTiktokField('shop_id', event.target.value)} placeholder="Optional shop ID" />
                </Field>
                <Field label="Shop Cipher">
                  <Input value={tiktokForm.shop_cipher} onChange={(event) => setTiktokField('shop_cipher', event.target.value)} placeholder="Optional shop cipher" />
                </Field>
              </div>

              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <ModernButton onClick={connectTikTokShop} disabled={tiktokBusy || !tiktokForm.app_key || (!tiktokForm.auth_code && !tiktokForm.merchant_id)}>
                  {tiktokBusy ? 'Connecting…' : tiktokConnected ? 'Connect / Update Shop' : 'Connect TikTok Shop'}
                </ModernButton>
                <ModernButton tone="secondary" onClick={refreshTikTokShop} disabled={tiktokBusy || !tiktokConnected}>
                  Refresh Token
                </ModernButton>
                <ModernButton tone="blue" onClick={testTikTokShop} disabled={tiktokBusy || !tiktokConnected}>
                  Test Connection
                </ModernButton>
                <ModernButton tone="danger" onClick={disconnectTikTokShop} disabled={tiktokBusy || !tiktokConnected}>
                  Disconnect
                </ModernButton>
              </div>
            </div>

            <div style={{ background: tiktokConnected ? COLORS.emeraldSoft : COLORS.amberSoft, border: `1px solid ${tiktokConnected ? '#a7f3d0' : '#fde68a'}`, borderRadius: 10, padding: 18, alignSelf: 'start' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 44, height: 44, borderRadius: 16, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: tiktokConnected ? COLORS.emerald : COLORS.amber }}>
                  <ShoppingBag size={20} />
                </div>
                <StatusBadge tone={tiktokConnected ? 'green' : 'amber'}>{tiktokConnected ? 'Connected' : 'Not Connected'}</StatusBadge>
              </div>
              <div style={{ marginTop: 16, fontSize: 22, lineHeight: 1.1, fontWeight: 800, color: COLORS.text }}>
                TikTok Shop API
              </div>
              <div style={{ marginTop: 10, display: 'grid', gap: 8, fontSize: 13, color: COLORS.textMuted }}>
                <div><strong style={{ color: COLORS.text }}>App:</strong> {tiktokConnection?.app_key || 'Not configured'}</div>
                <div><strong style={{ color: COLORS.text }}>Service:</strong> {tiktokConnection?.service_id || '—'}</div>
                <div><strong style={{ color: COLORS.text }}>Seller:</strong> {tiktokConnection?.seller_name || '—'}</div>
                <div><strong style={{ color: COLORS.text }}>Merchant:</strong> {tiktokConnection?.merchant_id || '—'}</div>
                <div><strong style={{ color: COLORS.text }}>Shop:</strong> {tiktokConnection?.shop_id || tiktokConnection?.shop_cipher || '—'}</div>
                <div><strong style={{ color: COLORS.text }}>Saved shops:</strong> {Array.isArray(tiktokConnection?.shops) ? tiktokConnection.shops.length : 0}</div>
                <div><strong style={{ color: COLORS.text }}>Authorized shops:</strong> {Array.isArray(tiktokConnection?.authorized_shops) ? tiktokConnection.authorized_shops.length : 0}</div>
                <div><strong style={{ color: COLORS.text }}>Access token:</strong> {tiktokConnection?.access_token_valid ? 'Valid' : 'Needs refresh'}</div>
                <div><strong style={{ color: COLORS.text }}>Refresh token:</strong> {tiktokConnection?.refresh_token_valid ? 'Valid' : 'Missing / expired'}</div>
                {tiktokConnection?.last_refreshed_at ? <div><strong style={{ color: COLORS.text }}>Last refresh:</strong> {new Date(tiktokConnection.last_refreshed_at).toLocaleString()}</div> : null}
                {tiktokConnection?.last_error ? <div style={{ color: COLORS.rose }}><strong>Last error:</strong> {tiktokConnection.last_error}</div> : null}
              </div>
              {Array.isArray(tiktokConnection?.shops) && tiktokConnection.shops.length ? (
                <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.08em', textTransform: 'uppercase', color: COLORS.textMuted }}>Connected Shops</div>
                  {tiktokConnection.shops.map((shop) => (
                    <div key={shop.key || shop.shop_cipher || shop.shop_id} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'center', padding: 10, borderRadius: 12, background: '#fff', border: `1px solid ${shop.active ? '#a7f3d0' : COLORS.borderSoft}` }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 800, color: COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {shop.seller_name || shop.shop_id || shop.shop_cipher || 'TikTok Shop'}
                        </div>
                        <div style={{ marginTop: 2, fontSize: 11.5, color: COLORS.textMuted, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {shop.region || '—'} · {shop.shop_id || shop.shop_cipher || shop.key}
                        </div>
                      </div>
                      {shop.active ? (
                        <StatusBadge tone="green">Active</StatusBadge>
                      ) : (
                        <button
                          type="button"
                          onClick={() => switchTikTokShop(shop.key)}
                          disabled={tiktokBusy}
                          style={{ border: `1px solid ${COLORS.border}`, background: '#fff', color: COLORS.indigo, borderRadius: 10, padding: '7px 10px', fontSize: 12, fontWeight: 800, cursor: tiktokBusy ? 'not-allowed' : 'pointer' }}
                        >
                          Use
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </SettingsCard>

        <SettingsCard
          eyebrow="TikTok Shop · Second Account"
          title="Add another TikTok Shop safely"
          description="Use this separate connector for a second TikTok Shop app/account. Saving here will not switch away from the main ShopYNFDeals account unless you later press Use in Connected Shops."
        >
          <MessageBox message={tiktokMessage} />
          <div style={{ display: 'grid', gap: 16 }}>
            <div style={{ border: `1px solid ${COLORS.amberSoft}`, background: '#fffbeb', borderRadius: 14, padding: 14, color: COLORS.text, fontSize: 13, lineHeight: 1.55 }}>
              <strong>Second account redirect URL:</strong>
              <div style={{ marginTop: 6, padding: 10, borderRadius: 10, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, wordBreak: 'break-all', color: COLORS.textMuted }}>
                https://ynfdeals.com/company?tab=settings&amp;tiktok_add=1
              </div>
              <div style={{ marginTop: 8, color: COLORS.textMuted }}>
                Save and publish this exact URL in the second TikTok app before generating the authorization link.
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
              <Field label="Second App Key">
                <Input value={addShopForm.app_key} onChange={(event) => setAddShopField('app_key', event.target.value)} placeholder="Second TikTok app key" />
              </Field>
              <Field label="Second App Secret" helper="Required if this is a different TikTok app. Stored encrypted.">
                <Input type="password" value={addShopForm.app_secret} onChange={(event) => setAddShopField('app_secret', event.target.value)} placeholder="Second app secret" />
              </Field>
              <Field label="Second Service ID">
                <Input value={addShopForm.service_id} onChange={(event) => setAddShopField('service_id', event.target.value)} placeholder="Second service ID" />
              </Field>
              <Field label="Region">
                <Input value={addShopForm.region} onChange={(event) => setAddShopField('region', event.target.value)} placeholder="US" />
              </Field>
            </div>

            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <ModernButton tone="secondary" onClick={generateAdditionalShopAuthUrl} disabled={tiktokBusy || (!addShopForm.app_key && !addShopForm.service_id)}>
                {tiktokBusy ? 'Preparing…' : 'Generate Second-Shop Auth URL'}
              </ModernButton>
              {addShopAuthUrl ? (
                <a href={addShopAuthUrl} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', minHeight: 44, padding: '0 16px', borderRadius: 18, background: COLORS.indigoSoft, color: COLORS.indigo, fontSize: 14, fontWeight: 700, textDecoration: 'none' }}>
                  Open second-shop authorization
                </a>
              ) : null}
            </div>
            {addShopAuthUrl ? (
              <div style={{ borderRadius: 18, border: `1px solid ${COLORS.border}`, background: '#fff', padding: 12, fontSize: 12, color: COLORS.textMuted, wordBreak: 'break-all' }}>
                {addShopAuthUrl}
              </div>
            ) : null}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
              <Field label="Second Authorization Code">
                <Input value={addShopForm.auth_code} onChange={(event) => setAddShopField('auth_code', event.target.value)} placeholder="Code from second-shop redirect" />
              </Field>
              <Field label="Merchant ID">
                <Input value={addShopForm.merchant_id} onChange={(event) => setAddShopField('merchant_id', event.target.value)} placeholder="Optional merchant ID" />
              </Field>
              <Field label="Shop ID">
                <Input value={addShopForm.shop_id} onChange={(event) => setAddShopField('shop_id', event.target.value)} placeholder="Optional shop ID" />
              </Field>
              <Field label="Shop Cipher">
                <Input value={addShopForm.shop_cipher} onChange={(event) => setAddShopField('shop_cipher', event.target.value)} placeholder="Optional shop cipher" />
              </Field>
            </div>

            <div>
              <ModernButton onClick={connectAdditionalTikTokShop} disabled={tiktokBusy || !addShopForm.app_key || (!addShopForm.auth_code && !addShopForm.merchant_id)}>
                {tiktokBusy ? 'Saving…' : 'Save Additional Shop'}
              </ModernButton>
            </div>
          </div>
        </SettingsCard>

        <SettingsCard
          eyebrow="TikTok Shop · Catalog"
          title="Bulk upload inventory to TikTok Shop"
          description="Upload all eligible inventory products to TikTok Shop as drafts. Products already mapped are skipped. Each product's images, price, quantity, EAN, brand, dimensions, and category attributes are mapped automatically. Run a dry run first to preview which products are ready."
        >
          {bulkUploadMessage ? (
            <div style={{ marginBottom: 16, padding: '12px 16px', borderRadius: 14, background: bulkUploadMessage.type === 'error' ? COLORS.roseSoft : COLORS.emeraldSoft, border: `1px solid ${bulkUploadMessage.type === 'error' ? '#fecdd3' : '#a7f3d0'}`, color: bulkUploadMessage.type === 'error' ? COLORS.rose : COLORS.emerald, fontSize: 14, fontWeight: 600 }}>
              {bulkUploadMessage.text}
            </div>
          ) : null}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            <ModernButton tone="secondary" onClick={() => dryRunBulkUpload()} disabled={bulkUploadBusy || !tiktokConnected}>
              {bulkUploadBusy ? 'Working…' : 'Dry Run — Preview Upload'}
            </ModernButton>
            <ModernButton onClick={() => runBulkUpload()} disabled={bulkUploadBusy || !tiktokConnected}>
              <Upload size={16} />
              {bulkUploadBusy ? 'Uploading…' : 'Upload New Products to TikTok Drafts'}
            </ModernButton>
            {!tiktokConnected ? <span style={{ fontSize: 13, color: COLORS.amber, alignSelf: 'center', fontWeight: 600 }}>Connect TikTok Shop first</span> : null}
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: bulkUploadResult ? 20 : 0, paddingTop: 12, borderTop: `1px solid ${COLORS.borderSoft}` }}>
            <span style={{ fontSize: 13, color: COLORS.textMuted, alignSelf: 'center', fontWeight: 600 }}>Re-push by status:</span>
            <ModernButton tone="secondary" onClick={() => dryRunBulkUpload(['draft'])} disabled={bulkUploadBusy || !tiktokConnected}>
              Dry Run Drafts
            </ModernButton>
            <ModernButton tone="blue" onClick={() => runBulkUpload(['draft'])} disabled={bulkUploadBusy || !tiktokConnected}>
              <Upload size={16} />
              Re-push Drafts
            </ModernButton>
            <ModernButton tone="secondary" onClick={() => dryRunBulkUpload(['draft', 'auditing'])} disabled={bulkUploadBusy || !tiktokConnected}>
              Dry Run Drafts + Auditing
            </ModernButton>
            <ModernButton tone="blue" onClick={() => runBulkUpload(['draft', 'auditing'])} disabled={bulkUploadBusy || !tiktokConnected}>
              <Upload size={16} />
              Re-push Drafts + Auditing
            </ModernButton>
          </div>
          {bulkUploadResult ? (
            <div style={{ display: 'grid', gap: 16 }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
                <div style={{ background: COLORS.indigoSoft, border: '1px solid #c7d2fe', borderRadius: 18, padding: '14px 18px' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#4338ca', marginBottom: 6 }}>Candidates</div>
                  <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{bulkUploadResult.candidate_count ?? 0}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>products ready</div>
                </div>
                {(bulkUploadResult.already_mapped_count ?? 0) > 0 ? (
                  <div style={{ background: COLORS.skySoft, border: '1px solid #bae6fd', borderRadius: 18, padding: '14px 18px' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.sky, marginBottom: 6 }}>Already on TikTok</div>
                    <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{bulkUploadResult.already_mapped_count}</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>
                      {Object.entries(bulkUploadResult.already_mapped_by_status || {}).map(([s, n]) => `${n} ${s}`).join(' · ') || 'skipped (mapped)'}
                    </div>
                  </div>
                ) : null}
                {bulkUploadResult.mode === 'upload' ? (
                  <div style={{ background: COLORS.emeraldSoft, border: '1px solid #a7f3d0', borderRadius: 18, padding: '14px 18px' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.emerald, marginBottom: 6 }}>Pushed</div>
                    <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{bulkUploadResult.pushed_count ?? 0}</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>uploaded to TikTok</div>
                  </div>
                ) : null}
                {bulkUploadResult.error_count > 0 ? (
                  <div style={{ background: COLORS.roseSoft, border: '1px solid #fecdd3', borderRadius: 18, padding: '14px 18px' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.rose, marginBottom: 6 }}>Errors</div>
                    <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{bulkUploadResult.error_count}</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>failed uploads</div>
                  </div>
                ) : null}
                <div style={{ background: COLORS.amberSoft, border: '1px solid #fde68a', borderRadius: 18, padding: '14px 18px' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.amber, marginBottom: 6 }}>Skipped</div>
                  <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{bulkUploadResult.skipped_count ?? 0}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>missing image/EAN</div>
                </div>
              </div>
              {bulkUploadResult.mode === 'dry_run' && Array.isArray(bulkUploadResult.candidates) && bulkUploadResult.candidates.length > 0 ? (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, marginBottom: 10 }}>Products ready to upload ({bulkUploadResult.candidates.length})</div>
                  <div style={{ display: 'grid', gap: 6, maxHeight: 320, overflowY: 'auto' }}>
                    {bulkUploadResult.candidates.map((c) => (
                      <div key={c.product_id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '10px 14px', background: COLORS.cardAlt, borderRadius: 12, border: `1px solid ${COLORS.borderSoft}`, fontSize: 13 }}>
                        <span style={{ fontWeight: 700, color: COLORS.text, minWidth: 36 }}>#{c.product_id}</span>
                        <span style={{ flex: 1, color: COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                        <span style={{ color: COLORS.textMuted, whiteSpace: 'nowrap' }}>SKU: {c.sku || '—'}</span>
                        <span style={{ color: COLORS.textMuted, whiteSpace: 'nowrap' }}>EAN: {c.barcode || '—'}</span>
                        <StatusBadge tone="indigo">{c.image_count} img</StatusBadge>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {Array.isArray(bulkUploadResult.skipped) && bulkUploadResult.skipped.length > 0 ? (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.text, marginBottom: 10 }}>Skipped products (up to 100 shown)</div>
                  <div style={{ display: 'grid', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
                    {bulkUploadResult.skipped.map((s, i) => (
                      <div key={s.product_id ?? i} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 14px', background: COLORS.amberSoft, borderRadius: 12, border: '1px solid #fde68a', fontSize: 13 }}>
                        <span style={{ fontWeight: 700, color: COLORS.text, minWidth: 36 }}>#{s.product_id}</span>
                        <span style={{ flex: 1, color: COLORS.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                        <StatusBadge tone="amber">{s.reason === 'image_missing' ? 'No image' : s.reason === 'ean_missing' ? 'No EAN' : s.reason}</StatusBadge>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
              {bulkUploadResult.mode === 'upload' && Array.isArray(bulkUploadResult.errors) && bulkUploadResult.errors.length > 0 ? (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: COLORS.rose, marginBottom: 10 }}>Upload errors</div>
                  <div style={{ display: 'grid', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
                    {bulkUploadResult.errors.map((e, i) => (
                      <div key={e.product_id ?? i} style={{ padding: '10px 14px', background: COLORS.roseSoft, borderRadius: 12, border: '1px solid #fecdd3', fontSize: 13 }}>
                        <span style={{ fontWeight: 700, color: COLORS.text }}>#{e.product_id} {e.sku ? `(${e.sku})` : ''}</span>
                        <span style={{ marginLeft: 12, color: COLORS.rose }}>{typeof e.error === 'string' ? e.error : JSON.stringify(e.error)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </SettingsCard>

        <SettingsCard
          eyebrow="TikTok Shop · Danger Zone"
          title="Delete products from TikTok Shop"
          description="Permanently remove products from TikTok Shop and clear their local mappings. Use this only when cleaning up drafts, auditing products, or rebuilding listings from a verified upload plan."
        >
          {deleteUploadMessage ? (
            <div style={{ marginBottom: 16, padding: '12px 16px', borderRadius: 14, background: deleteUploadMessage.type === 'error' ? COLORS.roseSoft : COLORS.emeraldSoft, border: `1px solid ${deleteUploadMessage.type === 'error' ? '#fecdd3' : '#a7f3d0'}`, color: deleteUploadMessage.type === 'error' ? COLORS.rose : COLORS.emerald, fontSize: 14, fontWeight: 600 }}>
              {deleteUploadMessage.text}
            </div>
          ) : null}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: deleteUploadResult ? 20 : 0 }}>
            <ModernButton tone="danger" onClick={() => deleteTikTokProducts(['draft'])} disabled={deleteUploadBusy || !tiktokConnected}>
              Delete Drafts
            </ModernButton>
            <ModernButton tone="danger" onClick={() => deleteTikTokProducts(['auditing'])} disabled={deleteUploadBusy || !tiktokConnected}>
              Delete Auditing
            </ModernButton>
            <ModernButton tone="danger" onClick={() => deleteTikTokProducts(['draft', 'auditing'])} disabled={deleteUploadBusy || !tiktokConnected}>
              Delete Drafts + Auditing
            </ModernButton>
            <ModernButton tone="danger" onClick={() => deleteTikTokProducts([])} disabled={deleteUploadBusy || !tiktokConnected}>
              Delete All TikTok Products
            </ModernButton>
            {deleteUploadBusy ? <span style={{ fontSize: 13, color: COLORS.textMuted, alignSelf: 'center', fontWeight: 600 }}>Deleting… this may take a minute</span> : null}
          </div>
          {deleteUploadResult ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12 }}>
              <div style={{ background: COLORS.emeraldSoft, border: '1px solid #a7f3d0', borderRadius: 18, padding: '14px 18px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.emerald, marginBottom: 6 }}>Deleted</div>
                <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{deleteUploadResult.deleted_count ?? 0}</div>
                <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>removed from TikTok</div>
              </div>
              {(deleteUploadResult.error_count ?? 0) > 0 ? (
                <div style={{ background: COLORS.roseSoft, border: '1px solid #fecdd3', borderRadius: 18, padding: '14px 18px' }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.rose, marginBottom: 6 }}>Errors</div>
                  <div style={{ fontSize: 30, fontWeight: 800, color: COLORS.text }}>{deleteUploadResult.error_count}</div>
                  <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>failed to delete</div>
                </div>
              ) : null}
              {Array.isArray(deleteUploadResult.errors) && deleteUploadResult.errors.length > 0 ? (
                <div style={{ gridColumn: '1 / -1', display: 'grid', gap: 6 }}>
                  {deleteUploadResult.errors.map((e, i) => (
                    <div key={i} style={{ padding: '8px 14px', background: COLORS.roseSoft, borderRadius: 10, border: '1px solid #fecdd3', fontSize: 13, color: COLORS.rose }}>
                      TikTok ID {e.tiktok_product_id}: {typeof e.error === 'string' ? e.error : JSON.stringify(e.error)}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </SettingsCard>
          </>
        ) : null}

        {currentSection === 'business' ? (
          <>
        <SettingsCard
          eyebrow="Navigation"
          title="Header navigation controls"
          description="Hide low-use top tabs by default and surface them only when your team needs them. This keeps the operator and admin views cleaner."
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 14 }}>
            {headerNavItems.map(([key, label, description]) => (
              <ToggleCard key={key} label={label} description={description} enabled={!!navVisibility?.[key]} onToggle={() => toggleNavItem(key)} />
            ))}
          </div>
          </SettingsCard>
          </>
        ) : null}

        {(currentSection === 'business' || currentSection === 'security') ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 20 }}>
          {currentSection === 'business' ? (
          <SettingsCard
            eyebrow="Fees"
            title="Whatnot fee settings"
            description="These values power auction result math, margin reporting, sale-order profitability, and session analytics. Keep them tight and current."
            action={<ModernButton onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save settings'}</ModernButton>}
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 18 }}>
              <Field label="Platform Fee %" helper="Percentage fee applied to the final sale price before profit is calculated.">
                <Input type="number" step="0.1" value={feePct} onChange={(event) => setFeePct(event.target.value)} />
              </Field>
              <Field label="Fixed Fee" helper="Flat fee added to each completed transaction for Whatnot reporting.">
                <Input type="number" step="0.01" value={fixedFee} onChange={(event) => setFixedFee(event.target.value)} />
              </Field>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(240px, 0.85fr)', gap: 16, marginTop: 18 }}>
              <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: COLORS.textSoft }}>Fee Description</div>
                <div style={{ marginTop: 10, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.7 }}>
                  {data?.description || 'These fees are used to compute Whatnot sale profitability in the dashboard.'}
                </div>
              </div>
              <div style={{ background: COLORS.emeraldSoft, border: '1px solid #bbf7d0', borderRadius: 10, padding: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.18em', textTransform: 'uppercase', color: '#16a34a' }}>Profit Formula Preview</div>
                <div style={{ marginTop: 8, fontSize: 26, fontWeight: 800, color: COLORS.text }}>
                  {feePct || '—'}% + ${fixedFee || '—'}
                </div>
                <div style={{ marginTop: 8, fontSize: 13, color: COLORS.textMuted, lineHeight: 1.6 }}>Applied throughout auction results, sales orders, and session profitability cards.</div>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <MessageBox message={message} />
            </div>
          </SettingsCard>
          ) : null}

          {currentSection === 'security' ? (
          <SettingsCard
            eyebrow="Security"
            title="MFA and access protection"
            description="TOTP-based MFA for secure staff access, with backup code visibility and a cleaner setup flow."
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
              <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 14, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: mfaEnabled ? COLORS.emerald : COLORS.rose }}>
                    {mfaEnabled ? <ShieldCheck size={18} /> : <ShieldX size={18} />}
                  </div>
                  <StatusBadge tone={mfaEnabled ? 'green' : 'red'}>{mfaEnabled ? 'Enabled' : 'Disabled'}</StatusBadge>
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text }}>MFA Status</div>
                <div style={{ marginTop: 6, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.6 }}>
                  {mfaEnabled ? 'This account is currently protected by TOTP-based MFA.' : 'MFA is currently disabled for this account.'}
                </div>
              </div>

              <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 14, background: '#fff', border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.amber }}>
                    <KeyRound size={18} />
                  </div>
                  <StatusBadge tone="amber">{mfaStatus ? `${mfaStatus.backup_codes_remaining || 0} left` : '—'}</StatusBadge>
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text }}>Backup Codes</div>
                <div style={{ marginTop: 6, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.6 }}>
                  Recovery codes can be used once each if the authenticator device is unavailable.
                </div>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              <MessageBox message={mfaMessage} />
            </div>

            {!mfaEnabled ? (
              <div style={{ marginTop: 18, display: 'grid', gap: 18 }}>
                <div>
                  <ModernButton onClick={startMfaSetup} disabled={mfaBusy}>{mfaBusy ? 'Preparing…' : 'Enable TOTP'}</ModernButton>
                </div>
                {mfaSetup ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '260px minmax(0, 1fr)', gap: 18 }}>
                    <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                      <div style={{ background: '#fff', borderRadius: 8, padding: 12, boxShadow: COLORS.shadowSoft }}>
                        <img src={mfaSetup.qr_code_data_url} alt="Scan MFA QR" style={{ width: '100%', display: 'block', borderRadius: 12 }} />
                      </div>
                    </div>
                    <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                      <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text }}>Set up with your authenticator app</div>
                      <div style={{ marginTop: 6, fontSize: 14, lineHeight: 1.7, color: COLORS.textMuted }}>
                        Scan the QR code with Google Authenticator, 1Password, Authy, or another TOTP app, then enter the current 6-digit code below.
                      </div>
                      <div style={{ marginTop: 14, background: '#fff', border: `1px solid ${COLORS.border}`, borderRadius: 18, padding: 14 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.textSoft }}>Manual Secret</div>
                        <div style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 14, color: COLORS.text, wordBreak: 'break-all' }}>{mfaSetup.secret}</div>
                      </div>
                      <div style={{ marginTop: 14, maxWidth: 260 }}>
                        <Field label="Verification Code">
                          <Input type="text" inputMode="numeric" value={mfaCode} onChange={(event) => setMfaCode(event.target.value)} placeholder="Enter 6-digit code" />
                        </Field>
                      </div>
                      <div style={{ marginTop: 14 }}>
                        <ModernButton onClick={confirmMfaSetup} disabled={mfaBusy || !mfaCode.trim()}>
                          {mfaBusy ? 'Verifying…' : 'Confirm and enable MFA'}
                        </ModernButton>
                      </div>
                      <div style={{ marginTop: 16, background: COLORS.amberSoft, border: '1px solid #fde68a', borderRadius: 10, padding: 14 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, fontWeight: 700, color: COLORS.text }}>
                          <BadgeCheck size={16} color={COLORS.amber} />
                          Backup Codes
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 8, marginTop: 12 }}>
                          {(mfaSetup.backup_codes || []).map((code) => (
                            <div key={code} style={{ background: '#fff', border: '1px solid #fde68a', borderRadius: 14, padding: '10px 12px', fontFamily: 'monospace', fontSize: 12, color: COLORS.text }}>
                              {code}
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : (
              <div style={{ marginTop: 18, display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 280px', gap: 18 }}>
                <div style={{ background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, borderRadius: 10, padding: 16 }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: COLORS.text }}>Disable MFA with a live code</div>
                  <div style={{ marginTop: 6, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.7 }}>
                    Enter a current authenticator code or a backup code to disable MFA for this account.
                  </div>
                  <div style={{ marginTop: 16, maxWidth: 280 }}>
                    <Field label="Current Code">
                      <Input type="text" inputMode="numeric" value={mfaDisableCode} onChange={(event) => setMfaDisableCode(event.target.value)} placeholder="Authenticator or backup code" />
                    </Field>
                  </div>
                  <div style={{ marginTop: 14 }}>
                    <ModernButton tone="danger" onClick={disableMfa} disabled={mfaBusy || !mfaDisableCode.trim()}>
                      {mfaBusy ? 'Disabling…' : 'Disable MFA'}
                    </ModernButton>
                  </div>
                </div>
                <div style={{ background: COLORS.emeraldSoft, border: '1px solid #a7f3d0', borderRadius: 10, padding: 16 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.16em', textTransform: 'uppercase', color: COLORS.emerald }}>Security Note</div>
                  <div style={{ marginTop: 8, fontSize: 24, lineHeight: 1.1, fontWeight: 800, color: COLORS.text }}>This account is protected</div>
                  <div style={{ marginTop: 10, fontSize: 14, lineHeight: 1.7, color: COLORS.textMuted }}>
                    MFA is active. If you disable it, make sure the user still has a secure recovery path and a controlled device environment.
                  </div>
                </div>
              </div>
            )}
          </SettingsCard>
          ) : null}
        </div>
        ) : null}

        {currentSection === 'security' ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(320px, 0.85fr)', gap: 20 }}>
          <SettingsCard
            eyebrow="Sessions"
            title="Session and device management"
            description="Review active device sessions tied to this account and revoke them after a password or security change."
            action={<ModernButton tone="secondary" onClick={revokeAllSessions} disabled={sessionBusy}>{sessionBusy ? 'Revoking…' : 'Log out all devices'}</ModernButton>}
          >
            <div style={{ marginBottom: 16 }}>
              <MessageBox message={sessionMessage} />
            </div>

            {!sessionRows.length ? (
              <EmptyState icon={Laptop2} title="No active sessions found" description="Signed-in browsers and devices will appear here once they authenticate against the dashboard." />
            ) : (
              <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: 'hidden', background: COLORS.cardBg }}>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1.15fr 1fr 0.85fr 0.65fr',
                    gap: 12,
                    padding: '14px 18px',
                    background: COLORS.cardAlt,
                    borderBottom: `1px solid ${COLORS.border}`,
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                    color: COLORS.textSoft,
                  }}
                >
                  <div>Device</div>
                  <div>IP / Browser</div>
                  <div>Activity</div>
                  <div>Status</div>
                </div>
                {sessionRows.map((row) => (
                  <div
                    key={row.id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1.15fr 1fr 0.85fr 0.65fr',
                      gap: 12,
                      padding: '16px 18px',
                      borderBottom: `1px solid ${COLORS.borderSoft}`,
                      alignItems: 'center',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 14, background: COLORS.cardAlt, border: `1px solid ${COLORS.borderSoft}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: COLORS.textMuted }}>
                        <Laptop2 size={18} />
                      </div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text }}>{row.current ? 'Current device' : 'Active browser session'}</div>
                        <div style={{ marginTop: 4, fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>{row.user_agent || 'User agent unavailable'}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: 13, color: COLORS.textMuted }}>{row.client_ip || 'Unknown IP'}</div>
                    <div style={{ fontSize: 13, color: COLORS.textMuted }}>{row.last_seen_at ? new Date(row.last_seen_at).toLocaleString() : 'Currently active'}</div>
                    <div><StatusBadge tone={row.current ? 'green' : 'slate'}>{row.current ? 'Current' : 'Active'}</StatusBadge></div>
                  </div>
                ))}
              </div>
            )}
          </SettingsCard>

          <SettingsCard eyebrow="Password" title="Password rotation" description="Rotate your own password without digging through a legacy form. This revokes existing sessions and forces a fresh login.">
            <div style={{ display: 'grid', gap: 14 }}>
              <MessageBox message={passwordMessage} />
              <Field label="Current Password">
                <Input type="password" value={passwordForm.current_password} onChange={(event) => setPasswordForm((prev) => ({ ...prev, current_password: event.target.value }))} />
              </Field>
              <Field label="New Password">
                <Input type="password" value={passwordForm.new_password} onChange={(event) => setPasswordForm((prev) => ({ ...prev, new_password: event.target.value }))} />
              </Field>
              <Field label="Confirm New Password">
                <Input type="password" value={passwordForm.confirm_password} onChange={(event) => setPasswordForm((prev) => ({ ...prev, confirm_password: event.target.value }))} />
              </Field>
              <div style={{ paddingTop: 6 }}>
                <ModernButton onClick={handlePasswordChange} disabled={passwordBusy}>{passwordBusy ? 'Updating…' : 'Change Password'}</ModernButton>
              </div>
            </div>
          </SettingsCard>
        </div>
        ) : null}

        {currentSection === 'team' && authMe?.role === 'admin' ? (
          <SettingsCard
            eyebrow="Administration"
            title="Team account management"
            description="Create staff accounts, update roles, review MFA usage, and revoke sessions from a cleaner admin workspace."
            action={!showUserForm ? <ModernButton onClick={openAddUser}><Users size={16} />Add User</ModernButton> : null}
          >
            <div style={{ marginBottom: 16 }}>
              <MessageBox message={authUsersMessage} />
            </div>

            {showUserForm ? (
              <div style={{ marginBottom: 20, borderRadius: 10, border: '1px solid #c7d2fe', background: COLORS.indigoSoft, padding: 18 }}>
                <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text }}>{editingUser ? `Editing ${editingUser}` : 'Create a new dashboard user'}</div>
                <div style={{ marginTop: 6, fontSize: 14, color: COLORS.textMuted }}>Set identity, role, password, and whether the account can sign in.</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginTop: 18 }}>
                  <Field label="Email">
                    <Input
                      type="email"
                      value={userForm.email}
                      onChange={(event) => setUserForm((prev) => ({ ...prev, email: event.target.value }))}
                      disabled={!!editingUser}
                      placeholder="user@example.com"
                      style={editingUser ? { background: '#eef2f7', color: COLORS.textMuted } : undefined}
                    />
                  </Field>
                  <Field label="Display Name">
                    <Input value={userForm.display_name} onChange={(event) => setUserForm((prev) => ({ ...prev, display_name: event.target.value }))} placeholder="Full Name" />
                  </Field>
                  <Field label="Role">
                    <Select value={userForm.role} onChange={(event) => setUserForm((prev) => ({ ...prev, role: event.target.value }))}>
                      <option value="staff">Staff</option>
                      <option value="admin">Admin</option>
                    </Select>
                  </Field>
                  <Field label={editingUser ? 'Password (leave blank to keep)' : 'Password'}>
                    <Input type="password" value={userForm.password} onChange={(event) => setUserForm((prev) => ({ ...prev, password: event.target.value }))} placeholder={editingUser ? 'Leave blank to keep current' : 'Set initial password'} />
                  </Field>
                </div>

                <label
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '12px 14px',
                    borderRadius: 18,
                    background: '#fff',
                    border: `1px solid ${COLORS.border}`,
                    marginTop: 16,
                    fontSize: 14,
                    color: COLORS.textMuted,
                  }}
                >
                  <input type="checkbox" checked={userForm.active} onChange={(event) => setUserForm((prev) => ({ ...prev, active: event.target.checked }))} />
                  Active account (can log in)
                </label>

                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 18 }}>
                  <ModernButton onClick={handleUpsertUser} disabled={authUsersBusy}>{authUsersBusy ? 'Saving…' : editingUser ? 'Update User' : 'Create User'}</ModernButton>
                  <ModernButton tone="secondary" onClick={cancelUserForm}>Cancel</ModernButton>
                </div>
              </div>
            ) : null}

            {!authUsers.length ? (
              <EmptyState icon={UserCog} title="No internal users yet" description="Create your first staff account to start using role-based access and session management." />
            ) : (
              <div style={{ display: 'grid', gap: 14 }}>
                {authUsers.map((user) => {
                  const isAdmin = user.role === 'admin';
                  const isMe = user.email === authMe?.email;
                  return (
                    <div
                      key={user.email}
                      style={{
                        background: user.active === false ? COLORS.roseSoft : COLORS.cardBg,
                        border: `1px solid ${user.active === false ? '#fecdd3' : COLORS.border}`,
                        borderRadius: 10,
                        padding: 18,
                        boxShadow: COLORS.shadowSoft,
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                        <div style={{ display: 'flex', gap: 14, minWidth: 0 }}>
                          <UserAvatar label={user.display_name || user.email} admin={isAdmin} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                              <div style={{ fontSize: 17, fontWeight: 700, color: COLORS.text }}>{user.display_name || user.email}</div>
                              <StatusBadge tone={isAdmin ? 'indigo' : 'blue'}>{user.role || 'staff'}</StatusBadge>
                              <StatusBadge tone={user.active === false ? 'red' : 'green'}>{user.active === false ? 'Disabled' : 'Active'}</StatusBadge>
                              {user.mfa_enabled ? <StatusBadge tone="green">MFA On</StatusBadge> : <StatusBadge tone="amber">MFA Off</StatusBadge>}
                              {isMe ? <StatusBadge>You</StatusBadge> : null}
                            </div>
                            <div style={{ marginTop: 6, fontSize: 13, color: COLORS.textMuted }}>
                              {user.email}
                              {user.last_login_at ? ` · Last login ${new Date(user.last_login_at).toLocaleString()}` : ' · No recent login'}
                            </div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                          <ModernButton tone="secondary" onClick={() => openEditUser(user)}>Edit</ModernButton>
                          {!isMe ? (
                            <ModernButton tone="danger" onClick={() => handleRevokeUserSessions(user.email)} disabled={revokeBusy === user.email}>
                              {revokeBusy === user.email ? 'Revoking…' : 'Kick Sessions'}
                            </ModernButton>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </SettingsCard>
        ) : null}

          </div>
        </div>
      </div>
    </div>
  );
}
