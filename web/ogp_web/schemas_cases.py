from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _require_non_empty(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


class CaseCreateRequest(BaseModel):
    server_id: str
    title: str
    case_type: str

    @field_validator("server_id")
    @classmethod
    def validate_server_id(cls, value: str) -> str:
        return _require_non_empty(value, "server_id").lower()

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _require_non_empty(value, "title")

    @field_validator("case_type")
    @classmethod
    def validate_case_type(cls, value: str) -> str:
        return _require_non_empty(value, "case_type")


class CaseResponse(BaseModel):
    id: int
    server_id: str
    owner_user_id: int
    title: str
    case_type: str
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class CaseDocumentCreateRequest(BaseModel):
    document_type: str

    @field_validator("document_type")
    @classmethod
    def validate_document_type(cls, value: str) -> str:
        return _require_non_empty(value, "document_type")


class CaseDocumentResponse(BaseModel):
    id: int
    case_id: int
    server_id: str
    document_type: str
    status: str
    created_by: int
    latest_version_id: int | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class DocumentVersionCreateRequest(BaseModel):
    content_json: dict[str, Any] | list[Any] | str | int | float | bool

    @field_validator("content_json")
    @classmethod
    def validate_content_json(cls, value):
        if value is None:
            raise ValueError("content_json is required.")
        return value


class DocumentVersionResponse(BaseModel):
    id: int
    document_id: int
    version_number: int
    content_json: Any
    created_by: int
    generation_snapshot_id: int | None = None
    created_at: str = ""


class DocumentVersionListResponse(BaseModel):
    items: list[DocumentVersionResponse] = Field(default_factory=list)
