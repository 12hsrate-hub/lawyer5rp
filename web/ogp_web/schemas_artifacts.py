from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _required(value: str, name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{name} is required.")
    return normalized


class AttachmentUploadUrlRequest(BaseModel):
    filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = Field(default=1, ge=1)
    link_type: str = "supporting"
    ttl_seconds: int = Field(default=900, ge=60, le=3600)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        return _required(value, "filename")

    @field_validator("link_type")
    @classmethod
    def validate_link_type(cls, value: str) -> str:
        normalized = _required(value, "link_type").lower()
        allowed = {"evidence", "supporting", "source_file", "other"}
        if normalized not in allowed:
            raise ValueError("Unsupported link_type.")
        return normalized


class AttachmentResponse(BaseModel):
    id: int
    server_id: str
    uploaded_by: int
    storage_key: str
    filename: str
    mime_type: str
    size_bytes: int
    checksum: str
    upload_status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class AttachmentDownloadUrlResponse(BaseModel):
    attachment_id: int
    url: str
    expires_at: int
    constraints: dict[str, Any] = Field(default_factory=dict)


class AttachmentUploadUrlResponse(BaseModel):
    document_version_id: int
    attachment: AttachmentResponse
    upload: dict[str, Any]


class ExportCreateRequest(BaseModel):
    format: str = "json"
    execution_mode: str = "sync"

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        return _required(value, "format").lower()

    @field_validator("execution_mode")
    @classmethod
    def validate_execution_mode(cls, value: str) -> str:
        normalized = _required(value, "execution_mode").lower()
        if normalized not in {"sync", "async"}:
            raise ValueError("execution_mode must be sync or async.")
        return normalized


class ExportResponse(BaseModel):
    id: int
    document_version_id: int
    server_id: str
    format: str
    status: str
    storage_key: str
    mime_type: str
    size_bytes: int
    checksum: str
    created_by: int
    job_run_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class ExportDownloadUrlResponse(BaseModel):
    export_id: int
    url: str
    expires_at: int
    constraints: dict[str, Any] = Field(default_factory=dict)
