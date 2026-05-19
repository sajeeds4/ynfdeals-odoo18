"""Central role and route-policy definitions for dashboard API access."""

from __future__ import annotations


MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

PUBLIC_TOKEN_POLICY = "public_token"
LIMITED_APP_READ_POLICY = "limited_app_read"
LIMITED_APP_WRITE_POLICY = "limited_app_write"
STAFF_READ_POLICY = "staff_read"
STAFF_WRITE_POLICY = "staff_write"
ADMIN_POLICY = "admin"

ROLE_LEVELS = {
    "affiliate-user": 10,
    "affiliate-owner": 20,
    "staff-read": 40,
    "staff-write": 50,
    "staff": 50,
    "admin": 100,
}

AUTH_ROLES = set(ROLE_LEVELS)

ROLE_PERMISSIONS = {
    "admin": {"*"},
    "staff": {"staff.read", "staff.write"},
    "staff-write": {"staff.read", "staff.write"},
    "staff-read": {"staff.read"},
    "affiliate-owner": {
        "affiliate.self.read",
        "affiliate.inventory.read",
        "affiliate.users.manage",
    },
    "affiliate-user": {
        "affiliate.self.read",
        "affiliate.inventory.read",
    },
}

POLICY_PERMISSIONS = {
    PUBLIC_TOKEN_POLICY: "public_token.use",
    LIMITED_APP_READ_POLICY: "staff.read",
    LIMITED_APP_WRITE_POLICY: "staff.write",
    STAFF_READ_POLICY: "staff.read",
    STAFF_WRITE_POLICY: "staff.write",
    ADMIN_POLICY: "admin.manage",
}

ROUTE_POLICY_EXACT = {
    "/api/stream_status": LIMITED_APP_READ_POLICY,
    "/api/obs/current": LIMITED_APP_READ_POLICY,
    "/api/current_lot/products": LIMITED_APP_READ_POLICY,
    "/api/obs/demo/scan": LIMITED_APP_WRITE_POLICY,
    "/api/auth/users": ADMIN_POLICY,
    "/api/auth/sessions": STAFF_READ_POLICY,
    "/api/auth/rbac": STAFF_READ_POLICY,
    "/api/auth/sessions/revoke_all": STAFF_WRITE_POLICY,
    "/api/auth/password/change": STAFF_WRITE_POLICY,
    "/api/auth/mfa/status": STAFF_READ_POLICY,
    "/api/auth/mfa/setup": STAFF_WRITE_POLICY,
    "/api/auth/mfa/confirm": STAFF_WRITE_POLICY,
    "/api/auth/mfa/disable": STAFF_WRITE_POLICY,
    "/api/employee_logins": ADMIN_POLICY,
    "/api/employee_logins/upsert": ADMIN_POLICY,
    "/api/employee_logins/revoke_sessions": ADMIN_POLICY,
    "/api/customers/reviews/sync": ADMIN_POLICY,
    "/api/upload_cookies": ADMIN_POLICY,
    "/api/employees/pos_token/create": ADMIN_POLICY,
    "/api/employees/pos_token/revoke": ADMIN_POLICY,
    "/api/employees/pos_token/rotate": ADMIN_POLICY,
    "/api/employees/pos_tokens": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/status": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/auth-url": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/connect": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/refresh": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/test": ADMIN_POLICY,
    "/api/integrations/tiktok-shop/disconnect": ADMIN_POLICY,
    "/api/in_house_orders/approve": ADMIN_POLICY,
    "/api/in_house_orders/reject": ADMIN_POLICY,
}

ROUTE_POLICY_PREFIX = (
    ("/api/auth/users/", ADMIN_POLICY),
    ("/api/integrations/tiktok-shop/", ADMIN_POLICY),
    ("/api/marketplace/", STAFF_WRITE_POLICY),
    ("/api/marketplace", STAFF_WRITE_POLICY),
)


def normalize_role(role: str | None) -> str:
    return str(role or "staff").strip().lower()


def role_permissions(role: str | None) -> set[str]:
    return set(ROLE_PERMISSIONS.get(normalize_role(role), set()))


def has_permission(role: str | None, permission: str) -> bool:
    permissions = role_permissions(role)
    return "*" in permissions or permission in permissions


def role_allows(role: str | None, policy: str) -> bool:
    if policy == PUBLIC_TOKEN_POLICY:
        return True
    if policy == LIMITED_APP_READ_POLICY:
        return has_permission(role, "staff.read") or has_permission(role, "affiliate.self.read")
    if policy == LIMITED_APP_WRITE_POLICY:
        return has_permission(role, "staff.write") or has_permission(role, "affiliate.self.read")
    permission = POLICY_PERMISSIONS.get(policy)
    if not permission:
        return False
    if has_permission(role, permission):
        return True
    if policy == ADMIN_POLICY:
        return ROLE_LEVELS.get(normalize_role(role), 0) >= ROLE_LEVELS["admin"]
    return False


def route_policy(
    path: str,
    method: str,
    *,
    public_token_paths: set[str] | None = None,
    public_token_prefixes: tuple[str, ...] = (),
) -> str:
    token_paths = public_token_paths or set()
    if path in token_paths or any(path.startswith(prefix) for prefix in public_token_prefixes):
        return PUBLIC_TOKEN_POLICY
    candidates = [path]
    if path.startswith("/api/v2/"):
        candidates.append(f"/api/{path.removeprefix('/api/v2/')}")
    for candidate in candidates:
        exact = ROUTE_POLICY_EXACT.get(candidate)
        if exact:
            return exact
        for prefix, policy in ROUTE_POLICY_PREFIX:
            if candidate.startswith(prefix):
                return policy
    if method.upper() in MUTATING_METHODS:
        return STAFF_WRITE_POLICY
    return STAFF_READ_POLICY
