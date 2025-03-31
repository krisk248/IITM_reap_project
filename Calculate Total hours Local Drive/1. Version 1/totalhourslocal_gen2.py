import os
import datetime
from moviepy import VideoFileClip

def format_time_hms(seconds):
    """Converts seconds to 'X hours Y minutes Z seconds' format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours} hours {minutes} minutes and {secs} seconds"

def get_folder_size(folder_path):
    """Calculates the total size of a folder in MB."""
    total_size = 0
    for dirpath, _, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)  # Convert bytes to MB

def log_message(log_file, message):
    """Logs messages with timestamps."""
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")

def get_video_duration(file_path):
    """Returns the duration of a video file in seconds."""
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        log_message(log_file, f"❌ Error processing {file_path}: {e}")
        return 0

def traverse_folder(folder_path, log_file):
    """Recursively scans the folder for video files and logs durations."""
    total_duration = 0
    folder_size = get_folder_size(folder_path)
    start_time = datetime.datetime.now()
    log_message(log_file, f"\n📁 Entering folder: {folder_path}")
    log_message(log_file, f"📦 Folder size: {folder_size:.2f} MB")
    
    for root, _, files in os.walk(folder_path):
        log_message(log_file, f"\n🔍 Scanning directory: {root}")
        for file in files:
            if file.lower().endswith((".mp4", ".mov")):
                file_path = os.path.join(root, file)
                log_message(log_file, f"🎬 Processing: {file}")
                duration = get_video_duration(file_path)
                log_message(log_file, f"✅ Duration: {format_time_hms(duration)}")
                total_duration += duration
    
    end_time = datetime.datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    log_message(log_file, f"⏳ Time taken for '{folder_path}': {format_time_hms(elapsed_time)}")
    log_message(log_file, f"📊 Total video content in '{folder_path}': {format_time_hms(total_duration)}\n")
    return total_duration

if __name__ == "__main__":
    ai_dubbing_folder = r"K:\REAP 15 Course 2024\720p"  # Update with your folder path
    log_file = "All15course_video_duration_log.txt"
    
    # Start Logging
    start_time = datetime.datetime.now()
    log_message(log_file, f"🚀 Log started at {start_time.strftime('%H:%M:%S')} on {start_time.strftime('%Y-%m-%d')}")
    
    total_duration = traverse_folder(ai_dubbing_folder, log_file)
    
    # End Logging
    end_time = datetime.datetime.now()
    elapsed_time = (end_time - start_time).total_seconds()
    log_message(log_file, f"\n🎥 Total video content scanned: {format_time_hms(total_duration)}")
    log_message(log_file, f"⏳ Total time taken: {format_time_hms(elapsed_time)}")
    log_message(log_file, f"🛑 Log ended at {end_time.strftime('%H:%M:%S')} on {end_time.strftime('%Y-%m-%d')}\n")
