import requests
import json
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from utils import format_contributors

log = logging.getLogger(__name__)

# --- URLs from your .src files ---

# From: A&udible API#Audible.com - Search by ASIN.src
# This is the "direct" lookup, which is fast but unreliable.
DIRECT_ASIN_URL_TEMPLATE = (
    "https://api.audible.com/1.0/catalog/products/{asin}"
    "?response_groups=contributors,media,product_desc,product_details,"
    "product_plans,rating,reviews,sample,series"
    "&image_sizes=500,700,1000"
)

# From: A&udible API#Audible.com - Search by Author + Title.src
# This is the "keyword search" lookup, which is very reliable.
KEYWORD_SEARCH_URL_TEMPLATE = (
    "https://api.audible.com/1.0/catalog/products"
    "?response_groups=product_attrs"
    "&image_sizes=100"
    "&num_results=5"
    "&products_sort_by=Relevance"
    "&keywords={keywords}"
)

class AudibleClient:
    """
    Client for interacting with the Audible.com API.
    
    This client fetches metadata based on the URL patterns and field mappings
    defined in the 'audible_api_src/' directory.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config.get("audible", {})
        self.api_base = self.config.get("api_base", "https://api.audible.com")
        self.web_base = self.config.get("web_base", "https://www.audible.com")
        self.locale = self.config.get("locale", "us")
        
        # We'll try to load auth, but we won't crash if it's missing.
        self.auth_data = self._load_auth()
        self.session = self._setup_session()

    def _load_auth(self) -> Optional[Dict[str, Any]]:
        """
        Loads authentication data if it exists. Does not error if missing.
        """
        auth_file_path = self.config.get("auth_file_path")
        if not auth_file_path:
            log.warning("No 'auth_file_path' in config. Proceeding unauthenticated.")
            return None
            
        try:
            with open(auth_file_path, 'r', encoding='utf-8') as f:
                auth_data = json.load(f)
                log.info(f"Successfully loaded auth data from {auth_file_path}")
                return auth_data
        except FileNotFoundError:
            log.error(f"Audible auth file not found at: {auth_file_path}")
            log.error("This is OK for public searches, but may fail.")
            return None
        except json.JSONDecodeError:
            log.error(f"Failed to parse auth file {auth_file_path}. Is it valid JSON?")
            return None

    def _setup_session(self) -> requests.Session:
        """
        Configures the requests session with headers, auth, and retries.
        """
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
        })

        if self.auth_data:
            if "access_token" in self.auth_data:
                token = self.auth_data["access_token"]
                session.headers.update({"Authorization": f"Bearer {token}"})
                log.debug("Configured session with Bearer token.")
            elif isinstance(self.auth_data, dict) and "cookies" in self.auth_data:
                session.cookies.update(self.auth_data["cookies"])
                log.debug("Configured session with cookies.")
            elif isinstance(self.auth_data, list):
                for cookie in self.auth_data:
                    if "name" in cookie and "value" in cookie:
                        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
                log.debug("Configured session with list of cookies.")

        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        session.mount("http://", HTTPAdapter(max_retries=retries))
        session.mount("https://", HTTPAdapter(max_retries=retries))
        
        return session

    def _make_api_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Helper for making API requests."""
        try:
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 401 or response.status_code == 403:
                log.error(f"Authentication failed (HTTP {response.status_code}).")
                log.error("Your auth data may be expired or invalid.")
                return None
            
            # Don't raise for 404, just return None
            if response.status_code == 404:
                log.warning(f"API request returned 404 Not Found: {url}")
                return None
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            log.error(f"HTTP Error for {url}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            log.error(f"Request failed for {url}: {e}")
            return None

    def get_metadata_by_asin(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        Fetches product metadata for a specific ASIN.
        
        NEW LOGIC:
        1. Try the direct ASIN URL (from Search by ASIN.src)
        2. If it fails, fall back to the keyword search URL (from other .src files)
        """
        log.debug(f"Fetching metadata for ASIN: {asin}")
        
        # --- Attempt 1: Direct URL (from A&udible API#Audible.com - Search by ASIN.src) ---
        direct_url = DIRECT_ASIN_URL_TEMPLATE.format(asin=asin)
        
        data = self._make_api_request(direct_url)
        
        if data and "product" in data:
            log.debug("Direct ASIN lookup successful.")
            return self._parse_product_json(data["product"])
        
        # --- Attempt 2: Fallback to Keyword Search ---
        log.warning(f"Direct ASIN lookup failed for {asin}. Falling back to keyword search.")
        
        search_results = self.search_by_keywords(asin, num_results=1)
        
        if not search_results:
            log.error(f"Keyword search for ASIN {asin} also failed. No data found.")
            return None
            
        # We found a match. Now we need its *full* metadata.
        # The search result might be incomplete.
        matched_asin = search_results[0].get("asin")
        if not matched_asin:
            log.error("Keyword search found a product with no ASIN.")
            return None
            
        # If the matched ASIN is what we searched for, get its full data
        if matched_asin == asin:
            log.debug("Keyword search confirmed ASIN. Fetching full product data.")
            direct_url = DIRECT_ASIN_URL_TEMPLATE.format(asin=matched_asin)
            data = self._make_api_request(direct_url)
            
            if data and "product" in data:
                return self._parse_product_json(data["product"])
        
        log.error(f"Keyword search for {asin} returned a different ASIN: {matched_asin}. Failing.")
        return None


    def search_by_keywords(self, keywords: str, num_results: int = 5) -> Optional[List[Dict[str, Any]]]:
        """
        Searches for products by keywords.
        (Based on A&udible API#Audible.com - Search by Author + Title.src)
        """
        log.debug(f"Searching by keywords: {keywords}")
        
        url = KEYWORD_SEARCH_URL_TEMPLATE.format(keywords=keywords)
        params = {"num_results": num_results} # num_results is in params, not URL
        
        data = self._make_api_request(url, params=params)
        
        if data and "products" in data:
            return data["products"]
        
        log.warning(f"No search results found for: {keywords}")
        return None

    def _parse_product_json(self, product_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses the raw JSON response into the metadata structure.
        (This function is unchanged)
        """
        log.debug(f"Parsing product data for ASIN {product_data.get('asin')}")
        
        def get_contributors(key: str) -> List[str]:
            return [c.get("name", "").strip() for c in product_data.get(key, []) if c.get("name")]

        series_list = product_data.get("series", [])
        series_name = None
        series_part = None
        if series_list and isinstance(series_list, list):
            series_info = series_list[0]
            series_name = series_info.get("title")
            series_part = series_info.get("sequence")
            if series_part:
                series_part = str(series_part).lower().replace("book", "").strip()
                try:
                    series_part = f"{int(float(series_part)):02d}"
                except ValueError:
                    pass

        release_date = product_data.get("release_date")
        year = None
        if release_date:
            try:
                year = release_date.split("-")[0]
            except Exception:
                log.warning(f"Could not parse year from release_date: {release_date}")

        cover_url = None
        images = product_data.get("product_images", {})
        for size in ["1000", "700", "500"]:
            if size in images:
                cover_url = images[size]
                break

        metadata = {
            "asin": product_data.get("asin"),
            "title": product_data.get("title"),
            "subtitle": product_data.get("subtitle"),
            "authors": get_contributors("authors"),
            "narrators": get_contributors("narrators"),
            "series": series_name,
            "series_part": series_part,
            "release_date": release_date,
            "year": year,
            "description": product_data.get("publisher_summary", "").strip(),
            "rating": product_data.get("ratings_summary", {}).get("average_rating"),
            "cover_url": cover_url,
            "product_url": f"{self.web_base}/pd/{product_data.get('asin')}",
            "raw_json": product_data
        }
        
        metadata["MP3TAG_TITLE"] = metadata["title"]
        metadata["MP3TAG_AUTHOR"] = format_contributors(metadata["authors"])
        metadata["MP3TAG_NARRATOR"] = format_contributors(metadata["narrators"])
        metadata["MP3TAG_SERIES"] = metadata["series"]
        metadata["MP3TAG_SERIES_PART"] = metadata["series_part"]
        metadata["MP3TAG_YEAR"] = metadata["year"]
        metadata["MP3TAG_DESC"] = metadata["description"]
        metadata["MP3TAG_WWWAUDIOFILE"] = metadata["product_url"]

        return metadata

    def download_cover(
        self,
        cover_url: str,
        save_path: Path,
        dry_run: bool = False
    ) -> bool:
        """
        Downloads the cover image to the specified path.
        (This function is unchanged)
        """
        if not cover_url:
            log.warning(f"No cover URL provided for {save_path.parent.name}")
            return False
            
        if dry_run:
            log.info(f"[DRY RUN] Would download cover from {cover_url} to {save_path}")
            return True

        try:
            log.debug(f"Downloading cover: {cover_url}")
            response = self.session.get(cover_url, stream=True, timeout=15)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            log.info(f"Saved cover image to {save_path}")
            return True
            
        except requests.exceptions.RequestException as e:
            log.error(f"Failed to download cover image {cover_url}: {e}")
            return False
