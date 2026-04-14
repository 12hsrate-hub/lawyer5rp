from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from ogp_web.storage.case_repository import CaseRepository
from ogp_web.storage.document_repository import DocumentRepository


class DocumentService:
    def __init__(self, *, case_repository: CaseRepository, document_repository: DocumentRepository):
        self.case_repository = case_repository
        self.document_repository = document_repository

    @staticmethod
    def _deserialize_document(row):
        payload = dict(row)
        payload["metadata_json"] = json.loads(payload.get("metadata_json") or "{}")
        payload["created_at"] = str(payload.get("created_at") or "")
        payload["updated_at"] = str(payload.get("updated_at") or "")
        return payload

    @staticmethod
    def _deserialize_version(row):
        payload = dict(row)
        payload["content_json"] = json.loads(payload.get("content_json") or "null")
        payload["created_at"] = str(payload.get("created_at") or "")
        return payload

    def _resolve_actor(self, username: str) -> int:
        actor_id = self.case_repository.get_user_id_by_username(username)
        if actor_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        return actor_id

    def add_document(self, *, username: str, user_server_id: str, case_id: int, document_type: str):
        case_row = self.case_repository.get_case(case_id=case_id)
        if case_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Кейс не найден."])
        case_payload = dict(case_row)
        if str(case_payload.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для кейса."])
        actor_id = self._resolve_actor(username)
        document = self._deserialize_document(
            self.document_repository.create_case_document(
                case_id=case_id,
                server_id=case_payload["server_id"],
                document_type=document_type,
                created_by=actor_id,
            )
        )
        self.case_repository.create_case_event(
            case_id=case_id,
            server_id=case_payload["server_id"],
            event_type="document_added",
            actor_user_id=actor_id,
            payload={"document_id": int(document["id"]), "document_type": document["document_type"]},
        )
        return document

    def list_case_documents(self, *, user_server_id: str, case_id: int):
        case_row = self.case_repository.get_case(case_id=case_id)
        if case_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Кейс не найден."])
        if str(case_row.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для кейса."])
        return [self._deserialize_document(row) for row in self.document_repository.list_case_documents(case_id=case_id)]

    def create_document_version(self, *, username: str, user_server_id: str, document_id: int, content_json: Any):
        doc_row = self.document_repository.get_case_document(document_id=document_id)
        if doc_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
        if str(doc_row.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для документа."])
        actor_id = self._resolve_actor(username)
        version = self._deserialize_version(
            self.document_repository.create_document_version(
                document_id=document_id,
                content_json=content_json,
                created_by=actor_id,
            )
        )
        self.case_repository.create_case_event(
            case_id=int(doc_row["case_id"]),
            server_id=str(doc_row["server_id"]),
            event_type="document_version_created",
            actor_user_id=actor_id,
            payload={"document_id": document_id, "version_number": int(version["version_number"])},
        )
        return version

    def list_document_versions(self, *, user_server_id: str, document_id: int):
        doc_row = self.document_repository.get_case_document(document_id=document_id)
        if doc_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
        if str(doc_row.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для документа."])
        return [self._deserialize_version(row) for row in self.document_repository.list_document_versions(document_id=document_id)]

    def transition_document_status(self, *, username: str, user_server_id: str, document_id: int, next_status: str):
        doc_row = self.document_repository.get_case_document(document_id=document_id)
        if doc_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
        if str(doc_row.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для документа."])
        current_status = str(doc_row.get("status") or "").strip().lower()
        target_status = str(next_status or "").strip().lower()
        allowed_transitions = {
            "draft": {"reviewed", "archived"},
            "reviewed": {"draft", "published", "archived"},
            "published": {"exported", "archived"},
            "exported": {"archived"},
            "archived": set(),
        }
        if target_status == current_status:
            return self._deserialize_document(doc_row)
        if target_status not in allowed_transitions.get(current_status, set()):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Недопустимый переход статуса документа."])
        actor_id = self._resolve_actor(username)
        updated = self.document_repository.transition_case_document_status(
            document_id=document_id,
            next_status=target_status,
            actor_user_id=actor_id,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Документ не найден."])
        self.case_repository.create_case_event(
            case_id=int(updated["case_id"]),
            server_id=str(updated["server_id"]),
            event_type="document_status_changed",
            actor_user_id=actor_id,
            payload={
                "document_id": int(updated["id"]),
                "from_status": current_status,
                "to_status": target_status,
            },
        )
        return self._deserialize_document(updated)
