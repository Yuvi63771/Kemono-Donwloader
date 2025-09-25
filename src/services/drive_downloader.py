# --- Standard Library Imports ---
import os
import re
import traceback
import json
import base64
import time
import zipfile
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# --- Third-party Library Imports ---
import requests
import cloudscraper

try:
    from Crypto.Cipher import AES
    PYCRYPTODOME_AVAILABLE = True
except ImportError:
    PYCRYPTODOME_AVAILABLE = False

try:
    import gdown
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

MEGA_API_URL = "https://g.api.mega.co.nz"

def _get_filename_from_headers(headers):
    """
    Extracts a filename from the Content-Disposition header.
    """
    cd = headers.get('content-disposition')
    if not cd:
        return None
    
    # Handles both filename="file.zip" and filename*=UTF-8''file%20name.zip
    fname_match = re.findall('filename="?([^"]+)"?', cd)
    if fname_match:
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', fname_match[0].strip())
        return sanitized_name
        
    return None

# --- Helper functions for Mega decryption ---

def urlb64_to_b64(s):
    s = s.replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    return s

def b64_to_bytes(s):
    return base64.b64decode(urlb64_to_b64(s))

def bytes_to_hex(b):
    return b.hex()

def hex_to_bytes(h):
    return bytes.fromhex(h)

def hrk2hk(hex_raw_key):
    key_part1 = int(hex_raw_key[0:16], 16)
    key_part2 = int(hex_raw_key[16:32], 16)
    key_part3 = int(hex_raw_key[32:48], 16)
    key_part4 = int(hex_raw_key[48:64], 16)
    
    final_key_part1 = key_part1 ^ key_part3
    final_key_part2 = key_part2 ^ key_part4
    
    return f'{final_key_part1:016x}{final_key_part2:016x}'

def decrypt_at(at_b64, key_bytes):
    at_bytes = b64_to_bytes(at_b64)
    iv = b'\0' * 16
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    decrypted_at = cipher.decrypt(at_bytes)
    return decrypted_at.decode('utf-8').strip('\0').replace('MEGA', '')

# --- Core Logic for Mega Downloads ---

def get_mega_file_info(file_id, file_key, session, logger_func):
    try:
        hex_raw_key = bytes_to_hex(b64_to_bytes(file_key))
        hex_key = hrk2hk(hex_raw_key)
        key_bytes = hex_to_bytes(hex_key)

        payload = [{"a": "g", "p": file_id}]
        response = session.post(f"{MEGA_API_URL}/cs", json=payload, timeout=20)
        response.raise_for_status()
        res_json = response.json()

        if isinstance(res_json, list) and isinstance(res_json[0], int) and res_json[0] < 0:
            logger_func(f"   [Mega] ❌ API Error: {res_json[0]}. The link may be invalid or removed.")
            return None

        file_size = res_json[0]['s']
        at_b64 = res_json[0]['at']
        at_dec_json_str = decrypt_at(at_b64, key_bytes)
        at_dec_json = json.loads(at_dec_json_str)
        file_name = at_dec_json['n']

        payload = [{"a": "g", "g": 1, "p": file_id}]
        response = session.post(f"{MEGA_API_URL}/cs", json=payload, timeout=20)
        response.raise_for_status()
        res_json = response.json()
        dl_temp_url = res_json[0]['g']

        return {
            'file_name': file_name,
            'file_size': file_size,
            'dl_url': dl_temp_url,
            'hex_raw_key': hex_raw_key
        }
    except (requests.RequestException, json.JSONDecodeError, KeyError, ValueError) as e:
        logger_func(f"   [Mega] ❌ Failed to get file info: {e}")
        return None

def download_and_decrypt_mega_file(info, download_path, logger_func):
    file_name = info['file_name']
    file_size = info['file_size']
    dl_url = info['dl_url']
    hex_raw_key = info['hex_raw_key']
    final_path = os.path.join(download_path, file_name)

    if os.path.exists(final_path) and os.path.getsize(final_path) == file_size:
        logger_func(f"   [Mega] ℹ️ File '{file_name}' already exists with the correct size. Skipping.")
        return

    key = hex_to_bytes(hrk2hk(hex_raw_key))
    iv_hex = hex_raw_key[32:48] + '0000000000000000'
    iv_bytes = hex_to_bytes(iv_hex)
    cipher = AES.new(key, AES.MODE_CTR, initial_value=iv_bytes, nonce=b'')

    try:
        with requests.get(dl_url, stream=True, timeout=(15, 300)) as r:
            r.raise_for_status()
            downloaded_bytes = 0
            last_log_time = time.time()
            
            with open(final_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk: continue
                    decrypted_chunk = cipher.decrypt(chunk)
                    f.write(decrypted_chunk)
                    downloaded_bytes += len(chunk)
                    
                    current_time = time.time()
                    if current_time - last_log_time > 1:
                        progress_percent = (downloaded_bytes / file_size) * 100 if file_size > 0 else 0
                        logger_func(f"   [Mega] Downloading '{file_name}': {downloaded_bytes/1024/1024:.2f}MB / {file_size/1024/1024:.2f}MB ({progress_percent:.1f}%)")
                        last_log_time = current_time
        
        logger_func(f"   [Mega] ✅ Successfully downloaded '{file_name}' to '{download_path}'")
    except Exception as e:
        logger_func(f"   [Mega] ❌ An unexpected error occurred during download/decryption: {e}")

def download_mega_file(mega_url, download_path, logger_func=print):
    if not PYCRYPTODOME_AVAILABLE:
        logger_func("❌ Mega download failed: 'pycryptodome' library is not installed. Please run: pip install pycryptodome")
        return

    logger_func(f"   [Mega] Initializing download for: {mega_url}")
    
    match = re.search(r'mega(?:\.co)?\.nz/(?:file/|#!)?([a-zA-Z0-9]+)(?:#|!)([a-zA-Z0-9_.-]+)', mega_url)
    if not match:
        logger_func(f"   [Mega] ❌ Error: Invalid Mega URL format.")
        return
        
    file_id = match.group(1)
    file_key = match.group(2)

    session = requests.Session()
    session.headers.update({'User-Agent': 'Kemono-Downloader-PyQt/1.0'})
    
    file_info = get_mega_file_info(file_id, file_key, session, logger_func)
    if not file_info:
        logger_func(f"   [Mega] ❌ Failed to get file info. Aborting.")
        return

    logger_func(f"   [Mega] File found: '{file_info['file_name']}' (Size: {file_info['file_size'] / 1024 / 1024:.2f} MB)")
    
    download_and_decrypt_mega_file(file_info, download_path, logger_func)

def download_gdrive_file(url, download_path, logger_func=print):
    if not GDRIVE_AVAILABLE:
        logger_func("❌ Google Drive download failed: 'gdown' library is not installed.")
        return
    try:
        logger_func(f"   [G-Drive] Starting download for: {url}")
        logger_func("   [G-Drive] Download in progress... This may take some time. Please wait.")
        
        output_path = gdown.download(url, output=download_path, quiet=True, fuzzy=True)
        
        if output_path and os.path.exists(output_path):
            logger_func(f"   [G-Drive] ✅ Successfully downloaded to '{output_path}'")
        else:
            logger_func(f"   [G-Drive] ❌ Download failed. The file may have been moved, deleted, or is otherwise inaccessible.")
    except Exception as e:
        logger_func(f"   [G-Drive] ❌ An unexpected error occurred: {e}")

# --- MODIFIED DROPBOX DOWNLOADER ---
def download_dropbox_file(dropbox_link, download_path=".", logger_func=print):
    """
    Downloads a file or a folder (as a zip) from a public Dropbox link.
    Uses cloudscraper to handle potential browser checks and auto-extracts zip files.
    """
    logger_func(f"   [Dropbox] Attempting to download: {dropbox_link}")
    
    # Modify URL to force download (works for both files and folders)
    parsed_url = urlparse(dropbox_link)
    query_params = parse_qs(parsed_url.query)
    query_params['dl'] = ['1']
    new_query = urlencode(query_params, doseq=True)
    direct_download_url = urlunparse(parsed_url._replace(query=new_query))

    logger_func(f"   [Dropbox] Using direct download URL: {direct_download_url}")

    scraper = cloudscraper.create_scraper()

    try:
        if not os.path.exists(download_path):
            os.makedirs(download_path, exist_ok=True)
            logger_func(f"   [Dropbox] Created download directory: {download_path}")

        with scraper.get(direct_download_url, stream=True, allow_redirects=True, timeout=(20, 600)) as r:
            r.raise_for_status()
            
            filename = _get_filename_from_headers(r.headers) or os.path.basename(parsed_url.path) or "dropbox_download"
            # If it's a folder, Dropbox will name it FolderName.zip
            if not os.path.splitext(filename)[1]:
                 filename += ".zip"

            full_save_path = os.path.join(download_path, filename)
            
            logger_func(f"   [Dropbox] Starting download of '{filename}'...")
            
            total_size = int(r.headers.get('content-length', 0))
            downloaded_bytes = 0
            last_log_time = time.time()

            with open(full_save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    current_time = time.time()
                    if total_size > 0 and current_time - last_log_time > 1:
                        progress = (downloaded_bytes / total_size) * 100
                        logger_func(f"      -> Downloading '{filename}'... {downloaded_bytes/1024/1024:.2f}MB / {total_size/1024/1024:.2f}MB ({progress:.1f}%)")
                        last_log_time = current_time
                    
            logger_func(f"   [Dropbox] ✅ Download complete: {full_save_path}")

            # --- NEW: Auto-extraction logic ---
            if zipfile.is_zipfile(full_save_path):
                logger_func(f"   [Dropbox] ዚ Detected zip file. Attempting to extract...")
                extract_folder_name = os.path.splitext(filename)[0]
                extract_path = os.path.join(download_path, extract_folder_name)
                os.makedirs(extract_path, exist_ok=True)
                
                with zipfile.ZipFile(full_save_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                
                logger_func(f"   [Dropbox] ✅ Successfully extracted to folder: '{extract_path}'")
                
                # Optional: remove the zip file after extraction
                try:
                    os.remove(full_save_path)
                    logger_func(f"   [Dropbox] 🗑️ Removed original zip file.")
                except OSError as e:
                    logger_func(f"   [Dropbox] ⚠️ Could not remove original zip file: {e}")

    except Exception as e:
        logger_func(f"   [Dropbox] ❌ An error occurred during Dropbox download: {e}")
        traceback.print_exc(limit=2)