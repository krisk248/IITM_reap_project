import os
import hashlib
import subprocess
import threading
import queue
from collections import defaultdict
from tqdm import tqdm

ROOT_FOLDER = "D:\IIT\ai dubbing"  # Change this to your root folder

def get_video_duration(file_path):
    """Fetch video duration using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "format=duration", "-of", "csv=p=0", file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip()) if result.stdout.strip() else 0
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def get_file_hash(file_path):
    """Compute MD5 hash of a file to identify duplicates."""
    hasher = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error hashing {file_path}: {e}")
        return None

def process_videos(q, results, duplicates, lock):
    """Worker thread to process video files."""
    while not q.empty():
        folder, file_path = q.get()
        file_hash = get_file_hash(file_path)

        with lock:
            if file_hash in duplicates:
                q.task_done()
                continue  # Skip duplicate files
            duplicates.add(file_hash)

        duration = get_video_duration(file_path)

        with lock:
            results[folder] += duration

        q.task_done()

def scan_folder(root_folder):
    """Scan folders for video files and calculate durations."""
    results = defaultdict(float)
    duplicates = set()
    q = queue.Queue()
    lock = threading.Lock()
    
    # Collect video files
    for folder, _, files in os.walk(root_folder):
        for file in files:
            if file.lower().endswith(('.mp4', '.mov')):
                q.put((folder, os.path.join(folder, file)))

    # Multithreading setup
    num_threads = min(8, os.cpu_count())  # Use up to 8 threads or CPU cores
    threads = [threading.Thread(target=process_videos, args=(q, results, duplicates, lock)) for _ in range(num_threads)]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results

def main():
    print("Scanning files, please wait...")
    results = scan_folder(ROOT_FOLDER)
    
    total_duration = sum(results.values())

    print("\n===== Video Duration Report =====")
    for folder, duration in results.items():
        print(f"{folder}: {duration/3600:.2f} hours")
    print(f"\nTotal Duration: {total_duration/3600:.2f} hours")
    
if __name__ == "__main__":
    main()
