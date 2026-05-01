from datetime import timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..db import get_cursor
from ..scheduler.job import CAMPAIGN_EMAIL_RATE_LIMIT, RATE_LIMIT_WINDOW_MINUTES
from .models import CampaignCreate, CampaignUpdate, CampaignResponse, EmailPreviewResponse

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

# Column list used in SELECT/RETURNING clauses
_CAMPAIGN_COLS = """
    id, user_id, name, sender_name, sender_email, goal,
    follow_up_delay_minutes, max_follow_ups, status,
    scheduled_start_at, created_at, updated_at
"""


def _fetch_documents_for_campaigns(cur: Any, campaign_ids: list[str]) -> dict[str, list[dict]]:
    """
    Return a mapping of campaign_id -> [document summary dicts] ordered by
    attachment time. Small second query keeps the campaign SELECT simple
    and avoids JSON aggregation edge cases.
    """
    if not campaign_ids:
        return {}
    cur.execute(
        """
        SELECT cd.campaign_id,
               d.id, d.name, d.size_bytes, d.extension,
               d.created_at, d.updated_at
        FROM campaign_documents cd
        JOIN documents d ON cd.document_id = d.id
        WHERE cd.campaign_id = ANY(%s::uuid[])
        ORDER BY cd.campaign_id, cd.created_at ASC
        """,
        (campaign_ids,),
    )
    out: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        cid = str(row["campaign_id"])
        out.setdefault(cid, []).append({
            "id": str(row["id"]),
            "name": row["name"],
            "size_bytes": row["size_bytes"],
            "extension": row["extension"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })
    return out


def _attach_documents(cur: Any, campaigns: list[dict]) -> list[dict]:
    """Annotate each campaign dict with its `documents` array in place."""
    ids = [str(c["id"]) for c in campaigns]
    by_id = _fetch_documents_for_campaigns(cur, ids)
    for c in campaigns:
        c["documents"] = by_id.get(str(c["id"]), [])
    return campaigns


def _build_product_context(docs: list[dict]) -> Optional[str]:
    """
    Concatenate attached document briefs into a single product-context block
    the LLM will consume during email generation. Returns None when no docs
    are attached, so the prompt can render a clean fallback instead of an
    empty section.
    """
    if not docs:
        return None
    parts: list[str] = []
    for d in docs:
        name = d.get("name") or "Untitled"
        brief = d.get("brief") or ""
        if not brief.strip():
            continue
        parts.append(f"## Document: {name}\n\n{brief.strip()}")
    if not parts:
        return None
    return "\n\n".join(parts)


@router.get("", response_model=List[CampaignResponse])
async def list_campaigns(user: dict[str, Any] = Depends(get_current_user)):
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {_CAMPAIGN_COLS} FROM campaigns WHERE user_id = %s ORDER BY created_at DESC",
            (user["id"],),
        )
        campaigns = [dict(row) for row in cur.fetchall()]
        _attach_documents(cur, campaigns)
    return campaigns


@router.post("", response_model=CampaignResponse)
async def create_campaign(
    campaign: CampaignCreate,
    user: dict[str, Any] = Depends(get_current_user),
):
    # Frontend sends empty string when the date picker is untouched; Postgres
    # cannot coerce "" to TIMESTAMPTZ, so normalise to NULL here.
    scheduled_start_at = campaign.scheduled_start_at if campaign.scheduled_start_at else None

    with get_cursor(commit=True) as cur:
        cur.execute(
            f"""
            INSERT INTO campaigns (user_id, name, sender_name, sender_email, goal,
                                   follow_up_delay_minutes, max_follow_ups, scheduled_start_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_CAMPAIGN_COLS}
            """,
            (
                user["id"],
                campaign.name,
                campaign.sender_name,
                user["email"],
                campaign.goal,
                campaign.follow_up_delay_minutes,
                campaign.max_follow_ups,
                scheduled_start_at,
            ),
        )
        new_campaign = cur.fetchone()
    return new_campaign


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {_CAMPAIGN_COLS} FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Campaign not found")
        campaign = dict(row)
        _attach_documents(cur, [campaign])
    return campaign


@router.delete("/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM campaigns WHERE id = %s AND user_id = %s RETURNING id",
            (campaign_id, user["id"]),
        )
        deleted = cur.fetchone()

    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {"message": "Campaign deleted"}


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: str,
    update: CampaignUpdate,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Update campaign fields. Only allowed when campaign is in draft or paused status."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT status FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        campaign = cur.fetchone()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        if campaign["status"] not in ("draft", "paused"):
            raise HTTPException(
                status_code=400,
                detail="Can only edit campaigns in draft or paused status",
            )

        updates: list[str] = []
        params: list[Any] = []

        if update.name is not None:
            updates.append("name = %s")
            params.append(update.name)
        if update.sender_name is not None:
            updates.append("sender_name = %s")
            params.append(update.sender_name)
        if update.goal is not None:
            updates.append("goal = %s")
            params.append(update.goal)
        if update.follow_up_delay_minutes is not None:
            updates.append("follow_up_delay_minutes = %s")
            params.append(update.follow_up_delay_minutes)
        if update.max_follow_ups is not None:
            updates.append("max_follow_ups = %s")
            params.append(update.max_follow_ups)
        if update.scheduled_start_at is not None:
            updates.append("scheduled_start_at = %s")
            # Allow clearing by passing empty string
            params.append(update.scheduled_start_at if update.scheduled_start_at else None)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        updates.append("updated_at = NOW()")
        params.extend([campaign_id, user["id"]])

        cur.execute(
            f"""
            UPDATE campaigns
            SET {', '.join(updates)}
            WHERE id = %s AND user_id = %s
            RETURNING {_CAMPAIGN_COLS}
            """,
            params,
        )
        updated = cur.fetchone()

    return updated


@router.post("/{campaign_id}/preview", response_model=EmailPreviewResponse)
async def preview_email(
    campaign_id: str,
    lead_id: str = Query(...),
    user: dict[str, Any] = Depends(get_current_user),
):
    """Generate a preview email for a specific lead without sending it."""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {_CAMPAIGN_COLS} FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        campaign = cur.fetchone()

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        cur.execute(
            """
            SELECT id, email, first_name, last_name, company, title, notes, current_sequence
            FROM leads WHERE id = %s AND campaign_id = %s
            """,
            (lead_id, campaign_id),
        )
        lead = cur.fetchone()

        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found in this campaign")

        # Fetch previous emails for context
        cur.execute(
            """
            SELECT sequence_number, subject, body, sent_at
            FROM emails WHERE lead_id = %s AND status = 'sent'
            ORDER BY sequence_number ASC LIMIT 5
            """,
            (lead_id,),
        )
        previous_emails = cur.fetchall()

        # Fetch attached document briefs (may be empty)
        cur.execute(
            """
            SELECT d.name, d.brief
            FROM campaign_documents cd
            JOIN documents d ON cd.document_id = d.id
            WHERE cd.campaign_id = %s
            ORDER BY cd.created_at ASC
            """,
            (campaign_id,),
        )
        attached_docs = cur.fetchall()

    from ..mail.agent import generate_mail

    user_info = {
        "email": lead["email"],
        "first_name": lead["first_name"],
        "last_name": lead["last_name"],
        "company": lead["company"],
        "title": lead["title"],
        "notes": lead["notes"],
    }

    campaign_info = {
        "name": campaign["name"],
        "goal": campaign["goal"],
        "product_context": _build_product_context(attached_docs),
        "sender_name": campaign["sender_name"],
        "sender_email": campaign["sender_email"],
        "current_sequence": lead["current_sequence"] + 1,
        "max_follow_ups": campaign["max_follow_ups"],
    }

    try:
        result = await generate_mail(user_info, campaign_info, list(previous_emails))
        subject = result.subject

        # Mirror scheduler threading: follow-ups go out as "Re: <first subject>".
        # The preview should show exactly what will hit the inbox.
        if previous_emails:
            original_subject = previous_emails[0]["subject"]
            if original_subject and not original_subject.lower().startswith("re:"):
                subject = f"Re: {original_subject}"
            else:
                subject = original_subject

        return EmailPreviewResponse(subject=subject, body=result.body)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate preview: {str(e)}")


@router.patch("/{campaign_id}/status", response_model=CampaignResponse)
async def update_campaign_status(
    campaign_id: str,
    action: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """
    Toggle campaign status:
    - action='start': draft/paused -> active (also queues pending leads)
    - action='stop': active -> paused
    """
    if action not in ["start", "stop"]:
        raise HTTPException(status_code=400, detail="Action must be 'start' or 'stop'")

    with get_cursor(commit=True) as cur:
        cur.execute(
            "SELECT status FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        result = cur.fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Campaign not found")

        current_status = result["status"]

        if action == "start":
            if current_status not in ["draft", "paused"]:
                raise HTTPException(
                    status_code=400,
                    detail="Can only start campaigns in draft or paused status",
                )

            cur.execute(
                "SELECT COUNT(*) as count FROM leads WHERE campaign_id = %s",
                (campaign_id,),
            )
            lead_count = cur.fetchone()["count"]
            if lead_count == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot start a campaign with no leads. Add leads first.",
                )

            new_status = "active"

            # Queue pending leads for immediate processing
            cur.execute(
                """
                UPDATE leads
                SET next_email_at = NOW(), updated_at = NOW()
                WHERE campaign_id = %s
                  AND status = 'pending'
                  AND next_email_at IS NULL
                """,
                (campaign_id,),
            )

        else:  # stop
            if current_status != "active":
                raise HTTPException(
                    status_code=400,
                    detail="Can only stop campaigns in active status",
                )
            new_status = "paused"

        cur.execute(
            f"""
            UPDATE campaigns
            SET status = %s, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING {_CAMPAIGN_COLS}
            """,
            (new_status, campaign_id, user["id"]),
        )

        updated_campaign = cur.fetchone()

    return updated_campaign


@router.post("/{campaign_id}/duplicate", response_model=CampaignResponse)
async def duplicate_campaign(
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Duplicate a campaign with all its leads into a new draft campaign."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"SELECT {_CAMPAIGN_COLS} FROM campaigns WHERE id = %s AND user_id = %s",
            (campaign_id, user["id"]),
        )
        original = cur.fetchone()

        if not original:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Create new campaign with same settings
        cur.execute(
            f"""
            INSERT INTO campaigns (user_id, name, sender_name, sender_email, goal,
                                   follow_up_delay_minutes, max_follow_ups, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'draft')
            RETURNING {_CAMPAIGN_COLS}
            """,
            (
                user["id"],
                f"{original['name']} (Copy)",
                original["sender_name"],
                original["sender_email"],
                original["goal"],
                original["follow_up_delay_minutes"],
                original["max_follow_ups"],
            ),
        )
        new_campaign = cur.fetchone()
        new_id = new_campaign["id"]

        # Copy all leads from original campaign
        cur.execute(
            """
            INSERT INTO leads (campaign_id, email, first_name, last_name, company, title, notes)
            SELECT %s, email, first_name, last_name, company, title, notes
            FROM leads WHERE campaign_id = %s
            """,
            (str(new_id), campaign_id),
        )

    return new_campaign


@router.get("/{campaign_id}/stats")
async def get_campaign_stats(
    campaign_id: str,
    user: dict[str, Any] = Depends(get_current_user),
):
    """
    Get campaign statistics including email counts and rate limit status.

    Uses a single query with CTEs to collapse what was 8 sequential DB
    round-trips into one. On a cross-region DB (200ms RTT) this was the
    difference between ~1.6s and ~200ms per stats load.
    """
    stats_query = """
    WITH
    camp AS (
        SELECT max_follow_ups
        FROM campaigns
        WHERE id = %(cid)s AND user_id = %(uid)s
    ),
    lead_agg AS (
        SELECT
            COUNT(*) AS total_leads,
            COUNT(*) FILTER (WHERE has_replied) AS reply_count,
            AVG(current_sequence) FILTER (WHERE has_replied) AS avg_sequence_at_reply,
            COALESCE(SUM(
                CASE
                    WHEN status IN ('replied', 'failed') THEN current_sequence
                    ELSE (SELECT max_follow_ups FROM camp)
                END
            ), 0) AS emails_target
        FROM leads
        WHERE campaign_id = %(cid)s
    ),
    status_counts AS (
        SELECT jsonb_object_agg(status, cnt) AS leads_by_status
        FROM (
            SELECT status, COUNT(*) AS cnt
            FROM leads
            WHERE campaign_id = %(cid)s
            GROUP BY status
        ) s
    ),
    email_agg AS (
        SELECT
            COUNT(*) FILTER (WHERE e.status IN ('sent', 'failed')) AS emails_sent,
            COUNT(*) FILTER (
                WHERE e.status = 'sent'
                  AND e.sent_at >= NOW() - make_interval(mins => %(win)s)
            ) AS emails_in_window,
            MIN(e.sent_at) FILTER (
                WHERE e.status = 'sent'
                  AND e.sent_at >= NOW() - make_interval(mins => %(win)s)
            ) AS oldest_in_window
        FROM emails e
        JOIN leads l ON e.lead_id = l.id
        WHERE l.campaign_id = %(cid)s
    )
    SELECT
        camp.max_follow_ups,
        la.total_leads,
        la.reply_count,
        la.avg_sequence_at_reply,
        la.emails_target,
        COALESCE(sc.leads_by_status, '{}'::jsonb) AS leads_by_status,
        COALESCE(ea.emails_sent, 0) AS emails_sent,
        COALESCE(ea.emails_in_window, 0) AS emails_in_window,
        ea.oldest_in_window
    FROM camp
    LEFT JOIN lead_agg la ON true
    LEFT JOIN status_counts sc ON true
    LEFT JOIN email_agg ea ON true
    """

    with get_cursor() as cur:
        cur.execute(
            stats_query,
            {
                "cid": campaign_id,
                "uid": user["id"],
                "win": RATE_LIMIT_WINDOW_MINUTES,
            },
        )
        row = cur.fetchone()

    # `camp` CTE returns zero rows if campaign doesn't exist or isn't owned
    # by this user, which makes the whole SELECT return nothing.
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")

    total_leads = row["total_leads"] or 0
    reply_count = row["reply_count"] or 0
    emails_in_window = row["emails_in_window"]
    oldest_in_window = row["oldest_in_window"]

    rate_limit_remaining = max(0, CAMPAIGN_EMAIL_RATE_LIMIT - emails_in_window)
    rate_limit_resets_at = None
    if oldest_in_window and rate_limit_remaining == 0:
        rate_limit_resets_at = oldest_in_window + timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)

    reply_rate = round((reply_count / total_leads) * 100, 1) if total_leads > 0 else 0.0
    avg_sequence_at_reply = (
        float(row["avg_sequence_at_reply"]) if row["avg_sequence_at_reply"] is not None else None
    )

    return {
        "emails_sent": row["emails_sent"],
        "emails_target": int(row["emails_target"] or 0),
        "emails_in_window": emails_in_window,
        "rate_limit": CAMPAIGN_EMAIL_RATE_LIMIT,
        "rate_limit_window_minutes": RATE_LIMIT_WINDOW_MINUTES,
        "rate_limit_remaining": rate_limit_remaining,
        "rate_limit_resets_at": (
            rate_limit_resets_at.isoformat() if rate_limit_resets_at else None
        ),
        "total_leads": total_leads,
        "reply_count": reply_count,
        "reply_rate": reply_rate,
        "leads_by_status": row["leads_by_status"] or {},
        "avg_sequence_at_reply": avg_sequence_at_reply,
    }
