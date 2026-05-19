/**
 * Shared API client hooks for the Whatnot Live Dashboard.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { reportApiFailure } from '../diagnostics/frontendErrorReporter';

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');
const CSRF_STORAGE_KEY = 'wn-csrf-token';
const CSRF_COOKIE_KEY = 'wn_csrf';
const API_CACHE_PREFIX = 'wn-api-cache:fastapi-runtime-v2:';
const API_FALLBACK_STATS_KEY = 'wn-api-fallback-stats';
const AUTH_REQUIRED_THROTTLE_MS = 3000;
const memoryCache = new Map();
const inFlightReads = new Map();
// Track ETag + last body per GET path so 304 responses can reuse cached data.
const etagCache = new Map();
let lastAuthRequiredAt = 0;

export function getStoredCsrfToken() {
  try {
    const stored = localStorage.getItem(CSRF_STORAGE_KEY);
    if (stored) return stored;
  } catch {
    // fall through to csrf cookie fallback
  }
  try {
    const match = document.cookie
      .split(';')
      .map((item) => item.trim())
      .find((item) => item.startsWith(`${CSRF_COOKIE_KEY}=`));
    return match ? decodeURIComponent(match.slice(CSRF_COOKIE_KEY.length + 1)) : '';
  } catch {
    return '';
  }
}

export function storeCsrfToken(token) {
  try {
    if (token) localStorage.setItem(CSRF_STORAGE_KEY, token);
    else localStorage.removeItem(CSRF_STORAGE_KEY);
  } catch {
    // ignore storage failures
  }
}

export function clearApiCache() {
  memoryCache.clear();
  inFlightReads.clear();
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(API_CACHE_PREFIX)) sessionStorage.removeItem(key);
    }
  } catch {
    // ignore storage failures
  }
}

function readCache(key, fallback = null) {
  if (!key) return fallback;
  if (memoryCache.has(key)) return memoryCache.get(key);
  try {
    const raw = sessionStorage.getItem(`${API_CACHE_PREFIX}${key}`);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    memoryCache.set(key, parsed);
    return parsed;
  } catch {
    return fallback;
  }
}

function writeCache(key, value) {
  if (!key) return;
  memoryCache.set(key, value);
  try {
    sessionStorage.setItem(`${API_CACHE_PREFIX}${key}`, JSON.stringify(value));
  } catch {
    // ignore storage failures
  }
}

function readFallbackStats() {
  try {
    const raw = sessionStorage.getItem(API_FALLBACK_STATS_KEY);
    return raw ? JSON.parse(raw) : { total: 0, entries: [] };
  } catch {
    return { total: 0, entries: [] };
  }
}

function writeFallbackStats(stats) {
  try {
    sessionStorage.setItem(API_FALLBACK_STATS_KEY, JSON.stringify(stats));
  } catch {
    // ignore storage failures
  }
}

function recordFallbackUsage(primaryPath, fallbackPath, error) {
  const timestamp = new Date().toISOString();
  const stats = readFallbackStats();
  const nextEntries = [
    {
      timestamp,
      primaryPath,
      fallbackPath,
      error: error?.message || 'unknown_error',
    },
    ...(stats.entries || []),
  ].slice(0, 50);
  const next = {
    total: Number(stats.total || 0) + 1,
    entries: nextEntries,
  };
  writeFallbackStats(next);
  try {
    window.__wnApiFallbackStats = next;
    window.dispatchEvent(new CustomEvent('wn-api-fallback', {
      detail: {
        timestamp,
        primaryPath,
        fallbackPath,
        error: error?.message || 'unknown_error',
        total: next.total,
      },
    }));
  } catch {
    // ignore window/event failures
  }
  try {
    console.warn('[api-fallback]', {
      primaryPath,
      fallbackPath,
      error: error?.message || 'unknown_error',
      total: next.total,
    });
  } catch {
    // ignore console failures
  }
}

export function getApiFallbackStats() {
  return readFallbackStats();
}

export function clearApiFallbackStats() {
  writeFallbackStats({ total: 0, entries: [] });
  try {
    window.__wnApiFallbackStats = { total: 0, entries: [] };
  } catch {
    // ignore window failures
  }
}

export function setCachedApi(path, value) {
  writeCache(`poll:${path}`, value);
}

export function clearCachedApi(path) {
  const key = `poll:${path}`;
  memoryCache.delete(key);
  try {
    sessionStorage.removeItem(`${API_CACHE_PREFIX}${key}`);
  } catch {
    // ignore storage failures
  }
}

export function clearCachedApiPrefix(pathPrefix) {
  const keyPrefix = `poll:${pathPrefix}`;
  for (const key of Array.from(memoryCache.keys())) {
    if (key.startsWith(keyPrefix)) memoryCache.delete(key);
  }
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(`${API_CACHE_PREFIX}${keyPrefix}`)) sessionStorage.removeItem(key);
    }
  } catch {
    // ignore storage failures
  }
}

export function getCachedApi(path, fallback = null) {
  return readCache(`poll:${path}`, fallback);
}

function dispatchAuthRequiredOnce(detail) {
  const now = Date.now();
  if (now - lastAuthRequiredAt < AUTH_REQUIRED_THROTTLE_MS) return;
  lastAuthRequiredAt = now;
  try {
    window.dispatchEvent(new CustomEvent('wn-auth-required', { detail }));
  } catch {
    // ignore window/event failures
  }
}

async function refreshAuthContext() {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    method: 'GET',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
    },
  });
  const data = await res.json().catch(() => ({}));
  if (data?.csrf_token) storeCsrfToken(data.csrf_token);
  return data;
}

function friendlyApiErrorMessage(status, code) {
  const normalized = String(code || '').trim().toLowerCase();
  if (normalized === 'csrf_failed') {
    return 'Your session token went stale during the request. Please try once more, or refresh and sign in again if it keeps happening.';
  }
  if (normalized === 'origin_forbidden') {
    return 'This request came from a different app/tab origin than your current login. Open the dashboard from one URL only, refresh, and try again.';
  }
  if (normalized === 'session_invalid' || normalized === 'auth_required' || normalized === 'unauthorized') {
    return 'Your session expired or is no longer valid. Refresh the page and sign in again.';
  }
  if (status === 403) {
    return 'This request was blocked by dashboard security checks. Refresh the page and try again.';
  }
  if (status === 401) {
    return 'Please sign in again and retry.';
  }
  return '';
}

function normalizeApiErrorMessage(value) {
  if (value == null) return '';
  if (Array.isArray(value)) {
    const joined = value
      .map((item) => normalizeApiErrorMessage(item))
      .filter(Boolean)
      .join('; ');
    return joined;
  }
  if (typeof value === 'object') {
    if (typeof value.msg === 'string' && value.msg.trim()) return value.msg.trim();
    if (typeof value.message === 'string' && value.message.trim()) return value.message.trim();
    if (typeof value.detail === 'string' && value.detail.trim()) return value.detail.trim();
    try {
      return JSON.stringify(value);
    } catch {
      return '';
    }
  }
  return String(value || '').trim();
}

export async function fetchApi(path, options, retryState = {}) {
  const method = (options?.method || 'GET').toUpperCase();
  const isRead = method === 'GET' || method === 'HEAD';
  if (isRead && !retryState?.skipDedupe) {
    const existing = inFlightReads.get(path);
    if (existing) return existing;
    const promise = fetchApi(path, options, { ...retryState, skipDedupe: true })
      .finally(() => {
        inFlightReads.delete(path);
      });
    inFlightReads.set(path, promise);
    if (inFlightReads.size > 80) {
      const oldest = inFlightReads.keys().next().value;
      if (oldest) inFlightReads.delete(oldest);
    }
    return promise;
  }
  const csrfToken = !isRead ? getStoredCsrfToken() : '';
  const requestUrl = `${API_BASE}${path}`;
  const cachedEtagEntry = isRead ? etagCache.get(path) : null;
  let res;
  try {
    res = await fetch(requestUrl, {
      ...options,
      credentials: options?.credentials || 'same-origin',
      cache: options?.cache || 'default',
      headers: {
        'Content-Type': 'application/json',
        ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
        ...(cachedEtagEntry?.etag ? { 'If-None-Match': cachedEtagEntry.etag } : {}),
        ...(options?.headers || {}),
      },
    });
  } catch (err) {
    reportApiFailure({ method, path, error: err });
    throw err;
  }
  if (res.status === 304 && cachedEtagEntry) {
    return cachedEtagEntry.body;
  }
  const cloned = res.clone();
  const data = await res.json().catch(() => ({}));
  if (isRead && res.ok) {
    const etag = res.headers.get('ETag');
    if (etag) {
      etagCache.set(path, { etag, body: data });
      if (etagCache.size > 200) {
        const oldest = etagCache.keys().next().value;
        if (oldest) etagCache.delete(oldest);
      }
    }
  }
  if (data?.csrf_token) storeCsrfToken(data.csrf_token);
  if (!res.ok) {
    const backendErrorCode = data?.error || data?.detail || data?.message || '';
    const shouldRetryAuthContext = !isRead
      && !retryState?.retriedAfterAuthRefresh
      && (
        (res.status === 403 && ['csrf_failed', 'origin_forbidden'].includes(String(backendErrorCode || '')))
        || (res.status === 401 && ['session_invalid'].includes(String(backendErrorCode || '')))
      );
    if (shouldRetryAuthContext) {
      try {
        const authState = await refreshAuthContext();
        if (authState?.authenticated && getStoredCsrfToken()) {
          return fetchApi(path, options, { ...retryState, retriedAfterAuthRefresh: true });
        }
      } catch {
        // Fall through to normal error handling below.
      }
    }
    const normalizedMessage = normalizeApiErrorMessage(data?.detail) || normalizeApiErrorMessage(data?.error) || normalizeApiErrorMessage(data?.message);
    const friendlyMessage = friendlyApiErrorMessage(res.status, backendErrorCode);
    const error = new Error(friendlyMessage || normalizedMessage || `HTTP ${res.status}`);
    error.status = res.status;
    error.body = data;
    error.response = cloned;
    if (res.status === 401 && ['auth_required', 'unauthorized', 'session_invalid'].includes(String(data.error || ''))) {
      dispatchAuthRequiredOnce({
        path,
        status: res.status,
        error: data.error || 'unauthorized',
      });
    }
    reportApiFailure({
      method,
      path,
      status: res.status,
      statusText: res.statusText,
      error,
      body: data,
    });
    throw error;
  }
  if (isRead) writeCache(`poll:${path}`, data);
  return data;
}

export async function fetchApiWithFallback(paths, options) {
  const candidates = Array.isArray(paths) ? paths : [paths];
  let lastError = null;
  for (let index = 0; index < candidates.length; index += 1) {
    const path = candidates[index];
    if (!path) continue;
    try {
      const result = await fetchApi(path, options);
      if (index > 0) {
        recordFallbackUsage(candidates[0], path, lastError);
      }
      return result;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error('No API path available');
}

export async function postApi(path, body = {}) {
  return fetchApi(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * Hook: poll an API endpoint at a regular interval.
 * Returns { data, error, loading, refresh }
 */
export function usePolling(path, intervalMs = 3000, enabled = true, options = {}) {
  const pathsKey = JSON.stringify(Array.isArray(path) ? path.filter(Boolean) : [path].filter(Boolean));
  const paths = JSON.parse(pathsKey);
  const primaryPath = paths[0];
  const useCache = options.useCache !== false;
  const hydrateFromCache = options.hydrateFromCache !== false;
  const pauseWhenHidden = options.pauseWhenHidden !== false;
  const refreshOnFocus = options.refreshOnFocus !== false;
  const cacheKey = `poll:${primaryPath}`;
  const initialCached = useCache && hydrateFromCache ? readCache(cacheKey, null) : null;
  const [data, setData] = useState(initialCached);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(initialCached == null);
  const mountedRef = useRef(true);
  const timerRef = useRef(null);

  const doFetch = useCallback(async () => {
    if (!enabled) return;
    const candidatePaths = JSON.parse(pathsKey);
    try {
      const result = await fetchApiWithFallback(candidatePaths);
      if (mountedRef.current) {
        setData(result);
        if (useCache) writeCache(cacheKey, result);
        setError(null);
        setLoading(false);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message);
        setLoading(false);
      }
    }
  }, [pathsKey, enabled, useCache, cacheKey]);

  useEffect(() => {
    const cached = useCache && hydrateFromCache ? readCache(cacheKey, null) : null;
    setData(cached);
    setError(null);
    setLoading(cached == null);
  }, [cacheKey, useCache, hydrateFromCache]);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    // Jitter ±15% so mass-mounted pollers don't align into thundering herds.
    const jitteredDelay = () => {
      const variance = intervalMs * 0.15;
      return Math.max(50, intervalMs + (Math.random() * 2 - 1) * variance);
    };
    async function loop() {
      while (!cancelled) {
        if (pauseWhenHidden && typeof document !== 'undefined' && document.visibilityState === 'hidden') {
          await new Promise((r) => { timerRef.current = setTimeout(r, intervalMs); });
          continue;
        }
        await doFetch();
        if (cancelled) break;
        await new Promise((r) => { timerRef.current = setTimeout(r, jitteredDelay()); });
      }
    }
    loop();
    // Debounce focus/visibility refetches so window-focus + visibilitychange
    // don't fire two simultaneous requests per hook on tab return.
    let focusDebounceTimer = null;
    const triggerFocusRefresh = () => {
      if (!refreshOnFocus || cancelled) return;
      if (pauseWhenHidden && typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
      if (focusDebounceTimer) return;
      focusDebounceTimer = setTimeout(() => {
        focusDebounceTimer = null;
        if (!cancelled) doFetch();
      }, 250);
    };
    const handleVisibilityRefresh = () => {
      if (typeof document === 'undefined' || document.visibilityState !== 'visible') return;
      triggerFocusRefresh();
    };
    if (refreshOnFocus && typeof window !== 'undefined') {
      window.addEventListener('focus', triggerFocusRefresh);
      if (typeof document !== 'undefined') {
        document.addEventListener('visibilitychange', handleVisibilityRefresh);
      }
    }
    return () => {
      cancelled = true;
      mountedRef.current = false;
      clearTimeout(timerRef.current);
      if (focusDebounceTimer) clearTimeout(focusDebounceTimer);
      if (refreshOnFocus && typeof window !== 'undefined') {
        window.removeEventListener('focus', triggerFocusRefresh);
        if (typeof document !== 'undefined') {
          document.removeEventListener('visibilitychange', handleVisibilityRefresh);
        }
      }
    };
  }, [doFetch, intervalMs, pauseWhenHidden, refreshOnFocus]);

  return { data, error, loading, refresh: doFetch };
}

/**
 * Hook: poll the event stream, returning new events since an ID.
 * @param {number} intervalMs  - polling interval
 * @param {string|null} streamUrl - if set, fetches events for that specific stream URL
 * @param {number|null} streamId - preferred exact stream id for restarted spectator sessions
 * Returns { events, latestId }
 */
export function useEvents(intervalMs = 1000, streamUrl = null, streamId = null, options = {}) {
  const bootstrapLimit = Math.max(50, Number(options.bootstrapLimit || 300));
  const maxEvents = Math.max(500, Number(options.maxEvents || 2000));
  const batchLimit = Math.max(100, Number(options.batchLimit || 1000));
  const maxCatchUpBatches = Math.max(1, Number(options.maxCatchUpBatches || 12));
  const eventsCacheKey = `events:${streamId || streamUrl || 'global'}`;
  const initialEventsCache = readCache(eventsCacheKey, { events: [], latestId: 0 });
  const [events, setEvents] = useState(initialEventsCache.events || []);
  const [latestId, setLatestId] = useState(initialEventsCache.latestId || 0);
  const [loading, setLoading] = useState(!(initialEventsCache.events || []).length);
  const [error, setError] = useState(null);
  const [lastSuccessAt, setLastSuccessAt] = useState(null);
  const [stale, setStale] = useState(false);
  const [isCatchingUp, setIsCatchingUp] = useState(false);
  const latestIdRef = useRef(0);
  const mountedRef = useRef(true);
  const lastSuccessRef = useRef(0);
  const wasHiddenRef = useRef(false);

  // Reset events when the target stream changes
  useEffect(() => {
    const cached = readCache(eventsCacheKey, { events: [], latestId: 0 });
    setEvents(cached.events || []);
    setLatestId(cached.latestId || 0);
    setLoading(!(cached.events || []).length);
    setError(null);
    setLastSuccessAt(null);
    setStale(false);
    setIsCatchingUp(false);
    latestIdRef.current = cached.latestId || 0;
    lastSuccessRef.current = 0;
  }, [eventsCacheKey, streamUrl, streamId]);

  useEffect(() => {
    mountedRef.current = true;
    const streamSuffix = streamId
      ? `&stream_id=${encodeURIComponent(streamId)}`
      : streamUrl
        ? `&stream_url=${encodeURIComponent(streamUrl)}`
        : '';
    const recentPaths = options.recentPaths || [`/recent?limit=${bootstrapLimit}${streamSuffix}`];
    const eventsPaths = options.eventsPaths || ((since) => [`/events?since=${since}&limit=${batchLimit}${streamSuffix}`]);
    const staleAfterMs = Math.max(intervalMs * 4, 10000);
    let refreshInFlight = false;

    const markSuccess = () => {
      const now = Date.now();
      lastSuccessRef.current = now;
      if (!mountedRef.current) return;
      setLoading(false);
      setError(null);
      setLastSuccessAt(now);
      setStale(false);
    };

    const markFailure = (err) => {
      if (!mountedRef.current) return;
      setLoading(false);
      setError(err?.message || 'Unable to refresh live events');
      if (lastSuccessRef.current && (Date.now() - lastSuccessRef.current) > staleAfterMs) {
        setStale(true);
      }
    };

    const appendEvents = (incoming) => {
      if (!incoming?.length || !mountedRef.current) return;
      setEvents((prev) => {
        const combined = [...prev, ...incoming];
        const next = combined.slice(-maxEvents);
        const maxId = Math.max(...incoming.map((e) => e.id));
        writeCache(eventsCacheKey, { events: next, latestId: maxId });
        return next;
      });
      const maxId = Math.max(...incoming.map((e) => e.id));
      latestIdRef.current = maxId;
      setLatestId(maxId);
    };

    const drainEvents = async (reason = 'interval') => {
      if (refreshInFlight) return;
      refreshInFlight = true;
      const idleGapMs = lastSuccessRef.current ? (Date.now() - lastSuccessRef.current) : 0;
      const shouldShowCatchUp = reason === 'resume' || idleGapMs > Math.max(intervalMs * 3, 4000);
      if (mountedRef.current && shouldShowCatchUp) setIsCatchingUp(true);
      try {
        let cursor = latestIdRef.current;
        let loops = 0;
        while (loops < maxCatchUpBatches) {
          const res = await fetchApiWithFallback(eventsPaths(cursor));
          if (!mountedRef.current) return;
          const newEvts = res.events || [];
          if (newEvts.length === 0) {
            markSuccess();
            return;
          }
          appendEvents(newEvts);
          cursor = Math.max(...newEvts.map((e) => e.id));
          loops += 1;
          if (!res.has_more || newEvts.length < batchLimit) {
            markSuccess();
            return;
          }
        }
        markSuccess();
      } catch (err) {
        markFailure(err);
      } finally {
        refreshInFlight = false;
        if (mountedRef.current) setIsCatchingUp(false);
      }
    };

    // Bootstrap: get recent events
    fetchApiWithFallback(recentPaths).then(res => {
      if (!mountedRef.current) return;
      const evts = res.events || [];
      setEvents(evts);
      if (evts.length > 0) {
        const maxId = Math.max(...evts.map(e => e.id));
        latestIdRef.current = maxId;
        setLatestId(maxId);
        writeCache(eventsCacheKey, { events: evts.slice(-maxEvents), latestId: maxId });
      } else {
        writeCache(eventsCacheKey, { events: [], latestId: 0 });
      }
      markSuccess();
    }).catch((err) => {
      markFailure(err);
    });

    const handleVisibilityRefresh = () => {
      if (document.visibilityState === 'hidden') {
        wasHiddenRef.current = true;
        return;
      }
      if (document.visibilityState === 'visible') {
        const reason = wasHiddenRef.current ? 'resume' : 'interval';
        wasHiddenRef.current = false;
        drainEvents(reason);
      }
    };

    const id = setInterval(() => {
      drainEvents('interval');
    }, intervalMs);
    const handleWindowFocus = () => {
      const reason = wasHiddenRef.current ? 'resume' : 'interval';
      wasHiddenRef.current = false;
      drainEvents(reason);
    };
    window.addEventListener('focus', handleWindowFocus);
    document.addEventListener('visibilitychange', handleVisibilityRefresh);

    return () => {
      mountedRef.current = false;
      clearInterval(id);
      window.removeEventListener('focus', handleWindowFocus);
      document.removeEventListener('visibilitychange', handleVisibilityRefresh);
    };
  }, [intervalMs, streamUrl, streamId, bootstrapLimit, maxEvents, batchLimit, maxCatchUpBatches, eventsCacheKey, options.recentPaths, options.eventsPaths]);

  return { events, latestId, loading, error, lastSuccessAt, stale, isCatchingUp };
}
