import requests
import re
from bs4 import BeautifulSoup
import cloudscraper
import time 
from urllib.parse import urlparse

def get_chapter_list(series_url, logger_func):
    """
    Checks if a URL is a series page and returns a list of all chapter URLs if it is.
    Includes a retry mechanism for robust connection.
    """
    logger_func(f"   [AllComic] Checking for chapter list at: {series_url}")
    
    scraper = cloudscraper.create_scraper()
    response = None
    max_retries = 8

    for attempt in range(max_retries):
        try:
            response = scraper.get(series_url, timeout=30)
            response.raise_for_status()
            logger_func(f"   [AllComic] Successfully connected to series page on attempt {attempt + 1}.")
            break # Success, exit the loop
        except requests.RequestException as e:
            logger_func(f"   [AllComic] ⚠️ Series page check attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 * (attempt + 1)
                logger_func(f"      Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger_func(f"   [AllComic] ❌ All attempts to check series page failed.")
                return [] # Return empty on final failure
    
    if not response:
        return []

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        chapter_links = soup.select('li.wp-manga-chapter a')
        
        if not chapter_links:
            logger_func("   [AllComic] ℹ️ No chapter list found. Assuming this is a single chapter page.")
            return []

        chapter_urls = [link['href'] for link in chapter_links]
        chapter_urls.reverse() # Reverse for oldest-to-newest reading order
        
        logger_func(f"   [AllComic] ✅ Found {len(chapter_urls)} chapters.")
        return chapter_urls
        
    except Exception as e:
        logger_func(f"   [AllComic] ❌ Error parsing chapters after successful connection: {e}")
        return []

def fetch_chapter_data(chapter_url, logger_func):
    """
    Fetches the comic title, chapter title, and image URLs for a single chapter page.
    """
    logger_func(f"   [AllComic] Fetching page: {chapter_url}")

    scraper = cloudscraper.create_scraper(
        browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
    )
    headers = {'Referer': 'https://allporncomic.com/'}
    
    response = None
    max_retries = 8
    for attempt in range(max_retries):
        try:
            response = scraper.get(chapter_url, headers=headers, timeout=30)
            response.raise_for_status()
            break
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
            else:
                logger_func(f"   [AllComic] ❌ All connection attempts failed for chapter: {chapter_url}")
                return None, None, None
    
    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        title_element = soup.find('h1', class_='post-title')
        comic_title = None
        if title_element:
            comic_title = title_element.text.strip()
        else:
            try:
                path_parts = urlparse(chapter_url).path.strip('/').split('/')
                if len(path_parts) >= 3 and path_parts[-3] == 'porncomic':
                    comic_slug = path_parts[-2]
                    comic_title = comic_slug.replace('-', ' ').title()
            except Exception:
                comic_title = "Unknown Comic"

        chapter_slug = chapter_url.strip('/').split('/')[-1]
        chapter_title = chapter_slug.replace('-', ' ').title()
        
        reading_container = soup.find('div', class_='reading-content')
        list_of_image_urls = []
        if reading_container:
            image_elements = reading_container.find_all('img', class_='wp-manga-chapter-img')
            for img in image_elements:
                img_url = (img.get('data-src') or img.get('src', '')).strip()
                if img_url:
                    list_of_image_urls.append(img_url)

        if not comic_title or comic_title == "Unknown Comic" or not list_of_image_urls:
            logger_func(f"   [AllComic] ❌ Could not find a valid title or images on the page. Title found: '{comic_title}'")
            return None, None, None

        return comic_title, chapter_title, list_of_image_urls
        
    except Exception as e:
        logger_func(f"   [AllComic] ❌ An unexpected error occurred while parsing the page: {e}")
        return None, None, None