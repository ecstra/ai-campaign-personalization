import os
import uuid
from typing import Any, List, Optional, Dict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from pydantic import BaseModel

from ..auth import get_current_user
from ..db import DatabaseEngine
from core.utilities.document import (
    DocumentParserUtility,
    DocumentParseError,
    DocumentSummarizerUtility,
    BriefSummarizationError,
)

MAX_DOCUMENTS_PER_CAMPAIGN = 2
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md"}
MAX_FILE_BYTES = 30 * 1024 * 1024

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

class UploadTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int
    filename: Optional[str] = None
    error: Optional[str] = None
    document: Optional[DocumentSummary] = None

# In-memory task tracking for progress
upload_tasks: Dict[str, dict] = {}

async def process_document_task(task_id: str, user_id: str, filename: str, ext: str, body: bytes):
    upload_tasks[task_id]["status"] = "parsing"
    upload_tasks[task_id]["progress"] = 60
    upload_tasks[task_id]["filename"] = filename
    # Store user_id so we can filter tasks later
    upload_tasks[task_id]["user_id"] = user_id
    
    try:
        markdown = await DocumentParserUtility.parse_document(body, filename)
    except DocumentParseError as e:
        upload_tasks[task_id]["status"] = "error"
        upload_tasks[task_id]["error"] = str(e)
        return
    except Exception:
        upload_tasks[task_id]["status"] = "error"
        upload_tasks[task_id]["error"] = "Document parsing service is unavailable."
        return

    upload_tasks[task_id]["status"] = "summarizing"
    upload_tasks[task_id]["progress"] = 80

    try:
        brief = await DocumentSummarizerUtility.summarize_to_brief(markdown)
    except BriefSummarizationError as e:
        upload_tasks[task_id]["status"] = "error"
        upload_tasks[task_id]["error"] = str(e)
        return
    except Exception:
        upload_tasks[task_id]["status"] = "error"
        upload_tasks[task_id]["error"] = "Summarization service is unavailable."
        return

    upload_tasks[task_id]["status"] = "saving"
    upload_tasks[task_id]["progress"] = 95

    try:
        with DatabaseEngine.get_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO documents (user_id, name, brief, size_bytes, extension)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, name) DO UPDATE SET
                    brief = EXCLUDED.brief,
                    size_bytes = EXCLUDED.size_bytes,
                    extension = EXCLUDED.extension,
                    updated_at = NOW()
                RETURNING id, name, size_bytes, extension, brief, created_at, updated_at
                """,
                (user_id, filename, brief, len(body), ext),
            )
            row = cur.fetchone()
            
        upload_tasks[task_id]["status"] = "success"
        upload_tasks[task_id]["progress"] = 100
        upload_tasks[task_id]["document"] = DocumentDetail(
            id=str(row["id"]),
            name=row["name"],
            size_bytes=row["size_bytes"],
            extension=row["extension"],
            brief=row["brief"],
            word_count=len(row["brief"].split()),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
    except Exception:
        upload_tasks[task_id]["status"] = "error"
        upload_tasks[task_id]["error"] = "Database error saving document."

@library_router.post("", response_model=UploadTaskStatus)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
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

    task_id = str(uuid.uuid4())
    upload_tasks[task_id] = {
        "task_id": task_id,
        "status": "processing",
        "progress": 50,
        "filename": file.filename,
        "error": None,
        "document": None
    }
    
    background_tasks.add_task(process_document_task, task_id, user["id"], file.filename, ext, body)
    
    return UploadTaskStatus(**upload_tasks[task_id])

@library_router.get("/status/{task_id}", response_model=UploadTaskStatus)
async def get_upload_status(
    task_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    if task_id not in upload_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return UploadTaskStatus(**upload_tasks[task_id])

@library_router.get("/tasks", response_model=List[UploadTaskStatus])
async def list_active_tasks(
    user: dict[str, Any] = Depends(get_current_user),
):
    """Returns all active upload/processing tasks for the current user."""
    user_id = user["id"]
    return [
        UploadTaskStatus(**task)
        for task in upload_tasks.values()
        if task.get("user_id") == user_id and task["status"] not in ("success", "error")
    ]

@library_router.get("", response_model=List[DocumentSummary])
async def list_documents(
    user: dict[str, Any] = Depends(get_current_user),
):
    with DatabaseEngine.get_cursor() as cur:
        cur.execute(
            "SELECT * FROM documents WHERE user_id = %s ORDER BY created_at DESC",
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
    user: dict[str, Any] = Depends(get_current_user),
):
    with DatabaseEngine.get_cursor() as cur:
        cur.execute(
            "SELECT * FROM documents WHERE id = %s AND user_id = %s",
            (document_id, user["id"]),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

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

@library_router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with DatabaseEngine.get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM documents WHERE id = %s AND user_id = %s RETURNING id",
            (document_id, user["id"]),
        )
        deleted = cur.fetchone()

    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"status": "success"}

@attach_router.post("")
async def attach_documents(
    campaign_id: str,
    update: CampaignDocumentsUpdate,
    user: dict[str, Any] = Depends(get_current_user),
):
    # Verify campaign ownership
    with DatabaseEngine.get_cursor() as cur:
        cur.execute(
            "SELECT id FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Campaign not found")

    # Verify document ownership and count
    if len(update.document_ids) > MAX_DOCUMENTS_PER_CAMPAIGN:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_DOCUMENTS_PER_CAMPAIGN} documents per campaign",
        )

    with DatabaseEngine.get_cursor(commit=True) as cur:
        # Remove old attachments
        cur.execute(
            "DELETE FROM campaign_documents WHERE campaign_id = %s",
            (campaign_id,),
        )
        # Add new ones
        for doc_id in update.document_ids:
            cur.execute(
                "INSERT INTO campaign_documents (campaign_id, document_id) VALUES (%s, %s)",
                (campaign_id, doc_id),
            )

    return {"status": "success"}
