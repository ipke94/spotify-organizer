import logging
import os
from itertools import islice
from typing import Optional

import spotipy
from dotenv import load_dotenv
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class SpotipyClient:
    def __init__(self):
        load_dotenv()
        self.auth_manager = self._create_auth_manager()
        self.sp = spotipy.Spotify(auth_manager=self.auth_manager)
        self.current_user_id = self._get_current_user_id()

    def _create_auth_manager(self) -> SpotifyOAuth:
        """Create Spotify authentication manager."""
        return SpotifyOAuth(
            scope="user-library-read playlist-read-private playlist-modify-public playlist-modify-private",
            show_dialog=True,
            cache_path="token.txt",
        )

    def _get_current_user_id(self) -> str:
        """Retrieve the current user's Spotify ID with authentication handling."""
        try:
            return self.sp.current_user()["id"]
        except SpotifyException as se:
            if "access token expired" in str(se):
                logging.warning(
                    "Access token has expired. Approve OAuth request in browser to complete login."
                )
                self._refresh_token()
                return self.sp.current_user()["id"]
            else:
                logging.error("Authentication error: %s", se)
                raise

    def _refresh_token(self):
        """Refresh Spotify access token."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        os.remove(os.path.join(current_dir, "token.txt"))
        self.auth_manager = self._create_auth_manager()
        self.sp = spotipy.Spotify(auth_manager=self.auth_manager)

    def get_current_user_playlists(
        self,
        owned_playlist_only: bool = False,
        excluded_playlists: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Retrieve current user's playlists.
        Args:
            owned_playlist_only (bool, optional): If True, returns playlists owned by the current user.
            excluded_playlists (list, optional): List of playlist names or IDs to exclude.

        Returns:
            list: Current user's playlists. Each playlist is a dict with the attributes:
            https://developer.spotify.com/documentation/web-api/reference/get-playlist
        """
        excluded_playlists = excluded_playlists or []
        results = self.sp.current_user_playlists()
        current_user_playlists = results["items"]

        # Handle pagination
        while results["next"]:
            results = self.sp.next(results)
            current_user_playlists.extend(results["items"])

        if excluded_playlists:
            current_user_playlists = [
                playlist
                for playlist in current_user_playlists
                if playlist["id"] not in excluded_playlists
                and playlist["name"] not in excluded_playlists
            ]

        if owned_playlist_only:
            current_user_playlists = [
                playlist
                for playlist in current_user_playlists
                if playlist["owner"]["id"] == self.current_user_id
            ]

        return current_user_playlists

    def create_playlist(
        self, playlist_name: str, public: bool = True, description: str = ""
    ) -> dict:
        """
        Create a new playlist for the current user. If a playlist with the same name exists, return it.

        Args:
            playlist_name (str): The name of the playlist.
            public (bool, optional): If True, the playlist is public.
            description (str, optional): Description of the playlist.

        Returns:
            dict: Created playlist details.
        """
        existing_playlists = self.get_current_user_playlists(owned_playlist_only=True)
        for existing_playlist in existing_playlists:
            if existing_playlist["name"] == playlist_name:
                logging.info(f"Playlist '{playlist_name}' already exists.")
                return existing_playlist

        new_playlist = self.sp.user_playlist_create(
            user=self.current_user_id,
            name=playlist_name,
            public=public,
            description=description,
        )
        logging.info(f"Playlist '{playlist_name}' (ID {new_playlist['id']}) created.")
        return new_playlist

    def unfollow_empty_playlists(self) -> None:
        """Unfollow (delete) all empty playlists."""
        empty_playlists = [
            playlist
            for playlist in self.get_current_user_playlists()
            if playlist["tracks"]["total"] == 0
        ]

        for empty_playlist in empty_playlists:
            logging.info(
                f"Unfollowing empty playlist {empty_playlist['name']} (ID: {empty_playlist['id']})"
            )
            self.sp.user_playlist_unfollow(
                user=self.current_user_id, playlist_id=empty_playlist["id"]
            )

    def unfollow_playlists(
        self,
        playlist_ids: Optional[list[str]] = None,
        name_contains: Optional[str] = None,
    ):
        """Unfollow playlists based on IDs or name patterns."""
        playlist_ids = playlist_ids or []

        if playlist_ids:
            for playlist_id in playlist_ids:
                self.sp.user_playlist_unfollow(
                    user=self.current_user_id, playlist_id=playlist_id
                )

        if name_contains:
            user_playlists = self.get_current_user_playlists(owned_playlist_only=True)
            for playlist in user_playlists:
                if name_contains in playlist["name"]:
                    logging.info(f"Unfollowing {playlist['name']}")
                    self.sp.user_playlist_unfollow(
                        user=self.current_user_id, playlist_id=playlist["id"]
                    )

    def get_tracks_from_playlist(self, playlist_id: str) -> list[dict]:
        """
        Get tracks from a specific playlist.

        Args:
            playlist_id (str): Playlist ID.

        Returns:
            list[dict]: List of track dictionaries containing 'artists', 'id', 'name', and 'type'.
        """
        results = self.sp.playlist_items(
            playlist_id=playlist_id,
            fields="items(track.artists(name),track.name,track.id,track.type),next",
            additional_types="track",
        )
        playlist_items = results["items"]
        while results["next"]:
            results = self.sp.next(results)
            playlist_items.extend(results["items"])

        # Filter only tracks (not episodes)
        tracks = [
            item["track"] for item in playlist_items if item["track"]["type"] == "track"
        ]

        for track in tracks:
            logging.debug(f"Track found: {track['name']} - ID: {track['id']}")

        return tracks

    def get_several_tracks_audio_features(self, track_ids: list[str]) -> list[dict]:
        """
        Get audio features for a list of tracks.

        Args:
            track_ids (list[str]): List of track IDs.

        Returns:
            list[dict]: List of track ids and audio features containing tempo, energy, and danceability.
        """
        batch_size = 100  # Max batch size per Spotify API
        tracks_with_audio_features = []
        logging.info(f"Retrieving audio features for {len(track_ids)} tracks...")

        for track_ids_batch in self._batch(track_ids, batch_size):
            audio_features = self.sp.audio_features(track_ids_batch)
            tracks_with_audio_features.extend(
                {
                    "id": track_audio_features["id"],
                    "tempo": round(track_audio_features["tempo"]),
                    "energy": track_audio_features["energy"],
                    "danceability": track_audio_features["danceability"],
                }
                for track_audio_features in audio_features
                if track_audio_features
            )

        return tracks_with_audio_features

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list[str]) -> None:
        """Add tracks to a playlist, skipping duplicates."""
        track_ids_in_playlist = {
            track["id"] for track in self.get_tracks_from_playlist(playlist_id)
        }
        track_ids_to_add = [
            track_id for track_id in track_ids if track_id not in track_ids_in_playlist
        ]

        if not track_ids_to_add:
            logging.info(f"All tracks are already in the playlist ID: {playlist_id}.")
        else:
            logging.info(f"Adding tracks to playlist ID: {playlist_id}")
            self.sp.playlist_add_items(playlist_id=playlist_id, items=track_ids_to_add)

    def _batch(self, iterable: list, n: int):
        """Yield successive n-sized chunks from iterable."""
        it = iter(iterable)
        while True:
            batch = list(islice(it, n))
            if not batch:
                break
            yield batch
