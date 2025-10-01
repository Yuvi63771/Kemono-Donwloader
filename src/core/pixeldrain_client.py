import os
import re
import cloudscraper
from ..utils.file_utils import clean_folder_name

def fetch_pixeldrain_data(url: str, logger):
    """
    Scrapes a given Pixeldrain URL to extract album or file information.
    Handles single files (/u/), albums/lists (/l/), and folders (/d/).

    Args:
        url (str): The full URL to the Pixeldrain resource.
        logger (function): A function to send log messages to the UI.

    Returns:
        A tuple of (str: title, list[dict]: files_to_download).
        Returns (None, []) on failure.
    """
    logger(f"Fetching data for Pixeldrain URL: {url}")
    scraper = cloudscraper.create_scraper()
    root = "https://pixeldrain.com"

    file_match = re.search(r"/u/(\w+)", url)
    album_match = re.search(r"/l/(\w+)", url)
    folder_match = re.search(r"/d/([^?]+)", url)

    try:
        if file_match:
            file_id = file_match.group(1)
            logger(f"   Detected Pixeldrain File ID: {file_id}")
            api_url = f"{root}/api/file/{file_id}/info"
            data = scraper.get(api_url).json()
            
            # The title for a single file will just be its name
            title = data.get("name", file_id)
            
            files = [{
                'url': f"{root}/api/file/{file_id}?download",
                'filename': data.get("name", f"{file_id}.tmp")
            }]
            return title, files

        elif album_match:
            album_id = album_match.group(1)
            logger(f"   Detected Pixeldrain Album ID: {album_id}")
            api_url = f"{root}/api/list/{album_id}"
            data = scraper.get(api_url).json()

            title = data.get("title", album_id)
            
            files = []
            for file_info in data.get("files", []):
                files.append({
                    'url': f"{root}/api/file/{file_info['id']}?download",
                    'filename': file_info.get("name", f"{file_info['id']}.tmp")
                })
            return title, files

        elif folder_match:
            # Note: The provided extractor had complex recursive logic for folders.
            # This adaptation handles the top-level folder content for simplicity.
            path_id = folder_match.group(1)
            logger(f"   Detected Pixeldrain Folder Path: {path_id}")
            api_url = f"{root}/api/filesystem/{path_id}?stat"
            data = scraper.get(api_url).json()

            # Use the name of the base folder as the title
            path_info = data["path"][data["base_index"]]
            title = path_info.get("name", path_id)

            files = []
            for child in data.get("children", []):
                if child.get("type") == "file":
                    files.append({
                        'url': f"{root}/api/filesystem{child['path']}?attach",
                        'filename': child.get("name")
                    })
            return title, files

        else:
            logger("   ❌ Could not identify Pixeldrain URL type (file, album, or folder).")
            return None, []

    except Exception as e:
        logger(f"❌ An error occurred while fetching Pixeldrain data: {e}")
        return None, []