#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
from datetime import datetime
import questionary
import requests

# =============================================================================
# CONFIGURATION (EDIT THESE PATHS AS NEEDED)
# =============================================================================
INPUT_ROOT = r"./6. Fast Food Stall (LOOK INSIDE)"  
OUTPUT_ROOT = r"./FFStall"
NTFY_TOPIC = "mytopic"             # ntfy topic name
NTFY_SERVER = "https://ntfy.sh"      # ntfy server URL (default public server)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

# =============================================================================
# Global variable to store whether to use NVIDIA CUDA acceleration
# =============================================================================
USE_CUDA = False

# =============================================================================
# Logging function: writes FFmpeg error output to a log file next to the output video.
# =============================================================================
def log_ffmpeg_error(input_file: str, output_file: str, error_output: str) -> None:
    log_file = Path(output_file).with_suffix(".log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Error converting file: {input_file}\n")
        f.write(error_output)
    print(f"Error log written to: {log_file}")

# =============================================================================
# FFmpeg conversion functions
# =============================================================================
def get_video_duration(input_file: str) -> float:
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"Error getting duration for {input_file}: {e}")
        return 0.0

def convert_video_file(input_file: str, output_file: str) -> None:
    total_duration = get_video_duration(input_file)
    if total_duration == 0:
        print(f"Skipping file due to error reading duration: {input_file}")
        return

    # Build the FFmpeg command based on whether CUDA is available.
    if USE_CUDA:
        command = [
            "ffmpeg",
            "-y",                        # Overwrite output file
            "-hwaccel", "cuda",          # Use NVIDIA CUDA acceleration
            "-i", input_file,
            "-vf", "scale=-2:720",       # Resize video to 720p height (width auto-adjusted)
            "-c:v", "h264_nvenc",        # NVENC encoder for H.264
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
            output_file,
        ]
    else:
        command = [
            "ffmpeg",
            "-y",                        # Overwrite output file
            "-i", input_file,
            "-vf", "scale=-2:720",       # Resize video to 720p height (width auto-adjusted)
            "-c:v", "libx264",           # Use software-based H.264 encoding
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
            output_file,
        ]

    # Start FFmpeg process and combine stdout and stderr so we can see all output.
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    print(f"\nConverting: {Path(input_file).name}")
    try:
        # Read and print FFmpeg output line by line.
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            print(line, end="")  # Already has newline characters
    except KeyboardInterrupt:
        print("\nConversion interrupted by user. Terminating FFmpeg process...")
        process.terminate()
        return

    # Capture any remaining output
    output, _ = process.communicate()
    if output:
        print(output)

    if process.returncode != 0:
        print(f"\nError: FFmpeg returned nonzero exit code {process.returncode} for file:")
        print(f"  {input_file}")
        print("Logging FFmpeg error output...")
        log_ffmpeg_error(input_file, output_file, output)
    else:
        print(f"Finished converting {input_file}")

def process_folder(input_dir: str, output_dir: str, include_subdirs: bool = True) -> None:
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    for root, dirs, files in os.walk(input_path):
        current_path = Path(root)
        if not include_subdirs and current_path != input_path:
            continue

        rel_path = current_path.relative_to(input_path)
        target_dir = output_path / rel_path
        target_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            file_path = current_path / file
            if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                out_file = target_dir / f"{file_path.stem}_720p.mp4"
                print(f"\nConverting:\n  Input: {file_path}\n  Output: {out_file}")
                convert_video_file(str(file_path), str(out_file))

# =============================================================================
# ntfy Notification Function
# =============================================================================
def send_ntfy_notification(topic: str, message: str, server: str = "https://ntfy.sh") -> None:
    url = f"{server}/{topic}"
    try:
        response = requests.post(url, data=message.encode("utf-8"))
        if response.status_code == 200:
            print("Ntfy notification sent successfully!")
        else:
            print(f"Error sending ntfy notification: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending ntfy notification: {e}")

# =============================================================================
# Helper Functions for Interactive Selection
# =============================================================================
def list_video_files(root: str):
    root_path = Path(root)
    return [p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]

def list_folders(root: str):
    root_path = Path(root)
    return [p for p in root_path.rglob("*") if p.is_dir() and p != root_path]

# =============================================================================
# Main Interactive Function
# =============================================================================
def main() -> None:
    global USE_CUDA

    # First, ask if this laptop supports NVIDIA CUDA acceleration.
    cuda_supported = questionary.confirm(
        "Does this laptop support NVIDIA CUDA acceleration?"
    ).ask()
    USE_CUDA = bool(cuda_supported)
    if USE_CUDA:
        print("Using NVIDIA GPU acceleration for FFmpeg.")
    else:
        print("Using CPU-based FFmpeg configuration (libx264).")

    mode = questionary.select(
        "Select conversion mode:",
        choices=["File", "Folder"]
    ).ask()

    if mode == "File":
        files = list_video_files(INPUT_ROOT)
        if not files:
            print("No video files found in the input root folder.")
            return

        file_choices = [str(f.relative_to(INPUT_ROOT)) for f in files]
        selected = questionary.select("Select a video file:", choices=file_choices).ask()
        if not selected:
            print("No file selected. Exiting.")
            return

        selected_file = Path(INPUT_ROOT) / selected
        relative_path = selected_file.relative_to(INPUT_ROOT)
        out_dir = Path(OUTPUT_ROOT) / relative_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        output_file = out_dir / f"{selected_file.stem}_720p.mp4"

        print(f"\nConverting file:\n  Input: {selected_file}\n  Output: {output_file}\n")
        convert_video_file(str(selected_file), str(output_file))
        print("File conversion complete!")

    elif mode == "Folder":
        folder_choices = ["Whole Root Folder"]
        subfolders = list_folders(INPUT_ROOT)
        folder_choices.extend([str(f.relative_to(INPUT_ROOT)) for f in subfolders])
        selected_folder = questionary.select("Select a folder:", choices=folder_choices).ask()
        if not selected_folder:
            print("No folder selected. Exiting.")
            return

        if selected_folder == "Whole Root Folder":
            input_folder = Path(INPUT_ROOT)
            output_folder = Path(OUTPUT_ROOT)
        else:
            input_folder = Path(INPUT_ROOT) / selected_folder
            output_folder = Path(OUTPUT_ROOT) / selected_folder

        print(f"\nConverting folder:\n  Input: {input_folder}\n  Output: {output_folder}\n")
        process_folder(str(input_folder), str(output_folder), include_subdirs=True)
        print("Folder conversion complete!")
    else:
        print("Invalid mode selected. Exiting.")
        return

    send_notify = questionary.confirm("Send ntfy notification after conversion?").ask()
    if send_notify:
        message = "Video conversion completed successfully."
        send_ntfy_notification(NTFY_TOPIC, message, NTFY_SERVER)

if __name__ == "__main__":
    main()
