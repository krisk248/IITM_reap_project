# --- START OF FILE youtube_manager.py ---

import sys
import os
import re
import logging
import datetime
import json
import pandas as pd
import importlib.metadata  # For getting package versions
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
from google_auth_oauthlib.flow import InstalledAppFlow  # Import the base class
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# --- Constants ---
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
CONFIG_FILE = "channel_config.json"
TOKENS_DIR = "tokens"  # Subdirectory for token files

# --- Helper function to sanitize filenames ---
def sanitize_filename(name, replace_spaces=True):
    """Removes characters that are invalid in filenames/paths."""
    if not name:
        return "untitled"
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip()
    if replace_spaces:
        name = re.sub(r'\s+', '_', name)
    if re.match(r'^\.+$', name) or name.upper() in ['CON', 'PRN', 'AUX', 'NUL', 
                                                     'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 
                                                     'COM6', 'COM7', 'COM8', 'COM9', 
                                                     'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 
                                                     'LPT6', 'LPT7', 'LPT8', 'LPT9']:
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
class ChannelDialog(QDialog):
    def __init__(self, parent=None, profile_data=None):
        super().__init__(parent)
        self.setWindowTitle("Channel Profile Configuration")
        self.setMinimumWidth(500)

        self.profile_data = profile_data or {}  # Store existing data if editing

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

        # Populate fields if editing
        self.client_secret_path = self.profile_data.get('client_secret_path', '')
        self.channel_name_input.setText(self.profile_data.get('name', ''))
        self.api_key_input.setText(self.profile_data.get('api_key', ''))
        if self.client_secret_path and os.path.exists(self.client_secret_path):
            self.client_secret_label.setText(os.path.basename(self.client_secret_path))
        else:
            if self.client_secret_path:
                logging.warning(f"Client secret file path '{self.client_secret_path}' exists in config but file not found.")
                self.client_secret_path = ''
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

        self.accept()  # Close dialog successfully

    def get_data(self):
        # Called after validation, so paths should be valid
        channel_name = self.channel_name_input.text().strip()
        sanitized_name = sanitize_filename(channel_name)
        token_filename = f"{sanitized_name}_token.json"
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
        self.current_channel_profile = None  # Track the currently authenticated profile dict

        # Channel Profile Management
        self.channel_profiles = {}  # { 'dict_key': { 'name': display_name, 'api_key': ..., ... } }
        self.config_file = CONFIG_FILE
        self.tokens_dir = self.get_tokens_dir_abs()

        # Dictionaries for other tabs
        self.rename_playlists = {}  # { display_text: playlist_id }
        self.check_playlists = {}   # { display_text: playlist_id }
        self.excel_playlists_data = {}  # { playlist_id: { 'id': ..., 'title': ..., ... } }
        self.folder_files = []      # List of folder basenames for checking tab
        self.playlist_titles = []   # List of playlist titles for checking tab

        self.setup_logging()  # Call logging setup first
        self.ensure_dirs()    # Ensure directories exist
        self.load_channel_config()  # Load profiles after ensuring dirs

        # Setup UI Tabs
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

        # Initialize Tab UIs
        self.init_auth_tab()
        self.init_rename_tab()
        self.init_check_tab()
        self.init_excel_tab()

    def setup_logging(self):
        """Sets up logging to file and console, includes library versions."""
        log_format = '%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
        log_file = 'youtube_manager.log'
        try:
            logging.basicConfig(
                filename=log_file,
                level=logging.INFO,  # Use INFO, change to DEBUG for troubleshooting
                format=log_format,
                filemode='w',  # Overwrite log each time
                encoding='utf-8'
            )
            # Add console handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(logging.Formatter(log_format))
            logging.getLogger().addHandler(console_handler)

            logging.info("-" * 30)
            logging.info("Application started.")
            logging.info(f"Log file: {os.path.abspath(log_file)}")
            logging.info(f"Python Version: {sys.version}")
            logging.info(f"Platform: {sys.platform}")

            libs_to_check = {
                "google-auth": "google.auth",
                "google-auth-oauthlib": "google_auth_oauthlib",
                "google-api-python-client": "googleapiclient",
                "pandas": "pandas",
                "openpyxl": "openpyxl",
                "PyQt5": "PyQt5"
            }
            versions_found = []
            for lib_name, import_name in libs_to_check.items():
                try:
                    version = importlib.metadata.version(lib_name)
                    versions_found.append(f"{lib_name}=={version}")
                except importlib.metadata.PackageNotFoundError:
                    if import_name == "googleapiclient":
                        try:
                            import googleapiclient
                            versions_found.append(f"{lib_name}=={googleapiclient.__version__}")
                        except (ImportError, AttributeError):
                            logging.warning(f"Could not determine version for {lib_name}")
                    else:
                        logging.warning(f"Could not determine version for {lib_name} (Package not found)")
                except Exception as e:
                    logging.warning(f"Error getting version for {lib_name}: {e}")
            logging.debug(f"Library versions: {', '.join(versions_found)}")
            logging.info("-" * 30)

        except Exception as e:
            print(f"FATAL: Logging setup failed: {e}", file=sys.stderr)

    def ensure_dirs(self):
        """Ensures the tokens directory exists."""
        try:
            os.makedirs(self.tokens_dir, exist_ok=True)
            logging.info(f"Ensured tokens directory exists: {self.tokens_dir}")
        except OSError as e:
            logging.error(f"Could not create tokens directory '{self.tokens_dir}': {e}", exc_info=True)
            QMessageBox.critical(self, "Directory Error",
                                 f"Could not create required directory:\n{self.tokens_dir}\n\nPlease check permissions.\n\nError: {e}")
            sys.exit(1)

    def load_channel_config(self):
        """Loads channel profiles from the JSON config file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.channel_profiles = json.load(f)
                logging.info(f"Loaded {len(self.channel_profiles)} channel profiles from {self.config_file}")
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from {self.config_file}. Backing up and starting fresh.", exc_info=True)
                backup_file = self.config_file + f".{datetime.datetime.now():%Y%m%d_%H%M%S}.bak"
                try:
                    os.rename(self.config_file, backup_file)
                    QMessageBox.warning(self, "Config Warning",
                                        f"{self.config_file} corrupted.\nBacked up to {backup_file}.\nPlease re-add profiles.")
                except OSError as backup_err:
                    logging.error(f"Could not back up corrupted config: {backup_err}")
                    QMessageBox.warning(self, "Config Warning",
                                        f"{self.config_file} corrupted & backup failed.\nPlease re-add profiles.")
                self.channel_profiles = {}
            except Exception as e:
                logging.error(f"Failed to load {self.config_file}: {e}", exc_info=True)
                self.channel_profiles = {}
        else:
            logging.info(f"{self.config_file} not found. Starting empty.")
            self.channel_profiles = {}

        keys_to_remove = []
        for key, profile in self.channel_profiles.items():
            required_keys = ['name', 'api_key', 'client_secret_path', 'token_path']
            if not all(k in profile for k in required_keys):
                logging.warning(f"Profile '{key}' missing required keys. Marking for removal.")
                keys_to_remove.append(key)
                continue
            try:
                stored_name = profile.get('name', key)
                sanitized_name = sanitize_filename(stored_name)
                correct_token_filename = f"{sanitized_name}_token.json"
                correct_token_path = os.path.join(self.tokens_dir, correct_token_filename)
                if profile.get('token_path') != correct_token_path:
                    logging.warning(f"Profile '{key}' token path corrected: '{profile.get('token_path')}' -> '{correct_token_path}'")
                    profile['token_path'] = correct_token_path
            except Exception as path_e:
                logging.error(f"Error processing path for profile '{key}': {path_e}. Marking for removal.", exc_info=True)
                keys_to_remove.append(key)
                continue
            cs_path = profile['client_secret_path']
            if not os.path.isabs(cs_path):
                logging.warning(f"Profile '{key}' client secret path is relative: '{cs_path}'.")

        if keys_to_remove:
            logging.info(f"Removing {len(keys_to_remove)} invalid profiles: {', '.join(keys_to_remove)}")
            for key in keys_to_remove:
                del self.channel_profiles[key]
            self.save_channel_config()

    def save_channel_config(self):
        """Saves the current channel profiles to the JSON config file."""
        try:
            sorted_profiles = dict(sorted(self.channel_profiles.items(), key=lambda item: item[1].get('name', item[0])))
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(sorted_profiles, f, indent=4, ensure_ascii=False)
            logging.info(f"Saved {len(sorted_profiles)} channel profiles to {self.config_file}")
        except Exception as e:
            logging.error(f"Failed save profiles to {self.config_file}: {e}", exc_info=True)
            QMessageBox.critical(self, "Config Error", f"Could not save channel configuration:\n{e}")

    # ----------------------- Tab 1: Authentication UI & Logic -----------------------
    def init_auth_tab(self):
        layout = QVBoxLayout()
        config_group = QVBoxLayout()
        config_group.addWidget(QLabel("<h3>Channel Profiles</h3>"))

        self.channel_table = QTableWidget()
        self.channel_table.setColumnCount(5)
        self.channel_table.setHorizontalHeaderLabels(["Channel Name", "API Key?", "Client Secret", "Token File", "Status"])
        self.channel_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.channel_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.channel_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.channel_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.channel_table.setSelectionMode(QTableWidget.SingleSelection)
        self.channel_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.channel_table.setMinimumHeight(200)
        config_group.addWidget(self.channel_table)

        button_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        edit_btn = QPushButton("Edit")
        remove_btn = QPushButton("Remove")
        add_btn.setToolTip("Add a new channel profile")
        edit_btn.setToolTip("Edit the selected channel profile")
        remove_btn.setToolTip("Remove the selected channel profile")
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

        auth_action_group = QVBoxLayout()
        self.authenticate_btn = QPushButton("Authenticate Selected Channel")
        self.authenticate_btn.setStyleSheet("font-size: 14px; padding: 8px;")
        self.authenticate_btn.clicked.connect(self.authenticate_selected_channel)
        auth_action_group.addWidget(self.authenticate_btn)

        self.auth_status_label = QLabel("Status: Select a channel and click Authenticate.")
        self.auth_status_label.setStyleSheet("font-weight: bold;")
        auth_action_group.addWidget(self.auth_status_label, alignment=Qt.AlignCenter)

        layout.addLayout(auth_action_group)
        layout.addStretch()
        self.auth_tab.setLayout(layout)
        self.populate_channel_table()

    def populate_channel_table(self):
        """Fills the channel table with data from self.channel_profiles."""
        self.channel_table.setRowCount(0)
        if not self.channel_profiles:
            logging.info("No profiles to show.")
            return
        sorted_items = sorted(self.channel_profiles.items(), key=lambda item: item[1].get('name', item[0]))
        self.channel_table.setRowCount(len(sorted_items))
        for row, (key, profile) in enumerate(sorted_items):
            display_name = profile.get('name', key)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.UserRole, key)
            api_key_item = QTableWidgetItem("Yes" if profile.get('api_key') else "No")
            api_key_item.setTextAlignment(Qt.AlignCenter)
            cs_path = profile.get('client_secret_path', 'N/A')
            cs_item = QTableWidgetItem(os.path.basename(cs_path))
            cs_item.setToolTip(cs_path)
            token_path = profile.get('token_path', 'N/A')
            tk_item = QTableWidgetItem(os.path.basename(token_path))
            tk_item.setToolTip(token_path)
            status_txt, status_clr = "Needs Auth", QColor("black")
            if os.path.exists(token_path):
                status_txt, status_clr = "Token Exists", QColor("darkGray")
            if self.current_channel_profile and self.current_channel_profile.get('token_path') == token_path:
                status_txt, status_clr = "Authenticated", QColor("green")
            status_item = QTableWidgetItem(status_txt)
            status_item.setForeground(status_clr)
            self.channel_table.setItem(row, 0, name_item)
            self.channel_table.setItem(row, 1, api_key_item)
            self.channel_table.setItem(row, 2, cs_item)
            self.channel_table.setItem(row, 3, tk_item)
            self.channel_table.setItem(row, 4, status_item)
        self.channel_table.resizeColumnsToContents()
        self.channel_table.resizeRowsToContents()
        if self.channel_table.rowCount() > 0:
            self.channel_table.selectRow(0)

    def add_channel(self):
        """Opens the dialog to add a new channel profile."""
        dialog = ChannelDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_data = dialog.get_data()
            channel_key = new_data['name']
            if channel_key in self.channel_profiles:
                QMessageBox.warning(self, "Duplicate Name", f"Profile '{channel_key}' already exists.")
                return
            self.channel_profiles[channel_key] = new_data
            self.save_channel_config()
            self.populate_channel_table()
            logging.info(f"Added profile: '{channel_key}'")
            for row in range(self.channel_table.rowCount()):
                item = self.channel_table.item(row, 0)
                if item and item.data(Qt.UserRole) == channel_key:
                    self.channel_table.selectRow(row)
                    break

    def edit_channel(self):
        """Opens the dialog to edit the selected channel profile."""
        sel_row = self.channel_table.currentRow()
        if sel_row < 0:
            QMessageBox.warning(self, "Selection Error", "Select profile to edit.")
            return
        item0 = self.channel_table.item(sel_row, 0)
        if not item0:
            return
        orig_key = item0.data(Qt.UserRole)
        if orig_key not in self.channel_profiles:
            QMessageBox.critical(self, "Error", f"Profile data missing '{orig_key}'.")
            logging.error(f"Profile mismatch edit: '{orig_key}'.")
            return
        profile_edit = self.channel_profiles[orig_key]
        dialog = ChannelDialog(self, profile_data=profile_edit)
        if dialog.exec_() == QDialog.Accepted:
            updated_data = dialog.get_data()
            new_key = updated_data['name']
            old_token = profile_edit.get('token_path')
            new_token = updated_data['token_path']
            if new_key != orig_key:
                if new_key in self.channel_profiles:
                    QMessageBox.warning(self, "Duplicate Name", f"Profile '{new_key}' exists.")
                    return
                logging.info(f"Renaming profile key '{orig_key}' -> '{new_key}'")
                self.channel_profiles.pop(orig_key)
                if old_token and new_token != old_token and os.path.exists(old_token):
                    try:
                        os.rename(old_token, new_token)
                        logging.info("Renamed token file.")
                    except OSError as e:
                        logging.error(f"Rename token failed {old_token}: {e}")
                        QMessageBox.warning(self, "File Warning", "Rename token failed.")
            self.channel_profiles[new_key] = updated_data
            self.save_channel_config()
            self.populate_channel_table()
            logging.info(f"Updated profile: '{new_key}'")
            for row in range(self.channel_table.rowCount()):
                item = self.channel_table.item(row, 0)
                if item and item.data(Qt.UserRole) == new_key:
                    self.channel_table.selectRow(row)
                    break

    def remove_channel(self):
        """Removes the selected channel profile."""
        sel_row = self.channel_table.currentRow()
        if sel_row < 0:
            QMessageBox.warning(self, "Selection Error", "Select profile to remove.")
            return
        item0 = self.channel_table.item(sel_row, 0)
        if not item0:
            return
        key_remove = item0.data(Qt.UserRole)
        if key_remove not in self.channel_profiles:
            QMessageBox.critical(self, "Error", f"Profile data missing '{key_remove}'.")
            logging.error(f"Profile mismatch remove: '{key_remove}'.")
            return
        disp_name = self.channel_profiles[key_remove].get('name', key_remove)
        reply = QMessageBox.question(self, 'Confirm Deletion',
                                     f"Remove profile '{disp_name}'?\nToken file also deleted.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            profile_remove = self.channel_profiles.pop(key_remove)
            token_remove = profile_remove.get('token_path')
            if token_remove and os.path.exists(token_remove):
                try:
                    os.remove(token_remove)
                    logging.info(f"Removed token: {token_remove}")
                except OSError as e:
                    logging.error(f"Remove token failed '{token_remove}': {e}", exc_info=True)
                    QMessageBox.warning(self, "File Error", f"Delete token failed:\n{token_remove}\n{e}")
            self.save_channel_config()
            self.populate_channel_table()
            logging.info(f"Removed profile: '{disp_name}' (key: '{key_remove}')")
            if self.current_channel_profile and self.current_channel_profile.get('name') == disp_name:
                self.reset_authentication_state()
                self.auth_status_label.setText("Status: Select & Authenticate.")
                self.auth_status_label.setStyleSheet("font-weight:bold;color:black;")

    def update_channel_status(self, channel_key, status_text, color=QColor("black")):
        """Updates the status column in the table for a specific channel key."""
        for row in range(self.channel_table.rowCount()):
            item = self.channel_table.item(row, 0)
            if item and item.data(Qt.UserRole) == channel_key:
                status_item = self.channel_table.item(row, 4)
                if not status_item:
                    status_item = QTableWidgetItem()
                    self.channel_table.setItem(row, 4, status_item)
                status_item.setText(status_text)
                status_item.setForeground(color)
                break
        QApplication.processEvents()

    def authenticate_selected_channel(self):
        """Authenticates using the profile selected in the table."""
        sel_row = self.channel_table.currentRow()
        if sel_row < 0:
            QMessageBox.warning(self, "Selection Error", "Select profile.")
            return
        item0 = self.channel_table.item(sel_row, 0)
        if not item0:
            return
        channel_key = item0.data(Qt.UserRole)
        if channel_key not in self.channel_profiles:
            QMessageBox.critical(self, "Error", f"Profile data missing '{channel_key}'.")
            logging.error(f"Auth mismatch: '{channel_key}'.")
            self.update_channel_status(channel_key, "Config Error", QColor("red"))
            return
        profile = self.channel_profiles[channel_key]
        disp_name = profile.get('name', channel_key)
        api_key, cs_file, tk_file = profile.get('api_key'), profile.get('client_secret_path'), profile.get('token_path')
        if not cs_file or not tk_file:
            QMessageBox.critical(self, "Config Error", f"Profile '{disp_name}' lacks paths.")
            logging.error(f"Paths missing for {disp_name}")
            self.update_channel_status(channel_key, "Config Error", QColor("red"))
            return
        if not os.path.exists(cs_file):
            QMessageBox.critical(self, "File Error", f"Secret file missing for '{disp_name}':\n{cs_file}")
            logging.error(f"Secret missing: {cs_file}")
            self.update_channel_status(channel_key, "Secret Missing", QColor("red"))
            return

        logging.info(f"Auth attempt: '{disp_name}'")
        self.auth_status_label.setText(f"Status: Authenticating '{disp_name}'...")
        self.auth_status_label.setStyleSheet("font-weight:bold;color:orange;")
        self.update_channel_status(channel_key, "Authenticating...", QColor("orange"))
        QApplication.processEvents()
        creds = None
        try:
            if os.path.exists(tk_file):
                logging.info(f"Loading token: {tk_file}")
                try:
                    creds = Credentials.from_authorized_user_file(tk_file, SCOPES)
                    logging.debug("Token loaded.")
                except Exception as e:
                    logging.warning(f"Load token failed {tk_file}: {e}", exc_info=True)
                    creds = None
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logging.info(f"Refreshing: '{disp_name}'.")
                    self.update_channel_status(channel_key, "Refreshing...", QColor("orange"))
                    QApplication.processEvents()
                    try:
                        creds.refresh(Request())
                        logging.info(f"Refreshed: '{disp_name}'.")
                    except Exception as e:
                        logging.warning(f"Refresh failed '{disp_name}': {e}. Need re-auth.", exc_info=True)
                        creds = None
                    if creds:
                        with open(tk_file, 'w', encoding='utf-8') as token:
                            token.write(creds.to_json())
                        logging.info(f"Saved refreshed: {tk_file}")
                    elif os.path.exists(tk_file):
                        try:
                            os.remove(tk_file)
                            logging.info(f"Removed invalid: {tk_file}")
                        except OSError:
                            pass
                if not creds or not creds.valid:
                    logging.info(f"OAuth flow needed for '{disp_name}'.")
                    self.update_channel_status(channel_key, "User Auth Required", QColor("blue"))
                    QApplication.processEvents()
                    QMessageBox.information(self, "Authentication Required",
                                            f"Authorize access for: '{disp_name}'.\nBrowser will open.", QMessageBox.Ok)
                    flow = ForceAccountSelectionFlow.from_client_secrets_file(cs_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    logging.info(f"OAuth done for '{disp_name}'.")
                    with open(tk_file, 'w', encoding='utf-8') as token:
                        token.write(creds.to_json())
                    logging.info(f"New token saved: {tk_file}")

            self.credentials = creds
            build_args = {'credentials': creds}
            if api_key:
                build_args['developerKey'] = api_key
            self.youtube = build('youtube', 'v3', **build_args)
            logging.info(f"Service built for '{disp_name}'.")
            self.current_channel_profile = profile
            self.auth_status_label.setText(f"Status: Authenticated as '{disp_name}'")
            self.auth_status_label.setStyleSheet("font-weight:bold;color:green;")
            self.update_channel_status(channel_key, "Authenticated", QColor("green"))
            self.update_inactive_channel_statuses(channel_key)
            QMessageBox.information(self, "Success", f"Authenticated as:\n'{disp_name}'!")
        except HttpError as e:
            error_d = f"API Error: {e.resp.status} {e.reason}"
            try:
                c = json.loads(e.content)
                error_d += f"\n{c.get('error', {}).get('message', '')}"
            except Exception:
                pass
            QMessageBox.critical(self, "API Error", f"Auth failed '{disp_name}':\n{error_d}")
            logging.error(f"Auth HttpError {disp_name}: {e}", exc_info=True)
            self.auth_status_label.setText("Status: Auth Failed (API)")
            self.auth_status_label.setStyleSheet("font-weight:bold;color:red;")
            self.update_channel_status(channel_key, f"API Error ({e.resp.status})", QColor("red"))
            self.reset_authentication_state()
        except Exception as e:
            error_t = type(e).__name__
            QMessageBox.critical(self, "Error", f"Auth failed '{disp_name}':\n{error_t}: {e}")
            logging.exception(f"Auth Exception {disp_name}.")
            self.auth_status_label.setText(f"Status: Auth Failed ({error_t})")
            self.auth_status_label.setStyleSheet("font-weight:bold;color:red;")
            self.update_channel_status(channel_key, f"Auth Error ({error_t})", QColor("red"))
            self.reset_authentication_state()

    def update_inactive_channel_statuses(self, active_channel_key):
        """Sets status for all channels not currently active."""
        for key, profile in self.channel_profiles.items():
            if key != active_channel_key:
                tk_path = profile.get('token_path')
                if tk_path and os.path.exists(tk_path):
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
            QMessageBox.warning(self, "Not Authenticated", "Select & authenticate a channel first.")
            logging.warning("Blocked: Not authenticated.")
            return False
        logging.debug(f"Auth OK. Channel: '{self.current_channel_profile.get('name', 'N/A')}'")
        return True

    # --- SORT KEY FUNCTION (Used across tabs) ---
    def extract_chapter_sort_key(self, title):
        """
        Generates a sort key tuple (group, num, subsort, suffix, original_title)
        Handles 'Course Introduction', 'Chapter N', 'Chapter NA'.
        """
        if not title:
            return (999, 0, "", "")
        title_lower_stripped = title.lower().strip()
        if "course introduction" in title_lower_stripped:
            return (-1, 0, "", title)
        m = re.search(r'chapter\s+(\d+)([A-Za-z]*)', title_lower_stripped)
        if m:
            num, suffix = int(m.group(1)), m.group(2).upper()
            subsort = 0 if not suffix else 1
            return (num, subsort, suffix, title)
        return (999, 0, "", title)

    # ----------------------- Tab 2: Renaming UI & Logic -----------------------
    def init_rename_tab(self):
        layout = QVBoxLayout()
        playlist_layout = QHBoxLayout()
        self.load_rename_playlist_btn = QPushButton("Load Playlists")
        self.load_rename_playlist_btn.setToolTip("Load playlists for current channel")
        self.load_rename_playlist_btn.clicked.connect(self.load_rename_playlist)
        self.rename_playlist_combo = QComboBox()
        playlist_layout.addWidget(self.load_rename_playlist_btn)
        playlist_layout.addWidget(self.rename_playlist_combo, 1)
        layout.addLayout(playlist_layout)
        self.show_scheme_btn = QPushButton("Load Videos & Show Scheme")
        self.show_scheme_btn.setToolTip("Load videos and generate proposed renames")
        self.show_scheme_btn.clicked.connect(self.show_rename_scheme)
        layout.addWidget(self.show_scheme_btn)
        self.rename_table = QTableWidget()
        self.rename_table.setColumnCount(3)
        self.rename_table.setHorizontalHeaderLabels(["Original Title", "Proposed Title", "Proposed Desc"])
        self.rename_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.rename_table)
        progress_layout = QHBoxLayout()
        self.rename_progress_bar = QProgressBar()
        progress_layout.addWidget(QLabel("Progress:"))
        progress_layout.addWidget(self.rename_progress_bar)
        layout.addLayout(progress_layout)
        self.rename_log_window = QTextEdit()
        self.rename_log_window.setReadOnly(True)
        self.rename_log_window.setFixedHeight(150)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.rename_log_window)
        self.rename_btn = QPushButton("Apply Renaming")
        self.rename_btn.setToolTip("Apply proposed changes")
        self.rename_btn.clicked.connect(self.rename_videos)
        layout.addWidget(self.rename_btn)
        self.rename_tab.setLayout(layout)

    def load_rename_playlist(self, show_messages=True):
        if not self.check_authentication():
            return
        chan_name = self.current_channel_profile['name']
        logging.info(f"Load Rename lists: '{chan_name}'.")
        self.rename_log_window.append(f"Loading lists for '{chan_name}'...")
        QApplication.processEvents()
        try:
            playlists = []
            nextToken = None
            pc, max_p = 0, 10
            while pc < max_p:
                pc += 1
                req = self.youtube.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextToken)
                resp = req.execute()
                items = resp.get("items", [])
                playlists.extend(items)
                logging.debug(f"Page {pc} ({len(items)}) rename lists {chan_name}")
                nextToken = resp.get("nextPageToken")
                if not nextToken:
                    break
            if pc >= max_p and nextToken:
                logging.warning(f"Max pages rename lists {chan_name}.")
                if show_messages:
                    QMessageBox.warning(self, "Limit", f"Loaded {len(playlists)} lists.")
            self.rename_playlist_combo.clear()
            self.rename_playlists.clear()
            if playlists:
                sorted_lists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                for item in sorted_lists:
                    pid = item["id"]
                    snip = item["snippet"]
                    cd = item["contentDetails"]
                    title = snip["title"]
                    desc = snip.get("description", "")
                    cnt = cd["itemCount"]
                    disp = f"{title} ({cnt} videos) - {desc[:50]}"
                    self.rename_playlists[disp] = pid
                    self.rename_playlist_combo.addItem(disp)
                msg = f"Loaded {len(playlists)} lists for '{chan_name}'."
                logging.info(msg)
                self.rename_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "Loaded", f"Found {len(playlists)} playlists.")
            else:
                msg = f"No lists found for '{chan_name}'."
                logging.info(msg)
                self.rename_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "No Playlists", msg)
        except HttpError as e:
            err = f"API Error load rename lists: {e}"
            logging.exception(err)
            self.rename_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "API Error", err)
        except Exception as e:
            err = f"Error load rename lists: {e}"
            logging.exception(err)
            self.rename_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "Error", err)

    def show_rename_scheme(self):
        if not self.check_authentication():
            return
        sel_txt = self.rename_playlist_combo.currentText()
        if not sel_txt:
            QMessageBox.warning(self, "No Selection", "Select playlist.")
            return
        pid = self.rename_playlists.get(sel_txt)
        if not pid:
            QMessageBox.critical(self, "Error", f"ID missing for:\n'{sel_txt}'")
            logging.error(f"ID missing for {sel_txt}")
            return
        chan_name = self.current_channel_profile['name']
        logging.info(f"Load scheme: '{chan_name}', PID: {pid}")
        self.rename_log_window.clear()
        self.rename_log_window.append(f"Loading videos: {sel_txt[:80]}...")
        QApplication.processEvents()
        try:
            videos = []
            nextToken = None
            pc, max_p = 0, 20
            while pc < max_p:
                pc += 1
                req = self.youtube.playlistItems().list(part="snippet,contentDetails", playlistId=pid, maxResults=50, pageToken=nextToken)
                resp = req.execute()
                items = resp.get("items", [])
                videos.extend(items)
                logging.debug(f"Page {pc} ({len(items)}) rename items {pid}")
                nextToken = resp.get("nextPageToken")
                if not nextToken:
                    break
            if pc >= max_p and nextToken:
                logging.warning(f"Max pages rename items {pid}.")
                self.rename_log_window.append(f"<font color='orange'>Warn: Fetched max {max_p*50}.</font>")
            logging.info(f"Fetched {len(videos)} items from {pid}.")
            try:
                items_sort = [v for v in videos if v.get('snippet', {}).get('title')]
                sorted_videos = sorted(items_sort, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                logging.info("Rename items sorted.")
            except Exception as e:
                logging.exception("Rename sort failed.")
                QMessageBox.warning(self, "Sort Warn", f"Sort fail: {e}")
                sorted_videos = videos
            self.rename_table.setRowCount(0)
            rows_data = []
            for vid_item in sorted_videos:
                snip = vid_item.get("snippet", {})
                cd = vid_item.get("contentDetails", {})
                vid = cd.get("videoId")
                orig_t = snip.get("title", "!!! MISSING !!!")
                pos = snip.get("position", -1)
                new_t, new_d = orig_t, orig_t
                if "course introduction" in orig_t.lower().strip():
                    pass
                else:
                    m = re.match(r'(Chapter\s+\d+[A-Za-z]?)\s*[-–—]?\s*(.*)', orig_t, re.IGNORECASE)
                    if m:
                        ch = m.group(1).strip()
                        tpc = m.group(2).strip()
                        new_t = f"{ch} - {tpc}" if tpc else ch
                        new_d = tpc if tpc else orig_t
                rows_data.append({"orig_title": orig_t, "new_title": new_t, "new_desc": new_d, "vid": vid, "pos": pos})
            self.rename_table.setRowCount(len(rows_data))
            for row, data in enumerate(rows_data):
                i0 = QTableWidgetItem(data["orig_title"])
                i0.setData(Qt.UserRole, data["vid"])
                i0.setData(Qt.UserRole+1, data["pos"])
                i0.setToolTip(f"ID: {data['vid']}\nPos: {data['pos']}")
                i0.setFlags(i0.flags() & ~Qt.ItemIsEditable)
                self.rename_table.setItem(row, 0, i0)
                self.rename_table.setItem(row, 1, QTableWidgetItem(data["new_title"]))
                self.rename_table.setItem(row, 2, QTableWidgetItem(data["new_desc"]))
            self.rename_table.resizeColumnsToContents()
            self.rename_table.resizeRowsToContents()
            self.rename_log_window.append(f"Loaded {len(rows_data)} videos.")
            logging.info("Rename scheme populated.")
        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Load videos failed: {e}")
            self.rename_log_window.append(f"<font color='red'>Load fail: {e}</font>")
            logging.exception(f"Load vid fail {pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error: {e}")
            self.rename_log_window.append(f"<font color='red'>Error: {e}</font>")
            logging.exception("Error show rename.")

    def rename_videos(self):
        if not self.check_authentication():
            return
        row_cnt = self.rename_table.rowCount()
        if row_cnt == 0:
            QMessageBox.information(self, "No Videos", "Load first.")
            return
        valid_rows = [r for r in range(row_cnt) if self.rename_table.item(r, 0) and self.rename_table.item(r, 0).data(Qt.UserRole)]
        if not valid_rows:
            QMessageBox.information(self, "No Valid Videos", "No IDs found.")
            return
        num_rename = len(valid_rows)
        chan_name = self.current_channel_profile['name']
        p_name = self.rename_playlist_combo.currentText().split(' (')[0]
        reply = QMessageBox.question(self, 'Confirm', f"Rename {num_rename} for '{chan_name}'/'{p_name}'?", QMessageBox.Yes|QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No:
            logging.info("User cancel rename.")
            return
        logging.info(f"Start rename: {num_rename} ('{chan_name}'/'{p_name}').")
        self.rename_progress_bar.setMaximum(num_rename)
        self.rename_progress_bar.setValue(0)
        self.rename_log_window.clear()
        self.rename_log_window.append(f"Renaming '{p_name}'...")
        QApplication.processEvents()
        ok_cnt, fail_cnt, proc_cnt = 0, 0, 0
        for row_idx in valid_rows:
            proc_cnt += 1
            vid = None
            row = row_idx
            try:
                i0 = self.rename_table.item(row, 0)
                i1 = self.rename_table.item(row, 1)
                i2 = self.rename_table.item(row, 2)
                if not (i0 and i1 and i2):
                    logging.warning(f"Row {row+1}: Skip miss item.")
                    fail_cnt += 1
                    continue
                vid = i0.data(Qt.UserRole)
                pos = i0.data(Qt.UserRole+1)
                orig_t = i0.text()
                new_t = i1.text().strip()
                new_d = i2.text().strip()
                if not vid:
                    logging.warning(f"Row {row+1}({pos}): Skip miss ID.")
                    fail_cnt += 1
                    continue
                if not new_t:
                    logging.warning(f"Row {row+1}({pos}): Skip {vid} empty title.")
                    fail_cnt += 1
                    continue
                self.rename_log_window.append(f"Proc {row+1}(ID:{vid}) '{orig_t[:50]}...'")
                QApplication.processEvents()
                vid_resp = self.youtube.videos().list(part="snippet", id=vid).execute()
                if not vid_resp.get("items"):
                    logging.error(f"FAIL R{row+1}: Vid {vid} not found.")
                    self.rename_log_window.append(f"<font color='red'>FAIL R{row+1}: Vid {vid} not found.</font>")
                    fail_cnt += 1
                    continue
                curr_snip = vid_resp["items"][0]["snippet"]
                curr_t = curr_snip.get('title', '')
                curr_d = curr_snip.get('description', '')
                curr_cat = curr_snip.get("categoryId")
                if not curr_cat:
                    logging.error(f"FAIL R{row+1}: Vid {vid} no catId.")
                    self.rename_log_window.append(f"<font color='red'>FAIL R{row+1}({vid}): No catId!</font>")
                    fail_cnt += 1
                    continue
                t_chg, d_chg = curr_t != new_t, curr_d != new_d
                if not t_chg and not d_chg:
                    msg = f"Skip R{row+1}: No change {vid}."
                    logging.info(msg)
                    self.rename_log_window.append(msg)
                else:
                    snip_upd = {"id": vid, "snippet": {"title": new_t, "description": new_d, "categoryId": curr_cat, "tags": curr_snip.get("tags", [])}}
                    if "defaultLanguage" in curr_snip:
                        snip_upd["snippet"]["defaultLanguage"] = curr_snip["defaultLanguage"]
                    if "defaultAudioLanguage" in curr_snip:
                        snip_upd["snippet"]["defaultAudioLanguage"] = curr_snip["defaultAudioLanguage"]
                    logging.debug(f"Update body: {snip_upd}")
                    req = self.youtube.videos().update(part="snippet", body=snip_upd)
                    resp = req.execute()
                    chgs = [c for c, chgd in [("T", t_chg), ("D", d_chg)] if chgd]
                    chg_s = "&".join(chgs) if chgs else "Meta"
                    msg = f"OK R{row+1}: Upd {chg_s} {vid}:'{new_t[:50]}...'"
                    logging.info(f"Upd {vid}")
                    self.rename_log_window.append(msg)
                ok_cnt += 1
            except HttpError as e:
                err_msg = f"FAIL R{row+1}({vid}): API Err {e.resp.status}"
                try:
                    c = json.loads(e.content)
                    err_msg += f"-{c.get('error', {}).get('message', '')}"
                except Exception:
                    pass
                logging.exception(f"API Err upd R{row+1}")
                self.rename_log_window.append(f"<font color='red'>{err_msg}</font>")
                fail_cnt += 1
            except Exception as e:
                err_msg = f"FAIL R{row+1}({vid}): Err {type(e).__name__}"
                logging.exception(f"Err upd R{row+1}")
                self.rename_log_window.append(f"<font color='red'>{err_msg}: {e}</font>")
                fail_cnt += 1
            finally:
                self.rename_progress_bar.setValue(proc_cnt)
                QApplication.processEvents()
        final = f"Rename done '{p_name}'. Proc:{proc_cnt}, OK:{ok_cnt}, Fail:{fail_cnt}."
        self.rename_log_window.append(f"\n<b>{final}</b>")
        logging.info(final)
        QMessageBox.information(self, "Rename Done", final)

    # ----------------------- Tab 3: Checking UI & Logic -----------------------
    def init_check_tab(self):
        layout = QVBoxLayout()
        self.folder_path = None
        folder_layout = QHBoxLayout()
        self.selected_folder_path_label = QLabel("<i>No folder selected</i>")
        self.selected_folder_path_label.setWordWrap(True)
        browse_folder_btn = QPushButton("Browse Folder")
        browse_folder_btn.clicked.connect(self.browse_folder)
        self.load_folder_names_btn = QPushButton("Load Folder Names")
        self.load_folder_names_btn.clicked.connect(self.load_folder_names)
        folder_layout.addWidget(QLabel("Folder:"))
        folder_layout.addWidget(self.selected_folder_path_label, 1)
        folder_layout.addWidget(browse_folder_btn)
        folder_layout.addWidget(self.load_folder_names_btn)
        layout.addLayout(folder_layout)
        playlist_layout = QHBoxLayout()
        self.load_check_playlist_btn = QPushButton("Load Playlists")
        self.load_check_playlist_btn.clicked.connect(self.load_check_playlist)
        self.check_playlist_combo = QComboBox()
        self.show_playlist_names_btn = QPushButton("Load Playlist Names")
        self.show_playlist_names_btn.clicked.connect(self.show_check_playlist_names)
        playlist_layout.addWidget(self.load_check_playlist_btn)
        playlist_layout.addWidget(self.check_playlist_combo, 1)
        playlist_layout.addWidget(self.show_playlist_names_btn)
        layout.addLayout(playlist_layout)
        self.check_table = QTableWidget()
        self.check_table.setColumnCount(3)
        self.check_table.setHorizontalHeaderLabels(["#", "Folder Filename", "YouTube Title"])
        self.check_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.check_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.check_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.check_table)
        compare_btn = QPushButton("Compare Folder vs Playlist")
        compare_btn.clicked.connect(self.compare_folder_playlist)
        layout.addWidget(compare_btn)
        self.check_log_window = QTextEdit()
        self.check_log_window.setReadOnly(True)
        self.check_log_window.setFixedHeight(100)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.check_log_window)
        self.check_tab.setLayout(layout)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_path = folder
            self.selected_folder_path_label.setText(folder)

    def clear_check_table_column(self, col_index):
        for i in range(self.check_table.rowCount()):
            item = self.check_table.item(i, col_index)
            if item:
                item.setText("")
                item.setBackground(QColor("white"))
            else:
                self.check_table.setItem(i, col_index, QTableWidgetItem(""))

    def load_folder_names(self):
        if not self.folder_path or not os.path.isdir(self.folder_path):
            QMessageBox.warning(self, "No Folder", "Select folder first.")
            return
        logging.info(f"Load check folder: {self.folder_path}")
        self.check_log_window.setText(f"Loading: {self.folder_path}...")
        QApplication.processEvents()
        try:
            vid_ext = ('.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm')
            files = [f for f in os.listdir(self.folder_path) if os.path.isfile(os.path.join(self.folder_path, f)) and f.lower().endswith(vid_ext)]
            basenames = [os.path.splitext(f)[0] for f in files]
            self.folder_files = sorted(basenames, key=self.extract_chapter_sort_key)
            logging.info(f"Found {len(self.folder_files)} folder names.")
            req_rows = max(self.check_table.rowCount(), len(self.folder_files))
            self.check_table.setRowCount(req_rows)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Load folder fail: {e}")
            self.check_log_window.append(f"<font color='red'>Folder fail: {e}</font>")
            logging.exception(f"Folder fail {self.folder_path}")
            return
        for i in range(req_rows):
            num_i = self.check_table.item(i, 0)
            if not num_i:
                num_i = QTableWidgetItem(str(i+1))
                num_i.setTextAlignment(Qt.AlignCenter)
                self.check_table.setItem(i, 0, num_i)
            f_name = self.folder_files[i] if i < len(self.folder_files) else ""
            f_item = self.check_table.item(i, 1)
            if f_item:
                f_item.setText(f_name)
                f_item.setBackground(QColor("white"))
            else:
                self.check_table.setItem(i, 1, QTableWidgetItem(f_name))
            p_item = self.check_table.item(i, 2)
            if not p_item:
                self.check_table.setItem(i, 2, QTableWidgetItem(""))
            elif i >= len(self.folder_files):
                p_item.setBackground(QColor("white"))
        self.check_table.resizeColumnsToContents()
        self.check_table.resizeRowsToContents()
        self.check_log_window.append(f"OK: Load {len(self.folder_files)} names (Col 2).")
        QMessageBox.information(self, "Folder Loaded", f"Loaded {len(self.folder_files)} filenames.")

    def load_check_playlist(self, show_messages=True):
        if not self.check_authentication():
            return
        chan_name = self.current_channel_profile['name']
        logging.info(f"Load Check lists: '{chan_name}'.")
        self.check_log_window.append(f"Loading lists '{chan_name}'...")
        QApplication.processEvents()
        try:
            playlists = []
            nextToken = None
            pc, max_p = 0, 10
            while pc < max_p:
                pc += 1
                req = self.youtube.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextToken)
                resp = req.execute()
                items = resp.get("items", [])
                playlists.extend(items)
                logging.debug(f"P{pc}({len(items)}) check lists {chan_name}")
                nextToken = resp.get("nextPageToken")
                if not nextToken:
                    break
            if pc >= max_p and nextToken:
                logging.warning(f"Max pages check lists {chan_name}.")
                if show_messages:
                    QMessageBox.warning(self, "Limit", f"Load {len(playlists)} lists.")
            self.check_playlist_combo.clear()
            self.check_playlists.clear()
            if playlists:
                sorted_lists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                for item in sorted_lists:
                    pid = item["id"]
                    snip = item["snippet"]
                    cd = item["contentDetails"]
                    title = snip["title"]
                    desc = snip.get("description", "")
                    cnt = cd["itemCount"]
                    disp = f"{title} ({cnt} videos) - {desc[:50]}"
                    self.check_playlists[disp] = pid
                    self.check_playlist_combo.addItem(disp)
                msg = f"Load {len(playlists)} check lists '{chan_name}'."
                logging.info(msg)
                self.check_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "Loaded", f"Found {len(playlists)}.")
            else:
                msg = f"No lists '{chan_name}'."
                logging.info(msg)
                self.check_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "No Playlists", msg)
        except HttpError as e:
            err = f"API Err load check lists: {e}"
            logging.exception(err)
            self.check_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "API Error", err)
        except Exception as e:
            err = f"Err load check lists: {e}"
            logging.exception(err)
            self.check_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "Error", err)

    def show_check_playlist_names(self):
        if not self.check_authentication():
            return
        sel_txt = self.check_playlist_combo.currentText()
        if not sel_txt:
            QMessageBox.warning(self, "No Selection", "Select playlist.")
            return
        pid = self.check_playlists.get(sel_txt)
        if not pid:
            QMessageBox.critical(self, "Error", f"ID missing:\n'{sel_txt}'")
            logging.error(f"ID miss check {sel_txt}")
            return
        chan_name = self.current_channel_profile['name']
        logging.info(f"Load check titles: '{chan_name}', PID: {pid}")
        self.check_log_window.append(f"Loading names: {sel_txt[:80]}...")
        QApplication.processEvents()
        try:
            videos = []
            nextToken = None
            pc, max_p = 0, 20
            while pc < max_p:
                pc += 1
                req = self.youtube.playlistItems().list(part="snippet", playlistId=pid, maxResults=50, pageToken=nextToken)
                resp = req.execute()
                items = resp.get("items", [])
                videos.extend(items)
                logging.debug(f"P{pc}({len(items)}) check titles {pid}")
                nextToken = resp.get("nextPageToken")
                if not nextToken:
                    break
            if pc >= max_p and nextToken:
                logging.warning(f"Max pages check titles {pid}.")
                self.check_log_window.append(f"<font color='orange'>Warn: Fetched max {max_p*50} items.</font>")
            logging.info(f"Fetched {len(videos)} items {pid}.")
            try:
                items_titles = [v for v in videos if v.get('snippet', {}).get('title')]
                sorted_videos = sorted(items_titles, key=lambda v: self.extract_chapter_sort_key(v['snippet']['title']))
                self.playlist_titles = [v['snippet']['title'] for v in sorted_videos]
                logging.info("Check titles sorted.")
            except Exception as e:
                logging.exception("Check sort fail.")
                QMessageBox.warning(self, "Sort Warn", f"Sort fail: {e}")
                self.playlist_titles = [v['snippet']['title'] for v in videos if v.get('snippet', {}).get('title')]
            req_rows = max(self.check_table.rowCount(), len(self.playlist_titles))
            self.check_table.setRowCount(req_rows)
            for i in range(req_rows):
                num_i = self.check_table.item(i, 0)
                if not num_i:
                    num_i = QTableWidgetItem(str(i+1))
                    num_i.setTextAlignment(Qt.AlignCenter)
                    self.check_table.setItem(i, 0, num_i)
                f_item = self.check_table.item(i, 1)
                if not f_item:
                    self.check_table.setItem(i, 1, QTableWidgetItem(""))
                elif i >= len(self.playlist_titles):
                    f_item.setBackground(QColor("white"))
                p_title = self.playlist_titles[i] if i < len(self.playlist_titles) else ""
                p_item = self.check_table.item(i, 2)
                if p_item:
                    p_item.setText(p_title)
                    p_item.setBackground(QColor("white"))
                else:
                    self.check_table.setItem(i, 2, QTableWidgetItem(p_title))
            self.check_table.resizeColumnsToContents()
            self.check_table.resizeRowsToContents()
            self.check_log_window.append(f"OK: Load {len(self.playlist_titles)} names (Col 3).")
            QMessageBox.information(self, "Names Loaded", f"Loaded {len(self.playlist_titles)} titles.")
        except HttpError as e:
            QMessageBox.critical(self, "API Error", f"Load names fail: {e}")
            self.check_log_window.append(f"<font color='red'>Load fail: {e}</font>")
            logging.exception(f"Load names fail {pid}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error: {e}")
            self.check_log_window.append(f"<font color='red'>Error: {e}</font>")
            logging.exception("Error show check names.")

    def compare_folder_playlist(self):
        row_cnt = self.check_table.rowCount()
        if row_cnt == 0 or (not self.folder_files and not self.playlist_titles):
            QMessageBox.information(self, "No Data", "Load folder/playlist first.")
            return
        logging.info("Start check compare.")
        self.check_log_window.setText("Comparing...")
        QApplication.processEvents()
        f_list = self.folder_files
        p_list = self.playlist_titles
        msgs = []
        discrep = False
        for r in range(row_cnt):
            for c in range(1, 3):
                item = self.check_table.item(r, c)
                if item:
                    item.setBackground(QColor("white"))
        len_f, len_p = len(f_list), len(p_list)
        if len_f != len_p:
            msg = f"Count Mismatch: F={len_f}, P={len_p}."
            msgs.append(f"<font color='orange'><b>{msg}</b></font>")
            logging.warning(msg)
            discrep = True
        else:
            msgs.append(f"Count Match: {len_f}.")
            logging.info(f"Counts ok: {len_f}")
        seen = {}
        f_map = {}
        for t in p_list:
            tl = t.lower()
            seen[tl] = seen.get(tl, 0) + 1
            if tl not in f_map:
                f_map[tl] = t
        dups = [f"'{f_map[tl]}' ({c}x)" for tl, c in seen.items() if c > 1]
        if dups:
            msg = "Dup Playlist Titles: " + ", ".join(dups)
            msgs.append(f"<font color='orange'>{msg}</font>")
            logging.warning(msg)
            discrep = True
        mismatches = []
        mm_color = QColor(255, 192, 203)
        max_r = self.check_table.rowCount()
        for i in range(max_r):
            i_f = self.check_table.item(i, 1)
            i_p = self.check_table.item(i, 2)
            f_txt = (i_f.text().strip() if i_f else "")
            p_txt = (i_p.text().strip() if i_p else "")
            report = False
            if f_txt != p_txt:
                if i < min(len_f, len_p):
                    report = True
                elif i < max(len_f, len_p):
                    report = True
            if report:
                mm_msg = f"R{i+1}: F='{f_txt}' != P='{p_txt}'"
                mismatches.append(mm_msg)
                logging.warning(f"Mismatch {i+1}: F='{f_txt}', P='{p_txt}'")
                discrep = True
                if i_f:
                    i_f.setBackground(mm_color)
                if i_p:
                    i_p.setBackground(mm_color)
        if mismatches:
            msgs.append("<font color='red'><b>Mismatches:</b></font><br>" + "<br>".join(mismatches))
        self.check_log_window.append("\n--- Compare Results ---")
        self.check_log_window.append("<br>".join(msgs))
        if discrep:
            summary = "Discrepancies found!"
            QMessageBox.warning(self, "Compare Issues", summary + "\nCheck log/table.")
            logging.warning("Compare done: Discrepancies.")
        else:
            summary = "No discrepancies found."
            QMessageBox.information(self, "Compare OK", summary)
            logging.info("Compare done: OK.")
        self.check_log_window.verticalScrollBar().setValue(self.check_log_window.verticalScrollBar().maximum())

    # ----------------------- Tab 4: Generate Excel UI & Logic -----------------------
    def init_excel_tab(self):
        layout = QVBoxLayout()
        load_layout = QHBoxLayout()
        self.load_excel_playlists_btn = QPushButton("Load Playlists")
        self.load_excel_playlists_btn.clicked.connect(self.load_excel_playlists)
        load_layout.addWidget(self.load_excel_playlists_btn)
        load_layout.addStretch()
        layout.addLayout(load_layout)
        self.excel_playlist_table = QTableWidget()
        self.excel_playlist_table.setColumnCount(2)
        self.excel_playlist_table.setHorizontalHeaderLabels(["Select", "Playlist Details"])
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.excel_playlist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.excel_playlist_table.verticalHeader().setVisible(False)
        self.excel_playlist_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(QLabel("Select Playlists for Excel:"))
        layout.addWidget(self.excel_playlist_table)
        progress_layout = QHBoxLayout()
        self.excel_progress_bar = QProgressBar()
        progress_layout.addWidget(QLabel("Progress:"))
        progress_layout.addWidget(self.excel_progress_bar)
        layout.addLayout(progress_layout)
        self.excel_log_window = QTextEdit()
        self.excel_log_window.setReadOnly(True)
        self.excel_log_window.setFixedHeight(200)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self.excel_log_window)
        self.generate_excel_btn = QPushButton("Generate Excel(s)")
        self.generate_excel_btn.clicked.connect(self.generate_selected_excels)
        layout.addWidget(self.generate_excel_btn)
        self.excel_tab.setLayout(layout)

    def load_excel_playlists(self, show_messages=True):
        if not self.check_authentication():
            return
        chan_name = self.current_channel_profile['name']
        logging.info(f"Load Excel lists: '{chan_name}'.")
        self.excel_log_window.setText(f"Loading lists '{chan_name}'...")
        QApplication.processEvents()
        try:
            playlists = []
            nextToken = None
            pc, max_p = 0, 10
            while pc < max_p:
                pc += 1
                req = self.youtube.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50, pageToken=nextToken)
                resp = req.execute()
                items = resp.get("items", [])
                playlists.extend(items)
                logging.debug(f"P{pc}({len(items)}) excel lists {chan_name}")
                nextToken = resp.get("nextPageToken")
                if not nextToken:
                    break
            if pc >= max_p and nextToken:
                logging.warning(f"Max pages excel lists {chan_name}.")
                if show_messages:
                    QMessageBox.warning(self, "Limit", f"Load {len(playlists)} lists.")
            self.excel_playlist_table.setRowCount(0)
            self.excel_playlists_data.clear()
            if playlists:
                sorted_lists = sorted(playlists, key=lambda p: p.get('snippet', {}).get('title', '').lower())
                self.excel_playlist_table.setRowCount(len(sorted_lists))
                for row, item in enumerate(sorted_lists):
                    pid = item["id"]
                    snip = item["snippet"]
                    cd = item["contentDetails"]
                    title = snip["title"]
                    desc = snip.get("description", "")
                    cnt = cd["itemCount"]
                    self.excel_playlists_data[pid] = {'id': pid, 'title': title, 'description': desc, 'row': row}
                    cb = QCheckBox()
                    cb_widget = QWidget()
                    cb_l = QHBoxLayout(cb_widget)
                    cb_l.addWidget(cb)
                    cb_l.setAlignment(Qt.AlignCenter)
                    cb_l.setContentsMargins(0, 0, 0, 0)
                    self.excel_playlist_table.setCellWidget(row, 0, cb_widget)
                    desc_prev = desc[:100].replace('\n', ' ') + ('...' if len(desc) > 100 else '')
                    disp = f"{title}\nDesc:{desc_prev}\n({cnt} videos)"
                    item1 = QTableWidgetItem(disp)
                    item1.setToolTip(f"ID:{pid}\nTitle:{title}\nVideos:{cnt}\nDesc:{desc}")
                    item1.setData(Qt.UserRole, pid)
                    self.excel_playlist_table.setItem(row, 1, item1)
                self.excel_playlist_table.resizeRowsToContents()
                msg = f"Load {len(playlists)} excel lists '{chan_name}'."
                logging.info(msg)
                self.excel_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "Loaded", f"Found {len(playlists)}.")
            else:
                msg = f"No lists '{chan_name}'."
                logging.info(msg)
                self.excel_log_window.append(msg)
                if show_messages:
                    QMessageBox.information(self, "No Playlists", msg)
        except HttpError as e:
            err = f"API Err load excel lists: {e}"
            logging.exception(err)
            self.excel_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "API Error", err)
        except Exception as e:
            err = f"Err load excel lists: {e}"
            logging.exception(err)
            self.excel_log_window.append(f"<font color='red'>{err}</font>")
            if show_messages:
                QMessageBox.critical(self, "Error", err)

    def video_sort_key(self, title):
        return self.extract_chapter_sort_key(title)

    def generate_selected_excels(self):
        if not self.check_authentication():
            return
        chan_name = self.current_channel_profile['name']
        sel_ids = []
        for row in range(self.excel_playlist_table.rowCount()):
            cb_w = self.excel_playlist_table.cellWidget(row, 0)
            cb = cb_w.findChild(QCheckBox) if cb_w else None
            item1 = self.excel_playlist_table.item(row, 1)
            if cb and cb.isChecked() and item1:
                pid = item1.data(Qt.UserRole)
                if pid and pid in self.excel_playlists_data:
                    sel_ids.append(pid)
                else:
                    logging.warning(f"Excel Gen: Bad ID '{pid}' R{row}.")
                    self.excel_log_window.append(f"<font color='orange'>Warn: Cannot process R{row+1}.</font>")
        if not sel_ids:
            QMessageBox.warning(self, "No Selection", "Select playlists.")
            return
        try:
            today = datetime.datetime.now().strftime("%d%m%y_%H%M")
            s_name = sanitize_filename(chan_name, True)
            dir_name = f"{s_name}_{today}_Excel"
            s_dir = os.path.dirname(os.path.abspath(__file__))
            out_dir = os.path.join(s_dir, dir_name)
            os.makedirs(out_dir, exist_ok=True)
            logging.info(f"Output dir: {out_dir}")
        except Exception as e:
            QMessageBox.critical(self, "Folder Error", f"Cannot create dir '{dir_name}': {e}")
            logging.exception("Output dir fail.")
            return
        total = len(sel_ids)
        self.excel_progress_bar.setMaximum(total)
        self.excel_progress_bar.setValue(0)
        self.excel_log_window.clear()
        self.excel_log_window.append(f"Gen Excel for {total} lists from '{chan_name}'...")
        self.excel_log_window.append(f"Output: {out_dir}")
        QApplication.processEvents()
        ok_cnt, fail_cnt = 0, 0
        for i, pid in enumerate(sel_ids):
            p_data = self.excel_playlists_data.get(pid)
            if not p_data:
                fail_cnt += 1
                logging.error(f"Skip Excel: Data miss ID {pid}.")
                self.excel_log_window.append(f"<font color='red'>--> FAIL: Data miss ID {pid}.</font>")
                self.excel_progress_bar.setValue(i+1)
                continue
            p_title = p_data.get('title', 'UNKNOWN')
            p_desc = p_data.get('description', '')
            self.excel_log_window.append(f"\nProc {i+1}/{total}: '{p_title}' (ID: {pid})")
            QApplication.processEvents()
            try:
                self.generate_excel_for_playlist(pid, p_title, p_desc, out_dir)
                self.excel_log_window.append(f"--> OK: Gen '{p_title}'.")
                logging.info(f"OK: Excel {pid} ('{p_title}')")
                ok_cnt += 1
            except HttpError as e:
                fail_cnt += 1
                err_d = f"{e.resp.status} {e.reason}"
                try:
                    c = json.loads(e.content)
                    err_d += f"-{c.get('error', {}).get('message', '')}"
                except Exception:
                    pass
                msg = f"--> FAIL(API) '{p_title}':{err_d}"
                self.excel_log_window.append(f"<font color='red'>{msg}</font>")
                logging.exception(f"API Err Excel {pid}")
            except ValueError as e:
                fail_cnt += 1
                msg = f"--> FAIL '{p_title}': {e}"
                self.excel_log_window.append(f"<font color='red'>{msg}</font>")
                logging.error(f"ValErr Excel {pid}: {e}")
            except Exception as e:
                fail_cnt += 1
                msg = f"--> FAIL(Err) '{p_title}':{type(e).__name__}"
                self.excel_log_window.append(f"<font color='red'>{msg}: {e}</font>")
                logging.exception(f"Err Excel {pid}")
            finally:
                self.excel_progress_bar.setValue(i+1)
                QApplication.processEvents()
        final = f"Excel done '{chan_name}'. OK:{ok_cnt}, Fail:{fail_cnt}."
        self.excel_log_window.append(f"\n<b>{final}</b>")
        logging.info(final)
        QMessageBox.information(self, "Excel Done", final + f"\nSaved: {out_dir}")
        try:
            if sys.platform == 'win32':
                os.startfile(out_dir)
            else:
                import subprocess
                subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', out_dir], check=True)
        except Exception as e:
            logging.warning(f"Cannot open folder '{out_dir}': {e}")

    # *** THIS FUNCTION CONTAINS THE SPECIFIC FIX ***
    def generate_excel_for_playlist(self, playlist_id, playlist_title, playlist_description, output_dir):
        """Fetches videos, sorts them, extracts data, and saves to an Excel file."""
        logging.info(f"Generating Excel for Playlist ID: {playlist_id}, Title: '{playlist_title}'")
        # 1. Parse Codes
        course_code, lang_code = "UNKNOWN", "UNKNOWN"
        match = re.match(r'PL_([^_]+(?:_[^_]+)*)_([a-zA-Z0-9]+)', playlist_title, re.IGNORECASE)
        if match:
            course_code, lang_code = match.group(1), match.group(2)
            logging.info(f"Codes: '{course_code}', '{lang_code}' from '{playlist_title}'")
        else:
            logging.warning(f"Title '{playlist_title}' != format.")
            self.excel_log_window.append(f"<font color='orange'>   Warn: Title '{playlist_title}' format mismatch.</font>")
        # 2. Filename
        s_desc = sanitize_filename(playlist_description or "NoDesc", True)
        s_title = sanitize_filename(playlist_title, True)
        max_l = 80
        combo = f"{s_desc}_{s_title}"
        fname = (combo[:max_l] + '...' if len(combo) > max_l else combo) + ".xlsx"
        fpath = os.path.join(output_dir, fname)
        logging.info(f"Excel path: {fpath}")
        # 3. Fetch items
        items = []
        nextPageToken = None
        self.excel_log_window.append("   Fetching items...")
        QApplication.processEvents()
        pc, max_p = 0, 20
        while pc < max_p:
            pc += 1
            req = self.youtube.playlistItems().list(part="snippet,contentDetails", playlistId=playlist_id, maxResults=50, pageToken=nextPageToken)
            resp = req.execute()
            fetched = resp.get("items", [])
            items.extend(fetched)
            logging.debug(f"Page {pc} ({len(fetched)} items) excel {playlist_id}")
            nextPageToken = resp.get("nextPageToken")
            if not nextPageToken:
                break
        if pc >= max_p and nextPageToken:
            logging.warning(f"Max pages excel fetch {playlist_id}.")
            self.excel_log_window.append(f"<font color='orange'>   Warn: Fetched max {max_p*50}.</font>")
        logging.info(f"Fetched {len(items)} total items for playlist {playlist_id}.")
        self.excel_log_window.append(f"   Fetched {len(items)} items.")
        # 4. Sort items
        try:
            items_to_sort = [i for i in items if i.get("snippet", {}).get("title")]
            sorted_items = sorted(items_to_sort, key=lambda i: self.video_sort_key(i["snippet"]["title"]))
            logging.info("Excel items sorted.")
            self.excel_log_window.append("   Items sorted.")
        except Exception as e:
            logging.exception("Error sorting excel items.")
            self.excel_log_window.append(f"<font color='orange'>   Warn: Sort failed ({e}). Using API order.</font>")
            sorted_items = items
        # 5. Process sorted items
        excel_data = []
        chapter_name = ""
        order_in_chapter = 0
        seen_ids = set()
        for item in sorted_items:
            snip = item.get("snippet", {})
            cd = item.get("contentDetails", {})
            vid = cd.get("videoId")
            title = snip.get("title", "!!! MISSING !!!")
            desc = snip.get("description", "")
            pos = snip.get("position", -1)
            if not vid:
                logging.warning(f"Excel: Skip pos {pos} ('{title[:50]}...') - no ID.")
                continue
            if vid in seen_ids:
                logging.warning(f"Excel: Skip dup ID {vid} ('{title[:50]}...')")
                continue
            seen_ids.add(vid)
            url = f"https://www.youtube.com/watch?v={vid}"
            chapter_excel = ""
            order_excel = 0
            sort_key = self.video_sort_key(title)
            # *** CORRECTED LOGIC FOR COURSE INTRODUCTION ***
            if sort_key[0] == -1:
                chapter_excel = ""
                order_excel = 0
                chapter_name = "Introduction"
                order_in_chapter = 0
            elif sort_key[0] == 999:
                logging.warning(f"Excel: Title '{title}' uses fallback sort.")
                self.excel_log_window.append(f"<font color='orange'>   Warn: Title '{title[:50]}...' not standard format.</font>")
                chapter_excel = chapter_name if chapter_name and chapter_name != "Introduction" else "Unknown Chapter Content"
                order_in_chapter += 1
                order_excel = order_in_chapter
            else:
                is_header = sort_key[1] == 0
                if is_header:
                    chapter_name = title
                    chapter_excel = chapter_name
                    order_excel = 0
                    order_in_chapter = 0
                else:
                    if not chapter_name or chapter_name == "Introduction":
                        logging.warning(f"Excel: Part '{title}' found before header.")
                        self.excel_log_window.append(f"<font color='orange'>   Warn: Part '{title[:30]}...' before header.</font>")
                        chapter_excel = "Unknown Chapter"
                        if chapter_name == "Introduction":
                            order_in_chapter = 0
                    else:
                        chapter_excel = chapter_name
                    order_in_chapter += 1
                    order_excel = order_in_chapter
            excel_data.append({
                'CourseCode': course_code,
                'Chapter Name': chapter_excel,
                'Youtubeurl': url,
                'Video Title': title,
                'Video Description': desc,
                'OrderNo in Chapter': order_excel,
                'Language code': lang_code
            })
        # 6. Create DataFrame and save
        if not excel_data:
            logging.warning(f"No valid data for playlist {playlist_id}. Skipping '{fname}'.")
            self.excel_log_window.append("<font color='orange'>   Warn: No valid video data found.</font>")
            raise ValueError("No valid video data found to create Excel file.")
        df = pd.DataFrame(excel_data)
        df = df[['CourseCode', 'Chapter Name', 'Youtubeurl', 'Video Title', 'Video Description', 'OrderNo in Chapter', 'Language code']]
        logging.info(f"Saving {len(df)} rows to {fpath}")
        self.excel_log_window.append(f"   Proc {len(df)} items. Saving: {fname}")
        QApplication.processEvents()
        try:
            df.to_excel(fpath, index=False, engine='openpyxl')
            logging.info(f"Saved: {fpath}")
        except Exception as e:
            logging.exception(f"Error saving to Excel: {fpath}")
            raise IOError(f"Failed to save Excel file {fname}: {e}") from e

# --- Main Execution ---
if __name__ == '__main__':
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception as e:
        print(f"Warning: Could not set Fusion style: {e}")
    try:
        os.makedirs(MainWindow.get_tokens_dir_abs(), exist_ok=True)
    except Exception as dir_e:
        print(f"FATAL ERROR: Cannot create dir {MainWindow.get_tokens_dir_abs()}. Error: {dir_e}", file=sys.stderr)
        QMessageBox.critical(None, "Fatal Error", f"Cannot create dir:\n{MainWindow.get_tokens_dir_abs()}")
        sys.exit(1)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

# --- END OF FILE youtube_manager.py ---
