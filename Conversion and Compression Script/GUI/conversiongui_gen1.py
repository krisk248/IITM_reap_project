import sys
import os
import subprocess
import threading
import datetime
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QRadioButton, QFileDialog, QCheckBox,
    QProgressBar, QTextEdit, QMessageBox, QGroupBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# -------------------------------
# Global Configuration
# -------------------------------
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
NTFY_TOPIC = "rclone_reap_iit"

try:
    import imageio_ffmpeg
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_BINARY = "ffmpeg"
FFPROBE_BINARY = "ffprobe"

# -------------------------------
# Helper Functions
# -------------------------------
def get_video_duration(input_file: str) -> float:
    """Get video duration in seconds using ffprobe."""
    command = [
        FFPROBE_BINARY, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def format_duration(seconds: float) -> str:
    """Return a string in 'H hours M min S sec' format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours} hours {minutes} min {secs:.0f} sec"

def write_error_log(log_file_path: str, input_file: str, error_output: str):
    """Write error details to a log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error converting file: {input_file}\n")
            f.write(error_output)
    except Exception:
        pass

# -------------------------------
# Worker Threads
# -------------------------------
class ConversionWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(float)
    finished_signal = pyqtSignal(bool, bool)  # (success, aborted)

    def __init__(self, input_path: str, output_path: str, mode: str, use_cuda: bool, send_notify: bool):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.mode = mode  # "File" or "Folder"
        self.use_cuda = use_cuda
        self.send_notify = send_notify
        self._stop_event = threading.Event()
        self.converted_files = []  # To track created files for cleanup
        self.aborted = False

    def run(self):
        try:
            if self.mode == "File":
                self.process_file(self.input_path, self.output_path)
            else:
                self.process_folder(self.input_path, self.output_path)
            if not self._stop_event.is_set():
                if self.send_notify:
                    self.send_notification("Video conversion completed successfully.")
                self.log_signal.emit("Conversion complete!")
                self.finished_signal.emit(True, False)
            else:
                self.aborted = True
                self.log_signal.emit("Conversion aborted!")
                self.finished_signal.emit(False, True)
        except Exception as e:
            self.log_signal.emit(f"Error during conversion: {str(e)}")
            self.finished_signal.emit(False, False)

    def stop(self):
        self._stop_event.set()

    def send_notification(self, message: str):
        import requests
        url = f"https://ntfy.sh/{NTFY_TOPIC}"
        try:
            response = requests.post(url, data=message.encode("utf-8"))
            if response.status_code == 200:
                self.log_signal.emit("Ntfy notification sent successfully!")
            else:
                self.log_signal.emit(f"Error sending ntfy notification: {response.status_code} - {response.text}")
        except Exception as e:
            self.log_signal.emit(f"Error sending ntfy notification: {e}")

    def process_file(self, input_file: str, output_dir: str):
        in_path = Path(input_file)
        out_file = Path(output_dir) / f"{in_path.stem}.mp4"
        self.convert_video_file(str(in_path), str(out_file))

    def process_folder(self, input_dir: str, output_dir: str):
        input_path = Path(input_dir)
        output_path = Path(output_dir)
        try:
            video_files = [p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
        except Exception as e:
            self.log_signal.emit(f"Error scanning folder: {e}")
            return
        total_files = len(video_files)
        if total_files == 0:
            self.log_signal.emit("No video files found in the selected folder.")
            return
        for idx, file_path in enumerate(video_files, 1):
            if self._stop_event.is_set():
                break
            rel_path = file_path.relative_to(input_path).parent
            target_dir = output_path / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)
            out_file = target_dir / f"{file_path.stem}.mp4"
            self.log_signal.emit(f"Converting: {str(file_path)}")
            self.convert_video_file(str(file_path), str(out_file))
            progress = (idx / total_files) * 100
            self.progress_signal.emit(progress)
        self.log_signal.emit("Folder conversion complete.")

    def convert_video_file(self, input_file: str, output_file: str):
        duration = get_video_duration(input_file)
        if duration == 0:
            self.log_signal.emit(f"Skipping file (error reading duration): {input_file}")
            return
        if self.use_cuda:
            command = [
                FFMPEG_BINARY, "-y", "-hwaccel", "cuda",
                "-i", input_file, "-vf", "scale=-2:720",
                "-c:v", "h264_nvenc", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k",
                output_file, "-progress", "pipe:1", "-nostats"
            ]
        else:
            command = [
                FFMPEG_BINARY, "-y",
                "-i", input_file, "-vf", "scale=-2:720",
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k",
                output_file, "-progress", "pipe:1", "-nostats"
            ]
        self.log_signal.emit(f"Starting conversion: {Path(input_file).name}")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.converted_files.append(output_file)
        while True:
            if self._stop_event.is_set():
                process.kill()
                self.log_signal.emit(f"Aborted conversion for {input_file}")
                break
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=")[1])
                    current_time = out_time_ms / 1_000_000
                    progress = min(current_time / duration * 100, 100)
                    self.progress_signal.emit(progress)
                except Exception:
                    pass
            elif line.startswith("progress="):
                if line.split("=")[1] == "end":
                    self.progress_signal.emit(100)
                    break
        process.wait()
        if process.returncode != 0:
            self.log_signal.emit(f"Error: FFmpeg exited with code {process.returncode} for {input_file}")
            remaining_output = process.stdout.read()
            log_file = Path(output_file).with_suffix(".log")
            write_error_log(str(log_file), input_file, remaining_output)
            self.log_signal.emit(f"Error log written to: {str(log_file)}")
        else:
            self.log_signal.emit(f"Finished converting {input_file}")

class DurationWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(float)
    finished_signal = pyqtSignal(bool)  # (success)

    def __init__(self, input_path: str, output_path: str, mode: str):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.mode = mode  # "File" or "Folder"
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        durations = {}
        total_duration = 0.0
        files = []
        if self.mode == "File":
            files = [self.input_path]
        else:
            input_path = Path(self.input_path)
            try:
                files = [str(p) for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
            except Exception as e:
                self.log_signal.emit(f"Error scanning folder: {e}")
                self.finished_signal.emit(False)
                return
        total_files = len(files)
        if total_files == 0:
            self.log_signal.emit("No video files found for duration check.")
            self.finished_signal.emit(False)
            return
        for idx, file in enumerate(files, 1):
            if self._stop_event.is_set():
                break
            duration = get_video_duration(file)
            durations[file] = duration
            total_duration += duration
            progress = (idx / total_files) * 100
            self.progress_signal.emit(progress)
        output_file = Path(self.output_path) / "video_durations.txt"
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                for file, dur in durations.items():
                    f.write(f"{Path(file).name} -> {format_duration(dur)}\n")
                f.write("\n")
                f.write(f"Total duration of the course -> {format_duration(total_duration)}\n")
            self.log_signal.emit(f"Duration file created: {str(output_file)}")
            self.finished_signal.emit(True)
        except Exception as e:
            self.log_signal.emit(f"Error writing duration file: {e}")
            self.finished_signal.emit(False)

# -------------------------------
# Main GUI Window
# -------------------------------
class ConverterWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kannan's Video Converter")
        self.setGeometry(100, 100, 800, 650)
        self.worker = None
        self.duration_worker = None
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Conversion Mode
        mode_group = QGroupBox("Conversion Mode")
        mode_layout = QHBoxLayout()
        mode_group.setLayout(mode_layout)
        self.file_radio = QRadioButton("File")
        self.folder_radio = QRadioButton("Folder")
        self.file_radio.setChecked(True)
        mode_layout.addWidget(self.file_radio)
        mode_layout.addWidget(self.folder_radio)
        main_layout.addWidget(mode_group)

        # Input selection
        input_group = QGroupBox("Input")
        input_layout = QHBoxLayout()
        input_group.setLayout(input_layout)
        self.input_line = QLineEdit()
        browse_input_btn = QPushButton("Browse")
        browse_input_btn.clicked.connect(self.browse_input)
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(browse_input_btn)
        main_layout.addWidget(input_group)

        # Output selection
        output_group = QGroupBox("Output Folder")
        output_layout = QHBoxLayout()
        output_group.setLayout(output_layout)
        self.output_line = QLineEdit()
        browse_output_btn = QPushButton("Browse")
        browse_output_btn.clicked.connect(self.browse_output)
        output_layout.addWidget(self.output_line)
        output_layout.addWidget(browse_output_btn)
        main_layout.addWidget(output_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QHBoxLayout()
        options_group.setLayout(options_layout)
        self.cuda_checkbox = QCheckBox("Use NVIDIA CUDA acceleration")
        self.notify_checkbox = QCheckBox("Send ntfy notification after conversion")
        options_layout.addWidget(self.cuda_checkbox)
        options_layout.addWidget(self.notify_checkbox)
        main_layout.addWidget(options_group)

        # Action Buttons and Progress Bar
        action_layout = QHBoxLayout()
        self.convert_btn = QPushButton("Convert")
        self.convert_btn.clicked.connect(self.start_conversion)
        self.duration_btn = QPushButton("Check Duration")
        self.duration_btn.clicked.connect(self.start_duration_check)
        self.abort_btn = QPushButton("Abort")
        self.abort_btn.clicked.connect(self.abort_conversion)
        self.abort_btn.setEnabled(False)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        self.cancel_btn.setEnabled(False)
        action_layout.addWidget(self.convert_btn)
        action_layout.addWidget(self.duration_btn)
        action_layout.addWidget(self.abort_btn)
        action_layout.addWidget(self.cancel_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        action_layout.addWidget(self.progress_bar)
        main_layout.addLayout(action_layout)

        # Log Text Area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)

    def browse_input(self):
        if self.file_radio.isChecked():
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select a video file", "",
                "Video files (*.mp4 *.mov *.mkv *.avi *.m4v);;All Files (*)"
            )
            if file_path:
                self.input_line.setText(file_path)
        else:
            folder_path = QFileDialog.getExistingDirectory(self, "Select a folder")
            if folder_path:
                self.input_line.setText(folder_path)

    def browse_output(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder_path:
            self.output_line.setText(folder_path)

    def log(self, message: str):
        self.log_text.append(message)

    def start_conversion(self):
        input_path = self.input_line.text().strip()
        output_path = self.output_line.text().strip()
        if not input_path:
            QMessageBox.critical(self, "Error", "Please select an input file or folder.")
            return
        if not output_path:
            QMessageBox.critical(self, "Error", "Please select an output folder.")
            return

        self.log_text.clear()
        self.progress_bar.setValue(0)
        mode = "File" if self.file_radio.isChecked() else "Folder"
        use_cuda = self.cuda_checkbox.isChecked()
        send_notify = self.notify_checkbox.isChecked()

        self.worker = ConversionWorker(input_path, output_path, mode, use_cuda, send_notify)
        self.worker.log_signal.connect(self.log)
        # Convert progress value to int before setting it.
        self.worker.progress_signal.connect(lambda x: self.progress_bar.setValue(int(x)))
        self.worker.finished_signal.connect(self.conversion_finished)

        self.convert_btn.setEnabled(False)
        self.duration_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

        self.worker.start()

    def conversion_finished(self, success: bool, aborted: bool):
        self.convert_btn.setEnabled(True)
        self.duration_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        if aborted:
            self.log("Conversion was aborted. Cleaning up partial files...")
            self.cleanup_partial_files()
        if success:
            QMessageBox.information(self, "Conversion Complete", "Video conversion completed successfully!")
        else:
            if not aborted:
                QMessageBox.critical(self, "Conversion Error", "An error occurred during conversion.")

    def abort_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("Abort requested...")

    def cancel_conversion(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log("Cancel requested...")

    def cleanup_partial_files(self):
        if self.worker:
            for file in self.worker.converted_files:
                try:
                    if os.path.exists(file):
                        os.remove(file)
                        self.log(f"Deleted: {file}")
                except Exception as e:
                    self.log(f"Error deleting file {file}: {str(e)}")

    def start_duration_check(self):
        input_path = self.input_line.text().strip()
        output_path = self.output_line.text().strip()
        if not input_path:
            QMessageBox.critical(self, "Error", "Please select an input file or folder for duration check.")
            return
        if not output_path:
            QMessageBox.critical(self, "Error", "Please select an output folder for duration check.")
            return

        self.log_text.clear()
        self.progress_bar.setValue(0)
        mode = "File" if self.file_radio.isChecked() else "Folder"

        self.duration_worker = DurationWorker(input_path, output_path, mode)
        self.duration_worker.log_signal.connect(self.log)
        self.duration_worker.progress_signal.connect(lambda x: self.progress_bar.setValue(int(x)))
        self.duration_worker.finished_signal.connect(self.duration_finished)

        self.convert_btn.setEnabled(False)
        self.duration_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

        self.duration_worker.start()

    def duration_finished(self, success: bool):
        self.convert_btn.setEnabled(True)
        self.duration_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        if success:
            QMessageBox.information(self, "Duration Check Complete", "Duration file created successfully!")
        else:
            QMessageBox.critical(self, "Duration Check Error", "An error occurred during duration check.")

# -------------------------------
# Application Entry Point
# -------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ConverterWindow()
    window.show()
    sys.exit(app.exec_())
