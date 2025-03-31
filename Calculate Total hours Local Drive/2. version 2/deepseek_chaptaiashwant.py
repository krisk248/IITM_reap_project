import os
import hashlib
import subprocess
from collections import defaultdict
from tqdm import tqdm  # For progress bar and ETA

LOG_FILE = "scan_log.txt"

def write_log(message):
    """Write logs to a file."""
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        log.write(message + "\n")

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
        error_message = f"\nError processing {file_path}: {e}"
        write_log(error_message)  # Log error to file
        return 0

def scan_folder(root_folder):
    """Scan the folder and subfolders for video files, calculate durations, and check for duplicates."""
    file_hashes = defaultdict(list)
    folder_durations = defaultdict(float)
    total_duration = 0.0

    # Clear previous log file
    open(LOG_FILE, "w").close()

    # Count total files for progress bar
    print("Counting files...")
    total_files = sum(
        len([fname for fname in filenames if fname.endswith(('.mov', '.mp4'))])
        for _, _, filenames in os.walk(root_folder)
    )
    print(f"Total video files to process: {total_files}")

    # Initialize progress bar
    progress_bar = tqdm(total=total_files, unit="file", desc="Processing", dynamic_ncols=True)

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

                # Update progress bar
                progress_bar.update(1)
                progress_bar.set_postfix(
                    {
                        "Current Folder": os.path.basename(foldername),
                        "Files Left": total_files - progress_bar.n,
                        "Total Duration So Far": f"{total_duration:.2f} sec",
                    }
                )

    # Close progress bar
    progress_bar.close()

    # Log duplicate files
    duplicate_log = "\nDuplicate files (based on content):\n"
    for file_hash, files in file_hashes.items():
        if len(files) > 1:
            duplicate_log += f"Hash: {file_hash}\n"
            for file in files:
                duplicate_log += f"  - {file}\n"
    write_log(duplicate_log)

    # Log folder durations
    folder_duration_log = "\nFolder durations:\n"
    for folder, duration in folder_durations.items():
        folder_duration_log += f"{folder}: {duration:.2f} seconds\n"
    write_log(folder_duration_log)

    # Log total duration
    total_duration_log = f"\nTotal duration of all videos: {total_duration:.2f} seconds\n"
    write_log(total_duration_log)

    # Print summary to console
    print(duplicate_log)
    print(folder_duration_log)
    print(total_duration_log)

if __name__ == "__main__":
    root_folder = r"D:\IIT\ai dubbing"  # Use raw string to handle backslashes
    scan_folder(root_folder)
