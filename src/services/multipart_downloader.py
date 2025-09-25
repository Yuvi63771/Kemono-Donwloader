# --- Standard Library Imports ---
# --- Standard Library Imports ---
import os
import time
import hashlib
import http.client
import traceback
import threading
import queue
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Third-Party Library Imports ---
import requests
MULTIPART_DOWNLOADER_AVAILABLE = True

# --- Module Constants ---
CHUNK_DOWNLOAD_RETRY_DELAY = 2
MAX_CHUNK_DOWNLOAD_RETRIES = 1
DOWNLOAD_CHUNK_SIZE_ITER = 1024 * 256  # 256 KB per iteration chunk


def _download_individual_chunk(
    chunk_url, chunk_temp_file_path, start_byte, end_byte, headers,
    part_num, total_parts, progress_data, cancellation_event,
    skip_event, pause_event, global_emit_time_ref, cookies_for_chunk,
    logger_func, emitter=None, api_original_filename=None
):
    """
    Downloads a single segment (chunk) of a larger file to its own unique part file.
    This function is intended to be run in a separate thread by a ThreadPoolExecutor.

    It handles retries, pauses, and cancellations for its specific chunk. If a
    download fails, the partial chunk file is removed, allowing a clean retry later.

    Args:
        chunk_url (str): The URL to download the file from.
        chunk_temp_file_path (str): The unique path to save this specific chunk
                                    (e.g., 'my_video.mp4.part0').
        start_byte (int): The starting byte for the Range header.
        end_byte (int): The ending byte for the Range header.
        headers (dict): The HTTP headers to use for the request.
        part_num (int): The index of this chunk (e.g., 0 for the first part).
        total_parts (int): The total number of chunks for the entire file.
        progress_data (dict): A thread-safe dictionary for sharing progress.
        cancellation_event (threading.Event): Event to signal cancellation.
        skip_event (threading.Event): Event to signal skipping the file.
        pause_event (threading.Event): Event to signal pausing the download.
        global_emit_time_ref (list): A mutable list with one element (a timestamp)
                                     to rate-limit UI updates.
        cookies_for_chunk (dict): Cookies to use for the request.
        logger_func (function): A function to log messages.
        emitter (queue.Queue or QObject): Emitter for sending progress to the UI.
        api_original_filename (str): The original filename for UI display.

    Returns:
        tuple: A tuple containing (bytes_downloaded, success_flag).
    """
    # --- Pre-download checks for control events ---
    if cancellation_event and cancellation_event.is_set():
        logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Download cancelled before start.")
        return 0, False
    if skip_event and skip_event.is_set():
        logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Skip event triggered before start.")
        return 0, False
    if pause_event and pause_event.is_set():
        logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Download paused before start...")
        while pause_event.is_set():
            if cancellation_event and cancellation_event.is_set():
                logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Download cancelled while paused.")
                return 0, False
            time.sleep(0.2)
        logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Download resumed.")

    # Set this chunk's status to 'active' before starting the download.
    with progress_data['lock']:
        progress_data['chunks_status'][part_num]['active'] = True

    try:
        # Prepare headers for the specific byte range of this chunk
        chunk_headers = headers.copy()
        if end_byte != -1:
            chunk_headers['Range'] = f"bytes={start_byte}-{end_byte}"

        bytes_this_chunk = 0
        last_speed_calc_time = time.time()
        bytes_at_last_speed_calc = 0

        # --- Retry Loop ---
        for attempt in range(MAX_CHUNK_DOWNLOAD_RETRIES + 1):
            if cancellation_event and cancellation_event.is_set():
                return bytes_this_chunk, False

            try:
                if attempt > 0:
                    logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Retrying (Attempt {attempt + 1}/{MAX_CHUNK_DOWNLOAD_RETRIES + 1})...")
                    time.sleep(CHUNK_DOWNLOAD_RETRY_DELAY * (2 ** (attempt - 1)))
                    last_speed_calc_time = time.time()
                    bytes_at_last_speed_calc = bytes_this_chunk

                logger_func(f"   🚀 [Chunk {part_num + 1}/{total_parts}] Starting download: bytes {start_byte}-{end_byte if end_byte != -1 else 'EOF'}")

                response = requests.get(chunk_url, headers=chunk_headers, timeout=(10, 120), stream=True, cookies=cookies_for_chunk)
                response.raise_for_status()

                # --- Data Writing Loop ---
                # We open the unique chunk file in write-binary ('wb') mode.
                # No more seeking is required.
                with open(chunk_temp_file_path, 'wb') as f:
                    for data_segment in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE_ITER):
                        if cancellation_event and cancellation_event.is_set():
                            return bytes_this_chunk, False
                        if pause_event and pause_event.is_set():
                            # Handle pausing during the download stream
                            logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Paused...")
                            while pause_event.is_set():
                                if cancellation_event and cancellation_event.is_set(): return bytes_this_chunk, False
                                time.sleep(0.2)
                            logger_func(f"   [Chunk {part_num + 1}/{total_parts}] Resumed.")

                        if data_segment:
                            f.write(data_segment)
                            bytes_this_chunk += len(data_segment)

                            # Update shared progress data structure
                            with progress_data['lock']:
                                progress_data['total_downloaded_so_far'] += len(data_segment)
                                progress_data['chunks_status'][part_num]['downloaded'] = bytes_this_chunk

                                # Calculate and update speed for this chunk
                                current_time = time.time()
                                time_delta = current_time - last_speed_calc_time
                                if time_delta > 0.5:
                                    bytes_delta = bytes_this_chunk - bytes_at_last_speed_calc
                                    current_speed_bps = (bytes_delta * 8) / time_delta if time_delta > 0 else 0
                                    progress_data['chunks_status'][part_num]['speed_bps'] = current_speed_bps
                                    last_speed_calc_time = current_time
                                    bytes_at_last_speed_calc = bytes_this_chunk

                                # Emit progress signal to the UI via the queue
                                if emitter and (current_time - global_emit_time_ref[0] > 0.25):
                                    global_emit_time_ref[0] = current_time
                                    status_list_copy = [dict(s) for s in progress_data['chunks_status']]
                                    if isinstance(emitter, queue.Queue):
                                        emitter.put({'type': 'file_progress', 'payload': (api_original_filename, status_list_copy)})
                                    elif hasattr(emitter, 'file_progress_signal'):
                                        emitter.file_progress_signal.emit(api_original_filename, status_list_copy)

                # If we get here, the download for this chunk is successful
                return bytes_this_chunk, True

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, http.client.IncompleteRead) as e:
                logger_func(f"   ❌ [Chunk {part_num + 1}/{total_parts}] Retryable error: {e}")
            except requests.exceptions.RequestException as e:
                logger_func(f"   ❌ [Chunk {part_num + 1}/{total_parts}] Non-retryable error: {e}")
                return bytes_this_chunk, False # Break loop on non-retryable errors
            except Exception as e:
                logger_func(f"   ❌ [Chunk {part_num + 1}/{total_parts}] Unexpected error: {e}\n{traceback.format_exc(limit=1)}")
                return bytes_this_chunk, False

        # If the retry loop finishes without a successful download
        return bytes_this_chunk, False
    finally:
        # This block runs whether the download succeeded or failed
        with progress_data['lock']:
            progress_data['chunks_status'][part_num]['active'] = False
            progress_data['chunks_status'][part_num]['speed_bps'] = 0.0


def download_file_in_parts(file_url, save_path, total_size, num_parts, headers, api_original_filename,
                           emitter_for_multipart, cookies_for_chunk_session,
                           cancellation_event, skip_event, logger_func, pause_event):
    """
    Manages a resilient, multipart file download by saving each chunk to a separate file.

    This function orchestrates the download process by:
    1. Checking for already completed chunk files to resume a previous download.
    2. Submitting only the missing chunks to a thread pool for parallel download.
    3. Assembling the final file from the individual chunks upon successful completion.
    4. Cleaning up temporary chunk files after assembly.
    5. Leaving completed chunks on disk if the download fails, allowing for a future resume.

    Args:
        file_url (str): The URL of the file to download.
        save_path (str): The final desired path for the downloaded file (e.g., 'my_video.mp4').
        total_size (int): The total size of the file in bytes.
        num_parts (int): The number of parts to split the download into.
        headers (dict): HTTP headers for the download requests.
        api_original_filename (str): The original filename for UI progress display.
        emitter_for_multipart (queue.Queue or QObject): Emitter for UI signals.
        cookies_for_chunk_session (dict): Cookies for the download requests.
        cancellation_event (threading.Event): Event to signal cancellation.
        skip_event (threading.Event): Event to signal skipping the file.
        logger_func (function): A function for logging messages.
        pause_event (threading.Event): Event to signal pausing the download.

    Returns:
        tuple: A tuple containing (success_flag, total_bytes_downloaded, md5_hash, file_handle).
               The file_handle will be for the final assembled file if successful, otherwise None.
    """
    logger_func(f"⬇️ Initializing Resumable Multi-part Download ({num_parts} parts) for: '{api_original_filename}' (Size: {total_size / (1024*1024):.2f} MB)")

    # Calculate the byte range for each chunk
    chunk_size_calc = total_size // num_parts
    chunks_ranges = []
    for i in range(num_parts):
        start = i * chunk_size_calc
        end = start + chunk_size_calc - 1 if i < num_parts - 1 else total_size - 1
        if start <= end:
            chunks_ranges.append((start, end))
        elif total_size == 0 and i == 0: # Handle zero-byte files
            chunks_ranges.append((0, -1))

    # Calculate the expected size of each chunk
    chunk_actual_sizes = []
    for start, end in chunks_ranges:
        chunk_actual_sizes.append(end - start + 1 if end != -1 else 0)

    if not chunks_ranges and total_size > 0:
        logger_func(f"   ⚠️ No valid chunk ranges for multipart download of '{api_original_filename}'. Aborting.")
        return False, 0, None, None

    # --- Resumption Logic: Check for existing complete chunks ---
    chunks_to_download = []
    total_bytes_resumed = 0
    for i, (start, end) in enumerate(chunks_ranges):
        chunk_part_path = f"{save_path}.part{i}"
        expected_chunk_size = chunk_actual_sizes[i]

        if os.path.exists(chunk_part_path) and os.path.getsize(chunk_part_path) == expected_chunk_size:
            logger_func(f"   [Chunk {i + 1}/{num_parts}] Resuming with existing complete chunk file.")
            total_bytes_resumed += expected_chunk_size
        else:
            chunks_to_download.append({'index': i, 'start': start, 'end': end})

    # Setup the shared progress data structure
    progress_data = {
        'total_file_size': total_size,
        'total_downloaded_so_far': total_bytes_resumed,
        'chunks_status': [],
        'lock': threading.Lock(),
        'last_global_emit_time': [time.time()]
    }
    for i in range(num_parts):
        is_resumed = not any(c['index'] == i for c in chunks_to_download)
        progress_data['chunks_status'].append({
            'id': i,
            'downloaded': chunk_actual_sizes[i] if is_resumed else 0,
            'total': chunk_actual_sizes[i],
            'active': False,
            'speed_bps': 0.0
        })

    # --- Download Phase ---
    chunk_futures = []
    all_chunks_successful = True
    total_bytes_from_threads = 0

    with ThreadPoolExecutor(max_workers=num_parts, thread_name_prefix=f"MPChunk_{api_original_filename[:10]}_") as chunk_pool:
        for chunk_info in chunks_to_download:
            if cancellation_event and cancellation_event.is_set():
                all_chunks_successful = False
                break
            
            i, start, end = chunk_info['index'], chunk_info['start'], chunk_info['end']
            chunk_part_path = f"{save_path}.part{i}"
            
            future = chunk_pool.submit(
                _download_individual_chunk,
                chunk_url=file_url,
                chunk_temp_file_path=chunk_part_path,
                start_byte=start, end_byte=end, headers=headers, part_num=i, total_parts=num_parts,
                progress_data=progress_data, cancellation_event=cancellation_event,
                skip_event=skip_event, global_emit_time_ref=progress_data['last_global_emit_time'],
                pause_event=pause_event, cookies_for_chunk=cookies_for_chunk_session,
                logger_func=logger_func, emitter=emitter_for_multipart,
                api_original_filename=api_original_filename
            )
            chunk_futures.append(future)

        for future in as_completed(chunk_futures):
            if cancellation_event and cancellation_event.is_set():
                all_chunks_successful = False
            bytes_downloaded, success = future.result()
            total_bytes_from_threads += bytes_downloaded
            if not success:
                all_chunks_successful = False

    total_bytes_final = total_bytes_resumed + total_bytes_from_threads

    if cancellation_event and cancellation_event.is_set():
        logger_func(f"   Multi-part download for '{api_original_filename}' cancelled by main event.")
        all_chunks_successful = False

    # --- Assembly and Cleanup Phase ---
    if all_chunks_successful and (total_bytes_final == total_size or total_size == 0):
        logger_func(f"   ✅ All {num_parts} chunks complete. Assembling final file...")
        md5_hasher = hashlib.md5()
        try:
            with open(save_path, 'wb') as final_file:
                for i in range(num_parts):
                    chunk_part_path = f"{save_path}.part{i}"
                    with open(chunk_part_path, 'rb') as chunk_file:
                        content = chunk_file.read()
                        final_file.write(content)
                        md5_hasher.update(content)
            
            calculated_hash = md5_hasher.hexdigest()
            logger_func(f"   ✅ Assembly successful for '{api_original_filename}'. Total bytes: {total_bytes_final}")
            return True, total_bytes_final, calculated_hash, open(save_path, 'rb')
        except Exception as e:
            logger_func(f"   ❌ Critical error during file assembly: {e}. Cleaning up.")
            return False, total_bytes_final, None, None
        finally:
            # Cleanup all individual chunk files after successful assembly
            for i in range(num_parts):
                chunk_part_path = f"{save_path}.part{i}"
                if os.path.exists(chunk_part_path):
                    try:
                        os.remove(chunk_part_path)
                    except OSError as e:
                        logger_func(f"    ⚠️ Failed to remove temp part file '{chunk_part_path}': {e}")
    else:
        # If download failed, we do NOT clean up, allowing for resumption later
        logger_func(f"   ❌ Multi-part download failed for '{api_original_filename}'. Success: {all_chunks_successful}, Bytes: {total_bytes_final}/{total_size}. Partial chunks saved for future resumption.")
        return False, total_bytes_final, None, None
