# YouTube Playlist Deleter GUI

A desktop application built with Python and PyQt5 that allows users to select and delete YouTube playlists, including **permanently deleting all videos** contained within those selected playlists, using the YouTube Data API v3.

**🚨🚨🚨 EXTREME WARNING: IRREVERSIBLE VIDEO DELETION 🚨🚨🚨**

This tool provides functionality to delete entire YouTube playlists. **Crucially, it also iterates through each selected playlist and permanently deletes every single video within it.**

*   **VIDEO DELETION IS PERMANENT.** Once a video is deleted using this tool, it cannot be recovered through YouTube.
*   **PLAYLIST DELETION IS PERMANENT.**
*   **USE WITH EXTREME CAUTION.** There is no 'undo' feature. Double-check every playlist you select before clicking the "Delete Selected" button.
*   **BACKUP YOUR VIDEOS:** If the videos in your playlists are important, ensure you have backups stored elsewhere *before* using this tool.
*   **HIGHLY SENSITIVE SCOPE:** This application requires the `youtube.force-ssl` scope, which grants broad permissions to manage your YouTube account, including deleting videos and playlists. Only grant this permission if you fully understand the risks.

## Features

*   **Graphical User Interface (GUI):** Easy-to-use interface built with PyQt5.
*   **OAuth 2.0 Authentication:** Securely authenticates with your YouTube account using Google's OAuth flow. Requires a `client_secret.json` file.
*   **Playlist Listing:** Fetches and displays your YouTube playlists (title, description).
*   **Video Count Display:** Shows the number of videos potentially targeted for deletion for selected playlists.
*   **Selective Deletion:** Allows selecting multiple playlists via checkboxes.
*   **Video & Playlist Deletion:** Deletes all videos within the selected playlists *first*, then deletes the playlist itself.
*   **Cancellation:** Provides a button to attempt cancellation during the deletion process.
*   **Status Updates:** Displays the number of selected playlists and the total number of videos to be deleted. Shows progress during deletion.
*   **Deletion Logging:** Records deleted playlist IDs and timestamps to `deletion_log.txt`.

## How it Works

1.  **Client Secret Selection:** The user clicks "Select Client Secret JSON" and chooses the `client_secret.json` file downloaded from Google Cloud Console.
2.  **Authentication:**
    *   The script checks for an existing `token.json` file containing valid credentials.
    *   If no valid token exists, it initiates the Google OAuth 2.0 flow:
        *   Opens a browser window/tab asking the user to log in to their Google account and grant permission for the application to manage their YouTube account (using the `youtube.force-ssl` scope).
        *   After authorization, Google redirects back, and the script obtains access credentials.
        *   These credentials are saved to `token.json` for future use, avoiding repeated logins.
    *   A `youtube` service object is built using the authenticated credentials.
3.  **Load Playlists:** The script calls the YouTube Data API v3 (`playlists.list` endpoint with `mine=True`) to fetch the user's playlists, including snippet (title, description) and content details (video count).
4.  **Populate Table:** The fetched playlists are displayed in a table. Each row shows the title, description, and a checkbox for selection. The video count is associated with the checkbox.
5.  **User Selection:** The user checks the boxes next to the playlists they wish to delete. The status label updates to show the count of selected playlists and the total number of videos within them.
6.  **Initiate Deletion:** The user clicks the "Delete Selected" button.
7.  **Deletion Process:**
    *   The script iterates through the table rows.
    *   For each **checked** playlist:
        *   It retrieves the Playlist ID.
        *   It calls the YouTube API (`playlistItems.list`) to get a list of all video items within that playlist.
        *   It then iterates through **each video item**:
            *   Extracts the Video ID.
            *   Calls the YouTube API (`videos.delete`) to **permanently delete the video** from YouTube.
        *   After attempting to delete all videos in the playlist, it calls the YouTube API (`playlists.delete`) to **delete the playlist itself**.
        *   It logs the playlist deletion to `deletion_log.txt`.
        *   The GUI status label is updated during this process.
        *   The script checks a `cancelled` flag periodically. If the "Cancel Deletion" button was pressed, it stops processing further playlists/videos.
8.  **Completion/Cancellation:** A message box notifies the user upon completion or cancellation.

## Prerequisites

*   **Python 3:** (e.g., Python 3.6 or newer recommended). Download from [python.org](https://www.python.org/).
*   **Google Cloud Project:** You need a project set up in the [Google Cloud Console](https://console.cloud.google.com/).
*   **YouTube Data API v3 Enabled:** Within your Google Cloud Project, you must enable the "YouTube Data API v3".
*   **OAuth 2.0 Credentials:** You need to create OAuth 2.0 credentials (type "Desktop app") for your project in the Google Cloud Console and download the `client_secret.json` file.

## Setup: Getting `client_secret.json`

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select an existing one.
3.  In the sidebar navigation, go to "APIs & Services" -> "Library".
4.  Search for "YouTube Data API v3" and click "Enable".
5.  Go to "APIs & Services" -> "Credentials".
6.  Click "+ CREATE CREDENTIALS" and select "OAuth client ID".
7.  If prompted, configure the "OAuth consent screen". Choose "External" (unless you are a Google Workspace user), provide an app name (e.g., "Playlist Deleter"), user support email, and developer contact information. Click "Save and Continue" through the scopes and test users sections for now (you might need to add your email as a test user later if the app stays in "Testing" mode).
8.  For "Application type", select "Desktop app".
9.  Give it a name (e.g., "Playlist Deleter Desktop Client").
10. Click "Create".
11. A window will pop up showing your Client ID and Client Secret. Click "**DOWNLOAD JSON**".
12. Save this downloaded file. **Rename it to `client_secret.json`** or be prepared to select the downloaded file name in the application. Keep this file secure!

## Installation

It's highly recommended to use a Python virtual environment.

1.  **Clone or Download:**
    *   Get the `playlistdel_version 1.py` script file.

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
    You need `PyQt5` and the Google API Client libraries. Create a file named `requirements.txt` in the same directory with the following content:

    ```txt
    PyQt5>=5.14
    google-api-python-client>=2.0
    google-auth-oauthlib>=0.5
    google-auth>=2.0
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
    python "playlistdel_version 1.py"
    ```
    (Use `python3` if needed on your system. Quote the filename if it contains spaces).

4.  **Use the GUI:**
    *   The application window will appear.
    *   Click "Select Client Secret JSON" and choose the `.json` file you downloaded during setup.
    *   If this is the first run or your `token.json` is invalid, a browser window will open asking you to log in and grant permission. Follow the prompts.
    *   Once authenticated, your playlists will load into the table.
    *   **CAREFULLY** check the boxes next to the playlists you want to delete (remembering this includes **deleting all their videos**).
    *   Monitor the status label for the number of videos targeted.
    *   When absolutely sure, click "Delete Selected".
    *   You can attempt to stop the process by clicking "Cancel Deletion".
    *   Check the `deletion_log.txt` file in the script's directory for a record of deleted playlists.

## Making it Simpler to Run

Since this is a GUI application, creating shortcuts is often the most convenient way to launch it.

**Method 1: Desktop Shortcut (Recommended)**

*   **Windows:**
    1.  Right-click -> "New" -> "Shortcut".
    2.  Location: Browse to `pythonw.exe` inside your virtual environment (`path\to\venv\Scripts\pythonw.exe`). Use `pythonw.exe` to avoid a console window.
    3.  Append the full path to the script (`playlistdel_version 1.py`) after the executable path, using quotes if necessary.
    4.  Click "Next", name the shortcut (e.g., "YouTube Deleter"), and "Finish".

*   **macOS:**
    1.  Use `Script Editor` to create an AppleScript: `do shell script "cd '/path/to/your/script/directory' && ./venv/bin/python 'playlistdel_version 1.py'"`. Save as an Application.

*   **Linux (Desktop Environments):**
    1.  Create a `.desktop` file (e.g., `youtube-deleter.desktop`) in `~/.local/share/applications/`.
    2.  Content (adjust paths):
        ```ini
        [Desktop Entry]
        Version=1.0
        Name=YouTube Playlist Deleter
        Comment=Delete YouTube playlists and videos
        Exec=/path/to/venv/bin/python '/path/to/script/playlistdel_version 1.py'
        Icon=youtube # Or specify a custom icon path
        Terminal=false
        Type=Application
        Categories=Utility;Network;
        ```
    3.  Make executable: `chmod +x ~/.local/share/applications/youtube-deleter.desktop`.

**Method 2: Simple Runner Script (.bat / .sh)**

*   **Windows (`run_deleter.bat`):**
    ```batch
    @echo off
    cd /d "%~dp0"
    call .\venv\Scripts\activate
    pythonw.exe "playlistdel_version 1.py"
    deactivate
    ```

*   **macOS/Linux (`run_deleter.sh`):**
    ```bash
    #!/bin/bash
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
    cd "$SCRIPT_DIR"
    source ./venv/bin/activate
    python "playlistdel_version 1.py"
    deactivate
    ```
    Save, make executable (`chmod +x run_deleter.sh`), and run (`./run_deleter.sh`).

## Notes & Caveats

*   **IRREVERSIBLE DELETION:** Cannot be stressed enough. Deleting videos via the API is permanent.
*   **API Quota:** Deleting playlists and especially many videos consumes YouTube Data API quota. If you have many videos/playlists to delete, you might hit daily limits. Check your quota usage in the Google Cloud Console.
*   **Scope:** The `youtube.force-ssl` scope is very permissive. Understand what you are authorizing.
*   **Pagination Limitation:** The script currently fetches only the first 50 playlists and the first 50 videos within each selected playlist (`maxResults=50`). If you have more than 50 playlists, or more than 50 videos in a playlist you want to delete, this script **will not delete all of them** without modifications to handle pagination.
*   **Error Handling:** Basic error handling is included (prints to console), but API errors or network issues might interrupt the process. Check the console output if issues occur.
*   **`token.json`:** This file stores your authentication credentials. Keep it secure if you are on a shared machine. Deleting it will force re-authentication.
*   **`deletion_log.txt`:** Provides a basic log of *successfully* deleted playlists. It does not log individual video deletions or errors comprehensively.