import time
import traceback
from urllib.parse import urlparse
import json
import requests
import cloudscraper 
from ..utils.network_utils import extract_post_info, prepare_cookies_for_request
from ..config.constants import (
    STYLE_DATE_POST_TITLE
)


def fetch_posts_paginated(api_url_base, headers, offset, logger, cancellation_event=None, pause_event=None, cookies_dict=None):
    """
    Fetches a single page of posts from the API with robust retry logic.
    """
    if cancellation_event and cancellation_event.is_set():
        raise RuntimeError("Fetch operation cancelled by user.")
    if pause_event and pause_event.is_set():
        logger("   Post fetching paused...")
        while pause_event.is_set():
            if cancellation_event and cancellation_event.is_set():
                raise RuntimeError("Fetch operation cancelled by user while paused.")
            time.sleep(0.5)
        logger("   Post fetching resumed.")
    fields_to_request = "id,user,service,title,shared_file,added,published,edited,file,attachments,tags"
    paginated_url = f'{api_url_base}?o={offset}&fields={fields_to_request}'
    
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        if cancellation_event and cancellation_event.is_set():
            raise RuntimeError("Fetch operation cancelled by user during retry loop.")

        log_message = f"   Fetching post list: {api_url_base} (Page approx. {offset // 50 + 1})"
        if attempt > 0:
            log_message += f" (Attempt {attempt + 1}/{max_retries})"
        logger(log_message)

        try:
            response = requests.get(paginated_url, headers=headers, timeout=(15, 60), cookies=cookies_dict)
            response.raise_for_status()
            response.encoding = 'utf-8'  
            return response.json()

        except requests.exceptions.RequestException as e:
            # Handle 403 error on the FIRST page as a rate limit/block
            if e.response is not None and e.response.status_code == 403 and offset == 0:
                logger("   ❌ Access Denied (403 Forbidden) on the first page.")
                logger("      This is likely a rate limit or a Cloudflare block.")
                logger("      💡 SOLUTION: Wait a while, use a VPN, or provide a valid session cookie.")
                return [] # Stop the process gracefully

            # Handle 400 error as the end of pages
            if e.response is not None and e.response.status_code == 400:
                logger(f"   ✅ Reached end of posts (API returned 400 Bad Request for offset {offset}).")
                return []

            # Handle all other network errors with a retry
            logger(f"   ⚠️ Retryable network error on page fetch (Attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = retry_delay * (2 ** attempt)
                logger(f"      Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            else:
                logger(f"   ❌ Failed to fetch page after {max_retries} attempts.")
                raise RuntimeError(f"Network error fetching offset {offset}")
        except json.JSONDecodeError as e:
            logger(f"   ❌ Failed to decode JSON on page fetch (Attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = retry_delay * (2 ** attempt)
                logger(f"      Retrying in {delay} seconds...")
                time.sleep(delay)
                continue
            else:
                raise RuntimeError(f"JSONDecodeError fetching offset {offset}")

    raise RuntimeError(f"Failed to fetch page {paginated_url} after all attempts.")

def fetch_single_post_data(api_domain, service, user_id, post_id, headers, logger, cookies_dict=None):
    """
    --- MODIFIED FUNCTION ---
    Fetches the full data, including the 'content' field, for a single post using cloudscraper.
    """
    post_api_url = f"https://{api_domain}/api/v1/{service}/user/{user_id}/post/{post_id}"
    logger(f"      Fetching full content for post ID {post_id}...")

    scraper = cloudscraper.create_scraper()

    try:
        response = scraper.get(post_api_url, headers=headers, timeout=(15, 300), cookies=cookies_dict)
        response.raise_for_status()

        full_post_data = response.json()

        if isinstance(full_post_data, list) and full_post_data:
            return full_post_data[0] 
        if isinstance(full_post_data, dict) and 'post' in full_post_data:
            return full_post_data['post'] 
        return full_post_data 

    except Exception as e:
        logger(f"      ❌ Failed to fetch full content for post {post_id}: {e}")
        return None

        
def fetch_post_comments(api_domain, service, user_id, post_id, headers, logger, cancellation_event=None, pause_event=None, cookies_dict=None):
    """Fetches all comments for a specific post."""
    if cancellation_event and cancellation_event.is_set():
        raise RuntimeError("Comment fetch operation cancelled by user.")

    comments_api_url = f"https://{api_domain}/api/v1/{service}/user/{user_id}/post/{post_id}/comments"
    logger(f"   Fetching comments: {comments_api_url}")
    
    try:
        response = requests.get(comments_api_url, headers=headers, timeout=(10, 30), cookies=cookies_dict)
        response.raise_for_status()
        response.encoding = 'utf-8'          
        return response.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Error fetching comments for post {post_id}: {e}")
    except ValueError as e:
        raise RuntimeError(f"Error decoding JSON from comments API for post {post_id}: {e}")

def download_from_api(
    api_url_input,
    logger=print,
    start_page=None,
    end_page=None,
    manga_mode=False,
    cancellation_event=None,
    pause_event=None,
    use_cookie=False,
    cookie_text="",
    selected_cookie_file=None,
    app_base_dir=None,
    manga_filename_style_for_sort_check=None,
    processed_post_ids=None,
    fetch_all_first=False  
    ):
    parsed_input_url_for_domain = urlparse(api_url_input)
    api_domain = parsed_input_url_for_domain.netloc

    headers = {
        'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'Referer': f'https://{api_domain}/',
        'Accept': 'text/css'
    }

    if processed_post_ids is None:
        processed_post_ids = set()
    else:
        processed_post_ids = set(processed_post_ids)

    service, user_id, target_post_id = extract_post_info(api_url_input)

    if cancellation_event and cancellation_event.is_set():
        logger("   Download_from_api cancelled at start.")
        return

    # The code that defined api_domain was moved from here to the top of the function
    
    if not any(d in api_domain.lower() for d in ['kemono.su', 'kemono.party', 'kemono.cr', 'coomer.su', 'coomer.party', 'coomer.st']):
        logger(f"⚠️ Unrecognized domain '{api_domain}' from input URL. Defaulting to kemono.su for API calls.")
        api_domain = "kemono.su"
        
    cookies_for_api = None
    if use_cookie and app_base_dir:
        cookies_for_api = prepare_cookies_for_request(use_cookie, cookie_text, selected_cookie_file, app_base_dir, logger, target_domain=api_domain)
    if target_post_id:
        if target_post_id in processed_post_ids:
            logger(f"   Skipping already processed target post ID: {target_post_id}")
            return
        direct_post_api_url = f"https://{api_domain}/api/v1/{service}/user/{user_id}/post/{target_post_id}"
        logger(f"   Attempting direct fetch for target post: {direct_post_api_url}")
        try:
            direct_response = requests.get(direct_post_api_url, headers=headers, timeout=(10, 30), cookies=cookies_for_api)
            direct_response.raise_for_status()
            direct_response.encoding = 'utf-8' 
            direct_post_data = direct_response.json()
            if isinstance(direct_post_data, list) and direct_post_data:
                direct_post_data = direct_post_data[0]
            if isinstance(direct_post_data, dict) and 'post' in direct_post_data and isinstance(direct_post_data['post'], dict):
                direct_post_data = direct_post_data['post']
            if isinstance(direct_post_data, dict) and direct_post_data.get('id') == target_post_id:
                logger(f"   ✅ Direct fetch successful for post {target_post_id}.")
                yield [direct_post_data]
                return
            else:
                response_type = type(direct_post_data).__name__
                response_snippet = str(direct_post_data)[:200]
                logger(f"   ⚠️ Direct fetch for post {target_post_id} returned unexpected data (Type: {response_type}, Snippet: '{response_snippet}'). Falling back to pagination.")
        except requests.exceptions.RequestException as e:
            logger(f"   ⚠️ Direct fetch failed for post {target_post_id}: {e}. Falling back to pagination.")
        except Exception as e:
            logger(f"   ⚠️ Unexpected error during direct fetch for post {target_post_id}: {e}. Falling back to pagination.")
    if not service or not user_id:
        logger(f"❌ Invalid URL or could not extract service/user: {api_url_input}")
        return
    if target_post_id and (start_page or end_page):
        logger("⚠️ Page range (start/end page) is ignored when a specific post URL is provided (searching all pages for the post).")

    is_manga_mode_fetch_all_and_sort_oldest_first = manga_mode and (manga_filename_style_for_sort_check != STYLE_DATE_POST_TITLE) and not target_post_id
    should_fetch_all = fetch_all_first or is_manga_mode_fetch_all_and_sort_oldest_first  
    api_base_url = f"https://{api_domain}/api/v1/{service}/user/{user_id}/posts"
    page_size = 50
    if is_manga_mode_fetch_all_and_sort_oldest_first:
        logger(f"   Manga Mode (Style: {manga_filename_style_for_sort_check if manga_filename_style_for_sort_check else 'Default'} - Oldest First Sort Active): Fetching all posts to sort by date...")
        all_posts_for_manga_mode = []
        current_offset_manga = 0
        if start_page and start_page > 1:
            current_offset_manga = (start_page - 1) * page_size
            logger(f"   Manga Mode: Starting fetch from page {start_page} (offset {current_offset_manga}).")
        elif start_page:
            logger(f"   Manga Mode: Starting fetch from page 1 (offset 0).")
        if end_page:
            logger(f"   Manga Mode: Will fetch up to page {end_page}.")
        while True:
            if pause_event and pause_event.is_set():
                logger("   Manga mode post fetching paused...")
                while pause_event.is_set():
                    if cancellation_event and cancellation_event.is_set():
                        logger("   Manga mode post fetching cancelled while paused.")
                        break
                    time.sleep(0.5)
                if not (cancellation_event and cancellation_event.is_set()): logger("   Manga mode post fetching resumed.")
            if cancellation_event and cancellation_event.is_set():
                logger("   Manga mode post fetching cancelled.")
                break
            current_page_num_manga = (current_offset_manga // page_size) + 1
            if end_page and current_page_num_manga > end_page:
                logger(f"   Manga Mode: Reached specified end page ({end_page}). Stopping post fetch.")
                break
            try:
                posts_batch_manga = fetch_posts_paginated(api_base_url, headers, current_offset_manga, logger, cancellation_event, pause_event, cookies_dict=cookies_for_api)
                if not isinstance(posts_batch_manga, list):
                    logger(f"❌ API Error (Manga Mode): Expected list of posts, got {type(posts_batch_manga)}.")
                    break
                if not posts_batch_manga:
                    logger("✅ Reached end of posts (Manga Mode fetch all).")
                    if start_page and not end_page and current_page_num_manga < start_page:
                        logger(f"   Manga Mode: No posts found on or after specified start page {start_page}.")
                    elif end_page and current_page_num_manga <= end_page and not all_posts_for_manga_mode:
                        logger(f"   Manga Mode: No posts found within the specified page range ({start_page or 1}-{end_page}).")
                    break
                all_posts_for_manga_mode.extend(posts_batch_manga)
                
                logger(f"RENAMING_MODE_FETCH_PROGRESS:{len(all_posts_for_manga_mode)}:{current_page_num_manga}")

                current_offset_manga += page_size
                time.sleep(0.6)
            except RuntimeError as e:
                if "cancelled by user" in str(e).lower():
                    logger(f"ℹ️ Manga mode pagination stopped due to cancellation: {e}")
                else:
                    logger(f"❌ {e}\n   Aborting manga mode pagination.")
                break
            except Exception as e:
                logger(f"❌ Unexpected error during manga mode fetch: {e}")
                traceback.print_exc()
                break
        
        if cancellation_event and cancellation_event.is_set(): return
        
        if all_posts_for_manga_mode:
            logger(f"RENAMING_MODE_FETCH_COMPLETE:{len(all_posts_for_manga_mode)}")

        if all_posts_for_manga_mode:
            if processed_post_ids:
                original_count = len(all_posts_for_manga_mode)
                all_posts_for_manga_mode = [post for post in all_posts_for_manga_mode if post.get('id') not in processed_post_ids]
                skipped_count = original_count - len(all_posts_for_manga_mode)
                if skipped_count > 0:
                    logger(f"   Manga Mode: Skipped {skipped_count} already processed post(s) before sorting.")

            logger(f"   Manga Mode: Fetched {len(all_posts_for_manga_mode)} total posts. Sorting by publication date (oldest first)...")
            def sort_key_tuple(post):
                published_date_str = post.get('published')
                added_date_str = post.get('added')
                post_id_str = post.get('id', "0")
                primary_sort_val = "0000-00-00T00:00:00"
                if published_date_str:
                    primary_sort_val = published_date_str
                elif added_date_str:
                    logger(f"    ⚠️ Post ID {post_id_str} missing 'published' date, using 'added' date '{added_date_str}' for primary sorting.")
                    primary_sort_val = added_date_str
                else:
                    logger(f"    ⚠️ Post ID {post_id_str} missing both 'published' and 'added' dates. Placing at start of sort (using default earliest date).")
                secondary_sort_val = 0
                try:
                    secondary_sort_val = int(post_id_str)
                except ValueError:
                    logger(f"    ⚠️ Post ID '{post_id_str}' is not a valid integer for secondary sorting, using 0.")
                return (primary_sort_val, secondary_sort_val)
            all_posts_for_manga_mode.sort(key=sort_key_tuple)
            for i in range(0, len(all_posts_for_manga_mode), page_size):
                if cancellation_event and cancellation_event.is_set():
                    logger("   Manga mode post yielding cancelled.")
                    break
                yield all_posts_for_manga_mode[i:i + page_size]
        return

    if manga_mode and not target_post_id and (manga_filename_style_for_sort_check == STYLE_DATE_POST_TITLE):
        logger(f"   Manga Mode (Style: {STYLE_DATE_POST_TITLE}): Processing posts in default API order (newest first).")

    current_page_num = 1
    current_offset = 0
    processed_target_post_flag = False
    if start_page and start_page > 1 and not target_post_id:
        current_offset = (start_page - 1) * page_size
        current_page_num = start_page
        logger(f"   Starting from page {current_page_num} (calculated offset {current_offset}).")
    while True:
        if pause_event and pause_event.is_set():
            logger("   Post fetching loop paused...")
            while pause_event.is_set():
                if cancellation_event and cancellation_event.is_set():
                    logger("   Post fetching loop cancelled while paused.")
                    break
                time.sleep(0.5)
            if not (cancellation_event and cancellation_event.is_set()): logger("   Post fetching loop resumed.")
        if cancellation_event and cancellation_event.is_set():
            logger("   Post fetching loop cancelled.")
            break
        if target_post_id and processed_target_post_flag:
            break
        if not target_post_id and end_page and current_page_num > end_page:
            logger(f"✅ Reached specified end page ({end_page}) for creator feed. Stopping.")
            break
        try:
            posts_batch = fetch_posts_paginated(api_base_url, headers, current_offset, logger, cancellation_event, pause_event, cookies_dict=cookies_for_api)
            if not isinstance(posts_batch, list):
                logger(f"❌ API Error: Expected list of posts, got {type(posts_batch)} at page {current_page_num} (offset {current_offset}).")
                break
        except RuntimeError as e:
            if "cancelled by user" in str(e).lower():
                logger(f"ℹ️ Pagination stopped due to cancellation: {e}")
            else:
                logger(f"❌ {e}\n   Aborting pagination at page {current_page_num} (offset {current_offset}).")
            break
        except Exception as e:
            logger(f"❌ Unexpected error fetching page {current_page_num} (offset {current_offset}): {e}")
            traceback.print_exc()
            break
        if processed_post_ids:
            original_count = len(posts_batch)
            posts_batch = [post for post in posts_batch if post.get('id') not in processed_post_ids]
            skipped_count = original_count - len(posts_batch)
            if skipped_count > 0:
                logger(f"   Skipped {skipped_count} already processed post(s) from page {current_page_num}.")
        
        if not posts_batch:
            if target_post_id and not processed_target_post_flag:
                logger(f"❌ Target post {target_post_id} not found after checking all available pages (API returned no more posts at offset {current_offset}).")
            elif not target_post_id:
                if current_page_num == (start_page or 1):
                    logger(f"😕 No posts found on the first page checked (page {current_page_num}, offset {current_offset}).")
                else:
                    logger(f"✅ Reached end of posts (no more content from API at offset {current_offset}).")
            break
        if target_post_id and not processed_target_post_flag:
            matching_post = next((p for p in posts_batch if str(p.get('id')) == str(target_post_id)), None)
            if matching_post:
                logger(f"🎯 Found target post {target_post_id} on page {current_page_num} (offset {current_offset}).")
                yield [matching_post]
                processed_target_post_flag = True
        elif not target_post_id:
            yield posts_batch
        if processed_target_post_flag:
            break
        current_offset += page_size
        current_page_num += 1
        time.sleep(0.6)
    if target_post_id and not processed_target_post_flag and not (cancellation_event and cancellation_event.is_set()):
        logger(f"❌ Target post {target_post_id} could not be found after checking all relevant pages (final check after loop).")

