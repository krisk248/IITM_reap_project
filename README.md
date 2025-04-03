# Media and YouTube Management Utilities

A collection of Python scripts providing Graphical User Interfaces (GUIs) and command-line tools for various media file management and YouTube channel tasks, including adding background music, batch renaming, duration calculation, duplicate checking, video conversion, playlist/video deletion, YouTube video metadata editing, consistency checking, Excel report generation, and bulk uploading.

---

**<span style="color:red; font-weight:bold;">🚨🚨🚨 IMPORTANT WARNINGS 🚨🚨🚨</span>**

> **Several scripts in this collection interact with the YouTube API and can perform actions that are PERMANENT and IRREVERSIBLE, such as deleting videos/playlists or modifying video metadata.**
>
> *   **`playlistdel_version 1.py`:** Deletes **BOTH** selected playlists **AND** all videos within them. **VIDEO DELETION IS PERMANENT.** Use with extreme caution and only if you are certain you want to delete the content forever. Backup videos first if they are important.
> *   **`gemini_maneger_v1.py` (Renaming Tab):** Modifies live YouTube video titles and descriptions. **Changes are PERMANENT.** Review proposed changes very carefully before applying.
> *   **`youtube_gen5.py` (Bulk Uploader):** Subject to **YouTube API practical daily upload limits (often ~50-100 videos/day)**, which are stricter than quota points indicate. Exceeding this can lead to **temporary 24-hour API upload blocks**. For large batch uploads (100+ videos), the standard YouTube web interface is usually much faster and has higher limits. Use the API uploader strategically.
> *   **API Scopes:** Scripts interacting with YouTube require broad permissions (`youtube.force-ssl`). Understand the permissions you are granting when authenticating.
> *   **Credentials Security:** Keep your `client_secret.json` and generated `token.json` files secure. Do not commit them to public repositories.

---

## Table of Contents

*   [Overall Description](#media-and-youtube-management-utilities)
*   [General Prerequisites](#general-prerequisites)
*   [General Installation](#general-installation)
*   [Consolidated Dependencies (`requirements.txt`)](#consolidated-dependencies-requirementstxt)
*   [Scripts Overview](#scripts-overview)
    *   [Script: `addbgmguiwin.py` - BGM Adder GUI](#script-addbgmguiwinpy---bgm-adder-gui)
    *   [Script: `filerenamer.py` - MP4 File Renamer GUI](#script-filerenamerpy---mp4-file-renamer-gui)
    *   [Script: `totalcourseduartionlocal_gen4.py` - Folder Duration Calculator](#script-totalcourseduartionlocal_gen4py---folder-duration-calculator)
    *   [Script: `deepseekaisashwenthdubbingcheck.py` - Duplicate Video Checker](#script-deepseekaisashwenthdubbingcheckpy---duplicate-video-checker)
    *   [Script: `conversiongui_gen1.py` - Video Converter GUI](#script-conversionguigen1py---video-converter-gui)
    *   [Script: `playlistdel_version 1.py` - YouTube Playlist & Video Deleter GUI](#script-playlistdel_version-1py---youtube-playlist--video-deleter-gui)
    *   [Script: `gemini_maneger_v1.py` - YouTube Channel Manager GUI](#script-gemini_maneger_v1py---youtube-channel-manager-gui)
    *   [Script: `youtube_gen5.py` - YouTube Bulk Uploader GUI](#script-youtube_gen5py---youtube-bulk-uploader-gui)
*   [General Notes and Caveats](#general-notes-and-caveats)

## General Prerequisites

Ensure you have the following installed on your system before proceeding:

1.  **Python 3:** (e.g., Python 3.7 or newer recommended). Download from [python.org](https://www.python.org/). Make sure Python is added to your system's PATH during installation.
2.  **FFmpeg & FFprobe:** Required by several scripts (`addbgmguiwin`, `totalcourseduartionlocal_gen4`, `deepseekaisashwenthdubbingcheck`, `conversiongui_gen1`). These tools must be installed and accessible via your system's PATH.
    *   Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
    *   Follow their installation instructions.
    *   Test installation by opening a terminal/command prompt and running `ffmpeg -version` and `ffprobe -version`.
3.  **(For YouTube Scripts) Google Cloud Project & OAuth Credentials:** Scripts interacting with YouTube (`playlistdel`, `gemini_maneger`, `youtube_gen5`) require:
    *   A Google Cloud Project.
    *   The "YouTube Data API v3" enabled within that project.
    *   OAuth 2.0 Credentials (Type: "Desktop app") downloaded as a `client_secret.json` file. *(See individual script sections or setup guides in previous responses for detailed steps)*.
4.  **(Optional) NVIDIA GPU & Drivers:** Required only if you intend to use the CUDA acceleration features in `addbgmguiwin.py` or `conversiongui_gen1.py`.
5.  **(Optional) SMTP Access:** Required only for the email notification feature in `youtube_gen5.py`. Needs configuration within the script.

## General Installation

It is **highly recommended** to use a Python virtual environment to manage dependencies for these scripts.

1.  **Clone or Download:** Obtain all the Python script files (`.py`) and place them in a single project directory.
2.  **Navigate to Directory:** Open your terminal or command prompt and change to the project directory:
    ```bash
    cd path/to/your/project/directory
    ```
3.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    ```
    (Use `python3` if `python` points to an older version on your system).
4.  **Activate the Virtual Environment:**
    *   **Windows:** `.\venv\Scripts\activate`
    *   **macOS/Linux:** `source venv/bin/activate`
    *(You should see `(venv)` prefixed to your terminal prompt)*.
5.  **Install Dependencies:** Create a file named `requirements.txt` in your project directory with the content listed below (see [Consolidated Dependencies](#consolidated-dependencies-requirementstxt)). Then run:
    ```bash
    pip install -r requirements.txt
    ```
    This will install PyQt5, Google API libraries, pandas, moviepy, requests, etc.

## Consolidated Dependencies (`requirements.txt`)

Create a file named `requirements.txt` in your project directory with the following content:

```txt
PyQt5>=5.14
requests>=2.20
moviepy>=1.0.3
google-api-python-client>=2.0
google-auth-oauthlib>=0.5
google-auth-httplib2>=0.1
google-auth>=2.0
pandas>=1.3
openpyxl>=3.0
imageio-ffmpeg>=0.4.5 # Recommended, used explicitly or by moviepy

```

Scripts Overview
----------------

### Script: addbgmguiwin.py - BGM Adder GUI

*   **Description:** A simple GUI to add background music (BGM) to single video files or all videos within a folder using FFmpeg.
    
*   **Features:** Single file/folder mode, BGM file selection, volume adjustment, output folder selection, optional CUDA acceleration, ntfy.sh notifications, progress logging, cancellation.
    
*   **Prerequisites:** Python, FFmpeg. Optional: NVIDIA GPU/Drivers for CUDA.
    
*   **How to Run:** python addbgmguiwin.py (after installation and activating venv). Use the GUI.
    
*   **Outputs:** Creates new .mp4 files with added BGM in the specified output folder (preserves structure for folder mode).
    
*   **Simplifying:** Use desktop shortcuts pointing to pythonw.exe (Windows) or runner scripts (.bat/.sh) as detailed in its individual README.
    

### Script: filerenamer.py - MP4 File Renamer GUI

*   **Description:** A GUI tool to batch rename .mp4 files within a folder and its subfolders interactively.
    
*   **Features:** Folder selection, recursive discovery, natural sorting, interactive table for new names, automatic .mp4 extension handling, logging to file (rename.log) and CSV (rename\_log.csv in target folder).
    
*   **Prerequisites:** Python.
    
*   **How to Run:** python filerenamer.py (after installation and activating venv). Use the GUI.
    
*   **Outputs:** Renames files _in place_. Creates rename.log (script dir) and rename\_log.csv (target folder).
    
*   **Simplifying:** Use desktop shortcuts pointing to pythonw.exe (Windows) or runner scripts (.bat/.sh).
    

### Script: totalcourseduartionlocal\_gen4.py - Folder Duration Calculator

*   **Description:** A command-line script to calculate the total duration of videos (.mp4, .mov) within each subfolder recursively, aggregating durations to parent folders.
    
*   **Features:** Recursive scanning, duration calculation via moviepy, parallel processing, outputs formatted results to .txt and .csv files.
    
*   **Prerequisites:** Python, FFmpeg (required by moviepy).
    
*   **How to Run:**
    
    1.  **Edit the script:** Change the hardcoded ai\_dubbing\_folder, log\_file, and csv\_file variables inside the script.
        
    2.  Run: python totalcourseduartionlocal\_gen4.py (after installation and activating venv)._(Recommended modification: Use argparse to pass the folder path as a command-line argument instead of hardcoding)._
        
*   **Outputs:** Creates specified .txt log file and .csv report file in the script's directory.
    

### Script: deepseekaisashwenthdubbingcheck.py - Duplicate Video Checker

*   **Description:** A command-line script to scan folders for videos, calculate duration per folder and total duration, and identify duplicate video files based on content hash (MD5).
    
*   **Features:** Recursive scanning, MD5 hash calculation, duplicate detection, duration calculation via moviepy, prints results to the console.
    
*   **Prerequisites:** Python, FFmpeg (required by moviepy).
    
*   **How to Run:**
    
    1.  **Edit the script:** Change the hardcoded root\_folder variable inside the script.
        
    2.  Run: python deepseekaisashwenthdubbingcheck.py (after installation and activating venv)._(Recommended modification: Use argparse to pass the folder path as a command-line argument)._
        
*   **Outputs:** Prints duplicate file lists and duration summaries directly to the console.
    

### Script: conversiongui\_gen1.py - Video Converter GUI

*   **Description:** A GUI to convert video files (single or folder batch) to 720p H.264 MP4 format using FFmpeg.
    
*   **Features:** File/Folder mode, output selection, standardized 720p MP4 output, optional CUDA acceleration, separate duration checking function (outputs video\_durations.txt), real-time progress bar, background processing, abort/cancel, logging, optional ntfy.sh notification.
    
*   **Prerequisites:** Python, FFmpeg, FFprobe. Optional: NVIDIA GPU/Drivers for CUDA.
    
*   **How to Run:** python conversiongui\_gen1.py (after installation and activating venv). Use the GUI.
    
*   **Outputs:** Creates converted .mp4 files in the output folder. Optionally creates video\_durations.txt. Creates .log files on FFmpeg errors.
    
*   **Simplifying:** Use desktop shortcuts pointing to pythonw.exe (Windows) or runner scripts (.bat/.sh).
    

### Script: playlistdel\_version 1.py - YouTube Playlist & Video Deleter GUI

> **🚨🚨🚨 EXTREME WARNING: IRREVERSIBLE VIDEO & PLAYLIST DELETION 🚨🚨🚨**
> 
> *   This tool **PERMANENTLY DELETES** both the selected YouTube playlists **AND ALL VIDEOS** they contain.
>     
> *   There is **NO UNDO**. Use only if absolutely certain. **BACKUP VIDEOS FIRST.**
>     
> *   Requires the sensitive youtube.force-ssl scope. Grant permission cautiously.
>     

*   **Description:** A GUI to select and **permanently delete** YouTube playlists and **all videos within them**.
    
*   **Features:** Secure OAuth 2.0 authentication, lists playlists with video counts, allows multiple selections via checkboxes, deletes videos first then the playlist, cancellation attempt, status updates, logs deleted playlist IDs to deletion\_log.txt.
    
*   **Prerequisites:** Python, Google Cloud Project with YouTube API v3 enabled, OAuth 2.0 Desktop Credentials (client\_secret.json).
    
*   **How to Run:** python "playlistdel\_version 1.py" (after installation and activating venv). Requires selecting client\_secret.json on first run or when token expires. Use the GUI **with extreme care.**
    
*   **Outputs:** Deletes content on YouTube. Creates/appends to deletion\_log.txt in the script directory. Generates token.json.
    
*   **Caveat:** Does not handle pagination for >50 playlists or >50 videos per playlist without modification.
    

### Script: gemini\_maneger\_v1.py - YouTube Channel Manager GUI

> **⚠️ WARNING: MODIFIES YOUTUBE DATA ⚠️**
> 
> *   The **Renaming tab** modifies live YouTube video titles and descriptions. These changes are **PERMANENT**. Review proposed changes carefully before applying.
>     

*   **Description:** A multi-tab GUI for various YouTube management tasks: renaming videos based on patterns, checking consistency between local files and playlists, and generating detailed Excel reports.
    
*   **Features:** Multi-tab interface (Auth, Renaming, Checking, Excel Gen), OAuth 2.0 Auth, video renaming based on "Chapter N/NA" patterns with preview/edit table, local vs. playlist name comparison (counts, duplicates, line-by-line), multi-playlist Excel report generation (sorted videos, parsed metadata, specific columns), logging.
    
*   **Prerequisites:** Python, Google Cloud Project with YouTube API v3 enabled, OAuth 2.0 Desktop Credentials (client\_secret.json).
    
*   **How to Run:** python gemini\_maneger\_v1.py (after installation and activating venv). Authenticate first, then use the desired tabs.
    
*   **Outputs:** Modifies YouTube data (Renaming tab). Creates youtube\_manager.log and token.json. Creates .xlsx files in a dated subfolder (DD\_MM\_YY\_Excel) within the script directory (Excel Gen tab).
    
*   **Simplifying:** Use desktop shortcuts pointing to pythonw.exe (Windows) or runner scripts (.bat/.sh).
    

### Script: youtube\_gen5.py - YouTube Bulk Uploader GUI

> **🚨🚨🚨 CRITICAL WARNING: YOUTUBE UPLOAD LIMITS & PERFORMANCE 🚨🚨🚨**
> 
> *   Subject to **practical API daily upload limits (often ~50-100 videos/day)**, stricter than quota points suggest. Exceeding this can cause **24-hour upload blocks**.
>     
> *   Chunked uploads might be slower than the web interface for high bandwidth connections.
>     
> *   **Use the standard YouTube web uploader for large batches (>60) in a single day.** Use this tool strategically for automation or over multiple days.
>     

*   **Description:** A GUI to automate uploading videos from a local folder (with specific naming structure) to a YouTube playlist.
    
*   **Features:** OAuth 2.0 Auth, playlist selection, local file structure validation (Course Intro, Chapter N, Chapter NA), natural sort upload order, automatic title/description generation, adds to selected playlist, resume capability (resume\_state.txt), pause/resume/cancel controls, optional session deletion, optional email notification (requires SMTP config), logging (upload\_log.txt), basic quota check.
    
*   **Prerequisites:** Python, Google Cloud Project with YouTube API v3 enabled, OAuth 2.0 Desktop Credentials (client\_secret.json). Optional: SMTP access for email.
    
*   **How to Run:** python youtube\_gen5.py (after installation and activating venv). Configure inputs, authenticate, select playlist, select folder, then start upload.
    
*   **Outputs:** Uploads videos to YouTube. Creates folders (courses/, playlists/) for logs, tokens, and resume state. Optionally creates error.txt in the video folder if validation fails.
    
*   **Simplifying:** Use desktop shortcuts pointing to pythonw.exe (Windows) or runner scripts (.bat/.sh).

### Application: app.py - Course Language & Student Tracking Dashboard (Streamlit)

*   **Description:** A web-based dashboard (built with Streamlit) that visualizes data from a public Google Sheet to track student assignments to courses, required vs. assigned dubbing languages, student status, and identify unassigned students suitable for missing language slots.
    
*   **Features:**
    
    *   Reads data directly from a public Google Sheet URL.
        
    *   Cleans and processes student and course data.
        
    *   Multi-tab Interface:
        
        *   **Unassigned:** Shows courses, missing required languages, and lists available unassigned students matching the language and course gender requirements.
            
        *   **Assigned:** Displays students assigned to each course, their languages, and status (color-coded).
            
        *   **Progress:** Provides charts and tables showing course completion percentage (based on languages covered), gender demographics, and student status breakdowns (Completed, In Progress, To be Updated). Includes an overall language completion pie chart.
            
        *   **Language Wise Unassigned:** Lists all unassigned students grouped by their target dubbing language, including contact info (phone number) and row number from the source sheet.
            
    *   Interactive charts using Altair.
        
*   **Prerequisites:** Python, Internet Access. Requires streamlit, altair, pandas Python packages.
    
*   **How to Access/Run:**
    
    *   **Online (Hosted):** Access the live dashboard directly at: [https://reap2025-dubbingtracking.hf.space](https://www.google.com/url?sa=E&q=https://reap2025-dubbingtracking.hf.space)
        
    *   **Locally:**
        
        1.  Ensure prerequisites and dependencies (including streamlit, altair) are installed in your virtual environment (see [General Installation](https://www.google.com/url?sa=E&q=#general-installation)).
            
        2.  Navigate to the project directory in your terminal.
            
        3.  Run: streamlit run app.py
            
        4.  Streamlit will provide a local URL (usually http://localhost:8501) to open in your web browser.
            
*   **Outputs:** An interactive web application displayed in your browser (either hosted online or locally). Does not create local files, but reads data from the specified Google Sheet.
    
*   **Caveats:** Functionality depends entirely on the continued public availability and consistent structure of the linked Google Sheet.
    

General Notes and Caveats
-------------------------

*   **API Usage & Quotas:** Be mindful of YouTube Data API quotas, especially when running scripts that interact heavily with the API (renaming, deleting, uploading). Check your quota usage in the Google Cloud Console. Practical limits (like video upload count per day) may be stricter than point quotas.
    
*   **Error Handling:** While the scripts include error handling, network issues, API changes, permission problems, or unexpected file/data formats can cause errors. Check the console output and log files (.log, .txt) generated by the scripts for details. For the Streamlit app, check the terminal where streamlit run was executed or the app's error messages.
    
*   **File Overwriting:** Some scripts might overwrite output files (like logs, CSVs, or converted videos using -y in FFmpeg) without warning. Be careful about where you direct outputs.
    
*   **Security:** Your client\_secret.json file and the generated token.json files contain sensitive credentials. Keep them secure and do not share them or commit them to public version control. If using email features, consider secure ways to handle passwords instead of hardcoding them directly in the script (e.g., environment variables, dedicated credential managers).
    
*   **Backups:** Before running scripts that modify or delete data (local files or YouTube content), ensure you have adequate backups.
    
*   **Dependencies:** Make sure all prerequisites and Python packages listed in requirements.txt are correctly installed within your activated virtual environment.
    
*   **Data Source Reliability (Streamlit App):** The app.py dashboard depends on the specific Google Sheet URL being accessible and maintaining its expected column structure. Changes to the sheet may break the dashboard.
