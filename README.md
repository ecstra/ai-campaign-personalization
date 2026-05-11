# Outreach

> Multi-tenant SaaS for automated, AI-personalised cold email outreach with
> intelligent follow-ups, Resend email delivery, and document-grounded
> personalisation.

![Showcase](assets/show.gif)

## What it does

Users sign in with Google, upload product documents to a shared library, and
launch personalised cold-email campaigns. The backend generates each email
using an LLM grounded in the product brief and per-lead context, sends through
Resend, threads follow-ups into the original conversation, and detects replies
via Resend inbound webhooks (real-time, no polling).

## Features

### Campaigns
- Create, edit (draft/paused only), duplicate, and delete campaigns
- Scheduled start: set a datetime, the scheduler auto-activates when time arrives
- Per-campaign rate limiting (50 emails / hour by default)
- Analytics per campaign: reply rate, average emails before reply, status breakdowns

### Leads
- Manual add, bulk CSV import with client-side validation + preview
- Bulk delete with checkboxes and a floating action bar
- Edit all lead fields; edit is hidden on terminal statuses (replied / completed / failed)
- Email activity timeline per lead with smooth accordion expansion

### Email generation
- LLM-powered personalisation using DeepSeek v3.2 (or any OpenAI-compatible provider via `moonlight-ai` abstraction)
- Post-generation **critic pass**: a second LLM call scores the draft against a banned-pattern checklist (inference-from-fact openers, filler phrases, em-dashes, capability menu-dumps) and regenerates with feedback if violations are found
- Email preview endpoint: generate a draft for any lead without sending
- Threading: follow-ups go out with `Re: {original subject}` so email clients bundle them into the same conversation

### Documents library
- Upload PDF, DOCX, PPTX, TXT, or MD
- LlamaParse (agentic tier) extracts to markdown
- LLM distils to a 300-500 word product brief
- Brief is injected into every email generation for campaigns that attach the document
- Account-wide library: upload once, attach to multiple campaigns (cap: 2 documents per campaign to bound LLM input)

### Reply detection
- Resend inbound webhooks — replies are detected in real-time, no IMAP polling
- Tracking email format `{lead_id}@{EMAIL_DOMAIN}` embedded in `reply_to` header
- Webhook verifies Svix signatures, fetches full email content, strips quoted/forwarded text, stores clean reply
- Works regardless of campaign status — completes monitoring even after campaign finishes

## Setup Resend

### 1. Add your domain in Resend

- Go to [resend.com/domains](https://resend.com/domains) and add your domain
- Enable **Sending** and **Receiving** for the domain
- Add the DNS records Resend provides (MX, DKIM, SPF, Return-Path)

### 2. Set up inbound webhook

- Go to **Webhooks** in the Resend dashboard
- Click **Add Webhook**
- **Target URL**: `https://your-domain.com/webhooks/resend/inbound`
- **Events**: select `email.received`
- Copy the **Signing Secret** to `RESEND_WEBHOOK_SECRET` in your `.env`

### 3. Configure environment

```env
RESEND_API_KEY=re_...
RESEND_WEBHOOK_SECRET=whsec_...
EMAIL_DOMAIN=yourdomain.com
```

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