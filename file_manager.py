import logging
import shutil
import os
from pathlib import Path
from typing import Dict, Any, Optional

from utils import sanitize_filename, SUPPORTED_AUDIO_EXTENSIONS, format_contributors

log = logging.getLogger(__name__)

def create_book_structure(
    output_dir: Path,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    dry_run: bool = False
) -> Optional[Path]:
    """
    Creates the book folder structure based on FORMATTED metadata.
    Does NOT move any files.
    """
    organizer_cfg = config.get("organizer", {})
    max_len = organizer_cfg.get("max_filename_length", 200)

    # --- 1. Get Path Components from FORMATTED metadata ---
    primary_author = "Unknown Author"
    if metadata.get("authors"):
        primary_author = metadata["authors"][0] 
        
    author_folder_name = sanitize_filename(primary_author, max_len)
    
    all_authors_str = metadata.get("formatted_album_artist", "Unknown Author")
    
    title_str = sanitize_filename(metadata.get("title", ""), max_len)
    if not title_str:
        log.warning("Metadata has no title. Cannot create folder.")
        return None
        
    year_str = metadata.get("formatted_year", "")
    series_str = sanitize_filename(metadata.get("series", ""), max_len)

    # --- 2. Determine target folder path ---
    book_folder_name = f"{title_str} {{{all_authors_str}}} {{{year_str}}}"
    book_folder_name = sanitize_filename(book_folder_name, max_len)

    target_folder = Path(output_dir) / author_folder_name
    
    if series_str:
        target_folder = target_folder / series_str
    
    target_folder = target_folder / book_folder_name

    # --- 3. Create folder ---
    if dry_run:
        log.info(f"[DRY RUN] Would create target folder: {target_folder}")
    else:
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            log.info(f"Created folder: {target_folder}")
        except OSError as e:
            log.error(f"Failed to create target folder {target_folder}: {e}")
            return None
    
    return target_folder

def organize_audio_file(
    source_file: Path,
    output_dir: Path,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    dry_run: bool = False,
    move: bool = False
) -> Optional[Path]:
    """
    Organizes a single audio file into the new structure,
    and RENAMES the file to match metadata.
    """
    
    # --- 1. Create the folder structure ---
    target_folder = create_book_structure(output_dir, metadata, config, dry_run)
    if not target_folder:
        log.error(f"Failed to create folder structure for {metadata.get('title')}")
        return None

    # --- 2. Perform file operation ---
    action = "Move" if move else "Copy"
    
    # --- THIS IS THE RENAMING LOGIC (RESTORED) ---
    organizer_cfg = config.get("organizer", {})
    max_len = organizer_cfg.get("max_filename_length", 200)

    title_str = sanitize_filename(metadata.get("title", ""), max_len)
    series_str = sanitize_filename(metadata.get("series", ""), max_len)
    all_authors_str = metadata.get("formatted_album_artist", "Unknown Author")
    year_str = metadata.get("formatted_year", "")

    series_part = f" {{{series_str}}}" if series_str else ""
    new_filename_base = (
        f"{title_str}{series_part} {{{all_authors_str}}} {{{year_str}}}"
    )
    new_filename = sanitize_filename(
        f"{new_filename_base}{source_file.suffix}",
        max_len
    )
    
    target_file_path = target_folder / new_filename
    # --- END OF RENAMING LOGIC ---
    
    if dry_run:
        log.info(f"[DRY RUN] Would {action.lower()} file:")
        log.info(f"[DRY RUN]   From: {source_file}")
        log.info(f"[DRY RUN]   To:   {target_file_path}")
    else:
        _safe_file_op(source_file, target_file_path, move)

    return target_folder

def _safe_file_op(source: Path, dest: Path, move: bool) -> None:
    """Helper to perform a single file move/copy operation."""
    action = "Move" if move else "Copy"
    log_action = "Moving" if move else "Copying"
    
    try:
        if move:
            shutil.move(source, dest)
            log.info(f"Moved {source.name} to {dest}")
        else:
            shutil.copy2(source, dest)
            log.info(f"Copied {source.name} to {dest}")
    except OSError as e:
        log.error(f"Failed to {action.lower()} file {source.name}: {e}")

def move_to_failed_folder(
    source_file: Path,
    output_dir: Path,
    dry_run: bool = False,
    move: bool = False
) -> None:
    """
    Moves or copies a single file to the '__FAILED_TO_PROCESS__' directory.
    """
    failed_dir = Path(output_dir) / "__FAILED_TO_PROCESS__"
    action = "move" if move else "copy"
    log_action = "Would move" if move else "Would copy"

    if dry_run:
        log.warning(f"[DRY RUN] {log_action} failed file to: {failed_dir / source_file.name}")
        return
        
    log.warning(f"{log_action.title()}ing failed file to: {failed_dir / source_file.name}")
        
    try:
        failed_dir.mkdir(parents=True, exist_ok=True)
        if move:
            shutil.move(source_file, failed_dir / source_file.name)
        else:
            shutil.copy2(source_file, failed_dir / source_file.name)
    except OSError as e:
        log.error(f"Failed to {action} file to failed folder: {e}")
