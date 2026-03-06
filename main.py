"""
Morning Briefing FastAPI — wraps the notebooklm CLI for Railway deployment.
All endpoints require X-API-Key header matching the API_KEY env var.
"""

import os
import json
import uuid
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Morning Briefing API", version="1.0.0")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("API_KEY", "")

def verify_api_key(x_api_key: str = Header(...)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY env var not set on server")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cli(cmd: str) -> dict:
    """Run a notebooklm CLI command and return parsed JSON output."""
    logger.info(f"CLI: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"CLI error: {result.stderr}")
        raise HTTPException(
            status_code=500,
            detail=f"CLI command failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Some commands return non-JSON success output
        return {"output": result.stdout.strip()}


def run_cli_raw(cmd: str) -> subprocess.CompletedProcess:
    """Run a CLI command and return the raw result (for binary downloads)."""
    logger.info(f"CLI (raw): {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class BriefingRequest(BaseModel):
    briefing_text: str                  # Formatted briefing doc from n8n / Claude
    news_urls: Optional[list[str]] = [] # Optional extra news URLs to add as sources
    audio_instructions: Optional[str] = (
        "Create a tight, engaging morning briefing podcast. "
        "Start by covering the key emails and action items, "
        "then discuss the news highlights, "
        "and end with a clear rundown of the day's schedule. "
        "Be concise, direct, and energetic — this is a commute podcast."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Health check for Railway."""
    return {"status": "ok"}


@app.post("/briefing/run", dependencies=[Depends(verify_api_key)])
def run_briefing(req: BriefingRequest):
    """
    All-in-one endpoint:
    1. Creates a fresh notebook
    2. Adds the briefing text as a source
    3. Adds any extra news URLs as sources
    4. Kicks off audio generation
    Returns {notebook_id, task_id} immediately — poll /briefing/status to wait.
    """
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    title = f"Morning Briefing — {date_str}"

    # 1. Create notebook
    nb = run_cli(f'notebooklm create "{title}" --json')
    notebook_id = nb["notebook"]["id"]
    logger.info(f"Created notebook: {notebook_id}")

    # 2. Write briefing text to temp file and add as source
    tmp_path = Path(tempfile.mktemp(suffix=".txt"))
    tmp_path.write_text(req.briefing_text)
    try:
        run_cli(f'notebooklm source add "{tmp_path}" --notebook {notebook_id} --json')
    finally:
        tmp_path.unlink(missing_ok=True)

    # 3. Add extra news URLs (best-effort; failures are logged, not fatal)
    for url in req.news_urls or []:
        try:
            run_cli(f'notebooklm source add "{url}" --notebook {notebook_id} --json')
            logger.info(f"Added source: {url}")
        except Exception as e:
            logger.warning(f"Failed to add source {url}: {e}")

    # 4. Generate audio
    safe_instructions = req.audio_instructions.replace('"', '\\"')
    artifact = run_cli(
        f'notebooklm generate audio "{safe_instructions}" --length short --notebook {notebook_id} --json'
    )
    task_id = artifact.get("task_id", "")
    logger.info(f"Generation started: task_id={task_id}")

    return {
        "notebook_id": notebook_id,
        "task_id": task_id,
        "status": "generating",
        "message": "Podcast generation started. Poll /briefing/status/{notebook_id} to check completion."
    }


@app.get("/briefing/status/{notebook_id}", dependencies=[Depends(verify_api_key)])
def get_status(notebook_id: str):
    """
    Check the status of the audio generation artifact.
    Returns {status: pending|in_progress|completed|error, artifact_id}.
    """
    data = run_cli(f'notebooklm artifact list --notebook {notebook_id} --json')
    artifacts = data.get("artifacts", [])

    if not artifacts:
        return {"status": "pending", "artifact_id": None}

    # Find the most recent audio artifact
    audio = next(
        (a for a in artifacts if "audio" in a.get("type", "").lower()),
        artifacts[0]
    )
    return {
        "status": audio.get("status", "unknown"),
        "artifact_id": audio.get("id"),
        "title": audio.get("title", ""),
    }


@app.get("/briefing/download/{notebook_id}", dependencies=[Depends(verify_api_key)])
def download_audio(notebook_id: str):
    """
    Download the completed podcast MP3. Returns binary audio file.
    Call this only after /briefing/status returns {status: completed}.
    """
    out_path = Path(f"/tmp/briefing-{notebook_id}.mp3")
    result = run_cli_raw(
        f'notebooklm download audio "{out_path}" --notebook {notebook_id}'
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {result.stderr.decode().strip()}"
        )
    if not out_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found after download")

    return FileResponse(
        path=str(out_path),
        media_type="audio/mpeg",
        filename=f"morning-briefing-{notebook_id[:8]}.mp3"
    )


@app.delete("/briefing/{notebook_id}", dependencies=[Depends(verify_api_key)])
def cleanup(notebook_id: str):
    """Delete the notebook and local temp file to keep the workspace clean."""
    run_cli(f'notebooklm notebook delete {notebook_id}')
    # Also clean up any local MP3
    mp3 = Path(f"/tmp/briefing-{notebook_id}.mp3")
    mp3.unlink(missing_ok=True)
    return {"deleted": notebook_id}
