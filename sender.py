#!/usr/bin/env python3
"""Telegram DM automation — sends messages to existing contacts."""

import asyncio
import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, InputUserDeactivatedError
from telethon.tl.types import User

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")

if not API_ID or not API_HASH:
    sys.exit("ERROR: API_ID and API_HASH must be set in your .env file")


async def send_messages(contacts: list[dict], dry_run: bool = False) -> None:
    """
    Send a DM to each contact in the list.

    Each contact dict must have:
      - 'username' OR 'phone': how to resolve the recipient
      - 'message': text to send (supports {name} placeholder)
    """
    async with TelegramClient("session", int(API_ID), API_HASH) as client:
        await client.start(phone=PHONE)

        for contact in contacts:
            recipient = contact.get("username") or contact.get("phone")
            message = contact.get("message", "").strip()
            name = contact.get("name", "")

            if not recipient or not message:
                print(f"[SKIP] Missing recipient or message: {contact}")
                continue

            message = message.replace("{name}", name)

            if dry_run:
                print(f"[DRY RUN] To: {recipient} | Message: {message!r}")
                continue

            try:
                entity = await client.get_entity(recipient)
                if not isinstance(entity, User):
                    print(f"[SKIP] {recipient} is not a user (group/channel)")
                    continue

                await client.send_message(entity, message)
                print(f"[SENT] {recipient}")

            except FloodWaitError as e:
                print(f"[FLOOD] Rate limited — waiting {e.seconds}s before continuing")
                await asyncio.sleep(e.seconds)
                await client.send_message(recipient, message)
                print(f"[SENT] {recipient} (after flood wait)")

            except UserPrivacyRestrictedError:
                print(f"[SKIP] {recipient} has privacy settings that block messages")

            except InputUserDeactivatedError:
                print(f"[SKIP] {recipient} account is deactivated")

            except Exception as e:
                print(f"[ERROR] {recipient}: {e}")

            # Polite delay to avoid triggering Telegram's anti-spam
            await asyncio.sleep(2)


def load_contacts_from_csv(path: str) -> list[dict]:
    """Load contacts from a CSV file with columns: username/phone, name, message"""
    contacts = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(dict(row))
    return contacts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send Telegram DMs to existing contacts")
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to CSV file with columns: username, name, message",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages without actually sending them",
    )
    args = parser.parse_args()

    if not Path(args.csv).exists():
        sys.exit(f"ERROR: CSV file not found: {args.csv}")

    contacts = load_contacts_from_csv(args.csv)
    print(f"Loaded {len(contacts)} contacts from {args.csv}")

    asyncio.run(send_messages(contacts, dry_run=args.dry_run))
