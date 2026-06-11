# okx-tg-auto

Telegram DM automation — sends personalised messages to existing contacts, segmented by cohort and language.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in API_ID, API_HASH, PHONE, SPREADSHEET_ID
```

### Google Sheets setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → Create a project
2. Enable **Google Sheets API**
3. Create a **Service Account** → download the JSON key → save as `service_account.json` in this folder
4. Share your Google Sheet with the service account email (viewer access is enough)
5. Copy the spreadsheet ID from the URL and add to `.env`

### Required sheet columns

| Column | Description |
|--------|-------------|
| `tg_username` | Telegram @handle |
| `phone` | International format (alternative to username) |
| `name` | Used in `{name}` placeholder |
| `cohort` | `P0`, `P1`, `P2`, `TV Affiliates`, `FTT Affiliates` |
| `language` | `en`, `ru`, `zh` (falls back to `en` if missing) |

## Usage

```bash
# Dry run — preview all messages
python sender.py --dry-run

# Send to one cohort only
python sender.py --cohort P0
python sender.py --cohort "TV Affiliates"

# Send to all cohorts (sorted P0 → P1 → P2 → TV Affiliates → FTT Affiliates)
python sender.py

# Use a local CSV instead of Google Sheets
python sender.py --csv contacts.csv

# Override rate limits
python sender.py --cohort P0 --delay 3 --daily-limit 200
```

## Message templates

Edit `templates.yaml` to set your message copy per cohort and language:

```yaml
P0:
  en: "Hi {name}, as one of our top clients..."
  ru: "Привет {name}..."
  zh: "你好 {name}..."
```

If a contact's language has no template, it falls back to `en`.
