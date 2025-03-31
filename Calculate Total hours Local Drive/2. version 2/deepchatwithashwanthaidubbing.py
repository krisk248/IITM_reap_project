import os
import hashlib
import subprocess
from collections import defaultdict
from tqdm import tqdm  # For progress bar and ETA

LOG_DIR = "./ashwanthscan_logs"
SCAN_LOG = os.path.join(LOG_DIR, "scan_log.txt")
DUPLICATES_LOG = os.path.join(LOG_DIR, "duplicates_log.txt")
DUPLICATES_SUMMARY = os.path.join(LOG_DIR, "duplicates_summary.txt")

# ANSI Color Codes for Text Files
GREEN = "\033[92m"  # Green for original file
RED = "\033[91m"  # Red for duplicate file
RESET = "\033[0m"  # Reset color

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def write_log(file_path, message, mode="a"):
    """Write logs to a file."""
    with open(file_path, mode, encoding="utf-8") as log:
        log.write(message + "\n")

def format_duration(seconds):
    """Convert seconds to HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

def calculate_file_hash(file_path, hash_algo=hashlib.md5, chunk_size=8192):
    """Calculate the hash of a file based on its content."""
    hash_obj = hash_algo()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

def get_video_duration(file_path):
    """Get the duration of a video file using FFmpeg (suppressed output)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of", "csv=p=0", file_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0
        return duration
    except Exception as e:
        write_log(SCAN_LOG, f"⚠️ Error processing {file_path}: {e}")
        return 0

def scan_folder(root_folder):
    """Scan the folder and subfolders for video files, calculate durations, and check for duplicates."""
    file_hashes = defaultdict(list)
    folder_durations = defaultdict(float)
    total_duration = 0.0
    duplicate_size = 0
    duplicate_duration = 0

    # Clear previous logs
    for log_file in [SCAN_LOG, DUPLICATES_LOG, DUPLICATES_SUMMARY]:
        open(log_file, "w").close()

    # Count total files for progress bar
    print("📂 Counting files...")
    total_files = sum(
        len([fname for fname in filenames if fname.endswith(('.mov', '.mp4'))])
        for _, _, filenames in os.walk(root_folder)
    )
    print(f"🎬 Total video files to process: {total_files}")

    # Initialize progress bar
    progress_bar = tqdm(total=total_files, unit="file", desc="🔍 Processing", dynamic_ncols=True)

    # Walk through the folder
    for foldername, subfolders, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(('.mov', '.mp4')):
                file_path = os.path.join(foldername, filename)

                # Calculate file hash
                file_hash = calculate_file_hash(file_path)
                file_hashes[file_hash].append(file_path)

                # Get video duration
                duration = get_video_duration(file_path)
                folder_durations[foldername] += duration
                total_duration += duration

                # Log individual file duration
                write_log(SCAN_LOG, f"📄 {file_path} - {format_duration(duration)}")

                # Update progress bar
                progress_bar.update(1)
                progress_bar.set_postfix(
                    {
                        "Current Folder": os.path.basename(foldername),
                        "Files Left": total_files - progress_bar.n,
                        "Total Duration": format_duration(total_duration),
                    }
                )

    # Close progress bar
    progress_bar.close()

    # Log duplicate files
    duplicate_log = "\n🔴 Duplicate Files Found:\n"
    for file_hash, files in file_hashes.items():
        if len(files) > 1:
            duplicate_log += f"\n🆔 Hash: {file_hash}\n"
            for i, file in enumerate(files):
                size = os.path.getsize(file) / (1024 * 1024)  # Convert to MB
                duration = get_video_duration(file)
                duplicate_size += size
                duplicate_duration += duration
                color = GREEN if i == 0 else RED
                duplicate_log += f"{color}  - {file} ({size:.2f} MB, {format_duration(duration)}){RESET}\n"
    write_log(DUPLICATES_LOG, duplicate_log, mode="w")

    # Log folder durations
    folder_duration_log = "\n📂 Folder Durations:\n"
    for folder, duration in folder_durations.items():
        folder_duration_log += f"📁 {folder} - {format_duration(duration)}\n"
    write_log(SCAN_LOG, folder_duration_log)

    # Log total duration
    total_duration_log = f"\n🎥 Total Duration of All Videos: {format_duration(total_duration)}"
    write_log(SCAN_LOG, total_duration_log)

    # Log duplicate summary
    duplicate_summary = (
        f"\n📑 Duplicate Files Summary:\n"
        f"🔄 Total Duplicate Size: {duplicate_size:.2f} MB\n"
        f"⏳ Total Duplicate Duration: {format_duration(duplicate_duration)}\n"
        f"📊 Content Duration After Removing Duplicates: {format_duration(total_duration - duplicate_duration)}\n"
    )
    write_log(DUPLICATES_SUMMARY, duplicate_summary, mode="w")

    # Print final summary
    print(duplicate_log)
    print(folder_duration_log)
    print(total_duration_log)
    print(duplicate_summary)

if __name__ == "__main__":
    root_folder = r"D:\IIT\ai dubbing"  # Use raw string to handle backslashes
    scan_folder(root_folder)
