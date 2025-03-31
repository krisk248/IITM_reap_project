import sys
import os
import datetime
from PyQt5 import QtWidgets, QtCore
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# The scope required for full YouTube management.
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

class YouTubeManager(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.youtube = None
        self.playlists = []  # Will hold fetched playlists with extra details.
        self.client_secret_file = None
        self.cancelled = False
        self.initUI()

    def initUI(self):
        self.setWindowTitle("YouTube Playlist Manager")
        self.resize(800, 600)
        main_layout = QtWidgets.QVBoxLayout(self)

        # File selection for the client secret JSON.
        file_layout = QtWidgets.QHBoxLayout()
        self.selectFileButton = QtWidgets.QPushButton("Select Client Secret JSON")
        self.selectFileButton.clicked.connect(self.select_client_secret)
        file_layout.addWidget(self.selectFileButton)
        self.clientSecretLabel = QtWidgets.QLabel("No file selected")
        file_layout.addWidget(self.clientSecretLabel)
        main_layout.addLayout(file_layout)

        # Status label to show selection details.
        self.statusLabel = QtWidgets.QLabel("Selected playlists: 0, Videos to delete: 0")
        main_layout.addWidget(self.statusLabel)

        # Table to list playlists.
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Playlist Title", "Description", "Select"])
        main_layout.addWidget(self.table)

        # Buttons for deletion and cancellation.
        button_layout = QtWidgets.QHBoxLayout()
        self.deleteButton = QtWidgets.QPushButton("Delete Selected")
        self.deleteButton.clicked.connect(self.delete_selected)
        self.deleteButton.setEnabled(False)
        button_layout.addWidget(self.deleteButton)
        
        self.cancelButton = QtWidgets.QPushButton("Cancel Deletion")
        self.cancelButton.clicked.connect(self.cancel_deletion)
        self.cancelButton.setEnabled(False)
        button_layout.addWidget(self.cancelButton)
        main_layout.addLayout(button_layout)

    def select_client_secret(self):
        options = QtWidgets.QFileDialog.Options()
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Client Secret JSON",
            "",
            "JSON Files (*.json);;All Files (*)",
            options=options
        )
        if filename:
            self.client_secret_file = filename
            self.clientSecretLabel.setText(os.path.basename(filename))
            # Once the client secret file is selected, perform authentication.
            self.authenticate_and_load_playlists()

    def authenticate_and_load_playlists(self):
        creds = None
        token_file = "token.json"
        # Check if the token file exists.
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            except Exception as e:
                print("Error loading token.json:", e)
        # If credentials are missing or invalid, run the OAuth flow.
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_file, SCOPES)
            creds = flow.run_local_server(port=8080)
            with open(token_file, "w") as token:
                token.write(creds.to_json())
        self.youtube = build('youtube', 'v3', credentials=creds)
        self.load_playlists()

    def load_playlists(self):
        # Fetch playlists along with 'snippet' and 'contentDetails' (for video count).
        request = self.youtube.playlists().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50  # For channels with >50 playlists, add pagination logic.
        )
        response = request.execute()
        self.playlists = response.get("items", [])
        self.populate_table()

    def populate_table(self):
        self.table.setRowCount(len(self.playlists))
        for row, playlist in enumerate(self.playlists):
            title = playlist["snippet"].get("title", "No Title")
            description = playlist["snippet"].get("description", "")
            # Retrieve the number of videos in the playlist.
            video_count = playlist.get("contentDetails", {}).get("itemCount", 0)

            title_item = QtWidgets.QTableWidgetItem(title)
            desc_item = QtWidgets.QTableWidgetItem(description)

            # Create a checkbox widget for selection.
            checkbox = QtWidgets.QCheckBox()
            # Store the video count as an attribute for status updates.
            checkbox.video_count = video_count
            checkbox.stateChanged.connect(self.update_status)

            self.table.setItem(row, 0, title_item)
            self.table.setItem(row, 1, desc_item)
            self.table.setCellWidget(row, 2, checkbox)
        # Enable the delete button now that playlists are loaded.
        self.deleteButton.setEnabled(True)
        self.update_status()

    def update_status(self):
        selected_playlists = 0
        total_videos = 0
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 2)
            if checkbox.isChecked():
                selected_playlists += 1
                total_videos += getattr(checkbox, "video_count", 0)
        self.statusLabel.setText(f"Selected playlists: {selected_playlists}, Videos to delete: {total_videos}")

    def cancel_deletion(self):
        self.cancelled = True
        QtWidgets.QMessageBox.information(self, "Cancellation", "Deletion process has been cancelled.")

    def delete_selected(self):
        self.cancelled = False
        self.cancelButton.setEnabled(True)
        self.deleteButton.setEnabled(False)
        # Loop over each playlist row to check if it is selected for deletion.
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 2)
            if checkbox.isChecked():
                playlist = self.playlists[row]
                playlist_id = playlist["id"]
                # Check for cancellation before processing.
                if self.cancelled:
                    QtWidgets.QMessageBox.information(self, "Cancelled", "Deletion cancelled by user.")
                    break
                self.statusLabel.setText(f"Deleting playlist: {playlist['snippet'].get('title', 'No Title')}")
                QtWidgets.QApplication.processEvents()  # Update the UI during deletion.
                self.delete_playlist_and_videos(playlist_id)
        self.statusLabel.setText("Deletion process completed.")
        self.deleteButton.setEnabled(True)
        self.cancelButton.setEnabled(False)
        QtWidgets.QMessageBox.information(self, "Deletion Completed", "Selected playlists and videos have been deleted.")

    def delete_playlist_and_videos(self, playlist_id):
        try:
            # Retrieve all videos in the playlist.
            request = self.youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50  # Add pagination logic if necessary.
            )
            response = request.execute()
            items = response.get("items", [])
            for item in items:
                if self.cancelled:
                    break
                video_id = item["snippet"]["resourceId"]["videoId"]
                try:
                    self.youtube.videos().delete(id=video_id).execute()
                    print(f"Deleted video: {video_id}")
                except Exception as e:
                    print(f"Error deleting video {video_id}: {e}")
            if not self.cancelled:
                self.youtube.playlists().delete(id=playlist_id).execute()
                print(f"Deleted playlist: {playlist_id}")
                # Log the deletion with a timestamp.
                with open("deletion_log.txt", "a") as log_file:
                    log_file.write(f"Deleted playlist {playlist_id} at {datetime.datetime.now()}\n")
        except Exception as e:
            print(f"Error processing playlist {playlist_id}: {e}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = YouTubeManager()
    window.show()
    sys.exit(app.exec_())
