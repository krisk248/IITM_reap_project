import csv
import os
from googleapiclient.discovery import build

# Function to fetch videos from a YouTube playlist
def fetch_videos_from_playlist(api_key, playlist_id):
    youtube = build('youtube', 'v3', developerKey=api_key)
    
    videos = []
    next_page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()

        for item in response['items']:
            video_title = item['snippet']['title']
            video_url = f"https://www.youtube.com/watch?v={item['snippet']['resourceId']['videoId']}"
            videos.append((video_title, video_url))

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    return videos

# Function to generate the CSV file
def generate_csv(project_id, videos, gender, assignee_email):
    csv_filename = f"translation_project_{project_id}.csv"

    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Writing the header row
        writer.writerow(["Project Id", "Youtube URL", "Source Language", "Gender", "Task Type", "Target Language", "Assignee", "Description", "Video Description", "Task Description"])

        # Writing video data rows
        for video_title, video_url in videos:
            writer.writerow([
                project_id, 
                video_url, 
                "en", 
                gender, 
                "Transcription Edit", 
                "",  # Target Language is empty for transcription tasks
                assignee_email, 
                video_title 
                # video_title, 
                # "Transcription Edit"
            ])

    print(f"CSV file '{csv_filename}' has been generated successfully!")

# Main script
if __name__ == "__main__":
    # Get API key and playlist ID
    api_key = "AIzaSyCoawDYKWW31295p-x5AZHb5h_ulFolBmQ"
    playlist_id = "PLIC0cwTiaddkNAHTRuk5po7nT0OGIX_HC"

    # Get project details
    project_id = input("Enter the Project ID: ")
    gender = input("Enter the Gender (Male/Female): ")
    assignee_email = input("Enter the Assignee email address: ")

    # Fetch videos from the playlist
    print("Fetching videos from the playlist...")
    videos = fetch_videos_from_playlist(api_key, playlist_id)

    # Sort videos based on title to ensure order
    videos.sort(key=lambda x: x[0])

    # Generate the CSV file
    generate_csv(project_id, videos, gender, assignee_email)
