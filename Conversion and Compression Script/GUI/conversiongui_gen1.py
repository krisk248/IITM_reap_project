import sys
import os
import subprocess
import threading
import datetime
import re  # Added for natural sorting fallback
from pathlib import Path
import time # Added for potential small sleeps

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QRadioButton, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# Attempt to import natsort for natural sorting
try:
    import natsort
    HAS_NATSORT = True
except ImportError:
    HAS_NATSORT = False

# -------------------------------
# Global Configuration
# -------------------------------
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
NTFY_TOPIC = "rclone_reap_iit" # Replace with your actual ntfy topic if needed

# Initialize with default values first
FFMPEG_BINARY = "ffmpeg"
FFPROBE_BINARY = "ffprobe"
if sys.platform == "win32":
    FFMPEG_BINARY += ".exe"
    FFPROBE_BINARY += ".exe"

try:
    import imageio_ffmpeg
    ffmpeg_path_str = imageio_ffmpeg.get_ffmpeg_exe()
    FFMPEG_BINARY = ffmpeg_path_str # Set ffmpeg path from imageio

    # Derive ffprobe path from ffmpeg path
    ffmpeg_path = Path(ffmpeg_path_str)
    # Try replacing 'ffmpeg' with 'ffprobe' in the filename
    ffprobe_path = ffmpeg_path.parent / ffmpeg_path.name.replace("ffmpeg", "ffprobe")

    if ffprobe_path.exists() and ffprobe_path.is_file():
        FFPROBE_BINARY = str(ffprobe_path)
        print(f"INFO: Using FFmpeg from imageio_ffmpeg: {FFMPEG_BINARY}")
        print(f"INFO: Derived FFprobe path: {FFPROBE_BINARY}")
    else:
        # If derived path doesn't exist, fall back to default name in the *same directory* or system PATH default
        ffprobe_path_default_name = ffmpeg_path.parent / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
        if ffprobe_path_default_name.exists() and ffprobe_path_default_name.is_file():
             FFPROBE_BINARY = str(ffprobe_path_default_name)
             print(f"INFO: Using FFmpeg from imageio_ffmpeg: {FFMPEG_BINARY}")
             print(f"INFO: Using FFprobe from same directory: {FFPROBE_BINARY}")
        else:
            # Stick with the initialized system PATH default if not found near ffmpeg
            print(f"INFO: Using FFmpeg from imageio_ffmpeg: {FFMPEG_BINARY}")
            print(f"WARNING: Could not find FFprobe near FFmpeg. Falling back to system PATH default: {FFPROBE_BINARY}")

except ImportError:
    # imageio_ffmpeg not installed or failed, rely on the initialized system PATH defaults
    print(f"INFO: imageio_ffmpeg not found or failed. Trying system PATH for {FFMPEG_BINARY} and {FFPROBE_BINARY}.")
except Exception as e:
    print(f"Error during imageio_ffmpeg import or processing: {e}. Falling back to system PATH defaults.")
    # Ensure defaults are set based on OS if an unexpected error happened
    FFMPEG_BINARY = "ffmpeg"
    FFPROBE_BINARY = "ffprobe"
    if sys.platform == "win32":
        FFMPEG_BINARY += ".exe"
        FFPROBE_BINARY += ".exe"

# -------------------------------
# Helper Functions
# -------------------------------
def get_video_duration(input_file: str) -> float:
    """Get video duration in seconds using ffprobe."""
    command = [
        FFPROBE_BINARY, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_file), # Ensure input is string
    ]
    try:
        # Added startupinfo for Windows to hide console window
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # startupinfo.wShowWindow = subprocess.SW_HIDE # May not be needed with CREATE_NO_WINDOW
            creationflags = subprocess.CREATE_NO_WINDOW # Another way to hide console

        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True, encoding='utf-8',
                                startupinfo=startupinfo, creationflags=creationflags) # Use startupinfo here
        return float(result.stdout.strip())
    except subprocess.CalledProcessError as e:
        print(f"Error getting duration for {input_file}: FFprobe exited with code {e.returncode}. Stderr: {e.stderr.strip()}") # Log error
        return 0.0
    except ValueError:
        # It's possible ffprobe returns nothing for duration on some invalid files
        print(f"Error parsing duration for {input_file}: FFprobe output was not a valid number. Output: '{result.stdout.strip() if 'result' in locals() else 'N/A'}'")
        return 0.0
    except FileNotFoundError:
        print(f"Error: '{FFPROBE_BINARY}' command not found. Ensure FFmpeg (including ffprobe) is installed and in your system's PATH.")
        # Maybe raise an exception here or signal the GUI? For now, return 0.
        return 0.0
    except Exception as e:
        print(f"Unexpected error getting duration for {input_file}: {e}") # Log general errors
        return 0.0

def format_duration(seconds: float) -> str:
    """Return a string in 'H hours M min S sec' format."""
    if seconds < 0: seconds = 0 # Handle potential negative durations if ffprobe fails unusually
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    # Format seconds to have consistent decimal places (e.g., 1 decimal place)
    return f"{hours} hours {minutes} min {secs:.1f} sec"

def write_error_log(log_file_path: str, input_file: str, error_output: str):
    """Write error details to a log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Ensure parent directory exists
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        # Use append mode 'a' to avoid overwriting logs if multiple errors occur
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error processing file: {input_file}\n")
            f.write("Details:\n")
            f.write(error_output)
            f.write("\n" + "-" * 40 + "\n") # Separator for multiple errors
    except Exception as e:
        print(f"Failed to write to error log {log_file_path}: {e}")


def natural_sort_key(s):
    """
    Key function for natural sorting (used if natsort library is not available).
    Splits strings into text and number parts for comparison.
    Example: "chapter 10" comes after "chapter 2".
    """
    # Convert input to string just in case
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]

# -------------------------------
# Worker Threads
# -------------------------------
class ConversionWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(float)
    finished_signal = pyqtSignal(bool, bool)  # (success, aborted)

    def __init__(self, input_path: str, output_path: str, mode: str, use_cuda: bool, send_notify: bool):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.mode = mode  # "File" or "Folder"
        self.use_cuda = use_cuda
        self.send_notify = send_notify
        self._stop_event = threading.Event()
        self.process = None # To hold the subprocess object
        self.converted_files = []  # To track created files for cleanup
        self.aborted = False

    def run(self):
        try:
            if self.mode == "File":
                self.process_file(self.input_path, self.output_path)
            else:
                self.process_folder(self.input_path, self.output_path)

            if self._stop_event.is_set():
                self.aborted = True
                # Ensure cleanup happens if aborted AFTER processing loop finishes but before signal
                if not self.process: # Check if cleanup wasn't already triggered by stop()
                    self.cleanup_partial_files()
                self.log_signal.emit("Conversion aborted by user!")
                self.finished_signal.emit(False, True)
            else:
                if self.send_notify:
                    self.send_notification("Video conversion completed successfully.")
                self.log_signal.emit("Conversion process finished.")
                self.finished_signal.emit(True, False) # Success = True, Aborted = False

        except Exception as e:
            self.log_signal.emit(f"Critical error during conversion process: {str(e)}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
            # Ensure cleanup happens on unexpected error
            self.cleanup_partial_files()
            self.finished_signal.emit(False, False)

    def stop(self):
        if self._stop_event.is_set(): # Avoid redundant actions if already stopping
            return
        self._stop_event.set()
        self.aborted = True # Mark as aborted immediately

        if self.process and self.process.poll() is None: # Check if process exists and is running
            try:
                self.log_signal.emit("Attempting to terminate FFmpeg process...")
                # Use taskkill on Windows for potentially better cleanup of child processes
                if sys.platform == "win32":
                     # Added startupinfo/creationflags to hide potential console flash from taskkill
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    creationflags = subprocess.CREATE_NO_WINDOW
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                   capture_output=True, check=False, # Don't check, process might be gone
                                   startupinfo=startupinfo, creationflags=creationflags)
                    self.log_signal.emit(f"Sent taskkill signal to PID {self.process.pid}")
                else:
                    self.process.terminate() # Try graceful termination first
                    try:
                        self.process.wait(timeout=2) # Wait briefly
                    except subprocess.TimeoutExpired:
                        self.log_signal.emit("FFmpeg did not terminate gracefully, killing...")
                        self.process.kill() # Force kill if needed
                # Short pause to allow OS to reclaim resources?
                time.sleep(0.5)
                self.log_signal.emit("FFmpeg process stop signal sent.")
            except Exception as e:
                self.log_signal.emit(f"Error stopping FFmpeg process: {e}")
        # Crucial: cleanup should happen *after* attempting to stop the process
        self.cleanup_partial_files()


    def send_notification(self, message: str):
        try:
            import requests
            url = f"https://ntfy.sh/{NTFY_TOPIC}"
            try:
                response = requests.post(url, data=message.encode("utf-8"), timeout=15) # Increased timeout
                if response.status_code == 200:
                    self.log_signal.emit("Ntfy notification sent successfully!")
                else:
                    self.log_signal.emit(f"Error sending ntfy notification: {response.status_code} - {response.text}")
            except requests.exceptions.RequestException as e: # Catch specific request errors
                self.log_signal.emit(f"Error sending ntfy notification (network issue?): {e}")
        except ImportError:
             self.log_signal.emit("Could not send notification: 'requests' library not installed.")
        except Exception as e:
            self.log_signal.emit(f"Unexpected error sending ntfy notification: {e}")

    def process_file(self, input_file: str, output_dir: str):
        if self._stop_event.is_set(): return # Check before starting
        in_path = Path(input_file)
        out_dir_path = Path(output_dir)
        try:
            out_dir_path.mkdir(parents=True, exist_ok=True) # Ensure output dir exists
        except OSError as e:
            self.log_signal.emit(f"Error creating output directory '{out_dir_path}': {e}. Aborting file processing.")
            # Signal failure? This case might leave the UI thinking it's running.
            # Maybe emit finished signal here? Needs careful thought. For now, log and signal.
            self.finished_signal.emit(False, False) # Signal failure
            return

        out_file = out_dir_path / f"{in_path.stem}.mp4"
        self.convert_video_file(str(in_path), str(out_file))

    def process_folder(self, input_dir: str, output_dir: str):
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        try:
            video_files = [p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            if not video_files:
                self.log_signal.emit("No video files found in the selected folder.")
                return # Nothing to do

            # --- Natural Sort ---
            if HAS_NATSORT:
                self.log_signal.emit("Sorting files naturally (using natsort)...")
                sorted_video_files = natsort.natsorted(video_files, key=lambda x: str(x))
            else:
                self.log_signal.emit("Sorting files naturally (using fallback method)...")
                sorted_video_files = sorted(video_files, key=lambda x: natural_sort_key(str(x)))
            # --------------------

        except Exception as e:
            self.log_signal.emit(f"Error scanning or sorting folder: {e}")
            self.finished_signal.emit(False, False) # Signal failure
            return

        total_files = len(sorted_video_files)
        files_processed_successfully = 0

        for idx, file_path in enumerate(sorted_video_files, 1):
            if self._stop_event.is_set():
                self.log_signal.emit("Stopping folder processing due to abort request.")
                break # Exit the loop if aborted

            try:
                 rel_path = file_path.relative_to(input_path).parent
            except ValueError: # Handle cases like different drives
                 rel_path = Path("") # Put in top level of output dir
            target_dir = output_path / rel_path
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                 self.log_signal.emit(f"Error creating target directory '{target_dir}' for {file_path.name}: {e}. Skipping file.")
                 # Update progress even on skip
                 progress = (idx / total_files) * 100
                 self.progress_signal.emit(progress)
                 continue # Skip to the next file

            out_file = target_dir / f"{file_path.stem}.mp4"

            # Check if output file already exists? Option to skip? For now, overwrite (-y in command)
            self.log_signal.emit(f"({idx}/{total_files}) Processing: {str(file_path.relative_to(input_path))}")
            success = self.convert_video_file(str(file_path), str(out_file))

            if success:
                files_processed_successfully += 1
            elif self._stop_event.is_set(): # Check again if convert_video_file was aborted internally
                 break # Exit loop immediately if aborted during a conversion
            else:
                 # Logged within convert_video_file
                 self.log_signal.emit(f"Finished processing (with error/skip) for {file_path.name}.")

            # Update progress based on files *attempted*
            progress = (idx / total_files) * 100
            self.progress_signal.emit(progress)

        # Final log message after loop finishes or breaks
        if not self._stop_event.is_set():
             self.log_signal.emit(f"Folder processing finished. {files_processed_successfully}/{total_files} files converted successfully.")
        # Abort message handled in run()


    def convert_video_file(self, input_file: str, output_file: str) -> bool:
        """Converts a single video file. Returns True on success, False on failure/skip/abort."""
        if self._stop_event.is_set():
            return False # Don't start if already aborted

        # Check if output file exists and if we should skip? For now, FFMPEG's -y handles overwrite.
        # if Path(output_file).exists():
        #     self.log_signal.emit(f"Output file {Path(output_file).name} already exists. Skipping.")
        #     return True # Or False depending on desired behavior for skips

        duration = get_video_duration(input_file)
        if duration <= 0 and not self._stop_event.is_set(): # Check stop event again after duration check
            self.log_signal.emit(f"Skipping file (invalid/zero duration {duration:.2f}s): {Path(input_file).name}")
            log_file = Path(output_file).with_suffix(".info.log")
            write_error_log(str(log_file), input_file, f"Skipped due to invalid/zero duration ({duration:.2f}s)")
            return False # Indicate failure/skip for this file
        elif self._stop_event.is_set(): # If stop event was set during duration check
             return False

        # --- Define FFmpeg Command ---
        common_args = [
            "-vf", "scale=-2:720",       # Scale to 720p height, maintaining aspect ratio
            "-c:a", "aac", "-b:a", "192k",# Audio codec AAC, bitrate 192k
            "-map_metadata", "-1",       # Remove global metadata
            "-map_chapters", "-1",       # Remove chapters
            "-progress", "pipe:1",       # Report progress to stdout pipe
            "-nostats"                   # Don't print encoding stats per frame
        ]
        # Use -hide_banner to make logs cleaner, -loglevel error to only show critical errors from ffmpeg itself
        base_command = [FFMPEG_BINARY, "-hide_banner", "-y", "-loglevel", "error"]

        if self.use_cuda:
            # Add check if CUDA is actually available/supported? More complex. Assume user knows for now.
            command = [
                *base_command,
                "-hwaccel", "cuda", "-hwaccel_output_format", "cuda", # Specify hwaccel details
                "-i", input_file,
                "-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", # p6~fast, p7~faster; tune hq/ll/ull
                *common_args,
                output_file
            ]
        else:
            command = [
                *base_command,
                "-i", input_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", # CRF 23 often good balance
                 *common_args,
                 output_file
            ]

        self.log_signal.emit(f"Starting conversion: {Path(input_file).name} -> {Path(output_file).name}")
        # self.log_signal.emit(f"FFmpeg command: {' '.join(command)}") # Uncomment for debugging

        try:
            # Startupinfo to hide console window on Windows
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                # startupinfo.wShowWindow = subprocess.SW_HIDE # May not be needed with CREATE_NO_WINDOW
                creationflags = subprocess.CREATE_NO_WINDOW # Another way to hide console


            # Use stderr=subprocess.PIPE to capture ffmpeg's log messages
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, encoding='utf-8', errors='replace', bufsize=1,
                                            startupinfo=startupinfo, creationflags=creationflags)
            # Append to converted_files list *after* Popen succeeds
            self.converted_files.append(output_file)

            # --- Concurrent Stderr Reading ---
            stderr_output = ""
            stderr_lines = []
            stderr_lock = threading.Lock()
            def read_stderr():
                nonlocal stderr_output
                try:
                    # Ensure self.process is valid before reading
                    proc = self.process
                    if proc:
                        for line in proc.stderr:
                            with stderr_lock:
                                stderr_lines.append(line)
                                stderr_output += line
                except Exception as read_err:
                    # This might happen if process is killed abruptly
                    # Check if stop event is set to avoid logging expected errors during abort
                    if not self._stop_event.is_set():
                         print(f"Error reading stderr for {Path(input_file).name}: {read_err}")

            stderr_thread = threading.Thread(target=read_stderr, daemon=True) # Daemon thread exits if main exits
            stderr_thread.start()
            # ---------------------------------

            last_progress_emit_time = time.time()

            while True:
                if self._stop_event.is_set():
                    self.log_signal.emit(f"Abort signal received during conversion for {Path(input_file).name}")
                    # Rely on stop() method called later to kill process and cleanup
                    return False # Indicate failure/abort

                # Read progress from stdout
                line = ""
                proc = self.process # Local ref for safety
                if proc and proc.stdout:
                    try:
                        line = proc.stdout.readline()
                    except Exception as read_err:
                         # Handle potential errors during readline (e.g., pipe closed)
                         if not self._stop_event.is_set():
                              self.log_signal.emit(f"Error reading FFmpeg stdout: {read_err}")
                         break # Exit loop on read error

                # Check process status using poll() *after* trying to read
                process_poll = proc.poll() if proc else -1 # Check if process exists and get status

                if not line and process_poll is not None:
                    # Process finished, break loop
                    break
                if line:
                    # Parse progress
                    parts = line.strip().split('=')
                    if len(parts) == 2:
                        key = parts[0]
                        value = parts[1]
                        if key == "out_time_ms":
                            try:
                                out_time_ms = int(value)
                                if out_time_ms >= 0: # Allow zero time
                                    current_time = out_time_ms / 1_000_000.0
                                    progress = min((current_time / duration) * 100, 100) if duration > 0 else 0
                                    # Throttle progress updates slightly for performance
                                    now = time.time()
                                    if now - last_progress_emit_time > 0.2: # Update ~5 times/sec max
                                        if self.mode == "File":
                                             self.progress_signal.emit(progress)
                                        last_progress_emit_time = now
                            except (ValueError, TypeError):
                                pass # Ignore malformed progress lines
                        elif key == "progress" and value == "end":
                             # Ensure final 100% is sent for file mode
                             if self.mode == "File":
                                 # Emit 100 slightly before breaking to ensure it registers
                                 self.progress_signal.emit(100)
                             # Don't break here, wait for process.poll()
                    # else: # Uncomment to log unexpected stdout lines
                    #      self.log_signal.emit(f"FFMPEG_UNPARSED_STDOUT: {line.strip()}")

                # If no line and process is still running, yield control briefly
                elif line == "" and process_poll is None:
                    time.sleep(0.05)

            # --- Process Finished ---
            # Ensure process is finished and wait briefly for OS cleanup
            final_poll = self.process.poll() if self.process else -1
            if final_poll is None:
                 try:
                     self.process.wait(timeout=5) # Wait with timeout JIC
                 except subprocess.TimeoutExpired:
                      self.log_signal.emit(f"Warning: FFmpeg process did not terminate cleanly after finishing for {Path(input_file).name}.")
                 except Exception as wait_err: # Catch other potential errors during wait
                      if not self._stop_event.is_set(): # Avoid logging error if we are aborting anyway
                           self.log_signal.emit(f"Error waiting for FFmpeg process: {wait_err}")


            # Ensure stderr thread has finished capturing all output
            stderr_thread.join(timeout=2)
            return_code = self.process.poll() if self.process else -1 # Get final code
            self.process = None # Clear process variable

            if self._stop_event.is_set():
                 # Abort might have happened just as the process finished
                 self.log_signal.emit(f"Conversion process finished but abort was requested for {Path(input_file).name}")
                 # Cleanup will be handled by the caller or the stop() method
                 return False # Aborted

            # Check final return code
            if return_code != 0:
                self.log_signal.emit(f"Error: FFmpeg exited with code {return_code} for {Path(input_file).name}")
                log_file = Path(output_file).with_suffix(".error.log")
                with stderr_lock: # Access shared stderr_output safely
                    error_details = f"FFmpeg Command: {' '.join(command)}\n\nFFmpeg Stderr Output:\n{stderr_output}"
                write_error_log(str(log_file), input_file, error_details)
                self.log_signal.emit(f"Error details written to: {str(log_file)}")
                self.cleanup_partial_files(specific_file=output_file) # Try to clean just this file
                return False # Indicate failure
            else:
                # Check if there was anything significant on stderr even on success?
                with stderr_lock:
                     # Check if stderr_output contains common error keywords (case-insensitive)
                     error_keywords = ["error", "failed", "invalid", "unable", "cannot", "warning"] # Add more if needed
                     found_error_word = any(word in stderr_output.lower() for word in error_keywords)

                     if stderr_output and not stderr_output.isspace() and found_error_word:
                         # Log non-empty stderr as warning only if it contains potential error words
                         self.log_signal.emit(f"Warning: FFmpeg reported messages on stderr for {Path(input_file).name} (check .info.log)")
                         log_file = Path(output_file).with_suffix(".info.log")
                         info_details = f"FFmpeg Command: {' '.join(command)}\n\nFFmpeg Stderr Output (Success Code 0):\n{stderr_output}"
                         write_error_log(str(log_file), input_file, info_details)

                self.log_signal.emit(f"Successfully finished: {Path(input_file).name}")
                return True # Indicate success

        except FileNotFoundError:
            self.log_signal.emit(f"FATAL Error: '{FFMPEG_BINARY}' command not found. Ensure FFmpeg is installed and in your system's PATH.")
            # Stop potentially processing other files if ffmpeg is fundamentally missing
            self._stop_event.set()
            # Signal failure back to GUI immediately
            self.finished_signal.emit(False, False)
            return False
        except subprocess.TimeoutExpired:
            self.log_signal.emit(f"Error: FFmpeg process timed out for {Path(input_file).name}. Output file might be incomplete.")
            if self.process: self.process.kill() # Ensure it's killed on timeout
            self.process = None # Ensure process is cleared
            self.cleanup_partial_files(specific_file=output_file)
            return False
        except Exception as e:
            self.log_signal.emit(f"An unexpected Python error occurred during conversion of {Path(input_file).name}: {e}")
            import traceback
            tb_str = traceback.format_exc()
            self.log_signal.emit(tb_str) # Log traceback to GUI log
            log_file = Path(output_file).with_suffix(".error.log")
            write_error_log(str(log_file), input_file, f"FFmpeg Command: {' '.join(command)}\n\nPython Exception:\n{tb_str}")
            self.log_signal.emit(f"Python error details written to: {str(log_file)}")
            # Ensure process is cleared if it exists
            if self.process and self.process.poll() is None:
                 try: self.process.kill()
                 except Exception: pass
            self.process = None
            self.cleanup_partial_files(specific_file=output_file)
            return False # Indicate failure


    def cleanup_partial_files(self, specific_file: str = None):
        """Deletes files created during an aborted or failed conversion.
           If specific_file is provided, only attempts to delete that file if tracked.
           Otherwise, cleans all files tracked in self.converted_files.
        """
        files_to_clean = []
        is_specific = False
        # Use a lock to protect access to the shared list, just in case
        list_lock = threading.Lock()

        with list_lock:
            if specific_file:
                is_specific = True
                # Only clean the specific file if it's in our tracked list
                if specific_file in self.converted_files:
                    files_to_clean.append(specific_file)
                else:
                    # If specific_file isn't in the list (e.g., error before appending),
                    # still try deleting it directly if it exists, as it might be orphaned.
                    if Path(specific_file).exists():
                        files_to_clean.append(specific_file) # Add for deletion attempt

            else:
                # Clean all tracked files (usually on abort or end-of-run cleanup)
                 if not self.converted_files:
                     return # Nothing to clean
                 self.log_signal.emit("Cleaning up generated files...")
                 files_to_clean = list(self.converted_files) # Process a copy

        cleaned_count = 0
        for file_path_str in files_to_clean:
            try:
                p = Path(file_path_str)
                if p.exists() and p.is_file(): # Check if it exists and is a file
                    os.remove(p)
                    self.log_signal.emit(f"Deleted potentially partial file: {p.name}")
                    cleaned_count += 1
                # Remove from the main list if we are cleaning everything OR if cleaning specific and it was found in the list
                with list_lock:
                    # Check again if still in list before removing
                    if file_path_str in self.converted_files:
                        self.converted_files.remove(file_path_str)

            except OSError as e:
                self.log_signal.emit(f"Error deleting file during cleanup {file_path_str}: {str(e)}")
            except Exception as e:
                 self.log_signal.emit(f"Unexpected error cleaning file {file_path_str}: {e}")


        if not is_specific and cleaned_count > 0:
            self.log_signal.emit(f"Cleanup finished. Deleted {cleaned_count} tracked file(s).")
        elif not is_specific:
             self.log_signal.emit("Cleanup check complete. No tracked files needed deletion.")

        # If cleaning all, ensure the list is clear at the end
        if not is_specific:
            with list_lock:
                 self.converted_files.clear()


class DurationWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(float)
    finished_signal = pyqtSignal(bool)  # (success)

    def __init__(self, input_path: str, output_path: str, mode: str):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path # This is the folder where the txt file will be saved
        self.mode = mode  # "File" or "Folder"
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        self.log_signal.emit("Starting duration check...")
        durations = {}
        total_duration = 0.0
        files_to_process = []
        processed_files_count = 0

        try:
            input_p = Path(self.input_path)
            if self.mode == "File":
                if input_p.is_file() and input_p.suffix.lower() in VIDEO_EXTENSIONS:
                    files_to_process = [str(input_p)]
                else:
                    self.log_signal.emit(f"Input is not a valid video file or not supported: {self.input_path}")
                    self.finished_signal.emit(False)
                    return
            else: # Folder mode
                if not input_p.is_dir():
                     self.log_signal.emit(f"Input path is not a valid folder: {self.input_path}")
                     self.finished_signal.emit(False)
                     return
                self.log_signal.emit(f"Scanning folder: {self.input_path}")
                # Use iterator for potentially large directories
                all_files_iter = input_p.rglob("*")
                # Filter more carefully - ensure we can access the file before adding
                all_files = []
                for p in all_files_iter:
                     try:
                          if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                               if os.access(p, os.R_OK): # Check read access
                                    all_files.append(p)
                               else:
                                    self.log_signal.emit(f"Skipping file due to read permission error: {p.name}")
                     except OSError as e:
                          self.log_signal.emit(f"Error accessing file {p}: {e}. Skipping.")


                # --- Natural Sort Implementation ---
                if not all_files:
                    self.log_signal.emit("No supported and accessible video files found in the folder.")
                    self.finished_signal.emit(False)
                    return

                if HAS_NATSORT:
                    self.log_signal.emit("Sorting files naturally (using natsort)...")
                    files_to_process = [str(p) for p in natsort.natsorted(all_files, key=lambda x: str(x))]
                else:
                    self.log_signal.emit("WARNING: 'natsort' library not found. Using basic natural sort. Install with 'pip install natsort' for better results.")
                    files_to_process = [str(p) for p in sorted(all_files, key=lambda x: natural_sort_key(str(x)))]
                # ----------------------------------

        except PermissionError as e:
             self.log_signal.emit(f"Permission error accessing input path '{self.input_path}': {e}")
             self.finished_signal.emit(False)
             return
        except Exception as e:
            self.log_signal.emit(f"Error accessing or scanning input path '{self.input_path}': {e}")
            self.finished_signal.emit(False)
            return

        total_files = len(files_to_process)
        if total_files == 0:
            # Should have been caught above, but acts as a safeguard
            self.log_signal.emit("No video files found to check duration for.")
            self.finished_signal.emit(False)
            return

        self.log_signal.emit(f"Found {total_files} video file(s). Calculating durations...")

        for idx, file_path_str in enumerate(files_to_process, 1):
            if self._stop_event.is_set():
                self.log_signal.emit("Duration check aborted by user.")
                self.finished_signal.emit(False) # Indicate not successful completion
                return

            file_path = Path(file_path_str)
            # Shorten display name for log if path is too long?
            log_display_name = file_path.name if len(file_path.name) < 70 else f"...{file_path.name[-67:]}"
            self.log_signal.emit(f"Processing ({idx}/{total_files}): {log_display_name}")

            duration = get_video_duration(file_path_str) # Call helper function
            processed_files_count += 1

            if duration > 0:
                durations[file_path_str] = duration # Store duration with full path as key initially
                total_duration += duration
            elif not self._stop_event.is_set(): # Don't log skip message if we just aborted
                 self.log_signal.emit(f"Could not get duration for {file_path.name}, skipping calculation for this file.")
                 durations[file_path_str] = 0.0 # Store 0 duration for problematic files

            progress = (processed_files_count / total_files) * 100
            self.progress_signal.emit(progress)
            # Yield control briefly to keep UI responsive
            # time.sleep(0.01) # Optional, might slow down very fast checks

        # --- Generate Output Filename ---
        input_p = Path(self.input_path)
        if input_p.is_dir():
            base_name = input_p.name # Use folder name
        else:
             base_name = input_p.stem # Use file name without extension
        # Sanitize the base name (replace invalid filename chars with underscore)
        # Keep it simple: replace non-alphanumeric/hyphen/underscore/dot with '_'
        safe_base_name = re.sub(r'[^\w\-\.]+', '_', base_name).strip('_') # Remove leading/trailing underscores
        if not safe_base_name: safe_base_name = "duration_report" # Fallback if name becomes empty
        output_filename = f"{safe_base_name}_duration_report.txt"
        output_file_path = Path(self.output_path) / output_filename
        # --------------------------------

        self.log_signal.emit(f"Writing durations report to: {output_file_path}")
        try:
            output_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure output dir exists
            with open(output_file_path, "w", encoding="utf-8") as f:
                f.write(f"Video Durations Report\n")
                f.write("="*30 + "\n")
                f.write(f"Source: {self.input_path}\n")
                f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total Files Scanned: {total_files}\n")
                f.write("-" * 30 + "\n\n")
                f.write("Individual File Durations (Sorted Naturally):\n")

                # Write durations using the sorted order preserved by files_to_process
                for file_path_str in files_to_process:
                    dur = durations.get(file_path_str, 0.0) # Get duration, default 0 if missing
                    display_name = ""
                    try:
                        # Display relative path in the output for folder mode, just name for file mode
                        input_base_path = Path(self.input_path)
                        if self.mode == "Folder":
                            # Ensure base path is treated as directory
                            if input_base_path.is_file(): input_base_path = input_base_path.parent
                            display_name = str(Path(file_path_str).relative_to(input_base_path))
                        else: # File mode
                            display_name = Path(file_path_str).name
                    except ValueError:
                         # Handle cases where relative_to fails (e.g., different drives on Windows)
                         display_name = Path(file_path_str).name # Fallback to just the name
                    except Exception as path_err:
                         display_name = f"[Error getting relative path: {path_err}] {Path(file_path_str).name}"


                    # --- Format Duration (Removed asterisks) ---
                    formatted_dur = format_duration(dur) if dur > 0 else "Error reading duration"
                    f.write(f"  {display_name} -> {formatted_dur}\n")
                    # -----------------------------------------

                f.write("\n" + "=" * 30 + "\n")
                # --- Format Total Duration (Removed asterisks) ---
                formatted_total_dur = format_duration(total_duration)
                f.write(f"TOTAL DURATION (Sum of readable files) -> {formatted_total_dur}\n")
                # ------------------------------------
                f.write("=" * 30 + "\n")

            self.log_signal.emit(f"Duration report saved successfully.")
            self.finished_signal.emit(True) # Indicate success
        except IOError as e:
            self.log_signal.emit(f"Error writing duration file '{output_file_path}': {e}")
            self.finished_signal.emit(False)
        except Exception as e:
             self.log_signal.emit(f"An unexpected error occurred while writing duration file: {e}")
             import traceback
             self.log_signal.emit(traceback.format_exc())
             self.finished_signal.emit(False)


# -------------------------------
# Main GUI Window
# -------------------------------
class ConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kannan's Video Converter")
        # Increase default size slightly
        self.setGeometry(100, 100, 850, 700)
        self.worker = None
        self.duration_worker = None
        self.mode = "File" # Initialize mode attribute
        self.init_ui()
        # Check for ffmpeg/ffprobe on startup?
        self._check_ffmpeg_ffprobe()

    def _check_ffmpeg_ffprobe(self):
        """Checks if ffmpeg/ffprobe seem accessible."""
        self.log("Checking for FFmpeg/FFprobe...")
        missing = []
        try:
             # Use startupinfo/creationflags to hide console window on Windows
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW

            subprocess.run([FFMPEG_BINARY, "-version"], check=True, capture_output=True, timeout=5,
                           startupinfo=startupinfo, creationflags=creationflags)
            self.log(f" -> {FFMPEG_BINARY} found.")
        except FileNotFoundError:
             self.log(f" -> ERROR: {FFMPEG_BINARY} not found in PATH. Conversion disabled.")
             missing.append(FFMPEG_BINARY)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
            self.log(f" -> ERROR: Failed to execute {FFMPEG_BINARY} ({type(e).__name__}). Conversion disabled.")
            missing.append(FFMPEG_BINARY)

        try:
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                creationflags = subprocess.CREATE_NO_WINDOW
            # Use global FFPROBE_BINARY which should now always be defined
            subprocess.run([FFPROBE_BINARY, "-version"], check=True, capture_output=True, timeout=5,
                           startupinfo=startupinfo, creationflags=creationflags)
            self.log(f" -> {FFPROBE_BINARY} found.")
        except FileNotFoundError:
             self.log(f" -> ERROR: {FFPROBE_BINARY} not found in PATH. Duration check/conversion disabled.")
             missing.append(FFPROBE_BINARY)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
            self.log(f" -> ERROR: Failed to execute {FFPROBE_BINARY} ({type(e).__name__}). Duration check/conversion disabled.")
            missing.append(FFPROBE_BINARY)

        # Prevent duplicates in missing list
        missing = list(set(missing))

        if missing:
            QMessageBox.critical(self, "Missing Dependencies",
                                 f"Could not find or execute: {', '.join(missing)}.\n\n"
                                 "Please ensure FFmpeg (including ffprobe) is installed and accessible "
                                 "via the system's PATH environment variable, or configure the paths "
                                 "at the top of the script (FFMPEG_BINARY, FFPROBE_BINARY).\n\n"
                                 "Relevant functions will be disabled.")
            if FFMPEG_BINARY in missing:
                 self.convert_btn.setEnabled(False)
                 self.convert_btn.setToolTip(f"{FFMPEG_BINARY} not found or failed execution.")
            if FFPROBE_BINARY in missing:
                 self.duration_btn.setEnabled(False)
                 self.duration_btn.setToolTip(f"{FFPROBE_BINARY} not found or failed execution.")
                 # Conversion also relies on ffprobe for duration check before starting
                 if FFMPEG_BINARY not in missing: # Only disable convert if ffprobe missing but ffmpeg wasn't
                      self.convert_btn.setEnabled(False)
                      self.convert_btn.setToolTip(f"{FFPROBE_BINARY} (needed for pre-check) not found or failed execution.")
        else:
             self.log("FFmpeg and FFprobe checks passed.")


    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # --- Input/Output Selection ---
        io_group = QGroupBox("Input / Output")
        io_layout = QVBoxLayout()
        io_group.setLayout(io_layout)

        mode_layout = QHBoxLayout()
        self.file_radio = QRadioButton("Single File")
        self.folder_radio = QRadioButton("Entire Folder")
        self.file_radio.setChecked(True)
        self.file_radio.toggled.connect(self.update_browse_button_text)
        mode_layout.addWidget(self.file_radio)
        mode_layout.addWidget(self.folder_radio)
        mode_layout.addStretch()
        io_layout.addLayout(mode_layout)

        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("Select input video file or folder...")
        self.browse_input_btn = QPushButton("Browse File...")
        self.browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.browse_input_btn)
        io_layout.addLayout(input_layout)

        output_layout = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_line.setPlaceholderText("Select output folder (for conversions or duration reports)...")
        self.browse_output_btn = QPushButton("Browse Output...") # Renamed button text
        self.browse_output_btn.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_line)
        output_layout.addWidget(self.browse_output_btn)
        io_layout.addLayout(output_layout)

        main_layout.addWidget(io_group)

        # --- Options ---
        options_group = QGroupBox("Options")
        options_layout = QHBoxLayout()
        options_group.setLayout(options_layout)
        self.cuda_checkbox = QCheckBox("Use NVIDIA CUDA acceleration (if available & supported)")
        self.notify_checkbox = QCheckBox("Send ntfy notification on completion")
        options_layout.addWidget(self.cuda_checkbox)
        options_layout.addWidget(self.notify_checkbox)
        options_layout.addStretch()
        main_layout.addWidget(options_group)

        # --- Actions ---
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout() # Changed to VBox for better layout with progress bar below
        action_group.setLayout(action_layout)

        buttons_layout = QHBoxLayout() # Horizontal layout for buttons
        self.convert_btn = QPushButton("Convert Video(s)") # Renamed
        self.convert_btn.setStyleSheet("QPushButton { font-weight: bold; background-color: #4CAF50; color: white; padding: 6px 10px; }")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.duration_btn = QPushButton("Check Duration(s)")
        self.duration_btn.setStyleSheet("QPushButton { font-weight: bold; background-color: #2196F3; color: white; padding: 6px 10px; }")
        self.duration_btn.clicked.connect(self.start_duration_check)
        self.abort_btn = QPushButton("Abort Current Task") # Renamed
        self.abort_btn.setStyleSheet("QPushButton { font-weight: bold; background-color: #f44336; color: white; padding: 6px 10px; }")
        self.abort_btn.clicked.connect(self.abort_process)
        self.abort_btn.setEnabled(False)

        buttons_layout.addWidget(self.convert_btn)
        buttons_layout.addWidget(self.duration_btn)
        buttons_layout.addStretch(1)
        buttons_layout.addWidget(self.abort_btn)
        action_layout.addLayout(buttons_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%") # Default format
        # self.progress_bar.setMinimumWidth(400) # Set width via layout if needed
        action_layout.addWidget(self.progress_bar)

        main_layout.addWidget(action_group)

        # --- Log Output ---
        log_group = QGroupBox("Log Output")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log_text.setStyleSheet("QTextEdit { background-color: #f0f0f0; font-family: Consolas, Courier New, monospace; }") # Monospace font
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group, stretch=1) # Allow log area to stretch

        # Set initial state
        self.update_browse_button_text()

    def update_browse_button_text(self):
        # Update mode and button text based on radio selection
        if self.file_radio.isChecked():
            self.browse_input_btn.setText("Browse File...")
            self.input_line.setPlaceholderText("Select input video file...")
            self.mode = "File"
        else:
            self.browse_input_btn.setText("Browse Folder...")
            self.input_line.setPlaceholderText("Select input folder containing videos...")
            self.mode = "Folder"

    def browse_input(self):
        input_path_text = ""
        current_path = self.input_line.text().strip()
        start_dir = ""
        # Try to start dialog in the parent of the current path if valid
        if current_path:
             try:
                 p = Path(current_path)
                 if p.is_file():
                     start_dir = str(p.parent)
                 elif p.is_dir():
                     start_dir = str(p)
                 if not Path(start_dir).is_dir(): # Fallback if parent/self isn't dir
                     start_dir = ""
             except Exception: # Handle invalid paths gracefully
                  start_dir = "" # Keep start_dir empty

        if self.mode == "File": # Use self.mode here
            video_filter = "Video files (" + " ".join("*" + ext for ext in VIDEO_EXTENSIONS) + ");;All Files (*)"
            file_path, _ = QFileDialog.getOpenFileName(self, "Select a Video File", start_dir, video_filter)
            if file_path:
                input_path_text = file_path
        else: # Folder mode
            folder_path = QFileDialog.getExistingDirectory(self, "Select Input Folder", start_dir)
            if folder_path:
                input_path_text = folder_path

        if input_path_text:
             self.input_line.setText(input_path_text)
             # REMOVED automatic output suggestion based on user request

    def browse_output(self):
        current_path = self.output_line.text().strip()
        start_dir = ""
        if current_path:
             try:
                 p = Path(current_path)
                 if p.is_dir():
                     start_dir = str(p)
                 elif p.is_file(): # If user somehow selected a file, start in parent
                      start_dir = str(p.parent)
                 if not Path(start_dir).is_dir(): # Fallback if parent/self isn't dir
                     start_dir = ""
             except Exception:
                  start_dir = ""

        folder_path = QFileDialog.getExistingDirectory(self, "Select Output Folder", start_dir)
        if folder_path:
            self.output_line.setText(folder_path)

    def log(self, message: str):
        """Safely appends a message to the log text area from any thread."""
        # This method might be called by GUI event handlers (main thread)
        # or via signals from worker threads (which PyQt ensures arrive in the main thread)
        # So, it should generally be safe to call _do_log directly.
        # Adding a check anyway for extra safety, but direct calls from workers are discouraged.
        if threading.current_thread() is threading.main_thread():
            self._do_log(message)
        else:
            # This path should ideally not be taken if workers use signals properly.
            print(f"Warning: log() called directly from worker thread: {message}. Use signals instead.")
            # Attempting a direct call here is risky, relying on signals is correct.


    def _do_log(self, message: str):
        """Actual logging implementation, always runs in GUI thread."""
        try:
            timestamp = datetime.datetime.now().strftime('%H:%M:%S')
            self.log_text.append(f"[{timestamp}] {message}")
            # Auto-scroll to the bottom
            scrollbar = self.log_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
             print(f"Error updating log GUI: {e}") # Log to console if GUI fails

    def set_ui_busy(self, busy: bool):
        """Enable/disable UI elements during processing."""
        # Check if ffmpeg/ffprobe are okay (based on tooltip being empty)
        ffmpeg_ok = self.convert_btn.toolTip() == ""
        ffprobe_ok = self.duration_btn.toolTip() == ""

        # Only enable convert if both are ok
        self.convert_btn.setEnabled(not busy and ffmpeg_ok and ffprobe_ok)
        # Only enable duration check if ffprobe is ok
        self.duration_btn.setEnabled(not busy and ffprobe_ok)

        self.abort_btn.setEnabled(busy)
        if not busy: # Reset abort button text only when becoming idle
            self.abort_btn.setText("Abort Current Task")

        self.input_line.setEnabled(not busy)
        self.output_line.setEnabled(not busy)
        self.browse_input_btn.setEnabled(not busy)
        self.browse_output_btn.setEnabled(not busy)
        self.file_radio.setEnabled(not busy)
        self.folder_radio.setEnabled(not busy)
        self.cuda_checkbox.setEnabled(not busy)
        self.notify_checkbox.setEnabled(not busy)

        if not busy:
            self.progress_bar.setValue(0)
            # Reset progress format based on previous task result? Or just to default?
            # Let's reset to default. Specific formats set by finished handlers.
            self.progress_bar.setFormat("%p%")
        else:
             self.progress_bar.setFormat("Processing... %p%")


    def validate_paths(self) -> bool:
        """Check if input and output paths are valid and accessible."""
        input_path = self.input_line.text().strip()
        output_path = self.output_line.text().strip()

        if not input_path:
            QMessageBox.warning(self, "Input Missing", "Please select an input file or folder.")
            return False
        if not output_path:
            QMessageBox.warning(self, "Output Missing", "Please select an output folder.\n(This folder is used for converted files or duration reports.)")
            return False

        input_p = Path(input_path)
        output_p = Path(output_path)

        # --- Input Validation ---
        current_mode = self.mode # Use mode updated by radio buttons
        if current_mode == "File":
            if not input_p.is_file():
                QMessageBox.critical(self, "Input Error", f"Input file not found or is not a file:\n{input_path}")
                return False
            if not os.access(input_path, os.R_OK):
                  QMessageBox.critical(self, "Input Error", f"Cannot read input file (check permissions):\n{input_path}")
                  return False
            if input_p.suffix.lower() not in VIDEO_EXTENSIONS:
                 # Just log a warning, let user decide if it's convertible
                 self.log(f"Warning: Input file '{input_p.name}' might not be a directly supported video format based on extension.")
        else: # Folder mode
             if not input_p.is_dir():
                QMessageBox.critical(self, "Input Error", f"Input folder not found or is not a directory:\n{input_path}")
                return False
             # Check read permissions on input folder?
             if not os.access(input_path, os.R_OK):
                  QMessageBox.critical(self, "Input Error", f"Cannot read input folder (check permissions):\n{input_path}")
                  return False

        # --- Output Directory Handling & Validation ---
        try:
             # Try creating first, then check write permissions
             output_p.mkdir(parents=True, exist_ok=True)
             if not output_p.is_dir(): # Check if path exists but isn't a dir after mkdir attempt
                 QMessageBox.critical(self, "Output Error", f"Output path exists but is not a directory:\n{output_path}")
                 return False

             # Check if we can write to the output directory using os.access (more reliable than touch/unlink sometimes)
             if not os.access(output_path, os.W_OK):
                 # If os.access fails, try the touch/unlink method as a backup check (might work on some systems/network drives)
                 try:
                     test_file = output_p / f".write_test_{os.getpid()}.tmp"
                     test_file.touch()
                     test_file.unlink()
                     # If touch/unlink worked, maybe os.access was wrong, proceed with caution
                     self.log(f"Warning: os.access check failed for output directory, but touch/unlink succeeded. Proceeding cautiously.")
                 except OSError as e:
                      # If touch/unlink also fails, then definitely no write permission
                      QMessageBox.critical(self, "Output Error", f"Cannot write to the selected output directory (check permissions):\n{output_path}\nError: {e}")
                      return False

        except OSError as e:
             QMessageBox.critical(self, "Output Error", f"Could not create or access output directory:\n{output_path}\nError: {e}")
             return False
        except Exception as e: # Catch other potential errors like invalid path format
              QMessageBox.critical(self, "Output Error", f"Invalid output path specified:\n{output_path}\nError: {e}")
              return False

        # --- Input/Output Overlap Check ---
        # This check is primarily relevant for Folder mode conversion
        if current_mode == "Folder":
            try:
                # Resolve paths to handle symlinks and relative paths consistently
                resolved_input = input_p.resolve(strict=True) # strict=True raises error if path doesn't exist
                resolved_output = output_p.resolve(strict=True)

                if resolved_input == resolved_output:
                    # Allow same dir for duration check, but warn for conversion
                    sender_button = self.sender() # Get the button that triggered this validation
                    is_conversion = sender_button == self.convert_btn
                    if is_conversion:
                        reply = QMessageBox.question(self, "Output Warning",
                                                  "Output folder is the same as the input folder.\n"
                                                  "Converting files in place is risky and may overwrite originals if errors occur.\n\n"
                                                  "It's strongly recommended to select a different output folder.\n\n"
                                                  "Continue conversion anyway?",
                                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                        if reply == QMessageBox.No: return False

                # Check if output is strictly inside input using Path.parents (more reliable than is_relative_to sometimes)
                elif resolved_input in resolved_output.parents:
                    sender_button = self.sender()
                    is_conversion = sender_button == self.convert_btn
                    if is_conversion:
                         reply = QMessageBox.question(self, "Output Warning",
                                                  f"The selected output folder:\n{output_path}\n"
                                                  f"is inside the input folder:\n{input_path}\n\n"
                                                  "This might lead to issues during conversion (e.g., converting already converted files if run again).\n"
                                                  "Consider using an output folder outside the input hierarchy.\n\n"
                                                  "Continue conversion anyway?",
                                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                         if reply == QMessageBox.No: return False

            except FileNotFoundError:
                 # This shouldn't happen if input/output existence checks above passed, but handle defensively
                 self.log("Warning: Could not resolve input/output paths for overlap check (path may have changed).")
            except OSError as e:
                 self.log(f"Warning: Could not fully resolve paths for overlap comparison: {e}")
            except Exception as e:
                 self.log(f"Warning: Error during input/output path overlap comparison: {e}")

        return True # Paths seem valid

    def start_conversion(self):
        self.mode = "File" if self.file_radio.isChecked() else "Folder" # Ensure mode is current
        # Pass self.convert_btn to validate_paths to help with context-specific warnings
        if not self.validate_paths():
            return

        input_path = self.input_line.text().strip()
        output_path = self.output_line.text().strip()
        self.log_text.clear()
        self.progress_bar.setValue(0)
        use_cuda = self.cuda_checkbox.isChecked()
        send_notify = self.notify_checkbox.isChecked()

        self.log(f"Starting conversion ({self.mode} mode)...")
        self.log(f"Input: {input_path}")
        self.log(f"Output Folder: {output_path}")
        self.log(f"Using CUDA: {use_cuda}")

        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "Busy", "A conversion task is already running.")
            return
        if self.duration_worker and self.duration_worker.isRunning():
             QMessageBox.warning(self, "Busy", "A duration check task is currently running.")
             return
        self.worker = None

        self.worker = ConversionWorker(input_path, output_path, self.mode, use_cuda, send_notify)
        self.worker.log_signal.connect(self._do_log)
        self.worker.progress_signal.connect(lambda value: self.progress_bar.setValue(int(value)))
        self.worker.finished_signal.connect(self.conversion_finished)

        self.set_ui_busy(True)
        self.worker.start()

    def conversion_finished(self, success: bool, aborted: bool):
        # Store worker reference temporarily to prevent race condition if user clicks again quickly
        finished_worker = self.worker
        self.worker = None # Clear worker reference *before* enabling UI

        self.set_ui_busy(False) # Enable UI

        if aborted:
            QMessageBox.warning(self, "Aborted", "Conversion process was aborted by the user.")
            self.progress_bar.setFormat("Aborted by user")
        elif success:
            QMessageBox.information(self, "Success", "Video conversion process finished successfully!")
            self.progress_bar.setFormat("Completed")
        else:
            QMessageBox.critical(self, "Error", "An error occurred during conversion. Please check the log and any '.error.log' or '.info.log' files in the output directory for details.")
            self.progress_bar.setFormat("Finished with errors")


    def start_duration_check(self):
        self.mode = "File" if self.file_radio.isChecked() else "Folder" # Ensure mode is current
        # Pass self.duration_btn to validate_paths
        if not self.validate_paths():
            return

        input_path = self.input_line.text().strip()
        output_path = self.output_line.text().strip() # Duration file goes into the selected output folder
        self.log_text.clear()
        self.progress_bar.setValue(0)

        self.log(f"Starting duration check ({self.mode} mode)...")
        self.log(f"Input: {input_path}")
        self.log(f"Output Folder for duration report: {output_path}")

        if self.duration_worker and self.duration_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A duration check task is already running.")
            return
        if self.worker and self.worker.isRunning():
             QMessageBox.warning(self, "Busy", "A conversion task is currently running.")
             return
        self.duration_worker = None

        self.duration_worker = DurationWorker(input_path, output_path, self.mode)
        self.duration_worker.log_signal.connect(self._do_log)
        self.duration_worker.progress_signal.connect(lambda value: self.progress_bar.setValue(int(value)))
        self.duration_worker.finished_signal.connect(self.duration_finished)

        self.set_ui_busy(True)
        self.duration_worker.start()

    def duration_finished(self, success: bool):
        # Store worker reference temporarily
        finished_worker = self.duration_worker
        self.duration_worker = None # Clear worker reference *before* enabling UI

        self.set_ui_busy(False) # Enable UI

        # Check internal flag for abort state *after* worker is done
        was_aborted = finished_worker and finished_worker._stop_event.is_set()

        if success:
            QMessageBox.information(self, "Duration Check Complete",
                                    f"Duration report created successfully in the output folder:\n{self.output_line.text().strip()}")
            self.progress_bar.setFormat("Completed")
        elif was_aborted:
             QMessageBox.warning(self, "Aborted", "Duration check was aborted by the user.")
             self.progress_bar.setFormat("Aborted by user")
        else:
             QMessageBox.critical(self, "Duration Check Error", "An error occurred during duration check. Please check the log.")
             self.progress_bar.setFormat("Finished with errors")


    def abort_process(self):
        """Stops the currently running worker (either conversion or duration)."""
        aborted_something = False
        if self.worker and self.worker.isRunning():
            self.log("Abort requested for conversion...")
            # Disable button immediately to prevent multiple clicks
            self.abort_btn.setEnabled(False)
            self.abort_btn.setText("Aborting...")
            self.worker.stop() # Signal the worker to stop
            aborted_something = True
        elif self.duration_worker and self.duration_worker.isRunning():
             self.log("Abort requested for duration check...")
             # Disable button immediately
             self.abort_btn.setEnabled(False)
             self.abort_btn.setText("Aborting...")
             self.duration_worker.stop() # Signal the worker to stop
             aborted_something = True

        if aborted_something:
             self.log("Abort signal sent. Waiting for task termination...")
             # UI state will be fully restored by the finished signal handler
        else:
            self.log("No active task to abort.")
            # Ensure abort button is disabled if no task is running
            self.abort_btn.setEnabled(False)
            self.abort_btn.setText("Abort Current Task")

    def closeEvent(self, event):
        """Ensure threads are stopped before closing."""
        running_worker = None
        task_name = ""

        if self.worker and self.worker.isRunning():
            running_worker = self.worker
            task_name = "conversion"
        elif self.duration_worker and self.duration_worker.isRunning():
            running_worker = self.duration_worker
            task_name = "duration check"

        if running_worker:
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         f"A {task_name} is in progress.\nAbort the task and exit the application?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.log(f"Aborting {task_name} due to application close request.")
                # Disable UI elements during forced shutdown
                self.set_ui_busy(True) # Disable most controls
                self.abort_btn.setText("Exiting...")
                self.abort_btn.setEnabled(False)

                running_worker.stop() # Send stop signal

                # Give the thread a moment to react and clean up
                if not running_worker.wait(4000): # Wait up to 4 seconds
                     self.log(f"Warning: {task_name.capitalize()} thread did not stop gracefully after 4 seconds.")
                     # Consider if more forceful termination is needed (tricky with subprocesses)

                event.accept() # Close the window
            else:
                event.ignore() # Keep window open
                return
        else:
            event.accept() # No running task, close normally


# -------------------------------
# Application Entry Point
# -------------------------------
if __name__ == "__main__":
    # --- Add instruction about natsort ---
    if not HAS_NATSORT:
        print("--------------------------------------------------------------------")
        print("INFO: For optimal natural sorting of filenames (e.g., 'Chapter 2' before 'Chapter 10'),")
        print("      it's recommended to install the 'natsort' library:")
        print("      pip install natsort")
        print("      (Falling back to basic alphanumeric sort)")
        print("--------------------------------------------------------------------")
    # -------------------------------------

    # Helps with scaling on high DPI displays if needed
    # QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    # QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    # Apply a style for a slightly more modern look (optional)
    app.setStyle('Fusion')
    window = ConverterWindow()
    window.show()
    sys.exit(app.exec_())
