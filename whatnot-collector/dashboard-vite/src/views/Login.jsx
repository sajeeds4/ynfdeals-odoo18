import { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { fetchApi, postApi } from '../hooks/useApi';
import ynfLogo from '../assets/ynf-logo.svg';

const STEP_EMAIL = 'email';
const STEP_PASSWORD = 'password';
const STEP_MFA = 'mfa';

export default function Login({ authReady, authEnabled, authenticated, onAuthenticated }) {
  const navigate = useNavigate();
  const location = useLocation();
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const otpRef = useRef(null);

  const [step, setStep] = useState(STEP_EMAIL);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [loginChallenge, setLoginChallenge] = useState('');
  const [honeypot, setHoneypot] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [retryAfter, setRetryAfter] = useState(0);
  const [accountLabel, setAccountLabel] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const cfg = await fetchApi('/api/auth/config');
        if (!cancelled) setLoginChallenge(cfg?.login_challenge || '');
      } catch {
        if (!cancelled) setLoginChallenge('');
      }
    }
    if (authEnabled) load();
    return () => {
      cancelled = true;
    };
  }, [authEnabled]);

  useEffect(() => {
    if (!retryAfter) return;
    const timer = setInterval(() => setRetryAfter((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [retryAfter]);

  useEffect(() => {
    if (step === STEP_EMAIL) emailRef.current?.focus();
    if (step === STEP_PASSWORD) passwordRef.current?.focus();
    if (step === STEP_MFA) otpRef.current?.focus();
  }, [step]);

  const normalizedEmail = useMemo(() => email.trim().toLowerCase(), [email]);
  const returnTo = useMemo(() => {
    const from = typeof location.state?.from === 'string' ? location.state.from : '/company?tab=overview';
    return from && from !== '/login' && from !== '/' ? from : '/company?tab=overview';
  }, [location.state?.from]);

  if (authReady && (!authEnabled || authenticated)) {
    return <Navigate to={returnTo} replace />;
  }

  async function loadFreshChallenge() {
    try {
      const cfg = await fetchApi('/api/auth/config');
      setLoginChallenge(cfg?.login_challenge || '');
    } catch {
      setLoginChallenge('');
    }
  }

  async function handleEmailStep(event) {
    event.preventDefault();
    if (!normalizedEmail) return;
    setError('');
    setAccountLabel(normalizedEmail);
    setStep(STEP_PASSWORD);
  }

  async function handlePasswordStep(event) {
    event.preventDefault();
    if (!normalizedEmail || !password) return;
    setSubmitting(true);
    setError('');
    try {
      const data = await postApi('/api/auth/login', {
        email: normalizedEmail,
        password,
        otp_code: '',
        login_challenge: loginChallenge,
        website: honeypot,
      });
      onAuthenticated?.(data);
      navigate(returnTo, { replace: true });
    } catch (err) {
      const body = err?.body || {};
      if (body.login_challenge) setLoginChallenge(body.login_challenge);
      if (body.retry_after_sec) {
        const seconds = Math.ceil(Number(body.retry_after_sec));
        setRetryAfter(seconds);
        setError(`Too many attempts. Try again in ${seconds}s.`);
        return;
      }
      if (body.mfa_required) {
        setStep(STEP_MFA);
        setError('');
        return;
      }
      setError(body.message || 'Invalid password.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleMfaStep(event) {
    event.preventDefault();
    if (!normalizedEmail || !password || !otpCode) return;
    setSubmitting(true);
    setError('');
    try {
      const data = await postApi('/api/auth/login', {
        email: normalizedEmail,
        password,
        otp_code: otpCode.trim(),
        login_challenge: loginChallenge,
        website: honeypot,
      });
      onAuthenticated?.(data);
      navigate(returnTo, { replace: true });
    } catch (err) {
      const body = err?.body || {};
      if (body.login_challenge) setLoginChallenge(body.login_challenge);
      if (body.retry_after_sec) {
        const seconds = Math.ceil(Number(body.retry_after_sec));
        setRetryAfter(seconds);
        setError(`Too many attempts. Try again in ${seconds}s.`);
        return;
      }
      setError(body.message || 'Invalid verification code.');
    } finally {
      setSubmitting(false);
    }
  }

  function goBack() {
    setError('');
    setRetryAfter(0);
    if (step === STEP_MFA) {
      setOtpCode('');
      setStep(STEP_PASSWORD);
      return;
    }
    if (step === STEP_PASSWORD) {
      setPassword('');
      setStep(STEP_EMAIL);
      return;
    }
  }

  const title =
    step === STEP_EMAIL ? 'Sign in' :
    step === STEP_PASSWORD ? 'Enter your password' :
    'Enter verification code';

  const subtitle =
    step === STEP_EMAIL ? 'Type your username to continue.' :
    step === STEP_PASSWORD ? 'Enter the password for this account.' :
    'Enter the verification code for this account.';

  return (
    <div style={styles.shell}>
      <div style={styles.card}>
        <img style={styles.logo} src={ynfLogo} alt="YNF Deals" />
        <div style={styles.eyebrow}>YNF Dashboard</div>
        <h1 style={styles.title}>{title}</h1>
        <p style={styles.subtitle}>{subtitle}</p>

        <input
          type="text"
          tabIndex={-1}
          value={honeypot}
          onChange={(event) => setHoneypot(event.target.value)}
          autoComplete="off"
          aria-hidden="true"
          style={{ position: 'absolute', left: '-9999px', opacity: 0, pointerEvents: 'none', width: 1, height: 1 }}
        />

        {step === STEP_EMAIL ? (
          <form onSubmit={handleEmailStep} style={styles.form}>
            <label style={styles.label} htmlFor="login-username">Username</label>
            <input
              id="login-username"
              ref={emailRef}
              type="text"
              autoComplete="off"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="sajeed"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              required
              style={styles.input}
            />
            {error ? <div style={styles.error}>{error}</div> : null}
            <button type="submit" disabled={!normalizedEmail || submitting} style={{ ...styles.primaryBtn, opacity: !normalizedEmail || submitting ? 0.6 : 1 }}>
              {submitting ? 'Checking…' : 'Continue'}
            </button>
          </form>
        ) : null}

        {step === STEP_PASSWORD ? (
          <form onSubmit={handlePasswordStep} style={styles.form}>
            <input type="text" name="username" autoComplete="username" value={normalizedEmail} readOnly hidden />
            <label style={styles.label} htmlFor="login-password">Password</label>
            <div style={styles.passwordWrap}>
              <input
                id="login-password"
                ref={passwordRef}
                type={showPw ? 'text' : 'password'}
                autoComplete="off"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your password"
                required
                style={{ ...styles.input, paddingRight: 84 }}
              />
              <button type="button" onClick={() => setShowPw((value) => !value)} style={styles.inlineBtn}>
                {showPw ? 'Hide' : 'Show'}
              </button>
            </div>
            {error ? <div style={styles.error}>{error}</div> : null}
            <div style={styles.actionRow}>
              <button type="button" onClick={goBack} style={styles.secondaryBtn}>Back</button>
              <button type="submit" disabled={!password || submitting} style={{ ...styles.primaryBtn, opacity: !password || submitting ? 0.6 : 1 }}>
                {submitting ? 'Signing in…' : 'Sign in'}
              </button>
            </div>
          </form>
        ) : null}

        {step === STEP_MFA ? (
          <form onSubmit={handleMfaStep} style={styles.form}>
            <input type="text" name="username" autoComplete="username" value={normalizedEmail} readOnly hidden />
            <label style={styles.label} htmlFor="login-mfa">Verification code</label>
            <input
              id="login-mfa"
              ref={otpRef}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={otpCode}
              onChange={(event) => setOtpCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="6-digit code"
              maxLength={6}
              required
              style={styles.input}
            />
            {error ? <div style={styles.error}>{error}</div> : null}
            <div style={styles.actionRow}>
              <button type="button" onClick={goBack} style={styles.secondaryBtn}>Back</button>
              <button type="submit" disabled={!otpCode || submitting} style={{ ...styles.primaryBtn, opacity: !otpCode || submitting ? 0.6 : 1 }}>
                {submitting ? 'Verifying…' : 'Verify'}
              </button>
            </div>
          </form>
        ) : null}

        <div style={styles.footer}>
          <span>Login, session activity, and access events are recorded.</span>
          {step !== STEP_EMAIL ? (
            <button
              type="button"
              onClick={async () => {
                setStep(STEP_EMAIL);
                setPassword('');
                setOtpCode('');
                setError('');
                await loadFreshChallenge();
              }}
              style={styles.footerLink}
            >
              Use a different account
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

const styles = {
  shell: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px',
    background: 'linear-gradient(180deg, #f7f2e8 0%, #f4eee2 100%)',
  },
  card: {
    position: 'relative',
    width: '100%',
    maxWidth: 420,
    background: 'rgba(255,255,255,0.9)',
    border: '1px solid rgba(226, 232, 240, 0.9)',
    borderRadius: 28,
    boxShadow: '0 24px 60px rgba(15, 23, 42, 0.08)',
    padding: '34px 30px 24px',
  },
  logo: {
    width: 58,
    height: 58,
    borderRadius: 18,
    display: 'block',
    objectFit: 'contain',
    marginBottom: 18,
    boxShadow: '0 16px 28px rgba(49, 95, 189, 0.20)',
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: '0.16em',
    textTransform: 'uppercase',
    color: '#a16207',
    marginBottom: 10,
  },
  title: {
    margin: 0,
    fontSize: 24,
    fontWeight: 900,
    letterSpacing: '-0.04em',
    color: '#0f172a',
  },
  subtitle: {
    margin: '10px 0 24px',
    fontSize: 14,
    lineHeight: 1.55,
    color: '#64748b',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 14,
  },
  label: {
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: '0.05em',
    textTransform: 'uppercase',
    color: '#64748b',
  },
  input: {
    width: '100%',
    borderRadius: 16,
    border: '1px solid rgba(148, 163, 184, 0.24)',
    background: '#fffdfa',
    padding: '14px 16px',
    fontSize: 15,
    color: '#0f172a',
    fontFamily: 'inherit',
    outline: 'none',
    boxSizing: 'border-box',
  },
  passwordWrap: {
    position: 'relative',
  },
  inlineBtn: {
    position: 'absolute',
    top: 10,
    right: 10,
    border: 'none',
    borderRadius: 10,
    background: 'rgba(148, 163, 184, 0.10)',
    color: '#64748b',
    padding: '7px 10px',
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  error: {
    borderRadius: 14,
    border: '1px solid rgba(239, 68, 68, 0.18)',
    background: 'rgba(239, 68, 68, 0.08)',
    color: '#b91c1c',
    padding: '11px 12px',
    fontSize: 13,
    fontWeight: 600,
  },
  actionRow: {
    display: 'grid',
    gridTemplateColumns: '1fr 1.4fr',
    gap: 10,
  },
  primaryBtn: {
    border: '1px solid rgba(217, 119, 6, 0.22)',
    background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
    color: '#fffaf0',
    borderRadius: 16,
    padding: '14px 16px',
    fontSize: 15,
    fontWeight: 800,
    cursor: 'pointer',
    fontFamily: 'inherit',
    boxShadow: '0 14px 26px rgba(245, 158, 11, 0.18)',
  },
  secondaryBtn: {
    border: '1px solid rgba(148, 163, 184, 0.24)',
    background: '#ffffff',
    color: '#475569',
    borderRadius: 16,
    padding: '14px 16px',
    fontSize: 14,
    fontWeight: 700,
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
  footer: {
    marginTop: 22,
    paddingTop: 18,
    borderTop: '1px solid rgba(226, 232, 240, 0.86)',
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    color: '#64748b',
    fontSize: 12,
    lineHeight: 1.55,
  },
  footerLink: {
    border: 'none',
    background: 'none',
    padding: 0,
    color: '#a16207',
    fontSize: 12,
    fontWeight: 700,
    textAlign: 'left',
    cursor: 'pointer',
    fontFamily: 'inherit',
  },
};
