from dataclasses import dataclass, field

from spotipy_client import SpotipyClient


@dataclass
class TempoPlaylist:
    low_tempo: int
    high_tempo: int
    name: str = ""
    id: str = ""
    track_ids: set[str] = field(default_factory=set)

    def __post_init__(self):
        if not self.name:
            self.name = f"auto-playlist-by-tempo [{self.low_tempo}, {self.high_tempo}]"

    def is_tempo_in_range(self, tempo: int) -> bool:
        if (self.low_tempo <= tempo) and (tempo <= self.high_tempo):
            return True
        return False

    def add_track(self, track_id: str):
        self.track_ids.add(track_id)


@dataclass
class TempoOrganizer:
    start_tempo: int
    end_tempo: int
    increment: int
    max_tempo: int = 300
    playlists: list[TempoPlaylist] = field(default_factory=list)

    def __post_init__(self):
        self.playlists.append(TempoPlaylist(0, self.start_tempo - 1))
        for tempo in range(self.start_tempo, self.end_tempo, self.increment):
            self.playlists.append(TempoPlaylist(tempo, tempo + self.increment - 1))
        self.playlists.append(TempoPlaylist(self.end_tempo, self.max_tempo - 1))

    def add_track_by_tempo(self, track_id: str, track_tempo: int):
        if track_tempo >= self.max_tempo:
            raise ValueError(
                f"Track tempo is higher than maximum allowed tempo {self.max_tempo}",
            )

        for playlist in self.playlists:
            if playlist.is_tempo_in_range(track_tempo):
                playlist.add_track(track_id)


def main():
    sp = SpotipyClient()

    tempo_organizer = TempoOrganizer(start_tempo=50, end_tempo=155, increment=15)
    current_user_playlists = sp.get_current_user_playlists(
        owned_playlist_only=True,
        excluded_playlists=[playlist.name for playlist in tempo_organizer.playlists],
    )

    for playlist in current_user_playlists:
        print(
            f'----------- Playlist: {playlist['name']} (ID: {playlist['id']}) -------------'
        )
        tracks = sp.get_tracks_from_playlist(playlist["id"])
        tempos = sp.get_several_tracks_tempo([track["id"] for track in tracks])
        for track_tempo in tempos:
            tempo_organizer.add_track_by_tempo(
                track_id=track_tempo["id"], track_tempo=track_tempo["tempo"]
            )

    # Actual creation of playlists and adding tracks in Spotify:
    for tempo_playlist in tempo_organizer.playlists:
        created_playlist = sp.create_playlist(tempo_playlist.name)
        tempo_playlist.id = created_playlist["id"]
        if tempo_playlist.track_ids:
            sp.add_tracks_to_playlist(tempo_playlist.id, tempo_playlist.track_ids)

    sp.unfollow_empty_playlists()


if __name__ == "__main__":
    main()
    # Add a dependency to python 3.12
