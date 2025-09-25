import sys
import os
import time
import queue
import random 
import traceback
import html
import http
import json
import re
import subprocess
import datetime
import requests
import cloudscraper
import unicodedata
from collections import deque, defaultdict
import threading
from concurrent.futures import Future, ThreadPoolExecutor ,CancelledError
from urllib .parse import urlparse 
from PyQt5.QtGui import QIcon, QIntValidator, QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QMessageBox, QListWidget, QRadioButton,
    QButtonGroup, QCheckBox, QSplitter, QGroupBox, QDialog, QStackedWidget,
    QScrollArea, QListWidgetItem, QSizePolicy, QProgressBar, QAbstractItemView, QFrame,
    QMainWindow, QAction, QGridLayout, 
)
try:
    from PIL import Image
except ImportError:
    Image = None

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QSettings, QStandardPaths, QUrl, QSize, QProcess, QMutex, QMutexLocker, QCoreApplication
from ..services.drive_downloader import download_mega_file as drive_download_mega_file ,download_gdrive_file ,download_dropbox_file 
from ..core.workers import DownloadThread as BackendDownloadThread
from ..core.workers import PostProcessorWorker  
from ..core.workers import PostProcessorSignals
from ..core.api_client import download_from_api
from ..core.discord_client import fetch_server_channels, fetch_channel_messages 
from ..core.manager import DownloadManager
from ..core.nhentai_client import fetch_nhentai_gallery
from ..core.bunkr_client import fetch_bunkr_data
from ..core.saint2_client import fetch_saint2_data 
from ..core.erome_client import fetch_erome_data
from ..core.Hentai2read_client import fetch_hentai2read_data
from .assets import get_app_icon_object
from ..config.constants import *
from ..utils.file_utils import KNOWN_NAMES, clean_folder_name
from ..utils.network_utils import extract_post_info, prepare_cookies_for_request
from ..utils.resolution import setup_ui
from ..utils.resolution import get_dark_theme
from ..utils.command import parse_commands_from_text
from ..i18n.translator import get_translation
from .dialogs.EmptyPopupDialog import EmptyPopupDialog
from .dialogs.CookieHelpDialog import CookieHelpDialog
from .dialogs.FavoriteArtistsDialog import FavoriteArtistsDialog
from .dialogs.KnownNamesFilterDialog import KnownNamesFilterDialog
from .dialogs.HelpGuideDialog import HelpGuideDialog
from .dialogs.FutureSettingsDialog import FutureSettingsDialog, CountdownMessageBox
from .dialogs.ErrorFilesDialog import ErrorFilesDialog
from .dialogs.DownloadHistoryDialog import DownloadHistoryDialog
from .dialogs.DownloadExtractedLinksDialog import DownloadExtractedLinksDialog
from .dialogs.FavoritePostsDialog import FavoritePostsDialog
from .dialogs.FavoriteArtistsDialog import FavoriteArtistsDialog
from .dialogs.ConfirmAddAllDialog import ConfirmAddAllDialog
from .dialogs.MoreOptionsDialog import MoreOptionsDialog
from .dialogs.SinglePDF import create_single_pdf_from_content
from .dialogs.discord_pdf_generator import create_pdf_from_discord_messages
from .dialogs.SupportDialog import SupportDialog
from .dialogs.KeepDuplicatesDialog import KeepDuplicatesDialog
from .dialogs.MultipartScopeDialog import MultipartScopeDialog
from .dialogs.ExportLinksDialog import ExportLinksDialog
from .dialogs.CustomFilenameDialog import CustomFilenameDialog

_ff_ver = (datetime.date.today().toordinal() - 735506) // 28
USERAGENT_FIREFOX = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; "
                     f"rv:{_ff_ver}.0) Gecko/20100101 Firefox/{_ff_ver}.0")

class DynamicFilterHolder:
    """A thread-safe class to hold and update character filters during a download."""
    def __init__(self, initial_filters=None):
        self.lock = threading.Lock()
        self._filters = initial_filters if initial_filters is not None else []

    def get_filters(self):
        with self.lock:
            return [dict(f) for f in self._filters]

    def set_filters(self, new_filters):
        with self.lock:
            self._filters = [dict(f) for f in (new_filters if new_filters else [])]


class PostProcessorSignals(QObject):
    """A collection of signals for the DownloaderApp to communicate with itself across threads."""
    progress_signal = pyqtSignal(str)
    file_download_status_signal = pyqtSignal(bool)
    external_link_signal = pyqtSignal(str, str, str, str, str)
    file_progress_signal = pyqtSignal(str, object)
    file_successfully_downloaded_signal = pyqtSignal(dict)
    missed_character_post_signal = pyqtSignal(str, str)
    worker_finished_signal = pyqtSignal(tuple)
    finished_signal = pyqtSignal(int, int, bool, list)
    retryable_file_failed_signal = pyqtSignal(list)
    permanent_file_failed_signal = pyqtSignal(list)

class DownloaderApp (QWidget ):
    character_prompt_response_signal =pyqtSignal (bool )
    log_signal =pyqtSignal (str )
    add_character_prompt_signal =pyqtSignal (str )
    overall_progress_signal =pyqtSignal (int ,int )
    file_successfully_downloaded_signal =pyqtSignal (dict )
    post_processed_for_history_signal =pyqtSignal (dict )
    finished_signal =pyqtSignal (int ,int ,bool ,list )
    external_link_signal =pyqtSignal (str ,str ,str ,str ,str )
    file_progress_signal =pyqtSignal (str ,object )
    fetch_only_complete_signal = pyqtSignal(list)


    def __init__(self):
        super().__init__()
        self.settings = QSettings(CONFIG_ORGANIZATION_NAME, CONFIG_APP_NAME_MAIN)
        self.active_update_profile = None
        self.new_posts_for_update = []
        self.is_finishing = False 
        self.finish_lock = threading.Lock() 

        saved_res = self.settings.value(RESOLUTION_KEY, "Auto")
        if saved_res != "Auto":
            try:
                width, height = map(int, saved_res.split('x'))
                self.resize(width, height)
                self._center_on_screen() 
            except ValueError:
                self.log_signal.emit(f"⚠️ Invalid saved resolution '{saved_res}'. Using default.")

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            self.app_base_dir = os.path.dirname(sys.executable)
        else:
            self.app_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

        executable_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else self.app_base_dir
        user_data_path = os.path.join(executable_dir, "appdata")
        os.makedirs(user_data_path, exist_ok=True) 

        self.config_file = os.path.join(user_data_path, "Known.txt")
        self.session_file_path = os.path.join(user_data_path, "session.json")
        self.persistent_history_file = os.path.join(user_data_path, "download_history.json")

        self.download_thread = None
        self.thread_pool = None
        self.cancellation_event = threading.Event()
        self.session_lock = threading.Lock()
        self.interrupted_session_data = None
        self.is_restore_pending = False
        self.external_link_download_thread = None
        self.pause_event = threading.Event()
        self.active_futures = []
        self.total_posts_to_process = 0
        self.dynamic_character_filter_holder = DynamicFilterHolder()
        self.processed_posts_count = 0
        self.creator_name_cache = {}
        self.log_signal.emit(f"ℹ️ App base directory: {self.app_base_dir}")
        self.log_signal.emit(f"ℹ️ Persistent history file path set to: {self.persistent_history_file}")
        self.last_downloaded_files_details = deque(maxlen=3)
        self.download_history_candidates = deque(maxlen=8)
        self.final_download_history_entries = []
        self.favorite_download_queue = deque()
        self.is_processing_favorites_queue = False
        self.current_processing_favorite_item_info = None 
        self.download_counter = 0
        self.permanently_failed_files_for_dialog = []
        self.last_link_input_text_for_queue_sync = ""
        self.is_fetcher_thread_running = False
        self._restart_pending = False
        self.download_history_log = deque(maxlen=50)
        self.skip_counter = 0
        self.all_kept_original_filenames = []
        self.cancellation_message_logged_this_session = False
        self.favorite_scope_toggle_button = None
        self.favorite_download_scope = FAVORITE_SCOPE_SELECTED_LOCATION
        self.manga_mode_checkbox = None
        self.selected_cookie_filepath = None
        self.retryable_failed_files_info = []
        self.is_paused = False
        self.worker_to_gui_queue = queue.Queue()
        self.gui_update_timer = QTimer(self)
        self.actual_gui_signals = PostProcessorSignals()
        self.worker_signals = PostProcessorSignals()
        self.prompt_mutex = QMutex()
        self._add_character_response = None
        self._original_scan_content_tooltip = ("If checked, the downloader will scan the HTML content of posts for image URLs (from <img> tags or direct links).\n"
                                               "now This includes resolving relative paths from <img> tags to full URLs.\n"
                                               "Relative paths in <img> tags (e.g., /data/image.jpg) will be resolved to full URLs.\n"
                                               "Useful for cases where images are in the post description but not in the API's file/attachment list.")
        self.downloaded_files = set()
        self.downloaded_files_lock = threading.Lock()
        self.downloaded_file_hashes = set()
        self.downloaded_file_hashes_lock = threading.Lock()
        self.show_external_links = False
        self.external_link_queue = deque()
        self._is_processing_external_link_queue = False
        self._current_link_post_title = None
        self.extracted_links_cache = []
        self.manga_rename_toggle_button = None
        self.favorite_mode_checkbox = None
        self.url_or_placeholder_stack = None
        self.url_input_widget = None
        self.url_placeholder_widget = None
        self.favorite_action_buttons_widget = None
        self.favorite_mode_artists_button = None
        self.favorite_mode_posts_button = None
        self.standard_action_buttons_widget = None
        self.bottom_action_buttons_stack = None
        self.main_log_output = None
        self.external_log_output = None
        self.log_splitter = None
        self.main_splitter = None
        self.reset_button = None
        self.progress_log_label = None
        self.log_verbosity_toggle_button = None
        self.missed_character_log_output = None
        self.log_view_stack = None
        self.current_log_view = 'progress'
        self.link_search_input = None
        self.link_search_button = None
        self.export_links_button = None
        self.radio_only_links = None
        self.radio_only_archives = None
        self.missed_title_key_terms_count = {}
        self.missed_title_key_terms_examples = {}
        self.logged_summary_for_key_term = set()
        self.STOP_WORDS = set(["a", "an", "the", "is", "was", "were", "of", "for", "with", "in", "on", "at", "by", "to", "and", "or", "but", "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her", "its", "our", "their", "com", "net", "org", "www"])
        self.already_logged_bold_key_terms = set()
        self.missed_key_terms_buffer = []
        self.char_filter_scope_toggle_button = None
        self.skip_words_scope = SKIP_SCOPE_POSTS
        self.char_filter_scope = CHAR_SCOPE_TITLE
        self.manga_filename_style = self.settings.value(MANGA_FILENAME_STYLE_KEY, STYLE_POST_TITLE, type=str)
        self.custom_manga_filename_format = self.settings.value(MANGA_CUSTOM_FORMAT_KEY, "{published} {title}", type=str)        
        self.manga_custom_date_format = self.settings.value(MANGA_CUSTOM_DATE_FORMAT_KEY, "YYYY-MM-DD", type=str) 
        self.current_theme = self.settings.value(THEME_KEY, "dark", type=str)
        self.only_links_log_display_mode = LOG_DISPLAY_LINKS
        self.mega_download_log_preserved_once = False
        self.allow_multipart_download_setting = False
        self.multipart_scope = 'both'
        self.multipart_parts_count = 4     
        self.multipart_min_size_mb = 100 
        self.use_cookie_setting = False
        self.scan_content_images_setting = self.settings.value(SCAN_CONTENT_IMAGES_KEY, False, type=bool)
        self.cookie_text_setting = ""
        self.current_selected_language = self.settings.value(LANGUAGE_KEY, "en", type=str)
        self.more_filter_scope = None 
        self.text_export_format = 'pdf'
        self.single_pdf_setting = False
        self.keep_duplicates_mode = DUPLICATE_HANDLING_HASH
        self.keep_duplicates_limit = 0 
        self.downloaded_hash_counts = defaultdict(int)
        self.downloaded_hash_counts_lock = threading.Lock()
        self.session_temp_files = []
        self.single_pdf_mode = False
        self.save_creator_json_enabled_this_session = True 
        self.date_prefix_format = self.settings.value(DATE_PREFIX_FORMAT_KEY, "YYYY-MM-DD {post}", type=str)
        self.is_single_post_session = False 
        self.discord_download_scope = 'files' 
        self.is_fetching_only = False
        self.fetched_posts_for_download = []
        self.is_ready_to_download_fetched = False 
        self.last_logged_filter_mode = None
        self.last_logged_external_link_status = None


        print(f"ℹ️ Known.txt will be loaded/saved at: {self.config_file}")

        try:
            base_path_for_icon = ""
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_path_for_icon = sys._MEIPASS
            else:
                base_path_for_icon = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            
            icon_path_for_window = os.path.join(base_path_for_icon, 'assets', 'Kemono.ico')
            
            if os.path.exists(icon_path_for_window):
                self.setWindowIcon(QIcon(icon_path_for_window))
            else:
                if getattr(sys, 'frozen', False):
                    executable_dir = os.path.dirname(sys.executable)
                    fallback_icon_path = os.path.join(executable_dir, 'assets', 'Kemono.ico')
                    if os.path.exists(fallback_icon_path):
                        self.setWindowIcon(QIcon(fallback_icon_path))
                    else:
                        self.log_signal.emit(f"⚠️ Main window icon 'assets/Kemono.ico' not found at {icon_path_for_window} or {fallback_icon_path}")
                else:
                    self.log_signal.emit(f"⚠️ Main window icon 'assets/Kemono.ico' not found at {icon_path_for_window}")
        except Exception as e_icon_app:
            self.log_signal.emit(f"❌ Error setting main window icon in DownloaderApp init: {e_icon_app}")

        self.url_label_widget = None
        self.download_location_label_widget = None
        self.remove_from_filename_label_widget = None
        self.skip_words_label_widget = None
        self.setWindowTitle("Kemono Downloader v7.2.0")
        setup_ui(self)
        self._connect_signals()
        if hasattr(self, 'character_input'):
            self.character_input.setToolTip(self._tr("character_input_tooltip", "Enter character names (comma-separated)..."))
        self.log_signal.emit(f"ℹ️ Manga filename style loaded: '{self.manga_filename_style}'")
        self.log_signal.emit(f"ℹ️ Skip words scope loaded: '{self.skip_words_scope}'")
        self.log_signal.emit(f"ℹ️ Character filter scope set to default: '{self.char_filter_scope}'")
        self.log_signal.emit(f"ℹ️ Multi-part download defaults to: {'Enabled' if self.allow_multipart_download_setting else 'Disabled'}")
        self.log_signal.emit(f"ℹ️ Scan post content for images defaults to: {'Enabled' if self.scan_content_images_setting else 'Disabled'}")
        self.log_signal.emit(f"ℹ️ Application language loaded: '{self.current_selected_language.upper()}' (UI may not reflect this yet).")
        self._retranslate_main_ui()
        self._load_persistent_history()
        self._load_saved_download_location()
        self._load_saved_cookie_settings() 
        self._update_button_states_and_connections()
        self._check_for_interrupted_session()
        self._cleanup_after_update() 

    def _run_discord_file_download_thread(self, session, server_id, channel_id, token, output_dir, message_limit=None):
        """
        Runs in a background thread to fetch and download all files from a Discord channel.
        """
        def queue_logger(message):
            self.worker_to_gui_queue.put({'type': 'progress', 'payload': (message,)})

        def queue_progress_label_update(message):
            self.worker_to_gui_queue.put({'type': 'set_progress_label', 'payload': (message,)})

        def check_events():
            if self.cancellation_event.is_set():
                return True # Stop
            while self.pause_event.is_set():
                time.sleep(0.5) # Wait while paused
                if self.cancellation_event.is_set():
                    return True # Allow cancelling while paused
            return False # Continue

        download_count = 0
        skip_count = 0
        
        try:
            queue_logger("=" * 40)
            queue_logger(f"🚀 Starting Discord download for channel: {channel_id}")
            queue_progress_label_update("Fetching messages...")

            def fetch_discord_api(endpoint):
                headers = {
                    'Authorization': token,
                    'User-Agent': USERAGENT_FIREFOX,
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.5',
                }
                try:
                    response = session.get(f"https://discord.com/api/v10{endpoint}", headers=headers)
                    response.raise_for_status()
                    return response.json()
                except Exception:
                    return None

            last_message_id = None
            all_messages = []
            
            while True:
                if check_events(): break
                
                url_endpoint = f"/channels/{channel_id}/messages?limit=100"
                if last_message_id:
                    url_endpoint += f"&before={last_message_id}"
                
                message_batch = fetch_discord_api(url_endpoint)
                if not message_batch:
                    break
                
                all_messages.extend(message_batch)
                
                if message_limit and len(all_messages) >= message_limit:
                    queue_logger(f"   Reached message limit of {message_limit}. Halting fetch.")
                    all_messages = all_messages[:message_limit]
                    break

                last_message_id = message_batch[-1]['id']
                queue_progress_label_update(f"Fetched {len(all_messages)} messages...")
                time.sleep(1)

            if self.cancellation_event.is_set():
                self.finished_signal.emit(0, 0, True, [])
                return

            queue_progress_label_update(f"Collected {len(all_messages)} messages. Starting downloads...")
            total_attachments = sum(len(m.get('attachments', [])) for m in all_messages)
            
            for message in reversed(all_messages):
                if check_events(): break
                for attachment in message.get('attachments', []):
                    if check_events(): break
                    
                    file_url = attachment['url']
                    original_filename = attachment['filename']
                    filepath = os.path.join(output_dir, original_filename)
                    filename_to_use = original_filename

                    counter = 1
                    base_name, extension = os.path.splitext(original_filename)
                    while os.path.exists(filepath):
                        filename_to_use = f"{base_name} ({counter}){extension}"
                        filepath = os.path.join(output_dir, filename_to_use)
                        counter += 1
                    
                    if filename_to_use != original_filename:
                        queue_logger(f"   -> Duplicate name '{original_filename}'. Saving as '{filename_to_use}'.")

                    try:
                        queue_logger(f"   Downloading ({download_count+1}/{total_attachments}): '{filename_to_use}'...")
                        response = requests.get(file_url, stream=True, timeout=60)
                        response.raise_for_status()
                        
                        download_cancelled = False
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if check_events():
                                    download_cancelled = True
                                    break
                                f.write(chunk)
                        
                        if download_cancelled:
                            queue_logger(f"   Download cancelled for '{filename_to_use}'. Deleting partial file.")
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            continue # Move to the next attachment
                        
                        download_count += 1
                    except Exception as e:
                        queue_logger(f"   ❌ Failed to download '{filename_to_use}': {e}")
                        skip_count += 1
        
        finally:
            self.finished_signal.emit(download_count, skip_count, self.cancellation_event.is_set(), [])

    def _cleanup_after_update(self):
        """Deletes the old executable after a successful update."""
        try:
            app_path = sys.executable
            old_app_path = os.path.join(os.path.dirname(app_path), "Kemono.Downloader.exe.old")
            if os.path.exists(old_app_path):
                os.remove(old_app_path)
                self.log_signal.emit("ℹ️ Cleaned up old application file after update.")
        except Exception as e:
            self.log_signal.emit(f"⚠️ Could not remove old application file: {e}")

    def _apply_theme_and_restart_prompt(self):
        """Applies the theme and prompts the user to restart."""
        if self.current_theme == "dark":
            scale = getattr(self, 'scale_factor', 1)
            self.setStyleSheet(get_dark_theme(scale))
        else:
            self.setStyleSheet("")
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle(self._tr("theme_change_title", "Theme Changed"))
        msg_box.setText(self._tr("language_change_message", "A restart is required for these changes to take effect."))
        msg_box.setInformativeText(self._tr("language_change_informative", "Would you like to restart now?"))
        restart_button = msg_box.addButton(self._tr("restart_now_button", "Restart Now"), QMessageBox.ApplyRole)
        ok_button = msg_box.addButton(self._tr("ok_button", "OK"), QMessageBox.AcceptRole)
        msg_box.setDefaultButton(ok_button)
        msg_box.exec_()

        if msg_box.clickedButton() == restart_button:
            self._request_restart_application()

    def _setup_creator_profile(self, creator_name, session_file_path):
        """Prepares the path and loads data for the current creator's profile."""
        if not creator_name:
            self.log_signal.emit("⚠️ Cannot create creator profile: Name not provided.")
            return {}

        appdata_dir = os.path.dirname(session_file_path)
        creator_profiles_dir = os.path.join(appdata_dir, "creator_profiles")
        os.makedirs(creator_profiles_dir, exist_ok=True)

        safe_filename = clean_folder_name(creator_name) + ".json"
        profile_path = os.path.join(creator_profiles_dir, safe_filename)

        if os.path.exists(profile_path):
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.log_signal.emit(f"❌ Error loading creator profile '{safe_filename}': {e}. Starting fresh.")
        return {}

    def _save_creator_profile(self, creator_name, data, session_file_path):
        """Saves the provided data to the current creator's profile file."""
        if not creator_name:
            return
        
        appdata_dir = os.path.dirname(session_file_path)
        creator_profiles_dir = os.path.join(appdata_dir, "creator_profiles")
        safe_filename = clean_folder_name(creator_name) + ".json"
        profile_path = os.path.join(creator_profiles_dir, safe_filename)

        try:
            temp_path = profile_path + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, profile_path)
        except OSError as e:
            self.log_signal.emit(f"❌ Error saving creator profile to '{profile_path}': {e}")

    def _create_initial_session_file(self, api_url_for_session, override_output_dir_for_session, remaining_queue=None):
        """Creates the initial session file at the start of a new download."""
        if self.is_restore_pending:
            return

        self.log_signal.emit("📝 Creating initial session file for this download...")
        initial_ui_settings = self._get_current_ui_settings_as_dict(
            api_url_override=api_url_for_session,
            output_dir_override=override_output_dir_for_session
        )

        session_data = {
            "ui_settings": initial_ui_settings,
            "download_state": {
                "processed_post_ids": [],
                "permanently_failed_files": [],
                "successfully_downloaded_hashes": [], 
                "last_processed_offset": 0,  
                "manga_counters": {
                    "date_based": 1,
                    "global_numbering": 1
                }
            },
            "remaining_queue": list(remaining_queue) if remaining_queue else []
        }    
        self._save_session_file(session_data)

    def get_checkbox_map(self):
        """Returns a mapping of checkbox attribute names to their corresponding settings key."""
        return {
            'skip_zip_checkbox': 'skip_zip',
            'download_thumbnails_checkbox': 'download_thumbnails',
            'compress_images_checkbox': 'compress_images',
            'use_subfolders_checkbox': 'use_subfolders',
            'use_subfolder_per_post_checkbox': 'use_post_subfolders',
            'use_multithreading_checkbox': 'use_multithreading',
            'external_links_checkbox': 'show_external_links',
            'keep_duplicates_checkbox': 'keep_in_post_duplicates',
            'date_prefix_checkbox': 'use_date_prefix_for_subfolder',
            'manga_mode_checkbox': 'manga_mode_active',
            'scan_content_images_checkbox': 'scan_content_for_images',
            'use_cookie_checkbox': 'use_cookie',
            'favorite_mode_checkbox': 'favorite_mode_active'
        }

    def _get_current_ui_settings_as_dict(self, api_url_override=None, output_dir_override=None):
        """Gathers all relevant UI settings into a JSON-serializable dictionary."""
        settings = {}
        
        settings['api_url'] = api_url_override if api_url_override is not None else self.link_input.text().strip()
        settings['output_dir'] = output_dir_override if output_dir_override is not None else self.dir_input.text().strip()
        settings['character_filter_text'] = self.character_input.text().strip()
        settings['skip_words_text'] = self.skip_words_input.text().strip()
        settings['remove_words_text'] = self.remove_from_filename_input.text().strip()
        settings['custom_folder_name'] = self.custom_folder_input.text().strip()
        settings['cookie_text'] = self.cookie_text_input.text().strip()
        if hasattr(self, 'manga_date_prefix_input'):
            settings['manga_date_prefix'] = self.manga_date_prefix_input.text().strip()
        
        try: settings['num_threads'] = int(self.thread_count_input.text().strip())
        except (ValueError, AttributeError): settings['num_threads'] = 4
        try: settings['start_page'] = int(self.start_page_input.text().strip()) if self.start_page_input.text().strip() else None
        except (ValueError, AttributeError): settings['start_page'] = None
        try: settings['end_page'] = int(self.end_page_input.text().strip()) if self.end_page_input.text().strip() else None
        except (ValueError, AttributeError): settings['end_page'] = None

        for checkbox_name, key in self.get_checkbox_map().items():
            if checkbox := getattr(self, checkbox_name, None): settings[key] = checkbox.isChecked()

        settings['filter_mode'] = self.get_filter_mode()
        settings['only_links'] = self.radio_only_links.isChecked()

        settings['skip_words_scope'] = self.skip_words_scope
        settings['char_filter_scope'] = self.char_filter_scope
        settings['manga_filename_style'] = self.manga_filename_style
        settings['allow_multipart_download'] = self.allow_multipart_download_setting
        settings['more_filter_scope'] = self.more_filter_scope
        settings['text_export_format'] = self.text_export_format
        settings['single_pdf_setting'] = self.single_pdf_setting
        settings['keep_duplicates_mode'] = self.keep_duplicates_mode
        settings['keep_duplicates_limit'] = self.keep_duplicates_limit
        
        return settings


    def _tr (self ,key ,default_text =""):
        """Helper to get translation based on current app language for the main window."""
        if callable (get_translation ):
            return get_translation (self .current_selected_language ,key ,default_text )
        return default_text 

    def _load_saved_download_location (self ):
        saved_location =self .settings .value (DOWNLOAD_LOCATION_KEY ,"",type =str )
        if saved_location and os .path .isdir (saved_location ):
            if hasattr (self ,'dir_input')and self .dir_input :
                self .dir_input .setText (saved_location )
                self .log_signal .emit (f"ℹ️ Loaded saved download location: {saved_location }")
            else :
                self .log_signal .emit (f"⚠️ Found saved download location '{saved_location }', but dir_input not ready.")
        elif saved_location :
            self .log_signal .emit (f"⚠️ Found saved download location '{saved_location }', but it's not a valid directory. Ignoring.")

    def _check_for_interrupted_session(self):
        """Checks for an incomplete session file on startup and prepares the UI for restore if found."""
        if os.path.exists(self.session_file_path):
            try:
                with open(self.session_file_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                if "ui_settings" not in session_data or "download_state" not in session_data:
                    raise ValueError("Invalid session file structure.")

                failed_files_from_session = session_data.get('download_state', {}).get('permanently_failed_files', [])
                if failed_files_from_session:
                    self.permanently_failed_files_for_dialog.clear()
                    self.permanently_failed_files_for_dialog.extend(failed_files_from_session)
                    self.log_signal.emit(f"ℹ️ Restored {len(failed_files_from_session)} failed file entries from the previous session.")

                remaining_queue_from_session = session_data.get('remaining_queue', [])
                if remaining_queue_from_session:
                    self.favorite_download_queue.clear()
                    self.favorite_download_queue.extend(remaining_queue_from_session)
                    self.log_signal.emit(f"ℹ️ Restored {len(self.favorite_download_queue)} creator(s) to the download queue.")

                self.interrupted_session_data = session_data
                self.log_signal.emit("ℹ️ Incomplete download session found. UI updated for restore.")
                self._prepare_ui_for_restore()

            except Exception as e:
                self.log_signal.emit(f"❌ Error reading session file: {e}. Deleting corrupt session file.")
                os.remove(self.session_file_path)
                self.interrupted_session_data = None
                self.is_restore_pending = False

    def _prepare_ui_for_restore(self):
        """Configures the UI to a 'restore pending' state."""
        if not self.interrupted_session_data:
            return

        self.log_signal.emit("   UI updated for session restore.")
        settings = self.interrupted_session_data.get("ui_settings", {})
        self._load_ui_from_settings_dict(settings)
        
        self.is_restore_pending = True
        self._update_button_states_and_connections()

    def _clear_session_and_reset_ui(self):
        """Clears the session file and resets the UI to its default state."""
        self._clear_session_file()
        self.interrupted_session_data = None
        self.is_restore_pending = False
        self._update_button_states_and_connections()
        self.reset_application_state()

    def _clear_session_file(self):
        """Safely deletes the session file."""
        if os.path.exists(self.session_file_path):
            try:
                os.remove(self.session_file_path)
                self.log_signal.emit("ℹ️ Interrupted session file cleared.")
            except Exception as e:
                self.log_signal.emit(f"❌ Failed to clear session file: {e}")

    def _save_session_file(self, session_data):
        """Safely saves the session data to the session file using an atomic write pattern."""
        temp_session_file_path = self.session_file_path + ".tmp"
        try:
            if 'download_state' in session_data:
                with self.downloaded_file_hashes_lock:
                    session_data['download_state']['successfully_downloaded_hashes'] = list(self.downloaded_file_hashes)
            with open(temp_session_file_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2)
            os.replace(temp_session_file_path, self.session_file_path)
        except Exception as e:
            self.log_signal.emit(f"❌ Failed to save session state: {e}")
            if os.path.exists(temp_session_file_path):
                try:
                    os.remove(temp_session_file_path)
                except Exception as e_rem:
                    self.log_signal.emit(f"❌ Failed to remove temp session file: {e_rem}")

    def _update_button_states_and_connections(self):
        try:
            self.download_btn.clicked.disconnect()
            self.pause_btn.clicked.disconnect()
            self.cancel_btn.clicked.disconnect()
        except TypeError: pass

        is_download_active = self._is_download_active()
        fetch_first_enabled = self.settings.value(FETCH_FIRST_KEY, False, type=bool)
        print(f"--- DEBUG: Updating buttons (is_download_active={is_download_active}) ---")

        if self.is_ready_to_download_fetched:
            num_posts = len(self.fetched_posts_for_download)
            self.download_btn.setText(f"⬇️ Start Download ({num_posts} Posts)")
            self.download_btn.setEnabled(True)
            self.download_btn.clicked.connect(self.start_download)
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setText("🗑️ Clear Fetch")
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.connect(self.reset_application_state)
            return  # <-- This 'return' is CRITICAL

        if self.active_update_profile and self.new_posts_for_update and not is_download_active:
            # State: Update confirmation (new posts found, waiting for user to start)
            num_new = len(self.new_posts_for_update)
            self.download_btn.setText(self._tr("start_download_new_button_text", f"⬇️ Start Download ({num_new} new)"))
            self.download_btn.setEnabled(True)
            self.download_btn.clicked.connect(self.start_download)
            self.download_btn.setToolTip(self._tr("start_download_new_tooltip", "Click to download the new posts found."))

            self.pause_btn.setText(self._tr("pause_download_button_text", "⏸️ Pause Download"))
            self.pause_btn.setEnabled(False)

            self.cancel_btn.setText(self._tr("clear_selection_button_text", "🗑️ Clear Selection"))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.connect(self._clear_update_selection)
            self.cancel_btn.setToolTip(self._tr("clear_selection_tooltip", "Click to cancel the update and clear the selection."))

        elif self.active_update_profile and not is_download_active:
            # State: Update check (profile loaded, waiting for user to check)
            self.download_btn.setText(self._tr("check_for_updates_button_text", "🔄 Check For Updates"))
            self.download_btn.setEnabled(True)
            self.download_btn.clicked.connect(self.start_download)
            self.download_btn.setToolTip(self._tr("check_for_updates_tooltip", "Click to check for new posts from this creator."))

            self.pause_btn.setText(self._tr("pause_download_button_text", "⏸️ Pause Download"))
            self.pause_btn.setEnabled(False)

            self.cancel_btn.setText(self._tr("clear_selection_button_text", "🗑️ Clear Selection"))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.connect(self._clear_update_selection)
            self.cancel_btn.setToolTip(self._tr("clear_selection_tooltip", "Click to clear the loaded creator profile and return to normal mode."))

        elif self.is_restore_pending:
            self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
            self.download_btn.setEnabled(True)
            self.download_btn.clicked.connect(self.start_download)
            self.download_btn.setToolTip(self._tr("start_download_discard_tooltip", "Click to start a new download, discarding the previous session."))

            self.pause_btn.setText(self._tr("restore_download_button_text", "🔄 Restore Download"))
            self.pause_btn.setEnabled(True)
            self.pause_btn.clicked.connect(self.restore_download)
            self.pause_btn.setToolTip(self._tr("restore_download_button_tooltip", "Click to restore the interrupted download."))

            self.cancel_btn.setText(self._tr("discard_session_button_text", "🗑️ Discard Session"))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.connect(self._clear_session_and_reset_ui)
            self.cancel_btn.setToolTip(self._tr("discard_session_tooltip", "Click to discard the interrupted session and reset the UI."))

        elif is_download_active:
            print("  --> Button state: ACTIVE DOWNLOAD/FETCH")
            if self.is_fetching_only:
                self.download_btn.setText("⏳ Fetching Pages...")
                self.download_btn.setEnabled(False)
                self.pause_btn.setEnabled(False)
            else:
                # --- START MODIFICATION ---
                # Check if we are about to download fetched posts and update text accordingly
                if self.is_ready_to_download_fetched:
                    num_posts = len(self.fetched_posts_for_download)
                    self.download_btn.setText(f"⬇️ Start Download ({num_posts} Posts)")
                    self.download_btn.setEnabled(True) # Keep it enabled for the user to click
                else:
                    # Original logic for an active download in other scenarios
                    self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
                    self.download_btn.setEnabled(False)
                
                self.pause_btn.setText(self._tr("resume_download_button_text", "▶️ Resume Download") if self.is_paused else self._tr("pause_download_button_text", "⏸️ Pause Download"))
                self.pause_btn.setEnabled(True)
                self.pause_btn.clicked.connect(self._handle_pause_resume_action)
            print("  --> Button state: IDLE")

            self.cancel_btn.setText(self._tr("cancel_button_text", "❌ Cancel & Reset UI"))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.connect(self.cancel_download_button_action)
        
        else:
            url_text = self.link_input.text().strip()
            _, _, post_id = extract_post_info(url_text)
            is_single_post = bool(post_id)

            if fetch_first_enabled and not is_single_post:
                self.download_btn.setText("📄 Fetch Pages")
            else:
                self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
            
            self.download_btn.setEnabled(True)
            self.download_btn.clicked.connect(self.start_download)
            self.pause_btn.setText(self._tr("pause_download_button_text", "⏸️ Pause Download"))
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setText(self._tr("cancel_button_text", "❌ Cancel & Reset UI"))
            self.cancel_btn.setEnabled(False)

    def _run_fetch_only_thread(self, fetch_args):
        """
        Runs in a background thread to ONLY fetch all posts without downloading.
        """
        all_posts = []
        try:
            post_generator = download_from_api(**fetch_args)
            for post_batch in post_generator:
                if self.cancellation_event.is_set():
                    break
                all_posts.extend(post_batch)
        except Exception as e:
            self.log_signal.emit(f"❌ Error during fetch-only operation: {e}")
        finally:
            self.fetch_only_complete_signal.emit(all_posts)

    def _fetch_only_finished(self, fetched_posts):
        """
        Called on the main thread when the fetch-only operation is complete.
        Updates the UI to the 'ready to download' state.
        """
        print("\n--- DEBUG: Entering _fetch_only_finished ---\n")
        self.download_thread = None        
        self.is_fetching_only = False

        if self.cancellation_event.is_set():
            self.log_signal.emit("ℹ️ Page fetching was cancelled.")
            self._update_button_states_and_connections()
            self.set_ui_enabled(True)
            return

        self.fetched_posts_for_download = fetched_posts
        self.is_ready_to_download_fetched = True
        self.log_signal.emit(f"✅ Fetch complete. Found {len(self.fetched_posts_for_download)} posts.")
        self.log_signal.emit("=" * 40)
        self.log_signal.emit("✅ Stage 1 complete. All post data has been fetched.")
        self.log_signal.emit("   💡 You can now disconnect your VPN (if used) before starting the download.")
        self.log_signal.emit("   Press the 'Start Download' button to begin Stage 2: Downloading files.")
        self.progress_label.setText(f"Found {len(self.fetched_posts_for_download)} posts. Ready to download.")
        
        self._update_button_states_and_connections()
        self.set_ui_enabled(True)

    def _start_download_of_fetched_posts(self):
        """
        Initiates the download of the posts that were previously fetched.
        """
        self.is_ready_to_download_fetched = False  # Reset the state flag
        self.log_signal.emit("=" * 40)
        self.log_signal.emit(f"🚀 Starting Stage 2: Downloading files for {len(self.fetched_posts_for_download)} fetched posts.")
        self.log_signal.emit("   💡 If you disconnected your VPN, downloads will now use your regular connection.")

        raw_character_filters_text = self.character_input.text().strip()
        parsed_filters, download_commands = self._parse_character_filters(raw_character_filters_text)
        domain_override = download_commands.get('domain_override')
        
        args_template = self.last_start_download_args
        
        # Update both the character filter list and the domain override in the arguments
        args_template['filter_character_list'] = parsed_filters
        args_template['domain_override'] = domain_override
        
        # Manually set the UI to a "downloading" state for reliability
        self.set_ui_enabled(False)
        self.download_btn.setText("⬇️ Downloading...")
        self.download_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("❌ Cancel & Reset UI")
        try:
            # Ensure signals are connected to the correct actions for this state
            self.cancel_btn.clicked.disconnect()
            self.pause_btn.clicked.disconnect()
        except TypeError:
            pass
        self.cancel_btn.clicked.connect(self.cancel_download_button_action)
        self.pause_btn.clicked.connect(self._handle_pause_resume_action)

        args_template = self.last_start_download_args
        args_template['fetch_first'] = False

        num_threads = int(self.thread_count_input.text()) if self.use_multithreading_checkbox.isChecked() else 1
        self.thread_pool = ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix='PostWorker_')

        self.total_posts_to_process = len(self.fetched_posts_for_download)
        self.processed_posts_count = 0
        self.overall_progress_signal.emit(self.total_posts_to_process, 0)

        ppw_expected_keys = list(PostProcessorWorker.__init__.__code__.co_varnames)[1:]

        for post_data in self.fetched_posts_for_download:
            self._submit_post_to_worker_pool(
                post_data, args_template, 1, self.worker_to_gui_queue, ppw_expected_keys, {}
            )

        self.fetched_posts_for_download = []
        self.is_fetcher_thread_running = False
        self._check_if_all_work_is_done()

    def update_discord_button_visibility(self, text=""):
        if not hasattr(self, 'save_discord_as_pdf_btn'):
            return
        url_text = self.link_input.text().strip()
        service, _, _ = extract_post_info(url_text)
        is_discord = (service == 'discord')
        self.save_discord_as_pdf_btn.setVisible(is_discord)

    def _clear_update_selection(self):
        """Clears the loaded creator profile and fully resets the UI to its default state."""
        self.log_signal.emit("ℹ️ Update selection cleared. Resetting UI to defaults.")
        self.active_update_profile = None
        self.new_posts_for_update = []
        self._perform_soft_ui_reset()

    def _retranslate_main_ui (self ):
        """Retranslates static text elements in the main UI."""
        if self .url_label_widget :
            self .url_label_widget .setText (self ._tr ("creator_post_url_label","🔗 Kemono Creator/Post URL:"))
        if self .download_location_label_widget :
            self .download_location_label_widget .setText (self ._tr ("download_location_label","📁 Download Location:"))
        if hasattr (self ,'character_label')and self .character_label :
            self .character_label .setText (self ._tr ("filter_by_character_label","🎯 Filter by Character(s) (comma-separated):"))
        if self .skip_words_label_widget :
            self .skip_words_label_widget .setText (self ._tr ("skip_with_words_label","🚫 Skip with Words (comma-separated):"))
        if self .remove_from_filename_label_widget :
            self .remove_from_filename_label_widget .setText (self ._tr ("remove_words_from_name_label","✂️ Remove Words from name:"))
        if hasattr (self ,'radio_all'):self .radio_all .setText (self ._tr ("filter_all_radio","All"))
        if hasattr (self ,'radio_images'):self .radio_images .setText (self ._tr ("filter_images_radio","Images/GIFs"))
        if hasattr (self ,'radio_videos'):self .radio_videos .setText (self ._tr ("filter_videos_radio","Videos"))
        if hasattr (self ,'radio_only_archives'):self .radio_only_archives .setText (self ._tr ("filter_archives_radio","📦 Only Archives"))
        if hasattr (self ,'radio_only_links'):self .radio_only_links .setText (self ._tr ("filter_links_radio","🔗 Only Links"))
        if hasattr (self ,'radio_only_audio'):self .radio_only_audio .setText (self ._tr ("filter_audio_radio","🎧 Only Audio"))
        if hasattr (self ,'favorite_mode_checkbox'):self .favorite_mode_checkbox .setText (self ._tr ("favorite_mode_checkbox_label","⭐ Favorite Mode"))
        if hasattr (self ,'dir_button'):self .dir_button .setText (self ._tr ("browse_button_text","Browse..."))
        self ._update_char_filter_scope_button_text ()
        self ._update_skip_scope_button_text ()

        if hasattr (self ,'skip_zip_checkbox'):self .skip_zip_checkbox .setText (self ._tr ("skip_zip_checkbox_label","Skip .zip"))
        if hasattr (self ,'download_thumbnails_checkbox'):self .download_thumbnails_checkbox .setText (self ._tr ("download_thumbnails_checkbox_label","Download Thumbnails Only"))
        if hasattr (self ,'scan_content_images_checkbox'):self .scan_content_images_checkbox .setText (self ._tr ("scan_content_images_checkbox_label","Scan Content for Images"))
        if hasattr (self ,'compress_images_checkbox'):self .compress_images_checkbox .setText (self ._tr ("compress_images_checkbox_label","Compress to WebP"))
        if hasattr (self ,'use_subfolders_checkbox'):self .use_subfolders_checkbox .setText (self ._tr ("separate_folders_checkbox_label","Separate Folders by Known.txt"))
        if hasattr (self ,'use_subfolder_per_post_checkbox'):self .use_subfolder_per_post_checkbox .setText (self ._tr ("subfolder_per_post_checkbox_label","Subfolder per Post"))
        if hasattr (self ,'use_cookie_checkbox'):self .use_cookie_checkbox .setText (self ._tr ("use_cookie_checkbox_label","Use Cookie"))
        if hasattr (self ,'use_multithreading_checkbox'):self .update_multithreading_label (self .thread_count_input .text ()if hasattr (self ,'thread_count_input')else "1")
        if hasattr (self ,'external_links_checkbox'):self .external_links_checkbox .setText (self ._tr ("show_external_links_checkbox_label","Show External Links in Log"))
        if hasattr (self ,'manga_mode_checkbox'):self .manga_mode_checkbox .setText (self ._tr ("manga_comic_mode_checkbox_label","Renaming Mode"))
        if hasattr (self ,'thread_count_label'):self .thread_count_label .setText (self ._tr ("threads_label","Threads:"))

        if hasattr (self ,'character_input'):
            self .character_input .setToolTip (self ._tr ("character_input_tooltip","Enter character names (comma-separated)..."))
        if hasattr (self ,'download_btn'):self .download_btn .setToolTip (self ._tr ("start_download_button_tooltip","Click to start the download or link extraction process with the current settings."))





        current_download_is_active =self ._is_download_active ()if hasattr (self ,'_is_download_active')else False 
        self .set_ui_enabled (not current_download_is_active )

        if hasattr (self ,'known_chars_label'):self .known_chars_label .setText (self ._tr ("known_chars_label_text","🎭 Known Shows/Characters (for Folder Names):"))
        if hasattr (self ,'open_known_txt_button'):self .open_known_txt_button .setText (self ._tr ("open_known_txt_button_text","Open Known.txt"));self .open_known_txt_button .setToolTip (self ._tr ("open_known_txt_button_tooltip","Open the 'Known.txt' file..."))
        if hasattr (self ,'add_char_button'):self .add_char_button .setText (self ._tr ("add_char_button_text","➕ Add"));self .add_char_button .setToolTip (self ._tr ("add_char_button_tooltip","Add the name from the input field..."))
        if hasattr (self ,'add_to_filter_button'):self .add_to_filter_button .setText (self ._tr ("add_to_filter_button_text","⤵️ Add to Filter"));self .add_to_filter_button .setToolTip (self ._tr ("add_to_filter_button_tooltip","Select names from 'Known Shows/Characters' list..."))
        if hasattr (self ,'character_list'):
            self .character_list .setToolTip (self ._tr ("known_chars_list_tooltip","This list displays all names and groups from your 'Known.txt' file.\nThese entries are used by the 'Separate Folder by Known.txt' option to create folders automatically from post titles.\n\nYou can select items here and use the '⤵️ Add to Filter' button to quickly add them to the character filter field."))
        if hasattr (self ,'delete_char_button'):self .delete_char_button .setText (self ._tr ("delete_char_button_text","🗑️ Delete Selected"));self .delete_char_button .setToolTip (self ._tr ("delete_char_button_tooltip","Delete the selected name(s)..."))

        if hasattr (self ,'cancel_btn'):self .cancel_btn .setToolTip (self ._tr ("cancel_button_tooltip","Click to cancel the ongoing download/extraction process and reset the UI fields (preserving URL and Directory)."))
        if hasattr (self ,'error_btn'):self .error_btn .setText (self ._tr ("error_button_text","Error"));self .error_btn .setToolTip (self ._tr ("error_button_tooltip","View files skipped due to errors and optionally retry them."))
        if hasattr (self ,'progress_log_label'):self .progress_log_label .setText (self ._tr ("progress_log_label_text","📜 Progress Log:"))
        if hasattr (self ,'reset_button'):self .reset_button .setText (self ._tr ("reset_button_text","🔄 Reset"));self .reset_button .setToolTip (self ._tr ("reset_button_tooltip","Reset all inputs and logs to default state (only when idle)."))
        self ._update_multipart_toggle_button_text ()
        if hasattr (self ,'progress_label')and not self ._is_download_active ():self .progress_label .setText (self ._tr ("progress_idle_text","Progress: Idle"))
        if hasattr (self ,'favorite_mode_artists_button'):self .favorite_mode_artists_button .setText (self ._tr ("favorite_artists_button_text","🖼️ Favorite Artists"));self .favorite_mode_artists_button .setToolTip (self ._tr ("favorite_artists_button_tooltip","Browse and download from your favorite artists..."))
        if hasattr (self ,'favorite_mode_posts_button'):self .favorite_mode_posts_button .setText (self ._tr ("favorite_posts_button_text","📄 Favorite Posts"));self .favorite_mode_posts_button .setToolTip (self ._tr ("favorite_posts_button_tooltip","Browse and download your favorite posts..."))
        self ._update_favorite_scope_button_text ()
        if hasattr (self ,'page_range_label'):self .page_range_label .setText (self ._tr ("page_range_label_text","Page Range:"))
        if hasattr (self ,'start_page_input'):
            self .start_page_input .setPlaceholderText (self ._tr ("start_page_input_placeholder","Start"))
            self .start_page_input .setToolTip (self ._tr ("start_page_input_tooltip","For creator URLs: Specify the starting page number..."))
        if hasattr (self ,'to_label'):self .to_label .setText (self ._tr ("page_range_to_label_text","to"))
        if hasattr (self ,'end_page_input'):
            self .end_page_input .setPlaceholderText (self ._tr ("end_page_input_placeholder","End"))
            self .end_page_input .setToolTip (self ._tr ("end_page_input_tooltip","For creator URLs: Specify the ending page number..."))
        if hasattr (self ,'fav_mode_active_label'):
            self .fav_mode_active_label .setText (self ._tr ("fav_mode_active_label_text","⭐ Favorite Mode is active..."))
        if hasattr (self ,'cookie_browse_button'):
            self .cookie_browse_button .setToolTip (self ._tr ("cookie_browse_button_tooltip","Browse for a cookie file..."))
        self ._update_manga_filename_style_button_text ()
        if hasattr (self ,'export_links_button'):self .export_links_button .setText (self ._tr ("export_links_button_text","Export Links"))
        if hasattr (self ,'download_extracted_links_button'):self .download_extracted_links_button .setText (self ._tr ("download_extracted_links_button_text","Download"))
        self ._update_log_display_mode_button_text ()


        if hasattr (self ,'radio_all'):self .radio_all .setToolTip (self ._tr ("radio_all_tooltip","Download all file types found in posts."))
        if hasattr (self ,'radio_images'):self .radio_images .setToolTip (self ._tr ("radio_images_tooltip","Download only common image formats (JPG, PNG, GIF, WEBP, etc.)."))
        if hasattr (self ,'radio_videos'):self .radio_videos .setToolTip (self ._tr ("radio_videos_tooltip","Download only common video formats (MP4, MKV, WEBM, MOV, etc.)."))
        if hasattr (self ,'radio_only_archives'):self .radio_only_archives .setToolTip (self ._tr ("radio_only_archives_tooltip","Exclusively download .zip and .rar files. Other file-specific options are disabled."))
        if hasattr (self ,'radio_only_audio'):self .radio_only_audio .setToolTip (self ._tr ("radio_only_audio_tooltip","Download only common audio formats (MP3, WAV, FLAC, etc.)."))
        if hasattr (self ,'radio_only_links'):self .radio_only_links .setToolTip (self ._tr ("radio_only_links_tooltip","Extract and display external links from post descriptions instead of downloading files.\nDownload-related options will be disabled."))


        if hasattr (self ,'use_subfolders_checkbox'):self .use_subfolders_checkbox .setToolTip (self ._tr ("use_subfolders_checkbox_tooltip","When checked, the post title will be scanned for names listed in 'Known.txt' to automatically create a subfolder.\n\nExample: A post titled 'Tifa in Nibelheim' will be saved in a 'Tifa' folder if 'Tifa' is in Known.txt.\n\nNote: If 'Filter by Character' is used, that filter will take priority for folder naming."))
        if hasattr (self ,'use_subfolder_per_post_checkbox'):self .use_subfolder_per_post_checkbox .setToolTip (self ._tr ("use_subfolder_per_post_checkbox_tooltip","Creates a subfolder for each post..."))
        if hasattr (self ,'use_cookie_checkbox'):self .use_cookie_checkbox .setToolTip (self ._tr ("use_cookie_checkbox_tooltip","If checked, will attempt to use cookies..."))
        if hasattr (self ,'use_multithreading_checkbox'):self .use_multithreading_checkbox .setToolTip (self ._tr ("use_multithreading_checkbox_tooltip","Enables concurrent operations..."))
        if hasattr (self ,'thread_count_input'):self .thread_count_input .setToolTip (self ._tr ("thread_count_input_tooltip","Number of concurrent operations..."))
        if hasattr (self ,'external_links_checkbox'):self .external_links_checkbox .setToolTip (self ._tr ("external_links_checkbox_tooltip","If checked, a secondary log panel appears..."))
        if hasattr (self ,'manga_mode_checkbox'):self .manga_mode_checkbox .setToolTip (self ._tr ("manga_mode_checkbox_tooltip","Downloads posts from oldest to newest..."))

        if hasattr (self ,'scan_content_images_checkbox'):self .scan_content_images_checkbox .setToolTip (self ._tr ("scan_content_images_checkbox_tooltip",self ._original_scan_content_tooltip ))
        if hasattr (self ,'download_thumbnails_checkbox'):self .download_thumbnails_checkbox .setToolTip (self ._tr ("download_thumbnails_checkbox_tooltip","Rewrites file URLs to download the smaller thumbnail version from the server instead of the full-sized file."))
        if hasattr (self ,'skip_words_input'):
            self .skip_words_input .setToolTip (self ._tr ("skip_words_input_tooltip",
            ("Enter words, comma-separated, to skip downloading certain content (e.g., WIP, sketch, preview).\n\n"
            "The 'Scope: [Type]' button next to this input cycles how this filter applies:\n"
            "- Scope: Files: Skips individual files if their names contain any of these words.\n"
            "- Scope: Posts: Skips entire posts if their titles contain any of these words.\n"
            "- Scope: Both: Applies both (post title first, then individual files if post title is okay).")))
        if hasattr (self ,'remove_from_filename_input'):
            self .remove_from_filename_input .setToolTip (self ._tr ("remove_words_input_tooltip",
            ("Enter words, comma-separated, to remove from downloaded filenames (case-insensitive).\n"
            "Useful for cleaning up common prefixes/suffixes.\nExample: patreon, kemono, [HD], _final")))

        if hasattr (self ,'link_input'):
            self .link_input .setPlaceholderText (self ._tr ("link_input_placeholder_text","e.g., https://kemono.su/patreon/user/12345 or .../post/98765"))
            self .link_input .setToolTip (self ._tr ("link_input_tooltip_text","Enter the full URL..."))
        if hasattr (self ,'dir_input'):
            self .dir_input .setPlaceholderText (self ._tr ("dir_input_placeholder_text","Select folder where downloads will be saved"))
            self .dir_input .setToolTip (self ._tr ("dir_input_tooltip_text","Enter or browse to the main folder..."))
        if hasattr (self ,'character_input'):
            self .character_input .setPlaceholderText (self ._tr ("character_input_placeholder_text","e.g., Tifa, Aerith, (Cloud, Zack)"))
        if hasattr (self ,'custom_folder_input'):
            self .custom_folder_input .setPlaceholderText (self ._tr ("custom_folder_input_placeholder_text","Optional: Save this post to specific folder"))
            self .custom_folder_input .setToolTip (self ._tr ("custom_folder_input_tooltip_text","If downloading a single post URL..."))
        if hasattr (self ,'skip_words_input'):
            self .skip_words_input .setPlaceholderText (self ._tr ("skip_words_input_placeholder_text","e.g., WM, WIP, sketch, preview"))
        if hasattr (self ,'remove_from_filename_input'):
            self .remove_from_filename_input .setPlaceholderText (self ._tr ("remove_from_filename_input_placeholder_text","e.g., patreon, HD"))
        self ._update_cookie_input_placeholders_and_tooltips ()
        if hasattr (self ,'character_search_input'):
            self .character_search_input .setPlaceholderText (self ._tr ("character_search_input_placeholder_text","Search characters..."))
            self .character_search_input .setToolTip (self ._tr ("character_search_input_tooltip_text","Type here to filter the list..."))
        if hasattr (self ,'new_char_input'):
            self .new_char_input .setPlaceholderText (self ._tr ("new_char_input_placeholder_text","Add new show/character name"))
            self .new_char_input .setToolTip (self ._tr ("new_char_input_tooltip_text","Enter a new show, game, or character name..."))
        if hasattr (self ,'link_search_input'):
            self .link_search_input .setPlaceholderText (self ._tr ("link_search_input_placeholder_text","Search Links..."))
            self .link_search_input .setToolTip (self ._tr ("link_search_input_tooltip_text","When in 'Only Links' mode..."))
        if hasattr (self ,'manga_date_prefix_input'):
            self .manga_date_prefix_input .setPlaceholderText (self ._tr ("manga_date_prefix_input_placeholder_text","Prefix for Manga Filenames"))
            self .manga_date_prefix_input .setToolTip (self ._tr ("manga_date_prefix_input_tooltip_text","Optional prefix for 'Date Based'..."))
        if hasattr (self ,'empty_popup_button'):self .empty_popup_button .setToolTip (self ._tr ("empty_popup_button_tooltip_text","Open Creator Selection..."))
        if hasattr (self ,'known_names_help_button'):self .known_names_help_button .setToolTip (self ._tr ("known_names_help_button_tooltip_text","Open the application feature guide."))
        if hasattr (self ,'future_settings_button'):self .future_settings_button .setToolTip (self ._tr ("future_settings_button_tooltip_text","Open application settings..."))
        if hasattr (self ,'link_search_button'):self .link_search_button .setToolTip (self ._tr ("link_search_button_tooltip_text","Filter displayed links"))
 
    def _get_tooltip_for_character_input (self ):
        return (
        self ._tr ("character_input_tooltip","Default tooltip if translation fails.")
        )
    def _connect_signals (self ):
        self .actual_gui_signals .progress_signal .connect (self .handle_main_log )
        self .actual_gui_signals .file_progress_signal .connect (self .update_file_progress_display )
        self .actual_gui_signals .missed_character_post_signal .connect (self .handle_missed_character_post )
        self .actual_gui_signals .external_link_signal .connect (self .handle_external_link_signal )
        self .actual_gui_signals .file_successfully_downloaded_signal .connect (self ._handle_actual_file_downloaded )
        self.actual_gui_signals.worker_finished_signal.connect(self._handle_worker_result)       
        self .actual_gui_signals .file_download_status_signal .connect (lambda status :None )
        self.fetch_only_complete_signal.connect(self._fetch_only_finished)

        if hasattr (self ,'character_input'):
            self .character_input .textChanged .connect (self ._on_character_input_changed_live )
        if hasattr (self ,'use_cookie_checkbox'):
            self .use_cookie_checkbox .toggled .connect (self ._update_cookie_input_visibility )
        if hasattr (self ,'link_input'):
            self.link_input.textChanged.connect(self._update_ui_for_url_change)
            self.link_input.textChanged.connect(self._update_contextual_ui_elements) 
            self.link_input.textChanged.connect(self._update_button_states_and_connections)
        if hasattr(self, 'discord_scope_toggle_button'):
            self.discord_scope_toggle_button.clicked.connect(self._cycle_discord_scope)
        if hasattr (self ,'cookie_browse_button'):
            self .cookie_browse_button .clicked .connect (self ._browse_cookie_file )
        if hasattr (self ,'cookie_text_input'):
            self .cookie_text_input .textChanged .connect (self ._handle_cookie_text_manual_change )
        if hasattr(self, 'keep_duplicates_checkbox'):
            self.keep_duplicates_checkbox.toggled.connect(self._handle_keep_duplicates_toggled)
        self .gui_update_timer .timeout .connect (self ._process_worker_queue )
        self .gui_update_timer .start (100 )
        self .log_signal .connect (self .handle_main_log )
        self .add_character_prompt_signal .connect (self .prompt_add_character )
        self .character_prompt_response_signal .connect (self .receive_add_character_result )
        self .overall_progress_signal .connect (self .update_progress_display )
        self .post_processed_for_history_signal .connect (self ._add_to_history_candidates )
        self .finished_signal .connect (self .download_finished )
        if hasattr (self ,'character_search_input'):self .character_search_input .textChanged .connect (self .filter_character_list )
        if hasattr (self ,'external_links_checkbox'):self .external_links_checkbox .toggled .connect (self .update_external_links_setting )
        if hasattr (self ,'thread_count_input'):self .thread_count_input .textChanged .connect (self .update_multithreading_label )
        if hasattr (self ,'use_subfolder_per_post_checkbox'):self .use_subfolder_per_post_checkbox .toggled .connect (self .update_ui_for_subfolders )
        if hasattr (self ,'use_multithreading_checkbox'):self .use_multithreading_checkbox .toggled .connect (self ._handle_multithreading_toggle )

        if hasattr (self ,'radio_group')and self .radio_group :
            self .radio_group .buttonToggled .connect (self ._handle_filter_mode_change )

        if self .reset_button :self .reset_button .clicked .connect (self .reset_application_state )
        if self .log_verbosity_toggle_button :self .log_verbosity_toggle_button .clicked .connect (self .toggle_active_log_view )

        if self .link_search_button :self .link_search_button .clicked .connect (self ._filter_links_log )
        if self .link_search_input :
            self .link_search_input .returnPressed .connect (self ._filter_links_log )
            self .link_search_input .textChanged .connect (self ._filter_links_log )
        if self .export_links_button :self .export_links_button .clicked .connect (self ._export_links_to_file )

        if self .manga_mode_checkbox :self .manga_mode_checkbox .toggled .connect (self .update_ui_for_manga_mode )


        if hasattr (self ,'download_extracted_links_button'):
            self .download_extracted_links_button .clicked .connect (self ._show_download_extracted_links_dialog )

        if hasattr (self ,'log_display_mode_toggle_button'):
            self .log_display_mode_toggle_button .clicked .connect (self ._toggle_log_display_mode )

        if self .manga_rename_toggle_button :self .manga_rename_toggle_button .clicked .connect (self ._toggle_manga_filename_style )

        if hasattr (self ,'link_input'):
            self .link_input .textChanged .connect (lambda :self .update_ui_for_manga_mode (self .manga_mode_checkbox .isChecked ()if self .manga_mode_checkbox else False ))

        if self .skip_scope_toggle_button :
            self .skip_scope_toggle_button .clicked .connect (self ._cycle_skip_scope )

        if self .char_filter_scope_toggle_button :
            self .char_filter_scope_toggle_button .clicked .connect (self ._cycle_char_filter_scope )

        if hasattr (self ,'multipart_toggle_button'):self .multipart_toggle_button .clicked .connect (self ._toggle_multipart_mode )


        if hasattr (self ,'favorite_mode_checkbox'):
            self .favorite_mode_checkbox .toggled .connect (self ._handle_favorite_mode_toggle )

        if hasattr (self ,'open_known_txt_button'):
            self .open_known_txt_button .clicked .connect (self ._open_known_txt_file )

        if hasattr (self ,'add_to_filter_button'):
            self .add_to_filter_button .clicked .connect (self ._show_add_to_filter_dialog )
        if hasattr (self ,'favorite_mode_artists_button'):
            self .favorite_mode_artists_button .clicked .connect (self ._show_favorite_artists_dialog )
        if hasattr (self ,'favorite_mode_posts_button'):
            self .favorite_mode_posts_button .clicked .connect (self ._show_favorite_posts_dialog )
        if hasattr (self ,'favorite_scope_toggle_button'):
            self .favorite_scope_toggle_button .clicked .connect (self ._cycle_favorite_scope )
        if hasattr (self ,'history_button'):
            self .history_button .clicked .connect (self ._show_download_history_dialog )
        if hasattr (self ,'error_btn'):
            self .error_btn .clicked .connect (self ._show_error_files_dialog )
        if hasattr(self, 'support_button'): 
            self.support_button.clicked.connect(self._show_support_dialog)

    def _on_character_input_changed_live (self ,text ):
        """
        Called when the character input field text changes.
        If a download is active (running or paused), this updates the dynamic filter holder.
        """
        if self ._is_download_active ():
            QCoreApplication .processEvents ()
            raw_character_filters_text =self .character_input .text ().strip ()
            parsed_filters =self ._parse_character_filters (raw_character_filters_text )

            self .dynamic_character_filter_holder .set_filters (parsed_filters )

    def _parse_character_filters (self ,raw_text ):
        """
        Helper to parse character filter string into a list of filter objects
        and extract special commands.
        Returns a tuple: (list_of_filter_objects, dict_of_commands)
        """
        text_without_commands, commands = parse_commands_from_text(raw_text)

        parsed_character_filter_objects =[]
        if text_without_commands :
            raw_parts =[]
            current_part_buffer =""
            in_group_parsing =False
            for char_token in text_without_commands :
                if char_token =='('and not in_group_parsing :
                    in_group_parsing =True
                    current_part_buffer +=char_token
                elif char_token ==')'and in_group_parsing :
                    in_group_parsing =False
                    current_part_buffer +=char_token
                elif char_token ==','and not in_group_parsing :
                    if current_part_buffer .strip ():raw_parts .append (current_part_buffer .strip ())
                    current_part_buffer =""
                else :
                    current_part_buffer +=char_token
            if current_part_buffer .strip ():raw_parts .append (current_part_buffer .strip ())

            for part_str in raw_parts :
                part_str =part_str .strip ()
                if not part_str :continue

                is_tilde_group =part_str .startswith ("(")and part_str .endswith (")~")
                is_standard_group_for_splitting =part_str .startswith ("(")and part_str .endswith (")")and not is_tilde_group

                if is_tilde_group :
                    group_content_str =part_str [1 :-2 ].strip ()
                    aliases_in_group =[alias .strip ()for alias in group_content_str .split (',')if alias .strip ()]
                    if aliases_in_group :
                        group_folder_name =" ".join (aliases_in_group )
                        parsed_character_filter_objects .append ({"name":group_folder_name ,"is_group":True ,"aliases":aliases_in_group })
                elif is_standard_group_for_splitting :
                    group_content_str =part_str [1 :-1 ].strip ()
                    aliases_in_group =[alias .strip ()for alias in group_content_str .split (',')if alias .strip ()]
                    if aliases_in_group :
                        group_folder_name =" ".join (aliases_in_group )
                        parsed_character_filter_objects .append ({
                        "name":group_folder_name ,
                        "is_group":True ,
                        "aliases":aliases_in_group ,
                        "components_are_distinct_for_known_txt":True
                        })
                else :
                    parsed_character_filter_objects .append ({"name":part_str ,"is_group":False ,"aliases":[part_str ],"components_are_distinct_for_known_txt":False })
        return parsed_character_filter_objects, commands

    def _process_worker_queue (self ):
        """Processes messages from the worker queue and emits Qt signals from the GUI thread."""
        while not self .worker_to_gui_queue .empty ():
            try :
                item =self .worker_to_gui_queue .get_nowait ()
                signal_type =item .get ('type')
                payload =item .get ('payload',tuple ())

                if signal_type =='progress':
                    self .actual_gui_signals .progress_signal .emit (*payload )
                elif signal_type =='file_download_status':
                    self .actual_gui_signals .file_download_status_signal .emit (*payload )
                elif signal_type =='external_link':
                    self .actual_gui_signals .external_link_signal .emit (*payload )
                elif signal_type =='file_progress':
                    self .actual_gui_signals .file_progress_signal .emit (*payload )
                elif signal_type =='missed_character_post':
                    self .actual_gui_signals .missed_character_post_signal .emit (*payload )
                elif signal_type =='file_successfully_downloaded':
                    self ._handle_actual_file_downloaded (payload [0 ]if payload else {})
                elif signal_type =='file_successfully_downloaded':
                    self ._handle_file_successfully_downloaded (payload [0 ])
                elif signal_type == 'worker_finished':
                    self.actual_gui_signals.worker_finished_signal.emit(payload[0] if payload else tuple())
                elif signal_type == 'set_progress_label' and self.progress_label:
                    self.progress_label.setText(payload[0] if payload else "")
                elif signal_type == 'set_ui_enabled':
                    self.set_ui_enabled(payload[0] if payload else True)
                else:
                    self .log_signal .emit (f"⚠️ Unknown signal type from worker queue: {signal_type }")
                self .worker_to_gui_queue .task_done ()
            except queue .Empty :
                break 
            except Exception as e :
                self .log_signal .emit (f"❌ Error processing worker queue: {e }")

    def load_known_names_from_util (self ):
        global KNOWN_NAMES 
        if os .path .exists (self .config_file ):
            parsed_known_objects =[]
            try :
                with open (self .config_file ,'r',encoding ='utf-8')as f :
                    for line_num ,line in enumerate (f ,1 ):
                        line =line .strip ()
                        if not line :continue 

                        if line .startswith ("(")and line .endswith (")"):
                            content =line [1 :-1 ].strip ()
                            parts =[p .strip ()for p in content .split (',')if p .strip ()]
                            if parts :
                                folder_name_raw =content .replace (',',' ')
                                folder_name_cleaned =clean_folder_name (folder_name_raw )

                                unique_aliases_set ={p for p in parts }
                                final_aliases_list =sorted (list (unique_aliases_set ),key =str .lower )

                                if not folder_name_cleaned :
                                    if hasattr (self ,'log_signal'):self .log_signal .emit (f"⚠️ Group resulted in empty folder name after cleaning in Known.txt on line {line_num }: '{line }'. Skipping entry.")
                                    continue 

                                parsed_known_objects .append ({
                                "name":folder_name_cleaned ,
                                "is_group":True ,
                                "aliases":final_aliases_list 
                                })
                            else :
                                if hasattr (self ,'log_signal'):self .log_signal .emit (f"⚠️ Empty group found in Known.txt on line {line_num }: '{line }'")
                        else :
                            parsed_known_objects .append ({
                            "name":line ,
                            "is_group":False ,
                            "aliases":[line ]
                            })
                parsed_known_objects .sort (key =lambda x :x ["name"].lower ())
                KNOWN_NAMES [:]=parsed_known_objects 
                log_msg =f"ℹ️ Loaded {len (KNOWN_NAMES )} known entries from {self .config_file }"
            except Exception as e :
                log_msg =f"❌ Error loading config '{self .config_file }': {e }"
                QMessageBox .warning (self ,"Config Load Error",f"Could not load list from {self .config_file }:\n{e }")
                KNOWN_NAMES [:]=[]
        else :
            self .character_input .setToolTip ("Names, comma-separated. Group aliases: (alias1, alias2, alias3) becomes folder name 'alias1 alias2 alias3' (after cleaning).\nAll names in the group are used as aliases for matching.\nE.g., yor, (Boa, Hancock, Snake Princess)")
            log_msg =f"ℹ️ Config file '{self .config_file }' not found. It will be created on save."
            KNOWN_NAMES [:]=[]

        if hasattr (self ,'log_signal'):self .log_signal .emit (log_msg )

        if hasattr (self ,'character_list'):
            self .character_list .clear ()
            if not KNOWN_NAMES :
                self .log_signal .emit ("ℹ️ 'Known.txt' is empty or was not found. No default entries will be added.")

            self .character_list .addItems ([entry ["name"]for entry in KNOWN_NAMES ])

    def start_discord_pdf_save(self):
        if self._is_download_active():
            QMessageBox.warning(self, "Busy", "Another operation is already in progress.")
            return

        api_url = self.link_input.text().strip()
        service, server_id, channel_id = extract_post_info(api_url)

        if service != 'discord':
            QMessageBox.critical(self, "Input Error", "This feature is only for Discord URLs.")
            return

        # --- Get Save Filename ---
        default_filename = f"discord_{server_id}_{channel_id or 'server'}.pdf"
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Discord Log as PDF", default_filename, "PDF Files (*.pdf)")

        if not filepath:
            self.log_signal.emit("ℹ️ Discord PDF save cancelled by user.")
            return
        
        # --- Create and run the background thread ---
        pdf_thread = threading.Thread(
            target=self._run_discord_pdf_creation_thread, 
            args=(api_url, server_id, channel_id, filepath),
            daemon=True
        )
        pdf_thread.start()

    def _run_discord_pdf_creation_thread(self, session, api_url, server_id, channel_id, output_filepath, message_limit=None):
        def queue_logger(message):
            self.worker_to_gui_queue.put({'type': 'progress', 'payload': (message,)})
        
        def queue_progress_label_update(message):
            self.worker_to_gui_queue.put({'type': 'set_progress_label', 'payload': (message,)})

        token = self.remove_from_filename_input.text().strip()
        headers = {
            'Authorization': token,
            'User-Agent': USERAGENT_FIREFOX,
        }

        self.set_ui_enabled(False)
        queue_logger("=" * 40)
        queue_logger(f"🚀 Starting Discord PDF export for: {api_url}")
        queue_progress_label_update("Fetching messages...")

        all_messages = []
        channels_to_process = []
        server_name_for_pdf = server_id

        if channel_id:
            channels_to_process.append({'id': channel_id, 'name': channel_id})
        else:
            # This logic can be expanded later to fetch all channels in a server if needed
            pass

        for i, channel in enumerate(channels_to_process):
            queue_progress_label_update(f"Fetching from channel {i+1}/{len(channels_to_process)}: #{channel.get('name', '')}")
            last_message_id = None
            while not self.cancellation_event.is_set():
                url_endpoint = f"/channels/{channel['id']}/messages?limit=100"
                if last_message_id:
                    url_endpoint += f"&before={last_message_id}"
                
                try:
                    resp = session.get(f"https://discord.com/api/v10{url_endpoint}", headers=headers)
                    resp.raise_for_status()
                    message_batch = resp.json()
                except Exception:
                    message_batch = []

                if not message_batch:
                    break
                
                all_messages.extend(message_batch)

                if message_limit and len(all_messages) >= message_limit:
                    queue_logger(f"   Reached message limit of {message_limit}. Halting fetch.")
                    all_messages = all_messages[:message_limit]
                    break

                last_message_id = message_batch[-1]['id']
                queue_progress_label_update(f"Fetched {len(all_messages)} messages...")
                time.sleep(1)

            if message_limit and len(all_messages) >= message_limit:
                break
        
        queue_progress_label_update(f"Collected {len(all_messages)} total messages. Generating PDF...")
        
        all_messages.reverse()

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = self.app_base_dir
        font_path = os.path.join(base_path, 'data', 'dejavu-sans', 'DejaVuSans.ttf')

        success = create_pdf_from_discord_messages(
            all_messages,
            server_name_for_pdf,
            channels_to_process[0].get('name', channel_id) if len(channels_to_process) == 1 else "All Channels",
            output_filepath,
            font_path,
            logger=queue_logger
        )

        if success:
            queue_progress_label_update(f"✅ PDF export complete!")
        else:
            queue_progress_label_update(f"❌ PDF export failed. Check log for details.")
        
        self.finished_signal.emit(0, len(all_messages), self.cancellation_event.is_set(), [])

    def save_known_names(self):
        """
        Saves the current list of known names (KNOWN_NAMES) to the config file.
        FIX: This version re-reads the file from disk before saving to preserve
        any external edits made by the user.
        """
        global KNOWN_NAMES
        try:
            config_dir = os.path.dirname(self.config_file)
            os.makedirs(config_dir, exist_ok=True)

            if os.path.exists(self.config_file):
                self.log_signal.emit("ℹ️ Re-reading Known.txt before saving to check for external edits...")
                disk_names = set()
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        disk_names.add(line.strip())
                
                for entry in KNOWN_NAMES:
                    if entry["is_group"]:
                        disk_names.add(f"({', '.join(sorted(entry['aliases'], key=str.lower))})")
                    else:
                        disk_names.add(entry["name"])
                
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    for name in sorted(list(disk_names), key=str.lower):
                        if name: 
                            f.write(name + '\n')

            else:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    for entry in KNOWN_NAMES:
                        if entry["is_group"]:
                            f.write(f"({', '.join(sorted(entry['aliases'], key=str.lower))})\n")
                        else:
                            f.write(entry["name"] + '\n')

            if hasattr(self, 'log_signal'):
                self.log_signal.emit(f"💾 Saved known entries to {self.config_file}")

        except Exception as e:
            log_msg = f"❌ Error saving config '{self.config_file}': {e}"
            if hasattr(self, 'log_signal'):
                self.log_signal.emit(log_msg)
            QMessageBox.warning(self, "Config Save Error", f"Could not save list to {self.config_file}:\n{e}")

    def closeEvent (self ,event ):
        self .save_known_names ()
        self .settings .setValue (MANGA_FILENAME_STYLE_KEY ,self .manga_filename_style )
        self .settings .setValue (ALLOW_MULTIPART_DOWNLOAD_KEY ,self .allow_multipart_download_setting )
        self .settings .setValue (COOKIE_TEXT_KEY ,self .cookie_text_input .text ()if hasattr (self ,'cookie_text_input')else "")
        self .settings .setValue (SCAN_CONTENT_IMAGES_KEY ,self .scan_content_images_checkbox .isChecked ()if hasattr (self ,'scan_content_images_checkbox')else False )
        self .settings .setValue (USE_COOKIE_KEY ,self .use_cookie_checkbox .isChecked ()if hasattr (self ,'use_cookie_checkbox')else False )
        self .settings .setValue (THEME_KEY ,self .current_theme )
        self .settings .setValue (LANGUAGE_KEY ,self .current_selected_language )
        self .settings .sync ()
        self ._save_persistent_history ()

        should_exit =True 
        is_downloading =self ._is_download_active ()

        if is_downloading :
            reply =QMessageBox .question (self ,"Confirm Exit",
            "Download in progress. Are you sure you want to exit and cancel?",
            QMessageBox .Yes |QMessageBox .No ,QMessageBox .No )
            if reply ==QMessageBox .Yes :
                self .log_signal .emit ("⚠️ Cancelling active download due to application exit...")
                self .cancellation_event .set ()
                if self .download_thread and self .download_thread .isRunning ():
                    self .download_thread .requestInterruption ()
                    self .log_signal .emit ("   Signaled single download thread to interrupt.")
                if self .download_thread and self .download_thread .isRunning ():
                    self .log_signal .emit ("   Waiting for single download thread to finish...")
                    self .download_thread .wait (3000 )
                    if self .download_thread .isRunning ():
                        self .log_signal .emit ("   ⚠️ Single download thread did not terminate gracefully.")

                if self .thread_pool :
                    self .log_signal .emit ("   Shutting down thread pool (waiting for completion)...")
                    self .thread_pool .shutdown (wait =True ,cancel_futures =True )
                    self .log_signal .emit ("   Thread pool shutdown complete.")
                    self .thread_pool =None 
                self .log_signal .emit ("   Cancellation for exit complete.")
            else :
                should_exit =False 
                self .log_signal .emit ("ℹ️ Application exit cancelled.")
                event .ignore ()
                return 

        if should_exit :
            self .log_signal .emit ("ℹ️ Application closing.")
            if self .thread_pool :
                self .log_signal .emit ("   Final thread pool check: Shutting down...")
                self .cancellation_event .set ()
                self .thread_pool .shutdown (wait =True ,cancel_futures =True )
                self .thread_pool =None 
            self .log_signal .emit ("👋 Exiting application.")
            event .accept ()


    def _request_restart_application (self ):
        self .log_signal .emit ("🔄 Application restart requested by user for language change.")
        self ._restart_pending =True 
        self .close ()

    def _do_actual_restart (self ):
        try :
            self .log_signal .emit ("   Performing application restart...")
            python_executable =sys .executable 
            script_args =sys .argv 


            if getattr (sys ,'frozen',False ):



                QProcess .startDetached (python_executable ,script_args [1 :])
            else :


                QProcess .startDetached (python_executable ,script_args )

            QCoreApplication .instance ().quit ()
        except Exception as e :
            self .log_signal .emit (f"❌ CRITICAL: Failed to start new application instance: {e }")
            QMessageBox .critical (self ,"Restart Failed",
            f"Could not automatically restart the application: {e }\n\nPlease restart it manually.")

    def _load_persistent_history (self ):
        """Loads download history from a persistent file."""
        self .log_signal .emit (f"📜 Attempting to load history from: {self .persistent_history_file }")
        if os .path .exists (self .persistent_history_file ):
            try :
                with open (self .persistent_history_file ,'r',encoding ='utf-8')as f :
                    loaded_data =json .load (f )
                
                if isinstance (loaded_data ,dict ):
                    self .last_downloaded_files_details .clear ()
                    self .last_downloaded_files_details .extend (loaded_data .get ("last_downloaded_files",[]))
                    self .final_download_history_entries =loaded_data .get ("first_processed_posts",[])
                    self .log_signal .emit (f"✅ Loaded {len (self .last_downloaded_files_details )} last downloaded files and {len (self .final_download_history_entries )} first processed posts from persistent history.")
                elif loaded_data is None and os .path .getsize (self .persistent_history_file )==0 :
                    self .log_signal .emit (f"ℹ️ Persistent history file is empty. Initializing with empty history.")
                    self .final_download_history_entries =[]
                    self .last_downloaded_files_details .clear ()
                elif isinstance(loaded_data, list): # Handle old format where only first_processed_posts was saved
                    self.log_signal.emit("⚠️ Persistent history file is in old format (only first_processed_posts). Converting to new format.")
                    self.final_download_history_entries = loaded_data
                    self.last_downloaded_files_details.clear()
                    self._save_persistent_history() # Save in new format immediately
                else :
                    self .log_signal .emit (f"⚠️ Persistent history file has incorrect format. Expected list, got {type (loaded_history )}. Ignoring.")
                    self .final_download_history_entries =[]
            except json .JSONDecodeError :
                self .log_signal .emit (f"⚠️ Error decoding persistent history file. It might be corrupted. Ignoring.")
                self .final_download_history_entries =[]
            except Exception as e :
                self .log_signal .emit (f"❌ Error loading persistent history: {e }")
                self .final_download_history_entries =[]
        else :
            self .log_signal .emit (f"⚠️ Persistent history file NOT FOUND at: {self .persistent_history_file }. Starting with empty history.")
            self .final_download_history_entries =[]
            self ._save_persistent_history ()


    def _save_persistent_history(self):
        """Saves download history to a persistent file."""
        self.log_signal.emit(f"📜 Attempting to save history to: {self.persistent_history_file}")
        try:
            history_dir = os.path.dirname(self.persistent_history_file)
            self.log_signal.emit(f"   History directory: {history_dir}")
            if not os.path.exists(history_dir):
                os.makedirs(history_dir, exist_ok=True)
                self.log_signal.emit(f"   Created history directory: {history_dir}")
            
            history_data = {
                "last_downloaded_files": list(self.last_downloaded_files_details),
                "first_processed_posts": self.final_download_history_entries
            }
            with open(self.persistent_history_file, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=2)
            self.log_signal.emit(f"✅ Saved {len(self.final_download_history_entries)} history entries to: {self.persistent_history_file}")
        except Exception as e:
            self.log_signal.emit(f"❌ Error saving persistent history to {self.persistent_history_file}: {e}")

   
    def _load_creator_name_cache_from_json (self ):
        """Loads creator id-name-service mappings from creators.json into self.creator_name_cache."""
        self .log_signal .emit ("ℹ️ Attempting to load creators.json for creator name cache.")

        if getattr (sys ,'frozen',False )and hasattr (sys ,'_MEIPASS'):
            base_path_for_creators =sys ._MEIPASS 
        else :
            base_path_for_creators =self .app_base_dir 

        creators_file_path =os .path .join (base_path_for_creators ,"data" ,"creators.json")

        if not os .path .exists (creators_file_path ):
            self .log_signal .emit (f"⚠️ 'creators.json' not found at {creators_file_path }. Creator name cache will be empty.")
            self .creator_name_cache .clear ()
            return 

        try :
            with open (creators_file_path ,'r',encoding ='utf-8')as f :
                loaded_data =json .load (f )

            creators_list =[]
            if isinstance (loaded_data ,list )and len (loaded_data )>0 and isinstance (loaded_data [0 ],list ):
                creators_list =loaded_data [0 ]
            elif isinstance (loaded_data ,list )and all (isinstance (item ,dict )for item in loaded_data ):
                creators_list =loaded_data 
            else :
                self .log_signal .emit (f"⚠️ 'creators.json' has an unexpected format. Creator name cache may be incomplete.")

            for creator_data in creators_list :
                creator_id =creator_data .get ("id")
                name =creator_data .get ("name")
                service =creator_data .get ("service")
                if creator_id and name and service :
                    self .creator_name_cache [(service .lower (),str (creator_id ))]=name 
            self .log_signal .emit (f"✅ Successfully loaded {len (self .creator_name_cache )} creator names into cache from 'creators.json'.")
        except Exception as e :
            self .log_signal .emit (f"❌ Error loading 'creators.json' for name cache: {e }")
            self .creator_name_cache .clear ()

    def _show_download_history_dialog (self ):
        """Shows the dialog with the finalized download history."""
        last_3_downloaded =list (self .last_downloaded_files_details )
        first_processed =self .final_download_history_entries 

        if not last_3_downloaded and not first_processed :
            QMessageBox .information (
            self ,
            self ._tr ("download_history_dialog_title_empty","Download History (Empty)"),
            self ._tr ("no_download_history_header","No Downloads Yet")
            )
            return 

        dialog = DownloadHistoryDialog(last_3_downloaded, first_processed, self)
        dialog .exec_ ()

    def _handle_actual_file_downloaded (self ,file_details_dict ):
        """Handles a successfully downloaded file for the 'last 3 downloaded' history."""
        if not file_details_dict :
            return 
        file_details_dict ['download_timestamp']=time .time ()
        creator_key =(file_details_dict .get ('service','').lower (),str (file_details_dict .get ('user_id','')))
        file_details_dict ['creator_display_name']=self .creator_name_cache .get (creator_key ,file_details_dict .get ('folder_context_name','Unknown Creator/Series'))
        self .last_downloaded_files_details .append (file_details_dict )


    def _handle_file_successfully_downloaded (self ,history_entry_dict ):
        """Handles a successfully downloaded file for history logging."""
        if len (self .download_history_log )>=self .download_history_log .maxlen :
            self .download_history_log .popleft ()
        self .download_history_log .append (history_entry_dict )


    def _handle_actual_file_downloaded (self ,file_details_dict ):
        """Handles a successfully downloaded file for the 'last 3 downloaded' history."""
        if not file_details_dict :
            return 

        file_details_dict ['download_timestamp']=time .time ()


        creator_key =(
        file_details_dict .get ('service','').lower (),
        str (file_details_dict .get ('user_id',''))
        )
        creator_display_name =self .creator_name_cache .get (creator_key ,file_details_dict .get ('folder_context_name','Unknown Creator'))
        file_details_dict ['creator_display_name']=creator_display_name 

        self .last_downloaded_files_details .append (file_details_dict )


    def _handle_favorite_mode_toggle (self ,checked ):
        if not self .url_or_placeholder_stack or not self .bottom_action_buttons_stack :
            return 

            self ._handle_favorite_mode_toggle (self .favorite_mode_checkbox .isChecked ())
        self ._update_favorite_scope_button_text ()
        if hasattr (self ,'link_input'):
            self .last_link_input_text_for_queue_sync =self .link_input .text ()

    def _update_download_extracted_links_button_state (self ):
        if hasattr (self ,'download_extracted_links_button')and self .download_extracted_links_button :
            is_only_links =self .radio_only_links and self .radio_only_links .isChecked ()
            if not is_only_links :
                self .download_extracted_links_button .setEnabled (False )
                return 

            supported_platforms_for_button ={'mega','google drive','dropbox'}
            has_supported_links =any (
            link_info [3 ].lower ()in supported_platforms_for_button for link_info in self .extracted_links_cache 
            )
            self .download_extracted_links_button .setEnabled (is_only_links and has_supported_links )

    def _show_download_extracted_links_dialog (self ):
        """Shows the placeholder dialog for downloading extracted links."""
        if not (self .radio_only_links and self .radio_only_links .isChecked ()):
            self .log_signal .emit ("ℹ️ Download extracted links button clicked, but not in 'Only Links' mode.")
            return 

        supported_platforms ={'mega','google drive','dropbox'}
        links_to_show_in_dialog =[]
        for link_data_tuple in self .extracted_links_cache :
            platform =link_data_tuple [3 ].lower ()
            if platform in supported_platforms :
                links_to_show_in_dialog .append ({
                'title':link_data_tuple [0 ],
                'link_text':link_data_tuple [1 ],
                'url':link_data_tuple [2 ],
                'platform':platform ,
                'key':link_data_tuple [4 ]
                })

        if not links_to_show_in_dialog :
            QMessageBox .information (self ,"No Supported Links","No Mega, Google Drive, or Dropbox links were found in the extracted links.")
            return 

        dialog = DownloadExtractedLinksDialog(links_to_show_in_dialog, self)
        dialog .download_requested .connect (self ._handle_extracted_links_download_request )
        dialog .exec_ ()

    def _handle_extracted_links_download_request (self ,selected_links_info ):
        if not selected_links_info :
            self .log_signal .emit ("ℹ️ No links selected for download from dialog.")
            return 


        if self .radio_only_links and self .radio_only_links .isChecked ()and self .only_links_log_display_mode ==LOG_DISPLAY_DOWNLOAD_PROGRESS :
            self .main_log_output .clear ()
            self .log_signal .emit ("ℹ️ Displaying Mega download progress (extracted links hidden)...")
            self .mega_download_log_preserved_once =False 

        current_main_dir =self .dir_input .text ().strip ()
        download_dir_for_mega =""

        if current_main_dir and os .path .isdir (current_main_dir ):
            download_dir_for_mega =current_main_dir 
            self .log_signal .emit (f"ℹ️ Using existing main download location for external links: {download_dir_for_mega }")
        else :
            if not current_main_dir :
                self .log_signal .emit ("ℹ️ Main download location is empty. Prompting for download folder.")
            else :
                self .log_signal .emit (
                f"⚠️ Main download location '{current_main_dir }' is not a valid directory. Prompting for download folder.")


            suggestion_path =current_main_dir if current_main_dir else QStandardPaths .writableLocation (QStandardPaths .DownloadLocation )

            chosen_dir =QFileDialog .getExistingDirectory (
            self ,
            self ._tr ("select_download_folder_mega_dialog_title","Select Download Folder for External Links"),
            suggestion_path ,
            options =QFileDialog .ShowDirsOnly |QFileDialog .DontUseNativeDialog 
            )

            if not chosen_dir :
                self .log_signal .emit ("ℹ️ External links download cancelled - no download directory selected from prompt.")
                return 
            download_dir_for_mega =chosen_dir 


        self .log_signal .emit (f"ℹ️ Preparing to download {len (selected_links_info )} selected external link(s) to: {download_dir_for_mega }")
        if not os .path .exists (download_dir_for_mega ):
            self .log_signal .emit (f"❌ Critical Error: Selected download directory '{download_dir_for_mega }' does not exist.")
            return 


        tasks_for_thread =selected_links_info 

        if self .external_link_download_thread and self .external_link_download_thread .isRunning ():
            QMessageBox .warning (self ,"Busy","Another external link download is already in progress.")
            return 

        self .external_link_download_thread =ExternalLinkDownloadThread (
        tasks_for_thread ,
        download_dir_for_mega ,
        self .log_signal .emit ,
        self 
        )
        self .external_link_download_thread .finished .connect (self ._on_external_link_download_thread_finished )

        self .external_link_download_thread .progress_signal .connect (self .handle_main_log )
        self .external_link_download_thread .file_complete_signal .connect (self ._on_single_external_file_complete )



        self .set_ui_enabled (False )

        self .progress_label .setText (self ._tr ("progress_processing_post_text","Progress: Processing post {processed_posts}...").format (processed_posts =f"External Links (0/{len (tasks_for_thread )})"))
        self .external_link_download_thread .start ()

    def _on_external_link_download_thread_finished (self ):
        self .log_signal .emit ("✅ External link download thread finished.")
        self .progress_label .setText (f"{self ._tr ('status_completed','Completed')}: External link downloads. {self ._tr ('ready_for_new_task_text','Ready for new task.')}")

        self .mega_download_log_preserved_once =True 
        self .log_signal .emit ("INTERNAL: mega_download_log_preserved_once SET to True.")

        if self .radio_only_links and self .radio_only_links .isChecked ():
            self .log_signal .emit (HTML_PREFIX +"<br><hr>--- End of Mega Download Log ---<br>")



        self .set_ui_enabled (True )



        if self .mega_download_log_preserved_once :
            self .mega_download_log_preserved_once =False 
            self .log_signal .emit ("INTERNAL: mega_download_log_preserved_once RESET to False.")

        if self .external_link_download_thread :
            self .external_link_download_thread .deleteLater ()
            self .external_link_download_thread =None 

    def _on_single_external_file_complete (self ,url ,success ):
        pass 


    def _show_future_settings_dialog(self):
        """Shows the placeholder dialog for future settings."""
        
        dialog = FutureSettingsDialog(self)
        dialog.exec_()

    def _show_support_dialog(self): 
        """Shows the support/donation dialog."""
        dialog = SupportDialog(self)
        dialog.exec_()

    def _check_if_all_work_is_done(self):
        """
        Checks if the fetcher thread is done AND if all submitted tasks have been processed OR if a cancellation was requested.
        If so, finalizes the download. This is the central point for completion logic.
        """
        fetcher_is_done = not self.is_fetcher_thread_running
        all_workers_are_done = (self.processed_posts_count >= self.total_posts_to_process)
        is_cancelled = self.cancellation_event.is_set()

        if fetcher_is_done and (all_workers_are_done or is_cancelled):
            if not self.is_finishing:
                if is_cancelled:
                    self.log_signal.emit("🏁 Fetcher cancelled. Finalizing...")
                else:
                    self.log_signal.emit("🏁 All fetcher and worker tasks complete. Finalizing...")
                
                self.finished_signal.emit(self.download_counter, self.skip_counter, is_cancelled, self.all_kept_original_filenames)

    def _sync_queue_with_link_input (self ,current_text ):
        """
        Synchronizes the favorite_download_queue with the link_input text.
        Removes creators from the queue if their names are removed from the input field.
        Only affects items added via 'creator_popup_selection'.
        """
        if not self .favorite_download_queue :
            self .last_link_input_text_for_queue_sync =current_text 
            return 

        current_names_in_input ={name .strip ().lower ()for name in current_text .split (',')if name .strip ()}

        queue_copy =list (self .favorite_download_queue )
        removed_count =0 

        for item in queue_copy :
            if item .get ('type')=='creator_popup_selection':
                item_name_lower =item .get ('name','').lower ()
                if item_name_lower and item_name_lower not in current_names_in_input :
                    try :
                        self .favorite_download_queue .remove (item )
                        self .log_signal .emit (f"ℹ️ Creator '{item .get ('name')}' removed from download queue due to removal from URL input.")
                        removed_count +=1 
                    except ValueError :
                        self .log_signal .emit (f"⚠️ Tried to remove '{item .get ('name')}' from queue, but it was not found (sync).")

        self .last_link_input_text_for_queue_sync =current_text 

    def _browse_cookie_file (self ):
        """Opens a file dialog to select a cookie file."""
        start_dir =QStandardPaths .writableLocation (QStandardPaths .DownloadLocation )
        if not start_dir :
            start_dir =os .path .dirname (self .config_file )

        filepath ,_ =QFileDialog .getOpenFileName (self ,"Select Cookie File",start_dir ,"Text files (*.txt);;All files (*)")
        if filepath :
            self .selected_cookie_filepath =filepath 
            self .log_signal .emit (f"ℹ️ Selected cookie file: {filepath }")
            if hasattr (self ,'cookie_text_input'):
                self .cookie_text_input .blockSignals (True )
                self .cookie_text_input .setText (filepath )
            self .cookie_text_input .setToolTip (self ._tr ("cookie_text_input_tooltip_file_selected","Using selected cookie file: {filepath}").format (filepath =filepath ))
            self .cookie_text_input .setPlaceholderText (self ._tr ("cookie_text_input_placeholder_with_file_selected_text","Using selected cookie file (see Browse...)"))
            self .cookie_text_input .setReadOnly (True )
            self .cookie_text_input .setPlaceholderText ("")
            self .cookie_text_input .blockSignals (False )

    def _update_cookie_input_placeholders_and_tooltips (self ):
        if hasattr (self ,'cookie_text_input'):
            if self .selected_cookie_filepath :
                self .cookie_text_input .setPlaceholderText (self ._tr ("cookie_text_input_placeholder_with_file_selected_text","Using selected cookie file..."))
                self .cookie_text_input .setToolTip (self ._tr ("cookie_text_input_tooltip_file_selected","Using selected cookie file: {filepath}").format (filepath =self .selected_cookie_filepath ))
            else :
                self .cookie_text_input .setPlaceholderText (self ._tr ("cookie_text_input_placeholder_no_file_selected_text","Cookie string (if no cookies.txt selected)"))
                self .cookie_text_input .setToolTip (self ._tr ("cookie_text_input_tooltip","Enter your cookie string directly..."))
                self .cookie_text_input .setReadOnly (True )
                self .cookie_text_input .setPlaceholderText ("")
                self .cookie_text_input .blockSignals (False )

    def _center_on_screen (self ):
        """Centers the widget on the screen."""
        try :
            primary_screen =QApplication .primaryScreen ()
            if not primary_screen :
                screens =QApplication .screens ()
                if not screens :return 
                primary_screen =screens [0 ]

            available_geo =primary_screen .availableGeometry ()
            widget_geo =self .frameGeometry ()

            x =available_geo .x ()+(available_geo .width ()-widget_geo .width ())//2 
            y =available_geo .y ()+(available_geo .height ()-widget_geo .height ())//2 
            self .move (x ,y )
        except Exception as e :
            self .log_signal .emit (f"⚠️ Error centering window: {e }")

    def _handle_cookie_text_manual_change (self ,text ):
        """Handles manual changes to the cookie text input, especially clearing a browsed path."""
        if not hasattr (self ,'cookie_text_input')or not hasattr (self ,'use_cookie_checkbox'):
            return 
        if self .selected_cookie_filepath and not text .strip ()and self .use_cookie_checkbox .isChecked ():
            self .selected_cookie_filepath =None 
            self .cookie_text_input .setReadOnly (False )
            self ._update_cookie_input_placeholders_and_tooltips ()
            self .log_signal .emit ("ℹ️ Browsed cookie file path cleared from input. Switched to manual cookie string mode.")


    def browse_directory (self ):
        initial_dir_text =self .dir_input .text ()
        start_path =""
        if initial_dir_text and os .path .isdir (initial_dir_text ):
            start_path =initial_dir_text 
        else :
            home_location =QStandardPaths .writableLocation (QStandardPaths .HomeLocation )
            documents_location =QStandardPaths .writableLocation (QStandardPaths .DocumentsLocation )
            if home_location and os .path .isdir (home_location ):
                start_path =home_location 
            elif documents_location and os .path .isdir (documents_location ):
                start_path =documents_location 

        self .log_signal .emit (f"ℹ️ Opening folder dialog. Suggested start path: '{start_path }'")

        try :
            folder =QFileDialog .getExistingDirectory (
            self ,
            "Select Download Folder",
            start_path ,
            options =QFileDialog .DontUseNativeDialog |QFileDialog .ShowDirsOnly 
            )

            if folder :
                self .dir_input .setText (folder )
                self .log_signal .emit (f"ℹ️ Folder selected: {folder }")
            else :
                self .log_signal .emit (f"ℹ️ Folder selection cancelled by user.")
        except RuntimeError as e :
            self .log_signal .emit (f"❌ RuntimeError opening folder dialog: {e }. This might indicate a deeper Qt or system issue.")
            QMessageBox .critical (self ,"Dialog Error",f"A runtime error occurred while trying to open the folder dialog: {e }")
        except Exception as e :
            self .log_signal .emit (f"❌ Unexpected error opening folder dialog: {e }\n{traceback .format_exc (limit =3 )}")
            QMessageBox .critical (self ,"Dialog Error",f"An unexpected error occurred with the folder selection dialog: {e }")

    def handle_main_log(self, message):
        if isinstance(message, str) and message.startswith("RENAMING_MODE_FETCH_PROGRESS:"):
            try:
                parts = message.split(":")
                fetched_count = int(parts[1])
                page_num = int(parts[2])
                self.progress_label.setText(self._tr("progress_fetching_manga_pages", "Progress: Fetching Page {page} ({count} posts found)...").format(page=page_num, count=fetched_count))
                QCoreApplication.processEvents() 
            except (ValueError, IndexError):
                try:
                    fetched_count = int(message.split(":")[1])
                    self.progress_label.setText(self._tr("progress_fetching_manga_posts", "Progress: Fetching Manga Posts ({count})...").format(count=fetched_count))
                    QCoreApplication.processEvents()
                except (ValueError, IndexError):
                    pass 
            return 
        elif isinstance(message, str) and message.startswith("RENAMING_MODE_FETCH_COMPLETE:"):
            try:
                total_posts = int(message.split(":")[1])
                self.total_posts_to_process = total_posts
                self.processed_posts_count = 0
                self.update_progress_display(self.total_posts_to_process, self.processed_posts_count)
            except (ValueError, IndexError):
                pass
            return 

        if message.startswith("TEMP_FILE_PATH:"):
            filepath = message.split(":", 1)[1]
            if self.single_pdf_setting:
                self.session_temp_files.append(filepath)
            return
            
        is_html_message = message.startswith(HTML_PREFIX)
        display_message = message[len(HTML_PREFIX):] if is_html_message else message
        
        try:
            safe_message = str(display_message).replace('\x00', '[NULL]')
            lines = safe_message.split('\n')

            for line in lines:
                if is_html_message:
                    self.main_log_output.insertHtml(line + "<br>") 
                else:
                    self.main_log_output.append(line)

            scrollbar = self.main_log_output.verticalScrollBar()
            if scrollbar.value() >= scrollbar.maximum() - 30:
                scrollbar.setValue(scrollbar.maximum())
                
        except Exception as e:
            print(f"GUI Main Log Error: {e}\nOriginal Message: {message}")
  
    def _extract_key_term_from_title (self ,title ):
        if not title :
            return None 
        title_cleaned =re .sub (r'\[.*?\]','',title )
        title_cleaned =re .sub (r'\(.*?\)','',title_cleaned )
        title_cleaned =title_cleaned .strip ()
        word_matches =list (re .finditer (r'\b[a-zA-Z][a-zA-Z0-9_-]*\b',title_cleaned ))

        capitalized_candidates =[]
        for match in word_matches :
            word =match .group (0 )
            if word .istitle ()and word .lower ()not in self .STOP_WORDS and len (word )>2 :
                if not (len (word )>3 and word .isupper ()):
                    capitalized_candidates .append ({'text':word ,'len':len (word ),'pos':match .start ()})

        if capitalized_candidates :
            capitalized_candidates .sort (key =lambda x :(x ['len'],x ['pos']),reverse =True )
            return capitalized_candidates [0 ]['text']
        non_capitalized_words_info =[]
        for match in word_matches :
            word =match .group (0 )
            if word .lower ()not in self .STOP_WORDS and len (word )>3 :
                non_capitalized_words_info .append ({'text':word ,'len':len (word ),'pos':match .start ()})

        if non_capitalized_words_info :
            non_capitalized_words_info .sort (key =lambda x :(x ['len'],x ['pos']),reverse =True )
            return non_capitalized_words_info [0 ]['text']

        return None 

    def handle_missed_character_post (self ,post_title ,reason ):
        if self .missed_character_log_output :
            key_term =self ._extract_key_term_from_title (post_title )

            if key_term :
                normalized_key_term =key_term .lower ()
                if normalized_key_term not in self .already_logged_bold_key_terms :
                    self .already_logged_bold_key_terms .add (normalized_key_term )
                    self .missed_key_terms_buffer .append (key_term )
                    self ._refresh_missed_character_log ()
        else :
            print (f"Debug (Missed Char Log): Title='{post_title }', Reason='{reason }'")

    def _refresh_missed_character_log (self ):
        if self .missed_character_log_output :
            self .missed_character_log_output .clear ()
            sorted_terms =sorted (self .missed_key_terms_buffer ,key =str .lower )
            separator_line ="-"*40 

            for term in sorted_terms :
                display_term =term .capitalize ()

                self .missed_character_log_output .append (separator_line )
                self .missed_character_log_output .append (f'<p align="center"><b><font style="font-size: 12.4pt; color: #87CEEB;">{display_term }</font></b></p>')
                self .missed_character_log_output .append (separator_line )
                self .missed_character_log_output .append ("")

            scrollbar =self .missed_character_log_output .verticalScrollBar ()
            scrollbar .setValue (0 )

    def _is_download_active (self ):
        single_thread_active = False
        if self.download_thread:
            if hasattr(self.download_thread, 'isRunning') and self.download_thread.isRunning():
                single_thread_active = True
            elif hasattr(self.download_thread, 'is_alive') and self.download_thread.is_alive():
                single_thread_active = True

        fetcher_active =hasattr (self ,'is_fetcher_thread_running')and self .is_fetcher_thread_running 
        pool_has_active_tasks =self .thread_pool is not None and any (not f .done ()for f in self .active_futures if f is not None )
        retry_pool_active =hasattr (self ,'retry_thread_pool')and self .retry_thread_pool is not None and hasattr (self ,'active_retry_futures')and any (not f .done ()for f in self .active_retry_futures if f is not None )
        external_dl_thread_active =hasattr (self ,'external_link_download_thread')and self .external_link_download_thread is not None and self .external_link_download_thread .isRunning ()
        
        # --- ADD THIS LINE ---
        fetching_only_active = hasattr(self, 'is_fetching_only') and self.is_fetching_only
        print("--- DEBUG: _is_download_active check ---")
        print(f"  single_thread_active: {single_thread_active} (thread is {self.download_thread})")
        print(f"  is_fetcher_thread_running: {self.is_fetcher_thread_running}")
        print(f"  is_fetching_only: {self.is_fetching_only}")
        result = single_thread_active or fetcher_active or pool_has_active_tasks or retry_pool_active or external_dl_thread_active or fetching_only_active
        print(f"  ==> Returning: {result}")
        return result

    def handle_external_link_signal (self ,post_title ,link_text ,link_url ,platform ,decryption_key ):
        link_data =(post_title ,link_text ,link_url ,platform ,decryption_key )
        self .external_link_queue .append (link_data )
        if self .radio_only_links and self .radio_only_links .isChecked ():
            self .extracted_links_cache .append (link_data )
            self ._update_download_extracted_links_button_state ()

        is_only_links_mode =self .radio_only_links and self .radio_only_links .isChecked ()
        should_display_in_external_log =self .show_external_links and not is_only_links_mode 

        if not (is_only_links_mode or should_display_in_external_log ):
            self ._is_processing_external_link_queue =False 
            if self .external_link_queue :
                QTimer .singleShot (0 ,self ._try_process_next_external_link )
            return 


        if link_data not in self .extracted_links_cache :
            self .extracted_links_cache .append (link_data )

    def _try_process_next_external_link (self ):
        if self ._is_processing_external_link_queue or not self .external_link_queue :
            return 

        is_only_links_mode =self .radio_only_links and self .radio_only_links .isChecked ()
        should_display_in_external_log =self .show_external_links and not is_only_links_mode 

        if not (is_only_links_mode or should_display_in_external_log ):
            self ._is_processing_external_link_queue =False 
            if self .external_link_queue :
                QTimer .singleShot (0 ,self ._try_process_next_external_link )
            return 

        self ._is_processing_external_link_queue =True 
        link_data =self .external_link_queue .popleft ()

        if is_only_links_mode :
            QTimer .singleShot (0 ,lambda data =link_data :self ._display_and_schedule_next (data ))
        elif self ._is_download_active ():
            delay_ms =random .randint (4000 ,8000 )
            QTimer .singleShot (delay_ms ,lambda data =link_data :self ._display_and_schedule_next (data ))
        else :
            QTimer .singleShot (0 ,lambda data =link_data :self ._display_and_schedule_next (data ))


    def _display_and_schedule_next (self ,link_data ):
        post_title ,link_text ,link_url ,platform ,decryption_key =link_data
        is_only_links_mode =self .radio_only_links and self .radio_only_links .isChecked ()

        # --- FONT STYLE DEFINITION ---
        # Use a clean, widely available sans-serif font family for a modern look.
        font_style = "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"

        if is_only_links_mode :
            if post_title != self._current_link_post_title:
                if self._current_link_post_title is not None:
                    separator_html = f'{HTML_PREFIX}<hr style="border: 1px solid #444;">'
                    self.log_signal.emit(separator_html)

                # Apply font style to the title
                title_html = f'<p style="{font_style} font-size: 11pt; color: #87CEEB; margin-top: 2px; margin-bottom: 2px;"><b>{html.escape(post_title)}</b></p>'
                self.log_signal.emit(HTML_PREFIX + title_html)
                self._current_link_post_title = post_title

            # Use the "smarter" logic to decide what text to show for the link
            cleaned_link_text = link_text.strip()
            display_text = ""
            if cleaned_link_text and cleaned_link_text.lower() != platform.lower() and cleaned_link_text != link_url:
                display_text = cleaned_link_text
            else:
                try:
                    path = urlparse(link_url).path
                    filename = os.path.basename(path)
                    if filename:
                        display_text = filename
                except Exception:
                    pass
            if not display_text:
                display_text = link_url

            # Truncate long display text
            if len(display_text) > 50:
                display_text = display_text[:50].strip() + "..."

            # Format the output as requested
            platform_display = platform.capitalize()
            
            # Escape parts that will be displayed as text
            escaped_url = html.escape(link_url)
            escaped_display_text = html.escape(f"({display_text})")

            # Apply font style to the link information and wrap in a paragraph tag
            link_html_line = (
                f'<p style="{font_style} font-size: 9.5pt; margin-left: 10px; margin-top: 1px; margin-bottom: 1px;">'
                f"  <span style='color: #E0E0E0;'>{platform_display} - {escaped_url} - {escaped_display_text}</span>"
            )

            if decryption_key:
                escaped_key = html.escape(f"(Decryption Key: {decryption_key})")
                link_html_line += f" <span style='color: #f0ad4e;'>{escaped_key}</span>"
            
            link_html_line += '</p>'

            # Emit the entire line as a single HTML signal
            self.log_signal.emit(HTML_PREFIX + link_html_line)

        elif self .show_external_links :
            # This part for the secondary log remains unchanged
            separator ="-"*45
            formatted_link_info = f"{link_text} - {link_url} - {platform}"
            if decryption_key:
                formatted_link_info += f" (Decryption Key: {decryption_key})"
            self._append_to_external_log(formatted_link_info, separator)

        self ._is_processing_external_link_queue =False
        self ._try_process_next_external_link ()


    def _append_to_external_log (self ,formatted_link_text ,separator ):
        if not (self .external_log_output and self .external_log_output .isVisible ()):
            return 

        try :
            self .external_log_output .append (formatted_link_text )
            self .external_log_output .append ("")

            scrollbar =self .external_log_output .verticalScrollBar ()
            if scrollbar .value ()>=scrollbar .maximum ()-50 :
                scrollbar .setValue (scrollbar .maximum ())
        except Exception as e :
            self .log_signal .emit (f"GUI External Log Append Error: {e }\nOriginal Message: {formatted_link_text }")
            print (f"GUI External Log Error (Append): {e }\nOriginal Message: {formatted_link_text }")


    def update_file_progress_display (self ,filename ,progress_info ):
        if not filename and progress_info is None :
            self .file_progress_label .setText ("")
            return 

        if isinstance (progress_info ,list ):
            if not progress_info :
                self .file_progress_label .setText (self ._tr ("downloading_multipart_initializing_text","File: {filename} - Initializing parts...").format (filename =filename ))
                return 

            total_downloaded_overall =sum (cs .get ('downloaded',0 )for cs in progress_info )
            total_file_size_overall =sum (cs .get ('total',0 )for cs in progress_info )

            active_chunks_count =0 
            combined_speed_bps =0 
            for cs in progress_info :
                if cs .get ('active',False ):
                    active_chunks_count +=1 
                    combined_speed_bps +=cs .get ('speed_bps',0 )

            dl_mb =total_downloaded_overall /(1024 *1024 )
            total_mb =total_file_size_overall /(1024 *1024 )
            speed_MBps =(combined_speed_bps /8 )/(1024 *1024 )

            progress_text =self ._tr ("downloading_multipart_text","DL '{filename}...': {downloaded_mb:.1f}/{total_mb:.1f} MB ({parts} parts @ {speed:.2f} MB/s)").format (filename =filename [:20 ],downloaded_mb =dl_mb ,total_mb =total_mb ,parts =active_chunks_count ,speed =speed_MBps )
            self .file_progress_label .setText (progress_text )

        elif isinstance (progress_info ,tuple )and len (progress_info )==2 :
            downloaded_bytes ,total_bytes =progress_info 

            if not filename and total_bytes ==0 and downloaded_bytes ==0 :
                self .file_progress_label .setText ("")
                return 

            max_fn_len =25 
            disp_fn =filename if len (filename )<=max_fn_len else filename [:max_fn_len -3 ].strip ()+"..."

            dl_mb =downloaded_bytes /(1024 *1024 )
            if total_bytes >0 :
                tot_mb =total_bytes /(1024 *1024 )
                prog_text_base =self ._tr ("downloading_file_known_size_text","Downloading '{filename}' ({downloaded_mb:.1f}MB / {total_mb:.1f}MB)").format (filename =disp_fn ,downloaded_mb =dl_mb ,total_mb =tot_mb )
            else :
                prog_text_base =self ._tr ("downloading_file_unknown_size_text","Downloading '{filename}' ({downloaded_mb:.1f}MB)").format (filename =disp_fn ,downloaded_mb =dl_mb )

            self .file_progress_label .setText (prog_text_base )
        elif filename and progress_info is None :
            self .file_progress_label .setText ("")
        elif not filename and not progress_info :
            self .file_progress_label .setText ("")

    def _clear_stale_temp_files(self):
        """On startup, cleans any temp files from a previous crashed session."""
        try:
            temp_dir = os.path.join(self.app_base_dir, "appdata")
            if not os.path.isdir(temp_dir):
                return
            
            for filename in os.listdir(temp_dir):
                if filename.startswith("tmp_") and filename.endswith(".json"):
                    try:
                        os.remove(os.path.join(temp_dir, filename))
                        self.log_signal.emit(f"   🧹 Removed stale temp file: {filename}")
                    except OSError:
                        pass # File might be locked, skip
        except Exception as e:
            self.log_signal.emit(f"⚠️ Error cleaning stale temp files: {e}")

    def _cleanup_temp_files(self):
        """Deletes all temporary files collected during the session."""
        if not self.session_temp_files:
            return
        
        self.log_signal.emit("   Cleaning up temporary files...")
        for filepath in self.session_temp_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ Could not delete temp file '{filepath}': {e}")
        self.session_temp_files = []

    def update_external_links_setting(self, checked, log_change=True):
        is_only_links_mode = self.radio_only_links and self.radio_only_links.isChecked()
        is_only_archives_mode = self.radio_only_archives and self.radio_only_archives.isChecked()
        is_only_audio_mode = hasattr(self, 'radio_only_audio') and self.radio_only_audio.isChecked()

        if is_only_links_mode or is_only_archives_mode or is_only_audio_mode:
            if self.external_log_output: self.external_log_output.hide()
            if self.log_splitter: self.log_splitter.setSizes([self.height(), 0])
            return

        self.show_external_links = checked

        if log_change and self.last_logged_external_link_status != checked:
            if checked:
                self.log_signal.emit("ℹ️ External Links Log Enabled")
            else:
                self.log_signal.emit("ℹ️ External Links Log Disabled")
            self.last_logged_external_link_status = checked

        if checked:
            if self.external_log_output: self.external_log_output.show()
            if self.log_splitter: self.log_splitter.setSizes([self.height() // 2, self.height() // 2])
            if self.main_log_output: self.main_log_output.setMinimumHeight(50)
            if self.external_log_output: self.external_log_output.setMinimumHeight(50)
            if self.external_log_output:
                self.external_log_output.clear()
                self.external_log_output.append("🔗 External Links Found:")
            self._try_process_next_external_link()
        else:
            if self.external_log_output: self.external_log_output.hide()
            if self.log_splitter: self.log_splitter.setSizes([self.height(), 0])
            if self.main_log_output: self.main_log_output.setMinimumHeight(0)
            if self.external_log_output: self.external_log_output.setMinimumHeight(0)
            if self.external_log_output: self.external_log_output.clear()

    def _handle_filter_mode_change(self, button, checked):
        if not button or not checked:
            return

        new_mode_text = button.text()
        if self.last_logged_filter_mode != new_mode_text:
            self.log_signal.emit(f"ℹ️ Filter mode changed to: {new_mode_text}")
            self.last_logged_filter_mode = new_mode_text

        is_only_links = (button == self.radio_only_links)

        if hasattr(self, 'use_multithreading_checkbox') and hasattr(self, 'thread_count_input'):
            if is_only_links:
                self.use_multithreading_checkbox.setChecked(True)
                self.thread_count_input.setText("20")
                self.thread_count_input.setEnabled(False) 
                self.thread_count_label.setEnabled(False)
                self.update_multithreading_label("20")
            else:
                is_multithreading_checked = self.use_multithreading_checkbox.isChecked()
                self.thread_count_input.setEnabled(is_multithreading_checked)
                self.thread_count_label.setEnabled(is_multithreading_checked)

        if button != self.radio_more and checked:
            self.radio_more.setText("More")
            self.more_filter_scope = None
            self.single_pdf_setting = False
            if hasattr(self, 'use_subfolders_checkbox'):
                self.use_subfolders_checkbox.setEnabled(True)

        is_only_audio = (hasattr(self, 'radio_only_audio') and self.radio_only_audio is not None and button == self.radio_only_audio)
        is_only_archives = (hasattr(self, 'radio_only_archives') and self.radio_only_archives is not None and button == self.radio_only_archives)

        if self.skip_scope_toggle_button:
            self.skip_scope_toggle_button.setVisible(True)
        if hasattr(self, 'multipart_toggle_button') and self.multipart_toggle_button:
            self.multipart_toggle_button.setVisible(not (is_only_links or is_only_archives or is_only_audio))

        if self.link_search_input: self.link_search_input.setVisible(is_only_links)
        if self.link_search_button: self.link_search_button.setVisible(is_only_links)
        if self.export_links_button:
            self.export_links_button.setVisible(is_only_links)
            self.export_links_button.setEnabled(is_only_links and bool(self.extracted_links_cache))

        if hasattr(self, 'download_extracted_links_button') and self.download_extracted_links_button:
            self.download_extracted_links_button.setVisible(is_only_links)
            self._update_download_extracted_links_button_state()


        if self.download_btn:
            if self.is_ready_to_download_fetched:
                return 

            if is_only_links:
                self.download_btn.setText(self._tr("extract_links_button_text", "🔗 Extract Links"))
            else:
                self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
        if not is_only_links and self.link_search_input: self.link_search_input.clear()

        file_download_mode_active = not is_only_links

        if self.use_subfolders_checkbox: self.use_subfolders_checkbox.setEnabled(file_download_mode_active)
        if self.skip_words_input: self.skip_words_input.setEnabled(True)
        if self.skip_scope_toggle_button: self.skip_scope_toggle_button.setEnabled(file_download_mode_active)
        if hasattr(self, 'remove_from_filename_input'): self.remove_from_filename_input.setEnabled(file_download_mode_active)

        if self.skip_zip_checkbox:
            can_skip_zip = file_download_mode_active and not is_only_archives
            self.skip_zip_checkbox.setEnabled(can_skip_zip)
            if is_only_archives:
                self.skip_zip_checkbox.setChecked(False)

        other_file_proc_enabled = file_download_mode_active and not is_only_archives
        if self.download_thumbnails_checkbox: self.download_thumbnails_checkbox.setEnabled(other_file_proc_enabled)
        if self.compress_images_checkbox: self.compress_images_checkbox.setEnabled(other_file_proc_enabled)

        if self.external_links_checkbox:
            can_show_external_log_option = file_download_mode_active and not is_only_archives
            self.external_links_checkbox.setEnabled(can_show_external_log_option)
            if not can_show_external_log_option:
                self.external_links_checkbox.setChecked(False)

        if is_only_links:
            self.progress_log_label.setText("📜 Extracted Links Log:")
        else:
            self.progress_log_label.setText(self._tr("progress_log_label_text", "📜 Progress Log:"))
        
        self.update_external_links_setting(self.external_links_checkbox.isChecked() if self.external_links_checkbox else False)
        
        if is_only_links:
            self._filter_links_log()

        if hasattr(self, 'log_display_mode_toggle_button'):
            self.log_display_mode_toggle_button.setVisible(is_only_links)
            self._update_log_display_mode_button_text()

        subfolders_on = self.use_subfolders_checkbox.isChecked() if self.use_subfolders_checkbox else False
        manga_on = self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False

        character_filter_should_be_active = True

        if self.character_filter_widget:
            self.character_filter_widget.setVisible(character_filter_should_be_active)

        enable_character_filter_related_widgets = character_filter_should_be_active

        if self.character_input:
            self.character_input.setEnabled(enable_character_filter_related_widgets)
            if not enable_character_filter_related_widgets:
                self.character_input.clear()

        if self.char_filter_scope_toggle_button:
            self.char_filter_scope_toggle_button.setEnabled(enable_character_filter_related_widgets)

        self.update_ui_for_subfolders(subfolders_on)
        self.update_custom_folder_visibility()
        self.update_ui_for_manga_mode(self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False)

    def _filter_links_log (self ):
        if not (self .radio_only_links and self .radio_only_links .isChecked ()):return

        search_term =self .link_search_input .text ().lower ().strip ()if self .link_search_input else ""

        if self .mega_download_log_preserved_once and self .only_links_log_display_mode ==LOG_DISPLAY_DOWNLOAD_PROGRESS :
            self .log_signal .emit ("INTERNAL: _filter_links_log - Preserving Mega log.")
            return
        elif self .only_links_log_display_mode ==LOG_DISPLAY_DOWNLOAD_PROGRESS :
            if self .main_log_output :self .main_log_output .clear ()
            self .log_signal .emit ("ℹ️ Switched to Mega download progress view. Extracted links are hidden.\n"
            "   Perform a Mega download to see its progress here, or switch back to 🔗 view.")
            return

        # Simplified logic: Clear the log and re-trigger the display process
        # The main display logic is now fully handled by _display_and_schedule_next
        if self .main_log_output :self .main_log_output .clear ()
        self._current_link_post_title = None # Reset the title tracking for the new display pass

        # Create a new temporary queue containing only the links that match the search term
        filtered_link_queue = deque()
        for post_title ,link_text ,link_url ,platform ,decryption_key in self .extracted_links_cache :
            matches_search =(not search_term or
            search_term in link_text .lower ()or
            search_term in link_url .lower ()or
            search_term in platform .lower ()or
            (decryption_key and search_term in decryption_key .lower ()))
            if matches_search :
                filtered_link_queue.append((post_title, link_text, link_url, platform, decryption_key))

        if not filtered_link_queue:
             self .log_signal .emit ("   (No links extracted yet or all filtered out in links view)")
        else:
            self.external_link_queue.clear()
            self.external_link_queue.extend(filtered_link_queue)
            self._try_process_next_external_link()

        if self .main_log_output :self .main_log_output .verticalScrollBar ().setValue (self .main_log_output .verticalScrollBar ().maximum ())

    def _display_and_schedule_next (self ,link_data ):
        post_title ,link_text ,link_url ,platform ,decryption_key =link_data
        is_only_links_mode =self .radio_only_links and self .radio_only_links .isChecked ()

        if is_only_links_mode :
            if post_title != self._current_link_post_title:
                if self._current_link_post_title is not None:
                    separator_html = f'{HTML_PREFIX}<hr style="border: 1px solid #444;">'
                    self.log_signal.emit(separator_html)

                title_html = f'<p style="font-size: 11pt; color: #87CEEB; margin-top: 2px; margin-bottom: 2px;"><b>{html.escape(post_title)}</b></p>'
                self.log_signal.emit(HTML_PREFIX + title_html)
                self._current_link_post_title = post_title

            # Use the "smarter" logic to decide what text to show for the link
            cleaned_link_text = link_text.strip()
            display_text = ""
            if cleaned_link_text and cleaned_link_text.lower() != platform.lower() and cleaned_link_text != link_url:
                display_text = cleaned_link_text
            else:
                try:
                    path = urlparse(link_url).path
                    filename = os.path.basename(path)
                    if filename:
                        display_text = filename
                except Exception:
                    pass
            if not display_text:
                display_text = link_url

            # Truncate long display text
            if len(display_text) > 50:
                display_text = display_text[:50].strip() + "..."

            # --- NEW: Format the output as requested ---
            platform_display = platform.capitalize()
            plain_link_info_line = f"  {platform_display} - {link_url} - ({display_text})"
            if decryption_key:
                plain_link_info_line += f" (Decryption Key: {decryption_key})"

            self.main_log_output.append(plain_link_info_line)

        elif self .show_external_links :
            # This part for the secondary log remains unchanged
            separator ="-"*45
            formatted_link_info = f"{link_text} - {link_url} - {platform}"
            if decryption_key:
                formatted_link_info += f" (Decryption Key: {decryption_key})"
            self._append_to_external_log(formatted_link_info, separator)

        self ._is_processing_external_link_queue =False
        self ._try_process_next_external_link ()

    def _export_links_to_file(self):
        """
        Opens a new, advanced dialog to handle exporting extracted links in various formats.
        """
        if not (self.radio_only_links and self.radio_only_links.isChecked()):
            QMessageBox.information(self, "Export Links", "Link export is only available in 'Only Links' mode.")
            return

        if not self.extracted_links_cache:
            QMessageBox.information(self, "Export Links", "No links have been extracted yet.")
            return

        # Create and execute the new export dialog
        dialog = ExportLinksDialog(self.extracted_links_cache, self)
        
        # The dialog now handles all logic. We just check if it was accepted.
        if dialog.exec_() == QDialog.Accepted:
            self.log_signal.emit("✅ Links successfully exported with selected options.")
        else:
            self.log_signal.emit("ℹ️ Link export was cancelled by the user.")


    def get_filter_mode (self ):
        if self.radio_more and self.radio_more.isChecked():
            return 'text_only'
        elif self.radio_only_links and self.radio_only_links.isChecked():
            return 'all'
        elif self .radio_images .isChecked ():
            return 'image'
        elif self .radio_videos .isChecked ():
            return 'video'
        elif self .radio_only_archives and self .radio_only_archives .isChecked ():
            return 'archive'
        elif hasattr (self ,'radio_only_audio')and self .radio_only_audio .isChecked ():
            return 'audio'
        elif self .radio_all .isChecked ():
            return 'all'
        return 'all'


    def get_skip_words_scope (self ):
        return self .skip_words_scope 


    def _update_skip_scope_button_text (self ):
        if self .skip_scope_toggle_button :
            if self .skip_words_scope ==SKIP_SCOPE_FILES :
                self .skip_scope_toggle_button .setText (self ._tr ("skip_scope_files_text","Scope: Files"))
                self .skip_scope_toggle_button .setToolTip (self ._tr ("skip_scope_files_tooltip","Tooltip for skip scope files"))
            elif self .skip_words_scope ==SKIP_SCOPE_POSTS :
                self .skip_scope_toggle_button .setText (self ._tr ("skip_scope_posts_text","Scope: Posts"))
                self .skip_scope_toggle_button .setToolTip (self ._tr ("skip_scope_posts_tooltip","Tooltip for skip scope posts"))
            elif self .skip_words_scope ==SKIP_SCOPE_BOTH :
                self .skip_scope_toggle_button .setText (self ._tr ("skip_scope_both_text","Scope: Both"))
                self .skip_scope_toggle_button .setToolTip (self ._tr ("skip_scope_both_tooltip","Tooltip for skip scope both"))
            else :
                self .skip_scope_toggle_button .setText (self ._tr ("skip_scope_unknown_text","Scope: Unknown"))
                self .skip_scope_toggle_button .setToolTip (self ._tr ("skip_scope_unknown_tooltip","Tooltip for skip scope unknown"))


    def _cycle_skip_scope (self ):
        if self .skip_words_scope ==SKIP_SCOPE_POSTS :
            self .skip_words_scope =SKIP_SCOPE_FILES 
        elif self .skip_words_scope ==SKIP_SCOPE_FILES :
            self .skip_words_scope =SKIP_SCOPE_BOTH 
        elif self .skip_words_scope ==SKIP_SCOPE_BOTH :
            self .skip_words_scope =SKIP_SCOPE_POSTS 
        else :
            self .skip_words_scope =SKIP_SCOPE_POSTS 

        self ._update_skip_scope_button_text ()
        self .settings .setValue (SKIP_WORDS_SCOPE_KEY ,self .skip_words_scope )
        self .log_signal .emit (f"ℹ️ Skip words scope changed to: '{self .skip_words_scope }'")

    def get_char_filter_scope (self ):
        return self .char_filter_scope 

    def _update_char_filter_scope_button_text (self ):
        if self .char_filter_scope_toggle_button :
            if self .char_filter_scope ==CHAR_SCOPE_FILES :
                self .char_filter_scope_toggle_button .setText (self ._tr ("char_filter_scope_files_text","Filter: Files"))
                self .char_filter_scope_toggle_button .setToolTip (self ._tr ("char_filter_scope_files_tooltip","Tooltip for char filter files"))
            elif self .char_filter_scope ==CHAR_SCOPE_TITLE :
                self .char_filter_scope_toggle_button .setText (self ._tr ("char_filter_scope_title_text","Filter: Title"))
                self .char_filter_scope_toggle_button .setToolTip (self ._tr ("char_filter_scope_title_tooltip","Tooltip for char filter title"))
            elif self .char_filter_scope ==CHAR_SCOPE_BOTH :
                self .char_filter_scope_toggle_button .setText (self ._tr ("char_filter_scope_both_text","Filter: Both"))
                self .char_filter_scope_toggle_button .setToolTip (self ._tr ("char_filter_scope_both_tooltip","Tooltip for char filter both"))
            elif self .char_filter_scope ==CHAR_SCOPE_COMMENTS :
                self .char_filter_scope_toggle_button .setText (self ._tr ("char_filter_scope_comments_text","Filter: Comments (Beta)"))
                self .char_filter_scope_toggle_button .setToolTip (self ._tr ("char_filter_scope_comments_tooltip","Tooltip for char filter comments"))
            else :
                self .char_filter_scope_toggle_button .setText (self ._tr ("char_filter_scope_unknown_text","Filter: Unknown"))
                self .char_filter_scope_toggle_button .setToolTip (self ._tr ("char_filter_scope_unknown_tooltip","Tooltip for char filter unknown"))

    def _cycle_char_filter_scope (self ):
        if self .char_filter_scope ==CHAR_SCOPE_TITLE :
            self .char_filter_scope =CHAR_SCOPE_FILES 
        elif self .char_filter_scope ==CHAR_SCOPE_FILES :
            self .char_filter_scope =CHAR_SCOPE_BOTH 
        elif self .char_filter_scope ==CHAR_SCOPE_BOTH :
            self .char_filter_scope =CHAR_SCOPE_COMMENTS 
        elif self .char_filter_scope ==CHAR_SCOPE_COMMENTS :
            self .char_filter_scope =CHAR_SCOPE_TITLE 
        else :
            self .char_filter_scope =CHAR_SCOPE_TITLE 

        self ._update_char_filter_scope_button_text ()
        self .settings .setValue (CHAR_FILTER_SCOPE_KEY ,self .char_filter_scope )
        self .log_signal .emit (f"ℹ️ Character filter scope changed to: '{self .char_filter_scope }'")

    def _handle_ui_add_new_character (self ):
        """Handles adding a new character from the UI input field."""
        name_from_ui_input =self .new_char_input .text ().strip ()
        successfully_added_any =False 

        if not name_from_ui_input :
            QMessageBox .warning (self ,"Input Error","Name cannot be empty.")
            return 

        if name_from_ui_input .startswith ("(")and name_from_ui_input .endswith (")~"):
            content =name_from_ui_input [1 :-2 ].strip ()
            aliases =[alias .strip ()for alias in content .split (',')if alias .strip ()]
            if aliases :
                folder_name =" ".join (aliases )
                if self .add_new_character (name_to_add =folder_name ,
                is_group_to_add =True ,
                aliases_to_add =aliases ,
                suppress_similarity_prompt =False ):
                    successfully_added_any =True 
            else :
                QMessageBox .warning (self ,"Input Error","Empty group content for `~` format.")

        elif name_from_ui_input .startswith ("(")and name_from_ui_input .endswith (")"):
            content =name_from_ui_input [1 :-1 ].strip ()
            names_to_add_separately =[name .strip ()for name in content .split (',')if name .strip ()]
            if names_to_add_separately :
                for name_item in names_to_add_separately :
                    if self .add_new_character (name_to_add =name_item ,
                    is_group_to_add =False ,
                    aliases_to_add =[name_item ],
                    suppress_similarity_prompt =False ):
                        successfully_added_any =True 
            else :
                QMessageBox .warning (self ,"Input Error","Empty group content for standard group format.")
        else :
            if self .add_new_character (name_to_add =name_from_ui_input ,
            is_group_to_add =False ,
            aliases_to_add =[name_from_ui_input ],
            suppress_similarity_prompt =False ):
                successfully_added_any =True 

        if successfully_added_any :
            self .new_char_input .clear ()
            self .save_known_names ()


    def add_new_character (self ,name_to_add ,is_group_to_add ,aliases_to_add ,suppress_similarity_prompt =False ):
        global KNOWN_NAMES ,clean_folder_name 
        if not name_to_add :
            QMessageBox .warning (self ,"Input Error","Name cannot be empty.");return False 

        name_to_add_lower =name_to_add .lower ()
        for kn_entry in KNOWN_NAMES :
            if kn_entry ["name"].lower ()==name_to_add_lower :
                QMessageBox .warning (self ,"Duplicate Name",f"The primary folder name '{name_to_add }' already exists.");return False 
            if not is_group_to_add and name_to_add_lower in [a .lower ()for a in kn_entry ["aliases"]]:
                QMessageBox .warning (self ,"Duplicate Alias",f"The name '{name_to_add }' already exists as an alias for '{kn_entry ['name']}'.");return False 

        similar_names_details =[]
        for kn_entry in KNOWN_NAMES :
            for term_to_check_similarity_against in kn_entry ["aliases"]:
                term_lower =term_to_check_similarity_against .lower ()
                if name_to_add_lower !=term_lower and (name_to_add_lower in term_lower or term_lower in name_to_add_lower ):
                    similar_names_details .append ((name_to_add ,kn_entry ["name"]))
                    break 
            for new_alias in aliases_to_add :
                if new_alias .lower ()!=term_to_check_similarity_against .lower ()and (new_alias .lower ()in term_to_check_similarity_against .lower ()or term_to_check_similarity_against .lower ()in new_alias .lower ()):
                    similar_names_details .append ((new_alias ,kn_entry ["name"]))
                    break 

        if similar_names_details and not suppress_similarity_prompt :
            if similar_names_details :
                first_similar_new ,first_similar_existing =similar_names_details [0 ]
                shorter ,longer =sorted ([first_similar_new ,first_similar_existing ],key =len )

                msg_box =QMessageBox (self )
                msg_box .setIcon (QMessageBox .Warning )
                msg_box .setWindowTitle ("Potential Name Conflict")
                msg_box .setText (
                f"The name '{first_similar_new }' is very similar to an existing name: '{first_similar_existing }'.\n\n"
                f"This could lead to unexpected folder grouping (e.g., under '{clean_folder_name (shorter )}' instead of a more specific '{clean_folder_name (longer )}' or vice-versa).\n\n"
                "Do you want to change the name you are adding, or proceed anyway?"
                )
                change_button =msg_box .addButton ("Change Name",QMessageBox .RejectRole )
                proceed_button =msg_box .addButton ("Proceed Anyway",QMessageBox .AcceptRole )
                msg_box .setDefaultButton (proceed_button )
                msg_box .setEscapeButton (change_button )
                msg_box .exec_ ()

                if msg_box .clickedButton ()==change_button :
                    self .log_signal .emit (f"ℹ️ User chose to change '{first_similar_new }' due to similarity with an alias of '{first_similar_existing }'.")
                    return False 
                self .log_signal .emit (f"⚠️ User proceeded with adding '{first_similar_new }' despite similarity with an alias of '{first_similar_existing }'.")
        new_entry ={
        "name":name_to_add ,
        "is_group":is_group_to_add ,
        "aliases":sorted (list (set (aliases_to_add )),key =str .lower )
        }
        if is_group_to_add :
            for new_alias in new_entry ["aliases"]:
                if any (new_alias .lower ()==kn_entry ["name"].lower ()for kn_entry in KNOWN_NAMES if kn_entry ["name"].lower ()!=name_to_add_lower ):
                    QMessageBox .warning (self ,"Alias Conflict",f"Alias '{new_alias }' (for group '{name_to_add }') conflicts with an existing primary name.");return False 
        KNOWN_NAMES .append (new_entry )
        KNOWN_NAMES .sort (key =lambda x :x ["name"].lower ())

        self .character_list .clear ()
        self .character_list .addItems ([entry ["name"]for entry in KNOWN_NAMES ])
        self .filter_character_list (self .character_search_input .text ())

        log_msg_suffix =f" (as group with aliases: {', '.join (new_entry ['aliases'])})"if is_group_to_add and len (new_entry ['aliases'])>1 else ""
        self .log_signal .emit (f"✅ Added '{name_to_add }' to known names list{log_msg_suffix }.")
        self .new_char_input .clear ()
        return True 

    def _handle_more_options_toggled(self, button, checked):
        """Shows the MoreOptionsDialog when the 'More' radio button is selected."""
        if button == self.radio_more and checked:
            current_scope = self.more_filter_scope or MoreOptionsDialog.SCOPE_CONTENT
            current_format = self.text_export_format or 'pdf'

            dialog = MoreOptionsDialog(
                self,
                current_scope=current_scope,
                current_format=current_format,
                single_pdf_checked=self.single_pdf_setting
            )

            if dialog.exec_() == QDialog.Accepted:
                self.more_filter_scope = dialog.get_selected_scope()
                self.text_export_format = dialog.get_selected_format()
                self.single_pdf_setting = dialog.get_single_pdf_state()
                is_any_pdf_mode = (self.text_export_format == 'pdf')
                scope_text = "Comments" if self.more_filter_scope == MoreOptionsDialog.SCOPE_COMMENTS else "Description"
                format_display = f" ({self.text_export_format.upper()})"
                if self.single_pdf_setting:
                    format_display = " (Single PDF)"
                self.radio_more.setText(f"{scope_text}{format_display}")
                if hasattr(self, 'use_multithreading_checkbox'):
                    self.use_multithreading_checkbox.setEnabled(not is_any_pdf_mode)
                    if is_any_pdf_mode:
                        self.use_multithreading_checkbox.setChecked(False)
                    self._handle_multithreading_toggle(self.use_multithreading_checkbox.isChecked())
                if hasattr(self, 'use_subfolders_checkbox'):
                    self.use_subfolders_checkbox.setEnabled(not self.single_pdf_setting)
                    if self.single_pdf_setting:
                        self.use_subfolders_checkbox.setChecked(False)

                if hasattr(self, 'use_subfolder_per_post_checkbox'):
                    self.use_subfolder_per_post_checkbox.setEnabled(not self.single_pdf_setting)
                    if self.single_pdf_setting:
                        self.use_subfolder_per_post_checkbox.setChecked(False)

                self.log_signal.emit(f"ℹ️ 'More' filter scope set to: {scope_text}, Format: {self.text_export_format.upper()}")
                self.log_signal.emit(f"ℹ️ Single PDF setting: {'Enabled' if self.single_pdf_setting else 'Disabled'}")
                if is_any_pdf_mode:
                    self.log_signal.emit("ℹ️ Multithreading automatically disabled for PDF export.")
            else:
                self.log_signal.emit("ℹ️ 'More' filter selection cancelled. Reverting to 'All'.")
                self.radio_all.setChecked(True)
        elif button != self.radio_more and checked:
            self.radio_more.setText("More")
            self.more_filter_scope = None
            self.single_pdf_setting = False
            if hasattr(self, 'use_multithreading_checkbox'):
                self.use_multithreading_checkbox.setEnabled(True)
                self._update_multithreading_for_date_mode()
            if hasattr(self, 'use_subfolders_checkbox'):
                self.use_subfolders_checkbox.setEnabled(True)
    
    def delete_selected_character (self ):
        global KNOWN_NAMES 
        selected_items =self .character_list .selectedItems ()
        if not selected_items :
            QMessageBox .warning (self ,"Selection Error","Please select one or more names to delete.");return 

        primary_names_to_remove ={item .text ()for item in selected_items }
        confirm =QMessageBox .question (self ,"Confirm Deletion",
        f"Are you sure you want to delete {len (primary_names_to_remove )} selected entry/entries (and their aliases)?",
        QMessageBox .Yes |QMessageBox .No ,QMessageBox .No )
        if confirm ==QMessageBox .Yes :
            original_count =len (KNOWN_NAMES )
            KNOWN_NAMES [:]=[entry for entry in KNOWN_NAMES if entry ["name"]not in primary_names_to_remove ]
            removed_count =original_count -len (KNOWN_NAMES )

            if removed_count >0 :
                self .log_signal .emit (f"🗑️ Removed {removed_count } name(s).")
                self .character_list .clear ()
                self .character_list .addItems ([entry ["name"]for entry in KNOWN_NAMES ])
                self .filter_character_list (self .character_search_input .text ())
                self .save_known_names ()
            else :
                self .log_signal .emit ("ℹ️ No names were removed (they might not have been in the list).")


    def update_custom_folder_visibility (self ,url_text =None ):
        if url_text is None :
            url_text =self .link_input .text ()

        _ ,_ ,post_id =extract_post_info (url_text .strip ())

        is_single_post_url =bool (post_id )
        
        subfolders_by_known_txt_enabled = getattr(self, 'use_subfolders_checkbox', None) and self.use_subfolders_checkbox.isChecked()
        subfolder_per_post_enabled = getattr(self, 'use_subfolder_per_post_checkbox', None) and self.use_subfolder_per_post_checkbox.isChecked()
        any_subfolder_option_enabled = subfolders_by_known_txt_enabled or subfolder_per_post_enabled

        not_only_links_or_archives_mode =not (
        (self .radio_only_links and self .radio_only_links .isChecked ())or 
        (self .radio_only_archives and self .radio_only_archives .isChecked ())or 
        (hasattr (self ,'radio_only_audio')and self .radio_only_audio .isChecked ())
        )

        should_show_custom_folder =is_single_post_url and any_subfolder_option_enabled and not_only_links_or_archives_mode 

        if self .custom_folder_widget :
            self .custom_folder_widget .setVisible (should_show_custom_folder )

        if not (self .custom_folder_widget and self .custom_folder_widget .isVisible ()):
            if self .custom_folder_input :self .custom_folder_input .clear ()


    def update_ui_for_subfolders (self ,separate_folders_by_name_title_checked :bool ):
        is_only_links =self .radio_only_links and self .radio_only_links .isChecked ()
        is_only_archives =self .radio_only_archives and self .radio_only_archives .isChecked ()
        is_only_audio =hasattr (self ,'radio_only_audio')and self .radio_only_audio .isChecked ()

        can_enable_subfolder_per_post_checkbox =not is_only_links 

        if self .use_subfolder_per_post_checkbox :
            self .use_subfolder_per_post_checkbox .setEnabled (can_enable_subfolder_per_post_checkbox )

            if not can_enable_subfolder_per_post_checkbox :
                self .use_subfolder_per_post_checkbox .setChecked (False )

        if hasattr(self, 'date_prefix_checkbox'):
            can_enable_date_prefix = self.use_subfolder_per_post_checkbox.isEnabled() and self.use_subfolder_per_post_checkbox.isChecked()
            self.date_prefix_checkbox.setEnabled(can_enable_date_prefix)
            if not can_enable_date_prefix:
                self.date_prefix_checkbox.setChecked(False)

        self .update_custom_folder_visibility ()


    def _update_cookie_input_visibility (self ,checked ):
        cookie_text_input_exists =hasattr (self ,'cookie_text_input')
        cookie_browse_button_exists =hasattr (self ,'cookie_browse_button')

        if cookie_text_input_exists or cookie_browse_button_exists :
            is_only_links =self .radio_only_links and self .radio_only_links .isChecked ()
            if cookie_text_input_exists :self .cookie_text_input .setVisible (checked )
            if cookie_browse_button_exists :self .cookie_browse_button .setVisible (checked )

            can_enable_cookie_text =checked and not is_only_links 
            enable_state_for_fields =can_enable_cookie_text and (self .download_btn .isEnabled ()or self .is_paused )

            if cookie_text_input_exists :
                self .cookie_text_input .setEnabled (enable_state_for_fields )
                if self .selected_cookie_filepath and checked :
                    self .cookie_text_input .setText (self .selected_cookie_filepath )
                    self .cookie_text_input .setReadOnly (True )
                    self .cookie_text_input .setPlaceholderText ("")
                elif checked :
                    self .cookie_text_input .setReadOnly (False )
                    self .cookie_text_input .setPlaceholderText ("Cookie string (if no cookies.txt)")

            if cookie_browse_button_exists :self .cookie_browse_button .setEnabled (enable_state_for_fields )

            if not checked :
                self .selected_cookie_filepath =None 


    def update_page_range_enabled_state (self ):
        url_text =self .link_input .text ().strip ()if self .link_input else ""
        _ ,_ ,post_id =extract_post_info (url_text )

        is_creator_feed =not post_id if url_text else False 
        enable_page_range =is_creator_feed 

        for widget in [self .page_range_label ,self .start_page_input ,self .to_label ,self .end_page_input ]:
            if widget :widget .setEnabled (enable_page_range )

        if not enable_page_range :
            if self .start_page_input :self .start_page_input .clear ()
            if self .end_page_input :self .end_page_input .clear ()


    def _update_manga_filename_style_button_text (self ):
        if self .manga_rename_toggle_button :
            if self .manga_filename_style ==STYLE_POST_TITLE :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_post_title_text","Name: Post Title"))

            elif self .manga_filename_style ==STYLE_ORIGINAL_NAME :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_date_original_text","Date + Original"))

            elif self .manga_filename_style ==STYLE_POST_TITLE_GLOBAL_NUMBERING :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_title_global_num_text","Name: Title+G.Num"))

            elif self .manga_filename_style ==STYLE_DATE_BASED :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_date_based_text","Name: Date Based"))
            
            elif self .manga_filename_style ==STYLE_POST_ID: # Add this block
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_post_id_text","Name: Post ID"))

            elif self .manga_filename_style ==STYLE_DATE_POST_TITLE :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_date_post_title_text","Name: Date + Title"))

            elif self.manga_filename_style == STYLE_CUSTOM:
                self.manga_rename_toggle_button.setText(self._tr("manga_style_custom_text", "Name: Custom"))

            else :
                self .manga_rename_toggle_button .setText (self ._tr ("manga_style_unknown_text","Name: Unknown Style"))

            self .manga_rename_toggle_button .setToolTip ("Click to cycle Manga Filename Style (when Renaming Mode is active for a creator feed).")

    def _toggle_manga_filename_style (self ):
        url_text = self.link_input.text().strip() if self.link_input else ""
        _, _, post_id = extract_post_info(url_text)
        is_single_post = bool(post_id)

        current_style = self.manga_filename_style
        new_style = ""

        if is_single_post:
            # Cycle through a limited set of styles suitable for single posts
            if current_style == STYLE_POST_TITLE:
                new_style = STYLE_DATE_POST_TITLE
            elif current_style == STYLE_DATE_POST_TITLE:
                new_style = STYLE_ORIGINAL_NAME
            elif current_style == STYLE_ORIGINAL_NAME:
                new_style = STYLE_POST_ID
            elif current_style == STYLE_POST_ID:
                new_style = STYLE_CUSTOM  
            elif current_style == STYLE_CUSTOM:  
                new_style = STYLE_POST_TITLE  
            else: # Fallback for any other style
                new_style = STYLE_POST_TITLE
        else:
            # Original cycling logic for creator feeds
            if current_style ==STYLE_POST_TITLE :
                new_style =STYLE_ORIGINAL_NAME 
            elif current_style ==STYLE_ORIGINAL_NAME :
                new_style =STYLE_DATE_POST_TITLE 
            elif current_style ==STYLE_DATE_POST_TITLE :
                new_style =STYLE_POST_TITLE_GLOBAL_NUMBERING 
            elif current_style ==STYLE_POST_TITLE_GLOBAL_NUMBERING :
                new_style =STYLE_DATE_BASED 
            elif current_style ==STYLE_DATE_BASED :
                new_style =STYLE_POST_ID 
            elif current_style ==STYLE_POST_ID: 
                new_style =STYLE_CUSTOM # <-- CHANGE THIS
            elif current_style == STYLE_CUSTOM: # <-- ADD THIS
                new_style = STYLE_POST_TITLE # <-- ADD THIS
            else :
                self .log_signal .emit (f"⚠️ Unknown current manga filename style: {current_style }. Resetting to default ('{STYLE_POST_TITLE }').")
                new_style =STYLE_POST_TITLE 

        self .manga_filename_style =new_style 
        self .settings .setValue (MANGA_FILENAME_STYLE_KEY ,self .manga_filename_style )
        self .settings .sync ()
        self ._update_manga_filename_style_button_text ()
        self .update_ui_for_manga_mode (self .manga_mode_checkbox .isChecked ()if self .manga_mode_checkbox else False )
        self .log_signal .emit (f"ℹ️ Manga filename style changed to: '{self .manga_filename_style }'")

    def _handle_favorite_mode_toggle (self ,checked ):
        if not self .url_or_placeholder_stack or not self .bottom_action_buttons_stack :
            return 

        self .url_or_placeholder_stack .setCurrentIndex (1 if checked else 0 )
        self .bottom_action_buttons_stack .setCurrentIndex (1 if checked else 0 )

        if checked :
            if self .link_input :
                self .link_input .clear ()
                self .link_input .setEnabled (False )
            for widget in [self .page_range_label ,self .start_page_input ,self .to_label ,self .end_page_input ]:
                if widget :widget .setEnabled (False )
            if self .start_page_input :self .start_page_input .clear ()
            if self .end_page_input :self .end_page_input .clear ()

            self .update_custom_folder_visibility ()
            self .update_page_range_enabled_state ()
            if self .manga_mode_checkbox :
                self .manga_mode_checkbox .setChecked (False )
                self .manga_mode_checkbox .setEnabled (False )
            if hasattr (self ,'use_cookie_checkbox'):
                self .use_cookie_checkbox .setChecked (True )
                self .use_cookie_checkbox .setEnabled (False )
            if hasattr (self ,'use_cookie_checkbox'):
                self ._update_cookie_input_visibility (True )
            self .update_ui_for_manga_mode (False )

            if hasattr (self ,'favorite_mode_artists_button'):
                self .favorite_mode_artists_button .setEnabled (True )
            if hasattr (self ,'favorite_mode_posts_button'):
                self .favorite_mode_posts_button .setEnabled (True )

        else :
            if self .link_input :self .link_input .setEnabled (True )
            self .update_page_range_enabled_state ()
            self .update_custom_folder_visibility ()
            self .update_ui_for_manga_mode (self .manga_mode_checkbox .isChecked ()if self .manga_mode_checkbox else False )

            if hasattr (self ,'use_cookie_checkbox'):
                self .use_cookie_checkbox .setEnabled (True )
            if hasattr (self ,'use_cookie_checkbox'):
                self ._update_cookie_input_visibility (self .use_cookie_checkbox .isChecked ())

            if hasattr (self ,'favorite_mode_artists_button'):
                self .favorite_mode_artists_button .setEnabled (False )
            if hasattr (self ,'favorite_mode_posts_button'):
                self .favorite_mode_posts_button .setEnabled (False )

    def update_ui_for_manga_mode (self ,checked ):
        # --- START: NEW DISCORD UI LOGIC ---
        url_text =self .link_input .text ().strip ()if self .link_input else ""
        service, _, _ = extract_post_info(url_text)
        is_discord_url = (service == 'discord')

        if is_discord_url:
            # When a discord URL is detected, disable incompatible options
            if self.manga_mode_checkbox:
                self.manga_mode_checkbox.setEnabled(False)
                self.manga_mode_checkbox.setChecked(False)
            if self.page_range_label: self.page_range_label.setEnabled(False)
            if self.start_page_input: self.start_page_input.setEnabled(False)
            if self.to_label: self.to_label.setEnabled(False)
            if self.end_page_input: self.end_page_input.setEnabled(False)
            checked = False # Force manga mode off
        # --- END: NEW DISCORD UI LOGIC ---

        is_only_links_mode =self .radio_only_links and self .radio_only_links .isChecked ()
        is_only_archives_mode =self .radio_only_archives and self .radio_only_archives .isChecked ()
        is_only_audio_mode =hasattr (self ,'radio_only_audio')and self .radio_only_audio .isChecked ()

        # The rest of the original function continues from here...
        _ ,_ ,post_id =extract_post_info (url_text )

        is_creator_feed =not post_id if url_text else False 
        is_single_post = bool(post_id)
        is_favorite_mode_on =self .favorite_mode_checkbox .isChecked ()if self .favorite_mode_checkbox else False 

        if self.favorite_download_queue and all(item.get('type') == 'single_post_from_popup' for item in self.favorite_download_queue):
            is_single_post = True

        # --- MODIFIED: Added check for is_discord_url ---
        can_enable_manga_checkbox = (is_creator_feed or is_single_post) and not is_favorite_mode_on and not is_discord_url
        
        if self .manga_mode_checkbox :
            self .manga_mode_checkbox .setEnabled (can_enable_manga_checkbox)
            if not can_enable_manga_checkbox and self .manga_mode_checkbox .isChecked ():
                self .manga_mode_checkbox .setChecked (False )
                checked =self .manga_mode_checkbox .isChecked ()

        manga_mode_effectively_on = can_enable_manga_checkbox and checked

        sequential_styles = [STYLE_DATE_BASED, STYLE_POST_TITLE_GLOBAL_NUMBERING]
        if is_single_post and self.manga_filename_style in sequential_styles:
            self.manga_filename_style = STYLE_POST_TITLE 
            self._update_manga_filename_style_button_text()

        if self .manga_rename_toggle_button :
            self .manga_rename_toggle_button .setVisible (manga_mode_effectively_on and not (is_only_links_mode or is_only_archives_mode or is_only_audio_mode ))

        # --- MODIFIED: Added check for is_discord_url ---
        if not is_discord_url:
            self .update_page_range_enabled_state ()

        current_filename_style =self .manga_filename_style 
        show_date_prefix_input =(
        manga_mode_effectively_on and 
        (current_filename_style ==STYLE_DATE_BASED) and 
        not (is_only_links_mode or is_only_archives_mode or is_only_audio_mode )
        )
        if hasattr (self ,'manga_date_prefix_input'):
            self .manga_date_prefix_input .setVisible (show_date_prefix_input )
            if show_date_prefix_input :
                self .manga_date_prefix_input .setMaximumWidth (120 )
                self .manga_date_prefix_input .setMinimumWidth (60 )
            else :
                self .manga_date_prefix_input .clear ()
                self .manga_date_prefix_input .setMaximumWidth (16777215 )
                self .manga_date_prefix_input .setMinimumWidth (0 )

        if hasattr(self, 'multipart_toggle_button'):
            hide_multipart_button_due_mode = is_only_links_mode or is_only_archives_mode or is_only_audio_mode
            self.multipart_toggle_button.setVisible(not hide_multipart_button_due_mode)
  
        if hasattr(self, 'custom_rename_dialog_button'):
            is_custom_mode = self.manga_filename_style == STYLE_CUSTOM
            self.custom_rename_dialog_button.setVisible(manga_mode_effectively_on and is_custom_mode)

        self ._update_multithreading_for_date_mode ()

    def filter_character_list (self ,search_text ):
        search_text_lower =search_text .lower ()
        for i in range (self .character_list .count ()):
            item =self .character_list .item (i )
            item .setHidden (search_text_lower not in item .text ().lower ())

    def _show_custom_rename_dialog(self):
        """Shows the dialog to edit the custom manga filename format."""
        dialog = CustomFilenameDialog(self.custom_manga_filename_format, self.manga_custom_date_format, self)
        if dialog.exec_() == QDialog.Accepted:
            self.custom_manga_filename_format = dialog.get_format_string()
            self.manga_custom_date_format = dialog.get_date_format_string()
            self.settings.setValue(MANGA_CUSTOM_FORMAT_KEY, self.custom_manga_filename_format)
            self.settings.setValue(MANGA_CUSTOM_DATE_FORMAT_KEY, self.manga_custom_date_format)
            self.log_signal.emit(f"ℹ️ Custom filename format set to: '{self.custom_manga_filename_format}'")
            self.log_signal.emit(f"ℹ️ Custom date format set to: '{self.manga_custom_date_format}'")
            self._update_manga_filename_style_button_text()


    def update_multithreading_label (self ,text ):
        if self .use_multithreading_checkbox .isChecked ():
            base_text =self ._tr ("use_multithreading_checkbox_base_label","Use Multithreading")
            try :
                num_threads_val =int (text )
                if num_threads_val >0 :self .use_multithreading_checkbox .setText (f"{base_text } ({num_threads_val } Threads)")
                else :self .use_multithreading_checkbox .setText (f"{base_text } (Invalid: >0)")
            except ValueError :
                self .use_multithreading_checkbox .setText (f"{base_text } (Invalid Input)")
        else :
            self .use_multithreading_checkbox .setText (f"{self ._tr ('use_multithreading_checkbox_base_label','Use Multithreading')} (1 Thread)")


    def _handle_multithreading_toggle (self ,checked ):
        if not checked :
            self .thread_count_input .setEnabled (False )
            self .thread_count_label .setEnabled (False )
            self .use_multithreading_checkbox .setText ("Use Multithreading (1 Thread)")
        else :
            self .thread_count_input .setEnabled (True )
            self .thread_count_label .setEnabled (True )
            self .update_multithreading_label (self .thread_count_input .text ())

    def _update_multithreading_for_date_mode (self ):
        """
        Checks if Renaming Mode is ON and 'Date Based' style is selected.
        If so, disables multithreading. Otherwise, enables it.
        """
        if not hasattr (self ,'manga_mode_checkbox')or not hasattr (self ,'use_multithreading_checkbox'):
            return 

        manga_on =self .manga_mode_checkbox .isChecked ()
        is_sequential_style_requiring_single_thread =(
        self .manga_filename_style ==STYLE_DATE_BASED or 
        self .manga_filename_style ==STYLE_POST_TITLE_GLOBAL_NUMBERING 
        )
        if manga_on and is_sequential_style_requiring_single_thread :
            if self .use_multithreading_checkbox .isChecked ()or self .use_multithreading_checkbox .isEnabled ():
                if self .use_multithreading_checkbox .isChecked ():
                    self .log_signal .emit ("ℹ️ Manga Date Mode: Multithreading for post processing has been disabled to ensure correct sequential file numbering.")
                self .use_multithreading_checkbox .setChecked (False )
            self .use_multithreading_checkbox .setEnabled (False )
            self ._handle_multithreading_toggle (False )
        else:
            # This block runs when multithreading is PERMITTED by the renaming mode
            if not self.use_multithreading_checkbox.isEnabled():
                self.use_multithreading_checkbox.setEnabled(True)
                # Restore the checkbox to its default 'checked' state when re-enabled
                self.use_multithreading_checkbox.setChecked(True)
            
            # Now, update the rest of the UI based on the (now correct) checkbox state
            self._handle_multithreading_toggle(self.use_multithreading_checkbox.isChecked())

    def update_progress_display (self ,total_posts ,processed_posts ):
        if total_posts >0 :
            progress_percent =(processed_posts /total_posts )*100 
            self .progress_label .setText (self ._tr ("progress_posts_text","Progress: {processed_posts} / {total_posts} posts ({progress_percent:.1f}%)").format (processed_posts =processed_posts ,total_posts =total_posts ,progress_percent =progress_percent ))
        elif processed_posts >0 :
            self .progress_label .setText (self ._tr ("progress_processing_post_text","Progress: Processing post {processed_posts}...").format (processed_posts =processed_posts ))
        else :
            self .progress_label .setText (self ._tr ("progress_starting_text","Progress: Starting..."))

        if total_posts >0 or processed_posts >0 :
            self .file_progress_label .setText ("")

    def _set_ui_for_specialized_downloader(self, is_specialized):
        """Disables or enables UI elements for non-standard downloaders."""
        widgets_to_disable = [
            self.page_range_label, self.start_page_input, self.to_label, self.end_page_input,
            self.character_filter_widget, self.skip_words_input, self.skip_scope_toggle_button,
            self.remove_from_filename_input, self.radio_images, self.radio_videos,
            self.radio_only_archives, self.radio_only_links, self.radio_only_audio, self.radio_more,
            self.skip_zip_checkbox, self.download_thumbnails_checkbox, self.compress_images_checkbox,
            self.use_subfolders_checkbox, self.use_subfolder_per_post_checkbox,
            self.scan_content_images_checkbox, self.external_links_checkbox, self.manga_mode_checkbox,
            self.use_cookie_checkbox, self.keep_duplicates_checkbox, self.date_prefix_checkbox,
            self.manga_rename_toggle_button, self.manga_date_prefix_input,
            self.multipart_toggle_button, self.custom_folder_input, self.custom_folder_label,
            self.discord_scope_toggle_button
        ]

        enable_state = not is_specialized

        for widget in widgets_to_disable:
            if widget:
                widget.setEnabled(enable_state)
        
        # When disabling, force 'All' to be checked and disable it too
        if is_specialized and self.radio_all:
            self.radio_all.setChecked(True)
            self.radio_all.setEnabled(False)
        elif self.radio_all:
            self.radio_all.setEnabled(True)

        # Re-run standard UI logic when re-enabling to restore correct states
        if enable_state:
            self._update_all_ui_states()

    def _update_all_ui_states(self):
        """A single function to call all UI update methods to restore state."""
        is_manga_checked = self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False
        is_subfolder_checked = self.use_subfolders_checkbox.isChecked() if self.use_subfolders_checkbox else False
        is_cookie_checked = self.use_cookie_checkbox.isChecked() if self.use_cookie_checkbox else False
        
        self.update_ui_for_manga_mode(is_manga_checked)
        self.update_custom_folder_visibility()
        self.update_page_range_enabled_state()
        if self.radio_group.checkedButton():
             self._handle_filter_mode_change(self.radio_group.checkedButton(), True)
        self.update_ui_for_subfolders(is_subfolder_checked)
        self._update_cookie_input_visibility(is_cookie_checked)

    def _update_contextual_ui_elements(self, text=""):
        """Shows or hides UI elements based on the URL, like the Discord scope button."""
        if not hasattr(self, 'discord_scope_toggle_button'): return
        
        url_text = self.link_input.text().strip()
        service, _, _ = extract_post_info(url_text) 

        is_any_discord_url = (service == 'discord')
        is_official_discord_url = 'discord.com' in url_text and is_any_discord_url

        if is_official_discord_url:
            self.remove_from_filename_label_widget.setText("🔑 Discord Token:")
            self.remove_from_filename_input.setPlaceholderText("Enter your Discord Authorization Token here")
            self.remove_from_filename_input.setEchoMode(QLineEdit.Password) 
            saved_token = self.settings.value(DISCORD_TOKEN_KEY, "")
            if saved_token:
                self.remove_from_filename_input.setText(saved_token)
        else:
            # Revert to the standard input for Kemono, Coomer, etc.
            self.remove_from_filename_label_widget.setText(self._tr("remove_words_from_name_label", "✂️ Remove Words from name:"))
            self.remove_from_filename_input.setPlaceholderText(self._tr("remove_from_filename_input_placeholder_text", "e.g., patreon, HD"))
            self.remove_from_filename_input.setEchoMode(QLineEdit.Normal)

        is_saint2 = 'saint2.su' in url_text or 'saint2.pk' in url_text
        is_erome = 'erome.com' in url_text 
        is_specialized = service in ['bunkr', 'nhentai', 'hentai2read'] or is_saint2 or is_erome
        self._set_ui_for_specialized_downloader(is_specialized)

        self.discord_scope_toggle_button.setVisible(is_any_discord_url)
        if hasattr(self, 'discord_message_limit_input'):
            self.discord_message_limit_input.setVisible(is_official_discord_url)

        if is_any_discord_url: 
            self._update_discord_scope_button_text()
        elif not is_specialized:
             self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))

    def _update_discord_scope_button_text(self):
        """Updates the text of the discord scope button and the main download button."""
        if self.discord_download_scope == 'files':
            self.discord_scope_toggle_button.setText("Scope: Files")
            self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
        else:
             self.discord_scope_toggle_button.setText("Scope: Messages")
             self.download_btn.setText("📄 Save Messages as PDF")

    def _cycle_discord_scope(self):
        """Toggles between 'files' and 'messages' for Discord downloads."""
        self.discord_download_scope = 'messages' if self.discord_download_scope == 'files' else 'files'
        self._update_discord_scope_button_text()
    
    def start_download(self, direct_api_url=None, override_output_dir=None, is_restore=False, is_continuation=False, item_type_from_queue=None):
        from ..utils.file_utils import clean_folder_name
        from ..config.constants import FOLDER_NAME_STOP_WORDS

        if self.is_ready_to_download_fetched:
            self._start_download_of_fetched_posts()
            return True

        self.is_finishing = False
        if self.active_update_profile:
            if not self.new_posts_for_update:
                return self._check_for_updates()
            else:
                return self._start_confirmed_update_download()

        self.is_finishing = False
        self.downloaded_hash_counts.clear()
        global KNOWN_NAMES, BackendDownloadThread, PostProcessorWorker, extract_post_info, MAX_FILE_THREADS_PER_POST_OR_WORKER

        if not is_restore and not is_continuation:
            self.permanently_failed_files_for_dialog.clear()

        self.retryable_failed_files_info.clear()
        self._update_error_button_count()

        self._clear_stale_temp_files()
        self.session_temp_files = []

        processed_post_ids_for_restore = []
        manga_counters_for_restore = None
        start_offset_for_restore = 0

        if is_restore and self.interrupted_session_data:
            self.log_signal.emit("   Restoring session state...")
            download_state = self.interrupted_session_data.get("download_state", {})
            processed_post_ids_for_restore = download_state.get("processed_post_ids", [])
            start_offset_for_restore = download_state.get("last_processed_offset", 0)
            restored_hashes = download_state.get("successfully_downloaded_hashes", [])
            if restored_hashes:
                with self.downloaded_file_hashes_lock:
                    self.downloaded_file_hashes.update(restored_hashes)
                self.log_signal.emit(f"   Restored memory of {len(restored_hashes)} successfully downloaded files.")
            manga_counters_for_restore = download_state.get("manga_counters")
            if processed_post_ids_for_restore:
                self.log_signal.emit(f"   Will skip {len(processed_post_ids_for_restore)} already processed posts.")
            if start_offset_for_restore > 0:
                self.log_signal.emit(f"   Resuming fetch from page offset: {start_offset_for_restore}")
            if manga_counters_for_restore:
                self.log_signal.emit(f"   Restoring manga counters: {manga_counters_for_restore}")

        if self._is_download_active():
            QMessageBox.warning(self, "Busy", "A download is already in progress.")
            return False

        if not is_restore and not direct_api_url and self.favorite_download_queue and not self.is_processing_favorites_queue:
            self.log_signal.emit(f"ℹ️ Detected {len(self.favorite_download_queue)} item(s) in the queue. Starting processing...")
            self.cancellation_message_logged_this_session = False
            self._process_next_favorite_download()
            return True

        if not is_restore and self.interrupted_session_data:
            self.log_signal.emit("ℹ️ New download started. Discarding previous interrupted session.")
            self._clear_session_file()
            self.interrupted_session_data = None
            self.is_restore_pending = False

        api_url = direct_api_url if direct_api_url else self.link_input.text().strip()

        # --- START: MOVED AND CORRECTED LOGIC ---
        # This block is moved to run before any special URL checks.
        main_ui_download_dir = self.dir_input.text().strip()
        extract_links_only = (self.radio_only_links and self.radio_only_links.isChecked())
        effective_output_dir_for_run = ""

        if override_output_dir:
            if not main_ui_download_dir:
                QMessageBox.critical(self, "Configuration Error",
                                     "The main 'Download Location' must be set in the UI "
                                     "before downloading favorites with 'Artist Folders' scope.")
                if self.is_processing_favorites_queue:
                    self.log_signal.emit(f"❌ Favorite download for '{api_url}' skipped: Main download directory not set.")
                return False

            if not os.path.isdir(main_ui_download_dir):
                QMessageBox.critical(self, "Directory Error",
                                     f"The main 'Download Location' ('{main_ui_download_dir}') "
                                     "does not exist or is not a directory. Please set a valid one for 'Artist Folders' scope.")
                if self.is_processing_favorites_queue:
                    self.log_signal.emit(f"❌ Favorite download for '{api_url}' skipped: Main download directory invalid.")
                return False
            effective_output_dir_for_run = os.path.normpath(override_output_dir)
        else:
            is_special_downloader = 'saint2.su' in api_url or 'saint2.pk' in api_url or 'nhentai.net' in api_url or 'bunkr' in api_url or 'erome.com' in api_url
            
            if not extract_links_only and not main_ui_download_dir:
                QMessageBox.critical(self, "Input Error", "Download Directory is required.")
                return False

            if not extract_links_only and main_ui_download_dir and not os.path.isdir(main_ui_download_dir):
                reply = QMessageBox.question(self, "Create Directory?",
                                             f"The directory '{main_ui_download_dir}' does not exist.\nCreate it now?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    try:
                        os.makedirs(main_ui_download_dir, exist_ok=True)
                        self.log_signal.emit(f"ℹ️ Created directory: {main_ui_download_dir}")
                    except Exception as e:
                        QMessageBox.critical(self, "Directory Error", f"Could not create directory: {e}")
                        return False
                else:
                    self.log_signal.emit("❌ Download cancelled: Output directory does not exist and was not created.")
                    return False
            effective_output_dir_for_run = os.path.normpath(main_ui_download_dir) if main_ui_download_dir else ""

        if 'erome.com' in api_url:
            self.log_signal.emit("ℹ️ Erome.com URL detected. Starting dedicated Erome download.")
            self.set_ui_enabled(False)

            self.download_thread = EromeDownloadThread(api_url, effective_output_dir_for_run, self)
            self.download_thread.progress_signal.connect(self.handle_main_log)
            self.download_thread.file_progress_signal.connect(self.update_file_progress_display)
            self.download_thread.finished_signal.connect(
                lambda dl, skip, cancelled: self.download_finished(dl, skip, cancelled, [])
            )
            self.download_thread.start()
            self._update_button_states_and_connections()
            return True

        if 'nhentai.net' in api_url and not re.search(r'/g/(\d+)', api_url):
            self.log_signal.emit("=" * 40)
            self.log_signal.emit("🚀 nhentai batch download mode detected.")
            
            nhentai_txt_path = os.path.join(self.app_base_dir, "appdata", "nhentai.txt")
            self.log_signal.emit(f"   Looking for batch file at: {nhentai_txt_path}")

            if not os.path.exists(nhentai_txt_path):
                QMessageBox.warning(self, "File Not Found", f"To use batch mode, create a file named 'nhentai.txt' in your 'appdata' folder.\n\nPlace one nhentai URL on each line.")
                self.log_signal.emit(f"   ❌ 'nhentai.txt' not found. Aborting batch download.")
                return False

            urls_to_download = []
            try:
                with open(nhentai_txt_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        found_urls = re.findall(r'https?://nhentai\.net/g/\d+/?', line)
                        if found_urls:
                            urls_to_download.extend(found_urls)
            except Exception as e:
                QMessageBox.critical(self, "File Error", f"Could not read 'nhentai.txt':\n{e}")
                self.log_signal.emit(f"   ❌ Error reading 'nhentai.txt': {e}")
                return False

            if not urls_to_download:
                QMessageBox.information(self, "Empty File", "No valid nhentai gallery URLs were found in 'nhentai.txt'.")
                self.log_signal.emit("   'nhentai.txt' was found but contained no valid URLs.")
                return False
            
            self.log_signal.emit(f"   Found {len(urls_to_download)} URLs to process.")
            self.favorite_download_queue.clear()
            for url in urls_to_download:
                self.favorite_download_queue.append({
                    'url': url,
                    'name': f"nhentai gallery from batch",
                    'type': 'post'
                })
            
            if not self.is_processing_favorites_queue:
                self._process_next_favorite_download()
            return True

        is_saint2_url = 'saint2.su' in api_url or 'saint2.pk' in api_url
        if is_saint2_url:
            # First, check if it's the batch command. If so, do nothing here and let the next block handle it.
            if api_url.strip().lower() != 'saint2.su':
                self.log_signal.emit("ℹ️ Saint2.su URL detected. Starting dedicated Saint2 download.")
                self.set_ui_enabled(False)
                self.download_thread = Saint2DownloadThread(api_url, effective_output_dir_for_run, self)
                self.download_thread.progress_signal.connect(self.handle_main_log)
                self.download_thread.file_progress_signal.connect(self.update_file_progress_display)
                self.download_thread.finished_signal.connect(
                    lambda dl, skip, cancelled: self.download_finished(dl, skip, cancelled, [])
                )
                self.download_thread.start()
                self._update_button_states_and_connections()
                return True

        if api_url.strip().lower() == 'saint2.su':
            self.log_signal.emit("=" * 40)
            self.log_signal.emit("🚀 Saint2.su batch download mode detected.")
            
            saint2_txt_path = os.path.join(self.app_base_dir, "appdata", "saint2.su.txt")
            self.log_signal.emit(f"   Looking for batch file at: {saint2_txt_path}")

            if not os.path.exists(saint2_txt_path):
                QMessageBox.warning(self, "File Not Found", f"To use batch mode, create a file named 'saint2.su.txt' in your 'appdata' folder.\n\nPlace one saint2.su URL on each line.")
                self.log_signal.emit(f"   ❌ 'saint2.su.txt' not found. Aborting batch download.")
                return False

            urls_to_download = []
            try:
                with open(saint2_txt_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        # Find valid saint2 URLs in the line
                        found_urls = re.findall(r'https?://saint\d*\.(?:su|pk|cr|to)/(?:a|d|embed)/[^/?#\s]+', line)
                        if found_urls:
                            urls_to_download.extend(found_urls)
            except Exception as e:
                QMessageBox.critical(self, "File Error", f"Could not read 'saint2.su.txt':\n{e}")
                self.log_signal.emit(f"   ❌ Error reading 'saint2.su.txt': {e}")
                return False

            if not urls_to_download:
                QMessageBox.information(self, "Empty File", "No valid saint2.su URLs were found in 'saint2.su.txt'.")
                self.log_signal.emit("   'saint2.su.txt' was found but contained no valid URLs.")
                return False
            
            self.log_signal.emit(f"   Found {len(urls_to_download)} URLs to process.")
            self.favorite_download_queue.clear()
            for url in urls_to_download:
                self.favorite_download_queue.append({
                    'url': url,
                    'name': f"saint2.su link from batch",
                    'type': 'post' # Treat each URL as a single post-like item
                })
            
            if not self.is_processing_favorites_queue:
                self._process_next_favorite_download()
            return True

        if api_url.strip().lower() in ['hentai2read.com', 'https://hentai2read.com', 'http://hentai2read.com']:
            self.log_signal.emit("=" * 40)
            self.log_signal.emit("🚀 Hentai2Read batch download mode detected.")
            
            h2r_txt_path = os.path.join(self.app_base_dir, "appdata", "hentai2read.txt")
            self.log_signal.emit(f"   Looking for batch file at: {h2r_txt_path}")

            if not os.path.exists(h2r_txt_path):
                QMessageBox.warning(self, "File Not Found", f"To use batch mode, create a file named 'hentai2read.txt' in your 'appdata' folder.\n\nPlace one Hentai2Read gallery URL on each line.")
                self.log_signal.emit(f"   ❌ 'hentai2read.txt' not found. Aborting batch download.")
                return False

            urls_to_download = []
            try:
                with open(h2r_txt_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        found_urls = re.findall(r'https?://hentai2read\.com/[^/]+/\d+/?', line)
                        if found_urls:
                            urls_to_download.extend(found_urls)
            except Exception as e:
                QMessageBox.critical(self, "File Error", f"Could not read 'hentai2read.txt':\n{e}")
                self.log_signal.emit(f"   ❌ Error reading 'hentai2read.txt': {e}")
                return False

            if not urls_to_download:
                QMessageBox.information(self, "Empty File", "No valid Hentai2Read gallery URLs were found in 'hentai2read.txt'.")
                self.log_signal.emit("   'hentai2read.txt' was found but contained no valid URLs.")
                return False
            
            self.log_signal.emit(f"   Found {len(urls_to_download)} URLs to process.")
            self.favorite_download_queue.clear()
            for url in urls_to_download:
                self.favorite_download_queue.append({
                    'url': url,
                    'name': f"Hentai2Read gallery from batch",
                    'type': 'post'
                })
            
            if not self.is_processing_favorites_queue:
                self._process_next_favorite_download()
            return True

        if not is_restore:
            self._create_initial_session_file(api_url, effective_output_dir_for_run, remaining_queue=self.favorite_download_queue)

        self.download_history_candidates.clear()
        self._update_button_states_and_connections()

        if self.favorite_mode_checkbox and self.favorite_mode_checkbox.isChecked() and not direct_api_url and not api_url:
            QMessageBox.information(self, "Favorite Mode Active",
                                    "Favorite Mode is active. Please use the 'Favorite Artists' or 'Favorite Posts' buttons to start downloads in this mode, or uncheck 'Favorite Mode' to use the URL input.")
            self.set_ui_enabled(True)
            return False

        if not api_url and not self.favorite_download_queue:
            QMessageBox.critical(self, "Input Error", "URL is required.")
            return False
        elif not api_url and self.favorite_download_queue:
            self.log_signal.emit("ℹ️ URL input is empty, but queue has items. Processing queue...")
            self.cancellation_message_logged_this_session = False
            self._process_next_favorite_download()
            return True

        self.cancellation_message_logged_this_session = False
        
        service, id1, id2 = extract_post_info(api_url)

        if 'discord.com' in api_url and service == 'discord':
            server_id, channel_id = id1, id2
            token = self.remove_from_filename_input.text().strip()
            output_dir = self.dir_input.text().strip()

            if not token or not output_dir:
                QMessageBox.critical(self, "Input Error", "A Discord Token and Download Location are required.")
                return False

            limit_text = self.discord_message_limit_input.text().strip()
            message_limit = int(limit_text) if limit_text else None
            if message_limit:
                self.log_signal.emit(f"ℹ️ Applying message limit: will fetch up to {message_limit} latest messages.")

            mode = 'pdf' if self.discord_download_scope == 'messages' else 'files'
            
            # 1. Create the thread object
            self.download_thread = DiscordDownloadThread(
                mode=mode, session=requests.Session(), token=token, output_dir=output_dir,
                server_id=server_id, channel_id=channel_id, url=api_url, limit=message_limit, parent=self
            )

            self.download_thread.progress_signal.connect(self.handle_main_log)
            self.download_thread.progress_label_signal.connect(self.progress_label.setText)
            self.download_thread.finished_signal.connect(self.download_finished)
            
            self.download_thread.start()
            
            self.set_ui_enabled(False)
            self._update_button_states_and_connections()
            
            return True

        if service == 'hentai2read':
            self.log_signal.emit("=" * 40)
            self.log_signal.emit(f"🚀 Detected Hentai2Read gallery: {id1}")

            if not effective_output_dir_for_run or not os.path.isdir(effective_output_dir_for_run):
                QMessageBox.critical(self, "Input Error", "A valid Download Location is required.")
                return False

            self.set_ui_enabled(False)
            self.download_thread = Hentai2readDownloadThread(
                base_url="https://hentai2read.com",
                manga_slug=id1,
                chapter_num=id2,
                output_dir=effective_output_dir_for_run,
                pause_event=self.pause_event,
                parent=self
            )    

            self.download_thread.progress_signal.connect(self.handle_main_log)
            self.download_thread.file_progress_signal.connect(self.update_file_progress_display)
            self.download_thread.overall_progress_signal.connect(self.update_progress_display) 
            self.download_thread.finished_signal.connect(
                lambda dl, skip, cancelled: self.download_finished(dl, skip, cancelled, [])
            )
            self.download_thread.start()
            self._update_button_states_and_connections()
            return True


        if service == 'nhentai':
            gallery_id = id1
            self.log_signal.emit("=" * 40)
            self.log_signal.emit(f"🚀 Detected nhentai gallery ID: {gallery_id}")

            if not effective_output_dir_for_run or not os.path.isdir(effective_output_dir_for_run):
                QMessageBox.critical(self, "Input Error", "A valid Download Location is required.")
                return False

            gallery_data = fetch_nhentai_gallery(gallery_id, self.log_signal.emit)
            if not gallery_data:
                QMessageBox.critical(self, "Error", f"Could not retrieve gallery data for ID {gallery_id}.")
                return False

            self.set_ui_enabled(False)
            self.download_thread = NhentaiDownloadThread(gallery_data, effective_output_dir_for_run, self)
            self.download_thread.progress_signal.connect(self.handle_main_log)
            self.download_thread.finished_signal.connect(
                lambda dl, skip, cancelled: self.download_finished(dl, skip, cancelled, [])
            )
            self.download_thread.start()
            self._update_button_states_and_connections()
            return True

        if service == 'bunkr':
            self.log_signal.emit("ℹ️ Bunkr URL detected. Starting dedicated Bunkr download.")
            self.set_ui_enabled(False)
            
            self.download_thread = BunkrDownloadThread(id1, effective_output_dir_for_run, self)
            self.download_thread.progress_signal.connect(self.handle_main_log)
            self.download_thread.file_progress_signal.connect(self.update_file_progress_display)
            self.download_thread.finished_signal.connect(
                lambda dl, skip, cancelled: self.download_finished(dl, skip, cancelled, [])
            )
            self.download_thread.start()
            self._update_button_states_and_connections()
            return True

        if not service or not id1:
            QMessageBox.critical(self, "Input Error", "Invalid or unsupported URL format.")
            return False

        if service == 'discord':
            server_id, channel_id = id1, id2
            
            def discord_processing_task():
                try:
                    def queue_logger(message):
                        self.worker_to_gui_queue.put({'type': 'progress', 'payload': (message,)})
                    
                    def queue_progress_label_update(message):
                        self.worker_to_gui_queue.put({'type': 'set_progress_label', 'payload': (message,)})

                    cookies = prepare_cookies_for_request(
                        self.use_cookie_checkbox.isChecked(), self.cookie_text_input.text(),
                        self.selected_cookie_filepath, self.app_base_dir, queue_logger
                    )
                    
                    if self.discord_download_scope == 'messages':
                        queue_logger("=" * 40)
                        queue_logger(f"🚀 Starting Discord PDF export for: {api_url}")
                        
                        output_dir = self.dir_input.text().strip()
                        if not output_dir or not os.path.isdir(output_dir):
                            queue_logger("❌ PDF Save Error: No valid download directory selected in the UI.")
                            self.worker_to_gui_queue.put({'type': 'set_ui_enabled', 'payload': (True,)})
                            return

                        default_filename = f"discord_{server_id}_{channel_id or 'server'}.pdf"
                        output_filepath = os.path.join(output_dir, default_filename)
                        
                        all_messages, channels_to_process = [], []
                        server_name_for_pdf = server_id
                        
                        if channel_id:
                            channels_to_process.append({'id': channel_id, 'name': channel_id})
                        else:
                            channels = fetch_server_channels(server_id, queue_logger, cookies)
                            if channels:
                                channels_to_process = channels

                        for i, channel in enumerate(channels_to_process):
                            queue_progress_label_update(f"Fetching from channel {i+1}/{len(channels_to_process)}: #{channel.get('name', '')}")
                            message_generator = fetch_channel_messages(channel['id'], queue_logger, self.cancellation_event, self.pause_event, cookies)
                            for message_batch in message_generator:
                                all_messages.extend(message_batch)
                        
                        queue_progress_label_update(f"Collected {len(all_messages)} total messages. Generating PDF...")
                        
                        if getattr(sys, 'frozen', False):
                            base_path = sys._MEIPASS
                        else:
                            base_path = self.app_base_dir
                        font_path = os.path.join(base_path, 'data', 'dejavu-sans', 'DejaVuSans.ttf')

                        success = create_pdf_from_discord_messages(
                            all_messages, server_name_for_pdf,
                            channels_to_process[0].get('name', channel_id) if len(channels_to_process) == 1 else "All Channels",
                            output_filepath, font_path, logger=queue_logger
                        )
                        
                        if success:
                            queue_progress_label_update("✅ PDF export complete!")
                        else:
                            queue_progress_label_update("❌ PDF export failed.")
                        self.finished_signal.emit(0, len(all_messages), self.cancellation_event.is_set(), [])
                        return

                    elif self.discord_download_scope == 'files':
                        worker_args = {
                            'download_root': effective_output_dir_for_run, 'known_names': list(KNOWN_NAMES),
                            'filter_character_list': self._parse_character_filters(self.character_input.text().strip()),
                            'emitter': self.worker_to_gui_queue, 'unwanted_keywords': FOLDER_NAME_STOP_WORDS,
                            'filter_mode': self.get_filter_mode(), 'skip_zip': self.skip_zip_checkbox.isChecked(),
                            'use_subfolders': self.use_subfolders_checkbox.isChecked(), 'use_post_subfolders': self.use_subfolder_per_post_checkbox.isChecked(),
                            'target_post_id_from_initial_url': None, 'custom_folder_name': None,
                            'compress_images': self.compress_images_checkbox.isChecked(), 'download_thumbnails': self.download_thumbnails_checkbox.isChecked(),
                            'service': service, 'user_id': server_id, 'api_url_input': api_url,
                            'pause_event': self.pause_event, 'cancellation_event': self.cancellation_event,
                            'downloaded_files': self.downloaded_files, 'downloaded_file_hashes': self.downloaded_file_hashes,
                            'downloaded_files_lock': self.downloaded_files_lock, 'downloaded_file_hashes_lock': self.downloaded_file_hashes_lock,
                            'skip_words_list': [part.strip().lower() for part in self.skip_words_input.text().strip().split(',') if part.strip() and not part.strip().startswith('[')],
                            'skip_file_size_mb': next((int(re.search(r'\[(\d+)\]', part).group(1)) for part in self.skip_words_input.text().strip().split(',') if re.fullmatch(r'\[\d+\]', part.strip())), None),
                            'skip_words_scope': self.get_skip_words_scope(), 'char_filter_scope': self.get_char_filter_scope(),
                            'remove_from_filename_words_list': [word.strip() for word in self.remove_from_filename_input.text().strip().split(',') if word.strip()],
                            'scan_content_for_images': self.scan_content_images_checkbox.isChecked(),
                            'manga_mode_active': False,
                        }
                        total_dl, total_skip = 0, 0
                        
                        def process_channel_files(channel_id_to_process, output_directory):
                            nonlocal total_dl, total_skip
                            message_generator = fetch_channel_messages(channel_id_to_process, queue_logger, self.cancellation_event, self.pause_event, cookies)
                            for message_batch in message_generator:
                                if self.cancellation_event.is_set():
                                    break
                                for message in message_batch:
                                    if self.cancellation_event.is_set():
                                        break
                                    if not message.get('attachments'):
                                        continue

                                    worker_instance_args = worker_args.copy()
                                    worker_instance_args.update({'post_data': message, 'download_root': output_directory, 'override_output_dir': output_directory})
                                    worker = PostProcessorWorker(**worker_instance_args)
                                    dl_count, skip_count, _, _, _, _, _ = worker.process()
                                    total_dl += dl_count
                                    total_skip += skip_count
                        
                        if channel_id:
                            process_channel_files(channel_id, effective_output_dir_for_run)
                        else:
                            channels = fetch_server_channels(server_id, queue_logger, cookies)
                            if channels:
                                for i, channel in enumerate(channels):
                                    if self.cancellation_event.is_set():
                                        break
                                    chan_id = channel.get('id')
                                    chan_name = channel.get('name', f"channel_{chan_id}")
                                    queue_logger("=" * 40)
                                    queue_logger(f"Processing Channel {i+1}/{len(channels)}: '{chan_name}'")
                                    channel_dir = os.path.join(effective_output_dir_for_run, clean_folder_name(chan_name))
                                    os.makedirs(channel_dir, exist_ok=True)
                                    process_channel_files(chan_id, channel_dir)
                        
                        self.finished_signal.emit(total_dl, total_skip, self.cancellation_event.is_set(), [])
                finally:
                    self.is_fetcher_thread_running = False

            self.is_fetcher_thread_running = True
            
            self.set_ui_enabled(False)
            self.download_thread = threading.Thread(target=discord_processing_task, daemon=True)
            self.download_thread.start()
            self._update_button_states_and_connections()
            return True

        user_id, post_id_from_url = id1, id2
        
        if direct_api_url and not post_id_from_url and item_type_from_queue and 'post' in item_type_from_queue:
            self.log_signal.emit(f"❌ CRITICAL ERROR: Could not parse post ID from the queued POST URL: {api_url}")
            self.log_signal.emit("   Skipping this item. This might be due to an unsupported URL format or a temporary issue.")
            self.download_finished(
                total_downloaded=0, 
                total_skipped=1, 
                cancelled_by_user=False, 
                kept_original_names_list=[]
            )
            return False

        self.save_creator_json_enabled_this_session = self.settings.value(SAVE_CREATOR_JSON_KEY, True, type=bool)
        self.is_single_post_session = bool(post_id_from_url) 

        if not self.is_single_post_session:
            self.save_creator_json_enabled_this_session = self.settings.value(SAVE_CREATOR_JSON_KEY, True, type=bool)

            creator_profile_data = {}
            if self.save_creator_json_enabled_this_session:
                creator_name_for_profile = None
                if self.is_processing_favorites_queue and self.current_processing_favorite_item_info:
                    creator_name_for_profile = self.current_processing_favorite_item_info.get('name_for_folder')
                else:
                    creator_key = (service.lower(), str(user_id))
                    creator_name_for_profile = self.creator_name_cache.get(creator_key)

                if not creator_name_for_profile:
                    creator_name_for_profile = f"{service}_{user_id}"
                    self.log_signal.emit(f"⚠️ Creator name not in cache. Using '{creator_name_for_profile}' for profile file.")

                creator_profile_data = self._setup_creator_profile(creator_name_for_profile, self.session_file_path)
            
                current_settings = self._get_current_ui_settings_as_dict(api_url_override=api_url, output_dir_override=effective_output_dir_for_run)
                creator_profile_data['settings'] = current_settings
            
                creator_profile_data.setdefault('creator_url', [])
                if api_url not in creator_profile_data['creator_url']:
                    creator_profile_data['creator_url'].append(api_url)

                if self.active_update_profile:
                    self.log_signal.emit("   Update session active: Loading existing processed post IDs to find new content.")
                    profile_processed_ids = set(creator_profile_data.get('processed_post_ids', []))
                
                elif not is_restore:
                    self.log_signal.emit("   Fresh download session: Clearing previous post history for this creator to re-download all.")
                    if 'processed_post_ids' in creator_profile_data:
                        creator_profile_data['processed_post_ids'] = []

                creator_profile_data.setdefault('processed_post_ids', [])
                self._save_creator_profile(creator_name_for_profile, creator_profile_data, self.session_file_path)
                self.log_signal.emit(f"✅ Profile for '{creator_name_for_profile}' loaded/created. Settings saved.")
        
        profile_processed_ids = set()

        session_processed_ids = set(processed_post_ids_for_restore)
        combined_processed_ids = session_processed_ids.union(profile_processed_ids)
        processed_post_ids_for_this_run = list(combined_processed_ids)

        use_subfolders = self.use_subfolders_checkbox.isChecked()
        use_post_subfolders = self.use_subfolder_per_post_checkbox.isChecked()
        compress_images = self.compress_images_checkbox.isChecked()
        download_thumbnails = self.download_thumbnails_checkbox.isChecked()

        use_multithreading_enabled_by_checkbox = self.use_multithreading_checkbox.isChecked()
        try:
            num_threads_from_gui = int(self.thread_count_input.text().strip())
            if num_threads_from_gui < 1: num_threads_from_gui = 1
        except ValueError:
            QMessageBox.critical(self, "Thread Count Error", "Invalid number of threads. Please enter a positive number.")
            return False

        if use_multithreading_enabled_by_checkbox:
            if num_threads_from_gui > MAX_THREADS:
                hard_warning_msg = (
                    f"You've entered a thread count ({num_threads_from_gui}) exceeding the maximum of {MAX_THREADS}.\n\n"
                    "Using an extremely high number of threads can lead to:\n"
                    "  - Diminishing returns (no significant speed increase).\n"
                    "  - Increased system instability or application crashes.\n"
                    "  - Higher chance of being rate-limited or temporarily IP-banned by the server.\n\n"
                    f"The thread count has been automatically capped to {MAX_THREADS} for stability."
                )
                QMessageBox.warning(self, "High Thread Count Warning", hard_warning_msg)
                num_threads_from_gui = MAX_THREADS
                self.thread_count_input.setText(str(MAX_THREADS))
                self.log_signal.emit(f"⚠️ User attempted {num_threads_from_gui} threads, capped to {MAX_THREADS}.")
            if SOFT_WARNING_THREAD_THRESHOLD < num_threads_from_gui <= MAX_THREADS:
                soft_warning_msg_box = QMessageBox(self)
                soft_warning_msg_box.setIcon(QMessageBox.Question)
                soft_warning_msg_box.setWindowTitle("Thread Count Advisory")
                soft_warning_msg_box.setText(
                    f"You've set the thread count to {num_threads_from_gui}.\n\n"
                    "While this is within the allowed limit, using a high number of threads (typically above 40-50) can sometimes lead to:\n"
                    "  - Increased errors or failed file downloads.\n"
                    "  - Connection issues with the server.\n"
                    "  - Higher system resource usage.\n\n"
                    "For most users and connections, 10-30 threads provide a good balance.\n\n"
                    f"Do you want to proceed with {num_threads_from_gui} threads, or would you like to change the value?"
                )
                proceed_button = soft_warning_msg_box.addButton("Proceed Anyway", QMessageBox.AcceptRole)
                change_button = soft_warning_msg_box.addButton("Change Thread Value", QMessageBox.RejectRole)
                soft_warning_msg_box.setDefaultButton(proceed_button)
                soft_warning_msg_box.setEscapeButton(change_button)
                soft_warning_msg_box.exec_()

                if soft_warning_msg_box.clickedButton() == change_button:
                    self.log_signal.emit(f"ℹ️ User opted to change thread count from {num_threads_from_gui} after advisory.")
                    self.thread_count_input.setFocus()
                    self.thread_count_input.selectAll()
                    return False

        raw_skip_words_text = self.skip_words_input.text().strip()
        skip_words_parts = [part.strip() for part in raw_skip_words_text.split(',') if part.strip()]
        skip_words_list = []
        skip_file_size_mb = None
        size_pattern = re.compile(r'\[(\d+)\]')

        for part in skip_words_parts:
            match = size_pattern.fullmatch(part)
            if match:
                skip_file_size_mb = int(match.group(1))
                self.log_signal.emit(f"ℹ️ File size skip rule found: Will skip files smaller than {skip_file_size_mb} MB.")
            else:
                skip_words_list.append(part.lower())

        raw_remove_filename_words = self.remove_from_filename_input.text().strip() if hasattr(self, 'remove_from_filename_input') else ""
        allow_multipart = self.allow_multipart_download_setting
        remove_from_filename_words_list = [word.strip() for word in raw_remove_filename_words.split(',') if word.strip()]
        scan_content_for_images = self.scan_content_images_checkbox.isChecked() if hasattr(self, 'scan_content_images_checkbox') else False
        use_cookie_from_checkbox = self.use_cookie_checkbox.isChecked() if hasattr(self, 'use_cookie_checkbox') else False
        app_base_dir_for_cookies = os.path.dirname(self.config_file)
        cookie_text_from_input = self.cookie_text_input.text().strip() if hasattr(self, 'cookie_text_input') and use_cookie_from_checkbox else ""

        use_cookie_for_this_run = use_cookie_from_checkbox
        selected_cookie_file_path_for_backend = self.selected_cookie_filepath if use_cookie_from_checkbox and self.selected_cookie_filepath else None

        if use_cookie_from_checkbox and not direct_api_url:
            temp_cookies_for_check = prepare_cookies_for_request(
                use_cookie_for_this_run,
                cookie_text_from_input,
                selected_cookie_file_path_for_backend,
                app_base_dir_for_cookies,
                lambda msg: self.log_signal.emit(f"[UI Cookie Check] {msg}")
            )
            if temp_cookies_for_check is None:
                cookie_dialog = CookieHelpDialog(self, offer_download_without_option=True)
                dialog_exec_result = cookie_dialog.exec_()

                if cookie_dialog.user_choice == CookieHelpDialog.CHOICE_PROCEED_WITHOUT_COOKIES and dialog_exec_result == QDialog.Accepted:
                    self.log_signal.emit("ℹ️ User chose to download without cookies for this session.")
                    use_cookie_for_this_run = False
                elif cookie_dialog.user_choice == CookieHelpDialog.CHOICE_CANCEL_DOWNLOAD or dialog_exec_result == QDialog.Rejected:
                    self.log_signal.emit("❌ Download cancelled by user at cookie prompt.")
                    return False
                else:
                    self.log_signal.emit("⚠️ Cookie dialog closed or unexpected choice. Aborting download.")
                    return False

        current_skip_words_scope = self.get_skip_words_scope()
        manga_mode_is_checked = self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False

        backend_filter_mode = self.get_filter_mode()
        text_only_scope_for_run = self.more_filter_scope if backend_filter_mode == 'text_only' else None
        export_format_for_run = self.text_export_format if backend_filter_mode == 'text_only' else 'txt'
        checked_radio_button = self.radio_group.checkedButton()
        user_selected_filter_text = checked_radio_button.text() if checked_radio_button else "All"

        if selected_cookie_file_path_for_backend:
            cookie_text_from_input = ""

        if backend_filter_mode == 'archive':
            effective_skip_zip = False
        else:
            effective_skip_zip = self.skip_zip_checkbox.isChecked()
            if backend_filter_mode == 'audio':
                effective_skip_zip = self.skip_zip_checkbox.isChecked()

        creator_folder_ignore_words_for_run = None
        is_full_creator_download = not post_id_from_url

        if compress_images and Image is None:
            QMessageBox.warning(self, "Missing Dependency", "Pillow library (for image compression) not found. Compression will be disabled.")
            compress_images = False;
            self.compress_images_checkbox.setChecked(False)

        fetch_first_enabled = self.settings.value(FETCH_FIRST_KEY, False, type=bool)

        log_messages = ["=" * 40, f"🚀 Starting {'Link Extraction' if extract_links_only else ('Archive Download' if backend_filter_mode == 'archive' else 'Download')} @ {time.strftime('%Y-%m-%d %H:%M:%S')}", f"    URL: {api_url}"]

        current_mode_log_text = "Download"
        if extract_links_only: current_mode_log_text = "Link Extraction"
        elif backend_filter_mode == 'archive': current_mode_log_text = "Archive Download"
        elif backend_filter_mode == 'audio': current_mode_log_text = "Audio Download"

        current_char_filter_scope = self.get_char_filter_scope()
        manga_mode = manga_mode_is_checked

        manga_date_prefix_text = ""
        if manga_mode and (self.manga_filename_style == STYLE_DATE_BASED or self.manga_filename_style == STYLE_ORIGINAL_NAME) and hasattr(self, 'manga_date_prefix_input'):
            manga_date_prefix_text = self.manga_date_prefix_input.text().strip()
            if manga_date_prefix_text:
                log_messages.append(f"      ↳ Manga Date Prefix: '{manga_date_prefix_text}'")

        start_page_str, end_page_str = self.start_page_input.text().strip(), self.end_page_input.text().strip()
        start_page, end_page = None, None
        is_creator_feed = bool(not post_id_from_url)

        if is_creator_feed:
            try:
                if start_page_str: start_page = int(start_page_str)
                if end_page_str: end_page = int(end_page_str)

                if start_page is not None and start_page <= 0: raise ValueError("Start page must be positive.")
                if end_page is not None and end_page <= 0: raise ValueError("End page must be positive.")
                if start_page and end_page and start_page > end_page: raise ValueError("Start page cannot be greater than end page.")

                if manga_mode and start_page and end_page:
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Warning)
                    msg_box.setWindowTitle("Renaming Mode & Page Range Warning")
                    msg_box.setText(
                    "You have enabled <b>Renaming Mode</b> with a sequential naming style (<b>Date Based</b> or <b>Title + G.Num</b>) and also specified a <b>Page Range</b>.\n\n"
                    "These modes rely on processing all posts from the beginning to create a correct sequence. "
                    "Using a page range may result in an incomplete or incorrectly ordered download.\n\n"
                    "It is recommended to use these styles without a page range.\n\n"
                    "Do you want to proceed anyway?"
                    )
                    proceed_button = msg_box.addButton("Proceed Anyway", QMessageBox.AcceptRole)
                    cancel_button = msg_box.addButton("Cancel Download", QMessageBox.RejectRole)
                    msg_box.setDefaultButton(proceed_button)
                    msg_box.setEscapeButton(cancel_button)
                    msg_box.exec_()

                    if msg_box.clickedButton() == cancel_button:
                        self.log_signal.emit("❌ Download cancelled by user due to Renaming Mode & Page Range warning.")
                        return False
            except ValueError as e:
                QMessageBox.critical(self, "Page Range Error", f"Invalid page range: {e}")
                return False
        self.external_link_queue.clear();
        self.extracted_links_cache = [];
        self._is_processing_external_link_queue = False;
        self._current_link_post_title = None

        raw_character_filters_text = self.character_input.text().strip()
        parsed_character_filter_objects, download_commands = self._parse_character_filters(raw_character_filters_text)

        domain_override_command = download_commands.get('domain_override')

        actual_filters_to_use_for_run = []

        needs_folder_naming_validation = (use_subfolders or manga_mode) and not extract_links_only

        if parsed_character_filter_objects:
            actual_filters_to_use_for_run = parsed_character_filter_objects

            if not extract_links_only:
                self.log_signal.emit(f"ℹ️ Using character filters for matching: {', '.join(item['name'] for item in actual_filters_to_use_for_run)}")

                filter_objects_to_potentially_add_to_known_list = []
                for filter_item_obj in parsed_character_filter_objects:
                    item_primary_name = filter_item_obj["name"]
                    cleaned_name_test = clean_folder_name(item_primary_name)
                    if needs_folder_naming_validation and not cleaned_name_test:
                        QMessageBox.warning(self, "Invalid Filter Name for Folder", f"Filter name '{item_primary_name}' is invalid for a folder and will be skipped for Known.txt interaction.")
                        self.log_signal.emit(f"⚠️ Skipping invalid filter for Known.txt interaction: '{item_primary_name}'")
                        continue

                    an_alias_is_already_known = False
                    if any(kn_entry["name"].lower() == item_primary_name.lower() for kn_entry in KNOWN_NAMES):
                        an_alias_is_already_known = True
                    elif filter_item_obj["is_group"] and needs_folder_naming_validation:
                        for alias_in_filter_obj in filter_item_obj["aliases"]:
                            if any(kn_entry["name"].lower() == alias_in_filter_obj.lower() or alias_in_filter_obj.lower() in [a.lower() for a in kn_entry["aliases"]] for kn_entry in KNOWN_NAMES):
                                an_alias_is_already_known = True;
                                break

                    if an_alias_is_already_known and filter_item_obj["is_group"]:
                        self.log_signal.emit(f"ℹ️ An alias from group '{item_primary_name}' is already known. Group will not be prompted for Known.txt addition.")

                    should_prompt_to_add_to_known_list = (
                            needs_folder_naming_validation and not manga_mode and
                            not any(kn_entry["name"].lower() == item_primary_name.lower() for kn_entry in KNOWN_NAMES) and
                            not an_alias_is_already_known
                    )
                    if should_prompt_to_add_to_known_list:
                        if not any(obj_to_add["name"].lower() == item_primary_name.lower() for obj_to_add in filter_objects_to_potentially_add_to_known_list):
                            filter_objects_to_potentially_add_to_known_list.append(filter_item_obj)
                    elif manga_mode and needs_folder_naming_validation and item_primary_name.lower() not in {kn_entry["name"].lower() for kn_entry in KNOWN_NAMES} and not an_alias_is_already_known:
                        self.log_signal.emit(f"ℹ️ Renaming Mode: Using filter '{item_primary_name}' for this session without adding to Known Names.")

                if filter_objects_to_potentially_add_to_known_list:
                    confirm_dialog = ConfirmAddAllDialog(filter_objects_to_potentially_add_to_known_list, self, self)
                    dialog_result = confirm_dialog.exec_()

                    if dialog_result == CONFIRM_ADD_ALL_CANCEL_DOWNLOAD:
                        self.log_signal.emit("❌ Download cancelled by user at new name confirmation stage.")
                        return False
                    elif isinstance(dialog_result, list):
                        if dialog_result:
                            self.log_signal.emit(f"ℹ️ User chose to add {len(dialog_result)} new entry/entries to Known.txt.")
                            for filter_obj_to_add in dialog_result:
                                if filter_obj_to_add.get("components_are_distinct_for_known_txt"):
                                    self.log_signal.emit(f"    Processing group '{filter_obj_to_add['name']}' to add its components individually to Known.txt.")
                                    for alias_component in filter_obj_to_add["aliases"]:
                                        self.add_new_character(
                                            name_to_add=alias_component,
                                            is_group_to_add=False,
                                            aliases_to_add=[alias_component],
                                            suppress_similarity_prompt=True
                                        )
                                else:
                                    self.add_new_character(
                                        name_to_add=filter_obj_to_add["name"],
                                        is_group_to_add=filter_obj_to_add["is_group"],
                                        aliases_to_add=filter_obj_to_add["aliases"],
                                        suppress_similarity_prompt=True
                                    )
                        else:
                            self.log_signal.emit("ℹ️ User confirmed adding, but no names were selected in the dialog. No new names added to Known.txt.")
                    elif dialog_result == CONFIRM_ADD_ALL_SKIP_ADDING:
                        self.log_signal.emit("ℹ️ User chose not to add new names to Known.txt for this session.")
            else:
                self.log_signal.emit(f"ℹ️ Using character filters for link extraction: {', '.join(item['name'] for item in actual_filters_to_use_for_run)}")

        self.dynamic_character_filter_holder.set_filters(actual_filters_to_use_for_run)

        creator_folder_ignore_words_for_run = None
        character_filters_are_empty = not actual_filters_to_use_for_run
        if is_full_creator_download and character_filters_are_empty:
            creator_folder_ignore_words_for_run = CREATOR_DOWNLOAD_DEFAULT_FOLDER_IGNORE_WORDS
            log_messages.append(f"    Creator Download (No Char Filter): Applying default folder name ignore list ({len(creator_folder_ignore_words_for_run)} words).")

        custom_folder_name_cleaned = None
        if use_subfolders and post_id_from_url and self.custom_folder_widget and self.custom_folder_widget.isVisible() and not extract_links_only:
            raw_custom_name = self.custom_folder_input.text().strip()
            if raw_custom_name:
                cleaned_custom = clean_folder_name(raw_custom_name)
                if cleaned_custom:
                    custom_folder_name_cleaned = cleaned_custom
                else:
                    self.log_signal.emit(f"⚠️ Invalid custom folder name ignored: '{raw_custom_name}' (resulted in empty string after cleaning).")

        self.main_log_output.clear()
        if extract_links_only: self.main_log_output.append("🔗 Extracting Links...");
        elif backend_filter_mode == 'archive': self.main_log_output.append("📦 Downloading Archives Only...")

        if self.external_log_output: self.external_log_output.clear()
        if self.show_external_links and not extract_links_only and backend_filter_mode != 'archive':
            self.external_log_output.append("🔗 External Links Found:")

        self.file_progress_label.setText("");
        self.cancellation_event.clear();
        self.active_futures = []
        self.total_posts_to_process = 0;
        self.processed_posts_count = 0;
        self.download_counter = 0;
        self.skip_counter = 0
        self.progress_label.setText(self._tr("progress_initializing_text", "Progress: Initializing..."))

        self.retryable_failed_files_info.clear()
        self._update_error_button_count()

        manga_date_file_counter_ref_for_thread = None
        if manga_mode and self.manga_filename_style == STYLE_DATE_BASED and not extract_links_only:
            start_val = 1
            if is_restore and manga_counters_for_restore:
                start_val = manga_counters_for_restore.get('date_based', 1)
            self.log_signal.emit(f"ℹ️ Manga Date Mode: Initializing shared file counter starting at {start_val}.")
            manga_date_file_counter_ref_for_thread = [start_val, threading.Lock()]

        manga_global_file_counter_ref_for_thread = None
        if manga_mode and self.manga_filename_style == STYLE_POST_TITLE_GLOBAL_NUMBERING and not extract_links_only:
            start_val = 1
            if is_restore and manga_counters_for_restore:
                start_val = manga_counters_for_restore.get('global_numbering', 1)
            self.log_signal.emit(f"ℹ️ Manga Title+GlobalNum Mode: Initializing shared file counter starting at {start_val}.")
            manga_global_file_counter_ref_for_thread = [start_val, threading.Lock()]

        effective_num_post_workers = 1
        effective_num_file_threads_per_worker = 1

        if post_id_from_url:
            if use_multithreading_enabled_by_checkbox:
                effective_num_file_threads_per_worker = max(1, min(num_threads_from_gui, MAX_FILE_THREADS_PER_POST_OR_WORKER))
        else:
            if manga_mode and self.manga_filename_style == STYLE_DATE_BASED:
                effective_num_post_workers = 1
            elif manga_mode and self.manga_filename_style == STYLE_POST_TITLE_GLOBAL_NUMBERING:
                effective_num_post_workers = 1
                effective_num_file_threads_per_worker = 1
            elif use_multithreading_enabled_by_checkbox:
                effective_num_post_workers = max(1, min(num_threads_from_gui, MAX_THREADS))
                effective_num_file_threads_per_worker = 1

        if not extract_links_only: log_messages.append(f"    Save Location: {effective_output_dir_for_run}")

        if post_id_from_url:
            log_messages.append(f"    Mode: Single Post")
            log_messages.append(f"      ↳ File Downloads: Up to {effective_num_file_threads_per_worker} concurrent file(s)")
        else:
            log_messages.append(f"    Mode: Creator Feed")
            log_messages.append(f"    Post Processing: {'Multi-threaded (' + str(effective_num_post_workers) + ' workers)' if effective_num_post_workers > 1 else 'Single-threaded (1 worker)'}")
            pr_log = "All"
            if start_page or end_page:
                pr_log = f"{f'From {start_page} ' if start_page else ''}{'to ' if start_page and end_page else ''}{f'{end_page}' if end_page else (f'Up to {end_page}' if end_page else (f'From {start_page}' if start_page else 'Specific Range'))}".strip()

            if manga_mode:
                log_messages.append(f"    Page Range: {pr_log if pr_log else 'All'} (Renaming Mode - Oldest Posts Processed First within range)")
            else:
                log_messages.append(f"    Page Range: {pr_log if pr_log else 'All'}")

        if not extract_links_only:
            log_messages.append(f"    Subfolders: {'Enabled' if use_subfolders else 'Disabled'}")
            if use_subfolders and self.use_subfolder_per_post_checkbox.isChecked():
                use_date_prefix = self.date_prefix_checkbox.isChecked() if hasattr(self, 'date_prefix_checkbox') else False
                log_messages.append(f"      ↳ Date Prefix for Post Subfolders: {'Enabled' if use_date_prefix else 'Disabled'}")
            if use_subfolders:
                if custom_folder_name_cleaned: log_messages.append(f"    Custom Folder (Post): '{custom_folder_name_cleaned}'")
            if actual_filters_to_use_for_run:
                log_messages.append(f"    Character Filters: {', '.join(item['name'] for item in actual_filters_to_use_for_run)}")
                log_messages.append(f"      ↳ Char Filter Scope: {current_char_filter_scope.capitalize()}")
            elif use_subfolders:
                log_messages.append(f"    Folder Naming: Automatic (based on title/known names)")

            keep_duplicates = self.keep_duplicates_checkbox.isChecked() if hasattr(self, 'keep_duplicates_checkbox') else False
            log_messages.extend([
                f"    File Type Filter: {user_selected_filter_text} (Backend processing as: {backend_filter_mode})",
                f"    Keep In-Post Duplicates: {'Enabled' if keep_duplicates else 'Disabled'}",
                f"    Skip Archives: {'.zip' if effective_skip_zip else ''}{', ' if effective_skip_zip else ''}{'None (Archive Mode)' if backend_filter_mode == 'archive' else ('None' if not (effective_skip_zip ) else '')}",
                f"    Skip Words Scope: {current_skip_words_scope.capitalize()}",
                f"    Remove Words from Filename: {', '.join(remove_from_filename_words_list) if remove_from_filename_words_list else 'None'}",
                f"    Compress Images: {'Enabled' if compress_images else 'Disabled'}",
                f"    Thumbnails Only: {'Enabled' if download_thumbnails else 'Disabled'}"
            ])
            log_messages.append(f"    Scan Post Content for Images: {'Enabled' if scan_content_for_images else 'Disabled'}")
        else:
            log_messages.append(f"    Mode: Extracting Links Only")

        log_messages.append(f"    Show External Links: {'Enabled' if self.show_external_links and not extract_links_only and backend_filter_mode != 'archive' else 'Disabled'}")

        if manga_mode:
            log_messages.append(f"    Renaming Mode: Enabled")
            
            # Create a mapping for user-friendly style names
            style_display_names = {
                STYLE_POST_TITLE: "Post Title",
                STYLE_ORIGINAL_NAME: "Date + Original",
                STYLE_DATE_POST_TITLE: "Date + Title",
                STYLE_POST_TITLE_GLOBAL_NUMBERING: "Title + Global Numbering",
                STYLE_DATE_BASED: "Date Based",
                STYLE_POST_ID: "Post ID",
                STYLE_CUSTOM: f"Custom ({self.custom_manga_filename_format})"
            }
            style_text = style_display_names.get(self.manga_filename_style, "Unknown")
            log_messages.append(f"      ↳ Filename Style: {style_text}")

            if actual_filters_to_use_for_run:
                log_messages.append(f"      ↳ Character Filter (for naming/folder): {', '.join(item['name'] for item in actual_filters_to_use_for_run)}")
            
            log_messages.append(f"      ↳ Filename Collisions: Will be handled with a numeric suffix (e.g., _1, _2).")

        log_messages.append(f"    Use Cookie ('cookies.txt'): {'Enabled' if use_cookie_from_checkbox else 'Disabled'}")
        if use_cookie_from_checkbox and cookie_text_from_input:
            log_messages.append(f"      ↳ Cookie Text Provided: Yes (length: {len(cookie_text_from_input)})")
        elif use_cookie_from_checkbox and selected_cookie_file_path_for_backend:
            log_messages.append(f"      ↳ Cookie File Selected: {os.path.basename(selected_cookie_file_path_for_backend)}")
        should_use_multithreading_for_posts = use_multithreading_enabled_by_checkbox and not post_id_from_url
        if manga_mode and (self.manga_filename_style == STYLE_DATE_BASED or self.manga_filename_style == STYLE_POST_TITLE_GLOBAL_NUMBERING) and not post_id_from_url:
            enforced_by_style = "Date Mode" if self.manga_filename_style == STYLE_DATE_BASED else "Title+GlobalNum Mode"
            should_use_multithreading_for_posts = False
            log_messages.append(f"    Threading: Single-threaded (posts) - Enforced by Manga {enforced_by_style} (Actual workers: {effective_num_post_workers if effective_num_post_workers > 1 else 1})")
        else:
            log_messages.append(f"    Threading: {'Multi-threaded (posts)' if should_use_multithreading_for_posts else 'Single-threaded (posts)'}")
        if should_use_multithreading_for_posts:
            log_messages.append(f"    Number of Post Worker Threads: {effective_num_post_workers}")
     
        if domain_override_command:
            self.log_signal.emit(f"ℹ️ Domain Override Active: Will probe for the correct 'n*' subdomain on the '.{domain_override_command}' domain for each file.")

        if domain_override_command:
            self.log_signal.emit(f"ℹ️ Domain override command found: Forcing download URLs to use '.{domain_override_command}'")
     
        log_messages.append("=" * 40)
        for msg in log_messages: self.log_signal.emit(msg)

        self.set_ui_enabled(False)

        from src.config.constants import FOLDER_NAME_STOP_WORDS

        args_template = {
            'api_url_input': api_url,
            'download_root': effective_output_dir_for_run,
            'output_dir': effective_output_dir_for_run,
            'known_names': list(KNOWN_NAMES),
            'known_names_copy': list(KNOWN_NAMES),
            'filter_character_list': actual_filters_to_use_for_run,
            'archive_only_mode': download_commands.get('archive_only', False), 
            'domain_override': domain_override_command, 
            'filter_mode': backend_filter_mode,
            'text_only_scope': text_only_scope_for_run,
            'text_export_format': export_format_for_run,
            'single_pdf_mode': self.single_pdf_setting,
            'skip_zip': effective_skip_zip,
            'use_subfolders': use_subfolders,
            'use_post_subfolders': use_post_subfolders,
            'compress_images': compress_images,
            'download_thumbnails': download_thumbnails,
            'service': service,
            'user_id': user_id,
            'downloaded_files': self.downloaded_files,
            'downloaded_files_lock': self.downloaded_files_lock,
            'downloaded_file_hashes': self.downloaded_file_hashes,
            'downloaded_file_hashes_lock': self.downloaded_file_hashes_lock,
            'skip_words_list': skip_words_list,
            'skip_file_size_mb': skip_file_size_mb,
            'skip_words_scope': current_skip_words_scope,
            'remove_from_filename_words_list': remove_from_filename_words_list,
            'char_filter_scope': current_char_filter_scope,
            'show_external_links': self.show_external_links,
            'extract_links_only': extract_links_only,
            'start_page': start_page,
            'end_page': end_page,
            'target_post_id_from_initial_url': post_id_from_url,
            'custom_folder_name': custom_folder_name_cleaned,
            'manga_mode_active': manga_mode,
            'unwanted_keywords': FOLDER_NAME_STOP_WORDS,
            'cancellation_event': self.cancellation_event,
            'manga_date_prefix': manga_date_prefix_text,
            'dynamic_character_filter_holder': self.dynamic_character_filter_holder,
            'pause_event': self.pause_event,
            'scan_content_for_images': scan_content_for_images,
            'manga_filename_style': self.manga_filename_style,
            'num_file_threads_for_worker': effective_num_file_threads_per_worker,
            'manga_date_file_counter_ref': manga_date_file_counter_ref_for_thread,
            'allow_multipart_download': allow_multipart,
            'multipart_scope': self.multipart_scope,
            'multipart_parts_count': self.multipart_parts_count,
            'multipart_min_size_mb': self.multipart_min_size_mb,
            'cookie_text': cookie_text_from_input,
            'selected_cookie_file': selected_cookie_file_path_for_backend,
            'manga_global_file_counter_ref': manga_global_file_counter_ref_for_thread,
            'app_base_dir': app_base_dir_for_cookies,
            'project_root_dir': self.app_base_dir,
            'use_cookie': use_cookie_for_this_run,
            'session_file_path': self.session_file_path,
            'session_lock': self.session_lock,
            'creator_download_folder_ignore_words': creator_folder_ignore_words_for_run,
            'use_date_prefix_for_subfolder': self.date_prefix_checkbox.isChecked() if hasattr(self, 'date_prefix_checkbox') else False,
            'date_prefix_format': self.date_prefix_format,            
            'keep_in_post_duplicates': self.keep_duplicates_checkbox.isChecked(),
            'keep_duplicates_mode': self.keep_duplicates_mode,
            'keep_duplicates_limit': self.keep_duplicates_limit,
            'manga_custom_filename_format': self.custom_manga_filename_format, 
            'manga_custom_date_format': self.manga_custom_date_format, # <-- ADD THIS
    
            'downloaded_hash_counts': self.downloaded_hash_counts,
            'downloaded_hash_counts_lock': self.downloaded_hash_counts_lock,
            'skip_current_file_flag': None,
            'processed_post_ids': processed_post_ids_for_this_run,
            'start_offset': start_offset_for_restore, 
            'fetch_first': fetch_first_enabled, 
        }

        args_template['override_output_dir'] = override_output_dir

        fetch_first_enabled = self.settings.value(FETCH_FIRST_KEY, False, type=bool)
        self.last_start_download_args = args_template.copy()

        if fetch_first_enabled and not post_id_from_url:
            self.log_signal.emit("=" * 40)
            self.log_signal.emit("🚀 'Fetch First' mode is active. Starting Stage 1: Fetching all post data.")
            self.log_signal.emit("   💡 If you are using a VPN for this stage, ensure it is connected now.")
            self.is_fetching_only = True
            self.set_ui_enabled(False)
            self._update_button_states_and_connections()
            self.progress_label.setText("Progress: Fetching pages...")
            
            fetch_thread_args = {
                'api_url_input': api_url, 'logger': self.log_signal.emit,
                'start_page': start_page, 'end_page': end_page,
                'manga_mode': manga_mode, 'cancellation_event': self.cancellation_event,
                'pause_event': self.pause_event, 'use_cookie': use_cookie_for_this_run,
                'cookie_text': cookie_text_from_input, 'selected_cookie_file': selected_cookie_file_path_for_backend,
                'app_base_dir': app_base_dir_for_cookies,
                'manga_filename_style_for_sort_check': self.manga_filename_style,
                'processed_post_ids': processed_post_ids_for_this_run,
                'fetch_all_first': True
            }
            
            self.download_thread = threading.Thread(target=self._run_fetch_only_thread, args=(fetch_thread_args,), daemon=True)
            self.download_thread.start()
            return True

        try:
            if should_use_multithreading_for_posts:
                self.log_signal.emit(f"    Initializing multi-threaded {current_mode_log_text.lower()} with {effective_num_post_workers} post workers...")
                args_template['emitter'] = self.worker_to_gui_queue
                self.start_multi_threaded_download(num_post_workers=effective_num_post_workers, **args_template)
            else:
                self.log_signal.emit(f"    Initializing single-threaded {'link extraction' if extract_links_only else 'download'}...")
                dt_expected_keys = [
                    'api_url_input', 'output_dir', 'known_names_copy', 'cancellation_event',
                    'filter_character_list', 'filter_mode', 'skip_zip',
                    'use_subfolders', 'use_post_subfolders', 'custom_folder_name',
                    'compress_images', 'download_thumbnails', 'service', 'user_id',
                    'downloaded_files', 'downloaded_file_hashes', 'pause_event', 'remove_from_filename_words_list',
                    'downloaded_files_lock', 'downloaded_file_hashes_lock', 'dynamic_character_filter_holder', 'session_file_path',
                    'session_lock', 'start_offset', 
                    'skip_words_list', 'skip_words_scope', 'char_filter_scope',
                    'show_external_links', 'extract_links_only', 'num_file_threads_for_worker',
                    'start_page', 'end_page', 'target_post_id_from_initial_url',
                    'manga_date_file_counter_ref',
                    'manga_global_file_counter_ref', 'manga_date_prefix',
                    'manga_mode_active', 'unwanted_keywords', 'manga_filename_style', 'scan_content_for_images',
                    'allow_multipart_download', 'use_cookie', 'cookie_text', 'app_base_dir', 'selected_cookie_file', 'override_output_dir', 'project_root_dir',
                    'text_only_scope', 'text_export_format', 'date_prefix_format',
                    'single_pdf_mode','multipart_parts_count', 'multipart_min_size_mb', 
                    'use_date_prefix_for_subfolder','keep_in_post_duplicates', 'keep_duplicates_mode',
                    'keep_duplicates_limit', 'downloaded_hash_counts', 'downloaded_hash_counts_lock',
                    'processed_post_ids', 'domain_override',
                    'archive_only_mode', 'skip_file_size_mb', 
                    'manga_custom_filename_format','manga_custom_date_format'
                ]
                args_template['skip_current_file_flag'] = None
                single_thread_args = {key: args_template[key] for key in dt_expected_keys if key in args_template}
                single_thread_args['fetch_first'] = args_template.get('fetch_first', False)
                self.start_single_threaded_download(**single_thread_args)
        except Exception as e:
            self._update_button_states_and_connections()
            self.log_signal.emit(f"❌ CRITICAL ERROR preparing download: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Start Error", f"Failed to start process:\n{e}")
            self.download_finished(0, 0, False, [])
            if self.pause_event: self.pause_event.clear()
            self.is_paused = False
        return True

    def restore_download(self):
        """Initiates the download restoration process."""
        if self._is_download_active():
            QMessageBox.warning(self, "Busy", "A download is already in progress.")
            return

        if not self.interrupted_session_data:
            self.log_signal.emit("❌ No session data to restore.")
            self._clear_session_and_reset_ui()
            return

        remaining_queue_from_session = self.interrupted_session_data.get("remaining_queue", [])
        if remaining_queue_from_session:
            self.favorite_download_queue.clear()
            self.favorite_download_queue.extend(remaining_queue_from_session)
            self.is_processing_favorites_queue = True
            self.log_signal.emit(f"ℹ️ Restored {len(self.favorite_download_queue)} item(s) to the download queue. Processing will continue automatically.")

        self.log_signal.emit("🔄 Preparing to restore download session...")

        settings = self.interrupted_session_data.get("ui_settings", {})
        restore_url = settings.get("api_url")
        restore_dir = settings.get("output_dir")

        if not restore_url:
            QMessageBox.critical(self, "Restore Error", "Session file is corrupt. Cannot restore because the URL is missing.")
            self._clear_session_and_reset_ui()
            return

        self.is_restore_pending = True
        self.start_download(direct_api_url=restore_url, override_output_dir=restore_dir, is_restore=True)

    def _update_ui_for_url_change(self, text=""):
        """A single, authoritative function to update all UI states based on the URL."""
        url_text = self.link_input.text().strip()
        service, _, _ = extract_post_info(url_text)

        # A list of all widgets that are context-dependent
        widgets_to_manage = [
            self.page_range_label, self.start_page_input, self.to_label, self.end_page_input,
            self.character_filter_widget, self.skip_words_input, self.skip_scope_toggle_button,
            self.remove_from_filename_input, self.radio_all, self.radio_images, self.radio_videos,
            self.radio_only_archives, self.radio_only_links, self.radio_only_audio, self.radio_more,
            self.skip_zip_checkbox, self.download_thumbnails_checkbox, self.compress_images_checkbox,
            self.use_subfolders_checkbox, self.use_subfolder_per_post_checkbox,
            self.scan_content_images_checkbox, self.external_links_checkbox, self.manga_mode_checkbox,
            self.use_cookie_checkbox, self.keep_duplicates_checkbox, self.date_prefix_checkbox,
            self.manga_rename_toggle_button, self.manga_date_prefix_input,
            self.multipart_toggle_button, self.custom_folder_input, self.custom_folder_label
        ]

        # --- Logic for Specialized Downloaders (Bunkr, nhentai) ---
        if service in ['bunkr', 'nhentai']:
            self.progress_log_label.setText("📜 Progress Log:")
            self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))
            
            # Disable all complex settings
            for widget in widgets_to_manage:
                if widget:
                    widget.setEnabled(False)

            # Force 'All' filter and disable it
            if self.radio_all:
                self.radio_all.setChecked(True)

            # Ensure Discord UI is hidden
            if hasattr(self, 'discord_scope_toggle_button'):
                self.discord_scope_toggle_button.setVisible(False)
            if hasattr(self, 'save_discord_as_pdf_btn'):
                self.save_discord_as_pdf_btn.setVisible(False)
            
            return  # CRUCIAL: Stop here for specialized URLs

        # --- Logic for Standard Downloaders (Kemono, Coomer, Discord) ---
        
        # First, re-enable all managed widgets as a baseline
        for widget in widgets_to_manage:
            if widget:
                widget.setEnabled(True)

        # Now, apply context-specific rules for the standard downloaders
        is_discord = (service == 'discord')
        if hasattr(self, 'discord_scope_toggle_button'):
            self.discord_scope_toggle_button.setVisible(is_discord)
        if hasattr(self, 'save_discord_as_pdf_btn'):
            self.save_discord_as_pdf_btn.setVisible(is_discord)
        if hasattr(self, 'discord_message_limit_input'):
            self.discord_message_limit_input.setVisible(is_discord)
        if is_discord:
            self._update_discord_scope_button_text()
        else:
            self.download_btn.setText(self._tr("start_download_button_text", "⬇️ Start Download"))

        # Re-run all the standard UI state functions to apply the correct logic
        is_manga_checked = self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False
        is_subfolder_checked = self.use_subfolders_checkbox.isChecked() if self.use_subfolders_checkbox else False
        is_cookie_checked = self.use_cookie_checkbox.isChecked() if self.use_cookie_checkbox else False
        
        self.update_ui_for_manga_mode(is_manga_checked)
        self.update_custom_folder_visibility()
        self.update_page_range_enabled_state()
        if self.radio_group and self.radio_group.checkedButton():
             self._handle_filter_mode_change(self.radio_group.checkedButton(), True)
        self.update_ui_for_subfolders(is_subfolder_checked)
        self._update_cookie_input_visibility(is_cookie_checked)

    def start_single_threaded_download (self ,**kwargs ):
        global BackendDownloadThread 
        try :
            self .download_thread =BackendDownloadThread (**kwargs )
            if self .pause_event :self .pause_event .clear ()
            self .is_paused =False 
            if hasattr (self .download_thread ,'progress_signal'):self .download_thread .progress_signal .connect (self .handle_main_log )
            if hasattr (self .download_thread ,'add_character_prompt_signal'):self .download_thread .add_character_prompt_signal .connect (self .add_character_prompt_signal )
            if hasattr (self .download_thread ,'finished_signal'):self .download_thread .finished_signal .connect (self .download_finished )
            if hasattr (self .download_thread ,'receive_add_character_result'):self .character_prompt_response_signal .connect (self .download_thread .receive_add_character_result )
            if hasattr (self .download_thread ,'external_link_signal'):self .download_thread .external_link_signal .connect (self .handle_external_link_signal )
            if hasattr (self .download_thread ,'file_progress_signal'):self .download_thread .file_progress_signal .connect (self .update_file_progress_display )
            if hasattr (self .download_thread ,'missed_character_post_signal'):
                self .download_thread .missed_character_post_signal .connect (self .handle_missed_character_post )
            if hasattr(self.download_thread, 'overall_progress_signal'): self.download_thread.overall_progress_signal.connect(self.update_progress_display)           
            if hasattr (self .download_thread ,'retryable_file_failed_signal'):

                if hasattr (self .download_thread ,'file_successfully_downloaded_signal'):
                    self .download_thread .file_successfully_downloaded_signal .connect (self ._handle_actual_file_downloaded )
                if hasattr (self .download_thread ,'post_processed_for_history_signal'):
                    self .download_thread .post_processed_for_history_signal .connect (self ._add_to_history_candidates )
                self .download_thread .retryable_file_failed_signal .connect (self ._handle_retryable_file_failure )
                if hasattr (self .download_thread ,'permanent_file_failed_signal'):
                    self .download_thread .permanent_file_failed_signal .connect (self ._handle_permanent_file_failure_from_thread )
            self .download_thread .start ()
            self .log_signal .emit ("✅ Single download thread (for posts) started.")
            self._update_button_states_and_connections() # Update buttons after thread starts      
        except Exception as e :
            self .log_signal .emit (f"❌ CRITICAL ERROR starting single-thread: {e }\n{traceback .format_exc ()}")
            QMessageBox .critical (self ,"Thread Start Error",f"Failed to start download process: {e }")
            if self .pause_event :self .pause_event .clear ()
            self .is_paused =False 

    def _show_error_files_dialog (self ):
        """Shows the dialog with files that were skipped due to errors."""
        # This method now always opens the dialog, even if the list is empty,
        # so the user can access the "Load URLs" button.
        dialog = ErrorFilesDialog(self.permanently_failed_files_for_dialog, self, self)
        dialog.retry_selected_signal.connect(self._handle_retry_from_error_dialog)
        dialog.exec_()
        
    def _handle_retry_from_error_dialog (self ,selected_files_to_retry ):
        self ._start_failed_files_retry_session (files_to_retry_list =selected_files_to_retry )
        self._update_error_button_count()

    def _handle_retryable_file_failure (self ,list_of_retry_details ):
        """Appends details of files that failed but might be retryable later."""
        if list_of_retry_details :
            self .retryable_failed_files_info .extend (list_of_retry_details )

    def _handle_permanent_file_failure_from_thread (self ,list_of_permanent_failure_details ):
        """Handles permanently failed files signaled by the single BackendDownloadThread."""
        if list_of_permanent_failure_details :
            self .permanently_failed_files_for_dialog .extend (list_of_permanent_failure_details )
            self .log_signal .emit (f"ℹ️ {len (list_of_permanent_failure_details )} file(s) from single-thread download marked as permanently failed for this session.")
            self._update_error_button_count()

    def _submit_post_to_worker_pool (self ,post_data_item ,worker_args_template ,num_file_dl_threads_for_each_worker ,emitter_for_worker ,ppw_expected_keys ,ppw_optional_keys_with_defaults ):
        """Helper to prepare and submit a single post processing task to the thread pool."""
        global PostProcessorWorker 
        if not isinstance (post_data_item ,dict ):
            self .log_signal .emit (f"⚠️ Skipping invalid post data item (not a dict): {type (post_data_item )}");
            return False 

        worker_init_args ={}
        missing_keys =[]
        for key in ppw_expected_keys :
            if key =='post_data':worker_init_args [key ]=post_data_item 
            elif key =='num_file_threads':worker_init_args [key ]=num_file_dl_threads_for_each_worker 
            elif key =='emitter':worker_init_args [key ]=emitter_for_worker 
            elif key in worker_args_template :worker_init_args [key ]=worker_args_template [key ]
            elif key in ppw_optional_keys_with_defaults :pass 
            else :missing_keys .append (key )

        if missing_keys :
            self .log_signal .emit (f"❌ CRITICAL ERROR: Missing keys for PostProcessorWorker: {', '.join (missing_keys )}");
            self .cancellation_event .set ()
            return False 

        if 'output_dir' in worker_init_args:
            worker_init_args['download_root'] = worker_init_args.pop('output_dir')
        if 'initial_target_post_id' in worker_init_args:
            worker_init_args['target_post_id_from_initial_url'] = worker_init_args.pop('initial_target_post_id')
        if 'filter_character_list_objects_initial' in worker_init_args:
            worker_init_args['filter_character_list'] = worker_init_args.pop('filter_character_list_objects_initial')

        try :
            worker_instance =PostProcessorWorker (**worker_init_args )
            if self .thread_pool :
                future =self .thread_pool .submit (worker_instance .process )
                self .active_futures .append (future )
                return True 
            else :
                self .log_signal .emit ("⚠️ Thread pool not available. Cannot submit task.");
                self .cancellation_event .set ()
                return False 
        except TypeError as te :
            self .log_signal .emit (f"❌ TypeError creating PostProcessorWorker: {te }\n    Passed Args: [{', '.join (sorted (worker_init_args .keys ()))}]\n{traceback .format_exc (limit =5 )}")
            self .cancellation_event .set ()
            return False 
        except RuntimeError :
            self .log_signal .emit (f"⚠️ RuntimeError submitting task (pool likely shutting down).")
            self .cancellation_event .set ()
            return False 
        except Exception as e :
            self .log_signal .emit (f"❌ Error submitting post {post_data_item .get ('id','N/A')} to worker: {e }")
            self .cancellation_event .set ()
            return False

    def _load_ui_from_settings_dict(self, settings: dict):
        """Populates the UI with values from a settings dictionary."""
        self.link_input.setText(settings.get('api_url', ''))
        self.dir_input.setText(settings.get('output_dir', ''))
        self.character_input.setText(settings.get('character_filter_text', ''))
        self.skip_words_input.setText(settings.get('skip_words_text', ''))
        self.remove_from_filename_input.setText(settings.get('remove_words_text', ''))
        self.custom_folder_input.setText(settings.get('custom_folder_name', ''))
        self.cookie_text_input.setText(settings.get('cookie_text', ''))
        if hasattr(self, 'manga_date_prefix_input'):
            self.manga_date_prefix_input.setText(settings.get('manga_date_prefix', ''))
        self.thread_count_input.setText(str(settings.get('num_threads', 4)))
        self.start_page_input.setText(str(settings.get('start_page', '')) if settings.get('start_page') is not None else '')
        self.end_page_input.setText(str(settings.get('end_page', '')) if settings.get('end_page') is not None else '')
        for checkbox_name, key in self.get_checkbox_map().items():
            checkbox = getattr(self, checkbox_name, None)
            if checkbox:
                checkbox.setChecked(settings.get(key, False))
        if settings.get('only_links'): self.radio_only_links.setChecked(True)
        else:
            filter_mode = settings.get('filter_mode', 'all')
            if filter_mode == 'image': self.radio_images.setChecked(True)
            elif filter_mode == 'video': self.radio_videos.setChecked(True)
            elif filter_mode == 'archive': self.radio_only_archives.setChecked(True)
            elif filter_mode == 'audio' and hasattr(self, 'radio_only_audio'): self.radio_only_audio.setChecked(True)
            else: self.radio_all.setChecked(True)

        self.keep_duplicates_mode = settings.get('keep_duplicates_mode', DUPLICATE_HANDLING_HASH)
        self.keep_duplicates_limit = settings.get('keep_duplicates_limit', 0)
        if hasattr(self, 'keep_duplicates_checkbox'):
            is_keep_mode = (self.keep_duplicates_mode == DUPLICATE_HANDLING_KEEP_ALL)
            self.keep_duplicates_checkbox.setChecked(is_keep_mode)
        self.more_filter_scope = settings.get('more_filter_scope')
        self.text_export_format = settings.get('text_export_format', 'pdf')
        self.single_pdf_setting = settings.get('single_pdf_setting', False)
        if self.radio_more.isChecked() and self.more_filter_scope:
            from .dialogs.MoreOptionsDialog import MoreOptionsDialog
            scope_text = "Comments" if self.more_filter_scope == MoreOptionsDialog.SCOPE_COMMENTS else "Description"
            format_display = f" ({self.text_export_format.upper()})"
            if self.single_pdf_setting:
                format_display = " (Single PDF)"
            self.radio_more.setText(f"{scope_text}{format_display}")
        self.skip_words_scope = settings.get('skip_words_scope', SKIP_SCOPE_POSTS)
        self.char_filter_scope = settings.get('char_filter_scope', CHAR_SCOPE_TITLE)
        self.manga_filename_style = settings.get('manga_filename_style', STYLE_POST_TITLE)
        self.allow_multipart_download_setting = settings.get('allow_multipart_download', False)
        self._update_skip_scope_button_text()
        self._update_char_filter_scope_button_text()
        self._update_manga_filename_style_button_text()
        self._update_multipart_toggle_button_text()

    def start_multi_threaded_download(self, num_post_workers, **kwargs):
        """
        Initializes and starts the multi-threaded download process.
        This version bundles arguments into a dictionary to prevent TypeErrors.
        """
        global PostProcessorWorker
        if self.thread_pool is None:
            if self.pause_event: self.pause_event.clear()
            self.is_paused = False
            self.thread_pool = ThreadPoolExecutor(max_workers=num_post_workers, thread_name_prefix='PostWorker_')

        self.active_futures = []
        self.processed_posts_count = 0; self.total_posts_to_process = 0; self.download_counter = 0; self.skip_counter = 0
        self.all_kept_original_filenames = []
        self.is_fetcher_thread_running = True

        fetcher_thread_args = {
            'api_url': kwargs.get('api_url_input'),
            'worker_args_template': kwargs,
            'num_post_workers': num_post_workers,
            'processed_post_ids': kwargs.get('processed_post_ids', [])
        }

        fetcher_thread = threading.Thread(
            target=self._fetch_and_queue_posts,
            args=(fetcher_thread_args,),  
            daemon=True,
            name="PostFetcher"
        )
        
        fetcher_thread.start()
        self.log_signal.emit(f"✅ Post fetcher thread started. {num_post_workers} post worker threads initializing...")
        self._update_button_states_and_connections()

    def _fetch_and_queue_posts(self, fetcher_args):
        """
        Fetches post data using the central `download_from_api` generator
        and submits tasks to the worker pool. This respects the 'Fetch First' setting.
        """
        global PostProcessorWorker, download_from_api
        
        worker_args_template = fetcher_args['worker_args_template']
        logger_func = lambda msg: self.log_signal.emit(f"[Fetcher] {msg}")

        try:
            # This single call now handles all fetching logic, including 'Fetch First'.
            post_generator = download_from_api(
                api_url_input=worker_args_template.get('api_url_input'),
                logger=logger_func,
                start_page=worker_args_template.get('start_page'),
                end_page=worker_args_template.get('end_page'),
                manga_mode=worker_args_template.get('manga_mode_active'),
                cancellation_event=self.cancellation_event,
                pause_event=self.pause_event,
                use_cookie=worker_args_template.get('use_cookie'),
                cookie_text=worker_args_template.get('cookie_text'),
                selected_cookie_file=worker_args_template.get('selected_cookie_file'),
                app_base_dir=worker_args_template.get('app_base_dir'),
                manga_filename_style_for_sort_check=worker_args_template.get('manga_filename_style'),
                processed_post_ids=worker_args_template.get('processed_post_ids', []),
                fetch_all_first=worker_args_template.get('fetch_first', False)
            )

            ppw_expected_keys = list(PostProcessorWorker.__init__.__code__.co_varnames)[1:]
            num_file_dl_threads = worker_args_template.get('num_file_threads_for_worker', 1)
            emitter = worker_args_template.get('emitter')
            
            fetch_first_enabled = worker_args_template.get('fetch_first', False)

            if fetch_first_enabled:
                # --- FETCH FIRST LOGIC ---
                # Exhaust the generator to get all posts into one list before processing.
                logger_func("   Fetch First: All posts have been fetched. Now queuing for download...")
                all_posts = [post for batch in post_generator for post in batch]
                
                self.total_posts_to_process = len(all_posts)
                self.overall_progress_signal.emit(self.total_posts_to_process, self.processed_posts_count)

                for post_data in all_posts:
                    if self.cancellation_event.is_set():
                        break
                    self._submit_post_to_worker_pool(post_data, worker_args_template, num_file_dl_threads, emitter, ppw_expected_keys, {})

            else:
                # --- STANDARD CONCURRENT LOGIC ---
                # Iterate over the batches of posts as they are yielded by the generator.
                for posts_batch_from_api in post_generator:
                    if self.cancellation_event.is_set():
                        break

                    processed_post_ids_set = set(worker_args_template.get('processed_post_ids', []))
                    new_posts_to_process = [
                        post for post in posts_batch_from_api if post.get('id') not in processed_post_ids_set
                    ]

                    if new_posts_to_process:
                        for post_data in new_posts_to_process:
                            if self.cancellation_event.is_set():
                                break
                            self._submit_post_to_worker_pool(post_data, worker_args_template, num_file_dl_threads, emitter, ppw_expected_keys, {})
                        
                        self.total_posts_to_process += len(new_posts_to_process)
                        self.overall_progress_signal.emit(self.total_posts_to_process, self.processed_posts_count)

        except Exception as e:
            logger_func(f"❌ Critical error during post fetching: {e}\n{traceback.format_exc(limit=2)}")
        finally:
            self.is_fetcher_thread_running = False
            logger_func("ℹ️ Post fetcher thread has finished submitting tasks.")
            self._check_if_all_work_is_done()

    def _handle_worker_result(self, result_tuple: tuple):
        """
        Safely processes results from a worker. This is now the ONLY place
        that checks if the entire download process is complete.
        """
        self.processed_posts_count += 1
        
        try:
            (downloaded, skipped, kept_originals, retryable,
             permanent, history_data,
             temp_filepath) = result_tuple

            if temp_filepath: self.session_temp_files.append(temp_filepath)
            
            with self.downloaded_files_lock:
                self.download_counter += downloaded
                self.skip_counter += skipped

            if permanent:
                self.permanently_failed_files_for_dialog.extend(permanent)
                self._update_error_button_count()
            
            if history_data and not permanent:
                self._add_to_history_candidates(history_data)
            elif history_data and permanent:
                post_id = history_data.get('post_id', 'N/A')
                self.log_signal.emit(f"⚠️ Post {post_id} had permanent file failures. It will NOT be marked as processed and will be retried on the next session/update.")

            self.overall_progress_signal.emit(self.total_posts_to_process, self.processed_posts_count)

        except Exception as e:
            self.log_signal.emit(f"❌ Error in _handle_worker_result: {e}\n{traceback.format_exc(limit=2)}")

        self._check_if_all_work_is_done()

        if not self.is_fetcher_thread_running and self.processed_posts_count >= self.total_posts_to_process:
            self.finished_signal.emit(self.download_counter, self.skip_counter, self.cancellation_event.is_set(), self.all_kept_original_filenames)

    def _trigger_single_pdf_creation(self):
        """Reads temp files, sorts them by date, then creates the single PDF."""
        self.log_signal.emit("="*40)
        self.log_signal.emit("Creating single PDF from collected text files...")

        posts_content_data = []
        for temp_filepath in self.session_temp_files:
            try:
                with open(temp_filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    posts_content_data.append(data)
            except Exception as e:
                self.log_signal.emit(f"   ⚠️ Could not read temp file '{temp_filepath}': {e}")
        
        if not posts_content_data:
            self.log_signal.emit("   No content was collected. Aborting PDF creation.")
            return

        output_dir = self.dir_input.text().strip() or QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        default_filename = os.path.join(output_dir, "Consolidated_Content.pdf")
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Single PDF", default_filename, "PDF Files (*.pdf)")

        if not filepath:
            self.log_signal.emit("   Single PDF creation cancelled by user.")
            return

        if not filepath.lower().endswith('.pdf'):
            filepath += '.pdf'
        
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = self.app_base_dir

        font_path = os.path.join(base_path, 'data', 'dejavu-sans', 'DejaVuSans.ttf')
        
        self.log_signal.emit("   Sorting collected posts by date (oldest first)...")
        sorted_content = sorted(posts_content_data, key=lambda x: x.get('published', 'Z'))

        create_single_pdf_from_content(sorted_content, filepath, font_path, logger=self.log_signal.emit)
        self.log_signal.emit("="*40)

    def _add_to_history_candidates(self, history_data):
        """Adds processed post data to the history candidates list and updates the creator profile."""        
        if self.save_creator_json_enabled_this_session and not self.is_single_post_session:
            post_id = history_data.get('post_id')
            service = history_data.get('service')
            user_id = history_data.get('user_id')
            if post_id and service and user_id:
                creator_key = (service.lower(), str(user_id))
                creator_name = self.creator_name_cache.get(creator_key, f"{service}_{user_id}")
                
                profile_data = self._setup_creator_profile(creator_name, self.session_file_path)
                
                if post_id not in profile_data.get('processed_post_ids', []):
                    profile_data.setdefault('processed_post_ids', []).append(post_id)
                    self._save_creator_profile(creator_name, profile_data, self.session_file_path)

        if history_data and len(self.download_history_candidates) < 8:
            history_data['download_date_timestamp'] = time.time()
            creator_key = (history_data.get('service','').lower(), str(history_data.get('user_id','')))
            history_data['creator_name'] = self.creator_name_cache.get(creator_key, history_data.get('user_id','Unknown'))
            self.download_history_candidates.append(history_data)


    def _finalize_download_history (self ):
        """Processes candidates and selects the final 3 history entries.
        Only updates final_download_history_entries if new candidates are available.
        """
        if not self .download_history_candidates :


            self .log_signal .emit ("ℹ️ No new history candidates from this session. Preserving existing history.")


            self .download_history_candidates .clear ()
            return 

        candidates =list (self .download_history_candidates )
        now =datetime .datetime .now (datetime .timezone .utc )

        def get_sort_key (entry ):
            upload_date_str =entry .get ('upload_date_str')
            if not upload_date_str :
                return datetime .timedelta .max 
            try :

                upload_dt =datetime .datetime .fromisoformat (upload_date_str .replace ('Z','+00:00'))
                if upload_dt .tzinfo is None :
                    upload_dt =upload_dt .replace (tzinfo =datetime .timezone .utc )
                return abs (now -upload_dt )
            except ValueError :
                return datetime .timedelta .max 

        candidates .sort (key =get_sort_key )
        self .final_download_history_entries =candidates [:3 ]
        self .log_signal .emit (f"ℹ️ Finalized download history: {len (self .final_download_history_entries )} entries selected.")
        self .download_history_candidates .clear ()


        self ._save_persistent_history ()

    def _get_configurable_widgets_on_pause (self ):
        """Returns a list of widgets that should be re-enabled when paused."""
        return [
        self .dir_input ,self .dir_button ,
        self .character_input ,self .char_filter_scope_toggle_button ,
        self .skip_words_input ,self .skip_scope_toggle_button ,
        self .remove_from_filename_input ,
        self .radio_all ,self .radio_images ,self .radio_videos ,
        self .radio_only_archives ,self .radio_only_links ,
        self .skip_zip_checkbox ,
        self .download_thumbnails_checkbox ,self .compress_images_checkbox ,
        self .use_subfolders_checkbox ,self .use_subfolder_per_post_checkbox ,
        self .manga_mode_checkbox ,
        self .manga_rename_toggle_button ,
        self .cookie_browse_button ,
        self .favorite_mode_checkbox ,
        self .multipart_toggle_button ,
        self .cookie_text_input ,
        self .scan_content_images_checkbox ,
        self .use_cookie_checkbox ,
        self .external_links_checkbox 
        ]

    def set_ui_enabled (self ,enabled ):
        all_potentially_toggleable_widgets =[
        self .link_input ,self .dir_input ,self .dir_button ,
        self .page_range_label ,self .start_page_input ,self .to_label ,self .end_page_input ,
        self .character_input ,self .char_filter_scope_toggle_button ,self .character_filter_widget ,
        self .filters_and_custom_folder_container_widget ,
        self .custom_folder_label ,self .custom_folder_input ,
        self .skip_words_input ,self .skip_scope_toggle_button ,self .remove_from_filename_input ,
        self .radio_all ,self .radio_images ,self .radio_videos ,self .radio_only_archives ,self .radio_only_links ,
        self .skip_zip_checkbox , self .download_thumbnails_checkbox ,self .compress_images_checkbox ,
        self .use_subfolders_checkbox ,self .use_subfolder_per_post_checkbox ,self .scan_content_images_checkbox ,
        self .use_multithreading_checkbox ,self .thread_count_input ,self .thread_count_label ,
        self .favorite_mode_checkbox ,
        self .external_links_checkbox ,self .manga_mode_checkbox ,self .manga_rename_toggle_button ,self .use_cookie_checkbox ,self .cookie_text_input ,self .cookie_browse_button ,
        self .multipart_toggle_button ,self .radio_only_audio ,
        self .character_search_input ,self .new_char_input ,self .add_char_button ,self .add_to_filter_button ,self .delete_char_button ,
        self .reset_button, self.radio_more, self.keep_duplicates_checkbox
        ]

        widgets_to_enable_on_pause =self ._get_configurable_widgets_on_pause ()
        is_fav_mode_active =self .favorite_mode_checkbox .isChecked ()if self .favorite_mode_checkbox else False 
        download_is_active_or_paused =not enabled 

        if not enabled :
            if self .bottom_action_buttons_stack :
                self .bottom_action_buttons_stack .setCurrentIndex (0 )

            if self .external_link_download_thread and self .external_link_download_thread .isRunning ():
                self .log_signal .emit ("ℹ️ Cancelling active Mega download due to UI state change.")
                self .external_link_download_thread .cancel ()
        else :
            pass 


        for widget in all_potentially_toggleable_widgets :
            if not widget :continue 


            if widget is self .favorite_mode_artists_button or widget is self .favorite_mode_posts_button :continue 
            elif self .is_paused and widget in widgets_to_enable_on_pause :
                widget .setEnabled (True )
            elif widget is self .favorite_mode_checkbox :
                widget .setEnabled (enabled )
            elif widget is self .use_cookie_checkbox and is_fav_mode_active :
                widget .setEnabled (False )
            elif widget is self .use_cookie_checkbox and self .is_paused and widget in widgets_to_enable_on_pause :
                widget .setEnabled (True )
            else :
                widget .setEnabled (enabled )

        if self .link_input :
            self .link_input .setEnabled (enabled and not is_fav_mode_active )



        if not enabled :
            if self .favorite_mode_artists_button :
                self .favorite_mode_artists_button .setEnabled (False )
            if self .favorite_mode_posts_button :
                self .favorite_mode_posts_button .setEnabled (False )

        if self .download_btn :
            self .download_btn .setEnabled (enabled and not is_fav_mode_active )


        if self .external_links_checkbox :
            is_only_links =self .radio_only_links and self .radio_only_links .isChecked ()
            is_only_archives =self .radio_only_archives and self .radio_only_archives .isChecked ()
            is_only_audio =hasattr (self ,'radio_only_audio')and self .radio_only_audio .isChecked ()
            can_enable_ext_links =enabled and not is_only_links and not is_only_archives and not is_only_audio 
            self .external_links_checkbox .setEnabled (can_enable_ext_links )
            if self .is_paused and not is_only_links and not is_only_archives and not is_only_audio :
                self .external_links_checkbox .setEnabled (True )
        if hasattr (self ,'use_cookie_checkbox'):
            self ._update_cookie_input_visibility (self .use_cookie_checkbox .isChecked ())

        if self .log_verbosity_toggle_button :self .log_verbosity_toggle_button .setEnabled (True )

        multithreading_currently_on =self .use_multithreading_checkbox .isChecked ()
        if self .thread_count_input :self .thread_count_input .setEnabled (enabled and multithreading_currently_on )
        if self .thread_count_label :self .thread_count_label .setEnabled (enabled and multithreading_currently_on )

        subfolders_currently_on =self .use_subfolders_checkbox .isChecked ()
        if self .use_subfolder_per_post_checkbox :
            self .use_subfolder_per_post_checkbox .setEnabled (enabled or (self .is_paused and self .use_subfolder_per_post_checkbox in widgets_to_enable_on_pause ))
        if self .cancel_btn :self .cancel_btn .setEnabled (download_is_active_or_paused )
        if self .pause_btn :
            self .pause_btn .setEnabled (download_is_active_or_paused )
            if download_is_active_or_paused :
                self .pause_btn .setText (self ._tr ("resume_download_button_text","▶️ Resume Download")if self .is_paused else self ._tr ("pause_download_button_text","⏸️ Pause Download"))
                self .pause_btn .setToolTip (self ._tr ("resume_download_button_tooltip","Click to resume the download.")if self .is_paused else self ._tr ("pause_download_button_tooltip","Click to pause the download."))
            else :
                self .pause_btn .setText (self ._tr ("pause_download_button_text","⏸️ Pause Download"))
                self .pause_btn .setToolTip (self ._tr ("pause_download_button_tooltip","Click to pause the ongoing download process."))
                self .is_paused =False 
        if self .cancel_btn :self .cancel_btn .setText (self ._tr ("cancel_button_text","❌ Cancel & Reset UI"))
        if enabled :
            if self .pause_event :self .pause_event .clear ()
        if enabled or self .is_paused :
            self ._handle_multithreading_toggle (multithreading_currently_on )
            self .update_ui_for_manga_mode (self .manga_mode_checkbox .isChecked ()if self .manga_mode_checkbox else False )
            self .update_custom_folder_visibility (self .link_input .text ())
            self .update_page_range_enabled_state ()
            if self .radio_group and self .radio_group .checkedButton ():
                self ._handle_filter_mode_change (self .radio_group .checkedButton (),True )
            self .update_ui_for_subfolders (subfolders_currently_on )
            self ._handle_favorite_mode_toggle (is_fav_mode_active )

    def _handle_pause_resume_action(self):
        if not self._is_download_active():
            return

        self.is_paused = not self.is_paused

        if isinstance(self.download_thread, DiscordDownloadThread):
            if self.is_paused:
                self.download_thread.pause()
            else:
                self.download_thread.resume()
        else:
            # Fallback for older download types
            if self.is_paused:
                self.pause_event.set()
                self.log_signal.emit("⏸️ Download paused. Workers will halt on their next check.")
            else:
                self.pause_event.clear()
                self.log_signal.emit("▶️ Download resumed.")

        # This call correctly updates the button's text to "Pause" or "Resume"
        self.set_ui_enabled(False)

    def _perform_soft_ui_reset (self ,preserve_url =None ,preserve_dir =None ):
        """Resets UI elements and some state to app defaults, then applies preserved inputs."""
        self .log_signal .emit ("🔄 Performing soft UI reset...")
        self .link_input .clear ()
        self .dir_input .clear ()
        self .custom_folder_input .clear ();self .character_input .clear ();
        self .skip_words_input .clear ();self .start_page_input .clear ();self .end_page_input .clear ();self .new_char_input .clear ();
        if hasattr (self ,'remove_from_filename_input'):self .remove_from_filename_input .clear ()
        self .character_search_input .clear ();self .thread_count_input .setText ("4");self .radio_all .setChecked (True );
        self .skip_zip_checkbox .setChecked (True );self .download_thumbnails_checkbox .setChecked (False );
        self .compress_images_checkbox .setChecked (False );self .use_subfolders_checkbox .setChecked (False );
        self .use_subfolder_per_post_checkbox .setChecked (True );self .use_multithreading_checkbox .setChecked (True );
        if self .favorite_mode_checkbox :self .favorite_mode_checkbox .setChecked (False )
        if hasattr (self ,'scan_content_images_checkbox'):self .scan_content_images_checkbox .setChecked (False )
        self .external_links_checkbox .setChecked (False )
        if self .manga_mode_checkbox :self .manga_mode_checkbox .setChecked (False )
        if hasattr (self ,'use_cookie_checkbox'):self .use_cookie_checkbox .setChecked (self .use_cookie_setting )
        if not (hasattr (self ,'use_cookie_checkbox')and self .use_cookie_checkbox .isChecked ()):
            self .selected_cookie_filepath =None 
        if hasattr (self ,'cookie_text_input'):self .cookie_text_input .setText (self .cookie_text_setting if self .use_cookie_setting else "")
        self .allow_multipart_download_setting =False 
        self ._update_multipart_toggle_button_text ()

        self .skip_words_scope =SKIP_SCOPE_POSTS 
        self ._update_skip_scope_button_text ()

        if hasattr (self ,'manga_date_prefix_input'):self .manga_date_prefix_input .clear ()

        self .char_filter_scope =CHAR_SCOPE_TITLE 
        self ._update_char_filter_scope_button_text ()

        self .manga_filename_style =STYLE_POST_TITLE 
        self ._update_manga_filename_style_button_text ()
        if preserve_url is not None :
            self .link_input .setText (preserve_url )
        if preserve_dir is not None :
            self .dir_input .setText (preserve_dir )
        self .external_link_queue .clear ();self .extracted_links_cache =[]
        self ._is_processing_external_link_queue =False ;self ._current_link_post_title =None 
        if self .pause_event :self .pause_event .clear ()
        self.is_restore_pending = False
        self .total_posts_to_process =0 ;self .processed_posts_count =0 
        self .download_counter =0 ;self .skip_counter =0 
        self .all_kept_original_filenames =[]
        self .is_paused =False 
        self ._handle_multithreading_toggle (self .use_multithreading_checkbox .isChecked ())
     
        self._update_button_states_and_connections() # Reset button states and connections
        self .favorite_download_queue .clear ()
        self .is_processing_favorites_queue =False 

        self .only_links_log_display_mode =LOG_DISPLAY_LINKS 

        if hasattr (self ,'link_input'):
            if self .download_extracted_links_button :
                self .download_extracted_links_button .setEnabled (False )

            self .last_link_input_text_for_queue_sync =self .link_input .text ()
        self .permanently_failed_files_for_dialog .clear ()
        self .filter_character_list (self .character_search_input .text ())
        self .favorite_download_scope =FAVORITE_SCOPE_SELECTED_LOCATION 
        self ._update_favorite_scope_button_text ()

        self .set_ui_enabled (True )
        self.interrupted_session_data = None # Clear session data from memory      
        self .update_custom_folder_visibility (self .link_input .text ())
        self .update_page_range_enabled_state ()
        self ._update_cookie_input_visibility (self .use_cookie_checkbox .isChecked ()if hasattr (self ,'use_cookie_checkbox')else False )
        if hasattr (self ,'favorite_mode_checkbox'):
            self ._handle_favorite_mode_toggle (False )

        self .log_signal .emit ("✅ Soft UI reset complete. Preserved URL and Directory (if provided).")

    def _update_log_display_mode_button_text (self ):
        if hasattr (self ,'log_display_mode_toggle_button'):
            if self .only_links_log_display_mode ==LOG_DISPLAY_LINKS :
                self .log_display_mode_toggle_button .setText (self ._tr ("log_display_mode_links_view_text","🔗 Links View"))
                self .log_display_mode_toggle_button .setToolTip (
                "Current View: Extracted Links.\n"
                "After Mega download, Mega log is shown THEN links are appended.\n"
                "Click to switch to 'Download Progress View'."
                )
            else :
                self .log_display_mode_toggle_button .setText (self ._tr ("log_display_mode_progress_view_text","⬇️ Progress View"))
                self .log_display_mode_toggle_button .setToolTip (
                "Current View: Mega Download Progress.\n"
                "After Mega download, ONLY Mega log is shown (links hidden).\n"
                "Click to switch to 'Extracted Links View'."
                )

    def _toggle_log_display_mode (self ):
        self .only_links_log_display_mode =LOG_DISPLAY_DOWNLOAD_PROGRESS if self .only_links_log_display_mode ==LOG_DISPLAY_LINKS else LOG_DISPLAY_LINKS 
        self ._update_log_display_mode_button_text ()
        self ._filter_links_log ()

    def cancel_download_button_action(self):
        if self.is_paused:
            self.log_signal.emit("❌ Cancellation requested while paused. Stopping all workers...")
        
        if self._is_download_active() and hasattr(self.download_thread, 'cancel'):
            self.progress_label.setText(self._tr("status_cancelling", "Cancelling... Please wait."))
            self.download_thread.cancel()
        else:
            # Fallback for other download types
            self.cancellation_event.set()

        # Update UI to "Cancelling" state
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        if hasattr(self, 'reset_button'):
            self.reset_button.setEnabled(False)

        self.progress_label.setText(self._tr("status_cancelling", "Cancelling... Please wait."))

        # Only call QThread-specific methods if the thread is a QThread
        if self.download_thread and hasattr(self.download_thread, 'requestInterruption'):
            self.download_thread.requestInterruption()
            self.log_signal.emit("    Signaled single download thread to interrupt.")

        if self.thread_pool:
            self.log_signal.emit("    Signaling worker pool to cancel futures...")
        
        if self.external_link_download_thread and self.external_link_download_thread.isRunning():
            self.log_signal.emit("    Cancelling active External Link download thread...")
            self.external_link_download_thread.cancel()

        if isinstance(self.download_thread, NhentaiDownloadThread): 
            self.log_signal.emit("    Signaling nhentai download thread to cancel.")
            self.download_thread.cancel()

        if isinstance(self.download_thread, BunkrDownloadThread):
            self.log_signal.emit("    Signaling Bunkr download thread to cancel.")
            self.download_thread.cancel()

        if isinstance(self.download_thread, Saint2DownloadThread):
            self.log_signal.emit("    Signaling Saint2 download thread to cancel.")
            self.download_thread.cancel()

        if isinstance(self.download_thread, EromeDownloadThread):
            self.log_signal.emit("    Signaling Erome download thread to cancel.")
            self.download_thread.cancel()

        if isinstance(self.download_thread, Hentai2readDownloadThread):
            self.log_signal.emit("    Signaling Hentai2Read download thread to cancel.")
            self.download_thread.cancel()

    def _get_domain_for_service(self, service_name: str) -> str:
        """Determines the base domain for a given service."""
        if not isinstance(service_name, str):
            return "kemono.cr"  # Default fallback
        service_lower = service_name.lower()
        coomer_primary_services = {'onlyfans', 'fansly', 'manyvids', 'candfans', 'gumroad', 'subscribestar', 'dlsite'}
        if service_lower in coomer_primary_services:
            return "coomer.st"
        return "kemono.cr"

    def download_finished(self, total_downloaded, total_skipped, cancelled_by_user, kept_original_names_list=None):
        if not self.finish_lock.acquire(blocking=False):
            return

        try:
            if self.is_finishing:
                return
            self.is_finishing = True

            if cancelled_by_user:
                self.log_signal.emit("✅ Cancellation complete. Resetting UI.")
                self._clear_session_file()
                self.interrupted_session_data = None
                self.is_restore_pending = False
                current_url = self.link_input.text()
                current_dir = self.dir_input.text()
                self._perform_soft_ui_reset(preserve_url=current_url, preserve_dir=current_dir)
                self.progress_label.setText(f"{self._tr('status_cancelled_by_user', 'Cancelled by user')}. {self._tr('ready_for_new_task_text', 'Ready for new task.')}")
                self.file_progress_label.setText("")
                if self.pause_event: self.pause_event.clear()
                self.is_paused = False
                return

            self.log_signal.emit("🏁 Download of current item complete.")

            if self.is_processing_favorites_queue and self.favorite_download_queue:
                self.log_signal.emit("✅ Item finished. Processing next in queue...")
                self.is_finishing = False 
                self.finish_lock.release() 
                self._process_next_favorite_download()
                return  

            if self.is_processing_favorites_queue:
                self.is_processing_favorites_queue = False
                self.log_signal.emit("✅ All items from the download queue have been processed.")

            if not cancelled_by_user and not self.retryable_failed_files_info:
                self._clear_session_file()
                self.interrupted_session_data = None
                self.is_restore_pending = False

            self._finalize_download_history()
            status_message = self._tr("status_completed", "Completed")

            summary_log = "=" * 40
            summary_log += f"\n🏁 Download {status_message}!\n    Summary: Downloaded Files={total_downloaded}, Skipped Files={total_skipped}\n"
            summary_log += "=" * 40
            self.log_signal.emit(summary_log)
            self.log_signal.emit("")
            
            if self.thread_pool:
                self.thread_pool.shutdown(wait=False) 
                self.thread_pool = None

            if self.single_pdf_setting and self.session_temp_files:
                try:
                    self._trigger_single_pdf_creation()
                finally:
                    self._cleanup_temp_files()
            else:
                self._cleanup_temp_files()
                self.single_pdf_setting = False

            if kept_original_names_list is None:
                kept_original_names_list = list(self.all_kept_original_filenames) if hasattr(self, 'all_kept_original_filenames') else []
            if kept_original_names_list is None:
                kept_original_names_list = []

            if kept_original_names_list:
                intro_msg = (
                    HTML_PREFIX +
                    "<p>ℹ️ The following files from multi-file manga posts "
                    "(after the first file) kept their <b>original names</b>:</p>"
                )
                self.log_signal.emit(intro_msg)
                html_list_items = "<ul>"
                for name in kept_original_names_list:
                    html_list_items += f"<li><b>{name}</b></li>"
                html_list_items += "</ul>"
                self.log_signal.emit(HTML_PREFIX + html_list_items)
                self.log_signal.emit("=" * 40)

            if self.download_thread:
                if isinstance(self.download_thread, QThread):
                    try:
                        # Disconnect signals to prevent any lingering connections
                        if hasattr(self.download_thread, 'progress_signal'): self.download_thread.progress_signal.disconnect(self.handle_main_log)
                        if hasattr(self.download_thread, 'add_character_prompt_signal'): self.download_thread.add_character_prompt_signal.disconnect(self.add_character_prompt_signal)
                        if hasattr(self.download_thread, 'finished_signal'): self.download_thread.finished_signal.disconnect(self.download_finished)
                        if hasattr(self.download_thread, 'receive_add_character_result'): self.character_prompt_response_signal.disconnect(self.download_thread.receive_add_character_result)
                        if hasattr(self.download_thread, 'external_link_signal'): self.download_thread.external_link_signal.disconnect(self.handle_external_link_signal)
                        if hasattr(self.download_thread, 'file_progress_signal'): self.download_thread.file_progress_signal.disconnect(self.update_file_progress_display)
                        if hasattr(self.download_thread, 'missed_character_post_signal'): self.download_thread.missed_character_post_signal.disconnect(self.handle_missed_character_post)
                        if hasattr(self.download_thread, 'retryable_file_failed_signal'): self.download_thread.retryable_file_failed_signal.disconnect(self._handle_retryable_file_failure)
                        if hasattr(self.download_thread, 'file_successfully_downloaded_signal'): self.download_thread.file_successfully_downloaded_signal.disconnect(self._handle_actual_file_downloaded)
                        if hasattr(self.download_thread, 'post_processed_for_history_signal'): self.download_thread.post_processed_for_history_signal.disconnect(self._add_to_history_candidates)
                    except (TypeError, RuntimeError) as e:
                        self.log_signal.emit(f"ℹ️ Note during single-thread signal disconnection: {e}")

                    self.download_thread.deleteLater()
                    self.download_thread = None
                else:
                    self.download_thread = None

            self.progress_label.setText(
                f"{status_message}: "
                f"{total_downloaded} {self._tr('files_downloaded_label', 'downloaded')}, "
                f"{total_skipped} {self._tr('files_skipped_label', 'skipped')}."
            )
            self.file_progress_label.setText("")

            if not cancelled_by_user and self.retryable_failed_files_info:
                num_failed = len(self.retryable_failed_files_info)
                reply = QMessageBox.question(self, "Retry Failed Downloads?",
                                             f"{num_failed} file(s) failed with potentially recoverable errors (e.g., IncompleteRead).\n\n"
                                             "Would you like to attempt to download these failed files again?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    self.is_finishing = False
                    self.finish_lock.release()
                    self._start_failed_files_retry_session()
                    return
                else:
                    self.log_signal.emit("ℹ️ User chose not to retry failed files.")
                    self.permanently_failed_files_for_dialog.extend(self.retryable_failed_files_info)
                    if self.permanently_failed_files_for_dialog:
                        self.log_signal.emit(f"🆘 Error button enabled. {len(self.permanently_failed_files_for_dialog)} file(s) can be viewed.")
                    self.cancellation_message_logged_this_session = False
                    self.retryable_failed_files_info.clear()

            self.is_fetcher_thread_running = False
            
            # --- This is where the post-download action is triggered ---
            if not cancelled_by_user and not self.is_processing_favorites_queue:
                self._execute_post_download_action()

            self.set_ui_enabled(True)
            self._update_button_states_and_connections()
            self.cancellation_message_logged_this_session = False
            self.active_update_profile = None 
        finally:
            self.finish_lock.release()

    def _execute_post_download_action(self):
        """Checks the settings and performs the chosen action after downloads complete."""
        action = self.settings.value(POST_DOWNLOAD_ACTION_KEY, "off")

        if action == "off":
            return

        elif action == "notify":
            QApplication.beep()
            self.log_signal.emit("✅ Download complete! Notification sound played.")
            return
        
        confirm_title = self._tr("action_confirmation_title", "Action After Download")
        confirm_text = ""
        
        if action == "sleep":
            confirm_text = self._tr("confirm_sleep_text", "All downloads are complete. The computer will now go to sleep.")
        elif action == "shutdown":
            confirm_text = self._tr("confirm_shutdown_text", "All downloads are complete. The computer will now shut down.")
        
        dialog = CountdownMessageBox(
            title=confirm_title,
            text=confirm_text,
            countdown_seconds=10,
            parent_app=self,
            parent=self
        )

        if dialog.exec_() == QDialog.Accepted:
            # The rest of the logic only runs if the dialog is accepted (by click or timeout)
            self.log_signal.emit(f"ℹ️ Performing post-download action: {action.capitalize()}")
            try:
                if sys.platform == "win32":
                    if action == "sleep":
                        os.system("powercfg -hibernate off")
                        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
                        os.system("powercfg -hibernate on")
                    elif action == "shutdown":
                        os.system("shutdown /s /t 1")
                elif sys.platform == "darwin": # macOS
                    if action == "sleep":
                        os.system("pmset sleepnow")
                    elif action == "shutdown":
                        os.system("osascript -e 'tell app \"System Events\" to shut down'")
                else: # Linux
                    if action == "sleep":
                        os.system("systemctl suspend")
                    elif action == "shutdown":
                        os.system("systemctl poweroff")
            except Exception as e:
                self.log_signal.emit(f"❌ Failed to execute post-download action '{action}': {e}")
        else:
            # This block runs if the user clicks "No"
            self.log_signal.emit(f"ℹ️ Post-download '{action}' cancelled by user.")

    def _handle_keep_duplicates_toggled(self, checked):
        """Shows the duplicate handling dialog when the checkbox is checked."""
        if checked:
            dialog = KeepDuplicatesDialog(self.keep_duplicates_mode, self.keep_duplicates_limit, self)
            if dialog.exec_() == QDialog.Accepted:
                options = dialog.get_selected_options()
                self.keep_duplicates_mode = options["mode"]
                self.keep_duplicates_limit = options["limit"]

                limit_text = f"with a limit of {self.keep_duplicates_limit}" if self.keep_duplicates_limit > 0 else "with no limit"
                self.log_signal.emit(f"ℹ️ Duplicate handling mode set to: '{self.keep_duplicates_mode}' {limit_text}.")
                self.log_signal.emit(f"")
                self.log_signal.emit(f"")
                if self.keep_duplicates_mode == DUPLICATE_HANDLING_KEEP_ALL:
                    self._log_keep_everything_warning()
            else:
                self.keep_duplicates_checkbox.setChecked(False)
        else:
            self.keep_duplicates_mode = DUPLICATE_HANDLING_HASH
            self.keep_duplicates_limit = 0
            self.log_signal.emit("ℹ️ 'Keep Duplicates' disabled. Reverted to default hash checking.")

    def _log_keep_everything_warning(self):
        """Logs a formatted warning when the 'Keep Everything' mode is selected."""
     
        warning_html = (
            f'{HTML_PREFIX}'
            '<h2 style="margin-top: 8px; margin-bottom: 4px; font-weight: bold;">⚠️ ATTENTION: "Keep Everything" Enabled</h2>'
            '<h3><p style="margin-top: 0; margin-bottom: 4px;">This mode will download every single file from the API response for a post,</p>'
            '<p style="margin-top: 0; margin-bottom: 4px;">even if they have identical content. This can lead to many redundant files.</p>'
            '<p style="margin-top: 0; margin-bottom: 4px;"><b>Recommendation:</b> Consider using the <b>limit feature</b>.</p>'
            '<p style="margin-top: 0; margin-bottom: 0;">For example, setting the limit to <b>2</b> will download a file with the same content up to two times.</p></h3>'
        )
        self.log_signal.emit(warning_html)

    def _handle_thumbnail_mode_change (self ,thumbnails_checked ):
        """Handles UI changes when 'Download Thumbnails Only' is toggled."""
        # This function is now a placeholder. The two checkboxes are independent.
        pass

        if thumbnails_checked :
            self .scan_content_images_checkbox .setChecked (True )
            self .scan_content_images_checkbox .setEnabled (False )
            self .scan_content_images_checkbox .setToolTip (
            "Automatically enabled and locked because 'Download Thumbnails Only' is active.\n"
            "In this mode, only images found by content scanning will be downloaded."
            )
        else :
            self .scan_content_images_checkbox .setEnabled (True )
            self .scan_content_images_checkbox .setChecked (False )
            self .scan_content_images_checkbox .setToolTip (self ._original_scan_content_tooltip )

    def _start_failed_files_retry_session (self ,files_to_retry_list =None ):
        if files_to_retry_list :
            self .files_for_current_retry_session =list (files_to_retry_list )
            self .permanently_failed_files_for_dialog =[f for f in self .permanently_failed_files_for_dialog if f not in files_to_retry_list ]
        else :
            self .files_for_current_retry_session =list (self .retryable_failed_files_info )
            self .retryable_failed_files_info .clear ()
        self .log_signal .emit (f"🔄 Starting retry session for {len (self .files_for_current_retry_session )} file(s)...")
        self .set_ui_enabled (False )
        if self .cancel_btn :self .cancel_btn .setText (self ._tr ("cancel_retry_button_text","❌ Cancel Retry"))

        raw_character_filters_text = self.character_input.text().strip()
        _, download_commands = self._parse_character_filters(raw_character_filters_text)
        domain_override_command = download_commands.get('domain_override')

        if domain_override_command:
            self.log_signal.emit(f"ℹ️ Retry Session: Domain override '[.{domain_override_command}]' is active.")

        self .active_retry_futures =[]
        self .processed_retry_count =0 
        self .succeeded_retry_count =0 
        self .failed_retry_count_in_session =0 
        self .total_files_for_retry =len (self .files_for_current_retry_session )
        self .active_retry_futures_map ={}

        self .progress_label .setText (self ._tr ("progress_posts_text","Progress: {processed_posts} / {total_posts} posts ({progress_percent:.1f}%)").format (processed_posts =0 ,total_posts =self .total_files_for_retry ,progress_percent =0.0 ).replace ("posts","files"))
        self .cancellation_event .clear ()

        num_retry_threads =1 
        try :
            num_threads_from_gui =int (self .thread_count_input .text ().strip ())
            num_retry_threads =max (1 ,min (num_threads_from_gui ,MAX_FILE_THREADS_PER_POST_OR_WORKER ,self .total_files_for_retry if self .total_files_for_retry >0 else 1 ))
        except ValueError :
            num_retry_threads =1 

        self .retry_thread_pool =ThreadPoolExecutor (max_workers =num_retry_threads ,thread_name_prefix ='RetryFile_')
        common_ppw_args_for_retry ={
        'download_root':self .dir_input .text ().strip (),
        'known_names':list (KNOWN_NAMES ),
        'emitter':self .worker_to_gui_queue ,
        'unwanted_keywords':{'spicy','hd','nsfw','4k','preview','teaser','clip'},
        'domain_override': domain_override_command,
        'filter_mode':self .get_filter_mode (),
        'skip_zip':self .skip_zip_checkbox .isChecked (),
        'use_subfolders':self .use_subfolders_checkbox .isChecked (),
        'use_post_subfolders':self .use_subfolder_per_post_checkbox .isChecked (),
        'compress_images':self .compress_images_checkbox .isChecked (),
        'download_thumbnails':self .download_thumbnails_checkbox .isChecked (),
        'pause_event':self .pause_event ,
        'cancellation_event':self .cancellation_event ,
        'downloaded_files':self .downloaded_files ,
        'downloaded_file_hashes':self .downloaded_file_hashes ,
        'downloaded_files_lock':self .downloaded_files_lock ,
        'downloaded_file_hashes_lock':self .downloaded_file_hashes_lock ,
        'skip_words_list':[word .strip ().lower ()for word in self .skip_words_input .text ().strip ().split (',')if word .strip ()],
        'skip_words_scope':self .get_skip_words_scope (),
        'char_filter_scope':self .get_char_filter_scope (),
        'remove_from_filename_words_list':[word .strip ()for word in self .remove_from_filename_input .text ().strip ().split (',')if word .strip ()]if hasattr (self ,'remove_from_filename_input')else [],
        'allow_multipart_download':self .allow_multipart_download_setting ,
        'filter_character_list':None ,
        'dynamic_character_filter_holder':None ,
        'target_post_id_from_initial_url':None ,
        'custom_folder_name':None ,
        'num_file_threads':1 ,
        'manga_date_file_counter_ref':None ,
        }

        for job_details in self .files_for_current_retry_session :
            future =self .retry_thread_pool .submit (self ._execute_single_file_retry ,job_details ,common_ppw_args_for_retry )
            future .add_done_callback (self ._handle_retry_future_result )
            self .active_retry_futures_map [future ]=job_details 
            self .active_retry_futures .append (future )

    def _execute_single_file_retry(self, job_details, common_args):
        """
        Executes a single file download retry attempt. This function is called by the retry thread pool.
        """
        import os
        from datetime import datetime
        from ..core.workers import PostProcessorWorker, FILE_DOWNLOAD_STATUS_SUCCESS, FILE_DOWNLOAD_STATUS_SKIPPED
        from urllib.parse import urlparse
        from ..utils.text_utils import match_folders_from_title
        from ..core.workers import robust_clean_name
        from ..config.constants import (
            STYLE_POST_TITLE, STYLE_ORIGINAL_NAME, STYLE_DATE_BASED,
            STYLE_DATE_POST_TITLE, STYLE_POST_TITLE_GLOBAL_NUMBERING,
            STYLE_POST_ID, STYLE_CUSTOM
        )

        dummy_post_data = job_details
        post_page_url = ""

        # Determine the correct Referer URL (common for both retry types)
        if job_details.get('is_loaded_from_txt'):
            try:
                file_url = job_details.get('file_info', {}).get('url')
                parsed_file_url = urlparse(file_url)
                post_page_url = f"{parsed_file_url.scheme}://{parsed_file_url.netloc}/"
            except Exception:
                post_page_url = "https://kemono.su/"
        else:
            service = job_details.get('service', 'unknown_service')
            user_id = job_details.get('user_id', 'unknown_user')
            post_id = job_details.get('original_post_id_for_log', 'unknown_id')
            api_url_input = job_details.get('api_url_input', '')
            parsed_api_url = urlparse(api_url_input)
            api_domain = parsed_api_url.netloc if parsed_api_url.netloc else self._get_domain_for_service(service)
            post_page_url = f"https://{api_domain}/{service}/user/{user_id}/post/{post_id}"

        # --- NEW LOGIC: Differentiate between loaded files and live session errors ---
        if job_details.get('is_loaded_from_txt'):
            # --- BEHAVIOR FOR LOADED FILES: Recalculate everything from current UI settings ---
            self.log_signal.emit(f"   Retrying loaded file. Recalculating path and name from current UI settings...")

            # 1. Get all current settings and job data
            post_title = job_details.get('post_title', '')
            original_filename = job_details.get('file_info', {}).get('name', 'unknown_file')
            use_subfolders = common_args.get('use_subfolders')
            use_post_subfolders = common_args.get('use_post_subfolders')
            use_date_prefix = common_args.get('use_date_prefix_for_subfolder')
            date_prefix_format = common_args.get('date_prefix_format', 'YYYY-MM-DD {post}')
            manga_mode_active = common_args.get('manga_mode_active')
            manga_filename_style = common_args.get('manga_filename_style')
            custom_format = common_args.get('manga_custom_filename_format', '{published} {title}')
            custom_date_format = common_args.get('manga_custom_date_format', 'YYYY-MM-DD')

            # 2. Recalculate the target folder path
            target_folder_path_for_download = common_args.get('download_root', '')
            if use_subfolders and post_title:
                matched_folders = match_folders_from_title(post_title, common_args.get('known_names', []), common_args.get('unwanted_keywords', set()))
                if matched_folders:
                    target_folder_path_for_download = os.path.join(target_folder_path_for_download, matched_folders[0])
            if use_post_subfolders:
                post_subfolder_name = robust_clean_name(post_title)
                if use_date_prefix:
                    published_date_str = job_details.get('published') or job_details.get('added')
                    if published_date_str:
                        try:
                            dt_obj = datetime.fromisoformat(published_date_str)
                            final_subfolder_name = date_prefix_format.replace("YYYY", dt_obj.strftime("%Y")).replace("MM", dt_obj.strftime("%m")).replace("DD", dt_obj.strftime("%d"))
                            if "{post}" in date_prefix_format:
                                final_subfolder_name = final_subfolder_name.replace("{post}", post_subfolder_name)
                            else:
                                final_subfolder_name = f"{final_subfolder_name} {post_subfolder_name}"
                            post_subfolder_name = final_subfolder_name.strip()
                        except (ValueError, TypeError):
                            post_subfolder_name = f"{published_date_str.split('T')[0]} {post_subfolder_name}"
                target_folder_path_for_download = os.path.join(target_folder_path_for_download, post_subfolder_name)

            # 3. Recalculate the filename based on Renaming Mode
            filename_override_for_download = original_filename
            if manga_mode_active:
                base, ext = os.path.splitext(original_filename)
                if manga_filename_style == STYLE_POST_TITLE:
                    filename_override_for_download = f"{robust_clean_name(post_title)}{ext}"
                elif manga_filename_style == STYLE_CUSTOM:
                    def format_date(date_str):
                        if not date_str or 'NoDate' in date_str: return "NoDate"
                        try:
                            dt_obj = datetime.fromisoformat(date_str)
                            strftime_format = custom_date_format.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
                            return dt_obj.strftime(strftime_format)
                        except (ValueError, TypeError): return date_str.split('T')[0]
                    format_values = { 'id': str(job_details.get('original_post_id_for_log', '')), 'user': str(job_details.get('user_id', '')), 'service': str(job_details.get('service', '')), 'title': post_title, 'name': base, 'added': format_date(job_details.get('added')), 'published': format_date(job_details.get('published')), 'edited': format_date(job_details.get('edited'))}
                    filename_override_for_download = f"{robust_clean_name(custom_format.format(**format_values))}{ext}"
                # Add other renaming styles here if needed...

        else:
            # --- BEHAVIOR FOR LIVE SESSION ERRORS: Use the original, pre-calculated values ---
            self.log_signal.emit(f"   Retrying live session error. Using original path and name.")
            target_folder_path_for_download = job_details['target_folder_path']
            filename_override_for_download = job_details.get('forced_filename_override')
        # --- END OF NEW LOGIC ---

        ppw_init_args = {**common_args, 'post_data': dummy_post_data, 'service': job_details.get('service', 'unknown_service'), 'user_id': job_details.get('user_id', 'unknown_user'), 'api_url_input': job_details.get('api_url_input', '')}
        worker = PostProcessorWorker(**ppw_init_args)

        dl_count, skip_count, filename_saved, original_kept, status, _ = worker._download_single_file(
            file_info=job_details['file_info'],
            target_folder_path=target_folder_path_for_download,
            post_page_url=post_page_url,
            original_post_id_for_log=job_details['original_post_id_for_log'],
            skip_event=None,
            post_title=job_details['post_title'],
            file_index_in_post=job_details['file_index_in_post'],
            num_files_in_this_post=job_details['num_files_in_this_post'],
            forced_filename_override=filename_override_for_download
        )

        is_successful_download = (status == FILE_DOWNLOAD_STATUS_SUCCESS)
        is_resolved_as_skipped = (status == FILE_DOWNLOAD_STATUS_SKIPPED)

        return is_successful_download or is_resolved_as_skipped

    def _handle_retry_future_result (self ,future ):
        self .processed_retry_count +=1 
        was_successful =False 
        try :
            if future .cancelled ():
                self .log_signal .emit ("    A retry task was cancelled.")
            elif future .exception ():
                self .log_signal .emit (f"❌ Retry task worker error: {future .exception ()}")
            else :
                was_successful =future .result ()
                job_details =self .active_retry_futures_map .pop (future ,None )
                if was_successful :
                    self .succeeded_retry_count +=1 
                else :
                    self .failed_retry_count_in_session +=1 
                    if job_details :
                        self .permanently_failed_files_for_dialog .append (job_details )
        except Exception as e :
            self .log_signal .emit (f"❌ Error in _handle_retry_future_result: {e }")
            self .failed_retry_count_in_session +=1 

        progress_percent_retry =(self .processed_retry_count /self .total_files_for_retry *100 )if self .total_files_for_retry >0 else 0 
        self .progress_label .setText (
        self ._tr ("progress_posts_text","Progress: {processed_posts} / {total_posts} posts ({progress_percent:.1f}%)").format (processed_posts =self .processed_retry_count ,total_posts =self .total_files_for_retry ,progress_percent =progress_percent_retry ).replace ("posts","files")+
        f" ({self ._tr ('succeeded_text','Succeeded')}: {self .succeeded_retry_count }, {self ._tr ('failed_text','Failed')}: {self .failed_retry_count_in_session })"
        )

        if self .processed_retry_count >=self .total_files_for_retry :
            if all (f .done ()for f in self .active_retry_futures ):
                QTimer .singleShot (0 ,self ._retry_session_finished )


    def _retry_session_finished (self ):
        self .log_signal .emit ("🏁 Retry session finished.")
        self .log_signal .emit (f"    Summary: {self .succeeded_retry_count } Succeeded, {self .failed_retry_count_in_session } Failed.")

        if self .retry_thread_pool :
            self .retry_thread_pool .shutdown (wait =True )
            self .retry_thread_pool =None 

        if os.path.exists(self.session_file_path):
            try:
                with self.session_lock:
                    with open(self.session_file_path, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    
                    if 'download_state' in session_data:
                        session_data['download_state']['permanently_failed_files'] = self.permanently_failed_files_for_dialog
                    self._save_session_file(session_data)
                    self.log_signal.emit("ℹ️ Session file updated with retry results.")

            except Exception as e:
                self.log_signal.emit(f"⚠️ Could not update session file after retry: {e}")

        if self .external_link_download_thread and not self .external_link_download_thread .isRunning ():
            self .external_link_download_thread .deleteLater ()
            self .external_link_download_thread =None 

        self .active_retry_futures .clear ()
        self .active_retry_futures_map .clear ()
        self .files_for_current_retry_session .clear ()

        if self .permanently_failed_files_for_dialog :
            self .log_signal .emit (f"🆘 {self ._tr ('error_button_text','Error')} button enabled. {len (self .permanently_failed_files_for_dialog )} file(s) ultimately failed and can be viewed.")

        self .set_ui_enabled (not self ._is_download_active ())
        if self .cancel_btn :self .cancel_btn .setText (self ._tr ("cancel_button_text","❌ Cancel & Reset UI"))
        self .progress_label .setText (
        f"{self ._tr ('retry_finished_text','Retry Finished')}. "
        f"{self ._tr ('succeeded_text','Succeeded')}: {self .succeeded_retry_count }, "
        f"{self ._tr ('failed_text','Failed')}: {self .failed_retry_count_in_session }. "
        f"{self ._tr ('ready_for_new_task_text','Ready for new task.')}")
        self .file_progress_label .setText ("")
        if self .pause_event :self .pause_event .clear ()
        self .is_paused =False 

    def toggle_active_log_view (self ):
        if self .current_log_view =='progress':
            self .current_log_view ='missed_character'
            if self .log_view_stack :self .log_view_stack .setCurrentIndex (1 )
            if self .log_verbosity_toggle_button :
                self .log_verbosity_toggle_button .setText (self .CLOSED_EYE_ICON )
                self .log_verbosity_toggle_button .setToolTip ("Current View: Missed Character Log. Click to switch to Progress Log.")
            if self .progress_log_label :self .progress_log_label .setText (self ._tr ("missed_character_log_label_text","🚫 Missed Character Log:"))
        else :
            self .current_log_view ='progress'
            if self .log_view_stack :self .log_view_stack .setCurrentIndex (0 )
            if self .log_verbosity_toggle_button :
                self .log_verbosity_toggle_button .setText (self .EYE_ICON )
                self .log_verbosity_toggle_button .setToolTip ("Current View: Progress Log. Click to switch to Missed Character Log.")
            if self .progress_log_label :self .progress_log_label .setText (self ._tr ("progress_log_label_text","📜 Progress Log:"))

    def reset_application_state(self):
        self.log_signal.emit("🔄 Resetting application state to defaults...")

        if self._is_download_active():
            self.log_signal.emit("   Cancelling all active background tasks for reset...")
            self.cancellation_event.set() 

            if self.download_thread and self.download_thread.isRunning():
                self.download_thread.requestInterruption()
            if self.thread_pool:
                self.thread_pool.shutdown(wait=False, cancel_futures=True)
                self.thread_pool = None
            if self.external_link_download_thread and self.external_link_download_thread.isRunning():
                self.external_link_download_thread.cancel()
            if hasattr(self, 'retry_thread_pool') and self.retry_thread_pool:
                self.retry_thread_pool.shutdown(wait=False, cancel_futures=True)
                self.retry_thread_pool = None
        
        self.cancellation_event.clear()

        if self.pause_event:
            self.pause_event.clear()
        self.is_paused = False

        self._clear_session_file()
        self._perform_soft_ui_reset()
        self._load_saved_download_location()
        self.main_log_output.clear()
        self.external_log_output.clear()
        if self.missed_character_log_output:
            self.missed_character_log_output.clear()

        self.current_log_view = 'progress'
        if self.log_view_stack:
            self.log_view_stack.setCurrentIndex(0)
        if self.progress_log_label:
            self.progress_log_label.setText(self._tr("progress_log_label_text", "📜 Progress Log:"))
        if self.log_verbosity_toggle_button:
            self.log_verbosity_toggle_button.setText(self.EYE_ICON)
            self.log_verbosity_toggle_button.setToolTip("Current View: Progress Log. Click to switch to Missed Character Log.")
        self.external_link_queue.clear()
        self.extracted_links_cache = []
        self._is_processing_external_link_queue = False
        self._current_link_post_title = None
        self.progress_label.setText(self._tr("progress_idle_text", "Progress: Idle"))
        self.file_progress_label.setText("")
        with self.downloaded_files_lock:
            self.downloaded_files.clear()
        with self.downloaded_file_hashes_lock:
            self.downloaded_file_hashes.clear()
        self.missed_title_key_terms_count.clear()
        self.missed_title_key_terms_examples.clear()
        self.logged_summary_for_key_term.clear()
        self.already_logged_bold_key_terms.clear()
        self.missed_key_terms_buffer.clear()
        self.favorite_download_queue.clear()
        self.only_links_log_display_mode = LOG_DISPLAY_LINKS
        self.mega_download_log_preserved_once = False
        self.permanently_failed_files_for_dialog.clear()
        self._update_error_button_count()
        self.favorite_download_scope = FAVORITE_SCOPE_SELECTED_LOCATION
        self._update_favorite_scope_button_text()
        self.retryable_failed_files_info.clear()
        self.cancellation_message_logged_this_session = False
        self.is_processing_favorites_queue = False
        self.total_posts_to_process = 0
        self.processed_posts_count = 0
        self.download_counter = 0
        self.skip_counter = 0
        self.all_kept_original_filenames = []
        self.is_paused = False
        self.is_fetcher_thread_running = False
        self.interrupted_session_data = None
        self.is_restore_pending = False

        self.active_update_profile = None
        self.settings.setValue(MANGA_FILENAME_STYLE_KEY, self.manga_filename_style)
        self.settings.setValue(SKIP_WORDS_SCOPE_KEY, self.skip_words_scope)
        self.settings.sync()
        self._update_manga_filename_style_button_text()
        self.update_ui_for_manga_mode(self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False)
        self.is_fetching_only = False
        self.fetched_posts_for_download = []
        self.is_ready_to_download_fetched = False 

        self.set_ui_enabled(True)
        self.log_signal.emit("✅ Application fully reset. Ready for new download.")
        self.is_processing_favorites_queue = False
        self.current_processing_favorite_item_info = None
        self.favorite_download_queue.clear()
        self.interrupted_session_data = None
        self.is_restore_pending = False
        self.last_link_input_text_for_queue_sync = ""
        
    def _show_feature_guide (self ):
        steps_content_keys =[
        ("help_guide_step1_title","help_guide_step1_content"),
        ("help_guide_step2_title","help_guide_step2_content"),
        ("help_guide_step3_title","help_guide_step3_content"),
        ("help_guide_step4_title","help_guide_step4_content"),
        ("help_guide_step5_title","help_guide_step5_content"),
        ("help_guide_step6_title","help_guide_step6_content"),
        ("help_guide_step7_title","help_guide_step7_content"),
        ("help_guide_step8_title","help_guide_step8_content"),
        ("help_guide_step9_title","help_guide_step9_content"),
        ("column_header_post_title","Post Title"),
        ("column_header_date_uploaded","Date Uploaded"),
        ]

        steps =[
        ]
        for title_key ,content_key in steps_content_keys :
            title =self ._tr (title_key ,title_key )
            content =self ._tr (content_key ,f"Content for {content_key } not found.")
            steps .append ((title ,content ))

        guide_dialog =HelpGuideDialog (steps ,self )
        guide_dialog .exec_ ()

    def prompt_add_character (self ,character_name ):
        global KNOWN_NAMES 
        reply =QMessageBox .question (self ,"Add Filter Name to Known List?",f"The name '{character_name }' was encountered or used as a filter.\nIt's not in your known names list (used for folder suggestions).\nAdd it now?",QMessageBox .Yes |QMessageBox .No ,QMessageBox .Yes )
        result =(reply ==QMessageBox .Yes )
        if result :
            if self .add_new_character (name_to_add =character_name ,
            is_group_to_add =False ,
            aliases_to_add =[character_name ],
            suppress_similarity_prompt =False ):
                self .log_signal .emit (f"✅ Added '{character_name }' to known names via background prompt.")
            else :result =False ;self .log_signal .emit (f"ℹ️ Adding '{character_name }' via background prompt was declined, failed, or a similar name conflict was not overridden.")
        self .character_prompt_response_signal .emit (result )

    def receive_add_character_result (self ,result ):
        with QMutexLocker (self .prompt_mutex ):self ._add_character_response =result 
        self .log_signal .emit (f"    Main thread received character prompt response: {'Action resulted in addition/confirmation'if result else 'Action resulted in no addition/declined'}")

    def _update_multipart_toggle_button_text(self):
        if hasattr(self, 'multipart_toggle_button'):
            if self.allow_multipart_download_setting:
                scope_text = self.multipart_scope.capitalize()
                self.multipart_toggle_button.setText(self._tr("multipart_on_button_text", f"Multi-part: {scope_text}"))
                self.multipart_toggle_button.setToolTip(self._tr("multipart_on_button_tooltip", f"Multipart download is ON. Applied to: {scope_text} files. Click to change."))
            else:
                self.multipart_toggle_button.setText(self._tr("multipart_off_button_text", "Multi-part: OFF"))
                self.multipart_toggle_button.setToolTip(self._tr("multipart_off_button_tooltip", "Multipart download is OFF. Click to enable and set options."))

    def _update_error_button_count(self):
        """Updates the Error button text to show the count of failed files."""
        if not hasattr(self, 'error_btn'):
            return

        count = len(self.permanently_failed_files_for_dialog)
        base_text = self._tr("error_button_text", "Error")

        if count > 0:
            self.error_btn.setText(f"({count}) {base_text}")
        else:
            self.error_btn.setText(base_text)

    def _toggle_multipart_mode(self):
        """
        Opens the Multipart Scope Dialog and updates settings based on user choice.
        """
        current_scope = self.multipart_scope if self.allow_multipart_download_setting else 'both'
        dialog = MultipartScopeDialog(current_scope, self.multipart_parts_count, self.multipart_min_size_mb, self)
        
        if dialog.exec_() == QDialog.Accepted:
            self.multipart_scope = dialog.get_selected_scope()
            self.multipart_parts_count = dialog.get_selected_parts()
            self.multipart_min_size_mb = dialog.get_selected_min_size() # Get the new value
            self.allow_multipart_download_setting = True
            self.log_signal.emit(f"ℹ️ Multi-part download enabled: Scope='{self.multipart_scope.capitalize()}', Parts={self.multipart_parts_count}, Min Size={self.multipart_min_size_mb} MB")
        else:
            self.allow_multipart_download_setting = False
            self.log_signal.emit("ℹ️ Multi-part download setting remains OFF.")
            
        self._update_multipart_toggle_button_text()
        self.settings.setValue(ALLOW_MULTIPART_DOWNLOAD_KEY, self.allow_multipart_download_setting)

    def _open_known_txt_file (self ):
        if not os .path .exists (self .config_file ):
            QMessageBox .warning (self ,"File Not Found",
            f"The file 'Known.txt' was not found at:\n{self .config_file }\n\n"
            "It will be created automatically when you add a known name or close the application.")
            self .log_signal .emit (f"ℹ️ 'Known.txt' not found at {self .config_file }. It will be created later.")
            return 

        try :
            if sys .platform =="win32":
                os .startfile (self .config_file )
            elif sys .platform =="darwin":
                subprocess .call (['open',self .config_file ])
            else :
                subprocess .call (['xdg-open',self .config_file ])
            self .log_signal .emit (f"ℹ️ Attempted to open '{os .path .basename (self .config_file )}' with the default editor.")
        except FileNotFoundError :
            QMessageBox .critical (self ,"Error",f"Could not find '{os .path .basename (self .config_file )}' at {self .config_file } to open it.")
            self .log_signal .emit (f"❌ Error: '{os .path .basename (self .config_file )}' not found at {self .config_file } when trying to open.")
        except Exception as e :
            QMessageBox .critical (self ,"Error Opening File",f"Could not open '{os .path .basename (self .config_file )}':\n{e }")
            self .log_signal .emit (f"❌ Error opening '{os .path .basename (self .config_file )}': {e }")

    def _show_add_to_filter_dialog (self ):
        global KNOWN_NAMES 
        if not KNOWN_NAMES :
            QMessageBox .information (self ,"No Known Names","Your 'Known.txt' list is empty. Add some names first.")
            return 

        dialog = KnownNamesFilterDialog(KNOWN_NAMES, self)
        if dialog .exec_ ()==QDialog .Accepted :
            selected_entries =dialog .get_selected_entries ()
            if selected_entries :
                self ._add_names_to_character_filter_input (selected_entries )

    def _add_names_to_character_filter_input (self ,selected_entries ):
        """
        Adds the selected known name entries to the character filter input field.
        """
        if not selected_entries :
            return 

        names_to_add_str_list =[]
        for entry in selected_entries :
            if entry .get ("is_group"):
                aliases_str =", ".join (entry .get ("aliases",[]))
                names_to_add_str_list .append (f"({aliases_str })~")
            else :
                names_to_add_str_list .append (entry .get ("name",""))

        names_to_add_str_list =[s for s in names_to_add_str_list if s ]

        if not names_to_add_str_list :
            return 

        current_filter_text =self .character_input .text ().strip ()
        new_text_to_append =", ".join (names_to_add_str_list )

        self .character_input .setText (f"{current_filter_text }, {new_text_to_append }"if current_filter_text else new_text_to_append )
        self .log_signal .emit (f"ℹ️ Added to character filter: {new_text_to_append }")

    def _update_favorite_scope_button_text (self ):
        if not hasattr (self ,'favorite_scope_toggle_button')or not self .favorite_scope_toggle_button :
            return 
        if self .favorite_download_scope ==FAVORITE_SCOPE_SELECTED_LOCATION :
            self .favorite_scope_toggle_button .setText (self ._tr ("favorite_scope_selected_location_text","Scope: Selected Location"))

        elif self .favorite_download_scope ==FAVORITE_SCOPE_ARTIST_FOLDERS :
            self .favorite_scope_toggle_button .setText (self ._tr ("favorite_scope_artist_folders_text","Scope: Artist Folders"))

        else :
            self .favorite_scope_toggle_button .setText (self ._tr ("favorite_scope_unknown_text","Scope: Unknown"))


    def _cycle_favorite_scope (self ):
        if self .favorite_download_scope ==FAVORITE_SCOPE_SELECTED_LOCATION :
            self .favorite_download_scope =FAVORITE_SCOPE_ARTIST_FOLDERS 
        else :
            self .favorite_download_scope =FAVORITE_SCOPE_SELECTED_LOCATION 
        self ._update_favorite_scope_button_text ()
        self .log_signal .emit (f"ℹ️ Favorite download scope changed to: '{self .favorite_download_scope }'")

    def _check_for_updates(self):
        """Phase 1 of Update: Fetches all posts, compares, and prompts the user for confirmation."""
        self.log_signal.emit("🔄 Checking for updates...")
        
        update_url = self.active_update_profile['creator_url'][0]
        processed_ids_from_profile = set(self.active_update_profile['processed_post_ids'])
        self.log_signal.emit(f"   Checking URL: {update_url}")
        
        self.set_ui_enabled(False)
        self.progress_label.setText(self._tr("progress_fetching_all_posts", "Progress: Fetching all post pages..."))
        QCoreApplication.processEvents()

        try:
            post_generator = download_from_api(
                api_url_input=update_url,
                logger=lambda msg: None, # Suppress noisy logs during check
                cancellation_event=self.cancellation_event,
                pause_event=self.pause_event,
                use_cookie=self.use_cookie_checkbox.isChecked(),
                cookie_text=self.cookie_text_input.text(),
                selected_cookie_file=self.selected_cookie_filepath,
                app_base_dir=self.app_base_dir,
                processed_post_ids=processed_ids_from_profile
            )
            all_posts_from_api = [post for batch in post_generator for post in batch]
        except Exception as e:
            self.log_signal.emit(f"❌ Failed to fetch posts during update check: {e}")
            self.download_finished(0, 0, False, [])
            return

        self.log_signal.emit(f"   Fetched a total of {len(all_posts_from_api)} posts from the server.")
        
        # CORRECTED LINE: Assign the list directly without re-filtering
        self.new_posts_for_update = all_posts_from_api
        
        if not self.new_posts_for_update:
            self.log_signal.emit("✅ Creator is up to date! No new posts found.")
            QMessageBox.information(self, "Up to Date", "No new posts were found for this creator.")
            self._clear_update_selection()
            self.set_ui_enabled(True)
            self.progress_label.setText(self._tr("progress_idle_text", "Progress: Idle"))
            return

        self.log_signal.emit(f"   Found {len(self.new_posts_for_update)} new post(s). Waiting for user confirmation to download.")
        self.progress_label.setText(f"Found {len(self.new_posts_for_update)} new post(s). Ready to download.")
        self._update_button_states_and_connections() 

    def _start_confirmed_update_download(self):
        """Phase 2 of Update: Starts the download of posts found during the check."""
        self.log_signal.emit(f"✅ User confirmed. Starting download for {len(self.new_posts_for_update)} new post(s).")
        self.main_log_output.clear()
        
        from src.config.constants import FOLDER_NAME_STOP_WORDS
        update_url = self.active_update_profile['creator_url'][0]
        service, user_id, _ = extract_post_info(update_url)

        base_download_dir_from_ui = self.dir_input.text().strip()
        self.log_signal.emit(f"   Update session will save to base folder: {base_download_dir_from_ui}")

        raw_character_filters_text = self.character_input.text().strip()
        parsed_character_filter_objects = self._parse_character_filters(raw_character_filters_text)

        try:
            num_threads_from_gui = int(self.thread_count_input.text().strip())
        except ValueError:
            num_threads_from_gui = 1
        effective_num_file_threads_per_worker = max(1, min(num_threads_from_gui, MAX_FILE_THREADS_PER_POST_OR_WORKER))

        # Logic to get folder ignore words if no character filters are used
        creator_folder_ignore_words_for_run = None
        # The 'not self.active_update_profile.get('post_id')' part is a simple way to check if it's a full creator page
        is_full_creator_download = not self.active_update_profile.get('post_id')
        if is_full_creator_download and not parsed_character_filter_objects:
            creator_folder_ignore_words_for_run = CREATOR_DOWNLOAD_DEFAULT_FOLDER_IGNORE_WORDS

        args_template = {
            'api_url_input': update_url, 
            'download_root': base_download_dir_from_ui,
            'override_output_dir': None,
            'known_names': list(KNOWN_NAMES), 
            'filter_character_list': parsed_character_filter_objects,
            'emitter': self.worker_to_gui_queue, 
            'unwanted_keywords': FOLDER_NAME_STOP_WORDS,
            'filter_mode': self.get_filter_mode(), 
            'skip_zip': self.skip_zip_checkbox.isChecked(),
            'use_subfolders': self.use_subfolders_checkbox.isChecked(),
            'use_post_subfolders': self.use_subfolder_per_post_checkbox.isChecked(),
            'target_post_id_from_initial_url': None, 
            'custom_folder_name': self.custom_folder_input.text().strip(),
            'compress_images': self.compress_images_checkbox.isChecked(),
            'download_thumbnails': self.download_thumbnails_checkbox.isChecked(),
            'service': service, 'user_id': user_id, 'pause_event': self.pause_event,
            'cancellation_event': self.cancellation_event, 
            'downloaded_files': self.downloaded_files,
            'downloaded_file_hashes': self.downloaded_file_hashes,
            'downloaded_files_lock': self.downloaded_files_lock,
            'downloaded_file_hashes_lock': self.downloaded_file_hashes_lock,
            'dynamic_character_filter_holder': self.dynamic_character_filter_holder,
            'skip_words_list': [part.strip().lower() for part in self.skip_words_input.text().strip().split(',') if part.strip() and not part.strip().startswith('[')],
            'skip_file_size_mb': next((int(re.search(r'\[(\d+)\]', part).group(1)) for part in self.skip_words_input.text().strip().split(',') if re.fullmatch(r'\[\d+\]', part.strip())), None),
            'skip_words_scope': self.get_skip_words_scope(), 
            'show_external_links': self.external_links_checkbox.isChecked(),
            'extract_links_only': self.radio_only_links.isChecked(), 
            'skip_current_file_flag': None,
            'manga_mode_active': self.manga_mode_checkbox.isChecked(), 
            'manga_filename_style': self.manga_filename_style,
            'char_filter_scope': self.get_char_filter_scope(),
            'remove_from_filename_words_list': [word.strip() for word in self.remove_from_filename_input.text().strip().split(',') if word.strip()],
            'allow_multipart_download': self.allow_multipart_download_setting, 
            'cookie_text': self.cookie_text_input.text(),
            'use_cookie': self.use_cookie_checkbox.isChecked(),
            'selected_cookie_file': self.selected_cookie_filepath, 
            'app_base_dir': self.app_base_dir,
            'manga_date_prefix': self.manga_date_prefix_input.text().strip(), 
            'manga_date_file_counter_ref': None,
            'scan_content_for_images': self.scan_content_images_checkbox.isChecked(),
            
            'creator_download_folder_ignore_words': creator_folder_ignore_words_for_run,
            'num_file_threads_for_worker': effective_num_file_threads_per_worker,
            'multipart_scope': 'files',
            'multipart_parts_count': 8,
            'multipart_min_size_mb': 100,

            'manga_global_file_counter_ref': None,
            'use_date_prefix_for_subfolder': self.date_prefix_checkbox.isChecked(),
            'keep_in_post_duplicates': self.keep_duplicates_checkbox.isChecked(),
            'keep_duplicates_mode': self.keep_duplicates_mode, 
            'keep_duplicates_limit': self.keep_duplicates_limit,
            'downloaded_hash_counts': self.downloaded_hash_counts, 
            'downloaded_hash_counts_lock': self.downloaded_hash_counts_lock,
            'session_file_path': self.session_file_path, 
            'session_lock': self.session_lock,
            'text_only_scope': self.more_filter_scope, 
            'text_export_format': self.text_export_format,
            'single_pdf_mode': self.single_pdf_setting, 
            'project_root_dir': self.app_base_dir,
            'processed_post_ids': list(self.active_update_profile['processed_post_ids'])
        }

        num_threads = int(self.thread_count_input.text()) if self.use_multithreading_checkbox.isChecked() else 1
        self.thread_pool = ThreadPoolExecutor(max_workers=num_threads, thread_name_prefix='UpdateWorker_')
        self.total_posts_to_process = len(self.new_posts_for_update)
        self.processed_posts_count = 0
        self.overall_progress_signal.emit(self.total_posts_to_process, 0)
        
        ppw_expected_keys = list(PostProcessorWorker.__init__.__code__.co_varnames)[1:]
        
        for post_data in self.new_posts_for_update:
            self._submit_post_to_worker_pool(
                post_data, args_template, 1, self.worker_to_gui_queue, ppw_expected_keys, {}
            )
        return True

    def _show_empty_popup (self ):
        """Creates and shows the empty popup dialog."""
        if self.is_restore_pending:
            QMessageBox.information(self, self._tr("restore_pending_title", "Restore Pending"),
                                    self._tr("restore_pending_message_creator_selection",
                                             "Please 'Restore Download' or 'Discard Session' before selecting new creators."))
            return
        dialog = EmptyPopupDialog(self.app_base_dir, self)
        if dialog.exec_() == QDialog.Accepted:
            if dialog.update_profile_data:
                self.active_update_profile = dialog.update_profile_data
                self.link_input.setText(dialog.update_creator_name)
                self.favorite_download_queue.clear()
                
                if 'settings' in self.active_update_profile:
                    self.log_signal.emit(f"ℹ️ Applying saved settings from '{dialog.update_creator_name}' profile...")
                    self._load_ui_from_settings_dict(self.active_update_profile['settings'])
                    self.log_signal.emit("   Settings restored.")

                self.log_signal.emit(f"ℹ️ Loaded profile for '{dialog.update_creator_name}'. Click 'Check For Updates' to continue.")
                self._update_button_states_and_connections()
          
            elif hasattr(dialog, 'selected_creators_for_queue') and dialog.selected_creators_for_queue:
                self.active_update_profile = None
                self.favorite_download_queue.clear()

                for creator_data in dialog.selected_creators_for_queue:
                    service = creator_data.get('service')
                    creator_id = creator_data.get('id')
                    creator_name = creator_data.get('name', 'Unknown Creator')
                    domain = dialog._get_domain_for_service(service)

                    if service and creator_id:
                        url = f"https://{domain}/{service}/user/{creator_id}"
                        queue_item = {
                            'url': url,
                            'name': creator_name,
                            'name_for_folder': creator_name,
                            'type': 'creator_popup_selection',
                            'scope_from_popup': dialog.current_scope_mode
                        }
                        self.favorite_download_queue.append(queue_item)

                if self.favorite_download_queue:
                    if hasattr(self, 'link_input'):
                        creator_names = [item['name'] for item in self.favorite_download_queue]
                        display_text = ", ".join(creator_names)
                        self.link_input.setText(display_text)
                    
                    self.log_signal.emit(f"ℹ️ {len(self.favorite_download_queue)} creators added to download queue from popup. Click 'Start Download' to process.")
                    if hasattr(self, 'link_input'):
                        self.last_link_input_text_for_queue_sync = self.link_input.text()

                # --- START: MODIFIED LOGIC ---
                # Manually trigger the UI update now that the queue is populated and the dialog is closed.
                self.update_ui_for_manga_mode(self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False)
                # --- END: MODIFIED LOGIC ---

    def _load_saved_cookie_settings(self):
        """Loads and applies saved cookie settings on startup."""
        try:
            use_cookie_saved = self.settings.value(USE_COOKIE_KEY, False, type=bool)
            cookie_content_saved = self.settings.value(COOKIE_TEXT_KEY, "", type=str)

            if use_cookie_saved and cookie_content_saved:
                self.use_cookie_checkbox.setChecked(True)
                self.cookie_text_input.setText(cookie_content_saved)
                
                # Check if the saved content is a file path and update UI accordingly
                if os.path.exists(cookie_content_saved):
                    self.selected_cookie_filepath = cookie_content_saved
                    self.cookie_text_input.setReadOnly(True)
                    self._update_cookie_input_placeholders_and_tooltips()
                
                self.log_signal.emit(f"ℹ️ Loaded saved cookie settings.")
        except Exception as e:
            self.log_signal.emit(f"⚠️ Could not load saved cookie settings: {e}")

    def _show_favorite_artists_dialog (self ):
        if self ._is_download_active ()or self .is_processing_favorites_queue :
            QMessageBox .warning (self ,"Busy","Another download operation is already in progress.")
            return 

        cookies_config ={
        'use_cookie':self .use_cookie_checkbox .isChecked ()if hasattr (self ,'use_cookie_checkbox')else False ,
        'cookie_text':self .cookie_text_input .text ()if hasattr (self ,'cookie_text_input')else "",
        'selected_cookie_file':self .selected_cookie_filepath ,
        'app_base_dir':self .app_base_dir 
        }

        dialog =FavoriteArtistsDialog (self ,cookies_config )
        if dialog .exec_ ()==QDialog .Accepted :
            selected_artists =dialog .get_selected_artists ()
            if selected_artists :
                if len (selected_artists )>1 and self .link_input :
                    display_names =", ".join ([artist ['name']for artist in selected_artists ])
                    if self .link_input :
                        self .link_input .clear ()
                        self .link_input .setPlaceholderText (f"{len (selected_artists )} favorite artists selected for download queue.")
                    self .log_signal .emit (f"ℹ️ Multiple favorite artists selected. Displaying names: {display_names }")
                elif len (selected_artists )==1 :
                    self .link_input .setText (selected_artists [0 ]['url'])
                    self .log_signal .emit (f"ℹ️ Single favorite artist selected: {selected_artists [0 ]['name']}")

                self .log_signal .emit (f"ℹ️ Queuing {len (selected_artists )} favorite artist(s) for download.")
                for artist_data in selected_artists :
                    self .favorite_download_queue .append ({'url':artist_data ['url'],'name':artist_data ['name'],'name_for_folder':artist_data ['name'],'type':'artist'})

                if not self .is_processing_favorites_queue :
                    self ._process_next_favorite_download ()
            else :
                self .log_signal .emit ("ℹ️ No favorite artists were selected for download.")
                QMessageBox .information (self ,
                self ._tr ("fav_artists_no_selection_title","No Selection"),
                self ._tr ("fav_artists_no_selection_message","Please select at least one artist to download."))
        else :
            self .log_signal .emit ("ℹ️ Favorite artists selection cancelled.")

    def _show_favorite_posts_dialog (self ):
        if self ._is_download_active ()or self .is_processing_favorites_queue :
            QMessageBox .warning (self ,"Busy","Another download operation is already in progress.")
            return 

        cookies_config ={
        'use_cookie':self .use_cookie_checkbox .isChecked ()if hasattr (self ,'use_cookie_checkbox')else False ,
        'cookie_text':self .cookie_text_input .text ()if hasattr (self ,'cookie_text_input')else "",
        'selected_cookie_file':self .selected_cookie_filepath ,
        'app_base_dir':self .app_base_dir 
        }
        global KNOWN_NAMES 

        target_domain_preference_for_fetch =None 

        if cookies_config['use_cookie']:
            self.log_signal.emit("Favorite Posts: 'Use Cookie' is checked. Determining target domain...")
            
            # --- Kemono Check with Fallback ---
            kemono_cookies = prepare_cookies_for_request(
                cookies_config['use_cookie'], cookies_config['cookie_text'], cookies_config['selected_cookie_file'],
                cookies_config['app_base_dir'], lambda msg: self.log_signal.emit(f"[FavPosts Cookie Check] {msg}"),
                target_domain="kemono.cr"
            )
            if not kemono_cookies:
                self.log_signal.emit("  ↳ No cookies for kemono.cr, trying fallback kemono.su...")
                kemono_cookies = prepare_cookies_for_request(
                    cookies_config['use_cookie'], cookies_config['cookie_text'], cookies_config['selected_cookie_file'],
                    cookies_config['app_base_dir'], lambda msg: self.log_signal.emit(f"[FavPosts Cookie Check] {msg}"),
                    target_domain="kemono.su"
                )

            # --- Coomer Check with Fallback ---
            coomer_cookies = prepare_cookies_for_request(
                cookies_config['use_cookie'], cookies_config['cookie_text'], cookies_config['selected_cookie_file'],
                cookies_config['app_base_dir'], lambda msg: self.log_signal.emit(f"[FavPosts Cookie Check] {msg}"),
                target_domain="coomer.st"
            )
            if not coomer_cookies:
                self.log_signal.emit("  ↳ No cookies for coomer.st, trying fallback coomer.su...")
                coomer_cookies = prepare_cookies_for_request(
                    cookies_config['use_cookie'], cookies_config['cookie_text'], cookies_config['selected_cookie_file'],
                    cookies_config['app_base_dir'], lambda msg: self.log_signal.emit(f"[FavPosts Cookie Check] {msg}"),
                    target_domain="coomer.su"
                )

            kemono_ok = bool(kemono_cookies)
            coomer_ok = bool(coomer_cookies)

            if kemono_ok and not coomer_ok:
                target_domain_preference_for_fetch = "kemono.cr"
                self.log_signal.emit("  ↳ Only Kemono cookies loaded. Will fetch favorites from Kemono.cr only.")
            elif coomer_ok and not kemono_ok:
                target_domain_preference_for_fetch = "coomer.st"
                self.log_signal.emit("  ↳ Only Coomer cookies loaded. Will fetch favorites from Coomer.st only.")
            elif kemono_ok and coomer_ok:
                target_domain_preference_for_fetch = None
                self.log_signal.emit("  ↳ Cookies for both Kemono and Coomer loaded. Will attempt to fetch from both.")
            else:
                self.log_signal.emit("  ↳ No valid cookies loaded for Kemono.cr or Coomer.st.")
                cookie_help_dialog = CookieHelpDialog(self, self)
                cookie_help_dialog.exec_()
                return
        else :
            self .log_signal .emit ("Favorite Posts: 'Use Cookie' is NOT checked. Cookies are required.")
            cookie_help_dialog =CookieHelpDialog (self ,self )
            cookie_help_dialog .exec_ ()
            return 

        dialog =FavoritePostsDialog (self ,cookies_config ,KNOWN_NAMES ,target_domain_preference_for_fetch )
        if dialog .exec_ ()==QDialog .Accepted :
            selected_posts =dialog .get_selected_posts ()
            if selected_posts :
                self .log_signal .emit (f"ℹ️ Queuing {len (selected_posts )} favorite post(s) for download.")
                for post_data in selected_posts :
                    domain =self ._get_domain_for_service (post_data ['service'])
                    direct_post_url =f"https://{domain }/{post_data ['service']}/user/{str (post_data ['creator_id'])}/post/{str (post_data ['post_id'])}"

                    queue_item ={
                    'url':direct_post_url ,
                    'name':post_data ['title'],
                    'name_for_folder':post_data ['creator_name_resolved'],
                    'type':'post'
                    }
                    self .favorite_download_queue .append (queue_item )

                if not self .is_processing_favorites_queue :
                    self ._process_next_favorite_download ()
            else :
                self .log_signal .emit ("ℹ️ No favorite posts were selected for download.")
        else :
            self .log_signal .emit ("ℹ️ Favorite posts selection cancelled.")

    def _process_next_favorite_download(self):

        if self.favorite_download_queue and not self.is_processing_favorites_queue:
            manga_mode_is_checked = self.manga_mode_checkbox.isChecked() if self.manga_mode_checkbox else False
            char_filter_is_empty = not self.character_input.text().strip()
            extract_links_only = (self.radio_only_links and self.radio_only_links.isChecked())

            if manga_mode_is_checked and char_filter_is_empty and not extract_links_only:
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowTitle("Renaming Mode Filter Warning")
                msg_box.setText(
                    "Renaming Mode is enabled, but 'Filter by Character(s)' is empty.\n\n"
                    "This is a one-time warning for this entire batch of downloads.\n\n"
                    "Proceeding without a filter may result in generic filenames and folders.\n\n"
                    "Proceed with the entire batch?"
                )
                proceed_button = msg_box.addButton("Proceed Anyway", QMessageBox.AcceptRole)
                cancel_button = msg_box.addButton("Cancel Entire Batch", QMessageBox.RejectRole)
                msg_box.exec_()
                if msg_box.clickedButton() == cancel_button:
                    self.log_signal.emit("❌ Entire favorite queue cancelled by user at Renaming Mode warning.")
                    self.favorite_download_queue.clear()
                    self.is_processing_favorites_queue = False
                    self.set_ui_enabled(True)
                    return # Stop processing the queue

        if self ._is_download_active ():
            self .log_signal .emit ("ℹ️ Waiting for current download to finish before starting next favorite.")
            return 
        if not self .favorite_download_queue :
            if self .is_processing_favorites_queue :
                self .is_processing_favorites_queue =False 
                item_type_log ="item"
                if hasattr (self ,'current_processing_favorite_item_info')and self .current_processing_favorite_item_info :
                    item_type_log =self .current_processing_favorite_item_info .get ('type','item')
                self .log_signal .emit (f"✅ All {item_type_log } downloads from favorite queue have been processed.")
                self .set_ui_enabled (True )
            return 
        if not self .is_processing_favorites_queue :
            self .is_processing_favorites_queue =True 
        self .current_processing_favorite_item_info =self .favorite_download_queue .popleft ()
        next_url =self .current_processing_favorite_item_info ['url']
        item_display_name =self .current_processing_favorite_item_info .get ('name','Unknown Item')

        # --- START: MODIFIED SECTION ---
        # Get the type of item from the queue to help start_download make smarter decisions.
        item_type = self.current_processing_favorite_item_info.get('type', 'artist')
        self.log_signal.emit(f"▶️ Processing next favorite from queue ({item_type}): '{item_display_name}' ({next_url})")

        override_dir = None
        item_scope = self.current_processing_favorite_item_info.get('scope_from_popup')
        if item_scope is None:
            item_scope = self.favorite_download_scope

        main_download_dir = self.dir_input.text().strip()

        should_create_artist_folder = False
        if item_type == 'creator_popup_selection' and item_scope == EmptyPopupDialog.SCOPE_CREATORS:
            should_create_artist_folder = True
        elif item_type != 'creator_popup_selection' and self.favorite_download_scope == FAVORITE_SCOPE_ARTIST_FOLDERS:
            should_create_artist_folder = True

        if should_create_artist_folder and main_download_dir:
            folder_name_key = self.current_processing_favorite_item_info.get('name_for_folder', 'Unknown_Folder')
            item_specific_folder_name = clean_folder_name(folder_name_key)
            override_dir = os.path.normpath(os.path.join(main_download_dir, item_specific_folder_name))
            self.log_signal.emit(f"    Scope requires artist folder. Target directory: '{override_dir}'")

        # Pass the item_type to the start_download function
        success_starting_download = self.start_download(
            direct_api_url=next_url,
            override_output_dir=override_dir,
            is_continuation=True,
            item_type_from_queue=item_type
        )
        # --- END: MODIFIED SECTION ---

        if not success_starting_download:
            self.log_signal.emit(f"⚠️ Failed to initiate download for '{item_display_name}'. Skipping and moving to the next item in queue.")
            # Use a QTimer to avoid deep recursion and correctly move to the next item.
            QTimer.singleShot(100, self._process_next_favorite_download)

class DiscordDownloadThread(QThread):
    """A dedicated QThread for handling all official Discord downloads."""
    progress_signal = pyqtSignal(str)
    progress_label_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int, bool, list)

    def __init__(self, mode, session, token, output_dir, server_id, channel_id, url, limit=None, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.session = session
        self.token = token
        self.output_dir = output_dir
        self.server_id = server_id
        self.channel_id = channel_id
        self.api_url = url
        self.message_limit = limit

        self.is_cancelled = False
        self.is_paused = False

    def run(self):
        if self.mode == 'pdf':
            self._run_pdf_creation()
        else:
            self._run_file_download()

    def cancel(self):
        self.progress_signal.emit("   Cancellation signal received by Discord thread.")
        self.is_cancelled = True

    def pause(self):
        self.progress_signal.emit("   Pausing Discord download...")
        self.is_paused = True

    def resume(self):
        self.progress_signal.emit("   Resuming Discord download...")
        self.is_paused = False

    def _check_events(self):
        if self.is_cancelled:
            return True
        while self.is_paused:
            time.sleep(0.5)
            if self.is_cancelled:
                return True
        return False

    def _fetch_all_messages(self):
        all_messages = []
        last_message_id = None
        headers = {'Authorization': self.token, 'User-Agent': USERAGENT_FIREFOX}

        while True:
            if self._check_events(): break
            
            endpoint = f"/channels/{self.channel_id}/messages?limit=100"
            if last_message_id:
                endpoint += f"&before={last_message_id}"
            
            try:
                # This is a blocking call, but it has a timeout
                resp = self.session.get(f"https://discord.com/api/v10{endpoint}", headers=headers, timeout=30)
                resp.raise_for_status()
                message_batch = resp.json()
            except Exception as e:
                self.progress_signal.emit(f"   ❌ Error fetching message batch: {e}")
                break

            if not message_batch:
                break
            
            all_messages.extend(message_batch)

            if self.message_limit and len(all_messages) >= self.message_limit:
                self.progress_signal.emit(f"   Reached message limit of {self.message_limit}. Halting fetch.")
                all_messages = all_messages[:self.message_limit]
                break

            last_message_id = message_batch[-1]['id']
            self.progress_label_signal.emit(f"Fetched {len(all_messages)} messages...")
            time.sleep(1) # API Rate Limiting
        
        return all_messages

    def _run_pdf_creation(self):
        # ... (This method remains the same as the previous version)
        self.progress_signal.emit("=" * 40)
        self.progress_signal.emit(f"🚀 Starting Discord PDF export for: {self.api_url}")
        self.progress_label_signal.emit("Fetching messages...")

        all_messages = self._fetch_all_messages()

        if self.is_cancelled:
            self.finished_signal.emit(0, 0, True, [])
            return
        
        self.progress_label_signal.emit(f"Collected {len(all_messages)} total messages. Generating PDF...")
        all_messages.reverse()
        
        base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        font_path = os.path.join(base_path, 'data', 'dejavu-sans', 'DejaVuSans.ttf')
        output_filepath = os.path.join(self.output_dir, f"discord_{self.server_id}_{self.channel_id or 'server'}.pdf")

        # The PDF generator itself now also checks for events
        success = create_pdf_from_discord_messages(
            all_messages, self.server_id, self.channel_id,
            output_filepath, font_path, logger=self.progress_signal.emit,
            cancellation_event=self, pause_event=self
        )
        
        if success:
            self.progress_label_signal.emit(f"✅ PDF export complete!")
        elif not self.is_cancelled:
            self.progress_label_signal.emit(f"❌ PDF export failed. Check log for details.")
        
        self.finished_signal.emit(0, len(all_messages), self.is_cancelled, [])

    def _run_file_download(self):
        # ... (This method remains the same as the previous version)
        download_count = 0
        skip_count = 0
        try:
            self.progress_signal.emit("=" * 40)
            self.progress_signal.emit(f"🚀 Starting Discord download for channel: {self.channel_id}")
            self.progress_label_signal.emit("Fetching messages...")
            all_messages = self._fetch_all_messages()

            if self.is_cancelled:
                self.finished_signal.emit(0, 0, True, [])
                return

            self.progress_label_signal.emit(f"Collected {len(all_messages)} messages. Starting downloads...")
            total_attachments = sum(len(m.get('attachments', [])) for m in all_messages)

            for message in reversed(all_messages):
                if self._check_events(): break
                for attachment in message.get('attachments', []):
                    if self._check_events(): break
                    
                    file_url = attachment['url']
                    original_filename = attachment['filename']
                    filepath = os.path.join(self.output_dir, original_filename)
                    filename_to_use = original_filename

                    counter = 1
                    base_name, extension = os.path.splitext(original_filename)
                    while os.path.exists(filepath):
                        filename_to_use = f"{base_name} ({counter}){extension}"
                        filepath = os.path.join(self.output_dir, filename_to_use)
                        counter += 1
                    
                    if filename_to_use != original_filename:
                        self.progress_signal.emit(f"   -> Duplicate name '{original_filename}'. Saving as '{filename_to_use}'.")

                    try:
                        self.progress_signal.emit(f"   Downloading ({download_count+1}/{total_attachments}): '{filename_to_use}'...")
                        response = requests.get(file_url, stream=True, timeout=60)
                        response.raise_for_status()
                        
                        download_cancelled_mid_file = False
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if self._check_events():
                                    download_cancelled_mid_file = True
                                    break
                                f.write(chunk)
                        
                        if download_cancelled_mid_file:
                            self.progress_signal.emit(f"   Download cancelled for '{filename_to_use}'. Deleting partial file.")
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            continue
                        
                        download_count += 1
                    except Exception as e:
                        self.progress_signal.emit(f"   ❌ Failed to download '{filename_to_use}': {e}")
                        skip_count += 1
        finally:
            self.finished_signal.emit(download_count, skip_count, self.is_cancelled, [])

    def cancel(self):
        self.is_cancelled = True
        self.progress_signal.emit("   Cancellation signal received by Discord thread.")

class Saint2DownloadThread(QThread):
    """A dedicated QThread for handling saint2.su downloads."""
    progress_signal = pyqtSignal(str)
    file_progress_signal = pyqtSignal(str, object)
    finished_signal = pyqtSignal(int, int, bool) # dl_count, skip_count, cancelled

    def __init__(self, url, output_dir, parent=None):
        super().__init__(parent)
        self.saint2_url = url
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        download_count = 0
        skip_count = 0
        self.progress_signal.emit("=" * 40)
        self.progress_signal.emit(f"🚀 Starting Saint2.su Download for: {self.saint2_url}")
        
        # Use the new client to get the download info
        album_name, files_to_download = fetch_saint2_data(self.saint2_url, self.progress_signal.emit)
        
        if not files_to_download:
            self.progress_signal.emit("❌ Failed to extract file information from Saint2. Aborting.")
            self.finished_signal.emit(0, 0, self.is_cancelled)
            return

        # For single media, album_name is the title; for albums, it's the album title
        album_path = os.path.join(self.output_dir, album_name)
        try:
            os.makedirs(album_path, exist_ok=True)
            self.progress_signal.emit(f"   Saving to folder: '{album_path}'")
        except OSError as e:
            self.progress_signal.emit(f"❌ Critical error creating directory: {e}")
            self.finished_signal.emit(0, len(files_to_download), self.is_cancelled)
            return

        total_files = len(files_to_download)
        session = requests.Session()

        for i, file_data in enumerate(files_to_download):
            if self.is_cancelled:
                self.progress_signal.emit("   Download cancelled by user.")
                skip_count = total_files - download_count
                break

            filename = file_data.get('filename', f'untitled_{i+1}.mp4')
            file_url = file_data.get('url')
            headers = file_data.get('headers')
            filepath = os.path.join(album_path, filename)
            
            if os.path.exists(filepath):
                self.progress_signal.emit(f"   -> Skip ({i+1}/{total_files}): '{filename}' already exists.")
                skip_count += 1
                continue

            self.progress_signal.emit(f"   Downloading ({i+1}/{total_files}): '{filename}'...")
            
            try:
                response = session.get(file_url, stream=True, headers=headers, timeout=60)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                last_update_time = time.time()

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.is_cancelled:
                            break
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            current_time = time.time()
                            if total_size > 0 and (current_time - last_update_time) > 0.5:
                                self.file_progress_signal.emit(filename, (downloaded_size, total_size))
                                last_update_time = current_time
                
                if self.is_cancelled:
                    if os.path.exists(filepath): os.remove(filepath)
                    continue
                
                if total_size > 0:
                    self.file_progress_signal.emit(filename, (total_size, total_size))

                download_count += 1
            except requests.exceptions.RequestException as e:
                self.progress_signal.emit(f"   ❌ Failed to download '{filename}'. Error: {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
            except Exception as e:
                self.progress_signal.emit(f"   ❌ An unexpected error occurred with '{filename}': {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
        
        self.file_progress_signal.emit("", None)
        self.finished_signal.emit(download_count, skip_count, self.is_cancelled)

    def cancel(self):
        self.is_cancelled = True
        self.progress_signal.emit("   Cancellation signal received by Saint2 thread.")

class EromeDownloadThread(QThread):
    """A dedicated QThread for handling erome.com downloads."""
    progress_signal = pyqtSignal(str)
    file_progress_signal = pyqtSignal(str, object)
    finished_signal = pyqtSignal(int, int, bool) # dl_count, skip_count, cancelled

    def __init__(self, url, output_dir, parent=None):
        super().__init__(parent)
        self.erome_url = url
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        download_count = 0
        skip_count = 0
        self.progress_signal.emit("=" * 40)
        self.progress_signal.emit(f"🚀 Starting Erome.com Download for: {self.erome_url}")
        
        album_name, files_to_download = fetch_erome_data(self.erome_url, self.progress_signal.emit)
        
        if not files_to_download:
            self.progress_signal.emit("❌ Failed to extract file information from Erome. Aborting.")
            self.finished_signal.emit(0, 0, self.is_cancelled)
            return

        album_path = os.path.join(self.output_dir, album_name)
        try:
            os.makedirs(album_path, exist_ok=True)
            self.progress_signal.emit(f"   Saving to folder: '{album_path}'")
        except OSError as e:
            self.progress_signal.emit(f"❌ Critical error creating directory: {e}")
            self.finished_signal.emit(0, len(files_to_download), self.is_cancelled)
            return

        total_files = len(files_to_download)
        session = cloudscraper.create_scraper()

        for i, file_data in enumerate(files_to_download):
            if self.is_cancelled:
                self.progress_signal.emit("   Download cancelled by user.")
                skip_count = total_files - download_count
                break

            filename = file_data.get('filename', f'untitled_{i+1}.mp4')
            file_url = file_data.get('url')
            headers = file_data.get('headers')
            filepath = os.path.join(album_path, filename)
            
            if os.path.exists(filepath):
                self.progress_signal.emit(f"   -> Skip ({i+1}/{total_files}): '{filename}' already exists.")
                skip_count += 1
                continue

            self.progress_signal.emit(f"   Downloading ({i+1}/{total_files}): '{filename}'...")
            
            try:
                response = session.get(file_url, stream=True, headers=headers, timeout=60)
                response.raise_for_status()

                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                last_update_time = time.time()

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.is_cancelled:
                            break
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            current_time = time.time()
                            if total_size > 0 and (current_time - last_update_time) > 0.5:
                                self.file_progress_signal.emit(filename, (downloaded_size, total_size))
                                last_update_time = current_time
                
                if self.is_cancelled:
                    if os.path.exists(filepath): os.remove(filepath)
                    continue
                
                if total_size > 0:
                    self.file_progress_signal.emit(filename, (total_size, total_size))

                download_count += 1
            except requests.exceptions.RequestException as e:
                self.progress_signal.emit(f"   ❌ Failed to download '{filename}'. Error: {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
            except Exception as e:
                self.progress_signal.emit(f"   ❌ An unexpected error occurred with '{filename}': {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
        
        self.file_progress_signal.emit("", None)
        self.finished_signal.emit(download_count, skip_count, self.is_cancelled)

    def cancel(self):
        self.is_cancelled = True
        self.progress_signal.emit("   Cancellation signal received by Erome thread.")

class BunkrDownloadThread(QThread):
    """A dedicated QThread for handling Bunkr downloads."""
    progress_signal = pyqtSignal(str)
    # --- ADD THIS SIGNAL for detailed file progress ---
    file_progress_signal = pyqtSignal(str, object)
    finished_signal = pyqtSignal(int, int, bool, list)

    def __init__(self, url, output_dir, parent=None):
        super().__init__(parent)
        self.bunkr_url = url
        self.output_dir = output_dir
        self.is_cancelled = False

        class ThreadLogger:
            def __init__(self, signal_emitter):
                self.signal_emitter = signal_emitter
            def info(self, msg, *args, **kwargs):
                self.signal_emitter.emit(str(msg))
            def error(self, msg, *args, **kwargs):
                self.signal_emitter.emit(f"❌ ERROR: {msg}")
            def warning(self, msg, *args, **kwargs):
                self.signal_emitter.emit(f"⚠️ WARNING: {msg}")
            def debug(self, msg, *args, **kwargs):
                pass

        self.logger = ThreadLogger(self.progress_signal)

    def run(self):
        download_count = 0
        skip_count = 0
        self.progress_signal.emit("=" * 40)
        self.progress_signal.emit(f"🚀 Starting Bunkr Download for: {self.bunkr_url}")
        
        album_name, files_to_download = fetch_bunkr_data(self.bunkr_url, self.logger)
        
        if not files_to_download:
            self.progress_signal.emit("❌ Failed to extract file information from Bunkr. Aborting.")
            self.finished_signal.emit(0, 0, self.is_cancelled, [])
            return

        album_path = os.path.join(self.output_dir, album_name)
        try:
            os.makedirs(album_path, exist_ok=True)
            self.progress_signal.emit(f"   Saving to folder: '{album_path}'")
        except OSError as e:
            self.progress_signal.emit(f"❌ Critical error creating directory: {e}")
            self.finished_signal.emit(0, len(files_to_download), self.is_cancelled, [])
            return

        total_files = len(files_to_download)
        for i, file_data in enumerate(files_to_download):
            if self.is_cancelled:
                self.progress_signal.emit("   Download cancelled by user.")
                skip_count = total_files - download_count
                break

            filename = file_data.get('name', 'untitled_file')
            file_url = file_data.get('url')
            headers = file_data.get('_http_headers')
            
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename).strip()
            filepath = os.path.join(album_path, filename)
            
            if os.path.exists(filepath):
                self.progress_signal.emit(f"   -> Skip ({i+1}/{total_files}): '{filename}' already exists.")
                skip_count += 1
                continue

            self.progress_signal.emit(f"   Downloading ({i+1}/{total_files}): '{filename}'...")
            
            try:
                response = requests.get(file_url, stream=True, headers=headers, timeout=60)
                response.raise_for_status()

                # --- MODIFY THIS BLOCK to calculate and emit progress ---
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                last_update_time = time.time()

                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.is_cancelled:
                            break
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            current_time = time.time()
                            if total_size > 0 and (current_time - last_update_time) > 0.5:
                                self.file_progress_signal.emit(filename, (downloaded_size, total_size))
                                last_update_time = current_time
                
                if self.is_cancelled:
                    if os.path.exists(filepath): os.remove(filepath)
                    continue

                # Emit final progress to show 100%
                if total_size > 0:
                    self.file_progress_signal.emit(filename, (total_size, total_size))

                download_count += 1
                # --- END MODIFICATION ---

            except requests.exceptions.RequestException as e:
                self.progress_signal.emit(f"   ❌ Failed to download '{filename}'. Error: {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
            except Exception as e:
                self.progress_signal.emit(f"   ❌ An unexpected error occurred with '{filename}': {e}")
                if os.path.exists(filepath): os.remove(filepath)
                skip_count += 1
        
        # Clear the progress label when finished
        self.file_progress_signal.emit("", None)
        self.finished_signal.emit(download_count, skip_count, self.is_cancelled, [])

    def cancel(self):
        self.is_cancelled = True
        self.progress_signal.emit("   Cancellation signal received by Bunkr thread.")

class Hentai2readDownloadThread(QThread):
    """
    A dedicated QThread for Hentai2Read that uses a two-phase process:
    1. Fetch Phase: Scans all chapters to get total image count.
    2. Download Phase: Downloads all found images with overall progress.
    """
    progress_signal = pyqtSignal(str)
    file_progress_signal = pyqtSignal(str, object)
    finished_signal = pyqtSignal(int, int, bool)
    overall_progress_signal = pyqtSignal(int, int) 

    def __init__(self, base_url, manga_slug, chapter_num, output_dir, pause_event, parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.manga_slug = manga_slug
        self.start_chapter = int(chapter_num) if chapter_num else 1
        self.output_dir = output_dir
        self.pause_event = pause_event
        self.is_cancelled = False
        # Store the original chapter number to detect single-chapter mode
        self.original_chapter_num = chapter_num

    def _check_pause(self):
        if self.is_cancelled: return True
        if self.pause_event and self.pause_event.is_set():
            self.progress_signal.emit("   Download paused...")
            while self.pause_event.is_set():
                if self.is_cancelled: return True
                time.sleep(0.5)
            self.progress_signal.emit("   Download resumed.")
        return self.is_cancelled

    def run(self):
        # --- SETUP ---
        is_single_chapter_mode = self.original_chapter_num is not None

        self.progress_signal.emit("=" * 40)
        self.progress_signal.emit(f"🚀 Starting Hentai2Read Download for: {self.manga_slug}")

        session = cloudscraper.create_scraper(
            browser={'browser': 'firefox', 'platform': 'windows', 'desktop': True}
        )

        # --- PHASE 1: FETCH METADATA FOR ALL CHAPTERS ---
        self.progress_signal.emit("--- Phase 1: Fetching metadata for all chapters... ---")
        all_chapters_to_download = []
        chapter_counter = self.start_chapter
        
        while True:
            if self._check_pause():
                self.finished_signal.emit(0, 0, True)
                return

            chapter_url = f"{self.base_url}/{self.manga_slug}/{chapter_counter}/"
            album_name, files_to_download = fetch_hentai2read_data(chapter_url, self.progress_signal.emit, session)

            if not files_to_download:
                break # End of series found

            all_chapters_to_download.append({
                'album_name': album_name,
                'files': files_to_download,
                'chapter_num': chapter_counter,
                'chapter_url': chapter_url
            })
            
            if is_single_chapter_mode:
                break # If user specified one chapter, only fetch that one
            chapter_counter += 1

        if self._check_pause():
            self.finished_signal.emit(0, 0, True)
            return

        # --- PHASE 2: CALCULATE TOTALS & START DOWNLOAD ---
        if not all_chapters_to_download:
            self.progress_signal.emit("❌ No downloadable chapters found for this series.")
            self.finished_signal.emit(0, 0, self.is_cancelled)
            return

        total_images = sum(len(chap['files']) for chap in all_chapters_to_download)
        self.progress_signal.emit(f"✅ Fetch complete. Found {len(all_chapters_to_download)} chapter(s) with a total of {total_images} images.")
        self.progress_signal.emit("--- Phase 2: Starting image downloads... ---")

        self.overall_progress_signal.emit(total_images, 0)

        grand_total_dl = 0
        grand_total_skip = 0
        images_processed = 0

        for chapter_data in all_chapters_to_download:
            if self._check_pause(): break

            chapter_album_name = chapter_data['album_name']
            self.progress_signal.emit("-" * 40)
            self.progress_signal.emit(f"Downloading Chapter {chapter_data['chapter_num']}: '{chapter_album_name}'")

            series_name_raw = chapter_album_name.split(' Chapter')[0]
            series_folder_name = clean_folder_name(series_name_raw)
            
            MAX_FOLDER_LEN = 100
            if len(series_folder_name) > MAX_FOLDER_LEN:
                series_folder_name = series_folder_name[:MAX_FOLDER_LEN].strip()

            chapter_part_raw = "Chapter " + str(chapter_data['chapter_num'])
            chapter_folder_name = clean_folder_name(chapter_part_raw)
            
            final_save_path = os.path.join(self.output_dir, series_folder_name, chapter_folder_name)
            os.makedirs(final_save_path, exist_ok=True)
            
            for file_data in chapter_data['files']:
                if self._check_pause(): break
                images_processed += 1
                
                filename = file_data.get('filename')
                filepath = os.path.join(final_save_path, filename)

                if os.path.exists(filepath):
                    self.progress_signal.emit(f"   -> Skip ({images_processed}/{total_images}): '{filename}' already exists.")
                    grand_total_skip += 1
                    continue

                self.progress_signal.emit(f"   Downloading ({images_processed}/{total_images}): '{filename}'...")

                download_successful = False
                for attempt in range(3):
                    if self._check_pause(): break
                    try:
                        headers = {'Referer': chapter_data['chapter_url']}
                        response = session.get(file_data.get('url'), stream=True, timeout=60, headers=headers)
                        response.raise_for_status()
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if self._check_pause(): break
                                f.write(chunk)
                        if not self._check_pause():
                            download_successful = True
                            break
                    except (requests.exceptions.RequestException, ConnectionResetError):
                        if attempt < 2: time.sleep(2 * (attempt + 1))

                if self._check_pause(): break
                if download_successful:
                    grand_total_dl += 1
                else:
                    self.progress_signal.emit(f"   ❌ Download failed for '{filename}' after 3 attempts. Skipping.")
                    if os.path.exists(filepath): os.remove(filepath)
                    grand_total_skip += 1
                self.overall_progress_signal.emit(total_images, images_processed)                 
                time.sleep(random.uniform(0.2, 0.7))
            
            if not is_single_chapter_mode:
                time.sleep(random.uniform(1.5, 4.0))

        self.file_progress_signal.emit("", None)
        self.finished_signal.emit(grand_total_dl, grand_total_skip, self.is_cancelled)

    def cancel(self):
        self.is_cancelled = True
        self.progress_signal.emit("   Cancellation signal received by Hentai2Read thread.")

class ExternalLinkDownloadThread (QThread ):
    """A QThread to handle downloading multiple external links sequentially."""
    progress_signal =pyqtSignal (str )
    file_complete_signal =pyqtSignal (str ,bool )
    finished_signal =pyqtSignal ()

    def __init__ (self ,tasks_to_download ,download_base_path ,parent_logger_func ,parent =None ):
        super ().__init__ (parent )
        self .tasks =tasks_to_download 
        self .download_base_path =download_base_path 
        self .parent_logger_func =parent_logger_func 
        self .is_cancelled =False 

    def run (self ):
        self .progress_signal .emit (f"ℹ️ Starting external link download thread for {len (self .tasks )} link(s).")
        for i ,task_info in enumerate (self .tasks ):
            if self .is_cancelled :
                self .progress_signal .emit ("External link download cancelled by user.")
                break 

            platform =task_info .get ('platform','unknown').lower ()
            full_url =task_info ['url'] # The URL is now guaranteed to be complete
            post_title =task_info ['title']

            self .progress_signal .emit (f"Download ({i +1 }/{len (self .tasks )}): Starting '{post_title }' ({platform .upper ()}) from {full_url }")

            try :
                if platform =='mega':
                    # Simplified: The URL is already complete, so we pass it directly.
                    drive_download_mega_file (full_url ,self .download_base_path ,logger_func =self .parent_logger_func )
                elif platform =='google drive':
                    download_gdrive_file (full_url ,self .download_base_path ,logger_func =self .parent_logger_func )
                elif platform =='dropbox':
                    download_dropbox_file (full_url ,self .download_base_path ,logger_func =self .parent_logger_func )
                else :
                    self .progress_signal .emit (f"⚠️ Unsupported platform '{platform }' for link: {full_url }")
                    self .file_complete_signal .emit (full_url ,False )
                    continue 
                self .file_complete_signal .emit (full_url ,True )
            except Exception as e :
                self .progress_signal .emit (f"❌ Error downloading ({platform .upper ()}) link '{full_url }' (from post '{post_title }'): {e }")
                self .file_complete_signal .emit (full_url ,False )
        self .finished_signal .emit ()

    def cancel (self ):
        self .is_cancelled =True 

class NhentaiDownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int, bool)

    IMAGE_SERVERS = [
        "https://i.nhentai.net", "https://i2.nhentai.net", "https://i3.nhentai.net",
        "https://i5.nhentai.net", "https://i7.nhentai.net"
    ]
    
    EXTENSION_MAP = {'j': 'jpg', 'p': 'png', 'g': 'gif', 'w': 'webp' }

    def __init__(self, gallery_data, output_dir, parent=None):
        super().__init__(parent)
        self.gallery_data = gallery_data
        self.output_dir = output_dir
        self.is_cancelled = False

    def run(self):
        title = self.gallery_data.get("title", {}).get("english", f"gallery_{self.gallery_data.get('id')}")
        gallery_id = self.gallery_data.get("id")
        media_id = self.gallery_data.get("media_id")
        pages_info = self.gallery_data.get("pages", [])

        folder_name = clean_folder_name(title)
        gallery_path = os.path.join(self.output_dir, folder_name)

        try:
            os.makedirs(gallery_path, exist_ok=True)
        except OSError as e:
            self.progress_signal.emit(f"❌ Critical error creating directory: {e}")
            self.finished_signal.emit(0, len(pages_info), False)
            return

        self.progress_signal.emit(f"⬇️ Downloading '{title}' to folder '{folder_name}'...")

        # Create a single cloudscraper instance for the entire download
        scraper = cloudscraper.create_scraper()
        download_count = 0
        skip_count = 0

        for i, page_data in enumerate(pages_info):
            if self.is_cancelled:
                break

            page_num = i + 1
            
            ext_char = page_data.get('t', 'j')
            extension = self.EXTENSION_MAP.get(ext_char, 'jpg')
            
            relative_path = f"/galleries/{media_id}/{page_num}.{extension}"
            
            local_filename = f"{page_num:03d}.{extension}"
            filepath = os.path.join(gallery_path, local_filename)

            if os.path.exists(filepath):
                self.progress_signal.emit(f"   -> Skip (Exists): {local_filename}")
                skip_count += 1
                continue

            download_successful = False
            for server in self.IMAGE_SERVERS:
                if self.is_cancelled:
                    break
                
                full_url = f"{server}{relative_path}"
                try:
                    self.progress_signal.emit(f"   Downloading page {page_num}/{len(pages_info)} from {server} ...")
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                        'Referer': f'https://nhentai.net/g/{gallery_id}/'
                    }

                    # Use the scraper instance to get the image
                    response = scraper.get(full_url, headers=headers, timeout=60, stream=True)
                    
                    if response.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        download_count += 1
                        download_successful = True
                        break
                    else:
                        self.progress_signal.emit(f"      -> {server} returned status {response.status_code}. Trying next server...")

                except Exception as e:
                    self.progress_signal.emit(f"      -> {server} failed to connect or timed out: {e}. Trying next server...")
            
            if not download_successful:
                self.progress_signal.emit(f"   ❌ Failed to download {local_filename} from all servers.")
                skip_count += 1

            time.sleep(0.5)

        self.finished_signal.emit(download_count, skip_count, self.is_cancelled)

    def cancel(self):
        self.is_cancelled = True
