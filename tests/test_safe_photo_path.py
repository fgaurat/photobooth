import os

import app


def test_safe_photo_path_accepts_a_bare_filename():
    result = app.safe_photo_path("photo_20260704_162953_360619.jpg")
    assert result == os.path.join(os.path.realpath(app.PHOTOS_DIR), "photo_20260704_162953_360619.jpg")


def test_safe_photo_path_rejects_parent_directory_traversal():
    assert app.safe_photo_path("../../etc/passwd") is None


def test_safe_photo_path_rejects_an_absolute_path():
    assert app.safe_photo_path("/etc/passwd") is None


def test_safe_photo_path_rejects_a_subdirectory():
    assert app.safe_photo_path("sub/photo.jpg") is None


def test_safe_photo_path_rejects_empty_or_missing_filename():
    assert app.safe_photo_path("") is None
    assert app.safe_photo_path(None) is None
