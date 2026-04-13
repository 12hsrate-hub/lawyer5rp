from __future__ import annotations

import json

from fastapi import HTTPException, status

from ogp_web.services.object_storage_service import ObjectStorageService
from ogp_web.storage.artifact_repository import ArtifactRepository


class AttachmentService:
    def __init__(self, *, repository: ArtifactRepository, storage_service: ObjectStorageService):
        self.repository = repository
        self.storage_service = storage_service

    @staticmethod
    def _deserialize(row):
        payload = dict(row)
        payload["metadata_json"] = json.loads(payload.get("metadata_json") or "{}")
        payload["created_at"] = str(payload.get("created_at") or "")
        if "linked_at" in payload:
            payload["linked_at"] = str(payload.get("linked_at") or "")
        return payload

    def _resolve_actor(self, username: str) -> int:
        actor_id = self.repository.get_user_id_by_username(username)
        if actor_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Пользователь не найден."])
        return actor_id

    def _get_version_or_403(self, *, version_id: int, user_server_id: str):
        version = self.repository.get_document_version(version_id=version_id)
        if version is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Версия документа не найдена."])
        if str(version.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для версии документа."])
        return dict(version)

    def create_upload_url(
        self,
        *,
        username: str,
        user_server_id: str,
        document_version_id: int,
        filename: str,
        mime_type: str,
        size_bytes: int,
        link_type: str,
        ttl_seconds: int,
    ):
        version = self._get_version_or_403(version_id=document_version_id, user_server_id=user_server_id)
        actor_id = self._resolve_actor(username)
        storage_key = self.storage_service.build_storage_key(
            server_id=user_server_id,
            entity_type="attachments",
            entity_id=document_version_id,
            filename=filename,
        )
        row = self.repository.create_attachment(
            server_id=user_server_id,
            uploaded_by=actor_id,
            storage_key=storage_key,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum="",
            upload_status="pending",
            metadata_json={"document_version_id": document_version_id, "expected_size_bytes": size_bytes},
        )
        attachment = self._deserialize(row)
        self.repository.create_document_version_attachment_link(
            document_version_id=document_version_id,
            attachment_id=int(attachment["id"]),
            link_type=link_type,
            created_by=actor_id,
        )
        presigned = self.storage_service.generate_presigned_upload_url(
            storage_key=storage_key,
            ttl_seconds=ttl_seconds,
            content_type=mime_type,
            size_bytes=size_bytes,
        )
        return {
            "attachment": attachment,
            "upload": presigned,
            "document_version_id": int(version["id"]),
        }

    def finalize_upload(self, *, username: str, user_server_id: str, attachment_id: int):
        self._resolve_actor(username)
        row = self.repository.get_attachment_with_version(attachment_id=attachment_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Attachment не найден."])
        payload = self._deserialize(row)
        if str(payload.get("document_server_id") or payload.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для attachment."])
        expected_size = int(payload.get("size_bytes") or 0) or None
        metadata = self.storage_service.finalize_upload(storage_key=str(payload["storage_key"]), expected_max_size=expected_size)
        updated = self.repository.update_attachment_upload_status(
            attachment_id=attachment_id,
            upload_status="uploaded",
            mime_type=payload.get("mime_type") or metadata.mime_type,
            size_bytes=metadata.size_bytes,
            checksum=metadata.checksum,
            metadata_json={**payload.get("metadata_json", {}), "finalized": True},
        )
        return self._deserialize(updated)

    def list_attachments(self, *, user_server_id: str, document_version_id: int):
        self._get_version_or_403(version_id=document_version_id, user_server_id=user_server_id)
        return [self._deserialize(row) for row in self.repository.list_attachments_for_document_version(document_version_id=document_version_id)]

    def get_download_url(self, *, user_server_id: str, attachment_id: int, ttl_seconds: int = 600):
        row = self.repository.get_attachment_with_version(attachment_id=attachment_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Attachment не найден."])
        payload = self._deserialize(row)
        if str(payload.get("document_server_id") or payload.get("server_id") or "") != user_server_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=["Недостаточно прав для attachment."])
        if payload.get("upload_status") != "uploaded":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=["Attachment ещё не финализирован."])
        presigned = self.storage_service.generate_presigned_download_url(
            storage_key=str(payload["storage_key"]),
            ttl_seconds=ttl_seconds,
        )
        return {"attachment_id": attachment_id, **presigned}

    def unlink_attachment(self, *, user_server_id: str, document_version_id: int, attachment_id: int):
        self._get_version_or_403(version_id=document_version_id, user_server_id=user_server_id)
        deleted = self.repository.delete_attachment_link(document_version_id=document_version_id, attachment_id=attachment_id)
        if deleted <= 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=["Attachment link не найден."])
