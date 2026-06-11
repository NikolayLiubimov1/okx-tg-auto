#!/usr/bin/env python3
"""Telegram DM automation — sends messages to existing contacts."""

import asyncio
import csv
import os
import sys
from pathlib import Path

import yaml
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

DEFAULT_DELAY = 5
DEFAULT_DAILY_LIMIT = 150
PRIORITY_ORDER = ["P0", "P1", "P2", "TV Affiliates", "FTT Affiliates"]


def load_templates(path: str = "templates.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_message(templates: dict, contact: dict) -> str | None:
    cohort = contact.get("cohort", "").strip()
    language = contact.get("language", "en").strip().lower()

    cohort_templates = templates.get(cohort)
    if not cohort_templates:
        return None

    # Fall back to English if the contact's language isn't defined
    message = cohort_templates.get(language) or cohort_templates.get("en", "")
    if not message:
        return None

    return message.replace("{name}", contact.get("name", ""))


def sort_by_priority(contacts: list[dict]) -> list[dict]:
    def key(c):
        cohort = c.get("cohort", "")
        try:
            return PRIORITY_ORDER.index(cohort)
        except ValueError:
            return len(PRIORITY_ORDER)
    return sorted(contacts, key=key)


def load_contacts_from_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


async def send_messages(
    contacts: list[dict],
    templates: dict,
    cohort_filter: str | None = None,
    dry_run: bool = False,
    delay: int = DEFAULT_DELAY,
    daily_limit: int = DEFAULT_DAILY_LIMIT,
) -> None:
    if cohort_filter:
        contacts = [c for c in contacts if c.get("cohort", "").strip() == cohort_filter]
        print(f"Filtered to cohort '{cohort_filter}': {len(contacts)} contacts")

    contacts = sort_by_priority(contacts)
    sent = 0

    async with TelegramClient("session", int(API_ID), API_HASH) as client:
        await client.start(phone=PHONE)

        for contact in contacts:
            if sent >= daily_limit:
                print(f"[LIMIT] Daily limit of {daily_limit} reached. Stopping.")
                break

            recipient = contact.get("tg_username") or contact.get("phone", "").strip()
            if not recipient:
                print(f"[SKIP] No tg_username or phone for: {contact.get('name')}")
                continue

            message = resolve_message(templates, contact)
            if not message:
                print(f"[SKIP] No template for cohort='{contact.get('cohort')}' lang='{contact.get('language')}' — fill in templates.yaml")
                continue

            if dry_run:
                print(f"[DRY RUN] [{contact.get('cohort')}] To: {recipient} | {message!r}")
                sent += 1
                continue

            try:
                entity = await client.get_entity(recipient)
                if not isinstance(entity, User):
                    print(f"[SKIP] {recipient} is not a user")
                    continue

                await client.send_message(entity, message)
                sent += 1
                print(f"[SENT {sent}/{daily_limit}] [{contact.get('cohort')}] {recipient}")

            except PeerFloodError:
                print("[STOP] PeerFloodError: Telegram flagged this account. Wait 24h before retrying.")
                sys.exit(1)

            except FloodWaitError as e:
                print(f"[FLOOD] Rate limited — waiting {e.seconds}s")
                await asyncio.sleep(e.seconds)
                await client.send_message(recipient, message)
                sent += 1
                print(f"[SENT {sent}/{daily_limit}] [{contact.get('cohort')}] {recipient} (after flood wait)")

            except UserPrivacyRestrictedError:
                print(f"[SKIP] {recipient} privacy settings block messages")

            except InputUserDeactivatedError:
                print(f"[SKIP] {recipient} account is deactivated")

            except Exception as e:
                print(f"[ERROR] {recipient}: {e}")

            await asyncio.sleep(delay)

    print(f"\nDone. Sent {sent} message(s).")


if __name__ == "__main__":
    import argparse
    from sheets import load_contacts_from_sheets

    parser = argparse.ArgumentParser(description="Send Telegram DMs to existing contacts")
    parser.add_argument("--cohort", help="Only send to this cohort (e.g. 'P0', 'TV Affiliates')")
    parser.add_argument("--csv", help="Load contacts from a local CSV instead of Google Sheets")
    parser.add_argument("--dry-run", action="store_true", help="Preview messages without sending")
    parser.add_argument("--delay", type=int, default=DEFAULT_DELAY, help=f"Seconds between messages (default: {DEFAULT_DELAY})")
    parser.add_argument("--daily-limit", type=int, default=DEFAULT_DAILY_LIMIT, help=f"Max messages per run (default: {DEFAULT_DAILY_LIMIT})")
    args = parser.parse_args()

    if args.csv:
        contacts = load_contacts_from_csv(args.csv)
        print(f"Loaded {len(contacts)} contacts from {args.csv}")
    else:
        contacts = load_contacts_from_sheets()
        print(f"Loaded {len(contacts)} contacts from Google Sheets")

    templates = load_templates()
    asyncio.run(send_messages(
        contacts,
        templates,
        cohort_filter=args.cohort,
        dry_run=args.dry_run,
        delay=args.delay,
        daily_limit=args.daily_limit,
    ))
