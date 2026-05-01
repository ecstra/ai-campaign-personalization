from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from psycopg2.extras import execute_values

from ..auth import get_current_user
from ..db import get_cursor
from .models import (
    LeadCreate,
    LeadBulkCreate,
    LeadBulkDelete,
    LeadResponse,
    LeadUpdate,
    LeadDetailResponse,
    EmailActivityResponse,
)

# Router for lead operations scoped to a campaign
router = APIRouter(prefix="/campaigns/{campaign_id}/leads", tags=["leads"])

# Router for lead detail operations (not scoped to campaign in URL)
detail_router = APIRouter(prefix="/leads", tags=["leads"])


def _verify_campaign_ownership(
    cur: Any,
    campaign_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Check that campaign exists and belongs to the authenticated user. Returns campaign row."""
    cur.execute(
        "SELECT id, status FROM campaigns WHERE id = %s AND user_id = %s",
        (campaign_id, user_id),
    )
    campaign = cur.fetchone()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("", response_model=List[LeadResponse])
async def list_leads(
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with get_cursor() as cur:
        _verify_campaign_ownership(cur, campaign_id, user["id"])
        cur.execute(
            """
            SELECT id, campaign_id, email, first_name, last_name, company,
                   title, notes, status, has_replied, current_sequence, created_at
            FROM leads
            WHERE campaign_id = %s
            ORDER BY created_at DESC
            """,
            (campaign_id,),
        )
        leads = cur.fetchall()
    return leads


@router.post("", response_model=LeadResponse)
async def create_lead(
    campaign_id: str,
    lead: LeadCreate,
    user: dict[str, Any] = Depends(get_current_user),
):
    with get_cursor(commit=True) as cur:
        campaign = _verify_campaign_ownership(cur, campaign_id, user["id"])
        if campaign["status"] == "completed":
            raise HTTPException(status_code=400, detail="Cannot add leads to a completed campaign")

        cur.execute(
            "SELECT id FROM leads WHERE campaign_id = %s AND email = %s",
            (campaign_id, lead.email),
        )
        if cur.fetchone():
            raise HTTPException(
                status_code=409,
                detail="Lead with this email already exists in this campaign",
            )

        cur.execute(
            """
            INSERT INTO leads (campaign_id, email, first_name, last_name, company, title, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, campaign_id, email, first_name, last_name, company,
                      title, notes, status, has_replied, current_sequence, created_at
            """,
            (
                campaign_id,
                lead.email,
                lead.first_name,
                lead.last_name,
                lead.company,
                lead.title,
                lead.notes,
            ),
        )
        new_lead = cur.fetchone()
    return new_lead


@router.post("/bulk", response_model=List[LeadResponse])
async def bulk_create_leads(
    campaign_id: str,
    data: LeadBulkCreate,
    user: dict[str, Any] = Depends(get_current_user),
):
    if not data.leads:
        raise HTTPException(status_code=400, detail="No leads provided")

    with get_cursor(commit=True) as cur:
        campaign = _verify_campaign_ownership(cur, campaign_id, user["id"])
        if campaign["status"] == "completed":
            raise HTTPException(status_code=400, detail="Cannot add leads to a completed campaign")

        cur.execute(
            "SELECT email FROM leads WHERE campaign_id = %s",
            (campaign_id,),
        )
        existing_emails = {row["email"] for row in cur.fetchall()}
        seen_emails: set[str] = set()

        rows_to_insert: list[tuple[Any, ...]] = []
        for lead in data.leads:
            if lead.email in existing_emails or lead.email in seen_emails:
                continue
            seen_emails.add(lead.email)
            rows_to_insert.append((
                campaign_id,
                lead.email,
                lead.first_name,
                lead.last_name,
                lead.company,
                lead.title,
                lead.notes,
            ))

        if not rows_to_insert:
            return []

        # Single round-trip multi-row INSERT, returns all created rows
        created_leads = execute_values(
            cur,
            """
            INSERT INTO leads (campaign_id, email, first_name, last_name, company, title, notes)
            VALUES %s
            RETURNING id, campaign_id, email, first_name, last_name, company,
                      title, notes, status, has_replied, current_sequence, created_at
            """,
            rows_to_insert,
            fetch=True,
        )

    return created_leads


@router.delete("/{lead_id}")
async def delete_lead(
    campaign_id: str,
    lead_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with get_cursor(commit=True) as cur:
        _verify_campaign_ownership(cur, campaign_id, user["id"])
        cur.execute(
            "DELETE FROM leads WHERE id = %s AND campaign_id = %s RETURNING id",
            (lead_id, campaign_id),
        )
        deleted = cur.fetchone()

    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"message": "Lead deleted"}


@router.post("/bulk-delete")
async def bulk_delete_leads(
    campaign_id: str,
    data: LeadBulkDelete,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Delete multiple leads from a campaign at once."""
    if not data.lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    with get_cursor(commit=True) as cur:
        _verify_campaign_ownership(cur, campaign_id, user["id"])
        cur.execute(
            "DELETE FROM leads WHERE id = ANY(%s::uuid[]) AND campaign_id = %s",
            (data.lead_ids, campaign_id),
        )
        deleted_count = cur.rowcount

    return {"message": f"{deleted_count} lead(s) deleted", "count": deleted_count}


@detail_router.get("/{lead_id}", response_model=LeadDetailResponse)
async def get_lead_detail(
    lead_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Get detailed lead info including campaign context. Verifies user ownership via campaign."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                l.id, l.campaign_id, l.email, l.first_name, l.last_name,
                l.company, l.title, l.notes, l.status, l.has_replied,
                l.current_sequence, l.next_email_at, l.created_at, l.updated_at,
                c.name as campaign_name
            FROM leads l
            JOIN campaigns c ON l.campaign_id = c.id
            WHERE l.id = %s AND c.user_id = %s
            """,
            (lead_id, user["id"]),
        )
        lead = cur.fetchone()

    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return lead


@detail_router.get("/{lead_id}/activity", response_model=List[EmailActivityResponse])
async def get_lead_activity(
    lead_id: str,
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Get email activity for a specific lead. Verifies campaign ownership."""
    with get_cursor() as cur:
        # Verify ownership through campaign join
        cur.execute(
            """
            SELECT l.id
            FROM leads l
            JOIN campaigns c ON l.campaign_id = c.id
            WHERE l.id = %s AND l.campaign_id = %s AND c.user_id = %s
            """,
            (lead_id, campaign_id, user["id"]),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Lead not found in this campaign")

        cur.execute(
            """
            SELECT id, sequence_number, subject, body, status, sent_at, created_at
            FROM emails
            WHERE lead_id = %s
            ORDER BY created_at DESC
            """,
            (lead_id,),
        )
        emails = cur.fetchall()

    return emails


@detail_router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    update: LeadUpdate,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Update lead information. Verifies ownership via campaign join."""
    updates: list[str] = []
    params: list[Any] = []

    if update.email is not None:
        updates.append("email = %s")
        params.append(update.email)

    if update.first_name is not None:
        updates.append("first_name = %s")
        params.append(update.first_name)

    if update.last_name is not None:
        updates.append("last_name = %s")
        params.append(update.last_name)

    if update.company is not None:
        updates.append("company = %s")
        params.append(update.company)

    if update.title is not None:
        updates.append("title = %s")
        params.append(update.title)

    if update.notes is not None:
        updates.append("notes = %s")
        params.append(update.notes)

    if update.has_replied is not None:
        updates.append("has_replied = %s")
        params.append(str(update.has_replied))

    if update.status is not None:
        updates.append("status = %s")
        params.append(update.status)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    params.extend([lead_id, user["id"]])

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            UPDATE leads
            SET {', '.join(updates)}
            WHERE id = %s
              AND campaign_id IN (SELECT id FROM campaigns WHERE user_id = %s)
            RETURNING id, campaign_id, email, first_name, last_name, company,
                      title, notes, status, has_replied, current_sequence, created_at
            """,
            params,
        )
        updated_lead = cur.fetchone()

    if not updated_lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return updated_lead
