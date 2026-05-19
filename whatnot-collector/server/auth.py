"""
Dashboard authentication helpers.

Implements a compact server-side session layer with:
- scrypt password verification
- optional TOTP verification
- in-memory session storage
- CSRF token issuance per session
- basic IP/account rate limiting
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time
import urllib.parse
from typing import Dict, Optional

import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from .config import (
    DASHBOARD_ADMIN_IP_ALLOWLIST,
    DASHBOARD_AUTH_REQUIRED,
    DASHBOARD_AUTH_USERS_PATH,
    DASHBOARD_CSRF_COOKIE,
    DASHBOARD_BOOTSTRAP_ADMIN_EMAIL,
    DASHBOARD_BOOTSTRAP_ADMIN_HASH,
    DASHBOARD_BOOTSTRAP_ADMIN_ROLE,
    DASHBOARD_CSRF_HEADER,
    DASHBOARD_JWT_SECRET,
    DASHBOARD_SESSION_COOKIE,
    DASHBOARD_SESSION_IDLE_TTL_SEC,
    DASHBOARD_SESSION_TTL_SEC,
    DASHBOARD_TOTP_ENCRYPTION_KEY,
    API_SECRET_KEY,
)
from .rbac import AUTH_ROLES

_SESSION_LOCK = threading.Lock()
_SESSIONS: Dict[str, dict] = {}
_FAILURES: Dict[str, list] = {}
_LOCKOUTS: Dict[str, float] = {}
_LOCKOUT_COUNTS: Dict[str, int] = {}  # progressive lockout escalation

_FAILURE_WINDOW_SEC = 10 * 60   # 10-minute sliding window
_FAILURE_LIMIT = 4              # 4 failures triggers lockout
_LOCKOUT_SEC = 15 * 60          # base lockout: 15 minutes
_LOCKOUT_SEC_MAX = 60 * 60      # cap at 1 hour after repeated lockouts
_MFA_SETUP: Dict[str, dict] = {}
_LOGIN_CHALLENGES: Dict[str, dict] = {}
_AUTH_LOG_PATH = os.path.join(os.path.dirname(DASHBOARD_AUTH_USERS_PATH or "."), "auth_audit.log")
_SESSION_STORE_PATH = os.path.join(os.path.dirname(DASHBOARD_AUTH_USERS_PATH or "."), "auth_sessions.json")
_JWT_SECRET_PATH = os.path.join(os.path.dirname(DASHBOARD_AUTH_USERS_PATH or "."), "auth_jwt_secret")
_PASSWORD_HASHER = PasswordHasher()
_LOGIN_CHALLENGE_TTL_SEC = 10 * 60
_LOGIN_CHALLENGE_MIN_AGE_SEC = 0.0

# Lazy dummy hash for constant-time verification against unknown emails
_DUMMY_HASH_LOCK = threading.Lock()
_DUMMY_HASH: Optional[str] = None

# TOTP replay-attack prevention: tracks recently used codes per user
_USED_TOTP_CODES: Dict[str, Dict[str, float]] = {}
_USED_TOTP_TTL_SEC = 95  # 30s period × 3 windows + 5s buffer

# Minimum required password length and complexity
_PASSWORD_MIN_LEN = 6


def _now() -> float:
    return time.time()


def _append_auth_log(event: str, **fields) -> None:
    try:
        os.makedirs(os.path.dirname(_AUTH_LOG_PATH), exist_ok=True)
        row = {"ts": int(_now()), "event": event, **fields}
        with open(_AUTH_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except Exception:
        pass


def audit_auth_event(event: str, **fields) -> None:
    _append_auth_log(event, **fields)


def _get_dummy_hash() -> str:
    """Return a pre-computed argon2id hash used for constant-time verification
    when the requested email doesn't exist, preventing email enumeration via timing."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        with _DUMMY_HASH_LOCK:
            if _DUMMY_HASH is None:
                _DUMMY_HASH = _PASSWORD_HASHER.hash("__timing_pad_b7z3k9m2__")
    return _DUMMY_HASH


def _cleanup_used_totp_codes() -> None:
    cutoff = _now() - _USED_TOTP_TTL_SEC
    for email in list(_USED_TOTP_CODES.keys()):
        codes = {c: ts for c, ts in _USED_TOTP_CODES[email].items() if ts > cutoff}
        if codes:
            _USED_TOTP_CODES[email] = codes
        else:
            del _USED_TOTP_CODES[email]


def _is_totp_replayed(email: str, code: str) -> bool:
    """Return True if this TOTP code was already used by this user within the replay window."""
    with _SESSION_LOCK:
        _cleanup_used_totp_codes()
        return str(code or "").strip() in (_USED_TOTP_CODES.get(email) or {})


def _mark_totp_used(email: str, code: str) -> None:
    with _SESSION_LOCK:
        if email not in _USED_TOTP_CODES:
            _USED_TOTP_CODES[email] = {}
        _USED_TOTP_CODES[email][str(code or "").strip()] = _now()


def _validate_password_policy(password: str) -> None:
    """Enforce minimum password complexity. Raises RuntimeError on violation."""
    if not password or len(password) < _PASSWORD_MIN_LEN:
        raise RuntimeError(f"Password must be at least {_PASSWORD_MIN_LEN} characters long.")
    if not any(c.isupper() for c in password):
        raise RuntimeError("Password must contain at least one uppercase letter.")
    if not any(c.isdigit() for c in password):
        raise RuntimeError("Password must contain at least one number.")
    if not any(not c.isalnum() for c in password):
        raise RuntimeError("Password must contain at least one special character.")


def _load_session_store() -> None:
    global _SESSIONS
    if not _SESSION_STORE_PATH or not os.path.exists(_SESSION_STORE_PATH):
        return
    try:
        with open(_SESSION_STORE_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            now = _now()
            cleaned = {}
            for session_id, row in payload.items():
                if isinstance(row, dict):
                    session = dict(row)
                    # Server restarts / downtime must not drain the idle timer.
                    # If idle has lapsed but the hard TTL is still valid, revive
                    # the idle window — the server simply wasn't running.
                    if session.get("idle_expires_at", 0) < now < session.get("expires_at", 0):
                        session["idle_expires_at"] = min(
                            now + DASHBOARD_SESSION_IDLE_TTL_SEC,
                            session["expires_at"],
                        )
                    cleaned[str(session_id)] = session
            _SESSIONS = cleaned
    except Exception:
        _SESSIONS = {}


def _save_session_store() -> None:
    if not _SESSION_STORE_PATH:
        return
    try:
        os.makedirs(os.path.dirname(_SESSION_STORE_PATH), exist_ok=True)
        with open(_SESSION_STORE_PATH, "w", encoding="utf-8") as fh:
            json.dump(_SESSIONS, fh, indent=2)
    except Exception:
        pass


def csrf_header_name() -> str:
    return DASHBOARD_CSRF_HEADER


def csrf_cookie_name() -> str:
    return DASHBOARD_CSRF_COOKIE


def session_cookie_name() -> str:
    return DASHBOARD_SESSION_COOKIE


def auth_enabled() -> bool:
    return bool(DASHBOARD_AUTH_REQUIRED)


def load_auth_users() -> Dict[str, dict]:
    rows: Dict[str, dict] = {}
    path = DASHBOARD_AUTH_USERS_PATH
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, list):
                for item in payload:
                    email = str((item or {}).get("email") or "").strip().lower()
                    if not email:
                        continue
                    rows[email] = {
                        "email": email,
                        "password_hash": str(item.get("password_hash") or "").strip(),
                        "role": str(item.get("role") or "staff").strip().lower() or "staff",
                        "display_name": str(item.get("display_name") or email).strip() or email,
                        "totp_secret": str(item.get("totp_secret") or "").strip(),
                        "totp_secret_encrypted": str(item.get("totp_secret_encrypted") or "").strip(),
                        "backup_code_hashes": list(item.get("backup_code_hashes") or []),
                        "mfa_required": bool(item.get("mfa_required") or item.get("totp_secret") or item.get("totp_secret_encrypted")),
                        "active": bool(item.get("active", True)),
                        "last_login_at": item.get("last_login_at"),
                    }
        except Exception:
            rows = {}
    if DASHBOARD_BOOTSTRAP_ADMIN_EMAIL and DASHBOARD_BOOTSTRAP_ADMIN_HASH:
        email = DASHBOARD_BOOTSTRAP_ADMIN_EMAIL.strip().lower()
        rows[email] = {
            "email": email,
            "password_hash": DASHBOARD_BOOTSTRAP_ADMIN_HASH.strip(),
            "role": DASHBOARD_BOOTSTRAP_ADMIN_ROLE.strip().lower() or "admin",
            "display_name": email,
            "totp_secret": "",
            "totp_secret_encrypted": "",
            "backup_code_hashes": [],
            "mfa_required": False,
            "active": True,
            "last_login_at": None,
        }
    return rows


def _normalize_login_email(email: str, users: Optional[Dict[str, dict]] = None) -> str:
    candidate = str(email or "").strip().lower()
    if not candidate:
        return ""
    if "@" in candidate:
        return candidate
    users = users or load_auth_users()
    default_match = f"{candidate}@ynfdeals.com"
    if default_match in users:
        return default_match
    matches = [
        stored_email
        for stored_email in users.keys()
        if stored_email.split("@", 1)[0] == candidate
    ]
    if len(matches) == 1:
        return matches[0]
    return candidate


def _save_auth_users(users: Dict[str, dict]) -> None:
    path = DASHBOARD_AUTH_USERS_PATH
    if not path:
        raise RuntimeError("auth_users_path_missing")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = []
    for email in sorted(users.keys()):
        row = users[email]
        payload.append({
            "email": row["email"],
            "display_name": row.get("display_name") or row["email"],
            "role": row.get("role") or "staff",
            "password_hash": row.get("password_hash") or "",
            "totp_secret_encrypted": row.get("totp_secret_encrypted") or "",
            "backup_code_hashes": row.get("backup_code_hashes") or [],
            "mfa_required": bool(row.get("mfa_required")),
            "active": bool(row.get("active", True)),
            "last_login_at": row.get("last_login_at"),
        })
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _jwt_secret() -> bytes:
    configured = (DASHBOARD_JWT_SECRET or API_SECRET_KEY or "").strip()
    if configured:
        return configured.encode("utf-8")
    try:
        os.makedirs(os.path.dirname(_JWT_SECRET_PATH), exist_ok=True)
        if os.path.exists(_JWT_SECRET_PATH):
            with open(_JWT_SECRET_PATH, "r", encoding="utf-8") as fh:
                saved = fh.read().strip()
            if saved:
                return saved.encode("utf-8")
        generated = secrets.token_urlsafe(48)
        with open(_JWT_SECRET_PATH, "w", encoding="utf-8") as fh:
            fh.write(generated)
        try:
            os.chmod(_JWT_SECRET_PATH, 0o600)
        except Exception:
            pass
        return generated.encode("utf-8")
    except Exception:
        # Last-resort fallback keeps auth functional in read-only local setups.
        return hashlib.sha256(os.path.abspath(DASHBOARD_AUTH_USERS_PATH or "auth").encode("utf-8")).digest()


def _jwt_sign(signing_input: str) -> str:
    return _base64url_encode(hmac.new(_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest())


def encode_session_jwt(session: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "typ": "dashboard_session",
        "sid": session.get("id"),
        "sub": session.get("email"),
        "role": session.get("role") or "staff",
        "iat": int(session.get("created_at") or _now()),
        "exp": int(session.get("expires_at") or (_now() + DASHBOARD_SESSION_TTL_SEC)),
        "jti": session.get("jwt_jti") or "",
    }
    header_raw = _base64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_raw = _base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_raw}.{payload_raw}"
    return f"{signing_input}.{_jwt_sign(signing_input)}"


def decode_session_jwt(token: str) -> Optional[dict]:
    token = str(token or "").strip()
    if token.count(".") != 2:
        return None
    try:
        header_raw, payload_raw, signature = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected = _jwt_sign(signing_input)
        if not hmac.compare_digest(signature, expected):
            return None
        header = json.loads(_base64url_decode(header_raw))
        payload = json.loads(_base64url_decode(payload_raw))
        if header.get("alg") != "HS256" or payload.get("typ") != "dashboard_session":
            return None
        if int(payload.get("exp") or 0) <= int(_now()):
            return None
        if not payload.get("sid") or not payload.get("sub") or not payload.get("jti"):
            return None
        return payload
    except Exception:
        return None


def hash_password(password: str, *, salt: Optional[bytes] = None, n: int = 2**14, r: int = 8, p: int = 1, scheme: str = "argon2id") -> str:
    if (scheme or "argon2id").lower() == "argon2id":
        return _PASSWORD_HASHER.hash(password)
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=64)
    return "scrypt${}${}${}${}${}".format(
        n,
        r,
        p,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    if (encoded_hash or "").startswith("$argon2id$"):
        try:
            return bool(_PASSWORD_HASHER.verify(encoded_hash, password or ""))
        except (VerifyMismatchError, InvalidHashError):
            return False
        except Exception:
            return False
    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = encoded_hash.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_raw.encode("ascii"))
        expected = base64.b64decode(digest_raw.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_raw),
            r=int(r_raw),
            p=int(p_raw),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    if (encoded_hash or "").startswith("$argon2id$"):
        try:
            return bool(_PASSWORD_HASHER.check_needs_rehash(encoded_hash))
        except Exception:
            return False
    return True


def _normalize_secret(secret: str) -> bytes:
    cleaned = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    return base64.b32decode(cleaned + padding, casefold=True)


def _fernet() -> Fernet:
    key = (DASHBOARD_TOTP_ENCRYPTION_KEY or "").strip()
    if not key:
        raise RuntimeError("DASHBOARD_TOTP_ENCRYPTION_KEY is required for TOTP setup")
    return Fernet(key.encode("utf-8"))


def _encrypt_secret(secret: str) -> str:
    if not secret:
        return ""
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def _decrypt_secret(secret_encrypted: str) -> str:
    if not secret_encrypted:
        return ""
    try:
        return _fernet().decrypt(secret_encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("invalid_totp_secret_encryption") from exc


def _user_totp_secret(user: dict) -> str:
    if user.get("totp_secret_encrypted"):
        return _decrypt_secret(user.get("totp_secret_encrypted") or "")
    return str(user.get("totp_secret") or "").strip()


def _random_base32_secret(length: int = 20) -> str:
    return base64.b32encode(secrets.token_bytes(length)).decode("ascii").rstrip("=")


def _otpauth_url(email: str, secret: str, issuer: str = "Whatnot Live Dashboard") -> str:
    label = urllib.parse.quote(f"{issuer} ({email})")
    issuer_q = urllib.parse.quote(issuer)
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_q}&algorithm=SHA1&digits=6&period=30"


def _qr_code_data_url(value: str) -> str:
    qr = qrcode.QRCode(border=2, box_size=6)
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _generate_backup_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]


def verify_totp(secret: str, code: str, *, window: int = 1, period: int = 30, digits: int = 6) -> bool:
    if not secret:
        return False
    candidate = str(code or "").strip().replace(" ", "")
    if not candidate.isdigit():
        return False
    key = _normalize_secret(secret)
    counter = int(_now() // period)
    for offset in range(-window, window + 1):
        msg = struct.pack(">Q", counter + offset)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        pos = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[pos:pos + 4])[0] & 0x7FFFFFFF
        token = str(value % (10 ** digits)).zfill(digits)
        if hmac.compare_digest(token, candidate):
            return True
    return False


def _verify_backup_code(code_hashes: list[str], candidate: str) -> tuple[bool, list[str]]:
    normalized = str(candidate or "").strip().lower()
    if not normalized:
        return False, list(code_hashes or [])
    remaining = []
    matched = False
    for encoded_hash in code_hashes or []:
        if not matched and verify_password(normalized, encoded_hash):
            matched = True
            continue
        remaining.append(encoded_hash)
    return matched, remaining


def _cleanup_sessions() -> None:
    now = _now()
    expired = []
    for session_id, row in list(_SESSIONS.items()):
        if row["expires_at"] <= now or row["idle_expires_at"] <= now:
            expired.append(session_id)
    for session_id in expired:
        _SESSIONS.pop(session_id, None)
    if expired:
        _save_session_store()


def _cleanup_login_challenges() -> None:
    now = _now()
    for token, row in list(_LOGIN_CHALLENGES.items()):
        if row.get("expires_at", 0) <= now:
            _LOGIN_CHALLENGES.pop(token, None)


def issue_login_challenge(client_ip: str) -> dict:
    token = secrets.token_urlsafe(24)
    now = _now()
    _cleanup_login_challenges()
    _LOGIN_CHALLENGES[token] = {
        "client_ip": client_ip or "unknown",
        "issued_at": now,
        "expires_at": now + _LOGIN_CHALLENGE_TTL_SEC,
    }
    return {
        "login_challenge": token,
        "login_challenge_min_delay_ms": int(_LOGIN_CHALLENGE_MIN_AGE_SEC * 1000),
    }


def consume_login_challenge(token: str, *, client_ip: str, honeypot_value: str = "") -> tuple[bool, str]:
    _cleanup_login_challenges()
    if str(honeypot_value or "").strip():
        return False, "bot_detected"
    token = str(token or "").strip()
    if not token:
        return False, "missing_login_challenge"
    row = _LOGIN_CHALLENGES.pop(token, None)
    if not row:
        return False, "invalid_login_challenge"
    if row.get("client_ip") not in {"", "unknown", client_ip}:
        return False, "invalid_login_challenge"
    age = _now() - float(row.get("issued_at") or 0)
    if age < _LOGIN_CHALLENGE_MIN_AGE_SEC:
        return False, "login_challenge_too_fast"
    if age > _LOGIN_CHALLENGE_TTL_SEC:
        return False, "login_challenge_expired"
    return True, ""


def create_session(user: dict, client_ip: str, user_agent: str) -> dict:
    session_id = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    jwt_jti = secrets.token_urlsafe(24)
    now = _now()
    session = {
        "id": session_id,
        "csrf_token": csrf_token,
        "jwt_jti": jwt_jti,
        "email": user["email"],
        "role": user.get("role") or "staff",
        "display_name": user.get("display_name") or user["email"],
        "created_at": now,
        "expires_at": now + DASHBOARD_SESSION_TTL_SEC,
        "idle_expires_at": now + DASHBOARD_SESSION_IDLE_TTL_SEC,
        "client_ip": client_ip,
        "user_agent": user_agent or "",
    }
    with _SESSION_LOCK:
        _load_session_store()
        _cleanup_sessions()
        _SESSIONS[session_id] = session
        _save_session_store()
    _append_auth_log("login_success", email=user["email"], role=session["role"], client_ip=client_ip)
    session["jwt"] = encode_session_jwt(session)
    return session


def get_session(session_id: str, *, client_ip: Optional[str] = None, user_agent: Optional[str] = None) -> Optional[dict]:
    raw_session_value = str(session_id or "").strip()
    if not raw_session_value:
        return None
    jwt_payload = decode_session_jwt(raw_session_value)
    lookup_session_id = str(jwt_payload.get("sid")) if jwt_payload else raw_session_value
    with _SESSION_LOCK:
        _load_session_store()
        _cleanup_sessions()
        session = _SESSIONS.get(lookup_session_id)
        if not session:
            return None
        if jwt_payload:
            if not hmac.compare_digest(str(jwt_payload.get("sub") or ""), str(session.get("email") or "")):
                return None
            session_jti = str(session.get("jwt_jti") or "")
            payload_jti = str(jwt_payload.get("jti") or "")
            if session_jti and not hmac.compare_digest(payload_jti, session_jti):
                return None
            if payload_jti and not session_jti:
                session["jwt_jti"] = payload_jti
            if int(jwt_payload.get("exp") or 0) > int(session.get("expires_at") or 0):
                return None
        if client_ip and session.get("client_ip") and session.get("client_ip") != client_ip:
            _append_auth_log(
                "session_ip_changed",
                email=session.get("email"),
                original_client_ip=session.get("client_ip"),
                client_ip=client_ip,
            )
        if user_agent and session.get("user_agent") and session.get("user_agent") != user_agent:
            _append_auth_log("session_user_agent_changed", email=session.get("email"))
        now = _now()
        session["idle_expires_at"] = now + DASHBOARD_SESSION_IDLE_TTL_SEC
        _SESSIONS[lookup_session_id] = session
        _save_session_store()
        return dict(session)


def destroy_session(session_id: str) -> None:
    if not session_id:
        return
    with _SESSION_LOCK:
        _load_session_store()
        session = _SESSIONS.pop(session_id, None)
        _save_session_store()
    if session:
        _append_auth_log("logout", email=session.get("email"), client_ip=session.get("client_ip"))


def revoke_user_sessions(email: str, *, reason: str = "manual_revoke") -> int:
    normalized_email = (email or "").strip().lower()
    revoked = 0
    with _SESSION_LOCK:
        _load_session_store()
        for session_id, session in list(_SESSIONS.items()):
            if session.get("email") == normalized_email:
                _SESSIONS.pop(session_id, None)
                revoked += 1
        _save_session_store()
    if normalized_email:
        _append_auth_log("sessions_revoked", email=normalized_email, reason=reason, revoked=revoked)
    return revoked


def list_active_sessions(email: Optional[str] = None) -> list[dict]:
    normalized_email = (email or "").strip().lower() if email else None
    with _SESSION_LOCK:
        _load_session_store()
        _cleanup_sessions()
        rows = []
        for session in _SESSIONS.values():
            if normalized_email and session.get("email") != normalized_email:
                continue
            rows.append({
                "id": session.get("id"),
                "email": session.get("email"),
                "role": session.get("role"),
                "display_name": session.get("display_name"),
                "client_ip": session.get("client_ip"),
                "user_agent": session.get("user_agent"),
                "created_at": session.get("created_at"),
                "expires_at": session.get("expires_at"),
                "idle_expires_at": session.get("idle_expires_at"),
            })
        rows.sort(key=lambda row: row.get("created_at") or 0, reverse=True)
        return rows


def update_user_credentials(current_email: str, *, new_email: str, new_password: str, actor_email: Optional[str] = None) -> dict:
    normalized_current = (current_email or "").strip().lower()
    normalized_new = (new_email or "").strip().lower()
    if not normalized_current:
        raise RuntimeError("current_email_required")
    if not normalized_new:
        raise RuntimeError("new_email_required")
    if not new_password:
        raise RuntimeError("new_password_required")
    users = load_auth_users()
    user = users.get(normalized_current)
    if not user:
        raise RuntimeError("user_not_found")
    if normalized_new != normalized_current and normalized_new in users:
        raise RuntimeError("email_already_exists")

    user["email"] = normalized_new
    user["password_hash"] = hash_password(new_password, scheme="argon2id")
    if normalized_new != normalized_current:
        users.pop(normalized_current, None)
    users[normalized_new] = user
    _save_auth_users(users)
    revoked = revoke_user_sessions(normalized_current, reason="credential_change")
    if normalized_new != normalized_current:
        revoked += revoke_user_sessions(normalized_new, reason="credential_change")
    _append_auth_log(
        "credentials_rotated",
        actor_email=(actor_email or normalized_new),
        target_email=normalized_new,
        previous_email=normalized_current,
        revoked_sessions=revoked,
    )
    return get_user_public_profile(normalized_new) or {
        "email": normalized_new,
        "display_name": user.get("display_name") or normalized_new,
        "role": user.get("role") or "staff",
        "mfa_enabled": bool(user.get("mfa_required")),
    }


def _register_failure(key: str) -> None:
    now = _now()
    rows = [ts for ts in _FAILURES.get(key, []) if now - ts <= _FAILURE_WINDOW_SEC]
    rows.append(now)
    _FAILURES[key] = rows
    if len(rows) >= _FAILURE_LIMIT:
        count = _LOCKOUT_COUNTS.get(key, 0) + 1
        _LOCKOUT_COUNTS[key] = count
        # Progressive escalation: 15m → 30m → 60m (capped)
        duration = min(_LOCKOUT_SEC * count, _LOCKOUT_SEC_MAX)
        _LOCKOUTS[key] = now + duration


def _clear_failures(*keys: str) -> None:
    for key in keys:
        if not key:
            continue
        _FAILURES.pop(key, None)
        _LOCKOUTS.pop(key, None)
        # Don't reset _LOCKOUT_COUNTS — history persists until server restart


def check_rate_limit(email: str, client_ip: str) -> Optional[int]:
    now = _now()
    keys = [f"ip:{client_ip}", f"acct:{email.lower().strip()}"]
    for key in keys:
        locked_until = _LOCKOUTS.get(key)
        if locked_until and locked_until > now:
            return int(locked_until - now)
    return None


def authenticate_user(email: str, password: str, otp_code: str, client_ip: str, user_agent: str) -> tuple[bool, str, Optional[dict], Optional[dict]]:
    users = load_auth_users()
    normalized_email = _normalize_login_email(email, users)
    ip_key = f"ip:{client_ip}"
    acct_key = f"acct:{normalized_email}"
    user = users.get(normalized_email)
    if user and user.get("role") == "admin" and DASHBOARD_ADMIN_IP_ALLOWLIST and client_ip not in DASHBOARD_ADMIN_IP_ALLOWLIST:
        _append_auth_log("admin_ip_blocked", email=normalized_email, client_ip=client_ip)
        # Still run dummy hash to avoid timing distinction vs. wrong password
        verify_password("__timing_pad__", _get_dummy_hash())
        return False, "Invalid email, password, or verification code.", None, None

    # Always run password verification even when user doesn't exist — this
    # prevents email enumeration via response-time differences (argon2id ≈ 300ms).
    password_hash = (user.get("password_hash") if user else None) or _get_dummy_hash()
    password_ok = verify_password(password or "", password_hash)

    user_active = bool(user and user.get("active"))
    valid = user_active and password_ok
    wait_sec = check_rate_limit(normalized_email, client_ip)
    if wait_sec and not valid:
        _append_auth_log("login_rate_limited", email=normalized_email, client_ip=client_ip, retry_after_sec=wait_sec)
        return False, "Invalid email, password, or verification code.", None, {"retry_after_sec": wait_sec}

    if valid and user.get("mfa_required"):
        secret = _user_totp_secret(user)
        candidate_code = str(otp_code or "").strip()
        if not candidate_code:
            return False, "Verification code required.", None, {
                "mfa_required": True,
                "email": normalized_email,
            }
        totp_ok = verify_totp(secret, candidate_code)
        if totp_ok:
            # Replay-attack prevention: reject re-use of the same TOTP code
            if _is_totp_replayed(normalized_email, candidate_code):
                totp_ok = False
                _append_auth_log("totp_replay_blocked", email=normalized_email, client_ip=client_ip)
            else:
                _mark_totp_used(normalized_email, candidate_code)
        if not totp_ok:
            matched_backup, remaining = _verify_backup_code(user.get("backup_code_hashes") or [], candidate_code)
            if matched_backup:
                totp_ok = True
                users[normalized_email]["backup_code_hashes"] = remaining
                _save_auth_users(users)
        valid = totp_ok

    if not valid:
        _register_failure(ip_key)
        if normalized_email:
            _register_failure(acct_key)
        _append_auth_log("login_failed", email=normalized_email, client_ip=client_ip)
        return False, "Invalid email, password, or verification code.", None, None

    if user and password_hash and password_needs_rehash(password_hash):
        users[normalized_email]["password_hash"] = hash_password(password or "", scheme="argon2id")
        _save_auth_users(users)
        user = users[normalized_email]
        _append_auth_log("password_hash_rehashed", email=normalized_email)

    _clear_failures(ip_key, acct_key)
    session = create_session(user, client_ip=client_ip, user_agent=user_agent)
    
    if user:
        import datetime
        users[normalized_email]["last_login_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        _save_auth_users(users)

    public_user = {
        "email": user["email"],
        "display_name": user.get("display_name") or user["email"],
        "role": user.get("role") or "staff",
        "mfa_enabled": bool(user.get("mfa_required")),
        "last_login_at": user.get("last_login_at"),
    }
    return True, "", session, public_user


def get_user_public_profile(email: str) -> Optional[dict]:
    user = load_auth_users().get((email or "").strip().lower())
    if not user:
        return None
    return {
        "email": user["email"],
        "display_name": user.get("display_name") or user["email"],
        "role": user.get("role") or "staff",
        "mfa_enabled": bool(user.get("mfa_required")),
        "backup_codes_remaining": len(user.get("backup_code_hashes") or []),
        "active": bool(user.get("active", True)),
        "last_login_at": user.get("last_login_at"),
    }


def lookup_auth_user(email: str) -> dict:
    users = load_auth_users()
    normalized = _normalize_login_email(email, users)
    if not normalized:
        return {"exists": False, "active": False, "mfa_enabled": False}
    user = users.get(normalized)
    if not user:
        return {"exists": False, "active": False, "mfa_enabled": False}
    return {
        "exists": True,
        "active": bool(user.get("active", True)),
        "mfa_enabled": bool(user.get("mfa_required")),
        "display_name": user.get("display_name") or user.get("email") or normalized,
    }


def list_auth_users_public() -> list[dict]:
    rows = []
    for email in sorted(load_auth_users().keys()):
        profile = get_user_public_profile(email)
        if profile:
            rows.append(profile)
    return rows


def list_auth_activity(email: Optional[str] = None, limit: int = 200) -> list[dict]:
    normalized_email = (email or "").strip().lower() if email else None
    if not _AUTH_LOG_PATH or not os.path.exists(_AUTH_LOG_PATH):
        return []
    rows = []
    try:
        with open(_AUTH_LOG_PATH, "r", encoding="utf-8") as fh:
            for line in fh:
                raw = str(line or "").strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except Exception:
                    continue
                if normalized_email:
                    candidates = {
                        str(item.get("email") or "").strip().lower(),
                        str(item.get("target_email") or "").strip().lower(),
                        str(item.get("actor_email") or "").strip().lower(),
                    }
                    if normalized_email not in candidates:
                        continue
                rows.append(item)
    except Exception:
        return []
    rows.sort(key=lambda row: float(row.get("ts") or 0), reverse=True)
    return rows[: max(1, int(limit or 200))]


def upsert_auth_user(email: str, *, display_name: str = "", role: str = "staff", password: str = "", active: bool = True, actor_email: Optional[str] = None) -> dict:
    normalized_email = (email or "").strip().lower()
    role = str(role or "staff").strip().lower()
    if not normalized_email:
        raise RuntimeError("email_required")
    if role not in AUTH_ROLES:
        raise RuntimeError("invalid_role")
    users = load_auth_users()
    existing = users.get(normalized_email) or {}
    if not existing and not password:
        raise RuntimeError("password_required")
    if password:
        _validate_password_policy(password)
    user = {
        "email": normalized_email,
        "display_name": (display_name or existing.get("display_name") or normalized_email).strip() or normalized_email,
        "role": role,
        "password_hash": existing.get("password_hash") or "",
        "totp_secret": existing.get("totp_secret") or "",
        "totp_secret_encrypted": existing.get("totp_secret_encrypted") or "",
        "backup_code_hashes": existing.get("backup_code_hashes") or [],
        "mfa_required": bool(existing.get("mfa_required")),
        "active": bool(active),
        "last_login_at": existing.get("last_login_at"),
    }
    if password:
        user["password_hash"] = hash_password(password, scheme="argon2id")
        revoke_user_sessions(normalized_email, reason="password_reset_by_admin")
    users[normalized_email] = user
    _save_auth_users(users)
    _append_auth_log(
        "auth_user_upserted",
        actor_email=(actor_email or normalized_email),
        target_email=normalized_email,
        role=role,
        active=bool(active),
        password_rotated=bool(password),
    )
    return get_user_public_profile(normalized_email)


def change_password(email: str, *, current_password: str, new_password: str) -> dict:
    normalized_email = (email or "").strip().lower()
    users = load_auth_users()
    user = users.get(normalized_email)
    if not user:
        raise RuntimeError("user_not_found")
    if not verify_password(current_password or "", user.get("password_hash") or ""):
        _append_auth_log("password_change_failed", email=normalized_email)
        raise RuntimeError("invalid_current_password")
    _validate_password_policy(new_password or "")
    user["password_hash"] = hash_password(new_password, scheme="argon2id")
    users[normalized_email] = user
    _save_auth_users(users)
    revoked = revoke_user_sessions(normalized_email, reason="password_change")
    _append_auth_log("password_changed", email=normalized_email, revoked_sessions=revoked)
    return get_user_public_profile(normalized_email)


def get_mfa_status(email: str) -> dict:
    user = load_auth_users().get((email or "").strip().lower())
    if not user:
        raise RuntimeError("user_not_found")
    pending = _MFA_SETUP.get(user["email"])
    return {
        "mfa_enabled": bool(user.get("mfa_required")),
        "backup_codes_remaining": len(user.get("backup_code_hashes") or []),
        "setup_pending": bool(pending),
    }


def begin_totp_setup(email: str) -> dict:
    user = load_auth_users().get((email or "").strip().lower())
    if not user:
        raise RuntimeError("user_not_found")
    secret = _random_base32_secret()
    otpauth_url = _otpauth_url(user["email"], secret)
    qr_code_data_url = _qr_code_data_url(otpauth_url)
    backup_codes = _generate_backup_codes()
    _MFA_SETUP[user["email"]] = {
        "secret": secret,
        "backup_codes": backup_codes,
        "backup_code_hashes": [hash_password(code.lower()) for code in backup_codes],
        "created_at": _now(),
    }
    _append_auth_log("mfa_setup_started", email=user["email"])
    return {
        "secret": secret,
        "otpauth_url": otpauth_url,
        "qr_code_data_url": qr_code_data_url,
        "backup_codes": backup_codes,
    }


def confirm_totp_setup(email: str, code: str) -> dict:
    normalized_email = (email or "").strip().lower()
    pending = _MFA_SETUP.get(normalized_email)
    if not pending:
        raise RuntimeError("mfa_setup_not_started")
    if not verify_totp(pending["secret"], code):
        raise RuntimeError("invalid_verification_code")
    users = load_auth_users()
    user = users.get(normalized_email)
    if not user:
        raise RuntimeError("user_not_found")
    user["totp_secret_encrypted"] = _encrypt_secret(pending["secret"])
    user["backup_code_hashes"] = pending.get("backup_code_hashes") or []
    user["mfa_required"] = True
    _save_auth_users(users)
    _MFA_SETUP.pop(normalized_email, None)
    _append_auth_log("mfa_enabled", email=normalized_email)
    return get_mfa_status(normalized_email)


def disable_totp(email: str, code: str) -> dict:
    normalized_email = (email or "").strip().lower()
    users = load_auth_users()
    user = users.get(normalized_email)
    if not user:
        raise RuntimeError("user_not_found")
    secret = _user_totp_secret(user)
    if not verify_totp(secret, code):
        matched_backup, remaining = _verify_backup_code(user.get("backup_code_hashes") or [], code or "")
        if not matched_backup:
            raise RuntimeError("invalid_verification_code")
    user["totp_secret_encrypted"] = ""
    user["totp_secret"] = ""
    user["backup_code_hashes"] = []
    user["mfa_required"] = False
    _save_auth_users(users)
    _MFA_SETUP.pop(normalized_email, None)
    _append_auth_log("mfa_disabled", email=normalized_email)
    return get_mfa_status(normalized_email)
