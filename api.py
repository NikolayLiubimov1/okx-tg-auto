#!/usr/bin/env python3
"""FastAPI backend for the Telegram DM automation UI."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from sender import load_contacts_from_csv, load_templates, sort_by_priority, resolve_message
from sheets import load_contacts_from_sheets

TEMPLATES_PATH = Path("templates.yaml")
LOG_PATH = Path("send_log.jsonl")

app = FastAPI(title="TG Auto")
app.mount("/static", StaticFiles(directory="static"), name="static")


def append_log(entry: dict):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# --- Contacts ---

@app.get("/api/contacts")
def get_contacts(cohort: str = None):
    try:
        contacts = load_contacts_from_sheets()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if cohort:
        contacts = [c for c in contacts if c.get("cohort", "").strip() == cohort]
    contacts = sort_by_priority(contacts)
    return {"contacts": contacts, "total": len(contacts)}


# --- Templates ---

@app.get("/api/templates")
def get_templates():
    return yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))


class TemplateUpdate(BaseModel):
    cohort: str
    language: str
    message: str


@app.post("/api/templates")
def update_template(update: TemplateUpdate):
    templates = yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8"))
    if update.cohort not in templates:
        raise HTTPException(status_code=404, detail=f"Cohort '{update.cohort}' not found")
    templates[update.cohort][update.language] = update.message
    TEMPLATES_PATH.write_text(yaml.dump(templates, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


# --- Send (streaming progress) ---

class SendRequest(BaseModel):
    cohort: str | None = None
    dry_run: bool = False
    delay: int = 5
    daily_limit: int = 150


@app.post("/api/send")
async def send(req: SendRequest):
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            contacts = load_contacts_from_sheets()
        except Exception as e:
            msg = str(e).replace('"', "'")
            yield f'data: {{"type": "error", "message": "{msg}"}}\n\n'
            return

        if req.cohort:
            contacts = [c for c in contacts if c.get("cohort", "").strip() == req.cohort]
        contacts = sort_by_priority(contacts)
        templates = load_templates()

        yield f'data: {{"type": "start", "total": {len(contacts)}}}\n\n'

        from telethon import TelegramClient
        from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError, InputUserDeactivatedError
        from telethon.tl.types import User

        api_id = os.getenv("API_ID")
        api_hash = os.getenv("API_HASH")
        phone = os.getenv("PHONE")

        sent = 0
        async with TelegramClient("session", int(api_id), api_hash) as client:
            await client.start(phone=phone)

            for contact in contacts:
                if sent >= req.daily_limit:
                    yield f'data: {{"type": "limit", "message": "Daily limit {req.daily_limit} reached"}}\n\n'
                    break

                recipient = contact.get("tg_username") or contact.get("phone", "").strip()
                name = contact.get("name", "")
                cohort = contact.get("cohort", "")
                lang = contact.get("language", "en")

                if not recipient:
                    yield f'data: {{"type": "skip", "recipient": "{name}", "reason": "no username or phone"}}\n\n'
                    continue

                message = resolve_message(templates, contact)
                if not message:
                    yield f'data: {{"type": "skip", "recipient": "{recipient}", "reason": "no template for {cohort}/{lang}"}}\n\n'
                    continue

                if req.dry_run:
                    yield f'data: {{"type": "dry_run", "recipient": "{recipient}", "cohort": "{cohort}", "message": {json.dumps(message)}}}\n\n'
                    sent += 1
                    await asyncio.sleep(0.1)
                    continue

                try:
                    entity = await client.get_entity(recipient)
                    if not isinstance(entity, User):
                        yield f'data: {{"type": "skip", "recipient": "{recipient}", "reason": "not a user"}}\n\n'
                        continue
                    await client.send_message(entity, message)
                    sent += 1
                    append_log({"ts": datetime.utcnow().isoformat(), "recipient": recipient, "cohort": cohort, "status": "sent"})
                    yield f'data: {{"type": "sent", "recipient": "{recipient}", "cohort": "{cohort}", "sent": {sent}, "limit": {req.daily_limit}}}\n\n'

                except PeerFloodError:
                    yield f'data: {{"type": "flood_stop", "message": "PeerFloodError - stopping. Wait 24h."}}\n\n'
                    return

                except FloodWaitError as e:
                    yield f'data: {{"type": "flood_wait", "seconds": {e.seconds}}}\n\n'
                    await asyncio.sleep(e.seconds)
                    await client.send_message(recipient, message)
                    sent += 1
                    yield f'data: {{"type": "sent", "recipient": "{recipient}", "cohort": "{cohort}", "sent": {sent}, "limit": {req.daily_limit}}}\n\n'

                except UserPrivacyRestrictedError:
                    yield f'data: {{"type": "skip", "recipient": "{recipient}", "reason": "privacy restricted"}}\n\n'

                except InputUserDeactivatedError:
                    yield f'data: {{"type": "skip", "recipient": "{recipient}", "reason": "account deactivated"}}\n\n'

                except Exception as e:
                    err = str(e).replace('"', "'")
                    yield f'data: {{"type": "error", "recipient": "{recipient}", "message": "{err}"}}\n\n'

                await asyncio.sleep(req.delay)

        yield f'data: {{"type": "done", "sent": {sent}}}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Log ---

@app.get("/api/log")
def get_log(limit: int = 200):
    if not LOG_PATH.exists():
        return {"entries": []}
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    entries = [json.loads(l) for l in lines[-limit:]]
    return {"entries": list(reversed(entries))}


# --- Serve UI ---

@app.get("/", response_class=HTMLResponse)
def index():
    return Path("static/index.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
