import re
import os
import cloudscraper
from urllib.parse import urlparse
from ..utils.file_utils import clean_folder_name

def fetch_fap_nation_data(album_url, logger_func):
    """
    Scrapes a fap-nation page by checking for direct links, then searching
    inside video iframes for HLS streams.
    """
    logger_func(f"   [Fap-Nation] Fetching album data from: {album_url}")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(album_url, timeout=45)
        response.raise_for_status()
        html_content = response.text
        
        title_match = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', html_content, re.IGNORECASE)
        album_slug = clean_folder_name(os.path.basename(urlparse(album_url).path.strip('/')))
        album_title = clean_folder_name(title_match.group(1).strip()) if title_match else album_slug

        files_to_download = []
        final_url = None
        link_type = None
        filename_from_video_tag = None

        # --- FINAL LOGIC ---

        # A. Attempt to find a high-quality filename from the video player's configuration on the main page.
        video_tag_title_match = re.search(r'data-plyr-config=.*?&quot;title&quot;:.*?&quot;([^&]+?\.mp4)&quot;', html_content, re.IGNORECASE)
        if video_tag_title_match:
            filename_from_video_tag = clean_folder_name(video_tag_title_match.group(1))
            logger_func(f"   [Fap-Nation] Found high-quality filename in video tag: {filename_from_video_tag}")

        # 1. Prioritize finding direct media links on the main page.
        direct_link_pattern = r'<a\s+[^>]*href="([^"]+\.(?:mp4|webm|mkv|mov))"[^>]*>'
        direct_links_found = re.findall(direct_link_pattern, html_content, re.IGNORECASE)

        if direct_links_found:
            logger_func(f"   [Fap-Nation] Found {len(direct_links_found)} direct media link(s). Selecting the best quality...")
            best_link = direct_links_found[0]
            for link in direct_links_found:
                if '1080p' in link.lower():
                    best_link = link
                    break
            final_url = best_link
            link_type = 'direct'
            logger_func(f"   [Fap-Nation] Identified direct media link: {final_url}")
        else:
            # 2. Fallback: Search for an iframe and extract the HLS stream from it.
            logger_func("   [Fap-Nation] No direct media links found. Searching for video iframe...")
            
            # This pattern specifically looks for the video provider's iframe
            iframe_match = re.search(r'<iframe[^>]+src="([^"]+mediadelivery\.net[^"]+)"', html_content, re.IGNORECASE)
            
            if iframe_match:
                iframe_url = iframe_match.group(1)
                logger_func(f"   [Fap-Nation] Found video iframe. Visiting: {iframe_url}")
                try:
                    # Make a second request to the iframe's URL to get its content
                    iframe_response = scraper.get(iframe_url, timeout=30)
                    iframe_response.raise_for_status()
                    iframe_html = iframe_response.text
                    
                    # Now search for the <source> tag INSIDE the iframe's HTML
                    playlist_match = re.search(r'<source[^>]+src="([^"]+\.m3u8)"', iframe_html, re.IGNORECASE)
                    if playlist_match:
                        final_url = playlist_match.group(1)
                        link_type = 'hls'
                        logger_func(f"   [Fap-Nation] Found embedded HLS stream in iframe: {final_url}")

                except Exception as e:
                    logger_func(f"   [Fap-Nation] ⚠️ Error fetching or parsing iframe content: {e}")
            
            # 3. Final Fallback: If no iframe or iframe failed, check main page for a stream link.
            if not final_url:
                logger_func("   [Fap-Nation] No stream found in iframe. Checking main page content as a last resort...")
                js_var_match = re.search(r'"(https?://[^"]+\.m3u8)"', html_content, re.IGNORECASE)
                if js_var_match:
                    final_url = js_var_match.group(1)
                    link_type = 'hls'
                    logger_func(f"   [Fap-Nation] Found HLS stream on main page: {final_url}")
                else:
                    logger_func("   [Fap-Nation] ❌ Stage 1 Failed: Could not find a direct link, iframe stream, or any embedded .m3u8 playlist.")
                    return None, []

        if final_url and link_type:
            if filename_from_video_tag:
                base_name, _ = os.path.splitext(filename_from_video_tag)
                new_filename = f"{base_name}.mp4"
            else:
                new_filename = f"{album_slug}.mp4"
            
            files_to_download.append({'url': final_url, 'filename': new_filename, 'type': link_type})
            logger_func(f"   [Fap-Nation] ✅ Ready to download '{new_filename}' ({link_type} method).")
            return album_title, files_to_download
        
        logger_func(f"   [Fap-Nation] ❌ Could not determine a valid download link.")
        return None, []
        
    except Exception as e:
        logger_func(f"   [Fap-Nation] ❌ Error fetching Fap-Nation data: {e}")
        return None, []