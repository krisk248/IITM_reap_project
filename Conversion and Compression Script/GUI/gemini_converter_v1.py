<<<<<<< HEAD
import sys
import os
import subprocess
import threading
import datetime
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# Third-party libraries
try:
    import natsort
except ImportError:
    print("Error: 'natsort' library not found. Please install it: pip install natsort")
    sys.exit(1)
try:
    import requests
except ImportError:
    requests = None # Handle gracefully if not installed and ntfy not used
    print("Warning: 'requests' library not found. Ntfy notifications will be disabled.")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QRadioButton, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QMessageBox, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject

# -------------------------------
# Global Configuration
# -------------------------------
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv"} # Added more common ones
NTFY_TOPIC = "rclone_reap_iit" # Keep configurable if needed

# Find FFmpeg/FFprobe
try:
    import imageio_ffmpeg
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_BINARY = "ffmpeg" # Fallback to system PATH

# Try to find ffprobe relative to ffmpeg or in PATH
ffmpeg_path = Path(FFMPEG_BINARY)
ffprobe_path_guess = ffmpeg_path.parent / "ffprobe"
ffprobe_exe_path_guess = ffmpeg_path.parent / "ffprobe.exe"

# Prefer ffprobe next to ffmpeg if it exists
if ffprobe_path_guess.is_file():
    FFPROBE_BINARY = str(ffprobe_path_guess.resolve())
elif ffprobe_exe_path_guess.is_file(): # Check for .exe on Windows
    FFPROBE_BINARY = str(ffprobe_exe_path_guess.resolve())
else:
    # Check if ffprobe is in PATH using subprocess
    try:
        ffprobe_check = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, check=True, timeout=5)
        if ffprobe_check.returncode == 0:
             FFPROBE_BINARY = "ffprobe"
        else:
             raise FileNotFoundError # Simulate not found if return code != 0
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print("Error: ffprobe executable not found.")
        print(f"Looked near ffmpeg: {ffprobe_path_guess}{' (.exe)' if os.name == 'nt' else ''}")
        print("Also checked system PATH.")
        print("Please ensure ffprobe is installed and accessible.")
        # Exit or prompt user? Exiting for now.
        # QMessageBox.critical(None, "Error", "ffprobe not found. Please install FFmpeg/ffprobe and ensure it's in your PATH.")
        # sys.exit(1) # Exit if ffprobe is critical and not found
        FFPROBE_BINARY = "ffprobe" # Set default and let it fail later if really not found


# Duration Check Specific Config (Patterns removed as filtering is removed)
# CHAPTER_HEADER_PATTERN = re.compile(r"Chapter \d+[A-Za-z]? - .*", re.IGNORECASE)
# COURSE_INTRO_PATTERN = re.compile(r"Course Introduction.*", re.IGNORECASE)

# -------------------------------
# Helper Functions
# -------------------------------
def get_video_duration(input_file: Path) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    if not input_file.is_file():
        print(f"Error: Input file not found: {input_file}")
        return None
    command = [
        FFPROBE_BINARY, "-v", "error",
        "-select_streams", "v:0", # Look for video stream first
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_file),
    ]
    duration_str = None
    try:
        # Run with a timeout to prevent hangs on corrupted files
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', timeout=30)
        duration_str = result.stdout.strip()
        if not duration_str or duration_str == "N/A":
             # Try getting duration from container format if stream duration fails
            command = [
                FFPROBE_BINARY, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(input_file),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', timeout=30)
            duration_str = result.stdout.strip()
            if not duration_str or duration_str == "N/A":
                 print(f"Warning: Could not determine duration for {input_file.name}")
                 return 0.0 # Treat as 0 duration if undetectable
        return float(duration_str)
    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe for {input_file.name}: {e}")
        stderr_output = e.stderr.strip() if e.stderr else "No stderr output"
        print(f"Stderr: {stderr_output}")
        # If stderr contains "No such file or directory", the input file might be the issue
        if "No such file or directory" in stderr_output:
            print(f"Check if file exists and path is correct: {input_file}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Error: ffprobe timed out processing {input_file.name}. File might be corrupted or too complex.")
        return None
    except ValueError:
        print(f"Error parsing duration for {input_file.name}. Got: '{duration_str}'")
        return None
    except FileNotFoundError:
        print(f"Error: '{FFPROBE_BINARY}' command not found. Cannot get duration.")
        # Potentially re-raise or handle globally
        raise # Re-raise critical error
    except Exception as e:
        print(f"Unexpected error getting duration for {input_file.name}: {e}")
        return None

def format_duration(seconds: Optional[float]) -> str:
    """Return a string in 'H hours M min S sec' format."""
    if seconds is None or seconds < 0:
        return "N/A"
    if seconds == 0:
        return "0 sec"

    total_seconds = int(round(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if secs > 0 or not parts: # Show seconds if non-zero or if H/M were zero
        parts.append(f"{secs} sec")

    return " ".join(parts)


def write_error_log(log_file_path: Path, input_file: Path, error_output: str):
    """Write error details to a log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure log dir exists
        with open(log_file_path, "a", encoding="utf-8") as f: # Append mode is often better
            f.write(f"[{timestamp}] Error processing file: {input_file}\n")
            f.write(f"Command attempted (simplified): ffmpeg ... -i \"{input_file}\" ...\n")
            f.write("-" * 20 + " FFmpeg Output " + "-" * 20 + "\n")
            f.write(error_output)
            f.write("\n" + "=" * 60 + "\n")
    except Exception as e:
        print(f"Critical: Failed to write error log to {log_file_path}: {e}")

def send_ntfy_notification(message: str, topic: str, log_emitter: Optional[pyqtSignal] = None):
    """Sends a notification to an ntfy topic."""
    if not requests:
        if log_emitter:
            log_emitter.emit("Ntfy skipped: 'requests' library not installed.")
        else:
            print("Ntfy skipped: 'requests' library not installed.")
        return

    if not topic:
        if log_emitter:
            log_emitter.emit("Ntfy skipped: No topic configured.")
        else:
            print("Ntfy skipped: No topic configured.")
        return

    url = f"https://ntfy.sh/{topic}"
    try:
        response = requests.post(url, data=message.encode("utf-8"), timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        if log_emitter:
            log_emitter.emit("Ntfy notification sent successfully!")
        else:
            print("Ntfy notification sent successfully!")
    except requests.exceptions.RequestException as e:
        if log_emitter:
            log_emitter.emit(f"Error sending ntfy notification: {e}")
        else:
            print(f"Error sending ntfy notification: {e}")
    except Exception as e:
        # Catch any other unexpected errors during notification
        if log_emitter:
            log_emitter.emit(f"Unexpected error sending ntfy notification: {e}")
        else:
            print(f"Unexpected error sending ntfy notification: {e}")

# -------------------------------
# Base Worker Thread
# -------------------------------
class BaseWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int) # Use int for progress bar (0-100)
    finished_signal = pyqtSignal(bool, bool)  # (success, aborted)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._is_aborted = False

    def stop(self):
        self._is_aborted = True
        self._stop_event.set()

    def is_aborted(self):
        return self._is_aborted

    def run(self):
        # Base run method - subclasses should implement their logic
        # and emit signals appropriately. Remember to check self._stop_event.is_set()
        # periodically in loops.
        pass

# -------------------------------
# Conversion Worker Thread
# -------------------------------
class ConversionWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited
    # log_signal(message: str) inherited

    def __init__(self, input_path: str, output_path: str, mode: str, use_cuda: bool, send_notify: bool):
        super().__init__()
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.mode = mode  # "File" or "Folder"
        self.use_cuda = use_cuda
        self.send_notify = send_notify
        self.converted_files = []  # To track created files for cleanup on abort

    def run(self):
        start_time = datetime.datetime.now()
        self.log_signal.emit(f"Starting conversion process at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        success = False
        try:
            if not self.output_path.exists():
                 self.log_signal.emit(f"Creating output directory: {self.output_path}")
                 self.output_path.mkdir(parents=True, exist_ok=True)

            if self.mode == "File":
                if not self.input_path.is_file():
                     raise FileNotFoundError(f"Input file not found: {self.input_path}")
                success = self.process_file(self.input_path, self.output_path)
            else: # Folder mode
                if not self.input_path.is_dir():
                     raise NotADirectoryError(f"Input folder not found: {self.input_path}")
                success = self.process_folder(self.input_path, self.output_path)

            if self.is_aborted():
                self.log_signal.emit("Conversion process aborted by user.")
                success = False # Mark as not successful if aborted
            elif success:
                end_time = datetime.datetime.now()
                total_time = end_time - start_time
                self.log_signal.emit(f"Conversion completed successfully at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.log_signal.emit(f"Total time taken: {str(total_time).split('.')[0]}") # Format timedelta nicely
                if self.send_notify:
                    send_ntfy_notification("Video conversion completed successfully.", NTFY_TOPIC, self.log_signal)
            else:
                 self.log_signal.emit("Conversion finished with errors or no files processed.")

        except FileNotFoundError as e:
             self.log_signal.emit(f"Error: {e}")
             success = False
        except NotADirectoryError as e:
            self.log_signal.emit(f"Error: {e}")
            success = False
        except Exception as e:
            self.log_signal.emit(f"An unexpected error occurred during conversion: {e}")
            import traceback
            self.log_signal.emit(traceback.format_exc()) # Log full traceback for debugging
            success = False
        finally:
             # Emit finished signal with success status and aborted flag
             self.finished_signal.emit(success, self.is_aborted())

    def process_file(self, input_file: Path, output_dir: Path) -> bool:
        """Processes a single file."""
        if self.is_aborted(): return False
        if input_file.suffix.lower() not in VIDEO_EXTENSIONS:
            self.log_signal.emit(f"Skipping non-video file: {input_file.name}")
            return True # Not an error, just skipping

        out_file = output_dir / f"{input_file.stem}.mp4" # Standardize output to mp4
        self.log_signal.emit("-" * 30)
        self.log_signal.emit(f"Processing: {input_file.name}")
        self.log_signal.emit(f"Outputting to: {out_file}")
        result = self.convert_video_file(input_file, out_file)
        self.progress_signal.emit(100) # Single file means 100% when done/failed
        return result

    def process_folder(self, input_dir: Path, output_dir: Path) -> bool:
        """Processes all video files in a folder recursively."""
        self.log_signal.emit(f"Scanning folder: {input_dir}")
        try:
            video_files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            # Sort naturally for predictable processing order
            video_files = natsort.natsorted(video_files, key=lambda x: x.as_posix())
        except Exception as e:
            self.log_signal.emit(f"Error scanning folder: {e}")
            return False

        total_files = len(video_files)
        if total_files == 0:
            self.log_signal.emit("No video files found in the selected folder.")
            return True # Not an error, just nothing to do

        self.log_signal.emit(f"Found {total_files} video files to process.")
        overall_success = True

        for idx, file_path in enumerate(video_files):
            if self.is_aborted():
                overall_success = False
                break

            self.log_signal.emit("-" * 30)
            self.log_signal.emit(f"Processing file {idx + 1}/{total_files}: {file_path.name}")

            # Calculate relative path and create corresponding output directory
            try:
                rel_path = file_path.relative_to(input_dir).parent
            except ValueError:
                self.log_signal.emit(f"Warning: Could not determine relative path for {file_path}. Outputting to base output folder.")
                rel_path = Path(".") # Fallback to avoid error

            target_dir = output_dir / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)

            out_file = target_dir / f"{file_path.stem}.mp4"
            self.log_signal.emit(f"Outputting to: {out_file}")

            file_success = self.convert_video_file(file_path, out_file)
            if not file_success:
                overall_success = False # Mark overall as failed if any file fails

            # Update overall progress (even if file failed, we processed it)
            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        self.log_signal.emit("-" * 30)
        if not self.is_aborted():
             self.log_signal.emit("Folder processing complete.")

        return overall_success

    def convert_video_file(self, input_file: Path, output_file: Path) -> bool:
        """Performs the actual FFmpeg conversion for a single file."""
        duration = None
        try:
            duration = get_video_duration(input_file)
        except FileNotFoundError: # Catch if ffprobe binary itself is missing
             self.log_signal.emit(f"Critical Error: '{FFPROBE_BINARY}' not found. Cannot determine video duration.")
             return False # Hard fail if ffprobe isn't available

        if duration is None: # Handle ffprobe error/timeout for this specific file
            self.log_signal.emit(f"Skipping file (error reading duration): {input_file.name}")
            log_file = output_file.with_suffix(".ffprobe_error.log")
            write_error_log(log_file, input_file, "Failed to get video duration using ffprobe (possible error or timeout).")
            return False
        if duration == 0:
             self.log_signal.emit(f"Skipping file (zero or undetectable duration): {input_file.name}")
             return True # Treat as success (skipped intentionally)


        # Base command parts
        command = [FFMPEG_BINARY, "-y"] # -y overwrites output without asking

        # Input and Hardware Acceleration (if applicable)
        if self.use_cuda:
            # Specify input hwaccel AND output format if needed
            # Using -hwaccel cuda often sufficient for NVDEC -> NVENC pipelines
            command.extend(["-hwaccel", "cuda"]) # "-hwaccel_output_format", "cuda" might be needed depending on filters
        command.extend(["-i", str(input_file)])

        # Filters (Scaling)
        scale_filter = "scale=-2:720" # Default software scale
        if self.use_cuda:
             # Check common CUDA filters. scale_cuda preferred if available. scale_npp as fallback.
             # This requires checking ffmpeg capabilities, which adds complexity.
             # Simpler approach: Use software scale, often works fine even with hwaccel.
             # Or just try scale_cuda and let it fail if not supported.
             # command.extend(["-vf", "scale_cuda=-2:720:interp_algo=lanczos"]) # Example CUDA scale
             command.extend(["-vf", scale_filter]) # Stick with software scale for broader compatibility
        else:
            command.extend(["-vf", scale_filter]) # Software scaling

        # Video Codec and Options
        if self.use_cuda:
            command.extend(["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-qmin", "0", "-qmax", "51", "-b:v", "0", "-profile:v", "main"])
             # Example NVENC settings: preset p6 (medium), tune hq, ConstQP mode (cq 23). Adjust as needed.
        else:
            command.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-profile:v", "main"])
            # CRF 23 is a good balance.

        # Audio Codec and Options
        command.extend(["-c:a", "aac", "-b:a", "192k"]) # 192k AAC stereo

        # Output file and Progress Reporting
        command.extend([str(output_file), "-progress", "pipe:1", "-nostats"])

        self.log_signal.emit(f"FFmpeg command (simplified): {' '.join(command[:5])} ... {' '.join(command[-4:])}")

        try:
            # Use CREATE_NO_WINDOW flag on Windows to prevent console pop-up
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace',
                                       creationflags=creationflags)
            self.converted_files.append(output_file) # Track for potential cleanup

            stdout_lines = [] # Collect output for error logging if needed

            while True:
                if self.is_aborted():
                    self.log_signal.emit(f"Attempting to terminate FFmpeg process for {input_file.name}...")
                    process.terminate() # Ask ffmpeg to stop gracefully first
                    try:
                         process.wait(timeout=5) # Wait a bit
                         if process.poll() is None: # Still running?
                              self.log_signal.emit("FFmpeg did not terminate gracefully, killing...")
                              process.kill() # Force stop
                    except subprocess.TimeoutExpired:
                         self.log_signal.emit("FFmpeg termination timed out, killing...")
                         process.kill()
                    self.log_signal.emit(f"Aborted conversion for {input_file.name}")
                    return False # Signal abortion

                # Read line by line, non-blocking if possible (though readline usually blocks)
                line = process.stdout.readline()
                if not line:
                    # Check if process finished
                    if process.poll() is not None:
                        break
                    # If no line and process still running, maybe it stalled? (less likely with pipe:1)
                    # Or maybe just waiting for more data. Continue reading.
                    continue

                stdout_lines.append(line) # Store line for potential error log
                line = line.strip()

                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = int(line.split("=")[1])
                        current_time = out_time_ms / 1_000_000
                        progress = min(int(current_time / duration * 100), 100) if duration > 0 else 0
                        # In file mode, this directly updates the main bar
                        if self.mode == "File":
                            self.progress_signal.emit(progress)
                        # Note: Per-file progress in folder mode isn't explicitly shown on progress bar,
                        # only overall progress is updated in process_folder method.
                    except (ValueError, IndexError, ZeroDivisionError):
                        pass # Ignore malformed progress lines
                elif line.startswith("progress=end"):
                     if self.mode == "File":
                         self.progress_signal.emit(100)
                     break # FFmpeg signals completion

            # Ensure process has fully finished and capture return code
            return_code = process.wait()

            if return_code != 0:
                self.log_signal.emit(f"Error: FFmpeg failed for {input_file.name} (exit code {return_code})")
                # Read any remaining output (might not be much if already read line-by-line)
                remaining_output = process.stdout.read()
                stdout_lines.append(remaining_output)
                error_output = "".join(stdout_lines)
                log_file = output_file.with_suffix(".ffmpeg_error.log")
                write_error_log(log_file, input_file, error_output)
                self.log_signal.emit(f"Error details logged to: {log_file}")
                # Clean up potentially broken output file
                if output_file in self.converted_files: self.converted_files.remove(output_file)
                if output_file.exists():
                    try:
                        output_file.unlink()
                        self.log_signal.emit(f"Deleted incomplete output file: {output_file.name}")
                    except OSError as e:
                        self.log_signal.emit(f"Warning: Could not delete incomplete file {output_file.name}: {e}")
                return False # Failure
            else:
                self.log_signal.emit(f"Successfully converted {input_file.name}")
                if self.mode == "File":
                    self.progress_signal.emit(100)
                return True # Success

        except FileNotFoundError:
             self.log_signal.emit(f"Error: '{FFMPEG_BINARY}' command not found. Please ensure FFmpeg is installed and in your PATH.")
             return False
        except Exception as e:
             self.log_signal.emit(f"Error running FFmpeg process for {input_file.name}: {e}")
             import traceback
             self.log_signal.emit(traceback.format_exc())
             log_file = output_file.with_suffix(".python_error.log")
             write_error_log(log_file, input_file, f"Python Exception:\n{traceback.format_exc()}")
             self.log_signal.emit(f"Python error details logged to: {log_file}")
             return False


# -------------------------------
# Duration Scan Worker
# -------------------------------
class DurationScanWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited - Represents scanning progress
    # log_signal(message: str) inherited
    files_scanned_signal = pyqtSignal(list) # Emits list[Path] of found video files

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = Path(input_path)

    def run(self):
        self.log_signal.emit(f"Scanning folder for videos: {self.input_path}")
        if not self.input_path.is_dir():
            self.log_signal.emit("Error: Selected path is not a valid directory.")
            self.finished_signal.emit(False, self.is_aborted())
            return

        video_files = []
        success = True
        try:
            # Estimate total items for progress (can be inaccurate with deep trees/symlinks)
            # A simple count of initial items might be faster for large directories
            # Let's use a generator approach for potentially large directories
            all_items_gen = self.input_path.rglob("*")
            # To get progress, we need a count, which means iterating twice or storing all.
            # For simplicity, let's list them first. Consider iterative approach if memory is a concern.
            all_files_list = list(all_items_gen)
            total_items = len(all_files_list)
            processed_items = 0

            for item in all_files_list:
                if self.is_aborted():
                     self.log_signal.emit("Scanning aborted.")
                     success = False
                     break

                processed_items += 1
                if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                    video_files.append(item)

                if total_items > 0:
                    progress = int((processed_items / total_items) * 100)
                    # Throttle progress updates slightly for performance
                    if processed_items % 50 == 0 or progress == 100 or processed_items == total_items:
                         self.progress_signal.emit(progress)

            if success:
                # Sort naturally before emitting
                sorted_files = natsort.natsorted(video_files, key=lambda x: x.as_posix())
                self.log_signal.emit(f"Scan complete. Found {len(sorted_files)} video files.")
                self.files_scanned_signal.emit(sorted_files)
            else:
                 # Emit empty list if aborted during scan
                 self.files_scanned_signal.emit([])


        except Exception as e:
            self.log_signal.emit(f"Error during folder scan: {e}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
            success = False
            self.files_scanned_signal.emit([]) # Emit empty list on error

        self.finished_signal.emit(success, self.is_aborted())


# -------------------------------
# Duration Calculation Worker
# -------------------------------
class DurationCalculateWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited - Represents calculation progress
    # log_signal(message: str) inherited
    file_duration_signal = pyqtSignal(int, str) # row_index, formatted_duration_str
    total_duration_signal = pyqtSignal(str) # formatted_total_duration_str

    def __init__(self, files_to_check: List[Tuple[int, Path]], report_folder: Path, report_filename_base: str):
        super().__init__()
        self.files_to_check = files_to_check # List of (row_index, file_path)
        self.report_folder = report_folder # Folder where report will be saved (now the input folder)
        self.report_filename_base = report_filename_base

    def run(self):
        total_files = len(self.files_to_check)
        if total_files == 0:
            self.log_signal.emit("No files selected for duration check.")
            self.finished_signal.emit(True, self.is_aborted()) # Success, but nothing done
            return

        self.log_signal.emit(f"Calculating duration for {total_files} selected files...")
        # report_folder is expected to exist (it's the input folder)

        durations: Dict[Path, Optional[float]] = {}
        total_duration_sec = 0.0
        success = True
        ffprobe_found = True # Flag to track if ffprobe is usable

        for idx, (row_index, file_path) in enumerate(self.files_to_check):
            if self.is_aborted():
                self.log_signal.emit("Duration calculation aborted.")
                success = False
                break

            self.log_signal.emit(f"Checking [{idx+1}/{total_files}]: {file_path.name}")
            duration_sec = None
            try:
                duration_sec = get_video_duration(file_path)
            except FileNotFoundError: # Catch ffprobe not found error from helper
                self.log_signal.emit(f"Critical Error: '{FFPROBE_BINARY}' not found. Aborting duration check.")
                ffprobe_found = False
                success = False
                break # Stop processing further files
            except Exception as e: # Catch other unexpected errors from helper
                self.log_signal.emit(f"Unexpected error getting duration for {file_path.name}: {e}")
                # Logged within helper, continue processing others if possible

            durations[file_path] = duration_sec
            formatted_duration = format_duration(duration_sec)
            self.file_duration_signal.emit(row_index, formatted_duration) # Update UI regardless of success

            if duration_sec is not None and duration_sec > 0:
                 total_duration_sec += duration_sec
            elif duration_sec is None:
                 self.log_signal.emit(f"Warning: Failed to get duration for {file_path.name}. It will not be included in the total.")
                 # Marked as N/A in UI, total won't include it.
            # else duration_sec == 0 (already logged by helper if undetectable)

            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        if not ffprobe_found:
             # If ffprobe wasn't found, finish with failure state
             self.finished_signal.emit(False, self.is_aborted())
             return

        if success and not self.is_aborted(): # Only calculate total and write report if not aborted and no critical errors
            formatted_total = format_duration(total_duration_sec)
            self.total_duration_signal.emit(formatted_total)
            self.log_signal.emit(f"Total calculated duration for selected files: {formatted_total}")

            # --- Generate Report File ---
            # Ensure base name is safe for filesystem
            safe_base_name = re.sub(r'[\\/*?:"<>|]', '_', self.report_filename_base) # Replace invalid chars
            report_file = self.report_folder / f"{safe_base_name}_duration.txt"
            self.log_signal.emit(f"Generating report file: {report_file}")
            try:
                # Sort the files based on the original order they were passed (reflects UI selection order/natural sort)
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(f"Duration Report for: {self.report_filename_base}\n")
                    f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total files selected: {len(self.files_to_check)}\n")
                    f.write("-" * 30 + "\n\n")

                    # Use the original sorted list passed to the worker
                    for _, file_path in self.files_to_check:
                         duration = durations.get(file_path) # Get calculated duration (might be None)
                         f.write(f"{file_path.name} -> {format_duration(duration)}\n")

                    f.write("\n" + "=" * 30 + "\n")
                    f.write(f"Total duration of the selection -> {formatted_total}\n")
                self.log_signal.emit("Report file generated successfully.")

            except Exception as e:
                self.log_signal.emit(f"Error writing duration report file '{report_file}': {e}")
                success = False # Mark as failed if report writing fails

        self.finished_signal.emit(success, self.is_aborted())


# -------------------------------
# Main GUI Window
# -------------------------------
class ConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kannan's Media Toolkit")
        self.setGeometry(100, 100, 850, 700) # Adjusted size

        # Worker threads - keep track of active ones
        self.conversion_worker: Optional[ConversionWorker] = None
        self.duration_scan_worker: Optional[DurationScanWorker] = None
        self.duration_calc_worker: Optional[DurationCalculateWorker] = None

        self._init_ui()

    def _init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create Tab Widgets
        self.conversion_tab = QWidget()
        self.duration_tab = QWidget()

        # Add tabs to QTabWidget
        self.tabs.addTab(self.conversion_tab, "Video Conversion")
        self.tabs.addTab(self.duration_tab, "Duration Check")

        # Populate each tab
        self._populate_conversion_tab()
        self._populate_duration_tab()

    # --- Conversion Tab UI ---
    def _populate_conversion_tab(self):
        layout = QVBoxLayout(self.conversion_tab)

        # Mode Group
        mode_group_conv = QGroupBox("Conversion Mode")
        mode_layout_conv = QHBoxLayout()
        self.file_radio_conv = QRadioButton("Single File")
        self.folder_radio_conv = QRadioButton("Entire Folder")
        self.file_radio_conv.setChecked(True)
        mode_layout_conv.addWidget(self.file_radio_conv)
        mode_layout_conv.addWidget(self.folder_radio_conv)
        mode_group_conv.setLayout(mode_layout_conv)
        layout.addWidget(mode_group_conv)

        # Input Selection
        input_group_conv = QGroupBox("Input Source")
        input_layout_conv = QHBoxLayout()
        self.input_line_conv = QLineEdit()
        self.input_line_conv.setPlaceholderText("Select input file or folder...")
        self.browse_input_btn_conv = QPushButton("Browse") # Store ref
        self.browse_input_btn_conv.clicked.connect(self.browse_input_conversion)
        input_layout_conv.addWidget(self.input_line_conv)
        input_layout_conv.addWidget(self.browse_input_btn_conv)
        input_group_conv.setLayout(input_layout_conv)
        layout.addWidget(input_group_conv)

        # Output Selection
        output_group_conv = QGroupBox("Output Folder")
        output_layout_conv = QHBoxLayout()
        self.output_line_conv = QLineEdit()
        self.output_line_conv.setPlaceholderText("Select output folder...")
        self.browse_output_btn_conv = QPushButton("Browse") # Store ref
        self.browse_output_btn_conv.clicked.connect(lambda: self.browse_folder(self.output_line_conv))
        output_layout_conv.addWidget(self.output_line_conv)
        output_layout_conv.addWidget(self.browse_output_btn_conv)
        output_group_conv.setLayout(output_layout_conv)
        layout.addWidget(output_group_conv)

        # Options
        options_group_conv = QGroupBox("Options")
        options_layout_conv = QVBoxLayout() # Use QVBoxLayout for better spacing
        self.cuda_checkbox_conv = QCheckBox("Use NVIDIA CUDA acceleration (if available)")
        self.notify_checkbox_conv = QCheckBox("Send ntfy notification on completion")
        self.notify_checkbox_conv.setEnabled(requests is not None) # Disable if requests not installed
        options_layout_conv.addWidget(self.cuda_checkbox_conv)
        options_layout_conv.addWidget(self.notify_checkbox_conv)
        options_group_conv.setLayout(options_layout_conv)
        layout.addWidget(options_group_conv)

        # Action Buttons & Progress
        action_layout_conv = QHBoxLayout()
        self.convert_btn = QPushButton("Start Conversion")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.abort_btn_conv = QPushButton("Abort Conversion")
        self.abort_btn_conv.clicked.connect(self.abort_conversion)
        self.abort_btn_conv.setEnabled(False)
        action_layout_conv.addWidget(self.convert_btn)
        action_layout_conv.addWidget(self.abort_btn_conv)
        layout.addLayout(action_layout_conv)

        self.progress_bar_conv = QProgressBar()
        self.progress_bar_conv.setValue(0)
        layout.addWidget(self.progress_bar_conv)

        # Log Area
        self.log_text_conv = QTextEdit()
        self.log_text_conv.setReadOnly(True)
        self.log_text_conv.setLineWrapMode(QTextEdit.WidgetWidth) # Better wrapping
        layout.addWidget(self.log_text_conv)

        self.conversion_tab.setLayout(layout) # Set the layout for the tab

    # --- Duration Check Tab UI ---
    def _populate_duration_tab(self):
        layout = QVBoxLayout(self.duration_tab)

        # Input Folder Selection (Now the only folder needed)
        input_group_dur = QGroupBox("Video Folder (Report will be saved here)") # Updated title
        input_layout_dur = QHBoxLayout()
        self.input_line_dur = QLineEdit()
        self.input_line_dur.setPlaceholderText("Select folder containing videos...")
        self.browse_input_btn_dur = QPushButton("Browse Folder") # Store ref
        self.browse_input_btn_dur.clicked.connect(lambda: self.browse_folder(self.input_line_dur))
        input_layout_dur.addWidget(self.input_line_dur)
        input_layout_dur.addWidget(self.browse_input_btn_dur)
        input_group_dur.setLayout(input_layout_dur)
        layout.addWidget(input_group_dur)

        # Scan Button (Moved out of removed filter group)
        scan_layout = QHBoxLayout() # Layout for just the scan button
        self.scan_folder_btn = QPushButton("Scan Folder for Videos")
        self.scan_folder_btn.clicked.connect(self.start_duration_scan)
        scan_layout.addWidget(self.scan_folder_btn)
        scan_layout.addStretch() # Push button to the left
        layout.addLayout(scan_layout)

        # File List Table
        table_group = QGroupBox("Video Files Found (Check/Uncheck to include in calculation)") # Updated instructions
        table_layout = QVBoxLayout()
        self.select_all_checkbox_dur = QCheckBox("Select/Deselect All")
        self.select_all_checkbox_dur.stateChanged.connect(self.toggle_select_all_duration)
        table_layout.addWidget(self.select_all_checkbox_dur)

        self.duration_table = QTableWidget()
        self.duration_table.setColumnCount(3)
        self.duration_table.setHorizontalHeaderLabels([" ", "File Name (relative to input folder)", "Duration"])
        self.duration_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Stretch filename column
        self.duration_table.setColumnWidth(0, 40) # Checkbox column width
        self.duration_table.setColumnWidth(2, 150) # Duration column width
        self.duration_table.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only except checkbox
        self.duration_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.duration_table.itemChanged.connect(self.duration_table_item_changed) # To handle checkbox clicks
        table_layout.addWidget(self.duration_table)
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)

        # Action Buttons & Progress
        action_layout_dur = QHBoxLayout()
        self.calculate_dur_btn = QPushButton("Calculate Selected Durations & Save Report") # Updated text
        self.calculate_dur_btn.clicked.connect(self.start_duration_calculation)
        self.calculate_dur_btn.setEnabled(False) # Enable after scanning
        self.abort_btn_dur = QPushButton("Abort Task")
        self.abort_btn_dur.clicked.connect(self.abort_duration_task)
        self.abort_btn_dur.setEnabled(False)
        action_layout_dur.addWidget(self.calculate_dur_btn)
        action_layout_dur.addWidget(self.abort_btn_dur)
        layout.addLayout(action_layout_dur)

        self.progress_bar_dur = QProgressBar()
        self.progress_bar_dur.setValue(0)
        layout.addWidget(self.progress_bar_dur)

         # Total Duration Display
        self.total_duration_label = QLabel("Total Duration of Selection: N/A")
        self.total_duration_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.total_duration_label)

        # Log Area
        self.log_text_dur = QTextEdit()
        self.log_text_dur.setReadOnly(True)
        self.log_text_dur.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_text_dur)

        self.duration_tab.setLayout(layout)

        # Store scanned files data separately from the table
        self._all_scanned_files: List[Path] = []
        self._row_map_dur: Dict[int, Path] = {} # Maps table row index to original Path


    # --- Common GUI Helpers ---
    def browse_folder(self, line_edit_widget: QLineEdit):
        """Opens a folder dialog and sets the path in the QLineEdit."""
        # Use the current value as starting directory if valid
        current_path = line_edit_widget.text().strip()
        start_dir = current_path if os.path.isdir(current_path) else ""

        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
        if folder_path:
            line_edit_widget.setText(folder_path)

    def log_message(self, message: str, log_widget: QTextEdit):
        """Appends a message to the specified log widget."""
        log_widget.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")
        # Auto-scroll to the bottom (optional)
        log_widget.verticalScrollBar().setValue(log_widget.verticalScrollBar().maximum())


    # --- Conversion Tab Logic ---
    def log_conv(self, message: str):
        self.log_message(message, self.log_text_conv)

    def browse_input_conversion(self):
        current_input = self.input_line_conv.text().strip()
        start_dir = ""
        if self.file_radio_conv.isChecked():
            if os.path.isfile(current_input):
                start_dir = os.path.dirname(current_input)
            elif os.path.isdir(current_input):
                 start_dir = current_input # Use if user switched mode after selecting folder
            # Use VIDEO_EXTENSIONS to create the filter string
            ext_filter = "Video Files (" + " ".join("*" + ext for ext in VIDEO_EXTENSIONS) + ");;All Files (*)"
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", start_dir, ext_filter)
            if file_path:
                self.input_line_conv.setText(file_path)
        else: # Folder mode
            if os.path.isdir(current_input):
                start_dir = current_input
            elif os.path.isfile(current_input):
                 start_dir = os.path.dirname(current_input)
            self.browse_folder(self.input_line_conv)

    def start_conversion(self):
        if self.conversion_worker and self.conversion_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A conversion process is already running.")
            return

        input_path_str = self.input_line_conv.text().strip()
        output_path_str = self.output_line_conv.text().strip()
        mode = "File" if self.file_radio_conv.isChecked() else "Folder"

        # Validation
        if not input_path_str:
            QMessageBox.critical(self, "Error", f"Please select an input {mode.lower()}.")
            return
        input_path = Path(input_path_str)
        if mode == "File" and not input_path.is_file():
             QMessageBox.critical(self, "Error", f"Input file not found:\n{input_path}")
             return
        if mode == "Folder" and not input_path.is_dir():
            QMessageBox.critical(self, "Error", f"Input folder not found:\n{input_path}")
            return

        if not output_path_str:
            QMessageBox.critical(self, "Error", "Please select an output folder.")
            return
        output_path = Path(output_path_str)
        if not output_path.exists():
             reply = QMessageBox.question(self, "Create Folder?",
                                          f"Output folder does not exist:\n{output_path}\n\nCreate it?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
             if reply == QMessageBox.Yes:
                 try:
                     output_path.mkdir(parents=True, exist_ok=True)
                     self.log_conv(f"Created output directory: {output_path}")
                 except Exception as e:
                     QMessageBox.critical(self, "Error", f"Could not create output folder:\n{e}")
                     return
             else:
                 return # User chose not to create
        elif not output_path.is_dir():
             QMessageBox.critical(self, "Error", f"Output path exists but is not a folder:\n{output_path}")
             return

        # Clear logs and progress
        self.log_text_conv.clear()
        self.progress_bar_conv.setValue(0)

        use_cuda = self.cuda_checkbox_conv.isChecked()
        send_notify = self.notify_checkbox_conv.isChecked()

        # Setup and start worker
        self.conversion_worker = ConversionWorker(str(input_path), str(output_path), mode, use_cuda, send_notify)
        self.conversion_worker.log_signal.connect(self.log_conv)
        self.conversion_worker.progress_signal.connect(lambda p: self.progress_bar_conv.setValue(p))
        self.conversion_worker.finished_signal.connect(self.conversion_finished)

        # Update UI state
        self.set_conversion_ui_active(True)

        self.conversion_worker.start()

    def set_conversion_ui_active(self, active: bool):
        """Enable/disable conversion UI elements based on running state."""
        self.convert_btn.setEnabled(not active)
        self.abort_btn_conv.setEnabled(active)
        # Disable input/output browsing and options while running
        self.input_line_conv.setEnabled(not active)
        self.output_line_conv.setEnabled(not active)
        self.browse_input_btn_conv.setEnabled(not active)
        self.browse_output_btn_conv.setEnabled(not active)
        self.file_radio_conv.setEnabled(not active)
        self.folder_radio_conv.setEnabled(not active)
        self.cuda_checkbox_conv.setEnabled(not active)
        self.notify_checkbox_conv.setEnabled(not active and requests is not None)
        # Prevent switching tabs while busy? (Optional, can be annoying)
        # self.tabs.setEnabled(not active)

    def conversion_finished(self, success: bool, aborted: bool):
        self.set_conversion_ui_active(False)
        self.progress_bar_conv.setValue(100 if success and not aborted else self.progress_bar_conv.value()) # Show 100 on success

        if aborted:
            QMessageBox.warning(self, "Aborted", "Conversion process was aborted.")
            self.log_conv("Cleaning up partial files due to abort...")
            self.cleanup_partial_files()
        elif success:
            QMessageBox.information(self, "Complete", "Conversion finished successfully!")
        else:
            QMessageBox.critical(self, "Error", "Conversion finished with errors. Check the log for details.")

        self.conversion_worker = None # Clear worker reference


    def abort_conversion(self):
        if self.conversion_worker and self.conversion_worker.isRunning():
            self.log_conv("Abort requested for conversion...")
            self.conversion_worker.stop()
            # UI update (disabling abort button etc.) happens in finished_signal handler
        else:
             self.log_conv("No active conversion process to abort.")


    def cleanup_partial_files(self):
        if self.conversion_worker:
            cleaned_count = 0
            # Use a copy of the list in case it's modified elsewhere (though unlikely here)
            files_to_check = list(self.conversion_worker.converted_files)
            for file_path_obj in files_to_check:
                 file_path = Path(file_path_obj) # Ensure it's a Path object
                 try:
                    # Check existence again right before deleting
                    if file_path.exists() and file_path.is_file():
                        file_path.unlink()
                        self.log_conv(f"Deleted partial file: {file_path.name}")
                        cleaned_count += 1
                 except Exception as e:
                    self.log_conv(f"Error deleting partial file {file_path.name}: {e}")
            if cleaned_count > 0:
                 self.log_conv(f"Cleaned up {cleaned_count} partial file(s).")
            else:
                 self.log_conv("No partial files found to clean up (or already deleted).")
            # Clear the list in the worker after attempting cleanup
            self.conversion_worker.converted_files.clear()
        else:
             self.log_conv("Cleanup skipped: No conversion worker context found.")


    # --- Duration Check Tab Logic ---
    def log_dur(self, message: str):
        self.log_message(message, self.log_text_dur)

    def set_duration_scan_ui_active(self, active: bool):
        """Enable/disable UI during duration scan."""
        self.scan_folder_btn.setEnabled(not active)
        self.input_line_dur.setEnabled(not active)
        self.browse_input_btn_dur.setEnabled(not active)
        # Disable calc button during scan
        self.calculate_dur_btn.setEnabled(not active and self.duration_table.rowCount() > 0)
        self.abort_btn_dur.setEnabled(active) # Abort applies to scan now
        # Disable table interaction during scan
        self.select_all_checkbox_dur.setEnabled(not active and self.duration_table.rowCount() > 0)
        self.duration_table.setEnabled(not active)
        # self.tabs.setEnabled(not active) # Optional: prevent tab switching

    def set_duration_calc_ui_active(self, active: bool):
        """Enable/disable UI during duration calculation."""
        self.calculate_dur_btn.setEnabled(not active and self.duration_table.rowCount() > 0)
        # Disable scan button and folder selection during calculation
        self.scan_folder_btn.setEnabled(not active)
        self.input_line_dur.setEnabled(not active)
        self.browse_input_btn_dur.setEnabled(not active)
        self.abort_btn_dur.setEnabled(active) # Abort applies to calculation now
        # Disable table interaction during calculation
        self.select_all_checkbox_dur.setEnabled(not active)
        self.duration_table.setEnabled(not active)
        # self.tabs.setEnabled(not active) # Optional: prevent tab switching


    def start_duration_scan(self):
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A folder scan is already in progress.")
            return
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
             QMessageBox.warning(self, "Busy", "Duration calculation is in progress.")
             return

        input_path_str = self.input_line_dur.text().strip()
        if not input_path_str:
            QMessageBox.critical(self, "Error", "Please select an input folder to scan.")
            return
        input_path = Path(input_path_str)
        if not input_path.is_dir():
            QMessageBox.critical(self, "Error", f"Input folder not found or is not a directory:\n{input_path}")
            return

        self.log_text_dur.clear()
        self.progress_bar_dur.setValue(0)
        self.duration_table.setRowCount(0) # Clear table
        self._all_scanned_files = [] # Clear internal list
        self._row_map_dur.clear()
        self.total_duration_label.setText("Total Duration of Selection: N/A")

        self.duration_scan_worker = DurationScanWorker(str(input_path))
        self.duration_scan_worker.log_signal.connect(self.log_dur)
        self.duration_scan_worker.progress_signal.connect(lambda p: self.progress_bar_dur.setValue(p))
        # Connect directly to the table population method (renamed for clarity)
        self.duration_scan_worker.files_scanned_signal.connect(self.populate_duration_table_from_scan)
        self.duration_scan_worker.finished_signal.connect(self.duration_scan_finished)

        self.set_duration_scan_ui_active(True)
        self.duration_scan_worker.start()


    def duration_scan_finished(self, success: bool, aborted: bool):
        self.set_duration_scan_ui_active(False) # Re-enable UI
        if aborted:
            QMessageBox.warning(self, "Aborted", "Folder scanning was aborted.")
        elif not success:
            QMessageBox.critical(self, "Error", "Folder scanning failed. Check logs.")
        # Enable calculation button only if scan succeeded AND files were found
        self.calculate_dur_btn.setEnabled(success and not aborted and self.duration_table.rowCount() > 0)
        self.duration_scan_worker = None # Clear worker


    def populate_duration_table_from_scan(self, scanned_files: List[Path]):
        """Populates the QTableWidget with all scanned files. No filtering here."""
        self.log_dur(f"Populating table with {len(scanned_files)} found video files...")
        self._all_scanned_files = scanned_files # Store the full list
        input_root = Path(self.input_line_dur.text()) # Get root for relative paths

        # Block signals during population to avoid issues with itemChanged
        self.duration_table.blockSignals(True)
        self.duration_table.setRowCount(0)
        self._row_map_dur.clear()

        current_row = 0
        for file_path in self._all_scanned_files: # Iterate through the full list
            self.duration_table.insertRow(current_row)
            self._row_map_dur[current_row] = file_path # Map row to path

            # Column 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked) # Default to checked
            self.duration_table.setItem(current_row, 0, chk_item)

            # Column 1: Relative Filename
            try:
                # Attempt to make relative, fallback to name if fails (e.g., different drive on Windows)
                rel_path_str = str(file_path.relative_to(input_root))
            except ValueError:
                rel_path_str = file_path.name # Fallback to just the filename
            name_item = QTableWidgetItem(rel_path_str)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Not editable
            name_item.setToolTip(str(file_path)) # Show full path on hover
            self.duration_table.setItem(current_row, 1, name_item)

            # Column 2: Duration (initially empty)
            dur_item = QTableWidgetItem("N/A")
            dur_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.duration_table.setItem(current_row, 2, dur_item)

            current_row += 1

        self.duration_table.blockSignals(False) # Re-enable signals

        # Update Select All checkbox state and enable if rows exist
        all_checked = current_row > 0
        self.select_all_checkbox_dur.setEnabled(all_checked)
        # Block signals temporarily to set state without triggering handler
        self.select_all_checkbox_dur.blockSignals(True)
        self.select_all_checkbox_dur.setChecked(all_checked)
        self.select_all_checkbox_dur.blockSignals(False)


        self.log_dur(f"Table updated. Displaying {current_row} files.")
        # Enable calculate button if rows exist and not busy
        is_busy = (self.duration_scan_worker and self.duration_scan_worker.isRunning()) or \
                  (self.duration_calc_worker and self.duration_calc_worker.isRunning())
        self.calculate_dur_btn.setEnabled(current_row > 0 and not is_busy)


    def toggle_select_all_duration(self, state):
        """Checks or unchecks all items in the duration table."""
        self.duration_table.blockSignals(True) # Prevent itemChanged signal spam
        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for row in range(self.duration_table.rowCount()):
            item = self.duration_table.item(row, 0)
            if item:
                item.setCheckState(check_state)
        self.duration_table.blockSignals(False)

    def duration_table_item_changed(self, item: QTableWidgetItem):
         """Handle clicks on checkboxes in the table to update master checkbox state."""
         if item.column() == 0: # Only react to checkbox column changes
             all_checked = True
             all_unchecked = True
             row_count = self.duration_table.rowCount()
             if row_count == 0: # No rows, disable and uncheck
                 all_checked = False
                 all_unchecked = True
             else:
                 for row in range(row_count):
                     chk_item = self.duration_table.item(row, 0)
                     if chk_item and chk_item.checkState() == Qt.Checked:
                         all_unchecked = False
                     elif chk_item and chk_item.checkState() == Qt.Unchecked:
                         all_checked = False
                     else: # Should not happen with standard checkboxes
                         all_checked = False
                         all_unchecked = False
                         break # Exit loop early

             # Block signals on the master checkbox while changing its state programmatically
             self.select_all_checkbox_dur.blockSignals(True)
             if all_checked:
                 self.select_all_checkbox_dur.setCheckState(Qt.Checked)
             elif all_unchecked:
                 self.select_all_checkbox_dur.setCheckState(Qt.Unchecked)
             else:
                 # Use PartiallyChecked state to indicate mixed selection
                  self.select_all_checkbox_dur.setCheckState(Qt.PartiallyChecked)
             self.select_all_checkbox_dur.blockSignals(False)


    def start_duration_calculation(self):
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
             QMessageBox.warning(self, "Busy", "Duration calculation is already in progress.")
             return
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A folder scan is in progress.")
            return

        # Report is saved in the input folder now
        input_folder_str = self.input_line_dur.text().strip()
        if not input_folder_str:
            QMessageBox.critical(self, "Error", "Please select the input video folder first.")
            return
        report_folder_path = Path(input_folder_str)
        if not report_folder_path.is_dir():
             QMessageBox.critical(self, "Error", f"Input folder not found or is not a directory:\n{report_folder_path}")
             return

        # Get selected files from the table
        selected_files: List[Tuple[int, Path]] = []
        for row in range(self.duration_table.rowCount()):
            chk_item = self.duration_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                 file_path = self._row_map_dur.get(row)
                 if file_path:
                     selected_files.append((row, file_path))
                 else:
                      self.log_dur(f"Warning: Could not find path for selected row {row}. Skipping.")


        if not selected_files:
            QMessageBox.information(self, "No Selection", "No files are selected in the table. Please check the boxes for files to include.")
            return

        # Reset progress and total duration label
        self.progress_bar_dur.setValue(0)
        self.total_duration_label.setText("Total Duration of Selection: Calculating...")
        # Clear previous duration results in the table only for selected rows? Or all? Let's clear all visible.
        for row in range(self.duration_table.rowCount()):
            item = self.duration_table.item(row, 2) # Duration column
            if item:
                item.setText("Calculating...") # Indicate which are being processed


        report_base_name = report_folder_path.name # Use input folder name for report
        if not report_base_name: report_base_name = "duration_report" # Fallback if path is root?


        self.duration_calc_worker = DurationCalculateWorker(selected_files, report_folder_path, report_base_name)
        self.duration_calc_worker.log_signal.connect(self.log_dur)
        self.duration_calc_worker.progress_signal.connect(lambda p: self.progress_bar_dur.setValue(p))
        self.duration_calc_worker.file_duration_signal.connect(self.update_duration_table_row)
        self.duration_calc_worker.total_duration_signal.connect(lambda total_str: self.total_duration_label.setText(f"Total Duration of Selection: {total_str}"))
        self.duration_calc_worker.finished_signal.connect(self.duration_calculation_finished)

        self.set_duration_calc_ui_active(True)
        self.duration_calc_worker.start()


    def update_duration_table_row(self, row_index: int, duration_str: str):
        """Update the duration string in a specific table row."""
        # Check if row_index is still valid (table might have changed?)
        if 0 <= row_index < self.duration_table.rowCount():
            item = self.duration_table.item(row_index, 2) # Duration column
            if item:
                item.setText(duration_str)
            else:
                # Should not happen if row exists, but handle defensively
                self.log_dur(f"Warning: Could not find item cell at row {row_index}, col 2 to update duration.")
        else:
            self.log_dur(f"Warning: Row index {row_index} out of bounds for table update.")


    def duration_calculation_finished(self, success: bool, aborted: bool):
        self.set_duration_calc_ui_active(False)
        # Keep progress bar at 100 if successful, otherwise leave as is or reset?
        if success and not aborted:
            self.progress_bar_dur.setValue(100)
        # Reset 'Calculating...' text for rows that were processed but failed (are N/A) or were aborted
        for row in range(self.duration_table.rowCount()):
             item = self.duration_table.item(row, 2)
             if item and item.text() == "Calculating...":
                  item.setText("N/A" if not aborted else "Aborted") # Or leave as N/A on abort


        if aborted:
             QMessageBox.warning(self, "Aborted", "Duration calculation was aborted.")
             self.total_duration_label.setText("Total Duration of Selection: Aborted")
        elif success:
             QMessageBox.information(self, "Complete", "Duration calculation and report generation finished successfully!")
             # Total duration label is set via signal, no need to update here
        else:
             # Check if failure was due to ffprobe missing (handled in worker run)
             if "ffprobe' not found" in self.log_text_dur.toPlainText()[-200:]: # Check recent logs for ffprobe error
                  QMessageBox.critical(self, "Error", "Duration calculation failed: ffprobe executable not found.\nPlease install FFmpeg/ffprobe and ensure it's in your PATH.")
             else:
                  QMessageBox.critical(self, "Error", "Duration calculation or report generation failed. Check logs for details.")
             self.total_duration_label.setText("Total Duration of Selection: Error")

        self.duration_calc_worker = None # Clear worker


    def abort_duration_task(self):
        aborted = False
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            self.log_dur("Abort requested for folder scan...")
            self.duration_scan_worker.stop()
            aborted = True
        elif self.duration_calc_worker and self.duration_calc_worker.isRunning():
             self.log_dur("Abort requested for duration calculation...")
             self.duration_calc_worker.stop()
             aborted = True

        if not aborted:
            self.log_dur("No active duration task (scan or calculate) to abort.")
        # UI update (disabling abort button etc.) happens in the respective finished_signal handlers


    # --- Window Closing ---
    def closeEvent(self, event):
        """Handle window close event to stop running threads."""
        active_workers = []
        worker_stopped = False

        if self.conversion_worker and self.conversion_worker.isRunning():
            active_workers.append("Video Conversion")
            self.conversion_worker.stop()
            worker_stopped = True
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            active_workers.append("Folder Scanning")
            self.duration_scan_worker.stop()
            worker_stopped = True
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
            active_workers.append("Duration Calculation")
            self.duration_calc_worker.stop()
            worker_stopped = True

        if active_workers:
            # Maybe give a slightly more responsive message
            self.statusBar().showMessage(f"Attempting to stop: {', '.join(active_workers)}...")
            QApplication.processEvents() # Allow UI to update

            # Wait a short time for threads to potentially finish cleanly
            # This is a simple approach; a more robust one would involve QThread.wait()
            # or checking isFinished() in a loop with processEvents.
            max_wait_ms = 2000 # e.g., 2 seconds
            start_wait = datetime.datetime.now()
            while worker_stopped and (datetime.datetime.now() - start_wait).total_seconds() * 1000 < max_wait_ms:
                 QApplication.processEvents() # Keep UI responsive during wait
                 worker_stopped = False # Assume finished unless proven otherwise
                 if self.conversion_worker and self.conversion_worker.isRunning(): worker_stopped = True
                 if self.duration_scan_worker and self.duration_scan_worker.isRunning(): worker_stopped = True
                 if self.duration_calc_worker and self.duration_calc_worker.isRunning(): worker_stopped = True
                 if not worker_stopped: break # Exit loop if all stopped
                 # Optional small sleep to prevent busy-waiting
                 # QThread.msleep(50)

            if worker_stopped:
                 print("Warning: Some background tasks may not have terminated gracefully on exit.")
            else:
                 print("Background tasks stopped.")

        event.accept() # Close the window

# -------------------------------
# Application Entry Point
# -------------------------------
if __name__ == "__main__":
    # Helps with scaling on high DPI displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = ConverterWindow()
    window.show()
=======
import sys
import os
import subprocess
import threading
import datetime
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

# Third-party libraries
try:
    import natsort
except ImportError:
    print("Error: 'natsort' library not found. Please install it: pip install natsort")
    sys.exit(1)
try:
    import requests
except ImportError:
    requests = None # Handle gracefully if not installed and ntfy not used
    print("Warning: 'requests' library not found. Ntfy notifications will be disabled.")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QRadioButton, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QMessageBox, QGroupBox, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject

# -------------------------------
# Global Configuration
# -------------------------------
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv", ".flv"} # Added more common ones
NTFY_TOPIC = "rclone_reap_iit" # Keep configurable if needed

# Find FFmpeg/FFprobe
try:
    import imageio_ffmpeg
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_BINARY = "ffmpeg" # Fallback to system PATH

# Try to find ffprobe relative to ffmpeg or in PATH
ffmpeg_path = Path(FFMPEG_BINARY)
ffprobe_path_guess = ffmpeg_path.parent / "ffprobe"
ffprobe_exe_path_guess = ffmpeg_path.parent / "ffprobe.exe"

# Prefer ffprobe next to ffmpeg if it exists
if ffprobe_path_guess.is_file():
    FFPROBE_BINARY = str(ffprobe_path_guess.resolve())
elif ffprobe_exe_path_guess.is_file(): # Check for .exe on Windows
    FFPROBE_BINARY = str(ffprobe_exe_path_guess.resolve())
else:
    # Check if ffprobe is in PATH using subprocess
    try:
        ffprobe_check = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, check=True, timeout=5)
        if ffprobe_check.returncode == 0:
             FFPROBE_BINARY = "ffprobe"
        else:
             raise FileNotFoundError # Simulate not found if return code != 0
    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        print("Error: ffprobe executable not found.")
        print(f"Looked near ffmpeg: {ffprobe_path_guess}{' (.exe)' if os.name == 'nt' else ''}")
        print("Also checked system PATH.")
        print("Please ensure ffprobe is installed and accessible.")
        # Exit or prompt user? Exiting for now.
        # QMessageBox.critical(None, "Error", "ffprobe not found. Please install FFmpeg/ffprobe and ensure it's in your PATH.")
        # sys.exit(1) # Exit if ffprobe is critical and not found
        FFPROBE_BINARY = "ffprobe" # Set default and let it fail later if really not found


# Duration Check Specific Config (Patterns removed as filtering is removed)
# CHAPTER_HEADER_PATTERN = re.compile(r"Chapter \d+[A-Za-z]? - .*", re.IGNORECASE)
# COURSE_INTRO_PATTERN = re.compile(r"Course Introduction.*", re.IGNORECASE)

# -------------------------------
# Helper Functions
# -------------------------------
def get_video_duration(input_file: Path) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    if not input_file.is_file():
        print(f"Error: Input file not found: {input_file}")
        return None
    command = [
        FFPROBE_BINARY, "-v", "error",
        "-select_streams", "v:0", # Look for video stream first
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_file),
    ]
    duration_str = None
    try:
        # Run with a timeout to prevent hangs on corrupted files
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', timeout=30)
        duration_str = result.stdout.strip()
        if not duration_str or duration_str == "N/A":
             # Try getting duration from container format if stream duration fails
            command = [
                FFPROBE_BINARY, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(input_file),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', timeout=30)
            duration_str = result.stdout.strip()
            if not duration_str or duration_str == "N/A":
                 print(f"Warning: Could not determine duration for {input_file.name}")
                 return 0.0 # Treat as 0 duration if undetectable
        return float(duration_str)
    except subprocess.CalledProcessError as e:
        print(f"Error running ffprobe for {input_file.name}: {e}")
        stderr_output = e.stderr.strip() if e.stderr else "No stderr output"
        print(f"Stderr: {stderr_output}")
        # If stderr contains "No such file or directory", the input file might be the issue
        if "No such file or directory" in stderr_output:
            print(f"Check if file exists and path is correct: {input_file}")
        return None
    except subprocess.TimeoutExpired:
        print(f"Error: ffprobe timed out processing {input_file.name}. File might be corrupted or too complex.")
        return None
    except ValueError:
        print(f"Error parsing duration for {input_file.name}. Got: '{duration_str}'")
        return None
    except FileNotFoundError:
        print(f"Error: '{FFPROBE_BINARY}' command not found. Cannot get duration.")
        # Potentially re-raise or handle globally
        raise # Re-raise critical error
    except Exception as e:
        print(f"Unexpected error getting duration for {input_file.name}: {e}")
        return None

def format_duration(seconds: Optional[float]) -> str:
    """Return a string in 'H hours M min S sec' format."""
    if seconds is None or seconds < 0:
        return "N/A"
    if seconds == 0:
        return "0 sec"

    total_seconds = int(round(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours > 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} min")
    if secs > 0 or not parts: # Show seconds if non-zero or if H/M were zero
        parts.append(f"{secs} sec")

    return " ".join(parts)


def write_error_log(log_file_path: Path, input_file: Path, error_output: str):
    """Write error details to a log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        log_file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure log dir exists
        with open(log_file_path, "a", encoding="utf-8") as f: # Append mode is often better
            f.write(f"[{timestamp}] Error processing file: {input_file}\n")
            f.write(f"Command attempted (simplified): ffmpeg ... -i \"{input_file}\" ...\n")
            f.write("-" * 20 + " FFmpeg Output " + "-" * 20 + "\n")
            f.write(error_output)
            f.write("\n" + "=" * 60 + "\n")
    except Exception as e:
        print(f"Critical: Failed to write error log to {log_file_path}: {e}")

def send_ntfy_notification(message: str, topic: str, log_emitter: Optional[pyqtSignal] = None):
    """Sends a notification to an ntfy topic."""
    if not requests:
        if log_emitter:
            log_emitter.emit("Ntfy skipped: 'requests' library not installed.")
        else:
            print("Ntfy skipped: 'requests' library not installed.")
        return

    if not topic:
        if log_emitter:
            log_emitter.emit("Ntfy skipped: No topic configured.")
        else:
            print("Ntfy skipped: No topic configured.")
        return

    url = f"https://ntfy.sh/{topic}"
    try:
        response = requests.post(url, data=message.encode("utf-8"), timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        if log_emitter:
            log_emitter.emit("Ntfy notification sent successfully!")
        else:
            print("Ntfy notification sent successfully!")
    except requests.exceptions.RequestException as e:
        if log_emitter:
            log_emitter.emit(f"Error sending ntfy notification: {e}")
        else:
            print(f"Error sending ntfy notification: {e}")
    except Exception as e:
        # Catch any other unexpected errors during notification
        if log_emitter:
            log_emitter.emit(f"Unexpected error sending ntfy notification: {e}")
        else:
            print(f"Unexpected error sending ntfy notification: {e}")

# -------------------------------
# Base Worker Thread
# -------------------------------
class BaseWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int) # Use int for progress bar (0-100)
    finished_signal = pyqtSignal(bool, bool)  # (success, aborted)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._is_aborted = False

    def stop(self):
        self._is_aborted = True
        self._stop_event.set()

    def is_aborted(self):
        return self._is_aborted

    def run(self):
        # Base run method - subclasses should implement their logic
        # and emit signals appropriately. Remember to check self._stop_event.is_set()
        # periodically in loops.
        pass

# -------------------------------
# Conversion Worker Thread
# -------------------------------
class ConversionWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited
    # log_signal(message: str) inherited

    def __init__(self, input_path: str, output_path: str, mode: str, use_cuda: bool, send_notify: bool):
        super().__init__()
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.mode = mode  # "File" or "Folder"
        self.use_cuda = use_cuda
        self.send_notify = send_notify
        self.converted_files = []  # To track created files for cleanup on abort

    def run(self):
        start_time = datetime.datetime.now()
        self.log_signal.emit(f"Starting conversion process at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        success = False
        try:
            if not self.output_path.exists():
                 self.log_signal.emit(f"Creating output directory: {self.output_path}")
                 self.output_path.mkdir(parents=True, exist_ok=True)

            if self.mode == "File":
                if not self.input_path.is_file():
                     raise FileNotFoundError(f"Input file not found: {self.input_path}")
                success = self.process_file(self.input_path, self.output_path)
            else: # Folder mode
                if not self.input_path.is_dir():
                     raise NotADirectoryError(f"Input folder not found: {self.input_path}")
                success = self.process_folder(self.input_path, self.output_path)

            if self.is_aborted():
                self.log_signal.emit("Conversion process aborted by user.")
                success = False # Mark as not successful if aborted
            elif success:
                end_time = datetime.datetime.now()
                total_time = end_time - start_time
                self.log_signal.emit(f"Conversion completed successfully at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
                self.log_signal.emit(f"Total time taken: {str(total_time).split('.')[0]}") # Format timedelta nicely
                if self.send_notify:
                    send_ntfy_notification("Video conversion completed successfully.", NTFY_TOPIC, self.log_signal)
            else:
                 self.log_signal.emit("Conversion finished with errors or no files processed.")

        except FileNotFoundError as e:
             self.log_signal.emit(f"Error: {e}")
             success = False
        except NotADirectoryError as e:
            self.log_signal.emit(f"Error: {e}")
            success = False
        except Exception as e:
            self.log_signal.emit(f"An unexpected error occurred during conversion: {e}")
            import traceback
            self.log_signal.emit(traceback.format_exc()) # Log full traceback for debugging
            success = False
        finally:
             # Emit finished signal with success status and aborted flag
             self.finished_signal.emit(success, self.is_aborted())

    def process_file(self, input_file: Path, output_dir: Path) -> bool:
        """Processes a single file."""
        if self.is_aborted(): return False
        if input_file.suffix.lower() not in VIDEO_EXTENSIONS:
            self.log_signal.emit(f"Skipping non-video file: {input_file.name}")
            return True # Not an error, just skipping

        out_file = output_dir / f"{input_file.stem}.mp4" # Standardize output to mp4
        self.log_signal.emit("-" * 30)
        self.log_signal.emit(f"Processing: {input_file.name}")
        self.log_signal.emit(f"Outputting to: {out_file}")
        result = self.convert_video_file(input_file, out_file)
        self.progress_signal.emit(100) # Single file means 100% when done/failed
        return result

    def process_folder(self, input_dir: Path, output_dir: Path) -> bool:
        """Processes all video files in a folder recursively."""
        self.log_signal.emit(f"Scanning folder: {input_dir}")
        try:
            video_files = [p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            # Sort naturally for predictable processing order
            video_files = natsort.natsorted(video_files, key=lambda x: x.as_posix())
        except Exception as e:
            self.log_signal.emit(f"Error scanning folder: {e}")
            return False

        total_files = len(video_files)
        if total_files == 0:
            self.log_signal.emit("No video files found in the selected folder.")
            return True # Not an error, just nothing to do

        self.log_signal.emit(f"Found {total_files} video files to process.")
        overall_success = True

        for idx, file_path in enumerate(video_files):
            if self.is_aborted():
                overall_success = False
                break

            self.log_signal.emit("-" * 30)
            self.log_signal.emit(f"Processing file {idx + 1}/{total_files}: {file_path.name}")

            # Calculate relative path and create corresponding output directory
            try:
                rel_path = file_path.relative_to(input_dir).parent
            except ValueError:
                self.log_signal.emit(f"Warning: Could not determine relative path for {file_path}. Outputting to base output folder.")
                rel_path = Path(".") # Fallback to avoid error

            target_dir = output_dir / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)

            out_file = target_dir / f"{file_path.stem}.mp4"
            self.log_signal.emit(f"Outputting to: {out_file}")

            file_success = self.convert_video_file(file_path, out_file)
            if not file_success:
                overall_success = False # Mark overall as failed if any file fails

            # Update overall progress (even if file failed, we processed it)
            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        self.log_signal.emit("-" * 30)
        if not self.is_aborted():
             self.log_signal.emit("Folder processing complete.")

        return overall_success

    def convert_video_file(self, input_file: Path, output_file: Path) -> bool:
        """Performs the actual FFmpeg conversion for a single file."""
        duration = None
        try:
            duration = get_video_duration(input_file)
        except FileNotFoundError: # Catch if ffprobe binary itself is missing
             self.log_signal.emit(f"Critical Error: '{FFPROBE_BINARY}' not found. Cannot determine video duration.")
             return False # Hard fail if ffprobe isn't available

        if duration is None: # Handle ffprobe error/timeout for this specific file
            self.log_signal.emit(f"Skipping file (error reading duration): {input_file.name}")
            log_file = output_file.with_suffix(".ffprobe_error.log")
            write_error_log(log_file, input_file, "Failed to get video duration using ffprobe (possible error or timeout).")
            return False
        if duration == 0:
             self.log_signal.emit(f"Skipping file (zero or undetectable duration): {input_file.name}")
             return True # Treat as success (skipped intentionally)


        # Base command parts
        command = [FFMPEG_BINARY, "-y"] # -y overwrites output without asking

        # Input and Hardware Acceleration (if applicable)
        if self.use_cuda:
            # Specify input hwaccel AND output format if needed
            # Using -hwaccel cuda often sufficient for NVDEC -> NVENC pipelines
            command.extend(["-hwaccel", "cuda"]) # "-hwaccel_output_format", "cuda" might be needed depending on filters
        command.extend(["-i", str(input_file)])

        # Filters (Scaling)
        scale_filter = "scale=-2:720" # Default software scale
        if self.use_cuda:
             # Check common CUDA filters. scale_cuda preferred if available. scale_npp as fallback.
             # This requires checking ffmpeg capabilities, which adds complexity.
             # Simpler approach: Use software scale, often works fine even with hwaccel.
             # Or just try scale_cuda and let it fail if not supported.
             # command.extend(["-vf", "scale_cuda=-2:720:interp_algo=lanczos"]) # Example CUDA scale
             command.extend(["-vf", scale_filter]) # Stick with software scale for broader compatibility
        else:
            command.extend(["-vf", scale_filter]) # Software scaling

        # Video Codec and Options
        if self.use_cuda:
            command.extend(["-c:v", "h264_nvenc", "-preset", "p6", "-tune", "hq", "-rc", "vbr", "-cq", "23", "-qmin", "0", "-qmax", "51", "-b:v", "0", "-profile:v", "main"])
             # Example NVENC settings: preset p6 (medium), tune hq, ConstQP mode (cq 23). Adjust as needed.
        else:
            command.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-profile:v", "main"])
            # CRF 23 is a good balance.

        # Audio Codec and Options
        command.extend(["-c:a", "aac", "-b:a", "192k"]) # 192k AAC stereo

        # Output file and Progress Reporting
        command.extend([str(output_file), "-progress", "pipe:1", "-nostats"])

        self.log_signal.emit(f"FFmpeg command (simplified): {' '.join(command[:5])} ... {' '.join(command[-4:])}")

        try:
            # Use CREATE_NO_WINDOW flag on Windows to prevent console pop-up
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW

            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, encoding='utf-8', errors='replace',
                                       creationflags=creationflags)
            self.converted_files.append(output_file) # Track for potential cleanup

            stdout_lines = [] # Collect output for error logging if needed

            while True:
                if self.is_aborted():
                    self.log_signal.emit(f"Attempting to terminate FFmpeg process for {input_file.name}...")
                    process.terminate() # Ask ffmpeg to stop gracefully first
                    try:
                         process.wait(timeout=5) # Wait a bit
                         if process.poll() is None: # Still running?
                              self.log_signal.emit("FFmpeg did not terminate gracefully, killing...")
                              process.kill() # Force stop
                    except subprocess.TimeoutExpired:
                         self.log_signal.emit("FFmpeg termination timed out, killing...")
                         process.kill()
                    self.log_signal.emit(f"Aborted conversion for {input_file.name}")
                    return False # Signal abortion

                # Read line by line, non-blocking if possible (though readline usually blocks)
                line = process.stdout.readline()
                if not line:
                    # Check if process finished
                    if process.poll() is not None:
                        break
                    # If no line and process still running, maybe it stalled? (less likely with pipe:1)
                    # Or maybe just waiting for more data. Continue reading.
                    continue

                stdout_lines.append(line) # Store line for potential error log
                line = line.strip()

                if line.startswith("out_time_ms="):
                    try:
                        out_time_ms = int(line.split("=")[1])
                        current_time = out_time_ms / 1_000_000
                        progress = min(int(current_time / duration * 100), 100) if duration > 0 else 0
                        # In file mode, this directly updates the main bar
                        if self.mode == "File":
                            self.progress_signal.emit(progress)
                        # Note: Per-file progress in folder mode isn't explicitly shown on progress bar,
                        # only overall progress is updated in process_folder method.
                    except (ValueError, IndexError, ZeroDivisionError):
                        pass # Ignore malformed progress lines
                elif line.startswith("progress=end"):
                     if self.mode == "File":
                         self.progress_signal.emit(100)
                     break # FFmpeg signals completion

            # Ensure process has fully finished and capture return code
            return_code = process.wait()

            if return_code != 0:
                self.log_signal.emit(f"Error: FFmpeg failed for {input_file.name} (exit code {return_code})")
                # Read any remaining output (might not be much if already read line-by-line)
                remaining_output = process.stdout.read()
                stdout_lines.append(remaining_output)
                error_output = "".join(stdout_lines)
                log_file = output_file.with_suffix(".ffmpeg_error.log")
                write_error_log(log_file, input_file, error_output)
                self.log_signal.emit(f"Error details logged to: {log_file}")
                # Clean up potentially broken output file
                if output_file in self.converted_files: self.converted_files.remove(output_file)
                if output_file.exists():
                    try:
                        output_file.unlink()
                        self.log_signal.emit(f"Deleted incomplete output file: {output_file.name}")
                    except OSError as e:
                        self.log_signal.emit(f"Warning: Could not delete incomplete file {output_file.name}: {e}")
                return False # Failure
            else:
                self.log_signal.emit(f"Successfully converted {input_file.name}")
                if self.mode == "File":
                    self.progress_signal.emit(100)
                return True # Success

        except FileNotFoundError:
             self.log_signal.emit(f"Error: '{FFMPEG_BINARY}' command not found. Please ensure FFmpeg is installed and in your PATH.")
             return False
        except Exception as e:
             self.log_signal.emit(f"Error running FFmpeg process for {input_file.name}: {e}")
             import traceback
             self.log_signal.emit(traceback.format_exc())
             log_file = output_file.with_suffix(".python_error.log")
             write_error_log(log_file, input_file, f"Python Exception:\n{traceback.format_exc()}")
             self.log_signal.emit(f"Python error details logged to: {log_file}")
             return False


# -------------------------------
# Duration Scan Worker
# -------------------------------
class DurationScanWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited - Represents scanning progress
    # log_signal(message: str) inherited
    files_scanned_signal = pyqtSignal(list) # Emits list[Path] of found video files

    def __init__(self, input_path: str):
        super().__init__()
        self.input_path = Path(input_path)

    def run(self):
        self.log_signal.emit(f"Scanning folder for videos: {self.input_path}")
        if not self.input_path.is_dir():
            self.log_signal.emit("Error: Selected path is not a valid directory.")
            self.finished_signal.emit(False, self.is_aborted())
            return

        video_files = []
        success = True
        try:
            # Estimate total items for progress (can be inaccurate with deep trees/symlinks)
            # A simple count of initial items might be faster for large directories
            # Let's use a generator approach for potentially large directories
            all_items_gen = self.input_path.rglob("*")
            # To get progress, we need a count, which means iterating twice or storing all.
            # For simplicity, let's list them first. Consider iterative approach if memory is a concern.
            all_files_list = list(all_items_gen)
            total_items = len(all_files_list)
            processed_items = 0

            for item in all_files_list:
                if self.is_aborted():
                     self.log_signal.emit("Scanning aborted.")
                     success = False
                     break

                processed_items += 1
                if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                    video_files.append(item)

                if total_items > 0:
                    progress = int((processed_items / total_items) * 100)
                    # Throttle progress updates slightly for performance
                    if processed_items % 50 == 0 or progress == 100 or processed_items == total_items:
                         self.progress_signal.emit(progress)

            if success:
                # Sort naturally before emitting
                sorted_files = natsort.natsorted(video_files, key=lambda x: x.as_posix())
                self.log_signal.emit(f"Scan complete. Found {len(sorted_files)} video files.")
                self.files_scanned_signal.emit(sorted_files)
            else:
                 # Emit empty list if aborted during scan
                 self.files_scanned_signal.emit([])


        except Exception as e:
            self.log_signal.emit(f"Error during folder scan: {e}")
            import traceback
            self.log_signal.emit(traceback.format_exc())
            success = False
            self.files_scanned_signal.emit([]) # Emit empty list on error

        self.finished_signal.emit(success, self.is_aborted())


# -------------------------------
# Duration Calculation Worker
# -------------------------------
class DurationCalculateWorker(BaseWorker):
    # finished_signal(success: bool, aborted: bool) inherited
    # progress_signal(percent: int) inherited - Represents calculation progress
    # log_signal(message: str) inherited
    file_duration_signal = pyqtSignal(int, str) # row_index, formatted_duration_str
    total_duration_signal = pyqtSignal(str) # formatted_total_duration_str

    def __init__(self, files_to_check: List[Tuple[int, Path]], report_folder: Path, report_filename_base: str):
        super().__init__()
        self.files_to_check = files_to_check # List of (row_index, file_path)
        self.report_folder = report_folder # Folder where report will be saved (now the input folder)
        self.report_filename_base = report_filename_base

    def run(self):
        total_files = len(self.files_to_check)
        if total_files == 0:
            self.log_signal.emit("No files selected for duration check.")
            self.finished_signal.emit(True, self.is_aborted()) # Success, but nothing done
            return

        self.log_signal.emit(f"Calculating duration for {total_files} selected files...")
        # report_folder is expected to exist (it's the input folder)

        durations: Dict[Path, Optional[float]] = {}
        total_duration_sec = 0.0
        success = True
        ffprobe_found = True # Flag to track if ffprobe is usable

        for idx, (row_index, file_path) in enumerate(self.files_to_check):
            if self.is_aborted():
                self.log_signal.emit("Duration calculation aborted.")
                success = False
                break

            self.log_signal.emit(f"Checking [{idx+1}/{total_files}]: {file_path.name}")
            duration_sec = None
            try:
                duration_sec = get_video_duration(file_path)
            except FileNotFoundError: # Catch ffprobe not found error from helper
                self.log_signal.emit(f"Critical Error: '{FFPROBE_BINARY}' not found. Aborting duration check.")
                ffprobe_found = False
                success = False
                break # Stop processing further files
            except Exception as e: # Catch other unexpected errors from helper
                self.log_signal.emit(f"Unexpected error getting duration for {file_path.name}: {e}")
                # Logged within helper, continue processing others if possible

            durations[file_path] = duration_sec
            formatted_duration = format_duration(duration_sec)
            self.file_duration_signal.emit(row_index, formatted_duration) # Update UI regardless of success

            if duration_sec is not None and duration_sec > 0:
                 total_duration_sec += duration_sec
            elif duration_sec is None:
                 self.log_signal.emit(f"Warning: Failed to get duration for {file_path.name}. It will not be included in the total.")
                 # Marked as N/A in UI, total won't include it.
            # else duration_sec == 0 (already logged by helper if undetectable)

            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        if not ffprobe_found:
             # If ffprobe wasn't found, finish with failure state
             self.finished_signal.emit(False, self.is_aborted())
             return

        if success and not self.is_aborted(): # Only calculate total and write report if not aborted and no critical errors
            formatted_total = format_duration(total_duration_sec)
            self.total_duration_signal.emit(formatted_total)
            self.log_signal.emit(f"Total calculated duration for selected files: {formatted_total}")

            # --- Generate Report File ---
            # Ensure base name is safe for filesystem
            safe_base_name = re.sub(r'[\\/*?:"<>|]', '_', self.report_filename_base) # Replace invalid chars
            report_file = self.report_folder / f"{safe_base_name}_duration.txt"
            self.log_signal.emit(f"Generating report file: {report_file}")
            try:
                # Sort the files based on the original order they were passed (reflects UI selection order/natural sort)
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(f"Duration Report for: {self.report_filename_base}\n")
                    f.write(f"Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total files selected: {len(self.files_to_check)}\n")
                    f.write("-" * 30 + "\n\n")

                    # Use the original sorted list passed to the worker
                    for _, file_path in self.files_to_check:
                         duration = durations.get(file_path) # Get calculated duration (might be None)
                         f.write(f"{file_path.name} -> {format_duration(duration)}\n")

                    f.write("\n" + "=" * 30 + "\n")
                    f.write(f"Total duration of the selection -> {formatted_total}\n")
                self.log_signal.emit("Report file generated successfully.")

            except Exception as e:
                self.log_signal.emit(f"Error writing duration report file '{report_file}': {e}")
                success = False # Mark as failed if report writing fails

        self.finished_signal.emit(success, self.is_aborted())


# -------------------------------
# Main GUI Window
# -------------------------------
class ConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kannan's Media Toolkit")
        self.setGeometry(100, 100, 850, 700) # Adjusted size

        # Worker threads - keep track of active ones
        self.conversion_worker: Optional[ConversionWorker] = None
        self.duration_scan_worker: Optional[DurationScanWorker] = None
        self.duration_calc_worker: Optional[DurationCalculateWorker] = None

        self._init_ui()

    def _init_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create Tab Widgets
        self.conversion_tab = QWidget()
        self.duration_tab = QWidget()

        # Add tabs to QTabWidget
        self.tabs.addTab(self.conversion_tab, "Video Conversion")
        self.tabs.addTab(self.duration_tab, "Duration Check")

        # Populate each tab
        self._populate_conversion_tab()
        self._populate_duration_tab()

    # --- Conversion Tab UI ---
    def _populate_conversion_tab(self):
        layout = QVBoxLayout(self.conversion_tab)

        # Mode Group
        mode_group_conv = QGroupBox("Conversion Mode")
        mode_layout_conv = QHBoxLayout()
        self.file_radio_conv = QRadioButton("Single File")
        self.folder_radio_conv = QRadioButton("Entire Folder")
        self.file_radio_conv.setChecked(True)
        mode_layout_conv.addWidget(self.file_radio_conv)
        mode_layout_conv.addWidget(self.folder_radio_conv)
        mode_group_conv.setLayout(mode_layout_conv)
        layout.addWidget(mode_group_conv)

        # Input Selection
        input_group_conv = QGroupBox("Input Source")
        input_layout_conv = QHBoxLayout()
        self.input_line_conv = QLineEdit()
        self.input_line_conv.setPlaceholderText("Select input file or folder...")
        self.browse_input_btn_conv = QPushButton("Browse") # Store ref
        self.browse_input_btn_conv.clicked.connect(self.browse_input_conversion)
        input_layout_conv.addWidget(self.input_line_conv)
        input_layout_conv.addWidget(self.browse_input_btn_conv)
        input_group_conv.setLayout(input_layout_conv)
        layout.addWidget(input_group_conv)

        # Output Selection
        output_group_conv = QGroupBox("Output Folder")
        output_layout_conv = QHBoxLayout()
        self.output_line_conv = QLineEdit()
        self.output_line_conv.setPlaceholderText("Select output folder...")
        self.browse_output_btn_conv = QPushButton("Browse") # Store ref
        self.browse_output_btn_conv.clicked.connect(lambda: self.browse_folder(self.output_line_conv))
        output_layout_conv.addWidget(self.output_line_conv)
        output_layout_conv.addWidget(self.browse_output_btn_conv)
        output_group_conv.setLayout(output_layout_conv)
        layout.addWidget(output_group_conv)

        # Options
        options_group_conv = QGroupBox("Options")
        options_layout_conv = QVBoxLayout() # Use QVBoxLayout for better spacing
        self.cuda_checkbox_conv = QCheckBox("Use NVIDIA CUDA acceleration (if available)")
        self.notify_checkbox_conv = QCheckBox("Send ntfy notification on completion")
        self.notify_checkbox_conv.setEnabled(requests is not None) # Disable if requests not installed
        options_layout_conv.addWidget(self.cuda_checkbox_conv)
        options_layout_conv.addWidget(self.notify_checkbox_conv)
        options_group_conv.setLayout(options_layout_conv)
        layout.addWidget(options_group_conv)

        # Action Buttons & Progress
        action_layout_conv = QHBoxLayout()
        self.convert_btn = QPushButton("Start Conversion")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.abort_btn_conv = QPushButton("Abort Conversion")
        self.abort_btn_conv.clicked.connect(self.abort_conversion)
        self.abort_btn_conv.setEnabled(False)
        action_layout_conv.addWidget(self.convert_btn)
        action_layout_conv.addWidget(self.abort_btn_conv)
        layout.addLayout(action_layout_conv)

        self.progress_bar_conv = QProgressBar()
        self.progress_bar_conv.setValue(0)
        layout.addWidget(self.progress_bar_conv)

        # Log Area
        self.log_text_conv = QTextEdit()
        self.log_text_conv.setReadOnly(True)
        self.log_text_conv.setLineWrapMode(QTextEdit.WidgetWidth) # Better wrapping
        layout.addWidget(self.log_text_conv)

        self.conversion_tab.setLayout(layout) # Set the layout for the tab

    # --- Duration Check Tab UI ---
    def _populate_duration_tab(self):
        layout = QVBoxLayout(self.duration_tab)

        # Input Folder Selection (Now the only folder needed)
        input_group_dur = QGroupBox("Video Folder (Report will be saved here)") # Updated title
        input_layout_dur = QHBoxLayout()
        self.input_line_dur = QLineEdit()
        self.input_line_dur.setPlaceholderText("Select folder containing videos...")
        self.browse_input_btn_dur = QPushButton("Browse Folder") # Store ref
        self.browse_input_btn_dur.clicked.connect(lambda: self.browse_folder(self.input_line_dur))
        input_layout_dur.addWidget(self.input_line_dur)
        input_layout_dur.addWidget(self.browse_input_btn_dur)
        input_group_dur.setLayout(input_layout_dur)
        layout.addWidget(input_group_dur)

        # Scan Button (Moved out of removed filter group)
        scan_layout = QHBoxLayout() # Layout for just the scan button
        self.scan_folder_btn = QPushButton("Scan Folder for Videos")
        self.scan_folder_btn.clicked.connect(self.start_duration_scan)
        scan_layout.addWidget(self.scan_folder_btn)
        scan_layout.addStretch() # Push button to the left
        layout.addLayout(scan_layout)

        # File List Table
        table_group = QGroupBox("Video Files Found (Check/Uncheck to include in calculation)") # Updated instructions
        table_layout = QVBoxLayout()
        self.select_all_checkbox_dur = QCheckBox("Select/Deselect All")
        self.select_all_checkbox_dur.stateChanged.connect(self.toggle_select_all_duration)
        table_layout.addWidget(self.select_all_checkbox_dur)

        self.duration_table = QTableWidget()
        self.duration_table.setColumnCount(3)
        self.duration_table.setHorizontalHeaderLabels([" ", "File Name (relative to input folder)", "Duration"])
        self.duration_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Stretch filename column
        self.duration_table.setColumnWidth(0, 40) # Checkbox column width
        self.duration_table.setColumnWidth(2, 150) # Duration column width
        self.duration_table.setEditTriggers(QTableWidget.NoEditTriggers) # Read-only except checkbox
        self.duration_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.duration_table.itemChanged.connect(self.duration_table_item_changed) # To handle checkbox clicks
        table_layout.addWidget(self.duration_table)
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)

        # Action Buttons & Progress
        action_layout_dur = QHBoxLayout()
        self.calculate_dur_btn = QPushButton("Calculate Selected Durations & Save Report") # Updated text
        self.calculate_dur_btn.clicked.connect(self.start_duration_calculation)
        self.calculate_dur_btn.setEnabled(False) # Enable after scanning
        self.abort_btn_dur = QPushButton("Abort Task")
        self.abort_btn_dur.clicked.connect(self.abort_duration_task)
        self.abort_btn_dur.setEnabled(False)
        action_layout_dur.addWidget(self.calculate_dur_btn)
        action_layout_dur.addWidget(self.abort_btn_dur)
        layout.addLayout(action_layout_dur)

        self.progress_bar_dur = QProgressBar()
        self.progress_bar_dur.setValue(0)
        layout.addWidget(self.progress_bar_dur)

         # Total Duration Display
        self.total_duration_label = QLabel("Total Duration of Selection: N/A")
        self.total_duration_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.total_duration_label)

        # Log Area
        self.log_text_dur = QTextEdit()
        self.log_text_dur.setReadOnly(True)
        self.log_text_dur.setLineWrapMode(QTextEdit.WidgetWidth)
        layout.addWidget(self.log_text_dur)

        self.duration_tab.setLayout(layout)

        # Store scanned files data separately from the table
        self._all_scanned_files: List[Path] = []
        self._row_map_dur: Dict[int, Path] = {} # Maps table row index to original Path


    # --- Common GUI Helpers ---
    def browse_folder(self, line_edit_widget: QLineEdit):
        """Opens a folder dialog and sets the path in the QLineEdit."""
        # Use the current value as starting directory if valid
        current_path = line_edit_widget.text().strip()
        start_dir = current_path if os.path.isdir(current_path) else ""

        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder", start_dir)
        if folder_path:
            line_edit_widget.setText(folder_path)

    def log_message(self, message: str, log_widget: QTextEdit):
        """Appends a message to the specified log widget."""
        log_widget.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {message}")
        # Auto-scroll to the bottom (optional)
        log_widget.verticalScrollBar().setValue(log_widget.verticalScrollBar().maximum())


    # --- Conversion Tab Logic ---
    def log_conv(self, message: str):
        self.log_message(message, self.log_text_conv)

    def browse_input_conversion(self):
        current_input = self.input_line_conv.text().strip()
        start_dir = ""
        if self.file_radio_conv.isChecked():
            if os.path.isfile(current_input):
                start_dir = os.path.dirname(current_input)
            elif os.path.isdir(current_input):
                 start_dir = current_input # Use if user switched mode after selecting folder
            # Use VIDEO_EXTENSIONS to create the filter string
            ext_filter = "Video Files (" + " ".join("*" + ext for ext in VIDEO_EXTENSIONS) + ");;All Files (*)"
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", start_dir, ext_filter)
            if file_path:
                self.input_line_conv.setText(file_path)
        else: # Folder mode
            if os.path.isdir(current_input):
                start_dir = current_input
            elif os.path.isfile(current_input):
                 start_dir = os.path.dirname(current_input)
            self.browse_folder(self.input_line_conv)

    def start_conversion(self):
        if self.conversion_worker and self.conversion_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A conversion process is already running.")
            return

        input_path_str = self.input_line_conv.text().strip()
        output_path_str = self.output_line_conv.text().strip()
        mode = "File" if self.file_radio_conv.isChecked() else "Folder"

        # Validation
        if not input_path_str:
            QMessageBox.critical(self, "Error", f"Please select an input {mode.lower()}.")
            return
        input_path = Path(input_path_str)
        if mode == "File" and not input_path.is_file():
             QMessageBox.critical(self, "Error", f"Input file not found:\n{input_path}")
             return
        if mode == "Folder" and not input_path.is_dir():
            QMessageBox.critical(self, "Error", f"Input folder not found:\n{input_path}")
            return

        if not output_path_str:
            QMessageBox.critical(self, "Error", "Please select an output folder.")
            return
        output_path = Path(output_path_str)
        if not output_path.exists():
             reply = QMessageBox.question(self, "Create Folder?",
                                          f"Output folder does not exist:\n{output_path}\n\nCreate it?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
             if reply == QMessageBox.Yes:
                 try:
                     output_path.mkdir(parents=True, exist_ok=True)
                     self.log_conv(f"Created output directory: {output_path}")
                 except Exception as e:
                     QMessageBox.critical(self, "Error", f"Could not create output folder:\n{e}")
                     return
             else:
                 return # User chose not to create
        elif not output_path.is_dir():
             QMessageBox.critical(self, "Error", f"Output path exists but is not a folder:\n{output_path}")
             return

        # Clear logs and progress
        self.log_text_conv.clear()
        self.progress_bar_conv.setValue(0)

        use_cuda = self.cuda_checkbox_conv.isChecked()
        send_notify = self.notify_checkbox_conv.isChecked()

        # Setup and start worker
        self.conversion_worker = ConversionWorker(str(input_path), str(output_path), mode, use_cuda, send_notify)
        self.conversion_worker.log_signal.connect(self.log_conv)
        self.conversion_worker.progress_signal.connect(lambda p: self.progress_bar_conv.setValue(p))
        self.conversion_worker.finished_signal.connect(self.conversion_finished)

        # Update UI state
        self.set_conversion_ui_active(True)

        self.conversion_worker.start()

    def set_conversion_ui_active(self, active: bool):
        """Enable/disable conversion UI elements based on running state."""
        self.convert_btn.setEnabled(not active)
        self.abort_btn_conv.setEnabled(active)
        # Disable input/output browsing and options while running
        self.input_line_conv.setEnabled(not active)
        self.output_line_conv.setEnabled(not active)
        self.browse_input_btn_conv.setEnabled(not active)
        self.browse_output_btn_conv.setEnabled(not active)
        self.file_radio_conv.setEnabled(not active)
        self.folder_radio_conv.setEnabled(not active)
        self.cuda_checkbox_conv.setEnabled(not active)
        self.notify_checkbox_conv.setEnabled(not active and requests is not None)
        # Prevent switching tabs while busy? (Optional, can be annoying)
        # self.tabs.setEnabled(not active)

    def conversion_finished(self, success: bool, aborted: bool):
        self.set_conversion_ui_active(False)
        self.progress_bar_conv.setValue(100 if success and not aborted else self.progress_bar_conv.value()) # Show 100 on success

        if aborted:
            QMessageBox.warning(self, "Aborted", "Conversion process was aborted.")
            self.log_conv("Cleaning up partial files due to abort...")
            self.cleanup_partial_files()
        elif success:
            QMessageBox.information(self, "Complete", "Conversion finished successfully!")
        else:
            QMessageBox.critical(self, "Error", "Conversion finished with errors. Check the log for details.")

        self.conversion_worker = None # Clear worker reference


    def abort_conversion(self):
        if self.conversion_worker and self.conversion_worker.isRunning():
            self.log_conv("Abort requested for conversion...")
            self.conversion_worker.stop()
            # UI update (disabling abort button etc.) happens in finished_signal handler
        else:
             self.log_conv("No active conversion process to abort.")


    def cleanup_partial_files(self):
        if self.conversion_worker:
            cleaned_count = 0
            # Use a copy of the list in case it's modified elsewhere (though unlikely here)
            files_to_check = list(self.conversion_worker.converted_files)
            for file_path_obj in files_to_check:
                 file_path = Path(file_path_obj) # Ensure it's a Path object
                 try:
                    # Check existence again right before deleting
                    if file_path.exists() and file_path.is_file():
                        file_path.unlink()
                        self.log_conv(f"Deleted partial file: {file_path.name}")
                        cleaned_count += 1
                 except Exception as e:
                    self.log_conv(f"Error deleting partial file {file_path.name}: {e}")
            if cleaned_count > 0:
                 self.log_conv(f"Cleaned up {cleaned_count} partial file(s).")
            else:
                 self.log_conv("No partial files found to clean up (or already deleted).")
            # Clear the list in the worker after attempting cleanup
            self.conversion_worker.converted_files.clear()
        else:
             self.log_conv("Cleanup skipped: No conversion worker context found.")


    # --- Duration Check Tab Logic ---
    def log_dur(self, message: str):
        self.log_message(message, self.log_text_dur)

    def set_duration_scan_ui_active(self, active: bool):
        """Enable/disable UI during duration scan."""
        self.scan_folder_btn.setEnabled(not active)
        self.input_line_dur.setEnabled(not active)
        self.browse_input_btn_dur.setEnabled(not active)
        # Disable calc button during scan
        self.calculate_dur_btn.setEnabled(not active and self.duration_table.rowCount() > 0)
        self.abort_btn_dur.setEnabled(active) # Abort applies to scan now
        # Disable table interaction during scan
        self.select_all_checkbox_dur.setEnabled(not active and self.duration_table.rowCount() > 0)
        self.duration_table.setEnabled(not active)
        # self.tabs.setEnabled(not active) # Optional: prevent tab switching

    def set_duration_calc_ui_active(self, active: bool):
        """Enable/disable UI during duration calculation."""
        self.calculate_dur_btn.setEnabled(not active and self.duration_table.rowCount() > 0)
        # Disable scan button and folder selection during calculation
        self.scan_folder_btn.setEnabled(not active)
        self.input_line_dur.setEnabled(not active)
        self.browse_input_btn_dur.setEnabled(not active)
        self.abort_btn_dur.setEnabled(active) # Abort applies to calculation now
        # Disable table interaction during calculation
        self.select_all_checkbox_dur.setEnabled(not active)
        self.duration_table.setEnabled(not active)
        # self.tabs.setEnabled(not active) # Optional: prevent tab switching


    def start_duration_scan(self):
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A folder scan is already in progress.")
            return
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
             QMessageBox.warning(self, "Busy", "Duration calculation is in progress.")
             return

        input_path_str = self.input_line_dur.text().strip()
        if not input_path_str:
            QMessageBox.critical(self, "Error", "Please select an input folder to scan.")
            return
        input_path = Path(input_path_str)
        if not input_path.is_dir():
            QMessageBox.critical(self, "Error", f"Input folder not found or is not a directory:\n{input_path}")
            return

        self.log_text_dur.clear()
        self.progress_bar_dur.setValue(0)
        self.duration_table.setRowCount(0) # Clear table
        self._all_scanned_files = [] # Clear internal list
        self._row_map_dur.clear()
        self.total_duration_label.setText("Total Duration of Selection: N/A")

        self.duration_scan_worker = DurationScanWorker(str(input_path))
        self.duration_scan_worker.log_signal.connect(self.log_dur)
        self.duration_scan_worker.progress_signal.connect(lambda p: self.progress_bar_dur.setValue(p))
        # Connect directly to the table population method (renamed for clarity)
        self.duration_scan_worker.files_scanned_signal.connect(self.populate_duration_table_from_scan)
        self.duration_scan_worker.finished_signal.connect(self.duration_scan_finished)

        self.set_duration_scan_ui_active(True)
        self.duration_scan_worker.start()


    def duration_scan_finished(self, success: bool, aborted: bool):
        self.set_duration_scan_ui_active(False) # Re-enable UI
        if aborted:
            QMessageBox.warning(self, "Aborted", "Folder scanning was aborted.")
        elif not success:
            QMessageBox.critical(self, "Error", "Folder scanning failed. Check logs.")
        # Enable calculation button only if scan succeeded AND files were found
        self.calculate_dur_btn.setEnabled(success and not aborted and self.duration_table.rowCount() > 0)
        self.duration_scan_worker = None # Clear worker


    def populate_duration_table_from_scan(self, scanned_files: List[Path]):
        """Populates the QTableWidget with all scanned files. No filtering here."""
        self.log_dur(f"Populating table with {len(scanned_files)} found video files...")
        self._all_scanned_files = scanned_files # Store the full list
        input_root = Path(self.input_line_dur.text()) # Get root for relative paths

        # Block signals during population to avoid issues with itemChanged
        self.duration_table.blockSignals(True)
        self.duration_table.setRowCount(0)
        self._row_map_dur.clear()

        current_row = 0
        for file_path in self._all_scanned_files: # Iterate through the full list
            self.duration_table.insertRow(current_row)
            self._row_map_dur[current_row] = file_path # Map row to path

            # Column 0: Checkbox
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked) # Default to checked
            self.duration_table.setItem(current_row, 0, chk_item)

            # Column 1: Relative Filename
            try:
                # Attempt to make relative, fallback to name if fails (e.g., different drive on Windows)
                rel_path_str = str(file_path.relative_to(input_root))
            except ValueError:
                rel_path_str = file_path.name # Fallback to just the filename
            name_item = QTableWidgetItem(rel_path_str)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable) # Not editable
            name_item.setToolTip(str(file_path)) # Show full path on hover
            self.duration_table.setItem(current_row, 1, name_item)

            # Column 2: Duration (initially empty)
            dur_item = QTableWidgetItem("N/A")
            dur_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.duration_table.setItem(current_row, 2, dur_item)

            current_row += 1

        self.duration_table.blockSignals(False) # Re-enable signals

        # Update Select All checkbox state and enable if rows exist
        all_checked = current_row > 0
        self.select_all_checkbox_dur.setEnabled(all_checked)
        # Block signals temporarily to set state without triggering handler
        self.select_all_checkbox_dur.blockSignals(True)
        self.select_all_checkbox_dur.setChecked(all_checked)
        self.select_all_checkbox_dur.blockSignals(False)


        self.log_dur(f"Table updated. Displaying {current_row} files.")
        # Enable calculate button if rows exist and not busy
        is_busy = (self.duration_scan_worker and self.duration_scan_worker.isRunning()) or \
                  (self.duration_calc_worker and self.duration_calc_worker.isRunning())
        self.calculate_dur_btn.setEnabled(current_row > 0 and not is_busy)


    def toggle_select_all_duration(self, state):
        """Checks or unchecks all items in the duration table."""
        self.duration_table.blockSignals(True) # Prevent itemChanged signal spam
        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for row in range(self.duration_table.rowCount()):
            item = self.duration_table.item(row, 0)
            if item:
                item.setCheckState(check_state)
        self.duration_table.blockSignals(False)

    def duration_table_item_changed(self, item: QTableWidgetItem):
         """Handle clicks on checkboxes in the table to update master checkbox state."""
         if item.column() == 0: # Only react to checkbox column changes
             all_checked = True
             all_unchecked = True
             row_count = self.duration_table.rowCount()
             if row_count == 0: # No rows, disable and uncheck
                 all_checked = False
                 all_unchecked = True
             else:
                 for row in range(row_count):
                     chk_item = self.duration_table.item(row, 0)
                     if chk_item and chk_item.checkState() == Qt.Checked:
                         all_unchecked = False
                     elif chk_item and chk_item.checkState() == Qt.Unchecked:
                         all_checked = False
                     else: # Should not happen with standard checkboxes
                         all_checked = False
                         all_unchecked = False
                         break # Exit loop early

             # Block signals on the master checkbox while changing its state programmatically
             self.select_all_checkbox_dur.blockSignals(True)
             if all_checked:
                 self.select_all_checkbox_dur.setCheckState(Qt.Checked)
             elif all_unchecked:
                 self.select_all_checkbox_dur.setCheckState(Qt.Unchecked)
             else:
                 # Use PartiallyChecked state to indicate mixed selection
                  self.select_all_checkbox_dur.setCheckState(Qt.PartiallyChecked)
             self.select_all_checkbox_dur.blockSignals(False)


    def start_duration_calculation(self):
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
             QMessageBox.warning(self, "Busy", "Duration calculation is already in progress.")
             return
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            QMessageBox.warning(self, "Busy", "A folder scan is in progress.")
            return

        # Report is saved in the input folder now
        input_folder_str = self.input_line_dur.text().strip()
        if not input_folder_str:
            QMessageBox.critical(self, "Error", "Please select the input video folder first.")
            return
        report_folder_path = Path(input_folder_str)
        if not report_folder_path.is_dir():
             QMessageBox.critical(self, "Error", f"Input folder not found or is not a directory:\n{report_folder_path}")
             return

        # Get selected files from the table
        selected_files: List[Tuple[int, Path]] = []
        for row in range(self.duration_table.rowCount()):
            chk_item = self.duration_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.Checked:
                 file_path = self._row_map_dur.get(row)
                 if file_path:
                     selected_files.append((row, file_path))
                 else:
                      self.log_dur(f"Warning: Could not find path for selected row {row}. Skipping.")


        if not selected_files:
            QMessageBox.information(self, "No Selection", "No files are selected in the table. Please check the boxes for files to include.")
            return

        # Reset progress and total duration label
        self.progress_bar_dur.setValue(0)
        self.total_duration_label.setText("Total Duration of Selection: Calculating...")
        # Clear previous duration results in the table only for selected rows? Or all? Let's clear all visible.
        for row in range(self.duration_table.rowCount()):
            item = self.duration_table.item(row, 2) # Duration column
            if item:
                item.setText("Calculating...") # Indicate which are being processed


        report_base_name = report_folder_path.name # Use input folder name for report
        if not report_base_name: report_base_name = "duration_report" # Fallback if path is root?


        self.duration_calc_worker = DurationCalculateWorker(selected_files, report_folder_path, report_base_name)
        self.duration_calc_worker.log_signal.connect(self.log_dur)
        self.duration_calc_worker.progress_signal.connect(lambda p: self.progress_bar_dur.setValue(p))
        self.duration_calc_worker.file_duration_signal.connect(self.update_duration_table_row)
        self.duration_calc_worker.total_duration_signal.connect(lambda total_str: self.total_duration_label.setText(f"Total Duration of Selection: {total_str}"))
        self.duration_calc_worker.finished_signal.connect(self.duration_calculation_finished)

        self.set_duration_calc_ui_active(True)
        self.duration_calc_worker.start()


    def update_duration_table_row(self, row_index: int, duration_str: str):
        """Update the duration string in a specific table row."""
        # Check if row_index is still valid (table might have changed?)
        if 0 <= row_index < self.duration_table.rowCount():
            item = self.duration_table.item(row_index, 2) # Duration column
            if item:
                item.setText(duration_str)
            else:
                # Should not happen if row exists, but handle defensively
                self.log_dur(f"Warning: Could not find item cell at row {row_index}, col 2 to update duration.")
        else:
            self.log_dur(f"Warning: Row index {row_index} out of bounds for table update.")


    def duration_calculation_finished(self, success: bool, aborted: bool):
        self.set_duration_calc_ui_active(False)
        # Keep progress bar at 100 if successful, otherwise leave as is or reset?
        if success and not aborted:
            self.progress_bar_dur.setValue(100)
        # Reset 'Calculating...' text for rows that were processed but failed (are N/A) or were aborted
        for row in range(self.duration_table.rowCount()):
             item = self.duration_table.item(row, 2)
             if item and item.text() == "Calculating...":
                  item.setText("N/A" if not aborted else "Aborted") # Or leave as N/A on abort


        if aborted:
             QMessageBox.warning(self, "Aborted", "Duration calculation was aborted.")
             self.total_duration_label.setText("Total Duration of Selection: Aborted")
        elif success:
             QMessageBox.information(self, "Complete", "Duration calculation and report generation finished successfully!")
             # Total duration label is set via signal, no need to update here
        else:
             # Check if failure was due to ffprobe missing (handled in worker run)
             if "ffprobe' not found" in self.log_text_dur.toPlainText()[-200:]: # Check recent logs for ffprobe error
                  QMessageBox.critical(self, "Error", "Duration calculation failed: ffprobe executable not found.\nPlease install FFmpeg/ffprobe and ensure it's in your PATH.")
             else:
                  QMessageBox.critical(self, "Error", "Duration calculation or report generation failed. Check logs for details.")
             self.total_duration_label.setText("Total Duration of Selection: Error")

        self.duration_calc_worker = None # Clear worker


    def abort_duration_task(self):
        aborted = False
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            self.log_dur("Abort requested for folder scan...")
            self.duration_scan_worker.stop()
            aborted = True
        elif self.duration_calc_worker and self.duration_calc_worker.isRunning():
             self.log_dur("Abort requested for duration calculation...")
             self.duration_calc_worker.stop()
             aborted = True

        if not aborted:
            self.log_dur("No active duration task (scan or calculate) to abort.")
        # UI update (disabling abort button etc.) happens in the respective finished_signal handlers


    # --- Window Closing ---
    def closeEvent(self, event):
        """Handle window close event to stop running threads."""
        active_workers = []
        worker_stopped = False

        if self.conversion_worker and self.conversion_worker.isRunning():
            active_workers.append("Video Conversion")
            self.conversion_worker.stop()
            worker_stopped = True
        if self.duration_scan_worker and self.duration_scan_worker.isRunning():
            active_workers.append("Folder Scanning")
            self.duration_scan_worker.stop()
            worker_stopped = True
        if self.duration_calc_worker and self.duration_calc_worker.isRunning():
            active_workers.append("Duration Calculation")
            self.duration_calc_worker.stop()
            worker_stopped = True

        if active_workers:
            # Maybe give a slightly more responsive message
            self.statusBar().showMessage(f"Attempting to stop: {', '.join(active_workers)}...")
            QApplication.processEvents() # Allow UI to update

            # Wait a short time for threads to potentially finish cleanly
            # This is a simple approach; a more robust one would involve QThread.wait()
            # or checking isFinished() in a loop with processEvents.
            max_wait_ms = 2000 # e.g., 2 seconds
            start_wait = datetime.datetime.now()
            while worker_stopped and (datetime.datetime.now() - start_wait).total_seconds() * 1000 < max_wait_ms:
                 QApplication.processEvents() # Keep UI responsive during wait
                 worker_stopped = False # Assume finished unless proven otherwise
                 if self.conversion_worker and self.conversion_worker.isRunning(): worker_stopped = True
                 if self.duration_scan_worker and self.duration_scan_worker.isRunning(): worker_stopped = True
                 if self.duration_calc_worker and self.duration_calc_worker.isRunning(): worker_stopped = True
                 if not worker_stopped: break # Exit loop if all stopped
                 # Optional small sleep to prevent busy-waiting
                 # QThread.msleep(50)

            if worker_stopped:
                 print("Warning: Some background tasks may not have terminated gracefully on exit.")
            else:
                 print("Background tasks stopped.")

        event.accept() # Close the window

# -------------------------------
# Application Entry Point
# -------------------------------
if __name__ == "__main__":
    # Helps with scaling on high DPI displays
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = ConverterWindow()
    window.show()
>>>>>>> 61d65bc5879b535e8b74bf5dcc2a05ba6b82538d
    sys.exit(app.exec_())