import sys
import os
import re
import csv
import logging
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QTableWidget, QTableWidgetItem, QLineEdit,
    QMessageBox, QLabel, QHeaderView
)
from PyQt5.QtCore import Qt

# Set up logging
logging.basicConfig(filename='rename.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def natural_keys(text):
    """
    Sort function for natural sort order.
    Example: "Chapter 2" comes before "Chapter 10"
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split('(\d+)', text)]

class RenameTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MP4 Rename Tool")
        self.resize(800, 600)
        self.folder_path = ""
        self.files_info = []  # List to hold dictionaries with keys: 'path', 'name'

        self.setup_ui()

    def setup_ui(self):
        # Main widget and layout
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout()
        widget.setLayout(layout)

        # Folder selection section
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("No folder selected")
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(browse_button)
        layout.addLayout(folder_layout)

        # Load button
        load_button = QPushButton("Load Files")
        load_button.clicked.connect(self.load_files)
        layout.addWidget(load_button)

        # Table for file list and rename input
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Video Title", "Rename To"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Rename button
        rename_button = QPushButton("Rename")
        rename_button.clicked.connect(self.rename_files)
        layout.addWidget(rename_button)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.folder_path = folder
            self.folder_label.setText(f"Selected Folder: {folder}")
            logging.info(f"Folder selected: {folder}")

    def load_files(self):
        if not self.folder_path:
            QMessageBox.warning(self, "Warning", "Please select a folder first.")
            return

        self.files_info = []
        # Walk the folder and collect all .mp4 files (case-insensitive)
        for root, dirs, files in os.walk(self.folder_path):
            for file in files:
                if file.lower().endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    self.files_info.append({"path": full_path, "name": file})

        # Natural sort by file name
        self.files_info.sort(key=lambda x: natural_keys(x["name"]))
        logging.info(f"{len(self.files_info)} .mp4 file(s) loaded.")

        # Populate the table
        self.table.setRowCount(0)
        for index, file_info in enumerate(self.files_info):
            self.table.insertRow(index)
            # Original file name (non-editable)
            item = QTableWidgetItem(file_info["name"])
            item.setFlags(item.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(index, 0, item)
            # Textbox for new name
            line_edit = QLineEdit()
            self.table.setCellWidget(index, 1, line_edit)

    def rename_files(self):
        if not self.files_info:
            QMessageBox.warning(self, "Warning", "No files loaded.")
            return

        log_entries = []  # To collect CSV rows
        errors = []

        for row in range(len(self.files_info)):
            file_info = self.files_info[row]
            old_full_path = file_info["path"]
            old_name = file_info["name"]

            # Get new name from the table's QLineEdit
            widget = self.table.cellWidget(row, 1)
            new_name_input = widget.text().strip()

            # If textbox is empty, skip renaming
            if not new_name_input:
                log_entries.append([row + 1, old_name, old_name])
                continue

            # Ensure the new file name has .mp4 extension
            if not new_name_input.lower().endswith('.mp4'):
                new_name = new_name_input + ".mp4"
            else:
                new_name = new_name_input

            # Build the new full path in the same folder as the original file
            new_full_path = os.path.join(os.path.dirname(old_full_path), new_name)

            try:
                os.rename(old_full_path, new_full_path)
                logging.info(f"Renamed: '{old_full_path}' to '{new_full_path}'")
                log_entries.append([row + 1, old_name, new_name])
                # Update the table to show new file name in the first column
                self.table.item(row, 0).setText(new_name)
                # Also update our internal record
                self.files_info[row]["path"] = new_full_path
                self.files_info[row]["name"] = new_name
            except Exception as e:
                logging.error(f"Error renaming '{old_full_path}' to '{new_full_path}': {e}")
                errors.append(f"Error renaming '{old_name}': {e}")
                log_entries.append([row + 1, old_name, f"Error: {e}"])

        # Save the CSV log in the selected folder
        csv_path = os.path.join(self.folder_path, "rename_log.csv")
        try:
            with open(csv_path, mode="w", newline='', encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Number", "Old Video Title", "Renamed Title"])
                writer.writerows(log_entries)
            logging.info(f"CSV log saved at: {csv_path}")
        except Exception as e:
            logging.error(f"Error saving CSV log: {e}")
            errors.append(f"Error saving CSV log: {e}")

        if errors:
            QMessageBox.warning(self, "Rename Completed with Errors", "\n".join(errors))
        else:
            QMessageBox.information(self, "Success", "Files renamed and CSV log saved successfully.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = RenameTool()
    window.show()
    sys.exit(app.exec_())
