"""Pull contacts from Google Sheets."""

import os
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

REQUIRED_COLUMNS = {"tg_username", "name", "cohort", "language"}


def load_contacts_from_sheets() -> list[dict]:
    key_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    worksheet_name = os.getenv("WORKSHEET_NAME", "Sheet1")

    if not spreadsheet_id:
        raise ValueError("SPREADSHEET_ID must be set in your .env file")

    creds = Credentials.from_service_account_file(key_file, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sheet = gc.open_by_key(spreadsheet_id).worksheet(worksheet_name)
    rows = sheet.get_all_records()

    if not rows:
        return []

    # Normalise column names: lowercase + strip whitespace
    normalised = []
    for row in rows:
        normalised.append({k.strip().lower().replace(" ", "_"): v for k, v in row.items()})

    missing = REQUIRED_COLUMNS - set(normalised[0].keys())
    if missing:
        raise ValueError(f"Sheet is missing required columns: {missing}")

    return normalised
