import os
import datetime
import hashlib
import csv
from concurrent.futures import ProcessPoolExecutor
from moviepy import VideoFileClip

def format_time_hms(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours} hours {minutes} minutes and {secs} seconds"

def get_video_duration(file_path):
    try:
        with VideoFileClip(file_path) as clip:
            return clip.duration
    except Exception:
        return 0

def generate_uid(folder_path):
    return hashlib.sha1(folder_path.encode()).hexdigest()[:10]

def process_folder(root, files):
    folder_duration = 0
    for file in files:
        if file.lower().endswith((".mp4", ".mov")):
            file_path = os.path.join(root, file)
            folder_duration += get_video_duration(file_path)
    return root, folder_duration

def traverse_folder(folder_path, log_file, csv_file):
    start_time = datetime.datetime.now()
    folder_durations = {}
    
    with ProcessPoolExecutor(max_workers=11) as executor:
        futures = []
        for root, _, files in os.walk(folder_path):
            futures.append(executor.submit(process_folder, root, files))
        
        for future in futures:
            root, duration = future.result()
            folder_durations[root] = duration
    
    # Aggregate durations for parent folders
    sorted_folders = sorted(folder_durations.keys(), key=lambda x: x.count(os.sep), reverse=True)
    for folder in sorted_folders:
        parent = os.path.dirname(folder)
        if parent in folder_durations:
            folder_durations[parent] += folder_durations[folder]
    
    # Logging and CSV writing
    with open(log_file, "w", encoding="utf-8") as log, open(csv_file, "w", newline="", encoding="utf-8") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["Course Name", "Duration"])
        
        for folder, duration in sorted(folder_durations.items()):
            formatted_duration = format_time_hms(duration)
            log.write(f"📂 {folder.replace(folder_path, '').strip(os.sep)}: {formatted_duration}\n")
            csv_writer.writerow([folder.replace(folder_path, '').strip(os.sep), formatted_duration])
    
    end_time = datetime.datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"\n🛑 Log ended at {end_time.strftime('%H:%M:%S')} on {end_time.strftime('%Y-%m-%d')}\n")
        log.write(f"⏳ Total processing time: {format_time_hms(elapsed_time)}\n")

if __name__ == "__main__":
    ai_dubbing_folder = r"D:\IIT\ai dubbing"
    log_file = "Ashwanth_videooneai_duration_log.txt"
    csv_file = "Ashwantrh_videooneai_duration.csv"
    
    traverse_folder(ai_dubbing_folder, log_file, csv_file)
