import os
import re as re_module
import html
import urllib.parse
import requests


PATTERN_CACHE = {}

def re(pattern):
    """Compile a regular expression pattern and cache it."""
    try:
        return PATTERN_CACHE[pattern]
    except KeyError:
        p = PATTERN_CACHE[pattern] = re_module.compile(pattern)
        return p

def extract_from(txt, pos=None, default=""):
    """Returns a function that extracts text between two delimiters from 'txt'."""
    def extr(begin, end, index=txt.find, txt=txt):
        nonlocal pos
        try:
            start_pos = pos if pos is not None else 0
            first = index(begin, start_pos) + len(begin)
            last = index(end, first)
            if pos is not None:
                pos = last + len(end)
            return txt[first:last]
        except (ValueError, IndexError):
            return default
    return extr

def nameext_from_url(url):
    """Extract filename and extension from a URL."""
    data = {}
    filename = urllib.parse.unquote(url.partition("?")[0].rpartition("/")[2])
    name, _, ext = filename.rpartition(".")
    if name and len(ext) <= 16:
        data["filename"], data["extension"] = name, ext.lower()
    else:
        data["filename"], data["extension"] = filename, ""
    return data

class BaseExtractor:
    """A simplified base class for extractors."""
    def __init__(self, match, session, logger):
        self.match = match
        self.groups = match.groups()
        self.session = session
        self.log = logger

    def request(self, url, **kwargs):
        """Makes an HTTP request using the session."""
        try:
            response = self.session.get(url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            self.log(f"Error making request to {url}: {e}")
            return None

class SaintAlbumExtractor(BaseExtractor):
    """Extractor for saint.su albums."""
    root = "https://saint2.su"
    pattern = re(r"(?:https?://)?saint\d*\.(?:su|pk|cr|to)/a/([^/?#]+)")

    def items(self):
        """Generator that yields all files from an album."""
        album_id = self.groups[0]
        response = self.request(f"{self.root}/a/{album_id}")
        if not response:
            return None, []

        extr = extract_from(response.text)
        title = extr("<title>", "<").rpartition(" - ")[0]
        self.log(f"Downloading album: {title}")

        files_html = re_module.findall(r'<a class="image".*?</a>', response.text, re_module.DOTALL)
        file_list = []
        for i, file_html in enumerate(files_html, 1):
            file_extr = extract_from(file_html)
            file_url = html.unescape(file_extr("onclick=\"play('", "'"))
            if not file_url:
                continue

            filename_info = nameext_from_url(file_url)
            filename = f"{filename_info['filename']}.{filename_info['extension']}"

            file_data = {
                "url": file_url,
                "filename": filename,
                "headers": {"Referer": response.url},
            }
            file_list.append(file_data)
        
        return title, file_list

class SaintMediaExtractor(BaseExtractor):
    """Extractor for single saint.su media links."""
    root = "https://saint2.su"
    pattern = re(r"(?:https?://)?saint\d*\.(?:su|pk|cr|to)(/(embe)?d/([^/?#]+))")

    def items(self):
        """Generator that yields the single file from a media page."""
        path, embed, media_id = self.groups
        url = self.root + path
        response = self.request(url)
        if not response:
            return None, []

        extr = extract_from(response.text)
        file_url = ""
        title = extr("<title>", "<").rpartition(" - ")[0] or media_id

        if embed:  # /embed/ link
            file_url = html.unescape(extr('<source src="', '"'))
        else:  # /d/ link
            file_url = html.unescape(extr('<a href="', '"'))

        if not file_url:
            self.log("Could not find video URL on the page.")
            return title, []

        filename_info = nameext_from_url(file_url)
        filename = f"{filename_info['filename'] or media_id}.{filename_info['extension'] or 'mp4'}"

        file_data = {
            "url": file_url,
            "filename": filename,
            "headers": {"Referer": response.url}
        }
        
        return title, [file_data]


def fetch_saint2_data(url, logger):
    """
    Identifies the correct extractor for a saint2.su URL and returns the data.
    
    Args:
        url (str): The saint2.su URL.
        logger (function): A function to log progress messages.
        
    Returns:
        tuple: A tuple containing (album_title, list_of_file_dicts).
               Returns (None, []) if no data could be fetched.
    """
    extractors = [SaintMediaExtractor, SaintAlbumExtractor]
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    for extractor_cls in extractors:
        match = extractor_cls.pattern.match(url)
        if match:
            extractor = extractor_cls(match, session, logger)
            album_title, files = extractor.items()
            sanitized_title = re_module.sub(r'[<>:"/\\|?*]', '_', album_title) if album_title else "saint2_download"
            return sanitized_title, files

    logger(f"Error: The URL '{url}' does not match a known saint2 pattern.")
    return None, []