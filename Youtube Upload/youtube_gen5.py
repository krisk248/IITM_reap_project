import os
import sys
import json
import time
import re
import smtplib
import webbrowser
from email.mime.text import MIMEText
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QFileDialog, QMessageBox,
    QFormLayout, QGroupBox, QTextEdit, QProgressBar, QComboBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# ----------------- Constants -----------------
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
MAX_DAILY_QUOTA = 500000000
COST_PER_VIDEO = 1650

# SMTP settings – replace these with your actual SMTP details.
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "reapdubbing@reaplearn.in"
SMTP_PASS = "obvqpcqybsejmrmh "
RECIPIENT_EMAIL = "reaplearn.2000@gmail.com"

def natural_sort_key(s):
    """Return a key for natural order sorting using a raw regex string."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def send_email(config, uploaded_count):
    """Send email notification using the given config and uploaded count."""
    subject = f"Upload Completed for {config['course_name']}"
    body = f"Course Name: {config['course_name']}\n"
    body += f"Playlist: {config.get('playlist_title', 'N/A')}\n"
    body += f"Total Videos Uploaded: {uploaded_count}\n"
    body += f"Upload Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = RECIPIENT_EMAIL
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)

# ----------------- Upload Worker -----------------
class UploadWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = True
        self.paused = False
        self.uploaded_count = 0
        self.uploaded_video_ids = []  # to store video IDs as they are uploaded
        self.log_file = None

    def log(self, message):
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}"
        self.log_signal.emit(log_message)
        if self.log_file:
            self.log_file.write(log_message + "\n")
            self.log_file.flush()

    def sanitize_text(self, text):
        return text.replace("`", "").replace("'", "")

    def validate_course_structure(self):
        valid_exts = ['.mp4', '.mov', '.avi', '.mkv']
        video_folder = self.config['video_folder']
        all_videos = []
        for root, dirs, files in os.walk(video_folder):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    all_videos.append(os.path.join(root, f))
        
        errors = []
        course_intro_found = False
        main_pattern = re.compile(r'^Chapter\s+(\d+)\s*-\s*(.+)$', re.IGNORECASE)
        supplemental_pattern = re.compile(r'^Chapter\s+(\d+)([A-Za-z]+)\s*-\s*(.+)$', re.IGNORECASE)
        chapters = {}
        valid_videos = []

        for file_path in all_videos:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            base_name = self.sanitize_text(base_name)
            if "course introduction" in base_name.lower():
                course_intro_found = True
                valid_videos.append(file_path)
                continue
            
            main_match = main_pattern.match(base_name)
            supp_match = supplemental_pattern.match(base_name)
            if main_match:
                chapter_num = main_match.group(1)
                if chapter_num not in chapters:
                    chapters[chapter_num] = {'main': None, 'supplemental': []}
                chapters[chapter_num]['main'] = file_path
                valid_videos.append(file_path)
            elif supp_match:
                chapter_num = supp_match.group(1)
                if chapter_num not in chapters:
                    chapters[chapter_num] = {'main': None, 'supplemental': []}
                chapters[chapter_num]['supplemental'].append(file_path)
                valid_videos.append(file_path)
            else:
                errors.append(f"Invalid file name format: {file_path}")

        if not course_intro_found:
            errors.append("Missing course introduction file (file name must contain 'Course Introduction' with a valid video extension).")
        for chapter, vids in chapters.items():
            if vids['main']:
                supplemental_ok = False
                for supp in vids['supplemental']:
                    supp_base = os.path.splitext(os.path.basename(supp))[0]
                    supp_match = supplemental_pattern.match(supp_base)
                    if supp_match:
                        letters = supp_match.group(2)
                        if letters.upper().startswith("A"):
                            supplemental_ok = True
                            break
                if not supplemental_ok:
                    errors.append(f"Missing supplemental video for Chapter {chapter} (expected at least one file with format: Chapter {chapter}A - <topic>).")
        if errors:
            error_file = os.path.join(self.config['video_folder'], "error.txt")
            with open(error_file, "w", encoding="utf-8") as f:
                for err in errors:
                    f.write(err + "\n")
            self.log("Validation errors found. See error file: " + error_file)
            return None

        valid_videos_sorted = sorted(valid_videos, key=lambda x: natural_sort_key(os.path.basename(x)))
        return valid_videos_sorted

    def run(self):
        try:
            course_dir = os.path.join("courses", self.config['course_name'])
            os.makedirs(course_dir, exist_ok=True)
            log_file_path = os.path.join(course_dir, "upload_log.txt")
            self.log_file = open(log_file_path, "a", encoding="utf-8")
            self.log("Starting upload process...")

            token_path = os.path.join(course_dir, "token.json")
            youtube = self.authenticate(self.config['client_secret_path'], token_path)

            playlist_folder = self.config.get('playlist_folder')
            if playlist_folder:
                os.makedirs(playlist_folder, exist_ok=True)

            videos = self.validate_course_structure()
            if videos is None:
                self.log("Aborting upload due to validation errors.")
                self.finished_signal.emit(False)
                return

            self.log(f"Validation passed. Found {len(videos)} video(s) to upload.")
            start_index = self.load_resume_state(playlist_folder)
            if "resume_state" in self.config and self.config["resume_state"].isdigit():
                start_index = int(self.config["resume_state"])
                self.log(f"Using user-provided resume state: {start_index}.")
            self.log(f"Resuming from video index {start_index}.")

            request_count = 0
            total_videos = len(videos)

            for i in range(start_index, total_videos):
                if not self.running:
                    self.log("Upload cancelled by user.")
                    break
                while self.paused and self.running:
                    time.sleep(1)
                if request_count + COST_PER_VIDEO > MAX_DAILY_QUOTA:
                    self.log("Daily quota exceeded. Stopping uploads.")
                    break

                video_path = videos[i]
                self.log(f"Uploading video: '{os.path.basename(video_path)}' to playlist: '{self.config.get('playlist_title', 'N/A')}'")
                try:
                    self.upload_video(youtube, video_path, self.config['playlist_id'])
                    request_count += COST_PER_VIDEO
                    self.uploaded_count += 1
                    self.log(f"Uploaded video: '{os.path.basename(video_path)}' to playlist: '{self.config.get('playlist_title', 'N/A')}'")
                    self.save_resume_state(playlist_folder, i + 1)
                    progress = int((i + 1) / total_videos * 100)
                    self.progress_signal.emit(progress)
                except Exception as e:
                    self.log(f"Error uploading video '{os.path.basename(video_path)}': {str(e)}")
                    break

            if self.uploaded_count == total_videos:
                playlist_url = f"https://www.youtube.com/playlist?list={self.config['playlist_id']}"
                self.log(f"All videos uploaded. Opening playlist URL: {playlist_url}")
                webbrowser.open(playlist_url)

            self.finished_signal.emit(True)
        except Exception as e:
            self.log(f"Fatal error: {str(e)}")
            self.finished_signal.emit(False)
        finally:
            if self.log_file:
                self.log_file.close()

    def authenticate(self, client_secret_path, token_path):
        token_file_provided = self.config.get('token_file', "").strip()
        creds = None
        if token_file_provided and os.path.exists(token_file_provided):
            try:
                creds = Credentials.from_authorized_user_file(token_file_provided, YOUTUBE_SCOPES)
            except Exception as e:
                print("Failed to load credentials from provided token file:", e)
        if not creds and os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, YOUTUBE_SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, YOUTUBE_SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w', encoding="utf-8") as token_file:
                token_file.write(creds.to_json())
        return build("youtube", "v3", credentials=creds)

    def load_resume_state(self, folder):
        state_file = os.path.join(folder, "resume_state.txt")
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                try:
                    return int(f.read().strip())
                except:
                    return 0
        return 0

    def save_resume_state(self, folder, index):
        state_file = os.path.join(folder, "resume_state.txt")
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(str(index))

    def upload_video(self, youtube, video_path, playlist_id):
        file_name = os.path.splitext(os.path.basename(video_path))[0]
        file_name = self.sanitize_text(file_name)
        if " - " in file_name:
            parts = file_name.split(" - ", 1)
            title = self.sanitize_text(file_name)
            description = self.sanitize_text(parts[1].strip())
        else:
            title = self.sanitize_text(file_name)
            description = self.sanitize_text(file_name)
        self.log(f"Starting upload for video: '{title}' with description: '{description}'")
        body = {
            "snippet": {
                "title": title,
                "description": description
            },
            "status": {
                "privacyStatus": "unlisted"
            }
        }
        media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                self.log(f"Upload progress: {int(status.progress() * 100)}%")
        video_id = response.get("id")
        self.log(f"Upload completed. Video ID: {video_id}")
        self.uploaded_video_ids.append(video_id)
        self.add_video_to_playlist(youtube, video_id, playlist_id)

    def add_video_to_playlist(self, youtube, video_id, playlist_id):
        request = youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        )
        response = request.execute()
        self.log(f"Video {video_id} added to playlist {playlist_id}.")
        return response

# ----------------- Delete Worker -----------------
class DeleteWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)
    
    def __init__(self, config, video_ids):
        super().__init__()
        self.config = config
        self.video_ids = video_ids

    def log(self, message):
        self.log_signal.emit(message)

    def run(self):
        course_dir = os.path.join("courses", self.config['course_name'])
        token_path = os.path.join(course_dir, "token.json")
        try:
            youtube = UploadWorker(self.config).authenticate(self.config['client_secret_path'], token_path)
        except Exception as e:
            self.log("Authentication failed for deletion: " + str(e))
            self.finished_signal.emit(False)
            return
        for video_id in self.video_ids:
            try:
                self.log(f"Deleting video {video_id}...")
                request = youtube.videos().delete(videoId=video_id)
                request.execute()
                self.log(f"Video {video_id} deleted successfully.")
            except Exception as e:
                self.log(f"Failed to delete video {video_id}: {str(e)}")
        self.finished_signal.emit(True)

# ----------------- Main Application -----------------
class UploadApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.delete_worker = None
        self.playlists = {}
        self.upload_config = None
        self.setup_ui()
        self.setStyleSheet("""
            QMainWindow { background-color: #f0f0f0; }
            QGroupBox { 
                border: 1px solid gray;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QPushButton { 
                background-color: #0078d4;
                color: white;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover { background-color: #006cbd; }
        """)

    def setup_ui(self):
        self.setWindowTitle("YouTube Upload Application")
        self.setGeometry(100, 100, 800, 600)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout()

        # Configuration Group
        config_group = QGroupBox("Upload Configuration")
        form_layout = QFormLayout()

        self.course_input = QLineEdit()
        self.client_secret_input = QLineEdit()
        self.btn_browse_client = QPushButton("Browse Client Secret")
        self.btn_authenticate = QPushButton("Authenticate")
        self.btn_load_playlists = QPushButton("Load Playlists")
        self.playlist_dropdown = QComboBox()
        self.video_folder_input = QLineEdit()
        self.btn_browse_folder = QPushButton("Browse Video Folder")
        self.token_input = QLineEdit()
        self.btn_load_token = QPushButton("Load Token")
        self.resume_state_input = QLineEdit()

        form_layout.addRow("Course Name:", self.course_input)
        form_layout.addRow("Client Secret JSON:", self.client_secret_input)
        h_client_layout = QHBoxLayout()
        h_client_layout.addWidget(self.btn_browse_client)
        h_client_layout.addWidget(self.btn_authenticate)
        h_client_layout.addWidget(self.btn_load_playlists)
        form_layout.addRow(h_client_layout)
        form_layout.addRow("Token JSON:", self.token_input)
        form_layout.addRow(self.btn_load_token)
        form_layout.addRow("Select Playlist:", self.playlist_dropdown)
        form_layout.addRow("Video Folder:", self.video_folder_input)
        form_layout.addRow(self.btn_browse_folder)
        form_layout.addRow("Resume State:", self.resume_state_input)

        config_group.setLayout(form_layout)
        layout.addWidget(config_group)

        # Upload Control Buttons
        self.btn_start_upload = QPushButton("Start Upload")
        self.btn_pause_upload = QPushButton("Pause Upload")
        self.btn_cancel_upload = QPushButton("Cancel Upload")
        self.btn_pause_upload.setEnabled(False)
        self.btn_cancel_upload.setEnabled(False)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_start_upload)
        btn_layout.addWidget(self.btn_pause_upload)
        btn_layout.addWidget(self.btn_cancel_upload)
        layout.addLayout(btn_layout)

        # Delete and Send Email Buttons
        extra_btn_layout = QHBoxLayout()
        self.btn_delete_upload = QPushButton("Delete Upload")
        self.btn_delete_upload.setStyleSheet("background-color: red; color: white;")
        self.btn_send_email = QPushButton("Send Email")
        extra_btn_layout.addWidget(self.btn_delete_upload)
        extra_btn_layout.addWidget(self.btn_send_email)
        layout.addLayout(extra_btn_layout)

        # Progress and Log Output
        self.progress = QProgressBar()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("Log Output:"))
        layout.addWidget(self.log_area)

        main_widget.setLayout(layout)

        # Connect signals
        self.btn_browse_client.clicked.connect(self.browse_client_secret)
        self.btn_authenticate.clicked.connect(self.authenticate_account)
        self.btn_load_playlists.clicked.connect(self.load_playlists)
        self.btn_load_token.clicked.connect(self.load_token)
        self.btn_browse_folder.clicked.connect(self.browse_video_folder)
        self.btn_start_upload.clicked.connect(self.start_upload)
        self.btn_pause_upload.clicked.connect(self.pause_resume_upload)
        self.btn_cancel_upload.clicked.connect(self.cancel_upload)
        self.btn_delete_upload.clicked.connect(self.delete_upload)
        self.btn_send_email.clicked.connect(self.send_email_clicked)

    def browse_client_secret(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Client Secret JSON", "", "JSON Files (*.json)")
        if file:
            self.client_secret_input.setText(file)

    def authenticate_account(self):
        client_secret = self.client_secret_input.text().strip()
        if not client_secret or not os.path.exists(client_secret):
            QMessageBox.warning(self, "Error", "Please select a valid Client Secret JSON file first.")
            return
        try:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret, YOUTUBE_SCOPES)
            creds = flow.run_local_server(port=0)
            base_name = os.path.splitext(os.path.basename(client_secret))[0]
            token_file = base_name + "_token.json"
            with open(token_file, 'w', encoding="utf-8") as f:
                f.write(creds.to_json())
            self.token_input.setText(token_file)
            QMessageBox.information(self, "Authentication", f"Authentication successful. Token saved as {token_file}.")
        except Exception as e:
            QMessageBox.warning(self, "Authentication Error", f"Failed to authenticate: {str(e)}")

    def load_token(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select Token JSON", "", "JSON Files (*.json)")
        if file:
            self.token_input.setText(file)
            try:
                creds = Credentials.from_authorized_user_file(file, YOUTUBE_SCOPES)
                if creds and creds.valid:
                    QMessageBox.information(self, "Token Loaded", "Token file loaded successfully. Authentication is done.")
                else:
                    QMessageBox.warning(self, "Token Load Error", "Token file loaded but credentials are invalid or expired.")
            except Exception as e:
                QMessageBox.warning(self, "Token Load Error", f"Failed to load token file: {str(e)}")

    def browse_video_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Video Folder")
        if folder:
            self.video_folder_input.setText(folder)

    def load_playlists(self):
        client_secret = self.client_secret_input.text().strip()
        if not client_secret:
            QMessageBox.warning(self, "Error", "Please select a Client Secret JSON file first.")
            return
        try:
            token_file = self.token_input.text().strip()
            creds = None
            if token_file and os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, YOUTUBE_SCOPES)
            if not creds and os.path.exists("token_temp.json"):
                creds = Credentials.from_authorized_user_file("token_temp.json", YOUTUBE_SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(client_secret, YOUTUBE_SCOPES)
                    creds = flow.run_local_server(port=0)
                with open("token_temp.json", "w", encoding="utf-8") as token_file_obj:
                    token_file_obj.write(creds.to_json())
            youtube = build("youtube", "v3", credentials=creds)
            request = youtube.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50)
            response = request.execute()
            items = response.get("items", [])
            self.playlist_dropdown.clear()
            self.playlists.clear()
            for item in items:
                playlist_id = item["id"]
                snippet = item["snippet"]
                content_details = item["contentDetails"]
                title = snippet.get("title", "No Title")
                description = snippet.get("description", "No Description")
                video_count = content_details.get("itemCount", 0)
                display_text = f"{title} - {description} ({video_count} videos)"
                self.playlist_dropdown.addItem(display_text)
                folder_name = re.sub(r'[\\/*?:"<>|]', "", title)
                playlist_folder = os.path.join("playlists", folder_name)
                self.playlists[display_text] = {
                    "id": playlist_id,
                    "title": title,
                    "folder": playlist_folder
                }
            if items:
                QMessageBox.information(self, "Playlists Loaded", "Playlists loaded successfully.")
            else:
                QMessageBox.information(self, "No Playlists", "No playlists found for this account.")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to load playlists: {str(e)}")

    def start_upload(self):
        if not self.validate_inputs():
            return
        selected_playlist = self.playlist_dropdown.currentText()
        if selected_playlist not in self.playlists:
            QMessageBox.warning(self, "Error", "Please load and select a valid playlist.")
            return
        playlist_details = self.playlists[selected_playlist]
        os.makedirs(playlist_details["folder"], exist_ok=True)
        if self.resume_state_input.text().strip() == "":
            state_file = os.path.join(playlist_details["folder"], "resume_state.txt")
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    self.resume_state_input.setText(f.read().strip())
        config = {
            "course_name": self.course_input.text().strip(),
            "client_secret_path": self.client_secret_input.text().strip(),
            "video_folder": self.video_folder_input.text().strip(),
            "playlist_id": playlist_details["id"],
            "playlist_folder": playlist_details["folder"],
            "playlist_title": playlist_details["title"],
            "token_file": self.token_input.text().strip(),
            "resume_state": self.resume_state_input.text().strip()
        }
        self.upload_config = config
        self.worker = UploadWorker(config)
        self.worker.log_signal.connect(self.update_log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.finished_signal.connect(self.upload_finished)
        self.worker.start()
        self.btn_start_upload.setEnabled(False)
        self.btn_pause_upload.setEnabled(True)
        self.btn_cancel_upload.setEnabled(True)

    def pause_resume_upload(self):
        if self.worker:
            if not self.worker.paused:
                self.worker.paused = True
                self.btn_pause_upload.setText("Resume Upload")
                self.update_log("Upload paused.")
            else:
                self.worker.paused = False
                self.btn_pause_upload.setText("Pause Upload")
                self.update_log("Upload resumed.")

    def cancel_upload(self):
        if self.worker:
            self.worker.running = False
            self.update_log("Cancelling upload...")
            self.btn_pause_upload.setEnabled(False)
            self.btn_cancel_upload.setEnabled(False)

    def delete_upload(self):
        if self.worker is None or not self.worker.uploaded_video_ids:
            QMessageBox.warning(self, "Error", "No uploaded videos found to delete.")
            return
        confirm = QMessageBox.question(self, "Confirm Deletion", "Are you sure you want to permanently delete all uploaded videos?",
                                       QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.delete_worker = DeleteWorker(self.upload_config, self.worker.uploaded_video_ids)
        self.delete_worker.log_signal.connect(self.update_log)
        self.delete_worker.finished_signal.connect(lambda success: QMessageBox.information(self, "Deletion", "Deletion completed successfully." if success else "Deletion encountered errors."))
        self.delete_worker.start()

    def send_email_clicked(self):
        if self.upload_config is None:
            QMessageBox.warning(self, "Error", "Upload configuration not found. Please start an upload first.")
            return
        count = self.worker.uploaded_count if self.worker else 0
        success, msg = send_email(self.upload_config, count)
        if success:
            QMessageBox.information(self, "Email", msg)
        else:
            QMessageBox.warning(self, "Email", f"Failed to send email: {msg}")

    def update_log(self, message):
        self.log_area.append(message)

    def upload_finished(self, success):
        self.btn_start_upload.setEnabled(True)
        self.btn_pause_upload.setEnabled(False)
        self.btn_cancel_upload.setEnabled(False)
        if success:
            QMessageBox.information(self, "Success", "Upload completed successfully!")
        else:
            QMessageBox.warning(self, "Warning", "Upload completed with errors!")

    def validate_inputs(self):
        if self.course_input.text().strip() == "":
            QMessageBox.warning(self, "Error", "Course Name is required!")
            return False
        if self.client_secret_input.text().strip() == "":
            QMessageBox.warning(self, "Error", "Client Secret JSON file is required!")
            return False
        if self.video_folder_input.text().strip() == "":
            QMessageBox.warning(self, "Error", "Video folder is required!")
            return False
        return True

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.running = False
            self.worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UploadApp()
    window.show()
    sys.exit(app.exec_())
