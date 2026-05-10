import os
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..auth import AuthUtility
from ..db import DatabaseEngine
from ..documents import (
    DocumentParserUtility,
    DocumentParseError,
    DocumentSummarizerUtility,
    BriefSummarizationError,
)

MAX_DOCUMENTS_PER_CAMPAIGN = 2

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}
MAX_FILE_BYTES = 10 * 1024 * 1024


library_router = APIRouter(prefix="/documents", tags=["documents"])
attach_router = APIRouter(prefix="/campaigns/{campaign_id}/documents", tags=["documents"])


class DocumentSummary(BaseModel):
    id: str
    name: str
    size_bytes: Optional[int] = None
    extension: Optional[str] = None
    created_at: Any
    updated_at: Any


class DocumentDetail(DocumentSummary):
    brief: str
    word_count: int


class CampaignDocumentsUpdate(BaseModel):
    document_ids: List[str]


@library_router.post("", response_model=DocumentDetail)
async def upload_document(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(AuthUtility.get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    body = await file.read()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="File is empty")
    if len(body) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
        )

    try:
        markdown = await DocumentParserUtility.parse_document(body, file.filename)
    except DocumentParseError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Document parsing service is unavailable.")

    try:
        brief = await DocumentSummarizerUtility.summarize_to_brief(markdown)
    except BriefSummarizationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=502, detail="Summarization service is unavailable.")

    with DatabaseEngine.get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO documents (user_id, name, brief, size_bytes, extension)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, name, size_bytes, extension, brief, created_at, updated_at
            """,
            (user["id"], file.filename, brief, len(body), ext),
        )
        row = cur.fetchone()

    return DocumentDetail(
        id=str(row["id"]),
        name=row["name"],
        size_bytes=row["size_bytes"],
        extension=row["extension"],
        brief=row["brief"],
        word_count=len(row["brief"].split()),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@library_router.get("", response_model=List[DocumentSummary])
async def list_documents(
    user: dict[str, Any] = Depends(AuthUtility.get_current_user),
):
    with DatabaseEngine.get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, size_bytes, extension, created_at, updated_at
            FROM documents
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user["id"],),
        )
        rows = cur.fetchall()
    return [
        DocumentSummary(
            id=str(r["id"]),
            name=r["name"],
            size_bytes=r["size_bytes"],
            extension=r["extension"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


@library_router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: str,
    user: dict[str, Any] = Depends(AuthUtility.get_current_user),
):
    with DatabaseEngine.get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, brief, size_bytes, extension, created_at, updated_at
            FROM documents
            WHERE id = %s AND user_id = %s
            """,
            (document_id, user["id"]),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentDetail(
        id=str(row["id"]),
        name=row["name"],
        brief=row["brief"],
        size_bytes=row["size_bytes"],
        extension=row["extension"],
        word_count=len(row["brief"].split()),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@library_router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: dict[str, Any] = Depends(AuthUtility.get_current_user),
):
    with DatabaseEngine.get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM documents WHERE id = %s AND user_id = %s RETURNING id",
            (document_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}


@attach_router.put("", response_model=List[DocumentSummary])
async def set_campaign_documents(
    campaign_id: str,
    payload: CampaignDocumentsUpdate,
    user: dict[str, Any] = Depends(AuthUtility.get_current_user),
):
    if len(payload.document_ids) > MAX_DOCUMENTS_PER_CAMPAIGN:
        raise HTTPException(
            status_code=400,
            detail=f"A campaign can have at most {MAX_DOCUMENTS_PER_CAMPAIGN} documents attached.",
        )

    doc_ids = list(dict.fromkeys(payload.document_ids))

    with DatabaseEngine.get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT status FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        camp = cur.fetchone()
        if not camp:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if camp["status"] not in ("draft", "paused"):
            raise HTTPException(
                status_code=400,
                detail="Attached documents can only be changed on draft or paused campaigns.",
            )

        if doc_ids:
            cur.execute(
                "SELECT id FROM documents WHERE id = ANY(%s::uuid[]) AND user_id = %s",
                (doc_ids, user["id"]),
            )
            found = {str(r["id"]) for r in cur.fetchall()}
            missing = [d for d in doc_ids if d not in found]
            if missing:
                raise HTTPException(
                    status_code=404,
                    detail=f"Documents not found in your library: {', '.join(missing)}",
                )

        cur.execute(
            "DELETE FROM campaign_documents WHERE campaign_id = %s",
            (campaign_id,),
        )
        for doc_id in doc_ids:
            cur.execute(
                "INSERT INTO campaign_documents (campaign_id, document_id) VALUES (%s, %s)",
                (campaign_id, doc_id),
            )

        cur.execute(
            """
            SELECT d.id, d.name, d.size_bytes, d.extension, d.created_at, d.updated_at
            FROM campaign_documents cd
            JOIN documents d ON cd.document_id = d.id
            WHERE cd.campaign_id = %s
            ORDER BY cd.created_at ASC
            """,
            (campaign_id,),
        )
        rows = cur.fetchall()

    return [
        DocumentSummary(
            id=str(r["id"]),
            name=r["name"],
            size_bytes=r["size_bytes"],
            extension=r["extension"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
