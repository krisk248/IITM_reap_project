import os
from moviepy import VideoFileClip

def format_time_hms(seconds):
    """Converts seconds to 'X hours Y minutes Z seconds' format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours} hours {minutes} minutes and {secs} seconds"

def get_video_duration(file_path):
    """Returns the duration of a video file in seconds."""
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration
        clip.close()
        return duration
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0

def traverse_folder(folder_path, log_file):
    """Recursively scans the folder for video files and calculates total duration."""
    total_duration = 0
    with open(log_file, "w", encoding="utf-8") as log:
        log.write(f"Scanning folder: {folder_path}\n")
        
        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith((".mp4", ".mov")):
                    file_path = os.path.join(root, file)
                    duration = get_video_duration(file_path)
                    log.write(f"{file}: {format_time_hms(duration)}\n")
                    total_duration += duration
                    
        log.write(f"\nTotal video duration: {format_time_hms(total_duration)}\n")
        print(f"Total video duration: {format_time_hms(total_duration)}")

if __name__ == "__main__":
    ai_dubbing_folder = r"D:\IIT\ai dubbing"  # Update with your folder path
    log_file = "./aiashwanthvideo_duration_log.txt"
    traverse_folder(ai_dubbing_folder, log_file)