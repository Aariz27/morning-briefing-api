# 🎙️ AI Morning Briefing Podcast — Setup Guide

## What You Need Before Starting
- n8n Cloud account
- Google account (Gmail + Calendar)
- Telegram account + a bot (create via @BotFather)
- GitHub account
- Anthropic API key (claude.ai/api)
- notebooklm-py installed locally (pip install notebooklm-py)

---

## Step 1 — Get Your NotebookLM Auth

On your local machine:
  pip install notebooklm-py
  notebooklm login        ← opens browser, sign in with Google
  cat ~/.notebooklm/storage_state.json   ← copy the ENTIRE contents

You'll need this in Step 2.

---

## Step 2 — GitHub Setup

1. Create a new GitHub repo (e.g. "morning-briefing")
2. Create the folder: .github/workflows/
3. Upload morning-briefing.yml into that folder
4. Go to Settings → Secrets and variables → Actions → New repository secret

Add these 3 secrets:

  NOTEBOOKLM_AUTH_JSON  →  paste the full contents of storage_state.json
  TELEGRAM_BOT_TOKEN    →  your bot token from @BotFather
  TELEGRAM_CHAT_ID      →  your chat ID (get it from @userinfobot)

5. Go to Settings → Tokens (classic) → generate a token with scopes: repo + workflow
   Save this token — you'll need it for n8n.

---

## Step 3 — n8n Setup

1. Import morning_briefing_workflow.json into n8n
2. Go to Settings → Variables and add:

  ANTHROPIC_API_KEY  →  your Anthropic key
  GITHUB_TOKEN       →  the token from Step 2

3. Open the workflow and connect credentials:
  - "Fetch Last 24h Emails" node → connect your Google account
  - "Fetch Today's Events" node  → same Google account

4. In the "Trigger GitHub Action" HTTP Request node:
  - Update the URL to point to YOUR repo (replace Aariz27 with your GitHub username)
  - Body type: Raw | Content type: application/json
  - Body expression:
    ={{ JSON.stringify({ ref: "main", inputs: { briefing_text: $('Generate Briefing Text').item.json.content[0].text } }) }}

---

## Step 4 — Test

Hit "Test Workflow" in n8n.
Watch it run in GitHub → your repo → Actions tab.
MP3 should arrive in your Telegram in ~15-20 minutes.

---

## Step 5 — Activate

Toggle the workflow Active in n8n.
It will run every day at 6:00am (Asia/Kuala_Lumpur).
To change the time: edit the Schedule Trigger node.

---

## Files in This Folder

  morning-briefing.yml           → goes into .github/workflows/ in your GitHub repo
  morning_briefing_workflow.json → import this into n8n
  README.txt                     → this file
