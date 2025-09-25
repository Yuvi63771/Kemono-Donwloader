import sys
import os
import requests
import subprocess # Keep this for now, though it's not used in the final command
from packaging.version import parse as parse_version
from PyQt5.QtCore import QThread, pyqtSignal

# Constants for the updater
GITHUB_REPO_URL = "https://api.github.com/repos/Yuvi9587/Kemono-Downloader/releases/latest"
EXE_NAME = "Kemono.Downloader.exe"

class UpdateChecker(QThread):
    """Checks for a new version on GitHub in a background thread."""
    update_available = pyqtSignal(str, str)  # new_version, download_url
    up_to_date = pyqtSignal(str)
    update_error = pyqtSignal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version_str = current_version.lstrip('v')

    def run(self):
        try:
            response = requests.get(GITHUB_REPO_URL, timeout=15)
            response.raise_for_status()
            data = response.json()

            latest_version_str = data['tag_name'].lstrip('v')
            current_version = parse_version(self.current_version_str)
            latest_version = parse_version(latest_version_str)

            if latest_version > current_version:
                for asset in data.get('assets', []):
                    if asset['name'] == EXE_NAME:
                        self.update_available.emit(latest_version_str, asset['browser_download_url'])
                        return
                self.update_error.emit(f"Update found, but '{EXE_NAME}' is missing from the release assets.")
            else:
                self.up_to_date.emit("You are on the latest version.")

        except requests.exceptions.RequestException as e:
            self.update_error.emit(f"Network error: {e}")
        except Exception as e:
            self.update_error.emit(f"An error occurred: {e}")


class UpdateDownloader(QThread):
    """
    Downloads the new executable and runs an updater script that kills the old process,
    replaces the file, and displays a message in the terminal.
    """
    download_finished = pyqtSignal()
    download_error = pyqtSignal(str)

    def __init__(self, download_url, parent_app):
        super().__init__()
        self.download_url = download_url
        self.parent_app = parent_app

    def run(self):
        try:
            app_path = sys.executable
            app_dir = os.path.dirname(app_path)
            temp_path = os.path.join(app_dir, f"{EXE_NAME}.tmp")
            old_path = os.path.join(app_dir, f"{EXE_NAME}.old")
            updater_script_path = os.path.join(app_dir, "updater.bat")
            
            # --- NEW: Path for the PID file ---
            pid_file_path = os.path.join(app_dir, "updater.pid")

            # Download the new executable
            with requests.get(self.download_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(temp_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

            # --- NEW: Write the current Process ID to the pid file ---
            with open(pid_file_path, "w") as f:
                f.write(str(os.getpid()))

            # --- NEW BATCH SCRIPT ---
            # This script now reads the PID from the "updater.pid" file.
            script_content = f"""
@echo off
SETLOCAL

echo.
echo Reading process information...
set /p PID=<{pid_file_path}

echo Closing the old application (PID: %PID%)...
taskkill /F /PID %PID%

echo Waiting for files to unlock...
timeout /t 2 /nobreak > nul

echo Replacing application files...
if exist "{old_path}" del /F /Q "{old_path}"
rename "{app_path}" "{os.path.basename(old_path)}"
rename "{temp_path}" "{EXE_NAME}"

echo.
echo ============================================================
echo      Update Complete!
echo      You can now close this window and run {EXE_NAME}.
echo ============================================================
echo.
pause

echo Cleaning up helper files...
del "{pid_file_path}"
del "%~f0"
ENDLOCAL
"""
            with open(updater_script_path, "w") as f:
                f.write(script_content)

            # --- Go back to the os.startfile command that we know works ---
            os.startfile(updater_script_path)
            
            self.download_finished.emit()

        except Exception as e:
            self.download_error.emit(f"Failed to download or run updater: {e}")
