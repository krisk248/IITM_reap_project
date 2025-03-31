import os
import io
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from moviepy import VideoFileClip

# Google Drive API Scope
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

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
        fields="nextPageToken, files(id, name, mimeType)",
        corpora="drive",
        driveId=shared_drive_id,
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()

    return results.get('files', [])

def get_video_duration(service, file_id, filename):
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
    return duration

def traverse_folder(service, folder_id, shared_drive_id):
    """Recursively traverses a folder, processes video files, and returns total duration."""
    total_duration = 0
    files = list_files_in_folder(service, folder_id, shared_drive_id)

    for file in files:
        if file['mimeType'] == 'application/vnd.google-apps.folder':  # If it's a folder, recurse
            print(f"📁 Entering folder: {file['name']}")
            total_duration += traverse_folder(service, file['id'], shared_drive_id)
        elif file['mimeType'] in ['video/mp4', 'video/quicktime']:  # Process only .mp4 and .mov files
            print(f"🎬 Processing video: {file['name']}")
            duration = get_video_duration(service, file['id'], file['name'])
            print(f"✅ File: {file['name']}, Duration: {duration:.2f} seconds")
            total_duration += duration
    
    return total_duration

def main():
    service = authenticate_google_drive()

    # Replace with your actual Shared Drive ID
    shared_drive_id = '0AHxy0uU6Xa9yUk9PVA'  

    # Replace with the root folder inside the Shared Drive
    root_folder_id = '1-39S98B4nB_AB12w7MxJSFGBbKp-luCS'  

    print(f"🔍 Scanning Shared Drive (ID: {shared_drive_id}) for .mp4 and .mov videos...")
    total_duration = traverse_folder(service, root_folder_id, shared_drive_id)
    print(f"🎥 Total duration of all videos: {total_duration:.2f} seconds")

if __name__ == '__main__':
    main()
