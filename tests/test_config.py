"""Configuration parsing tests."""

from __future__ import annotations

import pytest

from movielist.config import Settings


def test_path_mappings_comma_form(monkeypatch):
    monkeypatch.setenv(
        "MEDIA_PATH_MAPPINGS",
        "smb://nas/MediaDrive/=/mnt/MediaDrive,smb://nas2/TV=/mnt/TV",
    )
    s = Settings.load()
    assert s.media_path_mappings == {
        "smb://nas/MediaDrive/": "/mnt/MediaDrive",
        "smb://nas2/TV": "/mnt/TV",
    }


def test_path_mappings_json_form(monkeypatch):
    import json

    monkeypatch.setenv(
        "MEDIA_PATH_MAPPINGS",
        json.dumps({"smb://nas/MediaDrive/": "/mnt/MediaDrive"}),
    )
    s = Settings.load()
    assert s.media_path_mappings["smb://nas/MediaDrive/"] == "/mnt/MediaDrive"


def test_path_mappings_invalid(monkeypatch):
    monkeypatch.setenv("MEDIA_PATH_MAPPINGS", "nonsense")
    with pytest.raises(ValueError):
        Settings.load()


def test_approved_hosts_parsed(monkeypatch):
    monkeypatch.setenv(
        "APPROVED_ARTWORK_HOSTS", "Image.TMDB.org, assets.fanart.tv"
    )
    s = Settings.load()
    assert s.approved_artwork_hosts == {"image.tmdb.org", "assets.fanart.tv"}


def test_db_name_validation(monkeypatch):
    monkeypatch.setenv("KODI_DB_NAME", "MyVideos131; DROP TABLE movie")
    with pytest.raises(ValueError):
        Settings.load()


def test_root_path_normalized(monkeypatch):
    monkeypatch.setenv("MOVIELIST_ROOT_PATH", "/ML/")
    s = Settings.load()
    assert s.root_path == "/ML"


def test_no_password_in_repr(monkeypatch):
    monkeypatch.setenv("KODI_DB_PASSWORD", "supersecret")
    s = Settings.load()
    assert "supersecret" not in repr(s)
    assert "supersecret" not in str(s)


def test_defaults(monkeypatch):
    for var in (
        "KODI_DB_HOST", "KODI_DB_PORT", "KODI_DB_NAME", "KODI_DB_USER",
        "KODI_DB_PASSWORD", "MEDIA_PATH_MAPPINGS", "APPROVED_ARTWORK_HOSTS",
        "ARTWORK_ALLOWED_DIRS", "MOVIELIST_ROOT_PATH", "LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)
    s = Settings.load()
    assert s.kodi_db_name == "MyVideos131"  # never auto-switches versions
    assert s.kodi_db_port == 3306
    assert s.media_path_mappings == {}
    assert s.approved_artwork_hosts == frozenset()  # remote blocked by default
