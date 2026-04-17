from __future__ import annotations

from typing import Any

from ogp_web.storage.user_store import UserStore


def _build_access_operational_summary(*, items: list[dict[str, Any]]) -> dict[str, Any]:
    active_count = 0
    blocked_count = 0
    deactivated_count = 0
    tester_count = 0
    gka_count = 0
    assignment_count = 0
    global_assignment_count = 0
    for item in items:
        is_blocked = bool(item.get("is_blocked"))
        is_deactivated = bool(item.get("is_deactivated"))
        if is_blocked:
            blocked_count += 1
        if is_deactivated:
            deactivated_count += 1
        if not is_blocked and not is_deactivated:
            active_count += 1
        if bool(item.get("is_tester")):
            tester_count += 1
        if bool(item.get("is_gka")):
            gka_count += 1
        assignments = list(item.get("assignments") or [])
        assignment_count += len(assignments)
        global_assignment_count += sum(1 for assignment in assignments if str(assignment.get("scope") or "").strip().lower() == "global")
    if active_count <= 0:
        status = "not_configured"
        detail = f"active_users=0; total_users={len(items)}"
        next_step = "Выберите пользователя в server workspace и назначьте хотя бы одну server/global role."
    elif blocked_count > 0 or deactivated_count > 0:
        status = "partial"
        detail = (
            f"active_users={active_count}; blocked={blocked_count}; "
            f"deactivated={deactivated_count}; assignments={assignment_count}"
        )
        next_step = "Проверьте блокировки, деактивации и effective роли во вкладках «Пользователи» и «Доступ»."
    else:
        status = "ready"
        detail = (
            f"active_users={active_count}; testers={tester_count}; "
            f"gka={gka_count}; assignments={assignment_count}"
        )
        next_step = "Используйте server workspace для повседневных role changes и quick access actions."
    return {
        "status": status,
        "detail": detail,
        "next_step": next_step,
        "counts": {
            "total_users": len(items),
            "active_users": active_count,
            "blocked_users": blocked_count,
            "deactivated_users": deactivated_count,
            "tester_users": tester_count,
            "gka_users": gka_count,
            "assignments": assignment_count,
            "global_assignments": global_assignment_count,
        },
    }


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
    summary = _build_access_operational_summary(items=items)
    return {
        "ok": True,
        "server_code": normalized_server,
        "items": items,
        "count": len(items),
        "summary": summary,
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
