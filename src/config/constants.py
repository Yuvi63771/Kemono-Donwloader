CONFIG_ORGANIZATION_NAME = "KemonoDownloader"
CONFIG_APP_NAME_MAIN = "ApplicationSettings"
CONFIG_APP_NAME_TOUR = "ApplicationTour"

# --- Filename and Folder Naming Styles ---
STYLE_POST_TITLE = "post_title"
STYLE_ORIGINAL_NAME = "original_name"
STYLE_DATE_BASED = "date_based"
STYLE_DATE_POST_TITLE = "date_post_title"
STYLE_POST_TITLE_GLOBAL_NUMBERING = "post_title_global_numbering"
STYLE_POST_ID = "post_id"
MANGA_DATE_PREFIX_DEFAULT = ""

# --- Download Scopes ---
SKIP_SCOPE_FILES = "files"
SKIP_SCOPE_POSTS = "posts"
SKIP_SCOPE_BOTH = "both"

CHAR_SCOPE_TITLE = "title"
CHAR_SCOPE_FILES = "files"
CHAR_SCOPE_BOTH = "both"
CHAR_SCOPE_COMMENTS = "comments"

FAVORITE_SCOPE_SELECTED_LOCATION = "selected_location"
FAVORITE_SCOPE_ARTIST_FOLDERS = "artist_folders"

# --- Download Status Constants ---
FILE_DOWNLOAD_STATUS_SUCCESS = "success"
FILE_DOWNLOAD_STATUS_SKIPPED = "skipped"
FILE_DOWNLOAD_STATUS_FAILED_RETRYABLE_LATER = "failed_retry_later"
FILE_DOWNLOAD_STATUS_FAILED_PERMANENTLY_THIS_SESSION = "failed_permanent_session"

# --- Threading and Performance ---
MAX_THREADS = 200
RECOMMENDED_MAX_THREADS = 50
SOFT_WARNING_THREAD_THRESHOLD = 40
MAX_FILE_THREADS_PER_POST_OR_WORKER = 10
POST_WORKER_BATCH_THRESHOLD = 30
POST_WORKER_NUM_BATCHES = 4
POST_WORKER_BATCH_DELAY_SECONDS = 2.5
MAX_POST_WORKERS_WHEN_COMMENT_FILTERING = 3

# --- Multipart Download Settings ---
MIN_SIZE_FOR_MULTIPART_DOWNLOAD = 10 * 1024 * 1024  # 10 MB
MAX_PARTS_FOR_MULTIPART_DOWNLOAD = 15

# --- UI and Settings Keys (for QSettings) ---
TOUR_SHOWN_KEY = "neverShowTourAgainV19"
MANGA_FILENAME_STYLE_KEY = "mangaFilenameStyleV1"
MANGA_CUSTOM_FORMAT_KEY = "mangaCustomFormatV1" 
MANGA_CUSTOM_DATE_FORMAT_KEY = "mangaCustomDateFormatV1" 
SKIP_WORDS_SCOPE_KEY = "skipWordsScopeV1"
ALLOW_MULTIPART_DOWNLOAD_KEY = "allowMultipartDownloadV1"
USE_COOKIE_KEY = "useCookieV1"
COOKIE_TEXT_KEY = "cookieTextV1"
CHAR_FILTER_SCOPE_KEY = "charFilterScopeV1"
THEME_KEY = "currentThemeV2"
SCAN_CONTENT_IMAGES_KEY = "scanContentForImagesV1"
LANGUAGE_KEY = "currentLanguageV1"
DOWNLOAD_LOCATION_KEY = "downloadLocationV1"
RESOLUTION_KEY = "window_resolution"
UI_SCALE_KEY = "ui_scale_factor"
SAVE_CREATOR_JSON_KEY = "saveCreatorJsonProfile"
DATE_PREFIX_FORMAT_KEY = "datePrefixFormatV1" 
FETCH_FIRST_KEY = "fetchAllPostsFirst"
DISCORD_TOKEN_KEY = "discord/token"

POST_DOWNLOAD_ACTION_KEY = "postDownloadAction"

# --- UI Constants and Identifiers ---
HTML_PREFIX = "<!HTML!>"
LOG_DISPLAY_LINKS = "links"
LOG_DISPLAY_DOWNLOAD_PROGRESS = "download_progress"

# --- Dialog Return Codes ---
CONFIRM_ADD_ALL_ACCEPTED = 1
CONFIRM_ADD_ALL_SKIP_ADDING = 2
CONFIRM_ADD_ALL_CANCEL_DOWNLOAD = 3

# --- File Type Extensions ---
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.jpe', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp',
    '.heic', '.heif', '.svg', '.ico', '.jfif', '.pjpeg', '.pjp', '.avif'
}
VIDEO_EXTENSIONS = {
    '.mp4', '.mov', '.mkv', '.webm', '.avi', '.wmv', '.flv', '.mpeg',
    '.mpg', '.m4v', '.3gp', '.ogv', '.ts', '.vob'
}
ARCHIVE_EXTENSIONS = {
    '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'
}
AUDIO_EXTENSIONS = {
    '.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a', '.opus',
    '.aiff', '.ape', '.mid', '.midi'
}

# --- Text Processing Constants ---
MAX_FILENAME_COMPONENT_LENGTH = 150

# Words to ignore when creating folder names from titles
FOLDER_NAME_STOP_WORDS = {
    "a", "alone", "am", "an", "and", "at", "be", "by", "com",
    "for", "he", "her", "his", "i", "im", "in", "is", "it", "its",
    "me", "my", "net", "not", "of", "on", "or", "org", "our",
    "s", "she", "so", "the", "their", "they", "this",
    "to", "ve", "was", "we", "were", "with", "www", "you", "your", "nsfw", "sfw",
 # add more according to need     
}

# Additional words to ignore specifically for creator-level downloads
CREATOR_DOWNLOAD_DEFAULT_FOLDER_IGNORE_WORDS = {
    "poll", "cover", "fan-art", "fanart", "requests", "request", "holiday",
    "batch", "open", "closed", "winner", "loser", "wip",
    "update", "news", "discussion", "question", "stream", "video", "sketchbook",
    # Months and days
    "jan", "january", "feb", "february", "mar", "march", "apr", "april",
    "may", "jun", "june", "jul", "july", "aug", "august", "sep", "september",
    "oct", "october", "nov", "november", "dec", "december",
    "mon", "monday", "tue", "tuesday", "wed", "wednesday", "thu", "thursday",
    "fri", "friday", "sat", "saturday", "sun", "sunday", "Pack", "tier", "spoiler",
    

    # add more according to need 
}

# --- Duplicate Handling Modes ---
DUPLICATE_HANDLING_HASH = "hash"      
DUPLICATE_HANDLING_KEEP_ALL = "keep_all"
STYLE_CUSTOM = "custom"