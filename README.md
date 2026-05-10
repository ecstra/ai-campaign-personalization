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

## Quick Start

### Backend

1. Navigate to the `backend` directory.
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables by copying `.env.example` to `.env` and filling in the values.
5. Run the backend:
   ```bash
   fastapi dev app.py
   ```

### Frontend

1. Navigate to the `frontend` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
