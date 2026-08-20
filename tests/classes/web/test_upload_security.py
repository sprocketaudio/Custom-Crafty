import asyncio
from types import SimpleNamespace

import pytest

from app.classes.helpers.helpers import Helpers
from app.classes.web.routes.api.crafty.upload.index import ApiFilesUploadHandler


def _handler_for_path_validation(tmp_path, filename: str, *, chunked: bool = False):
    handler = ApiFilesUploadHandler.__new__(ApiFilesUploadHandler)
    handler.filename = filename
    handler.chunked = chunked
    handler.file_id = "upload-123" if chunked else None
    handler.chunk_index = None
    handler.upload_dir = tmp_path / "uploads"
    handler.controller = SimpleNamespace(project_root=tmp_path)
    handler.helper = SimpleNamespace(validate_traversal=Helpers.validate_traversal)
    return handler


def test_upload_path_validation_keeps_regular_and_chunk_paths_in_scope(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)

    handler._validate_upload_paths()

    assert handler.temp_dir == (tmp_path / "temp" / "upload-123").resolve()


@pytest.mark.parametrize("filename", ["../outside.jar", "nested/file.jar", ""])
def test_upload_path_validation_rejects_unsafe_filenames(tmp_path, filename):
    handler = _handler_for_path_validation(tmp_path, filename)

    with pytest.raises(ValueError):
        handler._validate_upload_paths()


def test_upload_path_validation_rejects_chunk_id_traversal(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)
    handler.file_id = "../outside"

    with pytest.raises(ValueError):
        handler._validate_upload_paths()


def test_upload_path_validation_rejects_non_numeric_chunk_id(tmp_path):
    handler = _handler_for_path_validation(tmp_path, "server.jar", chunked=True)
    handler.chunk_index = "../0"

    with pytest.raises(ValueError):
        handler._validate_upload_paths()


def test_server_upload_rejects_user_without_server_access():
    handler = ApiFilesUploadHandler.__new__(ApiFilesUploadHandler)
    handler.authenticate_user = lambda: (
        [],
        None,
        None,
        None,
        {"user_id": 12, "lang": "en_EN", "superuser": False},
        None,
    )
    handler.request = SimpleNamespace(headers={})
    handler.helper = SimpleNamespace(
        translation=SimpleNamespace(translate=lambda *_args: "Insufficient permissions")
    )
    handler.finish_json = lambda status, body: (status, body)

    status, body = asyncio.run(handler.post("server-1"))

    assert status == 400
    assert body["error"] == "NOT_AUTHORIZED"


def test_server_upload_requires_files_permission():
    handler = ApiFilesUploadHandler.__new__(ApiFilesUploadHandler)
    handler.authenticate_user = lambda: (
        [{"server_id": "server-1"}],
        None,
        None,
        None,
        {"user_id": 12, "lang": "en_EN", "superuser": False},
        None,
    )
    handler.request = SimpleNamespace(headers={})
    handler.helper = SimpleNamespace(
        translation=SimpleNamespace(translate=lambda *_args: "Insufficient permissions")
    )
    handler.controller = SimpleNamespace(
        server_perms=SimpleNamespace(
            get_user_permissions_mask=lambda *_args: 0,
            get_lowest_api_perm_mask=lambda *_args: 0,
            get_permissions=lambda _mask: set(),
        )
    )
    handler.finish_json = lambda status, body: (status, body)

    status, body = asyncio.run(handler.post("server-1"))

    assert status == 400
    assert body["error"] == "NOT_AUTHORIZED"
