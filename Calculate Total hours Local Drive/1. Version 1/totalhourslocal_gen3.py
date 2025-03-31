import os
import datetime
import hashlib
from moviepy import VideoFileClip

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
    size_gb = total_size / (1024 * 1024 * 1024)
    size_mb = (total_size % (1024 * 1024 * 1024)) / (1024 * 1024)
    return f"{size_gb:.2f} GB and {size_mb:.2f} MB"

def generate_uid(folder_path):
    return hashlib.sha1(folder_path.encode()).hexdigest()[:10]

def log_message(log_file, message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")

def get_video_duration(file_path):
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        return 0

def traverse_folder(folder_path, log_file):
    root_uid = generate_uid(folder_path)
    total_duration = 0
    course_durations = {}
    log_message(log_file, f"\n🚀 Log started for root folder: {folder_path} [UID: {root_uid}]")
    log_message(log_file, f"📦 Folder size: {get_folder_size(folder_path)}")
    
    for course_folder in sorted(os.listdir(folder_path)):
        course_path = os.path.join(folder_path, course_folder)
        if not os.path.isdir(course_path):
            continue
        
        course_uid = generate_uid(course_path)
        course_duration = 0
        log_message(log_file, f"\n📁 Entering Course: {course_folder} [UID: {course_uid}]")
        
        for root, _, files in os.walk(course_path):
            log_message(log_file, f"\n🔍 Scanning directory: {root}")
            for file in files:
                if file.lower().endswith((".mp4", ".mov")):
                    file_path = os.path.join(root, file)
                    duration = get_video_duration(file_path)
                    log_message(log_file, f"🎬 Processing: {file} - Duration: {format_time_hms(duration)}")
                    course_duration += duration
        
        course_durations[course_folder] = course_duration
        total_duration += course_duration
        log_message(log_file, f"📊 Total duration for '{course_folder}': {format_time_hms(course_duration)} [UID: {course_uid}]")
    
    log_message(log_file, "\n🎥 Summary of all courses:")
    for course, duration in course_durations.items():
        log_message(log_file, f"📊 {course}: {format_time_hms(duration)}")
    
    log_message(log_file, f"\n📊 Total video content in '{folder_path}': {format_time_hms(total_duration)} [UID: {root_uid}]")
    log_message(log_file, "🛑 Log ended\n")

if __name__ == "__main__":
    root_folder = r"K:\\REAP 15 Course 2024\\720p"  # Update with actual folder path
    log_file = "ALLCOURSE_bestvideo_duration_log.txt"
    traverse_folder(root_folder, log_file)
