import os
import subprocess

def create_video_list(video_files, list_path):
    with open(list_path, 'w', encoding='utf-8') as f:
        for video in video_files:
            f.write(f"file '{video}'\n")

def stitch_videos(video_files, output_video):
    list_path = "video_list.txt"
    create_video_list(video_files, list_path)
    
    try:
        subprocess.run([
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_path, '-c', 'copy', output_video
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error stitching videos: {e}")
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

def convert_mov_to_mp4(input_file, output_file):
    try:
        subprocess.run([
            'ffmpeg', '-i', input_file, '-c:v', 'libx264', '-c:a', 'aac', '-strict', 'experimental', output_file
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error converting {input_file}: {e}")

def process_root_folder(root_folder):
    converted_files = []
    output_video = os.path.join(root_folder, "output_stitched.mp4")
    
    for root, dirs, files in os.walk(root_folder):
        for file in files:
            if file.endswith(".mov"):
                input_file = os.path.join(root, file)
                output_file = os.path.join(root, f"converted_{file.replace('.mov', '.mp4')}")
                convert_mov_to_mp4(input_file, output_file)
                converted_files.append(output_file)
    
    if converted_files:
        stitch_videos(converted_files, output_video)

if __name__ == "__main__":
    root_folder = "./PHOTO FRAMING , PRINTING AND LAMINATION"
    process_root_folder(root_folder)