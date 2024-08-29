import json
import logging
from itertools import batched

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class SpotipyClient:
    def __init__(self):
        load_dotenv()
        auth_manager = SpotifyOAuth(
            scope="user-library-read playlist-read-private playlist-modify-public playlist-modify-private",
            show_dialog=True,
            cache_path="token.txt",
        )
        logging.info("Approve OAuth request in browser to complete login.")
        self.sp = spotipy.Spotify(auth_manager=auth_manager)
        self.current_user_id = self.sp.current_user()["id"]

    def get_current_user_playlists(
        self, owned_playlist_only: bool = False, excluded_playlists: list = []
    ) -> list[dict]:
        """
        Args:
            owned_playlist_only (bool, optional): If True, returns playlists that are owned by current user.
            excluded_playlist (list, optional): List of playlist names or IDs to exclude.

        Returns:
            list: Current user's playlists. A playlist has following attributes https://developer.spotify.com/documentation/web-api/reference/get-playlist
        """

        results = self.sp.current_user_playlists()
        current_user_playlists = results["items"]
        # Many of the spotipy methods return paginated results,
        # so you will have to scroll through them to view more than just the max limit
        # which is usually 50 or 100.
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

        logging.debug(f"All playlists:\n{json.dumps(current_user_playlists, indent=4)}")
        return current_user_playlists

    def create_playlist(
        self, playlist_name: str, public: bool = True, description=""
    ) -> dict:
        """
        Create playlist for the current user. Skips if the user has another playlist with the same name.

        Args:
            playlist_name (string)
            public (bool, optional): If True, playlist is public.
            description (string, optional): Playlist description.

        Returns:
            playlist (dict): See https://developer.spotify.com/documentation/web-api/reference/get-playlist

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
        logging.info(
            f"Playlist '{playlist_name}' (ID {new_playlist['id']}) is created."
        )
        return new_playlist

    def unfollow_empty_playlists(self) -> None:
        """
        Spotify API doesn't have an endpoint to delete playlists.
        Still one can "unfollow" a playlist (even his own!), which has the effect of deleting it from one's Spotify account.
        """
        empty_playlists = [
            playlist
            for playlist in self.get_current_user_playlists()
            if playlist["tracks"]["total"] == 0
        ]

        for empty_playlist in empty_playlists:
            logging.info(
                f"Unfollowing {empty_playlist['name']} (ID. {empty_playlist['id']})"
            )
            self.sp.user_playlist_unfollow(
                user=self.current_user_id, playlist_id=empty_playlist["id"]
            )

    def get_tracks_from_playlist(self, playlist_id: str) -> list[dict]:
        """
        Args:
            playlist_id (string): Playlist ID that contains tracks.

        Returns:
            list[dict]: List of dictinary that contains tracks (not episodes) in the playlist. Only 'artists', 'id', 'name' and 'type' fields of a track are available in the dict.
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

        # filter tracks (from episodes). additional_types argument does not actually work.
        tracks = [
            item["track"] for item in playlist_items if item["track"]["type"] == "track"
        ]

        for track in tracks:
            logging.debug(f"{track['name']} - id: {track['id']}")

        return tracks

    def get_several_tracks_tempo(self, track_ids: list) -> list[dict]:
        """
        Args:
            track_ids(list[str]): Example ['4ibzxSKw3a6rtIorruN5GO','1wU7z5XE8oa66ZvUlYAKfK', ...]

        Returns:
            list[dict]: Example [{'id': '4ibzxSKw3a6rtIorruN5GO', 'tempo': 152}, {'id': '1wU7z5XE8oa66ZvUlYAKfK', 'tempo': 114}, ...]
        """

        batch_size = 100  # limit from https://developer.spotify.com/documentation/web-api/reference/get-several-audio-features
        tracks_with_tempos = []
        logging.info(f"Retrieving audio features of {len(track_ids)} tracks...")

        for track_ids_batch in batched(track_ids, batch_size):
            audio_features = self.sp.audio_features(list(track_ids_batch))

            tracks_with_tempos.extend(
                [
                    {
                        "id": track_audio_features["id"],
                        "tempo": round(track_audio_features["tempo"]),
                    }
                    for track_audio_features in audio_features
                ]
            )

        return tracks_with_tempos

    def add_tracks_to_playlist(self, playlist_id: str, track_ids: list) -> None:
        """
        Add tracks to playlist (skips duplicates).
        """
        track_ids_in_playlist = {
            track["id"] for track in self.get_tracks_from_playlist(playlist_id)
        }
        track_ids_to_add = [
            track_id for track_id in track_ids if track_id not in track_ids_in_playlist
        ]

        if not track_ids_to_add:
            logging.info(f"All tracks are already in the playlist id: {playlist_id}.")
        else:
            logging.info(f"Adding tracks to playlist id: {playlist_id}")
            self.sp.playlist_add_items(playlist_id=playlist_id, items=track_ids_to_add)
