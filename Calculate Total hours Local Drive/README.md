# Video Folder Analysis Tools

This project contains two Python scripts designed to analyze video files (`.mp4`, `.mov`) within a specified directory structure:

1.  **`totalcourseduartionlocal_gen4.py`**: Calculates the total duration of videos within each subfolder and aggregates these durations up to parent folders. It outputs the results to structured log (`.txt`) and CSV (`.csv`) files.
2.  **`deepseekaisashwenthdubbingcheck.py`**: Scans folders for videos, calculates the duration per folder, the total duration across all videos, and identifies duplicate video files based on their content hash (MD5). It prints the results directly to the console.

## Features

*   **Recursive Scanning:** Both scripts process videos in the specified root folder and all its subdirectories.
*   **Duration Calculation:** Use the `moviepy` library to determine the duration of individual video files.
*   **Aggregated Durations (Script 1):** Calculates total video duration for each folder, summing up durations from its subfolders.
*   **Structured Reporting (Script 1):** Generates human-readable `.txt` log and machine-readable `.csv` files summarizing folder durations. Includes processing time.
*   **Parallel Processing (Script 1):** Uses `concurrent.futures.ProcessPoolExecutor` to potentially speed up duration calculation by processing folders in parallel.
*   **Duplicate File Detection (Script 2):** Identifies video files with identical content using MD5 hashing, regardless of filename or location within the scanned directory.
*   **Console Output (Script 2):** Prints folder durations, total duration, and lists of duplicate files directly to the terminal.
*   **Supported Formats:** Primarily targets `.mp4` and `.mov` files.

## How it Works

**1. `totalcourseduartionlocal_gen4.py` (Duration Aggregation & Reporting)**

*   **Initialization:** Sets the target root folder (`ai_dubbing_folder`) and output filenames (`log_file`, `csv_file`). **Note:** These are currently hardcoded in the script.
*   **Parallel Scan:** Uses `os.walk` to find all subfolders and files. It submits tasks to a `ProcessPoolExecutor` (up to 11 workers) where each task calculates the total duration of video files directly within a specific folder using `moviepy`.
*   **Duration Aggregation:** After individual folder durations are calculated, it sorts folders by depth and iterates bottom-up, adding the duration of each subfolder to its parent folder's total.
*   **Formatting & Output:** Formats the calculated durations (in seconds) into a "HH hours MM minutes SS seconds" string.
*   **File Writing:** Writes the results, folder by folder (relative path), to the specified `.txt` log file and `.csv` file. It also logs the start/end time and total processing time to the `.txt` file.

**2. `deepseekaisashwenthdubbingcheck.py` (Duplicate Check & Console Report)**

*   **Initialization:** Sets the target root folder (`root_folder`). **Note:** This is currently hardcoded in the script.
*   **Sequential Scan:** Uses `os.walk` to traverse the directory tree sequentially.
*   **Hashing & Duration:** For each `.mp4` or `.mov` file found:
    *   Calculates the MD5 hash of the file's content (`calculate_file_hash`).
    *   Stores the file path associated with its hash in a dictionary (to group duplicates).
    *   Calculates the video duration using `moviepy`.
    *   Adds the duration to the total for the current folder and to the overall total.
*   **Console Output:**
    *   Prints any file hashes that are associated with more than one file path (duplicates).
    *   Prints the total duration calculated for each folder.
    *   Prints the grand total duration for all video files found.

## Prerequisites

*   **Python 3:** (e.g., Python 3.6 or newer recommended). Download from [python.org](https://www.python.org/).
*   **FFmpeg:** The `moviepy` library relies heavily on FFmpeg for reading video files. You **must** have FFmpeg installed and accessible in your system's PATH.
    *   Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
    *   Follow their instructions to install it and add it to your system's PATH. Test by opening a terminal/command prompt and typing `ffmpeg -version`.

## Installation

It's highly recommended to use a Python virtual environment.

1.  **Clone or Download:**
    *   Get the `totalcourseduartionlocal_gen4.py` and `deepseekaisashwenthdubbingcheck.py` script files.

2.  **Navigate to Directory:**
    Open your terminal or command prompt and change to the directory where you saved the scripts:
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
    You need `moviepy`. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    moviepy>=1.0.3
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: `moviepy` will install its own dependencies like `numpy`, `decorator`, `tqdm`, etc.)*

## How to Run the Scripts

**IMPORTANT:** Both scripts currently have the target folder path hardcoded inside them. You **must** edit the scripts to point to your desired video folder before running.

1.  **Edit the Scripts:**
    *   Open `totalcourseduartionlocal_gen4.py` and change the line `ai_dubbing_folder = r"D:\IIT\ai dubbing"` to your target folder path. You might also want to change `log_file` and `csv_file` names.
    *   Open `deepseekaisashwenthdubbingcheck.py` and change the line `root_folder = r"D:\IIT\ai dubbing"` to your target folder path.

2.  **Activate Virtual Environment:** Ensure your virtual environment is active (see Step 4 in Installation).

3.  **Run Script 1 (Duration Report):**
    ```bash
    python totalcourseduartionlocal_gen4.py
    ```
    *   Check the output files (`Ashwanth_videooneai_duration_log.txt` and `Ashwantrh_videooneai_duration.csv` by default, unless changed) in the script's directory for results.

4.  **Run Script 2 (Duplicate Check):**
    ```bash
    python deepseekaisashwenthdubbingcheck.py
    ```
    *   Check the console output for duplicate file lists and folder/total durations.

## Making it Simpler to Run

Since these are command-line tools, the main simplification involves avoiding the need to edit the script each time you want to analyze a different folder.

**Method 1: Use Command-Line Arguments (Recommended Improvement)**

Modify the scripts to accept the target folder path as a command-line argument using Python's `argparse` module.

*   **Example modification for `totalcourseduartionlocal_gen4.py`:**
    ```python
    import argparse
    # ... (other imports)

    if __name__ == "__main__":
        parser = argparse.ArgumentParser(description="Calculate video durations in folders.")
        parser.add_argument("folder_path", help="Path to the root folder to scan.")
        parser.add_argument("-l", "--logfile", default="duration_log.txt", help="Output log file name.")
        parser.add_argument("-c", "--csvfile", default="duration_report.csv", help="Output CSV file name.")
        args = parser.parse_args()

        ai_dubbing_folder = args.folder_path
        log_file = args.logfile
        csv_file = args.csvfile

        traverse_folder(ai_dubbing_folder, log_file, csv_file)
        print(f"Processing complete. Check '{log_file}' and '{csv_file}'.")
    ```
    You would then run it like:
    ```bash
    python totalcourseduartionlocal_gen4.py "C:\path\to\your\videos" --logfile my_log.txt --csvfile my_report.csv
    ```
    *(A similar modification can be done for `deepseekaisashwenthdubbingcheck.py`)*

**Method 2: Simple Runner Scripts (`.bat`, `.sh`)**

You can create simple batch or shell scripts if you frequently analyze the same folder, or if you modify the scripts to take arguments as above.

*   **Windows (`run_duration_report.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    python totalcourseduartionlocal_gen4.py "C:\path\to\your\videos"  REM Replace with path or %1 if using args
    deactivate
    pause
    ```

*   **macOS/Linux (`run_duration_report.sh`):**
    ```bash
    #!/bin/bash
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"

    source ./venv/bin/activate
    python totalcourseduartionlocal_gen4.py "/path/to/your/videos" # Replace with path or $1 if using args
    deactivate
    ```
    Make it executable: `chmod +x run_duration_report.sh`

**Method 3: Add to PATH (Less Common for Specific Analysis)**

You could add the directory containing your scripts (and potentially the modified versions using `argparse`) to your system's PATH environment variable. This allows running them from any directory, but is usually more suited for general-purpose tools.

## Output Explanation

*   **`totalcourseduartionlocal_gen4.py`:**
    *   `_duration_log.txt`: A text file listing each subfolder (relative path) and its aggregated video duration in "HH hours MM minutes SS seconds" format. Includes start/end timestamps and total execution time.
    *   `_duration.csv`: A CSV file with two columns: "Course Name" (relative folder path) and "Duration" (formatted time string).
*   **`deepseekaisashwenthdubbingcheck.py`:**
    *   **Console Output:**
        *   Lists of duplicate files, grouped by content hash.
        *   Duration in seconds for each folder containing videos.
        *   The total duration in seconds for all videos found.

## Notes & Caveats

*   **Performance:** Video duration calculation can be I/O intensive and CPU-bound. Processing large collections of videos can take significant time, even with parallel processing (Script 1).
*   **FFmpeg Dependency:** Ensure FFmpeg is correctly installed and in your PATH. `moviepy` might fail or be unable to read certain files without it.
*   **Hardcoded Paths:** The current versions require manual editing of the source code to change the target folder. Modifying them to use command-line arguments (`argparse`) is highly recommended for better usability.
*   **Error Handling:** The `get_video_duration` functions include basic error handling, returning 0 duration for problematic files. Check logs or console output for potential errors during processing.
*   **Hashing (Script 2):** MD5 is used for duplicate checking. While generally good for detecting identical files, it's theoretically possible (though extremely unlikely for video files) for different files to have the same hash (collision). It's very reliable for finding exact copies.