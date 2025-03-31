# YouTube Channel Manager GUI

A multi-tab desktop application built with Python and PyQt5 to help manage YouTube channel content, focusing on video renaming, consistency checking between local files and online playlists, and generating detailed Excel reports.

![Screenshot (Add a screenshot of your app here if possible)]() <!-- Optional: Add a link to a screenshot -->

## Description

This tool provides a graphical interface to interact with the YouTube Data API v3 for several channel management tasks:

1.  **Authentication:** Securely connect to your YouTube account using OAuth 2.0.
2.  **Renaming:** Load videos from a specific playlist, automatically generate new titles and descriptions based on a "Chapter N / NA" naming convention, allow review and editing, and apply the changes directly to your YouTube videos.
3.  **Checking:** Compare a list of local video filenames (without extensions) against the video titles in a selected YouTube playlist to identify discrepancies in count or naming, useful for verifying uploads or local backups.
4.  **Generate Excel:** Select one or more playlists and generate detailed `.xlsx` files containing structured information about each video (Course Code, Chapter Name, YouTube URL, Title, Description, Order No, Language Code), sorted according to specific rules.

**🚨🚨🚨 WARNING: IRREVERSIBLE CHANGES 🚨🚨🚨**

The **Renaming** tab modifies your live YouTube video metadata (titles and descriptions).

*   **THESE CHANGES ARE PERMANENT ON YOUTUBE.** Once applied, they cannot be automatically undone by this tool.
*   **REVIEW CAREFULLY:** Always meticulously review the "Proposed New Title" and "Proposed New Description" columns in the Renaming tab before clicking the "Apply Renaming" button.
*   **BACKUP (Optional):** Consider backing up important metadata if needed before making large-scale changes.
*   **SENSITIVE SCOPE:** This application requires the `youtube.force-ssl` scope, granting broad permissions to manage your YouTube account. Only grant this permission if you understand the risks.

## Features

*   **Multi-Tab GUI:** Organizes functionality into Authentication, Renaming, Checking, and Generate Excel tabs using PyQt5.
*   **Secure Authentication:** Uses Google OAuth 2.0 flow with `client_secret.json` and manages `token.json` for persistent login. Supports optional Developer API Key input.
*   **Playlist Loading:** Fetches user's playlists with details (title, description, video count) across multiple tabs. Handles pagination for accounts with many playlists.
*   **Video Renaming:**
    *   Loads videos from a selected playlist.
    *   Applies a specific renaming scheme based on titles like "Course Introduction", "Chapter N - Topic", "Chapter NA - Topic".
    *   Generates proposed new descriptions based on the topic part of the title.
    *   Displays original title, proposed title, and proposed description in an editable table.
    *   Applies changes directly to YouTube videos using `videos().update`.
    *   Includes progress bar and detailed logging within the tab.
    *   Sorts videos "naturally" based on chapter numbers before display/processing.
*   **Consistency Checking:**
    *   Loads filenames (without extensions) from a user-selected local folder.
    *   Loads video titles from a selected YouTube playlist.
    *   Sorts both lists using the same natural sort key.
    *   Displays lists side-by-side for comparison.
    *   Performs checks for item count mismatch, duplicate titles in the playlist, and line-by-line differences.
    *   Reports findings in a dedicated log area within the tab.
*   **Excel Report Generation:**
    *   Allows selecting multiple playlists via checkboxes.
    *   For each selected playlist:
        *   Fetches all video details.
        *   Sorts videos using a detailed custom key prioritizing Introduction, Chapter Headers, and Chapter Parts.
        *   Parses playlist title for `CourseCode` and `LanguageCode` (expects `PL_CourseCode_LangCode` format).
        *   Determines `Chapter Name` and `OrderNo in Chapter` based on video title patterns.
        *   Generates an Excel (`.xlsx`) file using `pandas`.
        *   Excel columns: `CourseCode`, `Chapter Name`, `Youtubeurl`, `Video Title`, `Video Description`, `OrderNo in Chapter`, `Language code`.
        *   Saves Excel files to a dated subfolder (e.g., `DD_MM_YY_Excel`) in the script's directory.
        *   Includes progress bar and detailed logging.
*   **Logging:** Logs actions and errors to `youtube_manager.log` file, the console, and dedicated log windows within relevant tabs.
*   **Helper Functions:** Includes logic for filename sanitization and natural/custom sorting.

## How it Works

1.  **Authentication Tab:**
    *   User provides optional Developer API Key.
    *   User selects their `client_secret.json` file (obtained from Google Cloud Console).
    *   User can optionally specify a location for the `token.json` file (defaults to `token.json` in script directory).
    *   Clicking "Authenticate" triggers the OAuth 2.0 flow (if needed) or refreshes the token. Credentials are stored in `token.json`. The `youtube` service object is created.
2.  **Renaming Tab:**
    *   User clicks "Load My Playlists" to populate the dropdown.
    *   User selects a playlist and clicks "Load Videos & Show Rename Scheme".
    *   Playlist items are fetched, sorted naturally (`extract_chapter_sort_key`), and processed.
    *   The script attempts to parse titles ("Chapter N...", "Chapter NA...", "Course Introduction...").
    *   A proposed new title (standardized format) and description (usually the topic part) are generated.
    *   The table is populated: Col 1 (Original Title, read-only, stores video ID), Col 2 (Proposed Title, editable), Col 3 (Proposed Description, editable).
    *   User reviews and potentially edits Col 2 and Col 3.
    *   User clicks "Apply Renaming".
    *   The script iterates through the table rows. For each row:
        *   It fetches the current video snippet using `videos().list`.
        *   It compares current title/description with the table's proposed values.
        *   If changes are needed, it constructs an update request body (including required fields like `categoryId` from the original snippet).
        *   It executes the `videos().update` API call.
        *   Progress and logs are updated.
3.  **Checking Tab:**
    *   User clicks "Browse Folder" to select a local directory.
    *   User clicks "Load Folder Names". The script lists video files, extracts basenames, sorts them (`extract_chapter_sort_key`), and populates Column 2 of the table.
    *   User clicks "Load My Playlists" to populate the dropdown.
    *   User selects a playlist and clicks "Load Playlist Video Names". Playlist video titles are fetched, sorted (`extract_chapter_sort_key`), and populate Column 3 of the table.
    *   User clicks "Compare...". The script compares the counts of items in Col 2 vs Col 3, checks for duplicates in Col 3, and compares Col 2 and Col 3 line by line. Results are shown in the log window.
4.  **Generate Excel Tab:**
    *   User clicks "Load My Playlists". Playlists are loaded into a table with checkboxes.
    *   User checks the boxes for desired playlists.
    *   User clicks "Generate Excel File(s)".
    *   For each selected playlist:
        *   Playlist title is parsed for CourseCode/LangCode (expects `PL_CourseCode_LangCode`).
        *   All video items are fetched.
        *   Videos are sorted using the detailed `video_sort_key`.
        *   The script iterates through sorted videos, determining `Chapter Name` and `OrderNo in Chapter` based on title patterns (Introduction, Header, Part).
        *   Data is collected into a list of dictionaries.
        *   A `pandas` DataFrame is created from the collected data.
        *   The DataFrame is saved to an `.xlsx` file (named `description_playlistname.xlsx`) in a dated output folder (`DD_MM_YY_Excel`) using the `openpyxl` engine.
        *   Progress and logs are updated.

## Prerequisites

*   **Python 3:** (e.g., Python 3.7 or newer recommended). Download from [python.org](https://www.python.org/).
*   **Google Cloud Project:** You need a project set up in the [Google Cloud Console](https://console.cloud.google.com/).
*   **YouTube Data API v3 Enabled:** Within your Google Cloud Project, you must enable the "YouTube Data API v3".
*   **OAuth 2.0 Credentials:** You need to create OAuth 2.0 credentials (type "Desktop app") for your project in the Google Cloud Console and download the `client_secret.json` file.

## Setup: Getting `client_secret.json`

(Follow these steps carefully - this is essential)

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select an existing one.
3.  In the sidebar navigation, go to "APIs & Services" -> "Library".
4.  Search for "YouTube Data API v3" and click "Enable".
5.  Go to "APIs & Services" -> "Credentials".
6.  Click "+ CREATE CREDENTIALS" and select "OAuth client ID".
7.  If prompted, configure the "OAuth consent screen". Choose "External" (unless you are a Google Workspace user), provide an app name (e.g., "YouTube Manager"), user support email, and developer contact information. Click "Save and Continue" through the scopes and test users sections (you might need to add your email as a test user later if the app stays in "Testing" mode).
8.  For "Application type", select "Desktop app".
9.  Give it a name (e.g., "YouTube Manager Desktop Client").
10. Click "Create".
11. A window will pop up showing your Client ID and Client Secret. Click "**DOWNLOAD JSON**".
12. Save this downloaded file. You will need to browse to this file using the "Browse Client Secret (OAuth)" button in the application's Authentication tab. Keep this file secure!

## Installation

It's highly recommended to use a Python virtual environment.

1.  **Clone or Download:**
    *   Get the `gemini_maneger_v1.py` script file.

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
    You need `PyQt5`, the Google API Client libraries, `pandas` for Excel generation, and `openpyxl` as the engine for pandas. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    PyQt5>=5.14
    google-api-python-client>=2.0
    google-auth-oauthlib>=0.5
    google-auth-httplib2>=0.1 # Often needed by google-auth-oauthlib
    google-auth>=2.0
    pandas>=1.3
    openpyxl>=3.0
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run the Application

1.  **Ensure Prerequisites:** Make sure Python 3 is installed and you have obtained your `client_secret.json` file.
2.  **Activate Virtual Environment:** If you closed your terminal, navigate back to the script directory and activate the virtual environment again (see Step 4 in Installation).
3.  **Run the Script:**
    ```bash
    python gemini_maneger_v1.py
    ```
    (Use `python3` if needed on your system).

4.  **Use the GUI:**
    *   The application window will appear with multiple tabs.
    *   **Go to the "Authentication" tab first.**
        *   Optionally enter your Developer API Key.
        *   Click "Browse Client Secret (OAuth)" and select your downloaded `.json` file.
        *   Optionally change the location for `token.json`.
        *   Click "Authenticate / Re-Authenticate". Follow the browser prompts to log in and grant permissions if this is the first time or the token has expired.
    *   **Navigate to other tabs ("Renaming", "Checking", "Generate Excel")** and use the buttons as described in the "How it Works" section. Always load playlists/files before attempting actions like renaming, comparing, or generating Excels.
    *   **Monitor the log windows** within each tab and the `youtube_manager.log` file for progress and errors.

## Making it Simpler to Run

Since this is a GUI application, creating shortcuts is often the most convenient way to launch it.

**Method 1: Desktop Shortcut (Recommended)**

*   **Windows:**
    1.  Right-click -> "New" -> "Shortcut".
    2.  Location: Browse to `pythonw.exe` inside your virtual environment (`path\to\venv\Scripts\pythonw.exe`). Use `pythonw.exe` to avoid a console window.
    3.  Append the full path to the script (`gemini_maneger_v1.py`) after the executable path, using quotes if necessary.
    4.  Click "Next", name the shortcut (e.g., "YouTube Manager"), and "Finish".

*   **macOS:**
    1.  Use `Script Editor` to create an AppleScript: `do shell script "cd '/path/to/your/script/directory' && ./venv/bin/python 'gemini_maneger_v1.py'"`. Save as an Application.

*   **Linux (Desktop Environments):**
    1.  Create a `.desktop` file (e.g., `youtube-manager.desktop`) in `~/.local/share/applications/`.
    2.  Content (adjust paths):
        ```ini
        [Desktop Entry]
        Version=1.0
        Name=YouTube Channel Manager
        Comment=Manage YouTube videos (Rename, Check, Excel)
        Exec=/path/to/venv/bin/python '/path/to/script/gemini_maneger_v1.py'
        Icon=youtube # Or specify a custom icon path
        Terminal=false
        Type=Application
        Categories=Utility;Network;AudioVideo;
        ```
    3.  Make executable: `chmod +x ~/.local/share/applications/youtube-manager.desktop`.

**Method 2: Simple Runner Script (.bat / .sh)**

*   **Windows (`run_manager.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    pythonw.exe gemini_maneger_v1.py
    deactivate
    ```

*   **macOS/Linux (`run_manager.sh`):**
    ```bash
    #!/bin/bash
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"
    source ./venv/bin/activate
    python gemini_maneger_v1.py
    deactivate
    ```
    Save, make executable (`chmod +x run_manager.sh`), and run (`./run_manager.sh`).

## Output Explanation

*   **`token.json`:** Stores OAuth 2.0 credentials after successful authentication (located as specified in Auth tab, defaults to script directory).
*   **`youtube_manager.log`:** File containing detailed logs of operations, errors, and timestamps (located in the script directory).
*   **Excel Files (`.xlsx`):** Generated by the "Generate Excel" tab. Saved inside a dated subfolder (e.g., `DD_MM_YY_Excel`) within the script's directory. Filename format: `Playlist description_Playlist name.xlsx`. Columns include CourseCode, Chapter Name, Youtubeurl, Video Title, Video Description, OrderNo in Chapter, Language code.
*   **In-App Log Windows:** Each operational tab (Renaming, Checking, Generate Excel) has its own text area displaying relevant status updates and logs for the current operation.

## Notes & Caveats

*   **IRREVERSIBLE RENAMING:** Use the Renaming tab with extreme caution. Changes are permanent on YouTube.
*   **API Quota:** Extensive use (renaming many videos, generating many Excels) consumes YouTube Data API quota. Check your usage in the Google Cloud Console if you encounter quota errors (often `HttpError 403`).
*   **Scope Permissions:** The `youtube.force-ssl` scope is powerful. Understand what permissions you are granting.
*   **Sorting & Parsing Logic:** The Renaming, Checking, and Excel Generation features rely on specific video/playlist title patterns ("Chapter N", "Chapter NA", "Course Introduction", `PL_CourseCode_LangCode`). Videos/playlists not matching these patterns may not be sorted, processed, or have data extracted as expected. Check logs for warnings.
*   **Error Handling:** While the script includes error handling for common API errors and file operations, unexpected issues can occur. Check the log file and console output for detailed error messages.
*   **Dependencies:** Ensure all required Python packages (`PyQt5`, Google libs, `pandas`, `openpyxl`) are installed in your virtual environment.
*   **`client_secret.json` Security:** Keep your downloaded client secret file confidential. Do not share it or commit it to public repositories.