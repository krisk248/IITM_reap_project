import os
import io
import google.auth
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from moviepy import VideoFileClip

# Google Drive API Scope
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

def format_time_hms(seconds):
    """Converts seconds to 'X hours Y minutes Z seconds' format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours} hours {minutes} minutes and {secs} seconds"

def get_log_filenames(shared_drive_id, root_folder_name):
    """Generates log filenames based on timestamp, Shared Drive ID, and root folder name."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_root_folder_name = root_folder_name.replace(" ", "_").replace("/", "_")
    base_filename = f"{timestamp}_{shared_drive_id}_{safe_root_folder_name}"
    return f"duration_log_{base_filename}.txt", f"detailed_log_{base_filename}.txt"

def log_message(log_file, message, detailed_log_file=None, detailed_message=None):
    """Writes logs to a file and prints to console. Optionally writes debug details separately."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(log_file, "a", encoding="utf-8") as log:
        log.write(log_entry + "\n")
    
    if detailed_log_file and detailed_message:
        with open(detailed_log_file, "a", encoding="utf-8") as detailed_log:
            detailed_log.write(f"[{timestamp}] {detailed_message}\n")

def authenticate_google_drive():
    """Authenticates and returns Google Drive API service."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret_1.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def list_files_in_folder(service, folder_id, shared_drive_id):
    """Lists all files and folders inside a given folder."""
    results = service.files().list(
        q=f"'{folder_id}' in parents",
        fields="nextPageToken, files(id, name, mimeType, name)",
        corpora="drive",
        driveId=shared_drive_id,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()

    return results.get('files', [])

def get_video_duration(service, file_id, filename, detailed_log_file):
    """Downloads the video file temporarily and gets its duration."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    fh.seek(0)
    temp_filename = f'temp_video.{filename.split(".")[-1]}'
    with open(temp_filename, 'wb') as f:
        f.write(fh.read())

    clip = VideoFileClip(temp_filename)
    duration = clip.duration
    clip.close()
    
    os.remove(temp_filename)
    
    # Log detailed video metadata separately
    log_message(detailed_log_file, f"🔍 Detailed metadata for {filename}:\n{clip.__dict__}", None, None)

    return duration

def traverse_folder(service, folder_id, shared_drive_id, folder_name, log_file, detailed_log_file):
    """Recursively traverses a folder, processes video files, and returns total duration."""
    total_duration = 0
    files = list_files_in_folder(service, folder_id, shared_drive_id)

    log_message(log_file, f"\n📁 Entering folder: {folder_name}")

    for file in files:
        if file['mimeType'] == 'application/vnd.google-apps.folder':  # If it's a folder, recurse
            total_duration += traverse_folder(service, file['id'], shared_drive_id, file['name'], log_file, detailed_log_file)
        elif file['mimeType'] in ['video/mp4', 'video/quicktime']:  # Process only .mp4 and .mov files
            log_message(log_file, f"🎬 Processing video: {file['name']}...")
            duration = get_video_duration(service, file['id'], file['name'], detailed_log_file)
            log_message(log_file, f"✅ Duration: {format_time_hms(duration)}")
            total_duration += duration
    
    log_message(log_file, f"📊 Folder '{folder_name}' has {format_time_hms(total_duration)} of video content.")
    return total_duration

def main():
    service = authenticate_google_drive()

    # Replace with your actual Shared Drive ID and root folder ID
    shared_drive_id = '0AHxy0uU6Xa9yUk9PVA'  

    # Replace with the root folder inside the Shared Drive
    # root_folder_id = '1-39S98B4nB_AB12w7MxJSFGBbKp-luCS' # Ai Dubbing
    # root_folder_name = "Ai dubbing"  # Replace with actual root folder name

    root_folder_id = '18nRASqAiHLPxevUux6dQbwwbIwyM1pBW' # Manual Dubbing
    root_folder_name = "Manual dubbing"  # Replace with actual root folder name

    log_file, detailed_log_file = get_log_filenames(shared_drive_id, root_folder_name)

    start_time = datetime.datetime.now()
    log_message(log_file, f"\n🚀 The log is starting at {start_time.strftime('%H:%M:%S')} on {start_time.strftime('%Y-%m-%d')}")
    log_message(detailed_log_file, f"🛠 Detailed Log for Debugging\n🚀 Started at {start_time.strftime('%H:%M:%S')} on {start_time.strftime('%Y-%m-%d')}")

    log_message(log_file, f"\n🔍 Scanning Shared Drive (ID: {shared_drive_id}) for .mp4 and .mov videos...")
    total_duration = traverse_folder(service, root_folder_id, shared_drive_id, root_folder_name, log_file, detailed_log_file)

    end_time = datetime.datetime.now()
    log_message(log_file, f"\n🎥 Total video content in Shared Drive: {format_time_hms(total_duration)}")
    log_message(log_file, f"\n🛑 The log ends at {end_time.strftime('%H:%M:%S')} on {end_time.strftime('%Y-%m-%d')}\n")

    log_message(detailed_log_file, f"\n🛑 Detailed log ends at {end_time.strftime('%H:%M:%S')} on {end_time.strftime('%Y-%m-%d')}\n")

if __name__ == '__main__':
    main()
