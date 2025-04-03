# --- START OF FILE youtube_manager.py ---

import sys
import os
import re
import logging
import datetime
import json
import pandas as pd
# *** ADD THIS IMPORT for getting package versions ***
import importlib.metadata
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QComboBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QTextEdit, QProgressBar, QCheckBox, QHeaderView,
    QSpacerItem, QSizePolicy, QDialog, QDialogButtonBox, QFormLayout
)
from PyQt5.QtCore import Qt, QDir
from PyQt5.QtGui import QColor

# Google API imports
# pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 pandas openpyxl
from google_auth_oauthlib.flow import InstalledAppFlow # Import the base class
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- Constants ---
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CONFIG_FILE = "channel_config.json"
TOKENS_DIR = "tokens" # Subdirectory for token files

# --- Helper function to sanitize filenames ---
def sanitize_filename(name, replace_spaces=True):
    """Removes characters that are invalid in filenames/paths."""
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    if replace_spaces:
        name = re.sub(r'\s+', '_', name)
    if re.match(r'^\.+$', name) or name.upper() in ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']:
        name = "_" + name
    return name[:150]

# --- Custom Flow Class to Force Account Selection ---
class ForceAccountSelectionFlow(InstalledAppFlow):
    """
    An InstalledAppFlow subclass that always adds 'prompt=select_account'
    to the authorization URL, forcing the Google account chooser screen.
    """
    def authorization_url(self, **kwargs):
        """Generates the authorization URL with prompt=select_account."""
        kwargs['prompt'] = 'select_account'
        logging.debug(f"Generating authorization URL with forced prompt: select_account, kwargs: {kwargs}")
        return super().authorization_url(**kwargs)


# --- Dialog for Adding/Editing Channel Profiles ---
# [ This class remains unchanged ]
class ChannelDialog(QDialog):
    def __init__(self, parent=None, profile_data=None):
        super().__init__(parent)
        self.setWindowTitle("Channel Profile Configuration")
        self.setMinimumWidth(500)

        self.profile_data = profile_data or {} # Store existing data if editing

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.channel_name_input = QLineEdit()
        self.channel_name_input.setPlaceholderText("e.g., Reap Learn Tamil, My Gaming Channel")
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter Developer API Key (Optional but Recommended)")

        self.client_secret_layout = QHBoxLayout()
        self.client_secret_label = QLabel("<i>No file selected</i>")
        self.client_secret_label.setWordWrap(True)
        self.client_secret_browse_btn = QPushButton("Browse...")
        self.client_secret_browse_btn.clicked.connect(self.browse_client_secret)
        self.client_secret_layout.addWidget(self.client_secret_label, 1)
        self.client_secret_layout.addWidget(self.client_secret_browse_btn)

        form_layout.addRow("Channel Name:", self.channel_name_input)
        form_layout.addRow("API Key:", self.api_key_input)
        form_layout.addRow("Client Secret JSON:", self.client_secret_layout)

        layout.addLayout(form_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.client_secret_path = self.profile_data.get('client_secret_path', '')
        self.channel_name_input.setText(self.profile_data.get('name', ''))
        self.api_key_input.setText(self.profile_data.get('api_key', ''))
        if self.client_secret_path and os.path.exists(self.client_secret_path):
             self.client_secret_label.setText(os.path.basename(self.client_secret_path))
        else:
             self.client_secret_label.setText("<i>No file selected</i>")


    def browse_client_secret(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(
            self, "Select Client Secret JSON", "", "JSON Files (*.json);;All Files (*)", options=options)
        if filename:
            self.client_secret_path = filename
            self.client_secret_label.setText(os.path.basename(filename))

    def validate_and_accept(self):
        name = self.channel_name_input.text().strip()
        api_key = self.api_key_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Input Error", "Channel Name cannot be empty.")
            return
        if not self.client_secret_path:
            QMessageBox.warning(self, "Input Error", "Client Secret file must be selected.")
            return
        if not os.path.exists(self.client_secret_path):
            QMessageBox.warning(self, "Input Error", f"Client Secret file not found at:\n{self.client_secret_path}")
            return

        self.accept()

    def get_data(self):
        channel_name = self.channel_name_input.text().strip()
        sanitized_name = sanitize_filename(channel_name)
        token_filename = f"{sanitized_name}_token.json"
        # Ensure token_path uses the absolute path of the managed tokens_dir
        token_path = os.path.join(MainWindow.get_tokens_dir_abs(), token_filename)

        return {
            "name": channel_name,
            "api_key": self.api_key_input.text().strip(),
            "client_secret_path": self.client_secret_path,
            "token_path": token_path
        }

# --- Main Application Window ---
class MainWindow(QMainWindow):
    # Class variable to store the absolute path to the tokens directory
    _tokens_dir_abs = os.path.abspath(TOKENS_DIR)

    @classmethod
    def get_tokens_dir_abs(cls):
        """Returns the absolute path to the managed tokens directory."""
        return cls._tokens_dir_abs

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Channel Manager")
        self.setGeometry(100, 100, 1200, 800)
        self.youtube = None
        self.credentials = None
        self.current_channel_profile = None

        self.channel_profiles = {}
        self.config_file = CONFIG_FILE
        # Use the class method to get the consistent absolute path
        self.tokens_dir = self.get_tokens_dir_abs()

        self.rename_playlists = {}
        self.check_playlists = {}
        self.excel_playlists_data = {}
        self.folder_files = []
        self.playlist_titles = []

        self.setup_logging() # Call logging setup first
        self.ensure_dirs()   # Ensure directories exist
        self.load_channel_config() # Load profiles after ensuring dirs

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.auth_tab = QWidget()
        self.rename_tab = QWidget()
        self.check_tab = QWidget()
        self.excel_tab = QWidget()

        self.tabs.addTab(self.auth_tab, "Authentication")
        self.tabs.addTab(self.rename_tab, "Renaming")
        self.tabs.addTab(self.check_tab, "Checking")
        self.tabs.addTab(self.excel_tab, "Generate Excel")

        self.init_auth_tab()
        self.init_rename_tab()
        self.init_check_tab()
        self.init_excel_tab()

    # *** MODIFIED setup_logging METHOD ***
    def setup_logging(self):
        """Sets up logging to file and console, includes library versions."""
        log_format = '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s' # Added line number
        log_file = 'youtube_manager.log'
        try:
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO, # Change to DEBUG for more verbose logs if needed
                format=log_format,
                filemode='w' # Overwrite log each time
            )
            # Add console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(console_handler)

            logging.info("-" * 30)
            logging.info("Application started.")
            logging.info(f"Log file: {os.path.abspath(log_file)}")

            # Log library versions using importlib.metadata and try...except
            libs_to_check = {
                "google-auth": "google.auth",
                "google-auth-oauthlib": "google_auth_oauthlib", # Package name for metadata lookup
                "google-api-python-client": "googleapiclient", # Module name for __version__
                "pandas": "pandas",
                "openpyxl": "openpyxl",
                "PyQt5": "PyQt5"
            }

            for lib_name, import_name in libs_to_check.items():
                try:
                    version = importlib.metadata.version(lib_name)
                    logging.debug(f"{lib_name} version: {version}")
                except importlib.metadata.PackageNotFoundError:
                    # Fallback for googleapiclient which might still use __version__
                    if import_name == "googleapiclient":
                         try:
                             import googleapiclient
                             logging.debug(f"{lib_name} version: {googleapiclient.__version__}")
                         except (ImportError, AttributeError):
                             logging.warning(f"Could not determine version for {lib_name}")
                    else:
                         logging.warning(f"Could not determine version for {lib_name} (Package not found)")
                except Exception as e:
                     logging.warning(f"Error getting version for {lib_name}: {e}")
            logging.info("-" * 30)

        except Exception as e:
            # Fallback logging if setup fails
            print(f"FATAL: Logging setup failed: {e}", file=sys.stderr)


    def ensure_dirs(self):
        """Ensures the tokens directory exists."""
        try:
            os.makedirs(self.tokens_dir, exist_ok=True)
            logging.info(f"Ensured tokens directory exists: {self.tokens_dir}")
        except OSError as e:
            logging.error(f"Could not create tokens directory '{self.tokens_dir}': {e}", exc_info=True)
            QMessageBox.critical(self, "Directory Error", f"Could not create required directory:\n{self.tokens_dir}\n\nPlease check permissions.\n\nError: {e}")
            # Decide if app should exit or try to continue (risky)
            sys.exit(1) # Exit if critical directory cannot be created


    def load_channel_config(self):
        """Loads channel profiles from the JSON config file."""
        # self.tokens_dir is already set to absolute path in __init__ via ensure_dirs
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f: # Use UTF-8
                    self.channel_profiles = json.load(f)
                logging.info(f"Loaded {len(self.channel_profiles)} channel profiles from {self.config_file}")
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from {self.config_file}. Backing up and starting fresh.", exc_info=True)
                backup_file = self.config_file + f".{datetime.datetime.now():%Y%m%d_%H%M%S}.bak"
                try:
                     os.rename(self.config_file, backup_file)
                     QMessageBox.warning(self, "Config Warning", f"{self.config_file} was corrupted.\nIt has been backed up to {backup_file}.\nPlease re-add your channel profiles.")
                except OSError as backup_err:
                     logging.error(f"Could not back up corrupted config file: {backup_err}")
                     QMessageBox.warning(self, "Config Warning", f"{self.config_file} was corrupted and could NOT be backed up.\nPlease re-add your channel profiles.")
                self.channel_profiles = {}
            except Exception as e:
                logging.error(f"Failed to load {self.config_file}: {e}", exc_info=True)
                self.channel_profiles = {}
        else:
            logging.info(f"{self.config_file} not found. Starting with empty configuration.")
            self.channel_profiles = {}

        # Validation and path normalization
        for name, profile in list(self.channel_profiles.items()):
             # Check required keys
             if not all(k in profile for k in ['name', 'api_key', 'client_secret_path', 'token_path']):
                 logging.warning(f"Profile '{name}' is missing required keys. Removing.")
                 del self.channel_profiles[name]
                 continue
             # Ensure token path is within the managed directory
             expected_token_dir = self.tokens_dir
             try:
                 actual_token_dir = os.path.dirname(os.path.abspath(profile['token_path']))
                 if expected_token_dir != actual_token_dir:
                      logging.warning(f"Profile '{name}' token path '{profile['token_path']}' is not in the expected directory '{expected_token_dir}'. Rebuilding path.")
                      sanitized_name = sanitize_filename(profile['name']) # Use name from profile data
                      token_filename = f"{sanitized_name}_token.json"
                      profile['token_path'] = os.path.join(self.tokens_dir, token_filename)
             except Exception as path_e:
                 logging.error(f"Error processing path for profile '{name}': {path_e}. Removing profile.", exc_info=True)
                 del self.channel_profiles[name]
                 continue

             # Check if client secret path exists (warn if not absolute or doesn't exist)
             cs_path = profile['client_secret_path']
             if not os.path.isabs(cs_path):
                 logging.warning(f"Profile '{name}' client secret path is not absolute: '{cs_path}'. May cause issues.")
             # It's better to check existence during authentication attempt rather than load time


    def save_channel_config(self):
        """Saves the current channel profiles to the JSON config file."""
        try:
            # Sort profiles by name before saving for consistency
            sorted_profiles = dict(sorted(self.channel_profiles.items()))
            with open(self.config_file, 'w', encoding='utf-8') as f: # Use UTF-8
                json.dump(sorted_profiles, f, indent=4, ensure_ascii=False)
            logging.info(f"Saved {len(sorted_profiles)} channel profiles to {self.config_file}")
        except Exception as e:
            logging.error(f"Failed to save channel profiles to {self.config_file}: {e}", exc_info=True)
            QMessageBox.critical(self, "Config Error", f"Could not save channel configuration:\n{e}")

    # ----------------------- Tab 1: Authentication -----------------------
    # [ init_auth_tab, populate_channel_table, add/edit/remove_channel ]
    # [ update_channel_status, authenticate_selected_channel ]
    # [ update_inactive_channel_statuses, reset_authentication_state ]
    # [ check_authentication ]
    # [ These methods remain unchanged from the previous corrected version ]
    # [ (Including the use of ForceAccountSelectionFlow) ]
    def init_auth_tab(self):
        layout = QVBoxLayout()

        # --- Channel Configuration Management ---
        config_group = QVBoxLayout()
        config_group.addWidget(QLabel("<h3>Channel Profiles</h3>")) # Use h3 for title

        self.channel_table = QTableWidget()
        self.channel_table.setColumnCount(5)
        self.channel_table.setHorizontalHeaderLabels([
            "Channel Name", "API Key Set?", "Client Secret File", "Token File", "Status"
        ])
        self.channel_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.channel_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.channel_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.channel_table.setSelectionMode(QTableWidget.SingleSelection)
        self.channel_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.channel_table.setMinimumHeight(200) # Ensure table is visible
        config_group.addWidget(self.channel_table)

        button_layout = QHBoxLayout()
        add_btn = QPushButton("Add New Channel")
        edit_btn = QPushButton("Edit Selected")
        remove_btn = QPushButton("Remove Selected")
        add_btn.clicked.connect(self.add_channel)
        edit_btn.clicked.connect(self.edit_channel)
        remove_btn.clicked.connect(self.remove_channel)
        button_layout.addWidget(add_btn)
        button_layout.addWidget(edit_btn)
        button_layout.addWidget(remove_btn)
        button_layout.addStretch()
        config_group.addLayout(button_layout)

        layout.addLayout(config_group)
        layout.addSpacing(20)

        # --- Authentication Action ---
        auth_action_group = QVBoxLayout()
        self.authenticate_btn = QPushButton("Authenticate Selected Channel")
        self.authenticate_btn.setStyleSheet("font-size: 14px; padding: 8px;") # Make button prominent
        self.authenticate_btn.clicked.connect(self.authenticate_selected_channel)
        auth_action_group.addWidget(self.authenticate_btn)

        self.auth_status_label = QLabel("Status: Select a channel and click Authenticate.")
        self.auth_status_label.setStyleSheet("font-weight: bold;")
        auth_action_group.addWidget(self.auth_status_label, alignment=Qt.AlignCenter)

        layout.addLayout(auth_action_group)
        layout.addStretch() # Pushes content to the top

        self.auth_tab.setLayout(layout)

        # Populate the table initially
        self.populate_channel_table()

    def populate_channel_table(self):
        """Fills the channel table with data from self.channel_profiles."""
        self.channel_table.setRowCount(0) # Clear table

        if not self.channel_profiles:
             logging.info("No channel profiles exist to populate the table.")
             return

        self.channel_table.setRowCount(len(self.channel_profiles))
        # Sort profile names alphabetically for consistent display
        sorted_channel_names = sorted(self.channel_profiles.keys())

        for row, name in enumerate(sorted_channel_names):
            profile = self.channel_profiles[name]

            # Data integrity check
            if not all(k in profile for k in ['name', 'api_key', 'client_secret_path', 'token_path']):
                logging.warning(f"Skipping incomplete profile '{name}' during table population.")
                error_item = QTableWidgetItem(f"{name} (Config Error)")
                error_item.setForeground(QColor("red"))
                self.channel_table.setItem(row, 0, error_item)
                self.channel_table.setItem(row, 4, QTableWidgetItem("Config Error"))
                continue

            name_item = QTableWidgetItem(profile.get('name', name)) # Display name from profile data
            name_item.setData(Qt.UserRole, name) # Store the canonical dict key

            api_key_item = QTableWidgetItem("Yes" if profile.get('api_key') else "No")
            api_key_item.setTextAlignment(Qt.AlignCenter)

            cs_path = profile.get('client_secret_path', 'N/A')
            client_secret_item = QTableWidgetItem(os.path.basename(cs_path))
            client_secret_item.setToolTip(cs_path)

            token_path = profile.get('token_path', 'N/A')
            token_file_item = QTableWidgetItem(os.path.basename(token_path))
            token_file_item.setToolTip(token_path)

             # Determine initial status based on token file existence
            status_text = "Needs Auth"
            status_color = QColor("black")
            if os.path.exists(token_path):
                 status_text = "Token Exists"
                 status_color = QColor("darkGray")
                 # Could add a more sophisticated check here later (e.g., token expiry estimate)

            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(status_color)

            self.channel_table.setItem(row, 0, name_item)
            self.channel_table.setItem(row, 1, api_key_item)
            self.channel_table.setItem(row, 2, client_secret_item)
            self.channel_table.setItem(row, 3, token_file_item)
            self.channel_table.setItem(row, 4, status_item)

        self.channel_table.resizeColumnsToContents()
        self.channel_table.resizeRowsToContents()
        # Select first row if exists
        if self.channel_table.rowCount() > 0:
             self.channel_table.selectRow(0)

    def add_channel(self):
        """Opens the dialog to add a new channel profile."""
        dialog = ChannelDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            channel_name = new_data['name']

            if channel_name in self.channel_profiles:
                QMessageBox.warning(self, "Duplicate Name", f"A channel profile named '{channel_name}' already exists.")
                return

            # Ensure the token path is correctly formed using the absolute base dir
            sanitized_name = sanitize_filename(channel_name)
            token_filename = f"{sanitized_name}_token.json"
            new_data['token_path'] = os.path.join(self.tokens_dir, token_filename)


            self.channel_profiles[channel_name] = new_data
            self.save_channel_config()
            self.populate_channel_table() # Repopulate to include the new entry and status
            logging.info(f"Added new channel profile: '{channel_name}' with token path {new_data['token_path']}")
            # Select the newly added row
            for row in range(self.channel_table.rowCount()):
                name_item = self.channel_table.item(row, 0)
                if name_item and name_item.data(Qt.UserRole) == channel_name:
                    self.channel_table.selectRow(row)
                    break

    def edit_channel(self):
        """Opens the dialog to edit the selected channel profile."""
        selected_row = self.channel_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a channel profile to edit.")
            return

        channel_name_item = self.channel_table.item(selected_row, 0)
        if not channel_name_item: return
        original_channel_key = channel_name_item.data(Qt.UserRole) # Get dict key from stored data

        if original_channel_key not in self.channel_profiles:
             QMessageBox.critical(self, "Error", f"Could not find profile data for key '{original_channel_key}'. Config may be out of sync.")
             logging.error(f"Profile data mismatch for key '{original_channel_key}' during edit.")
             return

        profile_to_edit = self.channel_profiles[original_channel_key]

        dialog = ChannelDialog(self, profile_data=profile_to_edit)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_data()
            new_channel_name = updated_data['name'] # This is the potentially new display name

            # Check if the *key* (which is usually the name) needs changing
            new_channel_key = new_channel_name # Assume key is the name for now
            old_token_path = profile_to_edit.get('token_path')


            if new_channel_key != original_channel_key:
                # Check if the new key conflicts with another existing profile
                if new_channel_key in self.channel_profiles:
                     QMessageBox.warning(self, "Duplicate Name", f"Another channel profile named '{new_channel_name}' already exists.")
                     return

                logging.info(f"Renaming channel profile key from '{original_channel_key}' to '{new_channel_key}'")
                # Remove old entry using the old key
                self.channel_profiles.pop(original_channel_key)

                # Regenerate the token path based on the *new* name/key
                sanitized_new_name = sanitize_filename(new_channel_name)
                new_token_filename = f"{sanitized_new_name}_token.json"
                new_token_path = os.path.join(self.tokens_dir, new_token_filename)
                updated_data['token_path'] = new_token_path

                # Optionally rename existing token file
                if old_token_path and new_token_path != old_token_path and os.path.exists(old_token_path):
                    try:
                        os.rename(old_token_path, new_token_path)
                        logging.info(f"Renamed token file from {old_token_path} to {new_token_path}")
                    except OSError as e:
                        logging.error(f"Could not rename token file {old_token_path} to {new_token_path}: {e}")
                        QMessageBox.warning(self, "File Warning", f"Could not rename the token file for the channel.\nYou might need to re-authenticate '{new_channel_name}'.")
            else:
                 # Name/key hasn't changed, but ensure token path is still correct
                 sanitized_name = sanitize_filename(new_channel_name)
                 token_filename = f"{sanitized_name}_token.json"
                 updated_data['token_path'] = os.path.join(self.tokens_dir, token_filename)


            # Add/update the profile using the potentially new key
            self.channel_profiles[new_channel_key] = updated_data
            self.save_channel_config()
            self.populate_channel_table()
            logging.info(f"Updated channel profile: '{new_channel_name}'")
            # Reselect the edited row using the new key
            for row in range(self.channel_table.rowCount()):
                name_item = self.channel_table.item(row, 0)
                if name_item and name_item.data(Qt.UserRole) == new_channel_key:
                    self.channel_table.selectRow(row)
                    break

    def remove_channel(self):
        """Removes the selected channel profile."""
        selected_row = self.channel_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a channel profile to remove.")
            return

        channel_name_item = self.channel_table.item(selected_row, 0)
        if not channel_name_item: return
        channel_key_to_remove = channel_name_item.data(Qt.UserRole) # Get dict key

        if channel_key_to_remove not in self.channel_profiles:
             QMessageBox.critical(self, "Error", f"Could not find profile data for key '{channel_key_to_remove}' to remove.")
             logging.error(f"Profile data mismatch for key '{channel_key_to_remove}' during remove.")
             return

        # Get display name for confirmation message
        display_name = self.channel_profiles[channel_key_to_remove].get('name', channel_key_to_remove)

        reply = QMessageBox.question(self, 'Confirm Deletion',
                                     f"Are you sure you want to remove the channel profile '{display_name}'?\n\n"
                                     f"This will also delete its associated token file (if it exists). This action cannot be undone.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            profile_to_remove = self.channel_profiles.pop(channel_key_to_remove)
            token_path_to_remove = profile_to_remove.get('token_path')

            # Delete the associated token file
            if token_path_to_remove and os.path.exists(token_path_to_remove):
                try:
                    os.remove(token_path_to_remove)
                    logging.info(f"Removed token file: {token_path_to_remove}")
                except OSError as e:
                    logging.error(f"Failed to remove token file '{token_path_to_remove}': {e}", exc_info=True)
                    QMessageBox.warning(self, "File Error", f"Could not delete the token file:\n{token_path_to_remove}\n\nError: {e}")

            self.save_channel_config()
            self.populate_channel_table() # Update table after removal
            logging.info(f"Removed channel profile: '{display_name}' (key: '{channel_key_to_remove}')")

            # Clear current authentication if the removed channel was active
            if self.current_channel_profile and self.current_channel_profile.get('name') == display_name:
                self.reset_authentication_state() # Clear active auth
                self.auth_status_label.setText("Status: Select a channel and click Authenticate.")
                self.auth_status_label.setStyleSheet("font-weight: bold; color: black;")

    def update_channel_status(self, channel_key, status_text, color=QColor("black")):
        """Updates the status column in the table for a specific channel key."""
        for row in range(self.channel_table.rowCount()):
            name_item = self.channel_table.item(row, 0)
            # Check if item exists and its UserRole data matches the target key
            if name_item and name_item.data(Qt.UserRole) == channel_key:
                status_item = self.channel_table.item(row, 4)
                if not status_item:
                     status_item = QTableWidgetItem()
                     self.channel_table.setItem(row, 4, status_item)
                status_item.setText(status_text)
                status_item.setForeground(color)
                break # Found the row, no need to continue loop
        QApplication.processEvents() # Update UI immediately


    def authenticate_selected_channel(self):
        """Authenticates using the profile selected in the table."""
        selected_row = self.channel_table.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "Selection Error", "Please select a channel profile to authenticate.")
            return

        channel_name_item = self.channel_table.item(selected_row, 0)
        if not channel_name_item: return
        channel_key = channel_name_item.data(Qt.UserRole) # Get the dictionary key

        if channel_key not in self.channel_profiles:
             QMessageBox.critical(self, "Error", f"Could not find profile data for '{channel_key}' to authenticate.")
             logging.error(f"Profile data mismatch for key '{channel_key}' during authentication.")
             self.update_channel_status(channel_key, "Config Error", QColor("red"))
             return

        profile = self.channel_profiles[channel_key]
        display_name = profile.get('name', channel_key) # Use display name for messages
        api_key = profile.get('api_key')
        client_secret_file = profile.get('client_secret_path')
        token_file = profile.get('token_path')

        if not client_secret_file or not token_file:
            QMessageBox.critical(self, "Configuration Error", f"Profile '{display_name}' is missing client secret or token path information.")
            logging.error(f"Missing client_secret_path or token_path for '{display_name}' (key: {channel_key})")
            self.update_channel_status(channel_key, "Config Error", QColor("red"))
            return

        if not os.path.exists(client_secret_file):
             QMessageBox.critical(self, "File Error", f"Client secret file not found for '{display_name}':\n{client_secret_file}")
             logging.error(f"Client secret file not found: {client_secret_file}")
             self.update_channel_status(channel_key, "Secret Missing", QColor("red"))
             return

        logging.info(f"Attempting authentication for channel: '{display_name}' (key: {channel_key})")
        self.auth_status_label.setText(f"Status: Authenticating '{display_name}'...")
        self.auth_status_label.setStyleSheet("font-weight: bold; color: orange;")
        self.update_channel_status(channel_key, "Authenticating...", QColor("orange"))
        QApplication.processEvents()

        creds = None
        try:
            # 1. Check if token file exists
            if os.path.exists(token_file):
                logging.info(f"Attempting to load credentials from {token_file}")
                try:
                    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
                    logging.debug(f"Token loaded successfully from {token_file}")
                except ValueError as ve: # Handle specific token format errors
                    logging.warning(f"Invalid token format in {token_file}: {ve}. Will try OAuth flow.", exc_info=True)
                    creds = None
                except Exception as e:
                     logging.warning(f"Could not load token file {token_file}: {e}. Will try OAuth flow.", exc_info=True)
                     creds = None

            # 2. If no valid credentials, try refresh or run OAuth flow
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logging.info(f"Credentials for '{display_name}' expired, attempting refresh.")
                    self.update_channel_status(channel_key, "Refreshing...", QColor("orange"))
                    QApplication.processEvents()
                    try:
                        creds.refresh(Request())
                        logging.info(f"Credentials for '{display_name}' refreshed successfully.")
                        with open(token_file, 'w', encoding='utf-8') as token:
                            token.write(creds.to_json())
                        logging.info(f"Refreshed token saved to {token_file}")
                    except Exception as e:
                        logging.warning(f"Failed to refresh token for '{display_name}': {e}. Need full re-authentication.", exc_info=True)
                        creds = None
                        if os.path.exists(token_file):
                             try: os.remove(token_file)
                             except OSError: logging.warning(f"Could not remove invalid token file {token_file}")

                if not creds or not creds.valid: # Check again
                    logging.info(f"No valid credentials for '{display_name}'. Starting OAuth flow.")
                    self.update_channel_status(channel_key, "User Auth Required", QColor("blue"))
                    QApplication.processEvents()

                    QMessageBox.information(self, "Authentication Required",
                                            f"You need to authorize this application to access your YouTube channel: '{display_name}'.\n\n"
                                            "Your web browser will open to the Google sign-in page.\n\n"
                                            "**IMPORTANT:** Please sign in using the Google account associated with the '{display_name}' YouTube channel. "
                                            "The page should ask you to choose an account.\n\n"
                                            "Click OK to open the browser.")

                    # Use the custom flow class
                    flow = ForceAccountSelectionFlow.from_client_secrets_file(client_secret_file, SCOPES)
                    creds = flow.run_local_server(port=0)

                    logging.info(f"OAuth flow completed for '{display_name}'. Credentials obtained.")
                    with open(token_file, 'w', encoding='utf-8') as token:
                        token.write(creds.to_json())
                    logging.info(f"New token for '{display_name}' saved to {token_file}")

            # 3. Build the YouTube service object
            self.credentials = creds
            if api_key:
                 self.youtube = build('youtube', 'v3', credentials=self.credentials, developerKey=api_key)
                 logging.info(f"YouTube service built for '{display_name}' with credentials and developer key.")
            else:
                 self.youtube = build('youtube', 'v3', credentials=self.credentials)
                 logging.info(f"YouTube service built for '{display_name}' with credentials only.")

            self.current_channel_profile = profile # Store the currently active profile
            self.auth_status_label.setText(f"Status: Authenticated as '{display_name}'")
            self.auth_status_label.setStyleSheet("font-weight: bold; color: green;")
            self.update_channel_status(channel_key, "Authenticated", QColor("green"))
            self.update_inactive_channel_statuses(channel_key)

            QMessageBox.information(self, "Success", f"Authentication successful for channel:\n'{display_name}'!")

        except FileNotFoundError:
             QMessageBox.critical(self, "Error", f"Client secret file not found during authentication for '{display_name}':\n{client_secret_file}")
             logging.exception(f"Client secret file not found during authentication for {display_name}.")
             self.auth_status_label.setText(f"Status: Authentication Failed (File Not Found)")
             self.auth_status_label.setStyleSheet("font-weight: bold; color: red;")
             self.update_channel_status(channel_key, "Secret Missing", QColor("red"))
             self.reset_authentication_state()
        except HttpError as e:
            error_details = f"API Error: {e.resp.status} {e.reason}"
            try:
                content = json.loads(e.content)
                error_details += f"\nDetails: {content.get('error', {}).get('message', 'No details')}"
            except Exception: pass
            QMessageBox.critical(self, "API Error", f"Authentication failed for '{display_name}':\n{error_details}")
            logging.error(f"Authentication failed for {display_name} due to HttpError: {e}", exc_info=True)
            self.auth_status_label.setText(f"Status: Authentication Failed (API Error)")
            self.auth_status_label.setStyleSheet("font-weight: bold; color: red;")
            self.update_channel_status(channel_key, f"API Error ({e.resp.status})", QColor("red"))
            self.reset_authentication_state()
        except Exception as e:
            error_type = type(e).__name__
            QMessageBox.critical(self, "Error", f"Authentication failed for '{display_name}':\n{error_type}: {e}")
            logging.exception(f"Authentication failed for {display_name} with unexpected error.")
            self.auth_status_label.setText(f"Status: Authentication Failed ({error_type})")
            self.auth_status_label.setStyleSheet("font-weight: bold; color: red;")
            self.update_channel_status(channel_key, f"Auth Error ({error_type})", QColor("red"))
            self.reset_authentication_state()

    def update_inactive_channel_statuses(self, active_channel_key):
        """Sets status for all channels *not* currently active."""
        for key in self.channel_profiles:
             if key != active_channel_key:
                  row_profile = self.channel_profiles.get(key)
                  row_token_path = row_profile.get('token_path') if row_profile else None
                  if row_token_path and os.path.exists(row_token_path):
                       self.update_channel_status(key, "Token Exists", QColor("darkGray"))
                  else:
                       self.update_channel_status(key, "Needs Auth", QColor("black"))


    def reset_authentication_state(self):
        """Clears the current authentication details."""
        self.credentials = None
        self.youtube = None
        self.current_channel_profile = None
        logging.info("Authentication state reset.")

    def check_authentication(self):
        """Checks if authenticated and shows a warning if not."""
        if not self.youtube or not self.current_channel_profile:
            QMessageBox.warning(self, "Authentication Required",
                                "Please select a channel profile on the 'Authentication' tab and click 'Authenticate Selected Channel' first.")
            logging.warning("Action attempted without prior authentication or active channel.")
            return False
        logging.info(f"Authentication check passed. Current channel: '{self.current_channel_profile.get('name', 'N/A')}'")
        return True

    # ----------------------- Tab 2: Renaming -----------------------
    # [ init_rename_tab, load_rename_playlist, extract_chapter_sort_key ]
    # [ show_rename_scheme, rename_videos ]
    # [ These methods remain unchanged from the previous corrected version ]
    def init_rename_tab(self):
        layout = QVBoxLayout()

        playlist_layout = QHBoxLayout()
        self.load_rename_playlist_btn = QPushButton("Load Playlists for Current Channel")
        self.load_rename_playlist_btn.clicked.connect(self.load_rename_playlist)
        self.rename_playlist_combo = QComboBox()
        playlist_layout.addWidget(self.load_rename_playlist_btn)
        playlist_layout.addWidget(self.rename_playlist_combo, 1)
        layout.addLayout(playlist_layout)

        self.show_scheme_btn = QPushButton("Load Videos & Show Rename Scheme")
        self.show_scheme_btn.clicked.connect(self.show_rename_scheme)
        layout.addWidget(self.show_scheme_btn)

        self.rename_table = QTableWidget()
        self.rename_table.setColumnCount(3)
        self.rename_table.setHorizontalHeaderLabels(["Original YouTube Title", "Proposed New Title", "Proposed New Description"])
        self.rename_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.rename_table)

        progress_log_layout = QHBoxLayout()
        self.rename_progress_bar = QProgressBar()
        progress_log_layout.addWidget(QLabel("Progress:"))
        progress_log_layout.addWidget(self.rename_progress_bar)
        layout.addLayout(progress_log_layout)

        self.rename_log_window = QTextEdit()
        self.rename_log_window.setReadOnly(True)
        self.rename_log_window.setFixedHeight(150)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.rename_log_window)

        self.rename_btn = QPushButton("Apply Renaming to Selected Playlist Videos")
        self.rename_btn.clicked.connect(self.rename_videos)
        layout.addWidget(self.rename_btn)

        self.rename_tab.setLayout(layout)

    def load_rename_playlist(self, show_messages=True):
        if not self.check_authentication(): return
        channel_name = self.current_channel_profile['name']
        logging.info(f"Loading playlists for Renaming tab (Channel: '{channel_name}').")
        self.rename_log_window.append(f"Loading playlists for '{channel_name}'...")
        QApplication.processEvents()
        try:
            playlists = []
            nextPageToken = None
            page_count = 0
            max_pages = 10 # Limit pages for playlist loading
            while page_count < max_pages:
                page_count += 1
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                items = response.get("items", [])
                playlists.extend(items)
                logging.debug(f"Fetched page {page_count} with {len(items)} playlists for {channel_name}")
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken:
                    break
            if page_count >= max_pages and nextPageToken:
                logging.warning(f"Stopped fetching playlists for {channel_name} after {max_pages} pages. User might have more.")
                if show_messages:
                     QMessageBox.warning(self, "Playlist Limit", f"Loaded first {len(playlists)} playlists. If you have more, they won't be shown.")


            self.rename_playlist_combo.clear()
            self.rename_playlists.clear()
            if playlists:
                sorted_playlists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                for item in sorted_playlists:
                    playlist_id = item["id"]
                    title = item["snippet"]["title"]
                    description = item["snippet"].get("description", "No description")
                    video_count = item["contentDetails"]["itemCount"]
                    display_text = f"{title} ({video_count} videos) - {description[:50]}"
                    self.rename_playlists[display_text] = playlist_id
                    self.rename_playlist_combo.addItem(display_text)
                log_msg = f"Loaded {len(playlists)} playlists into rename dropdown for '{channel_name}'."
                logging.info(log_msg)
                self.rename_log_window.append(log_msg)
                if show_messages:
                    QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists for '{channel_name}'.\nSelect one and click 'Load Videos'.")
            else:
                 log_msg = f"No playlists found for channel '{channel_name}'."
                 logging.info(log_msg)
                 self.rename_log_window.append(log_msg)
                 if show_messages:
                     QMessageBox.information(self, "No Playlists", log_msg)

        except HttpError as e:
            error_msg = f"Failed to load playlists for '{channel_name}': {e}"
            logging.exception(error_msg)
            self.rename_log_window.append(f"<font color='red'>{error_msg}</font>")
            if show_messages: QMessageBox.critical(self, "API Error", error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred loading playlists for '{channel_name}': {e}"
            logging.exception(error_msg)
            self.rename_log_window.append(f"<font color='red'>{error_msg}</font>")
            if show_messages: QMessageBox.critical(self, "Error", error_msg)

    def extract_chapter_sort_key(self, title):
        if not title: return (999, 0, "", "") # Handle empty titles
        title_lower = title.lower()
        # Prioritize exact match for course introduction
        if "course introduction" == title_lower.strip():
            return (-1, 0, "", title) # Introduction first, use original case for tie-break

        # Match "Chapter N[A]" - allows for flexible spacing
        m = re.search(r'chapter\s+(\d+)([A-Za-z]*)', title_lower)
        if m:
            num = int(m.group(1))
            suffix = m.group(2).upper() if m.group(2) else ""
            # Sort headers (no suffix) before parts (with suffix)
            suffix_sort_order = 0 if not suffix else 1
            return (num, suffix_sort_order, suffix, title) # Use original case for tie-break

        # Fallback sorting: Use a high number, keep original case for alphabetical sort
        return (999, 0, "", title)

    def show_rename_scheme(self):
        if not self.check_authentication(): return
        selected_display_text = self.rename_playlist_combo.currentText()
        if not selected_display_text:
            QMessageBox.warning(self, "No Playlist Selected", "Please select a playlist from the dropdown first.")
            return

        playlist_id = self.rename_playlists.get(selected_display_text)
        if not playlist_id:
            QMessageBox.critical(self, "Error", f"Could not find ID for the selected playlist display text:\n'{selected_display_text}'")
            logging.error(f"Could not find playlist ID for display text: {selected_display_text}")
            return

        channel_name = self.current_channel_profile['name']
        logging.info(f"Loading videos for rename scheme (Channel: '{channel_name}', Playlist ID: {playlist_id})")
        self.rename_log_window.clear()
        self.rename_log_window.append(f"Loading videos for playlist: {selected_display_text[:80]}...")
        QApplication.processEvents()

        try:
            videos = []
            nextPageToken = None
            page_count = 0
            max_pages = 20 # Safety break for very long playlists
            while page_count < max_pages:
                 page_count += 1
                 request = self.youtube.playlistItems().list(
                     part="snippet,contentDetails",
                     playlistId=playlist_id,
                     maxResults=50,
                     pageToken=nextPageToken
                 )
                 response = request.execute()
                 items = response.get("items", [])
                 videos.extend(items)
                 logging.debug(f"Fetched page {page_count} with {len(items)} rename video items for playlist {playlist_id}")
                 nextPageToken = response.get("nextPageToken")
                 if not nextPageToken:
                     break
            if page_count >= max_pages and nextPageToken:
                 logging.warning(f"Stopped fetching rename video items for playlist {playlist_id} after {max_pages} pages. Playlist may be truncated.")
                 self.rename_log_window.append(f"<font color='orange'>   Warning: Fetched maximum {max_pages*50} video items. Playlist might be longer.</font>")

            logging.info(f"Fetched {len(videos)} video items from playlist {playlist_id}.")

            # Sort videos using the natural sort key
            try:
                items_to_sort = [v for v in videos if v.get('snippet', {}).get('title')]
                sorted_videos = sorted(items_to_sort, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                logging.info("Videos sorted naturally for renaming.")
            except Exception as e:
                 logging.exception("Error during video sorting for renaming. Using original order.")
                 QMessageBox.warning(self,"Sort Warning", f"Could not sort videos naturally, using API order. Error: {e}")
                 sorted_videos = videos # Fallback

            self.rename_table.setRowCount(0)
            valid_video_count = 0
            rows_data = [] # Collect valid data before setting row count

            for video_item in sorted_videos:
                snippet = video_item.get("snippet", {})
                contentDetails = video_item.get("contentDetails", {})
                video_id = contentDetails.get("videoId")
                original_title = snippet.get("title", "!!! TITLE MISSING !!!")
                position = snippet.get("position", -1)

                if not video_id:
                    logging.warning(f"Skipping item at pos {position} ('{original_title[:50]}...') - missing videoId.")
                    # Optionally add error to log window here
                    continue

                valid_video_count += 1
                # Generate new title/desc
                new_title = original_title
                new_desc = original_title # Default desc to original title

                if "course introduction" in original_title.lower():
                    pass # Keep original title and desc
                else:
                    m = re.match(r'(Chapter\s+\d+[A-Za-z]?)\s*[-–—]?\s*(.*)', original_title, re.IGNORECASE)
                    if m:
                        chapter_part = m.group(1).strip()
                        topic = m.group(2).strip()
                        # Use topic only if it's not empty
                        new_title = f"{chapter_part} - {topic}" if topic else chapter_part
                        if topic: new_desc = topic # Use topic as desc only if it exists

                rows_data.append({
                     "original_title": original_title,
                     "new_title": new_title,
                     "new_desc": new_desc,
                     "video_id": video_id,
                     "position": position
                 })

            # Now populate the table
            self.rename_table.setRowCount(len(rows_data))
            for row, data in enumerate(rows_data):
                title_item = QTableWidgetItem(data["original_title"])
                title_item.setData(Qt.UserRole, data["video_id"])
                title_item.setData(Qt.UserRole + 1, data["position"])
                title_item.setToolTip(f"Video ID: {data['video_id']}\nPlaylist Pos: {data['position']}")
                title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)

                self.rename_table.setItem(row, 0, title_item)
                self.rename_table.setItem(row, 1, QTableWidgetItem(data["new_title"]))
                self.rename_table.setItem(row, 2, QTableWidgetItem(data["new_desc"]))


            self.rename_table.resizeColumnsToContents()
            self.rename_table.resizeRowsToContents()
            self.rename_log_window.append(f"Loaded {valid_video_count} videos with IDs into the table. Review and edit proposed changes before applying.")
            logging.info("Rename scheme table populated.")

        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Failed to load playlist videos: {e}")
            self.rename_log_window.append(f"<font color='red'>Error loading videos: {e}</font>")
            logging.exception(f"Failed to load videos for playlist {playlist_id}.")
        except Exception as e:
             QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")
             self.rename_log_window.append(f"<font color='red'>Unexpected error: {e}</font>")
             logging.exception("Unexpected error showing rename scheme.")

    def rename_videos(self):
        if not self.check_authentication(): return

        row_count = self.rename_table.rowCount()
        if row_count == 0:
            QMessageBox.information(self, "No Videos", "No videos loaded in the table to rename.")
            return

        valid_rows_to_process = []
        for row in range(row_count):
            original_title_item = self.rename_table.item(row, 0)
            if original_title_item and original_title_item.data(Qt.UserRole):
                valid_rows_to_process.append(row)

        if not valid_rows_to_process:
             QMessageBox.information(self, "No Valid Videos", "No videos with valid IDs found in the table to rename (check for errors in loading).")
             return

        num_to_rename = len(valid_rows_to_process)
        channel_name = self.current_channel_profile['name']
        playlist_name = self.rename_playlist_combo.currentText().split(' (')[0]

        reply = QMessageBox.question(self, 'Confirm Rename',
                                     f"Are you sure you want to attempt renaming {num_to_rename} videos for channel '{channel_name}' in playlist '{playlist_name}'?\n\n"
                                     "This action modifies your YouTube videos directly and cannot be undone automatically.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.No:
            logging.info("User cancelled renaming operation.")
            return

        logging.info(f"Starting renaming process for {num_to_rename} videos (Channel: '{channel_name}', Playlist: '{playlist_name}').")
        self.rename_progress_bar.setMaximum(num_to_rename)
        self.rename_progress_bar.setValue(0)
        self.rename_log_window.clear()
        self.rename_log_window.append(f"Starting video renaming for '{playlist_name}'...")
        QApplication.processEvents()

        success_count = 0
        fail_count = 0
        processed_count = 0

        for row_index in valid_rows_to_process:
            processed_count += 1
            video_id = None
            row = row_index # Use row_index in logs for clarity if needed
            try:
                original_title_item = self.rename_table.item(row, 0)
                new_title_item = self.rename_table.item(row, 1)
                new_desc_item = self.rename_table.item(row, 2)

                if not (original_title_item and new_title_item and new_desc_item):
                     logging.warning(f"Row {row+1}: Skipping missing items (internal error).")
                     self.rename_log_window.append(f"Row {row+1}: Skipped (missing data).")
                     fail_count += 1
                     continue

                video_id = original_title_item.data(Qt.UserRole)
                playlist_pos = original_title_item.data(Qt.UserRole + 1)
                original_title_text = original_title_item.text()
                new_title_text = new_title_item.text().strip()
                new_desc_text = new_desc_item.text().strip()

                if not video_id: # Should be caught by filter, but double check
                    logging.warning(f"Row {row+1} (Pos {playlist_pos}): Skipping missing video ID (internal error).")
                    self.rename_log_window.append(f"Row {row+1} (Pos {playlist_pos}): Skipped '{original_title_text[:50]}...' (Missing ID).")
                    fail_count += 1
                    continue

                if not new_title_text:
                    logging.warning(f"Row {row+1} (Pos {playlist_pos}): Skipping ID {video_id} - empty new title.")
                    self.rename_log_window.append(f"Row {row+1} (Pos {playlist_pos}): Skipped '{original_title_text[:50]}...' (Empty New Title).")
                    fail_count += 1
                    continue

                self.rename_log_window.append(f"Processing Row {row+1} (Pos {playlist_pos}, ID: {video_id}) '{original_title_text[:50]}...'")
                QApplication.processEvents()

                video_response = self.youtube.videos().list( part="snippet", id=video_id ).execute()
                if not video_response.get("items"):
                    error_message = f"Failed Row {row+1}: Video {video_id} not found."
                    logging.error(error_message)
                    self.rename_log_window.append(f"<font color='red'>{error_message}</font>")
                    fail_count += 1
                    continue

                current_snippet = video_response["items"][0]["snippet"]
                current_title = current_snippet.get('title', '')
                current_desc = current_snippet.get('description', '')
                current_cat_id = current_snippet.get("categoryId") # Get current category ID

                # ** Crucial Check: Need category ID to update **
                if not current_cat_id:
                     logging.error(f"Failed Row {row+1}: Cannot update video {video_id} - categoryId is missing from current snippet data.")
                     self.rename_log_window.append(f"<font color='red'>Failed Row {row+1} (ID {video_id}): Missing categoryId. Update aborted.</font>")
                     fail_count += 1
                     continue

                title_changed = current_title != new_title_text
                desc_changed = current_desc != new_desc_text

                if not title_changed and not desc_changed:
                    log_message = f"Skipped Row {row+1}: No changes needed for video {video_id} ('{new_title_text[:50]}...')."
                    logging.info(log_message)
                    self.rename_log_window.append(log_message)
                else:
                    snippet_to_update = {
                        "id": video_id,
                        "snippet": {
                            "title": new_title_text,
                            "description": new_desc_text,
                            "categoryId": current_cat_id, # Use the retrieved category ID
                            "tags": current_snippet.get("tags", []),
                        }
                    }
                    if "defaultLanguage" in current_snippet: snippet_to_update["snippet"]["defaultLanguage"] = current_snippet["defaultLanguage"]
                    if "defaultAudioLanguage" in current_snippet: snippet_to_update["snippet"]["defaultAudioLanguage"] = current_snippet["defaultAudioLanguage"]

                    logging.debug(f"Updating video {video_id} with body: {snippet_to_update}")
                    update_request = self.youtube.videos().update( part="snippet", body=snippet_to_update )
                    update_response = update_request.execute()

                    changes = [c for c, changed in [("Title", title_changed), ("Description", desc_changed)] if changed]
                    change_str = " & ".join(changes) if changes else "Metadata"

                    log_message = f"Success Row {row+1}: Updated {change_str} for video {video_id}: '{new_title_text[:50]}...'"
                    logging.info(f"Updated video {video_id}: Title='{new_title_text}', Desc='{new_desc_text[:50]}...'")
                    self.rename_log_window.append(log_message)

                success_count +=1

            except HttpError as e:
                error_message = f"Failed Row {row+1} (ID {video_id}): API Error: {e.resp.status} {e.reason}"
                try: content = json.loads(e.content); details = content.get('error', {}).get('message', ''); error_message += f" - {details}"
                except: pass
                logging.exception(f"API Error updating video at row {row+1} (ID: {video_id})")
                self.rename_log_window.append(f"<font color='red'>{error_message}</font>")
                fail_count += 1
            except Exception as e:
                 error_message = f"Failed Row {row+1} (ID {video_id}): Unexpected error: {type(e).__name__}: {e}"
                 logging.exception(f"Unexpected Error updating video at row {row+1} (ID: {video_id})")
                 self.rename_log_window.append(f"<font color='red'>{error_message}</font>")
                 fail_count += 1
            finally:
                self.rename_progress_bar.setValue(processed_count)
                QApplication.processEvents()

        final_message = f"Renaming process completed for '{playlist_name}'. Processed: {processed_count}, Success: {success_count}, Failed: {fail_count}."
        self.rename_log_window.append(f"\n<b>{final_message}</b>")
        logging.info(final_message)
        QMessageBox.information(self, "Renaming Done", final_message + "\nCheck log window for details.")

    # ----------------------- Tab 3: Checking -----------------------
    # [ init_check_tab, browse_folder, load_folder_names, load_check_playlist ]
    # [ show_check_playlist_names, compare_folder_playlist ]
    # [ These methods remain unchanged from the previous corrected version ]
    def init_check_tab(self):
        layout = QVBoxLayout()
        self.folder_path = None

        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Folder:")
        self.selected_folder_path_label = QLabel("<i>No folder selected</i>")
        self.selected_folder_path_label.setWordWrap(True)
        browse_folder_btn = QPushButton("Browse Folder")
        browse_folder_btn.clicked.connect(self.browse_folder)
        self.load_folder_names_btn = QPushButton("Load Folder Names")
        self.load_folder_names_btn.clicked.connect(self.load_folder_names)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.selected_folder_path_label, 1)
        folder_layout.addWidget(browse_folder_btn)
        folder_layout.addWidget(self.load_folder_names_btn)
        layout.addLayout(folder_layout)

        playlist_layout = QHBoxLayout()
        self.load_check_playlist_btn = QPushButton("Load Playlists for Current Channel")
        self.load_check_playlist_btn.clicked.connect(self.load_check_playlist)
        self.check_playlist_combo = QComboBox()
        self.show_playlist_names_btn = QPushButton("Load Playlist Video Names")
        self.show_playlist_names_btn.clicked.connect(self.show_check_playlist_names)
        playlist_layout.addWidget(self.load_check_playlist_btn)
        playlist_layout.addWidget(self.check_playlist_combo, 1)
        playlist_layout.addWidget(self.show_playlist_names_btn)
        layout.addLayout(playlist_layout)

        self.check_table = QTableWidget()
        self.check_table.setColumnCount(3)
        self.check_table.setHorizontalHeaderLabels(["#", "Folder Filename (No Ext.)", "YouTube Video Title"])
        self.check_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.check_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.check_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.check_table)

        compare_btn = QPushButton("Compare Loaded Folder and Playlist Names")
        compare_btn.clicked.connect(self.compare_folder_playlist)
        layout.addWidget(compare_btn)

        self.check_log_window = QTextEdit()
        self.check_log_window.setReadOnly(True)
        self.check_log_window.setFixedHeight(100)
        layout.addWidget(QLabel("Comparison Log:"))
        layout.addWidget(self.check_log_window)

        self.check_tab.setLayout(layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder Containing Video Files")
        if folder:
            self.folder_path = folder
            self.selected_folder_path_label.setText(folder)
            logging.info(f"Folder selected for checking: {folder}")
            self.folder_files.clear()
            self.check_log_window.append(f"Folder selected: {folder}. Click 'Load Folder Names'.")
            # Clear folder column and reset colors
            for i in range(self.check_table.rowCount()):
                 item = self.check_table.item(i, 1)
                 if item:
                      item.setText("")
                      item.setBackground(QColor("white"))
                 else:
                      self.check_table.setItem(i, 1, QTableWidgetItem(""))

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
            video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')
            files_in_folder = [
                f for f in os.listdir(self.folder_path)
                if os.path.isfile(os.path.join(self.folder_path, f)) and f.lower().endswith(video_extensions)
            ]

            folder_basenames = [os.path.splitext(f)[0] for f in files_in_folder]
            self.folder_files = sorted(folder_basenames, key=self.extract_chapter_sort_key)
            logging.info(f"Found {len(self.folder_files)} video files (basenames) and sorted them.")

            current_playlist_rows = self.check_table.rowCount()
            required_rows = max(current_playlist_rows, len(self.folder_files))
            self.check_table.setRowCount(required_rows)

            for i in range(required_rows):
                # Row number
                num_item = self.check_table.item(i, 0)
                if not num_item:
                    num_item = QTableWidgetItem(str(i + 1))
                    num_item.setTextAlignment(Qt.AlignCenter)
                    self.check_table.setItem(i, 0, num_item)

                # Folder name (Col 1)
                folder_name = self.folder_files[i] if i < len(self.folder_files) else ""
                folder_item = self.check_table.item(i, 1)
                if folder_item:
                    folder_item.setText(folder_name)
                    folder_item.setBackground(QColor("white"))
                else:
                    self.check_table.setItem(i, 1, QTableWidgetItem(folder_name))

                # Ensure playlist item exists (Col 2) and reset color
                playlist_item = self.check_table.item(i, 2)
                if not playlist_item:
                    self.check_table.setItem(i, 2, QTableWidgetItem(""))
                elif i >= len(self.folder_files): # Reset color if row only exists for playlist
                    playlist_item.setBackground(QColor("white"))


            self.check_table.resizeColumnsToContents()
            self.check_table.resizeRowsToContents()
            self.check_log_window.append(f"Successfully loaded {len(self.folder_files)} folder filenames into column 2.")
            QMessageBox.information(self, "Folder Names Loaded", f"Loaded {len(self.folder_files)} video filenames (without extension).")

        except Exception as e:
            QMessageBox.critical(self, "Error Loading Folder Names", f"Failed to read folder contents: {e}")
            self.check_log_window.append(f"<font color='red'>Error loading folder names: {e}</font>")
            logging.exception(f"Failed to load filenames from {self.folder_path}")

    def load_check_playlist(self, show_messages=True):
        if not self.check_authentication(): return
        channel_name = self.current_channel_profile['name']
        logging.info(f"Loading playlists for Checking tab (Channel: '{channel_name}').")
        self.check_log_window.append(f"Loading playlists for '{channel_name}'...")
        QApplication.processEvents()
        try:
            playlists = []
            nextPageToken = None
            page_count = 0
            max_pages = 10 # Limit pages
            while page_count < max_pages:
                page_count += 1
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                items = response.get("items", [])
                playlists.extend(items)
                logging.debug(f"Fetched page {page_count} with {len(items)} check playlists for {channel_name}")
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken: break
            if page_count >= max_pages and nextPageToken:
                 logging.warning(f"Stopped fetching check playlists for {channel_name} after {max_pages} pages.")
                 if show_messages: QMessageBox.warning(self, "Playlist Limit", f"Loaded first {len(playlists)} playlists.")


            self.check_playlist_combo.clear()
            self.check_playlists.clear()
            if playlists:
                sorted_playlists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                for item in sorted_playlists:
                    playlist_id = item["id"]
                    title = item["snippet"]["title"]
                    description = item["snippet"].get("description", "No description")
                    video_count = item["contentDetails"]["itemCount"]
                    display_text = f"{title} ({video_count} videos) - {description[:50]}"
                    self.check_playlists[display_text] = playlist_id
                    self.check_playlist_combo.addItem(display_text)

                log_msg = f"Loaded {len(playlists)} playlists into check dropdown for '{channel_name}'."
                logging.info(log_msg)
                self.check_log_window.append(log_msg)
                if show_messages: QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists for '{channel_name}'.")
            else:
                log_msg = f"No playlists found for channel '{channel_name}'."
                logging.info(log_msg); self.check_log_window.append(log_msg)
                if show_messages: QMessageBox.information(self, "No Playlists", log_msg)

        except HttpError as e:
            error_msg = f"Failed to load playlists for '{channel_name}': {e}"
            logging.exception(error_msg); self.check_log_window.append(f"<font color='red'>{error_msg}</font>")
            if show_messages: QMessageBox.critical(self, "API Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error loading playlists for '{channel_name}': {e}"
            logging.exception(error_msg); self.check_log_window.append(f"<font color='red'>{error_msg}</font>")
            if show_messages: QMessageBox.critical(self, "Error", error_msg)

    def show_check_playlist_names(self):
        if not self.check_authentication(): return
        selected_display_text = self.check_playlist_combo.currentText()
        if not selected_display_text:
            QMessageBox.warning(self, "No Playlist Selected", "Please select a playlist.")
            return

        playlist_id = self.check_playlists.get(selected_display_text)
        if not playlist_id:
            QMessageBox.critical(self, "Error", f"Could not find ID for playlist:\n'{selected_display_text}'")
            logging.error(f"Could not find playlist ID for display text: {selected_display_text}")
            return

        channel_name = self.current_channel_profile['name']
        logging.info(f"Loading video names for checking (Channel: '{channel_name}', Playlist ID: {playlist_id})")
        self.check_log_window.append(f"Loading video names for playlist: {selected_display_text[:80]}...")
        QApplication.processEvents()

        try:
            videos = []
            nextPageToken = None
            page_count = 0
            max_pages = 20 # Safety break
            while page_count < max_pages:
                 page_count += 1
                 request = self.youtube.playlistItems().list(
                     part="snippet", playlistId=playlist_id, maxResults=50, pageToken=nextPageToken
                 )
                 response = request.execute()
                 items = response.get("items", [])
                 videos.extend(items)
                 logging.debug(f"Fetched page {page_count} with {len(items)} check titles for playlist {playlist_id}")
                 nextPageToken = response.get("nextPageToken")
                 if not nextPageToken: break
            if page_count >= max_pages and nextPageToken:
                 logging.warning(f"Stopped fetching check titles for playlist {playlist_id} after {max_pages} pages.")
                 self.check_log_window.append(f"<font color='orange'>   Warning: Fetched maximum {max_pages*50} items.</font>")

            logging.info(f"Fetched {len(videos)} video items from playlist {playlist_id}.")

            try:
                items_with_titles = [v for v in videos if v.get('snippet', {}).get('title')]
                sorted_videos = sorted(items_with_titles, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                self.playlist_titles = [v['snippet']['title'] for v in sorted_videos]
                logging.info("Playlist video titles sorted naturally for checking.")
            except Exception as e:
                 logging.exception("Error sorting playlist titles for checking.")
                 QMessageBox.warning(self,"Sort Warning", f"Could not sort playlist titles naturally: {e}")
                 self.playlist_titles = [v['snippet']['title'] for v in videos if v.get('snippet', {}).get('title')]


            current_folder_rows = self.check_table.rowCount()
            required_rows = max(current_folder_rows, len(self.playlist_titles))
            self.check_table.setRowCount(required_rows)

            for i in range(required_rows):
                # Row number
                num_item = self.check_table.item(i, 0)
                if not num_item:
                    num_item = QTableWidgetItem(str(i + 1)); num_item.setTextAlignment(Qt.AlignCenter)
                    self.check_table.setItem(i, 0, num_item)

                # Ensure folder item exists (Col 1) and reset color
                folder_item = self.check_table.item(i, 1)
                if not folder_item:
                     self.check_table.setItem(i, 1, QTableWidgetItem(""))
                elif i >= len(self.playlist_titles): # Reset color if row only exists for folder
                    folder_item.setBackground(QColor("white"))

                # Playlist title (Col 2)
                playlist_title = self.playlist_titles[i] if i < len(self.playlist_titles) else ""
                playlist_item = self.check_table.item(i, 2)
                if playlist_item:
                     playlist_item.setText(playlist_title)
                     playlist_item.setBackground(QColor("white"))
                else:
                     self.check_table.setItem(i, 2, QTableWidgetItem(playlist_title))


            self.check_table.resizeColumnsToContents(); self.check_table.resizeRowsToContents()
            self.check_log_window.append(f"Successfully loaded {len(self.playlist_titles)} playlist video titles into column 3.")
            QMessageBox.information(self, "Playlist Names Loaded", f"Loaded {len(self.playlist_titles)} video titles.")

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
        if row_count == 0 or (not self.folder_files and not self.playlist_titles):
            QMessageBox.information(self, "Nothing to Compare", "Please load folder names and/or playlist names first.")
            return

        logging.info("Starting comparison between loaded folder names and playlist titles.")
        self.check_log_window.setText("Comparing folder filenames (Col 2) and playlist titles (Col 3)...")
        QApplication.processEvents()

        folder_list = self.folder_files
        playlist_list = self.playlist_titles
        messages = []
        discrepancy_found = False

        # Reset table colors
        for r in range(row_count):
            for c in range(1, 3):
                item = self.check_table.item(r, c)
                if item: item.setBackground(QColor("white"))

        # 1. Compare counts
        len_f, len_p = len(folder_list), len(playlist_list)
        if len_f != len_p:
            msg = f"Item Count Mismatch: Folder={len_f}, Playlist={len_p}."
            messages.append(f"<font color='orange'><b>{msg}</b></font>")
            logging.warning(msg); discrepancy_found = True
        else:
             messages.append(f"Item Count Match: {len_f} items.")
             logging.info(f"Item counts match: {len_f}")

        # 2. Check for duplicates in playlist (case-insensitive)
        seen = {}; first_occurrence_map = {}
        for title in playlist_list:
             title_lower = title.lower()
             seen[title_lower] = seen.get(title_lower, 0) + 1
             if title_lower not in first_occurrence_map: first_occurrence_map[title_lower] = title
        duplicates = [f"'{first_occurrence_map[tl]}' ({c} times)" for tl, c in seen.items() if c > 1]
        if duplicates:
            msg = "Duplicate Playlist Titles: " + ", ".join(duplicates)
            messages.append(f"<font color='orange'>{msg}</font>")
            logging.warning(msg); discrepancy_found = True

        # 3. Compare line-by-line
        mismatch_details = []
        max_compare_rows = self.check_table.rowCount()
        mismatch_color = QColor(255, 192, 203) # Light Pink

        for i in range(max_compare_rows):
            folder_item = self.check_table.item(i, 1)
            playlist_item = self.check_table.item(i, 2)
            f_text = folder_item.text().strip() if folder_item else ""
            p_text = playlist_item.text().strip() if playlist_item else ""

            # Consider mismatch if strings differ OR if one is present and the other isn't
            # within the bounds of the shorter list length if counts mismatched.
            is_mismatch = f_text != p_text
            report_mismatch = False
            if is_mismatch:
                if i < min(len_f, len_p): # Both lists have an item at this index
                     report_mismatch = True
                elif i < max(len_f, len_p): # One list has an item, the other doesn't
                     report_mismatch = True # Report missing item

            if report_mismatch:
                mismatch_msg = f"Row {i+1}: Folder='{f_text}' != Playlist='{p_text}'"
                mismatch_details.append(mismatch_msg)
                logging.warning(f"Mismatch Row {i+1}: Folder='{f_text}', Playlist='{p_text}'")
                discrepancy_found = True
                if folder_item: folder_item.setBackground(mismatch_color)
                if playlist_item: playlist_item.setBackground(mismatch_color)

        if mismatch_details:
             messages.append("<font color='red'><b>Line-by-Line Mismatches Found:</b></font><br>" + "<br>".join(mismatch_details))

        # Display results
        self.check_log_window.append("\n--- Comparison Results ---")
        self.check_log_window.append("<br>".join(messages))

        if discrepancy_found:
            summary = "Comparison finished: Discrepancies found!"
            QMessageBox.warning(self, "Comparison Issues Found", summary + "\nCheck log and highlighted rows.")
            logging.warning("Comparison finished with discrepancies.")
        else:
            summary = "Comparison finished: No discrepancies found."
            QMessageBox.information(self, "Comparison OK", summary + "\nFolder names and playlist titles appear to match.")
            logging.info("Comparison finished successfully.")

        self.check_log_window.verticalScrollBar().setValue(self.check_log_window.verticalScrollBar().maximum())

    # ----------------------- Tab 4: Generate Excel -----------------------
    # [ init_excel_tab, load_excel_playlists, video_sort_key ]
    # [ generate_selected_excels, generate_excel_for_playlist ]
    # [ These methods remain unchanged from the previous corrected version ]
    def init_excel_tab(self):
        layout = QVBoxLayout()

        load_layout = QHBoxLayout()
        self.load_excel_playlists_btn = QPushButton("Load Playlists for Current Channel")
        self.load_excel_playlists_btn.clicked.connect(self.load_excel_playlists)
        load_layout.addWidget(self.load_excel_playlists_btn)
        load_layout.addStretch()
        layout.addLayout(load_layout)

        self.excel_playlist_table = QTableWidget()
        self.excel_playlist_table.setColumnCount(2)
        self.excel_playlist_table.setHorizontalHeaderLabels(["Select", "Playlist Details (Name, Desc, Count)"])
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.excel_playlist_table.verticalHeader().setVisible(False)
        self.excel_playlist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(QLabel("Select Playlists to Generate Excel For:"))
        layout.addWidget(self.excel_playlist_table)

        progress_log_layout = QHBoxLayout()
        self.excel_progress_bar = QProgressBar()
        progress_log_layout.addWidget(QLabel("Progress:"))
        progress_log_layout.addWidget(self.excel_progress_bar)
        layout.addLayout(progress_log_layout)

        self.excel_log_window = QTextEdit()
        self.excel_log_window.setReadOnly(True)
        self.excel_log_window.setFixedHeight(200)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.excel_log_window)

        self.generate_excel_btn = QPushButton("Generate Excel File(s) for Selected Playlists")
        self.generate_excel_btn.clicked.connect(self.generate_selected_excels)
        layout.addWidget(self.generate_excel_btn)

        self.excel_tab.setLayout(layout)

    def load_excel_playlists(self, show_messages=True):
        if not self.check_authentication(): return
        channel_name = self.current_channel_profile['name']
        logging.info(f"Loading playlists for Excel tab (Channel: '{channel_name}').")
        self.excel_log_window.setText(f"Loading playlists for '{channel_name}'...")
        QApplication.processEvents()

        try:
            playlists = []
            nextPageToken = None
            page_count = 0
            max_pages = 10 # Limit pages
            while page_count < max_pages:
                page_count += 1
                request = self.youtube.playlists().list(
                    part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextPageToken)
                response = request.execute()
                items = response.get("items", [])
                playlists.extend(items)
                logging.debug(f"Fetched page {page_count} with {len(items)} excel playlists for {channel_name}")
                nextPageToken = response.get("nextPageToken")
                if not nextPageToken: break
            if page_count >= max_pages and nextPageToken:
                 logging.warning(f"Stopped fetching excel playlists for {channel_name} after {max_pages} pages.")
                 if show_messages: QMessageBox.warning(self, "Playlist Limit", f"Loaded first {len(playlists)} playlists.")


            self.excel_playlist_table.setRowCount(0)
            self.excel_playlists_data.clear()

            if playlists:
                sorted_playlists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                self.excel_playlist_table.setRowCount(len(sorted_playlists))

                for row, item in enumerate(sorted_playlists):
                    playlist_id = item["id"]
                    snippet = item["snippet"]
                    title = snippet["title"]
                    description = snippet.get("description", "")
                    video_count = item["contentDetails"]["itemCount"]

                    # Use playlist ID as key for guaranteed uniqueness
                    self.excel_playlists_data[playlist_id] = {
                        'id': playlist_id, 'title': title, 'description': description, 'row': row
                    }

                    # Checkbox (Col 0)
                    checkbox = QCheckBox()
                    checkbox_widget = QWidget(); cb_layout = QHBoxLayout(checkbox_widget)
                    cb_layout.addWidget(checkbox); cb_layout.setAlignment(Qt.AlignCenter)
                    cb_layout.setContentsMargins(0,0,0,0)
                    self.excel_playlist_table.setCellWidget(row, 0, checkbox_widget)

                    # Details (Col 1)
                    desc_preview = description[:100].replace('\n', ' ') + ('...' if len(description)>100 else '')
                    display_text = f"{title}\nDesc: {desc_preview}\n({video_count} videos)"
                    details_item = QTableWidgetItem(display_text)
                    details_item.setToolTip(f"ID: {playlist_id}\nTitle: {title}\nVideos: {video_count}\nDesc: {description}")
                    details_item.setData(Qt.UserRole, playlist_id) # Store ID for retrieval
                    self.excel_playlist_table.setItem(row, 1, details_item)

                self.excel_playlist_table.resizeRowsToContents()
                log_msg = f"Loaded {len(playlists)} playlists for '{channel_name}'. Select to generate Excel."
                self.excel_log_window.append(log_msg)
                logging.info(f"Loaded {len(playlists)} excel playlists for '{channel_name}'.")
                if show_messages: QMessageBox.information(self, "Playlists Loaded", f"Found {len(playlists)} playlists for '{channel_name}'.")
            else:
                 log_msg = f"No playlists found for channel '{channel_name}'."
                 logging.info(log_msg); self.excel_log_window.append(log_msg)
                 if show_messages: QMessageBox.information(self, "No Playlists", log_msg)

        except HttpError as e:
            error_msg = f"Failed to load excel playlists for '{channel_name}': {e}"
            logging.exception(error_msg); self.excel_log_window.append(f"<font color='red'>API Error: {e}</font>")
            if show_messages: QMessageBox.critical(self, "API Error", error_msg)
        except Exception as e:
            error_msg = f"Unexpected error loading excel playlists for '{channel_name}': {e}"
            logging.exception(error_msg); self.excel_log_window.append(f"<font color='red'>Error: {e}</font>")
            if show_messages: QMessageBox.critical(self, "Error", error_msg)

    # Use consistent sort key
    def video_sort_key(self, title):
        return self.extract_chapter_sort_key(title)

    def generate_selected_excels(self):
        if not self.check_authentication(): return
        channel_name = self.current_channel_profile['name']

        selected_playlists_to_process = []
        for row in range(self.excel_playlist_table.rowCount()):
            checkbox_widget = self.excel_playlist_table.cellWidget(row, 0)
            checkbox = checkbox_widget.findChild(QCheckBox) if checkbox_widget else None
            details_item = self.excel_playlist_table.item(row, 1)

            if checkbox and checkbox.isChecked() and details_item:
                playlist_id = details_item.data(Qt.UserRole) # Retrieve ID from item data
                if playlist_id and playlist_id in self.excel_playlists_data:
                     selected_playlists_to_process.append(self.excel_playlists_data[playlist_id])
                else:
                     logging.warning(f"Excel Gen: Checkbox checked row {row}, but bad ID ('{playlist_id}') or data missing.")
                     self.excel_log_window.append(f"<font color='orange'>Warning: Cannot process playlist at row {row+1}. Data error?</font>")

        if not selected_playlists_to_process:
             QMessageBox.warning(self, "No Selection", "Please select at least one playlist using the checkboxes.")
             return

        # Create dated output folder specific to the channel
        try:
            today_str = datetime.datetime.now().strftime("%d_%m_%y")
            sanitized_channel_name = sanitize_filename(channel_name, replace_spaces=True)
            output_folder_name = f"{sanitized_channel_name}_{today_str}_Excel"
            script_dir = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(script_dir, output_folder_name)
            os.makedirs(output_dir, exist_ok=True)
            logging.info(f"Ensured output directory exists: {output_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Folder Creation Error", f"Could not create output directory '{output_folder_name}': {e}")
            logging.exception("Failed to create output directory."); return

        total_selected = len(selected_playlists_to_process)
        self.excel_progress_bar.setMaximum(total_selected); self.excel_progress_bar.setValue(0)
        self.excel_log_window.clear()
        self.excel_log_window.append(f"Starting Excel generation for {total_selected} playlist(s) from '{channel_name}'...")
        self.excel_log_window.append(f"Output folder: {output_dir}")
        QApplication.processEvents()

        success_count, fail_count = 0, 0
        for i, playlist_data in enumerate(selected_playlists_to_process):
            playlist_id = playlist_data.get('id')
            playlist_title = playlist_data.get('title', 'UNKNOWN_TITLE')
            playlist_description = playlist_data.get('description', '')

            if not playlist_id:
                 fail_count += 1; logging.error(f"Skipping '{playlist_title}' - missing ID.")
                 self.excel_log_window.append(f"<font color='red'>--> Failed: Missing ID for '{playlist_title}'.</font>")
                 self.excel_progress_bar.setValue(i + 1); continue

            self.excel_log_window.append(f"\nProcessing {i+1}/{total_selected}: '{playlist_title}' (ID: {playlist_id})")
            QApplication.processEvents()

            try:
                self.generate_excel_for_playlist(playlist_id, playlist_title, playlist_description, output_dir)
                self.excel_log_window.append(f"--> OK: Generated Excel for '{playlist_title}'.")
                logging.info(f"OK: Generated Excel for {playlist_id} ('{playlist_title}')")
                success_count += 1
            except HttpError as e:
                fail_count += 1; error_details = f"{e.resp.status} {e.reason}";
                try: content = json.loads(e.content); details = content.get('error', {}).get('message', ''); error_details += f" - {details}"
                except: pass
                error_msg = f"--> FAIL (API Error) for '{playlist_title}': {error_details}"
                self.excel_log_window.append(f"<font color='red'>{error_msg}</font>")
                logging.exception(f"API Error generating Excel for {playlist_id}: {playlist_title}")
            except ValueError as e:
                 fail_count += 1; error_msg = f"--> FAIL for '{playlist_title}': {e}"
                 self.excel_log_window.append(f"<font color='red'>{error_msg}</font>")
                 logging.error(f"ValueError generating Excel for {playlist_id} ('{playlist_title}'): {e}")
            except Exception as e:
                fail_count += 1; error_msg = f"--> FAIL (Error) for '{playlist_title}': {type(e).__name__}: {e}"
                self.excel_log_window.append(f"<font color='red'>{error_msg}</font>")
                logging.exception(f"Unexpected Error generating Excel for {playlist_id}: {playlist_title}")
            finally:
                 self.excel_progress_bar.setValue(i + 1); QApplication.processEvents()

        final_message = f"Excel generation finished for '{channel_name}'. Success: {success_count}, Failed: {fail_count}."
        self.excel_log_window.append(f"\n<b>{final_message}</b>")
        logging.info(final_message)
        QMessageBox.information(self, "Excel Generation Done", final_message + f"\nFiles saved in: {output_dir}")
        # Open output folder
        try:
            if sys.platform == 'win32': os.startfile(output_dir)
            else: import subprocess; subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', output_dir], check=True)
        except Exception as e: logging.warning(f"Could not open output folder '{output_dir}': {e}")

    def generate_excel_for_playlist(self, playlist_id, playlist_title, playlist_description, output_dir):
        """Fetches videos, sorts them, extracts data, and saves to an Excel file."""
        logging.info(f"Generating Excel for Playlist ID: {playlist_id}, Title: '{playlist_title}'")

        # 1. Parse Code/Lang from Title
        course_code, language_code = "UNKNOWN", "UNKNOWN"
        match = re.match(r'PL_([^_]+(?:_[^_]+)*)_([a-zA-Z0-9]+)', playlist_title, re.IGNORECASE)
        if match: course_code, language_code = match.group(1), match.group(2); logging.info(f"Parsed Codes: '{course_code}', '{language_code}' from '{playlist_title}'")
        else: logging.warning(f"Title '{playlist_title}' != PL_CourseCode_LangCode format."); self.excel_log_window.append(f"<font color='orange'>   Warn: Title '{playlist_title}' doesn't match format.</font>")

        # 2. Construct Filename
        sanitized_desc = sanitize_filename(playlist_description if playlist_description else "NoDesc", True)
        sanitized_title = sanitize_filename(playlist_title, True)
        max_len = 80; combined_name = f"{sanitized_desc}_{sanitized_title}"
        excel_filename = (combined_name[:max_len] + '...' if len(combined_name) > max_len else combined_name) + ".xlsx"
        excel_filepath = os.path.join(output_dir, excel_filename)
        logging.info(f"Target Excel path: {excel_filepath}")

        # 3. Fetch all items
        all_video_items = []; nextPageToken = None
        self.excel_log_window.append("   Fetching video details..."); QApplication.processEvents()
        page_count, max_pages = 0, 20
        while page_count < max_pages:
            page_count += 1
            request = self.youtube.playlistItems().list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=50, pageToken=nextPageToken)
            response = request.execute(); items = response.get("items", [])
            all_video_items.extend(items); logging.debug(f"Fetched page {page_count} ({len(items)} items) for excel playlist {playlist_id}")
            nextPageToken = response.get("nextPageToken");
            if not nextPageToken: break
        if page_count >= max_pages and nextPageToken: logging.warning(f"Max pages reached fetching excel items for {playlist_id}."); self.excel_log_window.append(f"<font color='orange'>   Warn: Fetched max {max_pages*50} items.</font>")
        logging.info(f"Fetched {len(all_video_items)} total items for playlist {playlist_id}."); self.excel_log_window.append(f"   Fetched {len(all_video_items)} items.")

        # 4. Sort items
        try:
            items_to_sort = [item for item in all_video_items if item.get("snippet", {}).get("title")]
            sorted_video_items = sorted(items_to_sort, key=lambda item: self.video_sort_key(item["snippet"]["title"]))
            logging.info("Excel items sorted."); self.excel_log_window.append("   Videos sorted.")
        except Exception as e:
            logging.exception("Error sorting excel items."); self.excel_log_window.append(f"<font color='orange'>   Warn: Sort failed ({e}). Using API order.</font>")
            sorted_video_items = all_video_items

        # 5. Process sorted items
        excel_data = []; current_chapter_name = ""; order_in_chapter = 0; processed_video_ids = set()
        for item in sorted_video_items:
            snippet = item.get("snippet", {}); contentDetails = item.get("contentDetails", {})
            video_id = contentDetails.get("videoId"); video_title = snippet.get("title", "!!! MISSING !!!")
            video_description = snippet.get("description", ""); position = snippet.get("position", -1)

            if not video_id: logging.warning(f"Excel: Skip pos {position} ('{video_title[:50]}...') - no ID."); continue
            if video_id in processed_video_ids: logging.warning(f"Excel: Skip duplicate ID {video_id} ('{video_title[:50]}...')"); continue
            processed_video_ids.add(video_id)

            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            chapter_name_for_excel = ""; order_no = 0
            sort_key = self.video_sort_key(video_title) # Tuple: (group, subsort, suffix, title)

            if sort_key[0] == -1: # Intro
                chapter_name_for_excel = "Course Introduction"; order_no = 0; current_chapter_name = "Introduction"; order_in_chapter = 0
            elif sort_key[0] == 999: # Fallback
                 logging.warning(f"Excel: Title '{video_title}' uses fallback sort."); self.excel_log_window.append(f"<font color='orange'>   Warn: Title '{video_title[:50]}...' not standard format.</font>")
                 chapter_name_for_excel = current_chapter_name if current_chapter_name and current_chapter_name != "Introduction" else "Unknown Chapter Content"
                 order_in_chapter += 1; order_no = order_in_chapter
            else: # Chapter Header or Part
                is_header = sort_key[1] == 0 # Check subsort index
                if is_header:
                    current_chapter_name = video_title; chapter_name_for_excel = current_chapter_name; order_no = 0; order_in_chapter = 0
                else: # Part
                    if not current_chapter_name or current_chapter_name == "Introduction":
                         logging.warning(f"Excel: Part '{video_title}' found before header."); self.excel_log_window.append(f"<font color='orange'>   Warn: Part '{video_title[:30]}...' before header.</font>")
                         chapter_name_for_excel = "Unknown Chapter"
                         if current_chapter_name == "Introduction": order_in_chapter = 0
                    else: chapter_name_for_excel = current_chapter_name
                    order_in_chapter += 1; order_no = order_in_chapter

            excel_data.append({
                'CourseCode': course_code, 'Chapter Name': chapter_name_for_excel, 'Youtubeurl': youtube_url,
                'Video Title': video_title, 'Video Description': video_description,
                'OrderNo in Chapter': order_no, 'Language code': language_code
            })

        # 6. Create DataFrame and save
        if not excel_data:
             logging.warning(f"No valid data for playlist {playlist_id}. Skipping '{excel_filename}'.")
             self.excel_log_window.append("<font color='orange'>   Warn: No valid video data found.</font>")
             raise ValueError("No valid video data found to create Excel file.")

        df = pd.DataFrame(excel_data)
        df = df[['CourseCode', 'Chapter Name', 'Youtubeurl', 'Video Title', 'Video Description', 'OrderNo in Chapter', 'Language code']]
        logging.info(f"Saving {len(df)} rows to {excel_filepath}"); self.excel_log_window.append(f"   Processed {len(df)} items. Saving: {excel_filename}"); QApplication.processEvents()
        try:
            df.to_excel(excel_filepath, index=False, engine='openpyxl')
            logging.info(f"Saved: {excel_filepath}")
        except Exception as e:
             logging.exception(f"Error saving to Excel: {excel_filepath}")
             raise IOError(f"Failed to save Excel file {excel_filename}: {e}") from e


# --- Main Execution ---
if __name__ == '__main__':
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    try: app.setStyle("Fusion")
    except Exception as e: logging.warning(f"Could not apply Fusion style: {e}")

    # Ensure critical directories exist *before* MainWindow init attempts logging/config load
    try:
        os.makedirs(MainWindow.get_tokens_dir_abs(), exist_ok=True)
    except Exception as dir_e:
         print(f"FATAL ERROR: Cannot create required directory {MainWindow.get_tokens_dir_abs()}. Error: {dir_e}", file=sys.stderr)
         # Show a simple message box if possible, then exit
         try:
             temp_app = QApplication.instance() # Check if app exists
             if not temp_app: temp_app = QApplication(sys.argv) # Create minimal app for message box
             QMessageBox.critical(None, "Fatal Error", f"Could not create required directory:\n{MainWindow.get_tokens_dir_abs()}\n\nPlease check permissions.\n\nError: {dir_e}")
         except:
             pass # If even message box fails, just exit
         sys.exit(1)


    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

# --- END OF FILE youtube_manager.py ---