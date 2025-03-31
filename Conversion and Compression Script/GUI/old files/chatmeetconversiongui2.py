import os
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from pathlib import Path
from datetime import datetime
import requests

# =============================================================================
# Configuration & Global Variables
# =============================================================================
# Define ntfy topic here (ntfy checkbox will use this)
NTFY_TOPIC = "rclone_reap_iit"

# Video extensions to process
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}

# Try to use a bundled ffmpeg binary via imageio-ffmpeg if available.
try:
    import imageio_ffmpeg
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_BINARY = "ffmpeg"  # fallback to system ffmpeg

# For ffprobe, you can bundle a binary similarly.
FFPROBE_BINARY = "ffprobe"  # Adjust this if you bundle ffprobe with your exe.

# =============================================================================
# Helper Functions for Video Conversion and Progress
# =============================================================================
def get_video_duration(input_file: str) -> float:
    """
    Get the duration of the video file using FFprobe.
    Note: FFPROBE_BINARY should point to a bundled ffprobe if needed.
    """
    command = [
        FFPROBE_BINARY,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_file,
    ]
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception as e:
        return 0.0

def log_ffmpeg_error(input_file: str, output_file: str, error_output: str, log_callback) -> None:
    """
    Write FFmpeg error output to a log file and log a single message.
    """
    log_file = Path(output_file).with_suffix(".log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error converting file: {input_file}\n")
            f.write(error_output)
        log_callback(f"Error log written to: {log_file}")
    except Exception as e:
        log_callback(f"Error writing log file: {e}")

def convert_video_file(input_file: str, output_file: str, use_cuda: bool, log_callback, progress_callback=None) -> None:
    """
    Convert a single video file using FFmpeg.
    Uses FFmpeg's -progress flag to update a progress callback.
    """
    duration = get_video_duration(input_file)
    if duration == 0:
        log_callback(f"Skipping file (error reading duration): {input_file}")
        return

    # Build the FFmpeg command.
    if use_cuda:
        command = [
            FFMPEG_BINARY,
            "-y",
            "-hwaccel", "cuda",
            "-i", input_file,
            "-vf", "scale=-2:720",
            "-c:v", "h264_nvenc",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
        ]
    else:
        command = [
            FFMPEG_BINARY,
            "-y",
            "-i", input_file,
            "-vf", "scale=-2:720",
            "-c:v", "libx264",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "320k",
        ]
    command += [output_file, "-progress", "pipe:1", "-nostats"]

    log_callback(f"Starting conversion: {Path(input_file).name}")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    # Parse FFmpeg's progress output (which prints key=value pairs)
    while True:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        line = line.strip()
        # If the line gives progress info, update progress bar accordingly.
        if line.startswith("out_time_ms="):
            try:
                out_time_ms = int(line.split("=")[1])
                # out_time_ms is in microseconds; convert to seconds.
                current_time = out_time_ms / 1_000_000
                progress = min(current_time / duration * 100, 100)
                if progress_callback:
                    progress_callback(progress)
            except Exception:
                pass
        elif line.startswith("progress="):
            if line.split("=")[1] == "end":
                # Ensure progress bar is set to 100%
                if progress_callback:
                    progress_callback(100)
                break

    process.wait()
    if process.returncode != 0:
        log_callback(f"Error: FFmpeg exited with code {process.returncode} for {input_file}")
        # Capture any remaining output for logging
        output, _ = process.communicate()
        log_ffmpeg_error(input_file, output_file, output, log_callback)
    else:
        log_callback(f"Finished converting {input_file}")

def process_folder(input_dir: str, output_dir: str, use_cuda: bool, log_callback, progress_callback=None) -> None:
    """
    Process all video files in a folder. For overall progress,
    count total files and update the progress bar after each file.
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Gather all video files
    video_files = [p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    total_files = len(video_files)
    if total_files == 0:
        log_callback("No video files found in the selected folder.")
        return

    for idx, file_path in enumerate(video_files, 1):
        # Determine output file path
        rel_path = file_path.relative_to(input_path).parent
        target_dir = output_path / rel_path
        target_dir.mkdir(parents=True, exist_ok=True)
        out_file = target_dir / f"{file_path.stem}.mp4"
        log_callback(f"Converting: {file_path}")
        # For folder conversion, we don’t update per-file progress;
        # you can use a dummy lambda if desired.
        convert_video_file(str(file_path), str(out_file), use_cuda, log_callback)
        if progress_callback:
            progress_callback(idx / total_files * 100)
    log_callback("Folder conversion complete.")

def send_ntfy_notification(message: str, server: str = "https://ntfy.sh", log_callback=None) -> None:
    """
    Send a notification via ntfy using the global NTFY_TOPIC.
    """
    url = f"{server}/{NTFY_TOPIC}"
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

# =============================================================================
# GUI Application (Using ttk for a Neat Interface)
# =============================================================================
class ConverterGUI(ttk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master = master
        self.master.title("Kannan's Video Converter")
        self.master.geometry("800x650")
        self.pack(fill="both", expand=True)
        self.input_path = None
        self.output_path = None
        self.create_widgets()

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")  # Use a neat built-in theme

        # Conversion Mode (File or Folder)
        mode_frame = ttk.Labelframe(self, text="Conversion Mode")
        mode_frame.pack(fill="x", padx=10, pady=5)
        self.mode_var = tk.StringVar(value="File")
        ttk.Radiobutton(mode_frame, text="File", variable=self.mode_var, value="File", command=self.mode_changed).pack(side="left", padx=10, pady=5)
        ttk.Radiobutton(mode_frame, text="Folder", variable=self.mode_var, value="Folder", command=self.mode_changed).pack(side="left", padx=10, pady=5)

        # Input selection
        input_frame = ttk.Labelframe(self, text="Input")
        input_frame.pack(fill="x", padx=10, pady=5)
        self.input_entry = ttk.Entry(input_frame, width=50)
        self.input_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        ttk.Button(input_frame, text="Browse", command=self.browse_input).pack(side="left", padx=5, pady=5)

        # Output folder selection
        output_frame = ttk.Labelframe(self, text="Output Folder")
        output_frame.pack(fill="x", padx=10, pady=5)
        self.output_entry = ttk.Entry(output_frame, width=50)
        self.output_entry.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        ttk.Button(output_frame, text="Browse", command=self.browse_output).pack(side="left", padx=5, pady=5)

        # Additional Options
        options_frame = ttk.Labelframe(self, text="Options")
        options_frame.pack(fill="x", padx=10, pady=5)
        self.cuda_var = tk.BooleanVar(value=False)
        self.notify_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Use NVIDIA CUDA acceleration", variable=self.cuda_var).pack(side="left", padx=10, pady=5)
        ttk.Checkbutton(options_frame, text="Send ntfy notification after conversion", variable=self.notify_var).pack(side="left", padx=10, pady=5)

        # Convert button and progress bar
        action_frame = ttk.Frame(self)
        action_frame.pack(fill="x", padx=10, pady=5)
        self.convert_button = ttk.Button(action_frame, text="Convert", command=self.start_conversion)
        self.convert_button.pack(side="left", padx=5, pady=5)
        self.progress_bar = ttk.Progressbar(action_frame, orient="horizontal", mode="determinate", maximum=100)
        self.progress_bar.pack(side="left", padx=10, pady=5, fill="x", expand=True)

        # Log text area
        log_frame = ttk.Labelframe(self, text="Log")
        log_frame.pack(fill="both", padx=10, pady=5, expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", state="normal")
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=log_scrollbar.set)

    def mode_changed(self):
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
        self.log_text.after(0, lambda: self.log_text.insert(tk.END, msg + "\n"))
        self.log_text.after(0, self.log_text.see, tk.END)

    def update_progress(self, value: float):
        self.progress_bar.after(0, lambda: self.progress_bar.configure(value=value))

    def start_conversion(self):
        if not self.input_entry.get():
            messagebox.showerror("Error", "Please select an input file or folder.")
            return
        if not self.output_entry.get():
            messagebox.showerror("Error", "Please select an output folder.")
            return

        self.convert_button.config(state="disabled")
        self.log_text.delete(1.0, tk.END)
        self.progress_bar.configure(value=0)

        mode = self.mode_var.get()
        input_path = self.input_entry.get()
        output_path = self.output_entry.get()
        use_cuda = self.cuda_var.get()
        send_notify = self.notify_var.get()

        def conversion_thread():
            try:
                if mode == "File":
                    in_path = Path(input_path)
                    output_file = Path(output_path) / f"{in_path.stem}.mp4"
                    convert_video_file(input_path, str(output_file), use_cuda, self.append_log, self.update_progress)
                else:
                    # Count video files to update overall progress
                    input_dir = input_path
                    process_folder(input_dir, output_path, use_cuda, self.append_log, self.update_progress)
                if send_notify:
                    send_ntfy_notification("Video conversion completed successfully.", log_callback=self.append_log)
                self.append_log("Conversion complete!")
                messagebox.showinfo("Conversion Complete", "Video conversion completed successfully!")
            except Exception as e:
                self.append_log(f"Error during conversion: {e}")
                messagebox.showerror("Conversion Error", str(e))
            finally:
                self.convert_button.config(state="normal")
                self.update_progress(100)

        threading.Thread(target=conversion_thread, daemon=True).start()

def main():
    root = tk.Tk()
    app = ConverterGUI(master=root)
    app.mainloop()

if __name__ == "__main__":
    main()