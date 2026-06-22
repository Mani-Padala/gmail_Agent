# Gmail AI Agent 🤖

> Autonomous inbox management powered by Claude AI — controlled via WhatsApp

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![Claude AI](https://img.shields.io/badge/Claude-Haiku_4.5-purple?logo=anthropic)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)
![Twilio](https://img.shields.io/badge/Twilio-WhatsApp-red?logo=twilio)
![SQLite](https://img.shields.io/badge/Storage-SQLite-lightgrey?logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Overview

The Gmail AI Agent is an agentic system that autonomously classifies and manages your Gmail inbox using Anthropic's Claude Haiku LLM. It fetches emails, classifies them into categories, stores a full audit trail, and lets you approve or reject deletions through natural language on WhatsApp.

**You type this on WhatsApp:**
```
run the agent
```

**You get back:**
```
✅ Email Check Complete
📥 Fetched: 20 | Already seen: 15 | Kept: 3 | To delete: 2

🗑️ Emails marked for deletion:
1. Welcome to Claude
   From: Claude Team
   Why: Promotional signup email

Reply yes to delete all, no to skip.
```

---

## Features

- **Context-aware classification** — Claude reads subject, sender, date, and full body to classify as `spam` / `job` / `news` / `alert`
- **Multi-layer guardrails** — OTPs, tax docs, receipts, government emails always protected regardless of LLM output
- **Human-in-the-loop** — nothing deleted without your explicit `yes` via WhatsApp
- **Natural language control** — `run the agent`, `clean my inbox`, `summary`, `yes`, `done`
- **Full audit trail** — every decision stored in SQLite with classification reason and approval status
- **Cost efficient** — ~$0.004 per run using Claude Haiku with token caps
- **Deduplication** — emails are never re-processed across runs

---

## Architecture

```
You (WhatsApp)
    → Twilio (WhatsApp bridge)
        → ngrok (public tunnel to localhost)
            → FastAPI webhook server
                → Intent Router (Claude Haiku)
                    → Agent Engine
                        ├── Gmail API   — fetch & delete emails
                        ├── Claude Haiku — classify emails
                        └── SQLite DB   — store & audit
                    → WhatsApp reply via Twilio
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10 |
| AI Model | Claude Haiku 4.5 (Anthropic) |
| Email | Gmail API v1 (OAuth 2.0) |
| Web Server | FastAPI + uvicorn |
| Messaging | Twilio WhatsApp API |
| Tunnel | ngrok |
| Storage | SQLite |
| Auth | google-auth-oauthlib |

---

## Project Structure

```
gmail_agent/
├── agent/
│   ├── classifier.py       # LLM classification + guardrails + cost tracking
│   ├── database.py         # SQLite data access layer
│   └── gmail_client.py     # Gmail API — fetch, delete, OAuth
├── bot/
│   ├── router.py           # Natural language → structured intent (Claude)
│   ├── session.py          # In-memory conversation state
│   └── whatsapp_bot.py     # FastAPI webhook server + flow orchestration
├── tools/
│   └── cleanup.py          # One-time full inbox cleanup (batched)
├── config/                 # Gmail OAuth credentials (not committed)
├── data/                   # SQLite database (not committed)
├── main.py                 # Daily agent run (preview + execute)
└── .env                    # Secrets (not committed)
```

---

## Prerequisites

- Python 3.10+
- A Google account with Gmail
- An Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
- A Twilio account — [twilio.com](https://www.twilio.com) (free sandbox)
- ngrok — [ngrok.com](https://ngrok.com) (free tier)
- A WhatsApp account

---

## Setup Guide

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/gmail-agent
cd gmail-agent
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac / Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install anthropic google-auth-oauthlib google-auth-httplib2 google-api-python-client fastapi uvicorn twilio python-dotenv python-multipart
```

### 4. Gmail API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable the **Gmail API**
4. Create **OAuth 2.0 credentials** (Desktop App)
5. Download the credentials JSON file
6. Rename it to `credentials.json` and place it in `config/`

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...

TWILIO_ACCOUNT_SID=ACxxx...
TWILIO_AUTH_TOKEN=xxx...
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
YOUR_WHATSAPP_NUMBER=whatsapp:+91xxxxxxxxxx
```

### 6. Twilio WhatsApp Sandbox Setup

1. Sign up at [twilio.com](https://www.twilio.com)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Note your sandbox number and join code
4. Send the join code from your WhatsApp to the sandbox number
   ```
   join bright-tiger   ← (your code will be different)
   ```
5. You should receive a confirmation reply from Twilio

### 7. Install and Configure ngrok

```bash
# Windows (PowerShell)
winget install Ngrok.Ngrok

# Mac
brew install ngrok

# Add your authtoken (get it from dashboard.ngrok.com)
ngrok config add-authtoken YOUR_AUTHTOKEN
```

---

## Running the Agent

### Option A — Terminal Mode (No WhatsApp needed)

Test the classification pipeline directly from the terminal:

```bash
python main.py
```

This runs the full preview + confirmation flow in the terminal. Good for testing before setting up Twilio.

### Option B — WhatsApp Bot Mode (Full Setup)

You need **two terminals** running simultaneously:

**Terminal 1 — Start the bot server (VS Code / venv terminal):**
```bash
python -m bot.whatsapp_bot
```

You should see:
```
INFO: Uvicorn running on http://0.0.0.0:8000
INFO: Application startup complete.
```

**Terminal 2 — Start ngrok (PowerShell):**
```bash
ngrok http 8000
```

You will see a public URL like:
```
Forwarding  https://abc123.ngrok-free.app -> http://localhost:8000
```

**Then in Twilio Console:**
1. Go to **Messaging → Sandbox settings**
2. Paste your ngrok URL + `/webhook` in "When a message comes in":
   ```
   https://abc123.ngrok-free.app/webhook
   ```
3. Set method to **HTTP POST**
4. Click **Save**

### Option C — One-Time Full Inbox Cleanup

```bash
python tools/cleanup.py
```

Processes your entire inbox in batches of 50, asking for confirmation per batch.

---

## WhatsApp Commands

| Command | What it does |
|---------|-------------|
| `run the agent` | Fetches and classifies new emails since last run |
| `clean my inbox` | Full inbox sweep in batches of 50 |
| `summary` | Shows email counts by category |
| `yes` | Confirm deletion of pending emails |
| `no` | Skip deletion, mark emails as skipped |
| `next` | Move to next cleanup batch without deleting |
| `done` | Stop the cleanup session |
| `reset` | Clear stuck session state |

> **Note:** Do not send `stop` — Twilio intercepts this as an unsubscribe command and ends your session.

---

## Email Categories

| Flag | Description | Decision |
|------|-------------|----------|
| `alert` | OTPs, receipts, bookings, bills, insurance, tax docs | Always keep |
| `job` | Job postings, HR communications, interview calls | Keep |
| `news` | Tech news, industry updates from reputable sources | Keep |
| `spam` | Promotions, offers, unsolicited marketing | Delete (with approval) |

---

## Database Schema

**gmail_agent table:**

| Column | Type | Description |
|--------|------|-------------|
| `gmail_id` | TEXT UNIQUE | Gmail message ID — deduplication key |
| `sender` | TEXT | Email sender |
| `subject` | TEXT | Email subject |
| `flag` | TEXT | spam / job / news / alert |
| `decision` | TEXT | delete / keep |
| `reason` | TEXT | One-line explanation from Claude |
| `user_approval` | TEXT | pending → approved / skipped / na |

---

## Cost

| Item | Cost |
|------|------|
| Claude Haiku input | $1.00 / million tokens |
| Claude Haiku output | $5.00 / million tokens |
| Typical run (10 emails) | ~$0.004 USD |
| Monthly (daily runs) | ~$0.12 USD |

---

## Important Notes

- **ngrok URL changes** every time you restart ngrok on the free tier. Update the Twilio sandbox webhook URL each time.
- **Twilio sandbox expires** after 72 hours of inactivity. Rejoin by sending your join code again.
- **Emails go to Trash**, not permanently deleted — 30-day recovery window in Gmail.
- **First run** authenticates Gmail via browser — a `token.pickle` file is saved to `config/` for future runs.

---

## Roadmap

- [ ] Upgrade to Python 3.11
- [ ] Add retry logic (tenacity) for Claude + Gmail API calls
- [ ] Add pytest test suite for classifier and guardrails
- [ ] Move session state to Redis
- [ ] PostgreSQL support for multi-user
- [ ] Docker + docker-compose
- [ ] GitHub Actions CI/CD
- [ ] Permanent cloud hosting (Railway / Render)
- [ ] Clear trash utility

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built by Manikanta Padala · June 2026*
