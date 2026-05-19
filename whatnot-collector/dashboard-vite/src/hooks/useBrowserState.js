import { useEffect, useRef, useState } from 'react';

const BROWSER_STATE_EVENT = 'wn-browser-state';
export const AUTH_USER_CACHE_KEY = 'wn-auth-user-cache';

function getStorage(kind) {
  if (typeof window === 'undefined') return null;
  return kind === 'session' ? window.sessionStorage : window.localStorage;
}

function readAuthUserCache() {
  const storage = getStorage('local');
  if (!storage) return null;
  try {
    const raw = storage.getItem(AUTH_USER_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function getScopedStorageKey(baseKey, scope = 'account') {
  const key = String(baseKey || '').trim();
  if (!key || scope !== 'account') return key;
  const auth = readAuthUserCache();
  const email = String(auth?.email || '').trim().toLowerCase();
  return email ? `${key}:${email}` : key;
}

function readStored(kind, key, fallback) {
  const storage = getStorage(kind);
  if (!storage || !key) return fallback;
  try {
    const raw = storage.getItem(key);
    if (raw == null) return fallback;
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function writeStored(kind, key, value) {
  const storage = getStorage(kind);
  if (!storage || !key) return;
  try {
    if (value === undefined) {
      if (storage.getItem(key) == null) return;
      storage.removeItem(key);
      window.dispatchEvent(new CustomEvent(BROWSER_STATE_EVENT, { detail: { kind, key, value } }));
      return;
    }
    const serialized = JSON.stringify(value);
    if (storage.getItem(key) === serialized) return;
    storage.setItem(key, serialized);
    window.dispatchEvent(new CustomEvent(BROWSER_STATE_EVENT, { detail: { kind, key, value } }));
  } catch {
    // ignore storage failures
  }
}

export function useBrowserState(kind, key, initialValue) {
  const initialValueRef = useRef(initialValue);
  const [value, setValue] = useState(() => readStored(kind, key, initialValueRef.current));

  useEffect(() => {
    writeStored(kind, key, value);
  }, [kind, key, value]);

  useEffect(() => {
    setValue(readStored(kind, key, initialValueRef.current));
  }, [key, kind]);

  useEffect(() => {
    function syncFromStorage(event) {
      if (event?.detail?.kind === kind && event?.detail?.key === key) {
        setValue(event.detail.value);
      }
    }
    function syncFromNativeStorage(event) {
      if (!event.key || event.key !== key) return;
      setValue(readStored(kind, key, initialValueRef.current));
    }
    window.addEventListener(BROWSER_STATE_EVENT, syncFromStorage);
    window.addEventListener('storage', syncFromNativeStorage);
    return () => {
      window.removeEventListener(BROWSER_STATE_EVENT, syncFromStorage);
      window.removeEventListener('storage', syncFromNativeStorage);
    };
  }, [key, kind]);

  return [value, setValue];
}

export function useLocalState(key, initialValue) {
  return useBrowserState('local', key, initialValue);
}

export function useSessionState(key, initialValue) {
  return useBrowserState('session', key, initialValue);
}

export function clearBrowserState(kind, key) {
  writeStored(kind, key, undefined);
}
