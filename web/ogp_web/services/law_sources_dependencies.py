from __future__ import annotations

from typing import Any


def build_sources_dependency_payload(server_rows: list[dict[str, Any]]) -> dict[str, Any]:
    dependency_index: dict[str, set[str]] = {}
    normalized_rows: list[dict[str, Any]] = []
    for row in server_rows:
        source_urls = list(row.get("source_urls") or [])
        normalized_row = {
            "server_code": row.get("server_code"),
            "server_name": row.get("server_name"),
            "source_origin": row.get("source_origin"),
            "source_count": len(source_urls),
            "source_urls": source_urls,
            "active_law_version_id": row.get("active_law_version_id"),
        }
        normalized_rows.append(normalized_row)
        for url in source_urls:
            dependency_index.setdefault(url, set()).add(str(row.get("server_code") or ""))

    for row in normalized_rows:
        shared_with: set[str] = set()
        shared_source_count = 0
        for url in row["source_urls"]:
            servers = dependency_index.get(url, set())
            if len(servers) > 1:
                shared_source_count += 1
            shared_with.update(code for code in servers if code != row["server_code"])
        row["shared_source_count"] = shared_source_count
        row["shared_with_servers"] = sorted(shared_with)

    dependency_rows = [
        {"source_url": url, "servers": sorted(servers), "server_count": len(servers)}
        for url, servers in dependency_index.items()
    ]
    dependency_rows.sort(key=lambda item: (-item["server_count"], item["source_url"]))
    normalized_rows.sort(key=lambda item: str(item["server_code"] or ""))

    return {
        "ok": True,
        "servers": normalized_rows,
        "sources": dependency_rows,
        "server_count": len(normalized_rows),
        "source_count": len(dependency_rows),
    }
