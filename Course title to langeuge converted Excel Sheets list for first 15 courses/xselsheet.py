import os
import re
import requests
import pandas as pd

# ---------------------------
# Configuration
# ---------------------------
API_KEY = "AIzaSyCoawDYKWW31295p-x5AZHb5h_ulFolBmQ"  # Replace with your actual YouTube Data API key

# YouTube API endpoints
YOUTUBE_PLAYLIST_URL = "https://www.googleapis.com/youtube/v3/playlists"
YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"

# List of languages for which Excel files need to be created
languages = [
    "Hindi", "Bengali", "Marathi", "Telugu", "Tamil",
    "Gujarati", "English", "Kannada", "Odia", "Malayalam",
    "Punjabi", "Assamese"
]

# ---------------------------
# Utility functions
# ---------------------------
def sanitize_filename(name):
    """
    Remove characters that are not allowed in file/folder names.
    """
    return re.sub(r'[\\/*?:"<>|]', "", name)

def read_playlist_ids(file_path):
    """
    Read playlist IDs from a text file, one per line.
    """
    with open(file_path, "r") as file:
        ids = [line.strip() for line in file if line.strip()]
    return ids

def get_playlist_details(playlist_id):
    """
    Retrieve the playlist details (snippet) from the YouTube API.
    Uses the playlist description as the folder name.
    """
    params = {
        "part": "snippet",
        "id": playlist_id,
        "key": API_KEY
    }
    response = requests.get(YOUTUBE_PLAYLIST_URL, params=params)
    data = response.json()
    if "items" in data and len(data["items"]) > 0:
        snippet = data["items"][0]["snippet"]
        description = snippet.get("description", "").strip()
        # Use description as folder name; if empty, fallback to a default name.
        folder_name = sanitize_filename(description) if description else f"Playlist_{playlist_id}"
        return folder_name
    else:
        return f"Playlist_{playlist_id}"

def get_playlist_videos(playlist_id):
    """
    Retrieve all video titles in the playlist using pagination.
    """
    videos = []
    nextPageToken = None
    while True:
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
            "key": API_KEY
        }
        if nextPageToken:
            params["pageToken"] = nextPageToken
        response = requests.get(YOUTUBE_PLAYLIST_ITEMS_URL, params=params)
        data = response.json()
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            videos.append(title)
        nextPageToken = data.get("nextPageToken")
        if not nextPageToken:
            break
    return videos

def parse_video_title(title):
    """
    Parse a video title to generate a sort key.
    - If the title contains "Course Introduction" (case-insensitive), assign a special order.
    - Otherwise, try to match "Chapter X" (optionally with a letter, e.g. Chapter 1A).
    - Videos that do not match the expected patterns are sorted to the end.
    Returns a tuple (main_order, sub_order, original_title).
    """
    if re.search(r"Course\s+Introduction", title, re.IGNORECASE):
        # Ensure course introduction comes first
        return (-1, 0, title)
    
    match = re.search(r"Chapter\s+(\d+)([A-Za-z]?)", title, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        letter = match.group(2).upper()
        letter_val = 0 if letter == "" else (ord(letter) - ord('A') + 1)
        return (chapter_num, letter_val, title)
    
    # Titles that do not match are pushed to the end
    return (9999, 9999, title)

def sort_videos(videos):
    """
    Sort the list of video titles based on the parsed sort key.
    """
    parsed = [parse_video_title(title) for title in videos]
    parsed.sort(key=lambda x: (x[0], x[1]))
    return [title for (_, _, title) in parsed]

def create_excel_files(folder_path, sorted_titles, languages):
    """
    For each language, create an Excel file with three columns:
    - S.No (numbering)
    - Video Title (from sorted_titles)
    - <Language> Translated Text (empty column for translation)
    
    The Excel file is saved in the folder_path with a name like:
    "<folder_name>_<language>.xlsx"
    """
    for lang in languages:
        df = pd.DataFrame({
            "S.No": list(range(1, len(sorted_titles) + 1)),
            "Video Title": sorted_titles,
            f"{lang} Translated Text": ["" for _ in sorted_titles]
        })
        folder_basename = os.path.basename(folder_path)
        filename = f"{folder_basename}_{lang.lower()}.xlsx"
        filepath = os.path.join(folder_path, filename)
        df.to_excel(filepath, index=False)
        print(f"Created file: {filepath}")

# ---------------------------
# Main processing function
# ---------------------------
def main():
    # Read playlist IDs from the text file "playlist_ids.txt"
    playlist_ids = read_playlist_ids("./playlist.txt")
    
    for playlist_id in playlist_ids:
        print(f"Processing playlist: {playlist_id}")
        # Get folder name from playlist description
        folder_name = get_playlist_details(playlist_id)
        folder_path = os.path.join(os.getcwd(), folder_name)
        os.makedirs(folder_path, exist_ok=True)
        print(f"Created folder: {folder_path}")
        
        # Retrieve video titles and sort them naturally
        videos = get_playlist_videos(playlist_id)
        sorted_titles = sort_videos(videos)
        print("Sorted video titles:")
        for idx, title in enumerate(sorted_titles, start=1):
            print(f"{idx}: {title}")
        
        # Create an Excel file per language inside the folder
        create_excel_files(folder_path, sorted_titles, languages)
        print("-" * 50)

if __name__ == "__main__":
    main()
