# Kannan's Video Converter GUI

A graphical application built with Python and PyQt5 to convert video files to 720p H.264 MP4 format using FFmpeg, with optional CUDA acceleration and duration checking features.

![Screenshot (Add a screenshot of your app here if possible)]() <!-- Optional: Add a link to a screenshot -->

## Description

This application provides a user-friendly interface for converting video files (individually or in batches from folders) into a standardized 720p MP4 format suitable for various uses. It leverages the power of FFmpeg for conversion and FFprobe for duration analysis. The tool includes options for using NVIDIA GPU acceleration (CUDA) and sending notifications upon completion.

## Features

*   **Graphical User Interface (GUI):** Easy-to-use interface built with PyQt5.
*   **File or Folder Mode:** Convert a single video file or recursively process all supported videos within a selected folder.
*   **Input/Output Selection:** Browse for input file/folder and output destination folder.
*   **Standardized Output:** Converts videos to `.mp4` container, `H.264` (libx264 or h264_nvenc) video codec, `AAC` audio codec (320k bitrate), and scales video height to 720p while maintaining aspect ratio.
*   **NVIDIA CUDA Acceleration:** Optional hardware acceleration using `h264_nvenc` for faster conversions on compatible NVIDIA GPUs.
*   **Duration Checking:** Separate function to scan videos (file or folder) and generate a `video_durations.txt` file listing individual and total durations using `ffprobe`.
*   **Real-time Progress:** Displays conversion progress using a progress bar, updated based on FFmpeg's output.
*   **Responsive UI:** Uses `QThread` to run conversion and duration checks in the background, keeping the GUI responsive.
*   **Abort/Cancel Functionality:** Stop ongoing conversion or duration check processes. Partially created files during aborted conversions are cleaned up.
*   **Logging:** Displays status messages and FFmpeg output within the application's log area.
*   **Error Logging:** If FFmpeg encounters an error during conversion, a `.log` file is created alongside the intended output file containing error details.
*   **Notification:** Optionally sends a completion notification via [ntfy.sh](https://ntfy.sh/) to a predefined topic (`rclone_reap_iit`).
*   **Automatic FFmpeg Detection:** Attempts to locate the FFmpeg binary using `imageio-ffmpeg` if installed, otherwise defaults to `ffmpeg`.

## How it Works

1.  **GUI Setup:** The application initializes a PyQt5 window with input fields, radio buttons for mode selection, checkboxes for options, action buttons, a progress bar, and a log display area.
2.  **User Input:** The user selects the mode (File/Folder), specifies the input source and output folder, and chooses options (CUDA, Notification).
3.  **Operation Selection:**
    *   **Convert:** Initiates the video conversion process.
    *   **Check Duration:** Initiates the duration calculation process.
4.  **Worker Threads:** To prevent the GUI from freezing during potentially long operations, tasks are delegated to separate `QThread` instances:
    *   `ConversionWorker`: Handles the video conversion process.
    *   `DurationWorker`: Handles the duration calculation process.
5.  **Conversion Process (`ConversionWorker`):**
    *   **File Discovery:** Scans the input path (single file or recursively through a folder) for files matching `VIDEO_EXTENSIONS`.
    *   **FFmpeg Command:** Constructs an `ffmpeg` command based on user selections:
        *   Input file (`-i`).
        *   Output file (`.mp4`). The folder structure is preserved relative to the input folder when processing folders.
        *   Video Scaling: `-vf scale=-2:720`.
        *   Video Codec: `-c:v h264_nvenc` (if CUDA enabled) or `-c:v libx264` (CPU). `-preset fast` is used.
        *   Audio Codec: `-c:a aac -b:a 320k`.
        *   Hardware Acceleration: `-hwaccel cuda` added before `-i` if CUDA is enabled.
        *   Progress Reporting: `-progress pipe:1 -nostats` flags added to capture progress info.
        *   Overwrite: `-y` flag allows overwriting existing output files.
    *   **Execution:** Runs the `ffmpeg` command using `subprocess.Popen`.
    *   **Progress Tracking:** Reads `ffmpeg`'s standard output line by line. Parses lines like `out_time_ms=` or `progress=end` to calculate the percentage completion and updates the GUI progress bar via signals (`progress_signal`).
    *   **Logging:** Sends status messages (starting, finished, error) and potentially relevant `ffmpeg` output to the GUI log area via signals (`log_signal`).
    *   **Error Handling:** If `ffmpeg` returns a non-zero exit code, it logs the error and calls `write_error_log` to save detailed error output to a `.log` file in the output directory.
    *   **Abort/Cancel:** If the user clicks Abort/Cancel, a stop event is set. The worker checks this event periodically and kills the running `ffmpeg` process if set. It then emits a signal indicating abortion (`finished_signal`).
    *   **Cleanup:** If aborted, attempts to delete any output files created during that specific run.
    *   **Notification:** If enabled and successful, sends a POST request to the configured `ntfy.sh` topic.
6.  **Duration Check Process (`DurationWorker`):**
    *   **File Discovery:** Similar to the conversion worker, finds relevant video files.
    *   **FFprobe Execution:** For each video file, calls the `get_video_duration` helper function, which runs `ffprobe` via `subprocess` to extract the duration in seconds.
    *   **Aggregation:** Sums up the durations of all processed files.
    *   **Progress Tracking:** Updates the GUI progress bar based on the number of files processed.
    *   **Output File:** Writes the results (individual filenames with formatted durations and the total formatted duration) to `video_durations.txt` in the selected *output folder*.
    *   **Logging & Signals:** Similar to the conversion worker for logging and completion signals.

## Prerequisites

*   **Python 3:** (e.g., Python 3.6 or newer recommended). Download from [python.org](https://www.python.org/).
*   **FFmpeg:** This application **requires** `ffmpeg` to be installed on your system and accessible via the system's PATH environment variable, or detectable by `imageio-ffmpeg`.
    *   Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
    *   Follow their instructions to install it and add it to your system's PATH. Test by opening a terminal/command prompt and typing `ffmpeg -version`.
*   **FFprobe:** This tool is also required for duration checking and usually comes bundled with FFmpeg. Ensure it's also accessible in your PATH. Test with `ffprobe -version`.
*   **(Optional) NVIDIA GPU & Drivers:** Required only if you intend to use the CUDA acceleration feature. Ensure you have compatible hardware and the latest NVIDIA drivers installed.

## Installation

It's highly recommended to use a Python virtual environment.

1.  **Clone or Download:**
    *   Get the `conversiongui_gen1.py` script file.

2.  **Navigate to Directory:**
    Open your terminal or command prompt and change to the directory where you saved the script:
    ```bash
    cd path/to/your/script/directory
    ```

3.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    ```
    (Use `python3` if needed)

4.  **Activate the Virtual Environment:**
    *   **Windows:** `.\venv\Scripts\activate`
    *   **macOS/Linux:** `source venv/bin/activate`

5.  **Install Dependencies:**
    You need `PyQt5` for the GUI, `requests` for notifications, and optionally `imageio-ffmpeg` to help find the ffmpeg binary. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    PyQt5>=5.14
    requests>=2.20
    imageio-ffmpeg>=0.4.5  # Optional, but recommended
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run the Application

1.  **Ensure Prerequisites:** Make sure Python, FFmpeg, and FFprobe are installed and accessible in your PATH.
2.  **Activate Virtual Environment:** If you closed your terminal, navigate back to the script directory and activate the virtual environment again (see Step 4 in Installation).
3.  **Run the Script:**
    ```bash
    python conversiongui_gen1.py
    ```
    (Use `python3` if needed on your system)

4.  **Use the GUI:**
    *   Select "File" or "Folder" mode.
    *   Click "Browse" to select your input source.
    *   Click "Browse" to select your output folder.
    *   Check/uncheck "Use NVIDIA CUDA" and "Send ntfy notification" as desired.
    *   Click "Convert" to start converting or "Check Duration" to analyze durations.
    *   Monitor progress in the progress bar and log area.
    *   Use "Abort" or "Cancel" to stop an ongoing process if needed.

## Making it Simpler to Run

Since this is a GUI application, creating shortcuts is often the most convenient way to launch it.

**Method 1: Desktop Shortcut (Recommended for GUI Apps)**

*   **Windows:**
    1.  Right-click -> "New" -> "Shortcut".
    2.  Location: Browse to `pythonw.exe` inside your virtual environment (`path\to\venv\Scripts\pythonw.exe`). Use `pythonw.exe` to avoid a console window appearing.
    3.  Append the full path to `conversiongui_gen1.py` after the executable path (e.g., `C:\path\to\venv\Scripts\pythonw.exe C:\path\to\script\conversiongui_gen1.py`).
    4.  Click "Next", name the shortcut (e.g., "Video Converter"), and "Finish".
    5.  *(Alternative)*: Create a `.bat` file (see Method 2) and point the shortcut to that.

*   **macOS:**
    1.  Use `Script Editor` to create a simple AppleScript: `do shell script "cd /path/to/your/script/directory && ./venv/bin/python conversiongui_gen1.py"`. Save it as an Application.

*   **Linux (Desktop Environments):**
    1.  Create a `.desktop` file (e.g., `video-converter.desktop`) in `~/.local/share/applications/`.
    2.  Content (adjust paths):
        ```ini
        [Desktop Entry]
        Version=1.0
        Name=Kannan's Video Converter
        Comment=Convert videos to 720p MP4
        Exec=/path/to/venv/bin/python /path/to/script/conversiongui_gen1.py
        Icon=video-x-generic  # Or specify a custom icon path
        Terminal=false
        Type=Application
        Categories=AudioVideo;Video;Conversion;
        ```
    3.  Make executable: `chmod +x ~/.local/share/applications/video-converter.desktop`.

**Method 2: Simple Runner Script (.bat / .sh)**

*   **Windows (`run_converter.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    pythonw.exe conversiongui_gen1.py
    deactivate
    ```
    Save in the script directory and double-click to run.

*   **macOS/Linux (`run_converter.sh`):**
    ```bash
    #!/bin/bash
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"
    source ./venv/bin/activate
    python conversiongui_gen1.py
    deactivate
    ```
    Save, make executable (`chmod +x run_converter.sh`), and run (`./run_converter.sh`).

**Method 3: Bundling (Advanced)**

Use tools like **PyInstaller** to create a standalone executable (requires more setup, especially handling the ffmpeg/ffprobe dependency if you want to bundle them).
    `pip install pyinstaller`
    `pyinstaller --onefile --windowed conversiongui_gen1.py` (Basic command, may need adjustments)

## Output Explanation

*   **Converted Videos:** `.mp4` files created in the specified output folder. If the input was a folder, the relative subdirectory structure is maintained within the output folder.
*   **Duration File:** If "Check Duration" is run, a `video_durations.txt` file is created in the *output folder*, containing individual and total formatted video durations.
*   **Error Logs:** If a conversion fails due to an FFmpeg error, a `.log` file (e.g., `myvideo.log`) will appear next to where the output video (`myvideo.mp4`) would have been created, containing the FFmpeg error output.
*   **GUI Log:** The text area within the application displays real-time status updates.
*   **Ntfy Notification:** A message sent to the `https://ntfy.sh/rclone_reap_iit` topic upon successful conversion completion (if the option is checked).

## Notes & Caveats

*   **FFmpeg/FFprobe Path:** The script relies heavily on finding `ffmpeg` and `ffprobe`. Ensure they are correctly installed and accessible in your system's PATH.
*   **Performance:** Video conversion is resource-intensive. Conversion times depend heavily on video length, source format, CPU speed, and GPU capabilities (if using CUDA).
*   **CUDA:** The CUDA option only works if you have a compatible NVIDIA GPU and correctly installed drivers recognized by FFmpeg.
*   **File Overwriting:** The script uses the `-y` flag in FFmpeg, meaning it will automatically overwrite existing files in the output directory if they have the same name. Be cautious when selecting the output folder.
*   **`ntfy` Topic:** The notification topic (`rclone_reap_iit`) is hardcoded. You may want to modify the script or add a configuration option if you need to change this.
*   **Error Handling:** While basic error logging is implemented for FFmpeg failures, other issues (e.g., file permissions, disk space) might cause problems. Check the GUI log for details.