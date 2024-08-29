# How to use?

1. Create a [Spotify Developers Account](https://developer.spotify.com/).

2. Go to "Dashboard" and Create "app":
  
    - Choose a redirect URL using localhost or 127.0.0.1, for example http://localhost:8080/callback.
      Because spotipy will instantiate a server on the indicated response to receive the access token 
      from the response at the end of the oauth flow.

    - Select "Web API" and "Web Playback SDK" for the APIs used.

3. Set required environment variables in an `.env` file:

    ```ini
    SPOTIPY_CLIENT_ID=****
    SPOTIPY_CLIENT_SECRET=****
    SPOTIPY_REDIRECT_URI=http://localhost:8080/callback
    ```

4. Install poetry

    ```bash
    $ pip install poetry
    ```

5. Install dependencies and run the script:

    ```bash
    # Create virtual environment and install dependencies
    $ poetry install

    # Runs the script within the context of the virtual environment
    $ poetry run python tempo_organizer.py
    ```

6. Helpful poetry commands:

    ```bash
    # Update dependencies
    $ poetry update

    # Remove virtual environment
    $ rm -rf $(poetry env info --path)
    ```
