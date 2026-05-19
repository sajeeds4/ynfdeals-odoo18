import { Component } from 'react';
import { reportFrontendError } from '../diagnostics/frontendErrorReporter';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { crashed: false, message: '' };
  }

  static getDerivedStateFromError(error) {
    return {
      crashed: true,
      message: error?.message || 'The dashboard hit a rendering error.',
    };
  }

  componentDidCatch(error, info) {
    reportFrontendError({
      source: 'react_render',
      message: error?.message || 'React render error',
      stack: error?.stack || '',
      component_stack: info?.componentStack || '',
    });
  }

  render() {
    if (this.state.crashed) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 24,
          background: 'var(--bg-page, #0f172a)',
          color: 'var(--text-primary, #f8fafc)',
        }}>
          <div style={{
            maxWidth: 620,
            border: '1px solid var(--border-default, rgba(255,255,255,0.16))',
            borderRadius: 22,
            padding: 28,
            background: 'var(--bg-panel, rgba(15,23,42,0.88))',
            boxShadow: '0 24px 80px rgba(0,0,0,0.28)',
          }}>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent-coral, #fb7185)' }}>
              Frontend error captured
            </div>
            <h1 style={{ margin: '10px 0 8px', fontSize: 28 }}>The dashboard tripped over a render error.</h1>
            <p style={{ margin: 0, color: 'var(--text-secondary, #cbd5e1)', lineHeight: 1.55 }}>
              I saved the error details to Diagnostics so we can inspect it without copying console logs.
            </p>
            <pre style={{
              whiteSpace: 'pre-wrap',
              marginTop: 18,
              padding: 14,
              borderRadius: 14,
              background: 'rgba(0,0,0,0.24)',
              color: 'var(--accent-coral, #fb7185)',
              fontSize: 12,
            }}>{this.state.message}</pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                marginTop: 18,
                border: 0,
                borderRadius: 12,
                padding: '10px 14px',
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              Reload dashboard
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
