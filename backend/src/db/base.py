from enum import Enum
import logging

from .engine import DatabaseEngine

logger = logging.getLogger(__name__)

class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"

class LeadStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    ACTIVE = "active"
    REPLIED = "replied"
    COMPLETED = "completed"
    FAILED = "failed"

class EmailStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RECEIVED = "received"

class DatabaseInitializer:

    USERS_TABLE = """
    CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        google_id TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        picture_url TEXT,
        access_token_encrypted TEXT,
        refresh_token_encrypted TEXT,
        token_expiry TIMESTAMPTZ,
        scopes TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """

    CAMPAIGNS_TABLE = """
    CREATE TABLE IF NOT EXISTS campaigns (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        sender_name TEXT NOT NULL,
        sender_email TEXT NOT NULL,
        goal TEXT NOT NULL,
        follow_up_delay_minutes INTEGER DEFAULT 2880,
        max_follow_ups INTEGER DEFAULT 3,
        status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed')),
        scheduled_start_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """

    LEADS_TABLE = """
    CREATE TABLE IF NOT EXISTS leads (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
        email TEXT NOT NULL,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        company TEXT,
        title TEXT,
        notes TEXT,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'processing', 'completed', 'replied', 'failed')),
        has_replied BOOLEAN DEFAULT FALSE,
        current_sequence INTEGER DEFAULT 0,
        next_email_at TIMESTAMPTZ,
        locked_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE(campaign_id, email)
    );
    """

    EMAILS_TABLE = """
    CREATE TABLE IF NOT EXISTS emails (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
        sequence_number INTEGER NOT NULL DEFAULT 0,
        subject TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed', 'received')),
        message_id TEXT,
        in_reply_to TEXT,
        attempts INTEGER DEFAULT 0,
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """

    DOCUMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        brief TEXT NOT NULL,
        size_bytes INTEGER,
        extension TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """

    CAMPAIGN_DOCUMENTS_TABLE = """
    CREATE TABLE IF NOT EXISTS campaign_documents (
        campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
        document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (campaign_id, document_id)
    );
    """

    INDEXES = """
    CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_campaigns_user_id ON campaigns(user_id);
    CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
    CREATE INDEX IF NOT EXISTS idx_leads_campaign_id ON leads(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
    CREATE INDEX IF NOT EXISTS idx_leads_next_email_at ON leads(next_email_at);
    CREATE INDEX IF NOT EXISTS idx_leads_locked_at ON leads(locked_at);
    CREATE INDEX IF NOT EXISTS idx_emails_lead_id ON emails(lead_id);
    CREATE INDEX IF NOT EXISTS idx_emails_lead_seq ON emails(lead_id, sequence_number);
    CREATE INDEX IF NOT EXISTS idx_emails_status ON emails(status);
    CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
    CREATE INDEX IF NOT EXISTS idx_campaign_documents_document_id ON campaign_documents(document_id);
    """

    @staticmethod
    def init_db() -> bool:
        try:
            with DatabaseEngine.get_cursor(commit=True) as cur:
                cur.execute(DatabaseInitializer.USERS_TABLE)
                cur.execute(DatabaseInitializer.CAMPAIGNS_TABLE)
                cur.execute(DatabaseInitializer.LEADS_TABLE)
                cur.execute(DatabaseInitializer.EMAILS_TABLE)
                cur.execute(DatabaseInitializer.DOCUMENTS_TABLE)
                cur.execute(DatabaseInitializer.CAMPAIGN_DOCUMENTS_TABLE)
                cur.execute(DatabaseInitializer.INDEXES)
            return True
        except Exception:
            logger.exception("Database initialization failed")
            return False
