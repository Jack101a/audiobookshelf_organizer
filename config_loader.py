import json
import logging
from typing import Dict, Any, Optional

log = logging.getLogger(__name__)

def load_config(config_path: str = 'config.json') -> Dict[str, Any]:
    """
    Loads the configuration from a JSON file.

    Args:
        config_path: Path to the config.json file.

    Returns:
        A dictionary containing the loaded configuration.
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            log.info(f"Successfully loaded configuration from {config_path}")
            return config
    except FileNotFoundError:
        log.error(f"CRITICAL: Configuration file not found at {config_path}.")
        log.error("Please copy 'config.json.example' to 'config.json' and fill it out.")
        raise
    except json.JSONDecodeError:
        log.error(f"CRITICAL: Could not parse {config_path}. Check for JSON syntax errors.")
        raise
    except Exception as e:
        log.error(f"An unexpected error occurred loading config: {e}")
        raise

def get_config_value(
    config: Dict[str, Any],
    key_path: str,
    default: Optional[Any] = None
) -> Any:
    """
    Safely retrieves a nested value from the config dictionary.

    Example:
        get_config_value(config, "audible.api_base", "https://api.audible.com")

    Args:
        config: The configuration dictionary.
        key_path: A dot-separated path to the key (e.g., "audible.auth_file_path").
        default: The default value to return if the key is not found.

    Returns:
        The configuration value or the default.
    """
    keys = key_path.split('.')
    value = config
    try:
        for key in keys:
            value = value[key]
        return value
    except KeyError:
        log.warning(
            f"Config key '{key_path}' not found. Using default: {default}"
        )
        return default