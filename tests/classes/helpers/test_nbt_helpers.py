import os
import tempfile

import pytest

from app.classes.helpers.nbt_helpers import NbtFileError, NbtFileHelpers

nbtlib = pytest.importorskip("nbtlib")


def _write_nbt_file(path: str, *, gzipped: bool) -> None:
    payload = nbtlib.Compound(
        {
            "DataVersion": nbtlib.Int(3700),
            "Name": nbtlib.String("UnitTest"),
            "Initialized": nbtlib.Byte(1),
        }
    )
    nbt_file = nbtlib.File(payload, root_name="")
    nbt_file.save(path, gzipped=gzipped)


def _cleanup_file_and_backup(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)
    backup_path = NbtFileHelpers.get_backup_path(path)
    if os.path.exists(backup_path):
        os.remove(backup_path)


def test_nbt_helper_roundtrip_gzipped_dat_file() -> None:
    fd, path = tempfile.mkstemp(suffix=".dat")
    os.close(fd)
    try:
        _write_nbt_file(path, gzipped=True)
        rendered_snbt = NbtFileHelpers.read_as_snbt(path)
        assert "DataVersion" in rendered_snbt
        assert 'Name: "UnitTest"' in rendered_snbt

        updated_snbt = rendered_snbt.replace('"UnitTest"', '"UpdatedName"')
        backup_path = NbtFileHelpers.write_from_snbt(path, updated_snbt)
        assert backup_path == f"{path}{NbtFileHelpers.NBT_BACKUP_SUFFIX}"
        assert os.path.exists(backup_path)

        loaded = nbtlib.load(path, gzipped=True)
        assert loaded["Name"] == nbtlib.String("UpdatedName")
        assert loaded.gzipped is True
    finally:
        _cleanup_file_and_backup(path)


def test_nbt_helper_roundtrip_uncompressed_dat_file() -> None:
    fd, path = tempfile.mkstemp(suffix=".dat")
    os.close(fd)
    try:
        _write_nbt_file(path, gzipped=False)
        rendered_snbt = NbtFileHelpers.read_as_snbt(path)
        assert "DataVersion" in rendered_snbt

        updated_snbt = rendered_snbt.replace("3700", "3800")
        NbtFileHelpers.write_from_snbt(path, updated_snbt)

        loaded = nbtlib.load(path, gzipped=False)
        assert int(loaded["DataVersion"]) == 3800
        assert loaded.gzipped is False
    finally:
        _cleanup_file_and_backup(path)


def test_nbt_helper_rejects_non_compound_root() -> None:
    fd, path = tempfile.mkstemp(suffix=".dat")
    os.close(fd)
    try:
        _write_nbt_file(path, gzipped=True)
        with pytest.raises(NbtFileError):
            NbtFileHelpers.write_from_snbt(path, "1")
    finally:
        _cleanup_file_and_backup(path)


def test_nbt_helper_roundtrip_json_mode_preserves_existing_tag_types() -> None:
    fd, path = tempfile.mkstemp(suffix=".dat")
    os.close(fd)
    try:
        _write_nbt_file(path, gzipped=True)
        rendered_json = NbtFileHelpers.read_as_json(path)
        assert '"DataVersion": 3700' in rendered_json
        assert '"Initialized": 1' in rendered_json

        updated_json = rendered_json.replace("3700", "3900").replace("UnitTest", "JSONEdit")
        backup_path = NbtFileHelpers.write_from_json(path, updated_json)
        assert os.path.exists(backup_path)

        loaded = nbtlib.load(path, gzipped=True)
        assert loaded["DataVersion"] == nbtlib.Int(3900)
        assert loaded["Name"] == nbtlib.String("JSONEdit")
        # Ensure we kept the original Byte tag type for this field.
        assert loaded["Initialized"] == nbtlib.Byte(1)
    finally:
        _cleanup_file_and_backup(path)


def test_nbt_helper_json_mode_rejects_unknown_keys() -> None:
    fd, path = tempfile.mkstemp(suffix=".dat")
    os.close(fd)
    try:
        _write_nbt_file(path, gzipped=True)
        rendered_json = NbtFileHelpers.read_as_json(path)
        injected = rendered_json.replace(
            '"Name": "UnitTest"', '"Name": "UnitTest",\n  "InjectedField": 123'
        )
        with pytest.raises(NbtFileError):
            NbtFileHelpers.write_from_json(path, injected)
    finally:
        _cleanup_file_and_backup(path)
