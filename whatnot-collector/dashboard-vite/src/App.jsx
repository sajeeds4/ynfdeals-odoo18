import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { Routes, Route, Link, useLocation, Navigate, useNavigate } from 'react-router-dom';
import { clearApiCache, fetchApi, postApi, storeCsrfToken, usePolling } from './hooks/useApi';
import { AUTH_USER_CACHE_KEY, clearBrowserState, useLocalState } from './hooks/useBrowserState';
import './App.css';
import LargeScreen from './views/LargeScreen';
import Operator from './views/Operator';
import TvScanner from './views/TvScanner';
import WinnerScanner from './views/WinnerScanner';
import Session from './views/Session';
import History from './views/History';
import Orders from './views/Orders';
import Inventory from './views/Inventory';
import Company from './views/Company';
import OperatorObs from './views/OperatorObs';
import Login from './views/Login';
import InternalPos from './views/InternalPos';
import ynfLogo from './assets/ynf-logo.svg';

async function verifyCurrentSession() {
  try {
    const res = await fetch('/api/auth/me', {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { Accept: 'application/json' },
    });
    const data = await res.json().catch(() => ({}));
    return {
      authenticated: !!data?.authenticated,
      user: data?.user || null,
      csrfToken: data?.csrf_token || '',
      networkError: false,
    };
  } catch {
    return { authenticated: null, user: null, csrfToken: '', networkError: true };
  }
}

const DEFAULT_NAV_VISIBILITY = {
  dashboard: false,
  users: false,
  history: false,
};

const LAST_APP_ROUTE_KEY = 'ynf_last_app_route';
const DEFAULT_APP_ROUTE = '/company?tab=overview';

function readLastAppRoute() {
  if (typeof window === 'undefined') return DEFAULT_APP_ROUTE;
  try {
    const saved = window.localStorage.getItem(LAST_APP_ROUTE_KEY) || '';
    if (
      saved
      && saved.startsWith('/')
      && !saved.startsWith('/login')
      && !saved.startsWith('/internal-pos')
      && !saved.startsWith('/self-checkout')
    ) {
      return saved;
    }
  } catch {
    // ignore storage failures
  }
  return DEFAULT_APP_ROUTE;
}

function LastRouteRedirect() {
  return <Navigate to={readLastAppRoute()} replace />;
}

export default function App() {
  const loc = useLocation();
  const navigate = useNavigate();
  const onCompanyRoute = loc.pathname.startsWith('/company');
  const [authReady, setAuthReady] = useState(false);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [authUser, setAuthUser] = useState(null);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef(null);
  const [navVisibility] = useLocalState('wn-nav-visibility', DEFAULT_NAV_VISIBILITY);
  const authCheckInFlightRef = useRef(false);
  const lastAuthRedirectRef = useRef('');
  const canUseApp = authReady && (!authEnabled || authenticated);
  const { data: connectionData, error: connectionError, loading } = usePolling(['/latest_id', '/api/stream_status'], 10000, canUseApp, { pauseWhenHidden: true });
  const [connectionFailureCount, setConnectionFailureCount] = useState(0);
  const { data: alertsData } = usePolling('/api/alerts', 30000, onCompanyRoute && canUseApp);
  const alertCount = (alertsData?.alerts || []).filter((a) => a.level === 'error' || a.level === 'warning').length;

  useEffect(() => {
    if (!canUseApp) {
      setConnectionFailureCount(0);
      return;
    }
    if (connectionError) {
      setConnectionFailureCount((count) => Math.min(count + 1, 10));
      return;
    }
    if (connectionData) {
      setConnectionFailureCount(0);
    }
  }, [canUseApp, connectionData, connectionError]);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', 'light');
    clearBrowserState('local', 'wn-theme');
  }, []);

  useEffect(() => {
    if (!accountMenuOpen) return undefined;
    function handlePointerDown(event) {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target)) {
        setAccountMenuOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') setAccountMenuOpen(false);
    }
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [accountMenuOpen]);

  useEffect(() => {
    setAccountMenuOpen(false);
  }, [loc.pathname, loc.search]);

  useEffect(() => {
    if (
      loc.pathname === '/login'
      || loc.pathname === '/'
      || loc.pathname === '/dashboard'
      || loc.pathname === '/internal-pos'
      || loc.pathname === '/self-checkout'
    ) {
      return;
    }
    try {
      window.localStorage.setItem(LAST_APP_ROUTE_KEY, `${loc.pathname}${loc.search || ''}`);
    } catch {
      // ignore storage failures
    }
  }, [loc.pathname, loc.search]);

  useEffect(() => {
    let cancelled = false;
    async function bootstrapAuth() {
      try {
        const cfg = await fetchApi('/api/auth/config');
        if (cancelled) return;
        const enabled = !!cfg?.auth_enabled;
        setAuthEnabled(enabled);
        if (!enabled) {
          setAuthenticated(false);
          setAuthUser(null);
          setAuthReady(true);
          return;
        }
        const me = await fetchApi('/api/auth/me');
        if (cancelled) return;
        setAuthenticated(!!me?.authenticated);
        setAuthUser(me?.user || null);
        storeCsrfToken(me?.csrf_token || '');
      } catch {
        if (cancelled) return;
        // Preserve the current session on transient bootstrap failures.
      } finally {
        if (!cancelled) setAuthReady(true);
      }
    }
    bootstrapAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function handleAuthRequired() {
      if (authCheckInFlightRef.current) return;
      authCheckInFlightRef.current = true;
      try {
        const session = await verifyCurrentSession();
        if (cancelled) return;
        if (session.networkError) {
          return;
        }
        if (session.authenticated) {
          setAuthenticated(true);
          setAuthUser(session.user);
          storeCsrfToken(session.csrfToken);
          lastAuthRedirectRef.current = '';
          return;
        }
        storeCsrfToken('');
        clearApiCache();
        setAuthenticated(false);
        setAuthUser(null);
        const returnTo = `${loc.pathname}${loc.search || ''}`;
        if (loc.pathname !== '/login' && loc.pathname !== '/internal-pos' && loc.pathname !== '/self-checkout' && lastAuthRedirectRef.current !== returnTo) {
          lastAuthRedirectRef.current = returnTo;
          navigate('/login', {
            replace: true,
            state: { from: returnTo },
          });
        }
      } finally {
        authCheckInFlightRef.current = false;
      }
    }
    window.addEventListener('wn-auth-required', handleAuthRequired);
    return () => {
      cancelled = true;
      window.removeEventListener('wn-auth-required', handleAuthRequired);
    };
  }, [loc.pathname, loc.search, navigate]);

  async function handleLogout() {
    const confirmMessage = loc.pathname.startsWith('/operator')
      ? 'Logout from the operator screen? This will end your dashboard session on this browser.'
      : 'Logout from the dashboard?';
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm(confirmMessage);
      if (!confirmed) {
        setAccountMenuOpen(false);
        return;
      }
    }
    try {
      await postApi('/api/auth/logout', {});
    } catch {
      // ignore logout cleanup errors
    }
    storeCsrfToken('');
    clearApiCache();
    setAuthenticated(false);
    setAuthUser(null);
    try {
      window.localStorage.removeItem(AUTH_USER_CACHE_KEY);
    } catch {
      // ignore storage failures
    }
  }

  function handleAuthenticated(data) {
    setAuthenticated(true);
    setAuthUser(data?.user || null);
  }
  useLayoutEffect(() => {
    try {
      const normalizedAuthEmail = String(authUser?.email || '').trim().toLowerCase();
      if (!authEnabled || !authenticated || !normalizedAuthEmail) {
        window.localStorage.removeItem(AUTH_USER_CACHE_KEY);
        return;
      }
      const nextValue = JSON.stringify({
        email: normalizedAuthEmail,
        role: String(authUser?.role || '').trim().toLowerCase(),
      });
      if (window.localStorage.getItem(AUTH_USER_CACHE_KEY) !== nextValue) {
        window.localStorage.setItem(AUTH_USER_CACHE_KEY, nextValue);
      }
    } catch {
      // ignore storage failures
    }
  }, [authEnabled, authenticated, authUser?.email, authUser?.role]);

  if (!authReady) {
    return <div className="login-shell"><div className="login-panel"><p className="login-copy">Loading secure dashboard...</p></div></div>;
  }

  const protectedElement = (element, access = 'staff') => {
    if (authEnabled && !authenticated) {
      return <Navigate to="/login" replace state={{ from: `${loc.pathname}${loc.search || ''}` }} />;
    }
    return element;
  };
  const hideChrome = (authEnabled && !authenticated && loc.pathname === '/login') || loc.pathname === '/internal-pos' || loc.pathname === '/self-checkout';
  return (
    <div className="app">
      {(!loading && connectionError && connectionFailureCount >= 3) && (
        <div style={{ background: 'var(--accent-coral)', color: '#1a0303', padding: '8px 16px', textAlign: 'center', fontWeight: 'bold', fontSize: 13, zIndex: 1000}}>
          ⚠️ Reconnecting: API did not answer after multiple checks. If this stays visible, ensure `python3 -m server` is running.
        </div>
      )}
      {!hideChrome && <header className="header">
        <div className="brand">
          <img className="logo" src={ynfLogo} alt="YNF Deals" />
          <div className="brand__copy">
            <h1>YNF Deals Ops</h1>
            <span className="brand__meta">Live operations</span>
          </div>
        </div>
        <nav className="nav">
          <div className="nav__links">
            <Link to="/company?tab=overview" className={`nav-link ${loc.pathname.startsWith('/company') ? 'active' : ''}`}>Overview</Link>
            <Link to="/operator" className={`nav-link ${loc.pathname.startsWith('/operator') ? 'active' : ''}`}>Operator</Link>
            {navVisibility.history && <Link to="/history" className={`nav-link ${loc.pathname === '/history' ? 'active' : ''}`}>History</Link>}
          </div>
          <div className="nav__actions">
            {authEnabled && authenticated ? (
              <div className="account-menu-wrap" ref={accountMenuRef}>
                <button
                  type="button"
                  className={`auth-pill auth-pill--button ${accountMenuOpen ? 'is-open' : ''}`}
                  title={authUser?.email || authUser?.display_name || 'Signed in user'}
                  aria-haspopup="menu"
                  aria-expanded={accountMenuOpen}
                  onClick={() => setAccountMenuOpen((value) => !value)}
                >
                  <span className="auth-pill__avatar" aria-hidden="true">👤</span>
                  <span className="auth-pill__copy">
                    <span className="auth-pill__name">{authUser?.display_name || authUser?.email || 'Staff'}</span>
                    <span className="auth-pill__role">{authUser?.role || 'staff'}</span>
                  </span>
                  <span className="auth-pill__chevron" aria-hidden="true">⌄</span>
                </button>
                {accountMenuOpen ? (
                  <div className="account-menu" role="menu">
                    <div className="account-menu__header">
                      <strong>{authUser?.display_name || authUser?.email || 'Staff'}</strong>
                      <span>{authUser?.email || authUser?.role || 'Signed in'}</span>
                    </div>
                    <Link className="account-menu__item" role="menuitem" to="/company?tab=staff-users">
                      <span>Team & Access</span>
                      <small>Users and permissions</small>
                    </Link>
                    <Link className="account-menu__item" role="menuitem" to="/company?tab=settings">
                      <span>Settings</span>
                      <small>Fees, security, controls</small>
                    </Link>
                    <Link className="account-menu__item" role="menuitem" to="/company?tab=diagnostics">
                      <span>System</span>
                      <small>Diagnostics and health</small>
                    </Link>
                    <button type="button" className="account-menu__item account-menu__item--danger" role="menuitem" onClick={handleLogout}>
                      <span>Logout</span>
                      <small>End this session</small>
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </nav>
      </header>}

      <main className="content" style={
        !hideChrome && loc.pathname.startsWith('/company')
          ? { padding: 0, overflowY: 'visible', overflowX: 'hidden', display: 'flex', flexDirection: 'column', minWidth: 0 }
          : loc.pathname.startsWith('/operator')
          ? { padding: '10px 14px 16px' }
          : {}
      }>
        <Routes>
          <Route path="/login" element={<Login authReady={authReady} authEnabled={authEnabled} authenticated={authenticated} onAuthenticated={handleAuthenticated} />} />
          <Route path="/" element={<LastRouteRedirect />} />
          <Route path="/tv-display" element={protectedElement(<LargeScreen />)} />
          <Route path="/operator" element={protectedElement(<Operator />)} />
          <Route path="/operator/tv-scanner" element={protectedElement(<TvScanner />)} />
          <Route path="/operator/winner-scanner" element={protectedElement(<WinnerScanner />)} />
          <Route path="/operator/obs" element={protectedElement(<OperatorObs />)} />
          <Route path="/session" element={protectedElement(<Session />)} />
          <Route path="/history" element={protectedElement(<History />)} />
          <Route path="/orders" element={protectedElement(<Orders />)} />
          <Route path="/inventory" element={protectedElement(<Inventory />)} />
          <Route path="/dashboard" element={<LastRouteRedirect />} />
          <Route path="/company" element={protectedElement(<Company />)} />
          <Route path="/users" element={<Navigate to="/company?tab=staff-users" replace />} />
        <Route path="/internal-pos" element={<InternalPos />} />
        <Route path="/self-checkout" element={<InternalPos />} />
        </Routes>
      </main>
    </div>
  );
}
