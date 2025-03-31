import os
import hashlib
from moviepy import VideoFileClip
from collections import defaultdict
from tqdm import tqdm  # For progress bar and ETA

def calculate_file_hash(file_path, hash_algo=hashlib.md5, chunk_size=8192):
    """Calculate the hash of a file based on its content."""
    hash_obj = hash_algo()
    with open(file_path, 'rb') as f:
        while chunk := f.read(chunk_size):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()

def get_video_duration(file_path):
    """Get the duration of a video file."""
    try:
        with VideoFileClip(file_path) as video:
            return video.duration
    except Exception as e:
        print(f"\nError processing {file_path}: {e}")
        return 0

def scan_folder(root_folder):
    """Scan the folder and subfolders for video files, calculate durations, and check for duplicates."""
    file_hashes = defaultdict(list)
    folder_durations = defaultdict(float)
    total_duration = 0.0

    # Count total files for progress bar
    print("Counting files...")
    total_files = sum(
        len(filenames)
        for _, _, filenames in os.walk(root_folder)
        if any(fname.endswith(('.mov', '.mp4')) for fname in filenames)
    )
    print(f"Total video files to process: {total_files}")

    # Initialize progress bar
    progress_bar = tqdm(total=total_files, unit="file", desc="Processing", dynamic_ncols=True)

    # Walk through the folder
    for foldername, subfolders, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(('.mov', '.mp4')):
                file_path = os.path.join(foldername, filename)
                file_hash = calculate_file_hash(file_path)
                file_hashes[file_hash].append(file_path)
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

    # Print duplicates
    print("\nDuplicate files (based on content):")
    for file_hash, files in file_hashes.items():
        if len(files) > 1:
            print(f"Hash: {file_hash}")
            for file in files:
                print(f"  - {file}")

    # Print folder durations
    print("\nFolder durations:")
    for folder, duration in folder_durations.items():
        print(f"{folder}: {duration:.2f} seconds")

    # Print total duration
    print(f"\nTotal duration of all videos: {total_duration:.2f} seconds")

if __name__ == "__main__":
    # Use a raw string or replace backslashes with forward slashes
    root_folder = r"D:\IIT\ai dubbing"  # Raw string to handle backslashes
    # Alternatively, you can use:
    # root_folder = "D:/IIT/ai dubbing"  # Forward slashes work in Python
    scan_folder(root_folder)