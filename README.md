# Gmail AI Agent

> Autonomous inbox management powered by Claude AI, controlled via WhatsApp

![Python](https://img.shields.io/badge/Python-3.10-blue)
![Claude AI](https://img.shields.io/badge/Claude-Haiku_4.5-purple)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Overview
The Gmail AI Agent is an agentic system that autonomously classifies and
manages email using large language models. It fetches emails from Gmail,
classifies them using Claude Haiku, stores results with a full audit trail,
and allows approval of deletions via WhatsApp natural language commands.

## Business Context
Professionals receive 100+ emails weekly. Manual triage is unsustainable.
Standard filters lack contextual intelligence. This agent uses LLMs to
understand email intent — not just keywords — while protecting critical
emails through deterministic guardrails.

## Architecture
WhatsApp → Twilio → ngrok → FastAPI → Intent Router (Claude)
    → Agent Engine → Gmail API + Claude Classifier + SQLite

## Key Features
- Context-aware classification (spam/job/news/alert)
- Multi-layer guardrails (OTPs, receipts, tax docs always protected)
- Human-in-the-loop: nothing deleted without WhatsApp confirmation
- Natural language control ('run the agent', 'clean my inbox')
- Full audit trail with user_approval lifecycle
- Cost tracking: ~$0.004 per run

## Setup
```bash
git clone https://github.com/yourusername/gmail-agent
cd gmail-agent
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
# Add Gmail credentials to config/credentials.json
# Add .env variables (see .env.example)
python main.py  # local test
python -m bot.whatsapp_bot  # WhatsApp bot
```

## Results
- 587 emails tracked in SQLite
- 281 spam emails deleted (48% of inbox)
- $0.004 average cost per run
