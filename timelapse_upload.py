# timelapse_upload.py

import os
import json
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from timelapse_config import config

def get_youtube_credentials():
    """
    Retrieve YouTube API credentials from the config.

    This function reads the YouTube API credentials from the config file,
    creates a Credentials object, and refreshes the token to ensure it's valid.

    Returns:
        google.oauth2.credentials.Credentials: A valid Credentials object for YouTube API.

    Raises:
        ValueError: If the YouTube credentials are not properly configured in the config file.
        Exception: If there's an error refreshing the credentials.
    """
    youtube_config = config['auth']['youtube']
    client_id = youtube_config.get('client_id')
    client_secret = youtube_config.get('client_secret')
    refresh_token = youtube_config.get('refresh_token')

    if not all([client_id, client_secret, refresh_token]):
        logging.error("YouTube credentials are not properly configured in config.json")
        logging.error(f"client_id: {'set' if client_id else 'missing'}")
        logging.error(f"client_secret: {'set' if client_secret else 'missing'}")
        logging.error(f"refresh_token: {'set' if refresh_token else 'missing'}")
        raise ValueError("YouTube credentials are not properly configured in config.json")

    try:
        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        # Force a refresh to check if the credentials are valid
        credentials.refresh(Request())
        return credentials
    except Exception as e:
        logging.error(f"Error refreshing credentials: {str(e)}")
        raise

def upload_to_youtube(video_path, title, description, category_id="28", privacy_status="public"):
    """
    Upload a video to YouTube.

    This function authenticates with YouTube, uploads the specified video,
    and returns the video ID along with the YouTube API client.

    Args:
        video_path (str): The file path of the video to upload.
        title (str): The title of the video.
        description (str): The description of the video.
        category_id (str, optional): The category ID for the video. Defaults to "28" (Science & Technology).
        privacy_status (str, optional): The privacy status of the video. Defaults to "public".

    Returns:
        tuple: A tuple containing the video ID (str) and the YouTube API client object.
               Returns (None, None) if the upload fails.

    Raises:
        Exception: If an error occurs during the upload process.
    """
    try:
        credentials = get_youtube_credentials()
        youtube = build("youtube", "v3", credentials=credentials)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status
            }
        }
        
        logging.info(f"Uploading video with privacy status: {privacy_status}")

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(video_path)
        )
        response = request.execute()

        video_id = response['id']
        logging.info(f"Video uploaded successfully. Video ID: {video_id}")
        
        return video_id, youtube  # Return both the video ID and the YouTube API client
    except Exception as e:
        logging.error(f"An error occurred during upload: {str(e)}")
        return None, None

def add_video_to_playlist(youtube, video_id, playlist_name=None):
    """
    Add a video to a specified YouTube playlist.

    This function searches for the specified playlist, and if found,
    adds the given video to that playlist.

    Args:
        youtube (googleapiclient.discovery.Resource): The YouTube API client.
        video_id (str): The ID of the video to add to the playlist.
        playlist_name (str, optional): The name of the playlist to add the video to. If None, uses project name from config.

    Returns:
        tuple: A tuple containing a boolean indicating success (True) or failure (False),
               and a string message providing details about the operation's outcome.

    Raises:
        HttpError: If an HTTP-related error occurs during the API requests.
        Exception: For any other unexpected errors.
    """
    try:
        # Use project name from config if not specified
        if playlist_name is None:
            from timelapse_config import YOUTUBE_PLAYLIST_NAME
            playlist_name = YOUTUBE_PLAYLIST_NAME
        
        # First, we need to find the playlist ID
        playlists_request = youtube.playlists().list(
            part="snippet",
            mine=True
        )
        playlists_response = playlists_request.execute()

        playlist_id = None
        for playlist in playlists_response.get('items', []):
            if playlist['snippet']['title'] == playlist_name:
                playlist_id = playlist['id']
                break

        if not playlist_id:
            logging.error(f"Playlist '{playlist_name}' not found")
            return False, f"Playlist '{playlist_name}' not found"

        # Now, add the video to the playlist
        playlist_items_request = youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {
                        "kind": "youtube#video",
                        "videoId": video_id
                    }
                }
            }
        )
        playlist_items_response = playlist_items_request.execute()

        # Check if the response contains the expected data
        if 'id' in playlist_items_response:
            logging.info(f"Video added to playlist '{playlist_name}' successfully. Playlist item ID: {playlist_items_response['id']}")
            return True, f"Video added to playlist '{playlist_name}' successfully"
        else:
            logging.warning(f"Video may not have been added to playlist. Unexpected response: {playlist_items_response}")
            return False, "Unexpected response from YouTube API"

    except HttpError as e:
        error_message = f"An HTTP error occurred: {e.resp.status} - {e.content.decode('utf-8')}"
        logging.error(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"An error occurred while adding video to playlist: {str(e)}"
        logging.error(error_message)
        return False, error_message