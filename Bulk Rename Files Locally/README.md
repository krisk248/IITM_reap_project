# MP4 File Renamer GUI

A graphical application built with Python and PyQt5 to easily batch rename `.mp4` video files within a selected folder and its subfolders.

## Description

This tool provides a user-friendly interface to select a directory containing `.mp4` files. It loads these files, sorts them naturally (e.g., "Episode 2" before "Episode 10"), and displays them in a table. Users can then type the desired new names into the table, and the tool will rename the files accordingly. It also logs the renaming operations for reference.

## Features

*   **Graphical User Interface (GUI):** Easy-to-use interface built with PyQt5.
*   **Folder Selection:** Browse and select the target folder containing video files.
*   **Recursive File Discovery:** Finds `.mp4` files within the selected folder and all its subfolders.
*   **Natural Sorting:** Lists files in a human-friendly order (e.g., `file1.mp4`, `file2.mp4`, `file10.mp4`).
*   **Interactive Renaming Table:** Displays original filenames and provides input fields for new names.
*   **Automatic Extension Handling:** Adds the `.mp4` extension automatically if omitted in the new name.
*   **Detailed Logging:** Records all rename operations (successes and failures) to a `rename.log` file in the script's directory.
*   **CSV Summary Log:** Creates a `rename_log.csv` file in the *selected folder* summarizing the old and new names for easy tracking.
*   **Error Handling:** Reports errors encountered during the renaming process.

## How it Works

1.  **Folder Selection:** The user clicks "Browse" to select the main folder containing the `.mp4` files they want to rename.
2.  **Load Files:** The user clicks "Load Files".
3.  **File Scanning:** The script walks through the selected folder and all its subdirectories, identifying all files ending with `.mp4` (case-insensitive).
4.  **Sorting:** The found files are sorted using a "natural sort" algorithm, ensuring that numerical parts are treated correctly (e.g., "Video 2" comes before "Video 10").
5.  **Table Population:** The sorted file list is displayed in a two-column table:
    *   Column 1 ("Video Title"): Shows the original filename (read-only).
    *   Column 2 ("Rename To"): Contains an empty text input field for each file.
6.  **User Input:** The user types the desired new filename (without the extension, though adding it works too) into the corresponding "Rename To" field for each file they wish to rename. Files with empty "Rename To" fields will be skipped.
7.  **Rename Execution:** The user clicks the "Rename" button.
8.  **Processing:** The script iterates through each row in the table:
    *   It reads the text entered in the "Rename To" field.
    *   If the field is empty, it skips the file.
    *   It ensures the new name ends with `.mp4`.
    *   It attempts to rename the original file (`os.rename`) to the new name *within its original directory*.
    *   If successful, it updates the filename displayed in Column 1 of the table and logs the change.
    *   If an error occurs (e.g., invalid characters, file permissions, name collision), it logs the error.
9.  **Logging:**
    *   Every significant action (folder selection, files loaded, successful rename, error) is logged with a timestamp to `rename.log` in the directory where the script is run.
    *   A summary CSV file (`rename_log.csv`) is created *inside the folder the user selected in step 1*. This CSV contains the original name and the corresponding new name (or error message) for each file processed.
10. **Completion:** A message box informs the user whether the process completed successfully or if errors occurred.

## Prerequisites

*   **Python 3:** (e.g., Python 3.6 or newer recommended). You can download Python from [python.org](https://www.python.org/).

## Installation

It's highly recommended to use a Python virtual environment to manage dependencies.

1.  **Clone or Download:**
    *   If you use Git: `git clone <repository_url>` (Replace `<repository_url>` with the actual URL if hosted)
    *   Or, download the `filerenamer.py` script file directly.

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
    You need `PyQt5` for the GUI. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    PyQt5>=5.14
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run the Application

1.  **Ensure Prerequisites:** Make sure Python 3 is installed.
2.  **Activate Virtual Environment:** If you closed your terminal, navigate back to the script directory and activate the virtual environment again (see Step 4 in Installation).
3.  **Run the Script:**
    ```bash
    python filerenamer.py
    ```
    (Use `python3` if needed on your system)

4.  **Use the GUI:**
    *   Click "Browse" to select the folder containing your `.mp4` files.
    *   Click "Load Files" to populate the table.
    *   Type the desired new names in the "Rename To" column for the files you want to change.
    *   Click "Rename".
    *   Check the confirmation message and the log files (`rename.log` in the script directory, `rename_log.csv` in the folder you selected) for details.

## Making it Simpler to Run

Since this is a GUI application, creating shortcuts is often the most convenient way to launch it without opening a terminal each time.

**Method 1: Desktop Shortcut (Recommended for GUI Apps)**

*   **Windows:**
    1.  Right-click on your desktop or in a folder.
    2.  Select "New" -> "Shortcut".
    3.  For the location, browse to your Python executable *within the virtual environment* (e.g., `path\to\your\script\directory\venv\Scripts\pythonw.exe` - use `pythonw.exe` to avoid a background console window).
    4.  Append the full path to your script (`filerenamer.py`) after the executable path, separated by a space.
    5.  Click "Next", give the shortcut a name (e.g., "MP4 Renamer"), and click "Finish".
    6.  *(Alternative)*: Create a `.bat` file (see Method 2) and point the shortcut to the `.bat` file instead.

*   **macOS:**
    1.  You can create an AppleScript or Automator application to launch the script.
    2.  A simpler way: Open `Script Editor`, paste `do shell script "cd /path/to/your/script/directory && ./venv/bin/python filerenamer.py"`, save it as an Application.

*   **Linux (Desktop Environments like GNOME, KDE, XFCE):**
    1.  Create a `.desktop` file (e.g., `mp4-renamer.desktop`) in `~/.local/share/applications/` or `/usr/share/applications/`.
    2.  The content should look something like this (adjust paths):
        ```ini
        [Desktop Entry]
        Version=1.0
        Name=MP4 File Renamer GUI
        Comment=Batch rename MP4 files
        Exec=/path/to/your/script/directory/venv/bin/python /path/to/your/script/directory/filerenamer.py
        Icon=video-x-generic  # Or specify a custom icon path
        Terminal=false
        Type=Application
        Categories=Utility;AudioVideo;
        ```
    3.  Make the `.desktop` file executable: `chmod +x ~/.local/share/applications/mp4-renamer.desktop`. It should then appear in your application menu.

**Method 2: Simple Runner Script (Cross-Platform)**

Create a small script to activate the environment and run the Python script.

*   **Windows (`run_renamer.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    pythonw.exe filerenamer.py
    deactivate
    ```
    Save this as `run_renamer.bat` in the same directory. Double-click this batch file to run the app. You can create a shortcut to this batch file.

*   **macOS/Linux (`run_renamer.sh`):**
    ```bash
    #!/bin/bash
    # Get the directory where the script resides
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"

    # Activate venv and run python script
    source ./venv/bin/activate
    python filerenamer.py
    deactivate
    ```
    Save as `run_renamer.sh`, make it executable (`chmod +x run_renamer.sh`), and run it with `./run_renamer.sh`. You can create launchers pointing to this shell script.

**Method 3: Bundling (Advanced)**

For creating a standalone executable that doesn't require users to install Python or dependencies, you can use tools like **PyInstaller**:

1.  `pip install pyinstaller` (in your activated venv).
2.  Run PyInstaller: `pyinstaller --onefile --windowed filerenamer.py` (adjust options as needed).
3.  This creates a `dist` folder containing a single executable file. This provides the easiest experience for end-users but is more complex to set up initially.

## Notes

*   The script renames files **in place** within their original directories. Make sure you have backups if you are unsure about the renaming process.
*   The `rename.log` file is stored in the same directory as the `filerenamer.py` script.
*   The `rename_log.csv` file is created inside the **folder you selected** for processing.
*   The script may fail to rename a file if the new name already exists in the same directory or if there are permission issues. Check the logs for details if errors occur.