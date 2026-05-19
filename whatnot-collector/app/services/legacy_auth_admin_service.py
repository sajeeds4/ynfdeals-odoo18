from __future__ import annotations

import json
import os
import hmac
from typing import Any

from fastapi import Request

from server.api import OUR_WHATNOT_ACCOUNT
from server.auth import (
    authenticate_user,
    auth_enabled,
    begin_totp_setup,
    change_password,
    confirm_totp_setup,
    consume_login_challenge,
    csrf_cookie_name,
    csrf_header_name,
    destroy_session,
    disable_totp,
    get_mfa_status,
    get_session,
    get_user_public_profile,
    issue_login_challenge,
    list_active_sessions,
    list_auth_activity,
    list_auth_users_public,
    lookup_auth_user,
    revoke_user_sessions,
    session_cookie_name,
    upsert_auth_user,
)
from server.config import COLLECTOR_COOKIES_PATH, DASHBOARD_HTTPS_ONLY, dashboard_origin_allowed
from server.whatnot_reviews import get_review_sync_status, sync_seller_reviews


def _with_status(payload: dict[str, Any], status: int | None = None, headers: list[tuple[str, str]] | None = None):
    if status is not None:
        payload["_status"] = status
    if headers:
        payload["_headers"] = headers
    return payload


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _current_session(request: Request) -> dict[str, Any] | None:
    return get_session(
        request.cookies.get(session_cookie_name()),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )


def _set_session_cookie_header(session_id: str, *, clear: bool = False) -> tuple[str, str]:
    pieces = [f"{session_cookie_name()}={'' if clear else session_id}", "Path=/", "HttpOnly", "SameSite=Strict"]
    if DASHBOARD_HTTPS_ONLY:
        pieces.append("Secure")
    if clear:
        pieces.append("Max-Age=0")
        pieces.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    return ("Set-Cookie", "; ".join(pieces))


def _set_csrf_cookie_header(csrf_token: str, *, clear: bool = False) -> tuple[str, str]:
    pieces = [f"{csrf_cookie_name()}={'' if clear else csrf_token}", "Path=/", "SameSite=Strict"]
    if DASHBOARD_HTTPS_ONLY:
        pieces.append("Secure")
    if clear:
        pieces.append("Max-Age=0")
        pieces.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    return ("Set-Cookie", "; ".join(pieces))


def _verify_request_origin(request: Request):
    if not auth_enabled():
        return None
    origin = (request.headers.get("Origin") or "").strip()
    referer = (request.headers.get("Referer") or "").strip()
    host = (request.headers.get("Host") or "").strip()
    if not dashboard_origin_allowed(origin=origin, referer=referer, host=host):
        return _with_status({"ok": False, "error": "origin_forbidden"}, 403)
    return None


def _require_session_auth(request: Request):
    session = _current_session(request)
    if session:
        return session, None
    return None, _with_status({"ok": False, "error": "auth_required"}, 401)


def _require_admin_auth(request: Request):
    session, error = _require_session_auth(request)
    if error:
        return None, error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return None, csrf_error
    if (session.get("role") or "") != "admin":
        return None, _with_status({"ok": False, "error": "forbidden"}, 403)
    return session, None


def _verify_csrf(request: Request, session: dict[str, Any] | None):
    origin_error = _verify_request_origin(request)
    if origin_error:
        return origin_error
    if not session:
        return _with_status({"ok": False, "error": "auth_required"}, 401)
    expected = str(session.get("csrf_token") or "")
    token = str(request.headers.get(csrf_header_name()) or "").strip()
    cookie_token = str(request.cookies.get(csrf_cookie_name()) or "").strip()
    if token and expected and hmac.compare_digest(token, expected):
        if cookie_token and not hmac.compare_digest(cookie_token, expected):
            return _with_status({"ok": False, "error": "csrf_failed"}, 403)
        return None
    return _with_status({"ok": False, "error": "csrf_failed"}, 403)


def get_legacy_auth_config(request: Request):
    challenge = issue_login_challenge(_client_ip(request))
    return {
        "ok": True,
        "auth_enabled": auth_enabled(),
        "https_only": DASHBOARD_HTTPS_ONLY,
        "csrf_header": csrf_header_name(),
        "csrf_cookie_name": csrf_cookie_name(),
        "session_cookie_name": session_cookie_name(),
        **challenge,
    }


def get_legacy_auth_me(request: Request):
    if not auth_enabled():
        return {"ok": True, "authenticated": False, "auth_enabled": False, "user": None}
    session = _current_session(request)
    if not session:
        return {"ok": True, "authenticated": False, "auth_enabled": True, "user": None}
    return _with_status({
        "ok": True,
        "authenticated": True,
        "auth_enabled": True,
        "csrf_token": session.get("csrf_token"),
        "user": get_user_public_profile(session.get("email")) or {
            "email": session.get("email"),
            "display_name": session.get("display_name"),
            "role": session.get("role"),
            "mfa_enabled": False,
            "backup_codes_remaining": 0,
        },
    }, headers=[_set_csrf_cookie_header(session.get("csrf_token") or "")])


def get_legacy_auth_lookup(email: str | None):
    return {"ok": True, **lookup_auth_user((email or "").strip().lower())}


def get_legacy_auth_sessions(request: Request):
    if not auth_enabled():
        return _with_status({"ok": False, "error": "auth_disabled"}, 400)
    session = _current_session(request)
    if not session:
        return _with_status({"ok": False, "error": "auth_required"}, 401)
    current_id = session.get("id")
    rows = []
    for row in list_active_sessions(session.get("email")):
        row["current"] = row.get("id") == current_id
        rows.append(row)
    return {"ok": True, "sessions": rows}


def get_legacy_auth_rbac(request: Request):
    if not auth_enabled():
        return {
            "ok": True,
            "auth_enabled": False,
            "roles": [],
            "route_policies": [],
            "notes": ["Dashboard auth is disabled, so RBAC is not enforced."],
        }
    session, error = _require_session_auth(request)
    if error:
        return error
    return {
        "ok": True,
        "auth_enabled": True,
        "current_user": {
            "email": session.get("email"),
            "display_name": session.get("display_name"),
            "role": session.get("role") or "staff",
        },
        "roles": [
            {
                "role": "admin",
                "level": 100,
                "description": "Full dashboard administration, user management, POS token management, cookie upload, and approval workflows.",
            },
            {
                "role": "staff-write",
                "level": 50,
                "description": "Staff dashboard access with normal read/write operations that are not explicitly admin-only.",
            },
            {
                "role": "staff",
                "level": 50,
                "description": "Backward-compatible alias for staff-write.",
            },
            {
                "role": "staff-read",
                "level": 40,
                "description": "Staff dashboard access for read-only operational views.",
            },
        ],
        "route_policies": [
            {
                "policy": "public",
                "routes": [
                    "GET /healthz",
                    "GET /api/v2/health",
                    "GET /api/v2/ready",
                    "GET /latest_id",
                    "GET /events",
                    "GET /recent",
                    "GET /api/auth/config",
                    "POST /api/auth/login",
                    "POST /api/v2/diagnostics/frontend-error",
                ],
            },
            {
                "policy": "staff_read",
                "routes": [
                    "GET /api/auth/me",
                    "GET /api/auth/sessions",
                    "GET /api/auth/mfa/status",
                    "GET /api/auth/rbac",
                    "GET /api/* unless listed as public/admin",
                ],
            },
            {
                "policy": "staff_write",
                "routes": [
                    "POST/PUT/PATCH/DELETE /api/* unless listed as public-token/admin",
                    "POST /api/auth/password/change",
                    "POST /api/auth/sessions/revoke_all",
                    "POST /api/auth/mfa/setup",
                    "POST /api/auth/mfa/confirm",
                    "POST /api/auth/mfa/disable",
                ],
            },
            {
                "policy": "admin",
                "routes": [
                    "GET /api/auth/users",
                    "POST /api/auth/users/upsert",
                    "POST /api/auth/users/revoke_sessions",
                    "GET/POST /api/employee_logins*",
                    "POST /api/customers/reviews/sync",
                    "POST /api/upload_cookies",
                    "POST /api/employees/pos_token/*",
                    "POST /api/in_house_orders/approve",
                    "POST /api/in_house_orders/reject",
                ],
            },
            {
                "policy": "public_token",
                "routes": [
                    "POST /api/internal_pos/orders",
                    "Any /api/internal_pos/* with a valid scoped POS token",
                ],
            },
        ],
        "notes": [
            "Route middleware enforces these policies before legacy proxy fallback.",
            "Mutating authenticated requests also require a valid CSRF token.",
            "The global bearer bypass should remain disabled or IP-allowlisted for trusted automation only.",
        ],
    }


def get_legacy_auth_users(request: Request):
    if not auth_enabled():
        return _with_status({"ok": False, "error": "auth_disabled"}, 400)
    session = _current_session(request)
    if not session:
        return _with_status({"ok": False, "error": "auth_required"}, 401)
    if (session.get("role") or "") != "admin":
        return _with_status({"ok": False, "error": "forbidden"}, 403)
    return {"ok": True, "users": list_auth_users_public()}


def get_legacy_employee_logins(request: Request, q: str | None = None, email: str | None = None):
    if auth_enabled():
        session = _current_session(request)
        if not session:
            return _with_status({"ok": False, "error": "auth_required"}, 401)
        if (session.get("role") or "") != "admin":
            return _with_status({"ok": False, "error": "forbidden"}, 403)
    users = list_auth_users_public()
    query = (q or "").strip().lower()
    email_value = (email or "").strip().lower() or None
    if query:
        users = [
            row for row in users
            if query in str(row.get("email") or "").lower()
            or query in str(row.get("display_name") or "").lower()
            or query in str(row.get("role") or "").lower()
        ]
    return {
        "ok": True,
        "auth_enabled": auth_enabled(),
        "users": users,
        "sessions": list_active_sessions(email_value),
        "activity": list_auth_activity(email_value, limit=100),
    }


def get_legacy_auth_mfa_status(request: Request):
    if not auth_enabled():
        return _with_status({"ok": False, "error": "auth_disabled"}, 400)
    session, error = _require_session_auth(request)
    if error:
        return error
    try:
        return {"ok": True, **get_mfa_status(session.get("email"))}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_login(request: Request, payload: dict[str, Any]):
    origin_error = _verify_request_origin(request)
    if origin_error:
        return origin_error
    challenge_ok, challenge_error = consume_login_challenge(
        payload.get("login_challenge"),
        client_ip=_client_ip(request),
        honeypot_value=payload.get("website") or payload.get("company") or "",
    )
    if not challenge_ok:
        refreshed = issue_login_challenge(_client_ip(request))
        return _with_status(
            {"ok": False, "error": challenge_error, "message": "Unable to sign in right now.", **refreshed},
            400,
        )
    ok, message, session, user = authenticate_user(
        payload.get("email"),
        payload.get("password"),
        payload.get("otp_code"),
        client_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )
    if not ok:
        refreshed = issue_login_challenge(_client_ip(request))
        return _with_status(
            {"ok": False, "error": "invalid_credentials", "message": message, **(user or {}), **refreshed},
            401,
        )
    return _with_status(
        {
            "ok": True,
            "authenticated": True,
            "csrf_token": session.get("csrf_token"),
            "user": user,
        },
        headers=[
            _set_session_cookie_header(session.get("jwt") or session["id"]),
            _set_csrf_cookie_header(session.get("csrf_token") or ""),
        ],
    )


def mutate_legacy_auth_logout(request: Request):
    session = _current_session(request)
    if session:
        csrf_error = _verify_csrf(request, session)
        if csrf_error:
            return csrf_error
        destroy_session(session.get("id"))
    return _with_status(
        {"ok": True},
        headers=[
            _set_session_cookie_header("", clear=True),
            _set_csrf_cookie_header("", clear=True),
            ("Clear-Site-Data", "\"cache\",\"storage\""),
        ],
    )


def mutate_legacy_auth_revoke_all(request: Request):
    session, error = _require_session_auth(request)
    if error:
        return error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return csrf_error
    revoked = revoke_user_sessions(session.get("email"), reason="logout_all_devices")
    return _with_status(
        {"ok": True, "revoked": revoked},
        headers=[
            _set_session_cookie_header("", clear=True),
            _set_csrf_cookie_header("", clear=True),
        ],
    )


def mutate_legacy_auth_password_change(request: Request, payload: dict[str, Any]):
    session, error = _require_session_auth(request)
    if error:
        return error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return csrf_error
    try:
        user = change_password(
            session.get("email"),
            current_password=payload.get("current_password"),
            new_password=payload.get("new_password"),
        )
        return _with_status(
            {"ok": True, "user": user, "message": "Password updated. Please sign in again."},
            headers=[
                _set_session_cookie_header("", clear=True),
                _set_csrf_cookie_header("", clear=True),
                ("Clear-Site-Data", "\"cache\",\"storage\""),
            ],
        )
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_users_upsert(request: Request, payload: dict[str, Any]):
    session, error = _require_admin_auth(request)
    if error:
        return error
    try:
        user = upsert_auth_user(
            payload.get("email"),
            display_name=payload.get("display_name") or "",
            role=payload.get("role") or "staff",
            password=payload.get("password") or "",
            active=bool(payload.get("active", True)),
            actor_email=session.get("email"),
        )
        return {"ok": True, "user": user}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_users_revoke_sessions(request: Request, payload: dict[str, Any]):
    session, error = _require_admin_auth(request)
    if error:
        return error
    target_email = payload.get("email") or ""
    if not target_email:
        return _with_status({"ok": False, "error": "email required"}, 400)
    try:
        revoked = revoke_user_sessions(target_email, reason="admin_revoke")
        return {"ok": True, "revoked": revoked, "email": target_email}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_employee_logins_upsert(request: Request, payload: dict[str, Any]):
    if auth_enabled():
        actor_session, error = _require_admin_auth(request)
        if error:
            return error
    else:
        actor_session = _current_session(request)
    actor_email = actor_session.get("email") if actor_session else "local_admin"
    try:
        user = upsert_auth_user(
            payload.get("email"),
            display_name=payload.get("display_name") or "",
            role=payload.get("role") or "staff",
            password=payload.get("password") or "",
            active=bool(payload.get("active", True)),
            actor_email=actor_email,
        )
        return {"ok": True, "user": user}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_employee_logins_revoke_sessions(request: Request, payload: dict[str, Any]):
    if auth_enabled():
        _session, error = _require_admin_auth(request)
        if error:
            return error
    target_email = payload.get("email") or ""
    if not target_email:
        return _with_status({"ok": False, "error": "email required"}, 400)
    try:
        revoked = revoke_user_sessions(target_email, reason="employee_management_revoke")
        return {"ok": True, "revoked": revoked, "email": target_email}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_mfa_setup(request: Request):
    session, error = _require_session_auth(request)
    if error:
        return error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return csrf_error
    try:
        return {"ok": True, **begin_totp_setup(session.get("email"))}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_mfa_confirm(request: Request, payload: dict[str, Any]):
    session, error = _require_session_auth(request)
    if error:
        return error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return csrf_error
    try:
        return {"ok": True, **confirm_totp_setup(session.get("email"), payload.get("otp_code"))}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_auth_mfa_disable(request: Request, payload: dict[str, Any]):
    session, error = _require_session_auth(request)
    if error:
        return error
    csrf_error = _verify_csrf(request, session)
    if csrf_error:
        return csrf_error
    try:
        return {"ok": True, **disable_totp(session.get("email"), payload.get("otp_code"))}
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 400)


def mutate_legacy_review_sync(request: Request, payload: dict[str, Any]):
    if auth_enabled():
        _session, error = _require_admin_auth(request)
        if error:
            return error
    seller_username = str(payload.get("seller_username") or OUR_WHATNOT_ACCOUNT).strip()
    try:
        result = sync_seller_reviews(seller_username)
        status = get_review_sync_status(seller_username)
        return _with_status(
            {
                "ok": bool(result.ok),
                "result": {
                    "seller_username": result.seller_username,
                    "source_url": result.source_url,
                    "fetched": result.fetched,
                    "saved": result.saved,
                    "matched_customers": result.matched_customers,
                    "challenge_blocked": result.challenge_blocked,
                    "error": result.error,
                },
                "status": status,
            },
            200 if result.ok else 400,
        )
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)


def mutate_legacy_upload_cookies(request: Request, raw: bytes):
    if auth_enabled():
        _session, error = _require_admin_auth(request)
        if error:
            return error
    if not raw:
        return _with_status({"ok": False, "error": "empty_body"}, 400)
    if len(raw) > 10 * 1024 * 1024:
        return _with_status({"ok": False, "error": "file_too_large"}, 400)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        return _with_status({"ok": False, "error": "invalid_json"}, 400)
    if not isinstance(parsed, (list, dict)):
        return _with_status({"ok": False, "error": "unexpected_format"}, 400)
    os.makedirs(os.path.dirname(os.path.abspath(COLLECTOR_COOKIES_PATH)), exist_ok=True)
    try:
        with open(COLLECTOR_COOKIES_PATH, "wb") as fh:
            fh.write(raw)
    except Exception as exc:
        return _with_status({"ok": False, "error": str(exc)}, 500)
    count = len(parsed) if isinstance(parsed, list) else 1
    return {"ok": True, "saved_to": COLLECTOR_COOKIES_PATH, "cookie_count": count}


def mutate_legacy_company_sync_from_odoo_removed():
    return _with_status(
        {
            "ok": False,
            "error": "removed",
            "message": "Odoo sync has been retired and is no longer available.",
        },
        410,
    )
