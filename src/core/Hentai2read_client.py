# src/core/Hentai2read_client.py

import re
import os
import json
import requests
import cloudscraper
from bs4 import BeautifulSoup

def fetch_hentai2read_data(url, logger, session):
    """
    Scrapes a SINGLE Hentai2Read chapter page using a provided session.
    """
    logger(f"Attempting to fetch chapter data from: {url}")
    
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        page_content_text = response.text
        soup = BeautifulSoup(page_content_text, 'html.parser')

        album_title = ""
        title_tags = soup.select('span[itemprop="name"]')
        if title_tags:
            album_title = title_tags[-1].text.strip()
        
        if not album_title:
            title_tag = soup.select_one('h1.title')
            if title_tag:
                album_title = title_tag.text.strip()

        if not album_title:
            logger("❌ Could not find album title on page.")
            return None, None
        
        image_urls = []
        try:
            start_index = page_content_text.index("'images' : ") + len("'images' : ")
            end_index = page_content_text.index(",\n", start_index)
            images_json_str = page_content_text[start_index:end_index]
            image_paths = json.loads(images_json_str)
            image_urls = ["https://hentaicdn.com/hentai" + part for part in image_paths]
        except (ValueError, json.JSONDecodeError):
            logger("❌ Could not find or parse image JSON data for this chapter.")
            return None, None

        if not image_urls:
            logger("❌ No image URLs found for this chapter.")
            return None, None

        logger(f"   Found {len(image_urls)} images for album '{album_title}'.")

        files_to_download = []
        for i, img_url in enumerate(image_urls):
            page_num = i + 1
            extension = os.path.splitext(img_url)[1].split('?')[0]
            if not extension: extension = ".jpg"
            filename = f"{page_num:03d}{extension}"
            files_to_download.append({'url': img_url, 'filename': filename})

        return album_title, files_to_download

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger(f"   Chapter not found (404 Error). This likely marks the end of the series.")
        else:
            logger(f"❌ An HTTP error occurred: {e}")
        return None, None
    except Exception as e:
        logger(f"❌ An unexpected error occurred while fetching data: {e}")
        return None, None
