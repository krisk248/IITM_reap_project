import os
import subprocess

def convert_video(input_path, output_path):
    """Convert a video to MP4 with H.264 video and AAC audio, 1280x720 resolution."""
    command = [
        'ffmpeg',
        '-i', input_path,              # Input file
        '-vf', 'scale=1280:720',       # Resize to 1280x720
        '-c:v', 'libx264',             # Video codec: H.264
        '-preset', 'medium',           # Encoding speed/quality tradeoff
        '-crf', '23',                  # Constant Rate Factor (quality)
        '-c:a', 'aac',                 # Audio codec: AAC
        '-b:a', '192k',                # Audio bitrate: 192 kbps
        '-r', '25',                    # Framerate: 25 fps
        output_path                    # Output file
    ]
    subprocess.run(command, check=True)

def create_video_list(video_files, list_path):
    """Create a text file with the list of videos to stitch."""
    with open(list_path, 'w') as f:
        for video in video_files:
            f.write(f"file '{video}'\n")

def stitch_videos(video_files, output_path):
    """Stitch videos together using ffmpeg's concat demuxer."""
    list_path = 'video_list.txt'
    create_video_list(video_files, list_path)

    command = [
        'ffmpeg',
        '-f', 'concat',                # Use concat demuxer
        '-safe', '0',                  # Allow absolute file paths
        '-i', list_path,               # Input list file
        '-c', 'copy',                  # Copy streams without re-encoding
        output_path                    # Output file
    ]
    subprocess.run(command, check=True)

    # Clean up the list file
    os.remove(list_path)

def process_root_folder(root_folder):
    """Process all videos in the root folder and its subfolders."""
    converted_files = []

    # Traverse through the root folder and its subfolders
    for subdir, _, files in os.walk(root_folder):
        for file in files:
            if file.endswith(('.mp4', '.mov')):
                input_path = os.path.join(subdir, file)
                output_path = os.path.join(subdir, f"converted_{file.split('.')[0]}.mp4")

                print(f"Converting: {input_path} -> {output_path}")
                convert_video(input_path, output_path)
                converted_files.append(output_path)

    # Stitch all converted videos
    if converted_files:
        output_video = os.path.join(root_folder, 'output_stitched.mp4')
        print(f"Stitching videos into: {output_video}")
        stitch_videos(converted_files, output_video)
        print("Stitching complete!")
    else:
        print("No video files found to process.")

# Main execution
if __name__ == "__main__":
    root_folder = "./Papad pickel Masala English"
    if os.path.isdir(root_folder):
        process_root_folder(root_folder)
    else:
        print("Invalid folder path. Please provide a valid directory.")