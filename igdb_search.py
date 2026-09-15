"""
IGDB game search functionality for Backloggd CSV Importer.
Handles game matching and scoring using the IGDB API.
"""

import requests
import re
import sys
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_igdb_credentials, ConfigError


# --- Logging Setup ---
logger = logging.getLogger(__name__)


# --- Configuration Constants ---
RETRY_WAIT_TIME = 120
REQUEST_TIMEOUT = 30  # seconds

# Game type categories considered "Official products" vs "Mods/Costumes"
# 0: Main Game, 3: Bundle, 4: Standalone Expansion, 8: Remake, 9: Remaster, 
# 10: Pack, 11: CP, 12: Season, 13: Epic
HIGH_PRIORITY_TYPES = [0, 3, 4, 8, 9, 10, 11, 12, 13]

# Keywords that indicate special editions or variants
KEYWORDS = [
    "remake",
    "remaster",
    "edition",
    "collection",
    "bundle",
    "pack",
    "gold",
    "ultimate",
    "port",
    "limited",
    "costume",
    "skin",
    "fps",
    "version",
]

# Prefixes that might be imputed (e.g., "Mario 64" -> "Super Mario 64")
IMPUTED_PREFIXES = ["super ", "the ", "legend of ", "sid meier's "]


# --- Scoring Constants ---
SCORE_MAIN_GAME_BOOST = 300
SCORE_OFFICIAL_PRODUCT_BOOST = 200
SCORE_EXACT_MATCH = 200
SCORE_NORMALIZED_MATCH = 150
SCORE_IMPUTED_PREFIX_MATCH = 150
SCORE_PREFIX_MATCH = 60
SCORE_SUBSTRING_MATCH = 30
SCORE_KEYWORD_PENALTY = -50
SCORE_YEAR_EXACT = 100
SCORE_YEAR_CLOSE_1 = 50
SCORE_YEAR_CLOSE_2 = 20
SCORE_YEAR_FAR_PENALTY = -100
SCORE_YEAR_RECENCY_FACTOR = -1.5
SCORE_LENGTH_PENALTY_FACTOR = -0.5
SCORE_RANK_BASE = 10
SCORE_RANK_DECAY = 0.5

# Scoring thresholds
MEDIOCRE_SCORE_THRESHOLD = 100


# --- Global Session & Auth ---
_session: Optional[requests.Session] = None
_headers: Dict[str, str] = {}


def _initialize_session() -> None:
    """Initialize the IGDB API session with authentication and retry logic."""
    global _session, _headers
    
    if _session is not None:
        return  # Already initialized
    
    try:
        # Get credentials from config module
        creds = get_igdb_credentials()
        client_id = creds["client_id"]
        client_secret = creds["client_secret"]
        
        # Create session with retry logic
        _session = requests.Session()
        
        # Configure retry strategy for transient failures
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            method_whitelist=["POST", "GET"]  # For older urllib3, use method_whitelist instead of allowed_methods
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
        
        # Get OAuth Token
        url = (
            f"https://id.twitch.tv/oauth2/token"
            f"?client_id={client_id}"
            f"&client_secret={client_secret}"
            f"&grant_type=client_credentials"
        )
        r = _session.post(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        token = r.json()["access_token"]
        
        _headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}"
        }
        
        logger.info("IGDB API session initialized successfully")
        
    except ConfigError:
        raise  # Re-raise config errors
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to authenticate with IGDB API: {e}")
        raise RuntimeError(f"IGDB API authentication failed: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize IGDB search: {e}")
        raise RuntimeError(f"IGDB initialization failed: {e}")


def normalize_name(name: str) -> str:
    """
    Standardize name for comparison:
    1. Lowercase
    2. Roman numerals to Arabic (e.g., IX -> 9)
    3. Remove all non-alphanumeric characters
    
    Args:
        name: Game name to normalize
        
    Returns:
        Normalized name string
    """
    name = name.lower()
    
    def roman_to_int(rom: str) -> str:
        """Convert Roman numeral string to integer string."""
        rom_val = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
        int_val = 0
        for i in range(len(rom)):
            if i > 0 and rom_val[rom[i]] > rom_val[rom[i - 1]]:
                int_val += rom_val[rom[i]] - 2 * rom_val[rom[i - 1]]
            else:
                int_val += rom_val[rom[i]]
        return str(int_val)
    
    # Identify whole words that are Roman numerals
    roman_pattern = (
        r"\b(?=[mdclxvi]+\b)m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})\b"
    )
    name = re.sub(roman_pattern, lambda m: roman_to_int(m.group(0)), name)
    
    return re.sub(r"[^a-z0-9]", "", name)


def calculate_score(
    query: str,
    game_data: Dict[str, Any],
    csv_year: Optional[int],
    rank_index: int
) -> float:
    """
    Calculate a match score for a single IGDB result.
    Higher scores indicate better matches.
    
    Args:
        query: Original search query
        game_data: Game data from IGDB API
        csv_year: Year from CSV (optional)
        rank_index: Position in IGDB search results (0-based)
        
    Returns:
        Match score (higher is better)
    """
    name = game_data["name"]
    game_type = game_data.get("game_type")
    release_date = game_data.get("first_release_date")
    igdb_year = datetime.fromtimestamp(release_date).year if release_date else None
    
    score = 0.0
    query_lower = query.lower()
    name_lower = name.lower()
    
    # 1. Category Boost
    if game_type == 0:
        score += SCORE_MAIN_GAME_BOOST
    elif game_type in HIGH_PRIORITY_TYPES:
        score += SCORE_OFFICIAL_PRODUCT_BOOST
    
    # 2. Match Quality (Exactness)
    query_norm = normalize_name(query)
    name_norm = normalize_name(name)
    
    if name_lower == query_lower:
        score += SCORE_EXACT_MATCH
    elif name_norm == query_norm:
        score += SCORE_NORMALIZED_MATCH
    else:
        # Check for imputed prefixes (e.g., "Mario 64" -> "Super Mario 64")
        for prefix in IMPUTED_PREFIXES:
            if (name_lower == prefix + query_lower or 
                name_norm == normalize_name(prefix + query_norm)):
                score += SCORE_IMPUTED_PREFIX_MATCH
                break
        
        # Partial matches
        if name_lower.startswith(query_lower) or name_norm.startswith(query_norm):
            score += SCORE_PREFIX_MATCH
        elif query_norm in name_norm:
            score += SCORE_SUBSTRING_MATCH
    
    # 3. IGDB Search Rank Relevance (decay to respect IGDB's internal ranking)
    score += SCORE_RANK_BASE - rank_index * SCORE_RANK_DECAY
    
    # 4. Keyword Penalties
    for kw in KEYWORDS:
        if kw in name_lower and kw not in query_lower:
            score += SCORE_KEYWORD_PENALTY
    
    # 5. Year Proximity
    if csv_year and igdb_year:
        year_diff = abs(csv_year - igdb_year)
        if year_diff == 0:
            score += SCORE_YEAR_EXACT
        elif year_diff <= 1:
            score += SCORE_YEAR_CLOSE_1
        elif year_diff <= 2:
            score += SCORE_YEAR_CLOSE_2
        elif year_diff > 10:
            score += SCORE_YEAR_FAR_PENALTY
    
    # 6. Original Release Preference (tie-breaker for duplicate names/ports)
    if igdb_year:
        score += (igdb_year - 1970) * SCORE_YEAR_RECENCY_FACTOR
    
    # 7. Length Penalty (tie-breaker for extra words)
    score += len(name) * SCORE_LENGTH_PENALTY_FACTOR
    
    return score


def get_game_id(
    name: str,
    csv_year: Optional[int],
    retry_no_spaces: bool = True
) -> Tuple[Optional[int], Optional[str]]:
    """
    Find the best game ID on IGDB for the given name and optional year.
    
    Args:
        name: Game name to search for
        csv_year: Release year from CSV (optional, helps matching)
        retry_no_spaces: Whether to retry without spaces if no good match
        
    Returns:
        Tuple of (game_id, matched_name) or (429, None) for rate limit or (None, None) if not found
    """
    # Initialize session if needed
    if _session is None:
        _initialize_session()
    
    # Clean search name
    search_name = name.replace(":", " ").replace("\ufffd", "").strip()
    search_name = re.sub(r"\s+", " ", search_name)
    
    logger.info(f"Searching IGDB for '{search_name}'...")
    
    try:
        # Primary search with exact phrase
        body = f'fields name, first_release_date, game_type; search "{search_name}"; limit 20;'
        r = _session.post(
            "https://api.igdb.com/v4/games/",
            headers=_headers,
            data=body.encode("utf-8"),
            timeout=REQUEST_TIMEOUT
        )
        
        if r.status_code == 429:
            logger.warning("IGDB rate limit hit")
            return 429, None
        
        r.raise_for_status()
        results = r.json()
        
        # Fallback 1: Try with special characters removed
        if not results and (":" in name or " " in name):
            alt_search = re.sub(r"[^a-zA-Z0-9 ]", " ", name).strip()
            logger.debug(f"No results for phrase. Trying with cleaned name: '{alt_search}'")
            body = f'fields name, first_release_date, game_type; search "{alt_search}"; limit 20;'
            r = _session.post(
                "https://api.igdb.com/v4/games/",
                headers=_headers,
                data=body.encode("utf-8"),
                timeout=REQUEST_TIMEOUT
            )
            if r.status_code == 200:
                results = r.json()
        
        # Fallback 2: Try without quotes (broader search)
        if not results and (":" in name or " " in name):
            logger.debug("No results for phrase. Retrying broad search...")
            body = f'fields name, first_release_date, game_type; search {search_name}; limit 20;'
            r = _session.post(
                "https://api.igdb.com/v4/games/",
                headers=_headers,
                data=body.encode("utf-8"),
                timeout=REQUEST_TIMEOUT
            )
            if r.status_code == 200:
                results = r.json()
        
        # Fallback 3: Subtitle check (e.g., "Hollow Knight: Silksong" -> "Silksong")
        if not results and ":" in name:
            subtitle = name.split(":")[-1].strip()
            if len(subtitle) > 3:
                logger.debug(f"No results. Retrying with subtitle '{subtitle}'...")
                return get_game_id(subtitle, csv_year, retry_no_spaces=retry_no_spaces)
        
        # Fallback 4: No spaces
        if not results and retry_no_spaces and " " in name:
            logger.debug("No results. Retrying without spaces...")
            return get_game_id(name.replace(" ", ""), csv_year, retry_no_spaces=False)
        
        if not results:
            logger.warning(f"No results found for '{name}'")
            return None, None
        
        # Score all matches
        matches: List[Dict[str, Any]] = []
        for i, game in enumerate(results):
            score = calculate_score(name, game, csv_year, i)
            matches.append({
                "id": game["id"],
                "name": game["name"],
                "score": score,
                "type": game.get("game_type"),
            })
        
        matches.sort(key=lambda x: x["score"], reverse=True)
        best = matches[0]
        
        # Spacing Fallback: Handle "Little Big Planet" vs "LittleBigPlanet"
        is_mediocre = best["score"] < MEDIOCRE_SCORE_THRESHOLD
        current_name_lower = best["name"].lower()
        likely_subproduct = (
            any(kw in current_name_lower for kw in ["edition", "pack", "bundle"])
            and " " not in name.lower()
        )
        
        if retry_no_spaces and " " in name and (is_mediocre or likely_subproduct):
            alt_id, alt_name = get_game_id(
                name.replace(" ", ""), csv_year, retry_no_spaces=False
            )
            if alt_id and alt_id != 429:
                logger.debug(f"Using no-space alternative: {alt_name}")
                return alt_id, alt_name
        
        logger.info(f"Best match: {best['name']} (score: {best['score']:.1f})")
        return best["id"], best["name"]
    
    except requests.exceptions.Timeout:
        logger.error(f"Request timeout while searching for '{name}'")
        return None, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error searching IGDB for '{name}': {e}")
        return None, None
    except Exception as e:
        logger.error(f"Unexpected error searching IGDB for '{name}': {e}")
        return None, None


# Initialize session on module load
try:
    _initialize_session()
except Exception as e:
    logger.error(f"Failed to initialize IGDB module: {e}")
    # Don't exit here - let the first actual search attempt handle the error
