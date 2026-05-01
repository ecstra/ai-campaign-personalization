from enum import Enum

from .engine import get_cursor
from ..logger import logger


class Status:
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
        SENT = "sent"
        FAILED = "failed"
        RECEIVED = "received"


# ── Table Schemas ──────────────────────────────────────────────────────────

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
    status TEXT DEFAULT 'draft',
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
    status TEXT DEFAULT 'pending',
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
    status TEXT DEFAULT 'pending',
    message_id TEXT,
    in_reply_to TEXT,
    gmail_thread_id TEXT,
    attempts INTEGER DEFAULT 0,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_campaigns_user_id ON campaigns(user_id);
CREATE INDEX IF NOT EXISTS idx_leads_campaign_id ON leads(campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_next_email_at ON leads(next_email_at);
CREATE INDEX IF NOT EXISTS idx_leads_locked_at ON leads(locked_at);
CREATE INDEX IF NOT EXISTS idx_emails_lead_id ON emails(lead_id);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
CREATE INDEX IF NOT EXISTS idx_emails_gmail_thread_id ON emails(gmail_thread_id);
"""

# ── Migrations for existing databases ──────────────────────────────────────

SCHEMA_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    # (version, description, SQL)
    (1, "Add users table", USERS_TABLE),
    (2, "Add user_id to campaigns", """
        ALTER TABLE campaigns
        ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;
    """),
    (3, "Add email threading columns", """
        ALTER TABLE emails ADD COLUMN IF NOT EXISTS message_id TEXT;
        ALTER TABLE emails ADD COLUMN IF NOT EXISTS in_reply_to TEXT;
        ALTER TABLE emails ADD COLUMN IF NOT EXISTS gmail_thread_id TEXT;
    """),
    (4, "Add new indexes", """
        CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_campaigns_user_id ON campaigns(user_id);
        CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);
        CREATE INDEX IF NOT EXISTS idx_emails_gmail_thread_id ON emails(gmail_thread_id);
    """),
    (5, "Add scheduled_start_at to campaigns", """
        ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS scheduled_start_at TIMESTAMPTZ;
    """),
    (6, "Add product document columns to campaigns", """
        ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_context TEXT;
        ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS product_document_name TEXT;
    """),
    (7, "Create account-wide documents library", """
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
        CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);

        CREATE TABLE IF NOT EXISTS campaign_documents (
            campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (campaign_id, document_id)
        );
        CREATE INDEX IF NOT EXISTS idx_campaign_documents_document_id ON campaign_documents(document_id);
    """),
    (8, "Move existing campaign product_context into documents library", """
        DO $$
        DECLARE
            c RECORD;
            new_doc_id UUID;
        BEGIN
            FOR c IN
                SELECT id, user_id, product_context, product_document_name
                FROM campaigns
                WHERE product_context IS NOT NULL
                  AND user_id IS NOT NULL
            LOOP
                INSERT INTO documents (user_id, name, brief)
                VALUES (
                    c.user_id,
                    COALESCE(c.product_document_name, 'Untitled'),
                    c.product_context
                )
                RETURNING id INTO new_doc_id;

                INSERT INTO campaign_documents (campaign_id, document_id)
                VALUES (c.id, new_doc_id);
            END LOOP;
        END $$;
    """),
    (9, "Drop per-campaign product columns (replaced by documents library)", """
        ALTER TABLE campaigns DROP COLUMN IF EXISTS product_context;
        ALTER TABLE campaigns DROP COLUMN IF EXISTS product_document_name;
    """),
]


def _run_migrations() -> None:
    """Run any unapplied schema migrations."""
    with get_cursor(commit=True) as cur:
        cur.execute(SCHEMA_MIGRATIONS_TABLE)
        cur.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = {row["version"] for row in cur.fetchall()}

        for version, description, sql in MIGRATIONS:
            if version in applied:
                continue
            logger.info(f"Applying migration {version}: {description}")
            cur.execute(sql)
            cur.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (version,),
            )
            logger.info(f"Migration {version} applied successfully")


def init_db() -> bool:
    """
    Initialize database tables and run pending migrations.
    Creates: users, campaigns, leads, emails tables with indexes.
    """
    try:
        with get_cursor(commit=True) as cur:
            cur.execute(USERS_TABLE)
            cur.execute(CAMPAIGNS_TABLE)
            cur.execute(LEADS_TABLE)
            cur.execute(EMAILS_TABLE)
            cur.execute(INDEXES)

        _run_migrations()

        logger.info("Database tables initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False