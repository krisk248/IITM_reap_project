# YouTube Bulk Uploader GUI

A desktop application built with Python and PyQt5 designed to automate the process of uploading videos from a local folder to a specified YouTube playlist, with features for authentication, validation, resume capability, and email notification.

---

**<span style="color:red; font-weight:bold;">🚨🚨🚨 CRITICAL WARNING: YOUTUBE UPLOAD LIMITS & PERFORMANCE 🚨🚨🚨</span>**

> **Please read this section carefully before using this tool extensively:**
>
> 1.  **Unofficial Daily Upload Limit (API):** While the YouTube Data API has a *quota point* system (this script estimates ~1650 points per video), there's a widely observed **practical limit of around 50-100 videos** that can be uploaded *via the API* within a 24-hour period per channel. **Exceeding this limit frequently results in YouTube temporarily blocking API uploads (often with a `quotaExceeded` error, even if points remain) for your channel for approximately 24 hours.** This script includes a basic quota check, but it's based on points and may not prevent hitting the *video count* block. **Do not rely on this tool to upload hundreds of videos in a single day.**
>
> 2.  **Chunked Upload Performance:** This script uses resumable uploads with 8MB chunks (`chunksize=8*1024*1024`). While this adds reliability, uploading many small chunks can sometimes be **slower** than uploading directly through the YouTube web interface, especially for users with very high upload bandwidth.
>
> 3.  **Manual Upload Recommendation:** For uploading a large number of videos *quickly*, the standard YouTube web uploader is generally **much more efficient and has significantly higher daily limits** (often allowing hundreds of videos per day, depending on channel history and standing).
>
> **Use this automated tool primarily when:**
>
> *   You need to perform uploads unattended over several days due to the API limits.
> *   You need the specific validation or organizational features it provides.
> *   You have other tasks to perform and cannot manually manage uploads.
>
> **It is STRONGLY recommended to use the manual YouTube web uploader if your goal is simply to upload a large batch of videos (e.g., 60+) within a single day.** Misuse of the API via aggressive uploading can lead to temporary blocks.

---

## Description

This application provides a graphical interface to manage the bulk uploading of videos structured according to a specific naming convention (Course Introduction, Chapters) from a local folder to a YouTube channel. It handles authentication, playlist selection, video validation, uploading, adding videos to playlists, and provides basic controls like pause, resume, and cancel. It also includes optional email notifications and the ability to delete videos uploaded during the current session.

## Features

*   **Graphical User Interface (GUI):** Built with PyQt5 for ease of use.
*   **OAuth 2.0 Authentication:** Securely connects to YouTube using Google's OAuth flow. Supports loading existing tokens.
*   **Playlist Selection:** Loads and allows selection from the user's YouTube playlists.
*   **Folder Structure Validation:** Checks the selected video folder for adherence to a specific naming convention:
    *   Requires one file containing "Course Introduction".
    *   Expects video files named like `Chapter N - Topic Name.ext` (Main Chapter).
    *   Expects supplemental files named like `Chapter NA - Topic Name.ext` (Supplemental Part).
    *   Logs errors to `error.txt` if validation fails.
*   **Natural Sorting:** Uploads videos based on natural sort order of filenames.
*   **Automated Uploading:** Uploads validated video files sequentially.
*   **Metadata Generation:** Automatically generates video title and description based on the filename (splitting at " - ").
*   **Add to Playlist:** Automatically adds successfully uploaded videos to the selected YouTube playlist.
*   **Resumable Uploads:** Uses chunked uploads via `MediaFileUpload`.
*   **Resume Capability:** Saves progress (index of the next video) to `resume_state.txt` allowing uploads to be resumed later. Supports manual resume index input.
*   **Upload Controls:** Start, Pause/Resume, and Cancel ongoing upload processes.
*   **Session Deletion:** Option to delete videos *uploaded during the current active session* (requires confirmation).
*   **Email Notification:** Sends a summary email upon completion or via a button press (requires configuring SMTP details in the script).
*   **Logging:** Provides real-time feedback in the GUI log area and saves a detailed log to `upload_log.txt` within a course-specific folder.
*   **Basic Quota Awareness:** Attempts to stop uploads if the estimated quota cost exceeds a predefined limit (Note: See warning above about practical limits).

## How it Works

1.  **Configuration:** User enters Course Name, browses for Client Secret JSON, browses for the Video Folder, optionally loads a Token JSON, and optionally enters a Resume State index.
2.  **Authentication:** User clicks "Authenticate". If no valid token is loaded/found, the OAuth 2.0 flow is initiated via the browser. Successful credentials are saved to a `token.json` file (named based on client secret or loaded file, stored under `courses/<CourseName>/`).
3.  **Load Playlists:** User clicks "Load Playlists". The application uses the authenticated credentials to fetch the user's playlists and populates the dropdown. It stores playlist IDs and generates target folder names under `playlists/`.
4.  **Select Playlist:** User selects the target playlist from the dropdown.
5.  **Start Upload:** User clicks "Start Upload".
    *   Input fields are validated.
    *   Configuration details are gathered.
    *   An `UploadWorker` thread is started.
    *   **Validation:** The worker first calls `validate_course_structure`. If errors are found, `error.txt` is created, and the upload aborts.
    *   **Resume State:** The worker checks for `resume_state.txt` in the associated `playlists/<PlaylistName>` folder or uses the user-provided index.
    *   **Upload Loop:** The worker iterates through the sorted list of valid video files starting from the resume index.
        *   Checks the `running` and `paused` flags for user control.
        *   Checks estimated quota cost against the limit.
        *   Constructs video title and description from the filename.
        *   Uses `youtube.videos().insert` with `MediaFileUpload` to upload the video in chunks. Progress is logged.
        *   On successful upload, uses `youtube.playlistItems().insert` to add the video to the selected playlist.
        *   Updates `resume_state.txt` with the index of the *next* video.
        *   Updates the GUI progress bar.
    *   **Completion:** When the loop finishes (or is stopped), the worker signals completion. If all videos were uploaded, it attempts to open the playlist URL in the browser.
6.  **Controls:**
    *   **Pause/Resume:** Toggles the `paused` flag in the worker thread.
    *   **Cancel:** Sets the `running` flag to `False` in the worker thread, causing the loop to terminate.
7.  **Delete Upload:** If clicked after an upload session, confirms with the user, then starts a `DeleteWorker` thread to delete videos whose IDs were stored during *that specific upload session*.
8.  **Send Email:** Gathers configuration and upload count, then attempts to send an email using the hardcoded SMTP settings.

## Prerequisites

*   **Python 3:** (e.g., Python 3.7 or newer recommended). Download from [python.org](https://www.python.org/).
*   **Google Cloud Project:** You need a project set up in the [Google Cloud Console](https://console.cloud.google.com/).
*   **YouTube Data API v3 Enabled:** Within your Google Cloud Project, you must enable the "YouTube Data API v3".
*   **OAuth 2.0 Credentials:** You need to create OAuth 2.0 credentials (type "Desktop app") for your project in the Google Cloud Console and download the `client_secret.json` file.
*   **Email Account (for Notifications):** An email account (like Gmail) configured for SMTP access if you want to use the email notification feature. You'll need to enable "Less secure app access" or ideally use an "App Password" if using Gmail with 2FA.

## Setup: Getting `client_secret.json`

(Follow these steps carefully - this is essential)

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project or select an existing one.
3.  In the sidebar navigation, go to "APIs & Services" -> "Library".
4.  Search for "YouTube Data API v3" and click "Enable".
5.  Go to "APIs & Services" -> "Credentials".
6.  Click "+ CREATE CREDENTIALS" and select "OAuth client ID".
7.  If prompted, configure the "OAuth consent screen". Choose "External" (unless you are a Google Workspace user), provide an app name (e.g., "Bulk Uploader"), user support email, and developer contact information. Click "Save and Continue" through the scopes and test users sections (you might need to add your email as a test user later if the app stays in "Testing" mode).
8.  For "Application type", select "Desktop app".
9.  Give it a name (e.g., "Bulk Uploader Desktop Client").
10. Click "Create".
11. A window will pop up showing your Client ID and Client Secret. Click "**DOWNLOAD JSON**".
12. Save this downloaded file. You will need to browse to this file using the application. Keep this file secure!

## Installation

It's highly recommended to use a Python virtual environment.

1.  **Clone or Download:**
    *   Get the `youtube_gen5.py` script file.

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
    google-auth-httplib2>=0.1
    google-auth>=2.0
    ```

    Then run:
    ```bash
    pip install -r requirements.txt
    ```

6.  **(Optional) Configure Email:** Edit the `youtube_gen5.py` script and update the `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, and `RECIPIENT_EMAIL` constants with your actual email sending details.

## How to Run the Application

1.  **Ensure Prerequisites & Setup:** Make sure Python 3 is installed, you have your `client_secret.json`, and you have optionally configured email settings in the script.
2.  **Activate Virtual Environment:** If you closed your terminal, navigate back to the script directory and activate the virtual environment again (see Step 4 in Installation).
3.  **Run the Script:**
    ```bash
    python youtube_gen5.py
    ```
    (Use `python3` if needed on your system).

4.  **Use the GUI:**
    *   The application window will appear.
    *   Enter a **Course Name** (used for creating log/token folders).
    *   Click "Browse Client Secret" and select your `.json` file.
    *   Click "Authenticate". Follow the browser prompts to log in and grant permissions. A token file (e.g., `client_secret_token.json`) will be created automatically.
    *   *(Optional)* Click "Load Token" to use a previously generated token file.
    *   Click "Load Playlists" to populate the playlist dropdown.
    *   Select the desired **Playlist** from the dropdown.
    *   Click "Browse Video Folder" and select the local folder containing your structured video files.
    *   *(Optional)* Enter a number in "Resume State" to start uploading from that video index (0 is the first video). If left blank, it will try to read `resume_state.txt`.
    *   Click "Start Upload".
    *   Monitor the progress bar and log area. Use Pause/Resume/Cancel as needed.
    *   *(Optional)* Use "Delete Upload" to remove videos uploaded *in this specific run*.
    *   *(Optional)* Use "Send Email" to send a notification.

## Making it Simpler to Run

Creating desktop shortcuts is the standard way for GUI apps:

*   **Windows:** Create a shortcut pointing to `pythonw.exe` in your `venv\Scripts` folder, adding the full path to `youtube_gen5.py` as an argument.
*   **macOS:** Use `Script Editor` to create an AppleScript wrapper that navigates to the directory, activates the venv, and runs the script. Save as an Application.
*   **Linux:** Create a `.desktop` file in `~/.local/share/applications/` pointing to the python executable in your venv and the script path.

## Output Explanation

*   **`courses/<CourseName>/`:** A folder created for each course name entered.
    *   **`token.json` (or similar):** Stores OAuth 2.0 credentials after successful authentication.
    *   **`upload_log.txt`:** Detailed log file for the upload session related to this course.
*   **`playlists/<PlaylistName>/`:** A folder created for each selected playlist.
    *   **`resume_state.txt`:** Stores the index (0-based) of the *next* video to be uploaded for this playlist, allowing resumption.
*   **`<VideoFolder>/error.txt`:** Created *only* if the `validate_course_structure` check fails, listing the specific filename or structure errors found.
*   **GUI Log Area:** Displays real-time status messages and logs during operation.

## Notes & Caveats

*   **UPLOAD LIMITS:** Re-read the critical warning at the top. Do not expect to upload hundreds of videos per day with this tool.
*   **Hardcoded Values:** SMTP details and quota estimations (`MAX_DAILY_QUOTA`, `COST_PER_VIDEO`) are hardcoded. For flexibility, consider moving these to a configuration file or environment variables.
*   **Filename Validation:** The script strictly enforces the `Course Introduction`, `Chapter N - ...`, `Chapter NA - ...` naming convention. Files not matching this will cause validation errors or be ignored. Ensure your files are named correctly *before* starting.
*   **Error Handling:** Basic error handling is present, but API issues, network problems, or unexpected file issues can still occur. Check the log files for details.
*   **Deletion Scope:** The "Delete Upload" button *only* affects videos uploaded successfully *during the current run* where the button is pressed. It does not delete previously uploaded videos or videos from other sessions.
*   **Security:** Keep your `client_secret.json` and generated `token.json` files secure. The SMTP password is also stored directly in the script - consider more secure methods like environment variables or dedicated credential management if deploying widely.
*   **API Costs:** Remember that uploading videos consumes significant API quota points.