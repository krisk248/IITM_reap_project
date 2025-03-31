import sys
import os
import subprocess
import shutil
import requests
from PyQt5.QtWidgets import (
    QApplication, QWidget, QRadioButton, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QDoubleSpinBox, QCheckBox,
    QTextEdit, QGroupBox
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread, pyqtSignal

class BGMWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)  # True if finished normally, False if cancelled or error

    def __init__(self, mode, input_path, bgm_file, output_path, volume, use_cuda, notif_topic, ffmpeg_path="ffmpeg"):
        super().__init__()
        self.mode = mode              # "file" or "folder"
        self.input_path = input_path  # file path or folder path
        self.bgm_file = bgm_file      # background music file
        self.output_path = output_path
        self.volume = volume
        self.use_cuda = use_cuda
        self.notif_topic = notif_topic
        self.ffmpeg_path = ffmpeg_path  # custom ffmpeg binary path
        self.cancelled = False
        self.created_files = []       # to track created files for cleanup
        self.current_process = None   # track current subprocess

    def run(self):
        try:
            if self.mode == "file":
                self.process_single_file()
            elif self.mode == "folder":
                self.process_folder()
            if self.cancelled:
                self.log_signal.emit("Process cancelled. Cleaning up created files...")
                self.cleanup()
                self.finished_signal.emit(False)
            else:
                self.log_signal.emit("Processing completed successfully.")
                # Send notification if topic provided
                if self.notif_topic.strip():
                    self.send_notification()
                self.finished_signal.emit(True)
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
            self.finished_signal.emit(False)

    def process_single_file(self):
        input_file = self.input_path
        base = os.path.splitext(os.path.basename(input_file))[0]
        # Append "Wbgm" to file name for output
        output_file = os.path.join(self.output_path, base + ".mp4")
        self.log_signal.emit(f"Processing file: {input_file} -> {output_file}")
        command = self.build_ffmpeg_command(input_file, output_file)
        self.run_command(command)
        if not self.cancelled:
            self.created_files.append(output_file)

    def process_folder(self):
        input_folder = self.input_path
        parent_name = os.path.basename(os.path.normpath(input_folder))
        # Create a parent folder in the output folder with "Wbgm" appended
        output_parent = os.path.join(self.output_path, parent_name + "Wbgm")
        if not os.path.exists(output_parent):
            os.makedirs(output_parent)
            self.log_signal.emit(f"Created output folder: {output_parent}")
        # Walk recursively through the folder
        for root, dirs, files in os.walk(input_folder):
            if self.cancelled:
                break
            for file in files:
                if file.lower().endswith(".mp4"):
                    input_file = os.path.join(root, file)
                    rel_path = os.path.relpath(root, input_folder)
                    out_dir = os.path.join(output_parent, rel_path)
                    if not os.path.exists(out_dir):
                        os.makedirs(out_dir)
                    output_file = os.path.join(out_dir, os.path.splitext(file)[0] + ".mp4")
                    self.log_signal.emit(f"Processing file: {input_file} -> {output_file}")
                    command = self.build_ffmpeg_command(input_file, output_file)
                    self.run_command(command)
                    if self.cancelled:
                        break
                    self.created_files.append(output_file)

    def build_ffmpeg_command(self, input_file, output_file):
        volume_str = f"{self.volume}"
        command = []
        if self.use_cuda:
            # Use CUDA hardware acceleration and nvenc encoder.
            command.extend([self.ffmpeg_path, "-hwaccel", "cuda", "-i", input_file])
        else:
            command.extend([self.ffmpeg_path, "-i", input_file])
        # Loop the BGM indefinitely
        command.extend(["-stream_loop", "-1", "-i", self.bgm_file])
        filter_complex = f"[1:a]volume={volume_str}[a1]; [0:a][a1]amix=inputs=2:duration=first[a]"
        command.extend(["-filter_complex", filter_complex, "-map", "0:v", "-map", "[a]"])
        if self.use_cuda:
            command.extend(["-c:v", "h264_nvenc"])
        else:
            command.extend(["-c:v", "copy"])
        command.extend(["-shortest", output_file])
        return command

    def run_command(self, command):
        if self.cancelled:
            return
        try:
            self.log_signal.emit("Running command: " + " ".join(command))
            self.current_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = self.current_process.communicate()
            if self.current_process.returncode != 0:
                self.log_signal.emit("Error processing file:\n" + stderr.decode())
            else:
                self.log_signal.emit("File processed successfully.")
        except Exception as e:
            self.log_signal.emit(f"Command execution error: {str(e)}")
        finally:
            self.current_process = None

    def cleanup(self):
        for file in self.created_files:
            if os.path.exists(file):
                try:
                    os.remove(file)
                    self.log_signal.emit(f"Deleted file: {file}")
                except Exception as e:
                    self.log_signal.emit(f"Error deleting file {file}: {str(e)}")
        if self.mode == "folder":
            input_folder = self.input_path
            parent_name = os.path.basename(os.path.normpath(input_folder))
            output_parent = os.path.join(self.output_path, parent_name + "Wbgm")
            if os.path.exists(output_parent):
                try:
                    shutil.rmtree(output_parent)
                    self.log_signal.emit(f"Deleted folder: {output_parent}")
                except Exception as e:
                    self.log_signal.emit(f"Error deleting folder {output_parent}: {str(e)}")

    def send_notification(self):
        try:
            url = f"https://ntfy.sh/{self.notif_topic}"
            data = "BGM adding has been completed successfully."
            response = requests.post(url, data=data)
            if response.status_code == 200:
                self.log_signal.emit("Notification sent successfully.")
            else:
                self.log_signal.emit(f"Notification failed with status code: {response.status_code}")
        except Exception as e:
            self.log_signal.emit(f"Notification error: {str(e)}")

    def cancel(self):
        self.cancelled = True
        if self.current_process:
            try:
                self.current_process.kill()
                self.log_signal.emit("Current ffmpeg process killed.")
            except Exception as e:
                self.log_signal.emit(f"Error killing process: {str(e)}")

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("K BGMAdder")
        self.resize(700, 800)  # Set window size to 700x800
        self.setWindowIcon(QIcon("app1.ico"))
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Mode Selection
        mode_group = QGroupBox("Select Mode")
        mode_layout = QHBoxLayout()
        self.radio_file = QRadioButton("Single File")
        self.radio_folder = QRadioButton("Folder")
        self.radio_file.setChecked(True)
        mode_layout.addWidget(self.radio_file)
        mode_layout.addWidget(self.radio_folder)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Input File/Folder
        input_layout = QHBoxLayout()
        self.input_line = QLineEdit()
        self.input_browse = QPushButton("Browse")
        self.input_browse.clicked.connect(self.browse_input)
        input_layout.addWidget(QLabel("Input:"))
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.input_browse)
        layout.addLayout(input_layout)

        # BGM File
        bgm_layout = QHBoxLayout()
        self.bgm_line = QLineEdit()
        self.bgm_browse = QPushButton("Browse")
        self.bgm_browse.clicked.connect(self.browse_bgm)
        bgm_layout.addWidget(QLabel("BGM File:"))
        bgm_layout.addWidget(self.bgm_line)
        bgm_layout.addWidget(self.bgm_browse)
        layout.addLayout(bgm_layout)

        # Output Folder
        output_layout = QHBoxLayout()
        self.output_line = QLineEdit()
        self.output_browse = QPushButton("Browse")
        self.output_browse.clicked.connect(self.browse_output)
        output_layout.addWidget(QLabel("Output Folder:"))
        output_layout.addWidget(self.output_line)
        output_layout.addWidget(self.output_browse)
        layout.addLayout(output_layout)

        # Volume Selection
        volume_layout = QHBoxLayout()
        self.volume_spin = QDoubleSpinBox()
        self.volume_spin.setRange(0.01, 0.15)
        self.volume_spin.setSingleStep(0.01)
        self.volume_spin.setValue(0.10)
        volume_layout.addWidget(QLabel("BGM Volume:"))
        volume_layout.addWidget(self.volume_spin)
        layout.addLayout(volume_layout)

        # CUDA Acceleration
        self.cuda_checkbox = QCheckBox("Use NVIDIA CUDA Acceleration")
        layout.addWidget(self.cuda_checkbox)

        # Notification Topic
        notif_layout = QHBoxLayout()
        self.notif_line = QLineEdit()
        notif_layout.addWidget(QLabel("Notification Topic:"))
        notif_layout.addWidget(self.notif_line)
        layout.addLayout(notif_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add BGM")
        self.add_btn.clicked.connect(self.start_processing)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # Log Output
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def browse_input(self):
        if self.radio_file.isChecked():
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", "", "Video Files (*.mp4 *.mov *.avi);;All Files (*)")
            if file_path:
                self.input_line.setText(file_path)
        else:
            folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
            if folder_path:
                self.input_line.setText(folder_path)

    def browse_bgm(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select BGM File", "", "Audio Files (*.mp3 *.wav *.flac *.ogg);;All Files (*)")
        if file_path:
            self.bgm_line.setText(file_path)

    def browse_output(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder_path:
            self.output_line.setText(folder_path)

    def log(self, message):
        self.log_text.append(message)

    def start_processing(self):
        mode = "file" if self.radio_file.isChecked() else "folder"
        input_path = self.input_line.text().strip()
        bgm_file = self.bgm_line.text().strip()
        output_path = self.output_line.text().strip()
        volume = self.volume_spin.value()
        use_cuda = self.cuda_checkbox.isChecked()
        notif_topic = self.notif_line.text().strip()

        if not input_path or not bgm_file or not output_path:
            self.log("Please select input, BGM file, and output folder.")
            return

        self.add_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log("Starting processing...")

        # Determine the ffmpeg binary path.
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
            if os.name == "nt":
                ffmpeg_path = os.path.join(base_path, "ffmpeg.exe")
            else:
                ffmpeg_path = os.path.join(base_path, "ffmpeg")
        else:
            ffmpeg_path = "ffmpeg"

        self.worker = BGMWorker(mode, input_path, bgm_file, output_path, volume, use_cuda, notif_topic, ffmpeg_path)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def cancel_processing(self):
        if self.worker:
            self.worker.cancel()
            self.log("Cancellation requested...")

    def processing_finished(self, success):
        if success:
            self.log("All files processed successfully.")
        else:
            self.log("Processing was cancelled or encountered errors.")
        self.add_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.worker = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("app1.ico"))
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
