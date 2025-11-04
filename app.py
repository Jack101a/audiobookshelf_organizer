import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import time
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging
import base64

# --- Project Imports ---
try:
    from config_loader import load_config, get_config_value
    from logger import setup_logging
    from utils import (
        load_asin_map, trigger_abs_rescan,
        find_audio_files_to_process, load_processed_log, append_to_processed_log,
        PROCESSED_LOG_NAME
    )
    from audible_client import AudibleClient
    from file_manager import organize_audio_file, move_to_failed_folder, create_book_structure
    from metadata_writer import write_metadata_files
    import tag_reader
    from main import apply_formatting_rules, clean_filename_for_search, ASIN_IN_FILENAME_RE
except ImportError as e:
    st.error(f"FATAL ERROR: Could not import project files. Make sure 'app.py' is in the same folder as 'main.py', 'utils.py', etc. Error: {e}")
    st.stop()

# --- App Setup ---
st.set_page_config(page_title="Audiobook Organizer", layout="centered")

# --- Styling (from your mockup & suggestions) ---
DARK_BG = "#0e1117"
ACCENT = "#2bb6ad"  # teal
TEXT = "#FFFFFF"
CARD = "#111316"

st.markdown(f"""
<style>
    /* Base */
    .stApp {{ background-color: {DARK_BG}; color: {TEXT}; }}
    .main {{ padding: 1rem 1.5rem; }}
    h1 {{ color: {TEXT}; text-align: center; }}
    h3 {{ font-weight: 600; }}
    
    /* Sections */
    .section-title {{ font-size:20px; font-weight:600; margin-top:1.5rem; margin-bottom: 0.5rem; }}
    .card {{ 
        background: {CARD}; 
        border-radius:12px; 
        padding:16px; 
        box-shadow: 0 4px 12px rgba(0,0,0,0.6); 
        border:1px solid rgba(255,255,255,0.03); 
    }}
    .file-card {{ 
        background: transparent; 
        border:1px solid rgba(255,255,255,0.1); 
        padding:14px; 
        border-radius:10px; 
        margin-bottom:12px; 
    }}
    
    /* Logs */
    .logbox {{ 
        background: #050705; 
        border-radius:8px; 
        padding:8px; 
        color: #58ff6b; 
        font-family: monospace; 
        height: 300px;
        overflow-y: auto;
        white-space: pre-wrap;
        scroll-behavior: smooth;
    }}
    .logbox::-webkit-scrollbar {{ width: 6px; }}
    
    /* Utils */
    .small-muted {{ color: rgba(255,255,255,0.55); font-size: 13px; }}
    hr {{ border-color:rgba(255,255,255,0.04); }}
</style>
""", unsafe_allow_html=True)


# --- Logger Setup ---
class StreamlitLogHandler(logging.Handler):
    """A logging handler that writes to st.session_state.log_lines."""
    def __init__(self):
        super().__init__()
        st.session_state.setdefault("log_lines", ["[12:00] Log initialized."])
            
    def emit(self, record):
        msg = self.format(record)
        st.session_state.log_lines.append(msg)
        st.session_state.log_lines = st.session_state.log_lines[-50:] # Keep last 50

# Initialize logger
if 'log_handler_initialized' not in st.session_state:
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    setup_logging(verbose=True) 
    root_logger.addHandler(StreamlitLogHandler()) 
    root_logger.setLevel(logging.INFO)
    st.session_state.log_handler_initialized = True
    
log = logging.getLogger("app_v12")

# --- Initialize State (Using setdefault) ---
st.session_state.setdefault("results", [])
st.session_state.setdefault("busy", False)
st.session_state.setdefault("operation_choice", "Copy") # Default to Copy

if 'config' not in st.session_state:
    try:
        st.session_state.config = load_config("config.json")
    except FileNotFoundError:
        st.error("config.json not found! Please create one.")
        st.stop()
        
if 'client' not in st.session_state:
    try:
        st.session_state.client = AudibleClient(st.session_state.config)
    except Exception as e:
        st.error(f"Failed to initialize Audible Client: {e}")
        st.stop()

# --- Helper Utilities (from mockup) ---
def make_placeholder_cover(size=156, title_text=None) -> str:
    """Create a simple placeholder cover image using PIL and return as b64 data URI."""
    img = Image.new("RGB", (size, size), (40, 40, 44))
    d = ImageDraw.Draw(img)
    d.rectangle([(12, size - 40), (size - 12, size - 12)], outline=(100, 100, 106))
    if title_text:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 12)
        except Exception:
            font = ImageFont.load_default()
        text = (title_text[:20] + "..") if len(title_text or "") > 20 else (title_text or "")
        d.text((10, 8), text, fill=(210, 210, 210), font=font)
    
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    b64_data = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{b64_data}"

# --- Real Scan Logic ---
def run_real_scan(input_dir, output_dir, min_size):
    """Replaces fake_scan() with our real V2 logic."""
    log.info(f"Scanning {input_dir}...")
    try:
        output_path = Path(output_dir)
        processed_log = load_processed_log(output_path)
        found_files = find_audio_files_to_process(input_dir, processed_log, min_size)
        
        if not found_files:
            log.info("No new files found to process.")
            st.session_state.results = []
            return

        found_files.sort(key=lambda p: p.name.lower()) # Sort alphabetically
        
        log.info(f"Found {len(found_files)} new files. Scanning local tags...")
        
        file_list_data = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        for i, file_path in enumerate(found_files):
            progress_text.text(f"Scanning local file: {file_path.name}")
            progress_bar.progress((i + 1) / len(found_files))
            
            tags = tag_reader.read_tags(str(file_path))
            
            cover_data_uri = tag_reader.get_embedded_cover_b64(str(file_path))
            if not cover_data_uri:
                cover_data_uri = make_placeholder_cover(156, title_text=file_path.stem)

            guess_asin = tags.get("asin") or ""
            if not guess_asin:
                match = ASIN_IN_FILENAME_RE.search(file_path.name)
                if match:
                    guess_asin = match.group(1)
            
            file_list_data.append({
                "file_name": file_path.name,
                "full_path": str(file_path),
                "original": {
                    "cover_data_uri": cover_data_uri,
                    "title": tags.get("title") or file_path.stem,
                    "author": tags.get("author") or "",
                    "asin": guess_asin,
                },
                "audible": {
                    "cover_data_uri": None,
                    "title": "", "author": "", "series": "",
                    "book_number": "", "year": "", "asin": "",
                    "raw_metadata": None,
                },
            })
            
        progress_text.empty()
        progress_bar.empty()
        log.info(f"Scan complete. Found {len(file_list_data)} files.")
        st.session_state.results = file_list_data

    except Exception as e:
        log.error(f"Error during scan: {e}", exc_info=True)
        st.error(f"Error during scan: {e}")


# --- Header ---
st.markdown("<h1>🎧 Audiobook Organizer</h1>", unsafe_allow_html=True)
st.markdown("<div class='small-muted' style='text-align:center;'>Smartly tag and organize your audiobooks using Audible data</div>", unsafe_allow_html=True)
st.markdown("<hr style='border-color:rgba(255,255,255,0.04)'/>", unsafe_allow_html=True)

# --- Settings ---
st.markdown("<div class='section-title'>Settings</div>", unsafe_allow_html=True)
with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    cfg = st.session_state.config.get("organizer", {})
    
    col1, col2 = st.columns(2)
    with col1:
        input_folder = st.text_input(
            "Input Source Folder", 
            value=cfg.get("default_input_dir", "/srv/media/audiobooks/new"), 
            key="input_dir"
        )
    with col2:
        output_folder = st.text_input(
            "Output Library Folder", 
            value=cfg.get("default_output_dir", "/srv/media/audiobooks"), 
            key="output_dir"
        )
    
    if st.button("Test Paths", key="test_paths", help="Check if paths exist"):
        in_path = Path(st.session_state.input_dir)
        out_path = Path(st.session_state.output_dir)
        if not in_path.is_dir():
            st.error(f"Input path not found: {in_path}")
        else:
            st.success(f"Input path OK: {in_path}")
        if not out_path.is_dir():
            st.warning(f"Output path not found: {out_path} (Will be created)")
        else:
            st.success(f"Output path OK: {out_path}")
    
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1.5, 1, 1])
    with col1:
        op_mode = st.radio(
            "Operation Mode", 
            options=["Copy", "Move"], 
            index=0, 
            horizontal=True, 
            key="operation_choice"
        )
    with col2:
        min_size = st.number_input(
            "Minimum File Size (MB)", 
            min_value=1, 
            value=cfg.get("min_file_size_mb", 80), 
            key="min_size"
        )
    with col3:
        create_opf = st.checkbox(
            "Create .opf File", 
            value=cfg.get("create_opf", True),
            key="create_opf"
        )
    
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    
    # --- Scan Button ---
    if st.button("🔍 Scan for Audiobooks", key="scan_btn", use_container_width=True, disabled=st.session_state.busy):
        st.session_state.busy = True
        try:
            with st.spinner("Scanning..."):
                run_real_scan(st.session_state.input_dir, st.session_state.output_dir, st.session_state.min_size)
        finally:
            st.session_state.busy = False
            st.rerun() 

    st.markdown('</div>', unsafe_allow_html=True)

# --- Scan Results (Your New UI) ---
st.markdown("<div class='section-title'>Scan Results</div>", unsafe_allow_html=True)

results_container = st.container()
with results_container:
    if not st.session_state.results:
        st.info("No scan results yet — click 'Scan for Audiobooks' to begin.")
    else:
        st.info(f"💡 Found {len(st.session_state.results)} files. Click 'Fetch Audible Data' to get matches.")
        
        # --- Fetch Button ---
        if st.button("🌐 Fetch Audible Data for All Files", use_container_width=True, disabled=st.session_state.busy):
            st.session_state.busy = True
            try:
                log.info("Starting metadata fetch for all files...")
                progress_text = st.empty()
                progress_bar = st.progress(0)
                
                for i, item in enumerate(st.session_state.results):
                    file_path = Path(item["full_path"])
                    progress_text.text(f"Fetching: {item['file_name']}")
                    progress_bar.progress((i + 1) / len(st.session_state.results))
                    
                    orig_title = st.session_state[f"orig_title_{i}"]
                    orig_author = st.session_state[f"orig_author_{i}"]
                    orig_asin = st.session_state[f"orig_asin_{i}"]
                    
                    best_asin = None
                    
                    if orig_asin:
                        best_asin = orig_asin
                        log.info(f"Using manual ASIN for {item['file_name']}: {best_asin}")
                    
                    if not best_asin:
                        tags = tag_reader.read_tags(str(file_path))
                        if tags.get("asin"):
                            best_asin = tags["asin"]
                            log.info(f"Found ASIN in ID3 tag: {best_asin}")
                        else:
                            match = ASIN_IN_FILENAME_RE.search(item['file_name'])
                            if match:
                                best_asin = match.group(1)
                                log.info(f"Found ASIN in filename: {best_asin}")

                    if not best_asin and orig_title and orig_author:
                        search_term = f"{orig_author} {orig_title}"
                        log.info(f"Searching by edited tags: {search_term}")
                        results = st.session_state.client.search_by_keywords(search_term, num_results=1)
                        if results: best_asin = results[0].get("asin")
                    
                    if not best_asin:
                        search_term = clean_filename_for_search(f"{file_path.parent.name} {item['file_name']}")
                        log.info(f"Searching by filename: {search_term}")
                        results = st.session_state.client.search_by_keywords(search_term, num_results=1)
                        if results: best_asin = results[0].get("asin")
                    
                    if best_asin:
                        raw_metadata = st.session_state.client.get_metadata_by_asin(best_asin)
                        if raw_metadata and raw_metadata.get("title"):
                            metadata = apply_formatting_rules(raw_metadata, st.session_state.config)
                            
                            # --- FIX: Store fetched data in a temp dict ---
                            fetched_data = {
                                "cover_data_uri": metadata.get("cover_url"),
                                "title": metadata.get("title"),
                                "author": metadata.get("formatted_album_artist"),
                                "series": metadata.get("series") or "",
                                "book_number": metadata.get("series_part") or "",
                                "year": metadata.get("formatted_year") or "",
                                "asin": metadata.get("asin"),
                                "raw_metadata": raw_metadata
                            }

                            # 1. Update the main data store (like you already do)
                            item["audible"].update(fetched_data)
                            
                            # 2. ALSO update the widget's state directly using their keys
                            # This prevents the stale widget state from overwriting the fetched data on redraw
                            st.session_state[f"aud_title_{i}"] = fetched_data["title"]
                            st.session_state[f"aud_author_{i}"] = fetched_data["author"]
                            st.session_state[f"aud_series_{i}"] = fetched_data["series"]
                            st.session_state[f"aud_book_{i}"] = fetched_data["book_number"]
                            st.session_state[f"aud_year_{i}"] = fetched_data["year"]
                            st.session_state[f"aud_asin_{i}"] = fetched_data["asin"]
                            # --- END OF FIX ---
                        else:
                            log.warning(f"Fetch failed for {item['file_name']}")
                    else:
                        log.warning(f"No ASIN match found for {item['file_name']}")

                progress_text.empty()
                progress_bar.empty()
                log.info("Metadata fetch complete. Review and edit any matches, then click Submit.")
            finally:
                st.session_state.busy = False
                st.rerun() 
        
        # --- Display the Cards ---
        for i, item in enumerate(st.session_state.results):
            st.markdown(f'<div class="file-card card">', unsafe_allow_html=True)
            left_col, right_col = st.columns([1, 1])
            
            with left_col:
                st.markdown("<strong>🧩 Original File Info (Editable)</strong>", unsafe_allow_html=True)
                st.image(item['original']['cover_data_uri'], width=156)
                st.caption(f"Original: {item['file_name']}")
                
                title_edit = st.text_input("Title (Guess)", value=item['original']['title'], key=f"orig_title_{i}")
                author_edit = st.text_input("Author (Guess)", value=item['original']['author'], key=f"orig_author_{i}")
                asin_edit = st.text_input("ASIN (Override)", value=item['original']['asin'], key=f"orig_asin_{i}")

                st.session_state.results[i]['original']['title'] = title_edit
                st.session_state.results[i]['original']['author'] = author_edit
                st.session_state.results[i]['original']['asin'] = asin_edit

            with right_col:
                st.markdown("<strong>🌐 Audible Match (Editable)</strong>", unsafe_allow_html=True)
                
                cover_url = item['audible']['cover_data_uri']
                if not cover_url:
                    cover_url = make_placeholder_cover(156, title_text="Audible")
                
                # --- THIS IS THE FIX ---
                # The line was: st.image(cover_url, width=1Example of...)
                # It is now fixed:
                st.image(cover_url, width=156)
                # --- END OF FIX ---
                
                a_title = st.text_input("Audible Title", value=item['audible']['title'], key=f"aud_title_{i}")
                a_author = st.text_input("Audible Author", value=item['audible']['author'], key=f"aud_author_{i}")
                a_series = st.text_input("Series", value=item['audible']['series'], key=f"aud_series_{i}")
                a_booknum = st.text_input("Book #", value=item['audible']['book_number'], key=f"aud_book_{i}")
                a_year = st.text_input("Year", value=item['audible']['year'], key=f"aud_year_{i}")
                a_asin = st.text_input("ASIN", value=item['audible']['asin'], key=f"aud_asin_{i}")

                st.session_state.results[i]['audible'].update({
                    'title': a_title, 'author': a_author, 'series': a_series,
                    'book_number': a_booknum, 'year': a_year, 'asin': a_asin,
                })

            st.markdown('</div>', unsafe_allow_html=True)

# --- Finalize and Organize ---
st.divider()
st.markdown("<div class='section-title'>Finalize and Organize</div>", unsafe_allow_html=True)
with st.container():
    confirm = st.checkbox("I confirm I've reviewed all matched data before proceeding.")
    submit_btn = st.button("🚚 Submit and Organize Files", disabled=(not confirm) or st.session_state.busy, use_container_width=True)
    
    if submit_btn:
        st.session_state.busy = True
        try:
            op_choice = st.session_state.operation_choice
            is_move = (op_choice == "Move")
            is_dry_run = False
            
            log.info(f"--- STARTING FINAL {op_choice.upper()} ---")
            
            files_to_process = [f for f in st.session_state.results if f['audible']['asin']]
            if not files_to_process:
                st.error("No files have a matched ASIN. Please fetch or enter data.")
                st.session_state.busy = False
                st.stop()
            
            progress_text = st.empty()
            progress_bar = st.progress(0)
            
            output_path = Path(st.session_state.output_dir)
            processed_log_dict = load_processed_log(output_path)
            
            processed_count = 0
            failed_count = 0
            
            for i, item in enumerate(files_to_process):
                file_path = Path(item["full_path"])
                progress_text.text(f"Processing: {file_path.name}")
                progress_bar.progress((i + 1) / len(files_to_process))
                
                try:
                    raw_metadata = item['audible'].get('raw_metadata')
                    if not raw_metadata:
                        raw_metadata = st.session_state.client.get_metadata_by_asin(item['audible']['asin'])
                    
                    if not raw_metadata or not raw_metadata.get("title"):
                        log.error(f"Failed to get metadata for {item['audible']['asin']} on final submit. Skipping.")
                        failed_count += 1
                        continue
                    
                    metadata = apply_formatting_rules(raw_metadata, st.session_state.config)
                    
                    metadata["title"] = st.session_state[f"aud_title_{i}"]
                    metadata["formatted_album_artist"] = st.session_state[f"aud_author_{i}"]
                    metadata["series"] = st.session_state[f"aud_series_{i}"]
                    metadata["series_part"] = st.session_state[f"aud_book_{i}"]
                    metadata["formatted_year"] = st.session_state[f"aud_year_{i}"]
                    metadata["asin"] = st.session_state[f"aud_asin_{i}"]
                    
                    target_folder = organize_audio_file(
                        source_file=file_path,
                        output_dir=output_path,
                        metadata=metadata,
                        config=st.session_state.config,
                        dry_run=is_dry_run,
                        move=is_move
                    )
                    
                    if not target_folder:
                        log.error(f"Failed to organize item {file_path.name}.")
                        failed_count += 1
                        continue

                    write_metadata_files(
                        metadata=metadata,
                        folder_path=target_folder,
                        dry_run=is_dry_run,
                        create_opf=st.session_state.create_opf
                    )
                    
                    cover_url_to_download = raw_metadata.get("cover_url")
                    if cover_url_to_download:
                        st.session_state.client.download_cover(
                            cover_url=cover_url_to_download,
                            save_path=target_folder / "cover.jpg",
                            dry_run=is_dry_run
                        )
                    
                    append_to_processed_log(output_path, str(file_path), metadata, processed_log_dict)
                    processed_count += 1

                except Exception as e:
                    log.error(f"Unhandled exception while processing {file_path.name}: {e}", exc_info=True)
                    failed_count += 1
            
            progress_text.empty()
            progress_bar.empty()
            st.success(f"Processing complete! {processed_count} files processed, {failed_count} files failed.")
            st.session_state.results = []
            st.balloons()
            
        finally:
            st.session_state.busy = False
            # We don't rerun here, let the balloons show
            # st.rerun()

# --- Live Log ---
st.divider()
st.markdown("<div class='section-title'>Live Log</div>", unsafe_allow_html=True)
log_box = st.empty()

log_html = "\n".join(st.session_state.log_lines[-50:])
log_html_br = log_html.replace('\n', '<br/>')

# --- FIX IS HERE ---
# Changed class'logbox' to class="logbox"
# Changed id='logbox' to id="logbox"
log_box.markdown(f"""
<div class="logbox" id="logbox">{log_html_br}</div>
<script>
    var logBox = window.parent.document.getElementById('logbox');
    if (logBox) {{
        logBox.scrollTop = logBox.scrollHeight;
    }}
</script>
""", unsafe_allow_html=True)
