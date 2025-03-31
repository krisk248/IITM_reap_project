from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

def get_shared_drive_ids():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    service = build('drive', 'v3', credentials=creds)

    results = service.drives().list().execute()
    drives = results.get('drives', [])

    if not drives:
        print("No shared drives found.")
    else:
        for drive in drives:
            print(f"Name: {drive['name']}, ID: {drive['id']}")

if __name__ == '__main__':
    get_shared_drive_ids()
