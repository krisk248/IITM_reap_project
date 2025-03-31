import os
import re
import subprocess

def natural_sort_key(s):
    """
    Key function for natural sorting (e.g., Chapter 1, Chapter 2, Chapter 10).
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def download_playlist(playlist_url, output_dir="downloaded_videos"):
    """
    Downloads a YouTube playlist using yt-dlp.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Command to download the playlist
    command = [
        "yt-dlp",
        "-f", "bv*+ba/b",  # Best video + audio format
        "-o", f"{output_dir}/%(playlist_index)s - %(title)s.%(ext)s",  # Output filename format
        "--merge-output-format", "mp4",  # Merge into MP4
        "--yes-playlist",  # Ensure it's a playlist
        playlist_url,  # Playlist URL
    ]

    print("Downloading playlist...")
    subprocess.run(command, check=True)
    print("Download complete!")

def create_concat_list(output_dir):
    """
    Creates a list of video files in natural order for concatenation.
    """
    video_files = sorted(
        [f for f in os.listdir(output_dir) if f.endswith(".mp4")],
        key=natural_sort_key,  # Sort using natural sorting
    )

    # Write the list to a file
    with open(os.path.join(output_dir, "list.txt"), "w") as f:
        for video_file in video_files:
            f.write(f"file '{video_file}'\n")

    print("Created concatenation list.")

def concatenate_videos(output_dir, output_file="output.mp4"):
    """
    Concatenates the downloaded videos into a single file using ffmpeg.
    Re-encodes the videos to ensure consistent timestamps and metadata.
    """
    concat_list_path = os.path.join(output_dir, "list.txt")
    output_path = os.path.join(output_dir, output_file)

    # Command to concatenate videos with re-encoding
    command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-vf", "fps=30",  # Set a consistent frame rate (adjust if needed)
        "-c:v", "libx264",  # Re-encode video using H.264
        "-c:a", "aac",  # Re-encode audio using AAC
        "-strict", "experimental",
        output_path,
    ]

    print("Concatenating videos with re-encoding...")
    subprocess.run(command, check=True)
    print(f"Concatenation complete! Output saved to {output_path}")

def main():
    # Input playlist URL
    playlist_url = input("Enter the YouTube playlist URL: ").strip()
    output_dir = "downloaded_videos"

    # Step 1: Download the playlist
    download_playlist(playlist_url, output_dir)

    # Step 2: Create a list of videos for concatenation
    create_concat_list(output_dir)

    # Step 3: Concatenate the videos with re-encoding
    concatenate_videos(output_dir)

if __name__ == "__main__":
    main()