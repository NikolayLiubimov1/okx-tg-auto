# okx-tg-auto

Telegram DM automation tool — sends personalised direct messages to existing contacts.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your API_ID and API_HASH
```

## Usage

### 1. Create a contacts CSV

Copy `contacts.example.csv` and fill in your contacts:

| Column | Description |
|--------|-------------|
| `username` | Telegram @username (use this OR phone) |
| `phone` | Phone number in international format |
| `name` | Used to personalise the message via `{name}` |
| `message` | Message text. Use `{name}` as a placeholder. |

### 2. Dry run (no messages sent)

```bash
python sender.py --csv contacts.csv --dry-run
```

### 3. Send messages

```bash
python sender.py --csv contacts.csv
```

On first run you will be prompted to enter your phone number and a login code sent by Telegram. A `session` file is created locally so you only authenticate once.

## Notes

- A 2-second delay is inserted between messages to avoid Telegram anti-spam limits.
- `FloodWaitError` is handled automatically — the script waits and retries.
- The `session` file and `.env` are gitignored and never committed.
