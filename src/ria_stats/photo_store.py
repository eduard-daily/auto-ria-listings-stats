"""Where downloaded photos live. Everything that reads or writes photo files goes through here,
addressing them by key ("<ria auto id>/<photo id>.jpg", stored in listing_photos.key), so a
different backend, such as S3, only has to replace this module.
"""
from pathlib import Path

from ria_stats.db import DB_PATH

PHOTOS_DIR = DB_PATH.parent / "photos"


def save(key: str, data: bytes) -> None:
    path = PHOTOS_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    partial.write_bytes(data)
    partial.replace(path)  # a half-written file never appears under its final name


def path(key: str) -> Path:
    return PHOTOS_DIR / key
