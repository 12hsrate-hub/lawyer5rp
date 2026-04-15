#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT_DIR / "web"
for candidate in (ROOT_DIR, WEB_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from ogp_web.db.factory import get_database_backend
from ogp_web.env import load_web_env
from ogp_web.storage.content_workflow_repository import ContentWorkflowRepository


def _resolve_bootstrap_pack(server_code: str) -> Path:
    return ROOT_DIR / "web" / "ogp_web" / "server_config" / "packs" / f"{server_code}.bootstrap.json"


def _load_bootstrap_pack(server_code: str) -> dict[str, object]:
    pack_path = _resolve_bootstrap_pack(server_code)
    if not pack_path.exists():
        raise FileNotFoundError(f"Missing bootstrap pack: {pack_path}")
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("Bootstrap pack root must be an object")
    return payload


def _pack_value(payload: dict[str, object], key_path: tuple[str, ...], *, default: str = "") -> str:
    current: object = payload
    for key in key_path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return str(current if current is not None else default)


def _check_content_item(*, repository: ContentWorkflowRepository, server_code: str, content_type: str, content_key: str) -> dict[str, object]:
    item = repository.get_content_item_by_identity(
        server_scope="server",
        server_id=server_code,
        content_type=content_type,
        content_key=content_key,
    )
    if not item:
        return {
            "content_type": content_type,
            "content_key": content_key,
            "has_item": False,
            "has_published_version": False,
            "item_id": None,
            "published_version_id": None,
            "errors": ["missing_content_item"],
        }

    version_id = item.get("current_published_version_id")
    published_version = repository.get_content_version(version_id=int(version_id)) if version_id else None
    payload = published_version.get("payload_json") if published_version else {}
    payload = payload if isinstance(payload, dict) else {}

    return {
        "content_type": content_type,
        "content_key": content_key,
        "has_item": True,
        "has_published_version": bool(published_version),
        "item_id": item.get("id"),
        "item_status": str(item.get("status") or "unknown"),
        "published_version_id": published_version.get("id") if published_version else None,
        "published_version_number": published_version.get("version_number") if published_version else None,
        "payload_fields": sorted(str(key) for key in payload.keys()),
        "errors": [] if published_version else ["missing_published_version"],
    }


def _find_rehab_validation_rule(*, repository: ContentWorkflowRepository, server_code: str) -> tuple[bool, str | None, dict[str, object] | None]:
    candidate_keys = ("rehab_default", "rehab_validation", "rehab_rules")
    for key in candidate_keys:
        check = _check_content_item(
            repository=repository,
            server_code=server_code,
            content_type="validation_rules",
            content_key=key,
        )
        if check["has_published_version"]:
            return True, key, check
    return False, None, {
        "reason": "no_published_rehab_validation_rule",
        "checked_keys": list(candidate_keys),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify runtime catalog checks for blackberry + rehab")
    parser.add_argument("--server", default="blackberry", help="Server code to verify")
    parser.add_argument("--json", default="1", help="Print JSON (1) or plain text (0)")
    args = parser.parse_args()

    load_web_env()
    try:
        bootstrap_pack = _load_bootstrap_pack(args.server)
        metadata = bootstrap_pack.get("metadata") if isinstance(bootstrap_pack.get("metadata"), dict) else {}
        template_binding_key = _pack_value(
            dict(metadata),
            ("template_bindings", "rehab", "template_key"),
            default="",
        )
        document_type = _pack_value(dict(metadata), ("template_bindings", "rehab", "document_type"), default="")
        validation_profiles = metadata.get("validation_profiles") if isinstance(metadata.get("validation_profiles"), dict) else {}

        repository = ContentWorkflowRepository(get_database_backend())

        checks = [
            _check_content_item(
                repository=repository,
                server_code=args.server,
                content_type="procedures",
                content_key="rehab_law_index",
            ),
            _check_content_item(
                repository=repository,
                server_code=args.server,
                content_type="templates",
                content_key=template_binding_key or "rehab_template_v1",
            ),
            _check_content_item(
                repository=repository,
                server_code=args.server,
                content_type="laws",
                content_key="law_sources_manifest",
            ),
        ]

        validation_ok, validation_key, validation_check = _find_rehab_validation_rule(
            repository=repository,
            server_code=args.server,
        )

        required_ok = all(item["has_item"] and item["has_published_version"] for item in checks) and validation_ok

        validation_profile_present = bool("rehab" in [str(key).strip().lower() for key in dict(validation_profiles).keys()])

        summary = {
            "server_code": args.server,
            "bootstrap_pack": {
                "path": str(_resolve_bootstrap_pack(args.server)),
                "rehab_template_key": template_binding_key,
                "rehab_document_type": document_type or "rehab",
                "rehab_validation_profile_present": validation_profile_present,
            },
            "checks": checks,
            "validation_rule": {
                "found": bool(validation_ok),
                "content_key": validation_key,
                "details": validation_check,
            },
            "result": {
                "status": "PASS" if required_ok else "FAIL",
                "reason": "rehab catalog runtime checks passed" if required_ok else "rehab catalog runtime checks are incomplete",
            },
        }

        if str(args.json) != "0":
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"H1b server={args.server} status={summary['result']['status']}")
            for item in checks:
                print(
                    f"- {item['content_type']}:{item['content_key']} "
                    f"item={item['has_item']} published={item['has_published_version']}"
                )
            print(f"- validation rule found={validation_key}")

        return 0 if required_ok else 1
    except Exception as exc:  # noqa: BLE001
        error_payload = {
            "server_code": args.server,
            "result": {
                "status": "ERROR",
                "reason": str(exc),
            },
        }
        print(json.dumps(error_payload, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
