import re
import os
import json
import logging
import stat
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set

from tag_reader import read_tags

log = logging.getLogger(__name__)

# --- Constants ---
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\n\r\t]|\.$|^\s|\s$')
MULTI_SPACE_RE = re.compile(r'\s+')
SUPPORTED_AUDIO_EXTENSIONS = {".aax", ".m4b", ".mp3", ".m4a"}

# NEW: Changed log name
PROCESSED_LOG_NAME = "processed_metadata.json"

# --- Main Functions (Unchanged) ---

def sanitize_filename(filename: str, max_length: int = 200) -> str:
    # ... (function is unchanged) ...
    if not filename:
        return ""
    sanitized = INVALID_FILENAME_CHARS_RE.sub('', filename)
    sanitized = MULTI_SPACE_RE.sub(' ', sanitized)
    sanitized = sanitized.strip()
    if len(sanitized) > max_length:
        last_space = sanitized.rfind(' ', 0, max_length)
        if last_space > 0:
            sanitized = sanitized[:last_space]
        else:
            sanitized = sanitized[:max_length]
    return sanitized

def format_contributors(contributors: List[str], separator: str = " & ") -> str:
    # ... (function is unchanged) ...
    if not contributors:
        return ""
    return separator.join(contributors)

def load_asin_map(map_path: Optional[str]) -> Dict[str, str]:
    # ... (function is unchanged) ...
    asin_map: Dict[str, str] = {}
    if not map_path or not os.path.exists(map_path):
        if map_path:
            log.warning(f"ASIN map file not found: {map_path}")
        return asin_map
    log.info(f"Loading ASIN map from {map_path}...")
    try:
        if map_path.endswith('.json'):
            with open(map_path, 'r', encoding='utf-8') as f:
                asin_map = json.load(f)
        elif map_path.endswith('.csv'):
            with open(map_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if ',' in line:
                        parts = line.split(',', 1)
                        if len(parts) == 2:
                            filename, asin = parts[0].strip(), parts[1].strip()
                            if filename and asin:
                                asin_map[filename] = asin
        else:
            log.warning(f"Unknown ASIN map file format: {map_path}. Must be .json or .csv")
    except Exception as e:
        log.error(f"Failed to load ASIN map from {map_path}: {e}")
    log.info(f"Loaded {len(asin_map)} ASIN mappings.")
    return asin_map

# --- NEW: Deep Scan Function ---

def find_audio_files_to_process(
    input_dir: str, 
    processed_log: Dict[str, Any], # CHANGED: Now a dict
    min_file_size_mb: int
) -> List[Path]:
    """
    Performs a full deep scan (os.walk) of the input directory.
    Filters files by:
    1. Already in processed_log (checks keys)
    2. Audio extension
    3. File size (>= min_file_size_mb)
    """
    files_to_process: List[Path] = []
    log.info(f"Deep scanning for audio files in: {input_dir}")
    
    min_file_size_bytes = min_file_size_mb * 1024 * 1024

    for root, _, files in os.walk(input_dir, topdown=True):
        if "__FAILED_TO_PROCESS__" in root:
            continue
            
        for file in files:
            file_path = Path(root) / file
            
            # 1. Check if already processed
            str_path = str(file_path)
            # CHANGED: Check if path is a key in the dict
            if str_path in processed_log: 
                log.debug(f"Skipping already processed file: {file}")
                continue

            # 2. Check for audio extension
            if file_path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
                continue

            # 3. Check file size
            try:
                file_size = file_path.stat().st_size
                if file_size < min_file_size_bytes:
                    log.info(f"Skipping small file: {file} [Size: {file_size / (1024*1024):.2f}MB]")
                    continue
            except OSError as e:
                log.warning(f"Could not read size of file {file_path}: {e}")
                continue
            
            files_to_process.append(file_path)

    log.info(f"Found {len(files_to_process)} new audio files to process (>= {min_file_size_mb}MB).")
    return files_to_process

# --- NEW: Processed Log Functions ---

def load_processed_log(output_dir: Path) -> Dict[str, Any]: # CHANGED: Returns Dict
    """
    Loads the processed log file from the output directory.
    Returns a dict of {file_path: metadata} for fast lookups.
    """
    log_path = output_dir / PROCESSED_LOG_NAME
    if not log_path.exists():
        log.info(f"No '{PROCESSED_LOG_NAME}' found. Starting fresh.")
        return {} # Return empty dict
    
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            log.info(f"Loaded {len(data)} paths from processed log.")
            return data # Return the full dict
    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Could not read {PROCESSED_LOG_NAME}: {e}. Starting fresh.")
        return {}

def append_to_processed_log(
    output_dir: Path, 
    original_file_path: str, 
    metadata: Dict[str, Any], # CHANGED: Pass in metadata
    processed_dict: Dict[str, Any] # CHANGED: Pass in the dict
) -> None:
    """
    Adds a file's metadata to the processed dict and saves the log as read-only.
    """
    log_path = output_dir / PROCESSED_LOG_NAME
    
    # NEW: Create the log entry as requested
    log_entry = {
        "title": metadata.get("title"),
        "series": metadata.get("series"),
        "year": metadata.get("formatted_year"),
        "asin": metadata.get("asin")
    }
    
    # Add the new entry to the dictionary
    processed_dict[original_file_path] = log_entry
    
    # Make the file writable
    if log_path.exists():
        try:
            os.chmod(log_path, 0o644) # rw-r--r--
        except OSError as e:
            log.error(f"Could not make log writeable: {e}")
            return

    # Write the new log
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(processed_dict, f, indent=2) # Save the whole dict
            log.info(f"Added {original_file_path} to processed log.")
    except IOError as e:
        log.error(f"Could not write to processed log: {e}")

    # Make the file read-only
    try:
        os.chmod(log_path, 0o444) # r--r--r--
    except OSError as e:
        log.error(f"Could not make log read-only: {e}")

# --- Unused Helper Functions ---
# (These are no longer needed but are safe to leave)
def get_metadata_from_folder(*args, **kwargs): pass
def _parse_opf_for_asin(*args, **kwargs): pass
def _parse_json_for_asin(*args, **kwargs): pass

def trigger_abs_rescan(config: Dict[str, Any], dry_run: bool) -> None:
    # ... (function is unchanged) ...
    pass
