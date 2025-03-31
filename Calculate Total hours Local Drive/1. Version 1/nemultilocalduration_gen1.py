import os
import datetime
import hashlib
from moviepy import VideoFileClip
from concurrent.futures import ProcessPoolExecutor

def format_time_hms(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours} hours {minutes} minutes and {secs} seconds"

def get_folder_size(folder_path):
    total_size = 0
    for dirpath, _, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    size_gb = total_size / (1024 ** 3)
    size_mb = total_size / (1024 ** 2)
    return f"{size_gb:.2f} GB and {size_mb:.2f} MB"

def log_message(log_file, message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")

def get_video_duration(file_path):
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return file_path, duration
    except Exception as e:
        return file_path, 0

def generate_uid(folder_path):
    return hashlib.sha1(folder_path.encode()).hexdigest()[:10]

def process_videos_in_folder(root, files):
    total_duration = 0
    video_files = [os.path.join(root, f) for f in files if f.lower().endswith((".mp4", ".mov"))]
    
    with ProcessPoolExecutor(max_workers=11) as executor:
        results = executor.map(get_video_duration, video_files)
        
    for file_path, duration in results:
        total_duration += duration
    
    return root, total_duration

def traverse_folder(folder_path, log_file):
    folder_durations = {}
    total_duration = 0
    start_time = datetime.datetime.now()
    
    log_message(log_file, f"\n📁 Entering folder: {folder_path} [UID: {generate_uid(folder_path)}]")
    log_message(log_file, f"📦 Folder size: {get_folder_size(folder_path)}")
    
    with ProcessPoolExecutor(max_workers=11) as executor:
        future_results = {}
        for root, _, files in os.walk(folder_path):
            if files:
                future_results[executor.submit(process_videos_in_folder, root, files)] = root
        
        for future in future_results:
            folder, duration = future.result()
            folder_durations[folder] = duration
            total_duration += duration
            log_message(log_file, f"📊 Total duration in '{folder}': {format_time_hms(duration)} [UID: {generate_uid(folder)}]")
    
    end_time = datetime.datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    
    log_message(log_file, f"\n📊 Total video content in '{folder_path}': {format_time_hms(total_duration)} [UID: {generate_uid(folder_path)}]")
    log_message(log_file, f"⏳ Total time taken: {format_time_hms(elapsed_time)}")
    
    log_message(log_file, "\nFinal Summary:")
    log_message(log_file, f"📁 Root: {format_time_hms(total_duration)}")
    for folder, duration in sorted(folder_durations.items()):
        indent_level = folder.replace(folder_path, "").count(os.sep)
        indent = "  " * indent_level
        log_message(log_file, f"{indent}📂 {os.path.basename(folder)}: {format_time_hms(duration)}")
    
    log_message(log_file, f"🛑 Log ended at {end_time.strftime('%H:%M:%S')} on {end_time.strftime('%Y-%m-%d')}\n")

if __name__ == "__main__":
    ai_dubbing_folder = r"D:\IIT\ai dubbing"
    log_file = "Ashwanth_ai_444gb_dubbing_duration_log.txt"
    
    start_time = datetime.datetime.now()
    log_message(log_file, f"🚀 Log started at {start_time.strftime('%H:%M:%S')} on {start_time.strftime('%Y-%m-%d')}")
    traverse_folder(ai_dubbing_folder, log_file)
