import zipfile
from pathlib import Path

import pytest

from app.classes.helpers.file_helpers import FileHelpers
from app.classes.helpers.helpers import Helpers


def test_validate_traversal_allows_child_path(tmp_path) -> None:
    base = tmp_path / "base"
    allowed = base / "child" / "file.txt"

    assert Helpers.validate_traversal(base, allowed) == allowed.resolve()


def test_validate_traversal_rejects_parent_path(tmp_path) -> None:
    base = tmp_path / "base"
    bad_relative = Path("..") / "outside.txt"

    with pytest.raises(ValueError):
        Helpers.validate_traversal(base, bad_relative)


def test_validate_traversal_rejects_absolute_path(tmp_path) -> None:
    base = tmp_path / "base"
    bad_absolute = (tmp_path.parent / "outside.txt").resolve()

    with pytest.raises(ValueError):
        Helpers.validate_traversal(base, bad_absolute)


def test_unzip_file_strips_parent_segments(tmp_path, monkeypatch) -> None:
    archive_path = tmp_path / "archive.zip"
    destination = tmp_path / "dest"

    with zipfile.ZipFile(archive_path, "w") as zip_ref:
        zip_ref.writestr("../outside.txt", "nope")
        zip_ref.writestr("dir/ok.txt", "ok")

    file_helper = FileHelpers(None)
    monkeypatch.setattr(file_helper, "send_percentage", lambda *args, **kwargs: None)

    file_helper.unzip_file(
        str(archive_path),
        str(destination),
        user_id=["test"],
    )

    assert (destination / "outside.txt").exists()
    assert (destination / "dir" / "ok.txt").exists()
    assert not (tmp_path / "outside.txt").exists()
