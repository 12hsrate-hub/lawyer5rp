from __future__ import annotations

from typing import Any

from ogp_web.storage.user_store import UserStore


def list_roles_payload(*, user_store: UserStore) -> dict[str, Any]:
    items = user_store.list_roles()
    return {
        "ok": True,
        "items": items,
        "count": len(items),
    }


def list_permissions_payload(*, user_store: UserStore) -> dict[str, Any]:
    items = user_store.list_permissions()
    return {
        "ok": True,
        "items": items,
        "count": len(items),
    }


def build_server_access_summary_payload(*, user_store: UserStore, server_code: str) -> dict[str, Any]:
    normalized_server = str(server_code or "").strip().lower()
    if not normalized_server:
        raise ValueError("server_code_required")
    users = user_store.list_users(limit=500)
    items: list[dict[str, Any]] = []
    permission_totals: dict[str, int] = {}
    for row in users:
        item = dict(row or {})
        current_server = str(item.get("server_code") or "").strip().lower()
        if current_server != normalized_server:
            continue
        username = str(item.get("username") or "").strip().lower()
        if not username:
            continue
        permission_codes = sorted(user_store.get_permission_codes(username, server_code=normalized_server))
        assignments = user_store.list_user_role_assignments(username, server_code=normalized_server)
        for code in permission_codes:
            permission_totals[code] = permission_totals.get(code, 0) + 1
        items.append(
            {
                "username": username,
                "display_name": str(item.get("username") or username),
                "email": str(item.get("email") or ""),
                "permissions": permission_codes,
                "assignments": assignments,
                "is_tester": bool(item.get("is_tester")),
                "is_gka": bool(item.get("is_gka")),
                "is_blocked": bool(item.get("access_blocked_at")),
                "is_deactivated": bool(item.get("deactivated_at")),
            }
        )
    items.sort(key=lambda entry: str(entry.get("display_name") or entry.get("username") or "").lower())
    return {
        "ok": True,
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
        "permission_totals": [
            {"code": code, "count": count}
            for code, count in sorted(permission_totals.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    }


def list_user_role_assignments_payload(*, user_store: UserStore, username: str, server_code: str = "") -> dict[str, Any]:
    normalized_username = str(username or "").strip().lower()
    if not normalized_username:
        raise ValueError("username_required")
    items = user_store.list_user_role_assignments(normalized_username, server_code=server_code or None)
    return {
        "ok": True,
        "username": normalized_username,
        "server_code": str(server_code or "").strip().lower(),
        "items": items,
        "count": len(items),
    }


def assign_user_role_payload(*, user_store: UserStore, username: str, role_code: str, server_code: str = "") -> dict[str, Any]:
    assignment = user_store.assign_role_to_user(username, role_code, server_code=server_code or None)
    return {
        "ok": True,
        "assignment": assignment,
    }


def revoke_user_role_assignment_payload(*, user_store: UserStore, username: str, assignment_id: str) -> dict[str, Any]:
    assignment = user_store.revoke_role_assignment(username, assignment_id)
    return {
        "ok": True,
        "assignment": assignment,
    }
