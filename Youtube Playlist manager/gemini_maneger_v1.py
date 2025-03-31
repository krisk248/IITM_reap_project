# --- START OF FILE youtuberename.py ---

import sys
import os
import re
import logging
import datetime
import pandas as pd  # Added for Excel generation
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QTextEdit, QProgressBar, QCheckBox, QHeaderView,
    QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt

# Google API imports – install these with pip if needed:
# pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 pandas openpyxl
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request # Added for refresh logic

# Define the YouTube API scope
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']

# --- Helper function to sanitize filenames ---
def sanitize_filename(name):
    """Removes characters that are invalid in Windows filenames."""
    # Remove invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Replace sequences of whitespace with a single underscore
    name = re.sub(r'\s+', '_', name)
    # Ensure it's not excessively long (Windows limit is often 260 chars for path)
    return name[:150] # Truncate to a reasonable length


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Channel Manager")
        self.setGeometry(100, 100, 1200, 800) # Increased height slightly
        self.youtube = None
        self.credentials = None
        self.api_key = "" # Developer key is often needed alongside OAuth for some read operations
        self.client_secret_file = ""
        self.token_file = "token.json"  # default token file

        # Dictionaries to store playlists for each tab
        self.rename_playlists = {}      # For renaming tab
        self.check_playlists = {}       # For checking tab
        self.excel_playlists_data = {}  # For Excel tab {row: {'id': ..., 'title': ..., 'description': ...}}

        # Storage for folder file names and playlist titles in checking tab
        self.folder_files = []
        self.playlist_titles = []

        # Setup logging to file
        log_format = '%(asctime)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            filename='youtube_manager.log', # Changed filename slightly
            level=logging.INFO,
            format=log_format
        )
        # Also log to console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(console_handler)


        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create four tabs
        self.auth_tab = QWidget()
        self.rename_tab = QWidget()
        self.check_tab = QWidget()
        self.excel_tab = QWidget() # New Excel Tab

        self.tabs.addTab(self.auth_tab, "Authentication")
        self.tabs.addTab(self.rename_tab, "Renaming")
        self.tabs.addTab(self.check_tab, "Checking")
        self.tabs.addTab(self.excel_tab, "Generate Excel") # Add new tab

        self.init_auth_tab()
        self.init_rename_tab()
        self.init_check_tab()
        self.init_excel_tab() # Initialize the new tab

    # ----------------------- Tab 1: Authentication -----------------------
    def init_auth_tab(self):
        layout = QVBoxLayout()
        auth_group_layout = QVBoxLayout() # Group related widgets

        # API key input
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("YouTube API Key (Developer Key):"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter your Developer API Key (optional for some operations, required for others)")
        api_key_layout.addWidget(self.api_key_input)
        auth_group_layout.addLayout(api_key_layout)

        # Client secret file selection
        client_secret_layout = QHBoxLayout()
        self.client_secret_label = QLabel("No client secret file selected.")
        client_secret_btn = QPushButton("Browse Client Secret (OAuth)")
        client_secret_btn.clicked.connect(self.browse_client_secret)
        client_secret_layout.addWidget(self.client_secret_label)
        client_secret_layout.addWidget(client_secret_btn)
        auth_group_layout.addLayout(client_secret_layout)

        # Token file selection (optional – the file is created after first authentication)
        token_layout = QHBoxLayout()
        self.token_label = QLabel(f"Token file (will be created/used): {self.token_file}")
        token_btn = QPushButton("Change Token File Location")
        token_btn.clicked.connect(self.browse_token_file)
        token_layout.addWidget(self.token_label)
        token_layout.addWidget(token_btn)
        auth_group_layout.addLayout(token_layout)

        # Authenticate button
        auth_btn = QPushButton("Authenticate / Re-Authenticate")
        auth_btn.clicked.connect(self.authenticate)
        auth_group_layout.addWidget(auth_btn)

        layout.addLayout(auth_group_layout)
        layout.addStretch() # Pushes content to the top

        self.auth_status_label = QLabel("Status: Not Authenticated")
        self.auth_status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.auth_status_label)

        self.auth_tab.setLayout(layout)

    def browse_client_secret(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Client Secret JSON", "", "JSON Files (*.json);;All Files (*)", options=options)
        if filename:
            self.client_secret_file = filename
            self.client_secret_label.setText(os.path.basename(filename))
            logging.info(f"Client secret file selected: {filename}")

    def browse_token_file(self):
        options = QFileDialog.Options()
        # Suggest saving if the file doesn't exist
        filename, _ = QFileDialog.getSaveFileName(
            self, "Select or Create Token JSON File", self.token_file, "JSON Files (*.json);;All Files (*)", options=options)
        if filename:
            self.token_file = filename
            self.token_label.setText(f"Token file: {os.path.basename(filename)}")
            logging.info(f"Token file location set to: {filename}")

    def authenticate(self):
        self.api_key = self.api_key_input.text().strip() # Get API key if provided
        creds = None
        try:
            # Check if token file exists
            if os.path.exists(self.token_file):
                logging.info(f"Attempting to load credentials from {self.token_file}")
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

            # If there are no (valid) credentials available, let the user log in.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logging.info("Credentials expired, attempting refresh.")
                    try:
                        creds.refresh(Request())
                        logging.info("Credentials refreshed successfully.")
                    except Exception as e:
                        logging.warning(f"Failed to refresh token: {e}. Need re-authentication.")
                        creds = None # Force re-authentication flow
                else:
                     # Run the OAuth 2.0 flow
                    if not self.client_secret_file:
                        QMessageBox.warning(self, "Authentication Required", "Client secret file not selected. Please browse to your client_secret.json file.")
                        logging.warning("Authentication attempted without client secret file.")
                        return
                    if not os.path.exists(self.client_secret_file):
                         QMessageBox.warning(self, "Authentication Error", f"Client secret file not found at: {self.client_secret_file}")
                         logging.error(f"Client secret file not found: {self.client_secret_file}")
                         return

                    logging.info("No valid credentials found or refresh failed. Starting OAuth flow.")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.client_secret_file, SCOPES)
                    # Make port=0 to find an available port automatically
                    creds = flow.run_local_server(port=0)
                    logging.info("OAuth flow completed. Credentials obtained.")

                # Save the credentials for the next run
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                logging.info(f"Credentials saved to {self.token_file}")

            self.credentials = creds
            # Build the YouTube service object
            # Pass developer key if available, otherwise only use credentials
            if self.api_key:
                 self.youtube = build('youtube', 'v3', credentials=self.credentials, developerKey=self.api_key)
                 logging.info("YouTube service built with credentials and developer key.")
            else:
                 self.youtube = build('youtube', 'v3', credentials=self.credentials)
                 logging.info("YouTube service built with credentials only.")

            self.auth_status_label.setText("Status: Authenticated Successfully!")
            self.auth_status_label.setStyleSheet("font-weight: bold; color: green;")
            QMessageBox.information(self, "Success", "Authentication successful!")

        except FileNotFoundError:
             QMessageBox.critical(self, "Error", f"Client secret file not found: {self.client_secret_file}")
             logging.exception("Client secret file not found during authentication.")
             self.auth_status_label.setText("Status: Authentication Failed (File Not Found)")
             self.auth_status_label.setStyleSheet("font-weight: bold; color: red;")
        except Exception as e:
            QMessageBox.critical(self, "Error", "Authentication failed: " + str(e))
            logging.exception("Authentication failed.")
            self.credentials = None
            self.youtube = None
            self.auth_status_label.setText(f"Status: Authentication Failed ({type(e).__name__})")
            self.auth_status_label.setStyleSheet("font-weight: bold; color: red;")

    def check_authentication(self):
        """Checks if authenticated and shows a warning if not."""
        if not self.youtube:
            QMessageBox.warning(self, "Authentication Required", "Please authenticate on the 'Authentication' tab first.")
            logging.warning("Action attempted without prior authentication.")
            return False
        return True

    # ----------------------- Tab 2: Renaming -----------------------
    def init_rename_tab(self):
        layout = QVBoxLayout()

        # Row for loading playlists
        playlist_layout = QHBoxLayout()
        self.load_rename_playlist_btn = QPushButton("Load My Playlists")
        self.load_rename_playlist_btn.clicked.connect(self.load_rename_playlist)
        self.rename_playlist_combo = QComboBox()
        playlist_layout.addWidget(self.load_rename_playlist_btn)
        playlist_layout.addWidget(self.rename_playlist_combo)
        layout.addLayout(playlist_layout)

        # Button to show the rename scheme in the table
        self.show_scheme_btn = QPushButton("Load Videos & Show Rename Scheme")
        self.show_scheme_btn.clicked.connect(self.show_rename_scheme)
        layout.addWidget(self.show_scheme_btn)

        # Table for showing video details
        self.rename_table = QTableWidget()
        self.rename_table.setColumnCount(3)
        self.rename_table.setHorizontalHeaderLabels(["Original YouTube Title", "Proposed New Title", "Proposed New Description"])
        self.rename_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch) # Stretch columns
        layout.addWidget(self.rename_table)

        # Progress and Log Area
        progress_log_layout = QHBoxLayout()
        self.rename_progress_bar = QProgressBar()
        progress_log_layout.addWidget(QLabel("Progress:"))
        progress_log_layout.addWidget(self.rename_progress_bar)
        layout.addLayout(progress_log_layout)

        self.rename_log_window = QTextEdit()
        self.rename_log_window.setReadOnly(True)
        self.rename_log_window.setFixedHeight(150) # Limit height
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.rename_log_window)

        # Rename button
        self.rename_btn = QPushButton("Apply Renaming to Selected Playlist Videos")
        self.rename_btn.clicked.connect(self.rename_videos)
        layout.addWidget(self.rename_btn)

        self.rename_tab.setLayout(layout)

    def load_rename_playlist(self):
        if not self.check_authentication(): return
        logging.info("Loading playlists for Renaming tab.")
        try:
            playlists = []
            nextPageToken = None
            while True:
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                playlists.extend(response.get("items", []))
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break

            self.rename_playlist_combo.clear()
            self.rename_playlists.clear()
            if playlists:
                for item in playlists:
                    playlist_id = item["id"]
                    title = item["snippet"]["title"]
                    description = item["snippet"].get("description", "No description")
                    video_count = item["contentDetails"]["itemCount"]
                    display_text = f"{title} ({video_count} videos) - {description[:50]}" # Shorten desc
                    self.rename_playlists[display_text] = playlist_id
                    self.rename_playlist_combo.addItem(display_text)
                logging.info(f"Loaded {len(playlists)} playlists into rename dropdown.")
                QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists. Select one and click 'Load Videos'.")
            else:
                 QMessageBox.information(self, "No Playlists", "No playlists found for your channel.")
                 logging.info("No playlists found for the user.")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlists: {e}")
            logging.exception("Failed to load playlists for rename tab.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            logging.exception("Unexpected error loading playlists for rename tab.")

    # Natural sort helper for renaming/checking tabs
    def extract_chapter_sort_key(self, title):
        if "Course Introduction" in title:
            return (-1, 0, "") # Introduction first

        # Match "Chapter N" or "Chapter NA"
        m = re.search(r'Chapter\s+(\d+)([A-Za-z]*)', title, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            suffix = m.group(2).upper() if m.group(2) else ""
            # Sort headers (no suffix) before parts (with suffix)
            suffix_sort_order = 0 if not suffix else 1
            return (num, suffix_sort_order, suffix)

        return (999, 0, title.lower()) # Fallback sorting

    def show_rename_scheme(self):
        if not self.check_authentication(): return
        selected_display_text = self.rename_playlist_combo.currentText()
        if not selected_display_text:
            QMessageBox.warning(self, "No Playlist Selected", "Please select a playlist from the dropdown first.")
            return

        playlist_id = self.rename_playlists.get(selected_display_text)
        if not playlist_id:
            QMessageBox.critical(self, "Error", "Could not find ID for the selected playlist.")
            logging.error(f"Could not find playlist ID for display text: {selected_display_text}")
            return

        logging.info(f"Loading videos for rename scheme for playlist ID: {playlist_id}")
        self.rename_log_window.clear()
        self.rename_log_window.append(f"Loading videos for playlist: {selected_display_text}...")
        QApplication.processEvents() # Update UI

        try:
            videos = []
            nextPageToken = None
            while True:
                request = self.youtube.playlistItems().list(
                    part="snippet,contentDetails", # contentDetails needed for videoId
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=nextPageToken
                )
                response = request.execute()
                videos.extend(response.get("items", []))
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break
            logging.info(f"Fetched {len(videos)} video items from playlist {playlist_id}.")

            # Sort videos using the natural sort key
            try:
                sorted_videos = sorted(videos, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                logging.info("Videos sorted naturally.")
            except Exception as e:
                 logging.exception("Error during video sorting. Using original order.")
                 QMessageBox.warning(self,"Sort Warning", f"Could not sort videos naturally, using API order. Error: {e}")
                 sorted_videos = videos # Fallback to original order

            # Populate the table
            self.rename_table.setRowCount(0) # Clear previous entries
            self.rename_table.setRowCount(len(sorted_videos)) # Set row count

            for row, video_item in enumerate(sorted_videos):
                snippet = video_item.get("snippet", {})
                contentDetails = video_item.get("contentDetails", {})
                video_id = contentDetails.get("videoId")
                original_title = snippet.get("title", " N/A ")

                if not video_id:
                    logging.warning(f"Skipping item at position {snippet.get('position', '?')} as videoId is missing.")
                    # Add a placeholder row indicating an issue
                    self.rename_table.setItem(row, 0, QTableWidgetItem(f"Error: Missing Video ID for item at pos {snippet.get('position', '?')}"))
                    self.rename_table.setItem(row, 1, QTableWidgetItem("N/A"))
                    self.rename_table.setItem(row, 2, QTableWidgetItem("N/A"))
                    continue

                # Generate the new title and description using regex
                new_title = original_title # Default
                new_desc = "" # Default to empty, will be topic or original title

                if "Course Introduction" in original_title:
                    # Keep original title, maybe set description based on title?
                    new_title = original_title
                    new_desc = original_title # Or some default description
                else:
                    # Match "Chapter N[A] - Topic" format
                    m = re.match(r'(Chapter\s+\d+[A-Za-z]?)\s*[-–—]?\s*(.*)', original_title, re.IGNORECASE)
                    if m:
                        chapter_part = m.group(1).strip()
                        topic = m.group(2).strip()
                        # Standardize the separator
                        new_title = f"{chapter_part} - {topic}"
                        new_desc = topic if topic else original_title # Use topic as desc, fallback to title
                    else:
                        # If no match, keep original title and maybe use it as description
                        new_title = original_title
                        new_desc = original_title

                # Populate table row
                title_item = QTableWidgetItem(original_title)
                title_item.setData(Qt.UserRole, video_id) # Store videoId with the original title item
                title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable) # Make original title read-only

                self.rename_table.setItem(row, 0, title_item)
                self.rename_table.setItem(row, 1, QTableWidgetItem(new_title)) # New title is editable
                self.rename_table.setItem(row, 2, QTableWidgetItem(new_desc)) # New desc is editable
                # self.rename_table.setRowHeight(row, 30) # Auto height usually better

            self.rename_table.resizeColumnsToContents()
            self.rename_table.resizeRowsToContents()
            self.rename_log_window.append(f"Loaded {self.rename_table.rowCount()} videos into the table. Review and edit proposed changes before applying.")
            logging.info("Rename scheme table populated.")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlist videos: {e}")
            self.rename_log_window.append(f"Error loading videos: {e}")
            logging.exception(f"Failed to load videos for playlist {playlist_id}.")
        except Exception as e:
             QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
             self.rename_log_window.append(f"Unexpected error: {e}")
             logging.exception("Unexpected error showing rename scheme.")

    def rename_videos(self):
        if not self.check_authentication(): return

        row_count = self.rename_table.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "No Videos", "No videos loaded in the table to rename.")
            return

        reply = QMessageBox.question(self, 'Confirm Rename',
                                     f"Are you sure you want to attempt renaming {row_count} videos based on the table contents?\n"
                                     "This action is irreversible on YouTube.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            logging.info("User cancelled renaming operation.")
            return

        logging.info(f"Starting renaming process for {row_count} videos.")
        self.rename_progress_bar.setMaximum(row_count)
        self.rename_progress_bar.setValue(0)
        self.rename_log_window.clear()
        self.rename_log_window.append("Starting video renaming...")
        QApplication.processEvents()

        success_count = 0
        fail_count = 0

        for row in range(row_count):
            try:
                original_title_item = self.rename_table.item(row, 0)
                new_title_item = self.rename_table.item(row, 1)
                new_desc_item = self.rename_table.item(row, 2)

                if not (original_title_item and new_title_item and new_desc_item):
                     logging.warning(f"Row {row+1}: Skipping due to missing table items.")
                     self.rename_log_window.append(f"Row {row+1}: Skipped (missing data in table).")
                     fail_count += 1
                     continue

                video_id = original_title_item.data(Qt.UserRole)
                original_title_text = original_title_item.text()
                new_title_text = new_title_item.text().strip()
                new_desc_text = new_desc_item.text().strip()

                if not video_id:
                    logging.warning(f"Row {row+1}: Skipping video '{original_title_text}' because video ID is missing.")
                    self.rename_log_window.append(f"Row {row+1}: Skipped '{original_title_text}' (Missing Video ID).")
                    fail_count += 1
                    continue

                if not new_title_text:
                    logging.warning(f"Row {row+1}: Skipping video '{original_title_text}' (ID: {video_id}) because new title is empty.")
                    self.rename_log_window.append(f"Row {row+1}: Skipped '{original_title_text}' (Empty New Title).")
                    fail_count += 1
                    continue

                self.rename_log_window.append(f"Processing Row {row+1}: '{original_title_text}' (ID: {video_id})")
                QApplication.processEvents()

                # 1. Get the current video snippet
                video_response = self.youtube.videos().list(
                    part="snippet", # Only need snippet to update
                    id=video_id
                ).execute()

                if not video_response.get("items"):
                    error_message = f"Failed Row {row+1}: Video {video_id} not found."
                    logging.error(error_message)
                    self.rename_log_window.append(error_message)
                    fail_count += 1
                    continue # Skip to next video

                current_snippet = video_response["items"][0]["snippet"]

                # 2. Check if changes are needed
                title_changed = current_snippet['title'] != new_title_text
                desc_changed = current_snippet.get('description', '') != new_desc_text

                if not title_changed and not desc_changed:
                    log_message = f"Skipped Row {row+1}: No changes needed for video {video_id} ('{new_title_text}')."
                    logging.info(log_message)
                    self.rename_log_window.append(log_message)
                    # Still count as success for progress bar as it was processed
                else:
                    # 3. Update the snippet with new values
                    snippet_to_update = {
                        "id": video_id,
                        "snippet": {
                            "title": new_title_text,
                            "description": new_desc_text,
                            # IMPORTANT: Must include categoryId and defaultLanguage from original snippet
                            # otherwise API may reject the update or reset them.
                            "categoryId": current_snippet.get("categoryId"),
                            # Also include tags if you want to preserve them
                            "tags": current_snippet.get("tags", []),
                            # Include defaultLanguage if present
                        }
                    }
                    # Add defaultLanguage only if it exists in the original snippet
                    if "defaultLanguage" in current_snippet:
                         snippet_to_update["snippet"]["defaultLanguage"] = current_snippet["defaultLanguage"]
                    if "defaultAudioLanguage" in current_snippet:
                        snippet_to_update["snippet"]["defaultAudioLanguage"] = current_snippet["defaultAudioLanguage"]


                    # 4. Execute the update request
                    update_request = self.youtube.videos().update(
                        part="snippet",
                        body=snippet_to_update
                    )
                    update_response = update_request.execute()

                    log_message = f"Success Row {row+1}: Updated video {video_id}: '{original_title_text}' --> '{new_title_text}'"
                    logging.info(log_message)
                    self.rename_log_window.append(log_message)

                success_count +=1 # Count success whether changed or not, as long as no error

            except HttpError as e:
                error_message = f"Failed Row {row+1}: Error updating video {video_id}: {e}"
                logging.exception(f"API Error updating video at row {row+1}")
                self.rename_log_window.append(f"<font color='red'>{error_message}</font>") # Show error in red
                fail_count += 1
            except Exception as e:
                 error_message = f"Failed Row {row+1}: Unexpected error for video {video_id}: {e}"
                 logging.exception(f"Unexpected Error updating video at row {row+1}")
                 self.rename_log_window.append(f"<font color='red'>{error_message}</font>")
                 fail_count += 1
            finally:
                self.rename_progress_bar.setValue(row + 1)
                QApplication.processEvents() # Keep UI responsive

        final_message = f"Renaming process completed. Success: {success_count}, Failed: {fail_count}."
        self.rename_log_window.append(f"\n<b>{final_message}</b>") # Bold summary
        logging.info(final_message)
        QMessageBox.information(self, "Renaming Done", final_message + "\nCheck log window for details.")


    # ----------------------- Tab 3: Checking -----------------------
    def init_check_tab(self):
        layout = QVBoxLayout()

        # --- Row 1: Folder Selection ---
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Folder:")
        self.selected_folder_path_label = QLabel("<i>No folder selected</i>")
        self.selected_folder_path_label.setWordWrap(True)
        browse_folder_btn = QPushButton("Browse Folder")
        browse_folder_btn.clicked.connect(self.browse_folder)
        self.load_folder_names_btn = QPushButton("Load Folder Names")
        self.load_folder_names_btn.clicked.connect(self.load_folder_names)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.selected_folder_path_label, 1) # Allow label to stretch
        folder_layout.addWidget(browse_folder_btn)
        folder_layout.addWidget(self.load_folder_names_btn)
        layout.addLayout(folder_layout)

        # --- Row 2: Playlist Selection ---
        playlist_layout = QHBoxLayout()
        self.load_check_playlist_btn = QPushButton("Load My Playlists")
        self.load_check_playlist_btn.clicked.connect(self.load_check_playlist)
        self.check_playlist_combo = QComboBox()
        self.show_playlist_names_btn = QPushButton("Load Playlist Video Names")
        self.show_playlist_names_btn.clicked.connect(self.show_check_playlist_names)
        playlist_layout.addWidget(self.load_check_playlist_btn)
        playlist_layout.addWidget(self.check_playlist_combo, 1) # Allow combo to stretch
        playlist_layout.addWidget(self.show_playlist_names_btn)
        layout.addLayout(playlist_layout)

        # --- Table for Comparison ---
        self.check_table = QTableWidget()
        self.check_table.setColumnCount(3)
        self.check_table.setHorizontalHeaderLabels(["#", "Folder Filename (No Ext.)", "YouTube Video Title"])
        self.check_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents) # Resize # column
        self.check_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.check_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.check_table)

        # --- Compare Button ---
        compare_btn = QPushButton("Compare Loaded Folder and Playlist Names")
        compare_btn.clicked.connect(self.compare_folder_playlist)
        layout.addWidget(compare_btn)

        # --- Log Area for Checking Tab ---
        self.check_log_window = QTextEdit()
        self.check_log_window.setReadOnly(True)
        self.check_log_window.setFixedHeight(100) # Smaller log area for this tab
        layout.addWidget(QLabel("Comparison Log:"))
        layout.addWidget(self.check_log_window)


        self.check_tab.setLayout(layout)
        self.folder_path = None # Initialize folder path


    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Video Files")
        if folder:
            self.folder_path = folder
            self.selected_folder_path_label.setText(folder)
            logging.info(f"Folder selected for checking: {folder}")
            # Clear folder files list and table column when new folder selected
            self.folder_files.clear()
            for i in range(self.check_table.rowCount()):
                 self.check_table.setItem(i, 1, QTableWidgetItem("")) # Clear folder column
        else:
             logging.info("Folder selection cancelled.")


    def load_folder_names(self):
        if not self.folder_path or not os.path.isdir(self.folder_path):
            QMessageBox.warning(self, "Folder Not Selected", "Please select a valid folder first using 'Browse Folder'.")
            return

        logging.info(f"Loading filenames from folder: {self.folder_path}")
        self.check_log_window.setText(f"Loading filenames from: {self.folder_path}...")
        QApplication.processEvents()

        try:
            # List files, filter by common video extensions (case-insensitive)
            video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')
            files_in_folder = [
                f for f in os.listdir(self.folder_path)
                if os.path.isfile(os.path.join(self.folder_path, f)) and f.lower().endswith(video_extensions)
            ]

            # Extract base name (without extension) and sort naturally
            folder_basenames = [os.path.splitext(f)[0] for f in files_in_folder]

            # Use the same sorting logic as renaming tab for consistency
            self.folder_files = sorted(folder_basenames, key=self.extract_chapter_sort_key)
            logging.info(f"Found {len(self.folder_files)} video files (basenames) and sorted them.")

            # Update table: Adjust row count if needed, populate folder column
            current_playlist_rows = self.check_table.rowCount()
            required_rows = max(current_playlist_rows, len(self.folder_files))
            self.check_table.setRowCount(required_rows)

            for i in range(required_rows):
                 # Ensure row numbering item exists
                if not self.check_table.item(i, 0):
                    self.check_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                    self.check_table.item(i, 0).setTextAlignment(Qt.AlignCenter)

                # Populate folder name column
                folder_name = self.folder_files[i] if i < len(self.folder_files) else ""
                self.check_table.setItem(i, 1, QTableWidgetItem(folder_name))

                 # Ensure playlist item exists (might be empty)
                if not self.check_table.item(i, 2):
                    self.check_table.setItem(i, 2, QTableWidgetItem(""))


            self.check_table.resizeColumnsToContents()
            self.check_table.resizeRowsToContents()
            self.check_log_window.append(f"Successfully loaded {len(self.folder_files)} folder filenames into column 2.")
            QMessageBox.information(self, "Folder Names Loaded", f"Loaded {len(self.folder_files)} video filenames (without extension) from the selected folder.")

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Folder Names", f"Failed to read or process folder contents: {e}")
            self.check_log_window.append(f"<font color='red'>Error loading folder names: {e}</font>")
            logging.exception(f"Failed to load filenames from {self.folder_path}")


    def load_check_playlist(self):
        # This is identical to load_rename_playlist, just targets a different combo box and dictionary
        if not self.check_authentication(): return
        logging.info("Loading playlists for Checking tab.")
        try:
            playlists = []
            nextPageToken = None
            while True:
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                playlists.extend(response.get("items", []))
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break

            self.check_playlist_combo.clear()
            self.check_playlists.clear()
            if playlists:
                for item in playlists:
                    playlist_id = item["id"]
                    title = item["snippet"]["title"]
                    description = item["snippet"].get("description", "No description")
                    video_count = item["contentDetails"]["itemCount"]
                    display_text = f"{title} ({video_count} videos) - {description[:50]}"
                    self.check_playlists[display_text] = playlist_id
                    self.check_playlist_combo.addItem(display_text)
                logging.info(f"Loaded {len(playlists)} playlists into checking dropdown.")
                QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists. Select one and click 'Load Playlist Video Names'.")
            else:
                QMessageBox.information(self, "No Playlists", "No playlists found for your channel.")
                logging.info("No playlists found for the user.")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlists: {e}")
            logging.exception("Failed to load playlists for checking tab.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            logging.exception("Unexpected error loading playlists for checking tab.")

    def show_check_playlist_names(self):
        # Similar to show_rename_scheme, but only loads titles and populates column 3
        if not self.check_authentication(): return
        selected_display_text = self.check_playlist_combo.currentText()
        if not selected_display_text:
            QMessageBox.warning(self, "No Playlist Selected", "Please select a playlist from the dropdown first.")
            return

        playlist_id = self.check_playlists.get(selected_display_text)
        if not playlist_id:
            QMessageBox.critical(self, "Error", "Could not find ID for the selected playlist.")
            logging.error(f"Could not find playlist ID for display text: {selected_display_text}")
            return

        logging.info(f"Loading video names for checking for playlist ID: {playlist_id}")
        self.check_log_window.setText(f"Loading video names for playlist: {selected_display_text}...")
        QApplication.processEvents()

        try:
            videos = []
            nextPageToken = None
            while True:
                # Only need snippet for title
                request = self.youtube.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=nextPageToken
                )
                response = request.execute()
                videos.extend(response.get("items", []))
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break
            logging.info(f"Fetched {len(videos)} video items from playlist {playlist_id}.")

            # Sort video titles naturally
            try:
                sorted_videos = sorted(videos, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                self.playlist_titles = [v['snippet']['title'] for v in sorted_videos]
                logging.info("Playlist video titles sorted naturally.")
            except Exception as e:
                 logging.exception("Error during playlist video title sorting. Using API order.")
                 QMessageBox.warning(self,"Sort Warning", f"Could not sort playlist video titles naturally, using API order. Error: {e}")
                 self.playlist_titles = [v['snippet']['title'] for v in videos] # Fallback


            # Update table: Adjust row count if needed, populate playlist column
            current_folder_rows = len(self.folder_files) # Use the actual count from loaded folder data
            required_rows = max(current_folder_rows, len(self.playlist_titles))
            self.check_table.setRowCount(required_rows)

            for i in range(required_rows):
                # Ensure row numbering item exists
                if not self.check_table.item(i, 0):
                    self.check_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                    self.check_table.item(i, 0).setTextAlignment(Qt.AlignCenter)

                 # Ensure folder item exists (might be empty)
                if not self.check_table.item(i, 1):
                    self.check_table.setItem(i, 1, QTableWidgetItem(self.folder_files[i] if i < len(self.folder_files) else ""))


                # Populate playlist title column
                playlist_title = self.playlist_titles[i] if i < len(self.playlist_titles) else ""
                self.check_table.setItem(i, 2, QTableWidgetItem(playlist_title))


            self.check_table.resizeColumnsToContents()
            self.check_table.resizeRowsToContents()
            self.check_log_window.append(f"Successfully loaded {len(self.playlist_titles)} playlist video titles into column 3.")
            QMessageBox.information(self, "Playlist Names Loaded", f"Loaded {len(self.playlist_titles)} video titles from the selected playlist.")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlist videos: {e}")
            self.check_log_window.append(f"<font color='red'>Error loading playlist videos: {e}</font>")
            logging.exception(f"Failed to load videos for playlist {playlist_id}.")
        except Exception as e:
             QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
             self.check_log_window.append(f"<font color='red'>Unexpected error: {e}</font>")
             logging.exception("Unexpected error showing check playlist names.")

    def compare_folder_playlist(self):
        row_count = self.check_table.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "Nothing to Compare", "Please load folder names and playlist names first.")
            return

        logging.info("Starting comparison between folder names and playlist titles.")
        self.check_log_window.setText("Comparing folder filenames (Col 2) and playlist titles (Col 3)...")
        QApplication.processEvents()

        folder_list = []
        playlist_list = []
        for i in range(row_count):
            folder_item = self.check_table.item(i, 1)
            playlist_item = self.check_table.item(i, 2)
            folder_text = folder_item.text().strip() if folder_item else ""
            playlist_text = playlist_item.text().strip() if playlist_item else ""
            # Only add non-empty strings to the lists for comparison counts
            if folder_text:
                folder_list.append(folder_text)
            if playlist_text:
                playlist_list.append(playlist_text)

        messages = []
        discrepancy_found = False

        # 1. Compare counts
        if len(folder_list) != len(playlist_list):
            msg = f"Item Count Mismatch: Folder has {len(folder_list)} items, Playlist has {len(playlist_list)} items."
            messages.append(f"<font color='orange'>{msg}</font>")
            logging.warning(msg)
            discrepancy_found = True
        else:
             messages.append(f"Item Count Match: Both have {len(folder_list)} items.")
             logging.info(f"Item counts match: {len(folder_list)}")


        # 2. Check for duplicates within the playlist titles (often indicates issues)
        seen = {}
        duplicates = []
        for title in playlist_list:
             seen[title] = seen.get(title, 0) + 1
        duplicates = [f"'{title}' ({count} times)" for title, count in seen.items() if count > 1]
        if duplicates:
            msg = "Duplicate Titles Found in Playlist: " + ", ".join(duplicates)
            messages.append(f"<font color='orange'>{msg}</font>")
            logging.warning(msg)
            discrepancy_found = True


        # 3. Compare line-by-line based on table rows
        mismatch_details = []
        max_compare_rows = self.check_table.rowCount() # Compare all rows shown in table
        for i in range(max_compare_rows):
            folder_item = self.check_table.item(i, 1)
            playlist_item = self.check_table.item(i, 2)
            f_text = folder_item.text().strip() if folder_item else ""
            p_text = playlist_item.text().strip() if playlist_item else ""

            # Compare only if both sides have text OR if one side has text and the other doesn't (indicates missing item)
            if (f_text or p_text) and (f_text != p_text):
                mismatch_msg = f"Row {i+1}: Folder='{f_text}' | Playlist='{p_text}'"
                mismatch_details.append(mismatch_msg)
                # Highlight the row in the table? (Optional, can be complex)
                logging.warning(f"Mismatch at Table Row {i+1}: Folder='{f_text}', Playlist='{p_text}'")
                discrepancy_found = True

        if mismatch_details:
             messages.append("<font color='red'><b>Line-by-Line Mismatches:</b></font><br>" + "<br>".join(mismatch_details))


        # Display results
        self.check_log_window.append("\n--- Comparison Results ---")
        self.check_log_window.append("<br>".join(messages)) # Use HTML for formatting in log

        if discrepancy_found:
            summary = "Discrepancies found! See details in the log window below."
            QMessageBox.warning(self, "Comparison Finished: Issues Found", summary)
            logging.warning("Comparison finished with discrepancies.")
        else:
            summary = "Folder names and playlist titles appear to match based on current loaded data."
            QMessageBox.information(self, "Comparison Finished: Match", summary)
            logging.info("Comparison finished successfully with no mismatches detected.")

        self.check_log_window.verticalScrollBar().setValue(self.check_log_window.verticalScrollBar().maximum()) # Scroll to bottom


    # ----------------------- Tab 4: Generate Excel -----------------------
    def init_excel_tab(self):
        layout = QVBoxLayout()

        # --- Row 1: Load Playlists ---
        load_layout = QHBoxLayout()
        self.load_excel_playlists_btn = QPushButton("Load My Playlists")
        self.load_excel_playlists_btn.clicked.connect(self.load_excel_playlists)
        load_layout.addWidget(self.load_excel_playlists_btn)
        load_layout.addStretch()
        layout.addLayout(load_layout)

        # --- Row 2: Playlist Table with Checkboxes ---
        self.excel_playlist_table = QTableWidget()
        self.excel_playlist_table.setColumnCount(2)
        self.excel_playlist_table.setHorizontalHeaderLabels(["Select", "Playlist Details (Name, Desc, Count)"])
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents) # Checkbox column
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Details column
        self.excel_playlist_table.verticalHeader().setVisible(False) # Hide row numbers
        self.excel_playlist_table.setEditTriggers(QTableWidget.NoEditTriggers) # Make table read-only
        layout.addWidget(QLabel("Select Playlists to Generate Excel For:"))
        layout.addWidget(self.excel_playlist_table)

        # --- Row 3: Progress and Log ---
        progress_log_layout = QHBoxLayout()
        self.excel_progress_bar = QProgressBar()
        progress_log_layout.addWidget(QLabel("Progress:"))
        progress_log_layout.addWidget(self.excel_progress_bar)
        layout.addLayout(progress_log_layout)

        self.excel_log_window = QTextEdit()
        self.excel_log_window.setReadOnly(True)
        self.excel_log_window.setFixedHeight(200) # More height for detailed logs
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.excel_log_window)

        # --- Row 4: Generate Button ---
        self.generate_excel_btn = QPushButton("Generate Excel File(s) for Selected Playlists")
        self.generate_excel_btn.clicked.connect(self.generate_selected_excels)
        layout.addWidget(self.generate_excel_btn)

        self.excel_tab.setLayout(layout)

    def load_excel_playlists(self):
        if not self.check_authentication(): return
        logging.info("Loading playlists for Excel Generation tab.")
        self.excel_log_window.setText("Loading your playlists...")
        QApplication.processEvents()

        try:
            playlists = []
            nextPageToken = None
            while True:
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                playlists.extend(response.get("items", []))
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break

            self.excel_playlist_table.setRowCount(0) # Clear previous
            self.excel_playlists_data.clear() # Clear stored data

            if playlists:
                self.excel_playlist_table.setRowCount(len(playlists))
                for row, item in enumerate(playlists):
                    playlist_id = item["id"]
                    snippet = item["snippet"]
                    title = snippet["title"]
                    description = snippet.get("description", "No description")
                    video_count = item["contentDetails"]["itemCount"]

                    # Store data associated with the row
                    self.excel_playlists_data[row] = {
                        'id': playlist_id,
                        'title': title,
                        'description': description
                    }

                    # Column 0: Checkbox
                    checkbox = QCheckBox()
                    checkbox_widget = QWidget() # Use a widget to center the checkbox
                    checkbox_layout = QHBoxLayout(checkbox_widget)
                    checkbox_layout.addWidget(checkbox)
                    checkbox_layout.setAlignment(Qt.AlignCenter)
                    checkbox_layout.setContentsMargins(0,0,0,0)
                    self.excel_playlist_table.setCellWidget(row, 0, checkbox_widget)

                    # Column 1: Playlist Details
                    display_text = f"{title} \nDesc: {description[:100]}{'...' if len(description)>100 else ''} \n({video_count} videos)"
                    details_item = QTableWidgetItem(display_text)
                    self.excel_playlist_table.setItem(row, 1, details_item)

                self.excel_playlist_table.resizeRowsToContents()
                self.excel_log_window.append(f"Loaded {len(playlists)} playlists. Select the ones you want and click 'Generate'.")
                logging.info(f"Loaded {len(playlists)} playlists into Excel tab table.")
                QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists. Check the boxes for the ones you want to process.")
            else:
                 self.excel_log_window.append("No playlists found for your channel.")
                 QMessageBox.information(self, "No Playlists", "No playlists found for your channel.")
                 logging.info("No playlists found for the user (Excel tab).")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlists: {e}")
            self.excel_log_window.append(f"<font color='red'>API Error loading playlists: {e}</font>")
            logging.exception("Failed to load playlists for Excel tab.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
            self.excel_log_window.append(f"<font color='red'>Unexpected error loading playlists: {e}</font>")
            logging.exception("Unexpected error loading playlists for Excel tab.")

    def video_sort_key(self, title):
        """ Generates a sort key for videos based on specific naming conventions.
            Sort Order: Course Introduction -> Chapter Headers -> Chapter Parts (naturally) -> Others """
        title_lower = title.lower()

        # 1. Course Introduction
        if "course introduction" in title_lower:
            # Sort by the course name itself if needed, otherwise fixed key
            return (0, 0, 0, "", title_lower) # Group 0

        # 2. Chapter Header: "Chapter N - Title"
        #    Allows flexible spacing and separators (-, –, —)
        m_header = re.match(r'chapter\s+(\d+)\s*[-–—]?\s+.*', title_lower)
        if m_header:
            chapter_num = int(m_header.group(1))
            # Group 1, Sort by Chapter Num, Sub-sort 0 (Header), Suffix "", Original title
            return (1, chapter_num, 0, "", title_lower)

        # 3. Chapter Video Part: "Chapter NA - Title"
        m_video = re.match(r'chapter\s+(\d+)([a-z]+)\s*[-–—]?\s+.*', title_lower)
        if m_video:
            chapter_num = int(m_video.group(1))
            suffix = m_video.group(2)
             # Group 1, Sort by Chapter Num, Sub-sort 1 (Part), Suffix, Original title
            return (1, chapter_num, 1, suffix, title_lower)

        # 4. Fallback for any other titles
        return (2, 0, 0, "", title_lower) # Group 2 (Others), sorted alphabetically

    def generate_selected_excels(self):
        if not self.check_authentication(): return

        selected_playlists = []
        for row in range(self.excel_playlist_table.rowCount()):
            checkbox_widget = self.excel_playlist_table.cellWidget(row, 0)
            checkbox = checkbox_widget.findChild(QCheckBox)
            if checkbox and checkbox.isChecked():
                if row in self.excel_playlists_data:
                     selected_playlists.append(self.excel_playlists_data[row])
                else:
                     logging.warning(f"Checkbox checked at row {row}, but no data found in self.excel_playlists_data.")

        if not selected_playlists:
             QMessageBox.warning(self, "No Selection", "Please select at least one playlist using the checkboxes.")
             return

        # Create dated output folder
        try:
            today_str = datetime.datetime.now().strftime("%d_%m_%y")
            output_folder_name = f"{today_str}_Excel"
            # Create folder in the same directory as the script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(script_dir, output_folder_name)
            os.makedirs(output_dir, exist_ok=True)
            logging.info(f"Ensured output directory exists: {output_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Folder Creation Error", f"Could not create output directory '{output_folder_name}': {e}")
            logging.exception("Failed to create output directory.")
            return

        total_selected = len(selected_playlists)
        self.excel_progress_bar.setMaximum(total_selected)
        self.excel_progress_bar.setValue(0)
        self.excel_log_window.clear()
        self.excel_log_window.append(f"Starting Excel generation for {total_selected} selected playlist(s)...")
        self.excel_log_window.append(f"Output folder: {output_dir}")
        QApplication.processEvents()

        success_count = 0
        fail_count = 0

        for i, playlist_data in enumerate(selected_playlists):
            playlist_id = playlist_data['id']
            playlist_title = playlist_data['title']
            playlist_description = playlist_data['description']

            self.excel_log_window.append(f"\nProcessing Playlist {i+1}/{total_selected}: '{playlist_title}' (ID: {playlist_id})")
            QApplication.processEvents()

            try:
                self.generate_excel_for_playlist(playlist_id, playlist_title, playlist_description, output_dir)
                self.excel_log_window.append(f"--> Successfully generated Excel for '{playlist_title}'.")
                logging.info(f"Successfully generated Excel for playlist ID {playlist_id}")
                success_count += 1
            except HttpError as e:
                fail_count += 1
                error_msg = f"--> Failed (API Error) for '{playlist_title}': {e}"
                self.excel_log_window.append(f"<font color='red'>{error_msg}</font>")
                logging.exception(f"API Error generating Excel for playlist {playlist_id}: {playlist_title}")
            except Exception as e:
                fail_count += 1
                error_msg = f"--> Failed (Error) for '{playlist_title}': {e}"
                self.excel_log_window.append(f"<font color='red'>{error_msg}</font>")
                logging.exception(f"Unexpected Error generating Excel for playlist {playlist_id}: {playlist_title}")
            finally:
                 self.excel_progress_bar.setValue(i + 1)
                 QApplication.processEvents()


        final_message = f"Excel generation finished. Success: {success_count}, Failed: {fail_count}."
        self.excel_log_window.append(f"\n<b>{final_message}</b>")
        logging.info(final_message)
        QMessageBox.information(self, "Excel Generation Done", final_message + f"\nFiles saved in: {output_dir}")
        # Optionally open the output folder
        try:
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin': # macOS
                os.system(f'open "{output_dir}"')
            else: # Linux variants
                 os.system(f'xdg-open "{output_dir}"')
        except Exception as e:
             logging.warning(f"Could not automatically open output folder: {e}")

    def generate_excel_for_playlist(self, playlist_id, playlist_title, playlist_description, output_dir):
        """Fetches videos, sorts them, extracts data, and saves to an Excel file."""
        logging.info(f"Generating Excel for Playlist ID: {playlist_id}, Title: {playlist_title}")

        # 1. Parse Course Code and Language Code from Playlist Title
        course_code = "UNKNOWN"
        language_code = "UNKNOWN"
        match = re.match(r'PL_([^_]+)_(\w+)', playlist_title, re.IGNORECASE)
        if match:
            course_code = match.group(1)
            language_code = match.group(2)
            logging.info(f"Parsed CourseCode: {course_code}, LanguageCode: {language_code}")
        else:
            logging.warning(f"Playlist title '{playlist_title}' did not match expected format PL_CourseCode_LangCode.")
            self.excel_log_window.append(f"<font color='orange'>Warning: Playlist title '{playlist_title}' doesn't match PL_CourseCode_LangCode format.</font>")


        # 2. Construct Excel Filename
        # Format: Playlist description_Playlist name.xlsx
        sanitized_desc = sanitize_filename(playlist_description if playlist_description else "NoDesc")
        sanitized_title = sanitize_filename(playlist_title)
        excel_filename = f"{sanitized_desc}_{sanitized_title}.xlsx"
        excel_filepath = os.path.join(output_dir, excel_filename)
        logging.info(f"Target Excel file path: {excel_filepath}")

        # 3. Fetch all video items from the playlist
        all_video_items = []
        nextPageToken = None
        self.excel_log_window.append("   Fetching video details...")
        QApplication.processEvents()
        while True:
            request = self.youtube.playlistItems().list(
                part="snippet,contentDetails", # Need snippet (title, desc, pos), contentDetails (videoId)
                playlistId=playlist_id,
                maxResults=50,
                pageToken=nextPageToken
            )
            response = request.execute()
            all_video_items.extend(response.get("items", []))
            nextPageToken = response.get("nextPageToken")
            if not nextPageToken:
                break
        logging.info(f"Fetched {len(all_video_items)} total items for playlist {playlist_id}.")
        self.excel_log_window.append(f"   Fetched {len(all_video_items)} video items.")
        QApplication.processEvents()


        # 4. Sort video items using the custom sort key
        try:
            sorted_video_items = sorted(all_video_items, key=lambda item: self.video_sort_key(item.get("snippet", {}).get("title", "")))
            logging.info("Video items sorted successfully.")
            self.excel_log_window.append("   Videos sorted.")
            QApplication.processEvents()
        except Exception as e:
            logging.exception("Error sorting video items. Proceeding with API order.")
            self.excel_log_window.append(f"<font color='orange'>   Warning: Could not sort videos naturally ({e}). Using API order.</font>")
            sorted_video_items = all_video_items # Fallback to original order


        # 5. Process sorted videos and prepare data for Excel
        excel_data = []
        current_chapter_name = ""
        order_in_chapter = 0

        for item in sorted_video_items:
            snippet = item.get("snippet", {})
            contentDetails = item.get("contentDetails", {})

            video_id = contentDetails.get("videoId")
            video_title = snippet.get("title", "!!! MISSING TITLE !!!")
            video_description = snippet.get("description", "") # Get full description
            # position = snippet.get("position", -1) # Original position in playlist (optional)

            if not video_id:
                 logging.warning(f"Skipping item with title '{video_title}' because videoId is missing.")
                 self.excel_log_window.append(f"<font color='orange'>   Warning: Skipping item '{video_title[:50]}...' - Missing video ID.</font>")
                 continue

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"

            # Determine Chapter Name and Order Number
            chapter_name_for_excel = ""
            order_no = 0
            title_lower = video_title.lower()

            # Check for Course Introduction
            if "course introduction" in title_lower:
                chapter_name_for_excel = "" # Empty as per requirement
                order_no = 0
                current_chapter_name = "Introduction" # Set context, but don't use in Excel
                order_in_chapter = 0 # Reset counter for next chapter

            # Check for Chapter Header (e.g., "Chapter N - Title")
            elif re.match(r'chapter\s+\d+\s*[-–—]?\s+.*', title_lower) and not re.match(r'chapter\s+\d+[a-z]+\s*[-–—]?\s+.*', title_lower):
                current_chapter_name = video_title # The header title is the chapter name
                chapter_name_for_excel = current_chapter_name
                order_no = 0
                order_in_chapter = 0 # Reset counter for parts within this chapter

            # Check for Chapter Video Part (e.g., "Chapter NA - Title")
            elif re.match(r'chapter\s+\d+[a-z]+\s*[-–—]?\s+.*', title_lower):
                if not current_chapter_name or current_chapter_name == "Introduction":
                     # If part appears before header or only after intro, log warning but proceed
                     logging.warning(f"Video part '{video_title}' found without preceding chapter header. Using 'Unknown Chapter'.")
                     self.excel_log_window.append(f"<font color='orange'>   Warning: Video part '{video_title[:30]}...' found without clear chapter header. Assigning to 'Unknown Chapter'.</font>")
                     chapter_name_for_excel = "Unknown Chapter" # Fallback
                     # Reset order if context is unclear
                     if current_chapter_name == "Introduction": order_in_chapter = 0
                else:
                    chapter_name_for_excel = current_chapter_name # Use the last seen chapter header

                order_in_chapter += 1
                order_no = order_in_chapter
            else:
                 # Fallback for unexpected titles - treat as part of previous chapter or unknown
                 logging.warning(f"Video title '{video_title}' doesn't match expected formats. Assigning based on current context.")
                 self.excel_log_window.append(f"<font color='orange'>   Warning: Title '{video_title[:50]}...' doesn't match standard format. Treating as part of '{current_chapter_name or 'Unknown'}'.</font>")
                 chapter_name_for_excel = current_chapter_name if current_chapter_name and current_chapter_name != "Introduction" else "Unknown Chapter Content"
                 order_in_chapter += 1
                 order_no = order_in_chapter


            excel_data.append({
                'CourseCode': course_code,
                'Chapter Name': chapter_name_for_excel,
                'Youtubeurl': youtube_url,
                'Video Title': video_title,
                'Video Description': video_description, # Use actual video description
                'OrderNo in Chapter': order_no,
                'Language code': language_code
            })

        # 6. Create Pandas DataFrame and save to Excel
        if not excel_data:
             logging.warning(f"No processable video data found for playlist {playlist_id}. Skipping Excel file creation.")
             self.excel_log_window.append("<font color='orange'>   Warning: No valid video data found to create Excel file.</font>")
             # Consider this a failure? Or success with no output? Let's treat as warning/skip.
             # If treated as failure, raise an exception here.
             # raise ValueError("No valid video data found to create Excel file.")
             return # Successfully did nothing?

        df = pd.DataFrame(excel_data)
        logging.info(f"Created DataFrame with {len(df)} rows. Saving to {excel_filepath}")
        self.excel_log_window.append(f"   Processed {len(df)} videos. Saving Excel file...")
        QApplication.processEvents()

        try:
             # Use openpyxl engine explicitly for better compatibility potential
            df.to_excel(excel_filepath, index=False, engine='openpyxl')
            logging.info(f"Successfully saved Excel file: {excel_filepath}")
        except Exception as e:
             logging.exception(f"Error saving DataFrame to Excel file: {excel_filepath}")
             # Re-raise the exception to be caught by the calling function
             raise IOError(f"Failed to save Excel file {excel_filename}: {e}") from e


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Apply a style for better look and feel (optional)
    # Available styles: 'Fusion', 'Windows', 'WindowsVista' (Windows only), 'Macintosh' (macOS only)
    try:
        app.setStyle("Fusion")
    except Exception as e:
        logging.warning(f"Could not apply Fusion style: {e}")

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

# --- END OF FILE youtuberename.py ---