import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import threading
import requests
from pathlib import Path
from datetime import datetime

# Set of video extensions to process
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}

def get_video_duration(input_file: str) -> float:
    """Return the duration of a video file using ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        return 0.0

def log_ffmpeg_error(input_file: str, output_file: str, error_output: str, log_callback) -> None:
    """Write FFmpeg error output to a log file and update the log callback."""
    log_file = Path(output_file).with_suffix(".log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error converting file: {input_file}\n")
            f.write(error_output)
        log_callback(f"Error log written to: {log_file}")
    except Exception as e:
        log_callback(f"Error writing log file: {e}")

def convert_video_file(input_file: str, output_file: str, use_cuda: bool, log_callback) -> None:
    """Convert a single video file using FFmpeg with or without CUDA acceleration."""
    duration = get_video_duration(input_file)
    if duration == 0:
        log_callback(f"Skipping file due to error reading duration: {input_file}")
        return

    if use_cuda:
        command = [
            "ffmpeg",
            "-y",
            "-hwaccel", "cuda",
            "-i", input_file,
            "-vf", "scale=-2:720",
            "-c:v", "h264_nvenc",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
            output_file,
        ]
    else:
        command = [
            "ffmpeg",
            "-y",
            "-i", input_file,
            "-vf", "scale=-2:720",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
            output_file,
        ]

    log_callback(f"Converting {os.path.basename(input_file)}...")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Read FFmpeg output line by line and update log
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            log_callback(line.strip())
    process.wait()

    if process.returncode != 0:
        log_callback(f"Error: FFmpeg returned nonzero exit code {process.returncode} for file: {input_file}")
        log_callback("Logging FFmpeg error output...")
        output, _ = process.communicate()
        log_ffmpeg_error(input_file, output_file, output, log_callback)
    else:
        log_callback(f"Finished converting {input_file}")

def process_folder(input_dir: str, output_dir: str, use_cuda: bool, log_callback) -> None:
    """Recursively process all video files in the folder."""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    for root, dirs, files in os.walk(input_path):
        current_path = Path(root)
        rel_path = current_path.relative_to(input_path)
        target_dir = output_path / rel_path
        target_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            file_path = current_path / file
            if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                out_file = target_dir / f"{file_path.stem}_720p.mp4"
                log_callback(f"\nConverting:\n  Input: {file_path}\n  Output: {out_file}")
                convert_video_file(str(file_path), str(out_file), use_cuda, log_callback)

def send_ntfy_notification(topic: str, message: str, server: str = "https://ntfy.sh", log_callback=None) -> None:
    """Send a notification via ntfy."""
    url = f"{server}/{topic}"
    try:
        response = requests.post(url, data=message.encode("utf-8"))
        if response.status_code == 200:
            if log_callback:
                log_callback("Ntfy notification sent successfully!")
        else:
            if log_callback:
                log_callback(f"Error sending ntfy notification: {response.status_code} - {response.text}")
    except Exception as e:
        if log_callback:
            log_callback(f"Error sending ntfy notification: {e}")

class ConverterGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Kannan's Video Converter")
        self.geometry("700x500")
        self.input_path = None
        self.output_path = None
        self.create_widgets()

    def create_widgets(self):
        # Conversion Mode (File or Folder)
        self.mode_var = tk.StringVar(value="File")
        frame_mode = tk.LabelFrame(self, text="Conversion Mode")
        frame_mode.pack(fill="x", padx=10, pady=5)
        tk.Radiobutton(frame_mode, text="File", variable=self.mode_var, value="File", command=self.mode_changed).pack(side="left", padx=10, pady=5)
        tk.Radiobutton(frame_mode, text="Folder", variable=self.mode_var, value="Folder", command=self.mode_changed).pack(side="left", padx=10, pady=5)

        # Input selection
        frame_input = tk.LabelFrame(self, text="Input")
        frame_input.pack(fill="x", padx=10, pady=5)
        self.input_entry = tk.Entry(frame_input, width=50)
        self.input_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        self.input_button = tk.Button(frame_input, text="Browse", command=self.browse_input)
        self.input_button.pack(side="left", padx=5, pady=5)

        # Output folder selection
        frame_output = tk.LabelFrame(self, text="Output Folder")
        frame_output.pack(fill="x", padx=10, pady=5)
        self.output_entry = tk.Entry(frame_output, width=50)
        self.output_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        self.output_button = tk.Button(frame_output, text="Browse", command=self.browse_output)
        self.output_button.pack(side="left", padx=5, pady=5)

        # Additional Options
        frame_options = tk.LabelFrame(self, text="Options")
        frame_options.pack(fill="x", padx=10, pady=5)
        self.cuda_var = tk.BooleanVar(value=False)
        self.notify_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame_options, text="Use NVIDIA CUDA acceleration", variable=self.cuda_var).pack(side="left", padx=10, pady=5)
        tk.Checkbutton(frame_options, text="Send ntfy notification after conversion", variable=self.notify_var).pack(side="left", padx=10, pady=5)

        # Convert button
        self.convert_button = tk.Button(self, text="Convert", command=self.start_conversion)
        self.convert_button.pack(pady=10)

        # Log text area
        frame_log = tk.LabelFrame(self, text="Log")
        frame_log.pack(fill="both", padx=10, pady=5, expand=True)
        self.log_text = tk.Text(frame_log, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(frame_log, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

    def mode_changed(self):
        # Clear input field when the mode changes
        self.input_entry.delete(0, tk.END)
        self.input_path = None

    def browse_input(self):
        mode = self.mode_var.get()
        if mode == "File":
            file_path = filedialog.askopenfilename(
                title="Select a video file",
                filetypes=[("Video files", "*.mp4 *.mov *.mkv *.avi"), ("All files", "*.*")]
            )
            if file_path:
                self.input_path = file_path
                self.input_entry.delete(0, tk.END)
                self.input_entry.insert(0, file_path)
        else:
            folder_path = filedialog.askdirectory(title="Select a folder")
            if folder_path:
                self.input_path = folder_path
                self.input_entry.delete(0, tk.END)
                self.input_entry.insert(0, folder_path)

    def browse_output(self):
        folder_path = filedialog.askdirectory(title="Select output folder")
        if folder_path:
            self.output_path = folder_path
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, folder_path)

    def append_log(self, msg: str):
        # Thread-safe logging to the text widget
        self.log_text.after(0, lambda: self.log_text.insert(tk.END, msg + "\n"))
        self.log_text.after(0, self.log_text.see, tk.END)

    def start_conversion(self):
        if not self.input_entry.get():
            messagebox.showerror("Error", "Please select an input file or folder.")
            return
        if not self.output_entry.get():
            messagebox.showerror("Error", "Please select an output folder.")
            return

        self.convert_button.config(state="disabled")
        self.log_text.delete(1.0, tk.END)

        mode = self.mode_var.get()
        input_path = self.input_entry.get()
        output_path = self.output_entry.get()
        use_cuda = self.cuda_var.get()
        send_notify = self.notify_var.get()

        def conversion_thread():
            try:
                if mode == "File":
                    # Create output file name based on input file stem
                    in_path = Path(input_path)
                    output_file = Path(output_path) / f"{in_path.stem}_720p.mp4"
                    convert_video_file(input_path, str(output_file), use_cuda, self.append_log)
                else:
                    process_folder(input_path, output_path, use_cuda, self.append_log)
                if send_notify:
                    send_ntfy_notification("mytopic", "Video conversion completed successfully.", log_callback=self.append_log)
                self.append_log("Conversion complete!")
                messagebox.showinfo("Conversion Complete", "Video conversion completed successfully!")
            except Exception as e:
                self.append_log(f"Error during conversion: {e}")
                messagebox.showerror("Conversion Error", str(e))
            finally:
                self.convert_button.config(state="normal")

        threading.Thread(target=conversion_thread, daemon=True).start()

if __name__ == "__main__":
    app = ConverterGUI()
    app.mainloop()
