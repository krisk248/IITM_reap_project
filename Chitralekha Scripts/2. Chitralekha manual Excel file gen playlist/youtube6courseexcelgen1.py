import re
import os
import pandas as pd
from googleapiclient.discovery import build

# Function to extract chapter number from video title
def extract_chapter(title):
    match = re.search(r'Chapter\s*(\d+[A-Za-z]?)', title, re.IGNORECASE)
    return match.group(1) if match else ""

# Function to sort chapters naturally
def natural_order(chapter):
    match = re.match(r'(\d+)([A-Za-z]?)', chapter)
    if match:
        number, letter = match.groups()
        return int(number), letter or ""
    return float('inf'), ""

# Function to fetch videos from YouTube playlist
def fetch_playlist_videos(api_key, playlist_id):
    youtube = build('youtube', 'v3', developerKey=api_key)
    videos = []

    request = youtube.playlistItems().list(
        part="snippet",
        playlistId=playlist_id,
        maxResults=50
    )

    while request:
        response = request.execute()
        for item in response['items']:
            title = item['snippet']['title']
            video_id = item['snippet']['resourceId']['videoId']
            videos.append((title, f"https://www.youtube.com/watch?v={video_id}"))

        request = youtube.playlistItems().list_next(request, response)

    return videos

# Function to fetch playlist details
def fetch_playlist_details(api_key, playlist_id):
    youtube = build('youtube', 'v3', developerKey=api_key)
    request = youtube.playlists().list(
        part="snippet",
        id=playlist_id
    )
    response = request.execute()
    return response['items'][0]['snippet']['description'] if response['items'] else "Playlist"

# Function to generate the Excel sheet
def generate_excel(api_key, playlist_id, output_folder):
    videos = fetch_playlist_videos(api_key, playlist_id)
    playlist_name = fetch_playlist_details(api_key, playlist_id)

    # Extract chapter and sort
    video_data = [
        {
            "Video Title": title,
            "Youtube URL": url,
            "Chapter": extract_chapter(title)
        }
        for title, url in videos
    ]

    video_data.sort(key=lambda x: natural_order(x['Chapter']))

    # Add order number
    for i, video in enumerate(video_data, start=1):
        video['Order Number'] = i

    # Create DataFrame and save to Excel
    df = pd.DataFrame(video_data)
    df = df[["Order Number", "Video Title", "Youtube URL"]]

    # Ensure the output folder exists
    os.makedirs(output_folder, exist_ok=True)
    output_file = os.path.join(output_folder, f"{playlist_name}.xlsx")
    df.to_excel(output_file, index=False)

# Main function to process multiple playlists
def process_playlists(api_key, playlist_file, output_folder):
    with open(playlist_file, "r") as file:
        playlist_ids = [line.strip() for line in file if line.strip()]

    for playlist_id in playlist_ids:
        print(f"Processing playlist: {playlist_id}")
        generate_excel(api_key, playlist_id, output_folder)

# Example usage
if __name__ == "__main__":
    API_KEY = "AIzaSyCoawDYKWW31295p-x5AZHb5h_ulFolBmQ"  # Replace with your YouTube Data API v3 key
    PLAYLIST_FILE = "playlists.txt"  # Text file containing playlist IDs (one per line)
    OUTPUT_FOLDER = "./Playlists_Gen3_excel"  # Folder to save all Excel files

    process_playlists(API_KEY, PLAYLIST_FILE, OUTPUT_FOLDER)
    print(f"All playlists processed. Files saved in folder: {OUTPUT_FOLDER}")
