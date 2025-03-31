import os
import subprocess
import threading
from pathlib import Path
from datetime import datetime
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from queue import Queue

# =============================================================================
# Configuration
# =============================================================================
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
DEFAULT_NTFY_SERVER = "https://ntfy.sh"

# =============================================================================
# GUI Application
# =============================================================================
class VideoConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Converter")
        self.root.geometry("800x600")
        
        self.create_widgets()
        self.log_queue = Queue()
        self.running = False
        self.check_log_queue()

    def create_widgets(self):
        # Conversion Mode
        ttk.Label(self.root, text="Conversion Mode:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.mode_var = tk.StringVar(value="File")
        self.mode_dropdown = ttk.Combobox(self.root, textvariable=self.mode_var, values=["File", "Folder"], state="readonly")
        self.mode_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.mode_dropdown.bind("<<ComboboxSelected>>", self.update_browse_button)

        # Input Selection
        ttk.Label(self.root, text="Input:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.input_path = tk.StringVar()
        self.input_entry = ttk.Entry(self.root, textvariable=self.input_path, width=50)
        self.input_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.browse_input_btn = ttk.Button(self.root, text="Browse", command=self.browse_input)
        self.browse_input_btn.grid(row=1, column=2, padx=5, pady=5)

        # Output Selection
        ttk.Label(self.root, text="Output Folder:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.output_path = tk.StringVar()
        self.output_entry = ttk.Entry(self.root, textvariable=self.output_path, width=50)
        self.output_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.browse_output_btn = ttk.Button(self.root, text="Browse", command=self.browse_output)
        self.browse_output_btn.grid(row=2, column=2, padx=5, pady=5)

        # CUDA Acceleration
        self.cuda_var = tk.BooleanVar()
        self.cuda_check = ttk.Checkbutton(self.root, text="Use NVIDIA CUDA Acceleration", variable=self.cuda_var)
        self.cuda_check.grid(row=3, column=0, columnspan=3, padx=5, pady=5, sticky="w")

        # Ntfy Notification
        self.ntfy_var = tk.BooleanVar()
        self.ntfy_check = ttk.Checkbutton(self.root, text="Send ntfy Notification", variable=self.ntfy_var, command=self.toggle_ntfy)
        self.ntfy_check.grid(row=4, column=0, padx=5, pady=5, sticky="w")
        
        ttk.Label(self.root, text="Topic:").grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.ntfy_topic = ttk.Entry(self.root)
        self.ntfy_topic.grid(row=5, column=1, padx=5, pady=5, sticky="ew")
        
        ttk.Label(self.root, text="Server:").grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.ntfy_server = ttk.Entry(self.root)
        self.ntfy_server.insert(0, DEFAULT_NTFY_SERVER)
        self.ntfy_server.grid(row=6, column=1, padx=5, pady=5, sticky="ew")

        # Log Area
        self.log_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD)
        self.log_area.grid(row=7, column=0, columnspan=3, padx=5, pady=5, sticky="nsew")

        # Convert Button
        self.convert_btn = ttk.Button(self.root, text="Convert", command=self.start_conversion)
        self.convert_btn.grid(row=8, column=0, columnspan=3, padx=5, pady=10)

        # Configure grid weights
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(7, weight=1)

    def update_browse_button(self, event=None):
        mode = self.mode_var.get()
        self.browse_input_btn.config(text="Browse File" if mode == "File" else "Browse Folder")

    def browse_input(self):
        mode = self.mode_var.get()
        if mode == "File":
            path = filedialog.askopenfilename(filetypes=[("Video Files", "*.mp4 *.mov *.mkv *.avi")])
        else:
            path = filedialog.askdirectory()
        if path:
            self.input_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_path.set(path)

    def toggle_ntfy(self):
        state = "normal" if self.ntfy_var.get() else "disabled"
        self.ntfy_topic.config(state=state)
        self.ntfy_server.config(state=state)

    def log(self, message):
        self.log_queue.put(message)

    def check_log_queue(self):
        while not self.log_queue.empty():
            message = self.log_queue.get()
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
        self.root.after(100, self.check_log_queue)

    def start_conversion(self):
        if self.running:
            return
        
        if not self.validate_inputs():
            return

        self.running = True
        self.convert_btn.config(text="Converting...", state=tk.DISABLED)
        
        # Gather parameters
        params = {
            "input_path": self.input_path.get(),
            "output_path": self.output_path.get(),
            "use_cuda": self.cuda_var.get(),
            "mode": self.mode_var.get(),
            "ntfy_topic": self.ntfy_topic.get() if self.ntfy_var.get() else None,
            "ntfy_server": self.ntfy_server.get() if self.ntfy_var.get() else None
        }

        # Start conversion thread
        thread = threading.Thread(target=self.run_conversion, args=(params,))
        thread.start()

    def validate_inputs(self):
        if not self.input_path.get():
            messagebox.showerror("Error", "Please select an input path")
            return False
        if not self.output_path.get():
            messagebox.showerror("Error", "Please select an output folder")
            return False
        if self.ntfy_var.get() and not self.ntfy_topic.get():
            messagebox.showerror("Error", "Please enter ntfy topic")
            return False
        return True

    def run_conversion(self, params):
        try:
            if params["mode"] == "File":
                self.convert_file(params)
            else:
                self.process_folder(params)
            
            messagebox.showinfo("Success", "Conversion completed successfully!")
            if params["ntfy_topic"]:
                self.send_ntfy_notification(params["ntfy_topic"], "Video conversion completed", params["ntfy_server"])
        
        except Exception as e:
            self.log(f"Error: {str(e)}")
            messagebox.showerror("Error", f"Conversion failed: {str(e)}")
        
        finally:
            self.running = False
            self.root.after(0, lambda: self.convert_btn.config(text="Convert", state=tk.NORMAL))

    def convert_file(self, params):
        input_file = Path(params["input_path"])
        output_dir = Path(params["output_path"])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{input_file.stem}_720p.mp4"
        
        self.log(f"Converting: {input_file.name}")
        self.convert_video_file(str(input_file), str(output_file), params["use_cuda"])

    def process_folder(self, params):
        input_dir = Path(params["input_path"])
        output_dir = Path(params["output_path"])
        
        for root, dirs, files in os.walk(input_dir):
            current_path = Path(root)
            rel_path = current_path.relative_to(input_dir)
            target_dir = output_dir / rel_path
            target_dir.mkdir(parents=True, exist_ok=True)

            for file in files:
                file_path = current_path / file
                if file_path.suffix.lower() in VIDEO_EXTENSIONS:
                    out_file = target_dir / f"{file_path.stem}_720p.mp4"
                    self.log(f"Converting: {file_path.name}")
                    self.convert_video_file(str(file_path), str(out_file), params["use_cuda"])

    def get_video_duration(self, input_file: str) -> float:
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
            self.log(f"Error getting duration for {input_file}: {e}")
            return 0.0

    def convert_video_file(self, input_file: str, output_file: str, use_cuda: bool) -> None:
        total_duration = self.get_video_duration(input_file)
        if total_duration == 0:
            self.log(f"Skipping file due to error reading duration: {input_file}")
            return

        # Build the FFmpeg command based on whether CUDA is available.
        if use_cuda:
            command = [
                "ffmpeg",
                "-y",                        # Overwrite output file
                "-hwaccel", "cuda",          # Use NVIDIA CUDA acceleration
                "-i", input_file,
                "-vf", "scale=-2:720",       # Resize video to 720p height (width auto-adjusted)
                "-c:v", "h264_nvenc",        # NVENC encoder for H.264
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "320k",
                output_file,
            ]
        else:
            command = [
                "ffmpeg",
                "-y",                        # Overwrite output file
                "-i", input_file,
                "-vf", "scale=-2:720",       # Resize video to 720p height (width auto-adjusted)
                "-c:v", "libx264",           # Use software-based H.264 encoding
                "-preset", "fast",
                "-c:a", "aac",
                "-b:a", "320k",
                output_file,
            ]

        # Start FFmpeg process and combine stdout and stderr so we can see all output.
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

        self.log(f"\nConverting: {Path(input_file).name}")
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    continue

                # Extract relevant info from FFmpeg output: frame, time, bitrate
                if "frame=" in line and "fps=" in line and "bitrate=" in line:
                    progress_line = line.strip().split(' ', 4)[-1]  # Capture only progress info
                    self.log(f"\r{progress_line}", end="")  # Overwrite the line
        except KeyboardInterrupt:
            self.log("\nConversion interrupted by user. Terminating FFmpeg process...")
            process.terminate()
            return

        # Capture any remaining output
        output, _ = process.communicate()
        if output:
            self.log(output)

        if process.returncode != 0:
            self.log(f"\nError: FFmpeg returned nonzero exit code {process.returncode} for file:")
            self.log(f"  {input_file}")
            self.log("Logging FFmpeg error output...")
            self.log_ffmpeg_error(input_file, output_file, output)
        else:
            self.log(f"\nFinished converting {input_file}")

    def log_ffmpeg_error(self, input_file: str, output_file: str, error_output: str) -> None:
        log_file = Path(output_file).with_suffix(".log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Error converting file: {input_file}\n")
            f.write(error_output)
        self.log(f"Error log written to: {log_file}")

    def send_ntfy_notification(self, topic: str, message: str, server: str = "https://ntfy.sh") -> None:
        url = f"{server}/{topic}"
        try:
            response = requests.post(url, data=message.encode("utf-8"))
            if response.status_code == 200:
                self.log("Ntfy notification sent successfully!")
            else:
                self.log(f"Error sending ntfy notification: {response.status_code} - {response.text}")
        except Exception as e:
            self.log(f"Error sending ntfy notification: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoConverterApp(root)
    root.mainloop()