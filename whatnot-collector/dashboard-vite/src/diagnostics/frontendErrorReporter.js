const FRONTEND_ERROR_ENDPOINT = '/api/v2/diagnostics/frontend-error';
const MAX_TEXT = 12000;
const DEDUPE_WINDOW_MS = 30000;
const recentReports = new Map();

function truncate(value, max = MAX_TEXT) {
  if (value == null) return '';
  const text = String(value);
  return text.length <= max ? text : `${text.slice(0, max)}...[truncated ${text.length - max} chars]`;
}

function currentRoute() {
  try {
    return `${window.location.pathname}${window.location.search}${window.location.hash}`;
  } catch {
    return '';
  }
}

function currentUrl() {
  try {
    return window.location.href;
  } catch {
    return '';
  }
}

function makeEventId(payload) {
  const parts = [
    payload.source,
    payload.message,
    payload.stack,
    payload.api_method,
    payload.api_url,
    payload.api_status,
    payload.route,
  ].map((part) => truncate(part, 240));
  let hash = 0;
  const raw = parts.join('|');
  for (let i = 0; i < raw.length; i += 1) {
    hash = ((hash << 5) - hash) + raw.charCodeAt(i);
    hash |= 0;
  }
  return `${Date.now().toString(36)}-${Math.abs(hash).toString(36)}`;
}

function dedupeKey(payload) {
  return [
    payload.source,
    payload.message,
    payload.api_method,
    payload.api_url,
    payload.api_status,
    payload.route,
  ].map((part) => truncate(part, 240)).join('|');
}

function shouldReport(payload) {
  const key = dedupeKey(payload);
  const now = Date.now();
  const last = recentReports.get(key) || 0;
  if (now - last < DEDUPE_WINDOW_MS) return false;
  recentReports.set(key, now);
  if (recentReports.size > 200) {
    for (const [entryKey, timestamp] of recentReports.entries()) {
      if (now - timestamp > DEDUPE_WINDOW_MS * 2) recentReports.delete(entryKey);
    }
  }
  return true;
}

export function reportFrontendError(input = {}) {
  try {
    const metadata = input.metadata && typeof input.metadata === 'object' ? input.metadata : {};
    const payload = {
      event_id: input.event_id || makeEventId(input),
      level: truncate(input.level || 'error', 32),
      source: truncate(input.source || 'frontend', 64),
      message: truncate(input.message || 'Unknown frontend error', 4000),
      stack: truncate(input.stack || ''),
      component_stack: truncate(input.component_stack || ''),
      url: truncate(input.url || currentUrl(), 2048),
      route: truncate(input.route || currentRoute(), 512),
      user_agent: truncate(navigator.userAgent || '', 1024),
      api_method: truncate(input.api_method || '', 16),
      api_url: truncate(input.api_url || '', 2048),
      api_status: input.api_status ?? null,
      api_status_text: truncate(input.api_status_text || '', 128),
      timestamp: new Date().toISOString(),
      metadata,
    };
    if (!shouldReport(payload)) return;
    fetch(FRONTEND_ERROR_ENDPOINT, {
      method: 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {});
  } catch {
    // Never let diagnostics create a new app failure.
  }
}

function errorToPayload(error, source, metadata = {}) {
  if (error instanceof Error) {
    return {
      source,
      message: error.message || String(error),
      stack: error.stack || '',
      metadata,
    };
  }
  return {
    source,
    message: truncate(typeof error === 'string' ? error : JSON.stringify(error)),
    stack: '',
    metadata,
  };
}

function summarizeBody(body) {
  if (!body || typeof body !== 'object') return body ?? null;
  const summary = {};
  for (const key of ['detail', 'error', 'message', 'code']) {
    if (body[key] != null) summary[key] = truncate(body[key], 1000);
  }
  summary.body_type = Array.isArray(body) ? 'array' : 'object';
  summary.body_keys = Object.keys(body).slice(0, 20);
  return summary;
}

export function reportApiFailure({ method = 'GET', path = '', status = null, statusText = '', error = null, body = null } = {}) {
  if (String(path).includes('/api/v2/diagnostics/frontend-error')) return;
  const numericStatus = Number(status || 0);
  const isNetworkFailure = !numericStatus;
  const isServerFailure = numericStatus >= 500;
  if (!isNetworkFailure && !isServerFailure) return;
  const base = errorToPayload(error || statusText || `HTTP ${status}`, isNetworkFailure ? 'api_network' : 'api_response', {
    response_body: summarizeBody(body),
  });
  reportFrontendError({
    ...base,
    level: isNetworkFailure ? 'error' : 'warning',
    api_method: method,
    api_url: path,
    api_status: numericStatus || null,
    api_status_text: statusText,
  });
}

export function installGlobalErrorHandlers() {
  if (window.__wnFrontendErrorHandlersInstalled) return;
  window.__wnFrontendErrorHandlersInstalled = true;

  window.addEventListener('error', (event) => {
    reportFrontendError({
      ...errorToPayload(event.error || event.message, 'runtime_error', {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      }),
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    reportFrontendError({
      ...errorToPayload(event.reason, 'unhandled_rejection'),
    });
  });
}
