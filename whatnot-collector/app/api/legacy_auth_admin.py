from __future__ import annotations

from fastapi import APIRouter, Body, Request, Response

from app.services.legacy_auth_admin_service import (
    get_legacy_auth_config,
    get_legacy_auth_lookup,
    get_legacy_auth_me,
    get_legacy_auth_mfa_status,
    get_legacy_auth_rbac,
    get_legacy_auth_sessions,
    get_legacy_auth_users,
    get_legacy_employee_logins,
    mutate_legacy_auth_login,
    mutate_legacy_auth_logout,
    mutate_legacy_auth_mfa_confirm,
    mutate_legacy_auth_mfa_disable,
    mutate_legacy_auth_mfa_setup,
    mutate_legacy_auth_password_change,
    mutate_legacy_auth_revoke_all,
    mutate_legacy_auth_users_revoke_sessions,
    mutate_legacy_auth_users_upsert,
    mutate_legacy_company_sync_from_odoo_removed,
    mutate_legacy_employee_logins_revoke_sessions,
    mutate_legacy_employee_logins_upsert,
    mutate_legacy_review_sync,
    mutate_legacy_upload_cookies,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    headers = payload.pop("_headers", None) or []
    if status:
        response.status_code = status
    for key, value in headers:
        response.headers.append(key, value)
    return payload


@router.get("/api/auth/config")
def legacy_auth_config(request: Request, response: Response):
    return _respond(get_legacy_auth_config(request), response)


@router.get("/api/auth/me")
def legacy_auth_me(request: Request, response: Response):
    return _respond(get_legacy_auth_me(request), response)


@router.get("/api/auth/lookup")
def legacy_auth_lookup(response: Response, email: str | None = None):
    return _respond(get_legacy_auth_lookup(email), response)


@router.get("/api/auth/sessions")
def legacy_auth_sessions(request: Request, response: Response):
    return _respond(get_legacy_auth_sessions(request), response)


@router.get("/api/auth/rbac")
def legacy_auth_rbac(request: Request, response: Response):
    return _respond(get_legacy_auth_rbac(request), response)


@router.get("/api/auth/users")
def legacy_auth_users(request: Request, response: Response):
    return _respond(get_legacy_auth_users(request), response)


@router.get("/api/employee_logins")
def legacy_employee_logins(request: Request, response: Response, q: str | None = None, email: str | None = None):
    return _respond(get_legacy_employee_logins(request, q=q, email=email), response)


@router.get("/api/auth/mfa/status")
def legacy_auth_mfa_status(request: Request, response: Response):
    return _respond(get_legacy_auth_mfa_status(request), response)


@router.post("/api/auth/login")
def legacy_auth_login(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_login(request, payload or {}), response)


@router.post("/api/auth/logout")
def legacy_auth_logout(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_logout(request), response)


@router.post("/api/auth/sessions/revoke_all")
def legacy_auth_revoke_all(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_revoke_all(request), response)


@router.post("/api/auth/password/change")
def legacy_auth_password_change(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_password_change(request, payload or {}), response)


@router.post("/api/auth/users/upsert")
def legacy_auth_users_upsert(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_users_upsert(request, payload or {}), response)


@router.post("/api/auth/users/revoke_sessions")
def legacy_auth_users_revoke_sessions(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_users_revoke_sessions(request, payload or {}), response)


@router.post("/api/employee_logins/upsert")
def legacy_employee_logins_upsert(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_employee_logins_upsert(request, payload or {}), response)


@router.post("/api/employee_logins/revoke_sessions")
def legacy_employee_logins_revoke_sessions(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_employee_logins_revoke_sessions(request, payload or {}), response)


@router.post("/api/auth/mfa/setup")
def legacy_auth_mfa_setup(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_mfa_setup(request), response)


@router.post("/api/auth/mfa/confirm")
def legacy_auth_mfa_confirm(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_mfa_confirm(request, payload or {}), response)


@router.post("/api/auth/mfa/disable")
def legacy_auth_mfa_disable(request: Request, response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_auth_mfa_disable(request, payload or {}), response)


@router.post("/api/customers/reviews/sync")
def legacy_customers_reviews_sync(request: Request, response: Response, payload: dict | None = Body(default=None)):
    response.status_code = 410
    return {"ok": False, "error": "reviews_feature_removed"}


@router.post("/api/upload_cookies")
async def legacy_upload_cookies(request: Request, response: Response):
    raw = await request.body()
    return _respond(mutate_legacy_upload_cookies(request, raw), response)


@router.post("/api/company/sync_from_odoo")
def legacy_company_sync_from_odoo_removed(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_legacy_company_sync_from_odoo_removed(), response)
