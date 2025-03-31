import os
import re
import subprocess

def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def combine_all_videos(root_folder, final_output_file):
    all_video_files = []

    # Traverse all subfolders and collect MP4 files
    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.endswith(".mp4"):
                full_path = os.path.abspath(os.path.join(dirpath, filename)).replace("\\", "/")
                all_video_files.append(full_path)

    if not all_video_files:
        print(f"No MP4 files found in the root folder: {root_folder}")
        return

    # Sort videos naturally
    all_video_files.sort(key=natural_sort_key)

    # Create videos.txt with all video paths
    txt_file_path = os.path.join(root_folder, "all_videos.txt")
    with open(txt_file_path, "w") as txt_file:
        for video in all_video_files:
            txt_file.write(f"file '{video}'\n")

    # Combine all videos using FFmpeg
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", txt_file_path,
                "-c", "copy",
                final_output_file
            ],
            check=True
        )
        print(f"All videos combined into: {final_output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error during video combination: {e}")
    finally:
        os.remove(txt_file_path)

# Example usage
combine_all_videos(
    root_folder="W:/Course Video",
    final_output_file="W:/Course Video/final_combined_video.mp4"
)
