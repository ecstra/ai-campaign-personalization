# Outreach

> Multi-tenant SaaS for automated, AI-personalised cold email outreach with
> intelligent follow-ups, Gmail send/receive integration, and document-grounded
> personalisation.

Live: **[lvoutreach.duckdns.org](https://lvoutreach.duckdns.org)**

![Showcase](assets/show.gif)

## What it does

Users sign in with Google, connect their Gmail inbox, upload product
documents to a shared library, and launch personalised cold-email campaigns.
The backend generates each email using an LLM grounded in the product brief
and per-lead context, sends through the user's own Gmail (via XOAUTH2),
threads follow-ups into the original conversation, and detects replies via
IMAP polling so dead leads stop receiving mail.

It's built for small teams running their own cold outreach — not a
delivery-as-a-service layer. Every email goes out through the user's own
Gmail account, so deliverability and sender reputation stay in their hands.

## Features

### Campaigns
- Create, edit (draft/paused only), duplicate, and delete campaigns
- Scheduled start: set a datetime, the scheduler auto-activates when time
  arrives
- Per-campaign rate limiting (50 emails / hour by default) and daily Gmail
  send caps (450 / day)
- Analytics per campaign: reply rate, average emails before reply,
  lead-quality score, status breakdowns

### Leads
- Manual add, bulk CSV import with client-side validation + preview
- Bulk delete with checkboxes and a floating action bar
- Edit all lead fields; edit is hidden on terminal statuses (replied /
  completed / failed)
- Email activity timeline per lead with smooth accordion expansion

### Email generation
- LLM-powered personalisation using DeepSeek v3.2 (or any OpenAI-compatible
  provider via `moonlight-ai` abstraction)
- Post-generation **critic pass**: a second LLM call scores the draft
  against a banned-pattern checklist (inference-from-fact openers, filler
  phrases, em-dashes, capability menu-dumps) and regenerates with feedback
  if violations are found
- Email preview endpoint: generate a draft for any lead without sending
- Threading: follow-ups go out with `Re: {original subject}` so Gmail
  bundles them into the same conversation

### Documents library
- Upload PDF, DOCX, PPTX, TXT, or MD
- LlamaParse (agentic tier) extracts to markdown
- Gemini / DeepSeek / your-chosen-LLM distils to a 300-500 word product
  brief
- Brief is injected into every email generation for campaigns that attach
  the document
- Account-wide library: upload once, attach to multiple campaigns (cap: 2
  documents per campaign to bound LLM input)

### Reply detection
- Gmail IMAP XOAUTH2 polling every 60 seconds
- Targeted pre-send check per user immediately before each send cycle to
  avoid race conditions
- Primary match by `In-Reply-To` / `References` headers; sender-email
  fallback with a date-guard to reject stale cross-campaign replies
- Reply date stored from the message's actual `Date` header, not poll
  timestamp

### Multi-tenancy
- Google OAuth2 with Gmail scope (`https://mail.google.com/`)
- OAuth tokens encrypted at rest (Fernet / `TOKEN_ENCRYPTION_KEY`)
- JWT sessions (HS256, 7-day expiry)
- Every query filtered by `user_id`; cross-tenant access blocked at the
  query level and verified by 20+ ownership tests

## Tech stack

| Layer            | Technology                                      |
| ---------------- | ----------------------------------------------- |
| Backend          | FastAPI (Python), APScheduler                   |
| Database         | PostgreSQL via Supabase (pooler, port 6543)     |
| LLM              | DeepSeek v3.2 via `moonlight-ai` (swappable)    |
| Document extract | LlamaParse (agentic tier)                       |
| Email send       | Gmail SMTP XOAUTH2                              |
| Email receive    | Gmail IMAP XOAUTH2 (60s poll)                   |
| Auth             | Google OAuth2 + JWT                             |
| Frontend         | React 19, Vite, TypeScript, Tailwind            |
| UI components    | shadcn/ui (Mira preset, Inter Variable)         |
| Deployment       | AWS EC2 (eu-north-1), Caddy, systemd            |
| CI/CD            | GitHub Actions (push to main → SSH deploy)      |

## Quick start (local)

### Prerequisites
- Python 3.12
- Node.js 20+
- PostgreSQL 15+ (local or Supabase project)
- Google Cloud project with OAuth consent screen configured

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Fill in DATABASE_URI, Google OAuth creds, LLM provider key, etc.

uvicorn app:app --reload
```

Scheduler and DB migrations run automatically on startup via the FastAPI
lifespan hook.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` to `localhost:8000`.

### Tests

```bash
cd backend
TEST_DATABASE_URI=postgresql:///campaign_test \
LLAMA_CLOUD_API_KEY=llx-test \
pytest tests/ -v
```

Current suite: **132 tests**, ~20s full run. No external service calls —
Google OAuth, Gmail, LlamaParse, and the LLM are all mocked. See
`backend/conftest.py` for the test harness.

## Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in:

```env
# Database (Supabase pooler — use port 6543, not 5432, on EC2)
DATABASE_URI=postgresql://postgres.PROJREF:PASSWORD@aws-X-eu-north-1.pooler.supabase.com:6543/postgres

# LLM (provider aliases: deepseek, groq, openrouter, google, openai)
LLM_SOURCE=deepseek
LLM_API_KEY=sk-your-deepseek-key
LLM_MODEL=deepseek-chat

# LlamaParse (for document upload extraction)
LLAMA_CLOUD_API_KEY=llx-your-llamaparse-key

# Email-generation quality gate (default on)
CRITIQUE_ENABLED=true

# Google OAuth
GOOGLE_CLIENT_ID=xxxxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=https://yourhost/auth/callback

# Security
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
TOKEN_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Gmail limits
GMAIL_DAILY_SEND_LIMIT=450
GMAIL_INTER_SEND_DELAY_MS=200
REPLY_CHECK_INTERVAL_SECONDS=60

# CORS
CORS_ORIGINS=https://yourhost
```

## Architecture

![Architecture](assets/arch.png)

The backend is a single FastAPI process running on EC2 t3.micro. The
scheduler (APScheduler, in-process) runs three jobs every 60 seconds:

1. **`process_leads_job`** — picks eligible leads, generates emails
   concurrently, batch-records sends
2. **`check_replies_job`** — polls each active user's Gmail inbox over
   IMAP, matches new mail to leads, marks as replied
3. **`check_scheduled_campaigns`** — auto-activates any draft campaigns
   whose `scheduled_start_at` is in the past

All database access goes through a connection pool; Supabase pooler at
port 6543 is required on IPv4-only hosts like t3.micro.

## API surface

All routes are mounted under `/api` behind Caddy's reverse proxy.

### Auth
| Method | Endpoint                    | Notes                       |
| ------ | --------------------------- | --------------------------- |
| GET    | `/auth/google/login`        | Returns Google auth URL     |
| POST   | `/auth/google/callback`     | Exchanges code for JWT      |
| GET    | `/auth/me`                  | Current user                |
| POST   | `/auth/logout`              | Clears server-side session  |

### Campaigns
| Method | Endpoint                             | Notes                         |
| ------ | ------------------------------------ | ----------------------------- |
| GET    | `/campaigns`                         | List (user-scoped)            |
| POST   | `/campaigns`                         | Create                        |
| GET    | `/campaigns/{id}`                    | Includes `documents[]` array  |
| PATCH  | `/campaigns/{id}`                    | Edit (draft/paused only)      |
| DELETE | `/campaigns/{id}`                    | Cascade delete                |
| PATCH  | `/campaigns/{id}/status`             | `?action=start` / `stop`      |
| POST   | `/campaigns/{id}/duplicate`          | Copies settings + all leads   |
| POST   | `/campaigns/{id}/preview`            | Generate email for `?lead_id` |
| GET    | `/campaigns/{id}/stats`              | Analytics (single-query CTE)  |

### Leads
| Method | Endpoint                                     | Notes                      |
| ------ | -------------------------------------------- | -------------------------- |
| GET    | `/campaigns/{id}/leads`                      | List                       |
| POST   | `/campaigns/{id}/leads`                      | Add single                 |
| POST   | `/campaigns/{id}/leads/bulk`                 | Bulk insert (execute_values) |
| POST   | `/campaigns/{id}/leads/bulk-delete`          | Batch delete by id list    |
| DELETE | `/campaigns/{id}/leads/{lead_id}`            | Single delete              |
| GET    | `/leads/{id}`                                | Detail                     |
| PATCH  | `/leads/{id}`                                | Edit                       |
| GET    | `/leads/{id}/activity`                       | Email timeline             |

### Documents
| Method | Endpoint                                | Notes                               |
| ------ | --------------------------------------- | ----------------------------------- |
| POST   | `/documents`                            | Upload + parse + summarise          |
| GET    | `/documents`                            | Library list (user-scoped)          |
| GET    | `/documents/{id}`                       | Single document + brief             |
| DELETE | `/documents/{id}`                       | Cascades to campaign_documents      |
| PUT    | `/campaigns/{id}/documents`             | Replace attachments (cap 2)         |

### Misc
| Method | Endpoint                    | Notes                       |
| ------ | --------------------------- | --------------------------- |
| GET    | `/health`                   | DB connection check         |

## Project structure

```
├── backend/
│   ├── app.py                    # FastAPI entry + lifespan (scheduler, DB)
│   ├── requirements.txt
│   ├── conftest.py               # Pytest fixtures (per-request-header auth)
│   ├── tests/                    # 132 tests, local Postgres
│   └── src/
│       ├── api/
│       │   ├── auth/             # OAuth + JWT + token encryption
│       │   ├── campaigns.py
│       │   ├── leads.py
│       │   ├── documents.py      # Library + campaign attachments
│       │   └── models.py         # Pydantic schemas
│       ├── db/
│       │   ├── base.py           # Schema + migrations (9 applied)
│       │   └── engine.py         # psycopg2 pool
│       ├── documents/
│       │   ├── parser.py         # LlamaParse wrapper
│       │   └── summarizer.py     # Brief generation via LLM
│       ├── mail/
│       │   ├── agent.py          # Email generation (+ critic loop)
│       │   ├── critic.py         # Second-pass quality gate
│       │   ├── gmail.py          # SMTP XOAUTH2 send
│       │   ├── imap.py           # IMAP XOAUTH2 reply polling
│       │   └── replies.py        # Reply extraction + persistence
│       └── scheduler/
│           └── job.py            # Three APScheduler jobs
├── frontend/
│   └── src/
│       ├── pages/                # Campaigns, CampaignDetail, CampaignCreate,
│       │                          # LeadDetail, Documents, DocumentDetail
│       ├── components/
│       │   ├── ui/               # shadcn/ui (Mira preset)
│       │   ├── AppLayout.tsx     # Persistent sidebar
│       │   ├── AttachedDocumentsCard.tsx
│       │   ├── ImportCSVModal.tsx    # papaparse-backed validation
│       │   └── PreviewEmailModal.tsx
│       ├── contexts/             # Auth, Breadcrumb
│       └── lib/
│           ├── api.ts            # JWT-authenticated fetch wrapper
│           ├── status.ts         # Shared status → Badge config
│           └── errors.ts         # parseApiError
├── deploy/
│   ├── Caddyfile                 # Reverse proxy + static frontend
│   ├── outreach-api.service      # systemd unit
│   └── setup.sh                  # EC2 one-time setup
└── .github/workflows/
    └── deploy.yml                # CI/CD: push to main → SSH deploy
```

## Email-generation pipeline

Every email goes through a two-call generate-and-critique loop:

1. **Generate** (`_generate_draft`): the ROLE prompt enforces tone, banned
   patterns (inference-from-fact openers, filler phrases, em-dashes,
   menu-dumps of capabilities), proof-point selectivity, and format. The
   generator reads campaign goal, recipient info, attached product-brief
   concatenation, and previous emails in sequence.
2. **Critique** (`critic.py`): a second LLM call scans the draft against a
   strict checklist and returns `{passed, violations[]}`.
3. **Regenerate** (optional): if the critic fails, the loop retries once
   with the violation list injected as additional guidance. Returns
   whatever the second attempt produces.

Cost: 2 LLM calls per clean email, 3 on failure. Latency: +3-5s per
email. Disable via `CRITIQUE_ENABLED=false` if the cost/latency tradeoff
changes.

## Reply-detection design

The IMAP poller needs to match incoming mail to the right lead across
campaigns that may reuse the same email address over time. Three match
strategies in order:

1. **`In-Reply-To` header** matches one of our sent `message_id` values
2. **`References` chain** — any ref matches a sent message_id
3. **Sender-email fallback** — only accepted if the reply's `Date` header
   is after the earliest email we sent to that lead. This date-guard
   rejects stale replies from previous campaigns where the same address
   was a lead.

Stored `sent_at` for received messages uses the email's actual `Date`
header (when parsable) rather than the polling timestamp, so the activity
timeline reflects when the lead actually sent, not when we detected.

## Deployment

The live system runs on a single AWS EC2 t3.micro in `eu-north-1`:

- `/home/ubuntu/app` holds the repo checkout
- `outreach-api.service` (systemd) runs uvicorn on `127.0.0.1:8000`
- Caddy reverse-proxies `/api/*` to the backend and serves the built
  frontend from `frontend/dist/` on everything else
- SSL via Caddy's auto Let's Encrypt integration
- Database is Supabase (eu-north-1 cluster), same region as EC2 for
  ~5 ms DB round-trip latency
- Pushing to `main` triggers `.github/workflows/deploy.yml` which SSHes
  into EC2, pulls, rebuilds the frontend, reinstalls Python deps, and
  restarts the service

See `deploy/setup.sh` for the one-time server provisioning script.

## Design notes

- **Rate limits enforced in two places** (DB query-time filter + pre-send
  targeted IMAP check) to handle overlapping scheduler runs safely on
  multi-worker deployments
- **Deterministic idempotency** on (lead_id, sequence_number) before each
  send — crashes between SMTP delivery and DB write don't cause duplicates
- **Bulk lead import uses `execute_values`** — 500-lead CSV imports finish
  in one DB round-trip instead of N
- **Campaign stats use a single CTE query** instead of the 8 sequential
  queries of the original design — critical when DB and app were in
  different regions
- **Pydantic structured output** via `moonlight-ai` for the LLM calls —
  the response is parsed into typed models, not free-form text
- **OAuth tokens encrypted at rest with Fernet** — a stolen DB snapshot
  does not give an attacker access to any user's Gmail
- **Client-side CSV parsing with papaparse** handles quoted newlines and
  UTF-8 correctly — common failure modes on exports from Excel and
  LinkedIn Sales Navigator
- **Document uploads don't hold request connections open** during parse —
  the frontend uses `toast.promise()` on a fire-and-forget fetch so users
  can navigate away during the ~30-60s LlamaParse + summarisation round
  trip

## License

Private / internal project for Lakshmi Vacuum Technologies. Not currently
licensed for public use.
