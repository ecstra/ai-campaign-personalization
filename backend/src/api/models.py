from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

MAX_DOCUMENTS_PER_CAMPAIGN = 2

# Request/Response models for campaigns
class CampaignCreate(BaseModel):
    name: str = Field(min_length=1)
    sender_name: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    follow_up_delay_minutes: int = Field(default=2880, ge=1)
    max_follow_ups: int = Field(default=3, ge=0, le=10)
    scheduled_start_at: Optional[datetime] = None

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

class CampaignStatsResponse(BaseModel):
    emails_sent: int
    emails_target: int
    emails_in_window: int
    rate_limit: int
    rate_limit_window_minutes: int
    rate_limit_remaining: int
    rate_limit_resets_at: Optional[str] = None
    total_leads: int
    reply_count: int
    reply_rate: float
    leads_by_status: dict = {}
    avg_sequence_at_reply: Optional[float] = None

# Request/Response models for leads
class LeadCreate(BaseModel):
    email: EmailStr
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    company: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None

class LeadBulkCreate(BaseModel):
    leads: List[LeadCreate] = Field(max_length=1000)

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
    name: Optional[str] = Field(default=None, min_length=1)
    sender_name: Optional[str] = Field(default=None, min_length=1)
    goal: Optional[str] = Field(default=None, min_length=1)
    follow_up_delay_minutes: Optional[int] = Field(default=None, ge=1)
    max_follow_ups: Optional[int] = Field(default=None, ge=0, le=10)
    scheduled_start_at: Optional[datetime] = None

class LeadUpdate(BaseModel):
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(default=None, min_length=1)
    last_name: Optional[str] = Field(default=None, min_length=1)
    company: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    has_replied: Optional[bool] = None
    status: Optional[Literal["pending", "active", "completed", "replied", "failed"]] = None

class LeadBulkDelete(BaseModel):
    lead_ids: List[str] = Field(max_length=1000)

class EmailPreviewResponse(BaseModel):
    subject: str
    body: str

class LeadDetailResponse(LeadResponse):
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
