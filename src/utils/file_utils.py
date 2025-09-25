# --- Standard Library Imports ---
import os
import re

# --- Module Constants ---

# This will be populated at runtime by the main application,
# but is defined here as it's conceptually related to file/folder naming.
KNOWN_NAMES = []

MAX_FILENAME_COMPONENT_LENGTH = 150

# Sets of file extensions for quick type checking
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

# Words to ignore when trying to generate a folder name from a title
FOLDER_NAME_STOP_WORDS = {
    "a", "alone", "am", "an", "and", "at", "be", "blues", "but", "by", "com",
    "for", "grown", "hard", "he", "her", "his", "hitting", "i", "im", "in", "is", "it", "its",
    "me", "much", "my", "net", "not", "of", "on", "or", "org", "our", "please",
    "right", "s", "she", "so", "technically", "tell", "the", "their", "they", "this",
    "to", "ve", "was", "we", "well", "were", "with", "www", "year", "you", "your",
}

# --- File and Folder Name Utilities ---

def clean_folder_name(name):
    """
    Sanitizes a string to make it a valid folder name.
    Removes invalid characters and trims whitespace.

    Args:
        name (str): The input string.

    Returns:
        str: A sanitized, valid folder name.
    """
    if not isinstance(name, str):
        name = str(name)
    
    # Remove characters that are invalid in folder names on most OS
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name)
    cleaned = cleaned.strip()
    
    # Replace multiple spaces with a single space
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # If after cleaning the name is empty, provide a default
    if not cleaned:
        return "untitled_folder"

    # Truncate to a reasonable length
    if len(cleaned) > MAX_FILENAME_COMPONENT_LENGTH:
        cleaned = cleaned[:MAX_FILENAME_COMPONENT_LENGTH]

    # Remove trailing dots or spaces, which can be problematic
    cleaned = cleaned.rstrip('. ')

    return cleaned if cleaned else "untitled_folder"


def clean_filename(name):
    """
    Sanitizes a string to make it a valid file name.

    Args:
        name (str): The input string.

    Returns:
        str: A sanitized, valid file name.
    """
    if not isinstance(name, str):
        name = str(name)
        
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
    cleaned = cleaned.strip()
    
    if not cleaned:
        return "untitled_file"
        
    base_name, ext = os.path.splitext(cleaned)
    max_base_len = MAX_FILENAME_COMPONENT_LENGTH - len(ext)

    if len(base_name) > max_base_len:
        if max_base_len > 0:
            base_name = base_name[:max_base_len]
        else:
            # Handle cases where the extension itself is too long
            return cleaned[:MAX_FILENAME_COMPONENT_LENGTH]
    
    return base_name + ext


# --- File Type Identification Functions ---

def is_image(filename):
    """Checks if a filename has a common image extension."""
    if not filename: return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in IMAGE_EXTENSIONS

def is_video(filename):
    """Checks if a filename has a common video extension."""
    if not filename: return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in VIDEO_EXTENSIONS

def is_zip(filename):
    """Checks if a filename is a .zip file."""
    if not filename: return False
    return filename.lower().endswith('.zip')

def is_rar(filename):
    """Checks if a filename is a .rar file."""
    if not filename: return False
    return filename.lower().endswith('.rar')

def is_archive(filename):
    """Checks if a filename has a common archive extension."""
    if not filename: return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in ARCHIVE_EXTENSIONS

def is_audio(filename):
    """Checks if a filename has a common audio extension."""
    if not filename: return False
    _, ext = os.path.splitext(filename)
    return ext.lower() in AUDIO_EXTENSIONS
