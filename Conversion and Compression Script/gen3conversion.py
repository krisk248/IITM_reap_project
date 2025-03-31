#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path
from datetime import datetime
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TaskProgressColumn,
)
import questionary
import requests

# =============================================================================
# CONFIGURATION (edit these paths and settings as needed)
# =============================================================================
INPUT_ROOT = r"K:\REAP 15 Course 2024\720p"  # <-- Your input root folder
OUTPUT_ROOT = r"W:\Youtube Project scripts\6. Automation Script\0. Converstion Script"  # <-- Your output folder
NTFY_TOPIC = "rclone_reap_iit"                        # <-- Your ntfy topic (used as the endpoint)
NTFY_SERVER = "https://ntfy.sh"               # <-- ntfy server URL (default public server)
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}  # Extend as needed

# =============================================================================
# Logging function
# =============================================================================
def log_ffmpeg_error(input_file: str, output_file: str, error_output: str) -> None:
    """
    Writes the FFmpeg error output to a log file placed next to the output file.
    """
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
    """
    Uses ffprobe to get the total duration (in seconds) of the video file.
    """
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"Error getting duration for {input_file}: {e}")
        return 0.0

def convert_video_file(input_file: str, output_file: str) -> None:
    """
    Convert a single video file to 720p resolution using NVIDIA hardware acceleration
    and a 320k audio bitrate. If FFmpeg fails, the stderr output is logged to a file.
    """
    total_duration = get_video_duration(input_file)
    if total_duration == 0:
        print(f"Skipping file due to error reading duration: {input_file}")
        return

    # Build the FFmpeg command.
    command = [
        "ffmpeg",
        "-y",                        # Overwrite output file without asking
        "-hwaccel", "cuda",          # Use NVIDIA GPU acceleration (remove if problematic)
        "-i", input_file,
        "-vf", "scale=-2:720",       # Resize video to 720p height (width auto-adjusted)
        "-c:v", "h264_nvenc",        # Use NVENC encoder for H.264
        "-preset", "fast",           # Fast encoding preset
        "-c:a", "aac",               # Encode audio to AAC
        "-b:a", "320k",              # Set audio bitrate to 320 kbps
        "-progress", "pipe:1",       # Send progress info to stdout
        "-nostats",                 # Suppress usual FFmpeg stats
        output_file,
    ]

    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        transient=True,
    )
    task = progress.add_task(f"Converting: {Path(input_file).name}", total=total_duration)

    with progress:
        while True:
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue

            line = line.strip()
            if line.startswith("out_time="):
                time_str = line.split("=")[1].strip()  # Format: HH:MM:SS.microseconds
                try:
                    h, m, s = time_str.split(":")
                    current_time = int(h) * 3600 + int(m) * 60 + float(s)
                    progress.update(task, completed=current_time)
                except Exception:
                    pass
            elif line.startswith("progress="):
                if line.split("=")[1].strip() == "end":
                    progress.update(task, completed=total_duration)
                    break

    # Capture any remaining output
    stdout_remaining, stderr_remaining = process.communicate()

    if process.returncode != 0:
        print(f"\nError: FFmpeg returned nonzero exit code {process.returncode} for file:")
        print(f"  {input_file}")
        print("Logging FFmpeg error output...")
        log_ffmpeg_error(input_file, output_file, stderr_remaining)
    else:
        print(f"Finished converting {input_file}")

def process_folder(input_dir: str, output_dir: str, include_subdirs: bool = True) -> None:
    """
    Recursively process a folder (or just its top-level if include_subdirs is False)
    to find video files and convert each one. The folder structure is recreated in the output.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    for root, dirs, files in os.walk(input_path):
        current_path = Path(root)
        if not include_subdirs and current_path != input_path:
            continue

        # Recreate the current folder structure in the output directory.
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
    """
    Sends a notification via ntfy. The 'topic' is appended to the server URL.
    """
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
    """
    Recursively list all video files (matching VIDEO_EXTENSIONS) under the given root.
    Returns a list of Path objects.
    """
    root_path = Path(root)
    return [p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]

def list_folders(root: str):
    """
    Recursively list all subdirectories (excluding the root itself) under the given root.
    Returns a list of Path objects.
    """
    root_path = Path(root)
    return [p for p in root_path.rglob("*") if p.is_dir() and p != root_path]

# =============================================================================
# Main Interactive Function
# =============================================================================
def main() -> None:
    """
    Presents dropdown selections for choosing the conversion mode (File or Folder),
    then lets you pick a video file or a folder (using only selection menus) from the
    hardcoded INPUT_ROOT. The output file(s) are automatically placed into OUTPUT_ROOT
    (with the folder structure recreated).
    """
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
        # Build the output file path inside OUTPUT_ROOT (mirroring relative location)
        relative_path = selected_file.relative_to(INPUT_ROOT)
        out_dir = Path(OUTPUT_ROOT) / relative_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        output_file = out_dir / f"{selected_file.stem}_720p.mp4"

        print(f"\nConverting file:\n  Input: {selected_file}\n  Output: {output_file}\n")
        convert_video_file(str(selected_file), str(output_file))
        print("File conversion complete!")

    elif mode == "Folder":
        # Provide an option to process the whole input root or select a subfolder.
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

    # Ask (via dropdown-style confirmation) if a ntfy notification should be sent.
    send_notify = questionary.confirm("Send ntfy notification after conversion?").ask()
    if send_notify:
        message = "Video conversion completed successfully."
        send_ntfy_notification(NTFY_TOPIC, message, NTFY_SERVER)

if __name__ == "__main__":
    main()
