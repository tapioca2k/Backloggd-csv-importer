# Backloggd.com CSV Importer

Quick and dirty Python script for importing games from a CSV file into Backloggd.com.

## Installation

1.  Clone this repository or download the files.
2.  Install the required Python packages:

```bash
pip install -r requirements.txt
```


## Initial Setup: Obtaining Your Credentials

To use this script, you need a `backloggd.json` file in the same directory. To get the required information, follow these steps:

1.  Go to the [Backloggd website](https://backloggd.com) and log in.
2.  Press **F12** to open the browser inspector.
3.  Click on the **Network** tab.
4.  In the filters, select **Fetch/XHR**.
5.  On the website, find any game, click **Edit Log**, make a temporary change (like changing the rating or status), and click **Save**.
6.  Look for a new request generated in the inspector (it will likely just be a number, which is the Game ID).
7.  **Verification**: Click on that request and check the **Request URL** in the **General** section. It should look like this:
    `https://backloggd.com/api/user/1234/log/5678`

### Extracting values for `backloggd.json`

Once you have the correct request selected:

*   **`backloggd_id`**: This is the number right after `/user/` in the Request URL (e.g., `1234` in the example above).
*   **`_backloggd_session`**: 
    1. Scroll down to the **Request Headers** section.
    2. Under the **Cookie** field, look for the part that says `_backloggd_session=` followed by a long string of numbers and letters. That whole string is your session value.
*   **`csrf`**: Look for **`X-Csrf-Token`** in the **Request Headers**. This is your CSRF token.

### Twitch/IGDB API

To get your Client ID and Client Secret, you need to register an application on the **Twitch Developer Console**:

1.  Log in to the [Twitch Developer Console](https://dev.twitch.tv/console).
2.  Click **Register Your Application**.
3.  Fill in the fields as follows:
    *   **Name**: Anything (e.g., "Backloggd Importer")
    *   **OAuth Redirect URLs**: `https://localhost`
    *   **Category**: `Application Integration`
    *   **Client Type**: `Confidential`
4.  Once created, click **Manage** on your application.
5.  Scroll to the bottom to find your **Client ID** (`id`).
6.  Click **New Secret** to generate and copy your **Client Secret** (`secret`).

### Final `backloggd.json` Format

Create a file named `backloggd.json` in the same directory as the script and paste the following structure with your collected values:

```json
{
    "id": "example_client_id_12345",
    "secret": "example_client_secret_67890",
    "backloggd_id": "1234",
    "csrf": "aB1c2D3e4F5g6H7i8J9k0L1m2N3o4P5q6R7s8T9u0V1w2X3y4Z5",
    "_backloggd_session": "BAh7CEkiD3Nlc3Npb25faWQGOgZFRiIlZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2ZDY0ZjY2"
}
```

## CSV Format

Your CSV should have the following columns:

```csv
Game,Year Released,Rating,Status,Date Played
Elden Ring,2022,5,completed,2022-05-25
Hollow Knight,2017,4.5,playing,
Silksong,2024,,wishlist,
Hades,2020,4,backlog,
Cyberpunk 2077,2020,3.5,playing,03/15/2022
```

| Column | Required | Description |
|--------|----------|-------------|
| **Game** | ✅ Yes | Game name (used for IGDB search) |
| **Year Released** | ✅ Yes | Release year (helps IGDB find the correct game) |
| **Rating** | ❌ No | Your rating on a **5-star scale** (use decimals for half stars: 4.5, 3.5, etc.). Leave empty for no rating. |
| **Status** | ❌ No | Game status: `completed`, `playing`, `backlog`, or `wishlist`. Defaults to `completed` if not specified. |
| **Date Played** | ❌ No | The date you played/finished the game. Leave empty for none. (See below.) |

### Rating System

Ratings use a **5-star scale**:
- Leave **empty** for no rating
- Use **0-5** scale (e.g., `3`, `4`, `5`)
- Supports **half stars** using decimals: `3.5`, `4.5`, etc.
- The script automatically converts your 5-star rating to Backloggd's 10-point scale (e.g., `4.5` stars → `9/10`)

### Date Played

This is the date you played or finished the game. It shows up on the game's entry in your Backloggd log. It's optional — leave it blank to skip.

The script accepts several common formats and normalizes them to `YYYY-MM-DD` before sending:

| Format | Example |
|--------|---------|
| `YYYY-MM-DD` (recommended) | `2022-05-25` |
| `YYYY/MM/DD` | `2022/05/25` |
| `MM/DD/YYYY` (US) | `05/25/2022` |
| `DD/MM/YYYY` | `25/05/2022` |
| `YYYY.MM.DD` | `2022.05.25` |

> **Note:** For ambiguous `DD/MM` vs `MM/DD` dates, US `MM/DD/YYYY` is tried first (so `03/15/2022` = March 15). Use `YYYY-MM-DD` to avoid ambiguity.

### Status Options

- **`completed`** - Finished the game (default if not specified)
- **`playing`** - Currently playing
- **`backlog`** - Want to play
- **`wishlist`** - Interested in

Additional valid statuses: `played`, `abandoned`, `retired`, `shelved`


## Usage

### Basic Usage

```bash
python backloggd.py
```

This will import games from `games.csv` using the default settings.

### Command-Line Options

The script now supports various command-line options for flexibility:

```bash
python backloggd.py [csv_file] [options]
```

**Positional Arguments:**
- `csv_file` - Path to CSV file (default: `games.csv`)

**Optional Arguments:**
- `--config CONFIG` - Path to config file (default: `backloggd.json`)
- `--not-found FILE` - Path to not-found log file (default: `notfound.txt`)
- `--start-row N` - Row number to start from (default: 1, skips header row 0)
- `--dry-run` - Preview import without making changes to Backloggd
- `--verbose` - Show detailed debug output
- `-h, --help` - Show help message

### Examples

**Preview import without making changes:**
```bash
python backloggd.py --dry-run
```

**Import from a custom CSV file:**
```bash
python backloggd.py my_games.csv
```

**Resume from a specific row (useful if import was interrupted):**
```bash
python backloggd.py --start-row 50
```

**Show detailed debug output:**
```bash
python backloggd.py --verbose
```

**Use custom config file:**
```bash
python backloggd.py --config custom_config.json
```

**Combine multiple options:**
```bash
python backloggd.py my_games.csv --dry-run --verbose --start-row 10
```

### Features

- ✅ **Progress Tracking** - Shows "Processing game X of Y" with current progress
- ✅ **Input Validation** - Validates year (1950-2050), rating (0-5), and status
- ✅ **Error Handling** - Graceful handling of network errors, rate limits, and authentication issues
- ✅ **Logging** - Outputs to both console and `backloggd_import.log` file
- ✅ **Dry-Run Mode** - Preview what will be imported without making changes
- ✅ **Resume Support** - Resume from any row if import is interrupted
- ✅ **Not Found Tracking** - Games not found in IGDB are written to `notfound.txt`

### Troubleshooting

**Games not being found:**
- Check spelling in your CSV file (common typos: "Deadsapce" → "Dead Space", "Rouge Legacy" → "Rogue Legacy")
- Include the release year to help matching
- Check `notfound.txt` for a list of games that couldn't be matched

**Authentication errors:**
- Your CSRF token and session cookie may have expired
- Follow the setup instructions again to get fresh credentials

**Rate limiting:**
- The script automatically handles rate limits with exponential backoff
- IGDB: Waits 120 seconds when rate limit is hit
- Backloggd: Waits 300 seconds when rate limit is hit

**Checking logs:**
- Review `backloggd_import.log` for detailed execution history
- Use `--verbose` flag for more detailed console output

