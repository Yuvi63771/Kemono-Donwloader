# --- Standard Library Imports ---
import os
import re
from urllib.parse import urlparse

# --- Third-Party Library Imports ---
# This module might not require third-party libraries directly,
# but 'requests' is a common dependency for network operations.
# import requests


def parse_cookie_string(cookie_string):
    """
    Parses a 'name=value; name2=value2' cookie string into a dictionary.

    Args:
        cookie_string (str): The cookie string from browser tools.

    Returns:
        dict or None: A dictionary of cookie names and values, or None if empty.
    """
    cookies = {}
    if cookie_string:
        for item in cookie_string.split(';'):
            parts = item.split('=', 1)
            if len(parts) == 2:
                name = parts[0].strip()
                value = parts[1].strip()
                if name:
                    cookies[name] = value
    return cookies if cookies else None


def load_cookies_from_netscape_file(filepath, logger_func, target_domain_filter=None):
    """
    Loads cookies from a Netscape-formatted cookies.txt file.

    If a target_domain_filter is provided, only cookies for that domain
    (or its subdomains) are returned.

    Args:
        filepath (str): The full path to the cookies.txt file.
        logger_func (callable): Function to use for logging.
        target_domain_filter (str, optional): The domain to filter cookies for.

    Returns:
        dict or None: A dictionary of cookie names and values, or None if none are loaded.
    """
    cookies = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split('\t')
                if len(parts) == 7:
                    cookie_domain = parts[0]
                    name = parts[5]
                    value = parts[6]

                    if not name:
                        continue

                    if target_domain_filter:
                        # Match domain exactly or as a subdomain
                        host_to_match = target_domain_filter.lower()
                        cookie_domain_norm = cookie_domain.lower()
                        if (cookie_domain_norm.startswith('.') and host_to_match.endswith(cookie_domain_norm)) or \
                           (host_to_match == cookie_domain_norm):
                            cookies[name] = value
                    else:
                        cookies[name] = value

        logger_func(f"   🍪 Loaded {len(cookies)} cookies from '{os.path.basename(filepath)}' for domain '{target_domain_filter or 'any'}'.")
        return cookies if cookies else None
    except FileNotFoundError:
        logger_func(f"   🍪 Cookie file '{os.path.basename(filepath)}' not found.")
        return None
    except Exception as e:
        logger_func(f"   🍪 Error parsing cookie file '{os.path.basename(filepath)}': {e}")
        return None


def prepare_cookies_for_request(use_cookie_flag, cookie_text_input, selected_cookie_file_path, app_base_dir, logger_func, target_domain=None):
    """
    Prepares a cookie dictionary from various sources based on user settings.
    Priority:
    1. UI-selected file path.
    2. Domain-specific file in the app directory.
    3. Default `cookies.txt` in the app directory.
    4. Manually entered cookie text.

    Args:
        use_cookie_flag (bool): Whether cookies are enabled in the UI.
        cookie_text_input (str): The raw text from the cookie input field.
        selected_cookie_file_path (str): The path to a user-browsed cookie file.
        app_base_dir (str): The base directory of the application.
        logger_func (callable): Function for logging.
        target_domain (str, optional): The domain for which cookies are needed.

    Returns:
        dict or None: A dictionary of cookies for the request, or None.
    """
    if not use_cookie_flag:
        return None

    # Priority 1: Use the specifically browsed file first
    if selected_cookie_file_path and os.path.exists(selected_cookie_file_path):
        cookies = load_cookies_from_netscape_file(selected_cookie_file_path, logger_func, target_domain)
        if cookies:
            return cookies

    # Priority 2: Look for a domain-specific cookie file
    if app_base_dir and target_domain:
        domain_specific_path = os.path.join(app_base_dir, "data", f"{target_domain}_cookies.txt")
        if os.path.exists(domain_specific_path):
            cookies = load_cookies_from_netscape_file(domain_specific_path, logger_func, target_domain)
            if cookies:
                return cookies

    # Priority 3: Look for a generic cookies.txt
    if app_base_dir:
        default_path = os.path.join(app_base_dir, "appdata", "cookies.txt")
        if os.path.exists(default_path):
            cookies = load_cookies_from_netscape_file(default_path, logger_func, target_domain)
            if cookies:
                return cookies

    # Priority 4: Fall back to manually entered text
    if cookie_text_input:
        cookies = parse_cookie_string(cookie_text_input)
        if cookies:
            return cookies

    logger_func(f"   🍪 Cookie usage enabled for '{target_domain or 'any'}', but no valid cookies found.")
    return None


def extract_post_info(url_string):
    """
    Parses a URL string to extract the service, user ID, and post ID.
    UPDATED to support Hentai2Read series and chapters.
    """
    if not isinstance(url_string, str) or not url_string.strip():
        return None, None, None

    stripped_url = url_string.strip()

    # --- Bunkr Check ---
    bunkr_pattern = re.compile(
        r"(?:https?://)?(?:[a-zA-Z0-9-]+\.)?bunkr\.(?:si|la|ws|red|black|media|site|is|to|ac|cr|ci|fi|pk|ps|sk|ph|su|ru)|bunkrr\.ru"
    )
    if bunkr_pattern.search(stripped_url):
        return 'bunkr', stripped_url, None

    # --- nhentai Check ---
    nhentai_match = re.search(r'nhentai\.net/g/(\d+)', stripped_url)
    if nhentai_match:
        return 'nhentai', nhentai_match.group(1), None
    
    # --- Hentai2Read Check (Updated) ---
    # This regex now captures the manga slug (id1) and optionally the chapter number (id2)
    hentai2read_match = re.search(r'hentai2read\.com/([^/]+)(?:/(\d+))?/?', stripped_url)
    if hentai2read_match:
        manga_slug, chapter_num = hentai2read_match.groups()
        return 'hentai2read', manga_slug, chapter_num # chapter_num will be None for series URLs

    discord_channel_match = re.search(r'discord\.com/channels/(@me|\d+)/(\d+)', stripped_url)
    if discord_channel_match:
        server_id, channel_id = discord_channel_match.groups()
        return 'discord', server_id, channel_id

    # --- Kemono/Coomer/Discord Parsing ---
    try:
        parsed_url = urlparse(stripped_url)
        path_parts = [part for part in parsed_url.path.strip('/').split('/') if part]

        if len(path_parts) >= 3 and path_parts[0].lower() == 'discord' and path_parts[1].lower() == 'server':
            return 'discord', path_parts[2], path_parts[3] if len(path_parts) >= 4 else None

        if len(path_parts) >= 3 and path_parts[1].lower() == 'user':
            service = path_parts[0]
            user_id = path_parts[2]
            post_id = path_parts[4] if len(path_parts) >= 5 and path_parts[3].lower() == 'post' else None
            return service, user_id, post_id

        if len(path_parts) >= 5 and path_parts[0:2] == ['api', 'v1'] and path_parts[3].lower() == 'user':
            service = path_parts[2]
            user_id = path_parts[4]
            post_id = path_parts[6] if len(path_parts) >= 7 and path_parts[5].lower() == 'post' else None
            return service, user_id, post_id

    except Exception as e:
        print(f"Debug: Exception during URL parsing for '{url_string}': {e}")

    return None, None, None
    
def get_link_platform(url):
    """
    Identifies the platform of a given URL based on its domain.

    Args:
        url (str): The URL to identify.

    Returns:
        str: The name of the platform (e.g., 'mega', 'google drive') or 'external'.
    """
    try:
        domain = urlparse(url).netloc.lower()
        if 'drive.google.com' in domain: return 'google drive'
        if 'mega.nz' in domain or 'mega.io' in domain: return 'mega'
        if 'dropbox.com' in domain: return 'dropbox'
        if 'patreon.com' in domain: return 'patreon'
        if 'gofile.io' in domain: return 'gofile'
        if 'instagram.com' in domain: return 'instagram'
        if 'twitter.com' in domain or 'x.com' in domain: return 'twitter/x'
        if 'discord.gg' in domain or 'discord.com/invite' in domain: return 'discord invite'
        if 'pixiv.net' in domain: return 'pixiv'
        if 'kemono.su' in domain or 'kemono.party' in domain or 'kemono.cr' in domain: return 'kemono'
        if 'coomer.su' in domain or 'coomer.party' in domain or 'coomer.st' in domain: return 'coomer'
        
        parts = domain.split('.')
        if len(parts) >= 2:
            return parts[-2]
        return 'external'
    except Exception:
        return 'unknown'
