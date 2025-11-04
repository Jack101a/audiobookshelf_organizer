import json
import logging
from pathlib import Path
from typing import Dict, Any, List

log = logging.getLogger(__name__)

# --- XML Helper ---

def _escape(s: Any) -> str:
    """Escapes XML special characters."""
    s = str(s) if s is not None else ""
    if not s: 
        return ""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace("\"", "&quot;")
    return s

# --- File Write Helper ---

def _safe_write(path: Path, content: str) -> None:
    """Helper to safely write text files."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        log.debug(f"Wrote {path}")
    except IOError as e:
        log.error(f"Failed to write {path}: {e}")

# --- Main Function ---

def write_metadata_files(
    metadata: Dict[str, Any],
    folder_path: Path,
    dry_run: bool = False,
    create_opf: bool = False
) -> None:
    """
    Writes all Audiobookshelf-compatible metadata files to the target folder
    using the provided FORMATTED metadata dictionary.
    """
    
    if not folder_path.exists():
        if dry_run:
            log.info(f"[DRY RUN] Would create directory: {folder_path}")
        else:
            log.info(f"Creating directory: {folder_path}")
            try:
                folder_path.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                log.error(f"Failed to create directory {folder_path}: {e}")
                return

    # --- Write OPF (if enabled) ---
    if create_opf:
        # If we create a full OPF, it contains all metadata.
        # We don't need the redundant .txt files.
        log.info("create_opf is True. Writing comprehensive book.opf...")
        write_opf(metadata, folder_path, dry_run)
    else:
        # --- Fallback: Write desc.txt ---
        desc_path = folder_path / "desc.txt"
        description = metadata.get("description")
        if description:
            if dry_run:
                log.info(f"[DRY RUN] Would write description to {desc_path}")
            else:
                _safe_write(desc_path, description)

        # --- Fallback: Write reader.txt ---
        reader_path = folder_path / "reader.txt"
        # Use 'formatted_narrator' which is likely a comma-separated string
        reader_str = metadata.get("formatted_narrator") 
        if reader_str:
            if dry_run:
                log.info(f"[DRY RUN] Would write narrators to {reader_path}")
            else:
                _safe_write(reader_path, reader_str)

    # --- Write metadata.json (raw API response) ---
    # This is useful for reference.
    # We assume the 'metadata' dict contains the raw data under 'raw_json'
    raw_json_path = folder_path / "metadata.json"
    raw_json_data = metadata.get("raw_json") 
    if raw_json_data:
        if dry_run:
            log.info(f"[DRY RUN] Would write raw API JSON to {raw_json_path}")
        else:
            try:
                # Dump the raw_json_data, which is already a dict/list
                with open(raw_json_path, 'w', encoding='utf-8') as f:
                    json.dump(raw_json_data, f, indent=2)
                log.debug(f"Wrote {raw_json_path}")
            except (IOError, TypeError) as e:
                log.error(f"Failed to write JSON {raw_json_path}: {e}")

# --- Comprehensive OPF Writer ---

def write_opf(
    metadata: Dict[str, Any],
    folder_path: Path,
    dry_run: bool = False
) -> None:
    """
    Writes a COMPREHENSIVE 'book.opf' file based on EPUB 3 standard,
    using FORMATTED metadata.
    """
    opf_path = folder_path / "book.opf"
    if dry_run:
        log.info(f"[DRY RUN] Would write comprehensive OPF file to {opf_path}")
        return

    # --- 1. Get All Metadata Values ---
    # These keys come from your main.py/apply_formatting_rules
    title = _escape(metadata.get("title", "Unknown Title"))
    
    # Authors (Creators)
    authors: List[str] = metadata.get("authors", [])  # Expects a list of names
    
    # Narrators (Contributors/Readers)
    narrators: List[str] = metadata.get("narrators", []) # Expects a list of names
    
    # Description
    description = _escape(metadata.get("description", ""))
    
    # Identifiers
    asin = metadata.get("asin", "")
    isbn = metadata.get("isbn", "") # Assumes this key exists if ISBN is found
    book_id_val = f"urn:asin:{asin}" if asin else (f"urn:isbn:{isbn}" if isbn else "urn:uuid:PLACEHOLDER-UUID")
    
    # Dates
    release_date = metadata.get("release_date", "") # e.g., "2023-10-27"
    publish_year = metadata.get("formatted_year", release_date.split('-')[0] if release_date else "")
    
    # Publisher (Studio)
    publisher = _escape(metadata.get("publisher", ""))
    
    language = _escape(metadata.get("language", "en"))
    
    # Genres (Subjects)
    genres: List[str] = metadata.get("genres", []) # Expects a list of strings
    
    # Series
    series = _escape(metadata.get("series", ""))
    # Use robust 'or' check for series position
    series_pos = _escape(metadata.get("series_part") or metadata.get("series_position") or "")
    
    # Duration
    runtime_sec = metadata.get("runtime", 0) # Expects runtime in seconds

    # --- 2. Build XML Tag Components ---
    meta_lines = []

    # ---Identifiers---
    meta_lines.append(f'    <dc:identifier id="BookId">{book_id_val}</dc:identifier>')
    if isbn:
        meta_lines.append(f'    <dc:identifier opf:scheme="ISBN">{_escape(isbn)}</dc:identifier>')
    if asin:
        meta_lines.append(f'    <dc:identifier opf:scheme="ASIN">{_escape(asin)}</dc:identifier>')

    # ---Title & Language---
    meta_lines.append(f'    <dc:title>{title}</dc:title>')
    meta_lines.append(f'    <dc:language>{language}</dc:language>')

    # ---Creators (Authors)---
    if not authors:
        meta_lines.append('    <dc:creator opf:role="aut">Unknown Author</dc:creator>')
    for name in authors:
        meta_lines.append(f'    <dc:creator opf:role="aut">{_escape(name)}</dc:creator>')

    # ---Contributors (Narrators / Readers)---
    for name in narrators:
        # 'nrt' is the standard machine-readable code for "narrator"
        meta_lines.append(f'    <dc:contributor opf:role="nrt">{_escape(name)}</dc:contributor>')

    # ---Publisher (Studio)---
    if publisher:
        meta_lines.append(f'    <dc:publisher>{publisher}</dc:publisher>')

    # ---Dates---
    if release_date:
        # Use the full date if available
        meta_lines.append(f'    <dc:date>{release_date}</dc:date>')
    elif publish_year:
        # Fallback to just the year
        meta_lines.append(f'    <dc:date>{publish_year}</dc:date>')

    # ---Description---
    if description:
        meta_lines.append(f'    <dc:description>{description}</dc:description>')
    
    # ---Subjects (Genres)---
    for genre in genres:
        meta_lines.append(f'    <dc:subject>{_escape(genre)}</dc:subject>')

    # ---Cover---
    meta_lines.append('    <meta name="cover" content="cover-image" />')

    # ---Series Info---
    if series:
        meta_lines.append(f'    <meta property="schema:series">{series}</meta>')
        if series_pos:
            meta_lines.append(f'    <meta property="schema:seriesPosition">{series_pos}</meta>')
            
    # ---Duration---
    if runtime_sec:
        # e.g., "37835" (for 10h 30m 35s)
        meta_lines.append(f'    <meta property="media:duration">{runtime_sec}</meta>')

    # --- 3. Assemble Final XML ---
    final_meta_content = "\n".join(meta_lines)

    # Note the added xmlns:schema="http://schema.org/" for series tags
    xml_content = f"""<?xml version='1.0' encoding='utf-8'?>
<package xmlns="http://www.idpf.org/2007/opf"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns:opf="http://www.idpf.org/2007/opf"
         xmlns:schema="http://schema.org/"
         unique-identifier="BookId" version="3.0">
  <metadata>
{final_meta_content}
  </metadata>
  <manifest>
    <item id="cover-image" href="cover.jpg" media-type="image/jpeg" properties="cover-image" />
    
    </manifest>
  <spine toc="ncx">
    </spine>
</package>
"""
    _safe_write(opf_path, xml_content)
