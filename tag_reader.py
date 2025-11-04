import mutagen
import logging
from typing import Dict, Optional
from pathlib import Path
import base64

log = logging.getLogger(__name__)

def read_tags(file_path: str) -> Dict[str, Optional[str]]:
    """
    Reads ID3/MP4 tags from an audio file to find ASIN, title, and author.
    """
    tags = {"asin": None, "title": None, "author": None}
    
    try:
        audio_easy = mutagen.File(file_path, easy=True)
        if audio_easy:
            if 'title' in audio_easy:
                tags['title'] = audio_easy['title'][0]
            if 'artist' in audio_easy or 'author' in audio_easy:
                tags['author'] = (audio_easy.get('author') or audio_easy.get('artist'))[0]

        audio_raw = mutagen.File(file_path)
        if not audio_raw:
            return tags

        # --- Hunt for ASIN ---
        asin = None
        if 'TXXX:ASIN' in audio_raw:
            asin = str(audio_raw['TXXX:ASIN'].text[0])
        elif '----:com.apple.iTunes:ASIN' in audio_raw:
            asin = str(audio_raw['----:com.apple.iTunes:ASIN'][0], 'utf-8')
        elif 'COMM::eng' in audio_raw:
            comment = str(audio_raw['COMM::eng'].text[0])
            if "ASIN:" in comment:
                try: asin = comment.split("ASIN:")[1].split()[0].strip()
                except IndexError: pass
        elif '\xa9cmt' in audio_raw:
            comment = str(audio_raw['\xa9cmt'][0])
            if "ASIN:" in comment:
                try: asin = comment.split("ASIN:")[1].split()[0].strip()
                except IndexError: pass
        
        if asin:
            tags['asin'] = asin
            
    except Exception as e:
        log.warning(f"Could not read tags from {Path(file_path).name}: {e}")
    
    return tags

def get_embedded_cover_b64(file_path: str) -> Optional[str]:
    """
    Extracts the embedded cover art and returns it as a base64-encoded
    data URI (e.g., 'data:image/jpeg;base64,...').
    """
    try:
        audio = mutagen.File(file_path)
        if not audio:
            return None

        # MP4 / M4B
        if 'covr' in audio.tags:
            cover_data = audio.tags['covr'][0]
            
            # --- FIX from user log ---
            if cover_data.imageformat == mutagen.mp4.MP4Cover.FORMAT_JPEG:
                mime = "image/jpeg"
            elif cover_data.imageformat == mutagen.mp4.MP4Cover.FORMAT_PNG:
                mime = "image/png"
            else:
                mime = "image/jpeg" # Default
            # --- END OF FIX ---

            b64_data = base64.b64encode(cover_data).decode('utf-8')
            return f"data:{mime};base64,{b64_data}"
        
        # MP3
        elif 'APIC:' in audio.tags:
            cover_data = audio.tags['APIC:'].data
            mime = audio.tags['APIC:'].mime
            b64_data = base64.b64encode(cover_data).decode('utf-8')
            return f"data:{mime};base64,{b64_data}"
            
    except Exception as e:
        log.warning(f"Failed to extract embedded cover from {Path(file_path).name}: {e}")
        
    return None
