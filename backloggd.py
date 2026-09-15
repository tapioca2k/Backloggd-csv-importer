"""
Backloggd CSV Importer - Main Script
Imports games from a CSV file into Backloggd.com using the IGDB API for game matching.
"""

import requests
import csv
import sys
import os
import time
import argparse
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from config import get_backloggd_credentials, set_config_path, ConfigError
from igdb_search import get_game_id


# --- Configuration Constants ---
RETRY_WAIT_TIME = 300  # Seconds to wait when hitting rate limits
REQUEST_TIMEOUT = 30  # Seconds

# Valid game statuses
VALID_STATUSES = [
    "completed", "played", "abandoned", "retired", "shelved",
    "playing", "backlog", "wishlist"
]

# Year validation range
MIN_YEAR = 1950
MAX_YEAR = 2050

# Rating validation range
MIN_RATING = 0.0
MAX_RATING = 5.0


# --- Logging Setup ---
logger = logging.getLogger(__name__)


# --- Global Session ---
session = requests.Session()


def setup_logging(verbose: bool = False) -> None:
    """
    Configure logging for the application.
    
    Args:
        verbose: If True, set log level to DEBUG
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Create formatters
    console_formatter = logging.Formatter('%(message)s')
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    
    # File handler
    file_handler = logging.FileHandler('backloggd_import.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def update_headers() -> Dict[str, str]:
    """
    Create HTTP headers for Backloggd API requests.
    
    Returns:
        Dictionary of HTTP headers
    """
    creds = get_backloggd_credentials()
    session_id = creds["_backloggd_session"]
    csrf_token = creds["csrf"]
    
    headers = {
        "Connection": "keep-alive",
        "sec-ch-ua": '" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
        "Accept": "*/*",
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua-mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://backloggd.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://backloggd.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "Cookie": f"has_js=true; auth_server=true; daily_tip=%2C%20don't%20tell%20anyone%20else%2C%20but%20you're%20my%20favorite%20user%20%3B); game-log-editor-mode=quick; _backloggd_session={session_id}",
    }
    return headers


def add_game_to_backloggd(
    headers: Dict[str, str],
    game_id: int,
    rating: str,
    status: str = "completed",
    dry_run: bool = False,
    finish_date: str = ""
) -> int:
    """
    Submit a game log request to Backloggd.

    Args:
        headers: HTTP headers for the request
        game_id: IGDB game ID
        rating: Game rating (0-10 scale, or empty string)
        status: Game status (completed, playing, backlog, wishlist, etc.)
        dry_run: If True, don't actually make the request
        finish_date: Date played in YYYY-MM-DD format, or empty string

    Returns:
        HTTP status code
    """
    if dry_run:
        return 200  # Simulate success
    
    # Set status flags based on the status parameter
    is_play = (
        "true"
        if status in ["completed", "played", "abandoned", "retired", "shelved"]
        else "false"
    )
    is_playing = "true" if status == "playing" else "false"
    is_backlog = "true" if status == "backlog" else "false"
    is_wishlist = "true" if status == "wishlist" else "false"
    
    data = {
        "game_id": game_id,
        "playthroughs[0][id]": -1,
        "playthroughs[0][title]": "Log",
        "playthroughs[0][rating]": rating if rating else "",
        "playthroughs[0][review]": "",
        "playthroughs[0][review_spoilers]": "false",
        "playthroughs[0][platform]": "",
        "playthroughs[0][hours]": "",
        "playthroughs[0][minutes]": "",
        "playthroughs[0][is_master]": "false",
        "playthroughs[0][is_replay]": "false",
        # NOTE: "Date Played" is NOT stored in playthroughs[0][finish_date] --
        # Backloggd ignores that field (it stays empty in real requests too).
        # The actual date lives in a separate dates[] structure, added below only
        # when a date is provided. A missing/empty "Date Played" therefore sends
        # no dates[] block, i.e. "no date set" (the null case).
        "playthroughs[0][start_date]": "",
        "playthroughs[0][finish_date]": "",
        "log[is_play]": is_play,
        "log[is_playing]": is_playing,
        "log[is_backlog]": is_backlog,
        "log[is_wishlist]": is_wishlist,
        "log[status]": status,
        "log[id]": "",
        "modal_type": "quick",
    }

    # Attach a "Date Played" as a one-day date range in Backloggd's dates[] block.
    # Confirmed via browser capture: a played day is stored as
    #   dates[-1][0][range_start_date] = the day played (e.g. 2026-09-15)
    #   dates[-1][0][range_end_date]   = that day + 1    (e.g. 2026-09-16)
    # `[-1]` mirrors the new playthrough id (-1). status=5/edited=true come from
    # the same capture. finish_date is already normalized to YYYY-MM-DD upstream.
    if finish_date:
        try:
            start = datetime.strptime(finish_date, "%Y-%m-%d")
            end = start + timedelta(days=1)
            data.update({
                "dates[-1][0][id]": -1,
                "dates[-1][0][range_start_date]": start.strftime("%Y-%m-%d"),
                "dates[-1][0][range_end_date]": end.strftime("%Y-%m-%d"),
                "dates[-1][0][edited]": "true",
                "dates[-1][0][status]": "5",
                "dates[-1][0][note]": "",
                "dates[-1][0][hours]": "",
                "dates[-1][0][minutes]": "",
                "dates[-1][0][start_date]": "",
                "dates[-1][0][finish_date]": "",
                "dates[-1][0][privacy]": "",
            })
        except ValueError:
            logger.warning(
                f"Could not interpret 'Date Played' value '{finish_date}' for game {game_id}; "
                f"skipping date. Expected YYYY-MM-DD."
            )
    
    creds = get_backloggd_credentials()
    user_id = creds["backloggd_id"]
    url = f"https://backloggd.com/api/user/{user_id}/log/{game_id}"
    
    logger.debug(f"Sending to Backloggd: game_id={game_id}, rating={rating}, status={status}")
    
    try:
        r = session.post(url, headers=headers, data=data, timeout=REQUEST_TIMEOUT)
        logger.debug(f"Backloggd API response: {r.status_code}")
        return r.status_code
    except requests.exceptions.Timeout:
        logger.error("Request to Backloggd timed out")
        return 504  # Gateway timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"Request to Backloggd failed: {e}")
        return 500  # Internal server error


def validate_year(year_str: str, game_name: str) -> Optional[int]:
    """
    Validate and parse year from CSV.
    
    Args:
        year_str: Year string from CSV
        game_name: Game name (for logging)
        
    Returns:
        Valid year as integer, or None if invalid
    """
    if not year_str or not year_str.strip():
        return None
    
    if not year_str.strip().isdigit():
        logger.warning(f"Invalid year '{year_str}' for '{game_name}', ignoring year")
        return None
    
    year = int(year_str.strip())
    if not (MIN_YEAR <= year <= MAX_YEAR):
        logger.warning(
            f"Year {year} out of valid range ({MIN_YEAR}-{MAX_YEAR}) "
            f"for '{game_name}', ignoring year"
        )
        return None
    
    return year


def validate_rating(rating_str: str, game_name: str) -> str:
    """
    Validate and convert rating from CSV (5-star scale to 10-point scale).
    
    Args:
        rating_str: Rating string from CSV (0-5 scale)
        game_name: Game name (for logging)
        
    Returns:
        Valid rating as string (0-10 scale), or empty string if invalid
    """
    if not rating_str or not rating_str.strip():
        return ""
    
    try:
        rating_val = float(rating_str.strip())
        if not (MIN_RATING <= rating_val <= MAX_RATING):
            logger.warning(
                f"Rating {rating_val} out of valid range ({MIN_RATING}-{MAX_RATING}) "
                f"for '{game_name}', skipping rating"
            )
            return ""
        # Convert 5-star scale to 10-point scale
        return str(rating_val * 2)
    except ValueError:
        logger.warning(
            f"Invalid rating '{rating_str}' for '{game_name}', skipping rating"
        )
        return ""


def validate_status(status_str: str, game_name: str) -> str:
    """
    Validate game status from CSV.
    
    Args:
        status_str: Status string from CSV
        game_name: Game name (for logging)
        
    Returns:
        Valid status string, or 'completed' as default
    """
    if not status_str or not status_str.strip():
        return "completed"
    
    status = status_str.strip().lower()
    if status not in VALID_STATUSES:
        logger.warning(
            f"Invalid status '{status_str}' for '{game_name}', "
            f"using 'completed'. Valid statuses: {', '.join(VALID_STATUSES)}"
        )
        return "completed"
    
    return status


# Accepted input formats for the "Date Played" column (tried in order).
DATE_INPUT_FORMATS = [
    "%Y-%m-%d",   # 2022-03-15
    "%Y/%m/%d",   # 2022/03/15
    "%m/%d/%Y",   # 03/15/2022
    "%m-%d-%Y",   # 03-15-2022
    "%d/%m/%Y",   # 15/03/2022
    "%d-%m-%Y",   # 15-03-2022
    "%Y.%m.%d",   # 2022.03.15
]


def validate_date(date_str: str, game_name: str) -> str:
    """
    Validate and normalize the "Date Played" value from the CSV.

    Accepts several common formats (e.g. 2022-03-15, 03/15/2022, 15/03/2022)
    and normalizes them to the YYYY-MM-DD format that Backloggd expects.

    Args:
        date_str: Date string from CSV (may be empty)
        game_name: Game name (for logging)

    Returns:
        Date as a YYYY-MM-DD string, or empty string if missing/invalid
    """
    if not date_str or not date_str.strip():
        return ""

    date_str = date_str.strip()

    for fmt in DATE_INPUT_FORMATS:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    logger.warning(
        f"Unrecognized date format '{date_str}' for '{game_name}', skipping date played. "
        f"Expected one of: YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY"
    )
    return ""


def validate_csv_header(header: list) -> None:
    """
    Validate CSV header matches expected format.
    
    Args:
        header: First row of CSV file
    """
    expected = ["Game", "Year Released", "Rating", "Status", "Date Played"]
    
    if header != expected:
        logger.warning("CSV header doesn't match expected format")
        logger.warning(f"Expected: {expected}")
        logger.warning(f"Got: {header}")
        logger.warning("Proceeding anyway, but results may be incorrect")


def process_csv(
    file_path: str,
    not_found_path: str = "notfound.txt",
    start_row: int = 1,
    dry_run: bool = False
) -> None:
    """
    Process CSV file and import games to Backloggd.
    
    Args:
        file_path: Path to CSV file
        not_found_path: Path to file for logging games not found
        start_row: Row number to start processing from (1-indexed)
        dry_run: If True, don't actually add games to Backloggd
    """
    # Validate CSV file exists
    if not os.path.exists(file_path):
        logger.error(f"CSV file '{file_path}' not found")
        sys.exit(1)
    
    # Get headers
    headers = update_headers()
    
    # Count total rows for progress tracking
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        total_rows = sum(1 for row in reader if row) - start_row
    
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Processing {total_rows} games from '{file_path}'")
    
    # Process CSV
    with open(not_found_path, "a", encoding="utf-8") as not_found_log:
        not_found_log.write(
            f"\n--- Import Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"{'[DRY RUN]' if dry_run else ''} ---\n"
        )
        
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            processed = 0
            
            for i, row in enumerate(reader):
                # Skip rows before start_row
                if i < start_row:
                    # Validate header if this is the first row
                    if i == 0:
                        validate_csv_header(row)
                    continue
                
                if not row:
                    continue
                
                processed += 1
                
                # Parse CSV row
                name = row[0].strip() if len(row) > 0 else ""
                if not name:
                    logger.warning(f"[{processed}/{total_rows}] Skipping empty row")
                    continue
                
                year = validate_year(row[1] if len(row) > 1 else "", name)
                rating = validate_rating(row[2] if len(row) > 2 else "", name)
                status = validate_status(row[3] if len(row) > 3 else "", name)
                date_played = validate_date(row[4] if len(row) > 4 else "", name)
                
                logger.info(
                    f"[{processed}/{total_rows}] Processing: {name} "
                    f"({year if year else 'No Year'}"
                    f"{', played ' + date_played if date_played else ''})..."
                )
                
                success = False
                while not success:
                    game_id, match_name = get_game_id(name, year)
                    
                    if game_id == 429:
                        logger.warning(f"IGDB rate limit hit. Waiting {RETRY_WAIT_TIME}s...")
                        time.sleep(RETRY_WAIT_TIME)
                        continue
                    
                    if game_id:
                        res = add_game_to_backloggd(
                            headers, game_id, rating, status, dry_run, date_played
                        )
                        
                        if res < 400:
                            logger.info(
                                f"  {'[DRY RUN] Would add' if dry_run else 'Added'}: "
                                f"{name} ({status}"
                                f"{', played ' + date_played if date_played else ''}) -> {match_name}"
                            )
                            success = True
                        elif res == 401:
                            logger.error(
                                f"HTTP 401 (Unauthorized) at row {i + 1}. "
                                f"Your credentials may have expired."
                            )
                            logger.error(
                                f"To resume: Update backloggd.json, then run: python backloggd.py --start-row {i + 1}"
                            )
                            sys.exit(1)
                        elif res == 422:
                            # 422 can mean game already added OR invalid data
                            logger.info(
                                f"  Skipping {name}: Game may already be added (HTTP 422)"
                            )
                            success = True
                        elif res == 429:
                            logger.warning(f"Rate limit hit (HTTP 429). Waiting {RETRY_WAIT_TIME}s...")
                            time.sleep(RETRY_WAIT_TIME)
                        elif res >= 500:
                            logger.warning(
                                f"  Server error (HTTP {res}) for {name}. Skipping."
                            )
                            success = True
                        else:
                            # Could be rate limiting with a different status code
                            logger.warning(
                                f"  HTTP {res} error for {name}. "
                                f"If this happens frequently, you may be rate limited. Skipping."
                            )
                            success = True
                    else:
                        logger.warning(f"  NOT FOUND: Could not find '{name}' on IGDB")
                        not_found_log.write(f"{name}\n")
                        not_found_log.flush()  # Ensure immediate write to disk
                        success = True
    
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Import complete!")


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Import games from CSV to Backloggd.com",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Import from games.csv
  %(prog)s my_games.csv             # Import from custom CSV file
  %(prog)s --dry-run                # Preview import without making changes
  %(prog)s --start-row 50           # Resume from row 50
  %(prog)s --verbose                # Show detailed debug output
        """
    )
    
    parser.add_argument(
        "csv_file",
        nargs="?",
        default="games.csv",
        help="Path to CSV file (default: games.csv)"
    )
    parser.add_argument(
        "--config",
        default="backloggd.json",
        help="Path to config file (default: backloggd.json)"
    )
    parser.add_argument(
        "--not-found",
        default="notfound.txt",
        help="Path to not-found log file (default: notfound.txt)"
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=1,
        help="Row number to start from (default: 1, skips header row 0)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without making changes to Backloggd"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed debug output"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Set config path
    set_config_path(args.config)
    
    try:
        # Process CSV
        process_csv(
            args.csv_file,
            args.not_found,
            args.start_row,
            args.dry_run
        )
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nImport cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
