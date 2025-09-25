import threading
import time
import os
import json
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from .api_client import download_from_api
from .workers import PostProcessorWorker
from ..config.constants import (
    STYLE_DATE_BASED, STYLE_POST_TITLE_GLOBAL_NUMBERING,
    MAX_THREADS
)
from ..utils.file_utils import clean_folder_name


class DownloadManager:
    """
    Manages the entire download lifecycle, acting as a bridge between the UI
    and the backend workers. It handles thread pools, task submission,
    and state management for a download session.
    """

    def __init__(self, progress_queue):
        """
        Initializes the DownloadManager.

        Args:
            progress_queue (queue.Queue): A thread-safe queue for sending
                                          status updates to the UI.
        """
        self.progress_queue = progress_queue
        self.thread_pool = None
        self.active_futures = []
        self.cancellation_event = threading.Event()
        self.pause_event = threading.Event()
        self.is_running = False
        
        self.total_posts = 0
        self.processed_posts = 0
        self.total_downloads = 0
        self.total_skips = 0
        self.all_kept_original_filenames = []
        self.creator_profiles_dir = None
        self.current_creator_name_for_profile = None
        self.current_creator_profile_path = None
        self.session_file_path = None

    def _log(self, message):
        """Puts a progress message into the queue for the UI."""
        self.progress_queue.put({'type': 'progress', 'payload': (message,)})

    def start_session(self, config, restore_data=None):
        """
        Starts a new download session based on the provided configuration.
        This is the main entry point called by the UI.

        Args:
            config (dict): A dictionary containing all settings from the UI.
            restore_data (dict, optional): Data from a previous, interrupted session.
        """
        if self.is_running:
            self._log("❌ Cannot start a new session: A session is already in progress.")
            return

        self.session_file_path = config.get('session_file_path')
        creator_profile_data = self._setup_creator_profile(config)
        
        # Save settings to profile at the start of the session
        if self.current_creator_profile_path:
            creator_profile_data['settings'] = config
            creator_profile_data.setdefault('processed_post_ids', [])
            self._save_creator_profile(creator_profile_data)
            self._log(f"✅ Loaded/created profile for '{self.current_creator_name_for_profile}'. Settings saved.")

        self.is_running = True
        self.cancellation_event.clear()
        self.pause_event.clear()
        self.active_futures.clear()
        self.total_posts = 0
        self.processed_posts = 0
        self.total_downloads = 0
        self.total_skips = 0
        self.all_kept_original_filenames = []
        
        is_single_post = bool(config.get('target_post_id_from_initial_url'))
        use_multithreading = config.get('use_multithreading', True)
        is_manga_sequential = config.get('manga_mode_active') and config.get('manga_filename_style') in [STYLE_DATE_BASED, STYLE_POST_TITLE_GLOBAL_NUMBERING]

        should_use_multithreading_for_posts = use_multithreading and not is_single_post and not is_manga_sequential
        
        if should_use_multithreading_for_posts:
            fetcher_thread = threading.Thread(
                target=self._fetch_and_queue_posts_for_pool,
                args=(config, restore_data, creator_profile_data),
                daemon=True
            )
            fetcher_thread.start()
        else:
            # Single-threaded mode does not use the manager's complex logic
            self._log("ℹ️ Manager is handing off to a single-threaded worker...")
            # The single-threaded worker will manage its own lifecycle and signals.
            # The manager's role for this session is effectively over.
            self.is_running = False # Allow another session to start if needed
            self.progress_queue.put({'type': 'handoff_to_single_thread', 'payload': (config,)})


    def _fetch_and_queue_posts_for_pool(self, config, restore_data, creator_profile_data):
        """
        Fetches posts from the API in batches and submits them as tasks to a thread pool.
        This method runs in its own dedicated thread to avoid blocking the UI.
        It provides immediate feedback as soon as the first batch of posts is found.
        """
        try:
            num_workers = min(config.get('num_threads', 4), MAX_THREADS)
            self.thread_pool = ThreadPoolExecutor(max_workers=num_workers, thread_name_prefix='PostWorker_')

            session_processed_ids = set(restore_data.get('processed_post_ids', [])) if restore_data else set()
            profile_processed_ids = set(creator_profile_data.get('processed_post_ids', []))
            processed_ids = session_processed_ids.union(profile_processed_ids)

            if restore_data and 'all_posts_data' in restore_data:
                # This logic for session restore remains as it relies on a pre-fetched list
                all_posts = restore_data['all_posts_data']
                posts_to_process = [p for p in all_posts if p.get('id') not in processed_ids]
                self.total_posts = len(all_posts)
                self.processed_posts = len(processed_ids)
                self._log(f"🔄 Restoring session. {len(posts_to_process)} posts remaining.")
                self.progress_queue.put({'type': 'overall_progress', 'payload': (self.total_posts, self.processed_posts)})
                
                if not posts_to_process:
                    self._log("✅ No new posts to process from restored session.")
                    return

                for post_data in posts_to_process:
                    if self.cancellation_event.is_set(): break
                    worker = PostProcessorWorker(post_data, config, self.progress_queue)
                    future = self.thread_pool.submit(worker.process)
                    future.add_done_callback(self._handle_future_result)
                    self.active_futures.append(future)
            else:
                # --- START: REFACTORED STREAMING LOGIC ---
                post_generator = download_from_api(
                    api_url_input=config['api_url'],
                    logger=self._log,
                    start_page=config.get('start_page'),
                    end_page=config.get('end_page'),
                    manga_mode=config.get('manga_mode_active', False),
                    cancellation_event=self.cancellation_event,
                    pause_event=self.pause_event,
                    use_cookie=config.get('use_cookie', False),
                    cookie_text=config.get('cookie_text', ''),
                    selected_cookie_file=config.get('selected_cookie_file'),
                    app_base_dir=config.get('app_base_dir'),
                    manga_filename_style_for_sort_check=config.get('manga_filename_style'),
                    processed_post_ids=list(processed_ids)
                )

                self.total_posts = 0
                self.processed_posts = 0

                # Process posts in batches as they are yielded by the API client
                for batch in post_generator:
                    if self.cancellation_event.is_set():
                        self._log("   Post fetching cancelled.")
                        break
                    
                    # Filter out any posts that might have been processed since the start
                    posts_in_batch_to_process = [p for p in batch if p.get('id') not in processed_ids]
                    
                    if not posts_in_batch_to_process:
                        continue

                    # Update total count and immediately inform the UI
                    self.total_posts += len(posts_in_batch_to_process)
                    self.progress_queue.put({'type': 'overall_progress', 'payload': (self.total_posts, self.processed_posts)})

                    for post_data in posts_in_batch_to_process:
                        if self.cancellation_event.is_set(): break
                        worker = PostProcessorWorker(post_data, config, self.progress_queue)
                        future = self.thread_pool.submit(worker.process)
                        future.add_done_callback(self._handle_future_result)
                        self.active_futures.append(future)

                if self.total_posts == 0 and not self.cancellation_event.is_set():
                     self._log("✅ No new posts found to process.")

        except Exception as e:
            self._log(f"❌ CRITICAL ERROR in post fetcher thread: {e}")
            self._log(traceback.format_exc())
        finally:
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True)
            self.is_running = False
            self._log("🏁 All processing tasks have completed or been cancelled.") 
            self.progress_queue.put({
                'type': 'finished',
                'payload': (self.total_downloads, self.total_skips, self.cancellation_event.is_set(), self.all_kept_original_filenames)
            })

    def _handle_future_result(self, future: Future):
        """Callback executed when a worker task completes."""
        if self.cancellation_event.is_set():
            return
            
        with threading.Lock(): # Protect shared counters
            self.processed_posts += 1
            try:
                if future.cancelled():
                    self._log("⚠️ A post processing task was cancelled.")
                    self.total_skips += 1
                else:
                    result = future.result()
                    (dl_count, skip_count, kept_originals, 
                     retryable, permanent, history) = result
                    self.total_downloads += dl_count
                    self.total_skips += skip_count
                    self.all_kept_original_filenames.extend(kept_originals)
                    if retryable:
                        self.progress_queue.put({'type': 'retryable_failure', 'payload': (retryable,)})
                    if permanent:
                        self.progress_queue.put({'type': 'permanent_failure', 'payload': (permanent,)})
                    if history:
                        self.progress_queue.put({'type': 'post_processed_history', 'payload': (history,)})
                        post_id = history.get('post_id')
                        if post_id and self.current_creator_profile_path:
                            profile_data = self._setup_creator_profile({'creator_name_for_profile': self.current_creator_name_for_profile, 'session_file_path': self.session_file_path})
                            if post_id not in profile_data.get('processed_post_ids', []):
                                profile_data.setdefault('processed_post_ids', []).append(post_id)
                                self._save_creator_profile(profile_data)

            except Exception as e:
                self._log(f"❌ Worker task resulted in an exception: {e}")
                self.total_skips += 1 # Count errored posts as skipped
            self.progress_queue.put({'type': 'overall_progress', 'payload': (self.total_posts, self.processed_posts)})

    def _setup_creator_profile(self, config):
        """Prepares the path and loads data for the current creator's profile."""
        self.current_creator_name_for_profile = config.get('creator_name_for_profile')
        if not self.current_creator_name_for_profile:
            self._log("⚠️ Cannot create creator profile: Name not provided in config.")
            return {}

        appdata_dir = os.path.dirname(config.get('session_file_path', '.'))
        self.creator_profiles_dir = os.path.join(appdata_dir, "creator_profiles")
        os.makedirs(self.creator_profiles_dir, exist_ok=True)

        safe_filename = clean_folder_name(self.current_creator_name_for_profile) + ".json"
        self.current_creator_profile_path = os.path.join(self.creator_profiles_dir, safe_filename)

        if os.path.exists(self.current_creator_profile_path):
            try:
                with open(self.current_creator_profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self._log(f"❌ Error loading creator profile '{safe_filename}': {e}. Starting fresh.")
        return {}

    def _save_creator_profile(self, data):
        """Saves the provided data to the current creator's profile file."""
        if not self.current_creator_profile_path:
            return
        try:
            temp_path = self.current_creator_profile_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.current_creator_profile_path)
        except OSError as e:
            self._log(f"❌ Error saving creator profile to '{self.current_creator_profile_path}': {e}")

    def cancel_session(self):
        """Cancels the current running session."""
        if not self.is_running:
            return
        
        if self.cancellation_event.is_set():
            self._log("ℹ️ Cancellation already in progress.")
            return

        self._log("⚠️ Cancellation requested by user...")
        self.cancellation_event.set()

        if self.thread_pool:
            self._log("   Signaling all worker threads to stop and shutting down pool...")
            self.thread_pool.shutdown(wait=False)

