import requests
import cloudscraper
import json

def fetch_nhentai_gallery(gallery_id, logger=print):
    """
    Fetches the metadata for a single nhentai gallery using cloudscraper to bypass Cloudflare.

    Args:
        gallery_id (str or int): The ID of the nhentai gallery.
        logger (function): A function to log progress and error messages.

    Returns:
        dict: A dictionary containing the gallery's metadata if successful, otherwise None.
    """
    api_url = f"https://nhentai.net/api/gallery/{gallery_id}"
    
    scraper = cloudscraper.create_scraper()
    
    logger(f"   Fetching nhentai gallery metadata from: {api_url}")

    try:
        # Use the scraper to make the GET request
        response = scraper.get(api_url, timeout=20)
        
        if response.status_code == 404:
            logger(f"   ❌ Gallery not found (404): ID {gallery_id}")
            return None
            
        response.raise_for_status()

        gallery_data = response.json()
        
        if "id" in gallery_data and "media_id" in gallery_data and "images" in gallery_data:
            logger(f"   ✅ Successfully fetched metadata for '{gallery_data['title']['english']}'")
            gallery_data['pages'] = gallery_data.pop('images')['pages']
            return gallery_data
        else:
            logger("   ❌ API response is missing essential keys (id, media_id, or images).")
            return None

    except Exception as e:
        logger(f"   ❌ An error occurred while fetching gallery {gallery_id}: {e}")
        return None