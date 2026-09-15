"""
Centralized configuration management for Backloggd CSV Importer.
Handles loading and validating credentials from backloggd.json.
"""

import json
import sys
from typing import Dict, Any, Optional


class ConfigError(Exception):
    """Raised when there's an issue with the configuration file."""
    pass


_config: Optional[Dict[str, Any]] = None
_config_path: str = "backloggd.json"


def set_config_path(path: str) -> None:
    """Set the path to the configuration file."""
    global _config_path, _config
    _config_path = path
    _config = None  # Reset cached config


def load_config() -> Dict[str, Any]:
    """
    Load and validate configuration from backloggd.json.
    
    Returns:
        Dictionary containing configuration values
        
    Raises:
        ConfigError: If config file is missing, malformed, or incomplete
    """
    global _config
    
    # Return cached config if already loaded
    if _config is not None:
        return _config
    
    try:
        with open(_config_path, "r", encoding="utf-8") as f:
            _config = json.load(f)
    except FileNotFoundError:
        raise ConfigError(
            f"Configuration file '{_config_path}' not found.\n"
            "Please create it following the instructions in README.md"
        )
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"Configuration file '{_config_path}' contains invalid JSON:\n{e}\n"
            "Please check the file format and try again."
        )
    except Exception as e:
        raise ConfigError(f"Error reading configuration file: {e}")
    
    # Validate required fields
    _validate_config(_config)
    
    return _config


def _validate_config(config: Dict[str, Any]) -> None:
    """
    Validate that all required fields are present in the config.
    
    Args:
        config: Configuration dictionary to validate
        
    Raises:
        ConfigError: If required fields are missing
    """
    # Required fields for Backloggd API
    backloggd_fields = ["backloggd_id", "csrf", "_backloggd_session"]
    
    # Required fields for IGDB API
    igdb_fields = ["id", "secret"]
    
    all_required = backloggd_fields + igdb_fields
    
    missing_fields = [field for field in all_required if field not in config]
    
    if missing_fields:
        raise ConfigError(
            f"Missing required fields in '{_config_path}':\n"
            f"  {', '.join(missing_fields)}\n\n"
            f"Required fields:\n"
            f"  Backloggd: {', '.join(backloggd_fields)}\n"
            f"  IGDB: {', '.join(igdb_fields)}\n\n"
            f"Please see README.md for instructions on obtaining these values."
        )
    
    # Validate field values are not empty
    empty_fields = [field for field in all_required if not str(config[field]).strip()]
    
    if empty_fields:
        raise ConfigError(
            f"The following required fields are empty in '{_config_path}':\n"
            f"  {', '.join(empty_fields)}\n\n"
            f"Please provide valid values for all required fields."
        )


def get_backloggd_credentials() -> Dict[str, str]:
    """
    Get Backloggd-specific credentials.
    
    Returns:
        Dictionary with backloggd_id, csrf, and _backloggd_session
    """
    config = load_config()
    return {
        "backloggd_id": config["backloggd_id"],
        "csrf": config["csrf"],
        "_backloggd_session": config["_backloggd_session"]
    }


def get_igdb_credentials() -> Dict[str, str]:
    """
    Get IGDB API credentials.
    
    Returns:
        Dictionary with id (client_id) and secret (client_secret)
    """
    config = load_config()
    return {
        "client_id": config["id"],
        "client_secret": config["secret"]
    }
