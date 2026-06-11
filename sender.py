#!/usr/bin/env python3
"""Telegram DM automation — sends messages to existing contacts."""

import asyncio
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError, PeerFloodError, UserPrivacyRestrictedError, InputUserDeactivatedError
from telethon.tl.types import User

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")

if not API_ID or not API_HASH:
    sys.exit("ERROR: API_ID and API_HASH must be set in your .env file")

DEFAULT_DELAY = 5       # seconds between messages
DEFAULT_DAILY_LIMIT = 150


async def send_messages(
    contacts: list[dict],
    dry_run: bool = False,
    delay: int = DEFAULT_DELAY,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
) -> None:
    sent = 0

    async with TelegramClient("session", int(API_ID), API_HASH) as client:
        await client.start(phone=PHONE)

        for contact in contacts:
            if sent >= daily_limit:
                print(f"[LIMIT] Daily limit of {daily_limit} reached. Stopping.")
                break

            recipient = contact.get("username") or contact.get("phone")
            message = contact.get("message", "").strip()
            name = contact.get("name", "")

            if not recipient or not message:
                print(f"[SKIP] Missing recipient or message: {contact}")
                continue

            message = message.replace("{name}", name)

            if dry_run:
                print(f"[DRY RUN] To: {recipient} | Message: {message!r}")
                sent += 1
                continue

            try:
                entity = await client.get_entity(recipient)
                if not isinstance(entity, User):
                    print(f"[SKIP] {recipient} is not a user (group/channel)")
                    continue

                await client.send_message(entity, message)
                sent += 1
                print(f"[SENT {sent}/{daily_limit}] {recipient}")

            except PeerFloodError:
                # Pre-ban warning — stop immediately
                print("[STOP] PeerFloodError: Telegram flagged this account. Stop and wait 24h before retrying.")
                sys.exit(1)

            except FloodWaitError as e:
                print(f"[FLOOD] Rate limited — waiting {e.seconds}s")
                await asyncio.sleep(e.seconds)
                await client.send_message(recipient, message)
                sent += 1
                print(f"[SENT {sent}/{daily_limit}] {recipient} (after flood wait)")

            except UserPrivacyRestrictedError:
                print(f"[SKIP] {recipient} has privacy settings that block messages")

            except InputUserDeactivatedError:
                print(f"[SKIP] {recipient} account is deactivated")

            except Exception as e:
                print(f"[ERROR] {recipient}: {e}")

            await asyncio.sleep(delay)

    print(f"\nDone. Sent {sent} message(s).")


def load_contacts_from_csv(path: str) -> list[dict]:
    contacts = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(dict(row))
    return contacts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send Telegram DMs to existing contacts")
    parser.add_argument("--csv", required=True, help="CSV file with columns: username, phone, name, message")
    parser.add_argument("--dry-run", action="store_true", help="Preview messages without sending")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY, help=f"Seconds between messages (default: {DEFAULT_DELAY})")
    parser.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT, help=f"Max messages per run (default: {DEFAULT_DAILY_LIMIT})")
    args = parser.parse_args()

    if not Path(args.csv).exists():
        sys.exit(f"ERROR: CSV file not found: {args.csv}")

    contacts = load_contacts_from_csv(args.csv)
    print(f"Loaded {len(contacts)} contacts. Delay: {args.delay}s | Limit: {args.daily_limit}/day")

    asyncio.run(send_messages(contacts, dry_run=args.dry_run, delay=args.delay, daily_limit=args.daily_limit))
