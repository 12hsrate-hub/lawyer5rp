from __future__ import annotations

import json

from fastapi import HTTPException, status

from ogp_web.storage.case_repository import CaseRepository


class CaseService:
    def __init__(self, repository: CaseRepository):
        self.repository = repository

    @staticmethod
    def _deserialize_case(row):
        payload = dict(row)
        payload["metadata_json"] = json.loads(payload.get("metadata_json") or "{}")
        payload["created_at"] = str(payload.get("created_at") or "")
        payload["updated_at"] = str(payload.get("updated_at") or "")
        return payload

    def create_case(self, *, username: str, user_server_id: str, server_id: str, title: str, case_type: str):
        if server_id != user_server_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=["Создание кейса разрешено только в текущем server scope пользователя."],
            )
        owner_user_id = self.repository.get_user_id_by_username(username)
        if owner_user_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        row = self.repository.create_case(
            server_id=server_id,
            owner_user_id=owner_user_id,
            title=title,
            case_type=case_type,
        )
        case_payload = self._deserialize_case(row)
        self.repository.create_case_event(
            case_id=int(case_payload["id"]),
            server_id=case_payload["server_id"],
            event_type="case_created",
            actor_user_id=owner_user_id,
            payload={"title": case_payload["title"], "case_type": case_payload["case_type"]},
        )
        return case_payload

    def get_case(self, *, case_id: int, user_server_id: str):
        row = self.repository.get_case(case_id=case_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Кейс не найден."])
        case_payload = self._deserialize_case(row)
        if case_payload["server_id"] != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для кейса."])
        return case_payload
