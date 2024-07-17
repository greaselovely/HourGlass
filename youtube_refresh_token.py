# get_refresh_token

import json
from google_auth_oauthlib.flow import InstalledAppFlow
from vla_config import config, update_config

"""
This module handles the OAuth 2.0 flow to obtain a new refresh token for the YouTube API.
It uses the client ID and secret from the configuration to authenticate and authorize
the application, then saves the new refresh token back to the configuration.
"""

def get_new_refresh_token():
    """
    Initiates the OAuth 2.0 flow to obtain a new refresh token for the YouTube API.

    This function performs the following steps:
    1. Retrieves the client ID and secret from the configuration.
    2. Sets up an OAuth 2.0 flow with the YouTube upload scope.
    3. Runs a local server to handle the OAuth redirect.
    4. Opens a browser for the user to authorize the application.
    5. Obtains the new refresh token from the resulting credentials.
    6. Updates the configuration with the new refresh token.

    The function will print error messages if the client ID or secret are missing,
    and will print the new refresh token and a confirmation message when successful.

    Raises:
        Any exceptions raised during the OAuth flow or configuration update process.
    """
    youtube_config = config['auth']['youtube']
    client_id = youtube_config.get('client_id')
    client_secret = youtube_config.get('client_secret')

    if not client_id or not client_secret:
        print("Error: client_id or client_secret is missing from the config.")
        return

    # Create a flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"]
            }
        },
        scopes=['https://www.googleapis.com/auth/youtube.upload']
    )

    # Run the OAuth flow
    credentials = flow.run_local_server(port=8080)

    new_refresh_token = credentials.refresh_token

    print(f"New refresh token: {new_refresh_token}")

    # Update the config with the new refresh token
    youtube_config['refresh_token'] = new_refresh_token
    update_config(config)

    print("Config updated with new refresh token.")

if __name__ == "__main__":
    get_new_refresh_token()