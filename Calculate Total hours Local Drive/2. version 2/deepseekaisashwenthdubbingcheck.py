import os
import hashlib
from moviepy import VideoFileClip
from collections import defaultdict

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
        print(f"Error processing {file_path}: {e}")
        return 0

def scan_folder(root_folder):
    """Scan the folder and subfolders for video files, calculate durations, and check for duplicates."""
    file_hashes = defaultdict(list)
    folder_durations = defaultdict(float)
    total_duration = 0.0

    for foldername, subfolders, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(('.mov', '.mp4')):
                file_path = os.path.join(foldername, filename)
                file_hash = calculate_file_hash(file_path)
                file_hashes[file_hash].append(file_path)
                duration = get_video_duration(file_path)
                folder_durations[foldername] += duration
                total_duration += duration

    # Print duplicates
    print("Duplicate files (based on content):")
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
    root_folder = r"D:\IIT\ai dubbing"  # Replace with your root folder path
    scan_folder(root_folder)