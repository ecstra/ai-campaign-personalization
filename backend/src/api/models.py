from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

# Request/Response models for campaigns
class CampaignCreate(BaseModel):
    name: str
    sender_name: str
    goal: str
    follow_up_delay_minutes: int = 2880
    max_follow_ups: int = 3
    scheduled_start_at: Optional[str] = None


class AttachedDocument(BaseModel):
    id: str
    name: str
    size_bytes: Optional[int] = None
    extension: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CampaignResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    name: str
    sender_name: str
    sender_email: str
    goal: Optional[str]
    follow_up_delay_minutes: int
    max_follow_ups: int
    status: str
    scheduled_start_at: Optional[datetime] = None
    documents: List[AttachedDocument] = []
    created_at: datetime
    updated_at: datetime

# Request/Response models for leads
class LeadCreate(BaseModel):
    email: str
    first_name: str
    last_name: str
    company: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None

class LeadBulkCreate(BaseModel):
    leads: List[LeadCreate]

class LeadResponse(BaseModel):
    id: str
    campaign_id: str
    email: str
    first_name: str
    last_name: str
    company: Optional[str]
    title: Optional[str]
    notes: Optional[str]
    status: str
    has_replied: bool
    current_sequence: int
    created_at: datetime

class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    sender_name: Optional[str] = None
    goal: Optional[str] = None
    follow_up_delay_minutes: Optional[int] = None
    max_follow_ups: Optional[int] = None
    scheduled_start_at: Optional[str] = None


class LeadUpdate(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    has_replied: Optional[bool] = None
    status: Optional[str] = None


class LeadBulkDelete(BaseModel):
    lead_ids: List[str]


class EmailPreviewResponse(BaseModel):
    subject: str
    body: str

class LeadDetailResponse(LeadResponse):
    # Extended lead response with campaign context
    campaign_name: str
    next_email_at: Optional[datetime]
    updated_at: datetime

class EmailActivityResponse(BaseModel):
    id: str
    sequence_number: int
    subject: str
    body: str
    status: str
    sent_at: Optional[datetime]
    created_at: datetime

