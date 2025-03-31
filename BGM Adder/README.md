# K BGMAdder GUI

A simple graphical application built with Python and PyQt5 to add background music (BGM) to video files using FFmpeg.

![Screenshot (Add a screenshot of your app here if possible)]() <!-- Optional: Add a link to a screenshot -->

## Description

This application provides a user-friendly interface to select a video file (or a folder containing video files), a background music audio file, and an output folder. It then uses the powerful `ffmpeg` command-line tool in the background to mix the selected BGM into the original video(s), saving the results as new `.mp4` files.

## Features

*   Process a single video file or recursively process all `.mp4` files within a folder.
*   Select custom background music (MP3, WAV, FLAC, OGG, etc.).
*   Adjust the volume of the background music.
*   Choose an output directory for the processed files.
*   Optional NVIDIA CUDA hardware acceleration for faster encoding (requires compatible hardware and drivers).
*   Optional desktop notifications via [ntfy.sh](https://ntfy.sh/) upon completion.
*   Logs processing steps and errors in the GUI.
*   Option to cancel the ongoing process.
*   Runs processing in a separate thread to keep the GUI responsive.

## How it Works

1.  **User Input:** The user selects the mode (single file or folder), specifies the input video/folder, the BGM audio file, and the output folder using the GUI. They can also adjust the BGM volume and choose whether to use CUDA acceleration.
2.  **Worker Thread:** When the "Add BGM" button is clicked, a separate worker thread (`BGMWorker`) is started to handle the processing without freezing the main GUI.
3.  **FFmpeg Command Generation:** The worker thread constructs an appropriate `ffmpeg` command based on the user's selections.
    *   It takes the original video and the BGM file as inputs.
    *   It uses `-stream_loop -1` to loop the BGM indefinitely.
    *   It uses the `amix` audio filter to mix the original video's audio (if any) with the BGM at the specified volume.
    *   It maps the original video stream and the mixed audio stream to the output.
    *   It uses `-shortest` to ensure the output video duration matches the original video's duration.
    *   If CUDA is enabled, it uses `-hwaccel cuda` for decoding and `-c:v h264_nvenc` for encoding. Otherwise, it attempts to copy the video stream (`-c:v copy`).
4.  **Execution:** The script executes the generated `ffmpeg` command using Python's `subprocess` module.
5.  **Output & Logging:** Output from `ffmpeg` (standard output and standard error) is captured. Progress and status messages are displayed in the GUI's log area.
6.  **File Handling:**
    *   For single files, the output is saved in the chosen output folder with the original filename.
    *   For folders, a new subfolder (with "Wbgm" appended to the original folder name) is created within the output directory, preserving the original folder structure. Output files are saved within this new structure.
7.  **Completion/Cancellation:** Once all files are processed, a success message is logged. If the user cancels, the current `ffmpeg` process is stopped, and any partially created files during the session are cleaned up.
8.  **Notification (Optional):** If an `ntfy.sh` topic is provided, a POST request is sent to notify the user upon successful completion.

## Prerequisites

*   **Python 3:** (e.g., Python 3.6 or newer recommended). You can download Python from [python.org](https://www.python.org/).
*   **FFmpeg:** This application *requires* `ffmpeg` to be installed on your system and accessible via the system's PATH environment variable.
    *   Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
    *   Follow their instructions to install it and add it to your system's PATH. You can test if it's installed correctly by opening a terminal or command prompt and typing `ffmpeg -version`.
*   **(Optional) NVIDIA GPU & Drivers:** Required only if you intend to use the CUDA acceleration feature. Ensure you have the latest NVIDIA drivers installed.

## Installation

It's highly recommended to use a Python virtual environment to manage dependencies.

1.  **Clone or Download:**
    *   If you use Git: `git clone <repository_url>` (Replace `<repository_url>` with the actual URL if hosted)
    *   Or, download the `addbgmguiwin.py` script file directly.

2.  **Navigate to Directory:**
    Open your terminal or command prompt and change to the directory where you saved the script:
    ```bash
    cd path/to/your/script/directory
    ```

3.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    ```
    (Use `python3` if `python` points to Python 2 on your system)

4.  **Activate the Virtual Environment:**
    *   **Windows:** `.\venv\Scripts\activate`
    *   **macOS/Linux:** `source venv/bin/activate`

5.  **Install Dependencies:**
    You need `PyQt5` for the GUI and `requests` for notifications. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    PyQt5>=5.14
    requests>=2.20
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run the Application

1.  **Ensure Prerequisites:** Make sure Python and FFmpeg are installed (and FFmpeg is in your PATH).
2.  **Activate Virtual Environment:** If you closed your terminal, navigate back to the script directory and activate the virtual environment again (see Step 4 in Installation).
3.  **Run the Script:**
    ```bash
    python addbgmguiwin.py
    ```
    (Use `python3` if needed on your system)

4.  **Use the GUI:** The application window will appear. Use the browse buttons and options to configure your task, then click "Add BGM". Monitor the progress in the log area.

## Making it Simpler to Run

Since this is a GUI application, the typical command-line simplifications (like adding to PATH) aren't the most direct approach. Here are common ways to make launching easier:

**Method 1: Desktop Shortcut (Recommended for GUI Apps)**

*   **Windows:**
    1.  Right-click on your desktop or in a folder.
    2.  Select "New" -> "Shortcut".
    3.  For the location, browse to your Python executable *within the virtual environment* (e.g., `path\to\your\script\directory\venv\Scripts\pythonw.exe` - use `pythonw.exe` to avoid a background console window) **OR** create a small batch file (see below) and point the shortcut to that.
    4.  If pointing directly to `pythonw.exe`, add the full path to your script (`addbgmguiwin.py`) as an argument after the executable path, separated by a space.
    5.  Click "Next", give the shortcut a name (e.g., "BGM Adder"), and click "Finish".
    6.  (Optional) Right-click the shortcut -> Properties -> Change Icon... to set the `app1.ico` if it's in the script's directory.

*   **macOS:**
    1.  You can create an AppleScript or Automator application to launch the script.
    2.  A simpler way: Open `Script Editor`, paste `do shell script "cd /path/to/your/script/directory && ./venv/bin/python addbgmguiwin.py"`, save it as an Application.

*   **Linux (Desktop Environments like GNOME, KDE, XFCE):**
    1.  Create a `.desktop` file (e.g., `bgm-adder.desktop`) in `~/.local/share/applications/` or `/usr/share/applications/`.
    2.  The content should look something like this (adjust paths):
        ```ini
        [Desktop Entry]
        Version=1.0
        Name=K BGMAdder GUI
        Comment=Add background music to videos
        Exec=/path/to/your/script/directory/venv/bin/python /path/to/your/script/directory/addbgmguiwin.py
        Icon=/path/to/your/script/directory/app1.ico  # Optional
        Terminal=false
        Type=Application
        Categories=AudioVideo;Video;
        ```
    3.  Make the `.desktop` file executable: `chmod +x ~/.local/share/applications/bgm-adder.desktop`. It should then appear in your application menu.

**Method 2: Simple Runner Script (Cross-Platform)**

Create a small script to activate the environment and run the Python script.

*   **Windows (`run_bgm_adder.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    pythonw.exe addbgmguiwin.py
    deactivate
    ```
    Save this as `run_bgm_adder.bat` in the same directory. Double-click this batch file to run the app. You can create a shortcut to this batch file.

*   **macOS/Linux (`run_bgm_adder.sh`):**
    ```bash
    #!/bin/bash
    # Get the directory where the script resides
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"

    # Activate venv and run python script
    source ./venv/bin/activate
    python addbgmguiwin.py
    deactivate
    ```
    Save as `run_bgm_adder.sh`, make it executable (`chmod +x run_bgm_adder.sh`), and run it with `./run_bgm_adder.sh`. You can create launchers pointing to this shell script.

**Method 3: Bundling (Advanced)**

For true standalone distribution (without needing users to install Python or dependencies), you can use tools like **PyInstaller**:

1.  `pip install pyinstaller` (in your activated venv).
2.  Run PyInstaller: `pyinstaller --onefile --windowed --add-data "app1.ico;." addbgmguiwin.py` (adjust options as needed, especially if you bundle ffmpeg).
3.  This creates a `dist` folder containing a single executable file. This is the most complex method but provides the easiest experience for end-users. Note that bundling ffmpeg requires extra steps.

## Notes

*   Processing video can be time-consuming, depending on the video length, resolution, and your computer's hardware.
*   The "Use NVIDIA CUDA Acceleration" option significantly speeds up processing *only* if you have a supported NVIDIA graphics card and correctly installed drivers. If unsure, leave it unchecked.
*   Ensure the BGM file you select is long enough or that looping it sounds acceptable for your video length.
*   The script currently overwrites output files if they already exist without warning. Be careful when selecting the output directory.