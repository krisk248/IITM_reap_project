import subprocess

# Loop over volume levels from 0.01 to 0.10
for i in range(1, 11):
    volume = i / 100.0
    output_filename = f"output_video{volume:.2f}.mp4"
    
    # Build the ffmpeg command with the desired volume
    command = [
        "ffmpeg",
        "-i", "input.mp4",
        "-stream_loop", "-1",
        "-i", "bgm.mp3",
        "-filter_complex", f"[1:a]volume={volume}[a1]; [0:a][a1]amix=inputs=2:duration=first[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-shortest",
        output_filename
    ]
    
    print(f"Running command for volume {volume:.2f} -> {output_filename}")
    subprocess.run(command)
