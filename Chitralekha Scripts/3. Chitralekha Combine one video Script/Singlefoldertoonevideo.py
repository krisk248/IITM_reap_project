import os
import re
import subprocess

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def combine_videos_fast(folder_path, output_file):
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return

    video_files = [f for f in os.listdir(folder_path) if f.endswith('.mp4')]
    if not video_files:
        print("Error: No MP4 files found in the specified folder.")
        return

    video_files.sort(key=natural_sort_key)

    # Create videos.txt file with absolute paths and forward slashes
    txt_file_path = os.path.join(folder_path, "videos.txt")
    with open(txt_file_path, "w") as txt_file:
        for video in video_files:
            full_path = os.path.abspath(os.path.join(folder_path, video)).replace("\\", "/")
            txt_file.write(f"file '{full_path}'\n")

    # Combine videos using FFmpeg
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", txt_file_path,
                "-c", "copy",
                output_file
            ],
            check=True
        )
        print(f"Combined video saved as: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during video combination: {e}")
    finally:
        # Clean up the videos.txt file
        os.remove(txt_file_path)
        print("The video is done")

# Example usage
combine_videos_fast(folder_path="W:\Course Video\Electric Rewinding English\Electricmotoren", output_file="fmpegelctrcicombined_video.mp4")
