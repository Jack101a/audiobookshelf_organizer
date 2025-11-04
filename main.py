import argparse
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter

# Local project imports
from config_loader import load_config, get_config_value
from logger import setup_logging
from utils import (
    load_asin_map, trigger_abs_rescan,
    find_audio_files_to_process, load_processed_log, append_to_processed_log
)
from audible_client import AudibleClient
from file_manager import (
    organize_audio_file, move_to_failed_folder, create_book_structure
)
from metadata_writer import write_metadata_files
import tag_reader
# We are on the V2 (Audible-Only) logic
# from google_books_client import get_google_books_match 

log = logging.getLogger("main")

# --- Globals & Regex ---
FILENAME_KEEP_WORDS_RE = re.compile(
    r"\b(book|part|bk|pt|act)\b[ \-]*(\d+|[IVXLCDM]+)\b", re.IGNORECASE
)
FILENAME_CLEAN_RE = re.compile(r"[_\-.]+")
ASIN_IN_FILENAME_RE = re.compile(r'\b(B0[0-9A-Z]{8})\b', re.IGNORECASE)


# --- Helper Function Definitions ---

def setup_argparse() -> argparse.ArgumentParser:
    # ... (This function is unchanged) ...
    parser = argparse.ArgumentParser(
        description="Organize audiobook files using Audible metadata for Audiobookshelf."
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        required=False,
        help="Input directory containing audiobook files."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output directory for the organized library. (Overrides config)"
    )
    parser.add_argument(
        "-a", "--asins",
        type=str,
        default=None,
        help="Path to a .json or .csv file mapping filenames to ASINs."
    )
    parser.add_argument(
        "-m", "--move",
        action="store_true",
        help="Move files instead of copying. (Overrides config)"
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default="config.json",
        help="Path to the configuration file."
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Simulate actions. Use --no-dry-run to force execution. (Overrides config)"
    )
    parser.add_argument(
        "--rescan",
        action="store_true",
        help="Trigger an Audiobookshelf library rescan after processing."
    )
    parser.add_argument(
        "--asin",
        type=str,
        default=None,
        dest="asin_list",
        help="A comma-separated list of ASINs. If used, the script will fetch metadata, create folders, and exit."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable detailed DEBUG logging."
    )
    group.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Disable all logging except ERROR messages."
    )
    return parser

def clean_filename_for_search(filename: str) -> str:
    # ... (This function is unchanged) ...
    base_name = Path(filename).stem
    series_parts_matches = FILENAME_KEEP_WORDS_RE.findall(base_name)
    series_parts = " ".join([" ".join(match) for match in series_parts_matches])
    cleaned = FILENAME_CLEAN_RE.sub(" ", base_name)
    cleaned = FILENAME_KEEP_WORDS_RE.sub("", cleaned)
    final_search = f"{cleaned} {series_parts}".strip()
    return re.sub(r"\s+", " ", final_search)

def apply_formatting_rules(
    metadata: Dict[str, Any], 
    config: Dict[str, Any]
) -> Dict[str, Any]:
    # ... (This function is unchanged) ...
    fmt_cfg = config.get("formatting", {})
    delimiter = fmt_cfg.get("multi_value_delimiter", " & ")
    authors: List[str] = metadata.get("authors", [])
    narrators: List[str] = metadata.get("narrators", [])
    release_date: Optional[str] = metadata.get("release_date")
    formatted = metadata.copy() 
    if fmt_cfg.get("use_full_release_date_as_year", False):
        formatted["formatted_year"] = release_date
    else:
        formatted["formatted_year"] = metadata.get("year")
    if fmt_cfg.get("single_album_artist", False) and authors:
        formatted["formatted_album_artist"] = authors[0]
        formatted["formatted_album_artists_list"] = delimiter.join(authors)
    else:
        formatted["formatted_album_artist"] = delimiter.join(authors)
        formatted["formatted_album_artists_list"] = None
    artist_parts = [formatted["formatted_album_artist"]]
    if fmt_cfg.get("narrator_in_artist_field", True) and narrators:
        artist_parts.append(delimiter.join(narrators))
    formatted["formatted_artist"] = " & ".join(filter(None, artist_parts))
    formatted["formatted_narrator"] = delimiter.join(narrators)
    return formatted

# --- NEW: Main Logic Function ---
# All the logic from main() is moved into this new function
# This is what our API server will call
def run_scan(
    input_dir: str,
    output_dir: str,
    asin_map_path: Optional[str] = None,
    move_files: bool = False,
    dry_run: bool = False,
    do_rescan: bool = False,
    config_path: str = "config.json"
) -> Dict[str, int]:
    
    # --- 1. Load Config and Set Up Logging ---
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        log.error(f"Error: Config file {config_path} not found.")
        return {"processed": 0, "failed": 0}

    # Get settings from config, but override with function args
    create_opf = get_config_value(config, "organizer.create_opf", True)
    min_file_size_mb = get_config_value(config, "organizer.min_file_size_mb", 80)

    # --- 2. Initialize Clients ---
    try:
        client = AudibleClient(config)
    except Exception as e:
        log.error(f"Failed to initialize Audible client: {e}")
        return {"processed": 0, "failed": 0}

    output_path = Path(output_dir)
    asin_map = load_asin_map(asin_map_path)
    input_path = Path(input_dir)
    log.info("Audiobookshelf Organizer - Starting Scan")

    if dry_run:
        log.info("--- DRY RUN ENABLED --- No files will be moved or written.")

    if not input_path.exists():
        log.error(f"Input path does not exist: {input_path}")
        return {"processed": 0, "failed": 0}

    processed_log_dict = load_processed_log(output_path)
    book_items = find_audio_files_to_process(str(input_path), processed_log_dict, min_file_size_mb)
    
    if not book_items:
        log.warning(f"No new audio files (>= {min_file_size_mb}MB) found in {input_path}. Exiting.")
        return {"processed": 0, "failed": 0}

    # --- 3. Process Files (Waterfall Logic) ---
    processed_count = 0
    failed_count = 0
    
    for item_path in book_items:
        log.info(f"--- Processing: {item_path.name} ---")
        best_asin: Optional[str] = None
        tags = {}
        
        # 1. ASIN Map
        if item_path.name in asin_map:
            best_asin = asin_map[item_path.name]
            log.info(f"Found match in ASIN map (Priority 1): {best_asin}")

        # 2. ID3/Filename ASIN
        if not best_asin:
            tags = tag_reader.read_tags(str(item_path))
            id3_asin = tags.get("asin")
            if id3_asin:
                log.info(f"Found ASIN in ID3 tag (Priority 2): {id3_asin}")
                best_asin = id3_asin
            else:
                filename_match = ASIN_IN_FILENAME_RE.search(item_path.name)
                if filename_match:
                    best_asin = filename_match.group(1)
                    log.info(f"Found ASIN in filename (Priority 2): {best_asin}")
        
        # 3. ID3 Title/Author Search
        if not best_asin:
            if not tags: tags = tag_reader.read_tags(str(item_path))
            if tags.get("title") and tags.get("author"):
                search_term = f"{tags['author']} {tags['title']}"
                log.info(f"Searching by ID3 tags (Priority 3): {search_term}")
                results = client.search_by_keywords(search_term, num_results=1)
                if results:
                    best_asin = results[0].get("asin")
                    log.info(f"Audible match found from ID3 tags: {best_asin}")

        # 4. Filename Search
        if not best_asin:
            parent_folder_name = item_path.parent.name
            file_name = item_path.name
            if item_path.parent == input_path:
                combined_search_string = file_name
            else:
                combined_search_string = f"{parent_folder_name} {file_name}"
            search_term = clean_filename_for_search(combined_search_string)
            log.info(f"Searching by filename (Priority 4): {search_term}")
            results = client.search_by_keywords(search_term, num_results=1)
            if results:
                best_asin = results[0].get("asin")
                log.info(f"Audible match found from filename: {best_asin}")

        # --- Process or Final Fail ---
        if not best_asin:
            log.warning(f"All 4 search methods failed for {item_path.name}. Moving to __FAILED_TO_PROCESS__.")
            move_to_failed_folder(item_path, output_path, dry_run, move_files)
            failed_count += 1
            continue
        
        try:
            raw_metadata = client.get_metadata_by_asin(best_asin)
            if not raw_metadata or not raw_metadata.get("title"):
                log.warning(f"Got ASIN {best_asin} but failed to fetch metadata or title is missing. Moving to __FAILED_TO_PROCESS__.")
                move_to_failed_folder(item_path, output_path, dry_run, move_files)
                failed_count += 1
                continue
            
            metadata = apply_formatting_rules(raw_metadata, config)
            
            target_folder = organize_audio_file(
                source_file=item_path,
                output_dir=output_path,
                metadata=metadata,
                config=config,
                dry_run=dry_run,
                move=move_files
            )
            
            if not target_folder:
                log.error(f"Failed to organize item {item_path.name}. Moving to __FAILED_TO_PROCESS__.")
                move_to_failed_folder(item_path, output_path, dry_run, move_files)
                failed_count += 1
                continue

            write_metadata_files(
                metadata=metadata,
                folder_path=target_folder,
                dry_run=dry_run,
                create_opf=create_opf
            )
            
            client.download_cover(
                cover_url=metadata.get("cover_url"),
                save_path=target_folder / "cover.jpg",
                dry_run=dry_run
            )
            
            if not dry_run:
                append_to_processed_log(output_path, str(item_path), metadata, processed_log_dict)
            
            processed_count += 1
            
        except Exception as e:
            log.error(f"Unhandled exception while processing {item_path.name} with ASIN {best_asin}: {e}", exc_info=True)
            move_to_failed_folder(item_path, output_path, dry_run, move_files)
            failed_count += 1

    # --- 4. Final Summary & Rescan ---
    log.info("--- Processing Complete ---")
    log.info(f"Successfully processed: {processed_count}")
    log.info(f"Failed to process:     {failed_count}")
    
    if do_rescan:
        trigger_abs_rescan(config, dry_run=dry_run)
        
    return {"processed": processed_count, "failed": failed_count}

# --- This function runs if you call `python3 main.py` ---
def main_cli():
    parser = setup_argparse()
    args = parser.parse_args()

    # --- 1. Load Config and Set Up Logging ---
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Config file {args.config} not found.")
        return

    is_verbose = args.verbose or get_config_value(config, "organizer.verbose", False)
    if args.dry_run is not None:
        is_dry_run = args.dry_run
    else:
        is_dry_run = get_config_value(config, "organizer.dry_run", True)
    output_dir = args.output or get_config_value(config, "organizer.default_output_dir", "./organized_library")
    move_files = args.move or get_config_value(config, "organizer.move_files", False)
    
    # Setup logging for the CLI
    setup_logging(verbose=is_verbose, quiet=args.quiet)

    # --- 2. Initialize Clients ---
    try:
        client = AudibleClient(config)
    except Exception as e:
        log.error(f"Failed to initialize Audible client: {e}")
        return

    output_path = Path(output_dir)

    # --- ASIN-Only Mode ---
    if args.asin_list:
        log.info("--- Create Folders from ASINs Mode ---")
        create_opf = get_config_value(config, "organizer.create_opf", True)
        asins = [asin.strip() for asin in args.asin_list.split(',') if asin.strip()]
        if not asins:
            log.error("No valid ASINs provided to --asin.")
            return

        for asin in asins:
            log.info(f"--- Processing ASIN: {asin} ---")
            raw_metadata = client.get_metadata_by_asin(asin)
            if not raw_metadata or not raw_metadata.get("title"):
                log.error(f"Failed to fetch metadata (or title is missing) for ASIN {asin}. Skipping.")
                continue
            metadata = apply_formatting_rules(raw_metadata, config)
            target_folder = create_book_structure(
                output_path, metadata, config, is_dry_run
            )
            if not target_folder:
                log.error(f"Failed to create folder for ASIN {asin}.")
                continue
            write_metadata_files(
                metadata=metadata,
                folder_path=target_folder,
                dry_run=is_dry_run,
                create_opf=create_opf
            )
            client.download_cover(
                cover_url=metadata.get("cover_url"),
                save_path=target_folder / "cover.jpg",
                dry_run=is_dry_run
            )
        log.info("--- Folder creation complete. ---")
        return

    # --- STANDARD MODE ---
    if not args.input:
        log.error("Missing required argument: -i/--input. (This is required when not using --asin)")
        return
    
    # Call the main logic function
    run_scan(
        input_dir=args.input,
        output_dir=output_dir,
        asin_map_path=args.asins,
        move_files=move_files,
        dry_run=is_dry_run,
        do_rescan=args.rescan,
        config_path=args.config
    )

# --- Script Entry Point ---
if __name__ == "__main__":
    main_cli()
